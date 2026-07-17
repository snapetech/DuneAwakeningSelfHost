#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
env_file="$tmp/test.env"
printf 'UNRELATED=keep\nDUNE_AUTOSCALER_PROFILE=custom\n' > "$env_file"

before="$(sha256sum "$env_file" | awk '{print $1}')"
"$repo_root/scripts/configure-autoscaler-profile.sh" "$env_file" balanced >/dev/null
after="$(sha256sum "$env_file" | awk '{print $1}')"
[[ "$before" == "$after" ]]

inode_before="$(stat -c '%d:%i' "$env_file")"
DUNE_AUTOSCALER_CONFIG_BACKUP_DIR="$tmp/backups" "$repo_root/scripts/configure-autoscaler-profile.sh" "$env_file" balanced --execute >/dev/null
[[ "$(stat -c '%d:%i' "$env_file")" == "$inode_before" ]]
grep -qx 'UNRELATED=keep' "$env_file"
grep -qx 'DUNE_AUTOSCALER_PROFILE=balanced' "$env_file"
grep -qx 'DUNE_AUTOSCALER_DEFAULT_MODE=dynamic' "$env_file"
grep -qx 'DUNE_AUTOSCALER_BALANCED_MAX_WARM_MAPS=4' "$env_file"
grep -qx 'DUNE_AUTOSCALER_BALANCED_MIN_AVAILABLE_MEMORY_GIB=16' "$env_file"
[[ "$(grep -c '^DUNE_AUTOSCALER_PROFILE=' "$env_file")" == 1 ]]

DUNE_AUTOSCALER_CONFIG_BACKUP_DIR="$tmp/backups" "$repo_root/scripts/configure-autoscaler-profile.sh" "$env_file" adaptive --execute >/dev/null
grep -qx 'DUNE_AUTOSCALER_PROFILE=adaptive' "$env_file"
grep -qx 'DUNE_CAPACITY_INTELLIGENCE_ENABLED=true' "$env_file"
grep -qx 'DUNE_CAPACITY_AUTO_APPLY_ENABLED=true' "$env_file"

printf 'autoscaler profile configuration tests passed\n'
