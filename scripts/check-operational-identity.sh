#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/check-operational-identity.sh [env-file]

Read-only identity/config check for operational handoff. It does not require
Steam image tarballs or running containers.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
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

if [[ ! -f "$env_file" ]]; then
  fail "env file missing: $env_file"
else
  ok "env file exists: $env_file"
fi

world_unique_name="$(get_env WORLD_UNIQUE_NAME)"
fls_env="$(get_env DUNE_FLS_ENV)"
game_rmq_public_host="$(get_env GAME_RMQ_PUBLIC_HOST)"

case "$world_unique_name" in
  ""|sh-example-dune|example|changeme|change-me)
    fail "WORLD_UNIQUE_NAME is missing or still an example placeholder"
    ;;
  sh-example-*)
    warn "WORLD_UNIQUE_NAME uses generated sh-example-* prefix; keep only if this is the registered durable identity"
    ;;
  *)
    ok "WORLD_UNIQUE_NAME set: $world_unique_name"
    ;;
esac

case "${fls_env:-retail}" in
  retail)
    ok "DUNE_FLS_ENV=retail"
    ;;
  beta|test|ptc|staging)
    warn "DUNE_FLS_ENV=${fls_env}; confirm matching PTC/test build and token authorization"
    ;;
  *)
    warn "DUNE_FLS_ENV=${fls_env:-unset} is not a known DASH value"
    ;;
esac

if [[ -n "$game_rmq_public_host" ]]; then
  ok "GAME_RMQ_PUBLIC_HOST set: $game_rmq_public_host"
else
  warn "GAME_RMQ_PUBLIC_HOST missing; Gateway falls back to EXTERNAL_ADDRESS"
fi

if command -v docker >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
  rendered="$(mktemp)"
  if docker compose --env-file "$env_file" config --format json >"$rendered"; then
    command_fls_env="$(jq -r '.services.survival.command[] | select(test("DefaultFlsEnvironment="))' "$rendered" | tail -n 1)"
    director_fls_env="$(jq -r '.services.director.environment.FuncomLiveServices__DefaultFlsEnvironment // ""' "$rendered")"
    if [[ "$command_fls_env" == *"DefaultFlsEnvironment=${fls_env:-retail}" ]]; then
      ok "survival command renders ${fls_env:-retail} FLS environment"
    else
      fail "survival command FLS environment render mismatch: ${command_fls_env:-missing}"
    fi
    if [[ "$director_fls_env" == "${fls_env:-retail}" ]]; then
      ok "service layer renders ${fls_env:-retail} FLS environment"
    else
      fail "service layer FLS environment render mismatch: ${director_fls_env:-missing}"
    fi
  else
    fail "Compose config render failed"
  fi
  rm -f "$rendered"
else
  warn "docker or jq missing; skipping rendered Compose identity check"
fi

if [[ -x ./scripts/check-rabbitmq-cert-sans.sh ]]; then
  if ./scripts/check-rabbitmq-cert-sans.sh "$env_file" >/dev/null; then
    ok "RabbitMQ cert SAN check passed"
  else
    warn "RabbitMQ cert SAN check reported warnings"
  fi
fi

if ./scripts/backup-state.sh --dry-run "$env_file" >/dev/null; then
  ok "backup identity dry-run passed"
else
  fail "backup identity dry-run failed"
fi

printf '\nSummary: %s failure(s), %s warning(s)\n' "$failures" "$warnings"
if [[ "$failures" -gt 0 ]]; then
  exit 1
fi
