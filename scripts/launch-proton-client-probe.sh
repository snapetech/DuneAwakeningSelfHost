#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/launch-proton-client-probe.sh [options] -- %command%
  scripts/launch-proton-client-probe.sh [options]

Options:
  --appid ID              Steam app id. Default: 1172710.
  --game-dir PATH         Dune install directory.
  --exe-rel PATH          Exe path relative to game dir.
                          Default: DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe.
  --dll-name NAME.dll     Proxy DLL name staged for Wine override. Default: version.dll.
  --stage-dir PATH        Repo-contained staging directory.
  --stage-to-game-dir     Copy proxy DLL beside the game exe, with backup if needed.
  --unstage-game-dir      Remove the staged game-dir proxy only if it matches our DLL.
  --preflight-only        Validate and print the staging plan without building,
                          copying, writing sidecars, exporting Wine vars, or launching.

Recommended Steam launch option for Dune:
  /abs/path/scripts/launch-proton-client-probe.sh --stage-to-game-dir -- %command%

The default path stages the DLL outside the Steam game directory and sets
WINEDLLOVERRIDES, WINEPATH, and WINEDLLPATH for experiments. Dune's Proton path
should use --stage-to-game-dir so the proxy DLL is in the game DLL search path.
Set DUNE_WIN_CLIENT_PROBE_PREFLIGHT_ONLY=true for the same non-mutating check.
Set DUNE_WIN_CLIENT_PROBE_PREP_DIR to a prepare-ue-anchor-canary.py output dir
to source prepared UE anchor/signature env before staging the sidecar.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
appid="${DUNE_STEAM_APPID:-1172710}"
steam_root="${STEAM_ROOT:-$HOME/.steam/steam}"
game_dir="${DUNE_CLIENT_GAME_DIR:-}"
exe_rel="${DUNE_CLIENT_EXE_REL:-DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe}"
dll_name="${DUNE_WIN_CLIENT_PROXY_DLL:-version.dll}"
sidecar_name="${DUNE_WIN_CLIENT_PROBE_SIDECAR:-dune-win-client-probe.env}"
build_dir="${DUNE_WINDOWS_CLIENT_LOADER_BUILD_DIR:-$repo_root/build/windows-client-loader}"
loader="${DUNE_WINDOWS_CLIENT_PRELOAD:-$build_dir/dune_win_client_probe_loader.dll}"
stage_dir="${DUNE_WIN_CLIENT_STAGE_DIR:-$build_dir/proton-stage}"
prep_dir="${DUNE_WIN_CLIENT_PROBE_PREP_DIR:-}"
strict_verify="${DUNE_WIN_CLIENT_PROBE_STRICT_VERIFY:-false}"
stage_to_game_dir=false
unstage_game_dir=false
preflight_only="${DUNE_WIN_CLIENT_PROBE_PREFLIGHT_ONLY:-false}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --appid)
      appid="${2:?missing value for --appid}"
      shift 2
      ;;
    --game-dir)
      game_dir="${2:?missing value for --game-dir}"
      shift 2
      ;;
    --exe-rel)
      exe_rel="${2:?missing value for --exe-rel}"
      shift 2
      ;;
    --dll-name)
      dll_name="${2:?missing value for --dll-name}"
      shift 2
      ;;
    --stage-dir)
      stage_dir="${2:?missing value for --stage-dir}"
      shift 2
      ;;
    --stage-to-game-dir)
      stage_to_game_dir=true
      shift
      ;;
    --unstage-game-dir)
      unstage_game_dir=true
      shift
      ;;
    --preflight-only)
      preflight_only=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if [[ "$dll_name" != *.dll ]]; then
  dll_name="${dll_name}.dll"
fi
override_name="${dll_name%.dll}"

acf="$steam_root/steamapps/appmanifest_${appid}.acf"
if [ -z "$game_dir" ] && [ -f "$acf" ]; then
  install_dir="$(awk -F '"' '/"installdir"/ {print $4; exit}' "$acf")"
  if [ -n "$install_dir" ]; then
    game_dir="$steam_root/steamapps/common/$install_dir"
  fi
fi

manifest="$build_dir/game-dir-stage-manifest.txt"
game_exe=""
game_exe_dir=""
if [ -n "$game_dir" ]; then
  game_exe="$game_dir/$exe_rel"
  game_exe_dir="$(dirname "$game_exe")"
fi

prep_anchor_env_path() {
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  printf '%s/ue-anchors.env\n' "$prep_dir"
}

prep_verify_script_path() {
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  if [ "$strict_verify" = "true" ]; then
    printf '%s/post-canary-verify-strict.sh\n' "$prep_dir"
  else
    printf '%s/post-canary-verify.sh\n' "$prep_dir"
  fi
}

validate_prep_dir() {
  local anchor_env verify_script
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  anchor_env="$(prep_anchor_env_path)"
  verify_script="$(prep_verify_script_path)"
  if [ ! -d "$prep_dir" ]; then
    echo "missing prepared Proton canary dir: $prep_dir" >&2
    exit 2
  fi
  if [ ! -f "$anchor_env" ]; then
    echo "missing prepared Proton anchor env: $anchor_env" >&2
    exit 2
  fi
  if [ ! -x "$verify_script" ]; then
    echo "missing executable Proton post-canary verifier: $verify_script" >&2
    exit 2
  fi
}

load_prep_env() {
  local anchor_env
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  anchor_env="$(prep_anchor_env_path)"
  set -a
  # shellcheck disable=SC1090
  . "$anchor_env"
  set +a
}

validate_prep_dir
load_prep_env

if [ "$preflight_only" = "true" ]; then
  loader_readable=false
  if [ -r "$loader" ]; then
    loader_readable=true
  fi
  active_stage_dir="$stage_dir"
  stage_target="$stage_dir/$dll_name"
  stage_dir_valid=true
  if $stage_to_game_dir; then
    active_stage_dir="$game_exe_dir"
    stage_target="$game_exe_dir/$dll_name"
    if [ -z "$game_exe_dir" ] || [ ! -d "$game_exe_dir" ]; then
      stage_dir_valid=false
    fi
  fi
  cat <<EOF
windows_client_probe_preflight=true
appid=$appid
game_dir=$game_dir
game_exe=$game_exe
game_exe_dir=$game_exe_dir
stage_to_game_dir=$stage_to_game_dir
stage_dir=$stage_dir
active_stage_dir=$active_stage_dir
dll_name=$dll_name
override_name=$override_name
loader=$loader
loader_readable=$loader_readable
prep_dir=$prep_dir
prep_anchor_env=$(prep_anchor_env_path)
post_canary_verify_script=$(prep_verify_script_path)
stage_target=$stage_target
sidecar=$active_stage_dir/$sidecar_name
manifest=$manifest
stage_dir_valid=$stage_dir_valid
would_exec=$*
EOF
  if [ "$loader_readable" != "true" ]; then
    echo "Windows client probe DLL is not readable: $loader" >&2
    exit 1
  fi
  if [ "$stage_dir_valid" != "true" ]; then
    echo "--stage-to-game-dir needs a valid game exe directory; got: ${game_exe_dir:-<unknown>}" >&2
    exit 2
  fi
  exit 0
fi

if [ ! -f "$loader" ]; then
  "$repo_root/scripts/build-windows-client-loader.sh" >/dev/null
fi

if [ ! -r "$loader" ]; then
  echo "Windows client probe DLL is not readable: $loader" >&2
  exit 1
fi

posix_to_win_path() {
  local path="$1"
  if command -v winepath >/dev/null 2>&1; then
    WINEDEBUG=-all winepath -w "$path" 2>/dev/null && return 0
  fi
  printf 'Z:%s\n' "${path//\//\\}"
}

same_file_content() {
  local a="$1"
  local b="$2"
  [ -f "$a" ] && [ -f "$b" ] && cmp -s "$a" "$b"
}

manifest_owned_target() {
  local target="$1"
  local manifest_file="$2"
  [ -f "$target" ] || return 1
  [ -f "$manifest_file" ] || return 1
  local manifest_target
  manifest_target="$(awk -F '=' '/^target=/ {print $2; exit}' "$manifest_file")"
  [ "$manifest_target" = "$target" ] || return 1
  local manifest_sha
  manifest_sha="$(awk '/  / {print $1; exit}' "$manifest_file")"
  [ -n "$manifest_sha" ] || return 1
  local current_sha
  current_sha="$(sha256sum "$target" | awk '{print $1}')"
  [ "$manifest_sha" = "$current_sha" ]
}

manifest_owned_sidecar() {
  local sidecar="$1"
  local manifest_file="$2"
  [ -f "$sidecar" ] || return 1
  [ -f "$manifest_file" ] || return 1
  local manifest_sidecar
  manifest_sidecar="$(awk -F '=' '/^sidecar=/ {print $2; exit}' "$manifest_file")"
  [ "$manifest_sidecar" = "$sidecar" ] || return 1
  local manifest_sha
  manifest_sha="$(awk -v path="$sidecar" '$2 == path {print $1; exit}' "$manifest_file")"
  [ -n "$manifest_sha" ] || return 1
  local current_sha
  current_sha="$(sha256sum "$sidecar" | awk '{print $1}')"
  [ "$manifest_sha" = "$current_sha" ]
}

write_sidecar_config() {
  local path="$1"
  cat > "$path" <<EOF
# Generated by launch-proton-client-probe.sh. Environment variables override these values.
DUNE_WIN_CLIENT_PROBE_LOG=$DUNE_WIN_CLIENT_PROBE_LOG
DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=$DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS
DUNE_WIN_CLIENT_PROBE_LOG_MODULES=$DUNE_WIN_CLIENT_PROBE_LOG_MODULES
DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=$DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED
DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS=$DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS
DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS=${DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS:-}
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES=${DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES:-}
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE=${DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE:-}
DUNE_WIN_CLIENT_PROBE_UE_ANCHORS=${DUNE_WIN_CLIENT_PROBE_UE_ANCHORS:-}
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=${DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES:-}
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=${DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE:-}
DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=${DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE:-false}
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE=${DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE:-false}
DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=${DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE:-false}
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_SLOTS=${DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_SLOTS:-8}
DUNE_WIN_CLIENT_PROBE_HOOK_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_HOOK_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_MOD_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_MOD_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_LUA_DLL=${DUNE_WIN_CLIENT_PROBE_LUA_DLL:-}
DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT=${DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT:-}
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST_SCRIPT=${DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST_SCRIPT:-}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_ADDRESS=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_ADDRESS:-}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ADDRESS=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ADDRESS:-}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_ADDRESS=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_ADDRESS:-}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ADDRESS=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ADDRESS:-}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS:-}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS:-false}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT:-8}
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH=${DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS:-}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT:-8}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH:-false}
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=${DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT:-}
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=${DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT:-}
DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED=${DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED:-false}
DUNE_WIN_CLIENT_PROBE_LUA_MOD_SCRIPTS=${DUNE_WIN_CLIENT_PROBE_LUA_MOD_SCRIPTS:-}
DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT=${DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT:-}
DUNE_WIN_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=${DUNE_WIN_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST:-false}
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=$DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES=$DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES
DUNE_WIN_CLIENT_PROBE_SCAN_PRIVATE=${DUNE_WIN_CLIENT_PROBE_SCAN_PRIVATE:-false}
DUNE_WIN_CLIENT_PROBE_AUTO_THREAD=${DUNE_WIN_CLIENT_PROBE_AUTO_THREAD:-true}
EOF
  chmod 0644 "$path"
}

stage_overlay="$stage_dir/$dll_name"
mkdir -p "$stage_dir"
cp "$loader" "$stage_overlay"
chmod 0644 "$stage_overlay"

if $unstage_game_dir; then
  if [ -z "$game_exe_dir" ]; then
    echo "--unstage-game-dir needs --game-dir or a readable Steam appmanifest" >&2
    exit 2
  fi
  target="$game_exe_dir/$dll_name"
  if same_file_content "$target" "$loader"; then
    rm -f "$target"
    printf 'removed staged proxy DLL: %s\n' "$target"
    sidecar="$(awk -F '=' '/^sidecar=/ {print $2; exit}' "$manifest" 2>/dev/null || true)"
    if [ -n "$sidecar" ] && manifest_owned_sidecar "$sidecar" "$manifest"; then
      rm -f "$sidecar"
      printf 'removed staged sidecar config: %s\n' "$sidecar"
    fi
    rm -f "$manifest"
  else
    printf 'not removing %s: missing or content differs from current loader\n' "$target" >&2
    exit 1
  fi
  exit 0
fi

active_stage_dir="$stage_dir"
if $stage_to_game_dir; then
  if [ -z "$game_exe_dir" ] || [ ! -d "$game_exe_dir" ]; then
    echo "--stage-to-game-dir needs a valid game exe directory; got: ${game_exe_dir:-<unknown>}" >&2
    exit 2
  fi
  target="$game_exe_dir/$dll_name"
  mkdir -p "$build_dir"
  if [ -e "$target" ] &&
     ! same_file_content "$target" "$loader" &&
     ! manifest_owned_target "$target" "$manifest"; then
    backup="$target.dune-probe-backup.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -a "$target" "$backup"
    printf 'backed up existing %s to %s\n' "$target" "$backup" >&2
  fi
  cp "$loader" "$target"
  chmod 0644 "$target"
  {
    printf 'time=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'target=%s\n' "$target"
    printf 'source=%s\n' "$loader"
    sha256sum "$target"
  } > "$manifest"
  active_stage_dir="$game_exe_dir"
fi

stage_win="$(posix_to_win_path "$active_stage_dir")"
default_log_posix="${DUNE_WIN_CLIENT_PROBE_LOG_POSIX:-/tmp/dune-win-client-probe-loader.log}"
default_log_win="$(posix_to_win_path "$default_log_posix")"

if [ -z "${DUNE_WIN_CLIENT_PROBE_LOG+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_LOG="$default_log_win"
fi
if [ -z "${DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=true
fi
if [ -z "${DUNE_WIN_CLIENT_PROBE_LOG_MODULES+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_LOG_MODULES=true
fi
if [ -z "${DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
fi
if [ -z "${DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=16
fi
if [ -z "${DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES=268435456
fi
if [ -z "${DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS+x}" ]; then
  export DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=2
fi

sidecar_path="$active_stage_dir/$sidecar_name"
if $stage_to_game_dir && [ -e "$sidecar_path" ] && ! manifest_owned_sidecar "$sidecar_path" "$manifest"; then
  sidecar_backup="$sidecar_path.dune-probe-backup.$(date -u +%Y%m%dT%H%M%SZ)"
  cp -a "$sidecar_path" "$sidecar_backup"
  printf 'backed up existing %s to %s\n' "$sidecar_path" "$sidecar_backup" >&2
fi
write_sidecar_config "$sidecar_path"

if $stage_to_game_dir; then
  {
    printf 'time=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'target=%s\n' "$target"
    printf 'sidecar=%s\n' "$sidecar_path"
    printf 'source=%s\n' "$loader"
    sha256sum "$target"
    sha256sum "$sidecar_path"
  } > "$manifest"
fi

if [ -n "${WINEDLLOVERRIDES:-}" ]; then
  export WINEDLLOVERRIDES="${override_name}=n,b;${WINEDLLOVERRIDES}"
else
  export WINEDLLOVERRIDES="${override_name}=n,b"
fi

if [ -n "${WINEPATH:-}" ]; then
  export WINEPATH="${stage_win};${WINEPATH}"
else
  export WINEPATH="$stage_win"
fi

if [ -n "${WINEDLLPATH:-}" ]; then
  export WINEDLLPATH="${active_stage_dir}:${WINEDLLPATH}"
else
  export WINEDLLPATH="$active_stage_dir"
fi

if [ "$#" -eq 0 ]; then
  cat <<EOF
Windows client probe staged.

proxy_dll=$stage_overlay
active_stage_dir=$active_stage_dir
sidecar_config=$sidecar_path
dll_override=$WINEDLLOVERRIDES
winepath=$WINEPATH
winedllpath=$WINEDLLPATH
probe_log=$DUNE_WIN_CLIENT_PROBE_LOG

Recommended Steam launch option for Dune:
$repo_root/scripts/launch-proton-client-probe.sh --stage-to-game-dir -- %command%

Non-mutating overlay experiment:
$repo_root/scripts/launch-proton-client-probe.sh -- %command%

Direct command shape:
WINEDLLOVERRIDES='$WINEDLLOVERRIDES' WINEPATH='$WINEPATH' WINEDLLPATH='$WINEDLLPATH' DUNE_WIN_CLIENT_PROBE_LOG='$DUNE_WIN_CLIENT_PROBE_LOG' <proton-or-wine-command>
EOF
  exit 0
fi

exec "$@"
