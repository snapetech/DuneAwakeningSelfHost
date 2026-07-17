# Ecosystem Peer Revision Watch

DASH continuously checks whether the exact primary repositories used by the
aggregate feature-parity audit have moved beyond their reviewed commit pins.
The result appears under **Discovery → Ecosystem Peer Watch**, enters the signed
Operator Briefing, and exports label-free Prometheus signals.

This is a review detector, not an automatic parity claim. A new upstream commit
means only that the pinned evidence is stale. DASH never changes an audit pin,
copies code, opens an upstream request, or treats a commit as a feature until an
operator reviews the diff.

## Authority and state model

[`ecosystem-feature-parity-audit.md`](ecosystem-feature-parity-audit.md) is the
only peer catalogue. Machine-readable audit rows supply the display name,
canonical HTTPS repository, and exact 40-character commit pin. The parser
rejects an empty catalogue, duplicates, symlinks, non-HTTPS URLs, credentials,
ports, query strings, fragments, extra path components, and repositories outside
the fixed `github.com` / `git.unityailab.com` allowlist. The latter is queried
through its Forgejo v1 API; it is not treated as GitLab.

Each poll asks the provider's fixed read-only commit endpoint for the current
default-branch head and stores one of three states:

| State | Meaning | Operator response |
| --- | --- | --- |
| `current` | Observed head exactly equals the reviewed audit pin. | None. |
| `drifted` | The primary repository has a different default-branch head. | Inspect commits from the pin through the observed head and update the audit only after reviewing claimed outcomes against source. |
| `error` | This repository could not be observed during the poll. | Repair provider reachability, rate limit, or response validity; other repositories were still checked. |

The SQLite ledger retains `discovered`, `drift-detected`, `collection-error`,
`current`, `pin-updated`, and `catalog-removed` transitions. A complete poll
requires exactly one bounded observation for every current catalogue row. A
catalogue parse failure or mismatched observation set records a collector-level
failure and does not silently accept a partial catalogue.

## Network and credential boundary

Collection is deliberately narrow:

- one HTTPS request per repository to a provider-derived API URL;
- redirects disabled;
- 1 MiB maximum response and a configurable 1–60 second per-source timeout;
- per-repository failure isolation;
- no repository write endpoint and no automatic pin update; and
- no player, game-map, Docker, Steam client, or desktop interaction.

GitHub's unauthenticated quota can be tight for a catalogue-wide poll behind a
shared address. `DUNE_PEER_WATCH_GITHUB_TOKEN_FILE` may point to a private
regular file containing a read-only token. The file must not be a symlink or
group/world accessible. Its value is sent only to `api.github.com`, never to the
Forgejo peer, APIs, metrics, audit detail, or browser.

## Configuration

```env
DUNE_PEER_WATCH_ENABLED=true
DUNE_PEER_WATCH_DATABASE=/workspace/backups/peer-watch/watch.sqlite3
DUNE_PEER_WATCH_HOST_DATABASE=backups/peer-watch/watch.sqlite3
DUNE_PEER_WATCH_CATALOG=/source-workspace/docs/ecosystem-feature-parity-audit.md
DUNE_PEER_WATCH_GITHUB_TOKEN_FILE=
DUNE_PEER_WATCH_POLL_SECONDS=21600
DUNE_PEER_WATCH_TIMEOUT_SECONDS=15
DUNE_PEER_WATCH_HISTORY_LIMIT=5000
```

The poll interval is bounded from one hour through seven days. History retention
is bounded from 100 through 50,000 transitions. The default six-hour cadence
keeps normal operation inexpensive while the authenticated **Poll primary
repositories now** action supports an immediate audit refresh.

## API, readiness, and briefing

Authenticated endpoints:

```text
GET /api/ops/peer-watch
GET /api/ops/peer-watch?refresh=1
```

The response contains aggregate counts, bounded peer rows, recent transitions,
collector age/error state, catalogue hash agreement, and an explicit execution
contract. It contains no token value. `limit` restricts returned detail but not
the global summary.

Feature Readiness proves that the enabled worker is running, the database
schema/integrity is valid, the checked-in catalogue still matches the last
completed observation, and the successful poll is fresh. Individual drift and
source errors remain visible operational findings rather than falsely claiming
the collector implementation is absent. The Operator Briefing independently
reports drift/error totals and refreshes on both regression and recovery.

## Metrics and alerts

`/metrics/change-intelligence` exports only label-free gauges:

```text
dash_peer_watch_enabled
dash_peer_watch_collector_up
dash_peer_watch_worker_running
dash_peer_watch_peers_total
dash_peer_watch_current
dash_peer_watch_drifted
dash_peer_watch_errors
dash_peer_watch_transitions_total
dash_peer_watch_last_success_timestamp_seconds
dash_peer_watch_age_seconds
```

Prometheus rules distinguish an invalid/stale collector, observed revision
drift, and per-source collection errors. Repository names, URLs, commit IDs,
error text, and transition details remain in the authenticated API and private
SQLite state.

## Backup and recovery

When enabled, both host and Admin-created full backups require an online SQLite
snapshot named `peer-watch.sqlite3`. Backup verification checks integrity and
the `peers`, `transitions`, and `metadata` schema. A required missing snapshot
fails closed instead of producing a passing incomplete recovery set.

Restore only during a reviewed Admin control-plane maintenance window so the
running process does not retain an old SQLite connection:

```bash
./scripts/restore-state.sh --dry-run --peer-watch .env backups/<backup-id>
./scripts/restore-state.sh --peer-watch .env backups/<backup-id>
```

The restore preflights the copied database, removes stale WAL/SHM companions,
and installs it with private directory/file modes. Recreate the Admin service
through the normal assured lifecycle after restoration.

## Drift review runbook

1. Open Discovery and record the pin and observed head for every drifted peer.
2. Inspect the primary repository's commit range, release notes, implementation,
   and tests. A README claim alone is not parity evidence.
3. Classify each actual operator-visible outcome as existing DASH coverage,
   feasible implementation work, provider/client blocked, or irrelevant.
4. Implement and validate any real gap; update the peer-specific and aggregate
   audits with exact source evidence.
5. Change the checked-in pin only as part of that reviewed audit commit.
6. Poll again. `pin-updated` followed by `current` is the retained closure
   evidence; never edit the SQLite database to clear drift.

Validation:

```bash
make test-peer-watch
make validate ENV_FILE=.env.example
```
