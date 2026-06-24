#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
seconds="${2:-300}"
poll_interval="${DUNE_CLIENT_BROWSER_PING_WATCH_POLL_SECONDS:-2}"

find_client_log() {
  if [[ -n "${DUNE_CLIENT_LOG:-}" ]]; then
    printf '%s' "$DUNE_CLIENT_LOG"
    return 0
  fi
  local steam_root="${STEAM_ROOT:-$HOME/.steam/steam}"
  local candidate="$steam_root/steamapps/compatdata/1172710/pfx/drive_c/users/steamuser/AppData/Local/DuneSandbox/Saved/Logs/DuneSandbox.log"
  if [[ -f "$candidate" ]]; then
    printf '%s' "$candidate"
    return 0
  fi
  find "$steam_root/steamapps/compatdata/1172710" -path '*/DuneSandbox/Saved/Logs/DuneSandbox.log' -type f -print 2>/dev/null | head -1
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi
case "$seconds" in
  ''|*[!0-9]*)
    printf 'seconds must be a positive integer\n' >&2
    exit 2
    ;;
esac
case "$poll_interval" in
  ''|*[!0-9]*)
    printf 'DUNE_CLIENT_BROWSER_PING_WATCH_POLL_SECONDS must be a positive integer\n' >&2
    exit 2
    ;;
esac

client_log="$(find_client_log || true)"
if [[ -z "$client_log" ]]; then
  printf 'WARN Dune client log not found yet. Set DUNE_CLIENT_LOG=/path/to/DuneSandbox.log if needed.\n'
  client_log=""
fi

start_epoch="$(date +%s)"
deadline=$((start_epoch + seconds))
initial_epoch=0
if [[ -n "$client_log" && -f "$client_log" ]]; then
  initial_epoch="$(stat -c %Y "$client_log")"
fi

printf 'watching for a fresh Dune browser/client log update for %s seconds\n' "$seconds"
printf 'env_file=%s\n' "$env_file"
printf 'client_log=%s\n' "${client_log:-unresolved}"
if [[ "$initial_epoch" != "0" ]]; then
  printf 'initial_log_mtime=%s\n' "$(date -d "@$initial_epoch" '+%Y-%m-%d %H:%M:%S %z')"
fi
printf 'No packet capture is used by this watcher.\n'

while (( "$(date +%s)" <= deadline )); do
  if [[ -z "$client_log" || ! -f "$client_log" ]]; then
    client_log="$(find_client_log || true)"
    sleep "$poll_interval"
    continue
  fi

  current_epoch="$(stat -c %Y "$client_log")"
  if (( current_epoch > initial_epoch && current_epoch >= start_epoch )); then
    printf '\nclient log updated: %s\n' "$(date -d "@$current_epoch" '+%Y-%m-%d %H:%M:%S %z')"
    DUNE_CLIENT_BROWSER_PING_FIX_EPOCH="$start_epoch" \
      DUNE_CLIENT_BROWSER_PING_FIX_LABEL="watch start" \
      "${DUNE_CLIENT_BROWSER_PING_VERIFIER:-./scripts/client-browser-ping-verifier.sh}" "$env_file"
    exit 0
  fi
  sleep "$poll_interval"
done

printf 'TIMEOUT no fresh Dune client log update observed within %s seconds.\n' "$seconds"
exit 124
