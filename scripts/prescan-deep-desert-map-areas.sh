#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/prescan-deep-desert-map-areas.sh [ENV_FILE] [options]

Pre-populates Deep Desert scan/probe area state for one account in dune.map_areas.
Dry-run is the default. Use --execute only on the live host.

Options:
  --account-id ID        Target an exact account id.
  --character NAME      Target an exact character name. Default: Paul.
  --funcom-id ID        Target an exact Funcom id.
  --platform-id ID      Target an exact platform id.
  --map-name NAME       Map-area name. Default: DeepDesert.
  --first-area-id ID    First area id to fill. Default: 1.
  --last-area-id ID     Last area id to fill. Default: 82.
  --no-marker-survey    Fill area coverage only; do not synthesize survey JSON
                        from dune.markers.
  --ensure-paul         If Paul is missing, create/refresh the synthetic Paul
                        account with dune.login_account before resolving target.
  --execute             Apply the mutation. Refuses unless hostname is kspls0
                        by default.

Environment:
  DUNE_DD_PRESCAN_REQUIRE_HOST=kspls0
  DUNE_DD_PRESCAN_DEFAULT_CHARACTER=Paul
USAGE
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="${DUNE_ENV_FILE:-.env}"
execute=false
ensure_paul=false
with_marker_survey=true
account_id=""
character="${DUNE_DD_PRESCAN_DEFAULT_CHARACTER:-Paul}"
funcom_id=""
platform_id=""
map_name="${DUNE_DD_PRESCAN_MAP_NAME:-DeepDesert}"
first_area_id="${DUNE_DD_PRESCAN_FIRST_AREA_ID:-1}"
last_area_id="${DUNE_DD_PRESCAN_LAST_AREA_ID:-82}"

while (($#)); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --execute)
      execute=true
      ;;
    --ensure-paul)
      ensure_paul=true
      ;;
    --no-marker-survey)
      with_marker_survey=false
      ;;
    --account-id)
      account_id="${2:-}"
      shift
      ;;
    --character)
      character="${2:-}"
      shift
      ;;
    --funcom-id)
      funcom_id="${2:-}"
      shift
      ;;
    --platform-id)
      platform_id="${2:-}"
      shift
      ;;
    --map-name)
      map_name="${2:-}"
      shift
      ;;
    --first-area-id)
      first_area_id="${2:-}"
      shift
      ;;
    --last-area-id)
      last_area_id="${2:-}"
      shift
      ;;
    --*)
      printf 'unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
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

if [[ -n "$account_id" && ! "$account_id" =~ ^[0-9]+$ ]]; then
  printf 'invalid --account-id: %s\n' "$account_id" >&2
  exit 2
fi
if [[ ! "$first_area_id" =~ ^[0-9]+$ || ! "$last_area_id" =~ ^[0-9]+$ || "$first_area_id" -gt "$last_area_id" ]]; then
  printf 'invalid area id range: %s..%s\n' "$first_area_id" "$last_area_id" >&2
  exit 2
fi
if [[ ! "$map_name" =~ ^[A-Za-z0-9_]+$ ]]; then
  printf 'refusing unsafe map name: %s\n' "$map_name" >&2
  exit 2
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
required_host="$(env_or_file DUNE_DD_PRESCAN_REQUIRE_HOST kspls0)"
backup_suffix="$(date -u +%Y%m%dT%H%M%SZ)"
backup_table="operator_map_areas_prescan_${map_name,,}_${backup_suffix}"
backup_table="${backup_table//[^a-zA-Z0-9_]/_}"

if [[ "$execute" == true ]]; then
  current_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
  if [[ "$current_host" != "$required_host" ]]; then
    printf 'refusing Deep Desert prescan mutation on host %s; required host is %s\n' "$current_host" "$required_host" >&2
    exit 1
  fi
fi

psql_args=(
  -v ON_ERROR_STOP=1
  -P pager=off
  -v target_account_id="$account_id"
  -v target_character="$character"
  -v target_funcom_id="$funcom_id"
  -v target_platform_id="$platform_id"
  -v map_name="$map_name"
  -v first_area_id="$first_area_id"
  -v last_area_id="$last_area_id"
  -v with_marker_survey="$with_marker_survey"
  -v backup_table="$backup_table"
)

if [[ "$execute" != true ]]; then
  printf 'dry run; pass --execute to write Deep Desert map-area rows\n'
  printf 'env_file=%s\n' "$env_file"
  printf 'db=%s\n' "$db"
  printf 'target account_id=%s character=%s funcom_id=%s platform_id=%s\n' "${account_id:-<auto>}" "${character:-<none>}" "${funcom_id:-<none>}" "${platform_id:-<none>}"
  printf 'map_name=%s area_ids=%s..%s marker_survey=%s\n' "$map_name" "$first_area_id" "$last_area_id" "$with_marker_survey"
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" "${psql_args[@]}" <<'SQL'
WITH target AS (
  SELECT ps.account_id, ps.character_name, a.funcom_id, a.platform_name, a.platform_id
  FROM dune.player_state ps
  LEFT JOIN dune.accounts a ON a.id = ps.account_id
  WHERE
    (NULLIF(:'target_account_id', '') IS NOT NULL AND ps.account_id = NULLIF(:'target_account_id', '')::bigint)
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_character' <> '' AND lower(ps.character_name) = lower(:'target_character'))
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_funcom_id' <> '' AND a.funcom_id = :'target_funcom_id')
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_platform_id' <> '' AND a.platform_id = :'target_platform_id')
  ORDER BY
    CASE WHEN lower(ps.character_name) = lower(:'target_character') THEN 0 ELSE 1 END,
    ps.account_id
  LIMIT 1
),
existing AS (
  SELECT ma.*
  FROM dune.map_areas ma
  JOIN target t ON t.account_id = ma.account_id
  WHERE ma.map_name = :'map_name'
),
marker_summary AS (
  SELECT count(*) AS marker_rows,
         count(DISTINCT m.area_id) FILTER (WHERE m.area_id BETWEEN :first_area_id::smallint AND :last_area_id::smallint) AS marker_areas
  FROM dune.markers m
  JOIN dune.map_names mn ON mn.map_name_id = m.map_name_id
  WHERE mn.map_name = :'map_name'
)
SELECT 'target' AS section, row_to_json(target)::text AS value FROM target
UNION ALL
SELECT 'existing_rows', json_build_object(
  'rows', count(*),
  'areas', count(DISTINCT area_id),
  'minArea', min(area_id),
  'maxArea', max(area_id),
  'surveyRows', count(*) FILTER (WHERE items_surveyed_target IS NOT NULL OR items_surveyed_progress IS NOT NULL)
)::text
FROM existing
UNION ALL
SELECT 'planned_rows', json_build_object(
  'areaIds', (:last_area_id::integer - :first_area_id::integer + 1),
  'backupTable', 'dune.' || :'backup_table',
  'markerSurvey', :'with_marker_survey',
  'markerRows', marker_rows,
  'markerAreas', marker_areas
)::text
FROM marker_summary;
SQL
  exit 0
fi

if [[ "$ensure_paul" == true ]]; then
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off <<'SQL'
SELECT *
FROM dune.login_account('A000000000000001','ADMIN#00001','PAUL','Paul',0,'Paul',0,0)
LIMIT 1;
SQL
fi

"${compose[@]}" exec -T postgres psql -U dune -d "$db" "${psql_args[@]}" <<'SQL'
BEGIN;

CREATE TABLE dune.:backup_table AS
WITH target AS (
  SELECT ps.account_id
  FROM dune.player_state ps
  LEFT JOIN dune.accounts a ON a.id = ps.account_id
  WHERE
    (NULLIF(:'target_account_id', '') IS NOT NULL AND ps.account_id = NULLIF(:'target_account_id', '')::bigint)
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_character' <> '' AND lower(ps.character_name) = lower(:'target_character'))
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_funcom_id' <> '' AND a.funcom_id = :'target_funcom_id')
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_platform_id' <> '' AND a.platform_id = :'target_platform_id')
  ORDER BY
    CASE WHEN lower(ps.character_name) = lower(:'target_character') THEN 0 ELSE 1 END,
    ps.account_id
  LIMIT 1
)
SELECT now() AS backed_up_at, ma.*
FROM dune.map_areas ma
JOIN target t ON t.account_id = ma.account_id
WHERE ma.map_name = :'map_name';

WITH target AS (
  SELECT ps.account_id
  FROM dune.player_state ps
  LEFT JOIN dune.accounts a ON a.id = ps.account_id
  WHERE
    (NULLIF(:'target_account_id', '') IS NOT NULL AND ps.account_id = NULLIF(:'target_account_id', '')::bigint)
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_character' <> '' AND lower(ps.character_name) = lower(:'target_character'))
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_funcom_id' <> '' AND a.funcom_id = :'target_funcom_id')
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_platform_id' <> '' AND a.platform_id = :'target_platform_id')
  ORDER BY
    CASE WHEN lower(ps.character_name) = lower(:'target_character') THEN 0 ELSE 1 END,
    ps.account_id
  LIMIT 1
),
target_check AS (
  SELECT CASE WHEN count(*) = 1 THEN 1 ELSE 1 / 0 END AS ok
  FROM target
),
area_ids AS (
  SELECT generate_series(:first_area_id::integer, :last_area_id::integer)::smallint AS area_id
),
marker_counts AS (
  SELECT m.area_id::smallint AS area_id,
         (m.marker).marker_type::text AS marker_type,
         count(*)::integer AS amount,
         jsonb_agg(m.marker_hash_id ORDER BY m.marker_hash_id)::text AS discovered
  FROM dune.markers m
  JOIN dune.map_names mn ON mn.map_name_id = m.map_name_id
  WHERE mn.map_name = :'map_name'
    AND m.area_id BETWEEN :first_area_id::smallint AND :last_area_id::smallint
  GROUP BY m.area_id, (m.marker).marker_type
),
marker_payload AS (
  SELECT area_id,
         jsonb_build_array(jsonb_build_object('SpiceYield', 0)) ||
           jsonb_agg(
             jsonb_build_object(
               'Num', amount,
               'MarkerType', marker_type,
               'QuantityType', CASE
                 WHEN marker_type ~ '(Ore|Pickup|Wreckage|Part)' THEN 'ESurveyReportQuantityCategory::High'
                 ELSE 'ESurveyReportQuantityCategory::None'
               END
             )
             ORDER BY marker_type
           ) AS items_surveyed_target,
         jsonb_build_array(jsonb_build_object('IntelConsumed', '[]'::jsonb)) ||
           jsonb_agg(
             jsonb_build_object(
               'Type', marker_type,
               'Amount', amount,
               'Maximum', amount,
               'Discovered', discovered
             )
             ORDER BY marker_type
           ) AS items_surveyed_progress
  FROM marker_counts
  GROUP BY area_id
),
upserted AS (
  INSERT INTO dune.map_areas (
    account_id,
    area_id,
    time_discovered,
    time_first_entered,
    survey_point_marker_id,
    map_name,
    items_surveyed_target,
    items_surveyed_progress
  )
  SELECT
    t.account_id,
    a.area_id,
    now(),
    now(),
    NULL::bigint,
    :'map_name',
    CASE WHEN :'with_marker_survey' = 'true' THEN mp.items_surveyed_target ELSE NULL::jsonb END,
    CASE WHEN :'with_marker_survey' = 'true' THEN mp.items_surveyed_progress ELSE NULL::jsonb END
  FROM target t
  CROSS JOIN target_check
  CROSS JOIN area_ids a
  LEFT JOIN marker_payload mp ON mp.area_id = a.area_id
  ON CONFLICT (account_id, area_id, map_name) DO UPDATE SET
    time_discovered = COALESCE(dune.map_areas.time_discovered, EXCLUDED.time_discovered),
    time_first_entered = COALESCE(dune.map_areas.time_first_entered, EXCLUDED.time_first_entered),
    survey_point_marker_id = COALESCE(dune.map_areas.survey_point_marker_id, EXCLUDED.survey_point_marker_id),
    items_surveyed_target = COALESCE(EXCLUDED.items_surveyed_target, dune.map_areas.items_surveyed_target),
    items_surveyed_progress = COALESCE(EXCLUDED.items_surveyed_progress, dune.map_areas.items_surveyed_progress)
  RETURNING *
)
SELECT 'upserted_rows' AS metric, count(*)::text AS value FROM upserted
UNION ALL
SELECT 'survey_rows', count(*)::text FROM upserted WHERE items_surveyed_target IS NOT NULL OR items_surveyed_progress IS NOT NULL;

WITH target AS (
  SELECT ps.account_id
  FROM dune.player_state ps
  LEFT JOIN dune.accounts a ON a.id = ps.account_id
  WHERE
    (NULLIF(:'target_account_id', '') IS NOT NULL AND ps.account_id = NULLIF(:'target_account_id', '')::bigint)
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_character' <> '' AND lower(ps.character_name) = lower(:'target_character'))
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_funcom_id' <> '' AND a.funcom_id = :'target_funcom_id')
    OR (NULLIF(:'target_account_id', '') IS NULL AND :'target_platform_id' <> '' AND a.platform_id = :'target_platform_id')
  ORDER BY
    CASE WHEN lower(ps.character_name) = lower(:'target_character') THEN 0 ELSE 1 END,
    ps.account_id
  LIMIT 1
)
SELECT count(*) AS final_rows,
       min(area_id) AS min_area,
       max(area_id) AS max_area,
       count(*) FILTER (WHERE time_discovered IS NOT NULL) AS discovered_rows,
       count(*) FILTER (WHERE time_first_entered IS NOT NULL) AS entered_rows,
       count(*) FILTER (WHERE items_surveyed_target IS NOT NULL OR items_surveyed_progress IS NOT NULL) AS survey_rows
FROM dune.map_areas ma
JOIN target t ON t.account_id = ma.account_id
WHERE ma.map_name = :'map_name';

COMMIT;
SQL

printf 'prescanned %s for target character/account; backup table=dune.%s\n' "$map_name" "$backup_table"
