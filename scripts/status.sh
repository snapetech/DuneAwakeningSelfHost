#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
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

redact() {
  sed -E \
    -e 's/(code=)[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(ServiceAuthKey["\\: ]+)[A-Za-z0-9+/=_-]+/\1[redacted]/g' \
    -e 's/eyJ[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+/[redacted-jwt]/g' \
    -e 's/(ServiceAuthToken=)[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(ServiceAuthToken: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(DatabasePassword=)[^ ]+/\1[redacted]/g' \
    -e 's/(Password=)[^;]+/\1[redacted]/g' \
    -e 's#(sg\.sh-[^/ ]+/)[A-Za-z0-9+/=_-]+#\1[redacted]#g' \
    -e 's#(sg|bgd|tr)\.sh-[A-Za-z0-9_.+/-]+#\1.sh-[redacted]#g' \
    -e 's/sh-[0-9a-fA-F]{16}-[A-Za-z0-9]+/sh-[redacted]/g'
}

echo "== containers =="
"${compose[@]}" ps

container_ids="$("${compose[@]}" ps -q 2>/dev/null || true)"

if [[ -n "$container_ids" ]]; then
  echo
  echo "== resource snapshot =="
  "$container_runtime" stats --no-stream --format \
    'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}' \
    $container_ids \
    || true

  echo
  echo "== restart counts =="
  "$container_runtime" inspect \
    --format '{{ index .Config.Labels "com.docker.compose.service" }} restart_count={{ .RestartCount }} oom_killed={{ .State.OOMKilled }} status={{ .State.Status }}' \
    $container_ids \
    | sort \
    || true
fi

echo
echo "== health verdict =="
current_ready_alive="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "
select count(*)
from dune.world_partition wp
join dune.farm_state fs on fs.server_id = wp.server_id
join dune.active_server_ids asi on asi.server_id = wp.server_id
where fs.ready and fs.alive;
" 2>/dev/null || printf '0')"
current_alive_active="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "
select count(*)
from dune.world_partition wp
join dune.farm_state fs on fs.server_id = wp.server_id
join dune.active_server_ids asi on asi.server_id = wp.server_id
where fs.alive;
" 2>/dev/null || printf '0')"
active_servers="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "select count(*) from dune.active_server_ids;" 2>/dev/null || printf '0')"
partitions="$("${compose[@]}" exec -T postgres psql -U dune -d "$db" -Atc "select count(*) from dune.world_partition;" 2>/dev/null || printf '0')"
game_sg_connections="$("${compose[@]}" exec -T game-rmq rabbitmqctl list_connections user 2>/dev/null | rg -c '^sg\.' || true)"
admin_sg_connections="$("${compose[@]}" exec -T admin-rmq rabbitmqctl list_connections user 2>/dev/null | rg -c '^sg\.' || true)"

if [[ "$current_alive_active" -gt 0 && "$current_alive_active" -eq "$partitions" && "$active_servers" -eq "$partitions" && "$game_sg_connections" -ge "$partitions" && "$admin_sg_connections" -ge "$partitions" ]]; then
  echo "OK: all current partitions have alive active farm rows, active server ids exist, and game/admin RMQ service users are connected."
else
  echo "WARN: expected readiness signals are incomplete."
fi
if [[ "$current_ready_alive" -lt "$partitions" ]]; then
  echo "NOTE: one or more current partitions are alive/active but have ready=false in farm_state. Check game logs for 'Server farm is READY' before treating this as fatal."
fi
if [[ "$admin_sg_connections" -lt "$partitions" ]]; then
  echo "NOTE: admin RMQ service-user connections are lower than farm-ready rows. This is expected for some warm-pool/on-demand maps, but investigate if admin mutations or heartbeats fail."
fi
printf 'current_ready_alive=%s current_alive_active=%s active_servers=%s partitions=%s game_sg_connections=%s admin_sg_connections=%s\n' \
  "$current_ready_alive" "$current_alive_active" "$active_servers" "$partitions" "$game_sg_connections" "$admin_sg_connections"

echo
echo "== FLS publication health =="
if "$script_dir/fls-publication-health.py" "$env_file" --compose-files "${COMPOSE_FILES:-compose.yaml}"; then
  :
else
  echo "WARN: FLS publication health is degraded. The local farm can be healthy while the server browser is stale/offline."
fi

echo
echo "== database state =="
"${compose[@]}" exec -T postgres psql -U dune -d "$db" -c "
select
  wp.partition_id,
  wp.server_id,
  wp.map,
  wp.dimension_index,
  wp.label,
  fs.farm_id,
  fs.ready,
  fs.alive,
  asi.server_id is not null as active,
  fs.connected_players,
  fs.revision,
  fs.game_addr,
  fs.igw_addr
from dune.world_partition wp
left join dune.farm_state fs on fs.server_id = wp.server_id
left join dune.active_server_ids asi on asi.server_id = wp.server_id
order by wp.partition_id;

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
  coalesce((select sum(connected_players) from dune.farm_state), 0) as connected_players_reported,
  (select count(*) from dune.get_online_player_controller_ids_on_farm()) as online_controller_ids,
  (select count(*) from dune.get_all_online_or_recently_disconnected_player_online_state()) as online_or_recently_disconnected,
  (select count(*) from dune.get_player_online_state_within_grace_period_for_each_server()) as grace_period_entries;
" || true

echo
echo "== rabbitmq game connections =="
"${compose[@]}" exec -T game-rmq rabbitmqctl list_connections name user peer_host state 2>/dev/null \
  | redact \
  || true

echo
echo "== rabbitmq admin connections =="
"${compose[@]}" exec -T admin-rmq rabbitmqctl list_connections name user peer_host state 2>/dev/null \
  | redact \
  || true

echo
echo "== recent high-signal logs =="
"${compose[@]}" logs --since=5m --tail=800 2>&1 \
  | redact \
  | rg -n "Autologin|ACCESS_REFUSED|Invalid token|PLAIN login refused|LogRmq|Director_InitializeDirector|Battlegroups_|Population|Heartbeat|Server .*listening|FarmHealth|partition|ready|error|failed|Exception" -i \
  || true
