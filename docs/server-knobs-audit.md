# Server Knobs Audit

Audit date: 2026-05-19.

This file tracks Funcom server settings that are useful to expose in the local admin panel or Compose stack. It intentionally avoids storing local secrets.

## Exposed Now

The admin panel config editor can edit these local files:

- `config/UserEngine.ini`
- `config/UserGame.ini`
- `config/director.ini`
- `config/gateway.ini`
- `config/rabbitmq-admin.conf`
- `config/rabbitmq-game.conf`

Game server containers copy `UserEngine.ini` and `UserGame.ini` into Unreal's saved config paths at launch:

- `DuneSandbox/Saved/Config/LinuxServer/Engine.ini`
- `DuneSandbox/Saved/Config/LinuxServer/Game.ini`
- `DuneSandbox/Saved/UserSettings/UserEngine.ini`
- `DuneSandbox/Saved/UserSettings/UserGame.ini`

`DUNE_SERVER_LOGIN_PASSWORD` remains in `.env`; `scripts/run_server_safe.sh` injects it at launch so the tracked config file does not contain the live password.

The admin panel exposes `[/Script/DuneSandbox.PlayerOnlineStateSettings]` from `UserGame.ini` as Settings -> Logout and Reconnect Timers. The typed API endpoints are:

- `GET /api/settings/player-online-state`
- `POST /api/settings/player-online-state`

The admin panel also exposes a safer typed gameplay-knob layer:

- `GET /api/settings/typed-knobs`
- `POST /api/settings/typed-knobs`

Dry-runs are available by passing `dry_run=true`. Actual writes require:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_TYPED_KNOBS_ENABLED=true
```

and confirmation:

```text
WRITE TYPED KNOBS
```

Typed writes back up the target config file under `backups/admin-panel` before replacing values.

## Official User Engine Knobs

These came from the Steam server package's `scripts/setup/config/UserEngine.ini` template.

Safe candidates for admin editing:

- `Bgd.ServerDisplayName`: public server display name.
- `Dune.GlobalMiningOutputMultiplier`: global player mining output multiplier.
- `Dune.GlobalVehicleMiningOutputMultiplier`: vehicle mining output multiplier.
- `SecurityZones.PvpResourceMultiplier`: resource multiplier in PvP/security-zone contexts.
- `dw.VehicleDurabilityDamageMultiplier`: vehicle durability damage multiplier.
- `Sandstorm.Enabled`: enable or disable sandstorms.
- `Sandstorm.Treasure.Enabled`: enable or disable sandstorm treasure.
- `sandworm.dune.Enabled`: enable or disable sandworm behavior.
- `Vehicle.SandwormCollisionInteraction`: vehicle/sandworm collision behavior.
- `Sandworm.SandwormDangerZonesEnabled`: enable danger-zone behavior.
- `Vehicle.SandwormInvulnerabilitySecondsOnExit`: post-exit protection duration.
- `Vehicle.SandwormInvulnerabilitySecondsOnServerRestart`: post-restart protection duration.

Typed controls currently implemented:

- `Dune.GlobalMiningOutputMultiplier`
- `Dune.GlobalVehicleMiningOutputMultiplier`
- `SecurityZones.PvpResourceMultiplier`
- `Sandstorm.Enabled`
- `Sandstorm.Treasure.Enabled`

Sensitive:

- `Bgd.ServerLoginPassword`: use `.env` and runtime injection, not tracked config.

## Official User Game Knobs

These came from the Steam server package's `scripts/setup/config/UserGame.ini` template.

Safe candidates for admin editing:

- `m_bShouldForceEnablePvpOnAllPartitions`: force PvP across all partitions.
- `m_PvpEnabledPartitions`: explicitly enable PvP on listed partitions.
- `m_bAreSecurityZonesEnabled`: enable/disable security zones.
- `m_CostAmount` under `[/Script/DuneSandbox.CharacterRecustomizerSubsystem]`: Solaris cost for character recustomization. The local override sets this to `0`; shipped/default is `5000`.
- `UpdateRateInSeconds`: item deterioration update cadence.
- `m_bCoriolisAutoSpawnEnabled`: Coriolis storm auto-spawn behavior.
- `m_DefaultReconnectGracePeriodSeconds`: normal-map reconnect grace/logoff persistence window; set to `0` for immediate disconnect/logout expiry.
- `m_OvermapReturnGracePeriodSeconds`: overmap return grace window; set to `0` for Steam Deck suspend-friendly immediate exit.
- `m_InstancedMapReconnectGracePeriodSeconds`: instanced-map reconnect grace/logoff persistence window; set to `0` for immediate disconnect/logout expiry.
- `m_MaxNumLandclaimSegments`: landclaim segment cap.
- `DUNE_SUBFIEF_LIMIT` / `DUNE_SUBFIEF_LIMIT_BONUS`: repo-owned experimental subfief/totem count knob. Apply with `scripts/apply-subfief-limit-knob.sh .env`; it writes `DunePlayerCharacterAttributeSet.SubfiefLimitBonus` into persisted player-character actors and current `dune.player_state.player_pawn_id` actors, including blank-class pawn rows. It installs DB triggers for future actor saves and player-state pawn changes. If `DUNE_SUBFIEF_LIMIT_BONUS` is set, it wins over derived `DUNE_SUBFIEF_LIMIT - DUNE_SUBFIEF_BASE_LIMIT`. The player-presence announcer also repairs joined/rejoined players whose current pawn bonus is below the configured value when `DUNE_PLAYER_PRESENCE_SUBFIEF_BONUS_ENFORCER_ENABLED=true`. This is not a shipped INI knob and must be validated in game. Roll back DB triggers with `scripts/apply-subfief-limit-knob.sh .env rollback`.
- `DUNE_GENERATOR_FUEL_DAYS`: repo-owned DB capacity patch for fuel-powered base generators. Apply with `scripts/apply-generator-fuel-capacity-knob.sh`; it raises generator fuel inventory `max_item_volume` from the observed `100` to `288` for 60 days at 1 hour per oil, and installs triggers for future generator inventory saves. Confidence is high that the observed 20-day limit is the `max_item_volume=100` inventory cap because live generators contain up to 500 oil and `FFuelPoweredPlaceableComponent.m_FuelBurningDuration` is 3600 seconds. Confidence is moderate that raising the DB volume alone is sufficient for client refuel UI after map restart; no cooked asset override has been needed yet. Roll back DB triggers with `scripts/apply-generator-fuel-capacity-knob.sh rollback`.
- `m_LimitNumberOfBuildablesPerServer` and `m_LimitNumberOfBuildablesPerMap`: experimental binary-only total buildable/building-piece cap candidates. The current override sets both to `7500` to test raising the observed `5000` cap. Confidence is low that these are sufficient for the per-base cap because live behavior allows multiple 5000-piece bases in one Hagga Basin map. These need live validation after map restart.
- Per-base building-piece cap lead: cooked data table `/Game/Dune/Systems/Building/Data/DT_BuildableStructureCategoryData`, row/category `BuildingPiece`, with strings for `m_BuildableStructureLimitsOnServer`, `m_BuildableStructureLimitsPerMap`, `m_MaximumNumberOfBuildables`, and `m_TargetNumberOfLandclaims`. The adjacent row payload contains a literal int32 `5000` inside the `BuildingPiece` row before the `Production` row starts. Confidence is high that this asset contains the observed limit value; confidence is moderate that it is the per-base cap; confidence is low on an editable INI override until cooked asset mappings or an override mechanism are found. `scripts/patch-building-piece-limit-pak.py` patches that row to `7500` with Oodle recompression. Lab validation on `kspld0` proved the patched pak boots and reports `already-patched` in a running `survival` container; client placement beyond `5000` is still unproven without a client or a discovered placement RPC.
- Native specialization XP bonus: cooked event asset `/Game/Dune/Events/DataAssets/DA_MTXEvent_SpecializationXPBonus` exists and uses `MTXEventModifier_TrackSpecializationScaleXP`. The game server accepts startup command syntax `-ExecCmds=ScheduleMTXEvent SpecializationXPBonus 60 604800,ListMTXEvents` in lab. Confidence is high that this schedules the shipped specialization-XP event when a map starts; confidence is low that the shipped event is configurable to an arbitrary `3x` scalar without a proved `ScheduleMTXEventJson` payload, cooked asset override, or native command route. `DUNE_SERVER_STARTUP_EXECCMDS` stages startup console commands for the next game-server start only.
- `m_BuildingBlueprintMaxExtensions`: blueprint extension cap.
- `m_BaseBackupMaxExtensions`: base backup extension cap.
- `m_bBuildingRestrictionLimitsEnabled`: enable/disable building restriction limits.

Typed controls currently implemented:

- `m_bShouldForceEnablePvpOnAllPartitions`
- `m_bAreSecurityZonesEnabled`
- `m_bCoriolisAutoSpawnEnabled`
- `[/Script/DuneSandbox.SpiceHarvestingSystem] m_PerMapSystemSettings`
- `m_BuildingShelterThreshold`
- `m_PlaceableShelterThreshold`
- `ShelteredProtectionThreshold`

The typed layer deliberately excludes Coriolis cycle-start, cycle-duration, DB wipe, and cycle-end restart fields. Those are high-impact fields and should remain raw-config-only until a stronger rollback and validation workflow exists.

## Deep Desert Harvest Bonus

`config/UserEngine.deep-desert-pvp.ini` sets:

```ini
Dune.GlobalMiningOutputMultiplier=3.0
Dune.GlobalVehicleMiningOutputMultiplier=3.0
SecurityZones.PvpResourceMultiplier=1.0
```

`compose.allmaps.yaml` wires that file into only the partition-31 Deep Desert
service if it is ever started manually. The live partition-8 Deep Desert service
uses the shared `config/UserEngine.ini` values, which keep harvest at 1.0x.
Because `run_server_safe.sh` copies `DUNE_USERENGINE_CONFIG_PATH` only into that
map server process, the "global" mining values are isolated to the second DD
service. This keeps the 3x second-DD harvest bonus separate from
`SecurityZones.PvpResourceMultiplier`; PvP itself is enabled in
`config/UserGame.deep-desert-pvp.ini` with `+m_PvpEnabledPartitions=31`.

No shipped or validated INI surface currently gates mining/resource multipliers
by player level. Confidence is unknown for a level-gated harvest bonus until a
binary asset override, native command, or DB-backed gameplay hook is proven.

## Deep Desert Spice Caps

The high-confidence Deep Desert content knob is:

```ini
[/Script/DuneSandbox.SpiceHarvestingSystem]
m_PerMapSystemSettings=...
```

The typed knob id is:

```text
spiceDeepDesertCaps
```

Structured dry-run example:

```json
{
  "dry_run": true,
  "updates": {
    "spiceDeepDesertCaps": {
      "Medium": {"primed": 24, "active": 24},
      "Large": {"primed": 3, "active": 3}
    }
  }
}
```

Validation after restart:

```sql
select * from dune.spicefield_types order by map, field_kind_id;

select map,dimension_index,field_kind_id,count(*),sum(value_remaining)
from dune.resourcefield_state
group by 1,2,3
order by 1,2,3;
```

`POST /api/admin/spice-fields/inspect` returns the same high-signal state without writing.

## Director Knobs

Already exposed through `config/director.ini` or typed admin settings:

- Character transfer policy and timeouts.
- Default and per-map `PlayerHardCap`.
- `ShouldUpdatePlayerCountOnFls`.
- `ForceLock`.
- `DauCap`, `WauCap`, `HbsCap`.
- `AllowGroupTravel`.
- `ScalingResourceTarget`.
- Per-map `NumExtraServers`, `MinServers`, and `EnableAutomaticInstanceScaling` where present.
- Per-map queue fallback destination for Deep Desert.

Good next candidates for typed admin controls:

- `ForceIsWorldClosed`: deliberately close the world at Director level.
- `ForceIsWorldClosingSoon`: advertise a closing-soon state.
- `TravelRequestExpirationTimeSeconds`: travel request lifetime.
- `SettingsUpdateFrequencySeconds`: Director settings refresh cadence.
- `FlsServerSettingsUpdateFrequencySeconds`: FLS settings push cadence.
- `FlsShouldSendHeartbeat` and heartbeat frequency values.
- Per-map `AllowQueueingOnLogin`, `KeepPartiesTogether`, `MaxParties`, `QueueFailMap`, and `QueueFailLocation`.

Riskier Director controls:

- `[InstancingModes]`: changing map modes can strand travel targets unless database partitions, compose services, ports, and Director expectations all agree.
- FLS timeout/heartbeat tuning: bad values may look like auth or discovery failures.
- `ScalingResourceTarget`: Kubernetes/operator-specific semantics may not map cleanly to Compose.

## Compose Stack Knobs

Safe candidates:

- Warm-pool size by compose profile/override: minimal, nine-map, or full 30-partition pool.
- Optional resource limits via `compose.limits.example.yaml`.
- Host UDP game port ranges.
- `EXTERNAL_ADDRESS`, `WORLD_NAME`, `WORLD_UNIQUE_NAME`, and `WORLD_REGION`.
- Admin panel limits such as request body size, audit retention, item stack cap, and row limits.

Riskier candidates:

- Public RabbitMQ/database binds. Keep these local-only.
- IGW/S2S UDP forwarding. For the full warm-pool layout, `7888-7918/udp` is the paired IGW range; forward it only when the deployment's live-client routing or server-browser checks require it.
- Arbitrary map service count changes without matching `world_partition` rows.

## Reverse Proxy / Ingress

A reverse proxy is useful for admin and informational HTTP surfaces only:

- Keep `admin.example.test` or equivalent admin hostnames restricted to LAN/VPN.
- Keep the admin panel bound to `127.0.0.1:18080` on the Docker host.
- Use host allowlists and the admin token together; neither should be the only guard.
- Leave `dune.snape.tech` as an informational web response. Dune game traffic is UDP and should use direct router forwarding, not HTTP reverse proxying.

Do not proxy the game UDP path through an HTTP reverse proxy unless a separate UDP transport design is deliberately built and tested.

## Current Gaps

- `gateway` is defined in the stack but was not running during this audit. Full farm readiness has been green without it, but this should be validated against live-client travel and FLS behavior before deciding it is optional.
- Admin panel has raw config-file editing for `UserEngine.ini` and `UserGame.ini`; logout/reconnect timers and selected high-confidence gameplay knobs now have typed controls. Shelter/hydration candidates are still experimental even though they are represented in the typed layer.
- Native GM command execution remains blocked until the RabbitMQ payload route is verified by a live client.
- Journey, recipe, and vehicle unlock mutation remain blocked until safe DB functions or live examples are mapped.
- There is no automated per-map resource recommendation yet. Use `scripts/profile-runtime.sh` and `scripts/summarize-runtime-profile.sh` while testing player travel.
