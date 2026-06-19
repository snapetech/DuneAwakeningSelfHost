#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
interval="${DUNE_BRT_DD_DB_WATCH_INTERVAL_SECONDS:-5}"
required_host="${DUNE_BRT_DD_DB_WATCH_HOST:-kspls0}"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_DB_WATCH_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "ERROR: refusing to watch on host '$short_host'; required '$required_host'." >&2
  exit 1
fi

cd "$repo_root"

db_name="$(
  awk -F= '
    /^DUNE_GAME_DB_NAME=/ {
      sub(/^[^=]*=/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$env_file"
)"
db_name="${db_name:-dune_sb_1_4_5_0}"

while true; do
  date -u '+%Y-%m-%dT%H:%M:%SZ DB_WATCH_POLL'
  docker compose --env-file "$env_file" exec -T postgres \
    psql -U dune -d "$db_name" -qAt -P pager=off -v ON_ERROR_STOP=1 <<'SQL'
select coalesce(
  string_agg(funcname || '=' || calls::text, ' ' order by funcname),
  'no_base_backup_function_stats'
)
from pg_stat_user_functions
where schemaname = 'dune'
  and funcname like 'base_backup%';
select 'base_backups=' || count(*) from dune.base_backups;
select 'base_backup_linked_actors=' || count(*) from dune.base_backup_linked_actors;
select 'latest_backups=' || coalesce(
  string_agg(id::text || ':' || player_id::text || ':' || base_backup_name, ',' order by id desc),
  'none'
)
from (
  select id, player_id, base_backup_name
  from dune.base_backups
  order by id desc
  limit 5
) recent;
select 'latest_linked_actor_counts=' || coalesce(
  string_agg(id::text || ':' || linked_count::text, ',' order by id desc),
  'none'
)
from (
  select bb.id, count(l.actor_id) as linked_count
  from dune.base_backups bb
  left join dune.base_backup_linked_actors l on l.id = bb.id
  group by bb.id
  order by bb.id desc
  limit 5
) recent;
SQL
  sleep "$interval"
done
