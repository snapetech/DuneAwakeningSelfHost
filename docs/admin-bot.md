# Paul Admin Bot

Paul is the in-game/admin-bot identity. `scripts/admin-bot.py` is the umbrella automation runner for approved Paul features.

Enabled in this first pass:

- Spam warn/kick path lives in `scripts/admin-chat-commands.py` and `scripts/spam-kick-player.sh`.
- Map death watchdog integration through `scripts/watch-maps.sh`.
- Stuck-transition reporting.
- Backup freshness reporting, with opt-in stale-backup execution.
- Restart workflow remains in the existing admin panel scheduler and `scripts/restart-target.sh`.
- Admin action audit digest.
- Economy anomaly reporting for large currency balances.
- Base/claim count reporting.
- Config drift detection for `.env`, Compose, `UserGame.ini`, and `director.ini`.
- Admin token/Host/Origin/denied-request audit summary.

Intentionally skipped:

- Toxicity/slur filtering.
- Queue/population announcements.

Run one report:

```bash
./scripts/admin-bot.py --once
```

Run as a loop:

```bash
./scripts/admin-bot.py --loop
```

Defaults are report-first. The map watchdog runs `watch-maps.sh --dry-run` unless `DUNE_ADMIN_BOT_MAP_WATCHDOG_RECOVER=true`. Stale backup execution is also disabled unless `DUNE_ADMIN_BOT_BACKUP_STALE_RUN=true`.

Important knobs:

```env
DUNE_ADMIN_BOT_INTERVAL_SECONDS=300
DUNE_ADMIN_BOT_BACKUP_MAX_AGE_HOURS=24
DUNE_ADMIN_BOT_BACKUP_STALE_RUN=false
DUNE_ADMIN_BOT_MAP_WATCHDOG_ENABLED=true
DUNE_ADMIN_BOT_MAP_WATCHDOG_RECOVER=false
DUNE_ADMIN_BOT_STUCK_TRANSITIONS_ENABLED=true
DUNE_ADMIN_BOT_STUCK_TRANSITION_MINUTES=10
DUNE_ADMIN_BOT_AUDIT_DIGEST_ENABLED=true
DUNE_ADMIN_BOT_ECONOMY_ANOMALIES_ENABLED=true
DUNE_ADMIN_BOT_SOLARI_WARN_THRESHOLD=10000000
DUNE_ADMIN_BOT_BASE_CLAIM_MONITOR_ENABLED=true
DUNE_ADMIN_BOT_MAX_BASES_WARN=6
DUNE_ADMIN_BOT_CONFIG_DRIFT_ENABLED=true
DUNE_ADMIN_BOT_SECURITY_GUARD_ENABLED=true
```

State is stored in `backups/admin-bot/state.json`. The state file tracks audit offsets and config hashes so repeated runs report only new audit activity and drift since the previous run.
