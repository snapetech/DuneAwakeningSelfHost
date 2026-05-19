#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")

wait_for_healthy() {
  local service="$1"
  local container_id
  local status

  container_id="$("${compose[@]}" ps -q "$service")"
  if [[ -z "$container_id" ]]; then
    printf 'service is not running: %s\n' "$service" >&2
    return 1
  fi

  for _ in {1..60}; do
    status="$("$container_runtime" inspect \
      --format '{{ if .State.Health }}{{ .State.Health.Status }}{{ else }}running{{ end }}' \
      "$container_id")"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      return 0
    fi
    sleep 2
  done

  printf 'service did not become healthy: %s\n' "$service" >&2
  return 1
}

printf 'starting stateful dependencies\n'
"${compose[@]}" up -d postgres admin-rmq game-rmq

wait_for_healthy postgres
wait_for_healthy admin-rmq
wait_for_healthy game-rmq

printf 'starting service layer\n'
"${compose[@]}" up -d rmq-auth-shim text-router gateway director

printf 'recreating survival\n'
"${compose[@]}" up -d --force-recreate survival

printf 'waiting for game-server registration\n'
sleep 90

exec ./scripts/status.sh "$env_file"
