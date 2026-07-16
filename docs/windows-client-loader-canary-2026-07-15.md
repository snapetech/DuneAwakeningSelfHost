# Windows Client Loader Canary — 2026-07-15

This records the authorized read-only Proton canary performed on July 15, 2026
local time (July 16 UTC). It is evidence for one exact client build, not a
portable signature manifest and not proof of a complete UE4SS port.

## Bound artifacts

| Artifact | Evidence |
| --- | --- |
| Steam app | `1172710` |
| Client build | `24146567` |
| Shipping executable SHA-256 | `20ff16f99d14664dbd159fe5f7ccadf4aac9380b3fcb9f436219f119f1390920` |
| Canary loader SHA-256 | `19f767f6c96fb409504df636c173dc9b965a17c1822fd438817ede95d306d3c2` |
| Runtime | GE-Proton 11-1, native-then-builtin `version.dll` override |
| Loader path observed by the target | `DuneSandbox/Binaries/Win64/VERSION.dll` |

The build-24146567 Steam depot inventory established that neither `version.dll`
nor `dune-win-client-probe.env` was an official file. The older June
`version.dll` backup was another DASH probe, not an original game DLL; it was
adopted as originally absent and removed through the transactional manager.

## Staged results

1. The modern proxy loaded inside `DuneSandbox-Win64-Shipping.exe`; the loaded
   module mapped to the game-directory DLL, not Wine's builtin.
2. Broad read-only discovery found a stable FName pool at RVA `0xb951768`. It
   decoded `None` as the first entry and 303 plausible sampled entries.
3. Discovery found the strong GUObjectArray candidate at RVA `0xb9f8ec0`. It
   grew from 113,542 objects/two chunks to 280,238 objects/five chunks during
   the delayed observation, while small competing candidates were unstable.
4. A targeted replay with only those two RVAs validated both consumers and
   registered 128 of 128 sampled objects with decoded UE names and classes.
5. The reflection replay completed in approximately five seconds. It scanned
   and registered 4,096 of 4,096 sampled objects, decoded 5,724 FNames, decoded
   4,097 object names and 4,096 class names, identified 3,069 reflection-field
   candidates, class-mapped 1,769 fields, identified 1,831 property candidates,
   and recovered 157 function-parameter candidates plus four container-child
   candidates.
6. Runtime-root validation finished ready for both `RuntimeFNamePool` and
   `RuntimeGUObjectArray`. Pointer/layout, object-array shape, FName decoding,
   object identities, internal flags, field walking, property descriptors, and
   property-value reads produced positive evidence.

The 128-slot vtable inventory covered 512 objects and produced 89 distinct
executable targets. Slots 64–68 ranked highest, but those rows are candidates,
not a validated ProcessEvent address. No hook, dispatch self-test, native call,
Lua mod, or Pak mount ran during this canary.

## Negative findings and remaining gates

- The generated literal/signature hits for GEngine/UObject/UClass were code or
  string locations, not usable root pointers, and were rejected by shape
  validation.
- `classMappedUeUObjectCount` remained zero in the readiness summary even though
  individual reflection fields mapped successfully.
- GWorld/GEngine, ProcessEvent/StaticFindObject/CallFunction dispatch, and
  package-loading anchors remain unproven for this build.
- The canary is not ready for hooks, live Lua dispatch, `LoadAsset`, `LoadClass`,
  or `StaticConstructObject` invocation.
- The reflection configuration emitted a 59 MiB trace, dominated by 65,536
  vtable-candidate rows. The next-canary planner now caps this stage at 64
  objects (8,192 candidate rows at 128 slots), an eightfold reduction; operators
  can still override the explicit limit when broader sampling is justified.

Confidence is **high** for proxy loading and the two build-specific runtime
roots, **moderate** for the sampled reflection layouts, and **unknown** for
dispatch and package-loading targets.

## Cleanup state

The game, launcher, anti-cheat wrapper, and Gamescope session were stopped after
the run. Deployment `current-loader-reflection` was checksum-verified and
rolled back; the staged DLL and sidecar are absent from the Steam directory,
and the app-specific Wine DLL override was removed. No client deployment is
currently active.

The private raw log was intentionally not committed. Reproduce the bounded
summaries with:

```bash
scripts/summarize-client-loader-scan.py /path/to/loader.log \
  --loader win-client --pid 1244 \
  --exe-substring DuneSandbox-Win64-Shipping.exe --format json

scripts/ue4ss-port-readiness.py \
  --client-log /path/to/loader.log --loader win-client --pid 1244 \
  --exe-substring DuneSandbox-Win64-Shipping.exe --format json

scripts/summarize-ue-vtable-candidates.py /path/to/loader.log \
  --format json --limit 20
```
