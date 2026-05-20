#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
failures=0

ok() {
  printf 'ok: %s\n' "$*"
}

fail() {
  printf 'fail: %s\n' "$*" >&2
  failures=$((failures + 1))
}

load_env() {
  [[ -f "$env_file" ]] || return 0
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# || "$line" != *"="* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      printf -v "$key" '%s' "$value"
    fi
  done <"$env_file"
}

http_code() {
  local url="$1"
  local host_header="${2:-}"
  if [[ -n "$host_header" ]]; then
    curl -kfsS -o /dev/null -w '%{http_code}' --max-time 8 -H "Host: ${host_header}" "$url" 2>/dev/null || true
  else
    curl -kfsS -o /dev/null -w '%{http_code}' --max-time 8 "$url" 2>/dev/null || true
  fi
}

host_from_url() {
  local url="$1"
  url="${url#http://}"
  url="${url#https://}"
  printf '%s\n' "${url%%/*}"
}

load_env

admin_port="${DUNE_ADMIN_HOST_PORT:-18080}"
direct_host="127.0.0.1:${admin_port}"
direct_url="http://127.0.0.1:${admin_port}/api/status"
direct_code="$(http_code "$direct_url" "$direct_host")"
if [[ "$direct_code" == "200" ]]; then
  ok "admin panel direct endpoint responds on ${direct_host}"
else
  fail "admin panel direct endpoint returned ${direct_code:-no response} on ${direct_host}"
fi

lan_url="${DUNE_ADMIN_LAN_URL:-}"
if [[ -z "$lan_url" && -n "${DUNE_ADMIN_LAN_HOST:-}" ]]; then
  lan_url="http://${DUNE_ADMIN_LAN_HOST}/api/status"
fi

if [[ -n "$lan_url" ]]; then
  lan_host="$(host_from_url "$lan_url")"
  allowed=",${DUNE_ADMIN_ALLOWED_HOSTS:-},"
  if [[ "$allowed" != *",${lan_host},"* ]]; then
    fail "DUNE_ADMIN_ALLOWED_HOSTS does not include LAN host ${lan_host}"
  else
    ok "LAN host ${lan_host} is allowed by admin panel"
  fi
  lan_code="$(http_code "$lan_url")"
  if [[ "$lan_code" == "200" ]]; then
    ok "LAN ingress responds at ${lan_url}"
  else
    fail "LAN ingress returned ${lan_code:-no response} at ${lan_url}; check DNS and reverse proxy route to 127.0.0.1:${admin_port}"
  fi
else
  ok "DUNE_ADMIN_LAN_URL/DUNE_ADMIN_LAN_HOST not set; skipped LAN ingress probe"
fi

if [[ "$failures" -gt 0 ]]; then
  printf '\nadmin ingress check failed with %s issue(s)\n' "$failures" >&2
  exit 1
fi

printf '\nadmin ingress check passed\n'
