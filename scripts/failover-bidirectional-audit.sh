#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
status_rc=0

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

ok() { printf 'OK %s\n' "$1"; }
warn() { printf 'WARN %s\n' "$1"; status_rc=1; }

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

primary_host="${DUNE_FAILOVER_PRIMARY_HOST:-$(read_env DUNE_FAILOVER_PRIMARY_HOST)}"
primary_ip="${DUNE_FAILOVER_PRIMARY_LAN_IP:-$(read_env DUNE_FAILOVER_PRIMARY_LAN_IP)}"
standby_host="${DUNE_FAILOVER_STANDBY_HOST:-$(read_env DUNE_FAILOVER_STANDBY_HOST)}"
standby_host="${standby_host:-${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}}"
standby_ip="${DUNE_FAILOVER_STANDBY_LAN_IP:-$(read_env DUNE_FAILOVER_STANDBY_LAN_IP)}"
remote_repo="${DUNE_STANDBY_REPO_ROOT:-$(read_env DUNE_STANDBY_REPO_ROOT)}"
remote_repo="${remote_repo:-$PWD}"
router="${DUNE_FAILOVER_ROUTER_SSH:-$(read_env DUNE_FAILOVER_ROUTER_SSH)}"
public_ip="${DUNE_FAILOVER_PUBLIC_IP:-${DUNE_PUBLIC_IP:-${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}}}"
remote_root="${POSTGRES_REMOTE_REPLICA_ROOT:-$(read_env POSTGRES_REMOTE_REPLICA_ROOT)}"

printf '== bidirectional failover audit ==\n'
for item in \
  "DUNE_FAILOVER_PRIMARY_HOST:$primary_host" \
  "DUNE_FAILOVER_PRIMARY_LAN_IP:$primary_ip" \
  "DUNE_FAILOVER_STANDBY_HOST:$standby_host" \
  "DUNE_FAILOVER_STANDBY_LAN_IP:$standby_ip" \
  "DUNE_FAILOVER_ROUTER_SSH:$router" \
  "DUNE_FAILOVER_PUBLIC_IP/EXTERNAL_ADDRESS:$public_ip" \
  "POSTGRES_REMOTE_REPLICA_ROOT:$remote_root" \
  "DUNE_STANDBY_REPO_ROOT:$remote_repo"; do
  key="${item%%:*}"
  value="${item#*:}"
  if [[ -n "$value" ]]; then ok "$key=$value"; else warn "$key is unset"; fi
done

printf '\n== required failover scripts ==\n'
required_scripts=(
  scripts/failover-topology-status.sh
  scripts/handoff-ready.sh
  scripts/handoff-experiment.sh
  scripts/failover-orchestrate.sh
  scripts/router-cutover-asuswrt.sh
  scripts/host-network-failover.sh
  scripts/promote-standby.sh
  scripts/postgres-failover-seal.sh
  scripts/postgres-cutback-proof.sh
  scripts/rebuild-postgres-standby.sh
  scripts/recreate-rabbitmq-tls-stack.sh
)
for script in "${required_scripts[@]}"; do
  [[ -x "$script" ]] && ok "local $script executable" || warn "local $script missing or not executable"
  if [[ -n "$standby_host" ]]; then
    ssh "$standby_host" "test -x '$remote_repo/$script'" 2>/dev/null \
      && ok "$standby_host:$script executable" \
      || warn "$standby_host:$script missing or not executable"
  fi
done

printf '\n== systemd unit symmetry ==\n'
make failover-role-services "ENV_FILE=$env_file" ROLE=standby || status_rc=1
make failover-role-services "ENV_FILE=$env_file" ROLE=primary || status_rc=1

printf '\n== router dry-run to each side ==\n'
if [[ -n "$standby_ip" ]]; then
  if make router-cutover "ENV_FILE=$env_file" "TARGET=$standby_ip" >/tmp/dune-router-standby-audit.$$ 2>&1; then
    ok "router can render standby target"
  else
    cat /tmp/dune-router-standby-audit.$$
    warn "router standby target render failed"
  fi
  rm -f /tmp/dune-router-standby-audit.$$
fi
if [[ -n "$primary_ip" ]]; then
  if make router-cutover "ENV_FILE=$env_file" "TARGET=$primary_ip" >/tmp/dune-router-primary-audit.$$ 2>&1; then
    ok "router can render primary target"
  else
    cat /tmp/dune-router-primary-audit.$$
    warn "router primary target render failed"
  fi
  rm -f /tmp/dune-router-primary-audit.$$
fi

printf '\n== topology ==\n'
make failover-topology-status "ENV_FILE=$env_file" || status_rc=1

printf '\n== verdict ==\n'
if [[ "$status_rc" -eq 0 ]]; then
  printf 'BIDIRECTIONAL_AUDIT=OK\n'
else
  printf 'BIDIRECTIONAL_AUDIT=WARN\n'
fi
exit "$status_rc"
