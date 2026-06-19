#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/brt-dd-runtime-patch-site.sh status|apply|revert SITE [CONTAINER]

Applies or reverts one current-build DD BRT runtime canary in a running map
process. This writes process memory only; it does not modify the container
binary on disk and is lost on container restart.

Sites:
  all (status only)
  failure-reason-action-method
  state-empty-context
  can-use-empty-context
  can-use-actor-lookup-null
  can-use-map-area-guard
  can-use-region-fail-join
  invalid-map-reason-guard
  rpc-request-force-placeable-load-path
  can-backup-blueprint-allow-valid-selected
  can-backup-blueprint-map-context-guard
  brt-component-use-force-backup-mode
  brt-backup-request-actor-validation-allow
  brt-backup-base-owner-allow
  brt-backup-mode-byte-allow-any
  brt-backup-inventory-match-allow
  perform-invalid-map-site-a
  perform-invalid-map-site-b
  perform-invalid-map-site-c
  perform-invalid-map-site-d
USAGE
}

action="${1:-}"
site="${2:-}"
container="${3:-dune_server-deep-desert-1}"
required_host="${DUNE_BRT_DD_RUNTIME_CANARY_HOST:-kspls0}"

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

if [[ -z "$site" ]]; then
  usage
  exit 2
fi

SITES=(
  failure-reason-action-method
  state-empty-context
  can-use-empty-context
  can-use-actor-lookup-null
  can-use-map-area-guard
  can-use-region-fail-join
  invalid-map-reason-guard
  rpc-request-force-placeable-load-path
  can-backup-blueprint-allow-valid-selected
  can-backup-blueprint-map-context-guard
  brt-component-use-force-backup-mode
  brt-backup-request-actor-validation-allow
  brt-backup-base-owner-allow
  brt-backup-mode-byte-allow-any
  brt-backup-inventory-match-allow
  perform-invalid-map-site-a
  perform-invalid-map-site-b
  perform-invalid-map-site-c
  perform-invalid-map-site-d
)

site_spec() {
  local key="$1"
  case "$key" in
    failure-reason-action-method)
    offset=0xe04e81e
    original="41 b6 32"
    patched="41 b6 03"
    ;;
    state-empty-context)
    offset=0xe04e9e3
    original="31 db"
    patched="b3 01"
    ;;
    can-use-empty-context)
    offset=0xe04ec15
    original="45 31 f6"
    patched="41 b6 01"
    ;;
    can-use-actor-lookup-null)
    offset=0xe04ed18
    original="74 0a"
    patched="90 90"
    ;;
    can-use-map-area-guard)
    offset=0xe04ed22
    original="75 03"
    patched="eb 03"
    ;;
    can-use-region-fail-join)
    offset=0xe04ed24
    original="45 31 f6"
    patched="41 b6 01"
    ;;
    invalid-map-reason-guard)
    offset=0xe04e6e6
    original="0f 85 f3 fe ff ff"
    patched="90 90 90 90 90 90"
    ;;
    rpc-request-force-placeable-load-path)
    offset=0xd202c47
    original="74 5e"
    patched="eb 5e"
    ;;
    can-backup-blueprint-allow-valid-selected)
    # In UBuildingBlueprintBackupToolPlayerCharacterComponent::CanBackupBlueprint,
    # an existing selected actor at component+0x350 normally reaches the valid
    # path only when its flags do not include 0x60000000. This test patch allows
    # any non-null selected actor to continue to the same valid path. It is only
    # safe when live trace proves component+0x350 is non-null and the branch is
    # failing on the flag test.
    offset=0xd08128e
    original="0f 84 70 01 00 00"
    patched="90 90 90 90 90 90"
    ;;
    can-backup-blueprint-map-context-guard)
    # Same function, after selected-actor validation. This bypasses the map/base
    # context guard that otherwise returns the local CanBackupBlueprint failure
    # response. It is only safe when trace proves the selected actor path reached
    # d081404 and failed through the d081419/d081430 guard sequence.
    offset=0xd081430
    original="0f 84 f0 01 00 00"
    patched="90 90 90 90 90 90"
    ;;
    brt-component-use-force-backup-mode)
    # In UBuildingBlueprintBackupToolPlayerCharacterComponent::Use, the
    # component mode byte at +0x1b0 dispatches mode 3 into the native
    # CanBackupBlueprint/backup path. Force this dispatch while testing DD
    # backup mode so a client stuck on a selected restore entry cannot keep the
    # server on the restore-preview branch.
    offset=0xd0800d0
    original="74 39"
    patched="eb 39"
    ;;
    brt-backup-request-actor-validation-allow)
    # In UBaseBackupActionBackup::Perform, after resolving the selected request
    # actor, this bypasses the request-actor validation branch that otherwise
    # jumps to the generic failure response. Only apply when trace proves
    # brt_backup_request_actor_valid was reached and failed here.
    offset=0xcf59452
    original="0f 84 d8 0a 00 00"
    patched="90 90 90 90 90 90"
    ;;
    brt-backup-base-owner-allow)
    # Native backup checks whether the resolved base/owner relation matches the
    # player context before checking the action mode byte. Only apply when trace
    # proves brt_backup_base_owner_check_fail is the stopping gate.
    offset=0xcf597f3
    original="0f 85 a6 01 00 00"
    patched="90 90 90 90 90 90"
    ;;
    brt-backup-mode-byte-allow-any)
    # Native backup expects the action mode byte to be 1. This bypass is for the
    # case where the forced component backup dispatch reaches Perform but the
    # original client payload still carries another mode byte.
    offset=0xcf597fd
    original="0f 85 2d 07 00 00"
    patched="90 90 90 90 90 90"
    ;;
    brt-backup-inventory-match-allow)
    # After mode validation, native backup verifies the selected tool/inventory
    # matches the owner context. Only apply when trace proves
    # brt_backup_inventory_match_fail is the next stopping gate.
    offset=0xcf59827
    original="0f 84 1c 03 00 00"
    patched="90 90 90 90 90 90"
    ;;
    perform-invalid-map-site-a)
    offset=0xcfc5a7e
    original="88"
    patched="01"
    ;;
    perform-invalid-map-site-b)
    offset=0xcfc5c88
    original="88"
    patched="01"
    ;;
    perform-invalid-map-site-c)
    offset=0xcfc5fe6
    original="88"
    patched="01"
    ;;
    perform-invalid-map-site-d)
    offset=0xcfc60d2
    original="88"
    patched="01"
    ;;
    *)
    printf 'unknown site: %s\n' "$site" >&2
    usage
    exit 2
    ;;
  esac
}

if [[ "$site" == "all" && "$action" != "status" ]]; then
  printf 'site "all" is only valid with status\n' >&2
  exit 2
fi
if [[ "$site" != "all" ]]; then
  site_spec "$site"
fi

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

addr_for_offset() {
  python3 - "$base" "$1" <<'PY'
import sys
print(hex(int(sys.argv[1], 16) + int(sys.argv[2], 16)))
PY
}

byte_count() {
  wc -w <<<"$1" | tr -d ' '
}

read_bytes() {
  local count="$1"
  local addr="$2"
  sudo -n gdb -q -nx -batch -p "$pid" \
    -ex "set pagination off" \
    -ex "x/${count}xb $addr" \
    -ex detach \
    -ex quit 2>/dev/null |
    awk -v count="$count" '
      {
        for (i = 1; i <= NF; i++) {
          if ($i ~ /^0x[[:xdigit:]][[:xdigit:]]$/) {
            gsub(/^0x/, "", $i)
            printf "%s%s", sep, tolower($i)
            sep = " "
            seen++
            if (seen == count) {
              printf "\n"
              exit
            }
          }
        }
      }
      END { if (seen != count) exit 1 }
    '
}

write_bytes() {
  local raw="$1" index=0 token
  local addr="$2"
  local -a exprs
  for token in $raw; do
    exprs+=( -ex "set {unsigned char}($addr+$index) = 0x$token" )
    index=$((index + 1))
  done
  sudo -n gdb -q -nx -batch -p "$pid" \
    -ex "set pagination off" \
    "${exprs[@]}" \
    -ex detach \
    -ex quit >/dev/null
}

uprobe_shadow() {
  local raw="$1"
  local first rest
  first="${raw%% *}"
  if [[ "$first" == "$raw" ]]; then
    return 1
  fi
  rest="${raw#* }"
  printf 'cc %s\n' "$rest"
}

mixed_original_first_patched_rest() {
  local original_first original_rest patched_rest
  original_first="${original%% *}"
  original_rest="${original#* }"
  patched_rest="${patched#* }"
  if [[ "$original_rest" == "$original" || "$patched_rest" == "$patched" ]]; then
    return 1
  fi
  [[ "$original_rest" != "$patched_rest" ]] || return 1
  printf '%s %s\n' "$original_first" "$patched_rest"
}

site_state() {
  local bytes="$1"
  original_uprobe="$(uprobe_shadow "$original" || true)"
  patched_uprobe="$(uprobe_shadow "$patched" || true)"
  mixed_original_patched="$(mixed_original_first_patched_rest || true)"
  case "$bytes" in
    "$original") printf 'original\n' ;;
    "$patched") printf 'patched\n' ;;
    "$original_uprobe") printf 'original_uprobe\n' ;;
    "$patched_uprobe") printf 'patched_uprobe\n' ;;
    "$mixed_original_patched") printf 'mixed_original_first_patched_rest\n' ;;
    *)
      if [[ "$bytes" == cc\ * ]]; then
        printf 'unexpected_uprobe\n'
      else
        printf 'unexpected\n'
      fi
      ;;
  esac
}

if [[ "$site" == "all" ]]; then
  printf 'container=%s pid=%s base=%s\n' "$container" "$pid" "$base"
  for one_site in "${SITES[@]}"; do
    site_spec "$one_site"
    addr="$(addr_for_offset "$offset")"
    count="$(byte_count "$original")"
    bytes="$(read_bytes "$count" "$addr")"
    state="$(site_state "$bytes")"
    printf 'site=%s offset=%s addr=%s state=%s bytes=%s\n' "$one_site" "$offset" "$addr" "$state" "$bytes"
  done
  exit 0
fi

addr="$(addr_for_offset "$offset")"
count="$(byte_count "$original")"
bytes="$(read_bytes "$count" "$addr")"
printf 'container=%s pid=%s base=%s site=%s offset=%s addr=%s bytes=%s\n' \
  "$container" "$pid" "$base" "$site" "$offset" "$addr" "$bytes"

state="$(site_state "$bytes")"
case "$state" in
  original|patched|original_uprobe|patched_uprobe|mixed_original_first_patched_rest) ;;
  unexpected_uprobe)
    printf 'site appears to have an active uprobe at %s with unexpected bytes; stop BRT trace before apply/revert/status for this site\n' "$addr" >&2
    exit 1
    ;;
  *)
    printf 'unexpected bytes at %s: %s; expected original [%s] or patched [%s]\n' "$addr" "$bytes" "$original" "$patched" >&2
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
    if [[ "$state" == "original_uprobe" ]]; then
      printf 'site has an active uprobe at %s; stop BRT trace before applying this site\n' "$addr" >&2
      exit 1
    fi
    write_bytes "$patched" "$addr"
    printf 'patched runtime site %s: %s -> %s\n' "$site" "$original" "$patched"
    ;;
  revert)
    if [[ "$state" == "original" || "$state" == "original_uprobe" ]]; then
      printf 'already original\n'
      exit 0
    fi
    if [[ "$state" == "patched_uprobe" ]]; then
      printf 'site has an active uprobe at %s; stop BRT trace before reverting this site\n' "$addr" >&2
      exit 1
    fi
    write_bytes "$original" "$addr"
    printf 'reverted runtime site %s: %s -> %s\n' "$site" "$patched" "$original"
    ;;
esac

bytes_after="$(read_bytes "$count" "$addr")"
printf 'bytes_after=%s\n' "$bytes_after"
