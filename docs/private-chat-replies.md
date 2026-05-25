# Private Chat Replies

This documents the working path for server-generated client-visible private chat replies.

## Result

Working private/pink chat rendering is confirmed. Confidence: high.

The client-visible payload requires:

- `m_ChannelType` set to `Whispers`
- `m_TimeStamp` with a capital `S`
- a normal `TextChat` courier wrapper
- delivery to the player's private queue, usually `{FLS_ID}_queue`

The payload was confirmed in-game by the operator when this message rendered in the private/whisper color:

```text
[Paul]: fieldfix 204311 timeS-whispers
```

That confirmation matters because several earlier RabbitMQ-delivered payloads were consumed by the client queue but silently ignored by the UI.

## Minimal Payload

Outer AMQP body:

```json
{
  "content": "{\"m_Id\":\"...\",\"m_ChannelType\":\"Whispers\",\"m_bUseSpoofedUserName\":true,\"m_SpoofedUserNameFrom\":{\"m_TableId\":\"\",\"m_Key\":\"\",\"m_UnlocalizedName\":\"Paul\"},\"m_FuncomIdFrom\":\"ADMIN#00001\",\"m_UserNameTo\":\"SamplePlayer\",\"m_Message\":{\"m_UnlocalizedMessage\":\"message text\",\"m_LocalizedMessage\":{\"m_TableId\":\"\",\"m_Key\":\"\",\"m_FormatArgs\":[]}},\"m_TimeStamp\":\"2026.05.21-02.43.11\",\"m_OriginLocation\":{\"X\":0.0,\"Y\":0.0,\"Z\":0.0},\"m_HasSeenMessage\":false}",
  "Type": "TextChat"
}
```

AMQP properties used by the working probes:

```text
content_type=Content
delivery_mode=1
type=text_chat
message_id=<unique id>
user_id=<announcer user>
```

`m_TimeStamp` is the critical spelling. The decompiled TextRouter C# model uses `m_TimeStamp`; the server binary also contains both `m_TimeStamp` and `m_Timestamp`, but the client-visible path accepted `m_TimeStamp`. Payloads using `m_Timestamp` were delivered to the queue and consumed, but did not render as private chat.

## Working Delivery Modes

The reliable route is a temporary direct binding to the target player's queue:

```text
exchange=chat.whispers
routing_key=<target FLS id>
queue=<target FLS id>_queue
```

This route is deterministic. It does not require the player to whisper Paul first and it does not depend on a reboot-specific channel token. The per-player queue name is derived from the player's FLS id by `scripts/dune_whisper_route.py`; for example, FLS id `6FF6498F4074E3DE` maps to queue `6FF6498F4074E3DE_queue` and routing key `6FF6498F4074E3DE`.

For direct/manual publishes, prefer `DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS` and let `scripts/announce.sh` derive the queue:

```env
DUNE_ANNOUNCE_CHAT_EXCHANGE=chat.whispers
DUNE_ANNOUNCE_CHAT_CHANNEL=Whispers
DUNE_ANNOUNCE_CHAT_USER_NAME_TO=SamplePlayer
DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS=<FLS_ID>
DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS=true
```

When `DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS` is set and routing keys are otherwise `<empty>`, `scripts/announce.sh` uses the FLS id as the routing key and binds `<FLS_ID>_queue` temporarily. This keeps operator-facing config from hard-coding queue names.

The repo's command reply path sets this up automatically when:

```env
DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=whisper
DUNE_CHAT_COMMAND_PRIVATE_REPLY_EXCHANGE=chat.whispers
DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL=Whispers
DUNE_CHAT_COMMAND_PRIVATE_REPLY_ROUTING_KEY=
```

When command replies are sent from inside `handle_command()`, `scripts/admin-chat-commands.py` infers the issuing player from the command sender and uses that player as the private target if no explicit target was passed to `run_announce()`. This keeps normal admin command replies, command errors, and auction confirmations private to the issuer. Command results should include `reply.stdout` metadata from `scripts/announce.sh`; for private replies it should report a whisper exchange. Public fallback is refused when the private target cannot be resolved.

Chat commands are PM-only. The command listener binds only whisper exchanges and Paul’s inbound whisper routing key, `ADMIN#00001`; map, proximity, party, and guild messages are intentionally ignored as command input.

The command listener retries RabbitMQ startup connection failures in-process instead of crash-looping while the broker is still accepting/authenticating clients:

```env
DUNE_CHAT_COMMAND_AMQP_RETRY_SECONDS=5
DUNE_CHAT_COMMAND_AMQP_CONNECT_ATTEMPTS=0
```

`DUNE_CHAT_COMMAND_AMQP_CONNECT_ATTEMPTS=0` means retry forever. A healthy startup eventually logs:

```json
{"ok":true,"listening":"chat.intercept","queue":"dash_admin_chat_commands","routingKey":"#"}
```

The player-presence private path uses the same confirmed route for private welcomes, first-seen messages, base-cap reminders, reconnect notices, restart warnings, starter-tool messages, stuck-position notices, and admin-only digests:

```env
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_EXCHANGE=chat.whispers
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL=Whispers
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_ROUTING_KEY=
```

Global join/leave and server-wide status notices intentionally stay on the public `announce()` path. Player-presence public messages still force `DUNE_ANNOUNCE_ENV_OVERRIDES_FILE=true` and default to one routing key, `DUNE_PLAYER_PRESENCE_ANNOUNCE_ROUTING_KEYS=<empty>`, so a join/leave notice is not delivered three times through the default shared announcement routing keys.

## Private Vs Global Matrix

Private to the issuing player or recipient:

- `&auction` previews, execution results, fuzzy-match suggestions, and `&auction yes/no` confirmations.
- `&test`, `&where`, `&disconnect`/`&kick`, `&teleport`, `&goto`, `&bring`, denied commands, unknown commands, and usage/errors.
- `&gm ...` command results and errors, including nested GM subcommands that call `run_announce()`.
- Player-presence private welcome and first-seen messages.
- Hagga arrival, first Deep Desert, every-entry Deep Desert instance notices, reconnect recovery/support, base reminders, stuck-position notices, restart private warnings, post-restart return notices, and starter-tool notices.
- Admin-only presence digests and alerts sent to currently online configured admins.

Global by design:

- Join/leave welcome and goodbye population notices.
- Public map-health, population-threshold, maintenance-cancelled, incident-mode, transfer-policy, rules-change, daily-peak, and daily-status notices.
- Vermilius Gap celebration announcements.
- Chat spam-protection action announcements when `DUNE_CHAT_SPAM_ANNOUNCE_ACTION=true`.

Fallback channels that rendered during investigation but are not private:

- `chat.proximity` with channel `Proximity`.
- `chat.guild.<id>` with channel `Guild`.

Use those only as diagnostics or deliberate non-private reply modes.

## Implementation Map

- `scripts/dune_whisper_route.py` is the shared FLS-id-to-whisper-route resolver. It derives `routing_key=<FLS_ID>` and `queue=<FLS_ID>_queue`.
- `scripts/announce.sh` is the shared publisher. It emits `m_TimeStamp`, accepts `DUNE_ANNOUNCE_CHAT_EXCHANGE`, `DUNE_ANNOUNCE_CHAT_CHANNEL`, `DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS`, `DUNE_ANNOUNCE_CHAT_TARGET_QUEUES`, and `DUNE_ANNOUNCE_CHAT_ROUTING_KEYS`, and reports the actual exchange in `transport`.
- `scripts/admin-chat-commands.py` handles chat commands. `run_announce()` infers the command sender from the `handle_command()` frame when no explicit target is provided. Command JSON replies include `reply.stdout` metadata from `scripts/announce.sh` where practical.
- `scripts/player-presence-announcer.py` handles presence automation. `private_message()` forces `chat.whispers`, channel `Whispers`, the target `{FLS_ID}_queue`, cleanup, and no dashboard wrapping.
- `Makefile` target `test-admin-chat` runs command/private-route and presence-private-route tests. `make validate` includes that target.

The command listener sets:

```env
DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS=<FLS_ID>
DUNE_ANNOUNCE_CHAT_TARGET_QUEUES=<FLS_ID>_queue
DUNE_ANNOUNCE_CHAT_ROUTING_KEYS=<FLS_ID>
DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS=true
DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES=false
```

The temporary binding is removed after publish. After cleanup, this check should return no rows:

```bash
docker exec dune_server-game-rmq-1 rabbitmqctl list_bindings source_name destination_name routing_key \
  | rg '(chat\.whispers|sh-.*chat\.whispers).*<FLS_ID>_queue|dash\.chat-command-reply'
```

## Smoke Tests

Direct publisher smoke test:

```bash
scripts/announce.sh "[Paul] private smoke $(date +%H%M%S)"
```

with these environment overrides:

```env
DUNE_ANNOUNCE_ENV_OVERRIDES_FILE=true
DUNE_ANNOUNCE_CHAT_EXCHANGE=chat.whispers
DUNE_ANNOUNCE_CHAT_CHANNEL=Whispers
DUNE_ANNOUNCE_CHAT_USER_NAME_TO=SamplePlayer
DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS=TEST_FLS_ID
DUNE_ANNOUNCE_CHAT_TARGET_QUEUES=TEST_FLS_ID_queue
DUNE_ANNOUNCE_CHAT_ROUTING_KEYS=TEST_FLS_ID
DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS=true
DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES=false
```

Command-path smoke test:

```bash
python3 scripts/admin-chat-commands.py \
  --dry-run-command '&auction PwerPck 1 456' \
  --sender-name SamplePlayer \
  --sender-fls-id TEST_FLS_ID \
  --reply
```

Expected private reply:

```text
[Paul]: no exact match for 'PwerPck'. did you mean PowerPack2 from inventory 15? reply &auction yes or &auction no
```

Expected command JSON includes a `reply.stdout` JSON string like:

```json
{"ok":true,"transport":"chat.whispers","exchange":"chat.whispers","routingKeys":[{"routingKey":"<FLS_ID>","ok":true}],"boundQueues":[{"queue":"<FLS_ID>_queue","routingKey":"<FLS_ID>"}]}
```

GM nested command smoke test:

```bash
python3 scripts/admin-chat-commands.py \
  --dry-run-command '&gm' \
  --sender-name SamplePlayer \
  --sender-fls-id TEST_FLS_ID \
  --reply
```

Expected result: a usage error plus `reply.stdout` with `transport=chat.whispers` and `exchange=chat.whispers`.

Presence private-route unit test:

```bash
make test-admin-chat
```

Expected result: command tests and player-presence private whisper routing tests pass.

## Failed Paths

These were tested and should not be reintroduced as fixes:

- `m_UserNameTo` by itself. It can render as normal visible chat, not private chat.
- `m_ChannelType=Private`. Delivered variants did not render as private chat.
- `m_ChannelType=Whisper`. Delivered variants did not render as private chat.
- `m_ChannelType=Whispers` with `m_Timestamp`. Delivered and consumed, but did not render.
- localized sender key `UI/TextChat_Channel_Title_Whispers` without the corrected timestamp field. It did not solve rendering.
- TextRouter intercept redirect without AMQP `user_id`. TextRouter hits `DemoPlayersFilter` with an `ArgumentNullException`.
- TextRouter intercept redirect with AMQP `user_id` in normal mode. TextRouter preserves the original `user_id`, then RabbitMQ rejects the republish because TextRouter is authenticated as its generated `tr.<world>.<correlation>` account.
- TextRouter fixed `--RMQCredentials guest:<password>` experiment. This fixes the broker `PRECONDITION_FAILED` republish failure, but the tested redirected messages still did not render for the operator.

## TextRouter Findings

Decompilation of `TextRouter.dll` showed:

- `chat.whispers` is a real direct exchange.
- private player queues are named `{FLS_ID}_queue`.
- private RPC queues are named `{FLS_ID}_rpcQueue`.
- intercepted messages use the AMQP header `redirect_exchange`.
- `redirect_exchange` must be an AMQP binary table value. With Pika, use `b"chat.whispers"`, not a plain string.
- allowed redirect exchanges include `chat.whispers`, `chat.proximity`, and `chat.map`.
- TextRouter's normal republish path preserves the inbound AMQP `user_id`.

The fixed-credential TextRouter experiment proved the broker failure mechanism but is not part of the working solution.

## Operational Notes

`DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=whisper` is the preferred setting now that rendering is confirmed. Confidence: high.

`proximity` and `guild` remain useful fallbacks because both rendered during earlier probes, but they are not private.

If private replies stop rendering:

1. Verify `scripts/announce.sh` still emits `m_TimeStamp`, not `m_Timestamp`.
2. Verify the channel is `Whispers`.
3. Verify the target queue is online and has one consumer:

   ```bash
   docker exec dune_server-game-rmq-1 rabbitmqctl list_queues name messages messages_ready messages_unacknowledged consumers \
     | rg '<FLS_ID>_queue'
   ```

4. Verify cleanup did not leave stale whisper bindings.
5. Send a direct `scripts/announce.sh` smoke test before debugging `&auction`.
6. For command replies, inspect `reply.stdout`; private replies should report `transport=chat.whispers` and `exchange=chat.whispers`.
7. For listener startup issues, inspect `docker compose logs admin-chat-commands`; transient `amqpConnectAttempt` lines are expected during RabbitMQ readiness, but they should eventually be followed by `listening=chat.intercept`.
