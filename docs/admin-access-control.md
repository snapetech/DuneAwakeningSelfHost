# Multi-User Admin Access Control

DASH supports multiple named admin identities with hashed bearer tokens and
route-level capabilities. The original `DUNE_ADMIN_TOKEN` remains a full owner
recovery credential, so enabling RBAC does not lock out an existing operator.

Confidence is **high** for token hashing, fail-closed config validation,
capability enforcement, throttling, owner-token compatibility, and federated
sessions resolving through the current local identity. OIDC and Discord OAuth
setup is documented in [`federated-auth.md`](federated-auth.md).
High-impact routes can additionally require a distinct second operator through
[`change-approvals.md`](change-approvals.md).

## Enable RBAC

Initialize the ignored, host-local identity file:

```bash
./scripts/admin-access.py init
chmod 600 config/admin-access.json
```

Set and deploy:

```dotenv
DUNE_ADMIN_REQUIRE_TOKEN=true
DUNE_ADMIN_RBAC_ENABLED=true
DUNE_ADMIN_ACCESS_FILE=/workspace/config/admin-access.json
```

The file is mounted through the existing writable `config/` bind mount. It
stores only SHA-256 digests of high-entropy tokens, never their plaintext.

## Roles and capabilities

| Role | Capabilities |
| --- | --- |
| `observer` | `read` |
| `operator` | `read`, `operations.write` |
| `moderator` | operator capabilities plus `players.write`, `community.write` |
| `administrator` | all named read/write capabilities |
| `owner` | `*` |

Named write capabilities are `operations.write`, `players.write`,
`economy.write`, `world.write`, `configuration.write`,
`infrastructure.write`, and `community.write`. A user may receive additional
explicit capabilities beyond its role.

Route authorization is fail-closed:

- GET/HEAD protected APIs require `read`;
- restart, announcements, events, autoscaler, and normal operational writes
  require `operations.write`;
- raw database operations, password rotation, destructive backup operations,
  restore drills, SLO/capacity controls, desired-state seal/acknowledgement,
  and updates require `infrastructure.write`;
- settings, bootstrap, and addon lifecycle require `configuration.write`;
- currency/Solari/Exchange/vendor writes require `economy.write`;
- guild/Landsraad/faction/marker/landclaim/world writes require `world.write`;
- player, item, XP, skill, vehicle, recovery, and care-package writes require
  `players.write`; and
- preview/inspect endpoints remain `read` even when they use POST bodies.

Unknown POST routes default to `infrastructure.write` rather than inheriting a
weaker permission.

When four-eyes control is enabled, both requester and approver are checked
against the governed route's normal capability. The requester cannot approve
their own request, and approval does not elevate either identity or replace the
route's feature gate, confirmation, backup, or runtime safety checks.

## Manage identities

Create a token:

```bash
./scripts/admin-access.py add night-ops --role operator \
  --display-name 'Night Operations'
```

The plaintext token is printed exactly once. Give it to the named operator
through an appropriate secret channel. The JSON file contains only its digest.
The browser accepts the token in the same token field as the owner credential;
API clients may use `X-Admin-Token` or `Authorization: Bearer`.

Other lifecycle commands:

```bash
./scripts/admin-access.py list
./scripts/admin-access.py disable night-ops
./scripts/admin-access.py enable night-ops
./scripts/admin-access.py rotate night-ops
./scripts/admin-access.py remove night-ops
```

Disable takes effect on the next request because the file is loaded during
authentication. Rotation invalidates the old token immediately.

## Inspect the current identity

```bash
curl -H "X-Admin-Token: $TOKEN" \
  -H 'Host: admin-panel:8080' \
  http://127.0.0.1:18080/api/auth/me
```

The response returns id, display name, role, and capabilities. It never returns
a token or digest. Authorization failures are written to the admin audit stream
with identity, required capability, and path; invalid-token responses do not
disclose whether an identity or digest exists. With the default mutation flight
recorder, sanitized events are independently HMAC-sealed and every non-read
POST requires a verified identity/capability/path/body-digest-bound admission
before dispatch. See [`audit-ledger.md`](audit-ledger.md).

Governed high-impact writes add a second admission layer: the same identity
must request and review a short-lived signed blast-radius contract for the
exact body, then return it in `X-DASH-Change-Contract`. The contract cannot
elevate capability and fails on operator, route, body, capability, policy,
expiry, or process-generation drift. See
[`change-contracts.md`](change-contracts.md).

## Recovery

If the identity file is missing or invalid, named-token authentication fails
closed. Use the unchanged `DUNE_ADMIN_TOKEN` owner recovery credential, repair
or restore `config/admin-access.json`, then validate it:

```bash
./scripts/admin-access.py list
python3 scripts/test-admin-access-control.py
```

To disable RBAC while retaining owner-token protection, set
`DUNE_ADMIN_RBAC_ENABLED=false` and redeploy the admin panel. Do not disable
`DUNE_ADMIN_REQUIRE_TOKEN` on a network-accessible panel.
