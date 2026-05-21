#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

status_root="${DUNE_STATUS_ROOT:-$(read_env DUNE_STATUS_ROOT)}"
status_user="${DUNE_STATUS_USER:-$(read_env DUNE_STATUS_USER)}"
status_host="${DUNE_STATUS_HOST:-$(read_env DUNE_STATUS_HOST)}"
status_port="${DUNE_STATUS_PORT:-$(read_env DUNE_STATUS_PORT)}"
unit_path="${DUNE_STATUS_UNIT_PATH:-/etc/systemd/system/dune-status.service}"

status_host="${status_host:-127.0.0.1}"
status_port="${status_port:-3030}"
status_user="${status_user:-$(id -un)}"

if [[ -z "$status_root" ]]; then
  printf 'DUNE_STATUS_ROOT is required\n' >&2
  exit 1
fi
if [[ ! -f "$status_root/server.js" ]]; then
  printf 'DuneStatus server.js not found under DUNE_STATUS_ROOT: %s\n' "$status_root" >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

cat > "$tmp" <<EOF
[Unit]
Description=Dune Status Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$status_user
WorkingDirectory=$status_root
Environment=NODE_ENV=production
Environment=PORT=$status_port
Environment=HOST=$status_host
Environment=STEAM_POLL_SECONDS=${DUNE_STATUS_STEAM_POLL_SECONDS:-60}
Environment=DUNESTATUS_POLL_SECONDS=${DUNE_STATUS_POLL_SECONDS:-120}
Environment=DUNEEXCHANGE_POLL_SECONDS=${DUNE_STATUS_EXCHANGE_POLL_SECONDS:-300}
Environment=MENTAT_POLL_SECONDS=${DUNE_STATUS_MENTAT_POLL_SECONDS:-900}
ExecStart=/usr/bin/node $status_root/server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

install_cmd=(install -m 0644 "$tmp" "$unit_path")
if [[ "$(id -u)" -ne 0 ]]; then
  install_cmd=(sudo "${install_cmd[@]}")
fi
"${install_cmd[@]}"

if [[ "$(id -u)" -eq 0 ]]; then
  systemctl daemon-reload
else
  sudo systemctl daemon-reload
fi

if [[ "${DUNE_STATUS_ENABLE_NOW:-false}" == "true" ]]; then
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl enable --now "$(basename "$unit_path")"
  else
    sudo systemctl enable --now "$(basename "$unit_path")"
  fi
else
  printf 'installed %s; enable with: sudo systemctl enable --now %s\n' "$unit_path" "$(basename "$unit_path")"
fi
