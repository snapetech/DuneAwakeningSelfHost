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
  restart|shutdown|stop|update|start) ;;
  *)
    printf 'invalid DUNE_RESTART_PHASE: %s\n' "$phase" >&2
    exit 64
    ;;
esac

steam_update_enabled() {
  case "${DUNE_RESTART_CHECK_STEAM_UPDATE:-true}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

run_steam_update_check() {
  env_file="${ENV_FILE:-.env}"
  if ! steam_update_enabled; then
    printf 'Steam package update check disabled by DUNE_RESTART_CHECK_STEAM_UPDATE\n'
    return 0
  fi
  if [ ! -x ./scripts/check-steam-update.sh ]; then
    printf 'Steam package update check skipped: scripts/check-steam-update.sh is missing or not executable\n' >&2
    return 0
  fi
  if ./scripts/check-steam-update.sh "$env_file"; then
    return 0
  fi
  rc=$?
  if [ "$rc" -eq 1 ]; then
    printf 'Steam package update available; loading official images and updating DUNE_IMAGE_TAG\n'
    ./scripts/load-images.sh
    ./scripts/check-steam-update.sh "$env_file" --write-env
    return 0
  fi
  printf 'Steam package update check could not determine a safe tag; continuing without changing DUNE_IMAGE_TAG\n' >&2
  return 0
}

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
import shlex
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
host_workspace = os.environ.get("DUNE_RESTART_HOST_WORKSPACE") or os.environ.get("DUNE_ANNOUNCE_HOST_WORKSPACE", "")
compose_image = os.environ.get("DUNE_RESTART_COMPOSE_IMAGE", "docker:27-cli")
use_host_compose = os.environ.get("DUNE_RESTART_USE_HOST_COMPOSE", "true").lower() in ("1", "true", "yes", "on")
compose_files = [item for item in os.environ.get("COMPOSE_FILES", "compose.yaml:compose.allmaps.yaml").split(":") if item]
env_file = os.environ.get("ENV_FILE", ".env")

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


def request_timeout(path):
    if "/wait" in path:
        return int(os.environ.get("DUNE_RESTART_COMPOSE_TIMEOUT_SECONDS", os.environ.get("DUNE_ADMIN_RESTART_COMMAND_TIMEOUT_SECONDS", "1800")))
    if "/stop" in path or "/restart" in path:
        return int(os.environ.get("DUNE_RESTART_DOCKER_STOP_TIMEOUT_SECONDS", "120"))
    return int(os.environ.get("DUNE_RESTART_DOCKER_API_TIMEOUT_SECONDS", "30"))


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
    sock.settimeout(request_timeout(path))
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


def remove_container(container_id):
    docker("DELETE", f"/containers/{container_id}?force=true&v=true")


def docker_logs(container_id):
    status, payload = docker("GET", f"/containers/{container_id}/logs?stdout=1&stderr=1")
    if status != 200:
        return f"failed reading helper logs: HTTP {status}"
    if payload and payload[0] in (1, 2) and len(payload) >= 8 and payload[1:4] == b"\x00\x00\x00":
        decoded = bytearray()
        offset = 0
        while offset + 8 <= len(payload):
            size = int.from_bytes(payload[offset + 4:offset + 8], "big")
            offset += 8
            decoded.extend(payload[offset:offset + size])
            offset += size
        payload = bytes(decoded)
    return payload.decode("utf-8", errors="replace").strip()


def run_host_compose(services):
    if not host_workspace:
        print(
            "DUNE_RESTART_HOST_WORKSPACE or DUNE_ANNOUNCE_HOST_WORKSPACE is required for host Compose recreate",
            file=sys.stderr,
        )
        sys.exit(78)
    compose_command = ["docker", "compose"]
    for file_name in compose_files:
        compose_command.extend(["-f", file_name])
    compose_command.extend(["--env-file", env_file, "up", "-d", "--force-recreate", "--no-deps"])
    compose_command.extend(services)
    shell_command = (
        "set -e; "
        + "if [ -x /workspace/scripts/seed-gateway-neighbor.sh ]; then "
        + "apk add --no-cache bash iproute2 util-linux sudo >/dev/null; "
        + "/workspace/scripts/seed-gateway-neighbor.sh || true; "
        + "fi; "
        + " ".join(shlex.quote(part) for part in compose_command)
        + "; if [ -x /workspace/scripts/seed-gateway-neighbor.sh ]; then "
        + "/workspace/scripts/seed-gateway-neighbor.sh; "
        + "fi; "
        + "if [ -x /workspace/scripts/restart-post-start-health.sh ]; then "
        + "/workspace/scripts/restart-post-start-health.sh; "
        + "elif [ -x /workspace/scripts/verify-rmq-auth-path.sh ]; then "
        + "/workspace/scripts/verify-rmq-auth-path.sh; "
        + "fi"
    )
    body = {
        "Image": compose_image,
        "WorkingDir": host_workspace,
        "Cmd": ["sh", "-lc", shell_command],
        "Env": [
            f"COMPOSE_PROJECT_NAME={project}",
            "DOCKER_HOST=unix:///var/run/docker.sock",
        ],
        "HostConfig": {
            "AutoRemove": False,
            "NetworkMode": "host",
            "PidMode": "host",
            "Privileged": True,
            "Binds": [
                f"{socket_path}:/var/run/docker.sock",
                f"{host_workspace}:{host_workspace}",
                f"{host_workspace}:/workspace",
            ],
        },
        "Labels": {
            "com.snapetech.dune.role": "admin-restart-compose",
            "com.snapetech.dune.restart_job": os.environ.get("DUNE_RESTART_JOB_ID", ""),
        },
    }
    helper_name = "dune-admin-restart-compose-" + (os.environ.get("DUNE_RESTART_JOB_ID", "manual") or "manual")
    status, payload = docker("POST", "/containers/create?name=" + urllib.parse.quote(helper_name), body)
    if status == 409:
        status, payload = docker("POST", "/containers/create", body)
    if status != 201:
        print(f"failed creating Compose helper: HTTP {status} {payload[:500]!r}", file=sys.stderr)
        sys.exit(75)
    container_id = json.loads(payload.decode())["Id"]
    try:
        status, payload = docker("POST", f"/containers/{container_id}/start")
        if status not in (204, 304):
            print(f"failed starting Compose helper: HTTP {status} {payload[:500]!r}", file=sys.stderr)
            sys.exit(75)
        status, payload = docker("POST", f"/containers/{container_id}/wait")
        if status != 200:
            print(f"failed waiting for Compose helper: HTTP {status} {payload[:500]!r}", file=sys.stderr)
            sys.exit(75)
        result = json.loads(payload.decode() or "{}")
        exit_code = int(result.get("StatusCode", 1))
        logs = docker_logs(container_id)
        if exit_code != 0:
            print(logs, file=sys.stderr)
            sys.exit(exit_code)
        return {"ok": True, "composeImage": compose_image, "hostWorkspace": host_workspace, "command": compose_command, "seedGatewayNeighbor": True, "output": logs}
    finally:
        remove_container(container_id)


def steam_update_enabled():
    return os.environ.get("DUNE_RESTART_CHECK_STEAM_UPDATE", "true").lower() in ("1", "true", "yes", "on")


def read_env_value(path, key):
    candidates = []
    if os.path.isabs(path):
        candidates.append(path)
    if host_workspace:
        candidates.append(os.path.join(host_workspace, path))
        candidates.append(os.path.join("/workspace", path))
    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    name, value = stripped.split("=", 1)
                    if name.strip() == key:
                        return value.strip().strip("\"'")
        except OSError:
            continue
    return ""


def run_host_update_check():
    if not steam_update_enabled():
        return {"ok": True, "skipped": True, "reason": "DUNE_RESTART_CHECK_STEAM_UPDATE disabled"}
    if not host_workspace:
        return {"ok": True, "skipped": True, "warning": "host workspace is not configured"}
    shell_command = (
        "set -e; "
        "if [ ! -x ./scripts/check-steam-update.sh ]; then "
        "echo 'Steam package update check skipped: scripts/check-steam-update.sh is missing or not executable' >&2; "
        "exit 0; "
        "fi; "
        "set +e; "
        f"./scripts/check-steam-update.sh {shlex.quote(env_file)}; "
        "rc=$?; "
        "set -e; "
        "if [ \"$rc\" = 0 ]; then exit 0; fi; "
        "if [ \"$rc\" = 1 ]; then "
        "echo 'Steam package update available; loading official images and updating DUNE_IMAGE_TAG'; "
        "./scripts/load-images.sh; "
        f"./scripts/check-steam-update.sh {shlex.quote(env_file)} --write-env; "
        "exit 0; "
        "fi; "
        "echo 'Steam package update check could not determine a safe tag; continuing without changing DUNE_IMAGE_TAG' >&2; "
        "exit 0"
    )
    binds = [
        f"{socket_path}:/var/run/docker.sock",
        f"{host_workspace}:{host_workspace}",
        f"{host_workspace}:/workspace",
    ]
    steam_dir = read_env_value(env_file, "DUNE_STEAM_SERVER_DIR")
    if steam_dir and os.path.isabs(steam_dir):
        binds.append(f"{steam_dir}:{steam_dir}:ro")
    body = {
        "Image": compose_image,
        "WorkingDir": host_workspace,
        "Cmd": ["sh", "-lc", shell_command],
        "Env": [
            "DOCKER_HOST=unix:///var/run/docker.sock",
        ],
        "HostConfig": {
            "AutoRemove": False,
            "NetworkMode": "host",
            "Privileged": True,
            "Binds": binds,
        },
        "Labels": {
            "com.snapetech.dune.role": "admin-restart-steam-update",
            "com.snapetech.dune.restart_job": os.environ.get("DUNE_RESTART_JOB_ID", ""),
        },
    }
    helper_name = "dune-admin-steam-update-" + (os.environ.get("DUNE_RESTART_JOB_ID", "manual") or "manual")
    status, payload = docker("POST", "/containers/create?name=" + urllib.parse.quote(helper_name), body)
    if status == 409:
        status, payload = docker("POST", "/containers/create", body)
    if status != 201:
        print(f"failed creating Steam update helper: HTTP {status} {payload[:500]!r}", file=sys.stderr)
        sys.exit(75)
    container_id = json.loads(payload.decode())["Id"]
    try:
        status, payload = docker("POST", f"/containers/{container_id}/start")
        if status not in (204, 304):
            print(f"failed starting Steam update helper: HTTP {status} {payload[:500]!r}", file=sys.stderr)
            sys.exit(75)
        status, payload = docker("POST", f"/containers/{container_id}/wait")
        if status != 200:
            print(f"failed waiting for Steam update helper: HTTP {status} {payload[:500]!r}", file=sys.stderr)
            sys.exit(75)
        result = json.loads(payload.decode() or "{}")
        exit_code = int(result.get("StatusCode", 1))
        logs = docker_logs(container_id)
        if exit_code != 0:
            print(logs, file=sys.stderr)
            sys.exit(exit_code)
        return {"ok": True, "output": logs}
    finally:
        remove_container(container_id)


if phase == "update":
    if dry_run:
        print(json.dumps({"ok": True, "target": target, "action": action, "phase": phase, "dryRun": True, "steamUpdate": True}, separators=(",", ":")))
        sys.exit(0)
    result = run_host_update_check() if use_host_compose else {"ok": True, "skipped": True, "warning": "host Compose helper disabled"}
    print(json.dumps({"ok": True, "target": target, "action": action, "phase": phase, "steamUpdate": True, "result": result}, separators=(",", ":")))
    sys.exit(0)


if phase in ("start", "restart") and use_host_compose:
    if dry_run:
        print(json.dumps({"ok": True, "target": target, "action": action, "phase": phase, "dryRun": True, "hostCompose": True, "services": services}, separators=(",", ":")))
        sys.exit(0)
    result = run_host_compose(services)
    print(json.dumps({"ok": True, "target": target, "action": action, "phase": phase, "hostCompose": True, "affected": services, "result": result}, separators=(",", ":")))
    sys.exit(0)


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
  services="survival overmap arrakeen harko-village testing-hephaestus testing-carthag testing-waterfat deep-desert proces-verbal lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab art-of-kanly dungeon-hephaestus dungeon-oldcarthag faction-outpost-atre faction-outpost-hark heighliner-dungeon ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-195 ecolab-green-136 overland-m-01 overland-s-04 overland-s-06 bandit-fortress overland-s-07 overland-s-08 dungeon-thepit director gateway text-router rmq-auth-shim"
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
if [ "$phase" = "update" ]; then
  run_steam_update_check
  exit 0
fi
if [ "$phase" = "shutdown" ] || [ "$phase" = "stop" ]; then
  exec "$@" stop -t 30 $services
fi
if [ "$phase" = "start" ]; then
  if [ -x ./scripts/seed-gateway-neighbor.sh ]; then
    ./scripts/seed-gateway-neighbor.sh || true
  fi
  "$@" up -d --force-recreate --no-deps $services
  if [ -x ./scripts/seed-gateway-neighbor.sh ]; then
    ./scripts/seed-gateway-neighbor.sh || true
  fi
  if [ -x ./scripts/restart-post-start-health.sh ]; then
    ./scripts/restart-post-start-health.sh
  elif [ -x ./scripts/verify-rmq-auth-path.sh ]; then
    ./scripts/verify-rmq-auth-path.sh
  fi
  exit 0
fi
if [ -x ./scripts/seed-gateway-neighbor.sh ]; then
  ./scripts/seed-gateway-neighbor.sh || true
fi
"$@" up -d --force-recreate --no-deps $services
if [ -x ./scripts/seed-gateway-neighbor.sh ]; then
  ./scripts/seed-gateway-neighbor.sh || true
fi
if [ -x ./scripts/restart-post-start-health.sh ]; then
  ./scripts/restart-post-start-health.sh
elif [ -x ./scripts/verify-rmq-auth-path.sh ]; then
  ./scripts/verify-rmq-auth-path.sh
fi
