#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
remote="${2:-}"
seal_file="${3:-}"

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

remote="${remote:-${POSTGRES_REMOTE_REPLICA_HOST:-$(read_env POSTGRES_REMOTE_REPLICA_HOST)}}"
db="${DUNE_DATABASE:-$(read_env DUNE_DATABASE)}"; db="${db:-dune_sb_1_4_0_0}"
seal_dir="${DUNE_POSTGRES_FAILOVER_SEAL_DIR:-backups/failover-seals}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
seal_file="${seal_file:-${seal_dir}/postgres-failover-seal-${stamp}.env}"

if [[ -z "$remote" ]]; then
  printf 'remote standby host is required\n' >&2
  exit 1
fi

compose=(docker compose --env-file "$env_file" -f compose.yaml -f compose.replica.yaml)
mkdir -p "$(dirname "$seal_file")"

system_id="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc 'select system_identifier from pg_control_system();')"
checkpoint="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "select timeline_id || '|' || checkpoint_lsn from pg_control_checkpoint();")"
timeline="${checkpoint%%|*}"
checkpoint_lsn="${checkpoint##*|}"
current_lsn="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc 'select pg_current_wal_lsn();')"
remote_replay_lsn="$(ssh "$remote" "docker exec dune-postgres-replica psql -U dune -d '$db' -Atc 'select pg_last_wal_replay_lsn();'" 2>/dev/null || true)"
remote_in_recovery="$(ssh "$remote" "docker exec dune-postgres-replica psql -U dune -d '$db' -Atc 'select pg_is_in_recovery();'" 2>/dev/null || true)"

if [[ "$remote_in_recovery" != "t" && "$remote_in_recovery" != "true" ]]; then
  printf 'remote %s is not a standby in recovery: %s\n' "$remote" "${remote_in_recovery:-unknown}" >&2
  exit 1
fi
if [[ -z "$remote_replay_lsn" ]]; then
  printf 'remote replay LSN unavailable\n' >&2
  exit 1
fi

replay_diff="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "select pg_wal_lsn_diff('$remote_replay_lsn'::pg_lsn, '$current_lsn'::pg_lsn);")"

cat >"$seal_file" <<EOF
created_at_utc=$stamp
primary_host=$(hostname -f 2>/dev/null || hostname)
standby_host=$remote
database=$db
system_identifier=$system_id
primary_timeline=$timeline
primary_checkpoint_lsn=$checkpoint_lsn
primary_current_wal_lsn=$current_lsn
standby_replay_lsn=$remote_replay_lsn
standby_replay_minus_primary_lsn_bytes=$replay_diff
EOF

printf 'wrote Postgres failover seal: %s\n' "$seal_file"
cat "$seal_file"

if [[ "$replay_diff" =~ ^- ]]; then
  printf 'WARN standby replay LSN is behind the primary seal LSN; wait and seal again before planned promotion\n' >&2
  exit 1
fi

printf 'OK standby has replayed through the sealed primary LSN\n'
