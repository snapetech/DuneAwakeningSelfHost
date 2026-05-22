#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
seconds="${2:-120}"
tag="${3:-rmq-window}"
out_dir="${4:-captures/rmq/$(date -u +%Y%m%dT%H%M%SZ)-${tag}}"

mkdir -p "$out_dir"
printf 'capturing RabbitMQ topology window for %s seconds into %s\n' "$seconds" "$out_dir"

python3 scripts/research/snapshot-rmq-topology.py "$env_file" --broker admin >"$out_dir/admin-before.json" 2>"$out_dir/admin-before.err" || true
python3 scripts/research/snapshot-rmq-topology.py "$env_file" --broker game >"$out_dir/game-before.json" 2>"$out_dir/game-before.err" || true
sleep "$seconds"
python3 scripts/research/snapshot-rmq-topology.py "$env_file" --broker admin >"$out_dir/admin-after.json" 2>"$out_dir/admin-after.err" || true
python3 scripts/research/snapshot-rmq-topology.py "$env_file" --broker game >"$out_dir/game-after.json" 2>"$out_dir/game-after.err" || true
python3 scripts/diff-rmq-captures.py "$out_dir/admin-before.json" "$out_dir/admin-after.json" --format markdown --output "$out_dir/admin-diff.md" || true
python3 scripts/diff-rmq-captures.py "$out_dir/game-before.json" "$out_dir/game-after.json" --format markdown --output "$out_dir/game-diff.md" || true

cat >"$out_dir/summary.md" <<MD
# RabbitMQ Capture Window

- Env file: \`$env_file\`
- Duration: \`$seconds\`
- Tag: \`$tag\`

Compare before/after topology files and pair this directory with any protocol-specific message capture.
MD

printf 'done: %s\n' "$out_dir"
