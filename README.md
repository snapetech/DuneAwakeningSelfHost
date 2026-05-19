# DuneAwakeningSelfHost (DASH)

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
- `rmq-auth-shim` is a local compatibility workaround for game-server S2S RabbitMQ users; the game RabbitMQ AMQPS port must be client-reachable for live self-host joins

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

## Documentation

Start with these:

- [`docs/setup.md`](docs/setup.md): step-by-step local startup flow.
- [`docs/operations.md`](docs/operations.md): health checks, recovery, backup, restore, ports, and upgrades.
- [`docs/admin-panel.md`](docs/admin-panel.md): local admin helper panel setup, security notes, and write-safety gates.
- [`docs/full-farm.md`](docs/full-farm.md): expanded standing farm and 30-partition warm-pool runbook.
- [`docs/troubleshooting.md`](docs/troubleshooting.md): common startup failures and where to look.

Planning and architecture:

- [`docs/architecture.md`](docs/architecture.md): Compose service map, partition layout, local state, and validation boundary.
- [`docs/reproducibility.md`](docs/reproducibility.md): fresh-host, migration, validation, and version-drift checklist.
- [`docs/kubernetes.md`](docs/kubernetes.md): unsupported design map for translating the Compose pod set to Kubernetes.
- [`docs/improvements.md`](docs/improvements.md): improvement roadmap with the reason behind each workstream.
- [`docs/optimization-targets.md`](docs/optimization-targets.md): practical memory, storage, network, and routing optimization targets.
- [`docs/publication.md`](docs/publication.md): what is safe to publish and what must stay local.
- [`docs/teardown.md`](docs/teardown.md): notes extracted from the Steam install and image metadata.

Networking, routing, and validation:

- [`docs/lan-reflection.md`](docs/lan-reflection.md): LAN reflection options for joining the public-advertised server from inside the same LAN.
- [`docs/network-investigation.md`](docs/network-investigation.md): DB/RabbitMQ/socket-level routing investigation notes.
- [`docs/routing-investigation.md`](docs/routing-investigation.md): Deep Desert, Arrakeen, and Testing Station transition investigation notes.
- [`docs/validation.md`](docs/validation.md): live-client route validation checklist and failed-transition capture flow.
- [`docs/benchmarking.md`](docs/benchmarking.md): repeatable resource and transition benchmark notes.

Admin, access, and gameplay knobs:

- [`docs/access-control.md`](docs/access-control.md): server login password and current restriction limits.
- [`docs/character-transfers.md`](docs/character-transfers.md): Director inbound/outbound character-transfer policy.
- [`docs/admin-mutation-map.md`](docs/admin-mutation-map.md): database contracts used or deliberately avoided by admin mutations.
- [`docs/server-knobs-audit.md`](docs/server-knobs-audit.md): audited Funcom, Compose, and reverse-proxy settings worth exposing in admin.
- [`docs/documentation-audit.md`](docs/documentation-audit.md): docs coverage gaps and audit checklist.

Research indexes at the repo root:

- [`SERVER_CONFIG_KEYS.md`](SERVER_CONFIG_KEYS.md): known local `UserGame.ini` override keys and evidence level.
- [`SERVER_CONFIG_KEY_INDEX.md`](SERVER_CONFIG_KEY_INDEX.md): generated shipped `DefaultGame.ini` key inventory.
- [`SERVER_BINARY_CONFIG_CANDIDATES.md`](SERVER_BINARY_CONFIG_CANDIDATES.md): binary-only candidate config strings for focused validation.
- [`DEEP_DESERT_EVENT_KNOBS.md`](DEEP_DESERT_EVENT_KNOBS.md): Deep Desert spice/event tuning research.
- [`RESOURCE_RESPAWN_KNOBS.md`](RESOURCE_RESPAWN_KNOBS.md): ore, scrap, fuel, resource-node, and loot respawn timer research.
- [`HYDRATION_WATER_KNOBS.md`](HYDRATION_WATER_KNOBS.md): dehydration, shelter, thirst-in-base, and base water generation/evaporation research.

## Key Files

- [`compose.yaml`](compose.yaml): base container topology.
- [`compose.allmaps.yaml`](compose.allmaps.yaml): 30-partition warm-pool extension.
- [`compose.limits.example.yaml`](compose.limits.example.yaml): optional local memory guardrails for profiling and small-host testing.
- [`admin/admin_panel.py`](admin/admin_panel.py): local admin helper web panel.
- [`.env.example`](.env.example): required world/token/password settings.
- [`Makefile`](Makefile): validation targets.
- [`scripts/`](scripts): helper scripts for image loading, preflight, DB bootstrap, backups, status, recovery, profiling, and routing capture.

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
./scripts/status.sh .env
```

Pass a custom env file when needed:

```bash
./scripts/status.sh .env.production
```

The `survival` service is the minimal direct game-server launch target:

```bash
docker compose --env-file .env up -d survival
```

For a single-server test world, prune the unused generated `Survival_1` dimensions after DB bootstrap:

```bash
./scripts/single-survival-partition.sh .env
```

The script writes a `backups/partition-surgery/world-partitions-before-single-survival-*.sql` backup before deleting only unassigned `Survival_1` dimensions greater than zero. This removes recurring Director warnings for dimensions that are not being launched.

Do not expect full gameplay until `FLS_SECRET` is set. The gateway/director/text-router path depends on that token for FLS registration; if the account page redirects to `/buy`, Funcom's entitlement service is not seeing the Steam ownership for the logged-in account.

For the expanded standing farm and 30-partition warm pool, see `docs/full-farm.md`. The known-good nine-map server-side target is:

```text
current_alive_active=9 active_servers=9 partitions=9
```

The known-good warm-pool target with `compose.allmaps.yaml` is:

```text
current_alive_active=30 active_servers=30 partitions=30
```

That means server registration is green. Client travel still needs validation from the live game client.

Start the local admin helper panel:

```bash
docker compose --env-file .env up -d admin-panel
```

It binds to `127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}` by default and is intended to sit behind trusted LAN/VPN ingress. If another local process owns `18080`, set `DUNE_ADMIN_HOST_PORT=18081` and include that host in `DUNE_ADMIN_ALLOWED_HOSTS`. If you want a LAN hostname such as `admin.example.test`, point your own DNS or reverse proxy at the host. Do not expose this panel directly to the public internet.

Open the panel at:

```text
http://127.0.0.1:18080/
```

The header token box uses `DUNE_ADMIN_TOKEN` from `.env`. After you click **Use token**, the browser stores it in session storage and sends protected API requests with `X-Admin-Token`. Keep the token private; it gates sensitive reads and all mutation endpoints.

The panel is the operator-facing Web UI for this repo:

| Tab | Use it for |
| --- | --- |
| **Overview** | Operator dashboard with online/offline players, realtime host/container resource use, headline health metrics, map health, network checks, and health verdicts. |
| **Ops** | Detailed resource use, map/network health, farm state, partition state, restart planning, and restart announcement helpers. |
| **Security** | Host/origin checks, mutation-gate status, token status, audit events, and editable-setting allowlists. |
| **Runbook** | Copy/paste operational commands for health, backups, restores, profiling, logs, and routing capture. |
| **Players** | Search/list existing players and inspect controller, account, currency, inventory, and progression state before changing anything. |
| **Settings** | Edit `.env`, `config/director.ini`, `config/UserGame.ini`, and selected config overlays with backups under `backups/admin-panel`. Runtime-only settings may apply immediately, but many game-server values require recreating or restarting affected containers. |
| **Admin Actions** | Create DB backups and perform guarded writes such as XP, currency, keystones, item grants, item stack edits, and item deletion. Back up the database before broad writes; item and inventory operations are guarded by the admin token and mutation safety flags. |

Typical admin flow:

1. Open **Overview** and confirm the Map Health list is sane.
2. Use **Players** to select the player instead of typing IDs by hand.
3. Use **Admin Actions** for dry-runs and guarded writes.
4. Check **Security** after failed auth, blocked host/origin requests, config edits, backups, or mutation runs.
5. Restart or recreate affected containers after settings that are loaded only at process startup.

Current headless captures of the Map Health list screen are saved locally under:

- `captures/admin-panel-webui/map-health-overview-desktop.png`
- `captures/admin-panel-webui/map-health-overview-mobile-tall.png`

For the single `Survival_1` test layout, forward:

- `7777/udp`

For the expanded standing full-farm layout, forward these game UDP ports:

- `7777-7785/udp`

For the full 30-partition warm pool, forward these game UDP ports:

- `7777-7806/udp`

The Compose files also expose the current IGW/S2S UDP ports on the host for debugging (`7888-7917/udp` in the 30-partition layout), but those are server-to-server paths on the Docker network. Do not forward them publicly unless a client test proves Funcom's routing requires it.

Forward the game RabbitMQ AMQPS port (`GAME_RMQ_PUBLIC_PORT`, default `31982/tcp`) when using live self-host joins; the client receives this address from FLS before gameplay UDP starts. Do not forward Postgres, RabbitMQ management, admin panel, or other local debug ports.

If LAN players join through the public server listing, keep `EXTERNAL_ADDRESS`
set to the public address and use the standard LAN reflection options in
`docs/lan-reflection.md`. Do not flip `EXTERNAL_ADDRESS` between public and LAN
addresses for normal operation.

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

For a fresh install on different hardware, use `docs/reproducibility.md`. For a future move back into a normal Kubernetes cluster, use `docs/kubernetes.md` as the service mapping and gap list.
