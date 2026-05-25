# Routing Investigation

This document tracks client travel validation after the Compose farm has server-side registration for Hagga Basin, Overmap, Deep Desert, Arrakeen, Harko Village, testing/story maps, and the 30-partition warm pool.

## Current Read

The initial issue looked like buggy or incomplete self-host plumbing, not unreleased content.

Funcom's private-server docs say a rented/private server contains one Hagga Basin. That server belongs to a larger World where the provider supplies shared social hubs and the Deep Desert. CubeCoders' self-host guide lists Deep Desert, Arrakeen, and Testing Stations as currently unreachable, and also lists broken FLS world-name generation.

As of May 19, 2026, the base Compose layout can stand up one ready/alive server for each of:

- `Survival_1`
- `Overmap`
- `SH_Arrakeen`
- `SH_HarkoVillage`
- `CB_Story_Hephaestus`
- `CB_Story_Ecolab_Carthag`
- `CB_Story_WaterFatManor`
- `DeepDesert_1`
- `Story_ProcesVerbal`

With `compose.allmaps.yaml`, the warm-pool layout can stand up all 30 self-host partition rows documented in `docs/full-farm.md`.

The remaining question is whether the live client can travel through those registrations. Likely failure surfaces are:

- FLS world identity or generated world name is wrong.
- Gateway or text-router cannot hand the client to the target instance.
- Token/session handoff fails during travel.
- Advertised ports or addresses are wrong for the target instance.

## Transition Paths To Capture

Capture each transition separately. Do not combine logs from multiple attempts until the signatures are known.

- Hagga Basin to Deep Desert.
- Hagga Basin to Arrakeen.
- Hagga Basin to Testing Station.
- Lost Harvest, Art of Kanly, faction outposts, ecolabs, overland islands, and dungeons represented by partitions 10-30.
- Arrakeen or Harko Village back to overland, if reachable later.
- Deep Desert server-to-server movement, if reachable later.

## Evidence To Collect

For each transition attempt, record:

- Client action and timestamp.
- Source map, target map, character name, and account/session identifier if visible. Keep this local unless it has been scrubbed.
- A capture before the transition.
- A capture immediately after failure.
- Full redacted logs for `director`, `gateway`, `text-router`, all game-server services, `admin-rmq`, and `game-rmq`.
- Rows from `dune.farm_state`, `dune.active_server_ids`, and `dune.world_partition`.
- Player-state counts from `farm_state.connected_players` and the online/recently-disconnected helper functions.
- RabbitMQ users/connections present before and after transition.
- Public and internal addresses advertised by each service.
- All game-server command-line arguments for the source and target map process.

Use the capture helper:

```bash
./scripts/capture-routing.sh .env hagga-to-deep-desert-before
# Attempt the transition in the client.
./scripts/capture-routing.sh .env hagga-to-deep-desert-after
```

For the 30-partition warm pool, include the all-maps overlay:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/capture-routing.sh .env failed-survival-to-arrakeen
```

Captures are written under `captures/`, which is ignored by git. Review every capture before sharing it because logs and database rows can still contain world names, addresses, character names, or account/session identifiers.

## Log Signals

Start by searching for:

```text
travel
transition
partition
instance
Deep
Arrakeen
Testing
FLS
World
Battlegroup
Auth
Token
Session
gateway
director
farm
ready
```

The useful pattern is the first component that disagrees with the intended transition. For example, a client request that reaches gateway but never appears in director is a different failure than a director assignment that points at a missing map process.

Observed local signatures worth tracking:

- `LogTravelDestination: Warning: Duplicated TravelDestination(...) for Map(DeepDesert) already exists on Map(HaggaBasin)`
- `LogTravelDestination: Warning: Duplicated TravelDestination(...) for Map(CombatGym_Camps) already exists on Map(HaggaBasin)`
- `LogGameSession: Warning: Autologin attempt failed, unable to register server!`
- `LogIGW: Display: Server ... listening for Clients on ...`
- `LogIGW: Display: Server ... listening for Servers on ...`

The duplicated travel-destination warnings are not proof of the routing bug by themselves. They are useful markers because they mention target-map transition data during `Survival_1` startup and should be compared against an operator-generated or provider-working topology.

Partition 31 / second Deep Desert is opt-in, so routing checks should expect only the partition 8 `DeepDesert_1` registration unless `DUNE_WORLD_PARTITION_COUNT=31` is deliberately staged. Confidence: high.

## Database Questions

Answer these with status snapshots and ad hoc SQL:

- Does the target map appear in `world_partition`?
- Does the target map get a `farm_state` row?
- If a row exists, is it `ready` and `alive`?
- Are `game_addr` and `igw_addr` populated and externally sensible?
- Does `active_server_ids` include the target map's server id?
- Does a failed transition create, update, or remove any rows?
- Do online/recently-disconnected player counts change during a failed transition?
- Does `player_travel_state` change during a failed transition?

## RabbitMQ Questions

Answer these with `rabbitmqctl` and logs:

- Does the target map create expected `.game` and `.admin` service users?
- Does the target map connect to `game-rmq`?
- Are there auth failures from generated service users?
- Does the auth shim receive a request for the target map?
- Are messages published to a queue that has no consumer?

## Launch Parity Questions

The direct game-server launch path is sufficient for server-side registration in this Compose topology. For unreachable client routes, compare against the official operator output:

- Map name and partition index.
- `ServerName`, `DatacenterId`, `FarmRegion`, and battlegroup display name.
- `MultiHome`, `POD_IP`, external address, and port assignments.
- Database name and connection args.
- RabbitMQ host, port, TLS, and auth arguments.
- Any per-map flags synthesized by the operator.

## References

- Funcom private-server model: https://funcom.helpshift.com/hc/en/4-dune-awakening/faq/59-private-servers/
- CubeCoders self-host known issues: https://discourse.cubecoders.com/t/dune-awakening-server-guide/40200
- Funcom 1.1.10.0 patch notes: https://duneawakening.com/news/dune-awakening-1-1-10-0-patch-notes/
