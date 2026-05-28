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
06:00  official DB upgrade patches are applied
06:00  operator DB patch markers and stale player RabbitMQ sessions are cleaned
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
DUNE_RESTART_CLEAR_PLAYER_RMQ_SESSIONS=true
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
with `+login anonymous`, `validate`, and `+@sSteamCmdForcePlatformType linux`
by default. On a production headless host, prefer a SteamCMD-owned directory
such as `/home/keith/dune-steamcmd-server` over a nested Steam desktop client
library path. If the Steam tool requires an owned Steam account instead of
anonymous access, set `DUNE_STEAM_LOGIN` and `DUNE_STEAM_PASSWORD` in `.env`. If
`steamcmd` is not installed on the host, the restart hook can run SteamCMD
through `DUNE_RESTART_STEAMCMD_HELPER_IMAGE`. The default helper image is
`cm2network/steamcmd:root`; pre-pull it before relying on unattended maintenance
if you do not want the maintenance window to depend on a Docker Hub pull.

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

## Pre-Start Hygiene

The maintenance start phase runs two local safety cleanups before services are
recreated:

- `scripts/apply-official-db-patches.sh` reads Funcom's
  `DuneSandbox/Database/Upgrade/__order.txt` from the configured
  `seabass-server:${DUNE_IMAGE_TAG}` image and applies any missing official SQL
  patches to `dune_sb_1_4_0_0` before maps start.
- `scripts/clear-player-rmq-sessions.sh` closes stale 16-hex player RabbitMQ
  connections and deletes matching `<FLS_ID>_queue` / `<FLS_ID>_rpcQueue`
  queues. This prevents a client from getting stuck when it reconnects after
  downtime and tries to recreate its per-player login queue.

For `DUNE_RESTART_TARGET=all`, player RabbitMQ cleanup is enabled by default.
For narrower restarts, it is skipped unless
`DUNE_RESTART_CLEAR_PLAYER_RMQ_SESSIONS=true` is set.

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
DUNE_STEAM_SERVER_DIR=/path/to/dune-steamcmd-server
DUNE_RESTART_STEAM_UPDATE_MODE=steamcmd
DUNE_RESTART_STEAMCMD_HELPER_IMAGE=cm2network/steamcmd:root
DUNE_STEAM_FORCE_PLATFORM=linux
DUNE_HARDCORE_DD_WEEKLY_WIPE_ENABLED=true
```

When `DUNE_HARDCORE_DD_WEEKLY_WIPE_ENABLED=true`, the restart start hook runs
`scripts/wipe-hardcore-deep-desert.sh .env --execute --if-due` before recreating map
servers. That script is deliberately narrower than the game's DB-wipe flag:

- actor/respawn cleanup uses `dune.coriolis_cleanup_partition` for partition
  `31`, `DeepDesert_1`, dimension `1`;
- resource fields are deleted only from `dune.resourcefield_state` where
  `map='DeepDesert'` and `dimension_index=1`;
- spice field current counters are reset only through
  `dune.reset_global_spice_field_state('DeepDesert', 1)`;
- marker and surveyed-area cleanup are not called because the official
  map-level cleanup only scopes those tables by map name.

Player-facing Deep Desert rule notices are handled by
`scripts/player-presence-announcer.py` through private Paul whispers. Keep
`DUNE_PLAYER_PRESENCE_DEEP_DESERT_JOIN_MESSAGES_ENABLED=true` so partition `8`
receives the PVE Casual notice and partition `31` receives the PVE Hardcore
notice.

Manual dry-run:

```bash
./scripts/wipe-hardcore-deep-desert.sh .env
```

Force an execution outside the weekly marker interval:

```bash
./scripts/wipe-hardcore-deep-desert.sh .env --execute --force
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

## Building-Piece Limit Patch Rollback

The `7500` building-piece experiment is applied through `compose.building-piece-limit.yaml` during game-server startup. It patches the server pak inside the recreated container overlay; it does not edit the official image or the host save data directly.

Current production wiring is derived by `scripts/compose-files.sh`. On `kspls0`,
`POSTGRES_REMOTE_REPLICA_HOST=kspls0` causes `compose.failover-standby.yaml` to
be included, and the building-piece overlay is included when the feature flag is
enabled:

```env
POSTGRES_REMOTE_REPLICA_HOST=kspls0
DUNE_BUILDING_PIECE_LIMIT_PATCH_ENABLED=true
DUNE_BUILDING_PIECE_LIMIT=7500
DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PATCH_ENABLED=false
DUNE_OODLE_HOST_LIBRARY=/home/keith/Documents/code/DuneAwakeningSelfHost/backups/operator-oodle/liboodle-data-shared.so
```

Known rollback anchors from the initial production wiring:

```text
pre-change files: /home/keith/Documents/code/DuneAwakeningSelfHost/backups/operator-changes/20260523T193322Z-building-piece-limit
pre-maintenance operator backup: /home/keith/Documents/code/DuneAwakeningSelfHost/backups/20260523T193525Z
scheduled maintenance backups: /home/keith/Documents/code/DuneAwakeningSelfHost/backups/admin-panel/maintenance/<stamp>-<job-id>
```

### Disable Before Maintenance Starts

Use this if the patch should not be attempted in the next 06:00 maintenance run.

```bash
cd /home/keith/Documents/code/DuneAwakeningSelfHost
python3 - <<'PY'
from pathlib import Path

path = Path(".env")
updates = {
    "DUNE_BUILDING_PIECE_LIMIT_PATCH_ENABLED": "false",
    "COMPOSE_FILES": "compose.yaml:compose.allmaps.yaml",
}
out = []
seen = set()
for line in path.read_text().splitlines():
    if line and not line.lstrip().startswith("#") and "=" in line:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY

docker compose --env-file .env \
  -f compose.yaml \
  -f compose.allmaps.yaml \
  up -d --force-recreate --no-deps admin-panel admin-panel-ingress
```

Confidence: high. This removes the overlay from the admin panel's scheduled restart environment before the game servers are recreated.

### Recover If Startup Fails

Use this if the 06:00 job stopped the game services but the patched recreate fails. This keeps the current database and save state and simply starts containers from the unpatched compose set.

```bash
cd /home/keith/Documents/code/DuneAwakeningSelfHost
python3 - <<'PY'
from pathlib import Path

path = Path(".env")
updates = {
    "DUNE_BUILDING_PIECE_LIMIT_PATCH_ENABLED": "false",
    "COMPOSE_FILES": "compose.yaml:compose.allmaps.yaml",
}
out = []
seen = set()
for line in path.read_text().splitlines():
    if line and not line.lstrip().startswith("#") and "=" in line:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY

DUNE_RESTART_TARGET=all \
DUNE_RESTART_PHASE=start \
DUNE_RESTART_ACTION=restart \
DUNE_RESTART_USE_HOST_COMPOSE=true \
DUNE_RESTART_HOST_WORKSPACE=/home/keith/Documents/code/DuneAwakeningSelfHost \
COMPOSE_FILES=compose.yaml:compose.allmaps.yaml \
./scripts/restart-target.sh
```

After the farm is online, recreate the admin panel so future scheduled jobs use the unpatched compose set:

```bash
docker compose --env-file .env \
  -f compose.yaml \
  -f compose.allmaps.yaml \
  up -d --force-recreate --no-deps admin-panel admin-panel-ingress
```

Confidence: high for a patcher, Oodle, or pak-layout failure. The original pak is restored by recreating containers without the overlay because the patch only touched the previous container filesystem.

## Landsraad Vendor Faction-Gate Patch

`DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PATCH_ENABLED=true` applies an experimental startup pak patch that keeps the active Landsraad vendor/decree gate but removes the dialogue condition that restricts vendors to the reigning faction. It targets eight generated vendor dialogue payloads in `pakchunk0-LinuxServer.pak`; if the target count changes, startup fails before the server runs. Use `compose.landsraad-vendor-faction-gate.yaml` when the building-piece overlay is not already mounting Oodle.

Dry-run from inside an opted-in game container:

```bash
python3 /workspace/scripts/patch-landsraad-vendor-faction-gate-pak.py \
  --pak /home/dune/server/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak \
  --oodle /tmp/oodle/liboodle-data-shared.so \
  --dry-run
```

Rollback is the same as the building-piece patch: set `DUNE_LANDSRAAD_VENDOR_FACTION_GATE_PATCH_ENABLED=false` and recreate the affected game-server containers. The patch only touches the container overlay pak, not the official image or persisted world data.

## Landsraad Goal Tuning

`DUNE_LANDSRAAD_GOAL_TUNING_ENABLED=true` runs `scripts/tune-landsraad-goals.sh`
during restart pre-start hygiene. The script installs a small DB-owned tuning
table, patches `dune.landsraad_insert_tasks` so future terms use the configured
scale, and idempotently applies the same scale to the current term. The default
scale is `DUNE_LANDSRAAD_GOAL_SCALE=0.5`, changing the stock `70,000` per-house
tile goal to `35,000`. A term is won by completing a row, column, or diagonal on
the 5x5 board, so the default winning-line target drops from `350,000` to
`175,000`.

Dry-run:

```bash
./scripts/tune-landsraad-goals.sh .env
```

Apply:

```bash
./scripts/tune-landsraad-goals.sh .env --execute
```

Rollback or retune by changing `DUNE_LANDSRAAD_GOAL_SCALE` and running the script
again. Set the scale to `1.0` to restore stock goals for incomplete current-term
tasks and future terms. Completed Landsraad tiles are not reopened by this
script.

### Restore World State

Use a state restore only if the server booted and then wrote bad world state, or if Postgres/RabbitMQ/server-saved data is otherwise suspect. Do not restore state for a simple patcher startup failure.

Find the newest stopped-world maintenance backup:

```bash
cd /home/keith/Documents/code/DuneAwakeningSelfHost
latest_backup="$(ls -dt backups/admin-panel/maintenance/* | head -1)"
printf '%s\n' "$latest_backup"
```

Dry-run the restore first:

```bash
./scripts/restore-state.sh --dry-run --rabbitmq --server-saved --config --tls .env "$latest_backup"
```

Then run the disruptive restore only after confirming the selected backup:

```bash
./scripts/restore-state.sh --rabbitmq --server-saved --config --tls .env "$latest_backup"
```

Confidence: high that the maintenance backup is the right restore point after the stop phase completes. Confidence is lower for the immediate operator backup taken while the world is live; prefer the stopped-world `backups/admin-panel/maintenance/...` backup when it exists.

### Full File Rollback

Use the pre-change file copy only if the `.env` or compose files themselves need to be restored to the exact pre-experiment state.

```bash
cd /home/keith/Documents/code/DuneAwakeningSelfHost
rollback_dir=backups/operator-changes/20260523T193322Z-building-piece-limit
cp -a "$rollback_dir/.env" .env
cp -a "$rollback_dir/compose.yaml" compose.yaml
cp -a "$rollback_dir/compose.allmaps.yaml" compose.allmaps.yaml
cp -a "$rollback_dir/scripts/run_server_safe.sh" scripts/run_server_safe.sh
rm -f compose.building-piece-limit.yaml
```

Only use this path when overwriting later `.env` changes is acceptable. The safer default is to set `DUNE_BUILDING_PIECE_LIMIT_PATCH_ENABLED=false` and remove `compose.building-piece-limit.yaml` from `COMPOSE_FILES`.
