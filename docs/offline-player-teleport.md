# Native Offline Player Teleport

## Outcome

DASH can move an explicitly Offline player's persisted pawn to a selected
world partition and finite XYZ coordinate through Dune's shipped
`dune.admin_move_offline_player_to_partition(text,bigint,dune.vector)`
function. The next reconnect loads the persisted target. No map or Admin
restart is required; the player must relog to observe the result.

This is a guarded database mutation, not a live in-engine teleport and not a
disconnect feature. It refuses an Online or native-present player. The
separate targeted network-timeout research is documented in
[soft-disconnect-teleport.md](soft-disconnect-teleport.md).

## Gates and authorization

Preview requires authenticated `players.write` access but remains read-only.
Execution requires all of:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`;
- `DUNE_ADMIN_OFFLINE_TELEPORT_ENABLED=true`;
- an executable preview generated for the exact account, target partition,
  target coordinates, current pawn transform, Offline predicates, and native
  function availability;
- the preview's unchanged `expectedFingerprint`;
- exact confirmation `MOVE OFFLINE PLAYER`;
- the configured high-risk change-approval policy when dual control is active.

The dedicated feature gate defaults to `false`. `scripts/enable-feature-parity.sh`
enables it in the complete parity profile. Changing the environment gate
requires the Admin service to reload; performing a teleport does not restart a
game map.

## Preview contract

```http
POST /api/admin/player-recovery/offline-teleport
Content-Type: application/json
```

```json
{
  "dryRun": true,
  "accountId": 456,
  "partitionId": 12,
  "location": {"x": 100.0, "y": 200.0, "z": 9000.0}
}
```

The response exposes the character, current pawn, target partition, bounded
target location, blockers, confirmation phrase, mutation-gate state, and a
SHA-256 fingerprint. It deliberately replaces the private FLS identity with
`<private FLS identity>`.

Coordinates must be finite and each axis must be between `-10000000` and
`10000000`. Preview refuses execution when any of these conditions is false:

- the persisted player status is exactly `Offline`;
- `dune.is_player_offline(fls_id)` is true;
- the active player pawn exists and matches the player-state reference;
- the native function is installed with the expected signature;
- the target world partition exists and is not blocked.

## Execution contract

```json
{
  "dryRun": false,
  "accountId": 456,
  "partitionId": 12,
  "location": {"x": 100.0, "y": 200.0, "z": 9000.0},
  "expectedFingerprint": "<64 lowercase hexadecimal characters>",
  "confirm": "MOVE OFFLINE PLAYER"
}
```

Execution performs the following ordered sequence:

1. Rebuild the preview and reject stale evidence before taking a backup.
2. Create a full database backup through the standard verified backup path.
3. Write a mode-`0600` pending receipt beneath
   `backups/admin-panel/offline-teleport/`.
4. Begin one database transaction and take an account-scoped advisory lock.
5. Lock the active encrypted player-state and pawn rows and take a shared lock
   on the target partition.
6. Rebuild and compare the complete preview fingerprint inside the locks.
7. Resolve the private FLS identity inside the transaction and invoke only the
   native offline move function.
8. Read back the pawn and require the same actor id, exact target partition,
   partition dimension, upgraded target map, bounded XYZ tolerance, explicit
   `Offline` status, and true native Offline predicate.
9. Commit only after every assertion passes, then finalize the private receipt.

Any exception before commit rolls the database transaction back. A failed
receipt finalization retains the pending receipt and reports that state rather
than claiming a complete evidence record.

The native function also calls Dune's Overmap survival-data path when the target
partition map is `Overmap`. That work remains inside the same transaction and
is covered by rollback on failure.

## Rollback

The execution receipt contains the complete prior pawn partition, map,
dimension, and coordinates plus the backup reference. Two recovery choices are
available:

1. Generate a fresh guarded preview and move the still-Offline player back to
   the receipted prior partition and coordinates.
2. Restore the referenced full database backup when a broader rollback is
   required.

The system does not silently perform a compensating teleport because the
player's connection state and pawn evidence may have changed after execution.

## Isolated semantic proof

The PostgreSQL restore drill requires the native teleport function in every
restored backup. Inside the disposable, networkless database it selects an
explicitly Offline player with a valid persisted pawn and partition, moves the
pawn by exactly one X unit through the native function, verifies the persisted
partition/map/dimension/coordinates and both Offline predicates, then rolls the
whole transaction back. The signed restore receipt records:

- `validation.offlineTeleportContract.candidateFound`;
- `validation.offlineTeleportContract.moveVerified`;
- `validation.offlineTeleportContract.transactionRolledBack`.

Feature readiness remains `semantic-proof-missing` until a current valid
restore receipt proves all three assertions. The drill has no network, uses a
read-only root filesystem, drops all capabilities, mounts the private source
dump read-only, and never connects to the live database.

## Metrics

The Admin metrics document exports:

```text
dash_offline_teleport_collector_up
dash_offline_teleport_enabled
dash_offline_teleport_ready
dash_offline_teleport_previews_total
dash_offline_teleport_executions_total
dash_offline_teleport_refusals_total
dash_offline_teleport_errors_total
```

Execution counters are process-local operational counters. Durable evidence is
the audit ledger, full backup, and private teleport receipt.

## Verification

```bash
make test-offline-teleport
make test-restore-drill
make test-admin-panel-safe-surfaces
make test-change-approvals test-change-contracts test-feature-readiness
make validate ENV_FILE=.env.example
```

For production activation, verify `hostname -s` returns `kspls0`, back up the
environment file, enable the dedicated gate, assured-deploy the Admin closure,
run a current isolated restore drill, and verify the readiness row. Deployment
validation uses preview only; it never teleports a live player.
