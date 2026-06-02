#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/validate-landsraad-coriolis-cycle.sh [ENV_FILE]

Validates that the Standard PvE Coriolis configs keep a weekly cycle.
Landsraad uses the Coriolis cycle to decide its active/suspended window, so
parking the cycle far in the future suspends Landsraad globally even when the
database term is active.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-${ENV_FILE:-.env}}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 2
fi

required_cycle_days="${DUNE_LANDSRAAD_CORIOLIS_REQUIRED_CYCLE_DAYS:-7}"
files=(
  "config/UserGame.ini"
  "config/UserGame.deep-desert-coriolis.ini"
)

read_ini_value() {
  local file="$1"
  local section="$2"
  local key="$3"
  awk -v section="$section" -v key="$key" '
    $0 ~ "^[[:space:]]*\\[" {
      in_section = ($0 == "[" section "]")
      next
    }
    in_section && $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      print
      exit
    }
  ' "$file"
}

failures=0
for file in "${files[@]}"; do
  if [[ ! -f "$file" ]]; then
    printf 'missing Landsraad Coriolis guard config: %s\n' "$file" >&2
    failures=$((failures + 1))
    continue
  fi

  cycle_days="$(read_ini_value "$file" "/Script/DuneSandbox.CoriolisSubsystem" "m_CycleDurationInDays")"
  auto_spawn="$(read_ini_value "$file" "/Script/DuneSandbox.SandStormConfig" "m_bCoriolisAutoSpawnEnabled")"
  does_damage="$(read_ini_value "$file" "/Script/DuneSandbox.SandStormConfig" "m_bCoriolisDoesDamage")"
  shifts_sands="$(read_ini_value "$file" "/Script/DuneSandbox.SandStormConfig" "m_bCoriolisTriggerShiftingSands")"
  restart_on_end="$(read_ini_value "$file" "/Script/DuneSandbox.CoriolisSubsystem" "m_bShouldRestartServerOnCycleEnd")"
  db_wipe="$(read_ini_value "$file" "/Script/DuneSandbox.CoriolisSubsystem" "m_bIsDbWipeEnabled")"

  if [[ "$cycle_days" != "$required_cycle_days" ]]; then
    printf '%s: m_CycleDurationInDays=%s; expected %s for Landsraad active-window health\n' \
      "$file" "${cycle_days:-missing}" "$required_cycle_days" >&2
    failures=$((failures + 1))
  fi
  if [[ "$auto_spawn" != "False" || "$does_damage" != "False" || "$shifts_sands" != "False" ]]; then
    printf '%s: Standard PvE Coriolis destructive flags must stay disabled; auto_spawn=%s damage=%s shifting_sands=%s\n' \
      "$file" "${auto_spawn:-missing}" "${does_damage:-missing}" "${shifts_sands:-missing}" >&2
    failures=$((failures + 1))
  fi
  if [[ "$restart_on_end" != "False" || "$db_wipe" != "False" ]]; then
    printf '%s: Coriolis restart/DB wipe must stay disabled; restart=%s db_wipe=%s\n' \
      "$file" "${restart_on_end:-missing}" "${db_wipe:-missing}" >&2
    failures=$((failures + 1))
  fi
done

if (( failures > 0 )); then
  printf 'Landsraad Coriolis guard failed: keep weekly cycle at %s days and disable destructive Coriolis effects.\n' "$required_cycle_days" >&2
  exit 1
fi

printf 'Landsraad Coriolis guard OK: weekly cycle=%s days, destructive effects disabled\n' "$required_cycle_days"
