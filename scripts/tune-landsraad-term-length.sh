#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/tune-landsraad-term-length.sh [ENV_FILE] [--execute]

Plans or applies a current Landsraad term end-time change. By default the
target is start_time + DUNE_LANDSRAAD_TERM_LENGTH_DAYS rounded up to the next
configured Coriolis cycle boundary, because Landsraad period state is derived
from Coriolis timing. Dry-run is the default.

Defaults:
  DUNE_LANDSRAAD_TERM_LENGTH_DAYS=7
  DUNE_LANDSRAAD_TERM_LENGTH_ALIGN_TO_CORIOLIS=true
  DUNE_LANDSRAAD_TERM_LENGTH_CORIOLIS_CONFIG=config/UserGame.ini
  DUNE_LANDSRAAD_TERM_LENGTH_REQUIRE_HOST=kspls0
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

read_ini_value() {
  local file="$1"
  local section="$2"
  local key="$3"
  awk -v section="$section" -v key="$key" '
    $0 ~ "^[[:space:]]*\\[" {
      in_section = ($0 == "[" section "]")
      next
    }
    in_section && $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      print
      exit
    }
  ' "$file"
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

term_days="$(env_or_file DUNE_LANDSRAAD_TERM_LENGTH_DAYS 7)"
align_to_coriolis="$(env_or_file DUNE_LANDSRAAD_TERM_LENGTH_ALIGN_TO_CORIOLIS true)"
allow_unaligned="$(env_or_file DUNE_LANDSRAAD_TERM_LENGTH_ALLOW_UNALIGNED false)"
coriolis_config="$(env_or_file DUNE_LANDSRAAD_TERM_LENGTH_CORIOLIS_CONFIG config/UserGame.ini)"
required_host="$(env_or_file DUNE_LANDSRAAD_TERM_LENGTH_REQUIRE_HOST kspls0)"
db="$(env_or_file DUNE_DATABASE dune_sb_1_4_0_0)"
container_runtime="$(env_or_file CONTAINER_RUNTIME docker)"

case "$term_days" in
  ''|*[!0-9]*) printf 'DUNE_LANDSRAAD_TERM_LENGTH_DAYS must be a positive integer\n' >&2; exit 64 ;;
esac
if ((term_days < 1)); then
  printf 'DUNE_LANDSRAAD_TERM_LENGTH_DAYS must be at least 1\n' >&2
  exit 64
fi
case "$align_to_coriolis" in
  1|true|yes|on) align_to_coriolis=true ;;
  0|false|no|off) align_to_coriolis=false ;;
  *) printf 'DUNE_LANDSRAAD_TERM_LENGTH_ALIGN_TO_CORIOLIS must be true or false\n' >&2; exit 64 ;;
esac
case "$allow_unaligned" in
  1|true|yes|on) allow_unaligned=true ;;
  0|false|no|off) allow_unaligned=false ;;
  *) printf 'DUNE_LANDSRAAD_TERM_LENGTH_ALLOW_UNALIGNED must be true or false\n' >&2; exit 64 ;;
esac
if [[ "$align_to_coriolis" != true && "$allow_unaligned" != true ]]; then
  printf 'refusing unaligned Landsraad term tuning; set DUNE_LANDSRAAD_TERM_LENGTH_ALIGN_TO_CORIOLIS=true or explicitly set DUNE_LANDSRAAD_TERM_LENGTH_ALLOW_UNALIGNED=true\n' >&2
  exit 64
fi

cycle_start_utc="1970-01-01 00:00:00+00"
cycle_days="$(env_or_file DUNE_LANDSRAAD_CORIOLIS_REQUIRED_CYCLE_DAYS 7)"
if [[ "$align_to_coriolis" == true ]]; then
  if [[ ! -f "$coriolis_config" ]]; then
    printf 'missing Coriolis config for Landsraad term alignment: %s\n' "$coriolis_config" >&2
    exit 2
  fi
  cycle_year="$(read_ini_value "$coriolis_config" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleStartYear")"
  cycle_month="$(read_ini_value "$coriolis_config" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleStartMonth")"
  cycle_day="$(read_ini_value "$coriolis_config" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleStartDay")"
  cycle_hour="$(read_ini_value "$coriolis_config" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleStartHour")"
  cycle_minute="$(read_ini_value "$coriolis_config" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleStartMinute")"
  cycle_days="$(read_ini_value "$coriolis_config" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleDurationInDays")"
  for value_name in cycle_year cycle_month cycle_day cycle_hour cycle_minute cycle_days; do
    value="${!value_name:-}"
    case "$value" in
      ''|*[!0-9]*) printf '%s is missing or not numeric in %s\n' "$value_name" "$coriolis_config" >&2; exit 64 ;;
    esac
  done
  if ((cycle_days < 1)); then
    printf 'm_CycleDurationInDays must be at least 1 in %s\n' "$coriolis_config" >&2
    exit 64
  fi
  cycle_start_utc="$(printf '%04d-%02d-%02d %02d:%02d:00+00' "$cycle_year" "$cycle_month" "$cycle_day" "$cycle_hour" "$cycle_minute")"
fi

if [[ "$execute" == true && -n "$required_host" ]]; then
  current_host="$(host_short)"
  if [[ "$current_host" != "$required_host" ]]; then
    printf 'refusing Landsraad term length tuning on host %s; required host is %s\n' "$current_host" "$required_host" >&2
    exit 78
  fi
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
  -v "term_days=$term_days"
  -v "align_to_coriolis=$align_to_coriolis"
  -v "cycle_start_utc=$cycle_start_utc"
  -v "cycle_days=$cycle_days"
)

if [[ "$execute" != true ]]; then
  "${psql_base[@]}" <<'SQL'
\pset pager off
SELECT set_config('landsraad_term_length.days', :'term_days', false);
SELECT set_config('landsraad_term_length.align_to_coriolis', :'align_to_coriolis', false);
SELECT set_config('landsraad_term_length.cycle_start_utc', :'cycle_start_utc', false);
SELECT set_config('landsraad_term_length.cycle_days', :'cycle_days', false);

DO $$
DECLARE
  days integer := current_setting('landsraad_term_length.days')::integer;
  cycle_days integer := current_setting('landsraad_term_length.cycle_days')::integer;
BEGIN
  IF days < 1 THEN
    RAISE EXCEPTION 'DUNE_LANDSRAAD_TERM_LENGTH_DAYS must be at least 1: %', days;
  END IF;
  IF cycle_days < 1 THEN
    RAISE EXCEPTION 'Coriolis cycle days must be at least 1: %', cycle_days;
  END IF;
END $$;

\echo landsraad_term_length_preview
WITH settings AS (
  SELECT current_setting('landsraad_term_length.align_to_coriolis')::boolean AS align_to_coriolis,
         current_setting('landsraad_term_length.cycle_start_utc')::timestamptz AS cycle_start,
         make_interval(days => current_setting('landsraad_term_length.cycle_days')::integer) AS cycle_duration
),
current_term AS (
  SELECT term_id,
         start_time,
         end_time,
         COALESCE(test_term, FALSE) AS test_term,
         start_time + make_interval(days => current_setting('landsraad_term_length.days')::integer) AS raw_desired_end_time
    FROM dune.landsraad_decree_term
   WHERE now() >= start_time
     AND now() < end_time
   ORDER BY term_id DESC
   LIMIT 1
),
planned AS (
  SELECT current_term.*,
         CASE
           WHEN settings.align_to_coriolis THEN
             settings.cycle_start
             + (
                 CEIL(
                   EXTRACT(EPOCH FROM (current_term.raw_desired_end_time - settings.cycle_start))
                   / EXTRACT(EPOCH FROM settings.cycle_duration)
                 ) * settings.cycle_duration
               )
           ELSE current_term.raw_desired_end_time
         END AS desired_end_time,
         CASE
           WHEN settings.align_to_coriolis THEN 'coriolis-boundary'
           ELSE 'unaligned'
         END AS alignment_mode
    FROM current_term, settings
)
SELECT term_id,
       start_time,
       end_time AS current_end_time,
       raw_desired_end_time,
       desired_end_time,
       end_time - start_time AS current_duration,
       desired_end_time - start_time AS desired_duration,
       alignment_mode,
       test_term,
       CASE
         WHEN end_time = desired_end_time THEN 'no-op'
         ELSE 'change-end-time'
       END AS planned_action
  FROM planned;
SQL
  exit 0
fi

printf 'Executing Landsraad term length tuning: days=%s align_to_coriolis=%s cycle_start=%s cycle_days=%s db=%s\n' \
  "$term_days" "$align_to_coriolis" "$cycle_start_utc" "$cycle_days" "$db"
"${psql_base[@]}" <<'SQL'
\pset pager off
BEGIN;
SELECT set_config('landsraad_term_length.days', :'term_days', true);
SELECT set_config('landsraad_term_length.align_to_coriolis', :'align_to_coriolis', true);
SELECT set_config('landsraad_term_length.cycle_start_utc', :'cycle_start_utc', true);
SELECT set_config('landsraad_term_length.cycle_days', :'cycle_days', true);

DO $$
DECLARE
  v_term_days integer := current_setting('landsraad_term_length.days')::integer;
  v_align_to_coriolis boolean := current_setting('landsraad_term_length.align_to_coriolis')::boolean;
  v_cycle_days integer := current_setting('landsraad_term_length.cycle_days')::integer;
  rec record;
BEGIN
  IF v_term_days < 1 THEN
    RAISE EXCEPTION 'DUNE_LANDSRAAD_TERM_LENGTH_DAYS must be at least 1: %', v_term_days;
  END IF;
  IF v_cycle_days < 1 THEN
    RAISE EXCEPTION 'Coriolis cycle days must be at least 1: %', v_cycle_days;
  END IF;

  CREATE TABLE IF NOT EXISTS dune.landsraad_term_length_tuning (
    id boolean PRIMARY KEY DEFAULT TRUE CHECK (id),
    term_days integer NOT NULL CHECK (term_days >= 1),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
  );

  INSERT INTO dune.landsraad_term_length_tuning (id, term_days, updated_at)
  VALUES (TRUE, v_term_days, now())
  ON CONFLICT (id)
  DO UPDATE SET term_days = EXCLUDED.term_days,
                updated_at = now();

  CREATE TABLE IF NOT EXISTS dune.landsraad_term_length_tuning_audit (
    id bigserial PRIMARY KEY,
    term_id bigint,
    start_time timestamp with time zone,
    previous_end_time timestamp with time zone,
    desired_end_time timestamp with time zone,
    term_days integer NOT NULL CHECK (term_days >= 1),
    changed boolean NOT NULL,
    applied_at timestamp with time zone NOT NULL DEFAULT now()
  );
  ALTER TABLE dune.landsraad_term_length_tuning_audit
    ADD COLUMN IF NOT EXISTS raw_desired_end_time timestamp with time zone,
    ADD COLUMN IF NOT EXISTS alignment_mode text,
    ADD COLUMN IF NOT EXISTS cycle_start timestamp with time zone,
    ADD COLUMN IF NOT EXISTS cycle_days integer;

  WITH settings AS (
    SELECT v_align_to_coriolis AS align_to_coriolis,
           current_setting('landsraad_term_length.cycle_start_utc')::timestamptz AS cycle_start,
           make_interval(days => v_cycle_days) AS cycle_duration
  ),
  current_term AS (
    SELECT term_id,
           start_time,
           end_time,
           COALESCE(test_term, FALSE) AS test_term,
           start_time + make_interval(days => v_term_days) AS raw_desired_end_time
      FROM dune.landsraad_decree_term
     WHERE now() >= start_time
       AND now() < end_time
     ORDER BY term_id DESC
     LIMIT 1
  )
  SELECT current_term.term_id,
         current_term.start_time,
         current_term.end_time,
         current_term.test_term,
         current_term.raw_desired_end_time,
         CASE
           WHEN settings.align_to_coriolis THEN
             settings.cycle_start
             + (
                 CEIL(
                   EXTRACT(EPOCH FROM (current_term.raw_desired_end_time - settings.cycle_start))
                   / EXTRACT(EPOCH FROM settings.cycle_duration)
                 ) * settings.cycle_duration
               )
           ELSE current_term.raw_desired_end_time
         END AS desired_end_time,
         CASE
           WHEN settings.align_to_coriolis THEN 'coriolis-boundary'
           ELSE 'unaligned'
         END AS alignment_mode,
         settings.cycle_start,
         v_cycle_days AS cycle_days
    INTO rec
    FROM current_term, settings;

  IF NOT FOUND THEN
    RAISE NOTICE 'no active Landsraad term found; nothing to tune';
    RETURN;
  END IF;

  IF rec.end_time <> rec.desired_end_time THEN
    PERFORM dune.landsraad_change_term_end_time(rec.term_id, rec.desired_end_time::timestamp, rec.test_term);
    INSERT INTO dune.landsraad_term_length_tuning_audit (
      term_id,
      start_time,
      previous_end_time,
      desired_end_time,
      term_days,
      changed,
      applied_at,
      raw_desired_end_time,
      alignment_mode,
      cycle_start,
      cycle_days
    )
    VALUES (
      rec.term_id,
      rec.start_time,
      rec.end_time,
      rec.desired_end_time,
      v_term_days,
      TRUE,
      now(),
      rec.raw_desired_end_time,
      rec.alignment_mode,
      rec.cycle_start,
      rec.cycle_days
    );
  ELSE
    INSERT INTO dune.landsraad_term_length_tuning_audit (
      term_id,
      start_time,
      previous_end_time,
      desired_end_time,
      term_days,
      changed,
      applied_at,
      raw_desired_end_time,
      alignment_mode,
      cycle_start,
      cycle_days
    )
    VALUES (
      rec.term_id,
      rec.start_time,
      rec.end_time,
      rec.desired_end_time,
      v_term_days,
      FALSE,
      now(),
      rec.raw_desired_end_time,
      rec.alignment_mode,
      rec.cycle_start,
      rec.cycle_days
    );
  END IF;
END $$;

\echo current_landsraad_term_after
WITH settings AS (
  SELECT current_setting('landsraad_term_length.align_to_coriolis')::boolean AS align_to_coriolis,
         current_setting('landsraad_term_length.cycle_start_utc')::timestamptz AS cycle_start,
         make_interval(days => current_setting('landsraad_term_length.cycle_days')::integer) AS cycle_duration
),
current_term AS (
  SELECT term_id,
         start_time,
         end_time,
         COALESCE(test_term, FALSE) AS test_term,
         start_time + make_interval(days => current_setting('landsraad_term_length.days')::integer) AS raw_desired_end_time
    FROM dune.landsraad_decree_term
   WHERE now() >= start_time
     AND now() < end_time
   ORDER BY term_id DESC
   LIMIT 1
),
planned AS (
  SELECT current_term.*,
         CASE
           WHEN settings.align_to_coriolis THEN
             settings.cycle_start
             + (
                 CEIL(
                   EXTRACT(EPOCH FROM (current_term.raw_desired_end_time - settings.cycle_start))
                   / EXTRACT(EPOCH FROM settings.cycle_duration)
                 ) * settings.cycle_duration
               )
           ELSE current_term.raw_desired_end_time
         END AS desired_end_time,
         CASE
           WHEN settings.align_to_coriolis THEN 'coriolis-boundary'
           ELSE 'unaligned'
         END AS alignment_mode
    FROM current_term, settings
)
SELECT term_id,
       start_time,
       end_time,
       raw_desired_end_time,
       desired_end_time,
       end_time - start_time AS current_duration,
       alignment_mode,
       test_term
  FROM planned;

COMMIT;
SQL
