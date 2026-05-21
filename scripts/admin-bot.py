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


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "backups" / "admin-bot"
STATE_FILE = STATE_DIR / "state.json"
AUDIT_FILE = ROOT / "backups" / "admin-panel" / "audit.jsonl"
DB = "dune_sb_1_4_0_0"


def env(name, default=""):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def configured_base_cap():
    config_path = ROOT / env("DUNE_ADMIN_BOT_BASE_CAP_CONFIG", "config/UserGame.ini")
    target_map = env("DUNE_ADMIN_BOT_BASE_CAP_MAP", "HaggaBasin")
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return int(env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6"))

    match = re.search(r"^m_MaxLandclaimSegmentsPerMap\s*=\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        return int(env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6"))

    entries = re.findall(r'Name="([^"]+)"\)\s*,\s*(\d+)', match.group(1))
    for map_name, cap in entries:
        if map_name == target_map:
            return int(cap)
    if entries:
        return int(entries[0][1])
    return int(env("DUNE_ADMIN_BOT_MAX_BASES_WARN", "6"))


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def iso(ts=None):
    return (ts or now_utc()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(cmd, timeout=60, check=False):
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")
    return result


def compose_cmd(*args):
    files = env("COMPOSE_FILES", "compose.yaml").split(":")
    cmd = [env("CONTAINER_RUNTIME", "docker"), "compose"]
    for file in files:
        if file:
            cmd.extend(["-f", file])
    cmd.extend(["--env-file", env("DUNE_ADMIN_BOT_ENV_FILE", ".env")])
    cmd.extend(args)
    return cmd


def psql(sql):
    cmd = compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-Atc", sql)
    result = run(cmd, timeout=int(env("DUNE_ADMIN_BOT_SQL_TIMEOUT_SECONDS", "15")))
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip(), "rows": []}
    rows = [line.split("|") for line in result.stdout.splitlines() if line.strip()]
    return {"ok": True, "rows": rows}


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def latest_backup():
    backups = []
    for path in (ROOT / "backups").glob("*"):
        if path.is_dir() and (path / "manifest.txt").exists():
            backups.append(path)
    for path in (ROOT / "backups" / "admin-panel").glob("*.dump"):
        if path.is_file() and not path.name.startswith("."):
            backups.append(path)
    for path in (ROOT / "backups" / "admin-panel" / "maintenance").glob("*"):
        if path.is_dir() and (path / "manifest.json").exists():
            backups.append(path / "manifest.json")
    return max(backups, key=lambda p: p.stat().st_mtime, default=None)


def check_backup_freshness():
    max_age_hours = float(env("DUNE_ADMIN_BOT_BACKUP_MAX_AGE_HOURS", "24"))
    latest = latest_backup()
    if not latest:
        return {"name": "backup-freshness", "ok": False, "reason": "no recognized backups found"}
    age_hours = (time.time() - latest.stat().st_mtime) / 3600
    return {
        "name": "backup-freshness",
        "ok": age_hours <= max_age_hours,
        "latest": str(latest.relative_to(ROOT)),
        "ageHours": round(age_hours, 2),
        "maxAgeHours": max_age_hours,
    }


def run_backup_if_stale():
    check = check_backup_freshness()
    if check.get("ok") or not env_bool("DUNE_ADMIN_BOT_BACKUP_STALE_RUN", False):
        return check
    result = run([str(ROOT / "scripts" / "backup-state.sh"), env("DUNE_ADMIN_BOT_ENV_FILE", ".env")], timeout=int(env("DUNE_ADMIN_BOT_BACKUP_TIMEOUT_SECONDS", "1800")))
    check["backupRun"] = {"ok": result.returncode == 0, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
    return check


def run_map_watchdog():
    if not env_bool("DUNE_ADMIN_BOT_MAP_WATCHDOG_ENABLED", True):
        return {"name": "map-watchdog", "ok": True, "skipped": True}
    mode = "--once" if env_bool("DUNE_ADMIN_BOT_MAP_WATCHDOG_RECOVER", False) else "--dry-run"
    result = run([str(ROOT / "scripts" / "watch-maps.sh"), env("DUNE_ADMIN_BOT_ENV_FILE", ".env"), mode], timeout=int(env("DUNE_ADMIN_BOT_WATCHDOG_TIMEOUT_SECONDS", "240")))
    return {"name": "map-watchdog", "ok": result.returncode == 0, "mode": mode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def stuck_transition_report():
    if not env_bool("DUNE_ADMIN_BOT_STUCK_TRANSITIONS_ENABLED", True):
        return {"name": "stuck-transitions", "ok": True, "skipped": True}
    minutes = int(env("DUNE_ADMIN_BOT_STUCK_TRANSITION_MINUTES", "10"))
    sql = f"""
    select ps.character_name, ps.online_status::text, ps.server_id, ps.last_avatar_activity
    from dune.player_state ps
    where ps.online_status::text <> 'Offline'
      and ps.last_avatar_activity < now() - interval '{minutes} minutes'
    order by ps.last_avatar_activity asc
    limit 25;
    """
    data = psql(sql)
    return {"name": "stuck-transitions", "ok": data["ok"], "thresholdMinutes": minutes, "rows": data.get("rows", []), "error": data.get("error")}


def economy_anomaly_report():
    if not env_bool("DUNE_ADMIN_BOT_ECONOMY_ANOMALIES_ENABLED", True):
        return {"name": "economy-anomalies", "ok": True, "skipped": True}
    threshold = int(env("DUNE_ADMIN_BOT_SOLARI_WARN_THRESHOLD", "10000000"))
    sql = f"""
    select ps.character_name, b.currency_id, b.balance
    from dune.player_virtual_currency_balances b
    join dune.player_state ps on ps.player_controller_id = b.player_controller_id
    where b.balance >= {threshold}
    order by b.balance desc
    limit 25;
    """
    data = psql(sql)
    return {"name": "economy-anomalies", "ok": data["ok"], "threshold": threshold, "rows": data.get("rows", []), "error": data.get("error")}


def base_claim_report():
    if not env_bool("DUNE_ADMIN_BOT_BASE_CLAIM_MONITOR_ENABLED", True):
        return {"name": "base-claim-monitor", "ok": True, "skipped": True}
    max_bases = configured_base_cap()
    sql = f"""
    select ps.character_name, count(distinct t.id) as base_count, count(ls.*) as segment_count
    from dune.totems t
    join dune.actors a on a.id = t.id
    join dune.player_state ps on ps.account_id = a.owner_account_id
    left join dune.landclaim_segments ls on ls.totem_id = t.id
    group by ps.character_name
    having count(distinct t.id) > {max_bases}
    order by base_count desc, segment_count desc
    limit 25;
    """
    data = psql(sql)
    return {"name": "base-claim-monitor", "ok": data["ok"], "maxBases": max_bases, "rows": data.get("rows", []), "error": data.get("error")}


def admin_audit_digest(state):
    if not env_bool("DUNE_ADMIN_BOT_AUDIT_DIGEST_ENABLED", True):
        return {"name": "audit-digest", "ok": True, "skipped": True}
    offset = int(state.get("auditOffset", 0))
    if not AUDIT_FILE.exists():
        return {"name": "audit-digest", "ok": True, "events": 0, "counts": {}}
    size = AUDIT_FILE.stat().st_size
    if offset > size:
        offset = 0
    counts = {}
    events = 0
    with AUDIT_FILE.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = event.get("event") or event.get("action") or "unknown"
            counts[name] = counts.get(name, 0) + 1
            events += 1
        state["auditOffset"] = handle.tell()
    return {"name": "audit-digest", "ok": True, "events": events, "counts": counts}


def config_hash(paths):
    digest = hashlib.sha256()
    for rel in paths:
        path = ROOT / rel
        if path.exists():
            digest.update(rel.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def config_drift_report(state):
    if not env_bool("DUNE_ADMIN_BOT_CONFIG_DRIFT_ENABLED", True):
        return {"name": "config-drift", "ok": True, "skipped": True}
    paths = [".env", "compose.yaml", "compose.allmaps.yaml", "config/UserGame.ini", "config/director.ini"]
    current = config_hash(paths)
    previous = state.get("configHash")
    state["configHash"] = current
    return {"name": "config-drift", "ok": True, "changed": bool(previous and previous != current), "hash": current, "tracked": paths}


def security_guard_report():
    if not env_bool("DUNE_ADMIN_BOT_SECURITY_GUARD_ENABLED", True):
        return {"name": "security-guard", "ok": True, "skipped": True}
    counts = {}
    if AUDIT_FILE.exists():
        for line in AUDIT_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = json.dumps(event).lower()
            if "token" in text or "origin" in text or "host" in text or "denied" in text:
                key = event.get("event") or "security-related"
                counts[key] = counts.get(key, 0) + 1
    return {"name": "security-guard", "ok": True, "recentCounts": counts}


def run_once():
    state = load_state()
    results = [
        run_backup_if_stale(),
        run_map_watchdog(),
        stuck_transition_report(),
        economy_anomaly_report(),
        base_claim_report(),
        admin_audit_digest(state),
        config_drift_report(state),
        security_guard_report(),
    ]
    save_state(state)
    return {"ok": all(item.get("ok", False) for item in results), "ts": iso(), "results": results}


def main():
    parser = argparse.ArgumentParser(description="Paul admin-bot read-only monitors and safe automation.")
    parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
    parser.add_argument("--loop", action="store_true", help="Run forever.")
    args = parser.parse_args()
    if not args.once and not args.loop:
        args.once = True
    while True:
        print(json.dumps(run_once(), indent=2), flush=True)
        if args.once:
            return
        time.sleep(int(env("DUNE_ADMIN_BOT_INTERVAL_SECONDS", "300")))


if __name__ == "__main__":
    main()
