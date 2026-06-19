#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/brt-dd-runtime-canary.sh status|apply|revert [CONTAINER]

Applies or reverts the current-build DD BRT failure-reason runtime canary in a
running map process. This writes process memory only; it does not modify the
container binary on disk and is lost on container restart.
USAGE
}

action="${1:-}"
container="${2:-dune_server-deep-desert-1}"
required_host="${DUNE_BRT_DD_RUNTIME_CANARY_HOST:-kspls0}"
offset="${DUNE_BRT_DD_FAILURE_REASON_OFFSET:-0xe04e81e}"

if [[ -z "$action" || "$action" == "-h" || "$action" == "--help" ]]; then
  usage
  exit 0
fi

case "$action" in
  status|apply|revert) ;;
  *)
    usage
    exit 2
    ;;
esac

host_short="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$host_short" != "$required_host" && "${DUNE_BRT_DD_RUNTIME_CANARY_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  printf 'refusing runtime canary on host %s; required %s\n' "${host_short:-unknown}" "$required_host" >&2
  exit 1
fi

pid="$(docker top "$container" -eo pid,args 2>/dev/null | awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}')"
if [[ -z "$pid" ]]; then
  printf 'no Dune server process found for %s\n' "$container" >&2
  exit 1
fi

base="$(sudo -n awk '/DuneSandboxServer-Linux-Shipping/ && /r-xp/ {split($1,a,"-"); print "0x" a[1]; exit}' "/proc/$pid/maps")"
if [[ -z "$base" ]]; then
  printf 'could not resolve executable mapping base for pid %s\n' "$pid" >&2
  exit 1
fi

addr="$(python3 - "$base" "$offset" <<'PY'
import sys
print(hex(int(sys.argv[1], 16) + int(sys.argv[2], 16)))
PY
)"

read_bytes() {
  sudo -n gdb -q -nx -batch -p "$pid" \
    -ex "set pagination off" \
    -ex "printf \"BYTES %02x %02x %02x\\n\", *(unsigned char*)$addr, *(unsigned char*)($addr+1), *(unsigned char*)($addr+2)" \
    -ex detach \
    -ex quit 2>/dev/null |
    awk '/^BYTES / {print $2, $3, $4; found=1} END {if (!found) exit 1}'
}

write_third_byte() {
  local value="$1"
  sudo -n gdb -q -nx -batch -p "$pid" \
    -ex "set pagination off" \
    -ex "set {unsigned char}($addr+2) = $value" \
    -ex detach \
    -ex quit >/dev/null
}

bytes="$(read_bytes)"
printf 'container=%s pid=%s base=%s offset=%s addr=%s bytes=%s\n' "$container" "$pid" "$base" "$offset" "$addr" "$bytes"

case "$bytes" in
  "41 b6 32") state=original ;;
  "41 b6 03") state=patched ;;
  "cc b6 32") state=original_uprobe ;;
  "cc b6 03") state=patched_uprobe ;;
  *)
    printf 'unexpected bytes at %s: %s; refusing to write\n' "$addr" "$bytes" >&2
    exit 1
    ;;
esac

case "$action" in
  status)
    printf 'state=%s\n' "$state"
    ;;
  apply)
    if [[ "$state" == "patched" || "$state" == "patched_uprobe" ]]; then
      printf 'already patched\n'
      exit 0
    fi
    write_third_byte 0x03
    printf 'patched runtime failure reason byte: 0x32 -> 0x03\n'
    ;;
  revert)
    if [[ "$state" == "original" || "$state" == "original_uprobe" ]]; then
      printf 'already original\n'
      exit 0
    fi
    write_third_byte 0x32
    printf 'reverted runtime failure reason byte: 0x03 -> 0x32\n'
    ;;
esac

read_bytes_after="$(read_bytes)"
printf 'bytes_after=%s\n' "$read_bytes_after"
