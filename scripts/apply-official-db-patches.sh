#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/apply-official-db-patches.sh [env-file]

Applies missing official Funcom database upgrade patches from the currently
configured seabass-server image before map startup.
USAGE
}

env_file="${1:-.env}"
case "$env_file" in
  -h|--help)
    usage
    exit 0
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'fail: env file not found: %s\n' "$env_file" >&2
  exit 1
fi

get_env() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

image_tag="${DUNE_IMAGE_TAG:-$(get_env DUNE_IMAGE_TAG)}"
if [[ -z "$image_tag" ]]; then
  printf 'fail: DUNE_IMAGE_TAG is empty\n' >&2
  exit 1
fi

server_image="${DUNE_DB_PATCH_SOURCE_IMAGE:-registry.funcom.com/funcom/self-hosting/seabass-server:$image_tag}"
db_name="${DUNE_GAME_DB_NAME:-dune_sb_1_4_0_0}"
patch_root="/home/dune/server/DuneSandbox/Database/Upgrade"

if ! command -v docker >/dev/null 2>&1; then
  printf 'fail: docker is required to read official DB patches from %s\n' "$server_image" >&2
  exit 127
fi

if ! docker image inspect "$server_image" >/dev/null 2>&1; then
  printf 'fail: official server image is not loaded: %s\n' "$server_image" >&2
  exit 1
fi

if [[ -x ./scripts/compose-files.sh ]]; then
  COMPOSE_FILES="$(./scripts/compose-files.sh "$env_file")"
  export COMPOSE_FILES
fi

compose=(docker compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

docker run --rm --entrypoint cat "$server_image" "$patch_root/__order.txt" \
  | sed -E '/^[[:space:]]*($|#)/d; s/[[:space:]]+$//' >"$tmp_dir/order"

"${compose[@]}" exec -T postgres psql -U dune -d "$db_name" -Atc \
  "select name from dune.applied_patches order by name;" >"$tmp_dir/applied"

missing=()
while IFS= read -r patch; do
  [[ -n "$patch" ]] || continue
  if ! [[ "$patch" =~ ^[A-Za-z0-9_-]+$ ]]; then
    printf 'fail: unsafe official patch name in __order.txt: %s\n' "$patch" >&2
    exit 1
  fi
  if ! grep -Fxq "$patch" "$tmp_dir/applied"; then
    missing+=("$patch")
  fi
done <"$tmp_dir/order"

if [[ "${#missing[@]}" -eq 0 ]]; then
  printf 'official DB patches current for %s\n' "$image_tag"
  exit 0
fi

printf 'applying %s official DB patch(es) for %s\n' "${#missing[@]}" "$image_tag"
for patch in "${missing[@]}"; do
  printf 'applying official DB patch: %s\n' "$patch"
  docker run --rm --entrypoint cat "$server_image" "$patch_root/$patch.sql" \
    | "${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U dune -d "$db_name" \
        -c "set search_path to dune, public;" -f -
  "${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U dune -d "$db_name" \
    -c "insert into dune.applied_patches(name, date) values ('$patch', now()) on conflict (name) do nothing;"
done

printf 'official DB patch application complete\n'
