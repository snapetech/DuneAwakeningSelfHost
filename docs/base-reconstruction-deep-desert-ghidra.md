# Base Reconstruction Tool in Deep Desert

Confidence: moderate that the first lab candidate is a config/data gap, not a
new binary branch.

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

Findings:

- BRT/base-backup server strings are present:
  `BaseBackupActionPlace.cpp`, `BaseBackupActionBackup.cpp`,
  `BuildingBlueprintBackupToolPlayerCharacterComponent.cpp`,
  `ServerRequestBaseBackup_Implementation`,
  `base_backup_get_data`, and `base_backup_get_buildable_data`.
- The restore path sits beside normal building validation strings:
  `IsLandclaimInsideServerBoundaries`,
  `EBuildingBlueprintCanBePlacedType::IsInHeightLimit`,
  `m_BuildingsForValidation`, and `m_SoftBuildableMapRegionDataTable`.
- Existing repo config allowed landclaim segments only for `HaggaBasin` and
  `Survival_1`. Deep Desert had no `m_MaxLandclaimSegmentsPerMap` entry.

## Candidate Change

Add both Deep Desert identifiers to `[/Script/DuneSandbox.BuildingSettings]`:

```ini
m_MaxLandclaimSegmentsPerMap=(((Name="HaggaBasin"), 6),((Name="Survival_1"), 6),((Name="DeepDesert"), 6),((Name="DeepDesert_1"), 6))
```

The repo configs now include this candidate for the full config files and the
Deep Desert research-lab configs. Both `DeepDesert` and `DeepDesert_1` are kept
until runtime evidence proves which name the landclaim/BRT path uses.

## Validation

Lab validation only:

1. Start/restart a Deep Desert lab partition with the updated config.
2. Give a disposable test account a `BaseBackupTool`.
3. Attempt a BRT restore in Deep Desert away from borders, POIs, resource fields,
   and obvious blocking volumes.
4. Watch logs for:

```text
BaseBackupActionPlace|BuildingBlueprintBackupTool|CanBePlaced|IsLandclaimInsideServerBoundaries|Landclaim|BuildableMapRegion
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
