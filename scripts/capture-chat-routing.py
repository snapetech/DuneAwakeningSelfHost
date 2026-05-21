#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import ssl
import sys
import time

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


def split_csv(value):
    out = []
    for item in value.split(","):
        item = item.strip()
        if item:
            out.append(item)
    return out


def decode_body(body):
    try:
        outer = json.loads(body.decode("utf-8"))
    except Exception:
        return {"raw": body.decode("utf-8", errors="replace")}
    decoded = {"outer": outer}
    content = outer.get("content")
    if isinstance(content, str):
        try:
            decoded["content"] = json.loads(content)
        except Exception:
            decoded["contentRaw"] = content
    return decoded


def decode_header_value(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [decode_header_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): decode_header_value(item) for key, item in value.items()}
    return value


def main():
    parser = argparse.ArgumentParser(description="Capture Dune chat RabbitMQ payloads on temporary tap queues.")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--exchanges", default="chat.intercept,chat.map,chat.proximity,chat.whispers")
    parser.add_argument("--routing-key", action="append", dest="routing_keys", default=[])
    args = parser.parse_args()

    host = env("DUNE_ANNOUNCE_HOST_AMQP_HOST", env("DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST", "127.0.0.1"))
    port = int(env("DUNE_ANNOUNCE_HOST_AMQP_PORT", env("DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT", env("GAME_RMQ_PUBLIC_PORT", "31982"))))
    tls = env_bool("DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS", True)
    user = env("DUNE_ANNOUNCE_CHAT_USER", "A000000000000001")
    password = env("DUNE_ANNOUNCE_CHAT_PASSWORD", "")
    routing_keys = args.routing_keys or ["#", "", "HaggaBasin.0", "Survival_1.dim_0", "TEST_FLS_ID", "SamplePlayer"]

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host="/",
            credentials=pika.PlainCredentials(user, password),
            ssl_options=pika.SSLOptions(context, host) if tls else None,
            heartbeat=0,
            blocked_connection_timeout=10,
        )
    )
    channel = connection.channel()
    deadline = time.time() + args.seconds

    def callback(ch, method, properties, body):
        record = {
            "ts": time.time(),
            "exchange": method.exchange,
            "routingKey": method.routing_key,
            "properties": {
                "contentType": properties.content_type,
                "type": properties.type,
                "userId": properties.user_id,
                "messageId": properties.message_id,
                "timestamp": properties.timestamp,
                "headers": decode_header_value(properties.headers or {}),
            },
            "body": decode_body(body),
        }
        print(json.dumps(record, default=str, separators=(",", ":")), flush=True)

    queues = []
    for exchange in split_csv(args.exchanges):
        result = channel.queue_declare(queue="", exclusive=True, auto_delete=True)
        queue_name = result.method.queue
        queues.append(queue_name)
        for routing_key in routing_keys:
            try:
                channel.queue_bind(queue=queue_name, exchange=exchange, routing_key=routing_key)
            except Exception as exc:
                print(json.dumps({"exchange": exchange, "routingKey": routing_key, "bindError": str(exc)}), flush=True)
        channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)

    print(json.dumps({"ok": True, "capturingSeconds": args.seconds, "queues": queues, "routingKeys": routing_keys}), flush=True)
    while time.time() < deadline:
        connection.process_data_events(time_limit=1)
    connection.close()


if __name__ == "__main__":
    main()
