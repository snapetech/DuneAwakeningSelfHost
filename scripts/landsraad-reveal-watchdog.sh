#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/landsraad-reveal-watchdog.sh [ENV_FILE] [--execute]

Checks the active Landsraad term for the suspended day-one state where tasks
exist but no task reveal rows were created. Dry-run is the default.

Defaults:
  DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRE_HOST=kspls0
  DUNE_LANDSRAAD_REVEAL_WATCHDOG_MIN_AGE_MINUTES=5
  DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRED_TASK_COUNT=25
  DUNE_DATABASE=dune_sb_1_4_0_0
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

host_short() {
  local host_ns=""
  if command -v nsenter >/dev/null 2>&1 && [[ -e /proc/1/ns/uts ]]; then
    host_ns="$(nsenter --target 1 --uts hostname -s 2>/dev/null || true)"
  fi
  if [[ -n "$host_ns" ]]; then
    printf '%s' "$host_ns"
  else
    hostname -s 2>/dev/null || hostname
  fi
}

required_host="$(env_or_file DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRE_HOST kspls0)"
min_age_minutes="$(env_or_file DUNE_LANDSRAAD_REVEAL_WATCHDOG_MIN_AGE_MINUTES 5)"
required_task_count="$(env_or_file DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRED_TASK_COUNT 25)"
db="$(env_or_file DUNE_DATABASE dune_sb_1_4_0_0)"
container_runtime="$(env_or_file CONTAINER_RUNTIME docker)"

case "$min_age_minutes" in
  ''|*[!0-9]*) printf 'DUNE_LANDSRAAD_REVEAL_WATCHDOG_MIN_AGE_MINUTES must be a non-negative integer\n' >&2; exit 64 ;;
esac
case "$required_task_count" in
  ''|*[!0-9]*) printf 'DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRED_TASK_COUNT must be a positive integer\n' >&2; exit 64 ;;
esac
if ((required_task_count < 1)); then
  printf 'DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRED_TASK_COUNT must be at least 1\n' >&2
  exit 64
fi

current_host="$(host_short)"
if [[ "$execute" == true && -n "$required_host" && "$current_host" != "$required_host" ]]; then
  printf 'skipping Landsraad reveal watchdog on host %s; required host is %s\n' "$current_host" "$required_host" >&2
  exit 0
fi

compose_files="$("$script_dir/compose-files.sh" "$env_file")"
compose=("$container_runtime" compose --env-file "$env_file")
IFS=':' read -ra files <<< "$compose_files"
for file in "${files[@]}"; do
  compose+=(-f "$file")
done

psql_base=(
  "${compose[@]}" exec -T postgres
  psql -U dune -d "$db" -v ON_ERROR_STOP=1
  -v "min_age_minutes=$min_age_minutes"
  -v "required_task_count=$required_task_count"
)

if [[ "$execute" != true ]]; then
  "${psql_base[@]}" <<'SQL'
\pset pager off
SELECT set_config('landsraad_reveal_watchdog.min_age_minutes', :'min_age_minutes', false);
SELECT set_config('landsraad_reveal_watchdog.required_task_count', :'required_task_count', false);

\echo landsraad_reveal_watchdog_preview
WITH current_term AS (
  SELECT term_id, start_time, end_time, last_processed_reveal_day
    FROM dune.landsraad_decree_term
   WHERE now() >= start_time
     AND now() < end_time
   ORDER BY term_id DESC
   LIMIT 1
),
state AS (
  SELECT ct.term_id,
         ct.start_time,
         ct.end_time,
         ct.last_processed_reveal_day,
         (SELECT count(*) FROM dune.landsraad_tasks t WHERE t.term_id = ct.term_id) AS task_count,
         (SELECT count(*)
            FROM dune.landsraad_task_reveal_state r
            JOIN dune.landsraad_tasks t ON t.id = r.task_id
           WHERE t.term_id = ct.term_id) AS reveal_rows,
         (SELECT array_agg(t.house_name ORDER BY t.board_index)
            FROM dune.landsraad_tasks t
           WHERE t.term_id = ct.term_id
             AND t.board_index BETWEEN 0 AND 4) AS selected_houses
    FROM current_term ct
)
SELECT term_id,
       start_time,
       end_time,
       last_processed_reveal_day,
       task_count,
       reveal_rows,
       selected_houses,
       CASE
         WHEN term_id IS NULL THEN 'skip: no active term'
         WHEN now() < start_time + make_interval(mins => current_setting('landsraad_reveal_watchdog.min_age_minutes')::integer) THEN 'skip: active term is not old enough'
         WHEN task_count <> current_setting('landsraad_reveal_watchdog.required_task_count')::integer THEN 'skip: unexpected task count'
         WHEN last_processed_reveal_day <> 0 THEN 'skip: reveal day already processed'
         WHEN reveal_rows <> 0 THEN 'skip: reveal rows already exist'
         WHEN array_length(selected_houses, 1) <> 5 THEN 'skip: expected five day-one houses'
         ELSE 'eligible: would reveal day-one boards 0-4 for Atreides and Harkonnen'
       END AS verdict
  FROM state
UNION ALL
SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'skip: no active term'
 WHERE NOT EXISTS (SELECT 1 FROM state);
SQL
  exit 0
fi

printf 'Executing Landsraad reveal watchdog: min_age_minutes=%s required_task_count=%s db=%s\n' "$min_age_minutes" "$required_task_count" "$db"
"${psql_base[@]}" <<'SQL'
\pset pager off
BEGIN;
SELECT set_config('landsraad_reveal_watchdog.min_age_minutes', :'min_age_minutes', true);
SELECT set_config('landsraad_reveal_watchdog.required_task_count', :'required_task_count', true);

CREATE TABLE IF NOT EXISTS dune.landsraad_reveal_watchdog_audit (
  id bigserial PRIMARY KEY,
  checked_at timestamp with time zone NOT NULL DEFAULT now(),
  action text NOT NULL,
  term_id bigint,
  before_last_processed_reveal_day integer,
  before_reveal_rows integer,
  after_last_processed_reveal_day integer,
  after_reveal_rows integer,
  selected_houses text[],
  reason text,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);

DO $$
DECLARE
  v_term_id bigint;
  v_start_time timestamp with time zone;
  v_end_time timestamp with time zone;
  v_last_processed_reveal_day integer;
  v_task_count integer;
  v_reveal_rows integer;
  v_selected_houses text[];
  v_after_last_processed_reveal_day integer;
  v_after_reveal_rows integer;
  v_reason text;
  v_revealed_rows integer := 0;
BEGIN
  SELECT ct.term_id,
         ct.start_time,
         ct.end_time,
         ct.last_processed_reveal_day,
         (SELECT count(*)::integer FROM dune.landsraad_tasks t WHERE t.term_id = ct.term_id),
         (SELECT count(*)::integer
            FROM dune.landsraad_task_reveal_state r
            JOIN dune.landsraad_tasks t ON t.id = r.task_id
           WHERE t.term_id = ct.term_id),
         (SELECT array_agg(t.house_name ORDER BY t.board_index)
            FROM dune.landsraad_tasks t
           WHERE t.term_id = ct.term_id
             AND t.board_index BETWEEN 0 AND 4)
    INTO v_term_id,
         v_start_time,
         v_end_time,
         v_last_processed_reveal_day,
         v_task_count,
         v_reveal_rows,
         v_selected_houses
    FROM dune.landsraad_decree_term ct
   WHERE now() >= ct.start_time
     AND now() < ct.end_time
   ORDER BY ct.term_id DESC
   LIMIT 1;

  IF v_term_id IS NULL THEN
    v_reason := 'no active term';
  ELSIF now() < v_start_time + make_interval(mins => current_setting('landsraad_reveal_watchdog.min_age_minutes')::integer) THEN
    v_reason := 'active term is not old enough';
  ELSIF v_task_count <> current_setting('landsraad_reveal_watchdog.required_task_count')::integer THEN
    v_reason := format('unexpected task count: %s', v_task_count);
  ELSIF v_last_processed_reveal_day <> 0 THEN
    v_reason := format('reveal day already processed: %s', v_last_processed_reveal_day);
  ELSIF v_reveal_rows <> 0 THEN
    v_reason := format('reveal rows already exist: %s', v_reveal_rows);
  ELSIF array_length(v_selected_houses, 1) <> 5 THEN
    v_reason := format('expected five day-one houses, got %s', COALESCE(array_length(v_selected_houses, 1), 0));
  ELSE
    SELECT count(*)::integer
      INTO v_revealed_rows
      FROM dune.landsraad_perform_daily_task_reveal(
             v_term_id,
             ARRAY['Atreides','Harkonnen']::text[],
             v_selected_houses,
             1
           );

    SELECT ct.last_processed_reveal_day,
           (SELECT count(*)::integer
              FROM dune.landsraad_task_reveal_state r
              JOIN dune.landsraad_tasks t ON t.id = r.task_id
             WHERE t.term_id = ct.term_id)
      INTO v_after_last_processed_reveal_day,
           v_after_reveal_rows
      FROM dune.landsraad_decree_term ct
     WHERE ct.term_id = v_term_id;

    INSERT INTO dune.landsraad_reveal_watchdog_audit (
      action,
      term_id,
      before_last_processed_reveal_day,
      before_reveal_rows,
      after_last_processed_reveal_day,
      after_reveal_rows,
      selected_houses,
      reason,
      details
    )
    VALUES (
      'repair-day-1',
      v_term_id,
      v_last_processed_reveal_day,
      v_reveal_rows,
      v_after_last_processed_reveal_day,
      v_after_reveal_rows,
      v_selected_houses,
      'revealed day-one boards 0-4 for Atreides and Harkonnen',
      jsonb_build_object(
        'revealed_rows_returned', v_revealed_rows,
        'min_age_minutes', current_setting('landsraad_reveal_watchdog.min_age_minutes')::integer,
        'required_task_count', current_setting('landsraad_reveal_watchdog.required_task_count')::integer
      )
    );

    RAISE NOTICE 'Landsraad reveal watchdog repaired term %, reveal rows % -> %, last_processed_reveal_day % -> %',
      v_term_id,
      v_reveal_rows,
      v_after_reveal_rows,
      v_last_processed_reveal_day,
      v_after_last_processed_reveal_day;
    RETURN;
  END IF;

  INSERT INTO dune.landsraad_reveal_watchdog_audit (
    action,
    term_id,
    before_last_processed_reveal_day,
    before_reveal_rows,
    after_last_processed_reveal_day,
    after_reveal_rows,
    selected_houses,
    reason,
    details
  )
  VALUES (
    'skip',
    v_term_id,
    v_last_processed_reveal_day,
    v_reveal_rows,
    v_last_processed_reveal_day,
    v_reveal_rows,
    v_selected_houses,
    v_reason,
    jsonb_build_object(
      'start_time', v_start_time,
      'end_time', v_end_time,
      'task_count', v_task_count,
      'min_age_minutes', current_setting('landsraad_reveal_watchdog.min_age_minutes')::integer,
      'required_task_count', current_setting('landsraad_reveal_watchdog.required_task_count')::integer
    )
  );

  RAISE NOTICE 'Landsraad reveal watchdog skipped: %', v_reason;
END $$;

\echo latest_landsraad_reveal_watchdog_audit
SELECT id,
       checked_at,
       action,
       term_id,
       before_last_processed_reveal_day,
       before_reveal_rows,
       after_last_processed_reveal_day,
       after_reveal_rows,
       selected_houses,
       reason
  FROM dune.landsraad_reveal_watchdog_audit
 ORDER BY id DESC
 LIMIT 1;
COMMIT;
SQL
