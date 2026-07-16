# Player Progression Receipts

The Admin Actions surface supports guarded persistent writes for Intel points,
known recipes, and research unlocks. These fields live inside the player pawn's
`dune.actors.properties` JSON document and do not have a mapped first-party
grant routine. The implementation therefore treats every write as a bounded,
receipted compare-and-swap operation.

Confidence: `moderate` for persistent-state and rollback correctness; `low` for
client refresh before the player relogs.

## Supported actions

`POST /api/admin/player-maintenance` accepts:

| Action | Input | Affected JSON state |
| --- | --- | --- |
| `add-intel` | `account_id`, `amount` | `TechKnowledgePlayerComponent.m_TechKnowledgePoints` |
| `unlock-recipe` | `account_id`, `key` | `CraftingRecipesLibraryActorComponent.m_KnownItemRecipes` |
| `unlock-research` | `account_id`, `key` | `TechKnowledgePlayerComponent.m_TechKnowledge.m_TechKnowledgeData`, plus the derived known-recipe array only when it is materialized |
| `rollback-progression` | `receipt_id`; optional matching `account_id` | The exact state captured by the selected receipt |

The specialization and keystone actions on the same endpoint use their
first-party tables/functions. They create database backups but do not use this
JSON receipt format and are not receipt-reversible.

## Write contract

Execution requires both the global mutation gate and
`DUNE_ADMIN_PLAYER_RUNTIME_MUTATIONS_ENABLED=true`. The target must be Offline
during preview and again while the player-state and actor rows are locked.
Before an actor JSON write, the panel:

1. validates the requested key against evidence in the active game database;
2. limits affected state to 4 MiB and each JSON collection to 10,000 rows;
3. creates a Postgres backup;
4. locks the target player and actor;
5. checks that the affected-state hash still matches the preview;
6. updates the complete actor properties with the previous document in the
   SQL `WHERE` clause as a compare-and-swap guard;
7. rereads and verifies the affected-state hash; and
8. writes a mode-`0600`, self-hashed receipt.

Receipt directories are mode `0700`. Receipt IDs are fixed-format, path
traversal is rejected, symlinks and non-regular files are rejected, and receipt
documents are limited to 8 MiB. Receipt state and document digests are checked
on every load.

## Preview and execution

Preview an Intel grant:

```bash
curl -sS -H "Authorization: Bearer $DUNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"action":"add-intel","account_id":123,"amount":100,"dry_run":true}' \
  https://SERVER/api/admin/player-maintenance
```

Execute the reviewed plan:

```bash
curl -sS -H "Authorization: Bearer $DUNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"action":"add-intel","account_id":123,"amount":100,"dry_run":false,"confirm":"WRITE PLAYER PROGRESSION"}' \
  https://SERVER/api/admin/player-maintenance
```

Dry-run responses omit raw before/after collections. Successful execution
returns state hashes, the database backup, and a receipt descriptor. The player
must relog; no map or game-server restart is required.

## Receipt-bound rollback

Receipts are stored below:

```text
backups/progression/receipts/<receipt-id>.json
```

The runtime catalog endpoint lists bounded receipt metadata for the browser:

```text
GET /api/admin/player-runtime-catalog
```

Preview rollback first:

```bash
curl -sS -H "Authorization: Bearer $DUNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"action":"rollback-progression","receipt_id":"RECEIPT","dry_run":true}' \
  https://SERVER/api/admin/player-maintenance
```

Execution requires the exact phrase `ROLL BACK PLAYER PROGRESSION`. It refuses
cross-database receipts, a mismatched selected account, an Online player, or
state that no longer matches the receipt after hash. A successful rollback
creates a fresh database backup and an inverse receipt whose `rollbackOf` field
points to the original receipt.

## Validation

```bash
make test-progression-admin
python3 -m unittest scripts/test-admin-panel-safe-surfaces.py
make validate
```

The focused suite covers affected-path preservation, compound research/recipe
state, size and shape bounds, Offline row locking, stale-preview rejection,
compare-and-swap updates, post-write verification, receipt permissions,
tamper detection, path confinement, and symlink rejection.
