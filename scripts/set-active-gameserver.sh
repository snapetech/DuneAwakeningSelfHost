#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/set-active-gameserver.sh ENV_FILE ACTIVE_HOST ACTIVE_LAN_IP STANDBY_HOST STANDBY_LAN_IP [--apply]

Updates the host-role values that must move together when the active Dune
gameserver primary changes. Dry-run is the default. Use --apply to edit ENV_FILE.
Run this on the active checkout, then sync the checkout to the standby.
EOF
}

env_file="${1:-}"
active_host="${2:-}"
active_ip="${3:-}"
standby_host="${4:-}"
standby_ip="${5:-}"
apply="${6:-}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ -z "$env_file" || -z "$active_host" || -z "$active_ip" || -z "$standby_host" || -z "$standby_ip" ]]; then
  usage
  exit 2
fi
if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
if [[ -n "$apply" && "$apply" != "--apply" ]]; then
  usage
  exit 2
fi
if [[ "$active_host" == "$standby_host" || "$active_ip" == "$standby_ip" ]]; then
  printf 'active and standby hosts/IPs must be different\n' >&2
  exit 1
fi

desired="$(
  cat <<EOF
DUNE_CURRENT_HOST=$active_host
DUNE_CURRENT_LAN_IP=$active_ip
DUNE_FAILOVER_PRIMARY_HOST=$active_host
DUNE_FAILOVER_PRIMARY_LAN_IP=$active_ip
DUNE_FAILOVER_STANDBY_HOST=$standby_host
DUNE_FAILOVER_STANDBY_LAN_IP=$standby_ip
POSTGRES_REPLICATION_BIND_ADDRESS=$active_ip
POSTGRES_REPLICATION_PRIMARY_HOST=$active_ip
POSTGRES_REMOTE_REPLICA_HOST=$standby_ip
POSTGRES_REPLICATION_ALLOWED_ADDRESS=$standby_ip
EOF
)"

current_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" | tail -1
}

printf 'active_host=%s active_ip=%s standby_host=%s standby_ip=%s\n' "$active_host" "$active_ip" "$standby_host" "$standby_ip"
printf '\n== planned env changes ==\n'
while IFS='=' read -r key value; do
  [[ -z "$key" ]] && continue
  old="$(current_value "$key")"
  if [[ "$old" == "$value" ]]; then
    printf 'OK %s=%s\n' "$key" "$value"
  else
    printf 'SET %s: %s -> %s\n' "$key" "${old:-<unset>}" "$value"
  fi
done <<< "$desired"

if [[ "$apply" != "--apply" ]]; then
  cat <<EOF

Dry run only. Apply with:
  $0 $env_file $active_host $active_ip $standby_host $standby_ip --apply
EOF
  exit 0
fi

tmp="$(mktemp)"
cp "$env_file" "$tmp"
while IFS='=' read -r key value; do
  [[ -z "$key" ]] && continue
  if grep -q "^${key}=" "$tmp"; then
    perl -0pi -e "s/^${key}=.*/${key}=${value}/m" "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
done <<< "$desired"
cat "$tmp" > "$env_file"
rm -f "$tmp"
printf '\nupdated %s\n' "$env_file"
