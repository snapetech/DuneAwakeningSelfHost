#!/usr/bin/env python3
import argparse
import json
import pathlib
import ssl
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

import pika

from dune_gm_command import amqp_connection, env, env_bool


def game_amqp_connection():
    host = env("DUNE_ANNOUNCE_HOST_AMQP_HOST", env("DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST", "127.0.0.1"))
    port = int(env("DUNE_ANNOUNCE_HOST_AMQP_PORT", env("DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT", env("GAME_RMQ_PUBLIC_PORT", "31982"))))
    tls = env_bool("DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS", True)
    user = env("DUNE_ANNOUNCE_CHAT_USER", "A000000000000001")
    password = env("DUNE_ANNOUNCE_CHAT_PASSWORD", "")
    ssl_options = None
    if tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        ssl_options = pika.SSLOptions(context, host)
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host="/",
            credentials=pika.PlainCredentials(user, password),
            ssl_options=ssl_options,
            heartbeat=0,
            blocked_connection_timeout=10,
        )
    )


def decode_body(body):
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return {"encoding": "hex", "body": body.hex()[:4096], "size": len(body)}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    return {"encoding": "utf-8", "body": text[:4096], "json": parsed, "size": len(body)}


def props_dict(props):
    fields = (
        "content_type",
        "content_encoding",
        "delivery_mode",
        "priority",
        "correlation_id",
        "reply_to",
        "expiration",
        "message_id",
        "timestamp",
        "type",
        "user_id",
        "app_id",
        "cluster_id",
    )
    return {field: getattr(props, field, None) for field in fields if getattr(props, field, None) is not None} | {"headers": getattr(props, "headers", None)}


def main():
    parser = argparse.ArgumentParser(description="Capture RabbitMQ messages without consuming production queues.")
    parser.add_argument("--binding", action="append", default=[], help="Binding as exchange:routing_key. Repeatable.")
    parser.add_argument("--broker", choices=("admin", "game"), default="admin")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--queue-prefix", default="dash.capture")
    args = parser.parse_args()

    bindings = args.binding or ["response:#", "rpc:#", "grant:#", "completions:#", "travel:#", "settingsUpdate:#", "director_respawned:#"]
    conn = game_amqp_connection() if args.broker == "game" else amqp_connection()
    messages = []
    try:
        channel = conn.channel()
        queue = channel.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
        for binding in bindings:
            if ":" in binding:
                exchange, routing_key = binding.split(":", 1)
            else:
                exchange, routing_key = binding, "#"
            channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
        deadline = time.time() + args.seconds
        while time.time() < deadline and len(messages) < args.limit:
            method, props, body = channel.basic_get(queue, auto_ack=True)
            if not method:
                time.sleep(0.1)
                continue
            messages.append(
                {
                    "exchange": method.exchange,
                    "routingKey": method.routing_key,
                    "properties": props_dict(props),
                    **decode_body(body),
                }
            )
    finally:
        conn.close()
    print(json.dumps({"ok": True, "count": len(messages), "messages": messages}, indent=2))


if __name__ == "__main__":
    main()
