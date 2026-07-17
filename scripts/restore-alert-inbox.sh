#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/restore-alert-inbox.sh [--execute] [env-file] <backup-dir>

Verifies and plans restoration of only alert-inbox.sqlite3. Execution is
hostname-gated, stops/recreates only admin-panel, preserves a private rollback
copy, and rolls back automatically if the admin container does not become
healthy. Game-map, database, and broker services are never targeted.
EOF
}

execute=false
if [[ "${1:-}" == "--execute" ]]; then execute=true; shift; fi
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; exit 0; fi

env_file=".env"
backup_dir="${1:-}"
if [[ -n "${2:-}" ]]; then env_file="$1"; backup_dir="$2"; fi
[[ -f "$env_file" ]] || { printf 'env file not found: %s\n' "$env_file" >&2; exit 1; }
[[ -d "$backup_dir" ]] || { printf 'backup directory not found: %s\n' "$backup_dir" >&2; exit 1; }
case "$backup_dir" in backups/*) ;; *) printf 'backup directory must be under backups/: %s\n' "$backup_dir" >&2; exit 1;; esac

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$0 ~ "^[[:space:]]*" key "=" {sub(/^[^=]*=/, ""); gsub(/^['"'"']|['"'"']$/, ""); print; exit}' "$env_file"
}

source_snapshot="$backup_dir/alert-inbox.sqlite3"
[[ -f "$source_snapshot" && ! -L "$source_snapshot" ]] || { printf 'safe alert-inbox snapshot not found: %s\n' "$source_snapshot" >&2; exit 1; }
target="${DUNE_ALERT_INBOX_HOST_DATABASE:-$(env_value DUNE_ALERT_INBOX_HOST_DATABASE)}"
target="${target:-backups/alert-inbox/inbox.sqlite3}"
case "$target" in backups/*) ;; *) printf 'alert-inbox target must be under backups/: %s\n' "$target" >&2; exit 1;; esac

PYTHONPATH=admin python3 - "$source_snapshot" "$target" <<'PY'
import pathlib,sqlite3,sys
import alert_inbox
path,target=map(pathlib.Path,sys.argv[1:])
root=(pathlib.Path.cwd()/"backups").resolve()
source_resolved=path.resolve(strict=True)
target_parent=target.parent.resolve(strict=False)
if root != source_resolved and root not in source_resolved.parents: raise SystemExit("alert-inbox source escapes backups/")
if root != target_parent and root not in target_parent.parents: raise SystemExit("alert-inbox target escapes backups/")
if path.stat().st_size > 1024 * 1024 * 1024: raise SystemExit("alert-inbox snapshot exceeds 1 GiB")
db=sqlite3.connect(f"file:{path}?mode=ro",uri=True)
try:
    integrity=db.execute("pragma integrity_check").fetchone()[0]
    tables={row[0] for row in db.execute("select name from sqlite_master where type='table'")}
finally: db.close()
if integrity != "ok" or not {"alerts","transitions","metadata"} <= tables or alert_inbox.SCHEMA != "dash-alert-inbox/v1":
    raise SystemExit("alert-inbox snapshot integrity/schema verification failed")
PY

required_host="${DUNE_PRODUCTION_HOST:-$(env_value DUNE_PRODUCTION_HOST)}"
required_host="${required_host:-kspls0}"
compose_files="$(scripts/compose-files.sh "$env_file")"
IFS=: read -r -a files <<<"$compose_files"
compose=(docker compose --env-file "$env_file")
for file in "${files[@]}"; do compose+=(-f "$file"); done

printf 'alert-inbox restore plan OK\n'
printf 'source=%s\n' "$source_snapshot"
printf 'target=%s\n' "$target"
printf 'required_host=%s\n' "$required_host"
printf 'services=admin-panel\n'
printf 'game_map_lifecycle=false\n'
if [[ "$execute" != true ]]; then exit 0; fi

actual_host="$(hostname -s 2>/dev/null || hostname)"
[[ "$actual_host" == "$required_host" ]] || { printf 'refusing alert-inbox restore on %s; expected %s\n' "$actual_host" "$required_host" >&2; exit 1; }

install -d -m 700 "$(dirname "$target")"
rollback="$(dirname "$target")/pre-restore-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
had_previous=false
if [[ -f "$target" ]]; then install -m 600 "$target" "$rollback"; had_previous=true; fi

restore_previous() {
  if [[ "$had_previous" == true && -f "$rollback" ]]; then
    install -m 600 "$rollback" "$target"
  else
    rm -f "$target"
  fi
  rm -f "${target}-wal" "${target}-shm"
  "${compose[@]}" up -d --no-deps admin-panel >/dev/null || true
}

"${compose[@]}" stop admin-panel >/dev/null
rm -f "${target}-wal" "${target}-shm"
install -m 600 "$source_snapshot" "$target"
if ! "${compose[@]}" up -d --no-deps admin-panel >/dev/null; then
  restore_previous
  printf 'admin-panel start failed; prior alert inbox restored\n' >&2
  exit 1
fi

healthy=false
for _attempt in $(seq 1 30); do
  container_id="$("${compose[@]}" ps -q admin-panel 2>/dev/null || true)"
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
  if [[ "$state" == "healthy" || "$state" == "running" ]]; then healthy=true; break; fi
  sleep 2
done
if [[ "$healthy" != true ]]; then
  "${compose[@]}" stop admin-panel >/dev/null || true
  restore_previous
  printf 'admin-panel did not recover; prior alert inbox restored\n' >&2
  exit 1
fi
printf 'alert-inbox restore complete: %s\n' "$target"
printf 'rollback_copy=%s\n' "${rollback:-none}"
