# Dune: Awakening Ecosystem Feature-Parity Audit

## Purpose

This is the aggregate parity program for DASH. It expands the focused
[`red-blink-feature-parity-audit.md`](red-blink-feature-parity-audit.md) into a
comparison against credible Dune: Awakening self-hosting stacks, dashboards,
administration tools, deployment toolkits, economy/community tools, and modding
surfaces.

The target is operator-visible outcome parity. DASH does not need to copy a
peer's framework, branding, desktop wrapper, or unsafe implementation to provide
the same outcome. A feature is not counted merely because a README promises it;
the pinned source must contain a corresponding implementation, configuration,
or documented operational path.

## Audit snapshot

- Audit date: **2026-07-15**, full GitHub search and remote HEAD refresh
  **2026-07-16 18:13 UTC**
- Search scope: GitHub repository search, project documentation, Funcom's
  self-host guide, CubeCoders' Dune template and guide, Nexus Mods' Dune:
  Awakening category, and public community discussions used only to discover
  primary sources.
- Primary-source rule: feature claims come from upstream repositories or
  official project documentation. Community posts are not treated as proof that
  a feature works.
- Target source: the current DASH worktree, including the completed Red-Blink
  parity, adaptive-autoscaler, recovery-proof, SLO, capacity-intelligence, and
  desired-state-attestation and change-intelligence tranches.

The 18:13 UTC refresh repeated all four repository searches below. The active
credible results introduced no new peer, and current default-branch HEAD still
matches every pinned fast-moving peer checked directly: Red-Blink
`12ac3b8b`, Manaiakalani `f1044620`, DST `7bafc137`, Sietch Console
`80897fc5`, adainrivers `f7dfeb0d`, Easy Dune Admin `b530670f`,
the4rchangel `749e77b8`, and BIGMOS `18ba6bc6`. Search-result-only cheat-guide
and placeholder repositories remain excluded because they contain no credible
self-host operator implementation.

Confidence labels in this document use the repository standard:

- **high**: code/configuration and documentation agree, or DASH has tests and
  runtime evidence.
- **moderate**: source contains the feature but proprietary-runtime behavior has
  not been reproduced locally.
- **low**: design or partial implementation exists without a complete outcome.
- **unknown**: no reproducible public evidence.

## Authoritative baseline

Funcom's [official self-host guide](https://duneawakening.com/self-hosted-servers/)
defines the baseline product: Windows Pro and Hyper-V, the Steam-delivered
appliance, VM and battlegroup lifecycle commands, database backup/import, file
browser and Director access, configuration files, AVX2, an FLS token, and the
published game/RMQ port ranges. The guide is a reference implementation, not a
community peer.

CubeCoders' [Dune server guide](https://discourse.cubecoders.com/t/dune-awakening-server-guide/40200)
is the strongest independently packaged alternative baseline. It replaces the
Hyper-V/k3s presentation with AMP's container orchestration and adds graphical
configuration, scheduling, backups, a file manager/SFTP, permissions, plugins,
webhooks, and Dune-specific announcement/player/status commands.

## Peer catalogue

### Full hosting stacks

| Peer | Pinned revision | Distinct operator outcomes | Confidence |
| --- | --- | --- | --- |
| [Red-Blink/dune-awakening-selfhost-docker](https://github.com/Red-Blink/dune-awakening-selfhost-docker) | `12ac3b8b30a0dac3d728a37db65cad4a292750b6` | Docker-native install, browser bootstrap, complete console, map/sietch controls, player administration, care packages, addons, metrics, backup/restore, update/repair | high |
| [Manaiakalani/arrakis-command-nexus](https://github.com/Manaiakalani/arrakis-command-nexus) | `f104462007b3ebb4a2df2f4a99e5a8337952bbdc` | Compose profiles, responsive dashboard, player history/heatmaps, race-free daily scheduled restarts, Discord event webhooks, inventory-conflict repair, host/CPU/NIC tuning, VM image builds, authenticated Steam updates, and explicitly disabled maps | high |
| [Sponge/Dune-Awakening-Server-Tools](https://git.unityailab.com/Sponge/Dune-Awakening-Server-Tools) | `04689ba704a3f6dd2d19db89a8df3b6d6a2424b2` | Ubuntu installer port, server manager/API, curated CVar catalogue, backup/update/network helpers | moderate |
| [bneff84/dunedocks](https://github.com/bneff84/dunedocks) | `5b1ec7ce728b8cb62539ae3b55388459f44cab0d` | Single privileged container enclosing the Funcom k3s stack, Unraid-oriented persistence and update-on-start | moderate |
| [n0logic/dune-linux-tools](https://github.com/n0logic/dune-linux-tools) | `089c8d61841c2f77040d644cb81b8db0f4ecdd39` | Bare-metal Debian/k3s guide, dual PvP/PvE Deep Desert, canonical configuration and memory tuning | moderate |

### Dashboards and server managers

| Peer | Pinned revision | Distinct operator outcomes | Confidence |
| --- | --- | --- | --- |
| [Icehunter/dune-admin](https://github.com/Icehunter/dune-admin) | `b1a86b16d4126e5052fb74f6463fe40ec1bce49a` | AMP/kubectl/Docker/local providers; local and Discord login; fine-grained RBAC; player/world/economy administration including offline stack/quality edits; welcome/MOTD; market bot; events; battle pass; scheduled operations | high |
| [AlphaNineGaming/AlphaNine-Dune-Suite](https://github.com/AlphaNineGaming/AlphaNine-Dune-Suite) | `bf3126ffcd7de563eda128e486009d21a325af3b` | Windows installer/setup wizard, receiver lifecycle, player/item tools, local live maps, market listings, orphan/owned-base cleanup, diagnostics, settings portability, VM scheduling, and PWA metadata | moderate; source is present but current release notes outpace live-runtime evidence |
| [Nerrowake/sietch-console](https://github.com/Nerrowake/sietch-console) | `80897fc5bc3efcbaff8b00f6a2ce57ba1b1e8aee` | Native Windows profiles, Hyper-V/Steam setup, INI editor, backups/cloud sync, remote API/SSE, diagnostics, metrics and player policy UI | moderate overall; source labels join parsing and kick/ban commands TODO/unverified |
| [adainrivers/dune-dedicated-server-manager](https://github.com/adainrivers/dune-dedicated-server-manager) | `f7dfeb0d1327273299a03802eb16a71d4523e05c` | Cross-platform desktop profiles and SSH tunnels; lifecycle/diagnostics; scheduled maintenance; live RMQ admin commands; welcome packages | high |
| [xixACExix/Simple-Dune-Awakening-Manager](https://github.com/xixACExix/Simple-Dune-Awakening-Manager) | `483530671c0bf74c61b059da269ad145de8124ad` | Windows/Hyper-V setup and lifecycle GUI; typed settings, reinstall-safe database/config backup/restore, and a keep-running health/repair watchdog | high |
| [coastal-ms/DST-DuneServerTool](https://github.com/coastal-ms/DST-DuneServerTool) | `7bafc137ca1d356b9fd4918ef9782956b00500ab` | Windows desktop/mobile/remote UI; Hyper-V management; broad gameplay/CVar editor; map spin-up; Coriolis/Landsraad tools; backup mirroring; gameplay bot; portable command console | high |
| [the4rchangel/dune-awakening-server-manager](https://github.com/the4rchangel/dune-awakening-server-manager) | `749e77b8cdff7277460ef245eb0eccb858622a93` | Six-step Hyper-V setup wizard; VM security/networking; WebSocket console; database import/export; character stats, recipes, specialization, economy, faction and cosmetics editor | high |
| [ReditusDraco/dune-dashboard](https://github.com/ReditusDraco/dune-dashboard) | `306ebcc87106a2cc3a312211da9134b93b3ac9e9` | Player/guild/vehicle/building views; chat; SSH file browser and shell; safe pod controls; encrypted/scheduled backups; TLS; SSH key rotation | high |
| [jdiveley/dune-dashboard](https://github.com/jdiveley/dune-dashboard) | `323f6d120d062c819e66c3cf034df5db9a3afe65` | Player, account, vehicle, building, guild, storage, market, event, package, map and chat views; browser shell; HTTPS | high |
| [comfuzio/OpenDune-Director](https://github.com/comfuzio/OpenDune-Director) | `f726e539d85332dd5792d58556c4d1b9d3dbfcaf` | Separate public/admin dashboards; player/vehicle/base radar; offline database teleport; vehicle fetch; over-repair; conntrack peer diagnostics; host telemetry | moderate |
| [Myers-Technologies-Public/arrakis-command-center](https://github.com/Myers-Technologies-Public/arrakis-command-center) | `17c13b9f3103c52096c69846dc09df0399d035fe` | Small PHP dashboard with player/guild/inventory administration, live logs, config editor, backups and PgHero | moderate |
| [n00bgames/Easy-Dune-Admin](https://github.com/n00bgames/Easy-Dune-Admin) | `b530670f9488c7e1b5454b1e3983d06f4c7e2d4c` | Red-Blink companion UI with live maps, offline player/vehicle teleport, item/progression/repair kits, market automation, VIP self-service, dual Deep Desert and PWA/Android packaging | high for implemented source; experimental progression paths remain labeled |
| [jaeblaze1989/Kanly-Dune](https://github.com/jaeblaze1989/Kanly-Dune) | `7acf78a980595bb31e1657c87884934678ba03c3` | One-click companion container, server/player status, INI editing and constrained command automation | moderate |
| [Gizmo3030/dune-web-admin](https://github.com/Gizmo3030/dune-web-admin) | `64cdf052f35eb7f84d0b8266622f3fbee61ae5da` | HTTPS Hyper-V lifecycle/status delegation for trusted non-shell operators | moderate |

### Deployment and panel packaging

| Peer | Pinned revision | Distinct operator outcomes | Confidence |
| --- | --- | --- | --- |
| [CubeCoders/AMPTemplates](https://github.com/CubeCoders/AMPTemplates) | `5101df5b04716e42051d456f5be5e3e9dfc6690a` | Turnkey AMP instance, graphical Dune settings, scheduler, backups, file/SFTP, plugins, webhooks, users/RBAC/OIDC | high for AMP; moderate for Dune runtime |
| [bsmr/dapdsm](https://github.com/bsmr/dapdsm) | `9d0673ef80ccc66f0020e2e2f0ba7f88e97d0e89` | Go CLI/TUI for image distribution, battlegroup creation and reconcile loops on a multi-node RKE2/HAProxy/Keepalived topology | high |
| [jegger42/dune-awakening-kvm](https://github.com/jegger42/dune-awakening-kvm) | `b89415df4891e8f6ee796b6427422663f00cf5ac` | Clean-room KVM launcher for Funcom's appliance; bridge/macvtap, unique SSH keys, lifecycle and status helpers | high |
| [comfuzio/dune-awakening-proxmox-self-hosting](https://github.com/comfuzio/dune-awakening-proxmox-self-hosting) | `bed0831d6ad0036aa7699cd970193e8d0b8fe547` | Proxmox import and VM setup path | moderate |
| [IEquilibriumI/dune-selfhost-ansible](https://github.com/IEquilibriumI/dune-selfhost-ansible) | `f59b74d826c821d4860e353c2b440066d292af27` | Ansible provisioning of a Dune Linux VM on Proxmox | moderate |
| [Sergentval/pelican-egg-dune-awakening](https://github.com/Sergentval/pelican-egg-dune-awakening) | `985e3767927cc494a55c02fac6c8aaf13d08c03f` | Pelican egg and custom Wings runtime derived from the AMP orchestration path | moderate |
| [StarTuz/Dune-awakening-svr-linux-slackware](https://github.com/StarTuz/Dune-awakening-svr-linux-slackware) | `c81560d74eaf9b8c904995d3aab30399ca9079b2` | Slackware-specific native deployment notes/scripts | moderate |

### Specialized community and modding tools

| Peer | Pinned revision | Distinct operator outcomes | Confidence |
| --- | --- | --- | --- |
| [SetsuaD/DuneAwakening-Wormageddon](https://github.com/SetsuaD/DuneAwakening-Wormageddon) | `62ef3890886b8c7ddb5b764f36e5f83189ca7515` | Portable worm/threat/storm/harvest/day/hydration presets, live commands, per-shard restart, base export | high |
| [neophrythe/Dune-Awakening-Shop-System](https://github.com/neophrythe/Dune-Awakening-Shop-System) | `affb69e8bc4b8451ddb742da6e8c5cc91dcc95a3` | Discord shop, wallets/ledger, playtime and vote rewards, manual payment credits, kits, FLS/RMQ delivery, admin dashboard | high |
| [Icehunter/dune-base-market](https://github.com/Icehunter/dune-base-market) | `85ac32524ffe8d02ffa679682404c2fd95ff3d6c` | Browser 3D/grid base designer, snapping, variants, gallery upload, ratings and blueprint detail pages | high |
| [yacketrj/dune-awakening-selfhost-discordbot](https://github.com/yacketrj/dune-awakening-selfhost-discordbot) | `c6ff63b429c88b5ab1c4d8fb053faad1d78e3a3e` | Twenty-five read/ops Discord commands, rendered status cards, scheduled posts, game/Discord bridge and role policy | high |
| [n00bgames/eda-exchange-bot](https://github.com/n00bgames/eda-exchange-bot) | `ed471e473fc02b81e8c7557ca6e218e9b28308bc` | Permissioned Red-Blink addon for exchange seeding, grade-aware pricing and buyback | high |
| [comfuzio/Dune-Awakening-remote-players-fix](https://github.com/comfuzio/Dune-Awakening-remote-players-fix) | `f47f0c0587bb7f43fc510c36ba76b0fcb4cb8646` | Automated k3s external-player routing repair | moderate |
| [jeffstokes72/duneawakeningselfhost_ini_maker](https://github.com/jeffstokes72/duneawakeningselfhost_ini_maker) | `9d10bb7b31c1ed950a69d11fe2424f25c8a84a43` | Hosted UserGame/UserEngine INI generator | low to moderate; explicitly work in progress |
| [atobo/dune-airdrop-addon](https://github.com/atobo/dune-airdrop-addon) | `cb13a7c6777edf6f56a3f73411d9e4a41c911aeb` | Movement/XP-aware playtime drops, daily streaks, weekly attendance, configurable tier multipliers and a retrying command-delivery daemon | high for source presence; runtime requires Dune-schema triggers plus Docker-socket companion |
| [yacketrj/dune-ops-observability-addon](https://github.com/yacketrj/dune-ops-observability-addon) | `271b45e7494646988bec678316659ef85313e710` | Read-only player summaries, active-rate/level/faction/guild KPIs, explicit capability reporting and constrained addon bridge | high |
| [BIGMOS/Dune-Dash-tools](https://github.com/BIGMOS/Dune-Dash-tools) | `18ba6bc654ccfb4f7758d3887c2aa20bd141567d` | Interactive/noninteractive Windows backup of game database, k3s resources, DASH configuration and server PVC configuration with destination selection and keep-last retention | high for source presence; restore is documented as a manual `pg_restore` command |

The deprecated `thebadwolf79` startup gist and the removed
`valknight/Easy-Dune-Admin` repository are historical sources; the active
`n00bgames/Easy-Dune-Admin` continuation is now a pinned peer. Empty
repositories, generic game-host marketing pages, cheat/
crack repositories, SEO “mod menu” repositories, and projects for unrelated
games were rejected.

`comfuzio/Open-Dune-Insurance` at
`e59aa6077df3648490b9d6be9d4fe4a6e865ac21` was inspected but rejected as
parity evidence. Its source explicitly uses placeholder `characters`,
`inventory_data`, `currency_data`, `is_online`, and `spice_melange` fields that
do not match the shipped Dune schema; the comments say the exact names still
need adaptation. A non-executable sketch does not create an operator outcome.

## Aggregate capability matrix

Status meanings:

- **Parity**: DASH provides the operator outcome now.
- **Authorization required**: implementation would mutate a game client and is
  paused under `AGENTS.md` until the operator explicitly authorizes client-side
  work for that task.
- **External contract**: no implementation can create the required third-party
  credential or proprietary service contract.

There are no remaining **Partial** or **Build** rows in this audit snapshot.
Parity is measured by operator-visible outcome, so an equivalent native Linux,
Ansible, or Proxmox path can satisfy a peer's Hyper-V/KVM wrapper outcome
without reproducing that wrapper.

### Installation, lifecycle, and infrastructure

| Capability | Peer evidence | DASH status | Gap/action |
| --- | --- | --- | --- |
| Direct Linux/Compose deployment | Red-Blink, Manaiakalani | Parity | Maintain clean-host validation |
| Browser bootstrap/preflight | Red-Blink, the4rchangel | Parity | Continue expanding guided error recovery |
| One-command release installer | Red-Blink, Icehunter, shop system | Parity | Full commit and SHA-256 required; archive preflight, immutable releases, shared state, atomic activation, status, and no-restart rollback; see `docs/deployment-packaging.md` |
| VM lifecycle and Hyper-V wizard | Funcom, the4rchangel, DST | Parity by supported deployment outcome | DASH's browser bootstrap plus immutable installer, secret-free cloud-init, and Ansible/Proxmox provisioning provide the setup/lifecycle outcome; native Compose deliberately removes the mandatory Hyper-V layer |
| KVM appliance launcher | jegger42 | Parity by supported VM outcome | The token-authenticated Proxmox playbook creates a `cpu: host` KVM VM, imports a reviewed cloud image, attaches cloud-init, and leaves it powered off; DASH then deploys natively instead of nesting the Funcom appliance |
| Proxmox/Ansible provisioning | comfuzio, IEquilibriumI | Parity | AVX2-aware clean-host role, Vault-only private env, exact release verification, secret-free cloud-init, token-authenticated powered-off Proxmox VM template, and independently gated image load/DB init/start |
| Pelican/AMP packaging | Sergentval, CubeCoders | Parity by safe operator outcome | Tested Pelican/Pterodactyl egg uses pinned source and a forced-command SSH client; no Docker socket, nested opaque stack, panel token, or arbitrary shell; panel lifecycle is intentionally separate from the game farm |
| Multi-node Kubernetes/RKE2 reconcile | bsmr | Parity by supported HA outcome | Immutable Ansible distribution plus existing standby reconcile/seal/promote/rebuild and a fenced Keepalived unicast service VIP; active/active and unfenced automatic promotion remain explicitly unsupported |
| Compose profiles and per-map policies | Red-Blink, Manaiakalani | Parity | Adaptive profiles exceed static peer layouts |
| Start/stop/restart/update/status | All full stacks/managers | Parity | Guarded target-aware paths are loaded |
| Per-map start/stop/restart/recovery | Red-Blink, Manaiakalani, DST | Parity | Native post-start hooks preserved |
| Dynamic maps and warm retention | Red-Blink | DASH exceeds | Minimum/balanced/adaptive/full/custom supported |
| Measured scaling efficiency and evidence-driven retention | No surveyed Dune peer | DASH exceeds | Private time-weighted ledger measures map-hours saved, idle warm cost, productive running, warm/cold revisits, request-to-ready p50/p95, coverage and forecasts; adaptive recommendations are evidence-gated, gradual, mode-preserving, receipted, backed up, and alertable; see `docs/capacity-intelligence.md` |
| Explicitly disabled maps survive update/restart | Manaiakalani | Parity | Persisted custom autoscaler modes and selective startup keep stopped/dynamic maps out of normal startup; full-warm remains an explicit operator choice |
| Multi-Sietch management | Red-Blink, the4rchangel | Parity | Up to 64 guarded dimensions |
| Public-IP/routing repair | Red-Blink, comfuzio | Parity | Monitor and LAN reflection paths loaded |
| Host CPU/NIC/THP tuning | Manaiakalani, DST | Parity | Cache-aware affinity plus guarded, backup-first sysctl/THP/NIC ring/IRQ tuning; larger existing network maxima are preserved and Docker is not restarted |
| Memory telemetry/balancing | Red-Blink, Manaiakalani | Parity | DASH adds pressure-aware LRU eviction |
| Metrics and retained history | Red-Blink, AMP | Parity | Prometheus/node/cAdvisor/Postgres/RMQ overlay |
| Public read-only status | OpenDune, Manaiakalani | Parity | Separate static-site package |

### Security and operator access

| Capability | Peer evidence | DASH status | Gap/action |
| --- | --- | --- | --- |
| Single owner token, host/origin checks, audit | Red-Blink, Manaiakalani | Parity | Existing hardened LAN/VPN mode |
| Multiple local users | Icehunter, AMP | Parity | Named identities, one-time high-entropy tokens, SHA-256-only storage, rotate/disable/enable/remove lifecycle, and owner recovery token |
| Fine-grained RBAC/capabilities | Icehunter, AMP | Parity | Protected routes map to read, operations, player, economy, world, configuration, infrastructure, and community capabilities; unknown writes fail closed |
| Discord OAuth/OIDC SSO | Icehunter, AMP | Parity implementation; provider canary pending | Authorization code + PKCE, OIDC discovery/RS256/issuer/audience/nonce validation, Discord `identify`, exact subject-to-local-RBAC mapping, signed HttpOnly sessions, replay defense, logout, and owner-token recovery; external application credentials and an HTTPS callback are required for a live canary; see `docs/federated-auth.md` |
| TLS/reverse-proxy guidance | Reditus, AMP | Parity | Private VPN/authenticated proxy patterns, exact host/origin handling, TLS/identity boundary, verification, and Caddy example; see `docs/remote-admin-access.md` |
| SSH key rotation/tunnels | adainrivers, Reditus | Parity | Named strict-host-key profiles, expected-hostname check, loopback-only admin forwarding, fixed-program two-phase Ed25519 rotation, remote backups, retained recovery key, and private receipts; see `docs/remote-targets.md` |
| Browser file manager/SFTP | Funcom, AMP, Reditus | Parity by outcome | Bounded config/log/backup/database/addon workspaces cover operator outcomes without arbitrary host filesystem authority; see `docs/remote-admin-access.md` |
| Browser shell/terminal | Reditus, jdiveley, DST | Parity by safe operator outcome | Six named native read-only diagnostics expose the operator outcome with no subprocess/shell/arguments/stdin, bounded timeout/output, redaction, operator RBAC, and receipt-only audit; see `docs/command-console.md` |
| Encrypted backup archives | Reditus | Parity | Encrypted restic repositories plus verified recipient OpenPGP archives, exact fingerprint selection, private temporary/plaintext cleanup, ciphertext SHA-256 receipts, safe decrypt staging, encrypted-only rclone/rsync scheduling, dashboard readiness/inventory, and recovery drills; see `docs/backup-encryption.md` |

### Operations, backup, and integrity

| Capability | Peer evidence | DASH status | Gap/action |
| --- | --- | --- | --- |
| Layered backup/list/download/import/restore | Red-Blink, dashboards | Parity | Verified, quarantined restore lifecycle |
| Scheduled backup and retention | Icehunter, Reditus, Manaiakalani | Parity | Host timers and panel schedule |
| Automated real restore rehearsal and RPO/RTO evidence | BIGMOS documents manual `pg_restore`; other peers inspect/archive backups | DASH exceeds | Daily no-network disposable PostgreSQL restore, Dune schema/data/index/constraint checks, analyze, round-trip dump, measured RPO/RTO, verified cleanup, private hash-chained receipts, dashboard/API, and hardened timer; see `docs/restore-drills.md` |
| Time-weighted reliability objectives and error budgets | Peers expose current health and retained infrastructure metrics | DASH exceeds | Nine service objectives, five time windows, observation coverage, burn rates, remaining budget, debounced incidents, immutable globally hash-chained events, bounded maintenance exclusions, dashboard/API/Prometheus, and transactionally consistent recovery; see `docs/operational-slo.md` |
| Continuous desired-state attestation and drift ownership | No surveyed Dune peer | DASH exceeds | HMAC-sealed repository/configuration and Compose-container baselines, keyed redaction of environment values and mount sources, retained findings, non-resolving acknowledgement, immutable baseline/event history, private dashboard/API/metrics, SLO integration, and backup-bound key verification; see `docs/desired-state-attestation.md` |
| Operational change intelligence and incident evidence capsules | No surveyed Dune peer | DASH exceeds | Append-only HMAC event timeline, authoritative incident reconciliation, credential stripping, identity/path pseudonymization, policy-classified impact, bounded temporal/scope candidate ranking, explicit non-causality, portable ledger-head-bound signed exports with offline verification, dashboard/API/CLI/metrics, and backup-bound verification; see `docs/change-intelligence.md` |
| Deterministic evidence-linked incident response plans | No surveyed Dune peer | DASH exceeds | Every default SLO plus desired/generic incidents maps to a policy-digested runbook with machine-evaluated evidence predicates, exact bounded diagnostic IDs, existing capability/gate/confirmation recovery contracts, zero automatic execution, nested plan integrity inside portable signed capsules, UI navigation, CLI, and backup-bound archived-capsule verification; see `docs/incident-response.md` |
| Non-disruptive incident-response readiness rehearsals | No surveyed Dune peer | DASH exceeds | Stale-plan-bound explicit drills run only fixed native read-only diagnostics, hash/discard output, verify current principal/gate/confirmation recovery contracts, execute no recovery/game mutation, append incident-linked HMAC receipts, feed signed capsule inputs, expose label-free readiness metrics, and alert on failure/staleness; see `docs/incident-response.md` |
| Offsite/mirror/failover backup | DST, Reditus | Parity | Replica, snapshot, rsync/rclone/restic examples |
| Scheduled restart with warnings and backup | adainrivers, Manaiakalani, AMP | Parity | Daily maintenance timer loaded |
| Authenticated Steam update and Steam Guard bootstrap | Manaiakalani | Parity | Protected owned-account login/password settings, interactive SteamCMD bootstrap for password/Steam Guard, persistent private Steam home, locked unattended hotfix updater, and restart-only-on-change behavior; one-time Steam Guard codes are not retained |
| One-time/repeating announcements | Manaiakalani, AMP | Parity | Panel scheduler and verified RMQ hook |
| General event automation | Icehunter, AMP | Parity | Persistent five-second scheduler, ISO times, bounded recurrence/max-runs, safe announcement/restart-plan primitives, dry-run-only mutation proposals, 500-run ledger, manual run/cancel, UI/API, and webhook audit emission; see `docs/event-automation.md` |
| Outbound Discord event webhooks | Manaiakalani, AMP | Parity | Filtered generic or Discord payloads, HMAC-SHA256 signatures, recursive redaction, bounded asynchronous queue/retry/rate limits, redirect refusal, and secret-free delivery records; see `docs/outbound-webhooks.md` |
| Full Discord bot/status cards | yacketrj, Icehunter | Parity implementation; credential canary pending | First-party dependency-free Gateway v10 bot, all 29 named peer subcommands plus eight identity-bound community commands (37 across seven groups), guild/channel restrictions, ephemeral bounded output, role propagation, heartbeat/resume/reconnect, hardened systemd service, credential-wait state, tests, and permissioned adapter isolation; a real Discord READY/interaction requires operator credentials; see `docs/discord-bot.md` |
| Inventory slot-conflict detection/repair | Manaiakalani | Parity | `scripts/inventory-conflicts.sh` audits live state and provides hostname-, backup-, capacity-, and transaction-gated no-delete repair |
| Log export/live stream/filter/download | Most dashboards | Parity | Bounded decoded service logs and evidence bundles |
| Cheat/anti-cheat event view | Icehunter | Parity | Bounded service logs are normalized, deduplicated, redacted, retained, and displayed beside moderation history; unrelated lines and raw peer IPs are not persisted |
| Database browser/query/export/row editor | Red-Blink, Icehunter, Myers | Parity | Bounded and separately gated |
| Host/process crash forensics | Manaiakalani, DST | Parity | Operational bundles, watchdog, profiles and captures |

### Players, world, and administration

| Capability | Peer evidence | DASH status | Gap/action |
| --- | --- | --- | --- |
| Player/account/profile/search/history | All admin peers | Parity | Online/offline roster and deep detail |
| Inventory, currency, XP, skills, recipes, journey | Icehunter, the4rchangel, Red-Blink | Parity | Guarded native/DB paths |
| Existing inventory stack and quality editing | Icehunter 0.45 | DASH exceeds | Combined editor requires the owner offline, creates a full DB backup, locks item/owner state and rechecks offline status in one transaction, preserves all other composite fields through `dune.save_item`, verifies both values before commit, audits the receipt, and documents relog cache behavior |
| Water, teleport, kick, vehicle spawn | adainrivers, DST, Red-Blink | Parity | Native runtime actions loaded |
| Ban/unban and moderation case history | Manaiakalani, admin feedback | Parity | Source/schema audit found dashboard-local ban state rather than a native Dune ban contract; DASH adds append-only cases plus repeated confirmed native `KickPlayer` enforcement and labels the lack of login-level rejection |
| Faction, guild and reputation management | Icehunter, Reditus | Parity | First-party function-backed guarded actions |
| Landsraad administration | Icehunter, DST, Red-Blink | Parity | Cycle guard remains mandatory |
| Bases/storage/vehicles/locations/map radar | Icehunter, OpenDune, Reditus | Parity | DASH adds asset-backed maps and storage detail |
| Player connection heatmaps | Manaiakalani | Parity | Presence sessions and daily/hourly/map coarse cells have bounded retention and no raw peer-IP persistence |
| Conntrack/raw peer IP diagnostics | OpenDune | Parity with privacy boundary | On-demand CLI filters configured game/RMQ ports, coarsens peers by default, requires exact confirmation for ephemeral raw output, and never persists it; see `docs/game-peer-diagnostics.md` |
| Character cosmetics/skins bulk editor | the4rchangel | Parity | Independent 391-ID observed catalog, optional local-pak builder, searchable inspection, catalog-confined idempotent add/remove, customization-only bulk unlock, offline row lock, backup, compare-and-swap verification, private receipts, and guarded rollback; no first-party routine exists; see `docs/character-cosmetics.md` |
| Base export/reconstruction/restore | Wormageddon, Icehunter | Parity for evidenced outcome | Exact plus recentered portable export and reconstruction are implemented. Wormageddon's source ships export but no import command and calls restore unfinished/experimental; DASH labels direct live restore unproven instead of claiming it |
| Base designer/gallery/ratings | dune-base-market | Parity | Browser snapping/yaw grid editor, top-down preview, JSON lifecycle, isolated private/unlisted/public gallery, per-identity ratings, backups, and RBAC; see `docs/base-creator.md` |
| Orphan/owned-base cleanup or retirement | AlphaNine | DASH exceeds; disposable live canary pending | Instead of permanently deleting a narrow row set, DASH classifies ownership, requires a stopped map and explicitly offline owners/recovery player, binds execution to a SHA-256 content preview under advisory/row locks, creates a full database dump and private receipt, calls the current build's native `base_backup_save_from_totem`, verifies the resulting player-owned linked-actor backup and permission removal before commit, and preserves in-game recovery; see `docs/base-retirement.md` |
| Welcome kits and per-session MOTD | Icehunter, adainrivers | Parity | Care packages and presence automations |
| Configurable item packages | DST, shop system | Parity | Care-package library and grant history |

### Economy and community systems

| Capability | Peer evidence | DASH status | Gap/action |
| --- | --- | --- | --- |
| NPC exchange seeding/buyback/pricing | Icehunter, EDA addon | Parity | Artificial Exchange with watchdog and audit |
| Discord shop/catalog/kits | shop system | Parity implementation; live purchase canary pending | Eight player-facing `/dune shop` commands, versioned offers/kits, stock, idempotent orders, and private adapter identity binding; see `docs/community-rewards.md` |
| External wallet and immutable ledger | shop system | Parity | Isolated SQLite wallet, non-negative constraints, append-only triggers, global SHA-256 hash chain, unique references, and full verification; never game Solari |
| Playtime rewards | shop system, AMP analytics | Parity | Confirmed presence checkpoints, remainder accounting, bounded observation gaps, idempotent credit and optional track XP |
| Movement/AFK-aware airdrops, daily streaks and weekly rewards | atobo airdrop addon | DASH exceeds | Map/partition/3D movement proof, bounded grace/gaps, scaled active-session rewards, UTC streaks, ISO-week active-time thresholds, combined credits/track XP/items, append-only claims, and receipted offline delivery without Dune-schema triggers or Docker-socket access; see `docs/engagement-airdrops.md` |
| Vote/manual-payment reward webhooks | shop system | Parity implementation; provider canary pending | Fresh timestamp plus raw-body HMAC-SHA256, provider/event replay identity, collision rejection, credit caps, and secret files; no processor/card data in DASH |
| Battle pass/custom reward track | Icehunter | Parity | Versioned tracks, monotonic levels, idempotent progress references, unique claims, and the guarded delivery queue |
| Custom community events | Icehunter | Parity | Persistent recurring scheduler, dry-run plans, bounded execution ledger, manual run/cancel, announcements/restarts, and signed outbound events |
| Discord command bridge | yacketrj, Icehunter | Parity implementation; credential canary pending | Permissioned read/ops adapter plus identity-bound community link/balance/catalog/buy/kit/track/claim writes; no owner credential or generic admin mutation route |

### Configuration and modding

| Capability | Peer evidence | DASH status | Gap/action |
| --- | --- | --- | --- |
| Raw UserGame/UserEngine editor | Funcom, all panels | Parity | Backed up and allowlisted |
| Typed visual settings | Red-Blink, AMP, the4rchangel | Parity | Expand labels/presets, not arbitrary unproven writes |
| Worm/threat/storm presets | Wormageddon | Parity | Nine validated worm/threat/storm/harvest/day/hydration/world profiles, exact per-target diff, backup-first atomic apply, confined rollback, restart planning, and mandatory seven-day Landsraad validation; see `docs/gameplay-presets.md` |
| Broad CVar/INI catalogue | Sponge, DST | Parity | Shipped 2,242-key/156-section INI index plus independently generated 7,028-entry build/binary-hash-pinned console catalogue, search/filter CLI, provenance, decoded flags, server relevance, and explicit candidate-vs-promoted boundary; see `docs/cvar-catalog.md` |
| Addon discovery/install/permissions | Red-Blink, EDA addon | Parity | SHA-pinned sandbox and constrained bridge |
| Server runtime loader/Lua API | UE4SS capability model | Parity with surveyed Dune peers; broader model remains build-specific research | No surveyed peer ships a proven live UE4SS-compatible Dune dedicated-server runtime. DASH ships a Linux server loader, packaged Lua lifecycle/scheduler APIs, and staged evidence gates; package-backed `LoadAsset` and current-build live-target promotion remain explicitly unproven research limits, not an aggregate peer gap; see `docs/ue4ss-linux-loader-evaluation.md` |
| Pak extraction/overlay/build tools | community mod workflows | Parity | Repo-contained, reversible server-side tooling exists |
| Client loader/Pak deployment | Nexus/UE4SS client workflows | Parity deployment; read-only current-build root canary complete | Receipt-bound transactional manager provides confined loader/sidecar/Lua/Pak-overlay planning, locked build/source/target revalidation, verified private backups/manifests, atomic install, collision detection, audit, and retryable rollback. The verified Windows archive includes the manager/tests/runbook/current evidence and rejects incomplete checksums or unsafe tar members. The authorized build-24146567 canary proved proxy loading plus build-specific FNamePool/GUObjectArray and sampled reflection; dispatch, native calls, Lua routing, and Pak mounting remain unproven. See `docs/client-deployment.md` and `docs/windows-client-loader-canary-2026-07-15.md` |
| Voice chat/Tencent GME | proprietary provider contract | External contract | No peer has public working Funcom-compatible credentials or token generation |

## Gap tranches

The implementation order is based on operational value and dependency, not on
peer popularity.

### Tranche 1: trust, integrity, and host efficiency

1. Multi-user capability/RBAC foundation that preserves the existing owner
   token as a full-access recovery credential. **Complete:** see
   `docs/admin-access-control.md`.
2. Inventory slot-conflict audit and guarded repair. **Complete:**
   `scripts/inventory-conflicts.sh`; see `docs/inventory-integrity.md`.
3. Dry-run-first host tuning and CPU pin overlay generation. **Complete:** see
   `docs/cpu-affinity.md` and `docs/host-tuning.md`.
4. Signed outbound event/webhook framework. **Complete:** see
   `docs/outbound-webhooks.md`.
5. Remote-access and bounded file-workspace documentation. **Complete:** see
   `docs/remote-admin-access.md`.

### Tranche 2: community automation

1. First-party Discord bot package using the permissioned adapter. **Complete:**
   see `docs/discord-bot.md`.
2. Recurring event scheduler and trigger ledger. **Complete:** see
   `docs/event-automation.md`.
3. Battle-pass/reward-track service. **Complete:** versioned tracks,
   monotonic progress, idempotent claims, and guarded delivery are part of the
   community rewards service.
4. Optional shop/wallet/playtime/vote service. **Complete:** see
   `docs/community-rewards.md`.

### Tranche 3: world and creator tooling

1. Privacy-bounded player history/heatmaps and normalized moderation events. **Complete:** see `docs/moderation-history.md`.
2. Proven base-backup export/restore workflow. **Complete for the peer-proven export/reconstruction contract; direct live placement remains unproven in peer source and current runtime.**
3. Standalone base designer/gallery package. **Complete:** see `docs/base-creator.md`.
4. Worm/CVar preset library with diff, preview, per-map apply, restart planning,
   and rollback. **Complete:** see `docs/gameplay-presets.md`.
5. Character cosmetics/skins catalog, exact add/remove, bulk unlock, and
   rollback. **Complete:** see `docs/character-cosmetics.md`.

### Tranche 4: alternate packaging

1. Clean-host installer with release pinning and rollback. **Complete:** exact
   commit/SHA-256, archive safety preflight, immutable release/state split,
   atomic activation, and no-restart rollback.
2. Proxmox/cloud-init/Ansible role. **Complete:** see
   `docs/deployment-packaging.md` and `packaging/ansible`.
3. Pelican template with a safe multi-service isolation contract. **Complete:**
   a constrained forced-command remote controller avoids Docker-socket and
   monolithic nested-runtime authority; see `packaging/pelican`.
4. Multi-node/HA reference deployment. **Complete for the supported
   active/passive outcome:** existing single-writer standby reconciliation plus
   explicit fencing authority and Keepalived VIP; see `packaging/ha`.

Client-side mod installation is not part of these server tranches. It starts
only when explicitly authorized for a concrete client task, as required by
`AGENTS.md`.

## Current conclusion

- **High confidence:** all feasible operator-visible outcomes in the pinned
  peer catalogue have a shipped DASH parity path. The only non-parity statuses
  are an explicitly unauthorized client-mutation scope and the external
  Funcom/Tencent voice credential contract.
- **High confidence:** DASH already meets or exceeds the core hosting,
  lifecycle, map, backup, player administration, exchange, addon, metrics,
  public-status, failover, and server-side reverse-engineering outcomes in the
  surveyed ecosystem. Backup capability now exceeds the newest peer evidence:
  DASH automatically proves a real dump restores and records measured,
  tamper-evident recovery evidence instead of stopping at archive creation or a
  manual `pg_restore` instruction.
- **High confidence:** DASH now goes beyond the surveyed scaling implementations
  by measuring both sides of the cold/warm tradeoff. Retained map-hours,
  warm-idle cost, warm/cold outcomes, empirical revisit gaps, and routable-ready
  start latency feed gradual per-map recommendations while LRU/memory budgets
  and operator-selected modes remain authoritative.
- **High confidence:** DASH now also exceeds surveyed configuration-management
  evidence with continuous HMAC-sealed file/container desired-state
  attestation, retained drift ownership, immutable baseline history, private
  metrics/SLO coupling, and backup-bound key verification.
- **High confidence:** no surveyed peer correlates retained operator changes
  with SLO/drift incident onset. DASH now adds a privacy-bounded HMAC timeline
  and ranked evidence capsules while explicitly refusing to infer causality.
  Capsules can also be frozen into portable ledger-head-bound artifacts and
  verified offline without trusting the live dashboard or source database.
- **High confidence:** DASH now turns those capsules into deterministic response
  plans for every default SLO plus desired/generic incidents. Plans distinguish
  verified facts from pending operator work, reuse exact bounded diagnostics,
  preserve every existing recovery gate, execute nothing automatically, and
  remain independently digest- and HMAC-verifiable in backups and escalation.
- **High confidence:** local RBAC, outbound events, the first-party Discord bot,
  community rewards/shop/tracks, host tuning, inventory integrity repair,
  recurring event automation, moderation case history, native policy-ban
  ejection, normalized security signals, coarse heatmaps, base creator tooling,
  recoverable native base retirement, curated gameplay presets, federated identity, bounded browser diagnostics,
  encrypted archives, guarded cosmetics administration, and alternate
  deployment packaging are implemented.
- **High confidence:** the 2026-07-16 live search added eight credible peers and
  one rejected placeholder project. New executable outcomes were closed in the
  same refresh: movement-verified engagement airdrops now exceed the trigger +
  Docker-socket peer design, and existing-item stack/quality edits add offline,
  backup, composite-preservation, and post-write verification gates. AlphaNine's
  newly surfaced destructive base-cleanup outcome is superseded by a native,
  recoverable, fingerprint-bound retirement path; its disposable live archive
  and in-game restore canary remains pending.
- **Unknown:** end-to-end Discord READY/interaction behavior until an operator
  supplies application, guild, and bot credentials. The unit, adapter, and
  protocol paths are locally validated and the service can wait without a
  restart loop.
- **Moderate confidence:** no credible open-source Dune-specific server mod
  manager exceeds DASH's current server loader, Pak tooling, addon lifecycle,
  and evidence pipeline. Nexus is a distribution surface, not a self-host
  administration peer.
- **Unknown:** working self-host voice without Funcom-compatible Tencent GME
  credentials. No surveyed peer supplies it.

## Refresh procedure

Repeat the audit before declaring aggregate parity complete:

```bash
gh search repos 'Dune Awakening self hosted' --limit 100
gh search repos 'Dune Awakening dedicated' --limit 100
gh search repos 'Dune Awakening admin' --limit 100
gh search repos 'Dune Awakening tool' --limit 100
```

For every included peer, pin `git rev-parse HEAD`, inspect README/release notes,
then verify claimed features against source files, routes, tests, templates, or
scripts. Update this document, the README capability summary, and the tranche
backlog together.
