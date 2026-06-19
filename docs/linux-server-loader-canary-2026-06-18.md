# Linux Server Loader Canary - 2026-06-18

Confidence: high for the scan evidence, high that this does not prove complete
UE4SS runtime dispatch.

Live evidence was collected from `kspls0`, service `deep-desert`, partition `8`.
The service had `connected_players=0` when checked. No restart was performed by
this agent; the container had already been started with the Linux server probe
loader enabled for partition `8`.

Captured local evidence:

- Loader log:
  `backups/canary-linux-loader/20260618T161209Z/dune-server-probe-loader-deep-desert-brt.log`
- Scan summary:
  `backups/canary-linux-loader/20260618T161209Z/dune-server-probe-loader-deep-desert-brt.log.summary.txt`
- Readiness report:
  `backups/canary-linux-loader/20260618T161209Z/ue4ss-readiness.md`
- Next canary plan:
  `backups/canary-linux-loader/20260618T161209Z/next-canary-plan.md`
- Ready extra env for the next read-only DD1 UE anchor canary:
  `backups/canary-linux-loader/20260618T161209Z/dd1-ue-anchor-canary.extra.env`

Follow-up DD1 UE-anchor canary evidence:

- Bundle/run capture:
  `backups/canary-linux-loader/20260618T163244Z/`
- Loader log:
  `backups/canary-linux-loader/20260618T163244Z/dune-server-probe-loader-deep-desert-ue-anchor.log`
- Scan summary:
  `backups/canary-linux-loader/20260618T163244Z/dune-server-probe-loader-deep-desert-ue-anchor.log.summary.txt`
- Readiness report:
  `backups/canary-linux-loader/20260618T163244Z/ue4ss-readiness.md`
- Static xref summary:
  `backups/canary-linux-loader/20260618T163244Z/ue-scan-xrefs.md`
- Ghidra UE core anchor xref pass:
  `backups/canary-linux-loader/20260618T163244Z/ghidra-ue-core-anchor-xrefs.md`
- Capstone instruction-neighborhood candidate pass:
  `backups/canary-linux-loader/20260618T163244Z/linux-ue-anchor-candidates.md`
- ELF UE symbol surface pass:
  `backups/canary-linux-loader/20260618T163244Z/elf-ue-symbol-surface.md`

Remote source evidence:

- Host: `kspls0`
- Service: `deep-desert`
- Partition: `8`
- Container log path: `/tmp/dune-server-probe-loader-deep-desert-brt.log`
- Container env included
  `LD_PRELOAD=/workspace/build/linux-server-loader/libdune_server_probe_loader.so`
  on the game process.

The scan completed on the live target image:

- `loader-loaded`: pass
- `scan-completed`: pass
- scan finish: `mappings=54 scanned=3 filtered=50 unreadable=1 sizeSkipped=0 hits=325`
- categories: `brt=46`, `building=80`, `cheat=94`, `deep-desert=22`,
  `gm=34`, `platform=30`, `other=19`

Relevant target-image hits from
`/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping`:

- `ServerRequestBaseBackup`: 4 hits, including image offsets `0x5a553f9`,
  `0x61a011b`, `0x61a026a`, `0x61a03c0`
- `m_BaseBackupToolMapRestriction`: image offset `0x5b5e1ec`
- `BaseBackupActionPlace`: 14 hits, first image offset `0x9227c7`
- `PerformCanBePlaced`: 6 hits, first image offset `0x59e9a91`
- `Fail_InvalidMap`: image offset `0x5994df9`
- `brt-action-guard`: image offset `0xe04ed15`
- `m_PerMapSystemSettings`: image offsets `0x5a5c56f`, `0x5c6f970`
- `m_ShiftingSands`: image offset `0x5c4965e`
- `CheatManager`: 16 hits before the hit limit
- `CheatClass`: image offset `0x59f6a1d`
- `ClientRestart`: image offsets `0x5955fc5`, `0x5c3f253`

The follow-up UE-anchor canary also completed on the live DD1 target image:

- `loader-loaded`: pass
- `scan-completed`: pass
- scan finish: `mappings=54 scanned=3 filtered=50 unreadable=1 sizeSkipped=0 hits=413`
- categories: `brt=46`, `building=80`, `cheat=94`, `deep-desert=22`,
  `gm=34`, `other=41`, `platform=30`, `ue=66`

Additional UE-ish target-image string hits included:

- `GName`: 11 hits, first image offset `0x120ab58`
- `GUObjectArray`: 2 hits, image offsets `0x59a0d55`, `0x5b1a72d`
- `UObject`: 16 hits before the hit limit, first image offset `0x5215c0`
- `UClass`: 16 hits before the hit limit, first image offset `0x569e6d`
- `UFunction`: 16 hits before the hit limit, first image offset `0x65a21c`
- `FProperty`: 16 hits before the hit limit, first image offset `0x5224df`
- `LoadObject`: 10 hits, first image offset `0x814c33`
- `LoadPackage`: image offset `0x5ae6260`

Static promotion result:

- `scripts/summarize-linux-loader-xrefs.py` found 77 UE-category targets and
  0 targets with simple static xrefs.
- `scripts/promote-ue-anchor-xref-candidates.py` produced 0 candidates and
  kept required groups `names`, `objects`, `world`, and `dispatch` missing.
- `scripts/research/DumpUeCoreAnchorXrefs.java` ran against a separate Ghidra
  project with the 1988751 server ELF and produced 0 candidate functions across
  `names`, `objects`, `world`, `dispatch`, `package`, and `reflection`.
- The Ghidra project image base was `0x100000`; runtime loader image offsets in
  the canary logs remain the normalized offsets to feed back into loader-side
  signatures.
- `scripts/recover-linux-ue-anchor-candidates.py` used Capstone around the
  exact live-canary UE hit offsets and produced 0 instruction-neighborhood
  candidates. The hit bytes confirm these offsets are mostly RTTI/mangled string
  data in the large `R E` LOAD segment, not nearby code references.
- `scripts/summarize-elf-ue-symbol-surface.py` scanned 164803 ELF symbols. It
  found 335 UE-like symbol matches, mostly RTTI/vtable/name surfaces, but no
  non-false-positive runtime exports for `ProcessEvent`, `GUObjectArray`,
  `GWorld`, `FNamePool`/`GNames`, `StaticFindObject`,
  `CallFunctionByNameWithArguments`, `StaticLoadObject`, `LoadObject`,
  `LoadPackage`, or `ResolveName`.
- `scripts/summarize-elf-ue-relocation-surface.py` joined the live canary UE
  hit offsets, the ELF UE symbol surface, and `R_X86_64_RELATIVE` relocation
  tables. Against build `1988751` it checked 248 UE-like targets, found 89
  targets with relocation refs and 125 total relocation refs, but 0 executable
  xrefs back into those relocation slots. `.init_array` has 3458 entries, 0
  named entries, and 0 UE-named entries in this stripped image. The relocation
  hits are RTTI/delegate metadata and one live `LoadObject` string table
  cluster, not core object registry, reflection, or `ProcessEvent` dispatch
  anchors.
- `scripts/summarize-elf-ue-function-neighborhoods.py` then disassembled the
  executable functions adjacent to those relocation contexts and all executable
  `.init_array` constructor entries. It analyzed 3627 function seeds, including
  the 3458 startup constructor entries, and still found 0 functions with
  required UE anchor group references for `names`, `objects`, `world`, or
  `dispatch`. The functions do reference writable `.bss`/`.data.rel.ro`
  surfaces, but the classified strings/symbols do not identify
  `FNamePool`/`GNames`, `GUObjectArray`, `GWorld`, or `ProcessEvent`-equivalent
  anchors.
- `scripts/summarize-elf-writable-global-refs.py` scanned all executable
  RIP-relative memory references and clustered anonymous writable targets. It
  found 396339 writable targets with at least one code ref and reported 1982
  targets with at least 32 refs. The only exact anchor text in the reported
  context was the diagnostic string
  `GUObjectArray.IsDisregardForGC(Object)` near writable target `0x165ff4a8`;
  that is evidence of a code path mentioning `GUObjectArray`, not evidence that
  `0x165ff4a8` is the global object array. No exact context identified
  `FNamePool`/`GNames`, `GWorld`, `ProcessEvent`,
  `CallFunctionByNameWithArguments`, or package-loading function anchors.

Conclusion from the follow-up pass: the live target image contains useful UE
string and relocation surfaces, but those surfaces are not resolved
object/reflection/dispatch anchors. The next technical step is deeper
instruction/global-pointer recovery for FName/GUObjectArray/GWorld/ProcessEvent
or equivalent signatures, not another string-only live restart. The static
evidence now also rules out direct dynamic symbol export lookup, simple
relocation-table or startup-constructor promotion, and naive high-fanout
writable-global clustering for the required runtime anchors in build `1988751`.

Negative UE4SS-runtime result:

- `liveTargetImageCanary=false`
- `targetObjectDiscovery=false`
- `targetHooks=false`
- `targetPackageLoadingSurface=false`
- `runtimeObjectRegistry=false`
- `runtimeReflection=false`
- `runtimeProcessEventDispatch=false`
- `ueProcessEventLiveRuntimeContext=false`
- `ueProcessEventLiveLuaDispatch=false`

The next canary plan selected `object-discovery` and blocked escalation because
the log has no resolved UE anchor signatures or loader-normalized UE anchor
group provenance. The next real step is not hook installation. It is an anchor
canary that feeds `DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE` or explicit
`DUNE_PROBE_LOADER_UE_ANCHORS`, with:

- `DUNE_PROBE_LOADER_UE_POINTER_PROBE=true`
- `DUNE_PROBE_LOADER_UE_LAYOUT_PROBE=true`
- `DUNE_PROBE_LOADER_UE_UOBJECT_PROBE=true`
- `DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE=true`
- `DUNE_PROBE_LOADER_UE_FNAME_PROBE=true`
- `DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS=true`

Newer server-loader builds also accept image-offset candidate globals through
`DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS`. This is for bounded shape probing of
anonymous writable globals after static recovery, not for promoting anchors. The
format is semicolon-delimited `Name=0xIMAGE_OFFSET`; the loader resolves the
offset against the live target image base at runtime and emits
`event=ue-candidate-global` before the normal `ue-anchor`, `ue-pointer`,
`ue-object-array`, and `ue-fname` probe events. A lab-only absolute-address form
exists as `Name@addr=0xADDRESS`, but do not use it for restarted maps because
ASLR invalidates it.

The auto-discovery flag is a separate live root pass. It scans bounded
readable+writable target-image mappings, promotes only unique FNamePool and
GUObjectArray-shaped roots as `RuntimeFNamePool` and `RuntimeGUObjectArray`,
and feeds those roots into the existing read-only pointer, FName, object-array,
UObject, reflection, and Lua registry probes. Missing or ambiguous roots are
logged and skipped; this does not install hooks or patch memory by itself.
Current server-loader builds also log `targetWritableMappings`,
`oversizedMappings`, `scannedSlots`, `fnameProbes`, and `objectArrayProbes` on
`ue-runtime-discovery-finish`. If no target writable image mapping is scanned,
the loader emits
`event=ue-runtime-discovery name=target-writable-image-mappings status=missing`.

The current anonymous-global pass has only one exact text hint:

```bash
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x165ff4a8
```

That candidate is intentionally weak: it is near a diagnostic
`GUObjectArray.IsDisregardForGC(Object)` string and should be used only to prove
whether the runtime shape probe rejects or accepts it. It is not evidence that
`0x165ff4a8` is the real `GUObjectArray`.

Later DD1 candidate-global canary evidence from `20260618T175732Z` rejected
that weak candidate at runtime:

- `GUObjectArray=0x165ff4a8` was added from the image offset and mapped in the
  target server process.
- `ue-pointer` reported `status=null`.
- direct `ue-object-array` reported `status=empty`.
- reflection probing started but produced no mapped reflection candidates.
- readiness still reported `targetObjectDiscovery=false`,
  `runtimeReflection=false`, and `runtimeProcessEventDispatch=false`.

That run did prove the candidate-global forwarding path and anchor group
provenance, but it did not prove a usable object registry.

The next ranked candidate sidecar is:

```bash
backups/canary-linux-loader/20260618T175732Z/dd1-ranked-candidate-globals.extra.env
```

It was generated from
`backups/canary-linux-loader/20260618T163244Z/elf-writable-global-refs.json`
with the `20260618T175732Z` log as a reject list:

```bash
python3 scripts/export-ue-candidate-globals.py \
  backups/canary-linux-loader/20260618T163244Z/elf-writable-global-refs.json \
  --reject-log backups/canary-linux-loader/20260618T175732Z/dune-server-probe-loader-dd1-candidate-global.log \
  --groups names --groups objects --groups world \
  --max-per-anchor 4 --max-total 12 --format markdown \
  > backups/canary-linux-loader/20260618T175732Z/next-candidate-globals.md
```

Candidate coverage:

- `FNamePool`: 1 candidate
- `GUObjectArray`: 4 candidates
- `GWorld`: 4 candidates
- dispatch/package/reflection writable-global candidates: 0 from this dataset

The resulting environment line is:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x165d1fe8;GUObjectArray=0x14a3bdc0;GUObjectArray=0x14a3d940;GUObjectArray=0x165d1ca0;GWorld=0x16561994;FNamePool=0x1686df70;GWorld=0x165f3e38;GWorld=0x165ff1f0;GWorld=0x16704cc0
```

This is still a bounded probe set, not promotion. A candidate becomes useful
only if the live runtime probes produce mapped pointer/layout/name/object-array
evidence. If this canary does not produce mapped names/object/world evidence,
the next recovery path remains deeper code/dataflow analysis, not hook
installation.

Ranked candidate canary `20260618T181326Z` result:

- Host verification: `kspls0`
- Service: `deep-desert`
- Partition: `8`
- Connected players before restart: `0`
- Preload container:
  `61a7587243ef2aff363dfc9d0d94aed8e33107d68cdba52abff655364b71c003`

Corrected candidate-global loader canaries `20260618T204919Z` and
`20260618T210720Z`:

- Host verification: `kspls0`
- Service: `deep-desert`
- Partition: `8`
- Connected players before each restart: `0`
- Corrected loader package:
  `dist/linux-server-loader/dune-linux-server-loader-canary-ue-candidates-20260618b-linux-x86_64.tar.gz`
- Package checksum:
  `fc2533bf3396937212301f3942a815ebc1d6bb470c9b6032ea1b1cb5b53ccf85`
- Live analysis copies:
  `/tmp/dune-canary-20260618T204919Z/` and
  `/tmp/dune-canary-20260618T210720Z/`

The first corrected package canary proved that the previously staged loader was
stale: the old `.so` accepted string scans but did not contain
`DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS` or `event=ue-candidate-global`.
The rebuilt loader emitted candidate-global, pointer, layout, object-array,
FName, UObject, and reflection probe events.

Runtime result from `20260618T204919Z`:

- `FNamePool=0x1686df70` produced `ue-fname-start status=ready`.
- `GUObjectArray=0x14a3bdc0` and `GUObjectArray=0x14a3d940` resolved to mapped
  executable targets and were classified as weak code-pointer false positives.
- Other names/object/world candidates were null or empty globals.
- No object-array registry entries were promoted.
- No class-mapped UObject, reflection field walk, ProcessEvent hook target, or
  Lua dispatch evidence was produced.

Root-recovery follow-up from `20260618T210720Z` used only restart-safe
image-offset candidate globals. The tested offsets were:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x166eba80;GName=0x166eba80;GUObjectArray=0x166eba80;GObjectArray=0x166eba80;GWorld=0x166eba80;FNamePool=0x166ebac0;GName=0x166ebac0;GUObjectArray=0x166ebac0
```

All eight candidate rows were rejected as null/empty globals:

- `FNamePool=0x166eba80`
- `FNamePool=0x166ebac0`
- `GName=0x166eba80`
- `GName=0x166ebac0`
- `GObjectArray=0x166eba80`
- `GUObjectArray=0x166eba80`
- `GUObjectArray=0x166ebac0`
- `GWorld=0x166eba80`

Readiness after the corrected root-recovery canary remains blocked:

- `targetObjectDiscovery=false`
- `ueFNameDecoder=false`
- `ueObjectArrayRegistry=false`
- `ueObjectArrayRegistryRuntime=false`
- `reflection=false`
- `hookDispatch=false`
- `luaDispatch=false`

Hardening added after these canaries:

- `scripts/plan-ue4ss-canary-env.py` now suppresses stale explicit
  `*_UE_ANCHORS` exported from a previous runtime log when root-recovery
  candidate globals are provided. Those anchors are absolute process addresses
  and are not safe across a map restart.
- `scripts/canary-linux-server-loader.sh` now strips matching outer quotes from
  `DUNE_LINUX_SERVER_CANARY_EXTRA_ENV` values before writing `.env`, so
  shell-quoted plan output cannot corrupt semicolon-delimited candidate-global
  values.

Conclusion: the live loader/probe path is working, but the tested root-recovery
candidates did not promote runtime UE roots. The remaining hard blocker is still
real target-image runtime root discovery. Do not escalate to reflection hooks,
ProcessEvent hooks, or Lua dispatch until names/object/world anchors produce
mapped, decoded, non-self-test object registry evidence.

Strict root-recovery re-triage after `20260618T210720Z`:

- Updated `scripts/summarize-ue-root-recovery-queue.py` so `movzx` byte-guard
  reads no longer count as write-like root evidence.
- Added per-target `pointerLikeRefCount`, `byteGuardRefCount`, and
  `constantStoreRefCount` to the root-recovery queue.
- Updated `scripts/export-ue-root-recovery-candidates.py` so live-rejected
  offsets can suppress nearby offsets and rejected static clusters, and so
  strict exports can require pointer-like refs while rejecting byte-guard and
  immediate constant-store targets.
- Strict evidence copies:
  `/tmp/dune-canary-20260618T210720Z/ue-root-recovery-queue-strict.json`,
  `/tmp/dune-canary-20260618T210720Z/ue-root-recovery-clusters-strict.json`,
  `/tmp/dune-canary-20260618T210720Z/ue-root-recovery-candidates-strict.md`,
  `/tmp/dune-canary-20260618T210720Z/ue-root-recovery-candidates-strict.env`.

The relaxed post-rejection export still proposes the `0x164d6d88` and
`0x164d6dc8` cluster, but those targets are constructor artifacts with
immediate dword stores such as `mov dword ptr [rip + ...], 0xffffffff`.
With strict filters enabled:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
```

Strict candidate count is `0`; missing groups remain `names`, `objects`, and
`world`. Confidence that another live canary from the current root-recovery
queue would waste a map restart: high. Next work should recover new root
candidates from deeper code/dataflow paths, not recycle `.init_array`
guard/constant-store clusters.

Wider writable-global candidate export after strict root-recovery exhaustion:

- `scripts/export-ue-candidate-globals.py` now accepts structured
  `--candidate-outcomes-json` files in addition to raw reject logs.
- Name anchors are not rejected from structured outcome JSON because the
  outcome summary does not carry `ue-fname-start status=ready`; raw logs still
  protect ready FNamePool anchors before object-array probe noise can reject
  them.
- The exporter now supports `--min-refs`, `--max-refs`, and
  `--max-function-buckets` to keep high-fanout shared globals out of bounded
  read-only canaries.
- `scripts/plan-ue4ss-canary-env.py` now accepts
  `--candidate-globals-json` from that exporter and feeds it through the same
  guarded candidate-global contract as root-recovery candidates.

Current writable-ref candidate export artifacts:

- `/tmp/dune-writable-candidate-export-20260618/ue-candidate-globals-writable-v2.json`
- `/tmp/dune-writable-candidate-export-20260618/ue-candidate-globals-writable-v2.md`
- `/tmp/dune-writable-candidate-export-20260618/next-writable-canary.env`
- `/tmp/dune-writable-candidate-export-20260618/next-writable-canary-plan.md`

The read-only candidate env is:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x165ff4a8;GUObjectArray=0x164559e8;GUObjectArray=0x165d1c88;GUObjectArray=0x165d1c00;FNamePool=0x1686df70
```

`FNamePool=0x1686df70` is preserved because the corrected live log showed
`ue-fname-start status=ready` and `ue-fname-finish status=ready`. The four
`GUObjectArray` rows are still hypotheses from writable-ref context only. The
generated plan stays at `object-discovery`, emits only read-only pointer,
layout, UObject, object-array, and FName probes, and still blocks escalation
because world, dispatch, package, and reflection candidate groups are missing.

Writable-ref live canary `20260618T213212Z` result:

- Host verification: `kspls0`
- Service: `deep-desert`
- Partition: `8`
- Connected players before restart: `0`; the canary wrapper rechecked this
  before enabling preload.
- Loader package:
  `dist/linux-server-loader/dune-linux-server-loader-canary-writable-candidates-20260618-linux-x86_64.tar.gz`
- Package checksum:
  `0a06a4b23aecd62e9f7ff9027d75f783a1129dd24271bc193381d421b785ad21`
- Remote evidence:
  `backups/canary-linux-loader/20260618T213212Z/`
- Local analysis copy:
  `/tmp/dune-canary-20260618T213212Z/`
- Corrected local reports:
  `/tmp/dune-canary-20260618T213212Z/ue-candidate-outcomes-pid343.md`
  and `/tmp/dune-canary-20260618T213212Z/ue-candidate-shapes-pid343.md`

The real target process for the map was `pid=343`. Earlier startup helper PIDs
in the same log had unmapped candidate addresses and should not be used as
runtime evidence.

Corrected runtime candidate classification for `pid=343`:

- `FNamePool=0x1686df70`: promising. The pool address mapped and produced
  `ue-fname-start status=ready` plus `ue-fname-finish status=ready` with
  source `FNamePool:direct`.
- `GUObjectArray=0x165ff4a8`: rejected; pointer null and direct object-array
  probe empty.
- `GUObjectArray=0x164559e8`: rejected; pointer null and direct object-array
  probe empty.
- `GUObjectArray=0x165d1c88`: rejected; pointer null and direct object-array
  probe empty.
- `GUObjectArray=0x165d1c00`: rejected; pointer null and direct object-array
  probe empty.

The FNamePool result is not enough to promote a full UE4SS runtime root set.
It proves the direct name-pool probe can reach a live mapped pool in the target
image, but this canary still produced:

- no `GUObjectArray` runtime registry entries
- no decoded target object registry walk
- no target world anchor
- no reflection field/property walk
- no package-loading runtime proof
- no ProcessEvent/hook dispatch proof
- no Lua dispatch proof

After cleanup, live `.env` had `DUNE_ENABLE_LINUX_SERVER_PRELOAD=false` again
and no `DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS` remained enabled. Do not run a
follow-up canary unless the selected live map is checked at zero connected
players immediately before the wrapper executes.

Second-order UE string dataflow pass after `20260618T213212Z`:

- Tool:
  `scripts/summarize-elf-ue-string-dataflow.py`
- Source binary:
  `/tmp/ghidra-work/server-bin-1988751`
- Source scan xrefs:
  `backups/canary-linux-loader/20260618T163244Z/ue-scan-xrefs.json`
- Local evidence:
  `/tmp/dune-canary-20260618T213212Z/elf-ue-string-dataflow.json`
  and `/tmp/dune-canary-20260618T213212Z/elf-ue-string-dataflow.md`

Result:

- UE source string targets checked: `77`
- targets with raw qword or `R_X86_64_RELATIVE` pointer slots: `0`
- targets with code refs to those slots: `0`
- groups represented in the source strings: names, objects, and reflection

This rules out a simple string -> pointer-table slot -> code xref recovery path
for the known UE string hits in build `1988751`. It does not contradict the
live `FNamePool=0x1686df70` readiness result; it means the remaining
`GUObjectArray`, `GWorld`, and dispatch recovery needs deeper instruction
dataflow or engine-layout signatures rather than direct string/table promotion.

Anonymous writable-root shape pass after `20260618T213212Z`:

- Tool:
  `scripts/summarize-elf-writable-root-shapes.py`
- Candidate exporter:
  `scripts/export-ue-writable-root-shape-candidates.py`
- Source binary:
  `/tmp/ghidra-work/server-bin-1988751`
- Merged live rejection sidecar:
  `/tmp/dune-canary-20260618T213212Z/ue-candidate-outcomes-merged-live-rejections.json`
- Raw shape evidence:
  `/tmp/dune-canary-20260618T213212Z/elf-writable-root-shapes.json`
  and `/tmp/dune-canary-20260618T213212Z/elf-writable-root-shapes.md`
- Read/write filtered evidence:
  `/tmp/dune-canary-20260618T213212Z/elf-writable-root-shapes-readwrite.json`
  and `/tmp/dune-canary-20260618T213212Z/elf-writable-root-shapes-readwrite.md`
- Candidate export:
  `/tmp/dune-canary-20260618T213212Z/ue-writable-root-shape-candidates.json`,
  `.md`, and `.env`
- Read-only canary plan:
  `/tmp/dune-canary-20260618T213212Z/next-writable-root-shape-canary-plan.json`
  and `.md`

The raw pass scanned `393936` anonymous writable targets after applying `16`
live-rejected offsets. The high-score raw rows were dominated by high-fanout
address-only tables, so the follow-up report required balanced qword read/write
access, at least four reads and writes, at most `1200` function buckets, and an
address-only ratio of at most `0.80`. That produced `60` `.bss` read/write
shape targets. The top three are:

- `0x16501c18`: score `19216`, refs `1420`, function buckets `746`
- `0x1648b370`: score `6655`, refs `486`, function buckets `287`
- `0x1648abd8`: score `4776`, refs `337`, function buckets `337`

The generated candidate sidecar keeps the known-ready `FNamePool=0x1686df70`
and tests the top three read/write-root offsets under object/world hypotheses:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70;GUObjectArray=0x16501c18;GObjectArray=0x16501c18;GWorld=0x16501c18;GUObjectArray=0x1648b370;GObjectArray=0x1648b370;GWorld=0x1648b370;GUObjectArray=0x1648abd8;GObjectArray=0x1648abd8;GWorld=0x1648abd8
```

The generated plan keeps `selectedStage=object-discovery` and `maxStage=read-only`.
It enables only pointer, layout, UObject, object-array, and FName probes. It
does not authorize ProcessEvent hooks, live hooks, reflection escalation, or
Lua dispatch. Run it only through the guarded canary wrapper after checking the
selected partition has zero connected players.

Read/write root canary `20260618T220610Z`:

- Host: `kspls0`; wrapper verified `hostname=kspls0`.
- Service/partition: `deep-desert`, partition `8`.
- Player guard: wrapper reported `connected_players=0` immediately before the
  canary restart.
- Local evidence:
  `/tmp/dune-canary-20260618T220610Z/`
- Remote backup:
  `backups/canary-linux-loader/20260618T220610Z/`
- Log:
  `/tmp/dune-canary-20260618T220610Z/dune-server-probe-loader-dd1-writable-root-shapes.log`
- Candidate outcomes:
  `/tmp/dune-canary-20260618T220610Z/ue-candidate-outcomes-pid343.md`
- Candidate shapes:
  `/tmp/dune-canary-20260618T220610Z/ue-candidate-shapes-pid343.md`
- Gap report:
  `/tmp/dune-canary-20260618T220610Z/ue4ss-port-gaps.md`

The server process for this run was pid `343`. The canary tested the known
ready `FNamePool=0x1686df70` plus the top three balanced read/write `.bss`
roots under `GUObjectArray`, `GObjectArray`, and `GWorld` hypotheses:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70;GUObjectArray=0x16501c18;GObjectArray=0x16501c18;GWorld=0x16501c18;GUObjectArray=0x1648b370;GObjectArray=0x1648b370;GWorld=0x1648b370;GUObjectArray=0x1648abd8;GObjectArray=0x1648abd8;GWorld=0x1648abd8
```

Result:

- candidates: `10`
- verdicts: `{'promising': 1, 'rejected': 9}`
- shape verdicts: `{'promising-fname-pool': 1, 'rejected-null': 9}`
- `FNamePool=0x1686df70`: still ready via `FNamePool:direct`.
- `0x16501c18`, `0x1648b370`, and `0x1648abd8`: rejected under all
  object/world hypotheses; each probed as null/empty with no registered
  object-array entries.

After this run, the first read/write-root batch was merged into the live
rejection sidecar and the next balanced shape pass was generated at:

- `/tmp/dune-canary-20260618T220610Z/elf-writable-root-shapes-readwrite-next.json`
- `/tmp/dune-canary-20260618T220610Z/ue-writable-root-shape-candidates-next.md`
- `/tmp/dune-canary-20260618T220610Z/next-writable-root-shape-canary-plan.md`

The next top read/write roots were:

- `0x16515a70`: score `4358`, refs `318`, function buckets `166`
- `0x16512d18`: score `4068`, refs `294`, function buckets `188`
- `0x16501bd0`: score `3965`, refs `292`, function buckets `119`

Read/write root canary `20260618T221715Z`:

- Host: `kspls0`; wrapper verified `hostname=kspls0`.
- Service/partition: `deep-desert`, partition `8`.
- Player guard: all queried partitions `1..31` showed `connected_players=0`
  before the run; wrapper also reported `connected_players=0` for partition `8`
  immediately before the canary restart.
- Local evidence:
  `/tmp/dune-canary-20260618T221715Z/`
- Remote backup:
  `backups/canary-linux-loader/20260618T221715Z/`
- Log:
  `/tmp/dune-canary-20260618T221715Z/dune-server-probe-loader-dd1-writable-root-shapes-2.log`
- Candidate outcomes:
  `/tmp/dune-canary-20260618T221715Z/ue-candidate-outcomes-pid343.md`
- Candidate shapes:
  `/tmp/dune-canary-20260618T221715Z/ue-candidate-shapes-pid343.md`
- Gap report:
  `/tmp/dune-canary-20260618T221715Z/ue4ss-port-gaps.md`

The second run tested:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70;GUObjectArray=0x16515a70;GObjectArray=0x16515a70;GWorld=0x16515a70;GUObjectArray=0x16512d18;GObjectArray=0x16512d18;GWorld=0x16512d18;GUObjectArray=0x16501bd0;GObjectArray=0x16501bd0;GWorld=0x16501bd0
```

Result:

- candidates: `10`
- verdicts: `{'promising': 1, 'rejected': 9}`
- shape verdicts: `{'promising-fname-pool': 1, 'rejected-null': 9}`
- `FNamePool=0x1686df70`: still ready via `FNamePool:direct`.
- `0x16515a70`, `0x16512d18`, and `0x16501bd0`: rejected under all
  object/world hypotheses; each probed as null/empty with no registered
  object-array entries.

Operational cleanup after both read/write-root canaries restored the live
environment to `DUNE_ENABLE_LINUX_SERVER_PRELOAD=false`, with no
`DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS` or read-only probe toggles left
enabled in `.env`. The current conclusion is that balanced anonymous
read/write `.bss` shape ranking is now useful for eliminating bad roots, but it
has not promoted `GUObjectArray`, `GObjectArray`, or `GWorld`. Confidence:
high.

The hard blockers after `20260618T221715Z` are unchanged:

- no live target-image object registry/root promotion
- no target world root
- no reflection field/property walk
- no package-loading runtime proof
- no ProcessEvent hook target proof
- no live hook dispatch proof
- no Lua dispatch proof

Do not escalate to reflection or hook/Lua dispatch from these read/write-root
results. The next useful work is deeper target-image root recovery: instruction
dataflow from object-array/world callsites, constructor cluster triage, and
engine-layout signatures that can produce a non-null live object registry
candidate before another guarded canary.

Next local-only read/write-root queue after merging `20260618T221715Z`
rejections:

- Merged rejection sidecar:
  `/tmp/dune-canary-20260618T221715Z/ue-candidate-outcomes-merged-live-rejections.json`
- Filtered shape scan:
  `/tmp/dune-canary-20260618T221715Z/elf-writable-root-shapes-readwrite-next.json`
  and `.md`
- Candidate export:
  `/tmp/dune-canary-20260618T221715Z/ue-writable-root-shape-candidates-next.json`
  and `.md`
- Read-only plan:
  `/tmp/dune-canary-20260618T221715Z/next-writable-root-shape-canary-plan.json`
  and `.md`

This pass applied `22` rejected offsets, scanned `393930` writable targets, and
reported `60` further `.bss` targets. The top three exported object/world
hypotheses are:

- `0x16501c38`: score `3850`, refs `448`, function buckets `280`
- `0x164e42a0`: score `3799`, refs `276`, function buckets `169`
- `0x164f0be8`: score `3536`, refs `256`, function buckets `158`

The generated env is:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70;GUObjectArray=0x16501c38;GObjectArray=0x16501c38;GWorld=0x16501c38;GUObjectArray=0x164e42a0;GObjectArray=0x164e42a0;GWorld=0x164e42a0;GUObjectArray=0x164f0be8;GObjectArray=0x164f0be8;GWorld=0x164f0be8
```

Confidence that this third read/write-root queue is lower value than the first
two live-tested queues: moderate. The first exported row is a 4-byte scalar
access pattern near the rejected `0x16501c18` root, and the prior two live
canaries rejected all six higher-ranked pointer roots under object/world
hypotheses. Prefer richer static dataflow before spending another live restart
on this queue.

Qword-filtered read/write-root queue:

After the scalar-heavy `0x16501c38` row surfaced, the writable-root shape
scanner was hardened with qword/scalar filters:

```bash
python3 scripts/summarize-elf-writable-root-shapes.py \
  /tmp/ghidra-work/server-bin-1988751 \
  --candidate-outcomes-json /tmp/dune-canary-20260618T221715Z/ue-candidate-outcomes-merged-live-rejections.json \
  --require-read-write \
  --require-qword \
  --min-qword-refs 16 \
  --max-scalar-ratio 0.10 \
  --min-read-refs 4 \
  --min-write-refs 4 \
  --max-function-buckets 1200 \
  --max-address-ratio 0.80 \
  --min-score 120 \
  --limit 60
```

Artifacts:

- Qword shape scan:
  `/tmp/dune-canary-20260618T221715Z/elf-writable-root-shapes-readwrite-qword-next.json`
  and `.md`
- Qword candidate export:
  `/tmp/dune-canary-20260618T221715Z/ue-writable-root-shape-candidates-qword-next.json`
  and `.md`
- Qword read-only plan:
  `/tmp/dune-canary-20260618T221715Z/next-writable-root-shape-qword-canary-plan.json`
  and `.md`

This qword-filtered pass still applied `22` rejected offsets, scanned `393930`
writable targets, and reported `60` further `.bss` targets. It removed the
4-byte scalar-heavy `0x16501c38` row from the next candidate export. The top
three exported object/world hypotheses are now:

- `0x164e42a0`: score `3799`, refs `276`, function buckets `169`,
  qword refs `276`, scalar ratio `0.0`
- `0x164f0be8`: score `3536`, refs `256`, function buckets `158`,
  qword refs `256`, scalar ratio `0.0`
- `0x164ecc70`: score `3082`, refs `224`, function buckets `112`,
  qword refs `224`, scalar ratio `0.0`

The generated env is:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70;GUObjectArray=0x164e42a0;GObjectArray=0x164e42a0;GWorld=0x164e42a0;GUObjectArray=0x164f0be8;GObjectArray=0x164f0be8;GWorld=0x164f0be8;GUObjectArray=0x164ecc70;GObjectArray=0x164ecc70;GWorld=0x164ecc70
```

If another read/write-root canary is justified, use this qword-filtered queue,
not the older scalar-admitting queue. Even then, confidence is only moderate:
the prior two live canaries already proved this heuristic class has a high
false-positive rate for `GUObjectArray`/`GWorld` root promotion.

Ranked candidate canary `20260618T181326Z` operational details:

- Wrapper exit: clean; cleanup restart completed; map watchdog resumed.
- Local evidence:
  `backups/canary-linux-loader/20260618T181326Z/`
- Candidate outcome report:
  `backups/canary-linux-loader/20260618T181326Z/ue-candidate-outcomes.md`
- Code-pointer static context report:
  `backups/canary-linux-loader/20260618T181326Z/ue-code-pointer-context.md`
- Root recovery queue:
  `backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-queue.md`
- Root recovery clusters:
  `backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-clusters.md`

Runtime readiness changed from the previous canary:

- `Ready pointer probe`: `true`
- `Ready UE anchor group provenance`: `true`
- `ue-names`, `ue-objects`, and `ue-world`: pass
- `target-image names`, `target-image objects`, and `target-image world`: pass
- `Ready layout probe`: still `false`
- `Ready UObject probe`: still `false`
- `Ready UE reflection probe`: still `false`
- `Ready target-image object discovery`: still `false`
- `Ready target-image hooks`: still `false`
- `Ready live target-image canary`: still `false`

The useful negative detail is that two `GUObjectArray` candidates
(`0x14a3bdc0` and `0x14a3d940`) pointed to executable text, produced readable
instruction bytes as "layout", then failed UObject validation with unmapped
class/vtable values and registered zero object-array entries. The remaining
mapped writable candidates were null or empty. `FNamePool=0x1686df70` made the
FName probe enter `ready` state as a direct pool, but sample decodes were
`block-unreadable`, so it is not yet a proven name decoder.

The live candidate outcome classifier reports:

- candidates: 9
- verdicts: `{'rejected': 7, 'weak-false-positive': 2}`
- recommendations:
  `{'reject-code-pointer-and-trace-caller-dataflow': 2, 'reject-null-or-empty-global': 7}`
- promotable candidates: 0
- promising candidates: 0
- weak false positives:
  - `GUObjectArray=0x14a3bdc0`
  - `GUObjectArray=0x14a3d940`

Regenerate that report with:

```bash
python3 scripts/summarize-ue-candidate-outcomes.py \
  backups/canary-linux-loader/20260618T181326Z/dune-server-probe-loader-dd1-ranked-candidate-globals.log \
  --server-pid 343 --format markdown \
  > backups/canary-linux-loader/20260618T181326Z/ue-candidate-outcomes.md
```

The stricter candidate-shape classifier reports the same nine injected
candidates as runtime shapes rather than just outcome classes:

- verdicts: `{'rejected-anchor-unmapped': 7, 'weak-code-pointer': 2}`
- promotable candidates: 0
- promising candidates: 0
- weak code-pointer candidates:
  - `GUObjectArray=0x14a3bdc0`
  - `GUObjectArray=0x14a3d940`

Regenerate that report with:

```bash
python3 scripts/summarize-ue-candidate-shapes.py \
  backups/canary-linux-loader/20260618T181326Z/dune-server-probe-loader-dd1-ranked-candidate-globals.log \
  --format markdown \
  > backups/canary-linux-loader/20260618T181326Z/ue-candidate-shapes.md
```

The static code-pointer context pass used the staged server ELF
`/tmp/ghidra-work/server-bin-1988751` and confirmed the two weak positives are
RTTI/vtable-style tables, not object-array roots:

- `GUObjectArray=0x14a3bdc0` is adjacent to
  `_ZTI20FRigVMExecuteContext` and points to code at `0xabbd820`.
- `GUObjectArray=0x14a3d940` is adjacent to `_ZTI15FRigUnitMutable` and points
  to code at `0xabdaa10`.

Regenerate that report with:

```bash
python3 scripts/summarize-ue-code-pointer-context.py \
  /tmp/ghidra-work/server-bin-1988751 \
  backups/canary-linux-loader/20260618T181326Z/ue-candidate-outcomes.json \
  --format markdown \
  > backups/canary-linux-loader/20260618T181326Z/ue-code-pointer-context.md
```

After feeding both failed live logs back into
`scripts/export-ue-candidate-globals.py`, the writable-global route has only
four further object candidates and no names/world/dispatch/package/reflection
candidates:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x164559e8;GUObjectArray=0x165d1c88;GUObjectArray=0x165d1c00;GUObjectArray=0x165d1e60
```

That makes another writable-global-only canary low value unless the loader adds
more discriminating object-array shape checks. The next higher-value work is
code/dataflow recovery for the actual object array/name pool/world roots and a
separate dispatch/package-loading recovery path. `ProcessEvent` is still not
ready for hook installation.

The first root-recovery queue was generated from
`elf-ue-function-neighborhoods.json` with the live rejected offsets applied:

```bash
python3 scripts/summarize-ue-root-recovery-queue.py \
  backups/canary-linux-loader/20260618T163244Z/elf-ue-function-neighborhoods.json \
  --candidate-outcomes-json backups/canary-linux-loader/20260618T181326Z/ue-candidate-outcomes.json \
  --limit 40 --format markdown \
  > backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-queue.md
```

It analyzed 3627 function-neighborhood seeds, applied 12 rejected live offsets,
and queued 40 constructor/dataflow functions with writable global refs. The top
entries are repeated `.init_array` constructor families writing dense `.bss`
ranges such as `0x166eba80` onward. This is a static review queue, not a
promotable anchor list. The next pass should cluster those constructor families
and identify whether any writable range has UE object/name/world shape before
another live canary.

The first cluster pass groups the queued functions by source family and
writable-target range:

The current bounded root-recovery candidate export from that queue is:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x166eba80;GUObjectArray=0x166ebac0;GUObjectArray=0x164d6d88;GUObjectArray=0x164d6dc8
```

Generate the guarded read-only canary plan from the readiness, root-recovery
candidate, and candidate-shape sidecars with:

```bash
python3 scripts/plan-ue4ss-canary-env.py \
  --platform server \
  --readiness-json backups/canary-linux-loader/20260618T181326Z/ue4ss-readiness.json \
  --root-recovery-candidates-json backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-candidates.json \
  --candidate-shapes-json backups/canary-linux-loader/20260618T181326Z/ue-candidate-shapes.json \
  --max-stage read-only \
  --format markdown \
  > backups/canary-linux-loader/20260618T181326Z/next-root-recovery-canary-plan.md
```

The generated plan keeps `selectedStage=object-discovery`, emits only
candidate-global plus read-only pointer/layout/UObject/object-array/FName
probes, and marks the four globals as root-recovery hypotheses. It does not
authorize ProcessEvent hook installation.

```bash
python3 scripts/cluster-ue-root-recovery-queue.py \
  backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-queue.json \
  --format markdown \
  > backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-clusters.md
```

With the expanded 80-function queue, this produced two `.init_array` families:
one large range `0x164d6d88..0x164d87e8` with 69 functions and 144 writable
targets, and one smaller range `0x166eba20..0x166ebc40` with 11 functions and
18 writable targets. Confidence that these are still static triage clusters,
not proven UE runtime roots: high.

Only after that produces target-image names/object/world/dispatch/package
loading anchor groups should the next canary move to guarded
`ProcessEvent`/reflection runtime proof.

Use the hardened canary wrapper for the next DD1 read-only anchor pass so the
selected service/partition is explicit and the previous `.env` preload state is
restored afterward:

```bash
DUNE_LINUX_SERVER_CANARY_SERVICE=deep-desert \
DUNE_LINUX_SERVER_CANARY_PARTITION=8 \
DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader-dd1-ranked-candidate-globals.log \
DUNE_LINUX_SERVER_CANARY_EXTRA_ENV=backups/canary-linux-loader/20260618T175732Z/dd1-ranked-candidate-globals.extra.env \
scripts/canary-linux-server-loader.sh .env
```

If the live workspace source is older than the local packaged loader, stage the
package `.so` first and make the canary use that exact loader without rebuilding
remote source:

```bash
DUNE_LINUX_SERVER_CANARY_SERVICE=deep-desert \
DUNE_LINUX_SERVER_CANARY_PARTITION=8 \
DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader-dd1-ranked-candidate-globals.log \
DUNE_LINUX_SERVER_CANARY_EXTRA_ENV=backups/canary-linux-loader/20260618T175732Z/dd1-ranked-candidate-globals.extra.env \
DUNE_LINUX_SERVER_CANARY_PRELOAD=/workspace/dist/linux-server-loader/dune-linux-server-loader-16d8f4c-dirty-linux-x86_64/lib/libdune_server_probe_loader.so \
DUNE_LINUX_SERVER_CANARY_SKIP_BUILD=true \
scripts/canary-linux-server-loader.sh .env
```

If static analysis produces a `server-anchor-signatures.txt` sidecar first, add
this line to the extra env file before running the canary:

```bash
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE=/workspace/build/server-anchor-signatures.txt
```

## Runtime Registry Shape Follow-Up

Later zero-player canaries were run against the live `kspls0`
`testing-waterfat` map (`WaterFat_0`, partition `7`) with scan/probe enabled and
then disabled again. Confidence: high that these runs did not disturb maps with
connected players because the target partition was checked at `0` players before
the canary restarts.

Captured evidence:

- `backups/canary-linux-loader/20260618T232039Z/dune-server-probe-loader-runtime-registry-shapes-container-path.log`
- `backups/canary-linux-loader/20260618T233323Z/dune-server-probe-loader-qword-after-rejects.log`
- `backups/canary-linux-loader/20260618T233323Z/ue-context-qword-candidates.md`
- `backups/canary-linux-loader/20260618T233323Z/ue-context-qword-candidates-broad.md`
- `backups/canary-linux-loader/20260618T233323Z/next-context-qword-canary-plan.md`
- `backups/canary-linux-loader/20260618T233323Z/next-context-qword-broad-canary-plan.md`

Runtime result:

- The loader loaded inside the real Linux server image.
- Runtime candidate globals were accepted by image offset and probed.
- No target-image runtime root was promoted.
- No live reflection proof was produced.
- No live hook/Lua dispatch proof was produced.

The strict static join now requires both UE nearby-context evidence and
read/write qword root-shape evidence. It produced no candidates:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
```

The broader diagnostic join produced 10 candidates, but those are not suitable
for another live canary because the root-shape evidence is address-heavy rather
than read/write root access:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x165ff4a8;GUObjectArray=0x16554738;GUObjectArray=0x165d1fe8;GUObjectArray=0x14a3bdc0;GWorld=0x16561994;FNamePool=0x1662abf0;GWorld=0x165f3e38;GWorld=0x165ff1f0;GWorld=0x16704cc0;FNamePool=0x16437634
```

The planner intentionally blocks that broad list with
`unproven-root-recovery-shape-quality` and
`scalar-heavy-root-recovery-candidates`. The current rule is that qword-shaped
candidate globals only count as live-canary-quality evidence when the static
classifier sees qword refs plus both read and write classified accesses. Plain
address-taking, even with many 8-byte references, is not enough.

A wider read/write qword pass was then generated as
`backups/canary-linux-loader/20260618T233323Z/elf-writable-root-shapes-readwrite-wide.json`.
It found 2453 read/write qword-shaped writable targets and only two candidates
that also survived UE-context/reject filtering:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x165516a8;GUObjectArray=0x16702ee8
```

Both are still address-heavy, not convincing object-array roots:

- `0x165516a8`: `addressRatio=0.87156`, kinds
  `{'address': 190, 'compare': 7, 'read': 19, 'write': 2}`
- `0x16702ee8`: `addressRatio=0.987696`, kinds
  `{'address': 2649, 'compare': 2, 'read': 29, 'write': 2}`

The planner now blocks those with
`address-heavy-root-recovery-candidates`, and an address-filtered export with
`--max-address-ratio 0.50` produces no candidates:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
```

The writable-global context report was then widened from the top 220 rows to
all 1982 min-32-reference rows:

- `backups/canary-linux-loader/20260618T233323Z/elf-writable-global-refs-after-rejects-wide.json`
- `backups/canary-linux-loader/20260618T233323Z/ue-context-readwrite-qword-candidates-wide-context-address-filtered.md`
- `backups/canary-linux-loader/20260618T233323Z/ue-context-readwrite-qword-candidates-specific-filtered.md`
- `backups/canary-linux-loader/20260618T233323Z/next-wide-context-address-filtered-canary-plan.md`

That wider pass found three shape-clean, address-ratio-clean hypotheses:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x16535950;GUObjectArray=0x16507950;FNamePool=0x16597550
```

They are still not live-canary-quality roots. All three have
`hintExact=0`, `hintSpecific=0`, and only generic UE type context:

- `GUObjectArray=0x16535950`: generic
  `UChatSubsystem::TryDeleteMessagesOfChannelType(UObject *, ...)`
- `GUObjectArray=0x16507950`: generic
  `Runtime/CoreUObject/Public\UObject/Class.h`
- `FNamePool=0x16597550`: generic
  `UExperienceUtils::SetSkillsModuleLevel(... const FName &, ...)`

The planner now blocks these as `generic-only-root-recovery-context`. Exports
with `--require-specific-context` or `--require-exact-anchor` produce no
candidate globals.

An exact-string dataflow pass over the available UE xref source
(`backups/canary-linux-loader/20260618T163244Z/ue-scan-xrefs.json`) covered 77
targets across `FProperty`, `UClass`, `UFunction`, `UObject`, `GName`, and
`GUObjectArray`. With `--only-with-slots`, it emitted zero pointer-slot/code-ref
targets:

```text
targetCount=0
reportedTargetCount=0
targetsWithCodeRefs=0
```

That is a useful negative result: in this stripped Linux server ELF, the exact
UE string hits we currently have do not lead directly to promotable root slots.
Confidence: high.

After widening the loader and exporter alias maps for `NamePoolData`, `GNames`,
`GObjects`, `FUObjectArray`, `CallFunctionByName`, `UStruct`, and `UEnum`, the
wide writable-global context export was rerun with root-shape, address-ratio,
read/write, and specific-context filters:

- `backups/canary-linux-loader/20260618T233323Z/ue-candidate-globals-alias-aware-specific.json`
- `backups/canary-linux-loader/20260618T233323Z/ue-candidate-globals-alias-aware-specific.md`

It still emitted no candidate globals:

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
```

Rejected rows were: `missing-root-shape=1794`, `max-address-ratio=22`,
`missing-specific-context=3`, and `no-anchor-hints=163`. This keeps the same
no-restart conclusion: alias-aware grouping improves future evidence capture,
but the current static evidence still does not justify another live canary.
Confidence: high.

The older `.init_array` root-recovery queue was also regenerated with the
alias-expanded object-discovery preset:

- `backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-candidates-alias-aware.json`
- `backups/canary-linux-loader/20260618T181326Z/next-root-recovery-alias-aware-canary-plan.json`

That export emits `36` aliases over the same four old offsets, but the plan
still blocks them with `unproven-root-recovery-shape-quality` and
`unmatched-root-recovery-source-groups`. The stricter source-group-matched
rerun emits zero candidates:

- `backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-candidates-alias-aware-source-matched.json`
- `backups/canary-linux-loader/20260618T181326Z/ue-root-recovery-candidates-alias-aware-source-matched.md`

```dotenv
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
```

This confirms the alias expansion does not rescue the old `.init_array`
hypotheses. Confidence: high.

The writable-root shape exporter now supports joining writable-global context
with `--writable-global-refs-json` before applying exact/specific context
filters. A strict offline rerun against the current combined-reject shape report
and the wide writable-global context report still emits no candidates:

```bash
python3 scripts/export-ue-writable-root-shape-candidates.py \
  backups/canary-linux-loader/20260619T050111Z/elf-writable-root-shapes-after-combined-rejects.json \
  --writable-global-refs-json backups/canary-linux-loader/20260618T233323Z/elf-writable-global-refs-after-rejects-wide.json \
  --anchor-preset complete \
  --require-specific-context \
  --require-exact-anchor \
  --max-generic-context-ratio 0.50 \
  --format json
```

Result: `candidateCount=0`, `sourceGlobalContextCount=1982`,
`rejectedReasonCounts={"missing-exact-anchor": 4680}`, and all root/hook/package
groups remain missing. This is another negative promotion result, not a tooling
failure: the current reports still lack exact target-image context for a
promotable root or dispatch/package-loading anchor. Confidence: high.

Follow-up static analysis added exact-anchor context output to the ELF string
dataflow and function-neighborhood summaries, and taught the writable-root shape
exporter to consume their `writableTargets` rows. The combined context set now
loads `2075` context offsets. It found one exact `GUObjectArray` context at
`0x165ff4a8` from an `AsyncLoading2` assertion string:

```text
!Object->HasAnyInternalFlags(EInternalObjectFlags::LoaderImport) || GUObjectArray.IsDisregardForGC(Object)
```

Forced root-shape classification for `0x165ff4a8` is not canary quality:
`section=.bss`, `refCount=415`, `qwordRefCount=406`,
`functionBucketCount=255`, `addressRatio=0.978313`, `readRefCount=0`, and
`writeRefCount=0`. A strict export with exact/specific context plus
`--max-address-ratio 0.05 --require-read-write --require-qword` emits no
candidate and reports `max-address-ratio=430`, `missing-exact-anchor=56`,
`missing-qword=3`, and `missing-read-write=11`. This is a useful exact-context
lead, but it remains an address-heavy false-positive shape, not a promotable
`GUObjectArray` root. Confidence: high.

The ELF function-neighborhood summary now also inherits exact/group context
from the seed xref source when the writable target itself is anonymous. That
surfaced exact `LoadObject` package-loading leads at:

- `0x165a8cb0`: `refCount=6`, `qwordRefCount=6`, `readRefCount=4`,
  `writeRefCount=0`, `addressRatio=0.333333`
- `0x165a8c88`: `refCount=3`, `qwordRefCount=3`, `readRefCount=2`,
  `writeRefCount=0`, `addressRatio=0.333333`
- `0x165a8c78`: `refCount=3`, `qwordRefCount=3`, `readRefCount=2`,
  `writeRefCount=0`, `addressRatio=0.333333`
- `0x165a8c80`: `refCount=3`, `qwordRefCount=3`, `readRefCount=2`,
  `writeRefCount=0`, `addressRatio=0.333333`

A relaxed exact/specific export with qword and address-ratio gates emits these
as package-loading hypotheses. The live-root-quality export with
`--require-read-write --max-address-ratio 0.05` emits no candidates and reports
`max-address-ratio=516`, `missing-exact-anchor=69`, `missing-qword=4`, and
`missing-read-write=11`. Treat these as read-only package-loading leads for
future dispatch/package analysis, not as runtime root-promotion candidates.
Confidence: high.

Current conclusion: do not restart another live map for the broad,
address-heavy, or generic-only candidate lists above. The next real blocker is
still target-image runtime root promotion: recover a higher-quality
`FNamePool`/`GUObjectArray`/`GWorld` root or a dispatch/package-loading anchor
from deeper dataflow/signature analysis, then run a single zero-player read-only
canary. Confidence: high.
