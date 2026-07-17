# Maintenance Intelligence

DASH records every scheduled restart or shutdown execution as a private,
tamper-evident maintenance outcome. The receipt proves:

- the job, authenticated principal, target, action, and update policy;
- whether the candidate was certified or blocked;
- whether the recovery backup was created and independently verified;
- which phases were required, attempted, successful, and how long they took;
- whether recovery ran and the requested service returned online; and
- whether the outcome passed, failed, deferred to reboot, or was a dry run.

This is an always-on server/control-plane feature. It does not run Steam,
touch a game client, mutate game data, or install a host timer.

## Execution Contract

An executed restart follows this state machine:

```text
candidate preflight
  -> clean player disconnect
  -> stop
  -> create backup
  -> verify backup
  -> allowed update phase
  -> start
  -> online proof
  -> bounded recovery and second online proof when needed
  -> signed outcome
```

Backup verification is an admission gate, not a warning. A candidate can be
applied only after the new stopped-world backup passes the same mixed-data
verifier exposed by Infrastructure and `scripts/verify-backup.sh`.

For a restart, a failed backup or update does not justify abandoning service
recovery. DASH disables further acquisition, starts the current available
build, waits for readiness, and invokes bounded recovery when needed. A receipt
can therefore correctly report both:

```text
outcome=failed
serviceRecovered=true
```

The requested maintenance contract failed even though service was restored;
it is never promoted to a successful result. For an intentional shutdown, the
target remains offline and the failed outcome is retained for investigation.

Targeted restarts remain current-build-only. All-farm jobs support `current`,
`certified`, and legacy `automatic`. Automatic acquisition is rejected while
readiness receipts are required.

## Receipt And Integrity Contract

Documents use outer schema `dune-maintenance-outcome/v1` and receipt schema
`1`, stored as:

```text
backups/operator-evidence/maintenance-outcome-<32-hex>.signed.json
```

Each contains a canonical receipt digest, HMAC-SHA256 signature, and signing
key fingerprint. Verification checks the cryptography and these semantics:

- exact fields and bounded identifiers, text, timestamps, and durations;
- outcome consistency with `ready`, `dryRun`, and `deferred`;
- update-applied implying update-attempted;
- backup proof matching the backup stage;
- recovery status matching the recovery stage;
- required-but-unattempted phases represented as failed, not omitted; and
- `gameDataMutationExecuted=false`.

The existing private Change Intelligence HMAC key signs receipts. Files are
mode `0600`, the directory is `0700`, writes are exclusive, fsynced, and
atomically replaced, and root-run Admin restores the configured host owner.

`DUNE_MAINTENANCE_OUTCOME_RETENTION` controls retention. The default is `400`
and bounds are `10..5000`. Pruning only matches maintenance-outcome filenames;
it does not remove deployment, update-readiness, or incident evidence.

## Admin And API

Operations provides an update-policy selector, automatically forces targeted
jobs to `current`, explains the verification/recovery behavior, and displays
recent receipts with retained/pass/fail/integrity totals.

Read history with the normal `read` capability:

```http
GET /api/ops/maintenance-history?limit=100
```

The response includes `latest`, bounded `receipts`, `summary`, retention, and
per-row verification. Malformed or tampered files set `ok=false`; they are not
silently discarded.

Scheduling remains an `operations.write` action:

```json
{
  "target": "all",
  "action": "restart",
  "delay": "30min",
  "execute": true,
  "backup": true,
  "update_policy": "certified"
}
```

Admin injects the authenticated principal server-side. A caller cannot forge
receipt attribution through the request body. System plans use `system`.

## Metrics

`GET /metrics/change-intelligence` exports label-free metrics:

```text
dash_maintenance_outcome_collector_up
dash_maintenance_outcome_latest_ready
dash_maintenance_outcome_latest_backup_verified
dash_maintenance_outcome_latest_service_recovered
dash_maintenance_outcome_latest_duration_seconds
dash_maintenance_outcome_last_completion_timestamp_seconds
dash_maintenance_outcome_retained_receipts
dash_maintenance_outcome_retained_failures
```

`collector_up=0` means initialization, key access, parsing, HMAC, digest, or
semantic verification failed. No receipts is a healthy zero-count state.
The shipped Prometheus rules alert on invalid evidence and on a latest failed
outcome once at least one receipt exists.

## Backup And Recovery

Receipts are included in `operator-evidence.tgz`. Both the Admin-native and
shell backup verifiers dispatch this schema to its semantic verifier using the
matching Change Intelligence key from the config archive. Unknown schemas,
missing keys, unsafe archive members, invalid signatures, or inconsistent
receipts fail verification.

A receipt is written after its own pre-maintenance backup, so that backup
cannot contain the receipt describing itself. The live evidence file is
available immediately and the next backup includes it.

Recovery:

1. Restore `config/secrets/change-intelligence-hmac.secret` as mode `0600`.
2. Restore the `maintenance-outcome-*.signed.json` files to the configured
   evidence directory.
3. Start/recreate Admin only.
4. Load Operations or call the history API.
5. Confirm `ok=true` and `dash_maintenance_outcome_collector_up 1`.

Do not delete invalid evidence to turn the collector green. Preserve it and
recover the matching key/history.

## Validation And Deployment Closure

```bash
make test-maintenance-outcomes
make test-admin-panel-safe-surfaces
make test-deployment-assurance
make validate
```

The assured deployment manifest and push helper always include
`admin/maintenance_outcomes.py`, so Admin cannot be promoted with a verifier
entrypoint that lacks its schema implementation.
