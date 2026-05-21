#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/handoff-lab.sh COMMAND [ENV_FILE]

Commands:
  config              Validate the isolated handoff-lab Compose config.
  up                  Start the local passworded one-partition lab.
  seed                Ensure the lab database has one Survival_1 partition.
  status              Print lab health without touching production.
  dump FILE           Dump the local lab database to FILE.
  restore FILE        Restore FILE into the local lab database.
  stop                Stop the local lab stack.
  remote-up HOST      Start the lab on HOST using DUNE_HANDOFF_LAB_REPO_ROOT.
  remote-seed HOST    Seed the lab database on HOST.
  remote-status HOST  Print lab health on HOST.
  remote-stop HOST    Stop the lab stack on HOST.
  handoff SRC DST     Stop SRC after dumping it, restore into DST, then start DST.

SRC/DST are either "local" or an SSH host. This lab uses compose.handoff-lab.yaml,
alternate ports, separate data directories, and DUNE_SERVER_LOGIN_PASSWORD.
USAGE
}

cmd="${1:-}"
env_file="${2:-.env.handoff-lab}"
repo_root="${DUNE_HANDOFF_LAB_REPO_ROOT:-$(pwd)}"
compose_project="${COMPOSE_PROJECT_NAME:-dune_handoff_lab}"
compose_files=(compose.yaml compose.handoff-lab.yaml)
db="${DUNE_DB_NAME:-dune_sb_1_4_0_0}"
runtime="${CONTAINER_RUNTIME:-docker}"

if [[ -z "$cmd" || "$cmd" == "-h" || "$cmd" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$env_file" ]]; then
  printf 'missing lab env file: %s\n' "$env_file" >&2
  printf 'Create it from .env.handoff-lab.example and set DUNE_SERVER_LOGIN_PASSWORD plus the lab secrets.\n' >&2
  exit 2
fi

compose_args() {
  printf '%q ' "$runtime" compose --env-file "$env_file" -f "${compose_files[0]}" -f "${compose_files[1]}"
}

run_compose() {
  COMPOSE_PROJECT_NAME="$compose_project" "$runtime" compose --env-file "$env_file" -f "${compose_files[0]}" -f "${compose_files[1]}" "$@"
}

remote_repo() {
  local host="$1"
  local configured
  configured="$(awk -F= '$1 == "DUNE_HANDOFF_LAB_REPO_ROOT" { print $2 }' "$env_file" | tail -n1)"
  printf '%s' "${configured:-$repo_root}"
}

remote_run() {
  local host="$1"
  shift
  local root
  root="$(remote_repo "$host")"
  ssh "$host" "cd '$root' && COMPOSE_PROJECT_NAME='$compose_project' $*"
}

wait_for_postgres() {
  local tries="${1:-60}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if run_compose exec -T postgres pg_isready -U dune -d "$db" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  printf 'lab Postgres did not become ready\n' >&2
  return 1
}

seed_sql() {
  cat <<'SQL'
insert into dune.world_partition (partition_id, map, dimension_index, partition_definition)
select
  1,
  'Survival_1',
  0,
  '{"box":{"max_x":1,"max_y":1,"min_x":0,"min_y":0},"type":"box2d_array"}'::jsonb
where not exists (
  select 1 from dune.world_partition where partition_id = 1
);
select setval(
  pg_get_serial_sequence('dune.world_partition', 'partition_id'),
  greatest((select coalesce(max(partition_id), 1) from dune.world_partition), 1),
  true
);
select dune.update_partition_labels(false);
notify world_partition_update;
SQL
}

seed_local() {
  wait_for_postgres
  seed_sql | run_compose exec -T postgres psql -U dune -d "$db"
}

start_local() {
  run_compose up -d postgres admin-rmq game-rmq db-init
  wait_for_postgres
  seed_local
  run_compose up -d text-router director gateway rmq-auth-shim survival
}

status_local() {
  COMPOSE_PROJECT_NAME="$compose_project" COMPOSE_FILES="${compose_files[0]}:${compose_files[1]}" ./scripts/status.sh "$env_file"
}

dump_local() {
  local dump_file="$1"
  if [[ -z "$dump_file" ]]; then
    printf 'dump file is required\n' >&2
    exit 2
  fi
  wait_for_postgres
  run_compose exec -T postgres pg_dump -U dune -d "$db" -Fc > "$dump_file"
  printf 'wrote lab dump: %s\n' "$dump_file"
}

restore_local() {
  local dump_file="$1"
  if [[ ! -f "$dump_file" ]]; then
    printf 'missing dump file: %s\n' "$dump_file" >&2
    exit 2
  fi
  run_compose up -d postgres
  wait_for_postgres
  run_compose exec -T postgres createdb -U dune "$db" 2>/dev/null || true
  run_compose exec -T postgres pg_restore -U dune -d "$db" --clean --if-exists < "$dump_file" || {
    rc=$?
    printf 'pg_restore exited with %s; continuing only if verification succeeds\n' "$rc" >&2
  }
  run_compose exec -T postgres psql -U dune -d "$db" -c "select partition_id, map, dimension_index, label from dune.world_partition order by partition_id;"
}

stop_local() {
  run_compose stop survival director gateway text-router rmq-auth-shim game-rmq admin-rmq postgres
}

case "$cmd" in
  config)
    run_compose config --quiet
    ;;
  up)
    start_local
    ;;
  seed)
    seed_local
    ;;
  status)
    status_local
    ;;
  dump)
    dump_local "${3:-}"
    ;;
  restore)
    restore_local "${3:-}"
    ;;
  stop)
    stop_local
    ;;
  remote-up)
    host="${3:-}"
    [[ -n "$host" ]] || { printf 'remote host is required\n' >&2; exit 2; }
    remote_run "$host" "$(compose_args) up -d postgres admin-rmq game-rmq db-init"
    remote_run "$host" "./scripts/handoff-lab.sh seed '$env_file'"
    remote_run "$host" "$(compose_args) up -d text-router director gateway rmq-auth-shim survival"
    ;;
  remote-seed)
    host="${3:-}"
    [[ -n "$host" ]] || { printf 'remote host is required\n' >&2; exit 2; }
    remote_run "$host" "./scripts/handoff-lab.sh seed '$env_file'"
    ;;
  remote-status)
    host="${3:-}"
    [[ -n "$host" ]] || { printf 'remote host is required\n' >&2; exit 2; }
    remote_run "$host" "COMPOSE_PROJECT_NAME='$compose_project' COMPOSE_FILES='${compose_files[0]}:${compose_files[1]}' ./scripts/status.sh '$env_file'"
    ;;
  remote-stop)
    host="${3:-}"
    [[ -n "$host" ]] || { printf 'remote host is required\n' >&2; exit 2; }
    remote_run "$host" "./scripts/handoff-lab.sh stop '$env_file'"
    ;;
  handoff)
    src="${3:-}"
    dst="${4:-}"
    [[ -n "$src" && -n "$dst" ]] || { printf 'source and destination are required\n' >&2; exit 2; }
    dump_file="${DUNE_HANDOFF_LAB_DUMP_FILE:-/tmp/dune-handoff-lab-$(date -u +%Y%m%dT%H%M%SZ).dump}"
    if [[ "$src" == "local" ]]; then
      dump_local "$dump_file"
      stop_local
    else
      remote_run "$src" "$(compose_args) exec -T postgres pg_dump -U dune -d '$db' -Fc" > "$dump_file"
      remote_run "$src" "./scripts/handoff-lab.sh stop '$env_file'"
    fi
    if [[ "$dst" == "local" ]]; then
      restore_local "$dump_file"
      start_local
      status_local
    else
      remote_dump="/tmp/$(basename "$dump_file")"
      scp "$dump_file" "$dst:$remote_dump" >/dev/null
      remote_run "$dst" "./scripts/handoff-lab.sh restore '$env_file' '$remote_dump'"
      remote_run "$dst" "./scripts/handoff-lab.sh up '$env_file'"
      remote_run "$dst" "COMPOSE_PROJECT_NAME='$compose_project' COMPOSE_FILES='${compose_files[0]}:${compose_files[1]}' ./scripts/status.sh '$env_file'"
    fi
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
