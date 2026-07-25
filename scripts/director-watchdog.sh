#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
interval="${DUNE_DIRECTOR_WATCHDOG_INTERVAL:-15}"
director="${DUNE_DIRECTOR_CONTAINER:-dune_server-director-1}"
rmq="${DUNE_DIRECTOR_RMQ_CONTAINER:-dune_server-game-rmq-1}"

purge_login_queue() {
  docker exec "$rmq" rabbitmqctl purge_queue loginRequests >/dev/null 2>&1 || true
}

while :; do
  state="$(docker inspect -f '{{.State.Status}}' "$director" 2>/dev/null || printf missing)"
  if [[ "$state" != running ]]; then
    printf '%s Director state=%s; purging loginRequests before recovery\n' "$(date -u +%FT%TZ)" "$state" >&2
    purge_login_queue
    docker start "$director" >/dev/null 2>&1 || docker restart "$director" >/dev/null 2>&1 || true
  fi
  sleep "$interval"
done
