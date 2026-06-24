#!/usr/bin/env bash
set -euo pipefail

# Generate a public-safe static status block for the Dune page.
# This exposes only coarse player-facing state. It does not publish ports,
# hosts, container names, routes, logs, tokens, or map topology.

if [[ -z "${DUNE_ROOT:-}" ]]; then
  script_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  if [[ -x "$script_repo_root/scripts/status.sh" ]]; then
    DUNE_ROOT="$script_repo_root"
  elif [[ -x /home/keith/Documents/code/DuneAwakeningSelfHost/scripts/status.sh ]]; then
    DUNE_ROOT="/home/keith/Documents/code/DuneAwakeningSelfHost"
  else
    DUNE_ROOT="/opt/DuneAwakeningSelfHost"
  fi
fi
export DUNE_ROOT
INDEX_FILE="${INDEX_FILE:-/srv/dash-public-site/index.html}"
STATUS_FILE="${STATUS_FILE:-$(dirname "$INDEX_FILE")/status.html}"
STATIC_DIR="${STATIC_DIR:-$(dirname "$INDEX_FILE")}"
SOURCE_INDEX_FILE="${SOURCE_INDEX_FILE:-$DUNE_ROOT/public-site/static/index.html}"
STATUS_TIMEOUT_SECONDS="${STATUS_TIMEOUT_SECONDS:-60}"
SYNC_HOST="${SYNC_HOST:-}"
SYNC_STATIC_ROOT="${SYNC_STATIC_ROOT:-/srv/hostapps/ingress/static}"
CONFIGURE_SCRIPT="${CONFIGURE_SCRIPT:-$(dirname "$0")/configure-dune-public-site.sh}"
DRIFT_CHECK_SCRIPT="${DRIFT_CHECK_SCRIPT:-$(dirname "$0")/check-dune-public-site-drift.sh}"

tmp_status="$(mktemp)"
tmp_index="$(mktemp)"
trap 'rm -f "$tmp_status" "$tmp_index"' EXIT

asset_version() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print substr($1, 1, 12)}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print substr($1, 1, 12)}'
  else
    cksum "$file" | awk '{print $1}'
  fi
}

stamp_static_asset_versions() {
  local app_file="$STATIC_DIR/app.js"
  local style_file="$STATIC_DIR/style.css"
  local app_version style_version tmp_versioned
  [[ -f "$INDEX_FILE" && -f "$app_file" && -f "$style_file" ]] || return 0
  app_version="$(asset_version "$app_file")"
  style_version="$(asset_version "$style_file")"
  tmp_versioned="$(mktemp)"
  sed -E \
    -e "s#href=\"style\.css(\\?v=[^\"]*)?\"#href=\"style.css?v=${style_version}\"#g" \
    -e "s#src=\"app\.js(\\?v=[^\"]*)?\"#src=\"app.js?v=${app_version}\"#g" \
    "$INDEX_FILE" > "$tmp_versioned"
  if [[ -w "$INDEX_FILE" ]]; then
    install -m 0644 "$tmp_versioned" "$INDEX_FILE"
  else
    sudo install -m 0644 "$tmp_versioned" "$INDEX_FILE"
  fi
  rm -f "$tmp_versioned"
}

if [[ -f "$SOURCE_INDEX_FILE" ]]; then
  if [[ -w "$(dirname "$INDEX_FILE")" ]]; then
    install -m 0644 "$SOURCE_INDEX_FILE" "$INDEX_FILE"
  else
    sudo install -m 0644 "$SOURCE_INDEX_FILE" "$INDEX_FILE"
  fi
fi

if [[ -x "$CONFIGURE_SCRIPT" ]]; then
  STATIC_DIR="$STATIC_DIR" INDEX_FILE="$INDEX_FILE" "$CONFIGURE_SCRIPT"
fi

stamp_static_asset_versions

server_class="status-warn"
server_text="Unknown"
world_class="status-warn"
world_text="Unknown"
access_class="status-warn"
access_text="Unknown"
runtime_class="status-unknown"
runtime_text="Unknown"
runtime_label="Since maintenance"
runtime_detail_html="Runtime data unavailable."

if [[ -d "$DUNE_ROOT" ]] && (cd "$DUNE_ROOT" && timeout "$STATUS_TIMEOUT_SECONDS" ./scripts/status.sh .env) >"$tmp_status" 2>&1; then
  health_line="$(sed -nE 's/^current_ready_alive=([0-9]+) current_alive_active=([0-9]+) active_servers=([0-9]+) partitions=([0-9]+) game_sg_connections=([0-9]+) admin_sg_connections=([0-9]+).*/\1 \2 \3 \4 \5 \6/p' "$tmp_status" | tail -1)"
  read -r current_ready_alive current_alive_active active_servers partitions game_sg_connections admin_sg_connections <<< "${health_line:-0 0 0 0 0 0}"
  if [[ "$current_ready_alive" =~ ^[0-9]+$ && "$current_alive_active" =~ ^[0-9]+$ \
      && "$active_servers" =~ ^[0-9]+$ && "$partitions" =~ ^[0-9]+$ \
      && "$game_sg_connections" =~ ^[0-9]+$ && "$admin_sg_connections" =~ ^[0-9]+$ \
      && "$partitions" -gt 0 && "$current_alive_active" -eq "$partitions" \
      && "$active_servers" -eq "$partitions" ]]; then
    server_class="status-ok"
    server_text="Online"
    if [[ "$current_ready_alive" -eq "$partitions" ]]; then
      world_class="status-ok"
      world_text="Healthy"
    else
      world_class="status-warn"
      world_text="Starting"
    fi
    if [[ "$game_sg_connections" -ge "$partitions" ]]; then
      access_class="status-ok"
      access_text="Available"
    else
      access_class="status-warn"
      access_text="Limited"
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

runtime_eval="$(
  python3 - <<'PY'
import datetime
import html
import json
import os
import shlex
import subprocess
import sys

services = {
    "survival", "overmap", "arrakeen", "harko-village", "testing-hephaestus",
    "testing-carthag", "testing-waterfat", "deep-desert", "proces-verbal",
    "lostharvest-ecolab-a", "lostharvest-ecolab-b", "lostharvest-forgottenlab",
    "art-of-kanly", "dungeon-hephaestus", "dungeon-oldcarthag",
    "faction-outpost-atre", "faction-outpost-hark", "heighliner-dungeon",
    "ecolab-green-089", "ecolab-green-152", "ecolab-green-024",
    "ecolab-green-195", "ecolab-green-136", "overland-m-01", "overland-s-04",
    "overland-s-06", "bandit-fortress", "overland-s-07", "overland-s-08",
    "dungeon-thepit",
}
project = os.environ.get("DOCKER_COMPOSE_PROJECT", "dune_server")
dune_root = os.environ.get("DUNE_ROOT", "/opt/DuneAwakeningSelfHost")
restart_state_file = os.environ.get(
    "DUNE_PUBLIC_RESTART_STATE_FILE",
    os.path.join(dune_root, "backups", "admin-panel", "restart-jobs.json"),
)

def read_env_value(path, key):
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""

partition_count = os.environ.get("DUNE_WORLD_PARTITION_COUNT") or read_env_value(
    os.path.join(os.environ.get("DUNE_ROOT", "/opt/DuneAwakeningSelfHost"), ".env"),
    "DUNE_WORLD_PARTITION_COUNT",
)
if partition_count == "31":
    services.add("deep-desert-pvp")

def parse_started(value):
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None

def fmt(seconds):
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def parse_epoch(value):
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)

def latest_maintenance_restart():
    try:
        with open(restart_state_file, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    candidates = []
    for job in state.get("jobs", []):
        status = job.get("status")
        if status not in ("executed", "failed", "completed_with_warnings"):
            continue
        if job.get("action") != "restart" or not job.get("execute"):
            continue
        executed = parse_epoch(job.get("executedAt"))
        if not executed:
            continue
        candidates.append((executed, job))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])

try:
    ps = subprocess.check_output(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            '{{.ID}}\t{{.Label "com.docker.compose.service"}}',
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
except Exception:
    sys.exit(0)

now = datetime.datetime.now(datetime.timezone.utc)
rows = []
restart_count = 0
for line in ps.splitlines():
    if not line.strip():
        continue
    parts = line.split("\t", 1)
    if len(parts) != 2 or parts[1] not in services:
        continue
    try:
        detail = json.loads(subprocess.check_output(["docker", "inspect", parts[0]], text=True, stderr=subprocess.DEVNULL))[0]
    except Exception:
        continue
    state = detail.get("State") or {}
    started = parse_started(state.get("StartedAt"))
    if state.get("Status") != "running" or not started:
        continue
    restart_count += int(detail.get("RestartCount") or 0)
    rows.append((parts[1], started))

if not rows:
    sys.exit(0)

newest = max(started for _, started in rows)
oldest = min(started for _, started in rows)
last_restart = int((now - newest).total_seconds())
oldest_uptime = int((now - oldest).total_seconds())
maintenance = latest_maintenance_restart()
runtime_label = "Since restart"
runtime_text = fmt(last_restart)
runtime_class = "status-ok" if len(rows) == len(services) else "status-warn"
detail = (
    f"<strong>Running maps</strong> {len(rows)}/{len(services)}<br>"
    f"<strong>Most recent restart</strong> {html.escape(newest.strftime('%Y-%m-%d %H:%M UTC'))}<br>"
    f"<strong>Oldest map uptime</strong> {html.escape(fmt(oldest_uptime))}<br>"
    f"<strong>Container restarts</strong> {restart_count}"
)
if maintenance:
    executed, job = maintenance
    age = int((now - executed).total_seconds())
    backup_state = "requested" if job.get("backup") else "not requested"
    status = str(job.get("status") or "unknown")
    status_label = {
        "executed": "completed",
        "failed": "failed",
        "completed_with_warnings": "completed with warnings",
    }.get(status, status)
    runtime_label = "Since maintenance"
    runtime_text = fmt(age)
    if status == "failed" or age > 36 * 3600:
        runtime_class = "status-warn"
    detail = (
        f"<strong>Last maintenance</strong> {html.escape(executed.strftime('%Y-%m-%d %H:%M UTC'))}<br>"
        f"<strong>Status</strong> {html.escape(status_label)}<br>"
        f"<strong>Target</strong> {html.escape(str(job.get('targetLabel') or job.get('target') or 'restart'))}<br>"
        f"<strong>Backup</strong> {html.escape(backup_state)}<br>"
        f"<strong>Most recent container restart</strong> {html.escape(newest.strftime('%Y-%m-%d %H:%M UTC'))}<br>"
        f"<strong>Oldest map uptime</strong> {html.escape(fmt(oldest_uptime))}"
    )
    if age > 36 * 3600:
        detail += "<br><strong>Schedule</strong> stale"
values = {
    "runtime_class": runtime_class,
    "runtime_label": runtime_label,
    "runtime_text": runtime_text,
    "runtime_detail_html": detail,
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)" || runtime_eval=""
if [[ -n "$runtime_eval" ]]; then
  eval "$runtime_eval"
fi

checked_at="$(date -u '+%Y-%m-%d %H:%M UTC')"

status_block="$(cat <<EOF
<section class="status-card">
<h2>Server Status</h2>
<dl class="status-list">
<dt><span class="status-dot ${server_class}"></span>Server</dt><dd>${server_text}</dd>
<dt><span class="status-dot ${world_class}"></span>World health</dt><dd>${world_text}</dd>
<dt><span class="status-dot ${access_class}"></span>Player access</dt><dd>${access_text}</dd>
<dt><span class="status-dot ${runtime_class}"></span>${runtime_label}</dt><dd><span class="status-help" tabindex="0">${runtime_text}<span class="status-popover" role="dialog" aria-label="Uptime details">${runtime_detail_html}</span></span></dd>
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

stamp_static_asset_versions

snapshot_script="$(dirname "$0")/render-dune-public-snapshot.py"
if [[ -x "$snapshot_script" ]]; then
  if [[ -w "$STATIC_DIR" ]]; then
    DUNE_ROOT="$DUNE_ROOT" STATIC_DIR="$STATIC_DIR" "$snapshot_script" || true
  else
    tmp_static="$(mktemp -d)"
    trap 'rm -f "$tmp_status" "$tmp_index"; rm -rf "$tmp_static"' EXIT
    DUNE_ROOT="$DUNE_ROOT" STATIC_DIR="$tmp_static" "$snapshot_script" || true
    find "$tmp_static" -maxdepth 1 -type f \( \
      -name '*.json' -o \
      -name '*.svg' -o \
      -name '*.webp' \
    \) -print0 |
      while IFS= read -r -d '' artifact; do
        sudo install -m 0644 "$artifact" "$STATIC_DIR/$(basename "$artifact")"
      done
  fi
fi

if [[ -x "$DRIFT_CHECK_SCRIPT" ]]; then
  STATIC_DIR="$STATIC_DIR" INDEX_FILE="$INDEX_FILE" STATUS_FILE="$STATUS_FILE" "$DRIFT_CHECK_SCRIPT" "$STATIC_DIR"
fi

if [[ -n "$SYNC_HOST" ]]; then
  tar --warning=no-file-changed --ignore-failed-read -C "$(dirname "$(dirname "$INDEX_FILE")")" -cf - "$(basename "$(dirname "$INDEX_FILE")")" |
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$SYNC_HOST" "sudo mkdir -p '$SYNC_STATIC_ROOT' && sudo tar -C '$SYNC_STATIC_ROOT' -xf -"
fi
