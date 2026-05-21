#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="${COMPOSE_FILE:-compose.yaml}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
compose=(docker compose -f "$compose_file")

usage() {
  cat <<'USAGE'
Usage:
  scripts/npc-exchange-stock.sh inspect
  scripts/npc-exchange-stock.sh patch-function --dry-run
  scripts/npc-exchange-stock.sh patch-function --apply --confirm "PATCH NPC EXCHANGE FUNCTION"
  scripts/npc-exchange-stock.sh add-order --dry-run [options]
  scripts/npc-exchange-stock.sh add-order --apply --confirm "ADD NPC EXCHANGE ORDER" [options]

Options for add-order:
  --exchange-id ID          Dune exchange id, default 2
  --access-point-id ID     Dune exchange access point id, default 1
  --owner-id ID            Actor/controller id recorded as order owner, required
  --item-id ID             Existing item id to move into exchange inventory, required
  --count N                Number of items to move/list, default 1
  --max-count N            Max stock cap for recurring merge path, default count
  --price N                Item price, required
  --wear-price N           Wear-normalized item price, default price
  --expires-at N           Expiration timestamp, default now + 28 days
  --category-mask N        Exchange category mask, default 0
  --category-depth N       Exchange category depth, default 0
  --durability-cur N       Durability current, default 100.0
  --durability-max N       Durability max, default 100.0
  --quality-level N        Quality level, default 0

Notes:
  - Dry-run add-order temporarily patches the recurring-order function inside a
    transaction, calls it, shows the planned rows, then rolls back.
  - Apply add-order does not patch the function. Run patch-function --apply
    first, then add-order --apply.
USAGE
}

psql() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" "$@"
}

patch_function_sql() {
  cat <<'SQL'
create or replace function dune.dune_exchange_update_recurring_sell_order(
    in_exchange_id bigint,
    in_expiration_time bigint,
    in_access_point_id bigint,
    in_owner_id bigint,
    in_item_id bigint,
    in_increment bigint,
    in_max_count bigint,
    in_category_mask integer,
    in_category_depth smallint,
    in_durability_cur real,
    in_durability_max real,
    in_item_price bigint,
    in_wear_normalized_item_price bigint,
    in_quality_level bigint
) returns bigint
language plpgsql
as $function$
declare
    exchange_inventory_id bigint;
    new_item_id bigint;
    item_stack_size bigint;
    new_order_id bigint;
    item_template_id text;
    old_count bigint;
    new_count bigint;
    delta_count bigint;
begin
    lock table dune_exchange_orders, items in row exclusive mode;

    select into exchange_inventory_id get_exchange_inventory_id(in_exchange_id);

    if exchange_inventory_id is null then
        return 0;
    end if;

    select into strict item_template_id template_id from items where id = in_item_id for share;

    select into new_order_id, new_item_id ord.id, ord.item_id
    from dune_exchange_orders ord
    join dune_exchange_sell_orders sord on (ord.id = sord.order_id)
    where ord.is_npc_order = true
      and ord.exchange_id = in_exchange_id
      and ord.access_point_id = in_access_point_id
      and ord.template_id = item_template_id
      and ord.item_price = in_item_price
      and ord.quality_level = in_quality_level
    for share;

    if new_order_id is null then
        new_count := in_increment;

        insert into dune_exchange_orders(
            exchange_id, access_point_id, owner_id, is_npc_order,
            expiration_time, template_id, durability_cur, durability_max,
            category_mask, category_depth, item_price, quality_level
        )
        values(
            in_exchange_id, in_access_point_id, in_owner_id, true,
            in_expiration_time, item_template_id, in_durability_cur,
            in_durability_max, in_category_mask, in_category_depth,
            in_item_price, in_quality_level
        )
        returning id into new_order_id;

        insert into dune_exchange_sell_orders(order_id, initial_stack_size, wear_normalized_price)
        values(new_order_id, new_count, in_wear_normalized_item_price);

        select into new_item_id move_inventory_item(in_item_id, exchange_inventory_id, new_order_id, in_increment);

        if new_item_id is null then
            delete from dune_exchange_orders where id = new_order_id;
            return 0;
        end if;

        update dune_exchange_orders set item_id = new_item_id where id = new_order_id;

        return in_increment;
    else
        update dune_exchange_orders set expiration_time = in_expiration_time where id = new_order_id;
        select into strict old_count stack_size from items where id = new_item_id for share;
        new_count = old_count + in_increment;
        if new_count > in_max_count then new_count = in_max_count; end if;
        if new_count != old_count then
            delta_count = new_count - old_count;
            select into new_item_id merge_or_move_inventory_item(in_item_id, exchange_inventory_id, new_order_id, delta_count);
            return delta_count;
        end if;

        return 0;
    end if;
end
$function$;
SQL
}

function_bug_present_sql() {
  cat <<'SQL'
select case
  when position('VALUES(new_order_id, new_count, in_wear_normalized_item_price)' in pg_get_functiondef(p.oid)) > 0
   and position('new_count := in_increment' in pg_get_functiondef(p.oid)) = 0
  then 'bug_present'
  else 'patched_or_changed'
end as recurring_order_function_status
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname='dune'
  and p.proname='dune_exchange_update_recurring_sell_order';
SQL
}

function_bug_present_marker_sql() {
  cat <<'SQL'
select 'function_status' as marker,
case
  when position('VALUES(new_order_id, new_count, in_wear_normalized_item_price)' in pg_get_functiondef(p.oid)) > 0
   and position('new_count := in_increment' in pg_get_functiondef(p.oid)) = 0
  then 'bug_present'
  else 'patched_or_changed'
end as recurring_order_function_status
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname='dune'
  and p.proname='dune_exchange_update_recurring_sell_order';
SQL
}

function_status() {
  psql -At -c "$(function_bug_present_sql)" | tr -d '[:space:]'
}

require_int() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^-?[0-9]+$ ]]; then
    printf '%s must be an integer, got %s\n' "$name" "$value" >&2
    exit 2
  fi
}

require_unsigned_int() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s must be a non-negative integer, got %s\n' "$name" "$value" >&2
    exit 2
  fi
}

require_number() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf '%s must be a non-negative number, got %s\n' "$name" "$value" >&2
    exit 2
  fi
}

inspect() {
  psql -P pager=off -c "$(function_bug_present_sql)"
  psql -P pager=off -c "
    select 'dune_exchange_orders' as table_name, count(*) as rows from dune.dune_exchange_orders
    union all select 'dune_exchange_sell_orders', count(*) from dune.dune_exchange_sell_orders
    union all select 'exchange_inventories', count(*) from dune.inventories where exchange_id is not null;

    select * from dune.dune_exchanges order by id;
    select * from dune.dune_exchange_accesspoints order by id;

    select o.id, o.exchange_id, e.exchange_name, o.access_point_id, ap.name as access_point,
           o.owner_id, o.item_id, o.template_id, o.is_npc_order, o.item_price,
           o.expiration_time, o.quality_level, s.initial_stack_size, s.wear_normalized_price
    from dune.dune_exchange_orders o
    left join dune.dune_exchange_sell_orders s on s.order_id=o.id
    left join dune.dune_exchanges e on e.id=o.exchange_id
    left join dune.dune_exchange_accesspoints ap on ap.id=o.access_point_id
    order by o.id
    limit 50;
  "
}

patch_function() {
  local dry_run=true
  local confirm=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) dry_run=true; shift ;;
      --apply) dry_run=false; shift ;;
      --confirm) confirm="${2:-}"; shift 2 ;;
      *) usage >&2; exit 2 ;;
    esac
  done

  if [ "$dry_run" = false ] && [ "$confirm" != "PATCH NPC EXCHANGE FUNCTION" ]; then
    printf 'missing confirmation: --confirm "PATCH NPC EXCHANGE FUNCTION"\n' >&2
    exit 2
  fi

  local stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  local backup_dir="$project_root/backups/admin-panel/npc-exchange-stock"
  mkdir -p "$backup_dir"

  psql -At -c "
    select pg_get_functiondef(p.oid)
    from pg_proc p
    join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='dune'
      and p.proname='dune_exchange_update_recurring_sell_order';
  " > "$backup_dir/${stamp}-dune_exchange_update_recurring_sell_order.sql"

  if [ "$dry_run" = true ]; then
    {
      printf 'begin;\n'
      patch_function_sql
      printf '\n'
      function_bug_present_marker_sql
      printf 'rollback;\n'
    } | psql -v ON_ERROR_STOP=1 -P pager=off
    printf 'dry_run=true backup=%s\n' "$backup_dir/${stamp}-dune_exchange_update_recurring_sell_order.sql"
  else
    patch_function_sql | psql -v ON_ERROR_STOP=1 -P pager=off
    psql -P pager=off -c "$(function_bug_present_sql)"
    printf 'applied=true backup=%s\n' "$backup_dir/${stamp}-dune_exchange_update_recurring_sell_order.sql"
  fi
}

add_order() {
  local dry_run=true
  local confirm=""
  local exchange_id=2
  local access_point_id=1
  local owner_id=""
  local item_id=""
  local count=1
  local max_count=""
  local price=""
  local wear_price=""
  local expires_at=""
  local category_mask=0
  local category_depth=0
  local durability_cur=100.0
  local durability_max=100.0
  local quality_level=0

  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) dry_run=true; shift ;;
      --apply) dry_run=false; shift ;;
      --confirm) confirm="${2:-}"; shift 2 ;;
      --exchange-id) exchange_id="${2:-}"; shift 2 ;;
      --access-point-id) access_point_id="${2:-}"; shift 2 ;;
      --owner-id) owner_id="${2:-}"; shift 2 ;;
      --item-id) item_id="${2:-}"; shift 2 ;;
      --count) count="${2:-}"; shift 2 ;;
      --max-count) max_count="${2:-}"; shift 2 ;;
      --price) price="${2:-}"; shift 2 ;;
      --wear-price) wear_price="${2:-}"; shift 2 ;;
      --expires-at) expires_at="${2:-}"; shift 2 ;;
      --category-mask) category_mask="${2:-}"; shift 2 ;;
      --category-depth) category_depth="${2:-}"; shift 2 ;;
      --durability-cur) durability_cur="${2:-}"; shift 2 ;;
      --durability-max) durability_max="${2:-}"; shift 2 ;;
      --quality-level) quality_level="${2:-}"; shift 2 ;;
      *) usage >&2; exit 2 ;;
    esac
  done

  if [ -z "$owner_id" ] || [ -z "$item_id" ] || [ -z "$price" ]; then
    printf 'owner-id, item-id, and price are required\n' >&2
    exit 2
  fi
  if [ -z "$max_count" ]; then max_count="$count"; fi
  if [ -z "$wear_price" ]; then wear_price="$price"; fi
  if [ -z "$expires_at" ]; then expires_at="$(($(date +%s) + 2419200))"; fi

  require_unsigned_int "--exchange-id" "$exchange_id"
  require_unsigned_int "--access-point-id" "$access_point_id"
  require_unsigned_int "--owner-id" "$owner_id"
  require_unsigned_int "--item-id" "$item_id"
  require_unsigned_int "--count" "$count"
  require_unsigned_int "--max-count" "$max_count"
  require_unsigned_int "--price" "$price"
  require_unsigned_int "--wear-price" "$wear_price"
  require_unsigned_int "--expires-at" "$expires_at"
  require_int "--category-mask" "$category_mask"
  require_unsigned_int "--category-depth" "$category_depth"
  require_number "--durability-cur" "$durability_cur"
  require_number "--durability-max" "$durability_max"
  require_unsigned_int "--quality-level" "$quality_level"

  if [ "$dry_run" = false ] && [ "$confirm" != "ADD NPC EXCHANGE ORDER" ]; then
    printf 'missing confirmation: --confirm "ADD NPC EXCHANGE ORDER"\n' >&2
    exit 2
  fi
  if [ "$dry_run" = false ] && [ "$(function_status)" = "bug_present" ]; then
    printf 'live function still has the first-order bug; run patch-function --apply first\n' >&2
    exit 2
  fi

  local prefix="begin;"
  local suffix="rollback;"
  local temp_patch=""
  if [ "$dry_run" = false ]; then
    prefix=""
    suffix=""
  else
    temp_patch="$(patch_function_sql)"
  fi

  psql -v ON_ERROR_STOP=1 -P pager=off <<SQL
$prefix
$temp_patch
$(function_bug_present_marker_sql)
select 'source_item_before' as marker, id, inventory_id, stack_size, position_index, template_id, quality_level
from dune.items
where id = $item_id::bigint;
select dune.dune_exchange_update_recurring_sell_order(
  $exchange_id::bigint,
  $expires_at::bigint,
  $access_point_id::bigint,
  $owner_id::bigint,
  $item_id::bigint,
  $count::bigint,
  $max_count::bigint,
  $category_mask::integer,
  $category_depth::smallint,
  $durability_cur::real,
  $durability_max::real,
  $price::bigint,
  $wear_price::bigint,
  $quality_level::bigint
) as increment_added;
select 'matching_orders' as marker,
       o.id, o.exchange_id, e.exchange_name, o.access_point_id, ap.name as access_point,
       o.owner_id, o.item_id, o.template_id, o.is_npc_order, o.item_price,
       o.expiration_time, o.quality_level, i.inventory_id, i.stack_size,
       i.position_index, s.initial_stack_size, s.wear_normalized_price
from dune.dune_exchange_orders o
join dune.dune_exchange_sell_orders s on s.order_id=o.id
join dune.items i on i.id=o.item_id
left join dune.dune_exchanges e on e.id=o.exchange_id
left join dune.dune_exchange_accesspoints ap on ap.id=o.access_point_id
where o.exchange_id=$exchange_id::bigint
  and o.access_point_id=$access_point_id::bigint
  and o.is_npc_order=true
order by o.id desc
limit 10;
$suffix
SQL
}

cd "$project_root"
cmd="${1:-}"
if [ -z "$cmd" ]; then
  usage >&2
  exit 2
fi
shift

case "$cmd" in
  inspect) inspect "$@" ;;
  patch-function) patch_function "$@" ;;
  add-order) add_order "$@" ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
