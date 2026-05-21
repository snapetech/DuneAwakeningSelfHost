#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
router_arg="${2:-}"
remote="${3:-${POSTGRES_REMOTE_REPLICA_HOST:-}}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

remote="${remote:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}"
router="${router_arg:-${DUNE_FAILOVER_ROUTER_SSH:-${DUNE_ROUTER_SSH:-$(read_env DUNE_FAILOVER_ROUTER_SSH)}}}"
public_ip="${DUNE_FAILOVER_PUBLIC_IP:-${DUNE_PUBLIC_IP:-${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}}}"
primary_ip="${DUNE_FAILOVER_PRIMARY_LAN_IP:-${DUNE_PRIMARY_LAN_IP:-$(read_env DUNE_FAILOVER_PRIMARY_LAN_IP)}}"
standby_ip="${DUNE_FAILOVER_STANDBY_LAN_IP:-${DUNE_STANDBY_LAN_IP:-$(read_env DUNE_FAILOVER_STANDBY_LAN_IP)}}"
game_rmq_port="${GAME_RMQ_PUBLIC_PORT:-$(read_env GAME_RMQ_PUBLIC_PORT)}"; game_rmq_port="${game_rmq_port:-31982}"
game_udp_range="${GAME_UDP_PORT_RANGE:-$(read_env GAME_UDP_PORT_RANGE)}"; game_udp_range="${game_udp_range:-7777:7806}"
igw_udp_range="${IGW_UDP_PORT_RANGE:-$(read_env IGW_UDP_PORT_RANGE)}"; igw_udp_range="${igw_udp_range:-7888:7917}"

if [[ -z "$router" || -z "$remote" || -z "$public_ip" || -z "$primary_ip" || -z "$standby_ip" ]]; then
  printf 'DUNE_FAILOVER_ROUTER_SSH, POSTGRES_REMOTE_REPLICA_HOST, EXTERNAL_ADDRESS/DUNE_PUBLIC_IP, DUNE_FAILOVER_PRIMARY_LAN_IP, and DUNE_FAILOVER_STANDBY_LAN_IP are required\n' >&2
  exit 1
fi

printf '== router Dune forwards ==\n'
vts_rulelist="$(ssh "$router" 'nvram get vts_rulelist' 2>/dev/null || true)"
if [[ -z "$vts_rulelist" ]]; then
  printf 'WARN unable to read router vts_rulelist from %s\n' "$router"
else
  printf '%s\n' "$vts_rulelist" | tr '<' '\n' | rg '^(duneA1|duneA2|DuneRMQ)>|$' || true
  if [[ "$vts_rulelist" == *"$standby_ip"* && "$vts_rulelist" != *"<duneA1>${game_udp_range}>${primary_ip}>>UDP>"* && "$vts_rulelist" != *"<duneA2>${igw_udp_range}>${primary_ip}>>UDP>"* && "$vts_rulelist" != *"<DuneRMQ>${game_rmq_port}>${primary_ip}>${game_rmq_port}>TCP>"* ]]; then
    printf 'OK router Dune forwards target standby %s\n' "$standby_ip"
  else
    printf 'WARN router Dune forwards are not fully cut over to standby %s\n' "$standby_ip"
  fi
fi

printf '\n== primary public address ownership ==\n'
if ip -brief addr | grep -q "$public_ip/32"; then
  printf 'primary owns %s/32\n' "$public_ip"
else
  printf 'primary does not own %s/32\n' "$public_ip"
fi

printf '\n== standby public address ownership ==\n'
if ssh "$remote" "ip -brief addr | grep -q '$public_ip/32'" 2>/dev/null; then
  printf 'OK standby %s owns %s/32\n' "$remote" "$public_ip"
else
  printf 'WARN standby %s does not own %s/32\n' "$remote" "$public_ip"
fi

printf '\n== standby Dune nft/iptables markers ==\n'
game_udp_start="${game_udp_range%%:*}"
game_udp_end="${game_udp_range##*:}"
igw_udp_start="${igw_udp_range%%:*}"
igw_udp_end="${igw_udp_range##*:}"
ssh "$remote" "if command -v nft >/dev/null 2>&1; then sudo -n nft list ruleset 2>/dev/null | grep -E '$public_ip|$game_rmq_port|$game_udp_start|$game_udp_end|$igw_udp_start|$igw_udp_end|172\\.31\\.240' || true; fi" || true
