#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/configure-autoscaler-profile.sh [ENV_FILE] PROFILE [--execute]

PROFILE is one of: minimum-footprint, balanced, full-warm, custom.
Without --execute, prints the planned values and does not change ENV_FILE.
The script changes only autoscaler keys and preserves unrelated settings.
USAGE
}

env_file="${1:-.env}"
profile="${2:-}"
mode="${3:-}"
[[ -f "$env_file" ]] || { printf 'env file not found: %s\n' "$env_file" >&2; exit 2; }
case "$profile" in minimum-footprint|balanced|full-warm|custom) ;; *) usage; exit 2 ;; esac
[[ -z "$mode" || "$mode" == "--execute" ]] || { usage; exit 2; }

declare -A values=(
  [DUNE_AUTOSCALER_ENABLED]=true
  [DUNE_AUTOSCALER_PROFILE]="$profile"
  [DUNE_AUTOSCALER_ALWAYS_ON_SERVICES]="${DUNE_AUTOSCALER_ALWAYS_ON_SERVICES:-survival,overmap}"
  [DUNE_AUTOSCALER_DEMAND_TTL_SECONDS]="${DUNE_AUTOSCALER_DEMAND_TTL_SECONDS:-900}"
  [DUNE_AUTOSCALER_POLL_SECONDS]="${DUNE_AUTOSCALER_POLL_SECONDS:-3}"
  [DUNE_AUTOSCALER_FAST_START]="${DUNE_AUTOSCALER_FAST_START:-true}"
)

case "$profile" in
  minimum-footprint)
    values[DUNE_AUTOSCALER_DEFAULT_MODE]=dynamic
    values[DUNE_AUTOSCALER_IDLE_SECONDS]="${DUNE_AUTOSCALER_IDLE_SECONDS:-300}"
    ;;
  balanced)
    values[DUNE_AUTOSCALER_DEFAULT_MODE]=dynamic
    values[DUNE_AUTOSCALER_BALANCED_RETENTION_SECONDS]="${DUNE_AUTOSCALER_BALANCED_RETENTION_SECONDS:-900}"
    values[DUNE_AUTOSCALER_BALANCED_RETENTION_BY_SERVICE]="${DUNE_AUTOSCALER_BALANCED_RETENTION_BY_SERVICE:-arrakeen=2700,harko-village=2700,deep-desert=1800}"
    values[DUNE_AUTOSCALER_BALANCED_MAX_WARM_MAPS]="${DUNE_AUTOSCALER_BALANCED_MAX_WARM_MAPS:-4}"
    values[DUNE_AUTOSCALER_BALANCED_MIN_AVAILABLE_MEMORY_GIB]="${DUNE_AUTOSCALER_BALANCED_MIN_AVAILABLE_MEMORY_GIB:-16}"
    ;;
  full-warm)
    values[DUNE_AUTOSCALER_DEFAULT_MODE]=always-on
    ;;
esac

printf 'autoscaler profile plan for %s:\n' "$env_file"
while IFS= read -r key; do printf '  %s=%s\n' "$key" "${values[$key]}"; done < <(printf '%s\n' "${!values[@]}" | sort)
if [[ -z "$mode" ]]; then
  printf 'no changes made; rerun with --execute\n'
  exit 0
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${DUNE_AUTOSCALER_CONFIG_BACKUP_DIR:-$repo_root/backups/admin-panel/autoscaler-config}"
mkdir -p "$backup_dir"
cp -a "$env_file" "$backup_dir/env-before-$stamp"

set_value() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp "${env_file}.tmp.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { done=0 }
    $0 ~ "^" key "=" { if (!done) print key "=" value; done=1; next }
    { print }
    END { if (!done) print key "=" value }
  ' "$env_file" > "$tmp"
  chmod --reference="$env_file" "$tmp" 2>/dev/null || chmod 600 "$tmp"
  mv "$tmp" "$env_file"
}

while IFS= read -r key; do set_value "$key" "${values[$key]}"; done < <(printf '%s\n' "${!values[@]}" | sort)
printf 'configured %s; backup=%s\n' "$profile" "$backup_dir/env-before-$stamp"
printf 'recreate admin-panel, then apply/reconcile the same profile in Infrastructure\n'
