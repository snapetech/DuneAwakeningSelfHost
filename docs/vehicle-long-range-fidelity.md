# Vehicle Long-Range Fidelity

This tracks the investigation into distant air vehicles appearing as simplified
hovering icons/proxies instead of accurately animated flight actors.

## Finding

Confidence: moderate.

The current repo evidence points to a long-distance vehicle proxy path. The
strongest binary-only strings are:

- `m_VehicleLongDistanceProxyActorClass`
- `m_VehicleLongDistanceProxyData`

Those names match the observed symptom more closely than general networking,
map routing, database state, or RabbitMQ behavior.

Local image inspection of `registry.funcom.com/funcom/self-hosting/seabass-server:1963158-0-shipping`
also found shipped PAK paths for vehicle long-distance proxies:

- `DuneSandbox/Content/Dune/Systems/Vehicles/Blueprints/LongDistanceProxies/`
- `BP_LightOrnithopter_LongDistanceProxy`
- `BP_MediumOrnithopter_LongDistanceProxy`
- `BP_TransportOrnithopter_LongDistanceProxy`
- `DuneSandbox/Content/Dune/Vehicles/FlyingVehicles/Ornithopter/ChoamFaction/*/Mesh/ProxyMeshes/`

Confidence: high that a dedicated long-distance proxy asset path exists.
Confidence: low that it is tunable by a known server INI key.

## Confirmed Config Evidence

Confidence: high for existence, low for direct animation impact.

`[/Script/DuneSandbox.DuneVehicleSettings]` exists in the shipped config index,
but the visible keys are mostly vehicle data-table references, access/recovery
settings, and `m_OrnithopterInAirDistanceToGround`. None is a validated
long-range animation-fidelity knob.

`[/Script/DuneSandbox.DuneVehicle]` exists, but the visible keys are
`s_RecentlyDrivenTime`, `s_CombatRatingScalar`, and
`m_VehicleShelterThreshold`. None is a validated distant-flight-state knob.

`[/Script/Engine.GameNetworkManager]` includes standard movement/network timing
keys. These are real shipped config keys, but they are global and risky to tune
without proving that the observed defect is caused by update cadence rather than
proxy substitution.

`[/Script/DuneSandbox.EntityLodOptimizationSettings]` exists and may matter, but
the indexed `DefaultSettings` summary visibly references NPC actor LOD settings.
It is a secondary lead until the full value and actor coverage are known.

`[/Script/InfiniteGameWorlds.S2sController]` in the local server image has
`MaxNetCullDistanceSquared=25.0e8`. Confidence: high for existence, low for this
symptom. This is an IGW/server-to-server cull setting, not a proven same-map
remote vehicle animation fidelity control.

## Candidate Classification

| Candidate | Confidence | Current status |
| --- | --- | --- |
| Vehicle long-distance proxy binary strings and PAK assets | high for existence, moderate for symptom match | Primary lead; no validated server override found. |
| Dune vehicle shipped settings | high for existence, low for fidelity | No direct fidelity knob found. |
| Game network movement keys | high for existence, low for proxy fix | Possible experiment after measuring transition distance. |
| IGW `MaxNetCullDistanceSquared` | high for existence, low for same-map proxy fix | Do not tune first; likely server-to-server relevance. |
| Entity LOD optimization | moderate | Needs full default value and actor coverage. |
| Terrain streaming distances | low for vehicle animation | Likely world/content streaming, not actor flight state. |

## Active Experiment

Confidence: low.

`config/UserEngine.ini` now overrides:

```ini
[/Script/InfiniteGameWorlds.S2sController]
MaxNetCullDistanceSquared=400.0e8
```

The shipped value is `25.0e8`, which is about a 500m radius in Unreal
centimeters. The experimental value is about a 2000m radius. This is the
smallest confirmed-config experiment that plausibly touches the observed
distance band.

Apply it by restarting the affected map server containers so
`scripts/run_server_safe.sh` copies `config/UserEngine.ini` into the effective
server `Engine.ini`.

Rollback is removing the whole `[/Script/InfiniteGameWorlds.S2sController]`
section from `config/UserEngine.ini`, then restarting the affected map server
containers again.

Expected useful signal:

- Positive: distant aircraft stop becoming proxy-like near the problem range,
  or the bad transition moves farther away.
- Negative: no visible change after restart.
- Bad: higher CPU/bandwidth, worse actor pop, map handoff issues, or server log
  warnings/errors around S2S/IGW culling.

## Live Test

Confidence: high that this test separates proxy behavior from ordinary lag.

Use two clients on the same map.

1. Put the observer still on high ground with a clear line of sight.
2. Fly an ornithopter through powered climb, powered level flight, glide/descent,
   yaw, roll, and pitch changes.
3. Record observer video or screenshots near 250m, 500m, 1000m, 1500m, 2000m,
   and 2500m.
4. For each distance, note whether the observer sees real mesh, proxy/icon,
   flight mode, pitch, roll, yaw, and smooth translation.
5. Repeat once crossing the observer's view and once flying toward/away from the
   observer.
6. Check server logs for actor, replication, LOD, or proxy messages around the
   transition point.

Use this worksheet for the observer:

| Distance | Real mesh? | Proxy/icon? | Powered/glide visible? | Pitch/roll/yaw visible? | Smooth translation? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 250m |  |  |  |  |  |  |
| 500m |  |  |  |  |  |  |
| 1000m |  |  |  |  |  |  |
| 1500m |  |  |  |  |  |  |
| 2000m |  |  |  |  |  |  |
| 2500m |  |  |  |  |  |  |

Record the first distance where the proxy appears and the last distance where
the real flight attitude is still visible. That pair determines whether the next
experiment should target a distance threshold or the proxy asset behavior.

## Tooling

Generate a fresh local evidence report:

```bash
./scripts/investigate-vehicle-fidelity.sh captures/vehicle-fidelity.md
```

The report writes only derived text from tracked evidence files. `captures/` is
ignored so local test notes and screenshots stay out of release artifacts.

## Implementation Boundary

Confidence: moderate.

Do not add unvalidated overrides for `m_VehicleLongDistanceProxyActorClass`,
`m_VehicleLongDistanceProxyData`, or `MaxLOD*` yet. Those names are binary-only
leads, not validated `UserGame.ini` keys with known sections and value shapes.
`MaxNetCullDistanceSquared` is now the one active confirmed-config experiment,
but confidence remains low that it controls same-map vehicle proxy visuals.

The local server image did not expose `m_VehicleLongDistanceProxyActorClass` or
`m_VehicleLongDistanceProxyData` in shipped INI files. The next implementable
server-side step is to discover whether those fields are config-backed asset
properties or hardwired blueprint/class data. If no server-readable config
property exists, the fix moves to client asset/blueprint behavior or to
replicating/rendering more remote flight state.
