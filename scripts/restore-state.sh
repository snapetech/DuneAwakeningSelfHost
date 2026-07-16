#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/restore-state.sh [--dry-run] [--rabbitmq] [--server-saved] [--config] [--tls] [--community-rewards] [--moderation] [--base-gallery] [--operational-slo] [env-file] <backup-dir>

Restores the Postgres dump from a backup created by scripts/backup-state.sh.
RabbitMQ and server saved-state archives are restored only when their flags are
provided because they replace local data directories.
Config and TLS archives are also opt-in because they can replace the current
world identity, secrets, local tuning, and RabbitMQ certificate material.

Examples:
  ./scripts/restore-state.sh --dry-run .env backups/20260519T150000Z
  ./scripts/restore-state.sh .env backups/20260519T150000Z
  ./scripts/restore-state.sh --rabbitmq --server-saved --config --tls --community-rewards --moderation --base-gallery --operational-slo .env backups/20260519T150000Z
EOF
}

dry_run=false
restore_rabbitmq=false
restore_server_saved=false
restore_config=false
restore_tls=false
restore_community_rewards=false
restore_moderation=false
restore_base_gallery=false
restore_operational_slo=false

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
    --config)
      restore_config=true
      shift
      ;;
    --tls)
      restore_tls=true
      shift
      ;;
    --community-rewards)
      restore_community_rewards=true
      shift
      ;;
    --moderation)
      restore_moderation=true
      shift
      ;;
    --base-gallery)
      restore_base_gallery=true
      shift
      ;;
    --operational-slo)
      restore_operational_slo=true
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

manifest_value() {
  local key="$1"
  [[ -f "${backup_dir}/manifest.txt" ]] || return 0
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "${backup_dir}/manifest.txt"
}

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

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

if [[ "$restore_config" == true && ! -f "${backup_dir}/config.tgz" ]]; then
  printf 'config archive not found: %s\n' "${backup_dir}/config.tgz" >&2
  exit 1
fi

if [[ "$restore_tls" == true && ! -f "${backup_dir}/config-tls.tgz" ]]; then
  printf 'TLS archive not found: %s\n' "${backup_dir}/config-tls.tgz" >&2
  exit 1
fi

if [[ "$restore_community_rewards" == true && ! -f "${backup_dir}/community-rewards.sqlite3" ]]; then
  printf 'community rewards snapshot not found: %s\n' "${backup_dir}/community-rewards.sqlite3" >&2
  exit 1
fi

if [[ "$restore_moderation" == true && ! -f "${backup_dir}/moderation.sqlite3" ]]; then
  printf 'moderation snapshot not found: %s\n' "${backup_dir}/moderation.sqlite3" >&2
  exit 1
fi
if [[ "$restore_base_gallery" == true && ! -f "${backup_dir}/base-gallery.sqlite3" ]]; then
  printf 'base gallery snapshot not found: %s\n' "${backup_dir}/base-gallery.sqlite3" >&2
  exit 1
fi
if [[ "$restore_operational_slo" == true && ! -f "${backup_dir}/operational-slo.sqlite3" ]]; then
  printf 'operational SLO snapshot not found: %s\n' "${backup_dir}/operational-slo.sqlite3" >&2
  exit 1
fi

backup_world="$(manifest_value world_unique_name)"
current_world="$(env_value WORLD_UNIQUE_NAME)"
if [[ -n "$backup_world" && -n "$current_world" && "$backup_world" != "$current_world" ]]; then
  printf 'warn: backup WORLD_UNIQUE_NAME=%s differs from current %s\n' "$backup_world" "$current_world" >&2
  printf 'warn: restoring this backup under a different world identity can change FLS battlegroup behavior\n' >&2
fi

if [[ "$dry_run" == true ]]; then
  printf 'restore dry run OK\n'
  printf 'env_file=%s\n' "$env_file"
  printf 'backup_dir=%s\n' "$backup_dir"
  printf 'postgres_dump=%s\n' "$dump_file"
  printf 'restore_rabbitmq=%s\n' "$restore_rabbitmq"
  printf 'restore_server_saved=%s\n' "$restore_server_saved"
  printf 'restore_config=%s\n' "$restore_config"
  printf 'restore_tls=%s\n' "$restore_tls"
  printf 'restore_community_rewards=%s\n' "$restore_community_rewards"
  printf 'restore_moderation=%s\n' "$restore_moderation"
  printf 'restore_base_gallery=%s\n' "$restore_base_gallery"
  printf 'restore_operational_slo=%s\n' "$restore_operational_slo"
  printf 'backup_world_unique_name=%s\n' "${backup_world:-}"
  printf 'current_world_unique_name=%s\n' "${current_world:-}"
  exit 0
fi

printf 'stopping write services\n'
"${compose[@]}" stop survival director gateway text-router rmq-auth-shim admin-rmq game-rmq admin-panel || true

if [[ "$restore_community_rewards" == true ]]; then
  printf 'restoring isolated community rewards state from %s\n' "${backup_dir}/community-rewards.sqlite3"
  mkdir -p backups/community-rewards
  rm -f backups/community-rewards/community.sqlite3-wal backups/community-rewards/community.sqlite3-shm
  install -m 600 "${backup_dir}/community-rewards.sqlite3" backups/community-rewards/community.sqlite3
fi

if [[ "$restore_moderation" == true ]]; then
  printf 'restoring isolated moderation state from %s\n' "${backup_dir}/moderation.sqlite3"
  mkdir -p backups/moderation
  rm -f backups/moderation/moderation.sqlite3-wal backups/moderation/moderation.sqlite3-shm
  install -m 600 "${backup_dir}/moderation.sqlite3" backups/moderation/moderation.sqlite3
fi
if [[ "$restore_base_gallery" == true ]]; then
  printf 'restoring isolated base gallery state from %s\n' "${backup_dir}/base-gallery.sqlite3"
  mkdir -p backups/base-gallery
  rm -f backups/base-gallery/gallery.sqlite3-wal backups/base-gallery/gallery.sqlite3-shm
  install -m 600 "${backup_dir}/base-gallery.sqlite3" backups/base-gallery/gallery.sqlite3
fi
if [[ "$restore_operational_slo" == true ]]; then
  printf 'restoring isolated operational SLO state from %s\n' "${backup_dir}/operational-slo.sqlite3"
  mkdir -p backups/operational-slo
  rm -f backups/operational-slo/slo.sqlite3-wal backups/operational-slo/slo.sqlite3-shm
  install -m 600 "${backup_dir}/operational-slo.sqlite3" backups/operational-slo/slo.sqlite3
fi

if [[ "$restore_config" == true ]]; then
  printf 'restoring config files from %s\n' "${backup_dir}/config.tgz"
  tar -xzf "${backup_dir}/config.tgz"
fi

if [[ "$restore_tls" == true ]]; then
  printf 'restoring TLS material from %s\n' "${backup_dir}/config-tls.tgz"
  rm -rf config/tls
  tar -xzf "${backup_dir}/config-tls.tgz"
fi

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
printf '  %s compose --env-file %s up -d admin-rmq game-rmq rmq-auth-shim text-router gateway director admin-panel admin-panel-ingress\n' "$container_runtime" "$env_file"
