# Vendor and Loot Table Research

Status: vendor stock state is now tested. True vendor catalogs and true loot
table rows still look asset-backed, not database-backed.

## Summary

| Surface | Current read | Confidence | Mutation status |
| --- | --- | --- | --- |
| Vendor catalog/list | Defined by cooked data table `/Game/Dune/Systems/Trading/DT_VendorTable.DT_VendorTable`. | high | blocked |
| Vendor per-player stock counters | Stored in `dune.vendor_stock_cycle` and `dune.vendor_stock_state`. | high | safe to inspect; writes only for controlled reset/repair |
| Vendor stock reset | First-party DB functions can clear per-player or per-vendor counters. | high | possible, but high player-facing impact |
| NPC exchange sell orders | DB function exists; shipped first-order creation fails, rollback patch proves route is structurally viable. | high | blocked pending schema patch and live-client validation |
| Vendor prices/demand/distance/cycle caps | Config keys exist under inventory/economy settings. | moderate | candidate `.ini` knobs; needs live vendor UI validation |
| Loot rights policy | `[/Script/DuneSandbox.LootSettings] GlobalLootRightsBehaviour`. | high | likely safe after restart test |
| Loot display/order/container filters | Config keys exist under inventory settings. | moderate | probably UI/container behavior, not drop weights |
| True loot table contents/drop weights | Binary exposes `FLootTableRow`, `m_LootTable`, `m_LootTablesDirectory`; config points to data assets. | moderate | blocked without cooked asset path |

Bottom line: we can play with vendor cycle state and some broad economy/loot
rules. We do not yet have a validated way to edit "vendor sells item X" or
"container drops item Y at weight Z" from plain self-host config or DB.

## Evidence: Shipped Config

Observed inside the live server container:

```sh
docker compose exec -T survival sed -n '620,636p' /home/dune/server/DuneSandbox/Config/DefaultGame.ini
docker compose exec -T survival sed -n '1907,2020p' /home/dune/server/DuneSandbox/Config/DefaultGame.ini
docker compose exec -T survival sed -n '2644,2646p' /home/dune/server/DuneSandbox/Config/DefaultGame.ini
```

Important shipped values:

```ini
m_VendorDataTable=/Game/Dune/Systems/Trading/DT_VendorTable.DT_VendorTable

[/Script/DuneSandbox.InventorySystemSettings]
LootQualityPerDifficulty=/Game/Dune/Systems/Looting/LootQualityChances/DA_LootQualityDropChancePerItemPerDifficulty.DA_LootQualityDropChancePerItemPerDifficulty
LootBlacklistTag=(TagName="Items.ExcludeFromLootSystem")
ExchangeBlacklistTag=(TagName="Items.ExcludeFromExchange")
ExchangeHiddenItemTag=(TagName="Items.HideFromExchange")
PlayerSellToVendorBlacklistTag=(TagName="Items.ExcludeFromPlayerSellingToVendor")
PlayerBuyFromVendorBlacklistTag=(TagName="Items.ExcludeFromPlayerBuyingFromVendor")
+LootItemsOrder=(...)
+DroppableLootContainers=(Name="Default")
+DroppableLootContainers=(Name="DefeatItemDrop")
+DroppableLootContainers=(Name="ItemDrop")
+DroppableLootContainers=(Name="NpcLootContainer")
LootContainersToHideWhenEmpty=(Name="NpcLootContainer")
VendorBaselineDemand=0.050000
MaxSqrDistanceToVendor=250000.000000
MaxVendorCycleDuration=2419200
MaxSlotlessItemBuyAmountPerBulk=40

[/Script/DuneSandbox.LootSettings]
GlobalLootRightsBehaviour=PerPlayerChestAndNpcDrop
```

Interpretation:

- `m_VendorDataTable` is a direct pointer to a cooked Unreal data table. High
  confidence that the vendor catalog/list lives there.
- `LootQualityPerDifficulty` is a direct pointer to a cooked data asset. Moderate
  confidence that quality weighting is asset-backed.
- `LootItemsOrder`, `DroppableLootContainers`, and
  `LootContainersToHideWhenEmpty` are configurable, but they look like display
  and container-behavior rules, not "drop this item" rules.
- `VendorBaselineDemand`, `MaxSqrDistanceToVendor`,
  `MaxVendorCycleDuration`, and `MaxSlotlessItemBuyAmountPerBulk` are plausible
  self-host economy knobs, but they need live vendor UI tests before promotion.

## Evidence: Loot Rights Enum

Binary/config string checks found only two visible `ELootRightsBehaviour` names:

```text
ELootRightsBehaviour::Default
ELootRightsBehaviour::PerPlayerChestAndNpcDrop
GlobalLootRightsBehaviour
```

The shipped config uses:

```ini
[/Script/DuneSandbox.LootSettings]
GlobalLootRightsBehaviour=PerPlayerChestAndNpcDrop
```

Interpretation:

- High confidence that `Default` and `PerPlayerChestAndNpcDrop` are valid
  override values.
- Unknown whether `Default` means shared loot, legacy behavior, or map/actor
  default behavior. It must be validated with two players because the name alone
  does not prove ownership semantics.
- No other loot-rights enum names were visible from binary strings.

## Evidence: Database Tables and Functions

Read-only introspection:

```sh
docker compose exec -T postgres psql -U dune -d dune_sb_1_4_0_0 -At -F $'\t' -c \
  "select table_schema,table_name
   from information_schema.tables
   where table_schema='dune'
     and (table_name ilike '%vendor%' or table_name ilike '%loot%' or table_name ilike '%stock%' or table_name ilike '%exchange%')
   order by 1,2;"
```

Tables found:

```text
dune.dune_exchange_accesspoints
dune.dune_exchange_categories_hash
dune.dune_exchange_fulfilled_orders
dune.dune_exchange_orders
dune.dune_exchange_sell_orders
dune.dune_exchange_users
dune.dune_exchanges
dune.vendor_stock_cycle
dune.vendor_stock_state
```

Vendor stock columns:

```text
vendor_stock_cycle(vendor_id text, player_id bigint, last_interacted_timestamp bigint)
vendor_stock_state(vendor_id text, player_id bigint, template_id text, amount_bought int)
```

Both vendor stock tables have `player_id` foreign keys to `dune.actors(id)`.
There is no DB table found that stores the vendor catalog itself.

Vendor stock functions:

```text
interact_get_vendor_items_bought_from_player(vendor_id, player_id, cycle_start)
player_purchased_item_from_vendor(vendor_id, player_id, template_id, amount)
update_vendor_timestamp_for_player(vendor_id, player_id, timestamp)
clean_stock_for_player(player_id)
clean_stock_for_vendors(vendor_ids[])
clean_vendors_older_than_timestamp(reference_timestamp)
```

These functions match the SQL shipped in
`/home/dune/server/DuneSandbox/Database/76_vendor_stock.sql`.

Exchange functions include `dune_exchange_update_recurring_sell_order`, which
looks like the first-party path for NPC exchange listings. That path is separate
from ordinary vendor stock and writes `dune_exchange_orders` with
`is_npc_order = true`.

## Tested Behavior

Synthetic player IDs are rejected by the actor foreign key:

```text
ERROR: insert or update on table "vendor_stock_cycle" violates foreign key constraint "vendor_stock_cycle_player_id_fkey"
DETAIL: Key (player_id)=(999999991) is not present in table "actors".
```

Rollback-only test against existing actor/player `17`:

```sql
begin;
select * from dune.interact_get_vendor_items_bought_from_player('CodexSyntheticVendor', 17, 1779271200);
select dune.player_purchased_item_from_vendor('CodexSyntheticVendor', 17, 'CodexSyntheticTemplate', 2);
select dune.player_purchased_item_from_vendor('CodexSyntheticVendor', 17, 'CodexSyntheticTemplate', 3);
select * from dune.vendor_stock_state where vendor_id='CodexSyntheticVendor';
select * from dune.interact_get_vendor_items_bought_from_player('CodexSyntheticVendor', 17, 1779271200);
select * from dune.interact_get_vendor_items_bought_from_player('CodexSyntheticVendor', 17, 1779271300);
rollback;
```

Observed behavior:

- First interaction creates a `vendor_stock_cycle` row.
- Two purchases of the same template accumulate to `amount_bought = 5`.
- Re-reading in the same cycle returns `CodexSyntheticTemplate = 5`.
- Re-reading with a later cycle timestamp deletes the per-player purchased-item
  state and returns no rows.
- Post-rollback verification returned zero synthetic rows in both vendor tables.

Conclusion: `vendor_stock_state` is not stock definition. It is per-player,
per-cycle purchase accounting. Editing it can make a player appear to have
already bought fewer/more items from a vendor, but it does not add new vendor
catalog items.

## Tested Behavior: NPC Exchange Orders

The exchange DB has an NPC recurring sell-order function:

```text
dune_exchange_update_recurring_sell_order(
  exchange_id, expiration_time, access_point_id, owner_id, item_id,
  increment, max_count, category_mask, category_depth, durability_cur,
  durability_max, item_price, wear_normalized_item_price, quality_level
)
```

This looked like a possible route for adding NPC exchange stock. It is not a
validated route yet, and in the current live schema it fails on first-order
creation.

Rollback-only test:

```sql
begin;
select dune.dune_exchange_update_recurring_sell_order(
  2::bigint, 1779279999::bigint, 1::bigint, 17::bigint, 33256527::bigint,
  1::bigint, 10::bigint, 0::int, 0::smallint, 100.0::real, 100.0::real,
  123::bigint, 123::bigint, 0::bigint
);
rollback;
```

Observed error:

```text
ERROR: null value in column "initial_stack_size" of relation "dune_exchange_sell_orders" violates not-null constraint
DETAIL: Failing row contains (1, null, 123).
CONTEXT: SQL statement "INSERT INTO dune_exchange_sell_orders(order_id, initial_stack_size, wear_normalized_price) VALUES(new_order_id, new_count, in_wear_normalized_item_price)"
```

Cause in shipped/current function body:

```sql
IF new_order_id IS NULL THEN
  INSERT INTO dune_exchange_orders(...)
  VALUES(...)
  RETURNING id INTO new_order_id;

  INSERT INTO dune_exchange_sell_orders(order_id, initial_stack_size, wear_normalized_price)
  VALUES(new_order_id, new_count, in_wear_normalized_item_price);
```

`new_count` is declared but not assigned before the first insert into
`dune_exchange_sell_orders`. High confidence this blocks first-time NPC exchange
order creation through this function in the current schema.

Post-test verification:

```text
dune_exchange_orders: 0
dune_exchange_sell_orders: 0
exchange inventories: 0
```

There are no later upgrade scripts in the shipped
`DuneSandbox/Database/Upgrade` tree that mention
`dune_exchange_update_recurring_sell_order` or `new_count`; only vendor-stock
upgrade names were found. So this appears to be current behavior in this server
build, not an already-patched migration artifact.

### Rollback Patch Probe

To separate "function typo" from "route impossible", the function was patched
inside a transaction only:

```sql
begin;
create or replace function dune.dune_exchange_update_recurring_sell_order(...)
returns bigint language plpgsql as $function$
...
if new_order_id is null then
  new_count := in_increment;
  insert into dune_exchange_orders(...);
  insert into dune_exchange_sell_orders(order_id, initial_stack_size, wear_normalized_price)
  values(new_order_id, new_count, in_wear_normalized_item_price);
  select into new_item_id move_inventory_item(in_item_id, exchange_inventory_id, new_order_id, in_increment);
...
rollback;
```

Then the same call succeeded inside the transaction:

```text
first_increment: 1
patched_order:
  exchange_id=2
  access_point_id=1
  owner_id=17
  item_id=33256527
  template_id=PowerPack
  is_npc_order=true
  item_price=123
  initial_stack_size=1
moved_item:
  id=33256527
  inventory_id=482
  stack_size=1
  position_index=2
```

Post-rollback verification:

```text
dune_exchange_orders: 0
dune_exchange_sell_orders: 0
exchange inventories: 0
item 33256527 restored to inventory_id=413, position_index=3
original function body restored; bug still present
```

Conclusion: high confidence the recurring NPC exchange order route can create
server-side NPC exchange listings if the function is patched. It still needs
live-client validation before any permanent schema patch because the exchange UI
may apply category masks, category depth, access point, owner, pricing, quality,
or item-stat expectations that the DB alone cannot prove.

## Built Tooling

`scripts/npc-exchange-stock.sh` now wraps the NPC exchange route with explicit
dry-run and apply modes.

`scripts/admin-chat-commands.py` also supports a player chat command for normal
player-owned exchange listings:

```text
&auction "<item name or template>" <count> <price>
&auction --base "<item name or template>" <count> <price>
&auction --inventory <inventory_id> "<item name or template>" <count> <price>
&auction --item-id <item_id> <count> <price>
&auction --inventory <inventory_id> --item-id <item_id> <count> <price>
```

This command uses the first-party player listing function
`dune.dune_exchange_add_sell_order`, not the NPC recurring-order function.

Examples:

```text
&auction PowerPack 1 456
&auction "power pack" 1 456
&auction --base PowerPack 1 456
&auction --inventory 413 PowerPack 1 456
&auction --item-id 33256803 1 456
```

Current behavior:

- Non-admin players may use `&auction` for their own character.
- All other chat commands still require admin allow-list membership.
- The default command searches the sender's pawn/controller inventories.
- `--base` searches base storage inventories the sender appears permitted to
  access through totem/rank data.
- `--inventory <inventory_id>` targets one explicit personal or permitted base
  storage inventory.
- `--item-id <item_id>` bypasses fuzzy name/template matching and only succeeds
  if that item row is in an allowed source inventory.
- Base and explicit-storage sources require
  `DUNE_CHAT_COMMAND_AUCTION_BASE_STORAGE_ENABLED=true`.
- It lists one stack that has at least `<count>` items. Split-across-stacks
  listings are not supported yet.
- The order owner is the sender's `player_controller_id`.
- It uses `dune.dune_exchange_add_sell_order`, so sold funds should follow the
  normal Dune Exchange seller settlement path.
- It defaults to dry-run/preview unless `DUNE_CHAT_COMMAND_AUCTION_ENABLED=true`.

Current defaults:

```text
DUNE_CHAT_COMMAND_AUCTION_ENABLED=false
DUNE_CHAT_COMMAND_AUCTION_BASE_STORAGE_ENABLED=false
DUNE_CHAT_COMMAND_AUCTION_EXCHANGE_ID=2
DUNE_CHAT_COMMAND_AUCTION_ACCESS_POINT_ID=1
DUNE_CHAT_COMMAND_AUCTION_MAX_ORDERS_PER_PLAYER=50
DUNE_CHAT_COMMAND_AUCTION_LISTING_FEE=0
DUNE_CHAT_COMMAND_AUCTION_DURATION_SECONDS=2419200
DUNE_CHAT_COMMAND_AUCTION_CATEGORY_MASK=0
DUNE_CHAT_COMMAND_AUCTION_CATEGORY_DEPTH=0
DUNE_CHAT_COMMAND_AUCTION_CONFIRM_SECONDS=120
DUNE_CHAT_COMMAND_AUCTION_SUGGESTION_MIN_SCORE=0.55
```

Dry-run examples already tested:

```text
Lukano: &auction "power pack" 1 456
-> previewed 1x PowerPack2 for 456, ownerId=17

Xale: &auction PowerPack 1 456
-> previewed 1x PowerPack for 456, ownerId=24

Xale: &auction NopeItem 1 456
-> no inventory item matched

Xale: &auction PowerPack one 456
-> count must be a positive integer

Lukano: &auction --base PowerPack 1 456
-> with base storage disabled: base/storage auction source is disabled
-> with base storage enabled: previewed 1x PowerPack from inventory 413

Lukano: &auction --inventory 413 PowerPack 1 456
-> with base storage enabled: previewed 1x PowerPack from inventory 413

Xale: &auction --inventory 413 PowerPack 1 456
-> inventory 413 is not an allowed personal/base inventory for this player

Xale: &auction --item-id 33256803 1 456
-> previewed 1x PowerPack from Xale's personal inventory

Lukano: &auction --inventory 413 --item-id 33256594 1 456
-> with base storage enabled: previewed 1x PowerPack from inventory 413

Xale: &auction --item-id 33256594 1 456
-> no allowed inventory item matched item-id:33256594

Xale: &auction PwerPck 1 456
-> no exact match for PwerPck; did you mean PowerPack from inventory 37?
-> reply &auction yes or &auction no

Lukano: &auction --inventory 413 PwerPck 1 456
-> with base storage enabled: did you mean PowerPack from inventory 413?
```

Parser coverage:

```text
python3 scripts/test-admin-chat-commands.py
-> 9 auction parser tests passing
```

Confirmation notes:

- `&auction yes` re-runs the pending suggestion using the suggested exact
  `item_id`, so it does not depend on fuzzy matching a second time.
- `&auction no` cancels the pending suggestion.
- Confirmation state is held in the running chat-command process. It is not
  shared across one-shot `--dry-run-command` executions.
- `m_UserNameTo` by itself was tested and rendered as a broadcast/channel
  message, not a private message.
- Private-shaped replies were also tested with `m_ChannelType=Private`,
  `m_UserNameTo=<name>`, target queue `<fls_id>_queue`, and a
  command-specific routing key.
- The private-channel shape published successfully to RabbitMQ but did not
  render in the client. Confidence is high that the current chat-publish route
  is not a working private-message route.
- `DUNE_CHAT_COMMAND_PRIVATE_REPLIES_ENABLED` now defaults to `false`; auction
  confirmations should use the normal visible reply path until the real
  private-chat contract is discovered.

Additional private-chat investigation:

- RabbitMQ has a real `chat.whispers` direct exchange. Confidence: high.
- TextRouter expects intercepted client chat on `chat.intercept`, then redirects
  based on an AMQP header named `redirect_exchange`. Confidence: high.
- The `redirect_exchange` header value must be AMQP bytes. With Pika, this is
  `headers={"redirect_exchange": b"chat.map"}` or
  `headers={"redirect_exchange": b"chat.whispers"}`. Plain string/list values
  either leave the redirect exchange empty or throw a TextRouter cast error.
  Confidence: high.
- With `redirect_exchange=b"chat.map"`, TextRouter logs a successful redirect to
  `chat.map`. Confidence: high.
- With `redirect_exchange=b"chat.whispers"`, TextRouter logs successful redirects
  to `chat.whispers` for routing keys `6FF6498F4074E3DE`, `Lukano`, and
  `6FF6498F4074E3DE_queue`. Confidence: high for TextRouter redirect, unknown
  for client rendering.
- Remaining blocker: prove the client-visible whisper routing key/body/channel
  by capturing a real player-to-player whisper. Use:

```text
scripts/capture-chat-routing.py --seconds 60 \
  --routing-key 6FF6498F4074E3DE \
  --routing-key Lukano \
  --routing-key 6FF6498F4074E3DE_queue \
  --routing-key '#'
```

Then send a real in-client whisper/private chat and compare the captured
`exchange`, `routingKey`, `properties.headers.redirect_exchange`, `userId`,
`m_ChannelType`, `m_UserNameTo`, and message body shape.

Important limitation: direct DB execution while the player is online still needs
live validation. The function is the server's first-party exchange function, but
the chat bot calls it from admin tooling rather than from the live map server
handling the player's UI action. Keep the command preview-only until one real
listing and purchase has been validated end-to-end.

### What This Tool Does

This tool does not edit ordinary NPC vendor catalogs such as
`DT_VendorTable`. It works on the separate Dune Exchange system.

What it can do:

- Detect whether the shipped DB function
  `dune.dune_exchange_update_recurring_sell_order` still has the first-order
  `new_count` bug.
- Patch that DB function so it can create the first NPC exchange sell order for
  a template/price/access-point combination.
- Move an existing item row into an exchange inventory and list it as
  `is_npc_order = true` in `dune.dune_exchange_orders`.
- Re-stock an existing matching NPC exchange order through the same recurring
  function path.
- Preview all of the above in a transaction that rolls back.

What it does not do:

- It does not create new item templates.
- It does not edit cooked vendor data tables.
- It does not edit loot drop tables.
- It does not duplicate an item. The listed item is moved out of its source
  inventory into the exchange inventory.
- It does not prove the client will display or allow purchase of the order.
  Category masks, access point, quality, stat shape, and exchange UI filters
  still need live validation.

Operational model:

1. Create or identify a disposable source item.
2. Dry-run the NPC exchange order and inspect the planned rows.
3. Patch the recurring-order function only if the dry-run looks correct.
4. Apply the order.
5. Check the exchange in client.

The source item matters. If `--item-id` points at a real player-owned item, that
item is removed from the player/source inventory and becomes exchange stock.
For testing, use a deliberately granted item in a test/admin inventory.

Inspect current state:

```sh
scripts/npc-exchange-stock.sh inspect
```

Observed on this farm after dry-run tests:

```text
recurring_order_function_status: bug_present
dune_exchange_orders: 0
dune_exchange_sell_orders: 0
exchange_inventories: 0
```

Patch preview:

```sh
scripts/npc-exchange-stock.sh patch-function --dry-run
```

Observed:

```text
BEGIN
CREATE FUNCTION
function_status | patched_or_changed
ROLLBACK
```

Apply patch, intentionally gated:

```sh
scripts/npc-exchange-stock.sh patch-function \
  --apply \
  --confirm "PATCH NPC EXCHANGE FUNCTION"
```

The script writes a host-side backup of the previous function definition under
`backups/admin-panel/npc-exchange-stock/` before patching.

NPC order preview:

```sh
scripts/npc-exchange-stock.sh add-order \
  --dry-run \
  --owner-id 17 \
  --item-id 33256527 \
  --count 1 \
  --max-count 10 \
  --price 123
```

Observed dry-run result:

```text
function_status: patched_or_changed
source_item_before: id=33256527 inventory_id=413 stack_size=1 position_index=3 template_id=PowerPack
increment_added: 1
matching_orders:
  exchange_id=2
  exchange_name=HarkoVillage_EX
  access_point_id=1
  access_point=HarkoVillage_AP
  owner_id=17
  item_id=33256527
  template_id=PowerPack
  is_npc_order=true
  item_price=123
  inventory_id=<temporary exchange inventory>
  stack_size=1
```

Post-dry-run verification:

```text
recurring_order_function_status: bug_present
dune_exchange_orders: 0
dune_exchange_sell_orders: 0
exchange_inventories: 0
item 33256527: inventory_id=413, stack_size=1, position_index=3
```

Apply NPC order, intentionally gated:

```sh
scripts/npc-exchange-stock.sh add-order \
  --apply \
  --confirm "ADD NPC EXCHANGE ORDER" \
  --owner-id <actor-or-controller-id> \
  --item-id <existing-item-id> \
  --count 1 \
  --max-count 10 \
  --price <solari-price>
```

Important constraints:

- `add-order --apply` does not patch the function. Run `patch-function --apply`
  first.
- The item is moved from its current inventory into the exchange inventory. Use
  a deliberately granted or disposable item, not a live player item, unless that
  is the intended stock source.
- Category mask/depth defaults to `0`; this may affect whether the client shows
  the order under useful filters. Live-client validation is still required.
- Rollback for an applied order is not just deleting the order if the item should
  be restored to a source inventory. Capture the source item row first or use a
  disposable/granted source item.

### Applied Live Probe

Applied on this farm:

```sh
scripts/npc-exchange-stock.sh patch-function \
  --apply \
  --confirm "PATCH NPC EXCHANGE FUNCTION"

scripts/npc-exchange-stock.sh add-order \
  --apply \
  --confirm "ADD NPC EXCHANGE ORDER" \
  --exchange-id 2 \
  --access-point-id 1 \
  --owner-id 17 \
  --item-id 33256527 \
  --count 1 \
  --max-count 10 \
  --price 123
```

Result:

```text
recurring_order_function_status: patched_or_changed
dune_exchange_orders: 1
dune_exchange_sell_orders: 1
exchange_inventories: 1

order id: 5
exchange: HarkoVillage_EX
access point: HarkoVillage_AP
owner_id: 17
item_id: 33256527
template_id: PowerPack
is_npc_order: true
item_price: 123
expiration_time: 1781745260
quality_level: 0
initial_stack_size: 1
wear_normalized_price: 123

item 33256527:
  inventory_id: 485
  stack_size: 1
  position_index: 5
```

Source before apply:

```text
item 33256527:
  inventory_id: 413
  stack_size: 1
  position_index: 3
  template_id: PowerPack
```

Backup of the original function definition:

```text
backups/admin-panel/npc-exchange-stock/20260521T011416Z-dune_exchange_update_recurring_sell_order.sql
```

Client validation target: check the HarkoVillage exchange/access point for an
NPC `PowerPack` order priced at `123`.

## Evidence: Runtime/Binary Strings

Binary string scan on the live server executable exposed these relevant names:

```text
FVendorTableRow
FVendorStockData
FVendorIndividualItemData
FVendorItemConfig
FVendorComponent
UVendorUtils
UNPCTradingSubsystem::GetVendorStockDataImmediate
ResetVendorStockData
m_VendorDataTable
m_LootTable
m_LootTablesDirectory
FLootTableRow
FBaseLootTableRow
FLootTableNumericalStat
ETemporaryLootSpawnerSettingsSource::LootTable
GlobalDistributionPrintLootSettingsForCurrentLocation
```

Interpretation:

- High confidence that the server has native vendor and loot table structures.
- Moderate confidence that actual rows are loaded from cooked assets/data tables.
- The cheat/debug string `ResetVendorStockData` supports the DB finding that
  vendor stock state is resettable runtime accounting.
- `GlobalDistributionPrintLootSettingsForCurrentLocation` may be a useful future
  GM/debug route if native command execution becomes validated.

## Evidence: Pak String Probe

Read-only string probes against the live server pak files:

```sh
docker compose exec -T survival sh -lc 'for f in /home/dune/server/DuneSandbox/Content/Paks/*.pak; do if grep -a -q "DT_VendorTable" "$f"; then echo "$f"; fi; done'
docker compose exec -T survival sh -lc 'for f in /home/dune/server/DuneSandbox/Content/Paks/*.pak; do if grep -a -q "DA_LootQualityDropChancePerItemPerDifficulty" "$f"; then echo "$f"; fi; done'
docker compose exec -T survival sh -lc 'for f in /home/dune/server/DuneSandbox/Content/Paks/*.pak; do if grep -a -q "LootTable" "$f"; then echo "$f"; fi; done'
```

Observed:

```text
DT_VendorTable: pakchunk0-LinuxServer.pak
DA_LootQualityDropChancePerItemPerDifficulty: pakchunk0-LinuxServer.pak
LootTable strings: pakchunk0, pakchunk140, pakchunk170, pakchunk200
```

No `UnrealPak` binary was found in the live server container. That means asset
extraction/repacking needs an external Unreal tooling path; it is not available
from the shipped self-host container alone.

## Live DB Snapshot

At test time:

```text
vendor_stock_cycle: 6
vendor_stock_state: 0
dune_exchange_orders: 0
dune_exchange_sell_orders: 0
dune_exchanges: 2
dune_exchange_accesspoints: 1
```

Observed vendor IDs in `vendor_stock_cycle`:

```text
TradingPost_Vendor1
Vehicle_Default
ScrapVendor
TradingPost_Vendor2
```

The empty `vendor_stock_state` means no current per-player limited-stock purchase
counters were active in this snapshot.

## What We Can Safely Play With Now

High confidence:

- Inspect vendor interactions and purchase counters.
- Reset vendor stock counters for one player with `clean_stock_for_player`.
- Reset vendor stock counters for known vendors with `clean_stock_for_vendors`.
- Let cycle rollover clear counters naturally through
  `interact_get_vendor_items_bought_from_player`.
- Do not use `dune_exchange_update_recurring_sell_order` for NPC stock injection
  unless the function body is patched or a pre-existing matching NPC order row is
  already present.

Moderate confidence:

- Test `MaxVendorCycleDuration` by lowering it, restarting, interacting with a
  limited-stock vendor, buying one tracked item, then verifying the counter clears
  after the shorter cycle.
- Test `MaxSlotlessItemBuyAmountPerBulk` against a stackable vendor purchase.
- Test `VendorBaselineDemand` only if the UI exposes demand/price changes.
- Test `GlobalLootRightsBehaviour` on a disposable chest/NPC drop scenario.

Low confidence / blocked:

- Adding a new item to a vendor list through DB.
- Adding first-time NPC exchange sell orders through the shipped recurring-order
  function.
- Editing vendor catalog rows through `.ini`.
- Editing true loot drop tables through `.ini`.
- Changing loot weight rows without cooked asset extraction/repack support.

## Next Experiments

1. Vendor cycle knob test:
   - Back up `config/UserGame.ini`.
   - Add/override `MaxVendorCycleDuration` under
     `[/Script/DuneSandbox.InventorySystemSettings]`.
   - Restart one test map.
   - Interact with a known limited-stock vendor and capture
     `vendor_stock_cycle` / `vendor_stock_state` before and after purchase.
   - Advance beyond the configured cycle and interact again.
   - Promote only if the timestamp/counter behavior changes predictably.

2. Vendor reset admin tool:
   - Add a dry-run endpoint that lists affected `vendor_stock_cycle` and
     `vendor_stock_state` rows for a player/vendor.
   - Add write support only for `clean_stock_for_player` and
     `clean_stock_for_vendors`.
   - Do not expose arbitrary inserts into `vendor_stock_state`.

3. Loot rights test:
   - Override `GlobalLootRightsBehaviour` on a disposable test map.
   - Use only the visible enum alternatives first: `Default` and
     `PerPlayerChestAndNpcDrop`.
   - Kill one NPC/open one chest with two players and record visibility/ownership
     behavior.

4. Asset route investigation:
   - Identify which pak contains `DT_VendorTable` and known loot table assets.
   - Try read-only Unreal asset extraction outside the live server.
   - Treat repacking/replacement as blocked until signature/loading behavior is
     proven on an offline disposable server.

5. NPC exchange live-client validation:
   - Patch the function on a disposable/test farm only.
   - Grant a disposable item into an offline admin/test inventory.
   - Run `scripts/npc-exchange-stock.sh add-order --dry-run` against that item.
   - Run `add-order --apply` only after the preview shows the expected exchange,
     access point, price, and item template.
   - Open the matching exchange in client and verify visibility, price, purchase,
     and resulting item stats.
   - If visible and purchasable, add an admin-panel endpoint that wraps this
     script/function with dry-run default, confirmation phrase, source-item
     capture, and explicit rollback guidance.
