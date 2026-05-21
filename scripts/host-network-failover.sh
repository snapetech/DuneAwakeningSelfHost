#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
remote="${2:-${POSTGRES_REMOTE_REPLICA_HOST:-}}"

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
remote_repo="${DUNE_STANDBY_REPO_ROOT:-$PWD}"
public_ip="${DUNE_FAILOVER_PUBLIC_IP:-${DUNE_PUBLIC_IP:-${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}}}"
game_rmq_port="${GAME_RMQ_PUBLIC_PORT:-$(read_env GAME_RMQ_PUBLIC_PORT)}"; game_rmq_port="${game_rmq_port:-31982}"
game_udp_range="${GAME_UDP_PORT_RANGE:-$(read_env GAME_UDP_PORT_RANGE)}"; game_udp_range="${game_udp_range:-7777:7806}"
igw_udp_range="${IGW_UDP_PORT_RANGE:-$(read_env IGW_UDP_PORT_RANGE)}"; igw_udp_range="${igw_udp_range:-7888:7917}"
game_udp_start="${game_udp_range%%:*}"
game_udp_end="${game_udp_range##*:}"
igw_udp_start="${igw_udp_range%%:*}"
igw_udp_end="${igw_udp_range##*:}"
primary_ip="${DUNE_FAILOVER_PRIMARY_LAN_IP:-${DUNE_PRIMARY_LAN_IP:-$(read_env DUNE_FAILOVER_PRIMARY_LAN_IP)}}"
standby_ip="${DUNE_FAILOVER_STANDBY_LAN_IP:-${DUNE_STANDBY_LAN_IP:-$(read_env DUNE_FAILOVER_STANDBY_LAN_IP)}}"

if [[ -z "$remote" || -z "$public_ip" || -z "$primary_ip" || -z "$standby_ip" ]]; then
  printf 'POSTGRES_REMOTE_REPLICA_HOST, EXTERNAL_ADDRESS/DUNE_PUBLIC_IP, DUNE_FAILOVER_PRIMARY_LAN_IP, and DUNE_FAILOVER_STANDBY_LAN_IP are required\n' >&2
  exit 1
fi

printf '== primary host network snapshot ==\n'
ip -brief addr | sed -n '1,80p'
ip route | sed -n '1,80p'
if command -v nft >/dev/null 2>&1; then
  sudo -n nft list ruleset 2>/dev/null | rg -n "$public_ip|$game_rmq_port|$game_udp_start|$game_udp_end|$igw_udp_start|$igw_udp_end|172\\.31\\.240" || true
fi

printf '\n== standby host network snapshot: %s ==\n' "$remote"
ssh "$remote" "ip -brief addr | sed -n '1,80p'
ip route | sed -n '1,80p'
if command -v nft >/dev/null 2>&1; then sudo -n nft list ruleset 2>/dev/null | grep -E '$public_ip|$game_rmq_port|$game_udp_start|$game_udp_end|$igw_udp_start|$igw_udp_end|172\\.31\\.240' || true; fi"

printf '\n== verdict ==\n'
if ssh "$remote" "ip -brief addr | grep -q '$public_ip/32'"; then
  printf 'OK standby already owns %s/32\n' "$public_ip"
else
  printf 'WARN standby does not own %s/32 yet\n' "$public_ip"
fi

if [[ "${CONFIRM_HOST_NETWORK_FAILOVER:-}" != "yes" ]]; then
  cat <<EOF
Dry run only. To apply host-side failover networking on ${remote}, run:
  CONFIRM_HOST_NETWORK_FAILOVER=yes make host-network-failover ENV_FILE=${env_file} REMOTE=${remote}

This runs scripts/setup-lan-reflection.sh on ${remote}; it adds ${public_ip}/32,
rp_filter relaxations, Dune bridge MASQUERADE, and local OUTPUT redirects for
${game_rmq_port}/tcp, ${game_udp_range}/udp, and ${igw_udp_range}/udp.
EOF
  exit 0
fi

printf '\n== applying standby host network failover on %s ==\n' "$remote"
ssh "$remote" "cd '$remote_repo' && DUNE_PUBLIC_IP='$public_ip' DUNE_PRIMARY_LAN_IP='$primary_ip' DUNE_STANDBY_LAN_IP='$standby_ip' ./scripts/setup-lan-reflection.sh '$env_file'"
ssh "$remote" "ip -brief addr | grep '$public_ip/32' && ip route get '$public_ip' || true"
