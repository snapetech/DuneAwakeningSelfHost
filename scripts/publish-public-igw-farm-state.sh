#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
target_map="${2:-}"
compose_cmd="${COMPOSE:-docker compose}"
loop_seconds="${DUNE_PUBLIC_IGW_LOOP_SECONDS:-0}"
trigger_action="${DUNE_PUBLIC_IGW_TRIGGER_ACTION:-}"

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

host="$(hostname)"
if [[ "${DUNE_ALLOW_NON_PROD_FARM_STATE_WRITE:-}" != "true" && "$host" != "kspls0" ]]; then
  printf 'refusing farm_state write on host %s; run on kspls0 or set DUNE_ALLOW_NON_PROD_FARM_STATE_WRITE=true for lab use\n' "$host" >&2
  exit 1
fi
if [[ "${DUNE_PUBLIC_IGW_ACK_INTERNAL_S2S_RISK:-}" != "yes" ]]; then
  cat >&2 <<'EOF'
refusing public IGW farm_state rewrite without DUNE_PUBLIC_IGW_ACK_INTERNAL_S2S_RISK=yes

This experiment can break internal server-to-server routing. On production it
caused map partition loss after current farm_state.igw_addr rows were rewritten
from container bridge IPs to the public address. Prefer keeping game_addr public
and igw_addr private unless a new packet capture proves otherwise.
EOF
  exit 1
fi

external_address="${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}"
if [[ -z "$external_address" ]]; then
  printf 'EXTERNAL_ADDRESS is required\n' >&2
  exit 1
fi

dune_database="${DUNE_GAME_DB_NAME:-$(read_env DUNE_GAME_DB_NAME)}"
dune_database="${dune_database:-${DUNE_DB_NAME:-$(read_env DUNE_DB_NAME)}}"
dune_database="${DUNE_PUBLIC_IGW_DATABASE:-$dune_database}"
dune_database="${dune_database:-dune_sb_1_4_0_0}"
backup_dir="${DUNE_FARM_STATE_BACKUP_DIR:-backups/browser-ping}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="${backup_dir}/farm-state-pre-public-igw-${timestamp}.tsv"
where_sql="igw_addr::text ~ '^(10|172\\.(1[6-9]|2[0-9]|3[0-1])|192\\.168)\\.'"
current_sql="server_id in (select server_id from dune.world_partition)"

mkdir -p "$backup_dir"
if [[ "${DUNE_PUBLIC_IGW_ALL_FARM_ROWS:-}" != "true" ]]; then
  where_sql="${where_sql} and ${current_sql}"
fi
if [[ -n "$target_map" ]]; then
  where_sql="${where_sql} and map = :'target_map'"
fi

publish_once() {
  local do_backup="${1:-false}" postgres_container tmp_backup
  postgres_container="$($compose_cmd --env-file "$env_file" ps -q postgres)"
  if [[ -z "$postgres_container" ]]; then
    printf 'postgres service is not available through compose ps\n' >&2
    exit 1
  fi

  tmp_backup="/tmp/farm-state-pre-public-igw-${timestamp}.tsv"
  if [[ "$do_backup" == "true" ]]; then
    if [[ -n "$target_map" ]]; then
      $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -v ON_ERROR_STOP=1 -v target_map="$target_map" <<SQL
\\copy (select now() as captured_at, * from dune.farm_state where ${where_sql} order by map, server_id) to '${tmp_backup}' with csv delimiter E'\\t' header
SQL
    else
      $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -v ON_ERROR_STOP=1 <<SQL
\\copy (select now() as captured_at, * from dune.farm_state where ${where_sql} order by map, server_id) to '${tmp_backup}' with csv delimiter E'\\t' header
SQL
    fi
    docker cp "${postgres_container}:${tmp_backup}" "$backup_file"
    printf 'farm_state backup written: %s\n' "$backup_file"
  fi

  if [[ -n "$target_map" ]]; then
    $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -v ON_ERROR_STOP=1 -v target_map="$target_map" <<SQL
begin;
with updated as (
update dune.farm_state
   set igw_addr = inet '${external_address}/0'
 where ${where_sql}
 returning server_id
)
select count(*) as updated_public_igw_rows from updated;
commit;
SQL
  else
    $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -v ON_ERROR_STOP=1 <<SQL
begin;
with updated as (
update dune.farm_state
   set igw_addr = inet '${external_address}/0'
 where ${where_sql}
 returning server_id
)
select count(*) as updated_public_igw_rows from updated;
commit;
SQL
  fi
}

install_trigger() {
  $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -v ON_ERROR_STOP=1 <<SQL
create or replace function dune.force_public_igw_addr()
returns trigger
language plpgsql
as \$\$
begin
  if NEW.igw_addr::text ~ '^(10|172\\.(1[6-9]|2[0-9]|3[0-1])|192\\.168)\\.' then
    NEW.igw_addr := inet '${external_address}/0';
  end if;
  return NEW;
end;
\$\$;

drop trigger if exists force_public_igw_addr on dune.farm_state;
create trigger force_public_igw_addr
before insert or update of igw_addr on dune.farm_state
for each row
execute function dune.force_public_igw_addr();
SQL
  printf 'installed farm_state public IGW trigger for %s\n' "$external_address"
}

uninstall_trigger() {
  $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -v ON_ERROR_STOP=1 <<'SQL'
drop trigger if exists force_public_igw_addr on dune.farm_state;
drop function if exists dune.force_public_igw_addr();
SQL
  printf 'removed farm_state public IGW trigger\n'
}

case "$trigger_action" in
  install)
    install_trigger
    ;;
  uninstall)
    uninstall_trigger
    exit 0
    ;;
  "")
    ;;
  *)
    printf 'invalid DUNE_PUBLIC_IGW_TRIGGER_ACTION: %s\n' "$trigger_action" >&2
    exit 2
    ;;
esac

publish_once true
if [[ "$loop_seconds" =~ ^[0-9]+$ && "$loop_seconds" -gt 0 ]]; then
  printf 'looping public IGW farm_state publication every %s second(s)\n' "$loop_seconds"
  while true; do
    sleep "$loop_seconds"
    publish_once false
  done
fi
