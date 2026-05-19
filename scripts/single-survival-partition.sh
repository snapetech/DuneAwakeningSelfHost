#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")
db=dune_sb_1_4_0_0
backup_dir=backups/partition-surgery

case "$backup_dir" in
  backups/*) ;;
  *)
    printf 'refusing to write partition backup outside ignored backups/: %s\n' "$backup_dir" >&2
    exit 1
    ;;
esac

mkdir -p "$backup_dir"
backup_file="$backup_dir/world-partitions-before-single-survival-$(date -u +%Y%m%dT%H%M%SZ).sql"

"${compose[@]}" exec -T postgres pg_dump \
  -U dune \
  -d "$db" \
  -t dune.world_partition \
  -t dune.world_partition_reset_seed \
  --data-only \
  --column-inserts \
  > "$backup_file"

echo "wrote backup: $backup_file"

"${compose[@]}" stop survival director

"${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 <<'SQL'
begin;
delete from dune.world_partition
where map = 'Survival_1'
  and dimension_index > 0
  and coalesce(server_id, '') = '';
commit;

select partition_id, server_id, map, dimension_index, label
from dune.world_partition
order by partition_id;
SQL

"${compose[@]}" up -d director survival
