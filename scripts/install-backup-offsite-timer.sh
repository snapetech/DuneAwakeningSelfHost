#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/install-backup-offsite-timer.sh [env-file] [backup-config] [service-path] [timer-path]

Installs a systemd timer for scripts/backup-offsite.sh.

Example:
  ./scripts/install-backup-offsite-timer.sh .env examples/backup/rclone-offsite.env
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
backup_config="${2:-examples/backup/rclone-offsite.env}"
service_path="${3:-/etc/systemd/system/dune-backup-offsite.service}"
timer_path="${4:-/etc/systemd/system/dune-backup-offsite.timer}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
if [[ ! -f "$backup_config" ]]; then
  printf 'backup config not found: %s\n' "$backup_config" >&2
  exit 1
fi

tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"

sed \
  -e "s#WorkingDirectory=.*#WorkingDirectory=${repo_root}#" \
  -e "s#Environment=DUNE_BACKUP_REMOTE_ENV=.*#Environment=DUNE_BACKUP_REMOTE_ENV=${repo_root}/${backup_config}#" \
  -e "s#ExecStart=.*#ExecStart=${repo_root}/scripts/backup-offsite.sh ${repo_root}/${env_file}#" \
  "$repo_root/config/systemd/dune-backup-offsite.service" > "$tmp_service"
cp "$repo_root/config/systemd/dune-backup-offsite.timer" "$tmp_timer"

sudo install -m 0644 "$tmp_service" "$service_path"
sudo install -m 0644 "$tmp_timer" "$timer_path"
rm -f "$tmp_service" "$tmp_timer"

sudo systemctl daemon-reload
sudo systemctl enable --now "$(basename "$timer_path")"
sudo systemctl list-timers "$(basename "$timer_path")" --no-pager
