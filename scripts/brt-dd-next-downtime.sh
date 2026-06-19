#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/brt-dd-next-downtime.sh COMMAND [ENV_FILE]

Commands:
  stage          Mark the BRT/DD config candidate pending for next downtime.
  apply-pending  Called by restart-post-start-health.sh after maintenance start.
  status         Print pending/applied marker state and current config status.

The stage command refuses unless hostname is kspls0. apply-pending does not
restart services; it only verifies the already-recreated Deep Desert container.
USAGE
}

cmd="${1:-}"
env_file="${2:-${ENV_FILE:-.env}}"
runtime="${CONTAINER_RUNTIME:-docker}"
service="${DUNE_BRT_DD_LIVE_SERVICE:-deep-desert}"
partition_id="${DUNE_BRT_DD_LIVE_PARTITION_ID:-8}"
required_host="${DUNE_BRT_DD_LIVE_HOST:-kspls0}"
timeout="${DUNE_BRT_DD_NEXT_DOWNTIME_VERIFY_TIMEOUT_SECONDS:-420}"
interval="${DUNE_BRT_DD_NEXT_DOWNTIME_VERIFY_INTERVAL_SECONDS:-10}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
marker_dir="${DUNE_BRT_DD_NEXT_DOWNTIME_MARKER_DIR:-$repo_root/backups/operations}"
pending_marker="$marker_dir/brt-dd-deep-desert.pending"
done_glob="$marker_dir/brt-dd-deep-desert.applied."*
target_config="config/UserGame.deep-desert-coriolis.ini"
copied_config="/home/dune/server/DuneSandbox/Saved/UserSettings/UserGame.ini"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"

required_config_patterns=(
  'm_MaxLandclaimSegmentsPerMap=.*DeepDesert'
  'm_MaxLandclaimSegmentsPerMap=.*DeepDesert_1'
  'm_BaseBackupToolMapRestriction=.*DeepDesert'
  'm_BaseBackupToolMapRestriction=.*DeepDesert_1'
)

dd_brt_bypass_patterns=(
  'm_bBuildingRestrictionLimitsEnabled=False'
)

required_brt_patch_site='can-use-region-fail-join'

dd1_no_shift_patterns=(
  'm_ShiftingSands=False'
  'm_bCoriolisAutoSpawnEnabled=False'
  'm_bCoriolisDoesDamage=False'
  'm_bCoriolisTriggerShiftingSands=False'
  'm_CoriolisLightDamage=0.000000'
  'm_CoriolisHeavyDamage=0.000000'
  'm_CycleDurationInDays=7'
  'm_bShouldRestartServerOnCycleEnd=False'
  'm_bIsDbWipeEnabled=False'
)

if [[ -z "$cmd" || "$cmd" == "-h" || "$cmd" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi

host_name() {
  hostname 2>/dev/null || true
}

host_short() {
  hostname -s 2>/dev/null || host_name
}

host_matches_required() {
  local actual="$1"
  [[ "$actual" == "$required_host" || "$actual" == "$required_host."* ]]
}

assert_live_host_for_staging() {
  local actual short
  actual="$(host_name)"
  short="$(host_short)"
  if ! host_matches_required "$actual" && ! host_matches_required "$short"; then
    printf 'refusing next-downtime staging: hostname is %s, required %s\n' "${actual:-unknown}" "$required_host" >&2
    exit 1
  fi
}

compose_command() {
  local compose_files
  compose_files="$("$script_dir/compose-files.sh" "$env_file")"
  compose=("$runtime" compose)
  IFS=':' read -ra compose_file_array <<< "$compose_files"
  for compose_file in "${compose_file_array[@]}"; do
    compose+=(-f "$compose_file")
  done
  compose+=(--env-file "$env_file")
}

check_rendered_patterns() {
  local file="$1"
  local rendered="$2"
  local pattern
  shift 2
  for pattern in "$@"; do
    if ! grep -Eq "$pattern" <<<"$rendered"; then
      printf 'missing required config pattern in %s: %s\n' "$file" "$pattern" >&2
      return 1
    fi
  done
}

check_dd1_no_shift_config() {
  local file="$1"
  local rendered
  if [[ ! -f "$file" ]]; then
    printf 'missing DD#1 no-shift config file: %s\n' "$file" >&2
    return 1
  fi
  rendered="$(cat "$file")"
  check_rendered_patterns "$file" "$rendered" "${required_config_patterns[@]}" "${dd_brt_bypass_patterns[@]}" "${dd1_no_shift_patterns[@]}"
}

check_brt_patch_site_config() {
  local rendered service_block site_line
  compose_command
  rendered="$("${compose[@]}" config 2>/dev/null)"
  service_block="$(awk -v service="$service" '
    $0 ~ "^  " service ":" { in_service = 1; print; next }
    in_service && $0 ~ "^  [A-Za-z0-9_-]+:" { in_service = 0 }
    in_service { print }
  ' <<<"$rendered")"
  site_line="$(grep -E 'DUNE_BRT_DD_NARROW_TOOL_STATE_PATCH_SITES:' <<<"$service_block" || true)"
  if [[ -z "$site_line" || "$site_line" != *"$required_brt_patch_site"* ]]; then
    printf 'missing required BRT/DD runtime patch site for %s: %s\n' "$service" "$required_brt_patch_site" >&2
    return 1
  fi
  printf 'rendered %s BRT/DD runtime patch sites include %s\n' "$service" "$required_brt_patch_site"
}

check_repo_config() {
  local file rendered
  for file in config/UserGame.ini config/UserGame.deep-desert-coriolis.ini config/UserGame.deep-desert-pvp.ini; do
    if [[ ! -f "$file" ]]; then
      printf 'missing config file: %s\n' "$file" >&2
      return 1
    fi
    rendered="$(cat "$file")"
    check_rendered_patterns "$file" "$rendered" "${required_config_patterns[@]}"
  done
  for file in config/UserGame.deep-desert-coriolis.ini config/UserGame.deep-desert-pvp.ini; do
    rendered="$(cat "$file")"
    check_rendered_patterns "$file" "$rendered" "${dd_brt_bypass_patterns[@]}"
  done
  check_dd1_no_shift_config "$target_config"
  check_brt_patch_site_config
  printf 'repo configs contain DeepDesert landclaim and BRT map restriction entries plus DD#1 no-shift/no-wipe guardrails\n'
}

container_id() {
  "${compose[@]}" ps -q "$service" 2>/dev/null || true
}

postgres_id() {
  "${compose[@]}" ps -q postgres 2>/dev/null || true
}

deep_desert_ready() {
  local id row rendered pattern
  id="$(container_id)"
  [[ -n "$id" ]] || return 1
  [[ "$("$runtime" inspect -f '{{.State.Running}}' "$id" 2>/dev/null || true)" == "true" ]] || return 1

  rendered="$("$runtime" exec "$id" sh -lc "test -f '$copied_config' && cat '$copied_config'" 2>/dev/null || true)"
  [[ -n "$rendered" ]] || return 1
  check_rendered_patterns "$copied_config" "$rendered" "${required_config_patterns[@]}" "${dd_brt_bypass_patterns[@]}" "${dd1_no_shift_patterns[@]}" || return 1

  if [[ -n "$(postgres_id)" ]]; then
    row="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "
      select wp.partition_id || '|' || wp.map || '|' || coalesce(fs.ready::text, '') || '|' || coalesce(fs.alive::text, '')
      from dune.world_partition wp
      left join dune.farm_state fs on fs.server_id = wp.server_id
      where wp.partition_id = ${partition_id};
    " 2>/dev/null || true)"
    [[ "$row" == ${partition_id}\|DeepDesert_1\|true\|true ]] || return 1
  fi

  return 0
}

stage_pending() {
  assert_live_host_for_staging
  check_repo_config
  mkdir -p "$marker_dir"
  {
    printf 'staged_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'host=%s\n' "$(host_name)"
    printf 'env_file=%s\n' "$env_file"
    printf 'service=%s\n' "$service"
    printf 'partition_id=%s\n' "$partition_id"
    sha256sum config/UserGame.ini config/UserGame.deep-desert-coriolis.ini config/UserGame.deep-desert-pvp.ini
  } > "$pending_marker"
  printf 'pending_marker=%s\n' "$pending_marker"
}

apply_pending() {
  if [[ ! -f "$pending_marker" ]]; then
    printf 'brt_dd_next_downtime=pending_marker_absent\n'
    return 0
  fi

  check_repo_config
  compose_command

  deadline=$((SECONDS + timeout))
  while (( SECONDS <= deadline )); do
    if deep_desert_ready; then
      applied_marker="$marker_dir/brt-dd-deep-desert.applied.$(date -u +%Y%m%dT%H%M%SZ)"
      mv "$pending_marker" "$applied_marker"
      printf 'brt_dd_next_downtime=applied marker=%s\n' "$applied_marker"
      return 0
    fi
    sleep "$interval"
  done

  printf 'BRT/DD pending marker was present, but %s did not verify copied config and ready partition within %ss\n' "$service" "$timeout" >&2
  return 1
}

status_pending() {
  printf 'host=%s required_live_host=%s\n' "$(host_name)" "$required_host"
  if [[ -f "$pending_marker" ]]; then
    printf 'pending_marker=%s\n' "$pending_marker"
  else
    printf 'pending_marker=absent\n'
  fi
  # shellcheck disable=SC2086
  ls -1t $done_glob 2>/dev/null | head -5 || true
  check_repo_config || true
}

case "$cmd" in
  stage)
    stage_pending
    ;;
  apply-pending)
    apply_pending
    ;;
  status)
    status_pending
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
