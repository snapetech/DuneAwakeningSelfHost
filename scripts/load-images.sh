#!/usr/bin/env bash
set -euo pipefail

server_dir="${DUNE_STEAM_SERVER_DIR:-$HOME/.local/share/Steam/steamapps/common/Dune Awakening Self-Hosted Server}"

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
