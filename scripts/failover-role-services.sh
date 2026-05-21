#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
target_role="${2:-}"
remote="${3:-}"

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
if [[ "$target_role" != "primary" && "$target_role" != "standby" ]]; then
  printf 'usage: %s ENV_FILE primary|standby [REMOTE]\n' "$0" >&2
  exit 2
fi

remote="${remote:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}"
role_services="${DUNE_STANDBY_ROLE_SERVICES:-$(read_env DUNE_STANDBY_ROLE_SERVICES)}"
role_timers="${DUNE_STANDBY_ROLE_TIMERS:-$(read_env DUNE_STANDBY_ROLE_TIMERS)}"
website_services="${DUNE_STANDBY_WEBSITE_SERVICES:-$(read_env DUNE_STANDBY_WEBSITE_SERVICES)}"
website_timers="${DUNE_STANDBY_WEBSITE_TIMERS:-$(read_env DUNE_STANDBY_WEBSITE_TIMERS)}"
website_mode="${DUNE_STANDBY_WEBSITE_MODE:-$(read_env DUNE_STANDBY_WEBSITE_MODE)}"
website_mode="${website_mode:-follow-role}"
if [[ "${DUNE_STANDBY_KEEP_WEBSITE_RUNNING:-$(read_env DUNE_STANDBY_KEEP_WEBSITE_RUNNING)}" == "true" ]]; then
  website_mode="independent"
fi

run_systemctl() {
  local host="$1"; shift
  if [[ "$host" == "local" ]]; then
    sudo systemctl "$@"
  else
    ssh "$host" "sudo systemctl $*"
  fi
}

check_units() {
  local host="$1" missing=0 unit
  shift
  for unit in "$@"; do
    [[ -z "$unit" ]] && continue
    if [[ "$host" == "local" ]]; then
      systemctl list-unit-files "$unit" --no-legend 2>/dev/null | grep -q "^$unit" || {
        printf 'WARN %s missing on local host\n' "$unit" >&2
        missing=1
      }
    else
      ssh "$host" "systemctl list-unit-files '$unit' --no-legend 2>/dev/null | grep -q '^$unit'" || {
        printf 'WARN %s missing on %s\n' "$unit" "$host" >&2
        missing=1
      }
    fi
  done
  return "$missing"
}

apply_role() {
  local host="$1" role="$2"
  if [[ "$role" == "primary" ]]; then
    [[ -n "$role_services" ]] && run_systemctl "$host" enable --now $role_services
    [[ -n "$role_timers" ]] && run_systemctl "$host" enable --now $role_timers
    if [[ "$website_mode" == "follow-role" ]]; then
      [[ -n "$website_services" ]] && run_systemctl "$host" enable --now $website_services
      [[ -n "$website_timers" ]] && run_systemctl "$host" enable --now $website_timers
    fi
  else
    [[ -n "$role_services" ]] && run_systemctl "$host" disable --now $role_services
    [[ -n "$role_timers" ]] && run_systemctl "$host" disable --now $role_timers
    if [[ "$website_mode" == "follow-role" ]]; then
      [[ -n "$website_services" ]] && run_systemctl "$host" disable --now $website_services
      [[ -n "$website_timers" ]] && run_systemctl "$host" disable --now $website_timers
    fi
  fi
}

if [[ "$target_role" == "primary" ]]; then
  if [[ "${CONFIRM_FAILOVER_ROLE_SERVICES:-}" != "yes" ]]; then
    check_units local $role_services $role_timers $website_services $website_timers || true
    [[ -n "$remote" ]] && check_units "$remote" $role_services $role_timers $website_services $website_timers || true
    printf 'Dry run: would make local host primary and remote %s standby. website_mode=%s. Set CONFIRM_FAILOVER_ROLE_SERVICES=yes to apply.\n' "${remote:-<unset>}" "$website_mode"
    exit 0
  fi
  apply_role local primary
  [[ -n "$remote" ]] && apply_role "$remote" standby
else
  if [[ -z "$remote" ]]; then
    printf 'remote standby host is required to move primary role away from local host\n' >&2
    exit 1
  fi
  if [[ "${CONFIRM_FAILOVER_ROLE_SERVICES:-}" != "yes" ]]; then
    check_units local $role_services $role_timers $website_services $website_timers || true
    check_units "$remote" $role_services $role_timers $website_services $website_timers || true
    printf 'Dry run: would make local host standby and remote %s primary. website_mode=%s. Set CONFIRM_FAILOVER_ROLE_SERVICES=yes to apply.\n' "$remote" "$website_mode"
    exit 0
  fi
  apply_role local standby
  apply_role "$remote" primary
fi
