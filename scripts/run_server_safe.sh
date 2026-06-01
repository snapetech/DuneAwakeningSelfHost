#!/usr/bin/env bash
set -euo pipefail

main() {
  local server_root="${DUNE_SERVER_ROOT:-/home/dune/server}"
  local dune_home="${DUNE_HOME:-/home/dune}"
  local dry_run="${DUNE_RUN_SERVER_SAFE_DRY_RUN:-false}"

  install_cert
  install_building_piece_limit_patch "$server_root" "$dry_run"
  install_landsraad_vendor_faction_gate_patch "$server_root" "$dry_run"
  install_subfief_cap_binary_patch "$server_root" "$dry_run"
  install_user_configs "$server_root"
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
  local oodle="${DUNE_OODLE_LIBRARY:-/tmp/oodle/liboodle-data-shared.so}"

  if [ "$dry_run" = "true" ]; then
    python3 /workspace/scripts/patch-building-piece-limit-pak.py \
      --pak "$pak" \
      --oodle "$oodle" \
      --limit "$limit" \
      --dry-run
    return 0
  fi

  python3 /workspace/scripts/patch-building-piece-limit-pak.py \
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
    python3 /workspace/scripts/patch-subfief-cap-binary.py \
      --binary "$binary" \
      --target "$target" \
      --new-cap "$cap" \
      --dry-run
    return 0
  fi

  python3 /workspace/scripts/patch-subfief-cap-binary.py \
    --binary "$binary" \
    --target "$target" \
    --new-cap "$cap"
}

install_landsraad_vendor_faction_gate_patch() {
  local server_root="$1"
  local dry_run="$2"
  [ "${DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PATCH_ENABLED:-false}" = "true" ] || return 0

  local pak="${DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PAK:-$server_root/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak}"
  local oodle="${DUNE_OODLE_LIBRARY:-/tmp/oodle/liboodle-data-shared.so}"

  if [ "$dry_run" = "true" ]; then
    python3 /workspace/scripts/patch-landsraad-vendor-faction-gate-pak.py \
      --pak "$pak" \
      --oodle "$oodle" \
      --dry-run
    return 0
  fi

  python3 /workspace/scripts/patch-landsraad-vendor-faction-gate-pak.py \
    --pak "$pak" \
    --oodle "$oodle"
}

main "$@"
