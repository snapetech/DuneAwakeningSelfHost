#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/capture-routing.sh [env-file] <label>

Examples:
  ./scripts/capture-routing.sh .env hagga-to-deep-desert-before
  ./scripts/capture-routing.sh hagga-to-arrakeen-after

Writes a redacted local capture under captures/. Do not publish captures without
reviewing them first; logs and database rows can still identify worlds, accounts,
addresses, or characters.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file=".env"
label="${1:-}"

if [[ "${2:-}" != "" ]]; then
  env_file="$1"
  label="$2"
fi

if [[ -z "$label" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

container_runtime="${CONTAINER_RUNTIME:-docker}"

if ! command -v "$container_runtime" >/dev/null 2>&1; then
  printf '%s is required\n' "$container_runtime" >&2
  exit 1
fi

safe_label="$(printf '%s' "$label" | tr -cs 'A-Za-z0-9._-' '-' | sed -E 's/^-+|-+$//g')"
if [[ -z "$safe_label" ]]; then
  printf 'label must contain at least one alphanumeric character\n' >&2
  exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="captures/${timestamp}-${safe_label}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
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
db=dune_sb_1_4_0_0

mkdir -p "$out_dir"

external_address="$(grep -E '^EXTERNAL_ADDRESS=' "$env_file" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
external_address_escaped="$(printf '%s' "$external_address" | sed -E 's/[][\\/.*^$()+?{}|]/\\&/g')"

cat > "$out_dir/README.txt" <<EOF
Routing capture: ${label}
Captured UTC: ${timestamp}

This directory is local-only and ignored by git. Review every file before
sharing it. Redaction covers known token, password, generated RabbitMQ user,
battlegroup id, and configured external-address patterns, but logs and database
rows can still contain world, character, account, network, or operational data.
EOF

redact_file() {
  local file="$1"
  sed -E -i \
    -e 's/(ServiceAuthToken=)[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(ServiceAuthToken: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(gateway_farm_api_key: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/([A-Za-z0-9_]*([Pp]assword|PASSWORD|[Ss]ecret|SECRET|[Tt]oken|TOKEN|[Aa]pi[Kk]ey|api_key)[A-Za-z0-9_]*: )[A-Za-z0-9_.+\/=-]+/\1[redacted]/g' \
    -e 's/([A-Za-z0-9_]*([Pp]assword|PASSWORD|[Ss]ecret|SECRET|[Tt]oken|TOKEN|[Aa]pi[Kk]ey|api_key)[A-Za-z0-9_]*=)[A-Za-z0-9_.+\/=-]+/\1[redacted]/g' \
    -e 's/(DatabasePassword=)[^ ]+/\1[redacted]/g' \
    -e 's/(DuneDatabaseInterfacePSQL_DatabasePassword: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(POSTGRES_[A-Z_]*PASSWORD: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(RMQ_HTTP_TOKEN_AUTH_SECRET: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(Password=)[^;]+/\1[redacted]/g' \
    -e 's#(sg\.sh-[^/ ]+/)[A-Za-z0-9+/=_-]+#\1[redacted]#g' \
    -e 's#(sg|bgd|tr)\.sh-[A-Za-z0-9_.+/-]+#\1.sh-[redacted]#g' \
    -e 's/sh-[0-9a-fA-F]{16}-[A-Za-z0-9]+/sh-[redacted]/g' \
    "$file"

  if [[ -n "$external_address_escaped" ]]; then
    sed -E -i "s/${external_address_escaped}/[external-address]/g" "$file"
  fi
}

capture() {
  local name="$1"
  shift
  {
    printf '# %s\n' "$name"
    printf '# captured_at=%s\n\n' "$timestamp"
    "$@"
  } >"$out_dir/$name.txt" 2>&1 || true
  redact_file "$out_dir/$name.txt"
}

container_ids="$("${compose[@]}" ps -q 2>/dev/null || true)"

capture metadata env bash -c '
  printf "label=%s\n" "$1"
  printf "env_file=%s\n" "$2"
  printf "utc=%s\n" "$3"
  printf "container_runtime=%s\n" "$4"
  printf "compose_files=%s\n" "$5"
' _ "$label" "$env_file" "$timestamp" "$container_runtime" "${COMPOSE_FILES:-compose.yaml}"

capture host-metadata bash -c '
  printf "hostname=%s\n" "$(hostname 2>/dev/null || true)"
  printf "kernel=%s\n" "$(uname -srmo 2>/dev/null || true)"
  printf "cpu_model=%s\n" "$(awk -F: "/model name/ { sub(/^[ \t]+/, \"\", \$2); print \$2; exit }" /proc/cpuinfo 2>/dev/null || true)"
  printf "cpu_count=%s\n" "$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
  printf "mem_total=%s\n" "$(awk "/MemTotal/ { print \$2 \" \" \$3 }" /proc/meminfo 2>/dev/null || true)"
  printf "runtime_version=%s\n" "$("$1" --version 2>/dev/null || true)"
  printf "compose_version=%s\n" "$("$1" compose version 2>/dev/null || true)"
' _ "$container_runtime"

capture compose-ps "${compose[@]}" ps
capture compose-config "${compose[@]}" config

if [[ -n "$container_ids" ]]; then
  capture container-stats "$container_runtime" stats --no-stream --format \
    'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}' \
    $container_ids

  capture restart-counts "$container_runtime" inspect \
    --format '{{ index .Config.Labels "com.docker.compose.service" }} restart_count={{ .RestartCount }} oom_killed={{ .State.OOMKilled }} status={{ .State.Status }} started_at={{ .State.StartedAt }} finished_at={{ .State.FinishedAt }}' \
    $container_ids
fi

capture db-routing "${compose[@]}" exec -T postgres psql -U dune -d "$db" -c "
select server_id,farm_id,ready,alive,map,revision,game_addr,igw_addr
from dune.farm_state
order by map, server_id;

select *
from dune.active_server_ids
order by server_id;

select partition_id,server_id,map,dimension_index,label
from dune.world_partition
order by partition_id;

select
  coalesce((
    select sum(fs.connected_players)
    from dune.world_partition wp
    join dune.farm_state fs on fs.server_id = wp.server_id
    join dune.active_server_ids asi on asi.server_id = wp.server_id
    where fs.alive
  ), 0) as active_farm_connected_players,
  coalesce((select sum(connected_players) from dune.farm_state), 0) as raw_farm_connected_players,
  (select count(*) from dune.get_online_player_controller_ids_on_farm()) as online_controller_ids,
  (select count(*) from dune.get_all_online_or_recently_disconnected_player_online_state()) as online_or_recently_disconnected,
  (select count(*) from dune.get_player_online_state_within_grace_period_for_each_server()) as grace_period_entries;
"

capture rabbitmq-connections "${compose[@]}" exec -T game-rmq rabbitmqctl list_connections name user peer_host state channels
capture rabbitmq-channels "${compose[@]}" exec -T game-rmq rabbitmqctl list_channels connection user number messages_unacknowledged messages_uncommitted acks_uncommitted
capture rabbitmq-queues "${compose[@]}" exec -T game-rmq rabbitmqctl list_queues name consumers messages messages_ready messages_unacknowledged state
capture recent-routing-logs "${compose[@]}" logs --since=20m

printf 'capture written: %s\n' "$out_dir"
