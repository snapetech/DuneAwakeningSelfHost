#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/load-images.sh [env-file]

Loads the official Funcom image tarballs from DUNE_STEAM_SERVER_DIR. When an
env file is provided, DUNE_STEAM_SERVER_DIR is read from that file unless it is
already set in the process environment.
USAGE
}

env_file="${1:-}"
case "$env_file" in
  -h|--help)
    usage
    exit 0
    ;;
esac
if [[ -n "$env_file" && ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

get_env() {
  local key="$1"
  local file="$2"
  [[ -f "$file" ]] || return 0
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$file"
}

server_dir="${DUNE_STEAM_SERVER_DIR:-}"
if [[ -z "$server_dir" && -n "$env_file" ]]; then
  server_dir="$(get_env DUNE_STEAM_SERVER_DIR "$env_file")"
fi
server_dir="${server_dir:-$HOME/.local/share/Steam/steamapps/common/Dune Awakening Self-Hosted Server}"

images=(
  "images/battlegroup/server-rabbitmq.tar"
  "images/battlegroup/server-text-router.tar"
  "images/battlegroup/server-bg-director.tar"
  "images/battlegroup/server-gateway.tar"
  "images/battlegroup/server-db-utils.tar"
  "images/battlegroup/server.tar"
  "images/prerequisites/igw-postgres.tar"
)

for image in "${images[@]}"; do
  path="$server_dir/$image"
  if [[ ! -f "$path" ]]; then
    echo "missing image tar: $path" >&2
    exit 1
  fi
  docker load -i "$path"
done
