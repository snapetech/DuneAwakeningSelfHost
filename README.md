# DuneAwakeningSelfHost (DASH)

DASH is a Linux/Docker Compose operations harness for the official Steam-installed **Dune: Awakening Self-Hosted Server** package.

It turns Funcom's self-host stack into a reproducible local layout with Compose services, operational scripts, a LAN-only admin panel, backup/recovery tooling, warm-pool map startup, watchdog recovery, restart/player-presence announcements, and guarded admin actions.

This repository does **not** contain, mirror, or license any Funcom server binaries, container images, Steam package files, game assets, live data, or secrets.

## Current Shape

- Official Steam server package: `Dune: Awakening Self-Hosted Server`
- Tested image lineage: `1963158-0-shipping`
- Runtime target: Linux host with Docker Compose
- Minimal world target: one `Survival_1` map
- Expanded standing farm: nine current travel targets
- Full warm-pool target: 30 online map partitions
- Admin surface: private LAN/VPN web panel. Token auth is optional and currently disabled by default for local trusted deployments.
- Automation: map watchdog, startup/recovery helpers, scheduled restart planner, restart/player-presence announcements, backups, and optional Postgres replica snapshots

Known working 30-map target:

```text
current_alive_active=30 active_servers=30 partitions=30
```

That is the server-side readiness target. Live-client login, travel, and routing still depend on a valid Funcom self-host/FLS token, public reachability, and correct LAN reflection when joining from inside the same network.

## Screenshots

### Overview

![DASH Admin overview showing 30/30 maps and Hagga Basin player positions](docs/assets/admin-overview.png)

### Operations

![DASH Admin operations page showing health, resources, and map status](docs/assets/admin-ops.png)

## What DASH Adds

- Compose topology for Postgres, admin RabbitMQ, game RabbitMQ, auth shim, text router, gateway, director, map services, and the admin panel.
- 30-partition warm-pool startup that brings maps up in a predictable order and validates active partition state.
- Recovery scripts for crashed/stale fixed-partition maps without blindly reproducing stale server-id loops.
- Host-level map watchdog service for unattended recovery.
- Local admin panel with Overview, Ops, Security, Runbook, Players, Settings, and Admin Actions pages.
- Hagga Basin player map that plots currently known online player coordinates from local database/runtime state.
- Restart announcement scheduler that publishes verified in-game chat through game RabbitMQ as the configured announcer.
- Optional player join/leave announcer that runs as a restartable host systemd service.
- Scheduled restart planner with pre-restart notices, maintenance backups, service recreate/start, and post-start health checks.
- Guarded admin writes for database backups, currency, XP, keystones, item grants, stack edits, and item deletion.
- Experimental GM/cheat route research kept out of the live panel until the native payload route is verified.
- Chat-command bridge for approved admins, including `&gm` helper commands and spam-protection hooks.
- Editable settings for `.env`, `director.ini`, `UserGame.ini`, and selected config overlays with backups.
- Backup/restore helpers, optional Postgres streaming replica setup, and remote replica snapshot helpers.
- Portable examples for single-map, full warm-pool, LAN admin ingress, rclone, rsync/NAS, restic, and systemd timers.
- LAN reflection/hairpin notes and Docker bridge neighbor seeding for the observed local networking failure mode.

## Repository Boundaries

Keep these local and uncommitted:

- `.env`
- `data/`
- `config/tls/`
- Steam package contents
- Funcom container image tarballs
- backups, captures, dumps, routing traces, and runtime logs
- real hostnames, public IPs, tokens, passwords, and private Discord/admin details

Publishable material should stay limited to original orchestration, helper scripts, and documentation. See [`docs/publication.md`](docs/publication.md) before making a public release.

## Requirements

- Linux host with Docker Compose.
- Official Dune: Awakening Self-Hosted Server Steam tool installed locally.
- Valid self-hosting/FLS token from Funcom's account portal.
- CPU with AVX2 support.
- Enough memory and disk for the map count you intend to run.
- `openssl`, `jq`, `rg`, and standard shell tooling for helper scripts.

Funcom's live account portal is:

```text
https://account.duneawakening.com/
```

If an old FAQ points to a PTS account URL, use the live portal for live self-hosting tokens.

## Quick Start

Create local settings, validate the host, load the official images, and initialize the database:

```bash
./scripts/populate-local-env.sh
./scripts/preflight.sh
./scripts/load-images.sh .env
docker compose --env-file .env up -d postgres admin-rmq game-rmq
docker compose --env-file .env run --rm db-init
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

For a single-map test world, prune unused generated `Survival_1` dimensions after DB bootstrap:

```bash
./scripts/single-survival-partition.sh .env
```

For the 30-partition warm pool:

```bash
./scripts/start-full-warm-pool.sh .env
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

The warm-pool helper starts dependencies first, writes the 30-partition layout, starts the service layer, starts maps in batches, seeds required Docker bridge neighbor entries, and validates RabbitMQ/auth/text-router paths.

## Admin Panel

Start the private admin panel:

```bash
docker compose --env-file .env up -d admin-panel
```

Default local URL:

```text
http://127.0.0.1:18080/
```

If another process owns `18080`, set `DUNE_ADMIN_HOST_PORT=18081` in `.env`, include that host in `DUNE_ADMIN_ALLOWED_HOSTS`, and recreate only the admin panel.

The panel is intended for trusted LAN/VPN access only. Do not expose it directly to the public internet. By default the local deployment runs unlocked on the private admin surface. To require a token, set `DUNE_ADMIN_REQUIRE_TOKEN=true` and `DUNE_ADMIN_TOKEN`; protected requests then send `X-Admin-Token`.

Panel pages:

| Page | Purpose |
| --- | --- |
| Overview | Readiness metrics, health summary, Hagga Basin player map, map details, and player preview. |
| Ops | Restart planner, restart announcements, resource telemetry, map health, network checks, farm state, and partition state. |
| Security | Host/origin checks, auth mode, mutation gates, allowlists, and audit events. |
| Runbook | Copy/paste operational commands for health, backups, restores, logs, profiling, and routing capture. |
| Players | Online/offline roster, player detail, account/controller/pawn context, currency, XP, inventory, and location views. |
| Settings | Edits for selected `.env` and config values, with backups. |
| Admin Actions | Database backups and guarded mutations for currency, XP, keystones, item grants, stack edits, and item deletion. |

If the local published admin port accepts TCP but returns no HTTP bytes after a container recreate, refresh the observed Docker bridge neighbor entries:

```bash
./scripts/seed-gateway-neighbor.sh
curl -H 'Host: admin-panel:8080' http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18081}/api/status
```

More detail: [`docs/admin-panel.md`](docs/admin-panel.md).

## Operations

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

Recover a fixed-partition map that has a stale server id:

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

Detailed runbooks live in [`docs/operations.md`](docs/operations.md) and [`docs/troubleshooting.md`](docs/troubleshooting.md).

## Backups and Replication

Create a local state backup:

```bash
./scripts/backup-state.sh .env
```

Restore a backup:

```bash
./scripts/restore-state.sh .env backups/<backup-id>
```

Optional local Postgres streaming standby:

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

Replication is an extra recovery layer, not a replacement for stopped-world backups. Deletes and bad writes replicate too. See [`docs/postgres-replication.md`](docs/postgres-replication.md).

Portable backup examples:

```bash
DUNE_BACKUP_OFFSITE_MODE=none ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/rclone-offsite.env ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/rsync-nas.env ./scripts/backup-offsite.sh .env
DUNE_BACKUP_REMOTE_ENV=examples/backup/restic.env ./scripts/backup-offsite.sh .env
```

Install an hourly offsite/onsite backup timer:

```bash
./scripts/install-backup-offsite-timer.sh .env examples/backup/rclone-offsite.env
```

See [`docs/backup-strategy.md`](docs/backup-strategy.md).

## Networking

Forward only the client-facing ports needed for your layout.

Single `Survival_1` layout:

```text
7777/udp
```

Expanded nine-map farm:

```text
7777-7785/udp
```

Full 30-partition warm pool:

```text
7777-7806/udp
```

Live-client login also receives the game RabbitMQ address from FLS before gameplay UDP starts. Forward:

```text
GAME_RMQ_PUBLIC_PORT tcp, default 31982/tcp
```

Do not forward Postgres, RabbitMQ management, the admin panel, or local debug ports. The Compose files may expose IGW/S2S UDP ports for local debugging; keep those closed publicly unless a live-client capture proves they are required.

For LAN players joining through the public listing, keep `EXTERNAL_ADDRESS` set to the public address and use LAN reflection/hairpin routing. Do not flip the advertised address between public and private for normal operation. See [`docs/lan-reflection.md`](docs/lan-reflection.md).

## Configuration

Start from [`.env.example`](.env.example). Important values:

| Key | Meaning |
| --- | --- |
| `DUNE_STEAM_SERVER_DIR` | Local Steam tool path. |
| `DUNE_IMAGE_TAG` | Official image tag loaded from the Steam package. |
| `WORLD_NAME` | Public/server-browser world name. |
| `WORLD_UNIQUE_NAME` | Stable internal world identifier. |
| `DUNE_SERVER_DISPLAY_NAME` | Optional in-engine `Bgd.ServerDisplayName`; defaults to `WORLD_NAME` when blank. |
| `FLS_SECRET` | Funcom self-hosting token. |
| `EXTERNAL_ADDRESS` | Public address advertised to clients. |
| `GAME_RMQ_PUBLIC_HOST` / `GAME_RMQ_PUBLIC_PORT` | Client-facing game RabbitMQ endpoint returned during login. |
| `DUNE_ADMIN_TOKEN` | Admin panel API token. |
| `DUNE_ADMIN_MUTATIONS_ENABLED` | Master gate for admin writes. |
| `DUNE_ADMIN_ITEM_GRANTS_ENABLED` | Separate gate for item grants/edits/deletes. |
| `DUNE_ADMIN_RESTART_COMMAND` | Hook used by scheduled restart jobs. |
| `DUNE_ADMIN_ANNOUNCE_COMMAND` | Hook used by restart announcements. |

Most service settings require the affected containers to be recreated or restarted before running processes pick them up. Runtime-only settings in the admin panel document whether a restart is expected.

## Chat, Announcements, and GM Research

Restart announcements use [`scripts/announce.sh`](scripts/announce.sh), which publishes verified `TextChat` payloads to game RabbitMQ `chat.map` with bundled `pika`.

Verify announcement delivery:

```bash
./scripts/verify-announcement.sh 'PAUL ANNOUNCEMENT VERIFY'
```

The chat-command bridge is [`scripts/admin-chat-commands.py`](scripts/admin-chat-commands.py). It listens for configured command prefixes, checks approved admins, and can reply through the announcement path.

The player-presence announcer is [`scripts/player-presence-announcer.py`](scripts/player-presence-announcer.py). It baselines current online players, then announces later joins/leaves through the same in-game announcement path. Install the host service with:

```bash
make install-player-presence-announcer-service ENV_FILE=.env
```

See [`docs/admin-bot.md`](docs/admin-bot.md) for templates, service checks, and reboot behavior.

The native GM/cheat route remains research-only. It is not exposed as a live Admin Actions control because the RabbitMQ payload envelope is not verified. Probe and chat helper paths stay blocked unless all related gates are enabled:

```env
DUNE_ADMIN_GM_COMMANDS_ENABLED=false
DUNE_GM_COMMAND_PAYLOAD_VERIFIED=false
DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=false
```

Documentation: [`docs/admin-gm-console.md`](docs/admin-gm-console.md).

## Documentation Map

Start here:

- [`docs/setup.md`](docs/setup.md): initial setup flow.
- [`docs/operator-handoff.md`](docs/operator-handoff.md): checklist for moving the stack to another operator or host.
- [`docs/platforms.md`](docs/platforms.md): Linux, Windows/macOS operator, Podman, VM, and NAS notes.
- [`docs/operations.md`](docs/operations.md): health, recovery, startup, watchdog, ports, and restart workflow.
- [`docs/maintenance-updates.md`](docs/maintenance-updates.md): 06:00 restart/backup/update timeline and Steam hotfix handling.
- [`docs/admin-panel.md`](docs/admin-panel.md): admin panel features, security, announcements, chat commands, and mutation gates.
- [`docs/admin-bot.md`](docs/admin-bot.md): Paul/DASH Admin automation, player-presence announcements, and service install.
- [`docs/backup-strategy.md`](docs/backup-strategy.md): local, onsite, offsite, replica, retention, and restore-test guidance.
- [`docs/troubleshooting.md`](docs/troubleshooting.md): common failures and checks.
- [`docs/full-farm.md`](docs/full-farm.md): expanded farm and 30-partition warm-pool notes.
- [`docs/lan-reflection.md`](docs/lan-reflection.md): internal client hairpin/LAN reflection.
- [`docs/postgres-replication.md`](docs/postgres-replication.md): local and remote Postgres standby.

Architecture and research:

- [`docs/architecture.md`](docs/architecture.md): service map, state layout, and validation boundary.
- [`docs/reproducibility.md`](docs/reproducibility.md): fresh-host and migration checklist.
- [`docs/access-control.md`](docs/access-control.md): login password and access limits.
- [`docs/character-transfers.md`](docs/character-transfers.md): Director transfer policy.
- [`docs/admin-mutation-map.md`](docs/admin-mutation-map.md): DB contracts used by admin writes.
- [`docs/server-knobs-audit.md`](docs/server-knobs-audit.md): audited config/settings candidates.
- [`docs/network-investigation.md`](docs/network-investigation.md): DB/RabbitMQ/socket routing notes.
- [`docs/routing-investigation.md`](docs/routing-investigation.md): travel route investigation notes.
- [`docs/validation.md`](docs/validation.md): live-client route validation checklist.
- [`docs/benchmarking.md`](docs/benchmarking.md): resource and transition benchmark notes.
- [`docs/kubernetes.md`](docs/kubernetes.md): unsupported Kubernetes translation notes.
- [`docs/packaging.md`](docs/packaging.md): publishable package boundaries and release checklist.
- [`docs/release-template.md`](docs/release-template.md): release/handoff note template.
- [`docs/publication.md`](docs/publication.md): release safety checklist.
- [`docs/public-static-site.md`](docs/public-static-site.md): optional public static server page with status, settings, player list, and Hagga Basin map.

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
- [`public-site/`](public-site): optional public static site package for operators who want a safe public status/settings/map page.
- [`scripts/start-full-warm-pool.sh`](scripts/start-full-warm-pool.sh): 30-map startup helper.
- [`scripts/bootstrap-checklist.sh`](scripts/bootstrap-checklist.sh): read-only new-host readiness checklist.
- [`scripts/check-steam-update.sh`](scripts/check-steam-update.sh): compare `.env` image pin with the current Steam package tarballs.
- [`scripts/watch-maps.sh`](scripts/watch-maps.sh): map watchdog.
- [`scripts/recover-map.sh`](scripts/recover-map.sh): fixed-partition recovery.
- [`scripts/restart-target.sh`](scripts/restart-target.sh): scheduled restart execution hook.
- [`scripts/install-daily-maintenance-timer.sh`](scripts/install-daily-maintenance-timer.sh): systemd timer installer for 06:00 daily restart/backup/update maintenance.
- [`scripts/announce.sh`](scripts/announce.sh): in-game announcement publisher.
- [`scripts/admin-chat-commands.py`](scripts/admin-chat-commands.py): chat command listener.
- [`scripts/seed-gateway-neighbor.sh`](scripts/seed-gateway-neighbor.sh): Docker bridge neighbor refresh helper for the observed local bridge issue.
- [`scripts/backup-offsite.sh`](scripts/backup-offsite.sh): local backup plus rclone, rsync, restic, or local-only sync helper.
- [`scripts/verify-backup.sh`](scripts/verify-backup.sh): structural check for backup dumps, archives, and manifests.
- [`scripts/install-backup-offsite-timer.sh`](scripts/install-backup-offsite-timer.sh): systemd timer installer for portable backup sync.
- [`scripts/package-manifest.sh`](scripts/package-manifest.sh): publishable file manifest generator.
- [`.env.example`](.env.example): documented settings template.

## Validation

Run the local validation target before pushing:

```bash
make validate
```

Useful focused checks:

```bash
python3 -m py_compile admin/admin_panel.py scripts/admin-chat-commands.py scripts/dune_gm_command.py scripts/probe-gm-command.py
git diff --check
```
