#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${DUNE_CURRENT_HOST:-kspls0}"
EXPECTED_BUILD_ID="${DUNE_LOGOFF_TIMER_BUILD_ID:-9bf5fbdef43a6d6d64459df973f3d252c01ab4ad}"
PATCH_OFFSET="${DUNE_LOGOFF_TIMER_PATCH_OFFSET:-0x12f49050}"
ORIGINAL_BYTES="${DUNE_LOGOFF_TIMER_ORIGINAL_BYTES:-554889e5f687a402000010751a}"
PATCH_BYTES="${DUNE_LOGOFF_TIMER_PATCH_BYTES:-31c0c3}"

if [[ "${1:-}" == "--host" ]]; then
  REMOTE_HOST="${2:?missing host after --host}"
  shift 2
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
else
  MODE="apply"
fi

if [[ "$MODE" != "dry-run" ]]; then
  cat >&2 <<'MSG'
refusing apply: the current build's duration accessor returns a pointer-like
duration payload, not an inline scalar. The 2026-06-01 return-zero code patch
matched the expected bytes but crashed survival-1 and deep-desert-1 with
signal 139. Use --dry-run only until a data/object-field patch is validated.
MSG
  exit 2
fi

ssh "$REMOTE_HOST" \
  "EXPECTED_BUILD_ID='$EXPECTED_BUILD_ID' PATCH_OFFSET='$PATCH_OFFSET' ORIGINAL_BYTES='$ORIGINAL_BYTES' PATCH_BYTES='$PATCH_BYTES' MODE='$MODE' bash -s" <<'REMOTE'
set -euo pipefail

mapfile -t containers < <(
  docker ps --format '{{.Names}}' |
    awk '$0 == "dune_server-survival-1" || $0 == "dune_server-deep-desert-1"'
)

if [[ "${#containers[@]}" -eq 0 ]]; then
  echo "no active survival/deep-desert containers found" >&2
  exit 1
fi

for container in "${containers[@]}"; do
  pid="$(docker top "$container" -eo pid,args | awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}')"
  if [[ -z "$pid" ]]; then
    echo "$container: no DuneSandboxServer-Linux-Shipping process found" >&2
    continue
  fi

  exe_path="$(sudo -n readlink "/proc/$pid/exe")"
  build_id="$(sudo -n readelf -n "/proc/$pid/exe" | awk '/Build ID:/ {print $3; exit}')"
  if [[ "$build_id" != "$EXPECTED_BUILD_ID" ]]; then
    echo "$container: refusing build $build_id; expected $EXPECTED_BUILD_ID" >&2
    exit 1
  fi

  base="$(sudo -n awk -v exe="$exe_path" '$6 == exe && $3 == "00000000" {split($1,a,"-"); print "0x"a[1]; exit}' "/proc/$pid/maps")"
  if [[ -z "$base" ]]; then
    echo "$container: could not find PIE base" >&2
    exit 1
  fi

  addr="$(printf '0x%x' $((base + PATCH_OFFSET)))"
  patch_len="$(( ${#PATCH_BYTES} / 2 ))"
  original_len="$(( ${#ORIGINAL_BYTES} / 2 ))"
  echo "$container: pid=$pid base=$base patch_addr=$addr patch_offset=$PATCH_OFFSET mode=$MODE"

  if [[ "$MODE" == "dry-run" ]]; then
    sudo -n gdb -q -batch -p "$pid" \
      -ex "set pagination off" \
      -ex "x/${original_len}xb $addr"
  else
    gdb_args=(-q -batch -p "$pid" -ex "set pagination off" -ex "x/${original_len}xb $addr")
    for ((i = 0; i < patch_len; i++)); do
      byte="0x${PATCH_BYTES:$((i * 2)):2}"
      gdb_args+=(-ex "set {unsigned char}($addr + $i) = $byte")
    done
    gdb_args+=(-ex "x/${original_len}xb $addr")
    sudo -n gdb "${gdb_args[@]}"
  fi
done
REMOTE
