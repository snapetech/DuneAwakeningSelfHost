# Discord Bot Adapter

DASH exposes the audited Discord adapter contract directly from the admin
service. Read and operations routes are role-scoped. The only write surface is
the narrowly typed, Discord-identity-bound community wallet/shop contract
documented in [`community-rewards.md`](community-rewards.md). The adapter does
not need the admin token and never accepts a shell command, SQL statement,
container id, game-admin action, raw database write, or arbitrary payload.

Configuration:

```env
DUNE_DISCORD_ADAPTER_ENABLED=true
DUNE_BOT_API_TOKEN=replace-with-a-long-random-adapter-token
DISCORD_OBSERVER_ROLE_IDS=111111111111111111
DISCORD_MODERATOR_ROLE_IDS=222222222222222222
DISCORD_ADMIN_ROLE_IDS=333333333333333333
DISCORD_OWNER_ROLE_IDS=444444444444444444
```

`DUNE_BOT_API_TOKEN_FILE` can be used instead of the env token. The adapter
requires `Authorization: Bearer <token>` and compares it in constant time.
POST routes also require actor context:

```json
{
  "actor": {
    "guildId": "1",
    "channelId": "2",
    "userId": "3",
    "username": "operator",
    "roleIds": ["111111111111111111"],
    "requestId": "discord-interaction-id"
  }
}
```

Live routes:

- `GET /api/integrations/discord/health`
- `GET /api/integrations/discord/version`
- `GET /api/integrations/discord/backups/list`
- `POST /api/integrations/discord/status`
- `POST /api/integrations/discord/readiness`
- `POST /api/integrations/discord/services`
- `POST /api/integrations/discord/population`
- `POST /api/integrations/discord/servers`
- `POST /api/integrations/discord/ports`
- `POST /api/integrations/discord/db`
- `POST /api/integrations/discord/announcements`
- `POST /api/integrations/discord/events`
- `POST /api/integrations/discord/ops`
- `POST /api/integrations/discord/community`

Observer roles can read status, readiness, and services. Moderator and higher
roles can read aggregate population and partition metadata. Responses redact
credential-like keys and bound strings/lists. Adapter audit records include
the route, Discord user id, and mapped tier.

The community route permits `howtolink`, one-time `link`, `balance`, `catalog`,
`kits`, idempotent `buy`, `track`, and idempotent `claim`. It derives the wallet
from `actor.userId`; it never accepts a Dune account ID for a linked player
operation. Purchases use the Discord interaction ID as their replay key. These
actions require the adapter bearer token but no configured observer role so
ordinary guild members can use the shop after linking. The bot enforces the
single guild and channel allowlist before calling the adapter.

`POST /api/integrations/discord/broadcast` exists for contract compatibility
and always refuses execution. Use DASH's independently authenticated browser
announcement controls for administrative writes. Generic game/admin writes
remain hard-disabled from Discord.
