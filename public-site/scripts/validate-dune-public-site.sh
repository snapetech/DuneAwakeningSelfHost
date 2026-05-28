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
  deep-desert-map.svg
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
  jq -e '(.mapStatus // []) | type == "array"' "$static_dir/players.json" >/dev/null
  jq -e '(.mapHealth // {}) | type == "object"' "$static_dir/players.json" >/dev/null
  jq -e '.groups | type == "object"' "$static_dir/hagga-pois.json" >/dev/null
  jq -e '.markers | type == "array" and length > 0' "$static_dir/hagga-pois.json" >/dev/null
  jq -e '
    (.markers | length <= 5000)
    and (.groups | length <= 64)
    and all(.groups | keys[]; test("^[A-Za-z0-9 _:\\\"()./-]{1,80}$"))
    and all(.markers[];
      (.id | type == "string" and length <= 120)
      and (.group | type == "string" and length <= 80)
      and (.name | type == "string" and length <= 120)
      and (.article | type == "string" and length <= 120)
      and (.x | type == "number" and . >= 0 and . <= 100000)
      and (.y | type == "number" and . >= 0 and . <= 100000)
    )
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
grep -q 'data-map-tab="deep-desert"' "$static_dir/index.html"
grep -q 'data-map-tab="health"' "$static_dir/index.html"
grep -q 'id="map-health-panel"' "$static_dir/index.html"
grep -q 'id="active-players"' "$static_dir/index.html"
grep -q 'id="poi-toggles"' "$static_dir/index.html"
grep -q 'id="poi-all"' "$static_dir/index.html"
grep -q 'id="poi-clear"' "$static_dir/index.html"
grep -q 'id="poi-filter"' "$static_dir/index.html"
grep -q 'id="poi-filter-summary"' "$static_dir/index.html"
grep -q 'awakening.wiki/Map:Hagga_Basin' "$static_dir/index.html"
grep -q 'hagga-pois.json' "$static_dir/app.js"
grep -q 'sessionStorage.getItem(poiStorageKey)' "$static_dir/app.js"
grep -q 'assetUrl("status.html", true)' "$static_dir/app.js"
grep -q 'Live status is not fresh' "$static_dir/app.js"
grep -q 'renderStatusUnavailable' "$static_dir/app.js"
if [[ -x "$(dirname "$0")/check-dune-public-site-drift.sh" ]]; then
  DUNE_PUBLIC_SITE_MAX_STATUS_AGE_SECONDS=0 "$(dirname "$0")/check-dune-public-site-drift.sh" "$static_dir" >/dev/null
fi
if grep -Eq 'innerHTML|outerHTML|insertAdjacentHTML|document\.write' "$static_dir/app.js"; then
  echo "public app.js contains unsafe HTML injection sinks" >&2
  exit 1
fi
grep -q '<svg' "$static_dir/hagga-map.svg"
grep -q '<svg' "$static_dir/deep-desert-map.svg"
if grep -Eiq '<script|<foreignObject|<iframe|<object|<embed|on[a-z]+=' "$static_dir/hagga-map.svg"; then
  echo "hagga-map.svg contains executable or embeddable content" >&2
  exit 1
fi
if ! grep -Eq 'hagga-basin\.webp|data:image/webp;base64' "$static_dir/hagga-map.svg"; then
  echo "hagga-map.svg does not reference or embed the Hagga Basin map image" >&2
  exit 1
fi

echo "OK: public Dune static site files validate in $static_dir"
