#!/usr/bin/env bash
set -euo pipefail

mode="check"
target="all"

usage() {
  cat <<'EOF'
Usage: scripts/ensure-loader-build-toolchain.sh [--check|--install] [--target all|linux|windows]

Checks or installs the build tools needed for:
  linux:   Linux server/client ELF preload loaders
  windows: Windows/Proton PE proxy DLL loader

Default is --check --target all. --install installs missing packages with the
host package manager when a supported manager is available.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      mode="check"
      shift
      ;;
    --install)
      mode="install"
      shift
      ;;
    --target)
      target="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$mode" in
  check|install) ;;
  *)
    printf 'invalid mode: %s\n' "$mode" >&2
    exit 2
    ;;
esac

case "$target" in
  all|linux|windows) ;;
  *)
    printf 'invalid target: %s\n' "$target" >&2
    exit 2
    ;;
esac

have() {
  command -v "$1" >/dev/null 2>&1
}

sudo_cmd=()
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  if have sudo; then
    sudo_cmd=(sudo)
  else
    sudo_cmd=()
  fi
fi

install_packages() {
  if [[ $# -eq 0 ]]; then
    return 0
  fi

  if have apt-get; then
    "${sudo_cmd[@]}" apt-get update
    "${sudo_cmd[@]}" apt-get install -y "$@"
  elif have dnf; then
    "${sudo_cmd[@]}" dnf install -y "$@"
  elif have pacman; then
    "${sudo_cmd[@]}" pacman -S --needed --noconfirm "$@"
  elif have zypper; then
    "${sudo_cmd[@]}" zypper --non-interactive install "$@"
  else
    printf 'no supported package manager found for: %s\n' "$*" >&2
    return 1
  fi
}

package_names() {
  local package_target="$1"
  if have apt-get; then
    case "$package_target" in
      linux) printf '%s\n' cmake ninja-build build-essential clang lld ;;
      windows) printf '%s\n' mingw-w64 clang lld ;;
    esac
  elif have dnf; then
    case "$package_target" in
      linux) printf '%s\n' cmake ninja-build gcc gcc-c++ clang lld ;;
      windows) printf '%s\n' mingw64-gcc mingw64-gcc-c++ clang lld ;;
    esac
  elif have pacman; then
    case "$package_target" in
      linux) printf '%s\n' cmake ninja base-devel clang lld ;;
      windows) printf '%s\n' mingw-w64-gcc clang lld ;;
    esac
  elif have zypper; then
    case "$package_target" in
      linux) printf '%s\n' cmake ninja gcc gcc-c++ clang lld ;;
      windows) printf '%s\n' mingw64-cross-gcc mingw64-cross-gcc-c++ clang lld ;;
    esac
  fi
}

check_linux() {
  local missing=()
  have cmake || missing+=(cmake)
  if ! have ninja && ! have make; then
    missing+=(ninja-or-make)
  fi
  if ! have cc && ! have gcc && ! have clang; then
    missing+=(c-compiler)
  fi

  if [[ ${#missing[@]} -eq 0 ]]; then
    printf 'linux_loader_toolchain=ok\n'
    return 0
  fi

  printf 'linux_loader_toolchain=missing missing=%s\n' "${missing[*]}"
  return 1
}

check_windows() {
  if have x86_64-w64-mingw32-gcc; then
    printf 'windows_loader_toolchain=ok provider=mingw\n'
    return 0
  fi

  local lld_ok=false
  if have ld.lld && ld.lld --version >/dev/null 2>&1; then
    lld_ok=true
  fi

  if have clang && [[ "$lld_ok" == "true" ]] && [[ -f /usr/lib/wine/x86_64-windows/libkernel32.a ]]; then
    printf 'windows_loader_toolchain=ok provider=clang-lld-wine-import-libs\n'
    return 0
  fi

  local missing=()
  have x86_64-w64-mingw32-gcc || missing+=(x86_64-w64-mingw32-gcc)
  have clang || missing+=(clang)
  [[ "$lld_ok" == "true" ]] || missing+=(ld.lld)
  [[ -f /usr/lib/wine/x86_64-windows/libkernel32.a ]] || missing+=(wine-x86_64-import-libs)
  printf 'windows_loader_toolchain=missing missing=%s\n' "${missing[*]}"
  return 1
}

install_target() {
  local package_target="$1"
  mapfile -t packages < <(package_names "$package_target")
  if [[ ${#packages[@]} -eq 0 ]]; then
    printf 'no package mapping for target=%s on this host\n' "$package_target" >&2
    return 1
  fi
  printf 'installing target=%s packages=%s\n' "$package_target" "${packages[*]}"
  install_packages "${packages[@]}"
}

rc=0

if [[ "$target" == "all" || "$target" == "linux" ]]; then
  if ! check_linux; then
    if [[ "$mode" == "install" ]]; then
      install_target linux
      check_linux
    else
      rc=1
    fi
  fi
fi

if [[ "$target" == "all" || "$target" == "windows" ]]; then
  if ! check_windows; then
    if [[ "$mode" == "install" ]]; then
      install_target windows
      check_windows
    else
      rc=1
    fi
  fi
fi

exit "$rc"
