# Blast-Radius Change Contracts

## Outcome

DASH compiles a machine-readable impact contract before every governed admin
mutation. The contract tells the operator what the exact request can touch,
which backup and rollback model applies, whether players or map lifecycle can
be disrupted, and which route safeguards remain in force. Production defaults
require the signed contract at admission; this is not a dashboard-only preview.

The control closes a common gap between a confirmation phrase and an informed
decision. A phrase proves intent to press a button. A change contract proves
that the current Admin Panel process evaluated the exact operator, route,
capability, body digest, and current impact policy immediately before dispatch.

Confidence: **high** for contract binding, expiry, policy invalidation, browser
review, API enforcement, and audit correlation. Route-specific runtime effects
retain the confidence documented for their underlying feature.

## Contract contents

A governed contract contains no plaintext request body or credential. It
contains:

- a random contract ID and schema version;
- issue and expiry timestamps;
- the authenticated operator ID;
- target route and required RBAC capability;
- SHA-256 of the canonical exact JSON body;
- policy-revision SHA-256;
- route label and `standard`, `high`, or `critical` risk;
- blast-radius scopes;
- backup expectation and reversibility model;
- restart impact;
- player-disruption and map-lifecycle flags;
- route safeguards and concise warnings.

The token is a URL-safe payload plus HMAC-SHA-256 signature. Its 32-byte key is
generated in memory for each Admin Panel process. It is deliberately not
written to disk or copied into backups. A process restart therefore invalidates
every outstanding contract and forces the operator to review the new process's
policy. Contracts expire after 120 seconds by default and cannot exceed 300
seconds. Each contract is atomically consumed before dispatch and authorizes
one attempt only; concurrent or sequential replay is refused.

## Admission sequence

For a governed request, the enforced sequence is:

1. Authenticate the operator and authorize the target route capability.
2. Parse the exact target JSON body under the normal request-size bound.
3. Evaluate the body-aware governed policy. Dry runs and non-mutating actions
   remain previews and do not receive a mutation contract.
4. Compile and HMAC-sign the impact contract.
5. Present the contract in the browser, or return it to the API caller.
6. Submit the unchanged body with `X-DASH-Change-Contract`.
7. Verify signature, process generation, expiry, operator, route, capability,
   exact body SHA-256, risk policy, policy revision, and impact metadata.
8. Atomically consume the contract so the reviewed request cannot be replayed.
9. Seal the correlated `privileged-request-admitted` flight-recorder event.
10. Apply four-eyes approval when enabled, then dispatch the existing guarded
   route.
11. Seal the correlated completion outcome.

The controls are cumulative. A signed contract does not replace the master
mutation gate, route feature gate, confirmation phrase, dry run, online/offline
check, backup, transaction, compare-and-swap guard, dual control, or post-write
verification.

## Browser workflow

The shared browser API client recognizes every governed route. Before it sends
a body that the server classifies as mutating, it requests a contract and opens
the **Review Change Contract** dialog. The dialog shows risk, backup,
reversibility, restart impact, blast-radius scopes, warnings, safeguards, body
digest, operator, capability, and expiry. The request is not dispatched until
the operator selects **Execute reviewed change**.

Cancel closes the dialog and sends no target mutation. Taking time to review
does not consume the target request timeout; the normal bounded timeout starts
again only after acceptance. The Security page exposes the policy revision,
governed-route count, TTL, and process-local issued/admitted/refused counters.

## API workflow

First authenticate to the preflight endpoint with the same credential that
will execute the target:

```bash
body='{"action":"game-apply","confirm":"APPLY GAME UPDATE"}'
contract_response="$({
  jq -n --argjson body "$body" \
    '{targetPath:"/api/ops/updates",requestBody:$body}'
} | curl --fail-with-body --silent --show-error \
  -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  https://admin.example.test/api/security/change-contract)"
```

Review `.contract`, then send the token with the semantically exact JSON
object:

```bash
token="$(jq -r .token <<<"$contract_response")"
curl --fail-with-body --silent --show-error \
  -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  -H "X-DASH-Change-Contract: $token" \
  -H 'Content-Type: application/json' \
  --data-binary "$body" \
  https://admin.example.test/api/ops/updates
```

JSON whitespace and object-key order do not matter because the server hashes a
canonical object. Values, array order, added fields, operator identity, route,
or capability do matter. Request a new contract after any change.

Read the active policy without issuing a contract:

```bash
curl --fail-with-body --silent --show-error \
  -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  https://admin.example.test/api/security/change-contract | jq
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DUNE_ADMIN_CHANGE_CONTRACTS_ENABLED` | `true` | Compile and sign governed mutation impact contracts. |
| `DUNE_ADMIN_CHANGE_CONTRACTS_REQUIRED` | `true` | Fail closed when a governed mutation lacks a matching current contract. |
| `DUNE_ADMIN_CHANGE_CONTRACT_TTL_SECONDS` | `120` | Contract lifetime, bounded to 30-300 seconds. |

`required=true` with `enabled=false` is invalid and prevents Admin Panel
startup. The Settings writer rejects that pair, out-of-range/non-numeric TTLs,
and CR/LF/NUL env-value injection before it creates a backup or changes
`.env`. `scripts/enable-feature-parity.sh` enables both and sets the TTL to 120
seconds. Keep both true in production.

## Governed policy and maintenance

`admin/change_approvals.py` remains the authoritative body-aware route/risk
registry. `admin/change_contracts.py` supplies the impact record for every one
of those policies. Tests require exact key-set equality; adding or removing a
governed policy without its blast-radius metadata fails validation.

The current policy covers 39 high-impact route families across backup restore,
database administration, updates, environment configuration, player/world/
economy state, moderation, service lifecycle, autoscaling, memory, restarts,
and generic GM execution. Predicates distinguish live execution from preview,
dry-run, status, or scheduling-only bodies.

When impact semantics change, update the metadata and documentation together.
The policy revision changes automatically and invalidates already issued
contracts.

## Audit and metrics

Contract issuance writes a sanitized `change-contract-issued` event containing
only contract ID, principal, target, capability, risk, body digest, expiry, and
policy revision. Refusal writes `change-contract-refused`. The mutation flight
recorder admission and completion events carry the contract ID and risk, so an
operator can trace preview, admission, dispatch outcome, and any interruption.

The private metrics endpoint exports label-free counters:

- `dash_change_contract_enabled`
- `dash_change_contract_required`
- `dash_change_contract_issued_total`
- `dash_change_contract_admitted_total`
- `dash_change_contract_refused_total`

Counters are intentionally process-local. The tamper-evident audit ledger is
the durable record.

## Failure and recovery

- **Missing token:** request a contract from the preflight endpoint and resend
  the unchanged body.
- **Expired contract:** review a fresh contract; do not extend the old token.
- **Body/route/operator/capability mismatch:** correct the target request and
  request a new contract.
- **Policy revision mismatch:** reload the current policy and review again.
- **Admin Panel restarted:** all prior contracts are invalid by design.
- **Already consumed:** the reviewed attempt was already admitted; investigate
  its flight-recorder outcome and request a new contract only if another
  execution is intended.
- **Repeated refusals:** inspect Security, the sealed audit ledger, and
  `dash_change_contract_refused_total`. Do not disable enforcement to bypass a
  malformed client.
- **Emergency owner recovery:** the owner-recovery identity can issue its own
  contract, but the same route gates, confirmations, backups, and audit
  admission still apply.

No game-map restart is needed to activate this control. Deploying the Admin
Panel recreates only the control-plane service through the guarded deployment
path. Map lifecycle remains untouched.

## Validation

Run the focused suites:

```bash
make test-change-contracts
python3 scripts/test-admin-panel-safe-surfaces.py
python3 -m py_compile admin/*.py
docker compose --env-file .env.example config --quiet
```

The focused tests cover registry completeness, non-mutating predicates,
secret-free blast-radius output, exact verification, signature/payload
tampering, body/route/principal/capability binding, expiry/future time,
policy-revision invalidation, size and key bounds, TTL bounds, missing identity,
atomic replay refusal/pruning, HTTP admission/refusal, browser surface,
metrics, and RBAC routing.
