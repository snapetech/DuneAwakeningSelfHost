#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import pathlib
import socket
import subprocess
import sys
import uuid


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DB = "dune_sb_1_4_0_0"
MAP = "CB_Overland_S_06"
MAP_FEATURE = "GroundVehicleTimeTrialIsland"
PARTITION_ID = 26
DEFAULT_ROUTE = f"{MAP}{PARTITION_ID}"
CAPTURE_ROOT = pathlib.Path(os.environ.get("DUNE_SMUGGLERS_RUN_CAPTURE_ROOT", ROOT / "captures" / "smugglers-run-mp"))


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def stamp():
    return utcnow().strftime("%Y%m%dT%H%M%SZ")


def read_env_file(path):
    values = {}
    try:
        for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


FILE_ENV = {}
for env_path in ("/workspace/.env", ROOT / ".env"):
    FILE_ENV.update(read_env_file(env_path))


def env(name, default=""):
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    return FILE_ENV.get(name, default)


def env_bool(name, default=False):
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def run(cmd, timeout=60, env=None):
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def compose_files(env_file):
    helper = ROOT / "scripts" / "compose-files.sh"
    result = run([str(helper), env_file], timeout=15)
    if result.returncode != 0:
        return os.environ.get("COMPOSE_FILES", "compose.yaml:compose.allmaps.yaml")
    return result.stdout.strip() or "compose.yaml:compose.allmaps.yaml"


def compose_cmd(env_file, *args):
    cmd = [os.environ.get("CONTAINER_RUNTIME", "docker"), "compose"]
    for item in compose_files(env_file).split(":"):
        if item:
            cmd.extend(["-f", item])
    cmd.extend(["--env-file", env_file])
    cmd.extend(args)
    return cmd


def psql_raw(env_file, sql, timeout=45):
    db = os.environ.get("DUNE_DB_NAME", DEFAULT_DB)
    return run(
        compose_cmd(
            env_file,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dune",
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ),
        timeout=timeout,
    )


def psql_json(env_file, sql, timeout=45):
    wrapped = "select coalesce(jsonb_agg(to_jsonb(q)), '[]'::jsonb) from (" + sql.rstrip().rstrip(";") + ") q;"
    result = psql_raw(env_file, wrapped, timeout=timeout)
    if result.returncode != 0:
        return {"ok": False, "sql": sql, "stdout": result.stdout, "stderr": result.stderr, "rows": []}
    text = result.stdout.strip() or "[]"
    try:
        rows = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "sql": sql, "stdout": result.stdout, "stderr": "psql output was not JSON", "rows": []}
    return {"ok": True, "sql": sql, "rows": rows}


def safe_name(value):
    out = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value.strip())
    return out.strip("-") or "race"


def session_path(session_id):
    return CAPTURE_ROOT / "sessions" / f"{safe_name(session_id)}.json"


def load_session(session_id):
    path = session_path(session_id)
    if not path.exists():
        raise SystemExit(f"session not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_session(session):
    path = session_path(session["sessionId"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def ensure_execute_allowed(scope):
    host = socket.gethostname()
    short = host.split(".", 1)[0]
    if scope == "production" and short != "kspls0":
        raise SystemExit(f"refusing production admin action on host {host}; connect to kspls0 first")
    if scope == "lab" and short == "kspls0":
        raise SystemExit("refusing lab-scoped admin action on kspls0")
    return host


def collect_snapshot(env_file, entrants):
    names = [item for item in entrants if item]
    player_filter = ""
    if names:
        quoted = ",".join("'" + item.replace("'", "''") + "'" for item in names)
        player_filter = f"and ps.character_name in ({quoted})"
    queries = {
        "partition": f"""
            select wp.partition_id, wp.server_id, wp.map, wp.dimension_index, wp.label,
                   coalesce(wp.blocked, false) as blocked,
                   fs.farm_id, fs.ready, fs.alive, fs.connected_players,
                   asi.server_id is not null as active
            from dune.world_partition wp
            left join dune.farm_state fs on fs.server_id = wp.server_id
            left join dune.active_server_ids asi on asi.server_id = wp.server_id
            where wp.partition_id = {PARTITION_ID} or wp.map = '{MAP}'
            order by wp.partition_id
        """,
        "players": f"""
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, wp.partition_id, wp.map as partition_map, wp.dimension_index,
                   ps.player_controller_id, ps.player_pawn_id, ps.last_login_time,
                   a.map as actor_map, a.partition_id as actor_partition_id,
                   a.dimension_index as actor_dimension_index,
                   ((a.transform).location).x::float8 as x,
                   ((a.transform).location).y::float8 as y,
                   ((a.transform).location).z::float8 as z
            from dune.player_state ps
            left join dune.actors a on a.id = ps.player_pawn_id
            left join dune.world_partition wp on wp.server_id = ps.server_id
            where true {player_filter}
            order by ps.character_name nulls last, ps.account_id
        """,
        "vehicleCounts": """
            select 'vehicles' as table_name, count(*)::bigint as count from dune.vehicles
            union all select 'vehicle_modules', count(*)::bigint from dune.vehicle_modules
            union all select 'backup_vehicles', count(*)::bigint from dune.backup_vehicles
            union all select 'recovered_vehicles', count(*)::bigint from dune.recovered_vehicles
        """,
        "vehicleFunctions": """
            select p.proname as name,
                   pg_get_function_identity_arguments(p.oid) as args,
                   pg_get_function_result(p.oid) as result
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'dune'
              and (p.proname ilike '%vehicle%' or p.proname ilike '%respawn%')
            order by p.proname
        """,
        "playerVehicles": f"""
            select ps.character_name, ps.account_id, ps.player_controller_id, v.*
            from dune.player_state ps
            cross join lateral dune.get_player_owned_vehicles_data(ps.player_controller_id, ps.account_id) v
            where true {player_filter}
            order by ps.character_name nulls last, v.out_actor_id
        """,
        "respawnLocations": f"""
            select ps.character_name, prl.id, prl.account_id, prl."group", prl.locator_name,
                   prl.map, prl.dimension, prl.last_used_timestamp
            from dune.player_state ps
            join dune.player_respawn_locations prl on prl.account_id = ps.account_id
            where true {player_filter}
            order by ps.character_name nulls last, prl.last_used_timestamp desc nulls last
        """,
    }
    snapshot = {"capturedAt": utcnow().isoformat(), "map": MAP, "mapFeature": MAP_FEATURE, "partitionId": PARTITION_ID}
    for name, sql in queries.items():
        snapshot[name] = psql_json(env_file, sql)
    return snapshot


def append_event(session, event_type, payload=None):
    session.setdefault("events", []).append({
        "type": event_type,
        "at": utcnow().isoformat(),
        "payload": payload or {},
    })


def add_snapshot(session, label, env_file):
    snap = collect_snapshot(env_file, session.get("entrants", []))
    session.setdefault("snapshots", {})[label] = snap
    append_event(session, "snapshot", {"label": label})


def maybe_announce(args, message):
    if not args.announce:
        return {"ok": True, "executed": False, "message": message}
    if not args.execute:
        return {"ok": True, "executed": False, "preview": True, "message": message}
    ensure_execute_allowed(args.scope)
    env = os.environ.copy()
    env["DUNE_ANNOUNCE_MESSAGE"] = message
    env.setdefault("DUNE_ANNOUNCE_CHAT_USE_SPOOF_NAME", "true")
    env.setdefault("DUNE_ANNOUNCE_CHAT_SPOOF_NAME", "Smugglers Run")
    result = run([str(ROOT / "scripts" / "announce.sh")], timeout=30, env=env)
    return {
        "ok": result.returncode == 0,
        "executed": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "message": message,
    }


def gm_preview(command_text, route, target_player, admin_player):
    sys.path.insert(0, str(ROOT / "scripts"))
    from dune_gm_command import build_envelope

    mode = env("DUNE_GM_COMMAND_ENVELOPE_MODE", "service-message")
    return {
        "route": route,
        "mode": mode,
        "commandText": command_text,
        "targetPlayer": target_player,
        "adminPlayer": admin_player,
        "envelope": build_envelope(mode, command_text, target_player=target_player, admin_player=admin_player),
    }


def gm_execute_allowed(args):
    return (
        args.execute
        and args.allow_unsafe_gm
        and env_bool("DUNE_ADMIN_GM_COMMANDS_ENABLED", False)
        and env_bool("DUNE_GM_COMMAND_PAYLOAD_VERIFIED", False)
    )


def publish_gm(command_text, route, target_player, admin_player, transport):
    sys.path.insert(0, str(ROOT / "scripts"))
    from dune_gm_command import publish_command, publish_command_management

    if transport == "management":
        return publish_command_management(command_text, route, target_player=target_player, admin_player=admin_player)
    return publish_command(command_text, route, target_player=target_player, admin_player=admin_player, app_id="SmugglersRunMP")


def count_map(snapshot):
    rows = (((snapshot or {}).get("vehicleCounts") or {}).get("rows") or [])
    return {row.get("table_name"): int(row.get("count") or 0) for row in rows}


def vehicle_rows_by_character(snapshot):
    rows = (((snapshot or {}).get("playerVehicles") or {}).get("rows") or [])
    grouped = {}
    for row in rows:
        key = row.get("character_name") or f"account:{row.get('account_id')}"
        grouped.setdefault(key, []).append(row)
    return grouped


def compare_snapshots(before, after):
    before_counts = count_map(before)
    after_counts = count_map(after)
    all_tables = sorted(set(before_counts) | set(after_counts))
    count_deltas = {
        table: {
            "before": before_counts.get(table, 0),
            "after": after_counts.get(table, 0),
            "delta": after_counts.get(table, 0) - before_counts.get(table, 0),
        }
        for table in all_tables
    }
    before_vehicles = vehicle_rows_by_character(before)
    after_vehicles = vehicle_rows_by_character(after)
    vehicle_changes = {}
    for character in sorted(set(before_vehicles) | set(after_vehicles)):
        before_serial = json.dumps(before_vehicles.get(character, []), sort_keys=True, default=str)
        after_serial = json.dumps(after_vehicles.get(character, []), sort_keys=True, default=str)
        vehicle_changes[character] = {
            "changed": before_serial != after_serial,
            "beforeRows": len(before_vehicles.get(character, [])),
            "afterRows": len(after_vehicles.get(character, [])),
        }
    warnings = []
    for table in ("backup_vehicles", "recovered_vehicles"):
        if count_deltas.get(table, {}).get("delta", 0) > 0:
            warnings.append(f"{table} increased by {count_deltas[table]['delta']}")
    for character, change in vehicle_changes.items():
        if change["changed"]:
            warnings.append(f"player vehicle rows changed for {character}")
    return {
        "countDeltas": count_deltas,
        "playerVehicleChanges": vehicle_changes,
        "warnings": warnings,
        "ownedVehicleSafetyPass": not warnings,
    }


def command_inspect(args):
    out = collect_snapshot(args.env_file, args.entrant)
    print(json.dumps(out, indent=2, sort_keys=True))


def command_init(args):
    session_id = args.session_id or f"smugglers-run-{stamp()}-{uuid.uuid4().hex[:6]}"
    session = {
        "sessionId": session_id,
        "createdAt": utcnow().isoformat(),
        "map": MAP,
        "mapFeature": MAP_FEATURE,
        "partitionId": PARTITION_ID,
        "vehicleMode": args.vehicle_mode,
        "scoringMode": "hybrid-native-and-external",
        "entrants": args.entrant,
        "events": [],
        "snapshots": {},
        "results": [],
        "notes": args.note,
    }
    add_snapshot(session, "pre_start", args.env_file)
    path = write_session(session)
    print(json.dumps({"ok": True, "sessionId": session_id, "path": str(path)}, indent=2))


def command_snapshot(args):
    session = load_session(args.session_id)
    add_snapshot(session, args.label, args.env_file)
    path = write_session(session)
    print(json.dumps({"ok": True, "sessionId": session["sessionId"], "label": args.label, "path": str(path)}, indent=2))


def command_start(args):
    session = load_session(args.session_id)
    if session.get("startedAt"):
        raise SystemExit(f"session already started at {session['startedAt']}")
    session["startedAt"] = utcnow().isoformat()
    append_event(session, "start", {"countdownSeconds": args.countdown_seconds})
    message = f"Smugglers Run race started: {session['sessionId']}"
    announce = maybe_announce(args, message)
    append_event(session, "announce", announce)
    path = write_session(session)
    print(json.dumps({"ok": True, "sessionId": session["sessionId"], "startedAt": session["startedAt"], "announce": announce, "path": str(path)}, indent=2))


def command_checkpoint(args):
    session = load_session(args.session_id)
    if not session.get("startedAt"):
        raise SystemExit("session has not started")
    payload = {"entrant": args.entrant, "checkpoint": args.checkpoint}
    append_event(session, "checkpoint", payload)
    path = write_session(session)
    print(json.dumps({"ok": True, "sessionId": session["sessionId"], "checkpoint": payload, "path": str(path)}, indent=2))


def elapsed_seconds(started_at, finished_at):
    start_time = dt.datetime.fromisoformat(started_at)
    finish_time = dt.datetime.fromisoformat(finished_at)
    return round((finish_time - start_time).total_seconds(), 3)


def command_finish(args):
    session = load_session(args.session_id)
    if not session.get("startedAt"):
        raise SystemExit("session has not started")
    finished_at = utcnow().isoformat()
    result = {
        "entrant": args.entrant,
        "finishedAt": finished_at,
        "elapsedSeconds": elapsed_seconds(session["startedAt"], finished_at),
        "status": args.status,
    }
    session.setdefault("results", []).append(result)
    append_event(session, "finish", result)
    message = f"Smugglers Run finish: {args.entrant} {result['elapsedSeconds']}s {args.status}"
    announce = maybe_announce(args, message)
    append_event(session, "announce", announce)
    path = write_session(session)
    print(json.dumps({"ok": True, "sessionId": session["sessionId"], "result": result, "announce": announce, "path": str(path)}, indent=2))


def command_summary(args):
    session = load_session(args.session_id)
    results = sorted(session.get("results", []), key=lambda row: (row.get("status") != "finished", row.get("elapsedSeconds", 10**12)))
    summary = {
        "ok": True,
        "sessionId": session["sessionId"],
        "map": session.get("map"),
        "entrants": session.get("entrants", []),
        "startedAt": session.get("startedAt"),
        "results": results,
        "winner": results[0] if results and results[0].get("status") == "finished" else None,
        "snapshotLabels": sorted((session.get("snapshots") or {}).keys()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def command_compare(args):
    session = load_session(args.session_id)
    snapshots = session.get("snapshots") or {}
    if args.before not in snapshots:
        raise SystemExit(f"snapshot label not found: {args.before}")
    if args.after not in snapshots:
        raise SystemExit(f"snapshot label not found: {args.after}")
    comparison = compare_snapshots(snapshots[args.before], snapshots[args.after])
    comparison.update({
        "ok": True,
        "sessionId": session["sessionId"],
        "before": args.before,
        "after": args.after,
    })
    print(json.dumps(comparison, indent=2, sort_keys=True))


def command_loaner(args):
    if args.execute:
        ensure_execute_allowed(args.scope)
    session = load_session(args.session_id) if args.session_id else None
    entrants = args.entrant or ((session or {}).get("entrants") or [])
    if not entrants:
        raise SystemExit("at least one --entrant is required when no session is supplied")
    route = args.route or DEFAULT_ROUTE
    command_text = " ".join(["SpawnVehicle", args.template] + args.extra_args)
    results = []
    for entrant in entrants:
        if gm_execute_allowed(args):
            result = publish_gm(command_text, route, entrant, args.admin_player, args.transport)
        else:
            result = {
                "ok": False,
                "blocked": True,
                "reason": "GM execution requires --execute, --allow-unsafe-gm, DUNE_ADMIN_GM_COMMANDS_ENABLED=true, and DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true",
                "preview": gm_preview(command_text, route, entrant, args.admin_player),
            }
        results.append(result)
    if session is not None:
        append_event(session, "loaner_vehicle", {
            "template": args.template,
            "route": route,
            "entrants": entrants,
            "executed": any(bool(row.get("ok")) for row in results),
            "results": results,
        })
        write_session(session)
    print(json.dumps({"ok": all(bool(row.get("ok")) for row in results), "results": results}, indent=2, sort_keys=True))


def build_parser():
    parser = argparse.ArgumentParser(description="SmugglersRunMP lab validation and external race timer.")
    parser.add_argument("--env-file", default=".env")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Read-only map/player/vehicle snapshot.")
    inspect_p.add_argument("--entrant", action="append", default=[], help="Character name to include. Repeat for multiple racers.")
    inspect_p.set_defaults(func=command_inspect)

    init_p = sub.add_parser("init", help="Create a local race session and pre-start snapshot.")
    init_p.add_argument("--session-id")
    init_p.add_argument("--entrant", action="append", required=True, help="Character name. Repeat for multiple racers.")
    init_p.add_argument("--vehicle-mode", choices=("owned", "loaner", "both"), default="both")
    init_p.add_argument("--note", action="append", default=[])
    init_p.set_defaults(func=command_init)

    snap_p = sub.add_parser("snapshot", help="Append a DB snapshot to a session.")
    snap_p.add_argument("session_id")
    snap_p.add_argument("--label", default="snapshot")
    snap_p.set_defaults(func=command_snapshot)

    start_p = sub.add_parser("start", help="Start the external timer.")
    start_p.add_argument("session_id")
    start_p.add_argument("--countdown-seconds", type=int, default=0)
    start_p.add_argument("--announce", action="store_true", help="Preview or send a chat announcement.")
    start_p.add_argument("--execute", action="store_true", help="Actually publish announcements.")
    start_p.add_argument("--scope", choices=("lab", "production"), default="lab")
    start_p.set_defaults(func=command_start)

    checkpoint_p = sub.add_parser("checkpoint", help="Record a manual or externally observed checkpoint.")
    checkpoint_p.add_argument("session_id")
    checkpoint_p.add_argument("--entrant", required=True)
    checkpoint_p.add_argument("--checkpoint", required=True)
    checkpoint_p.set_defaults(func=command_checkpoint)

    finish_p = sub.add_parser("finish", help="Record a finish/DNF result.")
    finish_p.add_argument("session_id")
    finish_p.add_argument("--entrant", required=True)
    finish_p.add_argument("--status", choices=("finished", "dnf", "dq"), default="finished")
    finish_p.add_argument("--announce", action="store_true", help="Preview or send a chat announcement.")
    finish_p.add_argument("--execute", action="store_true", help="Actually publish announcements.")
    finish_p.add_argument("--scope", choices=("lab", "production"), default="lab")
    finish_p.set_defaults(func=command_finish)

    summary_p = sub.add_parser("summary", help="Print winner/order summary.")
    summary_p.add_argument("session_id")
    summary_p.set_defaults(func=command_summary)

    compare_p = sub.add_parser("compare", help="Compare two session snapshots for vehicle-safety regressions.")
    compare_p.add_argument("session_id")
    compare_p.add_argument("--before", default="pre_start")
    compare_p.add_argument("--after", required=True)
    compare_p.set_defaults(func=command_compare)

    loaner_p = sub.add_parser("loaner", help="Preview or publish GM SpawnVehicle commands for event loaners.")
    loaner_p.add_argument("--session-id")
    loaner_p.add_argument("--entrant", action="append", default=[], help="Character name. Defaults to session entrants.")
    loaner_p.add_argument("--template", required=True, help="SpawnVehicle template argument to use.")
    loaner_p.add_argument("--extra-args", nargs="*", default=[], help="Additional SpawnVehicle args after the template.")
    loaner_p.add_argument("--route", default="", help=f"GM route override. Default: {DEFAULT_ROUTE}")
    loaner_p.add_argument("--admin-player", default="DASH")
    loaner_p.add_argument("--transport", choices=("amqp", "management"), default=env("DUNE_GM_COMMAND_TRANSPORT", "amqp"))
    loaner_p.add_argument("--execute", action="store_true", help="Actually publish GM commands when all gates are enabled.")
    loaner_p.add_argument("--allow-unsafe-gm", action="store_true", help="Required with --execute for SpawnVehicle.")
    loaner_p.add_argument("--scope", choices=("lab", "production"), default="lab")
    loaner_p.set_defaults(func=command_loaner)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
