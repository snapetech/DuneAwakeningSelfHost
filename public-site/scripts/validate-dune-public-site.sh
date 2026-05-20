#!/usr/bin/env bash
set -euo pipefail

static_dir="${1:-${STATIC_DIR:-/srv/dash-public-site}}"

required=(
  index.html
  style.css
  app.js
  status.html
  players.json
  hagga-map.svg
  hagga-basin.webp
)

for file in "${required[@]}"; do
  if [[ ! -s "$static_dir/$file" ]]; then
    echo "missing or empty: $static_dir/$file" >&2
    exit 1
  fi
done

if command -v jq >/dev/null 2>&1; then
  jq -e '.ok | type == "boolean"' "$static_dir/players.json" >/dev/null
  jq -e '.players | type == "array"' "$static_dir/players.json" >/dev/null
  if jq -e '
    def forbidden:
      paths(scalars) as $p
      | ($p | map(tostring) | join(".") | ascii_downcase) as $path
      | (getpath($p) | tostring | ascii_downcase) as $value
      | select(
          ($path | test("steam|platform|funcom|account|controller|pawn|fls|profile_url|persona"))
          or ($value | test("steamcommunity\\.com/profiles|steamid|funcom_id|platform_id|steam_persona"))
        );
    any(forbidden; true)
  ' "$static_dir/players.json" >/dev/null; then
    echo "public players.json contains private/admin identity fields" >&2
    exit 1
  fi
else
  grep -q '"players"' "$static_dir/players.json"
  if grep -Eiq 'steam|platform|funcom|account|controller|pawn|fls|profile_url|persona|steamcommunity\.com/profiles' "$static_dir/players.json"; then
    echo "public players.json contains private/admin identity fields" >&2
    exit 1
  fi
fi

grep -q 'id="hagga-map"' "$static_dir/index.html"
grep -q 'id="active-players"' "$static_dir/index.html"
grep -q '<svg' "$static_dir/hagga-map.svg"
grep -q 'hagga-basin.webp' "$static_dir/hagga-map.svg"

echo "OK: public Dune static site files validate in $static_dir"
