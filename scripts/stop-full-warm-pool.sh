#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-$repo_root/.env}"
if [[ "$env_file" != /* ]]; then
  env_file="$repo_root/$env_file"
fi
if [[ ! -f "$env_file" ]]; then
  printf 'env file does not exist: %s\n' "$env_file" >&2
  exit 1
fi

cd "$repo_root"
if grep -Eq '^DUNE_SIETCH_MUTATIONS_ENABLED=(1|true|yes|on)$' "$env_file"; then
  "$repo_root/scripts/sietches.sh" "$env_file" stop-managed --execute
fi
export ENV_FILE="$env_file"
export DUNE_RESTART_TARGET=all
export DUNE_RESTART_ACTION=shutdown
export DUNE_RESTART_PHASE=shutdown
export DUNE_RESTART_CHECK_STEAM_UPDATE=false
exec "$repo_root/scripts/restart-target.sh" all
