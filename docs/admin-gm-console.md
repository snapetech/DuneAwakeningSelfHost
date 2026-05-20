# Admin GM Console Research

This records what is known about the native Dune admin/cheat path without guessing on the live server.

## Verified Surfaces

- The live survival binary contains `UDuneServerCommandSubsystem`, `UDuneServerCommandsCheatManager`, `UServiceMessageCommand`, `AdminLogin`, `PrintAllowedCommands`, `SendDuneServerCommand`, `ServerCommand`, and `ServerExecRPC` strings.
- The survival container exposes `127.0.0.1:10000`, but tested paths only returned health/404 responses. This does not look like the command route.
- Admin RabbitMQ has map RPC bindings on exchange `rpc` with routing keys such as `Survival_11`, plus per-map `grant.<server_id>` and `response.<server_id>` routes.
- The active dedicated server allow-list found in `DuneSandbox/Config/DedicatedServerGame.ini` includes:
  - Console commands: `obj`, `FGL.ComponentAuditRequested`
  - GM commands: `AddItemToInventory`, `AddBasicInventoryToCharacter`, `SpawnVehicle`, teleport/travel helpers, `Fly`, `Ghost`, `Walk`, targeted destroy helpers, and `PrintPos`.

## Current Panel Behavior

The Admin Actions pane now includes a Native GM / Cheat Console section. It shows:

- The discovered command allow-list.
- Shipped cheat scripts and their command bodies where known.
- Candidate RabbitMQ map routes from live `farm_state`.
- A dry-run payload preview composer for command, route, target player, and arguments.

Execution is intentionally blocked until the RabbitMQ payload envelope for `UDuneServerCommandSubsystem` is proven. The safe first probe should be `PrintPos` against `Survival_11`, because it should not mutate state.

## Chat Command Plan

The chat-command bridge uses `&gm` as the native-admin namespace. Commands are split into risk tiers so safe operator workflows can be used while the native live command payload remains gated.

### Tier 0: Safe Probes

Implemented:

```text
&gm help
&gm test
&gm routes
&gm dry <native command...>
&gm pos
```

- `&gm help` lists the wired GM command names.
- `&gm test` replies `f00` through the normal chat reply path.
- `&gm routes` resolves the admin character, current map route, and whether native GM execution gates are open.
- `&gm dry ...` builds and returns a native command envelope preview without publishing.
- `&gm pos` prepares or sends `PrintPos`, depending on the native GM gates.

### Tier 1: Admin Movement

Implemented:

```text
&gm mark [name]
&gm marks
&gm unmark [name]
&gm recall [name]
&gm goto <playername>
&gm bring <playername>
&gm tp <x> <y> <z>
&gm map <map> [dimension]
&gm travel <map> [location]
&gm dimension <map> <dimension>
&gm patrol
&gm sandworm
&gm marker
&gm fly
&gm ghost
&gm walk
```

- `&gm mark` saves the admin's current database-backed location snapshot under `backups/admin-panel/gm-locations.json`. The default marker is `location0`.
- `&gm marks` lists saved markers for the issuing admin.
- `&gm unmark` deletes a saved marker. The default marker is `location0`.
- `&gm recall` prepares or sends `TeleportToExact <x> <y> <z>` back to the saved marker. It remains a preview until native GM command execution is verified and enabled.
- `&gm goto`, `&gm bring`, `&gm tp`, `&gm map`, `&gm travel`, and `&gm dimension` use the shared native GM adapter and remain previews until all native GM gates are enabled.
- `&gm patrol`, `&gm sandworm`, and `&gm marker` wrap `PatrolShipTeleportToNearest`, `TeleportToSandworm`, and `TeleportToPersonalMarker`.
- `&gm fly`, `&gm ghost`, and `&gm walk` are wired as gated admin movement-mode commands.

Already available outside the `&gm` namespace:

```text
&goto <playername>
&bring <playername>
```

These use the shared native GM adapter for online movement previews. They only publish when all live GM gates are enabled.

### Tier 2: Player Help

Implemented:

```text
&gm where <playername>
&gm unstuck <playername> [mark]
&where <playername>
&teleport <playername>
```

- `&gm where` is the namespaced form of `&where`.
- `&gm unstuck` prepares or sends a gated `TeleportToExact` for a target player. It uses the named saved marker, defaulting to `location0`; if no marker exists it falls back to the admin's current location.
- `&where` reports current known state and location.
- `&teleport` moves an offline target to the admin's current position using the database function `dune.admin_move_offline_player_to_partition(...)`, only when offline teleport execution is explicitly enabled.

### Tier 3: Inventory/Admin

Implemented as gated native previews:

```text
&gm item <playername> <template> [count] [quality]
&gm kit <playername> [basic]
&gm xp <playername> <track> <amount> [add|set] [level]
&gm vehicle <template> [args...]
```

- `&gm item` prepares or sends `AddItemToInventory <playername> <template> <count> [quality]`.
- `&gm kit` prepares or sends `AddBasicInventoryToCharacter <playername>`. Only the `basic` kit is wired right now.
- `&gm xp` resolves the player and specialization track, then returns the admin-panel mutation request body for `POST /api/admin/xp`. It does not write from chat; execute through the token-gated panel so the mutation gate and audit trail stay in force.
- `&gm vehicle` prepares or sends `SpawnVehicle <template> [args...]`; exact vehicle template and argument behavior still needs validation.

### Tier 4: Dangerous Commands

Do not enable by default:

```text
&gm fly
&gm ghost
&gm walk
&gm destroy target
```

`Fly`, `Ghost`, and `Walk` are admin movement modes and can be enabled after `PrintPos` proves the payload route. Targeted destroy commands should require a separate explicit confirmation, audit trail, and allow-list. Do not wire `DestroyEntireBuilding`, `DestroyPlaceable`, or related destructive commands as casual chat shortcuts.

## Why Execution Is Blocked

We know the command names and likely transport, but not the exact serialized message body. Publishing guessed messages into a live map `rpc` queue can be ignored, poison a consumer, or trigger unintended behavior. The panel therefore supports operator workflow and payload preview now, while hard-blocking `/api/admin/gm/execute`.

## Probe Tool

Use `scripts/probe-gm-command.py` to test harmless native command envelopes without wiring unverified execution into the dashboard:

```bash
./scripts/probe-gm-command.py --command PrintPos --target-player Lukano --route Survival_11
docker compose logs --since=30s survival | rg "PrintPos|ServerCommand|ServerExec|DuneServer|Admin|Command"
```

Preview the currently implemented envelope set without publishing:

```bash
./scripts/probe-gm-command.py --preview --command PrintPos --target-player Lukano --route Survival_11
```

If AMQP is unavailable, the probe can also publish through RabbitMQ's management API:

```bash
DUNE_GM_COMMAND_RMQ_URL=http://127.0.0.1:15672 \
DUNE_GM_COMMAND_RMQ_USER=guest \
DUNE_GM_COMMAND_RMQ_PASSWORD=guest \
./scripts/probe-gm-command.py --transport management --command PrintPos --target-player Lukano --route Survival_11
```

Current probe result: the `rpc` exchange route to `Survival_11` is real and the `Survival_11_queue` consumer drains probe messages, but the tested JSON-shaped envelopes do not produce a visible `PrintPos` response or survival log entry. Treat the route as located but the payload envelope as unverified.

Current transport note: `rabbitmqctl` can inspect the admin broker, but AMQP/HTTP connections to `admin-rmq` are timing out from the host/admin-panel network in this runtime. Do not change Docker networking without operator approval; use this document to separate transport reachability from envelope correctness.

Implemented `PrintPos` candidate envelopes:

- JSON-RPC notify with params array.
- JSON-RPC `SendDuneServerCommand` and `ServerExec` array variants.
- `{"Command":"ServerCommand","CommandText":"PrintPos"}` service-message style.
- `SendDuneServerCommand`, `ServerExec`, and `ServerExecRPC` object variants.
- Raw task-style array/object variants.
- Positional RPC argument variants inferred from `TRmqRpcCallProxy<TArray<FString>, FString>` and `TRmqRpcCallProxy<TArray<FString>, FString, FString>` binary symbols.
- Plain text `PrintPos` and `ServerExec <target> PrintPos` variants.

`scripts/dune_gm_command.py` is the shared adapter for probe and chat-command code. It builds the native GM command envelope and publishes to the admin RabbitMQ `rpc` exchange. Online teleport chat commands are connected to it but remain hard-gated:

```env
DUNE_ADMIN_GM_COMMANDS_ENABLED=true
DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true
DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true
```

Until all three are true, `&goto <playername>` and `&bring <playername>` only return a payload preview. The planned native command texts are:

- `&goto <playername>`: `TeleportToPlayer <playername>` targeted at the admin.
- `&bring <playername>`: `TeleportToExact <admin-x> <admin-y> <admin-z>` targeted at the online player.

## Targeted Kick Status

No confirmed targeted player kick command has been found yet.

What we verified:

- The active `DedicatedServerGame.ini` GM allow-list does not include a clear `KickPlayer`, `AdminKick`, `DisconnectPlayer`, or session-removal command.
- The live server binary does contain lower-level session and disconnect strings including `KickLobbyMember`, `RemoveSessionMember`, `BattlEyeMegaKick`, and `ClientWasKicked`.
- Those strings are not enough to execute safely. We still need the exact console/GM command syntax, required identifiers, and verified RabbitMQ command envelope.
- The database exposes player online state, `server_id`, `player_controller_id`, pawn id, FLS id, and map location, but it does not expose a live socket/session handle that can be safely closed.
- Host/container UDP listeners do not provide a reliable per-character connection to kill. A network-level kick would require a verified character-to-client-IP mapping first.

Implemented chat helper:

```text
&kick <playername>
```

`&kick` is intentionally a resolver/planner right now. It resolves the player, reports whether they are online, captures their current map route/controller ids, and returns the candidate kick paths. It does not mutate Postgres, publish guessed GM payloads, restart map services, or firewall an IP.

The chat spam auto-protector uses the same limitation. It detects repeated-message spam and calls `DUNE_CHAT_SPAM_KICK_COMMAND`, which defaults to `scripts/spam-kick-player.sh`. That hook fails closed with `DUNE_SPAM_KICK_BACKEND=blocked` until the native kick path is proven. With the default config, spam violations are logged and announced as blocked instead of silently doing unsafe state writes.

Candidate paths:

- Native GM/session command: investigate `KickLobbyMember`, `RemoveSessionMember`, or `BattlEyeMegaKick` only after the `PrintPos`/`PrintAllowedCommands` payload path is proven.
- Map-service restart: available as a blunt operational tool, but not targeted because it disconnects everyone on that map.
- DB online-state write: rejected because it is not the live session and can corrupt/desync state.
- Network block: blocked until we can reliably map a character to a client IP/session handle.

To enable real execution later:

1. Capture or reconstruct the exact `ServerCommand`/`SendDuneServerCommand` message envelope.
2. Test with `PrintPos` only.
3. Confirm the response path on `response.<server_id>` or the RPC reply queue.
4. Use `PrintAllowedCommands` through the verified path to confirm whether any native kick/session command is actually exposed.
5. Flip `GM_COMMAND_PAYLOAD_VERIFIED` in the panel implementation and keep `DUNE_ADMIN_GM_COMMANDS_ENABLED=true` as a second gate.
