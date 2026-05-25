#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
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
backup_dir=backups/partition-surgery

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

partition_count="${DUNE_WORLD_PARTITION_COUNT:-$(read_env DUNE_WORLD_PARTITION_COUNT)}"
partition_count="${partition_count:-30}"
case "$partition_count" in
  30|31) ;;
  *)
    printf 'DUNE_WORLD_PARTITION_COUNT must be 30, or 31 to intentionally enable the second Deep Desert; got: %s\n' "$partition_count" >&2
    exit 2
    ;;
esac

case "$backup_dir" in
  backups/*) ;;
  *)
    printf 'refusing to write partition backup outside ignored backups/: %s\n' "$backup_dir" >&2
    exit 1
    ;;
esac

mkdir -p "$backup_dir"
backup_file="$backup_dir/world-partitions-before-full-world-$(date -u +%Y%m%dT%H%M%SZ).sql"

"${compose[@]}" exec -T postgres pg_dump \
  -U dune \
  -d "$db" \
  --schema=dune \
  --table=dune.world_partition \
  --data-only \
  > "$backup_file"

printf 'wrote backup: %s\n' "$backup_file"

"${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -v partition_count="$partition_count" <<'SQL'
begin;

with desired(partition_id, map, dimension_index, label) as (
  values
    (1, 'Survival_1', 0, null),
    (2, 'Overmap', 0, null),
    (3, 'SH_Arrakeen', 0, null),
    (4, 'SH_HarkoVillage', 0, null),
    (5, 'CB_Story_Hephaestus', 0, null),
    (6, 'CB_Story_Ecolab_Carthag', 0, null),
    (7, 'CB_Story_WaterFatManor', 0, null),
    (8, 'DeepDesert_1', 0, 'Deep Desert PvE'),
    (9, 'Story_ProcesVerbal', 0, null),
    (10, 'DLC_Story_LostHarvest_EcolabA', 0, null),
    (11, 'DLC_Story_LostHarvest_EcolabB', 0, null),
    (12, 'DLC_Story_LostHarvest_ForgottenLab', 0, null),
    (13, 'Story_ArtOfKanly', 0, null),
    (14, 'CB_Dungeon_Hephaestus', 0, null),
    (15, 'CB_Dungeon_OldCarthag', 0, null),
    (16, 'Story_Faction_Outpost_Atre', 0, null),
    (17, 'Story_Faction_Outpost_Hark', 0, null),
    (18, 'Story_HeighlinerDungeon', 0, null),
    (19, 'CB_Ecolab_Bronze_Green_089', 0, null),
    (20, 'CB_Ecolab_Bronze_Green_152', 0, null),
    (21, 'CB_Ecolab_Bronze_Green_024', 0, null),
    (22, 'CB_Ecolab_Bronze_Green_195', 0, null),
    (23, 'CB_Ecolab_Bronze_Green_136', 0, null),
    (24, 'CB_Overland_M_01', 0, null),
    (25, 'CB_Overland_S_04', 0, null),
    (26, 'CB_Overland_S_06', 0, null),
    (27, 'CB_Story_BanditFortress01', 0, null),
    (28, 'CB_Overland_S_07', 0, null),
    (29, 'CB_Overland_S_08', 0, null),
    (30, 'CB_Dungeon_ThePit', 0, null),
    (31, 'DeepDesert_1', 1, 'Deep Desert PvP')
),
definition as (
  select '{"box": {"max_x": 1, "max_y": 1, "min_x": 0, "min_y": 0}, "type": "box2d_array"}'::jsonb as value
)
insert into dune.world_partition (partition_id, map, dimension_index, partition_definition, label)
select d.partition_id, d.map, d.dimension_index, definition.value, d.label
from desired d
cross join definition
where d.partition_id <= :partition_count
  and not exists (
    select 1
    from dune.world_partition wp
    where wp.map = d.map
      and wp.dimension_index = d.dimension_index
  );

with desired(partition_id, label) as (
  values
    (8, 'Deep Desert PvE'),
    (31, case when :partition_count >= 31 then 'Deep Desert PvP' else null end)
)
update dune.world_partition wp
set label = desired.label
from desired
where wp.partition_id = desired.partition_id
  and desired.label is not null;

update dune.actors
set partition_id = null
where :partition_count < 31
  and partition_id in (
    select partition_id
    from dune.world_partition
    where partition_id > :partition_count
      and map = 'DeepDesert_1'
      and dimension_index = 1
  );

delete from dune.world_partition_reset_seed
where not exists (
  select 1 from dune.world_partition wp
  where wp.partition_id = world_partition_reset_seed.partition_id
)
or (
  :partition_count < 31
  and partition_id in (
    select partition_id
    from dune.world_partition
    where partition_id > :partition_count
      and map = 'DeepDesert_1'
      and dimension_index = 1
  )
);

delete from dune.world_partition wp
where :partition_count < 31
  and wp.partition_id > :partition_count
  and wp.map = 'DeepDesert_1'
  and wp.dimension_index = 1;

select setval(
  'dune.world_partition_partition_id_seq',
  greatest(
    (select coalesce(max(partition_id), 1) from dune.world_partition),
    (select last_value from dune.world_partition_partition_id_seq)
  )
);

select dune.update_partition_labels(false);
notify world_partition_update;

commit;

select partition_id, server_id, map, dimension_index, label
from dune.world_partition
order by partition_id;
SQL
