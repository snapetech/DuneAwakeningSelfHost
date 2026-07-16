# Structured Item Augments

The **Admin Actions** page supports both pre-augmented item grants and applying
augments to an existing player-owned item. Compatibility metadata is pinned to
the Red-Blink audit source in `config/augment-compatibility.json`; its MIT
license is recorded in `THIRD_PARTY_NOTICES.md`.

## Compatibility and stat construction

`GET /api/admin/augments?template_id=<id>` returns the item kind, inferred game
tags, compatible augment templates, effect summaries, and slot limit. Clothing
accepts two augments and weapons accept three. The server rejects unknown,
duplicate-expanded, over-limit, or tag-incompatible selections even if a
request bypasses the browser.

The structured writer preserves unrelated item stats, removes legacy augment
tokens from `FCustomizationStats`, supplies missing durability/weapon base
stats, and writes `FAugmentedItemStats`. Roll payloads are taken from observed
standalone or already-augmented local items when available and normalized to
perfect rolls; the pinned compatibility catalog supplies a bounded fallback.
Grades are restricted to 1 through 5.

## Required player unlocks

Applying augments also grants the slot keystones needed by the target item:

- clothing: keystones 42 and 43;
- melee weapons: 44 through 46;
- ranged weapons: 47 through 49;
- ambiguous weapon mappings: all six weapon slot keystones.

When the schema supports it, the transaction also raises the Crafting
specialization baseline to at least 3100 XP / level 19.338913. Existing higher
values are preserved. Keystone presence is verified before commit.

## Mutation workflow

Preview is available with mutations disabled. Execution requires:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
DUNE_ADMIN_AUGMENT_MUTATIONS_ENABLED=true
```

The existing-item confirmation is `APPLY AUGMENTS`; a pre-augmented grant uses
`GRANT AUGMENTED ITEM`. Both require a directly owned inventory and an offline
owner. Both create a database backup before the write. Existing-item updates
and pre-augmented grants run in a database transaction with inventory/item
locks, capacity or ownership checks, slot unlocks, exact stat verification,
and rollback on any failure.

Implementation lives in `admin/augment_admin.py`. The safe-surface suite tests
catalog compatibility, limits, stat shape, dry-run routing, gates, and backup
ordering.
