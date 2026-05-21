#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import secrets
import ssl
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

import pika


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
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    return FILE_ENV.get(name, default)


def env_bool(name, default=False):
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def connection_params():
    host = env("DUNE_ANNOUNCE_HOST_AMQP_HOST", env("DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST", "127.0.0.1"))
    port = int(env("DUNE_ANNOUNCE_HOST_AMQP_PORT", env("DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT", env("GAME_RMQ_PUBLIC_PORT", "31982"))))
    tls = env_bool("DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS", True)
    user = env("DUNE_ANNOUNCE_CHAT_USER", "A000000000000001")
    password = env("DUNE_ANNOUNCE_CHAT_PASSWORD", "")
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host="/",
        credentials=pika.PlainCredentials(user, password),
        ssl_options=pika.SSLOptions(context, host) if tls else None,
        heartbeat=0,
        blocked_connection_timeout=10,
    )


def chat_payload(message, channel_type, sender_funcom_id, sender_name, user_name_to, origin):
    timestamp = time.strftime("%Y.%m.%d-%H.%M.%S", time.gmtime())
    chat_message = {
        "m_Id": uuid.uuid4().hex.upper(),
        "m_ChannelType": channel_type,
        "m_bUseSpoofedUserName": True,
        "m_SpoofedUserNameFrom": {
            "m_TableId": "",
            "m_Key": "",
            "m_UnlocalizedName": sender_name,
        },
        "m_FuncomIdFrom": sender_funcom_id,
        "m_UserNameTo": user_name_to,
        "m_Message": {
            "m_UnlocalizedMessage": message,
            "m_LocalizedMessage": {"m_TableId": "", "m_Key": "", "m_FormatArgs": []},
        },
        "m_Timestamp": timestamp,
        "m_OriginLocation": {"X": origin[0], "Y": origin[1], "Z": origin[2]},
        "m_HasSeenMessage": False,
    }
    return {"content": json.dumps(chat_message, separators=(",", ":")), "Type": "TextChat"}


def make_properties(include_user_id, redirect_exchange=""):
    kwargs = {
        "content_type": "Content",
        "delivery_mode": 1,
        "timestamp": int(time.time()),
        "type": "text_chat",
        "message_id": secrets.token_urlsafe(16),
    }
    if include_user_id:
        kwargs["user_id"] = env("DUNE_ANNOUNCE_CHAT_USER", "A000000000000001")
    if redirect_exchange:
        kwargs["headers"] = {"redirect_exchange": redirect_exchange.encode("utf-8")}
    return pika.BasicProperties(**kwargs)


def main():
    parser = argparse.ArgumentParser(description="Send labeled Dune chat channel probe variants.")
    parser.add_argument("--target-name", default="Lukano")
    parser.add_argument("--target-fls-id", default="6FF6498F4074E3DE")
    parser.add_argument("--message-prefix", default="channel probe")
    parser.add_argument("--sender-name", default=env("DUNE_ANNOUNCE_CHAT_SPOOF_NAME", "Paul"))
    parser.add_argument("--sender-funcom-id", default=env("DUNE_ANNOUNCE_CHAT_FUNCOM_ID", "ADMIN#00001"))
    parser.add_argument("--origin", default="0,0,0", help="Origin as X,Y,Z for proximity payloads.")
    parser.add_argument("--bind-target-queue", action="store_true")
    parser.add_argument("--include-user-id", action="store_true")
    parser.add_argument("--guild-id", default="1")
    parser.add_argument("--faction-id", default="3")
    parser.add_argument("--party-id", default="")
    args = parser.parse_args()

    origin = tuple(float(item.strip()) for item in args.origin.split(",", 2))
    if len(origin) != 3:
        raise SystemExit("--origin must be X,Y,Z")

    target_queue = f"{args.target_fls_id}_queue"
    variants = [
        ("direct-proximity-hagga", "chat.proximity", "HaggaBasin.0", "Proximity", ""),
        ("direct-proximity-survival", "chat.proximity", "Survival_1.dim_0", "Proximity", ""),
        ("intercept-proximity-hagga", "chat.intercept", "HaggaBasin.0", "Proximity", "chat.proximity"),
        ("intercept-proximity-fls", "chat.intercept", args.target_fls_id, "Proximity", "chat.proximity"),
        ("direct-guild", f"chat.guild.{args.guild_id}", "", "Guild", ""),
        ("intercept-guild", "chat.intercept", "", "Guild", f"chat.guild.{args.guild_id}"),
        ("direct-faction", f"chat.faction.{args.faction_id}", "", "Faction", ""),
        ("intercept-faction", "chat.intercept", "", "Faction", f"chat.faction.{args.faction_id}"),
    ]
    if args.party_id:
        variants.extend([
            ("direct-party", f"chat.party.{args.party_id}", "", "Party", ""),
            ("intercept-party", "chat.intercept", "", "Party", f"chat.party.{args.party_id}"),
        ])

    connection = pika.BlockingConnection(connection_params())
    channel = connection.channel()
    results = []
    try:
        if args.bind_target_queue:
            for exchange, routing_key in (
                ("chat.proximity", "HaggaBasin.0"),
                ("chat.proximity", "Survival_1.dim_0"),
                (f"chat.guild.{args.guild_id}", ""),
                (f"chat.faction.{args.faction_id}", ""),
            ):
                try:
                    channel.queue_bind(queue=target_queue, exchange=exchange, routing_key=routing_key)
                    results.append({"step": "bind", "exchange": exchange, "queue": target_queue, "routingKey": routing_key, "ok": True})
                except Exception as exc:
                    results.append({"step": "bind", "exchange": exchange, "queue": target_queue, "routingKey": routing_key, "ok": False, "error": str(exc)})
            if args.party_id:
                exchange = f"chat.party.{args.party_id}"
                try:
                    channel.exchange_declare(exchange=exchange, exchange_type="fanout", durable=False, auto_delete=False, passive=False)
                    channel.queue_bind(queue=target_queue, exchange=exchange, routing_key="")
                    results.append({"step": "bind", "exchange": exchange, "queue": target_queue, "routingKey": "", "ok": True})
                except Exception as exc:
                    results.append({"step": "bind", "exchange": exchange, "queue": target_queue, "routingKey": "", "ok": False, "error": str(exc)})

        for label, exchange, routing_key, channel_type, redirect_exchange in variants:
            message = f"{args.message_prefix} {label}"
            payload = chat_payload(message, channel_type, args.sender_funcom_id, args.sender_name, args.target_name, origin)
            try:
                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                    properties=make_properties(args.include_user_id, redirect_exchange),
                    mandatory=False,
                )
                results.append({
                    "step": "publish",
                    "label": label,
                    "exchange": exchange,
                    "routingKey": routing_key,
                    "channelType": channel_type,
                    "redirectExchange": redirect_exchange,
                    "message": message,
                    "ok": True,
                })
            except Exception as exc:
                results.append({"step": "publish", "label": label, "exchange": exchange, "routingKey": routing_key, "ok": False, "error": str(exc)})
            time.sleep(0.15)
    finally:
        connection.close()

    print(json.dumps({"ok": any(item.get("ok") for item in results), "targetQueue": target_queue, "results": results}, separators=(",", ":")))
    return 0 if any(item.get("ok") for item in results) else 75


if __name__ == "__main__":
    raise SystemExit(main())
