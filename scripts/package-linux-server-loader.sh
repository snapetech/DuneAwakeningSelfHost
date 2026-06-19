#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
build_script="$repo_root/scripts/build-linux-server-loader.sh"
build_dir="${DUNE_LINUX_SERVER_LOADER_BUILD_DIR:-$repo_root/build/linux-server-loader}"
loader="$build_dir/libdune_server_probe_loader.so"
dist_root="${DUNE_LINUX_SERVER_LOADER_DIST_DIR:-$repo_root/dist/linux-server-loader}"
default_version="$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%dT%H%M%SZ)"
if ! git -C "$repo_root" diff --quiet --ignore-submodules -- 2>/dev/null ||
   ! git -C "$repo_root" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
  default_version="${default_version}-dirty"
fi
version="${DUNE_LINUX_SERVER_LOADER_VERSION:-$default_version}"
platform="linux-x86_64"
package_name="dune-linux-server-loader-${version}-${platform}"
stage="$dist_root/$package_name"
archive="$dist_root/${package_name}.tar.gz"

"$build_script" >/dev/null

if [ ! -f "$loader" ]; then
  echo "missing built loader: $loader" >&2
  exit 1
fi

rm -rf "$stage" "$archive"
mkdir -p \
  "$stage/lib" \
  "$stage/src" \
  "$stage/scripts" \
  "$stage/scripts/research" \
  "$stage/tests" \
  "$stage/docs" \
  "$stage/examples" \
  "$stage/abi"

cp "$loader" "$stage/lib/libdune_server_probe_loader.so"
cp "$repo_root/tools/linux-server-loader/dune_server_probe_loader.c" "$stage/src/dune_server_probe_loader.c"
cp "$repo_root/tools/linux-server-loader/CMakeLists.txt" "$stage/src/CMakeLists.txt"
cp "$repo_root/scripts/summarize-linux-loader-scan.py" "$stage/scripts/summarize-linux-loader-scan.py"
cp "$repo_root/scripts/summarize-linux-loader-xrefs.py" "$stage/scripts/summarize-linux-loader-xrefs.py"
cp "$repo_root/scripts/summarize-linux-loader-anchors.py" "$stage/scripts/summarize-linux-loader-anchors.py"
cp "$repo_root/scripts/validate-elf-signatures.py" "$stage/scripts/validate-elf-signatures.py"
cp "$repo_root/scripts/export-elf-signature-manifest.py" "$stage/scripts/export-elf-signature-manifest.py"
cp "$repo_root/scripts/summarize-client-loader-scan.py" "$stage/scripts/summarize-client-loader-scan.py"
cp "$repo_root/scripts/ue4ss-port-readiness.py" "$stage/scripts/ue4ss-port-readiness.py"
cp "$repo_root/scripts/summarize-ue4ss-port-gaps.py" "$stage/scripts/summarize-ue4ss-port-gaps.py"
cp "$repo_root/scripts/ue4ss-portability-contract.py" "$stage/scripts/ue4ss-portability-contract.py"
cp "$repo_root/scripts/verify-loader-artifacts.py" "$stage/scripts/verify-loader-artifacts.py"
cp "$repo_root/scripts/export-ue-anchor-env.py" "$stage/scripts/export-ue-anchor-env.py"
cp "$repo_root/scripts/export-ue-candidate-globals.py" "$stage/scripts/export-ue-candidate-globals.py"
cp "$repo_root/scripts/summarize-ue-candidate-outcomes.py" "$stage/scripts/summarize-ue-candidate-outcomes.py"
cp "$repo_root/scripts/summarize-ue-candidate-shapes.py" "$stage/scripts/summarize-ue-candidate-shapes.py"
cp "$repo_root/scripts/summarize-ue-code-pointer-context.py" "$stage/scripts/summarize-ue-code-pointer-context.py"
cp "$repo_root/scripts/summarize-elf-ue-string-dataflow.py" "$stage/scripts/summarize-elf-ue-string-dataflow.py"
cp "$repo_root/scripts/summarize-elf-writable-global-refs.py" "$stage/scripts/summarize-elf-writable-global-refs.py"
cp "$repo_root/scripts/summarize-elf-writable-root-shapes.py" "$stage/scripts/summarize-elf-writable-root-shapes.py"
cp "$repo_root/scripts/export-ue-writable-root-shape-candidates.py" "$stage/scripts/export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/research/summarize-elf-pointer-context.py" "$stage/scripts/research/summarize-elf-pointer-context.py"
cp "$repo_root/scripts/summarize-ue-root-recovery-queue.py" "$stage/scripts/summarize-ue-root-recovery-queue.py"
cp "$repo_root/scripts/cluster-ue-root-recovery-queue.py" "$stage/scripts/cluster-ue-root-recovery-queue.py"
cp "$repo_root/scripts/export-ue-root-recovery-candidates.py" "$stage/scripts/export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/promote-ue-anchor-xref-candidates.py" "$stage/scripts/promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/prepare-ue-anchor-canary.py" "$stage/scripts/prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/plan-ue4ss-canary-env.py" "$stage/scripts/plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/canary-linux-server-loader.sh" "$stage/scripts/canary-linux-server-loader.sh"
cp "$repo_root/scripts/ensure-loader-build-toolchain.sh" "$stage/scripts/ensure-loader-build-toolchain.sh"
cp "$repo_root/scripts/test-linux-loader-scan-summary.py" "$stage/tests/test-linux-loader-scan-summary.py"
cp "$repo_root/scripts/test-ue4ss-port-readiness.py" "$stage/tests/test-ue4ss-port-readiness.py"
cp "$repo_root/scripts/test-ue4ss-port-gaps.py" "$stage/tests/test-ue4ss-port-gaps.py"
cp "$repo_root/scripts/test-verify-loader-artifacts.py" "$stage/tests/test-verify-loader-artifacts.py"
cp "$repo_root/scripts/test-loader-container-api-parity.py" "$stage/tests/test-loader-container-api-parity.py"
cp "$repo_root/scripts/test-loader-scheduler-api-parity.py" "$stage/tests/test-loader-scheduler-api-parity.py"
cp "$repo_root/scripts/test-loader-modref-api-parity.py" "$stage/tests/test-loader-modref-api-parity.py"
cp "$repo_root/scripts/test-loader-mod-lifecycle-api-parity.py" "$stage/tests/test-loader-mod-lifecycle-api-parity.py"
cp "$repo_root/scripts/test-loader-unregister-api-parity.py" "$stage/tests/test-loader-unregister-api-parity.py"
cp "$repo_root/scripts/test-loader-fname-api-parity.py" "$stage/tests/test-loader-fname-api-parity.py"
cp "$repo_root/scripts/test-loader-native-identity-parity.py" "$stage/tests/test-loader-native-identity-parity.py"
cp "$repo_root/scripts/test-loader-custom-property-api-parity.py" "$stage/tests/test-loader-custom-property-api-parity.py"
cp "$repo_root/scripts/test-loader-compat-globals-api-parity.py" "$stage/tests/test-loader-compat-globals-api-parity.py"
cp "$repo_root/scripts/test-loader-world-engine-api-parity.py" "$stage/tests/test-loader-world-engine-api-parity.py"
cp "$repo_root/scripts/test-loader-object-notify-api-parity.py" "$stage/tests/test-loader-object-notify-api-parity.py"
cp "$repo_root/scripts/test-loader-console-command-api-parity.py" "$stage/tests/test-loader-console-command-api-parity.py"
cp "$repo_root/scripts/test-loader-anchor-group-parity.py" "$stage/tests/test-loader-anchor-group-parity.py"
cp "$repo_root/scripts/test-loader-scan-preset-parity.py" "$stage/tests/test-loader-scan-preset-parity.py"
cp "$repo_root/scripts/test-promote-ue-anchor-xref-candidates.py" "$stage/tests/test-promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/test-export-ue-candidate-globals.py" "$stage/tests/test-export-ue-candidate-globals.py"
cp "$repo_root/scripts/test-ue-candidate-outcomes.py" "$stage/tests/test-ue-candidate-outcomes.py"
cp "$repo_root/scripts/test-ue-candidate-shapes.py" "$stage/tests/test-ue-candidate-shapes.py"
cp "$repo_root/scripts/test-ue-code-pointer-context.py" "$stage/tests/test-ue-code-pointer-context.py"
cp "$repo_root/scripts/test-elf-ue-string-dataflow.py" "$stage/tests/test-elf-ue-string-dataflow.py"
cp "$repo_root/scripts/test-elf-writable-global-refs.py" "$stage/tests/test-elf-writable-global-refs.py"
cp "$repo_root/scripts/test-elf-writable-root-shapes.py" "$stage/tests/test-elf-writable-root-shapes.py"
cp "$repo_root/scripts/test-export-ue-writable-root-shape-candidates.py" "$stage/tests/test-export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/test-elf-pointer-context.py" "$stage/tests/test-elf-pointer-context.py"
cp "$repo_root/scripts/test-ue-root-recovery-queue.py" "$stage/tests/test-ue-root-recovery-queue.py"
cp "$repo_root/scripts/test-ue-root-recovery-clusters.py" "$stage/tests/test-ue-root-recovery-clusters.py"
cp "$repo_root/scripts/test-export-ue-root-recovery-candidates.py" "$stage/tests/test-export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/test-canary-linux-server-loader.py" "$stage/tests/test-canary-linux-server-loader.py"
cp "$repo_root/scripts/smoke-linux-server-loader.sh" "$stage/examples/smoke-linux-server-loader.sh"
cp "$repo_root/docs/ue4ss-linux-loader-evaluation.md" "$stage/docs/ue4ss-linux-loader-evaluation.md"
if [ -f "$repo_root/docs/linux-server-loader-canary-2026-06-16.md" ]; then
  cp "$repo_root/docs/linux-server-loader-canary-2026-06-16.md" "$stage/docs/linux-server-loader-canary-2026-06-16.md"
fi
if [ -f "$repo_root/docs/linux-server-loader-canary-2026-06-18.md" ]; then
  cp "$repo_root/docs/linux-server-loader-canary-2026-06-18.md" "$stage/docs/linux-server-loader-canary-2026-06-18.md"
fi
if [ -f "$repo_root/docs/current-build-runtime-surface-1988751.md" ]; then
  cp "$repo_root/docs/current-build-runtime-surface-1988751.md" "$stage/docs/current-build-runtime-surface-1988751.md"
fi
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format json --check > "$stage/docs/ue4ss-portability-contract.json"
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format markdown --check > "$stage/docs/ue4ss-portability-contract.md"

cat > "$stage/build-linux-server-loader.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${DUNE_LINUX_SERVER_LOADER_SOURCE_DIR:-$script_dir/src}"
build_dir="${DUNE_LINUX_SERVER_LOADER_BUILD_DIR:-$script_dir/build}"
build_type="${CMAKE_BUILD_TYPE:-RelWithDebInfo}"

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required to build the Linux server loader" >&2
  exit 1
fi

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
EOF

chmod 0755 "$stage/build-linux-server-loader.sh"
chmod 0755 "$stage/scripts/summarize-linux-loader-scan.py"
chmod 0755 "$stage/scripts/summarize-linux-loader-xrefs.py"
chmod 0755 "$stage/scripts/summarize-linux-loader-anchors.py"
chmod 0755 "$stage/scripts/validate-elf-signatures.py"
chmod 0755 "$stage/scripts/export-elf-signature-manifest.py"
chmod 0755 "$stage/scripts/summarize-client-loader-scan.py"
chmod 0755 "$stage/scripts/ue4ss-port-readiness.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-port-gaps.py"
chmod 0755 "$stage/scripts/ue4ss-portability-contract.py"
chmod 0755 "$stage/scripts/verify-loader-artifacts.py"
chmod 0755 "$stage/scripts/export-ue-anchor-env.py"
chmod 0755 "$stage/scripts/export-ue-candidate-globals.py"
chmod 0755 "$stage/scripts/summarize-ue-candidate-outcomes.py"
chmod 0755 "$stage/scripts/summarize-ue-candidate-shapes.py"
chmod 0755 "$stage/scripts/summarize-ue-code-pointer-context.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-string-dataflow.py"
chmod 0755 "$stage/scripts/summarize-elf-writable-global-refs.py"
chmod 0755 "$stage/scripts/summarize-elf-writable-root-shapes.py"
chmod 0755 "$stage/scripts/export-ue-writable-root-shape-candidates.py"
chmod 0755 "$stage/scripts/research/summarize-elf-pointer-context.py"
chmod 0755 "$stage/scripts/summarize-ue-root-recovery-queue.py"
chmod 0755 "$stage/scripts/cluster-ue-root-recovery-queue.py"
chmod 0755 "$stage/scripts/export-ue-root-recovery-candidates.py"
chmod 0755 "$stage/scripts/promote-ue-anchor-xref-candidates.py"
chmod 0755 "$stage/scripts/prepare-ue-anchor-canary.py"
chmod 0755 "$stage/scripts/plan-ue4ss-canary-env.py"
chmod 0755 "$stage/scripts/canary-linux-server-loader.sh"
chmod 0755 "$stage/scripts/ensure-loader-build-toolchain.sh"
chmod 0755 "$stage/examples/smoke-linux-server-loader.sh"
chmod 0755 "$stage/lib/libdune_server_probe_loader.so"

cat > "$stage/examples/env.scan.example" <<'EOF'
# Opt-in runtime loader. Keep disabled until a deliberate canary restart.
DUNE_ENABLE_LINUX_SERVER_PRELOAD=true
DUNE_LINUX_SERVER_PRELOAD=/workspace/build/linux-server-loader/libdune_server_probe_loader.so
DUNE_LINUX_SERVER_PRELOAD_PARTITIONS=7
DUNE_PROBE_LOADER_LOG=/tmp/dune-server-probe-loader.log
DUNE_PROBE_LOADER_TARGET=DuneSandboxServer;DuneSandbox
DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS=0

# Read-only runtime anchor scan.
DUNE_PROBE_LOADER_SCAN_ENABLED=true
DUNE_PROBE_LOADER_SCAN_PRESETS=core,ue,building,brt,deep-desert,gm,cheat
DUNE_PROBE_LOADER_SCAN_STRINGS=DeepDesert;ServerRequestBaseBackup;BaseBackupTool;BuildingSettings;CheatManager;PrintAllowedCommands;PartitionIndex;BuildableMapRegion;FuncomLiveServices;FarmHealth
DUNE_PROBE_LOADER_SCAN_SIGNATURES=brt-action-guard=48 85 c0 74 0a 41 b6 01 41 80 7f 55 01 75 03
DUNE_PROBE_LOADER_SCAN_SIGNATURES_FILE=
DUNE_PROBE_LOADER_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_PROBE_LOADER_SCAN_LOG_MAPPINGS=true
DUNE_PROBE_LOADER_SCAN_MAX_MAPPING_BYTES=536870912

# Explicit read-only UE anchor probes. Fill these with runtime addresses from
# symbol/signature work or prior canary logs before enabling the deeper probes.
DUNE_PROBE_LOADER_UE_ANCHORS=
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES=
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE=
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS=true
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=true
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES=268435456
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS=1
DUNE_PROBE_LOADER_UE_POINTER_PROBE=false
DUNE_PROBE_LOADER_UE_LAYOUT_PROBE=false
DUNE_PROBE_LOADER_UE_LAYOUT_SLOTS=8
DUNE_PROBE_LOADER_UE_UOBJECT_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_NEXT_OFFSET=0x28
DUNE_PROBE_LOADER_UE_REFLECTION_SUPER_OFFSET=0x30
DUNE_PROBE_LOADER_UE_REFLECTION_CHILDREN_OFFSET=0x38
DUNE_PROBE_LOADER_UE_REFLECTION_CHILD_PROPERTIES_OFFSET=0x40
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_LINK_OFFSET=0x48
DUNE_PROBE_LOADER_UE_REFLECTION_FUNCTION_LINK_OFFSET=0x50
DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_WALK=false
DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_PROBE_LOADER_UE_REFLECTION_MAX_FIELDS=16
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_START=0x48
DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_END=0xa0
DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_MAX_BYTES=16
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE=false
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS=128
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_OFFSET=0
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_ITEM_SIZE=24
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_OBJECT_OFFSET=0
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CHUNK_SIZE=65536
DUNE_PROBE_LOADER_UE_FNAME_PROBE=false
DUNE_PROBE_LOADER_UE_FNAME_POOL=
DUNE_PROBE_LOADER_UE_FNAME_POOL_ADDR=
DUNE_PROBE_LOADER_UE_FNAME_POOL_OFFSET=0
DUNE_PROBE_LOADER_UE_FNAME_BLOCKS_OFFSET=0x10
DUNE_PROBE_LOADER_UE_FNAME_STRIDE=2
DUNE_PROBE_LOADER_UE_FNAME_MAX_LENGTH=128
DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS=false
DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS_MAX=16
DUNE_PROBE_LOADER_UE_SELF_TEST_ANCHOR=false

# Loader-owned UE4SS-style dispatch self-tests. Keep disabled in normal live operation.
DUNE_PROBE_LOADER_HOOK_SELF_TEST=false
DUNE_PROBE_LOADER_MOD_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_LIBRARY=
DUNE_PROBE_LOADER_LUA_SELF_TEST_SCRIPT=
DUNE_PROBE_LOADER_LUA_REFLECTION_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_REFLECTION_RAW_SET_ENABLED=false
DUNE_PROBE_LOADER_LUA_REFLECTION_SELF_TEST_SCRIPT=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_PROBE_LOADER_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=
DUNE_PROBE_LOADER_LUA_MODS_ENABLED=false
DUNE_PROBE_LOADER_LUA_MOD_SCRIPTS=
DUNE_PROBE_LOADER_LUA_MOD_DISPATCH_SELF_TEST=false
EOF

cat > "$stage/examples/smoke-cached-funcom-image.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

image="${1:-registry.funcom.com/funcom/self-hosting/seabass-server:1988751-0-shipping}"
loader="${2:-$(pwd)/lib/libdune_server_probe_loader.so}"
log=/tmp/dune-loader-image-scan.log

docker run --rm --pull never --network none \
  -v "$(dirname "$loader"):/probe:ro" \
  --entrypoint /bin/sh \
  "$image" \
  -lc "rm -f '$log'; DUNE_PROBE_LOADER_LOG='$log' DUNE_PROBE_LOADER_FORCE=true DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS=0 DUNE_PROBE_LOADER_SCAN_ENABLED=true DUNE_PROBE_LOADER_SCAN_PRESETS= DUNE_PROBE_LOADER_SCAN_STRINGS='Usage:' DUNE_PROBE_LOADER_SCAN_SIGNATURES='elf=7f 45 4c 46' DUNE_PROBE_LOADER_SCAN_MAX_HITS_PER_NEEDLE=4 LD_PRELOAD=/probe/$(basename "$loader") /usr/bin/true; cat '$log'"
EOF
chmod 0755 "$stage/examples/smoke-cached-funcom-image.sh"

cat > "$stage/README.md" <<EOF
# Dune Linux Server Loader

Package: ${package_name}
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source commit: $(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)
Platform: ${platform}

This is a native Linux server-process loader/probe for this Dune self-host repo.
It is not upstream UE4SS and does not install client mods. It is loaded into a
Linux dedicated-server process with LD_PRELOAD through scripts/run_server_safe.sh.
It supports read-only runtime scans, explicit UE anchor validation,
pointer/layout/UObject/object-array/FName probes, Lua object-handle registration
for UE candidates, and loader-owned hook/mod/Lua/ProcessEvent-shaped self-tests.

## Contents

- lib/libdune_server_probe_loader.so: runtime preload library.
- src/: source used for this package.
- build-linux-server-loader.sh: local rebuild helper.
- scripts/: scan, xref, ELF signature, anchor export, readiness, and portability contract helpers.
- examples/env.scan.example: opt-in environment settings.
- examples/smoke-linux-server-loader.sh: local loader-owned dispatch/Lua smoke test.
- examples/smoke-cached-funcom-image.sh: one-off Docker smoke test for a cached image.
- docs/ue4ss-portability-contract.md: repo-generated all-target portability contract.
- abi/: dependency and symbol-version report.
- SHA256SUMS: checksums for package contents.

## Safe Smoke Test

Local smoke without live Compose or game containers:

\`\`\`bash
examples/smoke-linux-server-loader.sh
\`\`\`

On a host with the Funcom server image cached:

\`\`\`bash
cd ${package_name}
examples/smoke-cached-funcom-image.sh registry.funcom.com/funcom/self-hosting/seabass-server:1988751-0-shipping
\`\`\`

The smoke test uses \`--pull never --network none\` and exits after \`/usr/bin/true\`.
It does not touch live Compose containers.

## Live Canary Shape

For a live canary, copy \`lib/libdune_server_probe_loader.so\` into a path mounted
readable in the target game container, set the variables from
\`examples/env.scan.example\`, then restart exactly one chosen map through the
repo restart/recovery scripts so post-start hooks still run.

Keep \`DUNE_PROBE_LOADER_SCAN_ENABLED=false\` for normal operation after collecting
anchors.

## Reports

\`\`\`bash
scripts/summarize-linux-loader-scan.py /path/to/loader.log
scripts/export-ue-anchor-env.py /path/to/loader.log --loader server --platform server > ue-server-anchors.env
scripts/summarize-linux-loader-xrefs.py /path/to/DuneSandboxServer-Linux-Shipping --loader-log /path/to/loader.log --category brt
scripts/summarize-linux-loader-anchors.py /path/to/DuneSandboxServer-Linux-Shipping --loader-log /path/to/loader.log --category brt
scripts/validate-elf-signatures.py /path/to/DuneSandboxServer-Linux-Shipping --loader-log /path/to/loader.log --category brt
scripts/export-elf-signature-manifest.py /path/to/DuneSandboxServer-Linux-Shipping --loader-log /path/to/loader.log --target-loader server --format signatures > server-signatures.txt
scripts/export-elf-signature-manifest.py /path/to/DuneSandboxServer-Linux-Shipping --loader-log /path/to/loader.log --target-loader server --category ue --format anchor-signatures > server-anchor-signatures.txt
scripts/summarize-ue-candidate-outcomes.py /path/to/loader.log --format markdown > ue-candidate-outcomes.md
scripts/summarize-ue-candidate-outcomes.py /path/to/loader.log --format json > ue-candidate-outcomes.json
scripts/summarize-ue-candidate-shapes.py /path/to/loader.log --format markdown > ue-candidate-shapes.md
scripts/summarize-ue-candidate-shapes.py /path/to/loader.log --format json > ue-candidate-shapes.json
scripts/summarize-ue-code-pointer-context.py /path/to/DuneSandboxServer-Linux-Shipping ue-candidate-outcomes.json --format markdown > ue-code-pointer-context.md
scripts/summarize-ue-root-recovery-queue.py elf-ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format markdown > ue-root-recovery-queue.md
scripts/summarize-ue-root-recovery-queue.py elf-ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format json > ue-root-recovery-queue.json
scripts/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format markdown > ue-root-recovery-clusters.md
scripts/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format json > ue-root-recovery-clusters.json
scripts/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform server --anchor-preset object-discovery --format markdown > ue-root-recovery-candidates.md
scripts/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform server --anchor-preset object-discovery --format json > ue-root-recovery-candidates.json
scripts/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform server --anchor-preset complete --require-source-group-match --format json > ue-root-recovery-candidates-complete-source-matched.json
scripts/prepare-ue-anchor-canary.py --platform server --binary /path/to/DuneSandboxServer-Linux-Shipping --loader-log /path/to/loader.log --output-dir build/server-anchor-canary
scripts/plan-ue4ss-canary-env.py --platform server --server-log /path/to/loader.log --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --max-stage read-only --format json > next-canary.json
scripts/plan-ue4ss-canary-env.py --platform server --server-log /path/to/loader.log --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --max-stage read-only > next-canary.env
scripts/ue4ss-port-readiness.py --server-log /path/to/loader.log --loader server --format json > ue4ss-readiness.json
scripts/summarize-ue4ss-port-gaps.py --readiness-json ue4ss-readiness.json --canary-plan-json next-canary.json --format markdown > ue4ss-port-gaps.md
scripts/ue4ss-portability-contract.py --targets available --format markdown --check > ue4ss-portability-contract.md
python3 -m unittest tests/test-linux-loader-scan-summary.py tests/test-ue4ss-port-readiness.py tests/test-ue4ss-port-gaps.py tests/test-loader-scheduler-api-parity.py tests/test-loader-modref-api-parity.py tests/test-loader-mod-lifecycle-api-parity.py tests/test-loader-unregister-api-parity.py tests/test-loader-fname-api-parity.py tests/test-loader-native-identity-parity.py tests/test-loader-custom-property-api-parity.py tests/test-loader-compat-globals-api-parity.py tests/test-loader-world-engine-api-parity.py tests/test-loader-object-notify-api-parity.py tests/test-loader-console-command-api-parity.py tests/test-loader-anchor-group-parity.py tests/test-loader-scan-preset-parity.py tests/test-export-ue-candidate-globals.py tests/test-ue-candidate-outcomes.py tests/test-ue-candidate-shapes.py tests/test-ue-code-pointer-context.py tests/test-elf-writable-global-refs.py tests/test-elf-writable-root-shapes.py tests/test-ue-root-recovery-queue.py tests/test-ue-root-recovery-clusters.py tests/test-export-ue-root-recovery-candidates.py
\`\`\`

\`export-ue-anchor-env.py\` exports core discovery anchors plus reflection
anchors by default, including anchors from resolved \`ue-anchor-signature\`
records. Unresolved and ambiguous signature anchors remain missing.
\`prepare-ue-anchor-canary.py\` combines the validated UE signature manifest,
loader-consumable anchor signature file, second-pass anchor env, validation
summary, readiness report, object-discovery coverage, and
\`post-canary-verify.sh\` in one output directory. After the next canary, run
\`post-canary-verify.sh [loader-log]\` from that output directory to rebuild
readiness, object-discovery coverage, the UE4SS gap summaries
(\`ue4ss-port-gaps.json\` and \`ue4ss-port-gaps.md\`), and a compact
post-canary summary from the collected log.
\`post-canary-verify-strict.sh [loader-log]\` sets
\`DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true\` and fails until
\`strictRuntimeContract.contractReady=true\`, including \`runtimeRootDiscovery\`.
Runtime root discovery means both \`RuntimeFNamePool\` and
\`RuntimeGUObjectArray\` are validated by FName/object-array consumers, not just
mapped or promoted. Strict readiness also requires exact/promotable signature
validation, target-image \`targetObjectDiscovery\`,
\`targetHooks\`, and \`targetPackageLoadingSurface\` evidence,
\`signatureAnchorReady=true\`, and no \`missingSignatureAnchorReadyKeys\`.
The full UE4SS completion gate remains \`ue4ssLuaApiComplete=true\`, which also
requires \`liveTargetImageCanaryContract.ready=true\` across
\`targetImageAnchors\`, \`runtimePackageLoading\`, \`runtimeObjectRegistry\`,
\`runtimeReflection\`, and
\`runtimeProcessEventDispatch\`/\`runtimeCallFunctionDispatch\`;
self-test-only logs are not enough.
The \`runtimeProcessEventDispatch\` group requires more than a live hook row:
decoded live function path, runtime registry context, active params, raw and
container param samples, Lua context handles, descriptor-backed param accessors,
typed scalar/name/string/struct/enum/object/bool accessor coverage, container
alias/layout methods, and hook routing/alias routing must all be present.
In short: container alias/layout methods are required, not optional.
The \`runtimePackageLoading\` group treats \`luaLoadAssetPackageNativeExecutor\`
as ready only when target-image evidence reports \`NativeExecutorReady=true\`,
\`ExecutorPreflightPassed=true\`, and \`FinalNativeCallEligible=true\`;
dry-run executor shape rows remain diagnostic only.
\`ue4ss-port-readiness.py\` auto-scopes mixed-process logs to loaded
\`DuneSandbox\` target PIDs when no explicit \`--pid\` or \`--exe-substring\`
filter is supplied. Strict completion requires \`targetImageProcess=true\` and
validated \`runtimeRootDiscovery=true\`; helper shell/tool process evidence,
mapped-only runtime roots, or self-test-only logs cannot satisfy target-image
runtime proof.
\`plan-ue4ss-canary-env.py\` reads readiness evidence and emits the next guarded
canary env. It defaults to read-only discovery/reflection and only emits
ProcessEvent/CallFunction hook or live Lua dispatch flags when \`--max-stage\`
allows them.
\`live-hook\` and \`lua-dispatch\` plans also enable bounded live ProcessEvent
call logging so \`ue-process-event-live-context\` and
\`ue-process-event-live-param\` readiness evidence is collected. The planner
also requires non-self-test ProcessEvent and CallFunction hook target evidence,
runtime ProcessEvent context, and live CallFunction Lua dispatch evidence before
live Lua dispatch is considered complete; older or self-test-only readiness
stays at hook-probe/live-hook.
EOF

readelf -d "$loader" > "$stage/abi/readelf-dynamic.txt"
objdump -T "$loader" | grep -E 'GLIBC|GLIBCXX|CXXABI|GCC_' | sort -u > "$stage/abi/symbol-versions.txt" || true
file "$loader" > "$stage/abi/file.txt"

(
  cd "$stage"
  find . -type f ! -name SHA256SUMS -print | sort | sed 's#^\./##' | xargs sha256sum > SHA256SUMS
)

tar -C "$dist_root" -czf "$archive" "$package_name"
sha256sum "$archive" > "${archive}.sha256"

printf 'packaged Linux server loader: %s\n' "$archive"
printf 'package checksum: %s\n' "${archive}.sha256"
