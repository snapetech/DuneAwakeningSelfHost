# Candidate-Bound Game Update Readiness

DASH will not treat “Steam says an update exists” as sufficient authority to
restart a live world. The Update Readiness Center binds a reviewed candidate
image tag and Steam build identity to current recovery, configuration,
reliability, and post-start evidence. It then emits a private HMAC-signed
receipt without downloading, loading, restarting, or mutating the game.

This capability is enabled by default. Browser `game-apply` and certified
scheduled maintenance are fail-closed by default until the current candidate
has a valid, unexpired receipt.

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

The daily scheduler uses the same staged-only apply contract. It performs an
early check before warnings, downgrades an uncertified candidate to a
current-build restart, and makes Admin force a second candidate/receipt
collection before any disconnect or stop. Targeted map restarts cannot change
the farm build. Even a certified candidate is suppressed unless the new
stopped-world backup passes the full verifier. The execution is captured in a
signed maintenance receipt; see [`maintenance-updates.md`](maintenance-updates.md)
and [`maintenance-intelligence.md`](maintenance-intelligence.md).

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
6. the newest RabbitMQ recovery receipt and its authenticated history are
   valid and current, both copied brokers passed inspected networkless boot,
   and the proof confirms no live broker access or created network;
7. the effective Compose model validates;
8. the Landsraad/Coriolis guard passes with the required seven-day cycle;
9. every required post-start/update recovery hook exists and is executable;
10. Desired State is attested with zero open findings and valid integrity;
11. Change Intelligence has a valid ledger and zero open incidents;
12. Operational SLOs are healthy with zero open incidents;
13. fleet-wide incident response readiness is current and verified; and
14. the latest assured deployment receipt is ready, verified, and has no open
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

New certifications use signed schema `dune-update-readiness/v2`; the verifier
continues to authenticate archived `v1` receipts against their original
13-check contract so adding the RabbitMQ gate does not invalidate historical
backup evidence. Semantic verification checks
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
DUNE_DAILY_RESTART_UPDATE_POLICY=certified
```

Changing these container settings requires recreating Admin Panel. Disabling
the receipt requirement removes this additional browser gate; it does not
remove the existing master/update gates, exact confirmation, backup, restart,
post-start hooks, or hostname protections.

The status/metrics collector caches Steam archive and full-backup verification
for five minutes by default; the UI and Prometheus reuse that snapshot. Steam
package inspection does not stream multi-gigabyte image layers. Docker-save
archives are required to be uncompressed and seekable: DASH scans valid
512-byte tar headers only in the first and last 16 MiB, verifies the
`manifest.json` header checksum/type/size, and seeks directly to its payload.
The hard header-read ceiling is 32 MiB per archive and the JSON ceiling is
8 MiB. A manifest outside those windows, a compressed archive, a symlink, a
bad checksum, or malformed JSON fails closed. A stale/missing metrics snapshot
starts one single background refresh and returns immediately, so concurrent
scrapes cannot create a verification thundering herd or exceed Prometheus's
scrape timeout. Explicit certification and game apply always force a fresh collection.
`DUNE_UPDATE_READINESS_POLL_SECONDS` accepts 60..3600 seconds.

The API's package evidence includes the inspection mode, configured byte
ceilings, required/successful archive counts, and measured `durationMs`. These
are diagnostic fields, not part of the candidate fingerprint or authorization
verdict. Overall collection evidence also reports `durationMs`, whether the
collection was forced, and the exact
`newest-manifest-config-direct-dump-leaf` backup-selection policy.

Recovery evidence always selects the newest atomic full-backup directory with a
direct PostgreSQL dump, `manifest.txt`, and config archive. Aggregate parents
such as `backups/admin-panel` may contain years of nested maintenance history
and old loose admin dumps; they are never treated as one backup set. This keeps
forced certification proportional to one recovery set without weakening the
normal verifier applied to that set.

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

The scheduled-maintenance `automatic` policy is likewise rejected while
receipt enforcement is enabled. Certified jobs set acquisition mode to `none`
in both restart execution implementations, so neither a desktop Steam client
nor SteamCMD can run between certification and image ingest.

## Metrics And Alerts

`/metrics/change-intelligence` adds label-free series:

- `dash_update_readiness_collector_up`
- `dash_update_readiness_scheduled_ready`
- `dash_update_readiness_immediate_ready`
- `dash_update_readiness_candidate_update_required`
- `dash_update_readiness_receipt_current`
- `dash_update_readiness_online_players`
- `dash_update_readiness_collection_duration_seconds`
- `dash_update_readiness_package_inspection_duration_seconds`
- `dash_update_readiness_last_certification_timestamp_seconds`

Metrics intentionally omit build IDs, image tags, fingerprints, operators,
backup paths, receipt IDs, and digests. Prometheus alerts when evidence is
invalid, an available candidate is blocked, or an available candidate remains
uncertified. Performance-budget alerts fire when the last complete evidence
collection remains above 15 seconds for five minutes or package inspection
remains above five seconds for five minutes. The production baseline recorded
on 2026-07-16 was 4.502 seconds end-to-end and 0.567 seconds for all six Funcom
archives.

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
failed-check refusal, nested/outer tampering, bounded inputs, first/tail tar
header lookup, corrupt-header and compressed-archive rejection, parsing of
Steam tag/build output, atomic-backup selection, browser and scheduled
execution enforcement, current-build fallback, acquisition-mode isolation,
metrics, and route access.
