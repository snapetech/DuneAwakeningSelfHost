#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
stage_dir="${RABBITMQ_STAGED_TLS_DIR:-config/tls/rabbitmq-staged}"

if [[ ! -x ./scripts/generate-rabbitmq-cert.sh || ! -x ./scripts/check-rabbitmq-cert-sans.sh ]]; then
  printf 'required RabbitMQ TLS helper scripts are missing or not executable\n' >&2
  exit 1
fi

if [[ "$stage_dir" == "config/tls/rabbitmq" ]]; then
  printf 'refusing to stage over live RabbitMQ TLS directory: %s\n' "$stage_dir" >&2
  exit 1
fi

if [[ -e "$stage_dir" ]]; then
  backup_dir="${stage_dir}.backup.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$stage_dir" "$backup_dir"
  printf 'moved existing staged RabbitMQ TLS material to %s\n' "$backup_dir"
fi

RABBITMQ_TLS_DIR="$stage_dir" ./scripts/generate-rabbitmq-cert.sh "$env_file"
RABBITMQ_CERT_PATH="$stage_dir/server.crt" ./scripts/check-rabbitmq-cert-sans.sh "$env_file"

printf 'staged RabbitMQ TLS material in %s\n' "$stage_dir"
printf 'install during maintenance with CONFIRM_INSTALL_STAGED_RMQ_CERT=yes make rabbitmq-cert-install-staged ENV_FILE=%s\n' "$env_file"
