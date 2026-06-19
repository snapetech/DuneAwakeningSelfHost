# Linux Server Loader Canary - 2026-06-16

## Outcome

Live canary target: `kspls0`, `testing-waterfat`, partition `7`.

Both the preload canary restart and cleanup restart were gated on
`connected_players=0`. The final state after cleanup was:

- `DUNE_ENABLE_LINUX_SERVER_PRELOAD=false`
- no partition-7 preload process
- partition 7 ready/alive/active with `connected_players=0`
- farm health `31/31`
- `dune-map-watchdog.service` active
- `/tmp/dune-map-watchdog.paused` absent

Raw log on `kspls0`:

```text
backups/canary-linux-loader/20260616T172946Z/testing-waterfat-loader-v2.log
```

Summarize it with:

```bash
scripts/summarize-linux-loader-scan.py \
  backups/canary-linux-loader/20260616T172946Z/testing-waterfat-loader-v2.log
```

Generate code-reference triage with a copied server binary:

```bash
make summarize-linux-loader-xrefs \
  SERVER_BINARY=/tmp/dune-server-bin-1988751 \
  LOADER_SCAN_LOG=backups/canary-linux-loader/20260616T172946Z/testing-waterfat-loader-v2.log \
  CATEGORY=brt
```

## Scan Summary

The useful server process was PID `100`:

```text
DuneSandboxServer-Linux-Shipping
```

Summary:

- hit count: `139`
- unique names: `39`
- mapped regions: `54`
- scanned regions: `3`
- filtered regions: `50`
- unreadable regions: `1`
- size-skipped regions: `0`

The first failed canary skipped the main server mapping because the cap was
`256 MiB`; the current server executable text mapping is about `342 MiB`.
The scan cap is now `512 MiB`.

## High-Value Anchors

Building and piece-count surfaces:

- `m_MaxNumLandclaimSegments`: `0x5b929bb`
- `m_MaxLandclaimSegmentsPerMap`: `0x59afced`, `0x5ad7346`
- `Fail_ReachedBuildableStructureLimitInServer`: `0x59e5f85`
- `Fail_ReachedBuildableStructureComposedLimitInServer`: `0x5945416`
- `Fail_ReachedBuildableStructureLimitInMap`: `0x5a3508d`
- `Fail_ReachedBuildableStructureComposedLimitInMap`: `0x597a3ae`
- `BuildingSystemActionSpawnBuildable.cpp`: `0x59e9866`
- `InsideLandclaimCanBePlaced.cpp`: `0x5b47537`

BRT and Deep Desert placement surfaces:

- `m_BaseBackupToolMapRestriction`: `0x5b5e1ec`
- `ServerRequestBaseBackup`: `0x5a553f9`, `0x61a011b`, `0x61a026a`, `0x61a03c0`
- `UGameItemBaseBackupToolActions`: `0xae15cb`, `0xae4c48`, `0xae5166`, `0x635b8f7`
- `BaseBackupActionPlace`: `0x9227c7`, `0x9227e4`, `0x922d3c`, `0x922d59`
- `PerformCanBePlaced`: `0x59e9a91`, `0x5a02e85`, `0x5a55079`, `0x5a89ddd`
- `BuildableMapRegion`: `0x81656a`, `0x816e46`, `0x817e49`, `0x817e8c`
- `Fail_InvalidMap`: `0x5994df9`
- `brt-action-guard`: `0xe04ed15`

Deep Desert state surfaces:

- `DeepDesert`: `0x59b08e1`, `0x5abab66`, `0x5b2d2f3`, `0x5c003d5`
- `m_DeepDesertGameplay`: `0x59b08df`
- `m_ShiftingSands`: `0x5c4965e`
- `m_PerMapSystemSettings`: `0x5a5c56f`, `0x5c6f970`
- `m_SpiceFieldTypeSettings`: `0x5b19814`, `0x5c39777`
- `MaxGloballyPrimed`: `0x5a90b98`, `0x5ac1149`, `0x5c8807f`
- `MaxGloballyActive`: `0x5a03f43`, `0x5c02a3d`, `0x5c8a4f2`

GM/CheatManager-adjacent surfaces:

- `PrintAllowedCommands`: `0x5a1f2b7`
- `PrintPos`: `0x5c83d55`
- `ServerCommand`: `0x9b26d7`, `0x9b26fd`, `0x9b271f`, `0x9b2754`
- `ServiceBroadcast`: `0x5a20069`, `0x5c4e5af`
- `UDuneServerCommandSubsystem`: `0x9b26f8`, `0x9b27b5`, `0x9b39c2`, `0x9b3ce9`
- `CheatManager`: `0x59e1cd`, `0x59e1e4`, `0x59e39a`, `0x59e442`
- `CheatClass`: `0x59f6a1d`
- `AdminLogin`: `0x8360ee`, `0x83693c`, `0x836978`, `0x9709db`

## Static Xref Triage

The xref helper scans simple x86-64 relative branches and RIP-relative memory
references in executable `LOAD` segments. A zero-xref result does not rule out a
surface; many UE names are reached through reflection metadata, generated
registries, or data tables rather than direct string loads.

Focused report results against `/tmp/dune-server-bin-1988751`:

- BRT: `32` targets, `6` with simple xrefs. All useful simple xrefs were
  `PerformCanBePlaced` strings.
- Building: `32` targets, `0` with simple xrefs. Treat these as reflected-name
  anchors for Ghidra metadata/class passes, not immediate patch sites.
- Deep Desert: `17` targets, `0` with simple xrefs. Treat these as config/state
  name anchors for metadata/data-table passes.
- GM: `20` targets, `1` with simple xrefs: `ServiceBroadcast` at `0x5c4e5af`
  referenced from `0xd96c103`.
- Cheat: `19` targets, `0` with simple xrefs. The upstream
  CheatManager-enabler idea still needs a real server-side UE object/function
  path, not only these strings.

Highest-value BRT code-name xrefs:

- `PerformCanBePlaced` at `0x59e9a91`: xrefs include `0xcfbaf72`,
  `0xcfbb249`, `0xcfc55bf`, `0xcfc5abe`.
- `PerformCanBePlaced` at `0x5a02e85`: xrefs include `0xcfbd12e`,
  `0xcfbd1dc`, `0xcfbd337`, `0xcfbd7ff`.
- `PerformCanBePlaced` at `0x5a55079`: xrefs include `0xcfbbffd`,
  `0xcfbc416`, `0xcfccae2`, `0xcfccc2c`.
- `PerformCanBePlaced` at `0x5a89ddd`: xrefs include `0xcfbc945`,
  `0xcfbcc2f`, `0xcfcd71a`, `0xcfcdaf9`.

The `brt-action-guard` signature remains a direct code-pattern anchor at
`0xe04ed15`. The nearby branch shape is:

```text
0xe04ed15: test rax,rax
0xe04ed18: je   0xe04ed24
0xe04ed1a: mov  r14b,0x1
0xe04ed1d: cmp  byte ptr [r15+0x55],0x1
0xe04ed22: jne  0xe04ed27
0xe04ed24: xor  r14d,r14d
```

## Next Use

Use these offsets as stable inputs for Ghidra cross-reference passes and focused
runtime traces. They are evidence for where to look, not patch targets by
themselves. Runtime writes still need a separate guarded patch design and a
zero-player canary.

## Current Loader Delta

After this canary, the Linux server loader gained the same read-only UE probe
surface used by the native Linux and Windows/Proton client loaders:

- explicit `DUNE_PROBE_LOADER_UE_ANCHORS` validation
- pointer and layout probes
- UObject-shaped candidate reads
- bounded chunked object-array walks
- bounded FName decoding
- Lua object-handle registration for UE candidates, including decoded
  `/RuntimeProbe/<DecodedName>` aliases when FName decoding succeeds
- Lua object-registry APIs: `FindObject`, `GetKnownObjects`, `FindObjects`,
  `FindAllOf`, `ForEachUObject`, `IsA`, and registry-backed `LoadAsset`
- signature-resolved UE anchors through
  `DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES` and
  `DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE`
- guarded ProcessEvent target hookability probes through
  `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE`
- persistent ProcessEvent hook scaffolding through
  `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK`
- native ProcessEvent pre/original/post dispatch self-test through
  `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST`
- live ProcessEvent-to-Lua callback routing through
  `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH`
- read-only function param descriptor discovery through
  `event=ue-function-param-root` and `event=ue-function-param` when the
  reflection property probe walks bounded `functionLink` candidates; readable
  descriptors are promoted into the live `GetFunctionParamDescriptors`/
  `GetFunctionParams` registry by function address, including decoded
  `functionName`/`functionPath` runtime identities and decoded
  `fieldClassName`/`ClassName` when FName/class reads are available
- guarded Lua ProcessEvent params get/set coverage through
  `GetFunctionParamDescriptors`/`GetFunctionParams`, descriptor-handle
  `GetParamDescriptor`, `GetParamValue`, and `SetParamValue` on the active
  loader-owned params block, with scalar, bool, and object-pointer descriptor
  handling

The historical log above predates those UE probe events. The next one-map
server canary should reuse the scan/xref outputs here to fill
`DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE` first, promote unique runtime
matches into UE anchors, enable only the read-only UE probes needed for the
target anchor group, and leave the ProcessEvent hook probe in dry-run mode
until the resolved target is mapped and executable. A later zero-player canary
can set `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=true` to install and
immediately restore the live target hook. Only after that passes should a
separate zero-player canary set
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK=true`; that scaffold leaves the
hook active until unload, forwards to the original function, and restores on
loader unload. In lab/smoke runs,
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true` arms native
pre/post callbacks around the original function. A later Lua-canary can also
set `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=true` after the
native dispatch path passes; that routes `RegisterHook` pre/post callbacks from
the persistent hook and passes raw `object`, `function`, and `params` addresses
  to Lua. The callback can also receive `Object`/`Function` handles and a `Params`
  context table. `GetFunctionParamDescriptors(ctx.Function)` now returns promoted
  live descriptors when the function address matches a scanned
  `UFunction`; `FindFunction`, `FindFirstFunction`, and `GetKnownFunctions`
  expose those promoted runtime UFunction handles to Lua mods by runtime
  `PathName`. `RegisterHook` returns UE4SS-shaped `preId, postId` values and
  `UnregisterHook` removes registered pairs. Hook routing matches exact paths
  first and then falls back to terminal function-name aliases; canary logs
  report `pathExactMatches` and `pathAliasMatches`. `GetKnownObjects`, `FindObjects`, `FindAllOf`, and
  `ForEachUObject` expose the current loader object registry by runtime
  `PathName`; `LoadAsset` resolves only already-registered handles. Mods can
  query `GetLoadAssetPackageBridgeState()` to refresh package anchors and report
  the selected `StaticLoadObject`/`LoadObject`/`LoadPackage` target,
  mapped/readable/executable status, `InvokeEnabled`, `AbiVerified=false`, and
  `NativeBridgeArmed=false`; readiness reports that as
  `luaLoadAssetPackageBridgeState`. Mods can call
  `GetLoadAssetPackageAbiState()` to report the selected package-loading
  target's Linux `sysv-x86_64` ABI contract, `SignatureFamily`,
  `RequiredSignature`, and still-false `AbiVerified`, `CallFrameReady`,
  `StringBridgeReady`, `ClassRootReady`, and `OuterReady` gates. Readiness
  reports that as `luaLoadAssetPackageAbiState`, not `luaLoadAssetPackage`.
  `PrepareLoadAssetPackageStringBridge(path)` stages bounded UTF-8 path input
  for the package string bridge without constructing a UE `TCHAR` buffer and
  reports `StringInputStaged=true`, `BoundedInput=true`,
  `TCharEncoding=unverified-live-build`, `TCharBridgeReady=false`,
  `NativeBufferReady=false`, and `NativeInvoked=false`; readiness reports that
  as `luaLoadAssetPackageStringBridge`, not `luaLoadAssetPackage`.
  `PrepareLoadAssetPackageNativeBuffer(path)` stages a bounded,
  NUL-terminated UTF-8 native input buffer descriptor and reports
  `Utf8BufferReady=true`, `NativeInputBufferReady=true`, `BufferBytes`,
  `NullTerminated=true`, `TCharBufferReady=false`, `CallFrameReady=false`, and
  `NativeInvoked=false`; readiness reports that as
  `luaLoadAssetPackageNativeBuffer`, not `luaLoadAssetPackage`.
  `PrepareLoadAssetPackageTCharBuffer(path)` reports the Linux candidate
  `TCHAR` layout using `CandidateEncoding=host-wchar-unverified`,
  host `CandidateUnitBytes`, and `CandidateBufferBytes`, while keeping
  `TCharLayoutVerified=false`, `TCharBufferReady=false`,
  `CallFrameReady=false`, and `NativeInvoked=false`; readiness reports that as
  `luaLoadAssetPackageTCharBuffer`, not `luaLoadAssetPackage`.
  `GetLoadAssetPackageTCharVerificationState()` is the Linux server evidence
  gate. It reads `DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES`,
  `DUNE_PROBE_LOADER_TCHAR_EVIDENCE`, and
  `DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT`, and reports
  `TCharLayoutVerified=false`/`TCharBufferReady=false` until explicit evidence,
  confirmation, and a resolved package anchor line up. Readiness reports this
  as `luaLoadAssetPackageTCharVerification`, not `luaLoadAssetPackage`.
  `GetLoadAssetPackageCallFrameVerificationState(path)` combines path staging,
  package ABI evidence from `DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE`
  plus `DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI`, and verified
  `TCHAR` layout evidence before reporting `CallFrameReady=true`. Default
  canary status is `abi-evidence-missing` with `AbiVerified=false`,
  `CallFrameReady=false`, and `NativeInvoked=false`; readiness reports this as
  `luaLoadAssetPackageCallFrameVerification`, not `luaLoadAssetPackage`.
  `PrepareLoadAssetPackageCallFrame(path)` stages the Lua path into a
  non-invoking package-call descriptor and reports `PathStaged=true`,
  `ArgumentDescriptorReady=true`, `TCharBridgeReady=false`,
  `CallFrameReady=false`, and `NativeInvoked=false`; readiness reports that as
  `luaLoadAssetPackageCallFrame`, not `luaLoadAssetPackage`.
  Mods can call
  `InvokeLoadAssetPackageNative(path, {Invoke=true})` to exercise the guarded
  native-invocation checkpoint; it logs
  `event=lua-load-asset-package-native-invoke`, counts
  `loadAssetPackageNativeCalls`/`loadAssetPackageNativeGateHits`, and returns
  `Invoked=false`, `InvokeRequested`, `InvokeEnabled`, `AbiVerified`,
  `TCharLayoutVerified`, `CallFrameReady`, and `NativeBridgeArmed`.
  `NativeBridgeArmed` only becomes true after the package ABI and `TCHAR`
  evidence gates pass and `DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE`
  is enabled; this checkpoint still does not call UE.
  Readiness reports that as `luaLoadAssetPackageNativeInvoke`, not
  `luaLoadAssetPackage`.
  `GetLoadAssetPackageNativeCallAdapterState(path)` exposes the SysV x86_64
  package-load adapter selected for the future native call and reports
  `FunctionPointerReady`, `CallFrameReady`, `NativeBridgeArmed`,
  `AdapterReady`, `FinalInvokeConfirmed=false`, `CrashGuardRequired=true`,
  `CrashGuardArmed=false`, `ReturnValidationReady=true`,
  `NativeCallable=false`, and `NativeInvoked=false`; readiness reports this as
  `luaLoadAssetPackageNativeCallAdapter`, not `luaLoadAssetPackage`. Mods can
  request the guarded package path with `LoadAsset(path, {Backend="package"})`,
  `{Package=true}`, or `{TryPackage=true}`, and
  `DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN=1` sends unknown registry
  assets through the same preflight. That logs
  `event=lua-load-asset-package-preflight status=native-bridge-missing`, counts
  `loadAssetPackagePreflightCalls` and `loadAssetPackageGateHits`, and still
  returns `nil`; readiness reports this as `luaLoadAssetPackagePreflight`, not
  `luaLoadAssetPackage`. This is still bounded registry enumeration, not full
  `GUObjectArray` enumeration or package loading. `NotifyOnNewObject` stores up
  to 32 class/path/name filter
  registrations and dispatches every match only when loader-owned
  `StaticConstructObject` creates a matching synthetic handle; it is not a live
  Unreal construction hook yet. Returned
  handles expose the same UE4SS-style method surface
  as the client loaders (`GetFullName`, `GetName`, `GetPathName`,
  `GetAddress`, `IsValid`, `GetClass`, `GetOuter`, `GetWorld`, `GetFName`,
  `type`, `IsClass`, `IsAnyClass`, `IsA`, flag checks, property helpers, and
  `CallFunction`, plus `ProcessConsoleExec`, UFunction flag, UStruct
  iteration/super, UClass CDO/child, and actor level method stubs), with
  synthetic class handles, loader-owned `GetOuter` for synthetic constructed
  handles, and nil/false/zero returns until live UObject layout fields are
  promoted. The server loader also exposes the same
  deterministic `FName`/`FText`, immediate async/delay/loop, keybind, console,
  global-console, custom-event, custom-property, local-player exec, game
  directory, UE4SS metadata, flag/property/key constant, and lifecycle
  registration shims as the client loaders; those allocate ids or run callbacks
  immediately until real engine callsites are resolved and hooked. `FName`
  values expose `ToString()` and `GetComparisonIndex()` methods. `Reflection()`
  returns a loader-owned `UObjectReflection` table for known handles, and
  `Reflection():GetProperty(name)` resolves self-test properties, promoted
  `UFunction` param descriptors, and scalar live reflection candidates into
  UE4SS-style property descriptor tables. Descriptor methods include
  `GetFullName`, `GetFName`, `IsA`, `GetClass`, `ContainerPtrToValuePtr`,
  `ImportText`, `GetPropertyClass`, bool mask helpers, `GetStruct`, `GetInner`,
  and `type`; `ForEachProperty` iterates the same known descriptor sets.
  `ForEachFunction` iterates unique promoted `UFunction` handles for
  loader-owned self-test object/class handles through the same bounded registry
  as `GetKnownFunctions`. This is a bounded descriptor/function shim, not
  complete live `FProperty` or `UStruct` traversal. No-hook Lua mod scripts now
  pass like the client loaders, and
  script failures log a sanitized `error=` field on `event=lua-mod-script`. The
  default self-test proves guarded `GetParamValue` and
  `SetParamValue` access against descriptor handles for loader-owned `Value`,
  `OriginalResult`, and `Touched` fields. The descriptor accessor now handles
  scalar, bool, and object-pointer params by class metadata, but still does not
  marshal full live `FProperty` payloads such as strings, names, arrays, or
  structs. Collect
`/tmp/dune-server-probe-loader.log`, then turn the probes back off. Confidence:
high for self-test coverage, moderate until validated against live server
anchors.

Export a second-pass env file from a future server scan log with:

```bash
scripts/export-ue-anchor-env.py /tmp/dune-server-probe-loader.log \
  --loader server \
  --platform server \
  --format env > ue-server-anchors.env
```
