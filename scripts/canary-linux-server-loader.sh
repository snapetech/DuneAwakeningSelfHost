#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/canary-linux-server-loader.sh [ENV_FILE]

Runs a single zero-player Linux server-loader canary on kspls0, defaulting to
testing-waterfat / partition 7. The script enables preload, restarts only the
canary service, captures the loader log, then always disables preload and
restarts the canary service clean.

Environment:
  DUNE_LINUX_SERVER_CANARY_SERVICE       default: testing-waterfat
  DUNE_LINUX_SERVER_CANARY_PARTITION     default: 7
  DUNE_LINUX_SERVER_CANARY_HOST          default: kspls0
  DUNE_LINUX_SERVER_CANARY_ALLOW_PLAYERS default: false
  DUNE_LINUX_SERVER_CANARY_LOG_PATH      default: .env DUNE_PROBE_LOADER_LOG
  DUNE_LINUX_SERVER_CANARY_EXTRA_ENV     optional KEY=VALUE lines to apply only during canary
  DUNE_LINUX_SERVER_CANARY_PREP_DIR      optional prepare-ue-anchor-canary.py output dir
  DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY default: false; run strict post-canary verifier
  DUNE_LINUX_SERVER_CANARY_PRELOAD       optional loader .so path to apply only during canary
  DUNE_LINUX_SERVER_CANARY_SKIP_BUILD    default: false
  DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY default: false; check host/env/player guard only
  DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS default: 10; seconds before copying loader log
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
service="${DUNE_LINUX_SERVER_CANARY_SERVICE:-testing-waterfat}"
partition_id="${DUNE_LINUX_SERVER_CANARY_PARTITION:-7}"
required_host="${DUNE_LINUX_SERVER_CANARY_HOST:-kspls0}"
allow_players="${DUNE_LINUX_SERVER_CANARY_ALLOW_PLAYERS:-false}"
canary_preload="${DUNE_LINUX_SERVER_CANARY_PRELOAD:-}"
prep_dir="${DUNE_LINUX_SERVER_CANARY_PREP_DIR:-}"
strict_verify="${DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY:-false}"
skip_build="${DUNE_LINUX_SERVER_CANARY_SKIP_BUILD:-false}"
preflight_only="${DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY:-false}"
capture_delay="${DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS:-10}"
runtime="${CONTAINER_RUNTIME:-docker}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

short_host="$(hostname -s 2>/dev/null || hostname)"
if [[ "$short_host" != "$required_host" ]]; then
  printf "refusing canary on host '%s'; required '%s'\n" "$short_host" "$required_host" >&2
  exit 1
fi
if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
export COMPOSE_FILES
compose=("$runtime" compose)
IFS=':' read -ra compose_files <<< "$COMPOSE_FILES"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

db="${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}"
db="${db:-dune_sb_1_4_0_0}"
loader_log="${DUNE_LINUX_SERVER_CANARY_LOG_PATH:-$(env_value DUNE_PROBE_LOADER_LOG)}"
loader_log="${loader_log:-/tmp/dune-server-probe-loader.log}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="backups/canary-linux-loader/$stamp"
extra_env_restore_file="$backup_dir/extra.env.before"

set_env_value() {
  local key="$1"
  local value="$2"
  KEY="$key" VALUE="$value" perl -0pi -e '
    BEGIN { $key = $ENV{"KEY"}; $value = $ENV{"VALUE"}; $quoted = quotemeta($key); }
    $matched = s/^$quoted=.*/$key=$value/m;
    $_ .= "\n$key=$value\n" unless $matched;
  ' "$env_file"
}

restore_env_value() {
  local key="$1"
  local marker="$2"
  if [[ "$marker" == "__DUNE_CANARY_UNSET__" ]]; then
    KEY="$key" perl -0pi -e '
      BEGIN { $quoted = quotemeta($ENV{"KEY"}); }
      s/^$quoted=.*\n?//m;
    ' "$env_file"
  else
    set_env_value "$key" "$marker"
  fi
}

apply_extra_env_file() {
  local path="$1"
  local label="$2"
  local line key value original
  if [[ -z "$path" ]]; then
    return 0
  fi
  if [[ ! -f "$path" ]]; then
    printf 'missing extra env file: %s\n' "$path" >&2
    exit 2
  fi
  cp -a "$path" "$backup_dir/$label"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    if [[ "$line" != *=* ]]; then
      printf 'invalid extra env line: %s\n' "$line" >&2
      exit 2
    fi
	    key="${line%%=*}"
	    value="${line#*=}"
	    if [[ ( "$value" == \'*\' && "$value" == *\' ) || ( "$value" == \"*\" && "$value" == *\" ) ]]; then
	      value="${value:1:${#value}-2}"
	    fi
	    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
	      printf 'invalid extra env key: %s\n' "$key" >&2
	      exit 2
    fi
    if ! grep -Eq "^${key}=" "$extra_env_restore_file" 2>/dev/null; then
      original="$(env_value "$key")"
      if [[ -z "$original" ]]; then
        original="__DUNE_CANARY_UNSET__"
      fi
      printf '%s=%s\n' "$key" "$original" >> "$extra_env_restore_file"
    fi
    set_env_value "$key" "$value"
  done < "$path"
}

apply_extra_env() {
  apply_extra_env_file "${DUNE_LINUX_SERVER_CANARY_EXTRA_ENV:-}" "extra.env"
}

prep_anchor_env_path() {
  if [[ -z "$prep_dir" ]]; then
    return 0
  fi
  printf '%s/ue-server-anchors.env\n' "$prep_dir"
}

prep_verify_script_path() {
  if [[ -z "$prep_dir" ]]; then
    return 0
  fi
  if [[ "$strict_verify" == "true" ]]; then
    printf '%s/post-canary-verify-strict.sh\n' "$prep_dir"
  else
    printf '%s/post-canary-verify.sh\n' "$prep_dir"
  fi
}

validate_prep_dir() {
  local anchor_env verify_script
  if [[ -z "$prep_dir" ]]; then
    return 0
  fi
  anchor_env="$(prep_anchor_env_path)"
  verify_script="$(prep_verify_script_path)"
  if [[ ! -d "$prep_dir" ]]; then
    printf 'missing prepared canary dir: %s\n' "$prep_dir" >&2
    exit 2
  fi
  if [[ ! -f "$anchor_env" ]]; then
    printf 'missing prepared canary anchor env: %s\n' "$anchor_env" >&2
    exit 2
  fi
  if [[ ! -x "$verify_script" ]]; then
    printf 'missing executable post-canary verifier: %s\n' "$verify_script" >&2
    exit 2
  fi
}

run_post_canary_verify() {
  local captured_log="$1"
  local verify_script verify_rc artifact name
  if [[ -z "$prep_dir" ]]; then
    return 0
  fi
  verify_script="$(prep_verify_script_path)"
  printf 'prepared_canary_dir=%s\n' "$prep_dir" | tee -a "$backup_dir/summary.txt"
  printf 'post_canary_verify_script=%s\n' "$verify_script" | tee -a "$backup_dir/summary.txt"
  set +e
  "$verify_script" "$captured_log" > "$backup_dir/post-canary-verify.log" 2>&1
  verify_rc=$?
  set -e
  printf 'post_canary_verify_rc=%s\n' "$verify_rc" | tee -a "$backup_dir/summary.txt"
  for name in \
    ue4ss-readiness.json \
    object-discovery-coverage.json \
    post-canary-summary.md \
    ue4ss-port-gaps.json \
    ue4ss-port-gaps.md; do
    artifact="$prep_dir/$name"
    if [[ -f "$artifact" ]]; then
      cp -a "$artifact" "$backup_dir/$name"
    fi
  done
  return 0
}

restore_extra_env() {
  local line key value
  if [[ ! -f "$extra_env_restore_file" ]]; then
    return 0
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    restore_env_value "$key" "$value"
  done < "$extra_env_restore_file"
}

container_preload_path() {
  local path="$1"
  if [[ "$path" == "$repo_root/"* ]]; then
    printf '/workspace/%s\n' "${path#"$repo_root/"}"
  else
    printf '%s\n' "$path"
  fi
}

original_preload_enabled="$(env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD)"
original_preload_enabled="${original_preload_enabled:-__DUNE_CANARY_UNSET__}"
original_preload_partitions="$(env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS)"
original_preload_partitions="${original_preload_partitions:-__DUNE_CANARY_UNSET__}"
original_preload_path="$(env_value DUNE_LINUX_SERVER_PRELOAD)"
original_preload_path="${original_preload_path:-__DUNE_CANARY_UNSET__}"
original_loader_log="$(env_value DUNE_PROBE_LOADER_LOG)"
original_loader_log="${original_loader_log:-__DUNE_CANARY_UNSET__}"

current_connected_players() {
  local value
  value="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -qAt -v pid="$partition_id" <<'SQL'
select coalesce(fs.connected_players, 0)::int
from dune.world_partition wp
left join dune.farm_state fs on fs.server_id = wp.server_id
where wp.partition_id = :pid;
SQL
)"
  printf '%s\n' "${value:-999}"
}

require_zero_players() {
  local phase="$1"
  local value
  value="$(current_connected_players)"
  printf 'player_guard_%s_connected_players=%s\n' "$phase" "$value" | tee -a "$backup_dir/summary.txt"
  if [[ "$allow_players" != "true" && "$value" != "0" ]]; then
    printf 'refusing canary %s: connected_players=%s\n' "$phase" "$value" >&2
    return 1
  fi
  return 0
}

players="$(current_connected_players)"
players="${players:-999}"
validate_prep_dir
if [[ "$preflight_only" == "true" ]]; then
  printf 'canary=%s service=%s partition=%s connected_players=%s\n' "$stamp" "$service" "$partition_id" "$players"
  if [[ -n "$prep_dir" ]]; then
    printf 'prepared_canary_dir=%s\n' "$prep_dir"
    printf 'prepared_canary_anchor_env=%s\n' "$(prep_anchor_env_path)"
    printf 'post_canary_verify_script=%s\n' "$(prep_verify_script_path)"
  fi
  if [[ "$allow_players" != "true" && "$players" != "0" ]]; then
    printf 'refusing canary: connected_players=%s\n' "$players" >&2
    exit 1
  fi
  printf 'preflight_only=true\n'
  printf 'preflight_ok=true\n'
  exit 0
fi

mkdir -p "$backup_dir"
cp -a "$env_file" "$backup_dir/env.before"
printf 'canary=%s service=%s partition=%s connected_players=%s\n' "$stamp" "$service" "$partition_id" "$players" | tee "$backup_dir/summary.txt"
require_zero_players preflight

restart_canary() {
  DUNE_RESTART_CHECK_STEAM_UPDATE=false DUNE_RESTART_SERVICES="$service" ./scripts/restart-target.sh linux-loader-canary
}

restart_canary_if_zero_players() {
  local phase="$1"
  if require_zero_players "$phase"; then
    restart_canary
  else
    printf 'restart_skipped_%s_due_players=true\n' "$phase" | tee -a "$backup_dir/summary.txt"
    return 1
  fi
}

cleanup_needed=false
cleanup() {
  local rc=$?
  if [[ "$cleanup_needed" == "true" ]]; then
    set +e
    restore_extra_env
    restore_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD "$original_preload_enabled"
    restore_env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS "$original_preload_partitions"
    restore_env_value DUNE_LINUX_SERVER_PRELOAD "$original_preload_path"
    restore_env_value DUNE_PROBE_LOADER_LOG "$original_loader_log"
    cp -a "$env_file" "$backup_dir/env.after-cleanup"
    restart_canary_if_zero_players cleanup >> "$backup_dir/cleanup.log" 2>&1
    printf 'cleanup_rc=%s\n' "$?" >> "$backup_dir/summary.txt"
    set -e
  fi
  exit "$rc"
}
trap cleanup EXIT

if [[ "$skip_build" == "true" ]]; then
  printf 'build_skipped=true\n' > "$backup_dir/build.log"
else
  "$script_dir/build-linux-server-loader.sh" > "$backup_dir/build.log"
fi
set_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD true
set_env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS "$partition_id"
set_env_value DUNE_PROBE_LOADER_LOG "$loader_log"
if [[ -n "$canary_preload" ]]; then
  set_env_value DUNE_LINUX_SERVER_PRELOAD "$(container_preload_path "$canary_preload")"
fi
if [[ -n "$prep_dir" ]]; then
  apply_extra_env_file "$(prep_anchor_env_path)" "prepared-canary.env"
fi
apply_extra_env
cleanup_needed=true
cp -a "$env_file" "$backup_dir/env.preload"
restart_canary_if_zero_players preload | tee "$backup_dir/preload-restart.log"

case "$capture_delay" in
  ''|*[!0-9]*)
    printf 'invalid capture delay seconds: %s\n' "$capture_delay" >&2
    exit 2
    ;;
esac

cid="$("${compose[@]}" ps -q "$service")"
if [[ -z "$cid" ]]; then
  fallback_container="dune_server-${service}-1"
  if "$runtime" inspect "$fallback_container" >/dev/null 2>&1; then
    cid="$fallback_container"
    printf 'preload_container_fallback=%s\n' "$fallback_container" | tee -a "$backup_dir/summary.txt"
  fi
fi
printf 'preload_container=%s\n' "$cid" | tee -a "$backup_dir/summary.txt"
printf 'capture_delay_seconds=%s\n' "$capture_delay" | tee -a "$backup_dir/summary.txt"
sleep "$capture_delay"
if [[ -n "$cid" ]] && "$runtime" cp "$cid:$loader_log" "$backup_dir/$(basename "$loader_log")"; then
  captured_log="$backup_dir/$(basename "$loader_log")"
  "$script_dir/summarize-linux-loader-scan.py" "$captured_log" > "$backup_dir/$(basename "$loader_log").summary.txt" || true
  if [[ -x "$script_dir/ue4ss-port-readiness.py" ]]; then
    "$script_dir/ue4ss-port-readiness.py" --server-log "$captured_log" > "$backup_dir/ue4ss-readiness.md" || true
    "$script_dir/ue4ss-port-readiness.py" --server-log "$captured_log" --format json > "$backup_dir/ue4ss-readiness.json" || true
  fi
  run_post_canary_verify "$captured_log"
else
  printf 'WARN: loader log not found in canary container: %s\n' "$loader_log" | tee -a "$backup_dir/summary.txt"
fi

restore_extra_env
restore_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD "$original_preload_enabled"
restore_env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS "$original_preload_partitions"
restore_env_value DUNE_LINUX_SERVER_PRELOAD "$original_preload_path"
restore_env_value DUNE_PROBE_LOADER_LOG "$original_loader_log"
cp -a "$env_file" "$backup_dir/env.after"
restart_canary_if_zero_players cleanup | tee "$backup_dir/cleanup-restart.log"
cleanup_needed=false
"$script_dir/watch-maps.sh" "$env_file" --status > "$backup_dir/watch-status.after.txt"
printf 'backup_dir=%s\n' "$backup_dir" | tee -a "$backup_dir/summary.txt"
