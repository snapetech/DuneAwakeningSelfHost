#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/repair-dd1-base-ownership.sh [options]

Repairs DD1 totem permission and BRT backup ownership for a current character.
Dry-run is the default. Live mutation requires --execute on kspls0 plus CONFIRM.

Options:
  --env-file FILE       Env file. Default: .env
  --character NAME      Current character name to own the base.
  --account-id ID       Current account_id to own the base.
  --player-id ID        Current player_controller_id to own the base.
  --totem-id ID         DD1 totem actor id to repair. Required.
  --execute             Apply the repair. Default is dry-run.
  --keep-old-ranks      Do not delete permission ranks for missing player actors.
  -h, --help            Show this help.

Environment:
  DUNE_DD1_REPAIR_REQUIRED_HOST  Required live hostname. Default: kspls0
  CONFIRM                        Required value for --execute:
                                 REPAIR DD1 BASE OWNERSHIP
USAGE
}

env_file=".env"
character=""
account_id=""
player_id=""
totem_id=""
execute=false
keep_old_ranks=false
required_host="${DUNE_DD1_REPAIR_REQUIRED_HOST:-kspls0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_file="${2:?missing value for --env-file}"
      shift 2
      ;;
    --character|--character-name)
      character="${2:?missing value for --character}"
      shift 2
      ;;
    --account-id)
      account_id="${2:?missing value for --account-id}"
      shift 2
      ;;
    --player-id)
      player_id="${2:?missing value for --player-id}"
      shift 2
      ;;
    --totem-id)
      totem_id="${2:?missing value for --totem-id}"
      shift 2
      ;;
    --execute)
      execute=true
      shift
      ;;
    --keep-old-ranks)
      keep_old_ranks=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$totem_id" || ! "$totem_id" =~ ^[0-9]+$ ]]; then
  printf 'ERROR: --totem-id is required and must be an integer\n' >&2
  exit 2
fi
if [[ -n "$account_id" && ! "$account_id" =~ ^[0-9]+$ ]]; then
  printf 'ERROR: --account-id must be an integer\n' >&2
  exit 2
fi
if [[ -n "$player_id" && ! "$player_id" =~ ^[0-9]+$ ]]; then
  printf 'ERROR: --player-id must be an integer\n' >&2
  exit 2
fi
if [[ -z "$character" && -z "$account_id" && -z "$player_id" ]]; then
  printf 'ERROR: provide --character, --account-id, or --player-id\n' >&2
  exit 2
fi

if [[ "${BASH_SOURCE[0]:-}" == "" || "${BASH_SOURCE[0]}" == "bash" || "${BASH_SOURCE[0]}" == "/dev/stdin" ]]; then
  repo_root="$(pwd)"
  script_dir="$repo_root/scripts"
else
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd -- "$script_dir/.." && pwd)"
fi
cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'ERROR: env file not found: %s\n' "$env_file" >&2
  exit 1
fi

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$execute" == true ]]; then
  if [[ "$short_host" != "$required_host" ]]; then
    printf "ERROR: refusing live repair on host '%s'; required '%s'\n" "$short_host" "$required_host" >&2
    exit 1
  fi
  if [[ "${CONFIRM:-}" != "REPAIR DD1 BASE OWNERSHIP" ]]; then
    printf "ERROR: --execute requires CONFIRM='REPAIR DD1 BASE OWNERSHIP'\n" >&2
    exit 1
  fi
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

psql_db() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off "$@"
}

mode="DRY RUN"
commit_sql="ROLLBACK;"
if [[ "$execute" == true ]]; then
  mode="EXECUTE"
  commit_sql="COMMIT;"
fi

printf 'mode=%s host=%s db=%s totem_id=%s character=%s account_id=%s player_id=%s keep_old_ranks=%s\n' \
  "$mode" "$short_host" "$db" "$totem_id" "${character:-}" "${account_id:-}" "${player_id:-}" "$keep_old_ranks"

psql_db \
  -v totem_id="$totem_id" \
  -v character="$character" \
  -v account_id="$account_id" \
  -v player_id="$player_id" \
  -v keep_old_ranks="$keep_old_ranks" \
  -v commit_sql="$commit_sql" <<'SQL'
BEGIN;

CREATE TEMP TABLE dd1_repair_target AS
WITH requested AS (
  SELECT
    NULLIF(:'character', '') AS character_name,
    NULLIF(:'account_id', '')::bigint AS account_id,
    NULLIF(:'player_id', '')::bigint AS player_id
),
resolved AS (
  SELECT
    ps.account_id,
    ps.character_name,
    ps.player_controller_id,
    a.map,
    a.partition_id,
    a.dimension_index
  FROM requested r
  JOIN dune.player_state ps ON
    (r.player_id IS NOT NULL AND ps.player_controller_id = r.player_id)
    OR (r.account_id IS NOT NULL AND ps.account_id = r.account_id)
    OR (r.character_name IS NOT NULL AND lower(ps.character_name) = lower(r.character_name))
  JOIN dune.actors a ON a.id = ps.player_controller_id
)
SELECT * FROM resolved;

CREATE TEMP TABLE dd1_repair_validation AS
WITH target AS (
  SELECT count(*)::integer AS target_count FROM dd1_repair_target
),
target_partition AS (
  SELECT partition_id, map FROM dd1_repair_target LIMIT 1
),
totem_partition AS (
  SELECT a.partition_id, a.map
  FROM dune.actors a
  JOIN dune.totems t ON t.id = a.id
  WHERE a.id = :'totem_id'::bigint
)
SELECT
  target.target_count,
  target_partition.partition_id AS target_partition_id,
  target_partition.map AS target_map,
  totem_partition.partition_id AS totem_partition_id,
  totem_partition.map AS totem_map
FROM target
LEFT JOIN target_partition ON true
LEFT JOIN totem_partition ON true;

SELECT 'validation' AS section, * FROM dd1_repair_validation;

DO $$
DECLARE
  v record;
BEGIN
  SELECT * INTO v FROM dd1_repair_validation;
  IF v.target_count <> 1 THEN
    RAISE EXCEPTION 'expected exactly one current player target, got %', v.target_count;
  END IF;
  IF v.totem_partition_id IS NULL THEN
    RAISE EXCEPTION 'totem was not found';
  END IF;
  IF v.target_partition_id <> 8 THEN
    RAISE EXCEPTION 'target player_controller_id is not in DD1 partition 8; got partition % map %',
      v.target_partition_id, v.target_map;
  END IF;
  IF v.totem_partition_id <> 8 THEN
    RAISE EXCEPTION 'totem is not in DD1 partition 8; got partition % map %',
      v.totem_partition_id, v.totem_map;
  END IF;
END $$;

SELECT 'target' AS section, * FROM dd1_repair_target;

SELECT
  'totem_before' AS section,
  a.id AS totem_id,
  a.map,
  a.partition_id,
  a.dimension_index,
  ((a.transform).location).x::float8 AS x,
  ((a.transform).location).y::float8 AS y,
  ((a.transform).location).z::float8 AS z,
  p.owner_entity_id,
  t.last_backup_timestamp
FROM dune.actors a
JOIN dune.totems t ON t.id = a.id
LEFT JOIN dune.placeables p ON p.id = a.id
WHERE a.id = :'totem_id'::bigint;

SELECT
  'permission_before' AS section,
  pa.actor_id,
  pa.actor_name,
  pa.actor_type,
  pa.access_level,
  par.player_id,
  ps.character_name,
  actor.id IS NOT NULL AS player_actor_exists,
  par.rank
FROM dune.permission_actor pa
LEFT JOIN dune.permission_actor_rank par ON par.permission_actor_id = pa.actor_id
LEFT JOIN dune.player_state ps ON ps.player_controller_id = par.player_id
LEFT JOIN dune.actors actor ON actor.id = par.player_id
WHERE pa.actor_id = :'totem_id'::bigint
ORDER BY par.rank, par.player_id;

SELECT
  'backups_before' AS section,
  bb.id,
  bb.player_id,
  ps.character_name,
  actor.id IS NOT NULL AS player_actor_exists,
  bb.base_backup_name,
  count(l.actor_id)::integer AS linked_actors
FROM dune.base_backups bb
JOIN dune.base_backup_linked_actors l ON l.id = bb.id
LEFT JOIN dune.player_state ps ON ps.player_controller_id = bb.player_id
LEFT JOIN dune.actors actor ON actor.id = bb.player_id
WHERE l.actor_id = :'totem_id'::bigint
GROUP BY bb.id, bb.player_id, ps.character_name, actor.id, bb.base_backup_name
ORDER BY bb.id;

INSERT INTO dune.permission_actor(actor_id, actor_name, actor_type, access_level, is_child)
VALUES (:'totem_id'::bigint, '##Totem_Placeable', 3, 3, false)
ON CONFLICT (actor_id) DO UPDATE SET
  actor_name = EXCLUDED.actor_name,
  actor_type = EXCLUDED.actor_type,
  access_level = EXCLUDED.access_level,
  is_child = EXCLUDED.is_child;

INSERT INTO dune.permission_actor_rank(permission_actor_id, player_id, rank)
SELECT :'totem_id'::bigint, player_controller_id, 1
FROM dd1_repair_target
ON CONFLICT (permission_actor_id, player_id) DO UPDATE SET rank = EXCLUDED.rank;

DELETE FROM dune.permission_actor_rank par
WHERE :'keep_old_ranks' <> 'true'
  AND par.permission_actor_id = :'totem_id'::bigint
  AND par.rank = 1
  AND par.player_id <> (SELECT player_controller_id FROM dd1_repair_target)
  AND NOT EXISTS (SELECT 1 FROM dune.actors a WHERE a.id = par.player_id);

UPDATE dune.base_backups bb
SET player_id = (SELECT player_controller_id FROM dd1_repair_target)
WHERE EXISTS (
  SELECT 1
  FROM dune.base_backup_linked_actors l
  WHERE l.id = bb.id
    AND l.actor_id = :'totem_id'::bigint
)
AND NOT EXISTS (SELECT 1 FROM dune.actors a WHERE a.id = bb.player_id);

SELECT
  'permission_after' AS section,
  pa.actor_id,
  pa.actor_name,
  pa.actor_type,
  pa.access_level,
  par.player_id,
  ps.character_name,
  actor.id IS NOT NULL AS player_actor_exists,
  par.rank
FROM dune.permission_actor pa
LEFT JOIN dune.permission_actor_rank par ON par.permission_actor_id = pa.actor_id
LEFT JOIN dune.player_state ps ON ps.player_controller_id = par.player_id
LEFT JOIN dune.actors actor ON actor.id = par.player_id
WHERE pa.actor_id = :'totem_id'::bigint
ORDER BY par.rank, par.player_id;

SELECT
  'backups_after' AS section,
  bb.id,
  bb.player_id,
  ps.character_name,
  actor.id IS NOT NULL AS player_actor_exists,
  bb.base_backup_name,
  count(l.actor_id)::integer AS linked_actors
FROM dune.base_backups bb
JOIN dune.base_backup_linked_actors l ON l.id = bb.id
LEFT JOIN dune.player_state ps ON ps.player_controller_id = bb.player_id
LEFT JOIN dune.actors actor ON actor.id = bb.player_id
WHERE l.actor_id = :'totem_id'::bigint
GROUP BY bb.id, bb.player_id, ps.character_name, actor.id, bb.base_backup_name
ORDER BY bb.id;

:commit_sql
SQL
