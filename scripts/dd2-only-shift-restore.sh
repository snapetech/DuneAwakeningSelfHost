#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/dd2-only-shift-restore.sh [options] <backup-dir>

Restores a stopped-world backup, then advances only DD#2's partition seed.
It intentionally does not restore config/TLS, so current no-shift/no-wipe
guardrails remain in place for DD#1.

Options:
  --execute                 Required for live mutation. Without it, dry-run only.
  --env-file FILE           Env file. Default: .env
  --warning-seconds N       Player warning delay before stop. Default: 300
  --seed N                  Explicit DD#2 seed. Default: max current seed + 1
  --no-rabbitmq             Do not restore RabbitMQ archives from the backup.
  --no-server-saved         Do not restore server-saved archive from the backup.
  --skip-warning            Do not announce/sleep before stopping.
  -h, --help                Show this help.

Environment:
  DUNE_DD2_ONLY_REQUIRED_HOST    Required live hostname. Default: kspls0
  DUNE_DD2_ONLY_PARTITION_ID     DD#2 partition id. Default: 31
  DUNE_DD1_PARTITION_ID          DD#1 partition id. Default: 8
USAGE
}

env_file=".env"
execute=false
warning_seconds=300
explicit_seed=""
restore_rabbitmq=true
restore_server_saved=true
skip_warning=false
backup_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      execute=true
      shift
      ;;
    --env-file)
      env_file="${2:-}"
      shift 2
      ;;
    --warning-seconds)
      warning_seconds="${2:-}"
      shift 2
      ;;
    --seed)
      explicit_seed="${2:-}"
      shift 2
      ;;
    --no-rabbitmq)
      restore_rabbitmq=false
      shift
      ;;
    --no-server-saved)
      restore_server_saved=false
      shift
      ;;
    --skip-warning)
      skip_warning=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      printf 'unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      backup_dir="$1"
      shift
      ;;
  esac
done

if [[ -z "$backup_dir" ]]; then
  usage >&2
  exit 2
fi
if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi
if [[ ! -d "$backup_dir" ]]; then
  printf 'missing backup dir: %s\n' "$backup_dir" >&2
  exit 2
fi
case "$backup_dir" in
  backups/*) ;;
  *)
    printf 'refusing backup outside backups/: %s\n' "$backup_dir" >&2
    exit 2
    ;;
esac
if [[ ! "$warning_seconds" =~ ^[0-9]+$ ]]; then
  printf 'warning seconds must be an integer: %s\n' "$warning_seconds" >&2
  exit 2
fi
if [[ -n "$explicit_seed" && ! "$explicit_seed" =~ ^[0-9]+$ ]]; then
  printf 'seed must be an integer: %s\n' "$explicit_seed" >&2
  exit 2
fi

required_host="${DUNE_DD2_ONLY_REQUIRED_HOST:-kspls0}"
dd2_partition="${DUNE_DD2_ONLY_PARTITION_ID:-31}"
dd1_partition="${DUNE_DD1_PARTITION_ID:-8}"
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
runtime="${CONTAINER_RUNTIME:-docker}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

dump_file="$backup_dir/postgres-${db}.dump"
if [[ ! -f "$dump_file" ]]; then
  dump_file="$(find "$backup_dir" -maxdepth 1 -type f -name "*-${db}.dump" | sort | head -1)"
fi
if [[ -z "${dump_file:-}" || ! -f "$dump_file" ]]; then
  printf 'could not find postgres dump for %s in %s\n' "$db" "$backup_dir" >&2
  exit 2
fi

if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose=("$runtime" compose)
IFS=':' read -ra compose_file_array <<< "${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"
for compose_file in "${compose_file_array[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

host_name() {
  hostname -s 2>/dev/null || hostname 2>/dev/null || true
}

assert_live_host() {
  local actual
  actual="$(host_name)"
  if [[ "$actual" != "$required_host" ]]; then
    printf 'refusing live mutation: hostname is %s, required %s\n' "${actual:-unknown}" "$required_host" >&2
    exit 1
  fi
}

run_or_print() {
  if [[ "$execute" == true ]]; then
    "$@"
  else
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  fi
}

psql_live() {
  "${compose[@]}" exec -T postgres psql -U dune -d "$db" -v ON_ERROR_STOP=1 "$@"
}

seed_summary_sql='
select
  (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
  (select world_reset_seed from dune.world_map_reset_seed where map in ('\''DeepDesert'\'','\''DeepDesert_1'\'') order by map limit 1) as deep_desert_map_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = 8) as dd1_seed,
  (select world_reset_seed from dune.world_partition_reset_seed where partition_id = 31) as dd2_seed,
  (select count(*) from dune.shiftingsands_data) as static_shifting_rows;
'

print_live_summary() {
  local label="$1"
  printf '\n== %s ==\n' "$label"
  psql_live -P pager=off -c "$seed_summary_sql"
}

print_backup_summary() {
  printf '\n== backup seed/static-sand summary: %s ==\n' "$backup_dir"
  printf 'dump=%s\n' "$dump_file"
  pg_restore -a -t world_farm_reset_seed -f - "$dump_file" \
    | awk '$1 == "t" {print "farm_seed=" $2}'
  pg_restore -a -t world_map_reset_seed -f - "$dump_file" \
    | awk '$1 ~ /^DeepDesert/ {print "map_seed[" $1 "]=" $2}'
  pg_restore -a -t world_partition_reset_seed -f - "$dump_file" \
    | awk -v dd1="$dd1_partition" -v dd2="$dd2_partition" '$1 == dd1 || $1 == dd2 {print "partition_seed[" $1 "]=" $2}'
  pg_restore -a -t shiftingsands_data -f - "$dump_file" \
    | awk 'BEGIN{n=0} /^COPY/{copy=1; next} /^\\\./{copy=0} copy && NF>0 {n++} END{print "static_shifting_rows=" n}'
}

announce_and_wait() {
  if [[ "$skip_warning" == true ]]; then
    printf 'warning skipped by --skip-warning\n'
    return 0
  fi
  local minutes
  minutes=$(( (warning_seconds + 59) / 60 ))
  DUNE_ANNOUNCE_MESSAGE="Server maintenance in ${minutes} minutes. Please get to a safe place." \
    "$script_dir/announce.sh"
  printf 'sent player warning; sleeping %s seconds\n' "$warning_seconds"
  sleep "$warning_seconds"
}

make_safety_backup() {
  local stamp safety_dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  safety_dir="backups/manual/dd2-only-shift-pre-restore-${stamp}"
  mkdir -p "$safety_dir"
  cp "$env_file" "$safety_dir/$(basename "$env_file")"
  tar --exclude='config/tls' --exclude='config/tls/**' -czf "$safety_dir/config.tgz" config
  if [[ -d config/tls ]]; then
    tar -czf "$safety_dir/config-tls.tgz" config/tls
  fi
  "${compose[@]}" exec -T postgres pg_dump -U dune -d "$db" -Fc > "$safety_dir/postgres-${db}.dump"
  if [[ -d data/server-saved ]]; then
    tar -czf "$safety_dir/server-saved.tgz" -C data/server-saved .
  fi
  if [[ -d data/rabbitmq/admin ]]; then
    tar -czf "$safety_dir/rabbitmq-admin.tgz" -C data/rabbitmq/admin .
  fi
  if [[ -d data/rabbitmq/game ]]; then
    tar -czf "$safety_dir/rabbitmq-game.tgz" -C data/rabbitmq/game .
  fi
  cat > "$safety_dir/manifest.txt" <<EOF
created_utc=${stamp}
reason=dd2-only-shift pre-restore safety backup
source_backup=${backup_dir}
database=${db}
env_file=${env_file}
compose_files=${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}
EOF
  printf 'safety_backup=%s\n' "$safety_dir"
}

stop_runtime() {
  ENV_FILE="$env_file" DUNE_RESTART_TARGET=all DUNE_RESTART_ACTION=restart DUNE_RESTART_PHASE=stop \
    "$script_dir/restart-target.sh"
  "${compose[@]}" stop -t 30 admin-chat-commands admin-panel admin-rmq game-rmq || true
}

restore_state() {
  if [[ "$restore_server_saved" == true ]]; then
    if [[ ! -f "$backup_dir/server-saved.tgz" ]]; then
      printf 'missing server-saved archive: %s/server-saved.tgz\n' "$backup_dir" >&2
      exit 2
    fi
    rm -rf data/server-saved
    mkdir -p data/server-saved
    tar -xzf "$backup_dir/server-saved.tgz" -C data/server-saved
  fi

  if [[ "$restore_rabbitmq" == true ]]; then
    for archive in rabbitmq-admin.tgz rabbitmq-game.tgz; do
      if [[ ! -f "$backup_dir/$archive" ]]; then
        printf 'missing RabbitMQ archive: %s/%s\n' "$backup_dir" "$archive" >&2
        exit 2
      fi
    done
    rm -rf data/rabbitmq/admin data/rabbitmq/game
    mkdir -p data/rabbitmq/admin data/rabbitmq/game
    tar -xzf "$backup_dir/rabbitmq-admin.tgz" -C data/rabbitmq/admin
    tar -xzf "$backup_dir/rabbitmq-game.tgz" -C data/rabbitmq/game
  fi

  "${compose[@]}" up -d postgres
  "${compose[@]}" exec -T postgres pg_restore -U dune -d "$db" --clean --if-exists < "$dump_file"
}

apply_dd2_seed() {
  local seed_expr
  if [[ -n "$explicit_seed" ]]; then
    seed_expr="$explicit_seed"
  else
    seed_expr="null"
  fi
  psql_live -v dd1="$dd1_partition" -v dd2="$dd2_partition" -v requested_seed="$seed_expr" -P pager=off <<'SQL'
begin;
lock table dune.world_farm_reset_seed, dune.world_map_reset_seed, dune.world_partition_reset_seed in exclusive mode;

with seed_input as (
  select nullif(:'requested_seed', 'null')::integer as requested_seed
),
next_seed as (
  select coalesce(
    requested_seed,
    greatest(
      coalesce((select max(world_reset_seed) from dune.world_farm_reset_seed), 0),
      coalesce((select max(world_reset_seed) from dune.world_map_reset_seed), 0),
      coalesce((select max(world_reset_seed) from dune.world_partition_reset_seed), 0)
    ) + 1
  ) as value
  from seed_input
),
before_values as (
  select
    (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
    (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) as map_seed,
    (select world_reset_seed from dune.world_partition_reset_seed where partition_id = :dd1) as dd1_seed
),
write_dd2 as (
  insert into dune.world_partition_reset_seed(partition_id, world_reset_seed)
  select :dd2, value from next_seed
  on conflict(partition_id) do update
  set world_reset_seed = excluded.world_reset_seed
  returning world_reset_seed
),
after_values as (
  select
    (select world_reset_seed from dune.world_farm_reset_seed where onerow_id = true) as farm_seed,
    (select world_reset_seed from dune.world_map_reset_seed where map in ('DeepDesert','DeepDesert_1') order by map limit 1) as map_seed,
    (select world_reset_seed from dune.world_partition_reset_seed where partition_id = :dd1) as dd1_seed,
    (select world_reset_seed from write_dd2) as dd2_seed
)
select
  before_values.farm_seed as before_farm,
  after_values.farm_seed as after_farm,
  before_values.map_seed as before_map,
  after_values.map_seed as after_map,
  before_values.dd1_seed as before_dd1,
  after_values.dd1_seed as after_dd1,
  after_values.dd2_seed as after_dd2
from before_values, after_values;

notify world_partition_update;
commit;
SQL
}

start_runtime() {
  "${compose[@]}" up -d admin-rmq game-rmq admin-panel admin-chat-commands
  ENV_FILE="$env_file" DUNE_RESTART_TARGET=all DUNE_RESTART_ACTION=restart DUNE_RESTART_PHASE=start \
    "$script_dir/restart-target.sh"
}

main() {
  printf 'host=%s required_host=%s execute=%s\n' "$(host_name)" "$required_host" "$execute"
  print_backup_summary
  if "${compose[@]}" ps -q postgres >/dev/null 2>&1; then
    print_live_summary "live before"
  fi
  if [[ "$execute" != true ]]; then
    printf '\ndry-run complete; rerun with --execute to mutate production\n'
    exit 0
  fi

  assert_live_host
  announce_and_wait
  stop_runtime
  make_safety_backup
  restore_state
  apply_dd2_seed
  print_live_summary "after restore + DD2-only seed"
  if [[ -x "$script_dir/brt-dd-next-downtime.sh" ]]; then
    "$script_dir/brt-dd-next-downtime.sh" status "$env_file"
  fi
  start_runtime
  print_live_summary "live after start"
  if [[ -x "$script_dir/status.sh" ]]; then
    "$script_dir/status.sh" "$env_file"
  fi
}

main
