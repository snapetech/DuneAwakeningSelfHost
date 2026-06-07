# Base Reconstruction Tool in Deep Desert

Confidence: moderate that the first lab candidate is a config/data gap, not a
new binary branch.

> **Active plan:** the sequenced diagnostic/fix plan that supersedes the
> "stack every patch at once" posture lives in
> [brt-deep-desert-plan.md](brt-deep-desert-plan.md). Start there.

## Ghidra Evidence

Headless Ghidra was run against the existing `/tmp/ghidra-work/project`
analysis for captured build `1973075`:

```bash
DUNE_BRT_DD_ONLY_EXTRA=true \
DUNE_BRT_DD_EXTRA_NEEDLES='BaseBackupActionPlace.cpp,BaseBackupActionBackup.cpp,BuildingBlueprintBackupToolPlayerCharacterComponent.cpp,ServerRequestBaseBackup_Implementation,IsLandclaimInsideServerBoundaries,EBuildingBlueprintCanBePlacedType,IsInHeightLimit,m_BuildingsForValidation,m_bEnableBuildingRestrictionLimitsCheat,m_SoftBuildableMapRegionDataTable,BaseBackupGetBuildableData,base_backup_get_buildable_data,LoadBaseBackup,base_backup_get_data,ServerRequestBuildingBlueprint_Implementation' \
/opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
  -process server-bin \
  -noanalysis \
  -postScript FindBaseBackupToolDeepDesert.java \
  -scriptPath scripts/research \
  -log /tmp/ghidra-work/base-backup-tool-dd-focused-ghidra.log
```

The focused class/RTTI pass was also run:

```bash
/opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
  -process server-bin \
  -noanalysis \
  -postScript DumpBaseBackupClassSurface.java \
  -scriptPath scripts/research \
  -log /tmp/ghidra-work/base-backup-class-surface-analyzed-ghidra.log
```

Findings:

- BRT/base-backup server strings are present:
  `BaseBackupActionPlace.cpp`, `BaseBackupActionBackup.cpp`,
  `BuildingBlueprintBackupToolPlayerCharacterComponent.cpp`,
  `ServerRequestBaseBackup_Implementation`,
  `base_backup_get_data`, and `base_backup_get_buildable_data`.
- RTTI/vtable evidence confirms native UE classes for the BRT path:
  `UBaseBackupActionPlace`, `UBaseBackupActionBackup`,
  `UBaseBackupActionPlaceResponse`,
  `UBuildingBlueprintBackupToolPlayerCharacterComponent`, and
  `UBuildingReplicationComponent`.
- Useful registration/decompile anchors from
  `/tmp/ghidra-work/base-backup-class-surface-findings.txt`:
  `FUN_0d058500` / `FUN_0d0581b0` register
  `BaseBackupActionPlace`, `FUN_0d053010` / `FUN_0d052c50`
  register `BaseBackupActionBackup`, and `FUN_0d176ff0` /
  `FUN_0d178e50` / `FUN_0d178f00` / `FUN_0d1790d0` register
  `BuildingBlueprintBackupToolPlayerCharacterComponent`.
- Component methods are visible on the backup tool path:
  `FUN_0d17c560` references `StartBuilding`, `FUN_0d17adf0`
  references `UpdateNearbyTotem`, and `FUN_0d17b5e0` references
  `CanBackupBlueprint`, all from
  `BuildingBlueprintBackupToolPlayerCharacterComponent.cpp`.
- The restore path sits beside normal building validation strings:
  `IsLandclaimInsideServerBoundaries`,
  `EBuildingBlueprintCanBePlacedType::IsInHeightLimit`,
  `m_BuildingsForValidation`, and `m_SoftBuildableMapRegionDataTable`.
- `m_MaxLandclaimSegmentsPerMap` is present as a referenced settings/data
  field, and `m_bEnableBuildingRestrictionLimitsCheat` is registered next to
  building cheat fields in `FUN_0d19fad0`.
- `DeepDesert` has direct binary references, but no BRT-specific branch was
  found that hard-codes Deep Desert rejection. `Survival_1` has more direct
  travel/world references and should not be treated as proof that the BRT path
  only accepts that map name.
- Existing repo config allowed landclaim segments only for `HaggaBasin` and
  `Survival_1`. Deep Desert had no `m_MaxLandclaimSegmentsPerMap` entry.
- Follow-up live testing showed the landclaim candidate did apply to DD#1, but
  the client still reported the BRT as not allowed in the region. The shipped
  `m_BaseBackupToolMapRestriction` default only lists `HaggaBasin`,
  `Editor_Default`, and `IGW_Test_Small`, which is a closer match for that
  exact failure text.

## Candidate Change

Add both Deep Desert identifiers to `[/Script/DuneSandbox.BuildingSettings]`:

```ini
m_MaxLandclaimSegmentsPerMap=(((Name="HaggaBasin"), 6),((Name="Survival_1"), 6),((Name="DeepDesert"), 6),((Name="DeepDesert_1"), 6))
m_BaseBackupToolMapRestriction=((Name="HaggaBasin"), (Name="Survival_1"), (Name="DeepDesert"), (Name="DeepDesert_1"), (Name="Editor_Default"), (Name="IGW_Test_Small"))
```

The repo configs now include this candidate for the full config files and the
Deep Desert research-lab configs. Both `DeepDesert` and `DeepDesert_1` are kept
until runtime evidence proves which name the landclaim/BRT path uses.

## Validation

### Next Downtime Live Candidate

Confidence: high that the landclaim-only candidate was deployed to DD#1 on
2026-06-02, and moderate-to-high that the next live candidate should also add
Deep Desert map names to `m_BaseBackupToolMapRestriction`. Restart only the Deep
Desert map service so the server copies the updated config.

The automatic next-downtime path is:

1. Stage the config files on `kspls0`.
2. Mark `backups/operations/brt-dd-deep-desert.pending`.
3. Let the existing `dune-daily-maintenance-schedule.timer` schedule the normal
   06:00 maintenance restart.
4. During post-start health checks, `scripts/brt-dd-next-downtime.sh
   apply-pending` verifies the recreated `deep-desert` container copied the
   updated config and then renames the marker to
   `brt-dd-deep-desert.applied.<timestamp>`.

For a manual downtime fallback, run the mutation only on `kspls0`:

```bash
hostname
make brt-dd-live-preflight ENV_FILE=.env
make brt-dd-live-restart ENV_FILE=.env CONFIRM='RESTART DEEP DESERT BRT'
make brt-dd-live-verify ENV_FILE=.env
```

The guarded restart refuses to run unless `hostname` is `kspls0`. It pauses the
map watchdog, calls `scripts/recover-map.sh .env deep-desert 8`, waits for
partition `8` to become ready/alive/active again, verifies the copied
`Saved/UserSettings/UserGame.ini` has the Deep Desert landclaim entries, and
then resumes the watchdog.

Check automatic staging status:

```bash
make brt-dd-next-downtime-status ENV_FILE=.env
```

While the tester tries the BRT restore, watch high-signal logs:

```bash
make brt-dd-live-logs ENV_FILE=.env
```

Live tester pass:

1. Use a trusted account with a BRT/base backup that can already be restored in
   Hagga Basin.
2. Travel to Deep Desert.
3. Attempt restore away from borders, POIs, resource fields, cliffs, and obvious
   blocking volumes.
4. Capture the exact client error text, timestamp, and location if it still
   rejects placement.

Pass criteria:

- The BRT place action reaches the normal preview/confirm flow in Deep Desert.
- The Deep Desert service stays ready/alive/active after restart.
- Hagga Basin BRT behavior is unchanged.

Rollback:

1. Restore the previous `config/UserGame.deep-desert-coriolis.ini`
   `m_MaxLandclaimSegmentsPerMap` line.
2. Rerun:

```bash
make brt-dd-live-restart ENV_FILE=.env CONFIRM='RESTART DEEP DESERT BRT'
make brt-dd-live-verify ENV_FILE=.env
```

If the live tester gets the same Deep Desert-only rejection, keep the captured
client error/log window and move to the cooked `DT_BuildableMapRegion` /
`m_SoftBuildableMapRegionDataTable` investigation. Do not jump straight to
`m_bBuildingRestrictionLimitsEnabled=False` on live; that is a broad server-side
building restriction toggle.

### Lab Validation

Optional lab validation. Bring up the isolated Deep Desert BRT lab on `kspld0`:

```bash
make brt-dd-lab-config ENV_FILE=.env.handoff-lab
make brt-dd-lab-images ENV_FILE=.env.handoff-lab
make brt-dd-lab-up ENV_FILE=.env.handoff-lab
make brt-dd-lab-status ENV_FILE=.env.handoff-lab
make brt-dd-lab-verify-config ENV_FILE=.env.handoff-lab
```

This starts the control plane plus `deep-desert-lab-pve`, seeds partition `8`
as `DeepDesert_1` dimension `0`, and verifies the copied
`Saved/UserSettings/UserGame.ini` contains:

```text
m_MaxLandclaimSegmentsPerMap=...DeepDesert...DeepDesert_1...
m_BaseBackupToolMapRestriction=...DeepDesert...DeepDesert_1...
m_BaseBackupMaxExtensions=8
m_bBuildingRestrictionLimitsEnabled=True
```

If `brt-dd-lab-images` reports missing images, load/pull the listed lab images
first. The lab will not attempt to start with missing server/RMQ images.

The in-game/manual BRT pass is:

1. Start/restart a Deep Desert lab partition with the updated config.
2. Give a disposable test account a `BaseBackupTool`.
3. Attempt a BRT restore in Deep Desert away from borders, POIs, resource fields,
   and obvious blocking volumes.
4. Watch logs for:

```text
BaseBackupActionPlace|BuildingBlueprintBackupTool|CanBePlaced|IsLandclaimInsideServerBoundaries|Landclaim|BuildableMapRegion
```

Use the focused log helper while the player tests:

```bash
make brt-dd-lab-logs ENV_FILE=.env.handoff-lab
```

Pass criteria:

- The BRT place action reaches the normal preview/confirm flow in Deep Desert.
- New totem/landclaim/buildable rows appear only for the disposable test base.
- Hagga Basin BRT behavior is unchanged.

If this fails with the same Deep Desert-only rejection, the next candidate is
the cooked `DT_BuildableMapRegion` / `m_SoftBuildableMapRegionDataTable`
surface, not a broad binary bypass. The broader
`m_bBuildingRestrictionLimitsEnabled=False` toggle exists, but it disables
server-side building restriction limits globally and should stay a fallback
experiment, not the first production candidate.
