# Character Cosmetics and Skins

## Outcome

DASH provides searchable character cosmetic inspection, exact add/remove,
bulk unlock of every enabled reviewed customization ID, and receipt rollback.
The browser page is **Cosmetics** and the API root is
`/api/admin/cosmetics`.

Confidence: **high** for the persistence contract and guardrails. The live
`dune_sb_1_4_10_0` schema was inspected read-only on 2026-07-15: 189 player
pawns exposed the expected component and their unlock arrays contained 391
distinct IDs. Confidence is **moderate** for whether every generated or
previously unseen ID renders in every future game build; catalog review remains
build/operator work.

## Peer and schema evidence

The aggregate parity audit pinned
[`the4rchangel/dune-awakening-server-manager`](https://github.com/the4rchangel/dune-awakening-server-manager)
at `749e77b8cdff7277460ef245eb0eccb858622a93`. Its implementation reads and
replaces this actor JSON path:

```text
CustomizationLibraryActorComponent
  .m_UnlockedCustomizationSerializableList
  .m_UnlockedCustomizationIds[]
  .m_CustomizationId
```

The current game schema exposes no cosmetic table or first-party cosmetic
mutation routine. DASH therefore labels this as a direct persistent actor edit
and does not imply a native API. The peer's source and catalog are evidence;
DASH does not copy its unlicensed catalog or its string-built SQL mutations.

The bundled [`config/cosmetic-catalog.json`](../config/cosmetic-catalog.json)
was independently generated from the production world's distinct observed
unlock IDs. It contains 391 customization IDs and no player identity. Inventory
tokens whose IDs begin with `Swatch_` are deliberately excluded: those are item
grants, not customization-library unlocks.

## Safety contract

Every persistent add, remove, bulk unlock, or rollback requires all of these:

1. the master `DUNE_ADMIN_MUTATIONS_ENABLED=true` gate;
2. `DUNE_ADMIN_COSMETIC_MUTATIONS_ENABLED=true`;
3. an authenticated identity with `players.write` (or the owner recovery
   token);
4. an exact confirmation phrase;
5. a target whose locked `player_state.online_status` is exactly `Offline`;
6. the expected actor component and array shape;
7. a successful full PostgreSQL custom-format backup;
8. a database row lock plus exact-property compare-and-swap;
9. post-write unlock-array hash verification; and
10. a private, tamper-evident receipt under
    `backups/admin-panel/cosmetics/receipts/`.

The admin container receives the active `DUNE_GAME_DB_NAME` explicitly as
`DUNE_ADMIN_DB_NAME`, `DUNE_GAME_DB_NAME`, and `DUNE_DATABASE`. Receipts record
that database and rollback refuses a receipt from any other database. This
prevents a stale image-default schema name from silently redirecting an admin
write or backup after an official database migration.

Add and remove accept only exact IDs that are enabled and marked
`unlockMode=customization` in the loaded catalog. Bulk unlock merges reviewed
IDs with existing state; it never deletes uncatalogued IDs. Remove deletes only
the selected exact ID. Repeating an add or remove is idempotent.

No server or map is restarted. The player must relog after a write so the game
reloads persistent actor state. If the player becomes Online after preview, the
locked execution check refuses the write.

## Browser workflow

1. Open **Cosmetics**.
2. Select a player and click **Inspect unlocks**.
3. Search by display label or exact ID, or filter by category.
4. Click **Add** or **Remove**. DASH previews the exact before/after counts and
   IDs before presenting the execution confirmation.
5. For a bulk grant, click **Preview unlock all**, review `added`, then click
   **Unlock all reviewed cosmetics**.
6. Have the player relog; a map restart is neither needed nor performed.

The page shows whether writes are enabled, current Online/Offline state, unlock
count, a truncated state hash, catalog provenance, and rollback receipts.

## API

Read catalog, receipts, and optionally one player's current state:

```http
GET /api/admin/cosmetics
GET /api/admin/cosmetics?pawn_id=12345
```

Preview uses a read-authorized route:

```json
POST /api/admin/cosmetics/preview
{
  "action": "add",
  "pawnId": 12345,
  "cosmeticId": "DyePack_Example"
}
```

Actions are `add`, `remove`, and `unlock-all`. Execute through the mutation
route:

```json
POST /api/admin/cosmetics
{
  "action": "add",
  "pawnId": 12345,
  "cosmeticId": "DyePack_Example",
  "confirm": "CHANGE PLAYER COSMETICS"
}
```

The response reports the database backup, receipt ID/SHA-256, before/after
hashes and counts, exact added/removed IDs, `verified=true`,
`restartRequired=false`, and `relogRequired=true`. Full before/after arrays are
kept in the private receipt and are not returned by the mutation API.

## Rollback

Select a receipt in the browser, or call:

```json
POST /api/admin/cosmetics
{
  "action": "rollback",
  "receiptId": "20260715T203000Z-0123456789abcdef",
  "confirm": "ROLL BACK PLAYER COSMETICS"
}
```

Rollback is not a blind overwrite. It refuses unless:

- the receipt name is a confined generated ID;
- the receipt document and embedded before/after hashes are valid;
- the same player is Offline under a database row lock; and
- current state equals the receipt's `afterHash`.

Execution creates another full database backup and an inverse receipt. If state
has changed since the original mutation, use the recorded full database backup
for deliberate recovery rather than forcing a stale receipt over newer state.

## Catalog generation and review

Build from an identity-free JSON array of observed IDs:

```bash
python3 scripts/build-cosmetic-catalog.py \
  --observed-json /path/to/observed-cosmetic-ids.json \
  --source local-schema-observation \
  --confidence high \
  --output config/cosmetic-catalog.json
```

An operator may also scan an operator-owned, locally installed `Systems.pak`
without changing the Steam client:

```bash
python3 scripts/build-cosmetic-catalog.py \
  --pak /path/to/DuneSandbox/Content/Paks/Systems.pak \
  --source local-systems-pak \
  --confidence moderate \
  --output /tmp/cosmetic-catalog.review.json
```

Pak discovery is heuristic. Review IDs, labels, categories, and unlock mode
before replacing the production catalog. Keep the checked-in catalog as the
last known-good rollback source. The builder excludes `Swatch_*` inventory
tokens from customization writes.

## Files and validation

- `admin/cosmetics_admin.py`: catalog validation, planning, locked writes,
  receipt storage, and rollback.
- `config/cosmetic-catalog.json`: reviewed bundled catalog.
- `scripts/build-cosmetic-catalog.py`: independent catalog builder.
- `scripts/test-cosmetics-admin.py`: catalog confinement, idempotency,
  preservation, bulk filtering, receipt permissions/tamper detection, and path
  confinement tests.
- `.env.example`, `compose.yaml`, `scripts/enable-feature-parity.sh`: feature
  gate definition, container propagation, and parity activation.

Run focused validation:

```bash
make test-cosmetics-admin
python3 -m unittest scripts/test-admin-panel-safe-surfaces.py
docker compose --env-file .env config >/dev/null
```

For a live canary, use an Offline test player and one already-owned reviewed ID:
preview an idempotent add, execute it, confirm `changed=false`, inspect the
unchanged state hash, and verify that a backup plus receipt were still recorded.
This validates the production gates and transaction path without changing game
state.

For non-player implementation proof, the Creator/Modding canary loads the exact
active catalog and runs add/replay/remove/unlock-all planning against synthetic
entries. It proves preservation and inventory-token exclusion without opening
the game database or writing a pawn; see
[`creator-modding-canary.md`](creator-modding-canary.md).
