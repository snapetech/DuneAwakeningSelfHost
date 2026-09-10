#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/recover-publication.sh ENV_FILE

Recreates the Director/Gateway publication path through restart-target.sh and
then runs the normal post-start health hooks.
USAGE
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

env_file="$1"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

if [[ ! -x "$script_dir/restart-target.sh" ]]; then
  printf 'restart-target.sh is missing or not executable\n' >&2
  exit 1
fi

ENV_FILE="$env_file" \
DUNE_RESTART_CHECK_STEAM_UPDATE=false \
DUNE_RESTART_SERVICES='director gateway' \
DUNE_RESTART_ACTION=restart \
DUNE_RESTART_PHASE=restart \
DUNE_RESTART_USE_HOST_COMPOSE=true \
"$script_dir/restart-target.sh" publication
