# UE4SS Linux Server Loader Evaluation

Status on 2026-06-16: upstream UE4SS is not directly usable in the current
native Linux Dune dedicated-server containers. Confidence: high.

The linked `CheatManagerEnablerMod` is a UE4SS Lua client-style mod by default.
It becomes server-side only if UE4SS itself is loaded into the dedicated server
process. Installing the mod files into a Dune client is out of scope for this
repo, and this repo must not edit local Steam/Dune client files.

The upstream mod script itself is small: it registers a UE4SS Lua hook on
`/Script/Engine.PlayerController:ClientRestart`, checks
`PlayerController.CheatManager`, falls back to
`StaticFindObject("/Script/Engine.CheatManager")` when `CheatClass` is null,
then `StaticConstructObject`s the cheat manager and assigns it back to
`PlayerController.CheatManager`. That requires UE4SS object discovery,
`RegisterHook`, `StaticFindObject`, and `StaticConstructObject` inside the
target Unreal process; the Lua file alone cannot do anything in a Linux server
container. The current loader now proves the Lua API shape for
`StaticConstructObject` with a synthetic registry handle, not a real UE
allocation.

## Upstream Findings

- Upstream `xmake.lua` restricts platforms to Windows x64.
- Upstream CMake project config exposes `Win64` as the platform type.
- The release/install shape is a Windows proxy-DLL layout under `Binaries/Win64`.
- Native Linux configure cannot complete from the public checkout here because
  `deps/first/Unreal` points to `git@github.com:Re-UE4SS/UEPseudo.git`, which is
  not accessible from this environment.
- Source inspection shows Windows loader/API assumptions throughout the runtime:
  proxy generation, `LoadLibrary*`, `GetModuleHandle*`, Windows module handles,
  DLL entrypoints, Windows exception/crash handling, and `__declspec` exports.
- Upstream `CheatManagerEnablerMod` depends on UE4SS Lua APIs and an Unreal
  `PlayerController` hook. It is not a standalone binary patch, pak patch, or
  server config.

## Repo-Side Loader Foundation

This repo now has a native Linux preload probe with read-only UE anchor probes
and loader-owned UE4SS-style dispatch self-tests. It is not a complete UE4SS
port. It proves that we can inject a shared object into the Linux server
process, collect runtime module visibility, validate explicit UE runtime
anchors, run bounded pointer/layout/UObject/object-array/FName probes, register
candidate object handles for Lua, run guarded hook/mod dispatch self-tests,
execute Lua through a dynamic Lua C API, exercise typed Lua reflection
callbacks, and dispatch Lua callbacks through a ProcessEvent-shaped
loader-owned trampoline. It can also run a guarded mapped/executable
ProcessEvent target hookability probe that installs an inline hook and
immediately restores it when explicitly enabled. The persistent ProcessEvent
hook scaffold can also be installed behind a separate opt-in gate; it forwards
to the original function and restores on unload. A separate live-Lua gate now
routes loader-provided `RegisterHook` pre/post callbacks from that persistent
hook, but it does not yet decode live UE arguments. Live reflection descriptors
now support a bounded typed `GetValue()` subset for known scalar/object/FName
property classes, but not arbitrary `FProperty` payloads. Confidence: high for
the local smoke path.

The shared portability contract is generated with
`scripts/ue4ss-portability-contract.py --check`. It compares the
Linux dedicated server, Linux native client, and Windows/Proton client artifacts so
the UE4SS-facing runtime anchor, UObject/UFunction lookup, reflection,
ProcessEvent hook dispatch, Lua dispatch, mod lifecycle, and container
marshaling surfaces stay aligned. It also enforces the injection distinction:
Linux ELF targets use `LD_PRELOAD`; the Proton client uses a `version.dll`
proxy loaded inside the Windows PE process.
The same contract requires `runtimeRootDiscovery=true` before target-image
hook, reflection, Lua, or package-loading evidence can count as full UE4SS
readiness.
As of the 2026-06-19 canary pass, `runtimeRootDiscovery=true` means more than
mapped `RuntimeFNamePool`/`RuntimeGUObjectArray` anchors. The roots must also be
validated by the consumers that need them: a ready or decoded FName path for
`RuntimeFNamePool`, and object-array registry or class-mapped UObject evidence
for `RuntimeGUObjectArray`. Mapped roots without those downstream probes are
reported as `unvalidated-root-hits`, not readiness. Confidence: high.
Current Linux server, native Linux client, and Windows/Proton loaders also emit
explicit consumer records when that proof happens:
`event=ue-runtime-root-validation name=RuntimeFNamePool status=validated consumer=fname`
and
`event=ue-runtime-root-validation name=RuntimeGUObjectArray status=validated consumer=object-array`.
Readiness consumes those records directly and keeps the older downstream
inference only as compatibility for older logs. Confidence: high.
Readiness also reports `runtimeRootValidation` separately. That key means roots
from any source were proven by the FName and GUObjectArray consumers.
`runtimeRootDiscovery` is stricter: the same proof must follow an auto-discovery
run. The 2026-06-19 exact runtime-root replay log at
`/tmp/ue4ss-port-current/dune-server-probe-loader-exact-runtime-roots-fname-shift6-16d8f4c.log`
proves validation, not auto-discovery: 129 decoded FNames, a ready
`RuntimeFNamePool`, a finished `RuntimeGUObjectArray` walk, and runtime object
registry entries. The live target-image contract still keeps
`runtimeRootDiscovery` missing until the bounded delayed auto-discovery canary
reaches the same consumer evidence. Confidence: high.
That same replay only scanned 128 GUObjectArray entries and did not produce
runtime UFunction registry evidence, so the next canary must not repeat the
shallow pass. When readiness has `runtimeRootValidation=true` but
`luaFunctionRegistryRuntime=false` or `reflection=false`,
`scripts/plan-ue4ss-canary-env.py` now emits a read-only deepening pass with
`*_UE_OBJECT_ARRAY_MAX_OBJECTS=4096` plus reflection field/property/value probes
enabled. The intended proof is live `ue-object-array` UFunction identity
promotion and a `lua-function-registry-check` row with
`registryProvenance=runtime`; that still is not hook or Lua dispatch proof.
Confidence: high.
Runtime root candidate rows now carry target-image location evidence before
promotion: Linux emits `imageOffset`, `fileOffset`, `perms`, and `map`, while
Windows/Proton emits `rva`, `allocationBase`, `regionBase`, `protect`, and
`module`. Readiness exposes those rows as `runtimeDiscovery.candidateLocations`
and aggregates them as `candidateImageCounts`, which keeps ambiguous root
triage anchored to the real target image instead of raw addresses.

Build it:

```bash
scripts/build-linux-server-loader.sh
```

The default output is:

```text
build/linux-server-loader/libdune_server_probe_loader.so
```

Enable it for a lab container only:

```dotenv
DUNE_ENABLE_LINUX_SERVER_PRELOAD=true
DUNE_LINUX_SERVER_PRELOAD=/workspace/build/linux-server-loader/libdune_server_probe_loader.so
DUNE_LINUX_SERVER_PRELOAD_PARTITIONS=7
DUNE_PROBE_LOADER_LOG=/tmp/dune-server-probe-loader.log
DUNE_PROBE_LOADER_TARGET=DuneSandboxServer;DuneSandbox
DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS=0
DUNE_PROBE_LOADER_UE_DELAYED_PROBE_SECONDS=0
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS=false
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=false
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS=1
```

`scripts/run_server_safe.sh` refuses to start with preload enabled unless the
library path exists and is readable inside the container. With preload disabled,
server startup behavior is unchanged.

`DUNE_PROBE_LOADER_TARGET` is a semicolon-delimited executable substring
filter. The server loader logs helper processes as `event=target-skip` and only
runs scan, root discovery, hook probes, reflection probes, and Lua work in a
matching Dune server process. Use `DUNE_PROBE_LOADER_FORCE=true` only for local
smoke tests against non-Dune executables.

For runtime root discovery, set `DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS=true`
only during a bounded read-only canary. The Linux loader scans readable+writable
target-image mappings for unique FNamePool and GUObjectArray-shaped roots. Set
`DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=true` when relocated
Unreal globals land in anonymous RW ELF mappings; the existing
`DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES` cap still applies.
Use `scripts/canary-linux-server-loader.sh` for live server canaries. It checks
the selected partition's `connected_players` before setup and rechecks
immediately before the preload restart. Cleanup also rechecks; if a player
appears during the canary, the script restores `.env` but skips the cleanup
restart instead of disrupting that map again. The skipped restart is recorded as
`restart_skipped_cleanup_due_players=true`, and the next planned restart will
start without preload because the environment has already been restored.
Confidence: high.
If a canary proves the real allocator root is outside target-image and
anonymous RW mappings, enable
`DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=true` for one bounded
canary to include bracketed/private RW mappings such as heap-like runtime
regions. Keep `DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES`
small when doing this; rejected FName samples log allocator state and
first-block evidence without promoting roots that fail the `None` entry gate.
Use `DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_CANDIDATES` and
`DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS` after an
ambiguous-root canary to fail fast and filter tiny GUObjectArray-shaped false
positives. Finish lines report `anonymousWritableMappings` so the canary
summary can prove whether that path was exercised; widened canaries also report
`privateWritableMappings` and `rejectedFNameSamples`. Current loaders also emit
`event=ue-runtime-discovery-limited` and `limited=true` on the finish line when
the pass has a FName hit and enough GUObjectArray-shaped hits to prove object
root ambiguity. That bounded exit lets the same delayed pass continue into
FName/object-array validation instead of spending the live canary window only
scanning for more candidates.
For explicit replay of a proven native Linux runtime root, use
`DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=RuntimeFNamePool@rwfile=0x...` or
`RuntimeGUObjectArray@rwfile=0x...`. `@rwfile` resolves the file offset against
the current process's readable+writable non-executable anonymous/private
runtime mappings, logs `runtimeRwFileOffset=true`, and skips missing matches.
When combining known-good roots with new root-recovery hypotheses, use
`scripts/plan-ue4ss-canary-env.py --candidate-global FNamePool=0x...` or
`--candidate-global RuntimeGUObjectArray@rwfile=0x...` alongside
`--root-recovery-candidates-json`/`--candidate-globals-json`; the planner merges
and de-duplicates those entries into the correct platform candidate-global env.

When a live canary rejects explicit or auto-discovered roots, fold those
outcomes back into the static writable-root exporter before retrying. For ELF
targets, run `scripts/summarize-elf-writable-root-shapes.py` with
`--candidate-outcomes-json`, then export with
`scripts/export-ue-writable-root-shape-candidates.py --anchor-preset
object-discovery`. The preset emits bounded FName/name, object-array, and
world candidates together and records group coverage so the next read-only
canary does not test object roots without a matching names root. The same
candidate-env contract is shared by the native Linux client and the
Windows/Proton path; Windows/Proton uses
`scripts/summarize-pe-writable-root-shapes.py` for PE image roots and the
`DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS` env name. Confidence: high for
tooling parity; runtime promotion still requires target-image canary evidence.
`scripts/export-ue-root-recovery-candidates.py` accepts multiple
`--candidate-outcomes-json` files and merges their rejected offsets before
exporting another queue. Use every relevant live outcome file from the current
build; using only the newest one can accidentally recycle a cluster that an
earlier canary already rejected.
`scripts/plan-ue4ss-canary-env.py` accepts the same
`--candidate-outcomes-json` input and filters rejected or weak live outcomes
before generating the next `*_UE_CANDIDATE_GLOBALS` value.
`scripts/summarize-ue4ss-port-gaps.py` also accepts
`--candidate-outcomes-json`; when present, the gap report threads those files
into the recommended `plan-ue4ss-canary-env.py` commands so the next canary
does not drop live rejection evidence between summary and planning.
Candidate outcomes preserve `runtimeRwFileOffset=true` separately from normal
target-image `imageOffset` evidence. A failed `Name@rwfile=0x...` canary does
not suppress a static image-offset candidate with the same numeric value; those
address modes refer to different mappings and must be reviewed separately.
Confidence: high.

## 2026-06-19 Runtime Root Canary Result

Two read-only live canaries were run on one zero-player `testing-waterfat`
partition and cleaned up afterward; the loader was verified absent from the map
process after each cleanup restart. Confidence: high.

- `20260619T103805Z`: six `GEngine`/`LoadAsset` root-recovery candidates were
  mapped but rejected as null/empty globals. No runtime roots were promoted.
- `20260619T104922Z`: known root candidates plus the next `GEngine` queue
  produced mapped anchors and raw promoted-name evidence, but no FName decode,
  object-array registry, target world, target package, reflection, or dispatch
  proof. `GEngine` candidates were either null/empty or code-pointer false
  positives. This is now classified as unvalidated root evidence, not full
  runtime root discovery.

The next useful canary should carry the last known FNamePool root explicitly
while testing a narrower object-array/world queue, and it must still remain
read-only until FName/object-array consumers validate both roots.

Generated local artifacts under
`/tmp/ue4ss-port-current/next-canary-20260619-strict/` show that the saved
`GEngine` and `LoadAsset` static queues produce zero candidates after both
`20260619T103805Z` and `20260619T104922Z` outcome files are merged. The
`GEngine` export suppresses rejected clusters `1, 2, 3` across 15 rejected
offsets. Confidence: high. Do not spend another live restart on those same
static queues.

The only generated env worth considering from that artifact set is the
read-only runtime-root replay plan:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS='FNamePool=0x1686df70;RuntimeFNamePool@rwfile=0x1e1e18;RuntimeGUObjectArray@rwfile=0x28c4c0'
```

That plan can only validate names/object roots; it does not cover world,
dispatch, package, or reflection groups. Treat it as a root-validation canary,
not an object-discovery or hook/Lua escalation canary.

Optional read-only scan mode:

```dotenv
DUNE_PROBE_LOADER_SCAN_ENABLED=true
DUNE_PROBE_LOADER_SCAN_PRESETS=core,ue,building,brt,deep-desert,gm,cheat
DUNE_PROBE_LOADER_SCAN_STRINGS=DeepDesert;ServerRequestBaseBackup;BaseBackupTool;BuildingSettings;StaticLoadObject;LoadObject;LoadPackage;ResolveName;CheatManager;PrintAllowedCommands;PartitionIndex;BuildableMapRegion;FuncomLiveServices;FarmHealth
DUNE_PROBE_LOADER_SCAN_SIGNATURES=brt-action-guard=48 85 c0 74 0a 41 b6 01 41 80 7f 55 01 75 03
DUNE_PROBE_LOADER_SCAN_SIGNATURES_FILE=/path/to/server-signatures.txt
DUNE_PROBE_LOADER_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_PROBE_LOADER_SCAN_LOG_MAPPINGS=true
DUNE_PROBE_LOADER_SCAN_MAX_MAPPING_BYTES=536870912
```

Scan mode reads `/proc/self/maps` from inside the process and logs string or byte
signature hits with runtime address, image offset, and file offset. It does not
write memory. The current Funcom Linux server executable is about 357 MiB, so
canaries need `DUNE_PROBE_LOADER_SCAN_MAX_MAPPING_BYTES` above that size.
`DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS` is a constructor-time sleep, so keep
it `0` unless intentionally delaying a lab server start. The built-in presets
cover the current investigation surfaces:

`DUNE_PROBE_LOADER_UE_DELAYED_PROBE_SECONDS` starts a detached UE-only
validation pass after the constructor returns. It logs `phase=ue-delayed` and
does not re-run the full scan suite, making it the preferred next canary knob
when constructor-time `RuntimeGUObjectArray` remains missing.

- `building`: landclaim, subfief/totem, and building-piece cap strings.
- `brt`: Base Reconstruction Tool and placement-verdict strings.
- `deep-desert`: Deep Desert map identity and spice/system settings strings.
- `gm`: native server-command/GM command strings.
- `cheat`: CheatManager/UE4SS-adjacent strings.

Validate and export same-build ELF signature seeds after a scan/xref pass:

```bash
scripts/validate-elf-signatures.py /path/to/DuneSandboxServer-Linux-Shipping \
  --loader-log /tmp/dune-server-probe-loader.log \
  --category brt \
  --format json > build/linux-server-loader/elf-signature-validation.json

scripts/export-elf-signature-manifest.py /path/to/DuneSandboxServer-Linux-Shipping \
  --loader-log /tmp/dune-server-probe-loader.log \
  --target-loader server \
  --category brt \
  --format signatures > build/linux-server-loader/server-signatures.txt

scripts/export-elf-signature-manifest.py /path/to/DuneSandboxServer-Linux-Shipping \
  --loader-log /tmp/dune-server-probe-loader.log \
  --target-loader server \
  --category ue \
  --format anchor-signatures > build/linux-server-loader/server-anchor-signatures.txt

scripts/prepare-ue-anchor-canary.py \
  --platform server \
  --binary /path/to/DuneSandboxServer-Linux-Shipping \
  --loader-log /tmp/dune-server-probe-loader.log \
  --include-runtime-candidates \
  --output-dir build/linux-server-loader/server-anchor-canary

scripts/plan-ue4ss-canary-env.py \
  --platform server \
  --server-log /tmp/dune-server-probe-loader.log \
  --max-stage read-only \
  --format json \
  > build/linux-server-loader/next-canary.json

scripts/plan-ue4ss-canary-env.py \
  --platform server \
  --server-log /tmp/dune-server-probe-loader.log \
  --max-stage read-only \
  > build/linux-server-loader/next-canary.env
```

`export-ue-anchor-env.py` exports only mapped explicit anchors and resolved
`ue-anchor-signature` records by default. Raw `scan-hit` rows are candidate
evidence for xref/signature promotion, not explicit anchor addresses; use
`--include-scan-hits` only for a documented manual exception. Confidence: high.

The validator reports `unique-expected`, `unique-unexpected`,
`ambiguous-expected`, `ambiguous`, or `missing` for each seed. The exported JSON
manifest is the cross-build revalidation artifact; the `signatures` output is a
line-based file for `DUNE_PROBE_LOADER_SCAN_SIGNATURES_FILE`. The
`anchor-signatures` output is a line-based file for
`DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE`; it emits only validated
promotable rows whose names map to UE anchor groups. Confidence: high for
synthetic ELF validator coverage.
Runtime `ue-anchor` and `ue-anchor-signature` lines also carry a
loader-normalized `group=` field. Native Linux and Proton/Windows use the same
group names, and synthetic `SelfTest*` anchors report `group=self-test` so they
remain separate from live `names`, `objects`, `world`, `dispatch`, and
`reflection` evidence. Confidence: high.
The per-loader scan summaries expose group counts, and
`ue4ss-port-readiness.py` merges them under `anchorGroups` plus the
`ue-anchor-group-provenance` gate. A failed provenance gate means rerun with a
new loader package before trusting group-level live canary coverage. Confidence:
high.
`prepare-ue-anchor-canary.py` is the one-command bridge for the next pass: it
writes the validated UE manifest, loader-consumable anchor signature sidecar,
second-pass anchor env, validation summary, Markdown/JSON readiness reports,
and runtime coverage sidecars into one directory. The generated env includes
`DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE` pointing at that sidecar, so the
next server canary can promote unique runtime signature matches directly. It
also writes `anchor-coverage.json`, `object-discovery-coverage.json`,
`post-canary-verify.sh`, and a README summary. `anchor-coverage.json` proves
whether combined explicit and
signature-promotable anchors cover the names, objects, world, dispatch, and
reflection groups required before object discovery or hook planning.
`object-discovery-coverage.json` preserves the readiness report's component
evidence for runtime object registry, decoded alias, object-array, native
identity, internal flag, FName decoder, outer-chain, and Lua FindObject
readiness. After the next canary, run `post-canary-verify.sh [loader-log]` from
that output directory to rebuild readiness, object-discovery coverage, the
UE4SS gap summaries (`ue4ss-port-gaps.json` and `ue4ss-port-gaps.md`), and a
compact post-canary summary from the collected log. The strict wrapper also
requires exact/promotable same-build signature validation and object/hook/package
anchor coverage before treating the canary as UE4SS-runtime ready:
`targetObjectDiscovery`, `targetHooks`, and `targetPackageLoadingSurface` must
all be true from target-image evidence. The planner
mirrors that as `strictRuntimeContract.contractReady`, with missing
signature/anchor keys listed separately from missing runtime evidence through
`signatureAnchorReady` and `missingSignatureAnchorReadyKeys`. Confidence: high.
Promotable non-UE signatures do not satisfy these gates. BRT, cheat, cap, or
other gameplay signature manifests are still useful runtime drift checks, but
the generated anchor sidecar must contain rows whose names map to core UE
anchors such as `FNamePool`, `GUObjectArray`, `GWorld`/`GEngine`, `ProcessEvent`, and
`CallFunctionByNameWithArguments`.
`prepare-ue-anchor-canary.py` reports both manifest entry categories and UE
anchor signature entry count; `0` UE anchor signature entries means continue
read-only anchor discovery, not object discovery or hook planning. Confidence:
high.
For UE-category non-string xrefs, promote candidates before validation:

```bash
scripts/summarize-linux-loader-xrefs.py /path/to/DuneSandboxServer-Linux-Shipping \
  --loader-log /tmp/dune-server-probe-loader.log \
  --category ue \
  --format json > build/linux-server-loader/ue-anchor-xrefs.json

scripts/promote-ue-anchor-xref-candidates.py \
  build/linux-server-loader/ue-anchor-xrefs.json \
  --format json > build/linux-server-loader/ue-anchor-candidates.json

scripts/validate-elf-signatures.py /path/to/DuneSandboxServer-Linux-Shipping \
  --xref-json build/linux-server-loader/ue-anchor-candidates.json \
  --category ue \
  --format json > build/linux-server-loader/ue-anchor-signature-validation.json
```

The promotion step rejects string targets by default because a literal
`FNamePool` reference is not the global anchor. Confidence: high.
`plan-ue4ss-canary-env.py` reads readiness evidence and emits the next guarded
server env. It defaults to read-only object/reflection discovery and, when the
readiness report includes prepared anchor coverage, refuses hook/live Lua
escalation until required object-discovery groups and ProcessEvent-level
dispatch coverage are present. It also refuses hook/live Lua escalation while
`findObjectSemantics=false`, because object-array registry entries, native
identities, outer-chain full names, and Lua object API calls must be proven
first. Use `--max-stage hook-probe`, `live-hook`, or
`lua-dispatch` only for the matching lab canary phase. `live-hook` and
`lua-dispatch` plans also enable bounded live
ProcessEvent call logging so `ue-process-event-live-context` readiness evidence
is collected in the same canary. The planner also requires
`ueProcessEventHookRuntimeTarget`, `ueProcessEventLiveHookRuntimeTarget`,
`ueProcessEventLiveRuntimeContext`, and
`ueProcessEventLiveRuntimeRegistryContext`; self-test-only or older readiness
evidence stays at hook-probe/live-hook and does not emit live Lua dispatch.
Pass
`--anchor-signatures-file <server-anchor-signatures.txt>` to feed a generated
anchor-signature sidecar into the next read-only server canary; the planner
emits `DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE` and omits empty
`DUNE_PROBE_LOADER_UE_ANCHORS` values. The planner does not emit live Lua dispatch
flags until the readiness report proves the persistent ProcessEvent hook and
native dispatch self-test. If `ueProcessEventLuaHookAliasRouting=false`, the
Lua-dispatch plan emits `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT`
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

The Linux server loader now emits `lua-object-outer-chain` for registered
objects with a non-null `OuterAddress`. The server, native Linux client, and
Windows/Proton real-Lua smoke log again after mod dispatch, so constructed
world/level/actor chains prove reconstructed outer-chain identity on all three
targets. `status=resolved` means each outer hop resolved through known Lua
object handles and the event carries `chain`, `terminalPath`, `terminalClass`,
`reconstructedPath`, `reconstructedFullName`, and `fullNameResolved=true`.
Readiness exposes the reconstructed identity gate as
`luaObjectOuterChainIdentities`. Lua object handles expose
`OuterChainPathName`, `OuterChainFullName`, `HasOuterChainPath`,
`GetOuterChainPathName()`, and `GetOuterChainFullName()`. Confidence: high.

The server, native Linux client, and Windows/Proton loaders also emit
`event=ue-object-native-identity` when a UObject or object-array item promotes
decoded object name, decoded class name, class pointer, and `OuterPrivate` into
the Lua handle. Readiness exposes this as `ueObjectNativeIdentities`, which must
pass before treating loader-owned handles as native UE identity evidence.
Confidence: high for loader-side promotion; live confidence depends on current
build anchor canaries.

Optional read-only UE anchor probes:

```dotenv
DUNE_PROBE_LOADER_UE_ANCHORS=FNamePool=0x0;GUObjectArray=0x0;GWorld=0x0;GEngine=0x0;ProcessEvent=0x0;CallFunctionByNameWithArguments=0x0
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES=
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE=/path/to/server-anchor-signatures.txt
DUNE_PROBE_LOADER_UE_POINTER_PROBE=false
DUNE_PROBE_LOADER_UE_LAYOUT_PROBE=false
DUNE_PROBE_LOADER_UE_LAYOUT_SLOTS=8
DUNE_PROBE_LOADER_UE_UOBJECT_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_NEXT_OFFSET=0x28
DUNE_PROBE_LOADER_UE_REFLECTION_SUPER_OFFSET=0x30
DUNE_PROBE_LOADER_UE_REFLECTION_CHILDREN_OFFSET=0x38
DUNE_PROBE_LOADER_UE_REFLECTION_CHILD_PROPERTIES_OFFSET=0x40
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_LINK_OFFSET=0x48
DUNE_PROBE_LOADER_UE_REFLECTION_FUNCTION_LINK_OFFSET=0x50
DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_WALK=false
DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_PROBE_LOADER_UE_REFLECTION_MAX_FIELDS=16
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_PROBE_LOADER_UE_REFLECTION_FUNCTION_FLAGS_OFFSET=0x58
DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_START=0x48
DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_END=0xa0
DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_MAX_BYTES=16
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE=false
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS=128
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_OFFSET=0
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_ITEM_SIZE=24
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_OBJECT_OFFSET=0
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CHUNK_SIZE=65536
DUNE_PROBE_LOADER_UE_FNAME_PROBE=false
DUNE_PROBE_LOADER_UE_FNAME_POOL=
DUNE_PROBE_LOADER_UE_FNAME_POOL_ADDR=
DUNE_PROBE_LOADER_UE_FNAME_POOL_OFFSET=0
DUNE_PROBE_LOADER_UE_FNAME_BLOCKS_OFFSET=0x10
DUNE_PROBE_LOADER_UE_FNAME_STRIDE=2
DUNE_PROBE_LOADER_UE_FNAME_MAX_LENGTH=128
DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS=false
DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS_MAX=16
DUNE_PROBE_LOADER_UE_SELF_TEST_ANCHOR=false
```

These probes are read-only. They report whether configured runtime addresses are
mapped, whether anchor pointers resolve to mapped targets, whether target memory
looks like expected UE layouts, and whether bounded object-array/FName reads can
produce Lua object handles. The probes do not install live UE hooks and do not
write game memory. Confidence: high for the self-test anchors, moderate for live
server anchors until a one-map canary supplies valid addresses.

`DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES` and
`DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE` use the same `name=aa bb ??`
syntax as scan signatures, but only unique runtime matches are promoted to UE
anchors before pointer/layout/UObject/FName probes run. Missing and ambiguous
matches log `event=ue-anchor-signature` and are skipped. Use `Name@hit+N`,
`Name@riprel32+N`, `Name@callrel32`, or `Name@ptr+N` when a signature match
must be transformed into the anchor address. Confidence: high.
Generate this file with
`scripts/export-elf-signature-manifest.py --format anchor-signatures` after a
same-build validation pass.

Export second-pass server anchor env from a scan log:

```bash
scripts/export-ue-anchor-env.py /tmp/dune-server-probe-loader.log \
  --loader server \
  --platform server \
  --format env > ue-server-anchors.env

scripts/export-ue-anchor-env.py /tmp/dune-server-probe-loader.log \
  --loader server \
  --platform server \
  --include-runtime-candidates \
  --format env > ue-server-runtime-root-candidates.env

scripts/prepare-ue-anchor-canary.py \
  --platform server \
  --binary /path/to/DuneSandboxServer-Linux-Shipping \
  --loader-log /tmp/dune-server-probe-loader.log \
  --include-runtime-candidates \
  --output-dir build/linux-server-loader/server-anchor-canary

scripts/plan-ue4ss-canary-env.py \
  --platform server \
  --server-log /tmp/dune-server-probe-loader.log \
  --max-stage read-only \
  --format json \
  > build/linux-server-loader/next-canary.json

scripts/plan-ue4ss-canary-env.py \
  --platform server \
  --server-log /tmp/dune-server-probe-loader.log \
  --max-stage read-only \
  > build/linux-server-loader/next-canary.env
```

The JSON plan feeds candidate-aware gap reporting; the env plan emits
`DUNE_PROBE_LOADER_UE_ANCHORS` plus the read-only pointer, layout, UObject,
object-array, and FName probe toggles for the Linux server loader.
`export-ue-anchor-env.py` exports only mapped explicit anchors and resolved
`ue-anchor-signature` records by default. Raw `scan-hit` rows are candidate
evidence for xref/signature promotion, not explicit anchor addresses; use
`--include-scan-hits` only for a documented manual exception. The readiness
core-anchor gates use the same conservative evidence rule: plain scan hits do
not pass `ue-names`, `ue-objects`, `ue-world`, `ue-dispatch`, or
`ue-reflection-surface`. Confidence: high.
The canary-prep helper emits the same env plus the corresponding signature and
readiness artifacts so the follow-up launch has one auditable input directory;
the env includes `DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE` pointing at the
generated anchor-signature sidecar.
The canary env planner turns that readiness evidence into the next guarded
environment file, keeping hook-probe/live-hook/Lua-dispatch escalation behind an
explicit `--max-stage` boundary and requiring live-hook evidence before live Lua
dispatch planning. It also re-checks proven anchor provenance itself: if a
readiness JSON lacks `anchorGroupProvenance=true`, claims object discovery
without proven names/objects/world anchor groups, or claims hook-capable stages
without a proven dispatch anchor, the plan stays in read-only object/reflection
discovery and does not emit ProcessEvent hook or Lua dispatch variables.
JSON/Markdown output includes machine-readable `blockers[]` entries with stable
`code`, blocked `stage`, message fields, and `nextCanaryContract` records
`anchorGroupProvenance`, `objectDiscoveryCoverage`,
`processEventRuntimeEvidence`, `registryRuntimeEvidence`, and
`postCanaryVerification` for automation.
The planner now keeps the next canary
at object-discovery/reflection when `luaObjectRegistryRuntime`,
`luaFunctionRegistryRuntime`, `luaDecodedObjectAliasesRuntime`, or
`ueObjectArrayRegistryRuntime` are missing or self-test-only, and at
Lua-dispatch when `luaFunctionIterationRuntime` is missing or self-test-only.
Confidence: high.

Optional loader-owned dispatch self-tests:

```dotenv
DUNE_PROBE_LOADER_HOOK_SELF_TEST=false
DUNE_PROBE_LOADER_MOD_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_LIBRARY=
DUNE_PROBE_LOADER_LUA_REFLECTION_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_REFLECTION_RAW_SET_ENABLED=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_PROBE_LOADER_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_MODS_ENABLED=false
DUNE_PROBE_LOADER_LUA_MOD_SCRIPTS=
DUNE_PROBE_LOADER_LUA_MOD_DISPATCH_SELF_TEST=false
DUNE_PROBE_LOADER_GAME_DIR=
DUNE_PROBE_LOADER_UNREAL_VERSION_MAJOR=5
DUNE_PROBE_LOADER_UNREAL_VERSION_MINOR=0
```

The local smoke runs these against `/usr/bin/true`:

```bash
scripts/smoke-linux-server-loader.sh
```

Passing `event=lua-reflection-self-test` proves integer, boolean, float,
double, string, object-handle, function-call, and read-only raw
reflected-candidate lookup against a loader-owned object when the bounded value
probe has populated the candidate registry. It also proves bounded
`FArrayProperty:GetInner()` metadata through `arrayInnerPropertyHits=1` and
bounded `FEnumProperty:GetEnum()` / `GetUnderlyingProperty()` metadata through
`enumPropertyHits=1 enumUnderlyingPropertyHits=1`, and bounded `FSetProperty`
element plus `FMapProperty` key/value metadata through
`setElementPropertyHits=1 mapKeyPropertyHits=1 mapValuePropertyHits=1`.
It also proves bounded `FProperty:ImportText()` text-to-value writes through
`importTextHits=1` and bounded `FProperty:ExportText()` value-to-text exports
through `exportTextHits=1`. Property descriptor metadata accessors are proven
through `propertyMetadataHits=7`, and descriptor-level `GetValue()` /
`SetValue()` plus shorthand `get()` / `set()` on loader-owned descriptors is
proven through `descriptorValueGetHits=21 descriptorValueSetHits=9
descriptorValueAliasHits=3`.
The Lua object API now includes `StaticFindObject`, `FindObject`,
`FindFirstOf`, `GetKnownObjects`, `FindObjects`, `FindAllOf`,
`ForEachUObject`, `IsA`, and `LoadAsset`. Those calls operate on the loader
registry: self-test handles, class-mapped `ue-uobject` candidates, bounded
object-array candidates, and synthetic objects created by
`StaticConstructObject`. Synthetic construction now preserves `ClassAddress`
when the class argument is a known object or `UClass` handle. `LoadAsset`
currently resolves only already-known registry handles by path/name and returns
`nil` for unknown assets. `GetLoadAssetBackendState()` makes that explicit with
`Backend="registry"`, `RegistryFallback=true`, and
`PackageBackendArmed=false`; it also reports package-anchor visibility with
`PackageBackendAvailable`, `StaticLoadObjectResolved`, `LoadObjectResolved`,
`LoadPackageResolved`, and `ResolveNameResolved`. This gives mods a
UE4SS-shaped object API before the backend is replaced with full `GUObjectArray`
enumeration and real package loading.
Readiness now exposes that missing backend separately as
`luaLoadAssetPackage=false`; `luaLoadAssetBackendState=true` only proves the
guarded backend contract was exercised from a mod,
`luaLoadAssetBackendAnchors=true` proves the same check saw package-loading
anchors, `luaLoadAssetPackageBridgeState=true` proves a mod queried the guarded
native package bridge status and saw the selected target/mapping/gate state, and
`luaLoadAssetPackageAbiState=true` proves a mod queried the guarded native
package-call ABI contract and saw the selected platform ABI, signature family,
and still-false `AbiVerified`/`CallFrameReady` gates.
`luaLoadAssetPackageStringBridge=true` proves a mod staged bounded UTF-8 package
path input for the native string bridge while `TCharEncoding` remained
`unverified-live-build` and `TCharBridgeReady`, `NativeBufferReady`, and
`NativeInvoked` stayed false.
`luaLoadAssetPackageNativeBuffer=true` proves a mod staged a bounded,
NUL-terminated UTF-8 native input buffer descriptor while `TCharBufferReady`,
`CallFrameReady`, and `NativeInvoked` stayed false.
`luaLoadAssetPackageTCharBuffer=true` proves a mod queried the target-specific
candidate `TCHAR` layout descriptor and saw `CandidateUnitBytes` and
`CandidateBufferBytes`, while `TCharLayoutVerified`, `TCharBufferReady`,
`CallFrameReady`, and `NativeInvoked` stayed false.
`luaLoadAssetPackageTCharVerification=true` proves a mod queried the evidence
gate that can accept explicit canary-provided `TCHAR` unit-size evidence; by
default it reports `evidenceProvided=false`, `verificationEnabled=false`, and
still-false `TCharLayoutVerified`/`TCharBufferReady`.
`luaLoadAssetPackageCallFrameVerification=true` proves a mod queried the
composed package-call readiness gate. That gate combines bounded path staging,
resolved package target evidence, explicit package ABI confirmation, and
verified `TCHAR` layout evidence, while still reporting `NativeInvoked=false`.
`luaLoadAssetPackageCallFrame=true` proves a mod staged a package path into the
guarded call-frame descriptor and saw `PathStaged=true` and
`ArgumentDescriptorReady=true`, while `TCharBridgeReady`, `CallFrameReady`, and
`NativeInvoked` stayed false.
`luaLoadAssetPackageNativeInvoke=true` proves a mod exercised the guarded
`InvokeLoadAssetPackageNative(path, {Invoke=true})` checkpoint while the loader
returned `Invoked=false`. `NativeBridgeArmed` can become true only after the
package ABI, `TCHAR`, call-frame, and invoke-env gates all pass; the checkpoint
still does not call UE.
`luaLoadAssetPackageNativeCallAdapter=true` proves a mod queried the ABI-specific
call-adapter layer that will sit immediately before the future native package
load call. It still reports `NativeInvoked=false`.
`luaLoadAssetPackagePreflight=true` proves a mod requested the
guarded package path with `LoadAsset(path, {Backend="package"})`,
`{Package=true}`, `{TryPackage=true}`, or the dry-run environment gate and hit
the intentional `native-bridge-missing` stop. It does not prove package loading.
`luaObjectApi=true` only proves registry-backed lookup/enumeration,
not Unreal package loading. The stricter
`ue4ssLuaApiComplete` aggregate stays false until staged Lua dispatch and real
package-backed `LoadAsset` evidence both pass.
The shared `ue` scan preset now includes `StaticLoadObject`, `LoadObject`,
`LoadPackage`, and `ResolveName`; those are read-only anchor candidates for the
next canary, not enabled package-loading calls. Readiness reports proven
package anchors as `packageLoadingSurface` and prepared canary package coverage
as `anchorCoveragePackageLoading`.
`NotifyOnNewObject(filter, callback)` is bounded to the synthetic construction
path for now: it stores up to 32 class/path/name filter registrations and
dispatches every matching callback when loader-owned `StaticConstructObject`
creates a matching handle. The default Lua dispatch self-test requires
`notifyOnNewObjectCallbacks=1`, `notifyOnNewObjectResult=17`, and
`notifyOnNewObjectStatus=0`. It is not a live Unreal object-construction hook yet.
Returned object/function handles now include the first UE4SS-style method layer:
`GetFullName`, `GetName`, `GetPathName`, `GetAddress`, `IsValid`, `GetClass`,
`GetOuter`, `GetWorld`, `GetFName`, `type`, `IsClass`, `IsAnyClass`, `IsA`,
flag checks, `GetPropertyValue`, `SetPropertyValue`, `CallFunction`,
`ProcessConsoleExec`, `ULocalPlayerExec`, `GetFunctionFlags`,
`SetFunctionFlags`, `GetSuperStruct`, `GetSuper`, `GetSuperClass`,
`ForEachFunction`, `ForEachProperty`, `GetCDO`, `GetDefaultObject`,
`GetDefaultObj`, `IsChildOf`, and `GetLevel`.
Handles expose scan-derived `ClassAddress`, `OuterAddress`, and `SuperAddress`
where available. `GetClass` now returns a `UClass` handle with the live scanned
`ClassPrivate` address for promoted candidates and address zero for purely
synthetic entries. `GetOuter` resolves only the loader-owned outer for synthetic
constructed objects, and `GetSuperStruct`, `GetSuper`, and `GetSuperClass`
prefer scanned super pointers before
falling back to the synthetic `UObject` base for non-`UObject` synthetic
`UClass` handles. `IsChildOf` now walks the bounded scan-derived
`SuperAddress` chain when both class handles carry live addresses, while full
hierarchy enumeration still waits on a real `GUObjectArray` backend. `GetWorld`
now resolves registered world-like handles and loader-owned outer chains, with
a conservative `GWorld`/`UWorld`-like fallback for common world-context classes;
it is not a live engine `UObject::GetWorld` call yet. The global `GetWorld()`
helper uses the same bounded world-like handle resolution, while the global `GetEngine()`
helper returns a discovered engine-like handle or creates one loader-owned `UEngine`
handle until live `GEngine` promotion exists.
After Lua mod dispatch, the loaders emit `lua-global-runtime-helper-check` with
`globalWorldPromoted` and `globalEnginePromoted` so canaries can distinguish
loader-owned fallback handles from UE-promoted handles.
`GetCDO`, `GetDefaultObject`, and `GetDefaultObj` now return a
loader-owned `Default__<Class>` handle for `UClass` handles with
`RF_ClassDefaultObject` set, and `GetLevel` resolves registered level-like
handles through loader-owned outer chains. Neither path calls the live engine
implementation yet. `HasAllFlags`/`HasAnyFlags` use promoted
`ObjectFlags` for scanned UObject candidates; `HasAnyInternalFlags` uses
promoted `InternalFlags` when the object-array item flags word is readable and
returns false for handles without decoded internal flag metadata;
`GetFunctionFlags` returns promoted `FunctionFlags` for scanned UFunction
handles when readable.
`SetFunctionFlags` mutates loader-owned Lua handle metadata and syncs matching
loader registry entries, but it does not write live UFunction memory.
`ForEachFunction` iterates unique promoted `UFunction` handles for
loader-owned self-test handles and scanned object/class handles whose address,
`ClassAddress`, name, or class matches a promoted UFunction owner through the
same bounded registry as `GetKnownFunctions`; it is not full live `UStruct`
function-chain traversal yet. Passed iteration emits
`event=lua-function-iteration-check status=passed`; `mode=owner` is required
for `luaFunctionIterationRuntime=true`.
`ProcessConsoleExec` now dispatches loader-owned
`RegisterProcessConsoleExecPreHook` callbacks, then
`RegisterConsoleCommandHandler`/`RegisterConsoleCommandGlobalHandler`
callbacks with `(context, command, args)`, then
`RegisterProcessConsoleExecPostHook` callbacks. Console exec hooks receive
`(context, rawCommand, command, args, handled)` and may return boolean true to
mark the command handled. It is not wired to the live engine console path yet.
`ULocalPlayerExec` dispatches loader-owned
`RegisterULocalPlayerExecPreHook` callbacks and
`RegisterULocalPlayerExecPostHook` callbacks with the same
`(context, rawCommand, command, args, handled)` shape. It is not wired to live
`ULocalPlayer::Exec` yet.
`CallFunction` and `CallFunctionByNameWithArguments` now dispatch loader-owned
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
`replacement, true` to short-circuit or replace the result. It is not wired to
the live engine `UObject::CallFunctionByNameWithArguments` path yet.
`Reflection()` now returns a loader-owned `UObjectReflection` table for known
handles. `Reflection():GetProperty(name)` resolves self-test properties,
promoted `UFunction` param descriptors, and scalar live reflection candidates
into UE4SS-style property descriptor tables. Those descriptors expose
`GetFullName`, `GetFName`, `IsA`, `GetClass`, `ContainerPtrToValuePtr`,
`ImportText`, `ExportText`, `ExportTextItem`, `GetOffset_Internal`,
`GetOffsetInternal`, `GetElementSize`, `GetSize`, `GetArrayDim`,
`GetPropertyFlags`, `HasAnyPropertyFlags`, `GetPropertyClass`, bool mask helpers, `GetStruct`, `GetInner`,
and `type`. The bounded self-test descriptor set now includes integer, bool,
float, double, string, and object properties. `Object:ForEachProperty(callback)`,
`Function:ForEachProperty(callback)`, and `Reflection():ForEachProperty(callback)`
iterate that bounded descriptor set instead of being pure no-ops where descriptors
exist; the reflection-handle path is tracked as `luaReflectionForEachProperty`.
Lua-dispatch readiness also requires `luaReflectionForEachPropertyRuntime=true`
so self-test-only enumeration cannot satisfy the completion gate.
Promoted scalar live reflection descriptors now support guarded `GetValue()` and
raw-set-enabled `SetValue()`, tracked as `luaReflectionLiveDescriptorValues`.
Completion claims require `luaReflectionLiveDescriptorTypedClassRuntime=true`
and `luaReflectionLiveDescriptorTypedValuesRuntime=true` and
`luaReflectionLiveDescriptorTypedSetValuesRuntime=true` and
`luaReflectionLiveDescriptorValuesRuntime=true` too; otherwise the descriptor
evidence is still generic, missing decoded `FProperty` class identity, missing
typed `GetValue()` proof, or loader-owned `SelfTest*` coverage rather than a
promoted non-self-test descriptor. Typed live `GetValue()` currently covers
guarded bool, float, double, object/class/interface, FName, and
FString-shaped `FStrProperty`, FVector-sized `FStructProperty`, and
integer/byte/enum-sized values where the live descriptor class and element size
are known. With the raw-set gate enabled, live `SetValue()` also supports the
bounded scalar path, including byte/enum-sized integer writes, plus
FString-shaped `FStrProperty` strings and
FVector-sized `FStructProperty` tables. This is still a shim: there is no
complete live `FProperty` chain traversal, FText/container storage marshaling,
or general struct-field marshaling yet.
The global compatibility shim now also covers `FName`, `FText`,
`ExecuteInGameThread`, `DrainGameThreadQueue()`, immediate
`ExecuteAsync`/`ExecuteWithDelay`/`LoopAsync`, keybind/console/custom-event
registration names, `RegisterConsoleCommandGlobalHandler`,
`RegisterProcessConsoleExecPreHook`, `RegisterProcessConsoleExecPostHook`,
`RegisterCustomProperty` with the `PropertyTypes` table,
`RegisterCallFunctionByNameWithArgumentsPreHook`,
`RegisterCallFunctionByNameWithArgumentsPostHook`,
`RegisterULocalPlayerExecPreHook`, `RegisterULocalPlayerExecPostHook`,
`RegisterLocalPlayerExecPreHook`, `RegisterLocalPlayerExecPostHook`,
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
The Lua dispatch canary now reports dedicated scheduler and input/command
counters, including `executeAsyncCalls`, `executeWithDelayCalls`,
`loopAsyncCalls`, `keyBindLookupHits`, `keyBindCallbackHandled`,
`consoleCommandHandlers`, and
`consoleCommandGlobalHandlers`; direct keybind and console dispatch through
`DuneProbeDispatchKeyBind(context, key)` and
`DuneProbeDispatchConsoleCommand(context, rawCommand)` additionally report
`keyBindDispatchCalls`, `consoleCommandHandlerCalls`, and
`consoleCommandGlobalHandlerHandled`, so
readiness can distinguish these compatibility families from object lookup and
hook dispatch.
`IterateGameDirectories`, UE4SS metadata
tables (`UE4SS`, `UnrealVersion`, `ModRef`), flag/property/key constant tables
(`EObjectFlags`, `EInternalObjectFlags`, `PropertyTypes`, `Key`,
`ModifierKey`, and `ModifierKeys`),
loader-local `ModRef` shared variables, and per-mod `ModRef` context through
`GetModName()`, `GetModPath()`/`GetModDir()`, `GetModScriptPath()`, and
`GetModScriptDir()`. The loaders prepend the active script directory to
`package.path`, so mod-local `require()` works for sibling and nested Lua files;
explicit sibling `dofile()` is supported through `ModRef:GetModScriptDir()`.
Loaded mods also get a UE-shaped `ProcessEvent(object, functionOrName[, args])`
global and `object:ProcessEvent(functionOrName[, args])` method on all three
loader targets. This is currently a compatibility alias for the same
hook-aware bounded call shim used by `CallFunction`; it is not live engine
`UObject::ProcessEvent` invocation until the runtime hook bridge is armed.
Canaries require `processEventCompatCalls=2` and `processEventCompatHits=2` in
`lua-mod-finish`; summaries expose `luaProcessEventCompatModFinishCount`, and
readiness keeps `luaProcessEventCompat` plus aggregate `luaDispatch` closed
until at least one loaded mod proves both compatibility routes.
Loaded mods can also call `GetProcessEventBridgeState()` to inspect whether the
persistent native hook/trampoline bridge is armed. Canaries require
`processEventBridgeStateCalls=2`, summaries expose
`luaProcessEventBridgeStateModFinishCount`, and readiness keeps
`luaProcessEventBridgeState` plus aggregate `luaDispatch` closed until a loaded
mod proves that introspection surface.
Loaded mods also get `InvokeProcessEventNative(object, function, {Value=n})`.
This now separates registry readiness from execution readiness:
`ObjectAllowed` requires a registered object address, `FunctionAllowed` requires
promoted `UFunction` descriptor evidence, and `SelfTestCallable` is only true
for the loader-owned self-test object/function that can safely run through the
current trampoline. It does not provide arbitrary live UE ProcessEvent
invocation yet. Canaries require
`event=lua-process-event-native-invoke-self-test status=passed` with
`ObjectRegistryAllowed=true`, `FunctionDescriptorAllowed=true`,
`SelfTestCallable=true`, `processEventNativeCalls=2`, and
`processEventNativeHits=1`; summaries expose
`luaProcessEventNativeInvokeSelfTestCount`,
`luaProcessEventNativeInvokeNonSelfTestGateCount`, and
`luaProcessEventNativeInvokeNonSelfTestInvokedCount`. Readiness reports
`luaProcessEventNativeInvoke=true` from the self-test evidence and
`luaProcessEventNativeInvokeNonSelfTestGate=true` when the descriptor-backed
non-self-test preflight is proven to stop at the closed safety gate.
Loaded mods can also call `CreateProcessEventParams(function)`. The API builds
a bounded loader-owned params buffer from promoted descriptors and returns the
same `ProcessEventParams` table shape used by live hook callbacks, including
`Properties` and direct aliases such as `params.Value`. The Linux server,
native Linux client, and Windows/Proton smokes prove `SetParamValue`,
`GetParamValue`, and shorthand descriptor access against that buffer outside an
active callback. This is the params marshaling prerequisite for broader native
ProcessEvent invocation, not the invocation step itself. Readiness exposes this
direct construction proof as `luaProcessEventParamsBuffer`.
`InvokeProcessEventNative` now exposes the matching no-call preflight layer:
`DescriptorBackedCallable`, `ParamsBufferConstructible`,
`ParamsDescriptorCount`, `ParamsBufferSize`, `InvokeRequested`, and
`NativeNonSelfTestEnabled`. A non-self-test target with object registry,
function descriptor, armed bridge, and constructible params reports
`descriptor-preflight-ready`; `{Invoke=true}` reports
`non-self-test-invoke-disabled` until the target-specific opt-in env is set,
and that closed-gate evidence feeds
`luaProcessEventNativeInvokeNonSelfTestGateCount`. Readiness exposes the
no-call state as `luaProcessEventNativeInvokeDescriptorPreflight` and the
closed explicit-invoke state as `luaProcessEventNativeInvokeNonSelfTestGate`.
With both gates open, the loader seeds a descriptor-sized params buffer from matching Lua table fields,
calls the original ProcessEvent trampoline, and reports
`NativeNonSelfTestInvoked=true`, `ParamsWritten=<n>`, and
`status=non-self-test-invoked`.
`FName` uses the method shape expected by Lua mods, including `ToString()` and
`GetComparisonIndex()`. `FName(index[, number])` and
`DecodeFName(index[, number])` use the active `FNamePool` resolver when present
and return a table with `Name`, `String`, `ComparisonIndex`, `Number`, and
`IsDecoded`; without a resolver, `IsDecoded=false`.
Root-discovered mods honor a UE4SS-style `mods.txt`: `ModName` and `+ModName`
load in file order, `-ModName` or `!ModName` disables a root mod, and
`lua-mod-start` reports `manifestEntries`/`manifestDisabled`.
Loaded mods can register loader-owned `RegisterModInitCallback`,
`RegisterModPostInitCallback`, and `RegisterModUnloadCallback` handlers;
`lua-mod-finish` reports `modInitCallbacks`, `modPostInitCallbacks`,
`modUnloadCallbacks`, `modInitCalls`, `modPostInitCalls`, `modUnloadCalls`,
`modInitHandled`, `modPostInitHandled`, and `modUnloadHandled`.
When live ProcessEvent Lua dispatch is enabled, enabled Lua mods also load into
the persistent live ProcessEvent Lua state, report
`lua-live-mod-start`/`lua-live-mod-finish`, dispatch `ModInit`/`ModPostInit`
when armed, remain registered for live hook dispatch, and dispatch `ModUnload`
when that live state closes.
Loader-owned ids now represent active registrations and can be released through
`UnregisterKeyBind`, `UnregisterConsoleCommandHandler`,
`UnregisterCustomEvent`, lifecycle unregister functions, and
`UnregisterModUnloadCallback`; unregistering compacts the active registrations
and releases the Lua registry ref on native Linux and Proton/Windows paths. The
shared smoke contract requires
`callbackUnregisterCalls=16 callbackUnregisterHits=16` for the UE4SS-style
callback families.
These unblock mods that probe for UE4SS APIs or do setup without registering
hooks, but they are not real scheduler threads, timers, key events, console
command dispatch, or live engine lifecycle callbacks yet. Loader-owned
custom-event and lifecycle dispatch shims now exercise registered Lua refs, but
they are not wired to live `LoadMap`, `BeginPlay`, or `InitGameState` callsites.
Passing `event=lua-process-event-self-test` proves Lua callback dispatch through
a loader-owned `ProcessEvent(UFunction*, void*)` stand-in. The default Lua
script also exercises guarded `GetParamValue`/`SetParamValue` access against
the loader-owned params block and logs
`paramDescriptorHits=2 paramDescriptorLookupHits=17
functionParamDescriptorHits=2 paramGetHits=29 paramSetHits=11`. The `Params`
table also includes descriptor
metadata under `Properties`, and Lua retrieves handles through
`GetParamDescriptor`. `Params.<Name>` and `Params.Values.<Name>` also expose
loader-owned `RemoteUnrealParam`-style wrappers with `get()`, `Get()`, `set()`,
`Set()`, and `type() == "RemoteUnrealParam"`. The default params fixture now
covers bool, byte-sized `FEnumProperty` values, object, `FName`,
`FStrProperty`, an `FVector`-shaped
`FStructProperty` whose `GetStruct()` returns a synthetic
`/Script/CoreUObject.Vector` `UScriptStruct`, signed/unsigned integers, and
`float`/`double` scalar get/set paths. `RegisterHook` returns `preId, postId` pairs and
`UnregisterHook` removes temporary registrations. The ProcessEvent scripts keep
a non-target hook registered before the target hook to prove route filtering,
so the target hook id result is `4`. Lua can also call `GetFunctionParamDescriptors` or
`GetFunctionParams` on `ctx.Function` to retrieve a function-scoped descriptor
table with `PropertyCount` and `Properties`. Mods can resolve the promoted
runtime function registry with `FindFunction(pathOrName)`,
`FindFirstFunction()`, and `GetKnownFunctions()`, which returns a table keyed by
runtime `PathName` plus `Count`; `ForEachUFunction(callback[, filter])`
enumerates the same promoted registry globally, and compatible owner/class
handles can enumerate owner-matched promoted functions with
`ForEachFunction(callback)`. These APIs only expose UFunctions already
discovered by bounded runtime probes. The `functionLink` descriptor probe
provides parameter descriptors when reflection layout is known; the
GUObjectArray walk can now promote a function-only runtime identity when an
object-array item's decoded native class contains `Function`. That function-only
path proves registry identity and lookup, not parameter descriptors. These
object-array UFunction descriptors are owned by the UFunction's decoded
`OuterPrivate` object when that outer is readable, falling back only when no
outer is available. That matters because `ForEachFunction` owner matching and
UE4SS-style hook path construction should bind functions to their declaring
class/object, not to the `UFunction` class object itself. Function-only identity
descriptors stay visible to `FindFunction`, `GetKnownFunctions`,
`ForEachUFunction`, and owner `ForEachFunction`, but they do not count as
parameter descriptors unless they have a real reflected field address. This
prevents object-array identity discovery from falsely satisfying ProcessEvent
parameter descriptor readiness. The routing self-test registers a
nonmatching hook plus the target hook, so `hooks=2` with
`preCalls=1 postCalls=1` proves known-path `RegisterHook` filtering through
`ctx.functionPath`. Hook routing matches exact paths first and then falls back
to the terminal function name, so a UE4SS-style `/Script/...` registration can
match a discovered `/RuntimeProbe/<Outer>.<Function>:Function` runtime path
without allowing the non-target hook to fire. Canary logs expose this as
`pathExactMatches` and `pathAliasMatches`. Passing
`event=lua-mod-dispatch-self-test` proves a Lua script entrypoint can register
callbacks and have those callbacks invoked by native code. `RegisterHook` is a
bounded registry with up to 32 hook registrations, so a later mod script does
not replace earlier pre/post callbacks for the loader-level dispatch path. None
of these events prove live typed `FProperty` marshaling yet. Unknown live
`UFunction` paths remain permissive until real path/name discovery is proven.
Confidence: high.

Set `DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_WALK=true` after the read-only
UObject, FName, and UClass slot probes are stable. It walks bounded
`children`, `childProperties`, `propertyLink`, and `functionLink` chains and
logs `event=ue-reflection-field status=candidate`. This is the server-side
equivalent of the client field/function discovery gate; it proves candidate
reflection-chain visibility, not live `FProperty` marshaling. Confidence: high
for the synthetic smoke fixture, moderate for live Dune until offsets are
validated on the current build.

Set `DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_PROBE=true` after the field walk
is stable. It implies the bounded field walk and reads property-shaped
descriptor fields from `childProperties` and `propertyLink`: `ArrayDim`,
`ElementSize`, `PropertyFlags`, and `Offset_Internal`. It logs
`event=ue-reflection-property status=candidate`. This is descriptor telemetry,
not live `FProperty` marshaling. Confidence: high for the synthetic smoke
fixture, moderate for live Dune until offsets are validated on the current
build. For each bounded `functionLink` candidate, the same probe also reads
function-level `FunctionFlags`, `childProperties`, and `propertyLink` roots and emits
`event=ue-function-param-root` plus `event=ue-function-param` descriptor lines
when param metadata is readable. Readable descriptors and readable
`FunctionFlags` values are promoted into the bounded live `UFunction` param
registry. The loader-owned `/RuntimeProbe/RuntimeProbeObject` smoke path now
proves non-`SelfTest*` runtime descriptor enumeration, typed `GetValue()`, and
typed `SetValue()`, plus owner-mode `ForEachFunction` parity with Linux client
and Proton/Windows. Owner-mode iteration also emits a runtime
`lua-function-registry-check` after path/runtime-path/name/address/flags lookup
succeeds. That is
runtime-provenance hardening, not proof of live Dune `FProperty` offsets; the
live canary still has to validate real object/property layout.
The parity fixture also includes a UE-shaped
`/RuntimeProbe/RuntimeProbeUObject` with a non-`SelfTest*` class/FName. It flows
through the normal `ue-uobject` scanner and logs
`registryProvenance=runtime`, so `luaObjectRegistryRuntime=true` is now proven
on Linux server, native Linux client, and Windows/Proton without counting the
synthetic `source=runtime-probe` handle.
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
this as `ueFunctionNativeIdentities`. When FName/class
reads are available, the registry carries decoded `fieldClassName`/`ClassName` so Lua
can distinguish scalar, bool, object-pointer, `FName`, and `FString` params.
This is server-side
descriptor visibility, not full live `FProperty` marshaling.

Set `DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_PROBE=true` after descriptor offsets
are stable. It implies descriptor probing and reads up to
`DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_MAX_BYTES` raw bytes from the owning
object at `Offset_Internal`, logging `event=ue-reflection-value status=read`
with `fieldName`, `raw`, and `rawLe`. Successful reads are registered as
read-only Lua raw property candidates keyed by decoded field names such as
`SelfTestUObjectName_0` when the FName reader is available, with positional
fallback keys such as `propertyLink[0]`; Lua `GetPropertyValue` re-reads
1/2/4/8-byte scalar candidates from the owning object through the same guarded
memory checks. The reflection self-test queries `/RuntimeProbe/SelfTestUObject`
by both positional raw path and decoded field-name alias. If
`DUNE_PROBE_LOADER_LUA_REFLECTION_RAW_SET_ENABLED=true`, `SetPropertyValue` can
write bounded 1/2/4/8-byte scalar candidates only when the destination range is
writable; keep it false for read-only live canaries. The smoke fixture enables
it only against loader-owned memory and expects `rawPropertySetHits=1
rawPropertySetValue=17` plus `rawPropertyHits=3 namedPropertyHits=1`. This is bounded server-side
value telemetry and live raw Lua scalar get/set, not typed `FProperty`
marshaling. The Lua reflection self-test also covers loader-owned
`FNameProperty` and `FTextProperty` get/set surfaces, with readiness reported as
`luaReflectionNameTextPropertyValues=true`, and bounded array inner metadata as
`luaReflectionArrayInnerProperty=true`, and bounded enum metadata as
`luaReflectionEnumProperty=true`. The same smoke path proves loader-owned
`FEnumProperty` value `GetValue()` / `SetValue()` plus enum `ImportText()` /
`ExportText()`; real live `FText` mutation, arbitrary live property ImportText
dispatch, and arbitrary container storage marshaling still require
target-layout proof. Confidence: high
for the synthetic smoke fixture, moderate for live Dune until offsets are
validated on the current build.

Set `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE=true` after a unique
`ProcessEvent` target exists through
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_ADDRESS`,
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ADDRESS`, explicit UE anchors, or
signature-resolved UE anchors. The probe validates that the target is mapped and
executable. With `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=true`, it
temporarily installs the inline hook and restores the original bytes before
returning. Use
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=true` only for
loader-owned smoke tests. This is the live-target hardening gate before a
persistent ProcessEvent dispatcher, not the dispatcher itself. Confidence:
high.

Set `DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE=true` after a unique
`CallFunctionByNameWithArguments` target exists through explicit anchors,
`DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_ADDRESS`, or signature-resolved UE
anchors. With `DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_INSTALL=true`, it
temporarily installs and restores `CallFunctionHookProbe`; use
`DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=true` only for
loader-owned smoke tests. This proves hookability, not live command/function
marshaling. Confidence: high.

Set `DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK=true` after the guarded
CallFunction hookability probe passes on the same resolved target. The scaffold
resolves from `DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS`, the
hook-probe address, the generic CallFunction address, explicit anchors, or
signature-resolved UE anchors. It installs once, calls the original through the
trampoline, optionally logs bounded calls, and restores on loader unload. This
gives the Linux dedicated-server path the same persistent interception spine as
Linux native client and Proton/Windows client; live command/function marshaling
remains gated on runtime object and command parsing evidence. Confidence: high.

Set `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK=true` only after the guarded
hookability probe passes on the same resolved target. The scaffold resolves the
target from `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS`, the
hook-probe address, the generic ProcessEvent address, explicit anchors, or
signature-resolved anchors. It installs once, leaves the hook active for the
process lifetime, calls the original through the trampoline, optionally logs
bounded calls, and restores on loader unload. When bounded call logging is
enabled, `event=ue-process-event-live-context status=resolved` proves sampled
raw `Object`/`Function`/`Params` pointers resolved to a Lua-visible object
handle, a runtime-provenance `UFunction` path plus runtime function path, a
nonzero params pointer, and promoted function param descriptors. Self-test
provenance remains logged as `status=partial` and does not satisfy native
runtime identity. The same bounded sample emits
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
Current parity smokes have `luaObjectRegistryRuntime=true`,
`luaFunctionRegistryRuntime=true`, `luaFunctionIterationRuntime=true`, and
`ueObjectArrayRegistryRuntime=true` on all three targets. Aggregate
`luaDispatch` remains false because `ueProcessEventLiveRuntimeContext` and
`ueProcessEventLiveRuntimeRegistryContext` still require live/runtime evidence.
Current loader builds append `registryProvenance=runtime|self-test` to
`lua-object-registry`, `lua-object-registry-check`,
`lua-function-registry-check`, and `lua-function-iteration-check` lines.
Readiness prefers that explicit field and falls back to name/path heuristics
only for older logs. Confidence: high.
The next-canary planner now records that rule in
`registryRuntimeEvidenceContract` and records equivalent ProcessEvent hook
requirements in `processEventRuntimeEvidenceContract`. Post-canary summaries
must show registry rows with `registryProvenance=runtime`, live context rows
with `functionProvenance=runtime`, and hook target rows with
`selfTestTarget=false callSelfTest=false` plus target-image anchor/signature
or explicit target provenance before escalation. Confidence: high.
The planner also records `callFunctionRuntimeEvidenceContract`; live
CallFunction parity requires the same non-self-test hook target evidence plus
`ue-call-function-live-hook ... luaDispatch=true` before the CallFunction Lua
hook bridge is treated as runtime-backed. Confidence: high.
Readiness exposes the combined promoted
runtime registry plus active-param accessor proof as
`ueProcessEventLiveClassAwareParamValues`; self-test provenance does not count.
The same bounded sample emits
`event=ue-process-event-live-param` for descriptor-backed scalar, bool,
object-pointer, `FName`, `FString`, and vector reads from the active params
block, and readiness counts those param rows only when the sampled ProcessEvent
context is runtime-proven. For arrays it emits `status=container` and Lua
`GetParamValue` returns
an `FScriptArray` table with `Data`, `Num`, `Max`, `BytesHex`, address, offset,
class, type, and size metadata. If the array data pointer is readable, the
table also includes `DataSampleAddress`, `DataSampleReadSize`, and
`DataSampleBytesHex`, and the log value includes `dataSampleHex=...`.
`FScriptArray` tables expose `GetNum()`, `NumElements()`, `GetData()`,
`GetDataSampleBytes()`, `GetRawElement(index, byteCount)`, and
`GetElement(index)`. `GetElement` uses promoted `Inner*` metadata when present
to decode bounded scalar, object, `FName`, `FString`/`FText`, and `FVector` elements;
unsupported element classes return a raw element table with `BytesHex`. For sets and maps it emits
`FScriptSetHeader` and `FScriptMapHeader` tables with `GetNum()`,
`NumElements()`, `GetData()`, and bounded raw reads. Sets expose
`GetRawEntry(index, byteCount)`, `GetRawElement(index, byteCount)`, and
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
key/value metadata, keeping Linux client, Linux server, and Proton/Windows
readiness evidence symmetric. The bounded scan window defaults to `0x48..0xa0`
via
`DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_START` and
`DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_END`. Promoted live param
descriptors expose decoded children to Lua as `ContainerChildren` plus
`GetInner()`, `GetElementProperty()`, `GetKeyProperty()`, and
`GetValueProperty()` where applicable.
Raw `byteCount` stays caller-supplied, and live-build `FScriptSet`/`FScriptMap`
sparse slot layout still needs validation before treating every slot as a typed
occupied element.
Unsupported complex values, including non-vector structs, still emit
`status=raw value=rawHex=...` and Lua returns a `RawUnrealParam` table. It still
does not perform complete arbitrary container element unmarshaling or complete
live `FProperty` object marshaling.
Confidence: high.

Set `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true` with the live
hook scaffold in a smoke/lab run to arm native ProcessEvent pre/post callbacks.
The persistent hook invokes those callbacks around the original function and
logs the callback counts. This proves the native dispatch spine before Lua is
attached. Confidence: high.

Set `DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=true` with the live
hook scaffold after native dispatch passes. The loader creates a persistent Lua
VM for the live hook, executes
`DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT` or the default
`RegisterHook` script, stores Lua pre/post refs, and invokes those callbacks
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
Lua lifecycle readiness is split into `luaCustomEventHooks`,
`luaLoadMapHooks`, `luaBeginPlayHooks`, and `luaInitGameStateHooks` in addition
to the aggregate `luaLifecycleHooks`; all four split gates must pass before
`luaDispatch=true` represents UE4SS-style lifecycle coverage. Full Lua API
completion is stricter: `ue4ssLuaApiComplete=true` also requires
`luaLoadAssetPackage=true`; `luaLoadAssetBackendState=true` is preflight
telemetry, not completion. The UE4SS lifecycle callback spellings are also
available as aliases: `RegisterLoadMapPreCallback`,
`RegisterLoadMapPostCallback`, `RegisterBeginPlayPreCallback`,
`RegisterBeginPlayPostCallback`, `RegisterInitGameStatePreCallback`, and
`RegisterInitGameStatePostCallback`, with matching unregister names.
`RegisterLocalPlayerExecPreHook` and `RegisterLocalPlayerExecPostHook` are the
short aliases for the `ULocalPlayerExec` hook names. Confidence: high.
`GetFunctionParamDescriptors`/
`GetFunctionParams` first return live registry descriptors when `ctx.Function`
matches a scanned `UFunction`, and fall back to the self-test `Value`,
`OriginalResult`, and `Touched` fields for loader-owned callbacks.
The readiness report tracks this as `ueProcessEventLiveFunctionPath=true`,
which requires live `ctx.Function`/`functionPath` evidence to match a decoded
scanned UFunction path from the read-only function descriptor probe.
`FindFunction`, `FindFirstFunction`, and `GetKnownFunctions` expose the same
promoted runtime UFunction handles to Lua mods, keyed by runtime `PathName`.
`GetKnownObjects`, `FindObjects`, `FindAllOf`, and `ForEachUObject` expose the
current object registry with the same keyed-table/handle shape across Linux and
Windows/Proton. `LoadAsset` is the same registry-backed lookup on each target,
not package loading yet.
Readiness now reports `objectDiscoveryCoverage` and `findObjectSemantics` in
addition to `objectDiscovery`; the former isolates missing pointer/layout/
UObject/FName/alias/internal-flag evidence, while the latter also requires
object-array registry entries, native path/name/class/address registry
self-checks (`event=lua-object-registry-check status=passed`), native object
identities, outer-chain full names, and Lua object API calls before
`FindObject`/`StaticFindObject` are treated as live-compatible.
`reflection=true` also requires
`event=lua-function-registry-check status=passed`, which proves native
path/runtimePath/name/address/flags lookup consistency for promoted UFunction
handles before `FindFunction()` is treated as live-compatible.
For current target-image canaries, a runtime function registry check may come
from either `ue-function-param` or `ue-object-array`; the latter is specifically
for the validated-root/deep-GUObjectArray stage where UFunction identities can be
proven before full param/reflection descriptor walking is reliable.
Decoded UObject `FName` values are promoted into `/RuntimeProbe/<DecodedName>`
object aliases when the bounded FName reader is active, with duplicate
object-array aliases skipped for the same object address/name.
`GetParamValue` and `SetParamValue` accept descriptor tables from either source,
but they are guarded to the active callback's params block, mapped page
permissions, descriptor type, and scalar/bool/object/name/string width. This
proves live ProcessEvent-to-Lua callback routing with handle-backed
object/function context, a stable params address table, and bounded
scalar/enum/bool/object-pointer plus in-place `FName`/`FString` params get/set
plumbing plus known-path `RegisterHook` filtering. Exact path matches are
counted as `pathExactMatches`, and terminal function-name fallback matches are
counted as `pathAliasMatches`. The built-in live Lua dispatch self-test uses an
alternate `/Script/...` owner with the same terminal UFunction name to prove
alias routing; this is not full live `FProperty` marshaling.
Unknown live
`UFunction` paths remain permissive until real path/name discovery is proven.
Confidence: high on
hosts with a compatible Lua 5.4 C API library.

Full completion is represented by `ue4ssLuaApiComplete=true`, which requires
`liveTargetImageCanaryContract.ready=true` with all grouped live proof present:
`targetImageAnchors`, `runtimePackageLoading`, `runtimeObjectRegistry`,
`runtimeReflection`, `runtimeProcessEventDispatch`, and
`runtimeCallFunctionDispatch`. Self-test-only logs do not satisfy that contract.
`runtimeProcessEventDispatch` is complete only when the live canary proves the
decoded live function path, runtime registry context, active params, raw/container
param samples, Lua context handles, descriptor-backed param accessors, typed
scalar/name/string/struct/enum/object/bool accessor coverage, container alias/
layout methods, and hook routing/alias routing. Hook installation alone remains
diagnostic. In short: container alias/layout methods are required, not optional.
The `runtimePackageLoading` group treats `luaLoadAssetPackageNativeExecutor` as
ready only when target-image evidence reports `NativeExecutorReady=true`,
`ExecutorPreflightPassed=true`, and `FinalNativeCallEligible=true`; dry-run
executor shape rows remain diagnostic only.

## Integration Plan

1. Use the probe loader in a disposable Linux server container and verify:
   process load, module list, configured scan hits, and no crash.
2. Use scan/xref output to promote same-build UE anchors into
   `DUNE_PROBE_LOADER_UE_ANCHORS`, then validate FName/object/world readers on
   exactly one live map before any live hook work.
3. Add real Unreal object discovery: find `GUObjectArray`, `FNamePool`/`GNames`,
   `GWorld`/`GEngine`, `UClass`/`UFunction` metadata, and `ProcessEvent` without manual
   anchor input.
4. Replace the bounded `Reflection():GetProperty` descriptor shim with live
   `FProperty` chain traversal and value marshaling for primitive values,
   strings, object references, arrays/maps, and function params/returns.
5. Run the guarded ProcessEvent hookability probe on the resolved live target
   and require `ueProcessEventHookRuntimeTarget=true`.
6. Install the persistent ProcessEvent hook scaffold only after a lab canary
   survives restarts and map travel, then require
   `ueProcessEventLiveHookRuntimeTarget=true`.
7. Install the persistent CallFunction hook scaffold only after the guarded
   CallFunction hookability probe passes on the live target, then require
   `ueCallFunctionLiveHookRuntimeTarget=true`.
8. Prove native ProcessEvent pre/original/post callback dispatch through the
   persistent hook before Lua routing.
9. Prove live ProcessEvent-to-Lua `RegisterHook` callback routing through the
   persistent hook with resolved `Object`/`Function` handles and a `Params`
   context table from a non-self-test runtime function before live reflection
   marshaling.
10. Promote non-self-test runtime object, function, decoded alias, and object
   array registry evidence so `luaObjectRegistryRuntime`,
   `luaFunctionRegistryRuntime`, `luaDecodedObjectAliasesRuntime`, and
   `ueObjectArrayRegistryRuntime` are all true.
11. Prove `ForEachFunction` enumerates promoted `UFunction` handles from a
   non-self-test object/class handle so `luaFunctionIterationRuntime=true`.
12. Prove live `RegisterHook` alias routing by registering a UE4SS-style
   `/Script/...` path whose terminal function name matches a decoded
   `/RuntimeProbe/<Outer>.<Function>:Function` path, producing
   `pathAliasMatches > 0` before claiming `luaDispatch=true`.
13. Prove Lua `GetFunctionParamDescriptors`/`GetFunctionParams` plus
   descriptor-handle `GetParamDescriptor` and `GetParamValue`/`SetParamValue`
   access from ProcessEvent callbacks, including scalar, name/string, struct,
   bool, byte-sized enum, and object-pointer params.
14. Prove descriptor-backed `CreateProcessEventParams(function)` buffers
   outside active callbacks on server, native Linux client, and Windows/Proton,
   then reuse that buffer builder for guarded non-self-test native invocation.
   Current builds expose the no-call `descriptor-preflight-ready` state and
   disabled-by-default `{Invoke=true}` gate; when the target-specific opt-in env
   is set, that path now seeds descriptor-backed params and calls the original
   trampoline.
15. Prove, on a live canary, that `ctx.Function` from a real ProcessEvent call
   has a nonempty runtime `PathName`, hits the promoted `ue-function-param`
   registry, and that guarded class-aware `GetParamValue` works on the active
   params pointer before replacing the self-test params block with full
   `FProperty` param marshaling.
16. Convert proven read-only anchors into guarded runtime patches only after the
   injected hook path has cleanup and recovery coverage.
17. Add Lua mod compatibility APIs beyond the current scaffold: replace the
   synthetic `StaticConstructObject`/`NotifyOnNewObject` path with guarded live
   construction and object notification, replace
   registry-only `LoadAsset` with real package/asset resolution, promote live
   class/outer/world/flag fields into object methods, broaden live
   `RegisterHook` argument marshaling, object notifications, game-thread
   scheduling, and UE4SS-compatible mod lifecycle loading.
18. Keep existing file/DB/pak patch paths as the production mechanism until the
   injected Linux runtime path has equivalent recovery hooks and startup tests.
19. Treat full upstream UE4SS compatibility as a separate porting project:
   replace the Windows proxy-DLL loader, port module/symbol handling, replace
   Windows crash/thread APIs, and verify Unreal object discovery on the Linux
   dedicated server binary.

## 2026-06-19 Current Port State

The latest live server evidence proves runtime `FNamePool`,
`GUObjectArray`, FName decoding, UObject array enumeration, decoded object
aliases, and native object identity promotion. It does not yet prove
target-image world, dispatch, package-loading, or reflection anchors, so
`liveTargetImageCanaryContract.ready=false` and live hook/Lua dispatch remains
blocked.

The loader `ue` scan preset has been widened on Linux server, native Linux
client, and Windows/Proton client to include common world/context, console
dispatch, package, and reflected property spellings. The static
`summarize-elf-ue-string-dataflow.py` tool also supports `--all-categories`
and reports nearby writable-target summaries for reviewed read-only candidate
selection. Confidence: high.

Current packaged artifacts:

- Linux server:
  `dist/linux-server-loader/dune-linux-server-loader-16d8f4c-dirty-linux-x86_64.tar.gz`
  sha256 `073e181359a701e43a32dae83a9cf5fff1907b48610bbc45cdc983086afdf79a`
- Native Linux client:
  `dist/linux-client-loader/dune-linux-client-loader-16d8f4c-dirty-linux-x86_64.tar.gz`
  sha256 `4f51f995c19f4f9dd1c1326e0406430ce1bb9ca499fe8bee5b020fbd50c8c6c3`
- Windows/Proton client:
  `dist/windows-client-loader/dune-windows-client-loader-16d8f4c-dirty-windows-x86_64.tar.gz`
  sha256 `6a7d4650e6a8b35c3cc0a09b66fce6bf37f31df5f48b3021a9a3d8dd4f1f2c5e`

## 2026-06-19 Direct-Xref Root-Recovery Pass

The ELF function-neighborhood analyzer now accepts live-canary xref JSON
directly via `--xref-json`, matching the Windows/Proton PE analyzer path. This
lets the Linux server/native-client analysis start from real string-hit xref
instructions instead of only relocation-surface pointer slots.

Against build `1988751`, the focused `GEngine` xref pass found five
neighborhoods and three with writable refs. A wider `LoadAssetRegistryModule`
neighborhood from the `LoadAsset` string xref found two pointer-like writable
refs. The current bounded root-recovery export emits six read-only hypotheses
for the next canary:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GEngine=0x16449320;GEngine=0x165f4350;GEngine=0x165ff1d1;GEngine=0x16562a14;LoadAsset=0x166d54b0;LoadAsset=0x16704982
```

These are candidate image offsets, not promoted runtime anchors or callable
package-loader functions. The next zero-player canary must validate whether any
resolves to a mapped pointer with the expected runtime shape before the
`GEngine` rows can count as target-image world evidence or the `LoadAsset` rows
can count as package-surface evidence. The generated read-only plan is
`/tmp/ue4ss-readonly-gengine-loadasset-canary-plan.md`, with env file
`/tmp/ue4ss-readonly-gengine-loadasset-canary.env`.

The runtime and offline classifiers now treat `LoadAsset`/`LoadClass` as
package-surface names and `FObjectProperty`, `FArrayProperty`, `FBoolProperty`,
and `FStructProperty` as reflection-surface names on Linux server, native Linux
client, and Windows/Proton client. Dispatch, reflection, and live hook/Lua
dispatch proof remain hard blockers. Confidence: high.
