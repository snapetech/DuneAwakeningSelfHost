#!/usr/bin/env bash
set -euo pipefail

main() {
  install_cert

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

install_cert() {
  local service_account=/var/run/secrets/kubernetes.io/serviceaccount
  if [ -d "$service_account" ]; then
    ln -s "${service_account}/ca.crt" /usr/local/share/ca-certificates/kubernetes.crt
    update-ca-certificates
  fi
}

main "$@"
