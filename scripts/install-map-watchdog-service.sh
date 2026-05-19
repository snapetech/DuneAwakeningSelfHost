#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-map-watchdog-service.sh [ENV_FILE] [UNIT_PATH]

Renders and installs the Dune map watchdog systemd unit for the current checkout.

Defaults:
  ENV_FILE=.env
  UNIT_PATH=/etc/systemd/system/dune-map-watchdog.service
USAGE
}

if [[ $# -gt 2 ]]; then
  usage
  exit 2
fi

env_file="${1:-.env}"
unit_path="${2:-/etc/systemd/system/dune-map-watchdog.service}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template="$repo_root/config/systemd/dune-map-watchdog.service"

if [[ ! -f "$repo_root/$env_file" && "$env_file" != /* ]]; then
  printf 'env file does not exist: %s\n' "$repo_root/$env_file" >&2
  exit 1
fi

if [[ ! -f "$template" ]]; then
  printf 'unit template does not exist: %s\n' "$template" >&2
  exit 1
fi

env_path="$env_file"
if [[ "$env_path" != /* ]]; then
  env_path="$repo_root/$env_path"
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

sed \
  -e "s#^WorkingDirectory=.*#WorkingDirectory=$repo_root#" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/watch-maps.sh $env_path#" \
  "$template" > "$tmp"

install_cmd=(install -m 0644 "$tmp" "$unit_path")
if [[ ! -w "$(dirname "$unit_path")" ]]; then
  install_cmd=(sudo "${install_cmd[@]}")
fi

"${install_cmd[@]}"

if command -v systemctl >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl daemon-reload
  else
    sudo systemctl daemon-reload
  fi
fi

printf 'installed %s\n' "$unit_path"
printf 'enable with: sudo systemctl enable --now %s\n' "$(basename "$unit_path")"
