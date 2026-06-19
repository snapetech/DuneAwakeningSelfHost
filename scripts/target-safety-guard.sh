#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/target-safety-guard.sh [ENV_FILE]

Read-only scheduled guard for live target safety. It runs the full target audit
and then runs reconcile-map-patch-overlays.sh in fail-on-drift dry-run mode.

Useful environment:
  DUNE_TARGET_AUDIT_PATCH_PROBE_EXCLUDE_SERVICES=survival
  DUNE_RECONCILE_EXCLUDE_SERVICES=survival
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-${ENV_FILE:-.env}}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

"$script_dir/live-target-safety-audit.sh" "$env_file"

DUNE_RECONCILE_FAIL_ON_DRIFT="${DUNE_RECONCILE_FAIL_ON_DRIFT:-true}" \
  "$script_dir/reconcile-map-patch-overlays.sh" "$env_file"
