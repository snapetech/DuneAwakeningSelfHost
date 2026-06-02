#!/usr/bin/env python3
import argparse
import itertools
import json
import pathlib
import secrets
import ssl
import sys
import time
import uuid

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


def json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def auth_token_value():
    return env("DUNE_GM_SERVER_COMMAND_AUTH_TOKEN", env("DUNE_SERVER_COMMANDS_AUTH_TOKEN", ""))


def service_broadcast_payload(command_text, broadcast_type):
    return {
        "BroadcastType": broadcast_type,
        "BroadcastPayload": {
            "ServerCommand": command_text,
        },
    }


def native_notification(command_payload, original_id, name, sender="fls", version=1, include_payload_json=True):
    body = {
        "EventNamespace": "notifications",
        "Name": name,
        "OriginalId": original_id,
        "OriginalTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Payload": command_payload,
        "SenderId": sender,
        "SenderID": sender,
        "Sender": sender,
        "From": sender,
        "Source": sender,
        "MessageSenderId": sender,
        "Version": version,
    }
    if include_payload_json:
        body["PayloadJSON"] = json.dumps(command_payload, separators=(",", ":"))
    return body


def notification_envelope(event_namespace, payload, original_id, name=None, sender=None, version=None):
    payload_json = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
    envelope = {
        "EventNamespace": event_namespace,
        "OriginalId": original_id,
        "OriginalTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "PayloadJSON": payload_json,
    }
    if name is not None:
        envelope["Name"] = name
    if sender is not None:
        envelope.update(
            {
                "SenderId": sender,
                "SenderID": sender,
                "Sender": sender,
                "From": sender,
                "Source": sender,
                "MessageSenderId": sender,
            }
        )
    if version is not None:
        envelope["Version"] = version
    return envelope


def engine_service_notification(event_namespace, event_name, event_data, sender=None, version=None):
    event_data_json = event_data if isinstance(event_data, str) else json.dumps(event_data, separators=(",", ":"))
    envelope = {
        "EntityId": sender or "",
        "EntityType": "fls" if sender else "",
        "EventData": event_data_json,
        "EventName": event_name,
        "EventNamespace": event_namespace,
    }
    if sender is not None:
        envelope["EventSettings"] = {
            "SenderId": sender,
            "SenderID": sender,
            "Sender": sender,
            "From": sender,
            "Source": sender,
            "MessageSenderId": sender,
        }
    if version is not None:
        envelope["Version"] = version
    return envelope


def build_bodies(command_text, target_player, admin_player):
    command, _, args = command_text.partition(" ")
    auth_token = auth_token_value()
    service_payloads = {
        "serverbroadcast-clientauth": service_broadcast_payload(command_text, "ServerBroadcastClientAuthenticated"),
        "serverbroadcast": service_broadcast_payload(command_text, "ServerBroadcast"),
        "generic-broadcast": service_broadcast_payload(command_text, "Generic"),
    }
    service_payload_json = {
        name: json.dumps(value, separators=(",", ":"))
        for name, value in service_payloads.items()
    }
    notification_payloads = {}
    if auth_token:
        for payload_name, raw_content in (
            ("clientauth", service_payload_json["serverbroadcast-clientauth"]),
            ("serverbroadcast", service_payload_json["serverbroadcast"]),
        ):
            notification_payloads[f"{payload_name}-content-auth"] = {
                "AuthToken": auth_token,
                "Content": raw_content,
            }
            notification_payloads[f"{payload_name}-rawcontent-auth"] = {
                "AuthToken": auth_token,
                "RawContent": raw_content,
            }
            notification_payloads[f"{payload_name}-servercommandstoken-content"] = {
                "ServerCommandsAuthToken": auth_token,
                "Content": raw_content,
            }
    base = {
        "jsonrpc-method-command-array": {"jsonrpc": "2.0", "method": command, "params": [args] if args else [], "id": None},
        "jsonrpc-id-method-command-array": {"jsonrpc": "2.0", "method": command, "params": [args] if args else [], "id": "dash-gm-probe"},
        "jsonrpc-method-command-string": {"jsonrpc": "2.0", "method": command, "params": args, "id": None},
        "jsonrpc-id-method-command-string": {"jsonrpc": "2.0", "method": command, "params": [args] if args else [], "id": "dash-gm-probe"},
        "jsonrpc-servercommand-array": {"jsonrpc": "2.0", "method": "ServerCommand", "params": [command_text], "id": None},
        "jsonrpc-id-servercommand-array": {"jsonrpc": "2.0", "method": "ServerCommand", "params": [command_text], "id": "dash-gm-probe"},
        "jsonrpc-servercommand-object": {"jsonrpc": "2.0", "method": "ServerCommand", "params": {"Command": command_text}, "id": None},
        "jsonrpc-id-servercommand-object": {"jsonrpc": "2.0", "method": "ServerCommand", "params": {"Command": command_text}, "id": "dash-gm-probe"},
        "jsonrpc-senddune-array": {"jsonrpc": "2.0", "method": "SendDuneServerCommand", "params": [command_text, target_player, admin_player], "id": None},
        "jsonrpc-id-senddune-array": {"jsonrpc": "2.0", "method": "SendDuneServerCommand", "params": [command_text, target_player, admin_player], "id": "dash-gm-probe"},
        "jsonrpc-id-senddune-one": {"jsonrpc": "2.0", "method": "SendDuneServerCommand", "params": [command_text], "id": "dash-gm-probe"},
        "jsonrpc-serverexec-array": {"jsonrpc": "2.0", "method": "ServerExec", "params": [target_player, command_text], "id": None},
        "jsonrpc-id-serverexec-array": {"jsonrpc": "2.0", "method": "ServerExec", "params": [target_player, command_text], "id": "dash-gm-probe"},
        "jsonrpc-serverexecrpc-array": {"jsonrpc": "2.0", "method": "ServerExecRPC", "params": [target_player, command_text], "id": None},
        "jsonrpc-id-serverexecrpc-array": {"jsonrpc": "2.0", "method": "ServerExecRPC", "params": [target_player, command_text], "id": "dash-gm-probe"},
        "jsonrpc-id-servicebroadcast-array": {"jsonrpc": "2.0", "method": "ServiceBroadcast", "params": [command_text], "id": "dash-gm-probe"},
        "jsonrpc-id-servicebroadcast-servercommand-object": {
            "jsonrpc": "2.0",
            "method": "ServiceBroadcast",
            "params": [{"ServerCommand": command_text}],
            "id": "dash-gm-probe",
        },
        "jsonrpc-id-servicebroadcast-command-object": {
            "jsonrpc": "2.0",
            "method": "ServiceBroadcast",
            "params": [{"Command": command_text}],
            "id": "dash-gm-probe",
        },
        "jsonrpc-id-servicebroadcast-payload-object": {
            "jsonrpc": "2.0",
            "method": "ServiceBroadcast",
            "params": [{"Payload": {"ServerCommand": command_text}}],
            "id": "dash-gm-probe",
        },
        "servercommand-object": {"ServerCommand": command_text},
        "servercommand-command-object": {"ServerCommand": command, "Args": args},
        "dune-server-command-object": {"DuneServerCommand": command_text},
        "broadcast-clientauth-object": service_payloads["serverbroadcast-clientauth"],
        "broadcast-server-object": service_payloads["serverbroadcast"],
        "broadcast-generic-object": service_payloads["generic-broadcast"],
        "payloadjson-broadcast-clientauth": {"PayloadJSON": service_payload_json["serverbroadcast-clientauth"]},
        "payloadjson-broadcast-server": {"PayloadJSON": service_payload_json["serverbroadcast"]},
        "payloadjson-broadcast-generic": {"PayloadJSON": service_payload_json["generic-broadcast"]},
        "payloadtype-payloadjson-clientauth": {
            "PayloadType": "ServiceBroadcast",
            "PayloadJSON": service_payload_json["serverbroadcast-clientauth"],
        },
        "payloadtype-payloadjson-serverbroadcast": {
            "PayloadType": "ServiceBroadcast",
            "PayloadJSON": service_payload_json["serverbroadcast"],
        },
        "servicebroadcast-servercommand-object": {"ServiceBroadcast": {"ServerCommand": command_text}},
        "servicebroadcast-command-object": {"ServiceBroadcast": {"Command": command_text}},
        "servicebroadcast-payloadjson-clientauth": {
            "ServiceBroadcast": {
                "PayloadJSON": service_payload_json["serverbroadcast-clientauth"],
            }
        },
        "servicebroadcast-payloadjson-server": {
            "ServiceBroadcast": {
                "PayloadJSON": service_payload_json["serverbroadcast"],
            }
        },
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
    if auth_token:
        native_service_broadcasts = {
            "clientauth": service_payloads["serverbroadcast-clientauth"],
            "serverbroadcast": service_payloads["serverbroadcast"],
            "generic": service_payloads["generic-broadcast"],
            "servercommand-only": {"ServerCommand": command_text},
        }
        for broadcast_name, broadcast_payload in native_service_broadcasts.items():
            for auth_field in ("AuthToken", "ServerCommandsAuthToken"):
                command_payload = {
                    auth_field: auth_token,
                    "Content": json.dumps(broadcast_payload, separators=(",", ":")),
                }
                base[f"native-derived-notification-{broadcast_name}-{auth_field.lower()}-content"] = native_notification(
                    command_payload,
                    f"dash-gm-{uuid.uuid4().hex[:10]}",
                    "ServerRequestEventNotifications",
                    include_payload_json=True,
                )
                object_payload = {
                    auth_field: auth_token,
                    "Content": broadcast_payload,
                }
                base[f"native-derived-notification-{broadcast_name}-{auth_field.lower()}-object-content"] = native_notification(
                    object_payload,
                    f"dash-gm-{uuid.uuid4().hex[:10]}",
                    "ServerRequestEventNotifications",
                    include_payload_json=True,
                )
                base[f"native-derived-notification-{broadcast_name}-{auth_field.lower()}-payload-only"] = native_notification(
                    object_payload,
                    f"dash-gm-{uuid.uuid4().hex[:10]}",
                    "NotificationSystemHandleServerMessages",
                    include_payload_json=False,
                )
    for payload_name, payload in notification_payloads.items():
        payload_json = json.dumps(payload, separators=(",", ":"))
        base[f"notification-servercommand-payloadjson-{payload_name}"] = notification_envelope(
            "ServerCommand",
            payload_json,
            f"dash-gm-{uuid.uuid4().hex[:10]}",
        )
        base[f"notification-servicebroadcast-payloadjson-{payload_name}"] = notification_envelope(
            "ServiceBroadcast",
            payload_json,
            f"dash-gm-{uuid.uuid4().hex[:10]}",
        )
        envelope_with_payload = notification_envelope(
            "ServerCommand",
            payload_json,
            f"dash-gm-{uuid.uuid4().hex[:10]}",
        )
        envelope_with_payload["Payload"] = payload
        base[f"notification-servercommand-payload-object-{payload_name}"] = envelope_with_payload
        for event_namespace, notification_name in (
            ("notifications", "ServerRequestEventNotifications"),
            ("ServerRequestEventNotifications", "ServerCommand"),
            ("ServerCommand", "ServerRequestEventNotifications"),
            ("ServiceBroadcast", "ServerRequestEventNotifications"),
        ):
            base[f"notification-native-fls-{event_namespace.lower()}-{notification_name.lower()}-{payload_name}"] = notification_envelope(
                event_namespace,
                payload_json,
                f"dash-gm-{uuid.uuid4().hex[:10]}",
                name=notification_name,
                sender="fls",
                version=1,
            )
        base[f"engine-service-fls-notifications-serverrequesteventnotifications-{payload_name}"] = engine_service_notification(
            "notifications",
            "ServerRequestEventNotifications",
            payload,
            sender="fls",
            version=1,
        )
        base[f"engine-service-fls-notifications-serverrequesteventnotifications-payloadjson-{payload_name}"] = engine_service_notification(
            "notifications",
            "ServerRequestEventNotifications",
            notification_envelope(
                "notifications",
                payload_json,
                f"dash-gm-{uuid.uuid4().hex[:10]}",
                name="ServerRequestEventNotifications",
                sender="fls",
                version=1,
            ),
            sender="fls",
            version=1,
        )
    if auth_token:
        auth_fields = {
            "AuthToken": auth_token,
            "AuthorizationToken": auth_token,
            "ServerCommandsAuthToken": auth_token,
        }
        for body_name, body_value in list(base.items()):
            if isinstance(body_value, dict):
                with_auth = dict(body_value)
                with_auth.update(auth_fields)
                base[f"authfields-{body_name}"] = with_auth
    wrapped = {}
    for body_name, body_value in base.items():
        if isinstance(body_value, str):
            json_payload = body_value
            payload = body_value
        else:
            json_payload = json.dumps(body_value, separators=(",", ":"))
            payload = body_value
        wrapped[f"payload-{body_name}"] = {"Payload": payload}
        wrapped[f"payload-correlation-{body_name}"] = {"CorrelationId": "", "Payload": payload}
        wrapped[f"jsonpayload-{body_name}"] = {"jsonPayload": json_payload}
        wrapped[f"attributejsonpayload-{body_name}"] = {"AttributeJsonPayload": json_payload}
        wrapped[f"callpayload-{body_name}"] = {"callPayload": payload}
        wrapped[f"dispatchpayload-{body_name}"] = {"DispatchPayload": payload}
    base.update(wrapped)
    return base


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
    auth_token = auth_token_value()
    headers = {"dash_gm_matrix": True, "dash_nonce": secrets.token_hex(4), "dash_tag": tag}
    if auth_token:
        headers.update(
            {
                "AuthToken": auth_token,
                "AuthorizationToken": auth_token,
                "ServerCommandsAuthToken": auth_token,
                "X-Auth-Token": auth_token,
            }
        )
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
        headers=headers,
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
    parser.add_argument("--target-player", default="SamplePlayer")
    parser.add_argument("--admin-player", default="SamplePlayer")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--wait", type=float, default=1.0)
    parser.add_argument("--include-game-rmq", action="store_true")
    parser.add_argument("--include-game-bindings", action="store_true", help="Also publish to known game exchange bindings for the server queue.")
    parser.add_argument("--game-rpc-route", default="", help="Optional game-RMQ rpc routing key, usually the world name.")
    parser.add_argument("--only-broker", choices=("admin", "game", "all"), default="all")
    parser.add_argument("--target-kind", choices=("all", "rpc", "direct"), default="all", help="Limit admin/game publishes to exchange RPC routes or direct queue routes.")
    parser.add_argument("--user-id", default="", help="AMQP user_id property to send. Leave empty to omit.")
    parser.add_argument("--body", action="append", default=[], help="Only send these exact body names. Repeatable.")
    parser.add_argument("--body-contains", action="append", default=[], help="Only send body names containing these substrings. Repeatable.")
    parser.add_argument("--amqp-type", action="append", default=[], help="Only send these AMQP type values. Repeatable; use empty for omitted type.")
    parser.add_argument("--content-type", action="append", default=[], help="Only send these content type modes: native, application/json, empty. Repeatable.")
    args = parser.parse_args()

    bodies = build_bodies(args.command, args.target_player, args.admin_player)
    if args.body:
        bodies = {
            name: value
            for name, value in bodies.items()
            if name in args.body
        }
    if args.body_contains:
        bodies = {
            name: value
            for name, value in bodies.items()
            if any(pattern in name for pattern in args.body_contains)
        }
    content_type_modes = args.content_type or ["native", "application/json", ""]
    content_type_modes = ["" if mode == "empty" else mode for mode in content_type_modes]
    amqp_types = args.amqp_type or ["json_rpc", "json-rpc", "request", ""]
    amqp_types = ["" if mode == "empty" else mode for mode in amqp_types]
    targets = [("admin", "rpc", args.route), ("admin", "", args.queue)]
    if args.include_game_rmq and args.game_server_queue:
        targets.append(("game", "", args.game_server_queue))
        if args.game_rpc_route:
            targets.append(("game", "rpc", args.game_rpc_route))
        if args.include_game_bindings and args.game_server_queue.startswith("queue.server."):
            server_id = args.game_server_queue.removeprefix("queue.server.")
            targets.extend(
                [
                    ("game", "heartbeats", server_id),
                    ("game", "heartbeats", "notifications"),
                    ("game", "notifications", "PlayerOnlineState"),
                ]
            )
    if args.only_broker != "all":
        targets = [target for target in targets if target[0] == args.only_broker]
    if args.target_kind == "rpc":
        targets = [target for target in targets if target[1] == "rpc"]
    elif args.target_kind == "direct":
        targets = [target for target in targets if target[1] == ""]

    sent = []
    responses = []
    admin_conn = None
    admin_ch = None
    reply_queue = None
    if any(target[0] == "admin" for target in targets):
        admin_conn = amqp_connection()
        admin_ch = admin_conn.channel()
        reply_queue = admin_ch.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
        bind_safely(admin_ch, reply_queue, "rpc", reply_queue)
        for key in (reply_queue, f"response.{args.route}", args.route):
            bind_safely(admin_ch, reply_queue, "response", key)

    game_conn = None
    game_ch = None
    game_reply_queue = None

    combos = [
        (target, body_item, content_type_mode, amqp_type)
        for body_item, content_type_mode, amqp_type, target in itertools.product(bodies.items(), content_type_modes, amqp_types, targets)
    ]
    if args.limit:
        combos = combos[: args.limit]

    for (broker, exchange, routing_key), (body_name, body_value), content_type_mode, amqp_type in combos:
        tag = f"gm-matrix-{uuid.uuid4().hex[:10]}"
        body, native_content_type = serialize_body(body_value)
        content_type = native_content_type if content_type_mode == "native" else content_type_mode
        try:
            if broker == "admin":
                publish_one(admin_ch, exchange, routing_key, body, content_type, amqp_type, reply_queue, args.user_id, tag)
            else:
                if game_conn is None:
                    game_conn = game_amqp_connection()
                    game_ch = game_conn.channel()
                    game_reply_queue = game_ch.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
                    bind_safely(game_ch, game_reply_queue, "rpc", game_reply_queue)
                publish_one(game_ch, exchange, routing_key, body, content_type, amqp_type, game_reply_queue, args.user_id, tag)
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
        if admin_ch is not None and reply_queue is not None:
            responses.extend(drain(admin_ch, reply_queue, args.wait))
        if game_ch is not None and game_reply_queue is not None:
            responses.extend(drain(game_ch, game_reply_queue, args.wait))

    if admin_ch is not None and reply_queue is not None:
        responses.extend(drain(admin_ch, reply_queue, max(args.wait, 2.0)))
    if game_ch is not None and game_reply_queue is not None:
        responses.extend(drain(game_ch, game_reply_queue, max(args.wait, 2.0)))
    if game_conn is not None:
        game_conn.close()
    if admin_conn is not None:
        admin_conn.close()
    print(json.dumps({"ok": True, "command": args.command, "sent": sent, "responses": responses}, indent=2))


if __name__ == "__main__":
    main()
