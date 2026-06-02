# Vehicle Long-Range Fidelity

This tracks the investigation into distant air vehicles appearing as simplified
hovering icons/proxies instead of accurately animated flight actors.

## Finding

Confidence: high for a dedicated proxy system, moderate for this exact symptom.

The current repo evidence points to a long-distance vehicle proxy path. Current
production binary capture:

- capture: `captures/vehicle-fidelity-1973075/server-bin`
- build ID: `9bf5fbdef43a6d6d64459df973f3d252c01ab4ad`

The strongest current-build strings are:

- `m_VehicleLongDistanceProxyActorClass`
- `m_VehicleLongDistanceProxyData`
- `AVehicleLongDistanceProxy`
- `FVehicleLongDistanceProxyDataSerializer`
- `FVehicleLongDistanceProxyDataSerializerItem`
- `FVehicleLongDistanceProxiesServerProcessor`
- `FVehicleLongDistanceProxiesClientProcessor`
- `../../DuneSandbox/Source/DuneSandbox/Vehicle/FGL/Processors/VehicleLongDistanceProxyProcessors.cpp`

Those names match the observed symptom more closely than general networking,
map routing, database state, or RabbitMQ behavior.

The current server processor type signature reads:

- `FOwnerComponent`
- `FPositionComponent`
- `TSpatialHashMapComponent<ESpatialGroup::Vehicles>`
- `TSpatialComponent<ESpatialGroup::Vehicles>`
- `FVehicleComponent`
- `FImmediatePhysicsComponent`
- `FPlayerControllerComponent`

The current client processor reads:

- `FOwnerComponent`
- `FVehicleComponent`
- `FPlayerControllerComponent`

Confidence: high that the proxy substitution is driven by a vehicle/spatial
processor path, not only a generic render-distance setting.

Current production `pakchunk0-LinuxServer.pak` also exposes the cooked proxy
blueprint asset names:

- `DuneSandbox/Content/Dune/Systems/Vehicles/Blueprints/LongDistanceProxies/`
- `BP_LightOrnithopter_LongDistanceProxy1`
- `BP_MediumOrnithopter_LongDistanceProxy`
- `BP_TransportOrnithopter_LongDistanceProxy`
- `BP_Sandbike_LongDistanceProxy`
- `BP_Buggy_LongDistanceProxy`
- `BP_Treadwheel_LongDistanceProxy`
- `BP_Tank_LongDistanceProxy`
- `BP_Sandcrawler_LongDistanceProxy`
- `BP_ContainerVehicle_LongDistanceProxy`

Confidence: high that the proxy path exposes console variables. Confidence:
moderate that disabling the proxy path plus raising live actor cull distance is
the right first test for forcing real vehicle visuals farther out.

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
| `VehicleLongDistanceProxyProcessors.cpp` server/client processors | high | Primary current-build lead; server side uses vehicle spatial components. |
| Dune vehicle shipped settings | high for existence, low for fidelity | No direct fidelity knob found. |
| Game network movement keys | high for existence, low for proxy fix | Possible experiment after measuring transition distance. |
| `Vehicle.LongDistanceProxiesEnabled` | high | Primary test knob. Disable to remove the dedicated proxy path and see whether real vehicle actors replicate with raised cull. |
| `Vehicle.LongDistanceProxiesRange` | high | Proxy range in centimeters. Default is 200000 cm / 2000m; increasing this makes proxies reach farther, not real actors. |
| `Vehicle.LongDistanceProxiesServerTickRate` | high | Proxy server update cadence. Secondary; not the live/proxy transition distance. |
| IGW `MaxNetCullDistanceSquared` | high for existence, moderate as supporting cull test | Keep paired with proxy-disable test; alone it did not prove same-map vehicle fidelity. |
| Entity LOD optimization | moderate | Needs full default value and actor coverage. |
| Terrain streaming distances | low for vehicle animation | Likely world/content streaming, not actor flight state. |
| `m_MinimumLongRangeMovementPredictionDistance` | high for string existence, low for thopter proxy | Current string neighborhood is sandworm-related. |
| `m_FlyingVehicleCheckUpdateRate` | high for string existence, low-to-moderate for IGW flying-object checks | Current string neighborhood is `DuneIgwServerConnectionComponent.cpp`, not the vehicle proxy processor. |
| `m_NetCullDstSqrd` / `m_NetCullDistanceInMeters` | high for string existence, low for vehicle proxy | Current neighborhoods point at sandstorm/other cull paths, not the vehicle long-distance proxy processor. |

## Active Experiment

Confidence: moderate.

`config/UserEngine.deep-desert.ini` and
`config/UserEngine.deep-desert-pvp.ini` currently override:

```ini
[/Script/InfiniteGameWorlds.S2sController]
MaxNetCullDistanceSquared=400.0e8
```

The shipped value is `25.0e8`, which is about a 500m radius in Unreal
centimeters. The experimental value is about a 2000m radius.

Both Deep Desert overlays also now override:

```ini
[ConsoleVariables]
Vehicle.LongDistanceProxiesEnabled=0
```

That scope is intentional: DD#1/Casual and DD#2/Hardcore get a clean test where
the dedicated proxy path is off while the existing 2km cull experiment remains
on. If real vehicles now stay visible or animate farther out, the proxy was
masking the live actor path. If aircraft vanish instead, actor replication/cull
still needs a separate fix.

Apply it by restarting the affected map server containers so
`scripts/run_server_safe.sh` copies the service's `UserEngine` overlay into the
effective server `Engine.ini`. DD#1/Casual uses
`config/UserEngine.deep-desert.ini`; DD#2/Hardcore uses
`config/UserEngine.deep-desert-pvp.ini`.

Rollback for the proxy-disable test is removing
`Vehicle.LongDistanceProxiesEnabled=0` from
the relevant Deep Desert `UserEngine` overlay, then restarting that map server
again.
Rollback for the cull experiment is removing the whole
`[/Script/InfiniteGameWorlds.S2sController]` section from the relevant
`UserEngine` overlay.

Expected useful signal:

- Positive: DD#1/DD#2 aircraft stop becoming proxy/icon-like near the problem
  range and remain as real animated actors farther out.
- Mixed: proxy/icon is gone, but aircraft vanish beyond a distance; then the
  proxy knob worked and the next target is live actor replication/cull.
- Negative: no visible change after restart; then the client may be using a
  separate client-side proxy/LOD path.
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
Use the validated `Vehicle.LongDistanceProxies*` CVars first.

The local server image did not expose `m_VehicleLongDistanceProxyActorClass` or
`m_VehicleLongDistanceProxyData` in shipped INI files. The next implementable
server-side step is to discover whether those fields are config-backed asset
properties or hardwired blueprint/class data. If no server-readable config
property exists, the fix moves to client asset/blueprint behavior or to
replicating/rendering more remote flight state.

## Current Reverse-Engineering Notes

Confidence: moderate.

Headless Ghidra is installed at `/opt/ghidra/support/analyzeHeadless`, but a
full analysis pass on the 357 MB Linux server binary is noisy and slow because
`GccExceptionAnalyzer` floods exception-table errors. A focused script was
started at
`captures/vehicle-fidelity-1973075/ghidra-scripts/VehicleProxyXrefs.java`, but
the next useful Ghidra pass should disable or avoid GCC exception analysis and
target only the proxy processor functions/RTTI.

Local artifacts from the current pass:

- `captures/vehicle-fidelity-1973075/focused-strings.txt`
- `captures/vehicle-fidelity-1973075/focused-strings-unique.txt`
- `captures/vehicle-fidelity-1973075/all-strings.dec.txt`
- `captures/vehicle-fidelity-1973075/pakchunk0-LinuxServer.pak`
- `captures/vehicle-fidelity-1973075/pakchunk0-long-distance-proxy-files.txt`

Pak extraction is not solved yet. `unreal_pak_cli` from crates.io is a stub, and
`unpak` fails this pak with `Parse`. Plain strings still confirm the proxy
blueprint filenames in the pak index.

## Reversed Proxy Window

Confidence: high.

The current server binary registers these CVars through `FAutoConsoleVariableRef`
inside the vehicle long-distance proxy code:

- `Vehicle.LongDistanceProxiesEnabled`
- `Vehicle.LongDistanceProxiesRange`
- `Vehicle.LongDistanceProxiesServerTickRate`

The server processor maintains a long-distance proxy entry array on the owning
player/controller object at offsets `0x1780` and `0x1788`, with 64-byte entries.
The per-candidate helper at `0xf58a9d0` adds or updates proxy entries. It rejects
vehicles below `900000000` cm squared, which is a 300m floor. Cleanup in
`0xf589830` removes proxy entries below that same 300m floor or above
`Vehicle.LongDistanceProxiesRange + 10000 cm`. With the default range
`200000 cm`, proxy entries cover roughly 300m through 2100m.

This means `Vehicle.LongDistanceProxiesRange` controls how far proxies are sent,
not when live actors replace proxies. Raising it would make the simplified proxy
system reach farther. The useful test is disabling
`Vehicle.LongDistanceProxiesEnabled` while keeping a raised live cull distance.
