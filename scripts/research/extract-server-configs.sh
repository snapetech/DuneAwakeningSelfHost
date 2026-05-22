#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
service="${2:-deep-desert}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")

paths=(
  /home/dune/server/DuneSandbox/Config/DefaultGame.ini
  /home/dune/server/DuneSandbox/Config/DedicatedServerGame.ini
  /home/dune/server/DuneSandbox/Config/DefaultEngine.ini
  /home/dune/server/DuneSandbox/Saved/UserSettings/UserGame.ini
  /home/dune/server/DuneSandbox/Saved/UserSettings/UserEngine.ini
)

for path in "${paths[@]}"; do
  printf '===== %s =====\n' "$path"
  "${compose[@]}" exec -T "$service" sh -lc "test -f '$path' && sed -n '1,260p' '$path' || true"
done
