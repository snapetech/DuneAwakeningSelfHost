# Anticipatory Just-In-Time Map Warming

DASH can schedule a dynamic map to become routable before a known player or
community-event window without returning to a 24/7 full-warm farm. The
Infrastructure → Capacity Intelligence panel asks for a **ready by** time. It
subtracts a bounded evidence-derived startup lead and creates a one-time,
daily, or weekly event in the existing persistent scheduler.

This is deterministic anticipatory warming, not an unreviewed prediction. The
operator identifies the future demand window; DASH uses measured startup data
to decide when warming must begin.

## Lead-Time Model

For each dynamic map, the Capacity Intelligence recommendation includes:

- `coldStartP95Seconds`: the retained p95 request-to-routable duration;
- `prewarmLeadSeconds`: p95 plus a configurable safety margin, clamped to a
  configured minimum and maximum;
- `prewarmLeadSource`: `measured-p95` when a completed start exists, otherwise
  `policy-fallback`.

The default policy is:

```json
{
  "fallbackColdStartSeconds": 90,
  "prewarmSafetySeconds": 30,
  "minimumPrewarmLeadSeconds": 60,
  "maximumPrewarmLeadSeconds": 600
}
```

For a measured p95 of 88 seconds, the default lead is 118 seconds. A requested
ready time of 20:00 therefore schedules the warm event for 19:58:02. The UI
refuses a ready time that does not leave the complete calculated lead.

## Execution Contract

The scheduler stores this fixed primitive:

```json
{"type":"map-prewarm","service":"arrakeen"}
```

At run time it:

1. requires `DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true`;
2. requires the master mutation and autoscaler mutation gates;
3. requires the persistent autoscaler worker to be enabled;
4. refuses an unknown or `disabled` map;
5. treats an `always-on` map as a successful recorded no-op;
6. gives a `dynamic` map a `scheduled-prewarm` demand lease;
7. invokes normal autoscaler reconciliation and its guarded start path;
8. retains Coriolis validation, post-start health checks, and runtime patches;
9. records failure in the event run ledger if the start reports an error.

The demand source is persisted and included in Capacity Intelligence start
evidence. When a player arrives, the lease clears and normal adaptive retention
takes over. When nobody arrives, the normal demand TTL expires and the map
returns to its configured retention/LRU/memory policy. A scheduled warm cannot
change a map mode, disable memory-pressure protection, or override a disabled
map.

## Dashboard Workflow

Infrastructure → Capacity Intelligence provides:

- map and evidence-derived lead selection;
- a local ready-by field converted to UTC for persistence;
- once, daily, or weekly recurrence;
- a bounded maximum-run count (`0` means unlimited recurrence);
- server-side event dry-run before confirmation;
- scheduled-warm inventory and cancellation;
- the complete calculated schedule and event plan as JSON evidence.

The equivalent API request is:

```http
POST /api/events
Content-Type: application/json

{
  "name": "Just-in-time warm: arrakeen",
  "runAt": "2026-07-18T01:58:02Z",
  "repeatSeconds": 604800,
  "maxRuns": 0,
  "actions": [{"type":"map-prewarm","service":"arrakeen"}]
}
```

Use `POST /api/events/dry-run` with the same body before creation. Cancel with
`{"id":"<event id>"}` at `POST /api/events/cancel`.

## Persistence, Audit, And Recovery

Schedules and their bounded 500-run ledger live in
`backups/admin-panel/events.json`, which the full backup workflow preserves.
Event creation, dry-run, cancellation, and execution emit normal audit events.
Each map start is also retained in the private Capacity Intelligence SQLite
ledger with `source=scheduled-prewarm`.

`/metrics/capacity` exports label-free schedule/run/failure totals and the
latest run timestamp. `DashCapacityPrewarmFailed` alerts on a failed scheduled
warm without retrying or changing map policy automatically.

No game-database write is performed. Creating or cancelling a schedule does
not restart a service. A due event may start only its selected dynamic map; it
never recreates or restarts an already-running game map.

## Fresh-State Adaptive Profile Fix

This tranche also fixes the process-start profile validator. `adaptive` was
accepted by the runtime action and configuration helper but omitted from the
fresh-state environment validator. That made
`DUNE_AUTOSCALER_PROFILE=adaptive` silently fall back to `balanced` when no
persistent state existed. All entry points now use one canonical profile list,
and regression coverage proves `adaptive` survives normalization.

## Validation

```bash
make test-capacity-intelligence
make test-admin-panel-safe-surfaces
make test-configure-autoscaler-profile
make validate
```

Tests cover policy bounds, fallback and measured lead calculation, adaptive
profile normalization, scheduled-event persistence, guarded dynamic demand,
disabled-map refusal, recurrence, run receipts, and dashboard wiring.
