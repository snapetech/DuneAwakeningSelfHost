#!/usr/bin/env bash
set -euo pipefail

env_file="${ENV_FILE:-.env}"
execute=false
seed="${DUNE_DD1_TEST_SEED:-1}"
warning_seconds="${DUNE_DD1_TEST_WARNING_SECONDS:-300}"
required_host="${DUNE_DD1_TEST_REQUIRED_HOST:-kspls0}"
service="${DUNE_DD1_SERVICE:-deep-desert}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
runtime="${CONTAINER_RUNTIME:-docker}"

case "${1:-}" in
  --execute) execute=true ;;
  -h|--help)
    cat <<'USAGE'
Usage: scripts/dd1-partition-seed-test.sh [--execute]

Sets only DD#1 partition seed to DUNE_DD1_TEST_SEED, default 1, and restarts
only the DD#1 service. Dry-run unless --execute is supplied.
USAGE
    exit 0
    ;;
  "") ;;
  *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi
if [[ ! "$seed" =~ ^[0-9]+$ ]]; then
  printf 'seed must be an integer: %s\n' "$seed" >&2
  exit 2
fi
if [[ ! "$warning_seconds" =~ ^[0-9]+$ ]]; then
  printf 'warning seconds must be an integer: %s\n' "$warning_seconds" >&2
  exit 2
fi

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

psql_live() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 "$@"
}

summary() {
  printf '\n== %s ==\n' "$1"
  psql_live -P pager=off -c "
    select
      (select world_reset_seed from dune.world_farm_reset_seed where onerow_id=true) farm_seed,
      (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) dd_map_seed,
      (select world_reset_seed from dune.world_partition_reset_seed where partition_id=8) dd1_seed,
      (select world_reset_seed from dune.world_partition_reset_seed where partition_id=31) dd2_seed;
    select wp.partition_id, wp.server_id, fs.ready, fs.alive, fs.connected_players
    from dune.world_partition wp
    left join dune.farm_state fs on fs.server_id=wp.server_id
    where wp.partition_id in (8,31)
    order by wp.partition_id;
  "
}

make_backup() {
  local stamp backup_dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="backups/manual/dd1-partition-seed-test-${stamp}"
  mkdir -p "$backup_dir"
  cp "$env_file" "$backup_dir/$(basename "$env_file")"
  "${compose[@]}" exec -T postgres pg_dump -U dune -d "$db" -Fc > "$backup_dir/postgres-${db}.dump"
  cat > "$backup_dir/manifest.txt" <<EOF
created_utc=${stamp}
reason=pre DD1 partition seed test
target_seed=${seed}
service=${service}
database=${db}
compose_files=${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}
EOF
  printf 'safety_backup=%s\n' "$backup_dir"
}

apply_seed() {
  psql_live -v target_seed="$seed" -P pager=off <<'SQL'
begin;
lock table dune.world_farm_reset_seed, dune.world_map_reset_seed, dune.world_partition_reset_seed in exclusive mode;
create temporary table dd1_seed_before on commit drop as
select
  (select world_reset_seed from dune.world_farm_reset_seed where onerow_id=true) as farm_seed,
  (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) as map_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id=31) as dd2_seed;

insert into dune.world_partition_reset_seed(partition_id, world_reset_seed)
values (8, :target_seed)
on conflict(partition_id) do update set world_reset_seed = excluded.world_reset_seed;

do $$
declare
  before_farm int; before_map int; before_dd2 int;
  after_farm int; after_map int; after_dd2 int;
begin
  select farm_seed, map_seed, dd2_seed into before_farm, before_map, before_dd2 from dd1_seed_before;
  select world_reset_seed into after_farm from dune.world_farm_reset_seed where onerow_id=true;
  select world_reset_seed into after_map from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1;
  select world_reset_seed into after_dd2 from dune.world_partition_reset_seed where partition_id=31;
  if before_farm is distinct from after_farm then raise exception 'farm seed changed % -> %', before_farm, after_farm; end if;
  if before_map is distinct from after_map then raise exception 'DD map seed changed % -> %', before_map, after_map; end if;
  if before_dd2 is distinct from after_dd2 then raise exception 'DD2 seed changed % -> %', before_dd2, after_dd2; end if;
end $$;

notify world_partition_update;
select
  (select world_reset_seed from dune.world_farm_reset_seed where onerow_id=true) farm_seed,
  (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) dd_map_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id=8) dd1_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id=31) dd2_seed;
commit;
SQL
}

main() {
  printf 'host=%s required_host=%s execute=%s service=%s target_seed=%s\n' "$(host_name)" "$required_host" "$execute" "$service" "$seed"
  summary "before"
  if [[ "$execute" != true ]]; then
    printf '\ndry-run complete; rerun with --execute to mutate production\n'
    exit 0
  fi
  if [[ "$(host_name)" != "$required_host" ]]; then
    printf 'refusing live mutation: hostname mismatch\n' >&2
    exit 1
  fi
  make_backup
  DUNE_ANNOUNCE_MESSAGE="DD#1 maintenance in 5 minutes. DD#1 will restart for a layout test. Other maps should remain online." "$script_dir/announce.sh"
  printf 'sent DD#1 warning; sleeping %s seconds\n' "$warning_seconds"
  sleep "$warning_seconds"
  "${compose[@]}" stop -t 30 "$service"
  apply_seed
  "${compose[@]}" up -d --force-recreate --no-deps "$service"
  summary "after start request"
  "${compose[@]}" ps "$service" deep-desert-pvp
}

main
