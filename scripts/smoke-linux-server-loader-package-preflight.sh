#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
log="${DUNE_SERVER_PROBE_PACKAGE_PREFLIGHT_LOG:-/tmp/dune-server-probe-package-preflight.log}"
target="${DUNE_SERVER_PROBE_SMOKE_TARGET:-/usr/bin/true}"

"$repo_root/scripts/build-linux-server-loader.sh" >/dev/null

rm -f "$log"
mod_root="$(mktemp -d)"
mod_script="$mod_root/package-preflight.lua"
trap 'rm -rf "$mod_root"' EXIT
cat >"$mod_script" <<'LUA'
local path='/Script/DuneProbe.MissingPackageAsset'
local packagePreflight=LoadAsset(path,{Backend='package'})
local packageClass=LoadClass('DuneServerProbeSelfTestClass',{Backend='package'})
local classBridge=GetLoadClassPackageBridgeState()
local classAbi=GetLoadClassPackageAbiState()
local classFrame=GetLoadClassPackageCallFrameVerificationState('/Script/DuneServerProbe.SelfTestClass')
local classExecutor=GetLoadClassPackageNativeExecutorState('/Script/DuneServerProbe.SelfTestClass')
local classNative=InvokeLoadClassPackageNative('/Script/DuneServerProbe.SelfTestClass',{Invoke=true})
local backend=GetLoadAssetBackendState()
local bridge=GetLoadAssetPackageBridgeState()
local abi=GetLoadAssetPackageAbiState()
local frame=GetLoadAssetPackageCallFrameVerificationState(path)
local adapter=GetLoadAssetPackageNativeCallAdapterState(path)
local descriptor=GetLoadAssetPackageInvocationDescriptorState(path)
local executor=GetLoadAssetPackageNativeExecutorState(path)
local native=InvokeLoadAssetPackageNative(path,{Invoke=true})
if packagePreflight ~= nil then error('package LoadAsset preflight returned an object before native bridge exists') end
if not (packageClass and packageClass.Name=='DuneServerProbeSelfTestClass' and packageClass.ClassName=='UClass') then error('package LoadClass did not preserve registry class fallback') end
if not (classBridge and classBridge.TargetName=='StaticLoadClass' and classBridge.Status=='anchor-missing' and not classBridge.NativeBridgeArmed) then error('LoadClass package bridge state did not block missing StaticLoadClass anchor') end
if not (classAbi and classAbi.SignatureFamily=='StaticLoadClass' and classAbi.PlatformAbi=='sysv-x86_64' and not classAbi.AbiVerified and not classAbi.CallFrameReady) then error('LoadClass package ABI state did not expose StaticLoadClass contract') end
if not (classFrame and classFrame.Status=='anchor-missing' and classFrame.BoundedInput and not classFrame.AbiVerified and not classFrame.ClassRootReady and not classFrame.CallFrameReady and not classFrame.NativeInvoked) then error('LoadClass package call frame state did not block missing anchor') end
if not (classExecutor and classExecutor.ExecutorKind=='guarded-class-package-native-executor' and classExecutor.TargetName=='StaticLoadClass' and not classExecutor.NativeExecutorReady and classExecutor.NativeExecutorBlockReason=='anchor-missing' and not classExecutor.NativeInvoked) then error('LoadClass package executor state did not block missing anchor') end
if not (classNative and classNative.Status=='anchor-missing' and classNative.TargetName=='StaticLoadClass' and classNative.InvokeEnabled==false and not classNative.NativeCallable and not classNative.NativeInvoked and not classNative.NativeCallPlanAccepted) then error('LoadClass package native invoke did not block missing anchor') end
if not (backend and backend.PackageBackendAvailable and not backend.PackageBackendTargetImage and not backend.PackageBackendArmed) then error('self-test package backend did not report non-target provenance') end
if not (bridge and bridge.Status=='target-not-target-image' and bridge.PackageBackendAvailable and not bridge.PackageBackendTargetImage and not bridge.NativeBridgeArmed and not bridge.AbiVerified) then error('self-test package bridge did not block non-target anchor') end
if not (abi and abi.Status=='target-not-target-image' and abi.TargetImage==false and not abi.AbiVerified and not abi.NativeBridgeArmed) then error('self-test package ABI state did not block non-target anchor') end
if not (frame and frame.Status=='target-not-target-image' and frame.TargetImage==false and not frame.AbiVerified and not frame.TCharLayoutVerified and not frame.CallFrameReady and not frame.NativeInvoked) then error('self-test package call frame did not block non-target anchor') end
if not (adapter and adapter.Status=='target-not-target-image' and not adapter.FunctionPointerReady and not adapter.AbiVerified and not adapter.TCharLayoutVerified and not adapter.CallFrameReady and not adapter.NativeBridgeArmed and not adapter.AdapterReady and not adapter.NativeCallable and not adapter.NativeInvoked) then error('self-test package adapter did not block non-target anchor') end
if not (descriptor and descriptor.DescriptorKind=='guarded-package-native-call' and descriptor.NativeCallPlanConstructed and not descriptor.NativeCallable and not descriptor.NativeInvoked) then error('self-test package descriptor did not preserve non-callable adapter state') end
if not (executor and executor.ExecutorKind=='guarded-package-native-executor' and executor.TargetName=='StaticLoadObject' and type(executor.TargetAddress)=='number' and executor.TargetAddress > 0 and executor.TargetImage==false and executor.SignatureFamily=='StaticLoadObject' and executor.NativeExecutorReady==false and executor.ExecutorPreflightPassed==false and executor.FinalNativeCallEligible==false and executor.NativeExecutorBlockReason=='target-not-target-image' and executor.FinalNativeCallBlocked and executor.FinalNativeCallBlockReason=='preflight-state-only' and not executor.NativeInvoked) then error('self-test package executor did not block non-target anchor') end
if not (native and native.Status=='target-not-target-image' and native.InvokeRequested and native.InvokeEnabled and not native.NativeBridgeArmed and not native.AbiVerified and not native.TCharLayoutVerified and not native.CallFrameReady and not native.NativeCallable and not native.NativeInvoked and not native.NativeCallPlanAccepted) then error('self-test package native invoke did not block non-target anchor') end
LUA

DUNE_PROBE_LOADER_LOG="$log" \
DUNE_PROBE_LOADER_FORCE=true \
DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS=0 \
DUNE_PROBE_LOADER_SCAN_ENABLED=false \
DUNE_PROBE_LOADER_UE_SELF_TEST_ANCHOR=true \
DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_SELF_TEST_ANCHOR=true \
DUNE_PROBE_LOADER_UE_UOBJECT_PROBE=true \
DUNE_PROBE_LOADER_UE_FNAME_PROBE=true \
DUNE_PROBE_LOADER_LUA_MODS_ENABLED=true \
DUNE_PROBE_LOADER_LUA_MOD_SCRIPTS="$mod_script" \
DUNE_PROBE_LOADER_LUA_MOD_ROOT="$mod_root" \
DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE=self-test-static-load-object \
DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI=true \
DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES=4 \
DUNE_PROBE_LOADER_TCHAR_EVIDENCE=self-test-host-wchar \
DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT=true \
DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE=true \
DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL=true \
DUNE_PROBE_LOADER_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD=true \
LD_PRELOAD="$repo_root/build/linux-server-loader/libdune_server_probe_loader.so" \
  "$target"

require_log() {
  local pattern="$1"
  if ! grep -q "$pattern" "$log"; then
    echo "missing expected Linux server package preflight log pattern: $pattern" >&2
    sed -n '1,180p' "$log" >&2 || true
    exit 1
  fi
}

require_log 'event=lua-load-asset-package-bridge-state status=target-not-target-image .*targetImage=false .*nativeBridgeArmed=false abiVerified=false packageAvailable=true'
require_log 'event=lua-load-asset-package-preflight status=native-bridge-missing .*targetName=StaticLoadObject .*target=0x[1-9a-fA-F][0-9a-fA-F]* .*targetImage=false .*targetMapped=true .*targetReadable=true .*targetExecutable=true .*platformAbi=sysv-x86_64 invokeEnabled=true nativeBridgeArmed=false nativeCallable=false nativeInvoked=false packageAvailable=true'
require_log 'event=lua-load-class-package-preflight status=anchor-missing .*targetName=StaticLoadClass .*target=0x0 .*platformAbi=sysv-x86_64 .*nativeBridgeArmed=false nativeCallable=false nativeInvoked=false .*staticLoadClass=false'
require_log 'event=lua-load-class-package-bridge-state status=anchor-missing .*targetName=StaticLoadClass .*target=0x0 .*platformAbi=sysv-x86_64 .*nativeBridgeArmed=false abiVerified=false packageAvailable=false'
require_log 'event=lua-load-class-package-native-executor-state status=prepared .*targetName=StaticLoadClass .*target=0x0 .*platformAbi=sysv-x86_64 .*nativeExecutorReady=false executorPreflightPassed=false finalNativeCallEligible=false nativeExecutorBlockReason=anchor-missing nativeInvoked=false'
require_log 'event=lua-load-class-package-native-invoke status=anchor-missing .*targetName=StaticLoadClass .*target=0x0 .*platformAbi=sysv-x86_64 .*nativeCallable=false nativeInvoked=false nativeCallPlanAccepted=false'
require_log 'event=lua-load-asset-package-call-frame-verification-state status=target-not-target-image .*targetImage=false .*abiVerified=false .*tcharLayoutVerified=false .*callFrameReady=false nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-call-adapter-state status=target-not-target-image .*functionPointerReady=false .*nativeBridgeArmed=false adapterReady=false .*nativeCallable=false nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-executor-state status=prepared .*nativeExecutorReady=false executorPreflightPassed=false finalNativeCallEligible=false nativeExecutorBlockReason=target-not-target-image .*finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-invoke status=target-not-target-image .*targetImage=false .*invokeRequested=true invokeEnabled=true .*abiVerified=false tcharLayoutVerified=false callFrameReady=false nativeBridgeArmed=false .*nativeCallPlanAccepted=false .*nativeCallable=false nativeInvoked=false'

echo "Linux server package self-test target-image guard smoke passed: $log"
