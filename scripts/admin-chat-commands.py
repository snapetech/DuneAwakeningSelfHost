#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import shlex
import ssl
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

import pika
import psycopg2
import psycopg2.extras


ROOT = pathlib.Path(__file__).resolve().parents[1]


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
            select ps.character_name, acc.user as fls_id
            from dune.accounts acc
            left join dune.player_state ps on ps.account_id = acc.id
            where acc.user = %s
            order by ps.character_name nulls last
            limit 1
            """,
            (fls_id,),
        )
        return cur.fetchone()


def is_admin(conn, sender_name, sender_fls_id):
    names = {item.lower() for item in split_csv(env("DUNE_CHAT_COMMAND_ADMINS", "Lukano"))}
    fls_ids = set(split_csv(env("DUNE_CHAT_COMMAND_ADMIN_FLS_IDS", "6FF6498F4074E3DE")))
    resolved = None
    if sender_fls_id:
        resolved = character_by_fls_id(conn, sender_fls_id)
    resolved_name = (resolved or {}).get("character_name") or sender_name or ""
    allowed = bool((resolved_name and resolved_name.lower() in names) or (sender_fls_id and sender_fls_id in fls_ids))
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


def format_location(row):
    label = row["partition_label"] or row["actor_map"] or "unknown"
    if row["x"] is None:
        return f"{label} position unknown"
    return f"{label} x={row['x']:.1f} y={row['y']:.1f} z={row['z']:.1f}"


def run_announce(message):
    command = env("DUNE_CHAT_COMMAND_REPLY_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", "/workspace/scripts/announce.sh"))
    wrapped = f"[DASH] {message}"
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
        if target["online_status"].lower() == "online":
            response = f"{target['character_name']} is online at {format_location(target)}; live goto needs native GM command route verification"
            if reply:
                run_announce(response)
            return {
                "ok": False,
                "action": "goto",
                "blocked": True,
                "reason": "online admin teleport requires the native live GM command route",
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
    parser = argparse.ArgumentParser(description="DASH in-game chat command listener")
    parser.add_argument("--dry-run-command", help="Process a command once without consuming RabbitMQ")
    parser.add_argument("--sender-name", default="", help="Sender character name for --dry-run-command")
    parser.add_argument("--sender-fls-id", default="", help="Sender account/user id for --dry-run-command")
    parser.add_argument("--reply", action="store_true", help="Send an in-game reply for --dry-run-command")
    args = parser.parse_args()

    if args.dry_run_command:
        with connect_db() as conn:
            result = handle_command(conn, args.dry_run_command, args.sender_name, args.sender_fls_id, reply=args.reply)
        print(json.dumps(result, default=str, indent=2))
        return
    consume_forever()


if __name__ == "__main__":
    main()
