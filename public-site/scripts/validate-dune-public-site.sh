#!/usr/bin/env bash
set -euo pipefail

static_dir="${1:-${STATIC_DIR:-/srv/dash-public-site}}"

required=(
  index.html
  style.css
  app.js
  status.html
  players.json
  hagga-pois.json
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
  jq -e '.groups | type == "object"' "$static_dir/hagga-pois.json" >/dev/null
  jq -e '.markers | type == "array" and length > 0' "$static_dir/hagga-pois.json" >/dev/null
  jq -e '
    all(.markers[]; (.group | type == "string") and (.name | type == "string") and (.x | type == "number") and (.y | type == "number"))
  ' "$static_dir/hagga-pois.json" >/dev/null
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
  grep -q '"markers"' "$static_dir/hagga-pois.json"
  grep -q '"groups"' "$static_dir/hagga-pois.json"
  if grep -Eiq 'steam|platform|funcom|account|controller|pawn|fls|profile_url|persona|steamcommunity\.com/profiles' "$static_dir/players.json"; then
    echo "public players.json contains private/admin identity fields" >&2
    exit 1
  fi
fi

grep -q 'id="hagga-map"' "$static_dir/index.html"
grep -q 'id="active-players"' "$static_dir/index.html"
grep -q 'id="poi-toggles"' "$static_dir/index.html"
grep -q 'id="poi-all"' "$static_dir/index.html"
grep -q 'id="poi-preset"' "$static_dir/index.html"
grep -q 'id="poi-clear"' "$static_dir/index.html"
grep -q 'id="poi-filter"' "$static_dir/index.html"
grep -q 'id="poi-enable-filtered"' "$static_dir/index.html"
grep -q 'id="poi-disable-filtered"' "$static_dir/index.html"
grep -q 'id="poi-filter-summary"' "$static_dir/index.html"
grep -q 'hagga-pois.json' "$static_dir/app.js"
grep -q 'sessionStorage.getItem(poiStorageKey)' "$static_dir/app.js"
grep -q 'setFiltered' "$static_dir/app.js"
grep -q '<svg' "$static_dir/hagga-map.svg"
if ! grep -Eq 'hagga-basin\.webp|data:image/webp;base64' "$static_dir/hagga-map.svg"; then
  echo "hagga-map.svg does not reference or embed the Hagga Basin map image" >&2
  exit 1
fi

echo "OK: public Dune static site files validate in $static_dir"
