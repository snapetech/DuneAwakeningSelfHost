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

## Why Execution Is Blocked

We know the command names and likely transport, but not the exact serialized message body. Publishing guessed messages into a live map `rpc` queue can be ignored, poison a consumer, or trigger unintended behavior. The panel therefore supports operator workflow and payload preview now, while hard-blocking `/api/admin/gm/execute`.

To enable real execution later:

1. Capture or reconstruct the exact `ServerCommand`/`SendDuneServerCommand` message envelope.
2. Test with `PrintPos` only.
3. Confirm the response path on `response.<server_id>` or the RPC reply queue.
4. Flip `GM_COMMAND_PAYLOAD_VERIFIED` in the panel implementation and keep `DUNE_ADMIN_GM_COMMANDS_ENABLED=true` as a second gate.
