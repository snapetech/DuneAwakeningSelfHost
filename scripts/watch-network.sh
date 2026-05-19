#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/watch-network.sh [env-file]

Prints current socket-state counts for the services most relevant to database,
RabbitMQ, and routing churn.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

services=(gateway text-router director survival postgres admin-rmq game-rmq)

for service in "${services[@]}"; do
  cid="$("${compose[@]}" ps -q "$service" 2>/dev/null || true)"
  [[ -n "$cid" ]] || continue

  printf '== %s ==\n' "$service"
  "$container_runtime" exec "$cid" sh -lc '
    ss -tunap 2>/dev/null || netstat -tunap 2>/dev/null || true
  ' 2>/dev/null \
    | awk '
      $1 ~ /^(tcp|udp)/ {
        state=$6
        if ($1 == "udp") state="UDP"
        counts[state]++
        if ($0 ~ /:5432[[:space:]]/) db[state]++
        if ($0 ~ /:5672[[:space:]]/) rmq[state]++
      }
      END {
        printf "states:"
        for (s in counts) printf " %s=%s", s, counts[s]
        printf "\npostgres:"
        for (s in db) printf " %s=%s", s, db[s]
        printf "\nrabbitmq:"
        for (s in rmq) printf " %s=%s", s, rmq[s]
        printf "\n"
      }
    '
  printf '\n'
done
