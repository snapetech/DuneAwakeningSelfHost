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

if [[ -f "$backup_dir/community-rewards.sqlite3" ]]; then
  if python3 - "$backup_dir/community-rewards.sqlite3" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    result = connection.execute("pragma integrity_check").fetchone()[0]
finally:
    connection.close()
raise SystemExit(0 if result == "ok" else 1)
PY
  then
    printf 'OK community rewards SQLite snapshot %s\n' "$backup_dir/community-rewards.sqlite3"
  else
    printf 'FAIL community rewards SQLite snapshot %s\n' "$backup_dir/community-rewards.sqlite3" >&2
    ok=false
  fi
else
  printf 'WARN no community-rewards.sqlite3 found in %s\n' "$backup_dir"
fi

if [[ -f "$backup_dir/moderation.sqlite3" ]]; then
  if python3 - "$backup_dir/moderation.sqlite3" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    result = connection.execute("pragma integrity_check").fetchone()[0]
finally:
    connection.close()
raise SystemExit(0 if result == "ok" else 1)
PY
  then
    printf 'OK moderation SQLite snapshot %s\n' "$backup_dir/moderation.sqlite3"
  else
    printf 'FAIL moderation SQLite snapshot %s\n' "$backup_dir/moderation.sqlite3" >&2
    ok=false
  fi
else
  printf 'WARN no moderation.sqlite3 found in %s\n' "$backup_dir"
fi

if [[ -f "$backup_dir/base-gallery.sqlite3" ]]; then
  if python3 - "$backup_dir/base-gallery.sqlite3" <<'PY'
import sqlite3
import sys
connection=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True)
try: result=connection.execute("pragma integrity_check").fetchone()[0]
finally: connection.close()
raise SystemExit(0 if result=="ok" else 1)
PY
  then
    printf 'OK base gallery SQLite snapshot %s\n' "$backup_dir/base-gallery.sqlite3"
  else
    printf 'FAIL base gallery SQLite snapshot %s\n' "$backup_dir/base-gallery.sqlite3" >&2
    ok=false
  fi
else
  printf 'WARN no base-gallery.sqlite3 found in %s\n' "$backup_dir"
fi

if [[ -f "$backup_dir/operational-slo.sqlite3" ]]; then
  if python3 - "$backup_dir/operational-slo.sqlite3" <<'PY'
import hashlib,json,sqlite3,sys
connection=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True)
connection.row_factory=sqlite3.Row
try:
    if connection.execute("pragma integrity_check").fetchone()[0]!="ok": raise SystemExit(1)
    rows=connection.execute("select * from incident_events order by sequence").fetchall()
finally: connection.close()
previous=None
for row in rows:
    document={"incidentId":row["incident_id"],"objectiveId":row["objective_id"],"eventType":row["event_type"],"createdAt":row["created_at"],"actor":row["actor"],"note":row["note"],"payload":json.loads(row["payload_json"]),"previousHash":row["previous_hash"]}
    expected=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if row["previous_hash"]!=previous or row["event_hash"]!=expected: raise SystemExit(1)
    previous=row["event_hash"]
PY
  then
    printf 'OK operational SLO SQLite snapshot and incident hash chain %s\n' "$backup_dir/operational-slo.sqlite3"
  else
    printf 'FAIL operational SLO SQLite snapshot or incident hash chain %s\n' "$backup_dir/operational-slo.sqlite3" >&2
    ok=false
  fi
else
  printf 'WARN no operational-slo.sqlite3 found in %s\n' "$backup_dir"
fi

if [[ -f "$backup_dir/manifest.json" ]]; then
  if command -v jq >/dev/null 2>&1; then
    jq . "$backup_dir/manifest.json" >/dev/null
    printf 'OK manifest %s\n' "$backup_dir/manifest.json"
  else
    printf 'SKIP jq not available for %s\n' "$backup_dir/manifest.json"
  fi
elif [[ -f "$backup_dir/manifest.txt" ]]; then
  printf 'OK manifest %s\n' "$backup_dir/manifest.txt"
  if rg -q '^world_unique_name=.' "$backup_dir/manifest.txt"; then
    printf 'OK manifest world identity present\n'
  else
    printf 'WARN manifest missing world_unique_name\n'
  fi
else
  printf 'WARN no manifest found in %s\n' "$backup_dir"
fi

if [[ -f "$backup_dir/config.tgz" ]]; then
  check_tgz "$backup_dir/config.tgz"
else
  printf 'WARN no config.tgz found in %s\n' "$backup_dir"
fi

if [[ -f "$backup_dir/config-tls.tgz" ]]; then
  check_tgz "$backup_dir/config-tls.tgz"
else
  printf 'WARN no config-tls.tgz found in %s\n' "$backup_dir"
fi

if find "$backup_dir" -maxdepth 1 -type f \( -name '.env' -o -name '*.env' \) | grep -q .; then
  printf 'OK env copy present\n'
else
  printf 'WARN no env copy found in %s\n' "$backup_dir"
fi

if [[ "$ok" == true ]]; then
  printf 'backup verification complete: OK\n'
else
  printf 'backup verification complete: FAILED\n' >&2
  exit 1
fi
