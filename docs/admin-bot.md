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
DUNE_ADMIN_BOT_BASE_CAP_CONFIG=config/UserGame.ini
DUNE_ADMIN_BOT_BASE_CAP_MAP=HaggaBasin
DUNE_ADMIN_BOT_CONFIG_DRIFT_ENABLED=true
DUNE_ADMIN_BOT_SECURITY_GUARD_ENABLED=true
```

State is stored in `backups/admin-bot/state.json`. The state file tracks audit offsets and config hashes so repeated runs report only new audit activity and drift since the previous run.

## Player Presence Announcements

`scripts/player-presence-announcer.py` is a lightweight companion loop for chatty player-presence events. It polls `dune.player_state`, stores the previous online set in `backups/admin-bot/player-presence.json`, and announces only transitions after the first baseline poll.

```env
DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED=true
DUNE_PLAYER_PRESENCE_POLL_SECONDS=15
DUNE_PLAYER_PRESENCE_SERVER_NAME=My Dune Server
DUNE_PLAYER_PRESENCE_SERVER_URL=https://example.test
DUNE_PLAYER_PRESENCE_RULES_URL=https://example.test
DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE=Welcome {playername}! Current player count is now {count}.
DUNE_PLAYER_PRESENCE_RETURN_JOIN_TEMPLATE=Welcome back {playername}! Current player count is now {count}.
DUNE_PLAYER_PRESENCE_LEAVE_TEMPLATE={playername} has left, current count is {count}.
DUNE_PLAYER_PRESENCE_JOIN_MESSAGE_DELAY_SECONDS=30
DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND=/workspace/scripts/announce.sh
DUNE_PLAYER_PRESENCE_ANNOUNCE_ROUTING_KEYS=<empty>
DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_ENABLED=true
DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_TEMPLATE=Welcome! Please check {rules_url} for server rules.
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_EXCHANGE=chat.whispers
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL=Whispers
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_ROUTING_KEY=
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_COMMAND=/workspace/scripts/announce.sh
DUNE_PLAYER_PRESENCE_FIRST_SEEN_ENABLED=true
DUNE_PLAYER_PRESENCE_FIRST_SEEN_TEMPLATE=Welcome to {server_name}. This is a friendly PvE server. Please keep shared paths, spawns, and resources clear. Rules: {rules_url}
DUNE_PLAYER_PRESENCE_HAGGA_ARRIVAL_ENABLED=true
DUNE_PLAYER_PRESENCE_HAGGA_ARRIVAL_TEMPLATE=You made it to Hagga Basin. Build with room around roads, spawns, resource areas, and points of interest. Rules: {rules_url}
DUNE_PLAYER_PRESENCE_DEEP_DESERT_FIRST_ENABLED=true
DUNE_PLAYER_PRESENCE_DEEP_DESERT_FIRST_TEMPLATE=Deep Desert is high risk. Expect sandstorms, sandworms, and harsher recovery. Support: {server_url}
DUNE_PLAYER_PRESENCE_DEEP_DESERT_JOIN_MESSAGES_ENABLED=true
DUNE_PLAYER_PRESENCE_DEEP_DESERT_CASUAL_PARTITIONS=8
DUNE_PLAYER_PRESENCE_DEEP_DESERT_HARDCORE_PARTITIONS=31
DUNE_PLAYER_PRESENCE_DEEP_DESERT_CASUAL_JOIN_TEMPLATE=PVE Casual ({partition_label}): persistent PvE Deep Desert, standard harvest, no weekly cleanup, no Shifting Sands reset.
DUNE_PLAYER_PRESENCE_DEEP_DESERT_HARDCORE_JOIN_TEMPLATE=PVE Hardcore ({partition_label}): PvE combat, 3x harvest, high sandstorm/Coriolis damage, Shifting Sands, 15% higher vehicle wear, and weekly Hardcore DD cleanup during maintenance.
DUNE_PLAYER_PRESENCE_BASE_REMINDERS_ENABLED=true
DUNE_PLAYER_PRESENCE_BASE_CAP_CONFIG=config/UserGame.ini
DUNE_PLAYER_PRESENCE_BASE_CAP_MAP=HaggaBasin
DUNE_PLAYER_PRESENCE_BASE_NEAR_CAP=5
DUNE_PLAYER_PRESENCE_FIRST_BASE_TEMPLATE=Base reminder: please avoid blocking shared paths, NPCs, resources, caves, wrecks, and POIs. Rules: {rules_url}
DUNE_PLAYER_PRESENCE_BASE_NEAR_CAP_TEMPLATE=Base reminder: this server has a {base_cap} landclaim cap per Hagga Basin map. Please clean up unused claims. Rules: {rules_url}
DUNE_PLAYER_PRESENCE_BASE_OVER_CAP_TEMPLATE=Heads up: you appear to be over the {base_cap} landclaim cap. Please clean up unused claims. Rules: {rules_url}
DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_ENABLED=true
DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_WINDOW_SECONDS=600
DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_TEMPLATE=Welcome back. If you were disconnected during travel, wait a moment before retrying the same transition.
DUNE_PLAYER_PRESENCE_RESTART_PRIVATE_WARNINGS_ENABLED=true
DUNE_PLAYER_PRESENCE_RESTART_PRIVATE_WARNING_MARKS_SECONDS=1800,600,300,60
DUNE_PLAYER_PRESENCE_RESTART_PRIVATE_WARNING_TEMPLATE=Server maintenance in about {remaining}. Please get to a safe place.
DUNE_PLAYER_PRESENCE_POST_RESTART_RETURN_ENABLED=true
DUNE_PLAYER_PRESENCE_POST_RESTART_WINDOW_SECONDS=3600
DUNE_PLAYER_PRESENCE_POST_RESTART_TEMPLATE=Maintenance is complete. If anything looks wrong, report it through {server_url}.
DUNE_PLAYER_PRESENCE_STUCK_POSITION_ENABLED=false
DUNE_PLAYER_PRESENCE_STUCK_POSITION_TEMPLATE=Your position looks unusual. If you are stuck, message an admin before relogging repeatedly.
DUNE_PLAYER_PRESENCE_ADMIN_NAMES=
DUNE_PLAYER_PRESENCE_ADMIN_FLS_IDS=
DUNE_PLAYER_PRESENCE_ADMIN_ALERT_INTERVAL_SECONDS=900
DUNE_PLAYER_PRESENCE_MAP_HEALTH_PUBLIC_ENABLED=true
DUNE_PLAYER_PRESENCE_MAP_HEALTH_DEGRADED_TEMPLATE=Server notice: some travel destinations are recovering ({online}/{expected} online). If travel fails, wait 1-2 minutes and retry.
DUNE_PLAYER_PRESENCE_MAP_HEALTH_RECOVERED_TEMPLATE=Server notice: all travel destinations are online again ({online}/{expected}).
DUNE_PLAYER_PRESENCE_MAP_HEALTH_ADMIN_ENABLED=true
DUNE_PLAYER_PRESENCE_MAP_HEALTH_ADMIN_TEMPLATE=Admin alert: map health degraded, {online}/{expected} online. Offline: {offline_maps}
DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_ENABLED=true
DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_THRESHOLDS=30,35,40
DUNE_PLAYER_PRESENCE_POPULATION_PUBLIC_TEMPLATE=Server is getting busy: {count} online. Travel and loading may take longer.
DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_ENABLED=true
DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_INTERVAL_SECONDS=1800
DUNE_PLAYER_PRESENCE_POPULATION_ADMIN_DIGEST_TEMPLATE=Admin population: {count} online. Maps: {map_counts}
DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_ENABLED=true
DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_WINDOW_SECONDS=600
DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_THRESHOLD=3
DUNE_PLAYER_PRESENCE_RECONNECT_SUPPORT_TEMPLATE=Looks like you have reconnected several times. If travel is stuck, report it through {server_url}.
DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_ENABLED=true
DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_INTERVAL_SECONDS=1800
DUNE_PLAYER_PRESENCE_ADMIN_ANOMALY_DIGEST_TEMPLATE=Admin digest: stuck/recent anomalies={stuck_count} ({stuck_names}); over base cap={over_base_cap}.
DUNE_PLAYER_PRESENCE_ADMIN_MAP_ROSTER_DIGEST_ENABLED=true
DUNE_PLAYER_PRESENCE_ADMIN_MAP_ROSTER_DIGEST_INTERVAL_SECONDS=1800
DUNE_PLAYER_PRESENCE_ADMIN_MAP_ROSTER_DIGEST_TEMPLATE=Admin roster: {count} online. {map_roster}
DUNE_PLAYER_PRESENCE_ADMIN_UNIQUE_DAILY_DIGEST_ENABLED=true
DUNE_PLAYER_PRESENCE_ADMIN_UNIQUE_DAILY_DIGEST_INTERVAL_SECONDS=86400
DUNE_PLAYER_PRESENCE_ADMIN_UNIQUE_DAILY_DIGEST_TEMPLATE=Admin daily players: {unique_count} unique accounts seen today, {count} currently online.
DUNE_PLAYER_PRESENCE_MAINTENANCE_ONLINE_ADMIN_ENABLED=true
DUNE_PLAYER_PRESENCE_MAINTENANCE_ONLINE_WINDOW_SECONDS=1800
DUNE_PLAYER_PRESENCE_MAINTENANCE_ONLINE_ADMIN_TEMPLATE=Admin maintenance check: {count} players still online before maintenance. {map_roster}
DUNE_PLAYER_PRESENCE_MAP_WITH_PLAYERS_UNHEALTHY_ADMIN_ENABLED=true
DUNE_PLAYER_PRESENCE_MAP_WITH_PLAYERS_UNHEALTHY_ADMIN_TEMPLATE=Admin alert: unhealthy maps still report players: {impacted_maps}
DUNE_PLAYER_PRESENCE_PUBLIC_MAINTENANCE_CANCELLED_ENABLED=true
DUNE_PLAYER_PRESENCE_PUBLIC_MAINTENANCE_CANCELLED_TEMPLATE=Maintenance has been cancelled or delayed. Normal play can continue.
DUNE_PLAYER_PRESENCE_INCIDENT_MODE_PUBLIC_ENABLED=true
DUNE_PLAYER_PRESENCE_INCIDENT_MODE_ACTIVE=false
DUNE_PLAYER_PRESENCE_INCIDENT_MODE_ON_TEMPLATE=Server notice: admins are investigating travel instability. Updates at {server_url}.
DUNE_PLAYER_PRESENCE_INCIDENT_MODE_OFF_TEMPLATE=Server notice: incident mode is cleared. Normal play can continue.
DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED=true
DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DIGEST_LIMIT=8
DUNE_PLAYER_PRESENCE_DIGEST_LOG_LIMIT=250
DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED=true
DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_MESSAGE_ENABLED=true
DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_MESSAGE_TEMPLATE=A Base Reconstruction Tool has been added to your inventory. You may need to log out and back in before it appears.
DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_ENABLED=true
DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_NODE=DA_SQ_VermiliusGap.Relocate.RelocateOutsideHBS.Drive north to the Vermilius Gap
DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_TEMPLATE=Congrats! {playername} has outrun Shai-Hulud!
```

Presence templates support `{playername}`, `{player_name}`, `{count}`, `{player_count}`, `{server_name}`, `{server_url}`, and `{rules_url}`. Base-cap templates also support `{base_cap}`. Restart-warning templates support `{remaining}` and `{remaining_seconds}`. Vermilius Gap templates support `{playername}`, `{player_name}`, and `{story_node_id}`.

Global join/leave messages use `DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE`, `DUNE_PLAYER_PRESENCE_RETURN_JOIN_TEMPLATE`, and `DUNE_PLAYER_PRESENCE_LEAVE_TEMPLATE` through the public `announce()` path. First-time joins are accounts missing from `seenAccounts`; returning joins are accounts already recorded there. `DUNE_PLAYER_PRESENCE_JOIN_MESSAGE_DELAY_SECONDS` can delay join-triggered public and private messages until a player has remained online long enough for the client chat path to render them. Player-presence announcements override the shared announcement routing and default to `DUNE_PLAYER_PRESENCE_ANNOUNCE_ROUTING_KEYS=<empty>` so each online client receives one copy. Do not set this to multiple routing keys unless you intentionally want fan-out; the shared `DUNE_ANNOUNCE_CHAT_ROUTING_KEYS=HaggaBasin.0,Survival_1.dim_0,<empty>` pattern can make HUD notices render more than once.

The private welcome path runs on every detected join for existing and new players after the first baseline poll. It uses the same Paul chat sender, disables dashboard `!!!` wrapping, derives the joined player's live whisper route from their FLS id, publishes to `DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_EXCHANGE`, and sets `m_ChannelType` to `DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL`. The intended private route is `chat.whispers` with `Whispers`. As of 2026-05-27, live player chat payloads use `m_Timestamp`; the shared publisher defaults to that spelling and can be overridden with `DUNE_ANNOUNCE_CHAT_TIMESTAMP_FIELD` if another game build requires `m_TimeStamp`. See `docs/private-chat-replies.md`. The default private welcome message is:

```text
Welcome! Please check {rules_url} for server rules.
```

Automated private messages are derived from local state and operator config rather than hard-coded server details. These use the private helper and should render as whispers/private messages:

- `FIRST_SEEN` sends once per account after its first observed join.
- `HAGGA_ARRIVAL` sends once when an online player is first observed on `HaggaBasin`.
- `DEEP_DESERT_FIRST` sends once when an online player is first observed on a Deep Desert map.
- `DEEP_DESERT_JOIN_MESSAGES` sends a private Paul whisper each time a player enters or logs into a Deep Desert instance. Partition `8` is treated as PVE Casual; partition `31` is treated as PVE Hardcore with 3x harvest, higher storm/Coriolis penalties, and weekly scoped cleanup.
- `BASE_REMINDERS` queries `dune.totems`, `dune.actors`, and `dune.landclaim_segments` for that account and sends first-base, near-cap, or over-cap reminders only when the count changes.
- `RECONNECT_RECOVERY` sends when a player rejoins inside the configured short reconnect window.
- `RESTART_PRIVATE_WARNINGS` mirrors scheduled admin-panel restart/announcement jobs to online players at configured remaining-time marks.
- `POST_RESTART_RETURN` sends once per recently executed restart job when a player rejoins after maintenance.
- `STUCK_POSITION` is available but disabled by default; it only warns when an online player has no map/location in the DB, which can be noisy during travel.
- `MAP_HEALTH_PUBLIC` announces when the farm transitions from full health to degraded, and again when all partition rows are back online. It derives `{online}` and `{expected}` from `dune.world_partition`, `dune.farm_state`, and `dune.active_server_ids`.
- `MAP_HEALTH_ADMIN` privately alerts currently online admins at `DUNE_PLAYER_PRESENCE_ADMIN_ALERT_INTERVAL_SECONDS` while map health remains degraded.
- `POPULATION_PUBLIC` announces once when online player count crosses a configured threshold band.
- `POPULATION_ADMIN_DIGEST` privately sends currently online admins a periodic player-count-by-map digest.
- `RECONNECT_SUPPORT` privately nudges players who reconnect repeatedly inside a short window.
- `ADMIN_ANOMALY_DIGEST` privately sends currently online admins a compact digest for stuck-transition candidates and over-cap base counts.
- `ADMIN_MAP_ROSTER_DIGEST` privately sends admins exact online player rosters grouped by map.
- `ADMIN_UNIQUE_DAILY_DIGEST` privately sends admins the daily unique-account count.
- `MAINTENANCE_ONLINE_ADMIN` privately tells admins who is still online, grouped by map, before scheduled maintenance.
- `MAP_WITH_PLAYERS_UNHEALTHY_ADMIN` privately alerts admins when an unhealthy map still reports connected players.
- `PUBLIC_MAINTENANCE_CANCELLED` publishes a cancellation/delay notice when an announcement or restart job is cancelled after scheduling.
- `INCIDENT_MODE_PUBLIC` publishes manual incident on/off notices when `DUNE_PLAYER_PRESENCE_INCIDENT_MODE_ACTIVE` changes.
- `ADMIN_FIRST_LOGIN_DAILY` sends the current admin digest set to each configured admin on their first login each day.

The subfief bonus repair path runs quietly for joined/rejoined players when
`DUNE_PLAYER_PRESENCE_SUBFIEF_BONUS_ENFORCER_ENABLED=true`. It checks the
joined account's current `dune.player_state.player_pawn_id` actor and writes
`DunePlayerCharacterAttributeSet.SubfiefLimitBonus` only when the current
base/current value is below the configured bonus. The configured bonus is
`DUNE_PLAYER_PRESENCE_SUBFIEF_MIN_BONUS` when set, otherwise
`DUNE_SUBFIEF_LIMIT_BONUS`, otherwise `DUNE_SUBFIEF_LIMIT -
DUNE_SUBFIEF_BASE_LIMIT`.

The public/global presence events are intentionally not private:

- `JOIN` and `LEAVE` are the visible welcome/goodbye population notices.
- `MAP_HEALTH_PUBLIC`, `POPULATION_PUBLIC`, `PUBLIC_MAINTENANCE_CANCELLED`, `INCIDENT_MODE_PUBLIC`, `TRANSFER_POLICY_PUBLIC`, `RULES_CHANGE_PUBLIC`, `PEAK_PUBLIC`, and `DAILY_STATUS_PUBLIC` publish server-wide notices.
- `VERMILIUS_GAP` is currently a public celebration announcement.

For the full private/global routing matrix, command-reply behavior, and RabbitMQ verification steps, use [private-chat-replies.md](private-chat-replies.md). That runbook tracks `chat.whispers`, `Whispers`, timestamp-field behavior, and the expected `reply.stdout` metadata from command smoke tests.

Admin-private recipients are derived from currently online players whose character name or FLS id matches `DUNE_PLAYER_PRESENCE_ADMIN_NAMES` / `DUNE_PLAYER_PRESENCE_ADMIN_FLS_IDS`. Keep real admin identifiers in private `.env`, not in committed examples or docs. Digest entries are stored in `backups/admin-bot/player-presence.json` under `adminDigestLog`, and the admin panel exposes them on the Admin Digests tab.

The starter Base Reconstruction Tool path grants one `BaseBackupTool` to each newly observed joining account that has not already been recorded in `backups/admin-bot/player-presence.json`. When the grant succeeds, it sends a private message telling the player they may need to log out and back in before the item appears.

The quiet starter emote path grants `DUNE_PLAYER_PRESENCE_STARTER_EMOTE_TEMPLATES` into the configured emote inventory type, default `14`, for newly observed joining accounts. It records successful accounts under `starterEmotesGranted` in the same state file and does not send a public or private message.

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

The installer writes `/etc/systemd/system/dune-player-presence-announcer.service`, enables it, and starts it. Because it is enabled with `WantedBy=multi-user.target`, `Requires=docker.service`, `Restart=always`, and an unlimited start-limit interval, it starts after host reboots and keeps restarting after script failures or early boot dependency races. The generated unit uses the current checkout path and current user by default; set `DUNE_PLAYER_PRESENCE_SERVICE_USER=<user>` when running the installer to choose another system user.

Operational checks:

```bash
systemctl is-enabled dune-player-presence-announcer.service
systemctl status dune-player-presence-announcer.service
journalctl -u dune-player-presence-announcer.service -f
```

The first service poll records the current online set and does not announce those already online. Announcements start on later observed joins/leaves.
