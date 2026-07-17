# Conflict-Aware Operations Calendar

DASH reduces its independent schedulers to one bounded, read-only operational
horizon and uses the same cross-process lock to serialize the operations that
can invalidate each other's recovery assumptions. The calendar does not start,
stop, restart, back up, or reschedule anything by itself.

## Included authorities

The default 14-day view combines:

- automatic full-backup occurrences from `backup-schedule.json`;
- active browser maintenance/restart jobs, including dry-run versus executing
  state, target, update policy, backup intent, and prior lock deferrals;
- recurring Event Automation occurrences, classified as communication,
  planning, or map preparation from their already-validated action plans; and
- active/future Operational SLO maintenance exclusions.

All inputs are normalized to UTC half-open windows (`start <= t < end`), given
stable source-qualified IDs, sorted deterministically, and bounded to a maximum
31-day horizon. Expired rows are omitted. Recurrences are capped per source so
an unlimited event cannot produce unbounded API or browser output.
An overdue queued backup, restart, or event is represented as due at the
calendar generation time instead of disappearing as an expired estimate; its
own worker remains authoritative for actual execution.

Configured reserved durations are estimates for planning, not claims about
actual completion time:

| Window | Default |
| --- | ---: |
| Automatic full backup | 1,800 seconds |
| Executing maintenance/restart | 5,400 seconds |
| Scheduled map prewarm | 1,800 seconds |
| Communication or plan-only event | 300 seconds |

## Deterministic findings

The pure analyzer emits a stable conflict ID, exact overlap, involved window
IDs, UTC start, reason, and severity.

| Overlap | Severity | Behavior |
| --- | --- | --- |
| Disruptive maintenance + recovery work | Critical | Executing maintenance scheduling is refused |
| Two disruptive operations | Critical | Executing maintenance scheduling is refused |
| Two recovery operations | Warning | Operator review; neither schedule is silently changed |
| Preparatory work + disruptive operation | Warning | Operator review |
| SLO exclusion + any operation | None | The exclusion is coverage evidence, not workload |

Every executing disruptive window is also checked for complete containment by
a non-cancelled SLO maintenance exclusion. Partial overlap does not count. An
uncovered change is a warning because the maintenance may still be intentional,
but its reliability accounting has not been explicitly aligned.

The fingerprint covers normalized windows, conflicts, coverage findings, and
source errors.
It excludes response-generation time, so identical authoritative state yields
the same fingerprint.

## Schedule-time guard

`POST /api/ops/restart` analyzes an executing job before persisting it. Existing
restart jobs are excluded because a newly accepted job supersedes them, while
automatic backups, recovery windows, and other authorities remain in scope.
A critical collision is rejected before announcements or job state are written.
If any calendar authority fails, executing maintenance admission also fails
closed; a partial horizon is never treated as proof that the proposed window is
safe.
Queued jobs may be superseded or cancelled. Once a job is `executing` or
`awaiting_reboot`, its state is immutable to new schedule/cancel requests so its
worker can finish recovery and seal the correct outcome.

Warning overlaps and missing SLO coverage do not masquerade as critical
admission failures. They are retained in `calendarConflicts` and
`calendarCoverageFindings` on the accepted job, exported through the calendar,
briefing, metrics, and alerts, and remain available for operator review.

An exceptional API caller may set:

```json
{
  "allowCalendarConflict": true,
  "calendarConflictConfirm": "OVERRIDE SCHEDULE CONFLICT"
}
```

The ordinary browser planner never supplies this override. Accepted overrides
retain the complete conflict list and `calendarConflictOverride=true` in the
job and audit trail. The override changes schedule admission only; it does not
bypass the runtime operation lock or any restart, update-readiness, backup,
player-disconnect, Coriolis, post-start, or recovery gate.

## Runtime serialization and deferral

Executing maintenance owns `backups/admin-panel/operation.lock` from before its
preflight/disconnect through stop, verified backup, optional certified update,
start, recovery, and online proof. The same bind-mounted inode is used by:

- automatic and manual panel full backups;
- standalone `scripts/backup-state.sh`;
- assured control-plane deployments; and
- executing browser maintenance.

If another operation owns the lock when maintenance becomes due, no player is
disconnected and no service command runs. The job returns to `scheduled`, moves
to the bounded retry time (default 300 seconds), increments
`operationDeferrals`, clears the transient error, and emits
`restart-operation-deferred`. A deferral is not recorded as a failed
maintenance outcome or `lastExecution` because disruptive execution never
began; bounded `lastDeferral` detail remains available with the queued job.

This runtime contract remains authoritative when a schedule estimate is wrong
or an unscheduled assured deployment begins after the calendar was viewed.

## Operator surfaces

Authenticated API:

```http
GET /api/ops/calendar?horizonDays=14
```

The Operations page shows current/next windows, local-time rendering, source,
impact, target, recurrence, conflicts, uncovered disruptive changes, the
calendar fingerprint, operation-lock path, and the non-mutation contract. The
signed Operator Briefing treats calendar conflicts and uncovered changes as an
independent critical authority. Schedule, event, SLO-maintenance, deferral, and
execution audit events invalidate the prior briefing.

The Change Intelligence metrics endpoint exports label-free series:

```text
dash_operations_calendar_collector_up
dash_operations_calendar_windows
dash_operations_calendar_current_windows
dash_operations_calendar_critical_conflicts
dash_operations_calendar_warning_conflicts
dash_operations_calendar_uncovered_disruptive_windows
dash_operations_calendar_next_window_timestamp_seconds
dash_operations_calendar_next_window_seconds
```

Prometheus alerts on collector failure, critical conflicts, warning conflicts,
and executing maintenance without a complete SLO exclusion.
An upstream source failure is retained in `errors`, changes the fingerprint,
sets `ok=false`, and exports `dash_operations_calendar_collector_up 0`; it is
never converted into an ordinary planning row. Scheduler JSON is parsed
strictly for this surface, so a corrupt state file is not silently treated as
an empty schedule even where the owning legacy reader has an empty-state
fallback.

## Configuration

```env
DUNE_OPERATIONS_CALENDAR_HORIZON_DAYS=14
DUNE_OPERATIONS_CALENDAR_BACKUP_WINDOW_SECONDS=1800
DUNE_OPERATIONS_CALENDAR_RESTART_WINDOW_SECONDS=5400
DUNE_ADMIN_RESTART_OPERATION_RETRY_SECONDS=300
```

The horizon is constrained to 1–31 days. Backup/restart reservations and retry
delay are bounded in code. These variables require an Admin Panel restart.

## Troubleshooting

1. Open **Operations → Conflict-Aware Operations Calendar** and identify the
   exact source-qualified window IDs.
2. Move the executing maintenance or underlying schedule. Do not delete
   recovery evidence to make a warning disappear.
3. Create an SLO maintenance exclusion that fully contains the estimated
   disruptive window when the change is planned.
4. Treat a runtime deferral as a current lock owner, not a failed restart.
   Inspect assured-deployment and backup state, then allow the bounded retry.
5. Use the exact override only when the overlap is intended and separately
   justified; it cannot bypass serialization.

## Validation

```bash
python3 -W error::ResourceWarning -m unittest scripts/test-operations-calendar.py
python3 scripts/test-admin-panel-safe-surfaces.py
python3 scripts/test-deployment-assurance.py
make validate
```

A production canary verifies the authenticated calendar API, all eight metrics,
loaded inactive alerts, a current 16-source signed briefing, and unchanged game
map container identities/start times across the admin-only deployment. It does
not schedule or execute a live restart.
