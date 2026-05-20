#!/usr/bin/env bash
set -euo pipefail

out="${1:-dist/dash-public-site.tar.gz}"
mkdir -p "$(dirname "$out")"

tar \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  -czf "$out" \
  public-site \
  examples/public-site \
  docs/public-static-site.md

echo "Wrote $out"
