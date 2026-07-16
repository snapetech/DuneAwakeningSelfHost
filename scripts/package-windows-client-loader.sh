#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
build_script="$repo_root/scripts/build-windows-client-loader.sh"
build_dir="${DUNE_WINDOWS_CLIENT_LOADER_BUILD_DIR:-$repo_root/build/windows-client-loader}"
loader="$build_dir/dune_win_client_probe_loader.dll"
dist_root="${DUNE_WINDOWS_CLIENT_LOADER_DIST_DIR:-$repo_root/dist/windows-client-loader}"
default_version="$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%dT%H%M%SZ)"
if ! git -C "$repo_root" diff --quiet --ignore-submodules -- 2>/dev/null ||
   ! git -C "$repo_root" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
  default_version="${default_version}-dirty"
fi
version="${DUNE_WINDOWS_CLIENT_LOADER_VERSION:-$default_version}"
platform="windows-x86_64"
package_name="dune-windows-client-loader-${version}-${platform}"
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
  "$stage/scripts" \
  "$stage/tests" \
  "$stage/abi"

cp "$loader" "$stage/lib/dune_win_client_probe_loader.dll"
cp "$loader" "$stage/lib/version.dll"
cp "$repo_root/tools/windows-client-loader/dune_win_client_probe_loader.c" "$stage/src/dune_win_client_probe_loader.c"
cp "$repo_root/scripts/build-windows-client-loader.sh" "$stage/build-windows-client-loader.sh"
cp "$repo_root/scripts/launch-proton-client-probe.sh" "$stage/examples/launch-proton-client-probe.sh"
cp "$repo_root/scripts/verify-client-probe-canary.sh" "$stage/examples/verify-client-probe-canary.sh"
cp "$repo_root/scripts/proton-dll-override-control.sh" "$stage/examples/proton-dll-override-control.sh"
cp "$repo_root/scripts/stage-windows-lua-runtime.sh" "$stage/examples/stage-windows-lua-runtime.sh"
cp "$repo_root/scripts/smoke-windows-client-loader.sh" "$stage/examples/smoke-windows-client-loader.sh"
cp "$repo_root/scripts/smoke-windows-client-loader-lua.sh" "$stage/examples/smoke-windows-client-loader-lua.sh"
cp "$repo_root/scripts/summarize-client-loader-scan.py" "$stage/analysis/summarize-client-loader-scan.py"
cp "$repo_root/scripts/summarize-client-loader-xrefs.py" "$stage/analysis/summarize-client-loader-xrefs.py"
cp "$repo_root/scripts/validate-client-pe-signatures.py" "$stage/analysis/validate-client-pe-signatures.py"
cp "$repo_root/scripts/export-client-pe-signature-manifest.py" "$stage/analysis/export-client-pe-signature-manifest.py"
cp "$repo_root/scripts/summarize-client-ue-anchors.py" "$stage/analysis/summarize-client-ue-anchors.py"
cp "$repo_root/scripts/ue4ss-port-readiness.py" "$stage/analysis/ue4ss-port-readiness.py"
cp "$repo_root/scripts/summarize-ue4ss-port-gaps.py" "$stage/analysis/summarize-ue4ss-port-gaps.py"
cp "$repo_root/scripts/summarize-ue4ss-evidence-inventory.py" "$stage/analysis/summarize-ue4ss-evidence-inventory.py"
cp "$repo_root/scripts/ue4ss-portability-contract.py" "$stage/analysis/ue4ss-portability-contract.py"
cp "$repo_root/scripts/verify-loader-artifacts.py" "$stage/analysis/verify-loader-artifacts.py"
cp "$repo_root/scripts/export-ue-anchor-env.py" "$stage/analysis/export-ue-anchor-env.py"
cp "$repo_root/scripts/export-ue-candidate-globals.py" "$stage/analysis/export-ue-candidate-globals.py"
cp "$repo_root/scripts/summarize-ue-candidate-outcomes.py" "$stage/analysis/summarize-ue-candidate-outcomes.py"
cp "$repo_root/scripts/summarize-ue-candidate-shapes.py" "$stage/analysis/summarize-ue-candidate-shapes.py"
cp "$repo_root/scripts/summarize-ue-code-pointer-context.py" "$stage/analysis/summarize-ue-code-pointer-context.py"
cp "$repo_root/scripts/summarize-ue-vtable-candidates.py" "$stage/analysis/summarize-ue-vtable-candidates.py"
cp "$repo_root/scripts/export-process-event-active-validation-candidates.py" "$stage/analysis/export-process-event-active-validation-candidates.py"
cp "$repo_root/scripts/summarize-ue-root-recovery-queue.py" "$stage/analysis/summarize-ue-root-recovery-queue.py"
cp "$repo_root/scripts/cluster-ue-root-recovery-queue.py" "$stage/analysis/cluster-ue-root-recovery-queue.py"
cp "$repo_root/scripts/export-ue-root-recovery-candidates.py" "$stage/analysis/export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/summarize-pe-writable-root-shapes.py" "$stage/analysis/summarize-pe-writable-root-shapes.py"
cp "$repo_root/scripts/export-ue-writable-root-shape-candidates.py" "$stage/analysis/export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/summarize-pe-ue-function-neighborhoods.py" "$stage/analysis/summarize-pe-ue-function-neighborhoods.py"
cp "$repo_root/scripts/promote-ue-anchor-xref-candidates.py" "$stage/analysis/promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/prepare-ue-anchor-canary.py" "$stage/analysis/prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/plan-ue4ss-canary-env.py" "$stage/analysis/plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/proton-proxy-candidates.py" "$stage/analysis/proton-proxy-candidates.py"
cp "$repo_root/scripts/ensure-loader-build-toolchain.sh" "$stage/analysis/ensure-loader-build-toolchain.sh"
cp "$repo_root/scripts/client-deployment.py" "$stage/scripts/client-deployment.py"
cp "$repo_root/scripts/test-client-loader-scan-summary.py" "$stage/tests/test-client-loader-scan-summary.py"
cp "$repo_root/scripts/test-client-loader-xrefs.py" "$stage/tests/test-client-loader-xrefs.py"
cp "$repo_root/scripts/test-client-pe-signatures.py" "$stage/tests/test-client-pe-signatures.py"
cp "$repo_root/scripts/test-client-pe-signature-manifest.py" "$stage/tests/test-client-pe-signature-manifest.py"
cp "$repo_root/scripts/test-client-ue-anchors.py" "$stage/tests/test-client-ue-anchors.py"
cp "$repo_root/scripts/test-ue4ss-port-readiness.py" "$stage/tests/test-ue4ss-port-readiness.py"
cp "$repo_root/scripts/test-ue4ss-port-gaps.py" "$stage/tests/test-ue4ss-port-gaps.py"
cp "$repo_root/scripts/test-ue4ss-portability-contract.py" "$stage/tests/test-ue4ss-portability-contract.py"
cp "$repo_root/scripts/test-ue4ss-evidence-inventory.py" "$stage/tests/test-ue4ss-evidence-inventory.py"
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
cp "$repo_root/scripts/test-export-process-event-active-validation-candidates.py" "$stage/tests/test-export-process-event-active-validation-candidates.py"
cp "$repo_root/scripts/test-ue-root-recovery-queue.py" "$stage/tests/test-ue-root-recovery-queue.py"
cp "$repo_root/scripts/test-ue-root-recovery-clusters.py" "$stage/tests/test-ue-root-recovery-clusters.py"
cp "$repo_root/scripts/test-export-ue-root-recovery-candidates.py" "$stage/tests/test-export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/test-pe-writable-root-shapes.py" "$stage/tests/test-pe-writable-root-shapes.py"
cp "$repo_root/scripts/test-export-ue-writable-root-shape-candidates.py" "$stage/tests/test-export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/test-pe-ue-function-neighborhoods.py" "$stage/tests/test-pe-ue-function-neighborhoods.py"
cp "$repo_root/scripts/test-promote-ue-anchor-xref-candidates.py" "$stage/tests/test-promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/test-prepare-ue-anchor-canary.py" "$stage/tests/test-prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/test-plan-ue4ss-canary-env.py" "$stage/tests/test-plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/test-proton-proxy-candidates.py" "$stage/tests/test-proton-proxy-candidates.py"
cp "$repo_root/scripts/test-client-launch-preflight.py" "$stage/tests/test-client-launch-preflight.py"
cp "$repo_root/scripts/test-client-deployment.py" "$stage/tests/test-client-deployment.py"
cp "$repo_root/docs/client-loader-support.md" "$stage/docs/client-loader-support.md"
cp "$repo_root/docs/windows-client-loader.md" "$stage/docs/windows-client-loader.md"
cp "$repo_root/docs/client-deployment.md" "$stage/docs/client-deployment.md"
cp "$repo_root/docs/windows-client-loader-canary-2026-06-16.md" "$stage/docs/windows-client-loader-canary-2026-06-16.md"
cp "$repo_root/docs/windows-client-loader-canary-2026-07-15.md" "$stage/docs/windows-client-loader-canary-2026-07-15.md"
cp "$repo_root/docs/windows-client-loader-xrefs-2026-06-16.md" "$stage/docs/windows-client-loader-xrefs-2026-06-16.md"
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format json --check > "$stage/docs/ue4ss-portability-contract.json"
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format markdown --check > "$stage/docs/ue4ss-portability-contract.md"

chmod 0755 "$stage/build-windows-client-loader.sh"
chmod 0755 "$stage/examples/launch-proton-client-probe.sh"
chmod 0755 "$stage/examples/verify-client-probe-canary.sh"
chmod 0755 "$stage/examples/proton-dll-override-control.sh"
chmod 0755 "$stage/examples/stage-windows-lua-runtime.sh"
chmod 0755 "$stage/examples/smoke-windows-client-loader.sh"
chmod 0755 "$stage/examples/smoke-windows-client-loader-lua.sh"
chmod 0755 "$stage/analysis/summarize-client-loader-scan.py"
chmod 0755 "$stage/analysis/summarize-client-loader-xrefs.py"
chmod 0755 "$stage/analysis/validate-client-pe-signatures.py"
chmod 0755 "$stage/analysis/export-client-pe-signature-manifest.py"
chmod 0755 "$stage/analysis/summarize-client-ue-anchors.py"
chmod 0755 "$stage/analysis/ue4ss-port-readiness.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-port-gaps.py"
chmod 0755 "$stage/analysis/summarize-ue4ss-evidence-inventory.py"
chmod 0755 "$stage/analysis/ue4ss-portability-contract.py"
chmod 0755 "$stage/analysis/verify-loader-artifacts.py"
chmod 0755 "$stage/analysis/export-ue-anchor-env.py"
chmod 0755 "$stage/analysis/export-ue-candidate-globals.py"
chmod 0755 "$stage/analysis/summarize-ue-candidate-outcomes.py"
chmod 0755 "$stage/analysis/summarize-ue-candidate-shapes.py"
chmod 0755 "$stage/analysis/summarize-ue-code-pointer-context.py"
chmod 0755 "$stage/analysis/summarize-ue-vtable-candidates.py"
chmod 0755 "$stage/analysis/export-process-event-active-validation-candidates.py"
chmod 0755 "$stage/analysis/summarize-ue-root-recovery-queue.py"
chmod 0755 "$stage/analysis/cluster-ue-root-recovery-queue.py"
chmod 0755 "$stage/analysis/export-ue-root-recovery-candidates.py"
chmod 0755 "$stage/analysis/summarize-pe-writable-root-shapes.py"
chmod 0755 "$stage/analysis/export-ue-writable-root-shape-candidates.py"
chmod 0755 "$stage/analysis/summarize-pe-ue-function-neighborhoods.py"
chmod 0755 "$stage/analysis/promote-ue-anchor-xref-candidates.py"
chmod 0755 "$stage/analysis/prepare-ue-anchor-canary.py"
chmod 0755 "$stage/analysis/plan-ue4ss-canary-env.py"
chmod 0755 "$stage/analysis/proton-proxy-candidates.py"
chmod 0755 "$stage/analysis/ensure-loader-build-toolchain.sh"
chmod 0755 "$stage/scripts/client-deployment.py"
chmod 0755 "$stage/tests/test-client-deployment.py"
chmod 0644 "$stage/lib/dune_win_client_probe_loader.dll" "$stage/lib/version.dll"

cat > "$stage/examples/env.scan.example" <<'EOF'
# Windows/Proton client proxy DLL probe.
DUNE_WIN_CLIENT_PROXY_DLL=version.dll
DUNE_WIN_CLIENT_PROBE_LOG=Z:\tmp\dune-win-client-probe-loader.log
DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=2

# Read-only runtime anchor scan.
DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=true
DUNE_WIN_CLIENT_PROBE_LOG_MODULES=true
DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS=ProcessEvent;FNamePool;GUObjectArray;CheatManager
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES=
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE=
DUNE_WIN_CLIENT_PROBE_UE_ANCHORS=
DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS=
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS=true
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REGION_BYTES=268435456
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS=1
DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_NEXT_OFFSET=0x28
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_SUPER_OFFSET=0x30
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_CHILDREN_OFFSET=0x38
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_CHILD_PROPERTIES_OFFSET=0x40
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_LINK_OFFSET=0x48
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FUNCTION_LINK_OFFSET=0x50
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_MAX_FIELDS=16
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_START=0x48
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_END=0xa0
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_MAX_BYTES=16
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS=128
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX=32
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=0
DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_FNAME_POOL=
DUNE_WIN_CLIENT_PROBE_UE_FNAME_BLOCKS_OFFSET=0x10
DUNE_WIN_CLIENT_PROBE_UE_FNAME_STRIDE=2
DUNE_WIN_CLIENT_PROBE_UE_FNAME_MAX_LENGTH=128
DUNE_WIN_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE=false
DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=false
DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS_MAX=16
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_SLOTS=8
DUNE_WIN_CLIENT_PROBE_HOOK_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_MOD_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_LUA_DLL=
DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT=
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_RAW_SET_ENABLED=false
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST_SCRIPT=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_RVA=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_RVA=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_RVA=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_RVA=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_RVA=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OUTPUT_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_EXECUTOR_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_FORCE_CALL=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_RVA=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=
DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED=false
DUNE_WIN_CLIENT_PROBE_LUA_MOD_SCRIPTS=
DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT=
DUNE_WIN_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES=268435456

# Proton/Wine load controls.
WINEDLLOVERRIDES=version=n,b
WINEPATH=Z:\absolute\path\to\stage
WINEDLLPATH=/absolute/path/to/stage

# The launch wrapper also writes these same probe keys to
# dune-win-client-probe.env beside version.dll for normal Steam launches where
# wrapper environment variables are not inherited.
EOF

cat > "$stage/README.md" <<EOF
# Dune Windows Client Loader

Package: ${package_name}
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source commit: $(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)
Platform: ${platform}

This is a Windows PE client-process proxy/probe for Dune under Wine/Proton. It
is not upstream UE4SS yet. It can be staged as a native override DLL, defaults
to \`version.dll\`, logs from inside the Windows process, and scans committed
image mappings for configured anchors. The Dune shipping executable imports
\`VERSION.dll\`, making \`version.dll\` a real proxy load point.

## Contents

- lib/dune_win_client_probe_loader.dll: runtime proxy/probe DLL.
- lib/version.dll: same DLL under the recommended proxy name.
- src/: source used for this package.
- build-windows-client-loader.sh: local rebuild helper.
- examples/launch-proton-client-probe.sh: Proton/Steam launch wrapper.
- examples/verify-client-probe-canary.sh: post-run prepared-canary verifier and artifact collector.
- examples/proton-dll-override-control.sh: registry override helper for Steam launches that do not inherit environment.
- examples/smoke-windows-client-loader.sh: local Wine smoke test.
- examples/stage-windows-lua-runtime.sh: staged LuaBinaries 5.4.8 helper for parity smoke tests.
- examples/smoke-windows-client-loader-lua.sh: real Lua DLL smoke test.
- examples/env.scan.example: scan environment settings.
- scripts/client-deployment.py: receipt-bound install, verification, whole-state audit, and retryable rollback manager.
- analysis/: log summarizer, PE xref summarizer, PE signature validator, manifest/env exporter, UE anchor readiness, candidate-global outcome/shape/export tools, active-validation candidate exporter, portability contract, and proxy candidate tools.
- tests/: unit tests for the packaged deployment and analysis tools.
- docs/client-loader-support.md: shared Linux/Windows support matrix.
- docs/client-deployment.md: transactional deployment and recovery runbook.
- docs/ue4ss-portability-contract.md: repo-generated all-target portability contract.
- loader-artifact-verification.txt and loader-artifact-verification.json: package-root artifact verification outputs.
- The packaged tarball also writes sibling .verification.txt and .verification.json reports that verify the staged root, safe tar layout, and portable .sha256 sidecar together.
- client-deployment-test.txt: packaged transactional-manager test receipt.
- docs/windows-client-loader-canary-2026-06-16.md: real Proton client canary result.
- docs/windows-client-loader-canary-2026-07-15.md: build-bound proxy/root/reflection canary and verified cleanup.
- docs/windows-client-loader-xrefs-2026-06-16.md: real Proton client static xref follow-up.
- abi/: PE header and export reports when local tools are available.
- SHA256SUMS: checksums for package contents.

## Steam Launch Option

The recommended installation path is the packaged transactional manager. It
binds the reviewed plan to the game executable, source artifacts, current
targets, and private backup state; it refuses drift and running-client
mutation:

\`\`\`bash
game=/absolute/path/to/steamapps/common/DuneAwakening
state="\$PWD/backups/client-deployments"
receipt="\$PWD/current-loader.plan.json"

scripts/client-deployment.py --state-root "\$state" plan \\
  --game-dir "\$game" \\
  --deployment current-loader \\
  --file "\$PWD/lib/version.dll::DuneSandbox/Binaries/Win64/version.dll" \\
  --file "\$PWD/examples/env.scan.example::DuneSandbox/Binaries/Win64/dune-win-client-probe.env" \\
  > "\$receipt"

python3 -m json.tool "\$receipt"
scripts/client-deployment.py --state-root "\$state" install \\
  --reviewed-plan "\$receipt" \\
  --confirm 'MUTATE DUNE CLIENT FILES'
scripts/client-deployment.py --state-root "\$state" verify --deployment current-loader
scripts/client-deployment.py --state-root "\$state" audit
\`\`\`

Rollback uses the same private state and is retryable after a recorded
interrupted install or partial rollback:

\`\`\`bash
scripts/client-deployment.py --state-root "\$state" rollback \\
  --deployment current-loader \\
  --confirm 'MUTATE DUNE CLIENT FILES'
\`\`\`

Read \`docs/client-deployment.md\` before using adoption or installing an
additive Pak overlay. The commands above do not set the Proton DLL override;
use the separately reversible override helper only after deployment verifies.

### Experimental launch wrapper

\`\`\`bash
examples/launch-proton-client-probe.sh --stage-to-game-dir -- %command%
\`\`\`

The wrapper can stage the DLL outside the Steam game directory for experiments,
but Dune's Proton path should use \`--stage-to-game-dir\` so \`version.dll\` is
beside the game executable. The script backs up any existing DLL with the same
name before replacing it. It also writes \`dune-win-client-probe.env\` beside
the proxy DLL so a normal Steam launch can still enable scan mode even when the
wrapper environment is not inherited.

Prefer the manager above for persistent staging because its reviewed receipt,
collision checks, private backup verification, audit, and crash-recovery state
machine are stronger than the experimental wrapper's single backup manifest.

For non-Dune Windows UE targets, keep the proxy package repo-contained by
using \`--game-dir\`, \`--exe-rel\`, \`--dll-name\`, and \`--stage-dir\` to point
at the target install, executable path, imported DLL proxy name, and external
staging directory. This makes the package usable with another Unreal title
without editing installed game files; use \`--stage-to-game-dir\` only after
reviewing the target DLL search path and keeping the generated manifest.

If the real game process still loads Proton's builtin \`version.dll\`, set the
per-app Wine override:

\`\`\`bash
examples/proton-dll-override-control.sh --set
examples/proton-dll-override-control.sh --query
\`\`\`

Default log:

\`\`\`text
/tmp/dune-win-client-probe-loader.log
\`\`\`

## Smoke Test

\`\`\`bash
examples/smoke-windows-client-loader.sh
\`\`\`

The default smoke validates the missing-Lua-DLL path. To prove real Windows Lua
dispatch parity, run the Lua smoke. It stages the pinned LuaBinaries 5.4.8
runtime automatically when \`DUNE_WIN_CLIENT_PROBE_LUA_DLL\` is not already set:

\`\`\`bash
examples/smoke-windows-client-loader-lua.sh
\`\`\`

## Analysis

\`\`\`bash
TARGET_BINARY="\${TARGET_BINARY:-/path/to/DuneSandbox-Win64-Shipping.exe}"
TARGET_FILTER_ARGS=(\${TARGET_FILTER_ARGS[@]:---exe-substring DuneSandbox})

analysis/summarize-client-loader-scan.py /tmp/dune-win-client-probe-loader.log
analysis/summarize-client-loader-xrefs.py "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --category cheat --show-context --show-seeds
analysis/summarize-client-loader-xrefs.py "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --category ue --format json > client-loader-xrefs.json
analysis/validate-client-pe-signatures.py "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --category cheat
analysis/export-client-pe-signature-manifest.py "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --category cheat --format env
analysis/export-client-pe-signature-manifest.py "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --category cheat --format signatures > client-signatures.txt
analysis/export-client-pe-signature-manifest.py "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --category ue --format anchor-signatures > client-anchor-signatures.txt
analysis/validate-client-pe-signatures.py "\$TARGET_BINARY" --manifest-json client-pe-signature-manifest.json --ignore-expected-offsets
analysis/export-ue-anchor-env.py /tmp/dune-win-client-probe-loader.log --loader win-client --platform windows > ue-anchors.env
analysis/summarize-ue-candidate-outcomes.py /tmp/dune-win-client-probe-loader.log --format markdown > ue-candidate-outcomes.md
analysis/summarize-ue-candidate-outcomes.py /tmp/dune-win-client-probe-loader.log --format json > ue-candidate-outcomes.json
analysis/summarize-ue-candidate-shapes.py /tmp/dune-win-client-probe-loader.log --format markdown > ue-candidate-shapes.md
analysis/summarize-ue-candidate-shapes.py /tmp/dune-win-client-probe-loader.log --format json > ue-candidate-shapes.json
analysis/summarize-ue-code-pointer-context.py "\$TARGET_BINARY" ue-candidate-outcomes.json --format markdown > ue-code-pointer-context.md
analysis/summarize-ue-vtable-candidates.py /tmp/dune-win-client-probe-loader.log --format markdown > ue-vtable-candidates.md
analysis/summarize-ue-vtable-candidates.py /tmp/dune-win-client-probe-loader.log --format json > ue-vtable-candidates.json
analysis/summarize-client-loader-scan.py /tmp/dune-win-client-probe-loader.log --format json > client-summary.json
analysis/export-process-event-active-validation-candidates.py client-summary.json --format markdown > process-event-active-validation-candidates.md
analysis/export-process-event-active-validation-candidates.py client-summary.json --format json > process-event-active-validation-candidates.json
analysis/summarize-pe-ue-function-neighborhoods.py "\$TARGET_BINARY" --xref-json client-loader-xrefs.json --format json > ue-function-neighborhoods.json
analysis/summarize-pe-writable-root-shapes.py "\$TARGET_BINARY" --candidate-outcomes-json ue-candidate-outcomes.json --require-read-write --require-qword --min-qword-refs 16 --max-scalar-ratio 0.10 --format markdown > pe-writable-root-shapes.md
analysis/summarize-pe-writable-root-shapes.py "\$TARGET_BINARY" --candidate-outcomes-json ue-candidate-outcomes.json --require-read-write --require-qword --min-qword-refs 16 --max-scalar-ratio 0.10 --format json > pe-writable-root-shapes.json
analysis/export-ue-writable-root-shape-candidates.py pe-writable-root-shapes.json --platform windows --include FNamePool=0x0 --anchor GUObjectArray --anchor GObjectArray --anchor GWorld --anchor GEngine --format json > ue-writable-root-shape-candidates.json
analysis/summarize-ue-root-recovery-queue.py ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format markdown > ue-root-recovery-queue.md
analysis/summarize-ue-root-recovery-queue.py ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format json > ue-root-recovery-queue.json
analysis/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format markdown > ue-root-recovery-clusters.md
analysis/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format json > ue-root-recovery-clusters.json
analysis/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform windows --anchor-preset object-discovery --format markdown > ue-root-recovery-candidates.md
analysis/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform windows --anchor-preset object-discovery --format json > ue-root-recovery-candidates.json
analysis/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform windows --anchor-preset complete --require-source-group-match --format json > ue-root-recovery-candidates-complete-source-matched.json
analysis/prepare-ue-anchor-canary.py --platform windows --binary "\$TARGET_BINARY" --loader-log /tmp/dune-win-client-probe-loader.log --output-dir build/windows-client-anchor-canary
examples/verify-client-probe-canary.sh --platform windows --prep-dir build/windows-client-anchor-canary --log /tmp/dune-win-client-probe-loader.log --output-dir backups/client-probe-canary/windows/manual
analysis/plan-ue4ss-canary-env.py --platform windows --client-log /tmp/dune-win-client-probe-loader.log --loader win-client "\${TARGET_FILTER_ARGS[@]}" --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --active-validation-candidates-json process-event-active-validation-candidates.json --max-stage read-only --format json > next-canary.json
analysis/plan-ue4ss-canary-env.py --platform windows --client-log /tmp/dune-win-client-probe-loader.log --loader win-client "\${TARGET_FILTER_ARGS[@]}" --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --active-validation-candidates-json process-event-active-validation-candidates.json --max-stage read-only > next-canary.env
analysis/ue4ss-port-readiness.py --client-log /tmp/dune-win-client-probe-loader.log --loader win-client "\${TARGET_FILTER_ARGS[@]}" --signature-validation-json client-pe-signature-validation.json --anchor-coverage-json build/windows-client-anchor-canary/anchor-coverage.json --format json > ue4ss-readiness.json
analysis/summarize-ue4ss-port-gaps.py --readiness-json ue4ss-readiness.json --canary-plan-json next-canary.json --format markdown > ue4ss-port-gaps.md
analysis/summarize-ue4ss-evidence-inventory.py build backups /tmp --limit 12 --format markdown > ue4ss-evidence-inventory.md
analysis/summarize-client-ue-anchors.py /tmp/dune-win-client-probe-loader.log
analysis/proton-proxy-candidates.py "\$TARGET_BINARY"
analysis/verify-loader-artifacts.py --target windows-client --package-root . --package-target windows-client --package-only --format text > loader-artifact-verification.txt
analysis/verify-loader-artifacts.py --target windows-client --package-root . --package-target windows-client --package-only --format json > loader-artifact-verification.json
analysis/verify-loader-artifacts.py --target windows-client --package-root . --package-target windows-client --package-archive "../${package_name}.tar.gz" --package-archive-sha256 "../${package_name}.tar.gz.sha256" --package-only --format json > downloaded-package-verification.json
analysis/ue4ss-portability-contract.py --targets available --format markdown --check > ue4ss-portability-contract.md
python3 -m unittest tests/test-client-deployment.py
python3 -m unittest tests/test-client-loader-scan-summary.py tests/test-client-loader-xrefs.py tests/test-client-pe-signatures.py tests/test-client-pe-signature-manifest.py tests/test-client-ue-anchors.py tests/test-ue4ss-port-readiness.py tests/test-ue4ss-port-gaps.py tests/test-ue4ss-portability-contract.py tests/test-ue4ss-evidence-inventory.py tests/test-loader-scheduler-api-parity.py tests/test-loader-modref-api-parity.py tests/test-loader-mod-lifecycle-api-parity.py tests/test-loader-unregister-api-parity.py tests/test-loader-fname-api-parity.py tests/test-loader-native-identity-parity.py tests/test-loader-custom-property-api-parity.py tests/test-loader-compat-globals-api-parity.py tests/test-loader-world-engine-api-parity.py tests/test-loader-object-notify-api-parity.py tests/test-loader-console-command-api-parity.py tests/test-loader-anchor-group-parity.py tests/test-loader-scan-preset-parity.py tests/test-export-ue-anchor-env.py tests/test-export-ue-candidate-globals.py tests/test-ue-candidate-outcomes.py tests/test-ue-candidate-shapes.py tests/test-ue-code-pointer-context.py tests/test-ue-vtable-candidates.py tests/test-export-process-event-active-validation-candidates.py tests/test-ue-root-recovery-queue.py tests/test-ue-root-recovery-clusters.py tests/test-export-ue-root-recovery-candidates.py tests/test-pe-writable-root-shapes.py tests/test-export-ue-writable-root-shape-candidates.py tests/test-pe-ue-function-neighborhoods.py tests/test-promote-ue-anchor-xref-candidates.py tests/test-prepare-ue-anchor-canary.py tests/test-plan-ue4ss-canary-env.py tests/test-proton-proxy-candidates.py tests/test-client-launch-preflight.py
\`\`\`

\`export-ue-anchor-env.py\` exports core discovery anchors plus reflection
anchors by default, including anchors from resolved \`ue-anchor-signature\`
records. Unresolved and ambiguous signature anchors remain missing.
\`prepare-ue-anchor-canary.py\` combines the validated UE signature manifest,
loader-consumable anchor signature file, second-pass anchor env, validation
summary, readiness report, object-discovery coverage, and
\`post-canary-verify.sh\` in one output directory. After the next canary, run
\`examples/verify-client-probe-canary.sh --platform windows --prep-dir
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
\`DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS=true\`; the
loader promotes \`RuntimeFNamePoolCandidate<N>\` and
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
guarded Proton/Windows plan through \`--hook-targets-json\`.
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

For a full one-launch signature canary, point
\`DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE\` at the generated
\`client-signatures.txt\`. Use \`--format env\` only when a file path is
inconvenient; env output is chunked. Use \`--manifest-json\` with
\`--ignore-expected-offsets\` to revalidate exported manifests against later
client builds before canary scanning.
EOF

file "$loader" > "$stage/abi/file.txt"
if command -v llvm-objdump >/dev/null 2>&1; then
  llvm-objdump -p "$loader" > "$stage/abi/pe-headers.txt"
fi
if command -v llvm-nm >/dev/null 2>&1; then
  llvm-nm -g "$loader" > "$stage/abi/exports-symbols.txt" || true
fi

(
  cd "$stage"
  python3 -m unittest tests/test-client-deployment.py > client-deployment-test.txt 2>&1
)

(
  cd "$stage"
  find . -type f ! -name SHA256SUMS -print | sort | sed 's#^\./##' | xargs sha256sum > SHA256SUMS
  verification_text="$(mktemp)"
  verification_json="$(mktemp)"
  trap 'rm -f "$verification_text" "$verification_json"' EXIT
  analysis/verify-loader-artifacts.py --target windows-client --package-root . --package-target windows-client --package-only --format text > "$verification_text"
  analysis/verify-loader-artifacts.py --target windows-client --package-root . --package-target windows-client --package-only --format json > "$verification_json"
  mv "$verification_text" loader-artifact-verification.txt
  mv "$verification_json" loader-artifact-verification.json
  find . -type f ! -name SHA256SUMS -print | sort | sed 's#^\./##' | xargs sha256sum > SHA256SUMS
)

tar -C "$dist_root" -czf "$archive" "$package_name"
archive_digest="$(sha256sum "$archive" | awk '{print $1}')"
printf '%s  %s\n' "$archive_digest" "$(basename "$archive")" > "${archive}.sha256"
python3 "$repo_root/scripts/verify-loader-artifacts.py" \
  --target windows-client \
  --package-root "$stage" \
  --package-target windows-client \
  --package-archive "$archive" \
  --package-archive-sha256 "${archive}.sha256" \
  --package-only \
  --format text > "${archive}.verification.txt"
python3 "$repo_root/scripts/verify-loader-artifacts.py" \
  --target windows-client \
  --package-root "$stage" \
  --package-target windows-client \
  --package-archive "$archive" \
  --package-archive-sha256 "${archive}.sha256" \
  --package-only \
  --format json > "${archive}.verification.json"

printf 'packaged Windows client loader: %s\n' "$archive"
printf 'package checksum: %s\n' "${archive}.sha256"
printf 'package verification: %s\n' "${archive}.verification.json"
