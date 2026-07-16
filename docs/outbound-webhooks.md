# Outbound event webhooks

DASH can deliver its existing admin audit events to generic HTTPS receivers or
Discord incoming webhooks. Delivery is asynchronous, filtered per endpoint,
HMAC-SHA256 signed, retry-bounded, redirect-blocked, and recursively redacted.
The admin request that creates an event never waits for the remote receiver.

This closes the outbound event capability found in Arrakis Command Nexus and
general hosting panels without giving a receiver any inbound admin authority.

## What is emitted

`admin/admin_panel.py` already records semantic audit events for backups,
updates, service control, announcement/restart schedules, event plans, and
guarded player, inventory, economy, world, configuration, and database actions.
The dispatcher consumes that event object after it has been written to
`backups/admin-panel/audit.jsonl`.

The default filter is:

```text
*,!auth-*,!discord-adapter-read
```

Endpoint filters use shell-style matching and are evaluated as an inclusion
set followed by exclusions prefixed with `!`. Examples:

```text
backup-*,update-*,service-control
*,!auth-*,!database-query
player-*,currency-update,item-*
```

Sensitive dictionary keys matching password, token, secret, credential,
authorization, cookie, or private-key variants are replaced with
`[redacted]`. Collections, nesting, key length, and string length are bounded.

## Configure an endpoint

The live file is intentionally ignored by Git because webhook URLs and signing
keys are credentials. The management helper creates it with mode `0600`.

```bash
python3 scripts/outbound-webhooks.py init
python3 scripts/outbound-webhooks.py add operations \
  https://events.example.net/dash \
  --events 'backup-*,service-control,update-*,event-*'
python3 scripts/outbound-webhooks.py list
```

For a Discord incoming webhook:

```bash
python3 scripts/outbound-webhooks.py add discord_ops \
  'https://discord.com/api/webhooks/REPLACE/REPLACE' \
  --format discord \
  --events 'backup-*,service-control,update-*,event-*' \
  --min-interval-seconds 1
```

The helper prints the generated signing key exactly once. A generic receiver
uses it to authenticate deliveries. Discord ignores the signature headers but
still receives a valid `content` plus `embeds` payload with mentions disabled.
The endpoint URL path is never printed by `list` or runtime delivery records.

Enable delivery and recreate only the admin panel:

```dotenv
DUNE_WEBHOOKS_ENABLED=true
DUNE_WEBHOOK_CONFIG=/workspace/config/outbound-webhooks.json
DUNE_WEBHOOK_TIMEOUT_SECONDS=5
DUNE_WEBHOOK_MAX_ATTEMPTS=3
DUNE_WEBHOOK_QUEUE_SIZE=1000
DUNE_WEBHOOK_ALLOW_HTTP=false
```

```bash
./scripts/deploy-admin-panel.sh .env
```

`DUNE_WEBHOOK_ALLOW_HTTP=true` exists only for a controlled loopback/LAN test
receiver. Production receivers should use HTTPS.

## Generic delivery contract

The generic request is `POST application/json` with this envelope:

```json
{
  "event": "backup-create-full",
  "id": "delivery-uuid",
  "occurredAt": "2026-07-15T00:00:00Z",
  "payload": {
    "action": "backup-create-full",
    "ok": true,
    "ts": "2026-07-15T00:00:00Z"
  },
  "server": "host-name",
  "source": "dash-admin-panel",
  "version": 1
}
```

Headers:

```text
X-DASH-Delivery: <UUID>
X-DASH-Event: <audit action>
X-DASH-Timestamp: <Unix seconds>
X-DASH-Signature: sha256=<lowercase hex HMAC>
```

The signed byte sequence is:

```text
ASCII(X-DASH-Timestamp) + "." + exact HTTP request body bytes
```

Receiver verification must use the raw request body, reject stale timestamps,
compare the signature in constant time, and make `X-DASH-Delivery` idempotent.
A minimal Python verification core is:

```python
expected = hmac.new(
    signing_secret.encode("utf-8"),
    timestamp.encode("ascii") + b"." + raw_body,
    hashlib.sha256,
).hexdigest()
if not hmac.compare_digest(f"sha256={expected}", signature_header):
    raise PermissionError("invalid DASH signature")
```

## Retry and failure behavior

- Default maximum: three attempts per matching endpoint.
- Backoff: 1, then 2 seconds; additional configured attempts remain capped.
- Timeout: five seconds per attempt by default, hard-capped at 30 seconds.
- Queue: 1,000 events by default, hard-capped at 10,000.
- Endpoint minimum interval: zero by default, hard-capped at 60 seconds.
- Redirects are not followed, so a redirect cannot receive the secret-bearing
  URL path, signed body, or signature headers.
- Delivery failure never reverses the admin action and never retries the admin
  mutation. It only retries notification delivery.
- Queue overflow records a dropped delivery instead of blocking the request.

Delivery metadata is appended to:

```text
backups/admin-panel/webhooks/delivery.jsonl
```

It contains endpoint IDs, event names, UUIDs, status codes, attempt counts, and
failure categories. It never contains endpoint URLs, signing keys, or event
payloads.

## Status and operations

Authenticated status:

```bash
curl -sS \
  -H "Host: admin-panel:8080" \
  -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  http://127.0.0.1:18080/api/ops/webhooks | jq
```

The public `/healthz` response is liveness-only. Authenticated `/api/status`
discloses only whether webhook support is enabled and whether the configured
path exists. Endpoint origins and filters are available only on the
authenticated route. A parse, schema, or permission error fails closed with
zero active endpoints and appears as `configError`.

Disable or remove an endpoint without exposing its URL:

```bash
python3 scripts/outbound-webhooks.py disable discord_ops
python3 scripts/outbound-webhooks.py enable discord_ops
python3 scripts/outbound-webhooks.py remove discord_ops
```

Run the isolated local receiver and signature suite:

```bash
make test-outbound-webhooks
```

The suite proves retry success, exact-body signature verification, recursive
redaction, filter exclusions, Discord payload validity, redirect refusal,
credential-file permissions, URL-userinfo rejection, and signing-key length.
