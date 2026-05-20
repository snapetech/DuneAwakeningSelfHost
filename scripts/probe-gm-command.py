#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

from dune_gm_command import amqp_connection, build_envelope, candidate_modes, publish_command, publish_command_management


def main():
    parser = argparse.ArgumentParser(description="Probe the native Dune GM command RabbitMQ route with safe commands.")
    parser.add_argument("--route", default="Survival_11", help="Admin RabbitMQ rpc routing key.")
    parser.add_argument("--command", default="PrintPos", help="Command text to send. Keep this harmless until the route is verified.")
    parser.add_argument("--target-player", default="Lukano", help="Target/admin player name for candidate envelopes.")
    parser.add_argument("--admin-player", default="Lukano", help="Admin player name for candidate envelopes.")
    parser.add_argument("--exchange", default="rpc", help="Admin RabbitMQ exchange.")
    parser.add_argument("--mode", action="append", choices=candidate_modes(), help="Envelope mode to send. Repeat to send several. Defaults to every known probe mode.")
    parser.add_argument("--preview", action="store_true", help="Print envelopes without publishing.")
    parser.add_argument("--transport", choices=("amqp", "management"), default="amqp", help="Publish transport. Management uses RabbitMQ HTTP API and cannot wait for replies.")
    parser.add_argument("--wait-response", type=float, default=0, help="Declare an exclusive reply queue and wait this many seconds for native responses.")
    args = parser.parse_args()

    sent = []
    reply_to = None
    response_conn = None
    response_channel = None
    responses = []
    if args.wait_response > 0 and not args.preview:
        response_conn = amqp_connection()
        response_channel = response_conn.channel()
        reply_to = response_channel.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
    for mode in args.mode or candidate_modes():
        if args.preview:
            sent.append({
                "mode": mode,
                "exchange": args.exchange,
                "route": args.route,
                "commandText": args.command,
                "body": build_envelope(mode, args.command, args.target_player, args.admin_player),
            })
            continue
        if args.transport == "management":
            result = publish_command_management(
                args.command,
                args.route,
                target_player=args.target_player,
                admin_player=args.admin_player,
                mode=mode,
                exchange=args.exchange,
            )
        else:
            result = publish_command(
                args.command,
                args.route,
                target_player=args.target_player,
                admin_player=args.admin_player,
                mode=mode,
                exchange=args.exchange,
                app_id="DASH-Probe",
                reply_to=reply_to,
            )
        sent.append(result)
    if response_channel is not None:
        deadline = time.time() + args.wait_response
        while time.time() < deadline:
            method, props, body = response_channel.basic_get(reply_to, auto_ack=True)
            if method:
                try:
                    decoded = body.decode("utf-8")
                except UnicodeDecodeError:
                    decoded = body.hex()
                responses.append({
                    "routingKey": method.routing_key,
                    "correlationId": getattr(props, "correlation_id", None),
                    "type": getattr(props, "type", None),
                    "contentType": getattr(props, "content_type", None),
                    "body": decoded,
                })
            else:
                time.sleep(0.2)
        response_conn.close()
    print(json.dumps({"ok": True, "sent": sent, "responses": responses}, indent=2))


if __name__ == "__main__":
    main()
