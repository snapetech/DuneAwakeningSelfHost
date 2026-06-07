#!/usr/bin/env bash
set -euo pipefail

container="${1:-dune_server-deep-desert-1}"
log="${2:-/tmp/brt-dd-focused-persistent-trace.log}"
required_host="${DUNE_BRT_DD_TRACE_HOST:-kspls0}"
supervisor_pid_file="${DUNE_BRT_DD_TRACE_PID_FILE:-/tmp/brt-dd-focused-persistent-trace.pid}"
gdb_pid_file="${DUNE_BRT_DD_TRACE_GDB_PID_FILE:-/tmp/brt-dd-focused-persistent-trace.gdb.pid}"
gdb_cmd_file="${DUNE_BRT_DD_TRACE_GDB_CMD_FILE:-/tmp/brt-dd-focused-persistent-trace.gdb}"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "$(ts) BRT_DD_FOCUSED_TRACE refuse_host actual=$short_host required=$required_host" >&2
  exit 1
fi

sudo -n rm -f "$supervisor_pid_file" "$gdb_pid_file" 2>/dev/null || rm -f "$supervisor_pid_file" "$gdb_pid_file" 2>/dev/null || true
echo "$$" >"$supervisor_pid_file"
child_pid=""

kill_tree() {
  local root="$1" child
  [[ "$root" =~ ^[0-9]+$ ]] || return 0
  for child in $(pgrep -P "$root" 2>/dev/null || true); do
    kill_tree "$child"
  done
  sudo -n kill "$root" 2>/dev/null || kill "$root" 2>/dev/null || true
}

cleanup() {
  local old_child="${child_pid:-}"
  if [[ -n "$old_child" ]] && ps -p "$old_child" >/dev/null 2>&1; then
    kill_tree "$old_child"
  fi
  sudo -n rm -f "$supervisor_pid_file" "$gdb_pid_file" 2>/dev/null || rm -f "$supervisor_pid_file" "$gdb_pid_file" 2>/dev/null || true
}

stop_now() {
  cleanup
  exit 0
}

trap cleanup EXIT
trap stop_now INT TERM

server_pid() {
  docker top "$container" -eo pid,args 2>/dev/null \
    | awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}'
}

pie_base() {
  local pid="$1" exe_path base
  exe_path="$(sudo -n readlink "/proc/$pid/exe" 2>/dev/null || true)"
  if [[ -n "$exe_path" ]]; then
    base="$(sudo -n awk -v exe="$exe_path" '$6 == exe && $3 == "00000000" {split($1,a,"-"); print "0x"a[1]; exit}' "/proc/$pid/maps" 2>/dev/null || true)"
    [[ -n "$base" ]] && { echo "$base"; return 0; }
  fi
  sudo -n awk '/DuneSandboxServer-Linux-Shipping/ && $2 ~ /r.xp/ {split($1,a,"-"); print "0x"a[1]; exit}' "/proc/$pid/maps" 2>/dev/null || true
}

addr() {
  local base="$1" off="$2"
  printf '0x%x' $((base + off))
}

emit_bp() {
  local base="$1" name="$2" off="$3" abs
  abs="$(addr "$base" "$off")"
  printf 'break *%s\n' "$abs"
  printf 'commands\n'
  printf ' silent\n'
  printf '%s\n' ' python import datetime; print("BRT_FOCUSED_TS utc=" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), flush=True)'
  printf ' printf "BRT_FOCUSED_HIT name=%s off=%s rip=%%p rax=%%p eax=0x%%x al=0x%%x rbx=%%p r12=%%p r13=%%p r14=%%p r15=%%p rdi=%%p rsi=%%p rdx=%%p rcx=%%p r8=%%p r9=%%p rsp=%%p rbp=%%p\\n", $rip, $rax, $eax, $al, $rbx, $r12, $r13, $r14, $r15, $rdi, $rsi, $rdx, $rcx, $r8, $r9, $rsp, $rbp\n' "$name" "$off"
  printf ' printf "BRT_FOCUSED_FRAME name=%s rbp_m40=%%p rbp_m58=%%p rbp_m98=0x%%lx rbp_m30=0x%%lx rbp_m34=0x%%x rbp_m5c=0x%%x rbp_m228=%%p rbp_m220=%%p\\n", *(void **)($rbp-0x40), *(void **)($rbp-0x58), *(unsigned long *)($rbp-0x98), *(unsigned long *)($rbp-0x30), *(unsigned int *)($rbp-0x34), *(int *)($rbp-0x5c), *(void **)($rbp-0x228), *(void **)($rbp-0x220)\n' "$name"
  printf ' continue\n'
  printf 'end\n'
}

write_gdb_cmd() {
  local pid="$1" base="$2"
  {
    printf 'set pagination off\n'
    printf 'set confirm off\n'
    printf 'set print pretty off\n'
    printf 'set breakpoint pending off\n'
    printf 'set detach-on-fork on\n'
    printf 'handle SIGPIPE nostop noprint pass\n'
    printf 'printf "BRT_DD_FOCUSED_TRACE armed container=%s pid=%s base=%s profile=focused-brt points=dynamic\\n"\n' "$container" "$pid" "$base"

    while read -r name off; do
      [[ -z "${name:-}" || "${name:0:1}" == "#" ]] && continue
      emit_bp "$base" "$name" "$off"
    done <<'POINTS'
tool_reason_entry 0xe0430e0
tool_can_entry 0xe0436e0
tool_can_region_fail_join 0xe043874
tool_can_return 0xe04372c
tool_reason_action_result_b 0xe04334d
tool_action_deep_guard_check 0xe03ee43
tool_action_deep_map_lookup_result 0xe03eebd
tool_action_deep_payload_build 0xe03efe7
tool_action_deep_hash_branch 0xe03f00f
tool_action_deep_payload_ready 0xe03f076
tool_action_deep_assign_context 0xe03f143
tool_action_deep_deferred_result 0xe03f1d7
tool_action_final_gate 0xe03f272
tool_action_final_gate_after_check 0xe03f286
tool_action_deep_fallback_entry 0xe03ef10
tool_action_deep_no_map_entry 0xe03efaf
tool_action_missing_target 0xe03eede
tool_action_final_apply 0xe03f28c
brt_component_status_backup_blocked_a 0xd078c16
brt_component_status_backup_commit 0xd07913e
brt_component_can_backup_call_a 0xd079302
brt_component_can_backup_detail_a 0xd079757
brt_component_can_backup_detail_b 0xd079837
brt_component_reset_entry 0xd079b50
brt_component_validate_selection 0xd079d70
brt_component_activate_entry 0xd079f70
brt_component_status_finalize 0xd07a170
brt_component_set_status 0xd07a540
backup_action_primary_check 0xcf52300
backup_action_secondary_check 0xcf52370
backup_action_perform 0xcf523e0
backup_action_method_gate 0xcf50d30
backup_action_persist_path 0xd052dc0
backup_action_response_a 0xcf79c30
backup_action_response_b 0xcf79c40
place_action_primary_check 0xcf569c0
place_action_secondary_check 0xcf56a30
place_action_perform 0xcf56b50
place_action_method_gate 0xcf56220
server_request_basebackup_registration 0xd21f03c
POINTS

    printf 'continue\n'
  } >"$gdb_cmd_file"
}

echo "$(ts) BRT_DD_FOCUSED_TRACE supervisor_start host=$short_host container=$container log=$log"

while true; do
  pid="$(server_pid || true)"
  if [[ -z "$pid" ]]; then
    echo "$(ts) BRT_DD_FOCUSED_TRACE waiting_for_pid container=$container" >>"$log"
    sleep 5
    continue
  fi

  base="$(pie_base "$pid")"
  if [[ -z "$base" ]]; then
    echo "$(ts) BRT_DD_FOCUSED_TRACE no_pie_base pid=$pid" >>"$log"
    sleep 5
    continue
  fi

  write_gdb_cmd "$pid" "$base"
  echo "$(ts) BRT_DD_FOCUSED_TRACE attaching pid=$pid base=$base" >>"$log"
  sudo -n stdbuf -oL -eL gdb -q -p "$pid" -x "$gdb_cmd_file" >>"$log" 2>&1 &
  child_pid="$!"
  sudo -n rm -f "$gdb_pid_file" 2>/dev/null || rm -f "$gdb_pid_file" 2>/dev/null || true
  echo "$child_pid" >"$gdb_pid_file"

  status=0
  wait "$child_pid" || status="$?"
  echo "$(ts) BRT_DD_FOCUSED_TRACE gdb_exit pid=$pid status=$status" >>"$log"
  child_pid=""
  sudo -n rm -f "$gdb_pid_file" 2>/dev/null || rm -f "$gdb_pid_file" 2>/dev/null || true

  sleep 2
done
