#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-stimulus-plan/v1"


LOADER_DRY_RUN_ENVS = (
    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL",
)

GUARDED_OPERATION_SCRIPTS = (
    "scripts/ue4ss-package-remote-trace.sh",
    "scripts/start-map-with-post-hooks.sh",
    "scripts/recover-map.sh",
)


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def resolve_loader_path(path):
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    packaged = Path("src/dune_server_probe_loader.c")
    if packaged.is_file():
        return packaged
    return candidate


def loader_gates(path):
    loader_path = resolve_loader_path(path)
    text = read_text(loader_path)
    return {
        "path": str(loader_path),
        "hasPackageDryRunGate": "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN" in text,
        "hasNativeInvokeOptIn": "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE" in text,
        "hasFinalNativeCallGate": "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL" in text,
        "requiresExistingTargetAnchor": "lua_load_asset_backend_package_target_image" in text,
        "nativeCallRequiresTarget": bool(
            re.search(r"call_frame_ready\s*=.*target\s*!=\s*0", text, re.DOTALL)
        ),
    }


def script_capabilities(paths=None):
    paths = GUARDED_OPERATION_SCRIPTS if paths is None else paths
    capabilities = {}
    for path in paths:
        candidate = Path(path)
        text = candidate.read_text(encoding="utf-8", errors="replace") if candidate.is_file() else ""
        capabilities[str(path)] = {
            "present": candidate.is_file(),
            "executable": candidate.is_file() and candidate.stat().st_mode & 0o111 != 0,
            "hasZeroPlayerGuard": "require_zero_players" in text and "connected_players" in text,
            "hasProductionHostGuard": "DUNE_PRODUCTION_HOSTNAME" in text or "kspls0" in text,
            "runsPostStartHooks": "restart-post-start-health.sh" in text,
            "runsLogoffTimerDryRun": "patch-logoff-timers-runtime.sh" in text and "--dry-run" in text,
        }
    return capabilities


def capability_for(capabilities, script_name):
    for path, row in capabilities.items():
        if Path(path).name == script_name:
            return row
    return {}


def build_plan(loader_path):
    gates = loader_gates(loader_path)
    capabilities = script_capabilities()
    remote_trace = capability_for(capabilities, "ue4ss-package-remote-trace.sh")
    guarded_map_start = capability_for(capabilities, "start-map-with-post-hooks.sh")
    guarded_map_recover = capability_for(capabilities, "recover-map.sh")
    loader_only_safe = all(
        gates[key]
        for key in (
            "hasPackageDryRunGate",
            "hasNativeInvokeOptIn",
            "hasFinalNativeCallGate",
            "requiresExistingTargetAnchor",
            "nativeCallRequiresTarget",
        )
    )
    candidates = [
        {
            "id": "loader-package-dry-run",
            "kind": "loader-api",
            "safe": True,
            "promotableStimulus": False,
            "reason": "exercises loader package readiness gates but cannot invoke target package loading while the target anchor is missing",
            "env": {LOADER_DRY_RUN_ENVS[0]: "1"},
        },
        {
            "id": "operator-client-map-entry",
            "kind": "client-server-reachability-probe",
            "safe": "requires-operator-selection",
            "promotableStimulus": True,
            "rank": 1,
            "reason": "a controlled client login, travel, or map-entry action is the lowest-blast-radius way to determine whether package/class loading reaches the server naturally; if it does not, the fallback is server-side replay of the equivalent call path",
            "constraints": [
                "zero connected players on target partition",
                "operator controls the only client/session used as stimulus",
                "remote trace preflight and arm must pass the zero-player guard before the action",
                "no production database/admin mutation is part of the stimulus",
                "if the trace proves the normal request does not reach a usable server-side path, recover the call frame and replay/spoof that call server-side instead of requiring client file modification",
            ],
            "evidence": {
                "remoteTraceHasZeroPlayerGuard": bool(remote_trace.get("hasZeroPlayerGuard")),
            },
        },
        {
            "id": "server-side-client-call-emulation",
            "kind": "server-side-emulation",
            "safe": "requires-captured-call-frame",
            "promotableStimulus": True,
            "rank": 2,
            "reason": "once the classification probe shows the normal request does not reach a usable server-side path, spoof the equivalent call on the server from captured arguments/registers so client modification is not a port requirement",
            "constraints": [
                "requires reviewed live call-frame evidence for the requested path",
                "requires SysV x86_64 argument/register review before native invocation",
                "must remain behind non-invoking canary and final native-call gates",
                "no local Steam/Dune client file mutation",
            ],
            "evidence": {
                "requiresPackageHitEvidence": True,
            },
        },
        {
            "id": "operator-natural-package-load",
            "kind": "game-action",
            "safe": "requires-operator-selection",
            "promotableStimulus": True,
            "rank": 3,
            "reason": "generic operator-selected server action that naturally loads a package/class when no lower-blast-radius client map-entry stimulus is available",
            "constraints": [
                "zero connected players on target partition",
                "operator must identify the exact in-game or server-side action before arming trace",
                "no production mutation from kspld0",
                "unique trace log and verified gdb detach",
            ],
            "evidence": {
                "remoteTraceHasZeroPlayerGuard": bool(remote_trace.get("hasZeroPlayerGuard")),
            },
        },
        {
            "id": "guarded-map-recreate",
            "kind": "guarded-restart",
            "safe": "last-resort",
            "promotableStimulus": True,
            "rank": 4,
            "reason": "map process start/recreate should naturally exercise package/class loading, but it has higher operational blast radius than client map entry",
            "constraints": [
                "run only on kspls0 for live production target",
                "zero connected players on target partition",
                "avoid map restart unless the operational restart scripts and post-hooks are used",
                "use start-map-with-post-hooks.sh or recover-map.sh, not raw docker compose start/restart/up",
                "verify restart-post-start-health hooks and logoff timer dry-run after start",
            ],
            "evidence": {
                "startMapWrapperPresent": bool(guarded_map_start.get("present")),
                "startMapWrapperHasProductionHostGuard": bool(guarded_map_start.get("hasProductionHostGuard")),
                "startMapWrapperRunsPostStartHooks": bool(guarded_map_start.get("runsPostStartHooks")),
                "startMapWrapperRunsLogoffTimerDryRun": bool(guarded_map_start.get("runsLogoffTimerDryRun")),
                "recoverMapWrapperPresent": bool(guarded_map_recover.get("present")),
                "recoverMapRunsPostStartHooks": bool(guarded_map_recover.get("runsPostStartHooks")),
            },
        },
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "loaderGates": gates,
        "operationScriptCapabilities": capabilities,
        "loaderOnlyStimulusCanHitTargetPackageLoad": False,
        "loaderOnlyStimulusSafe": loader_only_safe,
        "candidates": candidates,
        "recommendedCandidate": "operator-client-map-entry",
        "originClassification": {
            "status": "unknown",
            "probeCandidate": "operator-client-map-entry",
            "serverSideFallbackCandidate": "server-side-client-call-emulation",
            "decision": "trace first; classify whether the normal request reaches a usable server-side path; if it does not, recover and replay/spoof the equivalent call server-side",
        },
        "nextStep": "classify whether the package-load path reaches a usable server-side branch by tracing the approved login/travel/map-entry action; if it does not, recover the call frame and replay/spoof it server-side",
    }


def markdown(plan):
    lines = ["# UE4SS Package Stimulus Plan", ""]
    lines.append(f"- Loader-only stimulus can hit target package load: `{str(plan['loaderOnlyStimulusCanHitTargetPackageLoad']).lower()}`")
    lines.append(f"- Loader-only stimulus safe: `{str(plan['loaderOnlyStimulusSafe']).lower()}`")
    lines.append(f"- Recommended candidate: `{plan['recommendedCandidate']}`")
    classification = plan.get("originClassification", {}) or {}
    if classification:
        lines.append(f"- Origin/reachability classification: `{classification.get('status', '')}`")
        lines.append(f"- Server-side fallback: `{classification.get('serverSideFallbackCandidate', '')}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in plan["candidates"]:
        lines.append(
            f"- `{row['id']}` kind=`{row['kind']}` safe=`{row['safe']}` "
            f"promotableStimulus=`{str(row['promotableStimulus']).lower()}`"
        )
        lines.append(f"  - reason: {row['reason']}")
    lines.append("")
    lines.append(f"Next step: {plan['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan safe package-load stimulus for UE4SS live call-frame tracing.")
    parser.add_argument("--loader", default="tools/linux-server-loader/dune_server_probe_loader.c")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    plan = build_plan(args.loader)
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
