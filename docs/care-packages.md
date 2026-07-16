# Care Packages

DASH Admin supports reviewed, reusable care-package presets backed by the
existing guarded economy-bundle and item-grant primitives. Packages can be
granted manually or by persistent first-online and returning-player rules.

## Configuration

Presets live in [`config/care-packages.json`](../config/care-packages.json).
The committed starter preset is disabled and exists only as a schema example.

```json
{
  "schemaVersion": 2,
  "automatic": {
    "enabled": false,
    "intervalSeconds": 60,
    "rules": [
      {
        "id": "starter-first-online",
        "enabled": false,
        "packageId": "starter-tools",
        "grantWhen": "first_online",
        "lastSeenDays": 30
      }
    ]
  },
  "packages": [
    {
      "id": "starter-tools",
      "label": "Starter Tools",
      "description": "One reviewed package per account.",
      "enabled": false,
      "oncePerAccount": true,
      "cooldownHours": 0,
      "items": [
        {
          "template_id": "BasicBuildingTool",
          "stack_size": 1,
          "quality_level": 0,
          "stats": {}
        }
      ],
      "currency": [
        {"currency_id": 1, "amount": 500, "mode": "add"}
      ],
      "xp": [
        {"track_type": "Combat", "amount": 100, "mode": "add"}
      ]
    }
  ]
}
```

Constraints:

- package ids use lowercase letters, digits, `_`, or `-` and are unique;
- at most 100 packages are loaded;
- each package is limited to 50 item, 20 currency, and 20 XP actions;
- `items`, `currency`, and `xp` must be arrays of objects;
- package-supplied inventory, account, and player/controller targets are
  ignored and replaced with the selected player's identifiers;
- empty packages are rejected;
- disabled packages may be previewed but cannot execute.
- automatic intervals are bounded from 60 to 3600 seconds;
- at most 24 uniquely named automatic rules are accepted;
- rules must reference an existing package and use `first_online` or
  `last_seen`; `last_seen` eligibility persists until the player returns.

Confirm every template, currency id, specialization track, quantity, quality,
and structured `stats` payload against the current server build before
enabling a preset.

## Admin Page

Open:

```text
http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/care-packages
```

The page lists configured presets and grant history. Select a package and
player, then preview before considering execution. The automatic section can
preview/run eligibility, retry the latest failed grant, clear visible history
without removing claims, and edit the complete validated JSON catalog. Every
catalog save creates a timestamped backup.

## API

Catalog and history:

```http
GET /api/admin/care-packages
```

Preview:

```http
POST /api/admin/care-packages
Content-Type: application/json

{
  "package_id": "starter-tools",
  "account_id": 123,
  "dry_run": true
}
```

Automatic eligibility preview:

```json
{"action": "scan", "dry_run": true}
```

Execution adds `"confirm": "RUN CARE PACKAGE SCAN"`. Retry uses
`RETRY CARE PACKAGE`; history clearing uses `CLEAR GRANT HISTORY`.

Execution:

```json
{
  "package_id": "starter-tools",
  "account_id": 123,
  "dry_run": false,
  "confirm": "GRANT CARE PACKAGE"
}
```

## Execution Gates

Execution requires all applicable gates:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true
DUNE_ADMIN_CARE_PACKAGES_ENABLED=true
DUNE_ADMIN_CARE_PACKAGES_AUTO_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
```

`DUNE_ADMIN_ITEM_GRANTS_ENABLED` is required only when the package contains
items, but keeping it false blocks all item insertion globally.

The automatic gate is independent. Keep it false for manual-only operation.
The worker also requires the master, bundle, and care-package gates. Compose
passes both care-package gates into the container and exposes them in the
guarded `.env` editor.

## Eligibility, Backup, and History

Preview reports package eligibility and blockers. Execution refuses:

- disabled packages;
- a second successful grant when `oncePerAccount=true`;
- grants before a configured `cooldownHours` period expires;
- missing player/controller identities needed by currency or XP actions;
- any package whose bundle preview fails existing item/inventory checks.

Before execution, DASH creates a Postgres custom-format backup using the same
admin backup primitive as the Admin Actions page. It then passes the reviewed
package through `economy_bundle`, which preserves the master mutation, bundle,
and item-grant gates.

Successful grants append a bounded, non-secret record to:

```text
backups/admin-panel/care-package-history.jsonl
```

Persistent automatic state is kept in:

```text
backups/admin-panel/care-package-first-online-claims.json
backups/admin-panel/care-package-pending-returns.json
```

Claims are reserved before a grant and survive restarts. Failure releases the
claim for a later scan or retry. Clearing visible history preserves claims so
it cannot bypass duplicate prevention.

The record contains package id, account id, character name, backup path, action
counts, result status, and timestamp. It does not copy item stats, credentials,
or database contents.

The bundle is not one SQL transaction across currency, XP, and item actions.
If a later action fails, inspect the audit/history result and restore or apply
compensating changes from the pre-grant backup.

## Validation

```bash
python3 -m json.tool config/care-packages.json >/dev/null
python3 scripts/test-admin-panel-safe-surfaces.py
docker compose --env-file .env.example config --quiet
```

Tests cover target rewriting, dry-run planning, layered execution gates,
automatic pre-grant backup, confirmation forwarding, history recording,
disabled-package refusal, duplicate first-online scans, and persisted
returning-player eligibility.
