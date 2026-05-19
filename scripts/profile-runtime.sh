#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/profile-runtime.sh [env-file]

Writes a local runtime profile under captures/. The profile is intended to find
memory, storage, network, and process-level optimization targets without
modifying Funcom binaries or images.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

if ! command -v "$container_runtime" >/dev/null 2>&1; then
  printf '%s is required\n' "$container_runtime" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="captures/${timestamp}-runtime-profile"
mkdir -p "$out_dir"

cat > "$out_dir/README.txt" <<EOF
Runtime profile
Captured UTC: ${timestamp}

This directory is local-only and ignored by git. Review before sharing; profile
outputs can contain container names, image digests, paths, addresses, and world
or service identifiers.
EOF

capture() {
  local name="$1"
  shift
  {
    printf '# %s\n' "$name"
    printf '# captured_at=%s\n\n' "$timestamp"
    "$@"
  } >"$out_dir/$name.txt" 2>&1 || true
  redact_file "$out_dir/$name.txt"
}

redact_file() {
  local file="$1"
  sed -E -i \
    -e 's/(ServiceAuthToken=)[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(ServiceAuthToken: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(gateway_farm_api_key: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/([A-Za-z0-9_]*([Pp]assword|PASSWORD|[Ss]ecret|SECRET|[Tt]oken|TOKEN|[Aa]pi[Kk]ey|api_key)[A-Za-z0-9_]*: )[A-Za-z0-9_.+\/=-]+/\1[redacted]/g' \
    -e 's/([A-Za-z0-9_]*([Pp]assword|PASSWORD|[Ss]ecret|SECRET|[Tt]oken|TOKEN|[Aa]pi[Kk]ey|api_key)[A-Za-z0-9_]*=)[A-Za-z0-9_.+\/=-]+/\1[redacted]/g' \
    -e 's/(DatabasePassword=)[^ ]+/\1[redacted]/g' \
    -e 's/(DuneDatabaseInterfacePSQL_DatabasePassword: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(POSTGRES_[A-Z_]*PASSWORD: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(RMQ_HTTP_TOKEN_AUTH_SECRET: )[A-Za-z0-9_.-]+/\1[redacted]/g' \
    -e 's/(Password=)[^; ]+/\1[redacted]/g' \
    -e 's#(sg\.sh-[^/ ]+/)[A-Za-z0-9+/=_-]+#\1[redacted]#g' \
    -e 's#(sg|bgd|tr)\.sh-[A-Za-z0-9_.+/-]+#\1.sh-[redacted]#g' \
    -e 's/sh-[0-9a-fA-F]{16}-[A-Za-z0-9]+/sh-[redacted]/g' \
    "$file"
}

container_ids="$("${compose[@]}" ps -q 2>/dev/null || true)"

capture compose-ps "${compose[@]}" ps
capture compose-top "${compose[@]}" top
capture compose-images "${compose[@]}" images
capture compose-config "${compose[@]}" config

if [[ -n "$container_ids" ]]; then
  capture container-stats "$container_runtime" stats --no-stream --format \
    'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}' \
    $container_ids

  capture container-inspect "$container_runtime" inspect \
    --format 'name={{.Name}} image={{.Config.Image}} status={{.State.Status}} pid={{.State.Pid}} restart_count={{.RestartCount}} oom_killed={{.State.OOMKilled}} ports={{json .NetworkSettings.Ports}} mounts={{json .Mounts}}' \
    $container_ids

  capture container-processes bash -c '
    runtime="$1"
    shift
    for id in "$@"; do
      name="$("$runtime" inspect --format "{{.Name}}" "$id" 2>/dev/null | sed "s#^/##")"
      printf "\n## %s\n" "$name"
      "$runtime" exec "$id" sh -lc "ps -eo pid,ppid,rss,vsz,pcpu,pmem,args --sort=-rss 2>/dev/null || ps -o pid,ppid,rss,vsz,args 2>/dev/null || ps" 2>&1 | head -80 || true
    done
  ' _ "$container_runtime" $container_ids

  capture container-filesystems bash -c '
    runtime="$1"
    shift
    for id in "$@"; do
      name="$("$runtime" inspect --format "{{.Name}}" "$id" 2>/dev/null | sed "s#^/##")"
      printf "\n## %s\n" "$name"
      "$runtime" exec "$id" sh -lc "df -h; printf \"\nTop writable-ish dirs:\n\"; du -xh -d 2 /tmp /var /home 2>/dev/null | sort -h | tail -40" 2>&1 || true
    done
  ' _ "$container_runtime" $container_ids

  capture container-memory-detail bash -c '
    runtime="$1"
    shift
    for id in "$@"; do
      name="$("$runtime" inspect --format "{{.Name}}" "$id" 2>/dev/null | sed "s#^/##")"
      printf "\n## %s\n" "$name"
      "$runtime" exec "$id" sh -lc '"'"'
        for status in /proc/[0-9]*/status; do
          pid="${status#/proc/}"
          pid="${pid%/status}"
          name="$(awk "/^Name:/ {print \$2; exit}" "$status" 2>/dev/null)"
          rss="$(awk "/^VmRSS:/ {print \$2 \" \" \$3; exit}" "$status" 2>/dev/null)"
          hwm="$(awk "/^VmHWM:/ {print \$2 \" \" \$3; exit}" "$status" 2>/dev/null)"
          pss=""
          if [ -r "/proc/$pid/smaps_rollup" ]; then
            pss="$(awk "/^Pss:/ {print \$2 \" \" \$3; exit}" "/proc/$pid/smaps_rollup" 2>/dev/null)"
          fi
          [ -n "$rss$hwm$pss" ] && printf "pid=%s name=%s rss=%s hwm=%s pss=%s\n" "$pid" "$name" "$rss" "$hwm" "$pss"
        done
      '"'"' 2>&1 || true
    done
  ' _ "$container_runtime" $container_ids

  capture container-sockets bash -c '
    runtime="$1"
    shift
    for id in "$@"; do
      name="$("$runtime" inspect --format "{{.Name}}" "$id" 2>/dev/null | sed "s#^/##")"
      printf "\n## %s\n" "$name"
      "$runtime" exec "$id" sh -lc "ss -tunap 2>/dev/null || netstat -tunap 2>/dev/null || true" 2>&1 || true
    done
  ' _ "$container_runtime" $container_ids
fi

mapfile -t images < <("${compose[@]}" config --images 2>/dev/null | sort -u || true)
if [[ "${#images[@]}" -gt 0 ]]; then
  capture image-sizes bash -c '
    runtime="$1"
    shift
    for image in "$@"; do
      "$runtime" images --format "{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}" "$image"
    done
  ' _ "$container_runtime" "${images[@]}"
  for image in "${images[@]}"; do
    safe_image="$(printf '%s' "$image" | tr -cs 'A-Za-z0-9._-' '-')"
    capture "image-history-${safe_image}" "$container_runtime" history --no-trunc "$image"
  done
fi

printf 'runtime profile written: %s\n' "$out_dir"
