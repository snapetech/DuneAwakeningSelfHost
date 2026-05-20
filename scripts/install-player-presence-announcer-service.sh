#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-.env}"
run_user="${DUNE_PLAYER_PRESENCE_SERVICE_USER:-$(id -un)}"
service_name="dune-player-presence-announcer.service"
unit_dst="/etc/systemd/system/$service_name"

if [[ ! -f "$root/$env_file" ]]; then
  printf 'env file not found: %s\n' "$root/$env_file" >&2
  exit 66
fi

tmp_unit="$(mktemp)"
trap 'rm -f "$tmp_unit"' EXIT

cat > "$tmp_unit" <<EOF
[Unit]
Description=Dune player join/leave announcer
Documentation=file://$root/docs/admin-bot.md
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$run_user
WorkingDirectory=$root
Environment=DUNE_ADMIN_BOT_ENV_FILE=$env_file
ExecStart=$root/scripts/player-presence-announcer.py --loop
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$tmp_unit" "$unit_dst"
sudo systemctl daemon-reload
sudo systemctl enable --now "$service_name"
sudo systemctl status --no-pager --lines=20 "$service_name"
