# Improvement Plan

This project should improve the self-hosting path before trying to optimize the game server binaries. The useful first target is a reproducible, measurable Linux runtime that makes failures obvious.

## 1. Clean Compose/Podman/systemd Runtime

Why: the official package is oriented around a Hyper-V Linux VM and Kubernetes-style battlegroup operator flow. That hides service boundaries, makes local debugging harder, and adds operational weight that is not required for a single self-hosted battlegroup.

Current work:

- `compose.yaml` defines the extracted service topology directly.
- `compose.allmaps.yaml` provides a 30-partition warm-pool overlay for the official single-dimension self-host partitions.
- The host-facing ports are intentionally narrow: gameplay UDP is public, while Postgres and RabbitMQ debug/admin ports bind to `127.0.0.1`.
- `scripts/preflight.sh` and `make validate` guard common local mistakes before startup.

Next steps:

- Verify Podman Compose compatibility.
- Decide whether native systemd units are useful after Compose reaches parity.
- Keep the Compose file as the reference topology even if systemd wrappers are added.

## 2. Instrument Actual Resource Cost

Why: self-host operators need hard numbers for CPU, memory, restarts, ports, logs, database load, RabbitMQ load, and player/map symptoms. Abstract control panels can hide the source of cost and make capacity planning guesswork.

Current work:

- `scripts/status.sh` now reports container state, Docker CPU and memory snapshots, restart counts, OOM state, selected DB rows, RabbitMQ connections, and filtered logs.
- The admin panel overview surfaces per-map online/offline state and local/upstream network probes.
- `docs/benchmarking.md` defines a repeatable capture format for resource and routing comparisons.
- `docs/optimization-targets.md` records current memory, storage, network, and routing optimization targets.
- `scripts/profile-runtime.sh` captures process, image, filesystem, socket, and resource profiles under ignored `captures/`.

Next steps:

- Add optional Prometheus scrape targets for container, Postgres, and RabbitMQ metrics.
- Compare the admin-panel and script player-count probes against real client presence.
- Capture repeatable benchmark notes per map count and player count.

## 3. Remove Windows/Hyper-V Overhead

Why: a normal Linux container runtime should avoid the extra VM layer, reduce host requirements, simplify backups, and make system resource usage easier to attribute.

Current work:

- The repository assumes Linux plus Docker Compose.
- The Steam package path and Funcom image tarballs remain local and uncommitted.

Next steps:

- Test on a clean Linux host from only the documented setup steps.
- Record minimum host kernel/runtime assumptions.
- Compare Docker and Podman behavior before recommending one default.

## 4. Make Dependencies Reproducible

Why: Postgres and RabbitMQ are legitimate service dependencies, but they should be explicit, initialized predictably, health-checked, backed up, and upgraded deliberately.

Current work:

- Postgres, admin RabbitMQ, and game RabbitMQ are named services with persistent local volumes.
- `scripts/bootstrap_db.py` runs Funcom's bundled setup flow inside the DB utility image.
- TLS and generated secrets are separated from publishable repository content.
- `compose.yaml` health-checks Postgres and both RabbitMQ services.
- `docs/operations.md` documents backup, restore, and image-tag upgrade flow.
- `scripts/backup-state.sh` writes timestamped local backups for Postgres, RabbitMQ, and server saved state.
- `scripts/restore-state.sh` restores Postgres backups and can optionally replace RabbitMQ and server saved state.

Next steps:

- Identify reliable health probes for director, gateway, and text-router.
- Test backup and restore on a disposable world.
- Convert the upgrade checklist into a scripted dry-run once the image/schema behavior is better understood.

## 5. Fix Observability and Player Tracking

Why: if total CPU/RAM and player state are not visible accurately, operators cannot distinguish a routing failure from a capacity problem. Better local observability is also the safest way to find real bottlenecks later.

Current work:

- `scripts/status.sh` prints high-signal DB state from `farm_state`, `active_server_ids`, and `world_partition`.
- Logs are filtered for registration, auth, RabbitMQ, partition, readiness, heartbeat, and failure signals.
- `scripts/capture-routing.sh` writes local redacted captures for transition attempts.
- `scripts/discover-player-state.sh` lists candidate player/session/account schema objects.
- The admin panel exposes map health derived from `world_partition`, `farm_state`, and `active_server_ids`.

Next steps:

- Compare the current player-count SQL probes against real client presence.
- Promote only confirmed player/session fields into dashboard/exporter output.
- Export status data in a machine-readable format for dashboards.

## 6. Map Broken Instance Routing

Why: unreachable Deep Desert, Arrakeen, or Testing Station instances are more likely to be director/FLS/world-routing registration problems than raw performance problems. Routing parity is the highest-value reverse-engineering target after the base services are observable.

Public docs support treating this as incomplete self-host plumbing, not missing content. Funcom's private-server model describes the rented/private server as one Hagga Basin inside a larger World, while social hubs and the Deep Desert are supplied by the hosting provider for that World. CubeCoders' current self-host guide lists Deep Desert, Arrakeen, and Testing Stations as not reachable, and separately notes that the FLS world name is not produced correctly. Taken together, the likely failure class is world identity, instance registration, discovery, token handoff, or routing.

Current work:

- `docs/architecture.md` records the known service map and validation boundary.
- The direct game-server launch path is sufficient for server-side registration in the base farm and 30-partition warm pool.
- `docs/routing-investigation.md` defines the evidence to collect for broken instance transitions.
- `docs/validation.md` lists the live-client route checks that still need proof.

Next steps:

- Capture the transition path from Hagga Basin into Deep Desert, Arrakeen, and Testing Stations.
- Trace director, FLS, gateway, text-router, and game-server logs during each transition attempt.
- Capture generated world name, world unique name, FLS battlegroup identity, instance registration, auth/token handoff, advertised address, and port routing.
- Compare against operator-generated launch arguments for every map type if a client route fails despite server-side readiness.
- Compare registered partitions, farm state, advertised addresses, and RabbitMQ users across working and broken maps.
- Document each failure mode in `docs/troubleshooting.md` with the exact status output that identifies it.

Working hypothesis:

- Hagga Basin works because it is the primary hosted shard.
- Deep Desert likely requires director/FLS to register and route into a separate instanced map service.
- Arrakeen and Testing Stations likely use the same class of cross-server transition plumbing.
- Prior live-game patch notes mention fixes for cross-server travel, Deep Desert crashes, and travel between Arrakeen/Harko Village and the overland map, so cross-server movement is a known fragile surface in the game stack.

Useful references:

- Funcom private-server model: https://funcom.helpshift.com/hc/en/4-dune-awakening/faq/59-private-servers/
- CubeCoders self-host known issues: https://discourse.cubecoders.com/t/dune-awakening-server-guide/40200
- Funcom patch notes showing prior cross-server travel fixes: https://duneawakening.com/news/dune-awakening-1-1-10-0-patch-notes/
