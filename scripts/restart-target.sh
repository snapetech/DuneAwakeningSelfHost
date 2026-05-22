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

map_watchdog_control_enabled() {
  case "${DUNE_MAP_WATCHDOG_CONTROL:-true}" in
    0|false|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

map_watchdog_control() {
  verb="$1"
  env_file="${ENV_FILE:-.env}"
  if ! map_watchdog_control_enabled; then
    return 0
  fi
  if [ -x ./scripts/map-watchdog-control.sh ]; then
    ./scripts/map-watchdog-control.sh "$verb" "$env_file" || true
  fi
}

env_file_value() {
  key="$1"
  file="${2:-${ENV_FILE:-.env}}"
  eval "value=\${$key:-}"
  if [ -n "$value" ]; then
    printf '%s\n' "$value"
    return 0
  fi
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\''"]|["'\''"]$/, "")
      print
      exit
    }
  ' "$file" 2>/dev/null || true
}

run_steam_update_check() {
  env_file="${ENV_FILE:-.env}"
  if ! steam_update_enabled; then
    printf 'Steam package update check disabled by DUNE_RESTART_CHECK_STEAM_UPDATE\n'
    return 0
  fi
  if [ -x ./scripts/update-steam-tool.sh ]; then
    steamcmd_command="$(env_file_value DUNE_STEAMCMD_COMMAND "$env_file")"
    steamcmd_command="${steamcmd_command:-steamcmd}"
    steam_mode="$(env_file_value DUNE_RESTART_STEAM_UPDATE_MODE "$env_file")"
    steam_mode="${steam_mode:-auto}"
    if [ "$steam_mode" != "steamcmd" ]; then
      ./scripts/update-steam-tool.sh "$env_file"
    elif command -v "$steamcmd_command" >/dev/null 2>&1; then
      ./scripts/update-steam-tool.sh "$env_file"
    else
      helper_image="$(env_file_value DUNE_RESTART_STEAMCMD_HELPER_IMAGE "$env_file")"
      steam_dir="$(env_file_value DUNE_STEAM_SERVER_DIR "$env_file")"
      if [ -n "$helper_image" ] && [ -n "$steam_dir" ] && command -v docker >/dev/null 2>&1; then
        steam_mount="$steam_dir"
        case "$steam_dir" in
          */steamapps/common/*|*/Steam/steamapps/common/*)
            steam_mount="$(dirname "$(dirname "$(dirname "$steam_dir")")")"
            ;;
        esac
        docker run --rm \
          -v "$PWD:$PWD" \
          -v "$PWD:/workspace" \
          -v "$steam_mount:$steam_mount" \
          -w "$PWD" \
          -e "DUNE_RESTART_STEAMCMD_UPDATE=$(env_file_value DUNE_RESTART_STEAMCMD_UPDATE "$env_file")" \
          -e "DUNE_RESTART_STEAM_UPDATE_MODE=$(env_file_value DUNE_RESTART_STEAM_UPDATE_MODE "$env_file")" \
          -e "DUNE_RESTART_STEAM_CLIENT_TRIGGER=$(env_file_value DUNE_RESTART_STEAM_CLIENT_TRIGGER "$env_file")" \
          -e "DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS=$(env_file_value DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS "$env_file")" \
          -e "DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS=$(env_file_value DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS "$env_file")" \
          -e "DUNE_STEAM_CLIENT_COMMAND=$(env_file_value DUNE_STEAM_CLIENT_COMMAND "$env_file")" \
          -e "DUNE_RESTART_STEAMCMD_REQUIRED=$(env_file_value DUNE_RESTART_STEAMCMD_REQUIRED "$env_file")" \
          -e "DUNE_STEAM_APP_ID=$(env_file_value DUNE_STEAM_APP_ID "$env_file")" \
          -e "DUNE_STEAM_LOGIN=$(env_file_value DUNE_STEAM_LOGIN "$env_file")" \
          -e "DUNE_STEAM_PASSWORD=$(env_file_value DUNE_STEAM_PASSWORD "$env_file")" \
          -e "DUNE_STEAMCMD_COMMAND=$(env_file_value DUNE_STEAMCMD_COMMAND "$env_file")" \
          -e "DUNE_STEAMCMD_VALIDATE=$(env_file_value DUNE_STEAMCMD_VALIDATE "$env_file")" \
          -e "DUNE_STEAMCMD_TIMEOUT_SECONDS=$(env_file_value DUNE_STEAMCMD_TIMEOUT_SECONDS "$env_file")" \
          "$helper_image" bash ./scripts/update-steam-tool.sh "$env_file"
      else
        ./scripts/update-steam-tool.sh "$env_file"
      fi
    fi
  else
    printf 'SteamCMD package update skipped: scripts/update-steam-tool.sh is missing or not executable\n' >&2
  fi
  if [ ! -x ./scripts/check-steam-update.sh ]; then
    printf 'Steam package update check skipped: scripts/check-steam-update.sh is missing or not executable\n' >&2
    return 0
  fi
  set +e
  ./scripts/check-steam-update.sh "$env_file"
  rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    return 0
  fi
  if [ "$rc" -eq 1 ]; then
    printf 'Steam package update available; loading official images and updating DUNE_IMAGE_TAG\n'
    ./scripts/load-images.sh "$env_file"
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
watchdog_control_enabled = os.environ.get("DUNE_MAP_WATCHDOG_CONTROL", "true").lower() not in ("0", "false", "no", "off")

default_services = [
    "survival", "overmap", "arrakeen", "harko-village", "testing-hephaestus",
    "testing-carthag", "testing-waterfat", "deep-desert", "deep-desert-pvp", "proces-verbal",
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


def run_host_shell(name, shell_command):
    if not host_workspace:
        return {"ok": False, "skipped": True, "warning": "host workspace is not configured"}
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
            "com.snapetech.dune.role": name,
            "com.snapetech.dune.restart_job": os.environ.get("DUNE_RESTART_JOB_ID", ""),
        },
    }
    helper_name = "dune-" + name + "-" + (os.environ.get("DUNE_RESTART_JOB_ID", "manual") or "manual")
    status, payload = docker("POST", "/containers/create?name=" + urllib.parse.quote(helper_name), body)
    if status == 409:
        status, payload = docker("POST", "/containers/create", body)
    if status != 201:
        return {"ok": False, "error": f"failed creating helper: HTTP {status} {payload[:500]!r}"}
    container_id = json.loads(payload.decode())["Id"]
    try:
        status, payload = docker("POST", f"/containers/{container_id}/start")
        if status not in (204, 304):
            return {"ok": False, "error": f"failed starting helper: HTTP {status} {payload[:500]!r}"}
        status, payload = docker("POST", f"/containers/{container_id}/wait")
        if status != 200:
            return {"ok": False, "error": f"failed waiting for helper: HTTP {status} {payload[:500]!r}"}
        result = json.loads(payload.decode() or "{}")
        exit_code = int(result.get("StatusCode", 1))
        logs = docker_logs(container_id)
        return {"ok": exit_code == 0, "returncode": exit_code, "output": logs}
    finally:
        remove_container(container_id)


def map_watchdog_control(verb):
    if not watchdog_control_enabled:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    command = (
        "set -e; "
        "if [ -x /workspace/scripts/map-watchdog-control.sh ]; then "
        f"/workspace/scripts/map-watchdog-control.sh {shlex.quote(verb)} {shlex.quote(env_file)}; "
        "else echo 'map watchdog control skipped: script missing' >&2; fi"
    )
    return run_host_shell("admin-restart-watchdog", command)


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
    steam_dir = read_env_value(env_file, "DUNE_STEAM_SERVER_DIR")
    steamcmd_helper_image = os.environ.get("DUNE_RESTART_STEAMCMD_HELPER_IMAGE") or read_env_value(env_file, "DUNE_RESTART_STEAMCMD_HELPER_IMAGE")
    steamcmd_env_keys = [
        "DUNE_RESTART_STEAMCMD_UPDATE",
        "DUNE_RESTART_STEAM_UPDATE_MODE",
        "DUNE_RESTART_STEAM_CLIENT_TRIGGER",
        "DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS",
        "DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS",
        "DUNE_STEAM_CLIENT_COMMAND",
        "DUNE_RESTART_STEAMCMD_REQUIRED",
        "DUNE_STEAM_APP_ID",
        "DUNE_STEAM_LOGIN",
        "DUNE_STEAM_PASSWORD",
        "DUNE_STEAMCMD_COMMAND",
        "DUNE_STEAMCMD_VALIDATE",
        "DUNE_STEAMCMD_TIMEOUT_SECONDS",
    ]
    steamcmd_env = []
    for key in steamcmd_env_keys:
        value = os.environ.get(key)
        if value is None:
            value = read_env_value(env_file, key)
        if value:
            steamcmd_env.extend(["-e", f"{key}={value}"])
    steamcmd_container = ""
    if steam_dir and os.path.isabs(steam_dir) and steamcmd_helper_image:
        steam_mount = steam_dir
        if os.path.basename(os.path.dirname(steam_dir)) == "common" and os.path.basename(os.path.dirname(os.path.dirname(steam_dir))) == "steamapps":
            steam_mount = os.path.dirname(os.path.dirname(os.path.dirname(steam_dir)))
        docker_run = [
            "docker", "run", "--rm",
            "-v", f"{host_workspace}:{host_workspace}",
            "-v", f"{host_workspace}:/workspace",
            "-v", f"{steam_mount}:{steam_mount}",
            "-w", host_workspace,
        ]
        docker_run.extend(steamcmd_env)
        docker_run.extend([
            steamcmd_helper_image,
            "bash", "./scripts/update-steam-tool.sh", env_file,
        ])
        steamcmd_container = " ".join(shlex.quote(part) for part in docker_run)
    steam_client_command = os.environ.get("DUNE_STEAM_CLIENT_COMMAND") or read_env_value(env_file, "DUNE_STEAM_CLIENT_COMMAND") or "steam"
    steam_client_min_wait = os.environ.get("DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS") or read_env_value(env_file, "DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS") or "30"
    steam_client_trigger = os.environ.get("DUNE_RESTART_STEAM_CLIENT_TRIGGER") or read_env_value(env_file, "DUNE_RESTART_STEAM_CLIENT_TRIGGER") or "true"
    steam_client_host_trigger = (
        "steam_pid=\"$(pgrep -u $(stat -c %u " + shlex.quote(steam_dir or host_workspace) + ") -f '/Steam/.*/steam|/steam( |$)' | head -1 || true)\"; "
        "if [ -n \"$steam_pid\" ] && command -v nsenter >/dev/null 2>&1; then "
        "if [ " + shlex.quote(steam_client_trigger) + " = false ] || [ " + shlex.quote(steam_client_trigger) + " = 0 ]; then "
        "echo 'Host Steam client detected; validation trigger disabled'; "
        "else echo 'Requesting host Steam client validation for app " + shlex.quote(read_env_value(env_file, "DUNE_STEAM_APP_ID") or "4754530") + "'; "
        "steam_uid=\"$(stat -c %u " + shlex.quote(steam_dir or host_workspace) + ")\"; "
        "steam_gid=\"$(stat -c %g " + shlex.quote(steam_dir or host_workspace) + ")\"; "
        "steam_home=\"" + shlex.quote((steam_dir or "").split("/.local/share/Steam/", 1)[0] if "/.local/share/Steam/" in (steam_dir or "") else "") + "\"; "
        "nsenter --target \"$steam_pid\" --mount --uts --ipc --net --pid --setuid \"$steam_uid\" --setgid \"$steam_gid\" "
        "env HOME=\"${steam_home:-/tmp}\" XDG_RUNTIME_DIR=\"/run/user/$steam_uid\" DISPLAY=\"${DISPLAY:-:0}\" "
        + shlex.quote(steam_client_command or "steam") + " "
        + shlex.quote("steam://validate/" + (read_env_value(env_file, "DUNE_STEAM_APP_ID") or "4754530"))
        + " >/dev/null 2>&1 || true; fi; "
        "sleep " + shlex.quote(steam_client_min_wait) + "; "
        "else false; fi"
    )
    image_tars = [
        "images/battlegroup/server-rabbitmq.tar",
        "images/battlegroup/server-text-router.tar",
        "images/battlegroup/server-bg-director.tar",
        "images/battlegroup/server-gateway.tar",
        "images/battlegroup/server-db-utils.tar",
        "images/battlegroup/server.tar",
    ]
    load_tars = image_tars + ["images/prerequisites/igw-postgres.tar"]
    image_tars_shell = " ".join(shlex.quote(item) for item in image_tars)
    load_tars_shell = " ".join(shlex.quote(item) for item in load_tars)
    steam_dir_shell = shlex.quote(steam_dir or "")
    env_file_shell = shlex.quote(env_file)
    inline_package_ingest = (
        "steam_dir=" + steam_dir_shell + "; "
        "env_file=" + env_file_shell + "; "
        "tag_file=$(mktemp); "
        "missing=0; "
        "for rel in " + image_tars_shell + "; do "
        "path=\"$steam_dir/$rel\"; "
        "if [ ! -f \"$path\" ]; then echo \"warn: missing package image tar: $path\" >&2; missing=$((missing + 1)); continue; fi; "
        "tar -xOf \"$path\" manifest.json 2>/dev/null | "
        "tr ',' '\\n' | "
        "sed -n 's/.*registry\\.funcom\\.com\\/funcom\\/self-hosting\\/seabass-server[^:\" ]*:\\([^\"]*\\).*/\\1/p' >> \"$tag_file\" || true; "
        "done; "
        "tags=$(sort -u \"$tag_file\" | sed '/^$/d'); "
        "tag_count=$(printf '%s\\n' \"$tags\" | sed '/^$/d' | wc -l | tr -d ' '); "
        "current_tag=$(awk -F= '$1 == \"DUNE_IMAGE_TAG\" {print $2; exit}' \"$env_file\" 2>/dev/null || true); "
        "echo \"env file: $env_file\"; echo \"Steam server dir: $steam_dir\"; echo \"current DUNE_IMAGE_TAG: ${current_tag:-unset}\"; "
        "echo 'package server tags:'; printf '%s\\n' \"$tags\" | sed 's/^/  /'; "
        "if [ \"$missing\" -gt 0 ] || [ \"$tag_count\" -ne 1 ]; then "
        "echo 'Steam package update check could not determine a safe tag; continuing without changing DUNE_IMAGE_TAG' >&2; rm -f \"$tag_file\"; exit 0; "
        "fi; "
        "package_tag=$(printf '%s\\n' \"$tags\" | sed '/^$/d' | head -1); "
        "if [ \"$current_tag\" = \"$package_tag\" ]; then echo 'status: current'; rm -f \"$tag_file\"; exit 0; fi; "
        "echo 'status: update available'; echo \"next tag: $package_tag\"; "
        "for rel in " + load_tars_shell + "; do "
        "path=\"$steam_dir/$rel\"; "
        "if [ ! -f \"$path\" ]; then echo \"missing image tar: $path\" >&2; rm -f \"$tag_file\"; exit 1; fi; "
        "docker load -i \"$path\"; "
        "done; "
        "if grep -q '^DUNE_IMAGE_TAG=' \"$env_file\"; then sed -i \"s/^DUNE_IMAGE_TAG=.*/DUNE_IMAGE_TAG=$package_tag/\" \"$env_file\"; "
        "else printf '\\nDUNE_IMAGE_TAG=%s\\n' \"$package_tag\" >> \"$env_file\"; fi; "
        "echo \"updated $env_file: DUNE_IMAGE_TAG=$package_tag\"; "
        "rm -f \"$tag_file\""
    )
    shell_command = (
        "set -e; "
        "if [ -x ./scripts/update-steam-tool.sh ]; then "
        "steam_mode=${DUNE_RESTART_STEAM_UPDATE_MODE:-" + shlex.quote(read_env_value(env_file, "DUNE_RESTART_STEAM_UPDATE_MODE") or "auto") + "}; "
        "if [ \"$steam_mode\" != steamcmd ]; then "
        + steam_client_host_trigger + " || echo 'Steam client package refresh skipped: no host Steam client visible from helper' >&2; "
        "elif command -v steamcmd >/dev/null 2>&1; then "
        f"./scripts/update-steam-tool.sh {shlex.quote(env_file)}; "
        + (f"elif [ -n {shlex.quote(steamcmd_container)} ]; then {steamcmd_container}; " if steamcmd_container else "")
        + "else "
        "echo 'SteamCMD package update skipped: steamcmd is unavailable and no helper image is configured' >&2; "
        "fi; "
        "else "
        "echo 'SteamCMD package update skipped: scripts/update-steam-tool.sh is missing or not executable' >&2; "
        "fi; "
        + inline_package_ingest
    )
    binds = [
        f"{socket_path}:/var/run/docker.sock",
        f"{host_workspace}:{host_workspace}",
        f"{host_workspace}:/workspace",
    ]
    if steam_dir and os.path.isabs(steam_dir):
        steam_mount = steam_dir
        if os.path.basename(os.path.dirname(steam_dir)) == "common" and os.path.basename(os.path.dirname(os.path.dirname(steam_dir))) == "steamapps":
            steam_mount = os.path.dirname(os.path.dirname(os.path.dirname(steam_dir)))
        binds.append(f"{steam_mount}:{steam_mount}")
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
            "PidMode": "host",
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
    map_watchdog_control("stop")
    result = run_host_compose(services)
    map_watchdog_control("start")
    print(json.dumps({"ok": True, "target": target, "action": action, "phase": phase, "hostCompose": True, "affected": services, "result": result}, separators=(",", ":")))
    sys.exit(0)


label_filters = [
    f"label=com.docker.compose.project={project}",
]
for service in services:
    label_filters.append(f"label=com.docker.compose.service={service}")

restarted = []
missing = []
if phase in ("shutdown", "stop", "start", "restart") and not dry_run:
    map_watchdog_control("stop")
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

if phase in ("start", "restart") and not dry_run:
    map_watchdog_control("start")

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
  services="survival overmap arrakeen harko-village testing-hephaestus testing-carthag testing-waterfat deep-desert deep-desert-pvp proces-verbal lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab art-of-kanly dungeon-hephaestus dungeon-oldcarthag faction-outpost-atre faction-outpost-hark heighliner-dungeon ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-195 ecolab-green-136 overland-m-01 overland-s-04 overland-s-06 bandit-fortress overland-s-07 overland-s-08 dungeon-thepit director gateway text-router rmq-auth-shim"
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
  map_watchdog_control stop
  exec "$@" stop -t 30 $services
fi
if [ "$phase" = "start" ]; then
  map_watchdog_control stop
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
  map_watchdog_control start
  exit 0
fi
map_watchdog_control stop
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
map_watchdog_control start
