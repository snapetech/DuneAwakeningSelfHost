#!/usr/bin/env bash
set -euo pipefail

runtime="${CONTAINER_RUNTIME:-docker}"
postgres_container="${POSTGRES_CONTAINER:-dune_server-postgres-1}"
gateway_container="${GATEWAY_CONTAINER:-dune_server-gateway-1}"
admin_rmq_container="${ADMIN_RMQ_CONTAINER:-dune_server-admin-rmq-1}"
game_rmq_container="${GAME_RMQ_CONTAINER:-dune_server-game-rmq-1}"
rmq_auth_container="${RMQ_AUTH_CONTAINER:-dune_server-rmq-auth-shim-1}"
text_router_container="${TEXT_ROUTER_CONTAINER:-dune_server-text-router-1}"
director_container="${DIRECTOR_CONTAINER:-dune_server-director-1}"
admin_panel_container="${ADMIN_PANEL_CONTAINER:-dune_server-admin-panel-1}"
admin_panel_ingress_container="${ADMIN_PANEL_INGRESS_CONTAINER:-dune_server-admin-panel-ingress-1}"
admin_chat_container="${ADMIN_CHAT_CONTAINER:-dune_server-admin-chat-commands-1}"
postgres_ip="${POSTGRES_IP:-}"
gateway_ip="${GATEWAY_IP:-172.31.240.40}"
gateway_static_mac="${GATEWAY_MAC_ADDRESS:-02:42:ac:1f:f0:28}"
bridge_ip="${DUNE_BRIDGE_IP:-172.31.240.1}"
bridge_mac="${DUNE_BRIDGE_MAC_ADDRESS:-}"

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

container_pid() {
  "$runtime" inspect -f '{{.State.Pid}}' "$1"
}

container_mac() {
  "$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.MacAddress}}{{end}}' "$1"
}

container_ip() {
  "$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$1"
}

is_running() {
  local pid
  pid="$(container_pid "$1" 2>/dev/null || true)"
  [[ -n "$pid" && "$pid" != "0" ]]
}

if [[ -z "$bridge_mac" ]]; then
  bridge_dev="$(ip -o -4 addr show | awk -v ip="$bridge_ip" '$4 ~ "^" ip "/ " || $4 ~ "^" ip "/" {print $2; exit}')"
  if [[ -n "${bridge_dev:-}" ]]; then
    bridge_mac="$(cat "/sys/class/net/$bridge_dev/address" 2>/dev/null || true)"
  fi
fi

if is_running "$postgres_container" && ! is_running "$gateway_container"; then
  postgres_pid="$(container_pid "$postgres_container")"
  run_root nsenter -t "$postgres_pid" -n ip neigh replace "$gateway_ip" lladdr "$gateway_static_mac" dev eth0 nud permanent
  printf 'preseeded postgres gateway neighbor entry: gateway=%s/%s\n' "$gateway_ip" "$gateway_static_mac"
fi

if is_running "$postgres_container" && is_running "$gateway_container"; then
  postgres_pid="$(container_pid "$postgres_container")"
  gateway_pid="$(container_pid "$gateway_container")"
  postgres_ip="${postgres_ip:-$(container_ip "$postgres_container")}"
  gateway_ip="$(container_ip "$gateway_container")"
  postgres_mac="$(container_mac "$postgres_container")"
  gateway_mac="$(container_mac "$gateway_container")"

  run_root nsenter -t "$gateway_pid" -n ip neigh replace "$postgres_ip" lladdr "$postgres_mac" dev eth0 nud permanent
  if [[ -n "$bridge_mac" ]]; then
    run_root nsenter -t "$gateway_pid" -n ip neigh replace "$bridge_ip" lladdr "$bridge_mac" dev eth0 nud permanent
  fi
  run_root nsenter -t "$postgres_pid" -n ip neigh replace "$gateway_ip" lladdr "$gateway_mac" dev eth0 nud permanent

  printf 'seeded gateway/postgres neighbor entries: gateway=%s/%s postgres=%s/%s\n' \
    "$gateway_ip" "$gateway_mac" "$postgres_ip" "$postgres_mac"
else
  printf 'skipped gateway/postgres neighbor entries; one or both containers are not running\n' >&2
fi

seed_bridge() {
  local source="$1"
  local source_pid

  source_pid="$(container_pid "$source" 2>/dev/null || true)"
  if [[ -n "$source_pid" && "$source_pid" != "0" && -n "$bridge_mac" ]]; then
    run_root nsenter -t "$source_pid" -n ip neigh replace "$bridge_ip" lladdr "$bridge_mac" dev eth0 nud permanent
  fi
}

seed_pair() {
  local source="$1"
  local target="$2"
  local source_pid
  local target_ip
  local target_mac

  source_pid="$(container_pid "$source" 2>/dev/null || true)"
  target_ip="$("$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$target" 2>/dev/null || true)"
  target_mac="$(container_mac "$target" 2>/dev/null || true)"

  if [[ -n "$source_pid" && "$source_pid" != "0" && -n "$target_ip" && -n "$target_mac" ]]; then
    run_root nsenter -t "$source_pid" -n ip neigh replace "$target_ip" lladdr "$target_mac" dev eth0 nud permanent
  fi
}

seed_host_neighbor() {
  local target="$1"
  local target_ip
  local target_mac
  local target_dev

  target_ip="$("$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$target" 2>/dev/null || true)"
  target_mac="$(container_mac "$target" 2>/dev/null || true)"
  if [[ -z "$target_ip" || -z "$target_mac" ]]; then
    return
  fi

  target_dev="$(ip route get "$target_ip" 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "dev") {print $(i+1); exit}}')"
  if [[ -n "$target_dev" ]]; then
    run_root ip neigh replace "$target_ip" lladdr "$target_mac" dev "$target_dev" nud permanent
  fi
}

seed_host_alias() {
  local source="$1"
  local target="$2"
  local alias="$3"
  local target_ip

  target_ip="$("$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$target" 2>/dev/null || true)"
  if is_running "$source" && [[ -n "$target_ip" ]]; then
    "$runtime" exec "$source" sh -lc "sed -i '/[[:space:]]${alias}\$/d' /etc/hosts; printf '\\n%s %s\\n' '$target_ip' '$alias' >> /etc/hosts" >/dev/null 2>&1 || true
  fi
}

seed_bridge "$gateway_container"
seed_bridge "$director_container"
seed_bridge "$admin_rmq_container"
seed_bridge "$game_rmq_container"
seed_bridge "$rmq_auth_container"
seed_bridge "$text_router_container"
seed_bridge "$admin_panel_container"
seed_bridge "$admin_panel_ingress_container"
seed_bridge "$admin_chat_container"

seed_pair "$game_rmq_container" "$rmq_auth_container"
seed_pair "$rmq_auth_container" "$game_rmq_container"
seed_pair "$admin_rmq_container" "$rmq_auth_container"
seed_pair "$rmq_auth_container" "$admin_rmq_container"
seed_pair "$rmq_auth_container" "$text_router_container"
seed_pair "$text_router_container" "$rmq_auth_container"
seed_pair "$text_router_container" "$game_rmq_container"
seed_pair "$game_rmq_container" "$text_router_container"
seed_pair "$director_container" "$game_rmq_container"
seed_pair "$game_rmq_container" "$director_container"
seed_pair "$admin_panel_ingress_container" "$admin_panel_container"
seed_pair "$admin_panel_container" "$admin_panel_ingress_container"
seed_pair "$admin_panel_container" "$postgres_container"
seed_pair "$postgres_container" "$admin_panel_container"
seed_pair "$admin_chat_container" "$postgres_container"
seed_pair "$postgres_container" "$admin_chat_container"
seed_pair "$admin_chat_container" "$game_rmq_container"
seed_pair "$game_rmq_container" "$admin_chat_container"
seed_host_neighbor "$admin_panel_ingress_container"
seed_host_neighbor "$admin_panel_container"
seed_host_neighbor "$admin_chat_container"
seed_host_neighbor "$admin_rmq_container"
seed_host_neighbor "$gateway_container"
seed_host_alias "$admin_panel_ingress_container" "$admin_panel_container" "admin-panel"
seed_host_alias "$admin_panel_container" "$postgres_container" "postgres"
seed_host_alias "$admin_chat_container" "$postgres_container" "postgres"
seed_host_alias "$admin_chat_container" "$game_rmq_container" "game-rmq"

project="${COMPOSE_PROJECT_NAME:-dune_server}"
mapfile -t compose_containers < <("$runtime" ps \
  --filter "label=com.docker.compose.project=$project" \
  --format '{{.Names}}' 2>/dev/null || true)
critical_containers=(
  "$postgres_container"
  "$admin_rmq_container"
  "$game_rmq_container"
  "$rmq_auth_container"
  "$text_router_container"
)
for source in "${compose_containers[@]}"; do
  for target in "${critical_containers[@]}"; do
    if [[ "$source" != "$target" ]]; then
      seed_pair "$source" "$target"
    fi
  done
done
printf 'seeded available Dune bridge neighbor entries\n'
