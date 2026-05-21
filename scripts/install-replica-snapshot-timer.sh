#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
remote="${2:-${POSTGRES_REMOTE_REPLICA_HOST:-}}"
remote_root="${3:-${POSTGRES_REMOTE_REPLICA_ROOT:-/srv/dune-postgres-replica}}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_path="${4:-/etc/systemd/system/dune-replica-snapshot.service}"
timer_path="${5:-/etc/systemd/system/dune-replica-snapshot.timer}"
run_user="${DUNE_REPLICA_SNAPSHOT_USER:-$(id -un)}"
run_group="${DUNE_REPLICA_SNAPSHOT_GROUP:-$(id -gn)}"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
if [[ -z "$remote" ]]; then
  printf 'remote host required: %s ENV_FILE REMOTE_HOST [REMOTE_ROOT]\n' "$0" >&2
  exit 1
fi

tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
sed \
  -e "s#^User=.*#User=${run_user}#" \
  -e "s#^Group=.*#Group=${run_group}#" \
  -e "s#WorkingDirectory=.*#WorkingDirectory=${repo_root}#" \
  -e "s#ExecStart=.*#ExecStart=${repo_root}/scripts/replica-snapshot.sh ${repo_root}/${env_file} ${remote} ${remote_root}#" \
  "$repo_root/config/systemd/dune-replica-snapshot.service" > "$tmp_service"
cp "$repo_root/config/systemd/dune-replica-snapshot.timer" "$tmp_timer"

sudo install -m 0644 "$tmp_service" "$service_path"
sudo install -m 0644 "$tmp_timer" "$timer_path"
rm -f "$tmp_service" "$tmp_timer"

sudo systemctl daemon-reload
sudo systemctl enable --now "$(basename "$timer_path")"
sudo systemctl reset-failed "$(basename "$service_path")" || true
sudo systemctl list-timers "$(basename "$timer_path")" --no-pager
