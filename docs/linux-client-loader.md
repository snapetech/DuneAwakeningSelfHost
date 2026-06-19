# Linux Client Loader

Status on 2026-06-16: native Linux client preload support is scaffolded as a
read-only runtime probe. Confidence: high.

This is not a complete UE4SS Linux port. It is the client-side counterpart to
the server probe loader: a small shared object loaded with `LD_PRELOAD` into a
native Linux ELF process. It logs loaded modules and can scan readable mappings
for strings and byte signatures, then reports runtime address, image offset, and
file offset.

The cross-client support matrix and shared runbook live in
`docs/client-loader-support.md`.

The shared portability contract is generated with
`scripts/ue4ss-portability-contract.py --check`. It keeps the
Linux native client, Windows/Proton client, and Linux dedicated server surfaces aligned while
preserving the correct injection split: this target uses `LD_PRELOAD`, while
the Proton target uses `version.dll`.
Strict completion also requires `runtimeRootDiscovery=true`, meaning the live
target image promoted both runtime roots before hook, reflection, Lua, or
package-loading evidence can count toward full UE4SS parity.

## Supported Target

Supported now:

- Native Linux ELF Dune client executable.
- Launch-time injection with `LD_PRELOAD`.
- Read-only module and memory-map scanning.
- Presets for Unreal, client, CheatManager, BRT, and Deep Desert anchors.
- Smoke test parity through `scripts/smoke-linux-client-loader.sh`.

Not supported by the native Linux loader:

- Windows/PE Dune client running under Proton.
- Installing or replacing files inside a Steam game directory.
- Live UE4SS Lua compatibility against Dune's reflected object model.
- Live UE4SS Lua callback dispatch from real `ProcessEvent` calls or game
  memory patching.

If the client target is a Windows executable under Proton, a Linux `.so` cannot
be preloaded into it. That path needs a Windows DLL/proxy/injection artifact
loaded inside the Wine process, plus a separate bridge strategy if Linux-side
coordination is required. Confidence: high.

That Windows/Proton path now lives in `docs/windows-client-loader.md`.

## Build

Check the host build prerequisites first:

```bash
make loader-build-toolchain-check
```

If a dependency is missing, install the loader toolchain with:

```bash
make loader-build-toolchain-install
```

The Linux client build script also runs that install-capable toolchain guard
before compiling, so missing CMake/Ninja/compiler packages are installed through
the host package manager when supported.

```bash
scripts/build-linux-client-loader.sh
```

Default output:

```text
build/linux-client-loader/libdune_client_probe_loader.so
```

## Launch A Native Linux Client

```bash
scripts/launch-linux-client-probe.sh -- /path/to/DuneSandbox-Linux-Shipping
```

The wrapper builds the loader if missing, verifies that the target looks like an
ELF executable, sets default scan variables, and then execs the client with
`LD_PRELOAD`.

Use `DUNE_CLIENT_PROBE_PREFLIGHT_ONLY=true` with the same command to validate
the target/loader plan without building, setting `LD_PRELOAD`, or executing the
client. The preflight still rejects Windows/PE targets; those belong on the
Windows/Proton DLL path.

Default log:

```text
/tmp/dune-client-probe-loader.log
```

Smoke test:

```bash
scripts/smoke-linux-client-loader.sh
```

Useful scan variables:

```dotenv
DUNE_CLIENT_PROBE_SCAN_ENABLED=true
DUNE_CLIENT_PROBE_LOG_MODULES=true
DUNE_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
DUNE_CLIENT_PROBE_SCAN_STRINGS=ProcessEvent;CallFunctionByNameWithArguments;FNamePool;GUObjectArray;StaticLoadObject;LoadObject;LoadPackage;ResolveName;CheatManager
DUNE_CLIENT_PROBE_SCAN_SIGNATURES=name=48 8b ?? ?? 48 85 c0
DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE=/path/to/client-signatures.txt
DUNE_CLIENT_PROBE_UE_ANCHORS=FNamePool=0x0;GUObjectArray=0x0;GWorld=0x0;GEngine=0x0;ProcessEvent=0x0;CallFunctionByNameWithArguments=0x0
DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=
DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=/path/to/client-anchor-signatures.txt
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS=false
DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS=0
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=false
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES=268435456
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS=1
DUNE_CLIENT_PROBE_UE_POINTER_PROBE=false
DUNE_CLIENT_PROBE_UE_LAYOUT_PROBE=false
DUNE_CLIENT_PROBE_UE_UOBJECT_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=false
DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_CLIENT_PROBE_UE_REFLECTION_MAX_FIELDS=16
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_CLIENT_PROBE_UE_REFLECTION_FUNCTION_FLAGS_OFFSET=0x58
DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_START=0x48
DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_END=0xa0
DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=false
DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_MAX_BYTES=16
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=false
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS=128
DUNE_CLIENT_PROBE_UE_FNAME_PROBE=false
DUNE_CLIENT_PROBE_UE_FNAME_POOL=
DUNE_CLIENT_PROBE_UE_FNAME_BLOCKS_OFFSET=0x10
DUNE_CLIENT_PROBE_UE_FNAME_STRIDE=2
DUNE_CLIENT_PROBE_UE_FNAME_MAX_LENGTH=128
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
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ADDRESS=
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=
DUNE_CLIENT_PROBE_LUA_MODS_ENABLED=false
DUNE_CLIENT_PROBE_LUA_MOD_SCRIPTS=
DUNE_CLIENT_PROBE_LUA_MOD_ROOT=
DUNE_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=false
DUNE_CLIENT_PROBE_GAME_DIR=
DUNE_CLIENT_PROBE_UNREAL_VERSION_MAJOR=5
DUNE_CLIENT_PROBE_UNREAL_VERSION_MINOR=0
DUNE_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_CLIENT_PROBE_SCAN_PATH_FILTER=DuneSandbox;/Engine/Binaries/Linux
```

`DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE` accepts one `name=aa bb ??` pattern
per line or semicolon-delimited patterns. It is the preferred path for large
validated manifests because the loader can now hold up to 256 signature
patterns. Confidence: high.

`DUNE_CLIENT_PROBE_UE_ANCHORS` validates explicit runtime addresses without
writing memory. Mapped anchors are folded into the scan summary as
`kind=ue-anchor`; unmapped anchors remain blockers. Use real addresses from a
validated signature or xref pass, not the zero placeholders above. Confidence:
high.

`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES` and
`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` resolve `name=aa bb ??` byte
patterns inside the filtered executable mappings and promote only unique
matches to UE anchors. Missing or ambiguous signatures are logged and skipped.
Use `Name@hit+N`, `Name@riprel32+N`, `Name@callrel32`, or `Name@ptr+N` when a
signature match must be transformed into the anchor address. Confidence: high.
`scripts/export-elf-signature-manifest.py --format anchor-signatures` emits
that loader-consumable file from validated promotable UE signature rows; point
`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` at it for the next read-only
canary.

Set `DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS=true` only for a bounded runtime
root pass when explicit anchors or signature anchors are not available. The
loader scans readable+writable target-image mappings for unique FNamePool and
GUObjectArray-shaped roots. Set
`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=true` when the native
ELF loader places relocated Unreal globals in anonymous RW mappings; the same
mapping byte cap still applies. Use
`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=true` only for a bounded
diagnostic pass when root evidence points at heap/bracketed private RW mappings.
Pair it with a small
`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES` value to record
why FName-shaped roots failed the strict `None` first-entry gate. Use
`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES` and
`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS` after an
ambiguous-root canary to fail fast and filter tiny GUObjectArray-shaped false
positives. Unique hits promote as `RuntimeFNamePool` and
`RuntimeGUObjectArray`, and then feed the existing pointer, FName, object-array,
UObject, reflection, and Lua registry probes. Missing or ambiguous roots are
logged and skipped. Current builds include `targetWritableMappings`,
`privateWritableMappings`, `rejectedFNameSamples`,
`anonymousWritableMappings`, `oversizedMappings`, `scannedSlots`, `fnameProbes`,
and `objectArrayProbes` on `ue-runtime-discovery-finish`. When the scanner has
a FName hit and enough GUObjectArray-shaped hits to prove object-root ambiguity,
it emits `event=ue-runtime-discovery-limited` plus `limited=true` and proceeds
to validation instead of spending the whole canary window scanning. If no target
writable image mapping is scanned, they emit
`event=ue-runtime-discovery name=target-writable-image-mappings status=missing`.
Each `ue-runtime-discovery-candidate` row also includes target-image
`imageOffset`, `fileOffset`, `perms`, and `map` evidence so ambiguous root
hits can be triaged by module and file offset without promoting them.
For explicit replay of a proven native Linux runtime root, use
`DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS=RuntimeFNamePool@rwfile=0x...` or
`RuntimeGUObjectArray@rwfile=0x...`. `@rwfile` resolves the offset against the
current process's readable+writable non-executable anonymous/private runtime
mappings and logs `runtimeRwFileOffset=true`; missing matches are skipped.
Set `DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS` to run a second UE-only root
validation pass after startup. The delayed pass logs `phase=ue-delayed` and is
the native Linux client equivalent of the Windows/Proton delayed probe.
Confidence: moderate until a live Dune client canary produces promoted runtime
roots.

Set `DUNE_CLIENT_PROBE_UE_POINTER_PROBE=true` for the second read-only canary
after explicit anchors are configured. It reads one pointer-sized value from
each readable anchor address and validates whether that value points to mapped
memory. A `target-mapped` result is the minimum signal needed before attempting
FName/object/world layout validation. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_LAYOUT_PROBE=true` after pointer targets are mapped.
It reads up to `DUNE_CLIENT_PROBE_UE_LAYOUT_SLOTS` pointer-sized fields from the
mapped target and logs whether each slot is null, unmapped, or points to mapped
memory. This still does not interpret Unreal layouts; it only gives bounded
evidence for the first FName/object/world reader pass. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_UOBJECT_PROBE=true` only after pointer targets are
mapped. It reads the standard `UObjectBase`-shaped fields from the pointed-to
target: vtable, object flags, internal index, `ClassPrivate`, the `FName` pair,
and `OuterPrivate`. A `status=candidate` line with `classMapped=true` is a
read-only object candidate, not proof that full UE reflection or UE4SS Lua
dispatch is ready. Confidence: high.

Set `DUNE_CLIENT_PROBE_HOOK_SELF_TEST=true` only for a lab/smoke run after the
read-only gates are understood. It temporarily installs an inline jump on a
loader-owned self-test function, verifies dispatch to a replacement function,
executes one pre-callback, calls the original bytes through a generated
trampoline, executes one post-callback, then restores the original bytes before
returning. It does not hook `ProcessEvent` or any game function. Confidence:
high.

Set `DUNE_CLIENT_PROBE_MOD_SELF_TEST=true` to exercise the native mod-dispatch
scaffold. It registers one loader-owned mod entry, runs load, pre-hook,
post-hook, and unload callbacks around the same hook dispatch context, and logs
`event=mod-dispatch-self-test`. This is the ABI spine for later Lua binding; it
does not execute Lua scripts yet. Confidence: high.

Set `DUNE_CLIENT_PROBE_LUA_SELF_TEST=true` to execute a real Lua VM self-test
through a dynamically loaded Lua shared library. `DUNE_CLIENT_PROBE_LUA_LIBRARY`
can pin a specific library; otherwise the loader tries common names such as
`liblua5.4.so`. The default script calls a loader-provided
`RegisterHook('/Script/DuneProbe.SelfTest:Function', pre, post)` function,
stores the Lua pre/post callbacks in the registry, and then native code invokes
both callbacks. A pass logs `event=lua-dispatch-self-test ... result=42` plus
`callbackStatus=0 preCalls=1 postCalls=1 preResult=11 postResult=31`,
`executeAsyncCalls=1 executeWithDelayCalls=2 loopAsyncCalls=1 schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1`,
`keyBindLookupHits=1`, `keyBindCallbackHandled=1`,
`keyBindUnregisterCalls=1`, `keyBindUnregisterHits=1`,
`consoleCommandHandlers=2`, `consoleCommandGlobalHandlers=1`,
`consoleCommandUnregisterCalls=1`, and `consoleCommandUnregisterHits=1`,
plus direct dispatch counters `consoleCommandHandlerCalls=1` and
`consoleCommandGlobalHandlerHandled=1`.
The direct paths are exposed as
`DuneProbeDispatchKeyBind(context, key)` and
`DuneProbeDispatchConsoleCommand(context, rawCommand)`. The default script also
unregisters temporary keybind and command handlers and proves those removed
callbacks do not fire. This
proves Lua-to-native hook registration, native-to-Lua callback dispatch, and
script result handling. `RegisterHook` returns UE4SS-shaped `preId, postId`
values, and `UnregisterHook(name, preId, postId)` removes a registered pair.
The loader also registers UE4SS-style globals
`UnregisterHook`, `StaticFindObject`, `FindObject`, `FindFirstOf`, `GetKnownObjects`,
`FindObjects`, `FindAllOf`, `ForEachUObject`, `IsA`, `LoadAsset`,
`StaticConstructObject`, `NotifyOnNewObject`, `ExecuteInGameThread`,
`DrainGameThreadQueue()`, `ExecuteAsync`, `ExecuteWithDelay`, `LoopAsync`, `DrainSchedulerQueue()`, `CancelScheduledCallback`,
`FName`, `FText`,
`RegisterKeyBind`, `IsKeyBindRegistered`, `RegisterConsoleCommandHandler`,
`RegisterConsoleCommandGlobalHandler`, `RegisterProcessConsoleExecPreHook`,
`RegisterProcessConsoleExecPostHook`, `RegisterCustomEvent`,
`RegisterCustomProperty`, `RegisterCallFunctionByNameWithArgumentsPreHook`,
`RegisterCallFunctionByNameWithArgumentsPostHook`,
`ExecuteInGameThread` stores callbacks in a bounded game-thread queue and
returns a queued id; `DrainGameThreadQueue()` drains that queue in smoke tests.
`ExecuteAsync`, `ExecuteWithDelay`, and `LoopAsync` store callbacks in a
bounded scheduler queue; `DrainSchedulerQueue()` drains it and
`CancelScheduledCallback` releases queued scheduler or game-thread callbacks
before dispatch. These queues are Lua-state-owned, so callbacks are only
drained, cancelled, or released by the Lua state that created them. They are the
future handoff point for a real Unreal tick/game-thread pump; when live Lua
ProcessEvent dispatch is enabled, the live ProcessEvent post-hook pumps the
owning scheduler queue after post-hook callbacks.
`RegisterULocalPlayerExecPreHook`, `RegisterULocalPlayerExecPostHook`,
`RegisterLocalPlayerExecPreHook`, `RegisterLocalPlayerExecPostHook`,
`DuneProbeDispatchCustomEvent`, `DuneProbeLoadMap`, `DuneProbeBeginPlay`,
`DuneProbeInitGameState`, `DuneProbeDispatchKeyBind`,
`DuneProbeDispatchConsoleCommand`,
`IterateGameDirectories`, and common lifecycle hook
registration shims. `RegisterCustomEvent`,
`RegisterLoadMapPreHook`/`PostHook`, `RegisterBeginPlayPreHook`/`PostHook`, and
`RegisterInitGameStatePreHook`/`PostHook` now store Lua refs and dispatch through
loader-owned shims with `(context, eventName, payload, handled)`. They are not
attached to live UE lifecycle functions until those call targets are discovered
and hooked in the running client. The UE4SS callback spellings are exposed as
aliases too: `RegisterLoadMapPreCallback`, `RegisterLoadMapPostCallback`,
`RegisterBeginPlayPreCallback`, `RegisterBeginPlayPostCallback`,
`RegisterInitGameStatePreCallback`, and `RegisterInitGameStatePostCallback`,
with matching unregister names. It also
seeds UE4SS-style `UE4SS`,
`UnrealVersion`, `ModRef`, `EObjectFlags`, `EInternalObjectFlags`,
`PropertyTypes`, `Key`, `ModifierKey`, and `ModifierKeys` tables. `ModRef`
supports loader-local `SetSharedVariable`/`GetSharedVariable` for nil, string,
integer, bool, and known object handles. It also exposes per-mod `ModRef`
context while each entrypoint runs: `Name`/`GetModName()`,
`Path`/`GetModPath()`/`GetModDir()`, and `ScriptPath`/`GetModScriptPath()`
come from the active `Mods/<ModName>/Scripts/main.lua` script. The loader also
exposes `ScriptDir`/`GetModScriptDir()` and prepends that directory to
`package.path` before executing the entrypoint, so mod-local `require("file")`
and nested `require("lib.file")` work from `Scripts/`. Use
`dofile(ModRef:GetModScriptDir() .. "/file.lua")` for explicit sibling files.
The Linux client smoke proves this path with real Lua.
`StaticFindObject`, `FindObject`, `FindFirstOf`, `FindObjects`, and
`FindAllOf` return bounded object-handle tables from the loader's object
registry; `GetKnownObjects()` returns a table keyed by runtime `PathName` plus
`Count`; `ForEachUObject(callback[, class])` iterates that same registry; and
`IsA(object, class)` checks the handle class or the base `UObject`.
`ProcessEvent(object, functionOrName[, args])` and
`object:ProcessEvent(functionOrName[, args])` are exposed as UE-shaped Lua
compatibility aliases for the existing hook-aware bounded `CallFunction` shim.
They do not invoke live engine `UObject::ProcessEvent` until the runtime hook
bridge is armed, but the Linux client smoke proves the loaded-mod Lua surface.
The `lua-mod-finish` line must include `processEventCompatCalls=2` and
`processEventCompatHits=2` for the smoke mod, and readiness reports that as
`luaProcessEventCompat=true` before aggregate Lua dispatch can pass.
`GetProcessEventBridgeState()` exposes the live hook/trampoline state to Lua
mods without invoking native `ProcessEvent`; the Linux client smoke requires
`processEventBridgeStateCalls=2`, and readiness reports that as
`luaProcessEventBridgeState=true`.
`InvokeProcessEventNative(object, function, {Value=n})` is also registered, but
it is intentionally guarded. The API now separates registry readiness from
execution readiness: `ObjectAllowed` requires a registered object address,
`FunctionAllowed` requires promoted `UFunction` descriptor evidence, and
`SelfTestCallable` is only true for the loader-owned self-test object/function
that can safely run through the current trampoline. A successful smoke emits
`event=lua-process-event-native-invoke-self-test status=passed` with
`ObjectRegistryAllowed=true`, `FunctionDescriptorAllowed=true`,
`SelfTestCallable=true`, `processEventNativeCalls=2`, and
`processEventNativeHits=1`; readiness reports that as
`luaProcessEventNativeInvoke=true`. The second call is the descriptor-backed
non-self-test preflight that stays behind the closed gate and is reported as
`luaProcessEventNativeInvokeNonSelfTestGate=true`. This proves the
Lua-to-native ProcessEvent trampoline path plus registry/descriptors gates, not
arbitrary live UE ProcessEvent dispatch.
`CreateProcessEventParams(function)` allocates a bounded loader-owned params
buffer from promoted descriptors and returns the same `ProcessEventParams`
table shape used by live hook callbacks. Loaded mods can use
`GetParamValue`, `SetParamValue`, and direct descriptor aliases such as
`params.Value:get()` against that buffer. The Linux client smoke exercises this
outside an active callback so descriptor-backed params marshaling is proven
before arbitrary native `ProcessEvent` invocation is enabled. Readiness exposes
that direct construction proof as `luaProcessEventParamsBuffer`.
`InvokeProcessEventNative` also reports descriptor preflight fields:
`DescriptorBackedCallable`, `ParamsBufferConstructible`,
`ParamsDescriptorCount`, `ParamsBufferSize`, `InvokeRequested`, and
`NativeNonSelfTestEnabled`. Non-self-test calls stay in
`descriptor-preflight-ready` unless Lua passes `{Invoke=true}`; with invocation
requested and `DUNE_CLIENT_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE`
unset, the result is `non-self-test-invoke-disabled`, counted as
`luaProcessEventNativeInvokeNonSelfTestGateCount`. Readiness exposes the
no-call state as `luaProcessEventNativeInvokeDescriptorPreflight` and the
closed explicit-invoke state as `luaProcessEventNativeInvokeNonSelfTestGate`.
With both gates open, the loader seeds a descriptor-sized params buffer from matching Lua table fields,
calls the original ProcessEvent trampoline, and reports
`NativeNonSelfTestInvoked=true`, `ParamsWritten=<n>`, and
`status=non-self-test-invoked`.
`LoadAsset(pathOrName)` resolves an already-registered object handle by path or
name and returns `nil` when the object is not in the registry; it does not load
packages yet. Readiness exposes that remaining full-port gap separately as
`luaLoadAssetPackage=false`; `luaObjectApi=true` only proves registry-backed
lookup/enumeration. `GetLoadAssetBackendState()` returns a guarded backend
contract with `Backend="registry"`, `RegistryFallback=true`, and
`PackageBackendArmed=false` until a real `StaticLoadObject`/`LoadPackage`
bridge is installed. It also reports package-anchor visibility through
`PackageBackendAvailable`, `StaticLoadObjectResolved`, `LoadObjectResolved`,
`LoadPackageResolved`, and `ResolveNameResolved`. It also reports
`PackageBackendTargetImage`; this must be true before the guarded native
package-call path can arm. Readiness reports mod
coverage for the Lua contract as `luaLoadAssetBackendState` and anchor-informed
coverage as `luaLoadAssetBackendAnchors`. A mod can also request the guarded
bridge status with `GetLoadAssetPackageBridgeState()`. That call refreshes the
same package anchors, selects the first available `StaticLoadObject`/`LoadObject`/
`LoadPackage` target, verifies whether the target is mapped and executable, and
returns `NativeBridgeArmed=false`, `AbiVerified=false`, `InvokeEnabled`, and a
`Status` such as `anchor-missing`, `target-not-mapped`,
`target-not-target-image`, `target-not-executable`, `invoke-disabled`, or
`abi-unverified`. Readiness
reports mod coverage for that checkpoint as `luaLoadAssetPackageBridgeState`.
`GetLoadAssetPackageAbiState()` reports the next ABI checkpoint for the selected
package-loading target without calling it. It returns
`Source="loader-load-asset-package-abi-state"`, `PlatformAbi="sysv-x86_64"`,
`SignatureFamily`, `RequiredSignature`, `AbiVerified=false`,
`CallFrameReady=false`, `StringBridgeReady=false`, `ClassRootReady=false`, and
`OuterReady=false`; the loader logs `event=lua-load-asset-package-abi-state`.
Readiness reports this as `luaLoadAssetPackageAbiState`, still separate from
real `luaLoadAssetPackage`.
`PrepareLoadAssetPackageStringBridge(path)` stages bounded UTF-8 path input for
the package string bridge without constructing a UE `TCHAR` buffer. It returns
`Source="loader-load-asset-package-string-bridge-state"`,
`StringInputStaged=true`, `BoundedInput=true`, `InputEncoding="utf-8"`,
`TCharEncoding="unverified-live-build"`, `TCharBridgeReady=false`,
`NativeBufferReady=false`, and `NativeInvoked=false`; the loader logs
`event=lua-load-asset-package-string-bridge-state`. Readiness reports this as
`luaLoadAssetPackageStringBridge`, still not `luaLoadAssetPackage`.
`PrepareLoadAssetPackageNativeBuffer(path)` stages a bounded, NUL-terminated
UTF-8 native input buffer descriptor. It returns
`Source="loader-load-asset-package-native-buffer-state"`,
`Utf8BufferReady=true`, `NativeInputBufferReady=true`, `BufferBytes`,
`NullTerminated=true`, `TCharEncoding="unverified-live-build"`,
`TCharBufferReady=false`, `CallFrameReady=false`, and `NativeInvoked=false`;
the loader logs `event=lua-load-asset-package-native-buffer-state`. Readiness
reports this as `luaLoadAssetPackageNativeBuffer`, still not
`luaLoadAssetPackage`.
`PrepareLoadAssetPackageTCharBuffer(path)` reports the Linux candidate `TCHAR`
layout without claiming it is the live UE layout. It returns
`Source="loader-load-asset-package-tchar-buffer-state"`,
`CandidateEncoding="host-wchar-unverified"`, host `CandidateUnitBytes`,
`CandidateBufferBytes`, `TCharLayoutVerified=false`,
`TCharBufferReady=false`, `CallFrameReady=false`, and `NativeInvoked=false`;
the loader logs `event=lua-load-asset-package-tchar-buffer-state`. Readiness
reports this as `luaLoadAssetPackageTCharBuffer`, still not
`luaLoadAssetPackage`.
`GetLoadAssetPackageTCharVerificationState()` reports whether explicit canary
evidence has verified the candidate Linux `TCHAR` layout. It reads
`DUNE_CLIENT_PROBE_TCHAR_UNIT_BYTES`, `DUNE_CLIENT_PROBE_TCHAR_EVIDENCE`, and
`DUNE_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT`; default status is `evidence-missing`
with `TCharLayoutVerified=false` and `TCharBufferReady=false`. Readiness reports
this as `luaLoadAssetPackageTCharVerification`.
`GetLoadAssetPackageCallFrameVerificationState(path)` combines path staging,
the resolved package target, explicit package ABI evidence, and verified
`TCHAR` layout evidence before declaring a native package-call frame ready. It
reads `DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_ABI_EVIDENCE` and
`DUNE_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_ABI`; default status is
`abi-evidence-missing` with `AbiVerified=false`, `CallFrameReady=false`, and
`NativeInvoked=false`. Readiness reports this as
`luaLoadAssetPackageCallFrameVerification`.
`PrepareLoadAssetPackageCallFrame(path)` stages the requested path into a
non-invoking package-call descriptor. It returns
`Source="loader-load-asset-package-call-frame-state"`, `PathStaged=true`,
`ArgumentDescriptorReady=true`, `PlatformAbi="sysv-x86_64"`,
`SignatureFamily`, `ArgumentCount`, `TCharBridgeReady=false`,
`CallFrameReady=false`, and `NativeInvoked=false`; the loader logs
`event=lua-load-asset-package-call-frame-state`. Readiness reports this as
`luaLoadAssetPackageCallFrame`, still not `luaLoadAssetPackage`.
`InvokeLoadAssetPackageNative(path, {Invoke=true})` exercises the next guarded
invocation checkpoint without crossing into UE yet. It returns
`Source="loader-load-asset-package-native-bridge"`, `ContractVersion=1`,
`Invoked=false`, `InvokeRequested`, `InvokeEnabled`, `AbiVerified`,
`TCharLayoutVerified`, `CallFrameReady`, and `NativeBridgeArmed`.
`NativeBridgeArmed` only becomes true after the package ABI and `TCHAR`
evidence gates pass, `PackageBackendTargetImage=true`, and
`DUNE_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE` is enabled; this checkpoint
still does not call UE. The loader logs
`event=lua-load-asset-package-native-invoke` and counts
`loadAssetPackageNativeCalls`/`loadAssetPackageNativeGateHits`. Readiness
reports this as `luaLoadAssetPackageNativeInvoke`, which is still not
`luaLoadAssetPackage`.
`GetLoadAssetPackageNativeCallAdapterState(path)` exposes the SysV x86_64
package-load adapter selected for the future native call. It reports
`AdapterKind="sysv-x86_64-package-load"`, `FunctionPointerReady`,
`CallFrameReady`, `NativeBridgeArmed`, `AdapterReady`, and
`NativeInvoked=false`. The final-call envelope reports
`FinalInvokeConfirmed=false`, `CrashGuardRequired=true`,
`CrashGuardArmed=false`, `ReturnValidationReady=true`, and
`NativeCallable=false`; readiness reports this as
`luaLoadAssetPackageNativeCallAdapter`.
`GetLoadAssetPackageNativeExecutorState(path)` exposes the final Linux SysV
executor boundary for the same guarded package call. Readiness reports
`luaLoadAssetPackageNativeExecutor` only when the canary row proves
`NativeExecutorReady=true`, `ExecutorPreflightPassed=true`, and
`FinalNativeCallEligible=true` in the target image. Dry-run executor shape rows
remain diagnostic evidence and do not satisfy the runtime package-loading
contract.
A mod can also request the guarded
package path with `LoadAsset(path, {Backend="package"})`, `{Package=true}`, or
`{TryPackage=true}`; setting `DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN=1`
requests the same path for unknown registry assets. The loader refreshes package
anchors, logs `event=lua-load-asset-package-preflight
status=native-bridge-missing`, increments
`loadAssetPackagePreflightCalls`/`loadAssetPackageGateHits`, and still returns
`nil`. Readiness exposes that as `luaLoadAssetPackagePreflight`; it is not
`luaLoadAssetPackage` and does not complete `ue4ssLuaApiComplete`.
`StaticConstructObject` creates a loader-owned
synthetic `/RuntimeProbe/Constructed/<Name>` handle. It does not allocate or
initialize a live Unreal object yet, but it preserves `ClassAddress` when the
class argument is a known object or `UClass` handle.
The `ue` scan preset includes `StaticLoadObject`, `LoadObject`, `LoadPackage`,
and `ResolveName` as read-only candidates for the eventual package backend.
Readiness exposes proven package anchors as `packageLoadingSurface` and
prepared canary package coverage as `anchorCoveragePackageLoading`.
`targetPackageLoadingSurface` must also be true before package-backed
`LoadAsset` is treated as target-image ready; loader-image package anchors do
not satisfy the strict contract. Confidence: high.
`NotifyOnNewObject(filter, callback)` is bounded to that synthetic path: it
stores up to 32 class/path/name filter registrations and dispatches every
matching callback when `StaticConstructObject` creates a loader-owned handle.
The default Lua dispatch self-test requires `notifyOnNewObjectCallbacks=1`,
`notifyOnNewObjectResult=17`, and `notifyOnNewObjectStatus=0`.
Returned object/function handle tables
also expose UE4SS-style methods: `GetFullName`, `GetName`, `GetPathName`,
`GetAddress`, `IsValid`, `GetClass`, `GetOuter`, `GetWorld`, `GetFName`,
`type`, `IsClass`, `IsAnyClass`, `IsA`, `HasAllFlags`, `HasAnyFlags`,
`HasAnyInternalFlags`, `GetPropertyValue`, `SetPropertyValue`, and
`CallFunction`, plus UE4SS method stubs/compat methods `ProcessConsoleExec`,
`ULocalPlayerExec`,
`GetFunctionFlags`, `SetFunctionFlags`, `GetSuperStruct`, `GetSuper`,
`GetSuperClass`, `ForEachFunction`, `ForEachProperty`, `GetCDO`,
`GetDefaultObject`, `GetDefaultObj`, `IsChildOf`, and `GetLevel`. `ForEachFunction`
iterates unique promoted `UFunction` handles for loader-owned self-test handles
and scanned object/class handles whose address, `ClassAddress`, name, or class
matches a promoted UFunction owner through the same bounded registry used by
`GetKnownFunctions`; it is not full live `UStruct` function-chain traversal yet.
Passed iteration emits `event=lua-function-iteration-check status=passed`;
`mode=owner` is required for `luaFunctionIterationRuntime=true`.
Handles also expose `ClassAddress`, `OuterAddress`, and `SuperAddress`
when scan metadata is available. `GetClass` returns a `UClass` handle whose
`Address` is the live scanned `ClassPrivate` pointer when available and zero
for purely synthetic registry entries;
`GetOuter` resolves the loader-owned outer for synthetic objects created by
`StaticConstructObject` and otherwise returns `nil`;
`GetSuperStruct`, `GetSuper`, and `GetSuperClass` prefer a scanned `SuperAddress` and otherwise returns a
synthetic `UObject` class for non-`UObject` synthetic `UClass` handles or
`nil`;
`GetWorld` returns the handle itself for registered world-like handles,
resolves loader-owned `OuterAddress` chains to a registered world, and can fall
back to a registered `GWorld`/`UWorld`-like handle for common world-context
classes. It is not a live engine `UObject::GetWorld` call yet.
The global `GetWorld()` helper uses the same bounded world-like handle
resolution. The global `GetEngine()` helper returns a discovered engine-like
handle or creates one loader-owned `UEngine` handle until live `GEngine`
promotion exists.
After Lua mod dispatch, the loader emits `lua-global-runtime-helper-check` with
`globalWorldPromoted` and `globalEnginePromoted` so canaries can distinguish
loader-owned fallback handles from UE-promoted handles.
`GetCDO`, `GetDefaultObject`, and `GetDefaultObj` return a loader-owned `Default__<Class>` handle for `UClass` handles
with `RF_ClassDefaultObject` set; it is not the live engine class-default
object yet. `GetLevel` returns a registered level-like handle for level objects
and loader-owned outer chains; it is not a live `AActor::GetLevel` call yet,
`IsChildOf` is truthful for loader-owned self/base-class checks and walks the
bounded scan-derived `SuperAddress` chain when both class handles carry live
addresses; it is not full `GUObjectArray`-backed hierarchy enumeration yet.
`ProcessConsoleExec` dispatches loader-owned
`RegisterProcessConsoleExecPreHook` callbacks, then
`RegisterConsoleCommandHandler`/`RegisterConsoleCommandGlobalHandler`
callbacks, then `RegisterProcessConsoleExecPostHook` callbacks. Console exec
hooks receive `(context, rawCommand, command, args, handled)` and may return
boolean true to mark the command handled. It does not hook live engine console
routing yet,
`ULocalPlayerExec` dispatches loader-owned
`RegisterULocalPlayerExecPreHook` callbacks and
`RegisterULocalPlayerExecPostHook` callbacks with the same
`(context, rawCommand, command, args, handled)` shape. It is a distinct
loader-owned dispatcher and does not hook live `ULocalPlayer::Exec` yet,
`CallFunction` and `CallFunctionByNameWithArguments` dispatch loader-owned
`RegisterCallFunctionByNameWithArgumentsPreHook` callbacks before its bounded
self-test function shim and `RegisterCallFunctionByNameWithArgumentsPostHook`
callbacks after it. The function argument may be a string name or a promoted
`UFunction` handle from `FindFunction`, `FindFirstFunction`,
`ForEachFunction`, or `ForEachUFunction`; handle calls resolve the promoted
function name before hook dispatch. The argument value may be a plain string,
a table with an explicit `Args`, `Arguments`, or `Command` string, or a bounded
structured table using fields such as `Value`, `Message`, `Flag`,
`SignedByte`, `Mode`, `UnsignedShort`, `SignedLarge`, `FloatValue`,
`DoubleValue`, `Location`, `OriginalResult`, `Touched`, `NameToken`,
`ProbeValue`, and `ProbeBool`; structured tables are serialized
deterministically into command text before hook dispatch, with `Location`
formatted from `{X,Y,Z}`/`{x,y,z}`.
Call-function hooks receive
`(context, functionName, args, handled, result)` and may return
`replacement, true` to short-circuit or replace the result. It does not hook the
live engine `UObject::CallFunctionByNameWithArguments` path yet,
scanned UObject handles also expose `ObjectFlags`, `InternalIndex`,
`HasObjectMetadata`, and, when the object-array item flags word is readable,
`InternalFlags`/`HasInternalFlags`; scanned UFunction handles also expose
`FunctionFlags` and `HasFunctionFlags`; `HasAllFlags`/`HasAnyFlags` use the
promoted `ObjectFlags`, and `GetFunctionFlags` returns promoted
`FunctionFlags` when readable.
`SetFunctionFlags` mutates loader-owned Lua handle metadata and syncs matching
loader registry entries, but it does not write live UFunction memory.
`HasAnyInternalFlags` uses promoted `InternalFlags` and returns false for
handles without decoded internal flag metadata. The self-test seeds a
`/Script/DuneProbe.SelfTestObject` handle and requires both lookup paths plus
object enumeration, `IsA`, and synthetic construction to succeed. Class-mapped
`ue-uobject` probe candidates are also ingested as
`/RuntimeProbe/<AnchorName>` handles and logged as `event=lua-object-registry`.
When the FName decoder is available, decoded object names are additionally
registered as `/RuntimeProbe/<DecodedName>` aliases with
`source=ue-uobject-fname`; object-array aliases for the same address/name are
reported as `status=skipped` instead of creating duplicate handles.
`Reflection()` returns a loader-owned `UObjectReflection` table for known
handles. `Reflection():GetProperty(name)` resolves self-test properties,
promoted `UFunction` param descriptors, and scalar live reflection candidates
into UE4SS-style property descriptor tables. Descriptor methods include
`GetFullName`, `GetFName`, `IsA`, `GetClass`, `ContainerPtrToValuePtr`,
`ImportText`, `ExportText`, `ExportTextItem`, `GetOffset_Internal`,
`GetOffsetInternal`, `GetElementSize`, `GetSize`, `GetArrayDim`,
`GetPropertyFlags`, `HasAnyPropertyFlags`, `GetPropertyClass`, bool mask helpers, `GetStruct`, `GetInner`,
and `type`. `Object:ForEachProperty(callback)`, `Function:ForEachProperty(callback)`,
and `Reflection():ForEachProperty(callback)` iterate those known descriptor sets
and the reflection-handle path is tracked as `luaReflectionForEachProperty`.
Lua-dispatch readiness also requires `luaReflectionForEachPropertyRuntime=true`.
Promoted scalar live reflection descriptors support guarded `GetValue()` and
raw-set-enabled `SetValue()`, tracked as `luaReflectionLiveDescriptorValues`.
Lua-dispatch readiness also requires
`luaReflectionLiveDescriptorTypedClassRuntime=true` and
`luaReflectionLiveDescriptorTypedValuesRuntime=true` and
`luaReflectionLiveDescriptorTypedSetValuesRuntime=true` and
`luaReflectionLiveDescriptorValuesRuntime=true`; a false value means the proof
is still generic, lacks decoded `FProperty` class identity, lacks typed
`GetValue()` proof, or only touched loader-owned `SelfTest*` descriptors.
Typed live `GetValue()` currently covers guarded bool, float, double,
object/class/interface, FName, FString-shaped `FStrProperty`, FVector-sized
`FStructProperty`, and integer/byte/enum-sized values where the live descriptor
class and element size are known. With the raw-set gate enabled, live
`SetValue()` also supports the bounded scalar path, including byte/enum-sized
integer writes, plus FString-shaped
`FStrProperty` strings and FVector-sized `FStructProperty` tables. This is a
bounded descriptor shim, not complete live `FProperty` traversal,
FText/container storage, or general struct-field marshaling.
The smoke path also seeds `/RuntimeProbe/RuntimeProbeObject` so runtime
provenance can exercise descriptor enumeration, typed `GetValue()`, and typed
`SetValue()` plus owner-mode `ForEachFunction` without relying on `SelfTest*`
names. Owner-mode iteration also emits a runtime `lua-function-registry-check`
after path/runtime-path/name/address/flags lookup succeeds. That keeps native Linux,
Linux server, and Proton/Windows parity honest, but it is still loader-owned
evidence until a live canary validates real Dune property offsets.
The same smoke path now also seeds a UE-shaped
`/RuntimeProbe/RuntimeProbeUObject` with a non-`SelfTest*` class and FName. It is
discovered by the normal `ue-uobject` scanner and logs
`registryProvenance=runtime`, so `luaObjectRegistryRuntime=true` can be proven
without counting the synthetic `source=runtime-probe` handle.
The async/delay/loop helpers invoke callbacks immediately in the probe
environment, and registration shims allocate ids without live engine event
dispatch until the corresponding Unreal callsites are hooked. `FName`/`FText`
construct loader-visible value tables compatible with the existing ProcessEvent
param value shape; `FName` values expose `ToString()` and
`GetComparisonIndex()` methods. `FName(index[, number])` and
`DecodeFName(index[, number])` use the active `FNamePool` resolver when present
and return `IsDecoded=false` when no resolver is available. Lua mods do not need
to register a hook to be considered loaded; a clean no-hook compatibility
script passes in the smoke test.
Set `DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=true` to attempt a bounded
FChunkedFixedUObjectArray walk from configured anchors; it tries both direct and
indirect anchor interpretations and logs `event=ue-object-array` plus
`source=ue-object-array` registry handles for class-mapped items. Set
`DUNE_CLIENT_PROBE_UE_FNAME_PROBE=true` with a valid `FNamePool`/`GName` anchor
or explicit `DUNE_CLIENT_PROBE_UE_FNAME_POOL` address to decode candidate
`NamePrivate` values. Successful decodes log `event=ue-fname status=decoded`.
When a UObject or object-array item is promoted, the loader also logs
`event=ue-object-native-identity` with decoded object name, decoded class name,
class pointer, and `OuterPrivate`; readiness exposes this as
`ueObjectNativeIdentities` before treating native object handles as real UE
identity evidence.
Confidence: high on hosts with a compatible Lua 5.4 C API library.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_PROBE=true` after the UObject and FName
probes are stable. It reads the candidate object's class pointer and emits
`event=ue-reflection` plus `event=ue-reflection-slot` for configured UClass and
field/function slots. The default offsets match the synthetic self-test layout;
override them from current-build analysis before treating live output as
actionable. This is read-only metadata discovery, not live `FProperty`
marshaling. Confidence: high for the self-test fixture.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=true` after the class/slot
probe is stable. It walks bounded `children`, `childProperties`,
`propertyLink`, and `functionLink` chains, using
`DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_NEXT_OFFSET` and
`DUNE_CLIENT_PROBE_UE_REFLECTION_MAX_FIELDS`, and logs
`event=ue-reflection-field status=candidate`. This is the next read-only
reflection gate before live `FProperty` decoding. Confidence: high for the
self-test fixture, moderate for live Dune until offsets are canary-validated.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=true` after field walking
is stable. It implies the bounded field walk and reads property-shaped
descriptor fields from `childProperties` and `propertyLink`: `ArrayDim`,
`ElementSize`, `PropertyFlags`, and `Offset_Internal`. Successful reads log
`event=ue-reflection-property status=candidate`. This is descriptor telemetry,
not Lua-visible live property get/set. Confidence: high for the self-test
fixture, moderate for live Dune until offsets are canary-validated. For each
bounded `functionLink` candidate, the same probe also reads function-level
`FunctionFlags`, `childProperties`, and `propertyLink` roots and emits
`event=ue-function-param-root` plus `event=ue-function-param` descriptor lines
when param metadata is readable. Readable descriptors and readable
`FunctionFlags` values are promoted into the bounded live `UFunction` param
registry, and
`GetFunctionParamDescriptors(function)`/`GetFunctionParams(function)` returns
them when Lua passes the matching live function handle. The handle also exposes
`Function:GetFunctionParams()`, `Function:GetFunctionParamDescriptors()`,
`Function:GetParamDescriptor(name)`, and `Function:ForEachParam(callback)`;
readiness tracks the table method path as `ueProcessEventFunctionParamMethod`,
direct name lookup as `ueProcessEventFunctionParamLookupMethod`, and callback
iteration as `ueProcessEventFunctionParamIterationMethod`.
When the `functionLink`
FName decodes, `event=ue-function-param` also carries `functionName`,
UE4SS-style `functionPath`, and `functionRuntimePath`, and Lua
`ctx.Function.PathName`/`GetFunctionParams(ctx.Function)` use the
`/Script/<owner>.<function>:Function` identity while retaining the older
`/RuntimeProbe/<owner>.<function>:Function` identity as runtime evidence.
The loader also emits `event=ue-function-native-identity`; readiness exposes
this as `ueFunctionNativeIdentities`. This is raw descriptor visibility with
decoded `fieldClassName`/`ClassName` when the FName
decoder can read the parameter field's class object. Lua can distinguish scalar, bool, and
object-pointer params from that metadata, but this is not full live `FProperty`
marshaling for strings, names, arrays, structs, or complex out-param lifetimes.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=true` after descriptor offsets
are stable. It implies descriptor probing and reads up to
`DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_MAX_BYTES` raw bytes from the owning
object at `Offset_Internal`, logging `event=ue-reflection-value status=read`
with `raw` and `rawLe`. This is bounded value telemetry, not typed property
marshaling or Lua-visible get/set. Confidence: high for the self-test fixture,
moderate for live Dune until offsets are canary-validated.

Set `DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=true` after the plain Lua
self-test passes. It installs an inline hook on a loader-owned
`ProcessEvent(UFunction*, void*)` stand-in, dispatches the Lua pre/post
callbacks registered by `RegisterHook`, calls the original bytes through the
trampoline, restores the hook, and logs `event=lua-process-event-self-test`.
The default script also exercises guarded `GetParamValue`/`SetParamValue`
access against the loader-owned params block and logs
`paramDescriptorHits=2 paramDescriptorLookupHits=17
functionParamDescriptorHits=2 paramGetHits=29 paramSetHits=11`. The `Params`
table includes descriptor metadata under
`Properties` with `Name`, `Type`, `ClassName`, `OffsetInternal`, `ElementSize`,
`PropertyFlags`, `Size`, `ArrayDim`, `IsParm`, `IsOutParm`, and
`IsReturnParm`, and Lua can retrieve descriptor handles through
`GetParamDescriptor`. `Params.<Name>` and `Params.Values.<Name>` also expose
loader-owned `RemoteUnrealParam`-style wrappers with `get()`, `Get()`, `set()`,
`Set()`, and `type() == "RemoteUnrealParam"`. `GetParamValue` returns booleans for `FBoolProperty`
descriptors, byte-sized enum integers for `FEnumProperty` descriptors,
object-handle tables for object/class/interface pointer
descriptors, decoded `FName` tables when an `FNamePool` resolver is cached,
bounded read-only `FStrProperty` strings, guarded `FVector` tables for
`FStructProperty` descriptors with `X/Y/Z` and `x/y/z` fields, and
`FStructProperty:GetStruct()` returns a synthetic `/Script/CoreUObject.Vector`
`UScriptStruct` handle for that bounded vector shape. It also covers guarded signed/unsigned integer
scalars, and guarded `float`/`double` values for scalar descriptors;
`SetParamValue` accepts the matching Lua boolean/object/table/address/integer, vector table,
and numeric forms. Lua can
also call
`GetFunctionParamDescriptors(ctx.Function)` or the shorter `GetFunctionParams`
alias to retrieve a function-scoped descriptor table with `PropertyCount` and
`Properties`. Mods can resolve the promoted runtime function registry with
`FindFunction(pathOrName)`, `FindFirstFunction()`, and `GetKnownFunctions()`;
`GetKnownFunctions()` returns a table keyed by runtime `PathName` plus `Count`,
`ForEachUFunction(callback[, filter])` enumerates the same promoted registry
globally, and compatible owner/class handles can enumerate owner-matched
promoted functions with `ForEachFunction(callback)`.
These APIs only expose UFunctions already discovered by the bounded
`functionLink` descriptor probe. This proves the ProcessEvent-shaped Lua bridge and
function-param descriptor bounded self-test params access. The default routing
self-test registers one nonmatching hook and one matching hook, so `hooks=2`
with `preCalls=1 postCalls=1` proves known-path `RegisterHook` filtering
through `ctx.functionPath`. Hook routing matches exact paths first and then
falls back to the terminal function name, so a UE4SS-style `/Script/...`
registration can match a discovered `/RuntimeProbe/<Outer>.<Function>:Function`
runtime path without allowing the non-target hook to fire. Canary logs expose
this as `pathExactMatches` and `pathAliasMatches`. This is not full live
`FProperty` marshaling.
Confidence: high on hosts with a compatible Lua 5.4 C API library.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=true` after a unique
`ProcessEvent` target has been resolved from explicit anchors or
`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES`. The loader first validates that the
target is mapped and executable. With
`DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=true`, it installs an inline
hook and immediately restores it; use
`DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=true` to constrain
that install/restore path to loader-owned code in smoke tests. This proves
target hookability, not a persistent live ProcessEvent dispatcher. Confidence:
high.

Set `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=true` after a unique
`CallFunctionByNameWithArguments` target has been resolved from explicit
anchors or `DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES`. With
`DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=true`, it temporarily installs
and restores `CallFunctionHookProbe`; use
`DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=true` only for
loader-owned smoke tests. This proves hookability, not real command/function
marshaling. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=true` after the guarded
CallFunction hook probe passes on the same target. The scaffold resolves from
`DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS`, the hook-probe address,
the generic CallFunction address, explicit anchors, or signature-resolved
anchors. It installs once, calls the original through the trampoline, optionally
logs bounded calls, and restores on unload. This proves the persistent native
interception spine; Lua command/function argument marshaling remains gated on
runtime object and command parsing evidence. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=true` only after the guarded
hook probe passes on the same target. The scaffold resolves the target from
`DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS`, the hook-probe address,
the generic ProcessEvent address, explicit anchors, or signature-resolved
anchors. It installs once, leaves the hook active for the process lifetime,
calls the original through the trampoline, optionally logs bounded calls, and
restores on unload. When bounded call logging is enabled,
`event=ue-process-event-live-context status=resolved` proves sampled raw
`Object`/`Function`/`Params` pointers resolved to a Lua-visible object handle, a
runtime-provenance `UFunction` path plus runtime function path, a nonzero params
pointer, and promoted function param descriptors. Self-test provenance remains
logged as `status=partial` and does not satisfy native runtime identity. The
same bounded sample emits
`event=ue-process-event-live-registry-context` with
`objectNativeIdentity=true` and `functionNativeIdentity=true` only when both
handles come from promoted registries with runtime provenance; readiness exposes this as
`ueProcessEventLiveRegistryContext`. New loader builds also include
`functionProvenance=runtime|self-test` on both context lines; readiness prefers
that explicit field and falls back to path heuristics only for older logs.
Readiness also reports runtime-only registry gates:
`luaObjectRegistryRuntime`, `luaFunctionRegistryRuntime`,
`luaDecodedObjectAliasesRuntime`, and `ueObjectArrayRegistryRuntime`. Broad
registry gates may pass on loader-owned `SelfTest*` handles, but object
discovery, reflection, and Lua dispatch readiness require non-self-test runtime
registry evidence.
Current local smokes report `luaObjectRegistryRuntime=true`,
`luaFunctionRegistryRuntime=true`, `luaFunctionIterationRuntime=true`, and
`ueObjectArrayRegistryRuntime=true` on the native Linux client, Linux server,
and Windows/Proton client. Aggregate `luaDispatch` remains false until live
non-self-test ProcessEvent runtime context and runtime registry context are
proven.
Current loader builds append `registryProvenance=runtime|self-test` to
`lua-object-registry`, `lua-object-registry-check`,
`lua-function-registry-check`, and `lua-function-iteration-check` lines.
Readiness prefers that explicit field and falls back to name/path heuristics
only for older logs. Confidence: high.
`scripts/plan-ue4ss-canary-env.py --format json` now emits the same runtime
evidence contract for native Linux as for Proton/Windows: registry rows require
`registryProvenance=runtime`, live ProcessEvent context rows require
`functionProvenance=runtime`, and hook target rows require
`selfTestTarget=false callSelfTest=false`. The generated
`post-canary-verify.sh` summary repeats those requirements beside the gate
results. Confidence: high.
The same planner output includes `callFunctionRuntimeEvidenceContract`:
CallFunction hook probe/live-hook rows need the non-self-test fields, and
`ue-call-function-live-hook` must report `luaDispatch=true` before
CallFunction Lua hook parity is treated as runtime-backed. Confidence: high.
Readiness exposes the combined promoted
runtime registry plus active-param accessor proof as
`ueProcessEventLiveClassAwareParamValues`; self-test provenance does not count.
The same bounded sample emits
`event=ue-process-event-live-param`
for descriptor-backed scalar, bool, object-pointer, `FName`, `FString`, and
vector reads from the active params block, and readiness counts those param
rows only when the sampled ProcessEvent context is runtime-proven. For arrays
it emits
`status=container` and Lua `GetParamValue` returns an `FScriptArray` table with
`Data`, `Num`, `Max`, `BytesHex`, address, offset, class, type, and size
metadata. If the array data pointer is readable, the table also includes
`DataSampleAddress`, `DataSampleReadSize`, and `DataSampleBytesHex`, and the log
value includes `dataSampleHex=...`. `FScriptArray` tables expose
`GetNum()`, `NumElements()`, `GetData()`, `GetDataSampleBytes()`,
`GetRawElement(index, byteCount)`, and `GetElement(index)`. `GetElement` uses
promoted `Inner*` metadata when present to decode bounded scalar, object,
`FName`, `FString`/`FText`, and `FVector` elements; unsupported element classes return a raw element table with
`BytesHex`. For sets and maps it emits `FScriptSetHeader` and
`FScriptMapHeader` tables with `GetNum()`, `NumElements()`, `GetData()`, and
bounded raw reads. Sets expose `GetRawEntry(index, byteCount)`, `GetRawElement(index, byteCount)`, and
`GetElement(index)`, `Get(index)`, and `get(index)`; maps expose `GetRawPair(index, byteCount)`,
`GetRawElement(index, byteCount)`, `GetPair(index)`, `Get(index)`, `get(index)`,
`GetKey(index)`, and `GetValue(index)`. Promoted set headers
include `Element*` metadata, and promoted map headers include `Key*` and
`Value*` metadata. `GetElement(index)`, `GetPair(index)`, `GetKey(index)`, and `GetValue(index)` use that metadata
to decode bounded scalar, object, `FName`, `FString`/`FText`, and `FVector` values for descriptor-backed dense storage.
All container headers also expose `GetStorageLayout()`,
`IsSparseLayoutValidated()`, and `GetSlotStride()`. Current smoke-proven
headers report dense descriptor-backed storage; real `FScriptSet`/`FScriptMap`
sparse layout traversal remains gated until a live canary proves slot stride and
allocation flags.
Readiness now requires this surface through
`ueProcessEventContainerStorageLayoutMethods`: both the ProcessEvent Lua
self-test and live hook rows must report nonzero container storage-layout method
hits before `luaDispatch=true` is treated as UE4SS parity evidence.
Container descriptor discovery separately emits
`event=ue-function-param-container-child` for decoded `FArrayProperty`,
`FSetProperty`, or `FMapProperty` inner/key/value child metadata. The
ProcessEvent self-test also emits descriptor-backed
`source=process-event-self-test` records for array inner, set element, and map
key/value metadata. The bounded scan window defaults to `0x48..0xa0` via
`DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_START` and
`DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_END`. Promoted live param
descriptors expose decoded children to Lua as `ContainerChildren` plus
`GetInner()`, `GetElementProperty()`, `GetKeyProperty()`, and
`GetValueProperty()` where applicable.
Raw `byteCount` stays caller-supplied, and live-build `FScriptSet`/`FScriptMap`
sparse slot layout still needs validation before treating every slot as a typed
occupied element.
Unsupported complex values, including non-vector structs, still emit
`status=raw value=rawHex=...` and Lua returns a `RawUnrealParam` table. This
still does not perform complete arbitrary container element unmarshaling or
complete live `FProperty` object marshaling.
Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true` with the live
hook scaffold in a smoke/lab run to arm native ProcessEvent pre/post callbacks.
The persistent hook invokes those callbacks around the original function and
logs the callback counts. This proves the native dispatch spine before Lua is
attached. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=true` with the live
hook scaffold after native dispatch passes. The loader creates a persistent Lua
VM for the live hook, executes
`DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT` or the default
`RegisterHook` script, stores the Lua pre/post refs, and invokes those callbacks
from the live ProcessEvent hook around the original call. The callback receives
a table with raw `object`, `function`, and `params` addresses plus `stage`,
`call`, `originalCalled`, `preCallbacks`, and `postCallbacks`; when the loader
can resolve those addresses, it also includes UE4SS-shaped `Object` and
`Function` handle tables plus a `Params` context table. A pass logs
`event=ue-process-event-live-lua-dispatch status=armed` and the live hook line
reports `luaDispatch=true luaObjectHandleHits=2 luaFunctionHandleHits=2
luaParamsHandleHits=2 luaParamDescriptorHits=2
luaParamDescriptorLookupHits=12 luaFunctionParamDescriptorHits=2
luaParamGetHits=18 luaParamSetHits=6`. The readiness gate also requires the
armed live Lua dispatch to carry multiple `RegisterHook` entries and the
close-out line to report the matching callback results `preResult=11` and
`postResult=31`, proving the non-target hook did not satisfy routing.
`GetFunctionParamDescriptors`/
`GetFunctionParams` first return live registry descriptors when `ctx.Function`
matches a scanned `UFunction`, and fall back to the self-test `Value`,
`OriginalResult`, and `Touched` fields for loader-owned callbacks.
The readiness report tracks this as `ueProcessEventLiveFunctionPath=true`,
which requires live `ctx.Function`/`functionPath` evidence to match a decoded
scanned UFunction path from the read-only function descriptor probe.
`GetParamValue` and `SetParamValue` accept descriptor tables from either source,
but they are guarded to the active callback's params block, mapped page
permissions, descriptor type, and scalar/bool/object/name/string width. This
proves live ProcessEvent-to-Lua callback routing with handle-backed
object/function context, a stable params address table, and bounded
scalar/bool/object-pointer plus in-place `FName`/`FString` params get/set
plumbing, not full live `FProperty` marshaling. When the synthetic function path
is known, dispatch filters
registered hooks by `ctx.functionPath`; exact path matches are counted as
`pathExactMatches`, and terminal function-name fallback matches are counted as
`pathAliasMatches`. The built-in live Lua dispatch self-test registers through
an alternate `/Script/...` owner with the same terminal UFunction name, proving
alias routing in addition to exact routing. Unresolved live `UFunction` paths
remain permissive until real path/name discovery is proven. Confidence: high on
hosts with a compatible Lua 5.4 C API library.

Set `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH=true` with the live
CallFunctionByNameWithArguments hook after the ProcessEvent Lua VM is armed.
The live CallFunction hook routes
`RegisterCallFunctionByNameWithArgumentsPreHook` and
`RegisterCallFunctionByNameWithArgumentsPostHook` callbacks through that
persistent VM around the original call. A pass logs
`event=ue-call-function-live-hook ... status=installed luaDispatch=true` with
nonzero `luaPreCalls` or `luaPostCalls`; the default self-test post hook changes
`DoubleProbeValue` from `42` to `84`, so `luaPostHandled=1 result=84` proves Lua
handled the live CallFunction path. The readiness report tracks this as
`ueCallFunctionLiveLuaDispatch=true`. This is callback dispatch over the
resolved native function target with the same bounded table-to-command-string
argument subset as the loader-owned shim, not full arbitrary `FProperty`
argument marshaling by itself. Confidence: high.

Set `DUNE_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST=true` after the plain Lua
self-test passes. It exposes UE4SS-shaped `GetPropertyValue`,
`SetPropertyValue`, and `CallFunction` globals to Lua and exercises them against
the loader-owned `/Script/DuneProbe.SelfTestObject` handle. For the raw
property read only, the default self-test prefers the registered
`/RuntimeProbe/SelfTestUObject` candidate and falls back to the synthetic handle
when no runtime candidate was discovered. In the smoke fixture the scan logs
`fieldName=SelfTestUObjectName_0 rawLe=0x7`, then the loader mutates its own
`SelfTestUObject` scalar to prove Lua is doing a guarded live re-read through a
decoded property alias. If
`DUNE_CLIENT_PROBE_LUA_REFLECTION_RAW_SET_ENABLED=true`, the self-test also
writes `17` back to that loader-owned candidate and re-reads it, logging
`rawPropertySetHits=1 rawPropertySetValue=17`. Keep this flag false for live
read-only canaries. A read-only pass logs `rawPropertyValue=13`; a raw-set pass
logs `event=lua-reflection-self-test ... result=42 getPropertyHits=21
rawPropertyHits=3 rawPropertyValue=17 namedPropertyHits=1 rawPropertySetHits=1
rawPropertySetValue=17 arrayInnerPropertyHits=1 enumPropertyHits=1
enumUnderlyingPropertyHits=1 setElementPropertyHits=1 mapKeyPropertyHits=1
mapValuePropertyHits=1 importTextHits=2 setPropertyHits=10 probeFloat=13.750
probeDouble=-47.500 probeName=ArrakisName probeText=WaterDebt
callFunctionHits=2`. Without that
registry, the raw lookup returns nil and the self-test still covers the
synthetic fields.
This proves integer, boolean, float, double, `FName`, string, `FText`,
object-handle, function-call, bounded `FArrayProperty:GetInner()` metadata, and
bounded `FEnumProperty:GetEnum()` / `GetUnderlyingProperty()` metadata, and
bounded `FSetProperty` element plus `FMapProperty` key/value metadata, and
bounded `FProperty:ImportText()` text-to-value writes for loader-owned scalar
and enum/string-like descriptors, bounded `FProperty:ExportText()` value-to-text
exports for the same loader-owned descriptors, bounded descriptor `GetValue()` /
`SetValue()` for `ProbeEnum`, bounded property metadata accessors for offset,
size, array dimension, and property flags, and gated raw candidate get/set
through the Lua reflection dispatch surface, not complete live typed
`FProperty` marshaling or arbitrary container storage marshaling from Dune
objects.
Confidence: high on hosts
with a compatible Lua 5.4 C API library.

Set `DUNE_CLIENT_PROBE_LUA_MODS_ENABLED=true` to load Lua mod entrypoints from
`DUNE_CLIENT_PROBE_LUA_MOD_SCRIPTS` (semicolon-separated files) and
`DUNE_CLIENT_PROBE_LUA_MOD_ROOT`. The root scanner accepts direct `*.lua` files
and the UE4SS-style `Mods/<ModName>/Scripts/main.lua` layout. Set
`DUNE_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=true` to invoke the callbacks
registered by the loaded mod script and log
`event=lua-mod-dispatch-self-test ... status=passed`. `RegisterHook` is a
bounded registry, so separate mod scripts can register callbacks without
overwriting the previous script's pre/post callbacks. Script reads are capped at
256 KiB and the loader accepts at most 32 entrypoints and 32 hook registrations
per run. If a script fails to load or execute, `event=lua-mod-script` includes a
sanitized `error=` field. Confidence: high.

This per-mod `ModRef` context is loader-owned metadata, not the full UE4SS mod
manager lifecycle yet. Confidence: high.

Loaded mod scripts can register loader-owned `RegisterModInitCallback`,
`RegisterModPostInitCallback`, and `RegisterModUnloadCallback` handlers. After
all entrypoints finish loading, the loader dispatches `ModInit`,
`ModPostInit`, and then `ModUnload` with `(nil, eventName, phase, handled)`.
When live ProcessEvent Lua dispatch is enabled, enabled Lua mods also load into
the persistent live ProcessEvent Lua state, report
`lua-live-mod-start`/`lua-live-mod-finish`, dispatch `ModInit`/`ModPostInit`
when armed, remain registered for live hook dispatch, and dispatch `ModUnload`
when that live state closes.
`lua-mod-finish` reports `modInitCallbacks`, `modPostInitCallbacks`,
`modUnloadCallbacks`, `modInitCalls`, `modPostInitCalls`, `modUnloadCalls`,
`modInitHandled`, `modPostInitHandled`, and `modUnloadHandled`. Confidence:
high.

Loader-owned registrations now return stable ids for active registrations and
can be removed without waiting for Lua teardown. The native Linux client exposes
`UnregisterKeyBind`, `UnregisterConsoleCommandHandler`,
`UnregisterCustomEvent`, and the lifecycle unregister family including
`UnregisterModUnloadCallback`; unregistering compacts the active registration
array, releases the Lua registry ref, and reports
`callbackUnregisterCalls=16 callbackUnregisterHits=16` for the UE4SS-style
callback families covered by the smoke path. Confidence: high.

`DUNE_CLIENT_PROBE_LUA_MOD_ROOT` also honors a UE4SS-style `mods.txt` file:
blank lines and `#` comments are ignored, `ModName` and `+ModName` load in file
order, and `-ModName` or `!ModName` disables a root mod. Unlisted root mods are
appended after listed entries. `event=lua-mod-start` reports `manifestEntries`
and `manifestDisabled`. Confidence: high.

Use `DUNE_CLIENT_PROBE_TARGET` when the loader may be inherited by helper
processes:

```dotenv
DUNE_CLIENT_PROBE_TARGET=DuneSandbox-Linux-Shipping;DuneAwakening
```

## Package

```bash
scripts/package-linux-client-loader.sh
```

Default package location:

```text
dist/linux-client-loader/
```

## Analysis

Summarize a real client log:

```bash
scripts/summarize-client-loader-scan.py /tmp/dune-client-probe-loader.log
scripts/summarize-linux-loader-xrefs.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --exe-substring DuneSandbox \
  --category cheat
scripts/summarize-linux-loader-anchors.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --exe-substring DuneSandbox \
  --category cheat
scripts/validate-elf-signatures.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --exe-substring DuneSandbox \
  --category cheat \
  --format json > build/linux-client-loader/elf-signature-validation.json
scripts/export-elf-signature-manifest.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --target-loader linux-client \
  --exe-substring DuneSandbox \
  --category cheat \
  --format signatures > build/linux-client-loader/client-signatures.txt
scripts/export-elf-signature-manifest.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --target-loader linux-client \
  --exe-substring DuneSandbox \
  --category ue \
  --format anchor-signatures > build/linux-client-loader/client-anchor-signatures.txt
scripts/summarize-client-ue-anchors.py /tmp/dune-client-probe-loader.log
scripts/export-ue-anchor-env.py /tmp/dune-client-probe-loader.log \
  --loader client \
  --platform linux \
  > build/linux-client-loader/ue-anchors.env
scripts/export-ue-anchor-env.py /tmp/dune-client-probe-loader.log \
  --loader client \
  --platform linux \
  --include-runtime-candidates \
  > build/linux-client-loader/ue-runtime-root-candidates.env
scripts/prepare-ue-anchor-canary.py \
  --platform linux-client \
  --binary /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --include-runtime-candidates \
  --output-dir build/linux-client-loader/client-anchor-canary
scripts/plan-ue4ss-canary-env.py \
  --platform linux-client \
  --client-log /tmp/dune-client-probe-loader.log \
  --max-stage read-only \
  --format json \
  > build/linux-client-loader/next-canary.json
scripts/plan-ue4ss-canary-env.py \
  --platform linux-client \
  --client-log /tmp/dune-client-probe-loader.log \
  --max-stage read-only \
  > build/linux-client-loader/next-canary.env
scripts/ue4ss-port-readiness.py \
  --client-log /tmp/dune-client-probe-loader.log \
  --loader client
```

`export-ue-anchor-env.py` exports core discovery anchors plus reflection anchors
by default. It accepts mapped explicit anchor validation and resolved
`ue-anchor-signature` records; raw `scan-hit` rows stay as xref/signature
candidate evidence and are not exported as explicit anchors unless
`--include-scan-hits` is used for a documented manual exception. Unresolved and
ambiguous signatures remain missing.
The readiness core-anchor gates use that same conservative evidence rule:
mapped `ue-anchor` or resolved `ue-anchor-signature` only. Plain scan hits do
not pass `ue-names`, `ue-objects`, `ue-world`, `ue-dispatch`, or
`ue-reflection-surface`. Confidence: high.
Readiness also reports `targetObjectDiscovery` and `targetHooks`; these require
the core anchors to resolve in the native client executable or game module, not
inside `libdune_client_probe_loader.so`. Confidence: high.
Runtime `ue-anchor` and `ue-anchor-signature` rows include a normalized
`group=` field. Core groups are `names`, `objects`, `world`, `dispatch`, and
`reflection`; domain groups include `cheat`, `brt`, and `deep-desert`.
Synthetic `SelfTest*` anchors report `self-test` and do not prove live
object-discovery readiness.
The JSON scan summary reports these as anchor/signature group count maps. The
shared readiness report exposes merged `anchorGroups` and
`anchorGroupProvenance`; `false` means the log came from an older loader or an
anchor line is missing `group=`.
`prepare-ue-anchor-canary.py` combines the validated UE signature manifest,
loader-consumable anchor signature file, second-pass anchor env, validation
summary, readiness report, object-discovery coverage, and
`post-canary-verify.sh` for the next read-only launch. The env includes
`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` pointing at the generated
signature sidecar. It also writes `anchor-coverage.json` and a README summary
showing whether the combined explicit anchors and signature-promotable anchors
cover the names, objects, world, dispatch, and reflection groups needed before
object discovery or hook planning; the generated readiness report receives the
same coverage file via `--anchor-coverage-json`. After the next native-client
canary, run `post-canary-verify.sh [loader-log]` from that output directory to
rebuild readiness, object-discovery coverage, the UE4SS gap summaries
(`ue4ss-port-gaps.json` and `ue4ss-port-gaps.md`), and a compact post-canary
summary from the collected log.
For the repo wrapper that also snapshots the collected log, prepared anchor env,
and generated verifier artifacts into one evidence directory, run:

```bash
scripts/verify-client-probe-canary.sh \
  --platform linux-client \
  --prep-dir build/linux-client-anchor-canary \
  --log /tmp/dune-client-probe-loader.log \
  --output-dir backups/client-probe-canary/linux-client/manual
```

The native Linux launch wrapper can source the prepared bundle directly:

```bash
DUNE_CLIENT_PROBE_PREP_DIR=build/linux-client-anchor-canary \
scripts/launch-linux-client-probe.sh -- /path/to/DuneSandbox-Linux-Shipping
```

Preflight mode validates `ue-anchors.env` plus the selected post-canary
verifier before launching:

```bash
DUNE_CLIENT_PROBE_PREFLIGHT_ONLY=true \
DUNE_CLIENT_PROBE_PREP_DIR=build/linux-client-anchor-canary \
scripts/launch-linux-client-probe.sh -- /path/to/DuneSandbox-Linux-Shipping
```

Use report-only mode for read-only discovery. When the canary is meant to prove
UE4SS-runtime readiness, add `--strict` to
`scripts/verify-client-probe-canary.sh`; it uses
`post-canary-verify-strict.sh`, sets
`DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true`, and exits nonzero unless the runtime
object/function registry, non-self-test hook-target, live ProcessEvent context,
live CallFunction Lua dispatch, and live reflection descriptor runtime gates
are all true. It also requires exact/promotable same-build signature validation
and object/hook/package anchor coverage, so
`strictRuntimeContract.contractReady` is true only when both runtime evidence
and `signatureAnchorReady=true` are satisfied with no
`missingSignatureAnchorReadyKeys`. The verifier accepts either current `ready`
booleans or passed readiness `gates` as evidence, matching the canary planner.
Confidence: high.
The readiness JSON also includes `perLoaderReadiness`, and Markdown output
includes `Per Loader Readiness`. Check the `client` row, which is the native
Linux client log label; `linux-client` is accepted as a filter alias. Aggregate
readiness may include evidence from the Linux server or Windows/Proton client.
The canary planner's
`postCanaryVerification.crossPlatformStrictRuntimeContract` is the broader
1:1-port gate: it stays false until the server, native Linux client, and
Proton/Windows loader rows all have ready live target-image contracts.
Confidence: high.
Promotable ELF signatures only count toward UE4SS discovery when they map to UE
anchor names. BRT, cheat, cap, and other gameplay signatures remain useful drift
checks, but they do not prove `FNamePool`, `GUObjectArray`, `GWorld`, or
`ProcessEvent`. The canary prep summary prints manifest category counts and UE
anchor signature entry count; a zero count keeps the native Linux client on
read-only anchor discovery. Confidence: high.
For UE-category non-string xrefs, promote candidates before validation:

```bash
scripts/summarize-linux-loader-xrefs.py /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --exe-substring DuneSandbox \
  --category ue \
  --format json > build/linux-client-loader/ue-anchor-xrefs.json

scripts/promote-ue-anchor-xref-candidates.py \
  build/linux-client-loader/ue-anchor-xrefs.json \
  --format json > build/linux-client-loader/ue-anchor-candidates.json

scripts/validate-elf-signatures.py /path/to/DuneSandbox-Linux-Shipping \
  --xref-json build/linux-client-loader/ue-anchor-candidates.json \
  --category ue \
  --format json > build/linux-client-loader/ue-anchor-signature-validation.json
```

The promotion step rejects string targets by default because a literal
`FNamePool` reference is not the global anchor. Confidence: high.
`plan-ue4ss-canary-env.py` emits the next guarded native-client env from
readiness evidence. It defaults to read-only object/reflection discovery and,
independent of the upstream readiness builder, re-checks proven anchor
provenance before escalation. If a readiness JSON lacks
`anchorGroupProvenance=true`, claims object discovery without proven
names/objects/world anchor groups, or claims hook-capable stages without a
proven dispatch anchor, the planner stays in read-only object/reflection
discovery and does not emit ProcessEvent hook or Lua dispatch variables.
It also refuses escalation when `targetObjectDiscovery=false` or
`targetHooks=false`; broad anchor presence is not enough if the anchors only
resolve inside `libdune_client_probe_loader.so`. Confidence: high.
JSON/Markdown output includes machine-readable `blockers[]` entries
with stable `code`, blocked `stage`, and message fields for automation. When
the readiness report includes prepared anchor coverage, it refuses hook/live Lua
escalation until object-discovery groups and
ProcessEvent-level dispatch coverage are present. It also refuses hook/live Lua
escalation while `findObjectSemantics=false`, because object-array registry
entries, native identities, outer-chain full names, and Lua object API calls
must be proven first. Use `--max-stage hook-probe`, `live-hook`, or
`lua-dispatch` only for the matching lab canary phase. `live-hook` and
`lua-dispatch` plans also enable bounded live
ProcessEvent call logging so `ue-process-event-live-context` readiness evidence
is collected in the same canary. The planner also requires
`ueProcessEventHookRuntimeTarget`, `ueProcessEventLiveHookRuntimeTarget`,
`ueProcessEventLiveRuntimeContext`, and
`ueProcessEventLiveRuntimeRegistryContext` before escalation: self-test-only or
older readiness evidence stays at hook-probe/live-hook and does not emit live
Lua dispatch. It also requires `luaObjectRegistryRuntime`,
`luaFunctionRegistryRuntime`, `luaDecodedObjectAliasesRuntime`, and
`ueObjectArrayRegistryRuntime`, plus `luaFunctionIterationRuntime`; missing or
self-test-only registry/function iteration evidence keeps the plan at
object-discovery/reflection/Lua-dispatch and is recorded in
`nextCanaryContract.registryRuntimeEvidence`. Pass
`--anchor-signatures-file <client-anchor-signatures.txt>` to feed a generated
anchor-signature sidecar into the next read-only native-client canary; the
planner emits `DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` and omits empty
`DUNE_CLIENT_PROBE_UE_ANCHORS` values. The planner does not emit live Lua dispatch
flags until the readiness report proves the persistent ProcessEvent hook and
native dispatch self-test. JSON/Markdown output includes `nextCanaryContract`,
which records the required anchor groups, currently missing groups, signature
validation status, `anchorGroupProvenance`, object-discovery coverage,
ProcessEvent runtime evidence, registry runtime evidence, and the exact env
variable names for the next canary. The contract also includes
`postCanaryVerification`, which records the native-client readiness command,
default `/tmp/dune-client-probe-loader.log` input, required sidecars, and
expected JSON coverage outputs. It also includes `strictRuntimeContract`, the
`DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true` verifier setting, gate-aware per-key
runtime and signature/anchor readiness, required runtime and signature/anchor
readiness keys, `contractReady`, `signatureAnchorReady`, and any missing keys
including `missingSignatureAnchorReadyKeys`. `targetObjectDiscovery` and
`targetHooks` are required runtime keys.
For
native Linux client logs, the planner's default loader filter accepts both
`linux-client` and the actual log label `client`. Confidence: high.
If `ueProcessEventLuaHookAliasRouting=false`, the
Lua-dispatch plan emits `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT`
from `canaryHints.ue4ssFunctionPaths` when scan evidence exposes a
UE4SS-style `/Script/...:Function` candidate. New loader builds emit that path
directly as `functionPath` and retain the older `/RuntimeProbe/...:Function`
identity as `functionRuntimePath`; the analyzer still derives the script path
for older logs. It falls back to `canaryHints.ueFunctionPaths` plus a generated
probe package when only a runtime path is available. Use
`--live-lua-alias-hook-path` for an explicit
`/Script/...:Function` target, or `--live-lua-alias-function-path` with
`--live-lua-alias-script-package` for the fallback path generator. This is
decoded owner/function identity, not full Unreal outer/package chain
reconstruction. Confidence: high.

Native Linux client logs now include `lua-object-outer-chain` for registered
objects with a non-null `OuterAddress`. The loader logs again after Lua mod
dispatch so constructed world/level/actor smoke objects prove reconstructed
outer-chain identity. `status=resolved` means every outer hop was present in the
Lua object registry; the event includes `chain`, `terminalPath`,
`terminalClass`, `reconstructedPath`, `reconstructedFullName`, and
`fullNameResolved=true`, and readiness reports the identity layer as
`luaObjectOuterChainIdentities`. Lua handles expose
`OuterChainPathName`, `OuterChainFullName`, `HasOuterChainPath`,
`GetOuterChainPathName()`, and `GetOuterChainFullName()`. Confidence: high.

The ELF xref and nearby-anchor tools are shared with the Linux server probe
path. For a native client, pass `--exe-substring DuneSandbox` so loader hits are
selected from the client process rather than the dedicated-server defaults.
Confidence: high.

`validate-elf-signatures.py` checks same-build uniqueness for Linux ELF
signature seeds. `export-elf-signature-manifest.py --format signatures` emits a
line-based file for `DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE`; its JSON output is
the cross-build manifest to revalidate after a Funcom update. Confidence: high
for the synthetic validator coverage.

`ue4ss-port-readiness.py` must report `objectDiscovery=true`,
`objectDiscoveryCoverage=true`, `findObjectSemantics=true`,
`ueObjectNativeIdentities=true`, and `ueObjectInternalFlags=true` before adding
read-only UE layout walks and treating registry-backed `FindObject`/
`StaticFindObject` semantics as live-compatible. `objectDiscoveryCoverage`
lists missing pointer/layout/UObject/FName/alias/internal-flag components, while
`findObjectSemantics` also requires object-array registry entries, native
path/name/class/address registry self-checks
(`event=lua-object-registry-check status=passed`), native object identities,
outer-chain full names, and Lua object API calls.
`reflection=true` before live property work. That
reflection gate includes `ueReflectionProbe=true` and
`ueReflectionFieldWalk=true`, `ueReflectionPropertyDescriptors=true`, and
`ueFunctionParamDescriptors=true`, `ueFunctionParamContainerChildren=true`,
`ueFunctionIdentities=true`,
`ueFunctionFlags=true`, `luaFunctionRegistryChecks=true`,
`luaFunctionRegistryRuntime=true`, and
`ueReflectionPropertyValues=true`. The function registry check is emitted as
`event=lua-function-registry-check status=passed` and proves
path/runtimePath/name/address/flags lookup consistency for a non-self-test
runtime `FindFunction()` target.
It
must report `ueProcessEventHookProbe=true`, `ueProcessEventLiveHook=true`,
`ueProcessEventHookRuntimeTarget=true`,
`ueCallFunctionHookProbe=true`, `ueCallFunctionHookRuntimeTarget=true`,
`ueCallFunctionLiveHook=true`, `ueCallFunctionLiveHookRuntimeTarget=true`,
`ueProcessEventLiveHookRuntimeTarget=true`, `ueProcessEventDispatch=true`,
`ueProcessEventLiveLuaDispatch=true`, and `ueProcessEventLiveContext=true`,
`ueProcessEventLiveFunctionPath=true`, `ueProcessEventLiveRuntimeContext=true`,
`ueProcessEventLiveRuntimeRegistryContext=true`,
`ueProcessEventLiveClassAwareParamValues=true`,
`ueProcessEventLiveParamValues=true`,
`ueProcessEventLiveRawParamValues=true`,
`ueProcessEventLiveArrayContainerParamValues=true`,
`ueProcessEventLiveSetContainerParamValues=true`,
`ueProcessEventLiveMapContainerParamValues=true`,
`ueProcessEventLiveSetMapContainerParamValues=true`,
`ueProcessEventContainerAliasMethods=true`,
`ueProcessEventLuaContextHandles=true`,
`ueProcessEventLuaParamAccessors=true`,
`ueProcessEventLuaScalarParamAccessors=true`,
`ueProcessEventLuaNameStringParamAccessors=true`,
`ueProcessEventLuaStructParamAccessors=true`,
`ueProcessEventLuaEnumParamAccessors=true`,
`ueProcessEventLuaObjectParamAccessors=true`,
`ueProcessEventLuaBoolParamAccessors=true`, and
`ueProcessEventLuaHookRouting=true` plus
`ueProcessEventLuaHookAliasRouting=true` before routing real ProcessEvent calls
into Lua/mod callbacks, and `luaDispatch=true`, `luaObjectApi=true`,
`luaSchedulerApiMods=true`,
`luaInputCommandApiMods=true`,
`luaProcessConsoleExecHooks=true`, `luaLocalPlayerExecHooks=true`,
`luaCallFunctionHooks=true`, `luaCallFunctionStructuredArgs=true`,
`luaLifecycleHooks=true`,
`luaCustomEventHooks=true`, `luaLoadMapHooks=true`,
`luaBeginPlayHooks=true`, `luaInitGameStateHooks=true`,
`luaObjectNotify=true`, `luaSyntheticOuter=true`,
`luaDecodedObjectAliases=true`, `luaReflection=true`,
`luaReflectionNumericPropertyValues=true`,
`luaReflectionNameTextPropertyValues=true`,
`luaReflectionArrayInnerProperty=true`, `luaReflectionEnumProperty=true`,
`luaReflectionContainerProperties=true`, `luaReflectionImportText=true`,
`luaReflectionExportText=true`, `luaReflectionPropertyMetadata=true`,
`luaReflectionDescriptorValues=true`, and
`luaProcessEvent=true` before exposing UE4SS Lua APIs to live game objects.
`luaLoadAssetPackage=true` is intentionally tracked as a separate completion
gate: it requires a loaded Lua mod to prove `LoadAsset` resolved through a real
package/asset backend instead of the loader's object registry.
The stricter `ue4ssLuaApiComplete` readiness aggregate remains false until that
gate and staged `luaDispatch` both pass.
Full completion requires `liveTargetImageCanaryContract.ready=true` as well,
with the `targetImageAnchors`, `runtimePackageLoading`,
`runtimeObjectRegistry`, `runtimeReflection`,
`runtimeProcessEventDispatch`, and `runtimeCallFunctionDispatch` groups all
ready; self-test-only logs are not enough.
`runtimeProcessEventDispatch` requires more than a live hook install: decoded
live function path, runtime registry context, active params, raw/container
param samples, Lua context handles, descriptor-backed param accessors, typed
scalar/name/string/struct/enum/object/bool accessor coverage, container
alias/layout methods, and hook routing/alias routing must all be present.
In short: container alias/layout methods are required, not optional.
The decoded live function path is a required readiness marker.
`luaReflectionDescriptorValues=true` now requires descriptor `GetValue()` /
`SetValue()` and shorthand `get()` / `set()` on loader-owned property handles.
Confidence: high.

## UE4SS-Port Roadmap

The next client work is the same runtime spine needed on the server side:

1. Identify Unreal global surfaces in the actual process: `FNamePool`,
   `GUObjectArray`, `GWorld`/`GEngine`, `ProcessEvent`, and relevant class/property
   layout anchors.
2. Validate read-only FName, object-array, UObject, GWorld, and GEngine readers against
   those anchors.
3. Run the guarded ProcessEvent target hook probe after read-only discovery is
   stable.
4. Install the persistent ProcessEvent hook scaffold after the probe passes.
5. Use the native ProcessEvent dispatch registry to prove pre/original/post
   ordering.
6. Use the live ProcessEvent Lua bridge to route `RegisterHook` callbacks with
   resolved `Object`/`Function` handles and a `Params` context table.
7. Prove Lua `GetFunctionParamDescriptors`/`GetFunctionParams` plus
   descriptor-handle `GetParamDescriptor` and `GetParamValue`/`SetParamValue`
   access from ProcessEvent callbacks.
8. Prove descriptor-backed params-buffer construction with
   `CreateProcessEventParams(function)` on every target, then reuse that buffer
   builder for guarded non-self-test ProcessEvent invocation. Current builds
   expose the no-call `descriptor-preflight-ready` state and disabled-by-default
   `{Invoke=true}` gate; when the target-specific opt-in env is set, that path
   now seeds descriptor-backed params and calls the original trampoline.
9. Prove, on a live canary, that `ctx.Function` from a real ProcessEvent call
   hits the promoted `ue-function-param` registry and that guarded class-aware
   `GetParamValue` works on the active params pointer.
10. Replace the current bounded `Reflection():GetProperty` descriptor shim with
   live UE property traversal and argument marshaling.
11. Replace loader-owned `StaticConstructObject`/`NotifyOnNewObject` with
   guarded live construction and object notification only after class lookup,
   outer/name construction, and cleanup are proven.
12. Broaden the Lua/mod dispatch layer to the subset of UE4SS mods we actually
   need.

Server-authoritative gameplay still has to land on the server. Client-side
hooks can expose UI/console surfaces and help with discovery, but they do not
make BRT placement, inventory grants, map state, or other authoritative changes
valid unless the server path accepts them.
