#!/usr/bin/env bash
set -euo pipefail

directory_root="${DIRECTORY_ROOT:-/srv/dash-public-site/directory}"
sources_file="${DIRECTORY_SOURCES_FILE:-/etc/dash-directory-sources.json}"
timeout="${DIRECTORY_TIMEOUT_SECONDS:-5}"
workers="${DIRECTORY_WORKERS:-8}"
builder="${DIRECTORY_BUILDER:-/usr/local/sbin/build-federated-directory.py}"

[[ "$directory_root" == /* && "$sources_file" == /* ]] || { echo "directory paths must be absolute" >&2; exit 2; }
[[ -r "$sources_file" ]] || { echo "directory sources file is unreadable: $sources_file" >&2; exit 2; }
[[ "$timeout" =~ ^[0-9]+$ && "$workers" =~ ^[0-9]+$ ]] || { echo "directory timeout and workers must be integers" >&2; exit 2; }
(( timeout >= 1 && timeout <= 15 && workers >= 1 && workers <= 32 )) || { echo "directory timeout or workers are outside safe bounds" >&2; exit 2; }

install -d -m 0755 "$directory_root"
exec "$builder" \
  --sources "$sources_file" \
  --output "$directory_root/directory.json" \
  --timeout "$timeout" \
  --workers "$workers"
