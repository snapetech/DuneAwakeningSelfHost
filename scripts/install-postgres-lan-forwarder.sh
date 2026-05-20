#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
unit_path="${2:-/etc/systemd/system/dune-postgres-replication-forwarder.service}"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

bind_address="$(awk -F= '/^POSTGRES_REPLICATION_BIND_ADDRESS=/{print $2}' "$env_file" | tail -1)"
bind_address="${bind_address:-}"
bind_port="$(awk -F= '/^POSTGRES_REPLICATION_PUBLIC_PORT=/{print $2}' "$env_file" | tail -1)"
bind_port="${bind_port:-15434}"
allow_address="$(awk -F= '/^POSTGRES_REPLICATION_ALLOWED_ADDRESS=/{print $2}' "$env_file" | tail -1)"
allow_address="${allow_address:-}"
target_host="$(awk -F= '/^POSTGRES_REPLICATION_FORWARD_TARGET_HOST=/{print $2}' "$env_file" | tail -1)"
target_host="${target_host:-127.0.0.1}"
target_port="$(awk -F= '/^POSTGRES_REPLICATION_FORWARD_TARGET_PORT=/{print $2}' "$env_file" | tail -1)"
target_port="${target_port:-15431}"

if [[ -z "$bind_address" ]]; then
  bind_address="$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
fi

if [[ -z "$bind_address" ]]; then
  printf 'could not determine POSTGRES_REPLICATION_BIND_ADDRESS\n' >&2
  exit 1
fi

if [[ -z "$allow_address" && $# -ge 3 ]]; then
  allow_address="$3"
fi

command -v socat >/dev/null || {
  printf 'socat is required on the primary host\n' >&2
  exit 1
}

listen_opts="TCP-LISTEN:${bind_port},bind=${bind_address},fork,reuseaddr"
if [[ -n "$allow_address" ]]; then
  listen_opts="${listen_opts},range=${allow_address}/32"
fi

tmp="$(mktemp)"
cat > "$tmp" <<EOF
[Unit]
Description=Dune Postgres replication LAN forwarder
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/socat ${listen_opts} TCP:${target_host}:${target_port}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$tmp" "$unit_path"
rm -f "$tmp"
sudo systemctl daemon-reload
sudo systemctl enable --now "$(basename "$unit_path")"

printf 'forwarding %s:%s -> %s:%s\n' "$bind_address" "$bind_port" "$target_host" "$target_port"
if [[ -n "$allow_address" ]]; then
  printf 'allowed replication client: %s\n' "$allow_address"
fi
