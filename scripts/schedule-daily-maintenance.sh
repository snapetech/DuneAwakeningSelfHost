#!/usr/bin/env bash
set -euo pipefail

repo_dir="${DUNE_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
env_file="${DUNE_ENV_FILE:-$repo_dir/.env}"
admin_host="${DUNE_ADMIN_LOCAL_HOST:-127.0.0.1}"
admin_port="${DUNE_ADMIN_LOCAL_PORT:-}"
restart_delay="${DUNE_DAILY_RESTART_DELAY:-30min}"
repeat_seconds="${DUNE_DAILY_RESTART_REPEAT_SECONDS:-600}"
message="${DUNE_DAILY_RESTART_MESSAGE:-Daily maintenance restart at 3:00 AM. Please get to a safe place.}"

read_env() {
  local key="$1"
  [[ -f "$env_file" ]] || return 0
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$env_file"
}

if [[ -z "$admin_port" ]]; then
  admin_port="$(read_env DUNE_ADMIN_HOST_PORT)"
fi
admin_port="${admin_port:-18080}"

token="$(read_env DUNE_ADMIN_TOKEN || true)"
require_token="$(read_env DUNE_ADMIN_REQUIRE_TOKEN || true)"

body="$(
  python3 - "$restart_delay" "$repeat_seconds" "$message" <<'PY'
import json
import sys

delay, repeat_seconds, message = sys.argv[1:4]
print(json.dumps({
    "target": "all",
    "action": "restart",
    "delay": delay,
    "repeat_seconds": int(repeat_seconds),
    "message": message,
    "announce": True,
    "execute": True,
    "backup": True,
}))
PY
)"

args=(-fsS -H "Content-Type: application/json" -X POST --data "$body")
case "${require_token,,}" in
  1|true|yes|on)
    if [[ -z "$token" ]]; then
      printf 'DUNE_ADMIN_REQUIRE_TOKEN is enabled but DUNE_ADMIN_TOKEN is empty\n' >&2
      exit 1
    fi
    args+=(-H "Authorization: Bearer $token")
    ;;
esac

curl "${args[@]}" "http://${admin_host}:${admin_port}/api/ops/restart"
printf '\n'
