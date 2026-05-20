#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-daily-maintenance-timer.sh [ENV_FILE] [SERVICE_PATH] [TIMER_PATH]

Installs the systemd timer that schedules DASH daily maintenance at 05:30,
which creates a 30-minute warning window for the 06:00 restart.

Defaults:
  ENV_FILE=.env
  SERVICE_PATH=/etc/systemd/system/dune-daily-maintenance-schedule.service
  TIMER_PATH=/etc/systemd/system/dune-daily-maintenance-schedule.timer
USAGE
}

if [[ $# -gt 3 ]]; then
  usage
  exit 2
fi

env_file="${1:-.env}"
service_path="${2:-/etc/systemd/system/dune-daily-maintenance-schedule.service}"
timer_path="${3:-/etc/systemd/system/dune-daily-maintenance-schedule.timer}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_template="$repo_root/config/systemd/dune-daily-maintenance-schedule.service"
timer_template="$repo_root/config/systemd/dune-daily-maintenance-schedule.timer"

if [[ ! -f "$repo_root/$env_file" && "$env_file" != /* ]]; then
  printf 'env file does not exist: %s\n' "$repo_root/$env_file" >&2
  exit 1
fi

if [[ ! -f "$service_template" || ! -f "$timer_template" ]]; then
  printf 'daily maintenance systemd templates are missing\n' >&2
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
  -e "s#^Environment=DUNE_ENV_FILE=.*#Environment=DUNE_ENV_FILE=$env_path#" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/schedule-daily-maintenance.sh#" \
  "$service_template" > "$tmp_service"
cp "$timer_template" "$tmp_timer"

install_cmd=(install -m 0644 "$tmp_service" "$service_path")
if [[ ! -w "$(dirname "$service_path")" ]]; then
  install_cmd=(sudo "${install_cmd[@]}")
fi
"${install_cmd[@]}"

install_cmd=(install -m 0644 "$tmp_timer" "$timer_path")
if [[ ! -w "$(dirname "$timer_path")" ]]; then
  install_cmd=(sudo "${install_cmd[@]}")
fi
"${install_cmd[@]}"

if command -v systemctl >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl daemon-reload
    systemctl enable --now "$(basename "$timer_path")"
    systemctl list-timers "$(basename "$timer_path")" --no-pager
  else
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$(basename "$timer_path")"
    sudo systemctl list-timers "$(basename "$timer_path")" --no-pager
  fi
fi

printf 'installed %s and %s\n' "$service_path" "$timer_path"
