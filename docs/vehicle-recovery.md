# Recoverable Vehicle Retirement

## Outcome

DASH can move one or more abandoned player vehicles into the game's native
`VehicleRecovery` queue without deleting the vehicle actors. The current
`VehicleBackup` table has a one-row-per-character constraint, so it cannot
hold both vehicles when one player owns several. The first-party
`dune.store_recovered_vehicles_wiped_before_spawn(bigint[],recoveredvehiclereason,boolean)` routine is the source of truth for this multi-vehicle workflow. It removes the vehicles' world permission rows so the map can clear them; the native restore path recreates a rank-1 owner when an administrator places a recovered vehicle.

The workflow is intentionally narrow: the selected vehicles must have one
rank-1 owner, that owner must be explicitly offline, the owning map must be
stopped, and the request must reproduce a fresh preview fingerprint. A full
PostgreSQL dump and a private receipt are created before the native call.

## Cargo warning

The recovery queue preserves ordinary vehicle cargo by default. The operator
may explicitly request the native `delete_items` behavior with
`--allow-inventory-wipe`; that destructive side effect is then bound into the
exact confirmation phrase. The receipt always contains a private pre-action
snapshot of the vehicle actor, vehicle row, permission actors/ranks, actor
state, inventories, items, and vehicle modules. Vehicle modules are not
removed by this workflow.

This is not a credit or player-inventory operation. It does not claw back
currency, change the player's wallet, or delete the vehicle actors. World
permission rows are removed so the actors no longer occupy the live map; the
vehicle rows remain recoverable.

## Preview and archive

Read-only inventory and ownership scan:

```bash
./scripts/vehicle-retirement.py list --account-id 5247
```

Preview the two selected ornithopters while preserving `Shadow 2`'s cargo:

```bash
./scripts/vehicle-retirement.py preview \
  --account-id 5247 \
  --vehicle-id 22279 --vehicle-id 22296
```

The preview returns `expectedFingerprint` and the exact confirmation. Archive
only after the map is stopped and the preview still has `canExecute: true`:

```bash
./scripts/vehicle-retirement.py archive \
  --account-id 5247 \
  --vehicle-id 22279 --vehicle-id 22296 \
  --expected-fingerprint <preview fingerprint> \
  --confirm 'ARCHIVE THOPTERS 22279,22296'
```

The CLI calls the authenticated Admin Panel API. The same operations are
available at:

```text
GET  /api/admin/vehicle-retirement
POST /api/admin/vehicle-retirement   {"action":"preview"|"archive", ...}
```

Execution requires both `DUNE_ADMIN_MUTATIONS_ENABLED=true` and
`DUNE_ADMIN_VEHICLE_RETIREMENT_MUTATIONS_ENABLED=true`. It never starts or
stops a map itself; the response reports `mapRestartRequired: true` because a
map start is required before the staged actors disappear from the live world.
Use the guarded restart scripts documented in the repository instructions,
not raw `docker compose restart`.

Private artifacts are written under:

```text
backups/admin-panel/<timestamp>-<nonce>-<database>.dump
backups/admin-panel/vehicle-retirement/pending-<receipt>.json
backups/admin-panel/vehicle-retirement/vehicles-<ids>-<receipt>.json
```

The dump is the authoritative database rollback artifact. The native recovery
row is the preferred player-facing recovery path.
`dune.restore_recovered_vehicle` moves an actor back to a supplied
map/partition/transform, recreates Mara's rank-1 vehicle permission, and
consumes the recovery row. DASH does not provide an automatic restore because
placement and any extra permission ranks must be reviewed by an operator. The
receipt's permission snapshot is the source for restoring non-owner ranks if
needed.

## Repeating recovery reminders

Store one reminder per account with any number of native vehicle-recovery ids:

```bash
./scripts/vehicle-recovery-reminder.py add \
  --account-id 5247 --vehicle-id 22279 --vehicle-id 22296 \
  --message 'Your parked ornithopters are preserved in the server native vehicle recovery queue. Contact a server admin when you return.'
./scripts/vehicle-recovery-reminder.py list
./scripts/vehicle-recovery-reminder.py check --account-id 5247
./scripts/vehicle-recovery-reminder.py remove --account-id 5247
```

The registry defaults to
`backups/admin-bot/vehicle-recovery-reminders.json` and is shared by the CLI,
the player-presence worker, and Admin Digests. Each active record sends one
private Paul whisper per distinct login session. Status is checked every poll;
the reminder remains active on query failure and stops only after every listed
vehicle satisfies conservative restore proof: the actor still exists, both
native backup/recovery rows and actor states are gone, and the account still
has the rank-1 vehicle permission.

Admin Digests exposes the same registry with add/replace, status, online/last
send markers, and exact-confirmation removal. Reminder changes require the
global mutation gate and `DUNE_ADMIN_VEHICLE_RECOVERY_REMINDER_MUTATIONS_ENABLED=true`.
Removing a reminder changes only the reminder record; it does not alter the
vehicle, recovery row, inventory snapshot, player, or credits.

## Live-operation safety

Production mutations must run on `kspls0`. Confirm the hostname before the
preview/archive request. Stop and mark the owning map inactive using the
guarded restart workflow, verify there are no online players on that map, then
refresh the preview and execute. Afterward start the map through the same
guarded path and verify `recovered_vehicles`, `actor_state`, zero world
permission rows, the receipt, and map health before considering the spot clear.
