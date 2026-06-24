#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/audit-dd1-base-ownership.sh [ENV_FILE]

Read-only audit for DD1 base ownership drift. It fails if DD1 totem permission
owners or DD1 BRT backups point at missing player controller actors.

Environment:
  DUNE_DD1_OWNERSHIP_AUDIT_PARTITION  DD1 partition id. Default: 8
  DUNE_DD1_OWNERSHIP_AUDIT_MAPS       Comma list of DD1 map names.
                                      Default: DeepDesert,DeepDesert_1
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-${ENV_FILE:-.env}}"
if [[ "${BASH_SOURCE[0]:-}" == "" || "${BASH_SOURCE[0]}" == "bash" || "${BASH_SOURCE[0]}" == "/dev/stdin" ]]; then
  repo_root="$(pwd)"
  script_dir="$repo_root/scripts"
else
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd -- "$script_dir/.." && pwd)"
fi
cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\''"]|["'\''"]$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

container_runtime="${CONTAINER_RUNTIME:-docker}"
COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
export COMPOSE_FILES
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "$COMPOSE_FILES"
for compose_file in "${compose_files[@]}"; do
  [[ -n "$compose_file" ]] && compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

db="${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}"
db="${db:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
db="${db:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
db="${db:-dune_sb_1_4_0_0}"
partition="${DUNE_DD1_OWNERSHIP_AUDIT_PARTITION:-8}"
maps="${DUNE_DD1_OWNERSHIP_AUDIT_MAPS:-DeepDesert,DeepDesert_1}"

psql_db() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off "$@"
}

printf 'auditing DD1 ownership: db=%s partition=%s maps=%s\n' "$db" "$partition" "$maps"

report="$(
  psql_db -qAt -v partition="$partition" -v maps="$maps" <<'SQL'
BEGIN;

CREATE TEMP TABLE dd1_audit_map_names AS
  SELECT unnest(string_to_array(:'maps', ',')) AS map
;

CREATE TEMP TABLE dd1_audit_totems AS
  SELECT a.id AS totem_id
  FROM dune.actors a
  JOIN dune.totems t ON t.id = a.id
  WHERE a.partition_id = :'partition'::integer
    AND a.map IN (SELECT map FROM dd1_audit_map_names)
;

CREATE TEMP TABLE dd1_audit_orphan_permission_ranks AS
  SELECT par.permission_actor_id AS totem_id, par.player_id, par.rank
  FROM dune.permission_actor_rank par
  JOIN dd1_audit_totems t ON t.totem_id = par.permission_actor_id
  LEFT JOIN dune.actors player_actor ON player_actor.id = par.player_id
  WHERE player_actor.id IS NULL
;

CREATE TEMP TABLE dd1_audit_missing_owner_ranks AS
  SELECT t.totem_id
  FROM dd1_audit_totems t
  WHERE NOT EXISTS (
    SELECT 1
    FROM dune.permission_actor_rank par
    JOIN dune.actors player_actor ON player_actor.id = par.player_id
    WHERE par.permission_actor_id = t.totem_id
      AND par.rank = 1
  )
;

CREATE TEMP TABLE dd1_audit_orphan_backups AS
  SELECT DISTINCT bb.id AS backup_id, bb.player_id
  FROM dune.base_backups bb
  JOIN dune.base_backup_linked_actors l ON l.id = bb.id
  JOIN dd1_audit_totems t ON t.totem_id = l.actor_id
  LEFT JOIN dune.actors player_actor ON player_actor.id = bb.player_id
  WHERE player_actor.id IS NULL
;

SELECT 'dd1_totems=' || count(*) FROM dd1_audit_totems
UNION ALL
SELECT 'orphan_permission_ranks=' || count(*) FROM dd1_audit_orphan_permission_ranks
UNION ALL
SELECT 'missing_owner_ranks=' || count(*) FROM dd1_audit_missing_owner_ranks
UNION ALL
SELECT 'orphan_backups=' || count(*) FROM dd1_audit_orphan_backups;

SELECT 'ORPHAN_PERMISSION totem=' || totem_id || ' player_id=' || player_id || ' rank=' || rank
FROM dd1_audit_orphan_permission_ranks
ORDER BY totem_id, player_id;

SELECT 'MISSING_OWNER totem=' || totem_id
FROM dd1_audit_missing_owner_ranks
ORDER BY totem_id;

SELECT 'ORPHAN_BACKUP backup=' || backup_id || ' player_id=' || player_id
FROM dd1_audit_orphan_backups
ORDER BY backup_id;

ROLLBACK;
SQL
)"

printf '%s\n' "$report"

failures="$(printf '%s\n' "$report" | awk -F= '
  $1 == "orphan_permission_ranks" {n += $2}
  $1 == "missing_owner_ranks" {n += $2}
  $1 == "orphan_backups" {n += $2}
  END {print n + 0}
')"

if [[ "$failures" != "0" ]]; then
  printf 'DD1 ownership audit failed: %s ownership issue(s)\n' "$failures" >&2
  exit 1
fi

printf 'DD1 ownership audit OK\n'
