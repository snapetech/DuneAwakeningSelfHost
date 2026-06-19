#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
log="${DUNE_CLIENT_PROBE_PACKAGE_PREFLIGHT_LOG:-/tmp/dune-client-probe-package-preflight.log}"
target="${DUNE_CLIENT_PROBE_SMOKE_TARGET:-/usr/bin/true}"

"$repo_root/scripts/build-linux-client-loader.sh" >/dev/null

rm -f "$log"
mod_root="$(mktemp -d)"
trap 'rm -rf "$mod_root"' EXIT
mkdir -p "$mod_root/PackagePreflight/Scripts"
printf "%s\n" "PackagePreflight" >"$mod_root/mods.txt"
cat >"$mod_root/PackagePreflight/Scripts/main.lua" <<'LUA'
local path='/Script/DuneProbe.MissingPackageAsset'
local packagePreflight=LoadAsset(path,{Backend='package'})
local backend=GetLoadAssetBackendState()
local bridge=GetLoadAssetPackageBridgeState()
local abi=GetLoadAssetPackageAbiState()
local frame=GetLoadAssetPackageCallFrameVerificationState(path)
local adapter=GetLoadAssetPackageNativeCallAdapterState(path)
local descriptor=GetLoadAssetPackageInvocationDescriptorState(path)
local executor=GetLoadAssetPackageNativeExecutorState(path)
local native=InvokeLoadAssetPackageNative(path,{Invoke=true})
if packagePreflight ~= nil then
  error('package LoadAsset preflight returned an object before native bridge exists')
end
if not (backend and backend.PackageBackendAvailable and not backend.PackageBackendTargetImage and not backend.PackageBackendArmed) then
  error('self-test package backend did not report non-target provenance')
end
if not (bridge and bridge.Status=='target-not-target-image' and bridge.PackageBackendAvailable and not bridge.PackageBackendTargetImage and not bridge.NativeBridgeArmed and not bridge.AbiVerified) then
  error('self-test package bridge did not block non-target anchor')
end
if not (abi and abi.Status=='target-not-target-image' and abi.TargetImage==false and not abi.AbiVerified and not abi.NativeBridgeArmed) then
  error('self-test package ABI state did not block non-target anchor')
end
if not (frame and frame.Status=='target-not-target-image' and frame.TargetImage==false and not frame.AbiVerified and not frame.TCharLayoutVerified and not frame.CallFrameReady and not frame.NativeInvoked) then
  error('self-test package call frame did not block non-target anchor')
end
if not (adapter and adapter.Status=='target-not-target-image' and adapter.TargetImage==false and not adapter.FunctionPointerReady and not adapter.AbiVerified and not adapter.TCharLayoutVerified and not adapter.CallFrameReady and not adapter.NativeBridgeArmed and not adapter.AdapterReady and not adapter.NativeCallable and not adapter.NativeInvoked) then
  error('self-test package adapter did not block non-target anchor')
end
if not (descriptor and descriptor.DescriptorKind=='guarded-package-native-call' and descriptor.NativeCallPlanConstructed and not descriptor.NativeCallable and not descriptor.NativeInvoked) then
  error('self-test package descriptor did not preserve non-callable adapter state')
end
if not (executor and executor.ExecutorKind=='guarded-package-native-executor' and executor.TargetName=='StaticLoadObject' and type(executor.TargetAddress)=='number' and executor.TargetAddress > 0 and executor.TargetImage==false and executor.SignatureFamily=='StaticLoadObject' and executor.NativeExecutorConstructed and executor.NativeExecutorDryRun and not executor.NativeExecutorReady and not executor.ExecutorPreflightPassed and not executor.FinalNativeCallEligible and executor.NativeExecutorBlockReason=='target-not-target-image' and executor.FinalNativeCallBlocked and executor.FinalNativeCallBlockReason=='preflight-state-only' and not executor.NativeInvoked) then
  error('self-test package executor did not block non-target anchor')
end
if not (native and native.Status=='target-not-target-image' and native.TargetImage==false and native.InvokeRequested and native.InvokeEnabled and not native.AbiVerified and not native.TCharLayoutVerified and not native.CallFrameReady and not native.NativeBridgeArmed and not native.NativeCallable and not native.NativeInvoked and not native.NativeCallPlanAccepted) then
  error('self-test package native invoke did not block non-target anchor')
end
LUA

DUNE_CLIENT_PROBE_LOG="$log" \
DUNE_CLIENT_PROBE_FORCE=true \
DUNE_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=0 \
DUNE_CLIENT_PROBE_SCAN_ENABLED=false \
DUNE_CLIENT_PROBE_UE_SELF_TEST_ANCHOR=true \
DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_SELF_TEST_ANCHOR=true \
DUNE_CLIENT_PROBE_UE_UOBJECT_PROBE=true \
DUNE_CLIENT_PROBE_UE_FNAME_PROBE=true \
DUNE_CLIENT_PROBE_LUA_MODS_ENABLED=true \
DUNE_CLIENT_PROBE_LUA_MOD_ROOT="$mod_root" \
DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_ABI_EVIDENCE=self-test-static-load-object \
DUNE_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_ABI=true \
DUNE_CLIENT_PROBE_TCHAR_UNIT_BYTES=4 \
DUNE_CLIENT_PROBE_TCHAR_EVIDENCE=self-test-host-wchar \
DUNE_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT=true \
DUNE_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE=true \
DUNE_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL=true \
DUNE_CLIENT_PROBE_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD=true \
  "$repo_root/scripts/launch-linux-client-probe.sh" -- "$target"

require_log() {
  local pattern="$1"
  if ! grep -q "$pattern" "$log"; then
    echo "missing expected Linux client package preflight log pattern: $pattern" >&2
    sed -n '1,180p' "$log" >&2 || true
    exit 1
  fi
}

require_log 'event=lua-load-asset-package-bridge-state status=target-not-target-image .*targetImage=false .*nativeBridgeArmed=false abiVerified=false packageAvailable=true'
require_log 'event=lua-load-asset-package-preflight status=native-bridge-missing .*targetName=StaticLoadObject .*target=0x[1-9a-fA-F][0-9a-fA-F]* .*targetImage=false .*targetMapped=true .*targetReadable=true .*targetExecutable=true .*platformAbi=sysv-x86_64 invokeEnabled=true nativeBridgeArmed=false nativeCallable=false nativeInvoked=false packageAvailable=true'
require_log 'event=lua-load-asset-package-call-frame-verification-state status=target-not-target-image .*targetImage=false .*abiVerified=false .*tcharLayoutVerified=false .*callFrameReady=false nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-call-adapter-state status=target-not-target-image .*targetImage=false .*functionPointerReady=false .*nativeBridgeArmed=false adapterReady=false .*nativeCallable=false nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-executor-state status=prepared .*targetImage=false .*nativeExecutorReady=false executorPreflightPassed=false finalNativeCallEligible=false nativeExecutorBlockReason=target-not-target-image .*finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-invoke status=target-not-target-image .*targetImage=false .*invokeRequested=true invokeEnabled=true .*abiVerified=false tcharLayoutVerified=false callFrameReady=false nativeBridgeArmed=false .*nativeCallPlanAccepted=false .*nativeCallable=false nativeInvoked=false'

echo "Linux client package self-test target-image guard smoke passed: $log"
