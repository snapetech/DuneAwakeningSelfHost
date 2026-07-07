#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: ./scripts/hotfix-auto-update-and-restart.sh [env-file]

Polls the owned Steam package for Dune hotfixes, loads updated Funcom Docker
images, writes DUNE_IMAGE_TAG when needed, and restarts the live farm only when
the package changed. Intended for systemd timer use on kspls0.
USAGE
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

env_file="${1:-.env}"
script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -- "$(dirname -- "$script_path")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

if [[ "$(hostname)" != "kspls0" ]]; then
  printf 'fail: must run on kspls0; current host is %s\n' "$(hostname)" >&2
  exit 1
fi

if [[ ! -f "$env_file" ]]; then
  printf 'fail: env file not found: %s\n' "$env_file" >&2
  exit 1
fi

lock_file="${DUNE_HOTFIX_UPDATE_LOCK_FILE:-/tmp/dune-hotfix-auto-update.lock}"
exec 9>"$lock_file"
if ! flock -n 9; then
  printf 'another hotfix update run is already active; exiting\n'
  exit 0
fi

export DUNE_RESTART_CHECK_STEAM_UPDATE=false
"$script_dir/update-owned-steam-build-and-restart.sh" \
  "$env_file" \
  --yes \
  --non-interactive \
  --restart-only-on-update
