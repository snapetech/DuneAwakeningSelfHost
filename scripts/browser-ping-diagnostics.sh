#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
compose_cmd="${COMPOSE:-docker compose}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

ini_value() {
  local file="$1" section="$2" key="$3"
  awk -F= -v section="$section" -v key="$key" '
    /^[[:space:]]*\[/ {
      current=$0
      gsub(/^[[:space:]]*\[/, "", current)
      gsub(/\][[:space:]]*$/, "", current)
      next
    }
    current == section && $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      print
      found=1
    }
    END { if (!found) exit 0 }
  ' "$file" 2>/dev/null | tail -1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

redact_sensitive() {
  sed -E \
    -e 's/(ServiceAuthToken=)[^",[:space:]]+/\1<redacted>/g' \
    -e 's/(ServerCommandsAuthToken=)[^",[:space:]]*/\1<redacted>/g' \
    -e 's/(DatabasePassword=)[^",[:space:]]+/\1<redacted>/g' \
    -e 's/(RMQ_HTTP_TOKEN_AUTH_SECRET=)[^",[:space:]]+/\1<redacted>/g' \
    -e 's/(FLS_SECRET[=])[^",[:space:]]+/\1<redacted>/g' \
    -e 's/(FuncomLiveServices__ServiceAuthToken=)[^",[:space:]]+/\1<redacted>/g' \
    -e 's/(RMQ_HTTP_TOKEN_AUTH_SECRET: )[[:alnum:]_.-]+/\1<redacted>/g' \
    -e 's/(FuncomLiveServices__ServiceAuthToken: )[[:alnum:]_.-]+/\1<redacted>/g'
}

section() {
  printf '\n== %s ==\n' "$1"
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

world_unique_name="$(read_env WORLD_UNIQUE_NAME)"
world_name="$(read_env WORLD_NAME)"
world_region="$(read_env WORLD_REGION)"
world_datacenter_id="$(read_env WORLD_DATACENTER_ID)"
external_address="$(read_env EXTERNAL_ADDRESS)"
game_rmq_public_host="$(read_env GAME_RMQ_PUBLIC_HOST)"
game_rmq_public_host="${game_rmq_public_host:-$external_address}"
game_rmq_public_port="$(read_env GAME_RMQ_PUBLIC_PORT)"
game_rmq_public_port="${game_rmq_public_port:-31982}"
dune_fls_env="$(read_env DUNE_FLS_ENV)"
dune_database="$(read_env DUNE_DATABASE)"
dune_database="${dune_database:-dune_sb_1_4_0_0}"
game_udp_range="$(read_env GAME_UDP_PORT_RANGE)"
game_udp_range="${game_udp_range:-7777:7810}"
igw_udp_range="$(read_env IGW_UDP_PORT_RANGE)"
igw_udp_range="${igw_udp_range:-7888:7917}"

section "env public identity"
printf 'WORLD_UNIQUE_NAME=%s\n' "${world_unique_name:-unset}"
printf 'WORLD_NAME=%s\n' "${world_name:-unset}"
printf 'WORLD_REGION=%s\n' "${world_region:-unset}"
printf 'WORLD_DATACENTER_ID=%s\n' "${world_datacenter_id:-unset}"
printf 'EXTERNAL_ADDRESS=%s\n' "${external_address:-unset}"
printf 'GAME_RMQ_PUBLIC_HOST=%s\n' "${game_rmq_public_host:-unset}"
printf 'GAME_RMQ_PUBLIC_PORT=%s\n' "$game_rmq_public_port"
printf 'DUNE_FLS_ENV=%s\n' "${dune_fls_env:-unset}"
printf 'GAME_UDP_PORT_RANGE=%s\n' "$game_udp_range"
printf 'IGW_UDP_PORT_RANGE=%s\n' "$igw_udp_range"

section "gateway.ini identity"
if [[ -f config/gateway.ini ]]; then
  printf 'OnlineSubsystem.ServerName=%s\n' "$(ini_value config/gateway.ini OnlineSubsystem ServerName || true)"
  printf 'OnlineSubsystem.DatacenterId=%s\n' "$(ini_value config/gateway.ini OnlineSubsystem DatacenterId || true)"
  printf 'gateway.display_name=%s\n' "$(ini_value config/gateway.ini gateway display_name || true)"
else
  printf 'WARN missing config/gateway.ini\n'
fi

section "rendered compose signals"
if have docker; then
  if $compose_cmd --env-file "$env_file" config >/tmp/dune-browser-ping-compose.$$ 2>/tmp/dune-browser-ping-compose.err.$$; then
    rg -n 'RMQGameHostname|RMQGamePort|EXTERNAL_ADDRESS|ExternalAddress|HOST_DATACENTER|OPT_SERVERNAME|OPT_DISPLAY_NAME|BATTLEGROUP|GAME_RMQ|7777|7888|31982' /tmp/dune-browser-ping-compose.$$ || true
  else
    printf 'WARN docker compose config failed:\n'
    sed -n '1,80p' /tmp/dune-browser-ping-compose.err.$$
  fi
  rm -f /tmp/dune-browser-ping-compose.$$ /tmp/dune-browser-ping-compose.err.$$
else
  printf 'WARN docker not found\n'
fi

section "running container reality"
if have docker && have jq; then
  ids=()
  for service in gateway director text-router game-rmq survival; do
    id="$($compose_cmd --env-file "$env_file" ps -q "$service" 2>/dev/null || true)"
    [[ -n "$id" ]] && ids+=("$id")
  done
  if ((${#ids[@]})); then
    docker inspect "${ids[@]}" 2>/dev/null | jq -r '
      .[] |
      "\n## " + .Name,
      ((.Config.Env // [])[]? | select(test("WORLD_|OPT_|BATTLEGROUP|HOST_DATACENTER|FuncomLiveServices|RMQ|GAME_RMQ|EXTERNAL|FLS"))),
      "cmd=" + ((.Config.Cmd // []) | tostring)
    ' | redact_sensitive
  else
    printf 'WARN no target containers found through compose ps\n'
  fi
else
  printf 'WARN docker and jq are required for running-container inspection\n'
fi

section "rabbitmq certificate"
if [[ -x scripts/check-rabbitmq-cert-sans.sh ]]; then
  scripts/check-rabbitmq-cert-sans.sh "$env_file" || true
else
  printf 'WARN scripts/check-rabbitmq-cert-sans.sh not executable\n'
fi

section "local listeners"
if have ss; then
  printf '%s\n' "-- tcp ${game_rmq_public_port} --"
  ss -ltnup 2>/dev/null | rg "(:|\\*)${game_rmq_public_port}\\b" || true
  printf '%s\n' "-- udp game/igw ranges --"
  ss -lunp 2>/dev/null | awk -v game="$game_udp_range" -v igw="$igw_udp_range" '
    BEGIN {
      split(game, g, ":"); split(igw, i, ":")
      gs=g[1]+0; ge=g[2]+0; is=i[1]+0; ie=i[2]+0
    }
    {
      port=$5
      sub(/^.*:/, "", port)
      p=port+0
      if ((p >= gs && p <= ge) || (p >= is && p <= ie)) print
    }'
else
  printf 'WARN ss not found\n'
fi

section "docker nat counters"
if have iptables; then
  iptables -t nat -L DOCKER -n -v 2>/dev/null | rg "dpt:(${game_rmq_public_port}|777[7-9]|778[0-9]|779[0-9]|780[0-9]|7810|788[8-9]|789[0-9]|790[0-9]|791[0-7])" || true
elif have nft; then
  nft list ruleset 2>/dev/null | rg "(${game_rmq_public_port}|7777|7810|7888|7917)" || true
else
  printf 'WARN neither iptables nor nft found\n'
fi

section "db advertised addresses"
if have docker; then
  if $compose_cmd --env-file "$env_file" ps -q postgres >/dev/null 2>&1; then
    $compose_cmd --env-file "$env_file" exec -T postgres psql -U dune -d "$dune_database" -c \
      "select server_id,map,game_addr,game_port,igw_addr,igw_port,ready,alive,connected_players from dune.farm_state order by map,server_id;" \
      2>/dev/null || printf 'WARN farm_state query failed\n'
  else
    printf 'WARN postgres service is not available through compose ps\n'
  fi
else
  printf 'WARN docker not found\n'
fi

section "recent fls-ish logs"
if have docker; then
  $compose_cmd --env-file "$env_file" logs --since=30m gateway director text-router 2>/dev/null \
    | rg -i 'fls|heartbeat|battlegroup|gateway|server browser|population|ping|datacenter|external|rmq|declare|register|update|error|fail|timeout' \
    | redact_sensitive \
    | tail -n 300 \
    || true
else
  printf 'WARN docker not found\n'
fi
