# Moderation, Connection History, and Security Signals

## Proven contract

The current Dune: Awakening server schema exposes no confirmed native
persistent-ban table or login-rejection function. The peer implementation in
Arrakis Command Nexus also stores bans in its dashboard database; it does not
write a Dune ban contract. DASH therefore labels the behavior precisely:

- a **ban** is an isolated operator policy record;
- an active matching identity is ejected with the confirmed native
  `KickPlayer` Version 2 notification whenever it is observed online;
- this does not prevent the initial authentication attempt;
- enforcement retries after a cooldown and records every publish result;
- unban stops future ejection without changing the game database.

Confidence is **high** for the registry, history, matching, and RabbitMQ publish
receipt. Confidence is **moderate** for the final client disconnect because the
proprietary game process does not return a per-player acknowledgement.

## Data model and integrity

State lives at `backups/moderation/moderation.sqlite3` by default. It is not
stored in the Funcom Postgres schema.

| State | Contract |
| --- | --- |
| Cases | Account/Funcom/platform identity, category, severity, assignment, status, summary, timestamps |
| Case events | Append-only notes, workflow changes, ban lifecycle, expiry, and enforcement receipts; update/delete triggers reject mutation |
| Bans | Permanent or expiring policy rows matched against account, Funcom, or platform identity |
| Allowlist | Account, Funcom, or platform identity registry with optional expiry |
| Presence sessions | Join/last-seen/leave intervals, map, partition, and sample count |
| Maintenance population observations | Zero-inclusive five-minute count aggregates used for low-impact scheduling; no identities, coordinates, or IP addresses |
| Heatmap cells | Daily/hourly/map aggregates in coarse world-coordinate cells |
| Security events | Deduplicated and redacted anti-cheat, authentication, disconnect, tamper, and rate-limit signals |
| Enforcement receipts | Native kick publish result, account, policy/ban, timestamp, and bounded redacted detail |

The SQLite database uses foreign keys, WAL, full synchronous writes, immediate
write transactions, private `0700`/`0600` modes, and configured host ownership.
Backups use SQLite's online backup API followed by `pragma integrity_check`.

## Worker

The admin-panel process starts one `moderation-history` worker. Each tick:

1. Reads confirmed `Online` rows from `dune.player_state` and joins account,
   server, partition, and persisted pawn-transform context.
2. Opens, updates, or closes presence sessions.
3. Adds a coarse heatmap sample when finite X/Y coordinates exist.
4. Expires temporary bans.
5. Matches online identities against active bans.
6. If allowlist enforcement was explicitly enabled, matches identities against
   the allowlist too.
7. Publishes `KickPlayer` only when every mutation/native transport gate is on.
8. Normalizes a bounded tail from exact configured Compose services.
9. Prunes expirable telemetry according to retention policy.

The worker never stores raw peer IPs. Its security normalizer removes IPv4,
IPv6, email addresses, and common credential fields before insertion. It stores
only bounded matching log lines; unrelated log lines are discarded.

## Gates and defaults

```dotenv
DUNE_MODERATION_ENABLED=true
DUNE_MODERATION_ENFORCEMENT_ENABLED=true
DUNE_MODERATION_DATABASE=/workspace/backups/moderation/moderation.sqlite3
DUNE_MODERATION_POLL_SECONDS=15
DUNE_MODERATION_RETENTION_DAYS=90
DUNE_MODERATION_HEATMAP_CELL_SIZE=25000
DUNE_MODERATION_KICK_COOLDOWN_SECONDS=60
DUNE_MODERATION_LOG_SERVICES=survival,director,gateway,game-rmq
```

Native enforcement also requires:

```dotenv
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_PLAYER_RUNTIME_MUTATIONS_ENABLED=true
DUNE_ADMIN_GM_COMMANDS_ENABLED=true
DUNE_SERVER_NOTIFICATION_SYSTEM_ENABLED=true
DUNE_SERVER_COMMANDS_AUTH_TOKEN=<configured secret>
```

`DUNE_MODERATION_LOG_SERVICES` accepts exact Compose service names only. A
missing service is reported in worker state and does not stop presence or ban
processing.

## Dashboard and API

Open the **Moderation** page. It provides case workflow, permanent/temporary
bans, unban, an allowlist registry and explicit enforcement toggle, worker
status, presence/security/enforcement history, and a coarse activity view.

```http
GET /api/moderation
GET /api/moderation?account_id=42&limit=200
```

Writes use `POST /api/moderation` with `case-create`, `case-update`,
`case-note`, `ban`, `unban`, `allowlist-add`, `allowlist-remove`,
`allowlist-policy`, `tick`, or `prune`.

RBAC maps the endpoint to `moderation.write`. Moderator, administrator, and
owner roles have it by default. Ban, unban, and allowlist-policy operations
require exact confirmation phrases shown by the API.

### Ban example

```bash
curl -sS -H 'Host: admin-panel:8080' \
  -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  http://127.0.0.1:18080/api/moderation \
  --data '{"action":"ban","accountId":42,"reason":"documented policy violation","durationHours":24,"confirm":"CREATE ENFORCED BAN"}'
```

The response contains the case, policy ban, and immediate worker result. If the
player is online and all gates are ready, the enforcement array records the
queued native kick.

## Allowlist behavior

The allowlist is a registry until enforcement is explicitly enabled. Enabling
it ejects every observed online identity which matches none of the account,
Funcom, or platform entries. Populate and verify the registry first. Disabling
the policy leaves the registry intact.

## Backup, restore, and validation

`scripts/backup-state.sh` writes `moderation.sqlite3` when the live database
exists. `scripts/verify-backup.sh` runs an integrity check. Restore is opt-in
and stops the admin-panel writer first:

```bash
./scripts/restore-state.sh --moderation .env backups/<UTC timestamp>
make test-moderation
make moderation-check
make validate
```

Restore removes stale WAL/SHM files and installs the snapshot as mode `0600`.
The focused tests cover append-only history, identity matching, temporary
expiry, idempotent unban, allowlist policy, session close, coarse cells,
redaction/deduplication, enforcement cooldowns, permissions, and validation.

## Recovery

- Worker errors are visible in the Moderation page and do not stop HTTP.
- Set `DUNE_MODERATION_ENFORCEMENT_ENABLED=false` and recreate only the admin
  panel to stop ejection while retaining cases/history.
- Disable allowlist enforcement from the dashboard before changing its entries.
- Unban revokes the policy row and retains append-only case history.
- Never delete individual case events. Use telemetry retention or restore a
  verified whole-database snapshot.
