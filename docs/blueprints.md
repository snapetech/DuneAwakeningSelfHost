# Blueprint Archives

The admin panel's **Blueprints** page provides the Red-Blink-equivalent Solido
blueprint workflow: list, export one or many, import, and delete. The archive
format preserves building instances, placeables, pentashield scale data, and
the original blueprint name.

## Read and export

`GET /api/admin/blueprints` reports schema capability and lists stored
blueprints. `GET /api/admin/blueprints?export=12,13` returns a versioned JSON
archive. The browser downloads either the selected rows or all visible rows.
Exports are bounded to 100 blueprint IDs per request.

## Import

Import accepts at most ten JSON files in one browser selection. Each request is
limited by `DUNE_ADMIN_BLUEPRINT_MAX_BODY_BYTES`, which defaults to 32 MiB.
The server validates row counts, finite coordinates/rotations, building-type
identifiers, unique archive-local IDs, pentashield references, scale values,
and the normalized blueprint name before planning a write. Zero-based archive
IDs are shifted consistently to positive database IDs.

A dry run resolves the offline player pawn, target inventory, available slot,
archive counts, and resulting name without writing. Execution requires:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
DUNE_ADMIN_BLUEPRINT_MUTATIONS_ENABLED=true
```

The exact confirmation phrase is `IMPORT BLUEPRINT`. Execution creates a
Postgres custom-format backup first, locks the player/inventory, rechecks that
the player is offline and capacity is available, deduplicates the blueprint
name, inserts the Solido item and blueprint rows in one transaction, verifies
the stored row counts, and commits only after verification.

## Delete

Deletion first exports the complete rollback archive. A dry run returns that
archive without writing. Execution requires the same gates, a database backup,
and `DELETE BLUEPRINT`. The owner must be offline. Dependent instance,
placeable, and pentashield rows plus the associated Solido inventory item are
deleted in one transaction and absence is verified before commit. The response
contains the archive needed for manual re-import.

The implementation is in `admin/blueprint_admin.py`; safe-surface tests cover
archive validation, inventory planning, route registration, mutation gates,
and backup-before-write behavior.
