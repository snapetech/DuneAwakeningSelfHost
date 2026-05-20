#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
read_env() {
  local key="$1"
  local value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

remote="${2:-${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}}"
remote_root="${3:-${POSTGRES_REMOTE_REPLICA_ROOT:-$(read_env POSTGRES_REMOTE_REPLICA_ROOT)}}"
remote_root="${remote_root:-/srv/dune-postgres-replica}"
db="${DUNE_DATABASE:-$(read_env DUNE_DATABASE)}"
db="${db:-dune_sb_1_4_0_0}"
keep_hours="${DUNE_REPLICA_SNAPSHOT_KEEP_HOURS:-$(read_env DUNE_REPLICA_SNAPSHOT_KEEP_HOURS)}"
keep_hours="${keep_hours:-48}"

if [[ -z "$remote" ]]; then
  printf 'remote host required: %s ENV_FILE REMOTE_HOST [REMOTE_ROOT]\n' "$0" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
remote_dir="$remote_root/snapshots"
remote_file="$remote_dir/postgres-${db}-${timestamp}.dump"

ssh "$remote" "mkdir -p '$remote_dir'
docker exec dune-postgres-replica pg_dump -U dune -d '$db' -Fc > '$remote_file'
find '$remote_dir' -type f -name 'postgres-${db}-*.dump' -mmin +$((keep_hours * 60)) -delete
ls -lh '$remote_file'"
