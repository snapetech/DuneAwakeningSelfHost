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

container_runtime="${CONTAINER_RUNTIME:-docker}"
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
    if [[ "$alive_active" == "$expected" && "$active" == "$expected" && "$partitions" == "30" ]]; then
      printf 'ready enough: alive_active=%s active=%s partitions=%s\n' "$alive_active" "$active" "$partitions"
      return 0
    fi
    printf 'still starting: alive_active=%s active=%s partitions=%s\n' "${alive_active:-?}" "${active:-?}" "${partitions:-?}"
    sleep 10
  done

  printf '%s did not reach alive-active/active count %s within %s seconds\n' "$label" "$expected" "$wait_seconds" >&2
  return 1
}

remove_db_init

printf 'starting stateful dependencies without recreating existing containers\n'
"${compose[@]}" up -d --no-recreate postgres admin-rmq game-rmq
wait_for_healthy postgres
wait_for_healthy admin-rmq
wait_for_healthy game-rmq

printf 'ensuring 30 world partitions exist\n'
COMPOSE_FILES="${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}" CONTAINER_RUNTIME="$container_runtime" \
  "$(dirname "$0")/full-world-partitions.sh" "$env_file"

printf 'starting service layer without recreating existing containers\n'
"${compose[@]}" up -d --no-recreate \
  rmq-auth-shim text-router gateway director admin-panel admin-panel-ingress admin-chat-commands
"$(dirname "$0")/seed-gateway-neighbor.sh"

printf 'starting base travel maps\n'
"${compose[@]}" up -d --no-recreate survival overmap
wait_for_counts 2 'base travel maps'

printf 'starting base standing farm maps\n'
"${compose[@]}" up -d --no-recreate \
  arrakeen harko-village testing-hephaestus testing-carthag testing-waterfat \
  deep-desert proces-verbal
wait_for_counts 9 'base standing farm maps'

printf 'starting full warm-pool maps\n'
"${compose[@]}" up -d --no-recreate \
  lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab \
  art-of-kanly dungeon-hephaestus dungeon-oldcarthag \
  faction-outpost-atre faction-outpost-hark heighliner-dungeon \
  ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-195 ecolab-green-136 \
  overland-m-01 overland-s-04 overland-s-06 bandit-fortress \
  overland-s-07 overland-s-08 dungeon-thepit
wait_for_counts 30 'full warm pool'
remove_db_init

printf 'final status\n'
COMPOSE_FILES="${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}" CONTAINER_RUNTIME="$container_runtime" \
  "$(dirname "$0")/status.sh" "$env_file"
