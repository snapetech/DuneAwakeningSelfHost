#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
expected_host="${DUNE_PRODUCTION_HOST:-kspls0}"

if [[ "$(hostname -s)" != "$expected_host" ]]; then
  printf 'error: refusing live origin-guard install on %s; expected %s\n' "$(hostname -s)" "$expected_host" >&2
  exit 1
fi
if [[ "$(id -u)" -ne 0 ]]; then
  printf 'error: run as root\n' >&2
  exit 1
fi

install -o root -g root -m 0755 "$repo_root/scripts/cloudflare-origin-guard.sh" /usr/local/sbin/dune-cloudflare-origin-guard
install -o root -g root -m 0644 "$repo_root/config/systemd/dune-cloudflare-origin-guard.service" /etc/systemd/system/dune-cloudflare-origin-guard.service
systemctl daemon-reload
systemctl enable dune-cloudflare-origin-guard.service
systemctl restart dune-cloudflare-origin-guard.service
/usr/local/sbin/dune-cloudflare-origin-guard check
