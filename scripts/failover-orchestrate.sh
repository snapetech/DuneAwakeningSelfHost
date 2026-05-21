#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/failover-orchestrate.sh [ENV_FILE] standby|primary [--apply]

Modes:
  standby  move this checkout's configured standby into the active role
  primary  move router/systemd roles back to the configured primary LAN IP

The standby mode can optionally promote Postgres when --apply is used.
The primary mode does not magically reverse a promoted Postgres timeline; rebuild
a new replica first, then run this from the host that owns the active database.
EOF
}

env_file="${1:-.env}"
target_role="${2:-}"
apply=false
if [[ "${3:-}" == "--apply" ]]; then
  apply=true
fi

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
if [[ "$target_role" != "standby" && "$target_role" != "primary" ]]; then
  usage
  exit 2
fi

standby_host="${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}"
standby_ip="${DUNE_FAILOVER_STANDBY_LAN_IP:-$(read_env DUNE_FAILOVER_STANDBY_LAN_IP)}"
primary_ip="${DUNE_FAILOVER_PRIMARY_LAN_IP:-$(read_env DUNE_FAILOVER_PRIMARY_LAN_IP)}"

if [[ -z "$standby_host" || -z "$standby_ip" || -z "$primary_ip" ]]; then
  printf 'POSTGRES_REMOTE_REPLICA_HOST, DUNE_FAILOVER_STANDBY_LAN_IP, and DUNE_FAILOVER_PRIMARY_LAN_IP are required\n' >&2
  exit 1
fi

run_step() {
  printf '\n== %s ==\n' "$*"
  "$@"
}

run_preflight() {
  local rc=0
  run_step make standby-status "ENV_FILE=$env_file" || rc=1
  run_step make cutover-network-status "ENV_FILE=$env_file" || true
  run_step make failover-role-services "ENV_FILE=$env_file" "ROLE=$target_role" || rc=1
  return "$rc"
}

printf 'mode=%s apply=%s\n' "$target_role" "$apply"

preflight_rc=0
run_preflight || preflight_rc=1

if [[ "$apply" != true ]]; then
  cat <<EOF

Dry run complete. Apply with:
  $0 $env_file $target_role --apply
EOF
  exit 0
fi

if [[ "$preflight_rc" -ne 0 && "${DUNE_FAILOVER_ALLOW_PREFLIGHT_WARNINGS:-}" != "yes" ]]; then
  cat >&2 <<'EOF'
Refusing apply because one or more preflight checks failed.
Fix the failed checks or set DUNE_FAILOVER_ALLOW_PREFLIGHT_WARNINGS=yes for an intentional emergency override.
EOF
  exit 1
fi

case "$target_role" in
  standby)
    run_step make sync-standby-files "ENV_FILE=$env_file"
    CONFIRM_SYNC_STANDBY_IMAGES=yes run_step make sync-standby-images "ENV_FILE=$env_file"
    run_step make postgres-failover-seal "ENV_FILE=$env_file"
    CONFIRM_PROMOTE_STANDBY=yes run_step make promote-standby "ENV_FILE=$env_file"
    CONFIRM_HOST_NETWORK_FAILOVER=yes run_step make host-network-failover "ENV_FILE=$env_file"
    CONFIRM_ROUTER_CUTOVER=yes run_step make router-cutover "ENV_FILE=$env_file" "TARGET=$standby_ip"
    CONFIRM_FAILOVER_ROLE_SERVICES=yes run_step make failover-role-services "ENV_FILE=$env_file" ROLE=standby
    ;;
  primary)
    CONFIRM_ROUTER_CUTOVER=yes run_step make router-cutover "ENV_FILE=$env_file" "TARGET=$primary_ip"
    CONFIRM_FAILOVER_ROLE_SERVICES=yes run_step make failover-role-services "ENV_FILE=$env_file" ROLE=primary
    ;;
esac

run_step make cutover-network-status "ENV_FILE=$env_file" || true
run_step make cutover-check "ENV_FILE=$env_file" || true
