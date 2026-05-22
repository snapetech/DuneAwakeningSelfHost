#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-${PUBLIC_SITE_ENV_FILE:-/etc/dune-public-site.env}}"

if [[ -f "$env_file" ]]; then
  # shellcheck disable=SC1090
  source "$env_file"
fi

static_dir="${STATIC_DIR:-/srv/dash-public-site}"
index_file="${INDEX_FILE:-$static_dir/index.html}"
render_service="${PUBLIC_SITE_RENDER_SERVICE:-render-dune-static-status.service}"
render_script="${PUBLIC_SITE_RENDER_SCRIPT:-/usr/local/sbin/render-dune-static-status.sh}"
validate_script="$repo_root/public-site/scripts/validate-dune-public-site.sh"
verify_url="${PUBLIC_SITE_URL:-}"

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

install_file() {
  local src="$1"
  local dst="$2"
  if [[ -w "$(dirname "$dst")" ]]; then
    install -m 0644 "$src" "$dst"
  else
    run_privileged install -m 0644 "$src" "$dst"
  fi
}

if [[ -d "$static_dir" && -w "$static_dir" ]]; then
  install -d -m 0755 "$static_dir"
else
  run_privileged install -d -m 0755 "$static_dir"
fi
install_file "$repo_root/public-site/static/index.html" "$index_file"
install_file "$repo_root/public-site/static/style.css" "$static_dir/style.css"
install_file "$repo_root/public-site/static/app.js" "$static_dir/app.js"
if [[ -f "$repo_root/public-site/static/hagga-pois.json" ]]; then
  install_file "$repo_root/public-site/static/hagga-pois.json" "$static_dir/hagga-pois.json"
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$render_service" >/dev/null 2>&1; then
  run_privileged systemctl restart "$render_service"
elif [[ -x "$render_script" ]]; then
  STATIC_DIR="$static_dir" INDEX_FILE="$index_file" "$render_script"
else
  echo "no renderer found: $render_service or $render_script" >&2
  exit 1
fi

"$validate_script" "$static_dir"

if [[ -n "$verify_url" ]]; then
  "$repo_root/public-site/scripts/verify-dune-public-site.sh" "$verify_url"
fi

echo "OK: deployed public site to $static_dir"
