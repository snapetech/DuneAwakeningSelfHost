#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/watch-maps.sh ENV_FILE [--once|--status|--dry-run]

Watches fixed-partition map containers and recovers crashed/exited services with
scripts/recover-map.sh. It does not start services that were never launched.

Modes:
  --once      Run one recovery pass, quiet unless recovery is needed.
  --status    Print monitored service/container status and exit.
  --dry-run   Print what would be recovered and exit without changing state.

Environment:
  COMPOSE_FILES              Compose files, colon-separated. Default: compose.yaml
  CONTAINER_RUNTIME          Container runtime. Default: docker
  DUNE_WATCH_INTERVAL        Seconds between checks. Default: 30
  DUNE_WATCH_RECOVERY_WAIT   Seconds recover-map waits per recovery. Default: 180
  DUNE_WATCH_COOLDOWN        Minimum seconds between recoveries per service. Default: 300
  DUNE_WATCH_LOCK_DIR        Single-instance lock dir. Default: /tmp/dune-map-watchdog.lock
USAGE
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

env_file="$1"
mode="${2:-}"
if [[ -n "$mode" && "$mode" != "--once" && "$mode" != "--status" && "$mode" != "--dry-run" ]]; then
  usage
  exit 2
fi

container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

interval="${DUNE_WATCH_INTERVAL:-30}"
recovery_wait="${DUNE_WATCH_RECOVERY_WAIT:-180}"
cooldown="${DUNE_WATCH_COOLDOWN:-300}"
lock_dir="${DUNE_WATCH_LOCK_DIR:-/tmp/dune-map-watchdog.lock}"

if [[ ! "$interval" =~ ^[0-9]+$ || ! "$recovery_wait" =~ ^[0-9]+$ || ! "$cooldown" =~ ^[0-9]+$ ]]; then
  printf 'DUNE_WATCH_INTERVAL, DUNE_WATCH_RECOVERY_WAIT, and DUNE_WATCH_COOLDOWN must be numeric\n' >&2
  exit 2
fi

if [[ -z "$mode" ]]; then
  if ! mkdir "$lock_dir" 2>/dev/null; then
    printf 'another map watchdog appears to be running: %s\n' "$lock_dir" >&2
    exit 1
  fi
  trap 'rmdir "$lock_dir"' EXIT
fi

MAP_PARTITIONS=(
  "survival:1"
  "overmap:2"
  "arrakeen:3"
  "harko-village:4"
  "testing-hephaestus:5"
  "testing-carthag:6"
  "testing-waterfat:7"
  "deep-desert:8"
  "proces-verbal:9"
  "lostharvest-ecolab-a:10"
  "lostharvest-ecolab-b:11"
  "lostharvest-forgottenlab:12"
  "art-of-kanly:13"
  "dungeon-hephaestus:14"
  "dungeon-oldcarthag:15"
  "faction-outpost-atre:16"
  "faction-outpost-hark:17"
  "heighliner-dungeon:18"
  "ecolab-green-089:19"
  "ecolab-green-152:20"
  "ecolab-green-024:21"
  "ecolab-green-195:22"
  "ecolab-green-136:23"
  "overland-m-01:24"
  "overland-s-04:25"
  "overland-s-06:26"
  "bandit-fortress:27"
  "overland-s-07:28"
  "overland-s-08:29"
  "dungeon-thepit:30"
)

declare -A LAST_RECOVERY=()

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

container_status() {
  local service="$1"
  local container_id

  container_id="$("${compose[@]}" ps -q "$service" 2>/dev/null || true)"
  if [[ -z "$container_id" ]]; then
    printf 'missing'
    return
  fi

  "$container_runtime" inspect --format '{{ .State.Status }}' "$container_id" 2>/dev/null || printf 'missing'
}

recover_service() {
  local service="$1"
  local partition_id="$2"
  local now
  local last

  now="$(date +%s)"
  last="${LAST_RECOVERY[$service]:-0}"
  if (( now - last < cooldown )); then
    log "skip recovery during cooldown: service=$service partition=$partition_id"
    return
  fi

  LAST_RECOVERY[$service]="$now"
  if [[ "$mode" == "--dry-run" ]]; then
    log "would recover crashed map: service=$service partition=$partition_id"
    return
  fi

  log "recovering crashed map: service=$service partition=$partition_id"
  COMPOSE_FILES="${COMPOSE_FILES:-compose.yaml}" CONTAINER_RUNTIME="$container_runtime" \
    "$(dirname "$0")/recover-map.sh" "$env_file" "$service" "$partition_id" "$recovery_wait"
}

check_once() {
  local item
  local service
  local partition_id
  local status

  for item in "${MAP_PARTITIONS[@]}"; do
    service="${item%%:*}"
    partition_id="${item##*:}"
    status="$(container_status "$service")"

    if [[ "$mode" == "--status" ]]; then
      printf '%-32s partition=%-2s status=%s\n' "$service" "$partition_id" "$status"
      continue
    fi

    case "$status" in
      running|created|restarting|removing|paused)
        ;;
      exited|dead)
        recover_service "$service" "$partition_id"
        ;;
      missing)
        ;;
      *)
        log "unknown container status: service=$service status=$status"
        ;;
    esac
  done
}

while true; do
  check_once
  if [[ "$mode" == "--once" || "$mode" == "--status" || "$mode" == "--dry-run" ]]; then
    exit 0
  fi
  sleep "$interval"
done
