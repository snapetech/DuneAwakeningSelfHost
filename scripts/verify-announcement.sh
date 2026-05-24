#!/bin/sh
set -eu

message="${1:-PAUL ANNOUNCEMENT VERIFY}"
env_file="${ENV_FILE:-.env}"
script_dir="$(dirname "$0")"
if [ -x "$script_dir/compose-files.sh" ]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi
compose_files="${COMPOSE_FILES:-compose.yaml:compose.allmaps.yaml}"

set -- docker compose
old_ifs="$IFS"
IFS=:
for file in $compose_files; do
  set -- "$@" -f "$file"
done
IFS="$old_ifs"
set -- "$@" --env-file "$env_file"

exec "$@" exec -T admin-panel /workspace/scripts/announce.sh "$message"
