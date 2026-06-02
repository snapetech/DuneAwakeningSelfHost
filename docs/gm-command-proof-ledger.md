# GM Command Proof Ledger

Confidence: moderate. This is the non-disruptive validation path for mapped GM
commands.

## Result So Far

Bad news: command names are mapped, but the native payload route is still not
fully proven. Confidence: high.

Good news: proving can proceed without touching players by separating route
proof, isolated admin movement, isolated target mutation, and destructive lab
tests. Confidence: high.

First safe-only execution attempt on `kspld0` failed before publish because the
local admin-RMQ broker was not reachable. Confidence: high. That means no player
impact occurred, and the next non-disruptive step is bringing up or selecting an
isolated broker/route, then rerunning only the safe probe set.

Second safe-only execution attempt on `kspls0` used the empty
`CB_Story_WaterFatManor7` / `testing-waterfat` route with the default server
command subsystem settings. Confidence: high.

- Host was verified as `kspls0`.
- Online roster before and after stayed at four players:
  `Anekeestia`, `Ashlander`, `Rack`, and `Lukano`.
- None of those players were on `testing-waterfat`.
- `PrintAllowedCommands` and `PrintPos` were published through admin-RMQ using
  narrow safe envelopes, then a bounded safe payload matrix.
- The route reported `InGameOrInTransitPlayerCount:0` during the matrix run.
- Queue state stayed clean: `CB_Story_WaterFatManor7_queue` had one consumer and
  zero ready/unacknowledged messages.
- `testing-waterfat` stayed running with restart count `0`, OOM false, exit `0`.
- Logs showed no `PrintAllowedCommands`, `PrintPos`, `ServerCommand`, command
  output, parser error, crash, or fatal line.

Conclusion: admin-RMQ delivery to an empty route is safe, but command execution
is still not proven. Confidence: high. That running server command line had
`server.NotificationSystem.Enabled=false` and a blank
`ServerCommandsAuthToken`, so the negative result is expected. Confidence: high.

Third safe-only execution attempt on `kspls0` used the same empty route after
recreating only `testing-waterfat` with the server-command notification subsystem
enabled and a private auth token. Confidence: high.

- Host was verified as `kspls0`.
- The target route had `connected_players=0` before restart and stayed empty.
- Only `testing-waterfat` / `CB_Story_WaterFatManor7` partition `7` was
  recreated.
- Online roster before and after did not include anyone on `testing-waterfat`.
- `PrintAllowedCommands` and `PrintPos` were sent through the game-RMQ server
  queue and observed notification bindings using the bounded safe matrix.
- Queue state stayed clean on both game-RMQ and admin-RMQ.
- `testing-waterfat` stayed running with restart count `0`, OOM false, exit `0`.
- Logs showed the notification subsystem enabled, but no
  `PrintAllowedCommands`, `PrintPos`, `Now running ServerCommand`, command
  output, parser error, crash, or fatal line from the probes.

Conclusion: enabling the subsystem and publishing the current guessed
game-RMQ/admin-RMQ safe matrix still does not execute commands. Confidence:
high. The bad result is real: blind broker payload shapes are not enough. The
good result is also real: the proof did not disrupt live players. Confidence:
high.

Ghidra follow-up on 2026-06-02 narrowed the failure. `SendDuneServerCommand`
calls the `UDuneServerCommandSubsystem` execution thunk only from a
player-controller/cheat-manager scoped path. The suspected `FUN_12f2f980`
target is a generic Unreal class/object validity helper, not a broker command
handler. The `ServerCommand` field is extracted by the service-broadcast payload
parsers, so the next proof must derive the exact service-broadcast payload and
auth-token route instead of guessing method names on RMQ. Confidence: moderate.

Additional 2026-06-02 proof work on the empty `testing-waterfat` route tested
the auth-aware service-broadcast shapes and a full notification-envelope
candidate family containing `EventNamespace`, `OriginalId`, `OriginalTimestamp`,
`PayloadJSON`, auth token, and raw service-broadcast content. Confidence: high.

- Host was verified as `kspls0`.
- The target route stayed `ready=true`, `alive=true`, active, and
  `connected_players=0`.
- Game-RMQ and admin-RMQ publishes had zero publish errors; admin-RMQ returned
  only `director_state` responses.
- Queue state stayed clean: the game server queue had one consumer and zero
  ready/unacknowledged messages.
- `testing-waterfat` stayed running with restart count `0`, OOM false, exit `0`.
- Logs still showed no `Server command received`, `Invalid Auth Token`,
  `Empty message content`, `Handling ServiceBroadcast Server command`,
  `Now running ServerCommand`, command output, crash, or fatal line.

Conclusion: the newly tested auth-aware payloads still do not reach the native
server-command notification handler. Confidence: high. Ghidra now identifies the
outer native path as `FUN_09f3ff90 -> FUN_09ee73c0`, with
`FUN_09ee73c0` checking notification prefilter strings, extracting auth/content
through `FUN_09ee7970`, then calling the raw-content parser only after auth and
content pass. Confidence: moderate. The next useful proof is reconstructing the
native notification struct or capturing a real FLS notification message, not
running mutating GM commands.

Additional static work with
`scripts/research/DumpNativeGmNotificationLayout.java` narrowed the required
native envelope further. `FUN_09ee73c0` has an explicit sender gate and logs
`NotificationSystem message handling failed. Invalid Sender ID, we only accept
server commands from 'fls'.` The recovered JSON serializer emits
`EventNamespace`, required `Name`, `OriginalId`, `OriginalTimestamp`, `Payload`,
and `PayloadJSON`. Confidence: moderate/high. The payload matrix now includes
sender-aware safe candidates with `Name`, `Version`, and sender aliases set to
`fls`; they still need empty-route proof before any broader command testing.

The same Ghidra pass also pulled in the parser-side event surface:
`FUN_137af590` serializes `EntityId`, `EntityType`, `EventData`, `EventName`,
`EventNamespace`, and `EventSettings`, while `FUN_121360e0` registers
`EngineServiceNotification`. Confidence: moderate that the next safe payload
family should wrap the server-command event as an `EngineServiceNotification`
instead of publishing bare `EventContents` JSON. The payload matrix now includes
`engine-service-fls-notifications-serverrequesteventnotifications-*` candidates
with `EventName=ServerRequestEventNotifications`, `EventNamespace=notifications`,
`Version=1`, and sender settings set to `fls`. These are still unproven and
must be tested only with `PrintAllowedCommands`/`PrintPos` on an empty route.

`FUN_13db62f0` is a separate versioned parameter JSON parser. It requires
`Version` and a `Parameters` array whose entries have `Name`, `Type`, and
`Value`; supported versions are `0..3`. Confidence: moderate that this is useful
for typed command parameters after delivery is solved, but low that it is the
missing native notification wrapper.

Follow-up live proof on `kspls0` used only the empty `WaterFat_0` route:
partition `7`, map `CB_Story_WaterFatManor`, server id
`s0JD4zOYTPyN3oV0wU8f3A`, game queue
`queue.server.s0JD4zOYTPyN3oV0wU8f3A`, and admin queue
`CB_Story_WaterFatManor7_queue`. Confidence: high.

- Host was verified as `kspls0`.
- `testing-waterfat` was alive, active, `connected_players=0`, restart count
  `0`, OOM false, and both target queues were at zero ready/unacked messages.
- Eight `engine-service-fls-notifications-serverrequesteventnotifications-*`
  `PrintAllowedCommands` publishes were sent through the mapped game queue and
  notification/heartbeat bindings.
- Sixteen `notification-native-fls-*serverrequesteventnotifications*`
  `PrintAllowedCommands` publishes were sent through the same mapped game queue
  and notification/heartbeat bindings.
- All publishes completed without RMQ errors; no player route was occupied.
- Logs showed no `Server command received`, `Now running ServerCommand`,
  `PrintAllowedCommands`, `Invalid Sender`, `Invalid Auth Token`,
  `Empty message content`, `Failed to deserialize`, `JsonObjectStringToUStruct`,
  `Handling ServiceBroadcast`, crash, fatal, or restart.
- Target queue state remained clean and `WaterFat_0` stayed
  `connected_players=0`.

Conclusion: the new `engine-service` and sender-aware native JSON candidates
are also not working payloads. Confidence: high. They appear to be consumed or
ignored before the `FUN_09f3ff90 -> FUN_09ee73c0` native server-command handler
logs anything. Confidence: moderate/high that the remaining blocker is the
generated RMQ notification deserializer/event-dispatch contract, not another
top-level alias for `SenderId`, `EventNamespace`, or `ServerCommand`.

The latest static pass expanded
`scripts/research/DumpNativeGmNotificationLayout.java` with
`NotificationSystemListenQueue`, `JsonObjectStringToUStruct`, and
`Deserialized message has unknown Server Command` strings. These strings are
present in the binary, but the focused string pass did not recover simple direct
code xrefs for the JSON-to-struct failure or unknown-command log. Confidence:
moderate that these are table/generated serializer surfaces.

A follow-up static pass with
`scripts/research/DumpNativeGmRmqDeserializer.java` corrected one prior
assumption: `FUN_09ede9a0` is an outbound AMQP publisher, not the inbound
notification deserializer. It calls `amqp_basic_publish` at `09edef63`.
Confidence: high. `FUN_09ed8710` is still the RMQ listen loop; it creates the
connection with `FUN_09ed8920`, then calls consumer vtable slots `+0x40` and
`+0x48` after the periodic `FUN_09ed8ed0` outbound gate. Confidence: high.

The useful receive-side targets are now the listener callback functions found
through the `NotificationSystemListenQueue` strings:

- `FUN_0a05c5b0` and `FUN_0a05d070` call `FUN_09f8cf00(*param_1)` when a
  received message object is present. Confidence: high.
- `FUN_09fa5a70` handles notification-system initialization/queue state and
  allocates callback work items, but it is not enough by itself to identify the
  payload shape. Confidence: moderate.
- `NotificationSystemHandleServerMessages` appears as a C++ type/function-name
  string for `Dreamworld::FFuncomLiveServicesWithPlayFab`, not as a simple
  direct code xref. Confidence: high.

Conclusion: the latest static result is bad news for the earlier
`FUN_09ed8710 -> FUN_09ed8ed0 -> FUN_09ede9a0` inbound hypothesis. It is good
news for narrowing the next work: reverse the consumer vtable callbacks and the
message object consumed by `FUN_09f8cf00` before doing more live
`PrintAllowedCommands` payload probes. Confidence: high.

A follow-up callback pass added
`scripts/research/DumpNativeGmReceiveCallbacks.java` and decompiled the
receive-side delegates. Confidence: high.

- The callback tables are generated
  `TBaseFunctorDelegateInstance<...FNotificationsSystemMessage...>` tables
  around `1492b4c8`, `1492b598`, and `1492b688`. Confidence: high.
- `FUN_0a05bfb0` identifies the owner path as
  `Dreamworld::FPlayFabPlayerSession::NotificationSystemInitialize(...)`.
  Confidence: high.
- `FUN_0a05c580` / `FUN_0a05c590` thunk into `FUN_0a05c5b0`; `FUN_0a05d040`
  / `FUN_0a05d050` thunk into `FUN_0a05d070`. Confidence: high.
- `FUN_0a05c5b0` and `FUN_0a05d070` both validate/refcount the received
  notification message object and then call `FUN_09f8cf00(*param_1)` when the
  object pointer is present. Confidence: high.
- `FUN_09f8cf00` is a thin wrapper over `FUN_09f6ecb0(param_1, 0, 0, 0)`.
  Confidence: high.
- `FUN_09f3ff90` filters decoded notification sender/type fields at offsets
  `0x48` and `0x50`, then calls `FUN_09ee73c0`.
- `FUN_09ee73c0` reads additional decoded notification fields at offsets
  `0x58`, `0x60`, `0x78`, and `0x80`, extracts auth/content through
  `FUN_09ee7970(param_2 + 0x48, ...)`, and only logs `Server command received`
  when content is non-empty. Confidence: high.

Conclusion: native delivery is not a raw JSON body published to the queue. The
server command path expects an already decoded `FNotificationsSystemMessage`
object produced by the PlayFab/FLS notification system. The next useful static
target is the deserializer that constructs that object and populates offsets
`0x48..0x80`, not more live RMQ payload aliases. Confidence: high.

A follow-up static layout pass added
`scripts/research/DumpFNotificationsSystemMessageLayout.java` and wrote
`/tmp/ghidra-work/fnotifications-system-message-layout.txt`. Confidence: high.

- `FUN_09ec9f00` is a decoded-message copy/failure helper, not the missing
  inbound JSON parser. It copies string-like fields from source to destination:
  `0x48/0x50`, `0x58/0x60`, `0x68/0x70`, `0x78/0x80`, plus trailing state at
  `0x88..0x94`. Confidence: high.
- `FUN_09f3ff90` still gates on the decoded field at `0x48/0x50` before
  handing the message to `FUN_09ee73c0`. Confidence: high.
- `FUN_09ee73c0` still gates on `0x78/0x80`, extracts auth/content from
  `param_2 + 0x48`, then checks sender through `0x58/0x60`. Confidence: high.
- The outbound publisher `FUN_09ede9a0` serializes the same decoded-message
  fields into AMQP properties before calling `amqp_basic_publish`, which
  reinforces the field layout but does not solve inbound delivery. Confidence:
  high.
- A bounded scan found 220 functions in the `0x09e00000..0x0a100000`
  notification/serializer band touching these offsets; many are generic
  generated serialization/copy helpers. The highest-value next static target is
  the generated data-function/UStruct bridge around `FUN_09e05650` and
  `FUN_09e067f0`, which map property/data-function metadata to object fields.
  Confidence: moderate.

A follow-up pass added
`scripts/research/DumpFNotificationsDataBridge.java` and wrote
`/tmp/ghidra-work/fnotifications-data-bridge.txt`. That result corrected the
target list: `FUN_09e05650` and `FUN_09e067f0` are generic
`UOptimusNode_DataInterface` data-function support, not the PlayFab/FLS
notification deserializer. The nearby diagnostic table at `148e60f8..148e6198`
contains Optimus messages such as missing data read/write functions, and the
registration path identifies `/Script/OptimusCore` and
`OptimusNode_DataInterface`. Confidence: high.

The remaining static target is the PlayFab/FLS notification deserialize path in
`FuncomLiveServicesWithPlayFab.cpp`, anchored by the
`NotificationSystem message parsing failed. Failed to deserialize.` string/table
around `1490e420` and by callbacks that produce the decoded
`FNotificationsSystemMessage` consumed by `FUN_09f3ff90` and `FUN_09ee73c0`.
Confidence: moderate.

The receive-side callback and handler gates are documented in
[native-gm-notification-receive-proof.md](native-gm-notification-receive-proof.md).
Confidence: high that the native server-command handler expects an already
decoded `FNotificationsSystemMessage`-style object before the inner
ServiceBroadcast body is parsed.

Positive static result: a later focused Ghidra pass reran
`scripts/research/DumpServerCommandPayload.java` and
`scripts/research/DumpNotificationServerCommandSurface.java` against the same
build and found real native server-command surfaces, not just names.
Confidence: high.

- `FUN_09ee83c0` loads `FuncomLiveServices.ServerCommandsAuthToken` into the
  notification subsystem at offset `0x240`; `FUN_09ee73c0` compares extracted
  auth content against that configured value before it accepts command content.
  Confidence: high.
- `FUN_0da5cea0` extracts the JSON field `ServerCommand`; this proves
  `{"ServerCommand":"PrintAllowedCommands"}` is a real native command payload
  field for the server-command serializer/parser family. Confidence: high.
- `FUN_0da61730` and `FUN_0da61aa0` are real handlers that log
  `Handling ServiceBroadcast Server command:` after parsing service-broadcast
  payloads. Confidence: high.
- `FUN_1385a4f0` serializes notification objects with `EventNamespace`, `Name`,
  `OriginalId`, `OriginalTimestamp`, `Payload`, and `PayloadJSON`; the useful
  candidate family should carry both object `Payload` and string `PayloadJSON`
  where possible. Confidence: moderate/high.

Follow-up Ghidra work with
`scripts/research/DumpServiceBroadcastPayloadShape.java` wrote
`/tmp/ghidra-work/service-broadcast-payload-shape.txt` and proved a narrower
positive ServiceBroadcast shape. The detailed function-chain documentation is
in [native-gm-servicebroadcast-proof.md](native-gm-servicebroadcast-proof.md).
Confidence: high.

- `FUN_0da5fd90` is the native `BroadcastType` field accessor; it calls the
  string accessor on `L"BroadcastType"`. Confidence: high.
- The only explicit `BroadcastType:` display labels found by this pass are
  `Generic` and `ServerShutdown`. `ServerBroadcastClientAuthenticated` exists
  as a string, but this pass did not prove it as a ServiceBroadcast
  `BroadcastType`. Confidence: moderate/high.
- `FUN_0da61730` is the generic ServiceBroadcast handler. It parses the payload
  through `FUN_0f1bf7b0`, dispatches through `FUN_0f1bcd20`, applies the parsed
  generic broadcast through `FUN_0f1c0a70`, then logs
  `Handling ServiceBroadcast Server command:`. Confidence: high.
- `FUN_0da61aa0` is the shutdown ServiceBroadcast handler. It calls
  `FUN_0f1bfb30` and `FUN_0d8d4e30`, then logs the same handling string.
  This proves `ServerShutdown`, but that path is not safe for live proof.
  Confidence: high.
- The shutdown payload parser references `ShutdownType`, `ShutdownTimestamp`,
  `ShutdownDuration`, `DateTimestamp`, and `LocalizedText`, plus enum labels
  `Accept`, `Cancel`, `Completed`, `Maintenance`, `Restart`, and `Update`.
  That is useful documentation, not a live-test target. Confidence: high.

The probe matrix now has a native-derived candidate family named
`native-derived-notification-*`. These bodies keep sender aliases set to `fls`,
use `Name=ServerRequestEventNotifications` or
`Name=NotificationSystemHandleServerMessages`, include `Version=1`, and carry
`AuthToken` or `ServerCommandsAuthToken` plus service-broadcast content with a
real `BroadcastPayload.ServerCommand`. Confidence: high that these are more
binary-derived than the previous broad alias matrix.

The current positive-priority bodies are the `Generic` aliases named
`native-positive-notification-generic-*`. Use an empty route only. Example
exact-body safe probe:

```bash
python3 scripts/probe-gm-payload-matrix.py \
  --route CB_Story_WaterFatManor7 \
  --queue CB_Story_WaterFatManor7_queue \
  --game-server-queue queue.server.<server-id> \
  --include-game-rmq \
  --include-game-bindings \
  --only-broker game \
  --target-kind direct \
  --command PrintAllowedCommands \
  --body native-positive-notification-generic-authtoken-object-content \
  --body native-positive-notification-generic-servercommandsauthtoken-object-content \
  --body native-positive-notification-generic-authtoken-payload-only \
  --body native-positive-notification-generic-servercommandsauthtoken-payload-only \
  --content-type native \
  --amqp-type empty
```

Conclusion: no live command execution is proven yet, but the current positive
path is now specific: test the native-positive generic notification bodies
above on the empty route and look for `Server command received`,
`Handling ServiceBroadcast Server command:`, or `Now running ServerCommand`.
Confidence: high.

Use the proof runner:

```bash
python3 scripts/prove-gm-commands.py --format markdown
```

That command only generates the ledger. It does not publish anything.

## Non-Disruptive Proof Order

The broad static command inventory is documented in
[native-gm-command-catalog.md](native-gm-command-catalog.md). This proof order
applies only after the native payload route is proven with safe commands.

1. Safe route proof:
   `PrintAllowedCommands` and `PrintPos` are the only commands allowed for
   live-route smoke tests. Run with `--execute-safe` only after selecting the
   exact route and admin/test player.

2. Empty-route subsystem proof:
   Recreate only an empty target map with
   `DUNE_SERVER_NOTIFICATION_SYSTEM_ENABLED=true` and a private
   `DUNE_SERVER_COMMANDS_AUTH_TOKEN`. Then send only `PrintAllowedCommands` and
   `PrintPos` through the game-RMQ notification/server-command path. Do not use
   occupied routes.

3. Isolated admin session:
   Movement-mode and admin travel commands must be tested on an isolated
   admin/test character on an empty lab route or private map. This covers
   `Fly`, `Ghost`, `Walk`, `TeleportToExact`, `TeleportToMap`, travel helpers,
   patrol/sandworm/personal-marker teleports, and similar commands.

4. Isolated target mutation:
   Inventory grants, basic kit grants, vehicle spawn, and player-target
   teleports require a disposable test character or disposable spawned object.
   These do not run against normal players.

5. Destructive lab only:
   `DestroyTargetVehicle`, `DestroyTotem`, `DestroyPlaceable`,
   `DestroyEntireBuilding`, and `DestroyBuildingPiece` stay blocked for live
   routes. They can only be proven against disposable lab assets with rollback
   evidence.

6. Static rejected:
   `RemoveSessionMember`, `KickLobbyMember`, and `BattlEyeMegaKick` are not
   shipped dedicated-server GM commands for this build. They are static negative
   evidence only.

## Safe Probe Command

Example safe execution against a chosen route:

```bash
python3 scripts/prove-gm-commands.py \
  --route Survival_11 \
  --target-player SamplePlayer \
  --admin-player SamplePlayer \
  --execute-safe \
  --command PrintAllowedCommands \
  --command PrintPos \
  --format json
```

The script only executes commands in the safe probe set. Every other command
remains preview-only unless a separate lab-specific harness is added.

## Proof Status Terms

- `safe-route-probe`: may be run as a live smoke test because it should only
  print/log state.
- `isolated-admin-session`: requires an isolated admin/test character and empty
  route.
- `isolated-target-mutation`: requires a disposable target character/object.
- `destructive-lab-only`: blocked outside a disposable lab with rollback.
- `console-static-first`: requires exact argument mapping before execution.
- `static-rejected`: not a working shipped dedicated-server GM command.
