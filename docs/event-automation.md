# Recurring event automation

The admin panel has a persistent event scheduler for one-time and recurring
operator workflows. It runs every five seconds, stores event definitions and a
bounded 500-run execution ledger, emits signed-webhook-compatible audit events,
and resumes from disk after an admin-panel restart.

State lives under ignored local storage:

```text
backups/admin-panel/events.json
```

## Event shape

```json
{
  "name": "Daily player notice",
  "runAt": "2030-01-01T18:00:00Z",
  "repeatSeconds": 86400,
  "maxRuns": 0,
  "actions": [
    {
      "type": "announcement",
      "message": "Daily maintenance is at 06:00 local time."
    }
  ]
}
```

- `runAt` is an ISO-8601 timestamp. A timestamp without an offset is treated as
  UTC; an explicit `Z` is preferred.
- `repeatSeconds=0` creates a one-time event. Recurrence is bounded from 60
  seconds through 365 days.
- `maxRuns=0` means unlimited recurring runs; otherwise the limit is 1..10000.
- An event without `runAt` is stored for explicit `run now` operation only.

The Catalog page can preview JSON, schedule it, run an existing event now,
cancel it, show next-run/run-count fields, and inspect the execution ledger.

## Action types

| Type | Scheduler behavior |
| --- | --- |
| `announcement` | Creates a job through the existing bounded announcement scheduler. |
| `restart` | Creates a restart plan with `execute=false`; recurring events never turn a plan into an automatic restart. |
| `map-prewarm` | Creates a guarded autoscaler demand lease for one known map. It requires the live autoscaler gates, refuses disabled maps, and uses the normal post-start hooks. |
| `typed-knob-plan` | Records a dry-run-only plan. |
| `economy-bundle` | Records a dry-run-only bundle with `dry_run=true`. |
| `spice-cap-proposal` | Records a dry-run-only typed-knob proposal. |

Event execution requires `DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true`. The master
player/world mutation gates are not bypassed. Action types outside the fixed
catalog fail closed.

The Infrastructure → Capacity Intelligence panel builds `map-prewarm` events
from a **ready by** time and the map's measured cold-start p95. This supports
one-time, daily, and weekly just-in-time warming without keeping the map live
all day. See [`anticipatory-map-warming.md`](anticipatory-map-warming.md).

## API

All routes require an owner or named RBAC token:

```text
GET  /api/events
POST /api/events/dry-run
POST /api/events
POST /api/events/run
POST /api/events/cancel
```

Every run receives a random run ID. The ledger records event ID/name, trigger
(`manual` or `schedule`), timestamp, ordinal run number, primitive results,
failures, and next run time. It does not store credentials. The event advances
its recurrence only after all permitted primitives succeed; a failed run is
terminal until the operator reviews and creates a replacement event.

Announcement jobs have their own persisted IDs and delivery state. A restart
action remains a non-executing restart job even when event execution is
enabled. This separates schedule automation from host/game-map restart
authority and preserves the post-start hook requirements in `AGENTS.md`.

## Validation

```bash
python3 scripts/test-admin-panel-safe-surfaces.py
```

The tests cover recurrence bounds, invalid timestamps, due-event selection,
announcement dispatch, forced `execute=false` restart planning, guarded map
prewarming and disabled-map refusal, dry-run action handling, run-ledger
persistence, max-run termination, and the disabled gate.
