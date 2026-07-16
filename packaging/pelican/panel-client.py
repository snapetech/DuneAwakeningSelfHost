#!/usr/bin/env python3
"""Constrained Pelican console client for a forced-command DASH SSH key."""

import os
import pathlib
import re
import shlex
import stat
import subprocess
import sys

ALLOWED_SINGLE = {"help", "status", "bootstrap-check", "backup", "farm-start", "farm-stop"}
ALLOWED_MAP = {"map-start", "map-stop", "map-restart"}
SERVICE = re.compile(r"^[a-z0-9-]{1,48}$")


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def validate_command(line: str) -> str:
    try:
        parts = shlex.split(line, posix=True)
    except ValueError as exc:
        raise ValueError(f"invalid command quoting: {exc}") from exc
    if len(parts) == 1 and parts[0] in ALLOWED_SINGLE:
        return parts[0]
    if len(parts) == 2 and parts[0] in ALLOWED_MAP and SERVICE.fullmatch(parts[1]):
        return " ".join(parts)
    raise ValueError("command is outside the DASH Pelican allowlist; enter help")


def main() -> int:
    host = required("DASH_REMOTE_HOST")
    user = required("DASH_REMOTE_USER")
    port = os.environ.get("DASH_REMOTE_PORT", "22")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SystemExit("DASH_REMOTE_PORT must be 1..65535")
    key = pathlib.Path(os.environ.get("DASH_SSH_KEY_PATH", "/home/container/secrets/id_ed25519"))
    known_hosts = pathlib.Path(os.environ.get("DASH_KNOWN_HOSTS_PATH", "/home/container/secrets/known_hosts"))
    for path in (key, known_hosts):
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"required SSH file is missing or empty: {path}")
    if stat.S_IMODE(key.stat().st_mode) & 0o077:
        raise SystemExit(f"SSH private key must not be group/world accessible: {key}")

    timeout = int(os.environ.get("DASH_COMMAND_TIMEOUT_SECONDS", "900"))
    print("DASH Pelican controller ready; enter help", flush=True)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            command = validate_command(line)
            result = subprocess.run(
                [
                    "ssh", "-T", "-p", port, "-i", str(key),
                    "-o", "BatchMode=yes",
                    "-o", "IdentitiesOnly=yes",
                    "-o", "StrictHostKeyChecking=yes",
                    "-o", f"UserKnownHostsFile={known_hosts}",
                    "-o", "ForwardAgent=no",
                    "-o", "ClearAllForwardings=yes",
                    f"{user}@{host}", command,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
            output = result.stdout
            if len(output.encode("utf-8", errors="replace")) > 262_144:
                output = output[:262_144] + "\n[output truncated]\n"
            print(output.rstrip(), flush=True)
            print(f"[exit {result.returncode}]", flush=True)
        except (ValueError, subprocess.TimeoutExpired) as exc:
            print(f"ERROR: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
