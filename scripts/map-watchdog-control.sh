#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/map-watchdog-control.sh pause|resume|stop|start|restart|status [ENV_FILE]

Controls the map watchdog around deliberate maintenance. The pause marker is
honored by watch-maps.sh loop mode; stop/start also try the host systemd unit
when available and fall back to the current checkout's standalone process.

Environment:
  DUNE_WATCH_PAUSE_FILE       Pause marker. Default: /tmp/dune-map-watchdog.paused
  DUNE_MAP_WATCHDOG_UNIT      systemd unit. Default: dune-map-watchdog.service
  DUNE_MAP_WATCHDOG_CONTROL   Set false/0/no/off to disable actions.
USAGE
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

action="$1"
env_file="${2:-${ENV_FILE:-.env}}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
watch_script="$repo_root/scripts/watch-maps.sh"
pause_file="${DUNE_WATCH_PAUSE_FILE:-/tmp/dune-map-watchdog.paused}"
unit="${DUNE_MAP_WATCHDOG_UNIT:-dune-map-watchdog.service}"

case "${DUNE_MAP_WATCHDOG_CONTROL:-true}" in
  0|false|no|off)
    printf 'map watchdog control disabled by DUNE_MAP_WATCHDOG_CONTROL\n'
    exit 0
    ;;
esac

case "$action" in
  pause|resume|stop|start|restart|status) ;;
  *)
    usage
    exit 2
    ;;
esac

systemctl_available() {
  command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$unit" >/dev/null 2>&1
}

run_systemctl() {
  local verb="$1"
  if ! systemctl_available; then
    return 1
  fi
  systemctl "$verb" "$unit"
}

pause_watchdog() {
  mkdir -p "$(dirname "$pause_file")"
  : > "$pause_file"
  printf 'map watchdog paused: %s\n' "$pause_file"
}

resume_watchdog() {
  rm -f "$pause_file"
  printf 'map watchdog resumed: %s\n' "$pause_file"
}

stop_standalone_watchdog() {
  local pattern pid_line pid
  pattern="$watch_script $env_file"
  while IFS= read -r pid_line; do
    [[ -n "$pid_line" ]] || continue
    pid="${pid_line%% *}"
    [[ "$pid" != "$$" ]] || continue
    case "$pid_line" in
      *" --once"*|*" --status"*|*" --dry-run"*) continue ;;
    esac
    kill "$pid" 2>/dev/null || true
    printf 'stopped standalone map watchdog pid=%s\n' "$pid"
  done < <(pgrep -af "$pattern" || true)
}

status_watchdog() {
  if [[ -e "$pause_file" ]]; then
    printf 'paused: %s\n' "$pause_file"
  else
    printf 'not paused: %s\n' "$pause_file"
  fi
  if systemctl_available; then
    systemctl is-active "$unit" || true
  fi
  pgrep -af "$watch_script $env_file" || true
}

case "$action" in
  pause)
    pause_watchdog
    ;;
  resume)
    resume_watchdog
    ;;
  stop)
    pause_watchdog
    run_systemctl stop || true
    stop_standalone_watchdog
    ;;
  start)
    resume_watchdog
    run_systemctl start || true
    ;;
  restart)
    pause_watchdog
    run_systemctl stop || true
    stop_standalone_watchdog
    resume_watchdog
    run_systemctl start || true
    ;;
  status)
    status_watchdog
    ;;
esac
