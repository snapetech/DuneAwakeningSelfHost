#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

version="${DUNE_WINDOWS_LUA_VERSION:-5.4.8}"
case "$version" in
  5.4.8)
    archive="lua-5.4.8_Win64_dllw6_lib.zip"
    sha256="45506b8fcb83fa3aec17e343a56d415ea22d02319dc38350a4743cd5be3573a1"
    url="https://sourceforge.net/projects/luabinaries/files/5.4.8/Windows%20Libraries/Dynamic/${archive}/download"
    ;;
  *)
    echo "unsupported DUNE_WINDOWS_LUA_VERSION: $version" >&2
    exit 2
    ;;
esac

cache_dir="${DUNE_WINDOWS_LUA_CACHE_DIR:-$repo_root/build/cache/windows-lua-runtime}"
output_dir="${DUNE_WINDOWS_LUA_RUNTIME_DIR:-$repo_root/build/windows-lua-runtime}"
archive_path="$cache_dir/$archive"
lua_dll="$output_dir/lua54.dll"

mkdir -p "$cache_dir" "$output_dir"

if [ ! -f "$archive_path" ] ||
   ! printf '%s  %s\n' "$sha256" "$archive_path" | sha256sum -c --status -; then
  curl -fsSL --retry 3 --connect-timeout 20 -o "$archive_path" "$url"
fi

printf '%s  %s\n' "$sha256" "$archive_path" | sha256sum -c -
unzip -o "$archive_path" lua54.dll -d "$output_dir" >/dev/null
sha256sum "$lua_dll" >"$lua_dll.sha256"

printf 'staged Windows Lua runtime: %s\n' "$lua_dll"
printf 'runtime checksum: %s\n' "$lua_dll.sha256"
