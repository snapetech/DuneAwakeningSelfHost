#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="${DUNE_WORKSPACE_ROOT:-$(cd "$script_dir/.." && pwd)}"

workspace_script() {
  local name="$1"
  if [ -f "/workspace/scripts/$name" ]; then
    printf '%s\n' "/workspace/scripts/$name"
    return 0
  fi
  printf '%s\n' "$workspace_root/scripts/$name"
}

main() {
  local server_root="${DUNE_SERVER_ROOT:-/home/dune/server}"
  local dune_home="${DUNE_HOME:-/home/dune}"
  local dry_run="${DUNE_RUN_SERVER_SAFE_DRY_RUN:-false}"

  install_workspace_tools "$dry_run"
  install_cert
  install_building_piece_limit_patch "$server_root" "$dry_run"
  install_landsraad_vendor_faction_gate_patch "$server_root" "$dry_run"
  install_brt_dd_buildable_map_region_pak_patch "$server_root" "$dry_run"
  install_subfief_cap_binary_patch "$server_root" "$dry_run"
  install_brt_dd_invalid_map_binary_patch "$server_root" "$dry_run"
  install_brt_dd_action_gate_binary_patch "$server_root" "$dry_run"
  install_brt_dd_narrow_tool_state_binary_patch "$server_root" "$dry_run"
  install_brt_dd_tool_enable_binary_patch "$server_root" "$dry_run"
  install_user_configs "$server_root"
  sync_default_game_from_usergame "$server_root"
  install_server_login_password "$server_root" "$@"
  load_workspace_value DUNE_SERVER_DISPLAY_NAME
  load_workspace_value DUNE_SERVER_STARTUP_EXECCMDS
  install_server_display_name "$server_root" "$@"

  mkdir -p "$server_root/DuneSandbox/Saved/UserSettings"
  if [ "$dry_run" != "true" ]; then
    chown -R dune:nogroup "$server_root/DuneSandbox/Saved"
  fi

  mkdir -p "$dune_home/.config/Epic/Unreal Engine/Engine"
  local config_path="$dune_home/.config/Epic/Unreal Engine/Engine/Config"
  [ -d "$config_path" ] && [ ! -L "$config_path" ] && rm -rf "$config_path"
  ln -sfn "$server_root/DuneSandbox/Saved/UserSettings" "$config_path"

  cd "$server_root"

  load_workspace_bool DUNE_DISABLE_MULTIHOME
  load_workspace_bool DUNE_FORCE_PRIVATE_IGW_BIND_ADDRESS

  local pod_ip="${POD_IP:-127.0.0.1}"
  local args=()
  local arg
  local login_prefix='-ini:engine:[ConsoleVariables]:Bgd.ServerLoginPassword='
  for arg in "$@"; do
    if [ "$arg" = '-MultiHome=$POD_IP' ] && [ "${DUNE_DISABLE_MULTIHOME:-false}" = "true" ]; then
      continue
    elif [ "$arg" = '-MultiHome=$POD_IP' ]; then
      args+=("-MultiHome=$pod_ip")
    elif [[ "${arg:0:${#login_prefix}}" == "$login_prefix" ]] && [ -n "${DUNE_SERVER_LOGIN_PASSWORD:-}" ]; then
      args+=("-ini:engine:[ConsoleVariables]:Bgd.ServerLoginPassword=${DUNE_SERVER_LOGIN_PASSWORD}")
    else
      args+=("$arg")
    fi
  done
  if [ "${DUNE_FORCE_PRIVATE_IGW_BIND_ADDRESS:-false}" = "true" ]; then
    args+=("-IGWBindAddress=$pod_ip")
  fi
  if [ -n "${DUNE_SERVER_STARTUP_EXECCMDS:-}" ]; then
    args+=("-ExecCmds=${DUNE_SERVER_STARTUP_EXECCMDS}")
  fi

  if [ "$dry_run" = "true" ]; then
    printf '%s\0' "${args[@]}" > "${DUNE_RUN_SERVER_SAFE_ARGS_OUT:-/tmp/run_server_safe.args}"
    return 0
  fi

  exec runuser -u dune -- ./DuneSandboxServer.sh "${args[@]}"
}

load_workspace_bool() {
  local name="$1"
  [ -z "${!name:-}" ] || return 0
  [ -f /workspace/.env ] || return 0
  if grep -Eq "^[[:space:]]*${name}=true[[:space:]]*$" /workspace/.env; then
    printf -v "$name" true
    export "$name"
  fi
}

load_workspace_value() {
  local name="$1"
  local value
  [ -z "${!name:-}" ] || return 0
  [ -f /workspace/.env ] || return 0
  value="$(awk -F= -v key="$name" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "", $0)
      print $0
    }
  ' /workspace/.env | tail -n 1)"
  [ -n "$value" ] || return 0
  printf -v "$name" '%s' "$value"
  export "$name"
}

install_workspace_tools() {
  local dry_run="$1"

  install_workspace_tool "rg" \
    "${DUNE_INSTALL_RG_ENABLED:-true}" \
    "${DUNE_RG_SOURCE:-/workspace/vendor/bin/rg}" \
    "${DUNE_RG_TARGET:-/usr/local/bin/rg}" \
    "$dry_run"
  install_workspace_tool "busybox" \
    "${DUNE_INSTALL_BUSYBOX_ENABLED:-true}" \
    "${DUNE_BUSYBOX_SOURCE:-/workspace/vendor/bin/busybox}" \
    "${DUNE_BUSYBOX_TARGET:-/usr/local/bin/busybox}" \
    "$dry_run"
  install_workspace_tool "jq" \
    "${DUNE_INSTALL_JQ_ENABLED:-true}" \
    "${DUNE_JQ_SOURCE:-/workspace/vendor/bin/jq}" \
    "${DUNE_JQ_TARGET:-/usr/local/bin/jq}" \
    "$dry_run"
  install_workspace_tool "curl" \
    "${DUNE_INSTALL_CURL_ENABLED:-true}" \
    "${DUNE_CURL_SOURCE:-/workspace/vendor/bin/curl}" \
    "${DUNE_CURL_TARGET:-/usr/local/bin/curl}" \
    "$dry_run"
}

install_workspace_tool() {
  local name="$1"
  local enabled="$2"
  local source="$3"
  local target="$4"
  local dry_run="$5"

  [ "$enabled" = "true" ] || return 0
  [ -f "$source" ] || return 0
  [ -x "$source" ] || return 0
  if [ "$dry_run" = "true" ]; then
    printf '%s install available: %s -> %s\n' "$name" "$source" "$target"
    return 0
  fi
  if command -v "$name" >/dev/null 2>&1; then
    return 0
  fi
  mkdir -p "$(dirname "$target")"
  cp "$source" "$target"
  chmod 0755 "$target"
}

install_user_configs() {
  local server_root="$1"
  local source_dir=/workspace/config
  local user_game_config="${DUNE_USERGAME_CONFIG_PATH:-${source_dir}/UserGame.ini}"
  local user_engine_config="${DUNE_USERENGINE_CONFIG_PATH:-${source_dir}/UserEngine.ini}"
  local config_dir="$server_root/DuneSandbox/Saved/Config/LinuxServer"
  local user_settings_dir="$server_root/DuneSandbox/Saved/UserSettings"
  mkdir -p "$config_dir"
  mkdir -p "$user_settings_dir"

  copy_user_config "$user_engine_config" "${config_dir}/Engine.ini"
  copy_user_config "$user_engine_config" "${user_settings_dir}/UserEngine.ini"
  copy_user_config "$user_game_config" "${config_dir}/Game.ini"
  copy_user_config "$user_game_config" "${user_settings_dir}/UserGame.ini"
}

copy_user_config() {
  local source="$1"
  local target="$2"
  [ -f "$source" ] || return 0
  cp "$source" "$target"
}

sync_default_game_from_usergame() {
  local server_root="$1"
  local source_dir=/workspace/config
  local user_game_config="${DUNE_USERGAME_CONFIG_PATH:-${source_dir}/UserGame.ini}"
  local default_game_ini="$server_root/DuneSandbox/Config/DefaultGame.ini"
  [ -f "$user_game_config" ] || return 0
  [ -f "$default_game_ini" ] || return 0

  local keys="${DUNE_DEFAULTGAME_SYNC_KEYS:-m_BaseBackupToolMapRestriction m_BaseBackupToolTimeRestrictionInSeconds m_BaseBackupMaxExtensions m_bBuildingRestrictionLimitsEnabled m_MaxLandclaimSegmentsPerMap m_MaxNumLandclaimSegments}"
  local key value
  for key in $keys; do
    value="$(extract_ini_assignment "$user_game_config" "$key")"
    if [ -n "$value" ]; then
      replace_or_append_ini_assignment "$default_game_ini" "$key" "$value"
    fi
    sync_ini_operator_assignments "$user_game_config" "$default_game_ini" "$key"
  done
}

extract_ini_assignment() {
  local ini_file="$1"
  local key="$2"
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*;?[[:space:]]*" key "=" {
      line = $0
      sub(/^[[:space:]]*;?[[:space:]]*/, "", line)
      value = line
    }
    END {
      if (value != "") {
        print value
      }
    }
  ' "$ini_file"
}

replace_or_append_ini_assignment() {
  local ini_file="$1"
  local key="$2"
  local assignment="$3"
  local escaped_key
  escaped_key="$(printf '%s' "$key" | sed -e 's/[][\.^$*+?{}|()]/\\&/g')"
  if grep -Eq "^[[:space:]]*;?[[:space:]]*${escaped_key}=" "$ini_file"; then
    sed -i -E "s|^[[:space:]]*;?[[:space:]]*${escaped_key}=.*|${assignment}|" "$ini_file"
  else
    printf '\n%s\n' "$assignment" >> "$ini_file"
  fi
}

extract_ini_operator_assignments() {
  local ini_file="$1"
  local key="$2"
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*;?[[:space:]]*[!+.-]" key "=" {
      line = $0
      sub(/^[[:space:]]*;?[[:space:]]*/, "", line)
      print line
    }
  ' "$ini_file"
}

sync_ini_operator_assignments() {
  local source_ini="$1"
  local target_ini="$2"
  local key="$3"
  local operator_assignments escaped_key
  operator_assignments="$(extract_ini_operator_assignments "$source_ini" "$key")"
  [ -n "$operator_assignments" ] || return 0

  escaped_key="$(printf '%s' "$key" | sed -e 's/[][\.^$*+?{}|()]/\\&/g')"
  sed -i -E "/^[[:space:]]*;?[[:space:]]*[!+.-]${escaped_key}=.*/d" "$target_ini"
  printf '\n%s\n' "$operator_assignments" >> "$target_ini"
}

install_server_login_password() {
  local server_root="$1"
  shift
  local password="${DUNE_SERVER_LOGIN_PASSWORD:-}"
  local arg
  local prefix='-ini:engine:[ConsoleVariables]:Bgd.ServerLoginPassword='
  if [ -z "$password" ]; then
    for arg in "$@"; do
      if [[ "${arg:0:${#prefix}}" == "$prefix" ]]; then
        password="${arg:${#prefix}}"
        break
      fi
    done
  fi
  [ -n "$password" ] || return 0

  local config_dir="$server_root/DuneSandbox/Saved/Config/LinuxServer"
  local engine_ini="${config_dir}/Engine.ini"
  local user_settings_dir="$server_root/DuneSandbox/Saved/UserSettings"
  local user_engine_ini="${user_settings_dir}/UserEngine.ini"
  local quoted_password
  quoted_password="$(engine_ini_quote "$password")"
  mkdir -p "$config_dir"
  mkdir -p "$user_settings_dir"

  set_ini_console_variable "$engine_ini" Bgd.ServerLoginPassword "$quoted_password"
  set_ini_console_variable "$user_engine_ini" Bgd.ServerLoginPassword "$quoted_password"
}

install_server_display_name() {
  local server_root="$1"
  shift
  local display_name="${DUNE_SERVER_DISPLAY_NAME:-${WORLD_NAME:-}}"
  local arg
  local prefix='-ini:engine:[ConsoleVariables]:Bgd.ServerDisplayName='
  if [ -z "$display_name" ]; then
    for arg in "$@"; do
      if [[ "${arg:0:${#prefix}}" == "$prefix" ]]; then
        display_name="${arg:${#prefix}}"
        break
      fi
    done
  fi
  [ -n "$display_name" ] || return 0

  local config_dir="$server_root/DuneSandbox/Saved/Config/LinuxServer"
  local engine_ini="${config_dir}/Engine.ini"
  local user_settings_dir="$server_root/DuneSandbox/Saved/UserSettings"
  local user_engine_ini="${user_settings_dir}/UserEngine.ini"
  local quoted_display_name
  quoted_display_name="$(engine_ini_quote "$display_name")"
  mkdir -p "$config_dir"
  mkdir -p "$user_settings_dir"

  set_ini_console_variable "$engine_ini" Bgd.ServerDisplayName "$quoted_display_name"
  set_ini_console_variable "$user_engine_ini" Bgd.ServerDisplayName "$quoted_display_name"
}

set_ini_console_variable() {
  local ini_file="$1"
  local key="$2"
  local value="$3"

  local escaped_key="${key//./\\.}"

  if [ -f "$ini_file" ] && grep -q '^\[ConsoleVariables\]' "$ini_file"; then
    if grep -q -E "^;?${escaped_key}=" "$ini_file"; then
      sed -i -E "0,/^;?${escaped_key}=.*/s//${key}=\"${value}\"/" "$ini_file"
    else
      sed -i "/^\[ConsoleVariables\]/a ${key}=\"${value}\"" "$ini_file"
    fi
  else
    {
      printf '[ConsoleVariables]\n'
      printf '%s="%s"\n' "$key" "$value"
    } >> "$ini_file"
  fi
}

engine_ini_quote() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/[&/]/\\&/g'
}

resolve_oodle_library() {
  local configured="${1:-/tmp/oodle/liboodle-data-shared.so}"
  local fallback=/workspace/backups/operator-oodle/liboodle-data-shared.so

  if [ -f "$configured" ]; then
    printf '%s\n' "$configured"
    return 0
  fi

  if [ -f "$fallback" ]; then
    printf '%s\n' "$fallback"
    return 0
  fi

  printf '%s\n' "$configured"
}

install_cert() {
  local service_account=/var/run/secrets/kubernetes.io/serviceaccount
  if [ -d "$service_account" ]; then
    ln -s "${service_account}/ca.crt" /usr/local/share/ca-certificates/kubernetes.crt
    update-ca-certificates
  fi
}

install_building_piece_limit_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_BUILDING_PIECE_LIMIT_PATCH_ENABLED:-false}" = "true" ] || return 0

  local limit="${DUNE_BUILDING_PIECE_LIMIT:-7500}"
  local pak="${DUNE_BUILDING_PIECE_LIMIT_PAK:-$server_root/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak}"
  local oodle
  oodle="$(resolve_oodle_library "${DUNE_OODLE_LIBRARY:-/tmp/oodle/liboodle-data-shared.so}")"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-building-piece-limit-pak.py)" \
      --pak "$pak" \
      --oodle "$oodle" \
      --limit "$limit" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-building-piece-limit-pak.py)" \
    --pak "$pak" \
    --oodle "$oodle" \
    --limit "$limit"
}

install_subfief_cap_binary_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED:-false}" = "true" ] || return 0

  local cap="${DUNE_SUBFIEF_CAP:-6}"
  local target="${DUNE_SUBFIEF_CAP_BINARY_TARGET:-subfief}"
  local binary="${DUNE_SUBFIEF_CAP_BINARY:-$server_root/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping}"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-subfief-cap-binary.py)" \
      --binary "$binary" \
      --target "$target" \
      --new-cap "$cap" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-subfief-cap-binary.py)" \
    --binary "$binary" \
    --target "$target" \
    --new-cap "$cap"
}

install_brt_dd_invalid_map_binary_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_BRT_DD_INVALID_MAP_BINARY_PATCH_ENABLED:-false}" = "true" ] || return 0

  local binary="${DUNE_BRT_DD_INVALID_MAP_BINARY:-$server_root/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping}"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-brt-dd-invalid-map-binary.py)" \
      --binary "$binary" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-brt-dd-invalid-map-binary.py)" \
    --binary "$binary"
}

install_brt_dd_action_gate_binary_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_BRT_DD_ACTION_GATE_BINARY_PATCH_ENABLED:-false}" = "true" ] || return 0

  local binary="${DUNE_BRT_DD_ACTION_GATE_BINARY:-$server_root/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping}"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-brt-dd-action-gate-binary.py)" \
      --binary "$binary" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-brt-dd-action-gate-binary.py)" \
    --binary "$binary"
}

install_brt_dd_narrow_tool_state_binary_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_BRT_DD_NARROW_TOOL_STATE_BINARY_PATCH_ENABLED:-false}" = "true" ] || return 0

  local binary="${DUNE_BRT_DD_NARROW_TOOL_STATE_BINARY:-$server_root/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping}"
  local sites="${DUNE_BRT_DD_NARROW_TOOL_STATE_PATCH_SITES:-can-use-empty-context}"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-brt-dd-narrow-tool-state-binary.py)" \
      --binary "$binary" \
      --sites "$sites" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-brt-dd-narrow-tool-state-binary.py)" \
    --binary "$binary" \
    --sites "$sites"
}

install_brt_dd_buildable_map_region_pak_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_BRT_DD_BUILDABLE_MAP_REGION_PATCH_ENABLED:-false}" = "true" ] || return 0

  local pak="${DUNE_BRT_DD_BUILDABLE_MAP_REGION_PAK:-$server_root/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak}"
  local mode="${DUNE_BRT_DD_BUILDABLE_MAP_REGION_PATCH_MODE:-swap-map-rows}"
  local target="${DUNE_BRT_DD_BUILDABLE_MAP_REGION_PATCH_TARGET:-pak}"
  local overlay_pak="${DUNE_BRT_DD_BUILDABLE_MAP_REGION_OVERLAY_PAK:-$server_root/DuneSandbox/Content/Paks/zzz_brt_dd_buildable_map_region_patch.pak}"
  local oodle
  oodle="$(resolve_oodle_library "${DUNE_OODLE_LIBRARY:-/tmp/oodle/liboodle-data-shared.so}")"

  if [ "$target" = "overlay" ]; then
    if [ -f "$overlay_pak" ]; then
      echo "BRT DD buildable-region overlay pak present: $overlay_pak (mode=$mode)"
      return 0
    fi

    if ! command -v git >/dev/null 2>&1 || ! command -v cargo >/dev/null 2>&1; then
      echo "missing prebuilt BRT DD buildable-region overlay pak: $overlay_pak" >&2
      echo "$mode mode requires a host-built overlay pak mounted into the container" >&2
      return 1
    fi

    if [ "$dry_run" = "true" ]; then
      python3 "$(workspace_script build-brt-dd-buildable-map-region-overlay-pak.py)" \
        --source-pak "$pak" \
        --oodle "$oodle" \
        --mode "$mode" \
        --output-pak "$overlay_pak" \
        --dry-run
      return 0
    fi

    rm -f "$overlay_pak"
    python3 "$(workspace_script build-brt-dd-buildable-map-region-overlay-pak.py)" \
      --source-pak "$pak" \
      --oodle "$oodle" \
      --mode "$mode" \
      --output-pak "$overlay_pak"
    return 0
  fi

  if [ "$target" != "pak" ]; then
    echo "invalid DUNE_BRT_DD_BUILDABLE_MAP_REGION_PATCH_TARGET: $target" >&2
    echo "expected 'pak' or 'overlay'" >&2
    return 1
  fi

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-brt-dd-buildable-map-region-pak.py)" \
      --pak "$pak" \
      --oodle "$oodle" \
      --mode "$mode" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-brt-dd-buildable-map-region-pak.py)" \
    --pak "$pak" \
    --oodle "$oodle" \
    --mode "$mode"
}

install_brt_dd_tool_enable_binary_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_BRT_DD_TOOL_ENABLE_BINARY_PATCH_ENABLED:-false}" = "true" ] || return 0

  local binary="${DUNE_BRT_DD_TOOL_ENABLE_BINARY:-$server_root/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping}"
  local sites="${DUNE_BRT_DD_TOOL_ENABLE_PATCH_SITES:-all}"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-brt-dd-tool-enable-binary.py)" \
      --binary "$binary" \
      --sites "$sites" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-brt-dd-tool-enable-binary.py)" \
    --binary "$binary" \
    --sites "$sites"
}

install_landsraad_vendor_faction_gate_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PATCH_ENABLED:-false}" = "true" ] || return 0

  local pak="${DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PAK:-$server_root/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak}"
  local oodle
  oodle="$(resolve_oodle_library "${DUNE_OODLE_LIBRARY:-/tmp/oodle/liboodle-data-shared.so}")"

  if [ "$dry_run" = "true" ]; then
    python3 "$(workspace_script patch-landsraad-vendor-faction-gate-pak.py)" \
      --pak "$pak" \
      --oodle "$oodle" \
      --dry-run
    return 0
  fi

  python3 "$(workspace_script patch-landsraad-vendor-faction-gate-pak.py)" \
    --pak "$pak" \
    --oodle "$oodle"
}

main "$@"
