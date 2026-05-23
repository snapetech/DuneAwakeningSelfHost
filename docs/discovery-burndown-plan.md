# Discovery and Browser-Ping Burn-Down Plan

Evidence status: repo-side implementation complete; external/client evidence
runs still need operator action.

Current read: DASH now has a repeatable discovery pipeline that can capture
build-scoped surfaces, diff generated evidence, run fixture snapshots, create
experiment evidence directories, classify DB functions, score binary
candidates, generate asset-reference graphs, expose the ledger in the admin
Discovery tab, and keep unsafe promotions gated until runtime evidence exists.

Confidence: high.

## Goals

- Make server-surface discovery build-scoped and repeatable.
- Convert research notes into machine-readable evidence that can generate docs,
  admin catalog views, TODO queues, and promotion gates.
- Add fixture-backed runtime coverage for systems that currently have thin or
  zero live examples.
- Add one-variable experiment tooling for config and binary-candidate knobs.
- Add a non-disruptive browser-ping diagnostic path that proves whether FLS,
  Gateway metadata, game RabbitMQ, gameplay UDP, IGW UDP, Docker NAT, or TLS is
  the first failing layer.
- Keep unsafe mutation and GM/native-command expansion gated until evidence
  proves the contract.

## Burn-Down Board

| Priority | Work Item | Status | Deliverable |
| ---: | --- | --- | --- |
| P0 | Build surface ledger | implemented | `scripts/extract-build-surfaces.sh` writes `build/<image-tag>/` or a chosen output root with config, binary, DB, RMQ, log, score, graph, and queue artifacts |
| P0 | Research build-tag validation | implemented | `make validate-research-build-tags` fails on unmarked stale build research |
| P0 | Browser ping diagnostics | implemented | `scripts/browser-ping-diagnostics.sh` and `scripts/watch-browser-probe.sh` are read-only |
| P0 | Fail-closed admin example defaults | implemented | `.env.example` mutation and item-grant gates default to `false` |
| P1 | Machine-readable surface ledger | implemented | `research/schema/surface.schema.json` and `research/surfaces/*.jsonl` |
| P1 | Generated surface docs | implemented | `scripts/generate-surface-docs.py` renders/validates ledger Markdown |
| P1 | Binary candidate scoring | implemented | `scripts/score-binary-candidates.py` tiers candidates A-D |
| P1 | DB function classifier | implemented | `DB_FUNCTION_SURFACE_INDEX.md` and `DB_FUNCTION_COVERAGE_MATRIX.md` are generated from DB surface JSON |
| P1 | Runtime fixture runner | implemented | `scripts/fixture-runner.py` plus fixtures for vehicle, guild, landclaim, respawn, marker, Exchange, resource mining, and Deep Desert cycle |
| P2 | Knob experiment harness | implemented | `scripts/knob-experiment.py` and `experiments/catalog/dd-large-spice-cap-3.json` emit before/after evidence artifacts |
| P2 | RMQ capture/diff harness | implemented | `scripts/capture-rmq-window.sh` and `scripts/diff-rmq-captures.py` produce before/after topology diffs |
| P2 | Asset-reference graph | implemented | `scripts/build-asset-reference-graph.py` generates JSON/Markdown graphs |
| P2 | Log signature mining | implemented | `scripts/research/index-server-logs.py` feeds build ledgers and experiment evidence |
| P3 | Admin discovery pages | implemented | Admin `Discovery` tab reads the JSONL ledger and build ledger list |

Remaining external evidence runs:

- Browser-ping packet capture while an external client refreshes the server
  browser.
- Real in-game admin/client action capture for the native GM command envelope.
- Client-driven fixtures for guild, vehicle, landclaim, marker, Exchange order,
  resource mining, and respawn-location transitions.

Implemented entry points:

```bash
make validate-research-build-tags
make surface-ledger
make surface-ledger-markdown
make discovery-queue
make binary-candidate-scores STRINGS_FILE=build/1968181-0-shipping/binary-strings.txt SCORE_FLAGS='--format markdown'
make asset-reference-graph GRAPH_PATHS='build/1968181-0-shipping/server-configs.txt build/1968181-0-shipping/binary-strings.txt' GRAPH_FLAGS='--format markdown'
make extract-build-surfaces ENV_FILE=.env SERVICE=deep-desert OUT_ROOT=build
make diff-build-surfaces OLD_BUILD=build/1963158-0-shipping NEW_BUILD=build/1968181-0-shipping
make db-function-classifier DB_SURFACE_JSON=build/1968181-0-shipping/pg-surface.json CLASSIFIER_FLAGS='--format markdown'
make fixture-runner FIXTURE=fixtures/vehicle-create-basic.json ENV_FILE=.env FIXTURE_FLAGS='--phase before'
make knob-experiment CATALOG=experiments/catalog/dd-large-spice-cap-3.json ENV_FILE=.env
make capture-rmq-window ENV_FILE=.env SECONDS=120 TAG=admin-login-attempt
make diff-rmq-captures RMQ_BEFORE=captures/rmq/<id>/admin-before.json RMQ_AFTER=captures/rmq/<id>/admin-after.json
make browser-ping-diagnostics ENV_FILE=.env
sudo make watch-browser-probe ENV_FILE=.env SECONDS=120
```

## Build-Scoped Evidence Pipeline

Create a generated build ledger:

```text
build/
  1963158-0-shipping/
    DefaultGame.ini.index.json
    binary-strings.json
    pg-schema.sql
    pg-procs.json
    rabbitmq-topology.json
    route-captures/
    log-signatures.json
  1968181-0-shipping/
    ...
  diff-1963158-to-1968181.md
```

Every research file that depends on shipped behavior must declare:

```text
Evidence build: <image-tag>
Validated against live stack: yes/no
Last regeneration command: <command>
```

Validation rule:

```bash
make validate-research-build-tags
```

The check should compare `.env.example DUNE_IMAGE_TAG` against generated indexes
and docs that cite shipped behavior. If a doc remains useful but stale, mark it
as archived/stale instead of letting it silently pass.

## Evidence Ledger Model

Create `research/surfaces/*.jsonl` as the source of truth, with records like:

```json
{"id":"ini.SpiceHarvestingSystem.m_PerMapSystemSettings","build":"1968181-0-shipping","surface":"ini","section":"/Script/DuneSandbox.SpiceHarvestingSystem","key":"m_PerMapSystemSettings","evidence":["DefaultGame.ini","DB:spicefield_types","DB:resourcefield_state"],"confidence":"high","risk":"medium","restartRequired":true,"validated":true}
```

Required fields:

- `id`
- `build`
- `surface`
- `evidence`
- `confidence`
- `risk`
- `validated`
- `lastValidatedBuild`

Promotion fields for typed/admin knobs:

- `parseVerified`
- `runtimeEffectVerified`
- `requiresClientConfig`
- `rollbackTested`
- `fixtureCoverage`
- `promoteToTypedKnob`

Markdown research docs should be generated from this ledger where practical.
The admin catalog should consume the same ledger instead of drifting into a
separate hand-curated truth source.

## Runtime Fixtures

Problem: several runtime conclusions are schema/proc-based because live samples
are thin. Current known thin spots include vehicles, vehicle modules, guilds,
static encounters, shifting sands, and landclaim segments.

Add controlled fixtures:

```text
fixtures/
  01-baseline-empty-world.yaml
  02-create-guild.yaml
  03-place-base-and-segments.yaml
  04-place-vehicle.yaml
  05-mine-resource-node.yaml
  06-trigger-respawn-location.yaml
  07-create-marker.yaml
  08-create-exchange-order.yaml
  09-enter-deep-desert-and-wait-cycle.yaml
```

Each fixture captures:

- schema and selected row counts
- selected table diffs
- admin/game RabbitMQ topology
- container logs since fixture start
- network listeners
- active partitions and farm state

Outputs:

```text
research/fixtures/<fixture-id>.before.json
research/fixtures/<fixture-id>.after.json
research/fixtures/<fixture-id>.diff.md
research/fixtures/<fixture-id>.verdict.json
```

Acceptance: each fixture either proves a row/state transition or records that
the system remains unobserved with exact missing evidence.

## Binary Candidate Scoring

Binary strings are leads, not proof. Add scoring to reduce noise:

```text
+5 appears with _Key companion
+5 appears near known config class name
+4 appears near UDeveloperSettings / UGameInstanceSubsystem / UWorldSubsystem
+4 appears in shipped DefaultGame.ini nearby section
+3 scalar/control shape: m_b*, *Multiplier, *Rate, *Seconds, *Limit, *Enabled, *Chance
+3 appears in logs when subsystem initializes
+2 has DB table/proc with same noun
-5 asset/UI/widget/material/camera/audio naming
-4 component-only/runtime object naming
-4 transient actor instance naming
```

Output tiers:

- Tier A: likely config-loadable
- Tier B: likely runtime command/property
- Tier C: likely asset/data-table field
- Tier D: likely UI/client/noise

High-value candidates to force to the top for investigation:

- `m_TreasureSpawnRateMinMax`
- `m_CrashSitePriorityOverrides`
- `m_MaxLandclaimSegmentsPerMap`
- `m_BuildableStructureLimitsPerMap`
- `m_bShouldRespawnResources`
- `m_DefaultRespawnTimeInSec`

## Experiment Harness

Add:

```text
scripts/knob-experiment.py
experiments/catalog/*.yaml
```

Minimum run artifacts:

```text
experiments/<timestamp>-<id>/
  before.ini
  after.ini
  before-db.json
  after-db.json
  logs.txt
  summary.md
  verdict.json
```

Verdict shape:

```json
{"effectObserved":true,"confidence":"moderate","restartRequired":true,"sideEffects":["none observed"],"promoteToTypedKnob":false}
```

First experiment targets:

- Deep Desert medium/large spice caps.
- `m_PrimeRateInSeconds`, separate from caps.
- Encounter polling cadence, explicitly broad/random and not shipwreck-specific.
- Buried treasure commands/counting before treasure-spawn-rate config candidates.

Do not promote a knob from candidate to visible UI control unless startup parse,
runtime effect, and rollback behavior are recorded.

## Browser-Ping Diagnostics

Current read: server-browser ping is probably not derived from local
`farm_state` alone. Local `30/30` health can be green while browser ping is
blank if FLS/browser cannot validate the advertised public endpoint or if
Gateway/Director metadata is stale/incomplete.

Ranked suspects:

| Rank | Suspect | Confidence |
| ---: | --- | --- |
| 1 | Public game-RabbitMQ endpoint, cert, or host mismatch | moderate-high |
| 2 | Gateway stale/hardcoded identity versus env | moderate |
| 3 | Missing gameplay/IGW UDP forwards | moderate |
| 4 | Env changed but Gateway/Director/TextRouter containers were not recreated | moderate |
| 5 | FLS/Director metadata update not happening | low-moderate |
| 6 | Docker bridge/neighbour issue | low-moderate |

Add `scripts/browser-ping-diagnostics.sh` as a read-only report:

- `.env` identity: `WORLD_UNIQUE_NAME`, `WORLD_NAME`, `WORLD_REGION`,
  `WORLD_DATACENTER_ID`, `EXTERNAL_ADDRESS`, `GAME_RMQ_PUBLIC_HOST`,
  `GAME_RMQ_PUBLIC_PORT`, `DUNE_FLS_ENV`.
- `config/gateway.ini`: `OnlineSubsystem.ServerName`,
  `OnlineSubsystem.DatacenterId`, `[gateway].display_name`.
- rendered Compose: Gateway `--RMQGameHostname/Port`,
  `HOST_DATACENTER_IP_ADDRESS`, game `-ExternalAddress`, UDP/TCP publishes.
- running container reality: `docker inspect` env/cmd for Gateway, Director,
  TextRouter, game-rmq, and Survival.
- cert check: `scripts/check-rabbitmq-cert-sans.sh .env`.
- local listeners: TCP `31982`, UDP gameplay `7777-7810`, IGW `7888-7918`.
- Docker NAT/firewall counters for the same ports.
- DB advertised addresses from `dune.farm_state`.
- recent Gateway/Director/TextRouter FLS-ish logs.

Add `scripts/watch-browser-probe.sh .env <seconds>`:

- runs `tcpdump` for TCP game RabbitMQ plus gameplay/IGW UDP ranges;
- snapshots iptables/nft counters before/after;
- operator refreshes the server browser from an external client during the
  capture window.

Interpretation rules:

- no packets: FLS/browser did not receive or use a reachable endpoint;
- TCP `31982` only: focus on game-RMQ host, TLS, cert, Gateway advertisement;
- UDP arrives: check router forwards, Docker counters, MultiHome/IGW bind, and
  replies;
- host packets but no Docker counters: host firewall/NAT path;
- Docker counters rise but no response: container bind/service behavior;
- responses leave host but browser stays blank: return NAT or client-side
  interpretation.

Do not blindly change `EXTERNAL_ADDRESS`, `GAME_RMQ_PUBLIC_HOST`,
`gateway.ini`, `director.ini`, `DUNE_FORCE_PRIVATE_IGW_BIND_ADDRESS`,
`DUNE_DISABLE_MULTIHOME`, router forwards, or RabbitMQ TLS files before this
evidence identifies the first failing layer.

## Specific Research Tracks

### Resource Respawn

Do not add guessed keys such as `m_DefaultRespawnTimeInSec` until the owner
class/section is mapped.

Next experiment:

1. Mine one known ordinary node.
2. Capture actor name/class and logs.
3. Snapshot `actor_spawners`, `actor_spawner_actors`, and resource-related rows.
4. Watch readiness transition.
5. Restart map.
6. Compare spawned actor count and readiness.

Win condition is classification:

- persisted DB state;
- transient actor state;
- data-asset controlled;
- hardcoded/runtime subsystem controlled.

### Deep Desert / Spice / Events

- Treat spice caps as the strongest current knob class.
- Test medium/large caps through the experiment harness.
- Test prime rate separately from caps.
- Treat shipwreck and encounter cadence as broad encounter tuning until proven
  shipwreck-specific.
- For buried treasure, test native count/spawn commands before testing inferred
  spawn-rate config.

### GM / Native Command Route

Stop expanding visible GM wrappers until the payload route is solved.

Next useful evidence:

- real client/admin action capture;
- known-good chat/director/travel payload capture;
- structural diff against failed GM/native-command attempts;
- auth/session/player-controller binding check.

Only keep testing low-impact commands such as `PrintPos` and
`PrintAllowedCommands` until the route returns a real response.

## Admin Discovery UI

After the ledger, fixtures, and experiment harness exist, add admin pages:

```text
Discovery -> Build Diff
Discovery -> Candidate Queue
Discovery -> Experiment Runs
Discovery -> Evidence Ledger
Discovery -> Promotion Queue
```

Promotion flow:

```text
binary candidate
  -> startup parse probe
  -> one-map experiment
  -> DB/log/runtime effect
  -> rollback test
  -> typed knob PR
```

## Highest ROI Next 10 Tasks

1. Regenerate all config, binary, DB, RMQ, and runtime indexes for
   `1968181-0-shipping`.
2. Add build-tag validation to `make validate`.
3. Add read-only browser-ping diagnostics and browser-probe watcher scripts.
4. Flip `.env.example` mutation and item-grant defaults to fail-closed.
5. Create machine-readable `research/surfaces/*.jsonl`.
6. Generate Markdown docs from the ledger.
7. Add `scripts/knob-experiment.py`.
8. Run first automated Deep Desert medium/large spice-cap experiment.
9. Add fixture snapshots for vehicle, guild, landclaim, respawn, marker, and
   Exchange order.
10. Add DB function coverage matrix and RMQ capture/diff harness.
