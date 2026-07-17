# Player Identity Integrity And Native Character Deletion

## Outcome

DASH treats a Dune account and its current player-state row as an identity
pair, not as an unconstrained join. The Players roster, character search,
detail view, and account-based mutation resolver select exactly one current
row for each account:

1. newest `last_login_time`;
2. highest player-state `id` when login time is tied or absent.

Rows whose `account_id` no longer exists in `dune.accounts` never enter those
canonical reads. The Players page separately reports duplicates, true orphans,
and missing pawn/controller actor references so operators see the underlying
condition instead of merely hiding it.

Confidence: high for query and transaction behavior. The rule matches the
post-1.5 schema, where `encrypted_player_state.account_id` is no longer unique,
and protects every supported database state without assuming duplicate rows
are safe to delete.

## Why This Exists

The native `dune.delete_account(text,text)` function deletes the account and
character actors but can leave its `dune.encrypted_player_state` row behind.
Separately, a valid account can have multiple player-state rows. A plain join
against `dune.player_state` can therefore:

- duplicate a player in a roster or inflate counts;
- select a stale pawn/controller for item or teleport actions;
- keep a deleted character visible;
- make a later recreation appear attached to an old actor.

DASH distinguishes the two conditions:

- **orphan:** no matching `dune.accounts` row. It is mechanically safe to
  remove with the exact `NOT EXISTS` predicate.
- **duplicate valid row:** the account still exists. DASH selects a canonical
  row for reads, reports all row IDs, and does not automatically delete any of
  them because the game may still reference their state.

## Dashboard And API

The Players page contains the Player Identity Integrity panel. It shows:

- account and player-state row totals;
- duplicate-account and excess-row counts;
- orphan count and a bounded orphan sample;
- missing pawn and controller reference counts;
- the exact cleanup plan and evidence fingerprint;
- preview and execution controls for native character deletion.

Authenticated endpoints:

```text
GET  /api/admin/player-identity-integrity
POST /api/admin/player-identity-integrity
```

Supported POST actions:

```text
preview-cleanup
cleanup-orphans
preview-delete
delete-character
```

GET and preview actions are read-only. POST remains a `players.write`
capability because one endpoint also carries lifecycle writes. Mutating actions
are classified as critical by four-eyes approvals and blast-radius change
contracts.

## Orphan Cleanup Contract

Preview:

```json
{"action":"preview-cleanup"}
```

The preview binds the row count, ordered row-ID/account digest, first ID, and
last ID into `expectedFingerprint`. Execution requires:

```json
{
  "action":"cleanup-orphans",
  "expectedFingerprint":"<preview fingerprint>",
  "confirm":"CLEAN ORPHAN PLAYER STATE"
}
```

Execution order:

1. Re-read and compare the preview before backup.
2. Create a full PostgreSQL custom-format backup.
3. Re-read the exact evidence in one transaction.
4. Refuse if any row changed while the transaction was acquired.
5. Delete only:

   ```sql
   delete from dune.encrypted_player_state eps
   where not exists (
     select 1 from dune.accounts a where a.id=eps.account_id
   )
   ```

6. Verify zero orphans remain and the returned-row count equals the preview.
7. Commit and write a mode-`0600` private receipt beneath
   `backups/admin-panel/player-identity/`.

A `pending-player-identity-*.json` receipt is written after the backup and
before the transaction. Transaction failure leaves it for investigation. After
a verified commit DASH writes the final receipt atomically and removes the
pending file. If finalization storage fails, the API still reports the already
committed result with `receipt.status=pending-finalization-failed` and retains
the pending evidence instead of misreporting the mutation as rolled back.

No valid-account duplicate is part of this repair.

## Native Character Deletion Contract

Preview:

```json
{"action":"preview-delete","accountId":456}
```

The preview returns canonical character/account evidence, all player-state row
counts, current offline state, native-function availability, a SHA-256
fingerprint, and the target-specific confirmation:

```text
DELETE CHARACTER 456
```

Execution:

```json
{
  "action":"delete-character",
  "accountId":456,
  "reason":"Requested by the player after identity verification",
  "expectedFingerprint":"<preview fingerprint>",
  "confirm":"DELETE CHARACTER 456"
}
```

The server then:

1. Rejects missing native `delete_account(text,text)`, missing FLS identity, or
   any player-state row not explicitly Offline/Disconnected/Inactive.
2. Revalidates the fingerprint before creating a backup.
3. Creates a full database backup.
4. Takes an account-scoped PostgreSQL advisory transaction lock.
5. Locks every underlying `encrypted_player_state` row and the encrypted
   account row.
6. Rebuilds the plan inside that transaction and refuses drift or an online
   transition.
7. Calls only `dune.delete_account(fls_id, reason)`.
8. Requires the native function to report success.
9. Removes every true orphan left by the native call with the same `NOT
   EXISTS` predicate.
10. Proves the selected account and its player-state rows are absent and that
    no orphan remains before commit.
11. Writes a private receipt containing the backup, bound preview, result, and
    receipt SHA-256.

The operation does not restart a map or service. The deletion is permanent in
the live database; rollback is restoration of the recorded full backup.

## Gates

```dotenv
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_PLAYER_IDENTITY_MUTATIONS_ENABLED=true
DUNE_ADMIN_CHARACTER_DELETE_ENABLED=true
```

The identity gate authorizes orphan cleanup. Character deletion requires both
identity and delete gates. Keeping the delete gate false leaves audit and both
previews usable.

Changing either feature gate requires recreating only the Admin service. It
does not require a game-map restart.

## Unified Item And Schematic Catalog

The same parity tranche also makes the committed item catalog canonical:

- template IDs deduplicate case-insensitively;
- the richer duplicate wins deterministically;
- blank kinds become `item`, `schematic`, or `patent` from reviewed category;
- every row receives a display group;
- server ordering is group, category, numeric tier, name, and template ID;
- `catalog_item()` uses the same case-insensitive identity as the browser and
  grant metadata lookup;
- the browser groups categories, searches kind as well as name/template/
  category, shows 120 rows at a time, and progressively loads the complete
  catalog instead of silently truncating after 240.

The API returns catalog counts, dropped-duplicate count, groups, categories,
kinds, canonical-ID rule, and sort rule under `catalog`. Item grants and the
visual browser therefore consume one source and one identity rule.

## Metrics And Alerts

The existing `/metrics/change-intelligence` scrape includes label-free gauges:

```text
dash_player_identity_collector_up
dash_player_identity_healthy
dash_player_identity_accounts
dash_player_identity_state_rows
dash_player_identity_duplicate_accounts
dash_player_identity_duplicate_excess_rows
dash_player_identity_orphan_rows
dash_player_identity_missing_pawn_references
dash_player_identity_missing_controller_references
dash_player_identity_cleanup_enabled
dash_player_identity_character_delete_enabled
```

Prometheus rules alert when the audit cannot run, true orphans remain for five
minutes, or valid accounts retain duplicate player-state rows for fifteen
minutes. These alerts never trigger cleanup or deletion.

## Validation

```bash
make test-player-identity
make test-admin-panel-safe-surfaces
python3 scripts/test-change-approvals.py
python3 scripts/test-change-contracts.py
docker compose --env-file .env.example config --quiet
make validate
```

The focused suite covers integrity classification, canonical ordering,
fingerprint drift, exact confirmation, backup ordering, transactional cleanup,
native deletion success, post-write proof, rollback on proof failure, receipt
permissions, GET/preview routing, and gate-closed execution.

Do not test deletion against a production character merely to prove the route.
Use a disposable character in an isolated or explicitly selected live canary,
then verify the receipt and backup before considering the runtime path proven
for a new server build.
