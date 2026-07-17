# Federated Public Server Directory

DASH can publish a short-lived, Ed25519-signed public server descriptor and
build a player-facing directory from any reviewed set of descriptor URLs. The
result provides the public discovery outcome without giving one vendor a
registration secret, server identity, heartbeat stream, or permanent removal
credential.

The feature is opt-in. A private or LAN-only server remains absent by default.

## Outcome

An enabled server publishes `directory-entry.json` beside its existing static
status page. It contains only:

- public server name and description;
- coarse region;
- public site and optional canonical Discord invite;
- current player count and configured capacity;
- coarse online/warming/on-demand/offline map totals;
- Sietch count and public game-image build label;
- a stable public-key-derived identity;
- generation/expiry timestamps; and
- the Ed25519 public key, payload digest, and signature.

It does **not** contain Steam/Funcom/account/controller/pawn identifiers,
coordinates, internal hostnames, IP addresses, ports, Docker state, database
rows, FLS identity, Admin Panel URLs, credentials, or the private signing key.

A directory operator keeps a bounded manifest of HTTPS descriptor URLs. The
builder resolves and rejects private/reserved targets, pins one prevalidated
public address for the TLS connection, refuses redirects, validates the
hostname certificate, limits response size/type/time, verifies identity,
signature, digest, schema, URL binding, bounds, and freshness, and emits a
static `directory.json`. One bad source cannot suppress valid listings.

The browser independently repeats Ed25519, SHA-256 identity/digest, and expiry
verification with WebCrypto before showing a card. The static directory host
therefore cannot turn an unsigned catalog row into a visible “verified”
contact. Player-relative reachability timing uses an uncredentialed HTTPS GET
to each published descriptor only after the visitor explicitly selects
**Measure my latency**; loading the directory itself sends no cross-origin
probe.

## Why Pull Federation

Red-Blink added a centralized `dunedocker.app` heartbeat directory in
`v1.3.59`. Its operator outcome is useful: status, population, region,
Sietches, Discord, and personalized latency in one browser.

DASH uses a pull model:

```text
server renderer ── writes signed, expiring descriptor ──► public static origin
                                                           ▲
                                                           │ HTTPS pull
reviewed source manifest ──► directory builder ──► signed entries catalog
                                                    │
                                                    └──► static player UI
```

There is no inbound registration API to defend, no secret in a heartbeat
payload, no delete call that can fail, and no central identity migration.
Stopping publication removes the descriptor; every directory drops it after
expiry. Multiple independent directories can list the same public identity.

## Publish One Server

The existing one-minute public-site renderer owns publication. Configure these
in the DASH `.env` or `/etc/dune-public-site.env`:

```env
DUNE_PUBLIC_DIRECTORY_ENABLED=true
DUNE_PUBLIC_DIRECTORY_ENTRY_URL=https://dune.example.com/directory-entry.json
DUNE_PUBLIC_SITE_URL=https://dune.example.com/
DUNE_PUBLIC_DIRECTORY_NAME=Example Sietch
DUNE_PUBLIC_DIRECTORY_DESCRIPTION=Adaptive maps and a friendly PvE community.
DUNE_PUBLIC_DIRECTORY_REGION=North America
DUNE_PUBLIC_DIRECTORY_CAPACITY=40
DUNE_PUBLIC_DIRECTORY_DISCORD_INVITE=https://discord.gg/example
DUNE_PUBLIC_DIRECTORY_TTL_SECONDS=180
```

Supported regions are `Africa`, `Asia`, `Europe`, `Middle East`,
`North America`, `Oceania`, and `South America`. URLs must use public DNS
hostnames and HTTPS without credentials, non-default ports, queries, or
fragments; IP literals are refused. Discord accepts
only `discord.gg/<code>` or `discord.com/invite/<code>` and publishes the
canonical `discord.gg` form.

The dedicated name and description keep public discovery independent of
`WORLD_NAME` and `DUNE_SERVER_DISPLAY_NAME`; changing the listing never changes
the in-game server browser rows. If omitted, an enabled publisher falls back to
the existing public-site text and then the game identity fields. Disabled
publication does not validate or expose those fallbacks.

Render and verify:

```bash
sudo systemctl restart render-dune-static-status.service
sudo systemctl status render-dune-static-status.service --no-pager
./public-site/scripts/validate-dune-public-site.sh /srv/dash-public-site
curl --fail --silent --show-error \
  https://dune.example.com/directory-entry.json | jq \
  '{serverId,generatedAt,expiresAt,profile,status,signature:{algorithm:.signature.algorithm,payloadSha256:.signature.payloadSha256}}'
```

The first enabled render creates
`config/secrets/public-directory-ed25519.pem` as a mode-`0600` Ed25519 private
key and retains the canonical descriptor under
`backups/public-directory/directory-entry.json`. The normal configuration and
operator-evidence backup coverage preserves the key and public state. The key
is never copied to the static directory.

If the static directory is not writable, the renderer stages the descriptor in
a private temporary directory and installs only the public JSON with the other
generated assets. Disabling publication removes the retained and public copies;
remote directories age the previous descriptor out naturally.

## Serve The Descriptor

The Caddy and Nginx examples allow the exact descriptor and directory asset
paths. `directory-entry.json` receives:

```text
Access-Control-Allow-Origin: *
Cross-Origin-Resource-Policy: cross-origin
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

The descriptor is explicitly public and contains no credential. Those headers
permit browser-relative signal timing and optional direct verification. The
Admin Panel, database, Docker socket, RabbitMQ, and generated player snapshot
remain governed by their existing exposure rules.

The directory page needs `connect-src 'self' https:` to load its catalog and,
after explicit visitor action, time independently hosted descriptors. The
cross-origin request sends no cookie, authorization header, request body, or
stable browser identifier.

For an existing SNAPE-style Caddy `dune_static_site` snippet, preview and apply
the exact reviewed allowlist/header change with:

```bash
sudo ./scripts/patch-dune-directory-caddy.py \
  --file /srv/hostapps/ingress/Caddyfile
sudo ./scripts/patch-dune-directory-caddy.py \
  --file /srv/hostapps/ingress/Caddyfile \
  --backup-dir /srv/hostapps/ingress/backups \
  --required-host kspls0 \
  --execute
```

The helper is idempotent and fail-closed: it patches only the exact reviewed
direct-site and portal snippet shapes, refuses partial/drifted copies, creates a
timestamped backup, preserves file owner/mode, and adds only the descriptor and
directory routes. The portal integration serves the complete feature under all
three existing aliases: `/dune`, `/duneawakening`, and `/da`. Always validate
the resulting Caddyfile before reload. If validation fails, restore the reported
backup and do not reload Caddy. An ingress configured with Caddy `admin off`
must restart only its standalone Caddy service/container after validation.

## Build A Directory

Create a reviewed source file:

```json
{
  "schemaVersion": "dash-public-directory-sources/v1",
  "sources": [
    {"url": "https://dune-one.example/directory-entry.json"},
    {"url": "https://dune-two.example/directory-entry.json"}
  ]
}
```

Build once:

```bash
./public-site/scripts/build-federated-directory.py \
  --sources /etc/dash-directory-sources.json \
  --output /srv/dash-public-site/directory/directory.json
```

Install the hardened one-minute builder:

```bash
sudo DUNE_PUBLIC_SITE_USER="$USER" \
  ./public-site/scripts/install-federated-directory.sh \
  --source https://dune-one.example/directory-entry.json \
  --source https://dune-two.example/directory-entry.json \
  --enable
```

The installer refuses `--enable` while the manifest still contains the shipped
`.example.test` placeholder. To replace an existing reviewed manifest
atomically, make replacement explicit:

```bash
sudo ./public-site/scripts/configure-federated-directory-sources.py \
  --output /etc/dash-directory-sources.json \
  --source https://dune-one.example/directory-entry.json \
  --source https://dune-two.example/directory-entry.json \
  --replace
sudo systemctl start build-dash-federated-directory.service
```

Edit `/etc/dash-directory.env` only to change the output path, timeout, or
bounded worker count. Source configuration never accepts credentials, queries,
fragments, local names, or IP literals.

The service is a oneshot with `NoNewPrivileges`, private temporary storage,
read-only home/system views, and a single configured writable directory. Each
source gets 1–15 seconds, responses stop at 128 KiB, the manifest accepts at
most 500 unique URLs, and concurrency is bounded to 1–32 workers.

The generated page lives at `/directory/`. It supports callsign/description
search, region and state filters, signal/activity/name ordering, live player
and map counts, public site/Discord links, truncated signing identity, and
opt-in player-relative HTTPS latency. It is keyboard accessible, mobile
responsive, and honors reduced-motion preferences.

## Trust And Failure Semantics

The public key is the server identity. `serverId` is SHA-256 of its DER-encoded
Ed25519 public key. The signature covers every other document field, including
the exact descriptor URL, public profile, live state, key, generation time,
and expiry. JSON canonicalization sorts object keys recursively and uses compact
UTF-8 encoding.

The builder refuses:

- missing/extra schema fields;
- unsupported algorithms or versions;
- invalid base64, key identity, digest, or signature;
- descriptors generated more than five minutes in the future;
- expired descriptors or lifetimes outside 60–900 seconds;
- a signed `sourceUrl` different from the reviewed manifest URL;
- HTTP, credentials, queries, fragments, non-default ports, local hostnames,
  or any IP literal;
- DNS answers containing any private/reserved address;
- redirects, certificate failures, non-JSON content, oversize bodies, and
  non-200 responses;
- out-of-bound capacity/player/map/Sietch values; and
- duplicate signed identities in one catalog.

The DNS result used for policy validation is also the IP used for the TLS
socket, while TLS still authenticates the original hostname. This closes the
validation/use gap that would otherwise permit DNS rebinding into a private
network.

Rejected sources appear only as their already-reviewed public URL plus a
bounded error. Valid entries still publish. The browser drops a catalog row if
its independent exact schema/bounds/HTTPS policy, signature, identity, digest,
or freshness check fails. Public links are created through DOM APIs after those
checks; the directory script has no HTML-string insertion sink.

## Rotation And Recovery

The stable key makes one server recognizable across name, URL, and status
changes. Do not rotate it during normal upgrades.

If the private key is lost, remove the old source URL from each directory,
generate a new key by enabling the renderer with no existing key, and add the
new signed identity after review. A copied key intentionally represents the
same public identity, so restore it only from a verified backup belonging to
that server.

If a key may be compromised:

1. disable directory publication;
2. let the current descriptor expire;
3. remove the old source from directory manifests;
4. archive evidence and replace the private key;
5. render and verify the new identity; and
6. submit the new URL/identity for review.

No central revoke credential exists. Short expiry plus reviewed source removal
is the revocation contract.

## Admin Panel And Metrics

`GET /api/ops/public-directory` reports configuration, signature/currentness,
public identity, expiry, and the exact descriptor. Infrastructure shows the
same state and links to Settings, the descriptor, and public server page.

The shared label-free metrics endpoint exports:

```text
dash_public_directory_enabled
dash_public_directory_configured
dash_public_directory_entry_valid
dash_public_directory_entry_current
dash_public_directory_entry_expires_in_seconds
```

No series labels a server, URL, region, identity, build, player, or signature.
Prometheus warns after five minutes when enabled publication is invalid or
stale.

## Validation

Run focused coverage:

```bash
make test-public-directory
make public-site-check
python3 scripts/test-admin-panel-safe-surfaces.py
```

The suite covers config/URL/Discord bounds, real OpenSSL Ed25519 signing,
secret-free output, key modes/reuse, payload/digest/signature/identity tamper,
source binding, expiry/future time, atomic publication/removal, public status
and metrics, exact source manifests, deterministic failure isolation, pinned
public-address fetches, Admin API/UI/settings/alerts, browser WebCrypto checks,
unsafe DOM sink absence, reduced motion, shell syntax, JavaScript syntax, and
systemd unit verification.
