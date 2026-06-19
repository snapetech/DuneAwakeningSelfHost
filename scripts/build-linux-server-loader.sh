#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
source_dir="$repo_root/tools/linux-server-loader"
build_dir="${DUNE_LINUX_SERVER_LOADER_BUILD_DIR:-$repo_root/build/linux-server-loader}"
build_type="${CMAKE_BUILD_TYPE:-RelWithDebInfo}"

"$repo_root/scripts/ensure-loader-build-toolchain.sh" --install --target linux

generator=()
if command -v ninja >/dev/null 2>&1; then
  generator=(-G Ninja)
fi

cmake -S "$source_dir" -B "$build_dir" "${generator[@]}" -DCMAKE_BUILD_TYPE="$build_type"

build_args=(--build "$build_dir" --target dune_server_probe_loader)
if [ -n "${DUNE_LINUX_SERVER_LOADER_JOBS:-}" ]; then
  build_args+=(--parallel "$DUNE_LINUX_SERVER_LOADER_JOBS")
fi
cmake "${build_args[@]}"

loader="$build_dir/libdune_server_probe_loader.so"
if [ ! -f "$loader" ]; then
  loader="$(find "$build_dir" -name libdune_server_probe_loader.so -type f -print -quit)"
fi

if [ -z "$loader" ] || [ ! -f "$loader" ]; then
  echo "built target but did not find libdune_server_probe_loader.so under $build_dir" >&2
  exit 1
fi

printf 'built Linux server probe loader: %s\n' "$loader"
