#!/usr/bin/env bash
set -euo pipefail

env_file="${ENV_FILE:-.env}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose_files="${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"
project="${COMPOSE_PROJECT_NAME:-dune_server}"
text_router_service="${TEXT_ROUTER_SERVICE:-text-router}"
text_router_container="${TEXT_ROUTER_CONTAINER:-${project}-${text_router_service}-1}"
postgres_container="${POSTGRES_CONTAINER:-${project}-postgres-1}"
seed_script="${DUNE_SEED_NEIGHBOR_SCRIPT:-./scripts/seed-gateway-neighbor.sh}"
verify_script="${DUNE_VERIFY_RMQ_AUTH_PATH_SCRIPT:-./scripts/verify-rmq-auth-path.sh}"
timeout="${DUNE_RESTART_POST_START_TIMEOUT_SECONDS:-180}"
interval="${DUNE_RESTART_POST_START_INTERVAL_SECONDS:-5}"
logoff_patch_enabled="${DUNE_LOGOFF_TIMER_RUNTIME_PATCH_ENABLED:-true}"

compose_cmd=(docker compose)
IFS=':' read -r -a compose_file_array <<< "$compose_files"
for file in "${compose_file_array[@]}"; do
  [[ -n "$file" ]] && compose_cmd+=(-f "$file")
done
compose_cmd+=(--env-file "$env_file")

is_running() {
  local container="$1"
  [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == "true" ]]
}

seed_neighbors() {
  if [[ -x "$seed_script" ]]; then
    "$seed_script" || true
  fi
}

run_post_start_hooks() {
  if [[ -x "$script_dir/brt-dd-next-downtime.sh" ]]; then
    "$script_dir/brt-dd-next-downtime.sh" apply-pending "$env_file"
  fi
  if [[ "$logoff_patch_enabled" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee][Ss]|[Yy])$ && -x "$script_dir/patch-logoff-timers-runtime.sh" ]]; then
    "$script_dir/patch-logoff-timers-runtime.sh" --local \
      || printf 'warning: logoff timer runtime patch failed after restart\n' >&2
  fi
}

postgres_accepts_connections() {
  is_running "$postgres_container" || return 1
  docker exec "$postgres_container" sh -lc 'pg_isready -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1 || pg_isready >/dev/null 2>&1'
}

deadline=$((SECONDS + timeout))

seed_neighbors

while ! postgres_accepts_connections; do
  if (( SECONDS >= deadline )); then
    printf 'postgres was not connection-ready after %ss\n' "$timeout" >&2
    exit 1
  fi
  sleep "$interval"
done

text_router_recreated=false
while (( SECONDS < deadline )); do
  seed_neighbors

  if ! is_running "$text_router_container"; then
    printf 'text-router is not running after start; recreating it after postgres readiness\n' >&2
    "${compose_cmd[@]}" up -d --force-recreate --no-deps "$text_router_service"
    text_router_recreated=true
    sleep "$interval"
    continue
  fi

  if [[ -x "$verify_script" ]] && "$verify_script"; then
    run_post_start_hooks
    if [[ "$text_router_recreated" == "true" ]]; then
      printf 'post-start recovery recreated text-router and verified RMQ/auth routing\n'
    else
      printf 'post-start RMQ/auth routing verified\n'
    fi
    exit 0
  fi

  sleep "$interval"
done

printf 'post-start health checks did not pass after %ss\n' "$timeout" >&2
if [[ -x "$verify_script" ]]; then
  "$verify_script" || true
fi
exit 1
