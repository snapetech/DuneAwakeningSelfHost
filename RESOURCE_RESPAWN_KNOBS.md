# Resource Respawn Knob Research

Status: no confirmed self-host `.ini` key has been found yet for the actual respawn timer of ordinary ore, scrap metal, or fuel/fuel-cell world nodes.

This note tracks the evidence found so far so we do not confuse resource-node spawning, spice/resource fields, loot containers, NPC/player respawn, and ordinary node respawn timers.

## Confirmed Shipped Config

These sections exist in the server image's `DuneSandbox/Config/DefaultGame.ini` and in the generated config index.

```ini
[/Script/DuneSandbox.ResourceLocationSystem]
m_bIsEnabled=True
m_ResourcePointTrace=MoveUpwards
m_ResourceSpawnChance=1.0

[/Script/DuneSandbox.ResourceNodeSpawner]
m_ResourceSpawnChance=1.0

[/Game/Dune/Systems/GlobalDistribution/BP_BrittleBush_Spawner.BP_BrittleBush_Spawner_C]
m_ResourceSpawnChance=1.0
```

Interpretation:

- `m_ResourceSpawnChance` is confirmed as a shipped key.
- It is probably a spawn/placement chance for resource instances, not a depletion respawn timer.
- It may affect ore/scrap/fuel node density after map startup, but it should be treated as unvalidated until tested by changing it and comparing spawned node counts after a map restart.

`[/Script/DuneSandbox.MiscSettings]` also contains mining yield behavior:

```ini
m_MiningSettings=(...,ResourceTierMap=(((Name="Stone"), 1),((Name="MagnetiteOre"), 2),((Name="AzuriteOre"), 1),...,((Name="ScrapMetal"), 1),((Name="Oil"), 1),((Name="ScrapElectronics"), 1),...))
```

Interpretation:

- This maps resource item IDs to mining tiers and cutteray scaling data.
- It is useful for yield/difficulty research, but it is not a respawn timer.

`[/Script/DuneSandbox.LootSettings]` has only the global loot-rights key in tracked shipped config:

```ini
GlobalLootRightsBehaviour=PerPlayerChestAndNpcDrop
```

The binary/config index also exposes these loot-related values:

- `PerPlayerLootHiddemItemRefreshTime=5.000000`
- `PerPlayerLootMinimumDespawnTimeAfterInteraction=30.000000`

Interpretation:

- These look like per-player loot visibility/refresh/despawn values.
- They are not confirmed world resource-node respawn controls.

## Binary Evidence

The server executable contains real resource-node types and respawn-related names:

- `AResourceNode`
- `AResourceNodeSpawner`
- `AResourceSpawner`
- `AResourceNodePlaceableSpawner`
- `UResourceNodeComponent`
- `UResourceNodeData`
- `UResourceSpawnerData`
- `FResourceRespawnTimer`
- `FResourceSpawnerConfig`
- `FResourceNodeSpawnInfo`
- `m_bShouldRespawnResources`
- `m_DefaultRespawnTimeInSec`
- `MinimumRespawnTimeInSec`
- `MaximumRespawnTimeInSec`

Important caveat:

- These strings prove the engine has resource respawn machinery.
- They do not prove the correct `.ini` section or override syntax.
- Do not add guessed overrides such as `m_DefaultRespawnTimeInSec=...` until the owning class/section is mapped.

The nearest binary cluster is:

```text
FResourceNodePoint
FResourceNodeCluster
FResourceNodePointGroup
FResourceNodeZone
UResourceNodeData
FResourceRespawnTimer
AResourceSpawner
AResourceNodeSpawner
FResourceSpawnerConfig
```

This strongly suggests ordinary resource nodes have a structured config/data-asset path, but the values are probably stored in cooked data assets rather than plain shipped `.ini`.

## Live Log Evidence

Live map logs show ordinary nodes being created by resource spawners. Examples observed from `deep-desert`:

```text
LogResourceSpawning: AResourceSpawner::SetSpawnRange(): ResourceSpawner "BP_AzuriteOre_A_Spawner_C ..."
LogResourceSpawning: AResourceSpawner::SetSpawnRange(): ResourceSpawner "BP_ScrapMetal_C_Spawner_C ..."
LogResourceSpawning: AResourceSpawner::SetSpawnRange(): ResourceSpawner "BP_ScrapMetal_Pickup_C_Spawner_C ..."
LogResourceSpawning: AResourceSpawner::SetSpawnRange(): ResourceSpawner "BP_ImpureFuel_Spawner_C ..."
LogResourceSpawning: AResourceSpawner::SetSpawnRange(): ResourceSpawner "BP_ImpureFuel_Pickup_Spawner_C ..."
```

Live `survival` logs also show depleted/not-ready nodes:

```text
LogResourceNode: Unable to mine BP_ScrapMetal_A_Minigame_C ... It's either not ready or has no remaining health.
LogResourceNode: Unable to mine BP_ScrapElectronics_Minigame_C ... It's either not ready or has no remaining health.
LogResourceNode: Unable to mine BP_RhyoliteStone_B_Minigame_C ... It's either not ready or has no remaining health.
```

Interpretation:

- Ore/scrap/fuel world resources are ordinary resource-node actors/spawners, not only database-backed spice fields.
- The server knows whether a node is ready and has remaining health.
- We have not yet found where the ready/respawn timer state is persisted, if it is persisted at all.

## Database Evidence

The game database has these related tables:

```text
dune.actor_spawners
dune.actor_spawner_actors
dune.resourcefield_state
dune.spicefield_server_availability
dune.spicefield_types
```

Observed counts during this investigation:

```text
actor_spawners: 526
actor_spawner_actors: 13
resourcefield_state: 79
```

`dune.resourcefield_state` columns:

```text
field_id
map
dimension_index
spawn_time
value_remaining
field_kind_id
```

`resourcefield_state` currently groups into Deep Desert and Hagga Basin field kinds, with large `value_remaining` values. This looks relevant to spice/resource fields and `LogResourceField`, not necessarily ordinary ore/scrap/fuel node actors.

Resource-field functions:

```text
fetch_resourcefield_state(in_map, in_dimension_index, in_field_kind_id)
update_resourcefield_states(in_map, in_dimension_index, in_field_kind_id, in_field_states)
remove_resourcefield_states(in_map, in_dimension_index, in_field_ids)
```

Spice-field functions:

```text
register_spice_field_server_resources(...)
request_spawn_spice_field(...)
try_prime_spicefield(...)
try_restart_spicefield(...)
try_spawn_spicefield(...)
update_global_spice_field_rules(...)
```

Interpretation:

- Spice/resource fields are DB-backed and already well surfaced.
- Ordinary resource nodes appear mostly actor/data-asset driven.
- The DB tables do not yet expose an obvious ore/scrap/fuel respawn timer row.

## Candidate Knobs

| Candidate | Evidence | Confidence | Notes |
| --- | --- | --- | --- |
| `[/Script/DuneSandbox.ResourceNodeSpawner] m_ResourceSpawnChance` | Shipped config | Medium for spawn density, low for respawn timer | Safest first experiment for node density after restart. |
| `[/Script/DuneSandbox.ResourceLocationSystem] m_ResourceSpawnChance` | Shipped config | Medium for resource point generation, low for respawn timer | Could affect global resource point placement. |
| `[/Game/Dune/Systems/GlobalDistribution/BP_BrittleBush_Spawner.BP_BrittleBush_Spawner_C] m_ResourceSpawnChance` | Shipped config | High for brittle bush only | Specific blueprint spawner override. Pattern may apply to other spawner blueprint sections if the exact path is known. |
| `FResourceRespawnTimer` | Binary type | High that respawn exists internally, low for direct `.ini` | Need owning asset/class fields. |
| `FResourceSpawnerConfig` | Binary type | Medium | Likely holds data-asset config for spawner behavior. |
| `m_bShouldRespawnResources` | Binary string | Medium | Strong name, but owner/section unknown. |
| `m_DefaultRespawnTimeInSec` | Binary string | Low/medium | Appears near resource-field/node strings but could be a different respawn system. |
| `MinimumRespawnTimeInSec` / `MaximumRespawnTimeInSec` | Binary strings | Low | Appears near loot/Journey/NPC-ish clusters; not enough to bind to resource nodes. |
| `PerPlayerLootHiddemItemRefreshTime` | Binary/config index | Low for resources | Probably per-player loot hidden item refresh. Typo is in shipped key name. |
| `PerPlayerLootMinimumDespawnTimeAfterInteraction` | Binary/config index | Low for resources | Likely loot container despawn behavior. |

## Experiment Plan

Safe first experiments:

1. Add only confirmed keys to `config/UserGame.ini`, one at a time.
2. Restart/recreate one test map container.
3. Compare `LogResourceSpawning` counts and spawned class names before/after.
4. Mine a known node, record the server log actor name and timestamp, then watch for readiness after the public-observed 10-minute window.
5. Query `actor_spawners`, `actor_spawner_actors`, and `resourcefield_state` before/after mining to see whether ordinary node readiness is persisted.

Do not guess these yet:

```ini
m_bShouldRespawnResources=True
m_DefaultRespawnTimeInSec=...
MinimumRespawnTimeInSec=...
MaximumRespawnTimeInSec=...
```

Those keys need a confirmed section/owner first.

## Commands Used

Inspect shipped resource sections:

```bash
docker compose --env-file .env exec -T survival sh -lc \
  'sed -n "/ResourceLocationSystem/,+20p" /home/dune/server/DuneSandbox/Config/DefaultGame.ini'
```

Inspect resource DB tables:

```bash
docker compose --env-file .env exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -c \
  "select table_schema, table_name from information_schema.tables where table_schema='dune' and (table_name ilike '%resource%' or table_name ilike '%spawn%' or table_name ilike '%field%') order by 1,2;"
```

Inspect resource/spawn logs:

```bash
docker compose --env-file .env logs --no-color --tail=400 survival deep-desert | \
  rg -i "resource|respawn|spawn|harvest|ore|scrap|fuel|field"
```

Extract binary string evidence without copying the executable:

```bash
docker compose --env-file .env exec -T survival python3 - <<'PY'
from pathlib import Path
import re
p = Path('/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping')
data = p.read_bytes()
strings = []
cur = []
for b in data:
    if 32 <= b < 127:
        cur.append(chr(b))
    else:
        if len(cur) >= 4:
            strings.append(''.join(cur))
        cur = []
if len(cur) >= 4:
    strings.append(''.join(cur))
patterns = [re.compile(x, re.I) for x in [
    'Resource.*Respawn', 'Respawn.*Resource', 'Resource.*Spawn',
    'ResourceNode', 'ResourceSpawner', 'ResourceLocation',
    'ResourceField', 'Harvestable', 'MiningYield', 'MiningSettings',
    'DefaultRespawnTime', 'RespawnTimeInSec', 'ShouldRespawn',
]]
for s in strings:
    if any(p.search(s) for p in patterns):
        print(s)
PY
```
