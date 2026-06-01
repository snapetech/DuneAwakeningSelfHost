#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/apply-post-dd-cycle-coriolis-config.sh [ENV_FILE] [--restart]

Replaces the staged PvE Deep Desert one-shot Coriolis config with the normal
Standard PvE no-Coriolis config from config/UserGame.ini. The replacement keeps
auto-spawn off, no damage, no DB wipe, no restart, no Deep Desert Shifting
Sands, and a far-future cycle.

The partition-31 Hardcore Deep Desert config is intentionally left alone because
it owns high Coriolis damage, Shifting Sands, and the separate 3x harvest Engine
config.

Run this after a staged Standard PvE Deep Desert refresh has completed.
USAGE
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file=".env"
restart=false

while (($#)); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --restart)
      restart=true
      ;;
    *)
      env_file="$1"
      ;;
  esac
  shift
done

cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 1
fi

source_file="config/UserGame.ini"
targets=(
  "config/UserGame.deep-desert-coriolis.ini"
)

if [[ ! -f "$source_file" ]]; then
  printf 'missing source config: %s\n' "$source_file" >&2
  exit 1
fi

required_patterns=(
  'm_ShiftingSands=False'
  'm_bCoriolisAutoSpawnEnabled=False'
  'm_bCoriolisDoesDamage=False'
  'm_bCoriolisTriggerShiftingSands=False'
  'm_CoriolisLightDamage=0.000000'
  'm_CoriolisHeavyDamage=0.000000'
  'm_CycleDurationInDays=36524'
  'm_bShouldRestartServerOnCycleEnd=False'
  'm_bIsDbWipeEnabled=False'
)

for pattern in "${required_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$source_file"; then
    printf 'source config %s is missing required post-cycle setting: %s\n' "$source_file" "$pattern" >&2
    exit 1
  fi
done

backup_dir="backups/manual/post-dd-cycle-coriolis-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"

for target in "${targets[@]}"; do
  if [[ ! -f "$target" ]]; then
    printf 'skipping missing target config: %s\n' "$target"
    continue
  fi
  cp -p "$target" "$backup_dir/$(basename "$target")"
  cp -p "$source_file" "$target"
  printf 'applied post-cycle Coriolis config: %s -> %s\n' "$source_file" "$target"
done

printf 'backup written: %s\n' "$backup_dir"

if [[ "$restart" != true ]]; then
  printf 'restart not requested; restart deep-desert during downtime for this to take effect.\n'
  exit 0
fi

compose_files="$("$script_dir/compose-files.sh" "$env_file")"
compose=(docker compose --env-file "$env_file")
IFS=':' read -ra files <<< "$compose_files"
for file in "${files[@]}"; do
  compose+=(-f "$file")
done

"${compose[@]}" up -d --force-recreate --no-deps deep-desert
