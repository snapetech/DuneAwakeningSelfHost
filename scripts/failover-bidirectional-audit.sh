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
current_host="${DUNE_CURRENT_HOST:-$(read_env DUNE_CURRENT_HOST)}"
current_ip="${DUNE_CURRENT_LAN_IP:-$(read_env DUNE_CURRENT_LAN_IP)}"
postgres_bind_ip="${POSTGRES_REPLICATION_BIND_ADDRESS:-$(read_env POSTGRES_REPLICATION_BIND_ADDRESS)}"
postgres_primary_ip="${POSTGRES_REPLICATION_PRIMARY_HOST:-$(read_env POSTGRES_REPLICATION_PRIMARY_HOST)}"
postgres_remote_host="${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}"
postgres_allowed_ip="${POSTGRES_REPLICATION_ALLOWED_ADDRESS:-$(read_env POSTGRES_REPLICATION_ALLOWED_ADDRESS)}"
standby_ssh="${postgres_remote_host:-$standby_host}"
remote_repo="${DUNE_STANDBY_REPO_ROOT:-$(read_env DUNE_STANDBY_REPO_ROOT)}"
remote_repo="${remote_repo:-$PWD}"
router="${DUNE_FAILOVER_ROUTER_SSH:-$(read_env DUNE_FAILOVER_ROUTER_SSH)}"
public_ip="${DUNE_FAILOVER_PUBLIC_IP:-${DUNE_PUBLIC_IP:-${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}}}"
remote_root="${POSTGRES_REMOTE_REPLICA_ROOT:-$(read_env POSTGRES_REMOTE_REPLICA_ROOT)}"
role_services="${DUNE_STANDBY_ROLE_SERVICES:-$(read_env DUNE_STANDBY_ROLE_SERVICES)}"
role_timers="${DUNE_STANDBY_ROLE_TIMERS:-$(read_env DUNE_STANDBY_ROLE_TIMERS)}"
website_services="${DUNE_STANDBY_WEBSITE_SERVICES:-$(read_env DUNE_STANDBY_WEBSITE_SERVICES)}"
website_timers="${DUNE_STANDBY_WEBSITE_TIMERS:-$(read_env DUNE_STANDBY_WEBSITE_TIMERS)}"
keep_website_running="${DUNE_STANDBY_KEEP_WEBSITE_RUNNING:-$(read_env DUNE_STANDBY_KEEP_WEBSITE_RUNNING)}"
website_mode="${DUNE_STANDBY_WEBSITE_MODE:-$(read_env DUNE_STANDBY_WEBSITE_MODE)}"
website_mode="${website_mode:-follow-role}"
if [[ "$keep_website_running" == "true" ]]; then
  website_mode="independent"
fi

unit_enabled_state() {
  local host="$1" unit="$2"
  if [[ "$host" == "local" ]]; then
    systemctl is-enabled "$unit" 2>/dev/null || true
  else
    ssh "$host" "systemctl is-enabled '$unit' 2>/dev/null || true"
  fi
}

unit_active_state() {
  local host="$1" unit="$2"
  if [[ "$host" == "local" ]]; then
    systemctl is-active "$unit" 2>/dev/null || true
  else
    ssh "$host" "systemctl is-active '$unit' 2>/dev/null || true"
  fi
}

audit_primary_enabled_standby_disabled() {
  local label="$1" enforce_role_ownership="$2" unit local_enabled remote_enabled local_active remote_active
  shift 2
  for unit in "$@"; do
    [[ -z "$unit" ]] && continue
    local_enabled="$(unit_enabled_state local "$unit")"
    remote_enabled="$(unit_enabled_state "$standby_ssh" "$unit")"
    local_active="$(unit_active_state local "$unit")"
    remote_active="$(unit_active_state "$standby_ssh" "$unit")"
    printf '%s %s local_enabled=%s local_active=%s standby_enabled=%s standby_active=%s\n' "$label" "$unit" "${local_enabled:-unknown}" "${local_active:-unknown}" "${remote_enabled:-unknown}" "${remote_active:-unknown}"
    if [[ "$enforce_role_ownership" == "true" ]]; then
      case "$local_enabled" in
        enabled|static|generated|indirect) ;;
        *) warn "$label $unit is not enabled/static on current primary" ;;
      esac
      case "$remote_enabled" in
        disabled|masked|static|not-found|'') ;;
        *) warn "$label $unit is enabled on standby but should be cold for role-following cutover" ;;
      esac
      case "$remote_active" in
        inactive|failed|unknown|'') ;;
        *) warn "$label $unit is active on standby but should be cold for role-following cutover" ;;
      esac
    fi
  done
}

printf '== bidirectional failover audit ==\n'
for item in \
  "DUNE_FAILOVER_PRIMARY_HOST:$primary_host" \
  "DUNE_FAILOVER_PRIMARY_LAN_IP:$primary_ip" \
  "DUNE_FAILOVER_STANDBY_HOST:$standby_host" \
  "DUNE_FAILOVER_STANDBY_LAN_IP:$standby_ip" \
  "DUNE_CURRENT_HOST:$current_host" \
  "DUNE_CURRENT_LAN_IP:$current_ip" \
  "POSTGRES_REPLICATION_BIND_ADDRESS:$postgres_bind_ip" \
  "POSTGRES_REPLICATION_PRIMARY_HOST:$postgres_primary_ip" \
  "POSTGRES_REMOTE_REPLICA_HOST:$postgres_remote_host" \
  "POSTGRES_REPLICATION_ALLOWED_ADDRESS:$postgres_allowed_ip" \
  "DUNE_FAILOVER_ROUTER_SSH:$router" \
  "DUNE_FAILOVER_PUBLIC_IP/EXTERNAL_ADDRESS:$public_ip" \
  "POSTGRES_REMOTE_REPLICA_ROOT:$remote_root" \
  "DUNE_STANDBY_REPO_ROOT:$remote_repo"; do
  key="${item%%:*}"
  value="${item#*:}"
  if [[ -n "$value" ]]; then ok "$key=$value"; else warn "$key is unset"; fi
done

printf '\n== active role env consistency ==\n'
[[ "$current_host" == "$primary_host" ]] && ok "DUNE_CURRENT_HOST matches DUNE_FAILOVER_PRIMARY_HOST" || warn "DUNE_CURRENT_HOST ($current_host) does not match DUNE_FAILOVER_PRIMARY_HOST ($primary_host)"
[[ "$current_ip" == "$primary_ip" ]] && ok "DUNE_CURRENT_LAN_IP matches DUNE_FAILOVER_PRIMARY_LAN_IP" || warn "DUNE_CURRENT_LAN_IP ($current_ip) does not match DUNE_FAILOVER_PRIMARY_LAN_IP ($primary_ip)"
[[ "$postgres_bind_ip" == "$primary_ip" ]] && ok "POSTGRES_REPLICATION_BIND_ADDRESS follows active primary IP" || warn "POSTGRES_REPLICATION_BIND_ADDRESS ($postgres_bind_ip) does not match primary IP ($primary_ip)"
[[ "$postgres_primary_ip" == "$primary_ip" ]] && ok "POSTGRES_REPLICATION_PRIMARY_HOST follows active primary IP" || warn "POSTGRES_REPLICATION_PRIMARY_HOST ($postgres_primary_ip) does not match primary IP ($primary_ip)"
[[ "$postgres_remote_host" == "$standby_ip" || "$postgres_remote_host" == "$standby_host" ]] && ok "POSTGRES_REMOTE_REPLICA_HOST targets standby" || warn "POSTGRES_REMOTE_REPLICA_HOST ($postgres_remote_host) does not match standby host/IP ($standby_host/$standby_ip)"
[[ "$postgres_allowed_ip" == "$standby_ip" ]] && ok "POSTGRES_REPLICATION_ALLOWED_ADDRESS follows standby IP" || warn "POSTGRES_REPLICATION_ALLOWED_ADDRESS ($postgres_allowed_ip) does not match standby IP ($standby_ip)"

printf '\n== standby must not run game writers ==\n'
if [[ -n "$standby_ssh" ]]; then
  standby_dune_writers="$(ssh "$standby_ssh" "docker ps --format '{{.Names}}' | grep -E '^(dune_server-|dune_handoff_lab-)' | grep -v '^dune-postgres-replica$' || true" 2>/dev/null || true)"
  if [[ -z "$standby_dune_writers" ]]; then
    ok "standby has no Dune game/control-plane containers running except replica"
  else
    printf '%s\n' "$standby_dune_writers"
    warn "standby is running Dune writer/control-plane containers"
  fi
fi

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
  if [[ -n "$standby_ssh" ]]; then
    ssh "$standby_ssh" "test -x '$remote_repo/$script'" 2>/dev/null \
      && ok "$standby_ssh:$script executable" \
      || warn "$standby_ssh:$script missing or not executable"
  fi
done

printf '\n== systemd unit symmetry ==\n'
make failover-role-services "ENV_FILE=$env_file" ROLE=standby || status_rc=1
make failover-role-services "ENV_FILE=$env_file" ROLE=primary || status_rc=1

printf '\n== active role ownership ==\n'
audit_primary_enabled_standby_disabled "role-service" true $role_services
audit_primary_enabled_standby_disabled "role-timer" true $role_timers
if [[ "$keep_website_running" == "true" ]]; then
  ok "website standby running is explicitly allowed by DUNE_STANDBY_KEEP_WEBSITE_RUNNING=true"
fi
if [[ "$website_mode" == "independent" ]]; then
  ok "website units are independent of game role by DUNE_STANDBY_WEBSITE_MODE=independent"
  audit_primary_enabled_standby_disabled "website-service" false $website_services
  audit_primary_enabled_standby_disabled "website-timer" false $website_timers
else
  audit_primary_enabled_standby_disabled "website-service" true $website_services
  audit_primary_enabled_standby_disabled "website-timer" true $website_timers
fi

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
