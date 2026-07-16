# Inventory Slot Integrity

DASH detects and repairs the duplicate-slot condition that can make real item
rows invisible in game. The game database does not enforce uniqueness for
`(inventory_id, position_index)`. If two items occupy the same slot, the client
can render only one of them.

Confidence is **high** for detection and transactional relocation. A player
whose inventory was changed must return to the main menu and rejoin so the game
reloads that inventory. A full map restart is not required.

## Audit

Audit is live-safe and read-only:

```bash
./scripts/inventory-conflicts.sh --env-file .env audit
# or
make inventory-integrity-audit ENV_FILE=.env
```

The report includes duplicate non-null `(inventory_id, position_index)` groups,
negative positions, and positions at or above a finite `max_item_count`.

Audit exits with status `1` when duplicate slots exist so it can be used by a
monitor. Negative and over-capacity positions are reported but are not changed
by duplicate repair. Those cases require operator review because the correct
destination can depend on inventory type and intended layout.

## Repair preview

```bash
./scripts/inventory-conflicts.sh --env-file .env repair
# or
make inventory-integrity-repair-preview ENV_FILE=.env
```

Preview performs the audit and describes repair without creating a backup or
changing a database row.

## Execute a production repair

Run production repair on `kspls0`:

```bash
hostname
./scripts/inventory-conflicts.sh --env-file .env repair --execute \
  --confirm 'REPAIR INVENTORY SLOT CONFLICTS'
```

The script refuses execution unless `hostname` matches
`DUNE_PRODUCTION_HOST`, which defaults to `kspls0`. Other installations can set
that variable or pass `--production-host NAME`. A deliberate lab repair can use
`--allow-non-production-host`; that flag must not route a production write
through the lab host.

Before opening the repair transaction, the tool writes a full custom-format
PostgreSQL dump under `backups/inventory-conflicts/<UTC timestamp>/`. The
directory also contains before/after findings, moved rows, and a manifest. An
empty or failed database dump stops execution.

Inside one transaction, repair:

1. locks `dune.items` against concurrent writes;
2. keeps the lowest-id row in every conflicting slot;
3. assigns every later row to the lowest available slot in the same inventory;
4. respects finite `max_item_count` values;
5. aborts without partial changes if capacity is insufficient;
6. never deletes an item; and
7. verifies that no duplicate slot remains before commit.

The transaction also aborts if an affected inventory belongs to a player whose
database status is online. Have the player return to the main menu and rerun.

If an explicitly reviewed special/full inventory cannot accept another item,
exclude it while repairing every other conflict:

```bash
./scripts/inventory-conflicts.sh --env-file .env repair --execute \
  --exclude-inventory 14 \
  --confirm 'REPAIR INVENTORY SLOT CONFLICTS'
```

`--exclude-inventory` accepts only numeric ids and may be repeated. Excluded
inventories stay visible in the after-audit and are recorded in the manifest;
the transaction verifies all non-excluded conflicts. Resolve excluded rows only
after identifying an appropriate inventory-type-specific destination.

The lock timeout is 15 seconds and statement timeout is 120 seconds. A busy
database causes a clean failure instead of waiting indefinitely.

## Recovery and validation

If gameplay validation fails, use the generated PostgreSQL dump with the
guarded restore workflow in [backup-strategy.md](backup-strategy.md). Do not
restore only `dune.items` from an ad hoc text dump: related and concurrent game
state may have advanced since repair.

```bash
./scripts/test-inventory-conflicts.sh
./scripts/inventory-conflicts.sh --env-file .env audit
```

The automated test proves dry-run behavior, exact confirmation, hostname
enforcement, mandatory non-empty backup, no-delete SQL, capacity abort logic,
and committed execution with a mocked database runtime.
