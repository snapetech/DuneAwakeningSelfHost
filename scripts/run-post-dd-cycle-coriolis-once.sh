#!/usr/bin/env bash
set -euo pipefail

marker="post-dd-cycle-coriolis-20260525"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
log_dir="$repo_root/logs"
log_file="$log_dir/post-dd-cycle-coriolis.log"

mkdir -p "$log_dir"

set +e
{
  date
  cd "$repo_root"
  "$script_dir/apply-post-dd-cycle-coriolis-config.sh" .env --restart
} >>"$log_file" 2>&1
status=$?
set -e

if command -v crontab >/dev/null 2>&1; then
  tmp="$(mktemp)"
  crontab -l 2>/dev/null | grep -Fv "$marker" >"$tmp" || true
  crontab "$tmp"
  rm -f "$tmp"
fi

exit "$status"
