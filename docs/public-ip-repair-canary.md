# Public-IP Repair Canary

DASH proves its complete advertised-address recovery path before trusting it
with a real address change. The canary runs the production monitor, certificate
generator, SAN verifier, restart planner, retry path, and timer installer against
a disposable workspace, then stores a signed, input-bound receipt.

The proof is deliberately stronger than a syntax check. It performs a real
environment rewrite and real OpenSSL certificate rotation using the reserved
documentation addresses `198.51.100.10` and `198.51.100.20`. Docker, systemd,
the live workspace, game maps, and the network remain outside the canary.

## What is proven

One run must pass all 12 checks:

| Check | Evidence |
| --- | --- |
| `inputsBound` | Every executable/configuration input is a bounded regular file and contributes to one manifest digest. |
| `dryRunPlan` | Drift is detected, the intended rewrite is reported, state becomes `dry-run`, and the fixture environment remains byte-identical. |
| `hostnameGuard` | A non-matching exact hostname is refused with exit 77 and `refused` state. |
| `currentNoop` | An unchanged address produces the normal no-op and `current` state. |
| `fullAddressRewrite` | `EXTERNAL_ADDRESS` and the following `GAME_RMQ_PUBLIC_HOST` move to the synthetic new address. |
| `environmentBackup` | The prior environment is archived once with private permissions and retains the old address. |
| `tlsRotation` | All three old TLS files are backed up; a real replacement certificate is generated and contains the new IP SAN but not the old IP SAN. |
| `restartHandoff` | The monitor announces the change and hands all expected services to `restart-target.sh`; the helper is forced into its structured dry-run before any Docker action. |
| `restartRetry` | A synthetic interrupted `restarting` state causes the next check to retry and complete the restart handoff. |
| `timerInstall` | The real installer renders the workspace, environment path, service account, seven-minute cadence, daemon reload, and enable command into disposable units/fake systemctl. |
| `sourceInputsUnchanged` | The complete source manifest is identical after execution. |
| `temporaryStateRemoved` | The disposable workspace is gone before the receipt verdict is produced. |

The receipt also requires these isolation assertions:

- temporary state was created and removed;
- no live environment, TLS, systemd, or monitor-state path was written/opened;
- no game-map lifecycle was invoked; and
- no external network call was made.

Any failed check or isolation assertion makes `ready=false`. Exceptions are not
discarded: a signed failure receipt is retained after temporary cleanup so a
broken proof cannot disappear as if it never ran.

## Bound implementation

Readiness is tied to the SHA-256 manifest of:

```text
admin/public_ip_canary.py
scripts/public-ip-monitor.sh
scripts/generate-rabbitmq-cert.sh
scripts/check-rabbitmq-cert-sans.sh
scripts/restart-target.sh
scripts/install-public-ip-monitor.sh
config/systemd/dune-public-ip-monitor.service
config/systemd/dune-public-ip-monitor.timer
```

Symlinks, paths escaping the workspace, non-regular files, empty files, and
files larger than 50 MiB fail closed. Changing any bound byte immediately makes
an older receipt non-current without invalidating its historical signature.

## Dashboard and API

Open **Infrastructure → Public-IP Repair Proof**. The card reports whether the
monitor is enabled, whether it is armed or dry-run, current proof state, passed
checks, receipt age, execution time, bounded evidence, and exact isolation
claims. **Run isolated repair canary** requires `infrastructure.write`, the
global mutation gate, and exact confirmation:

```text
RUN PUBLIC IP REPAIR CANARY
```

The mutation gate covers writing the private evidence receipt. It does not
authorize or cause a live address, certificate, systemd, Docker, or map change.

Authenticated endpoints:

```text
GET  /api/ops/public-ip-canary?limit=20
POST /api/ops/public-ip-canary
```

POST body:

```json
{"confirm":"RUN PUBLIC IP REPAIR CANARY"}
```

The public response returns input digests and receipt evidence, never the live
public address, environment contents, certificate/private-key material, command
output, or signing secret.

## Signed receipt and readiness

Receipts use schema `dune-public-ip-repair-canary/v1` and the existing Change
Intelligence HMAC key. The verifier checks the outer signature, key fingerprint,
exact schemas, timestamps/duration, receipt digest, every boolean check,
synthetic addresses, evidence bounds, isolation semantics, and final verdict.

The `public-ip-repair` feature becomes `ready` only when all three conditions
are true:

1. the monitor is enabled with a non-empty exact allowed hostname;
2. the newest signed receipt passes, matches the current input manifest, and is
   within its configured lifetime; and
3. the live monitor is armed (`DUNE_PUBLIC_IP_MONITOR_DRY_RUN=false`).

A valid proof with a dry-run live monitor remains `canary-pending`. Invalid or
tampered evidence degrades the feature instead of being treated as merely
pending.

Configuration defaults:

```env
DUNE_PUBLIC_IP_CANARY_MAX_AGE_HOURS=168
DUNE_PUBLIC_IP_CANARY_RETENTION=200
```

Age is bounded to 1-2160 hours. Retention is bounded to 10-2000 receipts.
Receipt files are mode `0600`; their directory is mode `0700`.

## Arming the live monitor

The canary itself never arms the monitor. On the intended production host:

```bash
hostname -s
./scripts/validate-landsraad-coriolis-cycle.sh .env
./scripts/public-ip-monitor.sh .env check
systemctl is-enabled dune-public-ip-monitor.timer
systemctl is-active dune-public-ip-monitor.timer
```

Proceed only when the short hostname is the configured
`DUNE_PUBLIC_IP_MONITOR_ALLOWED_HOST` and the check reports the current-address
no-op. Set `DUNE_PUBLIC_IP_MONITOR_DRY_RUN=false` through the repository's
inode-preserving environment updater, reinstall/enable the timer if necessary,
and immediately run the check again. A current address remains a no-op: arming
does not itself rotate certificates or restart the farm.

When real drift is later detected, `public-ip-monitor.sh` retains its existing
guarded contract: archive environment/TLS state, stage and verify the new
certificate, rewrite only the reviewed address fields, announce, and invoke
`restart-target.sh all` so post-start health and runtime hooks are preserved.

## Metrics and alerts

The authenticated `/metrics/change-intelligence` endpoint exports only
label-free values:

```text
dash_public_ip_canary_enabled
dash_public_ip_monitor_armed
dash_public_ip_canary_collector_up
dash_public_ip_canary_current_ready
dash_public_ip_canary_last_completion_timestamp_seconds
dash_public_ip_canary_age_seconds
dash_public_ip_canary_retained_receipts
```

Alerts:

- `DashPublicIpCanaryCollectorInvalid`: a receipt cannot pass cryptographic or
  semantic verification;
- `DashPublicIpCanaryNotCurrent`: an enabled monitor lacks a current passing
  proof; and
- `DashPublicIpMonitorNotArmed`: an enabled monitor remains dry-run.

No metric labels an address, hostname, receipt, path, certificate, service,
operator, or digest.

## Backup and recovery

Full backups include the receipts in `operator-evidence.tgz` and the matching
Change Intelligence HMAC key in the private config archive. Both the shell and
Admin backup verifiers dispatch the public-IP schema and require the signed
semantic/isolation verdict. A syntactically valid JSON file or valid HMAC over
an inconsistent verdict is rejected.

Restore the evidence archive and matching key together. Replacing the key does
not re-authorize old evidence. After restoring or changing any bound input, run
a new isolated canary before treating the repair path as current.

## Validation

```bash
make test-public-ip-monitor
make test-public-ip-canary
python3 -m py_compile admin/admin_panel.py admin/public_ip_canary.py
promtool check rules config/metrics/rules/dash.yml
docker compose --env-file .env.example config --quiet
```

The focused suite covers the complete disposable lifecycle, signature and
semantic tampering, future timestamps, input drift, expiry, forced failure
cleanup, manifest symlink rejection, capability classification, metrics/alert
binding, deployment support, and real backup-verifier dispatch.
