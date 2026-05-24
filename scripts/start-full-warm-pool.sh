#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/start-full-warm-pool.sh [ENV_FILE] [WAIT_SECONDS]

Starts the 30-partition warm pool in dependency order without recreating
already-running stateful services.

Default:
  scripts/start-full-warm-pool.sh .env 600
USAGE
}

if [[ $# -gt 2 ]]; then
  usage
  exit 2
fi

env_file="${1:-.env}"
wait_seconds="${2:-600}"
if [[ ! "$wait_seconds" =~ ^[0-9]+$ ]]; then
  printf 'wait seconds must be numeric: %s\n' "$wait_seconds" >&2
  exit 2
fi

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

batch_size="${DUNE_WARM_POOL_BATCH_SIZE:-0}"
batch_delay="${DUNE_WARM_POOL_BATCH_DELAY:-20}"
if [[ ! "$batch_size" =~ ^[0-9]+$ || ! "$batch_delay" =~ ^[0-9]+$ ]]; then
  printf 'DUNE_WARM_POOL_BATCH_SIZE and DUNE_WARM_POOL_BATCH_DELAY must be numeric\n' >&2
  exit 2
fi
partition_count="${DUNE_WORLD_PARTITION_COUNT:-$(read_env DUNE_WORLD_PARTITION_COUNT)}"
partition_count="${partition_count:-30}"
if [[ "$partition_count" != "30" ]]; then
  printf 'DUNE_WORLD_PARTITION_COUNT must be 30; partition 31 Deep Desert PvP is intentionally disabled, got: %s\n' "$partition_count" >&2
  exit 2
fi

container_runtime="${CONTAINER_RUNTIME:-docker}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")
db=dune_sb_1_4_0_0

psql_at() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "$1"
}

remove_db_init() {
  local container_id

  container_id="$("${compose[@]}" ps -aq db-init 2>/dev/null || true)"
  if [[ -n "$container_id" ]]; then
    printf 'removing stale one-shot db-init container\n'
    "$container_runtime" rm -f "$container_id" >/dev/null
  fi
}

wait_for_healthy() {
  local service="$1"
  local container_id
  local status

  container_id="$("${compose[@]}" ps -q "$service")"
  if [[ -z "$container_id" ]]; then
    printf 'service is not running: %s\n' "$service" >&2
    return 1
  fi

  for _ in {1..90}; do
    status="$("$container_runtime" inspect \
      --format '{{ if .State.Health }}{{ .State.Health.Status }}{{ else }}running{{ end }}' \
      "$container_id")"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      return 0
    fi
    sleep 2
  done

  printf 'service did not become healthy: %s\n' "$service" >&2
  return 1
}

wait_for_counts() {
  local expected="$1"
  local label="$2"
  local deadline=$((SECONDS + wait_seconds))
  local row
  local alive_active
  local active
  local partitions

  printf 'waiting for %s: expected=%s\n' "$label" "$expected"
  while (( SECONDS < deadline )); do
    row="$(psql_at "
      select
        count(*) filter (where fs.alive and asi.server_id is not null) || ' ' ||
        count(*) filter (where asi.server_id is not null) || ' ' ||
        count(*)
      from dune.world_partition wp
      left join dune.farm_state fs on fs.server_id = wp.server_id
      left join dune.active_server_ids asi on asi.server_id = wp.server_id;
    ")"
    read -r alive_active active partitions <<< "$row"
    if (( alive_active >= expected && active >= expected )) && [[ "$partitions" == "$partition_count" ]]; then
      printf 'ready enough: alive_active=%s active=%s partitions=%s\n' "$alive_active" "$active" "$partitions"
      return 0
    fi
    printf 'still starting: alive_active=%s active=%s partitions=%s\n' "${alive_active:-?}" "${active:-?}" "${partitions:-?}"
    sleep 10
  done

  printf '%s did not reach alive-active/active count %s with %s partitions within %s seconds\n' "$label" "$expected" "$partition_count" "$wait_seconds" >&2
  return 1
}

start_services() {
  local services=("$@")
  local batch=()
  local service

  if (( batch_size <= 0 )); then
    "${compose[@]}" up -d --no-recreate "${services[@]}"
    return
  fi

  for service in "${services[@]}"; do
    batch+=("$service")
    if (( ${#batch[@]} >= batch_size )); then
      "${compose[@]}" up -d --no-recreate "${batch[@]}"
      batch=()
      sleep "$batch_delay"
    fi
  done

  if (( ${#batch[@]} > 0 )); then
    "${compose[@]}" up -d --no-recreate "${batch[@]}"
  fi
}

remove_db_init

printf 'starting stateful dependencies without recreating existing containers\n'
"${compose[@]}" up -d --no-recreate postgres admin-rmq game-rmq
wait_for_healthy postgres
wait_for_healthy admin-rmq
wait_for_healthy game-rmq

printf 'ensuring %s world partitions exist\n' "$partition_count"
COMPOSE_FILES="$COMPOSE_FILES" CONTAINER_RUNTIME="$container_runtime" \
  "$script_dir/full-world-partitions.sh" "$env_file"

printf 'starting service layer without recreating existing containers\n'
"${compose[@]}" up -d --no-recreate \
  rmq-auth-shim text-router gateway director admin-panel admin-panel-ingress admin-chat-commands
"$script_dir/seed-gateway-neighbor.sh"

printf 'starting base 3 maps\n'
start_services survival overmap arrakeen
wait_for_counts 3 'base 3 maps'

printf 'starting maps 4 through 9\n'
start_services \
  harko-village testing-hephaestus testing-carthag testing-waterfat \
  deep-desert proces-verbal
wait_for_counts 9 'maps 1 through 9'

printf 'starting maps 10 through 30\n'
start_services \
  lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab \
  art-of-kanly dungeon-hephaestus dungeon-oldcarthag \
  faction-outpost-atre faction-outpost-hark heighliner-dungeon \
  ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-195 ecolab-green-136 \
  overland-m-01 overland-s-04 overland-s-06 bandit-fortress \
  overland-s-07 overland-s-08 dungeon-thepit
wait_for_counts 30 'maps 1 through 30'

printf 'partition 31 Deep Desert PvP is intentionally disabled; ensuring the old service is stopped\n'
"${compose[@]}" stop deep-desert-pvp >/dev/null 2>&1 || true
remove_db_init

printf 'final status\n'
COMPOSE_FILES="$COMPOSE_FILES" CONTAINER_RUNTIME="$container_runtime" \
  "$script_dir/status.sh" "$env_file"
