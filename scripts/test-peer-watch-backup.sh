#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d -p "${TMPDIR:-/tmp}" dash-peer-watch-backup-test.XXXXXX)"
trap 'rm -rf "$work"' EXIT
missing="$work/unavailable/watch.sqlite3"
test_env="$work/test.env"
sed 's/^DUNE_ALERT_INBOX_ENABLED=.*/DUNE_ALERT_INBOX_ENABLED=false/' "$repo_root/.env.example" >"$test_env"

DUNE_PEER_WATCH_HOST_DATABASE="$missing" \
  "$repo_root/scripts/backup-state.sh" --dry-run "$test_env" >"$work/dry-run.out"
grep -Fq "peer_watch_snapshot=<required but unavailable $missing>" "$work/dry-run.out"

if DUNE_PEER_WATCH_HOST_DATABASE="$missing" \
  "$repo_root/scripts/backup-state.sh" "$test_env" >"$work/backup.out" 2>&1; then
  printf 'enabled peer watch with an unavailable host database unexpectedly entered backup execution\n' >&2
  exit 1
fi
grep -Fq "enabled peer watch is unavailable to host backup: $missing" "$work/backup.out"

mkdir -p "$work/incomplete-backup"
printf 'peer_watch_required=true\n' >"$work/incomplete-backup/manifest.txt"
if "$repo_root/scripts/verify-backup.sh" "$work/incomplete-backup" >"$work/verify.out" 2>&1; then
  printf 'verifier unexpectedly accepted a required but missing peer-watch snapshot\n' >&2
  exit 1
fi
grep -Fq "FAIL enabled peer-watch snapshot is missing" "$work/verify.out"

printf 'peer-watch backup coverage tests passed\n'
