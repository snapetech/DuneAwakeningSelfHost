#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/operational-bundle.sh [env-file] [output-tgz]

Creates a redacted operational handoff bundle under backups/. The bundle does
not include .env, TLS keys, RabbitMQ data, Postgres dumps, or raw rendered
Compose output.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
output_tgz="${2:-backups/operational-bundle-$(date -u +%Y%m%dT%H%M%SZ).tgz}"

case "$output_tgz" in
  backups/*) ;;
  *)
    printf 'refusing to write operational bundle outside backups/: %s\n' "$output_tgz" >&2
    exit 1
    ;;
esac

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

bundle_root="$(mktemp -d)"
trap 'rm -rf "$bundle_root"' EXIT
mkdir -p "$(dirname "$output_tgz")"

report="$bundle_root/operational-report.txt"
identity="$bundle_root/operational-identity-check.txt"
backup_dry_run="$bundle_root/backup-dry-run.txt"
compose_summary="$bundle_root/compose-summary.txt"
manifest="$bundle_root/manifest.txt"

./scripts/operational-report.sh "$env_file" "$report" >/dev/null
./scripts/check-operational-identity.sh "$env_file" >"$identity" 2>&1 || true
./scripts/backup-state.sh --dry-run "$env_file" >"$backup_dry_run" 2>&1

if docker compose --env-file "$env_file" config --format json >/tmp/dash-compose-summary.$$.json 2>/dev/null; then
  if command -v jq >/dev/null 2>&1; then
    jq -r '
      .services
      | to_entries[]
      | [
          .key,
          (.value.image // ""),
          ((.value.command // []) | if type == "array" then join(" ") else tostring end | gsub("ServiceAuthToken=[^ ]+"; "ServiceAuthToken=<redacted>") | gsub("DatabasePassword=[^ ]+"; "DatabasePassword=<redacted>")),
          (.value.environment.WORLD_NAME // ""),
          (.value.environment.BATTLEGROUP_DISPLAY_NAME // ""),
          (.value.environment.FuncomLiveServices__DefaultFlsEnvironment // "")
        ]
      | @tsv
    ' /tmp/dash-compose-summary.$$.json >"$compose_summary"
  else
    printf 'jq missing; compose summary unavailable\n' >"$compose_summary"
  fi
  rm -f /tmp/dash-compose-summary.$$.json
else
  printf 'docker compose render failed; compose summary unavailable\n' >"$compose_summary"
fi

cat >"$manifest" <<EOF
created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
env_file=$env_file
contains_env=false
contains_tls_keys=false
contains_database_dump=false
contains_rabbitmq_state=false
contains_raw_compose=false
files=operational-report.txt,operational-identity-check.txt,backup-dry-run.txt,compose-summary.txt,manifest.txt
EOF

tar -czf "$output_tgz" -C "$bundle_root" .
printf 'wrote operational bundle: %s\n' "$output_tgz"
