# Base Pack-Up Cooldown

## Outcome

DASH can inspect the pack-up timestamp recorded on every active base totem and,
when an operator deliberately chooses one, reset that exact timestamp to zero.
The workflow is available from **Creator → Portable Base Creator → Base Pack-Up
Cooldown** and the authenticated Admin API.

This closes the operator outcome added by `bsmr/dapdsm` v0.5.0 while adding
stopped-map and offline-owner admission, a content-bound preview, a full
database dump, transactional compare-and-swap, readback verification, private
receipts, RBAC, audit-ledger admission, and optional change governance.

Confidence is **high** that `dune.totems.last_backup_timestamp` is the current
build's persisted cooldown input and that DASH safely resets the selected value
to zero. Confidence is **unknown** for a numeric remaining-duration estimate:
the current production schema exposes no verified world-time relation that can
convert this value into seconds. DASH therefore reports the raw timestamp and
whether it is zero; it never invents a countdown.

## Evidence and provenance

The 2026-07-17 ecosystem refresh inspected
[`bsmr/dapdsm`](https://github.com/bsmr/dapdsm) at
`900915eb35bb11708d85add4b86090709d34519c` (`v0.5.0`). Its `ds-mentat base`
commands list player-owned totems and reset
`dune.totems.last_backup_timestamp`. Its world-time query is explicitly a
placeholder, so that source does not prove remaining-seconds semantics.

A read-only check against the current production schema on `kspls0` established
that:

- `dune.totems.last_backup_timestamp` exists as `bigint`;
- the live table contained 114 totems, including 111 nonzero values;
- the observed range was zero through 32,482,799; and
- no verified `dune.game_time` or equivalent world-time table was present.

No production cooldown was reset while deriving or deploying this feature.

## Dashboard workflow

The base table now includes:

- totem actor ID and name;
- verified owner references and their online state;
- map, partition, and active/stopped state;
- piece and placeable counts;
- the raw `last_backup_timestamp`; and
- a `cleared` state when the timestamp is zero.

Select **Cooldown**, then **Inspect and preview reset**. Preview is read-only.
It returns the exact source column, previous and resulting values, blockers,
SHA-256 fingerprint, and required confirmation phrase:

```text
RESET BASE COOLDOWN <totem_id>
```

The Reset button remains disabled unless the global mutation gate and dedicated
cooldown gate are loaded and the current preview is executable.

## Admission and transaction contract

Execution requires all of the following:

1. The target map is stopped and its partition has no active server.
2. Every matched current owner is explicitly `Offline`, `Disconnected`, or
   `Inactive`. Unknown state is blocked.
3. The timestamp is nonzero; an already-cleared totem is a blocker.
4. The global mutation gate and
   `DUNE_ADMIN_BASE_COOLDOWN_MUTATIONS_ENABLED` are enabled.
5. The request supplies the exact current 64-character content fingerprint.
6. The operator types `RESET BASE COOLDOWN <totem_id>` exactly.
7. The request has `world.write` authority and passes configured audit,
   change-contract, and approval policy.

The mutation then:

1. opens a serializable transaction and sets a bounded statement timeout, so a
   conflicting concurrent map/player/base change aborts rather than committing
   from stale evidence;
2. takes a totem-scoped PostgreSQL advisory lock;
3. row-locks the totem, actor, world partition, permissions, and matched player
   states;
4. rebuilds the plan and rejects fingerprint drift or a new blocker;
5. creates a non-empty full custom-format PostgreSQL dump;
6. writes a private pending receipt;
7. performs an exact compare-and-swap from the previewed timestamp to zero;
8. reads the selected row back and requires zero;
9. commits only after verification; and
10. finalizes the private committed receipt.

The affected map must remain stopped throughout the operation. DASH does not
start, stop, or restart any map from this endpoint. After a successful reset,
start the map through the guarded Operations workflow so the repository's
post-start hooks run.

## API

Read the bounded base inventory, both feature gates, and receipt metadata:

```http
GET /api/admin/base-retirement?limit=500
```

Create a read-only reset preview:

```http
POST /api/admin/base-retirement
Content-Type: application/json

{
  "action": "cooldown-preview",
  "totemId": 1234
}
```

Execute the exact preview:

```http
POST /api/admin/base-retirement
Content-Type: application/json

{
  "action": "cooldown-reset",
  "totemId": 1234,
  "expectedFingerprint": "<64 lowercase hex characters>",
  "confirm": "RESET BASE COOLDOWN 1234"
}
```

The result explicitly reports `mapRestartRequired=true` and
`mapLifecycleInvoked=false`.

## Configuration and activation

The dedicated mutation gate defaults off:

```dotenv
DUNE_ADMIN_BASE_COOLDOWN_MUTATIONS_ENABLED=false
```

Fresh parity installations can preview and execute the complete gate set with:

```bash
./scripts/enable-feature-parity.sh .env
./scripts/enable-feature-parity.sh .env --execute
```

On the live deployment, verify `hostname` returns `kspls0` before changing the
gate. Recreate only the Admin control plane through the normal assured
deployment path; do not restart a game map to load this dashboard feature.

## Evidence, rollback, and failures

Artifacts are private:

```text
backups/admin-panel/<timestamp>-<nonce>-<database>.dump
backups/admin-panel/base-cooldown/pending-cooldown-<receipt>.json
backups/admin-panel/base-cooldown/base-<totem>-cooldown-<receipt>.json
```

The full database dump is the authoritative rollback artifact. A failure before
commit rolls the transaction back. A pending receipt remains after a
post-backup/pre-commit failure so the operator can distinguish “backup created”
from “write committed.” If final receipt creation fails after commit, the API
truthfully returns `committed=true` and
`receiptStatus=pending-finalization-failed` rather than claiming rollback.

## Validation

```bash
make test-base-retirement
make test-creator-canary
make test-admin-panel-safe-surfaces
make test-feature-readiness
docker compose --env-file .env.example config --quiet
make validate ENV_FILE=.env.example
```

The focused tests cover raw timestamp normalization, already-cleared,
active-map and online-owner blockers, unknown countdown semantics, exact
confirmation, stale fingerprints, backup-before-write ordering,
compare-and-swap, readback verification, receipts, independent gates, Admin UI
source integration, and disposable Creator/Modding canary coverage.
