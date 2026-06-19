#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/recover-map.sh ENV_FILE SERVICE PARTITION_ID [WAIT_SECONDS]

Safely restarts a fixed-partition map service by marking the current partition
owner dead, waiting for that server id to leave active_server_ids, then starting
the service and waiting for the partition to be ready/alive again.

Example:
  ./scripts/recover-map.sh .env heighliner-dungeon 18
USAGE
}

if [[ $# -lt 3 || $# -gt 4 ]]; then
  usage
  exit 2
fi

env_file="$1"
service="$2"
partition_id="$3"
wait_seconds="${4:-180}"

if [[ ! "$partition_id" =~ ^[0-9]+$ ]]; then
  printf 'partition id must be numeric: %s\n' "$partition_id" >&2
  exit 2
fi

if [[ ! "$wait_seconds" =~ ^[0-9]+$ ]]; then
  printf 'wait seconds must be numeric: %s\n' "$wait_seconds" >&2
  exit 2
fi

container_runtime="${CONTAINER_RUNTIME:-docker}"
seed_timeout="${DUNE_RECOVER_MAP_SEED_TIMEOUT_SECONDS:-90}"
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

if [[ ! "$seed_timeout" =~ ^[0-9]+$ ]]; then
  printf 'DUNE_RECOVER_MAP_SEED_TIMEOUT_SECONDS must be numeric\n' >&2
  exit 2
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\''"]|["'\''"]$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

db="${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}"
db="${db:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
db="${db:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
db="${db:-dune_sb_1_4_0_0}"

psql() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" "$@"
}

wait_for_healthy() {
  local dependency="$1"
  local container_id
  local status

  container_id="$("${compose[@]}" ps -q "$dependency")"
  if [[ -z "$container_id" ]]; then
    printf 'service is not running: %s\n' "$dependency" >&2
    return 1
  fi

  for _ in {1..60}; do
    status="$("$container_runtime" inspect \
      --format '{{ if .State.Health }}{{ .State.Health.Status }}{{ else }}running{{ end }}' \
      "$container_id")"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      return 0
    fi
    sleep 2
  done

  printf 'service did not become healthy: %s\n' "$dependency" >&2
  return 1
}

run_post_start_health() {
  case "${DUNE_RECOVER_MAP_POST_START_HEALTH_ENABLED:-true}" in
    1|true|yes|on|TRUE|True|YES|ON) ;;
    *) return 0 ;;
  esac

  if [[ -x "$script_dir/restart-post-start-health.sh" ]]; then
    printf 'running post-start health hooks\n'
    ENV_FILE="$env_file" "$script_dir/restart-post-start-health.sh"
  elif [[ -x "$script_dir/verify-rmq-auth-path.sh" ]]; then
    printf 'running post-start RMQ/auth verification\n'
    ENV_FILE="$env_file" "$script_dir/verify-rmq-auth-path.sh"
  fi
}

run_seed_neighbors() {
  case "${DUNE_RECOVER_MAP_SEED_NEIGHBORS_ENABLED:-true}" in
    1|true|yes|on|TRUE|True|YES|ON) ;;
    *) return 0 ;;
  esac

  if [[ ! -x "$script_dir/seed-gateway-neighbor.sh" ]]; then
    return 0
  fi

  printf 'seeding bridge neighbor entries\n'
  if (( seed_timeout > 0 )) && command -v timeout >/dev/null 2>&1; then
    if ! timeout --kill-after=5s "${seed_timeout}s" env CONTAINER_RUNTIME="$container_runtime" "$script_dir/seed-gateway-neighbor.sh"; then
      printf 'warning: bridge neighbor seeding failed or timed out after %ss\n' "$seed_timeout" >&2
    fi
  elif ! CONTAINER_RUNTIME="$container_runtime" "$script_dir/seed-gateway-neighbor.sh"; then
    printf 'warning: bridge neighbor seeding failed\n' >&2
  fi
}

printf 'starting stateful dependencies\n'
"${compose[@]}" up -d --no-recreate --no-deps postgres admin-rmq game-rmq
wait_for_healthy postgres
wait_for_healthy admin-rmq
wait_for_healthy game-rmq
run_seed_neighbors

old_server_id="$(psql -Atc "select coalesce(server_id, '') from dune.world_partition where partition_id = ${partition_id};")"
if [[ -z "$old_server_id" ]]; then
  printf 'partition %s has no current server_id\n' "$partition_id"
else
  printf 'marking old partition owner dead: partition=%s server_id=%s\n' "$partition_id" "$old_server_id"
  psql -v ON_ERROR_STOP=1 -c "select dune.mark_server_dead('${old_server_id}');" >/dev/null
fi

printf 'stopping map service: %s\n' "$service"
"${compose[@]}" stop "$service"

if [[ -n "$old_server_id" ]]; then
  printf 'waiting for old server id to leave active_server_ids\n'
  deadline=$((SECONDS + wait_seconds))
  while (( SECONDS < deadline )); do
    active_count="$(psql -Atc "select count(*) from dune.active_server_ids where server_id = '${old_server_id}';")"
    if [[ "$active_count" == "0" ]]; then
      break
    fi
    sleep 5
  done

  if [[ "${active_count:-1}" != "0" ]]; then
    printf 'old server id is still active after %s seconds: %s\n' "$wait_seconds" "$old_server_id" >&2
    exit 1
  fi
fi

printf 'starting/recreating map service: %s\n' "$service"
"${compose[@]}" up -d --force-recreate --no-deps "$service"
run_seed_neighbors

printf 'waiting for partition %s to become ready/alive/active\n' "$partition_id"
deadline=$((SECONDS + wait_seconds))
while (( SECONDS < deadline )); do
  ready_count="$(psql -Atc "
    select count(*)
    from dune.world_partition wp
    join dune.farm_state fs on fs.server_id = wp.server_id
    join dune.active_server_ids asi on asi.server_id = wp.server_id
    where wp.partition_id = ${partition_id}
      and fs.ready
      and fs.alive;
  ")"
  if [[ "$ready_count" == "1" ]]; then
    break
  fi
  sleep 5
done

if [[ "${ready_count:-0}" != "1" ]]; then
  printf 'partition %s did not become ready/alive/active after %s seconds\n' "$partition_id" "$wait_seconds" >&2
  exit 1
fi

run_post_start_health

psql -c "
select wp.partition_id, wp.server_id, wp.map, fs.ready, fs.alive, asi.server_id is not null as active
from dune.world_partition wp
join dune.farm_state fs on fs.server_id = wp.server_id
left join dune.active_server_ids asi on asi.server_id = wp.server_id
where wp.partition_id = ${partition_id};
"
