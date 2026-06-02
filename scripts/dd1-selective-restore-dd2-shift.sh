#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/dd1-selective-restore-dd2-shift.sh [options]

Restores only DD#1 partition state from a backup database, then advances only
DD#2's partition seed. Other map partitions are left in current live state.

Options:
  --execute             Required for live mutation. Without it, dry-run only.
  --env-file FILE       Env file. Default: .env
  --backup-dir DIR      Backup source. Default: backups/20260602T014233Z
  --probe-db NAME       Temporary restored DB. Default: dune_dd_restore_probe
  --seed N              Explicit DD#2 seed. Default: max existing seed + 1
  --warning-seconds N   Player warning delay before stopping DD services. Default: 300
  --skip-warning        Do not announce/sleep.
  -h, --help            Show this help.

Environment:
  DUNE_DD_RESTORE_REQUIRED_HOST  Required live hostname. Default: kspls0
  DUNE_DD1_SERVICE               DD#1 service. Default: deep-desert
  DUNE_DD2_SERVICE               DD#2 service. Default: deep-desert-pvp
  DUNE_DD1_PARTITION_ID          DD#1 partition id. Default: 8
  DUNE_DD2_PARTITION_ID          DD#2 partition id. Default: 31
USAGE
}

execute=false
env_file=".env"
backup_dir="backups/20260602T014233Z"
probe_db="dune_dd_restore_probe"
explicit_seed=""
warning_seconds=300
skip_warning=false

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
    --backup-dir)
      backup_dir="${2:-}"
      shift 2
      ;;
    --probe-db)
      probe_db="${2:-}"
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
if [[ ! -d "$backup_dir" ]]; then
  printf 'missing backup dir: %s\n' "$backup_dir" >&2
  exit 2
fi
case "$backup_dir" in
  backups/*) ;;
  *)
    printf 'refusing backup outside backups/: %s\n' "$backup_dir" >&2
    exit 2
    ;;
esac
if [[ -n "$explicit_seed" && ! "$explicit_seed" =~ ^[0-9]+$ ]]; then
  printf 'seed must be an integer: %s\n' "$explicit_seed" >&2
  exit 2
fi
if [[ ! "$warning_seconds" =~ ^[0-9]+$ ]]; then
  printf 'warning seconds must be an integer: %s\n' "$warning_seconds" >&2
  exit 2
fi

required_host="${DUNE_DD_RESTORE_REQUIRED_HOST:-kspls0}"
dd1_service="${DUNE_DD1_SERVICE:-deep-desert}"
dd2_service="${DUNE_DD2_SERVICE:-deep-desert-pvp}"
dd1_partition="${DUNE_DD1_PARTITION_ID:-8}"
dd2_partition="${DUNE_DD2_PARTITION_ID:-31}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
runtime="${CONTAINER_RUNTIME:-docker}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

dump_file="$backup_dir/postgres-${db}.dump"
if [[ ! -f "$dump_file" ]]; then
  dump_file="$(find "$backup_dir" -maxdepth 1 -type f -name "*-${db}.dump" | sort | head -1)"
fi
if [[ -z "${dump_file:-}" || ! -f "$dump_file" ]]; then
  printf 'could not find postgres dump for %s in %s\n' "$db" "$backup_dir" >&2
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

psql_postgres() {
  "${compose[@]}" exec -T postgres psql -U dune -d postgres -v ON_ERROR_STOP=1 "$@"
}

restore_probe_db() {
  printf 'preparing probe database %s from %s\n' "$probe_db" "$dump_file"
  psql_postgres -v probe_db="$probe_db" <<'SQL'
select pg_terminate_backend(pid)
from pg_stat_activity
where datname = :'probe_db';
drop database if exists :"probe_db";
create database :"probe_db" owner dune;
SQL
  "${compose[@]}" exec -T postgres pg_restore -U dune -d "$probe_db" --clean --if-exists < "$dump_file"
}

announce_and_wait() {
  if [[ "$skip_warning" == true ]]; then
    printf 'warning skipped by --skip-warning\n'
    return 0
  fi
  local minutes
  minutes=$(( (warning_seconds + 59) / 60 ))
  DUNE_ANNOUNCE_MESSAGE="Deep Desert maintenance in ${minutes} minutes. DD#1 will be restored; DD#2 will be advanced. Please get to a safe place." \
    "$script_dir/announce.sh"
  printf 'sent player warning; sleeping %s seconds\n' "$warning_seconds"
  sleep "$warning_seconds"
}

make_safety_backup() {
  local stamp dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dir="backups/manual/dd1-restore-dd2-shift-${stamp}"
  mkdir -p "$dir"
  cp "$env_file" "$dir/$(basename "$env_file")"
  "${compose[@]}" exec -T postgres pg_dump -U dune -d "$db" -Fc > "$dir/postgres-${db}.dump"
  cat > "$dir/manifest.txt" <<EOF
created_utc=${stamp}
reason=pre selective DD1 restore and DD2 seed shift
source_backup=${backup_dir}
probe_db=${probe_db}
database=${db}
dd1_partition=${dd1_partition}
dd2_partition=${dd2_partition}
dd1_service=${dd1_service}
dd2_service=${dd2_service}
compose_files=${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}
EOF
  printf 'safety_backup=%s\n' "$dir"
}

stop_dd_services() {
  "${compose[@]}" stop -t 30 "$dd1_service" "$dd2_service"
}

start_dd_services() {
  "${compose[@]}" up -d --force-recreate --no-deps "$dd1_service" "$dd2_service"
}

fdw_setup_sql() {
  cat <<SQL
create extension if not exists postgres_fdw;
drop schema if exists dd_restore_src cascade;
drop server if exists dd_restore_probe_srv cascade;
create server dd_restore_probe_srv foreign data wrapper postgres_fdw options (dbname '${probe_db}');
create user mapping for current_user server dd_restore_probe_srv options (user 'dune');
create schema dd_restore_src;
import foreign schema dune limit to (
  actors, actor_fgl_entities, actor_inventories, actor_state,
  backup_vehicles, base_backup_linked_actors, base_backups,
  building_blueprint_instances, building_blueprint_pentashields,
  building_blueprint_placeables, building_blueprints, building_instances,
  buildings, consumed_per_player_lore, consumed_temporary_per_player_lore,
  encrypted_player_state, fgl_entities, game_events, inventories, items,
  landclaim_segments, permission_actor, permission_actor_rank, placeables,
  player_faction, player_faction_reputation, player_respawn_locations,
  player_virtual_currency_balances, recovered_vehicles, totems,
  travel_actor_parent, travel_return_info, vehicle_module_inventories,
  vehicle_modules, vehicles, world_partition_reset_seed
) from server dd_restore_probe_srv into dd_restore_src;
SQL
}

fdw_cleanup_sql() {
  cat <<'SQL'
drop schema if exists dd_restore_src cascade;
drop server if exists dd_restore_probe_srv cascade;
SQL
}

sets_sql() {
  cat <<SQL
create temporary table src_actor_ids on commit drop as
select id from dd_restore_src.actors where partition_id = ${dd1_partition};

create temporary table live_actor_ids on commit drop as
select id from dune.actors where partition_id = ${dd1_partition};

create temporary table delete_actor_ids on commit drop as
select id from src_actor_ids
union
select id from live_actor_ids;

create temporary table src_player_accounts on commit drop as
select distinct eps.account_id
from dd_restore_src.encrypted_player_state eps
where eps.player_controller_id in (select id from src_actor_ids)
   or eps.player_pawn_id in (select id from src_actor_ids)
   or eps.player_state_id in (select id from src_actor_ids);

create temporary table delete_player_accounts on commit drop as
select distinct eps.account_id
from dune.encrypted_player_state eps
where eps.player_controller_id in (select id from delete_actor_ids)
   or eps.player_pawn_id in (select id from delete_actor_ids)
   or eps.player_state_id in (select id from delete_actor_ids)
union
select account_id from src_player_accounts;

create temporary table src_vehicle_ids on commit drop as
select id from dd_restore_src.vehicles where id in (select id from src_actor_ids);

create temporary table delete_vehicle_ids on commit drop as
select id from dune.vehicles where id in (select id from delete_actor_ids)
union
select id from src_vehicle_ids;

create temporary table src_vehicle_module_ids on commit drop as
select id from dd_restore_src.vehicle_modules where vehicle_id in (select id from src_vehicle_ids);

create temporary table delete_vehicle_module_ids on commit drop as
select id from dune.vehicle_modules where vehicle_id in (select id from delete_vehicle_ids)
union
select id from src_vehicle_module_ids;

create temporary table src_inventory_ids on commit drop as
with recursive inv(id) as (
  select id from dd_restore_src.inventories where actor_id in (select id from src_actor_ids)
  union
  select id from dd_restore_src.inventories where vehicle_module_id in (select id from src_vehicle_module_ids)
  union
  select i.id
  from dd_restore_src.inventories i
  join dd_restore_src.items it on it.id = i.item_id
  join inv parent on parent.id = it.inventory_id
)
select distinct id from inv;

create temporary table src_item_ids on commit drop as
select distinct id from dd_restore_src.items where inventory_id in (select id from src_inventory_ids);

create temporary table delete_inventory_ids on commit drop as
with recursive inv(id) as (
  select id from dune.inventories where actor_id in (select id from delete_actor_ids)
  union
  select id from dune.inventories where vehicle_module_id in (select id from delete_vehicle_module_ids)
  union
  select i.id
  from dune.inventories i
  join dune.items it on it.id = i.item_id
  join inv parent on parent.id = it.inventory_id
)
select distinct id from inv
union
select id from src_inventory_ids;

create temporary table delete_item_ids on commit drop as
select distinct id from dune.items where inventory_id in (select id from delete_inventory_ids)
union
select id from src_item_ids;

create temporary table src_fgl_entity_ids on commit drop as
select entity_id from dd_restore_src.actor_fgl_entities where actor_id in (select id from src_actor_ids)
union
select owner_entity_id from dd_restore_src.building_instances where building_id in (select id from src_actor_ids) and owner_entity_id is not null
union
select owner_entity_id from dd_restore_src.placeables where id in (select id from src_actor_ids) and owner_entity_id is not null;

create temporary table src_base_backup_ids on commit drop as
select id from dd_restore_src.base_backups where player_id in (select id from src_actor_ids)
union
select id from dd_restore_src.base_backup_linked_actors where actor_id in (select id from src_actor_ids);

create temporary table delete_base_backup_ids on commit drop as
select id from dune.base_backups where player_id in (select id from delete_actor_ids)
union
select id from dune.base_backup_linked_actors where actor_id in (select id from delete_actor_ids)
union
select id from src_base_backup_ids;

create temporary table src_blueprint_ids on commit drop as
select id from dd_restore_src.building_blueprints
where player_id in (select id from src_actor_ids)
   or item_id in (select id from src_item_ids);

create temporary table delete_blueprint_ids on commit drop as
select id from dune.building_blueprints
where player_id in (select id from delete_actor_ids)
   or item_id in (select id from delete_item_ids)
union
select id from src_blueprint_ids;
SQL
}

dry_run_sql() {
  cat <<'SQL'
select 'src_actor_ids' as set_name, count(*) from src_actor_ids
union all select 'live_actor_ids', count(*) from live_actor_ids
union all select 'delete_actor_ids', count(*) from delete_actor_ids
union all select 'src_player_accounts', count(*) from src_player_accounts
union all select 'delete_player_accounts', count(*) from delete_player_accounts
union all select 'src_inventory_ids', count(*) from src_inventory_ids
union all select 'src_item_ids', count(*) from src_item_ids
union all select 'delete_inventory_ids', count(*) from delete_inventory_ids
union all select 'delete_item_ids', count(*) from delete_item_ids
union all select 'src_fgl_entity_ids', count(*) from src_fgl_entity_ids
union all select 'src_vehicle_ids', count(*) from src_vehicle_ids
union all select 'src_vehicle_module_ids', count(*) from src_vehicle_module_ids
union all select 'src_base_backup_ids', count(*) from src_base_backup_ids
union all select 'src_blueprint_ids', count(*) from src_blueprint_ids
order by set_name;

select 'source actors currently outside live DD1' as check_name, count(*) as rows
from src_actor_ids s
join dune.actors a on a.id = s.id
where coalesce(a.partition_id, -1) <> 8;

select a.id, a.partition_id, a.map, a.class
from src_actor_ids s
join dune.actors a on a.id = s.id
where coalesce(a.partition_id, -1) <> 8
order by a.id
limit 20;

select 'backup_dd1_classes' as section, class, count(*)
from dd_restore_src.actors
where id in (select id from src_actor_ids)
group by class
order by count(*) desc
limit 30;
SQL
}

mutate_sql() {
  local seed_expr
  if [[ -n "$explicit_seed" ]]; then
    seed_expr="$explicit_seed"
  else
    seed_expr="null"
  fi
  cat <<SQL
begin;
set local session_replication_role = replica;

$(sets_sql)

delete from dune.building_blueprint_instances where building_blueprint_id in (select id from delete_blueprint_ids);
delete from dune.building_blueprint_pentashields where building_blueprint_id in (select id from delete_blueprint_ids);
delete from dune.building_blueprint_placeables where building_blueprint_id in (select id from delete_blueprint_ids);
delete from dune.building_blueprints where id in (select id from delete_blueprint_ids);

delete from dune.actor_inventories where inventory_id in (select id from delete_inventory_ids);
delete from dune.vehicle_module_inventories where inventory_id in (select id from delete_inventory_ids);
delete from dune.items where id in (select id from delete_item_ids);
delete from dune.inventories where id in (select id from delete_inventory_ids);

delete from dune.backup_vehicles where vehicle_id in (select id from delete_vehicle_ids);
delete from dune.recovered_vehicles where vehicle_id in (select id from delete_vehicle_ids);
delete from dune.vehicle_modules where id in (select id from delete_vehicle_module_ids);

delete from dune.base_backup_linked_actors where id in (select id from delete_base_backup_ids) or actor_id in (select id from delete_actor_ids);
delete from dune.base_backups where id in (select id from delete_base_backup_ids);

delete from dune.permission_actor_rank where permission_actor_id in (select id from delete_actor_ids) or player_id in (select id from delete_actor_ids);
delete from dune.permission_actor where actor_id in (select id from delete_actor_ids);
delete from dune.landclaim_segments where totem_id in (select id from delete_actor_ids);
delete from dune.building_instances where building_id in (select id from delete_actor_ids);
delete from dune.actor_fgl_entities where actor_id in (select id from delete_actor_ids);
delete from dune.actor_state where actor_id in (select id from delete_actor_ids);
delete from dune.buildings where id in (select id from delete_actor_ids);
delete from dune.placeables where id in (select id from delete_actor_ids);
delete from dune.totems where id in (select id from delete_actor_ids);
delete from dune.vehicles where id in (select id from delete_actor_ids);
delete from dune.travel_actor_parent where id in (select id from delete_actor_ids) or parent_id in (select id from delete_actor_ids);
delete from dune.travel_return_info where player_controller_id in (select id from delete_actor_ids);
delete from dune.consumed_per_player_lore where actor_id in (select id from delete_actor_ids);
delete from dune.consumed_temporary_per_player_lore where actor_id in (select id from delete_actor_ids);
delete from dune.player_faction where actor_id in (select id from delete_actor_ids);
delete from dune.player_faction_reputation where actor_id in (select id from delete_actor_ids);
delete from dune.player_virtual_currency_balances where player_controller_id in (select id from delete_actor_ids);
delete from dune.player_respawn_locations where locator_actor_id in (select id from delete_actor_ids) or (account_id in (select account_id from src_player_accounts) and map = 'DeepDesert_1');
delete from dune.game_events where partition_id = ${dd1_partition} or actor_id in (select id from delete_actor_ids);
delete from dune.encrypted_player_state where account_id in (select account_id from src_player_accounts);
delete from dune.actors where id in (select id from delete_actor_ids);

insert into dune.actors select * from dd_restore_src.actors where id in (select id from src_actor_ids);
insert into dune.fgl_entities
select * from dd_restore_src.fgl_entities where entity_id in (select entity_id from src_fgl_entity_ids)
on conflict (entity_id) do update set components = excluded.components;
insert into dune.actor_fgl_entities select * from dd_restore_src.actor_fgl_entities where actor_id in (select id from src_actor_ids);
insert into dune.actor_state select * from dd_restore_src.actor_state where actor_id in (select id from src_actor_ids);
insert into dune.buildings select * from dd_restore_src.buildings where id in (select id from src_actor_ids);
insert into dune.building_instances select * from dd_restore_src.building_instances where building_id in (select id from src_actor_ids);
insert into dune.placeables select * from dd_restore_src.placeables where id in (select id from src_actor_ids);
insert into dune.totems select * from dd_restore_src.totems where id in (select id from src_actor_ids);
insert into dune.vehicles select * from dd_restore_src.vehicles where id in (select id from src_actor_ids);
insert into dune.vehicle_modules select * from dd_restore_src.vehicle_modules where id in (select id from src_vehicle_module_ids);
insert into dune.inventories select * from dd_restore_src.inventories where id in (select id from src_inventory_ids);
insert into dune.items select * from dd_restore_src.items where id in (select id from src_item_ids);
insert into dune.actor_inventories select * from dd_restore_src.actor_inventories where inventory_id in (select id from src_inventory_ids);
insert into dune.vehicle_module_inventories select * from dd_restore_src.vehicle_module_inventories where inventory_id in (select id from src_inventory_ids);
insert into dune.backup_vehicles select * from dd_restore_src.backup_vehicles where vehicle_id in (select id from src_vehicle_ids);
insert into dune.recovered_vehicles select * from dd_restore_src.recovered_vehicles where vehicle_id in (select id from src_vehicle_ids);
insert into dune.base_backups select * from dd_restore_src.base_backups where id in (select id from src_base_backup_ids);
insert into dune.base_backup_linked_actors select * from dd_restore_src.base_backup_linked_actors where id in (select id from src_base_backup_ids) or actor_id in (select id from src_actor_ids);
insert into dune.permission_actor select * from dd_restore_src.permission_actor where actor_id in (select id from src_actor_ids);
insert into dune.permission_actor_rank select * from dd_restore_src.permission_actor_rank where permission_actor_id in (select id from src_actor_ids) or player_id in (select id from src_actor_ids);
insert into dune.landclaim_segments select * from dd_restore_src.landclaim_segments where totem_id in (select id from src_actor_ids);
insert into dune.travel_actor_parent select * from dd_restore_src.travel_actor_parent where id in (select id from src_actor_ids) or parent_id in (select id from src_actor_ids);
insert into dune.travel_return_info select * from dd_restore_src.travel_return_info where player_controller_id in (select id from src_actor_ids);
insert into dune.consumed_per_player_lore select * from dd_restore_src.consumed_per_player_lore where actor_id in (select id from src_actor_ids);
insert into dune.consumed_temporary_per_player_lore select * from dd_restore_src.consumed_temporary_per_player_lore where actor_id in (select id from src_actor_ids);
insert into dune.player_faction select * from dd_restore_src.player_faction where actor_id in (select id from src_actor_ids);
insert into dune.player_faction_reputation select * from dd_restore_src.player_faction_reputation where actor_id in (select id from src_actor_ids);
insert into dune.player_virtual_currency_balances select * from dd_restore_src.player_virtual_currency_balances where player_controller_id in (select id from src_actor_ids);
insert into dune.player_respawn_locations select * from dd_restore_src.player_respawn_locations where locator_actor_id in (select id from src_actor_ids) or (account_id in (select account_id from src_player_accounts) and map = 'DeepDesert_1');
insert into dune.encrypted_player_state select * from dd_restore_src.encrypted_player_state where account_id in (select account_id from src_player_accounts);
insert into dune.game_events select * from dd_restore_src.game_events where partition_id = ${dd1_partition} or actor_id in (select id from src_actor_ids);
insert into dune.building_blueprints select * from dd_restore_src.building_blueprints where id in (select id from src_blueprint_ids);
insert into dune.building_blueprint_instances select * from dd_restore_src.building_blueprint_instances where building_blueprint_id in (select id from src_blueprint_ids);
insert into dune.building_blueprint_pentashields select * from dd_restore_src.building_blueprint_pentashields where building_blueprint_id in (select id from src_blueprint_ids);
insert into dune.building_blueprint_placeables select * from dd_restore_src.building_blueprint_placeables where building_blueprint_id in (select id from src_blueprint_ids);

insert into dune.world_partition_reset_seed(partition_id, world_reset_seed)
select ${dd1_partition}, world_reset_seed
from dd_restore_src.world_partition_reset_seed
where partition_id = ${dd1_partition}
on conflict(partition_id) do update set world_reset_seed = excluded.world_reset_seed;

with next_seed as (
  select coalesce(
    nullif('${seed_expr}', 'null')::integer,
    greatest(
      coalesce((select max(world_reset_seed) from dune.world_farm_reset_seed), 0),
      coalesce((select max(world_reset_seed) from dune.world_map_reset_seed), 0),
      coalesce((select max(world_reset_seed) from dune.world_partition_reset_seed), 0)
    ) + 1
  ) as value
)
insert into dune.world_partition_reset_seed(partition_id, world_reset_seed)
select ${dd2_partition}, value from next_seed
on conflict(partition_id) do update set world_reset_seed = excluded.world_reset_seed;

select setval('dune.actors_id_seq', greatest((select max(id) from dune.actors), (select last_value from dune.actors_id_seq)));
select setval('dune.inventories_id_seq', greatest((select max(id) from dune.inventories), (select last_value from dune.inventories_id_seq)));
select setval('dune.items_id_seq', greatest((select max(id) from dune.items), (select last_value from dune.items_id_seq)));
select setval('dune.vehicle_modules_id_seq', greatest((select max(id) from dune.vehicle_modules), (select last_value from dune.vehicle_modules_id_seq)));
select setval('dune.base_backups_id_seq', greatest((select max(id) from dune.base_backups), (select last_value from dune.base_backups_id_seq)));

set local session_replication_role = origin;
notify world_partition_update;

select
  (select count(*) from dune.actors where partition_id = ${dd1_partition}) as dd1_actors,
  (select count(*) from dune.inventories where actor_id in (select id from src_actor_ids)) as dd1_actor_inventories,
  (select count(*) from dune.items where inventory_id in (select id from src_inventory_ids)) as dd1_items,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = ${dd1_partition}) as dd1_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = ${dd2_partition}) as dd2_seed,
  (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
  (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) as dd_map_seed;

commit;
SQL
}

run_dry_run() {
  psql_live -P pager=off <<SQL
$(fdw_setup_sql)
begin;
$(sets_sql)
$(dry_run_sql)
rollback;
$(fdw_cleanup_sql)
SQL
}

run_mutation() {
  psql_live -P pager=off <<SQL
$(fdw_setup_sql)
$(mutate_sql)
$(fdw_cleanup_sql)
SQL
}

summary() {
  local label="$1"
  printf '\n== %s ==\n' "$label"
  psql_live -P pager=off -c "
    select
      (select count(*) from dune.actors where partition_id = ${dd1_partition}) as dd1_actors,
      (select count(*) from dune.actors where partition_id = ${dd2_partition}) as dd2_actors,
      (select world_reset_seed from dune.world_partition_reset_seed where partition_id = ${dd1_partition}) as dd1_seed,
      (select world_reset_seed from dune.world_partition_reset_seed where partition_id = ${dd2_partition}) as dd2_seed,
      (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
      (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) as dd_map_seed;
    select partition_id, map, dimension_index, label from dune.world_partition where partition_id in (${dd1_partition}, ${dd2_partition}) order by partition_id;
  "
}

main() {
  printf 'host=%s required_host=%s execute=%s backup=%s probe_db=%s\n' "$(host_name)" "$required_host" "$execute" "$backup_dir" "$probe_db"
  restore_probe_db
  summary "live before"
  if [[ "$execute" != true ]]; then
    run_dry_run
    printf '\ndry-run complete; rerun with --execute to mutate production\n'
    exit 0
  fi

  assert_live_host
  announce_and_wait
  stop_dd_services
  make_safety_backup
  run_mutation
  start_dd_services
  summary "live after"
  "${compose[@]}" ps "$dd1_service" "$dd2_service"
}

main
