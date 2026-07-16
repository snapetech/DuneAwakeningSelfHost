# Movement-Verified Engagement Airdrops

Confidence: high for activity accounting, streak/threshold claims, isolated
credit and reward-track writes, item-queue creation, replay resistance, and
offline delivery safety. Confidence: moderate for how frequently the game
persists pawn transforms during every activity type; stationary crafting may
not refresh coordinates and therefore deliberately earns no movement proof.

This feature extends the community-rewards worker with configurable active-play
rewards. It covers the playtime, anti-AFK, daily-streak, weekly-attendance, and
scaled-drop outcomes found in the public `atobo/dune-airdrop-addon`, while
keeping game-table triggers and Docker-socket access out of the reward engine.

## Outcome

One worker poll can:

1. read every Dune account's online state and persisted pawn transform;
2. prove activity through map/partition change or a configurable 3D movement
   distance;
3. accrue only the bounded interval since the preceding online observation;
4. apply a short activity grace window after proven movement;
5. issue scaled active-session, consecutive-day, and weekly-active-time
   rewards exactly once; and
6. queue item rewards through the existing receipted offline-delivery state
   machine.

Coordinates are rounded to a configurable world-unit grid before persistence;
the default is 10 units. Missing coordinates, an offline player, a replayed timestamp, a backward clock,
or an observation gap beyond the configured maximum never creates active time.
The worker tracks all Dune accounts, including accounts not yet linked to
Discord. A later Discord link exposes the already-isolated wallet and track
progress for that account.

## Why This Path Is Different

The surveyed airdrop addon installs triggers and reward tables directly in the
`dune` schema and runs a companion container with read-only Docker-socket access
to invoke a host command. DASH instead uses:

- the existing admin worker's read-only Dune query connection;
- a private SQLite state database under `backups/community-rewards/`;
- an append-only reward-claim table;
- the hash-chained community-credit ledger;
- versioned reward-track progress;
- the existing one-at-a-time item delivery queue; and
- the existing mutation/item-grant gates only when item delivery actually
  occurs.

This removes a privileged companion daemon and does not add triggers or
tracking tables to Funcom's database. The tradeoff is deliberate: item rewards
wait for a safe offline window instead of attempting an uncertain concurrent
inventory write while the player is online.

## Activity Model

Each account has one checkpoint containing:

- previous observation time and online state;
- map, partition, and XYZ coordinates;
- last movement-proof time;
- active-session start and accumulated seconds; and
- the number of session-hour rewards already issued.

Movement is proven when either the map/partition changes or Euclidean 3D
distance reaches `minimumMovementDistance`. Once movement is proven,
`movementGraceSeconds` permits short stationary periods without requiring every
poll to contain a changed transform. Elapsed time is capped by
`maxObservationGapSeconds`, even inside the grace window.

`coordinatePrecision` rounds X/Y/Z before writing the checkpoint. Set it well
below `minimumMovementDistance`; the committed 10/50 defaults preserve useful
movement evidence without retaining the exact transform in reward state.

Disconnecting or missing the maximum observation gap closes the active session.
The next online observation establishes a fresh session baseline and cannot
itself earn time.

## Reward Policy

The active policy lives in `config/community-rewards.json`; the committed
example is `config/community-rewards.example.json`.

```json
{
  "engagementRewards": {
    "enabled": true,
    "maxObservationGapSeconds": 120,
    "minimumMovementDistance": 50,
    "coordinatePrecision": 10,
    "movementGraceSeconds": 180,
    "hourly": {
      "enabled": true,
      "intervalSeconds": 3600,
      "maxRewardsPerSession": 6,
      "tiers": [
        {"fromHour": 1, "reward": {"credits": 2}},
        {"fromHour": 3, "reward": {"credits": 4}}
      ]
    },
    "daily": {
      "enabled": true,
      "repeatLast": true,
      "tiers": [
        {"day": 1, "reward": {"credits": 5}},
        {"day": 7, "reward": {"credits": 20}}
      ]
    },
    "weekly": {
      "enabled": true,
      "thresholds": [
        {"activeSeconds": 7200, "reward": {"credits": 25}}
      ]
    }
  }
}
```

Hourly `fromHour` tiers scale the reward for each completed interval. The
greatest tier at or below the earned hour wins, up to
`maxRewardsPerSession`. The interval name is retained for readability; an
operator can choose a shorter interval for testing.

Daily rewards use UTC calendar days. Consecutive activity days increment the
streak; a missed UTC day resets it to one. With `repeatLast=false`, only exact
tier days issue a reward. With `repeatLast=true`, the greatest configured tier
at or below the current streak issues once per active day.

Weekly thresholds use ISO weeks and active seconds, not login count. Every
configured threshold crossed during a week issues once. A single observation
may cross multiple thresholds without losing a claim.

## Reward Types

A reward object can combine all three forms:

```json
{
  "credits": 10,
  "track": {"id": "season-1", "xp": 5},
  "items": [
    {
      "type": "item",
      "templateId": "WaterPack_Consumable",
      "count": 1,
      "qualityLevel": 0
    }
  ]
}
```

- `credits` append to the immutable community ledger.
- `track` updates the newest enabled version of the named reward track with an
  idempotent source marker.
- `items` create one delivery containing the normalized item list.

All effects and the append-only engagement claim commit in one SQLite
transaction. A missing reward track or invalid policy rejects the operation
instead of partially issuing the remaining reward. Config save also rejects a
track reference that is absent or disabled in the same versioned policy.

## State and Audit

The SQLite schema adds:

- `engagement_checkpoints` for online/activity/session state;
- `engagement_days` for UTC active seconds and streaks;
- `engagement_weeks` for ISO-week active seconds; and
- `engagement_claims` for immutable issuance receipts.

Claim uniqueness is `(account, kind, period, tier)`. SQLite triggers reject
claim update or deletion. Item delivery state remains separately visible as
`queued`, `retry`, `processing`, `delivered`, `failed`, or `reconciliation`.

The Community Rewards dashboard shows policy state, movement threshold, grace,
tracked accounts, active-today count, claim totals, and per-account checkpoint,
day, week, claim, ledger, track, and delivery rows.

## Activation and Operations

The normal parity activator installs the committed example when no active
community policy exists:

```bash
scripts/enable-feature-parity.sh .env --execute
```

For an existing private community policy, the activator runs
`scripts/merge-community-engagement-policy.py`. It adds only the absent
`engagementRewards` block and any referenced example track that is genuinely
missing. Private offers, currency, webhooks, playtime policy, and existing
tracks remain unchanged. An operator-authored engagement block is never
overwritten; a disabled required track fails closed. The candidate policy is
fully initialized in a temporary SQLite database before replacement, the old
file is copied mode `0600` under
`backups/admin-panel/config-upgrades/`, and the final write is same-directory,
fsync-backed, and atomic. Use the helper's `--dry-run` flag to inspect a direct
upgrade outside the aggregate activator.

After activation, review the policy in the Community Rewards dashboard and run
one manual tick. Recreating the admin panel is unnecessary for a policy-only
change.

Item deliveries still require:

```dotenv
DUNE_COMMUNITY_REWARDS_ENABLED=true
DUNE_COMMUNITY_DELIVERY_ENABLED=true
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
```

Credit and track rewards remain in isolated state when item delivery is paused.
The dashboard exposes queued/retry/reconciliation counts before an operator
enables delivery.

## Validation

```bash
make test-community-rewards
python3 -m unittest scripts/test-merge-community-engagement-policy.py
make test-admin-panel-safe-surfaces
make validate
```

The focused suite proves movement and missing-coordinate behavior, bounded
grace, replay rejection, daily continuation/reset, scaled session rewards,
weekly threshold crossing, combined ledger/track/item issuance, offline session
reset, policy ordering validation, append-only claims, and delivery queue
creation.
