#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/discover-player-state.sh [env-file]

Lists candidate player/session/account tables and functions from the local
Postgres schema. This is a discovery helper; inspect output before wiring any
new field into status or dashboards.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")
db=dune_sb_1_4_0_0

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

if ! command -v "$container_runtime" >/dev/null 2>&1; then
  printf '%s is required\n' "$container_runtime" >&2
  exit 1
fi

"${compose[@]}" exec -T postgres psql -U dune -d "$db" <<'SQL'
\pset pager off

select n.nspname as schema,
       p.proname as function,
       pg_get_function_arguments(p.oid) as arguments,
       pg_get_function_result(p.oid) as returns
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and p.proname in (
    'get_online_player_controller_ids_on_farm',
    'get_all_online_or_recently_disconnected_player_online_state',
    'get_player_online_state_within_grace_period_for_each_server',
    'load_travel_to_player_info',
    'save_login_target_dimension',
    'set_all_inactive_players_in_farm_offline',
    'set_players_from_server_ids_offline'
  )
order by n.nspname, p.proname;

select n.nspname as schema,
       c.relname as table,
       pg_total_relation_size(c.oid) as bytes,
       obj_description(c.oid) as comment
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('r', 'p', 'v', 'm')
  and n.nspname not in ('pg_catalog', 'information_schema')
  and (
    c.relname ~* 'player|account|session|online|character|controller|login|party|guild'
    or obj_description(c.oid) ~* 'player|account|session|online|character|controller|login'
  )
order by n.nspname, c.relname;

select n.nspname as schema,
       p.proname as function,
       pg_get_function_arguments(p.oid) as arguments,
       pg_get_function_result(p.oid) as returns
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and p.proname ~* 'player|account|session|online|character|controller|login|farm'
order by n.nspname, p.proname;

select table_schema,
       table_name,
       column_name,
       data_type
from information_schema.columns
where table_schema not in ('pg_catalog', 'information_schema')
  and column_name ~* 'player|account|session|online|character|controller|login|steam|funcom|server|farm'
order by table_schema, table_name, ordinal_position;
SQL
