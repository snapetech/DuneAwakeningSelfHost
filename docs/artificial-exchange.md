# Artificial Exchange

This feature adds an operator-controlled artificial Exchange layer for Dune
Awakening self-hosts. It has three separate jobs:

- build a reviewed item price catalog
- buy eligible player listings through the native Exchange fulfill path
- optionally seed NPC listings from reviewed catalog rows

All write paths are gated. The default service state is enabled in dry-run mode,
with purchases, funding, settlement claim, and populator writes disabled.

Confidence levels:

- Catalog building and dry-run scans: high.
- Live native purchase for the tested `PowerPack` path: high.
- Safe seller Solari settlement through the validated direct transaction: high
  for completed seller Solari claim rows matching the tested shape.
- Broad item coverage and unattended economy tuning: moderate until more
  templates are reviewed.
- Native `dune_exchange_retrieve_solaris_from_item(...)`: low and not used by
  the bot because this server build showed unsafe behavior.

## Components

Files:

- `config/artificial-exchange-prices.csv`: reviewed manual catalog rows.
- `scripts/build-exchange-catalog.py`: catalog builder.
- `scripts/import-awakening-wiki-items.py`: imports Community Wiki API item
  metadata and game-file-derived prices into a snapshot CSV.
- `scripts/research-exchange-prices.py`: crawls Awakening Wiki page wikitext
  and extracts exact item ids with `Base Vendor Price` fields.
- `scripts/build-exchange-bootstrap-catalog.py`: heuristic broad catalog builder
  from locally observed templates.
- `scripts/artificial-exchange-bot.py`: buyer, settlement, funding, readiness,
  and populator CLI.
- `scripts/artificial-exchange-smoke.sh`: safe end-to-end smoke check.
- `scripts/install-artificial-exchange-service.sh`: systemd unit renderer.
- `scripts/test-artificial-exchange.py`: offline catalog/bot unit tests.
- `scripts/test-artificial-exchange-service.sh`: systemd render tests.
- `config/systemd/dune-artificial-exchange-bot.service`: systemd template.
- `docs/artificial-exchange.md`: this runbook.

Generated local state:

- `backups/admin-panel/artificial-exchange/catalog.json`
- `backups/admin-panel/artificial-exchange/catalog.csv`
- `backups/admin-panel/artificial-exchange/<timestamp>-catalog.json`
- `backups/admin-panel/artificial-exchange/bot-audit.jsonl`
- `backups/admin-panel/artificial-exchange/bot-state.json`

The generated state lives under `backups/` and is ignored by git.

## DuneAdmin Panel

The DuneAdmin dashboard exposes Artificial Exchange operations under
`Settings -> Artificial Exchange`.

The panel can:

- show catalog counts, readiness checks, and buyer/populator systemd state
- rebuild `backups/admin-panel/artificial-exchange/catalog.json`
- run `--check-ready`
- run a buyer dry-run scan with expanded skip reporting
- render a settlement report
- run the disposable populator validation path
- install, start, stop, and restart the buyer and populator systemd services
- edit every `DUNE_ARTIFICIAL_EXCHANGE_*` `.env` setting through the safe
  Settings editor

The backend endpoints are:

```text
GET  /api/admin/artificial-exchange
POST /api/admin/artificial-exchange
```

The POST body is:

```json
{"action":"check-ready"}
```

Supported actions:

```text
build-catalog
check-ready
buyer-dry-run
settlement-report
validate-populator
install-buyer-service
install-populator-service
start:buyer
stop:buyer
restart:buyer
status:buyer
start:populator
stop:populator
restart:populator
status:populator
```

Service actions require `systemctl` in the runtime where the admin panel is
running. When the panel runs inside the Compose container without host systemd
access, those actions fail cleanly and the response explains that `systemctl`
is unavailable. The setting editor still works in that mode; restart the host
services from the host after saving `.env` changes.

## Database Surfaces

Read surfaces:

- `dune.dune_exchange_orders`
- `dune.dune_exchange_sell_orders`
- `dune.dune_exchange_fulfilled_orders`
- `dune.dune_exchange_users`
- `dune.items`
- `dune.inventories`
- `dune.player_state`
- `dune.player_virtual_currency_balances`
- `dune.get_solaris_id()`
- Exchange function signatures from `pg_proc`

Native write functions used:

- `dune.dune_exchange_fulfill_sell_order(...)` for purchases.
- `dune.dune_exchange_modify_user_solari_balance(...)` for explicit buyer
  funding.
- `dune.dune_exchange_update_recurring_sell_order(...)` for populator listing
  creation.
- `dune.save_item(...)` and `dune.advance_items_id_sequencer(...)` for
  populator staging items.
- `dune.dune_exchange_expire_orders(...)` when seeded-order expiry is requested
  and the native function exists.

Direct SQL writes used:

- settlement creates missing base Solaris rows in
  `player_virtual_currency_balances`
- settlement updates that balance by the exact completed claim value
- settlement deletes the completed seller claim order after validation
- seeded-order cleanup deletes only owner-scoped, Exchange-scoped,
  `is_npc_order=true` rows

Native write function deliberately not used:

- `dune.dune_exchange_retrieve_solaris_from_item(...)`

Reason: live validation showed unsafe behavior on this server build.

## Data Model

Catalog fields:

```csv
template_id,display_name,category,category_mask,category_depth,sellable_status,baseline_price,max_buy_price,liquidity_tier,enabled,source,confidence,notes
```

Meaning:

- `template_id`: item template id used by Dune DB rows.
- `display_name`: human label for operators.
- `category`: operator grouping only.
- `category_mask` and `category_depth`: native Exchange category filter values
  used when seeding or validating category counts.
- `sellable_status`: expected values are `known`, `observed`, or `validated`.
- `baseline_price`: reference market price.
- `max_buy_price`: highest price the artificial buyer may pay.
- `liquidity_tier`: `low`, `medium`, or `high`; controls buy probability.
- `enabled`: only `true` rows are eligible for buying or seeding.
- `source`: `manual`, `snapshot`, `local-db`, `live-test`, or similar.
- `confidence`: `low`, `moderate`, or `high`.
- `notes`: operator comments.

The old one-row `PowerPack` live-test catalog entry is disabled. It remains
only as a historical validation record and must not be used as the production
seed source.

## Catalog Pipeline

Build without DB:

```bash
python3 scripts/build-exchange-catalog.py --no-db
```

Refresh the broad community/game-file snapshot first:

```bash
python3 scripts/import-awakening-wiki-items.py
python3 scripts/build-exchange-catalog.py --no-db
```

Promote the imported game-file rows for full population:

```bash
python3 scripts/import-awakening-wiki-items.py \
  --enabled \
  --sellable-status validated \
  --source awakening-wiki-game-files-full-populate \
  --confidence moderate \
  --output /tmp/awakening-wiki-full-populate.csv
```

Research exact wiki page vendor prices:

```bash
python3 scripts/research-exchange-prices.py \
  --crawl-allpages \
  --no-search-fallback \
  --output data/exchange-price-snapshots/wiki-base-vendor-prices.csv
python3 scripts/build-exchange-catalog.py --no-db
```

Build with live DB observations:

```bash
python3 scripts/build-exchange-catalog.py
```

Sources, in priority order:

- manual rows from `config/artificial-exchange-prices.csv`
- imported CSV snapshots under `data/exchange-price-snapshots/*.csv`
- local DB observations from `dune_exchange_orders` and
  `dune_exchange_sell_orders`

Manual rows override everything else. Snapshot rows are grouped by template and
use median pricing, with moderate confidence after at least three observations.
DB-observed rows are disabled until reviewed.

The `awakening-wiki-items.csv` snapshot is sourced from
`https://api.awakening.wiki/items`. The API describes itself as Community Wiki
data sourced from game files. Imported rows use `market_price` first and
`base_vendor_price` as a fallback, remain `enabled=false`, and should be treated
as broad reference coverage rather than reviewed live-market prices.

The `wiki-base-vendor-prices.csv` snapshot is sourced from wiki page wikitext at
`https://awakening.wiki`. The extractor only accepts pages that expose an exact
`ITEMID` marker and a numeric `Base Vendor Price` field. Confidence: high for
the extracted price matching the wiki page, moderate for whether that price is
the right player-market baseline without operator review. Example source pages
validated during development: `Plant Fiber`, `Power Pack Mk1`, and
`Scrap Metal Knife`.

Validation behavior:

- duplicate manual/snapshot template ids fail
- malformed prices fail
- unknown confidence values fail
- unknown liquidity tiers fail
- missing `enabled` defaults to false

## Buyer

The buyer scans Exchange sell orders and selects eligible listings. Normal scans
skip:

- NPC orders
- configured populator owner ids
- templates missing from the catalog
- disabled catalog rows
- blocked sellers
- prices above `max_buy_price`
- orders exceeding global, seller, or template daily caps
- randomized probability skips by liquidity tier
- stale order revisions

The buyer uses the native fulfill function:

```sql
dune.dune_exchange_fulfill_sell_order(
  in_exchange_id,
  in_max_orders_per_player,
  in_purchased_completion_type,
  in_sold_completion_type,
  in_instigator_id,
  in_order_id,
  in_order_revision,
  in_dst_inventory_id,
  in_dst_index,
  in_count,
  in_solaris_fee,
  in_purge_time
)
```

The bot passes the actual `dune_exchange_orders.revision`; it does not use
PostgreSQL `xmin`.

Dry-run scan:

```bash
DUNE_ARTIFICIAL_EXCHANGE_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py --dry-run
```

Apply one scan:

```bash
DUNE_ARTIFICIAL_EXCHANGE_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN=false \
DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py \
  --apply \
  --buyer-controller-id 17 \
  --confirm "RUN ARTIFICIAL EXCHANGE"
```

Loop:

```bash
python3 scripts/artificial-exchange-bot.py --loop
```

## Buyer Funding

Native purchases spend the buyer controller's Exchange Solari balance
(`dune_exchange_users.solari_balance`). This is separate from the base Solaris
row in `player_virtual_currency_balances`.

Check readiness and buyer balance:

```bash
python3 scripts/artificial-exchange-bot.py --check-ready --buyer-controller-id 17
```

Fund the buyer Exchange balance:

```bash
DUNE_ARTIFICIAL_EXCHANGE_FUNDING_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py \
  --buyer-controller-id 17 \
  --fund-buyer 10000 \
  --confirm "FUND ARTIFICIAL EXCHANGE"
```

Funding uses:

```sql
dune.dune_exchange_modify_user_solari_balance(controller_id, delta)
```

The command writes a `buyer-funded` audit event. It is intentionally separate
from buying and settlement.

## Settlement

Completed orders are visible through:

```bash
python3 scripts/artificial-exchange-bot.py --settlement-report
```

Statuses:

- `purchased_item_storage`: completed purchased item stored in Exchange storage.
- `seller_solari_claim_ready`: seller Solari claim with a base Solaris balance
  row already present.
- `unsafe_missing_base_solaris_balance`: seller claim where the base Solaris
  row is absent; the bot can repair this safely during claim.
- `seller_claim_has_item_id`: not a normal seller Solari claim.
- `unknown_completion_type`: unrecognized completion type.

Native retrieve warning:

`dune_exchange_retrieve_solaris_from_item(...)` is not used. On this server build
it attempted to set `player_virtual_currency_balances.balance` to `NULL` and
failed a not-null constraint. In rollback testing it also showed it could delete
the claim row without crediting when the base Solaris row was missing.

The bot uses a direct validated transaction for seller Solari claims:

- create missing base Solaris row at balance `0`
- lock the completed seller claim
- verify owner, completion type, item id, stack size, and expected Solari
- credit exactly `item_price * stack_size`
- delete the completed claim order
- verify the claim row is gone
- commit only if every check passes
- rollback on any mismatch

Claim one order:

```bash
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py \
  --claim-settlement 7 \
  --confirm "CLAIM ARTIFICIAL EXCHANGE"
```

Claim all eligible seller claims in the report limit:

```bash
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py \
  --claim-all-settlements \
  --confirm "CLAIM ARTIFICIAL EXCHANGE"
```

Auto-claim after each scan:

```bash
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN=true \
  python3 scripts/artificial-exchange-bot.py --loop
```

Auto-claim after scan does not require the manual confirmation phrase because it
is controlled by explicit environment gates and still uses the same validated
transaction.

## Populator

The populator seeds NPC Exchange listings from enabled catalog rows. By default
it only uses rows with `sellable_status=validated`, jitters prices around
`baseline_price`, gives listings a jittered expiration, and refuses to seed the
lowest observed item grade (`quality_level=0`).

Known grade boundary:

- The local Exchange and item tables expose numeric `quality_level` values.
- The tooling observed and can create `quality_level=0` and `quality_level=1`.
- The catalog/import metadata exposes tier markers through at least tier `6`.
- Operational answer: there are at least seven numeric quality/tier buckets if
  counting `0` through `6`; the populator minimum is set to `1`, so it skips the
  lowest bucket by default. Confidence: moderate because the DB stores numeric
  levels but does not include a canonical grade-name table.

Current category limitation:

- The live `dune_exchange_categories_hash` table currently exposes only integer
  hashes, not category names or a hierarchy.
- `try_update_exchange_categories_hash(...)` shows that category mappings are
  normally supplied by the game/client through `update_sell_orders_categories`.
- The bootstrap catalog therefore uses deterministic server-side category masks
  and depths. Native DB filtering through `get_exchange_sell_orders(... mask,
  depth)` works with those masks. Confidence: high.
- Whether the live game UI labels those exact masks as the expected category
  names depends on the client category tree. Confidence: moderate until observed
  in-client.

Single-template safety:

- Listings are NPC orders with `is_npc_order=true`.
- The buyer skips NPC orders and configured populator owners by default.
- The populator avoids duplicate active prices for the same template in one run
  so native recurring-order merging does not silently turn requested listings
  into fewer active orders.
- Apply mode fails if the native recurring sell function reports that no
  inventory was added.

Dry-run one populate pass:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py --populate-once
```

Apply one populate pass:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN=false \
  python3 scripts/artificial-exchange-bot.py \
  --populate-once \
  --apply \
  --populator-owner-id 17 \
  --populator-source-inventory-id 485 \
  --confirm "POPULATE ARTIFICIAL EXCHANGE"
```

Run the populator loop:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py --populate-loop
```

Populate to a minimum per available catalog subcategory:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py \
  --populate-categories-once \
  --populator-owner-id 17 \
  --populator-source-inventory-id 485 \
  --populator-target-min-orders 20
```

Apply mode:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN=false \
  python3 scripts/artificial-exchange-bot.py \
  --populate-categories-once \
  --apply \
  --populator-owner-id 17 \
  --populator-source-inventory-id 485 \
  --populator-target-min-orders 20 \
  --confirm "POPULATE ARTIFICIAL EXCHANGE"
```

Populate one listing for every enabled catalog template that is not already
seeded:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN=true \
  python3 scripts/artificial-exchange-bot.py \
  --populate-all-once \
  --populator-owner-id 17 \
  --populator-source-inventory-id 485
```

Apply mode:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN=false \
  python3 scripts/artificial-exchange-bot.py \
  --populate-all-once \
  --apply \
  --populator-owner-id 17 \
  --populator-source-inventory-id 485 \
  --confirm "POPULATE ARTIFICIAL EXCHANGE"
```

Run expiry and over-cap cleanup for seeded NPC listings:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py --expire-seeded
```

Cleanup is scoped to:

- target exchange id
- configured populator owner id
- `is_npc_order=true`

It does not select human orders.

Run a guarded one-listing validation:

```bash
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_LIVE_VALIDATION_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py \
  --validate-populator-once \
  --populator-owner-id 17 \
  --populator-source-inventory-id 485
```

With default dry-run behavior this reports the planned listing. With `--apply`
and `--confirm "POPULATE ARTIFICIAL EXCHANGE"`, it creates exactly one seeded
NPC listing at a validation-only price, runs a buyer dry-run scan to confirm the
new order is skipped, then deletes only the newly-created seeded order id.

The buyer skips NPC orders and populator-owned orders by default, so it does not
buy its own seeded liquidity. Use `--include-npc-test-orders` only for controlled
validation.

## Environment Reference

Global buyer:

```env
DUNE_ARTIFICIAL_EXCHANGE_ENABLED=true
DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN=true
DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_ID=2
DUNE_ARTIFICIAL_EXCHANGE_ACCESS_POINT_ID=1
DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID=0
DUNE_ARTIFICIAL_EXCHANGE_SCAN_LIMIT=200
DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MIN_SECONDS=180
DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MAX_SECONDS=420
```

Budgets and probabilities:

```env
DUNE_ARTIFICIAL_EXCHANGE_DAILY_SOLARI_CAP=50000
DUNE_ARTIFICIAL_EXCHANGE_DAILY_SELLER_CAP=10000
DUNE_ARTIFICIAL_EXCHANGE_DAILY_TEMPLATE_CAP=15000
DUNE_ARTIFICIAL_EXCHANGE_LOW_BUY_PROBABILITY=0.08
DUNE_ARTIFICIAL_EXCHANGE_MEDIUM_BUY_PROBABILITY=0.18
DUNE_ARTIFICIAL_EXCHANGE_HIGH_BUY_PROBABILITY=0.35
DUNE_ARTIFICIAL_EXCHANGE_BLOCKED_SELLERS=
```

Settlement and funding:

```env
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN=false
DUNE_ARTIFICIAL_EXCHANGE_FUNDING_ENABLED=false
```

Populator:

```env
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN=true
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_LIVE_VALIDATION_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID=0
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_IDS=
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID=0
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_POSITION_START=0
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_POSITION_MAX=100000
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MIN_ORDERS=20
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MAX_ORDERS=80
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_PRICE_JITTER_PCT=20
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRY_MIN_SECONDS=3600
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRY_MAX_SECONDS=86400
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRE_PROBABILITY=0.10
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_FORCE_COUNT=
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_VALIDATION_PRICE=
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_VALIDATED=true
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_STACK_SIZE=1
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MAX_STACK_SIZE=1
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CATEGORY_MASK=0
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CATEGORY_DEPTH=0
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DURABILITY_CUR=1
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DURABILITY_MAX=1
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MIN_QUALITY_LEVEL=1
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_QUALITY_LEVEL=1
```

## Bootstrap Catalog

Generate a broad heuristic catalog from locally observed templates:

```bash
python3 scripts/build-exchange-bootstrap-catalog.py --limit-per-category 20
python3 scripts/build-exchange-catalog.py
```

The bootstrap builder reads templates from:

- `dune.items`
- `dune.vehicle_modules`
- `dune.landsraad_house_rewards`
- `dune.landsraad_task_rewards`

It skips obvious non-market entries:

- emotes
- contract items
- SolarisCoin
- swatches and dye packs
- building blueprints
- known internal/test-looking ids

It classifies by template-id heuristics into these subcategories:

- `resources/raw`
- `resources/refined`
- `resources/components`
- `consumables/medical`
- `tools/mining`
- `tools/utility`
- `weapons/melee`
- `weapons/ranged`
- `armor/combat`
- `armor/stillsuit`
- `armor/social`
- `vehicles/sandbike`
- `vehicles/ornithopter`
- `vehicles/parts`
- `schematics/weapons`
- `schematics/armor`
- `schematics/vehicles`

The generated rows are marked:

- `sellable_status=observed`
- `enabled=false`
- `source=local-bootstrap`
- `confidence=low`

That means they are discovery placeholders only. Prices are heuristic category
defaults with simple tier multipliers and are not production prices. Confidence:
low. Do not use them for live market seeding.

There is an explicit unsafe override:

```bash
python3 scripts/build-exchange-bootstrap-catalog.py --enable-heuristic-prices
```

That marks heuristic rows as enabled and validated. Use it only for isolated
test servers, never for the real market population.

## Services

Render/install buyer service:

```bash
make install-artificial-exchange-buyer-service ENV_FILE=.env
```

Render/install populator service:

```bash
make install-artificial-exchange-populator-service ENV_FILE=.env
```

Direct installer syntax:

```bash
scripts/install-artificial-exchange-service.sh .env /etc/systemd/system/dune-artificial-exchange-bot.service buyer
scripts/install-artificial-exchange-service.sh .env /etc/systemd/system/dune-artificial-exchange-populator.service populator
```

The service unit:

- reads the selected `EnvironmentFile`
- runs `build-exchange-catalog.py` as `ExecStartPre`
- runs either buyer loop or populator loop
- does not hardcode artificial Exchange gates
- enables at boot and starts immediately when installed under
  `/etc/systemd/system`
- uses `Restart=always` so it comes back after process crashes

Prefer buyer and populator as separate services for clearer operations. The
installer also supports `both` for a combined process when explicitly selected.

## Command Reference

Catalog:

```bash
python3 scripts/build-exchange-catalog.py
python3 scripts/build-exchange-catalog.py --no-db
python3 scripts/build-exchange-catalog.py --manual config/artificial-exchange-prices.csv --snapshot-dir data/exchange-price-snapshots
```

Inspection:

```bash
python3 scripts/artificial-exchange-bot.py --check-ready
python3 scripts/artificial-exchange-bot.py --settlement-report
```

Buyer:

```bash
python3 scripts/artificial-exchange-bot.py --dry-run
python3 scripts/artificial-exchange-bot.py --loop
python3 scripts/artificial-exchange-bot.py --apply --buyer-controller-id <id> --confirm "RUN ARTIFICIAL EXCHANGE"
```

Settlement:

```bash
python3 scripts/artificial-exchange-bot.py --claim-settlement <order_id> --confirm "CLAIM ARTIFICIAL EXCHANGE"
python3 scripts/artificial-exchange-bot.py --claim-all-settlements --confirm "CLAIM ARTIFICIAL EXCHANGE"
```

Funding:

```bash
python3 scripts/artificial-exchange-bot.py --buyer-controller-id <id> --fund-buyer <amount> --confirm "FUND ARTIFICIAL EXCHANGE"
```

Populator:

```bash
python3 scripts/artificial-exchange-bot.py --populate-once
python3 scripts/artificial-exchange-bot.py --populate-loop
python3 scripts/artificial-exchange-bot.py --populate-categories-once
python3 scripts/artificial-exchange-bot.py --populate-all-once
python3 scripts/artificial-exchange-bot.py --expire-seeded
```

Test-order escape hatch:

```bash
python3 scripts/artificial-exchange-bot.py --include-npc-test-orders --dry-run
```

Use the escape hatch only for controlled validation. It bypasses the normal NPC
and populator-owner buyer skips.

## Smoke Checks

Safe full smoke check:

```bash
make artificial-exchange-smoke
```

It runs:

- catalog rebuild
- readiness check
- settlement report
- buyer dry-run scan
- populator dry-run plan if `DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID` is set
- service render validation

Standard repo validation:

```bash
make validate
```

Artificial Exchange-specific tests:

```bash
python3 scripts/test-artificial-exchange.py
./scripts/test-artificial-exchange-service.sh
python3 -m py_compile scripts/artificial-exchange-bot.py scripts/build-exchange-catalog.py
```

## Logging

The bot writes structured JSON events to stdout/stderr for `journalctl` and
important state transitions to:

```bash
backups/admin-panel/artificial-exchange/bot-audit.jsonl
```

Systemd sets `PYTHONUNBUFFERED=1`, so service logs are emitted immediately.

Follow the buyer service:

```bash
journalctl -u dune-artificial-exchange-bot.service -f
```

Inspect recent failures and restarts:

```bash
systemctl status dune-artificial-exchange-bot.service --no-pager --lines=80
journalctl -u dune-artificial-exchange-bot.service -n 200 --no-pager
```

Useful event names:

- `bot-start`: process start and CLI mode.
- `loop-iteration-start`: each buyer/populator loop pass.
- `scan-start` and `scan-complete`: buyer scan boundaries and counts.
- `catalog-loaded`: catalog path and enabled item count.
- `db-connect-attempt` and `db-connect-ok`: database connection target/result.
- `purchase-attempt` and `purchase-result`: live purchase execution.
- `settlement-claim-start` and `settlement-claim-complete`: manual claim path.
- `settlement-auto-claim-start` and `settlement-auto-claim-complete`: auto-claim
  pass.
- `populate-start` and `populate-complete`: populator pass.
- `loop-iteration-failed`: exception inside a service loop iteration.
- `bot-fatal`: top-level crash; includes exception type and traceback.

The audit JSONL file records purchase selections, settlement observations,
claim results, funding events, populator plans, and failure payloads. Use it
when journald has rotated:

```bash
tail -n 100 backups/admin-panel/artificial-exchange/bot-audit.jsonl
```

## Live Validation Record

Validated on May 20, 2026:

- Exchange id: `2`
- Access point id: `1`
- Test order: `5`
- Template: `PowerPack`
- Price: `123`
- Owner/controller: `17`

Purchase result:

- dry-run selected order `5`
- apply mode bought order `5`
- native fulfill returned `item_id=33256527`
- original sell order `5` was removed
- purchased item storage order `6` was created
- seller Solari claim order `7` was created
- buyer Exchange balance returned to `0`

Settlement result:

- native retrieve was rejected as unsafe after failed validation
- direct validated settlement credited controller `17` exactly `123` base Solaris
- claim order `7` was deleted
- purchased item storage order `6` remains

Current known live state after final service validation:

- active seeded NPC orders: `20`
- active player orders selected by buyer: `0`
- completed purchased-item storage order `6`
- no pending seller claim rows
- no unsafe settlement rows
- controller `17` base Solaris balance `0` after buyer funding
- buyer Exchange balance `123`
- active seeded item rows are in Exchange inventory `485`
- stale orphaned Exchange inventory items from earlier bad staging tests were
  purged

Category populate run on May 21, 2026:

- backup before category populate:
  `backups/admin-panel/artificial-exchange/live-runs/20260521T022133Z-before-category-populate.sql`
- generated bootstrap catalog rows: `151`
- active seeded NPC orders after apply: `340`
- seeded categories: `17`
- target per category: `20`
- minimum quality: `1`
- rows below minimum quality: `0`
- buyer dry-run selected: `0`
- buyer dry-run skipped seeded orders: `340`, all via `npc order skipped`

Final service validation on May 20, 2026 local time:

- `config/artificial-exchange-prices.csv` contains a broad disabled catalog and
  a reviewed enabled seed subset of `20` rows.
- `build-exchange-catalog.py` rebuilt a catalog with `2278` known rows and `20`
  enabled rows.
- `dune-artificial-exchange-bot.service` and
  `dune-artificial-exchange-populator.service` were both enabled and active.
- Both units use `Restart=always` and `RestartSec=15s`.
- Both units were killed with `SIGKILL`; systemd restarted both automatically.
- After restart, `NRestarts=1` for both units, `ActiveState=active`, and
  `UnitFileState=enabled`.
- The buyer loop skipped all `20` seeded NPC orders and selected `0`.
- The populator preflight passed, saw `20` active seeded orders, planned `0`,
  and deleted `0`.
- Cleanup was fixed to preserve
  `DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MIN_ORDERS`.
- Cleanup now deletes the selected order rows first, then deletes only unreferenced
  staged items from the native Exchange inventory.
- Earlier orphaned staging items were purged after verifying no active order
  referenced them.

Price research run after rollback:

- `scripts/research-exchange-prices.py --crawl-allpages --no-search-fallback`
  crawled Awakening Wiki mainspace pages in revision batches.
- Extracted exact wiki price records: `1259`.
- Matched locally observed seedable templates: `121`.
- Missed locally observed seedable templates: `30`.
- Output:
  `data/exchange-price-snapshots/wiki-base-vendor-prices.csv`.

Verified category counts:

| Category | Orders | Native mask filter count |
| --- | ---: | ---: |
| `armor/combat` | 20 | 20 |
| `armor/social` | 20 | 20 |
| `armor/stillsuit` | 20 | 20 |
| `consumables/medical` | 20 | 20 |
| `resources/components` | 20 | 20 |
| `resources/raw` | 20 | 20 |
| `resources/refined` | 20 | 20 |
| `schematics/armor` | 20 | 20 |
| `schematics/vehicles` | 20 | 20 |
| `schematics/weapons` | 20 | 20 |
| `tools/mining` | 20 | 20 |
| `tools/utility` | 20 | 20 |
| `vehicles/ornithopter` | 20 | 20 |
| `vehicles/parts` | 20 | 20 |
| `vehicles/sandbike` | 20 | 20 |
| `weapons/melee` | 20 | 20 |
| `weapons/ranged` | 20 | 20 |

Full catalog population run on May 21, 2026:

- backup before populate-all:
  `backups/admin-panel/artificial-exchange/live-runs/20260521T023525Z-before-populate-all.sql`
- enabled catalog rows: `2278`
- eligible validated rows: `2278`
- dry-run planned rows: `2278`
- apply planned rows: `2278`
- active seeded NPC orders after apply: `2278`
- distinct seeded templates after apply: `2278`
- seeded price range after apply: `1` to `568078`
- source inventory id: `485`

## Recovery And Rollback

Before live mutation tests, take a narrow dump:

```bash
docker compose --env-file .env exec -T postgres \
  pg_dump -U dune -d dune_sb_1_4_0_0 \
  -n dune \
  -t dune.dune_exchange_orders \
  -t dune.dune_exchange_sell_orders \
  -t dune.dune_exchange_fulfilled_orders \
  -t dune.dune_exchange_users \
  -t dune.player_virtual_currency_balances \
  --data-only --inserts \
  > backups/dune-exchange-before-$(date -u +%Y%m%dT%H%M%SZ).sql
```

Audit trail:

```bash
tail -n 100 backups/admin-panel/artificial-exchange/bot-audit.jsonl
cat backups/admin-panel/artificial-exchange/bot-state.json
```

Disable all live behavior:

```env
DUNE_ARTIFICIAL_EXCHANGE_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN=false
DUNE_ARTIFICIAL_EXCHANGE_FUNDING_ENABLED=false
DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=false
```

Stop services:

```bash
sudo systemctl disable --now dune-artificial-exchange-bot.service
sudo systemctl disable --now dune-artificial-exchange-populator.service
```

## Operational Sequence

Recommended rollout:

1. Edit `config/artificial-exchange-prices.csv`.
2. Run `python3 scripts/build-exchange-catalog.py`.
3. Run `make artificial-exchange-smoke`.
4. Run `python3 scripts/artificial-exchange-bot.py --check-ready --buyer-controller-id <id>`.
5. Fund the buyer Exchange balance if purchases will be enabled.
6. Start buyer service in dry-run.
7. Inspect `bot-audit.jsonl` and settlement reports.
8. Enable purchases only after dry-runs select expected orders.
9. Enable auto-claim after settlement reports are clean.
10. Start populator separately only if seeded liquidity is desired.
