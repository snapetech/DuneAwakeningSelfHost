#!/usr/bin/env bash
set -euo pipefail

main() {
  install_cert
  install_server_login_password "$@"

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
  for arg in "$@"; do
    if [ "$arg" = '-MultiHome=$POD_IP' ]; then
      args+=("-MultiHome=$pod_ip")
    else
      args+=("$arg")
    fi
  done
  args+=("-IGWBindAddress=$pod_ip")

  exec runuser -u dune -- ./DuneSandboxServer.sh "${args[@]}"
}

install_server_login_password() {
  local password="${DUNE_SERVER_LOGIN_PASSWORD:-}"
  local arg
  for arg in "$@"; do
    case "$arg" in
      *Bgd.ServerLoginPassword=*)
        password="${arg#*Bgd.ServerLoginPassword=}"
        password="${password%\"}"
        password="${password#\"}"
        ;;
    esac
  done
  [ -n "$password" ] || return 0

  local config_dir=/home/dune/server/DuneSandbox/Saved/Config/LinuxServer
  local engine_ini="${config_dir}/Engine.ini"
  local quoted_password
  quoted_password="$(engine_ini_quote "$password")"
  mkdir -p "$config_dir"

  if [ -f "$engine_ini" ] && grep -q '^\[ConsoleVariables\]' "$engine_ini"; then
    if grep -q '^Bgd\.ServerLoginPassword=' "$engine_ini"; then
      sed -i -E 's/^Bgd\.ServerLoginPassword=.*/Bgd.ServerLoginPassword="'"${quoted_password}"'"/' "$engine_ini"
    else
      sed -i '/^\[ConsoleVariables\]/a Bgd.ServerLoginPassword="'"${quoted_password}"'"' "$engine_ini"
    fi
  else
    {
      printf '[ConsoleVariables]\n'
      printf 'Bgd.ServerLoginPassword="%s"\n' "$quoted_password"
    } >> "$engine_ini"
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
