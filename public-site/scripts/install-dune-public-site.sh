#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
prefix="${PREFIX:-/usr/local}"
static_dir="${STATIC_DIR:-/srv/dash-public-site}"
env_file="${ENV_FILE:-/etc/dune-public-site.env}"
user_name="${DUNE_PUBLIC_SITE_USER:-${SUDO_USER:-$USER}}"

usage() {
  cat <<EOF
Usage: sudo ./public-site/scripts/install-dune-public-site.sh [--no-systemd]

Installs the public Dune static site assets, renderer scripts, example config,
and optional systemd timer. Override paths with environment variables:

  STATIC_DIR=/var/www/dune
  ENV_FILE=/etc/dune-public-site.env
  PREFIX=/usr/local
  DUNE_PUBLIC_SITE_USER=dune

EOF
}

install_systemd=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --no-systemd)
      install_systemd=0
      shift
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root so files can be installed under $static_dir and $prefix." >&2
  exit 1
fi

install -d -m 0755 "$static_dir"
install -m 0644 "$repo_root/public-site/static/index.html" "$static_dir/index.html"
install -m 0644 "$repo_root/public-site/static/style.css" "$static_dir/style.css"
install -m 0644 "$repo_root/public-site/static/app.js" "$static_dir/app.js"
if [[ -f "$repo_root/public-site/static/status.html" ]]; then
  install -m 0644 "$repo_root/public-site/static/status.html" "$static_dir/status.html"
fi

install -d -m 0755 "$prefix/sbin"
install -m 0755 "$repo_root/public-site/scripts/render-dune-static-status.sh" "$prefix/sbin/render-dune-static-status.sh"
install -m 0755 "$repo_root/public-site/scripts/render-dune-public-snapshot.py" "$prefix/sbin/render-dune-public-snapshot.py"
install -m 0755 "$repo_root/public-site/scripts/configure-dune-public-site.sh" "$prefix/sbin/configure-dune-public-site.sh"
install -m 0755 "$repo_root/public-site/scripts/validate-dune-public-site.sh" "$prefix/sbin/validate-dune-public-site.sh"

if [[ ! -f "$env_file" ]]; then
  install -m 0644 "$repo_root/public-site/dune-public-site.env.example" "$env_file"
fi

if [[ "$install_systemd" -eq 1 ]]; then
  install -d -m 0755 /etc/systemd/system
  tmp_service="$(mktemp)"
  sed \
    -e "s#^User=.*#User=$user_name#" \
    -e "s#^EnvironmentFile=.*#EnvironmentFile=-$env_file#" \
    -e "s#^ExecStart=.*#ExecStart=$prefix/sbin/render-dune-static-status.sh#" \
    "$repo_root/public-site/systemd/render-dune-static-status.service" > "$tmp_service"
  install -m 0644 "$tmp_service" /etc/systemd/system/render-dune-static-status.service
  rm -f "$tmp_service"
  install -m 0644 "$repo_root/public-site/systemd/render-dune-static-status.timer" /etc/systemd/system/render-dune-static-status.timer
  systemctl daemon-reload
  systemctl enable --now render-dune-static-status.timer
fi

echo "Installed public Dune static site to $static_dir"
if [[ "$install_systemd" -eq 1 ]]; then
  echo "Review $env_file, then run: systemctl restart render-dune-static-status.service"
else
  echo "Review $env_file, then run: $prefix/sbin/render-dune-static-status.sh"
fi
echo "Customize public text with: STATIC_DIR=$static_dir $prefix/sbin/configure-dune-public-site.sh"
