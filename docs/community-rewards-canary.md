# Community Rewards synthetic transaction canary

Confidence: high for the isolated runtime proof, receipt semantics, policy and
age binding, HMAC verification, cleanup, and no-live-data boundary.

The Community Rewards readiness row is not promoted merely because its SQLite
database opens. An operator can run the complete wallet/shop/delivery path
against disposable state and retain a portable signed receipt proving that the
currently active policy worked end to end.

## What the canary exercises

The runner loads `config/community-rewards.json`, hashes its exact bytes, and
initializes a new temporary SQLite database. It then performs:

1. catalog synchronization with at least one enabled, in-stock offer and one
   enabled reward track;
2. one-time link-code creation and Discord identity redemption;
3. HMAC webhook verification, first ingestion, and idempotent replay;
4. wallet credit and reference replay;
5. stock-aware purchase and idempotency-key replay;
6. queue claim and synthetic delivery completion;
7. bounded playtime accrual and timestamp replay;
8. movement-proven engagement accounting using the active distance and
   coordinate-precision policy;
9. reward-track progress, level-claim replay, and synthetic delivery; and
10. full append-only ledger hash and running-balance verification.

The synthetic delivery receipt says `gameWrite=false`. It exercises the same
queue claim/completion state machine without invoking the separately gated
item-grant adapter.

## Isolation contract

Every valid receipt must contain this exact semantic proof:

```json
{
  "temporaryDatabaseCreated": true,
  "temporaryStateRemoved": true,
  "liveCommunityDatabaseOpened": false,
  "gameDatabaseOpened": false,
  "gameDeliveryInvoked": false,
  "externalProviderCalled": false
}
```

The verifier rejects changed fields even if the receipt digest is recomputed.
The HMAC covers the complete signed envelope. The temporary directory is
removed before the receipt can pass. No Dune account, player inventory, live
community wallet, offer stock, game database, RabbitMQ route, Discord API, or
payment/vote provider is used.

## Run and inspect

In the dashboard, open **Community Rewards** and select **Run isolated
canary**. The API equivalent is:

```text
POST /api/community/rewards
Content-Type: application/json

{
  "action": "canary",
  "confirm": "RUN COMMUNITY REWARDS CANARY"
}
```

This requires the authenticated `community.write` route capability, global
mutation admission, and the exact confirmation. The operation writes only its
temporary database, audit event, and signed evidence receipt.

`GET /api/community/rewards` returns `canary.currentReady`, the current policy
digest, bounded receipt summaries, isolation flags, and verification state. It
does not return a signing key, link code, claim token, synthetic account ID, or
temporary path.

## Readiness and expiry

The `community-rewards` feature probe returns `canary-proven` only when the
newest receipt:

- has a valid HMAC, nested receipt SHA-256, schema, timestamp, and field set;
- reports all twelve named business-flow checks passing;
- contains the exact isolation contract above;
- matches the SHA-256 of the active private policy; and
- is no older than `DUNE_COMMUNITY_CANARY_MAX_AGE_HOURS`.

The default lifetime is seven days. Any policy byte change immediately returns
the row to `canary-pending`; a stale receipt does the same. Failed canaries are
retained as valid failure evidence and never promote readiness.

```env
DUNE_COMMUNITY_CANARY_MAX_AGE_HOURS=168
DUNE_COMMUNITY_CANARY_RETENTION=200
```

## Evidence and backups

Receipts use schema `dune-community-rewards-canary/v1` and live under:

```text
backups/operator-evidence/community-canary-<id>.signed.json
```

They use the existing private Change Intelligence HMAC key, so the normal
`operator-evidence.tgz` plus matching `config.tgz` is a complete portable
verification unit. Both the host verifier and Admin's native verifier dispatch
this schema to its strict semantic verifier. A backup fails verification if a
receipt, signature, policy digest structure, verdict, or isolation claim is
malformed.

Prometheus exports only label-free values:

```text
dash_community_canary_enabled
dash_community_canary_collector_up
dash_community_canary_current_ready
dash_community_canary_last_completion_timestamp_seconds
dash_community_canary_age_seconds
dash_community_canary_retained_receipts
```

## Failure handling

Inspect `latest.checks` and repair only the named layer. Common failures are an
empty/disabled offer catalog, no enabled reward track, invalid active policy,
or a regression in idempotency, delivery, engagement, or ledger behavior. Do
not edit a receipt or change readiness classification manually. Run the canary
again after fixing the policy or code; the prior failed receipt remains useful
evidence.

## Validation

```bash
make test-community-rewards
make test-feature-readiness
make test-admin-panel-safe-surfaces
make validate
```

The focused suite covers the full synthetic transaction, policy drift, expiry,
HMAC and semantic tampering, incomplete catalogs, failed-receipt retention,
cleanup, API confirmation, and readiness promotion.
