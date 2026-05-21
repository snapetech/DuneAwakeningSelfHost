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

default_services="game-rmq gateway director text-router survival overmap arrakeen harko-village testing-hephaestus testing-carthag testing-waterfat deep-desert proces-verbal lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab art-of-kanly dungeon-hephaestus dungeon-oldcarthag faction-outpost-atre faction-outpost-hark heighliner-dungeon ecolab-green-089 ecolab-green-152 ecolab-green-024 ecolab-green-136 ecolab-green-195 overland-m-01 overland-s-04 overland-s-06 bandit-fortress overland-s-07 overland-s-08 dungeon-thepit"
services="${DUNE_RMQ_TLS_RECREATE_SERVICES:-$(read_env DUNE_RMQ_TLS_RECREATE_SERVICES)}"
services="${services:-$default_services}"
if [[ -z "$services" ]]; then
  printf 'DUNE_RMQ_TLS_RECREATE_SERVICES is required\n' >&2
  exit 1
fi

compose=(docker compose --env-file "$env_file" -f compose.yaml -f compose.allmaps.yaml)

printf 'services_to_recreate=%s\n' "$services"
printf '\n== current RabbitMQ TLS SAN ==\n'
./scripts/check-rabbitmq-cert-sans.sh "$env_file"

if [[ "${CONFIRM_RECREATE_RMQ_TLS_STACK:-}" != "yes" ]]; then
  cat <<EOF
Dry run only. To recreate services during maintenance:
  CONFIRM_RECREATE_RMQ_TLS_STACK=yes make rabbitmq-cert-recreate-stack ENV_FILE=${env_file}
EOF
  exit 0
fi

printf '\n== recreating RabbitMQ TLS-dependent services ==\n'
"${compose[@]}" up -d --force-recreate $services

printf '\n== post-recreate status ==\n'
COMPOSE_FILES=compose.yaml:compose.allmaps.yaml ./scripts/status.sh "$env_file"
COMPOSE_FILES=compose.yaml:compose.allmaps.yaml ./scripts/rmq-health.sh "$env_file"
