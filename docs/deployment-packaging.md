# Deployment Packaging

Confidence: high that the supported deployment baseline is an x86_64 Linux
Docker Compose host with AVX2. DASH now ships four complementary deployment
surfaces: a checksum-enforcing release installer, an Ansible/Proxmox/cloud-init
package, a constrained Pelican/Pterodactyl controller, and a fenced
active/passive HA reference.

None of these artifacts contains or downloads Funcom server images. Obtain the
official self-host server package through the operator's entitled Steam account
and load it with `scripts/load-images.sh`.

## Deployment choices

| Path | Use it for | Starts the game automatically? | Secrets |
| --- | --- | --- | --- |
| `scripts/install-release.sh` | Immutable release install/update/rollback on an existing Linux host | No | Existing `.env` remains under `/var/lib/dash` |
| `packaging/ansible` | Repeatable Ubuntu/Debian host provisioning and optional Proxmox VM creation | No by default | `dash_env_content` must be Vault-backed |
| `packaging/cloud-init` | Secret-free initial VM/user/package bootstrap | No | Public SSH key only |
| `packaging/pelican` | Panel console controlling a separately provisioned DASH host | No; controller power is independent | File-based forced-command SSH key |
| `packaging/ha` | Fenced service VIP layered over the existing standby runbook | Never promotes or starts automatically | Root-owned authority marker and site VRRP value |

## Immutable release installer

The installer accepts only a full lowercase 40-hex Git commit and a full
SHA-256. Its default remote source is the official
`snapetech/DuneAwakeningSelfHost` GitHub archive for that commit. A local archive
is accepted for air-gapped installs. Remote arbitrary URLs, mutable branches,
tags, checksum mismatches, archive links/devices, traversal paths, multiple
roots, excessive member counts, and excessive expanded size are rejected.

Install and activate a release without touching running services:

```bash
ref=<full-40-hex-commit>
curl -fL "https://github.com/snapetech/DuneAwakeningSelfHost/archive/${ref}.tar.gz" \
  -o /tmp/dash-${ref}.tar.gz
sha256sum /tmp/dash-${ref}.tar.gz
sudo ./scripts/install-release.sh install \
  --ref "$ref" \
  --sha256 <exact-64-hex-sha256> \
  --archive "/tmp/dash-${ref}.tar.gz" \
  --activate
```

For a published version, prefer the project-built release asset over GitHub's
automatically generated source archive. Published assets contain embedded
commit/platform/exclusion metadata, an SPDX SBOM, checksums, provenance, and
GitHub attestations. See [`releases.md`](releases.md).

Default layout:

```text
/opt/dash/releases/<commit>/       immutable source release
/opt/dash/current                  atomic active-release symlink
/opt/dash/previous                 one-step rollback symlink
/var/lib/dash/.env                 private shared environment
/var/lib/dash/data                 shared runtime state
/var/lib/dash/backups              shared backups and receipts
/var/lib/dash/config-overrides     shared operator-edited INI/config files
/var/lib/dash/config-secrets       shared secret files
/var/lib/dash/config-tls           shared TLS material
```

The installer copies `.env.example` only when no shared `.env` exists. It does
not invent a token or overwrite existing configuration. Operator-mutable config
files are promoted into `config-overrides` on first installation and retained
across updates. Diff those files against the new release before a restart;
retention prevents data loss but does not automatically merge newly introduced
settings.

Inspect and roll back:

```bash
sudo ./scripts/install-release.sh status
sudo ./scripts/install-release.sh rollback \
  --confirm 'ROLL BACK DASH RELEASE'
```

Rollback atomically swaps `current` and `previous` and deliberately leaves
services untouched. A running process/container continues using its existing
code until a separately scheduled guarded restart. Validate the seven-day
Landsraad cycle before and after a map restart whenever Coriolis configuration
changed.

The installer records commit, archive SHA-256, source, and UTC installation
time in `.dash-release.json`. Reinstalling an existing release is idempotent
only when its recorded checksum matches; a conflicting directory fails closed.

## Ansible clean-host provisioning

The role under `packaging/ansible` performs these idempotent outcomes:

- assert x86_64 and AVX2;
- install host prerequisites and Docker Compose packages on Debian-family hosts;
- create a non-root DASH service account and private state root;
- install the release installer and activate the exact pinned release;
- verify the installed release manifest;
- write the Vault-provided `.env` as mode `0600` with task output suppressed;
- install a systemd unit that calls guarded warm-pool start/stop scripts;
- optionally load operator-owned images, initialize the database once, enable
  the unit, and start it through independent opt-in gates.

See `packaging/ansible/README.md` for the exact inventory, Vault, check-mode,
Proxmox, startup, and rollback workflow. Run Ansible from a trusted operator
workstation. Host-key checking stays enabled; the supplied configuration does
not silently trust new SSH hosts.

The Proxmox playbook uses the supported `community.proxmox` collection, reads a
scoped API token from environment variables, requests `cpu: host`, enables the
guest agent, creates a cloud-init device, imports `scsi0` with the dedicated
disk module, injects a required Ed25519 operator public key into the
`dash-admin` cloud-init user, defaults networking to DHCP, sets the disk boot
order, and leaves the VM powered off. The example `local:import/...` source is
Proxmox VE 9 syntax; override it with a reviewed form supported by the installed
release. The playbook never downloads or force-replaces an image. The separate
cloud-init document is intentionally secret-free and
stops after prerequisite bootstrap so tokens do not enter the Proxmox task log
or cloud-init history.

## Pelican/Pterodactyl packaging

The credible Pelican peer packages the full Funcom-derived multi-service stack
inside a custom Wings image. DASH does not collapse Postgres, RabbitMQ,
Gateway, Director, maps, and the admin surface into one opaque container. It
ships a thin panel controller instead:

```text
Pelican console -> pinned SSH host key -> forced DASH command -> guarded script
```

The controller receives neither the Docker socket nor an owner/admin-panel
token. Its exact allowlist exposes status, bootstrap check, backup, farm
start/stop, and named map start/stop/restart. Host-side map operations route
through `restart-target.sh`. The forced command rejects shell syntax and all
unknown arguments, checks an optional expected hostname, and writes a private
result audit log.

Panel Stop/Kill stops only the controller client, not the live world. This
prevents a Pelican/Wings restart from unexpectedly stopping Dune. See
`packaging/pelican/README.md` for account permissions, `authorized_keys`
restriction, host-key pinning, key rotation, import, and revocation.

## Active/passive HA

DASH already provides streaming Postgres standby, remote snapshots, file and
image synchronization, failover topology audits, WAL seal, promotion,
host/router cutover, active-role systemd control, stale-primary proof, and
standby rebuild. The HA package adds a Keepalived unicast service VIP whose
health script requires current, hostname-bound, epoch-bound, fencing-evidenced
authority and an active DASH service.

It does not implement automatic Postgres promotion. Confidence: high that a
false automatic promotion is worse than a short outage because it can create
two writable versions of the same world. The operator must fence the old host,
promote the replayed standby, start guarded services, grant a short authority
lease, and then allow the VIP to move. Both Keepalived nodes use `BACKUP` plus
`nopreempt`; failback is another explicit fenced transfer.

Use `packaging/ha/README.md` together with
`docs/primary-standby-failover.md` and `docs/cutover-runbook.md`. RKE2 or another
scheduler does not remove the single-writer Postgres, stable public address,
RabbitMQ identity, or hardware fencing requirements.

## Validation

Run the focused packaging tests:

```bash
make test-deployment-packaging
```

They validate release activation/state retention/rollback, reject bad refs,
checksums and link-bearing archives, exercise the panel command allowlist and
client grammar, parse the egg, test HA grant/epoch/revoke behavior, check shell
syntax, parse YAML when PyYAML is installed, and run Ansible syntax-check when
Ansible is available.

For a real clean host, also prove:

1. Ansible check mode produces only expected changes.
2. `/opt/dash/current/.dash-release.json` matches the selected release.
3. `/var/lib/dash/.env` and secret directories are not group/world readable.
4. `bootstrap-checklist.sh` succeeds before image load/start.
5. Official images match `DUNE_IMAGE_TAG` and the installed Steam build.
6. Database initialization occurs once and targets `DUNE_GAME_DB_NAME`.
7. `start-full-warm-pool.sh` honors the persisted autoscaler policy.
8. `/api/status` reports the active game database.
9. Backup, restore verification, guarded map restart, and release rollback are
   tested before accepting players.

## Known limits

- Published release assets are checksum-pinned, GitHub OIDC/Sigstore-attested,
  and locked by immutable releases. Locally built or raw GitHub commit archives
  retain only their explicit SHA-256 trust boundary.
- The Ansible Docker package names target current Ubuntu/Debian repositories;
  override `dash_docker_apt_packages` for another distribution/repository.
- The Proxmox playbook is a reviewed template, not permission to alter a live
  cluster without checking VM ID, storage, bridge, image, and API token scope.
- Pelican is a remote control plane, not the runtime owner; its file manager
  cannot browse DASH host data.
- HA is active/passive and reconnect-based. No peer or first-party surface
  proves zero-disconnect migration of live Dune client sessions.
