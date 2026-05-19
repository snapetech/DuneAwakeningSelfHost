#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/backup-state.sh [env-file]

Creates a timestamped local backup under backups/.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")
db=dune_sb_1_4_0_0

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
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
container_runtime=${container_runtime}
compose_files=${COMPOSE_FILES:-compose.yaml}
database=${db}
postgres_dump=postgres-${db}.dump
rabbitmq_admin_archive=rabbitmq-admin.tgz
rabbitmq_game_archive=rabbitmq-game.tgz
server_saved_archive=server-saved.tgz
EOF

printf 'backup complete: %s\n' "$backup_dir"
