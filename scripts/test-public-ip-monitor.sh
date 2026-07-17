#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
host="$(hostname -s)"
env_file="$tmp/test.env"
printf '%s\n' \
  'EXTERNAL_ADDRESS=198.51.100.10' \
  'GAME_RMQ_PUBLIC_HOST=198.51.100.10' \
  'DUNE_PUBLIC_IP_MONITOR_ENABLED=true' \
  "DUNE_PUBLIC_IP_MONITOR_ALLOWED_HOST=$host" \
  'DUNE_PUBLIC_IP_MONITOR_INTERVAL_MINUTES=5' \
  'DUNE_PUBLIC_IP_MONITOR_DRY_RUN=true' > "$env_file"

ENV_FILE="$tmp/ignored.env" \
DUNE_PUBLIC_IP_MONITOR_STATE_DIR="$tmp/state" \
DUNE_PUBLIC_IP_MONITOR_DETECTED_IP=198.51.100.20 \
  "$repo_root/scripts/public-ip-monitor.sh" "$env_file" check > "$tmp/output"
grep -q 'dry-run: would update EXTERNAL_ADDRESS' "$tmp/output"
grep -q '^status=dry-run$' "$tmp/state/public-ip-monitor.state"
grep -q '^EXTERNAL_ADDRESS=198.51.100.10$' "$env_file"

DUNE_PUBLIC_IP_MONITOR_STATE_DIR="$tmp/current-state" \
DUNE_PUBLIC_IP_MONITOR_DETECTED_IP=198.51.100.10 \
  "$repo_root/scripts/public-ip-monitor.sh" "$env_file" check > "$tmp/current-output"
grep -q 'public IP unchanged' "$tmp/current-output"
grep -q '^status=current$' "$tmp/current-state/public-ip-monitor.state"

sed -i 's/^DUNE_PUBLIC_IP_MONITOR_ALLOWED_HOST=.*/DUNE_PUBLIC_IP_MONITOR_ALLOWED_HOST=wrong-host/' "$env_file"
if DUNE_PUBLIC_IP_MONITOR_STATE_DIR="$tmp/state" DUNE_PUBLIC_IP_MONITOR_DETECTED_IP=198.51.100.20 \
  "$repo_root/scripts/public-ip-monitor.sh" "$env_file" check >/dev/null 2>&1; then
  printf 'host mismatch was not rejected\n' >&2
  exit 1
fi
grep -q '^status=refused$' "$tmp/state/public-ip-monitor.state"
printf 'public IP monitor tests passed\n'
