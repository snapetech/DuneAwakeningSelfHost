# First-party Discord bot

DASH includes a first-party, guild-scoped `/dune` slash-command bot. It uses
Discord Gateway v10 and calls only the permission-mapped DASH Discord adapter.
It has no database credentials, Docker socket, admin owner token, raw shell, or
filesystem-write API.

The implementation is `scripts/discord-bot.py`. It uses Python's standard
library, including a bounded RFC 6455 client, so the host service does not
download runtime packages from PyPI or npm.

Discord's official documentation identifies Gateway interactions as the
default persistent delivery mechanism and requires application commands to be
registered through the HTTP API:

- <https://docs.discord.com/developers/events/gateway>
- <https://docs.discord.com/developers/platform/interactions>
- <https://docs.discord.com/developers/interactions/application-commands>

## Command surface

One guild-only command is bulk-registered with all 29 peer subcommands plus
eight community commands: 37 subcommands across seven groups.

| Command | Minimum DASH role | Result |
| --- | --- | --- |
| `core` | guild/channel allowlist | `about`, `ping`, `help` |
| `server` | observer | `health`, `status`, `summary`, `readiness`, `services` |
| `data` | moderator for population/maps | `population`, `backups`, `maps` |
| `ops` | moderator | `activity`, `combat`, `resources`, `economy`, `inventory`, `location`, `soc`, `prometheus`, `dashboard` |
| `admin` | observer/moderator by route | `doctor`, `cooldowns`, `latency`, `events`, `broadcast` |
| `infra` | observer/moderator by route | `version`, `servers`, `ports`, `database` |
| `shop` | guild/channel allowlist; linked identity where required | `howtolink`, `link`, `balance`, `catalog`, `buy`, `kits`, `track`, `claim` |

`broadcast` reports that Discord writes are disabled; it cannot broadcast.
`dashboard` reports private availability without disclosing the LAN/VPN URL.
The shop commands accept only bounded schema-declared options. They link with a
short-lived one-use code, derive the wallet from the invoking Discord user ID,
and use the interaction ID for purchase replay protection. The ops endpoints
return aggregates or bounded recent rows and never raw
credentials, unrestricted SQL, filesystem paths, or host commands.

Responses are ephemeral, suppress all mentions, cap Discord content at 2,000
characters, and truncate large adapter output. The admin adapter performs the
authoritative role decision from the invoking member's Discord role IDs. The
bot cannot promote its own request.

## Discord application setup

1. Create an application and bot in the Discord Developer Portal.
2. Install it in exactly one server with `bot` and `applications.commands`.
3. The bot needs permission to use application commands and send responses in
   the intended channel. It does not need Administrator.
4. Do not enable Message Content, Guild Members, or Presence privileged
   intents. DASH identifies with `GUILDS` only (`1 << 0`).
5. Copy the application ID, guild/server ID, and bot token into the private
   `.env` or root/operator-readable secret files.

Configuration:

```dotenv
DUNE_DISCORD_ADAPTER_ENABLED=true
DUNE_BOT_API_TOKEN=replace-with-a-separate-random-adapter-token
DUNE_DISCORD_BOT_TOKEN=replace-with-the-discord-bot-token
DUNE_DISCORD_APPLICATION_ID=111111111111111111
DUNE_DISCORD_GUILD_ID=222222222222222222
DUNE_DISCORD_CHANNEL_IDS=333333333333333333
DUNE_DISCORD_ADAPTER_URL=http://127.0.0.1:18080
DUNE_DISCORD_ADAPTER_HOST=admin-panel:8080
DUNE_DISCORD_REGISTER_COMMANDS=true
DUNE_DISCORD_REQUEST_TIMEOUT_SECONDS=2.5
DUNE_DISCORD_ALLOWED_HOST=your-server-short-hostname
DISCORD_OBSERVER_ROLE_IDS=444444444444444444
DISCORD_MODERATOR_ROLE_IDS=555555555555555555
DISCORD_ADMIN_ROLE_IDS=666666666666666666
DISCORD_OWNER_ROLE_IDS=777777777777777777
```

`DUNE_DISCORD_BOT_TOKEN_FILE` and `DUNE_BOT_API_TOKEN_FILE` take precedence
over inline values. The two tokens have different purposes and should never be
the same.

If `DUNE_DISCORD_CHANNEL_IDS` is empty, the bot accepts commands from any
channel in the configured guild. A non-empty comma-separated list restricts
invocation before the adapter is called.

## Install and operate

The installer requires the exact short hostname in
`DUNE_DISCORD_ALLOWED_HOST`, writes a hardened unit, and enables it:

```bash
./scripts/install-discord-bot-service.sh .env
systemctl status dune-discord-bot.service
```

When credentials are incomplete, the unit remains active and writes
`status=waiting-for-credentials` instead of crash-looping. It re-reads `.env`
every 30 seconds. With a complete set, it bulk-upserts the guild command and
connects to the Gateway.

Read-only configuration check:

```bash
./scripts/discord-bot.py --env-file .env --check
```

The JSON reports only configured booleans, adapter origin, channel restriction
count, command count, and the fact that Message Content intent is disabled.
Tokens are never returned.

Force a one-time command registration after changing command definitions:

```bash
./scripts/discord-bot.py --env-file .env --register
sudo systemctl restart dune-discord-bot.service
```

Runtime state is stored at:

```text
backups/discord-bot/state.json
```

It contains connection/reconnect state, command count, last command name/time,
and redacted errors. It contains no Discord token, interaction token, adapter
token, user message content, or adapter response.

## Gateway and failure behavior

- TLS certificate and hostname verification use the platform trust store.
- The WebSocket upgrade verifies `Sec-WebSocket-Accept`.
- Client frames use a fresh cryptographic mask; server-masked frames fail.
- Frames, handshake headers, Gateway payloads, buffers, and REST responses have
  explicit size limits.
- Gateway sends are capped to Discord's 4,096-byte payload limit.
- Heartbeats carry the last sequence; a missing acknowledgement reconnects.
- READY session ID, sequence, and resume URL are process-memory only and used
  for resumable reconnects.
- Reconnect backoff grows from one to sixty seconds.
- Discord and adapter HTTP calls have bounded timeouts.
- Wrong guild and disallowed channel requests are rejected before adapter IO.
- The adapter independently authenticates its bearer token, maps roles, bounds
  output, redacts credentials, and audits Discord user ID/tier/route.

No Discord command performs an administrative or generic game write.
`/broadcast` remains blocked. The `shop` group can redeem a link code, create an
atomic community purchase, and queue an unlocked track claim through its typed
adapter contract. Community delivery has its own gates and offline-player
worker; other writes stay in the RBAC-protected browser/API.

## Validation

```bash
make test-discord-bot
```

The suite validates masked and extended WebSocket frames, server mask refusal,
guild-only command schema, role propagation, bearer/Host routing, wrong-guild
and channel denial, authorized routing and formatting, and secret-free config
status. A real `READY`/interaction canary requires operator-supplied Discord
application credentials; lack of those credentials is reported as unknown, not
as a successful external integration test.
