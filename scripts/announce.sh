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
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


message, restart_at, job_id = sys.argv[1:4]


def read_env_file(path):
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


file_env = {}
for env_path in ("/workspace/.env", os.path.join(os.getcwd(), ".env")):
    file_env.update(read_env_file(env_path))


def env(name, default=""):
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    return file_env.get(name, default)


def env_bool(name, default=False):
    value = env(name, "true" if default else "false").lower()
    return value in ("1", "true", "yes", "on")


def split_csv(value):
    items = []
    for item in value.split(","):
        item = item.strip()
        if item in ("<empty>", "empty", "EMPTY"):
            items.append("")
        elif item:
            items.append(item)
    return items


default_url = "http://game-rmq:15672" if os.path.exists("/workspace/.env") else "http://127.0.0.1:15673"
rmq_url = env("DUNE_ANNOUNCE_GAME_RMQ_MANAGEMENT_URL", default_url).rstrip("/")
sender_user = env("DUNE_ANNOUNCE_CHAT_USER", "A000000000000001")
sender_password = env("DUNE_ANNOUNCE_CHAT_PASSWORD", "dash-admin-test")
sender_funcom_id = env("DUNE_ANNOUNCE_CHAT_FUNCOM_ID", "ADMIN#00001")
sender_name = env("DUNE_ANNOUNCE_CHAT_SPOOF_NAME", "DASH Admin")
exchange = env("DUNE_ANNOUNCE_CHAT_EXCHANGE", "chat.map")
routing_keys = split_csv(env("DUNE_ANNOUNCE_CHAT_ROUTING_KEYS", "HaggaBasin.0,Survival_1.dim_0,<empty>"))
channel_type = env("DUNE_ANNOUNCE_CHAT_CHANNEL", "Map")
use_spoof_name = env_bool("DUNE_ANNOUNCE_CHAT_USE_SPOOF_NAME", False)
bind_online_queues = env_bool("DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES", True)
queue_pattern = re.compile(env("DUNE_ANNOUNCE_CHAT_QUEUE_PATTERN", r"^[0-9A-Fa-f]{16}_queue$"))
target_queues = split_csv(env("DUNE_ANNOUNCE_CHAT_TARGET_QUEUES", ""))

if not routing_keys:
    print("missing DUNE_ANNOUNCE_CHAT_ROUTING_KEYS", file=sys.stderr)
    sys.exit(64)

credentials = base64.b64encode(f"{sender_user}:{sender_password}".encode()).decode()
headers = {
    "Authorization": f"Basic {credentials}",
    "Content-Type": "application/json",
}
vhost = urllib.parse.quote("/", safe="")


def request_json(method, path, body=None, timeout=8):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{rmq_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode()
    return json.loads(text) if text else {}


def safe_request(method, path, body=None):
    try:
        return request_json(method, path, body), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, str(exc)


bound_queues = []
bind_errors = []
if bind_online_queues:
    queues, error = safe_request("GET", f"/api/queues/{vhost}")
    if error:
        bind_errors.append({"step": "listQueues", "error": error})
    else:
        seen = set(target_queues)
        for queue in queues:
            name = queue.get("name", "")
            if queue_pattern.match(name) and int(queue.get("consumers") or 0) > 0:
                seen.add(name)
        for queue_name in sorted(seen):
            if not queue_name:
                continue
            for routing_key in routing_keys:
                path = (
                    f"/api/bindings/{vhost}/e/{urllib.parse.quote(exchange, safe='')}"
                    f"/q/{urllib.parse.quote(queue_name, safe='')}"
                )
                _, error = safe_request("POST", path, {"routing_key": routing_key, "arguments": {}})
                if error:
                    bind_errors.append({"queue": queue_name, "routingKey": routing_key, "error": error})
                else:
                    bound_queues.append({"queue": queue_name, "routingKey": routing_key})

timestamp = time.strftime("%Y.%m.%d-%H.%M.%S", time.gmtime())
chat_message = {
    "m_Id": uuid.uuid4().hex.upper(),
    "m_ChannelType": channel_type,
    "m_bUseSpoofedUserName": use_spoof_name,
    "m_SpoofedUserNameFrom": {
        "m_TableId": "",
        "m_Key": "",
        "m_UnlocalizedName": sender_name if use_spoof_name else "",
    },
    "m_FuncomIdFrom": sender_funcom_id,
    "m_UserNameTo": "",
    "m_Message": {
        "m_UnlocalizedMessage": message,
        "m_LocalizedMessage": {"m_TableId": "", "m_Key": "", "m_FormatArgs": []},
    },
    "m_Timestamp": timestamp,
    "m_OriginLocation": {"X": 0.0, "Y": 0.0, "Z": 0.0},
    "m_HasSeenMessage": False,
}
payload = {"content": json.dumps(chat_message, separators=(",", ":")), "Type": "TextChat"}

results = []
for routing_key in routing_keys:
    properties = {
        "content_type": "Content",
        "delivery_mode": 1,
        "timestamp": int(time.time()),
        "type": "text_chat",
        "user_id": sender_user,
        "message_id": secrets.token_urlsafe(16),
    }
    body = {
        "properties": properties,
        "routing_key": routing_key,
        "payload": json.dumps(payload, separators=(",", ":")),
        "payload_encoding": "string",
    }
    path = f"/api/exchanges/{vhost}/{urllib.parse.quote(exchange, safe='')}/publish"
    response, error = safe_request("POST", path, body)
    routed = bool(response and response.get("routed"))
    results.append({"routingKey": routing_key, "ok": routed, "error": error})

ok = any(item["ok"] for item in results)
print(json.dumps({
    "ok": ok,
    "transport": "chat.map",
    "exchange": exchange,
    "sender": sender_user,
    "routingKeys": results,
    "boundQueues": bound_queues,
    "bindErrors": bind_errors,
    "jobId": job_id,
    "restartAt": restart_at,
}, separators=(",", ":")))
sys.exit(0 if ok else 75)
PY
