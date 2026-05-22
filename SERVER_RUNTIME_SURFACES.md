# Server Runtime Surfaces

Stale/archived evidence: generated from build `1963158`; current `.env.example` is `1968181-0-shipping`. Regenerate before using this file as current build truth.

This file connects shipped config sections, database persistence, live runtime
state, and admin-tool risk areas. It complements:

- `SERVER_CONFIG_KEYS.md`: curated config-key summary.
- `SERVER_CONFIG_KEY_INDEX.md`: exhaustive shipped `DefaultGame.ini` key index.
- `SERVER_BINARY_CONFIG_CANDIDATES.md`: binary-only candidate property names.
- `DEEP_DESERT_EVENT_KNOBS.md`: focused Deep Desert event findings.

Evidence source for this pass:

- Server image build: `1963158`.
- Shipped config: `DuneSandbox/Config/DefaultGame.ini`.
- Shipped schema/procs: `DuneSandbox/Database/*.sql`.
- Live DB: `dune_sb_1_4_0_0` inside the running `postgres` service.

## What Is Proven vs Candidate

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| Shipped `DefaultGame.ini` key | Funcom shipped the config property and default value. | Strongest config evidence. |
| Shipped setup `UserGame.ini` comments | Funcom intended admins to override this value. | Strong override evidence. |
| Live DB table/function | The server persists or mutates this system through Postgres. | Strong runtime evidence. |
| Binary string with nearby class/source names | Property, command, or type exists in the server binary. | Lead only unless section/syntax is confirmed. |
| `_Key` binary companion string | Usually a map/set helper for a reflected Unreal property. | Useful evidence for the non-`_Key` property, not an override key itself. |
| Public web docs | Helpful for high-level behavior. | Weak for internal self-host knobs so far. |

## Live Farm Snapshot

Observed on this repo's running stack on 2026-05-19. Treat these as local state,
not universal defaults.

| Area | Live count / value | Notes |
| --- | ---: | --- |
| Accounts | 3 | `dune.encrypted_accounts`. |
| Actors | 33 | Includes players, controllers, exchange terminals, placeables, building pieces. |
| Inventories | 70 | `dune.inventories`; owned by actor, exchange, item, or vehicle module. |
| Items | 127 | `dune.items`; template IDs are plain text IDs such as `AzuriteOre`. |
| Actor inventory links | 61 | `dune.actor_inventories`; component hash maps inventory role. |
| Vehicles | 0 | No live vehicle rows in this test farm. |
| Vehicle modules | 0 | No live vehicle-module rows. |
| Buildings | 1 | `dune.buildings`. |
| Totems | 1 | `dune.totems`. |
| Landclaim segments | 0 | No live segment rows yet, despite one totem/building. |
| Guilds | 0 | No guild rows. |
| Respawn locations | 6 | `dune.player_respawn_locations`. |
| Travel return rows | 3 | `dune.travel_return_info`. |
| Resource fields | 78 | `dune.resourcefield_state`; Deep Desert/Hagga Basin resource field persistence. |
| Spice field types | 4 | Small/medium/large Deep Desert plus small Hagga Basin. |
| Static encounters | 0 | `dune.encounters_static` exists, but no rows yet. |
| Shifting sands | 0 | `dune.shiftingsands_data` exists, but no rows yet. |
| World partitions | 30 | Full all-maps stack has one partition per configured map/dimension. |

## Config-to-DB Map

| System | Config section | DB tables/functions | What is persisted | Admin/tuning notes |
| --- | --- | --- | --- | --- |
| Landclaims/building | `[/Script/DuneSandbox.BuildingSettings]` | `buildings`, `building_instances`, `building_blueprints`, `placeables`, `totems`, `landclaim_segments`, `base_backups`; `save_building`, `load_building` | Building actors, totems, landclaim segments, blueprints/backups. | `m_MaxNumLandclaimSegments` is the per-base segment cap. `m_MaxLandclaimSegmentsPerMap` is map-level landclaim evidence, not the per-player 3 subfief/totem cap. Changing client-visible placement limits may require matching client config. |
| Inventory/items | `[/Script/DuneSandbox.InventorySystemSettings]`, item deterioration config | `inventories`, `actor_inventories`, `items`, `removed_items`, `removed_recipes`; `load_items`, `update_inventory`, `move_inventory_item`, `merge_inventory_items`, `delete_inventory_item` | Inventory containers, item rows, stack sizes, template IDs, quality/stats JSON. | Raw item grants should use or mirror the inventory functions where possible. Blind inserts risk bad `position_index`, stack, ownership, or stats shape. |
| Spice/resource fields | `[/Script/DuneSandbox.SpiceHarvestingSystem]` | `spicefield_types`, `spicefield_server_availability`, `resourcefield_state`; `try_prime_spicefield`, `try_spawn_spicefield`, `update_global_spice_field_rules`, `fetch_resourcefield_state` | Global spice-field caps/current counts and individual resource field remaining values. | This is the best-understood Deep Desert economy knob set. Medium/large caps are the highest-value overrides. |
| Encounters | `[/Script/DuneSandbox.EncountersSubsystem]` | `encounters_static`; `save_static_encounter_name`, `load_static_encounter_name`, `save_static_encounter_waiting_for_reset` | Static encounter identity/reset state only. | Dynamic encounter weights/caps are not in DB. Frequency knobs in config affect broad random encounter polling, not only shipwrecks. |
| Sandstorm/Coriolis/treasure | `[/Script/DuneSandbox.SandStormConfig]`, `[/Script/DuneSandbox.CoriolisSubsystem]`, `[/Script/DuneSandbox.CoriolisSettings]` | `world_farm_reset_seed`, `world_map_reset_seed`, `world_partition_reset_seed`, `shiftingsands_data`; `record_static_shifting_sand`, `delete_all_static_shifting_sand` | Reset seeds and static shifting-sands records. | Buried treasure has binary/config/heatmap evidence but no live DB persistence in this build. Coriolis cycle/wipe settings are high risk. |
| Respawn | `[/Script/DuneSandbox.RespawnSettings]` | `player_respawn_locations`, `travel_return_info`, `player_travel_state` | Per-player respawn locations and travel/return state. | `m_RespawnLocationMapLimit` looks like per-group limits. Cross-map respawn/drop behavior is configurable and high impact. |
| Travel/world partition | `[/Script/DuneSandbox.TravelDestinationSubsystem]`, map feature sections | `world_partition`, `world_partition_reset_seed`, `travel_actor_parent`, `travel_return_info`, `player_travel_state`; `delete_actor_states_travel` | Running map partition assignments and travel return data. | Travel destination routing is mostly asset/data-asset driven; DB confirms the active map partition layout. |
| Guilds | `[/Script/DuneSandbox.GuildSettings]` | `guilds`, `guild_members`, `guild_invites`; many `*_guild_*` functions | Guild identity, members, invites, allegiance. | Config has creation/member/invite limits. DB functions enforce relationship updates; admin edits should use functions or follow their constraints. |
| Vehicles | `[/Script/DuneSandbox.DuneVehicleSettings]` | `vehicles`, `vehicle_modules`, `vehicle_module_inventories`, `backup_vehicles`, `recovered_vehicles`; `load_vehicle_modules` | Vehicle actors/modules/inventories/recovery rows. | No live rows in this farm yet, so schema is known but runtime examples are missing. |
| Vendor stock/exchange | inventory/economy sections | `vendor_stock_cycle`, `vendor_stock_state`, `dune_exchange_*`; vendor stock functions | Vendor per-player purchase state and exchange orders. | Useful for economy/admin tooling; not directly related to DD event frequency. |
| Permissions | `[/Script/DuneSandbox.PermissionSettings]` | `permission_actor`, `permission_actor_rank` | Actor permission assignments and ranks. | Relevant before admin tooling changes ownership, bases, vehicles, or containers. |
| Access codes | access-code DB procs | `player_access_codes`; `get_player_access_codes`, `create_server_player_access_codes`, reset/delete functions | Per-account access codes. | Good admin-panel candidate; use functions instead of manual inserts. |
| Progression/tutorial/journey | tutorial/journey/progression sections | `journey_story_node`, `journey_tracked_cards`, `tutorials`, `player_tags`, specialization tables | Quest/journey/tutorial/progression state. | Skill/recipe unlock admin features likely need this area plus item/recipe tables. Avoid blind writes until exact functions are mapped. |

## Item and Inventory Write Model

Important live schema facts:

- `dune.items.template_id` is a plain text item/template ID.
- `dune.items.stack_size` must be positive.
- `dune.items.position_index` must be non-negative.
- `dune.items.stats` is JSONB and defaults vary by item type.
- `dune.items.quality_level` exists separately from stats.
- `dune.inventories` can be owned by exactly one of actor, exchange, item, or
  vehicle module.
- `dune.actor_inventories` maps inventory IDs to a `component_name_hash`; the
  hash identifies the inventory component/role, but the plain names have not
  been mapped yet.

Functions worth using or mirroring:

```text
get_inventory_id(actor_id, component_name_hash)
get_sub_inventory_id(owner_item_id)
get_vehicle_module_inventory_id(vehicle_module_id, vehicle_module_inventory_type)
load_items(inventory_id)
update_inventory(...)
update_item_locations(...)
delete_inventory_item(item_id, count)
move_inventory_item(item_id, dst_inventory_id, dst_index, count)
merge_inventory_items(item_id, dst_inventory_id, dst_index, count)
merge_or_move_inventory_item(item_id, dst_inventory_id, dst_index, count)
```

Admin grant implication:

- Currency/resource stack grants are comparatively safe once the target inventory
  and free/mergeable `position_index` are known.
- Gear grants need item-specific `stats` JSON and durability/condition data.
- Container/sub-inventory grants need `inventories.item_id` ownership handling.
- Vehicle/module grants need separate vehicle/module tables plus inventories.

## High-Value Config Areas Still Worth Expanding

| Area | Current state | Next validation target |
| --- | --- | --- |
| Subfief/totem count | Repo-owned experimental knob `DUNE_SUBFIEF_LIMIT` or direct `DUNE_SUBFIEF_LIMIT_BONUS`; binary evidence shows `SubfiefCount`, `SubfiefLimitBonus`, and claim-capacity UI hooks; DB migrations include an empty `DUNE-94841_subfief_cap.sql`. | `scripts/apply-subfief-limit-knob.sh .env` writes `DunePlayerCharacterAttributeSet.SubfiefLimitBonus` into persisted player actors and installs a DB trigger to stamp future player actor saves. `DUNE_SUBFIEF_LIMIT_BONUS` wins when set. Validate in game before calling this confirmed. |
| Spice bloom frequency | Caps and DB behavior are validated. | Test higher medium/large caps and watch `spicefield_types` / `resourcefield_state`. |
| Buried treasure | Loot table and binary fields found; no DB state. | Use in-game/admin commands `LootPrintTreasureCount` and `LootSpawnTreasure`; check logs for parsed config values. |
| Shipwreck/downed ships | Encounter and patrol systems found; no dynamic DB state. | Use patrol/crash-site commands and Deep Desert logs to identify runtime selection behavior. |
| Item grants | Schema and movement functions mapped. | Map character inventory component hashes and item stats templates before writing gear grants. |
| Skills/recipes | Progression tables identified, exact unlock write path not mapped. | Search functions/tables around `specialization_*`, `removed_recipes`, `building_progression`, and player tags. |
| Vehicles | Schema known; no live examples. | Create/spawn a vehicle, then diff `vehicles`, `vehicle_modules`, module inventories, and actor rows. |
| Guild limits | Config and DB functions known. | Create a guild and verify whether config limits are enforced server-side or UI-side. |
| Respawn rules | Config and DB table known. | Create/delete respawn beacon/checkpoint/base totem examples and watch `player_respawn_locations`. |

## Shipped Defaults Worth Knowing

These are exact or near-exact shipped defaults from `DefaultGame.ini` that are
likely to matter during self-host tuning.

### Sandstorm and Coriolis

Section: `[/Script/DuneSandbox.SandStormConfig]`

| Key | Shipped value | Notes |
| --- | --- | --- |
| `m_bAutoSpawnEnabled` | `True` | General sandstorm auto-spawn toggle. |
| `m_bSandStormDebrisEnabled` | `True` | Enables storm debris actors. |
| `m_SandStormDebrisSpeed` | `3000.000000` | Debris movement speed. |
| `m_PlayerOverlapCheckIntervalInSeconds` | `1.000000` | Player storm-overlap check cadence. |
| `m_BuildingOverlapCheckIntervalInSeconds` | `5.000000` | Building storm-overlap check cadence. |
| `m_PlaceableOverlapCheckIntervalInSeconds` | `5.000000` | Placeable storm-overlap check cadence. |
| `m_VehicleOverlapCheckIntervalInSeconds` | `3.000000` | Vehicle storm-overlap check cadence. |
| `m_DamageFramesPerOverlapInterval` | `15` | Damage application granularity inside overlap intervals. |
| `m_NetCullDistanceInMeters` | `10000.000000` | Storm network cull distance. |
| `m_FadeDistanceInMeters` | `9000.000000` | Storm visual fade distance. |
| `m_bCoriolisAutoSpawnEnabled` | `True` | Repo currently overrides this to `False`. |
| `m_CoriolisSpawnWarningsDurationInHours` | `6` | Warning period before Coriolis. |
| `m_CoriolisStage1DurationInSeconds` | `32400.000000` | 9 hours. |
| `m_CoriolisStage2DurationInSeconds` | `3540.000000` | 59 minutes. |
| `m_CoriolisStage3DurationSeconds` | `60.000000` | 1 minute. |
| `m_CoriolisStage4DurationSeconds` | `60.000000` | 1 minute. |
| `m_CoriolisStage5DurationSeconds` | `1740.000000` | 29 minutes. |
| `m_CoriolisSandstormSpawnPreventionSeconds` | `600.000000` | Prevents normal sandstorm spawn near Coriolis. |
| `m_bCoriolisDoesDamage` | `False` | Damage disabled by default in this config. |
| `m_bCoriolisTriggerShiftingSands` | `False` | Shifting-sands trigger disabled here. |
| `m_CoriolisLightDamage` | `5.000000` | Damage scalar if damage is enabled. |
| `m_CoriolisHeavyDamage` | `5000.000000` | Heavy damage scalar if damage is enabled. |
| `m_TotemShortCircuitTimeAfterCoriolis` | `300.000000` | Totem disruption window after Coriolis. |
| `m_TotemShortCircuitTimeAfterSandstorm` | `300.000000` | Totem disruption window after normal storm. |
| `m_SmallSandStormDamageConfig` | `Player/Building/Placeable/Vehicle=5` | Small storm damage config. |
| `m_LargeSandStormDamageConfig` | `Player/Building/Placeable/Vehicle=7` | Large storm damage config. |

Section: `[/Script/DuneSandbox.CoriolisSubsystem]`

| Key | Shipped value | Notes |
| --- | --- | --- |
| `m_CycleStartYear/Month/Day/Hour/Minute` | `2024/12/3/5/0` | Base cycle start timestamp. |
| `m_CycleDurationInDays` | `7` | Deep Desert weekly cycle. |
| `m_CycleStartSeedIndex` | `0` | Seed index for cycle start. |
| `m_ForcedCoriolisWorldSeed` | `-1` | `-1` likely means not forced. |
| `m_bShouldRestartServerOnCycleEnd` | `True` | Restart behavior at cycle end. |
| `m_bIsDbWipeEnabled` | `True` | Very high-risk wipe behavior. Back up before changing/testing. |

### Random Encounters and Contracts

Section: `[/Script/DuneSandbox.EncountersSubsystem]`

| Key | Shipped value | Notes |
| --- | --- | --- |
| `m_bAreRandomEncountersEnabled` | `True` | Master random encounter toggle. |
| `m_RandomEncounterInstigationAroundPlayersBoxExtentInMeters` | `500` | Around-player random encounter search volume. |
| `m_RandomEncounterInstigationAroundPlayersDelayInSec` | `15.000000` | Around-player polling cadence. |
| `m_RandomEncounterInstigationOnWholeServerDelayInSec` | `60.000000` | Whole-server polling cadence. |
| `m_RandomEncounterInstigationByAreaDelayInSecOverride` | `-1.000000` | Area override disabled/default. |
| `m_bAreEncounterAreaLimitsEnabled` | `True` | Enables area limits. |
| `m_SpiceCollectorsAttackChance` | `0.000030` | Named attack chance; exact event trigger still needs testing. |
| `m_bAreEncounterNodesEnabled` | `True` | Enables encounter nodes. |
| `m_bIsRandomEncounterInstigationAroundPlayersEnabled` | `True` | Around-player instigation enabled. |
| `m_bIsRandomEncounterInstigationOnWholeServerEnabled` | `True` | Whole-server instigation enabled. |
| `m_bIsRandomEncounterInstigationOnWholeServerForced` | `False` | Forced mode disabled. |
| `m_bIsRandomEncounterInstigationByAreaEnabled` | `True` | Area instigation enabled. |
| `m_DisabledEncounterNames` | `DE_120_SmallShipWreck_DeepDesert_Depricated` | Only this deprecated DD small shipwreck is explicitly disabled. |

Section: `[/Script/DuneSandbox.ContractsSubsystem]`

| Key | Shipped value | Notes |
| --- | --- | --- |
| `m_bIsEnabled` | `True` | Contract subsystem enabled. |
| `m_bIsIgwSupportEnabled` | `True` | IGW support enabled. |
| `m_MaxContractVariationsNum` | `5` | Contract variation cap. |
| `m_MaxGlobalContractsNumberPerServer` | `10` | Global contracts per server cap. |
| `m_bShouldGroupAvailableContracts` | `True` | Groups available contracts. |
| `m_MinNumOfPlayersOnServerForContractSpawn` | `1` | Spawn requires at least one player. |
| `m_TickRateInSec` | `1.000000` | Contract subsystem tick. |
| `m_InitialTickDelayInSec` | `1.000000` | Initial tick delay. |
| `m_ContractSpawnDelayInSec` | `0.000000` | Spawn delay. |
| `m_ContractLifetimeCheckDelayInSec` | `15.000000` | Lifetime check cadence. |
| `m_ContractConditionCheckDistance` | `100` | Condition check distance. |

### Respawn and Travel

Section: `[/Script/DuneSandbox.RespawnSettings]`

| Key | Shipped value / summary | Notes |
| --- | --- | --- |
| `m_RespawnMapSettings` | Hagga Basin allows cross-map destination; Deep Desert disables checkpoint group | This is the source of the earlier “respawn rules” note. |
| `m_RespawnLocationMapLimit` | Vehicle, Checkpoint, BaseTotem, RespawnBeacon groups each have limit `1` | Looks like per-player/per-map saved respawn-location caps by group. |
| `m_bCrossMapRespawnDropItems` | `True` | Cross-map respawn drops items. |
| `m_IgnoringRespawnTimerSpawnLocationGroup` | `CheckpointEntrySpawn`, `PlayerStart` | These groups bypass respawn timer. |
| `m_ManualRespawnDisabled` | Arrakeen, HarkoVillage, NPE, Overland, ProcesVerbal, and other non-normal maps | Manual respawn disabled for listed map groups. |

Travel-related sections:

| Section | Key | Shipped value / summary | Notes |
| --- | --- | --- | --- |
| `[/Script/DuneSandbox.TravelDestinationSubsystem]` | `m_TravelDestinationsDataAsset` | `/Game/Dune/Systems/Travel/DA_TravelDestinations.DA_TravelDestinations` | Travel routes are mostly data-asset driven. |
| `[/Script/DuneSandbox.TaxiService]` | `m_DisableTravelTo` | `()` | Empty shipped block list. |
| `[/Script/DuneSandbox.TaxiService]` | `m_DisableTravelFrom` | `()` | Empty shipped block list. |
| `[/Script/DuneSandbox.JourneySubsystem]` | `+m_TravelRequestFallbackNames` | `Arrakeen_to_Overland`, `Overland_to_Arrakeen`, `Overland_to_Harko_N` | Fallback travel request names. |

### Guilds, Loot, and Exchange

| Section | Key | Shipped value | Notes |
| --- | --- | --- | --- |
| `[/Script/DuneSandbox.LootSettings]` | `GlobalLootRightsBehaviour` | `PerPlayerChestAndNpcDrop` | Global loot-rights policy. |
| `[/Script/DuneSandbox.GuildSettings]` | `m_GuildCreationCost` | `1000` | Guild creation Solaris cost candidate. |
| `[/Script/DuneSandbox.GuildSettings]` | `m_MaxGuildsAllowed` | `3` | Max guild count candidate. |
| `[/Script/DuneSandbox.GuildSettings]` | `m_MaxGuildMembersAllowed` | `32` | Max members per guild candidate. |
| `[/Script/DuneSandbox.GuildSettings]` | `m_MaxPendingGuildInvitesAllowed` | `10` | Pending invite cap candidate. |
| `[/Script/DuneSandbox.DuneExchangeSettings]` | `SellOrderDailySolarisFee` | `20` | Exchange sell-order daily fee. |
| `[/Script/DuneSandbox.DuneExchangeSettings]` | `SellOrderPricePercentageFee` | `2.000000` | Exchange sell-order percent fee. |

Local override in `config/UserGame.ini` sets both values to `0` for a no-fee
private-server exchange.

### Admin and Progression Leads

| Section | Key | Shipped value / summary | Notes |
| --- | --- | --- | --- |
| `[AdminSetting.Global]` | `Password_Admin` | `sardaukar` | Shipped default admin password entry. Do not publish real local secrets. |
| `[AdminSetting.Global]` | `+Allowed_Commands` | `suicide`, `AdminLogin`, `PrintAllowedCommands`, bug/help UI commands | This is separate from `DedicatedServerGame.ini` GM command allow-list. |
| `[/Script/DuneSandbox.TechKnowledgeSettings]` | `m_TechTreeUpgrades` | `/Game/Dune/Systems/TechKnowledge/Data/DA_TechTreeUpgrades.DA_TechTreeUpgrades` | Tech tree unlock data asset. |
| `[/Script/DuneSandbox.TechKnowledgeSettings]` | `m_bRevealItemOnDistributedToCharacter` | `False` | Item reveal behavior when distributing to a character. |
| `[/Script/DuneSandbox.JourneySubsystem]` | `m_JourneyProgressionStatePresets` | Large preset map with completed journeys, revealed journeys, add/remove tags, and some item grants | Important evidence for future admin “set story/progression preset” tooling. |
| `[/Script/DuneSandbox.JourneySubsystem]` | `m_SandwormDeathLimboSettings` | Awards sandbike parts/fuel/repair tool on positive outcome | Confirms some progression/item awards are config-described. |

## Useful Queries

```bash
docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select 'actors' area,count(*) from dune.actors union all select 'items',count(*) from dune.items union all select 'inventories',count(*) from dune.inventories;"

docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select template_id,count(*) rows,sum(stack_size) total_stack_size from dune.items group by 1 order by rows desc,total_stack_size desc limit 30;"

docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select inventory_type,count(*) inventories,min(max_item_count),max(max_item_count),min(max_item_volume),max(max_item_volume) from dune.inventories group by 1 order by 1;"

docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select class,count(*) actors from dune.actors group by 1 order by actors desc,class limit 40;"

docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select map,dimension_index,count(*) partitions from dune.world_partition group by 1,2 order by 1,2;"
```
