#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/schedule-daily-maintenance.sh

Schedules the daily executed, backed-up, announced all-services maintenance
restart through the local DASH admin panel.

Environment:
  DUNE_ENV_FILE                         Env file to read. Default: <repo>/.env
  DUNE_ADMIN_LOCAL_HOST                 Admin bind host. Default: 127.0.0.1
  DUNE_ADMIN_LOCAL_PORT                 Admin port. Default: DUNE_ADMIN_HOST_PORT or 18080
  DUNE_DAILY_RESTART_DELAY              Warning window. Default: 30min
  DUNE_DAILY_RESTART_REPEAT_SECONDS     Repeat cadence. Default: 600
  DUNE_DAILY_RESTART_MESSAGE            Announcement text.
USAGE
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

repo_dir="${DUNE_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
env_file="${DUNE_ENV_FILE:-$repo_dir/.env}"
admin_host="${DUNE_ADMIN_LOCAL_HOST:-127.0.0.1}"
admin_port="${DUNE_ADMIN_LOCAL_PORT:-}"

read_env() {
  local key="$1"
  [[ -f "$env_file" ]] || return 0
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$env_file"
}

if [[ -z "$admin_port" ]]; then
  admin_port="$(read_env DUNE_ADMIN_HOST_PORT)"
fi
admin_port="${admin_port:-18080}"
restart_delay="${DUNE_DAILY_RESTART_DELAY:-$(read_env DUNE_DAILY_RESTART_DELAY)}"
restart_delay="${restart_delay:-30min}"
repeat_seconds="${DUNE_DAILY_RESTART_REPEAT_SECONDS:-$(read_env DUNE_DAILY_RESTART_REPEAT_SECONDS)}"
repeat_seconds="${repeat_seconds:-600}"
message="${DUNE_DAILY_RESTART_MESSAGE:-$(read_env DUNE_DAILY_RESTART_MESSAGE)}"
message="${message:-Daily maintenance restart at 6:00 AM. Please get to a safe place.}"

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
    "announcement_cadence": [
        {"remaining_seconds": 5 * 60, "interval_seconds": 60},
        {"remaining_seconds": 30 * 60, "interval_seconds": 5 * 60},
    ],
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
