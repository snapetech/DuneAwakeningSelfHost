# Maintenance Updates

This page documents the daily restart, backup, Steam-package update check, and return-online flow.

## Why 06:00

The daily maintenance target is 06:00 local host time. The timer schedules the job at 05:30 so players receive a 30-minute warning window before the restart begins.

The 06:00 target is deliberately after Funcom's nightly maintenance window. If Steam receives a self-hosted server hotfix during Funcom maintenance, the local Steam package has time to update before DASH stops the world, takes the stopped-world backup, loads the new image tarballs, and starts the farm again.

## Default Timeline

```text
05:30  dune-daily-maintenance-schedule.timer fires
05:30  scripts/schedule-daily-maintenance.sh posts a restart job to the admin panel
05:30  first in-game warning is sent immediately
05:30-05:55  warnings repeat every 5 minutes
05:55-06:00  warnings repeat every 1 minute
06:00  final "starting now" warning is sent
06:00  affected online players are soft-disconnected if the disconnect gates are enabled
06:00  selected services are stopped
06:00  maintenance backup is written
06:00  SteamCMD is asked to update the local self-hosted server tool
06:00  Steam package image tag is checked and updated if safe
06:00  selected services are recreated
06:00+ post-start health checks and farm readiness wait run
```

The configured defaults live in `.env`:

```env
DUNE_RESTART_CHECK_STEAM_UPDATE=true
DUNE_RESTART_STEAM_UPDATE_MODE=auto
DUNE_RESTART_STEAM_CLIENT_TRIGGER=true
DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS=900
DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS=30
DUNE_STEAM_CLIENT_COMMAND=steam
DUNE_RESTART_STEAMCMD_UPDATE=true
DUNE_RESTART_STEAMCMD_REQUIRED=false
DUNE_RESTART_STEAMCMD_HELPER_IMAGE=cm2network/steamcmd:root
DUNE_STEAM_APP_ID=4754530
DUNE_STEAM_LOGIN=anonymous
DUNE_STEAM_PASSWORD=
DUNE_STEAMCMD_COMMAND=steamcmd
DUNE_STEAMCMD_VALIDATE=true
DUNE_STEAMCMD_TIMEOUT_SECONDS=1800
DUNE_DAILY_RESTART_SCHEDULE_WINDOW=05:25-05:35
DUNE_DAILY_RESTART_ALLOW_OUTSIDE_WINDOW=false
DUNE_DAILY_RESTART_DELAY=30min
DUNE_DAILY_RESTART_REPEAT_SECONDS=600
DUNE_DAILY_RESTART_MESSAGE=Daily maintenance restart at 6:00 AM. Please get to a safe place.
```

## Install The Timer

After the admin panel restart path works manually, install the host timer:

```bash
./scripts/install-daily-maintenance-timer.sh .env
systemctl list-timers dune-daily-maintenance-schedule.timer --all --no-pager
```

The installer renders:

- `config/systemd/dune-daily-maintenance-schedule.service`
- `config/systemd/dune-daily-maintenance-schedule.timer`

The timer runs at `05:30:00` and creates an admin-panel restart job with `delay=30min`, so the actual maintenance begins at 06:00.

The timer is intentionally non-persistent. If the host is down at 05:30, DASH skips that day's automatic maintenance schedule instead of creating a late "06:00" restart at the wrong wall-clock time.

`scripts/schedule-daily-maintenance.sh` also refuses to schedule outside `DUNE_DAILY_RESTART_SCHEDULE_WINDOW` by default. This is a second guard for manual runs, timer mistakes, and stale installed units. For a deliberate manual test, set:

```bash
DUNE_DAILY_RESTART_ALLOW_OUTSIDE_WINDOW=true ./scripts/schedule-daily-maintenance.sh
```

## Restart Flow

Executed restart jobs use this sequence:

```text
soft-disconnect -> stop -> backup -> update -> start -> online wait
```

Executed shutdown jobs use this sequence:

```text
soft-disconnect -> stop -> backup -> update
```

Shutdown jobs leave services offline after the backup and update check.

If the stop phase fails, no backup, update check, or start is attempted. If the backup phase fails, services are left stopped so the failed backup can be investigated before the world is brought back online.

## Update Logic

The update phase first refreshes or waits for the official self-hosted server
Steam app:

```bash
./scripts/update-steam-tool.sh .env
```

By default `DUNE_RESTART_STEAM_UPDATE_MODE=auto`. On desktop Steam hosts, where
the Steam client is already running and owns the library, DASH sends
`steam://validate/4754530` to the client and waits for the local appmanifest
download/staging state to settle before image ingest. This avoids running a
competing SteamCMD process against the same library.

For headless hosts without a running Steam client, auto mode falls back to
SteamCMD. It runs app `4754530`, the Dune: Awakening Self-Hosted Server tool,
with `+login anonymous` and `validate`. If the Steam tool requires an owned
Steam account instead of anonymous access, set `DUNE_STEAM_LOGIN` and
`DUNE_STEAM_PASSWORD` in `.env`. If `steamcmd` is not installed on the host, the
restart hook can run SteamCMD through `DUNE_RESTART_STEAMCMD_HELPER_IMAGE`. The
default helper image is `cm2network/steamcmd:root`; pre-pull it before relying
on unattended maintenance if you do not want the maintenance window to depend on
a Docker Hub pull.

When `DUNE_RESTART_STEAMCMD_REQUIRED=false`, missing SteamCMD logs a warning and
the flow continues with the package already present on disk. Set
`DUNE_RESTART_STEAMCMD_REQUIRED=true` if you prefer maintenance to leave services
stopped rather than start from an unrefreshed Steam package.

After SteamCMD returns, the update phase runs:

```bash
./scripts/check-steam-update.sh .env
```

The script reads Docker `manifest.json` entries from the official Steam package image tarballs under `DUNE_STEAM_SERVER_DIR`, then compares the package tag with `DUNE_IMAGE_TAG`.

When the tags match, the update phase does nothing.

When exactly one newer package tag is found, the update phase runs:

```bash
./scripts/load-images.sh .env
./scripts/check-steam-update.sh .env --write-env
```

That loads the official Funcom image tarballs into Docker and updates `.env` to the package tag. The following start phase uses Compose `up -d --force-recreate --no-deps`, so recreated services use the new tag.

When the package is incomplete, unreadable, or contains multiple server tags, the update phase logs a warning and keeps the existing `DUNE_IMAGE_TAG`. This avoids guessing during unattended maintenance.

To disable the maintenance-window update check:

```env
DUNE_RESTART_CHECK_STEAM_UPDATE=false
```

## Container And Host Requirements

The normal host path uses local `docker compose`.

All normal Compose services use fixed addresses on the Dune bridge network.
The network gateway is pinned to `172.31.240.1`, service containers use the
lower static range, and Docker's dynamic allocation pool is restricted to
`172.31.240.128/25`. This keeps restart helpers and recreated one-shot
containers from taking addresses reserved for RabbitMQ, text-router, map
servers, or Postgres. It also keeps the Postgres host bind
`172.31.240.1:15432` valid after a full network recreate.

Before relying on an unattended restart after Compose changes, run:

```bash
make check-compose-static-ips ENV_FILE=.env
```

Inside the admin-panel container, `scripts/restart-target.sh` falls back to the mounted Docker socket and starts a short-lived privileged Docker CLI helper for update/start phases. That helper mounts:

- the Docker socket,
- the DASH repo path from `DUNE_RESTART_HOST_WORKSPACE`,
- the same repo at `/workspace`,
- `DUNE_STEAM_SERVER_DIR` when it is an absolute path.

That last mount is writable because SteamCMD must be able to update the local
Steam tool before DASH reads the package tarballs.

Required env values for unattended maintenance:

```env
DUNE_ADMIN_RESTART_COMMAND=/workspace/scripts/restart-target.sh
DUNE_RESTART_HOST_WORKSPACE=/path/to/DuneAwakeningSelfHost
DUNE_RESTART_COMPOSE_PROJECT=dune_server
DUNE_RESTART_USE_HOST_COMPOSE=true
DUNE_STEAM_SERVER_DIR=/path/to/Steam/steamapps/common/Dune Awakening Self-Hosted Server
DUNE_RESTART_STEAM_UPDATE_MODE=auto
DUNE_RESTART_STEAMCMD_HELPER_IMAGE=cm2network/steamcmd:root
```

## Manual Checks

Check the Steam package tag without changing `.env`:

```bash
./scripts/check-steam-update.sh .env
```

Force Steam to refresh the local self-hosted server tool:

```bash
./scripts/update-steam-tool.sh .env
```

Load images and update `.env` when a single safe package tag is found:

```bash
./scripts/load-images.sh .env
./scripts/check-steam-update.sh .env --write-env
```

Dry-run the restart hook update phase:

```bash
DUNE_RESTART_TARGET=all \
DUNE_RESTART_PHASE=update \
DUNE_RESTART_DRY_RUN=true \
./scripts/restart-target.sh
```

Run only the update phase with checks disabled:

```bash
DUNE_RESTART_TARGET=all \
DUNE_RESTART_PHASE=update \
DUNE_RESTART_CHECK_STEAM_UPDATE=false \
./scripts/restart-target.sh
```

## Rollback

Rollback after an image-tag upgrade means restoring the old `DUNE_IMAGE_TAG` and restoring state from a backup taken before the upgrade. Do not mix a downgraded image tag with post-upgrade database state unless schema compatibility has been verified.
