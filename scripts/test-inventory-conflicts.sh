#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
BIN_DIR="$TMP_DIR/bin"
LOG_FILE="$TMP_DIR/runtime.log"
ENV_FILE="$TMP_DIR/test.env"
BACKUP_ROOT="$TMP_DIR/backups"
mkdir -p "$BIN_DIR"
printf 'DUNE_IMAGE_TAG=test\n' >"$ENV_FILE"

cat >"$BIN_DIR/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$LOG_FILE"
if [[ "$*" == *"pg_dump"* ]]; then
  printf 'valid-custom-dump-fixture\n'
  exit 0
fi
if [[ "$*" == *"psql"* && "$*" == *"-f -"* ]]; then
  sql="$(cat)"
  printf '%s\n' "$sql" >>"$SQL_LOG_FILE"
  if [[ "$sql" == *"update dune.items"* ]]; then
    printf 'moved\t102\t7\t3\t4\tSilicone\n'
  else
    printf 'duplicate\t7\t3\t2\t{101,102}\t{Silicone,Silicone}\n'
  fi
  exit 0
fi
if [[ "$*" == *"having count(*) > 1"* && "$*" == *"select count(*)"* ]]; then
  printf '1\n'
  exit 0
fi
if [[ "$*" == *"psql"* ]]; then
  printf 'duplicate\t7\t3\t2\t{101,102}\t{Silicone,Silicone}\n'
  exit 0
fi
echo "unexpected docker invocation: $*" >&2
exit 1
EOF

cat >"$BIN_DIR/hostname" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${TEST_HOSTNAME:-kspld0}"
EOF
chmod +x "$BIN_DIR/docker" "$BIN_DIR/hostname"

export PATH="$BIN_DIR:$PATH"
export LOG_FILE SQL_LOG_FILE="$TMP_DIR/sql.log"
export DUNE_INVENTORY_BACKUP_ROOT="$BACKUP_ROOT"

sql="$($ROOT_DIR/scripts/inventory-conflicts.sh --print-repair-sql)"
grep -q 'lock table dune.items' <<<"$sql"
grep -q 'target_total <> assignment_total' <<<"$sql"
grep -q 'update dune.items' <<<"$sql"
grep -q "affected inventory owner is online" <<<"$sql"
! grep -qi 'delete from dune.items' <<<"$sql"

excluded_sql="$($ROOT_DIR/scripts/inventory-conflicts.sh --print-repair-sql --exclude-inventory 14)"
grep -q 'inventory_id not in (14)' <<<"$excluded_sql"

if "$ROOT_DIR/scripts/inventory-conflicts.sh" --env-file "$ENV_FILE" audit >/dev/null 2>&1; then
  echo "audit did not signal detected duplicate slots" >&2
  exit 1
fi
! grep -q 'pg_dump' "$LOG_FILE"

preview="$($ROOT_DIR/scripts/inventory-conflicts.sh --env-file "$ENV_FILE" repair)"
grep -q 'Dry-run only' <<<"$preview"
! grep -q 'pg_dump' "$LOG_FILE"

if "$ROOT_DIR/scripts/inventory-conflicts.sh" --env-file "$ENV_FILE" repair --execute --confirm WRONG >/dev/null 2>&1; then
  echo "repair accepted the wrong confirmation" >&2
  exit 1
fi

if "$ROOT_DIR/scripts/inventory-conflicts.sh" --env-file "$ENV_FILE" repair --execute \
  --confirm 'REPAIR INVENTORY SLOT CONFLICTS' >/dev/null 2>&1; then
  echo "repair accepted the lab hostname without an override" >&2
  exit 1
fi
! grep -q 'pg_dump' "$LOG_FILE"

export TEST_HOSTNAME=kspls0
result="$($ROOT_DIR/scripts/inventory-conflicts.sh --env-file "$ENV_FILE" repair --execute \
  --confirm 'REPAIR INVENTORY SLOT CONFLICTS')"
grep -q 'committed and verified' <<<"$result"
grep -q 'pg_dump' "$LOG_FILE"
grep -q 'update dune.items' "$SQL_LOG_FILE"
dump="$(find "$BACKUP_ROOT" -name 'postgres-*.dump' -type f -print -quit)"
[[ -n "$dump" && -s "$dump" ]]
find "$BACKUP_ROOT" -name manifest.txt -type f -exec grep -q 'hostname=kspls0' {} \;

echo "inventory conflict tests passed"
