# Hydration, Shelter, and Base Water Knob Research

Status: several relevant shipped config keys and binary-only candidates exist. The operational goal is **zero dehydration while inside a valid base/shelter, normal dehydration everywhere else**. That means the useful path is probably shelter-protection tuning, not setting the global dehydration rate to zero.

## Confirmed Shipped Config

### Hydration Subsystem

Confirmed in `DuneSandbox/Config/DefaultGame.ini`:

```ini
[/Script/DuneSandbox.HydrationSubsystem]
m_HydrationSystemSettings=/Game/Dune/Systems/Hydration/DA_HydrationSystemSettings.DA_HydrationSystemSettings
m_bHydrationEnabled=True
```

Interpretation:

- `m_bHydrationEnabled` is the only obvious scalar in the shipped section.
- `m_HydrationSystemSettings` points at a cooked data asset. The useful rates are probably inside that asset, not printed as plain `.ini`.
- Disabling hydration entirely may be possible through `m_bHydrationEnabled=False`, but that is a blunt global switch and needs live testing.

### Shelter Detection

Confirmed in `DefaultGame.ini`:

```ini
[/Script/DuneSandbox.ShelterSettings]
m_ShelterTraceLength=10000.000000
m_ShelterTimerSquareDistanceTolerance=1.000000
m_ShelterTraceGridCellSize=200.0000000
m_ShelterTraceFrameBudget=350
m_ShelterGeneralTraceChannel=ECC_GameTraceChannel13
m_ShelterBuildableTraceChannel=ECC_EngineTraceChannel6
m_ShelterDeployableTraceChannel=ECC_GameTraceChannel13
m_WindShelterGeneralTraceChannel=ECC_GameTraceChannel13
m_WindStaticShelterGeneralTraceChannel=ECC_WorldStatic
m_bUseShelterGeneralTraceOnly=false
m_BuildingShelterThreshold=0.9
m_PlaceableShelterThreshold=0.65
```

Interpretation:

- These are real shelter calculation knobs.
- They likely control whether a character/placeable counts as sheltered, including in bases.
- They are not direct thirst/dehydration-rate values, but hydration/exposure systems may consume shelter state.

### World Layout Dehydration Biomes

Deep Desert world layout config references:

```text
DehydrationBiomeTiersBitMap=/Game/Dune/Tools/HeatmapTool/Data/DeepDesert_HydrationBiomes/BMD_DeepDesert_HydrationBiomes.BMD_DeepDesert_HydrationBiomes
```

Interpretation:

- Dehydration severity is at least partly map/biome driven.
- Deep Desert uses hydration biome heatmaps in layout data.
- This is not a simple scalar knob, but it explains why dehydration rate can vary by location.

### Building / Base Water Circuits

Confirmed shipped config near building settings:

```ini
+m_WaterCircuits=(m_CircuitId=1,m_CircuitName=...)
m_PersistenceDelayWaterGeneration=300.000000
BaseResourcesCacheFlushHighPriorityTimer=0.500000
BaseResourcesCacheFlushLowPriorityTimer=3.000000
```

Interpretation:

- Bases/placeables have water circuits and persistence/cache timers.
- `m_PersistenceDelayWaterGeneration` looks like a persistence delay for generated water, not the generation or evaporation rate itself.
- The cache timers are internal update/cache cadence, not gameplay water-loss knobs.

## Binary-Only Candidates

These names are present in the server executable, but their owning section and override syntax are not proven.

### Player Hydration / Dehydration

| Candidate | Meaning inferred from name | Confidence |
| --- | --- | --- |
| `m_DehydrationPerSecondBase` | Base player dehydration drain per second. | Medium as a real internal field; low as direct `.ini`. |
| `m_DehydrationRateScale` | Multiplier applied to dehydration. | Medium as a real internal field; low as direct `.ini`. |
| `m_MaxHydration` | Max player hydration. | Medium. |
| `HydrationStates` | Data/state list for hydration levels. | Medium. |
| `HydrationPenalty` | Penalty applied when dehydrated. | Medium. |
| `RevivalHydrationPenalty` | Hydration penalty after revival. | Medium. |
| `RevivalFullyDehydratedRecoveryPercentage` | Recovery percent after fully dehydrated state. | Medium. |
| `m_InitialRespawnMinimumHydration` | Minimum hydration on initial respawn. | Medium. |
| `m_RespawnMinimumHydration` | Minimum hydration on respawn. | Medium. |

### Shelter / Exposure Interaction

| Candidate | Meaning inferred from name | Confidence |
| --- | --- | --- |
| `ShelteredProtectionThreshold` | Shelter amount needed for hydration/exposure protection. This is the key name most aligned with "no dehydration while in base, normal outside." | High as the target concept; owner/section still unconfirmed. |
| `InSunExposureThresholdSeated` | Sun exposure threshold while seated/in vehicle. | Medium. |
| `m_SunExposureIgnoreInStorm` | Whether sun exposure is ignored during storms. | Medium. |

### Base / Placeable Water

| Candidate | Meaning inferred from name | Confidence |
| --- | --- | --- |
| `m_WaterBaseEvaporationRate` | Base evaporation rate for stored water. | Medium as internal field; low as direct `.ini`. |
| `m_WaterEvaporationModifier` | Modifier on water evaporation, likely placeable/power/storm related. | Medium. |
| `m_WaterProductionShelterThreshold` | Shelter threshold required for water production. | Medium. |
| `m_WaterGenerationRateInSecs` | Water generation interval. | Medium. |
| `m_WaterGenerationAmountPerUpdate` | Water amount generated each update. | Medium. |
| `m_WaterGenRatePerStormLevel` | Storm-level map for water generation rate. | Medium. |
| `m_WaterGenModifierForStormIntensity` | Storm intensity modifier map. | Medium. |
| `m_WaterStorageCircuitPriority` | Water circuit priority. | Medium. |
| `m_WaterStartingAmount` | Starting water amount for a component/placeable. | Medium. |
| `m_MaxWaterCapacity` | Capacity of water storage. | Medium. |

## Database Evidence

No obvious hydration or water-rate tables/functions were found in the current Postgres schema.

Water/base persistence appears to be through normal building/placeable rows:

```text
dune.buildings
dune.building_instances
dune.building_blueprints
dune.building_blueprint_placeables
dune.placeables
```

Related functions:

```text
load_building
load_placeable
save_building
save_placeable
```

Interpretation:

- Building/placeable state is persisted.
- Rate constants are not exposed as obvious DB rows.
- Base water amount may be serialized in placeable/building state blobs/components, but the global rate knobs are likely asset/config driven.

## Practical Knob Ranking

Safest confirmed tests for the base/shelter side:

1. `[/Script/DuneSandbox.ShelterSettings] m_BuildingShelterThreshold`
   - Lower values should make buildings count as sheltered more easily.
2. `[/Script/DuneSandbox.ShelterSettings] m_PlaceableShelterThreshold`
   - Lower values should make placeable shelter count more easily.
3. `ShelteredProtectionThreshold`
   - Best candidate for "base shelter protects from dehydration." The field exists in the binary, but the owning config section is not confirmed yet.

Avoid for this goal:

```ini
m_DehydrationRateScale=0
m_DehydrationPerSecondBase=0
```

Those are the right names for global dehydration rate, but setting either to zero would probably disable thirst outside the base too.

Interesting but not safe yet:

```ini
m_DehydrationPerSecondBase=...
m_DehydrationRateScale=...
m_WaterBaseEvaporationRate=...
m_WaterEvaporationModifier=...
m_WaterProductionShelterThreshold=...
m_WaterGenerationRateInSecs=...
m_WaterGenerationAmountPerUpdate=...
```

Do not add those until the owning class/section is mapped. They are binary strings, not proven config overrides.

## Recommended Next Experiments

1. Add a Settings/admin panel group for the confirmed shelter keys and the experimental hydration candidates.
2. Test lower shelter thresholds and confirm whether bases reduce thirst/heat exposure more reliably.
3. Try the experimental `ShelteredProtectionThreshold` override under the most likely section and verify whether the server logs accept it or silently ignore it.
4. Capture before/after player hydration values if we map the live player stat storage or RPC/state path.
5. Diff `placeables` rows before/after water storage/generator ticks to locate serialized water amount fields.

Experimental config to try on a disposable map:

```ini
[/Script/DuneSandbox.ShelterSettings]
; Make normal base pieces count as sheltered more aggressively.
m_BuildingShelterThreshold=0.5
m_PlaceableShelterThreshold=0.5

[/Script/DuneSandbox.HydrationSubsystem]
; Experimental: binary-confirmed field name, section not yet proven.
; Goal is full dehydration protection while sheltered, not global dehydration disable.
ShelteredProtectionThreshold=0.5
```

If that does not apply, the next likely conclusion is that `ShelteredProtectionThreshold` lives inside `/Game/Dune/Systems/Hydration/DA_HydrationSystemSettings` and cannot be overridden as a plain subsystem scalar without asset patching or a supported game-tweak path.

## Current Answer

For “dehydration rate” and “thirst in base”:

- Global dehydration rate names found: `m_DehydrationPerSecondBase`, `m_DehydrationRateScale`.
- For this goal, do not zero those globally unless you want no dehydration anywhere.
- Confirmed indirect base/shelter knobs: `m_BuildingShelterThreshold`, `m_PlaceableShelterThreshold`, shelter trace settings.
- Best target for base-only protection: `ShelteredProtectionThreshold`, plus making building shelter detection easier.

For “water loss in base”:

- Strong but unproven binary candidates: `m_WaterBaseEvaporationRate`, `m_WaterEvaporationModifier`.
- Confirmed surrounding base-water/persistence knobs: `m_WaterCircuits`, `m_PersistenceDelayWaterGeneration`, `BaseResourcesCacheFlushHighPriorityTimer`, `BaseResourcesCacheFlushLowPriorityTimer`.
- No plain shipped `.ini` scalar for base water evaporation has been confirmed yet.
