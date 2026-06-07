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

while true; do
  date -u '+%Y-%m-%dT%H:%M:%SZ DB_WATCH_POLL'
  docker compose --env-file "$env_file" exec -T postgres \
    psql -U dune -d dune_sb_1_4_0_0 -qAt -P pager=off -v ON_ERROR_STOP=1 <<'SQL'
select coalesce(
  string_agg(funcname || '=' || calls::text, ' ' order by funcname),
  'no_base_backup_function_stats'
)
from pg_stat_user_functions
where schemaname = 'dune'
  and funcname like 'base_backup%';
select 'base_backups=' || count(*) from dune.base_backups;
select 'base_backup_linked_actors=' || count(*) from dune.base_backup_linked_actors;
SQL
  sleep "$interval"
done
