#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/check-steam-update.sh [env-file] [--write-env]

Compare DUNE_IMAGE_TAG with the image tags shipped in the local Steam-installed
Dune: Awakening Self-Hosted Server package. By default this is read-only.

Options:
  --write-env   Update DUNE_IMAGE_TAG in the env file when exactly one package
                server tag is found.
EOF
}

env_file=".env"
write_env=false

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    --write-env)
      write_env=true
      ;;
    *)
      env_file="$arg"
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

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

image_tars=(
  "images/battlegroup/server-rabbitmq.tar"
  "images/battlegroup/server-text-router.tar"
  "images/battlegroup/server-bg-director.tar"
  "images/battlegroup/server-gateway.tar"
  "images/battlegroup/server-db-utils.tar"
  "images/battlegroup/server.tar"
)

if [[ ! -f "$env_file" ]]; then
  echo "fail: env file not found: $env_file" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "fail: jq is required" >&2
  exit 1
fi

steam_dir="$(get_env DUNE_STEAM_SERVER_DIR)"
current_tag="$(get_env DUNE_IMAGE_TAG)"

if [[ -z "$steam_dir" ]]; then
  echo "fail: DUNE_STEAM_SERVER_DIR is empty" >&2
  exit 1
fi

if [[ ! -d "$steam_dir" ]]; then
  echo "fail: DUNE_STEAM_SERVER_DIR does not exist: $steam_dir" >&2
  exit 1
fi

tmp_tags="$(mktemp)"
trap 'rm -f "$tmp_tags"' EXIT

missing=0
for rel in "${image_tars[@]}"; do
  path="$steam_dir/$rel"
  if [[ ! -f "$path" ]]; then
    echo "warn: missing package image tar: $path" >&2
    missing=$((missing + 1))
    continue
  fi

  if ! tar -xOf "$path" manifest.json 2>/dev/null |
    jq -r '.[]?.RepoTags[]? | select(startswith("registry.funcom.com/funcom/self-hosting/seabass-server")) | split(":")[-1]' >>"$tmp_tags"; then
    echo "warn: could not read Docker manifest from $path" >&2
  fi
done

mapfile -t package_tags < <(sort -u "$tmp_tags")

printf 'env file: %s\n' "$env_file"
printf 'Steam server dir: %s\n' "$steam_dir"
printf 'current DUNE_IMAGE_TAG: %s\n' "${current_tag:-unset}"

if [[ "${#package_tags[@]}" -eq 0 ]]; then
  echo "package server tags: none found"
  echo "status: unable to determine package tag"
  exit 2
fi

printf 'package server tags:\n'
printf '  %s\n' "${package_tags[@]}"

if [[ "$missing" -gt 0 ]]; then
  echo "status: incomplete Steam package image set"
  exit 2
fi

if [[ "${#package_tags[@]}" -gt 1 ]]; then
  echo "status: multiple server tags found; update DUNE_IMAGE_TAG manually"
  exit 2
fi

package_tag="${package_tags[0]}"

if [[ "$current_tag" == "$package_tag" ]]; then
  echo "status: current"
  exit 0
fi

echo "status: update available"
echo "next tag: $package_tag"
echo "next steps:"
echo "  ./scripts/load-images.sh"
echo "  ./scripts/check-steam-update.sh $env_file --write-env"
echo "  docker compose --env-file $env_file config --quiet"
echo "  ./scripts/backup-state.sh $env_file"

if [[ "$write_env" == true ]]; then
  if rg -q '^DUNE_IMAGE_TAG=' "$env_file"; then
    sed -i "s/^DUNE_IMAGE_TAG=.*/DUNE_IMAGE_TAG=$package_tag/" "$env_file"
  else
    printf '\nDUNE_IMAGE_TAG=%s\n' "$package_tag" >>"$env_file"
  fi
  echo "updated $env_file: DUNE_IMAGE_TAG=$package_tag"
fi

exit 1
