#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-artificial-exchange-service.sh [ENV_FILE] [UNIT_PATH] [MODE]

Renders and installs the Dune artificial Exchange bot systemd unit for the
current checkout.

Defaults:
  ENV_FILE=.env
  UNIT_PATH=/etc/systemd/system/dune-artificial-exchange-bot.service
  MODE=buyer

Modes:
  buyer      run buyer scan loop only
  populator  run Exchange populator loop only
  both       run populator and buyer loops in the same process

The bot's own defaults are disabled/dry-run. ENV_FILE controls any live
artificial Exchange gates.
USAGE
}

if [[ $# -gt 3 ]]; then
  usage
  exit 2
fi

env_file="${1:-.env}"
unit_path="${2:-/etc/systemd/system/dune-artificial-exchange-bot.service}"
mode="${3:-buyer}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template="$repo_root/config/systemd/dune-artificial-exchange-bot.service"

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

case "$mode" in
  buyer) exec_args="--loop" ;;
  populator) exec_args="--populate-loop" ;;
  both) exec_args="--loop --populate-loop" ;;
  *)
    printf 'unknown mode: %s\n' "$mode" >&2
    usage
    exit 2
    ;;
esac

sed \
  -e "s#^WorkingDirectory=.*#WorkingDirectory=$repo_root#" \
  -e "s#^EnvironmentFile=.*#EnvironmentFile=$env_path#" \
  -e "s#^ExecStartPre=.*#ExecStartPre=$repo_root/scripts/build-exchange-catalog.py#" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/artificial-exchange-bot.py $exec_args#" \
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
  if [[ "$unit_path" == /etc/systemd/system/*.service ]]; then
    service_name="$(basename "$unit_path")"
    if [[ "$(id -u)" -eq 0 ]]; then
      systemctl enable --now "$service_name"
    else
      sudo systemctl enable --now "$service_name"
    fi
  fi
fi

printf 'installed %s\n' "$unit_path"
if [[ "$unit_path" == /etc/systemd/system/*.service ]]; then
  printf 'enabled and started %s\n' "$(basename "$unit_path")"
else
  printf 'enable with: sudo systemctl enable --now %s\n' "$(basename "$unit_path")"
fi
