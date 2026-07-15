#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

if [[ $(hostname) != "kspld0" ]]; then
  echo "error: local DASH launcher is restricted to kspld0" >&2
  exit 1
fi

mapfile -d '' admin_env < <(
  docker compose config --format json |
    jq -j '.services["admin-panel"].environment | to_entries[] | .key,"=",(.value|tostring),"\u0000"'
)
export "${admin_env[@]}"
export ADMIN_WORKSPACE="$ROOT"
export DUNE_ADMIN_BIND=127.0.0.1
export DUNE_ADMIN_PORT=18080
export DUNE_ADMIN_DB_HOST=127.0.0.1
export DUNE_ADMIN_DB_PORT=15431
export DUNE_ADMIN_ALLOWED_HOSTS="127.0.0.1:18080,localhost:18080"
export DUNE_ADMIN_MUTATIONS_ENABLED=true
export DUNE_ADMIN_ITEM_GRANTS_ENABLED=true

exec python3 admin/admin_panel.py
