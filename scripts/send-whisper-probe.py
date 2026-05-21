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


def chat_payload(message, channel_type, sender_funcom_id, sender_name, target_name, localized_sender=False):
    timestamp = time.strftime("%Y.%m.%d-%H.%M.%S", time.gmtime())
    chat_message = {
        "m_Id": uuid.uuid4().hex.upper(),
        "m_ChannelType": channel_type,
        "m_bUseSpoofedUserName": True,
        "m_SpoofedUserNameFrom": {
            "m_TableId": "/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI" if localized_sender else "",
            "m_Key": "UI/TextChat_Channel_Title_Whispers" if localized_sender else "",
            "m_UnlocalizedName": "" if localized_sender else sender_name,
        },
        "m_FuncomIdFrom": sender_funcom_id,
        "m_UserNameTo": target_name,
        "m_Message": {
            "m_UnlocalizedMessage": message,
            "m_LocalizedMessage": {"m_TableId": "", "m_Key": "", "m_FormatArgs": []},
        },
        "m_TimeStamp": timestamp,
        "m_OriginLocation": {"X": 0.0, "Y": 0.0, "Z": 0.0},
        "m_HasSeenMessage": False,
    }
    return {"content": json.dumps(chat_message, separators=(",", ":")), "Type": "TextChat"}


def make_properties(kind, include_user_id, headers=None):
    kwargs = {
        "content_type": "Content",
        "delivery_mode": 1,
        "timestamp": int(time.time()),
        "type": kind,
        "message_id": secrets.token_urlsafe(16),
    }
    if include_user_id:
        kwargs["user_id"] = env("DUNE_ANNOUNCE_CHAT_USER", "A000000000000001")
    if headers:
        kwargs["headers"] = headers
    return pika.BasicProperties(**kwargs)


def main():
    parser = argparse.ArgumentParser(description="Send labeled Dune whisper/chat probe variants.")
    parser.add_argument("--target-name", default="SamplePlayer")
    parser.add_argument("--target-fls-id", default="TEST_FLS_ID")
    parser.add_argument("--message-prefix", default="whisper probe")
    parser.add_argument("--sender-name", default=env("DUNE_ANNOUNCE_CHAT_SPOOF_NAME", "Paul"))
    parser.add_argument("--sender-funcom-id", default=env("DUNE_ANNOUNCE_CHAT_FUNCOM_ID", "ADMIN#00001"))
    parser.add_argument("--bind-target-queue", action="store_true")
    parser.add_argument("--include-user-id", action="store_true")
    parser.add_argument("--send-intercept", action="store_true")
    args = parser.parse_args()

    target_queue = f"{args.target_fls_id}_queue"
    direct_variants = [
        ("DW-map-fls", "chat.whispers", args.target_fls_id, "Map", "text_chat"),
        ("DW-whisper-fls", "chat.whispers", args.target_fls_id, "Whisper", "text_chat"),
        ("DW-private-fls", "chat.whispers", args.target_fls_id, "Private", "text_chat"),
        ("DW-map-name", "chat.whispers", args.target_name, "Map", "text_chat"),
        ("DQ-private", "", target_queue, "Private", "text_chat", False),
        ("DQ-whisper", "", target_queue, "Whisper", "text_chat", False),
        ("DQ-whispers", "", target_queue, "Whispers", "text_chat", False),
        ("DQ-whispers-localized", "", target_queue, "Whispers", "text_chat", True),
        ("DQ-map", "", target_queue, "Map", "text_chat"),
        ("DQ-type-whisper", "", target_queue, "Whisper", "whisper"),
        ("DQ-type-private", "", target_queue, "Private", "private"),
    ]
    intercept_variants = [
        ("IRW-map-fls", "chat.intercept", args.target_fls_id, "Map", "text_chat"),
        ("IRW-whisper-fls", "chat.intercept", args.target_fls_id, "Whisper", "text_chat"),
        ("IRW-private-fls", "chat.intercept", args.target_fls_id, "Private", "text_chat"),
    ]
    variants = direct_variants + (intercept_variants if args.send_intercept else [])

    connection = pika.BlockingConnection(connection_params())
    channel = connection.channel()
    results = []
    try:
        if args.bind_target_queue:
            for routing_key in (args.target_fls_id, args.target_name, target_queue):
                channel.queue_bind(queue=target_queue, exchange="chat.whispers", routing_key=routing_key)
                results.append({"step": "bind", "exchange": "chat.whispers", "queue": target_queue, "routingKey": routing_key, "ok": True})

        for index, variant in enumerate(variants, start=1):
            if len(variant) == 5:
                label, exchange, routing_key, channel_type, prop_type = variant
                localized_sender = False
            else:
                label, exchange, routing_key, channel_type, prop_type, localized_sender = variant
            message = f"{args.message_prefix} {label}"
            headers = None
            if exchange == "chat.intercept":
                headers = {"redirect_exchange": b"chat.whispers"}
            payload = chat_payload(message, channel_type, args.sender_funcom_id, args.sender_name, args.target_name, localized_sender=localized_sender)
            try:
                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                    properties=make_properties(prop_type, args.include_user_id, headers=headers),
                    mandatory=False,
                )
                results.append({
                    "step": "publish",
                    "label": label,
                    "exchange": exchange or "<default>",
                    "routingKey": routing_key,
                    "channelType": channel_type,
                    "propertyType": prop_type,
                    "message": message,
                    "ok": True,
                })
            except Exception as exc:
                results.append({
                    "step": "publish",
                    "label": label,
                    "exchange": exchange or "<default>",
                    "routingKey": routing_key,
                    "error": str(exc),
                    "ok": False,
                })
            time.sleep(0.15)
    finally:
        connection.close()

    print(json.dumps({"ok": any(item.get("ok") for item in results), "targetQueue": target_queue, "results": results}, separators=(",", ":")))
    return 0 if any(item.get("ok") for item in results) else 75


if __name__ == "__main__":
    raise SystemExit(main())
