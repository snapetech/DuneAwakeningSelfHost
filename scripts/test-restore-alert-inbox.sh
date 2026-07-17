#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
work="$(mktemp -d backups/alert-inbox-restore-test.XXXXXX)"
outside="$(mktemp -d)"
trap 'rm -rf "$work" "$outside"' EXIT

PYTHONPATH=admin python3 - "$work/alert-inbox.sqlite3" <<'PY'
import sys
import alert_inbox
alert_inbox.Store(sys.argv[1]).initialize()
PY

output="$(./scripts/restore-alert-inbox.sh .env.example "$work")"
grep -Fq 'alert-inbox restore plan OK' <<<"$output"
grep -Fq 'services=admin-panel' <<<"$output"
grep -Fq 'game_map_lifecycle=false' <<<"$output"

cp "$work/alert-inbox.sqlite3" "$outside/alert-inbox.sqlite3"
if ./scripts/restore-alert-inbox.sh .env.example "$outside" >/dev/null 2>&1; then
  printf 'restore helper accepted a source outside backups/\n' >&2
  exit 1
fi

ln -s "$outside" "$work/escaped-target"
if DUNE_ALERT_INBOX_HOST_DATABASE="$work/escaped-target/inbox.sqlite3" ./scripts/restore-alert-inbox.sh .env.example "$work" >/dev/null 2>&1; then
  printf 'restore helper accepted a target escaping backups/ through a symlink\n' >&2
  exit 1
fi

rm -f "$work/alert-inbox.sqlite3"
printf 'not sqlite\n' >"$work/alert-inbox.sqlite3"
if ./scripts/restore-alert-inbox.sh .env.example "$work" >/dev/null 2>&1; then
  printf 'restore helper accepted a malformed SQLite snapshot\n' >&2
  exit 1
fi

printf 'restore alert-inbox tests passed\n'
