#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/dd2-only-shift.sh [options]

Advances only DD#2's partition seed and restarts only the DD#2 service.
Farm seed, Deep Desert map seed, and DD#1 partition seed are guarded.

Options:
  --execute             Required for live mutation. Without it, dry-run only.
  --env-file FILE       Env file. Default: .env
  --seed N              Explicit DD#2 seed. Default: max existing seed + 1
  --warning-seconds N   Player warning delay before DD2 restart. Default: 300
  --skip-warning        Do not announce/sleep.
  --no-restart          Apply/plan seed only; do not restart DD2.
  -h, --help            Show this help.

Environment:
  DUNE_DD2_ONLY_REQUIRED_HOST  Required live hostname. Default: kspls0
  DUNE_DD2_ONLY_SERVICE        DD#2 service. Default: deep-desert-pvp
  DUNE_DD2_ONLY_PARTITION_ID   DD#2 partition id. Default: 31
  DUNE_DD1_PARTITION_ID        DD#1 partition id. Default: 8
USAGE
}

execute=false
env_file=".env"
explicit_seed=""
warning_seconds=300
skip_warning=false
restart_dd2=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      execute=true
      shift
      ;;
    --env-file)
      env_file="${2:-}"
      shift 2
      ;;
    --seed)
      explicit_seed="${2:-}"
      shift 2
      ;;
    --warning-seconds)
      warning_seconds="${2:-}"
      shift 2
      ;;
    --skip-warning)
      skip_warning=true
      shift
      ;;
    --no-restart)
      restart_dd2=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi
if [[ -n "$explicit_seed" && ! "$explicit_seed" =~ ^[0-9]+$ ]]; then
  printf 'seed must be an integer: %s\n' "$explicit_seed" >&2
  exit 2
fi
if [[ ! "$warning_seconds" =~ ^[0-9]+$ ]]; then
  printf 'warning seconds must be an integer: %s\n' "$warning_seconds" >&2
  exit 2
fi

required_host="${DUNE_DD2_ONLY_REQUIRED_HOST:-kspls0}"
service="${DUNE_DD2_ONLY_SERVICE:-deep-desert-pvp}"
dd2_partition="${DUNE_DD2_ONLY_PARTITION_ID:-31}"
dd1_partition="${DUNE_DD1_PARTITION_ID:-8}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
runtime="${CONTAINER_RUNTIME:-docker}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose=("$runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

host_name() {
  hostname -s 2>/dev/null || hostname 2>/dev/null || true
}

assert_live_host() {
  local actual
  actual="$(host_name)"
  if [[ "$actual" != "$required_host" ]]; then
    printf 'refusing live mutation: hostname is %s, required %s\n' "${actual:-unknown}" "$required_host" >&2
    exit 1
  fi
}

psql_live() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 "$@"
}

summary_sql='
select
  (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
  (select world_reset_seed from dune.world_map_reset_seed where map in ('\''DeepDesert'\'','\''DeepDesert_1'\'') order by map limit 1) as deep_desert_map_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = 8) as dd1_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = 31) as dd2_seed,
  (select count(*) from dune.shiftingsands_data) as static_shifting_rows;
'

print_summary() {
  printf '\n== %s ==\n' "$1"
  psql_live -P pager=off -c "$summary_sql"
  psql_live -P pager=off -c "
    select partition_id, map, dimension_index, label
    from dune.world_partition
    where partition_id in (${dd1_partition}, ${dd2_partition})
    order by partition_id;
  "
}

announce_and_wait() {
  if [[ "$skip_warning" == true ]]; then
    printf 'warning skipped by --skip-warning\n'
    return 0
  fi
  local minutes
  minutes=$(( (warning_seconds + 59) / 60 ))
  DUNE_ANNOUNCE_MESSAGE="DD#2 maintenance in ${minutes} minutes. DD#1 should remain online; please get to a safe place if you are in DD#2." \
    "$script_dir/announce.sh"
  printf 'sent player warning; sleeping %s seconds\n' "$warning_seconds"
  sleep "$warning_seconds"
}

make_safety_backup() {
  local stamp dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dir="backups/manual/dd2-only-shift-${stamp}"
  mkdir -p "$dir"
  cp "$env_file" "$dir/$(basename "$env_file")"
  "${compose[@]}" exec -T postgres pg_dump -U dune -d "$db" -Fc > "$dir/postgres-${db}.dump"
  cat > "$dir/manifest.txt" <<EOF
created_utc=${stamp}
reason=dd2-only partition seed shift
service=${service}
dd1_partition=${dd1_partition}
dd2_partition=${dd2_partition}
database=${db}
compose_files=${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}
EOF
  printf 'safety_backup=%s\n' "$dir"
}

stop_dd2() {
  [[ "$restart_dd2" == true ]] || return 0
  "${compose[@]}" stop -t 30 "$service"
}

start_dd2() {
  [[ "$restart_dd2" == true ]] || return 0
  "${compose[@]}" up -d --force-recreate --no-deps "$service"
}

apply_seed() {
  local seed_expr
  if [[ -n "$explicit_seed" ]]; then
    seed_expr="$explicit_seed"
  else
    seed_expr="null"
  fi
  psql_live -v dd1="$dd1_partition" -v dd2="$dd2_partition" -v requested_seed="$seed_expr" -P pager=off <<'SQL'
begin;
lock table dune.world_farm_reset_seed, dune.world_map_reset_seed, dune.world_partition_reset_seed in exclusive mode;

create temporary table dd2_only_params on commit drop as
select :dd1::integer as dd1, :dd2::integer as dd2;

create temporary table dd2_only_before on commit drop as
select
  (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
  (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) as map_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = :dd1) as dd1_seed;

with seed_input as (
  select nullif(:'requested_seed', 'null')::integer as requested_seed
),
next_seed as (
  select coalesce(
    requested_seed,
    greatest(
      coalesce((select max(world_reset_seed) from dune.world_farm_reset_seed), 0),
      coalesce((select max(world_reset_seed) from dune.world_map_reset_seed), 0),
      coalesce((select max(world_reset_seed) from dune.world_partition_reset_seed), 0)
    ) + 1
  ) as value
  from seed_input
)
insert into dune.world_partition_reset_seed(partition_id, world_reset_seed)
select :dd2, value from next_seed
on conflict(partition_id) do update
set world_reset_seed = excluded.world_reset_seed;

do $$
declare
  dd1_partition integer;
  before_farm integer;
  before_map integer;
  before_dd1 integer;
  after_farm integer;
  after_map integer;
  after_dd1 integer;
begin
  select dd1 into dd1_partition from dd2_only_params;

  select farm_seed, map_seed, dd1_seed
  into before_farm, before_map, before_dd1
  from dd2_only_before;

  select world_reset_seed into after_farm
  from dune.world_farm_reset_seed
  where onerow_id = true;

  select world_reset_seed into after_map
  from dune.world_map_reset_seed
  where map in ('DeepDesert','DeepDesert_1')
  order by map
  limit 1;

  select world_reset_seed into after_dd1
  from dune.world_partition_reset_seed
  where partition_id = dd1_partition;

  if before_farm is distinct from after_farm then
    raise exception 'farm seed changed: % -> %', before_farm, after_farm;
  end if;
  if before_map is distinct from after_map then
    raise exception 'Deep Desert map seed changed: % -> %', before_map, after_map;
  end if;
  if before_dd1 is distinct from after_dd1 then
    raise exception 'DD#1 seed changed: % -> %', before_dd1, after_dd1;
  end if;
end $$;

notify world_partition_update;

select
  (select farm_seed from dd2_only_before) as farm_seed_unchanged,
  (select map_seed from dd2_only_before) as map_seed_unchanged,
  (select dd1_seed from dd2_only_before) as dd1_seed_unchanged,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = :dd2) as dd2_seed;

commit;
SQL
}

main() {
  printf 'host=%s required_host=%s execute=%s service=%s restart=%s\n' "$(host_name)" "$required_host" "$execute" "$service" "$restart_dd2"
  print_summary "before"
  if [[ "$execute" != true ]]; then
    printf '\ndry-run complete; rerun with --execute to mutate production\n'
    exit 0
  fi

  assert_live_host
  announce_and_wait
  stop_dd2
  make_safety_backup
  apply_seed
  print_summary "after seed"
  start_dd2
  print_summary "after start request"
  "${compose[@]}" ps "$service"
}

main
