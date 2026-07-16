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
