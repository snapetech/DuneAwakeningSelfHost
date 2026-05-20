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
06:00  Steam package image tag is checked and updated if safe
06:00  selected services are recreated
06:00+ post-start health checks and farm readiness wait run
```

The configured defaults live in `.env`:

```env
DUNE_RESTART_CHECK_STEAM_UPDATE=true
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

The update phase runs:

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

Inside the admin-panel container, `scripts/restart-target.sh` falls back to the mounted Docker socket and starts a short-lived privileged Docker CLI helper for update/start phases. That helper mounts:

- the Docker socket,
- the DASH repo path from `DUNE_RESTART_HOST_WORKSPACE`,
- the same repo at `/workspace`,
- `DUNE_STEAM_SERVER_DIR` read-only when it is an absolute path.

That last mount is required so the helper can read Steam package tarballs that live outside the repo.

Required env values for unattended maintenance:

```env
DUNE_ADMIN_RESTART_COMMAND=/workspace/scripts/restart-target.sh
DUNE_RESTART_HOST_WORKSPACE=/path/to/DuneAwakeningSelfHost
DUNE_RESTART_COMPOSE_PROJECT=dune_server
DUNE_RESTART_USE_HOST_COMPOSE=true
DUNE_STEAM_SERVER_DIR=/path/to/Steam/steamapps/common/Dune Awakening Self-Hosted Server
```

## Manual Checks

Check the Steam package tag without changing `.env`:

```bash
./scripts/check-steam-update.sh .env
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
