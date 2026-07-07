#!/usr/bin/env bash
set -euo pipefail

env_file=".env"
database=""
commit="false"

required_host="${DUNE_JAMES_DD_MOVE_REQUIRED_HOST:-kspls0}"
source_partition="${DUNE_JAMES_DD_MOVE_SOURCE_PARTITION:-31}"
source_dimension="${DUNE_JAMES_DD_MOVE_SOURCE_DIMENSION:-1}"
target_partition="${DUNE_JAMES_DD_MOVE_TARGET_PARTITION:-8}"
target_dimension="${DUNE_JAMES_DD_MOVE_TARGET_DIMENSION:-0}"
totem_id="${DUNE_JAMES_DD_MOVE_TOTEM_ID:-24653}"
building_id="${DUNE_JAMES_DD_MOVE_BUILDING_ID:-24658}"
account_id="${DUNE_JAMES_DD_MOVE_ACCOUNT_ID:-6132}"
owner_entity_id="${DUNE_JAMES_DD_MOVE_OWNER_ENTITY_ID:-848448008818460409}"
expected_actor_count="${DUNE_JAMES_DD_MOVE_EXPECTED_ACTORS:-40}"
expected_piece_count="${DUNE_JAMES_DD_MOVE_EXPECTED_BUILDING_INSTANCES:-320}"

# Tight box around James Holden's DD2 base. This deliberately excludes a nearby
# unrelated buggy while including the owned totem, building base, and placeables.
min_x="${DUNE_JAMES_DD_MOVE_MIN_X:--930000}"
max_x="${DUNE_JAMES_DD_MOVE_MAX_X:--810000}"
min_y="${DUNE_JAMES_DD_MOVE_MIN_Y:-850000}"
max_y="${DUNE_JAMES_DD_MOVE_MAX_Y:-970000}"

usage() {
  cat <<'EOF'
Usage:
  scripts/move-james-dd2-base-to-dd1-db-surgery.sh [--env-file .env] [--database DB] [--commit]

Default mode validates and previews the direct DB surgery, then rolls back.
Commit mode requires:
  CONFIRM='MOVE JAMES DD2 BASE TO DD1'

This does not call BRT restore/copy/finish functions.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_file="${2:?missing value for --env-file}"
      shift 2
      ;;
    --database)
      database="${2:?missing value for --database}"
      shift 2
      ;;
    --commit)
      commit="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

database="${database:-${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}}"
database="${database:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
database="${database:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
database="${database:-dune_sb_1_4_0_0}"

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_JAMES_DD_MOVE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  printf "ERROR: refusing to run on host '%s'; required '%s'.\n" "$short_host" "$required_host" >&2
  exit 1
fi

if [[ "$commit" == "true" && "${CONFIRM:-}" != "MOVE JAMES DD2 BASE TO DD1" ]]; then
  printf "ERROR: --commit requires CONFIRM='MOVE JAMES DD2 BASE TO DD1'.\n" >&2
  exit 1
fi

container_runtime="${CONTAINER_RUNTIME:-docker}"
if [[ -x "scripts/compose-files.sh" ]]; then
  COMPOSE_FILES="$(scripts/compose-files.sh "$env_file")"
  export COMPOSE_FILES
fi
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

psql_db() {
  "${compose[@]}" exec -T postgres \
    psql -U dune -d "$database" -v ON_ERROR_STOP=1 -P pager=off "$@"
}

connected_players="$(
  psql_db -qAt \
    -v source_partition="$source_partition" \
    -v target_partition="$target_partition" <<'SQL'
with wanted(partition_id) as (
  values (:'source_partition'::bigint), (:'target_partition'::bigint)
)
select coalesce(sum(coalesce(fs.connected_players, 0)), 0)::integer
from wanted w
join dune.world_partition wp on wp.partition_id=w.partition_id
left join dune.farm_state fs on fs.server_id=wp.server_id;
SQL
)"

if [[ "$commit" == "true" && "${connected_players:-0}" != "0" ]]; then
  printf 'ERROR: refusing commit while DD1/DD2 connected_players=%s.\n' "$connected_players" >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_prefix="op_james_dd2_to_dd1_${stamp}"
end_statement="rollback;"
mode="ROLLBACK"
if [[ "$commit" == "true" ]]; then
  end_statement="commit;"
  mode="COMMIT"
fi

printf 'mode=%s host=%s db=%s connected_players=%s source=%s/%s target=%s/%s totem=%s building=%s\n' \
  "$mode" "$short_host" "$database" "$connected_players" \
  "$source_partition" "$source_dimension" "$target_partition" "$target_dimension" "$totem_id" "$building_id"

psql_db \
  -v commit_mode="$commit" \
  -v backup_prefix="$backup_prefix" \
  -v end_statement="$end_statement" \
  -v source_partition="$source_partition" \
  -v source_dimension="$source_dimension" \
  -v target_partition="$target_partition" \
  -v target_dimension="$target_dimension" \
  -v totem_id="$totem_id" \
  -v building_id="$building_id" \
  -v account_id="$account_id" \
  -v owner_entity_id="$owner_entity_id" \
  -v expected_actor_count="$expected_actor_count" \
  -v expected_piece_count="$expected_piece_count" \
  -v min_x="$min_x" \
  -v max_x="$max_x" \
  -v min_y="$min_y" \
  -v max_y="$max_y" <<'SQL'
begin;

create temp table move_actor_ids as
select a.id
from dune.actors a
where a.partition_id = :'source_partition'::bigint
  and a.dimension_index = :'source_dimension'::integer
  and (((a.transform).location).x) between :'min_x'::float8 and :'max_x'::float8
  and (((a.transform).location).y) between :'min_y'::float8 and :'max_y'::float8
  and (
    a.id in (:'totem_id'::bigint, :'building_id'::bigint)
    or a.owner_account_id = :'account_id'::bigint
    or a.id in (
      select id from dune.placeables
      where owner_entity_id = :'owner_entity_id'::bigint
    )
    or a.id in (
      select instance_id from dune.building_instances
      where owner_entity_id = :'owner_entity_id'::bigint
    )
  );

select
  'preflight_partitions' as section,
  wp.partition_id,
  wp.map,
  wp.dimension_index,
  wp.label,
  coalesce(fs.connected_players, 0) as connected_players,
  fs.ready,
  fs.alive
from dune.world_partition wp
left join dune.farm_state fs on fs.server_id=wp.server_id
where wp.partition_id in (:'source_partition'::bigint, :'target_partition'::bigint)
order by wp.partition_id;

select
  'preflight_counts' as section,
  (select count(*) from move_actor_ids) as actor_count,
  (select count(*) from dune.building_instances where building_id=:'building_id'::bigint) as building_instance_count,
  (select count(*) from move_actor_ids where id=:'totem_id'::bigint) as totem_selected,
  (select count(*) from move_actor_ids where id=:'building_id'::bigint) as building_selected,
  (select count(*) from dune.permission_actor_rank where permission_actor_id=:'totem_id'::bigint and player_id=19522 and rank=1) as james_owner_rank;

select
  'actor_classes' as section,
  regexp_replace(a.class, '^.*/', '') as class_name,
  count(*)
from move_actor_ids m
join dune.actors a on a.id=m.id
group by class_name
order by count desc, class_name;

select set_config('op.source_partition', :'source_partition', true);
select set_config('op.source_dimension', :'source_dimension', true);
select set_config('op.target_partition', :'target_partition', true);
select set_config('op.target_dimension', :'target_dimension', true);
select set_config('op.totem_id', :'totem_id', true);
select set_config('op.building_id', :'building_id', true);
select set_config('op.expected_actor_count', :'expected_actor_count', true);
select set_config('op.expected_piece_count', :'expected_piece_count', true);
select set_config('op.commit_mode', :'commit_mode', true);
select set_config('op.backup_prefix', :'backup_prefix', true);

do $$
declare
  actor_count integer;
  piece_count integer;
  target_count integer;
  source_count integer;
  totem_selected integer;
  building_selected integer;
  owner_rank integer;
begin
  select count(*) into actor_count from move_actor_ids;
  select count(*) into piece_count from dune.building_instances where building_id=current_setting('op.building_id')::bigint;
  select count(*) into source_count from dune.world_partition where partition_id=current_setting('op.source_partition')::bigint and dimension_index=current_setting('op.source_dimension')::integer;
  select count(*) into target_count from dune.world_partition where partition_id=current_setting('op.target_partition')::bigint and dimension_index=current_setting('op.target_dimension')::integer;
  select count(*) into totem_selected from move_actor_ids where id=current_setting('op.totem_id')::bigint;
  select count(*) into building_selected from move_actor_ids where id=current_setting('op.building_id')::bigint;
  select count(*) into owner_rank
  from dune.permission_actor_rank
  where permission_actor_id=current_setting('op.totem_id')::bigint and player_id=19522 and rank=1;

  if source_count <> 1 then
    raise exception 'source partition/dimension validation failed';
  end if;
  if target_count <> 1 then
    raise exception 'target partition/dimension validation failed';
  end if;
  if actor_count <> current_setting('op.expected_actor_count')::integer then
    raise exception 'expected % actors, got %', current_setting('op.expected_actor_count'), actor_count;
  end if;
  if piece_count <> current_setting('op.expected_piece_count')::integer then
    raise exception 'expected % building instances, got %', current_setting('op.expected_piece_count'), piece_count;
  end if;
  if totem_selected <> 1 or building_selected <> 1 then
    raise exception 'totem/building selection failed: totem %, building %', totem_selected, building_selected;
  end if;
  if owner_rank <> 1 then
    raise exception 'James owner rank validation failed';
  end if;
end $$;

do $$
declare
  prefix text := current_setting('op.backup_prefix');
begin
  if current_setting('op.commit_mode')::boolean then
    execute format('create table dune.%I as select * from dune.actors where id in (select id from move_actor_ids)', prefix || '_actors');
    execute format('create table dune.%I as select * from dune.building_instances where building_id = %s', prefix || '_building_instances', current_setting('op.building_id')::bigint);
    execute format('create table dune.%I as select * from dune.totems where id = %s', prefix || '_totems', current_setting('op.totem_id')::bigint);
    execute format('create table dune.%I as select * from dune.landclaim_segments where totem_id = %s', prefix || '_landclaim_segments', current_setting('op.totem_id')::bigint);
    execute format('create table dune.%I as select * from dune.permission_actor where actor_id = %s', prefix || '_permission_actor', current_setting('op.totem_id')::bigint);
    execute format('create table dune.%I as select * from dune.permission_actor_rank where permission_actor_id = %s', prefix || '_permission_actor_rank', current_setting('op.totem_id')::bigint);
  end if;
end $$;

update dune.actors
set
  partition_id = :'target_partition'::bigint,
  dimension_index = :'target_dimension'::integer
where id in (select id from move_actor_ids);

select
  'updated_counts' as section,
  (select count(*) from dune.actors where id in (select id from move_actor_ids) and partition_id=:'target_partition'::bigint and dimension_index=:'target_dimension'::integer) as actors_now_target,
  (select count(*) from dune.building_instances where building_id=:'building_id'::bigint) as building_instances_unchanged,
  (select count(*) from dune.landclaim_segments where totem_id=:'totem_id'::bigint) as landclaim_segments;

select
  'totem_after_in_tx' as section,
  a.id,
  a.map,
  a.partition_id,
  a.dimension_index,
  ((a.transform).location).x::int as x,
  ((a.transform).location).y::int as y,
  ((a.transform).location).z::int as z,
  wp.label
from dune.actors a
left join dune.world_partition wp on wp.partition_id=a.partition_id
where a.id=:'totem_id'::bigint;

:end_statement
SQL
