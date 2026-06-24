#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
mode="${2:-apply}"

if [[ ! -f "$env_file" ]]; then
  echo "missing env file: $env_file" >&2
  exit 1
fi

read_env() {
  local key="$1"
  local default="${2:-}"
  local line value
  line="$(grep -E "^[[:space:]]*${key}=" "$env_file" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  value="${line#*=}"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

read_first_env() {
  local value
  while (($#)); do
    value="$(read_env "$1" "")"
    if [[ -n "$value" ]]; then
      printf '%s' "$value"
      return
    fi
    shift
  done
}

project="$(read_env COMPOSE_PROJECT_NAME "${COMPOSE_PROJECT_NAME:-dune_server}")"
db_service="$(read_env DUNE_POSTGRES_SERVICE "${DUNE_POSTGRES_SERVICE:-postgres}")"
db_user="$(read_env DUNE_POSTGRES_USER "${DUNE_POSTGRES_USER:-dune}")"
db_name="$(read_first_env DUNE_POSTGRES_DB DUNE_GAME_DB_NAME DUNE_DATABASE DUNE_DB_NAME)"
partition_ids="$(read_env DUNE_INSTANT_LOGOFF_PARTITIONS "${DUNE_INSTANT_LOGOFF_PARTITIONS:-1,8}")"
container="${project}-${db_service}-1"

if [[ -z "$db_name" ]]; then
  echo "set DUNE_GAME_DB_NAME, DUNE_DATABASE, DUNE_DB_NAME, or DUNE_POSTGRES_DB; refusing to guess database" >&2
  exit 1
fi
if ! [[ "$partition_ids" =~ ^[0-9]+([,[:space:]]+[0-9]+)*$ ]]; then
  echo "DUNE_INSTANT_LOGOFF_PARTITIONS must be a comma/space separated integer list" >&2
  exit 1
fi

partition_array="$(printf '%s' "$partition_ids" | tr ',[:space:]' ' ' | awk '{ for (i=1; i<=NF; i++) printf "%s%s", (i == 1 ? "" : ","), $i }')"

apply_sql="
create or replace function dune.clamp_instant_logoff_timers()
returns trigger
language plpgsql
as \$\$
begin
  if new.previous_server_partition_id = any (ARRAY[${partition_array}]::int[]) then
    if new.last_avatar_activity is not null then
      new.reconnect_grace_period_end = least(coalesce(new.reconnect_grace_period_end, new.last_avatar_activity), new.last_avatar_activity);
      new.logoff_persistence_end_time = least(coalesce(new.logoff_persistence_end_time, new.last_avatar_activity), new.last_avatar_activity);
    elsif new.last_login_time is not null then
      new.reconnect_grace_period_end = least(coalesce(new.reconnect_grace_period_end, new.last_login_time), new.last_login_time);
      new.logoff_persistence_end_time = least(coalesce(new.logoff_persistence_end_time, new.last_login_time), new.last_login_time);
    else
      new.reconnect_grace_period_end = null;
      new.logoff_persistence_end_time = null;
    end if;
  end if;
  return new;
end;
\$\$;

drop trigger if exists clamp_instant_logoff_timers_encrypted_player_state on dune.encrypted_player_state;
create trigger clamp_instant_logoff_timers_encrypted_player_state
before insert or update of previous_server_partition_id,last_avatar_activity,last_login_time,reconnect_grace_period_end,logoff_persistence_end_time
on dune.encrypted_player_state
for each row execute function dune.clamp_instant_logoff_timers();

update dune.encrypted_player_state
set reconnect_grace_period_end = coalesce(last_avatar_activity, last_login_time),
    logoff_persistence_end_time = coalesce(last_avatar_activity, last_login_time)
where previous_server_partition_id = any (ARRAY[${partition_array}]::int[])
  and coalesce(last_avatar_activity, last_login_time) is not null
  and (
    (reconnect_grace_period_end is not null and reconnect_grace_period_end > coalesce(last_avatar_activity, last_login_time))
    or (logoff_persistence_end_time is not null and logoff_persistence_end_time > coalesce(last_avatar_activity, last_login_time))
  );

select
  previous_server_partition_id,
  count(*) filter (where reconnect_grace_period_end > coalesce(last_avatar_activity,last_login_time)) as future_reconnect,
  count(*) filter (where logoff_persistence_end_time > coalesce(last_avatar_activity,last_login_time)) as future_logoff,
  count(*) as rows
from dune.player_state
where previous_server_partition_id = any (ARRAY[${partition_array}]::int[])
group by previous_server_partition_id
order by previous_server_partition_id;
"

dry_sql="
select
  previous_server_partition_id,
  count(*) filter (where reconnect_grace_period_end > coalesce(last_avatar_activity,last_login_time)) as future_reconnect,
  count(*) filter (where logoff_persistence_end_time > coalesce(last_avatar_activity,last_login_time)) as future_logoff,
  count(*) as rows
from dune.player_state
where previous_server_partition_id = any (ARRAY[${partition_array}]::int[])
group by previous_server_partition_id
order by previous_server_partition_id;
"

case "$mode" in
  apply)
    docker exec "$container" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -c "$apply_sql"
    ;;
  dry-run|preview)
    docker exec "$container" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -c "$dry_sql"
    ;;
  rollback|remove|uninstall)
    docker exec "$container" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -c "drop trigger if exists clamp_instant_logoff_timers_encrypted_player_state on dune.encrypted_player_state; drop function if exists dune.clamp_instant_logoff_timers();"
    ;;
  *)
    echo "usage: $0 [env-file] [apply|dry-run|rollback]" >&2
    exit 2
    ;;
esac
