#!/usr/bin/env bash
set -euo pipefail

# Example object-storage sync after the local renderer updates the static files.
# Configure the remote with `rclone config` first.

STATIC_DIR="${STATIC_DIR:-/srv/dash-public-site}"
RCLONE_REMOTE="${RCLONE_REMOTE:-b2:dune-public-site}"

rclone sync "$STATIC_DIR" "$RCLONE_REMOTE" \
  --include "/index.html" \
  --include "/style.css" \
  --include "/app.js" \
  --include "/status.html" \
  --include "/players.json" \
  --include "/hagga-map.svg" \
  --include "/hagga-basin.webp" \
  --exclude "*" \
  --transfers 4 \
  --checkers 8
