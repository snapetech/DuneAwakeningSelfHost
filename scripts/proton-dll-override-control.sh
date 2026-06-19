#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/proton-dll-override-control.sh --set [options]
  scripts/proton-dll-override-control.sh --unset [options]
  scripts/proton-dll-override-control.sh --query [options]

Options:
  --appid ID          Steam app id. Default: 1172710.
  --prefix PATH      Proton/Wine prefix. Default: Steam compatdata prefix.
  --exe NAME.exe     AppDefaults executable. Default: DuneSandbox-Win64-Shipping.exe.
  --dll NAME         DLL override name without .dll. Default: version.
  --value VALUE      Override value for --set. Default: native,builtin.

This manages HKCU\Software\Wine\AppDefaults\<exe>\DllOverrides so Steam
launches that do not inherit WINEDLLOVERRIDES still load a staged native proxy
DLL. Registry files are backed up before set/unset.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
appid="${DUNE_STEAM_APPID:-1172710}"
steam_root="${STEAM_ROOT:-$HOME/.steam/steam}"
prefix="${DUNE_PROTON_PREFIX:-}"
exe_name="${DUNE_PROTON_OVERRIDE_EXE:-DuneSandbox-Win64-Shipping.exe}"
dll_name="${DUNE_PROTON_OVERRIDE_DLL:-version}"
override_value="${DUNE_PROTON_OVERRIDE_VALUE:-native,builtin}"
action=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --set|--unset|--query)
      action="${1#--}"
      shift
      ;;
    --appid)
      appid="${2:?missing value for --appid}"
      shift 2
      ;;
    --prefix)
      prefix="${2:?missing value for --prefix}"
      shift 2
      ;;
    --exe)
      exe_name="${2:?missing value for --exe}"
      shift 2
      ;;
    --dll)
      dll_name="${2:?missing value for --dll}"
      shift 2
      ;;
    --value)
      override_value="${2:?missing value for --value}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "$action" ]; then
  usage
  exit 2
fi

if [[ "$dll_name" == *.dll ]]; then
  dll_name="${dll_name%.dll}"
fi

if [ -z "$prefix" ]; then
  prefix="$steam_root/steamapps/compatdata/$appid/pfx"
fi

if [ ! -d "$prefix" ]; then
  echo "Proton prefix does not exist: $prefix" >&2
  exit 1
fi

if ! command -v wine >/dev/null 2>&1; then
  echo "wine is required to edit/query the Proton registry" >&2
  exit 1
fi

reg_key="HKCU\\Software\\Wine\\AppDefaults\\$exe_name\\DllOverrides"
build_dir="${DUNE_WINDOWS_CLIENT_LOADER_BUILD_DIR:-$repo_root/build/windows-client-loader}"
backup_root="$build_dir/proton-registry-backups"
manifest="$build_dir/proton-dll-override-manifest.txt"

game_running() {
  pgrep -f 'DuneSandbox-Win64-Shipping.exe|DuneSandbox_BE.exe|DuneSandbox.exe' >/dev/null 2>&1
}

backup_registry() {
  mkdir -p "$backup_root"
  local stamp backup_dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="$backup_root/$stamp"
  mkdir -p "$backup_dir"
  for name in user.reg system.reg userdef.reg; do
    if [ -f "$prefix/$name" ]; then
      cp -a "$prefix/$name" "$backup_dir/$name"
    fi
  done
  {
    printf 'time=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'action=%s\n' "$action"
    printf 'prefix=%s\n' "$prefix"
    printf 'key=%s\n' "$reg_key"
    printf 'dll=%s\n' "$dll_name"
    printf 'value=%s\n' "$override_value"
    printf 'backup=%s\n' "$backup_dir"
  } > "$manifest"
  printf '%s\n' "$backup_dir"
}

wine_reg() {
  WINEPREFIX="$prefix" WINEDEBUG=-all wine reg "$@"
}

case "$action" in
  query)
    wine_reg query "$reg_key" /v "$dll_name" || true
    ;;
  set)
    if game_running && [ "${DUNE_PROTON_OVERRIDE_ALLOW_RUNNING:-false}" != "true" ]; then
      echo "refusing to set DLL override while Dune client processes are running" >&2
      echo "stop the local client first, or set DUNE_PROTON_OVERRIDE_ALLOW_RUNNING=true" >&2
      exit 1
    fi
    backup_dir="$(backup_registry)"
    wine_reg add "$reg_key" /v "$dll_name" /d "$override_value" /f >/dev/null
    printf 'set Proton DLL override: %s %s=%s\n' "$reg_key" "$dll_name" "$override_value"
    printf 'registry backup: %s\n' "$backup_dir"
    ;;
  unset)
    if game_running && [ "${DUNE_PROTON_OVERRIDE_ALLOW_RUNNING:-false}" != "true" ]; then
      echo "refusing to unset DLL override while Dune client processes are running" >&2
      echo "stop the local client first, or set DUNE_PROTON_OVERRIDE_ALLOW_RUNNING=true" >&2
      exit 1
    fi
    backup_dir="$(backup_registry)"
    wine_reg delete "$reg_key" /v "$dll_name" /f >/dev/null 2>&1 || true
    printf 'removed Proton DLL override if present: %s %s\n' "$reg_key" "$dll_name"
    printf 'registry backup: %s\n' "$backup_dir"
    ;;
esac
