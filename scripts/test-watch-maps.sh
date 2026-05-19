#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fake_runtime="$tmp_dir/fake-runtime"
cat > "$fake_runtime" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

log_file="${FAKE_RUNTIME_LOG:?}"
status_file="${FAKE_RUNTIME_STATUS_FILE:?}"
health_file="${FAKE_RUNTIME_HEALTH_FILE:-}"

printf '%s\n' "$*" >> "$log_file"

if [[ "${1:-}" == "compose" ]]; then
  shift
  service=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -f|--env-file)
        shift 2
        ;;
      *)
        break
        ;;
    esac
  done
  while [[ $# -gt 0 ]]; do
    case "$1" in
      ps)
        shift
        if [[ "${1:-}" == "-q" || "${1:-}" == "-aq" ]]; then
          shift
          service="${1:-}"
          if grep -q "^${service}=" "$status_file"; then
            printf 'fake-%s\n' "$service"
          fi
          exit 0
        fi
        ;;
      exec)
        shift
        while [[ "${1:-}" == -* ]]; do
          shift
        done
        service="${1:-}"
        if [[ "$service" == "postgres" ]]; then
          partition_id="$(printf '%s\n' "$*" | sed -nE 's/.*where wp\.partition_id = ([0-9]+).*/\1/p' | head -1)"
          if [[ -n "$health_file" && -n "$partition_id" ]] && grep -q "^${partition_id}=" "$health_file"; then
            grep "^${partition_id}=" "$health_file" | tail -1 | cut -d= -f2
          else
            printf 't t t\n'
          fi
          exit 0
        fi
        ;;
      *)
        shift
        ;;
    esac
  done
fi

if [[ "${1:-}" == "inspect" ]]; then
  container="${@: -1}"
  service="${container#fake-}"
  grep "^${service}=" "$status_file" | tail -1 | cut -d= -f2
  exit 0
fi

printf 'unsupported fake-runtime command: %s\n' "$*" >&2
exit 1
EOF
chmod +x "$fake_runtime"

log_file="$tmp_dir/runtime.log"
status_file="$tmp_dir/status.txt"
env_file="$tmp_dir/test.env"
touch "$log_file" "$env_file"

cat > "$status_file" <<'EOF'
survival=running
heighliner-dungeon=exited
EOF

health_file="$tmp_dir/health.txt"
cat > "$health_file" <<'EOF'
1=t t t
18=f f f
EOF

status_output="$(
  FAKE_RUNTIME_LOG="$log_file" \
  FAKE_RUNTIME_STATUS_FILE="$status_file" \
  FAKE_RUNTIME_HEALTH_FILE="$health_file" \
  CONTAINER_RUNTIME="$fake_runtime" \
  COMPOSE_FILES=compose.yaml:compose.allmaps.yaml \
  "$repo_root/scripts/watch-maps.sh" "$env_file" --status
)"

if ! grep -q "survival .*status=running.*db=\"t t t\"" <<< "$status_output"; then
  printf 'status output did not report survival running\n' >&2
  exit 1
fi

if ! grep -q "heighliner-dungeon .*status=exited.*db=\"f f f\"" <<< "$status_output"; then
  printf 'status output did not report heighliner-dungeon exited\n' >&2
  exit 1
fi

dry_run_output="$(
  FAKE_RUNTIME_LOG="$log_file" \
  FAKE_RUNTIME_STATUS_FILE="$status_file" \
  FAKE_RUNTIME_HEALTH_FILE="$health_file" \
  CONTAINER_RUNTIME="$fake_runtime" \
  COMPOSE_FILES=compose.yaml:compose.allmaps.yaml \
  DUNE_WATCH_STARTUP_GRACE=0 \
  "$repo_root/scripts/watch-maps.sh" "$env_file" --dry-run
)"

if ! grep -q "would recover map: service=heighliner-dungeon partition=18 reason=exited" <<< "$dry_run_output"; then
  printf 'dry-run output did not report heighliner-dungeon recovery\n' >&2
  exit 1
fi

if grep -q "recover-map" "$log_file"; then
  printf 'dry-run attempted to invoke recovery\n' >&2
  exit 1
fi

cat > "$status_file" <<'EOF'
survival=running
heighliner-dungeon=running
EOF

cat > "$health_file" <<'EOF'
1=t t t
18=t t f
EOF

degraded_output="$(
  FAKE_RUNTIME_LOG="$log_file" \
  FAKE_RUNTIME_STATUS_FILE="$status_file" \
  FAKE_RUNTIME_HEALTH_FILE="$health_file" \
  CONTAINER_RUNTIME="$fake_runtime" \
  COMPOSE_FILES=compose.yaml:compose.allmaps.yaml \
  DUNE_WATCH_STARTUP_GRACE=0 \
  "$repo_root/scripts/watch-maps.sh" "$env_file" --dry-run
)"

if ! grep -q "would recover map: service=heighliner-dungeon partition=18 reason=not_active" <<< "$degraded_output"; then
  printf 'dry-run output did not report degraded heighliner-dungeon recovery\n' >&2
  exit 1
fi

printf 'watch-maps tests passed\n'
