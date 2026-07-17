# Red-Blink Feature Parity Audit

## Scope and pins

This audit compares operator-visible outcomes, not framework, file count,
screenshots, or branding.

| Repository | Pinned revision | Audit date |
| --- | --- | --- |
| `Red-Blink/dune-awakening-selfhost-docker` | `7ae3e7738897c0ca5cf902e4dcb6387d67d443dc` (`v1.3.59`) | 2026-07-16 |
| `snapetech/DuneAwakeningSelfHost` | `8e04154e16b8d77e4492b4e71b923da6432f041e` before this polish tranche | 2026-07-16 |

The comparison covered Red-Blink's README/release notes, React console, API
routes and service modules, runtime scripts and state contracts, all Compose
files, addon and Discord documentation, metrics configuration, tests, and
security/release checks. The DASH comparison covered its full admin route and
UI surface, Compose and overlays, configuration, scripts, tests, and operator
documentation.

Status meanings:

- **Parity**: the same operator outcome exists, although the architecture or UI
  can differ.
- **DASH exceeds**: parity exists and DASH adds operational or safety coverage.
- **Added**: the outcome was implemented during this audit.
- **Not applicable**: neither project provides the outcome.

## Result

At the pinned Red-Blink revision, no known operator-visible feature remains
unimplemented in DASH. Source-level feature parity is complete. Runtime actions
that depend on the proprietary game server still require a lab canary before
production enablement; that validation boundary is not an omitted feature.

| Area | Red-Blink outcome | DASH result | Status |
| --- | --- | --- | --- |
| First-run setup | Browser setup/config/init workflow | `/bootstrap` reports prerequisites, generates TLS, initializes the database, and reconciles/starts the project through repository scripts | Added/parity |
| Authentication | Password session and CSRF controls | Token auth, host/origin enforcement, throttling, CSP, request bounds, allowlist/bind controls | Parity |
| Readiness | Status, ports, services, doctor timeline | Readiness verdicts, FLS/RMQ/network probes, map health, evidence bundles, recovery paths | DASH exceeds |
| Services and logs | Service inventory, bounded logs, service controls | Project-labelled inventory, decoded bounded logs, target-aware start/stop/restart, separate stateful-service gate | Added/DASH exceeds |
| Backups | Create/list/download/import/restore/delete and schedule | Verified full backup lifecycle, quarantine import/delete, layer selection, stopped writers, pre-restore backup, post-hooks, rollback evidence, automatic schedule and retention | Added/DASH exceeds |
| Database | Catalog/table/query/export/row/password tools | Bounded catalog and previews, one-statement SQL/export, primary-key row editor, coordinated password rotation, backup/audit/redaction controls | Added/parity |
| Players | Search, online/profile/inventory/progression/history | Online/offline roster plus account, pawn, controller, currency, XP, inventory, location, lifecycle, progression, world, and economy inspectors | DASH exceeds |
| Player actions | Items, XP, max/reset specialization, all-keystone grant/reset, skills, Intel, recipe/research unlocks, water, teleport, kick, inventory/progression cleanup, recovery, gear and vehicles | Guarded item/currency/XP, exact max/reset specialization and all-keystone workflows, Intel/recipe/research and offline teleport tools; native Version 2 skills, water, online teleport, kick/kick-all, clean-inventory, reset-progression and vehicle spawn; guarded gear/vehicle repair, refuel and stale login-queue repair | Added/parity |
| Item/augment catalog | Search, categories, images, augment selection | Visual catalog, compatibility/effect picker, perfect-roll stat construction, slot limits, pre-augmented grants, automatic prerequisites | Added/parity |
| Blueprints | Solido import/export/delete/deduplicate | Validated dry-run/import, bulk export, rollback archive, deletion, name dedupe, transactions, backups, verification | Added/parity |
| Care packages | Presets, eligibility, manual/automatic grants, history | Reviewed presets, once/cooldown rules, preview, backup, first-online/returning worker, persisted claims/pending/history, retry and clear controls | Added/parity |
| Guilds | Searchable guild management | Guild/member/invite browser and guarded description/role plans and writes | Added/parity |
| Landsraad | Overview, term, task-goal, reward and contribution workflows | Terms/tasks/rewards/contributions browser; end-time/force-end, individual/all-term goals, reward-tier and player-contribution writes with backup, dry-run, rollback and aggregate recomputation | Added/parity |
| Live maps | Players, bases, storage, services, markers, overlays, teleport | Hagga Basin and Deep Desert maps, players, POIs, markers, resources/spice diagnostics, services, bases, storage and guarded offline teleport | Parity |
| Map layouts | Always-on/dynamic maps, up to 64 Sietches, per-Sietch display/password, and Deep Desert | Nine-map farm, 30-partition warm pool, guarded additional Survival dimensions up to 64 with isolated saved data and deterministic ports, per-partition settings, all-farm lifecycle integration, partition seed/recovery, DD overlays and watchdog | Added/parity |
| Autoscaling | Dynamic demand, spawn/despawn and reconcile controls | Configurable minimum/balanced/adaptive/full/custom modes, Director travel-log demand, idle stop, explicit demand, bounded reconciliation, watchdog integration, retained map-hours/warm-hit/cold-start evidence, and gradual per-map retention recommendations | DASH exceeds |
| Memory | Per-map settings and automatic balancing | Per-service limits, runtime profiles, host/container telemetry, bounded automatic memory balancer | Added/parity |
| Settings | Structured and raw game settings | Typed settings, safe environment editor, raw INI editor with backups, logout controls and Coriolis/Landsraad guardrails | DASH exceeds |
| Transfers and spice | Director transfer rules and spice controls | Typed transfer rulesets; spice caps, field inspection, lifecycle scripts and map diagnostics | Parity |
| Announcements/MOTD | Broadcast, map chat, MOTD and player messages | Broadcast/restart scheduling, map/private messages, first-session private welcome template, presence automation and digests | Parity |
| Updates/repair | Game/stack updates, schedule, runtime repair | Steam update flow, candidate-validated Git fast-forward, hotfix timer, reboot resume, image verification and post-start repair; certified maintenance revalidates the exact staged candidate before disruption, verifies the stopped-world recovery backup before apply, restores current service on proof/update failure, and emits a signed stage outcome | DASH exceeds |
| Host lifecycle | Clean host-shutdown protection and automatic advertised-address changes | Full-farm systemd `ExecStop` runs the ordered shutdown path; a hostname-gated, dry-run-first timer detects IPv4 drift, archives configuration/TLS, rotates the advertised address and certificate, and invokes the target-aware restart | Added/parity |
| Docker storage | Safe obsolete-image/cache cleanup | Dry-run-first known-repository cleanup with current/in-use protection and separate cache opt-in | Added/DASH exceeds |
| Public server directory | Account-backed centralized listing with heartbeat/status, region, population, Sietches, Discord, and visitor latency | Opt-in short-lived Ed25519 descriptor plus self-hosted pull federation; bounded DNS-pinned collection, no shared secret or registration API, independent browser verification, explicit visitor latency scan, metrics and stale/invalid alerts | Added/DASH exceeds |
| Game storage | Aggregate/detail storage browsing, JSON export and grants | Aggregate base-storage view, bounded per-actor item detail/JSON, player inventory and separately guarded base-storage discovery/grants | Added/parity |
| Metrics | Prometheus, node, container, Postgres and RabbitMQ metrics | Optional `compose.metrics.yaml` with Prometheus retention plus node exporter, cAdvisor, Postgres and RabbitMQ targets | Added/parity |
| Discord | Documented adapter route family | Same read-only Red route family, readiness and permission mapping; Red's write routes are also hard-disabled at the pinned revision | Added/parity |
| Community addons | Discovery/install/enable/remove and permission grants | Discovery, immutable hashes, staging, install/enable/remove, permission review, quarantine, iframe sandbox and constrained bridge | Added/DASH exceeds |
| Creator/modding runtime proof | No unified input-bound lifecycle proof | HMAC-signed disposable canary binds exact base/gallery/retirement/preset/cosmetics/addon inputs and exercises their real supported lifecycles without live database, config, map, or network state | DASH exceeds |
| Security/release | Non-root service and release/security checks | Secret scan, publication checks, mutation gates, audit log, target safety and validation suite | Parity |
| Failover/replication | Local single-host operation | Streaming replica, snapshots, promotion/cutback, bidirectional audit and identity bundles | DASH exceeds |
| Reverse engineering | Operational/admin emphasis | Build-pinned Ghidra, evidence catalogs, loader canaries and safe promotion contracts | DASH exceeds |
| Voice/Tencent GME | No credential acquisition, token generator or working self-host voice implementation | Provider-field diagnostics and failure documentation; no provider credentials or working self-host voice | Not applicable to parity |

## Added implementation surfaces

The parity tranche added or expanded these documented surfaces:

- [`infrastructure-console.md`](infrastructure-console.md): service/log control,
  backup lifecycle and scheduling, database operations, update/repair and Docker
  storage cleanup.
- [`bootstrap-console.md`](bootstrap-console.md): browser bootstrap status and
  guarded initialization actions.
- [`player-runtime-actions.md`](player-runtime-actions.md): native skill, water,
  kick and vehicle actions plus offline vehicle maintenance.
- [`care-packages.md`](care-packages.md): manual and automatic eligibility/grant
  lifecycle.
- [`blueprints.md`](blueprints.md) and [`augments.md`](augments.md): Solido and
  structured augment workflows.
- [`world-console.md`](world-console.md): guild, Landsraad and storage views plus
  the separately gated Landsraad write API.
- [`autoscaling-memory.md`](autoscaling-memory.md): map autoscaling, Director
  demand and automatic memory balancing.
- [`capacity-intelligence.md`](capacity-intelligence.md): retained scaling
  efficiency, cold-start/revisit evidence, forecasts, and adaptive retention.
- [`metrics.md`](metrics.md): retained Prometheus metrics stack.
- [`federated-public-directory.md`](federated-public-directory.md): signed,
  privacy-bounded publication and self-hosted static pull federation.
- [`discord-adapter.md`](discord-adapter.md): pinned Red-compatible adapter.
- [`addons.md`](addons.md): community addon lifecycle and containment contract.
- [`creator-modding-canary.md`](creator-modding-canary.md): signed,
  input-bound, no-live-state lifecycle proof across creator and modding tools.
- `scripts/storage-cleanup.sh`: scoped obsolete-image cleanup.
- `scripts/public-ip-monitor.sh`: automatic advertised-address/TLS lifecycle.
- `scripts/sietches.sh`: guarded multi-Sietch topology, settings and generated
  service lifecycle.

The exact Red Version 2 command envelope, player skill/vehicle catalogs,
Landsraad mutation semantics, community addon lifecycle concepts and Director
travel-demand patterns are attributed under Red-Blink's MIT license in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Mutation controls

Parity features are present but disabled by default where they mutate game or
host state. They require the master mutation gate, feature-specific gates,
exact confirmations, and—where applicable—an automatic database backup,
offline/online state check, transaction, verification, or rollback artifact.
The relevant variables and confirmations are listed in
[`admin-panel.md`](admin-panel.md).

The native player actions use Red-Blink's concrete outer envelope and RabbitMQ
route rather than enabling DASH's older generic GM research endpoint. The
generic `/api/admin/gm/execute` remains intentionally separate and blocked
until its broader arbitrary command-body contract is proven.

## Voice-chat finding

The pinned Red-Blink source, public issues and public discussions were searched
for Tencent, GME, `GmeAppId`, `GmeAppKey`, room tokens and voice chat. No
Red-Blink implementation or report of working self-host voice was found. A
Tencent room-auth buffer is tied to an application's SDK AppID, secret key,
OpenID, room ID and expiry; a token or key from another Tencent application is
not reusable for the Funcom application. Red-Blink therefore provides no voice
feature that DASH needs to copy.

## Validation boundary

- **High confidence**: the pinned feature inventory, route/config presence,
  static validation, unit tests and Compose rendering.
- **Moderate confidence**: proprietary game runtime effects for native player
  commands, vehicle spawn, Landsraad writes, bootstrap/update orchestration and
  automatic scaling until enabled and canaried on `kspld0`.
- **Unknown**: Tencent GME voice operation without authorized, compatible
  provider credentials.

No production host, player, container, database or client was mutated during
the audit or implementation work. Production mutations remain restricted to
`kspls0` after explicit hostname verification.

## Production activation

Source parity and runtime activation are separate. Preview and then apply the
complete gate set on the production host:

```bash
./scripts/enable-feature-parity.sh .env
./scripts/enable-feature-parity.sh .env --execute
```

The activation script refuses any host except the configured exact hostname
(`kspls0` by default), backs up `.env`, generates a private native-command
token only when one is missing, enables the metrics overlay and all parity
gates, selects the evidence-driven adaptive autoscaler profile, and leaves the public
IP monitor in dry-run for its first validation. It does not execute grants,
database writes, restores, updates, or addon installations; those operations
retain their per-action confirmation phrases and backups.

## Reproduction

Run the focused parity validation with:

```bash
python3 -m py_compile admin/admin_panel.py admin/addon_admin.py \
  admin/augment_admin.py admin/blueprint_admin.py admin/native_command_admin.py \
  scripts/test-admin-panel-safe-surfaces.py
python3 scripts/test-admin-panel-safe-surfaces.py
make test-public-directory
bash -n scripts/storage-cleanup.sh scripts/test-storage-cleanup.sh scripts/watch-maps.sh
./scripts/test-storage-cleanup.sh
./scripts/test-public-ip-monitor.sh
./scripts/test-sietches.sh
python3 -m json.tool config/care-packages.json >/dev/null
python3 -m json.tool config/augment-compatibility.json >/dev/null
python3 -m json.tool config/admin-skill-modules.json >/dev/null
python3 -m json.tool config/admin-vehicles.json >/dev/null
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example -f compose.yaml -f compose.metrics.yaml config --quiet
git diff --check
```
