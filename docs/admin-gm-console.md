# Admin GM Console Research

This records what is known about the native Dune admin/cheat path without guessing on the live server.

## AMP Public Template Research

Confidence: high. The public CubeCoders AMP Dune Awakening template does not expose GM, teleport, item grant, or kick execution payloads. It is useful for operational settings research, but it does not verify a native command route for DASH.

Current kick candidates remain unverified and are not in the shipped
`DedicatedServerGame.ini` GM allow-list:

- `RemoveSessionMember`
- `KickLobbyMember`
- opt-in `BattlEyeMegaKick`

Future research should compare RabbitMQ bindings, generated users, and server queue behavior between known-good runtime captures. That work stays separate from operational borrowing and should not block Compose, TLS, FLS environment, or config-wrapper improvements.

## Verified Surfaces

- The live survival binary contains `UDuneServerCommandSubsystem`, `UDuneServerCommandsCheatManager`, `UServiceMessageCommand`, `AdminLogin`, `PrintAllowedCommands`, `SendDuneServerCommand`, `ServerCommand`, and `ServerExecRPC` strings.
- The survival container exposes `127.0.0.1:10000`, but tested paths only returned health/404 responses. This does not look like the command route.
- Admin RabbitMQ has map RPC bindings on exchange `rpc` with routing keys such as `Survival_11`, plus per-map `grant.<server_id>` and `response.<server_id>` routes.
- Game RabbitMQ has a verified Director JSON-RPC route on exchange `rpc`, routing key `sh-6ff6498f4074e3de-ksplsz`, queue `bgdRpc`. The payload contract is `{"jsonrpc":"2.0","method":"<method>","params":[...],"id":"<non-empty id>"}` with AMQP `type=json_rpc`, `user_id=<authenticated user>`, and `reply_to=<queue name bound to exchange rpc with that same routing key>`.
- The active Survival game-RMQ server queue observed in the latest capture is `queue.server.6tKBlSXBT5+AqlbBVCn32Q`. It consumes heartbeat/notification messages, but is not bound to the game-RMQ `rpc` exchange. Tested JSON-RPC methods `PrintAllowedCommands`, `ServerCommand`, and `SendDuneServerCommand` produced no response and no visible Survival log hit on the game broker. The same envelopes sent to Director `rpc/sh-6ff6498f4074e3de-ksplsz` returned JSON-RPC `-32601 Method not found`, proving the envelope/reply path while rejecting those GM method names on Director.
- Admin-RMQ firehose tracing verified that `rpc/Survival_11` publishes are routed to and delivered from `Survival_11_queue`; the consuming user is the Survival server admin user (`sg.<world>.6tKBlSXBT5+AqlbBVCn32Q.admin`). Safe exact probes for `PrintPos` using JSON-RPC command, `ServerCommand`, `SendDuneServerCommand`, service-broadcast candidates, direct queue publishes, raw text, non-`json_rpc` AMQP types, omitted AMQP type, and omitted content type were delivered but produced no command reply and no visible Survival log hit. Confidence: high that auth, routing, and delivery are working; confidence: high that the remaining blocker is the native handler/method contract or required in-game admin/session context.
- `AdminLogin sardaukar` was tested through the same delivered admin-RMQ path as JSON-RPC method, JSON-RPC `ServerCommand`, and raw text. It produced no command reply and no visible Survival log hit. Confidence: high that broker-only admin-login guessing is not enough.
- Binary strings and local disassembly show `ADunePlayerControllerBase::AdminLogin(const FString&)`, `UDuneServerCommandsCheatManager`, `UDuneServerCommandSubsystem`, `DuneServerCommands::FServerBroadcastPayload`, and `ServerCommand` JSON serialization code. Confidence: moderate/high that at least part of the native GM path is player-controller or cheat-manager scoped, not a standalone broker method that can be called blindly from the admin queue.
- `UDuneServerCommandSubsystem` is gated by two opt-in server settings: `server.NotificationSystem.Enabled=true` and `FuncomLiveServices.ServerCommandsAuthToken=<token>`. DASH wires these as disabled-by-default Compose args:
  - `DUNE_SERVER_NOTIFICATION_SYSTEM_ENABLED`, default `false`
  - `DUNE_SERVER_COMMANDS_AUTH_TOKEN`, default blank
- With those two settings enabled on Survival, publishing to the live game-RMQ server queue through the existing `heartbeats` exchange proved delivery into the running server notification parser. The proof probe used routing keys `MHh7RJrGT3CLt9lNDmRMCQ` and `notifications`; the server consumed the messages and logged `JsonObjectStringToUStruct` failures for invalid array/object-wrapper shapes. Confidence: high that the route reaches the game-server notification parser. Confidence: low that the final native `UDuneServerCommandSubsystem` command payload is solved; `PrintAllowedCommands` and `PrintPos` still produced no `Now running ServerCommand` or command-output log.
- The active dedicated server allow-list found in `DuneSandbox/Config/DedicatedServerGame.ini` includes:
  - Console commands: `obj`, `FGL.ComponentAuditRequested`
  - GM commands: `AddItemToInventory`, `AddBasicInventoryToCharacter`, `SpawnVehicle`, teleport/travel helpers, `Fly`, `Ghost`, `Walk`, targeted destroy helpers, and `PrintPos`.
- A 2026-06-02 Ghidra pass over command strings, xrefs, and decompiled
  command-format functions is recorded in
  [gm-command-ghidra-surface.md](gm-command-ghidra-surface.md). It found no
  shipped allow-listed nice kick/return-to-menu GM command. Confidence: high.

## Current Panel Behavior

The live Admin Actions pane does **not** expose a Native GM / Cheat Console. Earlier builds showed a blocked preview UI, but that was removed because it looked actionable while the payload route was still unverified.

The research APIs and scripts can still list discovered commands, shipped cheat scripts, and candidate RabbitMQ routes for operator investigation. Execution remains blocked until the inner `UDuneServerCommandSubsystem` payload contract is proven. The safe first probe should be `PrintPos` against a known live server queue, because it should not mutate state.

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
&teleport list|locations
&teleport set <slot> [name]
&teleport replace <slot> [name]
&teleport delete|rm <slot>
&teleport <playername> <slot>
&teleport <slot>
```

- `&gm where` is the namespaced form of `&where`.
- `&gm unstuck` prepares or sends a gated `TeleportToExact` for a target player. It uses the named saved marker, defaulting to `location0`; if no marker exists it falls back to the admin's current location.
- `&where` reports current known state and location.
- `&teleport` moves an offline target to the admin's current position only when offline teleport execution is explicitly enabled. The shipped `dune.admin_move_offline_player_to_partition(...)` helper updates the pawn row, which is the row consumed by the verified network-disconnect/rejoin test.
- `&teleport set <slot> [name]` saves the issuing admin's current location as a shared numbered slot under `backups/admin-panel/teleport-slots.json`, but refuses to overwrite an occupied slot. Use `&teleport replace <slot> [name]` to overwrite intentionally.
- `&teleport list` shows shared slots in numeric order, and `&teleport delete <slot>` removes one.
- `&teleport <playername> <slot>` moves an offline target to a saved shared slot through `dune.admin_move_offline_player_to_partition(...)`. Online targets are still refused.
- `&teleport <slot>` prepares or sends a gated native `TeleportToExact` for the issuing admin to go to that slot. It remains a preview until the native GM execution gates are enabled.
- Recommended shared city setup is manual: stand in Arrakeen and run `&teleport set 0 arrakeen`; stand in Harko Village and run `&teleport set 1 harko`.
- Direct online database movement is not a live teleport path. A same-partition test moved the test player's controller, player-state, and pawn actor rows together by `+750` X; the live Survival server later saved the old in-memory position back to the database.
- Network-disconnect teleport is now the preferred online-adjacent fallback while native GM teleport remains unverified. The path is: force a real `UNetConnection` timeout, wait until Survival marks the player `Offline`, call `dune.admin_move_offline_player_to_partition(...)`, then let the client reconnect. See [soft-disconnect-teleport.md](soft-disconnect-teleport.md).

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
- `&gm xp` resolves the player and specialization track, then returns the admin-panel mutation request body for `POST /api/admin/xp`. It does not write from chat; execute through Admin Actions so the mutation gate and audit trail stay in force.
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

We know the command names and likely transport, but not the exact serialized message body. Publishing guessed messages into a live map `rpc` queue can be ignored, poison a consumer, or trigger unintended behavior. The panel therefore does not expose this as a live control, and `/api/admin/gm/execute` remains hard-blocked.

## Probe Tool

Use `scripts/gm-command-catalog.py` to list the current native command map, wiring status, syntax, and chat/admin wrapper:

```bash
./scripts/gm-command-catalog.py --format markdown
./scripts/gm-command-catalog.py --tier movement --format names
make gm-catalog
```

The chat bridge also exposes a short operational summary through `&gm catalog`. Confidence is moderate: the command names come from the live server allow-list and binary/string research, but live execution is still preview-only until the native RabbitMQ payload contract is proven.

Use `scripts/prove-gm-commands.py` to build the non-disruptive proof ledger and
execute only the harmless route probes:

```bash
./scripts/prove-gm-commands.py --format markdown
./scripts/prove-gm-commands.py --execute-safe --command PrintAllowedCommands --command PrintPos
```

The proof runner refuses to execute mutating/destructive commands by default.
See [gm-command-proof-ledger.md](gm-command-proof-ledger.md).

Use `scripts/probe-gm-command.py` to test harmless native command envelopes without wiring unverified execution into the dashboard:

```bash
./scripts/probe-gm-command.py --command PrintPos --target-player SamplePlayer --route Survival_11
docker compose logs --since=30s survival | rg "PrintPos|ServerCommand|ServerExec|DuneServer|Admin|Command"
```

The probe refuses to publish commands outside `PrintPos` and `PrintAllowedCommands` unless `--allow-unsafe` is provided. Use `--preview` first for anything else.

The safe live probe target is:

```bash
GM_COMMAND=PrintAllowedCommands GM_ROUTE=Survival_11 GM_TARGET_PLAYER=SamplePlayer make gm-probe-safe
```

If this returns no native response and the map logs show no command hit, the command is still mapped but not live-proven for the current payload envelope.

Preview the currently implemented envelope set without publishing:

```bash
./scripts/probe-gm-command.py --preview --command PrintPos --target-player SamplePlayer --route Survival_11
GM_COMMAND=PrintAllowedCommands GM_ROUTE=Survival_11 GM_TARGET_PLAYER=SamplePlayer make gm-probe-preview
```

If AMQP is unavailable, the probe can also publish through RabbitMQ's management API:

```bash
DUNE_GM_COMMAND_RMQ_URL=http://127.0.0.1:15672 \
DUNE_GM_COMMAND_RMQ_USER=guest \
DUNE_GM_COMMAND_RMQ_PASSWORD=guest \
./scripts/probe-gm-command.py --transport management --command PrintPos --target-player SamplePlayer --route Survival_11
```

Current probe result: admin RabbitMQ routing for `Survival_11` is present (`rpc -> Survival_11_queue`, `grant.Survival_11`, `response.Survival_11`, `validation.Survival_11`, and `settingsUpdateQueue_Survival_11`). RabbitMQ firehose tracing proved exact `rpc/Survival_11` test messages are delivered to `Survival_11_queue` and consumed by the Survival server connection. Safe `PrintPos` publishes over current JSON-RPC, server-command, service-broadcast, direct-queue, raw-text, non-`json_rpc`, and omitted-property candidates returned no command response and produced no Survival log hit. `AdminLogin sardaukar` over the same path also produced no response/log hit. The game-RMQ Director JSON-RPC envelope is verified: non-null `id` is required for replies, and the temporary reply queue must be bound to the `rpc` exchange. Treat transport, auth, route discovery, and delivery as working; the native server command method contract or required in-game admin/player-controller context remains unverified.

Current transport note: `rabbitmqctl` and AMQP publishing both work against the local brokers in the current runtime. The failure is not basic broker reachability; it is the unverified native server-command RPC method contract.

Implemented `PrintPos` candidate envelopes:

- JSON-RPC notify with params array.
- JSON-RPC `SendDuneServerCommand` and `ServerExec` array variants.
- JSON-RPC `ServiceBroadcast` variants with raw string, `ServerCommand`, `Command`, and nested `Payload` objects.
- `{"Command":"ServerCommand","CommandText":"PrintPos"}` service-message style.
- `SendDuneServerCommand`, `ServerExec`, and `ServerExecRPC` object variants.
- `{"ServerCommand":"PrintPos"}`, `{"DuneServerCommand":"PrintPos"}`, and `{"ServiceBroadcast":{"ServerCommand":"PrintPos"}}` object variants.
- Raw task-style array/object variants.
- Positional RPC argument variants inferred from `TRmqRpcCallProxy<TArray<FString>, FString>` and `TRmqRpcCallProxy<TArray<FString>, FString, FString>` binary symbols.
- Plain text `PrintPos` and `ServerExec <target> PrintPos` variants.

Additional negative probes:

- Exact `AdminLogin sardaukar` as a JSON-RPC method, JSON-RPC `ServerCommand`, and raw string.
- Exact `PrintPos` object/service-message variants with AMQP `type` omitted.
- Exact `PrintPos` object/service-message variants with content type omitted.
- Exact `PrintPos` object/service-message variants with non-`json_rpc` style properties.

Binary follow-up:

- `ServerCommand` is a real string field in nearby `DuneServerCommands` serialization code, so payloads containing `{"ServerCommand":"PrintPos"}` were worth testing. Those tests were delivered and still failed.
- `AdminLogin` has an `ADunePlayerControllerBase::AdminLogin(const FString&)` symbol trail, and server commands have a `UDuneServerCommandsCheatManager` trail. The next useful capture is from a real in-game admin action or client-side admin login, not more blind admin-queue shape guessing. Confidence: moderate/high.

`scripts/dune_gm_command.py` is the shared adapter for probe and chat-command code. It supports TLS AMQP and now sends the required JSON-RPC AMQP properties (`type=json_rpc`, `user_id`, and `reply_to`). Online teleport chat commands are connected to it but remain hard-gated:

```env
DUNE_ADMIN_GM_COMMANDS_ENABLED=true
DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true
DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true
```

Until all three are true, `&goto <playername>` and `&bring <playername>` only return a payload preview. The planned native command texts are:

- `&goto <playername>`: `TeleportToPlayer <playername>` targeted at the admin.
- `&bring <playername>`: `TeleportToExact <admin-x> <admin-y> <admin-z>` targeted at the online player.

The first live-test path is intentionally same-route only. Leave this guard enabled until same-partition movement is proven:

```env
DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_REQUIRE_SAME_ROUTE=true
DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_REQUIRE_ARM=true
DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_ARM_SECONDS=60
```

With these guards enabled, the admin and target must both be online and resolve to the same GM route before a teleport command can publish. Live movement also requires a short-lived, one-use arm:

```text
&armgoto <playername>
&goto <playername>

&armbring <playername>
&bring <playername>
```

## Targeted Disconnect Status

The stack now treats targeted disconnect as a gated native GM/session command. The preferred candidate is `RemoveSessionMember <playername>`, because it is less punitive than a kick. `KickLobbyMember <playername>` is the fallback. `BattlEyeMegaKick <playername>` stays opt-in only because it may behave like a harsher kick or impose client retry behavior outside the server reconnect-grace settings.

A network-disconnect teleport path is now verified separately from native GM/session commands. DB-only presence flips were a false positive: they triggered automation but did not disconnect the game client or release the live pawn. The verified test player forced a real `UNetConnection` timeout, waited for `Offline`, called `dune.admin_move_offline_player_to_partition(...)`, and reconnect loaded the moved pawn. Confidence: high for the observed test, moderate for generalized automation.

Update 2026-06-02: Ghidra confirms that `RemoveSessionMember` and
`KickLobbyMember` are real UE Online Services operations, but not proven
dedicated-server GM commands. `RemoveSessionMember` is backed by
`UE::Online::FSessionsCommon::FRemoveSessionMember`; `KickLobbyMember` is
backed by `UE::Online::FLobbiesCommon::FKickLobbyMember`. The current build
does not expose a simple `KickPlayer`, `AdminKick`, or `DisconnectPlayer`
command in `DedicatedServerGame.ini`, and previous delivered RabbitMQ probes for
the string commands were consumed or ignored. Confidence: high that the current
admin/chat labels must treat these as session/lobby operation candidates, not a
verified "soft disconnect" button.

Live validation on 2026-06-02 did not find a working native button. Admin-RMQ
and game-RMQ probes for `BattlEyeMegaKick`, `ClientReturnToMainMenu`,
`ClientReturnToMainMenuWithTextReason`, `ClientWasKicked`,
`RemoveSessionMember`, `KickLobbyMember`, `ServerStartLogOffTimer`, and
`ClientLogOff` produced no useful player disconnect and no confirming command
logs. The shipped `DedicatedServerGame.ini` allow-list also does not include
`KickPlayer`, `AdminKick`, `DisconnectPlayer`, `RemoveSessionMember`,
`KickLobbyMember`, or `BattlEyeMegaKick`. A targeted UDP `DROP` did disconnect
the target, but it produced a network-error/login-screen style timeout and
eventual reconnect, not a nice return-to-menu notice.

Direct `gdb` invocation of `ADunePlayerController` client RPC thunks is unsafe
for production. Calling `ClientReturnToMainMenu`/`ClientReturnToMainMenuWithTextReason`
against a live `BP_DunePlayerController_C` closed the target client's
`UNetConnection`, but it also destabilized and crashed the Deep Desert map
process. Treat these thunks as reverse-engineering evidence only, not an
operator control path. Confidence: high.

If a failed live test crashes a map and the browser shows the server offline,
check `dune.farm_state` for duplicate dead rows on the same public
`game_port`. On 2026-06-02, Deep Desert came back as
`dkudsd1kTTO_CszGtbcLig`, but stale dead rows for `igFkOF7rTZCsbJtVWhbaDw` and
`sKOEet45Tse+SweBaX2zGw` still advertised port `7784`. Removing only the
`alive=false` duplicate rows restored a single valid `DeepDesert_1` registration;
`scripts/fls-publication-health.py` then reported a healthy FLS publication
window.

Ghidra helper:

```bash
/opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
  -process server-bin \
  -noanalysis \
  -postScript DumpDisconnectOperationHandlers.java \
  -scriptPath scripts/research \
  -log /tmp/ghidra-work/disconnect-handlers-ghidra.log
```

Current vtable anchors from that run:

- `FKickLobbyMember` exec handler vtable: Ghidra `0x148cda28`.
- `FRemoveSessionMember` exec handler vtable: Ghidra `0x148d3c10`.
- `FKickLobbyMember` async op vtable: Ghidra `0x148cfc00`.
- `FRemoveSessionMember` async op vtable: Ghidra `0x148d7c50`.

This does not yet give an operational route. The next useful reverse-engineering
step is to trace callers that construct the `FRemoveSessionMember::Params` or
`FKickLobbyMember::Params` structs, then determine whether any server-side admin
surface can supply those params for a live player. Until then, keep
`DUNE_GM_COMMAND_PAYLOAD_VERIFIED=false` and keep `&disconnect` as preview-only.

What we verified:

- The active `DedicatedServerGame.ini` GM allow-list does not include a clear `KickPlayer`, `AdminKick`, or `DisconnectPlayer` command.
- The live server binary does contain lower-level session and disconnect strings including `KickLobbyMember`, `RemoveSessionMember`, `BattlEyeMegaKick`, and `ClientWasKicked`.
- `RemoveSessionMember` and `KickLobbyMember` are present as UE Online Services operations, not as dedicated-server GM command handlers.
- `KickPlayer` exists as a string/data-table entry, but Ghidra did not find a Dune GM handler for it and it is not in the shipped GM allow-list.
- Those strings are not enough to execute safely unless the native RabbitMQ command envelope is verified for the current build.
- The database exposes player online state, `server_id`, `player_controller_id`, pawn id, FLS id, and map location, but it does not expose a live socket/session handle that can be safely closed.
- Host/container UDP listeners do not provide a reliable per-character connection to kill. A network-level kick would require a verified character-to-client-IP mapping first.

Implemented chat helper:

```text
&disconnect <playername>
&kick <playername>
```

`&disconnect` and `&kick` resolve the player, capture the current map route, and build a native command payload. They publish only when all three gates are enabled:

```env
DUNE_ADMIN_GM_COMMANDS_ENABLED=true
DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true
DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=true
DUNE_PLAYER_DISCONNECT_COMMAND=RemoveSessionMember
DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE=false
```

With the default gates, the command returns a preview and does not mutate Postgres, restart map services, firewall an IP, or publish a guessed payload.

The chat spam auto-protector uses the same limitation. It detects repeated-message spam and calls `DUNE_CHAT_SPAM_KICK_COMMAND`, which defaults to `scripts/spam-kick-player.sh`. That hook fails closed with `DUNE_SPAM_KICK_BACKEND=blocked` until the native kick path is proven. With the default config, spam violations are logged and announced as blocked instead of silently doing unsafe state writes.

Candidate paths:

- Network-disconnect teleport: verified for a test player on Survival; use this as the practical fallback for online-adjacent teleport while native GM teleport remains unverified. See [soft-disconnect-teleport.md](soft-disconnect-teleport.md).
- Native GM/session command: use `RemoveSessionMember` first after the `PrintPos`/`PrintAllowedCommands` payload path is proven.
- Native GM/lobby kick: use `KickLobbyMember` only if session removal does not disconnect the client.
- BattlEye kick: leave off unless deliberately testing a harsher kick path.
- Map-service restart: available as a blunt operational tool, but not targeted because it disconnects everyone on that map.
- DB online-state write: rejected because it is not the live session and can corrupt/desync state.
- Network block: blocked until we can reliably map a character to a client IP/session handle.

To enable real execution later:

1. Set `DUNE_SERVER_NOTIFICATION_SYSTEM_ENABLED=true` and `DUNE_SERVER_COMMANDS_AUTH_TOKEN` to a private token, then recreate the target game-server container.
2. Publish only safe probes through game-RMQ `heartbeats` to the current `queue.server.<server_id>` routing keys.
3. Capture or reconstruct the inner `ServerCommand` payload that causes `UDuneServerCommandSubsystem` to log `Now running ServerCommand`.
4. Test with `PrintPos` only.
5. Confirm the response path on `response.<server_id>` or the RPC reply queue.
6. Use `PrintAllowedCommands` through the verified path to confirm whether any native kick/session command is actually exposed.
7. Flip `GM_COMMAND_PAYLOAD_VERIFIED` in the panel implementation and keep `DUNE_ADMIN_GM_COMMANDS_ENABLED=true` as a second gate.
