#!/usr/bin/env bash
set -euo pipefail

action="${1:-status}"
env_file="${2:-.env}"
container="${DUNE_BRT_DD_CANARY_CONTAINER:-dune_server-deep-desert-1}"
required_host="${DUNE_BRT_DD_CANARY_HOST:-kspls0}"
test_kind="${DUNE_BRT_DD_CANARY_TEST_KIND:-mixed}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
trace_log="${DUNE_BRT_DD_CANARY_TRACE_LOG:-/tmp/brt-dd-live-canary-trace.log}"
trace_classification_json="${DUNE_BRT_DD_CANARY_TRACE_CLASSIFICATION_JSON:-${trace_log}.classification.json}"
trace_profile="${DUNE_BRT_DD_CANARY_PROFILE:-brt}"
default_trace_skip_events="brt_action_method_failure_reason,brt_action_state_empty_context,brt_action_canuse_empty_context,brt_action_canuse_actor_lookup_null,brt_action_canuse_map_area_guard,brt_action_canuse_region_fail_join,brt_action_invalid_map_reason_guard,brt_rpc_request_mode_branch,perform_invalid_map_site_a,perform_invalid_map_site_b,perform_invalid_map_site_c,perform_invalid_map_site_d"
trace_skip_events="${DUNE_BRT_DD_CANARY_SKIP_EVENTS:-$default_trace_skip_events}"
baseline_file="${DUNE_BRT_DD_CANARY_BASELINE:-/tmp/brt-dd-live-canary-db-baseline.txt}"
state_file="${DUNE_BRT_DD_CANARY_STATE:-/tmp/brt-dd-live-canary-state.env}"

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_CANARY_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "ERROR: refusing to run canary on host '$short_host'; required '$required_host'." >&2
  exit 1
fi

cd "$repo_root"

db_name="$(
  awk -F= '
    /^DUNE_GAME_DB_NAME=/ {
      sub(/^[^=]*=/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$env_file"
)"
db_name="${db_name:-dune_sb_1_4_5_0}"

compose_cmd() {
  local files file
  IFS=: read -ra files <<<"$(./scripts/compose-files.sh "$env_file")"
  printf 'docker compose'
  for file in "${files[@]}"; do
    printf ' -f %q' "$file"
  done
  printf ' --env-file %q' "$env_file"
}

psql_readonly() {
  local compose
  compose="$(compose_cmd)"
  eval "$compose exec -T postgres psql -U dune -d \"\$db_name\" -P pager=off -v ON_ERROR_STOP=1 -qAt" <<'SQL'
select 'function_calls=' || coalesce(
  string_agg(funcname || '=' || calls::text, ' ' order by funcname),
  'none'
)
from pg_stat_user_functions
where schemaname='dune'
  and funcname like 'base_backup%';
select 'base_backups=' || count(*) from dune.base_backups;
select 'linked_actors=' || count(*) from dune.base_backup_linked_actors;
select 'latest=' || coalesce(
  string_agg(id::text || ':' || player_id::text || ':' || base_backup_name, ',' order by id desc),
  'none'
)
from (
  select id, player_id, base_backup_name
  from dune.base_backups
  order by id desc
  limit 8
) recent;
select 'shim_events=' || count(*) from dune.brt_dd_shim_events;
select 'latest_shim_events=' || coalesce(
  string_agg(
    id::text || ':' || event || ':backup=' || coalesce(backup_id::text, 'null') ||
      ':player=' || coalesce(player_id::text, 'null') ||
      ':map=' || coalesce(player_map, 'null') ||
      ':details=' || left(details::text, 220),
    ' | ' order by id desc
  ),
  'none'
)
from (
  select id, event, backup_id, player_id, player_map, details
  from dune.brt_dd_shim_events
  order by id desc
  limit 12
) recent;
SQL
}

psql_players() {
  local compose
  compose="$(compose_cmd)"
  eval "$compose exec -T postgres psql -U dune -d \"\$db_name\" -P pager=off -v ON_ERROR_STOP=1 -qAt" <<'SQL'
select coalesce(
  string_agg(character_name || ':' || online_status || ':partition=' || previous_server_partition_id::text, ',' order by character_name),
  'none'
)
from dune.player_state
where online_status='Online';
SQL
}

load_state() {
  [[ -s "$state_file" ]] || return 0
  # shellcheck disable=SC1090
  source "$state_file"
  trace_profile="${TRACE_PROFILE:-$trace_profile}"
  test_kind="${TEST_KIND:-$test_kind}"
}

save_state() {
  {
    printf 'TRACE_PROFILE=%q\n' "$trace_profile"
    printf 'TEST_KIND=%q\n' "$test_kind"
    printf 'CONTAINER=%q\n' "$container"
    printf 'TRACE_LOG=%q\n' "$trace_log"
    printf 'SAVED_AT=%q\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  } >"$state_file"
}

print_db_delta() {
  local before="$1" after="$2"
  [[ -s "$before" && -s "$after" ]] || return 0
  awk '
    function load_counts(line, arr,    n, i, kv) {
      sub(/^function_calls=/, "", line)
      n = split(line, parts, " ")
      for (i = 1; i <= n; i++) {
        split(parts[i], kv, "=")
        if (kv[1] != "" && kv[2] ~ /^[0-9]+$/) arr[kv[1]] = kv[2] + 0
      }
    }
    function split_value(line,    idx) {
      idx = index(line, "=")
      if (idx == 0) return ""
      return substr(line, idx + 1)
    }
    FNR == 1 && /^function_calls=/ {
      if (ARGIND == 1) load_counts($0, before)
      if (ARGIND == 2) load_counts($0, after)
    }
    /^base_backups=/ {
      if (ARGIND == 1) before_scalar["base_backups"] = split_value($0) + 0
      if (ARGIND == 2) after_scalar["base_backups"] = split_value($0) + 0
    }
    /^linked_actors=/ {
      if (ARGIND == 1) before_scalar["linked_actors"] = split_value($0) + 0
      if (ARGIND == 2) after_scalar["linked_actors"] = split_value($0) + 0
    }
    /^shim_events=/ {
      if (ARGIND == 1) before_scalar["shim_events"] = split_value($0) + 0
      if (ARGIND == 2) after_scalar["shim_events"] = split_value($0) + 0
    }
    /^latest=/ {
      if (ARGIND == 1) before_latest = split_value($0)
      if (ARGIND == 2) after_latest = split_value($0)
    }
    END {
      for (k in after) {
        delta = after[k] - before[k]
        if (delta != 0) {
          out = out sprintf("%s%s=%+d", (out == "" ? "" : " "), k, delta)
        }
      }
      if (out == "") out = "none"
      print "function_call_delta=" out
      scalar_out = ""
      for (k in after_scalar) {
        delta = after_scalar[k] - before_scalar[k]
        if (delta != 0) {
          scalar_out = scalar_out sprintf("%s%s=%+d", (scalar_out == "" ? "" : " "), k, delta)
        }
      }
      if (scalar_out == "") scalar_out = "none"
      print "table_count_delta=" scalar_out
      if (before_latest != after_latest) {
        print "latest_changed=true"
        print "latest_before=" before_latest
        print "latest_after=" after_latest
      } else {
        print "latest_changed=false"
      }
    }
  ' "$before" "$after"
}

print_trace_summary() {
  local trace_file="$1"
  if [[ ! -s "$trace_file" ]]; then
    echo "trace_event_count=0"
    echo "trace_hotbar_events=0"
    echo "trace_backup_events=0"
    echo "trace_place_events=0"
    echo "trace_rpc_events=0"
    echo "trace_summary=none"
    return 0
  fi

  awk '
    /brt_action_canuse_/ || /brt_action_state_/ || /brt_action_failreason/ || /brt_action_method_failure_reason/ ||
    /brt_component_/ || /brt_delegate_/ {
      hotbar++
    }
    /brt_component_.*backup/ || /brt_component_use_/ || /brt_backup_/ {
      backup++
    }
    /brt_component_can_backup_blueprint_/ {
      can_backup_blueprint++
    }
    /brt_component_can_backup_blueprint_status_text_/ {
      can_backup_blueprint_status_text++
    }
    /brt_backup_perform_entry/ {
      backup_perform++
    }
    /brt_backup_.*fail|brt_backup_.*disabled_path|brt_backup_.*guard/ {
      backup_gate++
    }
    /brt_action_place_/ || /perform_can_be_placed/ || /perform_invalid_map_site_/ {
      place++
    }
    /brt_rpc_/ || /server_request_basebackup_/ {
      rpc++
    }
    /brt_rpc_.*building_blueprint/ {
      building_blueprint_rpc++
    }
    /_args:/ {
      args++
    }
    /brt_rpc_impl_server_request_basebackup_args:.*rsi=0x44.*rdx=0x8/ ||
    /server_request_basebackup_entry/ ||
    /brt_rpc_request_handler_args:.*rsi=0x41/ ||
    /brt_rpc_request_handler_args:.*rsi=0x44/ {
      restore_preview_rpc++
    }
    /brt_rpc_request_placeable_load_path/ {
      placeable_load_path++
    }
    /brt_rpc_request_immediate_path/ {
      immediate_path++
    }
    {
      total++
    }
    END {
      print "trace_event_count=" total + 0
      print "trace_hotbar_events=" hotbar + 0
      print "trace_backup_events=" backup + 0
      print "trace_can_backup_blueprint_events=" can_backup_blueprint + 0
      print "trace_can_backup_blueprint_status_text_events=" can_backup_blueprint_status_text + 0
      print "trace_backup_perform_events=" backup_perform + 0
      print "trace_backup_gate_events=" backup_gate + 0
      print "trace_place_events=" place + 0
      print "trace_rpc_events=" rpc + 0
      print "trace_building_blueprint_rpc_events=" building_blueprint_rpc + 0
      print "trace_arg_events=" args + 0
      print "trace_restore_preview_rpc_events=" restore_preview_rpc + 0
      print "trace_rpc_placeable_load_path_events=" placeable_load_path + 0
      print "trace_rpc_immediate_path_events=" immediate_path + 0
      if (backup_perform > 0) {
        print "trace_summary=server_backup_path_reached"
      } else if (building_blueprint_rpc > 0) {
        print "trace_summary=server_building_blueprint_rpc_reached"
      } else if (can_backup_blueprint > 0) {
        print "trace_summary=server_can_backup_blueprint_reached"
      } else if (restore_preview_rpc > 0 && backup == 0) {
        print "trace_summary=restore_preview_rpc_only"
      } else if (rpc > 0) {
        print "trace_summary=server_rpc_reached"
      } else if (place > 0) {
        print "trace_summary=server_place_path_without_rpc"
      } else if (hotbar > 0) {
        print "trace_summary=server_tool_checks_only"
      } else if (total > 0) {
        print "trace_summary=server_other_brt_events"
      } else {
        print "trace_summary=none"
      }
    }
  ' "$trace_file"
}

print_attempt_diagnosis() {
  local delta_file="$1" trace_summary_file="$2" trace_status_file="${3:-}"
  local function_delta table_delta latest_changed trace_summary trace_count
  function_delta="$(awk '/^function_call_delta=/ {sub(/^[^=]*=/, ""); print; exit}' "$delta_file")"
  table_delta="$(awk '/^table_count_delta=/ {sub(/^[^=]*=/, ""); print; exit}' "$delta_file")"
  latest_changed="$(awk '/^latest_changed=/ {sub(/^[^=]*=/, ""); print; exit}' "$delta_file")"
  trace_summary="$(awk '/^trace_summary=/ {sub(/^[^=]*=/, ""); print; exit}' "$trace_summary_file")"
  trace_count="$(awk '/^trace_event_count=/ {sub(/^[^=]*=/, ""); print; exit}' "$trace_summary_file")"

  function_delta="${function_delta:-unknown}"
  table_delta="${table_delta:-unknown}"
  latest_changed="${latest_changed:-unknown}"
  trace_summary="${trace_summary:-unknown}"
  trace_count="${trace_count:-0}"

  echo "== diagnosis =="
  if [[ -n "$trace_status_file" ]] && ! awk '/^enabled_events=/ {found=1} END {exit(found ? 0 : 1)}' "$trace_status_file"; then
    echo "diagnosis=trace_not_armed_at_collect"
    echo "next_focus=discard_stale_trace_window_and_rearm_before_next_confirmed_backup_test"
    return 0
  fi
  if [[ "$function_delta" == "none" && "$table_delta" == "none" && "$latest_changed" == "false" && "$trace_count" == "0" ]]; then
    echo "diagnosis=no_server_evidence"
    echo "next_focus=client_or_input_path_before_server_brt"
  elif [[ "$trace_summary" == "server_tool_checks_only" && "$function_delta" == "none" ]]; then
    echo "diagnosis=server_tool_checks_without_db"
    echo "next_focus=tool_action_or_invalid_map_gate"
  elif [[ "$trace_summary" == "server_place_path_without_rpc" && "$function_delta" == "none" ]]; then
    echo "diagnosis=server_place_validation_without_rpc_or_db"
    echo "next_focus=perform_can_be_placed_or_place_commit_gate"
  elif [[ "$trace_summary" == "server_backup_path_reached" && "$function_delta" == "none" ]]; then
    echo "diagnosis=server_backup_path_without_db_save"
    echo "next_focus=backup_action_validation_or_confirm_gate"
  elif [[ "$trace_summary" == "server_building_blueprint_rpc_reached" && "$function_delta" == "none" ]]; then
    echo "diagnosis=building_blueprint_rpc_reached_without_db_save"
    echo "next_focus=building_blueprint_copydata_or_backup_action_gate"
  elif [[ "$trace_summary" == "server_building_blueprint_rpc_reached" ]]; then
    echo "diagnosis=building_blueprint_rpc_reached_with_db_activity"
    echo "next_focus=inspect_building_blueprint_rpc_delta"
  elif [[ "$trace_summary" == "server_can_backup_blueprint_reached" ]]; then
    echo "diagnosis=server_can_backup_blueprint_reached_without_backup_perform"
    echo "next_focus=component_selected_context_or_backup_action_gate"
  elif [[ "$trace_summary" == "restore_preview_rpc_only" ]]; then
    echo "diagnosis=restore_preview_rpc_reached_without_backup_perform"
    echo "next_focus=client_backup_mode_or_server_action_selector"
  elif [[ "$trace_summary" == "server_rpc_reached" && "$function_delta" == "none" ]]; then
    echo "diagnosis=rpc_reached_without_db_change"
    echo "next_focus=server_rpc_payload_or_early_reject"
  elif [[ "$function_delta" == *"base_backup_save="* || "$function_delta" == *"base_backup_save_from_totem="* ]]; then
    echo "diagnosis=backup_save_db_path_reached"
    echo "next_focus=verify_created_backup_and_client_feedback"
  elif [[ "$function_delta" == *"base_backup_finish_placing="* || "$function_delta" == *"base_backup_get_actors_to_spawn="* ]]; then
    echo "diagnosis=restore_place_db_path_reached"
    echo "next_focus=verify_actor_spawn_finish_and_client_feedback"
  elif [[ "$function_delta" == *"base_backup_get_data="* || "$function_delta" == *"base_backup_get_available_backups="* || "$function_delta" == *"base_backup_get_totem_data="* ]]; then
    echo "diagnosis=metadata_preview_db_path_reached_without_spawn_or_commit"
    echo "next_focus=client_place_confirmation_or_server_spawn_request_gate"
  else
    echo "diagnosis=mixed_brt_activity"
    echo "next_focus=inspect_trace_and_db_deltas"
  fi
}

snapshot() {
  local game_pid
  game_pid="$(docker top "$container" -eo pid,args 2>/dev/null | awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}')"
  echo "== host =="
  hostname
  date -u '+utc=%Y-%m-%dT%H:%M:%SZ'
  echo "== dd1 process =="
  docker inspect "$container" --format 'name={{.Name}} pid={{.State.Pid}} status={{.State.Status}} started={{.State.StartedAt}} restart={{.RestartCount}} oom={{.State.OOMKilled}}'
  echo "game_pid=${game_pid:-missing}"
  echo "== dd1 players =="
  psql_players
  echo "== db snapshot =="
  psql_readonly
  echo "== trace status =="
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh status "$container" || true
}

arm() {
  snapshot
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh arm "$container"
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh status "$container" | sed -n '1,8p'
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh status "$container" |
      { rg -o 'brt_component_can_backup_blueprint_[a-z_]+(_args)?|brt_rpc_(exec|impl)_server_request_building_blueprint(_args)?|brt_rpc_impl_server_request_basebackup(_args)?|brt_backup_perform_entry' || true; } |
      sort -u |
      sed 's/^/key_probe_enabled=/'
  echo "armed=true"
  echo "profile=$trace_profile"
  echo "test_kind=$test_kind"
  echo "trace_log=$trace_log"
  echo "trace_classification_json=$trace_classification_json"
  psql_readonly >"$baseline_file"
  save_state
  echo "db_baseline=$baseline_file"
  case "$test_kind" in
    backup)
      echo "next: perform exactly one BRT backup attempt in DD, then run: $0 collect $env_file"
      ;;
    restore|place)
      echo "next: perform exactly one BRT restore/place attempt in DD, then run: $0 collect $env_file"
      ;;
    *)
      echo "next: perform one BRT backup attempt and one BRT restore/place attempt, then run: $0 collect $env_file"
      ;;
  esac
}

ready() {
  echo "== pre-arm cleanup collect: not a user test =="
  collect prearm
  echo "== arm fresh test window =="
  arm
  printf '\a\a\a'
  echo "READY_FOR_BRT_TEST"
  echo "Canaries armed. Perform the BRT attempt now, then report: tested."
}

ready_backup() {
  DUNE_BRT_DD_CANARY_TEST_KIND=backup test_kind=backup
  DUNE_BRT_DD_CANARY_PROFILE=backup trace_profile=backup
  echo "== pre-arm cleanup collect: not a user test =="
  collect prearm
  echo "== arm fresh backup-only test window =="
  arm
  printf '\a\a\a'
  echo "READY_FOR_BRT_BACKUP_TEST"
  echo "Canaries armed. Perform exactly one BRT backup attempt in DD now, then report: tested."
}

collect() {
  local collect_mode="${1:-confirmed}"
  local current_db delta_file trace_summary_file trace_status_file
  load_state
  current_db="$(mktemp)"
  delta_file="$(mktemp)"
  trace_summary_file="$(mktemp)"
  trace_status_file="$(mktemp)"
  echo "== db snapshot =="
  psql_readonly | tee "$current_db"
  if [[ -s "$baseline_file" ]]; then
    echo "== db delta since arm =="
    print_db_delta "$baseline_file" "$current_db" | tee "$delta_file"
  fi
  echo "== trace status =="
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh status "$container" | tee "$trace_status_file" | sed -n '1,12p'
  echo "== uprobe dump =="
  DUNE_BRT_DD_UPROBE_DUMP_LINES="${DUNE_BRT_DD_UPROBE_DUMP_LINES:-300}" \
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh dump "$container" | tee "$trace_log"
  echo "== trace summary =="
  print_trace_summary "$trace_log" | tee "$trace_summary_file"
  echo "== trace rpc classification =="
  scripts/classify-brt-dd-trace.py "$trace_log" --format json | tee "$trace_classification_json"
  if [[ "$collect_mode" == "prearm" ]]; then
    echo "diagnosis=prearm_cleanup_not_user_test"
    echo "next_focus=arm_fresh_window_and_wait_for_confirmed_test"
  elif [[ -s "$delta_file" ]]; then
    print_attempt_diagnosis "$delta_file" "$trace_summary_file" "$trace_status_file"
  fi
  rm -f "$current_db" "$delta_file" "$trace_summary_file" "$trace_status_file"
  echo "trace_log=$trace_log"
}

stop() {
  load_state
  DUNE_BRT_DD_UPROBE_PROFILE="$trace_profile" \
  DUNE_BRT_DD_UPROBE_SKIP_EVENTS="$trace_skip_events" \
    ./scripts/brt-dd-uprobe-watch.sh stop "$container"
}

case "$action" in
  arm) arm ;;
  ready) ready ;;
  ready-backup) ready_backup ;;
  collect) collect confirmed ;;
  tested) collect confirmed ;;
  snapshot|status) snapshot ;;
  stop) stop ;;
  *)
    echo "usage: $0 arm|ready|ready-backup|collect|tested|snapshot|status|stop [env_file]" >&2
    exit 2
    ;;
esac
