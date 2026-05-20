#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap-checklist.sh [env-file]

Read-only checklist for a new DASH host. It reports missing tools, missing env
values, missing Steam package paths, and likely unsafe defaults. It does not
start, stop, or modify services.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

failures=0
warnings=0

ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL %s\n' "$*"; failures=$((failures + 1)); }

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

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "command available: $1"
  else
    fail "command missing: $1"
  fi
}

printf 'DASH bootstrap checklist\n'
printf 'repo: %s\n' "$repo_root"
printf 'env:  %s\n\n' "$env_file"

if [[ -f "$env_file" ]]; then
  ok "env file exists"
else
  fail "env file missing; run ./scripts/populate-local-env.sh"
fi

for command in docker jq rg openssl; do
  check_command "$command"
done

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    ok "docker compose plugin available"
  else
    fail "docker compose plugin missing"
  fi
fi

if [[ -f "$env_file" ]]; then
  steam_dir="$(get_env DUNE_STEAM_SERVER_DIR)"
  image_tag="$(get_env DUNE_IMAGE_TAG)"
  fls_secret="$(get_env FLS_SECRET)"
  external_address="$(get_env EXTERNAL_ADDRESS)"
  game_rmq_host="$(get_env GAME_RMQ_PUBLIC_HOST)"
  admin_token="$(get_env DUNE_ADMIN_TOKEN)"

  [[ -n "$steam_dir" && "$steam_dir" != "/path/to/Steam/steamapps/common/Dune Awakening Self-Hosted Server" ]] && ok "DUNE_STEAM_SERVER_DIR set" || fail "DUNE_STEAM_SERVER_DIR still placeholder"
  [[ -n "$image_tag" ]] && ok "DUNE_IMAGE_TAG set: $image_tag" || fail "DUNE_IMAGE_TAG missing"
  [[ -n "$fls_secret" ]] && ok "FLS_SECRET set" || fail "FLS_SECRET missing"
  [[ -n "$external_address" && "$external_address" != "127.0.0.1" ]] && ok "EXTERNAL_ADDRESS set to non-localhost" || warn "EXTERNAL_ADDRESS is empty or localhost"
  [[ -n "$game_rmq_host" && "$game_rmq_host" != "127.0.0.1" ]] && ok "GAME_RMQ_PUBLIC_HOST set to non-localhost" || warn "GAME_RMQ_PUBLIC_HOST is empty or localhost"
  [[ -n "$admin_token" && "$admin_token" != "change-me-admin-token" ]] && ok "DUNE_ADMIN_TOKEN changed from placeholder" || fail "DUNE_ADMIN_TOKEN missing or placeholder"

  if [[ -n "$steam_dir" && -d "$steam_dir" ]]; then
    ok "Steam server directory exists"
  else
    warn "Steam server directory not found locally: ${steam_dir:-unset}"
  fi
fi

if [[ -d examples ]]; then
  ok "examples directory present"
else
  warn "examples directory missing"
fi

if [[ -x scripts/backup-offsite.sh && -x scripts/verify-backup.sh ]]; then
  ok "backup helper scripts executable"
else
  fail "backup helper scripts missing or not executable"
fi

printf '\nSummary: %s failure(s), %s warning(s)\n' "$failures" "$warnings"
if [[ "$failures" -gt 0 ]]; then
  exit 1
fi
