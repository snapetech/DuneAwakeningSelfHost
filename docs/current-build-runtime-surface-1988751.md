# Current Build Runtime Surface - 1988751

Date: 2026-06-16.

Confidence: high for byte offsets and checksums, moderate for static
classification, low-to-moderate for behavior until each candidate is hit by a
runtime trace or player canary.

## Binary Provenance

Pristine image binary:

```text
image: registry.funcom.com/funcom/self-hosting/seabass-server:1988751-0-shipping
path: /home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
build id: 6f8ca9ee5f3420c0b4c1ef7cefb412347bcba04b
sha256: f23e19cb7a6dae5c147cf754c8a52bafd35522ace5e8169e82470da16e55cd20
```

Live-patched binary copied from a running container:

```text
sha256: 9a5fa936ab0fea8ed3f8a7091305ac121349c4ec1e5888a01e6ece1f11f3c7de
```

The live-patched binary differs from the pristine binary only at the five
subfief/building-cap branch bypasses listed below. That is expected when
`DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED=true` and target `all` has been applied
during container startup.

## Report Commands

```bash
scripts/summarize-linux-loader-scan.py /tmp/testing-waterfat-loader-v2.log
strings -a -t x /tmp/dune-server-bin-1988751-pristine \
  | rg 'BaseBackup|PerformCanBePlaced|BuildableMapRegion|BuildingSettings|BuildableStructure|Landclaim|DeepDesert|SpiceField|ShiftingSands|PerMapSystem|MaxGlobally|CheatManager|ServerCommand|ServiceBroadcast|AdminLogin|Subfief|Totem'
python3 scripts/research/extract-cheat-manager-methods.py \
  /tmp/dune-server-bin-1988751-pristine --format names
python3 scripts/gm-command-catalog.py --format names --include-binary-methods
make summarize-linux-loader-xrefs \
  SERVER_BINARY=/tmp/dune-server-bin-1988751-pristine \
  LOADER_SCAN_LOG=/tmp/testing-waterfat-loader-v2.log \
  CATEGORY=brt
make summarize-linux-loader-anchors \
  SERVER_BINARY=/tmp/dune-server-bin-1988751-pristine \
  LOADER_SCAN_LOG=/tmp/testing-waterfat-loader-v2.log \
  CATEGORY=brt
scripts/research/run-ghidra-headless.sh \
  --script DumpBrtTraceAnchors.java \
  --binary /tmp/dune-server-bin-1988751-pristine \
  --work-dir /tmp/ghidra-work-1988751-pristine \
  --project-location /tmp/ghidra-work-1988751-pristine/project \
  --project-name DuneServer1988751Pristine \
  --program-name dune-server-bin-1988751-pristine \
  --analysis off
python3 scripts/summarize-linux-loader-xrefs.py \
  /tmp/dune-server-bin-1988751-pristine \
  --target ServerRequestBaseBackupName=0x5a553f9 \
  --target ServerRequestBaseBackupImplTypeA=0x61a006d \
  --target ServerRequestBaseBackupImplTypeB=0x61a01c2 \
  --target ServerRequestBaseBackupImplTypeC=0x61a0311 \
  --target BaseBackupToolMapRestriction=0x5b5e1ec \
  --target PerformCanBePlaced=0x59e9a91 \
  --format json
```

Use the pristine binary for static discovery. Use live container binaries only
to confirm which startup patches are currently applied.

## Broad String Inventory

The broad target inventory found `3835` strings matching current operational
targets in the pristine `1988751` binary:

| Bucket | Matching strings | Usefulness |
| --- | ---: | --- |
| CheatManager-adjacent | `437` | command/method inventory and route proof work |
| ServerCommand/ServiceBroadcast | `39` | native GM payload envelope work |
| BRT/BaseBackup/CanBePlaced | `237` | BRT in DD route and binary gates |
| Building/totem/landclaim/subfief | `2917` | base-piece caps and totem/landclaim limits |
| Deep Desert/shifting/Coriolis | `30` | reflected config/data-table anchors |
| Spice fields/global caps | `278` | Deep Desert state and spice-field runtime knobs |

Static inventory conclusions:

- The server binary contains native BRT backup, placement, and spawn code. This
  includes `UBaseBackupActionBackup`, `UBaseBackupActionForget`,
  `UBaseBackupActionPlace`, `UBaseBackupActionRecycle`, `UBaseBackupSpawner`,
  `UGameItemBaseBackupToolActions`, `UBuildingReplicationComponent` delegate
  strings for `ServerRequestBaseBackup_Implementation`, and the
  `FBaseBackupDatabaseInterface` SQL command strings for save, load, delete,
  recycle, available-backups, buildable-data, actors-to-spawn, and
  finish-placing.
- The server binary contains a large native building/totem/landclaim ECS
  surface, including `FTotemBuildablesComponent`,
  `FTotemLandclaimComponent`, `FStakingUnitAssignTotemProcessor`,
  `FStakingUnitExtendProcessor`, `FTotemLoadedByPersistenceProcessor`,
  `FTotemFinalizePersistenceLoadingProcessor`, and landclaim proximity update
  processors. These are mostly reflected C++ type names, not direct patch sites.
- The server binary contains native Deep Desert, Shifting Sands, spice-field,
  and Coriolis seed surfaces. The direct actionable pieces remain the
  config/data-table anchors and any proven GM route into the methods; simple
  string presence alone is not enough to mutate live state.
- The server binary contains native GM and CheatManager-adjacent classes. That
  still does not make upstream UE4SS Lua mods available in Linux containers.
  UE4SS Lua support would require a real Linux Unreal object/function hook
  runtime in the dedicated server process.

## BRT In Deep Desert

High-signal class and function anchors:

- `UBaseBackupActionBackup`: `0x922738`, `0x922cad`, `0x923122`.
- `UBaseBackupActionForget`: `0x92277c`, `0x922cf1`, `0x923166`.
- `UBaseBackupActionPlace`: `0x9227c0`, `0x922d35`, `0x9231aa`,
  `0x59ce761`.
- `UBaseBackupActionRecycle`: `0x922802`, `0x922d77`, `0x9231ec`.
- `UBaseBackupSpawner`: `0x922890`, `0x922dbd`, `0x923232`, plus
  `SpawnBaseBackup` / `LoadAndPlaceBuildingBlueprint` delegate strings around
  `0x6156525` through `0x6157eb8`.
- `UGameItemBaseBackupToolActions` RTTI/vtable/name clusters: `0xae15cb`,
  `0xae4c48`, `0xae5166`, `0x635b8f7`.
- `UBuildingReplicationComponent::ServerRequestBaseBackup_Implementation`
  appears in long coroutine/delegate type names around `0x61a006d` through
  `0x61a0311`.
- `UBuildingBlueprintBackupToolPlayerCharacterComponent` delegate strings for
  `LoadAvailableBaseBackups`, `StartBuilding`,
  `RequestBuildingBlueprintForBuildingMode`, `PlaceBlueprint`,
  `BackupBlueprint`, `ForgetBlueprint`, `RecycleBlueprint`, and
  deployable-restriction responses around `0x61603fe` through `0x6163794`.
- `FBaseBackupDatabaseInterface` command strings include
  `base_backup_save`, `base_backup_get_available_backups`,
  `base_backup_get_buildable_data`, `base_backup_get_actors_to_spawn`,
  `base_backup_finish_placing`, `base_backup_get_data`,
  `base_backup_delete`, and `base_backup_recycle`.
- `m_BaseBackupToolMapRestriction`: `0x5b5e1ec`.
- `BaseBackupActionPlace.cpp`: `0x59ce761`.

`PerformCanBePlaced` anchors with direct simple xrefs:

- `PerformCanBePlaced`: `0x59e9a91`; xrefs include `0xcfbaf72`,
  `0xcfbb249`, `0xcfc55bf`, `0xcfc5abe`.
- `PerformCanBePlaced_CheckCollisions`: `0x5a02e85`; xrefs include
  `0xcfbd12e`, `0xcfbd1dc`, `0xcfbd337`, `0xcfbd7ff`.
- `PerformCanBePlaced_IsBuildingNearBorders`: `0x5a55079`; xrefs include
  `0xcfbbffd`, `0xcfbc416`, `0xcfccae2`, `0xcfccc2c`.
- `PerformCanBePlaced_IsInHeightLimit`: `0x5a89ddd`; xrefs include
  `0xcfbc945`, `0xcfbcc2f`, `0xcfcd71a`, `0xcfcdaf9`.
- `PerformCanBePlaced_IsLoading`: `0x5be3ac9`; xrefs include `0xcfbb348`,
  `0xcfbb3d9`, `0xcfcb60c`, `0xcfcb6a1`.
- `PerformCanBePlaced_HasPermissions`: `0x5c8325a`; xrefs include
  `0xcfbb6ed`, `0xcfbba11`, `0xcfcb981`, `0xcfcc449`.

Current-build pristine BRT patch candidates:

| Surface | Offset | Original | Patch |
| --- | ---: | --- | --- |
| `PerformCanBePlaced` function start | `0xcfc5440` | function prologue | reference only |
| invalid-map result A | `0xcfc5a7e` | `0x88` | `0x01` |
| invalid-map result B | `0xcfc5c88` | `0x88` | `0x01` |
| invalid-map result C | `0xcfc5fe6` | `0x88` | `0x01` |
| invalid-map result D | `0xcfc60d2` | `0x88` | `0x01` |
| action-method failure reason | `0xe04e81e` | `41 b6 32` | `41 b6 03` |
| action state empty context | `0xe04e9e3` | `31 db` | `b3 01` |
| can-use empty context | `0xe04ec15` | `45 31 f6` | `41 b6 01` |
| can-use actor lookup null | `0xe04ed18` | `74 0a` | `90 90` |
| can-use map-area guard | `0xe04ed22` | `75 03` | `eb 03` |
| can-use region fail join | `0xe04ed24` | `45 31 f6` | `41 b6 01` |
| invalid-map reason guard | `0xe04e6e6` | `0f 85 f3 fe ff ff` | `90` x6 |

Current stale BRT patch signatures:

- `can-use-fallback-selected-actor`: signature not found in build `1988751`.
- `patch-brt-dd-tool-enable-binary.py`: top-level failure-reason signature not
  found in build `1988751`.

The branch shape around `0xe04ed15` remains the best compact BRT action-gate
signature:

```text
0xe04ed15: test rax,rax
0xe04ed18: je   0xe04ed24
0xe04ed1a: mov  r14b,0x1
0xe04ed1d: cmp  byte ptr [r15+0x55],0x1
0xe04ed22: jne  0xe04ed27
0xe04ed24: xor  r14d,r14d
```

Static conclusion: the current build still has all known server-side BRT
surfaces. Runtime conclusion remains unresolved: the keystone trace still needs
to prove whether DD BRT attempts reach
`ServerRequestBaseBackup_Implementation` on the server. Confidence: high for
surface existence, moderate for candidate behavior.

Trace guard and canary status, 2026-06-16:

- Current-build BRT trace points are recorded in
  `scripts/research/brt-dd-points-1988751.tsv` and include the validated
  `0xe04e...` BRT action sites plus `PerformCanBePlaced` invalid-map sites.
- `scripts/brt-dd-uprobe-watch.sh`,
  `scripts/brt-dd-focused-persistent-trace.sh`, and
  `scripts/brt-dd-wide-persistent-trace.sh` now validate a points-file
  `build_id` against the running process before arming. Built-in stale offsets
  require explicit `DUNE_BRT_DD_TRACE_ALLOW_STALE_BUILTINS=1`.
- `scripts/trace-brt-place-live.sh` is keystone-only by default and refuses
  dense built-in breakpoints unless the same stale-offset override is set.
  `scripts/trace-brt-save-live.sh` also refuses its stale built-ins by default.
- `DumpBrtTraceAnchors.java` now writes under
  `${BRT_TRACE_ANCHORS_FILE:-${DUNE_GHIDRA_WORK_DIR}/brt-trace-anchors.txt}`.
  Against the dedicated 1988751 pristine project, it found the
  `ServerRequestBaseBackup_Implementation`,
  `ServerRequestBaseBackup`, `m_BaseBackupToolMapRestriction`, and
  `BaseBackupToolMapRestriction` strings but no function xrefs without full
  analysis. The static ELF xref scanner also found zero executable xrefs for
  those RPC/restriction strings.
- `scripts/research/summarize-elf-pointer-context.py` reconstructs
  relocation-applied pointer tables. Using it on the same pristine binary
  resolves `ServerRequestBaseBackup` to native exec thunk `0xd1093f0` and
  implementation target `0xd109ff0` via
  `UBuildingReplicationComponent` vtable slot `0x588`. These are now current
  trace points in `scripts/research/brt-dd-points-1988751.tsv`. Confidence:
  high for the RPC mapping.
- Live zero-player tracefs canary on `kspls0` DD1 armed the minimal current
  points file, showed eight enabled `brt_dd` events including
  `brt_rpc_exec_server_request_basebackup` and
  `brt_rpc_impl_server_request_basebackup`, then stopped cleanly. Final
  health after the canary: trace group not armed, DD1 running, `31/31`
  partitions ready/alive, DD1/DD2 `connected_players=0`,
  `dune-map-watchdog.service` active, and `/tmp/dune-map-watchdog.paused`
  absent. Confidence: high for trace guard behavior and current point arming;
  unknown for actual BRT restore behavior until a tester/client action fires a
  trace point.

## Base Piece, Building, And Subfief Caps

High-signal data/class anchors:

- `UBuildingSettings`: `0x6054020`, `0x8199ab`, `0x819f4b`.
- `FBuildableMapRegionDataRow`: `0x816543`, `0x816e3f`, `0x817ea8`.
- `BuildableMapRegionDataRow`: `0x59afb75`.
- `BuildableStructureCategoryDataRow`: `0x59afbaa`.
- `m_SoftBuildableMapRegionDataTable`: `0x5949054`.
- `m_TargetNumberOfLandclaims`: `0x59afb8f`.
- `m_MaxNumLandclaimSegments`: `0x5b929bb`.
- `m_MaxLandclaimSegmentsPerMap`: `0x59afced`.
- `Fail_DisallowedBuildLimit`: `0x5b92a3f`.

Current-build pristine cap branch bypasses:

| Surface | Branch offset | Fail enum | Original | Patch |
| --- | ---: | ---: | --- | --- |
| subfief/totem placement cap | `0xcde37ba` | `0x6b` | `0f 84 fe 01 00 00` | `90` x6 |
| server-wide building-piece structure cap | `0xcf070b6` | `0x7e` | `0f 84 aa 00 00 00` | `90` x6 |
| server-wide composed building-piece cap | `0xcf06e34` | `0x80` | `0f 84 f7 01 00 00` | `90` x6 |
| map-wide building-piece structure cap | `0xcf08436` | `0x7f` | `0f 84 ca 00 00 00` | `90` x6 |
| map-wide composed building-piece cap | `0xcf086b2` | `0x81` | `0f 84 d0 00 00 00` | `90` x6 |

The live-patched binary has all five branch sites NOPed. The patcher verifies
each target by following the branch to a fail block that writes the expected
enum byte, so these are stronger than raw signature matches. Confidence: high.

The simple xref scanner found no direct executable RIP references for the
building/reflection string bucket. The five branch bypasses above were found by
binary signatures and fail-block verification, not by string xrefs. Confidence:
high for those five branch sites, low for using nearby reflected names as patch
sites without decompilation.

Remaining base-piece unknown:

- The binary branch bypasses cover known server-side fail paths.
- The cooked `DT_BuildableStructureCategoryData` `BuildingPiece` row remains a
  separate likely data source for the observed `5000` value.
- Player validation is still required to know whether the binary bypass, cooked
  table patch, or both are required for actual beyond-cap placement.

Totem/landclaim surfaces that are useful for future cap work:

- `FTotemBuildablesComponent`, `FTotemComponent`,
  `FTotemLandclaimComponent`, `FTotemProximityCheckComponent`, and the
  corresponding component-pool/type metadata clusters.
- `FStakingUnitAssignTotemProcessor` and `FStakingUnitExtendProcessor`; the
  latter references `FTotemBuildablesComponent`, `FTotemLandclaimComponent`,
  `FBuildingModuleComponent`, `FBuildingModuleOwnerComponent`, spatial groups,
  and circuit components in one reflected processor signature.
- `FTotemLoadedByPersistenceProcessor` and
  `FTotemFinalizePersistenceLoadingProcessor`, both likely useful when proving
  whether cap changes survive restart and persistence reload.
- `FUpdatePlayersCloseToLandclaimProcessor`,
  `FUpdatePlayerClientCloseToLandclaimProcessor`, and
  `FOnPlayerEntersLandclaimProcessor`, useful for client-visible landclaim
  state and proximity validation.

## Deep Desert State

High-signal anchors:

- `m_DeepDesertGameplay`: `0x59b08df`, adjacent to `GetDuneMapIdFromPath`.
- `DeepDesertData`: `0x5abab66`, adjacent to landscape/biome fields.
- `m_DeepDesertThresholds`: `0x5b2d2f1`.
- `bHideInDeepDesertInStreamerMode`: `0x5c003ce`.
- `UCartographyMapSubsystem::SetupForDeepDesertMap` appears in delegate type
  names around `0x61a2ef6`.
- `m_PerMapSystemSettings`: `0x5a5c56f`, `m_PerMapSystemSettings_Key`:
  `0x5c6f970`.
- `m_ShiftingSands`: `0x5c4965e`.
- `m_SpiceFieldTypeSettings`: `0x5c39777`,
  `m_SpiceFieldTypeSettings_Key`: `0x5b19814`.
- `UDuneCheatManager::SpiceFieldUpdateGlobalRules` appears near
  `0x5a03f55`.
- `MaxGloballyPrimed`: `0x5a90b98`, `0x5ac113b`, `0x5c8807d`.
- `MaxGloballyActive`: `0x5a03f35`, `0x5c02a3b`, `0x5c8a4f2`.
- `UShiftingSandsFunctions`: `0xbf2168`, `0xbf2771`, `0xbf2c2b`.
- `FDropThreatBlobOnSpiceFieldProcessor`: `0xbd83ab`, `0xbe77cf`,
  `0xbe77fa`, plus reflected processor signatures around `0x6461d58`.
- `ASpiceField`, `ASpiceFieldExplosion`, `FSpiceFieldTypeSettings`,
  `FSpiceFieldTypeInfo`, `FServerSpiceFieldManifest`, and
  `USpiceHarvestingSystem` delegate/type strings around `0xbfcb8b` through
  `0xbff9f4`.
- `FSpiceGlobalDistributionDataInterface` command strings include
  `request_spawn_spice_field`, `record_deactivated_spice_field`,
  `produce_spicefield_manifest`, `fetch_server_spice_field_manifest`,
  `upsert_spicefield_types`, `register_spice_field_server_resources`,
  `reset_global_spice_field_state`, `update_spice_field_spawn_state`, and
  `update_global_spice_field_rules`.

The simple xref scanner found no direct executable RIP references for these
strings. Treat them as reflected-name/config/data-table anchors for Ghidra
metadata passes, not direct patch sites. Confidence: moderate.

## GM And CheatManager

Native server-command anchors:

- `UDuneServerCommandsCheatManager`: vtable/typeinfo/name clusters around
  `0x9b26cc`, `0x9b3996`, `0x9b3cbd`, `0x62189a5`.
- `UDuneServerCommandSubsystem`: clusters around `0x9b26f2`, `0x9b39bc`,
  `0x9b3ce3`, `0x62189c7`.
- `DuneServerCommands::FGenericBroadcastPayload`: `0x9b2714`.
- `DuneServerCommands::FServerBroadcastPayload`: `0x9b27fd`.
- `DuneServerCommands::FLocalizedServerBroadcastPayload`: `0x9b2749`.
- `DuneServerCommands::FServerShutdownBroadcastPayload`: `0x9b2831`.
- `ServiceBroadcastServerCommand.cpp`: `0x5a2002f`.
- `ServiceBroadcast`: `0x5c4e5af`, simple xref from `0xd96c103`.

CheatManager-adjacent anchors:

- The broad scan found `30` native CheatManager-adjacent classes, including
  `UBuildingSystemCheatManager`, `UCharacterTransferCheatManager`,
  `UClaimSystemCheatManager`, `UDWCheatManager`, `UDuneCheatManager`,
  `UDuneS2sCheatManager`, `UDuneServerCommandsCheatManager`,
  `UDuneShippingCheatManager`, `UFlsCheatManager`, `UFogOfWarCheatManager`,
  `UJourneyCheatManager`, `UOvermapCheatManager`, `URespawnCheatManager`,
  and `US2sCheatManager`.
- `UFlsCheatManager`: `0x59e1da`, `0x59e657`, `0x59e6b6`.
- `UFlsCharacterTransfersCheatManager`: `0x59e1b1`, `0x59e62e`.
- `UFlsPlayerAccountCheatManager`: `0x59e383`, `0x59e66e`.
- `UFlsPlayerRewardsCheatManager`: `0x59e42b`, `0x59e692`.
- `UCheatManagerExtension`: `0x59e6cd`.
- `CheatClass`: `0x59f6a1d`, adjacent to `ServerRestartPlayer` and
  `ServerBlockPlayer`.
- `AdminLoginResponse` / `FDuneUserPrivileges` struct clusters around
  `0x8360c7`, `0x836915`, `0x83698d`.

Static conclusion: the Linux server binary already contains native GM and
CheatManager-adjacent classes. This is not equivalent to upstream UE4SS Lua mod
support. The upstream `CheatManagerEnablerMod` path still depends on UE4SS
finding Unreal objects and registering a hook on an Engine function, while this
repo only has a native Linux preload probe today. Confidence: high.

The simple xref scanner found one direct GM xref: `ServiceBroadcast` at
`0x5c4e5af` referenced from `0xd96c103`. It found no direct simple xrefs for
the CheatManager/AdminLogin bucket. Use Ghidra/decompilation for payload
routing; do not infer executable call flow from those reflected class names
alone.

Current GM/CheatManager command inventory:

- `scripts/research/extract-cheat-manager-methods.py` recovered `100`
  CheatManager methods from the pristine `1988751` binary.
- `scripts/gm-command-catalog.py --include-binary-methods` lists `128` names:
  `28` cataloged command names plus `100` recovered binary methods.
- Only three recovered binary methods overlap the operational allow-list:
  `UDuneCheatManager::AddItemToInventory`,
  `UDuneCheatManager::PatrolShipTeleportToNearest`, and
  `UDuneCheatManager::TravelToDimension`. Execution remains gated on proving
  the native GM payload route.
- `UDuneCheatManager::SpiceFieldUpdateGlobalRules`,
  `UDuneCheatManager::FlushActorPersistence`, Coriolis seed setters, and FLS
  account/reward methods are binary-only-unverified. Do not execute them from
  static discovery alone.

## Next Work

1. Run a separate Ghidra headless project for the pristine `1988751` binary and
   decompile the exact offsets listed above. Do not reuse the locked MCP project.
2. For BRT/DD, run the keystone trace at a low/no-population window with a
   trusted tester. The decisive event is whether
   `ServerRequestBaseBackup_Implementation` is hit during a DD restore attempt.
3. For building/base piece limits, validate whether the current live NOPed branch
   bypasses are sufficient, or whether the cooked `BuildingPiece` data-table row
   still must be patched.
4. For Deep Desert state, use Ghidra reflection/metadata scripts around
   `m_PerMapSystemSettings`, `m_SpiceFieldTypeSettings`, and
   `SpiceFieldUpdateGlobalRules`; simple string xrefs are not enough.
5. For GM/CheatManager, work from the existing native GM catalog and the
   `UDuneServerCommandSubsystem` / `ServiceBroadcast` surfaces instead of trying
   to install upstream UE4SS Lua mods into Linux containers.
