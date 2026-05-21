#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
cert_path="${RABBITMQ_CERT_PATH:-config/tls/rabbitmq/server.crt}"

load_env() {
  [[ -f "$env_file" ]] || return 0

  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *"="* ]] || continue
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

cert_sans() {
  openssl x509 -in "$cert_path" -noout -ext subjectAltName 2>/dev/null \
    | tr ',' '\n' \
    | sed -n -E 's/^[[:space:]]*(DNS|IP Address):([^[:space:]]+).*$/\1:\2/p' \
    | sort -u
}

has_san() {
  local expected="$1"
  printf '%s\n' "$sans" | grep -Fxq "$expected"
}

load_env

if [[ ! -f "$cert_path" ]]; then
  printf 'warn: RabbitMQ certificate is missing: %s\n' "$cert_path" >&2
  exit 1
fi

sans="$(cert_sans)"
printf 'RabbitMQ certificate SANs from %s:\n' "$cert_path"
if [[ -n "$sans" ]]; then
  while IFS= read -r san; do
    printf '  %s\n' "$san"
  done <<<"$sans"
else
  printf '  <none>\n'
fi

required=("DNS:game-rmq" "DNS:localhost" "IP Address:127.0.0.1")
public_host="${GAME_RMQ_PUBLIC_HOST:-${EXTERNAL_ADDRESS:-}}"
if [[ -n "$public_host" ]]; then
  if [[ "$public_host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    required+=("IP Address:$public_host")
  else
    required+=("DNS:$public_host")
  fi
fi

missing=0
for item in "${required[@]}"; do
  if has_san "$item"; then
    printf 'ok: SAN covers %s\n' "$item"
  else
    printf 'warn: SAN missing %s\n' "$item" >&2
    missing=1
  fi
done

exit "$missing"
