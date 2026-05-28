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

install_static_assets() {
  local src_dir="$repo_root/public-site/static"
  local asset
  find "$src_dir" -maxdepth 1 -type f \( \
    -name '*.html' -o \
    -name '*.css' -o \
    -name '*.js' -o \
    -name '*.json' -o \
    -name '*.svg' -o \
    -name '*.webp' \
  \) -print0 |
    while IFS= read -r -d '' asset; do
      case "$(basename "$asset")" in
        players.json|status.html|hagga-map.svg|deep-desert-map.svg|deep-desert-map-data.json|deep-desert-observations.json)
          continue
          ;;
      esac
      install_file "$asset" "$static_dir/$(basename "$asset")"
    done
}

install_render_scripts() {
  local dst_dir="${PUBLIC_SITE_RENDER_SCRIPT_DIR:-/usr/local/sbin}"
  local script
  if [[ -d "$dst_dir" && -w "$dst_dir" ]]; then
    install -m 0755 "$repo_root/public-site/scripts/render-dune-static-status.sh" "$dst_dir/render-dune-static-status.sh"
    install -m 0755 "$repo_root/public-site/scripts/render-dune-public-snapshot.py" "$dst_dir/render-dune-public-snapshot.py"
    install -m 0755 "$repo_root/public-site/scripts/configure-dune-public-site.sh" "$dst_dir/configure-dune-public-site.sh"
    install -m 0755 "$repo_root/public-site/scripts/validate-dune-public-site.sh" "$dst_dir/validate-dune-public-site.sh"
    install -m 0755 "$repo_root/public-site/scripts/check-dune-public-site-drift.sh" "$dst_dir/check-dune-public-site-drift.sh"
  else
    run_privileged install -d -m 0755 "$dst_dir"
    for script in render-dune-static-status.sh render-dune-public-snapshot.py configure-dune-public-site.sh validate-dune-public-site.sh check-dune-public-site-drift.sh; do
      run_privileged install -m 0755 "$repo_root/public-site/scripts/$script" "$dst_dir/$script"
    done
  fi
}

if [[ -d "$static_dir" && -w "$static_dir" ]]; then
  install -d -m 0755 "$static_dir"
else
  run_privileged install -d -m 0755 "$static_dir"
fi
install_static_assets
install_render_scripts

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
