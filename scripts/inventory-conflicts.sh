#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
DATABASE="${DUNE_GAME_DB_NAME:-dune_sb_1_4_0_0}"
COMMAND="audit"
EXECUTE=false
CONFIRM=""
ALLOW_NON_PRODUCTION_HOST=false
PRODUCTION_HOST="${DUNE_PRODUCTION_HOST:-kspls0}"
BACKUP_ROOT="${DUNE_INVENTORY_BACKUP_ROOT:-$ROOT_DIR/backups/inventory-conflicts}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"
EXCLUDED_INVENTORIES=()

usage() {
  cat <<'EOF'
Usage:
  scripts/inventory-conflicts.sh [--env-file PATH] [--db NAME] audit
  scripts/inventory-conflicts.sh [--env-file PATH] [--db NAME] repair [--dry-run]
  scripts/inventory-conflicts.sh [--env-file PATH] [--db NAME] repair --execute \
    --confirm 'REPAIR INVENTORY SLOT CONFLICTS' [--exclude-inventory ID ...]
  scripts/inventory-conflicts.sh --print-repair-sql

Safety contract:
  - audit is read-only and reports duplicate, negative, and over-capacity slots;
  - repair is a dry-run unless --execute and the exact confirmation are supplied;
  - execution is restricted to DUNE_PRODUCTION_HOST (default: kspls0) unless
    --allow-non-production-host is explicitly supplied for a deliberate lab run;
  - a full PostgreSQL custom-format dump must complete before repair starts;
  - repair keeps the lowest item id in each occupied slot and moves every later
    row to a free slot in the same inventory;
  - repair never deletes items and aborts the whole transaction if capacity is
    insufficient or any duplicate remains.
  - --exclude-inventory permits an explicitly reviewed full/special inventory
    to remain untouched while all other conflicts are transactionally repaired.
EOF
}

AUDIT_SQL=$(cat <<'SQL'
with duplicate_slots as (
  select inventory_id, position_index, count(*)::bigint as row_count,
         array_agg(id order by id) as item_ids,
         array_agg(template_id order by id) as template_ids
  from dune.items
  where inventory_id is not null and position_index is not null
  group by inventory_id, position_index
  having count(*) > 1
), invalid_slots as (
  select i.id, i.inventory_id, i.position_index, i.template_id,
         inv.max_item_count,
         case
           when i.position_index < 0 then 'negative'
           when inv.max_item_count is not null and inv.max_item_count >= 0
                and i.position_index >= inv.max_item_count then 'over-capacity'
         end as reason
  from dune.items i
  left join dune.inventories inv on inv.id = i.inventory_id
  where i.position_index < 0
     or (inv.max_item_count is not null and inv.max_item_count >= 0
         and i.position_index >= inv.max_item_count)
)
select 'duplicate' as finding, inventory_id::text, position_index::text,
       row_count::text, item_ids::text, template_ids::text
from duplicate_slots
union all
select reason, inventory_id::text, position_index::text,
       '1', array[id]::text, array[template_id]::text
from invalid_slots
order by 1, 2, 3;
SQL
)

CONFLICT_COUNT_SQL=$(cat <<'SQL'
select count(*)
from (
  select inventory_id, position_index
  from dune.items
  where inventory_id is not null and position_index is not null
  group by inventory_id, position_index
  having count(*) > 1
) conflicts;
SQL
)

REPAIR_SQL_TEMPLATE=$(cat <<'SQL'
begin;
set local lock_timeout = '15s';
set local statement_timeout = '120s';
lock table dune.items in share row exclusive mode;

create temporary table inventory_conflict_targets on commit drop as
with ranked as (
  select id, inventory_id, position_index,
         row_number() over (
           partition by inventory_id, position_index
           order by id
         ) as duplicate_rank
  from dune.items
  where inventory_id is not null and position_index is not null
    and (/*TARGET_FILTER*/)
)
select id, inventory_id, position_index,
       row_number() over (partition by inventory_id order by position_index, id) as target_rank
from ranked
where duplicate_rank > 1;

do $online$
begin
  if exists (
    select 1
    from inventory_conflict_targets targets
    join dune.inventories inv on inv.id = targets.inventory_id
    join dune.player_state ps
      on inv.actor_id in (ps.player_pawn_id, ps.player_controller_id)
    where lower(ps.online_status::text) = 'online'
  ) then
    raise exception 'inventory repair aborted: an affected inventory owner is online';
  end if;
end
$online$;

create temporary table inventory_conflict_free_slots on commit drop as
with target_counts as (
  select inventory_id, count(*)::bigint as target_count
  from inventory_conflict_targets
  group by inventory_id
), inventory_limits as (
  select tc.inventory_id, tc.target_count, inv.max_item_count,
         coalesce((
           select max(i.position_index)
           from dune.items i
           where i.inventory_id = tc.inventory_id
         ), -1) as highest_position
  from target_counts tc
  join dune.inventories inv on inv.id = tc.inventory_id
), candidates as (
  select limits.inventory_id, slot.position_index::bigint,
         row_number() over (
           partition by limits.inventory_id
           order by slot.position_index
         ) as free_rank
  from inventory_limits limits
  cross join lateral generate_series(
    0::bigint,
    case
      when limits.max_item_count is null or limits.max_item_count < 0
        then limits.highest_position + limits.target_count
      else limits.max_item_count - 1
    end::bigint
  ) as slot(position_index)
  where not exists (
    select 1
    from dune.items occupied
    where occupied.inventory_id = limits.inventory_id
      and occupied.position_index = slot.position_index
  )
)
select inventory_id, position_index, free_rank
from candidates;

create temporary table inventory_conflict_assignments on commit drop as
select targets.id, targets.inventory_id,
       targets.position_index as old_position,
       free.position_index as new_position
from inventory_conflict_targets targets
join inventory_conflict_free_slots free
  on free.inventory_id = targets.inventory_id
 and free.free_rank = targets.target_rank;

do $repair$
declare
  target_total bigint;
  assignment_total bigint;
begin
  select count(*) into target_total from inventory_conflict_targets;
  select count(*) into assignment_total from inventory_conflict_assignments;
  if target_total <> assignment_total then
    raise exception 'inventory repair aborted: % duplicate rows need relocation but only % safe assignments exist',
      target_total, assignment_total;
  end if;
end
$repair$;

with moved as (
  update dune.items items
  set position_index = assignments.new_position,
      is_new = true
  from inventory_conflict_assignments assignments
  where items.id = assignments.id
  returning items.id, items.inventory_id, assignments.old_position,
            assignments.new_position, items.template_id
)
select 'moved' as result, id::text, inventory_id::text,
       old_position::text, new_position::text, template_id
from moved
order by inventory_id, old_position, id;

do $verify$
declare
  remaining bigint;
begin
  select count(*) into remaining
  from (
    select inventory_id, position_index
    from dune.items
    where inventory_id is not null and position_index is not null
      and (/*TARGET_FILTER*/)
    group by inventory_id, position_index
    having count(*) > 1
  ) conflicts;
  if remaining <> 0 then
    raise exception 'inventory repair verification failed: % duplicate slots remain', remaining;
  end if;
end
$verify$;

commit;
SQL
)

PRINT_SQL=false
while (($#)); do
  case "$1" in
    audit|repair) COMMAND="$1" ;;
    --env-file)
      shift
      [[ $# -gt 0 ]] || { echo "--env-file requires a path" >&2; exit 2; }
      ENV_FILE="$1"
      ;;
    --db)
      shift
      [[ $# -gt 0 ]] || { echo "--db requires a name" >&2; exit 2; }
      DATABASE="$1"
      ;;
    --dry-run) EXECUTE=false ;;
    --execute) EXECUTE=true ;;
    --confirm)
      shift
      [[ $# -gt 0 ]] || { echo "--confirm requires a phrase" >&2; exit 2; }
      CONFIRM="$1"
      ;;
    --production-host)
      shift
      [[ $# -gt 0 ]] || { echo "--production-host requires a hostname" >&2; exit 2; }
      PRODUCTION_HOST="$1"
      ;;
    --allow-non-production-host) ALLOW_NON_PRODUCTION_HOST=true ;;
    --exclude-inventory)
      shift
      [[ $# -gt 0 ]] || { echo "--exclude-inventory requires a numeric id" >&2; exit 2; }
      [[ "$1" =~ ^[0-9]+$ ]] || { echo "--exclude-inventory requires a numeric id" >&2; exit 2; }
      EXCLUDED_INVENTORIES+=("$1")
      ;;
    --print-repair-sql) PRINT_SQL=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

target_filter="true"
if ((${#EXCLUDED_INVENTORIES[@]})); then
  excluded_csv="$(IFS=,; echo "${EXCLUDED_INVENTORIES[*]}")"
  target_filter="inventory_id not in ($excluded_csv)"
fi
REPAIR_SQL="${REPAIR_SQL_TEMPLATE//\/\*TARGET_FILTER\*\//$target_filter}"

if [[ "$PRINT_SQL" == true ]]; then
  printf '%s\n' "$REPAIR_SQL"
  exit 0
fi

[[ -r "$ENV_FILE" ]] || { echo "env file not found: $ENV_FILE" >&2; exit 1; }
command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || { echo "$CONTAINER_RUNTIME is required" >&2; exit 1; }

compose=("$CONTAINER_RUNTIME" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$ENV_FILE")

psql_query() {
  "${compose[@]}" exec -T postgres psql -X -U dune -d "$DATABASE" \
    -v ON_ERROR_STOP=1 -At -F $'\t' -c "$1"
}

echo "Inventory slot integrity audit (database=$DATABASE)"
printf 'finding\tinventory_id\tposition_index\trows\titem_ids\ttemplate_ids\n'
psql_query "$AUDIT_SQL"
conflict_count="$(psql_query "$CONFLICT_COUNT_SQL" | tr -d '[:space:]')"
[[ "$conflict_count" =~ ^[0-9]+$ ]] || { echo "could not determine duplicate-slot count" >&2; exit 1; }

if [[ "$conflict_count" == "0" ]]; then
  echo "No duplicate inventory slots found."
  exit 0
fi

echo "$conflict_count duplicate inventory slot group(s) require repair."
if [[ "$COMMAND" != "repair" ]]; then
  echo "Run 'scripts/inventory-conflicts.sh repair' to preview the repair contract." >&2
  exit 1
fi

if [[ "$EXECUTE" != true ]]; then
  echo "Dry-run only. Repair would keep each lowest-id row and move later rows to free in-capacity slots."
  echo "No database rows or backup files were changed."
  exit 0
fi

[[ "$CONFIRM" == "REPAIR INVENTORY SLOT CONFLICTS" ]] || {
  echo "Execution requires --confirm 'REPAIR INVENTORY SLOT CONFLICTS'" >&2
  exit 2
}

current_host="$(hostname)"
if [[ "$ALLOW_NON_PRODUCTION_HOST" != true && "$current_host" != "$PRODUCTION_HOST" ]]; then
  echo "refusing inventory database repair on host '$current_host'; expected DUNE_PRODUCTION_HOST '$PRODUCTION_HOST'" >&2
  echo "Use --allow-non-production-host only for an intentional lab repair." >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$BACKUP_ROOT/$timestamp"
mkdir -p "$backup_dir"

echo "Creating mandatory pre-repair PostgreSQL backup: $backup_dir/postgres-$DATABASE.dump"
if ! "${compose[@]}" exec -T postgres pg_dump -U dune -d "$DATABASE" -Fc \
  >"$backup_dir/postgres-$DATABASE.dump"; then
  rm -f "$backup_dir/postgres-$DATABASE.dump"
  echo "pre-repair PostgreSQL dump failed; no repair was attempted" >&2
  exit 1
fi
[[ -s "$backup_dir/postgres-$DATABASE.dump" ]] || {
  rm -f "$backup_dir/postgres-$DATABASE.dump"
  echo "pre-repair PostgreSQL dump was empty; no repair was attempted" >&2
  exit 1
}

printf '%s\n' "$AUDIT_SQL" | "${compose[@]}" exec -T postgres \
  psql -X -U dune -d "$DATABASE" -v ON_ERROR_STOP=1 -At -F $'\t' -f - \
  >"$backup_dir/conflicts-before.tsv"

echo "Applying guarded inventory repair transaction."
printf '%s\n' "$REPAIR_SQL" | "${compose[@]}" exec -T postgres \
  psql -X -U dune -d "$DATABASE" -v ON_ERROR_STOP=1 -At -F $'\t' -f - \
  | tee "$backup_dir/repair-result.tsv"

printf '%s\n' "$AUDIT_SQL" | "${compose[@]}" exec -T postgres \
  psql -X -U dune -d "$DATABASE" -v ON_ERROR_STOP=1 -At -F $'\t' -f - \
  >"$backup_dir/conflicts-after.tsv"

{
  printf 'created_utc=%s\n' "$timestamp"
  printf 'hostname=%s\n' "$current_host"
  printf 'database=%s\n' "$DATABASE"
  printf 'env_file=%s\n' "$ENV_FILE"
  printf 'pre_repair_dump=%s\n' "postgres-$DATABASE.dump"
  printf 'conflicts_before=%s\n' "$conflict_count"
  printf 'excluded_inventories=%s\n' "${excluded_csv:-}"
  printf 'confirmation=%s\n' "$CONFIRM"
} >"$backup_dir/manifest.txt"

echo "Inventory repair committed and verified. Recovery artifacts: $backup_dir"
