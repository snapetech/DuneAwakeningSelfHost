#!/usr/bin/env python3
"""Summarize readiness for Dune base-cap and BRT tooling."""
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


KEYS = (
    "m_MaxLandclaimSegmentsPerMap",
    "m_MaxNumLandclaimSegments",
    "m_BuildingBlueprintMaxExtensions",
    "m_BaseBackupMaxExtensions",
    "m_StakingUnitExtensionDefaultTimes",
    "m_StakingUnitVerticalExtensionDefaultTimes",
    "m_BaseBackupToolMapRestriction",
    "m_BaseBackupToolTimeRestrictionInSeconds",
    "m_bBuildingRestrictionLimitsEnabled",
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def config_values(path: Path) -> dict:
    values: dict[str, list[str]] = {key: [] for key in KEYS}
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.lstrip("+")
        if key in values:
            values[key].append(value.strip())
    return {key: found for key, found in values.items() if found}


def first_int(values: dict, key: str) -> int | None:
    found = values.get(key) or []
    if not found:
        return None
    match = re.search(r"-?\d+", found[-1])
    return int(match.group(0)) if match else None


def has(path: str, needle: str) -> bool:
    return needle in read_text(ROOT / path)


def build_report(config: Path) -> dict:
    values = config_values(config)
    maintenance = read_text(ROOT / "docs" / "maintenance-updates.md")
    runtime_surface = read_text(ROOT / "docs" / "current-build-runtime-surface-1988751.md")
    canary_doc = read_text(ROOT / "docs" / "linux-server-loader-canary-2026-06-16.md")
    brt_doc = read_text(ROOT / "docs" / "base-reconstruction-deep-desert-ghidra.md")
    run_safe = read_text(ROOT / "scripts" / "run_server_safe.sh")
    post_start = read_text(ROOT / "scripts" / "restart-post-start-health.sh")
    subfief_patcher = read_text(ROOT / "scripts" / "patch-subfief-cap-binary.py")
    ue4ss_building_mod = read_text(ROOT / "tools" / "ue4ss-mods" / "BuildingPieceCap" / "Scripts" / "main.lua")
    ue4ss_building_compose = read_text(ROOT / "compose.ue4ss-building-piece-limit-lab.yaml")

    extension_configured = (
        first_int(values, "m_MaxNumLandclaimSegments") is not None
        and first_int(values, "m_MaxNumLandclaimSegments") > 5
    )
    extension_anchors = all(
        needle in runtime_surface or needle in brt_doc or needle in canary_doc
        for needle in ("m_MaxNumLandclaimSegments", "InsideLandclaimCanBePlaced.cpp")
    )

    return {
        "config": str(config),
        "values": values,
        "surfaces": {
            "logoffTimerRuntimePatch": {
                "status": "buildable",
                "confidence": "high",
                "evidence": [
                    "scripts/patch-logoff-timers-runtime.sh",
                    "scripts/restart-post-start-health.sh",
                    "DUNE_LOGOFF_TIMER_RUNTIME_PATCH_ENABLED",
                ],
                "enabledBy": "DUNE_LOGOFF_TIMER_RUNTIME_PATCH_ENABLED=true",
                "ready": has("scripts/restart-post-start-health.sh", "patch-logoff-timers-runtime.sh")
                and "DUNE_LOGOFF_TIMER_RUNTIME_PATCH_ENABLED" in post_start,
            },
            "subfiefTotemCap": {
                "status": "buildable",
                "confidence": "moderate-high",
                "evidence": [
                    "scripts/apply-subfief-limit-knob.sh",
                    "scripts/patch-subfief-cap-binary.py",
                    "DUNE_SUBFIEF_CAP_BINARY_TARGET=all",
                ],
                "enabledBy": "DUNE_SUBFIEF_LIMIT plus DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED=true",
                "ready": has("scripts/patch-subfief-cap-binary.py", "expected_fail_enum")
                and "DUNE_SUBFIEF_CAP_BINARY_TARGET=all" in maintenance
                and "install_subfief_cap_binary_patch" in run_safe,
            },
            "buildingPieceCaps": {
                "status": "buildable",
                "confidence": "high",
                "evidence": [
                    "scripts/patch-subfief-cap-binary.py target all",
                    "server/map building cap fail-enum verification",
                ],
                "enabledBy": "DUNE_BUILDING_PIECE_LIMIT_PATCH_ENABLED=true and DUNE_SUBFIEF_CAP_BINARY_TARGET=all",
                "ready": all(needle in subfief_patcher for needle in ("building-server", "building-map"))
                and "The live-patched binary has all five branch sites NOPed" in runtime_surface,
            },
            "ue4ssBuildingPieceCap": {
                "status": "lab-ready",
                "confidence": "moderate",
                "evidence": [
                    "tools/ue4ss-mods/BuildingPieceCap/Scripts/main.lua",
                    "compose.ue4ss-building-piece-limit-lab.yaml",
                    "DUNE_PROBE_LOADER_LUA_MOD_ROOT=/workspace/tools/ue4ss-mods",
                    "DUNE_BUILDING_PIECE_LIMIT_UE4SS_APPLY=false by default",
                ],
                "enabledBy": (
                    "compose.ue4ss-building-piece-limit-lab.yaml plus "
                    "DUNE_BUILDING_PIECE_LIMIT_UE4SS_APPLY=true only after dry-run evidence"
                ),
                "nextStep": (
                    "run the overlay on kspld0 survival, inspect "
                    "BuildingPieceCap observed/patched summary, then enable raw-set apply"
                ),
                "ready": all(
                    needle in ue4ss_building_mod
                    for needle in (
                        "DT_BuildableStructureCategoryData",
                        "m_MaximumNumberOfBuildables",
                        "DUNE_BUILDING_PIECE_LIMIT_UE4SS_APPLY",
                        "RegisterModInitCallback",
                    )
                )
                and "DUNE_PROBE_LOADER_LUA_MOD_ROOT" in run_safe
                and "DUNE_PROBE_LOADER_LUA_REFLECTION_RAW_SET_ENABLED" in run_safe
                and "DUNE_BUILDING_PIECE_LIMIT_UE4SS_APPLY" in run_safe
                and "DUNE_PROBE_LOADER_LUA_MOD_ROOT: /workspace/tools/ue4ss-mods" in ue4ss_building_compose,
            },
            "brtDeepDesertBackupRestore": {
                "status": "partially-buildable",
                "confidence": "moderate",
                "evidence": [
                    "m_BaseBackupToolMapRestriction includes DeepDesert and DeepDesert_1",
                    "m_BaseBackupMaxExtensions configured",
                    "docs/brt-deep-desert-plan.md still requires RPC-arrival trace / server-side emulation path",
                ],
                "enabledBy": "config candidate is present; full restore needs trace/emulator validation",
                "ready": "DeepDesert" in "\n".join(values.get("m_BaseBackupToolMapRestriction", []))
                and first_int(values, "m_BaseBackupMaxExtensions") is not None,
            },
            "horizontalExtensionCap": {
                "status": "needs-proof",
                "confidence": "moderate",
                "evidence": [
                    "m_MaxNumLandclaimSegments configured above 5",
                    "m_BaseBackupMaxExtensions configured",
                    "binary string anchors exist, but no cap-specific patcher exists yet",
                ],
                "nextStep": "trace/readback placement rejection, then patch the native branch if config readback still caps at 5",
                "ready": False,
                "configCandidatePresent": extension_configured,
                "anchorsPresent": extension_anchors,
            },
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config" / "UserGame.ini"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(Path(args.config))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    print(f"config: {report['config']}")
    for name, surface in report["surfaces"].items():
        print(
            f"{name}: status={surface['status']} confidence={surface['confidence']} "
            f"ready={str(surface['ready']).lower()}"
        )
        if "enabledBy" in surface:
            print(f"  enable: {surface['enabledBy']}")
        if "nextStep" in surface:
            print(f"  next: {surface['nextStep']}")


if __name__ == "__main__":
    main()
