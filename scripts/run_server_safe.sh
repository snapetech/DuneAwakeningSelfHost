#!/usr/bin/env bash
set -euo pipefail

main() {
  install_cert
  install_user_configs
  install_server_login_password "$@"
  install_server_display_name "$@"

  mkdir -p /home/dune/server/DuneSandbox/Saved/UserSettings
  chown -R dune:nogroup /home/dune/server/DuneSandbox/Saved

  mkdir -p "/home/dune/.config/Epic/Unreal Engine/Engine"
  local config_path="/home/dune/.config/Epic/Unreal Engine/Engine/Config"
  [ -d "$config_path" ] && [ ! -L "$config_path" ] && rm -rf "$config_path"
  ln -sfn /home/dune/server/DuneSandbox/Saved/UserSettings "$config_path"

  cd /home/dune/server

  local pod_ip="${POD_IP:-127.0.0.1}"
  local args=()
  local arg
  local login_prefix='-ini:engine:[ConsoleVariables]:Bgd.ServerLoginPassword='
  for arg in "$@"; do
    if [ "$arg" = '-MultiHome=$POD_IP' ]; then
      args+=("-MultiHome=$pod_ip")
    elif [[ "${arg:0:${#login_prefix}}" == "$login_prefix" ]] && [ -n "${DUNE_SERVER_LOGIN_PASSWORD:-}" ]; then
      args+=("-ini:engine:[ConsoleVariables]:Bgd.ServerLoginPassword=${DUNE_SERVER_LOGIN_PASSWORD}")
    else
      args+=("$arg")
    fi
  done
  args+=("-IGWBindAddress=$pod_ip")

  exec runuser -u dune -- ./DuneSandboxServer.sh "${args[@]}"
}

install_user_configs() {
  local source_dir=/workspace/config
  local config_dir=/home/dune/server/DuneSandbox/Saved/Config/LinuxServer
  local user_settings_dir=/home/dune/server/DuneSandbox/Saved/UserSettings
  mkdir -p "$config_dir"
  mkdir -p "$user_settings_dir"

  copy_user_config "${source_dir}/UserEngine.ini" "${config_dir}/Engine.ini"
  copy_user_config "${source_dir}/UserEngine.ini" "${user_settings_dir}/UserEngine.ini"
  copy_user_config "${source_dir}/UserGame.ini" "${config_dir}/Game.ini"
  copy_user_config "${source_dir}/UserGame.ini" "${user_settings_dir}/UserGame.ini"
}

copy_user_config() {
  local source="$1"
  local target="$2"
  [ -f "$source" ] || return 0
  cp "$source" "$target"
}

install_server_login_password() {
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

  local config_dir=/home/dune/server/DuneSandbox/Saved/Config/LinuxServer
  local engine_ini="${config_dir}/Engine.ini"
  local user_settings_dir=/home/dune/server/DuneSandbox/Saved/UserSettings
  local user_engine_ini="${user_settings_dir}/UserEngine.ini"
  local quoted_password
  quoted_password="$(engine_ini_quote "$password")"
  mkdir -p "$config_dir"
  mkdir -p "$user_settings_dir"

  set_ini_console_variable "$engine_ini" Bgd.ServerLoginPassword "$quoted_password"
  set_ini_console_variable "$user_engine_ini" Bgd.ServerLoginPassword "$quoted_password"
}

install_server_display_name() {
  local display_name="${WORLD_NAME:-}"
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

  local config_dir=/home/dune/server/DuneSandbox/Saved/Config/LinuxServer
  local engine_ini="${config_dir}/Engine.ini"
  local user_settings_dir=/home/dune/server/DuneSandbox/Saved/UserSettings
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

main "$@"
