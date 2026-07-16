# Client Loader Support Matrix

Status on 2026-06-16: native Linux ELF and Windows/Proton client probe support
are both scaffolded and smoke-tested as read-only runtime probes, with an
additional opt-in loader-owned hook dispatch self-test. Confidence: high.

Observed on 2026-06-16: the staged Windows `version.dll` loaded inside the real
Proton client process
`DuneSandbox-Win64-Shipping.exe` and logged module images to
`/tmp/dune-win-client-probe-loader.log`. That launch did not inherit scan
environment, so it recorded `0` scan starts. The Windows sidecar fallback was
added after that observation; the next normal Steam launch with the staged
`dune-win-client-probe.env` should scan without requiring launch environment
inheritance. Confidence: high for load, moderate until the next real scan log.

Follow-up on 2026-06-16: a later Steam launch started
`DuneSandbox-Win64-Shipping.exe`, but process maps showed Proton's builtin
`version.dll` was loaded instead of the staged game-directory proxy. For that
case use `scripts/proton-dll-override-control.sh --set` to write a per-app
`version=native,builtin` Wine override before the next client restart.
Confidence: high.

Final client canary on 2026-06-16: after setting the per-app Wine DLL override,
the real Proton client loaded the staged `VERSION.dll`, read
`dune-win-client-probe.env`, and completed a full preset scan with
`strings=45`. See `docs/windows-client-loader-canary-2026-06-16.md`.
Confidence: high.

This is not UE4SS yet. Both client paths are loader/probe foundations for
runtime discovery with loader-owned hook, Lua dispatch, reflection, and
ProcessEvent-shaped self-tests. They now marshal a bounded live descriptor
`GetValue()` subset when the promoted `FProperty` class and size are known, but
they do not yet provide complete live `FProperty` marshaling, arbitrary
container/struct/string storage marshaling, or patch game memory. The
persistent parity smokes also seed a loader-owned
`/RuntimeProbe/RuntimeProbeObject` to prove non-`SelfTest*` runtime descriptor
enumeration, typed `GetValue()`, typed `SetValue()`, and owner-mode
`ForEachFunction` plus its registry-check event across Linux client, Linux
server, and Proton/Windows. They also seed a UE-shaped
`/RuntimeProbe/RuntimeProbeUObject` with a non-`SelfTest*` class so the normal
`source=ue-uobject` scanner path can produce
`registryProvenance=runtime` object-registry evidence. That closes
`luaObjectRegistryRuntime` in local parity smokes without loosening the
readiness gate; it is runtime-provenance hardening, not proof of live Dune
`FProperty` offsets. The
persistent ProcessEvent hook
scaffold exists, but it currently only validates install/restore, logs bounded
calls when requested, and forwards to the original function. Confidence: high.

## Target Selection

Use the loader that matches the process format:

| Client process | Loader artifact | Launch path | File mutation |
| --- | --- | --- | --- |
| Native Linux ELF | `libdune_client_probe_loader.so` | `LD_PRELOAD` through `scripts/launch-linux-client-probe.sh` | None |
| Windows PE under Proton/Wine | `dune_win_client_probe_loader.dll` staged as `version.dll` | `scripts/launch-proton-client-probe.sh --stage-to-game-dir -- %command%` | Adds/removes `version.dll` beside the game exe with manifest tracking |

Do not use the Linux `.so` for a Proton client. It cannot load into a Windows PE
process. Do not use the Windows DLL for a native Linux ELF client.

The installed Dune client on this host is Windows PE:

```text
~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe
```

The shipping executable imports `VERSION.dll`, including
`GetFileVersionInfoSizeW`, `GetFileVersionInfoW`, and `VerQueryValueW`, so the
`version.dll` proxy is a real Proton load point. Confidence: high.

## Parity

Both client loaders now provide:

| Capability | Linux ELF | Windows/Proton |
| --- | --- | --- |
| Read-only process load proof | Constructor log | `DllMain` worker-thread log |
| Module/image logging | `DUNE_CLIENT_PROBE_LOG_MODULES=true` | `DUNE_WIN_CLIENT_PROBE_LOG_MODULES=true` |
| String scan | `DUNE_CLIENT_PROBE_SCAN_STRINGS` | `DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS` |
| Byte signature scan | `DUNE_CLIENT_PROBE_SCAN_SIGNATURES` | `DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES` |
| Signature file scan | `DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE` | `DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE` |
| Explicit UE anchor validation | `DUNE_CLIENT_PROBE_UE_ANCHORS` | `DUNE_WIN_CLIENT_PROBE_UE_ANCHORS` |
| Signature-resolved UE anchors | `DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES`, `DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` | `DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES`, `DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` |
| Runtime candidate globals by image offset/RVA | `DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS` | `DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS` |
| Runtime root auto-discovery | `DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS` | `DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS` |
| Delayed UE root probe | `DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS` | `DUNE_WIN_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS` |
| Read-only UE pointer probe | `DUNE_CLIENT_PROBE_UE_POINTER_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE` |
| Read-only UE layout probe | `DUNE_CLIENT_PROBE_UE_LAYOUT_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE` |
| Read-only UObject candidate probe | `DUNE_CLIENT_PROBE_UE_UOBJECT_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE` |
| Read-only UE reflection probe | `DUNE_CLIENT_PROBE_UE_REFLECTION_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE` |
| Bounded UE reflection field walk | `DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK` | `DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK` |
| Bounded FProperty descriptor probe | `DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE` |
| Bounded container child property scan | `DUNE_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_START`/`END` | `DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_CONTAINER_CHILD_SCAN_START`/`END` |
| Bounded reflected property value probe | `DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE` |
| Bounded object-array walk | `DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE` |
| Bounded object-array class reflection | `DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE` |
| Bounded ProcessEvent vtable candidate scan | `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN` | `DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN` |
| Bounded FName decoder | `DUNE_CLIENT_PROBE_UE_FNAME_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE` |
| Strict-gated FName recovery | `DUNE_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE` | `DUNE_WIN_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE` |
| Bounded FName decode diagnostics | `DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS` | `DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS` |
| Guarded hook dispatch self-test | `DUNE_CLIENT_PROBE_HOOK_SELF_TEST` | `DUNE_WIN_CLIENT_PROBE_HOOK_SELF_TEST` |
| Guarded ProcessEvent target hook probe | `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE` |
| Guarded CallFunctionByNameWithArguments hook probe | `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE` | `DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE` |
| Persistent ProcessEvent hook scaffold | `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK` | `DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK` |
| Persistent CallFunctionByNameWithArguments hook scaffold | `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK` | `DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK` |
| Live ProcessEvent Lua callback bridge | `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH` | `DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH` |
| Guarded Lua-to-native ProcessEvent invoke self-test | `InvokeProcessEventNative` after `NativeBridgeArmed=true` | `InvokeProcessEventNative` after `NativeBridgeArmed=true` |
| Live CallFunctionByNameWithArguments Lua callback bridge | `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH` | `DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH` |
| Guarded Lua-to-native CallFunction invoke self-test | `InvokeCallFunctionNative` after `CallFunctionLiveHook` | `InvokeCallFunctionNative` after `CallFunctionLiveHook` |
| Native mod dispatch self-test | `DUNE_CLIENT_PROBE_MOD_SELF_TEST` | `DUNE_WIN_CLIENT_PROBE_MOD_SELF_TEST` |
| Lua runtime execution self-test | `DUNE_CLIENT_PROBE_LUA_SELF_TEST`, `DUNE_CLIENT_PROBE_LUA_LIBRARY` | `DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST`, `DUNE_WIN_CLIENT_PROBE_LUA_DLL` |
| Typed Lua reflection/property self-test | `DUNE_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST` | `DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST` |
| Lua ProcessEvent-shaped hook self-test | `DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST` | `DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST` |
| Lua mod entrypoints | `DUNE_CLIENT_PROBE_LUA_MODS_ENABLED`, `DUNE_CLIENT_PROBE_LUA_MOD_ROOT` | `DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED`, `DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT` |
| Post-canary xref/anchor/outcome analysis | `summarize-linux-loader-xrefs.py`, `summarize-linux-loader-anchors.py`, `summarize-ue-candidate-outcomes.py`, `summarize-ue-candidate-shapes.py`, `summarize-ue-vtable-candidates.py` | `summarize-client-loader-xrefs.py`, `summarize-ue-candidate-outcomes.py`, `summarize-ue-candidate-shapes.py`, `summarize-ue-vtable-candidates.py` |
| Built-in presets | `core,ue,client,cheat,brt,deep-desert` | `core,ue,client,cheat,brt,deep-desert` |
| Hit coordinates | runtime address, image offset, file offset | runtime address, module RVA, region base |
| Scan size guard | `DUNE_CLIENT_PROBE_SCAN_MAX_MAPPING_BYTES` | `DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES` |
| Hit-count guard | `DUNE_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE` | `DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE` |
| Path filters | `DUNE_CLIENT_PROBE_SCAN_PATH_FILTER` | `DUNE_WIN_CLIENT_PROBE_SCAN_PATH_FILTER` |
| Launch-env fallback | not needed for `LD_PRELOAD` | `dune-win-client-probe.env` sidecar beside proxy DLL |
| Proton builtin override | not applicable | `scripts/proton-dll-override-control.sh --set` |
| Read-only default | yes | yes, `MEM_IMAGE` only |
| Smoke script | `scripts/smoke-linux-client-loader.sh` | `scripts/smoke-windows-client-loader.sh` |
| Real Lua runtime smoke | included in default smoke through `liblua5.4.so` | `make smoke-windows-client-loader-lua` stages pinned LuaBinaries 5.4.8 when no DLL is set and also enables read-only discovery/hook-probe gates |
| Package native-call preflight | `scripts/smoke-linux-client-loader-package-preflight.sh` | `scripts/smoke-windows-client-loader-package-preflight.sh` |
| Full local parity smoke | `make smoke-linux-client-loader && make smoke-linux-client-loader-package-preflight` | `make smoke-windows-client-loader-full` |
| Package script | `scripts/package-linux-client-loader.sh` | `scripts/package-windows-client-loader.sh` |

When the bounded ProcessEvent vtable scan is enabled, both client paths must
run `scripts/summarize-ue-vtable-candidates.py <loader.log> --format json` and
use only its ranked `hookProbeShortlist` for the next guarded hookability probe.
Raw `ue-process-event-vtable-candidate` rows are target evidence, not hook or
dispatch proof.
`scripts/verify-client-probe-canary.sh` now performs that ranking automatically
for captured client logs and writes `ue-vtable-candidates.json`,
`ue-vtable-candidates.md`, `next-canary-plan.json`, `next-canary-plan.env`, and
`next-canary-plan.md` into the evidence directory. Confidence: high.

The `ue` scan preset is intentionally identical across native Linux and
Windows/Proton. It now includes root aliases (`GUObjectArray`, `GObjectArray`,
`GObjects`, `FUObjectArray`, `FNamePool`, `NamePoolData`, `GName`, `GNames`,
`GWorld`/`GEngine`), dispatch candidates (`ProcessEvent`, `StaticFindObject`,
`CallFunctionByNameWithArguments`, `CallFunctionByName`), package-loading
surfaces (`StaticLoadObject`, `StaticLoadClass`, `LoadObject`, `LoadPackage`, `ResolveName`), and
reflection names (`UObject`, `UClass`, `UFunction`, `FProperty`, `UStruct`,
`UEnum`). This only improves read-only evidence capture; scan hits are still
not promoted to live hook or Lua dispatch proof without target-image anchor
validation. Confidence: high.
The same aliases are now classified by `ue_anchor_group_for_name()` in the
Linux server, native Linux client, and Windows/Proton loaders, and by
`export-ue-candidate-globals.py` when it emits root-recovery candidate globals.
That keeps grouped runtime logs and generated canary env files aligned with the
widened scan preset. Confidence: high.
The signature/xref promotion path, explicit anchor env exporter, canary prep,
root-recovery exporter, and canary planner now use the same alias-expanded
contract. This prevents `NamePoolData`, `GNames`, `GObjects`, `FUObjectArray`,
`CallFunctionByName`, `UStruct`, or `UEnum` evidence from being downgraded to
`unknown` or dropped before validation. Confidence: high.

The Windows path has an extra proxy-forwarding smoke because it must preserve
the `version.dll` API surface expected by the game. The Linux path has no
equivalent forwarding layer because `LD_PRELOAD` does not replace a game DLL.

`InvokeProcessEventNative(object, function, {Value=n})` is present on native
Linux and Proton/Windows. It now separates registry readiness from execution
readiness: `ObjectAllowed` requires a registered object address,
`FunctionAllowed` requires promoted `UFunction` descriptor evidence, and
`SelfTestCallable` is only true for the loader-owned self-test object/function
that can safely run through the current trampoline after
`GetProcessEventBridgeState().NativeBridgeArmed` is true. Passing smokes emit
`event=lua-process-event-native-invoke-self-test status=passed` with
`ObjectRegistryAllowed=true`, `FunctionDescriptorAllowed=true`,
`SelfTestCallable=true`, `processEventNativeCalls=2`, and
`processEventNativeHits=2`. The second call is the non-self-test preflight
attempt. The full local smokes also enable the target-specific opt-in and prove
a third `status=non-self-test-invoked` row, which raises
`luaProcessEventNativeInvokeNonSelfTestInvoked=true`. This is a Lua-to-native
trampoline proof plus registry/descriptors gating, not arbitrary target-image
UE ProcessEvent execution.
`InvokeCallFunctionNative(object, functionName, args, options)` is now present
on native Linux, Proton/Windows, and the Linux dedicated server loader. The
self-test path proves loaded-mod Lua can drive the armed
`CallFunctionByNameWithArguments` trampoline and return `Result=42` through the
original-call path. Non-self-test object calls report `preflight-ready` by
default, and `{Invoke=true}` stays closed as `non-self-test-invoke-disabled`
unless the target-specific opt-in env is set:
`DUNE_CLIENT_PROBE_ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE`,
`DUNE_WIN_CLIENT_PROBE_ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE`, or
`DUNE_SERVER_PROBE_ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE`. Summaries expose
`luaCallFunctionNativeInvokeSelfTestCount`,
`luaCallFunctionNativeInvokePreflightCount`, and
`luaCallFunctionNativeInvokeNonSelfTestGateCount`; actual enabled calls also
increment `luaCallFunctionNativeInvokeNonSelfTestInvokedCount`. Readiness
reports these as
`luaCallFunctionNativeInvoke`, `luaCallFunctionNativeInvokePreflight`, and
`luaCallFunctionNativeInvokeNonSelfTestGate`, and requires
`luaCallFunctionNativeInvokeNonSelfTestInvoked` for aggregate Lua dispatch.
`GetCallFunctionNativeExecutorState(object, functionName, args, options)` is
the matching no-call executor view. It returns
`ExecutorKind='guarded-call-function-native-executor'`, bridge/object/function
gates, `NativeCallable`, `NativeExecutorBlockReason`, and
`NativeInvoked=false`; the smoke self-test exercises it before
`InvokeCallFunctionNative`.
Confidence: high.
`CreateProcessEventParams(function)` is also present on native Linux,
Windows/Proton, and the Linux dedicated server loader. It allocates a bounded
loader-owned params buffer from the promoted function descriptors and returns
the same `ProcessEventParams` table shape used by live hook callbacks:
`Kind='ProcessEventParams'`, `IsValid`, `PropertyCount`, `Properties`, and
direct field aliases such as `params.Value`. The returned handle works with
`GetParamValue`, `SetParamValue`, and descriptor shorthand methods like
`params.Value:get()`. This proves descriptor-backed params layout and Lua
marshaling outside an active callback; readiness reports this direct buffer
evidence as `luaProcessEventParamsBuffer`, backed by the
`event=lua-process-event-params-buffer status=created` log row. It still does
not call arbitrary native `ProcessEvent`.
`InvokeProcessEventNative` now reports the same descriptor preflight state:
`DescriptorBackedCallable`, `ParamsBufferConstructible`,
`ParamsDescriptorCount`, `ParamsBufferSize`, `InvokeRequested`, and
`NativeNonSelfTestEnabled`. Summaries expose
`luaProcessEventNativeInvokeSelfTestCount`,
`luaProcessEventNativeInvokeNonSelfTestGateCount`, and
`luaProcessEventNativeInvokeNonSelfTestInvokedCount`; readiness reports the
closed preflight as `luaProcessEventNativeInvokeNonSelfTestGate=true`. For
non-self-test functions with registry evidence and constructible params, the
guarded status is `descriptor-preflight-ready`; if Lua passes `{Invoke=true}`
while the opt-in env is unset, the status is `non-self-test-invoke-disabled`.
Readiness exposes the no-call state as
`luaProcessEventNativeInvokeDescriptorPreflight` and the closed explicit-invoke
state as `luaProcessEventNativeInvokeNonSelfTestGate`.
`GetProcessEventNativeExecutorState(object, function)` is the explicit no-call
executor view for the same bridge. It returns
`ExecutorKind='guarded-process-event-native-executor'`,
`NativeBridgeArmed`, object/function registry gates, descriptor/params-buffer
readiness, `NativeCallable`, `NativeExecutorBlockReason`, and
`NativeInvoked=false`; the smoke self-test exercises it before
`InvokeProcessEventNative`.
Actual non-self-test native invocation is implemented but disabled unless Lua
passes `{Invoke=true}` and the target-specific opt-in is set:
`DUNE_CLIENT_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE`,
`DUNE_WIN_CLIENT_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE`, or
`DUNE_SERVER_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE`. When both gates
are open, the loader seeds a descriptor-sized params buffer from matching Lua
table fields, calls the original `ProcessEvent` trampoline, and reports
`NativeNonSelfTestInvoked=true`, `ParamsWritten=<n>`, and
`status=non-self-test-invoked`.

## Portability Contract

Run `scripts/ue4ss-portability-contract.py --check` before packaging or
claiming a parity step. It emits the current portability contract for the
Linux native client, Windows/Proton client, and Linux dedicated server artifacts,
including the expected injection model split: `LD_PRELOAD` for ELF targets and
`version.dll` plus `WINEDLLOVERRIDES` for the Proton PE target.

The contract is intentionally source/package based. It proves that each target
still carries the same UE4SS-facing surfaces for runtime anchors, object and
function lookup, reflection, ProcessEvent hook dispatch, Lua hook routing, Lua
mod lifecycle, scheduler/input callbacks, world/engine helpers, object
notification, and container marshaling. Runtime canary readiness still comes
from `scripts/ue4ss-port-readiness.py`; the portability contract prevents one
target from silently falling behind before that canary runs.
It also has target-specific package gates for root-discovery hardening:
`linux-client` and `linux-server` must carry the ELF qword/scalar writable-root
classifier plus candidate exporter, and `windows-client` must carry the PE
qword/scalar writable-root classifier plus the same candidate exporter. Those
gates prevent client or Proton paths from regressing to scalar-heavy
writable-root candidates after the server-side live canaries showed that
anonymous writable-root queues have a high false-positive rate. Confidence:
high.
The planner now treats qword root-recovery candidates as canary-quality only
when the candidate metadata includes qword references and both read and write
classified accesses. Address-only roots, even when every access is 8 bytes, stay
blocked as `unproven-root-recovery-shape-quality`. This rule applies equally to
native Linux ELF clients, Linux dedicated servers, and Windows/Proton PE
clients. Confidence: high.
The root-shape reports also emit `addressRatio`, and the shared planner blocks
address-heavy read/write roots as `address-heavy-root-recovery-candidates`.
Exporters should use `--max-address-ratio` for live-canary candidate queues so a
mostly address-taking global cannot advance to runtime probing just because a
few read/write references exist. Confidence: high.
`export-ue-writable-root-shape-candidates.py` also supports
`--max-ref-count`, `--max-function-buckets`, `--require-read-write`,
`--require-qword`, and `--min-qword-refs`. Use those gates with
`--max-address-ratio` before producing a live `*_UE_CANDIDATE_GLOBALS` env file
from a broad root-shape report; otherwise high-fanout `.bss` globals can
outrank smaller but more plausible root candidates.
Candidate exports also carry hint-quality metadata: exact, specific, and
generic context counts. The planner blocks generic-only root-recovery input as
`generic-only-root-recovery-context`; use `--require-specific-context` or
`--require-exact-anchor` for live-canary queues. This prevents generic
`UObject *`, `const FName &`, or `CoreUObject/Class.h` mentions from becoming
runtime root hypotheses without stronger target-image evidence. Confidence:
high.
When the root set is bounded but ambiguous, the loaders now support
`DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS=true` and
`DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS=true`. Those
promote numbered `RuntimeFNamePoolCandidate<N>` and
`RuntimeGUObjectArrayCandidate<N>` anchors so FName and object-array consumers
can validate the real root in the same canary instead of requiring a replay.
`export-ue-writable-root-shape-candidates.py` can also join writable-global
context into anonymous root-shape rows with `--writable-global-refs-json`.
The joined input can be a writable-global refs report, an ELF string-dataflow
report, or an ELF/PE function-neighborhood report as long as it carries
`writableTargets`/`context` rows with exact and group hint counts. Use that when
a shape report has good qword/read-write/access-ratio evidence but lacks
`context` rows of its own. The joined export must still pass
`--require-specific-context` and, for live root promotion, should pass
`--require-exact-anchor`; shape-only rows with no matching exact/specific
global context are triage input, not canary input. Exact context is also not
enough by itself: address-heavy rows and rows without classified read/write
accesses remain blocked. This rule is shared by the Linux server loader, native
Linux ELF client loader, and Windows/Proton PE client loader. Confidence: high.
ELF and PE function-neighborhood reports may inherit exact/group context from
the source xref seed when the writable target itself is anonymous. That is valid
for ranking and for later package/dispatch investigation, but a read-only
candidate with no classified write refs is still not a promoted runtime root.
Keep those leads labeled as package/dispatch hypotheses until a canary path can
prove the actual callable surface in the target process. Confidence: high.
`export-ue-candidate-globals.py --format json` reports
`rejectedReasonCounts` so a zero-candidate export distinguishes weak evidence
from tooling failure. For example, `missing-root-shape` means the writable
global had context hints but no matching read/write root-shape row, while
`max-refs` or `max-function-buckets` means the row was intentionally suppressed
as a generic high-fanout global.
When an exact anchor hint appears only in the writable-global context report,
rerun `summarize-elf-writable-root-shapes.py` or
`summarize-pe-writable-root-shapes.py` with `--include-target 0x...` to force
that target into the root-shape report. The row is marked `forcedInclude=true`
and still carries `addressRatio`, read/write counts, qword counts, and samples,
so `export-ue-candidate-globals.py` can reject it with a precise reason such as
`max-address-ratio` instead of hiding it as `missing-root-shape`.
After generating readiness JSON, run
`scripts/summarize-ue4ss-port-gaps.py --readiness-json ue4ss-readiness.json
--canary-plan-json next-canary.json`.
That report projects raw gates into feature-parity buckets: runtime anchors,
object registry/FindObject, reflection/FProperty, ProcessEvent hook dispatch,
Lua mod dispatch, package loading/LoadAsset, and complete UE4SS Lua API. Use
it as the operator-facing progress report; use readiness JSON for underlying
evidence and blockers. It also includes the recommended next canary stage and
`plan-ue4ss-canary-env.py` command templates for server, native Linux client,
and Windows/Proton targets.

## Native Linux ELF Runbook

Toolchain check:

```bash
make loader-build-toolchain-check
```

Install missing loader build tools:

```bash
make loader-build-toolchain-install
```

Build:

```bash
scripts/build-linux-client-loader.sh
```

Smoke:

```bash
scripts/smoke-linux-client-loader.sh
```

Launch a native ELF client:

```bash
scripts/launch-linux-client-probe.sh -- /path/to/DuneSandbox-Linux-Shipping
```

Non-mutating preflight for the native ELF path:

```bash
DUNE_CLIENT_PROBE_PREFLIGHT_ONLY=true \
  scripts/launch-linux-client-probe.sh -- /path/to/DuneSandbox-Linux-Shipping
```

The preflight validates that the target is not a Windows/PE executable, reports
the selected loader and `LD_PRELOAD` plan, and exits before building the loader
or executing the client.

Default log:

```text
/tmp/dune-client-probe-loader.log
```

Useful environment:

```dotenv
DUNE_CLIENT_PROBE_LOG=/tmp/dune-client-probe-loader.log
DUNE_CLIENT_PROBE_FORCE=true
DUNE_CLIENT_PROBE_LOG_MODULES=true
DUNE_CLIENT_PROBE_SCAN_ENABLED=true
DUNE_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
DUNE_CLIENT_PROBE_SCAN_STRINGS=ProcessEvent;CallFunctionByNameWithArguments;FNamePool;GUObjectArray;StaticLoadObject;StaticLoadClass;LoadObject;LoadPackage;ResolveName;CheatManager
DUNE_CLIENT_PROBE_SCAN_SIGNATURES=name=48 8b ?? ?? 48 85 c0
DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE=/path/to/client-signatures.txt
DUNE_CLIENT_PROBE_UE_ANCHORS=FNamePool=0x0;GUObjectArray=0x0;GWorld=0x0;GEngine=0x0;ProcessEvent=0x0;CallFunctionByNameWithArguments=0x0
DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=
DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=/path/to/client-anchor-signatures.txt
DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS=
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS=true
DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS=0
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES=268435456
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0
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
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false
DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX=32
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN=false
DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96
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
DUNE_CLIENT_PROBE_SCAN_MAX_MAPPING_BYTES=268435456
```

The Linux launch wrapper refuses Windows/PE targets and reports that the Proton
DLL path is required.

## Windows/Proton Runbook

Build:

```bash
scripts/build-windows-client-loader.sh
```

Smoke:

```bash
scripts/smoke-windows-client-loader.sh
```

The default Windows smoke proves loader, scan, proxy forwarding, hook, mod,
object-array, FName, and Lua missing-DLL behavior. It does not prove a real
Windows Lua runtime. Run the parity smoke to execute the real Lua path; it
stages a pinned LuaBinaries 5.4.8 `lua54.dll` under `build/` automatically when
`DUNE_WIN_CLIENT_PROBE_LUA_DLL` is unset:

```bash
make smoke-windows-client-loader-lua
```

before treating Windows/Proton Lua dispatch parity as fully validated.
Confidence: high.

Recommended Steam launch option for the installed Dune client:

```bash
/home/keith/Documents/code/DuneAwakeningSelfHost/scripts/launch-proton-client-probe.sh --stage-to-game-dir -- %command%
```

Non-mutating preflight for the Proton/Windows path:

```bash
scripts/launch-proton-client-probe.sh --preflight-only --stage-to-game-dir
```

The preflight resolves the Steam/game directory when available, reports the DLL,
sidecar, manifest, and launch plan, and exits before building, copying
`version.dll`, writing the sidecar, exporting Wine variables, or launching the
client.

This stages:

```text
~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/version.dll
~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/dune-win-client-probe.env
```

and records:

```text
build/windows-client-loader/game-dir-stage-manifest.txt
```

Default log:

```text
/tmp/dune-win-client-probe-loader.log
```

Useful environment:

```dotenv
DUNE_WIN_CLIENT_PROBE_LOG=Z:\tmp\dune-win-client-probe-loader.log
DUNE_WIN_CLIENT_PROBE_LOG_MODULES=true
DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=true
DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS=ProcessEvent;CallFunctionByNameWithArguments;FNamePool;GUObjectArray;StaticLoadObject;StaticLoadClass;LoadObject;LoadPackage;ResolveName;CheatManager
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES=name=48 8b ?? ?? 48 85 c0
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE=Z:\path\to\client-signatures.txt
DUNE_WIN_CLIENT_PROBE_UE_ANCHORS=FNamePool=0x0;GUObjectArray=0x0;GWorld=0x0;GEngine=0x0;ProcessEvent=0x0;CallFunctionByNameWithArguments=0x0
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=Z:\path\to\client-anchor-signatures.txt
DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS=
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS=true
DUNE_WIN_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS=0
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REGION_BYTES=268435456
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0
DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_MAX_FIELDS=16
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FUNCTION_FLAGS_OFFSET=0x58
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
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=
DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED=false
DUNE_WIN_CLIENT_PROBE_LUA_MOD_SCRIPTS=
DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT=
DUNE_WIN_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=false
DUNE_WIN_CLIENT_PROBE_GAME_DIR=
DUNE_WIN_CLIENT_PROBE_UNREAL_VERSION_MAJOR=5
DUNE_WIN_CLIENT_PROBE_UNREAL_VERSION_MINOR=0
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_REGION_BYTES=268435456
DUNE_WIN_CLIENT_PROBE_SCAN_PRIVATE=false
```

The same keys are valid in `dune-win-client-probe.env`. The launch wrapper
writes the sidecar automatically during staging, and process environment values
override sidecar values if both are present. This covers normal Steam launches
where the proxy DLL loads but the wrapper environment was not inherited.

Remove the staged proxy if it still matches the current probe:

```bash
scripts/launch-proton-client-probe.sh --unstage-game-dir
```

The wrapper backs up an unrelated preexisting `version.dll` before replacing it.
Manifest-owned probe DLLs are restaged without accumulating backups.

If `/proc/<pid>/maps` shows Proton's builtin `version.dll` instead of the staged
game-directory proxy, set the per-app Wine DLL override:

```bash
scripts/proton-dll-override-control.sh --set
scripts/proton-dll-override-control.sh --query
```

Unset it with:

```bash
scripts/proton-dll-override-control.sh --unset
```

## Packaging

Build both client packages:

```bash
make package-client-loaders
```

Outputs:

```text
dist/linux-client-loader/
dist/windows-client-loader/
```

The Windows archive also carries the receipt-bound transactional deployment
manager, its operator runbook and tests, and the current build-specific canary
record. Packaging runs the manager tests, verifies every internal checksum,
rejects unsafe tar members, verifies the outer archive digest, and records the
results as `client-deployment-test.txt` plus
`loader-artifact-verification.{txt,json}` inside the archive and sibling
`.verification.{txt,json}` reports beside every Windows/Linux loader archive.
Use `docs/client-deployment.md` from the extracted package instead of staging
the DLL with an untracked copy command.

Each package includes source, build helper, launch helper, smoke helper, docs,
ABI/header reports, `package-provenance.json`, and `SHA256SUMS`. Archive member
metadata, generated timestamps, gzip headers, ABI paths, and packaged test
receipts are normalized for reproducible output. See
[`reproducible-loader-packages.md`](reproducible-loader-packages.md) for the
build-input contract, provenance schema, and independent verification flow.

## Analysis Tools

Summarize a Linux or Windows client probe log:

```bash
scripts/summarize-client-loader-scan.py /tmp/dune-win-client-probe-loader.log
```

Summarize UE anchor readiness from the same log:

```bash
scripts/summarize-client-ue-anchors.py /tmp/dune-win-client-probe-loader.log
```

For a native Linux ELF client, map runtime scan hits back into the ELF file and
rank simple code xrefs:

```bash
scripts/summarize-linux-loader-xrefs.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --exe-substring DuneSandbox \
  --category cheat \
  --category brt
```

Validate Linux ELF seed uniqueness and export a line-based runtime signature
file:

```bash
scripts/validate-elf-signatures.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --exe-substring DuneSandbox \
  --category cheat \
  --category brt

scripts/export-elf-signature-manifest.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --target-loader linux-client \
  --exe-substring DuneSandbox \
  --category cheat \
  --category brt \
  --format signatures

scripts/export-elf-signature-manifest.py \
  /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
  --target-loader linux-client \
  --exe-substring DuneSandbox \
  --category ue \
  --format anchor-signatures
```

For full native Linux manifests, prefer the `signatures` output and point
`DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE` at it. The JSON output is the
cross-build revalidation artifact. Use `anchor-signatures` for validated UE
anchor rows and point `DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` at that
file during the next read-only canary. Confidence: high for synthetic ELF
validator coverage.

For a full second-pass native Linux canary bundle, generate all anchor inputs
and the readiness report together:

```bash
scripts/prepare-ue-anchor-canary.py \
  --platform linux-client \
  --binary /path/to/DuneSandbox-Linux-Shipping \
  --loader-log /tmp/dune-client-probe-loader.log \
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
```

For the Windows/Proton client, map runtime scan hits back into the PE file and
rank simple code xrefs:

```bash
scripts/summarize-client-loader-xrefs.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --category deep-desert \
  --show-context \
  --show-seeds
```

This is the bridge from read-only runtime canary to static signature work. It
uses loader `rva` values, PE section headers, and x86-64 RIP-relative/call/jump
patterns; it does not patch or inject anything further. The `--show-seeds`
output wildcards the relative displacement inside each xref instruction and is
a seed for later cross-build validation, not a final signature. Confidence:
high.

Validate Windows/Proton seed uniqueness:

```bash
scripts/validate-client-pe-signatures.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt
```

Only `unique-expected` seeds should move into build-check manifests. Everything
else remains useful context but is not durable enough to gate patch/hook work.
Confidence: high.

Export the validated Windows/Proton manifest or runtime scan chunks:

```bash
scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --format json

scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --format env

scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --format signatures

scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category ue \
  --format anchor-signatures
```

For full Windows/Proton manifests, prefer the `signatures` output and point
`DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE` at it. The env output is chunked
for sidecar/env value limits; use one chunk per client launch and do not
concatenate all chunks into a single sidecar value. Use `anchor-signatures` for
validated UE anchor rows and point
`DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE` at that file during the next
read-only Proton canary. Confidence: high.

Revalidate an exported Windows/Proton manifest after a client update:

```bash
scripts/validate-client-pe-signatures.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --manifest-json build/windows-client-loader/client-pe-signature-manifest.json \
  --ignore-expected-offsets
```

Use exact-offset validation without `--ignore-expected-offsets` for same-build
proof. Use offset-ignored validation for a new build to separate moved unique
signatures from missing or ambiguous signatures before runtime canary work.
Confidence: high.

Rank Proton proxy fallback DLLs from the Dune PE import table:

```bash
scripts/proton-proxy-candidates.py ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe
```

Current ranking on this host puts `version.dll` first because the executable
imports it directly, it has a small forwarding surface, and the existing
`version.dll` is manifest-owned by our probe. Fallbacks if `version.dll` fails
are `dxgi.dll`, `winmm.dll`, `xinput1_3.dll`, `d3d9.dll`, `d3d11.dll`, and
`dsound.dll`, in that order from the current import-table evidence. Confidence:
moderate until a real Dune launch log proves `version.dll` loads early enough.

## Interpreting Logs

First validate load:

```text
event=loaded
event=module
```

Then validate scan setup:

```text
event=scan-start
event=scan-hit
event=scan-finish
```

If explicit UE anchors are configured, validate them separately:

```text
event=ue-anchor-start
event=ue-anchor name=<anchor> group=<group> status=mapped
event=ue-anchor-finish
event=ue-candidate-global name=<anchor> status=added
event=ue-pointer name=<anchor> status=target-mapped
event=ue-layout name=<anchor> status=target-readable
event=ue-layout-slot name=<anchor> status=target-mapped
event=ue-uobject name=<anchor> status=candidate
event=hook-dispatch-self-test status=passed
event=ue-process-event-hook status=passed
event=ue-process-event-dispatch-self-test status=armed
event=ue-process-event-live-hook status=installed
event=mod-dispatch-self-test status=passed
event=lua-dispatch-self-test status=passed
```

`status=unmapped` is a blocker for that anchor and does not count toward
object-discovery readiness. `ue-pointer status=target-mapped` is the next gate:
it means the anchor can be read as a pointer-sized value and the value lands in
mapped memory. `ue-layout-slot status=target-mapped` is the next bounded layout
signal. `ue-uobject status=candidate classMapped=true` means the pointed-to
target has readable `UObjectBase`-shaped fields and its `ClassPrivate` value is
mapped. It still does not prove the full Unreal layout is correct.

`DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES` and
`DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES` use the same `name=aa bb ??`
syntax as normal scan signatures, but only unique runtime matches are promoted
to UE anchors. Missing and ambiguous matches log
`event=ue-anchor-signature status=missing|ambiguous` and are ignored for deeper
pointer/layout/UObject probes. Add `@hit+N`, `@riprel32+N`, `@callrel32`, or
`@ptr+N` to the signature name when the match is an instruction or pointer
slot rather than the anchor address itself, for example
`GWorld@riprel32+3=48 8b 0d ?? ?? ?? ??`. Confidence: high.

`DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS` and
`DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS` accept semicolon-delimited
`Name=0xIMAGE_OFFSET` or `Name=0xRVA` values and resolve them against the
current target image at runtime. Use this when offline ELF/PE analysis finds a
weak global candidate, but the loader still needs ASLR-correct live evidence
before pointer/layout/reflection probes run. The lab-only absolute-address form
is `Name@addr=0xADDRESS`; do not use it for normal canaries because it is not
portable across restarts. Native Linux loaders also accept
`Name@rwfile=0xFILE_OFFSET` for restart-stable mapped RW offsets from the live
`/proc/<pid>/maps` surface. The Windows/Proton loader accepts
`Name@private-rva=0xOFFSET` for committed writable `MEM_PRIVATE` allocations;
ambiguous or missing private-RVA matches are logged and skipped. A
`ue-candidate-global status=added` row means only that the candidate address was
injected into the anchor-validation pass; it is not anchor proof until a
following `ue-anchor status=mapped`,
`ue-pointer status=target-mapped`, and deeper object/reflection evidence pass.
Run `summarize-ue-candidate-outcomes.py` on each canary log before reusing
candidate globals; it classifies candidates as `rejected`,
`weak-false-positive`, `weak`, `promising`, or `promotable` and prevents code
pointers, null globals, empty object arrays, and unmapped UObject shapes from
being recycled into the next pass.
Run `summarize-ue-candidate-shapes.py` on the same log when a canary includes
candidate globals. It groups each injected image offset/RVA across its runtime
addresses, attaches pointer/layout/UObject/object-array/FName evidence, and
reports whether the candidate is promotable, promising, a code-pointer false
positive, null/empty, implausible as an object-array header, unmapped, or still
unknown. This report is stricter than the raw log: a candidate is not promoted
just because one phase mapped it.
For ELF and PE targets, `summarize-ue-code-pointer-context.py` can then
disassemble code-pointer false positives and show adjacent pointer-table
context. The ELF path can also use symbol/relocation hints from the staged
binary; the PE path is intentionally leaner and reports section/RVA/string
context from the image plus decoded RIP/control-flow references.
`summarize-ue-root-recovery-queue.py` consumes function-neighborhood output
plus candidate outcomes and ranks the remaining static functions/writable
globals for root-recovery review. Treat that queue as triage input, not as an
anchor manifest; live promotion still requires mapped pointer/layout/UObject or
FName evidence.
`cluster-ue-root-recovery-queue.py` groups that queue by source family and
writable-target range so repeated constructor/table families can be reviewed as
one surface. It is binary-format neutral if the input JSON has the expected
queue schema. Linux uses `summarize-elf-ue-function-neighborhoods.py`;
Windows/Proton uses `summarize-pe-ue-function-neighborhoods.py`, seeded from
the PE xref summary. The PE path is xref-window based because stripped PE
function boundaries are not available from symbols; confidence that it is
queue-compatible is high, confidence that it is as deep as the ELF constructor
harvest is moderate.
`export-ue-root-recovery-candidates.py` converts that queue plus optional
clusters and candidate-outcome rejects into a bounded
`*_UE_CANDIDATE_GLOBALS` canary env. This is an explicit root-recovery
hypothesis export: it diversifies across clusters/ranges and avoids prior
false positives, but the exported names are not proven anchors until the next
runtime pointer/layout/UObject/FName probes pass. When `--anchor` is omitted,
the exporter now defaults to the `object-discovery` preset:
`FNamePool`, `GName`, `GUObjectArray`, `GObjectArray`, `GWorld`, and `GEngine`. Use
`--anchor-preset hook-planning` when preparing dispatch-surface candidates,
`--anchor-preset package-loading` for package/load-asset surface recovery,
`--anchor-preset reflection` for class/property/function descriptor recovery,
or `--anchor-preset complete` when building a full parity canary input bundle.
The JSON output includes `groupCoverage` for `names`, `objects`, `world`,
`dispatch`, `package`, and `reflection`. `ready=true` means at least one
candidate was emitted for that group; `complete=true` means every known alias
in that group was emitted. Missing aliases remain visible in `missingAnchors`,
and groups with no emitted candidates are listed in `missingGroups`.
For dispatch, package-loading, reflection, or complete parity candidate bundles,
use `--require-source-group-match`. That option only emits an anchor when the
source function neighborhood covered the corresponding UE group, preventing an
anonymous object-table-looking target from being relabeled as `ProcessEvent`,
`LoadPackage`, or `FProperty` without group evidence. Confidence: high.
The planner carries those fields into `nextCanaryContract` and emits
`incomplete-root-recovery-*` blockers when the candidate bundle does not cover
the stage being planned.
`summarize-ue4ss-port-gaps.py --canary-plan-json next-canary.json` reads that
same contract and prints root-recovery candidate coverage beside the remaining
UE4SS parity gaps, including which features are blocked by missing candidate
groups. Pass the same live outcome files to the gap summary with
`--candidate-outcomes-json`; its recommended planner commands will include
those paths so rejected live candidates are carried into the next env plan.
Feed the JSON form into `plan-ue4ss-canary-env.py` with
`--root-recovery-candidates-json`, and pass the latest
`summarize-ue-candidate-shapes.py --format json` output with
`--candidate-shapes-json`. Also pass live
`summarize-ue-candidate-outcomes.py --format json` output with
`--candidate-outcomes-json` so rejected live canary candidates are suppressed
before the next env is generated. The planner will emit the platform-correct
`*_UE_CANDIDATE_GLOBALS` variable, filter candidates already classified as
`rejected-*`, `weak-*`, `rejected`, or `weak-false-positive`, and keep the next
canary at read-only discovery until runtime shape evidence promotes the
candidates.
Confidence: high.

For selected hook targets, pass `--hook-targets-json` or the explicit
`--process-event-image-offset` / `--call-function-image-offset` flags on Linux
and `--process-event-rva` / `--call-function-rva` on Proton/Windows. The planner
emits the generic, hook-probe, and live-hook target env keys together, using
`*_IMAGE_OFFSET` for ELF and `*_RVA` for PE. This keeps hook-probe,
persistent-hook, and Lua-dispatch canaries on the same restart-safe target
instead of a stale absolute address. Confidence: high.

`hook-dispatch-self-test status=passed` proves only the platform hook
substrate: write an absolute jump into loader-owned code, dispatch to a
replacement function, run a pre-callback, call the original bytes through a
generated trampoline, run a post-callback, restore the original bytes, and keep
executing. It is not a `ProcessEvent` hook and it is deliberately disabled by
default. Confidence: high.

`mod-dispatch-self-test status=passed` proves the native mod lifecycle and
callback registry: load a mod entry, register pre/post hook callbacks, dispatch
around an original-call context, and unload the mod entry. This is the layer a
Lua runtime will attach to; it is not Lua execution yet. Confidence: high.

`lua-dispatch-self-test status=passed` proves a Lua VM was loaded dynamically,
a script was compiled/executed through the Lua C API, Lua called the
loader-provided `RegisterHook` function, native code recorded the hook name,
native code stored the Lua pre/post callbacks, native code invoked both
callbacks, `UnregisterHook` removed a temporary hook pair, and the script
result was read back. `RegisterHook` returns UE4SS-shaped `preId, postId`
values. ProcessEvent routing self-tests intentionally keep a non-target hook
registered ahead of the target hook, so the target hook's first id is `4` in
those logs. Native Linux can use system
`liblua`; Windows/Proton needs a staged Lua DLL named by
`DUNE_WIN_CLIENT_PROBE_LUA_DLL` or available under a common DLL name. The
Windows Lua smoke stages the pinned local test DLL automatically when no DLL is
configured. A complete
pass includes `callbackStatus=0 preCalls=1 postCalls=1 preResult=11
postResult=31` and the API surface counters
`staticFindObjectCalls=1 findFirstOfCalls=1 staticConstructObjectCalls=1
notifyOnNewObjectCalls=1 executeInGameThreadCallbacks=1`. It also now exports
dedicated scheduler counters,
`executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2
executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1
schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1`, and
input/command counters,
`keyBindRegistrations=1 keyBindLookupHits=1 keyBindDispatchCalls=2
keyBindCallbackHandled=1 keyBindUnregisterCalls=1 keyBindUnregisterHits=1
consoleCommandHandlers=2 consoleCommandGlobalHandlers=2
consoleCommandHandlerCalls=1 consoleCommandGlobalHandlerHandled=1
consoleCommandUnregisterCalls=2 consoleCommandUnregisterHits=2`. The default
script proves this through
`DuneProbeDispatchKeyBind(context, key)` and
`DuneProbeDispatchConsoleCommand(context, rawCommand)`, which dispatches
registered named handlers first and then global handlers until one returns a
handled result; it also unregisters temporary keybind and command handlers and
proves the removed callbacks do not fire. The object API check
now also requires `staticFindObjectHits=1 findFirstOfHits=1
findAllOfHits=1 loadAssetHits=1 staticConstructObjectHits=1`, proving the
lookup calls returned loader object-handle tables, class enumeration works
through both `FindObjects` and `FindAllOf`, `LoadAsset` resolves an already
known handle, and synthetic construction returned a handle instead of `nil`.
`LoadAsset` is loader-owned here too: it is a registry lookup by path/name, not
package loading. `GetStaticConstructObjectNativeExecutorState(class, outer, name)` and `InvokeStaticConstructObjectNative(class, outer, name, {Invoke=true})` now expose the guarded `StaticConstructObject` native executor contract. They report target address, target-image confirmation, class/outer/name call-frame state, FName indices, object/internal flags, ABI evidence, invoke gates, crash-guard state, native return address, and return memory readability. The native call only runs after target, target-image, ABI, FName, final-call, invoke, and crash-guard gates are all explicitly confirmed for the active platform; Proton/Windows keeps the call closed unless the DLL was built with recoverable SEH support. The strict live target-image contract now requires both `lua-static-construct-object-native-executor-state` readiness and a `lua-static-construct-object-native-invoke` row with `nativeInvoked=true` before construction counts toward 1:1 UE4SS parity. `StaticConstructObject` is loader-owned here: it creates a
bounded `/RuntimeProbe/Constructed/<Name>` registry handle and does not
allocate a live Unreal object. It preserves `ClassAddress` when the class
argument is a known object or `UClass` handle. If
`NotifyOnNewObject(filter, callback)` has a
matching loader-owned class/path/name filter, synthetic construction dispatches
every matching callback with the constructed handle and logs
`notifyOnNewObjectCallbacks`, `notifyOnNewObjectResult`,
`notifyOnNewObjectIsNumber`, and `notifyOnNewObjectStatus`; the default
Lua dispatch self-test now requires `notifyOnNewObjectCallbacks=1`,
`notifyOnNewObjectResult=17`, and `notifyOnNewObjectStatus=0`.
`NotifyOnNewObject` returns a stable active-registration id, and
`UnregisterNotifyOnNewObject(id)` removes that registration before synthetic
construction dispatch. The smoke path proves a removed matching callback does
not fire while the two still-active matching callbacks do. This is still not a
live Unreal construction hook. Live Dune object handles still require validated
GUObjectArray/FNamePool anchors from the target build. Class-mapped
`ue-uobject` probe candidates are added as `/RuntimeProbe/<AnchorName>` handles
and logged with `event=lua-object-registry source=ue-uobject status=added`.
The parity fixture includes `RuntimeProbeUObject`, which must log
`registryProvenance=runtime` from this same `ue-uobject` source on Linux client,
Linux server, and Windows/Proton before `luaObjectRegistryRuntime` is considered
green.
When FName decoding succeeds, the same object is also exposed as
`/RuntimeProbe/<DecodedName>` with `source=ue-uobject-fname`; later object-array
aliases for the same decoded name/address are logged as `status=skipped` so the
registry remains stable.
Successful UObject or object-array promotion also logs
`event=ue-object-native-identity` with the decoded object name, decoded class
name, class pointer, and `OuterPrivate` address that were promoted into the Lua
handle. The readiness report exposes this as `ueObjectNativeIdentities`; it is
the gate that separates synthetic registry handles from native UE identity
evidence.
Before the bounded object-array walk, current loaders also log
`event=ue-object-array-shape`. That line records whether header counters are
plausible (`maxElements >= numElements`, `maxChunks >= numChunks`, bounded
chunk counts), whether the first chunk slot is readable, and whether the first
chunk pointer maps. `status=header-implausible` is a read-only rejection signal
for root-recovery candidate globals; it should be treated as a failed
candidate, not as an anchor. The readiness report exposes plausible header
evidence as `ueObjectArrayShape`; that key is not enough by itself. Runtime
object discovery still requires `ueObjectArrayRegistryRuntime`,
`ueObjectNativeIdentities`, and `ueFNameDecoder`.
Confidence: high for Linux on this host, moderate for Windows until a real Lua
DLL is staged.

Set `DUNE_CLIENT_PROBE_UE_FNAME_PROBE=true` or
`DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE=true` after a valid `FNamePool`/`GName`
anchor is configured. The bounded decoder reads UE-style block entries and logs
`event=ue-fname status=decoded` for UObject/object-array candidates whose
`NamePrivate` fields resolve. Confidence: high for the self-test fixture,
moderate for live Dune until same-build FNamePool anchors are validated.

When decode fails on a live build, set
`DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=true` or
`DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=true` with the `*_MAX` limit kept
small. The loaders emit bounded `event=ue-fname-diagnostic` records with raw
entry bytes and alternate header interpretations; this is the evidence used to
correct decoder layout without turning on hooks.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_PROBE=true` or
`DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE=true` after pointer, UObject, and
FName probes are stable. The probe reads the candidate object's class pointer,
logs `event=ue-reflection status=class-mapped`, and classifies configured
UClass/field slots with `event=ue-reflection-slot`. Slot offsets are
environment-configurable and default to the synthetic self-test layout. This is
read-only metadata telemetry; it does not marshal live `FProperty` values.
Confidence: high for the self-test fixture, moderate for live Dune until
offsets are validated against the current build.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=true` or
`DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=true` only after the class/slot
probe is stable. The loader walks bounded `children`, `childProperties`,
`propertyLink`, and `functionLink` chains from the configured UClass offsets,
logs `event=ue-reflection-field status=candidate`, and decodes field names
through the FName reader when enabled. `*_UE_REFLECTION_FIELD_NEXT_OFFSET`
defaults to `0x28`, and `*_UE_REFLECTION_MAX_FIELDS` defaults to `16` with a
hard clamp. This proves candidate `FField`/`UField` chain visibility, not live
property marshaling. Confidence: high for the self-test fixture, moderate for
live Dune until current-build offsets are validated.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=true` or
`DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=true` after field walking
is stable. This implies the bounded field walk and reads property-shaped
descriptor fields from `childProperties` and `propertyLink`: `ArrayDim`,
`ElementSize`, `PropertyFlags`, and `Offset_Internal`. It logs
`event=ue-reflection-property status=candidate`. Offsets default to UE4-style
values but must be validated per Funcom build before live marshaling.
For each bounded `functionLink` candidate, the same probe also reads the
configured `FunctionFlags` slot plus function-level `childProperties` and
`propertyLink` roots, then emits `event=ue-function-param-root` plus
`event=ue-function-param` descriptor lines when param metadata is readable.
Readable descriptors and readable `FunctionFlags` values are promoted into
the bounded live `UFunction` param registry, and
`GetFunctionParamDescriptors(function)`/`GetFunctionParams(function)` returns
them when Lua passes the matching live function handle. The handle also exposes
`Function:GetFunctionParams()`, `Function:GetFunctionParamDescriptors()`,
`Function:GetParamDescriptor(name)`, and `Function:ForEachParam(callback)`;
readiness tracks the table method path as `ueProcessEventFunctionParamMethod`,
direct name lookup as `ueProcessEventFunctionParamLookupMethod`, and callback
iteration as `ueProcessEventFunctionParamIterationMethod`. This is
equal for native Linux and Windows/Proton. When the `functionLink` FName decodes, the descriptor
log also carries `functionName`, UE4SS-style `functionPath`, and
`functionRuntimePath`; Lua `ctx.Function.PathName`/`GetFunctionParams(ctx.Function)`
use the `/Script/<owner>.<function>:Function` identity and retain the older
`/RuntimeProbe/<owner>.<function>:Function` identity as runtime evidence. When
a readable UFunction root is promoted, loaders also emit
`event=ue-function-native-identity` with function address, decoded function
name, UE4SS path, runtime path, root address, and readable `FunctionFlags`.
Readiness exposes this as `ueFunctionNativeIdentities`. When the FName decoder
can read the parameter field's class object, the registry also carries
`fieldClassName`/`ClassName`, so Lua can
distinguish scalar, bool, and object-pointer params. This is not full live
`FProperty` marshaling for strings, names, arrays, structs, or complex out-param
lifetimes.
Confidence: high for the self-test fixture, moderate for live Dune until
current-build offsets are validated.

Set `DUNE_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=true` or
`DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=true` after descriptor offsets
are stable. This implies the descriptor probe and reads up to
`*_UE_REFLECTION_VALUE_MAX_BYTES` raw bytes from the owning object at
`Offset_Internal`, logging `event=ue-reflection-value status=read` with
`fieldName`, `raw`, and `rawLe`. Successful reads are also registered as
read-only Lua raw property candidates keyed by decoded field names such as
`SelfTestUObjectName_0` when the FName reader is available, with positional
fallback keys such as `propertyLink[0]`; Lua `GetPropertyValue` re-reads
1/2/4/8-byte scalar candidates from the owning object through the same guarded
memory checks. The self-test queries `/RuntimeProbe/SelfTestUObject` by both
positional raw path and decoded field-name alias. If
`*_LUA_REFLECTION_RAW_SET_ENABLED=true`, `SetPropertyValue` can write bounded
1/2/4/8-byte scalar candidates only when the destination range is writable; keep
it false for read-only canaries. The smoke fixture enables it only against
loader-owned memory and expects `rawPropertyHits=3 namedPropertyHits=1 rawPropertySetHits=1
rawPropertySetValue=17`.
This proves bounded container-byte visibility and Lua-visible live raw scalar
get/set; it is not typed `FProperty` marshaling. Confidence: high for the
self-test fixture, moderate for live Dune until current-build offsets are
validated.

For container params, the reflection probe also performs a bounded pointer-slot
scan across `FArrayProperty`, `FSetProperty`, and `FMapProperty` descriptors.
Decoded candidates emit `event=ue-function-param-container-child` with role
`inner`, `element`, `key`, or `value`, plus child property/class names when the
FName resolver can decode them. The scan window defaults to `0x48..0xa0` and is
controlled by `*_UE_REFLECTION_CONTAINER_CHILD_SCAN_START` and
`*_UE_REFLECTION_CONTAINER_CHILD_SCAN_END`. The readiness key is
`ueFunctionParamContainerChildren`; it proves metadata needed for future typed
container element unmarshaling, not the element unmarshaling itself. The
ProcessEvent self-test also emits descriptor-backed child metadata with
`source=process-event-self-test` for array inner, set element, and map key/value
descriptors, so Linux client, Linux server, and Proton/Windows smokes carry the
same readiness evidence. Promoted live param descriptors expose decoded
children to Lua as `ContainerChildren`
plus UE4SS-style accessors/fields: arrays use `GetInner()` and `Inner*`, sets
use `GetElementProperty()`/`GetElementProp()` and `Element*`, and maps use
`GetKeyProperty()`/`GetKeyProp()` plus `GetValueProperty()`/`GetValueProp()` and
`Key*`/`Value*`.

The Lua object-registry surface now includes `StaticFindObject`,
`FindObject`, `FindFirstOf`, `GetKnownObjects`, `FindObjects`, `FindAllOf`,
`ForEachUObject`, `GetObjectFromAddress`, `FindObjectByAddress`, `IsA`,
`LoadAsset`, and `LoadClass` on the Linux server, native Linux client, and
Windows/Proton client loaders. `GetKnownObjects()`, `FindObjects()`, and
`FindAllOf()` return tables keyed by runtime `PathName` plus `Count`;
`GetObjectFromAddress(address)` and `FindObjectByAddress(address)` resolve a
known runtime address back to the same handle shape;
`ForEachUObject(callback[, class])` iterates the same bounded registry; and
`IsA(object, class)` checks the handle class or base `UObject`.
`LoadAsset(pathOrName)` returns an existing registry handle by default.
`LoadClass(classOrObjectPath)` returns a registry-backed `UClass` handle by
class name or by resolving an object's path/name to its class. When a mod passes
`LoadClass(path, {Backend="package"})`,
`{Package=true}`, `{TryPackage=true}`, or enables the matching
`*_LOAD_CLASS_PACKAGE_DRY_RUN` env, the loader refreshes package anchors and
logs `event=lua-load-class-package-preflight` against `StaticLoadClass`,
including target image, mapping/protection, executable, invoke, ABI, TCHAR, and
call-frame gates. Mods can also call `GetLoadClassPackageBridgeState()`,
`GetLoadClassPackageAbiState()`,
`GetLoadClassPackageCallFrameVerificationState(path)`,
`GetLoadClassPackageNativeExecutorState(path)`, and
`InvokeLoadClassPackageNative(path, {Invoke=true})` to inspect the staged
`StaticLoadClass` call plan. These APIs report `ClassRootReady`,
`NativeCallable`, `NativeCallPlanAccepted`, and `NativeInvoked=false` until the
target-image `StaticLoadClass` ABI/root-class call path is proven. `LoadClass`
still returns through the registry fallback until that path is proven. When a mod passes
`{Backend="package"}`, `{Package=true}`, `{TryPackage=true}`, or the package
dry-run env is enabled, the loader routes the `LoadAsset` call through the
guarded package path before returning. `GetLoadAssetBackendState()` reports that contract
explicitly with `Backend="registry"`, `RegistryFallback=true`, and
`PackageBackendArmed=false`; it also reports whether package-loading anchors
were visible through `PackageBackendAvailable`, `StaticLoadObjectResolved`,
`StaticLoadClassResolved`, `LoadObjectResolved`, `LoadPackageResolved`, and
`ResolveNameResolved`.
`PackageBackendTargetImage` must also be true before any guarded native package
call can arm; loader/proxy/self-test anchors only prove that the loader surface
works.
Readiness exposes mod coverage for the Lua contract as
`luaLoadAssetBackendState` and anchor-informed coverage as
`luaLoadAssetBackendAnchors`. Mods can query
`GetLoadAssetPackageBridgeState()` to prove the guarded native package bridge
checkpoint was exercised. That state reports the selected
`StaticLoadObject`/`LoadObject`/`LoadPackage` target, mapped/readable/executable
status, `InvokeEnabled`, `AbiVerified=false`, `NativeBridgeArmed=false`, and a
status such as `anchor-missing`, `target-not-mapped`, `target-not-executable`,
`target-not-target-image`, `invoke-disabled`, or `abi-unverified`. The
`LoadClass` package preflight uses the same status vocabulary for
`StaticLoadClass`, and the class package native-readiness APIs carry the
executor and explicit-invoke plan up to `NativeCallPlanAccepted`; they remain
non-invoking until target-image ABI evidence, root-class evidence, and explicit
native-call confirmation are present. Mods can query
`GetLoadAssetPackageAbiState()` to report the selected package-loading target's
platform ABI contract without calling it: Linux targets return
`PlatformAbi="sysv-x86_64"`, Windows/Proton returns
`PlatformAbi="win64-ms-abi"`, and all targets expose `SignatureFamily`,
`RequiredSignature`, `AbiVerified=false`, `CallFrameReady=false`,
`StringBridgeReady=false`, `ClassRootReady=false`, and `OuterReady=false`.
Readiness exposes this as `luaLoadAssetPackageAbiState`; it is the call-frame
contract checkpoint before native invocation, not package loading.
Current summary/readiness tooling requires package ABI, TCHAR verification, and
call-frame verification records to include `targetImage=true|false` and rejects
contradictory evidence, such as `target-not-target-image targetImage=true` or a
ready call frame with `targetImage=false`. Confidence: high.
`PrepareLoadAssetPackageStringBridge(path)` stages bounded UTF-8 path input for
the native package string bridge without constructing a UE `TCHAR` buffer. It
returns `Source="loader-load-asset-package-string-bridge-state"`,
`StringInputStaged=true`, `BoundedInput=true`, `InputEncoding="utf-8"`,
`TCharEncoding="unverified-live-build"`, `TCharBridgeReady=false`,
`NativeBufferReady=false`, and `NativeInvoked=false`; readiness exposes this as
`luaLoadAssetPackageStringBridge`.
`PrepareLoadAssetPackageNativeBuffer(path)` stages the next dry-run descriptor:
a bounded, NUL-terminated UTF-8 native input buffer, not a UE `TCHAR` buffer. It
returns `Source="loader-load-asset-package-native-buffer-state"`,
`Utf8BufferReady=true`, `NativeInputBufferReady=true`, `BufferBytes`,
`NullTerminated=true`, `TCharBufferReady=false`, `CallFrameReady=false`, and
`NativeInvoked=false`; readiness exposes this as
`luaLoadAssetPackageNativeBuffer`.
`PrepareLoadAssetPackageTCharBuffer(path)` reports the target-specific
candidate `TCHAR` layout without claiming it is UE-compatible yet. Linux
targets report `CandidateEncoding="host-wchar-unverified"` and host
`CandidateUnitBytes`; Windows/Proton reports
`CandidateEncoding="windows-wchar-unverified"` and `CandidateUnitBytes=2`.
All targets keep `TCharLayoutVerified=false`, `TCharBufferReady=false`,
`CallFrameReady=false`, and `NativeInvoked=false`; readiness exposes this as
`luaLoadAssetPackageTCharBuffer`.
`GetLoadAssetPackageTCharVerificationState()` is the evidence gate that can
turn the candidate layout into a verified layout only when explicit canary
evidence is supplied. Linux client uses `DUNE_CLIENT_PROBE_TCHAR_UNIT_BYTES`,
`DUNE_CLIENT_PROBE_TCHAR_EVIDENCE`, and
`DUNE_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT`; Linux server uses
`DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES`, `DUNE_PROBE_LOADER_TCHAR_EVIDENCE`, and
`DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT`; Windows/Proton uses
`DUNE_WIN_CLIENT_PROBE_TCHAR_UNIT_BYTES`,
`DUNE_WIN_CLIENT_PROBE_TCHAR_EVIDENCE`, and
`DUNE_WIN_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT`. Without matching unit bytes,
evidence text, confirmation, and a resolved package anchor it reports
`TCharLayoutVerified=false` and `TCharBufferReady=false`; readiness exposes the
query as `luaLoadAssetPackageTCharVerification`.
`GetLoadAssetPackageCallFrameVerificationState(path)` composes the staged path,
resolved package target, explicit package ABI evidence, and explicit `TCHAR`
layout evidence into the call-frame readiness gate. It returns
`Source="loader-load-asset-package-call-frame-verification-state"`,
`AbiEvidenceProvided`, `AbiVerificationEnabled`, `AbiVerified`,
`TCharLayoutVerified`, `CallFrameReady`, and `NativeInvoked=false`. By default
it reports missing ABI evidence and `CallFrameReady=false`; readiness exposes
the query as `luaLoadAssetPackageCallFrameVerification`.
Local package preflight smokes prove this promotion path without using game
files or calling UE: `scripts/smoke-linux-client-loader-package-preflight.sh`,
`scripts/smoke-linux-server-loader-package-preflight.sh`, and
`scripts/smoke-windows-client-loader-package-preflight.sh` seed a loader-owned
executable `StaticLoadObject` self-test anchor with
`*_LOAD_ASSET_PACKAGE_SELF_TEST_ANCHOR=true`, provide explicit ABI and `TCHAR`
evidence, enable the crash guard, and assert `CallFrameReady=true`,
`NativeCallable=true`, and `FinalNativeCallEligible=true` while
`NativeInvoked=false` and `FinalNativeCallBlocked=true` remain true. This proves
the guarded native package-call boundary and executor eligibility; final UE
native invocation still requires live target evidence.
`PrepareLoadAssetPackageCallFrame(path)` performs the next dry-run step by
staging the Lua path into a package-call descriptor. It reports
`Source="loader-load-asset-package-call-frame-state"`, `PathStaged=true`,
`ArgumentDescriptorReady=true`, platform ABI, signature family, argument count,
`TCharBridgeReady=false`, `CallFrameReady=false`, and `NativeInvoked=false`.
Readiness exposes this as `luaLoadAssetPackageCallFrame`; it still does not
cross into UE or prove package loading. Mods can then call
`InvokeLoadAssetPackageNative(path, {Invoke=true})` to exercise the guarded
native-invocation checkpoint. That returns
`Source="loader-load-asset-package-native-bridge"`, `ContractVersion=1`,
`Invoked`, `InvokeRequested`, `InvokeEnabled`, `TargetImage`, `AbiVerified`,
`TCharLayoutVerified`, `CallFrameReady`, `NativeBridgeArmed`, and platform
native return/exception metadata.
`NativeBridgeArmed` only becomes true after the explicit package ABI and
`TCHAR` evidence gates pass, `PackageBackendTargetImage=true`, and the
target-specific invoke env var is enabled. The loader performs the native call
only when `NativeCallable=true` and the final confirmation env is set; otherwise
the row remains diagnostic and `Invoked=false`. The invoke result also reports
`InvocationDescriptorRequired=true`, `InvocationDescriptorConsumed=true`,
`NativeCallPlanAccepted`, `NativeCallExecutionMode`, and
`NativeCallGuardPolicy`, proving the guarded invocation path consumed the same
descriptor contract that `GetLoadAssetPackageInvocationDescriptorState(path)`
exposes. It logs
`event=lua-load-asset-package-native-invoke` and counts
`loadAssetPackageNativeCalls`/`loadAssetPackageNativeGateHits`.
`GetLoadAssetPackageNativeCallAdapterState(path)` exposes the call adapter that
sits between the verified call frame and guarded native UE call. It
reports `AdapterKind`, `SignatureFamily`, `FunctionPointerReady`,
`CallFrameReady`, `NativeBridgeArmed`, `AdapterReady`, and
`NativeInvoked=false`. It also reports the final safety envelope:
`FinalInvokeConfirmed`, `CrashGuardRequired`, `CrashGuardArmed`,
`GuardedCallRequired`, `GuardedCallReady`, `GuardedCallResult`,
`ReturnValidationReady`, and `NativeCallable`. `NativeCallable` remains false
until explicit final-call confirmation, crash-guarding, guarded-call wrapper
self-test success, and return validation are all present. The adapter logs
`event=lua-load-asset-package-native-call-adapter-state`. Linux targets report
`AdapterKind="sysv-x86_64-package-load"`; Windows/Proton reports
`AdapterKind="win64-ms-abi-package-load"`.
`GetLoadAssetPackageInvocationDescriptorState(path)` derives the same guarded
adapter state into a reusable invocation descriptor. It reports
`Source="loader-load-asset-package-invocation-descriptor-state"`,
`DescriptorKind="guarded-package-native-call"`,
`DescriptorProvenance="adapter-state-derived"`, `DescriptorConstructed=true`,
`NativeCallPlanConstructed=true`,
`NativeCallExecutionMode="guarded-native-package-load"`,
`NativeCallTargetField="TargetAddress"`, `NativeCallPathField="Path"`,
`NativeCallGuardPolicy="crash-guard+guarded-call+return-validation"`,
`NativeCallReturnValidator="uobject-registry-memory-class"`, and the inherited
target, ABI, guard, return-validation, and callability fields.
It logs `event=lua-load-asset-package-invocation-descriptor-state` and still
reports `NativeInvoked=false`; descriptor construction is a handoff contract for
the future UE call site, not package resolution.
`GetLoadAssetPackageNativeExecutorState(path)` derives the descriptor into the
final executor boundary. It reports
`Source="loader-load-asset-package-native-executor-state"`,
`ExecutorKind="guarded-package-native-executor"`,
`TargetImage`,
`NativeExecutorConstructed=true`, `NativeExecutorDryRun=true`,
`NativeExecutorReady`, `ExecutorPreflightPassed`,
`FinalNativeCallEligible`, `NativeExecutorBlockReason`,
`FinalNativeCallBlocked=true`, and
`FinalNativeCallBlockReason="preflight-state-only"`. This state query remains a
dry-run executor preflight and reports `NativeInvoked=false`; the actual guarded
call is performed only by `InvokeLoadAssetPackageNative(path,{Invoke=true})`
after the same gate chain is callable. Post-canary readiness
exposes this as `luaLoadAssetPackageNativeExecutor` only when the executor row
reports `NativeExecutorReady=true`, `ExecutorPreflightPassed=true`, and
`FinalNativeCallEligible=true`; a dry-run shape row with those fields false is
kept as diagnostic evidence but does not satisfy the UE4SS package-loading
runtime gate.
The same runtime gate now also requires
`luaLoadAssetPackageNativeInvocation=true`, which only passes after a guarded
`lua-load-asset-package-native-invoke` row reports `nativeInvoked=true`,
`nativeCallable=true`, `targetImage=true`, and `nativeReturnValidated=true`.
Executor readiness is therefore preflight proof, not package-load completion.
`scripts/plan-ue4ss-canary-env.py --max-stage lua-dispatch` now emits this
canary path directly when the invocation gate is missing. By default it keeps
`*_ALLOW_LOAD_ASSET_PACKAGE_INVOKE=false` and
`*_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL=false`; after reviewing target-image
executor evidence, package ABI evidence, `TCHAR` layout evidence, and the
package path, pass `--allow-load-asset-package-native-call`,
`--load-asset-package-native-script`, `--load-asset-package-path`,
`--load-asset-package-abi-evidence`,
`--load-asset-package-tchar-unit-bytes`, and
`--load-asset-package-tchar-evidence`. The generated env is platform-matched:
`DUNE_PROBE_LOADER_*` for Linux server, `DUNE_CLIENT_PROBE_*` for native Linux
client, and `DUNE_WIN_CLIENT_PROBE_*` for Proton/Windows.
`GetLoadAssetPackageCrashGuardState()` reports the platform crash-containment
contract for that native call. Linux targets report a POSIX
`sigaction` guard surface; Windows/Proton reports `windows-seh-recovery` when
compiled by the current clang/SEH path and `windows-veh` for nonrecoverable
fallback builds. Linux POSIX guard recovery is based on `siglongjmp`. The
clang/SEH Windows artifact reports `CrashGuardRecoverable=true` after a guarded
no-op self-test and keeps the package native-call crash guard unarmed until the
target-specific
`DUNE_WIN_CLIENT_PROBE_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD` env var is set.
Fallback Windows toolchains without SEH support can still pass the no-op VEH
self-test, but report `CrashGuardRecoverable=false` and cannot arm the package
native-call crash guard.
`GetLoadAssetPackageGuardedCallState()` enters the same guarded-call wrapper
with a local no-op self-test. It reports `GuardedCallAvailable`,
`GuardedCallExecuted`, `GuardedCallSucceeded`, `GuardedCallResult`,
`CrashCaptured`, and `NativeInvoked=false`. This proves the wrapper can run
without invoking UE package-loading code. The native adapter and native invoke
preflight also consume this check as `GuardedCallReady` and include the known
self-test result before they can become callable.
`GetLoadAssetPackageReturnValidationState()` validates the seeded self-test
object through the Lua registry and mapped/readable memory checks. It can also
validate a specific future return candidate with
`GetLoadAssetPackageReturnValidationState(objectOrAddress, expectedClass)`,
reporting `CandidateAddress`, `Address`, `ExpectedClass`, `RegistryHit`,
`Mapped`, `Readable`, and `ClassMatch`. That makes the return validator ready
for a real native result without invoking UE package loading.
Readiness exposes this as `luaLoadAssetPackageNativeInvoke`; it still does not
prove real package loading by itself. Mods can run the package path with
`LoadAsset(path, {Backend="package"})`, `{Package=true}`, or
`{TryPackage=true}`. Unknown registry assets also take that path when
`DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN=1` or
`DUNE_WIN_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN=1` is set on clients, or when
`DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN=1` is set on the Linux server.
The loaders log `event=lua-load-asset-package-preflight`, count
`loadAssetPackagePreflightCalls` and `loadAssetPackageGateHits`, and include the
selected package-load target, target-image verdict, mapped/readable/executable
state, platform ABI, invoke flag, ABI/TCHAR/call-frame verdicts, and native-call
guard fields on Linux server, native Linux client, and Windows/Proton client
loaders. The row reports `status=native-bridge-missing` until the executor gate
is ready. When executor readiness and return validation pass and the requested
path already has a validated UObject handle, `LoadAsset` returns that handle
through the package branch, increments
`loadAssetPackageCalls`/`loadAssetPackageHits`/`loadAssetPackageExecutorHits`,
and emits `loadAssetBackend=package` in the finish row. Readiness reports the
preflight step as `luaLoadAssetPackagePreflight` and the returned package path
as `luaLoadAssetPackage`.
The backing registry currently contains loader
self-test handles, class-mapped `ue-uobject` candidates, bounded object-array
candidates, and loader-owned synthetic objects. It is an API-compatible staging
point for a real `GUObjectArray` backend, not full global UObject enumeration
yet.

Every returned object/function handle now carries UE4SS-style methods:
`GetFullName`, `GetName`, `GetPathName`, `GetAddress`, `IsValid`, `GetClass`,
`GetOuter`, `GetWorld`, `GetFName`, `type`, `IsClass`, `IsAnyClass`, `IsA`,
`HasAllFlags`, `HasAnyFlags`, `HasAnyInternalFlags`, `GetPropertyValue`,
`SetPropertyValue`, `CallFunction`, `ProcessConsoleExec`, `ULocalPlayerExec`,
`GetFunctionFlags`, `SetFunctionFlags`, `GetSuperStruct`, `GetSuper`,
`GetSuperClass`, `ForEachFunction`, `ForEachProperty`, `GetCDO`,
`GetDefaultObject`, `GetDefaultObj`, `IsChildOf`, and `GetLevel`. These methods are
equal across native Linux, Linux server, and Windows/Proton loaders. Handles
also expose `ClassAddress`, `OuterAddress`, `SuperAddress`, `ObjectFlags`,
`InternalIndex`, `HasObjectMetadata`, `InternalFlags`, `HasInternalFlags`,
`FunctionFlags`, and `HasFunctionFlags` when scan metadata is available.
`GetClass` returns a `UClass` handle named from the
registry `ClassName`; its `Address` is the live scanned `ClassPrivate` pointer
when available and zero for purely synthetic registry entries. `GetOuter`
resolves the loader-owned outer for synthetic objects created by
`StaticConstructObject` and otherwise returns `nil`; `GetSuperStruct`, `GetSuper`, and `GetSuperClass` prefer a
scanned `SuperAddress` and otherwise returns a synthetic `UObject` class for
non-`UObject` synthetic `UClass` handles or `nil`; `GetWorld` returns the
handle itself for registered world-like handles, resolves loader-owned
`OuterAddress` chains to a registered world, and can fall back to a registered
`GWorld`/`UWorld`-like handle for common world-context classes. It is not a
live engine `UObject::GetWorld` call yet. The global `GetWorld()` helper uses
the same registered world-like handle resolution, and the global `GetEngine()`
helper returns a discovered engine-like handle or a single loader-owned `UEngine`
handle when no live `GEngine` surface has been promoted yet.
After Lua mod dispatch, loaders emit `lua-global-runtime-helper-check` with
`globalWorldPromoted` and `globalEnginePromoted` so canaries can distinguish
loader-owned fallback handles from handles promoted out of UE object discovery.
`GetCDO`, `GetDefaultObject`, and `GetDefaultObj` return a loader-owned
`Default__<Class>` handle for `UClass` handles with `RF_ClassDefaultObject`
set; it is not the live engine class-default object yet. `GetLevel` returns a
registered level-like handle for level objects and loader-owned outer chains;
it is not a live `AActor::GetLevel` call yet;
`IsChildOf` is truthful for loader-owned self/base-class checks and walks the
bounded scan-derived `SuperAddress` chain when both class handles carry live
addresses; it is not full `GUObjectArray`-backed hierarchy enumeration yet.
`ProcessConsoleExec` dispatches loader-owned
`RegisterProcessConsoleExecPreHook` callbacks, then
`RegisterConsoleCommandHandler`/`RegisterConsoleCommandGlobalHandler`
callbacks, then `RegisterProcessConsoleExecPostHook` callbacks. Console exec
hooks receive `(context, rawCommand, command, args, handled)` and may return
boolean true to mark the command handled. Console command handlers receive the
UE4SS-shaped `(fullCommand, parameters, outputDevice)` tuple first, with
loader context compatibility appended as
`(context, command, args)`. `parameters[0]` is the command token,
`parameters[1..n]` are whitespace-split arguments, and `parameters.RawArgs`
keeps the unsplit tail. The output device exposes `Log`, `Serialize`, `Write`,
`GetOutput`, `ToString`, and `Clear` methods, increments `WriteCount`, and
records the last loader-handled message; it is not backed by the live engine
`FOutputDevice` yet. It does not hook live engine console routing yet;
`ULocalPlayerExec` dispatches loader-owned
`RegisterULocalPlayerExecPreHook` callbacks and
`RegisterULocalPlayerExecPostHook` callbacks with the same
`(context, rawCommand, command, args, handled)` shape. It is a distinct
loader-owned dispatcher and does not hook live `ULocalPlayer::Exec` yet;
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
`replacement, true` to short-circuit or replace the result. `ProcessEvent` is
now exposed as both a global `ProcessEvent(object, functionOrName[, args])` and
a UObject method `object:ProcessEvent(functionOrName[, args])`; today it routes
through the same hook-aware bounded call shim as `CallFunction`, so loaded mods
can use the UE-shaped call surface before the live native bridge is armed. It
does not invoke the live engine `UObject::ProcessEvent` or
`UObject::CallFunctionByNameWithArguments` paths yet;
`lua-mod-finish` reports `processEventCompatCalls` and
`processEventCompatHits`; the smoke mods require two calls and two hits, proving
both the global and UObject-method compatibility routes. Summary output exposes
that as `luaProcessEventCompatModFinishCount`, and
`scripts/ue4ss-port-readiness.py` keeps `luaProcessEventCompat` and aggregate
`luaDispatch` false until at least one loaded mod proves the route;
`GetProcessEventBridgeState()` returns a loader-owned state table with
`LiveHookInstalled`, `LiveLuaDispatchEnabled`, `DispatchCallbackCount`,
`LiveHookTarget`, `Trampoline`, `OriginalCallable`, `NativeBridgeArmed`,
`LiveCalls`, `OriginalCalls`, and `Source`. This is bridge introspection, not
permission to call arbitrary native `ProcessEvent`; `lua-mod-finish` reports
`processEventBridgeStateCalls`, summaries expose
`luaProcessEventBridgeStateModFinishCount`, and readiness keeps
`luaProcessEventBridgeState` plus aggregate `luaDispatch` false until a loaded
mod proves the state surface;
`RegisterModInitCallback`, `RegisterModPostInitCallback`, and
`RegisterModUnloadCallback` are loader-owned mod lifecycle callbacks fired after
all mod entrypoints load and before the Lua state is closed. They receive
`(nil, eventName, phase, handled)` for `ModInit`, `ModPostInit`, and
`ModUnload`; when live ProcessEvent Lua dispatch is enabled, enabled Lua mods
also load into the persistent live ProcessEvent Lua state, report
`lua-live-mod-start`/`lua-live-mod-finish`, dispatch `ModInit`/`ModPostInit`
when armed, remain registered for live hook dispatch, and dispatch `ModUnload`
when that live state closes.
`lua-mod-finish` reports per-family hook counts and call/handled totals for
loader-owned console exec, local-player exec, call-function, and mod lifecycle
callbacks, including `modInitCallbacks`, `modPostInitCallbacks`,
`modUnloadCallbacks`, `modInitCalls`, `modPostInitCalls`, `modUnloadCalls`,
`modInitHandled`, `modPostInitHandled`, and `modUnloadHandled`, so canary logs
can prove those paths without inspecting mod source;
loader-owned ids now represent active registrations and can be released through
`UnregisterKeyBind`, `UnregisterConsoleCommandHandler`, `UnregisterConsoleCommandGlobalHandler`,
`UnregisterCustomEvent`, lifecycle unregister functions, and
`UnregisterModUnloadCallback`, plus `UnregisterNotifyOnNewObject`;
unregistering compacts the active registrations
and releases the Lua registry ref on native Linux and Proton/Windows paths;
the full smoke path reports
`callbackUnregisterCalls=17 callbackUnregisterHits=17` for those UE4SS-style
callback families;
`HasAllFlags`/`HasAnyFlags` use promoted `ObjectFlags` for scanned UObject
candidates and keep conservative zero-flag behavior for synthetic-only handles;
`HasAnyInternalFlags` uses promoted `InternalFlags` when the object-array item
flags word is readable and returns false for handles without decoded internal
flag metadata;
`GetFunctionFlags` returns promoted `FunctionFlags` for scanned UFunction
handles when readable and `0` otherwise; `SetFunctionFlags` mutates
loader-owned Lua handle metadata and syncs matching loader registry entries,
but it does not write live UFunction memory.
`ForEachFunction` is no longer a pure no-op: on loader-owned self-test handles
and on scanned object/class handles whose address, `ClassAddress`, name, or
class matches a promoted UFunction owner, it iterates unique promoted
`UFunction` handles from the same bounded registry as `GetKnownFunctions`.
It is still not a complete live `UStruct` function-chain traversal. Loader logs expose this as
`forEachFunctionCalls` and `forEachFunctionCallbacks` on Lua dispatch/mod-finish
events plus `event=lua-function-iteration-check status=passed`; the readiness
report gates broad API coverage as `luaFunctionIteration` and non-self-test
owner/class iteration (`mode=owner`) as `luaFunctionIterationRuntime`.
`NotifyOnNewObject` is also bounded: it stores up to 32 class/path/name filter
registrations, then dispatches every match only when loader-owned
`StaticConstructObject` creates a matching synthetic handle. The readiness
report gates this as
`luaObjectNotify`.
Synthetic constructed-object outer preservation is gated as
`luaSyntheticOuter`.
`GetWorld`, `GetCDO`/`GetDefaultObject`/`GetDefaultObj`, and `GetLevel` compatibility are gated as
`luaWorldContext`, `luaClassDefaultObject`, and `luaLevel`.

`Reflection()` returns a loader-owned `UObjectReflection` table for known
handles. `Reflection():GetProperty(name)` resolves self-test properties,
promoted `UFunction` param descriptors, and scalar live reflection candidates
into UE4SS-style property descriptor tables. Descriptor methods include
`GetFullName`, `GetFName`, `IsA`, `GetClass`, `ContainerPtrToValuePtr`,
`ImportText`, `ExportText`, `ExportTextItem`, `GetOffset_Internal`,
`GetOffsetInternal`, `GetElementSize`, `GetSize`, `GetArrayDim`,
`GetPropertyFlags`, `HasAnyPropertyFlags`, `GetPropertyClass`, bool mask helpers, `GetStruct`, `GetInner`,
and `type`. The self-test descriptor set includes integer, bool, float, double,
`FName`, string, `FText`, object, and bounded array properties; readiness reports the
float/double proof as `luaReflectionNumericPropertyValues=true` and the
name/text proof as `luaReflectionNameTextPropertyValues=true`, and the
`FArrayProperty:GetInner()` proof as `luaReflectionArrayInnerProperty=true`,
and the `FEnumProperty:GetEnum()` / `GetUnderlyingProperty()` proof as
`luaReflectionEnumProperty=true`, and the `FSetProperty` element plus
`FMapProperty` key/value proof as `luaReflectionContainerProperties=true`.
`GetInner()` returns the bounded fixture's synthetic `FIntProperty` inner
descriptor. `GetEnum()` returns the bounded fixture's synthetic `UEnum` handle,
and `GetUnderlyingProperty()` returns its synthetic `FByteProperty` descriptor.
`GetElementProperty()` / `GetElementProp()` return the bounded fixture's
synthetic set element descriptor, while `GetKeyProperty()` / `GetKeyProp()` and
`GetValueProperty()` / `GetValueProp()` return synthetic map key/value
descriptors. `ImportText()` accepts text for loader-owned integer, bool,
float, double, enum, string, `FName`, and `FText` descriptors and is reported as
`luaReflectionImportText=true`. `ExportText()` and `ExportTextItem()` export
text from the same loader-owned descriptor set, including enum values, and are reported as
`luaReflectionExportText=true`. `GetOffset_Internal()`, `GetOffsetInternal()`,
`GetElementSize()`, `GetSize()`, `GetArrayDim()`, `GetPropertyFlags()`,
and `HasAnyPropertyFlags()` expose bounded descriptor metadata and are reported
as `luaReflectionPropertyMetadata=true`. `GetValue()` / `SetValue()` and the
shorthand `get()` / `set()` aliases provide bounded descriptor-level value
access for loader-owned descriptors and are reported as
`luaReflectionDescriptorValues=true`. Promoted scalar live reflection
descriptors also support guarded `GetValue()` and raw-set-enabled `SetValue()`
through the same mapped-memory checks used by global `GetPropertyValue` /
`SetPropertyValue`; that path is reported as
`luaReflectionLiveDescriptorValues=true`. Full Lua-dispatch readiness also
requires `luaReflectionLiveDescriptorTypedClassRuntime=true` and
`luaReflectionLiveDescriptorTypedValuesRuntime=true` and
`luaReflectionLiveDescriptorTypedSetValuesRuntime=true` and
`luaReflectionLiveDescriptorValuesRuntime=true`; if any of those are false, the
descriptor proof is still generic, missing decoded `FProperty` class identity,
missing typed `GetValue()` proof, or only touched loader-owned `SelfTest*`
fields. Typed live `GetValue()` currently covers guarded bool, float, double,
object/class/interface, FName, FString-shaped `FStrProperty`, FVector-sized
`FStructProperty`, and integer/byte/enum-sized values where the live descriptor
class and element size are known. With the raw-set gate enabled, live
`SetValue()` also supports the bounded scalar path, including byte/enum-sized
integer writes, plus FString-shaped
`FStrProperty` strings and FVector-sized `FStructProperty` tables.
`Object:ForEachProperty(callback)`, `Function:ForEachProperty(callback)`, and
`Reflection():ForEachProperty(callback)` iterate the same known descriptor sets
and stop when the callback returns true. The reflection-handle iterator is
reported as `luaReflectionForEachProperty=true`; Lua-dispatch readiness also
requires `luaReflectionForEachPropertyRuntime=true`, proving enumeration over a
promoted non-self-test descriptor. This is a bounded descriptor shim, not
complete live `FProperty` traversal, FText marshaling, arbitrary container
storage marshaling, or general struct field marshaling.

The Lua global compatibility surface also includes `FName`, `FText`,
`ExecuteInGameThread`, `DrainGameThreadQueue()`, `ExecuteAsync`,
`ExecuteWithDelay`, `LoopAsync`, `DrainSchedulerQueue()`,
`CancelScheduledCallback`, `RegisterKeyBind`,
`IsKeyBindRegistered`, `RegisterConsoleCommandHandler`,
`RegisterConsoleCommandGlobalHandler`, `RegisterProcessConsoleExecPreHook`,
`RegisterProcessConsoleExecPostHook`, `RegisterCustomEvent`,
`RegisterCustomProperty`, `RegisterCallFunctionByNameWithArgumentsPreHook`,
`RegisterCallFunctionByNameWithArgumentsPostHook`,
`RegisterULocalPlayerExecPreHook`, `RegisterULocalPlayerExecPostHook`,
`RegisterLocalPlayerExecPreHook`, `RegisterLocalPlayerExecPostHook`,
`ProcessEvent`,
`DuneProbeDispatchCustomEvent`, `DuneProbeLoadMap`, `DuneProbeBeginPlay`,
`DuneProbeInitGameState`, `DuneProbeDispatchKeyBind`,
`DuneProbeDispatchConsoleCommand`,
`IterateGameDirectories`, and common lifecycle hook
registration names. The
`ExecuteInGameThread` now stores callbacks in a bounded game-thread queue and
returns a queued id; `DrainGameThreadQueue()` drains that queue in smoke tests.
`ExecuteAsync`, `ExecuteWithDelay`, and `LoopAsync` store callbacks in a
bounded scheduler queue; `DrainSchedulerQueue()` drains it and
`CancelScheduledCallback` releases queued scheduler or game-thread callbacks
before dispatch. These queues are Lua-state-owned, so callbacks are only
drained, cancelled, or released by the Lua state that created them. When live
Lua `ProcessEvent` or `CallFunctionByNameWithArguments` dispatch is enabled,
the live ProcessEvent post-hook and live CallFunction post-hook pump the owning
game-thread queue and scheduler queue after post-hook callbacks, giving
`ExecuteInGameThread` a hook-driven Unreal-thread execution path instead of a
smoke-test-only manual drain.
loaders also seed `UE4SS`,
`UnrealVersion`, `ModRef`, `EObjectFlags`, `EInternalObjectFlags`,
`PropertyTypes`, `Key`, `ModifierKey`, and `ModifierKeys`. `ModRef`
implements loader-local shared variables for nil, string, integer, bool, and
known object handles. It also carries a per-mod `ModRef` context while an
entrypoint is executing: `Name`/`GetModName()`, `Path`/`GetModPath()`/`GetModDir()`,
`ScriptPath`/`GetModScriptPath()`, and `ScriptDir`/`GetModScriptDir()` are
refreshed from the active Lua script before `load_string`. Before executing a
mod entrypoint, the loaders prepend `ScriptDir/?.lua` and
`ScriptDir/?/init.lua` to `package.path`, so UE4SS-style split Lua mods can use
mod-local `require("file")` and nested `require("lib.file")`. Explicit sibling
loads should use `dofile(ModRef:GetModScriptDir() .. "/file.lua")`. These are
deterministic loader shims today: async/delay
callbacks run immediately, no-hook Lua mods load successfully, and loader-owned
custom-event/lifecycle shims dispatch registered Lua refs. No real engine event
is dispatched until the matching
Unreal callsite is resolved and hooked. `FName` returns a table with `ToString()`
and `GetComparisonIndex()` methods, matching the ProcessEvent decoded-name value
shape. `FName(index[, number])` and `DecodeFName(index[, number])` use the
active `FNamePool` resolver when a scan has proven one; returned tables carry
`Name`, `String`, `ComparisonIndex`, `Number`, and `IsDecoded`. Without a
resolver, the table is still returned with `IsDecoded=false`.
Confidence: high for the loader registry, moderate for live Dune object-array
candidates until current-build anchors are confirmed.

Set `DUNE_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=true` or
`DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=true` after the plain Lua
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
Confidence: high for native Linux with Lua present and for local Windows/Wine
Lua smoke, moderate until the same DLL path is tested with live Dune under
Proton.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=true` or
`DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=true` after a unique
`ProcessEvent` anchor exists. The probe resolves the hook target from
`*_UE_PROCESS_EVENT_HOOK_ADDRESS`, `*_UE_PROCESS_EVENT_ADDRESS`, explicit UE
anchors, or signature-resolved UE anchors. With `*_HOOK_INSTALL=false` it only
validates that the target is mapped and executable. With
`*_HOOK_INSTALL=true` it installs an inline hook and immediately restores it;
`*_HOOK_SELF_TEST_TARGET=true` confines that install/restore pass to
loader-owned code for smoke tests. This is a guarded hookability probe, not a
persistent live ProcessEvent dispatch loop. Readiness no longer treats
`selfTestTarget=false` alone as runtime-target proof; the hook target must also
match a target-image anchor/signature or carry explicit target provenance.
Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=true` or
`DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=true` after a unique
`CallFunctionByNameWithArguments` target exists. The probe resolves from
`*_UE_CALL_FUNCTION_HOOK_ADDRESS`, `*_UE_CALL_FUNCTION_ADDRESS`, explicit UE
anchors, or signature-resolved UE anchors, then validates mapping/executable
state. With `*_UE_CALL_FUNCTION_HOOK_INSTALL=true`, it installs and immediately
restores a `CallFunctionHookProbe` inline hook. This is a hookability gate for
the UE4SS command/function surface; it does not yet marshal or invoke real game
`CallFunctionByNameWithArguments` calls. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=true` or
`DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=true` only after the guarded
hook probe passes on the same resolved target. The live hook scaffold resolves
the target from `*_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS`, the hook-probe address,
the generic ProcessEvent address, explicit UE anchors, or signature-resolved UE
anchors. It installs once, leaves the hook active for the process lifetime,
calls the original through the trampoline, optionally logs bounded call
entries/returns, and restores on loader unload/process detach. It does not yet
decode live `UObject`/`UFunction` arguments or marshal live `FProperty`
payloads. The live-hook runtime-target gate follows the same anchor/provenance
rule and can also be satisfied by a sampled live ProcessEvent context whose
function resolves to a non-self-test runtime UFunction identity. Confidence:
high.

Set `DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=true` or
`DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=true` only after the guarded
CallFunction hook probe passes on the same resolved target. The live hook
scaffold resolves from `*_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS`, the hook-probe
address, the generic CallFunction address, explicit UE anchors, or
signature-resolved UE anchors. It installs once, calls the original through the
trampoline, optionally logs bounded call entries/returns, and restores on
loader unload/process detach. This is the persistent interception spine for
UE4SS command/function hooks; argument marshaling still requires runtime
`UObject`/command parsing evidence. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true` or
`DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true` with the live
hook scaffold in a smoke/lab run to arm a native ProcessEvent pre/post callback
registry. A passing self-test proves the persistent hook runs native callbacks
before and after the original function. It is the spine for live Lua routing,
not the Lua routing itself. Confidence: high.

Set `DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=true` or
`DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=true` with the live
hook scaffold after the native dispatch self-test passes. The loader creates a
persistent Lua VM for the live hook, executes a script that calls
`RegisterHook`, stores the Lua pre/post refs, and invokes those callbacks from
the persistent ProcessEvent hook around the original call. The callback receives
a table with raw `object`, `function`, and `params` addresses plus `stage`,
`call`, `originalCalled`, `preCallbacks`, and `postCallbacks`; when the loader
can resolve the raw addresses, the same table also includes UE4SS-shaped
`Object` and `Function` handle tables plus a `Params` context table. A pass logs
`event=ue-process-event-live-lua-dispatch status=armed` and the hook install
line reports `luaDispatch=true luaObjectHandleHits=2
luaFunctionHandleHits=2 luaParamsHandleHits=2 luaParamDescriptorHits=2
luaParamDescriptorLookupHits=12 luaFunctionParamDescriptorHits=2
luaParamGetHits=18 luaParamSetHits=6`.
The same descriptor accessors are now also tested outside callbacks with
`CreateProcessEventParams(function)`, which constructs a bounded loader-owned
`ProcessEventParams` handle and verifies `SetParamValue`, `GetParamValue`, and
direct field shorthand access against that buffer on Linux client, Linux
server, and Windows/Proton.
The native invoke API also returns descriptor preflight evidence before any
non-self-test call is made: `DescriptorBackedCallable`,
`ParamsBufferConstructible`, `ParamsDescriptorCount`, `ParamsBufferSize`,
`InvokeRequested`, and `NativeNonSelfTestEnabled`. `descriptor-preflight-ready`
means the registered object, promoted function descriptors, armed bridge, and
params buffer are all present; it is still a no-call state. `{Invoke=true}`
with the target-specific opt-in env unset is counted by summaries as
`luaProcessEventNativeInvokeNonSelfTestGateCount`; with the env set it advances
to `non-self-test-invoked` after seeding descriptor-backed params and calling
the original trampoline.
The readiness gate also requires the armed live Lua dispatch to carry multiple
`RegisterHook` entries and the close-out line to report the matching callback
results `preResult=11` and `postResult=31`, proving the non-target hook did not
satisfy routing. Current native Linux client, Linux server, and Windows/Proton
smokes register both an exact `/Script/SelfTestUObject.SelfTestUObjectName_0:Function`
hook and an alias-owner hook with the same terminal function name; the close-out
line must now show nonzero `pathExactMatches` and `pathAliasMatches`. This makes
`ueProcessEventLuaHookRouting=true` and
`ueProcessEventLuaHookAliasRouting=true` independent readiness checks rather
than alias-only evidence. `GetFunctionParamDescriptors`/
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
plumbing. When the synthetic function path is known, dispatch filters
registered hooks by `ctx.functionPath`; exact path matches are counted as
`pathExactMatches`, and terminal function-name fallback matches are counted as
`pathAliasMatches`. The built-in live Lua dispatch self-test registers its
target hook through an alternate `/Script/...` owner with the same terminal
UFunction name, so a passing canary proves terminal-name alias routing instead
of only exact path routing. Unresolved live `UFunction` paths remain permissive
until real path/name discovery is proven. Bounded live samples now emit
`event=ue-process-event-live-param` for descriptor-backed scalar, bool,
object-pointer, `FName`, `FString`, and vector reads from the active params
block. For arrays it emits `status=container` and Lua `GetParamValue` returns
an `FScriptArray` table with `Data`, `Num`, `Max`, `BytesHex`, address, offset,
class, type, and size metadata. If the array data pointer is readable, the
table also includes `DataSampleAddress`, `DataSampleReadSize`, and
`DataSampleBytesHex`, and the log value includes `dataSampleHex=...`.
`FScriptArray` tables expose `GetNum()`, `NumElements()`, `GetData()`,
`GetDataSampleBytes()`, `GetRawElement(index, byteCount)`, and
`GetElement(index)`. They also expose UE4SS-style `TArray:Empty()`, implemented
as a safe logical empty on the Lua/container handle by setting `Num` to zero;
it does not free or rewrite target allocator storage. `GetElement` uses
promoted `Inner*` metadata when present to decode bounded scalar, object,
`FName`, `FString`/`FText`, and `FVector` elements;
unsupported element classes return a raw element table with `BytesHex`. For sets and maps it emits
`FScriptSetHeader` and `FScriptMapHeader` tables with `GetNum()`,
`NumElements()`, `GetData()`, and bounded raw reads. Sets expose
UE4SS-style `Add(element)`, `Remove(element)`, `Contains(element)`,
`ForEach(callback)`, and `Empty()`, plus
`GetRawEntry(index, byteCount)`, `GetRawElement(index, byteCount)`,
`GetElement(index)`, `Get(index)`, and `get(index)`. Maps expose
UE4SS-style `Add(key, value)`, `Remove(key)`, `Contains(key)`, `Find(key)`,
`ForEach(callback)`, and `Empty()`, plus `GetRawPair(index, byteCount)`, `GetRawElement(index, byteCount)`,
`GetPair(index)`, `Get(index)`, `get(index)`, `GetKey(index)`, and
`GetValue(index)`. `Empty()` is a logical handle empty, matching the TArray
implementation; it does not free or rewrite target allocator storage.
`Add()` and `Remove()` are guarded dense scalar writable backing storage
mutations: they require descriptor-backed dense layout, supported scalar
key/value sizes, writable `Data`, and spare `Max` capacity for adds; removals
compact entries and update the handle `Num`. Real UE set/map allocator and hash mutation is not proven yet. Promoted set headers
include `Element*` metadata, and promoted map headers include `Key*` and
`Value*` metadata. `GetElement(index)`, `GetPair(index)`, `GetKey(index)`, and `GetValue(index)` use that metadata
to decode bounded scalar, object, `FName`, `FString`/`FText`, and `FVector` values for descriptor-backed dense storage,
falling back to raw element tables for unsupported classes.
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
`event=ue-function-param-container-child` when a live `FArrayProperty`,
`FSetProperty`, or `FMapProperty` param has decoded inner/key/value child
metadata; `GetFunctionParams(function).Properties.<Param>` and
`RemoteUnrealParam.Descriptor` expose that metadata through `ContainerChildren`
and the same child-property getter methods. Raw `byteCount` stays
caller-supplied, and live-build `FScriptSet`/`FScriptMap` sparse slot layout
still needs validation before treating every slot as a typed occupied element.
Unsupported complex values,
including non-vector structs, still emit
`status=raw value=rawHex=...` and Lua returns a `RawUnrealParam` table. This
still does not perform complete arbitrary container element unmarshaling or
complete live `FProperty` object marshaling. Windows/Proton
additionally requires a staged Lua DLL or the event reports
`status=library-missing`.
When bounded call logging is enabled, the hook also emits
`event=ue-process-event-live-context`. `status=resolved` proves that a sampled
live call had a nonzero params pointer, a Lua-visible object handle for the raw
object pointer, a runtime-provenance `UFunction` path plus runtime function
path, and promoted function-param descriptors for the raw function pointer.
Self-test provenance remains logged as `status=partial` and does not satisfy
native runtime identity. The same sample emits
`event=ue-process-event-live-registry-context` with
`objectNativeIdentity=true` and `functionNativeIdentity=true` only when both raw
pointers resolve through promoted Lua-visible registries with runtime
provenance; readiness exposes this as `ueProcessEventLiveRegistryContext`.
New loader builds also include
`functionProvenance=runtime|self-test` on both context lines; readiness prefers
that explicit field and falls back to path heuristics only for older logs. A
separate set of runtime-only registry gates now splits self-test registry
records from real process evidence:
`luaObjectRegistryRuntime`, `luaFunctionRegistryRuntime`,
`luaDecodedObjectAliasesRuntime`, and `ueObjectArrayRegistryRuntime`. The broad
registry gates can still pass on loader-owned `SelfTest*` records, but
`objectDiscovery`, `reflection`, and `luaDispatch` require the runtime variants
before the port is treated as live-compatible.
Current loader builds append `registryProvenance=runtime|self-test` to
`lua-object-registry`, `lua-object-registry-check`,
`lua-function-registry-check`, and `lua-function-iteration-check` lines.
Readiness prefers that explicit field and falls back to name/path heuristics
only for older logs. Confidence: high.
`scripts/plan-ue4ss-canary-env.py --format json` now includes a
`registryRuntimeEvidenceContract` and `processEventRuntimeEvidenceContract` in
`nextCanaryContract`. The generated `post-canary-verify.sh` summary repeats the
same rule: registry rows need `registryProvenance=runtime`, live ProcessEvent
context rows need `functionProvenance=runtime`, and hook target rows need
`selfTestTarget=false callSelfTest=false` before escalation. The ProcessEvent
contract also lists the active-validation row required for the strict parity
gate: `event=ue-process-event-active-validate status=invoked
targetEntry=true` with positive `liveCallsDelta` and `originalCallsDelta`.
Confidence: high.
`scripts/ue4ss-port-readiness.py` also emits `perLoaderReadiness` in JSON and a
`Per Loader Readiness` section in Markdown. Use that matrix when comparing
native Linux client, Linux server, and Windows/Proton logs: aggregate readiness
can show that some target proved a surface, but the per-loader rows show whether
each target independently proved runtime context, exact hook routing, alias
routing, reflection, Lua dispatch, `liveTargetImageCanary`, and
`ue4ssLuaApiComplete`. Each per-loader JSON entry also carries its own
`liveTargetImageCanaryContract`, so automation can reject a Linux or
Windows/Proton target independently even when another target in the same report
is complete. Confidence: high.
The canary planner also emits
`postCanaryVerification.crossPlatformStrictRuntimeContract`. That contract is
separate from the per-platform strict verifier: a single server, native Linux
client, or Proton/Windows canary can pass its own strict runtime contract, but
the cross-platform contract remains false until `server`, `linux-client`, and
`windows` all have per-loader readiness entries and all three live target-image
contracts are ready. Confidence: high.
The contract also includes `callFunctionRuntimeEvidenceContract`; CallFunction
hook probe/live-hook rows need the same non-self-test fields, and
`ue-call-function-live-hook` must report `luaDispatch=true` before
`RegisterCallFunctionByNameWithArgumentsPreHook/PostHook` parity is treated as
runtime-backed. The same contract now carries the active-validation row required
for strict parity: `event=ue-call-function-active-validate status=invoked
targetEntry=true` with positive `liveCallsDelta` and `originalCallsDelta`.
Confidence: high.
A readable
`ue-process-event-live-param` line is the readiness gate between raw hook
dispatch and live Lua/mod routing with descriptor-backed payload access only
when the sampled context also has runtime `functionProvenance` evidence. The
readiness report also tracks `ueProcessEventLiveFunctionPath`; `false` means
the sampled live function path has not matched a decoded scanned UFunction path
from the read-only descriptor probe. The readiness report also tracks
`ueProcessEventLiveClassAwareParamValues`; `false` means the sampled live Lua
callback has not yet resolved a runtime-proven `ctx.Function` through the
promoted UFunction registry and proven descriptor-backed
`GetParamValue`/`SetParamValue` against the active params pointer. The
readiness report also tracks
`ueProcessEventLiveContainerParamValues`; `false`
means no sampled live array/set/map param produced a typed header table yet.
It now splits that evidence into
`ueProcessEventLiveArrayContainerParamValues`,
`ueProcessEventLiveSetContainerParamValues`,
`ueProcessEventLiveMapContainerParamValues`, and
`ueProcessEventLiveSetMapContainerParamValues`, so array-only canaries no
longer imply set/map coverage. The built-in ProcessEvent self-test emits
loader-owned `NumberArray`, `NumberSet`, and `NumberMap` live-param samples on
native Linux, Linux server, and Windows/Proton, so local smokes exercise the
same readiness split before a live Dune canary. It also tracks
`ueProcessEventLiveContainerDataSamples`; `false` means no sampled live array
header had a readable data pointer for bounded storage bytes.
Confidence: high.
Confidence: high for native Linux and local Windows/Wine Lua smoke, moderate
until a live Dune Proton Lua canary passes.

`lua-mod-script status=passed` proves the loader can discover and execute a Lua
entrypoint from either an explicit script list or a UE4SS-style
`Mods/<ModName>/Scripts/main.lua` root. `lua-mod-dispatch-self-test
status=passed` proves callbacks registered by that loaded mod entrypoint can be
invoked from native code. `RegisterHook` is a bounded multi-callback registry
on the Linux server, native Linux client, and Windows/Proton client loaders, so
multiple loaded scripts can register callbacks without overwriting each other.
The active script also sees per-mod `ModRef` context through `GetModName()`,
`GetModPath()`, `GetModDir()`, `GetModScriptPath()`, and
`GetModScriptDir()`. The Linux client, Linux server, and Wine real-Lua smokes
now prove mod-local `require()` and explicit `dofile()` from that script
directory. This is still a loader-level dispatch proof; it is not yet a live
`ProcessEvent` bridge. Confidence: high.

Root-discovered mods now honor a UE4SS-style `mods.txt` file on all three
loaders. Blank lines and `#` comments are ignored; `ModName` and `+ModName`
load that mod in file order, while `-ModName` or `!ModName` marks it disabled.
Unlisted root mods are appended after manifest-listed entries. `lua-mod-start`
logs `manifestEntries` and `manifestDisabled` so a canary can prove the loader
honored the order/disabled set. Confidence: high.

If a Lua mod entrypoint fails to load or execute, `event=lua-mod-script` logs a
sanitized `error=` field on all three loaders. Script reads remain capped at 256
KiB, and the loader does not print arbitrary binary data from the Lua stack.

Export explicit anchor env from a first scan:

```bash
scripts/export-ue-anchor-env.py /tmp/dune-win-client-probe-loader.log \
  --loader win-client \
  --platform windows \
  > build/windows-client-loader/ue-anchors.env

# After reviewing runtimeDiscovery.candidateLocations, export unique runtime
# root candidates or a specific ambiguous candidate by offset for a second
# read-only validation pass:
scripts/export-ue-anchor-env.py /tmp/dune-win-client-probe-loader.log \
  --loader win-client \
  --platform windows \
  --include-runtime-candidates \
  > build/windows-client-loader/ue-runtime-root-candidates.env
scripts/export-ue-anchor-env.py /tmp/dune-win-client-probe-loader.log \
  --loader win-client \
  --platform windows \
  --runtime-candidate FNamePool=0x60000 \
  > build/windows-client-loader/ue-reviewed-runtime-root.env

scripts/prepare-ue-anchor-canary.py \
  --platform windows \
  --binary /path/to/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --include-runtime-candidates \
  --output-dir build/windows-client-loader/client-anchor-canary

# For ambiguous roots, pass reviewed candidate offsets instead of exporting
# every runtime candidate:
scripts/prepare-ue-anchor-canary.py \
  --platform windows \
  --binary /path/to/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --runtime-candidate FNamePool=0x60000 \
  --output-dir build/windows-client-loader/client-anchor-canary-reviewed

The same runtime-candidate flags are supported for native Linux and server
canaries; use `--platform linux-client --loader client` with
`/tmp/dune-client-probe-loader.log`, or `--platform server --loader server` with
`/tmp/dune-server-probe-loader.log`.

scripts/plan-ue4ss-canary-env.py \
  --platform windows \
  --client-log /tmp/dune-win-client-probe-loader.log \
  --loader win-client \
  --hook-targets-json build/windows-client-loader/selected-hook-targets.json \
  --max-stage read-only \
  --format json \
  > build/windows-client-loader/next-canary.json

scripts/plan-ue4ss-canary-env.py \
  --platform windows \
  --client-log /tmp/dune-win-client-probe-loader.log \
  --loader win-client \
  --process-event-rva 0x50000 \
  --max-stage read-only \
  > build/windows-client-loader/next-canary.env
```

By default this exports core discovery anchors plus reflection anchors
(`UObject`, `UFunction`, `UClass`, `FProperty`) only from mapped explicit
anchors or resolved `ue-anchor-signature` records. Raw `scan-hit` rows are
candidate evidence for xref/signature promotion, not explicit anchor addresses;
use `--include-scan-hits` only for a documented manual exception. Missing or
ambiguous signature anchors stay out of the env file.
The standard readiness report uses the same conservative rule for core-anchor
gates: `ue-names`, `ue-objects`, `ue-world`, `ue-dispatch`, and
`ue-reflection-surface` require mapped `ue-anchor` or resolved
`ue-anchor-signature` evidence. Plain string/signature `scan-hit` rows keep the
workflow in xref/signature-promotion mode. Confidence: high.
Mapped explicit anchors and resolved/missing/ambiguous `ue-anchor-signature`
records include a loader-normalized `group=` field: `names`, `objects`,
`world`, `dispatch`, `package`, `reflection`, `cheat`, `brt`, `deep-desert`,
`self-test`, or `unknown`. `package` covers read-only package-loading
candidates such as `StaticLoadObject`, `StaticLoadClass`, `LoadObject`, `LoadPackage`, and
`ResolveName`. `SelfTest*` anchors deliberately report `self-test`, so local
smoke evidence cannot masquerade as live anchor readiness. Confidence: high.
The scan summaries preserve these maps as `ueAnchorGroupCounts`,
`mappedUeAnchorGroupCounts`, `ueAnchorSignatureGroupCounts`, and
`resolvedUeAnchorSignatureGroupCounts`. The shared readiness report exposes the
merged view as `anchorGroups` and gates old or malformed logs as
`anchorGroupProvenance=false` when any anchor evidence lacks `group=`.
Confidence: high.
The canary-prep helper writes the PE manifest, anchor-signature sidecar, anchor
env, validation summary, Markdown/JSON readiness reports, and runtime coverage
sidecars into one directory for the next Proton/Windows launch. The generated
anchor env includes the platform-specific `*_UE_ANCHOR_SIGNATURES_FILE` value
pointing at the sidecar, so a second-pass canary can promote unique signature
matches without manual env stitching. It also writes `anchor-coverage.json`,
`object-discovery-coverage.json`, `post-canary-verify.sh`, and a README
summary. `anchor-coverage.json`
marks whether combined explicit and signature-promotable anchors cover the
names, objects, world, dispatch, and reflection groups required before object
discovery or hook planning. When runtime root candidate export is enabled, it
also reports `runtimeCandidateAnchorCount`, lists
`runtimeCandidateAnchors`, and marks affected anchor rows with
`runtime-candidate` in `sources`. `object-discovery-coverage.json` preserves the
readiness report's component-level promotion evidence, including which runtime
object registry, decoded alias, object-array, native identity, internal flag,
FName decoder, outer-chain, or Lua FindObject requirements are still missing.
After the next canary, run `post-canary-verify.sh [loader-log]` from that output
directory to rebuild `ue4ss-readiness.json`,
`object-discovery-coverage.json`, `ue4ss-port-gaps.json`,
`ue4ss-port-gaps.md`, `ue4ss-evidence-inventory.md`, and
`post-canary-summary.md` from the collected log and sidecars. The evidence
inventory is generated by `summarize-ue4ss-evidence-inventory.py` and ranks
which saved canary directory is currently closest to target-image anchor
closure. Strict server or client verification requires that inventory step:
`DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true` and
`verify-client-probe-canary.sh --strict` both require
`ue4ss-evidence-inventory.json` and `ue4ss-evidence-inventory.md` to be
generated with `--require-complete`, rather than treating missing or incomplete
inventory as best-effort. The bundle also writes
the injected runtime candidate anchors, the subset promoted by
`runtimeDiscovery.promotedNames`, and any candidate roots still missing, so the
post-canary report can distinguish "candidate was exported" from "candidate was
accepted as a live runtime root." The bundle also writes
`post-canary-verify-strict.sh`, which sets
`DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true` before running the same verifier. Use
strict mode only when the canary is expected to prove UE4SS-runtime readiness;
it exits nonzero while runtime object/function registry, non-self-test hook
target, live ProcessEvent context, live CallFunction Lua dispatch, or live
reflection descriptor gates are still false. Strict mode also requires
same-build signature validation to pass both exact and promotable checks, and
requires anchor coverage to prove object-discovery and hook-planning readiness.
The verifier treats either current `ready` booleans or passed readiness `gates`
as evidence, so older gate-only readiness JSON is evaluated consistently with
the planner.
Confidence: high.
For the Linux server canary wrapper, the prepared bundle can be handed directly
to the guarded one-map runner:

```bash
DUNE_LINUX_SERVER_CANARY_PREP_DIR=backups/ue-anchor-canary/<bundle> \
DUNE_LINUX_SERVER_CANARY_SERVICE=deep-desert \
DUNE_LINUX_SERVER_CANARY_PARTITION=8 \
DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader-dd1.log \
scripts/canary-linux-server-loader.sh .env
```

The wrapper validates `ue-server-anchors.env` and the post-canary verifier
before any env mutation or restart, applies the prepared anchor/signature env
only for the canary window, captures the loader log, runs the bundle verifier,
and copies `ue4ss-readiness.json`, `object-discovery-coverage.json`,
`post-canary-summary.md`, and UE4SS gap summaries into the canary backup
directory. Set `DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true` only when that run
is expected to satisfy the full live target-image contract.
Confidence: high.
Candidate-shape promotion is intentionally stricter now. In
`scripts/summarize-ue-candidate-shapes.py`, a `promotable-object-array`
verdict requires candidate-specific runtime evidence: registered object-array
items, decoded FName aliases that match the candidate label, runtime
Lua/object-registry provenance from the object-array path, and promoted native
identity evidence tied to the same array name. A plausible header plus decoded
names without that runtime registry/native-identity proof is only
`promising-object-array`. Confidence: high.
Validated gameplay signatures are not the same thing as UE anchor coverage.
BRT, cheat, cap, or similar manifests can be fully promotable and still provide
`0` UE anchor signature entries. In that state the canary prep README reports
the manifest categories and explicitly marks UE anchor signature coverage as
none; continue read-only anchor discovery until rows map to core anchors such as
`FNamePool`, `GUObjectArray`, `GWorld`/`GEngine`, `ProcessEvent`, and
`CallFunctionByNameWithArguments`. Confidence: high.
When a scan/xref pass has UE-category non-string candidates, promote them
before validation:

```bash
scripts/summarize-client-loader-xrefs.py /path/to/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category ue \
  --format json > build/windows-client-loader/ue-anchor-xrefs.json

scripts/promote-ue-anchor-xref-candidates.py \
  build/windows-client-loader/ue-anchor-xrefs.json \
  --require-target-source \
  --format json > build/windows-client-loader/ue-anchor-candidates.json

scripts/validate-client-pe-signatures.py /path/to/DuneSandbox-Win64-Shipping.exe \
  --xref-json build/windows-client-loader/ue-anchor-candidates.json \
  --category ue \
  --format json > build/windows-client-loader/ue-anchor-signature-validation.json
```

The promotion step is deliberately conservative: it rejects non-UE categories
and string targets by default, because a reference to the literal text
`FNamePool` is not proof of the global `FNamePool` anchor. Use
`--allow-string-targets` only for a documented manual exception. Confidence:
high.
The canary env planner reads readiness evidence and emits the next guarded env:
read-only object/reflection discovery by default. It re-checks proven anchor
provenance before escalation, independent of the upstream readiness builder: if
a readiness JSON lacks `anchorGroupProvenance=true`, claims object discovery
without proven names/objects/world anchor groups, or claims hook-capable stages
without a proven dispatch anchor, the plan stays in read-only object/reflection
discovery and does not emit ProcessEvent hook or Lua dispatch variables.
JSON/Markdown output includes
machine-readable `blockers[]` entries with stable `code`, blocked `stage`, and
message fields for automation. When the readiness report includes prepared
anchor coverage, it keeps the plan in read-only discovery or reflection until
required object-discovery groups and ProcessEvent-level dispatch coverage are
present. It also keeps the plan in read-only discovery while
`findObjectSemantics=false`, because hook work needs registry-backed object
identity, object-array, outer-chain, and Lua object API evidence first. Guarded
ProcessEvent install/restore is emitted
only with `--max-stage hook-probe`, persistent hook scaffolding only with
`--max-stage live-hook`, and live Lua/mod dispatch only with `--max-stage
lua-dispatch`. `live-hook` and `lua-dispatch` plans also enable bounded live
ProcessEvent call logging so `ue-process-event-live-context` readiness evidence
is collected in the same canary. The planner also re-checks
`ueProcessEventHookRuntimeTarget`, `ueProcessEventLiveHookRuntimeTarget`,
`ueProcessEventLiveRuntimeContext`, and
`ueProcessEventLiveRuntimeRegistryContext`: self-test-only or older readiness
evidence stays at hook-probe/live-hook and does not emit live Lua dispatch.
`nextCanaryContract.processEventRuntimeEvidence` records those booleans for
automation. The planner also requires
`luaObjectRegistryRuntime`, `luaFunctionRegistryRuntime`,
`luaDecodedObjectAliasesRuntime`, `ueObjectArrayRegistryRuntime`, and
`luaFunctionIterationRuntime`; missing or self-test-only registry/function
iteration evidence keeps the plan at object-discovery/reflection/Lua-dispatch
and is recorded in `nextCanaryContract.registryRuntimeEvidence`. Pass
`--anchor-signatures-file <client-anchor-signatures.txt>` to carry a generated
signature sidecar into the next read-only canary; the planner emits the matching
`*_UE_ANCHOR_SIGNATURES_FILE` variable and skips empty `*_UE_ANCHORS` values
when no explicit anchors were resolved yet. The planner will not emit
live Lua dispatch flags until the readiness report already proves the persistent
ProcessEvent hook and native dispatch self-test. JSON/Markdown output also
includes `nextCanaryContract`, a machine-readable summary of required
names/objects/world/dispatch/reflection anchor groups, missing groups, signature
validation status, `anchorGroupProvenance`, object-discovery coverage,
ProcessEvent runtime evidence, registry runtime evidence, and the env names to
apply in the next run. The contract also includes `postCanaryVerification`,
which records the platform-specific default loader log, readiness command,
required sidecars, and expected `ue4ss-readiness.json` plus
`object-discovery-coverage.json` outputs for closing the canary loop. It also
includes `strictRuntimeContract`, the `DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true`
verifier setting, gate-aware per-key runtime/signature/anchor readiness,
required runtime and signature/anchor readiness keys, and any missing keys.
`strictRuntimeContract.contractReady` is true only when both
`runtimeReady` and `signatureAnchorReady` are true; missing runtime keys are
reported under `missingReadyKeys`, while missing exact/promotable signature or
anchor coverage keys are reported under `missingSignatureAnchorReadyKeys`.
Runtime readiness explicitly requires both `targetImageProcess=true` and
`runtimeRootDiscovery=true`, so a strict post-canary pass cannot be based on
helper-process logs or hook/Lua evidence that never promoted live `FNamePool` /
`GUObjectArray` roots in the target image.
It also requires `ueProcessEventActiveValidation` and
`ueCallFunctionActiveValidation`; installed hooks and armed Lua callbacks do not
prove full dispatch until an explicitly allowed active validation call reaches
both the hook and original trampoline.
Signature/anchor readiness includes `anchorCoveragePackageLoading` and
`targetPackageLoadingSurface`, so strict post-canary verification cannot ignore
the target-image package-loading anchors needed for real `LoadAsset`. Strict
summaries also include `targetObjectDiscovery` and `targetHooks`; both require
promoted runtime roots and target-image anchors before a canary can prove
game-image rather than loader-image readiness.
The same verification block now includes
`liveTargetImageCanaryContract`, a grouped contract for the remaining
"complete UE4SS port" gap. It is ready only when target-image anchor/signature
coverage, non-self-test object/function registry evidence, runtime reflection
descriptor evidence, live ProcessEvent dispatch evidence, live
CallFunctionByNameWithArguments dispatch evidence, and guarded runtime package
loading evidence are all present.
The ProcessEvent group requires non-self-test hook targets, live Lua dispatch,
runtime function/registry context, live param values, class-aware param values,
and UE4SS-style hook plus alias routing. Partial ProcessEvent logs therefore do
not close the runtime proof gap. The CallFunction group requires non-self-test
hook probe/live-hook targets and `ue-call-function-live-hook luaDispatch=true`.
The top-level `hooks=true`, `targetHooks=true`, and `luaDispatch=true`
aggregates require the CallFunction runtime path as well as ProcessEvent, so a
ProcessEvent-only canary cannot report complete hook or Lua dispatch readiness.
Confidence: high.
`summarize-ue4ss-port-gaps.py` preserves that grouped contract in
`liveTargetImageContract` and reports the first blocked group under
`nextCanaryRecommendation.liveTargetImageContractGroup`, so automation can tell
whether the next canary should stay at target-image anchors, runtime package
loading, runtime object registry, runtime reflection, live ProcessEvent
dispatch, or live CallFunction dispatch. Runtime reflection now requires both
native non-self-test FProperty descriptor/value evidence and the Lua live
descriptor runtime checks before the group is complete. Confidence: high.
The `runtimeProcessEventDispatch` group is intentionally as strict as the Lua
dispatch gate: it requires decoded live function path evidence, runtime
object/function registry context, active params reads, raw/container param
samples, Lua context handles, descriptor-backed param accessors, scalar/name/
string/struct/enum/object/bool accessor coverage, container alias/layout
methods, and live hook routing/alias routing. A live hook row alone is not
UE4SS ProcessEvent parity. Confidence: high.
Native `ue-reflection-property` and `ue-reflection-value` rows now emit
`descriptorProvenance=runtime|self-test` on Linux server, native Linux client,
and Windows/Proton loaders, so readiness can prefer explicit provenance over
name-based fallback heuristics. Confidence: high.
Runtime reflection readiness now requires explicit
`descriptorProvenance=runtime`. Ambiguous older rows without that field can
still be summarized as generic descriptor/value scan evidence, but they do not
open `ueReflectionPropertyDescriptorsRuntime` or
`ueReflectionPropertyValuesRuntime`. The same rows also include
`fieldTargetImage`, `objectTargetImage`, and `valueTargetImage` diagnostics on
current loaders so canary review can see whether a descriptor/value came from
the game image or runtime heap. Confidence: high.
The top-level readiness aggregate follows the same rule:
`ue4ssLuaApiComplete=true` now requires `luaDispatch=true`,
`luaLoadAssetPackage=true`, the guarded package-native crash guard,
guarded-call, return-validation, adapter, invocation-descriptor, and executor
state gates, and `liveTargetImageCanary=true`. A log that proves package-backed
`LoadAsset` but lacks same-build signature validation, prepared anchor coverage,
or the guarded native-call safety chain remains incomplete. Confidence: high.
`nextCanaryContract` records the same rule as
`currentTargetAnchorGroupCounts`, `missingAnchorGroups.targetObjectDiscovery`,
`missingAnchorGroups.targetHookPlanning`, and
`missingAnchorGroups.targetPackageLoading` so automation can reject
loader-image-only evidence before hook probes or package-backed `LoadAsset`.
Confidence: high.
Readiness ingestion defaults to Dune target detection and auto-scopes
mixed-process logs to target PIDs when `event=loaded exe=...DuneSandbox...` is
present and no explicit `--pid` or `--exe-substring` filter was supplied. For
non-Dune UE targets, pass the game executable or module fragment explicitly,
for example `--exe-substring ExampleGame`, to
`scripts/ue4ss-port-readiness.py` and `scripts/summarize-ue4ss-port-gaps.py`.
The selected PIDs are emitted as `autoTargetPidFilters`; the active target
fragments are emitted as `targetImageSubstrings`. `targetImageProcess=true` is
required by the strict live target-image contract. Strict post-canary
verification also requires `runtimeRootDiscovery=true`, mapped to the
`ue-runtime-root-discovery` gate, before target-image anchors are considered
ready. This prevents helper shell/tool processes or self-test-only logs from
contributing root, reflection, hook, or Lua evidence to a game-image readiness
claim. Confidence: high.
Runtime root auto-discovery logs scan coverage before promotion. Linux loaders
report `targetWritableMappings`, `oversizedMappings`, `scannedSlots`,
`fnameProbes`, and `objectArrayProbes`; the Windows/Proton loader reports the
same probe counters with `targetWritableRegions` and `oversizedRegions`. A
zero-target scan emits a dedicated `target-writable-image-* status=missing`
row, so the next canary can distinguish "wrong image or mapping filter" from
"scanned target image but no plausible root". Confidence: high.
The scan summarizers and `scripts/ue4ss-port-readiness.py` now expose this as
`ueRuntimeDiscovery`/`runtimeDiscovery`, including promoted runtime root names,
per-root `candidateNameCounts`, per-image `candidateImageCounts`, bounded
`candidateLocations` with module/RVA or image/file offsets, coverage totals,
status counts, and failure classes such as `not-run`,
`no-target-writable-image`, `no-root-hits`, `ambiguous-root-hits`, and
`incomplete-promotion`. Confidence: high.
`scripts/plan-ue4ss-canary-env.py` consumes those failure classes when building
the next read-only canary env: `not-run` keeps auto-discovery enabled at the
default bound, `no-target-writable-image` widens the bounded mapping/region
scan, `no-root-hits` broadens scan size and candidate count, and
`ambiguous-root-hits` tightens candidate count to produce a smaller diagnostic
failure. When candidate counts identify only one root family, the planner calls
out `RuntimeFNamePool` versus `RuntimeGUObjectArray` specifically so the next
canary does not hide root-family skew behind a generic root-discovery failure.
When the previous readiness report includes `candidateLocations`, the generated
plan also lists the candidate root module and RVA/image/file offsets to inspect
before attempting promotion.
If a previous canary produced exactly one `RuntimeFNamePool` or
`RuntimeGUObjectArray` candidate location, the next generated env carries that
root forward as an explicit candidate global while auto-discovery continues for
the missing or ambiguous partner root. Target-image candidates use
`RuntimeFNamePool=0x...`; Linux runtime RW mappings use
`RuntimeGUObjectArray@rwfile=0x...`.
Confidence: high.
If
`ueProcessEventLuaHookAliasRouting=false`, the Lua-dispatch plan emits
`*_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT` from `canaryHints.ue4ssFunctionPaths`
when scan evidence exposes a UE4SS-style `/Script/...:Function` candidate. New
loader builds emit that path directly as `functionPath` and retain the older
`/RuntimeProbe/...:Function` identity as `functionRuntimePath`; the analyzer
still derives the script path for older logs. It falls back to
`canaryHints.ueFunctionPaths` plus a generated probe package when only a
runtime path is available. Use
`--live-lua-alias-hook-path` for an explicit `/Script/...:Function` target, or
`--live-lua-alias-function-path` with `--live-lua-alias-script-package` for the
fallback path generator. This is decoded owner/function identity, not full
Unreal outer/package chain reconstruction yet. Confidence: high.

Current loaders emit `lua-object-outer-chain` when a registered object has a
non-null `OuterAddress`. They log once after registry seeding and again after
Lua mod dispatch, so loader-owned `StaticConstructObject` world/level/actor
chains are included. The event reports `resolved` only when each outer hop is
present in the Lua object registry and includes `chain`, `terminalPath`, and
`terminalClass`. Resolved events also include `reconstructedPath`,
`reconstructedFullName`, and `fullNameResolved=true` when the loader can rebuild
a path/full-name from known outer handles; readiness exposes this as
`luaObjectOuterChainIdentities`. Lua object handles expose the same identity as
`OuterChainPathName`, `OuterChainFullName`, `HasOuterChainPath`,
`GetOuterChainPathName()`, and `GetOuterChainFullName()`. This proves
loader-side outer-chain reconstruction for discovered handles, not a call
through Unreal's native full-name/path functions. Confidence: high.

Source that env for a second read-only launch, then run the readiness gate.

For Windows, also validate forwarding:

```text
event=forward-smoke function=GetFileVersionInfoSizeW result=<nonzero>
```

If the client starts but no Dune-specific scan hits appear, do not assume the
loader failed. Check `event=module` first to verify the game executable and
expected modules are present in the log, then narrow `SCAN_PATH_FILTER` or add
more precise signatures.

For UE readiness, the minimum useful read-only discovery set is at least one
anchor in each of:

- names: `FNamePool` or `GName`
- objects: `GUObjectArray` or `GObjectArray`
- world: `GWorld`, `GEngine`
- dispatch: `ProcessEvent`, `StaticFindObject`, or `CallFunctionByNameWithArguments`

Run the shared port gate after a canary:

```bash
scripts/ue4ss-port-readiness.py \
  --client-log /tmp/dune-win-client-probe-loader.log \
  --loader win-client \
  --signature-validation-json build/windows-client-loader/client-pe-signature-validation.json \
  --anchor-coverage-json build/windows-client-loader/client-anchor-canary/anchor-coverage.json
```

For local Windows/Proton parity after `make smoke-windows-client-loader-full`,
use `/tmp/dune-win-client-probe-lua-smoke.log` as the readiness input. The
default `/tmp/dune-win-client-probe-smoke.log` intentionally covers the
`library-missing` Lua path.

For a native Linux client, use `--client-log /tmp/dune-client-probe-loader.log`.
The planner accepts both the platform name `linux-client` and the loader log
label `client` by default. For a Linux server canary, use
`--server-log /tmp/dune-server-probe-loader.log`.

The gate is intentionally strict. `objectDiscovery=false` means stay in
scan/xref mode or rerun with pointer, layout, UObject candidate, and
object-array internal-flag probes.
`targetObjectDiscovery=false` means the core discovery anchors may still be
missing or may only resolve inside the probe loader image. It does not pass
until the names, objects, world, and dispatch groups have target executable or
game-module provenance. `targetHooks=false` applies the same target-image rule
to hook escalation, so loader-owned self-test anchors cannot unlock live
ProcessEvent or CallFunction work. Confidence: high.
Linux server, native Linux client, and Windows/Proton summaries now export the
same proven-target hook counters for guarded probes and persistent hooks:
`provenTargetPassedUeProcessEventHookCount`,
`provenTargetInstalledUeProcessEventLiveHookCount`,
`provenTargetPassedUeCallFunctionHookCount`, and
`provenTargetInstalledUeCallFunctionLiveHookCount`. CallFunction Lua routing
also has proven-target routed/handled counters. Generic installed/routed hook
rows without target provenance remain useful diagnostics, but they cannot open
`targetHooks`, `ueProcessEventLiveHookRuntimeTarget`, or
`ueCallFunctionLiveHookRuntimeTarget`. Confidence: high.
`objectDiscoveryCoverage=false` gives a structured breakdown in
`objectDiscoveryCoverage.missingObjectDiscoveryComponents`; use it to decide
whether the missing piece is anchors, pointer/layout probing, UObject candidate
reads, FName decoding, decoded aliases, or internal flags.
`findObjectSemantics=false` means the loader has not yet proven the full
registry-backed `FindObject`/`StaticFindObject` surface, including object-array
registry entries, native path/name/class/address registry self-checks
(`event=lua-object-registry-check status=passed`), native object identities,
outer-chain full names, and Lua object API calls.
`reflection=false` now also covers `ueFunctionFlags=false`,
`luaFunctionRegistryChecks=false`, and `luaFunctionRegistryRuntime=false`;
readable `FunctionFlags` must be promoted and
the native function registry self-check
(`event=lua-function-registry-check status=passed`) must prove
path/runtimePath/name/address/flags lookup consistency on a non-self-test
runtime function before
`FindFunction()`/`GetFunctionFlags()` are treated as live-compatible. It also
covers `ueFunctionParamContainerChildren=false`, which means no bounded
container-param scan has decoded inner/key/value child property metadata yet.
`hookDispatch=false` means prove the guarded self-test before touching a game
function. `modDispatch=false` means prove the native mod lifecycle before Lua
binding work. `luaRuntime=false` means Lua execution, Lua callback dispatch, and
UE4SS-style Lua API surface calls have not all been proven.
`luaObjectApi=false` means `FindObject`, `GetKnownObjects`, `FindObjects`,
`FindAllOf`, `ForEachUObject`, `IsA`, and `LoadAsset` have not passed in both
the built-in Lua self-test and a loaded Lua mod. This is still registry-backed
object API evidence. `luaLoadAssetBackendState=true` means a Lua mod exercised
the guarded backend contract; `luaLoadAssetBackendAnchors=true` means that check
also saw package-loading anchors. Neither means package loading is armed.
`luaLoadAssetPackage=false` means `LoadAsset` has not yet resolved through a
real Unreal package/asset backend; current loader builds only prove lookup of
already-known registry handles. `ue4ssLuaApiComplete=false`
keeps that distinction visible even when the staged `luaDispatch` gate is true.
The standard `ue` scan preset now includes `StaticLoadObject`, `StaticLoadClass`, `LoadObject`,
`LoadPackage`, and `ResolveName` so the next canary can rank package-loading
surfaces without calling them. Readiness reports proven package anchors as
`packageLoadingSurface` and prepared canary package coverage as
`anchorCoveragePackageLoading`.
`luaFunctionIterationRuntime=false` means `ForEachFunction` has not yet
enumerated promoted `UFunction` handles from a non-self-test object/class
handle; self-test class iteration is no longer enough for `luaDispatch=true`.
`luaObjectRegistryRuntime=false` means no non-`SelfTest*` object has reached the
Lua registry through the `ue-uobject` scanner path. Current local parity smokes
close that with loader-owned `RuntimeProbeUObject`; live `FindObject` semantics
still require real target anchors. Current parity smokes also close
`ueObjectArrayRegistryRuntime` by scanning `RuntimeProbeObjectArray_1` through
the normal chunked object-array reader with `registryProvenance=runtime`.
`luaDecodedObjectAliasesRuntime=false` or `ueObjectArrayRegistryRuntime=false`
means decoded alias or object-array evidence is still self-test only.
`luaDecodedObjectAliases=false` means decoded UObject FNames have not been
promoted into Lua-visible `/RuntimeProbe/<DecodedName>` aliases. `luaMods=false`
means Lua mod entrypoint loading and callback dispatch have not both passed.
`luaSchedulerApiMods=false` means the scheduler API only passed the built-in
Lua self-test and has not yet been proven from a loaded mod entrypoint using
`ExecuteInGameThread`, `ExecuteAsync`, `ExecuteWithDelay`, `LoopAsync`, queue
drain, and cancellation paths.
`luaInputCommandApiMods=false` means keybind and console command APIs only
passed the built-in Lua self-test and have not yet been proven from a loaded
mod entrypoint using keybind dispatch/unregister and named/global console
handler dispatch/unregister paths.
`luaProcessConsoleExecHooks=false` means a Lua mod has not yet proven
`RegisterProcessConsoleExecPreHook`/`PostHook` dispatch around loader-owned
`ProcessConsoleExec`.
`luaLocalPlayerExecHooks=false` means a Lua mod has not yet proven
`RegisterULocalPlayerExecPreHook`/`PostHook` dispatch around loader-owned
`ULocalPlayerExec`.
`luaCallFunctionHooks=false` means a Lua mod has not yet proven
`RegisterCallFunctionByNameWithArgumentsPreHook`/`PostHook` dispatch around
loader-owned `CallFunction`. `luaCallFunctionStructuredArgs=false` means hook
dispatch may work, but the bounded table-to-command-string subset has not been
proven with scalar, boolean, numeric, and vector-shaped fields across the Linux
server, native Linux client, and Windows/Proton client loaders.
`luaLifecycleHooks=false` means a Lua mod has not yet proven `RegisterCustomEvent`
plus `RegisterLoadMap*`, `RegisterBeginPlay*`, and `RegisterInitGameState*`
dispatch around loader-owned lifecycle shims. The UE4SS callback spellings are
available as aliases too: `RegisterLoadMapPreCallback`,
`RegisterLoadMapPostCallback`, `RegisterBeginPlayPreCallback`,
`RegisterBeginPlayPostCallback`, `RegisterInitGameStatePreCallback`, and
`RegisterInitGameStatePostCallback`, with matching unregister names.
`RegisterLocalPlayerExecPreHook` and `RegisterLocalPlayerExecPostHook` are also
available as shorter aliases for the `ULocalPlayerExec` hook names.
The readiness report also splits that aggregate into `luaCustomEventHooks`,
`luaLoadMapHooks`, `luaBeginPlayHooks`, and `luaInitGameStateHooks`; all four
must be true before `luaDispatch=true` can represent UE4SS-style lifecycle
coverage.
`ueProcessEventHookProbe=false` means no mapped/executable ProcessEvent target
has survived the guarded install/restore probe. `ueProcessEventLiveHook=false`
means the opt-in persistent hook scaffold has not been installed on a resolved
target. `ueProcessEventDispatch=false` means the native pre/original/post
callback spine has not been armed. `ueProcessEventLiveLuaDispatch=false` means
the live hook has not invoked Lua `RegisterHook` callbacks.
`ueProcessEventHookRuntimeTarget=false` or
`ueCallFunctionHookRuntimeTarget=false` means the corresponding guarded hook
probe only proved loader-owned self-test code, not a resolved runtime target.
`ueCallFunctionHookProbe=false` means no mapped/executable
`CallFunctionByNameWithArguments` target has survived guarded install/restore.
`ueCallFunctionLiveHook=false` means the opt-in persistent
`CallFunctionByNameWithArguments` hook scaffold has not installed on a resolved
target. `ueCallFunctionLiveHookRuntimeTarget=false` means live hook evidence
still came from loader-owned self-test code, not the resolved Dune
`CallFunctionByNameWithArguments` target.
`ueCallFunctionLiveLuaDispatch=false` means the live CallFunction hook has not
yet routed Lua pre/post callbacks with the persistent hook installed.
`ueCallFunctionActiveValidation=false` means no explicitly allowed active
`CallFunctionByNameWithArguments` validation call has entered the live hook and
original trampoline. This gate is closed by default; it requires
`*_UE_CALL_FUNCTION_ACTIVE_VALIDATE=true`,
`*_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=true`, a runtime object
address, and either a command string or command-string address.
`ueProcessEventLiveHookRuntimeTarget=false` means the hook probe/install
evidence still came from the loader-owned self-test target, not the resolved
Dune `ProcessEvent` target. `hooks=true` requires both runtime-target gates.
`ueProcessEventActiveValidation=false` means no explicitly allowed active
`ProcessEvent` validation call has entered the live hook and original
trampoline. This gate is also closed by default and requires
`*_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=true` plus runtime object
and function addresses; params may be supplied when a descriptor-backed params
buffer is available.
When either active validation gate is false,
`scripts/plan-ue4ss-canary-env.py --max-stage live-hook` emits the matching
`*_UE_PROCESS_EVENT_ACTIVE_VALIDATE=true` and
`*_UE_CALL_FUNCTION_ACTIVE_VALIDATE=true` variables for server, native Linux
client, or Proton/Windows targets. The planner keeps
`*_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false` unless
`--allow-active-native-call` is passed with reviewed runtime inputs:
`--active-validation-object-address`,
`--process-event-active-function-address`,
`--process-event-active-params-address`,
`--call-function-active-command`,
`--call-function-active-command-address`,
`--call-function-active-output-address`, and
`--call-function-active-executor-address`. Confidence: high.
For the strict parity proof, also pass `--active-validation-through-target`.
That emits `*_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=true` and
`*_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET=true`; the loaders then call
the patched target entrypoint rather than the replacement shim. Readiness only
passes the active-validation gates when the resulting row has
`targetEntry=true` plus positive live/original deltas. Confidence: high.
For ProcessEvent, `*_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS` is
optional when promoted function descriptors are available. If it is omitted,
the loader constructs the same bounded descriptor-backed params buffer used by
`CreateProcessEventParams(function)` and reports `paramsSource=descriptor-buffer`
with buffer size and descriptor count in the active-validation row. Confidence:
high.
If the readiness report contains
`canaryHints.activeValidationCandidates`, add
`--use-active-validation-hints` to promote the first reviewed runtime candidate
into the active-validation env for native Linux client, Proton/Windows client,
or server plans. This only fills object/function/params/command inputs; native
invocation remains closed unless `--allow-active-native-call` is also supplied.
Confidence: high.
When non-self-test live hook targets are already proven and
`ueCallFunctionLiveLuaDispatch=false`, request `--max-stage lua-dispatch` with
the active-validation hints. The planner now emits active-validation env and
live Lua dispatch/mod env in the same canary, so one reviewed run can prove
`ueProcessEventActiveValidation`, `ueCallFunctionActiveValidation`, and
`ueCallFunctionLiveLuaDispatch` instead of spending a restart on only the
active-validation gates. Confidence: high for planning behavior.
`ueProcessEventLiveContext=false` means sampled live hook calls have not yet
resolved raw object/function/params into a Lua-visible object handle, function
path, params pointer, and function-param descriptor set.
`ueProcessEventLiveFunctionPath=false` means sampled live hook calls have not
yet matched that function path to a decoded scanned UFunction identity.
`ueProcessEventLiveRuntimeContext=false` or
`ueProcessEventLiveRuntimeRegistryContext=false` means sampled callback context
still matches loader-owned `SelfTest*`/`LiveProcessEvent` surfaces instead of a
non-self-test decoded runtime `UFunction`; `luaDispatch=true` requires both
runtime context gates.
`ueProcessEventLiveClassAwareParamValues=false` means live Lua dispatch may be
armed, but it has not yet proven promoted `ctx.Function` registry identity plus
descriptor-backed param get/set on the active params pointer.
`ueProcessEventLiveParamValues=false` means sampled live hook calls have not yet
read at least one descriptor-backed param value from the active params block.
`ueProcessEventLiveRawParamValues=false` means sampled live hook calls have not
yet read a complex param payload/header as bounded raw bytes.
`ueProcessEventLiveContainerParamValues=false` means sampled live hook calls
have not yet read an array/set/map param as a typed container header table.
`ueProcessEventLiveArrayContainerParamValues=false`,
`ueProcessEventLiveSetContainerParamValues=false`, and
`ueProcessEventLiveMapContainerParamValues=false` identify which container
kinds were not sampled. `ueProcessEventLiveSetMapContainerParamValues=false`
means no sampled live hook call proved the new `FScriptSetHeader` or
`FScriptMapHeader` path.
`ueProcessEventLiveContainerDataSamples=false` means sampled live array headers
have not yet yielded bounded readable storage bytes from their data pointer.
`ueProcessEventContainerAliasMethods=false` means the Lua self-test and live
hook have not both proved container shorthand methods: `FScriptArray:Get/get`,
`FScriptSet:Get/get`, and `FScriptMap:Get/get` plus direct `GetKey`/`GetValue`.
`luaDispatch=true` now requires all live ProcessEvent container kind gates
(`array`, `set`, `map`, and combined set/map coverage) plus those container
alias methods; an array-only canary no longer implies live set/map parity.
`ueProcessEventLuaContextHandles=false` means those callbacks have not received
resolved `Object`, `Function`, and `Params` context tables.
`ueProcessEventLuaParamAccessors=false` means Lua
`GetFunctionParamDescriptors`/`GetFunctionParams` plus descriptor-handle
`GetParamDescriptor`, `GetParamValue`, and `SetParamValue` access has not
passed in both the synthetic ProcessEvent self-test and the live hook path.
`ueProcessEventLuaScalarParamAccessors=false` means that path has not yet proven
the widened signed/unsigned integer and `float`/`double` scalar get/set fixture.
`ueProcessEventLuaNameStringParamAccessors=false` means that path has not yet
proven guarded in-place `FName`/`FString` param get/set from both the synthetic
ProcessEvent self-test and the live hook path.
`ueProcessEventLuaStructParamAccessors=false` means that path has not yet proven
bounded `FVector`-shaped `FStructProperty` param get/set from both paths.
`ueProcessEventLuaEnumParamAccessors=false` means that path has not yet proven
byte-sized `FEnumProperty` param get/set from both paths.
`ueProcessEventLuaObjectParamAccessors=false` means that path has not yet
proven `FObjectProperty` param get/set from both paths.
`ueProcessEventLuaBoolParamAccessors=false` means that path has not yet proven
`FBoolProperty` param get/set from both paths.
`ueFunctionIdentities=false` means decoded `functionLink` names have not yet
produced Lua-visible runtime UFunction paths.
`ueProcessEventLuaHookRouting=false` means multiple `RegisterHook` entries have
not yet proven that only the matching known `ctx.functionPath` callback fires.
`ueProcessEventLuaHookAliasRouting=false` means a live canary has not yet
proved that a UE4SS-style `/Script/...` registration can route to a decoded
`/RuntimeProbe/<Outer>.<Function>:Function` path by terminal function-name
alias, reported as `pathAliasMatches`.
`luaObjectNotify=false` means a Lua mod has not yet proven
`NotifyOnNewObject` callback dispatch for a newly constructed loader-owned
object handle.
`luaSyntheticOuter=false` means a Lua mod has not yet proven
`StaticConstructObject` preserved and resolved a loader-owned outer handle.
`hooks=false` means do not route live ProcessEvent into Lua/mod callbacks.
`luaDispatch=false` means do not expose UE4SS Lua APIs yet.
`ue4ssLuaApiComplete=false` means the staged dispatch surface still lacks at
least one full-port API requirement, currently real package-backed `LoadAsset`.
The full completion aggregate is `ue4ssLuaApiComplete=true`, which also
requires `liveTargetImageCanaryContract.ready=true` across
`targetImageAnchors`, `runtimePackageLoading`, `runtimeObjectRegistry`,
`runtimeReflection`, and
`runtimeProcessEventDispatch`/`runtimeCallFunctionDispatch`; self-test-only
logs are not enough.
`runtimePackageLoading` includes both guarded `LoadAsset` native invocation and
the package-backed `LoadClass` chain through target-image `StaticLoadClass`.
`runtimeObjectRegistry` includes guarded target-image `StaticConstructObject`
executor state, executor readiness, and native invocation evidence.
The ProcessEvent group specifically requires decoded live function path,
runtime registry context, raw/container params, Lua context handles,
descriptor-backed param accessors, typed scalar/name/string/struct/enum/object/
bool accessors, container alias/layout methods, and hook routing/alias routing.
Confidence: high.

## Next UE4SS-Port Step

The next shared implementation step is read-only Unreal discovery against the
confirmed live process surfaces:

1. locate `FNamePool`;
2. locate `GUObjectArray`;
3. locate `GWorld` and `GEngine`;
4. locate `ProcessEvent`;
5. validate FName/object/class/property layout reads without hooks;
6. use the guarded ProcessEvent hook probe on the resolved target;
7. install the persistent ProcessEvent hook scaffold on the resolved target;
8. enable the live ProcessEvent Lua callback bridge;
9. require resolved `Object`/`Function` handles and a `Params` table in live Lua callbacks;
10. prove Lua `GetFunctionParamDescriptors`/`GetFunctionParams` plus descriptor-handle `GetParamDescriptor` and `GetParamValue`/`SetParamValue` access from ProcessEvent callbacks;
11. prove on a live native-Linux or Proton canary that `ctx.Function` from a real ProcessEvent call has a nonempty runtime `PathName`, hits the promoted `ue-function-param` registry, and that guarded class-aware `GetParamValue` works on the active params pointer;
12. only then attach live UE property marshaling.

## 2026-06-19 Scan Widening

The Linux server, native Linux client, and Windows/Proton client loaders now
share the widened `ue` scan preset for the remaining target-image gates. In
addition to the prior root/function terms, the preset includes common world,
console dispatch, package, and reflected property spellings:
`/Script/Engine.World`, `/Script/Engine.Engine`, `WorldContext`,
`ProcessConsoleExec`, `ULocalPlayerExec`, `LoadAsset`, `LoadClass`,
`FObjectProperty`, `FArrayProperty`, `FBoolProperty`, and `FStructProperty`.

This is still read-only scan evidence. It does not enable live hooks or Lua
dispatch by itself; the next canary must prove target-image world, dispatch,
package-loading, and reflection anchors before hook escalation.

FindObjects(limit, className, objectName, bannedFlags, requiredFlags, exactClass) and FindObject(className, objectName, bannedFlags, requiredFlags) are supported as UE4SS-style bounded registry queries on Linux server, native Linux client, and Windows/Proton. Returned tables keep numeric entries for array-style iteration, path keys for existing lookup compatibility, and Count for bounded result accounting.
