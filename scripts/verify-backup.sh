#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/verify-backup.sh BACKUP_DIR

Checks that a DASH backup directory has readable dump/archive files.
This is a structural verification only; it does not perform a full restore.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

backup_dir="${1:-}"
if [[ -z "$backup_dir" || ! -d "$backup_dir" ]]; then
  printf 'backup directory required\n' >&2
  usage >&2
  exit 1
fi

ok=true

check_dump() {
  local dump="$1"
  if ! command -v pg_restore >/dev/null 2>&1; then
    printf 'SKIP pg_restore not available for %s\n' "$dump"
    return 0
  fi
  if pg_restore --list "$dump" >/dev/null; then
    printf 'OK dump %s\n' "$dump"
  else
    printf 'FAIL dump %s\n' "$dump" >&2
    ok=false
  fi
}

check_tgz() {
  local archive="$1"
  if tar -tzf "$archive" >/dev/null; then
    printf 'OK archive %s\n' "$archive"
  else
    printf 'FAIL archive %s\n' "$archive" >&2
    ok=false
  fi
}

shopt -s nullglob
dumps=("$backup_dir"/*.dump)
archives=("$backup_dir"/*.tgz)
if [[ -d "$backup_dir"/maintenance ]]; then
  dumps+=("$backup_dir"/maintenance/*/*.dump)
  archives+=("$backup_dir"/maintenance/*/*.tgz)
fi

if [[ "${#dumps[@]}" -eq 0 ]]; then
  printf 'FAIL no Postgres dump files found under %s\n' "$backup_dir" >&2
  ok=false
fi

for dump in "${dumps[@]}"; do
  check_dump "$dump"
done
for archive in "${archives[@]}"; do
  check_tgz "$archive"
done

if [[ -f "$backup_dir/manifest.json" ]]; then
  if command -v jq >/dev/null 2>&1; then
    jq . "$backup_dir/manifest.json" >/dev/null
    printf 'OK manifest %s\n' "$backup_dir/manifest.json"
  else
    printf 'SKIP jq not available for %s\n' "$backup_dir/manifest.json"
  fi
elif [[ -f "$backup_dir/manifest.txt" ]]; then
  printf 'OK manifest %s\n' "$backup_dir/manifest.txt"
else
  printf 'WARN no manifest found in %s\n' "$backup_dir"
fi

if [[ "$ok" == true ]]; then
  printf 'backup verification complete: OK\n'
else
  printf 'backup verification complete: FAILED\n' >&2
  exit 1
fi
