# Native Character Backups

DASH can capture and restore the portable character payload produced by the
game database's own character-transfer subsystem. This is a character-scoped
recovery artifact, not a substitute for a full database backup.

## Scope

`dune.character_transfer_export(text)` serializes the account and player actor
trio, inventories and items, progression, currency, markers, safe respawn
locations, packed/recovered vehicles, and base or vehicle data already placed
into the game's backup systems. The native payload does **not** capture a live
placed base or an ordinary parked world vehicle. Restore can consequently
disown live world property while it replaces the account. The browser repeats
that boundary before execution.

Use a full database backup when the desired recovery unit is the entire world.
Use this feature when the desired recovery unit is one offline character or a
portable character-transfer artifact.

## Activation

Preview, list, integrity verification, and authenticated download are available
without enabling writes. Capture, restore, and deletion require both gates:

```dotenv
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_CHARACTER_BACKUPS_ENABLED=true
```

The Admin Actions page exposes **Native Character Backups**. No map or service
restart is required after capture or restore. A restored player must relog so
the client and game process discard cached identity and actor state.

## API

- `GET /api/admin/character-backups` lists bounded public metadata. Add
  `account_id=<id>` to filter by the account ID recorded at capture.
- `GET /api/admin/character-backups?download=<snapshot-id>` downloads the raw
  native transfer JSON after authentication and snapshot integrity validation.
- `POST /api/admin/character-backups/preview` with `action=capture` and an
  `accountId` returns the exact capture fingerprint.
- `POST /api/admin/character-backups` with `action=capture`, the preview
  fingerprint, and `CAPTURE CHARACTER BACKUP` creates a snapshot.
- `POST /api/admin/character-backups/preview` with `action=restore` and a
  `snapshotId` returns restore eligibility and the exact restore fingerprint.
- `POST /api/admin/character-backups` with `action=restore`, the preview
  fingerprint, and `RESTORE CHARACTER BACKUP` performs the destructive native
  replacement.
- `POST /api/admin/character-backups` with `action=delete`, a `snapshotId`, and
  `DELETE CHARACTER BACKUP` removes that snapshot.

The API never returns the private FLS identity in list, preview, metrics, audit,
or receipts. The private snapshot necessarily retains it because the native
import function needs the exact identity that owned the export.

## Capture contract

Capture requires two independent offline predicates: the persisted
`online_status` must be exactly `Offline`, and `dune.is_player_offline(fls_id)`
must be true. The preview also binds the account/state/actor IDs, character
name, private-identity digest, current patch checksum, and native function
availability.

Execution rechecks the preview, takes an advisory lock and a shared player-state
row lock, recomputes the fingerprint inside that transaction, and calls only
`dune.character_transfer_export`. The transaction is rolled back after the JSON
is in memory, ensuring capture retains no database write. DASH validates the
payload shape and patch checksum, then writes a new private `0600` file with
exclusive creation under:

```text
backups/admin-panel/character-backups/snapshots/
```

The envelope is capped at 128 MiB and sealed with SHA-256 over its metadata,
private identity, and transfer payload. Listing and download recompute that hash
and fail closed on tampering, malformed JSON, path traversal, symlinks, invalid
shape, or checksum disagreement.

## Restore contract

Restore is a full character replacement and is governed as a critical change.
The preview verifies:

1. snapshot SHA-256, schema, payload shape, and stored patch checksum;
2. the current database's native export/import/checksum functions;
3. exact snapshot/current patch equality;
4. explicit `Offline` state plus `dune.is_player_offline` when the private
   identity currently has a character, or the verified absence of current
   player state when it does not; and
5. an exact fingerprint over public snapshot metadata, current identity/actor
   state, native contract, and patch state.

Execution creates a full PostgreSQL custom-format dump **before** opening the
restore transaction. It then locks a private-identity advisory key plus the
current account, player-state, and exact player actor rows; recomputes the
preview under those locks; and invokes
`dune.character_transfer_import(jsonb,text,text)`.

The shipped import function replaces the account and allocates new local IDs.
Some builds leave the destroyed account's player-state row or player actor trio
behind. DASH removes only the previously fingerprinted row and actor IDs, only
when the exact old account no longer exists, and only for PlayerCharacter,
PlayerController, or PlayerState classes. It never sweeps all actors owned by
the old account, because placed bases, storage, totems, and vehicles can retain
that historical owner ID. The transaction commits only after one account/state
pair exists for the private identity, the returned controller ID matches the
persisted controller, and the decrypted character name matches the snapshot.

The private receipt records the snapshot's public metadata, full database
backup reference, new account/state/controller IDs, bounded orphan-cleanup
counts, principal, and SHA-256. It does not record the FLS identity or transfer
payload.

## Recovery proof and readiness

The networkless PostgreSQL restore drill now selects an explicitly Offline
character inside the copied database, performs a native export, validates the
entry array and patch checksum, drops only the temporary export work table,
performs the native import, verifies the reconstructed identity/controller/name,
and rolls back the entire transaction. No live database, player, map, network,
or client is touched.

Feature readiness remains non-ready until the current restore-drill receipt has
all four assertions:

- `transactionRolledBack`
- `candidateFound`
- `exportVerified`
- `importVerified`

The dedicated gate and master mutation gate must also be enabled and all three
native functions must exist.

## Metrics

The Admin metrics endpoint exposes label-free counters and state only:

```text
dash_character_backups_collector_up
dash_character_backups_enabled
dash_character_backups_ready
dash_character_backups_snapshots
dash_character_backups_previews_total
dash_character_backups_captures_total
dash_character_backups_restores_total
dash_character_backups_deletes_total
dash_character_backups_refusals_total
dash_character_backups_errors_total
```

No player, account, snapshot, character, or private identity is used as a metric
label.

## Rollback

Capture and preview make no persistent database change. Deletion can be
recovered only from a broader DASH backup that contains the snapshot file.
Restore rollback is the full database dump referenced in its receipt. Use the
normal guarded restore workflow; do not attempt to reverse a native import with
raw table edits.

Run the focused tests with:

```bash
make test-character-backups
make test-restore-drill
make test-admin-panel-safe-surfaces
```
