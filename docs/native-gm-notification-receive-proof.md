# Native GM Notification Receive Proof

Confidence: high for the static callback chain. Confidence: moderate for the
exact inbound RabbitMQ wrapper shape because the deserializer before the
callbacks is still not fully resolved.

This page documents the receive-side native notification path that runs before
the ServiceBroadcast payload handler. It explains why publishing plausible
inner JSON bodies has not yet reached `Now running ServerCommand`: the native
server-command handler receives a decoded
`Dreamworld::FNotificationsSystemMessage`-style object, not a bare
ServiceBroadcast JSON object.

## Source Artifacts

- Ghidra script:
  `scripts/research/DumpNativeGmRmqDeserializer.java`
- Latest local output:
  `/tmp/ghidra-work/native-gm-rmq-deserializer.txt`
- Ghidra script:
  `scripts/research/DumpNativeGmReceiveCallbacks.java`
- Latest local output:
  `/tmp/ghidra-work/native-gm-receive-callbacks.txt`
- Ghidra script:
  `scripts/research/DumpFNotificationsCommandAcceptance.java`
- Latest local output:
  `/tmp/ghidra-work/fnotifications-command-acceptance.txt`
- Ghidra script:
  `scripts/research/DumpFNotificationsAdjacentHelpers.java`
- Latest local output:
  `/tmp/ghidra-work/fnotifications-adjacent-helpers.txt`
- Ghidra script:
  `scripts/research/DumpRmqRunnableVtables.java`
- Latest local output:
  `/tmp/ghidra-work/rmq-runnable-vtables.txt`
- Run commands:

```bash
scripts/research/run-ghidra-headless.sh --script DumpNativeGmRmqDeserializer.java
scripts/research/run-ghidra-headless.sh --script DumpNativeGmReceiveCallbacks.java
scripts/research/run-ghidra-headless.sh --script DumpFNotificationsCommandAcceptance.java
scripts/research/run-ghidra-headless.sh --script DumpFNotificationsAdjacentHelpers.java
scripts/research/run-ghidra-headless.sh --script DumpRmqRunnableVtables.java
```

## Positive Static Result

The receive path is real and reaches the server-command notification handler:

```text
NotificationSystemListenQueue callback
  -> FUN_09f8cf00
  -> FUN_09f6ecb0
  -> registered FNotificationsSystemMessage delegate
  -> FUN_09f3ff50 or FUN_09f3ff60
  -> FUN_09f3ff90
  -> FUN_09ee73c0
  -> FUN_09ee7970
  -> FUN_09eb7e60
  -> FUN_09691b80 after auth/content validation
```

Confidence: high for the observed function chain through `FUN_09ee73c0`.
Confidence: moderate for the exact role of `FUN_09f6ecb0`; the decompile looks
like delegate/container dispatch, not the JSON deserializer itself.

## Listen Queue Callbacks

`FUN_0a05c5b0` and `FUN_0a05d070` are
`NotificationSystemListenQueue` callbacks. Both call `FUN_09f8cf00(*param_1)`
after successful receive-side checks. Confidence: high.

Evidence:

```text
FUN_0a05c5b0 -> FUN_09f8cf00(*param_1)
FUN_0a05d070 -> FUN_09f8cf00(*param_1)
```

The nearby pointer tables include C++ type strings for:

```text
TBaseFunctorDelegateInstance<...Dreamworld::FNotificationsSystemMessage...>
```

Interpretation: these callbacks are already operating on a decoded
`FNotificationsSystemMessage` delegate payload. They are not simply passing a
raw AMQP body string into `FUN_09ee73c0`. Confidence: high.

The same tables point at the source path:

```text
Plugins/Funcom/Dreamworld/Source/FuncomLiveServices/Private/PlayFab/PlayFabPlayerSession.cpp
```

Confidence: high.

## Callback Handoff

`FUN_09f8cf00` is a thin handoff:

```text
FUN_09f8cf00(param_1)
  -> FUN_09f6ecb0(param_1, 0, 0, 0)
```

`FUN_09f6ecb0` walks a callback/container structure keyed by global string data
and appears to dispatch the decoded notification to registered handlers.
Confidence: moderate.

The dispatch thunks are:

```text
FUN_09f3ff50(param_1) -> FUN_09f3ff90(param_1 + 0x10)
FUN_09f3ff60(param_1) -> FUN_09f3ff90(param_1 + 0x10), returns true
```

Confidence: high.

## Server-Command Dispatch Gate

`FUN_09f3ff90` filters a decoded notification string field before it calls
`FUN_09ee73c0`. It compares the field at `param_2 + 0x48/0x50` against the
global string at `DAT_16562160/DAT_16562168`; only matching messages reach the
server-command handler. Confidence: high for the offset and call, moderate for
the field name.

Observed call:

```text
FUN_09f3ff90
  checks param_2 + 0x48/0x50
  calls FUN_09ee73c0(*param_1, param_2)
```

Operational meaning: a body can be delivered to the notification queue and
still miss the GM handler if the decoded message field used at
`param_2 + 0x48/0x50` does not match the registered server-command event name.
Confidence: high.

## Server-Command Handler Gate

`FUN_09ee73c0` is the native server-command notification handler. Confidence:
high.

Observed control flow:

```text
FUN_09ee73c0(param_1, param_2)
  checks a decoded message field at param_2 + 0x78/0x80
  calls FUN_09ee7970(param_2 + 0x48, &local_3c, local_38, local_28)
  rejects if local_3c < 2
  checks sender-like field at param_2 + 0x58/0x60
  checks auth token extracted into local_38
  checks raw content extracted into local_28
  logs "Server command received. Raw Content: %s"
  calls FUN_09691b80(&local_d8, local_28_length, 0)
```

Confidence: high for the gates and log sequence. Confidence: moderate for the
exact source field names because the decompiler output does not retain type
names.

The tighter offset-level read is:

```text
FUN_09f3ff90:
  compares param_2 + 0x48/0x50 against DAT_16562160/DAT_16562168
  calls FUN_09ee73c0 only after that discriminator matches

FUN_09ee73c0:
  compares param_2 + 0x78/0x80 against subsystem fields +0x210/+0x218
  calls FUN_09ec9f00(&local_d8, param_2) when the +0x78/0x80 gate matches
  calls FUN_09ee7970(param_2 + 0x48, &version, auth, content)
  rejects version/status below 2
  compares param_2 + 0x58/0x60 against subsystem fields +0x220/+0x228
  compares extracted auth against configured token fields +0x230/+0x238 and
    +0x240/+0x248
  accepts only non-empty extracted content
```

Confidence: high for the offsets and ordering. Confidence: moderate for the
human field names. The key operational point is that `SenderId=fls` in a JSON
body is not automatically enough; the decoded field at `0x58/0x60` must be
populated by the PlayFab/FLS notification deserializer before the sender gate
can pass.

`FUN_09ee7970` calls `FUN_09eb7e60` and then allocates a result object. The
decompiler does not recover the extraction fields cleanly, but the caller shows
the extracted values:

- `local_3c`: version/status-like value; values below `2` hit the outdated
  message log.
- `local_38`: auth token string candidate.
- `local_28`: raw command content string candidate.

Confidence: moderate.

## Outbound Publisher Evidence

`FUN_09ede9a0` is not the inbound deserializer. It is still useful because it
serializes the same notification-message family before calling
`amqp_basic_publish`. Confidence: high.

Recovered behavior:

```text
FUN_09ede9a0(connection, optional_property_string, notification_message)
  converts decoded notification strings to AMQP byte spans
  maps message strings into basic_publish exchange/routing/body arguments
  maps optional decoded fields into AMQP basic properties
  maps a message enum to "Unknown", "Content", or "Close"
  calls amqp_basic_publish(...)
```

Confidence: high for outbound publish role and the `"Unknown"`, `"Content"`,
`"Close"` enum labels. Confidence: moderate for naming the individual decoded
fields until the inbound constructor/deserializer is resolved.

This explains why successful `basic_publish` calls and empty queues are not
sufficient proof. A message can be valid AMQP and still fail to construct the
decoded `FNotificationsSystemMessage` object required by `FUN_09f3ff90` and
`FUN_09ee73c0`. Confidence: high.

## Adjacent Helper Result

`DumpFNotificationsAdjacentHelpers.java` checked the helper cluster around
`FUN_09ec9f00` and the RMQ operation loop. Confidence: high.

Positive results:

```text
FUN_09ec5b60, FUN_09ec9f00, FUN_09ed72c0, FUN_09ed82d0:
  copy decoded string fields between existing message objects

FUN_09eca180, FUN_09ec8390:
  clean up decoded message/operation structures

FUN_09eca430:
  move/copy an AMQP operation task structure

FUN_09ec9730:
  builds or forwards an already-decoded notification object, then calls
  FUN_09ec9b30

FUN_09ec9b30:
  allocates or enqueues callback work for an existing message object

FUN_09ed8ed0:
  periodic outbound gate; prepares a message and calls FUN_09ede9a0

FUN_09ede1c0:
  AMQP operation state machine; case 1 calls outbound publish, other cases
  cover queue/exchange create/delete/bind/unbind-style operations
```

Confidence: high that this adjacent cluster is not the inbound RabbitMQ body
deserializer. It manipulates already-existing decoded message/operation
structures. The inbound parser still sits earlier, before the generated
`TBaseFunctorDelegateInstance<...FNotificationsSystemMessage...>` callback gets
the object consumed by `FUN_09f8cf00`. Confidence: high.

## Inbound AMQP Consumer

`DumpRmqRunnableVtables.java` found the RMQ runnable vtables used by
`FUN_09ed8710`. Confidence: high.

The consumer runnable table around `1490ca78` identifies:

```text
slot +6 -> FUN_09edbb50  consumer init/start path
slot +8 -> FUN_09edc750  inbound AMQP consume-message path
slot +9 -> FUN_09edb420  consumer task/registration path
```

The table is anchored by `FlsRmqRunnables.cpp` strings and consumer logs such as
`Failed to cancel consumer for {queue}` and `Failed to start consumer on
{queue}`. Confidence: high.

`FUN_09edc750` is the first confirmed inbound AMQP message function in this
chain. Confidence: high. Recovered flow:

```text
FUN_09edc750
  amqp_maybe_release_buffers
  amqp_consume_message
  handles heartbeat/timeout/connection-close cases
  on delivered message:
    FUN_09edd340(...)                 delivery/routing metadata
    FUN_09ee0490(..., "app_id", 8)
    FUN_09ee0490(..., "user_id", 0x10)
    FUN_09ee0490(..., "correlation_id", 0x400)
    FUN_09ee0490(..., "reply_to", 0x200)
    FUN_09edd540(...)
    FUN_09edd810(...)
    FUN_09edd980(...)
    amqp_destroy_envelope
    hashes the delivery key and finds a registered consumer entry
    builds a local decoded AMQP notification object
    FUN_09edda40(consumer_entry + 0x160, local_decoded_message)
    FUN_09edda40(global/default consumer, local_decoded_message)
```

Confidence: high for the call sequence and AMQP property names. Confidence:
moderate for the exact names of the helper outputs that do not retain symbols.

Operational consequence: the missing wrapper is now more specific than
"some JSON envelope." The native receive path constructs the decoded
`FNotificationsSystemMessage` from AMQP delivery metadata/properties and body
before the generated `FNotificationsSystemMessage` delegate runs. Therefore a
safe live probe must control AMQP properties such as `app_id`, `user_id`,
`correlation_id`, `reply_to`, AMQP type/body metadata, and the delivery/routing
key, not only JSON field aliases inside the message body. Confidence: high.

## Log String Map

These strings are directly tied to `FUN_09ee73c0` through pointer tables:

```text
1490e380 -> NotificationSystem message ignored. Outdated message version: "%d"
1490e3a0 -> NotificationSystem message handling failed. Invalid Sender ID, we only accept server commands from 'fls'.
1490e3c0 -> NotificationSystem message handling failed. Invalid Auth Token.
1490e3e0 -> NotificationSystem message handling failed. Empty message content.
1490e400 -> Server command received. Raw Content: %s
```

Confidence: high.

The receive-side parse failure string is present nearby:

```text
1490e420 -> NotificationSystem message parsing failed. Failed to deserialize.
```

The script found that table in
`FuncomLiveServicesWithPlayFab.cpp`, but did not recover a direct code reference
to it in this pass. Confidence: high for the string/table, low/moderate for the
exact parser function until another focused script resolves that call site.

## Current Wrapper Implication

The receive path expects a decoded notification message with at least these
logical fields before the inner ServiceBroadcast content can matter:

```text
registered server-command event discriminator
server-command notification type/discriminator
message version/status
sender ID equal to fls
auth token matching FuncomLiveServices.ServerCommandsAuthToken
non-empty raw content
```

Confidence: moderate/high.

The raw content is the likely place for the proven inner ServiceBroadcast body:

```json
{
  "BroadcastType": "Generic",
  "BroadcastPayload": {
    "ServerCommand": "PrintAllowedCommands"
  }
}
```

Confidence: moderate.

The missing part is the exact AMQP/body wrapper that deserializes into
`FNotificationsSystemMessage` with those fields populated. Confidence: high.

## Why Previous Payloads Failed

Previous payloads could be delivered and still produce no native GM logs because
they may have failed before `FUN_09f3ff90`, or they may have decoded with the
wrong discriminator/sender/auth/content fields. Confidence: high.

Specific failure interpretations:

- No `Server command received`: the message did not pass
  `FUN_09ee73c0` auth/content gates. Confidence: high.
- No `Invalid Sender ID`: the message likely did not reach `FUN_09ee73c0`, or
  logging level did not emit that branch. Confidence: moderate.
- No `Handling ServiceBroadcast Server command:`: even if raw content was
  present, it did not pass the inner ServiceBroadcast parser. Confidence:
  moderate/high.
- `JsonObjectStringToUStruct` failures from earlier probes prove parser
  reachability for some route/body combinations, but not the final
  `FNotificationsSystemMessage` shape. Confidence: high.

## Proof Milestones

The proof ladder is now concrete:

1. `Server command received. Raw Content: %s` proves the decoded
   `FNotificationsSystemMessage` passed discriminator, sender, auth, and
   content gates. Confidence: high.
2. `Handling ServiceBroadcast Server command:` proves the raw content parsed as
   native ServiceBroadcast. Confidence: high.
3. `Now running ServerCommand` proves the command reached
   `UDuneServerCommandSubsystem`. Confidence: high.

Until milestone 1 appears, changing the inner `ServerCommand` name is not useful
because native code has not accepted the outer notification. Confidence: high.

## Safe Next Targets

1. Resolve the function that logs or references
   `NotificationSystem message parsing failed. Failed to deserialize.` from
   the table at `1490e420`. Confidence: high value, moderate difficulty.
2. Resolve the inbound constructor/deserializer that populates decoded offsets
   `0x48/0x50`, `0x58/0x60`, and `0x78/0x80`, plus the auth/content fields
   extracted from `param_2 + 0x48`. Confidence: high value.
3. Build the next probe family around `FUN_09edc750` inputs: delivery key,
   `app_id`, `user_id`, `correlation_id`, `reply_to`, AMQP type/body metadata,
   and raw body. Confidence: high.
4. Keep live proof restricted to empty routes and `PrintAllowedCommands` until
   `Server command received` and `Handling ServiceBroadcast Server command:`
   are observed. Confidence: high.
