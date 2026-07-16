# Candidate-Bound Game Update Readiness

DASH will not treat “Steam says an update exists” as sufficient authority to
restart a live world. The Update Readiness Center binds a reviewed candidate
image tag and Steam build identity to current recovery, configuration,
reliability, and post-start evidence. It then emits a private HMAC-signed
receipt without downloading, loading, restarting, or mutating the game.

This capability is enabled by default. Browser `game-apply` is fail-closed by
default until the current candidate has a valid, unexpired receipt.

The browser flow is deliberately split:

```text
stage Steam candidate -> inspect -> certify exact candidate -> apply staged candidate
```

`game-stage` runs the existing Steam acquisition tool but does not load Docker
images, write the active image tag, stop/recreate containers, or touch game
state. After certification, `game-apply` revalidates the live candidate and
sets `DUNE_RESTART_STEAM_UPDATE_MODE=none` for the guarded restart workflow.
The restart can load and activate the already-staged candidate, but it cannot
silently fetch a different Steam build after certification.

Admin Panel's minimal image intentionally contains no Bash or Docker CLI. Stage
and apply therefore run in a short-lived, uniquely named
`DUNE_RESTART_COMPOSE_IMAGE` helper through the mounted Docker socket. The
helper mounts only the configured host workspace and Steam directory, uses the
normal repository scripts, captures bounded logs, and is forcibly removed.
Before creation, DASH reads Docker `/info` and requires the exact configured
host name; the default is `kspls0`.

## What Certification Proves

A scheduled-update receipt is issued only when every check is true:

1. The local Steam package exposes exactly one bounded Funcom server image tag.
2. All required image archives exist and the package check has a recognized
   current, update-available, or same-tag-reload result.
3. `buildid` and `TargetBuildID` do not show an incomplete Steam download.
4. the newest recognized full backup passes the normal mixed-evidence verifier;
5. the newest isolated restore drill has valid integrity/policy/hash results,
   meets the configured proof-freshness policy, and confirms no live DB access;
6. the effective Compose model validates;
7. the Landsraad/Coriolis guard passes with the required seven-day cycle;
8. every required post-start/update recovery hook exists and is executable;
9. Desired State is attested with zero open findings and valid integrity;
10. Change Intelligence has a valid ledger and zero open incidents;
11. Operational SLOs are healthy with zero open incidents;
12. fleet-wide incident response readiness is current and verified; and
13. the latest assured deployment receipt is ready, verified, and has no open
    or overdue change window.

`scheduledReady` allows online players because the existing update path has a
warning and controlled soft-disconnect phase. `immediateReady` additionally
requires zero online players. The UI displays both instead of conflating a
safe scheduled maintenance plan with permission to interrupt active players.

## Candidate Binding And Expiry

The canonical candidate includes:

- current and candidate Funcom image tags;
- Steam installed, target, and last-loaded build IDs when available;
- `current`, `update-available`, or `reload-required` status;
- whether the candidate actually requires an update; and
- a SHA-256 fingerprint over that complete identity.

The receipt is valid only for the exact fingerprint. A newly downloaded Steam
build, a changed image tag, same-tag hotfix, or status transition invalidates
the old receipt. Receipts default to a one-hour lifetime and can be configured
from five minutes to 24 hours.

The signed schema is `dune-update-readiness/v1`. Semantic verification checks
the nested candidate fingerprint, exact check set, scheduled/immediate verdict
derivation, expiration, receipt SHA-256, outer HMAC, and the explicit
`updateExecuted=false` / `gameMutationExecuted=false` claims. Evidence files
are mode `0600` under `backups/operator-evidence/` and use the existing private
Change Intelligence HMAC key. Full backups include them, and both host and
minimal-container backup verifiers dispatch by schema and independently verify
the receipt with the matching archived key.

## Dashboard And API

Infrastructure → Updates displays the exact candidate, failed checks, online
player count, latest receipt, expiration, and scheduled/immediate verdicts.

Read-only status:

```http
GET /api/ops/update-readiness
Authorization: Bearer <token>
```

Certification writes evidence only and requires `infrastructure.write`:

```http
POST /api/ops/update-readiness
Authorization: Bearer <token>
Content-Type: application/json

{"confirm":"CERTIFY GAME UPDATE READINESS"}
```

The server recollects every input during certification. Clients cannot submit
checks, player counts, candidate identity, backup paths, or verdicts.

When `DUNE_UPDATE_REQUIRE_READINESS_RECEIPT=true`, `POST /api/ops/updates` with
`action=game-apply` recollects current state and refuses unless the newest
receipt is still valid, unexpired, candidate-matched, and scheduled-ready. The
normal guarded full-farm backup/update/restart/post-hook workflow remains the
only execution path after the gate passes.

Stage first through `POST /api/ops/updates` with:

```json
{"action":"game-stage","confirm":"STAGE GAME UPDATE"}
```

This is a protected host-package write, so it uses the master update mutation
gate and `infrastructure.write`; its response explicitly records
`containersTouched=false` and `gameMutationExecuted=false`.

## Configuration

```env
DUNE_UPDATE_READINESS_ENABLED=true
DUNE_UPDATE_REQUIRE_READINESS_RECEIPT=true
DUNE_UPDATE_READINESS_TTL_SECONDS=3600
DUNE_UPDATE_READINESS_POLL_SECONDS=300
DUNE_UPDATE_READINESS_STEAM_DIR=/steam-server
DUNE_UPDATE_READINESS_REQUIRED_HOST=kspls0
DUNE_HOTFIX_AUTO_APPLY_WITHOUT_READINESS=false
```

Changing these container settings requires recreating Admin Panel. Disabling
the receipt requirement removes this additional browser gate; it does not
remove the existing master/update gates, exact confirmation, backup, restart,
post-start hooks, or hostname protections.

The status/metrics collector caches its bounded but comparatively expensive
Steam archive and full-backup verification for five minutes by default; the UI
and Prometheus reuse that snapshot. A stale/missing metrics snapshot starts one
single background refresh and returns immediately, so concurrent scrapes cannot
create a verification thundering herd or exceed Prometheus's scrape timeout.
Explicit certification and game apply always force a fresh collection.
`DUNE_UPDATE_READINESS_POLL_SECONDS` accepts 60..3600 seconds.

Compose mounts `DUNE_STEAM_SERVER_DIR` read-only at
`DUNE_UPDATE_READINESS_STEAM_DIR` for native Python inspection. This fixes the
minimal Admin image boundary without granting the long-lived panel write
access to Steam content. Only the short-lived, explicitly confirmed stage/apply
helper receives a writable Steam bind.

The unattended hotfix timer follows the same trust boundary. With receipt
enforcement enabled and the legacy opt-out false, it acquires and validates the
Steam package, then exits before image load, active-tag writes, or restart. The
candidate metrics/alerts request operator review. Setting
`DUNE_HOTFIX_AUTO_APPLY_WITHOUT_READINESS=true` restores the previous fully
automatic stage/load/restart behavior and is intentionally explicit.

## Metrics And Alerts

`/metrics/change-intelligence` adds label-free series:

- `dash_update_readiness_collector_up`
- `dash_update_readiness_scheduled_ready`
- `dash_update_readiness_immediate_ready`
- `dash_update_readiness_candidate_update_required`
- `dash_update_readiness_receipt_current`
- `dash_update_readiness_online_players`
- `dash_update_readiness_last_certification_timestamp_seconds`

Metrics intentionally omit build IDs, image tags, fingerprints, operators,
backup paths, receipt IDs, and digests. Prometheus alerts when evidence is
invalid, an available candidate is blocked, or an available candidate remains
uncertified.

## Failure And Recovery

- **Package unknown/incomplete:** finish Steam acquisition; do not guess a tag.
- **Backup or restore proof fails:** repair recovery coverage first, then
  recollect and certify.
- **Coriolis fails:** restore the mandatory seven-day Standard PvE cycle before
  any map restart.
- **Desired/SLO/change/readiness fails:** resolve the named evidence gap. A
  certification cannot waive it.
- **Candidate changed:** review and certify the new fingerprint.
- **Steam acquisition needed:** run `game-stage`, then reload the evaluation;
  never certify an old candidate and allow the apply phase to fetch another.
- **Receipt expired:** recollect; do not extend or edit the signed file.
- **Players online:** scheduled readiness may pass, but immediate readiness
  remains false. Use the normal warning/soft-disconnect maintenance path.
- **Tampered receipt or wrong HMAC key:** backup verification and the live gate
  fail closed. Restore the matching key/evidence layer from a verified backup.

## Validation

```bash
make test-update-readiness
make test-hotfix-update-readiness
make test-admin-panel-safe-surfaces
make test-admin-access-control
docker compose --env-file .env.example config --quiet
```

The test suite covers candidate binding, expiry, online-player semantics,
failed-check refusal, nested/outer tampering, bounded inputs, parsing of Steam
tag/build output, browser execution enforcement, metrics, and route access.
