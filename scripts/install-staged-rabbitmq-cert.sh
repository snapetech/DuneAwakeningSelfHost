#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/install-staged-rabbitmq-cert.sh [env-file] [remote-host]

Install RabbitMQ TLS material previously generated in config/tls/rabbitmq-staged
into config/tls/rabbitmq. This is confirmation-gated because it changes live
client-facing RabbitMQ identity. Run it only during maintenance.
EOF
}

env_file="${1:-.env}"
remote="${2:-}"
stage_dir="${RABBITMQ_STAGED_TLS_DIR:-config/tls/rabbitmq-staged}"
live_dir="${RABBITMQ_TLS_DIR:-config/tls/rabbitmq}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

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

load_env

remote="${remote:-${POSTGRES_REMOTE_REPLICA_HOST:-}}"
remote_root="${DUNE_STANDBY_REPO_ROOT:-}"
confirm="${CONFIRM_INSTALL_STAGED_RMQ_CERT:-no}"
restart_after="${DUNE_RESTART_RMQ_AFTER_TLS_INSTALL:-false}"

for file in ca.crt ca.key server.crt server.key; do
  if [[ ! -f "$stage_dir/$file" ]]; then
    printf 'staged RabbitMQ TLS file is missing: %s\n' "$stage_dir/$file" >&2
    exit 1
  fi
done

if [[ -x ./scripts/check-rabbitmq-cert-sans.sh ]]; then
  RABBITMQ_CERT_PATH="$stage_dir/server.crt" ./scripts/check-rabbitmq-cert-sans.sh "$env_file"
fi

if [[ "$confirm" != "yes" ]]; then
  printf 'dry-run: would back up %s and install staged RabbitMQ TLS from %s\n' "$live_dir" "$stage_dir"
  if [[ -n "$remote" && -n "$remote_root" ]]; then
    printf 'dry-run: would rsync installed TLS material to %s:%s/%s\n' "$remote" "$remote_root" "$live_dir"
  fi
  printf 'set CONFIRM_INSTALL_STAGED_RMQ_CERT=yes to apply during maintenance\n'
  exit 0
fi

mkdir -p "$(dirname "$live_dir")"
if [[ -e "$live_dir" ]]; then
  backup_dir="${live_dir}.backup.$(date -u +%Y%m%dT%H%M%SZ)"
  cp -a "$live_dir" "$backup_dir"
  printf 'backed up live RabbitMQ TLS material to %s\n' "$backup_dir"
fi

mkdir -p "$live_dir"
install -m 0644 "$stage_dir/ca.crt" "$live_dir/ca.crt"
install -m 0600 "$stage_dir/ca.key" "$live_dir/ca.key"
install -m 0644 "$stage_dir/server.crt" "$live_dir/server.crt"
install -m 0644 "$stage_dir/server.key" "$live_dir/server.key"
printf 'installed staged RabbitMQ TLS material into %s\n' "$live_dir"

if [[ -n "$remote" && -n "$remote_root" ]]; then
  ssh "$remote" "mkdir -p '$remote_root/$live_dir'"
  rsync -a --delete "$live_dir/" "$remote:$remote_root/$live_dir/"
  printf 'mirrored RabbitMQ TLS material to %s:%s/%s\n' "$remote" "$remote_root" "$live_dir"
fi

if [[ "$restart_after" == "true" ]]; then
  docker compose --env-file "$env_file" restart game-rmq gateway director text-router
  printf 'restarted client-facing RabbitMQ and control-plane containers\n'
else
  printf 'restart skipped. Recreate game-rmq, gateway, director, text-router, and map containers during maintenance.\n'
fi
