#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

remote="${2:-${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}}"
remote_repo="${DUNE_STANDBY_REPO_ROOT:-$PWD}"
extra_paths="${DUNE_STANDBY_EXTRA_SYNC_PATHS:-$(read_env DUNE_STANDBY_EXTRA_SYNC_PATHS)}"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
if [[ -z "$remote" ]]; then
  printf 'remote host required: %s ENV_FILE REMOTE\n' "$0" >&2
  exit 1
fi

ssh "$remote" "mkdir -p '$remote_repo'"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'data/postgres/' \
  --exclude 'data/postgres-replica/' \
  --exclude 'data/rabbitmq/' \
  --exclude 'config/tls/rabbitmq-staged/' \
  --exclude 'config/tls/rabbitmq-staged.backup.*/' \
  --exclude 'captures/' \
  --exclude 'backups/' \
  --exclude 'public-site/output/' \
  ./ "$remote:$remote_repo/"

printf 'synced standby runtime files to %s:%s\n' "$remote" "$remote_repo"
printf 'note: data/postgres is not mirrored by rsync; it is owned by streaming replication.\n'

if [[ -n "$extra_paths" ]]; then
  printf 'syncing extra failover paths\n'
  IFS=':' read -ra paths <<< "$extra_paths"
  for path in "${paths[@]}"; do
    [[ -z "$path" ]] && continue
    if [[ ! -e "$path" ]]; then
      printf 'WARN extra sync path missing locally: %s\n' "$path" >&2
      continue
    fi
    parent="$(dirname "$path")"
    ssh "$remote" "mkdir -p '$parent'"
    rsync -a --delete "$path" "$remote:$parent/"
    printf 'synced %s to %s:%s\n' "$path" "$remote" "$parent"
  done
fi
