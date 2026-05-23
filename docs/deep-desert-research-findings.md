# Deep Desert Research Findings

Confidence: moderate. These findings come from the non-destructive collectors
under `captures/research/20260522T161723Z/` plus the repo config and compose
state.

## Current Findings

- Coriolis has DB-visible seed controls. The `dune` schema exposes
  `debug_get_coriolis_seeds()`, `debug_set_farm_seed(seed)`,
  `debug_set_map_seed(map, seed)`, `debug_set_partition_seed(partition_id, seed)`,
  `coriolis_update_seed(...)`, `coriolis_cleanup_partition(...)`,
  `coriolis_cleanup_map(...)`, and `coriolis_cleanup_farm(...)`.
- Spice field state is map and dimension aware. The observed DB functions include
  `fetch_spicefie_id_types_with_global_info(map_name, dimension_index)`,
  `upsert_spicefield_types(..., map_name, dimension_index)`,
  `reset_global_spice_field_state(map_name, dimension_index)`, and
  `produce_spicefield_manifest(map_name, dimension_index)`.
- Static Shifting Sands state has DB functions:
  `record_static_shifting_sand(...)`, `retrieve_all_static_shifting_sand()`, and
  `delete_all_static_shifting_sand()`.
- Native strings expose Coriolis commands:
  `CoriolisPrintSeed`, `CoriolisPrintStoredSeeds`, `CoriolisSetFarmSeed`,
  `CoriolisSetMapSeed`, and `CoriolisSetPartitionSeed`.
- Native strings also expose dangerous Coriolis commands:
  `CoriolisRestartServer`, `CoriolisWipeDatabase`, and `CoriolisMapReset`.
  Treat these as blocked outside disposable labs.
- Native strings expose `DisableShiftingSandsPhysics` and
  `DisableShiftingSandsStormInteractions`. These are candidates only until a
  command/config surface is proven.
- Server pak scans show Deep Desert layout and bitmap assets, including
  `DA_DeepDesert_1_Bitmap_Collection_Layout*`,
  `BMD_DeepDesert_*_LootAreas`, `BMD_DeepDesert_*_SmallShipwrecks`, and
  `MI_DeepDesert_1_LayoutMap`. These are not exposed as ready static images in
  the mounted server tree. Confidence: high for asset references, moderate for
  extractability with external UE pak/uasset tooling.
- No rows are currently present in `dune.shiftingsands_data`, so there is no
  live static shifting-sand mask to draw today. Confidence: high.
- The public/admin Deep Desert map now uses a DB-derived background from
  marker density, Coriolis seeds, resource field counts, spice state, and
  shifting-sand rows when present. A registered weekly screenshot can override
  the schematic background through `admin/static/deep-desert.webp`.
- RabbitMQ topology proves live admin/game routing surfaces exist for map state,
  settings updates, login grants, online state, notifications, chat, and
  heartbeat flows. Delivery is not the same as handler execution.

## Working Model

- `m_bCoriolisAutoSpawnEnabled` is a SandStorm config key. Confidence: high.
- `m_bCoriolisTriggerShiftingSands` is a SandStorm config key. Confidence: high.
- No proven dimension-specific Coriolis damage key has been found. Confidence:
  moderate.
- No proven dimension-specific `MapFeatures` key has been found. Confidence:
  moderate.
- Different Deep Desert containers can be given different mounted `UserGame.ini`
  files in the handoff lab. Whether the game treats those settings as
  per-instance or reconciles them through shared DB/global runtime state is what
  the standby lab test is meant to prove.

## Standby Lab Test

Use `compose.research-dd-lab.yaml` only with the handoff lab project
`dune_handoff_lab`. It adds two standby Deep Desert containers:

| Service | Partition | Dimension | Intended Behavior |
| --- | ---: | ---: | --- |
| `deep-desert-lab-pve` | 8 | 0 | PvE, Shifting Sands off, low Coriolis damage |
| `deep-desert-lab-pvp` | 31 | 1 | PvP, Shifting Sands on, higher Coriolis damage |

Both lab configs use a five-minute Coriolis cycle candidate:
`m_CycleDurationInDays=0.003472`. Confidence is low that the server accepts
fractional days; the test must verify logs and DB state rather than assuming the
key parses that way.

Expected evidence to capture:

- startup logs proving both partitions register as `DeepDesert_1`;
- copied `Saved/UserSettings/UserGame.ini` for both DD containers;
- `dune.world_partition` rows for partitions 8 and 31;
- repeated `debug_get_coriolis_seeds()` output over at least one five-minute
  interval;
- repeated Shifting Sands and spice state snapshots by map/dimension;
- map logs around any Coriolis warning, seed update, storm, restart, wipe, or
  shifting-sands phrase.

## Standby Run: 2026-05-22

Host: `<standby-host>`.

Capture path: `captures/research/dd-coriolis-lab-20260522T162747Z`.

Outcome:

- Both lab Deep Desert containers started and became DB-ready.
- Partition 8 registered as `DeepDesert_1`, dimension `0`, label
  `Deep Desert PvE`.
- Partition 31 registered as `DeepDesert_1`, dimension `1`, label
  `Deep Desert PvP`.
- The mounted per-service `UserGame.ini` files were copied into each
  container's Saved `UserSettings` directory with different PVE/PVP values.
- The fractional cycle value did not behave as a five-minute cycle. Startup logs
  showed `This Coriolis Cycle start date UTC: 2026.05.22-16.27.00` and
  `Next Coriolis Cycle start date UTC: 2026.05.22-16.28.00`, so the observed
  cycle interval was one minute. Confidence: high.
- Both instances requested a Coriolis spawn at `2026.05.22-16.28.02`.
  Confidence: high.
- `debug_get_coriolis_seeds()` stayed stable across samples from `16:27:47Z`
  through `16:33:49Z`: farm seed `1`, `DeepDesert_1` map seed `-1`, and
  partition seeds `-1` for partitions 8 and 31. Confidence: high.
- `retrieve_all_static_shifting_sand()` returned zero rows across all samples.
  Confidence: high.
- `spicefield_types` materialized `DeepDesert` rows for both dimension `0` and
  dimension `1`, three rows each, by the second sample. Confidence: high.
- No wipe, map reset, or container restart occurred during the observation
  window. Confidence: high.

Interpretation:

- Two `DeepDesert_1` dimensions can run at the same time in the standby lab.
  Confidence: high.
- Spice state is dimension-aware for the two-DD shape. Confidence: high.
- The Coriolis spawn request happened on both DD instances from the same cycle
  timing, even though the mounted configs differed. That suggests Coriolis cycle
  timing is effectively shared for this map/farm shape, or both instances
  independently derived the same schedule from config. Confidence: moderate.
- The run did not prove per-instance Coriolis damage. No player or damage probe
  was inside the storm, and no damage-specific log line appeared. Confidence:
  unknown.
- The run did not prove per-instance Shifting Sands. The PVP instance had
  `m_bCoriolisTriggerShiftingSands=True`, but no static Shifting Sands DB rows
  appeared during the short observation. Confidence: unknown.

## Asymmetric Standby Runs: 2026-05-22

Host: `<standby-host>`.

Captures:

- `captures/research/dd-coriolis-asym-20260522T164032Z`
- `captures/research/dd-coriolis-pvp-shortstage-20260522T164619Z`

Tested configuration:

- PVE DD, partition `8`, dimension `0`:
  `m_bCoriolisAutoSpawnEnabled=False`, `m_bCoriolisTriggerShiftingSands=False`,
  `m_CoriolisLightDamage=0`, `m_CoriolisHeavyDamage=0`,
  `m_ShiftingSands=False`.
- PVP DD, partition `31`, dimension `1`:
  `m_bCoriolisAutoSpawnEnabled=True`, `m_bCoriolisTriggerShiftingSands=True`,
  `m_CoriolisLightDamage=2`, `m_CoriolisHeavyDamage=25`,
  `m_ShiftingSands=True`.

Findings:

- With PVE auto-spawn off and PVP auto-spawn on, only partition `31` logged
  `Requested a Coriolis Spawn`. Partition `8` initialized Coriolis timing but did
  not request a spawn. Confidence: high.
- Adding short PVP-only stage/warning values changed the PVP spawn log from
  `SkipTime 36000` to `SkipTime 16`. This proves at least one warning/stage
  timing surface is being read by the PVP DD container. Confidence: high.
- During both asymmetric runs, `retrieve_all_static_shifting_sand()` remained at
  zero rows. Confidence: high.
- During both asymmetric runs, `debug_get_coriolis_seeds()` stayed unchanged:
  farm seed `1`, `DeepDesert_1` map seed `-1`, and partition seeds `-1` for
  partitions `8` and `31`. Confidence: high.
- No wipe, map reset, or container restart occurred during these runs.
  Confidence: high.

Practical conclusion:

- A PVP DD with Coriolis enabled and a PVE DD with Coriolis disabled is achievable
  through per-container mounted `UserGame.ini` files. Confidence: high for the
  lab topology.
- A PVE DD with zero-damage Coriolis is likely achievable by setting its
  Coriolis damage values to zero, but this exact damage behavior was not proven
  because no player/vehicle damage probe was present. Confidence: moderate.
- PVP-only Shifting Sands is still unproven. The known `m_ShiftingSands=True`
  and `m_bCoriolisTriggerShiftingSands=True` settings did not write
  `shiftingsands_data` rows in these short server-only tests. Confidence: low.
