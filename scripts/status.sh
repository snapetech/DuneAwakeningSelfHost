#!/usr/bin/env bash
set -euo pipefail

compose=(docker compose --env-file .env)
db=dune_sb_1_4_0_0

redact() {
  sed -E \
    -e 's/(ServiceAuthToken=)[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(ServiceAuthToken: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(DatabasePassword=)[^ ]+/\1[redacted]/g' \
    -e 's/(Password=)[^;]+/\1[redacted]/g' \
    -e 's#(sg\.sh-[^/ ]+/)[A-Za-z0-9+/=_-]+#\1[redacted]#g'
}

echo "== containers =="
"${compose[@]}" ps

echo
echo "== database state =="
"${compose[@]}" exec -T postgres psql -U dune -d "$db" -c "
select server_id,farm_id,ready,alive,map,revision,game_addr,igw_addr
from dune.farm_state
order by map, server_id;

select *
from dune.active_server_ids
order by server_id;

select partition_id,server_id,map,dimension_index,label
from dune.world_partition
order by partition_id;
"

echo
echo "== rabbitmq game connections =="
"${compose[@]}" exec -T game-rmq rabbitmqctl list_connections name user peer_host state 2>/dev/null || true

echo
echo "== recent high-signal logs =="
"${compose[@]}" logs --since=5m survival director text-router gateway game-rmq 2>&1 \
  | redact \
  | rg -n "Autologin|ACCESS_REFUSED|Invalid token|PLAIN login refused|LogRmq|Director_InitializeDirector|Battlegroups_|Population|Heartbeat|Server .*listening|FarmHealth|partition|ready|error|failed|Exception" -i \
  || true
