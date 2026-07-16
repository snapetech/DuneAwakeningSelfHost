#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-$repo_root/.env}"
unit_dir="${2:-/etc/systemd/system}"
if [[ "$env_file" != /* ]]; then env_file="$repo_root/$env_file"; fi
[[ -f "$env_file" ]] || { printf 'env file does not exist: %s\n' "$env_file" >&2; exit 1; }
interval="$(sed -nE 's/^DUNE_PUBLIC_IP_MONITOR_INTERVAL_MINUTES=//p' "$env_file" | tail -1)"
interval="${interval:-5}"
[[ "$interval" =~ ^[0-9]+$ ]] && ((interval >= 1 && interval <= 1440)) || { printf 'interval must be 1..1440 minutes\n' >&2; exit 2; }
service_user="${DUNE_SERVICE_USER:-$(stat -c %U "$repo_root")}"
service_group="${DUNE_SERVICE_GROUP:-$(stat -c %G "$repo_root")}"
tmp_service="$(mktemp)"; tmp_timer="$(mktemp)"
trap 'rm -f "$tmp_service" "$tmp_timer"' EXIT
sed -e "s#^WorkingDirectory=.*#WorkingDirectory=$repo_root#" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/public-ip-monitor.sh $env_file check#" \
  -e "s#DUNE_SERVICE_USER_PLACEHOLDER#$service_user#g" \
  -e "s#DUNE_SERVICE_GROUP_PLACEHOLDER#$service_group#g" \
  "$repo_root/config/systemd/dune-public-ip-monitor.service" > "$tmp_service"
sed "s/DUNE_PUBLIC_IP_MONITOR_INTERVAL_PLACEHOLDER/$interval/g" \
  "$repo_root/config/systemd/dune-public-ip-monitor.timer" > "$tmp_timer"
install_cmd=(install -m 0644 "$tmp_service" "$unit_dir/dune-public-ip-monitor.service")
timer_cmd=(install -m 0644 "$tmp_timer" "$unit_dir/dune-public-ip-monitor.timer")
if [[ ! -w "$unit_dir" ]]; then install_cmd=(sudo "${install_cmd[@]}"); timer_cmd=(sudo "${timer_cmd[@]}"); fi
"${install_cmd[@]}"; "${timer_cmd[@]}"
if [[ "$(id -u)" -eq 0 ]]; then systemctl daemon-reload; systemctl enable --now dune-public-ip-monitor.timer
else sudo systemctl daemon-reload; sudo systemctl enable --now dune-public-ip-monitor.timer; fi
printf 'installed and enabled dune-public-ip-monitor.timer (%s minutes)\n' "$interval"
