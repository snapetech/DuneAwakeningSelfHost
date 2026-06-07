#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/validate-landsraad-term-coriolis-alignment.sh [ENV_FILE]

Validates that the active Landsraad term end_time lands on the configured
Coriolis cycle boundary. Landsraad period state is derived from Coriolis timing;
an active term ending hours before that boundary can leave the UI suspended even
while the DB term is otherwise valid.

Defaults:
  DUNE_LANDSRAAD_TERM_ALIGNMENT_TOLERANCE_SECONDS=300
  DUNE_LANDSRAAD_TERM_LENGTH_CORIOLIS_CONFIG=config/UserGame.ini
  DUNE_DATABASE=dune_sb_1_4_0_0
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-${ENV_FILE:-.env}}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
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

db="$(env_or_file DUNE_DATABASE dune_sb_1_4_0_0)"
container_runtime="$(env_or_file CONTAINER_RUNTIME docker)"
coriolis_config="$(env_or_file DUNE_LANDSRAAD_TERM_LENGTH_CORIOLIS_CONFIG config/UserGame.ini)"
tolerance_seconds="$(env_or_file DUNE_LANDSRAAD_TERM_ALIGNMENT_TOLERANCE_SECONDS 300)"

case "$tolerance_seconds" in
  ''|*[!0-9]*) printf 'DUNE_LANDSRAAD_TERM_ALIGNMENT_TOLERANCE_SECONDS must be a non-negative integer\n' >&2; exit 64 ;;
esac

if [[ ! -f "$coriolis_config" ]]; then
  printf 'missing Coriolis config for Landsraad term alignment guard: %s\n' "$coriolis_config" >&2
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

compose_files="$("$script_dir/compose-files.sh" "$env_file")"
compose=("$container_runtime" compose --env-file "$env_file")
IFS=':' read -ra files <<< "$compose_files"
for file in "${files[@]}"; do
  compose+=(-f "$file")
done

"${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off \
  -v "cycle_start_utc=$cycle_start_utc" \
  -v "cycle_days=$cycle_days" \
  -v "tolerance_seconds=$tolerance_seconds" <<'SQL'
WITH settings AS (
  SELECT :'cycle_start_utc'::timestamptz AS cycle_start,
         make_interval(days => :'cycle_days'::integer) AS cycle_duration,
         :'tolerance_seconds'::integer AS tolerance_seconds
),
active_term AS (
  SELECT term_id, start_time, end_time, COALESCE(test_term, FALSE) AS test_term
  FROM dune.landsraad_decree_term
  WHERE now() >= start_time
    AND now() < end_time
  ORDER BY term_id DESC
  LIMIT 1
),
calc AS (
  SELECT active_term.*,
         settings.cycle_start,
         settings.cycle_duration,
         settings.tolerance_seconds,
         settings.cycle_start
           + (
             ROUND(EXTRACT(EPOCH FROM (active_term.end_time - settings.cycle_start))
                   / EXTRACT(EPOCH FROM settings.cycle_duration))
             * settings.cycle_duration
           ) AS nearest_cycle_boundary
  FROM active_term, settings
),
verdict AS (
  SELECT *,
         ABS(EXTRACT(EPOCH FROM (end_time - nearest_cycle_boundary)))::integer AS seconds_from_boundary
  FROM calc
)
SELECT 'landsraad_term_coriolis_alignment' AS check_name,
       term_id,
       start_time,
       end_time,
       nearest_cycle_boundary,
       seconds_from_boundary,
       tolerance_seconds,
       CASE
         WHEN seconds_from_boundary <= tolerance_seconds THEN 'ok'
         ELSE 'fail'
       END AS verdict
FROM verdict;
SQL

verdict="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 -qAt \
  -v "cycle_start_utc=$cycle_start_utc" \
  -v "cycle_days=$cycle_days" \
  -v "tolerance_seconds=$tolerance_seconds" <<'SQL'
WITH settings AS (
  SELECT :'cycle_start_utc'::timestamptz AS cycle_start,
         make_interval(days => :'cycle_days'::integer) AS cycle_duration,
         :'tolerance_seconds'::integer AS tolerance_seconds
),
active_term AS (
  SELECT term_id, start_time, end_time
  FROM dune.landsraad_decree_term
  WHERE now() >= start_time
    AND now() < end_time
  ORDER BY term_id DESC
  LIMIT 1
),
calc AS (
  SELECT active_term.*,
         settings.tolerance_seconds,
         settings.cycle_start
           + (
             ROUND(EXTRACT(EPOCH FROM (active_term.end_time - settings.cycle_start))
                   / EXTRACT(EPOCH FROM settings.cycle_duration))
             * settings.cycle_duration
           ) AS nearest_cycle_boundary
  FROM active_term, settings
),
verdict AS (
  SELECT *,
         ABS(EXTRACT(EPOCH FROM (end_time - nearest_cycle_boundary)))::integer AS seconds_from_boundary
  FROM calc
)
SELECT CASE
         WHEN NOT EXISTS (SELECT 1 FROM active_term) THEN 'ok:no-active-term'
         WHEN EXISTS (SELECT 1 FROM verdict WHERE seconds_from_boundary <= tolerance_seconds) THEN 'ok:aligned'
         ELSE 'fail:misaligned'
       END;
SQL
)"

case "$verdict" in
  ok:*)
    printf 'Landsraad term Coriolis alignment guard OK: %s\n' "$verdict"
    ;;
  *)
    printf 'Landsraad term Coriolis alignment guard failed: %s\n' "$verdict" >&2
    exit 1
    ;;
esac
