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

limit="$(read_env DUNE_SUBFIEF_LIMIT "${DUNE_SUBFIEF_LIMIT:-}")"
base="$(read_env DUNE_SUBFIEF_BASE_LIMIT "${DUNE_SUBFIEF_BASE_LIMIT:-3}")"
explicit_bonus="$(read_env DUNE_SUBFIEF_LIMIT_BONUS "${DUNE_SUBFIEF_LIMIT_BONUS:-}")"
project="$(read_env COMPOSE_PROJECT_NAME "${COMPOSE_PROJECT_NAME:-dune_server}")"
db_service="$(read_env DUNE_POSTGRES_SERVICE "${DUNE_POSTGRES_SERVICE:-postgres}")"
db_name="$(read_first_env DUNE_POSTGRES_DB DUNE_GAME_DB_NAME DUNE_DATABASE DUNE_DB_NAME)"
db_user="$(read_env DUNE_POSTGRES_USER "${DUNE_POSTGRES_USER:-dune}")"

if [[ -z "$db_name" ]]; then
  echo "set DUNE_GAME_DB_NAME, DUNE_DATABASE, DUNE_DB_NAME, or DUNE_POSTGRES_DB; refusing to guess database" >&2
  exit 1
fi
if [[ -z "$limit" && -z "$explicit_bonus" ]]; then
  echo "set DUNE_SUBFIEF_LIMIT or DUNE_SUBFIEF_LIMIT_BONUS; nothing to apply" >&2
  exit 1
fi
if ! [[ "$base" =~ ^[0-9]+$ ]]; then
  echo "DUNE_SUBFIEF_BASE_LIMIT must be an integer" >&2
  exit 1
fi
if [[ -n "$explicit_bonus" ]]; then
  if ! [[ "$explicit_bonus" =~ ^[0-9]+$ ]]; then
    echo "DUNE_SUBFIEF_LIMIT_BONUS must be an integer" >&2
    exit 1
  fi
  bonus="$explicit_bonus"
  limit=$((base + bonus))
else
  if ! [[ "$limit" =~ ^[0-9]+$ ]]; then
    echo "DUNE_SUBFIEF_LIMIT must be an integer" >&2
    exit 1
  fi
  if (( limit < base )); then
  echo "DUNE_SUBFIEF_LIMIT (${limit}) must be >= DUNE_SUBFIEF_BASE_LIMIT (${base})" >&2
  exit 1
  fi
  bonus=$((limit - base))
fi

container="${project}-${db_service}-1"

sql="
create or replace function dune.subfief_limit_bonus_attributes(in_gas_attributes jsonb)
returns jsonb
language sql
as \$\$
  select jsonb_set(
    jsonb_set(
      coalesce(in_gas_attributes, '{}'::jsonb),
      '{DunePlayerCharacterAttributeSet}',
      coalesce(in_gas_attributes #> '{DunePlayerCharacterAttributeSet}', '{}'::jsonb),
      true
    ),
    '{DunePlayerCharacterAttributeSet,SubfiefLimitBonus}',
    jsonb_build_object('BaseValue', ${bonus}::float, 'CurrentValue', ${bonus}::float),
    true
  );
\$\$;

create or replace function dune.apply_subfief_limit_bonus()
returns trigger
language plpgsql
as \$\$
begin
  if new.class = '/Game/Dune/Characters/Player/BP_DunePlayerCharacter.BP_DunePlayerCharacter_C'
     or exists (select 1 from dune.player_state where player_pawn_id = new.id) then
    new.gas_attributes = dune.subfief_limit_bonus_attributes(new.gas_attributes);
  end if;
  return new;
end;
\$\$;

create or replace function dune.apply_subfief_limit_bonus_from_player_state()
returns trigger
language plpgsql
as \$\$
begin
  if new.player_pawn_id is not null then
    update dune.actors
    set gas_attributes = dune.subfief_limit_bonus_attributes(gas_attributes)
    where id = new.player_pawn_id;
  end if;
  return new;
end;
\$\$;

drop trigger if exists apply_subfief_limit_bonus_on_actors on dune.actors;
create trigger apply_subfief_limit_bonus_on_actors
before insert or update of class, gas_attributes
on dune.actors
for each row
execute function dune.apply_subfief_limit_bonus();

drop trigger if exists apply_subfief_limit_bonus_on_player_state on dune.encrypted_player_state;
create trigger apply_subfief_limit_bonus_on_player_state
after insert or update of player_pawn_id
on dune.encrypted_player_state
for each row
execute function dune.apply_subfief_limit_bonus_from_player_state();

with target as (
  select id, 'player_character_class' as source
  from dune.actors
  where class = '/Game/Dune/Characters/Player/BP_DunePlayerCharacter.BP_DunePlayerCharacter_C'
  union
  select player_pawn_id as id, 'current_player_state_pawn' as source
  from dune.player_state
  where player_pawn_id is not null
),
updated as (
  update dune.actors a
  set gas_attributes = dune.subfief_limit_bonus_attributes(a.gas_attributes)
  from target
  where a.id = target.id
  returning a.id, target.source
)
select
  count(distinct id) as updated_player_actors,
  count(distinct id) filter (where source = 'player_character_class') as updated_player_character_class_actors,
  count(distinct id) filter (where source = 'current_player_state_pawn') as updated_current_player_state_pawns,
  ${limit} as desired_subfief_limit,
  ${base} as assumed_base_limit,
  ${bonus} as applied_subfief_limit_bonus
from updated;
"

dry_sql="
with target as (
  select id, 'player_character_class' as source
  from dune.actors
  where class = '/Game/Dune/Characters/Player/BP_DunePlayerCharacter.BP_DunePlayerCharacter_C'
  union
  select player_pawn_id as id, 'current_player_state_pawn' as source
  from dune.player_state
  where player_pawn_id is not null
)
select
  count(distinct a.id) as player_actors,
  count(distinct a.id) filter (where target.source = 'player_character_class') as player_character_class_actors,
  count(distinct a.id) filter (where target.source = 'current_player_state_pawn') as current_player_state_pawns,
  ${limit} as desired_subfief_limit,
  ${base} as assumed_base_limit,
  ${bonus} as derived_subfief_limit_bonus,
  count(distinct a.id) filter (
    where a.gas_attributes #> '{DunePlayerCharacterAttributeSet,SubfiefLimitBonus}' is not null
  ) as actors_already_with_subfief_bonus
from target
join dune.actors a on a.id = target.id;
"

rollback_sql="
drop trigger if exists apply_subfief_limit_bonus_on_actors on dune.actors;
drop trigger if exists apply_subfief_limit_bonus_on_player_state on dune.encrypted_player_state;
drop function if exists dune.apply_subfief_limit_bonus();
drop function if exists dune.apply_subfief_limit_bonus_from_player_state();
drop function if exists dune.subfief_limit_bonus_attributes(jsonb);
"

case "$mode" in
  apply)
    docker exec "$container" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -c "$sql"
    ;;
  dry-run|preview)
    docker exec "$container" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -c "$dry_sql"
    ;;
  rollback|remove|uninstall)
    docker exec "$container" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -c "$rollback_sql"
    ;;
  *)
    echo "usage: $0 [env-file] [apply|dry-run|rollback]" >&2
    exit 1
    ;;
esac
