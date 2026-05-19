#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
since="${RMQ_HEALTH_SINCE:-2m}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

redact() {
  sed -E \
    -e 's#(sg|bgd|tr)\.sh-[A-Za-z0-9_.+/-]+#\1.sh-[redacted]#g' \
    -e 's/sh-[0-9a-fA-F]{16}-[A-Za-z0-9]+/sh-[redacted]/g'
}

summarize_connections() {
  local service="$1"
  "${compose[@]}" exec -T "$service" rabbitmqctl list_connections user peer_host state 2>/dev/null \
    | awk '
      NR > 1 && $1 ~ /^(sg|bgd|tr)\./ {
        users[$1] = 1
        hosts[$2] = 1
        conns++
      }
      END {
        printf "%s_service_connections=%d %s_unique_users=%d %s_unique_hosts=%d\n", svc, conns + 0, svc, length(users), svc, length(hosts)
      }
    ' svc="${service%-rmq}"
}

echo "== rabbitmq service-user coverage =="
summarize_connections admin-rmq
summarize_connections game-rmq

echo
echo "== recent rabbitmq auth errors since ${since} =="
recent_errors="$("${compose[@]}" logs --since="$since" admin-rmq game-rmq rmq-auth-shim 2>&1 \
  | redact \
  | rg -n 'failed authenticating|access_refused|failed_connect|timeout|Error on AMQP|Host is unreachable' || true)"

if [[ -z "$recent_errors" ]]; then
  echo "OK: no recent RabbitMQ auth/connectivity errors found."
else
  printf '%s\n' "$recent_errors"
  exit 2
fi
