#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${DUNE_CURRENT_HOST:-kspls0}"
EXPECTED_BUILD_ID="${DUNE_LOGOFF_TIMER_BUILD_ID:-9bf5fbdef43a6d6d64459df973f3d252c01ab4ad}"
VALUE_A_OFFSET="${DUNE_LOGOFF_TIMER_VALUE_A_OFFSET:-0x16521698}"
VALUE_B_OFFSET="${DUNE_LOGOFF_TIMER_VALUE_B_OFFSET:-0x165216b0}"
DEADLINE_CLAMP_OFFSET="${DUNE_LOGOFF_TIMER_DEADLINE_CLAMP_OFFSET:-0xd50f864}"
TIMER_DURATION_ZERO_OFFSET="${DUNE_LOGOFF_TIMER_DURATION_ZERO_OFFSET:-0xd50fcba}"
TARGET_VALUE="${DUNE_LOGOFF_TIMER_VALUE:-0.0}"

if [[ "${1:-}" == "--host" ]]; then
  REMOTE_HOST="${2:?missing host after --host}"
  shift 2
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
else
  MODE="apply"
fi

ssh "$REMOTE_HOST" \
  "EXPECTED_BUILD_ID='$EXPECTED_BUILD_ID' VALUE_A_OFFSET='$VALUE_A_OFFSET' VALUE_B_OFFSET='$VALUE_B_OFFSET' DEADLINE_CLAMP_OFFSET='$DEADLINE_CLAMP_OFFSET' TIMER_DURATION_ZERO_OFFSET='$TIMER_DURATION_ZERO_OFFSET' TARGET_VALUE='$TARGET_VALUE' MODE='$MODE' bash -s" <<'REMOTE'
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

  addr_a="$(printf '0x%x' $((base + VALUE_A_OFFSET)))"
  addr_b="$(printf '0x%x' $((base + VALUE_B_OFFSET)))"
  addr_clamp="$(printf '0x%x' $((base + DEADLINE_CLAMP_OFFSET)))"
  addr_duration_zero="$(printf '0x%x' $((base + TIMER_DURATION_ZERO_OFFSET)))"
  echo "$container: pid=$pid base=$base pointers=$addr_a,$addr_b clamp=$addr_clamp duration_zero=$addr_duration_zero mode=$MODE"

  if [[ "$MODE" == "dry-run" ]]; then
    sudo -n gdb -q -batch -p "$pid" \
      -ex "set pagination off" \
      -ex "set \$p1 = *(void**)$addr_a" \
      -ex "set \$p2 = *(void**)$addr_b" \
      -ex "printf \"before p1=%p p2=%p\\n\", \$p1, \$p2" \
      -ex "x/4fw \$p1" \
      -ex "x/4fw \$p2" \
      -ex "printf \"deadline clamp bytes: \"" \
      -ex "x/3xb $addr_clamp" \
      -ex "printf \"timer duration bytes: \"" \
      -ex "x/5xb $addr_duration_zero"
  else
    sudo -n gdb -q -batch -p "$pid" \
      -ex "set pagination off" \
      -ex "set \$p1 = *(void**)$addr_a" \
      -ex "set \$p2 = *(void**)$addr_b" \
      -ex "printf \"before p1=%p p2=%p\\n\", \$p1, \$p2" \
      -ex "x/4fw \$p1" \
      -ex "x/4fw \$p2" \
      -ex "set {float}\$p1 = $TARGET_VALUE" \
      -ex "set {float}((char*)\$p1 + 4) = $TARGET_VALUE" \
      -ex "set {float}\$p2 = $TARGET_VALUE" \
      -ex "set {float}((char*)\$p2 + 4) = $TARGET_VALUE" \
      -ex "set \$clamp = (unsigned char*)$addr_clamp" \
      -ex "printf \"deadline clamp before: %02x %02x %02x\\n\", \$clamp[0], \$clamp[1], \$clamp[2]" \
      -ex "set \$clamp[1] = 0x89" \
      -ex "set \$duration = (unsigned char*)$addr_duration_zero" \
      -ex "printf \"timer duration before: %02x %02x %02x %02x %02x\\n\", \$duration[0], \$duration[1], \$duration[2], \$duration[3], \$duration[4]" \
      -ex "set \$duration[0] = 0xc5" \
      -ex "set \$duration[1] = 0xf8" \
      -ex "set \$duration[2] = 0x57" \
      -ex "set \$duration[3] = 0xc0" \
      -ex "set \$duration[4] = 0x90" \
      -ex "printf \"after p1=%p p2=%p\\n\", \$p1, \$p2" \
      -ex "x/4fw \$p1" \
      -ex "x/4fw \$p2" \
      -ex "printf \"deadline clamp bytes: \"" \
      -ex "x/3xb $addr_clamp" \
      -ex "printf \"timer duration bytes: \"" \
      -ex "x/5xb $addr_duration_zero"
  fi
done
REMOTE
