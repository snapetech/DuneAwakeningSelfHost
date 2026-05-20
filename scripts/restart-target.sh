#!/bin/sh
set -eu

target="${DUNE_RESTART_TARGET:-${1:-}}"
services="${DUNE_RESTART_SERVICES:-}"
action="${DUNE_RESTART_ACTION:-restart}"
phase="${DUNE_RESTART_PHASE:-$action}"

if [ -z "$target" ]; then
  printf 'missing DUNE_RESTART_TARGET\n' >&2
  exit 64
fi
case "$action" in
  restart|shutdown) ;;
  *)
    printf 'invalid DUNE_RESTART_ACTION: %s\n' "$action" >&2
    exit 64
    ;;
esac
case "$phase" in
  restart|shutdown|stop|start) ;;
  *)
    printf 'invalid DUNE_RESTART_PHASE: %s\n' "$phase" >&2
    exit 64
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  if [ ! -S /var/run/docker.sock ]; then
    cat >&2 <<EOF
Docker CLI is not available and /var/run/docker.sock is not mounted.
Target: ${target}
Services: ${services}

Mount the Docker socket for restart-only execution, run this hook from the
Docker host, or replace DUNE_ADMIN_RESTART_COMMAND with a trusted wrapper.
EOF
    exit 78
  fi
  python3 - "$target" "$services" <<'PY'
import json
import os
import socket
import sys
import urllib.parse


target = sys.argv[1]
services_arg = sys.argv[2]
project = os.environ.get("DUNE_RESTART_COMPOSE_PROJECT", "dune_server")
socket_path = os.environ.get("DUNE_RESTART_DOCKER_SOCKET", "/var/run/docker.sock")
dry_run = os.environ.get("DUNE_RESTART_DRY_RUN", "").lower() in ("1", "true", "yes", "on")
action = os.environ.get("DUNE_RESTART_ACTION", "restart")
phase = os.environ.get("DUNE_RESTART_PHASE", action)

default_services = [
    "survival", "overmap", "arrakeen", "harko-village", "testing-hephaestus",
    "testing-carthag", "testing-waterfat", "deep-desert", "proces-verbal",
    "lostharvest-ecolab-a", "lostharvest-ecolab-b", "lostharvest-forgottenlab",
    "art-of-kanly", "dungeon-hephaestus", "dungeon-oldcarthag",
    "faction-outpost-atre", "faction-outpost-hark", "heighliner-dungeon",
    "ecolab-green-089", "ecolab-green-152", "ecolab-green-024",
    "ecolab-green-195", "ecolab-green-136", "overland-m-01",
    "overland-s-04", "overland-s-06", "bandit-fortress", "overland-s-07",
    "overland-s-08", "dungeon-thepit",
    "director", "gateway", "text-router", "rmq-auth-shim",
    "admin-panel",
]
stateful_services = {"postgres", "admin-rmq", "game-rmq"}
allow_stateful = os.environ.get("DUNE_RESTART_ALLOW_STATEFUL", "").lower() in ("1", "true", "yes", "on")

services = services_arg.split() if services_arg else []
if target == "all":
    services = default_services
if not services:
    print(f"no services mapped for target {target}", file=sys.stderr)
    sys.exit(65)
blocked_stateful = sorted(stateful_services.intersection(services))
if blocked_stateful and not allow_stateful:
    print(
        "refusing to restart stateful services without DUNE_RESTART_ALLOW_STATEFUL=true: "
        + " ".join(blocked_stateful),
        file=sys.stderr,
    )
    sys.exit(66)


def decode_chunked(payload):
    decoded = bytearray()
    rest = payload
    while rest:
        line, sep, rest = rest.partition(b"\r\n")
        if not sep:
            raise ValueError("truncated chunked response")
        size = int(line.split(b";", 1)[0], 16)
        if size == 0:
            return bytes(decoded)
        decoded.extend(rest[:size])
        rest = rest[size + 2:]
    return bytes(decoded)


def docker(method, path, body=None):
    data = b"" if body is None else json.dumps(body).encode()
    request = [
        f"{method} {path} HTTP/1.1",
        "Host: docker",
        "Connection: close",
    ]
    if body is not None:
        request.extend(["Content-Type: application/json", f"Content-Length: {len(data)}"])
    request.append("")
    request.append("")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect(socket_path)
    sock.sendall("\r\n".join(request).encode() + data)
    chunks = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    sock.close()
    raw = b"".join(chunks)
    header, _, payload = raw.partition(b"\r\n\r\n")
    header_text = header.decode("iso-8859-1")
    status = int(header_text.split(" ", 2)[1])
    headers = {}
    for line in header_text.split("\r\n")[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip().lower()
    if headers.get("transfer-encoding") == "chunked":
        payload = decode_chunked(payload)
    return status, payload


label_filters = [
    f"label=com.docker.compose.project={project}",
]
for service in services:
    label_filters.append(f"label=com.docker.compose.service={service}")

restarted = []
missing = []
for service in services:
    filters = {
        "label": [
            f"com.docker.compose.project={project}",
            f"com.docker.compose.service={service}",
        ]
    }
    query = urllib.parse.urlencode({"all": "true", "filters": json.dumps(filters)})
    status, payload = docker("GET", f"/containers/json?{query}")
    if status != 200:
        print(f"failed listing containers for {service}: HTTP {status}", file=sys.stderr)
        sys.exit(75)
    containers = json.loads(payload.decode() or "[]")
    if not containers:
        missing.append(service)
        continue
    for container in containers:
        container_id = container["Id"]
        if dry_run:
            restarted.append(service)
            continue
        if phase in ("shutdown", "stop"):
            endpoint = "stop?t=30"
        elif phase == "start":
            endpoint = "start"
        else:
            endpoint = "restart?t=30"
        status, payload = docker("POST", f"/containers/{container_id}/{endpoint}")
        if status not in (204, 304):
            print(f"failed {phase} for {service}: HTTP {status} {payload[:200]!r}", file=sys.stderr)
            sys.exit(75)
        restarted.append(service)

print(json.dumps({"ok": True, "target": target, "action": action, "phase": phase, "dryRun": dry_run, "affected": restarted, "missing": missing}, separators=(",", ":")))
PY
  exit $?
fi

compose_files="${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"
set -- docker compose
old_ifs="$IFS"
IFS=:
for file in $compose_files; do
  set -- "$@" -f "$file"
done
IFS="$old_ifs"
set -- "$@" --env-file "${ENV_FILE:-.env}"

if [ "$target" = "all" ]; then
  services="survival overmap arrakeen harko-village testing-hephaestus testing-carthag testing-waterfat deep-desert proces-verbal lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab art-of-kanly dungeon-hephaestus dungeon-oldcarthag faction-outpost-atre faction-outpost-hark heighliner-dungeon ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-195 ecolab-green-136 overland-m-01 overland-s-04 overland-s-06 bandit-fortress overland-s-07 overland-s-08 dungeon-thepit director gateway text-router rmq-auth-shim admin-panel"
fi

if [ -z "$services" ]; then
  printf 'no services mapped for target %s\n' "$target" >&2
  exit 65
fi

# shellcheck disable=SC2086
case " $services " in
  *" postgres "*|*" admin-rmq "*|*" game-rmq "*)
    if [ "${DUNE_RESTART_ALLOW_STATEFUL:-}" != "true" ] && [ "${DUNE_RESTART_ALLOW_STATEFUL:-}" != "1" ]; then
      printf 'refusing to restart stateful services without DUNE_RESTART_ALLOW_STATEFUL=true: %s\n' "$services" >&2
      exit 66
    fi
    ;;
esac
if [ "${DUNE_RESTART_DRY_RUN:-}" = "true" ] || [ "${DUNE_RESTART_DRY_RUN:-}" = "1" ]; then
  printf '{"ok":true,"target":"%s","action":"%s","phase":"%s","dryRun":true,"services":"%s"}\n' "$target" "$action" "$phase" "$services"
  exit 0
fi
if [ "$phase" = "shutdown" ] || [ "$phase" = "stop" ]; then
  exec "$@" stop -t 30 $services
fi
if [ "$phase" = "start" ]; then
  exec "$@" up -d --force-recreate $services
fi
exec "$@" up -d --force-recreate $services
