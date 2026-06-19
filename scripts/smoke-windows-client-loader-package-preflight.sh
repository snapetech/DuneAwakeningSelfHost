#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
log="${DUNE_WIN_CLIENT_PROBE_PACKAGE_PREFLIGHT_LOG:-/tmp/dune-win-client-probe-package-preflight.log}"
loader="${DUNE_WINDOWS_CLIENT_PRELOAD:-$repo_root/build/windows-client-loader/dune_win_client_probe_loader.dll}"
lua_dll="${DUNE_WIN_CLIENT_PROBE_LUA_DLL:-}"

if [ -z "$lua_dll" ]; then
  stage_script="$repo_root/scripts/stage-windows-lua-runtime.sh"
  if [ ! -x "$stage_script" ]; then
    echo "DUNE_WIN_CLIENT_PROBE_LUA_DLL must point at a real Windows Lua DLL, for example lua54.dll" >&2
    exit 2
  fi
  "$stage_script" >/dev/null
  lua_dll="${DUNE_WINDOWS_LUA_RUNTIME_DIR:-$repo_root/build/windows-lua-runtime}/lua54.dll"
fi
if [ ! -f "$lua_dll" ]; then
  echo "missing Windows Lua DLL: $lua_dll" >&2
  exit 2
fi
if ! command -v wine >/dev/null 2>&1 || ! command -v winepath >/dev/null 2>&1; then
  echo "wine and winepath are required for the Windows package preflight smoke" >&2
  exit 1
fi

"$repo_root/scripts/build-windows-client-loader.sh" >/dev/null

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
local crash=GetLoadAssetPackageCrashGuardState()
local guarded=GetLoadAssetPackageGuardedCallState()
local frame=GetLoadAssetPackageCallFrameVerificationState(path)
local adapter=GetLoadAssetPackageNativeCallAdapterState(path)
local descriptor=GetLoadAssetPackageInvocationDescriptorState(path)
local executor=GetLoadAssetPackageNativeExecutorState(path)
local native=InvokeLoadAssetPackageNative(path,{Invoke=true})
if packagePreflight ~= nil then error('package LoadAsset preflight returned an object before native bridge exists') end
if not (crash and crash.CrashGuardAvailable and crash.CrashGuardEnabled and not crash.NativeInvoked) then error('package crash guard unavailable') end
if crash.CrashGuardRecoverable and not (crash.Status=='armed' and crash.CrashGuardArmed) then error('recoverable package crash guard did not arm') end
if (not crash.CrashGuardRecoverable) and crash.CrashGuardArmed then error('non-recoverable package crash guard armed') end
if not (guarded and guarded.Status=='self-test-passed' and guarded.GuardedCallAvailable and guarded.GuardedCallExecuted and guarded.GuardedCallSucceeded and guarded.GuardedCallResult==17 and not guarded.CrashCaptured and not guarded.NativeInvoked) then error('package guarded call did not pass') end
if not (backend and backend.PackageBackendAvailable and not backend.PackageBackendTargetImage and not backend.PackageBackendArmed) then error('self-test package backend did not report non-target provenance') end
if not (bridge and bridge.Status=='target-not-target-image' and bridge.PackageBackendAvailable and not bridge.PackageBackendTargetImage and not bridge.NativeBridgeArmed and not bridge.AbiVerified) then error('self-test package bridge did not block non-target anchor') end
if not (abi and abi.Status=='target-not-target-image' and abi.TargetImage==false and not abi.AbiVerified and not abi.NativeBridgeArmed) then error('self-test package ABI state did not block non-target anchor') end
if not (frame and frame.Status=='target-not-target-image' and frame.TargetImage==false and not frame.AbiVerified and not frame.TCharLayoutVerified and not frame.CallFrameReady and not frame.NativeInvoked) then error('self-test package call frame did not block non-target anchor') end
if not (adapter and adapter.Status=='target-not-target-image' and not adapter.FunctionPointerReady and not adapter.AbiVerified and not adapter.TCharLayoutVerified and not adapter.CallFrameReady and not adapter.NativeBridgeArmed and not adapter.AdapterReady and not adapter.NativeCallable and not adapter.NativeInvoked) then error('self-test package adapter did not block non-target anchor') end
if not (descriptor and descriptor.DescriptorKind=='guarded-package-native-call' and descriptor.NativeCallPlanConstructed and not descriptor.NativeCallable and not descriptor.NativeInvoked) then error('self-test package descriptor did not preserve non-callable adapter state') end
if not (executor and executor.ExecutorKind=='guarded-package-native-executor' and executor.TargetName=='StaticLoadObject' and type(executor.TargetAddress)=='number' and executor.TargetAddress > 0 and executor.TargetImage==false and executor.SignatureFamily=='StaticLoadObject' and executor.NativeExecutorReady==false and executor.ExecutorPreflightPassed==false and executor.FinalNativeCallEligible==false and executor.NativeExecutorBlockReason=='target-not-target-image' and executor.FinalNativeCallBlocked and executor.FinalNativeCallBlockReason=='preflight-state-only' and not executor.NativeInvoked) then error('self-test package executor did not block non-target anchor') end
if not (native and native.Status=='target-not-target-image' and native.InvokeRequested and native.InvokeEnabled and not native.NativeBridgeArmed and not native.AbiVerified and not native.TCharLayoutVerified and not native.CallFrameReady and native.GuardedCallReady and native.ReturnValidationReady and not native.NativeCallable and not native.NativeInvoked and not native.NativeCallPlanAccepted) then error('self-test package native invoke did not block non-target anchor') end
LUA

dll_win="$(WINEDEBUG=-all winepath -w "$loader" 2>/dev/null)"
log_win="$(WINEDEBUG=-all winepath -w "$log" 2>/dev/null)"
lua_dll_win="$(WINEDEBUG=-all winepath -w "$lua_dll" 2>/dev/null)"
mod_root_win="$(WINEDEBUG=-all winepath -w "$mod_root" 2>/dev/null)"

WINEDEBUG=-all \
DUNE_WIN_CLIENT_PROBE_LOG="$log_win" \
DUNE_WIN_CLIENT_PROBE_AUTO_THREAD=false \
DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=0 \
DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=false \
DUNE_WIN_CLIENT_PROBE_UE_SELF_TEST_ANCHOR=true \
DUNE_WIN_CLIENT_PROBE_LOAD_ASSET_PACKAGE_SELF_TEST_ANCHOR=true \
DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE=true \
DUNE_WIN_CLIENT_PROBE_LUA_DLL="$lua_dll_win" \
DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED=true \
DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT="$mod_root_win" \
DUNE_WIN_CLIENT_PROBE_LOAD_ASSET_PACKAGE_ABI_EVIDENCE=self-test-static-load-object \
DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_ABI=true \
DUNE_WIN_CLIENT_PROBE_TCHAR_UNIT_BYTES=2 \
DUNE_WIN_CLIENT_PROBE_TCHAR_EVIDENCE=self-test-windows-wchar \
DUNE_WIN_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT=true \
DUNE_WIN_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE=true \
DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL=true \
DUNE_WIN_CLIENT_PROBE_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD=true \
  wine rundll32.exe "$dll_win,DuneWinClientProbeSmoke" >/tmp/dune-win-client-probe-package-preflight.out 2>&1

require_log() {
  local pattern="$1"
  if ! grep -q "$pattern" "$log"; then
    echo "missing expected Windows package preflight log pattern: $pattern" >&2
    sed -n '1,220p' "$log" >&2 || true
    sed -n '1,160p' /tmp/dune-win-client-probe-package-preflight.out >&2 || true
    exit 1
  fi
}

require_log 'event=lua-load-asset-package-bridge-state status=target-not-target-image .*targetImage=false .*packageAvailable=true'
require_log 'event=lua-load-asset-package-preflight status=native-bridge-missing .*targetName=StaticLoadObject .*target=0x[1-9a-fA-F][0-9a-fA-F]* .*targetImage=false .*targetMapped=true .*targetReadable=true .*targetExecutable=true .*targetProtect=0x[1-9a-fA-F][0-9a-fA-F]* platformAbi=win64-ms-abi invokeEnabled=true nativeBridgeArmed=false nativeCallable=false nativeInvoked=false packageAvailable=true'
require_log 'event=lua-load-asset-package-call-frame-verification-state status=target-not-target-image .*targetImage=false .*abiVerified=false .*tcharLayoutVerified=false .*callFrameReady=false nativeInvoked=false'
require_log 'event=lua-load-asset-package-crash-guard-state status=.* platformAbi=win64-ms-abi mechanism=windows-.* available=true enabled=true recoverable=.* armed=.* nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-call-adapter-state status=target-not-target-image .*functionPointerReady=false .*nativeBridgeArmed=false adapterReady=false .*nativeCallable=false nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-executor-state status=prepared .*nativeExecutorReady=false executorPreflightPassed=false finalNativeCallEligible=false .*nativeExecutorBlockReason=target-not-target-image .*finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only nativeInvoked=false'
require_log 'event=lua-load-asset-package-native-invoke status=target-not-target-image .*targetImage=false .*invokeRequested=true invokeEnabled=true .*abiVerified=false tcharLayoutVerified=false callFrameReady=false nativeBridgeArmed=false .*nativeCallPlanAccepted=false .*nativeCallable=false nativeInvoked=false'

echo "Windows client package self-test target-image guard smoke passed: $log"
