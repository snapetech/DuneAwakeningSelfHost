#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/dd-pre-restore-backup.sh [options]

Creates a manifested Deep Desert pre-restore backup under backups/manual/.
The backup always includes a full Postgres custom dump and DD/BRT metadata.

Options:
  --env-file FILE              Env file. Default: .env
  --label TEXT                 Manifest label for the canary/test.
  --dd-partitions LIST         Comma-separated DD partitions. Default: 8,31
  --required-host HOST         Host safety guard. Default: kspls0
  --allow-dd-players           Allow backup while DD connected_players > 0.
  --brt-player-id ID           Player/controller id for source BRT backup.
  --brt-character NAME         Character name for source BRT backup lookup.
  --brt-totem-id ID            Totem id for source BRT backup.
  --commit-brt-backup          Commit dune.base_backup_save_from_totem().
  --no-post-brt-db-dump        Skip post-source-backup DB dump after commit.
  -h, --help                   Show this help.

Committed BRT source backups require DD connected_players=0 unless
--allow-dd-players is passed, and still require the full pre-mutation DB dump.
EOF
}

env_file=".env"
label="dd-pre-restore"
dd_partitions="${DUNE_DD_PRE_RESTORE_PARTITIONS:-8,31}"
required_host="${DUNE_DD_PRE_RESTORE_REQUIRED_HOST:-kspls0}"
allow_dd_players=false
brt_player_id=""
brt_character=""
brt_totem_id=""
commit_brt_backup=false
post_brt_db_dump=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_file="${2:?missing value for --env-file}"
      shift 2
      ;;
    --label)
      label="${2:?missing value for --label}"
      shift 2
      ;;
    --dd-partitions)
      dd_partitions="${2:?missing value for --dd-partitions}"
      shift 2
      ;;
    --required-host)
      required_host="${2:?missing value for --required-host}"
      shift 2
      ;;
    --allow-dd-players)
      allow_dd_players=true
      shift
      ;;
    --brt-player-id)
      brt_player_id="${2:?missing value for --brt-player-id}"
      shift 2
      ;;
    --brt-character|--brt-character-name)
      brt_character="${2:?missing value for --brt-character}"
      shift 2
      ;;
    --brt-totem-id)
      brt_totem_id="${2:?missing value for --brt-totem-id}"
      shift 2
      ;;
    --commit-brt-backup)
      commit_brt_backup=true
      shift
      ;;
    --no-post-brt-db-dump)
      post_brt_db_dump=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
cd "$repo_root"

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ -n "$required_host" && "$short_host" != "$required_host" && "${DUNE_DD_PRE_RESTORE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  printf "ERROR: refusing to run on host '%s'; required '%s'.\n" "$short_host" "$required_host" >&2
  exit 1
fi

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

if [[ "$commit_brt_backup" == true && -z "$brt_totem_id" ]]; then
  printf 'ERROR: --commit-brt-backup requires --brt-totem-id.\n' >&2
  exit 2
fi

if [[ -n "$brt_totem_id" && -z "$brt_player_id" && -z "$brt_character" ]]; then
  printf 'ERROR: --brt-totem-id requires --brt-player-id or --brt-character.\n' >&2
  exit 2
fi

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

container_runtime="${CONTAINER_RUNTIME:-docker}"
COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
export COMPOSE_FILES
compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "$COMPOSE_FILES"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

db="${DUNE_GAME_DB_NAME:-$(env_value DUNE_GAME_DB_NAME)}"
db="${db:-${DUNE_DATABASE:-$(env_value DUNE_DATABASE)}}"
db="${db:-${DUNE_DB_NAME:-$(env_value DUNE_DB_NAME)}}"
db="${db:-dune_sb_1_4_0_0}"
world_unique_name="$(env_value WORLD_UNIQUE_NAME)"
dune_fls_env="$(env_value DUNE_FLS_ENV)"
game_rmq_public_host="$(env_value GAME_RMQ_PUBLIC_HOST)"

psql_db() {
  "${compose[@]}" exec -T postgres \
    psql -U dune -d "$db" -v ON_ERROR_STOP=1 -P pager=off "$@"
}

service_running() {
  local service="$1"
  "${compose[@]}" ps --services --filter status=running 2>/dev/null | grep -qx "$service"
}

archive_optional_state() {
  local service="$1" container_dir="$2" local_dir="$3" archive="$4"
  if service_running "$service"; then
    if ! "${compose[@]}" exec -T "$service" tar -czf - -C "$container_dir" . > "$archive"; then
      printf 'WARN: failed to archive %s from running service %s\n' "$container_dir" "$service" >&2
      rm -f "$archive"
    fi
  elif [[ -d "$local_dir" ]]; then
    if ! tar -czf "$archive" -C "$local_dir" .; then
      printf 'WARN: failed to archive local dir %s\n' "$local_dir" >&2
      rm -f "$archive"
    fi
  fi
}

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
dd_connected_players="${dd_connected_players:-0}"
if [[ "$allow_dd_players" == false && "$dd_connected_players" != "0" ]]; then
  printf 'ERROR: refusing DD pre-restore backup while DD connected_players=%s for partitions %s.\n' "$dd_connected_players" "$dd_partitions" >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="backups/manual/dd-pre-restore-${stamp}"
case "$backup_dir" in
  backups/manual/*) ;;
  *)
    printf 'refusing to write backup outside ignored backups/manual/: %s\n' "$backup_dir" >&2
    exit 1
    ;;
esac
if [[ -e "$backup_dir" ]]; then
  printf 'backup dir already exists: %s\n' "$backup_dir" >&2
  exit 1
fi
mkdir -p "$backup_dir"

printf 'backup_dir=%s\n' "$backup_dir"
printf 'database=%s\n' "$db"
printf 'dd_connected_players=%s\n' "$dd_connected_players"

install -m 600 "$env_file" "$backup_dir/$(basename "$env_file")"
printf '%s\n' "$COMPOSE_FILES" > "$backup_dir/compose-files.txt"
tar --exclude='config/tls' --exclude='config/tls/**' -czf "$backup_dir/config.tgz" config
if [[ -d config/tls ]]; then
  tar -czf "$backup_dir/config-tls.tgz" config/tls
fi

dump_file="$backup_dir/postgres-${db}.dump"
printf 'writing postgres dump: %s\n' "$dump_file"
"${compose[@]}" exec -T postgres pg_dump -U dune -d "$db" -Fc > "$dump_file"

archive_optional_state survival /home/dune/server/DuneSandbox/Saved data/server-saved "$backup_dir/server-saved.tgz"
archive_optional_state admin-rmq /var/lib/rabbitmq data/rabbitmq/admin "$backup_dir/rabbitmq-admin.tgz"
archive_optional_state game-rmq /var/lib/rabbitmq data/rabbitmq/game "$backup_dir/rabbitmq-game.tgz"

if command -v pg_restore >/dev/null 2>&1; then
  pg_restore --list "$dump_file" > "$backup_dir/postgres-${db}.list"
else
  "${compose[@]}" exec -T postgres sh -c 'tmp="$(mktemp)"; cat > "$tmp"; pg_restore --list "$tmp"; rm -f "$tmp"' \
    < "$dump_file" > "$backup_dir/postgres-${db}.list"
fi

psql_db -A -F $'\t' -v dd_partitions="$dd_partitions" <<'SQL' > "$backup_dir/dd-partition-health.tsv"
with wanted(partition_id) as (
  select unnest(string_to_array(:'dd_partitions', ',')::int[])
)
select
  wp.partition_id,
  wp.server_id,
  wp.map,
  wp.dimension_index,
  wp.label,
  coalesce(fs.connected_players, 0) as connected_players,
  fs.ready,
  fs.alive,
  asi.server_id is not null as active,
  fs.revision,
  fs.game_addr,
  fs.igw_addr
from wanted w
join dune.world_partition wp on wp.partition_id = w.partition_id
left join dune.farm_state fs on fs.server_id = wp.server_id
left join dune.active_server_ids asi on asi.server_id = wp.server_id
order by wp.partition_id;
SQL

psql_db -A -F $'\t' -v dd_partitions="$dd_partitions" <<'SQL' > "$backup_dir/dd-counts.tsv"
with wanted(partition_id) as (
  select unnest(string_to_array(:'dd_partitions', ',')::int[])
),
dd_actors as (
  select id from dune.actors where partition_id in (select partition_id from wanted)
),
dd_vehicles as (
  select id from dune.vehicles where id in (select id from dd_actors)
)
select 'actors' as table_name, count(*)::bigint as rows from dd_actors
union all select 'actor_state', count(*) from dune.actor_state where actor_id in (select id from dd_actors)
union all select 'building_instances', count(*) from dune.building_instances where building_id in (select id from dd_actors)
union all select 'buildings', count(*) from dune.buildings where id in (select id from dd_actors)
union all select 'landclaim_segments', count(*) from dune.landclaim_segments where totem_id in (select id from dd_actors)
union all select 'permission_actor', count(*) from dune.permission_actor where actor_id in (select id from dd_actors)
union all select 'permission_actor_rank', count(*) from dune.permission_actor_rank where permission_actor_id in (select id from dd_actors)
union all select 'placeables', count(*) from dune.placeables where id in (select id from dd_actors)
union all select 'totems', count(*) from dune.totems where id in (select id from dd_actors)
union all select 'vehicles', count(*) from dd_vehicles
union all select 'vehicle_modules', count(*) from dune.vehicle_modules where vehicle_id in (select id from dd_vehicles)
union all select 'base_backups', count(*) from dune.base_backups
union all select 'base_backup_linked_actors', count(*) from dune.base_backup_linked_actors
order by table_name;
SQL

psql_db -A -F $'\t' <<'SQL' > "$backup_dir/brt-backups-before.tsv"
select
  bb.id,
  bb.player_id,
  bb.base_backup_name,
  count(l.actor_id)::bigint as linked_actor_count,
  min(a.partition_id) as min_partition_id,
  max(a.partition_id) as max_partition_id
from dune.base_backups bb
left join dune.base_backup_linked_actors l on l.id = bb.id
left join dune.actors a on a.id = l.actor_id
group by bb.id, bb.player_id, bb.base_backup_name
order by bb.id desc;
SQL

psql_db -A -F $'\t' <<'SQL' > "$backup_dir/world-reset-seeds.tsv"
select 'world_farm_reset_seed' as table_name, null::integer as partition_id, world_reset_seed from dune.world_farm_reset_seed
union all
select 'world_map_reset_seed' as table_name, null::integer as partition_id, world_reset_seed from dune.world_map_reset_seed
union all
select 'world_partition_reset_seed' as table_name, partition_id, world_reset_seed from dune.world_partition_reset_seed
order by table_name, partition_id nulls first;
SQL

for service in deep-desert deep-desert-pvp; do
  cid="$("${compose[@]}" ps -q "$service" 2>/dev/null || true)"
  if [[ -n "$cid" ]]; then
    "$container_runtime" inspect "$cid" > "$backup_dir/docker-${service}.inspect.json" || true
    "$container_runtime" logs --since=10m "$cid" > "$backup_dir/docker-${service}.log" 2>&1 || true
  fi
done

brt_backup_id=""
if [[ -n "$brt_totem_id" ]]; then
  brt_args=(--env-file "$env_file" --totem-id "$brt_totem_id")
  if [[ -n "$brt_player_id" ]]; then
    brt_args+=(--player-id "$brt_player_id")
  else
    brt_args+=(--character "$brt_character")
  fi
  if [[ "$commit_brt_backup" == true ]]; then
    brt_args+=(--commit)
    printf 'creating committed BRT source backup\n'
    CONFIRM='CREATE BRT DB BACKUP' "$script_dir/brt-dd-synthetic-db-backup.sh" "${brt_args[@]}" \
      > "$backup_dir/brt-source-backup.log" 2>&1
  else
    printf 'dry-running BRT source backup\n'
    "$script_dir/brt-dd-synthetic-db-backup.sh" "${brt_args[@]}" \
      > "$backup_dir/brt-source-backup.log" 2>&1
  fi
  brt_backup_id="$(
    awk '
      /synthetic_backup_id/ {want=1; next}
      want && $0 ~ /^[[:space:]-]+$/ {next}
      want && $0 ~ /^[[:space:]]*[0-9]+[[:space:]]*$/ {
        gsub(/[[:space:]]/, "", $0)
        print
        exit
      }
    ' "$backup_dir/brt-source-backup.log"
  )"
  printf '%s\n' "$brt_backup_id" > "$backup_dir/brt-source-backup-id.txt"

  psql_db -A -F $'\t' <<'SQL' > "$backup_dir/brt-backups-after.tsv"
select
  bb.id,
  bb.player_id,
  bb.base_backup_name,
  count(l.actor_id)::bigint as linked_actor_count,
  min(a.partition_id) as min_partition_id,
  max(a.partition_id) as max_partition_id
from dune.base_backups bb
left join dune.base_backup_linked_actors l on l.id = bb.id
left join dune.actors a on a.id = l.actor_id
group by bb.id, bb.player_id, bb.base_backup_name
order by bb.id desc;
SQL

  if [[ "$commit_brt_backup" == true && "$post_brt_db_dump" == true ]]; then
    post_dump_file="$backup_dir/postgres-${db}-after-brt-backup.dump"
    printf 'writing post-BRT-source postgres dump: %s\n' "$post_dump_file"
    "${compose[@]}" exec -T postgres pg_dump -U dune -d "$db" -Fc > "$post_dump_file"
    if command -v pg_restore >/dev/null 2>&1; then
      pg_restore --list "$post_dump_file" > "$backup_dir/postgres-${db}-after-brt-backup.list"
    else
      "${compose[@]}" exec -T postgres sh -c 'tmp="$(mktemp)"; cat > "$tmp"; pg_restore --list "$tmp"; rm -f "$tmp"' \
        < "$post_dump_file" > "$backup_dir/postgres-${db}-after-brt-backup.list"
    fi
  fi
fi

cat > "$backup_dir/manifest.txt" <<EOF
created_utc=${stamp}
reason=dd pre-restore backup
label=${label}
host=${short_host}
env_file=${env_file}
env_archive=$(basename "$env_file")
database=${db}
compose_files=${COMPOSE_FILES}
world_unique_name=${world_unique_name}
dune_fls_env=${dune_fls_env:-retail}
game_rmq_public_host=${game_rmq_public_host}
dd_partitions=${dd_partitions}
dd_connected_players=${dd_connected_players}
postgres_dump=$(basename "$dump_file")
commit_brt_backup=${commit_brt_backup}
brt_player_id=${brt_player_id}
brt_character=${brt_character}
brt_totem_id=${brt_totem_id}
brt_backup_id=${brt_backup_id}
post_brt_db_dump=${post_brt_db_dump}
config_archive=config.tgz
config_tls_archive=config-tls.tgz
server_saved_archive=server-saved.tgz
rabbitmq_admin_archive=rabbitmq-admin.tgz
rabbitmq_game_archive=rabbitmq-game.tgz
EOF

(
  cd "$backup_dir"
  find . -maxdepth 1 -type f ! -name sha256sums.txt -print0 | sort -z | xargs -0 sha256sum
) > "$backup_dir/sha256sums.txt"

printf 'backup complete: %s\n' "$backup_dir"
if [[ -n "$brt_backup_id" ]]; then
  printf 'brt_backup_id=%s\n' "$brt_backup_id"
fi
