#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/brt-dd-lab.sh COMMAND [ENV_FILE]

Commands:
  config         Validate the isolated Deep Desert BRT lab Compose config.
  images         List required Compose images and whether they are cached.
  up             Start control services plus the Deep Desert PvE lab partition.
  seed           Ensure partition 8 is a DeepDesert_1 lab partition.
  status         Print lab health using the research Deep Desert overlay.
  verify-config  Verify DB partition and copied BRT/landclaim config.
  logs           Print recent high-signal Deep Desert BRT/building logs.
  stop           Stop the Deep Desert BRT lab services.

This uses COMPOSE_PROJECT_NAME=dune_handoff_lab by default and the lab-only
compose overlays. It is intended for kspld0/lab use, not production mutation.
USAGE
}

cmd="${1:-}"
env_file="${2:-.env.handoff-lab}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
project="${COMPOSE_PROJECT_NAME:-dune_handoff_lab}"
runtime="${CONTAINER_RUNTIME:-docker}"
service="${DUNE_BRT_DD_LAB_SERVICE:-deep-desert-lab-pve}"
compose_files=(compose.yaml compose.handoff-lab.yaml compose.research-dd-lab.yaml)
lab_services=(postgres admin-rmq game-rmq db-init text-router director gateway rmq-auth-shim "$service")
required_config_patterns=(
  'm_MaxLandclaimSegmentsPerMap=.*DeepDesert'
  'm_MaxLandclaimSegmentsPerMap=.*DeepDesert_1'
  'm_BaseBackupToolMapRestriction=.*DeepDesert'
  'm_BaseBackupToolMapRestriction=.*DeepDesert_1'
  'm_BaseBackupMaxExtensions=8'
  'm_bBuildingRestrictionLimitsEnabled=False'
)

if [[ -z "$cmd" || "$cmd" == "-h" || "$cmd" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$env_file" ]]; then
  printf 'missing lab env file: %s\n' "$env_file" >&2
  exit 2
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "", $0)
      print $0
    }
  ' "$env_file" | tail -n 1
}

if [[ -z "${WORLD_DATACENTER_ID:-}" ]]; then
  WORLD_DATACENTER_ID="$(env_value WORLD_DATACENTER_ID)"
  if [[ -z "$WORLD_DATACENTER_ID" ]]; then
    WORLD_DATACENTER_ID="$(env_value WORLD_REGION)"
  fi
  export WORLD_DATACENTER_ID
fi

run_compose() {
  COMPOSE_PROJECT_NAME="$project" "$runtime" compose --env-file "$env_file" \
    -f "${compose_files[0]}" -f "${compose_files[1]}" -f "${compose_files[2]}" "$@"
}

required_images() {
  run_compose config --images "${lab_services[@]}" | sort -u
}

check_images() {
  local missing=0
  local image
  while IFS= read -r image; do
    [[ -n "$image" ]] || continue
    if "$runtime" image inspect "$image" >/dev/null 2>&1; then
      printf 'cached %s\n' "$image"
    else
      printf 'missing %s\n' "$image"
      missing=1
    fi
  done < <(required_images)
  return "$missing"
}

wait_for_postgres() {
  local tries="${1:-60}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if run_compose exec -T postgres pg_isready -U dune -d "$db" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  printf 'lab Postgres did not become ready\n' >&2
  return 1
}

seed_dd_partition() {
  wait_for_postgres
  run_compose exec -T postgres psql -U dune -d "$db" <<'SQL'
insert into dune.world_partition (partition_id, map, dimension_index, partition_definition, label)
values
  (8, 'DeepDesert_1', 0, '{"box":{"max_x":1,"max_y":1,"min_x":0,"min_y":0},"type":"box2d_array"}'::jsonb, 'BRT Deep Desert Lab')
on conflict (partition_id) do update
set map = excluded.map,
    dimension_index = excluded.dimension_index,
    partition_definition = excluded.partition_definition,
    label = excluded.label;

select setval(
  pg_get_serial_sequence('dune.world_partition', 'partition_id'),
  greatest((select coalesce(max(partition_id), 1) from dune.world_partition), 1),
  true
);
select dune.update_partition_labels(false);
notify world_partition_update;
select partition_id, map, dimension_index, label
from dune.world_partition
where partition_id = 8;
SQL
}

start_lab() {
  check_images
  run_compose up -d postgres admin-rmq game-rmq db-init
  wait_for_postgres
  seed_dd_partition
  run_compose up -d text-router director gateway rmq-auth-shim "$service"
  verify_config
}

status_lab() {
  COMPOSE_PROJECT_NAME="$project" COMPOSE_FILES="$(IFS=:; printf '%s' "${compose_files[*]}")" ./scripts/status.sh "$env_file"
}

container_id() {
  run_compose ps -q "$service"
}

verify_db_partition() {
  local row
  row="$(run_compose exec -T postgres psql -U dune -d "$db" -Atc "
    select partition_id || '|' || map || '|' || dimension_index || '|' || coalesce(label, '')
    from dune.world_partition
    where partition_id = 8;
  ")"
  printf 'partition_8=%s\n' "${row:-missing}"
  [[ "$row" == 8\|DeepDesert_1\|0\|* ]]
}

verify_copied_config() {
  local id
  id="$(container_id)"
  if [[ -z "$id" ]]; then
    printf '%s is not created/running yet\n' "$service" >&2
    return 1
  fi

  local copied=/home/dune/server/DuneSandbox/Saved/UserSettings/UserGame.ini
  local rendered
  rendered="$("$runtime" exec "$id" sh -lc "test -f '$copied' && cat '$copied'")"
  for pattern in "${required_config_patterns[@]}"; do
    if ! grep -Eq "$pattern" <<<"$rendered"; then
      printf 'missing copied config pattern: %s\n' "$pattern" >&2
      return 1
    fi
  done
  printf 'copied_config=%s contains DeepDesert landclaim and BRT map restriction candidate\n' "$copied"
}

verify_config() {
  verify_db_partition
  verify_copied_config
}

show_logs() {
  run_compose logs --since="${DUNE_BRT_DD_LAB_LOG_SINCE:-30m}" --tail="${DUNE_BRT_DD_LAB_LOG_TAIL:-1200}" "$service" 2>&1 \
    | rg -n "BaseBackup|BuildingBlueprintBackupTool|CanBePlaced|Landclaim|BuildableMapRegion|BuildingRestriction|DeepDesert|Server farm is READY|READY|error|failed|Exception" -i \
    || true
}

stop_lab() {
  run_compose stop "$service" director gateway text-router rmq-auth-shim game-rmq admin-rmq postgres
}

case "$cmd" in
  config)
    run_compose config --quiet
    ;;
  images)
    check_images
    ;;
  up)
    start_lab
    ;;
  seed)
    seed_dd_partition
    ;;
  status)
    status_lab
    ;;
  verify-config)
    verify_config
    ;;
  logs)
    show_logs
    ;;
  stop)
    stop_lab
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
