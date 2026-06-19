#!/usr/bin/env bash
set -euo pipefail

container="${1:-dune_server-deep-desert-1}"
log="${2:-/tmp/brt-place-trace-live.log}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
source "$script_dir/lib/brt-dd-trace-guards.sh"
required_host="${DUNE_BRT_DD_TRACE_HOST:-kspls0}"

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
echo "$short_host"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_TRACE_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "ERROR: refusing to trace on host '$short_host'; required '$required_host'." >&2
  exit 1
fi

pid="$(docker top "$container" -eo pid,args | awk '/DuneSandboxServer-Linux-Shipping/ {print $1; exit}')"
if [[ -z "$pid" ]]; then
  echo "$container: no DuneSandboxServer-Linux-Shipping process found" >&2
  exit 1
fi
BRT_TRACE_KEYSTONE_ONLY="${BRT_TRACE_KEYSTONE_ONLY:-1}"
if [[ "$BRT_TRACE_KEYSTONE_ONLY" != "1" ]]; then
  brt_dd_trace_refuse_dense_builtins_unless_allowed "$pid" "trace-brt-place-live"
fi

if [[ -s /tmp/brt-place-trace-gdb.pid ]]; then
  old_gdb="$(cat /tmp/brt-place-trace-gdb.pid 2>/dev/null || true)"
  if [[ "$old_gdb" =~ ^[0-9]+$ ]] && ps -p "$old_gdb" -o cmd= 2>/dev/null | grep -q 'gdb -q -p'; then
    sudo -n kill "$old_gdb" 2>/dev/null || true
    sleep 0.3
  fi
fi

exe_path="$(sudo -n readlink "/proc/$pid/exe")"
base="$(sudo -n awk -v exe="$exe_path" '$6 == exe && $3 == "00000000" {split($1,a,"-"); print "0x"a[1]; exit}' "/proc/$pid/maps")"
if [[ -z "$base" ]]; then
  echo "$container: could not find PIE base for pid $pid" >&2
  exit 1
fi

addr() { printf '0x%x' $((base + $1)); }

cmd="/tmp/brt-place-trace.gdb"
{
  printf 'set pagination off\n'
  printf 'set confirm off\n'
  printf 'set print pretty off\n'
  printf 'set logging file %s\n' "$log"
  printf 'set logging overwrite on\n'
  printf 'set logging enabled on\n'
  printf 'printf "BRT_PLACE_TRACE armed container=%s pid=%%d base=%%p\\n", %d, (void*)%s\n' "$container" "$pid" "$base"

  add_bp() {
    local off="$1"
    shift
    printf 'break *%s\ncommands\n silent\n%s\n continue\nend\n' "$(addr "$off")" "$*"
  }

  # The dense state/preview/PerformCanBePlaced breakpoints below fire on normal
  # building/totem placement by ANY player on this partition. On a live, populated
  # Deep Desert that is a hot path; set BRT_TRACE_KEYSTONE_ONLY=1 to skip them and
  # arm only the env-driven keystone breakpoints (RPC entry / restriction gate /
  # region reject), which fire only when someone actually uses the BRT.
  if [[ "$BRT_TRACE_KEYSTONE_ONLY" != "1" ]]; then
  # UBuildingBlueprintBackupToolPlayerCharacterComponent state / preview path.
  add_bp 0xd07a460 'printf "BRT_PLACE hit state-entry comp=%p mode=%u ctx108=%p selected350=%p b358=%u b359=%u\n", $rdi, *(unsigned char*)($rdi+0x1b0), *(void**)($rdi+0x108), *(void**)($rdi+0x350), *(unsigned char*)($rdi+0x358), *(unsigned char*)($rdi+0x359)'
  add_bp 0xd07a4c7 'printf "BRT_PLACE hit state-after-nearby code=%u rbp=%p\n", *(unsigned char*)($rbp-0x68), $rbp'
  add_bp 0xd07a4e3 'printf "BRT_PLACE hit state-before-can rbp=%p\n", $rbp'
  add_bp 0xd07a5f6 'printf "BRT_PLACE hit state-after-can code=%u rbp=%p\n", *(unsigned char*)($rbp-0x68), $rbp'

  # CanBackupBlueprint result path used by BRT state/UI.
  add_bp 0xd07b5e0 'if $rsi != 0
  printf "BRT_PLACE hit can-entry comp=%p out=%p ctx108=%p selected350=%p b358=%u b359=%u\n", $rsi, $rdi, *(void**)($rsi+0x108), *(void**)($rsi+0x350), *(unsigned char*)($rsi+0x358), *(unsigned char*)($rsi+0x359)
 else
  printf "BRT_PLACE hit can-entry comp=NULL out=%p\n", $rdi
 end'
  add_bp 0xd07b9fe 'printf "BRT_PLACE hit can-after-validation local_code=%u rbp=%p\n", *(unsigned char*)($rbp-0xa8), $rbp'
  add_bp 0xd07bad6 'printf "BRT_PLACE hit can-state-check r12b=%u r15b=%u al=%u rbp=%p\n", (unsigned char)$r12, (unsigned char)$r15, (unsigned char)$al, $rbp'
  add_bp 0xd07bd17 'printf "BRT_PLACE hit can-return-fail64 rbp=%p\n", $rbp'

  # BRT StartBuilding / actual place handoff.
  add_bp 0xd07c560 'printf "BRT_PLACE hit start-building entry rdi=%p rsi=%p rdx=%p rcx=%p\n", $rdi, $rsi, $rdx, $rcx'
  add_bp 0xd07c6e2 'printf "BRT_PLACE hit start-building helperA before ret-check rbp=%p\n", $rbp'
  add_bp 0xd07c6ea 'printf "BRT_PLACE hit start-building helperB before ret-check rbp=%p\n", $rbp'
  add_bp 0xd07c821 'if $rdx != 0
  printf "BRT_PLACE hit start-building status ok=%u code=%u status=%p\n", (unsigned int)$esi, *(unsigned char*)($rdx+0x18), $rdx
 else
  printf "BRT_PLACE hit start-building status ok=%u status=NULL\n", (unsigned int)$esi
 end'

  # Shared status widget/update path.
  add_bp 0xd083c00 'if $rdx != 0
  printf "BRT_PLACE hit status-update tool=%p ok=%u code=%u status=%p\n", $rdi, (unsigned int)$esi, *(unsigned char*)($rdx+0x18), $rdx
 else
  printf "BRT_PLACE hit status-update tool=%p ok=%u status=NULL\n", $rdi, (unsigned int)$esi
 end'

  # BuildingBlueprintBrush::PerformCanBePlaced. Offsets here are binary file offsets.
  add_bp 0xcfbf7f0 'printf "BRT_PLACE hit perform-can entry out=%p brush=%p flag=%u ctx=%p\n", $rdi, $rsi, (unsigned int)$edx, $rcx'
  add_bp 0xcfbfabb 'printf "BRT_PLACE hit perform-mapregion-result eax=%u rbp=%p\n", (unsigned int)$eax, $rbp'
  add_bp 0xcfbfe2e 'printf "BRT_PLACE hit invalid-map-site-A patched_byte=%u rbp=%p\n", *(unsigned char*)$rip, $rbp'
  add_bp 0xcfc0038 'printf "BRT_PLACE hit invalid-map-site-B patched_byte=%u rbp=%p\n", *(unsigned char*)$rip, $rbp'
  add_bp 0xcfc0396 'printf "BRT_PLACE hit invalid-map-site-C patched_byte=%u rbp=%p\n", *(unsigned char*)$rip, $rbp'
  add_bp 0xcfc0482 'printf "BRT_PLACE hit invalid-map-site-D patched_byte=%u rbp=%p\n", *(unsigned char*)$rip, $rbp'
  fi

  # Phase-1 keystone breakpoints. Offsets are build-specific and are NOT
  # hardcoded; resolve them on the host with
  # scripts/research/DumpBrtTraceAnchors.java and pass via env, e.g.:
  #   BRT_RPC_PLACE_OFFSET=0x... BRT_RESTRICTION_GATE_OFFSET=0x... \
  #     scripts/trace-brt-place-live.sh dune_server-deep-desert-1
  #
  # BRT_RPC_PLACE_OFFSET answers unknown #1: if this never fires during a DD
  # restore attempt, the block is client-side and no server patch can help.
  if [[ -n "${BRT_RPC_EXEC_OFFSET:-}" ]]; then
    add_bp "$BRT_RPC_EXEC_OFFSET" 'printf "BRT_PLACE hit SERVER-RPC-EXEC request-dispatched-to-native-exec rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p\n", $rdi, $rsi, $rdx, $rcx, $r8, $r9
if '"${BRT_TRACE_RPC_BACKTRACE:-0}"' != 0
  info registers rdi rsi rdx rcx r8 r9 rax rbx rbp rsp rip
  bt 12
end'
  fi
  if [[ -n "${BRT_RPC_PLACE_OFFSET:-}" ]]; then
    add_bp "$BRT_RPC_PLACE_OFFSET" 'printf "BRT_PLACE hit SERVER-RPC-ENTRY request-reached-server rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p\n", $rdi, $rsi, $rdx, $rcx, $r8, $r9
if '"${BRT_TRACE_RPC_BACKTRACE:-0}"' != 0
  info registers rdi rsi rdx rcx r8 r9 rax rbx rbp rsp rip
  bt 12
end'
  fi
  # BRT_RESTRICTION_GATE_OFFSET answers unknown #2: at the map-restriction read
  # site, dump the argument registers so the live restriction array/object can be
  # inspected. Override the printed expression with BRT_RESTRICTION_GATE_EXPR
  # once the settings pointer/array offset is known from the Ghidra dump.
  if [[ -n "${BRT_RESTRICTION_GATE_OFFSET:-}" ]]; then
    add_bp "$BRT_RESTRICTION_GATE_OFFSET" "${BRT_RESTRICTION_GATE_EXPR:-printf \"BRT_PLACE hit RESTRICTION-GATE rdi=%p rsi=%p rdx=%p rcx=%p r8=%p\\n\", \$rdi, \$rsi, \$rdx, \$rcx, \$r8}"
  fi
  # Optional extra player-visible reject emitter from DumpBrtTraceAnchors.java.
  if [[ -n "${BRT_REGION_REJECT_OFFSET:-}" ]]; then
    add_bp "$BRT_REGION_REJECT_OFFSET" 'printf "BRT_PLACE hit REGION-REJECT-EMITTER rdi=%p rsi=%p rbp=%p\n", $rdi, $rsi, $rbp'
  fi

  printf 'continue\n'
} >"$cmd"

rm -f "$log" /tmp/brt-place-trace-gdb.out /tmp/brt-place-trace-gdb.pid
sudo -n gdb -q -p "$pid" -x "$cmd" >/tmp/brt-place-trace-gdb.out 2>&1 &
echo $! >/tmp/brt-place-trace-gdb.pid

sleep 0.8
echo "gdb_pid=$(cat /tmp/brt-place-trace-gdb.pid)"
pgrep -af "gdb -q -p $pid" || true
echo "--out--"
tail -80 /tmp/brt-place-trace-gdb.out 2>/dev/null || true
echo "--log--"
tail -80 "$log" 2>/dev/null || true
echo "keystone_bps: rpc_exec=${BRT_RPC_EXEC_OFFSET:-unset} rpc_impl=${BRT_RPC_PLACE_OFFSET:-unset} restriction_gate=${BRT_RESTRICTION_GATE_OFFSET:-unset} region_reject=${BRT_REGION_REJECT_OFFSET:-unset}"
if [[ -z "${BRT_RPC_EXEC_OFFSET:-}" && -z "${BRT_RPC_PLACE_OFFSET:-}" ]]; then
  echo "note: RPC offsets unset -> cannot prove the place request reached the server (Phase 1 keystone). Resolve them with scripts/research/summarize-elf-pointer-context.py or scripts/research/DumpBrtTraceAnchors.java." >&2
fi
echo "armed target_pid=$pid base=$base log=$log"
