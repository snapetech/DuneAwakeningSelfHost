# Dune Awakening Linux Host

Work-in-progress Linux/Compose harness for the Steam-installed Dune: Awakening self-hosted server package.

The goal is a reproducible Linux host layout that starts from Funcom's current container images but avoids the Hyper-V/k3s/operator wrapper where possible. This repository does not contain, mirror, or license any Funcom server binaries, container images, Steam package files, game assets, or secrets.

As of 2026-05-19, Steam exposes `Dune: Awakening Self-Hosted Server` as a released live tool, not only a PTC-only server package. Funcom's current live self-hosting FAQ still points token generation at `https://account-pts.duneawakening.com/`, but the proper live token generator is in the Dune: Awakening account portal at `https://account.duneawakening.com/`.

## Current State

- Steam package found at `$HOME/.local/share/Steam/steamapps/common/Dune Awakening Self-Hosted Server`
- Battlegroup image version: `1963158-0-shipping`
- Operator version in the package: `v1.5.0`
- Host has AVX2 and enough CPU for the server image
- Docker is installed and the Funcom images have been loaded locally
- Postgres, both RabbitMQ instances, gateway, and text-router start under Compose; FLS registration still needs a valid self-host token
- `Survival_1` reaches farm-ready with public address advertisement when `FLS_SECRET` and `EXTERNAL_ADDRESS` are set
- `rmq-auth-shim` is a local compatibility workaround for game-server S2S RabbitMQ users; keep RabbitMQ ports internal only

Adjust the path and image tag in `.env` for your install. The values above document the package version used during this teardown.

## Runtime Shape

The official package creates a Kubernetes `BattleGroup` custom resource. The useful workload pieces are:

- `igw-postgres`
- `server-rabbitmq` twice: admin queue and game queue
- `server-bg-director`
- `server-gateway`
- `server-text-router`
- `server` game map instances, with `Survival_1` and `Overmap` enabled by default
- `server-db-utils` for dump/import/DB operations

The first target here is Docker Compose parity for those pieces. After that, systemd units can wrap either Docker/Podman containers or native extracted binaries if that proves viable.

## Files

- `compose.yaml`: first-pass container topology.
- `compose.limits.example.yaml`: optional local memory guardrails for profiling and small-host testing.
- `admin/admin_panel.py`: local admin helper web panel.
- `.env.example`: required world/token/password settings.
- `docs/teardown.md`: notes extracted from the Steam install and image metadata.
- `docs/publication.md`: what is safe to publish and what must stay local.
- `docs/setup.md`: step-by-step local startup flow.
- `docs/architecture.md`: Compose service map and runtime state notes.
- `docs/full-farm.md`: expanded standing farm / 30-partition warm-pool runbook and validation boundary.
- `docs/benchmarking.md`: repeatable resource and transition benchmark notes.
- `docs/improvements.md`: improvement roadmap with the reason behind each workstream.
- `docs/network-investigation.md`: connection-level DB/RabbitMQ/routing investigation notes.
- `docs/optimization-targets.md`: practical memory, storage, network, and routing optimization targets.
- `docs/operations.md`: health-check, backup, restore, and upgrade notes.
- `docs/routing-investigation.md`: Deep Desert, Arrakeen, and Testing Station transition investigation notes.
- `docs/troubleshooting.md`: common startup failures and where to look.
- `scripts/load-images.sh`: loads the Steam image tarballs into Docker.
- `scripts/inspect-images.sh`: prints entrypoints, env, ports, and volumes from the loaded images.
- `scripts/bootstrap_db.py`: one-shot Compose DB bootstrap using Funcom's bundled SQL setup API.
- `scripts/backup-state.sh`: writes a timestamped local backup under `backups/`.
- `scripts/populate-local-env.sh`: generates local passwords/RabbitMQ secret and RabbitMQ TLS files.
- `scripts/preflight.sh`: checks local tools, env values, Steam image tarballs, and unsafe bindings.
- `scripts/capture-routing.sh`: writes local redacted transition/debug captures under `captures/`.
- `scripts/discover-player-state.sh`: lists candidate player/session/account DB objects for observability work.
- `scripts/profile-runtime.sh`: captures local memory, storage, image, process, port, and socket profiles under `captures/`.
- `scripts/summarize-runtime-profile.sh`: prints a compact summary from a runtime profile capture.
- `scripts/watch-network.sh`: prints current socket-state counts for routing/DB/RabbitMQ churn.
- `scripts/recover-survival.sh`: restarts the game-server process after dependency restarts or a database disconnect crash.
- `scripts/full-world-partitions.sh`: adds the official single-dimension travel target partitions for Overmap, social hubs, testing stations, Deep Desert, and Proces Verbal.
- `scripts/rmq_auth_shim.py`: local RabbitMQ HTTP auth compatibility shim.
- `scripts/restore-state.sh`: restores a local backup made by `scripts/backup-state.sh`.
- `scripts/run_server_safe.sh`: local game-server launcher that preserves arguments containing spaces.
- `scripts/single-survival-partition.sh`: backs up and prunes unused `Survival_1` dimensions for a one-server test world.
- `scripts/status.sh`: redacted status/log inspection helper.

## Requirements

- Linux host with Docker Compose.
- Official Dune: Awakening Self-Hosted Server Steam tool installed locally.
- A valid self-hosting/FLS token from Funcom's account flow.
- `openssl`, `jq`, and `rg` for the helper scripts.

## Quick Start

Generate local secrets, fill in the self-hosting token in `.env`, load the official images, then bootstrap the DB:

```bash
./scripts/populate-local-env.sh
./scripts/preflight.sh
./scripts/load-images.sh
docker compose --env-file .env up -d postgres admin-rmq game-rmq
docker compose --env-file .env run --rm db-init
```

Then bring up the service layer:

```bash
docker compose --env-file .env up -d rmq-auth-shim text-router gateway director
./scripts/status.sh
```

Pass a custom env file when needed:

```bash
./scripts/status.sh .env.production
```

The `survival` service is present as an experimental direct game-server launch target:

```bash
docker compose --env-file .env up -d survival
```

For a single-server test world, prune the unused generated `Survival_1` dimensions after DB bootstrap:

```bash
./scripts/single-survival-partition.sh
```

The script writes a `backups/partition-surgery/world-partitions-before-single-survival-*.sql` backup before deleting only unassigned `Survival_1` dimensions greater than zero. This removes recurring Director warnings for dimensions that are not being launched.

Do not expect full gameplay until `FLS_SECRET` is set. The gateway/director/text-router path depends on that token for FLS registration; if the account page redirects to `/buy`, Funcom's entitlement service is not seeing the Steam ownership for the logged-in account.

For the expanded standing farm and 30-partition warm pool, see `docs/full-farm.md`. The known-good nine-map server-side target is:

```text
farm_ready_alive=9 active_servers=9 partitions=9
```

The known-good warm-pool target with `compose.allmaps.yaml` is:

```text
farm_ready_alive=30 active_servers=30 partitions=30
```

That means server registration is green. Client travel still needs validation from the live game client.

Start the local admin helper panel:

```bash
docker compose --env-file .env up -d admin-panel
```

It binds to `127.0.0.1:18080` by default. Put a trusted local reverse proxy or LAN DNS entry in front of it if you want `http://duneadmin.home`.

For the single `Survival_1` test layout, forward:

- `7777/udp`

For the expanded standing full-farm layout, forward these game UDP ports:

- `7777-7785/udp`

For the full 30-partition warm pool, forward these game UDP ports:

- `7777-7806/udp`

The Compose files also expose the current IGW/S2S UDP ports on the host for debugging (`7888-7917/udp` in the 30-partition layout), but those are server-to-server paths on the Docker network. Do not forward them publicly unless a client test proves Funcom's routing requires it.

Do not forward RabbitMQ (`31982/tcp`) or the local debug/admin ports. Compose binds RabbitMQ and database debug ports to `127.0.0.1` where host publication is needed.

## Repository Boundaries

This repo is intended to contain only original orchestration, documentation, and local helper scripts. Keep these local and uncommitted:

- `.env`
- `data/`
- `config/tls/`
- Steam package contents
- backups and routing captures
- Funcom container image tarballs
- logs, dumps, and generated runtime state

See `docs/publication.md` for the public-release checklist.

## Validation

Run the local validation target before pushing:

```bash
make validate
```

This checks the Compose config against `.env.example` and scans publishable files for obvious secret patterns.
