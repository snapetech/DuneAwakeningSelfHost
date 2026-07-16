# Capacity Intelligence And Adaptive Retention

DASH measures whether dynamic maps are actually saving resources and whether
the saved map-hours are worth the player-facing cold-start delay. The private
capacity ledger turns the minimum-footprint, balanced, adaptive, full-warm, and
custom modes into an evidence-driven continuum instead of a guess.

This subsystem reads map/container state, player counts, Director demand
leases, farm readiness, and the current retention policy. It does not write the
Dune database, change map modes, or start/stop a map. Applying a recommendation
changes only `retentionByService` in the existing autoscaler state.

## What It Measures

Every 30 seconds by default, the collector records one bounded interval per map:

- running, ready, demanded, player-active, or stopped state;
- always-on, dynamic, or disabled mode;
- current per-map/default retention;
- active, idle-running, and avoided map-seconds;
- warm and cold revisits;
- explicit autoscaler request-to-ready latency;
- observed container starts that happened outside the autoscaler.

The Infrastructure → Capacity Intelligence view reports 1-day, 7-day, and
30-day windows. The fleet summary includes:

- map-hours saved versus keeping the observed farm running continuously;
- idle map-hours spent retaining empty maps;
- resource-avoidance ratio (`stopped dynamic seconds / all observed map seconds`);
- productive-running ratio (`player/demand-active seconds / running seconds`);
- observation coverage so a short history is never presented as a full month.

The ledger is time-weighted. Gaps are capped at five minutes by default, so an
offline collector cannot invent hours of savings or waste.

## Cold Starts And Warm Hits

The autoscaler writes a start-request event immediately before invoking its
guarded map start path. The capacity collector completes the event only after
the corresponding partition is alive, ready, active, and unblocked. A failed
start is marked immediately; a start that never becomes ready reaches a bounded
timeout. This measures demand-to-routable readiness rather than container
creation alone.

When a map becomes active after an idle interval, the event is classified:

- `warm`: the map was already running and ready;
- `cold`: the visit required or was waiting on a start.

Per-map summaries include warm hits, cold revisits, revisit-gap p50/p75/p90,
cold-start p50/p95, and the empirical chance of another visit within the next
15 minutes given the current idle age.

## Recommendation Model

For every dynamic map, DASH evaluates retention candidates between the policy
minimum and maximum in fixed steps. For each candidate `r` and observed revisit
gap `g`, the model cost is:

```text
idle cost = min(g, r)
cold cost = median cold-start seconds × wait weight, when g > r
candidate cost = average(idle cost + cold cost)
```

The default wait weight is `4`: one second of player cold-start wait is valued
like four seconds of one idle map. This is an explicit policy preference, not a
claim that CPU, RAM, and human time share a physical unit. Operators can tune
the weight in `config/capacity-intelligence.json`.

A recommendation is eligible only after at least five revisits and two measured
ready starts for that map. It is `high` confidence after 20 revisits and five
starts. Lower-evidence rows remain visible but cannot be applied.

## Profiles

| Profile | Behavior |
| --- | --- |
| `minimum-footprint` | Core maps stay always-on; other maps use the short global retention. |
| `balanced` | Core maps plus static per-map/default warm retention, LRU cap, and memory floor. |
| `adaptive` | Starts from balanced limits, then uses evidence-qualified per-map retention. |
| `full-warm` | Every map stays running; no automatic eviction. |
| `custom` | Operator-selected modes, retention, LRU cap, and memory floor. |

Configure without mutation, then apply:

```bash
./scripts/configure-autoscaler-profile.sh .env adaptive
./scripts/configure-autoscaler-profile.sh .env adaptive --execute
```

The adaptive profile keeps the balanced warm-map cap and memory floor. Capacity
recommendations never override those pressure controls and never convert an
always-on, dynamic, or disabled map.

## Applying Recommendations

Manual application uses:

```text
POST /api/ops/capacity
{"action":"apply-recommendations","confirm":"APPLY CAPACITY RECOMMENDATIONS"}
```

It requires authenticated `infrastructure.write`, the master mutation gate,
and `DUNE_ADMIN_AUTOSCALER_MUTATIONS_ENABLED=true`. Each eligible per-map
retention moves at most 50% from its current value per application. This makes a
large model change converge instead of instantly swinging from full retention
to nearly cold or back.

Set `DUNE_CAPACITY_AUTO_APPLY_ENABLED=true` for the same bounded application at
the configured interval (24 hours by default). Automatic application also
requires the master and autoscaler mutation gates. Empty/low-confidence models
produce no change. Every nonempty application has an append-only SHA-256
receipt containing actor, source, before/recommended/applied values, confidence,
and evidence counts.

## API And Prometheus

Authenticated retained status:

```text
GET /api/ops/capacity
```

Private Compose-network metrics:

```text
GET /metrics/capacity
```

Metrics include collector freshness, map-hours saved, idle map-hours,
resource-avoidance/productive-running/coverage ratios, eligible recommendations,
recommended retention, retention delta, warm/cold revisit counts, and cold-start
p95. Prometheus alerts when collection is stale or a measured cold-start p95
exceeds three minutes.

The metric endpoint contains no player identities, coordinates, tokens, notes,
database rows, or paths.

## Storage, Backup, And Recovery

The private ledger defaults to:

```text
backups/capacity-intelligence/capacity.sqlite3
```

Its directory is mode `0700` and database is mode `0600`. SQLite uses WAL, full
synchronous commits, foreign keys, a busy timeout, and immediate write
transactions. Samples retain 90 days; start/revisit/application evidence keeps
730 days by default. Application rows are protected by update/delete rejection
triggers and their payload hashes are recomputed by the verifier.

Full CLI and browser maintenance backups use SQLite's online backup API and
include `capacity-intelligence.sqlite3`. `verify-backup.sh` checks SQLite
integrity, append-only triggers, JSON payloads, and every application hash.
Restore is explicit and must happen while the admin writer is stopped:

```bash
./scripts/restore-state.sh --capacity-intelligence .env backups/<id>
```

## Configuration

| Variable | Default | Meaning |
| --- | ---: | --- |
| `DUNE_CAPACITY_INTELLIGENCE_ENABLED` | `true` | Run the read-only evidence collector and expose status/metrics. |
| `DUNE_CAPACITY_INTELLIGENCE_POLICY` | `/workspace/config/capacity-intelligence.json` | Versioned model and retention policy. |
| `DUNE_CAPACITY_INTELLIGENCE_DATABASE` | `/workspace/backups/capacity-intelligence/capacity.sqlite3` | Private ledger path. |
| `DUNE_CAPACITY_INTELLIGENCE_POLL_SECONDS` | `30` | Collection cadence, bounded to 10–3600 seconds. |
| `DUNE_CAPACITY_AUTO_APPLY_ENABLED` | `false` | Enable evidence-qualified gradual application. |
| `DUNE_CAPACITY_AUTO_APPLY_INTERVAL_HOURS` | `24` | Minimum automatic-application interval. |

Policy validation bounds sample/event retention, collector gaps, start timeout,
sample thresholds, fallback latency, wait weight, retention range/step, forecast
horizon, and maximum per-application movement.

## CLI And Validation

```bash
make capacity-status
make capacity-verify
make capacity-metrics
make test-capacity-intelligence
make validate
```

`scripts/capacity-intelligence.py observe --maps fixture.json` exists for
controlled fixtures and reviewed external collectors. The admin worker is the
production writer; do not run a second periodic writer.

Tests cover policy rejection, private modes, bounded intervals, start
request/ready/failure/timeout transitions, warm/cold revisits, time-weighted
savings and waste, recommendation eligibility and bounds, empirical forecasts,
append-only receipts, tamper detection, backup integrity, public metric bounds,
authenticated API routing, real autoscaler/DB collection, and exact mutation
confirmation.
