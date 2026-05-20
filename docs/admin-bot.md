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
- Optional join/leave announcements through the same Paul/DASH Admin in-game announcement path.

Intentionally skipped:

- Toxicity/slur filtering.
- Queue/population forecasts.

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

## Player Presence Announcements

`scripts/player-presence-announcer.py` is a lightweight companion loop for chatty player-presence events. It polls `dune.player_state`, stores the previous online set in `backups/admin-bot/player-presence.json`, and announces only transitions after the first baseline poll.

```env
DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED=true
DUNE_PLAYER_PRESENCE_POLL_SECONDS=15
DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE=Welcome {playername}! Current player count is now {count}.
DUNE_PLAYER_PRESENCE_LEAVE_TEMPLATE={playername} has left, current count is {count}.
DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND=/workspace/scripts/announce.sh
DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_ENABLED=true
DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_TEMPLATE=Welcome! Please Check https://snape.tech for Server Rules.
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL=Private
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_COMMAND=/workspace/scripts/announce.sh
DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED=true
DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_MESSAGE_ENABLED=true
DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_MESSAGE_TEMPLATE=A Base Reconstruction Tool has been added to your inventory. You may need to log out and back in before it appears.
DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_ENABLED=true
DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_NODE=DA_SQ_VermiliusGap.Relocate.RelocateOutsideHBS.Drive north to the Vermilius Gap
DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_TEMPLATE=Congrats! {playername} has outrun Shai-Hulud!
```

Join/leave, private-welcome, and starter Base Reconstruction Tool templates support `{playername}`, `{player_name}`, `{count}`, and `{player_count}`. Vermilius Gap templates support `{playername}`, `{player_name}`, and `{story_node_id}`.

The private welcome path runs on every detected join for existing and new players after the first baseline poll. It uses the same Paul chat sender, disables dashboard `!!!` wrapping, targets the joined player's live game RabbitMQ queue, and sets `m_ChannelType` to `DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL`. The default message is:

```text
Welcome! Please Check https://snape.tech for Server Rules.
```

The starter Base Reconstruction Tool path grants one `BaseBackupTool` to each newly observed joining account that has not already been recorded in `backups/admin-bot/player-presence.json`. When the grant succeeds, it sends a private message telling the player they may need to log out and back in before the item appears.

The Vermilius Gap announcement watches `dune.journey_story_node` for the configured node's `complete_condition_state = true`. It records completed account ids under `backups/admin-bot/player-presence.json`, so each player is congratulated once. The first poll after enabling the feature baselines already-completed players and does not announce them retroactively.

Run one baseline/check without installing the service:

```bash
./scripts/player-presence-announcer.py --once
```

Install the host service with:

```bash
./scripts/install-player-presence-announcer-service.sh .env
```

or:

```bash
make install-player-presence-announcer-service ENV_FILE=.env
```

The installer writes `/etc/systemd/system/dune-player-presence-announcer.service`, enables it, and starts it. Because it is enabled with `WantedBy=multi-user.target` and `Restart=always`, it starts after host reboots and restarts itself after script failures. The generated unit uses the current checkout path and current user by default; set `DUNE_PLAYER_PRESENCE_SERVICE_USER=<user>` when running the installer to choose another system user.

Operational checks:

```bash
systemctl is-enabled dune-player-presence-announcer.service
systemctl status dune-player-presence-announcer.service
journalctl -u dune-player-presence-announcer.service -f
```

The first service poll records the current online set and does not announce those already online. Announcements start on later observed joins/leaves.
