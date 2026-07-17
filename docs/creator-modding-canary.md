# Creator and Modding isolated lifecycle canary

## Outcome and evidence boundary

The Creator/Modding readiness row is promoted only by a current, signed proof
that the checked-in implementation and active catalogs complete their supported
lifecycles. The canary runs entirely in a private temporary directory. It does
not open the live gallery or game database, write live configuration or player
state, invoke map lifecycle, or call an external network service.

This proof covers the implemented creator and server-modding contract. It does
not claim direct live base placement, visual rendering of every cosmetic, or a
real-player mutation. Those claims retain their feature-specific evidence
boundaries.

## What one run proves

The receipt binds the exact SHA-256 and size of:

- `admin/addon_admin.py`;
- `admin/base_creator.py`;
- `admin/base_retirement.py`;
- `admin/cosmetics_admin.py`;
- `admin/creator_canary.py`;
- `admin/gameplay_presets.py`;
- all three active `config/UserGame*.ini` targets;
- `config/cosmetic-catalog.json`; and
- `config/gameplay-presets.json`.

Against those inputs, the canary runs these real implementation paths:

1. Exports a synthetic live-base query result and verifies exact components,
   centroid recentering, content digest, and `gameRestoreSupported=false`.
2. Initializes a temporary gallery, publishes a private design, rates it,
   updates it to public, and lists it through the normal gallery API.
3. Plans recoverable retirement and pack-up cooldown reset from ready and
   blocked query fixtures, proving the offline/stopped-map/native-function,
   already-cleared, backup, raw-timestamp, and no-automatic-lifecycle contracts
   refuse unsafe rows.
4. Copies all three active `UserGame` targets, finds an effective checked-in
   preset, previews it, applies it atomically, rolls it back, and compares the
   final bytes with the original.
5. Verifies that both Standard PvE configurations still retain the mandatory
   seven-day Landsraad Coriolis cycle.
6. Loads the full active cosmetic catalog, exercises add/replay/remove and bulk
   unlock planning, preserves unknown existing IDs, and excludes inventory-mode
   tokens from customization unlocks.
7. Builds a bounded in-memory addon index, remote manifest, and ZIP; installs it
   through the real SHA-pinned installer, enables it, enforces its approved
   permission, resolves its content path, removes it, and verifies recovery.
8. Re-hashes every source input after execution and refuses readiness if any
   module, catalog, or active target changed.
9. Removes the entire temporary state tree before signing the result.

The addon installer accepts an injected fetch function only for this closed
fixture path. Normal dashboard installation still uses the existing bounded
HTTPS fetcher and host allowlist.

## Run it

Open **Creator → Portable Base Creator** and select **Run isolated canary**.
The authenticated API equivalent is:

```http
POST /api/creator/bases
Content-Type: application/json

{"action":"canary","confirm":"RUN CREATOR MODDING CANARY"}
```

The request requires the normal `creator.write` capability, the global mutation
admission gate, exact typed confirmation, change-contract admission when
configured, and the append-only audit ledger. The gate classifies an explicit
proof run; it does not make the run touch production gameplay state.

Read current evidence with:

```http
GET /api/creator/bases
```

The `canary` object reports current readiness, input digest and file manifest,
latest receipt, age policy, retention, and explicit isolation booleans.

## Signed receipt and readiness

Receipts use schema `dune-creator-modding-canary/v1` and the Change
Intelligence HMAC key. They are private files under:

```text
backups/operator-evidence/creator-canary-<32 lowercase hex>.signed.json
```

Each receipt contains:

- principal, start/completion time, and measured duration;
- one digest over the exact bound input manifest;
- all twelve Boolean checks;
- bounded counts for input files, gallery rows/ratings, cosmetics, addon
  permissions, and retirement blockers;
- selected preset and exact target;
- eight explicit isolation assertions;
- a semantic `ready` verdict and receipt SHA-256; and
- outer HMAC signature and signing-key fingerprint.

Receipt verification rejects unknown/missing fields, invalid identifiers,
impossible times/counts, inconsistent verdicts, receipt tampering, or HMAC
tampering. Current-readiness evaluation separately rejects input drift and
expiry. A failed execution is still signed and retained, but cannot promote
readiness. A successful receipt remains cryptographically valid after input
drift or expiry while `currentReady` becomes false.

The `creator-modding` Feature Readiness row uses
`operator-canary-pending`. It returns `ready` only when the latest receipt is
valid, passing, bound to the current inputs, and younger than the configured
maximum age.

## Configuration

```dotenv
DUNE_CREATOR_CANARY_MAX_AGE_HOURS=168
DUNE_CREATOR_CANARY_RETENTION=200
```

Maximum age is bounded to 1–2160 hours. Retention is bounded to 10–2000
receipts. The defaults require a fresh proof weekly and retain 200 results.
Changing either value requires recreating the admin-panel container.

## Metrics and alerts

The authenticated `/metrics/change-intelligence` endpoint exports label-free
series:

```text
dash_creator_canary_enabled
dash_creator_canary_collector_up
dash_creator_canary_current_ready
dash_creator_canary_last_completion_timestamp_seconds
dash_creator_canary_age_seconds
dash_creator_canary_retained_receipts
```

`DashCreatorCanaryCollectorInvalid` fires when evidence cannot be verified.
`DashCreatorCanaryNotCurrent` fires when the feature is enabled without a
current passing proof.

## Backup, restore, and recovery

Full backups include signed receipts in `operator-evidence.tgz` and the matching
Change Intelligence HMAC key in the private configuration archive. Both the
host `scripts/verify-backup.sh` path and the admin-panel verifier dispatch by
schema and perform full cryptographic plus semantic verification.

After restoring a backup, run its normal verifier. If the receipt is stale or
its input digest differs from the restored/current code and catalogs, do not
edit it. Run a new canary. A failed receipt should be preserved for diagnosis;
its failed check names identify the subsystem to inspect.

## Validation

```bash
make test-creator-canary
python3 -W error::ResourceWarning -m unittest scripts/test-admin-panel-safe-surfaces.py
make test-feature-readiness
make test-deployment-assurance
docker compose --env-file .env.example config >/dev/null
make validate
```

The focused tests cover the complete lifecycle, strict isolation, exact input
binding, drift, expiry, signed failed receipts, HMAC tampering, semantic
tampering, metrics, alert wiring, backup dispatch, feature-readiness wiring, and
assured-deployment support-file binding.
