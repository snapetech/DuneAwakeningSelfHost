#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

section() {
  printf '\n== %s ==\n' "$1"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

redact_sensitive() {
  sed -E \
    -e 's/(Token ")[^"]+/\1<redacted>/g' \
    -e 's/(Server Token successfully\. Cache key:"[^"]+", Token ")[^"]+/\1<redacted>/g' \
    -e 's/(GameRmqSecret["=: ][ ":]*)[^",[:space:]}]+/\1<redacted>/g' \
    -e 's/(RMQ_HTTP_TOKEN_AUTH_SECRET=)[^",[:space:]]+/\1<redacted>/g' \
    -e 's/(FuncomLiveServices__ServiceAuthToken=)[^",[:space:]]+/\1<redacted>/g'
}

tcp_check() {
  local host="$1" port="$2" label="$3"
  if [[ -z "$host" || -z "$port" ]]; then
    printf 'WARN %s endpoint is incomplete: host=%s port=%s\n' "$label" "${host:-unset}" "${port:-unset}"
    return 0
  fi
  if have nc; then
    if nc -vz -w "${DUNE_CLIENT_BROWSER_PING_TCP_TIMEOUT:-5}" "$host" "$port" >/tmp/dune-client-browser-ping-nc.$$ 2>&1; then
      printf 'OK %s %s:%s reachable\n' "$label" "$host" "$port"
    else
      printf 'FAIL %s %s:%s unreachable: %s\n' "$label" "$host" "$port" "$(tail -1 /tmp/dune-client-browser-ping-nc.$$)"
    fi
    rm -f /tmp/dune-client-browser-ping-nc.$$
  else
    if timeout "${DUNE_CLIENT_BROWSER_PING_TCP_TIMEOUT:-5}" bash -c ":</dev/tcp/$host/$port" 2>/dev/null; then
      printf 'OK %s %s:%s reachable\n' "$label" "$host" "$port"
    else
      printf 'FAIL %s %s:%s unreachable\n' "$label" "$host" "$port"
    fi
  fi
}

icmp_check() {
  local host="$1" label="$2"
  if [[ -z "$host" ]]; then
    printf 'WARN %s ICMP target is unset\n' "$label"
    return 0
  fi
  if have ping; then
    if ping -c "${DUNE_CLIENT_BROWSER_PING_ICMP_COUNT:-3}" -W "${DUNE_CLIENT_BROWSER_PING_ICMP_TIMEOUT:-2}" "$host" >/tmp/dune-client-browser-ping-icmp.$$ 2>&1; then
      awk -v label="$label" -v host="$host" '
        /packets transmitted/ { summary=$0 }
        /^rtt / { rtt=$0 }
        END {
          printf "OK %s ICMP %s reachable", label, host
          if (rtt != "") printf " (%s)", rtt
          printf "\n"
        }' /tmp/dune-client-browser-ping-icmp.$$
    else
      printf 'FAIL %s ICMP %s unreachable: %s\n' "$label" "$host" "$(tail -1 /tmp/dune-client-browser-ping-icmp.$$)"
    fi
    rm -f /tmp/dune-client-browser-ping-icmp.$$
  else
    printf 'WARN ping command not found; ICMP browser-ping path not checked\n'
  fi
}

external_icmp_check() {
  local host="$1"
  if [[ -z "$host" ]]; then
    printf 'WARN external WAN ICMP target is unset\n'
    return 0
  fi
  if [[ "${DUNE_CLIENT_BROWSER_PING_EXTERNAL_ICMP:-false}" != "true" ]]; then
    printf 'SKIP external WAN ICMP check; set DUNE_CLIENT_BROWSER_PING_EXTERNAL_ICMP=true to use Globalping probes\n'
    return 0
  fi
  if ! have curl; then
    printf 'WARN curl not found; external WAN ICMP check skipped\n'
    return 0
  fi
  if ! have jq; then
    printf 'WARN jq not found; external WAN ICMP check skipped\n'
    return 0
  fi

  local limit country response id result
  limit="${DUNE_CLIENT_BROWSER_PING_EXTERNAL_LIMIT:-3}"
  country="${DUNE_CLIENT_BROWSER_PING_EXTERNAL_COUNTRY:-US}"
  response="$(curl -sS -X POST https://api.globalping.io/v1/measurements \
    -H 'content-type: application/json' \
    -d "{\"type\":\"ping\",\"target\":\"${host}\",\"limit\":${limit},\"locations\":[{\"country\":\"${country}\"}]}" 2>/tmp/dune-client-browser-ping-globalping.err.$$ || true)"
  if [[ -z "$response" ]] || ! id="$(printf '%s' "$response" | jq -r '.id // empty' 2>/dev/null)" || [[ -z "$id" ]]; then
    printf 'WARN external WAN ICMP measurement could not be started: %s\n' "$(cat /tmp/dune-client-browser-ping-globalping.err.$$ 2>/dev/null || printf '%s' "$response")"
    rm -f /tmp/dune-client-browser-ping-globalping.err.$$
    return 0
  fi
  rm -f /tmp/dune-client-browser-ping-globalping.err.$$

  local attempt status
  result=""
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    result="$(curl -sS "https://api.globalping.io/v1/measurements/${id}" 2>/dev/null || true)"
    status="$(printf '%s' "$result" | jq -r '.status // empty' 2>/dev/null || true)"
    [[ "$status" == "finished" ]] && break
    sleep 1
  done
  if [[ "$status" != "finished" ]]; then
    printf 'WARN external WAN ICMP measurement %s did not finish; status=%s\n' "$id" "${status:-unknown}"
    return 0
  fi

  printf '%s\n' "$result" | jq -r --arg host "$host" '
    [ .results[]
      | {
          city: (.probe.city // "unknown"),
          state: (.probe.state // ""),
          country: (.probe.country // ""),
          avg: (.result.stats.avg // null),
          loss: (.result.stats.loss // null),
          rcv: (.result.stats.rcv // null),
          total: (.result.stats.total // null)
        }
    ] as $rows
    | ($rows | map(select(.loss == 0 and .rcv == .total and .total > 0)) | length) as $ok
    | if $ok == ($rows | length) and $ok > 0 then
        "OK external WAN ICMP " + $host + " reachable from " + ($ok|tostring) + " Globalping probes: " +
        ($rows | map(.city + (if .state != "" then ", " + .state else "" end) + " avg=" + (.avg|tostring) + "ms loss=" + (.loss|tostring) + "%") | join("; "))
      elif ($rows | length) > 0 then
        "WARN external WAN ICMP " + $host + " had probe loss/failure: " +
        ($rows | map(.city + (if .state != "" then ", " + .state else "" end) + " rcv=" + (.rcv|tostring) + "/" + (.total|tostring) + " loss=" + (.loss|tostring) + "%") | join("; "))
      else
        "WARN external WAN ICMP " + $host + " returned no probe results"
      end'
}

find_client_log() {
  if [[ -n "${DUNE_CLIENT_LOG:-}" ]]; then
    printf '%s' "$DUNE_CLIENT_LOG"
    return 0
  fi
  local steam_root="${STEAM_ROOT:-$HOME/.steam/steam}"
  local candidate="$steam_root/steamapps/compatdata/1172710/pfx/drive_c/users/steamuser/AppData/Local/DuneSandbox/Saved/Logs/DuneSandbox.log"
  if [[ -f "$candidate" ]]; then
    printf '%s' "$candidate"
    return 0
  fi
  find "$steam_root/steamapps/compatdata/1172710" -path '*/DuneSandbox/Saved/Logs/DuneSandbox.log' -type f -print 2>/dev/null | head -1
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

external_address="$(read_env EXTERNAL_ADDRESS)"
lan_address="$(read_env DUNE_CURRENT_LAN_IP)"
world_unique_name="$(read_env WORLD_UNIQUE_NAME)"
world_name="$(read_env WORLD_NAME)"
world_name="${world_name:-$(read_env OPT_DISPLAY_NAME)}"
game_rmq_public_host="$(read_env GAME_RMQ_PUBLIC_HOST)"
game_rmq_public_host="${game_rmq_public_host:-$external_address}"
game_rmq_public_port="$(read_env GAME_RMQ_PUBLIC_PORT)"
game_rmq_public_port="${game_rmq_public_port:-31982}"
game_rmq_public_http_port="$(read_env GAME_RMQ_PUBLIC_HTTP_PORT)"
game_rmq_public_http_port="${game_rmq_public_http_port:-15673}"
fix_epoch="${DUNE_CLIENT_BROWSER_PING_FIX_EPOCH:-}"
fix_label="${DUNE_CLIENT_BROWSER_PING_FIX_LABEL:-current endpoint fix}"

section "advertised endpoints"
printf 'EXTERNAL_ADDRESS=%s\n' "${external_address:-unset}"
printf 'DUNE_CURRENT_LAN_IP=%s\n' "${lan_address:-unset}"
printf 'WORLD_UNIQUE_NAME=%s\n' "${world_unique_name:-unset}"
printf 'WORLD_NAME=%s\n' "${world_name:-unset}"
printf 'GAME_RMQ_PUBLIC_HOST=%s\n' "${game_rmq_public_host:-unset}"
printf 'GAME_RMQ_PUBLIC_PORT=%s\n' "$game_rmq_public_port"
printf 'GAME_RMQ_PUBLIC_HTTP_PORT=%s\n' "$game_rmq_public_http_port"

section "client-host reachability"
icmp_check "$game_rmq_public_host" "public host"
tcp_check "$game_rmq_public_host" "$game_rmq_public_port" "public AMQP/TLS"
tcp_check "$game_rmq_public_host" "$game_rmq_public_http_port" "public HTTP"
if [[ -n "$lan_address" && "$lan_address" != "$game_rmq_public_host" ]]; then
  icmp_check "$lan_address" "LAN host"
  tcp_check "$lan_address" "$game_rmq_public_port" "LAN AMQP/TLS"
  tcp_check "$lan_address" "$game_rmq_public_http_port" "LAN HTTP"
fi

section "external WAN reachability"
external_icmp_check "$game_rmq_public_host"

section "client log"
client_log="$(find_client_log || true)"
if [[ -z "$client_log" || ! -f "$client_log" ]]; then
  printf 'WARN Dune client log not found. Set DUNE_CLIENT_LOG=/path/to/DuneSandbox.log to inspect it.\n'
  exit 0
fi
printf 'log=%s\n' "$client_log"
log_epoch="$(stat -c %Y "$client_log")"
printf 'log_mtime=%s\n' "$(date -d "@$log_epoch" '+%Y-%m-%d %H:%M:%S %z')"
if [[ -n "$fix_epoch" ]]; then
  printf '%s=%s\n' "$fix_label" "$(date -d "@$fix_epoch" '+%Y-%m-%d %H:%M:%S %z')"
  if (( log_epoch < fix_epoch )); then
    printf 'WARN client log predates %s; it cannot prove the current in-game ping state.\n' "$fix_label"
  else
    printf 'OK client log is newer than %s.\n' "$fix_label"
  fi
fi

section "recent browser/rmq symptoms"
printf '%s\n' "-- server-browser/FLS calls --"
rg -n -i 'Getting info for the battlegroups|ServerBrowser|server browser|ping|latenc' "$client_log" \
  | tail -n "${DUNE_CLIENT_BROWSER_PING_LOG_LINES:-40}" | redact_sensitive || true
printf '%s\n' "-- RMQ connection setup/errors --"
rg -n -i 'Getting GAME RMQ connection info|GameRmq|ConnectTls|timeout|failed to create connection|RMQ runnable failed|Browse:|ConnectionFailure' "$client_log" \
  | tail -n "${DUNE_CLIENT_BROWSER_PING_LOG_LINES:-40}" | redact_sensitive || true
printf '%s\n' "-- repeated AMQP SSL consumer error count --"
rg -c -i 'AMQP Consumer error: a SSL error occurred' "$client_log" || true

section "target battlegroup in client log"
if [[ -n "$world_unique_name" ]]; then
  rg -n -i "$world_unique_name" "$client_log" | tail -n 30 | redact_sensitive || printf 'WARN no client-log hits for WORLD_UNIQUE_NAME=%s\n' "$world_unique_name"
fi
if [[ -n "$world_name" ]]; then
  rg -n -F "$world_name" "$client_log" | tail -n 20 | redact_sensitive || printf 'WARN no client-log hits for WORLD_NAME=%s\n' "$world_name"
fi
if [[ -n "$external_address" ]]; then
  rg -n -F "$external_address" "$client_log" | tail -n 40 | redact_sensitive || true
fi

section "verdict"
if [[ -n "$fix_epoch" && "$log_epoch" -lt "$fix_epoch" ]]; then
  printf 'INCOMPLETE: endpoints can be checked from this host, but the Dune client has not produced a post-fix log yet. In-game ping remains unproven.\n'
else
  recent_rmq="$(rg -n -i 'Received login grant|ConnectTls: Failed to open TLS socket|Failed to create connection|RMQ runnable failed to create connection' "$client_log" | tail -n 1 | redact_sensitive || true)"
  if [[ "$recent_rmq" == *"Received login grant"* ]]; then
    printf 'OK latest target RMQ/login evidence is a received login grant: %s\n' "$recent_rmq"
  elif [[ -n "$recent_rmq" ]]; then
    printf 'WARN latest target RMQ/login evidence is a failure or ambiguous line: %s\n' "$recent_rmq"
  else
    printf 'WARN no target RMQ/login evidence found in client log.\n'
  fi
  printf 'Evidence is sufficient only if the latest server-browser attempt is after the fix and no current RMQ/browser timeout appears.\n'
fi
