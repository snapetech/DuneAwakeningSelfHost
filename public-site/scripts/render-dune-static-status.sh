#!/usr/bin/env bash
set -euo pipefail

# Generate a public-safe static status block for the Dune page.
# This exposes only coarse player-facing state. It does not publish ports,
# hosts, container names, routes, logs, tokens, or map topology.

DUNE_ROOT="${DUNE_ROOT:-/opt/DuneAwakeningSelfHost}"
INDEX_FILE="${INDEX_FILE:-/srv/dash-public-site/index.html}"
STATUS_FILE="${STATUS_FILE:-$(dirname "$INDEX_FILE")/status.html}"
STATIC_DIR="${STATIC_DIR:-$(dirname "$INDEX_FILE")}"
STATUS_TIMEOUT_SECONDS="${STATUS_TIMEOUT_SECONDS:-20}"
SYNC_HOST="${SYNC_HOST:-}"
SYNC_STATIC_ROOT="${SYNC_STATIC_ROOT:-/srv/hostapps/ingress/static}"

tmp_status="$(mktemp)"
tmp_index="$(mktemp)"
trap 'rm -f "$tmp_status" "$tmp_index"' EXIT

server_class="status-down"
server_text="Offline"
world_class="status-down"
world_text="Offline"
access_class="status-down"
access_text="Unavailable"

if [[ -d "$DUNE_ROOT" ]] && (cd "$DUNE_ROOT" && timeout "$STATUS_TIMEOUT_SECONDS" ./scripts/status.sh .env) >"$tmp_status" 2>&1; then
  if grep -q 'OK: all current partitions have alive active farm rows' "$tmp_status"; then
    server_class="status-ok"
    server_text="Online"
    access_class="status-ok"
    access_text="Available"
    if grep -q '^NOTE: one or more current partitions are alive/active but have ready=false' "$tmp_status"; then
      world_class="status-warn"
      world_text="Degraded"
    else
      world_class="status-ok"
      world_text="Healthy"
    fi
  else
    server_class="status-warn"
    server_text="Partial"
    world_class="status-warn"
    world_text="Degraded"
    access_class="status-warn"
    access_text="Limited"
  fi
fi

checked_at="$(date -u '+%Y-%m-%d %H:%M UTC')"

status_block="$(cat <<EOF
<section class="status-card">
<h2>Server Status</h2>
<dl class="status-list">
<dt><span class="status-dot ${server_class}"></span>Server</dt><dd>${server_text}</dd>
<dt><span class="status-dot ${world_class}"></span>World health</dt><dd>${world_text}</dd>
<dt><span class="status-dot ${access_class}"></span>Player access</dt><dd>${access_text}</dd>
</dl>
<p class="status-updated">Last checked ${checked_at}.</p>
</section>
EOF
)"

status_marked_block="$(cat <<EOF
<!-- STATUS_BEGIN -->
<div id="server-status">
${status_block}
</div>
<!-- STATUS_END -->
EOF
)"

if [[ -w "$(dirname "$STATUS_FILE")" ]]; then
  printf '%s\n' "$status_block" > "$STATUS_FILE"
else
  printf '%s\n' "$status_block" | sudo tee "$STATUS_FILE" >/dev/null
  sudo chmod 0644 "$STATUS_FILE"
fi

awk -v block="$status_marked_block" '
  /<!-- STATUS_BEGIN -->/ {
    print block
    skipping = 1
    next
  }
  /<!-- STATUS_END -->/ {
    skipping = 0
    next
  }
  !skipping { print }
' "$INDEX_FILE" > "$tmp_index"

if [[ -w "$(dirname "$INDEX_FILE")" ]]; then
  install -m 0644 "$tmp_index" "$INDEX_FILE"
else
  sudo install -m 0644 "$tmp_index" "$INDEX_FILE"
fi

snapshot_script="$(dirname "$0")/render-dune-public-snapshot.py"
if [[ -x "$snapshot_script" ]]; then
  if [[ -w "$STATIC_DIR" ]]; then
    DUNE_ROOT="$DUNE_ROOT" STATIC_DIR="$STATIC_DIR" "$snapshot_script" || true
  else
    tmp_static="$(mktemp -d)"
    trap 'rm -f "$tmp_status" "$tmp_index"; rm -rf "$tmp_static"' EXIT
    DUNE_ROOT="$DUNE_ROOT" STATIC_DIR="$tmp_static" "$snapshot_script" || true
    for artifact in players.json hagga-map.svg hagga-basin.webp; do
      if [[ -f "$tmp_static/$artifact" ]]; then
        sudo install -m 0644 "$tmp_static/$artifact" "$STATIC_DIR/$artifact"
      fi
    done
  fi
fi

if [[ -n "$SYNC_HOST" ]]; then
  tar --warning=no-file-changed --ignore-failed-read -C "$(dirname "$(dirname "$INDEX_FILE")")" -cf - "$(basename "$(dirname "$INDEX_FILE")")" |
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$SYNC_HOST" "sudo mkdir -p '$SYNC_STATIC_ROOT' && sudo tar -C '$SYNC_STATIC_ROOT' -xf -"
fi
