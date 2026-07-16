# Recoverable Base Retirement

## Outcome

DASH can remove an abandoned or deliberately retired base from the active
world without copying the destructive row-deletion approach used by a surveyed
peer. The workflow calls the game's own
`dune.base_backup_save_from_totem(bigint,bigint)` function and assigns the
resulting recoverable backup to a current player-controller actor.

Confidence is **high** for the current-build database contract and the DASH
transaction/guard implementation, **moderate** for the expected next-start
world removal, and **unknown** until a disposable live base is archived and
restored through the game UI. The implementation therefore requires the target
map to be stopped and reports that a map start is required after execution.

## Why this is stronger than direct deletion

The July 16, 2026 AlphaNine source added a base-cleanup page that classifies
orphaned, partial, and owned bases and then deletes permission, building,
entity-link, and actor rows. That provides the cleanup outcome, but its active
path does not create a full PostgreSQL dump, bind the write to a content
fingerprint, or preserve the base in Dune's recovery system.

DASH instead uses the first-party database workflow. Read-only inspection of
the current `dune_sb_1_4_10_0` function body on `kspls0` established that it:

- finds the totem's FGL owner entity;
- captures every building instance owned by that entity;
- links supported placeables and the totem itself;
- detaches unsupported placeables from the totem owner;
- creates a `base_backups` record owned by the selected player controller;
- moves linked actors into `BaseBackup` state;
- removes permission rows and map markers through
  `dune.permission_actor_destroy`; and
- publishes the native permission-destroy notification.

No production write was used to derive that contract.

## Dashboard workflow

Open **Base Creator → Recoverable Base Retirement**. The table reports:

- totem actor and name;
- ownership classification;
- matched and missing player references;
- map, partition, and whether a server remains assigned;
- building-piece and owned-placeable counts; and
- content fingerprint inputs.

Select a row, provide a recovery player-controller ID when it cannot be chosen
unambiguously, and generate a preview. Preview is read-only and returns
`canExecute`, blockers, the exact typed confirmation, and the SHA-256
fingerprint that execution must reproduce while holding database locks.

Execution requires all of these conditions:

1. The target map has been stopped through the normal DASH Operations control
   and its server is absent from `dune.active_server_ids`.
2. Every matched base owner is explicitly `Offline`, `Disconnected`, or
   `Inactive`; unknown state is blocked.
3. The recovery player is a current `player_controller_id` and explicitly
   offline.
4. The totem is not already linked to an existing base backup.
5. The totem has exactly one FGL owner entity and the current database exposes
   the exact native function signature.
6. The base still has building pieces or owned placeables.
7. Global mutations and the dedicated retirement gate are enabled.
8. The request carries the exact preview fingerprint and
   `ARCHIVE BASE <totem_id>` confirmation.

The map must stay stopped from preview through completion. Refresh the preview
after any ownership, construction, placeable, player-status, or map-state
change.

## Transaction and recovery contract

Execution performs the following ordered sequence:

1. Open a database transaction and take a transaction-scoped advisory lock for
   the totem actor.
2. Lock the totem, FGL link, permission records, and recovery player state.
3. Rebuild the preview and reject a changed fingerprint or new blocker.
4. Create a non-empty full custom-format PostgreSQL dump with the existing
   `create_db_backup` path.
5. Persist a private `0600` pending receipt.
6. Call `dune.base_backup_save_from_totem(recovery_player_id, totem_id)`.
7. Verify the returned backup exists for the selected recovery player, has
   linked actors including the totem, and no permission actor/ranks remain.
8. Commit only after every verification passes.
9. Finalize a `0600` committed receipt.

The receipt directory is forced to `0700`; symbolic-link directories and
receipt entries are rejected or ignored so metadata browsing cannot escape the
private retirement workspace.

Any exception before commit rolls back the native operation. A pending receipt
is intentionally retained after a post-backup failure so an operator can see
that a dump was created but the retirement did not commit. If final receipt
creation fails after the database commit, the API returns
`committed=true`, `receiptStatus=pending-finalization-failed`, the retained
pending path, and a bounded finalization error; it does not misreport the
already-committed archive as rolled back.

Artifacts are private:

```text
backups/admin-panel/<timestamp>-<nonce>-<database>.dump
backups/admin-panel/base-retirement/pending-<receipt>.json
backups/admin-panel/base-retirement/base-<totem>-backup-<id>-<receipt>.json
```

The full dump remains the authoritative rollback path. The native base backup
is the preferred in-game recovery path after the map starts.

## API

Read the bounded inventory and receipt metadata:

```http
GET /api/admin/base-retirement?limit=500
```

Create a read-only preview:

```http
POST /api/admin/base-retirement
Content-Type: application/json

{
  "action": "preview",
  "totemId": 1234,
  "recoveryPlayerId": 46
}
```

Execute the exact preview:

```http
POST /api/admin/base-retirement
Content-Type: application/json

{
  "action": "archive",
  "totemId": 1234,
  "recoveryPlayerId": 46,
  "expectedFingerprint": "<64 lowercase hex characters>",
  "confirm": "ARCHIVE BASE 1234"
}
```

Reads require `read`; preview and execution use `world.write`. The owner token
continues to have recovery authority.

## Configuration and activation

The mutation gate defaults off:

```dotenv
DUNE_ADMIN_BASE_RETIREMENT_MUTATIONS_ENABLED=false
```

The normal parity activator includes the gate:

```bash
./scripts/enable-feature-parity.sh .env
./scripts/enable-feature-parity.sh .env --execute
```

The activator remains hostname-gated to `kspls0`, backs up `.env`, updates it
atomically, and loads the admin panel through the existing activation flow.
Preview remains available while the dedicated gate is off.

## Disposable live canary

Use a newly built disposable base on a nonessential stopped partition. Record
its totem ID, owner controller, piece count, placeables, and location. Then:

1. Stop the target map through DASH.
2. Generate and save the retirement preview.
3. Execute the fingerprint-bound archive.
4. Confirm the receipt, full dump, `base_backups` owner, linked actors, and
   removed permission rows.
5. Start the map through the normal guarded start path so post-start hooks run.
6. Verify the base is absent from the world and present in the recovery UI.
7. Restore it through the game workflow and verify pieces, supported
   placeables, ownership, and name.

Do not use an occupied player base for the first canary.

## Validation

```bash
make test-base-retirement
make test-admin-panel-safe-surfaces
make test-admin-access-control
make validate
```

The focused suite covers ownership classification, content-fingerprint
changes, automatic recovery-owner selection, active-map/online/already-backed
blockers, exact confirmation, backup-before-native ordering, verified commit,
stale-preview rejection, rollback, pending evidence, private receipt modes,
API gates, RBAC, and dashboard source integration. The scanner SQL was also
executed read-only against the current production schema and returned valid
rows. Rendered browser QA was unavailable in the implementation session; no
host desktop or operator Chrome session was used as a fallback.
