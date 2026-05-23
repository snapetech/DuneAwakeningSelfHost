# Live Client Validation

Use this checklist after the 30-partition warm pool is server-ready. Server readiness proves that containers, Director, Gateway, Postgres, and RabbitMQ agree on the farm. It does not prove that the live client can route into every destination.

## Before Testing

Run a clean status check:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/status.sh .env
```

Confirm the client-facing RabbitMQ certificate covers the address FLS will hand to clients:

```bash
./scripts/check-rabbitmq-cert-sans.sh .env
```

Expected server-side baseline:

```text
current_alive_active=31 active_servers=31 partitions=31
```

Create a baseline capture:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/capture-routing.sh .env pre-client-validation
```

## How To Capture A Failed Transition

When a transition fails, immediately run:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/capture-routing.sh .env failed-<from>-to-<to>
```

Use short lowercase labels, for example:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/capture-routing.sh .env failed-survival-to-arrakeen
```

## Core Route Checklist

Record the result, client symptom, and capture path for every failed step.

| Status | From | To / Target | Partition | Map |
| --- | --- | --- | ---: | --- |
| TODO | Login | Starting world | 1 | `Survival_1` |
| TODO | Survival | Overmap | 2 | `Overmap` |
| TODO | Overmap | Arrakeen | 3 | `SH_Arrakeen` |
| TODO | Overmap | Harko Village | 4 | `SH_HarkoVillage` |
| TODO | Overmap | Deep Desert | 8 | `DeepDesert_1` |
| TODO | Overmap/Quest | Proces Verbal | 9 | `Story_ProcesVerbal` |

## Testing / Story / Dungeon Checklist

| Status | Target | Partition | Map |
| --- | --- | ---: | --- |
| TODO | Wreck of the Hephaestus story/testing | 5 | `CB_Story_Hephaestus` |
| TODO | Beneath Old Carthag story/testing | 6 | `CB_Story_Ecolab_Carthag` |
| TODO | Water Fat Manor story/testing | 7 | `CB_Story_WaterFatManor` |
| TODO | Lost Harvest Ecolab A | 10 | `DLC_Story_LostHarvest_EcolabA` |
| TODO | Lost Harvest Ecolab B | 11 | `DLC_Story_LostHarvest_EcolabB` |
| TODO | Lost Harvest Forgotten Lab | 12 | `DLC_Story_LostHarvest_ForgottenLab` |
| TODO | Art of Kanly | 13 | `Story_ArtOfKanly` |
| TODO | Hephaestus revisit dungeon | 14 | `CB_Dungeon_Hephaestus` |
| TODO | Old Carthag revisit dungeon | 15 | `CB_Dungeon_OldCarthag` |
| TODO | Atreides faction outpost | 16 | `Story_Faction_Outpost_Atre` |
| TODO | Harkonnen faction outpost | 17 | `Story_Faction_Outpost_Hark` |
| TODO | Heighliner dungeon | 18 | `Story_HeighlinerDungeon` |
| TODO | Radiation ecolab | 19 | `CB_Ecolab_Bronze_Green_089` |
| TODO | Electricity ecolab | 20 | `CB_Ecolab_Bronze_Green_152` |
| TODO | Darkness ecolab | 21 | `CB_Ecolab_Bronze_Green_024` |
| TODO | Poison ecolab | 22 | `CB_Ecolab_Bronze_Green_195` |
| TODO | Fire ecolab | 23 | `CB_Ecolab_Bronze_Green_136` |
| TODO | Radioactive Shipwreck | 24 | `CB_Overland_M_01` |
| TODO | Erythrite Cave Island | 25 | `CB_Overland_S_04` |
| TODO | Ground Vehicle Time Trial Island | 26 | `CB_Overland_S_06` |
| TODO | Sandflies Fortress | 27 | `CB_Story_BanditFortress01` |
| TODO | The Ruins of Tsimpo | 28 | `CB_Overland_S_07` |
| TODO | Wind Pass | 29 | `CB_Overland_S_08` |
| TODO | The Pit | 30 | `CB_Dungeon_ThePit` |

## RabbitMQ Signals To Watch

For all 30 maps, game RabbitMQ should show 30 unique `sg.*.game` users and usually 60 connections.

Admin RabbitMQ can have fewer active connections at any exact moment, but all map queues should exist and failed transitions should not correlate with repeated `failed authenticating`, `access_refused`, or `Failed to open TCP socket for admin-rmq` errors.

Fast health check:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

Check counts:

```bash
docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env exec -T game-rmq \
  rabbitmqctl list_connections user peer_host state

docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env exec -T admin-rmq \
  rabbitmqctl list_connections user peer_host state
```

If `rmq-health.sh` reports no recent errors, proceed with client travel tests even if admin-RMQ has fewer than 30 unique map hosts connected. Treat admin-RMQ as a failure signal only when errors line up with a failed transition or when queues are missing consumers.
