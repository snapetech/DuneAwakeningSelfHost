#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
build_script="$repo_root/scripts/build-linux-client-loader.sh"
build_dir="${DUNE_LINUX_CLIENT_LOADER_BUILD_DIR:-$repo_root/build/linux-client-loader}"
loader="$build_dir/libdune_client_probe_loader.so"
dist_root="${DUNE_LINUX_CLIENT_LOADER_DIST_DIR:-$repo_root/dist/linux-client-loader}"
default_version="$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%dT%H%M%SZ)"
if ! git -C "$repo_root" diff --quiet --ignore-submodules -- 2>/dev/null ||
   ! git -C "$repo_root" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
  default_version="${default_version}-dirty"
fi
version="${DUNE_LINUX_CLIENT_LOADER_VERSION:-$default_version}"
platform="linux-x86_64"
package_name="dune-linux-client-loader-${version}-${platform}"
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
  "$stage/docs" \
  "$stage/examples" \
  "$stage/analysis" \
  "$stage/analysis/research" \
  "$stage/tests" \
  "$stage/abi"

cp "$loader" "$stage/lib/libdune_client_probe_loader.so"
cp "$repo_root/tools/linux-client-loader/dune_client_probe_loader.c" "$stage/src/dune_client_probe_loader.c"
cp "$repo_root/tools/linux-client-loader/CMakeLists.txt" "$stage/src/CMakeLists.txt"
cp "$repo_root/scripts/build-linux-client-loader.sh" "$stage/build-linux-client-loader.sh"
cp "$repo_root/scripts/launch-linux-client-probe.sh" "$stage/examples/launch-native-client.sh"
cp "$repo_root/scripts/verify-client-probe-canary.sh" "$stage/examples/verify-client-probe-canary.sh"
cp "$repo_root/scripts/smoke-linux-client-loader.sh" "$stage/examples/smoke-linux-client-loader.sh"
cp "$repo_root/scripts/summarize-client-loader-scan.py" "$stage/analysis/summarize-client-loader-scan.py"
cp "$repo_root/scripts/summarize-linux-loader-xrefs.py" "$stage/analysis/summarize-linux-loader-xrefs.py"
cp "$repo_root/scripts/summarize-linux-loader-anchors.py" "$stage/analysis/summarize-linux-loader-anchors.py"
cp "$repo_root/scripts/validate-elf-signatures.py" "$stage/analysis/validate-elf-signatures.py"
cp "$repo_root/scripts/export-elf-signature-manifest.py" "$stage/analysis/export-elf-signature-manifest.py"
cp "$repo_root/scripts/summarize-client-ue-anchors.py" "$stage/analysis/summarize-client-ue-anchors.py"
cp "$repo_root/scripts/ue4ss-port-readiness.py" "$stage/analysis/ue4ss-port-readiness.py"
cp "$repo_root/scripts/summarize-ue4ss-port-gaps.py" "$stage/analysis/summarize-ue4ss-port-gaps.py"
cp "$repo_root/scripts/summarize-ue4ss-evidence-inventory.py" "$stage/analysis/summarize-ue4ss-evidence-inventory.py"
cp "$repo_root/scripts/summarize-ue4ss-package-route-evidence.py" "$stage/analysis/summarize-ue4ss-package-route-evidence.py"
cp "$repo_root/scripts/summarize-ue4ss-package-decompile-plan.py" "$stage/analysis/summarize-ue4ss-package-decompile-plan.py"
cp "$repo_root/scripts/summarize-ue4ss-package-external-symbol-plan.py" "$stage/analysis/summarize-ue4ss-package-external-symbol-plan.py"
cp "$repo_root/scripts/plan-ue4ss-package-runtime-trace.py" "$stage/analysis/plan-ue4ss-package-runtime-trace.py"
cp "$repo_root/scripts/ue4ss-portability-contract.py" "$stage/analysis/ue4ss-portability-contract.py"
cp "$repo_root/scripts/verify-loader-artifacts.py" "$stage/analysis/verify-loader-artifacts.py"
cp "$repo_root/scripts/export-ue-anchor-env.py" "$stage/analysis/export-ue-anchor-env.py"
cp "$repo_root/scripts/export-ue-candidate-globals.py" "$stage/analysis/export-ue-candidate-globals.py"
cp "$repo_root/scripts/summarize-ue-candidate-outcomes.py" "$stage/analysis/summarize-ue-candidate-outcomes.py"
cp "$repo_root/scripts/summarize-ue-candidate-shapes.py" "$stage/analysis/summarize-ue-candidate-shapes.py"
cp "$repo_root/scripts/summarize-ue-code-pointer-context.py" "$stage/analysis/summarize-ue-code-pointer-context.py"
cp "$repo_root/scripts/summarize-ue-vtable-candidates.py" "$stage/analysis/summarize-ue-vtable-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-function-neighborhoods.py" "$stage/analysis/summarize-elf-ue-function-neighborhoods.py"
cp "$repo_root/scripts/summarize-elf-ue-function-callgraph.py" "$stage/analysis/summarize-elf-ue-function-callgraph.py"
cp "$repo_root/scripts/summarize-elf-ue-symbol-surface.py" "$stage/analysis/summarize-elf-ue-symbol-surface.py"
cp "$repo_root/scripts/summarize-elf-ue-package-loader-vtables.py" "$stage/analysis/summarize-elf-ue-package-loader-vtables.py"
cp "$repo_root/scripts/summarize-elf-ue-package-wrapper-candidates.py" "$stage/analysis/summarize-elf-ue-package-wrapper-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-package-static-wrapper-candidates.py" "$stage/analysis/summarize-elf-ue-package-static-wrapper-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-rtti-function-object-vtables.py" "$stage/analysis/summarize-elf-ue-rtti-function-object-vtables.py"
cp "$repo_root/scripts/export-process-event-active-validation-candidates.py" "$stage/analysis/export-process-event-active-validation-candidates.py"
cp "$repo_root/scripts/summarize-elf-writable-global-refs.py" "$stage/analysis/summarize-elf-writable-global-refs.py"
cp "$repo_root/scripts/summarize-elf-writable-root-shapes.py" "$stage/analysis/summarize-elf-writable-root-shapes.py"
cp "$repo_root/scripts/export-ue-writable-root-shape-candidates.py" "$stage/analysis/export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/research/summarize-elf-pointer-context.py" "$stage/analysis/research/summarize-elf-pointer-context.py"
cp "$repo_root/scripts/summarize-ue-root-recovery-queue.py" "$stage/analysis/summarize-ue-root-recovery-queue.py"
cp "$repo_root/scripts/cluster-ue-root-recovery-queue.py" "$stage/analysis/cluster-ue-root-recovery-queue.py"
cp "$repo_root/scripts/export-ue-root-recovery-candidates.py" "$stage/analysis/export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/promote-ue-anchor-xref-candidates.py" "$stage/analysis/promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/prepare-ue-anchor-canary.py" "$stage/analysis/prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/plan-ue4ss-canary-env.py" "$stage/analysis/plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/ensure-loader-build-toolchain.sh" "$stage/analysis/ensure-loader-build-toolchain.sh"
cp "$repo_root/scripts/test-client-loader-scan-summary.py" "$stage/tests/test-client-loader-scan-summary.py"
cp "$repo_root/scripts/test-linux-loader-xrefs.py" "$stage/tests/test-linux-loader-xrefs.py"
cp "$repo_root/scripts/test-linux-loader-anchors.py" "$stage/tests/test-linux-loader-anchors.py"
cp "$repo_root/scripts/test-elf-signatures.py" "$stage/tests/test-elf-signatures.py"
cp "$repo_root/scripts/test-elf-signature-manifest.py" "$stage/tests/test-elf-signature-manifest.py"
cp "$repo_root/scripts/test-client-ue-anchors.py" "$stage/tests/test-client-ue-anchors.py"
cp "$repo_root/scripts/test-ue4ss-port-readiness.py" "$stage/tests/test-ue4ss-port-readiness.py"
cp "$repo_root/scripts/test-ue4ss-port-gaps.py" "$stage/tests/test-ue4ss-port-gaps.py"
cp "$repo_root/scripts/test-ue4ss-portability-contract.py" "$stage/tests/test-ue4ss-portability-contract.py"
cp "$repo_root/scripts/test-ue4ss-evidence-inventory.py" "$stage/tests/test-ue4ss-evidence-inventory.py"
cp "$repo_root/scripts/test-ue4ss-package-route-evidence.py" "$stage/tests/test-ue4ss-package-route-evidence.py"
cp "$repo_root/scripts/test-ue4ss-package-decompile-plan.py" "$stage/tests/test-ue4ss-package-decompile-plan.py"
cp "$repo_root/scripts/test-ue4ss-package-external-symbol-plan.py" "$stage/tests/test-ue4ss-package-external-symbol-plan.py"
cp "$repo_root/scripts/test-ue4ss-package-runtime-trace-plan.py" "$stage/tests/test-ue4ss-package-runtime-trace-plan.py"
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
cp "$repo_root/scripts/test-export-ue-anchor-env.py" "$stage/tests/test-export-ue-anchor-env.py"
cp "$repo_root/scripts/test-export-ue-candidate-globals.py" "$stage/tests/test-export-ue-candidate-globals.py"
cp "$repo_root/scripts/test-ue-candidate-outcomes.py" "$stage/tests/test-ue-candidate-outcomes.py"
cp "$repo_root/scripts/test-ue-candidate-shapes.py" "$stage/tests/test-ue-candidate-shapes.py"
cp "$repo_root/scripts/test-ue-code-pointer-context.py" "$stage/tests/test-ue-code-pointer-context.py"
cp "$repo_root/scripts/test-ue-vtable-candidates.py" "$stage/tests/test-ue-vtable-candidates.py"
cp "$repo_root/scripts/test-elf-ue-function-neighborhoods.py" "$stage/tests/test-elf-ue-function-neighborhoods.py"
cp "$repo_root/scripts/test-elf-ue-function-callgraph.py" "$stage/tests/test-elf-ue-function-callgraph.py"
cp "$repo_root/scripts/test-elf-ue-package-loader-vtables.py" "$stage/tests/test-elf-ue-package-loader-vtables.py"
cp "$repo_root/scripts/test-elf-ue-package-wrapper-candidates.py" "$stage/tests/test-elf-ue-package-wrapper-candidates.py"
cp "$repo_root/scripts/test-elf-ue-package-static-wrapper-candidates.py" "$stage/tests/test-elf-ue-package-static-wrapper-candidates.py"
cp "$repo_root/scripts/test-elf-ue-rtti-function-object-vtables.py" "$stage/tests/test-elf-ue-rtti-function-object-vtables.py"
cp "$repo_root/scripts/test-export-process-event-active-validation-candidates.py" "$stage/tests/test-export-process-event-active-validation-candidates.py"
cp "$repo_root/scripts/test-elf-writable-global-refs.py" "$stage/tests/test-elf-writable-global-refs.py"
cp "$repo_root/scripts/test-elf-writable-root-shapes.py" "$stage/tests/test-elf-writable-root-shapes.py"
cp "$repo_root/scripts/test-export-ue-writable-root-shape-candidates.py" "$stage/tests/test-export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/test-elf-pointer-context.py" "$stage/tests/test-elf-pointer-context.py"
cp "$repo_root/scripts/test-ue-root-recovery-queue.py" "$stage/tests/test-ue-root-recovery-queue.py"
cp "$repo_root/scripts/test-ue-root-recovery-clusters.py" "$stage/tests/test-ue-root-recovery-clusters.py"
cp "$repo_root/scripts/test-export-ue-root-recovery-candidates.py" "$stage/tests/test-export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/test-promote-ue-anchor-xref-candidates.py" "$stage/tests/test-promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/test-prepare-ue-anchor-canary.py" "$stage/tests/test-prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/test-plan-ue4ss-canary-env.py" "$stage/tests/test-plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/test-client-launch-preflight.py" "$stage/tests/test-client-launch-preflight.py"
cp "$repo_root/docs/client-loader-support.md" "$stage/docs/client-loader-support.md"
cp "$repo_root/docs/linux-client-loader.md" "$stage/docs/linux-client-loader.md"
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format json --check > "$stage/docs/ue4ss-portability-contract.json"
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format markdown --check > "$stage/docs/ue4ss-portability-contract.md"

chmod 0755 "$stage/build-linux-client-loader.sh"
chmod 0755 "$stage/examples/launch-native-client.sh"
chmod 0755 "$stage/examples/verify-client-probe-canary.sh"
chmod 0755 "$stage/examples/smoke-linux-client-loader.sh"
chmod 0755 "$stage/analysis/summarize-client-loader-scan.py"
chmod 0755 "$stage/analysis/summarize-linux-loader-xrefs.py"
chmod 0755 "$stage/analysis/summarize-linux-loader-anchors.py"
chmod 0755 "$stage/analysis/validate-elf-signatures.py"
chmod 0755 "$stage/analysis/export-elf-signature-manifest.py"
chmod 0755 "$stage/analysis/summarize-client-ue-anchors.py"
chmod 0755 "$stage/analysis/ue4ss-port-readiness.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-port-gaps.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-evidence-inventory.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-package-route-evidence.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-package-decompile-plan.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-package-external-symbol-plan.py"
chmod 0755 "$stage/analysis/plan-ue4ss-package-runtime-trace.py"
chmod 0755 "$stage/analysis/ue4ss-portability-contract.py"
chmod 0755 "$stage/analysis/verify-loader-artifacts.py"
chmod 0755 "$stage/analysis/export-ue-anchor-env.py"
chmod 0755 "$stage/analysis/export-ue-candidate-globals.py"
chmod 0755 "$stage/analysis/summarize-ue-candidate-outcomes.py"
chmod 0755 "$stage/analysis/summarize-ue-candidate-shapes.py"
chmod 0755 "$stage/analysis/summarize-ue-code-pointer-context.py"
chmod 0755 "$stage/analysis/summarize-ue-vtable-candidates.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-function-neighborhoods.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-function-callgraph.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-symbol-surface.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-package-loader-vtables.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-package-wrapper-candidates.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-package-static-wrapper-candidates.py"
chmod 0755 "$stage/analysis/summarize-elf-ue-rtti-function-object-vtables.py"
chmod 0755 "$stage/analysis/export-process-event-active-validation-candidates.py"
chmod 0755 "$stage/analysis/summarize-elf-writable-global-refs.py"
chmod 0755 "$stage/analysis/summarize-elf-writable-root-shapes.py"
chmod 0755 "$stage/analysis/export-ue-writable-root-shape-candidates.py"
chmod 0755 "$stage/analysis/research/summarize-elf-pointer-context.py"
chmod 0755 "$stage/analysis/summarize-ue-root-recovery-queue.py"
chmod 0755 "$stage/analysis/cluster-ue-root-recovery-queue.py"
chmod 0755 "$stage/analysis/export-ue-root-recovery-candidates.py"
chmod 0755 "$stage/analysis/promote-ue-anchor-xref-candidates.py"
chmod 0755 "$stage/analysis/prepare-ue-anchor-canary.py"
chmod 0755 "$stage/analysis/plan-ue4ss-canary-env.py"
chmod 0755 "$stage/analysis/ensure-loader-build-toolchain.sh"
chmod 0755 "$stage/lib/libdune_client_probe_loader.so"

cat > "$stage/examples/env.scan.example" <<'EOF'
# Native Linux ELF client preload. This does not modify installed game files.
DUNE_LINUX_CLIENT_PRELOAD=/abs/path/libdune_client_probe_loader.so
DUNE_CLIENT_PROBE_LOG=/tmp/dune-client-probe-loader.log
DUNE_CLIENT_PROBE_FORCE=true
DUNE_CLIENT_PROBE_LOG_MODULES=true
DUNE_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=0

# Read-only runtime anchor scan.
DUNE_CLIENT_PROBE_SCAN_ENABLED=true
DUNE_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
DUNE_CLIENT_PROBE_SCAN_STRINGS=ProcessEvent;FNamePool;GUObjectArray;CheatManager
DUNE_CLIENT_PROBE_SCAN_SIGNATURES=
DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE=
DUNE_CLIENT_PROBE_UE_ANCHORS=
DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS=
DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=
DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS=true
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=true
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES=268435456
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS=1
DUNE_CLIENT_PROBE_UE_POINTER_PROBE=false
DUNE_CLIENT_PROBE_UE_LAYOUT_PROBE=false
DUNE_CLIENT_PROBE_UE_UOBJECT_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_NEXT_OFFSET=0x28
DUNE_CLIENT_PROBE_UE_REFLECTION_SUPER_OFFSET=0x30
DUNE_CLIENT_PROBE_UE_REFLECTION_CHILDREN_OFFSET=0x38
DUNE_CLIENT_PROBE_UE_REFLECTION_CHILD_PROPERTIES_OFFSET=0x40
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_LINK_OFFSET=0x48
DUNE_CLIENT_PROBE_UE_REFLECTION_FUNCTION_LINK_OFFSET=0x50
DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=false
DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_CLIENT_PROBE_UE_REFLECTION_MAX_FIELDS=16
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_START=0x48
DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_END=0xa0
DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_MAX_BYTES=16
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=false
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS=128
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX=32
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=0
DUNE_CLIENT_PROBE_UE_FNAME_PROBE=false
DUNE_CLIENT_PROBE_UE_FNAME_POOL=
DUNE_CLIENT_PROBE_UE_FNAME_BLOCKS_OFFSET=0x10
DUNE_CLIENT_PROBE_UE_FNAME_STRIDE=2
DUNE_CLIENT_PROBE_UE_FNAME_MAX_LENGTH=128
DUNE_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE=false
DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=false
DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS_MAX=16
DUNE_CLIENT_PROBE_UE_LAYOUT_SLOTS=8
DUNE_CLIENT_PROBE_HOOK_SELF_TEST=false
DUNE_CLIENT_PROBE_MOD_SELF_TEST=false
DUNE_CLIENT_PROBE_LUA_SELF_TEST=false
DUNE_CLIENT_PROBE_LUA_LIBRARY=
DUNE_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT=
DUNE_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST=false
DUNE_CLIENT_PROBE_LUA_REFLECTION_RAW_SET_ENABLED=false
DUNE_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST_SCRIPT=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_IMAGE_OFFSET=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_IMAGE_OFFSET=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OUTPUT_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_EXECUTOR_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_FORCE_CALL=true
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=
DUNE_CLIENT_PROBE_LUA_MODS_ENABLED=false
DUNE_CLIENT_PROBE_LUA_MOD_SCRIPTS=
DUNE_CLIENT_PROBE_LUA_MOD_ROOT=
DUNE_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=false
DUNE_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_CLIENT_PROBE_SCAN_MAX_MAPPING_BYTES=268435456
EOF

cat > "$stage/README.md" <<EOF
# Dune Linux Client Loader

Package: ${package_name}
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source commit: $(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)
Platform: ${platform}

This is a native Linux client-process preload/probe for this repo. It is not
upstream UE4SS yet. It collects read-only runtime anchors from an ELF client
process and refuses Windows/PE Proton targets in the launch wrapper.

## Contents

- lib/libdune_client_probe_loader.so: runtime preload library.
- src/: source used for this package.
- build-linux-client-loader.sh: local rebuild helper.
- examples/launch-native-client.sh: launch wrapper for a native ELF client.
- examples/verify-client-probe-canary.sh: post-run prepared-canary verifier and artifact collector.
- examples/smoke-linux-client-loader.sh: local smoke test.
- examples/env.scan.example: scan environment settings.
- analysis/: log summarizer, ELF xref, nearby-anchor, UE readiness, and portability contract tools.
- analysis/summarize-ue-candidate-outcomes.py: candidate-global runtime outcome classifier.
- analysis/summarize-ue-candidate-shapes.py: candidate-global shape/failure classifier.
- analysis/summarize-ue-code-pointer-context.py: static ELF context for rejected code-pointer candidates.
- analysis/summarize-ue-vtable-candidates.py: ranked ProcessEvent vtable hook-probe shortlist from runtime logs.
- analysis/summarize-elf-ue-function-neighborhoods.py: static executable-neighborhood report for xref, init-array, or explicit function seeds.
- analysis/summarize-elf-ue-function-callgraph.py: bounded direct-call report for exact function seeds and package-anchor promotion blockers.
- analysis/summarize-elf-ue-symbol-surface.py: target-image UE-like static/dynamic symbol surface inventory.
- analysis/summarize-elf-ue-package-loader-vtables.py: target-image package-loader vtable method candidate inventory.
- analysis/summarize-elf-ue-package-wrapper-candidates.py: direct caller/wrapper queue for package-loader method candidates.
- analysis/summarize-elf-ue-package-static-wrapper-candidates.py: static/free-function package wrapper symbol and string queue.
- analysis/summarize-elf-ue-rtti-function-object-vtables.py: RTTI function-object vtable queue for streamable/package owner-method leads.
- analysis/export-process-event-active-validation-candidates.py: reviewable ProcessEvent active-validation candidate exporter.
- analysis/summarize-ue-root-recovery-queue.py: ranked static function queue for root-recovery review.
- analysis/cluster-ue-root-recovery-queue.py: range/family clustering for queued root-recovery functions.
- analysis/export-ue-root-recovery-candidates.py: bounded candidate-global export from root-recovery queue/cluster evidence.
- analysis/export-ue-candidate-globals.py: bounded candidate-global env exporter with reject-log feedback.
- tests/: unit tests for the packaged analysis tools.
- docs/client-loader-support.md: shared Linux/Windows support matrix.
- docs/ue4ss-portability-contract.md: repo-generated all-target portability contract.
- loader-artifact-verification.txt and loader-artifact-verification.json: package-root artifact verification outputs.
- abi/: dependency and symbol-version report.
- SHA256SUMS: checksums for package contents.

## Native Client Launch

\`\`\`bash
examples/launch-native-client.sh -- /path/to/DuneSandbox-Linux-Shipping
\`\`\`

The wrapper uses \`LD_PRELOAD\` and does not edit Steam or game files. If the
target is a Windows/PE executable under Proton, it exits and reports that a
Windows DLL/proxy/injection path is required instead.

For non-Dune native UE targets, pass the executable path directly to the
wrapper and set \`DUNE_CLIENT_PROBE_TARGET\` to a semicolon-delimited target
executable fragment list. Each target executable fragment should match the
game process name, for example
\`DUNE_CLIENT_PROBE_TARGET=ExampleGame-Linux-Shipping;ExampleGame\`.
\`DUNE_CLIENT_PROBE_FORCE=true\` is suitable for local smoke tests where the
target filter is intentionally bypassed. These controls keep the package
usable with another Unreal title without editing installed game files or
rebuilding Dune-specific paths into the loader.

Large signature manifests should be passed with
\`DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE=/path/to/client-signatures.txt\`.
Validated UE anchor signatures should be passed separately with
\`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=/path/to/client-anchor-signatures.txt\`.

## Smoke Test

\`\`\`bash
examples/smoke-linux-client-loader.sh
\`\`\`

## Analysis

\`\`\`bash
TARGET_BINARY="\${TARGET_BINARY:-/path/to/DuneSandbox-Linux-Shipping}"
TARGET_FILTER_ARGS=(\${TARGET_FILTER_ARGS[@]:---exe-substring DuneSandbox})

analysis/summarize-client-loader-scan.py /tmp/dune-client-probe-loader.log
analysis/summarize-linux-loader-xrefs.py "\$TARGET_BINARY" --loader-log /tmp/dune-client-probe-loader.log "\${TARGET_FILTER_ARGS[@]}" --category cheat
analysis/summarize-linux-loader-anchors.py "\$TARGET_BINARY" --loader-log /tmp/dune-client-probe-loader.log "\${TARGET_FILTER_ARGS[@]}" --category cheat
analysis/validate-elf-signatures.py "\$TARGET_BINARY" --loader-log /tmp/dune-client-probe-loader.log "\${TARGET_FILTER_ARGS[@]}" --category cheat
analysis/export-elf-signature-manifest.py "\$TARGET_BINARY" --loader-log /tmp/dune-client-probe-loader.log --target-loader linux-client "\${TARGET_FILTER_ARGS[@]}" --format signatures > client-signatures.txt
analysis/export-elf-signature-manifest.py "\$TARGET_BINARY" --loader-log /tmp/dune-client-probe-loader.log --target-loader linux-client "\${TARGET_FILTER_ARGS[@]}" --category ue --format anchor-signatures > client-anchor-signatures.txt
analysis/summarize-client-ue-anchors.py /tmp/dune-client-probe-loader.log
analysis/export-ue-anchor-env.py /tmp/dune-client-probe-loader.log --loader linux-client --platform linux > ue-anchors.env
analysis/summarize-ue-candidate-outcomes.py /tmp/dune-client-probe-loader.log --format markdown > ue-candidate-outcomes.md
analysis/summarize-ue-candidate-outcomes.py /tmp/dune-client-probe-loader.log --format json > ue-candidate-outcomes.json
analysis/summarize-ue-candidate-shapes.py /tmp/dune-client-probe-loader.log --format markdown > ue-candidate-shapes.md
analysis/summarize-ue-candidate-shapes.py /tmp/dune-client-probe-loader.log --format json > ue-candidate-shapes.json
analysis/summarize-ue-code-pointer-context.py "\$TARGET_BINARY" ue-candidate-outcomes.json --format markdown > ue-code-pointer-context.md
analysis/summarize-ue-vtable-candidates.py /tmp/dune-client-probe-loader.log --format markdown > ue-vtable-candidates.md
analysis/summarize-ue-vtable-candidates.py /tmp/dune-client-probe-loader.log --format json > ue-vtable-candidates.json
analysis/summarize-elf-ue-function-neighborhoods.py "\$TARGET_BINARY" --seed reviewed-function=0x0 --format markdown > elf-ue-function-neighborhoods.example.md
analysis/summarize-elf-ue-function-callgraph.py "\$TARGET_BINARY" --seed reviewed-function=0x0 --depth 1 --format markdown > elf-ue-function-callgraph.example.md
analysis/summarize-elf-ue-symbol-surface.py "\$TARGET_BINARY" --format markdown > ue-symbol-surface.md
analysis/summarize-elf-ue-symbol-surface.py "\$TARGET_BINARY" --format json > ue-symbol-surface.json
analysis/summarize-elf-ue-package-loader-vtables.py "\$TARGET_BINARY" --format markdown > ue-package-loader-vtables.md
analysis/summarize-elf-ue-package-loader-vtables.py "\$TARGET_BINARY" --format json > ue-package-loader-vtables.json
analysis/summarize-elf-ue-package-loader-vtables.py "\$TARGET_BINARY" --no-default-class-filters --address reviewed-table=0x0 --format markdown > ue-reviewed-table-vtables.md
analysis/summarize-elf-ue-package-wrapper-candidates.py "\$TARGET_BINARY" --package-loader-vtables-json ue-package-loader-vtables.json --vtable-filter FAsyncPackage2 --slot 66 --slot 69 --slot 94 --slot 95 --format markdown > ue-package-wrapper-candidates.md
analysis/summarize-elf-ue-package-wrapper-candidates.py "\$TARGET_BINARY" --package-loader-vtables-json ue-package-loader-vtables.json --vtable-filter FAsyncPackage2 --slot 66 --slot 69 --slot 94 --slot 95 --format json > ue-package-wrapper-candidates.json
analysis/summarize-elf-ue-package-static-wrapper-candidates.py "\$TARGET_BINARY" --format markdown > ue-package-static-wrapper-candidates.md
analysis/summarize-elf-ue-package-static-wrapper-candidates.py "\$TARGET_BINARY" --format json > ue-package-static-wrapper-candidates.json
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --static-wrapper-json ue-package-static-wrapper-candidates.json --format markdown > ue-rtti-function-object-vtables.md
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --static-wrapper-json ue-package-static-wrapper-candidates.json --format json > ue-rtti-function-object-vtables.json
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --format markdown > ue-package-symbol-surface-vtables.md
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --format json > ue-package-symbol-surface-vtables.json
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UPackage*' --symbol-needle EAsyncLoadingResult --format markdown > ue-async-package-delegate-vtables.md
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UPackage*' --symbol-needle EAsyncLoadingResult --format json > ue-async-package-delegate-vtables.json
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UKismetSystemLibrary::LoadAsset' --symbol-needle FLoadAssetAction --symbol-needle FLoadAssetClassAction --format markdown > ue-kismet-loadasset-vtables.md
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UKismetSystemLibrary::LoadAsset' --symbol-needle FLoadAssetAction --symbol-needle FLoadAssetClassAction --format json > ue-kismet-loadasset-vtables.json
analysis/summarize-elf-ue-function-callgraph.py "\$TARGET_BINARY" --seed FLoadAssetActionBase_dispatch=0x0 --seed KismetLoadAsset_helper=0x0 --depth 2 --format markdown > ue-kismet-loadasset-callgraph.md
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --raw-typeinfo-needle FLinkerLoad --raw-typeinfo-needle FAsyncPackage --raw-typeinfo-needle FAsyncLoadingThread --raw-typeinfo-needle FAsyncArchive --format markdown > ue-raw-typeinfo-linker-async-vtables.md
analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --raw-typeinfo-needle FLinkerLoad --raw-typeinfo-needle FAsyncPackage --raw-typeinfo-needle FAsyncLoadingThread --raw-typeinfo-needle FAsyncArchive --format json > ue-raw-typeinfo-linker-async-vtables.json
read -r -a RAW_TYPEINFO_SEEDS <<< "\$(analysis/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --raw-typeinfo-needle FLinkerLoad --raw-typeinfo-needle FAsyncPackage --raw-typeinfo-needle FAsyncLoadingThread --raw-typeinfo-needle FAsyncArchive --seed-limit 16 --format seeds)"
analysis/summarize-elf-ue-function-callgraph.py "\$TARGET_BINARY" "\${RAW_TYPEINFO_SEEDS[@]}" --depth 2 --format markdown > ue-raw-typeinfo-linker-async-callgraph.md
analysis/summarize-elf-writable-global-refs.py "\$TARGET_BINARY" --target reviewed-global=0x0 --format markdown > writable-global-reviewed.md
analysis/summarize-ue4ss-package-route-evidence.py --format markdown > ue4ss-package-route-evidence.md
analysis/summarize-ue4ss-package-route-evidence.py --format json > ue4ss-package-route-evidence.json
analysis/summarize-ue4ss-package-decompile-plan.py --format markdown > ue4ss-package-decompile-plan.md
analysis/summarize-ue4ss-package-decompile-plan.py --format json > ue4ss-package-decompile-plan.json
analysis/summarize-ue4ss-package-external-symbol-plan.py --format markdown > ue4ss-package-external-symbol-plan.md
analysis/summarize-ue4ss-package-external-symbol-plan.py --format json > ue4ss-package-external-symbol-plan.json
analysis/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format markdown > ue4ss-package-runtime-trace-plan.md
analysis/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format json > ue4ss-package-runtime-trace-plan.json
analysis/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format gdb > ue4ss-package-runtime-trace.gdb
analysis/summarize-client-loader-scan.py /tmp/dune-client-probe-loader.log --format json > client-summary.json
analysis/export-process-event-active-validation-candidates.py client-summary.json --format markdown > process-event-active-validation-candidates.md
analysis/export-process-event-active-validation-candidates.py client-summary.json --format json > process-event-active-validation-candidates.json
analysis/summarize-ue-root-recovery-queue.py elf-ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format markdown > ue-root-recovery-queue.md
analysis/summarize-ue-root-recovery-queue.py elf-ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format json > ue-root-recovery-queue.json
analysis/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format markdown > ue-root-recovery-clusters.md
analysis/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format json > ue-root-recovery-clusters.json
analysis/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform linux-client --anchor-preset object-discovery --format markdown > ue-root-recovery-candidates.md
analysis/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform linux-client --anchor-preset object-discovery --format json > ue-root-recovery-candidates.json
analysis/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform linux-client --anchor-preset complete --require-source-group-match --format json > ue-root-recovery-candidates-complete-source-matched.json
analysis/prepare-ue-anchor-canary.py --platform linux-client --binary "\$TARGET_BINARY" --loader-log /tmp/dune-client-probe-loader.log --output-dir build/linux-client-anchor-canary
examples/verify-client-probe-canary.sh --platform linux-client --prep-dir build/linux-client-anchor-canary --log /tmp/dune-client-probe-loader.log --output-dir backups/client-probe-canary/linux-client/manual
analysis/plan-ue4ss-canary-env.py --platform linux-client --client-log /tmp/dune-client-probe-loader.log "\${TARGET_FILTER_ARGS[@]}" --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --active-validation-candidates-json process-event-active-validation-candidates.json --max-stage read-only --format json > next-canary.json
analysis/plan-ue4ss-canary-env.py --platform linux-client --client-log /tmp/dune-client-probe-loader.log "\${TARGET_FILTER_ARGS[@]}" --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --active-validation-candidates-json process-event-active-validation-candidates.json --max-stage read-only > next-canary.env
analysis/ue4ss-port-readiness.py --client-log /tmp/dune-client-probe-loader.log --loader linux-client "\${TARGET_FILTER_ARGS[@]}" --anchor-coverage-json build/linux-client-anchor-canary/anchor-coverage.json --format json > ue4ss-readiness.json
analysis/summarize-ue4ss-port-gaps.py --readiness-json ue4ss-readiness.json --canary-plan-json next-canary.json --format markdown > ue4ss-port-gaps.md
analysis/summarize-ue4ss-evidence-inventory.py build backups /tmp --limit 12 --format markdown > ue4ss-evidence-inventory.md
analysis/summarize-ue4ss-package-route-evidence.py --format markdown > ue4ss-package-route-evidence.md
analysis/summarize-ue4ss-package-decompile-plan.py --format markdown > ue4ss-package-decompile-plan.md
analysis/summarize-ue4ss-package-external-symbol-plan.py --format markdown > ue4ss-package-external-symbol-plan.md
analysis/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format markdown > ue4ss-package-runtime-trace-plan.md
analysis/verify-loader-artifacts.py --target linux-client --package-root . --package-target linux-client --package-only --format text > loader-artifact-verification.txt
analysis/verify-loader-artifacts.py --target linux-client --package-root . --package-target linux-client --package-only --format json > loader-artifact-verification.json
analysis/ue4ss-portability-contract.py --targets available --format markdown --check > ue4ss-portability-contract.md
python3 -m unittest tests/test-client-loader-scan-summary.py tests/test-linux-loader-xrefs.py tests/test-linux-loader-anchors.py tests/test-elf-signatures.py tests/test-elf-signature-manifest.py tests/test-client-ue-anchors.py tests/test-ue4ss-port-readiness.py tests/test-ue4ss-port-gaps.py tests/test-ue4ss-portability-contract.py tests/test-ue4ss-evidence-inventory.py tests/test-ue4ss-package-route-evidence.py tests/test-ue4ss-package-decompile-plan.py tests/test-ue4ss-package-external-symbol-plan.py tests/test-ue4ss-package-runtime-trace-plan.py tests/test-loader-scheduler-api-parity.py tests/test-loader-modref-api-parity.py tests/test-loader-mod-lifecycle-api-parity.py tests/test-loader-unregister-api-parity.py tests/test-loader-fname-api-parity.py tests/test-loader-native-identity-parity.py tests/test-loader-custom-property-api-parity.py tests/test-loader-compat-globals-api-parity.py tests/test-loader-world-engine-api-parity.py tests/test-loader-object-notify-api-parity.py tests/test-loader-console-command-api-parity.py tests/test-loader-anchor-group-parity.py tests/test-loader-scan-preset-parity.py tests/test-export-ue-anchor-env.py tests/test-export-ue-candidate-globals.py tests/test-ue-candidate-outcomes.py tests/test-ue-candidate-shapes.py tests/test-ue-code-pointer-context.py tests/test-ue-vtable-candidates.py tests/test-elf-ue-function-neighborhoods.py tests/test-elf-ue-function-callgraph.py tests/test-elf-ue-package-loader-vtables.py tests/test-elf-ue-package-wrapper-candidates.py tests/test-elf-ue-package-static-wrapper-candidates.py tests/test-elf-ue-rtti-function-object-vtables.py tests/test-export-process-event-active-validation-candidates.py tests/test-elf-writable-global-refs.py tests/test-elf-writable-root-shapes.py tests/test-ue-root-recovery-queue.py tests/test-ue-root-recovery-clusters.py tests/test-export-ue-root-recovery-candidates.py tests/test-promote-ue-anchor-xref-candidates.py tests/test-prepare-ue-anchor-canary.py tests/test-plan-ue4ss-canary-env.py tests/test-client-launch-preflight.py
\`\`\`

\`export-ue-anchor-env.py\` exports core discovery anchors plus reflection
anchors by default, including anchors from resolved \`ue-anchor-signature\`
records. Unresolved and ambiguous signature anchors remain missing.
\`prepare-ue-anchor-canary.py\` combines the validated UE signature manifest,
loader-consumable anchor signature file, second-pass anchor env, validation
summary, readiness report, object-discovery coverage, and
\`post-canary-verify.sh\` in one output directory. After the next canary, run
\`examples/verify-client-probe-canary.sh --platform linux-client --prep-dir
[prepared-dir] --log [loader-log]\` to copy the log and prepared anchors into a
timestamped evidence directory, run the selected verifier, and preserve
readiness, object-discovery coverage, the UE4SS gap summaries
(\`ue4ss-port-gaps.json\` and \`ue4ss-port-gaps.md\`), and a compact
post-canary summary from the collected log.
\`post-canary-verify-strict.sh [loader-log]\` sets
\`DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true\` and fails until
\`strictRuntimeContract.contractReady=true\`, including \`runtimeRootDiscovery\`.
\`examples/verify-client-probe-canary.sh --strict\` also requires
\`summarize-ue4ss-evidence-inventory.py\` to write
\`ue4ss-evidence-inventory.json\` and \`ue4ss-evidence-inventory.md\`; strict
client canaries run the inventory with \`--require-complete\` and must not
treat missing or incomplete inventory as a best-effort side artifact.
Runtime root discovery means both \`RuntimeFNamePool\` and
\`RuntimeGUObjectArray\` are validated by FName/object-array consumers, not just
mapped or promoted. Strict readiness also requires exact/promotable signature
validation, target-image \`targetObjectDiscovery\`,
\`targetHooks\`, and \`targetPackageLoadingSurface\` evidence,
\`signatureAnchorReady=true\`, and no \`missingSignatureAnchorReadyKeys\`.
For a bounded ambiguous-root canary, set
\`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS=true\`; the loader
promotes \`RuntimeFNamePoolCandidate<N>\` and
\`RuntimeGUObjectArrayCandidate<N>\` anchors so the same consumers can validate
the real root without a second explicit replay. The canary planner emits this
as \`promoteAmbiguousRoots\` for same-run FName/object-array validation when
bounded ambiguous root evidence is present.
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
It also requires \`luaProcessEventNativeInvokeNonSelfTestInvoked=true\`, proving
an explicitly enabled descriptor-backed non-self-test ProcessEvent target was
invoked through the Lua native bridge.
In short: container alias/layout methods are required, not optional.
The \`runtimeCallFunctionDispatch\` group requires
\`luaCallFunctionNativeInvokeNonSelfTestInvoked=true\`, proving an explicitly
enabled non-self-test CallFunction target was invoked through the Lua native
bridge.
The \`runtimePackageLoading\` group treats \`luaLoadAssetPackageNativeExecutor\`
as ready only when target-image evidence reports \`NativeExecutorReady=true\`,
\`ExecutorPreflightPassed=true\`, and \`FinalNativeCallEligible=true\`;
dry-run executor shape rows remain diagnostic only.
It also requires \`luaLoadAssetPackageNativeInvocation=true\`, proven by
\`lua-load-asset-package-native-invoke nativeInvoked=true nativeCallable=true
targetImage=true nativeReturnValidated=true\`; executor readiness alone is not
package-load completion.
The same group also requires the package-backed \`LoadClass\` chain:
\`luaLoadClassPackageAbiState=true\`,
\`luaLoadClassPackageCallFrameVerification=true\`,
\`luaLoadClassPackageNativeExecutor=true\`, and
\`luaLoadClassPackageNativeInvocation=true\` from target-image
\`StaticLoadClass\` evidence. The \`runtimeObjectRegistry\` group similarly
requires guarded target-image \`StaticConstructObject\` executor state,
executor readiness, and native invocation evidence before synthetic
construction counts toward 1:1 object API parity.
\`ue4ss-port-readiness.py\` auto-scopes mixed-process logs to loaded
\`DuneSandbox\` target PIDs when no explicit \`--pid\` or \`--exe-substring\`
filter is supplied. Strict completion requires \`targetImageProcess=true\` and
validated \`runtimeRootDiscovery=true\`; helper shell/tool process evidence,
mapped-only runtime roots, or self-test-only logs cannot satisfy target-image
runtime proof.
\`verify-client-probe-canary.sh\` also writes \`ue-vtable-candidates.json\`,
\`ue-vtable-candidates.md\`, \`next-canary-plan.json\`,
\`next-canary-plan.env\`, and \`next-canary-plan.md\` into the evidence
directory, using any ranked vtable shortlist as hook-target input for the next
guarded native-client plan through \`--hook-targets-json\`.
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

printf 'packaged Linux client loader: %s\n' "$archive"
printf 'package checksum: %s\n' "${archive}.sha256"
