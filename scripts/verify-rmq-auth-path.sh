#!/usr/bin/env bash
set -euo pipefail

runtime="${CONTAINER_RUNTIME:-docker}"
admin_rmq_container="${ADMIN_RMQ_CONTAINER:-dune_server-admin-rmq-1}"
game_rmq_container="${GAME_RMQ_CONTAINER:-dune_server-game-rmq-1}"
rmq_auth_container="${RMQ_AUTH_CONTAINER:-dune_server-rmq-auth-shim-1}"
text_router_container="${TEXT_ROUTER_CONTAINER:-dune_server-text-router-1}"
timeout="${DUNE_RMQ_AUTH_PATH_TIMEOUT_SECONDS:-2}"

container_ip() {
  "$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$1"
}

is_running() {
  local state
  state="$("$runtime" inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)"
  [[ "$state" == "true" ]]
}

require_running() {
  local container="$1"
  if ! is_running "$container"; then
    printf 'container is not running: %s\n' "$container" >&2
    exit 1
  fi
}

check_tcp() {
  local source="$1"
  local target="$2"
  local port="$3"
  local name="$4"
  local target_ip

  require_running "$source"
  require_running "$target"
  target_ip="$(container_ip "$target")"
  if [[ -z "$target_ip" ]]; then
    printf 'missing target ip: %s\n' "$target" >&2
    exit 1
  fi
  "$runtime" exec "$source" sh -lc "nc -vz -w '$timeout' '$target_ip' '$port' >/dev/null 2>&1"
  printf 'ok: %s can reach %s (%s:%s)\n' "$source" "$name" "$target_ip" "$port"
}

check_tcp "$admin_rmq_container" "$rmq_auth_container" 8080 "rmq-auth-shim"
check_tcp "$game_rmq_container" "$rmq_auth_container" 8080 "rmq-auth-shim"
check_tcp "$game_rmq_container" "$text_router_container" 8080 "text-router"
