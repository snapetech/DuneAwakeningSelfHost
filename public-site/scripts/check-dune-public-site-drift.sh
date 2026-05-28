#!/usr/bin/env bash
set -euo pipefail

static_dir="${1:-${STATIC_DIR:-/srv/dash-public-site}}"
max_age_seconds="${DUNE_PUBLIC_SITE_MAX_STATUS_AGE_SECONDS:-180}"

index_file="${INDEX_FILE:-$static_dir/index.html}"
status_file="${STATUS_FILE:-$static_dir/status.html}"
players_file="$static_dir/players.json"

tmp_index_status="$(mktemp)"
tmp_expected_status="$(mktemp)"
trap 'rm -f "$tmp_index_status" "$tmp_expected_status"' EXIT

if [[ ! -s "$index_file" ]]; then
  echo "missing or empty index file: $index_file" >&2
  exit 1
fi
if [[ ! -s "$status_file" ]]; then
  echo "missing or empty status file: $status_file" >&2
  exit 1
fi

awk '
  /<!-- STATUS_BEGIN -->/ { inside = 1; next }
  /<!-- STATUS_END -->/ { inside = 0; next }
  inside { print }
' "$index_file" > "$tmp_index_status"

{
  echo '<div id="server-status">'
  cat "$status_file"
  echo '</div>'
} > "$tmp_expected_status"

if ! cmp -s "$tmp_index_status" "$tmp_expected_status"; then
  echo "embedded index status differs from status.html" >&2
  diff -u "$tmp_expected_status" "$tmp_index_status" >&2 || true
  exit 1
fi

checked_text="$(sed -nE 's/.*Last checked ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}) UTC.*/\1/p' "$status_file" | tail -1)"
if [[ -z "$checked_text" ]]; then
  echo "status.html does not contain a parseable Last checked timestamp" >&2
  exit 1
fi
checked_epoch="$(date -u -d "${checked_text} UTC" +%s)"
now_epoch="$(date -u +%s)"
age_seconds=$((now_epoch - checked_epoch))
if (( max_age_seconds > 0 )); then
  if (( age_seconds < 0 || age_seconds > max_age_seconds )); then
    echo "status.html is stale: age=${age_seconds}s max=${max_age_seconds}s" >&2
    exit 1
  fi
fi

if [[ -s "$players_file" ]] && command -v jq >/dev/null 2>&1; then
  jq -e '.ok == true' "$players_file" >/dev/null
  jq -e '(.mapHealth // {}) as $h | (($h.offline // 0) | type == "number") and (($h.degraded // 0) | type == "number")' "$players_file" >/dev/null
fi

echo "OK: public site status is synchronized and fresh age=${age_seconds}s"
