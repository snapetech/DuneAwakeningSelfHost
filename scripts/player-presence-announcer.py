#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "backups" / "admin-bot"
STATE_FILE = STATE_DIR / "player-presence.json"
DB = "dune_sb_1_4_0_0"
STARTER_BASE_TOOL_TEMPLATE = "BaseBackupTool"
STARTER_BASE_TOOL_MESSAGE = "A Base Reconstruction Tool has been added to your inventory. You may need to log out and back in before it appears."
RESTART_STATE_FILE = ROOT / "backups" / "admin-panel" / "restart-jobs.json"
ANNOUNCEMENT_STATE_FILE = ROOT / "backups" / "admin-panel" / "announcements.json"


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
    result = subprocess.run([command, message], cwd=ROOT, env=child_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def private_message(player, message, job_id="player-presence-private-message"):
    fls_id = player_fls_id(player)
    name = player_name(player)
    if not fls_id:
        return {"ok": False, "error": "missing player FLS id", "player": name}
    command = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_COMMAND", env("DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh"))))
    if command.startswith("/workspace/"):
        command = str(ROOT / command.removeprefix("/workspace/"))
    timeout = int(env("DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS", env("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45")))
    child_env = os.environ.copy()
    child_env.update(FILE_ENV)
    child_env["DUNE_ANNOUNCE_MESSAGE"] = message
    child_env["DUNE_ANNOUNCE_JOB_ID"] = job_id
    child_env["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"] = "false"
    child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL", "Private")
    child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = name
    child_env["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"] = f"{fls_id}_queue"
    child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = f"dash.{job_id}.{fls_id}"
    result = subprocess.run([command, message], cwd=ROOT, env=child_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "targetQueue": f"{fls_id}_queue",
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

    results = []
    if env_bool("DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED", False) and not first_run:
        join_template = env("DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE", "Welcome {playername}! Current player count is now {count}.")
        leave_template = env("DUNE_PLAYER_PRESENCE_LEAVE_TEMPLATE", "{playername} has left, current count is {count}.")
        for account_id in joined:
            message = render_template(join_template, player_name(current.get(account_id, account_id)), final_count)
            results.append({"event": "join", "accountId": account_id, "message": message, "announce": announce(message)})
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
        seen_accounts = set(str(item) for item in state.get("seenAccounts", []))
        hagga_arrivals = set(str(item) for item in state.get("haggaArrivalMessaged", []))
        recent_leaves = state.setdefault("recentLeaves", {})

        if env_bool("DUNE_PLAYER_PRESENCE_FIRST_SEEN_ENABLED", False):
            template = env("DUNE_PLAYER_PRESENCE_FIRST_SEEN_TEMPLATE", "Welcome to {server_name}. This is a friendly PvE server. Please keep shared paths, spawns, and resources clear. Rules: {rules_url}")
            for account_id in joined:
                if str(account_id) not in seen_accounts:
                    automated_private_results.append(send_private(current[account_id], template, final_count, "first-seen", account_id))
                    seen_accounts.add(str(account_id))

        if env_bool("DUNE_PLAYER_PRESENCE_HAGGA_ARRIVAL_ENABLED", False):
            template = env("DUNE_PLAYER_PRESENCE_HAGGA_ARRIVAL_TEMPLATE", "You made it to Hagga Basin. Build with room around roads, spawns, resource areas, and points of interest. Rules: {rules_url}")
            for account_id, player in current.items():
                if str(account_id) not in hagga_arrivals and player_map(player) == "HaggaBasin":
                    automated_private_results.append(send_private(player, template, final_count, "hagga-arrival", account_id))
                    hagga_arrivals.add(str(account_id))

        if env_bool("DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_ENABLED", False):
            window = int(env("DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_WINDOW_SECONDS", "600"))
            template = env("DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_TEMPLATE", "Welcome back. If you were disconnected during travel, wait a moment before retrying the same transition.")
            for account_id in joined:
                left_at = int(recent_leaves.get(str(account_id), 0) or 0)
                if left_at and current_time - left_at <= window:
                    automated_private_results.append(send_private(current[account_id], template, final_count, "reconnect-recovery", account_id))

        if env_bool("DUNE_PLAYER_PRESENCE_BASE_REMINDERS_ENABLED", False):
            base_counts = base_claim_counts()
            cap = int(env("DUNE_PLAYER_PRESENCE_BASE_CAP", env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6")))
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
