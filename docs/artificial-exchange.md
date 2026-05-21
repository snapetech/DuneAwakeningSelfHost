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
template_id,display_name,category,sellable_status,baseline_price,max_buy_price,liquidity_tier,enabled,source,confidence,notes
```

Meaning:

- `template_id`: item template id used by Dune DB rows.
- `display_name`: human label for operators.
- `category`: operator grouping only.
- `sellable_status`: expected values are `known`, `observed`, or `validated`.
- `baseline_price`: reference market price.
- `max_buy_price`: highest price the artificial buyer may pay.
- `liquidity_tier`: `low`, `medium`, or `high`; controls buy probability.
- `enabled`: only `true` rows are eligible for buying or seeding.
- `source`: `manual`, `snapshot`, `local-db`, `live-test`, or similar.
- `confidence`: `low`, `moderate`, or `high`.
- `notes`: operator comments.

Current reviewed manual seed:

```csv
PowerPack,PowerPack,test,validated,123,123,high,true,live-test,high,validated via order 5 live purchase and settlement
```

## Catalog Pipeline

Build without DB:

```bash
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

Current category limitation:

- The reviewed catalog currently has one enabled row: `PowerPack`.
- The live `dune_exchange_categories_hash` table currently exposes only integer
  hashes, not category names or a hierarchy.
- The populator can set global `category_mask` and `category_depth`, but the
  catalog does not yet carry per-row native category mask/depth values.
- Because of that, it cannot truthfully populate 20 listings in every native
  Exchange subcategory yet. It can only populate the reviewed catalog rows under
  one configured mask/depth until category metadata is mapped.

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

Run buyer and populator as separate services. There is no combined mode.

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

Current known live state after validation:

- no active sell orders
- completed purchased-item storage order `6`
- no pending seller claim rows
- no unsafe settlement rows
- controller `17` base Solaris balance `123`
- buyer Exchange balance `0`

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
