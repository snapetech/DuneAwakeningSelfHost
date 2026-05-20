#!/usr/bin/env python3
import argparse
import collections
import json
import os
import pathlib
import re
import shlex
import ssl
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

import pika
import psycopg2
import psycopg2.extras

from dune_gm_command import build_envelope, publish_command, publish_command_management


ROOT = pathlib.Path(__file__).resolve().parents[1]
GM_LOCATION_FILE = ROOT / "backups" / "admin-panel" / "gm-locations.json"
SPAM_STATE = {}


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
    if name.startswith("DUNE_CHAT_COMMAND_") or name.startswith("DUNE_ANNOUNCE_"):
        value = FILE_ENV.get(name)
        if value is not None and value != "":
            return value
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    return FILE_ENV.get(name, default)


def env_bool(name, default=False):
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def env_chat_or_announce(chat_name, announce_name, default=""):
    value = FILE_ENV.get(chat_name)
    if value:
        return value
    value = FILE_ENV.get(announce_name)
    if value:
        return value
    value = os.environ.get(chat_name)
    if value and value != "dash-admin-test":
        return value
    return env(announce_name, default)


def split_csv(value):
    out = []
    for item in value.split(","):
        item = item.strip()
        if item:
            out.append(item)
    return out


def db_default_host():
    return "postgres" if pathlib.Path("/workspace/.env").exists() else "127.0.0.1"


def db_default_port():
    return "5432" if pathlib.Path("/workspace/.env").exists() else "15431"


def connect_db():
    db_host = env("DUNE_ADMIN_DB_HOST", db_default_host())
    db_port = env("DUNE_ADMIN_DB_PORT", db_default_port())
    if not pathlib.Path("/workspace/.env").exists() and db_host in ("postgres", "admin-postgres"):
        db_host = "127.0.0.1"
        db_port = "15431"
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        user=env("DUNE_ADMIN_DB_USER", "dune"),
        password=env("DUNE_ADMIN_DB_PASSWORD", env("POSTGRES_DUNE_PASSWORD", "")),
        dbname=env("DUNE_ADMIN_DB_NAME", "dune_sb_1_4_0_0"),
        connect_timeout=5,
    )


def character_row(conn, name):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            with candidate as (
                select
                    ps.account_id,
                    ps.character_name,
                    ps.online_status::text as online_status,
                    ps.life_state::text as life_state,
                    ps.server_id,
                    ps.player_controller_id,
                    ps.player_pawn_id,
                    acc.user as fls_id,
                    acc.funcom_id,
                    act.map as actor_map,
                    act.partition_id,
                    act.dimension_index,
                    wp.label as partition_label,
                    wp.map as partition_map,
                    ((act.transform).location).x::float8 as x,
                    ((act.transform).location).y::float8 as y,
                    ((act.transform).location).z::float8 as z,
                    case when lower(ps.character_name) = lower(%s) then 0 else 1 end as match_rank
                from dune.player_state ps
                join dune.accounts acc on acc.id = ps.account_id
                left join dune.actors act on act.id = ps.player_pawn_id
                left join dune.world_partition wp on wp.partition_id = act.partition_id
                where lower(ps.character_name) = lower(%s)
                   or lower(ps.character_name) like lower(%s) || '%%'
            )
            select *
            from candidate
            order by match_rank, character_name
            limit 5
            """,
            (name, name, name),
        )
        rows = cur.fetchall()
    if not rows:
        return None, []
    exact = [row for row in rows if row["character_name"].lower() == name.lower()]
    if exact:
        return exact[0], rows
    if len(rows) == 1:
        return rows[0], rows
    return None, rows


def character_by_fls_id(conn, fls_id):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select ps.character_name, acc.user as fls_id, acc.funcom_id
            from dune.accounts acc
            left join dune.player_state ps on ps.account_id = acc.id
            where acc.user = %s
            order by ps.character_name nulls last
            limit 1
            """,
            (fls_id,),
        )
        return cur.fetchone()


def resolve_sender_character(conn, sender_name, sender_fls_id):
    if sender_fls_id:
        resolved = character_by_fls_id(conn, sender_fls_id)
        if resolved and resolved.get("character_name"):
            return resolved["character_name"]
    if sender_name:
        resolved = character_by_fls_id(conn, sender_name)
        if resolved and resolved.get("character_name"):
            return resolved["character_name"]
    if sender_name:
        target, _ = character_row(conn, sender_name)
        if target:
            return target["character_name"]
    return sender_name or sender_fls_id or "unknown"


def is_admin(conn, sender_name, sender_fls_id):
    names = {item.lower() for item in split_csv(env("DUNE_CHAT_COMMAND_ADMINS", "Lukano"))}
    fls_ids = set(split_csv(env("DUNE_CHAT_COMMAND_ADMIN_FLS_IDS", "6FF6498F4074E3DE")))
    resolved = None
    if sender_fls_id:
        resolved = character_by_fls_id(conn, sender_fls_id)
    if not resolved and sender_name:
        resolved = character_by_fls_id(conn, sender_name)
    resolved_name = (resolved or {}).get("character_name") or sender_name or ""
    sender_ids = {item for item in (sender_fls_id, sender_name) if item}
    allowed = bool((resolved_name and resolved_name.lower() in names) or (sender_ids & fls_ids))
    return allowed, resolved_name


def compact_location(row):
    return {
        "partitionId": row["partition_id"],
        "partitionLabel": row["partition_label"],
        "map": row["actor_map"] or row["partition_map"],
        "dimensionIndex": row["dimension_index"],
        "x": row["x"],
        "y": row["y"],
        "z": row["z"],
    }


def compact_character(row):
    return {
        "accountId": row["account_id"],
        "characterName": row["character_name"],
        "flsId": row["fls_id"],
        "funcomId": row["funcom_id"],
        "onlineStatus": row["online_status"],
        "lifeState": row["life_state"],
        "serverId": row["server_id"],
        "playerControllerId": row["player_controller_id"],
        "playerPawnId": row["player_pawn_id"],
        "location": compact_location(row),
    }


def format_location(row):
    label = row["partition_label"] or row["actor_map"] or "unknown"
    if row["x"] is None:
        return f"{label} position unknown"
    return f"{label} x={row['x']:.1f} y={row['y']:.1f} z={row['z']:.1f}"


def route_key_from_map_partition(map_name, partition_id):
    if map_name == "HaggaBasin":
        map_name = "Survival_1"
    if map_name and partition_id not in (None, ""):
        return f"{map_name}{partition_id}"
    return None


def location_from_character(row, name="location0"):
    if row is None or row.get("partition_id") is None or row.get("x") is None:
        raise ValueError("character location is unavailable")
    return {
        "name": name,
        "characterName": row.get("character_name"),
        "serverId": row.get("server_id"),
        "partitionId": row.get("partition_id"),
        "partitionLabel": row.get("partition_label"),
        "map": row.get("partition_map") or row.get("actor_map"),
        "dimensionIndex": row.get("dimension_index"),
        "x": float(row.get("x")),
        "y": float(row.get("y")),
        "z": float(row.get("z")),
        "savedAt": int(time.time()),
    }


def read_gm_locations():
    try:
        data = json.loads(GM_LOCATION_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"locations": {}}
    if not isinstance(data, dict):
        return {"locations": {}}
    data.setdefault("locations", {})
    return data


def write_gm_locations(data):
    GM_LOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = GM_LOCATION_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(GM_LOCATION_FILE)


def save_gm_location(admin_name, location_name, row):
    data = read_gm_locations()
    locations = data.setdefault("locations", {})
    key = f"{admin_name.lower()}:{location_name.lower()}"
    location = location_from_character(row, location_name)
    locations[key] = location
    write_gm_locations(data)
    return location


def load_gm_location(admin_name, location_name):
    key = f"{admin_name.lower()}:{location_name.lower()}"
    return read_gm_locations().get("locations", {}).get(key)


def list_gm_locations(admin_name):
    prefix = f"{admin_name.lower()}:"
    locations = []
    for key, location in read_gm_locations().get("locations", {}).items():
        if key.startswith(prefix):
            locations.append(location)
    return sorted(locations, key=lambda item: item.get("name", "").lower())


def delete_gm_location(admin_name, location_name):
    data = read_gm_locations()
    key = f"{admin_name.lower()}:{location_name.lower()}"
    location = data.get("locations", {}).pop(key, None)
    if location:
        write_gm_locations(data)
    return location


def format_saved_location(location):
    if not location:
        return "location not found"
    label = location.get("partitionLabel") or location.get("map") or "unknown"
    return f"{location.get('name', 'location')} {label} x={location['x']:.1f} y={location['y']:.1f} z={location['z']:.1f}"


def gm_route_for(conn, row):
    route_key = route_key_from_map_partition(row.get("partition_map"), row.get("partition_id"))
    if route_key:
        return route_key
    map_name = row.get("partition_map") or row.get("actor_map")
    if map_name:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                select server_id
                from dune.farm_state
                where map = %s and server_id is not null
                order by ready desc, alive desc, server_id
                limit 1
                """,
                (map_name,),
            )
            farm = cur.fetchone()
        if farm and farm.get("server_id"):
            return farm["server_id"]
    return env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")


def gm_route_for_saved_location(conn, location):
    route_key = route_key_from_map_partition(location.get("map"), location.get("partitionId"))
    if route_key:
        return route_key
    return env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")


def gm_command_preview(command_text, target_player, admin_player, route):
    mode = env("DUNE_GM_COMMAND_ENVELOPE_MODE", "service-message")
    return {
        "route": route,
        "mode": mode,
        "commandText": command_text,
        "targetPlayer": target_player,
        "adminPlayer": admin_player,
        "envelope": build_envelope(mode, command_text, target_player=target_player, admin_player=admin_player),
    }


def gm_execution_allowed():
    return (
        env_bool("DUNE_ADMIN_GM_COMMANDS_ENABLED", False)
        and env_bool("DUNE_GM_COMMAND_PAYLOAD_VERIFIED", False)
        and env_bool("DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT", False)
    )


def send_gm_command(command_text, target_player, admin_player, route):
    if not gm_execution_allowed():
        return {"ok": False, "blocked": True, "preview": gm_command_preview(command_text, target_player, admin_player, route)}
    if env("DUNE_GM_COMMAND_TRANSPORT", "amqp") == "management":
        return publish_command_management(command_text, route, target_player=target_player, admin_player=admin_player)
    return publish_command(command_text, route, target_player=target_player, admin_player=admin_player)


def specialization_track_types(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            select enumlabel
            from pg_enum e
            join pg_type t on t.oid = e.enumtypid
            join pg_namespace n on n.oid = t.typnamespace
            where n.nspname = 'dune' and t.typname = 'specializationtracktype'
            order by e.enumsortorder
            """
        )
        return [row[0] for row in cur.fetchall()]


def handle_gm_command(conn, args, resolved_admin, reply=False):
    if not args:
        response = "usage: &gm <help|test|routes|mark|marks|recall|pos|dry|where|goto|bring|unstuck|item|kit|xp|tp|map|travel|dimension|patrol|sandworm|marker|vehicle|fly|ghost|walk> ..."
        if reply:
            run_announce(response)
        return {"ok": False, "error": response}

    subcommand = args[0].lower()
    admin, _ = character_row(conn, resolved_admin)

    if subcommand in ("help", "?"):
        response = "gm: test, routes, mark, marks, recall, pos, dry, where, goto, bring, unstuck, item, kit, xp, tp, map, travel, dimension, patrol, sandworm, marker, vehicle, fly, ghost, walk"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.help", "message": response}

    if subcommand == "test":
        response = "f00"
        announce_result = run_announce(response) if reply else None
        return {"ok": True, "action": "gm.test", "message": response, "reply": announce_result}

    if subcommand == "routes":
        if admin is None:
            response = f"admin player not found: {resolved_admin}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for(conn, admin)
        response = f"gm route {route}; native execution {'enabled' if gm_execution_allowed() else 'gated'}; you are at {format_location(admin)}"
        if reply:
            run_announce(response)
        return {
            "ok": True,
            "action": "gm.routes",
            "message": response,
            "route": route,
            "executionAllowed": gm_execution_allowed(),
            "admin": compact_character(admin),
        }

    if subcommand == "mark":
        location_name = args[1] if len(args) > 1 else "location0"
        if admin is None:
            response = f"admin player not found: {resolved_admin}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        try:
            location = save_gm_location(resolved_admin, location_name, admin)
        except ValueError as exc:
            response = str(exc)
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        response = f"marked {format_saved_location(location)}"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.mark", "message": response, "location": location}

    if subcommand in ("marks", "locations"):
        locations = list_gm_locations(resolved_admin)
        if locations:
            response = "marks: " + "; ".join(format_saved_location(location) for location in locations[:8])
        else:
            response = "no saved marks; use &gm mark [name]"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.marks", "message": response, "locations": locations}

    if subcommand in ("unmark", "delete-mark", "rm"):
        location_name = args[1] if len(args) > 1 else "location0"
        location = delete_gm_location(resolved_admin, location_name)
        response = f"deleted {format_saved_location(location)}" if location else f"no saved {location_name}"
        if reply:
            run_announce(response)
        return {"ok": bool(location), "action": "gm.unmark", "message": response, "location": location}

    if subcommand == "recall":
        location_name = args[1] if len(args) > 1 else "location0"
        location = load_gm_location(resolved_admin, location_name)
        if not location:
            response = f"no saved {location_name}; use &gm mark {location_name}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for_saved_location(conn, location)
        command_text = f"TeleportToExact {location['x']:.3f} {location['y']:.3f} {location['z']:.3f}"
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        if gm_result.get("ok"):
            response = f"sent recall to {format_saved_location(location)} via {route}"
        else:
            response = f"recall ready for {format_saved_location(location)}; native GM execution is still gated"
        if reply:
            run_announce(response)
        return {
            "ok": bool(gm_result.get("ok")),
            "action": "gm.recall",
            "blocked": not bool(gm_result.get("ok")),
            "message": response,
            "location": location,
            "gm": gm_result,
        }

    if subcommand == "pos":
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        gm_result = send_gm_command("PrintPos", resolved_admin, resolved_admin, route)
        response = f"PrintPos {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.pos", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand == "dry":
        command_text = " ".join(args[1:]).strip()
        if not command_text:
            response = "usage: &gm dry <native command...>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        preview = gm_command_preview(command_text, resolved_admin, resolved_admin, route)
        response = f"dry native command {command_text} via {route}"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.dry", "message": response, "preview": preview}

    if subcommand == "where":
        if len(args) != 2:
            response = "usage: &gm where <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        response = f"{target['character_name']} is {target['online_status']} at {format_location(target)}"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.where", "message": response, "target": compact_character(target)}

    if subcommand == "goto":
        if len(args) != 2:
            response = "usage: &gm goto <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        route = gm_route_for(conn, target)
        command_text = f"TeleportToPlayer {target['character_name']}"
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"goto {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.goto", "blocked": not bool(gm_result.get("ok")), "message": response, "target": compact_character(target), "gm": gm_result}

    if subcommand in ("bring", "summon"):
        if len(args) != 2:
            response = "usage: &gm bring <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        if admin is None or admin.get("x") is None:
            response = f"admin location unavailable for {resolved_admin}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        route = gm_route_for(conn, target)
        command_text = f"TeleportToExact {admin['x']:.3f} {admin['y']:.3f} {admin['z']:.3f}"
        gm_result = send_gm_command(command_text, target["character_name"], resolved_admin, route)
        response = f"bring {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.bring", "blocked": not bool(gm_result.get("ok")), "message": response, "admin": compact_character(admin), "target": compact_character(target), "gm": gm_result}

    if subcommand == "unstuck":
        if len(args) not in (2, 3):
            response = "usage: &gm unstuck <playername> [mark]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        mark_name = args[2] if len(args) == 3 else "location0"
        location = load_gm_location(resolved_admin, mark_name)
        if location:
            route = gm_route_for(conn, target)
            command_text = f"TeleportToExact {location['x']:.3f} {location['y']:.3f} {location['z']:.3f}"
            destination = format_saved_location(location)
        elif admin and admin.get("x") is not None:
            route = gm_route_for(conn, target)
            command_text = f"TeleportToExact {admin['x']:.3f} {admin['y']:.3f} {admin['z']:.3f}"
            destination = f"{resolved_admin} at {format_location(admin)}"
        else:
            response = f"no saved {mark_name} and admin location unavailable"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        gm_result = send_gm_command(command_text, target["character_name"], resolved_admin, route)
        response = f"unstuck {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} to {destination} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.unstuck", "blocked": not bool(gm_result.get("ok")), "message": response, "target": compact_character(target), "location": location, "gm": gm_result}

    if subcommand == "item":
        if len(args) not in (3, 4, 5):
            response = "usage: &gm item <playername> <template> [count] [quality]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        count = args[3] if len(args) >= 4 else "1"
        quality = args[4] if len(args) >= 5 else ""
        command_text = " ".join(part for part in ("AddItemToInventory", target["character_name"], args[2], count, quality) if part)
        route = gm_route_for(conn, target)
        gm_result = send_gm_command(command_text, target["character_name"], resolved_admin, route)
        response = f"item {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.item", "blocked": not bool(gm_result.get("ok")), "message": response, "target": compact_character(target), "gm": gm_result}

    if subcommand == "kit":
        if len(args) not in (2, 3):
            response = "usage: &gm kit <playername> [basic]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        kit_name = args[2].lower() if len(args) == 3 else "basic"
        if kit_name != "basic":
            response = "only basic kit is wired right now"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        route = gm_route_for(conn, target)
        command_text = f"AddBasicInventoryToCharacter {target['character_name']}"
        gm_result = send_gm_command(command_text, target["character_name"], resolved_admin, route)
        response = f"basic kit {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.kit", "blocked": not bool(gm_result.get("ok")), "message": response, "target": compact_character(target), "gm": gm_result}

    if subcommand == "xp":
        if len(args) not in (4, 5, 6):
            response = "usage: &gm xp <playername> <track> <amount> [add|set] [level]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        tracks = specialization_track_types(conn)
        track = args[2]
        if track not in tracks:
            response = "unknown track; valid tracks: " + ", ".join(tracks)
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "tracks": tracks}
        try:
            amount = int(args[3])
            mode = args[4] if len(args) >= 5 else "add"
            level = float(args[5]) if len(args) >= 6 else 0.0
        except ValueError:
            response = "usage: &gm xp <playername> <track> <amount> [add|set] [level]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        if mode not in ("add", "set"):
            response = "xp mode must be add or set"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        body = {
            "player_id": target["player_controller_id"],
            "track_type": track,
            "amount": amount,
            "level": level,
            "mode": mode,
        }
        response = f"xp preview ready for {target['character_name']}: {mode} {amount} {track}; use admin panel mutations to execute/audit"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.xp", "blocked": True, "message": response, "target": compact_character(target), "adminPanelApi": {"method": "POST", "path": "/api/admin/xp", "body": body}}

    if subcommand == "tp":
        if len(args) != 4:
            response = "usage: &gm tp <x> <y> <z>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        try:
            x, y, z = (float(args[1]), float(args[2]), float(args[3]))
        except ValueError:
            response = "usage: &gm tp <x> <y> <z>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        command_text = f"TeleportToExact {x:.3f} {y:.3f} {z:.3f}"
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"tp {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.tp", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand in ("map", "tomap"):
        if len(args) not in (2, 3):
            response = "usage: &gm map <map> [dimension]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        map_name = args[1]
        dimension = args[2] if len(args) == 3 else ""
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        command_text = " ".join(part for part in ("TeleportToMap", map_name, dimension) if part)
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"map teleport {'sent' if gm_result.get('ok') else 'preview ready'} to {map_name}{(' dim ' + dimension) if dimension else ''} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.map", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand in ("travel", "travelto"):
        if len(args) not in (2, 3):
            response = "usage: &gm travel <map> [location]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        command_text = " ".join(["TravelTo"] + args[1:])
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"travel {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.travel", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand in ("dimension", "dim"):
        if len(args) != 3:
            response = "usage: &gm dimension <map> <dimension>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        command_text = f"TravelToDimension {args[1]} {args[2]}"
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"dimension travel {'sent' if gm_result.get('ok') else 'preview ready'} to {args[1]} dim {args[2]} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.dimension", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand in ("patrol", "patrolship"):
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        gm_result = send_gm_command("PatrolShipTeleportToNearest", resolved_admin, resolved_admin, route)
        response = f"patrol ship teleport {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.patrol", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand == "sandworm":
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        gm_result = send_gm_command("TeleportToSandworm", resolved_admin, resolved_admin, route)
        response = f"sandworm teleport {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.sandworm", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand in ("marker", "personalmarker"):
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        gm_result = send_gm_command("TeleportToPersonalMarker", resolved_admin, resolved_admin, route)
        response = f"personal marker teleport {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.marker", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand == "vehicle":
        if len(args) < 2:
            response = "usage: &gm vehicle <template> [args...]"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        command_text = " ".join(["SpawnVehicle"] + args[1:])
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"vehicle spawn {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": "gm.vehicle", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    if subcommand in ("fly", "ghost", "walk"):
        route = gm_route_for(conn, admin) if admin else env("DUNE_GM_COMMAND_DEFAULT_ROUTE", "Survival_11")
        command_text = {"fly": "Fly", "ghost": "Ghost", "walk": "Walk"}[subcommand]
        gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
        response = f"{subcommand} {'sent' if gm_result.get('ok') else 'preview ready'} via {route}"
        if reply:
            run_announce(response)
        return {"ok": bool(gm_result.get("ok")), "action": f"gm.{subcommand}", "blocked": not bool(gm_result.get("ok")), "message": response, "gm": gm_result}

    response = f"unknown &gm command: {subcommand}"
    if reply:
        run_announce(response)
    return {"ok": False, "error": response}


def kick_candidate_routes(conn, target):
    route = gm_route_for(conn, target)
    return [
        {
            "name": "native-gm-session-command",
            "status": "investigate",
            "route": route,
            "candidateCommands": [
                f"PrintAllowedCommands",
                f"KickLobbyMember {target['character_name']}",
                f"RemoveSessionMember {target['character_name']}",
                f"BattlEyeMegaKick {target['character_name']}",
            ],
            "reason": "The live binary contains session/lobby kick strings, but DedicatedServerGame.ini does not expose a confirmed KickPlayer-style GM command and the RabbitMQ payload envelope is still unverified.",
        },
        {
            "name": "map-service-restart",
            "status": "available-but-not-targeted",
            "route": route,
            "reason": "Restarting the owning map can disconnect this player, but it disconnects every player on that map and is not a targeted kick.",
        },
        {
            "name": "database-online-state-write",
            "status": "rejected",
            "reason": "Postgres player_state is not the live network socket; blind writes can desync or be overwritten by the running map server.",
        },
        {
            "name": "network-block-by-client-ip",
            "status": "blocked",
            "reason": "The current DB/log surfaces do not reliably map character names to client IPs or UDP session handles.",
        },
    ]


def run_announce(message):
    command = env("DUNE_CHAT_COMMAND_REPLY_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", "/workspace/scripts/announce.sh"))
    wrapped = f"[Paul] {message}"
    result = subprocess.run(
        [command, wrapped],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=float(env("DUNE_CHAT_COMMAND_REPLY_TIMEOUT_SECONDS", "10")),
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def normalize_chat_text(text):
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def spam_protect_enabled():
    return env_bool("DUNE_CHAT_SPAM_PROTECT_ENABLED", True)


def spam_exempt(conn, sender_name, sender_fls_id):
    if env_bool("DUNE_CHAT_SPAM_PROTECT_EXEMPT_ADMINS", True):
        allowed, _ = is_admin(conn, sender_name, sender_fls_id)
        if allowed:
            return True
    exempt_names = {item.lower() for item in split_csv(env("DUNE_CHAT_SPAM_EXEMPT_NAMES", ""))}
    exempt_fls_ids = set(split_csv(env("DUNE_CHAT_SPAM_EXEMPT_FLS_IDS", "")))
    resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
    return bool((resolved_name and resolved_name.lower() in exempt_names) or (sender_fls_id and sender_fls_id in exempt_fls_ids))


def spam_state_key(sender_name, sender_fls_id):
    return sender_fls_id or sender_name or "unknown"


def spam_violation(state, normalized, now):
    consecutive_limit = int(env("DUNE_CHAT_SPAM_SAME_CONSECUTIVE_LIMIT", "3"))
    window_limit = int(env("DUNE_CHAT_SPAM_SAME_WINDOW_LIMIT", "5"))
    window_seconds = float(env("DUNE_CHAT_SPAM_SAME_WINDOW_SECONDS", "30"))

    if state.get("lastText") == normalized:
        state["consecutive"] = int(state.get("consecutive", 0)) + 1
    else:
        state["lastText"] = normalized
        state["consecutive"] = 1

    recent = state.setdefault("recent", collections.defaultdict(collections.deque))
    hits = recent[normalized]
    hits.append(now)
    while hits and now - hits[0] > window_seconds:
        hits.popleft()

    if state["consecutive"] > consecutive_limit:
        return {
            "type": "consecutive-repeat",
            "count": state["consecutive"],
            "limit": consecutive_limit,
            "windowSeconds": window_seconds,
        }
    if len(hits) >= window_limit:
        return {
            "type": "window-repeat",
            "count": len(hits),
            "limit": window_limit,
            "windowSeconds": window_seconds,
        }
    return None


def run_spam_kick_command(player_name, sender_fls_id, reason, text):
    command_template = env("DUNE_CHAT_SPAM_KICK_COMMAND", "")
    if not command_template:
        return {"ok": False, "blocked": True, "reason": "DUNE_CHAT_SPAM_KICK_COMMAND is not configured"}
    mapping = {
        "player": player_name,
        "character_name": player_name,
        "fls_id": sender_fls_id,
        "reason": reason,
        "message": text,
    }
    command = [part.format(**mapping) for part in shlex.split(command_template)]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=float(env("DUNE_CHAT_SPAM_KICK_TIMEOUT_SECONDS", "10")),
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def enforce_spam_protect(conn, text, sender_name="", sender_fls_id=""):
    if not spam_protect_enabled():
        return None
    normalized = normalize_chat_text(text)
    min_len = int(env("DUNE_CHAT_SPAM_MIN_MESSAGE_LENGTH", "1"))
    if len(normalized) < min_len:
        return None
    if spam_exempt(conn, sender_name, sender_fls_id):
        return None

    now = time.time()
    key = spam_state_key(sender_name, sender_fls_id)
    state = SPAM_STATE.setdefault(key, {})
    cooldown = float(env("DUNE_CHAT_SPAM_KICK_COOLDOWN_SECONDS", "300"))
    if now - float(state.get("lastKickAt", 0)) < cooldown:
        return None

    violation = spam_violation(state, normalized, now)
    if not violation:
        return None

    state["lastKickAt"] = now
    player_name = resolve_sender_character(conn, sender_name, sender_fls_id)
    reason = f"chat spam: {violation['type']} {violation['count']}/{violation['limit']}"
    kick_result = run_spam_kick_command(player_name, sender_fls_id, reason, text)
    announce = None
    if env_bool("DUNE_CHAT_SPAM_ANNOUNCE_ACTION", True):
        if kick_result.get("ok"):
            announce = run_announce(f"{player_name} was kicked for repeated chat spam")
        else:
            announce = run_announce(f"{player_name} triggered spam auto-kick, but kick backend is not configured")
    return {
        "ok": bool(kick_result.get("ok")),
        "action": "spam-protect",
        "player": player_name,
        "senderFlsId": sender_fls_id,
        "violation": violation,
        "message": text,
        "kick": kick_result,
        "announce": announce,
    }


def handle_command(conn, command_text, sender_name="", sender_fls_id="", reply=False):
    prefix = env("DUNE_CHAT_COMMAND_PREFIX", "&")
    if not command_text.startswith(prefix):
        return {"ok": True, "ignored": True}
    try:
        parts = shlex.split(command_text[len(prefix):])
    except ValueError as exc:
        return {"ok": False, "error": f"bad command syntax: {exc}"}
    if not parts:
        return {"ok": True, "ignored": True}

    command = parts[0].lower()
    allowed, resolved_admin = is_admin(conn, sender_name, sender_fls_id)
    if not allowed:
        response = f"command denied for {resolved_admin or sender_name or sender_fls_id or 'unknown'}"
        if reply:
            run_announce(response)
        return {"ok": False, "error": response}

    if command == "test":
        response = "f00"
        announce_result = run_announce(response) if reply else None
        return {"ok": True, "action": "test", "message": response, "reply": announce_result}

    if command == "gm":
        return handle_gm_command(conn, parts[1:], resolved_admin, reply=reply)

    if command in ("where", "loc", "location"):
        if len(parts) != 2:
            response = "usage: &where <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        response = f"{target['character_name']} is {target['online_status']} at {format_location(target)}"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "where", "message": response, "target": dict(target)}

    if command in ("kick", "disconnect", "sessionkick"):
        if len(parts) != 2:
            response = "usage: &kick <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}

        online = (target["online_status"] or "").lower() == "online"
        route = gm_route_for(conn, target)
        if online:
            response = f"{target['character_name']} is online on {route}; targeted kick route is not verified yet"
            ok = False
            reason = "no confirmed allow-listed native kick/session command is available yet"
        else:
            response = f"{target['character_name']} is {target['online_status']}; no live session to kick"
            ok = True
            reason = "target is not online"
        if reply:
            run_announce(response)
        return {
            "ok": ok,
            "action": "kick",
            "blocked": True,
            "reason": reason,
            "message": response,
            "target": compact_character(target),
            "candidateRoutes": kick_candidate_routes(conn, target),
        }

    if command == "teleport":
        if len(parts) != 2:
            response = "usage: &teleport <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        admin, _ = character_row(conn, resolved_admin)
        if admin is None or admin["partition_id"] is None or admin["x"] is None:
            response = f"admin location unavailable for {resolved_admin}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        if target["online_status"].lower() != "offline":
            response = f"{target['character_name']} is {target['online_status']}; safe teleport only supports offline targets right now"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "target": dict(target)}

        execute = env_bool("DUNE_CHAT_COMMAND_EXECUTE_TELEPORT", False)
        dry_run = env_bool("DUNE_CHAT_COMMAND_DRY_RUN", True) or not execute
        response = f"would move {target['character_name']} to {resolved_admin} at {format_location(admin)}"
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select dune.admin_move_offline_player_to_partition(
                        %s,
                        %s,
                        row(%s::real, %s::real, %s::real)::dune.vector
                    )
                    """,
                    (target["fls_id"], admin["partition_id"], admin["x"], admin["y"], admin["z"]),
                )
            conn.commit()
            response = f"moved {target['character_name']} to {resolved_admin} at {format_location(admin)}"
        if reply:
            run_announce(response)
        return {
            "ok": True,
            "action": "teleport",
            "dryRun": dry_run,
            "message": response,
            "admin": {"characterName": resolved_admin, "location": compact_location(admin)},
            "target": {"characterName": target["character_name"], "flsId": target["fls_id"], "status": target["online_status"], "location": compact_location(target)},
        }

    if command in ("goto", "teleportto", "tpto"):
        if len(parts) != 2:
            response = "usage: &goto <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        route = gm_route_for(conn, target)
        if target["online_status"].lower() == "online":
            command_text = f"TeleportToPlayer {target['character_name']}"
            gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
            if gm_result.get("ok"):
                response = f"sent native GM goto for {resolved_admin} to {target['character_name']} via {route}"
            else:
                response = f"{target['character_name']} is online at {format_location(target)}; live goto GM envelope is still gated"
            if reply:
                run_announce(response)
            return {
                "ok": bool(gm_result.get("ok")),
                "action": "goto",
                "blocked": not bool(gm_result.get("ok")),
                "reason": "online admin teleport requires DUNE_ADMIN_GM_COMMANDS_ENABLED=true, DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true, and DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true",
                "gm": gm_result,
                "candidateCommands": [
                    f"TeleportToPlayer {target['character_name']}",
                    f"TeleportToExact {target['x']} {target['y']} {target['z']}" if target["x"] is not None else "TeleportToExact <x> <y> <z>",
                    f"TravelTo {target['actor_map'] or target['partition_map']}",
                ],
                "message": response,
                "target": {"characterName": target["character_name"], "status": target["online_status"], "location": compact_location(target)},
            }
        response = f"{target['character_name']} is offline at {format_location(target)}; live goto still needs native GM command route verification"
        if reply:
            run_announce(response)
        return {
            "ok": False,
            "action": "goto",
            "blocked": True,
            "reason": "the sender is online when issuing chat commands, so moving the sender needs a live server command",
            "message": response,
            "target": {"characterName": target["character_name"], "status": target["online_status"], "location": compact_location(target)},
        }

    if command in ("bring", "summon", "tphere"):
        if len(parts) != 2:
            response = "usage: &bring <playername>"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        admin, _ = character_row(conn, resolved_admin)
        if admin is None or admin["partition_id"] is None or admin["x"] is None:
            response = f"admin location unavailable for {resolved_admin}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        if target["online_status"].lower() != "online":
            response = f"{target['character_name']} is {target['online_status']}; use &teleport for offline targets"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "target": dict(target)}
        route = gm_route_for(conn, target)
        command_text = f"TeleportToExact {admin['x']:.3f} {admin['y']:.3f} {admin['z']:.3f}"
        gm_result = send_gm_command(command_text, target["character_name"], resolved_admin, route)
        if gm_result.get("ok"):
            response = f"sent native GM bring for {target['character_name']} to {resolved_admin} via {route}"
        else:
            response = f"{target['character_name']} is online; bring GM envelope is still gated"
        if reply:
            run_announce(response)
        return {
            "ok": bool(gm_result.get("ok")),
            "action": "bring",
            "blocked": not bool(gm_result.get("ok")),
            "reason": "online player teleport requires the native live GM command route gates",
            "gm": gm_result,
            "candidateCommands": [command_text, f"TeleportToPlayer {resolved_admin}"],
            "message": response,
            "admin": {"characterName": resolved_admin, "location": compact_location(admin)},
            "target": {"characterName": target["character_name"], "status": target["online_status"], "location": compact_location(target)},
        }

    response = f"unknown command: {command}"
    if reply:
        run_announce(response)
    return {"ok": False, "error": response}


def parse_chat_message(body):
    outer = json.loads(body.decode("utf-8"))
    content = outer.get("content", outer)
    if isinstance(content, str):
        content = json.loads(content)
    message = content.get("m_Message", {}).get("m_UnlocalizedMessage", "")
    sender = content.get("m_FuncomIdFrom", "")
    return message, sender


def consume_forever():
    host = env("DUNE_CHAT_COMMAND_AMQP_HOST", env("DUNE_ANNOUNCE_HOST_AMQP_HOST", "172.31.240.1"))
    port = int(env("DUNE_CHAT_COMMAND_AMQP_PORT", env("DUNE_ANNOUNCE_HOST_AMQP_PORT", "31982")))
    tls = env_bool("DUNE_CHAT_COMMAND_AMQP_TLS", env_bool("DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS", True))
    user = env_chat_or_announce("DUNE_CHAT_COMMAND_AMQP_USER", "DUNE_ANNOUNCE_CHAT_USER", "")
    password = env_chat_or_announce("DUNE_CHAT_COMMAND_AMQP_PASSWORD", "DUNE_ANNOUNCE_CHAT_PASSWORD", "")
    exchange = env("DUNE_CHAT_COMMAND_EXCHANGE", "chat.intercept")
    queue = env("DUNE_CHAT_COMMAND_QUEUE", "dash_admin_chat_commands")
    routing_key = env("DUNE_CHAT_COMMAND_ROUTING_KEY", "#")

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host="/",
        credentials=pika.PlainCredentials(user, password),
        ssl_options=pika.SSLOptions(context, host) if tls else None,
        heartbeat=30,
        blocked_connection_timeout=10,
    ))
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=True, auto_delete=False)
    channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
    channel.basic_qos(prefetch_count=1)

    conn = connect_db()

    def on_message(ch, method, props, body):
        try:
            text, sender_name = parse_chat_message(body)
            sender_fls_id = getattr(props, "user_id", "") or ""
            spam_result = enforce_spam_protect(conn, text, sender_name=sender_name, sender_fls_id=sender_fls_id)
            if spam_result:
                print(json.dumps({"ts": int(time.time()), "routingKey": method.routing_key, "sender": sender_name, "senderFlsId": sender_fls_id, "result": spam_result}, default=str, separators=(",", ":")), flush=True)
            if text.startswith(env("DUNE_CHAT_COMMAND_PREFIX", "&")):
                result = handle_command(conn, text, sender_name=sender_name, sender_fls_id=sender_fls_id, reply=True)
                print(json.dumps({"ts": int(time.time()), "routingKey": method.routing_key, "sender": sender_name, "senderFlsId": sender_fls_id, "result": result}, default=str, separators=(",", ":")), flush=True)
            ch.basic_ack(method.delivery_tag)
        except Exception as exc:
            conn.rollback()
            print(json.dumps({"ts": int(time.time()), "error": str(exc)}, separators=(",", ":")), file=sys.stderr, flush=True)
            ch.basic_ack(method.delivery_tag)

    print(json.dumps({"ok": True, "listening": exchange, "queue": queue, "routingKey": routing_key}, separators=(",", ":")), flush=True)
    channel.basic_consume(queue=queue, on_message_callback=on_message)
    channel.start_consuming()


def main():
    parser = argparse.ArgumentParser(description="Paul in-game chat command listener")
    parser.add_argument("--dry-run-command", help="Process a command once without consuming RabbitMQ")
    parser.add_argument("--dry-run-spam-message", help="Process one message through spam protection without consuming RabbitMQ")
    parser.add_argument("--dry-run-spam-count", type=int, default=1, help="Number of times to feed --dry-run-spam-message")
    parser.add_argument("--sender-name", default="", help="Sender character name for --dry-run-command")
    parser.add_argument("--sender-fls-id", default="", help="Sender account/user id for --dry-run-command")
    parser.add_argument("--reply", action="store_true", help="Send an in-game reply for --dry-run-command")
    args = parser.parse_args()

    if args.dry_run_spam_message:
        with connect_db() as conn:
            results = [
                enforce_spam_protect(conn, args.dry_run_spam_message, args.sender_name, args.sender_fls_id)
                for _ in range(args.dry_run_spam_count)
            ]
        print(json.dumps({"ok": True, "results": results}, default=str, indent=2))
        return

    if args.dry_run_command:
        with connect_db() as conn:
            result = handle_command(conn, args.dry_run_command, args.sender_name, args.sender_fls_id, reply=args.reply)
        print(json.dumps(result, default=str, indent=2))
        return
    consume_forever()


if __name__ == "__main__":
    main()
