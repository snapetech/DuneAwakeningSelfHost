# Linux Server Loader Canary - 2026-06-19

Confidence: high for the runtime root, FName, UObject array, and UFunction
registry evidence. Confidence: high that this is still not complete UE4SS live
dispatch.

Live evidence was collected from `kspls0`, service `testing-waterfat`,
partition `7`. The canary wrapper reported `connected_players=0` before the
restart. The canaries used the repo canary wrapper and restored preload after
capture.

Captured local evidence:

- Relaxed FName/runtime root canary:
  `backups/canary-linux-loader/20260619T155054Z/`
- Class-reflection canary:
  `backups/canary-linux-loader/20260619T160622Z/`
- Function-registry canary:
  `backups/canary-linux-loader/20260619T161816Z/`
- Function-iteration follow-up canary:
  `backups/canary-linux-loader/20260619T163655Z/`
- ProcessEvent vtable candidate canary:
  `backups/canary-linux-loader/20260619T172145Z/`
- Persistent ProcessEvent hook canary:
  `backups/canary-linux-loader/20260619T180553Z/`
- Latest loader log:
  `backups/canary-linux-loader/20260619T180553Z/dune-server-probe-loader-deep-desert-brt.log`
- Latest readiness report:
  `backups/canary-linux-loader/20260619T180553Z/ue4ss-readiness.md`

## What Passed

The 2026-06-19 live canary promoted both runtime roots:

- `RuntimeFNamePool`
- `RuntimeGUObjectArray`

The delayed probe then proved the FName decoder against the live process:

- `event=ue-fname-start phase=ue-delayed status=ready`
- `event=ue-fname-finish phase=ue-delayed status=ready`

The object-array pass produced runtime registry evidence:

- `event=ue-object-array-finish phase=ue-delayed registryCount=32`
- readiness: `Ready Lua object registry runtime evidence: true`
- readiness: `Ready Lua decoded object aliases runtime evidence: true`
- readiness: `Ready UE object array registry runtime evidence: true`
- readiness: `Ready UE object native identities: true`
- readiness: `Ready UE object internal flags: true`

The new class-reflection pass walked `UClass` objects from the live
`GUObjectArray` and promoted `functionLink` entries without requiring a
non-null params/property root. That produced real runtime UFunction registry
evidence:

- `event=ue-object-array-class-reflection ... className=Class`
- `event=ue-function-native-identity source=ue-function-link status=promoted`
- `event=lua-function-registry-check source=ue-function-link status=passed`
- readiness: `Ready Lua function registry checks: true`
- readiness: `Ready Lua function registry runtime evidence: true`

Sample promoted runtime functions include:

- `/Script/Object.ExecuteUbergraph:Function`
- `/Script/Actor.WasRecentlyRendered:Function`
- `/Script/ActorComponent.ToggleActive:Function`
- `/Script/SceneComponent.ToggleVisibility:Function`
- `/Script/PrimitiveComponent.WasRecentlyRendered:Function`
- `/Script/MeshComponent.SetVectorParameterValueOnMaterials:Function`
- `/Script/ChaosCacheManager.TriggerComponentByCache:Function`
- `/Script/MovieSceneSection.SetRowIndex:Function`

The follow-up canary from `20260619T163655Z` used the rebuilt server loader and
closed runtime-backed function iteration evidence:

- `event=lua-function-registry-check source=ForEachFunction status=passed`
- `event=lua-function-iteration-check source=ForEachFunction status=passed
  mode=owner registryProvenance=runtime`
- readiness: `Ready Lua function iteration runtime evidence: true`

The vtable candidate canary from `20260619T172145Z` enabled
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN=true` after fixing
`scripts/run_server_safe.sh` to load and pass the new vtable env keys from
`/workspace/.env`. Earlier attempts at `20260619T165642Z` and
`20260619T170958Z` had the env set in `.env` but did not pass it into the
server process.

The successful run emitted:

- `event=ue-process-event-vtable-scan`: 4096 rows
- `event=ue-process-event-vtable-candidate`: 393216 rows
- scan summaries: 4096 `status=scanned`, 0 `vtable-unreadable`, 0
  `vtable-unmapped`
- slot totals: 393216 readable slots, 393216 executable slots, 0 zero,
  non-executable, or unreadable slots

This proves that live `GUObjectArray` objects expose readable vtables whose
first 96 slots point into executable target-image mappings. It does not identify
which slot is `UObject::ProcessEvent`; the candidate set must be ranked and
narrowed before running the guarded hookability probe.

Rank the candidate set with:

```bash
scripts/summarize-ue-vtable-candidates.py backups/canary-linux-loader/20260619T172145Z/dune-server-probe-loader-deep-desert-brt.log --format markdown > backups/canary-linux-loader/20260619T172145Z/ue-vtable-candidates.md
scripts/summarize-ue-vtable-candidates.py backups/canary-linux-loader/20260619T172145Z/dune-server-probe-loader-deep-desert-brt.log --format json > backups/canary-linux-loader/20260619T172145Z/ue-vtable-candidates.json
```

The generated local artifacts are:

- `backups/canary-linux-loader/20260619T172145Z/ue-vtable-candidates.json`
- `backups/canary-linux-loader/20260619T172145Z/ue-vtable-candidates.md`

The first guarded hook target selected from that evidence was slot 67 /
`imageOffset=0xfa92d50`.

The dry-run canary from `20260619T174714Z` used
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET=0xfa92d50`,
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE=true`, and
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=false`. It emitted:

- `event=ue-code-target ... status=resolved target=0x55fa4185ad50
  imageOffset=0xfa92d50`
- `event=ue-process-event-hook ... status=target-mapped ... executable=true
  install=false`
- `event=ue-process-event-hook ... status=dry-run`

The guarded install/restore canary from `20260619T175542Z` used the same image
offset with `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=true`. It emitted:

- `event=ue-code-target ... status=resolved target=0x556ac892ed50
  imageOffset=0xfa92d50`
- `event=ue-process-event-hook ... status=target-mapped ... executable=true
  install=true`
- `event=ue-process-event-hook ... status=passed ... installed=true
  restored=true targetSource=image-offset-hook-address targetName=ProcessEvent
  callSelfTest=false liveCalls=0 originalCalls=0`

Readiness for `20260619T175542Z` reports
`ueProcessEventHookProbe=true` and
`ueProcessEventHookRuntimeTarget=true`. It still does not prove a persistent
live hook, live ProcessEvent calls, Lua routing, or param marshaling.

The persistent live hook canary from `20260619T180553Z` used
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET=0xfa92d50`,
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK=true`, and bounded call logging.
It emitted:

- `event=ue-code-target ... status=resolved target=0x5582e009cd50
  imageOffset=0xfa92d50`
- `event=ue-process-event-live-hook ... status=target-mapped ...
  executable=true ... logCalls=true callLogLimit=8`
- `event=ue-process-event-live-hook ... status=installed ...
  selfTestTarget=false targetSource=image-offset-live-hook-address
  targetName=ProcessEvent callSelfTest=false luaDispatch=false liveCalls=0
  originalCalls=0 trampoline=0x7fed689fd000`

Readiness for `20260619T180553Z` reports `ueProcessEventLiveHook=true` and
`ueProcessEventLiveHookRuntimeTarget=true`. It does not report
`ueProcessEventHookProbe=true` because this was a separate persistent-hook run,
not an install/restore hook-probe run. It also does not prove live
`ProcessEvent` context, native dispatch, Lua routing, or param marshaling
because no live ProcessEvent calls were observed during the canary window.

The wrapper reported `connected_players=0`, restored
`DUNE_ENABLE_LINUX_SERVER_PRELOAD=false`, and `watch-status.after.txt` reported
`testing-waterfat partition=7 status=running`.

## What Remains Blocked

The canary still reports `Ready live target-image canary: false` and
`Ready complete UE4SS Lua API: false`.

Remaining hard blockers:

- Target-image object discovery: still missing world/core anchors,
  outer-chain identities, and live `FindObject` semantics.
- Target-image hook readiness: `ProcessEvent` slot-67 image offset
  `0xfa92d50` has passed guarded install/restore and persistent live-hook
  install on one zero-player map.
  `CallFunctionByNameWithArguments` still lacks an equivalent selected live
  runtime target canary. The repo-side loaders now include
  `InvokeCallFunctionNative` self-test/preflight support, but that does not
  replace live target-image proof.
- Live dispatch: no observed ProcessEvent/CallFunction runtime context, Lua
  routing, alias routing, or live params evidence.
- Reflection marshaling: no runtime `FProperty` descriptor/value proof from
  live Dune function params or properties.
- Package loading: no proven `StaticLoadObject`/`LoadObject`/`LoadPackage`
  target surface or guarded package call path.
- Lua function/mod aggregate: runtime function iteration is now proven, but
  no live Lua mod has run on the target server path in this canary, so the
  broader `Ready Lua function iteration` and `Ready Lua dispatch` aggregates
  remain false.

The next high-value step is not more string scanning or another passive
ProcessEvent install canary. It is a selected `CallFunctionByNameWithArguments`
target canary, plus an active runtime dispatch validation path that can
deliberately exercise ProcessEvent/CallFunction through promoted runtime
object/function descriptors without mutating player state. Lua callback routing
should stay gated until those runtime context and param rows exist.
