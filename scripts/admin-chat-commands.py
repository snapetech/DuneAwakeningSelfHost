#!/usr/bin/env python3
import argparse
import collections
import csv
import difflib
import importlib.util
import inspect
import json
import os
import pathlib
import re
import shlex
import ssl
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "vendor"))

import pika
import psycopg2
import psycopg2.extras

from dune_gm_command import build_envelope, publish_command, publish_command_management
from dune_whisper_route import whisper_route_for_fls_id

GM_CATALOG_PATH = pathlib.Path(__file__).with_name("gm-command-catalog.py")
GM_CATALOG_SPEC = importlib.util.spec_from_file_location("gm_command_catalog", GM_CATALOG_PATH)
gm_command_catalog = importlib.util.module_from_spec(GM_CATALOG_SPEC)
GM_CATALOG_SPEC.loader.exec_module(gm_command_catalog)

ROOT = pathlib.Path(__file__).resolve().parents[1]
GM_LOCATION_FILE = ROOT / "backups" / "admin-panel" / "gm-locations.json"
TELEPORT_SLOT_FILE = ROOT / "backups" / "admin-panel" / "teleport-slots.json"
ONLINE_GM_TELEPORT_ARM_FILE = ROOT / "backups" / "admin-panel" / "online-gm-teleport-arm.json"
ITEM_CATALOG = ROOT / "config" / "artificial-exchange-prices.csv"
SPAM_STATE = {}
AUCTION_CONFIRMATIONS = {}
LAST_ANNOUNCE_RESULT = None
ITEM_DISPLAY_NAMES = None


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

PROCESS_ENV_FIRST = {
    "DUNE_ADMIN_DB_HOST",
    "DUNE_ADMIN_DB_PORT",
    "DUNE_GM_COMMAND_AMQP_HOST",
    "DUNE_GM_COMMAND_AMQP_PORT",
    "DUNE_GM_COMMAND_RMQ_URL",
    "DUNE_CHAT_COMMAND_AMQP_HOST",
    "DUNE_CHAT_COMMAND_AMQP_PORT",
    "DUNE_CHAT_COMMAND_AMQP_TLS",
    "DUNE_ANNOUNCE_GAME_RMQ_MANAGEMENT_URL",
    "DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST",
    "DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT",
    "DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS",
    "DUNE_ANNOUNCE_RMQ_URL",
}


def env(name, default=""):
    if name in PROCESS_ENV_FIRST:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    if name.startswith("DUNE_CHAT_COMMAND_") or name.startswith("DUNE_ANNOUNCE_"):
        value = FILE_ENV.get(name)
        if value is not None and value != "":
            return value
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    value = FILE_ENV.get(name)
    if value is not None and value != "":
        return value
    return default


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


def split_routing_keys(value):
    out = []
    for item in value.split(","):
        item = item.strip()
        if item in ("<empty>", "empty", "EMPTY"):
            item = ""
        if item or item == "":
            out.append(item)
    return out


def item_display_names():
    global ITEM_DISPLAY_NAMES
    if ITEM_DISPLAY_NAMES is not None:
        return ITEM_DISPLAY_NAMES
    names = {}
    try:
        with ITEM_CATALOG.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                template_id = row.get("template_id")
                display_name = row.get("display_name")
                if template_id and display_name:
                    names[template_id] = display_name
    except OSError:
        pass
    ITEM_DISPLAY_NAMES = names
    return ITEM_DISPLAY_NAMES


def auction_usage_message():
    return 'usage: &auction --item-id <item-id> <count> <price> or &auction "<item code/template>" <count> <price>; use &inv_list for item codes'


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


def fls_id_for_sender(conn, sender_name):
    if not sender_name:
        return ""
    if not hasattr(conn, "cursor"):
        return ""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                select acc.user as fls_id
                from dune.accounts acc
                left join dune.player_state ps on ps.account_id = acc.id
                where acc.user = %s
                   or lower(acc.funcom_id) = lower(%s)
                   or lower(ps.character_name) = lower(%s)
                order by case when lower(ps.character_name) = lower(%s) then 0 else 1 end,
                         ps.character_name nulls last
                limit 1
                """,
                (sender_name, sender_name, sender_name, sender_name),
            )
            row = cur.fetchone()
    except (AttributeError, TypeError):
        return ""
    return (row or {}).get("fls_id") or ""


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
    names = {item.lower() for item in split_csv(env("DUNE_CHAT_COMMAND_ADMINS", "AdminUser"))}
    fls_ids = set(split_csv(env("DUNE_CHAT_COMMAND_ADMIN_FLS_IDS", "TEST_FLS_ID")))
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


def online_player_list(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select
                coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name,
                coalesce(nullif(wp.label, ''), nullif(act.map, ''), nullif(wp.map, ''), 'Unknown') as map_label
            from dune.player_state ps
            left join dune.actors act on act.id = ps.player_pawn_id
            left join dune.world_partition wp on wp.partition_id = act.partition_id
            where ps.online_status::text = 'Online'
            order by character_name;
            """
        )
        return cur.fetchall()


def format_online_player_list(rows):
    if not rows:
        return "no players online"
    return "online players: " + ", ".join(
        f"{row.get('character_name') or 'unknown'} ({row.get('map_label') or 'Unknown'})"
        for row in rows
    )


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


def teleport_slot_from_character(row, slot, name, creator):
    location = location_from_character(row, name or f"slot{slot}")
    location["slot"] = slot
    location["creator"] = creator
    location["dimension"] = row.get("dimension_index")
    return location


def parse_teleport_slot(value):
    if not re.fullmatch(r"\d+", value or ""):
        raise ValueError("slot must be a non-negative integer")
    return int(value)


def read_teleport_slots():
    try:
        data = json.loads(TELEPORT_SLOT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"slots": {}}
    if not isinstance(data, dict):
        return {"slots": {}}
    slots = data.get("slots")
    if not isinstance(slots, dict):
        data["slots"] = {}
    return data


def write_teleport_slots(data):
    TELEPORT_SLOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TELEPORT_SLOT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(TELEPORT_SLOT_FILE)


def load_teleport_slot(slot):
    return read_teleport_slots().get("slots", {}).get(str(slot))


def list_teleport_slots():
    slots = read_teleport_slots().get("slots", {})
    return [
        slots[key]
        for key in sorted((key for key in slots if re.fullmatch(r"\d+", str(key))), key=lambda item: int(item))
        if isinstance(slots.get(key), dict)
    ]


def next_free_teleport_slot(slots=None):
    slots = slots if slots is not None else read_teleport_slots().get("slots", {})
    occupied = {int(key) for key in slots if re.fullmatch(r"\d+", str(key))}
    slot = 0
    while slot in occupied:
        slot += 1
    return slot


def save_teleport_slot(slot, name, row, creator, replace=False):
    data = read_teleport_slots()
    slots = data.setdefault("slots", {})
    key = str(slot)
    if key in slots and not replace:
        return None, slots[key], next_free_teleport_slot(slots)
    location = teleport_slot_from_character(row, slot, name, creator)
    slots[key] = location
    write_teleport_slots(data)
    return location, None, None


def delete_teleport_slot(slot):
    data = read_teleport_slots()
    location = data.get("slots", {}).pop(str(slot), None)
    if location:
        write_teleport_slots(data)
    return location


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


def read_online_gm_teleport_arm():
    try:
        data = json.loads(ONLINE_GM_TELEPORT_ARM_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"arms": []}
    if not isinstance(data, dict):
        return {"arms": []}
    arms = data.get("arms")
    if not isinstance(arms, list):
        data["arms"] = []
    return data


def write_online_gm_teleport_arm(data):
    ONLINE_GM_TELEPORT_ARM_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ONLINE_GM_TELEPORT_ARM_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(ONLINE_GM_TELEPORT_ARM_FILE)


def online_gm_teleport_arm_seconds():
    return max(5, int(env("DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_ARM_SECONDS", "60")))


def online_gm_teleport_arm_entry(action, admin_name, target_name, route, command_text):
    return {
        "action": action,
        "adminPlayer": admin_name,
        "targetPlayer": target_name,
        "route": route,
        "commandText": command_text,
        "expiresAt": int(time.time()) + online_gm_teleport_arm_seconds(),
    }


def arm_online_gm_teleport(action, admin_name, target_name, route, command_text):
    now = int(time.time())
    data = read_online_gm_teleport_arm()
    entry = online_gm_teleport_arm_entry(action, admin_name, target_name, route, command_text)
    data["arms"] = [
        arm for arm in data.get("arms", [])
        if int(arm.get("expiresAt") or 0) > now
        and not (
            arm.get("action") == action
            and arm.get("adminPlayer") == admin_name
            and arm.get("targetPlayer") == target_name
        )
    ]
    data["arms"].append(entry)
    write_online_gm_teleport_arm(data)
    return entry


def consume_online_gm_teleport_arm(action, admin_name, target_name, route, command_text):
    if not env_bool("DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_REQUIRE_ARM", True):
        return True, "online GM teleport arming disabled"
    now = int(time.time())
    data = read_online_gm_teleport_arm()
    kept = []
    matched = None
    for arm in data.get("arms", []):
        if int(arm.get("expiresAt") or 0) <= now:
            continue
        if (
            arm.get("action") == action
            and arm.get("adminPlayer") == admin_name
            and arm.get("targetPlayer") == target_name
            and arm.get("route") == route
            and arm.get("commandText") == command_text
            and matched is None
        ):
            matched = arm
            continue
        kept.append(arm)
    if matched:
        data["arms"] = kept
        write_online_gm_teleport_arm(data)
        return True, f"armed until {matched.get('expiresAt')}"
    data["arms"] = kept
    write_online_gm_teleport_arm(data)
    return False, f"online GM teleport is not armed; run &arm{action} {target_name} first"


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


def format_teleport_slot(location):
    if not location:
        return "slot not found"
    label = location.get("partitionLabel") or location.get("map") or "unknown"
    name = location.get("name") or f"slot{location.get('slot')}"
    return f"slot {location.get('slot')}: {name} {label} x={location['x']:.1f} y={location['y']:.1f} z={location['z']:.1f}"


def format_teleport_slot_collision(location):
    if not location:
        return "slot not found"
    label = location.get("partitionLabel") or location.get("map") or "unknown"
    name = location.get("name") or f"slot{location.get('slot')}"
    return f"slot {location.get('slot')} exists: {name} {label} x={location['x']:.1f} y={location['y']:.1f} z={location['z']:.1f}"


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


def online_gm_teleport_safety(conn, action, admin, target):
    if admin is None:
        return False, "admin player not found", None, None
    if (admin.get("online_status") or "").lower() != "online":
        return False, f"admin {admin.get('character_name')} is {admin.get('online_status')}; online GM teleport needs the admin online", None, None
    if target is None:
        return False, "target player not found", None, None
    if (target.get("online_status") or "").lower() != "online":
        return False, f"{target.get('character_name')} is {target.get('online_status')}; online GM teleport only supports online targets", None, None
    if action in ("bring", "unstuck") and admin.get("x") is None:
        return False, f"admin location unavailable for {admin.get('character_name')}", None, None

    admin_route = gm_route_for(conn, admin)
    target_route = gm_route_for(conn, target)
    if not admin_route or not target_route:
        return False, "could not resolve admin and target GM routes", admin_route, target_route
    if env_bool("DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_REQUIRE_SAME_ROUTE", True) and admin_route != target_route:
        return (
            False,
            f"admin route {admin_route} differs from target route {target_route}; same-route live teleport guard is enabled",
            admin_route,
            target_route,
        )
    return True, "online GM teleport safety checks passed", admin_route, target_route


def player_disconnect_allowed():
    return (
        env_bool("DUNE_ADMIN_GM_COMMANDS_ENABLED", False)
        and env_bool("DUNE_GM_COMMAND_PAYLOAD_VERIFIED", False)
        and env_bool("DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT", False)
    )


def send_gm_command(command_text, target_player, admin_player, route):
    if not gm_execution_allowed():
        return {"ok": False, "blocked": True, "preview": gm_command_preview(command_text, target_player, admin_player, route)}
    if env("DUNE_GM_COMMAND_TRANSPORT", "amqp") == "management":
        return publish_command_management(command_text, route, target_player=target_player, admin_player=admin_player)
    return publish_command(command_text, route, target_player=target_player, admin_player=admin_player)


def send_online_gm_teleport(action, command_text, target_player, admin_player, route):
    armed, arm_reason = consume_online_gm_teleport_arm(action, admin_player, target_player, route, command_text)
    if not armed:
        return {
            "ok": False,
            "blocked": True,
            "reason": arm_reason,
            "preview": gm_command_preview(command_text, target_player, admin_player, route),
        }
    result = send_gm_command(command_text, target_player, admin_player, route)
    if isinstance(result, dict):
        result.setdefault("arm", {"ok": True, "reason": arm_reason})
    return result


def send_player_disconnect(command_text, target_player, admin_player, route):
    if not player_disconnect_allowed():
        return {"ok": False, "blocked": True, "preview": gm_command_preview(command_text, target_player, admin_player, route)}
    if env("DUNE_GM_COMMAND_TRANSPORT", "amqp") == "management":
        return publish_command_management(command_text, route, target_player=target_player, admin_player=admin_player)
    return publish_command(command_text, route, target_player=target_player, admin_player=admin_player)


def move_offline_player_to_partition(conn, fls_id, partition_id, x, y, z):
    with conn.cursor() as cur:
        cur.execute(
            """
            select dune.admin_move_offline_player_to_partition(
                %s,
                %s,
                row(%s::real, %s::real, %s::real)::dune.vector
            )
            """,
            (fls_id, partition_id, x, y, z),
        )
        cur.fetchall()
    return {
        "function": "dune.admin_move_offline_player_to_partition",
        "flsId": fls_id,
        "partitionId": partition_id,
        "location": {"x": x, "y": y, "z": z},
    }


def player_disconnect_command(target_name):
    command = env("DUNE_PLAYER_DISCONNECT_COMMAND", "RemoveSessionMember").strip()
    allowed = {"RemoveSessionMember", "KickLobbyMember"}
    if env_bool("DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE", False):
        allowed.add("BattlEyeMegaKick")
    if command not in allowed:
        raise ValueError(f"DUNE_PLAYER_DISCONNECT_COMMAND must be one of: {', '.join(sorted(allowed))}")
    return f"{command} {target_name}"


def chat_auction_enabled():
    return env_bool("DUNE_CHAT_COMMAND_AUCTION_ENABLED", False)


def chat_auction_base_storage_enabled():
    return env_bool("DUNE_CHAT_COMMAND_AUCTION_BASE_STORAGE_ENABLED", False)


def chat_exchange_cashout_enabled():
    return env_bool("DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_ENABLED", False)


def normalize_item_search(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def auction_confirmation_key(sender_name="", sender_fls_id="", resolved_name=""):
    return (sender_fls_id or resolved_name or sender_name or "unknown").lower()


def auction_confirmation_ttl():
    return int(env("DUNE_CHAT_COMMAND_AUCTION_CONFIRM_SECONDS", "120"))


def parse_positive_int(value, name):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive integer")
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def player_inventory_ids(conn, player):
    actor_ids = [player.get("player_pawn_id"), player.get("player_controller_id")]
    actor_ids = [int(actor_id) for actor_id in actor_ids if actor_id is not None]
    if not actor_ids:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select id, actor_id, inventory_type, max_item_count
            from dune.inventories
            where actor_id = any(%s)
            order by
              case when actor_id=%s then 0 else 1 end,
              inventory_type nulls last,
              id
            """,
            (actor_ids, player.get("player_pawn_id")),
        )
        return cur.fetchall()


def base_storage_inventory_ids(conn, player):
    actor_ids = [player.get("player_pawn_id"), player.get("player_controller_id")]
    actor_ids = [int(actor_id) for actor_id in actor_ids if actor_id is not None]
    if not actor_ids:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            with permitted_totems as (
                select t.id as totem_id, tp.owner_entity_id
                from dune.totems t
                join dune.placeables tp on tp.id=t.id
                join dune.permission_actor_rank par on par.permission_actor_id=t.id
                where par.player_id = any(%s)
            )
            select inv.id, inv.actor_id, inv.inventory_type, inv.max_item_count,
                   a.class, pa.actor_name, pt.totem_id
            from permitted_totems pt
            join dune.placeables child on child.owner_entity_id=pt.owner_entity_id and child.id<>pt.totem_id
            join dune.actors a on a.id=child.id
            join dune.inventories inv on inv.actor_id=child.id
            left join dune.permission_actor pa on pa.actor_id=child.id
            where a.class not like '%%/Characters/Player/%%'
            order by pt.totem_id, pa.actor_name nulls last, inv.id
            """,
            (actor_ids,),
        )
        return cur.fetchall()


def auction_source_inventories(conn, player, source="personal", explicit_inventory_id=None):
    personal = player_inventory_ids(conn, player)
    if source == "personal":
        return personal
    if source in ("base", "storage"):
        if not chat_auction_base_storage_enabled():
            raise ValueError("base/storage auction source is disabled")
        return base_storage_inventory_ids(conn, player)
    if source == "inventory":
        if not chat_auction_base_storage_enabled():
            raise ValueError("explicit inventory auction source is disabled")
        base = base_storage_inventory_ids(conn, player)
        allowed = {int(row["id"]) for row in personal + base}
        inventory_id = int(explicit_inventory_id)
        if inventory_id not in allowed:
            raise ValueError(f"inventory {inventory_id} is not an allowed personal/base inventory for this player")
        return [row for row in personal + base if int(row["id"]) == inventory_id]
    raise ValueError(f"unknown auction source: {source}")


def inventory_item_rows(conn, inventory_ids, explicit_item_id=None):
    if explicit_item_id is not None:
        where_clause = "i.id=%s and i.inventory_id = any(%s)"
        params = (int(explicit_item_id), inventory_ids)
    else:
        where_clause = "i.inventory_id = any(%s)"
        params = (inventory_ids,)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            select i.id, i.inventory_id, i.stack_size, i.position_index, i.template_id,
                   i.quality_level, i.stats, inv.actor_id, inv.inventory_type
            from dune.items i
            join dune.inventories inv on inv.id = i.inventory_id
            where {where_clause}
            order by i.template_id, i.quality_level desc, i.stack_size desc, i.id
            """,
            params,
        )
        return cur.fetchall()


def player_inventory_list_rows(conn, player):
    inventories = auction_source_inventories(conn, player, source="personal")
    if not inventories:
        return []
    inventory_ids = [row["id"] for row in inventories]
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select i.id, i.inventory_id, i.stack_size, i.position_index, i.template_id,
                   i.quality_level, inv.actor_id, inv.inventory_type
            from dune.items i
            join dune.inventories inv on inv.id = i.inventory_id
            where i.inventory_id = any(%s)
            order by i.inventory_id, i.position_index nulls last, i.id
            """,
            (inventory_ids,),
        )
        return cur.fetchall()


def format_inventory_item_list(rows):
    if not rows:
        return "inventory is empty"
    names = item_display_names()
    parts = []
    for row in rows:
        template_id = row.get("template_id") or "unknown"
        display_name = names.get(template_id, template_id)
        parts.append(
            f"{int(row.get('stack_size') or 0)}x {display_name} code={template_id} item-id={row.get('id')}"
        )
    return "inventory: " + "; ".join(parts)


def inventory_list_for_player(conn, player):
    rows = player_inventory_list_rows(conn, player)
    return rows, format_inventory_item_list(rows)


def parse_exchange_list_limit(args):
    default_limit = int(env("DUNE_CHAT_COMMAND_EXCHANGE_LIST_LIMIT", "25"))
    max_limit = int(env("DUNE_CHAT_COMMAND_EXCHANGE_LIST_MAX_LIMIT", "100"))
    if not args:
        return min(default_limit, max_limit)
    if len(args) > 1:
        raise ValueError("usage: &exchange_list [limit]")
    return min(parse_positive_int(args[0], "limit"), max_limit)


def exchange_fulfilled_orders_available(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select to_regclass('dune.dune_exchange_fulfilled_orders') as rel")
        row = cur.fetchone() or {}
    return bool(row.get("rel"))


def player_exchange_list_rows(conn, player, limit):
    exchange_id = int(env("DUNE_CHAT_COMMAND_AUCTION_EXCHANGE_ID", "2"))
    owner_id = int(player["player_controller_id"])
    has_fulfilled = exchange_fulfilled_orders_available(conn)
    fulfilled_join = "left join dune.dune_exchange_fulfilled_orders f on f.order_id=o.id" if has_fulfilled else ""
    fulfilled_where = "and f.order_id is null" if has_fulfilled else ""
    base_where = f"""
        o.exchange_id=%s
        and o.owner_id=%s
        and coalesce(o.is_npc_order, false)=false
        and o.template_id is not null
        and o.item_price is not null
        {fulfilled_where}
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            select count(*) as count
            from dune.dune_exchange_orders o
            join dune.dune_exchange_sell_orders s on s.order_id=o.id
            {fulfilled_join}
            where {base_where}
            """,
            (exchange_id, owner_id),
        )
        total = int((cur.fetchone() or {}).get("count") or 0)
        cur.execute(
            f"""
            select
                o.id, o.owner_id, o.template_id, o.item_price, o.expiration_time,
                coalesce(i.stack_size, s.initial_stack_size, 1) as stack_size
            from dune.dune_exchange_orders o
            join dune.dune_exchange_sell_orders s on s.order_id=o.id
            left join dune.items i on i.id=o.item_id
            {fulfilled_join}
            where {base_where}
            order by o.id desc
            limit %s
            """,
            (exchange_id, owner_id, int(limit)),
        )
        return cur.fetchall(), total


def format_player_exchange_list(rows, total):
    if total <= 0:
        return "exchange: you have no active sales"
    names = item_display_names()
    parts = []
    for row in rows:
        template_id = row.get("template_id") or "unknown"
        display_name = names.get(template_id, template_id)
        parts.append(
            f"order {row.get('id')}: {int(row.get('stack_size') or 0)}x {display_name} code={template_id} price={int(row.get('item_price') or 0)}"
        )
    prefix = f"exchange: showing {len(rows)}/{total} active sales"
    return prefix + ": " + "; ".join(parts)


def player_exchange_cashout_limit():
    return int(env("DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_LIMIT", "50"))


def player_exchange_cashout_candidates(conn, player, limit=None):
    owner_id = int(player["player_controller_id"])
    sold_completion_type = int(env("DUNE_ARTIFICIAL_EXCHANGE_SOLD_COMPLETION_TYPE", "1"))
    limit = int(limit if limit is not None else player_exchange_cashout_limit())
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select to_regclass('dune.dune_exchange_fulfilled_orders') as rel")
        if not (cur.fetchone() or {}).get("rel"):
            return [], 0
        cur.execute(
            """
            select count(*) as count
            from dune.dune_exchange_fulfilled_orders f
            join dune.dune_exchange_orders o on o.id=f.order_id
            where o.owner_id=%s
              and f.completion_type=%s
              and o.item_id is null
            """,
            (owner_id, sold_completion_type),
        )
        total = int((cur.fetchone() or {}).get("count") or 0)
        cur.execute(
            """
            select
                o.id as order_id,
                o.owner_id,
                o.item_id,
                o.template_id,
                o.item_price,
                f.completion_type,
                f.stack_size,
                f.source_order_id,
                f.original_order_id,
                (o.item_price * f.stack_size) as expected_solari
            from dune.dune_exchange_fulfilled_orders f
            join dune.dune_exchange_orders o on o.id=f.order_id
            where o.owner_id=%s
              and f.completion_type=%s
              and o.item_id is null
            order by o.id
            limit %s
            """,
            (owner_id, sold_completion_type, limit),
        )
        return cur.fetchall(), total


def ensure_solaris_balance_row(cur, controller_id):
    cur.execute(
        """
        insert into dune.player_virtual_currency_balances(player_controller_id, currency_id, balance)
        values(%s, dune.get_solaris_id(), 0)
        on conflict do nothing
        """,
        (controller_id,),
    )


def read_locked_solaris_balance(cur, controller_id):
    cur.execute(
        """
        select balance
        from dune.player_virtual_currency_balances
        where player_controller_id=%s and currency_id=dune.get_solaris_id()
        for update
        """,
        (controller_id,),
    )
    row = cur.fetchone()
    return int(row["balance"]) if row and row.get("balance") is not None else None


def execute_player_exchange_cashout_row(cur, row, owner_id):
    expected = int(row["expected_solari"])
    ensure_solaris_balance_row(cur, owner_id)
    before_balance = read_locked_solaris_balance(cur, owner_id)
    if before_balance is None:
        raise RuntimeError("Solaris balance row is unavailable for cashout")
    cur.execute(
        """
        select
            o.id as order_id,
            o.owner_id,
            o.item_id,
            o.item_price,
            f.completion_type,
            f.stack_size,
            f.original_order_id
        from dune.dune_exchange_orders o
        join dune.dune_exchange_fulfilled_orders f on f.order_id=o.id
        where o.id=%s and o.owner_id=%s
        for update
        """,
        (row["order_id"], owner_id),
    )
    locked = cur.fetchone()
    if not locked:
        raise RuntimeError(f"settlement order {row['order_id']} was not found")
    if locked["item_id"] not in (None, 0, ""):
        raise RuntimeError("settlement order has item_id; refusing Solari cashout")
    if int(locked["completion_type"]) != int(env("DUNE_ARTIFICIAL_EXCHANGE_SOLD_COMPLETION_TYPE", "1")):
        raise RuntimeError("settlement completion type is not a seller Solari claim")
    actual_value = int(locked["item_price"]) * int(locked["stack_size"])
    if actual_value != expected:
        raise RuntimeError(f"settlement value changed before cashout: expected {expected}, got {actual_value}")
    cur.execute(
        """
        update dune.player_virtual_currency_balances
        set balance = balance + %s
        where player_controller_id=%s and currency_id=dune.get_solaris_id()
        returning balance
        """,
        (expected, owner_id),
    )
    after_balance = int(cur.fetchone()["balance"])
    cur.execute("delete from dune.dune_exchange_orders where id=%s", (row["order_id"],))
    cur.execute(
        """
        select exists(
            select 1
            from dune.dune_exchange_orders o
            left join dune.dune_exchange_fulfilled_orders f on f.order_id=o.id
            where o.id=%s or f.order_id=%s
        ) as still_exists
        """,
        (row["order_id"], row["order_id"]),
    )
    still_exists = bool(cur.fetchone()["still_exists"])
    credited = after_balance - before_balance
    if credited != expected or still_exists:
        raise RuntimeError("cashout failed validation")
    return {
        "orderId": int(row["order_id"]),
        "templateId": row.get("template_id"),
        "stackSize": int(row["stack_size"]),
        "credited": credited,
        "beforeBalance": before_balance,
        "afterBalance": after_balance,
    }


def player_exchange_cashout(conn, player, dry_run=True):
    owner_id = int(player["player_controller_id"])
    rows, total = player_exchange_cashout_candidates(conn, player)
    expected_total = sum(int(row["expected_solari"]) for row in rows)
    if dry_run:
        return {"ok": True, "dryRun": True, "claimed": [], "candidateCount": len(rows), "total": total, "expectedSolari": expected_total}
    claimed = []
    try:
        for row in rows:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                claimed.append(execute_player_exchange_cashout_row(cur, row, owner_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "ok": True,
        "dryRun": False,
        "claimed": claimed,
        "candidateCount": len(rows),
        "total": total,
        "credited": sum(int(row["credited"]) for row in claimed),
    }


def format_exchange_cashout(result):
    if result.get("dryRun"):
        count = int(result.get("candidateCount") or 0)
        total = int(result.get("total") or 0)
        solari = int(result.get("expectedSolari") or 0)
        if count <= 0:
            return "exchange cashout preview: no completed sales ready"
        suffix = "; rerun after current batch if more remain" if total > count else ""
        return f"exchange cashout preview: {solari} Solaris from {count}/{total} completed sales; enable DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_ENABLED=true to execute{suffix}"
    claimed = result.get("claimed") or []
    credited = int(result.get("credited") or 0)
    if not claimed:
        return "exchange cashout: no completed sales ready"
    suffix = "; rerun to claim remaining completed sales" if int(result.get("total") or 0) > len(claimed) else ""
    return f"exchange cashout: credited {credited} Solaris from {len(claimed)} completed sales{suffix}"


def fuzzy_item_suggestion(rows, search_text, count):
    normalized = normalize_item_search(search_text)
    wanted_tokens = [token for token in re.split(r"[^a-z0-9]+", search_text.lower()) if token]
    ignored = {"improved", "basic", "advanced", "mk", "tier"}
    scored = []
    for row in rows:
        if int(row.get("stack_size") or 0) < count:
            continue
        template = row.get("template_id") or ""
        template_norm = normalize_item_search(template)
        if not template_norm:
            continue
        ratio = difflib.SequenceMatcher(None, normalized, template_norm).ratio() if normalized else 0.0
        token_hits = sum(1 for token in wanted_tokens if token not in ignored and token in template_norm)
        prefix_bonus = 0.2 if template_norm.startswith(normalized[: min(len(normalized), 4)]) else 0.0
        contains_bonus = 0.25 if normalized and normalized in template_norm else 0.0
        score = ratio + contains_bonus + prefix_bonus + (token_hits * 0.1)
        scored.append((score, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], int(item[1].get("stack_size") or 0)), reverse=True)
    score, row = scored[0]
    threshold = float(env("DUNE_CHAT_COMMAND_AUCTION_SUGGESTION_MIN_SCORE", "0.55"))
    if score < threshold:
        return None
    return {
        "itemId": row["id"],
        "templateId": row["template_id"],
        "stackSize": row["stack_size"],
        "inventoryId": row["inventory_id"],
        "qualityLevel": row["quality_level"],
        "score": round(score, 3),
    }


def item_search_candidates(conn, player, search_text, source="personal", explicit_inventory_id=None, explicit_item_id=None, count=1):
    inventories = auction_source_inventories(conn, player, source=source, explicit_inventory_id=explicit_inventory_id)
    if not inventories:
        return [], [], None
    inventory_ids = [row["id"] for row in inventories]
    if explicit_item_id is not None:
        rows = inventory_item_rows(conn, inventory_ids, explicit_item_id=explicit_item_id)
        return rows, inventories, None
    normalized = normalize_item_search(search_text)
    if not normalized:
        return [], inventories, None
    rows = inventory_item_rows(conn, inventory_ids)
    exact = []
    contains = []
    token_contains = []
    wanted_tokens = [token for token in re.split(r"[^a-z0-9]+", search_text.lower()) if token]
    for row in rows:
        template_norm = normalize_item_search(row["template_id"])
        if template_norm == normalized:
            exact.append(row)
        elif normalized and normalized in template_norm:
            contains.append(row)
        elif wanted_tokens and all(token in template_norm for token in wanted_tokens if token not in {"improved", "basic", "advanced", "mk", "tier"}):
            token_contains.append(row)
    matches = exact or contains or token_contains
    suggestion = None if matches else fuzzy_item_suggestion(rows, search_text, count)
    return matches, inventories, suggestion


def parse_auction_command_args(args):
    if len(args) < 3:
        raise ValueError(auction_usage_message())
    source = "personal"
    explicit_inventory_id = None
    explicit_item_id = None
    remaining = list(args)
    while remaining:
        if remaining[0] in ("--base", "base", "--storage", "storage"):
            source = "base"
            remaining = remaining[1:]
        elif remaining[0] in ("--inventory", "inventory", "--inv", "inv"):
            if len(remaining) < 2:
                raise ValueError("usage: &auction --inventory <inventory_id> <item> <count> <price>")
            explicit_inventory_id = parse_positive_int(remaining[1], "inventory_id")
            source = "inventory"
            remaining = remaining[2:]
        elif remaining[0] in ("--item-id", "item-id", "--item", "item"):
            if len(remaining) < 2:
                raise ValueError("usage: &auction --item-id <item_id> <count> <price>")
            explicit_item_id = parse_positive_int(remaining[1], "item_id")
            remaining = remaining[2:]
        else:
            break
    if explicit_item_id is None and len(remaining) < 3:
        raise ValueError(auction_usage_message())
    if explicit_item_id is not None and len(remaining) > 2:
        raise ValueError("do not provide an item name when using --item-id")
    if explicit_item_id is not None and len(remaining) < 2:
        raise ValueError("usage: &auction --item-id <item_id> <count> <price>")
    count = parse_positive_int(remaining[-2], "count")
    price = parse_positive_int(remaining[-1], "price")
    if explicit_item_id is None:
        search_text = " ".join(remaining[:-2]).strip()
        if not search_text:
            raise ValueError(auction_usage_message())
    else:
        if remaining[:-2]:
            raise ValueError("do not provide an item name when using --item-id")
        search_text = f"item-id:{explicit_item_id}"
    return source, explicit_inventory_id, explicit_item_id, search_text, count, price


def solari_balance(conn, owner_id):
    with conn.cursor() as cur:
        cur.execute("select dune.dune_exchange_retrieve_solari_balance(%s)", (owner_id,))
        row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def exchange_order_slots(conn, owner_id):
    with conn.cursor() as cur:
        cur.execute("select dune.get_dune_exchange_used_order_slots(%s)", (owner_id,))
        row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def auction_item(conn, player, search_text, count, price, dry_run=True, source="personal", explicit_inventory_id=None, explicit_item_id=None):
    owner_id = int(player["player_controller_id"])
    exchange_id = int(env("DUNE_CHAT_COMMAND_AUCTION_EXCHANGE_ID", "2"))
    access_point_id = int(env("DUNE_CHAT_COMMAND_AUCTION_ACCESS_POINT_ID", "1"))
    max_orders = int(env("DUNE_CHAT_COMMAND_AUCTION_MAX_ORDERS_PER_PLAYER", "50"))
    solari_cost = int(env("DUNE_CHAT_COMMAND_AUCTION_LISTING_FEE", "0"))
    duration_seconds = int(env("DUNE_CHAT_COMMAND_AUCTION_DURATION_SECONDS", "2419200"))
    category_mask = int(env("DUNE_CHAT_COMMAND_AUCTION_CATEGORY_MASK", "0"))
    category_depth = int(env("DUNE_CHAT_COMMAND_AUCTION_CATEGORY_DEPTH", "0"))
    expires_at = int(time.time()) + duration_seconds

    try:
        matches, inventories, suggestion = item_search_candidates(conn, player, search_text, source=source, explicit_inventory_id=explicit_inventory_id, explicit_item_id=explicit_item_id, count=count)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not matches:
        response = {
            "ok": False,
            "error": f"no allowed inventory item matched '{search_text}'",
            "source": source,
            "searchedInventories": [row["id"] for row in inventories],
        }
        if suggestion:
            response["suggestion"] = suggestion
        return response
    templates = sorted({row["template_id"] for row in matches})
    if len(templates) > 1:
        return {
            "ok": False,
            "error": "item search is ambiguous: " + ", ".join(templates[:12]),
            "source": source,
            "matches": [
                {"itemId": row["id"], "templateId": row["template_id"], "stackSize": row["stack_size"], "inventoryId": row["inventory_id"]}
                for row in matches[:20]
            ],
        }

    available = sum(int(row["stack_size"]) for row in matches)
    if available < count:
        return {
            "ok": False,
            "error": f"only {available}x {templates[0]} available, requested {count}",
            "source": source,
            "matches": [
                {"itemId": row["id"], "templateId": row["template_id"], "stackSize": row["stack_size"], "inventoryId": row["inventory_id"]}
                for row in matches
            ],
        }
    if exchange_order_slots(conn, owner_id) >= max_orders:
        return {"ok": False, "error": f"exchange order slot limit reached ({max_orders})"}
    balance = solari_balance(conn, owner_id)
    if balance < solari_cost:
        return {"ok": False, "error": f"exchange Solari balance {balance} is below listing fee {solari_cost}"}

    source_item = next((row for row in matches if int(row["stack_size"]) >= count), None)
    if not source_item:
        return {"ok": False, "error": "split-across-stacks listing is not supported yet; merge the stack first"}
    stats = source_item.get("stats") or {}
    durability = ((stats.get("FItemStackAndDurabilityStats") or [None, {}])[1] or {}) if isinstance(stats, dict) else {}
    durability_cur = float(durability.get("CurrentDurability") or 100.0)
    durability_max = float(durability.get("MaxDurability") or 100.0)
    plan = {
        "player": player["character_name"],
        "ownerId": owner_id,
        "exchangeId": exchange_id,
        "accessPointId": access_point_id,
        "itemId": source_item["id"],
        "templateId": source_item["template_id"],
        "count": count,
        "price": price,
        "listingFee": solari_cost,
        "expiresAt": expires_at,
        "sourceInventoryId": source_item["inventory_id"],
        "sourceStackSize": source_item["stack_size"],
        "source": source,
        "explicitItemId": explicit_item_id,
        "dryRun": dry_run,
    }
    if dry_run:
        return {"ok": True, "action": "auction.preview", "plan": plan}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            select *
            from dune.dune_exchange_add_sell_order(
              %s::bigint, %s::bigint, %s::bigint, %s::integer, %s::bigint,
              %s::bigint, %s::bigint, %s::integer, %s::smallint, %s::real,
              %s::real, %s::bigint, %s::bigint, %s::bigint, %s::bigint
            )
            """,
            (
                exchange_id,
                access_point_id,
                owner_id,
                max_orders,
                expires_at,
                int(source_item["id"]),
                count,
                category_mask,
                category_depth,
                durability_cur,
                durability_max,
                price,
                price,
                int(source_item["quality_level"] or 0),
                solari_cost,
            ),
        )
        result = cur.fetchone()
        order_id = int(result.get("order_id") or 0) if result else 0
        slots = int(result.get("order_slots_used") or 0) if result else 0
        if order_id <= 0:
            conn.rollback()
            return {"ok": False, "error": "exchange function returned order_id=0", "plan": plan, "orderSlotsUsed": slots}
        cur.execute(
            """
            select o.id, o.owner_id, o.item_id, o.template_id, o.item_price, o.expiration_time,
                   i.stack_size, i.inventory_id
            from dune.dune_exchange_orders o
            join dune.items i on i.id=o.item_id
            where o.id=%s
            """,
            (order_id,),
        )
        order = cur.fetchone()
    conn.commit()
    return {"ok": True, "action": "auction.created", "plan": plan, "order": dict(order), "orderSlotsUsed": slots}


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
        response = "usage: &gm <help|catalog|test|routes|mark|marks|recall|pos|dry|where|goto|bring|unstuck|item|kit|xp|tp|map|travel|dimension|patrol|sandworm|marker|vehicle|fly|ghost|walk> ...; online &goto/&bring require &armgoto/&armbring first"
        if reply:
            run_announce(response)
        return {"ok": False, "error": response}

    subcommand = args[0].lower()
    admin, _ = character_row(conn, resolved_admin)

    if subcommand in ("help", "?"):
        response = "gm: catalog, test, routes, mark, marks, recall, pos, dry, where, goto, bring, unstuck, item, kit, xp, tp, map, travel, dimension, patrol, sandworm, marker, vehicle, fly, ghost, walk; use &armgoto/&armbring before live online movement"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.help", "message": response}

    if subcommand in ("catalog", "commands"):
        data = gm_command_catalog.catalog()
        counts = {}
        for command in data["commands"]:
            counts[command["status"]] = counts.get(command["status"], 0) + 1
        wired = [command["name"] for command in data["commands"] if command["status"] in ("wired-preview", "gated-preview")]
        response = "gm catalog: " + ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
        response += "; wired: " + ", ".join(wired[:12])
        if len(wired) > 12:
            response += f", +{len(wired) - 12} more"
        response += "; full list: ./scripts/gm-command-catalog.py --format markdown"
        if reply:
            run_announce(response)
        return {"ok": True, "action": "gm.catalog", "message": response, "catalog": data}

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
        if admin is None:
            response = f"admin player not found: {resolved_admin}"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response}
        target, matches = character_row(conn, args[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            if reply:
                run_announce(response)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches]}
        safe, safety_reason, admin_route, target_route = online_gm_teleport_safety(conn, "goto", admin, target)
        route = target_route or gm_route_for(conn, target)
        command_text = f"TeleportToPlayer {target['character_name']}"
        if safe:
            gm_result = send_online_gm_teleport("goto", command_text, resolved_admin, resolved_admin, route)
            response = f"goto {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} via {route}"
        else:
            gm_result = {"ok": False, "blocked": True, "reason": safety_reason, "preview": gm_command_preview(command_text, resolved_admin, resolved_admin, route)}
            response = f"goto blocked for {target['character_name']}: {safety_reason}"
        if reply:
            run_announce(response)
        reason = safety_reason if not safe else "online GM teleport requires DUNE_ADMIN_GM_COMMANDS_ENABLED=true, DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true, and DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true"
        return {"ok": bool(gm_result.get("ok")), "action": "gm.goto", "blocked": not bool(gm_result.get("ok")), "reason": reason, "message": response, "adminRoute": admin_route, "targetRoute": target_route, "target": compact_character(target), "gm": gm_result}

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
        safe, safety_reason, admin_route, target_route = online_gm_teleport_safety(conn, "bring", admin, target)
        route = target_route or gm_route_for(conn, target)
        command_text = f"TeleportToExact {admin['x']:.3f} {admin['y']:.3f} {admin['z']:.3f}"
        if safe:
            gm_result = send_online_gm_teleport("bring", command_text, target["character_name"], resolved_admin, route)
            response = f"bring {'sent' if gm_result.get('ok') else 'preview ready'} for {target['character_name']} via {route}"
        else:
            gm_result = {"ok": False, "blocked": True, "reason": safety_reason, "preview": gm_command_preview(command_text, target["character_name"], resolved_admin, route)}
            response = f"bring blocked for {target['character_name']}: {safety_reason}"
        if reply:
            run_announce(response)
        reason = safety_reason if not safe else "online GM teleport requires DUNE_ADMIN_GM_COMMANDS_ENABLED=true, DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true, and DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true"
        return {"ok": bool(gm_result.get("ok")), "action": "gm.bring", "blocked": not bool(gm_result.get("ok")), "reason": reason, "message": response, "adminRoute": admin_route, "targetRoute": target_route, "admin": compact_character(admin), "target": compact_character(target), "gm": gm_result}

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
            "status": "gated",
            "route": route,
            "candidateCommands": [
                f"PrintAllowedCommands",
                f"RemoveSessionMember {target['character_name']}",
                f"KickLobbyMember {target['character_name']}",
                f"BattlEyeMegaKick {target['character_name']}",
            ],
            "reason": "Use RemoveSessionMember first for the least punitive disconnect. Execution requires DUNE_ADMIN_GM_COMMANDS_ENABLED=true, DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true, and DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=true.",
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


def run_announce(message, target_name="", target_fls_id=""):
    global LAST_ANNOUNCE_RESULT
    if not target_name or not target_fls_id:
        inferred_name, inferred_fls_id = infer_command_reply_target()
        target_name = target_name or inferred_name
        target_fls_id = target_fls_id or inferred_fls_id
    command = env("DUNE_CHAT_COMMAND_REPLY_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", "/workspace/scripts/announce.sh"))
    if command.startswith("/workspace/") and not pathlib.Path(command).exists():
        command = str(ROOT / command.removeprefix("/workspace/"))
    wrapped = f"[Paul] {message}"
    child_env = os.environ.copy()
    child_env.update(FILE_ENV)
    cwd = ROOT
    target_reply_mode = env("DUNE_CHAT_COMMAND_TARGET_REPLY_MODE", "").strip().lower()
    if not target_reply_mode and env_bool("DUNE_CHAT_COMMAND_PRIVATE_REPLIES_ENABLED", False):
        target_reply_mode = "whisper"
    if target_reply_mode in ("whisper", "private") and (not target_name or not target_fls_id):
        LAST_ANNOUNCE_RESULT = {
            "ok": False,
            "skipped": True,
            "reason": "private command reply target unavailable; refusing public fallback",
            "stdout": "",
            "stderr": "",
        }
        return LAST_ANNOUNCE_RESULT
    if target_name and target_fls_id and target_reply_mode in ("whisper", "private"):
        whisper_route = whisper_route_for_fls_id(target_fls_id)
        child_env["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"] = "true"
        child_env["DUNE_ANNOUNCE_CHAT_EXCHANGE"] = env("DUNE_CHAT_COMMAND_PRIVATE_REPLY_EXCHANGE", "chat.whispers")
        child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL", "Whispers")
        child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = target_name
        child_env["DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS"] = whisper_route["routingKey"]
        child_env["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"] = whisper_route["queue"]
        child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = env("DUNE_CHAT_COMMAND_PRIVATE_REPLY_ROUTING_KEY", whisper_route["routingKey"]) or whisper_route["routingKey"]
        child_env["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"] = "false"
        child_env["DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS"] = "true"
        child_env["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"] = "false"
        cwd = "/tmp"
    elif target_name and target_fls_id and target_reply_mode in ("proximity", "prox"):
        child_env["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"] = "true"
        child_env["DUNE_ANNOUNCE_CHAT_EXCHANGE"] = env("DUNE_CHAT_COMMAND_TARGET_REPLY_EXCHANGE", "chat.proximity")
        child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_CHAT_COMMAND_TARGET_REPLY_CHANNEL", "Proximity")
        child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = target_name
        child_env["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"] = f"{target_fls_id}_queue"
        child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = env("DUNE_CHAT_COMMAND_TARGET_REPLY_ROUTING_KEY", f"dash.chat-command-reply.{target_fls_id}")
        child_env["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"] = "false"
        child_env["DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS"] = "true"
        child_env["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"] = "false"
        cwd = "/tmp"
    elif target_name and target_fls_id and target_reply_mode == "guild":
        child_env["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"] = "true"
        child_env["DUNE_ANNOUNCE_CHAT_EXCHANGE"] = env("DUNE_CHAT_COMMAND_TARGET_REPLY_EXCHANGE", "chat.guild.1")
        child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_CHAT_COMMAND_TARGET_REPLY_CHANNEL", "Guild")
        child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = target_name
        child_env["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"] = f"{target_fls_id}_queue"
        child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = env("DUNE_CHAT_COMMAND_TARGET_REPLY_ROUTING_KEY", "<empty>")
        child_env["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"] = "false"
        child_env["DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS"] = "true"
        child_env["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"] = "false"
        cwd = "/tmp"
    elif target_name:
        child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = target_name
    result = subprocess.run(
        [command, wrapped],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=float(env("DUNE_CHAT_COMMAND_REPLY_TIMEOUT_SECONDS", "10")),
        check=False,
        env=child_env,
    )
    LAST_ANNOUNCE_RESULT = {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    return LAST_ANNOUNCE_RESULT


def maybe_reply(message, reply=False, target_name="", target_fls_id=""):
    return run_announce(message, target_name=target_name, target_fls_id=target_fls_id) if reply else None


def infer_command_reply_target():
    frame = inspect.currentframe()
    if frame is None:
        return "", ""
    frame = frame.f_back
    while frame:
        if frame.f_code.co_name == "handle_command":
            sender_fls_id = frame.f_locals.get("sender_fls_id") or ""
            if not sender_fls_id:
                return "", ""
            sender_name = frame.f_locals.get("sender_name") or ""
            resolved_admin = frame.f_locals.get("resolved_admin") or ""
            return resolved_admin or sender_name, sender_fls_id
        frame = frame.f_back
    return "", ""


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
    if not sender_fls_id and sender_name:
        sender_fls_id = fls_id_for_sender(conn, sender_name)

    command = parts[0].lower()
    if command in ("list", "players", "online"):
        players = online_player_list(conn)
        response = format_online_player_list(players)
        announce_result = maybe_reply(response, reply, target_name=sender_name, target_fls_id=sender_fls_id)
        return {"ok": True, "action": "list", "message": response, "players": [dict(row) for row in players], "reply": announce_result}

    if command in ("inv_list", "inventory", "inv"):
        resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
        player, matches = character_row(conn, resolved_name)
        if player is None:
            response = "could not resolve your character for inventory list"
            if matches:
                response = "no unique character match: " + ", ".join(row["character_name"] for row in matches)
            announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        rows, response = inventory_list_for_player(conn, player)
        announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
        return {"ok": True, "action": "inv_list", "message": response, "items": [dict(row) for row in rows], "reply": announce_result}

    if command in ("exchange_list", "auction_list", "my_auctions", "sales"):
        try:
            limit = parse_exchange_list_limit(parts[1:])
        except ValueError as exc:
            response = str(exc)
            announce_result = maybe_reply(response, reply, target_name=sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
        player, matches = character_row(conn, resolved_name)
        if player is None:
            response = "could not resolve your character for exchange list"
            if matches:
                response = "no unique character match: " + ", ".join(row["character_name"] for row in matches)
            announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        rows, total = player_exchange_list_rows(conn, player, limit)
        response = format_player_exchange_list(rows, total)
        announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
        return {"ok": True, "action": "exchange_list", "message": response, "orders": [dict(row) for row in rows], "total": total, "reply": announce_result}

    if command in ("exchange_cashout", "cashout"):
        if len(parts) > 1:
            response = "usage: &exchange_cashout"
            announce_result = maybe_reply(response, reply, target_name=sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
        player, matches = character_row(conn, resolved_name)
        if player is None:
            response = "could not resolve your character for exchange cashout"
            if matches:
                response = "no unique character match: " + ", ".join(row["character_name"] for row in matches)
            announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        dry_run = not chat_exchange_cashout_enabled()
        try:
            result = player_exchange_cashout(conn, player, dry_run=dry_run)
            response = format_exchange_cashout(result)
            ok = bool(result.get("ok"))
        except Exception as exc:
            conn.rollback()
            result = {"ok": False, "error": str(exc), "dryRun": dry_run}
            response = f"exchange cashout failed: {exc}"
            ok = False
        announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
        return result | {"ok": ok, "action": "exchange_cashout", "message": response, "reply": announce_result}

    if command == "auction":
        if len(parts) == 1:
            resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
            player, matches = character_row(conn, resolved_name)
            if player is None:
                inventory_response = "could not resolve your character for inventory list"
                if matches:
                    inventory_response = "no unique character match: " + ", ".join(row["character_name"] for row in matches)
                response = f"{auction_usage_message()}; {inventory_response}"
                announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
                return {"ok": False, "error": inventory_response, "message": response, "reply": announce_result}
            rows, inventory_response = inventory_list_for_player(conn, player)
            response = f"{auction_usage_message()}; {inventory_response}"
            announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
            return {"ok": True, "action": "auction.help", "message": response, "items": [dict(row) for row in rows], "reply": announce_result}

        if len(parts) == 2 and parts[1].lower() in ("yes", "y", "no", "n"):
            resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
            confirm_key = auction_confirmation_key(sender_name, sender_fls_id, resolved_name)
            pending = AUCTION_CONFIRMATIONS.get(confirm_key)
            if not pending or int(time.time()) > int(pending.get("expiresAt", 0)):
                AUCTION_CONFIRMATIONS.pop(confirm_key, None)
                response = "no pending auction suggestion"
                announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
                return {"ok": False, "error": response, "reply": announce_result}
            if parts[1].lower() in ("no", "n"):
                AUCTION_CONFIRMATIONS.pop(confirm_key, None)
                response = "auction suggestion cancelled"
                announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
                return {"ok": True, "action": "auction.cancelled", "message": response, "reply": announce_result}
            player, matches = character_row(conn, resolved_name)
            if player is None:
                response = "could not resolve your character for auction"
                if matches:
                    response = "no unique character match: " + ", ".join(row["character_name"] for row in matches)
                announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
                return {"ok": False, "error": response, "reply": announce_result}
            dry_run = not chat_auction_enabled()
            result = auction_item(
                conn,
                player,
                pending["searchText"],
                int(pending["count"]),
                int(pending["price"]),
                dry_run=dry_run,
                source=pending["source"],
                explicit_inventory_id=pending.get("explicitInventoryId"),
                explicit_item_id=pending["itemId"],
            )
            AUCTION_CONFIRMATIONS.pop(confirm_key, None)
            if result.get("ok"):
                plan = result.get("plan") or {}
                source_inventory = plan.get("sourceInventoryId")
                if dry_run:
                    source_label = f" from inventory {source_inventory}" if plan.get("source") != "personal" and source_inventory else ""
                    response = f"auction preview: {plan.get('count')}x {plan.get('templateId')}{source_label} for {plan.get('price')}; enable DUNE_CHAT_COMMAND_AUCTION_ENABLED to execute"
                else:
                    order = result.get("order") or {}
                    source_label = f" from inventory {source_inventory}" if source_inventory else ""
                    response = f"auction listed {plan.get('count')}x {plan.get('templateId')}{source_label} for {plan.get('price')}; order {order.get('id')}"
            else:
                response = result.get("error", "auction failed")
            announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
            return result | {"message": response, "dryRun": dry_run, "reply": announce_result}

        try:
            source, explicit_inventory_id, explicit_item_id, search_text, count, price = parse_auction_command_args(parts[1:])
        except ValueError as exc:
            response = str(exc)
            announce_result = maybe_reply(response, reply, target_name=sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        resolved_name = resolve_sender_character(conn, sender_name, sender_fls_id)
        player, matches = character_row(conn, resolved_name)
        if player is None:
            response = "could not resolve your character for auction"
            if matches:
                response = "no unique character match: " + ", ".join(row["character_name"] for row in matches)
            announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
            return {"ok": False, "error": response, "reply": announce_result}
        dry_run = not chat_auction_enabled()
        result = auction_item(conn, player, search_text, count, price, dry_run=dry_run, source=source, explicit_inventory_id=explicit_inventory_id, explicit_item_id=explicit_item_id)
        if result.get("ok"):
            plan = result.get("plan") or {}
            source_inventory = plan.get("sourceInventoryId")
            if dry_run:
                source_label = f" from inventory {source_inventory}" if plan.get("source") != "personal" and source_inventory else ""
                response = f"auction preview: {count}x {plan.get('templateId')}{source_label} for {price}; enable DUNE_CHAT_COMMAND_AUCTION_ENABLED to execute"
            else:
                order = result.get("order") or {}
                source_label = f" from inventory {source_inventory}" if source_inventory else ""
                response = f"auction listed {count}x {plan.get('templateId')}{source_label} for {price}; order {order.get('id')}"
        else:
            response = result.get("error", "auction failed")
            suggestion = result.get("suggestion")
            if suggestion and explicit_item_id is None:
                confirm_key = auction_confirmation_key(sender_name, sender_fls_id, resolved_name)
                AUCTION_CONFIRMATIONS[confirm_key] = {
                    "itemId": int(suggestion["itemId"]),
                    "templateId": suggestion["templateId"],
                    "inventoryId": int(suggestion["inventoryId"]),
                    "source": source,
                    "explicitInventoryId": explicit_inventory_id,
                    "searchText": search_text,
                    "count": count,
                    "price": price,
                    "expiresAt": int(time.time()) + auction_confirmation_ttl(),
                }
                response = (
                    f"no exact match for '{search_text}'. did you mean {suggestion['templateId']} "
                    f"from inventory {suggestion['inventoryId']}? reply &auction yes or &auction no"
                )
        announce_result = maybe_reply(response, reply, target_name=resolved_name or sender_name, target_fls_id=sender_fls_id)
        return result | {"message": response, "dryRun": dry_run, "reply": announce_result}

    allowed, resolved_admin = is_admin(conn, sender_name, sender_fls_id)
    if not allowed:
        response = f"command denied for {resolved_admin or sender_name or sender_fls_id or 'unknown'}"
        announce_result = maybe_reply(response, reply)
        return {"ok": False, "error": response, "reply": announce_result}

    if command == "test":
        response = "f00"
        announce_result = run_announce(response) if reply else None
        return {"ok": True, "action": "test", "message": response, "reply": announce_result}

    if command == "gm":
        global LAST_ANNOUNCE_RESULT
        LAST_ANNOUNCE_RESULT = None
        result = handle_gm_command(conn, parts[1:], resolved_admin, reply=reply)
        if reply and isinstance(result, dict) and "reply" not in result:
            result = result | {"reply": LAST_ANNOUNCE_RESULT}
        return result

    if command in ("where", "loc", "location"):
        if len(parts) != 2:
            response = "usage: &where <playername>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}
        response = f"{target['character_name']} is {target['online_status']} at {format_location(target)}"
        announce_result = maybe_reply(response, reply)
        return {"ok": True, "action": "where", "message": response, "target": dict(target), "reply": announce_result}

    if command in ("kick", "disconnect", "sessionkick"):
        if len(parts) != 2:
            response = "usage: &disconnect <playername>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}

        online = (target["online_status"] or "").lower() == "online"
        route = gm_route_for(conn, target)
        if online:
            try:
                command_text = player_disconnect_command(target["character_name"])
                gm_result = send_player_disconnect(command_text, target["character_name"], resolved_admin, route)
                sent = bool(gm_result.get("ok"))
                response = f"{target['character_name']} disconnect {'sent' if sent else 'preview ready'} via {route} using {command_text.split()[0]}"
                ok = sent
                reason = "disconnect sent" if sent else "player disconnect execution is gated or payload route is not verified"
            except ValueError as exc:
                command_text = ""
                gm_result = {"ok": False, "blocked": True, "error": str(exc)}
                response = str(exc)
                ok = False
                reason = str(exc)
        else:
            response = f"{target['character_name']} is {target['online_status']}; no live session to kick"
            ok = True
            reason = "target is not online"
            command_text = ""
            gm_result = None
        announce_result = maybe_reply(response, reply)
        return {
            "ok": ok,
            "action": "disconnect",
            "blocked": not ok,
            "reason": reason,
            "message": response,
            "commandText": command_text,
            "gm": gm_result,
            "target": compact_character(target),
            "candidateRoutes": kick_candidate_routes(conn, target),
            "reply": announce_result,
        }

    if command == "teleport":
        if len(parts) < 2:
            response = "usage: &teleport <playername>|<slot>|list|set <slot> [name]|replace <slot> [name]|delete <slot>|<playername> <slot>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}

        subcommand = parts[1].lower()
        if subcommand in ("list", "locations"):
            locations = list_teleport_slots()
            response = "teleport slots: " + "; ".join(format_teleport_slot(location) for location in locations[:12]) if locations else "no teleport slots; use &teleport set 0 <name>"
            announce_result = maybe_reply(response, reply)
            return {"ok": True, "action": "teleport.list", "message": response, "locations": locations, "reply": announce_result}

        if subcommand in ("set", "replace"):
            if len(parts) < 3:
                response = f"usage: &teleport {subcommand} <slot> [name]"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            try:
                slot = parse_teleport_slot(parts[2])
            except ValueError as exc:
                response = str(exc)
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            admin, _ = character_row(conn, resolved_admin)
            if admin is None or admin["partition_id"] is None or admin["x"] is None:
                response = f"admin location unavailable for {resolved_admin}"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            name = " ".join(parts[3:]).strip() or None
            location, existing, next_slot = save_teleport_slot(slot, name, admin, resolved_admin, replace=(subcommand == "replace"))
            if existing:
                response = f"{format_teleport_slot_collision(existing)}; next free slot is {next_slot}; use &teleport set {next_slot} or &teleport replace {slot}"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "action": "teleport.set", "error": response, "location": existing, "nextFreeSlot": next_slot, "reply": announce_result}
            response = f"{'replaced' if subcommand == 'replace' else 'saved'} {format_teleport_slot(location)}"
            announce_result = maybe_reply(response, reply)
            return {"ok": True, "action": f"teleport.{subcommand}", "message": response, "location": location, "reply": announce_result}

        if subcommand in ("delete", "rm"):
            if len(parts) != 3:
                response = f"usage: &teleport {subcommand} <slot>"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            try:
                slot = parse_teleport_slot(parts[2])
            except ValueError as exc:
                response = str(exc)
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            location = delete_teleport_slot(slot)
            response = f"deleted {format_teleport_slot(location)}" if location else f"no saved slot {slot}"
            announce_result = maybe_reply(response, reply)
            return {"ok": bool(location), "action": "teleport.delete", "message": response, "location": location, "reply": announce_result}

        if len(parts) == 2:
            try:
                slot = parse_teleport_slot(parts[1])
            except ValueError:
                slot = None
            if slot is not None:
                location = load_teleport_slot(slot)
                if not location:
                    response = f"no saved slot {slot}; use &teleport set {slot} [name]"
                    announce_result = maybe_reply(response, reply)
                    return {"ok": False, "error": response, "reply": announce_result}
                route = gm_route_for_saved_location(conn, location)
                command_text = f"TeleportToExact {location['x']:.3f} {location['y']:.3f} {location['z']:.3f}"
                gm_result = send_gm_command(command_text, resolved_admin, resolved_admin, route)
                response = f"teleport slot {'sent' if gm_result.get('ok') else 'preview ready'} for {format_teleport_slot(location)} via {route}"
                announce_result = maybe_reply(response, reply)
                return {"ok": bool(gm_result.get("ok")), "action": "teleport.slot", "blocked": not bool(gm_result.get("ok")), "message": response, "location": location, "gm": gm_result, "reply": announce_result}

        if len(parts) == 3:
            try:
                slot = parse_teleport_slot(parts[2])
            except ValueError:
                response = "usage: &teleport <playername> <slot>"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            location = load_teleport_slot(slot)
            if not location:
                response = f"no saved slot {slot}; use &teleport set {slot} [name]"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "reply": announce_result}
            target, matches = character_row(conn, parts[1])
            if target is None:
                response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}
            if target["online_status"].lower() != "offline":
                response = f"{target['character_name']} is {target['online_status']}; safe teleport only supports offline targets right now"
                announce_result = maybe_reply(response, reply)
                return {"ok": False, "error": response, "target": dict(target), "reply": announce_result}
            execute = env_bool("DUNE_CHAT_COMMAND_EXECUTE_TELEPORT", False)
            dry_run = env_bool("DUNE_CHAT_COMMAND_DRY_RUN", True) or not execute
            response = f"would move {target['character_name']} to {format_teleport_slot(location)}"
            move_result = None
            if not dry_run:
                move_result = move_offline_player_to_partition(conn, target["fls_id"], location["partitionId"], location["x"], location["y"], location["z"])
                conn.commit()
                response = f"moved {target['character_name']} to {format_teleport_slot(location)} via dune.admin_move_offline_player_to_partition"
            announce_result = maybe_reply(response, reply)
            return {"ok": True, "action": "teleport.player-slot", "dryRun": dry_run, "message": response, "moveResult": move_result, "location": location, "target": {"characterName": target["character_name"], "flsId": target["fls_id"], "status": target["online_status"], "location": compact_location(target)}, "reply": announce_result}

        if len(parts) != 2:
            response = "usage: &teleport <playername>|<slot>|list|set <slot> [name]|replace <slot> [name]|delete <slot>|<playername> <slot>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}

        admin, _ = character_row(conn, resolved_admin)
        if admin is None or admin["partition_id"] is None or admin["x"] is None:
            response = f"admin location unavailable for {resolved_admin}"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}
        if target["online_status"].lower() != "offline":
            response = f"{target['character_name']} is {target['online_status']}; safe teleport only supports offline targets right now"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "target": dict(target), "reply": announce_result}

        execute = env_bool("DUNE_CHAT_COMMAND_EXECUTE_TELEPORT", False)
        dry_run = env_bool("DUNE_CHAT_COMMAND_DRY_RUN", True) or not execute
        response = f"would move {target['character_name']} to {resolved_admin} at {format_location(admin)}"
        move_result = None
        if not dry_run:
            move_result = move_offline_player_to_partition(
                conn,
                target["fls_id"],
                admin["partition_id"],
                admin["x"],
                admin["y"],
                admin["z"],
            )
            conn.commit()
            response = f"moved {target['character_name']} to {resolved_admin} at {format_location(admin)} via dune.admin_move_offline_player_to_partition"
        announce_result = maybe_reply(response, reply)
        return {
            "ok": True,
            "action": "teleport",
            "dryRun": dry_run,
            "message": response,
            "moveResult": move_result,
            "admin": {"characterName": resolved_admin, "location": compact_location(admin)},
            "target": {"characterName": target["character_name"], "flsId": target["fls_id"], "status": target["online_status"], "location": compact_location(target)},
            "reply": announce_result,
        }

    if command in ("armgoto", "armbring"):
        if len(parts) != 2:
            response = f"usage: &{command} <playername>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        action = "goto" if command == "armgoto" else "bring"
        admin, _ = character_row(conn, resolved_admin)
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}
        safe, safety_reason, admin_route, target_route = online_gm_teleport_safety(conn, action, admin, target)
        route = target_route or gm_route_for(conn, target)
        if action == "goto":
            command_text = f"TeleportToPlayer {target['character_name']}"
            target_player = resolved_admin
        else:
            command_text = f"TeleportToExact {admin['x']:.3f} {admin['y']:.3f} {admin['z']:.3f}" if admin and admin.get("x") is not None else "TeleportToExact <admin-x> <admin-y> <admin-z>"
            target_player = target["character_name"]
        if not safe:
            response = f"arm {action} blocked for {target['character_name']}: {safety_reason}"
            announce_result = maybe_reply(response, reply)
            return {
                "ok": False,
                "action": f"arm.{action}",
                "blocked": True,
                "reason": safety_reason,
                "message": response,
                "adminRoute": admin_route,
                "targetRoute": target_route,
                "preview": gm_command_preview(command_text, target_player, resolved_admin, route),
                "reply": announce_result,
            }
        arm = arm_online_gm_teleport(action, resolved_admin, target_player, route, command_text)
        response = f"armed {action} for {target['character_name']} via {route} for {online_gm_teleport_arm_seconds()}s; run &{action} {target['character_name']} to execute once"
        announce_result = maybe_reply(response, reply)
        return {
            "ok": True,
            "action": f"arm.{action}",
            "message": response,
            "arm": arm,
            "adminRoute": admin_route,
            "targetRoute": target_route,
            "preview": gm_command_preview(command_text, target_player, resolved_admin, route),
            "reply": announce_result,
        }

    if command in ("goto", "teleportto", "tpto"):
        if len(parts) != 2:
            response = "usage: &goto <playername>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        admin, _ = character_row(conn, resolved_admin)
        if admin is None:
            response = f"admin player not found: {resolved_admin}"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}
        if target["online_status"].lower() == "online":
            safe, safety_reason, admin_route, target_route = online_gm_teleport_safety(conn, "goto", admin, target)
            route = target_route or gm_route_for(conn, target)
            command_text = f"TeleportToPlayer {target['character_name']}"
            if safe:
                gm_result = send_online_gm_teleport("goto", command_text, resolved_admin, resolved_admin, route)
            else:
                gm_result = {"ok": False, "blocked": True, "reason": safety_reason, "preview": gm_command_preview(command_text, resolved_admin, resolved_admin, route)}
            if gm_result.get("ok"):
                response = f"sent native GM goto for {resolved_admin} to {target['character_name']} via {route}"
            elif not safe:
                response = f"online goto blocked for {target['character_name']}: {safety_reason}"
            else:
                response = f"{target['character_name']} is online at {format_location(target)}; live goto GM envelope is still gated"
            announce_result = maybe_reply(response, reply)
            return {
                "ok": bool(gm_result.get("ok")),
                "action": "goto",
                "blocked": not bool(gm_result.get("ok")),
                "reason": safety_reason if not safe else "online admin teleport requires DUNE_ADMIN_GM_COMMANDS_ENABLED=true, DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true, and DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true",
                "gm": gm_result,
                "candidateCommands": [
                    f"TeleportToPlayer {target['character_name']}",
                    f"TeleportToExact {target['x']} {target['y']} {target['z']}" if target["x"] is not None else "TeleportToExact <x> <y> <z>",
                    f"TravelTo {target['actor_map'] or target['partition_map']}",
                ],
                "message": response,
                "adminRoute": admin_route,
                "targetRoute": target_route,
                "target": {"characterName": target["character_name"], "status": target["online_status"], "location": compact_location(target)},
                "reply": announce_result,
            }
        response = f"{target['character_name']} is offline at {format_location(target)}; live goto still needs native GM command route verification"
        announce_result = maybe_reply(response, reply)
        return {
            "ok": False,
            "action": "goto",
            "blocked": True,
            "reason": "the sender is online when issuing chat commands, so moving the sender needs a live server command",
            "message": response,
            "target": {"characterName": target["character_name"], "status": target["online_status"], "location": compact_location(target)},
            "reply": announce_result,
        }

    if command in ("bring", "summon", "tphere"):
        if len(parts) != 2:
            response = "usage: &bring <playername>"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        admin, _ = character_row(conn, resolved_admin)
        if admin is None or admin["partition_id"] is None or admin["x"] is None:
            response = f"admin location unavailable for {resolved_admin}"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "reply": announce_result}
        target, matches = character_row(conn, parts[1])
        if target is None:
            response = "no unique player match: " + ", ".join(row["character_name"] for row in matches) if matches else "player not found"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "matches": [row["character_name"] for row in matches], "reply": announce_result}
        if target["online_status"].lower() != "online":
            response = f"{target['character_name']} is {target['online_status']}; use &teleport for offline targets"
            announce_result = maybe_reply(response, reply)
            return {"ok": False, "error": response, "target": dict(target), "reply": announce_result}
        safe, safety_reason, admin_route, target_route = online_gm_teleport_safety(conn, "bring", admin, target)
        route = target_route or gm_route_for(conn, target)
        command_text = f"TeleportToExact {admin['x']:.3f} {admin['y']:.3f} {admin['z']:.3f}"
        if safe:
            gm_result = send_online_gm_teleport("bring", command_text, target["character_name"], resolved_admin, route)
        else:
            gm_result = {"ok": False, "blocked": True, "reason": safety_reason, "preview": gm_command_preview(command_text, target["character_name"], resolved_admin, route)}
        if gm_result.get("ok"):
            response = f"sent native GM bring for {target['character_name']} to {resolved_admin} via {route}"
        elif not safe:
            response = f"online bring blocked for {target['character_name']}: {safety_reason}"
        else:
            response = f"{target['character_name']} is online; bring GM envelope is still gated"
        announce_result = maybe_reply(response, reply)
        return {
            "ok": bool(gm_result.get("ok")),
            "action": "bring",
            "blocked": not bool(gm_result.get("ok")),
            "reason": safety_reason if not safe else "online player teleport requires the native live GM command route gates",
            "gm": gm_result,
            "candidateCommands": [command_text, f"TeleportToPlayer {resolved_admin}"],
            "message": response,
            "adminRoute": admin_route,
            "targetRoute": target_route,
            "admin": {"characterName": resolved_admin, "location": compact_location(admin)},
            "target": {"characterName": target["character_name"], "status": target["online_status"], "location": compact_location(target)},
            "reply": announce_result,
        }

    response = f"unknown command: {command}"
    announce_result = maybe_reply(response, reply)
    return {"ok": False, "error": response, "reply": announce_result}


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
    exchanges = split_csv(env("DUNE_CHAT_COMMAND_EXCHANGES", exchange))
    if exchange and exchange not in exchanges:
        exchanges.insert(0, exchange)
    queue = env("DUNE_CHAT_COMMAND_QUEUE", "dash_admin_chat_commands")
    routing_key = env("DUNE_CHAT_COMMAND_ROUTING_KEY", "#")
    bind_routing_keys = split_routing_keys(env("DUNE_CHAT_COMMAND_BIND_ROUTING_KEYS", routing_key))

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    retry_seconds = float(env("DUNE_CHAT_COMMAND_AMQP_RETRY_SECONDS", "5"))
    max_attempts = int(env("DUNE_CHAT_COMMAND_AMQP_CONNECT_ATTEMPTS", "0"))
    attempt = 0
    while True:
        attempt += 1
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=host,
                port=port,
                virtual_host="/",
                credentials=pika.PlainCredentials(user, password),
                ssl_options=pika.SSLOptions(context, host) if tls else None,
                heartbeat=30,
                blocked_connection_timeout=10,
            ))
            break
        except pika.exceptions.AMQPConnectionError as exc:
            if max_attempts and attempt >= max_attempts:
                raise
            print(json.dumps({"ok": False, "amqpConnectAttempt": attempt, "retrySeconds": retry_seconds, "error": str(exc)}, separators=(",", ":")), file=sys.stderr, flush=True)
            time.sleep(retry_seconds)
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=True, auto_delete=False)
    for exchange_name in exchanges:
        for bind_routing_key in dict.fromkeys(bind_routing_keys):
            channel.queue_bind(queue=queue, exchange=exchange_name, routing_key=bind_routing_key)
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

    print(json.dumps({"ok": True, "listening": exchanges, "queue": queue, "routingKeys": bind_routing_keys}, separators=(",", ":")), flush=True)
    channel.basic_consume(queue=queue, on_message_callback=on_message)
    channel.start_consuming()


def healthcheck():
    queue = env("DUNE_CHAT_COMMAND_QUEUE", "dash_admin_chat_commands")
    min_consumers = int(env("DUNE_CHAT_COMMAND_HEALTH_MIN_CONSUMERS", "1"))

    conn = connect_db()
    conn.close()

    host = env("DUNE_CHAT_COMMAND_AMQP_HOST", env("DUNE_ANNOUNCE_HOST_AMQP_HOST", "172.31.240.1"))
    port = int(env("DUNE_CHAT_COMMAND_AMQP_PORT", env("DUNE_ANNOUNCE_HOST_AMQP_PORT", "31982")))
    tls = env_bool("DUNE_CHAT_COMMAND_AMQP_TLS", env_bool("DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS", True))
    user = env_chat_or_announce("DUNE_CHAT_COMMAND_AMQP_USER", "DUNE_ANNOUNCE_CHAT_USER", "")
    password = env_chat_or_announce("DUNE_CHAT_COMMAND_AMQP_PASSWORD", "DUNE_ANNOUNCE_CHAT_PASSWORD", "")
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
    try:
        channel = connection.channel()
        declared = channel.queue_declare(queue=queue, passive=True)
        consumers = declared.method.consumer_count
        messages = declared.method.message_count
        ok = consumers >= min_consumers
        print(json.dumps({
            "ok": ok,
            "queue": queue,
            "consumers": consumers,
            "messages": messages,
            "minConsumers": min_consumers,
        }, separators=(",", ":")), flush=True)
        return 0 if ok else 1
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="Paul in-game chat command listener")
    parser.add_argument("--healthcheck", action="store_true", help="Check DB, RabbitMQ, and the live command queue consumer.")
    parser.add_argument("--dry-run-command", help="Process a command once without consuming RabbitMQ")
    parser.add_argument("--dry-run-spam-message", help="Process one message through spam protection without consuming RabbitMQ")
    parser.add_argument("--dry-run-spam-count", type=int, default=1, help="Number of times to feed --dry-run-spam-message")
    parser.add_argument("--sender-name", default="", help="Sender character name for --dry-run-command")
    parser.add_argument("--sender-fls-id", default="", help="Sender account/user id for --dry-run-command")
    parser.add_argument("--reply", action="store_true", help="Send an in-game reply for --dry-run-command")
    args = parser.parse_args()

    if args.healthcheck:
        return healthcheck()

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
