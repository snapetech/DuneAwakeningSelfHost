#!/usr/bin/env bash
# Stage and run the UE4SS package runtime trace helper on a remote host.
#
# This keeps the live host dependency small and reversible: files are copied to
# a /tmp handoff directory, then the remote runner's host guard still decides
# whether preflight/arm/status may proceed.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
action="${1:-preflight}"
remote="${2:-kspls0}"
container="${3:-dune_server-deep-desert-1}"
trace_log="${4:-/tmp/ue4ss-package-runtime-trace-live.log}"

required_host="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST:-kspls0}"
stage_dir="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_STAGE_DIR:-/tmp/ue4ss-package-runtime-trace-handoff}"
partition_id="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PARTITION:-8}"
db="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_DB:-dune_sb_1_4_0_0}"
postgres_container="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_POSTGRES:-dune_server-postgres-1}"
allow_players="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS:-false}"
trace_anchor="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR:-LoadPackage,LoadObject}"
trace_seed_address="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS:-}"
trace_route_address="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS:-}"
trace_limit="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT:-2}"
trace_method_limit="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_LIMIT:-4}"
trace_signature_family="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY:-LoadPackage}"
trace_hit_index="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HIT_INDEX:-auto}"
external_plan="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN:-$repo_root/build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json}"
trace_plan_json="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON:-$repo_root/build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.json}"
trace_plan_md="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD:-$repo_root/build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.md}"
method_candidates="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES:-$repo_root/build/server-ue-package-loader-vtables.json}"
live_trace_runbook_json="${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON:-$repo_root/build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json}"

copy_files=(
  scripts/ue4ss-package-runtime-trace.sh
  scripts/plan-ue4ss-package-runtime-trace.py
  scripts/summarize-ue4ss-package-runtime-trace-evidence.py
  scripts/review-ue4ss-package-abi.py
  scripts/export-ue4ss-package-promotion-env.py
  scripts/summarize-ue4ss-package-promotion-dir.py
  scripts/plan-ue4ss-package-next-action.py
  scripts/verify-ue4ss-package-review-bundle.py
  scripts/verify-ue4ss-package-route-slot-recovery.py
  scripts/verify-ue4ss-package-live-stimulus-summary.py
  scripts/plan-ue4ss-canary-env.py
)

quote_cmd() {
  local quoted=()
  local arg
  for arg in "$@"; do
    printf -v arg '%q' "$arg"
    quoted+=("$arg")
  done
  printf '%s' "${quoted[*]}"
}

assert_single_line() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "ERROR: $name must be a non-empty single-line value." >&2
    exit 2
  fi
}

assert_inputs() {
  assert_single_line "remote" "$remote"
  assert_single_line "container" "$container"
  assert_single_line "trace_log" "$trace_log"
  assert_single_line "stage_dir" "$stage_dir"
  assert_single_line "partition_id" "$partition_id"
  assert_single_line "db" "$db"
  assert_single_line "postgres_container" "$postgres_container"
  assert_single_line "trace_anchor" "$trace_anchor"
  if [[ -n "$trace_route_address" ]]; then
    assert_single_line "trace_route_address" "$trace_route_address"
  fi
  assert_single_line "trace_limit" "$trace_limit"
  assert_single_line "trace_method_limit" "$trace_method_limit"
  assert_single_line "trace_signature_family" "$trace_signature_family"
  assert_single_line "trace_hit_index" "$trace_hit_index"
  assert_single_line "external_plan" "$external_plan"
  assert_single_line "trace_plan_json" "$trace_plan_json"
  assert_single_line "trace_plan_md" "$trace_plan_md"
  assert_single_line "method_candidates" "$method_candidates"
  assert_single_line "live_trace_runbook_json" "$live_trace_runbook_json"
  case "$action" in
    print|preflight|arm|status|stop) ;;
    *)
      echo "ERROR: unknown action: $action (use print|preflight|arm|status|stop)" >&2
      exit 2
      ;;
  esac
  if [[ "$action" != "stop" ]]; then
    [[ -f "$external_plan" ]] || { echo "ERROR: missing external plan: $external_plan" >&2; exit 1; }
    [[ -f "$trace_plan_json" ]] || { echo "ERROR: missing trace plan JSON: $trace_plan_json" >&2; exit 1; }
    [[ -f "$trace_plan_md" ]] || { echo "ERROR: missing trace plan markdown: $trace_plan_md" >&2; exit 1; }
    [[ -f "$method_candidates" ]] || { echo "ERROR: missing method candidates: $method_candidates" >&2; exit 1; }
    [[ -f "$live_trace_runbook_json" ]] || { echo "ERROR: missing live trace runbook: $live_trace_runbook_json" >&2; exit 1; }
    require_trace_log_matches_runbook
    require_cleanup_matches_runbook
  fi
  if [[ "$required_host" == "kspls0" && "$allow_players" == "true" ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=true is not allowed for live host kspls0." >&2
    exit 2
  fi
}

require_trace_log_matches_runbook() {
  local runbook_trace_log
  runbook_trace_log="$(
    python3 - "$live_trace_runbook_json" <<'PY'
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)
value = data.get("traceLog", "")
if isinstance(value, str):
    print(value)
PY
  )"
  if [[ -n "$runbook_trace_log" && "$runbook_trace_log" != "$trace_log" ]]; then
    echo "ERROR: trace_log must match live trace runbook traceLog: $runbook_trace_log" >&2
    exit 2
  fi
}

require_cleanup_matches_runbook() {
  local cleanup_identity
  cleanup_identity="$(
    python3 - "$live_trace_runbook_json" <<'PY'
import json
import shlex
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)
command = data.get("cleanupCommand", "")
if not isinstance(command, str) or not command:
    raise SystemExit(0)
try:
    parts = shlex.split(command)
except ValueError:
    print("INVALID")
    raise SystemExit(0)
try:
    wrapper_index = parts.index("scripts/ue4ss-package-remote-trace.sh")
except ValueError:
    print("INVALID")
    raise SystemExit(0)
tail = parts[wrapper_index + 1 :]
if len(tail) != 4:
    print("INVALID")
    raise SystemExit(0)
print("\t".join(tail))
PY
  )"
  if [[ -z "$cleanup_identity" ]]; then
    echo "ERROR: live trace runbook cleanupCommand must be a non-empty remote trace stop command." >&2
    exit 2
  fi
  if [[ "$cleanup_identity" == "INVALID" ]]; then
    echo "ERROR: live trace runbook cleanupCommand must parse as remote trace stop command." >&2
    exit 2
  fi
  local cleanup_action cleanup_remote cleanup_container cleanup_trace_log
  IFS=$'\t' read -r cleanup_action cleanup_remote cleanup_container cleanup_trace_log <<< "$cleanup_identity"
  if [[ "$cleanup_action" != "stop" || "$cleanup_remote" != "$remote" || "$cleanup_container" != "$container" || "$cleanup_trace_log" != "$trace_log" ]]; then
    echo "ERROR: live trace runbook cleanupCommand must match stop $remote $container $trace_log." >&2
    exit 2
  fi
}

remote_host() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$remote" 'hostname -s 2>/dev/null || hostname'
}

assert_remote_host() {
  local host
  host="$(remote_host)"
  echo "remote_host=$host"
  if [[ "$host" != "$required_host" && "${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
    echo "ERROR: refusing remote package trace on host '$host'; required '$required_host'." >&2
    exit 1
  fi
}

remote_connected_players() {
  ssh -o BatchMode=yes "$remote" "$(quote_cmd docker exec -i "$postgres_container" psql -U dune -d "$db" -qAt -v "pid=$partition_id")" <<'SQL'
select coalesce(fs.connected_players, 0)::int
from dune.world_partition wp
left join dune.farm_state fs on fs.server_id = wp.server_id
where wp.partition_id = :pid;
SQL
}

require_zero_players() {
  local phase="$1"
  local players
  players="$(remote_connected_players)"
  players="${players:-999}"
  export DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE="$phase"
  export DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PARTITION="$partition_id"
  export DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_CONNECTED_PLAYERS="$players"
  echo "player_guard_${phase}_partition=$partition_id"
  echo "player_guard_${phase}_connected_players=$players"
  if [[ "$allow_players" != "true" && "$players" != "0" ]]; then
    echo "ERROR: refusing remote package trace $phase: connected_players=$players partition=$partition_id" >&2
    exit 1
  fi
}

stage_remote_files() {
  local file
  ssh -o BatchMode=yes "$remote" "$(quote_cmd mkdir -p "$stage_dir/scripts" "$stage_dir/build/server-current-anchor-prep")"
  for file in "${copy_files[@]}"; do
    [[ -f "$repo_root/$file" ]] || { echo "ERROR: missing staged file: $repo_root/$file" >&2; exit 1; }
    ssh -o BatchMode=yes "$remote" "$(quote_cmd mkdir -p "$stage_dir/$(dirname "$file")")"
    scp -q "$repo_root/$file" "$remote:$stage_dir/$file"
  done
  stage_file_as "$external_plan" "build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json"
  stage_file_as "$trace_plan_json" "build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.json"
  stage_file_as "$trace_plan_md" "build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.md"
  stage_file_as "$method_candidates" "build/server-ue-package-loader-vtables.json"
  stage_file_as "$live_trace_runbook_json" "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"
  ssh -o BatchMode=yes "$remote" "$(quote_cmd chmod +x "$stage_dir/scripts/ue4ss-package-runtime-trace.sh")"
}

stage_remote_stop_file() {
  local file="scripts/ue4ss-package-runtime-trace.sh"
  [[ -f "$repo_root/$file" ]] || { echo "ERROR: missing staged file: $repo_root/$file" >&2; exit 1; }
  ssh -o BatchMode=yes "$remote" "$(quote_cmd mkdir -p "$stage_dir/scripts")"
  scp -q "$repo_root/$file" "$remote:$stage_dir/$file"
  ssh -o BatchMode=yes "$remote" "$(quote_cmd chmod +x "$stage_dir/scripts/ue4ss-package-runtime-trace.sh")"
}

stage_file_as() {
  local src="$1"
  local rel="$2"
  [[ -f "$src" ]] || { echo "ERROR: missing staged file: $src" >&2; exit 1; }
  ssh -o BatchMode=yes "$remote" "$(quote_cmd mkdir -p "$stage_dir/$(dirname "$rel")")"
  scp -q "$src" "$remote:$stage_dir/$rel"
}

remote_env=(
  "DUNE_UE4SS_PACKAGE_TRACE_HOST=$required_host"
  "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=$trace_anchor"
  "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=$trace_hit_index"
  "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=$trace_limit"
  "DUNE_UE4SS_PACKAGE_TRACE_METHOD_LIMIT=$trace_method_limit"
  "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=$trace_signature_family"
)
if [[ -n "$trace_seed_address" ]]; then
  remote_env+=("DUNE_UE4SS_PACKAGE_TRACE_SEED_ADDRESS=$trace_seed_address")
fi
if [[ -n "$trace_route_address" ]]; then
  remote_env+=("DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=$trace_route_address")
fi

remote_command() {
  local remote_external="$stage_dir/build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json"
  local remote_trace_plan_json="$stage_dir/build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.json"
  local remote_trace_plan_md="$stage_dir/build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.md"
  local remote_method_candidates="$stage_dir/build/server-ue-package-loader-vtables.json"
  local remote_live_trace_runbook_json="$stage_dir/build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"
	  local env_args=(
	    "${remote_env[@]}"
	    "DUNE_UE4SS_PACKAGE_TRACE_PLAN=$remote_external"
	    "DUNE_UE4SS_PACKAGE_TRACE_METHOD_CANDIDATES=$remote_method_candidates"
	    "DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON=$remote_trace_plan_json"
	    "DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD=$remote_trace_plan_md"
	    "DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON=$remote_live_trace_runbook_json"
	  )
	  if [[ -n "${DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE:-}" ]]; then
	    env_args+=(
	      "DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE=$DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE"
	      "DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PARTITION=$DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PARTITION"
	      "DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_CONNECTED_PLAYERS=$DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_CONNECTED_PLAYERS"
	    )
	  fi
	  quote_cmd env "${env_args[@]}" "$stage_dir/scripts/ue4ss-package-runtime-trace.sh" "$action" "$container" "$trace_log"
	}

assert_inputs
if [[ "$action" == "print" ]]; then
  echo "stage_dir=$stage_dir"
  echo "stage_command=$(quote_cmd "$0" preflight "$remote" "$container" "$trace_log")"
  action=preflight
  echo "remote_preflight=$(remote_command)"
  action=arm
  echo "remote_arm=$(remote_command)"
  action=status
  echo "remote_status=$(remote_command)"
  action=stop
  echo "remote_stop=$(remote_command)"
  exit 0
fi

assert_remote_host
if [[ "$action" == "preflight" || "$action" == "arm" || "$action" == "status" ]]; then
  require_zero_players "$action"
fi

if [[ "$action" == "stop" ]]; then
  stage_remote_stop_file
else
  stage_remote_files
fi
ssh -o BatchMode=yes "$remote" "$(remote_command)"
