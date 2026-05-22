#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/recreate-rabbitmq-tls-stack.sh [ENV_FILE]

Recreate RabbitMQ and Dune services that must reload client-facing RabbitMQ TLS
material. Dry-run by default. Apply with CONFIRM_RECREATE_RMQ_TLS_STACK=yes.
EOF
}

env_file="${1:-.env}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

default_services="game-rmq gateway director text-router survival overmap arrakeen harko-village testing-hephaestus testing-carthag testing-waterfat deep-desert deep-desert-pvp proces-verbal lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab art-of-kanly dungeon-hephaestus dungeon-oldcarthag faction-outpost-atre faction-outpost-hark heighliner-dungeon ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-136 ecolab-green-195 overland-m-01 overland-s-04 overland-s-06 bandit-fortress overland-s-07 overland-s-08 dungeon-thepit"
services="${DUNE_RMQ_TLS_RECREATE_SERVICES:-$(read_env DUNE_RMQ_TLS_RECREATE_SERVICES)}"
services="${services:-$default_services}"
if [[ -z "$services" ]]; then
  printf 'DUNE_RMQ_TLS_RECREATE_SERVICES is required\n' >&2
  exit 1
fi

compose=(docker compose --env-file "$env_file" -f compose.yaml -f compose.allmaps.yaml)

split_services() {
  rmq_requested=false
  dependent_services=()
  local service
  for service in $services; do
    if [[ "$service" == "game-rmq" ]]; then
      rmq_requested=true
    else
      dependent_services+=("$service")
    fi
  done
}

wait_for_game_rmq() {
  local timeout="${DUNE_RMQ_TLS_RECREATE_WAIT_SECONDS:-180}"
  local deadline=$((SECONDS + timeout))
  local container_id=""

  printf 'waiting for game-rmq broker ping, timeout_seconds=%s\n' "$timeout"
  while (( SECONDS < deadline )); do
    container_id="$("${compose[@]}" ps -q game-rmq 2>/dev/null || true)"
    if [[ -n "$container_id" ]] && docker exec "$container_id" rabbitmq-diagnostics -q ping >/dev/null 2>&1; then
      printf 'OK game-rmq broker ping succeeded\n'
      return 0
    fi
    sleep 2
  done

  printf 'ERROR game-rmq did not answer broker ping within %s seconds\n' "$timeout" >&2
  return 1
}

split_services

printf 'services_to_recreate=%s\n' "$services"
if [[ "$rmq_requested" == true ]]; then
  printf 'recreate_phase_1=game-rmq\n'
fi
if [[ "${#dependent_services[@]}" -gt 0 ]]; then
  printf 'recreate_phase_2=%s\n' "${dependent_services[*]}"
fi
printf '\n== current RabbitMQ TLS SAN ==\n'
tls_rc=0
./scripts/check-rabbitmq-cert-sans.sh "$env_file" || tls_rc=1

if [[ "${CONFIRM_RECREATE_RMQ_TLS_STACK:-}" != "yes" ]]; then
  cat <<EOF
Dry run only. To recreate services during maintenance:
  CONFIRM_RECREATE_RMQ_TLS_STACK=yes make rabbitmq-cert-recreate-stack ENV_FILE=${env_file}
EOF
  exit 0
fi

if [[ "$tls_rc" -ne 0 && "${DUNE_ALLOW_INVALID_RMQ_TLS_RECREATE:-}" != "yes" ]]; then
  printf 'refusing recreate because RabbitMQ TLS SAN check failed\n' >&2
  printf 'install staged TLS first or set DUNE_ALLOW_INVALID_RMQ_TLS_RECREATE=yes for an intentional emergency\n' >&2
  exit 1
fi

printf '\n== recreating RabbitMQ TLS-dependent services ==\n'
if [[ "$rmq_requested" == true ]]; then
  printf '== phase 1: game-rmq ==\n'
  "${compose[@]}" up -d --force-recreate game-rmq
  wait_for_game_rmq
fi

if [[ "${#dependent_services[@]}" -gt 0 ]]; then
  if [[ "$rmq_requested" == false ]]; then
    wait_for_game_rmq
  fi
  printf '\n== phase 2: RabbitMQ clients ==\n'
  "${compose[@]}" up -d --force-recreate "${dependent_services[@]}"
fi

printf '\n== post-recreate status ==\n'
COMPOSE_FILES=compose.yaml:compose.allmaps.yaml ./scripts/status.sh "$env_file"
COMPOSE_FILES=compose.yaml:compose.allmaps.yaml ./scripts/rmq-health.sh "$env_file"
