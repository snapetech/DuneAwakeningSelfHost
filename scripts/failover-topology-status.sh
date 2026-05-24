#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"

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

primary_host="${DUNE_FAILOVER_PRIMARY_HOST:-$(read_env DUNE_FAILOVER_PRIMARY_HOST)}"
primary_ip="${DUNE_FAILOVER_PRIMARY_LAN_IP:-$(read_env DUNE_FAILOVER_PRIMARY_LAN_IP)}"
standby_host="${DUNE_FAILOVER_STANDBY_HOST:-$(read_env DUNE_FAILOVER_STANDBY_HOST)}"
standby_host="${standby_host:-${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}}"
standby_ip="${DUNE_FAILOVER_STANDBY_LAN_IP:-$(read_env DUNE_FAILOVER_STANDBY_LAN_IP)}"
current_host="${DUNE_CURRENT_HOST:-$(read_env DUNE_CURRENT_HOST)}"
current_ip="${DUNE_CURRENT_LAN_IP:-$(read_env DUNE_CURRENT_LAN_IP)}"
standby_ssh="${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}"
standby_ssh="${standby_ssh:-$standby_host}"
router="${DUNE_FAILOVER_ROUTER_SSH:-$(read_env DUNE_FAILOVER_ROUTER_SSH)}"
public_ip="${DUNE_FAILOVER_PUBLIC_IP:-${DUNE_PUBLIC_IP:-${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}}}"
db="${DUNE_DATABASE:-$(read_env DUNE_DATABASE)}"; db="${db:-dune_sb_1_4_0_0}"
remote_repo="${DUNE_STANDBY_REPO_ROOT:-$(read_env DUNE_STANDBY_REPO_ROOT)}"
remote_repo="${remote_repo:-$PWD}"

compose=(docker compose --env-file "$env_file" -f compose.yaml -f compose.replica.yaml)

printf '== configured topology ==\n'
printf 'current_host=%s current_ip=%s\n' "${current_host:-<unset>}" "${current_ip:-<unset>}"
printf 'primary_host=%s primary_ip=%s\n' "${primary_host:-<unset>}" "${primary_ip:-<unset>}"
printf 'standby_host=%s standby_ip=%s\n' "${standby_host:-<unset>}" "${standby_ip:-<unset>}"
printf 'public_ip=%s router=%s\n' "${public_ip:-<unset>}" "${router:-<unset>}"
if [[ -n "$current_host" && -n "$primary_host" && "$current_host" != "$primary_host" ]]; then
  printf 'WARN current_host does not match primary_host; run set-active-gameserver after a role change\n'
fi
if [[ -n "$current_ip" && -n "$primary_ip" && "$current_ip" != "$primary_ip" ]]; then
  printf 'WARN current_ip does not match primary_ip; run set-active-gameserver after a role change\n'
fi

printf '\n== local postgres role ==\n'
local_recovery="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc 'select pg_is_in_recovery();' 2>/dev/null || printf 'unavailable')"
case "$local_recovery" in
  f|false) printf 'local_postgres=writable-primary\n' ;;
  t|true) printf 'local_postgres=standby-in-recovery\n' ;;
  *) printf 'local_postgres=%s\n' "$local_recovery" ;;
esac

if [[ -n "$standby_ssh" ]]; then
  printf '\n== remote postgres role: %s ==\n' "$standby_ssh"
  ssh "$standby_ssh" "set -u
if docker ps --format '{{.Names}}' | grep -qx dune-postgres-replica; then
  printf 'dune-postgres-replica='
  docker exec dune-postgres-replica psql -U dune -d '$db' -Atc 'select case when pg_is_in_recovery() then '\''standby-in-recovery'\'' else '\''writable-primary'\'' end;' 2>/dev/null || echo unavailable
elif [ -d '$remote_repo' ] && cd '$remote_repo' && docker compose --env-file '$env_file' -f compose.yaml ps -q postgres >/dev/null 2>&1; then
  printf 'compose-postgres='
  docker compose --env-file '$env_file' -f compose.yaml exec -T postgres psql -U dune -d '$db' -Atc 'select case when pg_is_in_recovery() then '\''standby-in-recovery'\'' else '\''writable-primary'\'' end;' 2>/dev/null || echo unavailable
else
  echo 'remote_postgres=not-running-or-unknown'
fi" || true
fi

printf '\n== traffic ownership ==\n'
if [[ -n "$public_ip" ]]; then
  if ip -brief addr | grep -q "$public_ip/32"; then
    printf 'local_public_ip=owned\n'
  else
    printf 'local_public_ip=not-owned\n'
  fi
  if [[ -n "$standby_ssh" ]]; then
    if ssh "$standby_ssh" "ip -brief addr | grep -q '$public_ip/32'" 2>/dev/null; then
      printf 'remote_public_ip=owned\n'
    else
      printf 'remote_public_ip=not-owned\n'
    fi
  fi
fi

if [[ -n "$router" ]]; then
  vts="$(ssh "$router" 'nvram get vts_rulelist' 2>/dev/null || true)"
  if [[ -n "$vts" ]]; then
    printf 'router_dune_targets='
    printf '%s\n' "$vts" | tr '<' '\n' | awk -F'>' '/^(duneA1|duneA2|DuneRMQ)>/ {print $3}' | sort -u | paste -sd, -
  else
    printf 'router_dune_targets=unavailable\n'
  fi
fi

printf '\n== next-command hints ==\n'
if [[ "$local_recovery" == "f" || "$local_recovery" == "false" ]]; then
  printf 'local host appears writable. For primary->standby handoff: make handoff-ready ENV_FILE=%s ROLE=standby\n' "$env_file"
  printf 'For planned promotion: make failover-orchestrate ENV_FILE=%s ROLE=standby\n' "$env_file"
else
  printf 'local host is not writable or unavailable. Run this from the active database host for authoritative actions.\n'
fi
printf 'After any promotion, prove/rebuild the old primary before reverse cutback.\n'
