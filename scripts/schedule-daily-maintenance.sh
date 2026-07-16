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
  DUNE_DAILY_RESTART_SCHEDULE_WINDOW    Allowed local HH:MM-HH:MM invocation window. Default: 05:25-05:35
  DUNE_DAILY_RESTART_ALLOW_OUTSIDE_WINDOW
                                        Set true to allow manual runs outside the window.
  DUNE_DAILY_RESTART_DELAY              Warning window. Default: 30min
  DUNE_DAILY_RESTART_REPEAT_SECONDS     Repeat cadence. Default: 600
  DUNE_DAILY_RESTART_REQUIRE_SOFT_DISCONNECT
                                        Require targeted player disconnect before stop.
                                        Default: false
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

env_or_file() {
  local key="$1"
  local value="${!key:-}"
  if [[ -n "$value" ]]; then
    printf '%s\n' "$value"
  else
    read_env "$key"
  fi
}

time_to_minutes() {
  local value="$1"
  if [[ ! "$value" =~ ^([0-2][0-9]):([0-5][0-9])$ ]]; then
    printf 'invalid schedule time: %s\n' "$value" >&2
    exit 2
  fi
  local hour="${BASH_REMATCH[1]}"
  local minute="${BASH_REMATCH[2]}"
  if (( 10#$hour > 23 )); then
    printf 'invalid schedule hour: %s\n' "$value" >&2
    exit 2
  fi
  printf '%s\n' $((10#$hour * 60 + 10#$minute))
}

check_schedule_window() {
  local allow window start end now_minutes start_minutes end_minutes
  allow="$(env_or_file DUNE_DAILY_RESTART_ALLOW_OUTSIDE_WINDOW)"
  case "${allow,,}" in
    1|true|yes|on) return 0 ;;
  esac
  window="$(env_or_file DUNE_DAILY_RESTART_SCHEDULE_WINDOW)"
  window="${window:-05:25-05:35}"
  if [[ "$window" != *-* ]]; then
    printf 'invalid DUNE_DAILY_RESTART_SCHEDULE_WINDOW: %s\n' "$window" >&2
    exit 2
  fi
  start="${window%-*}"
  end="${window#*-}"
  start_minutes="$(time_to_minutes "$start")"
  end_minutes="$(time_to_minutes "$end")"
  now_minutes=$((10#$(date +%H) * 60 + 10#$(date +%M)))
  if (( start_minutes <= end_minutes )); then
    if (( now_minutes >= start_minutes && now_minutes <= end_minutes )); then
      return 0
    fi
  else
    if (( now_minutes >= start_minutes || now_minutes <= end_minutes )); then
      return 0
    fi
  fi
  printf 'refusing to schedule daily maintenance outside %s local time; now=%s\n' "$window" "$(date +%H:%M)" >&2
  printf 'set DUNE_DAILY_RESTART_ALLOW_OUTSIDE_WINDOW=true for a deliberate manual run\n' >&2
  exit 2
}

check_schedule_window

if [[ -z "$admin_port" ]]; then
  admin_port="$(read_env DUNE_ADMIN_HOST_PORT)"
fi
admin_port="${admin_port:-18080}"
restart_delay="$(env_or_file DUNE_DAILY_RESTART_DELAY)"
restart_delay="${restart_delay:-30min}"
repeat_seconds="$(env_or_file DUNE_DAILY_RESTART_REPEAT_SECONDS)"
repeat_seconds="${repeat_seconds:-600}"
require_soft_disconnect="$(env_or_file DUNE_DAILY_RESTART_REQUIRE_SOFT_DISCONNECT)"
require_soft_disconnect="${require_soft_disconnect:-false}"
message="$(env_or_file DUNE_DAILY_RESTART_MESSAGE)"
message="${message:-Daily maintenance restart at 6:00 AM. Please get to a safe place.}"

token="$(read_env DUNE_ADMIN_TOKEN || true)"
require_token="$(read_env DUNE_ADMIN_REQUIRE_TOKEN || true)"

body="$(
  python3 - "$restart_delay" "$repeat_seconds" "$require_soft_disconnect" "$message" <<'PY'
import json
import sys

delay, repeat_seconds, require_soft_disconnect, message = sys.argv[1:5]
require_soft_disconnect = require_soft_disconnect.strip().lower() in ("1", "true", "yes", "on")
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
    "require_soft_disconnect": require_soft_disconnect,
}))
PY
)"

args=(-fsS -H "Content-Type: application/json" -X POST --data "$body")
if [[ -n "$token" ]]; then
  args+=(-H "Authorization: Bearer $token")
else
  case "${require_token,,}" in
    1|true|yes|on)
      printf 'DUNE_ADMIN_REQUIRE_TOKEN is enabled but DUNE_ADMIN_TOKEN is empty\n' >&2
      exit 1
      ;;
  esac
fi

curl "${args[@]}" "http://${admin_host}:${admin_port}/api/ops/restart"
printf '\n'
