#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/restore-state.sh [--dry-run] [--rabbitmq] [--server-saved] [env-file] <backup-dir>

Restores the Postgres dump from a backup created by scripts/backup-state.sh.
RabbitMQ and server saved-state archives are restored only when their flags are
provided because they replace local data directories.

Examples:
  ./scripts/restore-state.sh --dry-run .env backups/20260519T150000Z
  ./scripts/restore-state.sh .env backups/20260519T150000Z
  ./scripts/restore-state.sh --rabbitmq --server-saved .env backups/20260519T150000Z
EOF
}

dry_run=false
restore_rabbitmq=false
restore_server_saved=false

while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --dry-run)
      dry_run=true
      shift
      ;;
    --rabbitmq)
      restore_rabbitmq=true
      shift
      ;;
    --server-saved)
      restore_server_saved=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

env_file=".env"
backup_dir="${1:-}"

if [[ "${2:-}" != "" ]]; then
  env_file="$1"
  backup_dir="$2"
fi

if [[ -z "$backup_dir" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

if [[ ! -d "$backup_dir" ]]; then
  printf 'backup dir not found: %s\n' "$backup_dir" >&2
  exit 1
fi

case "$backup_dir" in
  backups/*) ;;
  *)
    printf 'refusing to restore from outside ignored backups/: %s\n' "$backup_dir" >&2
    exit 1
    ;;
esac

container_runtime="${CONTAINER_RUNTIME:-docker}"
if ! command -v "$container_runtime" >/dev/null 2>&1; then
  printf '%s is required\n' "$container_runtime" >&2
  exit 1
fi

db=dune_sb_1_4_0_0
dump_file="${backup_dir}/postgres-${db}.dump"
compose=("$container_runtime" compose --env-file "$env_file")

if [[ ! -f "$dump_file" ]]; then
  printf 'postgres dump not found: %s\n' "$dump_file" >&2
  exit 1
fi

if [[ "$restore_rabbitmq" == true ]]; then
  for archive in "${backup_dir}/rabbitmq-admin.tgz" "${backup_dir}/rabbitmq-game.tgz"; do
    if [[ ! -f "$archive" ]]; then
      printf 'rabbitmq archive not found: %s\n' "$archive" >&2
      exit 1
    fi
  done
fi

if [[ "$restore_server_saved" == true ]]; then
  archive="${backup_dir}/server-saved.tgz"
  if [[ ! -f "$archive" ]]; then
    printf 'server saved archive not found: %s\n' "$archive" >&2
    exit 1
  fi
fi

if [[ "$dry_run" == true ]]; then
  printf 'restore dry run OK\n'
  printf 'env_file=%s\n' "$env_file"
  printf 'backup_dir=%s\n' "$backup_dir"
  printf 'postgres_dump=%s\n' "$dump_file"
  printf 'restore_rabbitmq=%s\n' "$restore_rabbitmq"
  printf 'restore_server_saved=%s\n' "$restore_server_saved"
  exit 0
fi

printf 'stopping write services\n'
"${compose[@]}" stop survival director gateway text-router rmq-auth-shim admin-rmq game-rmq || true

if [[ "$restore_rabbitmq" == true ]]; then
  printf 'restoring RabbitMQ state from %s\n' "$backup_dir"
  rm -rf data/rabbitmq
  mkdir -p data/rabbitmq/admin data/rabbitmq/game
  tar -xzf "${backup_dir}/rabbitmq-admin.tgz" -C data/rabbitmq/admin
  tar -xzf "${backup_dir}/rabbitmq-game.tgz" -C data/rabbitmq/game
fi

if [[ "$restore_server_saved" == true ]]; then
  archive="${backup_dir}/server-saved.tgz"
  if [[ ! -f "$archive" ]]; then
    printf 'server saved archive not found: %s\n' "$archive" >&2
    exit 1
  fi
  printf 'restoring server saved state from %s\n' "$archive"
  rm -rf data/server-saved
  mkdir -p data/server-saved
  tar -xzf "$archive" -C data/server-saved
fi

printf 'starting postgres\n'
"${compose[@]}" up -d postgres

printf 'restoring postgres from %s\n' "$dump_file"
"${compose[@]}" exec -T postgres \
  pg_restore -U dune -d "$db" --clean --if-exists \
  < "$dump_file"

printf 'restore complete. Start remaining services when ready:\n'
printf '  %s compose --env-file %s up -d admin-rmq game-rmq rmq-auth-shim text-router gateway director\n' "$container_runtime" "$env_file"
