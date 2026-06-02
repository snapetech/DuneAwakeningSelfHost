#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/start-map-with-post-hooks.sh ENV_FILE SERVICE [SERVICE...]

Manual live-map start/recreate wrapper. Prefer scripts/recover-map.sh when a
fixed-partition map has a stale server id or degraded partition registration.
This wrapper exists for intentional manual starts where raw docker compose up
would otherwise skip post-start hooks.
USAGE
}

if [[ $# -lt 2 ]]; then
  usage
  exit 2
fi

env_file="$1"
shift
services=("$@")
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 2
fi

if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi

compose=(docker compose)
IFS=':' read -r -a compose_files <<< "${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"
for compose_file in "${compose_files[@]}"; do
  [[ -n "$compose_file" ]] && compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

case "${DUNE_REQUIRE_PRODUCTION_HOST_FOR_MANUAL_MAP_START:-true}" in
  1|true|yes|on|TRUE|True|YES|ON)
    current_host="$(hostname)"
    required_host="${DUNE_PRODUCTION_HOSTNAME:-kspls0}"
    if [[ "$current_host" != "$required_host" ]]; then
      printf 'refusing manual live-map start on %s; expected %s\n' "$current_host" "$required_host" >&2
      exit 1
    fi
    ;;
esac

if [[ -x "$script_dir/seed-gateway-neighbor.sh" ]]; then
  "$script_dir/seed-gateway-neighbor.sh" || true
fi

printf 'starting/recreating map services with post hooks: %s\n' "${services[*]}"
"${compose[@]}" up -d --force-recreate --no-deps "${services[@]}"

if [[ -x "$script_dir/seed-gateway-neighbor.sh" ]]; then
  "$script_dir/seed-gateway-neighbor.sh" || true
fi

if [[ -x "$script_dir/restart-post-start-health.sh" ]]; then
  ENV_FILE="$env_file" "$script_dir/restart-post-start-health.sh"
elif [[ -x "$script_dir/verify-rmq-auth-path.sh" ]]; then
  ENV_FILE="$env_file" "$script_dir/verify-rmq-auth-path.sh"
fi

if [[ -x "$script_dir/patch-logoff-timers-runtime.sh" ]]; then
  "$script_dir/patch-logoff-timers-runtime.sh" --local --dry-run
fi

"${compose[@]}" ps "${services[@]}"
