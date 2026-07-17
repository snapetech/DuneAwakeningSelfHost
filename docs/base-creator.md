# Portable Base Creator and Gallery

## Evidence boundary

DASH implements the working aggregate peer outcome: read-only live-base export,
portable reconstruction data, a browser grid editor, JSON download, gallery,
visibility, and ratings.

The surveyed Wormageddon source implements `base-export`, but its own
documentation says restore/import is experimental and "being finished"; the
command has no import implementation. The current Dune schema exposes
`base_backup_get_actors_to_spawn` and `base_backup_finish_placing`, but those are
parts of a game-orchestrated placement sequence, not an atomic database restore
contract. DASH therefore does not claim live restore. Confidence is **high** for
export/editor/gallery parity and **unknown** for direct live reconstruction.

## Live export

The Base Creator page lists live `building_instances` groups and their owner,
piece count, related-owner placeable count, sample type, and minimum health.
Export is read-only:

```http
GET /api/creator/bases?export=<building_id>
```

The `dash-base/1` archive contains:

- source building and owner identifiers;
- exact seven-value building transforms, flags, health, and type;
- exact placeable actor transforms, type, hologram state, map, partition, and
  dimension;
- a calculated centroid anchor;
- recentered relative transforms for portable reconstruction and design;
- piece/placeable counts, UTC export time, and SHA-256 digest;
- explicit `gameRestoreSupported=false` provenance.

Placeables are associated using the same owner-entity relationship used by the
working peer export. Exact transforms remain intact even when portable relative
coordinates are edited.

## Editor

The browser editor provides:

- a top-down coordinate-grid reconstruction preview;
- separate building-piece and placeable rendering;
- type, X/Y/Z, yaw, and configurable snap-size inputs;
- quaternion creation from yaw;
- add/remove/new actions;
- editable validated archive JSON;
- local draft persistence for page reloads;
- portable JSON download.

It never writes to the game database.

## Gallery and ratings

Gallery state is isolated at
`backups/base-gallery/gallery.sqlite3` (`0700` directory, `0600` database).
Designs support private, unlisted, and public visibility, bounded metadata,
version-neutral archive replacement, SHA-256 content identity, and created/
updated timestamps. Ratings are one 1–5 score per authenticated admin identity;
repeat rating updates the same identity row.

```http
GET  /api/creator/bases
GET  /api/creator/bases?design=<uuid>
POST /api/creator/bases {"action":"publish",...}
POST /api/creator/bases {"action":"rate",...}
POST /api/creator/bases {"action":"canary","confirm":"RUN CREATOR MODDING CANARY"}
```

Writes map to `creator.write`. Moderator, administrator, and owner roles receive
that capability by default. The gallery does not expose an unauthenticated
upload path.

## Creator and modding proof

The same page reports whether the current Creator/Modding input set has a
passing signed lifecycle receipt and can run the disposable proof. It exercises
base export, gallery publish/rate/update, recoverable-retirement guards, preset
apply/rollback, the seven-day Landsraad invariant, cosmetic planning, and the
SHA-pinned addon lifecycle without opening live creator/game state or invoking
a map or network operation. See
[`creator-modding-canary.md`](creator-modding-canary.md) for its exact input
binding, isolation contract, receipt verification, expiry, metrics, and backup
handling.

## Configuration

```dotenv
DUNE_BASE_CREATOR_ENABLED=true
DUNE_BASE_GALLERY_DATABASE=/workspace/backups/base-gallery/gallery.sqlite3
```

## Backup and restore

Full backups use SQLite's online backup API and integrity check to write
`base-gallery.sqlite3`. Verification checks the snapshot independently.
Restore is explicit and stops the admin-panel writer:

```bash
./scripts/restore-state.sh --base-gallery .env backups/<UTC timestamp>
```

The restore removes stale WAL/SHM files and installs mode `0600` state.

## Validation

```bash
make test-base-creator
make test-creator-canary
make validate
```

Tests cover exact transform preservation, recentering, unsupported-transform
rejection, publish/update/list/get/rate behavior, visibility validation,
component validation, bounds, and private file modes. The dashboard suite and
embedded JavaScript parser cover routing and rendering integration.

## Recoverable retirement

Base retirement is separate from portable reconstruction and does not claim a
direct live restore transaction. The Base Creator page can archive a stopped,
offline-owned base through the game's current-build
`dune.base_backup_save_from_totem` function after a fingerprint-bound preview,
full database dump, locks, and native result verification. This preserves an
in-game recovery record instead of deleting structural rows. See
[`base-retirement.md`](base-retirement.md) for the complete contract and
disposable live-canary procedure.
