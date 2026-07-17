# Community UI Addons

The Addons page provides community discovery, install, permission approval,
enable/disable, quarantine removal, and sandboxed rendering. The default index
is the same pinned community used by the audited Red-Blink implementation:

```text
https://raw.githubusercontent.com/Red-Blink/dune-docker-addons/main/index.json
```

Reads require the normal admin authentication. Lifecycle changes additionally
require:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ADDON_MUTATIONS_ENABLED=true
```

Install requires `INSTALL COMMUNITY ADDON`; enable, disable, and remove require
`CHANGE ADDON STATE`.

The installer:

- accepts only HTTPS downloads from the configured GitHub host allowlist;
- limits the index, manifest, archive, file count, and expanded size;
- requires the manifest SHA-256 to match the downloaded ZIP;
- rejects absolute/traversal paths and symbolic links;
- checks index, remote manifest, packaged manifest, version, id, and entry path;
- permits UI addons only;
- requires exact approval of every requested bridge permission;
- stages before promotion and keeps an older install/removal in recovery;
- installs disabled.

Installed state and files live under:

```text
backups/admin-panel/addons/
```

Enabled content is served from a bounded extension allowlist with `nosniff`, a
restrictive Content Security Policy, and an opaque-origin `sandbox=allow-scripts`
iframe. It cannot inherit the admin token, navigate the parent, submit forms,
open popups, or access a server-side shell. Static files for enabled addons do
not require the admin token so a sandboxed iframe can load them; they contain
only the downloaded public package. All data bridge calls pass through the
authenticated parent, bind the message source to the exact iframe/addon id,
and re-check installed, enabled, lifecycle, requested, and approved permission
state server-side.

The live bridge supports the community `leadership.players.list`,
`ops.health.*`, `ops.activity.summary`, resource/combat/economy summary, and
Prometheus status reads. `database.execute` uses the same one-statement parser,
timeouts, row bounds, redaction, read-only transaction enforcement, write gate,
and pre-write backup as the Infrastructure SQL console. Unsupported actions
are refused.

The implementation adapts Red-Blink's MIT addon lifecycle contract. Attribution
is recorded in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

The signed Creator/Modding canary exercises the real installer, enable,
permission, content-resolution, remove, and recovery functions using a bounded
in-memory index/manifest/ZIP. The normal network fetcher remains the default;
the injected fixture fetcher exists only to produce a deterministic no-network
proof. See [`creator-modding-canary.md`](creator-modding-canary.md).
