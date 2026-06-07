#!/usr/bin/env bash
set -euo pipefail

container="${1:-dune_server-deep-desert-1}"
log="${2:-/tmp/brt-dd-persistent-trace.log}"
required_host="${DUNE_BRT_DD_TRACE_HOST:-kspls0}"
supervisor_pid_file="${DUNE_BRT_DD_TRACE_PID_FILE:-/tmp/brt-dd-persistent-trace.pid}"
gdb_pid_file="${DUNE_BRT_DD_TRACE_GDB_PID_FILE:-/tmp/brt-dd-persistent-trace.gdb.pid}"
gdb_cmd_file="${DUNE_BRT_DD_TRACE_GDB_CMD_FILE:-/tmp/brt-dd-persistent-trace.gdb}"

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "$(ts) BRT_DD_PERSISTENT_TRACE_WIDE refuse_host actual=$short_host required=$required_host" >&2
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
  printf '%s\n' ' python import datetime; print("BRT_WIDE_TS utc=" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), flush=True)'
  printf ' printf "BRT_WIDE_HIT name=%s off=%s rip=%%p rax=%%p eax=0x%%x al=0x%%x rbx=%%p r12=%%p r13=%%p r14=%%p r15=%%p rdi=%%p rsi=%%p rdx=%%p rcx=%%p r8=%%p r9=%%p rsp=%%p rbp=%%p\\n", $rip, $rax, $eax, $al, $rbx, $r12, $r13, $r14, $r15, $rdi, $rsi, $rdx, $rcx, $r8, $r9, $rsp, $rbp\n' "$name" "$off"
  printf ' printf "BRT_WIDE_FRAME name=%s rbp_m40=%%p rbp_m58=%%p rbp_m98=0x%%lx rbp_m30=0x%%lx rbp_m34=0x%%x rbp_m5c=0x%%x rbp_m228=%%p rbp_m220=%%p\\n", *(void **)($rbp-0x40), *(void **)($rbp-0x58), *(unsigned long *)($rbp-0x98), *(unsigned long *)($rbp-0x30), *(unsigned int *)($rbp-0x34), *(int *)($rbp-0x5c), *(void **)($rbp-0x228), *(void **)($rbp-0x220)\n' "$name"
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
    printf 'printf "BRT_DD_PERSISTENT_TRACE_WIDE armed container=%s pid=%s base=%s profile=brt-native-wide points=dynamic\\n"\n' "$container" "$pid" "$base"

    while read -r name off; do
      [[ -z "${name:-}" || "${name:0:1}" == "#" ]] && continue
      emit_bp "$base" "$name" "$off"
    done <<'POINTS'
tool_reason_entry 0xe0430e0
tool_reason_return 0xe04312f
tool_reason_action_result_b 0xe04334d
tool_action_pre_reason 0xe043010
tool_state_entry 0xe043510
tool_state_return 0xe043535
tool_can_entry 0xe0436e0
tool_can_return 0xe04372c
tool_can_after_actor_lookup 0xe043865
tool_can_region_fail_join 0xe043874
tool_action_slot103 0xe03e940
tool_action_after_reason 0xe03e966
tool_action_return 0xe03e96a
tool_action_mode3_context 0xe03e987
tool_action_mode3_before_apply 0xe03e9d2
tool_action_other_mode_context 0xe03e9d9
tool_action_other_after_first_apply 0xe03ea34
tool_action_deep_branch 0xe03ed46
tool_action_deep_after_primary_check 0xe03ed55
tool_action_deep_first_gate 0xe03ed5f
tool_action_deep_first_pass 0xe03ed65
tool_action_deep_selected_ptr 0xe03ed90
tool_action_deep_static_lookup_return 0xe03eda4
tool_action_deep_context_ptr 0xe03edce
tool_action_deep_second_lookup_return 0xe03eddf
tool_action_deep_context_cleanup 0xe03ee22
tool_action_deep_guard_check 0xe03ee43
tool_action_deep_map_capacity_check 0xe03ee89
tool_action_deep_map_lookup_result 0xe03eebd
tool_action_deep_fallback_entry 0xe03ef10
tool_action_deep_abort_cleanup 0xe03ef89
tool_action_deep_no_map_entry 0xe03efaf
tool_action_deep_payload_build 0xe03efe7
tool_action_deep_hash_branch 0xe03f00f
tool_action_deep_payload_ready 0xe03f076
tool_action_deep_assign_context 0xe03f143
tool_action_deep_deferred_result 0xe03f1d7
tool_action_final_gate 0xe03f272
tool_action_final_gate_after_check 0xe03f286
tool_action_missing_target 0xe03eede
tool_action_final_apply 0xe03f28c
tool_apply_helper_entry 0xe03fe60
tool_apply_helper_invalid 0xe03fe98
tool_apply_helper_valid 0xe03feab
tool_apply_helper_virtual_c88 0xe03fee1
tool_apply_helper_after_c88 0xe03fee7
tool_apply_helper_effect_call 0xe03ff85
tool_apply_helper_return 0xe03fe9d
tool_action_slot104 0xe0438a0
tool_action_slot105 0xe043ae0
tool_action_slot107 0xe0461b0
tool_action_slot108 0xe046250
tool_action_slot109 0xe043e80
tool_action_slot110 0xe043df0
tool_action_slot113 0xe045e30
tool_action_slot116 0xe03fd30
tool_action_slot118 0xe046240
tool_action_slot121 0xe046180
tool_action_slot123 0xe0445f0
tool_action_slot129 0xe046080
tool_action_slot133 0xe046110
tool_action_ctor 0xe039830
tool_action_dtor 0xe039840
tool_action_thunk 0xe039860
gameitem_brt_slot136 0xe039800
gameitem_brt_slot137 0xe039730
gameitem_brt_slot143 0xe039ce0
gameitem_brt_slot145 0xe03a090
gameitem_brt_slot147 0xe039fa0
gameitem_brt_slot149 0xe039a30
gameitem_brt_slot151 0xe039870
gameitem_brt_slot179 0xe03a3d0
gameitem_brt_slot189 0xe03a3e0
gameitem_brt_slot194 0xe03a3f0
gameitem_brt_slot230 0xe03a450
gameitem_brt_vslot99 0xe063550
gameitem_brt_vslot100 0xe063560
gameitem_brt_vslot169 0xe02d280
gameitem_brt_vslot271 0xe03a490
gameitem_brt_vslot327 0xe03a4d0
gameitem_brt_vslot374 0xe03a420
gameitem_brt_vslot376 0xe03a460
gameitem_brt_vslot378 0xe03a4a0
gameitem_brt_vslot380 0xe03a4e0
gameitem_brt_vslot382 0xe03a510
gameitem_brt_vslot384 0xe03a330
weapon_slot208 0xe046370
weapon_slot209 0xe046340
weapon_slot216 0xe0462d0
weapon_slot233 0xe047b80
weapon_slot240 0xe047b10
brt_component_ctor 0xd077060
brt_component_dtor 0xd0773a0
brt_component_slot181 0xd077380
brt_component_slot190 0xd077390
brt_component_slot182 0xd0773c0
brt_component_slot191 0xd0773f0
brt_component_available_static 0xd077010
brt_component_slot70 0xd077420
brt_component_slot136 0xd0774b0
brt_component_input_bool_entry 0xd076410
brt_component_input_bool_reset_path 0xd076468
brt_component_input_bool_open_path 0xd0764a9
brt_component_input_bool_lookup_result 0xd07651b
brt_component_slot172 0xd078010
brt_component_state_entry 0xd078070
brt_component_state_backup_branch 0xd0780cb
brt_component_state_place_branch 0xd0780e9
brt_component_internal_state_entry 0xd078280
brt_component_internal_state_context_ok 0xd07835b
brt_component_internal_state_actor_ok 0xd07878c
brt_component_status_backup_builder 0xd078a00
brt_component_status_backup_fileline_a 0xd078b1a
brt_component_status_backup_blocked_a 0xd078c16
brt_component_status_backup_fileline_b 0xd078c8b
brt_component_status_backup_actor_ok 0xd078f30
brt_component_status_backup_fileline_c 0xd078fcb
brt_component_status_backup_action_dialog 0xd079031
brt_component_status_backup_commit 0xd07913e
brt_component_status_place_builder 0xd0791f0
brt_component_status_place_fileline 0xd07918e
brt_component_can_backup_fileline_a 0xd0792b7
brt_component_can_backup_call_a 0xd079302
brt_component_can_backup_fileline_b 0xd07943f
brt_component_can_backup_detail_a 0xd079757
brt_component_can_backup_detail_b 0xd079837
brt_component_status_misc_fileline 0xd07a220
brt_component_available_vslot290 0xd076f70
brt_component_nearby_lookup 0xd0779f0
brt_component_target_lookup 0xd079a90
brt_component_reset_entry 0xd079b50
brt_component_context_fail_return 0xd079d60
brt_component_validate_selection 0xd079d70
brt_component_activate_entry 0xd079f70
brt_component_cleanup_selection 0xd07a0f0
brt_component_status_finalize 0xd07a170
brt_component_set_status 0xd07a540
brt_component_slot196 0xd076bb0
brt_component_slot197 0xd076b10
brt_component_slot203 0xd081a10
brt_component_slot213 0xd081f10
brt_component_slot215 0xd081f20
brt_component_slot226 0xd081f50
brt_component_slot308 0xd081e70
backup_action_ctor 0xcf50940
backup_action_dtor 0xcf50980
backup_action_response_a 0xcf79c30
backup_action_response_b 0xcf79c40
backup_action_primary_check 0xcf52300
backup_action_secondary_check 0xcf52370
backup_action_perform 0xcf523e0
backup_action_method_gate 0xcf50d30
backup_action_slot187 0xcf50ad0
backup_action_slot199 0xcf50ba0
backup_action_slot200 0xcf50bb0
backup_action_persist_path 0xd052dc0
backup_action_register_a 0xd052c50
backup_action_register_b 0xd053010
backup_action_response_register_a 0xd052dd0
backup_action_response_register_b 0xd052ec0
place_action_primary_check 0xcf569c0
place_action_secondary_check 0xcf56a30
place_action_transform_state 0xcf56aa0
place_action_perform 0xcf56b50
place_action_method_gate 0xcf56220
place_action_response_a 0xcf79cb0
place_action_response_b 0xcf79cc0
place_action_ctor 0xcf55e90
place_action_dtor 0xcf55ea0
place_action_slot146 0xcf56050
place_action_slot150 0xcf55fb0
place_action_slot162 0xcf56090
place_action_slot163 0xcf560a0
place_action_register_a 0xd058050
place_action_register_b 0xd058360
replication_component_ctor 0xd101a00
replication_component_dtor 0xd101af0
replication_component_slot96 0xd1019b0
replication_component_slot198 0xd101600
replication_component_slot199 0xd101560
replication_component_thunk_d0 0xd101a50
replication_component_thunk_c8 0xd101aa0
replication_component_dtor_d0 0xd101b40
replication_component_dtor_c8 0xd101b90
replication_component_init 0xd101be0
replication_component_method 0xd101c20
replication_component_slot99 0xd114310
replication_component_slot100 0xd114320
replication_component_slot179 0xd101fb0
replication_component_slot180 0xd101e50
replication_component_slot205 0xd1023d0
replication_component_slot207 0xd102450
replication_component_slot209 0xd1021f0
replication_component_slot211 0xd102060
replication_component_slot222 0xd1027c0
replication_component_slot288 0xd102850
replication_component_slot402 0xd1027f0
replication_component_slot404 0xd102820
replication_component_slot406 0xd102860
replication_component_slot408 0xd102890
replication_component_slot410 0xd102720
replication_component_slot422 0xd102a70
replication_component_slot423 0xd102aa0
replication_component_slot519 0xd114330
replication_component_slot520 0xd114340
replication_component_slot599 0xd102ce0
replication_component_slot600 0xd102c10
replication_component_slot601 0xd102c00
replication_component_slot602 0xd102b20
replication_component_slot605 0xd102a80
replication_component_slot606 0xd102ac0
replication_component_slot614 0xd102a90
replication_component_slot615 0xd102af0
replication_component_slot677 0xd102dd0
replication_component_slot689 0xd102ea0
replication_component_slot690 0xd102ec0
server_request_basebackup_registration 0xd21f03c
POINTS

    printf 'continue\n'
  } >"$gdb_cmd_file"
}

echo "$(ts) BRT_DD_PERSISTENT_TRACE_WIDE supervisor_start host=$short_host container=$container log=$log"

while true; do
  pid="$(server_pid || true)"
  if [[ -z "$pid" ]]; then
    echo "$(ts) BRT_DD_PERSISTENT_TRACE_WIDE waiting_for_pid container=$container" >>"$log"
    sleep 5
    continue
  fi

  base="$(pie_base "$pid")"
  if [[ -z "$base" ]]; then
    echo "$(ts) BRT_DD_PERSISTENT_TRACE_WIDE no_pie_base pid=$pid" >>"$log"
    sleep 5
    continue
  fi

  write_gdb_cmd "$pid" "$base"
  echo "$(ts) BRT_DD_PERSISTENT_TRACE_WIDE attaching pid=$pid base=$base" >>"$log"
  sudo -n stdbuf -oL -eL gdb -q -p "$pid" -x "$gdb_cmd_file" >>"$log" 2>&1 &
  child_pid="$!"
  sudo -n rm -f "$gdb_pid_file" 2>/dev/null || rm -f "$gdb_pid_file" 2>/dev/null || true
  echo "$child_pid" >"$gdb_pid_file"

  status=0
  wait "$child_pid" || status="$?"
  echo "$(ts) BRT_DD_PERSISTENT_TRACE_WIDE gdb_exit pid=$pid status=$status" >>"$log"
  child_pid=""
  sudo -n rm -f "$gdb_pid_file" 2>/dev/null || rm -f "$gdb_pid_file" 2>/dev/null || true

  sleep 2
done
