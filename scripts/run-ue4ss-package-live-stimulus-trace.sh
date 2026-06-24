#!/usr/bin/env bash
# Coordinate the bounded live UE4SS package trace window from the generated
# stimulus runbook.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

runbook="${DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK:-$repo_root/build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json}"
review_summary_json="${DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON:-$repo_root/build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json}"
preflight_summary_json="${DUNE_UE4SS_PACKAGE_STIMULUS_PREFLIGHT_SUMMARY_JSON:-$repo_root/build/server-current-anchor-prep/ue4ss-package-live-preflight-summary.json}"
prearm_readiness_json="${DUNE_UE4SS_PACKAGE_STIMULUS_PREARM_READINESS_JSON:-$repo_root/build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json}"
wait_seconds="${DUNE_UE4SS_PACKAGE_STIMULUS_WAIT_SECONDS:-}"
trace_log_override=""
source_runbook="$runbook"
dry_run=0
effective_runbook=""
preflight_only=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      sed -n '1,68p' "$0"
      exit 0
      ;;
    --dry-run|--describe)
      dry_run=1
      shift
      ;;
    --preflight-only)
      preflight_only=1
      shift
      ;;
    --wait)
      [[ -n "${2:-}" ]] || { echo "ERROR: --wait requires seconds." >&2; exit 2; }
      wait_seconds="$2"
      shift 2
      ;;
    --runbook)
      [[ -n "${2:-}" ]] || { echo "ERROR: --runbook requires a path." >&2; exit 2; }
      runbook="$2"
      source_runbook="$2"
      shift 2
      ;;
    --trace-log)
      [[ -n "${2:-}" ]] || { echo "ERROR: --trace-log requires a path." >&2; exit 2; }
      trace_log_override="$2"
      shift 2
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ && -z "$wait_seconds" ]]; then
        wait_seconds="$1"
        shift
      else
        echo "ERROR: unknown argument: $1" >&2
        exit 2
      fi
      ;;
  esac
done

[[ -f "$runbook" ]] || { echo "ERROR: missing stimulus runbook: $runbook" >&2; exit 1; }
if [[ -n "$trace_log_override" ]]; then
  [[ "$trace_log_override" == /* ]] || { echo "ERROR: --trace-log must be an absolute remote path." >&2; exit 2; }
  source_runbook="$runbook"
  effective_runbook="$(mktemp -t ue4ss-package-live-stimulus-runbook.XXXXXX.json)"
  python3 - "$source_runbook" "$effective_runbook" "$trace_log_override" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
trace_log = sys.argv[3]
data = json.loads(source.read_text(encoding="utf-8"))
data["traceLog"] = trace_log
command = data.get("cleanupCommand", "")
if isinstance(command, str) and command:
    parts = shlex.split(command)
    try:
        wrapper_index = parts.index("scripts/ue4ss-package-remote-trace.sh")
    except ValueError:
        wrapper_index = -1
    if wrapper_index >= 0 and len(parts[wrapper_index + 1 :]) == 4:
        parts[wrapper_index + 4] = trace_log
        data["cleanupCommand"] = shlex.join(parts)
commands = data.get("commands", [])
if isinstance(commands, list):
    updated = []
    for item in commands:
        if not isinstance(item, str):
            updated.append(item)
            continue
        try:
            parts = shlex.split(item)
        except ValueError:
            updated.append(item)
            continue
        try:
            wrapper_index = parts.index("scripts/ue4ss-package-remote-trace.sh")
        except ValueError:
            updated.append(item)
            continue
        if len(parts[wrapper_index + 1 :]) == 4:
            parts[wrapper_index + 4] = trace_log
            updated.append(shlex.join(parts))
        else:
            updated.append(item)
    data["commands"] = updated
target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  runbook="$effective_runbook"
fi

eval "$(
  python3 - "$runbook" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
operator_window = data.get("operatorWindow", {}) or {}
trace_env = data.get("traceEnv", {}) or {}
trace_inputs = data.get("traceInputs", {}) or {}
required = {
    "remote": data.get("remote", ""),
    "container": data.get("container", ""),
    "trace_log": data.get("traceLog", ""),
    "max_arm_seconds": operator_window.get("maxArmSeconds", ""),
    "cleanup_required": operator_window.get("cleanupRequired", ""),
    "cleanup_command": data.get("cleanupCommand", ""),
    "no_debugger_check_command": data.get("noDebuggerCheckCommand", ""),
    "route_address": trace_inputs.get("routeAddress", ""),
}
for key, value in required.items():
    print(f"{key}={shlex.quote(str(value))}")
for key, value in sorted(trace_env.items()):
    if not isinstance(key, str) or not key.startswith("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_"):
        continue
    if not key.replace("_", "").isalnum():
        continue
    if os.environ.get(key):
        continue
    print(f"export {key}={shlex.quote(str(value))}")
PY
)"

if [[ -z "$remote" || -z "$container" || -z "$trace_log" ]]; then
  echo "ERROR: runbook must provide remote, container, and traceLog." >&2
  exit 2
fi
if [[ -n "$effective_runbook" ]]; then
  export DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON="$effective_runbook"
fi
if [[ "$cleanup_required" != "True" && "$cleanup_required" != "true" ]]; then
  echo "ERROR: runbook operatorWindow.cleanupRequired must be true." >&2
  exit 2
fi
if [[ ! "$max_arm_seconds" =~ ^[0-9]+$ || "$max_arm_seconds" -le 0 ]]; then
  echo "ERROR: runbook operatorWindow.maxArmSeconds must be a positive integer." >&2
  exit 2
fi
if [[ -z "$wait_seconds" ]]; then
  wait_seconds="$max_arm_seconds"
fi
if [[ ! "$wait_seconds" =~ ^[0-9]+$ || "$wait_seconds" -le 0 ]]; then
  echo "ERROR: wait seconds must be a positive integer." >&2
  exit 2
fi
if (( wait_seconds > max_arm_seconds )); then
  echo "ERROR: wait seconds $wait_seconds exceeds runbook maxArmSeconds $max_arm_seconds." >&2
  exit 2
fi
if [[ -z "$cleanup_command" || -z "$no_debugger_check_command" ]]; then
  echo "ERROR: runbook must provide cleanupCommand and noDebuggerCheckCommand." >&2
  exit 2
fi
if [[ -n "$route_address" ]]; then
  if [[ "${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS:-}" != "$route_address" ]]; then
    echo "ERROR: runbook traceEnv must export DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=$route_address." >&2
    exit 2
  fi
  if [[ "$cleanup_command" != *"DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=$route_address"* ]]; then
    echo "ERROR: runbook cleanupCommand must include DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=$route_address." >&2
    exit 2
  fi
fi

cleanup_identity="$(
  python3 - "$cleanup_command" <<'PY'
import shlex
import sys

command = sys.argv[1]
try:
    parts = shlex.split(command)
except ValueError:
    print("INVALID")
    raise SystemExit(0)
try:
    wrapper_index = parts.index("scripts/ue4ss-package-remote-trace.sh")
except ValueError:
    raise SystemExit(0)
tail = parts[wrapper_index + 1 :]
if len(tail) != 4:
    print("INVALID")
    raise SystemExit(0)
print("\t".join(tail))
PY
)"
if [[ "$cleanup_identity" == "INVALID" ]]; then
  echo "ERROR: runbook cleanupCommand must parse as remote trace stop command." >&2
  exit 2
fi
if [[ -n "$cleanup_identity" ]]; then
  IFS=$'\t' read -r cleanup_action cleanup_remote cleanup_container cleanup_trace_log <<< "$cleanup_identity"
  if [[ "$cleanup_action" != "stop" || "$cleanup_remote" != "$remote" || "$cleanup_container" != "$container" || "$cleanup_trace_log" != "$trace_log" ]]; then
    echo "ERROR: runbook cleanupCommand must match stop $remote $container $trace_log." >&2
    exit 2
  fi
fi

trace_args=("$remote" "$container" "$trace_log")
local_summary_verification_args=(
  python3
  "$repo_root/scripts/verify-ue4ss-package-live-stimulus-summary.py"
  "$review_summary_json"
  --runbook-json "$runbook"
  --next-action-json "$repo_root/build/server-current-anchor-prep/ue4ss-package-next-action.json"
  --format json
)
printf -v local_summary_verification_command "%q " "${local_summary_verification_args[@]}"
local_summary_verification_command="${local_summary_verification_command% }"
prearm_readiness_verification_args=(
  python3
  "$repo_root/scripts/verify-ue4ss-package-prearm-readiness.py"
  --preflight-summary "$preflight_summary_json"
  --runbook-json "$runbook"
  --next-action-json "$repo_root/build/server-current-anchor-prep/ue4ss-package-next-action.json"
  --completion-audit-json "$repo_root/build/server-current-anchor-prep/ue4ss-linux-port-completion-audit.json"
  --format json
)
printf -v prearm_readiness_verification_command "%q " "${prearm_readiness_verification_args[@]}"
prearm_readiness_verification_command="${prearm_readiness_verification_command% }"
armed=0
cleanup_done=0
status_output=""
run_started_utc=""
status_finished_utc=""

cleanup() {
  local rc=$?
  if [[ "$armed" == "1" && "$cleanup_done" == "0" ]]; then
    echo "cleanup=begin"
    bash -lc "$cleanup_command" || true
    cleanup_done=1
    echo "cleanup=done"
  fi
  echo "no_debugger_check=begin"
  bash -lc "$no_debugger_check_command" || true
  echo "no_debugger_check=done"
  if [[ -n "$status_output" ]]; then
    rm -f "$status_output"
  fi
  if [[ -n "$effective_runbook" ]]; then
    rm -f "$effective_runbook"
  fi
  return "$rc"
}

render_remote_trace_command() {
  local action="$1"
  python3 - "$repo_root/scripts/ue4ss-package-remote-trace.sh" "$action" "$remote" "$container" "$trace_log" <<'PY'
import os
import shlex
import sys

script, action, remote, container, trace_log = sys.argv[1:6]
assignments = []
for key in sorted(os.environ):
    if key.startswith("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_"):
        assignments.append(f"{key}={shlex.quote(os.environ[key])}")
parts = assignments + [shlex.quote(script), action, shlex.quote(remote), shlex.quote(container), shlex.quote(trace_log)]
print(" ".join(parts))
PY
}

print_route_slot_trace_requirement() {
  python3 - "$prearm_readiness_json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)
if not isinstance(data, dict):
    raise SystemExit(0)
requirement = (
    data.get("completionAuditNextRouteSlotTraceRequirement")
    or data.get("nextRouteSlotTraceRequirement")
    or data.get("routeSlotRecoveryNextTraceRequirement")
    or {}
)
if not isinstance(requirement, dict) or not requirement:
    raise SystemExit(0)

def join_values(values):
    if not isinstance(values, list):
        return ""
    return ",".join(str(value) for value in values if isinstance(value, (str, int)))

fields = {
    "route_slot_expected_trace_marker": requirement.get("expectedTraceMarker", ""),
    "route_slot_route_address": requirement.get("routeAddress", ""),
    "route_slot_review_field": requirement.get("reviewField") or requirement.get("expectedReviewField", ""),
    "route_slot_required_slots": join_values(requirement.get("requiredSlots")),
    "route_slot_missing_slots": join_values(requirement.get("missingSlots")),
    "route_slot_required_registers": join_values(requirement.get("requiredRegisters")),
    "route_slot_missing_registers": join_values(requirement.get("missingRegisters")),
}
for key, value in fields.items():
    if value:
        print(f"{key}={value}")
PY
}

print_review_verification_summary() {
  local verify_json="$1"
  local route_slot_verify_json="${2:-}"
  [[ -n "$verify_json" ]] || return 0
  echo "review_bundle_verify_json=$verify_json"
  local raw
  raw="$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$remote" "cat $(printf '%q' "$verify_json") 2>/dev/null" || true)"
  local route_slot_raw=""
  if [[ -n "$route_slot_verify_json" ]]; then
    echo "route_slot_recovery_verify_json=$route_slot_verify_json"
    route_slot_raw="$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$remote" "cat $(printf '%q' "$route_slot_verify_json") 2>/dev/null" || true)"
  fi
  local prearm_raw=""
  if [[ -f "$prearm_readiness_json" ]]; then
    prearm_raw="$(cat "$prearm_readiness_json" 2>/dev/null || true)"
  fi
  REVIEW_BUNDLE_VERIFY_RAW="$raw" ROUTE_SLOT_RECOVERY_VERIFY_RAW="$route_slot_raw" PREARM_READINESS_VERIFY_RAW="$prearm_raw" PREARM_READINESS_JSON_PATH="$prearm_readiness_json" python3 - \
    "$verify_json" \
    "$route_slot_verify_json" \
    "$review_summary_json" \
    "$runbook" \
    "$source_runbook" \
    "$trace_log_override" \
    "$remote" \
    "$container" \
    "$trace_log" \
    "$wait_seconds" \
    "$run_started_utc" \
    "$status_finished_utc" <<'PY'
import json
import os
from pathlib import Path
import sys
import hashlib

raw = os.environ.get("REVIEW_BUNDLE_VERIFY_RAW", "")
route_slot_raw = os.environ.get("ROUTE_SLOT_RECOVERY_VERIFY_RAW", "")
prearm_raw = os.environ.get("PREARM_READINESS_VERIFY_RAW", "")
verify_json = sys.argv[1]
route_slot_verify_json = sys.argv[2]
summary_path = Path(sys.argv[3])
runbook = sys.argv[4]
source_runbook = sys.argv[5]
trace_log_override = sys.argv[6]
remote = sys.argv[7]
container = sys.argv[8]
trace_log = sys.argv[9]
operator_window_seconds = sys.argv[10]
run_started_utc = sys.argv[11]
status_finished_utc = sys.argv[12]
runbook_payload = {}
try:
    runbook_payload = json.loads(Path(runbook).read_text(encoding="utf-8", errors="replace"))
except (OSError, json.JSONDecodeError):
    runbook_payload = {}
if not raw.strip():
    raise SystemExit(0)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(0)
verification_sha256 = hashlib.sha256(
    json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
ready = data.get("ready", "")
print(f"review_bundle_ready={str(ready).lower()}")
blockers = []
for blocker in data.get("blockers", []) or []:
    if isinstance(blocker, str) and blocker:
        blockers.append(blocker)
        print(f"review_bundle_blocker={blocker}")
runbook_classification = runbook_payload.get("originClassification", {})
if not isinstance(runbook_classification, dict):
    runbook_classification = {}
classification_status = "not-required"
classification_blockers = []
if runbook_classification:
    missing_hit = any(
        "selected runtime trace hit is missing" in str(blocker) or str(blocker).strip() == "missing hit"
        for blocker in data.get("blockers", []) or []
    )
    if missing_hit:
        classification_status = "missing"
        classification_blockers.append("package-load classification has no selected runtime package hit")
    elif data.get("ready") is True:
        classification_status = "client-originated-pending-server-replay"
    else:
        classification_status = "inconclusive"
        classification_blockers.append("package-load classification evidence is not ready")
origin_classification = {
    "status": classification_status,
    "source": "live-stimulus-review-summary",
    "probeCandidate": runbook_classification.get("probeCandidate", ""),
    "serverSideFallbackCandidate": runbook_classification.get("serverSideFallbackCandidate", ""),
    "decision": runbook_classification.get("decision", ""),
    "requiresServerSideReplay": classification_status == "client-originated-pending-server-replay",
    "blockers": classification_blockers,
}
print(f"origin_classification_status={classification_status}")
if origin_classification["requiresServerSideReplay"]:
    print("client_gate_requires_server_side_replay=true")
for blocker in classification_blockers:
    print(f"origin_classification_blocker={blocker}")
route_slot_verification = None
route_slot_sha256 = ""
route_slot_next_trace_requirement = None
route_slot_required = bool(route_slot_verify_json)
if route_slot_raw.strip():
    try:
        route_slot_verification = json.loads(route_slot_raw)
    except json.JSONDecodeError:
        route_slot_verification = None
        blockers.append("route-slot recovery verification JSON is unreadable")
    if route_slot_verification is not None:
        route_slot_sha256 = hashlib.sha256(
            json.dumps(route_slot_verification, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        route_ready = route_slot_verification.get("ready", "")
        route_slot_next_trace_requirement = route_slot_verification.get("nextTraceRequirement")
        print(f"route_slot_recovery_ready={str(route_ready).lower()}")
        for blocker in route_slot_verification.get("blockers", []) or []:
            if isinstance(blocker, str) and blocker:
                blockers.append(f"route-slot recovery: {blocker}")
                print(f"route_slot_recovery_blocker={blocker}")
elif route_slot_required:
    blockers.append("route-slot recovery verification JSON is missing")
if route_slot_verification is not None and route_slot_verification.get("ready") is not True:
    if not any(blocker.startswith("route-slot recovery:") for blocker in blockers):
        blockers.append("route-slot recovery verification is not ready")
prearm_verification = None
prearm_sha256 = ""
if prearm_raw.strip():
    try:
        prearm_verification = json.loads(prearm_raw)
    except json.JSONDecodeError:
        prearm_verification = None
        blockers.append("prearm readiness verification JSON is unreadable")
    if prearm_verification is not None:
        prearm_sha256 = hashlib.sha256(
            json.dumps(prearm_verification, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        prearm_ready = prearm_verification.get("ready", "")
        print(f"prearm_readiness_embedded_ready={str(prearm_ready).lower()}")
        for blocker in prearm_verification.get("blockers", []) or []:
            if isinstance(blocker, str) and blocker:
                blockers.append(f"prearm readiness: {blocker}")
                print(f"prearm_readiness_embedded_blocker={blocker}")
else:
    blockers.append("prearm readiness verification JSON is missing")
if prearm_verification is not None and prearm_verification.get("ready") is not True:
    if not any(blocker.startswith("prearm readiness:") for blocker in blockers):
        blockers.append("prearm readiness verification is not ready")
ready = bool(
    data.get("ready") is True
    and not blockers
    and (not route_slot_required or (route_slot_verification or {}).get("ready") is True)
    and (prearm_verification or {}).get("ready") is True
)
summary = {
    "schemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
    "runbook": runbook,
    "sourceRunbook": source_runbook,
    "traceLogOverride": trace_log_override,
    "traceRemote": remote,
    "container": container,
    "traceLog": trace_log,
    "operatorWindowSeconds": int(operator_window_seconds),
    "runStartedUtc": run_started_utc,
    "statusFinishedUtc": status_finished_utc,
    "bundle": data.get("bundle", ""),
    "verifyJson": verify_json,
    "reviewBundleVerification": data,
    "reviewBundleVerificationSha256": verification_sha256,
    "routeSlotRecoveryVerifyJson": route_slot_verify_json,
    "routeSlotRecoveryVerification": route_slot_verification,
    "routeSlotRecoveryVerificationSha256": route_slot_sha256,
    "routeSlotRecoveryNextTraceRequirement": route_slot_next_trace_requirement,
    "prearmReadinessJson": os.environ.get("PREARM_READINESS_JSON_PATH", ""),
    "prearmReadinessVerification": prearm_verification,
    "prearmReadinessVerificationSha256": prearm_sha256,
    "originClassification": origin_classification,
    "ready": ready,
    "blockers": blockers,
    "artifactCount": data.get("artifactCount"),
    "checksumCount": data.get("checksumCount"),
}
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"review_bundle_summary_json={summary_path}")
PY
  if [[ -f "$review_summary_json" ]]; then
    echo "local_review_summary_verification=begin"
    local verifier_output
    local verifier_rc=0
    verifier_output="$(
      "${local_summary_verification_args[@]}"
    )" || verifier_rc=$?
    printf '%s\n' "$verifier_output" | python3 -c 'import json,sys
raw=sys.stdin.read()
try:
    data=json.loads(raw)
except json.JSONDecodeError:
    print("local_review_summary_ready=false")
    print("local_review_summary_blocker=invalid verifier JSON")
    raise SystemExit(0)
print("local_review_summary_ready={}".format(str(data.get("ready", False)).lower()))
for blocker in data.get("blockers", []) or []:
    if isinstance(blocker, str) and blocker:
        print(f"local_review_summary_blocker={blocker}")
'
    echo "local_review_summary_verification=done"
    return "$verifier_rc"
  fi
}

write_preflight_summary_from_output() {
  local preflight_output="$1"
  python3 - \
    "$preflight_output" \
    "$preflight_summary_json" \
    "$runbook" \
    "$source_runbook" \
    "$trace_log_override" \
    "$remote" \
    "$container" \
    "$trace_log" \
    "$wait_seconds" <<'PY'
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

output_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
runbook = sys.argv[3]
source_runbook = sys.argv[4]
trace_log_override = sys.argv[5]
remote = sys.argv[6]
container = sys.argv[7]
trace_log = sys.argv[8]
operator_window_seconds = int(sys.argv[9])

fields = {}
lines = output_path.read_text(encoding="utf-8", errors="replace").splitlines()
for line in lines:
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key and "\n" not in key and "\r" not in key:
        fields[key] = value
blockers = []
if fields.get("preflight") != "ok":
    blockers.append("preflight did not report ok")
if fields.get("remote_host") and fields.get("remote_host") != remote:
    blockers.append("preflight remote_host does not match runbook remote")
if fields.get("container") and fields.get("container") != container:
    blockers.append("preflight container does not match runbook container")
connected = fields.get("player_guard_preflight_connected_players")
if connected not in ("", None, "0"):
    blockers.append(f"preflight connected players is {connected}, expected 0")
trace_env = {
    key: value
    for key, value in sorted(os.environ.items())
    if key.startswith("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_")
    and key != "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON"
}
summary = {
    "schemaVersion": "dune-ue4ss-package-live-preflight-summary/v1",
    "createdUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "runbook": runbook,
    "sourceRunbook": source_runbook,
    "traceLogOverride": trace_log_override,
    "traceRemote": remote,
    "container": container,
    "traceLog": trace_log,
    "operatorWindowSeconds": operator_window_seconds,
    "traceEnv": trace_env,
    "ready": not blockers,
    "blockers": blockers,
    "fields": fields,
}
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"preflight_summary_json={summary_path}")
print(f"preflight_summary_ready={str(not blockers).lower()}")
for blocker in blockers:
    print(f"preflight_summary_blocker={blocker}")
PY
}

echo "runbook=$runbook"
echo "source_runbook=$source_runbook"
echo "trace_log_override=$trace_log_override"
echo "remote=$remote"
echo "container=$container"
echo "trace_log=$trace_log"
echo "operator_window_seconds=$wait_seconds"
echo "coordinator_dry_run=$dry_run"
echo "coordinator_preflight_only=$preflight_only"
echo "review_bundle_summary_json=$review_summary_json"
echo "preflight_summary_json=$preflight_summary_json"
echo "prearm_readiness_json=$prearm_readiness_json"
echo "local_review_summary_verification_command=$local_summary_verification_command"
echo "prearm_readiness_verification_command=$prearm_readiness_verification_command"
print_route_slot_trace_requirement

if [[ "$dry_run" == "1" ]]; then
  echo "preflight_command=$(render_remote_trace_command preflight)"
  echo "arm_command=$(render_remote_trace_command arm)"
  echo "status_command=$(render_remote_trace_command status)"
  echo "cleanup_command=$cleanup_command"
  echo "no_debugger_check_command=$no_debugger_check_command"
  if [[ -n "$effective_runbook" ]]; then
    rm -f "$effective_runbook"
  fi
  exit 0
fi

if [[ "$preflight_only" == "1" ]]; then
  preflight_output="$(mktemp -t ue4ss-package-live-preflight.XXXXXX)"
  "$repo_root/scripts/ue4ss-package-remote-trace.sh" preflight "${trace_args[@]}" | tee "$preflight_output"
  write_preflight_summary_from_output "$preflight_output"
  rm -f "$preflight_output"
  echo "preflight_only=done"
  if [[ -n "$effective_runbook" ]]; then
    rm -f "$effective_runbook"
  fi
  exit 0
fi

trap cleanup EXIT

run_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "run_started_utc=$run_started_utc"
preflight_output="$(mktemp -t ue4ss-package-live-preflight.XXXXXX)"
"$repo_root/scripts/ue4ss-package-remote-trace.sh" preflight "${trace_args[@]}" | tee "$preflight_output"
preflight_summary_output="$(write_preflight_summary_from_output "$preflight_output")"
printf '%s\n' "$preflight_summary_output"
rm -f "$preflight_output"
if ! grep -qx 'preflight_summary_ready=true' <<<"$preflight_summary_output"; then
  echo "ERROR: live package trace preflight summary is not ready; refusing to arm." >&2
  exit 1
fi
prearm_readiness_output="$(
  "${prearm_readiness_verification_args[@]}"
)" || {
  printf '%s\n' "$prearm_readiness_output"
  echo "ERROR: package prearm readiness is not ready; refusing to arm." >&2
  exit 1
}
mkdir -p "$(dirname "$prearm_readiness_json")"
printf '%s\n' "$prearm_readiness_output" >"$prearm_readiness_json"
printf '%s\n' "$prearm_readiness_output" | python3 -c 'import json,sys
raw=sys.stdin.read()
try:
    data=json.loads(raw)
except json.JSONDecodeError:
    print("prearm_readiness_ready=false")
    print("prearm_readiness_blocker=invalid verifier JSON")
    raise SystemExit(0)
print("prearm_readiness_ready={}".format(str(data.get("ready", False)).lower()))
for blocker in data.get("blockers", []) or []:
    if isinstance(blocker, str) and blocker:
        print(f"prearm_readiness_blocker={blocker}")
'
"$repo_root/scripts/ue4ss-package-remote-trace.sh" arm "${trace_args[@]}"
armed=1
echo "operator_stimulus_window=begin"
echo "operator_stimulus_window_started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "operator_instruction=perform client login/travel/map-entry package-load stimulus now"
sleep "$wait_seconds"
echo "operator_stimulus_window_finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "operator_stimulus_window=end"
status_output="$(mktemp -t ue4ss-package-live-stimulus-status.XXXXXX)"
"$repo_root/scripts/ue4ss-package-remote-trace.sh" status "${trace_args[@]}" | tee "$status_output"
status_finished_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "status_finished_utc=$status_finished_utc"
review_bundle_verify_json="$(
  awk -F= '$1 == "review_bundle_verify_json" { value=$2 } END { print value }' "$status_output"
)"
route_slot_recovery_verify_json="$(
  awk -F= '$1 == "route_slot_recovery_verify_json" { value=$2 } END { print value }' "$status_output"
)"
print_review_verification_summary "$review_bundle_verify_json" "$route_slot_recovery_verify_json"
bash -lc "$cleanup_command"
cleanup_done=1
echo "cleanup=done"
