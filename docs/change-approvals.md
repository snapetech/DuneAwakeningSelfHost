# Four-Eyes Change Approvals

DASH can require two distinct named operators for high-impact mutations. The
requester submits the exact API body, a second operator reviews a redacted
representation and approves it, and only the original requester may consume
that approval for one exact request attempt.

No surveyed Dune: Awakening hosting stack provides request-body-bound,
capability-aware, single-use dual control with a tamper-evident ledger.
Confidence is `high` for local enforcement, identity separation, request/state
integrity, expiry, replay refusal, and concurrent consumption. Runtime behavior
of the governed game mutation remains at the confidence level documented for
that mutation.

## Enable it

Dual control requires RBAC and at least two named identities with the relevant
capability:

```dotenv
DUNE_ADMIN_REQUIRE_TOKEN=true
DUNE_ADMIN_RBAC_ENABLED=true
DUNE_ADMIN_DUAL_CONTROL_ENABLED=true
DUNE_ADMIN_DUAL_CONTROL_POLICY=critical
DUNE_ADMIN_DUAL_CONTROL_TTL_SECONDS=900
```

Policies are cumulative:

| Policy | Enforced risk levels |
| --- | --- |
| `critical` | critical only |
| `high` | critical and high |
| `all` | critical, high, and standard |

The lifetime is bounded to 60–3,600 seconds. Configuration changes require an
Admin Panel recreate. If dual control is enabled without RBAC, governed
mutations fail closed.

Create identities with `scripts/admin-access.py`; see
[`admin-access-control.md`](admin-access-control.md). The owner recovery token
is a named `owner-recovery` principal and may participate, but it cannot be both
requester and approver.

## Governed operations

The active policy catalogue is returned by `GET /api/security/approvals` and
shown on the Security page. The implementation currently classifies:

- `critical`: backup restore, arbitrary database row/write SQL and password
  changes, game/stack update application, environment changes, base retirement,
  character-slot execution, blueprint import/delete, cosmetic writes/rollback,
  and gameplay-preset apply/rollback;
- `high`: persistent player progression/recovery/runtime actions, player
  teleport/vehicle/item/currency/Solari/XP/economy changes, Landsraad/faction/
  journey/guild/world/permission/access-code changes, and ban policy changes;
- `standard`: service control, memory/autoscaler changes, executable restart
  scheduling, and generic GM execution.

Route-aware predicates exclude previews, dry runs, read-only SQL, update checks,
and other non-mutating actions. Existing feature gates, exact confirmation
phrases, Offline/Online checks, backups, transactions, and post-verification
still apply after approval. Approval never replaces an existing safeguard.

## Browser workflow

Open **Security → Four-eyes Change Control**.

1. The requester chooses a governed path, enters a summary and lifetime, and
   pastes the exact JSON body they intend to execute. Include `dry_run=false`
   and the route's normal confirmation phrase.
2. A second operator signs in with a distinct identity. They review the path,
   risk, capability, HMAC, summary, and redacted request body, then approve or
   reject it.
3. The requester may execute the locally retained draft while the page remains
   open, or arm the approval for the next matching feature-page POST.

Arming is path-scoped. The browser sends `X-DASH-Approval-ID` only to the next
POST for that exact path, then clears the armed value. The server still refuses
any body mismatch.

The executable plaintext body remains only in the requester's browser memory.
It is not persisted in localStorage, sessionStorage, the approval database, the
admin audit, metrics, or the reviewer's browser. Reloading the page discards the
local executable draft; the requester can still arm the approval and reproduce
the exact body through the normal feature UI or an API client.

## API workflow

Requester:

```bash
BODY='{"action":"add-intel","account_id":123,"amount":100,"dry_run":false,"confirm":"WRITE PLAYER PROGRESSION"}'

curl -sS -H "Authorization: Bearer $REQUESTER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$(jq -cn --argjson body "$BODY" '{action:"request",targetPath:"/api/admin/player-maintenance",summary:"Grant reviewed Intel",requestBody:$body}')" \
  https://SERVER/api/security/approvals
```

Approver:

```bash
curl -sS -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"action":"approve","approvalId":"APPROVAL_ID"}' \
  https://SERVER/api/security/approvals
```

Original requester, before expiry:

```bash
curl -sS -H "Authorization: Bearer $REQUESTER_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'X-DASH-Approval-ID: APPROVAL_ID' \
  -d "$BODY" \
  https://SERVER/api/admin/player-maintenance
```

The approval is consumed atomically before downstream dispatch. This prevents
concurrent replay: only one execution attempt can pass the approval gate. If a
later feature gate, confirmation, backup, database, or game operation fails,
the approval remains consumed and a new reviewed request is required. This is
deliberate fail-closed behavior.

## Integrity and privacy

Private state lives under `backups/admin-panel/`:

```text
change-approvals.sqlite3
change-approvals.key
```

Full backups preserve these as an inseparable pair and verify the complete
request/event HMAC history. Restore them together with
`scripts/restore-state.sh --change-approvals`; a database without its matching
key, or a key without its database, fails closed. Credential Lifecycle also
reports their presence, private permissions, consumers, and newest-backup
coverage. See [`credential-lifecycle.md`](credential-lifecycle.md).

The directory is mode `0700`; database and 256-bit HMAC key are mode `0600`.
The key protects four separate contracts:

- the complete executable request body, including secret values;
- immutable request identity, expiry, requester, path, capability, risk,
  summary, and redacted review body;
- every mutable state field, approver, decision time, and consumption record;
- a globally chained append-only transition event ledger.

Review JSON recursively redacts password, secret, token, credential,
authorization, private-key, and large archive payload fields. Other strings and
arrays are bounded for review. HMAC comparison still covers the complete,
unredacted body, so a hidden secret change invalidates execution.

The store rejects self-approval, approval by an identity lacking the target
capability, execution by anyone except the requester, expired/cancelled/rejected
requests, body/path/capability/risk drift, state or immutable-record tampering,
event-chain tampering, and replay.

## Metrics and alerting

`/metrics/change-intelligence` exports label-free series:

```text
dash_change_approval_enabled
dash_change_approval_ledger_valid
dash_change_approval_pending
dash_change_approval_approved
dash_change_approval_consumed_total
dash_change_approval_rejected_total
dash_change_approval_cancelled_total
dash_change_approval_expired_total
dash_change_approval_oldest_pending_age_seconds
```

No operator, path, request ID, capability, HMAC, or request value is used as a
Prometheus label. `DashChangeApprovalLedgerInvalid` becomes critical only when
dual control is enabled and request/state/event verification fails.

## Recovery

Keep the database and key together in normal DASH backup/offsite workflows. A
missing or wrong key makes verification and governed execution fail closed.

If recovery is required:

1. restore both files from the same trusted backup;
2. verify permissions are `0600` and the key is exactly 32 bytes;
3. load the Security page and require `ledger valid` before executing changes;
4. cancel or allow old approvals to expire; do not recreate their plaintext
   requests from memory.

Emergency owner access does not bypass enabled dual control. The explicit
break-glass procedure is to disable `DUNE_ADMIN_DUAL_CONTROL_ENABLED`, recreate
only the Admin Panel, perform the separately gated operation, restore the
setting, recreate the panel, and review the normal admin/change-intelligence
audit. This configuration change is intentionally visible.

## Validation

```bash
make test-change-approvals
python3 scripts/test-admin-panel-safe-surfaces.py
docker compose --env-file .env.example config --quiet
make validate
```

The focused suite covers policy selection, preview exclusion, two-person
separation, capability/path/body/risk binding, secret redaction, one-time
consumption, concurrent-state CAS, expiry, cancel/reject semantics, private
permissions, immutable-record tampering, mutable-state tampering, event-chain
tampering, and label-free metrics.
