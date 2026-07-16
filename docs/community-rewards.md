# Community rewards, shop, and reward tracks

Confidence: high for the isolated wallet/order state, idempotency, HMAC receiver,
playtime accounting, and delivery/refund state machine. Confidence: moderate for
the game-item delivery bridge until representative catalog purchases have been
canaried on the live server.

This subsystem provides the community economy features exposed by the pinned
`neophrythe/Dune-Awakening-Shop-System` peer while keeping community credits
separate from Dune's Solari and player-currency tables.

## What is included

- Discord-to-Dune account linking with short-lived, one-use, hash-only codes.
- A separate community wallet and an append-only SHA-256 hash-chained ledger.
- Versioned item and kit offers, finite or unlimited stock, atomic debit and
  stock reservation, and request idempotency.
- A persistent one-at-a-time delivery queue. Deliveries wait for an offline
  player, preflight the existing item-grant path, and retain exact receipts.
- Automatic wallet refund and stock restoration on a definitive preflight or
  delivery failure.
- A `reconciliation` state for an ambiguous game-write result. It deliberately
  does not refund until an operator records whether delivery happened, avoiding
  both a free duplicate and an unjustified debit.
- Confirmed-presence playtime accrual with interval remainders, a maximum
  observation gap, and idempotent checkpoints.
- Movement-verified engagement airdrops with bounded grace, scaled active-session
  rewards, consecutive UTC-day streaks, ISO-week active-time thresholds, and
  append-only issuance claims. See
  [`engagement-airdrops.md`](engagement-airdrops.md).
- Signed vote and manual-payment credit webhooks with timestamp replay windows,
  provider event IDs, payload collision detection, and per-provider credit caps.
- Versioned reward tracks, monotonic XP thresholds, idempotent progress sources,
  one-time level claims, and delivery through the same queue.
- Admin API/status, RBAC mapping, audit events, a background worker, tests, and
  player-facing Discord commands.

It does not change game Solari, take payment-card data, call a payment processor,
or write Dune tables except when the separately gated delivery worker invokes the
existing item-grant function for an offline player.

## Files and state

| Path | Purpose | Treatment |
|---|---|---|
| `config/community-rewards.example.json` | Versioned example catalog, playtime, webhook, and track policy | committed |
| `config/community-rewards.json` | Active policy/catalog | ignored; mode `0600` |
| `config/secrets/community-vote-webhook.secret` | Vote receiver HMAC key | ignored; mode `0600` |
| `config/secrets/community-payment-webhook.secret` | Manual-payment receiver HMAC key | ignored; mode `0600` |
| `backups/community-rewards/community.sqlite3` | Wallet, ledger, orders, deliveries, stock, links, and tracks | ignored; mode `0600` |

SQLite runs in WAL mode with foreign keys, `synchronous=FULL`, a busy timeout,
and `BEGIN IMMEDIATE` for state changes. `scripts/backup-state.sh` uses SQLite's
online backup API and verifies `integrity_check`, producing
`community-rewards.sqlite3` inside every backup set when the live database
exists. Offsite sync then carries that snapshot with the rest of `backups/`.

## Activation

The aggregate feature activator performs the initial setup on its exact allowed
host:

```bash
./scripts/enable-feature-parity.sh .env --execute
```

It copies the example when no live config exists. For an older private config,
it atomically merges only the missing engagement-airdrop block after validation
and a mode-`0600` backup; existing operator policy wins. It generates independent
256-bit vote/payment HMAC secrets only when missing, locks the files, and enables:

```dotenv
DUNE_COMMUNITY_REWARDS_ENABLED=true
DUNE_COMMUNITY_DELIVERY_ENABLED=true
DUNE_COMMUNITY_REWARDS_DATABASE=/workspace/backups/community-rewards/community.sqlite3
DUNE_COMMUNITY_POLL_SECONDS=30
```

Recreate only the admin surface after changing container environment values:

```bash
./scripts/deploy-admin-panel.sh .env
```

This does not restart a game map. The worker and API are embedded in
`admin-panel`. Config synchronization happens at initialization and can be run
again through the API after editing the catalog.

## Catalog configuration

`version` is the document schema. Each offer also has a version:

```json
{
  "id": "field-kit",
  "version": 1,
  "name": "Field Kit",
  "kind": "kit",
  "price": 50,
  "stock": 25,
  "enabled": true,
  "rewards": [
    {"type": "item", "templateId": "WaterPack_Consumable", "count": 2, "qualityLevel": 0},
    {"type": "item", "templateId": "Bloodsack_02", "count": 1, "qualityLevel": 0}
  ]
}
```

Supported delivery type is currently `item`. Offer IDs are stable. Syncing the
same offer version preserves remaining stock; incrementing its version resets
stock to the configured value. Removing an offer from config disables it without
deleting purchase history. A purchase snapshots offer ID, version, quantity,
price, and expanded rewards.

Validate and load the active config locally with:

```bash
make community-rewards-check
```

## Wallet and ledger invariants

Every credit or debit runs in the same SQLite transaction as the corresponding
wallet, purchase, stock, webhook receipt, or refund state change. Wallet balances
have a database `balance >= 0` constraint. Provider event IDs, ledger references,
purchase idempotency keys, delivery sources, and track claims are unique.

Each ledger entry stores the prior global entry hash and a hash of canonical
entry fields. SQLite triggers reject update and delete statements. The status API
runs a full chain and per-account running-balance verification. This detects
tampering; it does not make a host administrator unable to replace the entire
database. Protect backups and host access accordingly.

## Linking flow

1. A moderator or administrator creates a link code for a verified Dune
   `account_id` through DASH. The database stores only its SHA-256 digest.
2. The player runs `/dune shop link code:<code>` in the configured guild/channel.
3. The adapter binds the invoking Discord user ID to that Dune account. A code is
   one-use and expires in 15 minutes by default.

Discord identity, never a user-supplied account ID, selects the wallet for
balance, purchases, progress, and claims.

## Discord commands

The first-party bot adds this `shop` group:

| Command | Result |
|---|---|
| `/dune shop howtolink` | linking instructions |
| `/dune shop link code:<code>` | redeem one-time link code |
| `/dune shop balance` | linked wallet balance |
| `/dune shop catalog` | enabled item and kit offers |
| `/dune shop buy offer:<id> [quantity]` | atomic purchase and queued delivery |
| `/dune shop kits` | kit-only catalog |
| `/dune shop track` | linked reward-track progress |
| `/dune shop claim track:<id> level:<n>` | idempotent unlocked-level claim |

Responses are ephemeral, mentions are disabled, guild/channel restrictions still
apply, and the bot sees no admin-owner token. The adapter bearer token permits
only its explicit routes.

## Playtime accrual

The worker reads linked accounts' confirmed `dune.player_state.online_status`.
The first observation establishes a checkpoint. Later observations count elapsed
time only when the preceding state was online. The calculation preserves partial
intervals and caps any observation gap, so downtime cannot create unbounded
credits. Repeating an observation timestamp grants nothing.

Example policy:

```json
"playtime": {
  "enabled": true,
  "intervalSeconds": 900,
  "creditsPerInterval": 1,
  "maxObservationGapSeconds": 600,
  "trackId": "season-1",
  "trackXpPerInterval": 1
}
```

The `maxObservationGapSeconds` value should be at least one interval. It is an
anti-overcredit ceiling, not a session timeout.

The separate `engagementRewards` policy adds movement proof, hourly scaling,
daily streaks, weekly thresholds, community credits, reward-track XP, and
receipted item airdrops. It tracks every Dune account rather than only linked
Discord accounts. See [`engagement-airdrops.md`](engagement-airdrops.md) for the
configuration, exact activity model, state schema, and delivery tradeoff.

## Signed inbound webhooks

Endpoints:

```text
POST /api/community/webhooks/vote
POST /api/community/webhooks/payment
```

Headers:

```text
Content-Type: application/json
X-DASH-Timestamp: <unix-seconds>
X-DASH-Signature: <hex HMAC-SHA256>
```

The signed bytes are exactly:

```text
<timestamp>.<raw-request-body>
```

Example body:

```json
{"eventId":"provider-unique-123","duneAccountId":42,"amount":5}
```

The endpoint is active only when both the subsystem and that provider's config
entry are enabled. It rejects stale timestamps, missing secrets, invalid HMACs,
non-positive/over-cap credits, duplicate event payload collisions, and oversized
bodies. An exact replay returns the original logical receipt without a second
credit. Terminate TLS at the private ingress or a reviewed external reverse
proxy; do not publish the full admin surface merely to expose these two paths.

The `payment` endpoint is an adapter for a trusted, already-settled provider
event. DASH never handles card data and does not decide whether a payment settled.

## Reward tracks

Tracks are keyed by `(id, version)`. Levels are array order and require strictly
increasing XP thresholds. Progress references are idempotent; a level claim is
unique per account, track, version, and level. Claims produce queue entries, so
the same offline-window and receipt rules apply as purchases.

Changing a track's rewards in place changes the content of future unclaimed
levels. Increment the track version for a new season or materially changed
reward contract.

## Delivery states and operator action

```text
queued/retry -> processing -> delivered
                         \-> failed + atomic refund (definitive failure)
                         \-> reconciliation (ambiguous game outcome)
```

Online players remain in `retry`; this prevents concurrent save/write conflicts.
A preflight failure is definitive and refunds a purchase. An exception after
actual delivery begins is ambiguous because the Dune write and its response are
not one distributed transaction. Such a record enters `reconciliation` and
retains confirmed receipts. Inspect the target inventory and then resolve it as
delivered or failed. Resolving failed applies the refund/stock restoration once.

The worker processes at most one delivery per poll. This bounds load and makes
receipts easy to audit. The manual `tick` action is available for a controlled
canary.

## Admin API

Read status:

```text
GET /api/community/rewards?account_id=42&limit=100
```

Write actions use `POST /api/community/rewards` with an `action` field:

- `sync`
- `link-code`
- `redeem-link`
- `credit` (requires `CREDIT COMMUNITY WALLET`)
- `purchase`
- `track-progress`
- `claim-track`
- `tick`
- `reconcile` (requires `RESOLVE COMMUNITY DELIVERY`)

RBAC maps the route to `community.write`; reads require `read`. Game delivery
still requires the community delivery, global mutation, and item-grant gates.
Every admin and Discord adapter action emits a bounded DASH audit record.

## Validation

```bash
make test-community-rewards
make test-discord-bot
make test-admin-panel-safe-surfaces
make validate
```

Tests cover hash-only one-time linking, immutable and verifiable ledger entries,
credit/webhook/purchase/progress/claim replay, payload collision rejection,
stock version semantics, bounded playtime accrual, delivery success, automatic
refund, ambiguous reconciliation, movement proof and grace, daily/weekly/session
engagement claims, combined reward types, Discord command schemas, and RBAC
routing.

## Recovery

1. Stop or recreate only `admin-panel` so no SQLite writer is active.
2. Preserve the current database and WAL files for evidence.
3. Restore a consistent `community.sqlite3` snapshot.
4. Start/deploy the admin surface and inspect `GET /api/community/rewards`.
5. Require `ledger.ok=true` before resuming delivery.

Do not reconstruct balances from current wallet rows alone. The ledger, purchase,
webhook, stock, claim, and delivery tables are one consistency unit.
