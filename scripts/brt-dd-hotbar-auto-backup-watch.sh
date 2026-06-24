#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/brt-dd-hotbar-auto-backup-watch.sh arm|run-once|status|stop [player_id] [container]

Server-side DD1 BRT hotbar bridge. It watches tracefs for the current-build
BRT action/can-use event that fires from the in-game BRT tool, then creates a
real DD1 base backup for the allowlisted player through the proven persistence
path. This is a canary bridge, not a chat/admin command.
USAGE
}

action="${1:-}"
player_id="${2:-17}"
container="${3:-dune_server-deep-desert-1}"
required_host="${DUNE_BRT_DD_HOTBAR_WATCH_HOST:-kspls0}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
tracefs="${DUNE_TRACEFS:-/sys/kernel/tracing}"
pid_file="${DUNE_BRT_DD_HOTBAR_WATCH_PID_FILE:-/tmp/brt-dd-hotbar-auto-backup-watch.pid}"
log_file="${DUNE_BRT_DD_HOTBAR_WATCH_LOG:-/tmp/brt-dd-hotbar-auto-backup-watch.log}"
trace_log="${DUNE_BRT_DD_HOTBAR_WATCH_TRACE_LOG:-/tmp/brt-dd-hotbar-auto-backup-watch.trace.log}"
cooldown_seconds="${DUNE_BRT_DD_HOTBAR_WATCH_COOLDOWN_SECONDS:-15}"

case "$action" in
  arm|run-once|status|stop) ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  *)
    usage
    exit 2
    ;;
esac

case "$player_id" in
  ''|*[!0-9]*)
    echo "player_id must be numeric" >&2
    exit 2
    ;;
esac

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_HOTBAR_WATCH_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "refusing on host '$short_host'; required '$required_host'" >&2
  exit 1
fi

cd "$repo_root"

trace_has_hotbar_event() {
  sudo -n cat "$tracefs/trace" | grep -q 'brt_action_canuse_entry'
}

clear_trace() {
  printf '\n' | sudo -n tee "$tracefs/trace" >/dev/null
}

ensure_hotbar_trace_armed() {
  bash scripts/brt-dd-uprobe-watch.sh stop "$container" >/dev/null 2>&1 || true
  DUNE_BRT_DD_POINTS_FILE=scripts/research/brt-dd-points-427a3084.tsv \
  DUNE_BRT_DD_UPROBE_PROFILE=hotbar \
    bash scripts/brt-dd-uprobe-watch.sh arm "$container" >/dev/null
  clear_trace
}

backup_from_hotbar_event() {
  local stamp totem_id
  stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  totem_id="$(
    scripts/dd1-brt-emulator.py list-totems --player-id "$player_id" |
      python3 -c 'import json,sys; data=json.load(sys.stdin); ts=data.get("totems") or []; print(ts[0]["totem_id"] if len(ts) == 1 else "")'
  )"
  if [[ -z "$totem_id" ]]; then
    echo "[$stamp] no unique active DD1 totem found for player_id=$player_id; refusing auto-backup" >>"$log_file"
    return 1
  fi
  {
    echo "[$stamp] hotbar BRT event observed; attempting DD1 auto-backup player_id=$player_id totem_id=$totem_id"
    DUNE_ALLOW_LIVE_DD1_BRT_MUTATION=1 \
    CONFIRM_DD1_BRT="I UNDERSTAND DD1 BRT MAY BREAK BASE OWNERSHIP" \
      scripts/dd1-brt-emulator.py create-backup \
        --player-id "$player_id" \
        --totem-id "$totem_id" \
        --rpc-classification normal-request-not-observed \
        --commit \
        --confirm "CREATE DD1 BRT BACKUP"
  } >>"$log_file" 2>&1
}

run_once() {
  local deadline now last_fire_file="/tmp/brt-dd-hotbar-auto-backup-watch.last"
  ensure_hotbar_trace_armed
  echo "watching player_id=$player_id container=$container log=$log_file trace=$trace_log"
  deadline=$((SECONDS + ${DUNE_BRT_DD_HOTBAR_WATCH_TIMEOUT_SECONDS:-180}))
  while (( SECONDS < deadline )); do
    sudo -n cat "$tracefs/trace" >"$trace_log"
    if grep -q 'brt_action_canuse_entry' "$trace_log"; then
      now="$(date +%s)"
      if [[ -f "$last_fire_file" ]] && (( now - $(cat "$last_fire_file") < cooldown_seconds )); then
        echo "cooldown active; ignoring hotbar event" >>"$log_file"
        clear_trace
        sleep 1
        continue
      fi
      printf '%s\n' "$now" >"$last_fire_file"
      backup_from_hotbar_event
      clear_trace
      echo "auto-backup attempted; see $log_file"
      return 0
    fi
    sleep 0.5
  done
  echo "timeout waiting for hotbar BRT event" >&2
  return 124
}

case "$action" in
  arm)
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      echo "already running pid=$(cat "$pid_file") log=$log_file"
      exit 0
    fi
    (
      run_once
    ) >>"$log_file" 2>&1 &
    echo $! >"$pid_file"
    echo "armed pid=$(cat "$pid_file") player_id=$player_id log=$log_file"
    ;;
  run-once)
    run_once
    ;;
  status)
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      echo "running pid=$(cat "$pid_file")"
    else
      echo "not running"
    fi
    echo "log=$log_file"
    echo "trace_log=$trace_log"
    tail -40 "$log_file" 2>/dev/null || true
    ;;
  stop)
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      kill "$(cat "$pid_file")"
      echo "stopped pid=$(cat "$pid_file")"
    else
      echo "not running"
    fi
    rm -f "$pid_file"
    ;;
esac
