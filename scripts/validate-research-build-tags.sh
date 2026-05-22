#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env.example}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

current_tag="$(read_env DUNE_IMAGE_TAG)"
if [[ -z "$current_tag" ]]; then
  printf 'DUNE_IMAGE_TAG is missing from %s\n' "$env_file" >&2
  exit 1
fi
current_build="${current_tag%%-*}"

files=(
  "SERVER_CONFIG_KEY_INDEX.md"
  "SERVER_BINARY_CONFIG_CANDIDATES.md"
  "SERVER_RUNTIME_SURFACES.md"
  "DEEP_DESERT_EVENT_KNOBS.md"
)

printf 'research build tag validation\n'
printf '  env: %s\n' "$env_file"
printf '  current tag: %s\n\n' "$current_tag"

failed=0
for file in "${files[@]}"; do
  if [[ ! -f "$file" ]]; then
    printf 'FAIL %-38s missing\n' "$file" >&2
    failed=1
    continue
  fi

  if rg -qi 'stale/archived evidence|archived evidence|stale evidence' "$file"; then
    printf 'OK   %-38s explicitly stale/archived\n' "$file"
  elif rg -q --fixed-strings "$current_tag" "$file" || rg -q --fixed-strings "$current_build" "$file"; then
    printf 'OK   %-38s current build evidence\n' "$file"
  else
    printf 'FAIL %-38s no current tag/build and no stale marker\n' "$file" >&2
    failed=1
  fi
done

exit "$failed"
