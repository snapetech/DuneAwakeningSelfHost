#!/bin/sh
set -eu

message="${DUNE_ANNOUNCE_MESSAGE:-${1:-}}"
restart_at="${DUNE_ANNOUNCE_RESTART_AT:-}"
job_id="${DUNE_ANNOUNCE_JOB_ID:-manual}"

if [ -z "$message" ]; then
  printf 'missing DUNE_ANNOUNCE_MESSAGE\n' >&2
  exit 64
fi

python3 - "$message" "$restart_at" "$job_id" <<'PY'
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


message, restart_at, job_id = sys.argv[1:4]
rmq_url = os.environ.get("DUNE_ANNOUNCE_RMQ_URL", "http://admin-rmq:15672").rstrip("/")
rmq_user = os.environ.get("DUNE_ANNOUNCE_RMQ_USER", "guest")
rmq_password = os.environ.get("DUNE_ANNOUNCE_RMQ_PASSWORD", "guest")
exchange = os.environ.get("DUNE_ANNOUNCE_RMQ_EXCHANGE", "rpc")
targets = [
    item.strip()
    for item in os.environ.get("DUNE_ANNOUNCE_RMQ_ROUTING_KEYS", "Survival_11").split(",")
    if item.strip()
]
duration = int(os.environ.get("DUNE_ANNOUNCE_DURATION_SECONDS", "12"))
title = os.environ.get("DUNE_ANNOUNCE_TITLE", "Maintenance")
command = os.environ.get("DUNE_ANNOUNCE_COMMAND_NAME", "ServiceBroadcast")
template = os.environ.get("DUNE_ANNOUNCE_PAYLOAD_TEMPLATE", "")
mode = os.environ.get("DUNE_ANNOUNCE_PAYLOAD_MODE", "command-payload")
reply_to = os.environ.get("DUNE_ANNOUNCE_RMQ_REPLY_TO", "")
correlation_id = os.environ.get("DUNE_ANNOUNCE_RMQ_CORRELATION_ID", job_id)
app_id = os.environ.get("DUNE_ANNOUNCE_RMQ_APP_ID", "")
user_id = os.environ.get("DUNE_ANNOUNCE_RMQ_USER_ID", "")

if not targets:
    print("missing DUNE_ANNOUNCE_RMQ_ROUTING_KEYS", file=sys.stderr)
    sys.exit(64)

context = {
    "command": command,
    "title": title,
    "message": message,
    "duration": duration,
    "restart_at": restart_at,
    "job_id": job_id,
    "timestamp": int(time.time()),
}

service_payload = {
    "m_Title": title,
    "m_Message": message,
    "m_DurationInSeconds": duration,
    "m_MessageTargets": [],
    "m_RestartAt": restart_at,
    "m_JobId": job_id,
}

if template:
    body = template
    for key, value in context.items():
        body = body.replace("{{" + key + "}}", json.dumps(value)[1:-1] if isinstance(value, str) else str(value))
else:
    if mode == "command-payload":
        envelope = {"Command": command, "Payload": service_payload}
    elif mode == "server-command":
        envelope = {"ServerCommand": command, "Payload": service_payload}
    elif mode == "message-type":
        envelope = {"MessageType": command, "Payload": service_payload}
    elif mode == "flat-command":
        envelope = {"Command": command, **service_payload}
    elif mode == "jsonrpc-object":
        envelope = {"jsonrpc": "2.0", "method": command, "params": service_payload, "id": job_id}
    elif mode == "jsonrpc-array":
        envelope = {"jsonrpc": "2.0", "method": command, "params": [service_payload], "id": job_id}
    elif mode == "payload-only":
        envelope = service_payload
    else:
        print(f"unknown DUNE_ANNOUNCE_PAYLOAD_MODE: {mode}", file=sys.stderr)
        sys.exit(64)
    body = json.dumps(
        envelope,
        separators=(",", ":"),
    )

credentials = base64.b64encode(f"{rmq_user}:{rmq_password}".encode()).decode()
headers = {
    "Authorization": f"Basic {credentials}",
    "Content-Type": "application/json",
}

ok = True
results = []
for routing_key in targets:
    properties = {
        "content_type": "application/json",
        "delivery_mode": 1,
        "timestamp": int(time.time()),
        "type": command,
        "correlation_id": correlation_id,
    }
    if reply_to:
        properties["reply_to"] = reply_to
    if app_id:
        properties["app_id"] = app_id
    if user_id:
        properties["user_id"] = user_id
    payload = {
        "properties": properties,
        "routing_key": routing_key,
        "payload": body,
        "payload_encoding": "string",
    }
    url = f"{rmq_url}/api/exchanges/{urllib.parse.quote('/', safe='')}/{urllib.parse.quote(exchange, safe='')}/publish"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        ok = False
        results.append({"routingKey": routing_key, "ok": False, "error": f"HTTP {exc.code}"})
        continue
    except Exception as exc:
        ok = False
        results.append({"routingKey": routing_key, "ok": False, "error": str(exc)})
        continue
    routed = bool(result.get("routed"))
    ok = ok and routed
    results.append({"routingKey": routing_key, "ok": routed})

print(json.dumps({"ok": ok, "mode": mode, "exchange": exchange, "targets": results}, separators=(",", ":")))
sys.exit(0 if ok else 75)
PY
