#!/usr/bin/env bash
set -euo pipefail

capture_dir="${1:-}"
if [[ -z "$capture_dir" || ! -d "$capture_dir" ]]; then
  printf 'usage: %s CAPTURE_DIR\n' "$0" >&2
  exit 2
fi

extract_line() {
  local file="$1" pattern="$2"
  [[ -f "$file" ]] || return 0
  rg -m 1 "$pattern" "$file" || true
}

before="$capture_dir/before.txt"
after="$capture_dir/after.txt"
summary="$capture_dir/summary.md"

{
  printf '# Handoff Summary\n\n'
  printf 'capture_dir=%s\n\n' "$capture_dir"
  printf '## Before\n\n'
  extract_line "$before" 'current_ready_alive='
  extract_line "$before" 'OK: all current partitions'
  extract_line "$before" 'WARN: expected readiness'
  extract_line "$before" 'OK: no recent RabbitMQ'
  extract_line "$before" 'router Dune forwards are'
  printf '\n## After\n\n'
  extract_line "$after" 'current_ready_alive='
  extract_line "$after" 'OK: all current partitions'
  extract_line "$after" 'WARN: expected readiness'
  extract_line "$after" 'OK: no recent RabbitMQ'
  extract_line "$after" 'router Dune forwards are'
  printf '\n## Operator Result\n\n'
  if [[ -f "$capture_dir/operator-notes.md" ]]; then
    sed -n '/^Record:/,$p' "$capture_dir/operator-notes.md"
  else
    printf 'operator-notes.md missing\n'
  fi
  printf '\n## Files\n\n'
  find "$capture_dir" -maxdepth 1 -type f -printf '- %f\n' | sort
} >"$summary"

cat "$summary"
