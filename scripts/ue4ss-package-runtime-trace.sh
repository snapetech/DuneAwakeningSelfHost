#!/usr/bin/env bash
# Guarded runtime trace runner for the remaining UE4SS Linux package-loader gap.
#
# This attaches gdb read-watchpoints to current-build package string seeds. A hit
# is only evidence for promotion after the captured call frame is reviewed.
#
# Usage:
#   scripts/ue4ss-package-runtime-trace.sh preflight [CONTAINER] [TRACE_LOG]
#   scripts/ue4ss-package-runtime-trace.sh arm       [CONTAINER] [TRACE_LOG]
#   scripts/ue4ss-package-runtime-trace.sh stop      [CONTAINER]
#   scripts/ue4ss-package-runtime-trace.sh status    [CONTAINER]
#
# Env:
#   DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0       host guard for Docker/container traces
#                                              explicit PID traces default to the current host
#   DUNE_UE4SS_PACKAGE_TRACE_ALLOW_ANY_HOST=1    allow lab/off-host research
#   DUNE_UE4SS_PACKAGE_TRACE_PLAN=...            external-symbol plan JSON
#   DUNE_UE4SS_PACKAGE_TRACE_PID=...             explicit target PID for non-Docker targets
#   DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN=... docker-top awk process regex
#   DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject
#   DUNE_UE4SS_PACKAGE_TRACE_SEED_ADDRESS=0x814c33,0x815640
#   DUNE_UE4SS_PACKAGE_TRACE_LIMIT=1
#   DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage
#   DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto
#   DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON=/tmp/ue4ss-package-runtime-trace-plan.json
#   DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD=/tmp/ue4ss-package-runtime-trace-plan.md
#   DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_TARGET_IMAGE=1
#   DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_ABI=1
#   DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_CLASS_ROOT=1
#   DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_TCHAR=1
#   DUNE_UE4SS_PACKAGE_TRACE_TCHAR_UNIT_BYTES=2
#   DUNE_UE4SS_PACKAGE_TRACE_ALLOW_NATIVE_INVOKE=1
#   DUNE_UE4SS_PACKAGE_TRACE_FINAL_NATIVE_CALL=1
#   DUNE_UE4SS_PACKAGE_TRACE_PROMOTION_JSON=/tmp/ue4ss-package-promotion-env.json
#   DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_DIR=/tmp/ue4ss-package-family-reviews
#   DUNE_UE4SS_PACKAGE_TRACE_CANARY_SERVER_LOG=/tmp/dune-server-probe-loader.log
#   DUNE_UE4SS_PACKAGE_TRACE_NEXT_CANARY_JSON=/tmp/ue4ss-package-next-canary.json
#   DUNE_UE4SS_PACKAGE_TRACE_NEXT_CANARY_ENV=/tmp/ue4ss-package-next-canary.env
#   DUNE_UE4SS_PACKAGE_TRACE_NEXT_ACTION_JSON=/tmp/ue4ss-package-next-action.json
#   DUNE_UE4SS_PACKAGE_TRACE_NEXT_ACTION_MD=/tmp/ue4ss-package-next-action.md
#   DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON=... package stimulus trace runbook for next-action replay
#   DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_DIR=/tmp/ue4ss-package-review-bundles

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
action="${1:-arm}"
container="${2:-dune_server-deep-desert-1}"
container_was_set=0
if [[ "${2+x}" == x ]]; then
  container_was_set=1
fi
required_host="${DUNE_UE4SS_PACKAGE_TRACE_HOST:-kspls0}"
required_host_was_set=0
if [[ "${DUNE_UE4SS_PACKAGE_TRACE_HOST+x}" == x ]]; then
  required_host_was_set=1
fi
process_pattern="${DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN:-DuneSandboxServer-Linux-Shipping}"
explicit_pid="${DUNE_UE4SS_PACKAGE_TRACE_PID:-}"
if [[ -n "$explicit_pid" && "$container_was_set" != "1" ]]; then
  container="pid-$explicit_pid"
fi
external_plan="${DUNE_UE4SS_PACKAGE_TRACE_PLAN:-$repo_root/build/server-ue4ss-package-external-symbol-plan.json}"
limit="${DUNE_UE4SS_PACKAGE_TRACE_LIMIT:-1}"
anchor="${DUNE_UE4SS_PACKAGE_TRACE_ANCHOR:-LoadPackage,LoadObject}"
seed_address="${DUNE_UE4SS_PACKAGE_TRACE_SEED_ADDRESS:-}"
route_address="${DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS:-}"
signature_family="${DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY:-LoadPackage}"
hit_index="${DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX:-auto}"
gdb_cmd="${DUNE_UE4SS_PACKAGE_TRACE_GDB:-/tmp/ue4ss-package-runtime-trace.gdb}"
gdb_out="${DUNE_UE4SS_PACKAGE_TRACE_GDB_OUT:-/tmp/ue4ss-package-runtime-trace-gdb.out}"
gdb_pid_file="${DUNE_UE4SS_PACKAGE_TRACE_GDB_PID:-/tmp/ue4ss-package-runtime-trace-gdb.pid}"
method_candidates="${DUNE_UE4SS_PACKAGE_TRACE_METHOD_CANDIDATES:-$repo_root/build/server-ue-package-loader-vtables.json}"
method_limit="${DUNE_UE4SS_PACKAGE_TRACE_METHOD_LIMIT:-4}"
trace_plan_json="${DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON:-/tmp/ue4ss-package-runtime-trace-plan.json}"
trace_plan_md="${DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD:-/tmp/ue4ss-package-runtime-trace-plan.md}"
evidence_json="${DUNE_UE4SS_PACKAGE_TRACE_EVIDENCE_JSON:-/tmp/ue4ss-package-runtime-trace-evidence.json}"
evidence_md="${DUNE_UE4SS_PACKAGE_TRACE_EVIDENCE_MD:-/tmp/ue4ss-package-runtime-trace-evidence.md}"
abi_review_json="${DUNE_UE4SS_PACKAGE_TRACE_ABI_REVIEW_JSON:-/tmp/ue4ss-package-abi-review.json}"
abi_review_md="${DUNE_UE4SS_PACKAGE_TRACE_ABI_REVIEW_MD:-/tmp/ue4ss-package-abi-review.md}"
promotion_md="${DUNE_UE4SS_PACKAGE_TRACE_PROMOTION_MD:-/tmp/ue4ss-package-promotion-env.md}"
promotion_json="${DUNE_UE4SS_PACKAGE_TRACE_PROMOTION_JSON:-/tmp/ue4ss-package-promotion-env.json}"
all_family_dir="${DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_DIR:-/tmp/ue4ss-package-family-reviews}"
all_family_summary_md="${DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_SUMMARY_MD:-/tmp/ue4ss-package-family-reviews.md}"
all_family_summary_json="${DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_SUMMARY_JSON:-/tmp/ue4ss-package-family-reviews.json}"
canary_server_log="${DUNE_UE4SS_PACKAGE_TRACE_CANARY_SERVER_LOG:-/tmp/dune-server-probe-loader.log}"
next_canary_json="${DUNE_UE4SS_PACKAGE_TRACE_NEXT_CANARY_JSON:-/tmp/ue4ss-package-next-canary.json}"
next_canary_env="${DUNE_UE4SS_PACKAGE_TRACE_NEXT_CANARY_ENV:-/tmp/ue4ss-package-next-canary.env}"
next_action_json="${DUNE_UE4SS_PACKAGE_TRACE_NEXT_ACTION_JSON:-/tmp/ue4ss-package-next-action.json}"
next_action_md="${DUNE_UE4SS_PACKAGE_TRACE_NEXT_ACTION_MD:-/tmp/ue4ss-package-next-action.md}"
live_trace_runbook_json="${DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON:-$repo_root/build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json}"
review_bundle_root="${DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_DIR:-/tmp/ue4ss-package-review-bundles}"
review_bundle_verify_json="${DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_VERIFY_JSON:-/tmp/ue4ss-package-review-bundle-verification.json}"
review_bundle_verify_md="${DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_VERIFY_MD:-/tmp/ue4ss-package-review-bundle-verification.md}"
route_slot_recovery_verify_json="${DUNE_UE4SS_PACKAGE_TRACE_ROUTE_SLOT_RECOVERY_VERIFY_JSON:-/tmp/ue4ss-package-route-slot-recovery-verification.json}"
route_slot_recovery_verify_md="${DUNE_UE4SS_PACKAGE_TRACE_ROUTE_SLOT_RECOVERY_VERIFY_MD:-/tmp/ue4ss-package-route-slot-recovery-verification.md}"
default_log="/tmp/ue4ss-package-runtime-trace-live.log"

short_host() {
  hostname -s 2>/dev/null || hostname 2>/dev/null || true
}

assert_host() {
  local host
  local expected_host="$required_host"
  host="$(short_host)"
  if [[ -n "$explicit_pid" && "$required_host_was_set" != "1" ]]; then
    expected_host="$host"
  fi
  if [[ "$host" != "$expected_host" && "${DUNE_UE4SS_PACKAGE_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
    echo "ERROR: refusing package runtime trace on host '$host'; required '$expected_host'." >&2
    echo "       Set DUNE_UE4SS_PACKAGE_TRACE_ALLOW_ANY_HOST=1 only for lab/offline research." >&2
    exit 1
  fi
}

server_pid() {
  if [[ -n "$explicit_pid" ]]; then
    if [[ ! "$explicit_pid" =~ ^[0-9]+$ ]]; then
      echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_PID must be numeric, got '$explicit_pid'." >&2
      return 2
    fi
    if [[ ! -d "/proc/$explicit_pid" ]]; then
      echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_PID does not exist: $explicit_pid" >&2
      return 1
    fi
    printf '%s\n' "$explicit_pid"
    return 0
  fi
  docker top "$container" -eo pid,args 2>/dev/null \
    | awk -v pattern="$process_pattern" '$0 ~ pattern {print $1; exit}' \
    || true
}

docker_container_exists() {
  [[ -z "$explicit_pid" ]] || return 1
  docker inspect "$container" >/dev/null 2>&1
}

kill_existing_gdb() {
  local old_gdb
  if [[ ! -s "$gdb_pid_file" ]]; then
    return 0
  fi
  old_gdb="$(cat "$gdb_pid_file" 2>/dev/null || true)"
  if [[ "$old_gdb" =~ ^[0-9]+$ ]] && ps -p "$old_gdb" -o cmd= 2>/dev/null | grep -q 'gdb -q -p'; then
    echo "detaching previous package-trace gdb pid $old_gdb"
    sudo -n kill "$old_gdb" 2>/dev/null || kill "$old_gdb" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "$gdb_pid_file"
}

server_state() {
  local pid="$1"
  sudo -n awk '{print $3}' "/proc/$pid/stat" 2>/dev/null \
    || awk '{print $3}' "/proc/$pid/stat" 2>/dev/null \
    || echo '?'
}

assert_signature_family() {
  case "$signature_family" in
    StaticLoadObject|StaticLoadClass|LoadObject|LoadPackage|ResolveName)
      ;;
    *)
      echo "ERROR: unsupported DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY='$signature_family'." >&2
      echo "       Use StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or ResolveName." >&2
      exit 2
      ;;
  esac
}

assert_hit_index() {
  if [[ "$hit_index" != "auto" && ! "$hit_index" =~ ^[0-9]+$ ]]; then
    echo "ERROR: unsupported DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX='$hit_index'; use auto or a non-negative integer." >&2
    exit 2
  fi
}

assert_trace_limit() {
  if [[ ! "$limit" =~ ^[0-9]+$ || "$limit" == "0" ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_LIMIT must be a positive integer, got '$limit'." >&2
    exit 2
  fi
  if [[ ! "$method_limit" =~ ^[0-9]+$ ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_METHOD_LIMIT must be a non-negative integer, got '$method_limit'." >&2
    exit 2
  fi
}

assert_runtime_selector_args() {
  if [[ -z "$container" || "$container" == *$'\n'* || "$container" == *$'\r'* ]]; then
    echo "ERROR: package runtime trace container selector must be non-empty and single-line." >&2
    exit 2
  fi
  if [[ -z "$process_pattern" || "$process_pattern" == *$'\n'* || "$process_pattern" == *$'\r'* ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN must be non-empty and single-line." >&2
    exit 2
  fi
  if [[ -n "$explicit_pid" && ! "$explicit_pid" =~ ^[0-9]+$ ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_PID must be numeric, got '$explicit_pid'." >&2
    exit 2
  fi
}

assert_single_line_path() {
  local env_name="$1"
  local value="$2"
  if [[ -z "$value" || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "ERROR: $env_name must be a non-empty single-line path." >&2
    exit 2
  fi
}

assert_trace_output_paths() {
  local trace_log="${1:-$default_log}"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_PLAN" "$external_plan"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_GDB" "$gdb_cmd"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_GDB_OUT" "$gdb_out"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_GDB_PID" "$gdb_pid_file"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_METHOD_CANDIDATES" "$method_candidates"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_METHOD_LIMIT" "$method_limit"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON" "$trace_plan_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD" "$trace_plan_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_EVIDENCE_JSON" "$evidence_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_EVIDENCE_MD" "$evidence_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ABI_REVIEW_JSON" "$abi_review_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ABI_REVIEW_MD" "$abi_review_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_PROMOTION_MD" "$promotion_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_PROMOTION_JSON" "$promotion_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_DIR" "$all_family_dir"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_SUMMARY_MD" "$all_family_summary_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_SUMMARY_JSON" "$all_family_summary_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_CANARY_SERVER_LOG" "$canary_server_log"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_NEXT_CANARY_JSON" "$next_canary_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_NEXT_CANARY_ENV" "$next_canary_env"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_NEXT_ACTION_JSON" "$next_action_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_NEXT_ACTION_MD" "$next_action_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON" "$live_trace_runbook_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_DIR" "$review_bundle_root"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_VERIFY_JSON" "$review_bundle_verify_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_VERIFY_MD" "$review_bundle_verify_md"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_SLOT_RECOVERY_VERIFY_JSON" "$route_slot_recovery_verify_json"
  assert_single_line_path "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_SLOT_RECOVERY_VERIFY_MD" "$route_slot_recovery_verify_md"
  assert_single_line_path "TRACE_LOG" "$trace_log"
}

remove_generated_file() {
  local path="$1"
  [[ -n "$path" ]] || return 0
  rm -f "$path" 2>/dev/null || sudo -n rm -f "$path"
}

assert_anchor_args() {
  local raw="${anchor//,/ }"
  local item
  local count=0
  for item in $raw; do
    [[ -n "$item" ]] || continue
    case "$item" in
      StaticLoadObject|StaticLoadClass|LoadObject|LoadPackage|ResolveName)
        count=$((count + 1))
        ;;
      *)
        echo "ERROR: unsupported DUNE_UE4SS_PACKAGE_TRACE_ANCHOR='$item'." >&2
        echo "       Use StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or ResolveName." >&2
        exit 2
        ;;
    esac
  done
  if [[ "$count" -eq 0 ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_ANCHOR must include at least one package anchor." >&2
    echo "       Use StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or ResolveName." >&2
    exit 2
  fi
}

assert_promotion_review_args() {
  if [[ "${DUNE_UE4SS_PACKAGE_TRACE_FINAL_NATIVE_CALL:-0}" =~ ^(1|true|yes)$ ]] \
    && [[ ! "${DUNE_UE4SS_PACKAGE_TRACE_ALLOW_NATIVE_INVOKE:-0}" =~ ^(1|true|yes)$ ]]; then
    echo "ERROR: DUNE_UE4SS_PACKAGE_TRACE_FINAL_NATIVE_CALL requires DUNE_UE4SS_PACKAGE_TRACE_ALLOW_NATIVE_INVOKE=1." >&2
    exit 2
  fi
}

bool_arg() {
  local env_name="$1"
  local arg_name="$2"
  local value="${!env_name:-0}"
  if [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" ]]; then
    printf '%s\n' "$arg_name"
  fi
}

promotion_review_args() {
  bool_arg DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_TARGET_IMAGE --reviewed-target-image
  bool_arg DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_ABI --reviewed-abi
  bool_arg DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_CLASS_ROOT --reviewed-class-root
  bool_arg DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_TCHAR --reviewed-tchar
  if [[ -n "${DUNE_UE4SS_PACKAGE_TRACE_TCHAR_UNIT_BYTES:-}" ]]; then
    printf '%s\n' --tchar-unit-bytes
    printf '%s\n' "$DUNE_UE4SS_PACKAGE_TRACE_TCHAR_UNIT_BYTES"
  fi
  bool_arg DUNE_UE4SS_PACKAGE_TRACE_ALLOW_NATIVE_INVOKE --allow-native-invoke
  bool_arg DUNE_UE4SS_PACKAGE_TRACE_FINAL_NATIVE_CALL --final-native-call
}

anchor_args() {
  local raw="${anchor//,/ }"
  local item
  for item in $raw; do
    [[ -n "$item" ]] || continue
    printf '%s\n' --anchor
    printf '%s\n' "$item"
  done
}

seed_address_args() {
  local raw="${seed_address//,/ }"
  local item
  for item in $raw; do
    [[ -n "$item" ]] || continue
    if [[ ! "$item" =~ ^0x[0-9a-fA-F]+$ ]]; then
      echo "ERROR: unsupported DUNE_UE4SS_PACKAGE_TRACE_SEED_ADDRESS='$item'." >&2
      echo "       Use comma-separated hex image offsets from the package trace plan." >&2
      exit 2
    fi
    printf '%s\n' --seed-address
    printf '%s\n' "$item"
  done
}

route_address_args() {
  local raw="${route_address//,/ }"
  local item
  for item in $raw; do
    [[ -n "$item" ]] || continue
    if [[ ! "$item" =~ ^0x[0-9a-fA-F]+$ ]]; then
      echo "ERROR: unsupported DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS='$item'." >&2
      echo "       Use comma-separated hex image offsets from method-hit callerImageOffset rows." >&2
      exit 2
    fi
    printf '%s\n' --route-address
    printf '%s\n' "$item"
  done
}

quote_cmd() {
  local quoted=()
  local arg
  for arg in "$@"; do
    printf -v arg '%q' "$arg"
    quoted+=("$arg")
  done
  printf '%s' "${quoted[*]}"
}

refresh_trace_plan_outputs() {
  local runtime_pid="${1:-}"
  assert_anchor_args
  assert_trace_limit
  local trace_anchor_args=()
  while IFS= read -r arg; do
    trace_anchor_args+=("$arg")
  done < <(anchor_args)
  while IFS= read -r arg; do
    trace_anchor_args+=("$arg")
  done < <(seed_address_args)
  while IFS= read -r arg; do
    trace_anchor_args+=("$arg")
  done < <(route_address_args)
  local effective_limit="$limit"
  local anchor_count=$(( ${#trace_anchor_args[@]} / 2 ))
  if [[ -z "${DUNE_UE4SS_PACKAGE_TRACE_LIMIT:-}" && "$anchor_count" -gt 1 ]]; then
    effective_limit="$anchor_count"
  fi
  local trace_plan_runtime_args=()
  if [[ "$runtime_pid" =~ ^[0-9]+$ ]]; then
    trace_plan_runtime_args=(--pid "$runtime_pid")
  else
    trace_plan_runtime_args=(--base 0x100000)
  fi
  local tmp_json="${trace_plan_json}.tmp.$$"
  local tmp_md="${trace_plan_md}.tmp.$$"
  rm -f "$tmp_json" "$tmp_md"
  if ! "$repo_root/scripts/plan-ue4ss-package-runtime-trace.py" \
    --external-plan "$external_plan" \
    "${trace_plan_runtime_args[@]}" \
    "${trace_anchor_args[@]}" \
    --method-candidates "$method_candidates" \
    --method-limit "$method_limit" \
    --limit "$effective_limit" \
    --format json >"$tmp_json"; then
    rm -f "$tmp_json" "$tmp_md" "$trace_plan_json" "$trace_plan_md"
    echo "WARN: failed to refresh package runtime trace plan JSON; stale trace-plan outputs removed" >&2
    return 1
  fi
  if ! "$repo_root/scripts/plan-ue4ss-package-runtime-trace.py" \
    --external-plan "$external_plan" \
    "${trace_plan_runtime_args[@]}" \
    "${trace_anchor_args[@]}" \
    --method-candidates "$method_candidates" \
    --method-limit "$method_limit" \
    --limit "$effective_limit" \
    --format markdown >"$tmp_md"; then
    rm -f "$tmp_json" "$tmp_md" "$trace_plan_json" "$trace_plan_md"
    echo "WARN: failed to refresh package runtime trace plan markdown; stale trace-plan outputs removed" >&2
    return 1
  fi
  mv "$tmp_json" "$trace_plan_json"
  mv "$tmp_md" "$trace_plan_md"
}

require_trace_plan_ready() {
  local plan="$1"
  python3 - "$plan" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
plan = json.loads(path.read_text(encoding="utf-8"))
blockers = list(plan.get("blockers", []) or [])
if blockers:
    print("ERROR: package runtime trace plan is blocked:", file=sys.stderr)
    for blocker in blockers:
        print(f"  - {blocker}", file=sys.stderr)
    raise SystemExit(2)
if not plan.get("seeds"):
    print("ERROR: package runtime trace plan selected no seeds", file=sys.stderr)
    raise SystemExit(2)
PY
}

print_next_canary_preview() {
  local base_cmd=(
    "$repo_root/scripts/plan-ue4ss-canary-env.py"
    --platform server
    --server-log "$canary_server_log"
    --max-stage lua-dispatch
  )
  local package_args=()
  if [[ -s "$promotion_json" ]]; then
    package_args+=(--package-promotion-json "$promotion_json")
  fi
  if [[ -s "$all_family_summary_json" ]]; then
    package_args+=(--package-promotion-summary-json "$all_family_summary_json")
  elif [[ -d "$all_family_dir" ]]; then
    package_args+=(--package-promotion-dir "$all_family_dir")
  fi
  echo "--next-canary-preview--"
  echo "next_canary_json=$next_canary_json"
  echo "next_canary_env=$next_canary_env"
  if [[ "${#package_args[@]}" -eq 0 ]]; then
    echo "package_promotion_json=none"
  else
    local i
    for ((i = 0; i < ${#package_args[@]}; i += 2)); do
      echo "${package_args[$i]#--}=${package_args[$((i + 1))]}"
    done
  fi
  printf '%s >%s\n' "$(quote_cmd "${base_cmd[@]}" "${package_args[@]}" --format json)" "$(printf '%q' "$next_canary_json")"
  printf '%s >%s\n' "$(quote_cmd "${base_cmd[@]}" "${package_args[@]}" --format env)" "$(printf '%q' "$next_canary_env")"
}

write_next_action() {
  local trace_log_arg="${1:-$default_log}"
  local runtime_pid="${2:-}"
  local effective_target_pid="$explicit_pid"
  if [[ -z "$effective_target_pid" && "$runtime_pid" =~ ^[0-9]+$ ]]; then
    effective_target_pid="$runtime_pid"
  fi
  if [[ -f "$external_plan" ]]; then
    refresh_trace_plan_outputs "$runtime_pid" || true
  fi
  if [[ -x "$repo_root/scripts/plan-ue4ss-package-next-action.py" ]]; then
    local next_action_args=(
      --trace-plan-json "$trace_plan_json"
      --wrapper "$repo_root/scripts/ue4ss-package-runtime-trace.sh"
      --container "$container"
      --process-pattern "$process_pattern"
      --target-pid "$effective_target_pid"
      --trace-log "$trace_log_arg"
      --canary-log "$canary_server_log"
      --next-canary-json "$next_canary_json"
      --next-canary-env "$next_canary_env"
    )
    if [[ -s "$live_trace_runbook_json" ]]; then
      next_action_args+=(--live-trace-runbook-json "$live_trace_runbook_json")
    fi
    if [[ "$required_host_was_set" == "1" ]]; then
      next_action_args+=(--trace-host "$required_host")
    fi
    if [[ -s "$all_family_summary_json" ]]; then
      next_action_args=(--promotion-summary-json "$all_family_summary_json" "${next_action_args[@]}")
    elif [[ -s "$promotion_json" ]]; then
      next_action_args=(--promotion-json "$promotion_json" "${next_action_args[@]}")
    fi
    local tmp_next_action_json="${next_action_json}.tmp.$$"
    local tmp_next_action_md="${next_action_md}.tmp.$$"
    rm -f "$tmp_next_action_json" "$tmp_next_action_md"
    if ! "$repo_root/scripts/plan-ue4ss-package-next-action.py" "${next_action_args[@]}" --format json >"$tmp_next_action_json"; then
      rm -f "$tmp_next_action_json" "$tmp_next_action_md" "$next_action_json" "$next_action_md"
      echo "WARN: failed to write package next-action JSON; stale next-action outputs removed" >&2
      return 1
    fi
    if ! "$repo_root/scripts/plan-ue4ss-package-next-action.py" "${next_action_args[@]}" --format markdown >"$tmp_next_action_md"; then
      rm -f "$tmp_next_action_json" "$tmp_next_action_md" "$next_action_json" "$next_action_md"
      echo "WARN: failed to write package next-action markdown; stale next-action outputs removed" >&2
      return 1
    fi
    mv "$tmp_next_action_json" "$next_action_json"
    mv "$tmp_next_action_md" "$next_action_md"
    echo "next_action_json=$next_action_json"
    echo "next_action=$next_action_md"
    sed -n '1,80p' "$next_action_md" 2>/dev/null || true
  fi
}

write_route_slot_recovery_verification() {
  [[ -x "$repo_root/scripts/verify-ue4ss-package-route-slot-recovery.py" ]] || return 0
  [[ -s "$evidence_json" && -s "$next_action_json" ]] || return 0
  "$repo_root/scripts/verify-ue4ss-package-route-slot-recovery.py" \
    "$evidence_json" \
    --next-action-json "$next_action_json" \
    --format json >"$route_slot_recovery_verify_json" || true
  "$repo_root/scripts/verify-ue4ss-package-route-slot-recovery.py" \
    "$evidence_json" \
    --next-action-json "$next_action_json" \
    --format markdown >"$route_slot_recovery_verify_md" || true
  echo "route_slot_recovery_verify_json=$route_slot_recovery_verify_json"
  echo "route_slot_recovery_verify=$route_slot_recovery_verify_md"
  sed -n '1,60p' "$route_slot_recovery_verify_md" 2>/dev/null || true
}

write_bundle_image_manifest_fields() {
  local evidence="$1"
  [[ -s "$evidence" ]] || return 0
  python3 - "$evidence" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)

def file_sha256(candidate):
    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()

fields = {
    "sourceLogExists": data.get("sourceLogExists", ""),
    "sourceLogSha256": data.get("sourceLogSha256", ""),
    "sourceEvidenceJson": data.get("sourceEvidenceJson") or str(path),
    "sourceEvidenceJsonSha256": data.get("sourceEvidenceJsonSha256") or file_sha256(path),
    "evidencePid": data.get("pid", ""),
    "tracePidMatchesRequested": data.get("tracePidMatchesRequested", ""),
    "imageRangeSource": data.get("imageRangeSource", ""),
    "imageBase": data.get("imageBase", ""),
    "imageStart": data.get("imageStart", ""),
    "imageEnd": data.get("imageEnd", ""),
    "imagePath": data.get("imagePath", ""),
    "imagePerms": data.get("imagePerms", ""),
}
for key, value in fields.items():
    text = str(value if value is not None else "")
    print(f"{key}={text}")
PY
}

evidence_pid_field() {
  local evidence="$1"
  [[ -s "$evidence" ]] || return 0
  python3 - "$evidence" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)
pid = data.get("pid", "")
if isinstance(pid, int) and pid >= 0:
    print(pid)
elif isinstance(pid, str) and pid.isdecimal():
    print(pid)
PY
}

write_bundle_trace_plan_manifest_fields() {
  local plan="$1"
  [[ -s "$plan" ]] || return 0
  python3 - "$plan" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
except Exception:
    raise SystemExit(0)
print(f"sourceTracePlan={path}")
print(f"tracePlanSourceExternalPlan={data.get('sourceExternalPlan', '')}")
print(f"tracePlanPromotionAcceptanceSchema={data.get('sourcePromotionAcceptanceSchemaVersion', '')}")
print(f"tracePlanBase={data.get('base', '')}")
print(f"tracePlanExpectedBuildId={data.get('expectedBuildId', '')}")
print(f"tracePlanRuntimeBuildId={data.get('runtimeBuildId', '')}")
print(f"tracePlanSeedCount={data.get('seedCount', '')}")
seed_offsets = ",".join(
    f"{seed.get('name', '')}@{seed.get('address', '')}"
    for seed in data.get("seeds", []) or []
    if seed.get("name") and seed.get("address")
)
print(f"tracePlanSeedOffsets={seed_offsets}")
selected = ((data.get("seedSelection", {}) or {}).get("selectedByFamily", {}) or {})
selected_text = ",".join(
    f"{key}:{selected[key]}"
    for key in sorted(selected)
    if str(key) and selected.get(key, 0)
)
print(f"tracePlanSelectedByFamily={selected_text}")
print(f"tracePlanBlockerCount={len(data.get('blockers', []) or [])}")
recommended = data.get("recommendedTraceEnv", {}) or {}
print(f"tracePlanRecommendedAnchor={recommended.get('DUNE_UE4SS_PACKAGE_TRACE_ANCHOR', '')}")
print(f"tracePlanRecommendedLimit={recommended.get('DUNE_UE4SS_PACKAGE_TRACE_LIMIT', '')}")
print(f"tracePlanRecommendedSignatureFamily={recommended.get('DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY', '')}")
print(f"tracePlanRecommendedHitIndex={recommended.get('DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX', '')}")
PY
}

write_review_bundle() {
  local trace_log_arg="${1:-$default_log}"
  local stamp bundle manifest rel_path source target effective_trace_pid suffix
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$review_bundle_root"
  bundle="$review_bundle_root/$stamp"
  suffix=0
  while ! mkdir "$bundle" 2>/dev/null; do
    suffix=$((suffix + 1))
    bundle="$review_bundle_root/$stamp-$suffix"
  done
  manifest="$bundle/review-bundle-manifest.txt"
  effective_trace_pid="$explicit_pid"
  if [[ -z "$effective_trace_pid" ]]; then
    effective_trace_pid="$(evidence_pid_field "$evidence_json")"
  fi
  {
    echo "schema=dune-ue4ss-package-review-bundle/v1"
	    echo "createdUtc=$stamp"
	    echo "container=$container"
	    if [[ "$required_host_was_set" == "1" ]]; then
	      echo "traceHost=$required_host"
	    fi
	    if [[ -n "${DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE:-}" ]]; then
	      echo "playerGuardPhase=$DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE"
	      echo "playerGuardPartition=$DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PARTITION"
	      echo "playerGuardConnectedPlayers=$DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_CONNECTED_PLAYERS"
	    fi
	    echo "processPattern=$process_pattern"
	    echo "tracePid=$effective_trace_pid"
	    echo "signatureFamily=$signature_family"
	    echo "hitIndex=$hit_index"
	    echo "traceLog=$trace_log_arg"
	    echo "externalPlan=$external_plan"
	    write_bundle_trace_plan_manifest_fields "$trace_plan_json"
	    write_bundle_image_manifest_fields "$evidence_json"
	  } >"$manifest"
  while IFS= read -r source; do
    [[ -n "$source" && -e "$source" ]] || continue
    rel_path="$(basename "$source")"
    target="$bundle/$rel_path"
    if [[ -d "$source" ]]; then
      if ! find "$source" -type f -print -quit | grep -q .; then
        continue
      fi
      mkdir -p "$target"
      cp -a "$source"/. "$target"/
    else
      cp -a "$source" "$target"
    fi
    echo "artifact=$rel_path source=$source" >>"$manifest"
  done <<EOF
$trace_log_arg
$gdb_out
$gdb_cmd
$trace_plan_json
$trace_plan_md
$evidence_json
$evidence_md
$abi_review_json
$abi_review_md
$promotion_json
$promotion_md
$all_family_dir
$all_family_summary_json
$all_family_summary_md
$next_action_json
$next_action_md
$route_slot_recovery_verify_json
$route_slot_recovery_verify_md
$live_trace_runbook_json
$next_canary_json
$next_canary_env
EOF
  (
    cd "$bundle"
    find . -type f ! -name SHA256SUMS -print | sort | sed 's#^\./##' | xargs -r sha256sum > SHA256SUMS
  )
  echo "review_bundle=$bundle"
  echo "review_bundle_manifest=$manifest"
  echo "review_bundle_sha256=$bundle/SHA256SUMS"
  if [[ -x "$repo_root/scripts/verify-ue4ss-package-review-bundle.py" ]]; then
    "$repo_root/scripts/verify-ue4ss-package-review-bundle.py" "$bundle" --format json >"$review_bundle_verify_json" || true
    "$repo_root/scripts/verify-ue4ss-package-review-bundle.py" "$bundle" --format markdown >"$review_bundle_verify_md" || true
    echo "review_bundle_verify_json=$review_bundle_verify_json"
    echo "review_bundle_verify=$review_bundle_verify_md"
    sed -n '1,60p' "$review_bundle_verify_md" 2>/dev/null || true
  fi
}

candidate_families() {
  local evidence="$1"
  python3 - "$evidence" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)
known = {"StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName"}
printed = set()
rank = 0
for candidate in data.get("concreteReviewPriority") or data.get("reviewPriority") or []:
    family = candidate.get("seed") or candidate.get("signatureFamily") or ""
    if family in known and family not in printed:
        hit_index = candidate.get("hitIndex", "auto")
        if not isinstance(hit_index, int):
            continue
        print(f"{rank}\t{family}\t{hit_index}")
        printed.add(family)
        rank += 1
for family, candidate in sorted((data.get("familyCandidates") or {}).items()):
    if family in known and family not in printed:
        hit_index = candidate.get("hitIndex", "auto") if isinstance(candidate, dict) else "auto"
        if not isinstance(hit_index, int):
            continue
        print(f"{rank}\t{family}\t{hit_index}")
        printed.add(family)
        rank += 1
PY
}

write_all_family_reviews() {
  local promotion_args=("$@")
  local family rank review_hit_index family_dir family_abi_json family_abi_md family_promotion_json family_promotion_md
  local wrote=0

  rm -rf "$all_family_dir"
  rm -f "$all_family_summary_json" "$all_family_summary_md"
  mkdir -p "$all_family_dir"
  while IFS=$'\t' read -r rank family review_hit_index; do
    [[ -n "$family" ]] || continue
    family_dir="$all_family_dir/$family"
    mkdir -p "$family_dir"
    python3 - "$rank" "$family" "${review_hit_index:-auto}" >"$family_dir/review-priority.json" <<'PY'
import json
import sys

rank = int(sys.argv[1])
family = sys.argv[2]
raw_hit_index = sys.argv[3] or "auto"
if not raw_hit_index.isdigit():
    raise SystemExit(f"review-priority hitIndex must be concrete integer, got {raw_hit_index!r}")
hit_index = int(raw_hit_index)
json.dump(
    {
        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
        "rank": rank,
        "signatureFamily": family,
        "hitIndex": hit_index,
    },
    sys.stdout,
    sort_keys=True,
)
sys.stdout.write("\n")
PY
    family_abi_json="$family_dir/abi-review.json"
    family_abi_md="$family_dir/abi-review.md"
    family_promotion_json="$family_dir/promotion-env.json"
    family_promotion_md="$family_dir/promotion-env.md"
    "$repo_root/scripts/review-ue4ss-package-abi.py" "$evidence_json" \
      --signature-family "$family" \
      --hit-index "${review_hit_index:-auto}" \
      --format json >"$family_abi_json" || true
    "$repo_root/scripts/review-ue4ss-package-abi.py" "$evidence_json" \
      --signature-family "$family" \
      --hit-index "${review_hit_index:-auto}" \
      --format markdown >"$family_abi_md" || true
    "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$evidence_json" \
      --abi-review-json "$family_abi_json" \
      --signature-family "$family" \
      --hit-index "${review_hit_index:-auto}" \
      "${promotion_args[@]}" \
      --format json >"$family_promotion_json" || true
    "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$evidence_json" \
      --abi-review-json "$family_abi_json" \
      --signature-family "$family" \
      --hit-index "${review_hit_index:-auto}" \
      "${promotion_args[@]}" \
      --format markdown >"$family_promotion_md" || true
    wrote=1
  done < <(candidate_families "$evidence_json")

  if [[ "$wrote" == "1" ]]; then
    echo "all_family_review_dir=$all_family_dir"
    find "$all_family_dir" -mindepth 2 -maxdepth 2 \( -name 'abi-review.md' -o -name 'promotion-env.json' \) -print | sort
    if [[ -x "$repo_root/scripts/summarize-ue4ss-package-promotion-dir.py" ]]; then
      "$repo_root/scripts/summarize-ue4ss-package-promotion-dir.py" "$all_family_dir" --format markdown >"$all_family_summary_md" || true
      "$repo_root/scripts/summarize-ue4ss-package-promotion-dir.py" "$all_family_dir" --format json >"$all_family_summary_json" || true
      echo "all_family_summary_md=$all_family_summary_md"
      echo "all_family_summary_json=$all_family_summary_json"
      sed -n '1,80p' "$all_family_summary_md" 2>/dev/null || true
    fi
  else
    echo "all_family_review_dir=$all_family_dir (no captured family candidates)"
  fi
}

do_arm() {
  assert_host
  assert_runtime_selector_args
  assert_signature_family
  assert_anchor_args
  assert_trace_limit
  local trace_log="${3:-$default_log}"
  assert_trace_output_paths "$trace_log"
  [[ -f "$external_plan" ]] || { echo "ERROR: external plan not found: $external_plan" >&2; exit 1; }

  local pid
  pid="$(server_pid)"
  [[ -n "$pid" ]] || { echo "$container: no process matching '$process_pattern' found" >&2; exit 1; }

  kill_existing_gdb

  local trace_anchor_args=()
  while IFS= read -r arg; do
    trace_anchor_args+=("$arg")
  done < <(anchor_args)
  while IFS= read -r arg; do
    trace_anchor_args+=("$arg")
  done < <(seed_address_args)
  while IFS= read -r arg; do
    trace_anchor_args+=("$arg")
  done < <(route_address_args)
  local effective_limit="$limit"
  local anchor_count=$(( ${#trace_anchor_args[@]} / 2 ))
  if [[ -z "${DUNE_UE4SS_PACKAGE_TRACE_LIMIT:-}" && "$anchor_count" -gt 1 ]]; then
    effective_limit="$anchor_count"
  fi

  "$repo_root/scripts/plan-ue4ss-package-runtime-trace.py" \
    --external-plan "$external_plan" \
    --pid "$pid" \
    "${trace_anchor_args[@]}" \
    --method-candidates "$method_candidates" \
    --method-limit "$method_limit" \
    --limit "$effective_limit" \
    --format json >"$trace_plan_json"
  require_trace_plan_ready "$trace_plan_json"
  "$repo_root/scripts/plan-ue4ss-package-runtime-trace.py" \
    --external-plan "$external_plan" \
    --pid "$pid" \
    "${trace_anchor_args[@]}" \
    --method-candidates "$method_candidates" \
    --method-limit "$method_limit" \
    --limit "$effective_limit" \
    --gdb-out "$gdb_cmd" \
    --format markdown >"$trace_plan_md"

  remove_generated_file "$trace_log"
  remove_generated_file "$gdb_out"
  {
    printf 'set logging file %s\n' "$trace_log"
    printf 'set logging overwrite on\n'
    printf 'set logging enabled on\n'
    cat "$gdb_cmd"
  } >"$gdb_cmd.with-log"
  mv "$gdb_cmd.with-log" "$gdb_cmd"

  local gdb_bin="${DUNE_UE4SS_PACKAGE_TRACE_GDB_BIN:-gdb}"
  sudo -n "$gdb_bin" -q -p "$pid" -x "$gdb_cmd" >"$gdb_out" 2>&1 &
  local gdb_pid=$!
  echo "$gdb_pid" >"$gdb_pid_file"

  sleep 0.8
  if ! kill -0 "$gdb_pid" 2>/dev/null; then
    echo "ERROR: package trace gdb exited before the arm window could be used; see $gdb_out" >&2
    tail -80 "$gdb_out" 2>/dev/null >&2 || true
    rm -f "$gdb_pid_file"
    exit 1
  fi
  echo "armed package trace container=$container pid=$pid gdb_pid=$(cat "$gdb_pid_file")"
  echo "plan=$trace_plan_md"
  echo "log=$trace_log"
  echo "gdb_out=$gdb_out"
  tail -80 "$gdb_out" 2>/dev/null || true
}

do_preflight() {
  assert_host
  assert_runtime_selector_args
  assert_signature_family
  assert_anchor_args
  assert_trace_limit
  assert_hit_index
  assert_promotion_review_args
  local trace_log="${3:-$default_log}"
  assert_trace_output_paths "$trace_log"
  [[ -f "$external_plan" ]] || { echo "ERROR: external plan not found: $external_plan" >&2; exit 1; }

  local pid
  pid="$(server_pid)"
  if [[ -z "$pid" ]]; then
    if ! docker_container_exists; then
      echo "$container: docker container not found" >&2
    else
      echo "$container: no process matching '$process_pattern' found" >&2
    fi
    exit 1
  fi

  local gdb_bin="${DUNE_UE4SS_PACKAGE_TRACE_GDB_BIN:-gdb}"
  if ! command -v "$gdb_bin" >/dev/null 2>&1; then
    echo "ERROR: gdb binary not found: $gdb_bin" >&2
    exit 1
  fi
  if ! sudo -n true >/dev/null 2>&1; then
    echo "ERROR: sudo -n is required for gdb attach; configure noninteractive sudo or run from an approved root shell." >&2
    exit 1
  fi

  echo "preflight=ok"
  echo "container=$container"
  echo "process_pattern=$process_pattern"
  echo "server_pid=$pid"
  echo "server_state=$(server_state "$pid")"
  echo "external_plan=$external_plan"
  refresh_trace_plan_outputs "$pid"
  require_trace_plan_ready "$trace_plan_json"
  echo "trace_plan_json=$trace_plan_json"
  echo "trace_plan_md=$trace_plan_md"
  echo "trace_log=$trace_log"
  echo "route_address=$route_address"
  echo "gdb_bin=$(command -v "$gdb_bin")"
  if [[ -r /proc/sys/kernel/yama/ptrace_scope ]]; then
    echo "ptrace_scope=$(cat /proc/sys/kernel/yama/ptrace_scope)"
  fi
}

do_stop() {
  assert_host
  assert_runtime_selector_args
  assert_trace_output_paths
  kill_existing_gdb
  local pid state
  pid="$(server_pid)"
  if [[ -n "$pid" ]]; then
    state="$(server_state "$pid")"
    echo "server pid=$pid state=$state (expect R/S; t/T means stopped)"
    if [[ "$state" == "t" || "$state" == "T" ]]; then
      echo "WARN: server appears stopped; sending SIGCONT" >&2
      sudo -n kill -CONT "$pid" 2>/dev/null || kill -CONT "$pid" 2>/dev/null || true
    fi
  else
    echo "WARN: no process matching '$process_pattern' found for $container" >&2
  fi
}

do_status() {
  assert_host
  assert_runtime_selector_args
  assert_signature_family
  assert_hit_index
  assert_promotion_review_args
  local pid gdb_pid=""
  local trace_log="${3:-$default_log}"
  assert_trace_output_paths "$trace_log"
  pid="$(server_pid || true)"
  [[ -s "$gdb_pid_file" ]] && gdb_pid="$(cat "$gdb_pid_file" 2>/dev/null || true)"
  echo "container=$container"
  echo "server_pid=${pid:-}"
  if [[ -n "${pid:-}" ]]; then
    echo "server_state=$(server_state "$pid")"
  fi
  echo "gdb_pid=$gdb_pid"
  if [[ "$gdb_pid" =~ ^[0-9]+$ ]]; then
    if ps -p "$gdb_pid" -o pid=,stat=,cmd= 2>/dev/null; then
      echo "gdb_running=true"
    else
      echo "gdb_running=false"
      echo "WARN: package trace gdb pid file exists but gdb is not running" >&2
    fi
  else
    echo "gdb_running=false"
  fi
  echo "gdb_out=$gdb_out"
  tail -40 "$gdb_out" 2>/dev/null || true
  if [[ "$gdb_pid" =~ ^[0-9]+$ ]] && ps -p "$gdb_pid" >/dev/null 2>&1; then
    echo "status_detach=begin"
    kill_existing_gdb
    echo "status_detach=done"
  fi
	  rm -f \
	    "$evidence_json" "$evidence_md" \
	    "$abi_review_json" "$abi_review_md" \
	    "$promotion_json" "$promotion_md" \
	    "$all_family_summary_json" "$all_family_summary_md" \
	    "$trace_plan_json" "$trace_plan_md" \
	    "$next_action_json" "$next_action_md" \
	    "$next_canary_json" "$next_canary_env"
		  rm -rf "$all_family_dir"
  if [[ -f "$external_plan" ]]; then
    refresh_trace_plan_outputs "${pid:-}" || true
  fi
  if [[ -x "$repo_root/scripts/summarize-ue4ss-package-runtime-trace-evidence.py" ]]; then
    echo "--evidence--"
    if [[ -n "${pid:-}" ]]; then
      "$repo_root/scripts/summarize-ue4ss-package-runtime-trace-evidence.py" "$trace_log" --pid "$pid" --trace-plan-json "$trace_plan_json" --format json >"$evidence_json" || true
      "$repo_root/scripts/summarize-ue4ss-package-runtime-trace-evidence.py" "$trace_log" --pid "$pid" --trace-plan-json "$trace_plan_json" --format markdown >"$evidence_md" || true
    else
      "$repo_root/scripts/summarize-ue4ss-package-runtime-trace-evidence.py" "$trace_log" --trace-plan-json "$trace_plan_json" --format json >"$evidence_json" || true
      "$repo_root/scripts/summarize-ue4ss-package-runtime-trace-evidence.py" "$trace_log" --trace-plan-json "$trace_plan_json" --format markdown >"$evidence_md" || true
    fi
    cat "$evidence_md" 2>/dev/null || true
    echo "evidence_json=$evidence_json"
    echo "evidence_md=$evidence_md"
    if [[ -x "$repo_root/scripts/review-ue4ss-package-abi.py" && -s "$evidence_json" ]]; then
      "$repo_root/scripts/review-ue4ss-package-abi.py" "$evidence_json" \
        --signature-family "$signature_family" \
        --hit-index "$hit_index" \
        --format json >"$abi_review_json" || true
      "$repo_root/scripts/review-ue4ss-package-abi.py" "$evidence_json" \
        --signature-family "$signature_family" \
        --hit-index "$hit_index" \
        --format markdown >"$abi_review_md" || true
      echo "abi_review_json=$abi_review_json"
      echo "abi_review=$abi_review_md"
      sed -n '1,80p' "$abi_review_md" 2>/dev/null || true
    fi
    if [[ -x "$repo_root/scripts/export-ue4ss-package-promotion-env.py" && -s "$evidence_json" ]]; then
      local promotion_args=()
      while IFS= read -r arg; do
        promotion_args+=("$arg")
      done < <(promotion_review_args)
      if [[ -x "$repo_root/scripts/review-ue4ss-package-abi.py" ]]; then
        write_all_family_reviews "${promotion_args[@]}"
      fi
      if [[ -s "$abi_review_json" ]]; then
        "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$evidence_json" \
          --abi-review-json "$abi_review_json" \
          --signature-family "$signature_family" \
          --hit-index "$hit_index" \
          "${promotion_args[@]}" \
          --format markdown >"$promotion_md" || true
        "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$evidence_json" \
          --abi-review-json "$abi_review_json" \
          --signature-family "$signature_family" \
          --hit-index "$hit_index" \
          "${promotion_args[@]}" \
          --format json >"$promotion_json" || true
      else
        "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$evidence_json" \
          --signature-family "$signature_family" \
          --hit-index "$hit_index" \
          "${promotion_args[@]}" \
          --format markdown >"$promotion_md" || true
        "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$evidence_json" \
          --signature-family "$signature_family" \
          --hit-index "$hit_index" \
          "${promotion_args[@]}" \
          --format json >"$promotion_json" || true
      fi
      echo "promotion_json=$promotion_json"
      echo "promotion_preview=$promotion_md"
      sed -n '1,80p' "$promotion_md" 2>/dev/null || true
      print_next_canary_preview
      write_next_action "$trace_log" "${pid:-}"
      write_route_slot_recovery_verification
      write_review_bundle "$trace_log"
    fi
  fi
}

case "$action" in
  preflight)
    do_preflight "$@"
    ;;
  arm)
    do_arm "$@"
    ;;
  stop)
    do_stop
    ;;
  status)
    do_status "$@"
    ;;
  -h|--help|"")
    sed -n '1,33p' "$0"
    ;;
  *)
    echo "unknown action: $action (use preflight|arm|stop|status)" >&2
    exit 2
    ;;
esac
