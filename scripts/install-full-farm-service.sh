#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-full-farm-service.sh [ENV_FILE] [UNIT_PATH]

Renders and installs the Dune full-farm startup systemd unit for this checkout.

Defaults:
  ENV_FILE=.env
  UNIT_PATH=/etc/systemd/system/dune-full-farm.service
USAGE
}

if [[ $# -gt 2 ]]; then
  usage
  exit 2
fi

env_file="${1:-.env}"
unit_path="${2:-/etc/systemd/system/dune-full-farm.service}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template="$repo_root/config/systemd/dune-full-farm.service"

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

# Default the service user to whoever owns this checkout (almost always the
# operator running the installer). Their HOME is where the docker compose CLI
# plugin lives, so the service must run as them or `docker compose` exits 125
# with "unknown shorthand flag: 'f'". Override with DUNE_SERVICE_USER.
service_user="${DUNE_SERVICE_USER:-$(stat -c %U "$repo_root")}"
service_group="${DUNE_SERVICE_GROUP:-$(stat -c %G "$repo_root")}"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

sed \
  -e "s#^WorkingDirectory=.*#WorkingDirectory=$repo_root#" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/start-full-warm-pool.sh $env_path#" \
  -e "s#^ExecStop=.*#ExecStop=$repo_root/scripts/stop-full-warm-pool.sh $env_path#" \
  -e "s#^User=DUNE_SERVICE_USER_PLACEHOLDER#User=$service_user#" \
  -e "s#^Group=DUNE_SERVICE_USER_PLACEHOLDER#Group=$service_group#" \
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
printf 'enable with: sudo systemctl enable %s\n' "$(basename "$unit_path")"
