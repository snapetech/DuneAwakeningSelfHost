#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
compose_files="${COMPOSE_FILES:-compose.yaml:compose.replica.yaml}"
db="${DUNE_DATABASE:-dune_sb_1_4_0_0}"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

replication_user="$(awk -F= '/^POSTGRES_REPLICATION_USER=/{print $2}' "$env_file" | tail -1)"
replication_user="${replication_user:-dune_replicator}"
replication_password="$(awk -F= '/^POSTGRES_REPLICATION_PASSWORD=/{print $2}' "$env_file" | tail -1)"
replication_slot="$(awk -F= '/^POSTGRES_REPLICATION_SLOT=/{print $2}' "$env_file" | tail -1)"
replication_slot="${replication_slot:-dune_standby}"

if [[ -z "$replication_password" ]]; then
  printf 'POSTGRES_REPLICATION_PASSWORD is not set in %s\n' "$env_file" >&2
  printf 'Generate one, add it to .env, then rerun this script.\n' >&2
  exit 1
fi

IFS=':' read -ra files <<< "$compose_files"
compose=(docker compose --env-file "$env_file")
for file in "${files[@]}"; do
  compose+=(-f "$file")
done

"${compose[@]}" up -d postgres

printf 'creating replication role and slot on primary\n'
"${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 \
  -v repl_user="$replication_user" \
  -v repl_password="$replication_password" \
  -v repl_slot="$replication_slot" <<'SQL'
select format('create role %I with replication login password %L', :'repl_user', :'repl_password')
where not exists (select 1 from pg_roles where rolname = :'repl_user') \gexec

select format('alter role %I with replication login password %L', :'repl_user', :'repl_password') \gexec

select pg_create_physical_replication_slot(:'repl_slot')
where not exists (select 1 from pg_replication_slots where slot_name = :'repl_slot');
SQL

printf 'ensuring primary pg_hba replication rule\n'
"${compose[@]}" exec -T postgres sh -lc "
set -eu
hba=/var/lib/postgresql/data/pg_hba.conf
rule='host replication ${replication_user} all scram-sha-256'
grep -qxF \"\$rule\" \"\$hba\" || printf '\n%s\n' \"\$rule\" >> \"\$hba\"
psql -U dune -d \"$db\" -c 'select pg_reload_conf();'
"

printf 'starting postgres-replica\n'
"${compose[@]}" up -d postgres-replica

printf 'replication status on primary:\n'
"${compose[@]}" exec -T postgres psql -U dune -d "$db" -c "
select slot_name, active, restart_lsn from pg_replication_slots where slot_name = '$replication_slot';
select application_name, state, sync_state, write_lag, flush_lag, replay_lag from pg_stat_replication;
"
