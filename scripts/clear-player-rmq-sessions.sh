#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-${ENV_FILE:-.env}}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  [[ -n "$compose_file" ]] && compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

rmq_service="${DUNE_GAME_RMQ_SERVICE:-game-rmq}"
reason="${DUNE_PLAYER_RMQ_CLEAR_REASON:-maintenance player-session cleanup}"
hex_re='^[[:xdigit:]]{16}$'
queue_re='^[[:xdigit:]]{16}_(queue|rpcQueue)$'

if ! "${compose[@]}" ps -q "$rmq_service" >/dev/null 2>&1; then
  printf 'game RabbitMQ service is not available; skipping player RMQ cleanup\n' >&2
  exit 0
fi

connections="$("${compose[@]}" exec -T "$rmq_service" rabbitmqctl -q list_connections name user 2>/dev/null || true)"
closed=0
while IFS=$'\t' read -r name user; do
  [[ "$name" == "name" || -z "$name" ]] && continue
  if [[ "$user" =~ $hex_re ]]; then
    if "${compose[@]}" exec -T "$rmq_service" rabbitmqctl close_connection "$name" "$reason" >/dev/null 2>&1; then
      ((closed += 1))
    fi
  fi
done <<< "$connections"

if (( closed > 0 )); then
  sleep 2
fi

queues="$("${compose[@]}" exec -T "$rmq_service" rabbitmqctl -q list_queues name 2>/dev/null || true)"
deleted=0
while IFS=$'\t' read -r queue_name _; do
  [[ "$queue_name" == "name" || -z "$queue_name" ]] && continue
  if [[ "$queue_name" =~ $queue_re ]]; then
    if "${compose[@]}" exec -T "$rmq_service" rabbitmqctl delete_queue "$queue_name" >/dev/null 2>&1; then
      ((deleted += 1))
    fi
  fi
done <<< "$queues"

printf 'player RMQ cleanup complete: closed_connections=%s deleted_queues=%s\n' "$closed" "$deleted"
