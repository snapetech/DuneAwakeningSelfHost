#!/usr/bin/env bash
# Phase-1 keystone runner for docs/brt-deep-desert-plan.md, adapted for the
# LIVE production host (kspls0) tracing Deep Desert #1, because the isolated
# lab host (kspld0) is unreachable.
#
# arm:  resolve build-current BRT trace offsets with Ghidra
#       (DumpBrtTraceAnchors.java) -> parse the "=> BRT_*_OFFSET=0x..." lines ->
#       pause the map watchdog -> arm scripts/trace-brt-place-live.sh in
#       KEYSTONE-ONLY mode (only the BRT RPC / restriction / region-reject
#       breakpoints, which fire when someone uses the BRT, NOT on every player's
#       building preview).
# stop: cleanly detach gdb (kernel auto-resumes the server), verify the server
#       process is not left stopped, and resume the map watchdog.
#
# Production safety:
#   - refuses to run unless hostname is kspls0 (override DUNE_BRT_DD_TRACE_HOST).
#   - keystone-only by default so live players are not trapped on every place.
#   - leaves the watchdog PAUSED while armed; you MUST run `stop` when done.
#
# Usage:
#   scripts/brt-dd-trace.sh arm  [CONTAINER] [TRACE_LOG] [ENV_FILE]
#   scripts/brt-dd-trace.sh stop [CONTAINER]            [ENV_FILE]
#
# Env:
#   BRT_TRACE_RESOLVE=1             force re-running the Ghidra resolve.
#   BRT_TRACE_KEYSTONE_ONLY=0       also arm the dense state/preview breakpoints
#                                   (hot path; only for a quiet/empty DD).
#   BRT_TRACE_ALLOW_UNRESOLVED=1    arm even if the RPC offset did not resolve.
#   BRT_TRACE_ANCHORS_FILE=...      anchors output. Default:
#                                   ${DUNE_GHIDRA_WORK_DIR:-/tmp/ghidra-work}/brt-trace-anchors.txt

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source "$repo_root/scripts/lib/brt-dd-trace-guards.sh"
action="${1:-arm}"
container="${2:-dune_server-deep-desert-1}"

work_dir="${DUNE_GHIDRA_WORK_DIR:-/tmp/ghidra-work}"
anchors_file="${BRT_TRACE_ANCHORS_FILE:-$work_dir/brt-trace-anchors.txt}"
points_file="${DUNE_BRT_DD_POINTS_FILE:-$repo_root/scripts/research/brt-dd-points-1988751.tsv}"
required_host="${DUNE_BRT_DD_TRACE_HOST:-kspls0}"
gdb_pid_file="/tmp/brt-place-trace-gdb.pid"

assert_host() {
  local short
  short="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
  if [[ "$short" != "$required_host" && "${DUNE_BRT_DD_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
    echo "ERROR: refusing to trace on host '$short'; required '$required_host'." >&2
    echo "       This traces the live Deep Desert server. Run it on $required_host," >&2
    echo "       or set DUNE_BRT_DD_TRACE_ALLOW_ANY_HOST=1 to override." >&2
    exit 1
  fi
}

watchdog() {
  "$repo_root/scripts/map-watchdog-control.sh" "$1" "$env_file" || true
}

resolve_offsets() {
  echo "resolving BRT trace offsets via Ghidra (DumpBrtTraceAnchors.java)..."
  "$repo_root/scripts/research/run-ghidra-headless.sh" \
    --script DumpBrtTraceAnchors.java \
    --log "$work_dir/brt-trace-anchors-ghidra.log"
  [[ -f "$anchors_file" ]] || { echo "ERROR: Ghidra did not produce $anchors_file" >&2; exit 1; }
}

parse_offset() {
  grep -oE "=> $1=0x[0-9a-fA-F]+" "$anchors_file" 2>/dev/null \
    | tail -n 1 | sed -E "s/.*=(0x[0-9a-fA-F]+)/\1/"
}

parse_point_offset() {
  local name="$1"
  awk -v name="$name" '
    /^[[:space:]]*(#|$)/ { next }
    NF >= 3 && $2 == name { print $3; exit }
  ' "$points_file" 2>/dev/null
}

server_pid() {
  docker top "$container" -eo pid,args 2>/dev/null \
    | awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}'
}

do_arm() {
  assert_host
  local trace_log="${1:-/tmp/brt-place-trace-lab.log}"

  local points_rpc_exec points_rpc_impl
  points_rpc_exec="$(parse_point_offset brt_rpc_exec_server_request_basebackup)"
  points_rpc_impl="$(parse_point_offset brt_rpc_impl_server_request_basebackup)"

  if [[ "${BRT_TRACE_RESOLVE:-0}" == "1" ]]; then
    resolve_offsets
  elif [[ -f "$anchors_file" ]]; then
    echo "reusing anchors file: $anchors_file (BRT_TRACE_RESOLVE=1 to refresh)"
  elif [[ -n "$points_rpc_exec" || -n "$points_rpc_impl" ]]; then
    echo "anchors file absent; using RPC offsets from current points file: $points_file"
  fi

  export BRT_RPC_PLACE_OFFSET="${BRT_RPC_PLACE_OFFSET:-$(parse_offset BRT_RPC_PLACE_OFFSET)}"
  export BRT_RPC_EXEC_OFFSET="${BRT_RPC_EXEC_OFFSET:-$points_rpc_exec}"
  if [[ -z "${BRT_RPC_PLACE_OFFSET:-}" ]]; then
    export BRT_RPC_PLACE_OFFSET="$points_rpc_impl"
  fi
  export BRT_RESTRICTION_GATE_OFFSET="${BRT_RESTRICTION_GATE_OFFSET:-$(parse_offset BRT_RESTRICTION_GATE_OFFSET)}"
  export BRT_REGION_REJECT_OFFSET="${BRT_REGION_REJECT_OFFSET:-$(parse_offset BRT_REGION_REJECT_OFFSET)}"
  export BRT_TRACE_KEYSTONE_ONLY="${BRT_TRACE_KEYSTONE_ONLY:-1}"

  echo "resolved offsets:"
  echo "  points_file=$points_file"
  echo "  BRT_RPC_EXEC_OFFSET=${BRT_RPC_EXEC_OFFSET:-<unresolved>}"
  echo "  BRT_RPC_PLACE_OFFSET=${BRT_RPC_PLACE_OFFSET:-<unresolved>}"
  echo "  BRT_RESTRICTION_GATE_OFFSET=${BRT_RESTRICTION_GATE_OFFSET:-<unresolved>}"
  echo "  BRT_REGION_REJECT_OFFSET=${BRT_REGION_REJECT_OFFSET:-<unresolved>}"
  echo "  BRT_TRACE_KEYSTONE_ONLY=$BRT_TRACE_KEYSTONE_ONLY"

  if [[ -z "${BRT_RPC_EXEC_OFFSET:-}" && -z "${BRT_RPC_PLACE_OFFSET:-}" && "${BRT_TRACE_ALLOW_UNRESOLVED:-0}" != "1" ]]; then
    echo "ERROR: RPC offsets unresolved -> the keystone (did the request" >&2
    echo "       reach the server) cannot be answered. Inspect $anchors_file and" >&2
    echo "       $points_file, set BRT_RPC_*_OFFSET, or pass BRT_TRACE_ALLOW_UNRESOLVED=1." >&2
    exit 1
  fi

  echo "pausing map watchdog (stays paused until you run: stop)"
  watchdog pause

  echo "arming keystone trace on container=$container log=$trace_log"
  "$repo_root/scripts/trace-brt-place-live.sh" "$container" "$trace_log"

  cat <<EOF

ARMED. Now have a tester attempt a BRT restore in Deep Desert.
Watch:   tail -f $trace_log
Classify:
    scripts/classify-brt-dd-trace.py $trace_log --format json > /tmp/brt-dd-trace-classification.json
Keystone read: if SERVER-RPC-ENTRY/SERVER-RPC-EXEC fires, the request reached
the server and the next fix belongs on the reached server-side gate. If neither
fires during the attempt, do not require client-side file changes by default;
treat the normal request as not observed and use the server-side emulation path.

*** REMEMBER to disarm and resume the watchdog when done: ***
    scripts/brt-dd-trace.sh stop $container
EOF
}

do_stop() {
  assert_host
  local gdb_pid ok=1
  if [[ -s "$gdb_pid_file" ]]; then
    gdb_pid="$(cat "$gdb_pid_file" 2>/dev/null || true)"
    if [[ "$gdb_pid" =~ ^[0-9]+$ ]] && ps -p "$gdb_pid" -o cmd= 2>/dev/null | grep -q 'gdb -q -p'; then
      echo "detaching gdb pid $gdb_pid (SIGTERM -> gdb detaches, kernel resumes server)"
      sudo -n kill "$gdb_pid" 2>/dev/null || kill "$gdb_pid" 2>/dev/null || true
      for _ in 1 2 3 4 5 6 7 8 9 10; do
        ps -p "$gdb_pid" >/dev/null 2>&1 || { ok=0; break; }
        sleep 0.3
      done
      [[ "$ok" == 0 ]] && echo "gdb detached" || echo "WARN: gdb pid $gdb_pid still present" >&2
    else
      echo "no live gdb for $gdb_pid; nothing to detach"
    fi
    rm -f "$gdb_pid_file"
  else
    echo "no gdb pid file; nothing to detach"
  fi

  local spid state
  spid="$(server_pid)"
  if [[ -n "$spid" ]]; then
    state="$(sudo -n awk '{print $3}' "/proc/$spid/stat" 2>/dev/null || awk '{print $3}' "/proc/$spid/stat" 2>/dev/null || echo '?')"
    echo "server pid=$spid state=$state (expect R/S; 't'/'T' means left stopped)"
    if [[ "$state" == "t" || "$state" == "T" ]]; then
      echo "WARN: server appears STOPPED; sending SIGCONT" >&2
      sudo -n kill -CONT "$spid" 2>/dev/null || kill -CONT "$spid" 2>/dev/null || true
    fi
  else
    echo "WARN: could not find live server process for $container" >&2
  fi

  echo "resuming map watchdog"
  watchdog resume
}

case "$action" in
  arm)
    # arm [CONTAINER] [TRACE_LOG] [ENV_FILE]
    trace_log="${3:-/tmp/brt-place-trace-lab.log}"
    env_file="${4:-${ENV_FILE:-.env}}"
    do_arm "$trace_log"
    ;;
  stop)
    # stop [CONTAINER] [ENV_FILE]
    env_file="${3:-${ENV_FILE:-.env}}"
    do_stop
    ;;
  -h|--help|"")
    sed -n '1,40p' "$0"
    ;;
  *)
    echo "unknown action: $action (use arm|stop)" >&2
    exit 2
    ;;
esac
