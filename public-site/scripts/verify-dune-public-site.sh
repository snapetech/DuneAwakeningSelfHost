#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-${PUBLIC_SITE_URL:-}}"
max_age_seconds="${PUBLIC_SITE_MAX_STATUS_AGE_SECONDS:-150}"

if [[ -z "$base_url" ]]; then
  echo "usage: $0 https://example.test/" >&2
  exit 2
fi

base_url="${base_url%/}"
tmp_headers="$(mktemp)"
tmp_index="$(mktemp)"
tmp_status="$(mktemp)"
tmp_players="$(mktemp)"
tmp_index_status="$(mktemp)"
tmp_expected_status="$(mktemp)"
trap 'rm -f "$tmp_headers" "$tmp_index" "$tmp_status" "$tmp_players" "$tmp_index_status" "$tmp_expected_status"' EXIT

curl -fsSL --max-time 15 "$base_url/?v=$(date +%s)" -o "$tmp_index"
curl -fsSIL --max-time 15 "$base_url/" -o "$tmp_headers"
curl -fsSL --max-time 15 "$base_url/status.html?v=$(date +%s)" -o "$tmp_status"
curl -fsSL --max-time 15 "$base_url/players.json?v=$(date +%s)" -o "$tmp_players"

if ! grep -Eiq '^cache-control:.*no-store' "$tmp_headers"; then
  echo "missing no-store Cache-Control on $base_url/" >&2
  exit 1
fi
if grep -Eiq '^age: [1-9]' "$tmp_headers"; then
  echo "unexpected cached response Age header on $base_url/" >&2
  exit 1
fi
if ! grep -q 'World health' "$tmp_status"; then
  echo "status.html does not contain status block" >&2
  exit 1
fi

awk '
  /<!-- STATUS_BEGIN -->/ { inside = 1; next }
  /<!-- STATUS_END -->/ { inside = 0; next }
  inside { print }
' "$tmp_index" > "$tmp_index_status"
{
  echo '<div id="server-status">'
  cat "$tmp_status"
  echo '</div>'
} > "$tmp_expected_status"
if ! cmp -s "$tmp_index_status" "$tmp_expected_status"; then
  echo "remote embedded index status differs from status.html" >&2
  diff -u "$tmp_expected_status" "$tmp_index_status" >&2 || true
  exit 1
fi

checked_text="$(sed -nE 's/.*Last checked ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}) UTC.*/\1/p' "$tmp_status" | tail -1)"
if [[ -z "$checked_text" ]]; then
  echo "status.html does not contain a parseable Last checked timestamp" >&2
  exit 1
fi
checked_epoch="$(date -u -d "${checked_text} UTC" +%s)"
now_epoch="$(date -u +%s)"
age_seconds=$((now_epoch - checked_epoch))
if (( age_seconds < 0 || age_seconds > max_age_seconds )); then
  echo "status.html is not fresh: age=${age_seconds}s max=${max_age_seconds}s" >&2
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  jq -e '.ok | type == "boolean"' "$tmp_players" >/dev/null
  jq -e '.players | type == "array"' "$tmp_players" >/dev/null
else
  grep -q '"players"' "$tmp_players"
fi

echo "OK: verified $base_url status freshness age=${age_seconds}s"
