#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/map-memory-squeeze.sh ACTION SERVICE [ARGS...]

Manages a running game-map container's cgroup v2 memory.high ceiling so an
idle map's resident memory is reclaimed (and swapped out) while the process
keeps running, instead of stopping the container. This is the primitive
behind the "swap-warm" idle policy: warm/always-on maps are never squeezed,
dynamic maps get squeezed on idle instead of stopped, and unsqueezed the
moment demand returns.

Actions:
  squeeze SERVICE [HIGH_MIB]         Set memory.high to HIGH_MIB (default:
                                      DUNE_MEMORY_SQUEEZE_HIGH_MIB or 256).
  restore SERVICE                    Set memory.high back to max (unsqueeze).
  status SERVICE                     Print current/swap/high, no change.
  watch SERVICE SECONDS INTERVAL     Sample current/swap every INTERVAL
                                      seconds for SECONDS total. No change.

All actions append a timestamped line to the log file and print the same
line to stdout, so a single invocation is enough evidence to review later
without re-running commands interactively.

Environment:
  DUNE_MEMORY_SQUEEZE_HIGH_MIB    Default squeeze ceiling in MiB. Default: 256
  DUNE_RESTART_COMPOSE_PROJECT    Compose project name. Default: dune_server
  DUNE_MEMORY_SQUEEZE_LOG         Log file. Default:
                                   <repo>/backups/memory-squeeze/memory-squeeze.log
  DUNE_MEMORY_SQUEEZE_SUDO        Set false/0/no/off to avoid sudo fallback.
USAGE
}

if [[ $# -lt 2 ]]; then
  usage
  exit 2
fi

action="$1"
service="$2"
shift 2

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="${DUNE_RESTART_COMPOSE_PROJECT:-dune_server}"
log_file="${DUNE_MEMORY_SQUEEZE_LOG:-$repo_root/backups/memory-squeeze/memory-squeeze.log}"
default_high_mib="${DUNE_MEMORY_SQUEEZE_HIGH_MIB:-256}"

case "$action" in
  squeeze|restore|status|watch) ;;
  *)
    usage
    exit 2
    ;;
esac

log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) [$service] $*"
  printf '%s\n' "$line"
  mkdir -p "$(dirname "$log_file")"
  printf '%s\n' "$line" >> "$log_file"
}

sudo_prefix() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    return 0
  fi
  case "${DUNE_MEMORY_SQUEEZE_SUDO:-true}" in
    0|false|no|off)
      printf 'DUNE_MEMORY_SQUEEZE_SUDO is disabled and process is not root\n' >&2
      exit 1
      ;;
  esac
  if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
    printf 'passwordless sudo is required to read/write cgroup memory files\n' >&2
    exit 1
  fi
}

cgroup_path() {
  local container_id
  container_id="$(docker inspect -f '{{.Id}}' "${project}-${service}-1" 2>/dev/null)" || true
  if [[ -z "$container_id" ]]; then
    printf 'no running container found for service %s (project %s)\n' "$service" "$project" >&2
    exit 1
  fi
  local path="/sys/fs/cgroup/system.slice/docker-${container_id}.scope"
  if [[ ! -d "$path" ]]; then
    printf 'cgroup path not found (expected cgroup v2 systemd layout): %s\n' "$path" >&2
    exit 1
  fi
  printf '%s\n' "$path"
}

read_file() {
  sudo_prefix
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    cat "$1"
  else
    sudo cat "$1"
  fi
}

write_file() {
  sudo_prefix
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    printf '%s\n' "$2" > "$1"
  else
    printf '%s\n' "$2" | sudo tee "$1" >/dev/null
  fi
}

report() {
  local cg="$1"
  local cur swap high cur_mib swap_mib
  cur="$(read_file "$cg/memory.current")"
  swap="$(read_file "$cg/memory.swap.current")"
  high="$(read_file "$cg/memory.high")"
  cur_mib=$((cur / 1024 / 1024))
  swap_mib=$((swap / 1024 / 1024))
  log "current=${cur_mib}MiB swap=${swap_mib}MiB high=${high}"
}

cg="$(cgroup_path)"

case "$action" in
  squeeze)
    high_mib="${1:-$default_high_mib}"
    log "squeezing: setting memory.high=${high_mib}M"
    write_file "$cg/memory.high" "${high_mib}M"
    report "$cg"
    ;;
  restore)
    log "restoring: setting memory.high=max"
    write_file "$cg/memory.high" "max"
    report "$cg"
    ;;
  status)
    report "$cg"
    ;;
  watch)
    seconds="${1:?watch requires SECONDS}"
    interval="${2:?watch requires INTERVAL}"
    elapsed=0
    while (( elapsed < seconds )); do
      sleep "$interval"
      elapsed=$((elapsed + interval))
      report "$cg"
    done
    ;;
esac
