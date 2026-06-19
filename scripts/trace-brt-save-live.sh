#!/usr/bin/env bash
set -euo pipefail

container="${1:-dune_server-deep-desert-1}"
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
brt_dd_trace_refuse_dense_builtins_unless_allowed "$pid" "trace-brt-save-live"

exe_path="$(sudo -n readlink "/proc/$pid/exe")"
base="$(sudo -n awk -v exe="$exe_path" '$6 == exe && $3 == "00000000" {split($1,a,"-"); print "0x"a[1]; exit}' "/proc/$pid/maps")"
if [[ -z "$base" ]]; then
  echo "$container: could not find PIE base for pid $pid" >&2
  exit 1
fi

addr() { printf '0x%x' $((base + $1)); }

cmd="/tmp/brt-save-trace.gdb"
{
  printf 'set pagination off\n'
  printf 'set confirm off\n'
  printf 'set print pretty off\n'
  printf 'set logging file /tmp/brt-save-trace-live.log\n'
  printf 'set logging overwrite on\n'
  printf 'set logging enabled on\n'
  printf 'printf "BRT_SAVE_TRACE armed container=%s pid=%%d base=%%p\\n", %d, (void*)%s\n' "$container" "$pid" "$base"

  add_bp() {
    local off="$1"
    shift
    printf 'break *%s\ncommands\n silent\n%s\n continue\nend\n' "$(addr "$off")" "$*"
  }

  add_bp 0xd080150 'printf "BRT_SAVE hit use-entry rip=%p param=%p\n", $rip, $rdi'
  add_bp 0xd080176 'printf "BRT_SAVE hit use-after-can code=%u rbp=%p\n", *(unsigned char*)($rbp-0x180), $rbp'
  add_bp 0xd07a4c7 'printf "BRT_SAVE hit action-update-nearby-code code=%u rbp=%p\n", *(unsigned char*)($rbp-0x68), $rbp'
  add_bp 0xd07a4e3 'printf "BRT_SAVE hit action-before-can rbp=%p\n", $rbp'
  add_bp 0xd07a5f6 'printf "BRT_SAVE hit action-after-can code=%u rbp=%p\n", *(unsigned char*)($rbp-0x68), $rbp'
  add_bp 0xd07b5e0 'if $rsi != 0
  printf "BRT_SAVE hit can-entry comp=%p out=%p ctx108=%p selected350=%p b358=%u b359=%u\n", $rsi, $rdi, *(void**)($rsi+0x108), *(void**)($rsi+0x350), *(unsigned char*)($rsi+0x358), *(unsigned char*)($rsi+0x359)
 else
  printf "BRT_SAVE hit can-entry comp=NULL out=%p\n", $rdi
 end'
  add_bp 0xd07b791 'printf "BRT_SAVE hit can-return-0x90 rbp=%p\n", $rbp'
  add_bp 0xd07b9fe 'printf "BRT_SAVE hit can-after-validation local_code=%u rbp=%p\n", *(unsigned char*)($rbp-0xa8), $rbp'
  add_bp 0xd07bad6 'printf "BRT_SAVE hit can-state-check r12b=%u r15b=%u al=%u rbp=%p\n", (unsigned char)$r12, (unsigned char)$r15, (unsigned char)$al, $rbp'
  add_bp 0xd07bd17 'printf "BRT_SAVE hit can-return-0x64 rbp=%p\n", $rbp'
  add_bp 0xd302ae0 'printf "BRT_SAVE hit build-validation entry actor=%p flag=%u ctx=%p\n", $rsi, (unsigned int)$edx, $rcx'
  printf 'continue\n'
} >"$cmd"

rm -f /tmp/brt-save-trace-live.log /tmp/brt-save-trace-gdb.out /tmp/brt-save-trace-gdb.pid
sudo -n gdb -q -p "$pid" -x "$cmd" >/tmp/brt-save-trace-gdb.out 2>&1 &
echo $! >/tmp/brt-save-trace-gdb.pid

sleep 0.7
echo "gdb_pid=$(cat /tmp/brt-save-trace-gdb.pid)"
pgrep -af "gdb -q -p $pid" || true
echo "--out--"
tail -60 /tmp/brt-save-trace-gdb.out 2>/dev/null || true
echo "--log--"
tail -60 /tmp/brt-save-trace-live.log 2>/dev/null || true
echo "armed target_pid=$pid base=$base"
