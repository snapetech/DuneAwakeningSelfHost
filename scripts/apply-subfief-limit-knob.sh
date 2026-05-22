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

limit="$(read_env DUNE_SUBFIEF_LIMIT "${DUNE_SUBFIEF_LIMIT:-}")"
base="$(read_env DUNE_SUBFIEF_BASE_LIMIT "${DUNE_SUBFIEF_BASE_LIMIT:-3}")"
explicit_bonus="$(read_env DUNE_SUBFIEF_LIMIT_BONUS "${DUNE_SUBFIEF_LIMIT_BONUS:-}")"
project="$(read_env COMPOSE_PROJECT_NAME "${COMPOSE_PROJECT_NAME:-dune_server}")"
db_service="$(read_env DUNE_POSTGRES_SERVICE "${DUNE_POSTGRES_SERVICE:-postgres}")"
db_name="$(read_env DUNE_POSTGRES_DB "${DUNE_POSTGRES_DB:-dune_sb_1_4_0_0}")"
db_user="$(read_env DUNE_POSTGRES_USER "${DUNE_POSTGRES_USER:-dune}")"

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
create or replace function dune.apply_subfief_limit_bonus()
returns trigger
language plpgsql
as \$\$
begin
  if new.class = '/Game/Dune/Characters/Player/BP_DunePlayerCharacter.BP_DunePlayerCharacter_C' then
    new.gas_attributes = jsonb_set(
      jsonb_set(
        coalesce(new.gas_attributes, '{}'::jsonb),
        '{DunePlayerCharacterAttributeSet}',
        coalesce(new.gas_attributes #> '{DunePlayerCharacterAttributeSet}', '{}'::jsonb),
        true
      ),
      '{DunePlayerCharacterAttributeSet,SubfiefLimitBonus}',
      jsonb_build_object('BaseValue', ${bonus}::float, 'CurrentValue', ${bonus}::float),
      true
    );
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

with target as (
  select id
  from dune.actors
  where class = '/Game/Dune/Characters/Player/BP_DunePlayerCharacter.BP_DunePlayerCharacter_C'
),
updated as (
  update dune.actors a
  set gas_attributes = jsonb_set(
    jsonb_set(
      coalesce(a.gas_attributes, '{}'::jsonb),
      '{DunePlayerCharacterAttributeSet}',
      coalesce(a.gas_attributes #> '{DunePlayerCharacterAttributeSet}', '{}'::jsonb),
      true
    ),
    '{DunePlayerCharacterAttributeSet,SubfiefLimitBonus}',
    jsonb_build_object('BaseValue', ${bonus}::float, 'CurrentValue', ${bonus}::float),
    true
  )
  from target
  where a.id = target.id
  returning a.id
)
select count(*) as updated_player_actors, ${limit} as desired_subfief_limit, ${base} as assumed_base_limit, ${bonus} as applied_subfief_limit_bonus
from updated;
"

dry_sql="
select
  count(*) as player_actors,
  ${limit} as desired_subfief_limit,
  ${base} as assumed_base_limit,
  ${bonus} as derived_subfief_limit_bonus,
  count(*) filter (
    where gas_attributes #> '{DunePlayerCharacterAttributeSet,SubfiefLimitBonus}' is not null
  ) as actors_already_with_subfief_bonus
from dune.actors
where class = '/Game/Dune/Characters/Player/BP_DunePlayerCharacter.BP_DunePlayerCharacter_C';
"

rollback_sql="
drop trigger if exists apply_subfief_limit_bonus_on_actors on dune.actors;
drop function if exists dune.apply_subfief_limit_bonus();
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
