#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-artificial-exchange-watchdog-timer.sh [ENV_FILE] [SERVICE_PATH] [TIMER_PATH]

Installs a systemd timer that restarts enabled artificial Exchange buyer and
populator services when their .env gates are enabled but the units are inactive.
USAGE
}

if [[ $# -gt 3 ]]; then
  usage
  exit 2
fi

env_file="${1:-.env}"
service_path="${2:-/etc/systemd/system/dune-artificial-exchange-watchdog.service}"
timer_path="${3:-/etc/systemd/system/dune-artificial-exchange-watchdog.timer}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_template="$repo_root/config/systemd/dune-artificial-exchange-watchdog.service"
timer_template="$repo_root/config/systemd/dune-artificial-exchange-watchdog.timer"

if [[ ! -f "$repo_root/$env_file" && "$env_file" != /* ]]; then
  printf 'env file does not exist: %s\n' "$repo_root/$env_file" >&2
  exit 1
fi

env_path="$env_file"
if [[ "$env_path" != /* ]]; then
  env_path="$repo_root/$env_path"
fi

tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
trap 'rm -f "$tmp_service" "$tmp_timer"' EXIT

sed \
  -e "s#^WorkingDirectory=.*#WorkingDirectory=$repo_root#" \
  -e "s#^EnvironmentFile=.*#EnvironmentFile=$env_path#" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/artificial-exchange-watchdog.sh $env_path#" \
  "$service_template" > "$tmp_service"
cp "$timer_template" "$tmp_timer"

install_cmd=(install -m 0644 "$tmp_service" "$service_path")
timer_install_cmd=(install -m 0644 "$tmp_timer" "$timer_path")
if [[ ! -w "$(dirname "$service_path")" || ! -w "$(dirname "$timer_path")" ]]; then
  install_cmd=(sudo "${install_cmd[@]}")
  timer_install_cmd=(sudo "${timer_install_cmd[@]}")
fi

"${install_cmd[@]}"
"${timer_install_cmd[@]}"

if command -v systemctl >/dev/null 2>&1 && [[ "$service_path" == /etc/systemd/system/*.service && "$timer_path" == /etc/systemd/system/*.timer ]]; then
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl daemon-reload
    systemctl enable --now "$(basename "$timer_path")"
    systemctl start "$(basename "$service_path")"
    systemctl list-timers "$(basename "$timer_path")" --no-pager
  else
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$(basename "$timer_path")"
    sudo systemctl start "$(basename "$service_path")"
    systemctl list-timers "$(basename "$timer_path")" --no-pager
  fi
fi

printf 'installed %s and %s\n' "$service_path" "$timer_path"
