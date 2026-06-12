#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/watch-maps.sh ENV_FILE [--once|--status|--dry-run]

Watches fixed-partition map containers and recovers crashed/exited services or
degraded partition registration with scripts/recover-map.sh. It does not start
services that were never launched.

Modes:
  --once      Run one recovery pass, quiet unless recovery is needed.
  --status    Print monitored service/container status and exit.
  --dry-run   Print what would be recovered and exit without changing state.

Environment:
  COMPOSE_FILES              Compose files, colon-separated. Defaults are derived from ENV_FILE and host role.
  CONTAINER_RUNTIME          Container runtime. Default: docker
  DUNE_WATCH_INTERVAL        Seconds between checks. Default: 30
  DUNE_WATCH_RECOVERY_WAIT   Seconds recover-map waits per recovery. Default: 180
  DUNE_WATCH_COOLDOWN        Minimum seconds between recoveries per service. Default: 300
  DUNE_WATCH_STARTUP_GRACE   Seconds to let running maps warm before DB recovery. Default: 300
  DUNE_WATCH_LOCK_DIR        Single-instance lock dir. Default: /tmp/dune-map-watchdog.lock
  DUNE_WATCH_PAUSE_FILE      Pause marker honored in loop mode. Default: /tmp/dune-map-watchdog.paused
  DUNE_WATCH_REQUIRE_READY    Recover running maps with ready=false. Default: false
  DUNE_WATCH_RECOVER_COMMAND Recovery command. Default: scripts/recover-map.sh
  DUNE_WATCH_SEED_NEIGHBORS Seed known Docker bridge neighbor entries. Default: false
  DUNE_WATCH_SEED_COMMAND   Neighbor seed command. Default: scripts/seed-gateway-neighbor.sh
  DUNE_WATCH_SEED_INTERVAL  Seconds between neighbor seeding attempts. Default: 300
  DUNE_WATCH_SEED_TIMEOUT   Max seconds for neighbor seeding. Default: 90
  DUNE_WORLD_PARTITION_COUNT Monitored partition ceiling. Default: 30; set 31
                             only when the second Deep Desert is intentionally online.
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
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

interval="${DUNE_WATCH_INTERVAL:-30}"
recovery_wait="${DUNE_WATCH_RECOVERY_WAIT:-180}"
cooldown="${DUNE_WATCH_COOLDOWN:-300}"
startup_grace="${DUNE_WATCH_STARTUP_GRACE:-300}"
lock_dir="${DUNE_WATCH_LOCK_DIR:-/tmp/dune-map-watchdog.lock}"
pause_file="${DUNE_WATCH_PAUSE_FILE:-/tmp/dune-map-watchdog.paused}"
require_ready="${DUNE_WATCH_REQUIRE_READY:-false}"
recover_command="${DUNE_WATCH_RECOVER_COMMAND:-$script_dir/recover-map.sh}"
seed_neighbors="${DUNE_WATCH_SEED_NEIGHBORS:-false}"
seed_command="${DUNE_WATCH_SEED_COMMAND:-$script_dir/seed-gateway-neighbor.sh}"
seed_interval="${DUNE_WATCH_SEED_INTERVAL:-300}"
seed_timeout="${DUNE_WATCH_SEED_TIMEOUT:-90}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

partition_count="${DUNE_WORLD_PARTITION_COUNT:-$(read_env DUNE_WORLD_PARTITION_COUNT)}"
partition_count="${partition_count:-30}"
db="${DUNE_GAME_DB_NAME:-$(read_env DUNE_GAME_DB_NAME)}"
db="${db:-${DUNE_DATABASE:-$(read_env DUNE_DATABASE)}}"
db="${db:-${DUNE_DB_NAME:-$(read_env DUNE_DB_NAME)}}"
db="${db:-dune_sb_1_4_0_0}"
case "$partition_count" in
  30|31) ;;
  *)
    printf 'DUNE_WORLD_PARTITION_COUNT must be 30, or 31 to intentionally enable the second Deep Desert; got: %s\n' "$partition_count" >&2
    exit 2
    ;;
esac

if [[ ! "$interval" =~ ^[0-9]+$ || ! "$recovery_wait" =~ ^[0-9]+$ || ! "$cooldown" =~ ^[0-9]+$ || ! "$startup_grace" =~ ^[0-9]+$ || ! "$seed_interval" =~ ^[0-9]+$ || ! "$seed_timeout" =~ ^[0-9]+$ ]]; then
  printf 'DUNE_WATCH_INTERVAL, DUNE_WATCH_RECOVERY_WAIT, DUNE_WATCH_COOLDOWN, DUNE_WATCH_STARTUP_GRACE, DUNE_WATCH_SEED_INTERVAL, and DUNE_WATCH_SEED_TIMEOUT must be numeric\n' >&2
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
  "deep-desert-pvp:31"
)

declare -A LAST_RECOVERY=()
last_seed=0

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

container_status() {
  local service="$1"
  local container_id

  container_id="$("${compose[@]}" ps -aq "$service" 2>/dev/null || true)"
  if [[ -z "$container_id" ]]; then
    printf 'missing'
    return
  fi

  "$container_runtime" inspect --format '{{ .State.Status }}' "$container_id" 2>/dev/null || printf 'missing'
}

container_age_seconds() {
  local service="$1"
  local container_id
  local started_at
  local started_epoch
  local now

  container_id="$("${compose[@]}" ps -aq "$service" 2>/dev/null || true)"
  if [[ -z "$container_id" ]]; then
    printf '0'
    return
  fi

  started_at="$("$container_runtime" inspect --format '{{ .State.StartedAt }}' "$container_id" 2>/dev/null || true)"
  if [[ -z "$started_at" || "$started_at" == "0001-01-01T00:00:00Z" ]]; then
    printf '0'
    return
  fi

  started_epoch="$(date -d "$started_at" +%s 2>/dev/null || printf '0')"
  now="$(date +%s)"
  if (( started_epoch <= 0 || now < started_epoch )); then
    printf '0'
    return
  fi

  printf '%s' "$((now - started_epoch))"
}

partition_health() {
  local partition_id="$1"

  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "
    select
      coalesce(fs.ready, false) || ' ' ||
      coalesce(fs.alive, false) || ' ' ||
      (asi.server_id is not null)
    from dune.world_partition wp
    left join dune.farm_state fs on fs.server_id = wp.server_id
    left join dune.active_server_ids asi on asi.server_id = wp.server_id
    where wp.partition_id = ${partition_id};
  " 2>/dev/null || printf 'unknown unknown unknown'
}

partition_degraded_reason() {
  local partition_id="$1"
  local ready
  local alive
  local active

  read -r ready alive active <<< "$(partition_health "$partition_id")"

  if [[ "$alive" == "unknown" || "$active" == "unknown" ]]; then
    printf 'health_unknown'
    return
  fi

  if [[ "$alive" != "t" && "$alive" != "true" ]]; then
    printf 'not_alive'
    return
  fi

  if [[ "$active" != "t" && "$active" != "true" ]]; then
    printf 'not_active'
    return
  fi

  if [[ "$require_ready" == "true" && "$ready" != "t" && "$ready" != "true" ]]; then
    printf 'not_ready'
    return
  fi

  printf 'ok'
}

recover_service() {
  local service="$1"
  local partition_id="$2"
  local reason="${3:-crashed}"
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
    log "would recover map: service=$service partition=$partition_id reason=$reason"
    return
  fi

  log "recovering map: service=$service partition=$partition_id reason=$reason"
  if ! COMPOSE_FILES="$COMPOSE_FILES" CONTAINER_RUNTIME="$container_runtime" \
    "$recover_command" "$env_file" "$service" "$partition_id" "$recovery_wait"; then
    log "map recovery failed: service=$service partition=$partition_id reason=$reason"
    if [[ "$mode" == "--once" ]]; then
      return 1
    fi
  fi
}

seed_network_neighbors() {
  if [[ "$seed_neighbors" != "true" ]]; then
    return
  fi

  if [[ ! -x "$seed_command" ]]; then
    log "skip neighbor seeding; command is not executable: $seed_command"
    return
  fi

  if (( seed_timeout > 0 )) && command -v timeout >/dev/null 2>&1; then
    set +e
    timeout --kill-after=5s "${seed_timeout}s" env CONTAINER_RUNTIME="$container_runtime" "$seed_command" >/dev/null
    rc=$?
    set -e
    if (( rc != 0 )); then
      log "neighbor seeding failed or timed out: command=$seed_command rc=$rc timeout=${seed_timeout}s"
    fi
    return
  fi

  if ! CONTAINER_RUNTIME="$container_runtime" "$seed_command" >/dev/null; then
    log "neighbor seeding failed: command=$seed_command"
  fi
}

maybe_seed_network_neighbors() {
  local now

  if [[ "$mode" == "--status" || "$mode" == "--dry-run" ]]; then
    return
  fi

  if [[ "$mode" == "--once" ]]; then
    seed_network_neighbors
    return
  fi

  now="$(date +%s)"
  if (( last_seed > 0 && seed_interval > 0 && now - last_seed < seed_interval )); then
    return
  fi
  last_seed="$now"
  seed_network_neighbors
}

wait_if_paused() {
  if [[ -n "$mode" ]]; then
    return
  fi

  while [[ -e "$pause_file" ]]; do
    log "map watchdog paused: pause_file=$pause_file"
    sleep "$interval"
  done
}

check_once() {
  local item
  local service
  local partition_id
  local status
  local health
  local reason

  for item in "${MAP_PARTITIONS[@]}"; do
    service="${item%%:*}"
    partition_id="${item##*:}"
    if (( partition_id > partition_count )); then
      continue
    fi
    status="$(container_status "$service")"

    if [[ "$mode" == "--status" ]]; then
      health="$(partition_health "$partition_id")"
      printf '%-32s partition=%-2s status=%-10s db=\"%s\"\n' "$service" "$partition_id" "$status" "$health"
      continue
    fi

    case "$status" in
      running)
        if (( $(container_age_seconds "$service") < startup_grace )); then
          log "skip DB recovery during startup grace: service=$service partition=$partition_id"
          continue
        fi
        reason="$(partition_degraded_reason "$partition_id")"
        case "$reason" in
          ok)
            ;;
          health_unknown)
            log "skip recovery because partition health is unavailable: service=$service partition=$partition_id"
            ;;
          *)
            recover_service "$service" "$partition_id" "$reason"
            ;;
        esac
        ;;
      created|restarting|removing|paused)
        ;;
      exited|dead)
        recover_service "$service" "$partition_id" "$status"
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
  wait_if_paused
  check_once
  maybe_seed_network_neighbors
  if [[ "$mode" == "--once" || "$mode" == "--status" || "$mode" == "--dry-run" ]]; then
    exit 0
  fi
  sleep "$interval"
done
