#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/swap-warm-daemon.sh [ENV_FILE]

Keeps DUNE_SWAP_WARM_SERVICES running continuously (they must already be in
autoscaler mode always-on, see scripts/enable-swap-warm-fleet.sh) but squeezes
an idle map's resident memory into swap via scripts/map-memory-squeeze.sh
instead of stopping the container. The moment a map has a player, is active,
or has a Director demand lease, it is restored (unsqueezed) immediately; the
kernel then pages the process's working set back in on its own via normal
page faults as it resumes handling the map.

This trades the 90-300+ second cold container boot for a swap-in that is
bounded by NVMe page-fault latency instead of Unreal Engine cold init, while
letting idle maps fall to a small resident footprint instead of full RSS.

This whole subsystem is optional and off by default. DUNE_SWAP_WARM_ENABLED is
re-read from ENV_FILE every cycle (no restart needed to flip it). While
disabled, any map this daemon had squeezed is restored to full memory.high
first, then every cycle is a no-op -- the process stays running under
systemd (Restart=always) but does nothing, so toggling the flag is instant
and never crash-loops.

Environment:
  DUNE_SWAP_WARM_ENABLED             Master switch. Default: false
  DUNE_SWAP_WARM_SERVICES            Comma-separated service list to manage.
                                      No default; a warning is logged once and
                                      the daemon idles if empty while enabled.
  DUNE_SWAP_WARM_RETENTION_SECONDS   Idle seconds (zero players/active/demand)
                                      before squeezing. Default: 120
  DUNE_SWAP_WARM_MIN_HOLD_SECONDS    Minimum seconds a map stays fully resident
                                      after being restored before it is
                                      eligible to be squeezed again, even if it
                                      goes idle sooner. Prevents rapid
                                      squeeze/restore flapping from brief,
                                      intermittent visits. Default: 1800 (30
                                      minutes). Does not apply to a map's first
                                      squeeze -- only after an actual restore.
  DUNE_SWAP_WARM_HIGH_MIB            Squeeze ceiling in MiB. Default: 256
  DUNE_SWAP_WARM_POLL_SECONDS        Reconcile cadence. Default: 10
  DUNE_SWAP_WARM_LOG                 Log file. Default:
                                      <repo>/backups/memory-squeeze/swap-warm-daemon.log
USAGE
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
env_file="${1:-${ENV_FILE:-.env}}"

env_file_value() {
  local key="$1"
  local value="${!key:-}"
  if [[ -n "$value" ]]; then
    printf '%s\n' "$value"
    return 0
  fi
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\''"]|["'\''"]$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null || true
}

services_raw="$(env_file_value DUNE_SWAP_WARM_SERVICES)"
retention_seconds="$(env_file_value DUNE_SWAP_WARM_RETENTION_SECONDS)"
retention_seconds="${retention_seconds:-120}"
min_hold_seconds="$(env_file_value DUNE_SWAP_WARM_MIN_HOLD_SECONDS)"
min_hold_seconds="${min_hold_seconds:-1800}"
high_mib="$(env_file_value DUNE_SWAP_WARM_HIGH_MIB)"
high_mib="${high_mib:-256}"
poll_seconds="$(env_file_value DUNE_SWAP_WARM_POLL_SECONDS)"
poll_seconds="${poll_seconds:-10}"
log_file="$(env_file_value DUNE_SWAP_WARM_LOG)"
log_file="${log_file:-$repo_root/backups/memory-squeeze/swap-warm-daemon.log}"

log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
  printf '%s\n' "$line"
  mkdir -p "$(dirname "$log_file")"
  printf '%s\n' "$line" >> "$log_file"
}

log "starting: enabled-flag=DUNE_SWAP_WARM_ENABLED services=${services_raw:-<empty>} retention=${retention_seconds}s min-hold=${min_hold_seconds}s high=${high_mib}MiB poll=${poll_seconds}s"

IFS=',' read -r -a services <<< "$services_raw"

declare -A last_active
declare -A squeezed
declare -A restored_at
declare -A warned_hold
now_epoch="$(date +%s)"
for svc in "${services[@]}"; do
  svc="$(printf '%s' "$svc" | xargs)"
  [[ -n "$svc" ]] || continue
  last_active["$svc"]="$now_epoch"
  squeezed["$svc"]="0"
done

last_enabled=""
while true; do
  enabled_raw="$(env_file_value DUNE_SWAP_WARM_ENABLED)"
  case "${enabled_raw,,}" in
    1|true|yes|on) enabled="true" ;;
    *) enabled="false" ;;
  esac

  if [[ "$enabled" != "$last_enabled" ]]; then
    log "DUNE_SWAP_WARM_ENABLED is now ${enabled}"
    last_enabled="$enabled"
  fi

  if [[ "$enabled" != "true" ]]; then
    for svc in "${services[@]}"; do
      svc="$(printf '%s' "$svc" | xargs)"
      [[ -n "$svc" ]] || continue
      if [[ "${squeezed[$svc]:-0}" == "1" ]]; then
        log "disabled, restoring ${svc} before idling"
        ./scripts/map-memory-squeeze.sh restore "$svc" || true
        squeezed["$svc"]="0"
      fi
    done
    sleep "$poll_seconds"
    continue
  fi

  if [[ -z "$services_raw" ]]; then
    if [[ "${warned_empty:-0}" != "1" ]]; then
      log "enabled but DUNE_SWAP_WARM_SERVICES is empty; idling until it is set"
      warned_empty=1
    fi
    sleep "$poll_seconds"
    continue
  fi

  hot_pairs="$(
    ./scripts/capacity-intelligence.py status 2>/dev/null | python3 -c '
import json, sys
managed = set(s.strip() for s in sys.argv[1].split(",") if s.strip())
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for m in d.get("maps", []):
    svc = m.get("service")
    if svc not in managed:
        continue
    hot = bool(m.get("players") or m.get("active") or m.get("demanded"))
    print(f"{svc}|{1 if hot else 0}")
' "$services_raw" 2>/dev/null || true
  )"

  if [[ -n "$hot_pairs" ]]; then
    now_epoch="$(date +%s)"
    while IFS='|' read -r svc hot; do
      [[ -n "$svc" ]] || continue
      if [[ "$hot" == "1" ]]; then
        last_active["$svc"]="$now_epoch"
        if [[ "${squeezed[$svc]:-0}" == "1" ]]; then
          log "demand detected, restoring ${svc}"
          ./scripts/map-memory-squeeze.sh restore "$svc" || true
          squeezed["$svc"]="0"
          restored_at["$svc"]="$now_epoch"
        fi
      else
        idle_for=$(( now_epoch - ${last_active[$svc]:-now_epoch} ))
        held_for=$(( now_epoch - ${restored_at[$svc]:-0} ))
        if (( idle_for >= retention_seconds )) && [[ "${squeezed[$svc]:-0}" != "1" ]]; then
          if [[ -n "${restored_at[$svc]:-}" ]] && (( held_for < min_hold_seconds )); then
            if [[ "${warned_hold[$svc]:-0}" != "1" ]]; then
              log "idle ${idle_for}s >= ${retention_seconds}s but ${svc} was only restored ${held_for}s ago (< ${min_hold_seconds}s min hold), keeping it resident"
              warned_hold["$svc"]="1"
            fi
          else
            log "idle ${idle_for}s >= ${retention_seconds}s, squeezing ${svc}"
            if ./scripts/map-memory-squeeze.sh squeeze "$svc" "$high_mib"; then
              squeezed["$svc"]="1"
              warned_hold["$svc"]="0"
            else
              log "squeeze failed for ${svc} (container not up?), will retry next cycle"
            fi
          fi
        fi
      fi
    done <<< "$hot_pairs"
  fi

  sleep "$poll_seconds"
done
