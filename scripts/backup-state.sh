#!/usr/bin/env bash
set -euo pipefail
umask 077

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
community_db="${DUNE_COMMUNITY_REWARDS_HOST_DATABASE:-backups/community-rewards/community.sqlite3}"
community_snapshot=""
[[ -f "$community_db" ]] && community_snapshot="community-rewards.sqlite3"
moderation_db="${DUNE_MODERATION_HOST_DATABASE:-backups/moderation/moderation.sqlite3}"
moderation_snapshot=""
[[ -f "$moderation_db" ]] && moderation_snapshot="moderation.sqlite3"
base_gallery_db="${DUNE_BASE_GALLERY_HOST_DATABASE:-backups/base-gallery/gallery.sqlite3}"
base_gallery_snapshot=""
[[ -f "$base_gallery_db" ]] && base_gallery_snapshot="base-gallery.sqlite3"
slo_db="${DUNE_OPERATIONAL_SLO_HOST_DATABASE:-backups/operational-slo/slo.sqlite3}"
slo_snapshot=""
[[ -f "$slo_db" ]] && slo_snapshot="operational-slo.sqlite3"
db="${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}"
db="${db:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
db="${db:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
db="${db:-dune_sb_1_4_0_0}"

if [[ "$dry_run" == true ]]; then
  printf 'backup dry run OK\n'
  printf 'env_file=%s\n' "$env_file"
  printf 'env_copy=%s\n' "$(basename "$env_file")"
  printf 'config_archive=config.tgz\n'
  if [[ -f "$community_db" ]]; then
    printf 'community_rewards_snapshot=community-rewards.sqlite3\n'
  else
    printf 'community_rewards_snapshot=<missing %s>\n' "$community_db"
  fi
  if [[ -f "$moderation_db" ]]; then
    printf 'moderation_snapshot=moderation.sqlite3\n'
  else
    printf 'moderation_snapshot=<missing %s>\n' "$moderation_db"
  fi
  if [[ -f "$base_gallery_db" ]]; then
    printf 'base_gallery_snapshot=base-gallery.sqlite3\n'
  else
    printf 'base_gallery_snapshot=<missing %s>\n' "$base_gallery_db"
  fi
  if [[ -f "$slo_db" ]]; then
    printf 'operational_slo_snapshot=operational-slo.sqlite3\n'
  else
    printf 'operational_slo_snapshot=<missing %s>\n' "$slo_db"
  fi
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

if [[ -f "$community_db" ]]; then
  python3 - "$community_db" "${backup_dir}/community-rewards.sqlite3" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("pragma integrity_check").fetchone()[0] != "ok":
        raise SystemExit("community rewards snapshot failed integrity_check")
finally:
    target.close()
    source.close()
PY
  chmod 600 "${backup_dir}/community-rewards.sqlite3"
fi

if [[ -f "$moderation_db" ]]; then
  python3 - "$moderation_db" "${backup_dir}/moderation.sqlite3" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("pragma integrity_check").fetchone()[0] != "ok":
        raise SystemExit("moderation snapshot failed integrity_check")
finally:
    target.close()
    source.close()
PY
  chmod 600 "${backup_dir}/moderation.sqlite3"
fi

if [[ -f "$base_gallery_db" ]]; then
  python3 - "$base_gallery_db" "${backup_dir}/base-gallery.sqlite3" <<'PY'
import sqlite3
import sys
source=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True)
target=sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("pragma integrity_check").fetchone()[0]!="ok": raise SystemExit("base gallery snapshot failed integrity_check")
finally:
    target.close(); source.close()
PY
  chmod 600 "${backup_dir}/base-gallery.sqlite3"
fi

if [[ -f "$slo_db" ]]; then
  python3 - "$slo_db" "${backup_dir}/operational-slo.sqlite3" <<'PY'
import sqlite3
import sys
source=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True)
target=sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("pragma integrity_check").fetchone()[0]!="ok": raise SystemExit("operational SLO snapshot failed integrity_check")
finally:
    target.close(); source.close()
PY
  chmod 600 "${backup_dir}/operational-slo.sqlite3"
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
community_rewards_snapshot=${community_snapshot}
moderation_snapshot=${moderation_snapshot}
base_gallery_snapshot=${base_gallery_snapshot}
operational_slo_snapshot=${slo_snapshot}
world_unique_name=${world_unique_name}
dune_fls_env=${dune_fls_env:-retail}
game_rmq_public_host=${game_rmq_public_host}
EOF

printf 'backup complete: %s\n' "$backup_dir"
