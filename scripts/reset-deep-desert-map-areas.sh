#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/reset-deep-desert-map-areas.sh [ENV_FILE] [--execute]

Clears Deep Desert scan/probe area state from dune.map_areas after first
creating a timestamped backup table in the dune schema. Dry-run is the default.

Scope:
  - affects every account with map_name='DeepDesert'
  - affects both Casual and Hardcore DD scan/probe state, because this table is
    keyed by map_name and has no dimension_index
  - does not reset bases, actors, resources, spice fields, POI marker rows, or
    world partitions

Defaults:
  DUNE_DD_MAP_AREAS_MAP_NAME=DeepDesert
  DUNE_DD_MAP_AREAS_REQUIRE_HOST=kspls0
USAGE
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="${DUNE_ENV_FILE:-.env}"
execute=false

while (($#)); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --execute)
      execute=true
      ;;
    *)
      env_file="$1"
      ;;
  esac
  shift
done

cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 1
fi

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

env_or_file() {
  local key="$1" default_value="${2:-}" value
  value="${!key:-}"
  if [[ -z "$value" ]]; then
    value="$(read_env "$key")"
  fi
  printf '%s' "${value:-$default_value}"
}

container_runtime="${CONTAINER_RUNTIME:-docker}"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi

compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

db="${DUNE_DB_NAME:-$(env_or_file DUNE_DB_NAME dune_sb_1_4_0_0)}"
map_name="$(env_or_file DUNE_DD_MAP_AREAS_MAP_NAME DeepDesert)"
required_host="$(env_or_file DUNE_DD_MAP_AREAS_REQUIRE_HOST kspls0)"
backup_suffix="$(date -u +%Y%m%dT%H%M%SZ)"
backup_table="operator_map_areas_${map_name,,}_backup_${backup_suffix}"
backup_table="${backup_table//[^a-zA-Z0-9_]/_}"

if [[ ! "$map_name" =~ ^[A-Za-z0-9_]+$ ]]; then
  printf 'refusing unsafe map name: %s\n' "$map_name" >&2
  exit 2
fi

if [[ "$execute" == true ]]; then
  current_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
  if [[ "$current_host" != "$required_host" ]]; then
    printf 'refusing live map-area reset on host %s; required host is %s\n' "$current_host" "$required_host" >&2
    exit 1
  fi
fi

if [[ "$execute" != true ]]; then
  printf 'dry run; pass --execute to clear map area rows\n'
  printf 'env_file=%s\n' "$env_file"
  printf 'db=%s\n' "$db"
  printf 'map_name=%s\n' "$map_name"
  printf 'backup_table=dune.%s\n' "$backup_table"
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off <<SQL
SELECT count(*) AS rows_to_delete
FROM dune.map_areas
WHERE map_name = '$map_name';

SELECT count(distinct account_id) AS affected_accounts
FROM dune.map_areas
WHERE map_name = '$map_name';
SQL
  exit 0
fi

"${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off <<SQL
BEGIN;

CREATE TABLE dune.$backup_table AS
SELECT now() AS backed_up_at, m.*
FROM dune.map_areas m
WHERE m.map_name = '$map_name';

SELECT count(*) AS backed_up_rows
FROM dune.$backup_table;

DELETE FROM dune.map_areas
WHERE map_name = '$map_name';

SELECT count(*) AS remaining_rows
FROM dune.map_areas
WHERE map_name = '$map_name';

COMMIT;
SQL

printf 'cleared map area rows for map_name=%s; backup table=dune.%s\n' "$map_name" "$backup_table"
