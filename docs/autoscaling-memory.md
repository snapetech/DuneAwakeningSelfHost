# Dynamic Maps and Memory Balancing

The Infrastructure page provides persistent map modes, automatic idle
scale-down, Director travel-demand scale-up, manual reconciliation, live memory
limits, and an automatic memory balancer.

## Dynamic map autoscaler

State is stored in `backups/admin-panel/autoscaler.json`. Every map service has
one mode:

- `always-on`: start it whenever it is not running;
- `dynamic`: start it on demand and stop it after the zero-player idle window;
- `disabled`: keep it stopped, but refuse a stop while players remain online.

The worker scans for demand every `DUNE_AUTOSCALER_POLL_SECONDS` (3 seconds by
default) and performs the full Docker/player/lifecycle reconciliation every
`DUNE_AUTOSCALER_RECONCILE_SECONDS` (30 seconds by default). A newly detected
demand bypasses that slower cadence and triggers an immediate reconciliation.
The fast path reads recent Director logs and recognizes all current
travel-demand forms, including the generic dimension queue emitted for Deep
Desert and Overmap:

The fast loop is incremental. After its first bounded 1,000-line Director
scan, it requests only logs since the previous scan with a one-second overlap
and deduplicates the overlapping event fingerprints. Travel selection and map
lifecycle decisions share one Docker inventory snapshot per reconciliation,
and the retained state file is rewritten only when its semantic content
changes. Between full reconciliations it reuses the known Director container
identity, touches no player table, and enumerates Docker only after a new demand
event or a Director-container replacement. This preserves the three-second
demand-response target without running the heavier 31-map lifecycle survey on
every scan.

```text
Processing travel queue for ClassicalInstancing group <Map> (servers: [...], num: N)
Received travel request for N player(s) to <Map> (instancingMode=Dimension)
Processing travel queue for <Map> (..., num=N)
```

Each log line has a SHA-1 event identity retained for 24 hours, preventing
repeated scans from replaying the same request. Matching
`dune.world_partition` rows are mapped to this repository's static Compose map
services. Stopped dynamic services are preferred, and up to the requested
dimension/player count receives a time-limited demand marker. The normal
service start path runs `scripts/restart-target.sh`, including post-start
health and runtime patches. Dynamic starts use the guarded fast path by
default: Compose starts an unchanged stopped container directly, recreates it
only when its configuration changed, validates the Landsraad Coriolis cycle,
and still runs the normal post-start health/runtime hooks. It does not repeat
global database patches, Landsraad tuning, full-partition seeding, image
audits, or global watchdog stop/start for each cold map. Set
`DUNE_AUTOSCALER_FAST_START=false` to use the full workflow. Scale-down uses
Docker's stop API directly so it
does not stop the global map watchdog; the watchdog then recognizes the
persistent dynamic mode and leaves that container intentionally stopped.

An operator can also queue explicit demand from the browser. Demand expires
after `demandTtlSeconds`; the current browser exposes idle-window tuning and
persists the demand TTL in the state file. The map watchdog reads this same
state and skips intentional dynamic/disabled stops instead of undoing them.
Changing a map mode clears any older demand lease for that map, so an operator
can disable or return it to dynamic mode without a stale travel event
immediately starting it again.
The demand lease remains active while the map loads, clears as soon as the
first player is observed, and otherwise expires at the configured TTL. This
prevents a slow-starting map from reaching its idle deadline before Director
can route the waiting player.

Execution requires the master mutation gate,
`DUNE_ADMIN_AUTOSCALER_MUTATIONS_ENABLED=true`, and `CHANGE AUTOSCALER`.

## Warm-pool profiles

The autoscaler supports the complete range from fully cold to the original
30-map standing farm. Applying a profile reconciles the running farm
immediately and persists it in `backups/admin-panel/autoscaler.json`.

| Profile | Map modes | Retention and eviction | Intended use |
| --- | --- | --- | --- |
| `minimum-footprint` | Configured core maps are `always-on`; all other maps are `dynamic`. | Dynamic maps use `DUNE_AUTOSCALER_IDLE_SECONDS`; no global warm-map or memory budget. | Smallest normal idle footprint. |
| `balanced` | Configured core maps are `always-on`; all other maps are `dynamic`. | Default/per-map retention, LRU warm-map cap, and available-memory floor. | Recommended general-purpose production policy. |
| `adaptive` | Same safe core/dynamic modes as balanced. | Balanced LRU/memory bounds plus evidence-qualified per-map retention from the capacity ledger. | Sites that want the resource/latency middle ground to converge from observed demand. |
| `full-warm` | Every configured map is `always-on`. | Nothing is automatically evicted. | Original all-maps-running behavior and latency-sensitive large hosts. |
| `custom` | Each map keeps its selected `always-on`, `dynamic`, or `disabled` mode. | Operator-selected default/per-map retention and budgets. | Mixed policies and experiments. |

The Infrastructure page exposes profile buttons, per-map modes, per-map
retention, default retention, maximum optional warm maps, minimum available
memory, demand TTL, live heat/activity data, and the latest eviction reason.
The JSON endpoint is `GET/POST /api/ops/autoscaler`; writes require
`CHANGE AUTOSCALER`.

The adjacent Capacity Intelligence card retains map-hours saved, idle warm
cost, warm/cold revisits, request-to-ready latency, and observation coverage.
Its adaptive recommendations are separately confirmed, evidence-thresholded,
gradual, and mode-preserving. See
[`capacity-intelligence.md`](capacity-intelligence.md).

The same card can schedule a map by **ready by** time. It subtracts measured
cold-start p95 plus a bounded safety margin and stores a one-time, daily, or
weekly guarded demand event. This covers predictable play windows without
changing the selected profile or retaining every map continuously. See
[`anticipatory-map-warming.md`](anticipatory-map-warming.md).

### Balanced profile

Fresh installations can configure the balanced defaults entirely through
`.env`:

```env
DUNE_ADMIN_AUTOSCALER_MUTATIONS_ENABLED=true
DUNE_AUTOSCALER_ENABLED=true
DUNE_AUTOSCALER_PROFILE=balanced
DUNE_AUTOSCALER_DEFAULT_MODE=dynamic
DUNE_AUTOSCALER_ALWAYS_ON_SERVICES=survival,overmap
DUNE_AUTOSCALER_DEMAND_TTL_SECONDS=900
DUNE_AUTOSCALER_POLL_SECONDS=3
DUNE_AUTOSCALER_RECONCILE_SECONDS=30
DUNE_AUTOSCALER_FAST_START=true

DUNE_AUTOSCALER_BALANCED_RETENTION_SECONDS=900
DUNE_AUTOSCALER_BALANCED_RETENTION_BY_SERVICE=arrakeen=2700,harko-village=2700,deep-desert=1800
DUNE_AUTOSCALER_BALANCED_MAX_WARM_MAPS=4
DUNE_AUTOSCALER_BALANCED_MIN_AVAILABLE_MEMORY_GIB=16
```

The profile helper edits only these autoscaler keys, creates an `.env` backup,
and is dry-run by default:

```bash
./scripts/configure-autoscaler-profile.sh .env balanced
./scripts/configure-autoscaler-profile.sh .env balanced --execute
```

Replace `balanced` with `minimum-footprint`, `adaptive`, `full-warm`, or `custom`. Recreate
the admin panel after changing defaults, then apply the same profile from
Infrastructure to reconcile persistent runtime state.

This keeps Survival and Overmap live. A used dynamic map remains warm for 15
minutes by default, Arrakeen and Harko Village for 45 minutes, and Deep Desert
for 30 minutes. At most four empty, non-demanded dynamic maps are retained.
When a fifth becomes optional-warm, the least-recently-active map is stopped.
If Linux `MemAvailable` falls below 16 GiB, optional-warm maps are stopped in
the same LRU order until the floor is restored or no eligible map remains.

The memory floor does not reserve RAM. It is an eviction trigger. A stopped
map consumes no game-process CPU/RAM, while an `always-on` map, a map with an
online player, or a map protected by a current demand lease is never selected
for budget or memory-pressure eviction.

### Retention lifecycle and heat

For a successful visit, retention starts after the last player leaves. The
worker records `lastActivityAt`, `idleSince`, `warmUntil`, and `demandCount`
per map. Repeated visits while the map is retained are immediate and refresh
activity. The per-service retention override wins over the default.

For a demand where no player arrives, the demand lease remains in force for
`demandTtlSeconds` before idle retention begins. This intentionally prevents a
slow cold start or delayed transfer from being evicted while Director still
has a waiting request. Setting a map mode clears the old lease.

LRU and memory-pressure eviction considers only maps satisfying all of these:

1. mode is `dynamic`;
2. container is running;
3. player count is zero;
4. no current demand lease exists; and
5. the map has not already reached its own retention expiry.

An unavailable `/proc/meminfo` signal fails open for memory pressure: the
worker records a warning and does not evict maps based on an unknown value.
Individual retention expiry and the configured warm-map cap continue working.

### Minimum footprint and full warm

Minimum footprint is the previous two-core-map policy:

```env
DUNE_AUTOSCALER_PROFILE=minimum-footprint
DUNE_AUTOSCALER_IDLE_SECONDS=300
DUNE_AUTOSCALER_ALWAYS_ON_SERVICES=survival,overmap
```

Full warm deliberately returns to the original standing farm:

```env
DUNE_AUTOSCALER_PROFILE=full-warm
```

Applying full warm can take many minutes because every stopped map must cold
start. The request timeout is sized for that operation. Switching back to a
selective profile never stops maps containing players; those maps remain live
until empty and are reconciled by later ticks.

### Reboot and migration behavior

`scripts/start-full-warm-pool.sh` reads the persisted autoscaler state when it
exists. For minimum, balanced, and selective custom policies it starts only
the persisted `always-on` maps after seeding all world partitions. For full
warm it starts the whole farm. When no state exists, it falls back to `.env`.

Older state files containing only `idleSeconds`, modes, and demand markers are
migrated in memory: `idleSeconds` becomes `retentionSeconds`, new maps receive
valid default modes, and new heat/budget dictionaries start empty. The next
successful reconciliation writes the expanded schema atomically.

Runtime changes made in the browser persist in the state file. Change `.env`
as well when the same policy must be the installation default after deleting
state or moving the deployment to another host.

Use `adaptive` to start from balanced bounds and enable the retained model:

```bash
./scripts/configure-autoscaler-profile.sh .env adaptive
./scripts/configure-autoscaler-profile.sh .env adaptive --execute
```

Profile changes use the shared locked, inode-preserving `.env` writer. They are
immediately visible to the running Admin container and survive its next
recreation. See [configuration-durability.md](configuration-durability.md).

### Persistent state fields

| Field | Meaning |
| --- | --- |
| `enabled`, `profile` | Worker state and selected policy. |
| `modes` | Per-service `always-on`, `dynamic`, or `disabled` selection. |
| `retentionSeconds` | Default zero-player warm retention. `idleSeconds` is retained as a compatibility alias. |
| `retentionByService` | Per-map retention overrides. |
| `maxWarmDynamicMaps` | LRU cap for empty/non-demanded dynamic maps; zero disables this cap. |
| `minAvailableMemoryBytes` | Linux `MemAvailable` eviction floor; zero disables memory-pressure eviction. |
| `demandTtlSeconds`, `demand`, `demandEvents` | Demand protection, active leases, and 24-hour Director-log deduplication. |
| `idleSince`, `lastActivity` | Retention start and LRU ordering timestamps. |
| `demandCount` | Persistent per-map demand counter used as heat evidence. |
| `lastEvictionReason` | Latest `retention-expired`, `warm-budget-lru`, `memory-pressure-lru`, or operator-disabled reason. |

All timestamps are Unix seconds. The state writer uses the same atomic JSON
replacement helper as other admin-panel state. Do not hand-edit it while the
worker is enabled; use the Infrastructure controls or API so updates share the
autoscaler lock.

### Configuration reference

| Variable | Default | Purpose |
| --- | ---: | --- |
| `DUNE_AUTOSCALER_ENABLED` | `false` | Start the worker and allow profile reconciliation. |
| `DUNE_AUTOSCALER_PROFILE` | `balanced` | Fresh-state installation profile: minimum-footprint, balanced, adaptive, full-warm, or custom. |
| `DUNE_AUTOSCALER_ALWAYS_ON_SERVICES` | `survival,overmap` | Core maps for minimum and balanced profiles. |
| `DUNE_AUTOSCALER_IDLE_SECONDS` | `300` | Minimum-profile retention and legacy fallback. |
| `DUNE_AUTOSCALER_DEMAND_TTL_SECONDS` | `900` | Maximum protection for a demand with no observed player. |
| `DUNE_AUTOSCALER_POLL_SECONDS` | `3` | Incremental Director-demand scan cadence, bounded to 1–60. |
| `DUNE_AUTOSCALER_RECONCILE_SECONDS` | `30` | Full Docker/player/lifecycle cadence, bounded to at least the demand cadence and at most 300 seconds. New demand reconciles immediately. |
| `DUNE_AUTOSCALER_FAST_START` | `true` | Use guarded config-aware dynamic starts. |
| `DUNE_AUTOSCALER_BALANCED_RETENTION_SECONDS` | `900` | Balanced default retention. |
| `DUNE_AUTOSCALER_BALANCED_RETENTION_BY_SERVICE` | Arrakeen/Harko `2700`, Deep Desert `1800` | Comma-separated `service=seconds` overrides. Unknown services and invalid values are ignored. |
| `DUNE_AUTOSCALER_BALANCED_MAX_WARM_MAPS` | `4` | Optional-warm LRU cap; zero means unlimited. |
| `DUNE_AUTOSCALER_BALANCED_MIN_AVAILABLE_MEMORY_GIB` | `16` | Available-memory floor; zero disables pressure eviction. |

The admin container must be recreated after changing these `.env` defaults.
Applying a profile afterward copies the loaded defaults into persistent state.
Changing only `.env` does not overwrite an existing state file automatically.
Adaptive application changes only the persistent per-service retention map; it
does not rewrite `.env`, map modes, warm-map caps, or the memory floor.

`adaptive` is a first-class process-start default. Fresh state, deleted state,
and migrated installations no longer normalize an adaptive `.env` selection
back to balanced.

This lifecycle controller is what reduces CPU and resident memory. Docker
memory limits do not reserve memory and lowering a limit does not make a game
process intrinsically use less RAM. The memory balancer below is therefore a
bounded protection mechanism, not a substitute for stopping unused maps.

### Measured production startup

On `kspls0` on 2026-07-15, a stopped Arrakeen container started at
22:36:57 UTC, the map reported its local farm ready at 22:37:51, and Director
received the first `ready=true` state at 22:37:55. That is about 58 seconds from
container start to routable registration. Later 15-second state reports at
22:38:10 through 22:39:10 were periodic updates, not initial registration;
using the last line originally overstated cold start as 2 minutes 13 seconds.

Cold game-process initialization is therefore the dominant floor for this
small map. The 3-second demand poll removes up to 12 seconds from detection
versus the original worker, while the fast guarded start removes repeated
global orchestration before container start. Keep the 15-minute demand lease
until Deep Desert and real player travel have measured distributions.

After deploying the fast path, a second production run under substantial host
load measured 5.012 seconds from explicit demand to container start, 79.076
seconds from container start to local ready, 4.122 seconds from local ready to
Director ready, and 88.211 seconds end to end. Raising only the starting
container's CPU scheduling weight to 4096 produced 94.378 seconds and was
rejected/restored; it did not improve this workload. The observed small-map
cold range is therefore roughly 1–1.5 minutes. Warm visits are immediate while
the selected profile's default or per-map retention remains active.

## Automatic memory balancer

State is stored in `backups/admin-panel/memory-balancer.json`. Enabling the
balancer captures each running map container's live baseline limit. Every 10
seconds it:

1. finds the most pressured map at or above 90 percent;
2. selects a donor at or below 70 percent that remains at or below 80 percent
   after donation and retains at least 1 GiB/25 percent headroom;
3. adds 1 GiB to the target through Docker's container-update API;
4. removes 1 GiB from the donor;
5. restores the target if the donor update fails.

Each observation requests live Docker stats only for currently running game
maps. Stopped maps and control-plane, database, broker, monitoring, and web
containers are excluded before the bounded stats fan-out begins. Memory
protection therefore stays active without surveying every Compose container
on every balance tick.

Disabling restores all still-running captured baselines. Manual set/unset
operations update the captured baseline while balancing is enabled. Live
limits use equal memory, swap, and reservation values and accept byte units
from MiB through TiB.

Execution requires the master mutation gate and
`DUNE_ADMIN_MEMORY_MUTATIONS_ENABLED=true`. Balancer/tick operations use
`CHANGE MEMORY BALANCER`; individual map limits use `SET MAP MEMORY`.
