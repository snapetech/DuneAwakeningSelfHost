#!/bin/sh
set -eu

message="${1:-PAUL ANNOUNCEMENT VERIFY}"
compose_files="${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"

set -- docker compose
old_ifs="$IFS"
IFS=:
for file in $compose_files; do
  set -- "$@" -f "$file"
done
IFS="$old_ifs"
set -- "$@" --env-file "${ENV_FILE:-.env}"

exec "$@" exec -T admin-panel /workspace/scripts/announce.sh "$message"
