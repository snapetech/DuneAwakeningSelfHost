# DuneAwakeningSelfHost (DASH)

DASH is a Linux/Docker Compose operations harness for the official Steam-installed **Dune: Awakening Self-Hosted Server** package.

It turns Funcom's self-host stack into a reproducible local layout with Compose services, startup and recovery scripts, a LAN/VPN admin panel, backup tooling, optional Postgres replication, warm-pool map startup, restart automation, player/admin utilities, and a public static site package that does not expose private control surfaces.

This repository does **not** contain, mirror, or license Funcom server binaries, container images, Steam package files, game assets, live server data, or secrets.

Documented baseline: image lineage `1963158-0-shipping`. Treat that as the tested baseline for this repo, not as a permanent version requirement. Always compare your `.env` image pin with the Steam package installed on your host.

## Contents

- [Screenshots](#screenshots)
- [Choose Your Path](#choose-your-path)
- [What DASH Includes](#what-dash-includes)
- [What DASH Does Not Include](#what-dash-does-not-include)
- [Security Posture](#security-posture)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Install And Deployment Paths](#install-and-deployment-paths)
- [Admin Panel](#admin-panel)
- [Operations And Recovery](#operations-and-recovery)
- [Backups, Replication, And Restore](#backups-replication-and-restore)
- [Networking And Ports](#networking-and-ports)
- [Automation And Host Services](#automation-and-host-services)
- [Public Static Site](#public-static-site)
- [Artificial Exchange](#artificial-exchange)
- [Configuration Map](#configuration-map)
- [Validation Before Publishing](#validation-before-publishing)
- [Full Manual](#full-manual)
- [Key Files](#key-files)

## Screenshots

### Overview

![DASH Admin overview showing 30/30 maps and Hagga Basin player positions](docs/assets/admin-overview.png)

### Operations

![DASH Admin operations page showing health, resources, and map status](docs/assets/admin-ops.png)

## Choose Your Path

| Goal | Start here | Public exposure |
| --- | --- | --- |
| Single-map validation | Prove Steam package, token, database bootstrap, Gateway, RabbitMQ, and `Survival_1`. | `7777/udp` plus `31982/tcp` for live-client login. |
| Public self-host | Run the nine-map standing farm or the 30-partition warm pool after single-map validation passes. | Game UDP range for your layout plus `31982/tcp`. |
| Full warm-pool operator setup | Run all 30 official self-host partitions, watchdog recovery, restart planning, backups, and optional replica/sync. | `7777-7806/udp`, optional observed IGW `7888-7917/udp`, plus `31982/tcp`. |
| Public-status-only website | Render static status, settings, players, and Hagga Basin map files from the private DASH host. | Only your normal static web server ports. |

## What DASH Includes

- Compose topology for Postgres, admin RabbitMQ, game RabbitMQ, auth shim, text router, Gateway, Director, map services, and the admin panel.
- Minimal single-map startup for `Survival_1`.
- Expanded nine-map standing farm matching the current travel targets used by the Compose layout.
- Full 30-partition warm pool through `compose.allmaps.yaml` and `scripts/start-full-warm-pool.sh`.
- Recovery helpers for dependency loss and stale fixed-partition server IDs.
- Host-level map watchdog service for unattended recovery.
- LAN/VPN admin panel with Overview, Ops, Security, Runbook, Players, Settings, Admin Actions, and Catalog surfaces.
- Guarded admin writes for backups, currency, XP, keystones, item grants, stack edits, item deletion, and catalog dry-runs.
- Restart announcements, restart planner hooks, chat-command bridge, player-presence announcer, and admin-bot monitoring.
- Local backups, restore helpers, optional streaming Postgres replica, optional remote replica snapshots, and portable offsite/onsite backup sync examples.
- Optional public static site package with status, settings, player list, and Hagga Basin map.
- Artificial Exchange catalog, buyer, settlement, populator, smoke tests, and optional systemd services.
- Publication and validation guardrails for keeping local state and secrets out of shared artifacts.

## What DASH Does Not Include

- Funcom server binaries, container images, Steam package files, or game assets.
- A Funcom self-hosting/FLS token.
- Production hosting, DDoS protection, router/firewall configuration, or account portal access.
- Point-in-time recovery by replication alone. Replicas mirror bad writes and deletes too.
- Verified native GM/cheat command execution. Those paths remain research-gated unless the payload route is explicitly verified.
- Public exposure for Postgres, RabbitMQ management, the admin panel, debug ports, or private automation endpoints.

## Security Posture

Keep these local and uncommitted:

- `.env`
- `data/`
- `backups/`
- `captures/`
- `config/tls/`
- Steam package contents and Funcom image tarballs
- TLS material, logs, dumps, routing traces, database exports, tokens, passwords, public IPs, real hostnames, and private admin/community details

The admin panel is intended for trusted LAN/VPN access only. Do not expose it directly to the public internet. Public exposure should be limited to required gameplay ports, the game RabbitMQ client TCP endpoint, and optionally a separate static website generated from sanitized files.

Admin mutations are gated and audit-logged. Many higher-risk paths are dry-run-first or disabled unless explicit `.env` gates are enabled. GM, cheat, native command, and unverified live-action surfaces stay blocked by default.

Replication is a redundancy layer, not a backup strategy. Keep stopped-world backups and test restores because logical mistakes, destructive admin writes, and compromised credentials can replicate immediately.

Read [`SECURITY.md`](SECURITY.md) and [`docs/publication.md`](docs/publication.md) before sharing the repo or publishing artifacts.

## Requirements

- Linux host with Docker Compose.
- Official **Dune: Awakening Self-Hosted Server** Steam tool installed locally.
- Valid self-hosting/FLS token from Funcom's live account portal: `https://account.duneawakening.com/`.
- CPU with AVX2 support.
- Memory and disk sized for the map count you intend to run.
- `openssl`, `jq`, `rg`, Python 3, and standard shell tooling for helper scripts.

## Quick Start

Generate local settings, edit `.env`, validate the host, load the official Steam package images, and initialize the database:

```bash
./scripts/populate-local-env.sh
$EDITOR .env
./scripts/preflight.sh
./scripts/load-images.sh .env
docker compose --env-file .env up -d postgres admin-rmq game-rmq
docker compose --env-file .env run --rm db-init
```

For a one-server test world, prune unused generated `Survival_1` dimensions after database bootstrap:

```bash
./scripts/single-survival-partition.sh .env
```

Start the service layer:

```bash
docker compose --env-file .env up -d rmq-auth-shim text-router gateway director
./scripts/status.sh .env
```

Start a single test map:

```bash
docker compose --env-file .env up -d survival
./scripts/status.sh .env
```

Start the private admin panel:

```bash
docker compose --env-file .env up -d admin-panel
```

Default local URL:

```text
http://127.0.0.1:18080/
```

More detail: [`docs/setup.md`](docs/setup.md).

## Install And Deployment Paths

### Minimal Single-Map Test

Use this first on a new host. It proves the Steam package, `.env`, database initialization, Gateway/Director service layer, RabbitMQ auth path, and starting map registration.

```bash
./scripts/populate-local-env.sh
./scripts/preflight.sh
./scripts/load-images.sh .env
docker compose --env-file .env up -d postgres admin-rmq game-rmq
docker compose --env-file .env run --rm db-init
./scripts/single-survival-partition.sh .env
docker compose --env-file .env up -d rmq-auth-shim text-router gateway director survival
./scripts/status.sh .env
```

### Expanded Nine-Map Standing Farm

This keeps one container online for each current travel target in the base Compose layout.

```bash
./scripts/full-world-partitions.sh .env

docker compose --env-file .env up -d \
  survival overmap arrakeen harko-village \
  testing-hephaestus testing-carthag testing-waterfat \
  deep-desert proces-verbal

./scripts/status.sh .env
```

Expected server-side readiness:

```text
current_alive_active=9 active_servers=9 partitions=9
```

### Full 30-Partition Warm Pool

Compose cannot provide Kubernetes-style on-demand game-server scaling, so the all-maps overlay keeps one server warm for every official single-dimension self-host partition.

```bash
./scripts/start-full-warm-pool.sh .env
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

Expected server-side readiness:

```text
current_alive_active=30 active_servers=30 partitions=30
```

Live-client login and travel still depend on a valid FLS token, public reachability, router/firewall state, and LAN reflection when joining from inside the same network. See [`docs/full-farm.md`](docs/full-farm.md), [`docs/operations.md`](docs/operations.md), and [`docs/lan-reflection.md`](docs/lan-reflection.md).

### Optional Host Services

Install only after the matching manual command works:

```bash
make install-map-watchdog-service ENV_FILE=.env
make install-full-farm-service ENV_FILE=.env
make install-daily-maintenance-timer ENV_FILE=.env
make install-player-presence-announcer-service ENV_FILE=.env
```

### Optional Postgres Replica

```bash
COMPOSE_FILES=compose.yaml:compose.replica.yaml ./scripts/setup-postgres-replica.sh .env
```

### Optional Backup Sync

```bash
DUNE_BACKUP_REMOTE_ENV=examples/backup/rclone-offsite.env ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/rsync-nas.env ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/restic.env ./scripts/backup-offsite.sh .env
```

### Optional Public Static Site

```bash
make public-site-check
./public-site/scripts/package-dune-public-site.sh /tmp/dash-public-site.tar.gz
```

## Admin Panel

Start:

```bash
docker compose --env-file .env up -d admin-panel
```

Open:

```text
http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/
```

If another process owns `18080`, set `DUNE_ADMIN_HOST_PORT=18081` in `.env`, include that host in `DUNE_ADMIN_ALLOWED_HOSTS`, and recreate only the admin panel.

By default the local deployment is configured for a trusted private admin surface. To require a token, set `DUNE_ADMIN_REQUIRE_TOKEN=true` and `DUNE_ADMIN_TOKEN`; protected requests then send `X-Admin-Token`.

| Page | Purpose |
| --- | --- |
| Overview | Readiness metrics, health summary, Hagga Basin player map, map details, and player preview. |
| Ops | Restart planner, restart announcements, resource telemetry, map health, network checks, farm state, and partition state. |
| Security | Host/origin checks, auth mode, mutation gates, allowlists, and audit events. |
| Runbook | Copy/paste operational commands for health, backups, restores, logs, profiling, and routing capture. |
| Players | Online/offline roster, player detail, account/controller/pawn context, currency, XP, inventory, and location views. |
| Settings | Selected `.env` and config edits with backups. |
| Admin Actions | Database backups and guarded mutations for currency, XP, keystones, grants, stack edits, and deletion. |
| Catalog | Content insertion evidence, typed knob dry-runs, resource inspection, event dry-runs, and economy bundle dry-runs. |

If the published local admin port accepts TCP but returns no HTTP bytes after a container recreate, refresh the observed Docker bridge neighbor entries:

```bash
./scripts/seed-gateway-neighbor.sh
curl -H 'Host: admin-panel:8080' http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/status
```

More detail: [`docs/admin-panel.md`](docs/admin-panel.md), [`docs/admin-safe-content-api.md`](docs/admin-safe-content-api.md), and [`CONTENT_INSERTION_SURFACES.md`](CONTENT_INSERTION_SURFACES.md).

## Operations And Recovery

Common health checks:

```bash
./scripts/status.sh .env
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
./scripts/verify-rmq-auth-path.sh
```

Recover the single survival target after dependency loss:

```bash
./scripts/recover-survival.sh .env
```

Recover a fixed-partition map with stale server ID state:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/recover-map.sh .env heighliner-dungeon 18
```

Run the watchdog interactively:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/watch-maps.sh .env
```

Install it as a host service:

```bash
./scripts/install-map-watchdog-service.sh .env
sudo systemctl enable --now dune-map-watchdog.service
```

Detailed runbooks: [`docs/operations.md`](docs/operations.md), [`docs/maintenance-updates.md`](docs/maintenance-updates.md), and [`docs/troubleshooting.md`](docs/troubleshooting.md).

## Backups, Replication, And Restore

Create a local stopped-world state backup:

```bash
./scripts/backup-state.sh .env
```

Verify a backup structurally:

```bash
./scripts/verify-backup.sh backups/<backup-id>
```

Restore:

```bash
./scripts/restore-state.sh .env backups/<backup-id>
```

Optional local streaming standby:

```bash
COMPOSE_FILES=compose.yaml:compose.replica.yaml ./scripts/setup-postgres-replica.sh .env
```

Optional remote LAN standby and snapshots:

```bash
./scripts/install-postgres-lan-forwarder.sh .env
./scripts/install-remote-postgres-replica.sh .env replica.example.lan /srv/dune-postgres-replica
./scripts/install-replica-snapshot-timer.sh .env replica.example.lan /srv/dune-postgres-replica
./scripts/backup-layers-status.sh .env replica.example.lan /srv/dune-postgres-replica
```

Portable sync examples:

```bash
DUNE_BACKUP_OFFSITE_MODE=none ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/rclone-offsite.env ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/rsync-nas.env ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/restic.env ./scripts/backup-offsite.sh .env
```

Install a timer after the selected path works manually:

```bash
./scripts/install-backup-offsite-timer.sh .env examples/backup/rclone-offsite.env
```

More detail: [`docs/backup-strategy.md`](docs/backup-strategy.md) and [`docs/postgres-replication.md`](docs/postgres-replication.md).

## Networking And Ports

Forward only the client-facing ports needed for your layout.

| Layout | Public game UDP |
| --- | --- |
| Single `Survival_1` | `7777/udp` |
| Nine-map farm | `7777-7785/udp` |
| Full 30-partition warm pool | `7777-7806/udp` |
| Optional/observed full-pool IGW range | `7888-7917/udp` |

Live-client login also receives the game RabbitMQ endpoint from FLS before gameplay UDP starts. Forward the configured game RabbitMQ public TCP port:

```text
GAME_RMQ_PUBLIC_PORT tcp, default 31982/tcp
```

Do not forward Postgres, RabbitMQ management, admin panel, debug ports, local reverse proxies, or systemd automation endpoints.

For LAN players joining through the public listing, keep `EXTERNAL_ADDRESS` set to the public address and use LAN reflection/hairpin routing. Do not switch the advertised address between public and private during normal operation. See [`docs/lan-reflection.md`](docs/lan-reflection.md).

## Automation And Host Services

DASH can install host systemd services and timers for operator workflows. Install these from the target checkout and `.env` so rendered units point at the correct paths.

```bash
make install-map-watchdog-service ENV_FILE=.env
make install-full-farm-service ENV_FILE=.env
make install-daily-maintenance-timer ENV_FILE=.env
make install-player-presence-announcer-service ENV_FILE=.env
make install-artificial-exchange-buyer-service ENV_FILE=.env
make install-artificial-exchange-populator-service ENV_FILE=.env
```

The daily maintenance flow targets a 06:00 local restart with warning announcements, stopped-world backup, optional Steam package update check, service recreate/start, and post-start health checks. See [`docs/maintenance-updates.md`](docs/maintenance-updates.md).

## Public Static Site

The optional public site publishes static files only:

```text
/status.html
/players.json
/hagga-map.svg
/hagga-basin.webp
```

The renderer runs locally on the DASH host. The public web server does not need Docker, Postgres, RabbitMQ, `.env`, admin-token, or admin-panel access.

Linux install path:

```bash
sudo STATIC_DIR=/srv/dash-public-site \
  ENV_FILE=/etc/dune-public-site.env \
  DUNE_PUBLIC_SITE_USER="$USER" \
  ./public-site/scripts/install-dune-public-site.sh
```

Package a shareable static-site bundle:

```bash
make public-site-check
./public-site/scripts/package-dune-public-site.sh /tmp/dash-public-site.tar.gz
```

More detail: [`docs/public-static-site.md`](docs/public-static-site.md).

## Artificial Exchange

The Artificial Exchange tooling manages a local item catalog, buyer flow, settlement checks, optional populator, and service wrappers for operators who want an always-on artificial market helper.

Run the smoke check before enabling live purchase, funding, auto-claim, or populator apply gates:

```bash
make artificial-exchange-smoke
```

Install services after `.env` gates and owner/source IDs are configured:

```bash
make install-artificial-exchange-buyer-service ENV_FILE=.env
make install-artificial-exchange-populator-service ENV_FILE=.env
```

More detail: [`docs/artificial-exchange.md`](docs/artificial-exchange.md).

## Configuration Map

Start from [`.env.example`](.env.example). It is the source of truth for the full setting list.

| Key | First-run/security meaning |
| --- | --- |
| `DUNE_STEAM_SERVER_DIR` | Local path to the official Steam self-host tool. |
| `DUNE_IMAGE_TAG` | Image tag loaded from the Steam package; documented baseline is `1963158-0-shipping`. |
| `WORLD_NAME` | Public/server-browser world name. |
| `WORLD_UNIQUE_NAME` | Stable internal world identifier; do not casually change after bootstrap. |
| `WORLD_REGION` | Region string used by the server configuration. |
| `FLS_SECRET` | Funcom self-hosting token; keep private. |
| `EXTERNAL_ADDRESS` | Public address clients should reach. |
| `GAME_RMQ_PUBLIC_HOST` / `GAME_RMQ_PUBLIC_PORT` | Client-facing game RabbitMQ endpoint; default TCP port is `31982`. |
| `POSTGRES_SUPER_PASSWORD` / `POSTGRES_DUNE_PASSWORD` | Local database credentials; never publish. |
| `POSTGRES_REPLICATION_PASSWORD` | Required for optional streaming replica. |
| `RMQ_HTTP_TOKEN_AUTH_SECRET` | Internal RabbitMQ auth-shim secret. |
| `DUNE_ADMIN_BIND_ADDRESS` / `DUNE_ADMIN_HOST_PORT` | Admin panel bind and host port; keep private. |
| `DUNE_ADMIN_ALLOWED_HOSTS` | Host header allowlist for the admin panel. |
| `DUNE_ADMIN_TOKEN` / `DUNE_ADMIN_REQUIRE_TOKEN` | Optional token protection for private admin API requests. |
| `DUNE_ADMIN_MUTATIONS_ENABLED` | Master gate for admin writes. |
| `DUNE_ADMIN_ITEM_GRANTS_ENABLED` | Separate gate for item grants, stack edits, and deletion. |
| `DUNE_ADMIN_GM_COMMANDS_ENABLED` / `DUNE_GM_COMMAND_PAYLOAD_VERIFIED` | GM/native command gates; keep false unless verified. |
| `DUNE_ADMIN_RESTART_COMMAND` | Hook used by scheduled restart jobs. |
| `DUNE_ADMIN_ANNOUNCE_COMMAND` | Hook used by restart announcements. |
| `DUNE_CHAT_COMMAND_ADMINS` / `DUNE_CHAT_COMMAND_ADMIN_FLS_IDS` | Chat-command allowlists. |

Most service settings require recreating or restarting affected containers before running processes pick them up. The admin panel documents runtime-only settings where applicable.

## Validation Before Publishing

Run the local validation target before pushing or publishing:

```bash
make validate
```

Also check formatting and publishable scope:

```bash
git diff --check
make list-publishable
```

If the full validation target cannot run in your local environment, run focused safe checks:

```bash
python3 -m py_compile admin/admin_panel.py scripts/admin-chat-commands.py scripts/dune_gm_command.py scripts/probe-gm-command.py
make secret-scan
make verify-local-state-ignored
```

Before public release, read [`SECURITY.md`](SECURITY.md) and [`docs/publication.md`](docs/publication.md).

## Full Manual

Start here:

- [`docs/setup.md`](docs/setup.md): initial setup flow.
- [`docs/operations.md`](docs/operations.md): health, recovery, startup, watchdog, ports, and restart workflow.
- [`docs/admin-panel.md`](docs/admin-panel.md): admin panel features, security, announcements, chat commands, and mutation gates.
- [`docs/backup-strategy.md`](docs/backup-strategy.md): local, onsite, offsite, replica, retention, and restore-test guidance.
- [`docs/postgres-replication.md`](docs/postgres-replication.md): local and remote Postgres standby.
- [`docs/artificial-exchange.md`](docs/artificial-exchange.md): artificial Exchange catalog, buyer, settlement, populator, and services.
- [`docs/public-static-site.md`](docs/public-static-site.md): optional public static status site.
- [`docs/maintenance-updates.md`](docs/maintenance-updates.md): 06:00 restart/backup/update timeline and Steam hotfix handling.
- [`docs/troubleshooting.md`](docs/troubleshooting.md): common failures and checks.
- [`docs/publication.md`](docs/publication.md): release safety checklist.

Operator references:

- [`docs/operator-handoff.md`](docs/operator-handoff.md): checklist for moving the stack to another operator or host.
- [`docs/platforms.md`](docs/platforms.md): Linux, Windows/macOS operator, Podman, VM, and NAS notes.
- [`docs/full-farm.md`](docs/full-farm.md): expanded farm and 30-partition warm-pool notes.
- [`docs/lan-reflection.md`](docs/lan-reflection.md): internal client hairpin/LAN reflection.
- [`docs/admin-bot.md`](docs/admin-bot.md): Paul/DASH Admin automation, player-presence announcements, and service install.
- [`docs/access-control.md`](docs/access-control.md): login password and access limits.
- [`docs/character-transfers.md`](docs/character-transfers.md): Director transfer policy.
- [`docs/validation.md`](docs/validation.md): live-client route validation checklist.

Architecture and research:

- [`docs/architecture.md`](docs/architecture.md): service map, state layout, and validation boundary.
- [`docs/reproducibility.md`](docs/reproducibility.md): fresh-host and migration checklist.
- [`docs/admin-mutation-map.md`](docs/admin-mutation-map.md): DB contracts used by admin writes.
- [`docs/admin-safe-content-api.md`](docs/admin-safe-content-api.md): guarded content mutation API.
- [`docs/admin-gm-console.md`](docs/admin-gm-console.md): GM command research and gates.
- [`docs/server-knobs-audit.md`](docs/server-knobs-audit.md): audited config/settings candidates.
- [`docs/network-investigation.md`](docs/network-investigation.md): DB/RabbitMQ/socket routing notes.
- [`docs/routing-investigation.md`](docs/routing-investigation.md): travel route investigation notes.
- [`docs/benchmarking.md`](docs/benchmarking.md): resource and transition benchmark notes.
- [`docs/kubernetes.md`](docs/kubernetes.md): unsupported Kubernetes translation notes.
- [`docs/packaging.md`](docs/packaging.md): publishable package boundaries and release checklist.
- [`docs/release-template.md`](docs/release-template.md): release/handoff note template.

Root-level research indexes:

- [`SERVER_CONFIG_KEYS.md`](SERVER_CONFIG_KEYS.md)
- [`SERVER_CONFIG_KEY_INDEX.md`](SERVER_CONFIG_KEY_INDEX.md)
- [`SERVER_BINARY_CONFIG_CANDIDATES.md`](SERVER_BINARY_CONFIG_CANDIDATES.md)
- [`DEEP_DESERT_EVENT_KNOBS.md`](DEEP_DESERT_EVENT_KNOBS.md)
- [`RESOURCE_RESPAWN_KNOBS.md`](RESOURCE_RESPAWN_KNOBS.md)
- [`HYDRATION_WATER_KNOBS.md`](HYDRATION_WATER_KNOBS.md)

## Key Files

- [`compose.yaml`](compose.yaml): base service topology.
- [`compose.allmaps.yaml`](compose.allmaps.yaml): 30-partition warm-pool extension.
- [`compose.replica.yaml`](compose.replica.yaml): optional Postgres streaming-replica extension.
- [`compose.limits.example.yaml`](compose.limits.example.yaml): optional local resource guardrails.
- [`examples/`](examples): portable env, backup, and operator examples.
- [`admin/admin_panel.py`](admin/admin_panel.py): admin web panel.
- [`admin/static/hagga-basin.webp`](admin/static/hagga-basin.webp): Hagga Basin panel map asset.
- [`public-site/`](public-site): optional public static site package.
- [`scripts/start-full-warm-pool.sh`](scripts/start-full-warm-pool.sh): 30-map startup helper.
- [`scripts/bootstrap-checklist.sh`](scripts/bootstrap-checklist.sh): read-only new-host readiness checklist.
- [`scripts/check-steam-update.sh`](scripts/check-steam-update.sh): compare `.env` image pin with current Steam package tarballs.
- [`scripts/watch-maps.sh`](scripts/watch-maps.sh): map watchdog.
- [`scripts/recover-map.sh`](scripts/recover-map.sh): fixed-partition recovery.
- [`scripts/restart-target.sh`](scripts/restart-target.sh): scheduled restart execution hook.
- [`scripts/install-daily-maintenance-timer.sh`](scripts/install-daily-maintenance-timer.sh): daily maintenance timer installer.
- [`scripts/install-artificial-exchange-service.sh`](scripts/install-artificial-exchange-service.sh): artificial Exchange service installer.
- [`scripts/announce.sh`](scripts/announce.sh): in-game announcement publisher.
- [`scripts/admin-chat-commands.py`](scripts/admin-chat-commands.py): chat command listener.
- [`scripts/seed-gateway-neighbor.sh`](scripts/seed-gateway-neighbor.sh): Docker bridge neighbor refresh helper.
- [`scripts/backup-offsite.sh`](scripts/backup-offsite.sh): local backup plus rclone, rsync, restic, or local-only sync helper.
- [`scripts/verify-backup.sh`](scripts/verify-backup.sh): structural backup check.
- [`scripts/install-backup-offsite-timer.sh`](scripts/install-backup-offsite-timer.sh): portable backup sync timer installer.
- [`scripts/package-manifest.sh`](scripts/package-manifest.sh): publishable file manifest generator.
- [`.env.example`](.env.example): documented settings template.
