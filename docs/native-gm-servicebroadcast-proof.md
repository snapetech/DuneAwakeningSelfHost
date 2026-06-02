# Native GM ServiceBroadcast Proof

Confidence: high for the static handler chain. Confidence: moderate for the
exact inbound live payload body because live command execution is still not
proven.

This page documents the current native GM command payload evidence from Ghidra.
It is intentionally separate from the operational probe ledger so the static
binary facts, inferred payload shape, and live proof status do not get mixed
together.

The receive-side notification wrapper that must deliver this inner
ServiceBroadcast body is documented separately in
[native-gm-notification-receive-proof.md](native-gm-notification-receive-proof.md).

## Source Artifacts

- Ghidra script:
  `scripts/research/DumpServiceBroadcastPayloadShape.java`
- Latest local output:
  `/tmp/ghidra-work/service-broadcast-payload-shape.txt`
- Run command:

```bash
scripts/research/run-ghidra-headless.sh --script DumpServiceBroadcastPayloadShape.java
```

The script focuses on `DuneServerCommands` ServiceBroadcast payload handling:
`BroadcastType`, `BroadcastPayload`, `ServerCommand`, the generic
ServiceBroadcast handler, and the server-shutdown handler.

## Positive Static Result

The binary has a real ServiceBroadcast path that handles `BroadcastType=Generic`
and reaches the log string `Handling ServiceBroadcast Server command:`.
Confidence: high.

This does not yet prove the exact RabbitMQ inbound body. It proves that the
inner native path exists and that `Generic` is a better next payload target than
the previously broad `ServerBroadcastClientAuthenticated` and `ServerBroadcast`
guesses. Confidence: high.

## String And Field Evidence

`FUN_0da5fd90` is the `BroadcastType` field accessor. It calls the native string
accessor with `L"BroadcastType"`. Confidence: high.

```text
FUN_0da5fd90 -> FUN_0f86ef40(..., L"BroadcastType")
```

The focused string pass found exactly these explicit `BroadcastType:` display
labels:

```text
BroadcastType: Generic,
BroadcastType: ServerShutdown,
```

`ServerBroadcastClientAuthenticated` exists as a string, but this focused pass
did not prove it as a `BroadcastType` consumed by the ServiceBroadcast command
handler. Confidence: moderate/high.

The same pass found these relevant `BroadcastPayload` parser/format strings:

```text
BroadcastPayload
BroadcastPayload: {
BroadcastPayload parsing failed. DateTimestamp field does not exist.
BroadcastPayload parsing failed. Failed to parse LocalizedText field.
BroadcastPayload parsing failed. ShutdownDuration field does not exist.
BroadcastPayload parsing failed. ShutdownTimestamp field does not exist.
BroadcastPayload parsing failed. ShutdownType field does not exist.
```

Interpretation: `BroadcastPayload` is a real payload field, but several strings
come from shutdown/localized payload parsers. For safe GM proof, the useful
field remains `BroadcastPayload.ServerCommand`, backed separately by
`FUN_0da5cea0` in the server-command payload research. Confidence: high.

## Generic Handler Chain

The generic ServiceBroadcast command handler is `FUN_0da61730`. Confidence:
high.

Static call sequence:

```text
FUN_0da61730
  obtains/validates UServiceMessageQueueSubsystem-like object
  calls FUN_0f1bf7b0(local_e8, param_2)
  calls FUN_0f1bcd20(0, local_e8)
  when parsed payload state is clean:
    calls FUN_0f1e1080(local_e8)
    calls FUN_0f1c0a70(lVar1, local_40)
    logs "Handling ServiceBroadcast Server command:"
```

Interpretation:

- `FUN_0f1bf7b0` copies/converts the incoming generic broadcast payload object
  into a local parsed payload structure. Confidence: moderate/high.
- `FUN_0f1bcd20` dispatches/copies parsed generic payload entries into the
  target structure through `FUN_0ded23f0`. Confidence: moderate.
- `FUN_0f1c0a70` is the apply step immediately before the handler log.
  Ghidra only decompiled it as a tiny allocation wrapper, so its detailed type
  is still unresolved. Confidence: low/moderate for exact semantics, high for
  its position in the chain.
- The handler logs only after the parser path succeeds. Seeing
  `Handling ServiceBroadcast Server command:` in server logs is therefore a
  strong positive signal that a probe reached the native generic handler.
  Confidence: high.

## Shutdown Handler Chain

The shutdown ServiceBroadcast command handler is `FUN_0da61aa0`. Confidence:
high.

Static call sequence:

```text
FUN_0da61aa0
  validates shutdown-capable server/world object
  calls FUN_0f1bfb30(local_70, param_2)
  calls FUN_0d8d4e30(lVar1, local_70)
  calls FUN_0f1e1080(local_70)
  logs "Handling ServiceBroadcast Server command:"
```

`FUN_0f1bfb30` copies a compact shutdown payload layout:

```text
offset +0x08 copied as a 32-bit field
offset +0x0c copied as a byte
offset +0x10 copied as an 8-byte field
offset +0x18 copied as a 32-bit field
offset +0x20 copied as an 8-byte field
offset +0x28 copied as a 32-bit field
offset +0x2c copied as a byte
```

`FUN_0d8d4e30` applies that shutdown payload to server state around offsets
`0x3f4..0x414`, sends message/update code `0x19`, and logs if the shutdown
message path is too verbose. Confidence: moderate/high.

The pass also found shutdown enum labels:

```text
ShutdownType::Accept
ShutdownType::Cancel
ShutdownType::Completed
ShutdownType::Maintenance
ShutdownType::Restart
ShutdownType::Update
```

Interpretation: `ServerShutdown` is real and documented, but it is not a safe
live proof target. Do not send `BroadcastType=ServerShutdown` on a live or
player-occupied route. Confidence: high.

## Current Candidate Payload Shape

The safest current inferred inner command body is:

```json
{
  "BroadcastType": "Generic",
  "BroadcastPayload": {
    "ServerCommand": "PrintAllowedCommands"
  }
}
```

The current native notification wrapper candidates put that body under
`Payload.Content`, include either `AuthToken` or `ServerCommandsAuthToken`, set
sender aliases to `fls`, set `Name=ServerRequestEventNotifications`, and carry
both object `Payload` and string `PayloadJSON` where possible.

The current positive-priority matrix bodies are:

```text
native-positive-notification-generic-authtoken-content
native-positive-notification-generic-authtoken-object-content
native-positive-notification-generic-authtoken-payload-only
native-positive-notification-generic-servercommandsauthtoken-content
native-positive-notification-generic-servercommandsauthtoken-object-content
native-positive-notification-generic-servercommandsauthtoken-payload-only
```

The object-content form is the best current first probe because it preserves a
structured `Content` object and also includes `PayloadJSON`. Confidence:
moderate.

## Safe Proof Command

Use only an empty route and only non-mutating commands. `PrintAllowedCommands`
is the preferred first command; `PrintPos` is acceptable after that. Confidence:
high.

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

Positive log indicators:

```text
Server command received
Handling ServiceBroadcast Server command:
Now running ServerCommand
PrintAllowedCommands
PrintPos
```

Negative-but-useful log indicators:

```text
NotificationSystem message handling failed. Invalid Auth Token.
NotificationSystem message handling failed. Empty message content.
Invalid Sender ID, we only accept server commands from 'fls'.
Deserialized ServiceBroadcast Payload has unknown Broadcast type.
ServiceBroadcast Payload has unknown Broadcast type.
```

## Current Live Proof Status

No live payload has yet produced `Server command received`,
`Handling ServiceBroadcast Server command:`, or `Now running ServerCommand`.
Confidence: high.

Previous live proof attempts were non-disruptive:

- They targeted empty routes.
- They used only `PrintAllowedCommands` and `PrintPos`.
- Queue state stayed clean.
- Restart count stayed `0`.
- No command-output log, crash, or fatal line appeared.

Interpretation: route delivery and parser reachability have been demonstrated
for some invalid shapes, but the exact decoded notification/body contract is
still incomplete. Confidence: high.

## What Is Not Proven

- A working live RabbitMQ body for native GM execution is not proven.
  Confidence: high.
- `ServerBroadcastClientAuthenticated` is not proven as the correct
  `BroadcastType` for this handler. Confidence: moderate/high.
- `ServerShutdown` is not a safe workaround for disconnect/relog behavior.
  It is a real shutdown command path. Confidence: high.
- A nice kick, soft bounce to main menu, or player relog command is still not
  present in the allow-listed GM surface found so far. Confidence: high.
- Mutating commands such as item grants remain gated until a safe command
  reaches the native handler on an empty route. Confidence: high.

## Next Reverse-Engineering Targets

1. Resolve the PlayFab/FLS `FNotificationsSystemMessage` inbound deserializer
   anchored around `NotificationSystem message parsing failed. Failed to
   deserialize.` Confidence: moderate.
2. Determine whether inbound RabbitMQ expects the notification body as
   `EngineServiceNotification`, `FNotificationsSystemMessage`, or another
   wrapper before `FUN_09f3ff90 -> FUN_09ee73c0`. Confidence: moderate.
3. Tighten `FUN_0f1c0a70` and adjacent type metadata to identify the exact
   generic broadcast apply type. Confidence: low/moderate.
4. Only after a safe command reaches the handler, test operator-visible command
   effects in the documented tier order. Confidence: high.
