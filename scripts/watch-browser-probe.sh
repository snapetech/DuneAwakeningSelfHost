#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
seconds="${2:-120}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

range_for_tcpdump() {
  printf '%s' "$1" | tr ':' '-'
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
if ! command -v tcpdump >/dev/null 2>&1; then
  printf 'tcpdump is required\n' >&2
  exit 1
fi

game_rmq_public_port="$(read_env GAME_RMQ_PUBLIC_PORT)"
game_rmq_public_port="${game_rmq_public_port:-31982}"
game_udp_range="$(read_env GAME_UDP_PORT_RANGE)"
game_udp_range="${game_udp_range:-7777:7810}"
igw_udp_range="$(read_env IGW_UDP_PORT_RANGE)"
igw_udp_range="${igw_udp_range:-7888:7917}"
game_tcpdump_range="$(range_for_tcpdump "$game_udp_range")"
igw_tcpdump_range="$(range_for_tcpdump "$igw_udp_range")"
filter="(tcp port ${game_rmq_public_port}) or (udp portrange ${game_tcpdump_range}) or (udp portrange ${igw_tcpdump_range})"

printf 'watching browser probe traffic for %s seconds\n' "$seconds"
printf 'filter: %s\n\n' "$filter"

if command -v iptables >/dev/null 2>&1; then
  printf '== docker nat counters before ==\n'
  iptables -t nat -L DOCKER -n -v 2>/dev/null | rg "dpt:(${game_rmq_public_port}|777[7-9]|778[0-9]|779[0-9]|780[0-9]|7810|788[8-9]|789[0-9]|790[0-9]|791[0-7])" || true
  printf '\n'
fi

timeout "$seconds" tcpdump -ni any "$filter" || status=$?
status="${status:-0}"
if [[ "$status" != "0" && "$status" != "124" ]]; then
  exit "$status"
fi

if command -v iptables >/dev/null 2>&1; then
  printf '\n== docker nat counters after ==\n'
  iptables -t nat -L DOCKER -n -v 2>/dev/null | rg "dpt:(${game_rmq_public_port}|777[7-9]|778[0-9]|779[0-9]|780[0-9]|7810|788[8-9]|789[0-9]|790[0-9]|791[0-7])" || true
fi
