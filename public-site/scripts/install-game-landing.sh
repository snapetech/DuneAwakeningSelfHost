#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
config_file="${GAME_LANDING_CONFIG:-$repo_root/public-site/landing/game-links.example.json}"
landing_dir="${LANDING_DIR:-/srv/game-landing}"

usage() {
  cat <<EOF
Usage: sudo GAME_LANDING_CONFIG=/path/to/game-links.json \\
  LANDING_DIR=/srv/game-landing \\
  ./public-site/scripts/install-game-landing.sh

Generates and installs a static multi-game link landing page. The bundled
example contains only Dune: Awakening. Add other games in your own manifest.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$config_file" ]]; then
  echo "Missing game landing config: $config_file" >&2
  exit 1
fi

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
"$repo_root/public-site/scripts/generate-game-landing.py" \
  --config "$config_file" \
  --output "$stage"

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

run_privileged install -d -m 0755 "$landing_dir" "$landing_dir/assets"
run_privileged find "$landing_dir/assets" -maxdepth 1 -type f -delete
run_privileged install -m 0644 "$stage/index.html" "$landing_dir/index.html"
run_privileged install -m 0644 "$stage/landing.css" "$landing_dir/landing.css"
run_privileged install -m 0644 "$stage/landing-generated.css" "$landing_dir/landing-generated.css"
while IFS= read -r -d '' asset; do
  run_privileged install -m 0644 "$asset" "$landing_dir/assets/$(basename "$asset")"
done < <(find "$stage/assets" -maxdepth 1 -type f -print0)

echo "Installed static game landing page to $landing_dir"
