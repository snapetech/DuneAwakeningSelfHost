#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from dune_whisper_route import whisper_route_for_fls_id


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "backups" / "admin-bot"
STATE_FILE = STATE_DIR / "player-presence.json"
DB = "dune_sb_1_4_0_0"
STARTER_BASE_TOOL_TEMPLATE = "BaseBackupTool"
STARTER_BASE_TOOL_MESSAGE = "A Base Reconstruction Tool has been added to your inventory. You may need to log out and back in before it appears."
ADMIN_ANOMALY_DIGEST_TEMPLATE = "Admin digest: stale online activity={stuck_count} ({stuck_names}); over base cap={over_base_cap}."
RESTART_STATE_FILE = ROOT / "backups" / "admin-panel" / "restart-jobs.json"
ANNOUNCEMENT_STATE_FILE = ROOT / "backups" / "admin-panel" / "announcements.json"
AUDIT_FILE = ROOT / "backups" / "admin-panel" / "audit.jsonl"


def read_env_file(path):
    values = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


FILE_ENV = read_env_file(ROOT / os.environ.get("DUNE_ADMIN_BOT_ENV_FILE", ".env"))


def env(name, default=""):
    return os.environ.get(name) or FILE_ENV.get(name) or default


def env_bool(name, default=False):
    return str(env(name, "true" if default else "false")).lower() in ("1", "true", "yes", "on")


def env_is_set(name):
    return name in os.environ or name in FILE_ENV


def configured_base_cap():
    config_path = ROOT / env("DUNE_PLAYER_PRESENCE_BASE_CAP_CONFIG", "config/UserGame.ini")
    target_map = env("DUNE_PLAYER_PRESENCE_BASE_CAP_MAP", "HaggaBasin")
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return int(env("DUNE_PLAYER_PRESENCE_BASE_CAP", env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6")))

    match = re.search(r"^m_MaxLandclaimSegmentsPerMap\s*=\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        return int(env("DUNE_PLAYER_PRESENCE_BASE_CAP", env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6")))

    entries = re.findall(r'Name="([^"]+)"\)\s*,\s*(\d+)', match.group(1))
    for map_name, cap in entries:
        if map_name == target_map:
            return int(cap)
    if entries:
        return int(entries[0][1])
    return int(env("DUNE_PLAYER_PRESENCE_BASE_CAP", env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6")))


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def now_ts():
    return int(time.time())


def compose_cmd(*args):
    files = env("COMPOSE_FILES", "compose.yaml").split(":")
    cmd = [env("CONTAINER_RUNTIME", "docker"), "compose"]
    for file in files:
        if file:
            cmd.extend(["-f", file])
    cmd.extend(["--env-file", env("DUNE_ADMIN_BOT_ENV_FILE", ".env")])
    cmd.extend(args)
    return cmd


def run(cmd, timeout=30):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_json_file(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {} if default is None else default


def file_hash(paths):
    digest = hashlib.sha256()
    found = False
    for rel in paths:
        path = ROOT / rel
        if path.exists():
            found = True
            digest.update(str(rel).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest() if found else ""


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def online_players():
    sql = """
    select
      ps.account_id::text,
      coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name,
      acc.user as fls_id,
      coalesce(act.map, wp.map, '') as map_name,
      coalesce(wp.label, '') as partition_label,
      ((act.transform).location).x::float8 as x,
      ((act.transform).location).y::float8 as y,
      ((act.transform).location).z::float8 as z
    from dune.player_state ps
    left join dune.accounts acc on acc.id = ps.account_id
    left join dune.actors act on act.id = ps.player_pawn_id
    left join dune.world_partition wp on wp.partition_id = act.partition_id
    where ps.online_status::text = 'Online'
    order by ps.character_name nulls last, ps.account_id;
    """
    result = run(compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-F", "\t", "-c", sql), timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "online player query failed")
    players = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        account_id = parts[0]
        name = parts[1] if len(parts) > 1 else account_id
        fls_id = parts[2] if len(parts) > 2 else ""
        map_name = parts[3] if len(parts) > 3 else ""
        partition_label = parts[4] if len(parts) > 4 else ""
        players[account_id] = {
            "name": name or account_id,
            "flsId": fls_id,
            "map": map_name,
            "partitionLabel": partition_label,
            "x": parts[5] if len(parts) > 5 else "",
            "y": parts[6] if len(parts) > 6 else "",
            "z": parts[7] if len(parts) > 7 else "",
        }
    return players


def base_claim_counts():
    sql = """
    select
      a.owner_account_id::text,
      count(distinct t.id)::int as base_count,
      count(ls.*)::int as segment_count
    from dune.totems t
    join dune.actors a on a.id = t.id
    left join dune.landclaim_segments ls on ls.totem_id = t.id
    where a.owner_account_id is not null
    group by a.owner_account_id;
    """
    result = run(compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-F", "\t", "-c", sql), timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "base claim query failed")
    counts = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        account_id, base_count, segment_count = (line.split("\t") + ["0", "0"])[:3]
        counts[account_id] = {"baseCount": int(base_count or 0), "segmentCount": int(segment_count or 0)}
    return counts


def map_health_summary():
    sql = """
    with active as (
      select server_id from dune.active_server_ids
    ),
    status as (
      select
        wp.partition_id,
        coalesce(nullif(wp.label, ''), wp.map || ' #' || wp.partition_id::text) as label,
        wp.map,
        wp.server_id,
        coalesce(fs.ready, false) as ready,
        coalesce(fs.alive, false) as alive,
        active.server_id is not null as active,
        coalesce(wp.blocked, false) as blocked,
        coalesce(fs.connected_players, 0)::int as connected_players
      from dune.world_partition wp
      left join dune.farm_state fs on fs.server_id = wp.server_id
      left join active on active.server_id = wp.server_id
    )
    select jsonb_build_object(
      'expected', count(*),
      'online', count(*) filter (where server_id is not null and alive and active and not blocked),
      'readyAlive', count(*) filter (where ready and alive and active and not blocked),
      'activeServers', (select count(*) from active),
      'connectedPlayers', coalesce(sum(connected_players), 0),
      'offlineLabels', coalesce(jsonb_agg(label order by label) filter (where not (server_id is not null and alive and active and not blocked)), '[]'::jsonb),
      'playersByMap', coalesce(jsonb_object_agg(label, connected_players order by label), '{}'::jsonb)
    )::text
    from status;
    """
    result = run(compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-c", sql), timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "map health query failed")
    text = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}"
    return json.loads(text)


def player_roster_by_map():
    sql = """
    select
      coalesce(nullif(wp.label, ''), nullif(act.map, ''), nullif(wp.map, ''), 'Unknown') as map_label,
      coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name
    from dune.player_state ps
    left join dune.actors act on act.id = ps.player_pawn_id
    left join dune.world_partition wp on wp.partition_id = act.partition_id
    where ps.online_status::text = 'Online'
    order by map_label, character_name;
    """
    result = run(compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-F", "\t", "-c", sql), timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "player roster by map query failed")
    roster = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        map_label, name = (line.split("\t") + [""])[:2]
        roster.setdefault(map_label or "Unknown", []).append(name)
    return roster


def compact_roster_by_map(roster, map_limit=8, player_limit=8):
    if not roster:
        return "no online players"
    parts = []
    for map_label in sorted(roster)[:map_limit]:
        players = roster[map_label]
        shown = ", ".join(players[:player_limit])
        if len(players) > player_limit:
            shown += f", +{len(players) - player_limit} more"
        parts.append(f"{map_label}: {shown}")
    if len(roster) > map_limit:
        parts.append(f"+{len(roster) - map_limit} more maps")
    return "; ".join(parts)


def service_health_checks():
    checks = []
    for unit in [item.strip() for item in env("DUNE_PLAYER_PRESENCE_SERVICE_HEALTH_UNITS", "dune-player-presence-announcer.service").split(",") if item.strip()]:
        result = run(["systemctl", "is-active", unit], timeout=5)
        checks.append({"name": unit, "ok": result.returncode == 0, "status": result.stdout.strip() or result.stderr.strip()})
    max_age = int(env("DUNE_PLAYER_PRESENCE_FRESHNESS_MAX_AGE_SECONDS", "300"))
    missing_grace = int(env("DUNE_PLAYER_PRESENCE_FRESHNESS_MISSING_GRACE_SECONDS", "900"))
    default_optional_missing = "" if env_is_set("DUNE_PLAYER_PRESENCE_FRESHNESS_FILES") else "public-site/static/hagga-map.svg"
    optional_missing = {
        item.strip()
        for item in env("DUNE_PLAYER_PRESENCE_FRESHNESS_OPTIONAL_MISSING_FILES", default_optional_missing).split(",")
        if item.strip()
    }
    anchor_paths = [
        ROOT / item.strip()
        for item in env("DUNE_PLAYER_PRESENCE_FRESHNESS_ANCHOR_FILES", "public-site/static/players.json").split(",")
        if item.strip()
    ]
    newest_anchor_mtime = max((path.stat().st_mtime for path in anchor_paths if path.exists()), default=0)
    freshness_files = [
        item.strip()
        for item in env("DUNE_PLAYER_PRESENCE_FRESHNESS_FILES", "public-site/static/players.json").split(",")
        if item.strip() and item.strip().lower() not in ("none", "off", "false", "disabled")
    ]
    for rel in freshness_files:
        path = ROOT / rel
        if not path.exists():
            anchor_age = int(time.time() - newest_anchor_mtime) if newest_anchor_mtime else None
            if rel in optional_missing and newest_anchor_mtime and anchor_age is not None and anchor_age <= missing_grace:
                checks.append({"name": rel, "ok": True, "status": f"missing but optional; anchor age={anchor_age}s"})
            else:
                checks.append({"name": rel, "ok": False, "status": "missing"})
            continue
        age = int(time.time() - path.stat().st_mtime)
        checks.append({"name": rel, "ok": age <= max_age, "status": f"age={age}s"})
    if env_bool("DUNE_PLAYER_PRESENCE_FLS_PUBLICATION_HEALTH_ENABLED", True):
        result = run([
            str(ROOT / "scripts" / "fls-publication-health.py"),
            env("DUNE_PLAYER_PRESENCE_ENV_FILE", ".env"),
            "--compose-files",
            env("COMPOSE_FILES", "compose.yaml"),
            "--json",
        ], timeout=int(env("DUNE_PLAYER_PRESENCE_FLS_PUBLICATION_HEALTH_TIMEOUT_SECONDS", "30")))
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        except Exception:
            payload = {}
        failed = [item for item in payload.get("checks", []) if not item.get("ok")]
        if result.returncode == 0 and payload.get("ok"):
            checks.append({"name": "FLS publication", "ok": True, "status": payload.get("state", "healthy")})
        else:
            summary = "; ".join(f"{item.get('name')}: {item.get('value', '')}" for item in failed[:3])
            if not summary:
                summary = (result.stderr or result.stdout or "unknown failure").strip()[:240]
            checks.append({"name": "FLS publication", "ok": False, "status": summary})
    return checks


def latest_backup_age_hours():
    candidates = []
    for path in (ROOT / "backups").glob("*"):
        if path.is_dir() and ((path / "manifest.txt").exists() or (path / "manifest.json").exists()):
            candidates.append(path)
    for path in (ROOT / "backups" / "admin-panel" / "maintenance").glob("*"):
        if path.is_dir() and (path / "manifest.json").exists():
            candidates.append(path)
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    return {"path": str(latest.relative_to(ROOT)), "ageHours": round((time.time() - latest.stat().st_mtime) / 3600, 2)}


def failed_restart_jobs_since(since_ts):
    jobs = []
    for job in load_json_file(RESTART_STATE_FILE, {"jobs": []}).get("jobs", []):
        ts = float(job.get("executedAt") or job.get("createdAt") or 0)
        if job.get("status") == "failed" and ts > since_ts:
            jobs.append({"id": job.get("id"), "target": job.get("targetLabel") or job.get("target") or "unknown", "error": (job.get("lastError") or "")[:180]})
    return jobs


def cancelled_jobs_since(since_ts):
    jobs = []
    for path in (RESTART_STATE_FILE, ANNOUNCEMENT_STATE_FILE):
        for job in load_json_file(path, {"jobs": []}).get("jobs", []):
            ts = float(job.get("cancelledAt") or 0)
            if job.get("status") == "cancelled" and ts > since_ts:
                jobs.append({"id": job.get("id"), "source": path.name, "message": job.get("message", "")})
    return jobs


def audit_counts_since(offset):
    counts = {}
    mutations = 0
    if not AUDIT_FILE.exists():
        return {"offset": 0, "counts": counts, "mutations": mutations}
    size = AUDIT_FILE.stat().st_size
    if offset > size:
        offset = 0
    with AUDIT_FILE.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = event.get("event") or event.get("action") or "unknown"
            counts[name] = counts.get(name, 0) + 1
            if any(token in name.lower() for token in ("write", "grant", "mutation", "restart", "transfer", "config")):
                mutations += 1
        offset = handle.tell()
    return {"offset": offset, "counts": counts, "mutations": mutations}


def stuck_transition_players(minutes):
    sql = f"""
    select ps.account_id::text,
           coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name,
           ps.online_status::text,
           coalesce(fs.map, '') as map,
           floor(extract(epoch from (now() - ps.last_avatar_activity)) / 60)::int as stale_minutes
    from dune.player_state ps
    left join dune.farm_state fs on fs.server_id = ps.server_id
    where ps.online_status::text = 'Online'
      and ps.last_avatar_activity < now() - interval '{int(minutes)} minutes'
    order by ps.last_avatar_activity asc
    limit 25;
    """
    result = run(compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-F", "\t", "-c", sql), timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "stuck transition query failed")
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        account_id, name, status, map_name, stale_minutes = (line.split("\t") + ["", "", "", ""])[:5]
        rows.append({"accountId": account_id, "name": name, "status": status, "map": map_name, "staleMinutes": stale_minutes})
    return rows


def player_name(player):
    if isinstance(player, dict):
        return player.get("name") or player.get("characterName") or player.get("accountId") or "unknown"
    return str(player)


def player_fls_id(player):
    if isinstance(player, dict):
        return player.get("flsId") or ""
    return ""


def player_map(player):
    if isinstance(player, dict):
        return player.get("map") or ""
    return ""


def player_location_label(player):
    if not isinstance(player, dict):
        return ""
    return player.get("partitionLabel") or player.get("map") or ""


def admin_players(current):
    names = {item.strip().lower() for item in env("DUNE_PLAYER_PRESENCE_ADMIN_NAMES", env("DUNE_CHAT_COMMAND_ADMINS", "")).split(",") if item.strip()}
    fls_ids = {item.strip() for item in env("DUNE_PLAYER_PRESENCE_ADMIN_FLS_IDS", env("DUNE_CHAT_COMMAND_ADMIN_FLS_IDS", "")).split(",") if item.strip()}
    admins = {}
    for account_id, player in current.items():
        if (names and player_name(player).lower() in names) or (fls_ids and player_fls_id(player) in fls_ids):
            admins[account_id] = player
    return admins


def completed_journey_players(story_node_id):
    sql = f"""
    select ps.account_id::text, coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name
    from dune.journey_story_node jsn
    join dune.player_state ps on ps.account_id = jsn.account_id
    where jsn.story_node_id = {sql_literal(story_node_id)}
      and jsn.complete_condition_state = 'true'::jsonb
    order by ps.character_name nulls last, ps.account_id;
    """
    result = run(
        compose_cmd(
            "exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB,
            "-At", "-F", "\t", "-c", sql,
        ),
        timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "journey completion query failed")
    players = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        account_id, _, name = line.partition("\t")
        players[account_id] = name or account_id
    return players


def grant_starter_base_tool(account_id):
    template_id = env("DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_TEMPLATE", STARTER_BASE_TOOL_TEMPLATE)
    preferred_inventory_type = int(env("DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_INVENTORY_TYPE", "0"))
    sql = f"""
    with player as (
      select account_id, character_name, player_pawn_id, player_controller_id
      from dune.player_state
      where account_id = {int(account_id)}
      limit 1
    ),
    owned_inventories as (
      select inv.id as inventory_id, inv.inventory_type, inv.max_item_count
      from player p
      join dune.inventories inv on inv.actor_id in (p.player_pawn_id, p.player_controller_id)
    ),
    existing as (
      select i.id as item_id, i.inventory_id
      from owned_inventories inv
      join dune.items i on i.inventory_id = inv.inventory_id
      where i.template_id = {sql_literal(template_id)}
      limit 1
    ),
    candidate_inventories as (
      select inv.inventory_id, inv.inventory_type, inv.max_item_count
      from owned_inventories inv
      where not exists (select 1 from existing)
      order by
        case when inv.inventory_type = {preferred_inventory_type} then 0 else 1 end,
        case when inv.max_item_count is null or inv.max_item_count < 0 then 1 else 0 end,
        inv.inventory_type nulls last,
        inv.inventory_id
    ),
    finite_slots as (
      select ci.inventory_id, ci.inventory_type, slot.position_index
      from candidate_inventories ci
      cross join lateral generate_series(0, ci.max_item_count - 1) as slot(position_index)
      where ci.max_item_count is not null and ci.max_item_count > 0
        and not exists (
          select 1 from dune.items i
          where i.inventory_id = ci.inventory_id
            and i.position_index = slot.position_index
        )
    ),
    unbounded_slots as (
      select ci.inventory_id, ci.inventory_type, coalesce(max(i.position_index), -1) + 1 as position_index
      from candidate_inventories ci
      left join dune.items i on i.inventory_id = ci.inventory_id
      where ci.max_item_count is null or ci.max_item_count < 0
      group by ci.inventory_id, ci.inventory_type
    ),
    target as (
      select inventory_id, inventory_type, position_index
      from (
        select inventory_id, inventory_type, position_index from finite_slots
        union all
        select inventory_id, inventory_type, position_index from unbounded_slots
      ) slots
      order by
        case when inventory_type = {preferred_inventory_type} then 0 else 1 end,
        inventory_type nulls last,
        inventory_id,
        position_index
      limit 1
    ),
    next_item as (
      select dune.advance_items_id_sequencer(1) as item_id
      where exists (select 1 from target)
    ),
    saved as (
      select dune.save_item((
        next_item.item_id,
        target.inventory_id,
        1,
        target.position_index,
        {sql_literal(template_id)},
        true,
        (extract(epoch from now()))::bigint,
        '{{}}'::jsonb,
        0,
        null
      )::dune.inventoryitem) as ok,
      next_item.item_id,
      target.inventory_id,
      target.position_index,
      target.inventory_type
      from next_item, target
    )
    select jsonb_build_object(
      'accountId', (select account_id from player),
      'characterName', (select character_name from player),
      'templateId', {sql_literal(template_id)},
      'alreadyHadItem', exists(select 1 from existing),
      'granted', exists(select 1 from saved),
      'itemId', (select item_id from saved),
      'inventoryId', coalesce((select inventory_id from saved), (select inventory_id from existing)),
      'inventoryType', (select inventory_type from saved),
      'positionIndex', (select position_index from saved),
      'error', case
        when not exists(select 1 from player) then 'player not found'
        when exists(select 1 from existing) then null
        when not exists(select 1 from target) then 'no empty owned inventory slot'
        else null
      end
    )::text;
    """
    result = run(
        compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-c", sql),
        timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")),
    )
    if result.returncode != 0:
        return {"ok": False, "accountId": account_id, "error": result.stderr.strip() or "starter base tool grant failed"}
    text = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}"
    payload = json.loads(text)
    payload["ok"] = bool(payload.get("alreadyHadItem") or payload.get("granted"))
    return payload


def announce(message):
    command = env("DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh")))
    if command.startswith("/workspace/"):
        command = str(ROOT / command.removeprefix("/workspace/"))
    timeout = int(env("DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS", env("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45")))
    child_env = os.environ.copy()
    child_env.update(FILE_ENV)
    child_env["DUNE_ANNOUNCE_MESSAGE"] = message
    child_env["DUNE_ANNOUNCE_JOB_ID"] = "player-presence"
    child_env["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"] = "true"
    child_env["DUNE_ANNOUNCE_CHAT_EXCHANGE"] = env("DUNE_PLAYER_PRESENCE_ANNOUNCE_EXCHANGE", env("DUNE_ANNOUNCE_CHAT_EXCHANGE", "chat.map"))
    child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_PLAYER_PRESENCE_ANNOUNCE_CHANNEL", env("DUNE_ANNOUNCE_CHAT_CHANNEL", "Map"))
    child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = env("DUNE_PLAYER_PRESENCE_ANNOUNCE_ROUTING_KEYS", "<empty>") or "<empty>"
    child_env["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"] = env("DUNE_PLAYER_PRESENCE_ANNOUNCE_BIND_ONLINE_QUEUES", env("DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES", "true"))
    result = subprocess.run([command, message], cwd=ROOT, env=child_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "routingKeys": child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"],
        "exchange": child_env["DUNE_ANNOUNCE_CHAT_EXCHANGE"],
        "channel": child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"],
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def private_message(player, message, job_id="player-presence-private-message"):
    fls_id = player_fls_id(player)
    name = player_name(player)
    route = whisper_route_for_fls_id(fls_id)
    if not route["ok"]:
        return {"ok": False, "error": route["error"], "player": name}
    command = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_COMMAND", env("DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh"))))
    if command.startswith("/workspace/"):
        command = str(ROOT / command.removeprefix("/workspace/"))
    timeout = int(env("DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS", env("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45")))
    child_env = os.environ.copy()
    child_env.update(FILE_ENV)
    child_env["DUNE_ANNOUNCE_MESSAGE"] = message
    child_env["DUNE_ANNOUNCE_JOB_ID"] = job_id
    child_env["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"] = "true"
    child_env["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"] = "false"
    child_env["DUNE_ANNOUNCE_CHAT_EXCHANGE"] = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_EXCHANGE", "chat.whispers")
    child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL", "Whispers")
    child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = name
    child_env["DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS"] = route["routingKey"]
    child_env["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"] = route["queue"]
    child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_ROUTING_KEY", route["routingKey"]) or route["routingKey"]
    child_env["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"] = "false"
    child_env["DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS"] = "true"
    result = subprocess.run([command, message], cwd=ROOT, env=child_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "targetFlsId": route["routingKey"],
        "targetQueue": route["queue"],
        "channel": child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"],
        "userNameTo": name,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def private_join_message(player, message):
    return private_message(player, message, "player-presence-private-welcome")


def render_template(template, player_name, count, **extra):
    context = {
        "playername": player_name,
        "player_name": player_name,
        "count": count,
        "player_count": count,
        "server_name": env("DUNE_PLAYER_PRESENCE_SERVER_NAME", env("DUNE_SERVER_DISPLAY_NAME", env("WORLD_NAME", "this server"))),
        "server_url": env("DUNE_PLAYER_PRESENCE_SERVER_URL", env("DUNE_PUBLIC_SITE_URL", "")),
        "rules_url": env("DUNE_PLAYER_PRESENCE_RULES_URL", env("DUNE_PLAYER_PRESENCE_SERVER_URL", env("DUNE_PUBLIC_SITE_URL", ""))),
    }
    context.update(extra)
    return template.format(**context)


def render_journey_template(template, player_name, story_node_id):
    return template.format(playername=player_name, player_name=player_name, story_node_id=story_node_id)


def active_restart_targets():
    now = time.time()
    targets = []
    for path in (RESTART_STATE_FILE, ANNOUNCEMENT_STATE_FILE):
        for job in load_json_file(path, {"jobs": []}).get("jobs", []):
            status = job.get("status")
            run_at = float(job.get("runAt") or job.get("restartAt") or 0)
            if status in ("scheduled", "delivering") and run_at > now:
                targets.append({"id": job.get("id"), "runAt": run_at, "message": job.get("message", ""), "source": path.name})
    return targets


def recently_executed_restarts(window_seconds):
    now = time.time()
    jobs = []
    for job in load_json_file(RESTART_STATE_FILE, {"jobs": []}).get("jobs", []):
        executed_at = float(job.get("executedAt") or 0)
        if job.get("status") == "executed" and executed_at and now - executed_at <= window_seconds:
            jobs.append({"id": job.get("id"), "executedAt": executed_at, "target": job.get("targetLabel") or job.get("target") or "server"})
    return jobs


def send_private(player, template, count, event, account_id, extra=None):
    extra = extra or {}
    message = render_template(template, player_name(player), count, **extra)
    return {"event": event, "accountId": account_id, "message": message, "send": private_message(player, message, f"player-presence-{event}")}


def send_admin_private(current, template, count, event, extra=None):
    results = []
    for account_id, player in admin_players(current).items():
        results.append(send_private(player, template, count, event, account_id, extra))
    return results


def admin_anomaly_digest_template(stuck_count, stuck_names, over_base_cap):
    parts = []
    if stuck_count:
        parts.append(f"stuck/recent anomalies={stuck_count} ({stuck_names})")
    if over_base_cap:
        parts.append(f"over base cap={over_base_cap}")
    if not parts:
        return ""
    return "Admin digest: " + "; ".join(parts) + "."


def admin_anomaly_digest_signature(stuck, over_base_cap):
    stuck_ids = sorted(str(item.get("accountId") or item.get("name") or "") for item in stuck if item.get("accountId") or item.get("name"))
    return json.dumps({"stuck": stuck_ids, "overBaseCap": int(over_base_cap or 0)}, sort_keys=True)


def compact_map_counts(players_by_map, limit=6):
    items = [(name, int(count or 0)) for name, count in (players_by_map or {}).items() if int(count or 0) > 0]
    items.sort(key=lambda item: (-item[1], item[0].lower()))
    if not items:
        return "no reported map population"
    shown = [f"{name}: {count}" for name, count in items[:limit]]
    if len(items) > limit:
        shown.append(f"+{len(items) - limit} more")
    return ", ".join(shown)


def record_digest(state, event, audience, message, payload=None):
    entry = {
        "ts": now_iso(),
        "event": event,
        "audience": audience,
        "message": message,
        "payload": payload or {},
    }
    log = state.setdefault("adminDigestLog", [])
    log.append(entry)
    del log[:-int(env("DUNE_PLAYER_PRESENCE_DIGEST_LOG_LIMIT", "250"))]
    return entry


def send_admin_digest(current, state, template, count, event, extra=None):
    extra = extra or {}
    message = render_template(template, "admin", count, **extra)
    record_digest(state, event, "admin", message, extra)
    results = []
    for account_id, player in admin_players(current).items():
        results.append({"event": event, "accountId": account_id, "message": message, "send": private_message(player, message, f"player-presence-{event}")})
    return results


def check_once():
    state = load_state()
    current = online_players()
    previous = state.get("onlinePlayers")
    current_ids = set(current)
    previous_ids = set(previous or {})
    first_run = previous is None
    joined = sorted(current_ids - previous_ids, key=lambda account_id: player_name(current.get(account_id, account_id)).lower())
    left = sorted(previous_ids - current_ids, key=lambda account_id: player_name(previous.get(account_id, account_id)).lower()) if previous else []
    final_count = len(current)
    current_time = now_ts()
    seen_accounts = set(str(item) for item in state.get("seenAccounts", []))

    results = []
    if env_bool("DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED", False) and not first_run:
        join_template = env("DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE", "Welcome {playername}! Current player count is now {count}.")
        return_join_template = env(
            "DUNE_PLAYER_PRESENCE_RETURN_JOIN_TEMPLATE",
            env("DUNE_PLAYER_PRESENCE_WELCOME_BACK_TEMPLATE", "Welcome back {playername}! Current player count is now {count}."),
        )
        leave_template = env("DUNE_PLAYER_PRESENCE_LEAVE_TEMPLATE", "{playername} has left, current count is {count}.")
        for account_id in joined:
            event = "join-returning" if str(account_id) in seen_accounts else "join-first-time"
            template = return_join_template if str(account_id) in seen_accounts else join_template
            message = render_template(template, player_name(current.get(account_id, account_id)), final_count)
            results.append({"event": event, "accountId": account_id, "message": message, "announce": announce(message)})
        for account_id in left:
            message = render_template(leave_template, player_name(previous.get(account_id, account_id)), final_count)
            results.append({"event": "leave", "accountId": account_id, "message": message, "announce": announce(message)})

    private_welcome_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_ENABLED", False) and not first_run:
        template = env("DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_TEMPLATE", "Welcome! Please Check https://snape.tech for Server Rules.")
        for account_id in joined:
            player = current.get(account_id, account_id)
            message = render_template(template, player_name(player), final_count)
            private_welcome_results.append({"event": "private-welcome", "accountId": account_id, "message": message, "send": private_join_message(player, message)})

    automated_private_results = []
    if not first_run:
        hagga_arrivals = set(str(item) for item in state.get("haggaArrivalMessaged", []))
        recent_leaves = state.setdefault("recentLeaves", {})

        if env_bool("DUNE_PLAYER_PRESENCE_FIRST_SEEN_ENABLED", False):
            template = env("DUNE_PLAYER_PRESENCE_FIRST_SEEN_TEMPLATE", "Welcome to {server_name}. This is a friendly PvE server. Please keep shared paths, spawns, and resources clear. Rules: {rules_url}")
            for account_id in joined:
                if str(account_id) not in seen_accounts:
                    automated_private_results.append(send_private(current[account_id], template, final_count, "first-seen", account_id))
                    seen_accounts.add(str(account_id))
        seen_accounts.update(str(account_id) for account_id in joined)

        join_counts = state.setdefault("joinCounts", {})
        repo_star_messaged = set(str(item) for item in state.get("repoStarMessaged", []))
        for account_id in joined:
            key = str(account_id)
            join_counts[key] = int(join_counts.get(key, 0) or 0) + 1
        if env_bool("DUNE_PLAYER_PRESENCE_REPO_STAR_THIRD_JOIN_ENABLED", True):
            threshold = int(env("DUNE_PLAYER_PRESENCE_REPO_STAR_JOIN_COUNT", "3"))
            template = env("DUNE_PLAYER_PRESENCE_REPO_STAR_TEMPLATE", "Glad to have you back on {server_name}. If this server and self-host stack have been useful, please consider starring the project: https://github.com/snapetech/DuneAwakeningSelfHost")
            for account_id in joined:
                key = str(account_id)
                if key not in repo_star_messaged and int(join_counts.get(key, 0) or 0) >= threshold:
                    automated_private_results.append(send_private(current[account_id], template, final_count, "repo-star-third-join", account_id, {"join_count": join_counts[key]}))
                    repo_star_messaged.add(key)
        state["repoStarMessaged"] = sorted(repo_star_messaged, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))

        if env_bool("DUNE_PLAYER_PRESENCE_HAGGA_ARRIVAL_ENABLED", False):
            template = env("DUNE_PLAYER_PRESENCE_HAGGA_ARRIVAL_TEMPLATE", "You made it to Hagga Basin. Build with room around roads, spawns, resource areas, and points of interest. Rules: {rules_url}")
            for account_id, player in current.items():
                if str(account_id) not in hagga_arrivals and player_map(player) == "HaggaBasin":
                    automated_private_results.append(send_private(player, template, final_count, "hagga-arrival", account_id))
                    hagga_arrivals.add(str(account_id))

        if env_bool("DUNE_PLAYER_PRESENCE_DEEP_DESERT_FIRST_ENABLED", False):
            deep_desert_seen = set(str(item) for item in state.get("deepDesertMessaged", []))
            template = env("DUNE_PLAYER_PRESENCE_DEEP_DESERT_FIRST_TEMPLATE", "Deep Desert is high risk. Expect sandstorms, sandworms, and harsher recovery. Support: {server_url}")
            for account_id, player in current.items():
                if str(account_id) not in deep_desert_seen and "DeepDesert" in player_map(player):
                    automated_private_results.append(send_private(player, template, final_count, "deep-desert-first", account_id))
                    deep_desert_seen.add(str(account_id))
            state["deepDesertMessaged"] = sorted(deep_desert_seen, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))

        if env_bool("DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_ENABLED", False):
            window = int(env("DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_WINDOW_SECONDS", "600"))
            template = env("DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_TEMPLATE", "Welcome back. If you were disconnected during travel, wait a moment before retrying the same transition.")
            for account_id in joined:
                left_at = int(recent_leaves.get(str(account_id), 0) or 0)
                if left_at and current_time - left_at <= window:
                    automated_private_results.append(send_private(current[account_id], template, final_count, "reconnect-recovery", account_id))

        if env_bool("DUNE_PLAYER_PRESENCE_BASE_REMINDERS_ENABLED", False):
            base_counts = base_claim_counts()
            cap = configured_base_cap()
            near_cap = int(env("DUNE_PLAYER_PRESENCE_BASE_NEAR_CAP", str(max(1, cap - 1))))
            notices = state.setdefault("baseClaimNotices", {})
            near_template = env("DUNE_PLAYER_PRESENCE_BASE_NEAR_CAP_TEMPLATE", "Base reminder: this server has a {base_cap} landclaim cap per Hagga Basin map. Please clean up unused claims. Rules: {rules_url}")
            over_template = env("DUNE_PLAYER_PRESENCE_BASE_OVER_CAP_TEMPLATE", "Heads up: you appear to be over the {base_cap} landclaim cap. Please clean up unused claims. Rules: {rules_url}")
            first_template = env("DUNE_PLAYER_PRESENCE_FIRST_BASE_TEMPLATE", "Base reminder: please avoid blocking shared paths, NPCs, resources, caves, wrecks, and POIs. Rules: {rules_url}")
            for account_id in joined:
                counts = base_counts.get(str(account_id), {"baseCount": 0, "segmentCount": 0})
                base_count = counts["baseCount"]
                last_notice = notices.get(str(account_id), {})
                if base_count <= 0:
                    continue
                if not last_notice.get("firstBase"):
                    automated_private_results.append(send_private(current[account_id], first_template, final_count, "first-base", account_id, {"base_cap": cap}))
                    last_notice["firstBase"] = True
                if base_count > cap and last_notice.get("overBaseCount") != base_count:
                    automated_private_results.append(send_private(current[account_id], over_template, final_count, "base-over-cap", account_id, {"base_cap": cap}))
                    last_notice["overBaseCount"] = base_count
                elif base_count >= near_cap and last_notice.get("nearBaseCount") != base_count:
                    automated_private_results.append(send_private(current[account_id], near_template, final_count, "base-near-cap", account_id, {"base_cap": cap}))
                    last_notice["nearBaseCount"] = base_count
                notices[str(account_id)] = last_notice

        if env_bool("DUNE_PLAYER_PRESENCE_STUCK_POSITION_ENABLED", False):
            template = env("DUNE_PLAYER_PRESENCE_STUCK_POSITION_TEMPLATE", "Your position looks unusual. If you are stuck, message an admin before relogging repeatedly.")
            stuck_state = state.setdefault("stuckPositionNotices", {})
            for account_id, player in current.items():
                location_known = bool(player_map(player) and player.get("x") and player.get("y")) if isinstance(player, dict) else False
                if not location_known and stuck_state.get(str(account_id)) != now_iso()[:10]:
                    automated_private_results.append(send_private(player, template, final_count, "stuck-position", account_id))
                    stuck_state[str(account_id)] = now_iso()[:10]

        state["seenAccounts"] = sorted(seen_accounts, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))
        state["haggaArrivalMessaged"] = sorted(hagga_arrivals, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))
        for account_id in left:
            recent_leaves[str(account_id)] = current_time
        for account_id, left_at in list(recent_leaves.items()):
            if current_time - int(left_at or 0) > 86400:
                recent_leaves.pop(account_id, None)

    starter_grant_results = []
    starter_message_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED", True) and not first_run:
        granted = state.setdefault("starterBaseToolGranted", [])
        granted_ids = set(str(account_id) for account_id in granted)
        message_enabled = env_bool("DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_MESSAGE_ENABLED", True)
        message_template = env("DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_MESSAGE_TEMPLATE", STARTER_BASE_TOOL_MESSAGE)
        for account_id in joined:
            if str(account_id) in granted_ids:
                continue
            result = grant_starter_base_tool(account_id)
            starter_grant_results.append({"event": "starter-base-tool", "accountId": account_id, "grant": result})
            if result.get("ok"):
                granted_ids.add(str(account_id))
                if message_enabled:
                    player = current.get(account_id, account_id)
                    message = render_template(message_template, player_name(player), final_count)
                    starter_message_results.append({
                        "event": "starter-base-tool-message",
                        "accountId": account_id,
                        "message": message,
                        "send": private_join_message(player, message),
                    })
        state["starterBaseToolGranted"] = sorted(granted_ids, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))

    journey_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_ENABLED", False):
        story_node_id = env("DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_NODE", "DA_SQ_VermiliusGap.Relocate.RelocateOutsideHBS.Drive north to the Vermilius Gap")
        completed = completed_journey_players(story_node_id)
        journey_state = state.setdefault("announcedJourneyNodes", {})
        previous_completed = set(journey_state.get(story_node_id, []))
        current_completed = set(completed)
        journey_first_run = story_node_id not in journey_state
        newly_completed = sorted(current_completed - previous_completed, key=lambda account_id: completed.get(account_id, account_id).lower())
        if not journey_first_run:
            template = env("DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_TEMPLATE", "Congrats! {playername} has outrun Shai-Hulud!")
            for account_id in newly_completed:
                message = render_journey_template(template, completed.get(account_id, account_id), story_node_id)
                journey_results.append({"event": "vermilius-gap", "accountId": account_id, "message": message, "announce": announce(message)})
        journey_state[story_node_id] = sorted(current_completed)

    restart_private_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_RESTART_PRIVATE_WARNINGS_ENABLED", False):
        marks = [int(item.strip()) for item in env("DUNE_PLAYER_PRESENCE_RESTART_PRIVATE_WARNING_MARKS_SECONDS", "1800,600,300,60").split(",") if item.strip()]
        sent = state.setdefault("restartPrivateWarnings", {})
        template = env("DUNE_PLAYER_PRESENCE_RESTART_PRIVATE_WARNING_TEMPLATE", "Server maintenance in about {remaining}. Please get to a safe place.")
        for job in active_restart_targets():
            remaining = max(0, int(job["runAt"] - time.time()))
            due_marks = [mark for mark in marks if remaining <= mark]
            if not due_marks:
                continue
            mark = min(due_marks)
            sent_key = f"{job['id']}:{mark}"
            sent_accounts = set(sent.get(sent_key, []))
            remaining_text = f"{max(1, round(remaining / 60))} minutes" if remaining >= 90 else f"{remaining} seconds"
            for account_id, player in current.items():
                if str(account_id) in sent_accounts:
                    continue
                message = render_template(template, player_name(player), final_count, remaining=remaining_text, remaining_seconds=remaining)
                restart_private_results.append({"event": "restart-private-warning", "accountId": account_id, "jobId": job["id"], "mark": mark, "message": message, "send": private_message(player, message, "player-presence-restart-warning")})
                sent_accounts.add(str(account_id))
            sent[sent_key] = sorted(sent_accounts)

    post_restart_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_POST_RESTART_RETURN_ENABLED", False) and joined:
        window = int(env("DUNE_PLAYER_PRESENCE_POST_RESTART_WINDOW_SECONDS", "3600"))
        sent = state.setdefault("postRestartReturnMessages", {})
        template = env("DUNE_PLAYER_PRESENCE_POST_RESTART_TEMPLATE", "Maintenance is complete. If anything looks wrong, report it through {server_url}.")
        for job in recently_executed_restarts(window):
            sent_accounts = set(sent.get(job["id"], []))
            for account_id in joined:
                if str(account_id) in sent_accounts:
                    continue
                player = current[account_id]
                post_restart_results.append(send_private(player, template, final_count, "post-restart-return", account_id))
                sent_accounts.add(str(account_id))
            sent[job["id"]] = sorted(sent_accounts)

    public_status_results = []
    admin_alert_results = []
    health = None
    if (
        env_bool("DUNE_PLAYER_PRESENCE_MAP_HEALTH_PUBLIC_ENABLED", False)
        or env_bool("DUNE_PLAYER_PRESENCE_MAP_HEALTH_ADMIN_ENABLED", False)
        or env_bool("DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_ENABLED", False)
        or env_bool("DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_ENABLED", False)
    ):
        health = map_health_summary()
        expected = int(health.get("expected") or 0)
        online = int(health.get("online") or 0)
        health_state = "healthy" if expected > 0 and online == expected else "degraded"
        previous_health_state = state.get("mapHealthState")
        state["mapHealthState"] = health_state

        if env_bool("DUNE_PLAYER_PRESENCE_MAP_HEALTH_PUBLIC_ENABLED", False) and previous_health_state and previous_health_state != health_state:
            if health_state == "degraded":
                template = env("DUNE_PLAYER_PRESENCE_MAP_HEALTH_DEGRADED_TEMPLATE", "Server notice: some travel destinations are recovering ({online}/{expected} online). If travel fails, wait 1-2 minutes and retry.")
            else:
                template = env("DUNE_PLAYER_PRESENCE_MAP_HEALTH_RECOVERED_TEMPLATE", "Server notice: all travel destinations are online again ({online}/{expected}).")
            message = render_template(template, "server", final_count, online=online, expected=expected)
            public_status_results.append({"event": f"map-health-{health_state}", "message": message, "announce": announce(message)})

        if env_bool("DUNE_PLAYER_PRESENCE_MAP_HEALTH_ADMIN_ENABLED", False) and health_state == "degraded":
            interval = int(env("DUNE_PLAYER_PRESENCE_ADMIN_ALERT_INTERVAL_SECONDS", "900"))
            last = int(state.get("lastAdminMapHealthAlertAt", 0) or 0)
            if current_time - last >= interval:
                offline = ", ".join((health.get("offlineLabels") or [])[:8]) or "unknown"
                template = env("DUNE_PLAYER_PRESENCE_MAP_HEALTH_ADMIN_TEMPLATE", "Admin alert: map health degraded, {online}/{expected} online. Offline: {offline_maps}")
                admin_alert_results.extend(send_admin_private(current, template, final_count, "admin-map-health", {"online": online, "expected": expected, "offline_maps": offline}))
                state["lastAdminMapHealthAlertAt"] = current_time

        if env_bool("DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_ENABLED", False):
            thresholds = sorted([int(item.strip()) for item in env("DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_THRESHOLDS", "30,35,40").split(",") if item.strip()])
            band = 0
            for threshold in thresholds:
                if final_count >= threshold:
                    band = threshold
            previous_band = int(state.get("populationPublicBand", 0) or 0)
            if band and band != previous_band:
                template = env("DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_TEMPLATE", "Server is getting busy: {count} online. Travel and loading may take longer.")
                message = render_template(template, "server", final_count)
                public_status_results.append({"event": "population-threshold", "threshold": band, "message": message, "announce": announce(message)})
            state["populationPublicBand"] = band

        if env_bool("DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_ENABLED", False):
            interval = int(env("DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_INTERVAL_SECONDS", "1800"))
            last = int(state.get("lastAdminPopulationDigestAt", 0) or 0)
            if current_time - last >= interval:
                map_counts = compact_map_counts(health.get("playersByMap") or {})
                template = env("DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_TEMPLATE", "Admin population: {count} online. Maps: {map_counts}")
                admin_alert_results.extend(send_admin_private(current, template, final_count, "admin-population-digest", {"map_counts": map_counts}))
                state["lastAdminPopulationDigestAt"] = current_time

    if env_bool("DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_ENABLED", False):
        window = int(env("DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_WINDOW_SECONDS", "600"))
        threshold = int(env("DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_THRESHOLD", "3"))
        reconnects = state.setdefault("reconnectSupportEvents", {})
        sent = state.setdefault("reconnectSupportSent", {})
        template = env("DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_TEMPLATE", "Looks like you have reconnected several times. If travel is stuck, report it through {server_url}.")
        for account_id in joined:
            events = [int(ts) for ts in reconnects.get(str(account_id), []) if current_time - int(ts) <= window]
            events.append(current_time)
            reconnects[str(account_id)] = events
            if len(events) >= threshold and current_time - int(sent.get(str(account_id), 0) or 0) >= window:
                player = current[account_id]
                automated_private_results.append(send_private(player, template, final_count, "reconnect-support", account_id))
                sent[str(account_id)] = current_time
        for account_id, events in list(reconnects.items()):
            remaining = [int(ts) for ts in events if current_time - int(ts) <= window]
            if remaining:
                reconnects[account_id] = remaining
            else:
                reconnects.pop(account_id, None)

    if env_bool("DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_ENABLED", False):
        interval = int(env("DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_INTERVAL_SECONDS", "1800"))
        last = int(state.get("lastAdminAnomalyDigestAt", 0) or 0)
        if current_time - last >= interval:
            try:
                stuck = stuck_transition_players(int(env("DUNE_ADMIN_BOT_STUCK_TRANSITION_MINUTES", "10")))
                base_counts = base_claim_counts()
                cap = configured_base_cap()
                over_cap = sum(1 for item in base_counts.values() if item.get("baseCount", 0) > cap)
                stuck_names = ", ".join(
                    f"{item['name']} {item.get('staleMinutes', '?')}m {item.get('map') or 'unknown-map'}"
                    for item in stuck[:5]
                ) or "none"
                template = env("DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_TEMPLATE", ADMIN_ANOMALY_DIGEST_TEMPLATE)
                if template == ADMIN_ANOMALY_DIGEST_TEMPLATE:
                    template = admin_anomaly_digest_template(len(stuck), stuck_names, over_cap)
                if template:
                    signature = admin_anomaly_digest_signature(stuck, over_cap)
                    repeat_unchanged = env_bool("DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_REPEAT_UNCHANGED", False)
                    if repeat_unchanged or signature != state.get("lastAdminAnomalyDigestSignature"):
                        admin_alert_results.extend(send_admin_private(current, template, final_count, "admin-anomaly-digest", {"stuck_count": len(stuck), "stuck_names": stuck_names, "over_base_cap": over_cap}))
                        state["lastAdminAnomalyDigestSignature"] = signature
                else:
                    state.pop("lastAdminAnomalyDigestSignature", None)
                state["lastAdminAnomalyDigestAt"] = current_time
            except Exception as exc:
                admin_alert_results.append({"event": "admin-anomaly-digest", "ok": False, "error": str(exc)})

    if env_bool("DUNE_PLAYER_PRESENCE_ADMIN_MAP_ROSTER_DIGEST_ENABLED", False):
        interval = int(env("DUNE_PLAYER_PRESENCE_ADMIN_MAP_ROSTER_DIGEST_INTERVAL_SECONDS", "1800"))
        last = int(state.get("lastAdminMapRosterDigestAt", 0) or 0)
        if current_time - last >= interval:
            roster = player_roster_by_map()
            roster_text = compact_roster_by_map(roster)
            template = env("DUNE_PLAYER_PRESENCE_ADMIN_MAP_ROSTER_DIGEST_TEMPLATE", "Admin roster: {count} online. {map_roster}")
            admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-map-roster-digest", {"map_roster": roster_text, "roster": roster}))
            state["lastAdminMapRosterDigestAt"] = current_time

    if env_bool("DUNE_PLAYER_PRESENCE_ADMIN_UNIQUE_DAILY_DIGEST_ENABLED", False):
        today = dt.datetime.now().strftime("%Y-%m-%d")
        daily = state.setdefault("dailyUniquePlayers", {})
        seen_today = set(daily.get(today, []))
        seen_today.update(current_ids)
        daily[today] = sorted(seen_today, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))
        for old_day in list(daily):
            if old_day != today:
                daily.pop(old_day, None)
        interval = int(env("DUNE_PLAYER_PRESENCE_ADMIN_UNIQUE_DAILY_DIGEST_INTERVAL_SECONDS", "86400"))
        last = int(state.get("lastAdminUniqueDailyDigestAt", 0) or 0)
        if current_time - last >= interval:
            template = env("DUNE_PLAYER_PRESENCE_ADMIN_UNIQUE_DAILY_DIGEST_TEMPLATE", "Admin daily players: {unique_count} unique accounts seen today, {count} currently online.")
            admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-unique-daily-digest", {"unique_count": len(seen_today)}))
            state["lastAdminUniqueDailyDigestAt"] = current_time

    if env_bool("DUNE_PLAYER_PRESENCE_MAINTENANCE_ONLINE_ADMIN_ENABLED", False):
        targets = active_restart_targets()
        if targets:
            window = int(env("DUNE_PLAYER_PRESENCE_MAINTENANCE_ONLINE_WINDOW_SECONDS", "1800"))
            for job in targets:
                remaining = int(job["runAt"] - time.time())
                key = f"{job['id']}:online"
                if 0 <= remaining <= window and key not in state.setdefault("maintenanceOnlineDigests", []):
                    roster = compact_roster_by_map(player_roster_by_map())
                    template = env("DUNE_PLAYER_PRESENCE_MAINTENANCE_ONLINE_ADMIN_TEMPLATE", "Admin maintenance check: {count} players still online before maintenance. {map_roster}")
                    admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-maintenance-online", {"map_roster": roster, "remaining_seconds": remaining}))
                    state["maintenanceOnlineDigests"].append(key)

    if env_bool("DUNE_PLAYER_PRESENCE_MAP_WITH_PLAYERS_UNHEALTHY_ADMIN_ENABLED", False):
        if health is None:
            health = map_health_summary()
        offline = set(health.get("offlineLabels") or [])
        players_by_map = health.get("playersByMap") or {}
        impacted = [f"{name}: {players_by_map.get(name)}" for name in offline if int(players_by_map.get(name) or 0) > 0]
        if impacted:
            digest_key = hashlib.sha256("|".join(sorted(impacted)).encode("utf-8")).hexdigest()
            if state.get("lastImpactedMapDigestKey") != digest_key:
                template = env("DUNE_PLAYER_PRESENCE_MAP_WITH_PLAYERS_UNHEALTHY_ADMIN_TEMPLATE", "Admin alert: unhealthy maps still report players: {impacted_maps}")
                admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-map-players-unhealthy", {"impacted_maps": "; ".join(impacted)}))
                state["lastImpactedMapDigestKey"] = digest_key

    if env_bool("DUNE_PLAYER_PRESENCE_PUBLIC_MAINTENANCE_CANCELLED_ENABLED", False):
        since = float(state.get("lastMaintenanceCancelScanAt", current_time - 3600) or 0)
        cancelled = cancelled_jobs_since(since)
        state["lastMaintenanceCancelScanAt"] = current_time
        if cancelled:
            template = env("DUNE_PLAYER_PRESENCE_PUBLIC_MAINTENANCE_CANCELLED_TEMPLATE", "Maintenance has been cancelled or delayed. Normal play can continue.")
            message = render_template(template, "server", final_count)
            record_digest(state, "maintenance-cancelled-public", "public", message, {"cancelled": cancelled[:5]})
            public_status_results.append({"event": "maintenance-cancelled", "message": message, "announce": announce(message)})

    if env_bool("DUNE_PLAYER_PRESENCE_INCIDENT_MODE_PUBLIC_ENABLED", False):
        incident_on = env_bool("DUNE_PLAYER_PRESENCE_INCIDENT_MODE_ACTIVE", False)
        previous = state.get("incidentModeActive")
        state["incidentModeActive"] = incident_on
        if previous is not None and previous != incident_on:
            if incident_on:
                template = env("DUNE_PLAYER_PRESENCE_INCIDENT_MODE_ON_TEMPLATE", "Server notice: admins are investigating travel instability. Updates at {server_url}.")
                event = "incident-mode-on"
            else:
                template = env("DUNE_PLAYER_PRESENCE_INCIDENT_MODE_OFF_TEMPLATE", "Server notice: incident mode is cleared. Normal play can continue.")
                event = "incident-mode-off"
            message = render_template(template, "server", final_count)
            record_digest(state, event, "public", message)
            public_status_results.append({"event": event, "message": message, "announce": announce(message)})

    if env_bool("DUNE_PLAYER_PRESENCE_INFRA_ADMIN_ALERTS_ENABLED", False):
        interval = int(env("DUNE_PLAYER_PRESENCE_ADMIN_ALERT_INTERVAL_SECONDS", "900"))
        last = int(state.get("lastAdminInfraAlertAt", 0) or 0)
        if current_time - last >= interval:
            checks = service_health_checks()
            failed = [item for item in checks if not item.get("ok")]
            backup = latest_backup_age_hours()
            max_backup_age = float(env("DUNE_PLAYER_PRESENCE_BACKUP_MAX_AGE_HOURS", "24"))
            if backup is None:
                failed.append({"name": "backup", "status": "no backup found"})
            elif backup["ageHours"] > max_backup_age:
                failed.append({"name": "backup", "status": f"{backup['ageHours']}h old"})
            if failed:
                summary = "; ".join(f"{item['name']} {item.get('status', '')}".strip() for item in failed[:6])
                template = env("DUNE_PLAYER_PRESENCE_INFRA_ADMIN_ALERT_TEMPLATE", "Admin alert: infrastructure check failed: {infra_failures}")
                admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-infra-alert", {"infra_failures": summary}))
                state["lastAdminInfraAlertAt"] = current_time

    if env_bool("DUNE_PLAYER_PRESENCE_RESTART_FAILURE_ADMIN_ENABLED", False):
        since = float(state.get("lastRestartFailureScanAt", current_time - 3600) or 0)
        failed_jobs = failed_restart_jobs_since(since)
        state["lastRestartFailureScanAt"] = current_time
        if failed_jobs:
            summary = "; ".join(f"{job['target']} {job['id']}: {job['error']}" for job in failed_jobs[:3])
            template = env("DUNE_PLAYER_PRESENCE_RESTART_FAILURE_ADMIN_TEMPLATE", "Admin alert: restart job failed: {restart_failures}")
            admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-restart-failure", {"restart_failures": summary, "jobs": failed_jobs[:3]}))

    if env_bool("DUNE_PLAYER_PRESENCE_ADMIN_MUTATION_DIGEST_ENABLED", False):
        interval = int(env("DUNE_PLAYER_PRESENCE_ADMIN_MUTATION_DIGEST_INTERVAL_SECONDS", "1800"))
        last = int(state.get("lastAdminMutationDigestAt", 0) or 0)
        if current_time - last >= interval:
            audit = audit_counts_since(int(state.get("adminMutationAuditOffset", 0) or 0))
            state["adminMutationAuditOffset"] = audit["offset"]
            if audit["mutations"]:
                top = sorted(audit["counts"].items(), key=lambda item: (-item[1], item[0]))[:6]
                summary = ", ".join(f"{name}={count}" for name, count in top)
                template = env("DUNE_PLAYER_PRESENCE_ADMIN_MUTATION_DIGEST_TEMPLATE", "Admin write digest: {mutation_count} write-ish events. {mutation_summary}")
                admin_alert_results.extend(send_admin_digest(current, state, template, final_count, "admin-mutation-digest", {"mutation_count": audit["mutations"], "mutation_summary": summary}))
            state["lastAdminMutationDigestAt"] = current_time

    if env_bool("DUNE_PLAYER_PRESENCE_TRANSFER_POLICY_PUBLIC_ENABLED", False):
        transfer_hash = file_hash(["config/director.ini"])
        previous_hash = state.get("transferPolicyHash")
        state["transferPolicyHash"] = transfer_hash
        if previous_hash and transfer_hash and transfer_hash != previous_hash:
            template = env("DUNE_PLAYER_PRESENCE_TRANSFER_POLICY_PUBLIC_TEMPLATE", "Server notice: character transfer policy changed. Changes may apply after the next Director restart. Details: {server_url}")
            message = render_template(template, "server", final_count)
            record_digest(state, "transfer-policy-changed", "public", message)
            public_status_results.append({"event": "transfer-policy-changed", "message": message, "announce": announce(message)})

    if env_bool("DUNE_PLAYER_PRESENCE_RULES_CHANGE_PUBLIC_ENABLED", False):
        rule_paths = [item.strip() for item in env("DUNE_PLAYER_PRESENCE_RULES_HASH_FILES", "public-site/static/index.html").split(",") if item.strip()]
        rules_hash = file_hash(rule_paths)
        previous_hash = state.get("rulesHash")
        state["rulesHash"] = rules_hash
        if previous_hash and rules_hash and rules_hash != previous_hash:
            template = env("DUNE_PLAYER_PRESENCE_RULES_CHANGE_PUBLIC_TEMPLATE", "Server rules were updated. Please review {rules_url}.")
            message = render_template(template, "server", final_count)
            record_digest(state, "rules-changed", "public", message, {"files": rule_paths})
            public_status_results.append({"event": "rules-changed", "message": message, "announce": announce(message)})

    if env_bool("DUNE_PLAYER_PRESENCE_PEAK_PUBLIC_ENABLED", False):
        thresholds = sorted([int(item.strip()) for item in env("DUNE_PLAYER_PRESENCE_PEAK_PUBLIC_THRESHOLDS", "10,20,30,40").split(",") if item.strip()])
        today = dt.datetime.now().strftime("%Y-%m-%d")
        peak_state = state.setdefault("dailyPeak", {"date": today, "peak": 0, "announced": []})
        if peak_state.get("date") != today:
            peak_state = {"date": today, "peak": 0, "announced": []}
        if final_count > int(peak_state.get("peak", 0) or 0):
            peak_state["peak"] = final_count
        announced = set(int(item) for item in peak_state.get("announced", []))
        for threshold in thresholds:
            if final_count >= threshold and threshold not in announced:
                template = env("DUNE_PLAYER_PRESENCE_PEAK_PUBLIC_TEMPLATE", "New daily player peak: {count} online.")
                message = render_template(template, "server", final_count)
                record_digest(state, "daily-peak-public", "public", message, {"threshold": threshold})
                public_status_results.append({"event": "daily-peak", "threshold": threshold, "message": message, "announce": announce(message)})
                announced.add(threshold)
        peak_state["announced"] = sorted(announced)
        state["dailyPeak"] = peak_state

    if env_bool("DUNE_PLAYER_PRESENCE_DAILY_STATUS_PUBLIC_ENABLED", False):
        interval = int(env("DUNE_PLAYER_PRESENCE_DAILY_STATUS_INTERVAL_SECONDS", "86400"))
        last = int(state.get("lastDailyStatusAt", 0) or 0)
        if current_time - last >= interval:
            if health is None:
                health = map_health_summary()
            online = int(health.get("online") or 0)
            expected = int(health.get("expected") or 0)
            template = env("DUNE_PLAYER_PRESENCE_DAILY_STATUS_PUBLIC_TEMPLATE", "Daily status: {online}/{expected} maps online, {count} players online. Next maintenance is the normal configured window.")
            message = render_template(template, "server", final_count, online=online, expected=expected)
            record_digest(state, "daily-status-public", "public", message, {"online": online, "expected": expected})
            public_status_results.append({"event": "daily-status", "message": message, "announce": announce(message)})
            state["lastDailyStatusAt"] = current_time

    if env_bool("DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED", True) and joined:
        today = dt.datetime.now().strftime("%Y-%m-%d")
        sent = state.setdefault("adminDailyLoginDigestSent", {})
        digest_log = state.get("adminDigestLog", [])
        latest_messages = []
        for entry in reversed(digest_log):
            if entry.get("audience") == "admin" and entry.get("message") not in latest_messages:
                latest_messages.append(entry.get("message"))
            if len(latest_messages) >= int(env("DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DIGEST_LIMIT", "8")):
                break
        if not latest_messages:
            latest_messages = ["No admin digests have been recorded yet today."]
        for account_id in joined:
            player = current.get(account_id)
            if account_id in admin_players(current) and sent.get(str(account_id)) != today:
                message = "Admin daily digest:\n" + "\n".join(f"- {item}" for item in reversed(latest_messages))
                admin_alert_results.append({"event": "admin-first-login-daily", "accountId": account_id, "message": message, "send": private_message(player, message, "player-presence-admin-daily-login")})
                record_digest(state, "admin-first-login-daily", "admin", message, {"accountId": account_id})
                sent[str(account_id)] = today

    state["onlinePlayers"] = current
    state["updatedAt"] = now_iso()
    save_state(state)
    return {
        "ok": True,
        "firstRun": first_run,
        "onlineCount": final_count,
        "joined": [player_name(current[account_id]) for account_id in joined],
        "left": [player_name(previous[account_id]) for account_id in left] if previous else [],
        "announcements": results,
        "privateWelcomeMessages": private_welcome_results,
        "automatedPrivateMessages": automated_private_results,
        "starterBaseToolGrants": starter_grant_results,
        "starterBaseToolMessages": starter_message_results,
        "journeyAnnouncements": journey_results,
        "restartPrivateWarnings": restart_private_results,
        "postRestartReturnMessages": post_restart_results,
        "publicStatusAnnouncements": public_status_results,
        "adminAlertMessages": admin_alert_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Announce Dune player join/leave events through the configured Paul/DASH Admin chat path.")
    parser.add_argument("--once", action="store_true", help="Run one poll and exit.")
    parser.add_argument("--loop", action="store_true", help="Poll forever.")
    args = parser.parse_args()
    if not args.once and not args.loop:
        args.once = True
    while True:
        try:
            print(json.dumps(check_once(), indent=2), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc), "ts": now_iso()}), flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(int(env("DUNE_PLAYER_PRESENCE_POLL_SECONDS", "15")))


if __name__ == "__main__":
    sys.exit(main())
