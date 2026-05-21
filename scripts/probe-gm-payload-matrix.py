#!/usr/bin/env python3
import argparse
import itertools
import json
import pathlib
import secrets
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

import pika

from dune_gm_command import amqp_connection


def json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def build_bodies(command_text, target_player, admin_player):
    command, _, args = command_text.partition(" ")
    return {
        "jsonrpc-method-command-array": {"jsonrpc": "2.0", "method": command, "params": [args] if args else [], "id": None},
        "jsonrpc-method-command-string": {"jsonrpc": "2.0", "method": command, "params": args, "id": None},
        "jsonrpc-servercommand-array": {"jsonrpc": "2.0", "method": "ServerCommand", "params": [command_text], "id": None},
        "jsonrpc-servercommand-object": {"jsonrpc": "2.0", "method": "ServerCommand", "params": {"Command": command_text}, "id": None},
        "jsonrpc-senddune-array": {"jsonrpc": "2.0", "method": "SendDuneServerCommand", "params": [command_text, target_player, admin_player], "id": None},
        "jsonrpc-serverexec-array": {"jsonrpc": "2.0", "method": "ServerExec", "params": [target_player, command_text], "id": None},
        "jsonrpc-serverexecrpc-array": {"jsonrpc": "2.0", "method": "ServerExecRPC", "params": [target_player, command_text], "id": None},
        "command-commandtext": {"Command": "ServerCommand", "CommandText": command_text, "TargetPlayer": target_player, "AdminPlayer": admin_player},
        "command-direct": {"Command": command, "Args": args, "TargetPlayer": target_player, "AdminPlayer": admin_player},
        "command-params": {"Command": "SendDuneServerCommand", "Params": [command_text, target_player, admin_player]},
        "serverexec-object": {"Command": "ServerExec", "TargetPlayer": target_player, "ConsoleCommand": command_text, "AdminPlayer": admin_player},
        "serverexecrpc-object": {"Command": "ServerExecRPC", "TargetPlayer": target_player, "ConsoleCommand": command_text, "AdminPlayer": admin_player},
        "ue-function-object": {"Function": command, "Parameters": [args] if args else []},
        "ue-function-commandline": {"Function": "ServerCommand", "Parameters": [command_text]},
        "dw-api-args": {"Api": command, "Args": [args] if args else []},
        "dw-api-arguments": {"Api": command, "Arguments": [args] if args else []},
        "dw-method-params": {"Method": command, "Params": [args] if args else []},
        "dw-name-arguments": {"Name": command, "Arguments": [args] if args else []},
        "dw-commandline": {"CommandLine": command_text},
        "raw-array-one": [command_text],
        "raw-array-target-command": [target_player, command_text],
        "raw-array-command-target-admin": [command_text, target_player, admin_player],
        "raw-string": command_text,
        "raw-serverexec-string": f"ServerExec {target_player} {command_text}",
    }


def serialize_body(value):
    if isinstance(value, str):
        return value.encode("utf-8"), "text/plain"
    return json_bytes(value), "application/json"


def bind_safely(channel, queue, exchange, routing_key):
    try:
        channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
        return True
    except Exception:
        return False


def publish_one(channel, exchange, routing_key, body, content_type, amqp_type, reply_to, user_id, tag):
    props = pika.BasicProperties(
        content_type=content_type,
        delivery_mode=1,
        timestamp=int(time.time()),
        type=amqp_type or None,
        reply_to=reply_to or None,
        correlation_id=tag,
        message_id=tag,
        app_id="DASH-GM-Matrix",
        user_id=user_id or None,
        headers={"dash_gm_matrix": True, "dash_nonce": secrets.token_hex(4), "dash_tag": tag},
    )
    channel.basic_publish(exchange=exchange, routing_key=routing_key, body=body, properties=props, mandatory=True)


def drain(channel, queue, seconds):
    deadline = time.time() + seconds
    responses = []
    while time.time() < deadline:
        method, props, body = channel.basic_get(queue, auto_ack=True)
        if method:
            try:
                decoded = body.decode("utf-8")
            except UnicodeDecodeError:
                decoded = body.hex()
            responses.append(
                {
                    "exchange": method.exchange,
                    "routingKey": method.routing_key,
                    "correlationId": getattr(props, "correlation_id", None),
                    "type": getattr(props, "type", None),
                    "contentType": getattr(props, "content_type", None),
                    "body": decoded[:2000],
                }
            )
        else:
            time.sleep(0.1)
    return responses


def main():
    parser = argparse.ArgumentParser(description="Probe Dune GM/server-command RabbitMQ payload variants with harmless commands.")
    parser.add_argument("--route", required=True, help="Admin RPC routing key, for example SH_Arrakeen3.")
    parser.add_argument("--queue", required=True, help="Admin default-exchange queue, for example SH_Arrakeen3_queue.")
    parser.add_argument("--game-server-queue", default="", help="Optional game-RMQ server queue name.")
    parser.add_argument("--command", default="PrintAllowedCommands")
    parser.add_argument("--target-player", default="Lukano")
    parser.add_argument("--admin-player", default="Lukano")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--wait", type=float, default=1.0)
    parser.add_argument("--include-game-rmq", action="store_true")
    args = parser.parse_args()

    bodies = build_bodies(args.command, args.target_player, args.admin_player)
    content_type_modes = ["native", "application/json", ""]
    amqp_types = ["json_rpc", "json-rpc", "request", ""]
    targets = [("admin", "rpc", args.route), ("admin", "", args.queue)]
    if args.include_game_rmq and args.game_server_queue:
        targets.append(("game", "", args.game_server_queue))

    sent = []
    responses = []
    admin_conn = amqp_connection()
    admin_ch = admin_conn.channel()
    reply_queue = admin_ch.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
    for key in (reply_queue, f"response.{args.route}", args.route):
        bind_safely(admin_ch, reply_queue, "response", key)

    game_conn = None
    game_ch = None

    combos = list(itertools.product(targets, bodies.items(), content_type_modes, amqp_types))
    if args.limit:
        combos = combos[: args.limit]

    for (broker, exchange, routing_key), (body_name, body_value), content_type_mode, amqp_type in combos:
        tag = f"gm-matrix-{uuid.uuid4().hex[:10]}"
        body, native_content_type = serialize_body(body_value)
        content_type = native_content_type if content_type_mode == "native" else content_type_mode
        try:
            if broker == "admin":
                publish_one(admin_ch, exchange, routing_key, body, content_type, amqp_type, reply_queue, "", tag)
            else:
                if game_conn is None:
                    game_conn = amqp_connection()
                    game_ch = game_conn.channel()
                publish_one(game_ch, exchange, routing_key, body, content_type, amqp_type, reply_queue, "", tag)
            sent.append(
                {
                    "tag": tag,
                    "broker": broker,
                    "exchange": exchange or "<default>",
                    "routingKey": routing_key,
                    "body": body_name,
                    "contentType": content_type,
                    "amqpType": amqp_type,
                }
            )
        except Exception as exc:
            sent.append(
                {
                    "tag": tag,
                    "broker": broker,
                    "exchange": exchange or "<default>",
                    "routingKey": routing_key,
                    "body": body_name,
                    "contentType": content_type,
                    "amqpType": amqp_type,
                    "error": str(exc),
                }
            )
        responses.extend(drain(admin_ch, reply_queue, args.wait))

    responses.extend(drain(admin_ch, reply_queue, max(args.wait, 2.0)))
    if game_conn is not None:
        game_conn.close()
    admin_conn.close()
    print(json.dumps({"ok": True, "command": args.command, "sent": sent, "responses": responses}, indent=2))


if __name__ == "__main__":
    main()
