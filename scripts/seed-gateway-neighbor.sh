#!/usr/bin/env bash
set -euo pipefail

runtime="${CONTAINER_RUNTIME:-docker}"
postgres_container="${POSTGRES_CONTAINER:-dune_server-postgres-1}"
gateway_container="${GATEWAY_CONTAINER:-dune_server-gateway-1}"
game_rmq_container="${GAME_RMQ_CONTAINER:-dune_server-game-rmq-1}"
rmq_auth_container="${RMQ_AUTH_CONTAINER:-dune_server-rmq-auth-shim-1}"
text_router_container="${TEXT_ROUTER_CONTAINER:-dune_server-text-router-1}"
director_container="${DIRECTOR_CONTAINER:-dune_server-director-1}"
postgres_ip="${POSTGRES_IP:-172.31.240.4}"
gateway_ip="${GATEWAY_IP:-172.31.240.40}"
bridge_ip="${DUNE_BRIDGE_IP:-172.31.240.1}"
bridge_mac="${DUNE_BRIDGE_MAC_ADDRESS:-36:e6:a2:8f:49:66}"

container_pid() {
  "$runtime" inspect -f '{{.State.Pid}}' "$1"
}

container_mac() {
  "$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.MacAddress}}{{end}}' "$1"
}

postgres_pid="$(container_pid "$postgres_container")"
gateway_pid="$(container_pid "$gateway_container")"
postgres_mac="$(container_mac "$postgres_container")"
gateway_mac="$(container_mac "$gateway_container")"

if [[ -z "$postgres_pid" || "$postgres_pid" == "0" || -z "$gateway_pid" || "$gateway_pid" == "0" ]]; then
  printf 'postgres and gateway must both be running before seeding neighbors\n' >&2
  exit 1
fi

sudo nsenter -t "$gateway_pid" -n ip neigh replace "$postgres_ip" lladdr "$postgres_mac" dev eth0 nud permanent
sudo nsenter -t "$gateway_pid" -n ip neigh replace "$bridge_ip" lladdr "$bridge_mac" dev eth0 nud permanent
sudo nsenter -t "$postgres_pid" -n ip neigh replace "$gateway_ip" lladdr "$gateway_mac" dev eth0 nud permanent

seed_bridge() {
  local source="$1"
  local source_pid

  source_pid="$(container_pid "$source")"
  if [[ -n "$source_pid" && "$source_pid" != "0" ]]; then
    sudo nsenter -t "$source_pid" -n ip neigh replace "$bridge_ip" lladdr "$bridge_mac" dev eth0 nud permanent
  fi
}

seed_pair() {
  local source="$1"
  local target="$2"
  local source_pid
  local target_ip
  local target_mac

  source_pid="$(container_pid "$source")"
  target_ip="$("$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$target")"
  target_mac="$(container_mac "$target")"

  if [[ -n "$source_pid" && "$source_pid" != "0" && -n "$target_ip" && -n "$target_mac" ]]; then
    sudo nsenter -t "$source_pid" -n ip neigh replace "$target_ip" lladdr "$target_mac" dev eth0 nud permanent
  fi
}

seed_bridge "$gateway_container"
seed_bridge "$director_container"
seed_bridge "$game_rmq_container"
seed_bridge "$rmq_auth_container"
seed_bridge "$text_router_container"

seed_pair "$game_rmq_container" "$rmq_auth_container"
seed_pair "$rmq_auth_container" "$game_rmq_container"
seed_pair "$rmq_auth_container" "$text_router_container"
seed_pair "$text_router_container" "$rmq_auth_container"
seed_pair "$director_container" "$game_rmq_container"
seed_pair "$game_rmq_container" "$director_container"

printf 'seeded gateway/postgres neighbor entries: gateway=%s/%s postgres=%s/%s\n' \
  "$gateway_ip" "$gateway_mac" "$postgres_ip" "$postgres_mac"
