#!/usr/bin/env bash
set -euo pipefail

static_dir="${STATIC_DIR:-/srv/dash-public-site}"
index_file="${INDEX_FILE:-$static_dir/index.html}"
env_file="${ENV_FILE:-}"

env_file_value() {
  local key="$1"
  local line value
  [[ -n "$env_file" && -f "$env_file" ]] || return 1
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$env_file" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1
  value="${line#*=}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

PUBLIC_SITE_TITLE="${PUBLIC_SITE_TITLE:-$(env_file_value PUBLIC_SITE_TITLE || true)}"
PUBLIC_SERVER_NAME="${PUBLIC_SERVER_NAME:-$(env_file_value PUBLIC_SERVER_NAME || true)}"
PUBLIC_SERVER_DESCRIPTION="${PUBLIC_SERVER_DESCRIPTION:-$(env_file_value PUBLIC_SERVER_DESCRIPTION || true)}"
PUBLIC_SERVER_WHERE="${PUBLIC_SERVER_WHERE:-$(env_file_value PUBLIC_SERVER_WHERE || true)}"
PUBLIC_STACK_URL="${PUBLIC_STACK_URL:-$(env_file_value PUBLIC_STACK_URL || true)}"
WORLD_NAME="${WORLD_NAME:-$(env_file_value WORLD_NAME || true)}"
DUNE_SERVER_DISPLAY_NAME="${DUNE_SERVER_DISPLAY_NAME:-$(env_file_value DUNE_SERVER_DISPLAY_NAME || true)}"

server_name="${WORLD_NAME:-${PUBLIC_SERVER_NAME:-${PUBLIC_SITE_TITLE:-Dune Awakening Server}}}"
server_description="${DUNE_SERVER_DISPLAY_NAME:-${PUBLIC_SERVER_DESCRIPTION:-A community Dune Awakening server with public status, settings, and an active player map.}}"
site_title="$server_name"
server_where="${PUBLIC_SERVER_WHERE:-Dune Awakening > Servers > search for your server name.}"
stack_url="${PUBLIC_STACK_URL:-https://github.com/snapetech/DuneAwakeningSelfHost}"

usage() {
  cat <<EOF
Usage:
  WORLD_NAME="Example PVE Server" \\
  DUNE_SERVER_DISPLAY_NAME="Friendly PvE server." \\
  PUBLIC_SERVER_WHERE="Dune Awakening > Servers > Experimental > search Example." \\
  STATIC_DIR=/srv/dune-public-site \\
  ./public-site/scripts/configure-dune-public-site.sh

Updates common public-facing text in an installed static Dune site. Server
name and description default to the same WORLD_NAME and
DUNE_SERVER_DISPLAY_NAME values used by the game stack.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$index_file" ]]; then
  echo "Missing index file: $index_file" >&2
  exit 1
fi

escape_html() {
  printf '%s' "$1" | sed \
    -e 's/&/\&amp;/g' \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g' \
    -e 's/"/\&quot;/g' \
    -e "s/'/\&#39;/g"
}

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

title_html="$(escape_html "$site_title")"
server_html="$(escape_html "$server_name")"
description_html="$(escape_html "$server_description")"
where_html="$(escape_html "$server_where")"
stack_url_html="$(escape_html "$stack_url")"

tmp="$(mktemp)"
sed \
  -e "s#<title>.*</title>#<title>$(escape_sed "$title_html")</title>#" \
  -e "s#<h1>.*</h1>#<h1>$(escape_sed "$server_html")</h1>#" \
  -e "s#<p class=\"lede\">.*</p>#<p class=\"lede\">$(escape_sed "$description_html")</p>#" \
  -e "s#<p><strong>Server Name:</strong> .*<\\/p>#<p><strong>Server Name:</strong> $(escape_sed "$server_html")</p>#" \
  -e "s#<p><strong>How To Join:</strong> .*<\\/p>#<p><strong>How To Join:</strong> $(escape_sed "$where_html")</p>#" \
  -e "s#<p><a href=\"[^\"]*\">DuneAwakeningSelfHost</a> is the stack used to host this server\\.</p>#<p><a href=\"$(escape_sed "$stack_url_html")\">DuneAwakeningSelfHost</a> is the stack used to host this server.</p>#" \
  -e "s#<p class=\"stack-link\"><a href=\"[^\"]*\">DuneAwakeningSelfHost</a> powers this self-hosted server\\.</p>#<p class=\"stack-link\"><a href=\"$(escape_sed "$stack_url_html")\">DuneAwakeningSelfHost</a> powers this self-hosted server.</p>#" \
  "$index_file" > "$tmp"

install -m 0644 "$tmp" "$index_file"
rm -f "$tmp"
echo "Updated $index_file"
