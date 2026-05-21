#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/generate-rabbitmq-cert.sh [env-file] [--force]

Generate local game RabbitMQ TLS material under config/tls/rabbitmq.
By default this refuses to overwrite an existing ca.crt, server.crt, or
server.key. Use --force only during planned maintenance after backing up
config/tls/rabbitmq and stopping client-facing services.
EOF
}

env_file=".env"
force=false
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --force)
      force=true
      ;;
    *)
      env_file="$1"
      ;;
  esac
  shift
done

tls_dir="${RABBITMQ_TLS_DIR:-config/tls/rabbitmq}"

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

san_entry_for_host() {
  local host="$1"
  [[ -n "$host" ]] || return 0
  if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf 'IP:%s\n' "$host"
  else
    printf 'DNS:%s\n' "$host"
  fi
}

load_env
mkdir -p "$tls_dir"

existing=()
for path in "$tls_dir/ca.crt" "$tls_dir/server.crt" "$tls_dir/server.key"; do
  [[ -e "$path" ]] && existing+=("$path")
done

if [[ "${#existing[@]}" -gt 0 && "$force" != "true" ]]; then
  printf 'refusing to overwrite existing RabbitMQ TLS files:\n' >&2
  printf '  %s\n' "${existing[@]}" >&2
  printf 'back up %s and rerun with --force during maintenance if replacement is intentional\n' "$tls_dir" >&2
  exit 1
fi

if [[ "$force" == "true" && "${#existing[@]}" -gt 0 ]]; then
  backup_dir="${tls_dir}/backup-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$backup_dir"
  for path in "${existing[@]}"; do
    cp -p "$path" "$backup_dir/"
  done
  printf 'backed up existing RabbitMQ TLS files to %s\n' "$backup_dir"
fi

public_host="${GAME_RMQ_PUBLIC_HOST:-${EXTERNAL_ADDRESS:-}}"
mapfile -t san_entries < <(
  {
    printf 'DNS:game-rmq\n'
    printf 'DNS:localhost\n'
    printf 'IP:127.0.0.1\n'
    san_entry_for_host "$public_host"
  } | awk 'NF && !seen[$0]++'
)

openssl genrsa -out "$tls_dir/ca.key" 4096
openssl req -x509 -new -nodes -key "$tls_dir/ca.key" -sha256 -days 3650 \
  -subj "/CN=dune-rabbitmq-ca" \
  -out "$tls_dir/ca.crt"

openssl genrsa -out "$tls_dir/server.key" 2048
openssl req -new -key "$tls_dir/server.key" \
  -subj "/CN=game-rmq" \
  -out "$tls_dir/server.csr"

{
  printf 'subjectAltName = %s\n' "$(IFS=,; printf '%s' "${san_entries[*]}")"
  printf 'extendedKeyUsage = serverAuth\n'
} >"$tls_dir/server.ext"

openssl x509 -req -in "$tls_dir/server.csr" \
  -CA "$tls_dir/ca.crt" -CAkey "$tls_dir/ca.key" -CAcreateserial \
  -out "$tls_dir/server.crt" -days 3650 -sha256 \
  -extfile "$tls_dir/server.ext"

chmod 644 "$tls_dir/server.key"
chmod 600 "$tls_dir/ca.key"

printf 'generated RabbitMQ TLS files in %s\n' "$tls_dir"
printf 'SANs:\n'
printf '  %s\n' "${san_entries[@]}"
