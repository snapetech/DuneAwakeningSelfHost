# Retained Metrics

The optional metrics overlay provides the same retained Prometheus outcome as
the audited Red-Blink stack: Prometheus, node-exporter, cAdvisor, a Postgres
exporter, and the RabbitMQ Prometheus endpoints already enabled by DASH.
The private admin service also exposes label-safe `/metrics/slo`,
`/metrics/capacity`, `/metrics/desired-state`, and
`/metrics/change-intelligence` endpoints. They add retained
reliability/error-budget, autoscaler-efficiency, configuration-attestation, and
incident/change-correlation evidence without exporting player identities,
notes, coordinates, paths, candidates, digests, or credentials.
The capacity endpoint also exposes label-free autoscaler enablement, configured
demand/reconcile cadences, process-lifetime scan/reconcile totals, latest scan
times, and separate demand/reconcile error gauges. Alerts distinguish failed or
stale three-second demand detection from the lower-priority full lifecycle
reconcile path, suppress intentional maintenance pauses, and ensure a
resource-saving cadence change cannot silently lengthen a cold-map request.
The SLO, capacity-history, Desired State, and combined Change Intelligence
documents reuse an authenticated result for 30 seconds by default. Their
SQLite/HMAC source refreshes are substantially more expensive than serving the
text exposition, while their underlying collectors run on 30–60 second
cadences. Live autoscaler enablement, timestamps, counters, and error gauges are
appended after the cache and therefore remain current on every capacity scrape.
Set `DUNE_ADMIN_METRICS_CACHE_SECONDS=0` to disable reuse or a value through
`300` to tune it. Label-free cache entry/hit/miss counters make the behavior
observable.
The audit-ledger and Change Intelligence verification caches bind to their own
database, WAL, anchor, policy, and key metadata. The shared parent directory's
ownership and mode remain part of the security check, but unrelated Admin state
renames do not invalidate an 80,000+ event verification. A ledger artifact,
permission, owner, size, or timestamp change still forces full verification;
governed backups and signed exports always force it independently.
The SLO public view also uses a single-flight cache because its five rolling
windows aggregate the retained sample history and pair it with an integrity
scan. A new collector sample, incident note/acknowledgement, or maintenance
mutation invalidates the view immediately; concurrent dashboards, assurance
checks, readiness probes, and Prometheus scrapes reuse one calculation.
Change Intelligence emits the latest response-readiness drill result/time and
the latest fleet-wide readiness certification result/time, runbook coverage,
shared-diagnostic totals, and recovery-contract totals. Those series have no
incident, operator, command, runbook, gate, or digest labels.
The same endpoint emits deployment-assurance verification, latest outcome/time,
open windows, and overdue windows. It does not label commits, paths, services,
operators, backups, or receipt digests.
It also emits game-update readiness, exact-candidate receipt currency,
candidate-update-required state, online-player count, last-certification time,
complete evidence-collection latency, and package-inspection latency. It does
not label image tags, Steam build IDs, candidate fingerprints, operators,
backup paths, or receipt identities.
Steam/archive/full-backup collection runs as a single cached background refresh;
the Prometheus request path never performs those expensive checks inline.
The same endpoint exports label-free four-eyes approval enablement, ledger
validity, state totals, and oldest-pending age. It never labels an operator,
route, capability, request ID, body HMAC, summary, or request value.
It also exports the player-impact maintenance collector state, learning versus
measured mode, aggregate evidence-bucket count, recommended and baseline
expected population, and expected player-minutes saved. These series never
contain player identities, local timestamps, candidate labels, or coordinates.
It also exports mutation flight-recorder enablement, full-chain/head validity,
event/head counts, append failures, privileged admissions/completions, open
requests, and oldest-open age. It never labels a principal, path, capability,
request/approval ID, request-body digest, event HMAC, or event value.
Blast-radius change contracts add label-free enabled/required state and
process-local issued/admitted/refused counters. They never label an operator,
route, capability, body digest, contract ID, policy revision, or impact value;
the sealed audit ledger retains those correlations privately.
Opt-in public-directory publication adds label-free enabled/configured,
entry-valid/current, and seconds-to-expiry series. It never labels a public
URL, region, server identity, build, player count, signing key, or signature;
the signed descriptor remains the authoritative public detail surface.
Credential Lifecycle adds label-free enabled/overall state, totals for required,
missing, unsafe-permission, backup-uncovered, due-soon, and overdue credentials,
plus observation-chain validity and observed rotation count. It never labels a
credential ID, environment key, path, consumer, value, fingerprint, or backup
name. Alert rules fail on an invalid HMAC history, missing active material,
unsafe source permissions, newest-backup gaps, and overdue rotation.
RabbitMQ Recovery Proof adds label-free enabled/configured/running state,
receipt presence, recovery/integrity outcome, source-backup age, and latest
completion time. It never labels a broker, vhost, user, queue, exchange,
binding, container, image, backup path, or receipt ID. Alert rules fail on
invalid configuration, the latest failed or tampered proof, and eight-day
staleness.
Public-IP Repair Proof adds label-free monitor enablement/arming, receipt
verification/current state, completion time, age, and retained count. It never
labels the public address, hostname, certificate, service, operator, path, or
receipt. Alerts distinguish invalid evidence, missing/stale/input-drifted proof,
and an enabled monitor left in dry-run mode; see
[`public-ip-repair-canary.md`](public-ip-repair-canary.md).

Isolated Proof Autopilot adds label-free enablement, collector/worker health,
active/current/due/backoff target counts, cumulative attempts/failures, and
last-attempt/last-success timestamps. Alerts cover invalid scheduler or target
evidence, a worker that did not start, and proof refresh that remains overdue.
Target IDs and failure text stay in the authenticated API; see
[`canary-autopilot.md`](canary-autopilot.md).

Operator Briefing adds label-free enablement, collector/worker health,
current-input/age verdict, score, critical/warning/action counts, generation
time, age, retained receipt count, event invalidation/wakeup/generation totals,
and pending-refresh state. Alerts cover invalid evidence, a stopped worker, a
briefing that remains non-current, a stuck event-driven refresh, and critical
queued actions. Source IDs and action detail stay in the authenticated API; see
[`operations-briefing.md`](operations-briefing.md).

Start it with the normal world Compose files plus the overlay:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.allmaps.yaml -f compose.metrics.yaml \
  up -d prometheus node-exporter cadvisor postgres-exporter
```

For persistent lifecycle integration, set `DUNE_METRICS_ENABLED=true`.
`scripts/compose-files.sh` then includes `compose.metrics.yaml`, and the normal
full-farm startup launches the four metrics services.

Prometheus binds only to localhost by default:

```text
http://127.0.0.1:19090
```

Configuration:

```env
DUNE_METRICS_BIND_ADDRESS=127.0.0.1
DUNE_METRICS_PROMETHEUS_PORT=19090
DUNE_METRICS_RETENTION_TIME=7d
DUNE_METRICS_RETENTION_SIZE=2GB
DUNE_ADMIN_METRICS_CACHE_SECONDS=30
DUNE_METRICS_ENABLED=true
```

Image variables allow reviewed digest pins without editing Compose. The
Postgres password is supplied directly from `.env`; it is not written into the
Prometheus configuration. The Prometheus data volume is bounded by both time
and size retention.

`node-exporter` requires host PID visibility and a read-only root mount.
`cAdvisor` requires privileged host/container telemetry and read-only host
mounts. Neither exporter publishes a host port. Do not include this overlay on
a host where those observation privileges are outside the operator's trust
boundary.

Validate before deployment:

```bash
docker compose --env-file .env.example \
  -f compose.yaml -f compose.metrics.yaml config --quiet
```

`config/metrics/rules/dash.yml` includes collector-freshness, critical SLO,
fast-burn, exhausted-budget, slow cold-start, desired-state target/unsealed/
stale/critical-drift, change-ledger target/integrity/candidate-review,
container-health, memory, disk, Postgres, failed/stale incident drills, and
missing/failed/stale fleet-wide response certification alerts.
It also alerts independently when autoscaler demand scans or full lifecycle
reconciliations fail or become stale.
They also cover invalid, failed, and stale networkless RabbitMQ recovery proof.
It also alerts on invalid deployment evidence, a missing/failed latest assured
deployment, seven-day staleness, and an expired open change window.
Community Rewards exports label-free synthetic-canary collector, current-proof,
age, completion-time, and retention gauges. The proof is policy-bound, so the
readiness matrix returns to canary-pending immediately after catalog changes or
when the configured evidence lifetime expires. Rules alert on invalid canary
evidence after two minutes and missing/stale/policy-mismatched proof after
fifteen minutes.
Creator/Modding exports the equivalent label-free collector, current-proof,
age, completion-time, and retention gauges. Its proof binds exact module,
catalog, and active `UserGame` hashes, so code/config drift or expiry returns readiness to
canary-pending. Rules alert after two minutes on invalid evidence and after
fifteen minutes on missing, stale, failed, or input-mismatched proof. See
[`creator-modding-canary.md`](creator-modding-canary.md).
Game-update alerts cover invalid readiness evidence, an available candidate
blocked by safety checks, and an available candidate without a current signed
receipt. They also enforce 15-second full-collection and five-second
package-inspection performance budgets, both with five-minute debounce, so a
regression toward maintenance-window-scale control-plane latency is visible.
Four-eyes approval alerts fail only when the feature is enabled and the
immutable request, mutable state, or transition-event HMAC verification fails.
Audit-ledger rules alert when its event chain/authenticated head is invalid and
when a privileged admission remains without a completion receipt for more than
five minutes.
The change-contract rule warns when more than five governed requests are
refused inside ten minutes, which surfaces stale/malformed API automation or a
repeated bypass attempt without exposing its target.
Public-directory alerts remain inactive while publication is disabled. Once
enabled, they warn if the signed descriptor is invalid or remains non-current
for five minutes, covering renderer/config/key failures without exporting its
identity or URL as a metric label.
Prometheus On-Call Alert Inbox adds label-free collector/worker state, active
firing/pending/unacknowledged/critical/warning totals, consecutive failures,
transition count, and last-success age. Source labels, annotations,
fingerprints, operators, and notes remain in the authenticated API. Meta-alerts
cover an invalid collector and stopped worker; DASH does not alert on its own
unacknowledged metric because that could create a self-latching alert. See
[`alert-inbox.md`](alert-inbox.md).
Ecosystem Peer Watch adds label-free enablement, collector/worker health,
current/drifted/error peer totals, transition count, last-success time, and
collector age. Repository identity, URL, commit pins/heads, and error detail
remain in the authenticated Discovery API. Rules distinguish collector failure,
revision drift, and isolated source errors; see [`peer-watch.md`](peer-watch.md).
Validate the exact Prometheus version and rules with:

```bash
docker run --rm --entrypoint /bin/promtool \
  -v "$PWD/config/metrics/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$PWD/config/metrics/rules:/etc/prometheus/rules:ro" \
  quay.io/prometheus/prometheus:v3.5.0 \
  check config /etc/prometheus/prometheus.yml
```
