# Feature Readiness Control Center

DASH exposes one authoritative, secret-safe answer to a question that feature
flags alone cannot answer: which capabilities are disabled, partially enabled,
configured, running, blocked by an external credential, degraded at runtime, or
still waiting for an explicit canary?

The control center is read-only. It does not enable a gate, create a credential,
start a service, run a canary, execute a game command, or change an incident. It
links each finding to the existing guarded operator surface that owns recovery.

## Outcome

Open **Infrastructure → Feature Readiness Control Center**. The matrix combines:

- every gate used by `scripts/enable-feature-parity.sh`;
- credential **presence** without credential values;
- required repository/configuration artifacts and their bounded minimum size;
- current Compose service state;
- feature dependencies;
- explicit runtime probes for the database, governance chain, operational
  evidence stores, autoscaler, metrics collectors, native command transport,
  moderation/community ledgers, authentication, webhooks, public directory,
  public-IP monitor, and backup encryption; and
- a separate canary classification so configured code is never mislabeled as
  end-to-end runtime proof.

The current catalog groups the complete activation set into trust,
infrastructure, retained evidence, adaptive maps, metrics, player/world/content
administration, creator tooling, moderation, community rewards, Discord,
federated login, webhooks, public discovery, multi-Sietch topology, public-IP
repair, and encrypted backups.

The catalog is [`config/feature-readiness.json`](../config/feature-readiness.json).
Evaluation is implemented by
[`admin/feature_readiness.py`](../admin/feature_readiness.py). Runtime probes and
the authenticated API live in the Admin Panel.

Repository artifacts are checked through the complete read-only
`DUNE_DEPLOYMENT_ASSURANCE_WORKSPACE` mount (normally `/source-workspace` in
the Admin container). Runtime state remains under `/workspace`; this prevents
the deliberately partial runtime mounts from falsely reporting committed
Compose overlays as absent.

Directory verification uses OpenSSL when the executable is available. The
minimal vendor Admin image does not currently ship that executable, so DASH
also includes a strict RFC 8032 Ed25519 verification fallback. It rejects
non-canonical points, non-prime-order points, identity points, out-of-range
scalars, and altered payloads/signatures; signing and key generation remain on
the private host-side renderer.

## States

| State | Exact meaning |
| --- | --- |
| `ready` | Required gates, credentials, artifacts, services, dependencies, and runtime probe pass; any required live canary is proven. |
| `canary-pending` | Implementation is loaded and configured, but the declared operator/provider live canary remains unproven. |
| `disabled` | The optional feature's primary gate is intentionally inactive. This is not an outage. |
| `partial` | At least one gate in the feature group is active, but the required group is incomplete. |
| `blocked` | An active feature is missing a required artifact, local credential, or dependency. |
| `degraded` | Configuration is present, but a required service or explicit runtime probe is unhealthy. |
| `external-blocked` | An active integration still needs an operator-owned external provider credential. |

`overall=attention` means at least one active feature is `partial`, `blocked`,
`degraded`, or `external-blocked`. Disabled optional integrations and explicitly
visible pending canaries do not masquerade as runtime failures.

Readiness is evidence-specific. For example, a `ready` native-command row proves
the gates, private command token, Admin RMQ service, and already promoted
runtime transport. It does not claim that every possible player command was
re-run against a live player during the current request. Where a disposable or
provider-backed live canary is still required, the row remains
`canary-pending` or `external-blocked`.

## API

The authenticated read endpoint is:

```text
GET /api/ops/feature-readiness
GET /api/ops/feature-readiness?refresh=1
```

The normal response is cached for 30 seconds to keep dashboard loads and
Prometheus scrapes cheap. `refresh=1` recomputes service inventory, artifact
metadata, credential presence, and runtime probes immediately. The TTL is
bounded to 5-300 seconds with:

```env
DUNE_FEATURE_READINESS_CACHE_TTL_SECONDS=30
```

Each feature row contains its group, documentation, remediation surface,
individual gate booleans, credential-presence booleans, file sizes, service
states, dependency states, runtime-probe result, and canary contract. It never
contains an environment value, secret-file content, OAuth secret, Discord bot
token, database password, Admin token, or native-command token.

The response explicitly returns `secretValuesReturned=false`.

## Metrics

The existing private `/metrics/change-intelligence` scrape now also exports:

```text
dash_feature_readiness_ok
dash_feature_readiness_total
dash_feature_readiness_active
dash_feature_readiness_active_problems
dash_feature_readiness_ready
dash_feature_readiness_canary_pending
dash_feature_readiness_disabled
dash_feature_readiness_partial
dash_feature_readiness_blocked
dash_feature_readiness_degraded
dash_feature_readiness_external_blocked
```

Metrics are deliberately label-free. Feature IDs, credential names, service
names, operator identities, paths, and failure text remain in the authenticated
API rather than becoming public/high-cardinality labels.

`DashFeatureReadinessCollectorInvalid` alerts when evaluation returns no
catalog, and `DashFeatureReadinessActiveProblems` alerts when an active feature
remains partial, blocked, degraded, or externally blocked for five minutes.

## Catalog Contract

Every feature declares:

- stable `id`, title, group, description, and documentation path;
- one `primaryGate` and the complete required `gates` set;
- credential environment keys whose values are checked only for presence;
- confined relative regular-file requirements and minimum byte counts;
- required Compose service names;
- an allowlisted runtime `probe` identifier;
- other catalog feature IDs that must be `ready` first;
- one canary state; and
- the existing surface and concise recovery instruction.

Catalog loading fails closed on unknown fields, duplicate/invalid IDs, invalid
environment or service names, absolute/traversing paths, invalid byte bounds,
unknown dependencies, self-dependencies, or unsupported canary states.
Dependency cycles are also refused.

The repository test extracts the `keys=(...)` block from
`scripts/enable-feature-parity.sh` and requires every activated gate to appear
in at least one catalog feature. Adding a new parity gate without readiness
coverage therefore breaks validation instead of silently creating another
untracked toggle.

## Recovery Workflow

1. Refresh the matrix once to rule out the bounded cache.
2. Read the exact failing gate, artifact, service, dependency, or probe.
3. Open the row's documented remediation surface.
4. Use that surface's existing capability, feature gate, exact confirmation,
   backup, hostname, post-start hook, and change-contract controls.
5. Recheck the matrix and the subsystem's own detailed status.

Do not turn a disabled optional external integration into a false outage. Do
not treat `canary-pending` as failure or as proof. Do not repair a failed
evidence ledger by generating a new key; follow its backup-specific recovery
contract.

## Validation

Run the focused tests with:

```bash
make test-feature-readiness
make test-admin-panel-safe-surfaces
```

The tests cover every state, dependency failure, secret non-disclosure,
catalog confinement/validation, label-free metrics, documentation links, and
complete parity-activator gate coverage. `make validate` includes both suites.

Production activation requires only an assured Admin/control-plane deployment.
The feature itself has no mutation gate and does not require or perform a game
map lifecycle action.
