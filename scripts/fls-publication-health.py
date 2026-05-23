#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCKER_SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
DOCKER_COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT_NAME", "dune_server")

SECRET_PATTERNS = [
    (re.compile(r"eyJ[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+"), "[redacted-jwt]"),
    (re.compile(r"(ServiceAuthToken: )\S+"), r"\1[redacted]"),
    (re.compile(r'("GameRmqSecret": ")[^"]+'), r'\1[redacted]'),
    (re.compile(r"(postgresql://dune:)[^@]+"), r"\1[redacted]"),
]

BAD_PATTERNS = [
    "INVALID_DATA",
    "does not exist or is inactive",
    "HTTP Request Error",
    "Failed to execute critical Azure API function",
    "GatewayDeclareFarmStatus failed",
    "Traceback",
]


def redact(text):
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def run(cmd, timeout=20):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def decode_chunked_body(body):
    out = b""
    rest = body
    while rest:
        size_raw, sep, rest = rest.partition(b"\r\n")
        if not sep:
            break
        try:
            size = int(size_raw.split(b";", 1)[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        out += rest[:size]
        rest = rest[size + 2 :]
    return out


def docker_api_raw(path, timeout=10):
    sock_path = pathlib.Path(DOCKER_SOCKET)
    if not sock_path.exists():
        raise FileNotFoundError(f"Docker socket not found: {sock_path}")
    request = f"GET {path} HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n".encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(sock_path))
        sock.sendall(request)
        raw = b""
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            raw += chunk
    header, _, body = raw.partition(b"\r\n\r\n")
    if b" 200 " not in header.split(b"\r\n", 1)[0]:
        raise RuntimeError(header.split(b"\r\n", 1)[0].decode("utf-8", errors="replace"))
    if b"transfer-encoding: chunked" in header.lower():
        body = decode_chunked_body(body)
    return body


def docker_api_json(path, timeout=10):
    body = docker_api_raw(path, timeout=timeout)
    return json.loads(body.decode("utf-8") or "null")


def parse_since_seconds(value):
    text = str(value).strip().lower()
    match = re.fullmatch(r"(\d+)([smhd]?)", text)
    if not match:
        return 600
    amount = int(match.group(1))
    unit = match.group(2) or "s"
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def clean_docker_log_bytes(body):
    # Non-TTY Docker logs are multiplexed with 8-byte frame headers. They include
    # NUL/control bytes that break simple text scans; removing controls preserves
    # the actual log payload well enough for health-pattern checks.
    text = body.decode("utf-8", errors="ignore")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def find_container_id(service):
    filters = {
        "label": [
            f"com.docker.compose.project={DOCKER_COMPOSE_PROJECT}",
            f"com.docker.compose.service={service}",
        ]
    }
    path = f"/containers/json?all=1&filters={urllib.parse.quote(json.dumps(filters))}"
    containers = docker_api_json(path)
    for container in containers:
        if container.get("State") == "running":
            return container.get("Id")
    return containers[0].get("Id") if containers else None


def socket_service_logs(service, since):
    container_id = find_container_id(service)
    if not container_id:
        return "", f"{service} container is not running"
    since_epoch = max(0, int(time.time()) - parse_since_seconds(since))
    path = f"/containers/{container_id}/logs?stdout=1&stderr=1&timestamps=0&since={since_epoch}"
    return redact(clean_docker_log_bytes(docker_api_raw(path, timeout=20))), None


def compose_cmd(env_file, compose_files):
    runtime = os.environ.get("CONTAINER_RUNTIME", "docker")
    cmd = [runtime, "compose"]
    for compose_file in compose_files.split(":"):
        if compose_file:
            cmd.extend(["-f", compose_file])
    cmd.extend(["--env-file", env_file])
    return cmd


def service_running(base_cmd, service):
    if not shutil.which(base_cmd[0]):
        return find_container_id(service) is not None
    result = run(base_cmd + ["ps", "-q", service], timeout=10)
    return result.returncode == 0 and bool(result.stdout.strip())


def service_logs(base_cmd, service, since):
    if not shutil.which(base_cmd[0]):
        return socket_service_logs(service, since)
    if not service_running(base_cmd, service):
        return "", f"{service} container is not running"
    result = run(base_cmd + ["logs", "--since", since, service], timeout=20)
    text = redact((result.stdout or "") + "\n" + (result.stderr or ""))
    if result.returncode != 0:
        return text, f"{service} logs failed"
    return text, None


def last_index(lines, needle):
    idx = -1
    for i, line in enumerate(lines):
        if needle in line:
            idx = i
    return idx


def has_after(lines, start_idx, needles):
    haystack = "\n".join(lines[start_idx + 1 :])
    return [needle for needle in needles if needle in haystack]


def line_sample(lines, needles, limit=3):
    samples = []
    for line in lines:
        if any(needle in line for needle in needles):
            samples.append(line.strip())
    return samples[-limit:]


def evaluate(env_file, compose_files, since):
    base = compose_cmd(env_file, compose_files)
    director_log, director_error = service_logs(base, "director", since)
    gateway_log, gateway_error = service_logs(base, "gateway", since)
    director_lines = director_log.splitlines()
    gateway_lines = gateway_log.splitlines()

    initialize_idx = last_index(director_lines, '("api/Director_InitializeDirector") Request successful')
    heartbeat_idx = last_index(director_lines, '("api/Battlegroups_SendBattlegroupHeartbeat") Request successful')
    population_idx = last_index(director_lines, '("api/Battlegroups_DeclarePopulationAndActivity") Request successful')
    capacity_idx = last_index(director_lines, '("api/Battlegroups_DeclareMaxPlayerCapacities") Request successful')
    update_idx = last_index(director_lines, '("api/Battlegroups_DeclareBattlegroupUpdates") Request successful')
    gateway_decl_idx = last_index(gateway_lines, "Request: api/GatewayDeclareFarmStatus")
    gateway_monitor_idx = last_index(gateway_lines, "Monitoring for servers going up or down")
    gateway_map_idx = last_index(gateway_lines, "Server ")

    director_bad_after_population = has_after(director_lines, population_idx, BAD_PATTERNS) if population_idx >= 0 else line_sample(director_lines, BAD_PATTERNS, 5)
    gateway_bad_after_declare = has_after(gateway_lines, gateway_decl_idx, BAD_PATTERNS) if gateway_decl_idx >= 0 else line_sample(gateway_lines, BAD_PATTERNS, 5)

    checks = [
        {"name": "director container running", "ok": director_error is None, "value": director_error or "running"},
        {"name": "gateway container running", "ok": gateway_error is None, "value": gateway_error or "running"},
        {"name": "director initialized with FLS", "ok": initialize_idx >= 0, "value": "seen" if initialize_idx >= 0 else "missing"},
        {"name": "director heartbeat accepted by FLS", "ok": heartbeat_idx >= 0, "value": "seen" if heartbeat_idx >= 0 else "missing"},
        {"name": "director population accepted by FLS", "ok": population_idx >= 0, "value": "seen" if population_idx >= 0 else "missing"},
        {"name": "director capacity accepted by FLS", "ok": capacity_idx >= 0, "value": "seen" if capacity_idx >= 0 else "missing"},
        {"name": "director battlegroup update accepted by FLS", "ok": update_idx >= 0, "value": "seen" if update_idx >= 0 else "missing"},
        {"name": "no director FLS errors after latest population success", "ok": not director_bad_after_population, "value": "; ".join(director_bad_after_population) if director_bad_after_population else "clean"},
        {"name": "gateway farm status declared", "ok": gateway_decl_idx >= 0 and gateway_monitor_idx > gateway_decl_idx, "value": "seen" if gateway_decl_idx >= 0 else "missing"},
        {"name": "gateway observed farm maps", "ok": gateway_map_idx >= 0, "value": "seen" if gateway_map_idx >= 0 else "missing"},
        {"name": "no gateway errors after latest farm declaration", "ok": not gateway_bad_after_declare, "value": "; ".join(gateway_bad_after_declare) if gateway_bad_after_declare else "clean"},
    ]
    ok = all(check["ok"] for check in checks)
    return {
        "ok": ok,
        "state": "healthy" if ok else "degraded",
        "generatedAtEpoch": int(time.time()),
        "window": since,
        "checks": checks,
        "samples": {
            "directorErrors": line_sample(director_lines, BAD_PATTERNS, 5),
            "gatewayErrors": line_sample(gateway_lines, BAD_PATTERNS, 5),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Check whether Director/Gateway are publishing live battlegroup state to FLS.")
    parser.add_argument("env_file", nargs="?", default=".env")
    parser.add_argument("--compose-files", default=os.environ.get("COMPOSE_FILES", "compose.yaml"))
    parser.add_argument("--since", default=os.environ.get("DUNE_FLS_PUBLICATION_HEALTH_SINCE", "10m"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.env_file, args.compose_files, args.since)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"FLS publication health: {result['state']} window={result['window']}")
        for check in result["checks"]:
            prefix = "OK" if check["ok"] else "FAIL"
            print(f"{prefix}: {check['name']}: {check.get('value', '')}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
