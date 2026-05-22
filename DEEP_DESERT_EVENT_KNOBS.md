# Deep Desert Event Knobs

Stale/archived evidence: generated from build `1963158`; current `.env.example` is `1968181-0-shipping`. Regenerate before using this file as current build truth.

This file tracks knobs found for Deep Desert spice blooms, patrol/crash-site
ship events, dynamic small shipwreck encounters, and buried sandstorm treasure.
Evidence comes from the shipped build `1963158` server image.

## Spice Blooms

Status: nailed down enough to override and test.

Section:

```ini
[/Script/DuneSandbox.SpiceHarvestingSystem]
```

Shipped keys:

```ini
m_PrimeRateInSeconds=30.000000
m_ManagerTickRateInSeconds=5.000000
m_ManagerRequestRefreshRateInSeconds=90.000000
m_GlobalManagerRequestRefreshRateInSeconds=120.000000
m_bPlayerMustWitnessBloom=False
m_bEnableSpiceBloomLongRangeReplication=True
m_bEnableSpiceFieldLongRangeReplication=True
m_NodeValueToSpiceResourceRatio=10.000000
m_bSpawningActive=True
```

Deep Desert field caps from `m_PerMapSystemSettings`:

```ini
("DeepDesert_1", (m_SpiceFieldTypeSettings=(
  ((Name="Small"),  (MaxGloballyPrimed=60,MaxGloballyActive=60)),
  ((Name="Medium"), (MaxGloballyPrimed=12,MaxGloballyActive=12)),
  ((Name="Large"),  (MaxGloballyPrimed=1, MaxGloballyActive=1))
)))
```

Interpretation:

- `MaxGloballyPrimed`: max fields of that type queued/primed globally for the map.
- `MaxGloballyActive`: max fields of that type active globally for the map.
- `m_PrimeRateInSeconds`: how often the system tries to prime fields.
- `m_ManagerTickRateInSeconds`: manager tick cadence.
- `m_ManagerRequestRefreshRateInSeconds` and `m_GlobalManagerRequestRefreshRateInSeconds`: local/global refresh cadence.
- The live DB confirms these caps are materialized into
  `dune.spicefield_types`, and the SQL functions refuse spawn/prime requests
  once `current_globally_active` or `current_globally_primed` reaches the caps.

Live validation from the running `dune_sb_1_4_0_0` database:

```text
DeepDesert Small   max primed/active 60/60  current active 16
DeepDesert Medium  max primed/active 12/12  current active 12
DeepDesert Large   max primed/active 1/1    current active 1
HaggaBasin Small   max primed/active 5/5    current active 4
```

`dune.spicefield_server_availability` also reported Deep Desert inactive pools
of `283` small, `76` medium, and `3` large fields for the live Deep Desert
server, so raising medium/large caps has available field actors to draw from.
`dune.resourcefield_state` showed `60` Deep Desert persisted resource fields at
the same time, which matches the global active cap behavior.

Additional runtime/debug evidence:

- The binary exposes `SpiceFieldUpdateGlobalRules`, which maps directly to the
  DB function `update_global_spice_field_rules(...)`.
- The binary exposes `SpiceFieldSetFieldSpawnRate`, but no matching persistent
  config key has been found yet. Treat direct spawn-rate changes as runtime/debug
  until a config property is proven.
- The log message `Fields of type Small do not have a spawn rate multiplier over
  coriolis cycle set. Will use base spawn rate.` proves per-field-type Coriolis
  spawn-rate multipliers exist somewhere, but those multiplier assets are not in
  the extracted self-host server image.

Likely first override to test for more Deep Desert spice:

```ini
[/Script/DuneSandbox.SpiceHarvestingSystem]
m_PerMapSystemSettings=(("DeepDesert_1", (m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=60,MaxGloballyActive=60)),((Name="Medium"), (MaxGloballyPrimed=24,MaxGloballyActive=24)),((Name="Large"), (MaxGloballyPrimed=3,MaxGloballyActive=3))))),("Survival_1", (m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=5,MaxGloballyActive=5))))))
```

Small fields are already high at `60/60`; medium and large are the obvious
targets.

## Dynamic Small Shipwreck Encounters

Status: partially nailed down. We have real shipped encounter cadence keys and
shipwreck tags. We do not yet have per-encounter spawn weights.

Section:

```ini
[/Script/DuneSandbox.EncountersSubsystem]
```

Relevant shipped keys:

```ini
m_bAreRandomEncountersEnabled=True
m_RandomEncounterInstigationAroundPlayersBoxExtentInMeters=500
m_RandomEncounterInstigationAroundPlayersDelayInSec=15.000000
m_RandomEncounterInstigationOnWholeServerDelayInSec=60.000000
m_RandomEncounterInstigationByAreaDelayInSecOverride=-1.000000
m_bAreEncounterAreaLimitsEnabled=True
m_bAreEncounterNodesEnabled=True
m_bIsRandomEncounterInstigationAroundPlayersEnabled=True
m_bIsRandomEncounterInstigationOnWholeServerEnabled=True
m_bIsRandomEncounterInstigationOnWholeServerForced=False
m_bIsRandomEncounterInstigationByAreaEnabled=True
m_DisabledEncounterNames=((Name="DE_120_SmallShipWreck_DeepDesert_Depricated"))
```

Relevant tags found:

```ini
Encounter.Type.SmallShipwreck
Encounter.Type.SmallShipwreckDeepDesert
```

Interpretation:

- Around-player random encounter checks run every `15` seconds.
- Whole-server random encounter checks run every `60` seconds.
- The shipped config disables one deprecated Deep Desert small shipwreck
  encounter: `DE_120_SmallShipWreck_DeepDesert_Depricated`.
- There is a live `Encounter.Type.SmallShipwreckDeepDesert` tag, so the
  deprecated entry is not proof all Deep Desert shipwreck encounters are off.
- The database only exposes static encounter persistence:
  `dune.encounters_static` plus `save/load_static_encounter_*` functions. The
  running DB currently has no rows in `encounters_static`.
- No DB table/function for dynamic encounter weights, per-type random encounter
  caps, or small shipwreck frequency was found in this build.

Potential test override:

```ini
[/Script/DuneSandbox.EncountersSubsystem]
m_RandomEncounterInstigationAroundPlayersDelayInSec=10.000000
m_RandomEncounterInstigationOnWholeServerDelayInSec=30.000000
```

This should increase random encounter polling broadly, not only shipwrecks. Do
not use it if the goal is only shipwrecks unless broader encounter frequency is
acceptable.

## Patrol Ship / Crash Site

Status: partly nailed down. We found the subsystem and spawn time window; spawn
entries/priority overrides are binary-only candidates so far.

Section:

```ini
[/Script/DuneSandbox.PatrolShipSubSystem]
```

Shipped key:

```ini
m_SpawnTimeSettings=(m_TimeOfDayToSpawn=18.000000,m_TimeOfDayToDespawn=6.000000)
```

Binary-only candidate fields:

```text
m_PatrolShipSpawnerEntries
m_CrashSitePriorityOverrides
m_CrashSitePriorityOverrides_Key
m_bIsPatrolShipEnabled
m_SpawnedPatrolShip
m_CrashSite
m_PatrolShipName
m_ShipwreckName
```

Relevant cheat/admin commands found in the binary:

```text
PatrolShipListSpawned
PatrolShipSetEnabled
PatrolShipTeleportToNearest
PatrolShipToggleSplineOfNearest
PatrolShipSetMovementSpeedMultiplierOnNearest
CrashSiteForceSelectForNextSpawn
CrashSiteForceSetOccupied
CrashSiteSetPriority
CrashSitePrintInfo
CrashSitePrintInfoIfLinked
CrashSiteSimulateSpawnNewPlayer
SetShipwrecksRevealStateInRange
```

Interpretation:

- The only shipped config scalar found so far controls the active time-of-day
  window: spawn at `18.0`, despawn at `6.0`.
- The actual crash-site selection/frequency likely lives in level-placed
  `APatrolShipSpawner` entries or binary-only `m_PatrolShipSpawnerEntries`.
- `m_CrashSitePriorityOverrides` strongly suggests priority weighting can be
  influenced, but we have not confirmed the section or syntax.
- The live DB has a `RadioactiveShipwreck_0` world partition, but no
  crash-site/patrol-ship persistence tables or functions were found.
- Deep Desert startup logs show `CB_WreckedShip_Medium_001` terrain-block marker
  warnings, which confirms shipwreck content is loaded in the Deep Desert map,
  but does not expose frequency.

Potential low-risk test override:

```ini
[/Script/DuneSandbox.PatrolShipSubSystem]
m_SpawnTimeSettings=(m_TimeOfDayToSpawn=0.000000,m_TimeOfDayToDespawn=23.900000)
```

This may keep the patrol/crash-site system available nearly all day. It does
not prove more crash sites spawn if another subsystem limits the active count.

## Buried Sandstorm Treasure

Status: stronger than patrol ship, but not fully live-validated. The default
config exposes the loot table and Deep Desert heatmaps; the binary exposes
probable spawn rate/radius fields clustered with `SandStormConfig`.

Section:

```ini
[/Script/DuneSandbox.SandStormConfig]
```

Shipped key:

```ini
m_TreasureItemsTable=/Game/Dune/Systems/LootTables/Loot_Experience/Buried_Treasure/DT_LootTable_BuriedTreasure_Main.DT_LootTable_BuriedTreasure_Main
```

Deep Desert layout heatmap references:

```text
SandstormTreasureHeatMap=/Game/Dune/Tools/HeatmapTool/Baking/Deep_Desert_BuriedTreasure_01/BP_Deep_Desert_BuriedTreasure_01_HeatMap.BP_Deep_Desert_BuriedTreasure_01_HeatMap
```

Binary-only candidate fields clustered with sandstorm/treasure strings:

```text
m_TreasureSpawnRateMinMax
m_TreasureSpawnLineLengthInMeters
m_TreasureDestroyRadiusInMeters
m_TreasureItemsTable
m_SandStormTreasureHeatMap
m_SandstormTreasureStaticCompactors
m_SandstormTreasureScanners
m_TreasureDataTable
```

Relevant cheat/admin commands found in the binary:

```text
LootSpawnTreasure
LootDestroyAllTreasure
LootPrintTreasureCount
SandstormTreasureTutorial
```

Relevant server gameplay setting enum:

```text
EServerGameplaySettingType::SandStormTreasureEnabled
```

Interpretation:

- Treasure is a sandstorm/Deep Desert heatmap system.
- `m_TreasureSpawnRateMinMax` is the best candidate for frequency.
- `m_TreasureSpawnLineLengthInMeters` likely controls the line/trace used to
  choose a treasure spawn position.
- `m_TreasureDestroyRadiusInMeters` likely controls cleanup/despawn radius.
- These fields are not in shipped `DefaultGame.ini`, but they are near known
  `USandStormManager` / `USandStormConfig` symbols and `m_TreasureItemsTable`.
- The running DB has no treasure tables/functions. The only treasure-related DB
  migration found is `DUNE-153318_nuke_persisted_buried_treasure.sql`, and it is
  empty in this image. Current evidence points to buried treasure being runtime
  state, not durable DB state.
- Logs did not show treasure spawn/count lines under normal startup and idle
  operation. Use `LootPrintTreasureCount` or `LootSpawnTreasure` in-game/admin
  testing to validate before treating `m_TreasureSpawnRateMinMax` as proven.

Candidate override to test carefully:

```ini
[/Script/DuneSandbox.SandStormConfig]
m_TreasureSpawnRateMinMax=(X=30.000000,Y=90.000000)
```

The value shape is inferred from the `MinMax` name and local Unreal vector/range
patterns. Validate in logs/game before adding more treasure-related overrides.

## Current Confidence

| Area | Best knob | Confidence | Notes |
| --- | --- | --- | --- |
| Small spice | `DeepDesert_1` `Small` `MaxGloballyPrimed/Active` | High | Already `60/60`; increasing may not matter much. |
| Medium spice | `DeepDesert_1` `Medium` `MaxGloballyPrimed/Active` | High | Good target; default `12/12`. |
| Large spice | `DeepDesert_1` `Large` `MaxGloballyPrimed/Active` | High | Best target; default `1/1`. |
| General spice cadence | `m_PrimeRateInSeconds` | Medium | Lowering may increase attempts, but caps still matter. |
| Random small shipwreck encounters | `m_RandomEncounterInstigation*DelayInSec` | Medium | Broadly affects random encounters, not only shipwrecks. |
| Patrol ship/crash site window | `m_SpawnTimeSettings` | Medium | Real shipped config; may only change time window. |
| Patrol ship/crash site frequency | `m_PatrolShipSpawnerEntries`, `m_CrashSitePriorityOverrides` | Low / investigate | Binary-only; syntax/section unknown. |
| Buried treasure frequency | `m_TreasureSpawnRateMinMax` | Medium / investigate | Strong binary evidence near sandstorm config, but default absent. |
| Buried treasure enable | `SandStormTreasureEnabled` | Low / investigate | Enum found, not config syntax. |

## Validation Commands

Useful live checks:

```bash
docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select field_type,map_name,dimension_index,max_globally_primed,max_globally_active,current_globally_primed,current_globally_active,is_spawning_active,global_spawn_weight from dune.spicefield_types order by map_name,dimension_index,field_type;"

docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select st.map_name,st.dimension_index,st.field_type,sa.server_id,sa.inactive_fields_of_type,sa.requested_spawned_of_type from dune.spicefield_server_availability sa join dune.spicefield_types st on st.spicefield_type_id=sa.spicefield_type_id order by st.map_name,st.dimension_index,st.field_type,sa.server_id;"

docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select map,dimension_index,field_kind_id,count(*) as fields,min(value_remaining),max(value_remaining),sum(value_remaining) from dune.resourcefield_state group by 1,2,3 order by 1,2,3;"

docker compose logs --no-color --tail=20000 deep-desert | \
  rg -i "LogSpice|treasure|patrol|crash|shipwreck|Encounter|SmallShip"
```
