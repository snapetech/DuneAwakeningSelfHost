#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/operational-report.sh [env-file] [output-file]

Writes a redacted operational identity report. The report is intended for
handoff/review and avoids secret values.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
output_file="${2:-backups/operational-report-$(date -u +%Y%m%dT%H%M%SZ).txt}"

get_env() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

redacted_presence() {
  local key="$1"
  local value
  value="$(get_env "$key")"
  if [[ -n "$value" ]]; then
    printf '%s=<set length=%s>\n' "$key" "${#value}"
  else
    printf '%s=<empty>\n' "$key"
  fi
}

mkdir -p "$(dirname "$output_file")"

{
  printf '# DASH Operational Report\n'
  printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'env_file=%s\n' "$env_file"
  printf '\n## Identity\n'
  printf 'WORLD_NAME=%s\n' "$(get_env WORLD_NAME)"
  printf 'WORLD_UNIQUE_NAME=%s\n' "$(get_env WORLD_UNIQUE_NAME)"
  printf 'WORLD_REGION=%s\n' "$(get_env WORLD_REGION)"
  printf 'DUNE_FLS_ENV=%s\n' "$(get_env DUNE_FLS_ENV)"
  printf 'DUNE_IMAGE_TAG=%s\n' "$(get_env DUNE_IMAGE_TAG)"
  printf 'GAME_RMQ_PUBLIC_HOST=%s\n' "$(get_env GAME_RMQ_PUBLIC_HOST)"
  printf 'GAME_RMQ_PUBLIC_PORT=%s\n' "$(get_env GAME_RMQ_PUBLIC_PORT)"
  printf 'EXTERNAL_ADDRESS=%s\n' "$(get_env EXTERNAL_ADDRESS)"
  redacted_presence FLS_SECRET
  redacted_presence DUNE_ADMIN_TOKEN
  redacted_presence RMQ_HTTP_TOKEN_AUTH_SECRET

  printf '\n## Operational Identity Check\n'
  if ./scripts/check-operational-identity.sh "$env_file"; then
    printf 'operational_identity_check=OK\n'
  else
    printf 'operational_identity_check=FAILED\n'
  fi

  printf '\n## RabbitMQ TLS SANs\n'
  if ./scripts/check-rabbitmq-cert-sans.sh "$env_file"; then
    printf 'rabbitmq_cert_sans=OK\n'
  else
    printf 'rabbitmq_cert_sans=WARN\n'
  fi

  printf '\n## Backup Dry Run\n'
  ./scripts/backup-state.sh --dry-run "$env_file"

  printf '\n## Compose Render\n'
  if docker compose --env-file "$env_file" config --quiet; then
    printf 'compose_config=OK\n'
  else
    printf 'compose_config=FAILED\n'
  fi
} >"$output_file"

printf 'wrote operational report: %s\n' "$output_file"
