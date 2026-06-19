#!/usr/bin/env bash
set -euo pipefail

env_file=".env"
database="${DUNE_DB_NAME:-}"
required_host="${DUNE_BRT_DD_SYNTHETIC_HOST:-kspls0}"
player_id=""
character_name=""
totem_id=""
commit="false"
dd_partitions="${DUNE_BRT_DD_SYNTHETIC_DD_PARTITIONS:-8,31}"

usage() {
  sed -n '1,80p' "$0" | sed -n '/^# Usage:/,/^$/p'
}

# Usage:
#   scripts/brt-dd-synthetic-db-backup.sh --character Lukano --totem-id 5903
#   scripts/brt-dd-synthetic-db-backup.sh --player-id 17 --totem-id 5903
#   CONFIRM='CREATE BRT DB BACKUP' scripts/brt-dd-synthetic-db-backup.sh --player-id 17 --totem-id 5903 --commit
#
# Default mode opens a transaction, calls dune.base_backup_save_from_totem(),
# prints the rows it would create, and rolls back. --commit leaves the backup in
# dune.base_backups / dune.base_backup_linked_actors.

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_file="${2:?missing value for --env-file}"
      shift 2
      ;;
    --database)
      database="${2:?missing value for --database}"
      shift 2
      ;;
    --player-id)
      player_id="${2:?missing value for --player-id}"
      shift 2
      ;;
    --character|--character-name)
      character_name="${2:?missing value for --character}"
      shift 2
      ;;
    --totem-id)
      totem_id="${2:?missing value for --totem-id}"
      shift 2
      ;;
    --commit)
      commit="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
script_dir="${repo_root}/scripts"
cd "$repo_root"

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

database="${database:-${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}}"
database="${database:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
database="${database:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
database="${database:-dune_sb_1_4_0_0}"

container_runtime="${CONTAINER_RUNTIME:-docker}"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_SYNTHETIC_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "ERROR: refusing to run on host '$short_host'; required '$required_host'." >&2
  exit 1
fi

if [[ "$commit" == "true" && "${CONFIRM:-}" != "CREATE BRT DB BACKUP" ]]; then
  echo "ERROR: --commit requires CONFIRM='CREATE BRT DB BACKUP'." >&2
  exit 1
fi

psql_db() {
  "${compose[@]}" exec -T postgres \
    psql -U dune -d "$database" -v ON_ERROR_STOP=1 -P pager=off "$@"
}

if [[ "$commit" == "true" && "${DUNE_BRT_DD_SYNTHETIC_ALLOW_DD_PLAYERS:-0}" != "1" ]]; then
  dd_connected_players="$(psql_db -qAt -v dd_partitions="$dd_partitions" <<'SQL'
with wanted(partition_id) as (
  select unnest(string_to_array(:'dd_partitions', ',')::int[])
)
select coalesce(sum(coalesce(fs.connected_players, 0)), 0)::integer
from wanted w
join dune.world_partition wp on wp.partition_id = w.partition_id
left join dune.farm_state fs on fs.server_id = wp.server_id;
SQL
)"
  if [[ "${dd_connected_players:-0}" != "0" ]]; then
    echo "ERROR: refusing committed BRT backup while DD connected_players=${dd_connected_players} for partitions ${dd_partitions}." >&2
    exit 1
  fi
fi

if [[ -z "$player_id" ]]; then
  if [[ -z "$character_name" ]]; then
    echo "ERROR: pass --player-id or --character." >&2
    exit 2
  fi
  player_id="$(psql_db -qAt -v character_name="$character_name" <<'SQL'
select player_controller_id
from dune.player_state
where lower(character_name) = lower(:'character_name')
order by last_avatar_activity desc
limit 1;
SQL
)"
fi

if [[ -z "$player_id" ]]; then
  echo "ERROR: could not resolve player id." >&2
  exit 1
fi

if ! [[ "$player_id" =~ ^[0-9]+$ ]]; then
  echo "ERROR: player id is not numeric: $player_id" >&2
  exit 1
fi

echo "resolved_player_id=$player_id"
echo "available_totems:"
psql_db -v player_id="$player_id" <<'SQL'
select f.totem_id, a.map, a.partition_id, a.dimension_index, t.landclaim_original_global_location
from dune.base_backup_find_totems_from_player_owner(:player_id) f
left join dune.actors a on a.id = f.totem_id
left join dune.totems t on t.id = f.totem_id
order by a.map, f.totem_id;
SQL

if [[ -z "$totem_id" ]]; then
  echo "ERROR: pass --totem-id. Refusing to guess when a player has multiple totems." >&2
  exit 2
fi

if ! [[ "$totem_id" =~ ^[0-9]+$ ]]; then
  echo "ERROR: totem id is not numeric: $totem_id" >&2
  exit 1
fi

owned_count="$(psql_db -qAt -v player_id="$player_id" -v totem_id="$totem_id" <<'SQL'
select count(*)
from dune.base_backup_find_totems_from_player_owner(:player_id)
where totem_id = :totem_id;
SQL
)"
if [[ "$owned_count" != "1" ]]; then
  echo "ERROR: totem $totem_id is not returned by base_backup_find_totems_from_player_owner($player_id)." >&2
  exit 1
fi

if [[ "$commit" == "true" ]]; then
  end_statement="commit;"
  mode_label="COMMIT"
else
  end_statement="rollback;"
  mode_label="ROLLBACK"
fi

echo "mode=$mode_label"
psql_db -v player_id="$player_id" -v totem_id="$totem_id" -v end_statement="$end_statement" <<'SQL'
select 'before_base_backups' as label, count(*) from dune.base_backups;
select 'before_linked_actors' as label, count(*) from dune.base_backup_linked_actors;
begin;
select dune.base_backup_save_from_totem(:player_id, :totem_id) as synthetic_backup_id \gset
select :'synthetic_backup_id' as synthetic_backup_id;
select 'inside_base_backups' as label, count(*) from dune.base_backups;
select 'inside_linked_actors' as label, count(*) from dune.base_backup_linked_actors;
select 'available' as label, * from dune.base_backup_get_available_backups(:player_id)
  where id = :'synthetic_backup_id'::bigint;
select 'buildable_data' as label, * from dune.base_backup_get_buildable_data(:'synthetic_backup_id'::bigint);
:end_statement
select 'after_base_backups' as label, count(*) from dune.base_backups;
select 'after_linked_actors' as label, count(*) from dune.base_backup_linked_actors;
SQL
