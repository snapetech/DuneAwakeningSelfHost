#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env.handoff-lab}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
project="${COMPOSE_PROJECT_NAME:-dune_handoff_lab}"
runtime="${CONTAINER_RUNTIME:-docker}"
compose_files=(compose.yaml compose.handoff-lab.yaml compose.research-dd-lab.yaml)

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi

run_compose() {
  COMPOSE_PROJECT_NAME="$project" "$runtime" compose --env-file "$env_file" \
    -f "${compose_files[0]}" -f "${compose_files[1]}" -f "${compose_files[2]}" "$@"
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

wait_for_postgres

run_compose exec -T postgres psql -U dune -d "$db" <<'SQL'
insert into dune.world_partition (partition_id, map, dimension_index, partition_definition, label)
values
  (1, 'Survival_1', 0, '{"box":{"max_x":1,"max_y":1,"min_x":0,"min_y":0},"type":"box2d_array"}'::jsonb, 'Hagga Basin'),
  (8, 'DeepDesert_1', 0, '{"box":{"max_x":1,"max_y":1,"min_x":0,"min_y":0},"type":"box2d_array"}'::jsonb, 'PVE Casual'),
  (31, 'DeepDesert_1', 1, '{"box":{"max_x":1,"max_y":1,"min_x":0,"min_y":0},"type":"box2d_array"}'::jsonb, 'PVE Hardcore')
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
where partition_id in (1, 8, 31)
order by partition_id;
SQL
