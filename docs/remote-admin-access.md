# Remote admin access and bounded file workspace

DASH's admin panel is a private control plane. Remote access should terminate
TLS and identity at a private VPN or authenticated reverse proxy while the
Compose port remains bound to loopback. Do not publish Postgres, RabbitMQ, the
Docker socket, or the raw admin-panel container port.

## Supported access patterns

1. LAN/VPN DNS plus the existing Caddy example in
   `examples/ingress/caddy-admin.example`.
2. A private overlay VPN forwarding to `127.0.0.1:DUNE_ADMIN_HOST_PORT`.
3. An authenticated tunnel/reverse proxy forwarding the original `Host` header
   to the loopback port.

The supported Internet-portal form is a stable named tunnel protected by a
deny-by-default identity application and MFA. The repository's Cloudflare
tunnel tooling manages reviewed public host routes, and the same named-tunnel
architecture may carry an explicit Admin hostname only after its Cloudflare
Access application and MFA policy exist. DASH then applies its own token/RBAC
or explicitly mapped OIDC identity, Host/Origin checks, secure sessions,
capability enforcement, mutation contracts, optional two-person approval, and
tamper-evident audit behind that edge. Do not treat possession of a tunnel URL
or an upstream identity header as DASH authorization.

Temporary anonymous quick-tunnel URLs are not the production Admin path. They
create a new public origin before an operator has proved DNS, Access policy,
allowed-host, callback, recovery, and audit behavior. Use the private
LAN/VPN/SSH tunnel for initial setup, then promote only a stable authenticated
hostname.

For every pattern:

- keep `DUNE_ADMIN_REQUIRE_TOKEN=true`;
- enable named RBAC identities for day-to-day use and retain the owner token as
  recovery only;
- add only the exact external admin hostname to `DUNE_ADMIN_ALLOWED_HOSTS`;
- preserve the original `Host` and set `X-Forwarded-Proto=https`;
- require TLS at the remote edge;
- apply an identity policy before traffic reaches DASH;
- run `scripts/check-admin-ingress.sh .env` after routing changes.

The panel's own origin/host enforcement and RBAC remain required even when an
upstream proxy supplies SSO. Provider-neutral OIDC inside DASH remains a
separate parity item.

## File-workspace boundary

DASH intentionally exposes task-specific file surfaces instead of an arbitrary
host filesystem or unrestricted browser shell:

| Surface | Browser capability | Boundary |
| --- | --- | --- |
| Config | Read/write allowlisted INI/JSON files | Parse validation and backup before replace |
| Logs | Read/filter/download bounded service output | Project services only; response limits |
| Backups | List/download/import/verify/quarantine/restore | `backups/` only; import size/type checks; restore overlay only when explicitly loaded |
| Database export | Bounded query/table export | `dune`/`public` schemas and separate write gates |
| Addons | Staged content and sandboxed UI | SHA pin, permission approval, quarantine, opaque-origin iframe |

`compose.admin-restore.yaml` is the temporary reviewed write overlay for restore
operations. Do not leave it loaded as a general-purpose writable file manager.
The normal admin container mounts the workspace read-only except for the
specific config, backup, and state paths needed by its documented features.

An unrestricted web terminal or arbitrary path browser is not parity: peers
that expose those surfaces delegate full host authority to a browser session.
DASH can meet the operational outcomes through allowlisted service control,
logs, config, backup, update, database, and runbook actions without expanding
browser compromise into unrestricted host execution.

## Verification

```bash
curl -fsS -H 'Host: admin-panel:8080' \
  http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/healthz
./scripts/check-admin-ingress.sh .env
```

Then verify that unauthenticated protected routes return `401`, an observer
cannot invoke writes, the owner recovery token still works, and public firewall
rules expose only intended game UDP and authenticated HTTPS/VPN entry points.
For an Internet hostname, also prove the edge denies an unmapped identity,
requires MFA, preserves the exact HTTPS `Host`/Origin, sends no Admin response
through the direct origin address, and leaves local owner-token recovery usable
when the identity provider or tunnel is unavailable.
