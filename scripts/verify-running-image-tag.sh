#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"

if [[ ! -f "$env_file" ]]; then
  printf 'fail: env file not found: %s\n' "$env_file" >&2
  exit 2
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'"'"']|["'"'"']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

expected_tag="$(env_value DUNE_IMAGE_TAG)"
project="$(env_value COMPOSE_PROJECT_NAME)"
project="${project:-dune_server}"

if [[ -z "$expected_tag" ]]; then
  printf 'fail: DUNE_IMAGE_TAG is empty in %s\n' "$env_file" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  printf 'fail: docker is required to verify running image tags\n' >&2
  exit 2
fi

checked=0
mismatches=0
while IFS=$'\t' read -r container_id service; do
  [[ -n "$container_id" ]] || continue
  image="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
  repository="${image%:*}"
  tag="${image##*:}"

  case "$repository:$service" in
    registry.funcom.com/funcom/self-hosting/seabass-server:*) ;;
    registry.funcom.com/funcom/self-hosting/seabass-server-bg-director:director) ;;
    registry.funcom.com/funcom/self-hosting/seabass-server-gateway:gateway) ;;
    registry.funcom.com/funcom/self-hosting/seabass-server-text-router:text-router) ;;
    registry.funcom.com/funcom/self-hosting/seabass-server-db-utils:rmq-auth-shim) ;;
    *) continue ;;
  esac

  checked=$((checked + 1))
  if [[ "$tag" != "$expected_tag" ]]; then
    printf 'running image mismatch: service=%s container=%s running=%s expected_tag=%s\n' \
      "$service" "$container_id" "$image" "$expected_tag"
    mismatches=$((mismatches + 1))
  fi
done < <(
  docker ps \
    --filter "label=com.docker.compose.project=$project" \
    --format '{{.ID}}\t{{.Label "com.docker.compose.service"}}'
)

if [[ "$checked" -eq 0 ]]; then
  printf 'running image mismatch: no live map/control-plane containers found for project=%s\n' "$project"
  exit 1
fi
if [[ "$mismatches" -ne 0 ]]; then
  printf 'running image convergence: mismatch checked=%s mismatches=%s expected_tag=%s\n' \
    "$checked" "$mismatches" "$expected_tag"
  exit 1
fi

printf 'running image convergence: current checked=%s expected_tag=%s\n' "$checked" "$expected_tag"
