#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/backup-state.sh [--dry-run] [env-file]

Creates a timestamped local backup under backups/.
Use --dry-run to report planned identity/config/TLS backup layers without
contacting Docker or writing a backup directory.
EOF
}

dry_run=false
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --dry-run)
      dry_run=true
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

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

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

world_unique_name="$(env_value WORLD_UNIQUE_NAME)"
dune_fls_env="$(env_value DUNE_FLS_ENV)"
game_rmq_public_host="$(env_value GAME_RMQ_PUBLIC_HOST)"
db="${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}"
db="${db:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
db="${db:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
db="${db:-dune_sb_1_4_0_0}"

if [[ "$dry_run" == true ]]; then
  printf 'backup dry run OK\n'
  printf 'env_file=%s\n' "$env_file"
  printf 'env_copy=%s\n' "$(basename "$env_file")"
  printf 'config_archive=config.tgz\n'
  if [[ -d config/tls ]]; then
    printf 'config_tls_archive=config-tls.tgz\n'
  else
    printf 'config_tls_archive=<missing config/tls>\n'
  fi
  printf 'world_unique_name=%s\n' "${world_unique_name:-}"
  printf 'dune_fls_env=%s\n' "${dune_fls_env:-retail}"
  printf 'game_rmq_public_host=%s\n' "${game_rmq_public_host:-}"
  exit 0
fi

if ! command -v "$container_runtime" >/dev/null 2>&1; then
  printf '%s is required\n' "$container_runtime" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="backups/${timestamp}"

case "$backup_dir" in
  backups/*) ;;
  *)
    printf 'refusing to write backup outside ignored backups/: %s\n' "$backup_dir" >&2
    exit 1
    ;;
esac

mkdir -p "$backup_dir"

printf 'writing backup: %s\n' "$backup_dir"

env_base="$(basename "$env_file")"
cp "$env_file" "${backup_dir}/${env_base}"
tar --exclude='config/tls' --exclude='config/tls/**' -czf "${backup_dir}/config.tgz" config
if [[ -d config/tls ]]; then
  tar -czf "${backup_dir}/config-tls.tgz" config/tls
fi

"${compose[@]}" exec -T postgres \
  pg_dump -U dune -d "$db" -Fc \
  > "${backup_dir}/postgres-${db}.dump"

if "${compose[@]}" ps --services --filter status=running | grep -qx admin-rmq; then
  "${compose[@]}" exec -T admin-rmq tar -czf - -C /var/lib/rabbitmq . \
    > "${backup_dir}/rabbitmq-admin.tgz"
fi

if "${compose[@]}" ps --services --filter status=running | grep -qx game-rmq; then
  "${compose[@]}" exec -T game-rmq tar -czf - -C /var/lib/rabbitmq . \
    > "${backup_dir}/rabbitmq-game.tgz"
fi

if "${compose[@]}" ps --services --filter status=running | grep -qx survival; then
  "${compose[@]}" exec -T survival tar -czf - -C /home/dune/server/DuneSandbox/Saved . \
    > "${backup_dir}/server-saved.tgz"
elif [[ -d data/server-saved ]]; then
  tar -czf "${backup_dir}/server-saved.tgz" data/server-saved
fi

cat > "${backup_dir}/manifest.txt" <<EOF
created_utc=${timestamp}
env_file=${env_file}
env_archive=${env_base}
container_runtime=${container_runtime}
compose_files=${COMPOSE_FILES:-compose.yaml}
database=${db}
postgres_dump=postgres-${db}.dump
rabbitmq_admin_archive=rabbitmq-admin.tgz
rabbitmq_game_archive=rabbitmq-game.tgz
server_saved_archive=server-saved.tgz
config_archive=config.tgz
config_tls_archive=config-tls.tgz
world_unique_name=${world_unique_name}
dune_fls_env=${dune_fls_env:-retail}
game_rmq_public_host=${game_rmq_public_host}
EOF

printf 'backup complete: %s\n' "$backup_dir"
