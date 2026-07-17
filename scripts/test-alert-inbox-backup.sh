#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d -p "${TMPDIR:-/tmp}" dash-alert-inbox-backup-test.XXXXXX)"
trap 'rm -rf "$work"' EXIT
missing="$work/unavailable/inbox.sqlite3"

DUNE_ALERT_INBOX_HOST_DATABASE="$missing" \
  "$repo_root/scripts/backup-state.sh" --dry-run "$repo_root/.env.example" >"$work/dry-run.out"
grep -Fq "alert_inbox_snapshot=<required but unavailable $missing>" "$work/dry-run.out"

if DUNE_ALERT_INBOX_HOST_DATABASE="$missing" \
  "$repo_root/scripts/backup-state.sh" "$repo_root/.env.example" >"$work/backup.out" 2>&1; then
  printf 'enabled inbox with an unavailable host database unexpectedly entered backup execution\n' >&2
  exit 1
fi
grep -Fq "enabled alert inbox is unavailable to host backup: $missing" "$work/backup.out"

mkdir -p "$work/incomplete-backup"
printf 'alert_inbox_required=true\n' >"$work/incomplete-backup/manifest.txt"
if "$repo_root/scripts/verify-backup.sh" "$work/incomplete-backup" >"$work/verify.out" 2>&1; then
  printf 'verifier unexpectedly accepted a required but missing inbox snapshot\n' >&2
  exit 1
fi
grep -Fq "FAIL enabled alert-inbox snapshot is missing" "$work/verify.out"

printf 'alert inbox backup coverage tests passed\n'
