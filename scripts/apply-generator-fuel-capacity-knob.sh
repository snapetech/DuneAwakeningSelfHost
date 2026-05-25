#!/usr/bin/env bash
set -euo pipefail

remote_host="${DUNE_CURRENT_HOST:-kspls0}"
mode="apply"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      remote_host="${2:?missing host after --host}"
      shift 2
      ;;
    apply|dry-run|preview|rollback|remove|uninstall)
      mode="$1"
      shift
      ;;
    *)
      echo "usage: $0 [--host HOST] [apply|dry-run|rollback]" >&2
      exit 1
      ;;
  esac
done

days="${DUNE_GENERATOR_FUEL_DAYS:-60}"
item_seconds="${DUNE_GENERATOR_FUEL_ITEM_SECONDS:-3600}"
item_volume="${DUNE_GENERATOR_FUEL_ITEM_VOLUME:-0.2}"
max_volume="${DUNE_GENERATOR_FUEL_MAX_VOLUME:-}"
min_item_count="${DUNE_GENERATOR_FUEL_MIN_ITEM_COUNT:-5}"
project="${COMPOSE_PROJECT_NAME:-dune_server}"
db_service="${DUNE_POSTGRES_SERVICE:-postgres}"
db_name="${DUNE_POSTGRES_DB:-dune_sb_1_4_0_0}"
db_user="${DUNE_POSTGRES_USER:-dune}"

number_re='^[0-9]+([.][0-9]+)?$'
integer_re='^[0-9]+$'
for value_name in days item_seconds item_volume; do
  value="${!value_name}"
  if ! [[ "$value" =~ $number_re ]]; then
    echo "DUNE_GENERATOR_FUEL_${value_name^^} must be numeric" >&2
    exit 1
  fi
done
if [[ -n "$max_volume" && ! "$max_volume" =~ $number_re ]]; then
  echo "DUNE_GENERATOR_FUEL_MAX_VOLUME must be numeric" >&2
  exit 1
fi
if ! [[ "$min_item_count" =~ $integer_re ]]; then
  echo "DUNE_GENERATOR_FUEL_MIN_ITEM_COUNT must be an integer" >&2
  exit 1
fi

if [[ -n "$max_volume" ]]; then
  target_volume_sql="${max_volume}::real"
else
  target_volume_sql="(${days}::double precision * 24.0 * 3600.0 / ${item_seconds}::double precision * ${item_volume}::double precision)::real"
fi

sql_apply="
create or replace function dune.is_extended_fuel_capacity_generator(actor_id bigint)
returns boolean
language sql
stable
as \$\$
  select exists (
    select 1
    from dune.actors a
    where a.id = actor_id
      and a.class in (
        '/Game/Dune/Systems/Building/Pieces/BP_Generator_Placeable.BP_Generator_Placeable_C'
      )
  );
\$\$;

create or replace function dune.apply_generator_fuel_capacity_inventory()
returns trigger
language plpgsql
as \$\$
begin
  if new.actor_id is not null
     and new.inventory_type = 3
     and dune.is_extended_fuel_capacity_generator(new.actor_id) then
    new.max_item_volume = greatest(coalesce(new.max_item_volume, 0), ${target_volume_sql});
    new.max_item_count = greatest(coalesce(new.max_item_count, 0), ${min_item_count});
  end if;
  return new;
end;
\$\$;

create or replace function dune.apply_generator_fuel_capacity_actor()
returns trigger
language plpgsql
as \$\$
begin
  if dune.is_extended_fuel_capacity_generator(new.id) then
    update dune.inventories
    set
      max_item_volume = greatest(coalesce(max_item_volume, 0), ${target_volume_sql}),
      max_item_count = greatest(coalesce(max_item_count, 0), ${min_item_count})
    where actor_id = new.id
      and inventory_type = 3;
  end if;
  return new;
end;
\$\$;

drop trigger if exists apply_generator_fuel_capacity_on_inventories on dune.inventories;
create trigger apply_generator_fuel_capacity_on_inventories
before insert or update of actor_id, inventory_type, max_item_volume, max_item_count
on dune.inventories
for each row
execute function dune.apply_generator_fuel_capacity_inventory();

drop trigger if exists apply_generator_fuel_capacity_on_actors on dune.actors;
create trigger apply_generator_fuel_capacity_on_actors
after insert or update of class
on dune.actors
for each row
execute function dune.apply_generator_fuel_capacity_actor();

with target as (
  select i.id
  from dune.inventories i
  join dune.actors a on a.id = i.actor_id
  where i.inventory_type = 3
    and a.class = '/Game/Dune/Systems/Building/Pieces/BP_Generator_Placeable.BP_Generator_Placeable_C'
),
updated as (
  update dune.inventories i
  set
    max_item_volume = greatest(coalesce(i.max_item_volume, 0), ${target_volume_sql}),
    max_item_count = greatest(coalesce(i.max_item_count, 0), ${min_item_count})
  from target
  where i.id = target.id
  returning i.id, i.max_item_count, i.max_item_volume
),
patch as (
  insert into dune.applied_patches(name, date)
  values ('operator_generator_fuel_capacity', now())
  on conflict (name) do update set date = excluded.date
  returning name
)
select
  count(*) as updated_generator_inventories,
  ${target_volume_sql} as target_max_item_volume,
  ${days}::double precision as desired_fuel_days,
  ${min_item_count}::integer as minimum_item_count
from updated;
"

sql_dry_run="
with target as (
  select i.id, i.max_item_count, i.max_item_volume, coalesce(sum(it.stack_size), 0) as stored_fuel_items
  from dune.inventories i
  join dune.actors a on a.id = i.actor_id
  left join dune.items it on it.inventory_id = i.id
  where i.inventory_type = 3
    and a.class = '/Game/Dune/Systems/Building/Pieces/BP_Generator_Placeable.BP_Generator_Placeable_C'
  group by i.id, i.max_item_count, i.max_item_volume
)
select
  count(*) as generator_inventories,
  count(*) filter (where max_item_volume < ${target_volume_sql} or max_item_count < ${min_item_count}) as inventories_below_target,
  min(max_item_volume) as min_current_volume,
  max(max_item_volume) as max_current_volume,
  max(stored_fuel_items) as max_current_oil_items,
  ${target_volume_sql} as target_max_item_volume,
  ${days}::double precision as desired_fuel_days,
  ${min_item_count}::integer as minimum_item_count
from target;
"

sql_rollback="
drop trigger if exists apply_generator_fuel_capacity_on_inventories on dune.inventories;
drop trigger if exists apply_generator_fuel_capacity_on_actors on dune.actors;
drop function if exists dune.apply_generator_fuel_capacity_inventory();
drop function if exists dune.apply_generator_fuel_capacity_actor();
drop function if exists dune.is_extended_fuel_capacity_generator(bigint);
delete from dune.applied_patches where name = 'operator_generator_fuel_capacity';
"

case "$mode" in
  apply)
    sql="$sql_apply"
    ;;
  dry-run|preview)
    sql="$sql_dry_run"
    ;;
  rollback|remove|uninstall)
    sql="$sql_rollback"
    ;;
esac

container="${project}-${db_service}-1"
remote_cmd="docker exec -i $(printf '%q' "$container") psql -U $(printf '%q' "$db_user") -d $(printf '%q' "$db_name") -v ON_ERROR_STOP=1 -P pager=off"
ssh "$remote_host" "$remote_cmd" <<<"$sql"
