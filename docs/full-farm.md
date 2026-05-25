# Full Standing Farm / Warm Pool

This Compose layout can run either the initial nine-map standing farm or the full 30-partition warm pool.

Funcom's template treats most of the non-starting maps as `dedicatedScaling` / on-demand capacity with `replicas: 0`. In Kubernetes, the operator and Director can create those game-server pods when a travel/instance trigger needs them. In Compose, there is no operator, so `compose.allmaps.yaml` keeps one server container warm for every official single-dimension self-host partition. That is a warm-pool substitute for on-demand scaling, not true elastic scaling.

The base standing services cover partitions 1-9. The all-maps overlay adds partitions 10-30. Partition 31 / PvP Deep Desert is intentionally disabled in the live farm.

## Services

| Service | Map | Partition | Game UDP | IGW UDP |
| --- | --- | ---: | ---: | ---: |
| `survival` | `Survival_1` | 1 | 7777 | 7888 |
| `overmap` | `Overmap` | 2 | 7778 | 7889 |
| `arrakeen` | `SH_Arrakeen` | 3 | 7779 | 7890 |
| `harko-village` | `SH_HarkoVillage` | 4 | 7780 | 7891 |
| `testing-hephaestus` | `CB_Story_Hephaestus` | 5 | 7781 | 7892 |
| `testing-carthag` | `CB_Story_Ecolab_Carthag` | 6 | 7782 | 7893 |
| `testing-waterfat` | `CB_Story_WaterFatManor` | 7 | 7783 | 7894 |
| `deep-desert` | `DeepDesert_1` | 8 | 7784 | 7895 |
| `proces-verbal` | `Story_ProcesVerbal` | 9 | 7785 | 7896 |
| `lostharvest-ecolab-a` | `DLC_Story_LostHarvest_EcolabA` | 10 | 7786 | 7897 |
| `lostharvest-ecolab-b` | `DLC_Story_LostHarvest_EcolabB` | 11 | 7787 | 7898 |
| `lostharvest-forgottenlab` | `DLC_Story_LostHarvest_ForgottenLab` | 12 | 7788 | 7899 |
| `art-of-kanly` | `Story_ArtOfKanly` | 13 | 7789 | 7900 |
| `dungeon-hephaestus` | `CB_Dungeon_Hephaestus` | 14 | 7790 | 7901 |
| `dungeon-oldcarthag` | `CB_Dungeon_OldCarthag` | 15 | 7791 | 7902 |
| `faction-outpost-atre` | `Story_Faction_Outpost_Atre` | 16 | 7792 | 7903 |
| `faction-outpost-hark` | `Story_Faction_Outpost_Hark` | 17 | 7793 | 7904 |
| `heighliner-dungeon` | `Story_HeighlinerDungeon` | 18 | 7794 | 7905 |
| `ecolab-green-089` | `CB_Ecolab_Bronze_Green_089` | 19 | 7795 | 7906 |
| `ecolab-green-152` | `CB_Ecolab_Bronze_Green_152` | 20 | 7796 | 7907 |
| `ecolab-green-024` | `CB_Ecolab_Bronze_Green_024` | 21 | 7797 | 7908 |
| `ecolab-green-195` | `CB_Ecolab_Bronze_Green_195` | 22 | 7798 | 7909 |
| `ecolab-green-136` | `CB_Ecolab_Bronze_Green_136` | 23 | 7799 | 7910 |
| `overland-m-01` | `CB_Overland_M_01` | 24 | 7800 | 7911 |
| `overland-s-04` | `CB_Overland_S_04` | 25 | 7801 | 7912 |
| `overland-s-06` | `CB_Overland_S_06` | 26 | 7802 | 7913 |
| `bandit-fortress` | `CB_Story_BanditFortress01` | 27 | 7803 | 7914 |
| `overland-s-07` | `CB_Overland_S_07` | 28 | 7804 | 7915 |
| `overland-s-08` | `CB_Overland_S_08` | 29 | 7805 | 7916 |
| `dungeon-thepit` | `CB_Dungeon_ThePit` | 30 | 7806 | 7917 |

## Start

Nine-map standing farm:

```bash
./scripts/full-world-partitions.sh .env

docker compose --env-file .env up -d \
  survival overmap arrakeen harko-village \
  testing-hephaestus testing-carthag testing-waterfat \
  deep-desert proces-verbal

./scripts/status.sh .env
```

Expected status:

```text
current_alive_active=9 active_servers=9 partitions=9
```

Full 30-partition warm pool:

```bash
./scripts/start-full-warm-pool.sh .env
```

If any control-plane container is force-recreated outside the startup helper,
refresh the host-side bridge neighbor entries:

```bash
./scripts/seed-gateway-neighbor.sh
```

Expected status:

```text
current_alive_active=30 active_servers=30 partitions=30
```

## Network

Forward `7777-7785/udp` from the router to the host for the full standing farm.

Forward `7777-7806/udp` from the router to the host for the full 30-partition warm pool.

Forward `7888-7917/udp` from the router to the host for the full 30-partition warm pool when your deployment uses the paired IGW ports for live-client routing or server-browser checks. These are the IGW ports paired with the gameplay ports.

## Disabled PvP Deep Desert

Partition 31 / PvP Deep Desert is deliberately disabled. It is prepped behind
the `disabled-deep-desert-pvp` Compose profile with its own
`config/UserGame.deep-desert-pvp.ini` override, separate saved-data directory,
and ports `7807/udp` plus `7918/udp`. Do not include it in restart targets,
watchdog expectations, public status, or router forwarding until it is
intentionally promoted and validated.

Coriolis is not currently proven to be partition-scoped. The known config
surface exposes `m_bCoriolisAutoSpawnEnabled` under `SandStormConfig` and
cycle/wipe fields under `CoriolisSubsystem`, which appear global. PvP DD keeps
auto-spawn, Shifting Sands trigger, and DB wipe disabled in its dedicated config
until partition-specific behavior is validated on live routing.

To intentionally bring PvP DD online after a maintenance window, keep it as a
manual opt-in:

1. Set `DUNE_WORLD_PARTITION_COUNT=31` for the activation command or in `.env`
   only when partition 31 should be monitored and included in all-target
   restarts.
2. Run `DUNE_WORLD_PARTITION_COUNT=31 ./scripts/full-world-partitions.sh .env`
   to add `DeepDesert_1` dimension `1` / partition `31`.
3. Start only the PvP DD service with
   `DUNE_WORLD_PARTITION_COUNT=31 docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env up -d --no-deps deep-desert-pvp`.
4. Validate partition `31` in `dune.world_partition`, `dune.farm_state`, and
   `dune.active_server_ids`, then test routing before adding router forwarding
   or public status/watchdog expectations.

Keep these closed publicly:

- `15431/tcp`, `15672/tcp`, `15673/tcp`, `18080/tcp`: local debug/admin surfaces.

Forward `31982/tcp` when using the live client through Funcom/FLS. Gateway advertises this as the game RabbitMQ endpoint during login; if it advertises Docker-internal `game-rmq:5672`, the client fails before gameplay UDP starts.

## Known-Good Baseline

On May 19, 2026, the local live build registered all 30 official self-host partitions alive and active with the warm-pool overlay:

```text
current_alive_active=30 active_servers=30 partitions=30
```

Earlier the same day, the nine-map base farm also registered alive/active with `current_alive_active=9 active_servers=9 partitions=9`.

## Validation Boundary

Server-side readiness means the containers are running, the maps loaded, Director assigned partitions, Gateway saw the public game ports, and RabbitMQ service users connected.

It does not prove client travel. Validate from the live game client:

- Login to the starting map.
- Travel to Overmap.
- Travel to Arrakeen and Harko Village.
- Travel to Deep Desert.
- Enter testing/story maps and instanced locations represented by partitions 5-30.
- Capture before/after each failed transition with `COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/capture-routing.sh .env <label>`.

Some allowed route aliases exist in game config but do not have a matching official self-host partition row in the current template, for example the parent `DLC_Story_LostHarvest` route and `CB_Overland_S_05`. Those should not be added blindly until client travel or official template changes prove they need a standing server.
