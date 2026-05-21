#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/investigate-vehicle-fidelity.sh [output-file]

Collects repo-known evidence for long-range remote vehicle visual fidelity.
The report is an investigation aid only; it does not change server config.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="${1:-}"

emit_matches() {
  local title="$1"
  local file="$2"
  local pattern="$3"

  printf '## %s\n\n' "$title"
  if [[ ! -f "$repo_root/$file" ]]; then
    printf 'Missing `%s`.\n\n' "$file"
    return
  fi

  local matches
  matches="$(rg -n --no-heading "$pattern" "$repo_root/$file" || true)"
  if [[ -z "$matches" ]]; then
    printf 'No matches.\n\n'
    return
  fi

  printf '```text\n%s\n```\n\n' "$matches"
}

emit() {
  cat <<'EOF'
# Vehicle Long-Range Fidelity Investigation

This report looks for server-side evidence that could explain distant air
vehicles appearing as simplified hovering proxies instead of accurately animated
flight actors.

Confidence scale:

- high: shipped config section/key exists in the extracted index.
- moderate: binary string strongly matches the symptom but is not a validated
  config key.
- low: nearby/network/general tuning lead; useful for experiments only.

EOF

  emit_matches \
    "Confirmed Shipped Vehicle Config" \
    "SERVER_CONFIG_KEY_INDEX.md" \
    "DuneVehicleSettings|DuneVehicle\\]|Ornithopter|Vehicle.*Ability|Vehicle.*DataTable|VehicleShelter|InAirDistance"

  emit_matches \
    "Confirmed Shipped Network And LOD Config" \
    "SERVER_CONFIG_KEY_INDEX.md" \
    "GameNetworkManager|EntityLodOptimizationSettings|TerrainBlocksSubsystem|ClientNet|MAXCLIENT|NetCull|CullDistance|Replication|LongRange|LOD|StreamingDistance|Simulation.*Optimized"

  emit_matches \
    "Binary-Only Long-Distance Vehicle Proxy Leads" \
    "SERVER_BINARY_CONFIG_CANDIDATES.md" \
    "VehicleLongDistanceProxy|LongDistanceProxy|FlyingVehicleCheckUpdateRate|VehicleFlyingIcons|VehicleGroundIcons|VehicleMovement|VehicleInput|AirVehicle|Ornithopter|MaxNetCullDistanceSquared|MaxLOD"

  emit_matches \
    "Runtime Vehicle Persistence Evidence" \
    "SERVER_RUNTIME_SURFACES.md" \
    "Vehicles|vehicle|DuneVehicleSettings"

  cat <<'EOF'
## Classification

| Candidate | Evidence | Confidence | Action |
| --- | --- | --- | --- |
| `m_VehicleLongDistanceProxyActorClass` / `m_VehicleLongDistanceProxyData` | Binary-only names match the observed distant proxy symptom. | moderate | Primary research lead. Do not override until section/type/default value are known. |
| `[/Script/DuneSandbox.DuneVehicleSettings]` | Shipped section exists, but exposed keys are mostly data-table references and vehicle recovery/access values. | high for existence, low for fidelity impact | Useful for locating vehicle data assets; not a proven animation-fidelity knob. |
| `[/Script/Engine.GameNetworkManager]` movement send/update keys | Shipped Unreal movement/network keys exist. | high for existence, low for vehicle-proxy impact | Test only after proxy-distance behavior is measured. These can affect global movement behavior. |
| `[/Script/DuneSandbox.EntityLodOptimizationSettings]` | Shipped LOD optimization settings exist; default data references NPC actor settings in the visible summary. | moderate | Secondary lead. Need full default value before touching. |
| `[/Script/DuneSandbox.TerrainBlocksSubsystem]` streaming distances | Shipped world/content streaming distances exist. | moderate for existence, low for vehicle actor fidelity | Probably content streaming, not remote actor animation. Do not use as first experiment. |

## Test Protocol

Use two clients on the same map and record exact distances where the remote
vehicle representation changes.

1. Observer stands still with a clear line of sight.
2. Pilot flies an ornithopter through powered climb, powered level flight,
   glide/descent, yaw, roll, and pitch changes.
3. Capture observer video or screenshots at about 250m, 500m, 1000m, 1500m,
   2000m, and 2500m.
4. Record whether the observer sees the real mesh, long-distance proxy,
   flight-mode changes, pitch/roll/yaw, and smooth translation.
5. Repeat once with the pilot flying directly across the observer's view and
   once flying toward/away from the observer.
6. Check server logs around the transition time for actor, replication, or LOD
   messages.

A config experiment is only justified if the bad transition distance is stable
and a candidate key has section/type evidence. If the transition is cleanly tied
to the long-distance proxy names above, the likely fix is client asset/blueprint
or replicated-state work rather than this orchestration repo.

## Current Conclusion

The strongest current lead is a client/server long-distance vehicle proxy path,
not ordinary ping, routing, or Postgres/RabbitMQ behavior. Server-side config may
move the threshold if the proxy distance is configurable, but accurate glide,
powered mode, pitch, roll, and yaw at 2km likely require the client proxy to
receive and render more state.
EOF
}

if [[ -n "$output" ]]; then
  mkdir -p "$(dirname "$output")"
  emit > "$output"
  printf 'wrote vehicle fidelity report: %s\n' "$output"
else
  emit
fi
