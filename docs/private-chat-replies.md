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
  "content": "{\"m_Id\":\"...\",\"m_ChannelType\":\"Whispers\",\"m_bUseSpoofedUserName\":true,\"m_SpoofedUserNameFrom\":{\"m_TableId\":\"\",\"m_Key\":\"\",\"m_UnlocalizedName\":\"Paul\"},\"m_FuncomIdFrom\":\"ADMIN#00001\",\"m_UserNameTo\":\"Lukano\",\"m_Message\":{\"m_UnlocalizedMessage\":\"message text\",\"m_LocalizedMessage\":{\"m_TableId\":\"\",\"m_Key\":\"\",\"m_FormatArgs\":[]}},\"m_TimeStamp\":\"2026.05.21-02.43.11\",\"m_OriginLocation\":{\"X\":0.0,\"Y\":0.0,\"Z\":0.0},\"m_HasSeenMessage\":false}",
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

The repo's command reply path sets this up automatically when:

```env
DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=whisper
DUNE_CHAT_COMMAND_PRIVATE_REPLY_EXCHANGE=chat.whispers
DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL=Whispers
DUNE_CHAT_COMMAND_PRIVATE_REPLY_ROUTING_KEY=
```

When command replies are sent from inside `handle_command()`, `scripts/admin-chat-commands.py` infers the issuing player from the command sender and uses that player as the private target if no explicit target was passed to `run_announce()`. This keeps normal admin command replies, command errors, and auction confirmations private to the issuer. Command results should include `reply.stdout` metadata from `scripts/announce.sh`; for private replies it should report `transport` and `exchange` as `chat.whispers`. Public moderation notices such as spam auto-kick announcements are not generated inside that command context and remain global.

The player-presence private path uses the same confirmed route for private welcomes, first-seen messages, base-cap reminders, reconnect notices, restart warnings, starter-tool messages, stuck-position notices, and admin-only digests:

```env
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_EXCHANGE=chat.whispers
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL=Whispers
DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_ROUTING_KEY=
```

Global join/leave and server-wide status notices intentionally stay on the public `announce()` path.

The command listener sets:

```env
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
DUNE_ANNOUNCE_CHAT_USER_NAME_TO=Lukano
DUNE_ANNOUNCE_CHAT_TARGET_QUEUES=6FF6498F4074E3DE_queue
DUNE_ANNOUNCE_CHAT_ROUTING_KEYS=6FF6498F4074E3DE
DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS=true
DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES=false
```

Command-path smoke test:

```bash
python3 scripts/admin-chat-commands.py \
  --dry-run-command '&auction PwerPck 1 456' \
  --sender-name Lukano \
  --sender-fls-id 6FF6498F4074E3DE \
  --reply
```

Expected private reply:

```text
[Paul]: no exact match for 'PwerPck'. did you mean PowerPack2 from inventory 15? reply &auction yes or &auction no
```

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
