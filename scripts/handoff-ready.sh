#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
role="${2:-standby}"
status_rc=0

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
if [[ "$role" != "standby" && "$role" != "primary" ]]; then
  printf 'usage: %s ENV_FILE standby|primary\n' "$0" >&2
  exit 2
fi

section() {
  printf '\n== %s ==\n' "$1"
}

check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'OK %s\n' "$label"
  else
    printf 'BLOCKER %s\n' "$label"
    status_rc=1
  fi
}

section "RabbitMQ TLS"
check "public RabbitMQ cert covers advertised host" ./scripts/check-rabbitmq-cert-sans.sh "$env_file"

section "Standby Replication And Mirror"
check "standby replication, mirror, snapshots, and images are clean" env DUNE_STANDBY_SKIP_RMQ_TLS_CHECK=true make standby-status "ENV_FILE=$env_file"

section "Current Public Endpoint"
check "current stack health and public RMQ probe are clean" make cutover-check "ENV_FILE=$env_file"

section "Role Services"
check "role-service dry-run has no missing-unit failure" make failover-role-services "ENV_FILE=$env_file" "ROLE=$role"

section "Router/Host Network Inventory"
make cutover-network-status "ENV_FILE=$env_file" || true

section "Verdict"
if [[ "$status_rc" -eq 0 ]]; then
  printf 'READY for quick-hiccup handoff experiment dry-run/apply gate.\n'
else
  printf 'NOT READY. Fix BLOCKER lines before live handoff experiment.\n'
fi
exit "$status_rc"
