#!/usr/bin/env bash
set -euo pipefail

action="${1:-status}"
container="${2:-dune_server-deep-desert-1}"
required_host="${DUNE_BRT_DD_TRACE_HOST:-kspls0}"
tracefs="${DUNE_TRACEFS:-/sys/kernel/tracing}"
group="${DUNE_BRT_DD_UPROBE_GROUP:-brt_dd}"
profile="${DUNE_BRT_DD_UPROBE_PROFILE:-minimal}"
skip_events_csv="${DUNE_BRT_DD_UPROBE_SKIP_EVENTS:-}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
source "$script_dir/lib/brt-dd-trace-guards.sh"
active_points_file=""

assert_host() {
  local short
  short="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
  if [[ "$short" != "$required_host" && "${DUNE_BRT_DD_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
    echo "ERROR: refusing to trace on host '$short'; required '$required_host'." >&2
    exit 1
  fi
}

server_pid() {
  docker top "$container" -eo pid,args 2>/dev/null |
    awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}'
}

sudo_write() {
  local path="$1"
  local value="$2"
  printf '%s\n' "$value" | sudo -n tee "$path" >/dev/null
}

sudo_append() {
  local path="$1"
  local value="$2"
  printf '%s\n' "$value" | sudo -n tee -a "$path" >/dev/null
}

event_path_for_pid() {
  local pid="$1" exe
  exe="$(sudo -n readlink "/proc/$pid/exe")"
  if [[ -e "$exe" ]]; then
    printf '%s\n' "$exe"
  else
    printf '/proc/%s/root%s\n' "$pid" "$exe"
  fi
}

events_minimal() {
  cat <<'EOF'
brt_tool_failreason_entry 0xe0430e0
brt_tool_canuse_entry 0xe0436e0
tool_action_slot103 0xe03e940
brt_component_input_bool_entry 0xd076410
brt_component_state_entry 0xd078070
brt_component_internal_state_entry 0xd078280
brt_component_activate_entry 0xd079f70
backup_action_primary_check 0xcf52300
backup_action_secondary_check 0xcf52370
backup_action_perform 0xcf523e0
place_action_primary_check 0xcf569c0
place_action_secondary_check 0xcf56a30
place_action_perform 0xcf56b50
server_request_basebackup_entry 0xd21efa0
EOF
}

events_decision() {
  cat <<'EOF'
tool_action_slot103 0xe03e940
tool_action_after_reason 0xe03e966
tool_action_return 0xe03e96a
tool_action_mode3_context 0xe03e987
tool_action_mode3_before_apply 0xe03e9d2
tool_action_other_mode_context 0xe03e9d9
tool_action_other_after_first_apply 0xe03ea34
brt_tool_failreason_entry 0xe0430e0
brt_action_invalid_reason_guard 0xe043236
brt_narrow_fail_reason 0xe04336e
brt_tool_canuse_entry 0xe0436e0
brt_narrow_canuse_empty_context 0xe043765
brt_candidate_actor_lookup_null 0xe043868
brt_action_dd_map_guard 0xe043872
brt_candidate_region_fail_join 0xe043874
brt_component_input_bool_entry 0xd076410
brt_component_state_entry 0xd078070
brt_component_internal_state_entry 0xd078280
brt_component_activate_entry 0xd079f70
backup_action_primary_check 0xcf52300
backup_action_perform 0xcf523e0
server_request_basebackup_entry 0xd21efa0
EOF
}

events_full() {
  # Current 1979201 / build-id caebf04f... BRT action surface. Offsets are
  # image/file-relative and match the patch scripts for this build.
  cat <<'EOF'
brt_tool_failreason_entry 0xe0430e0
brt_tool_canuse_entry 0xe0436e0
brt_action_invalid_reason_guard 0xe043236
brt_narrow_fail_reason 0xe04336e
brt_narrow_state_empty_context 0xe043533
brt_narrow_canuse_empty_context 0xe043765
brt_candidate_actor_lookup_null 0xe043868
brt_action_dd_map_guard 0xe043872
brt_candidate_region_fail_join 0xe043874
tool_action_pre_reason 0xe043010
tool_action_slot103 0xe03e940
tool_action_after_reason 0xe03e966
tool_action_return 0xe03e96a
tool_action_mode3_context 0xe03e987
tool_action_mode3_before_apply 0xe03e9d2
tool_action_other_mode_context 0xe03e9d9
tool_action_deep_guard_check 0xe03ee43
tool_action_deep_map_lookup_result 0xe03eebd
tool_action_missing_target 0xe03eede
tool_action_deep_fallback_entry 0xe03ef10
tool_action_deep_no_map_entry 0xe03efaf
tool_action_deep_payload_build 0xe03efe7
tool_action_deep_hash_branch 0xe03f00f
tool_action_deep_payload_ready 0xe03f076
tool_action_deep_assign_context 0xe03f143
tool_action_deep_deferred_result 0xe03f1d7
tool_action_final_gate 0xe03f272
tool_action_final_gate_after_check 0xe03f286
tool_action_final_apply 0xe03f28c
brt_component_input_bool_entry 0xd076410
brt_component_input_bool_open_path 0xd0764a9
brt_component_state_entry 0xd078070
brt_component_state_backup_branch 0xd0780cb
brt_component_state_place_branch 0xd0780e9
brt_component_internal_state_entry 0xd078280
brt_component_internal_state_context_ok 0xd07835b
brt_component_internal_state_actor_ok 0xd07878c
brt_component_status_backup_builder 0xd078a00
brt_component_status_backup_blocked_a 0xd078c16
brt_component_status_backup_commit 0xd07913e
brt_component_status_place_builder 0xd0791f0
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
place_action_primary_check 0xcf569c0
place_action_secondary_check 0xcf56a30
place_action_perform 0xcf56b50
place_action_method_gate 0xcf56220
server_request_basebackup_entry 0xd21efa0
server_request_basebackup_first_object_ok 0xd21efed
server_request_basebackup_second_object_ok 0xd21f031
server_request_basebackup_name_ref 0xd21f03d
server_request_basebackup_any_component_ok 0xd21f095
server_request_basebackup_payload_ready 0xd21f0bd
server_request_basebackup_candidate_loop 0xd21f188
server_request_basebackup_candidate_match 0xd21f1c8
EOF
}

events() {
  local points_file="${1:-}"
  if [[ -n "$points_file" ]]; then
    brt_dd_trace_emit_points "$points_file" "$profile"
    if [[ -n "${BRT_RPC_PLACE_OFFSET:-}" ]]; then
      printf 'brt_rpc_place_entry %s\n' "$BRT_RPC_PLACE_OFFSET"
    fi
    return 0
  fi
  case "$profile" in
    minimal) events_minimal ;;
    decision) events_decision ;;
    full) events_full ;;
    *)
      echo "ERROR: unknown DUNE_BRT_DD_UPROBE_PROFILE=$profile (use minimal|decision|full)" >&2
      exit 2
      ;;
  esac
  if [[ -n "${BRT_RPC_PLACE_OFFSET:-}" ]]; then
    printf 'brt_rpc_place_entry %s\n' "$BRT_RPC_PLACE_OFFSET"
  fi
}

event_is_skipped() {
  local event_name="$1" entry
  [[ -n "$skip_events_csv" ]] || return 1
  IFS=',' read -ra entries <<<"$skip_events_csv"
  for entry in "${entries[@]}"; do
    entry="${entry#"${entry%%[![:space:]]*}"}"
    entry="${entry%"${entry##*[![:space:]]}"}"
    if [[ "$entry" == "$event_name" ]]; then
      return 0
    fi
  done
  return 1
}

remove_events() {
  local name
  if sudo -n test -d "$tracefs/events/$group" 2>/dev/null; then
    sudo -n find "$tracefs/events/$group" -mindepth 2 -maxdepth 2 -name enable -print 2>/dev/null |
      while IFS= read -r enable_file; do
        sudo_write "$enable_file" 0 || true
      done
  fi
  while read -r name; do
    [[ -n "$name" ]] || continue
    sudo_append "$tracefs/uprobe_events" "-:$group/$name" || true
  done < <(sudo -n awk -v group="$group" '$1 ~ "^[pr]:" group "/" { split($1, parts, "/"); print parts[2] }' "$tracefs/uprobe_events" 2>/dev/null || true)
}

arm() {
  assert_host
  [[ -w "$tracefs/uprobe_events" || -w "$tracefs/trace" ]] || sudo -n true
  local pid event_path name offset fetch_args
  pid="$(server_pid)"
  [[ -n "$pid" ]] || { echo "ERROR: no server process found for $container" >&2; exit 1; }
  active_points_file="$(brt_dd_trace_points_or_stale_override "$pid" "brt-dd-uprobe-watch/$profile")"
  event_path="$(event_path_for_pid "$pid")"
  sudo -n test -e "$event_path" || { echo "ERROR: event binary path not found: $event_path" >&2; exit 1; }

  remove_events
  sudo_write "$tracefs/tracing_on" 0 || true
  sudo_write "$tracefs/trace" "" || true

  events_file="$(mktemp)"
  events "$active_points_file" >"$events_file"
  [[ -s "$events_file" ]] || { rm -f "$events_file"; echo "ERROR: no trace points for profile=$profile" >&2; exit 1; }

  while read -r name offset fetch_args; do
    [[ -n "$name" && -n "$offset" ]] || continue
    event_is_skipped "$name" && continue
    if [[ -n "${fetch_args:-}" ]]; then
      sudo_append "$tracefs/uprobe_events" "p:$group/$name $event_path:$offset $fetch_args"
    else
      sudo_append "$tracefs/uprobe_events" "p:$group/$name $event_path:$offset"
    fi
  done <"$events_file"

  while read -r name _; do
    [[ -n "$name" ]] || continue
    event_is_skipped "$name" && continue
    sudo_write "$tracefs/events/$group/$name/enable" 1
  done <"$events_file"
  rm -f "$events_file"

  sudo_write "$tracefs/tracing_on" 1
  echo "armed tracefs uprobes group=$group profile=$profile container=$container pid=$pid binary=$event_path points=${active_points_file:-builtins} skip_events=${skip_events_csv:-none}"
  echo "dump with: $0 dump $container"
  echo "stop with: $0 stop $container"
}

dump() {
  sudo -n awk '$0 ~ /^[[:space:]][^#].*:[[:space:]][[:alnum:]_]+:/ {print}' "$tracefs/trace" |
    tail -n "${DUNE_BRT_DD_UPROBE_DUMP_LINES:-200}"
}

status() {
  local pid enabled_names inferred_profile
  pid="$(server_pid || true)"
  enabled_names=""
  inferred_profile="not-armed"
  if sudo -n test -d "$tracefs/events/$group" 2>/dev/null; then
    enabled_names="$(
      sudo -n find "$tracefs/events/$group" -mindepth 2 -maxdepth 2 -name enable -print 2>/dev/null |
        while IFS= read -r enable_file; do
          [[ "$(sudo -n cat "$enable_file" 2>/dev/null || true)" == "1" ]] || continue
          basename "$(dirname "$enable_file")"
        done |
        sort |
        paste -sd, -
    )"
    case ",$enabled_names," in
      *,brt_action_failreason_entry,*brt_action_place_can_place_entry,*|*,brt_action_place_can_place_entry,*brt_action_failreason_entry,*)
        inferred_profile="brt"
        ;;
      *,brt_action_place_can_place_entry,*|*,brt_action_place_place_entry,*|*,brt_action_place_commit_entry,*)
        inferred_profile="place"
        ;;
      *,brt_action_canuse_entry,*|*,brt_action_state_entry,*|*,brt_action_failreason_entry,*)
        inferred_profile="hotbar-action"
        ;;
      *,brt_rpc_exec_server_request_basebackup,*|*,brt_rpc_impl_server_request_basebackup,*|*,perform_can_be_placed_entry,*)
        inferred_profile="rpc-placement"
        ;;
      ,)
        inferred_profile="disabled"
        ;;
      *)
        inferred_profile="custom"
        ;;
    esac
  fi
  echo "container=$container pid=${pid:-missing} group=$group requested_profile=$profile inferred_profile=$inferred_profile tracefs=$tracefs"
  [[ -z "$enabled_names" ]] || echo "enabled_events=$enabled_names"
  if sudo -n test -d "$tracefs/events/$group" 2>/dev/null; then
    sudo -n find "$tracefs/events/$group" -mindepth 2 -maxdepth 2 -name enable -print 2>/dev/null |
      while IFS= read -r enable_file; do
        printf '%s=' "$enable_file"
        sudo -n cat "$enable_file"
      done
  else
    echo "not armed"
  fi
  dump || true
}

stop() {
  assert_host
  remove_events
  echo "stopped tracefs uprobes group=$group"
}

case "$action" in
  arm) arm ;;
  dump) dump ;;
  status) status ;;
  stop) stop ;;
  *)
    echo "usage: $0 arm|dump|status|stop [container]" >&2
    exit 2
    ;;
esac
