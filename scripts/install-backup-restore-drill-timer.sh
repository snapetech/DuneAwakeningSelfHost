#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-backup-restore-drill-timer.sh [ENV_FILE] [SERVICE_PATH] [TIMER_PATH]

Install and enable the daily no-network PostgreSQL restore-rehearsal timer.
Run as the normal DASH operator; the script uses sudo only for system unit files.
USAGE
}

if [[ $# -gt 3 ]]; then usage; exit 2; fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-$repo_root/.env}"
service_path="${2:-/etc/systemd/system/dune-backup-restore-drill.service}"
timer_path="${3:-/etc/systemd/system/dune-backup-restore-drill.timer}"
[[ "$env_file" == /* ]] || env_file="$repo_root/$env_file"
[[ -f "$env_file" ]] || { printf 'env file does not exist: %s\n' "$env_file" >&2; exit 1; }
[[ -S /var/run/docker.sock ]] || { printf 'Docker socket is unavailable: /var/run/docker.sock\n' >&2; exit 1; }

operator="${DUNE_RESTORE_DRILL_SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
[[ "$operator" != root ]] || { printf 'restore-drill service must use a non-root DASH operator\n' >&2; exit 1; }
operator_group="$(id -gn "$operator")"
socket_group="$(stat -c %G /var/run/docker.sock)"
id "$operator" >/dev/null
if ! id -nG "$operator" | tr ' ' '\n' | grep -Fxq "$socket_group" && [[ "$operator" != root ]]; then
  printf 'operator %s is not a member of Docker socket group %s\n' "$operator" "$socket_group" >&2
  exit 1
fi

receipt_dir="$repo_root/backups/admin-panel/restore-drills"
install_dir=(install -d -m 0700 -o "$operator" -g "$operator_group" "$receipt_dir")
if [[ ! -w "$(dirname "$receipt_dir")" ]]; then install_dir=(sudo "${install_dir[@]}"); fi
"${install_dir[@]}"

service_template="$repo_root/config/systemd/dune-backup-restore-drill.service"
timer_template="$repo_root/config/systemd/dune-backup-restore-drill.timer"
tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
trap 'rm -f "$tmp_service" "$tmp_timer"' EXIT

sed \
  -e "s#^User=.*#User=$operator#" \
  -e "s#^Group=.*#Group=$operator_group#" \
  -e "s#^SupplementaryGroups=.*#SupplementaryGroups=$socket_group#" \
  -e "s#/path/to/DuneAwakeningSelfHost#$repo_root#g" \
  "$service_template" > "$tmp_service"
cp "$timer_template" "$tmp_timer"

install_unit() {
  local source="$1" target="$2"
  if [[ -w "$(dirname "$target")" ]]; then
    install -m 0644 "$source" "$target"
  else
    sudo install -m 0644 "$source" "$target"
  fi
}
install_unit "$tmp_service" "$service_path"
install_unit "$tmp_timer" "$timer_path"

systemctl_cmd=(systemctl)
[[ "$(id -u)" -eq 0 ]] || systemctl_cmd=(sudo systemctl)
"${systemctl_cmd[@]}" daemon-reload
"${systemctl_cmd[@]}" enable --now "$(basename "$timer_path")"
"${systemctl_cmd[@]}" list-timers "$(basename "$timer_path")" --all --no-pager
printf 'installed and enabled %s with service %s as %s\n' "$timer_path" "$service_path" "$operator"
