#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READINESS_SCRIPT = ROOT / "scripts" / "ue4ss-port-readiness.py"

FEATURES = (
    {
        "id": "runtime-anchors",
        "title": "Runtime UE Anchors",
        "ready": ("targetImageProcess", "runtimeRootDiscovery", "runtimeRootValidation", "targetObjectDiscovery"),
        "required": (
            "anchorGroupProvenance",
            "targetImageProcess",
            "runtimeRootDiscovery",
            "runtimeRootValidation",
            "targetObjectDiscovery",
            "anchorCoverageObjectDiscovery",
        ),
    },
    {
        "id": "object-registry",
        "title": "Object Registry And FindObject",
        "ready": ("objectDiscoveryCoverage", "findObjectSemantics"),
        "required": (
            "luaObjectRegistryRuntime",
            "luaFunctionRegistryRuntime",
            "luaDecodedObjectAliasesRuntime",
            "ueObjectArrayShape",
            "ueObjectArrayRegistryRuntime",
            "ueObjectNativeIdentities",
            "ueObjectInternalFlags",
            "ueFNameDecoder",
            "luaObjectOuterChainIdentities",
            "luaObjectApi",
            "luaFunctionIterationRuntime",
        ),
    },
    {
        "id": "reflection",
        "title": "Reflection And FProperty",
        "ready": ("reflection",),
        "required": (
            "ueReflectionProbe",
            "ueReflectionFieldWalk",
            "ueReflectionPropertyDescriptors",
            "ueReflectionPropertyDescriptorsRuntime",
            "ueFunctionParamDescriptors",
            "ueFunctionIdentities",
            "ueFunctionNativeIdentities",
            "ueFunctionFlags",
            "ueReflectionPropertyValuesRuntime",
            "luaFunctionRegistryRuntime",
            "luaReflectionForEachPropertyRuntime",
            "luaReflectionLiveDescriptorTypedClassRuntime",
            "luaReflectionLiveDescriptorTypedValuesRuntime",
            "luaReflectionLiveDescriptorTypedSetValuesRuntime",
            "luaReflectionLiveDescriptorValuesRuntime",
        ),
    },
    {
        "id": "process-event-hooks",
        "title": "ProcessEvent And CallFunction Hook Dispatch",
        "ready": ("targetHooks",),
        "required": (
            "ueProcessEventHookRuntimeTarget",
            "ueProcessEventLiveHookRuntimeTarget",
            "ueProcessEventLiveLuaDispatch",
            "ueProcessEventLiveFunctionPath",
            "ueProcessEventLiveRuntimeContext",
            "ueProcessEventLiveRegistryContext",
            "ueProcessEventLiveRuntimeRegistryContext",
            "ueProcessEventLiveParamValues",
            "ueProcessEventLiveRawParamValues",
            "ueProcessEventLiveContainerParamValues",
            "ueProcessEventLiveArrayContainerParamValues",
            "ueProcessEventLiveSetContainerParamValues",
            "ueProcessEventLiveMapContainerParamValues",
            "ueProcessEventLiveSetMapContainerParamValues",
            "ueProcessEventLiveContainerDataSamples",
            "ueProcessEventLuaContextHandles",
            "ueProcessEventLuaParamAccessors",
            "ueProcessEventLiveClassAwareParamValues",
            "ueProcessEventFunctionParamMethod",
            "ueProcessEventFunctionParamLookupMethod",
            "ueProcessEventFunctionParamIterationMethod",
            "ueProcessEventContainerAliasMethods",
            "ueProcessEventContainerStorageLayoutMethods",
            "ueProcessEventLuaScalarParamAccessors",
            "ueProcessEventLuaNameStringParamAccessors",
            "ueProcessEventLuaStructParamAccessors",
            "ueProcessEventLuaEnumParamAccessors",
            "ueProcessEventLuaObjectParamAccessors",
            "ueProcessEventLuaBoolParamAccessors",
            "ueProcessEventLuaHookRouting",
            "ueProcessEventLuaHookAliasRouting",
            "ueCallFunctionHookRuntimeTarget",
            "ueCallFunctionLiveHookRuntimeTarget",
            "ueCallFunctionLiveLuaDispatch",
        ),
    },
    {
        "id": "lua-mod-dispatch",
        "title": "Lua Mod Dispatch",
        "ready": ("luaDispatch",),
        "required": (
            "luaRuntime",
            "luaMods",
            "luaSchedulerApiMods",
            "luaInputCommandApiMods",
            "luaObjectApi",
            "luaFunctionIterationRuntime",
            "luaProcessEventCompat",
            "luaProcessEventBridgeState",
            "luaProcessEventNativeInvoke",
            "luaProcessEventNativeInvokeDescriptorPreflight",
            "luaProcessEventParamsBuffer",
            "ueProcessEventLiveLuaDispatch",
            "ueCallFunctionLiveLuaDispatch",
        ),
    },
    {
        "id": "package-loading",
        "title": "Package Loading And LoadAsset",
        "ready": ("luaLoadAssetPackage", "targetPackageLoadingSurface"),
        "required": (
            "targetPackageLoadingSurface",
            "anchorCoveragePackageLoading",
            "luaLoadAssetPackageAbiState",
            "luaLoadAssetPackageStringBridge",
            "luaLoadAssetPackageNativeBuffer",
            "luaLoadAssetPackageTCharBuffer",
            "luaLoadAssetPackageTCharVerification",
            "luaLoadAssetPackageCallFrame",
            "luaLoadAssetPackageCallFrameVerification",
            "luaLoadAssetPackageCrashGuard",
            "luaLoadAssetPackageGuardedCall",
            "luaLoadAssetPackageReturnValidation",
            "luaLoadAssetPackageNativeCallAdapter",
            "luaLoadAssetPackageInvocationDescriptor",
            "luaLoadAssetPackageNativeExecutor",
            "luaLoadAssetPackage",
        ),
    },
    {
        "id": "complete-ue4ss-lua-api",
        "title": "Complete UE4SS Lua API",
        "ready": ("ue4ssLuaApiComplete",),
        "required": (
            "liveTargetImageCanary",
            "ue4ssLuaApiComplete",
        ),
    },
)
FEATURE_STAGE_HINTS = {
    "runtime-anchors": {
        "stage": "object-discovery",
        "maxStage": "read-only",
        "reason": "recover target-image FNamePool/GUObjectArray/GWorld/dispatch anchors before hook work",
    },
    "object-registry": {
        "stage": "object-discovery",
        "maxStage": "read-only",
        "reason": "prove runtime UObject/object-array registry and FName decoding before reflection or hooks",
    },
    "reflection": {
        "stage": "reflection",
        "maxStage": "read-only",
        "reason": "walk runtime class/property/function descriptors without installing hooks",
    },
    "process-event-hooks": {
        "stage": "process-event-hooks",
        "maxStage": "live-hook",
        "reason": "install only guarded runtime ProcessEvent/CallFunction hook probes after reflection is ready",
    },
    "lua-mod-dispatch": {
        "stage": "lua-dispatch",
        "maxStage": "lua-dispatch",
        "reason": "arm Lua dispatch only after runtime hooks and live params evidence are ready",
    },
    "package-loading": {
        "stage": "package-loading",
        "maxStage": "read-only",
        "reason": "recover package-loading anchors and ABI/call-frame evidence before native LoadAsset invocation",
    },
    "complete-ue4ss-lua-api": {
        "stage": "completion-contract",
        "maxStage": "lua-dispatch",
        "reason": "rerun full strict contract after all runtime target-image groups are ready",
    },
}
PLATFORM_PLANNER_COMMANDS = {
    "server": (
        "scripts/plan-ue4ss-canary-env.py",
        "--platform",
        "server",
        "--server-log",
        "/tmp/dune-server-probe-loader.log",
    ),
    "linux-client": (
        "scripts/plan-ue4ss-canary-env.py",
        "--platform",
        "linux-client",
        "--client-log",
        "/tmp/dune-client-probe-loader.log",
    ),
    "windows": (
        "scripts/plan-ue4ss-canary-env.py",
        "--platform",
        "windows",
        "--client-log",
        "/tmp/dune-win-client-probe-loader.log",
        "--loader",
        "win-client",
    ),
}
FEATURE_CANDIDATE_GROUPS = {
    "runtime-anchors": ("names", "objects", "world"),
    "object-registry": ("names", "objects", "world"),
    "reflection": ("reflection",),
    "process-event-hooks": ("dispatch",),
    "lua-mod-dispatch": ("dispatch", "reflection"),
    "package-loading": ("package",),
}
LIVE_CONTRACT_GROUP_FEATURES = {
    "targetImageAnchors": "runtime-anchors",
    "runtimePackageLoading": "package-loading",
    "runtimeObjectRegistry": "object-registry",
    "runtimeReflection": "reflection",
    "runtimeProcessEventDispatch": "process-event-hooks",
    "runtimeCallFunctionDispatch": "process-event-hooks",
}
LIVE_CONTRACT_GROUP_ORDER = tuple(LIVE_CONTRACT_GROUP_FEATURES)
REFLECTION_RUNTIME_GROUPS = (
    (
        "propertyDescriptors",
        "runtime class field and property descriptor discovery",
        (
            "ueReflectionProbe",
            "ueReflectionFieldWalk",
            "ueReflectionPropertyDescriptors",
            "ueReflectionPropertyDescriptorsRuntime",
        ),
    ),
    (
        "functionDescriptors",
        "runtime UFunction params, path identity, native identity, and flags",
        (
            "ueFunctionParamDescriptors",
            "ueFunctionParamContainerChildren",
            "ueFunctionIdentities",
            "ueFunctionNativeIdentities",
            "ueFunctionFlags",
        ),
    ),
    (
        "propertyValues",
        "runtime reflected property value reads",
        (
            "ueReflectionPropertyValuesRuntime",
        ),
    ),
    (
        "luaReflectionBridge",
        "Lua reflection iteration and typed descriptor access",
        (
            "luaFunctionRegistryRuntime",
            "luaFunctionIterationRuntime",
            "luaReflectionForEachPropertyRuntime",
            "luaReflectionLiveDescriptorTypedClassRuntime",
            "luaReflectionLiveDescriptorTypedValuesRuntime",
            "luaReflectionLiveDescriptorTypedSetValuesRuntime",
            "luaReflectionLiveDescriptorValuesRuntime",
        ),
    ),
)
PROCESS_EVENT_RUNTIME_GROUPS = (
    (
        "hookTargets",
        "guarded hook target installation",
        (
            "ueProcessEventHookRuntimeTarget",
            "ueProcessEventLiveHookRuntimeTarget",
        ),
    ),
    (
        "liveFunctionContext",
        "live UObject/UFunction path and registry context",
        (
            "ueProcessEventLiveFunctionPath",
            "ueProcessEventLiveRuntimeContext",
            "ueProcessEventLiveRegistryContext",
            "ueProcessEventLiveRuntimeRegistryContext",
        ),
    ),
    (
        "paramDecoding",
        "descriptor-backed ProcessEvent param decoding",
        (
            "ueProcessEventLiveParamValues",
            "ueProcessEventLiveRawParamValues",
            "ueProcessEventLiveContainerParamValues",
            "ueProcessEventLiveArrayContainerParamValues",
            "ueProcessEventLiveSetContainerParamValues",
            "ueProcessEventLiveMapContainerParamValues",
            "ueProcessEventLiveSetMapContainerParamValues",
            "ueProcessEventLiveContainerDataSamples",
            "ueProcessEventLiveClassAwareParamValues",
        ),
    ),
    (
        "luaBridge",
        "Lua hook context, param accessors, and routing",
        (
            "ueProcessEventLiveLuaDispatch",
            "ueProcessEventLuaContextHandles",
            "ueProcessEventLuaParamAccessors",
            "ueProcessEventFunctionParamMethod",
            "ueProcessEventFunctionParamLookupMethod",
            "ueProcessEventFunctionParamIterationMethod",
            "ueProcessEventContainerAliasMethods",
            "ueProcessEventContainerStorageLayoutMethods",
            "ueProcessEventLuaScalarParamAccessors",
            "ueProcessEventLuaNameStringParamAccessors",
            "ueProcessEventLuaStructParamAccessors",
            "ueProcessEventLuaEnumParamAccessors",
            "ueProcessEventLuaObjectParamAccessors",
            "ueProcessEventLuaBoolParamAccessors",
            "ueProcessEventLuaHookRouting",
            "ueProcessEventLuaHookAliasRouting",
        ),
    ),
)
LUA_DISPATCH_RUNTIME_GROUPS = (
    (
        "modRuntime",
        "Lua runtime, mod lifecycle, scheduler, input, and object APIs",
        (
            "luaRuntime",
            "luaMods",
            "luaSchedulerApiMods",
            "luaInputCommandApiMods",
            "luaObjectApi",
            "luaFunctionIterationRuntime",
        ),
    ),
    (
        "processEventBridge",
        "Lua ProcessEvent compatibility, params buffer, and native invoke bridge",
        (
            "luaProcessEventCompat",
            "luaProcessEventBridgeState",
            "luaProcessEventNativeInvoke",
            "luaProcessEventNativeInvokeDescriptorPreflight",
            "luaProcessEventParamsBuffer",
            "ueProcessEventLiveLuaDispatch",
            "ueCallFunctionLiveLuaDispatch",
        ),
    ),
)
KEY_BLOCKER_HINTS = {
    "luaLoadAssetPackageNativeExecutor": (
        "package native executor must report NativeExecutorReady=true, "
        "ExecutorPreflightPassed=true, and FinalNativeCallEligible=true in the "
        "target image; dry-run executor shape evidence is diagnostic only"
    ),
}


def import_readiness():
    spec = importlib.util.spec_from_file_location("ue4ss_port_readiness_for_gap_summary", READINESS_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {READINESS_SCRIPT}")
    spec.loader.exec_module(module)
    return module


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def build_readiness(args):
    if args.readiness_json:
        return load_json(args.readiness_json)
    readiness = import_readiness()
    log_paths = args.log + args.client_log + args.server_log
    if not log_paths:
        raise SystemExit("provide --readiness-json, --log, --client-log, or --server-log")
    summaries = [
        readiness.summarize_log(path, args.loader, args.pid, args.exe_substring)
        for path in log_paths
    ]
    validations = [load_json(path) for path in args.signature_validation_json]
    anchor_coverages = [load_json(path) for path in args.anchor_coverage_json]
    return readiness.build_report(summaries, validations, anchor_coverages)


def gate_lookup(report):
    return {item.get("name"): item for item in report.get("gates", [])}


def kebab_to_ready_key(name):
    parts = name.split("-")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def ready_value(report, key):
    ready = report.get("ready", {})
    if key in ready:
        return bool(ready[key])
    return bool(ready.get(kebab_to_ready_key(key), False))


def evidence_for_key(report, gates, key):
    if key in KEY_BLOCKER_HINTS and not ready_value(report, key):
        return "", KEY_BLOCKER_HINTS[key]
    if key in gates:
        gate = gates[key]
        return gate.get("evidence", ""), gate.get("blocker", "")
    camel = kebab_to_ready_key(key)
    for gate_name, gate in gates.items():
        if kebab_to_ready_key(gate_name) == camel:
            return gate.get("evidence", ""), gate.get("blocker", "")
    live_contract = report.get("liveTargetImageCanaryContract", {})
    if isinstance(live_contract, dict) and key in live_contract.get("missingKeys", []):
        return "", "missing from live target-image canary contract"
    return "", ""


def feature_row(report, feature):
    gates = gate_lookup(report)
    ready_keys = feature["ready"]
    required = feature["required"]
    ready_passed = [key for key in ready_keys if ready_value(report, key)]
    missing_ready = [key for key in ready_keys if not ready_value(report, key)]
    missing_required = [key for key in required if not ready_value(report, key)]
    blockers = []
    for key in missing_required:
        evidence, blocker = evidence_for_key(report, gates, key)
        blockers.append({"key": key, "evidence": evidence, "blocker": blocker})
    status = "ready" if not missing_ready and not missing_required else "blocked"
    if ready_passed and (missing_ready or missing_required):
        status = "partial"
    return {
        "id": feature["id"],
        "title": feature["title"],
        "status": status,
        "readyKeys": list(ready_keys),
        "requiredKeys": list(required),
        "passedReadyKeys": ready_passed,
        "missingReadyKeys": missing_ready,
        "missingRequiredKeys": missing_required,
        "blockers": blockers,
    }


def summarize_key_group(report, name, title, keys):
    gates = gate_lookup(report)
    missing = [key for key in keys if not ready_value(report, key)]
    blockers = []
    for key in missing:
        evidence, blocker = evidence_for_key(report, gates, key)
        blockers.append({"key": key, "evidence": evidence, "blocker": blocker})
    return {
        "name": name,
        "title": title,
        "ready": not missing,
        "requiredKeys": list(keys),
        "missingKeys": missing,
        "blockers": blockers,
    }


def summarize_process_event_runtime_evidence(report):
    groups = {
        name: summarize_key_group(report, name, title, keys)
        for name, title, keys in PROCESS_EVENT_RUNTIME_GROUPS
    }
    return summarize_group_rows(groups)


def summarize_reflection_runtime_evidence(report):
    groups = {
        name: summarize_key_group(report, name, title, keys)
        for name, title, keys in REFLECTION_RUNTIME_GROUPS
    }
    return summarize_group_rows(groups)


def summarize_lua_dispatch_runtime_evidence(report):
    groups = {
        name: summarize_key_group(report, name, title, keys)
        for name, title, keys in LUA_DISPATCH_RUNTIME_GROUPS
    }
    return summarize_group_rows(groups)


def summarize_group_rows(groups):
    missing_keys = []
    first_blocked_group = ""
    for name, group in groups.items():
        if group["missingKeys"] and not first_blocked_group:
            first_blocked_group = name
        missing_keys.extend(group["missingKeys"])
    return {
        "ready": not missing_keys,
        "firstBlockedGroup": first_blocked_group,
        "missingKeys": missing_keys,
        "groups": groups,
    }


def summarize_candidate_plans(plans):
    rows = []
    aggregate_missing = set()
    aggregate_ready = set()
    aggregate_counts = {}
    aggregate_sources = {"candidate": set(), "shape": set(), "outcome": set()}
    filtered = {"candidate": 0, "shape": 0, "outcome": 0}
    for plan in plans:
        contract = plan.get("nextCanaryContract", {}) or {}
        root = contract.get("rootRecoveryCandidateInput", {}) or {}
        carry = contract.get("runtimeCandidateCarryForward", {}) or {}
        if not root.get("provided") and not carry.get("provided"):
            continue
        missing = list(root.get("missingGroups", []) or [])
        coverage = root.get("groupCoverage", {}) or {}
        carry_coverage = carry.get("groupCoverage", {}) or {}
        for group_name, group in carry_coverage.items():
            if group.get("ready"):
                aggregate_ready.add(group_name)
            else:
                aggregate_missing.add(group_name)
        for group_name, group in coverage.items():
            if group.get("ready"):
                aggregate_ready.add(group_name)
            else:
                aggregate_missing.add(group_name)
        for group in missing:
            aggregate_missing.add(group)
        for name, count in (root.get("anchorCounts", {}) or {}).items():
            aggregate_counts[name] = aggregate_counts.get(name, 0) + int(count or 0)
        for name, count in (carry.get("anchorCounts", {}) or {}).items():
            aggregate_counts[name] = aggregate_counts.get(name, 0) + int(count or 0)
        aggregate_sources["candidate"].update(root.get("sourcePaths", []) or [])
        aggregate_sources["shape"].update(root.get("shapeSourcePaths", []) or [])
        aggregate_sources["outcome"].update(root.get("outcomeSourcePaths", []) or [])
        filtered["candidate"] += int(
            root.get("filteredRejectedCandidateCount", root.get("filteredRejectedShapeCount", 0)) or 0
        )
        filtered["shape"] += int(root.get("filteredRejectedShapeOnlyCount", root.get("filteredRejectedShapeCount", 0)) or 0)
        filtered["outcome"] += int(root.get("filteredRejectedOutcomeCount", 0) or 0)
        rows.append(
            {
                "platform": plan.get("platform", ""),
                "loader": plan.get("loader", ""),
                "selectedStage": plan.get("selectedStage", ""),
                "envName": root.get("envName", ""),
                "candidateCount": int(root.get("candidateCount", 0) or 0),
                "emittedCount": int(root.get("emittedCount", 0) or 0),
                "filteredRejectedShapeCount": int(root.get("filteredRejectedShapeCount", 0) or 0),
                "filteredRejectedCandidateCount": int(
                    root.get("filteredRejectedCandidateCount", root.get("filteredRejectedShapeCount", 0)) or 0
                ),
                "filteredRejectedShapeOnlyCount": int(
                    root.get("filteredRejectedShapeOnlyCount", root.get("filteredRejectedShapeCount", 0)) or 0
                ),
                "filteredRejectedOutcomeCount": int(root.get("filteredRejectedOutcomeCount", 0) or 0),
                "runtimeCarryForwardEntryCount": int(carry.get("entryCount", 0) or 0),
                "runtimeCarryForwardEntries": list(carry.get("entries", []) or []),
                "sourceAnchorPresets": list(root.get("sourceAnchorPresets", []) or []),
                "sourcePaths": list(root.get("sourcePaths", []) or []),
                "shapeSourcePaths": list(root.get("shapeSourcePaths", []) or []),
                "outcomeSourcePaths": list(root.get("outcomeSourcePaths", []) or []),
                "anchorCounts": dict(root.get("anchorCounts", {}) or {}),
                "missingGroups": missing,
                "groupCoverage": coverage,
                "blockerCodes": list((contract.get("blockerCodes", []) or plan.get("blockers", [])) or []),
            }
        )
    aggregate_missing.difference_update(aggregate_ready)
    return {
        "provided": bool(rows),
        "plans": rows,
        "readyGroups": sorted(aggregate_ready),
        "missingGroups": sorted(aggregate_missing),
        "anchorCounts": dict(sorted(aggregate_counts.items())),
        "sourcePaths": {
            "candidate": sorted(aggregate_sources["candidate"]),
            "shape": sorted(aggregate_sources["shape"]),
            "outcome": sorted(aggregate_sources["outcome"]),
        },
        "filteredRejectedCandidateCount": filtered["candidate"],
        "filteredRejectedShapeOnlyCount": filtered["shape"],
        "filteredRejectedOutcomeCount": filtered["outcome"],
    }


def summarize_live_target_image_contract(report):
    contract = report.get("liveTargetImageCanaryContract") or {}
    groups = contract.get("groups", {}) if isinstance(contract, dict) else {}
    summarized_groups = {}
    for group_name in LIVE_CONTRACT_GROUP_ORDER:
        group = groups.get(group_name, {}) if isinstance(groups, dict) else {}
        missing = list(group.get("missingKeys", []) or [])
        summarized_groups[group_name] = {
            "ready": bool(group.get("ready", False)) if group else False,
            "feature": LIVE_CONTRACT_GROUP_FEATURES[group_name],
            "requiredKeys": list(group.get("requiredKeys", []) or []),
            "missingKeys": missing,
        }
    for group_name, group in sorted(groups.items() if isinstance(groups, dict) else []):
        if group_name in summarized_groups:
            continue
        summarized_groups[group_name] = {
            "ready": bool(group.get("ready", False)),
            "feature": "",
            "requiredKeys": list(group.get("requiredKeys", []) or []),
            "missingKeys": list(group.get("missingKeys", []) or []),
        }
    missing_all = list(contract.get("missingKeys", []) or []) if isinstance(contract, dict) else []
    first_blocked_group = next(
        (
            group_name
            for group_name in LIVE_CONTRACT_GROUP_ORDER
            if summarized_groups.get(group_name, {}).get("missingKeys")
        ),
        "",
    )
    return {
        "ready": bool(contract.get("ready", False)) if isinstance(contract, dict) else False,
        "missingKeys": missing_all,
        "firstBlockedGroup": first_blocked_group,
        "firstBlockedFeature": LIVE_CONTRACT_GROUP_FEATURES.get(first_blocked_group, ""),
        "groups": summarized_groups,
    }


def runtime_candidate_locations(report, limit=8):
    discovery = report.get("runtimeDiscovery") or report.get("ueRuntimeDiscovery") or {}
    locations = discovery.get("candidateLocations") or []
    return [
        {
            "name": row.get("name", ""),
            "addr": row.get("addr", ""),
            "imageOffset": row.get("imageOffset", ""),
            "fileOffset": row.get("fileOffset", ""),
            "map": row.get("map", ""),
            "perms": row.get("perms", ""),
        }
        for row in locations[:limit]
    ]


def summarize(report, candidate_plans=None, candidate_outcome_paths=None):
    candidate_outcome_paths = [str(path) for path in (candidate_outcome_paths or [])]
    features = [feature_row(report, feature) for feature in FEATURES]
    status_counts = {}
    for feature in features:
        status_counts[feature["status"]] = status_counts.get(feature["status"], 0) + 1
    per_loader = {}
    for loader, entry in sorted((report.get("perLoaderReadiness") or {}).items()):
        per_loader[loader] = summarize({**entry, "perLoaderReadiness": {}})
    live_contract = summarize_live_target_image_contract(report)
    next_canary = next_canary_recommendation(features, live_contract, report, candidate_outcome_paths)
    candidate_coverage = summarize_candidate_plans(candidate_plans or [])
    reflection_evidence = summarize_reflection_runtime_evidence(report)
    process_event_evidence = summarize_process_event_runtime_evidence(report)
    lua_dispatch_evidence = summarize_lua_dispatch_runtime_evidence(report)
    for feature in features:
        required_groups = FEATURE_CANDIDATE_GROUPS.get(feature["id"], ())
        feature["candidateMissingGroups"] = [
            group for group in required_groups
            if group in candidate_coverage.get("missingGroups", [])
        ]
    return {
        "schemaVersion": "dune-ue4ss-port-gap-summary/v1",
        "ready": bool(report.get("ready", {}).get("ue4ssLuaApiComplete", False)),
        "statusCounts": dict(sorted(status_counts.items())),
        "features": features,
        "nextCanaryRecommendation": next_canary,
        "nextSteps": report.get("nextSteps", []),
        "liveTargetImageMissingKeys": live_contract.get("missingKeys", []),
        "liveTargetImageContract": live_contract,
        "reflectionRuntimeEvidence": reflection_evidence,
        "processEventRuntimeEvidence": process_event_evidence,
        "luaDispatchRuntimeEvidence": lua_dispatch_evidence,
        "rootRecoveryCandidateCoverage": candidate_coverage,
        "candidateOutcomeInputs": candidate_outcome_paths,
        "perLoader": per_loader,
    }


def planner_command(platform, max_stage, candidate_outcome_paths=None):
    base = list(PLATFORM_PLANNER_COMMANDS[platform])
    for path in candidate_outcome_paths or []:
        base += ["--candidate-outcomes-json", str(path)]
    return base + ["--max-stage", max_stage, "--format", "json"]


def next_canary_recommendation(features, live_contract=None, report=None, candidate_outcome_paths=None):
    feature_by_id = {feature["id"]: feature for feature in features}
    first_blocked = None
    contract_feature = (live_contract or {}).get("firstBlockedFeature", "")
    if contract_feature:
        first_blocked = feature_by_id.get(contract_feature)
    if first_blocked is None or first_blocked["status"] == "ready":
        first_blocked = next((feature for feature in features if feature["status"] != "ready"), None)
    if not first_blocked:
        return {
            "needed": False,
            "feature": "",
            "stage": "none",
            "maxStage": "",
            "reason": "all tracked UE4SS parity features are ready",
            "plannerCommands": {},
        }
    hint = FEATURE_STAGE_HINTS[first_blocked["id"]]
    first_blocked_group = (live_contract or {}).get("firstBlockedGroup", "")
    recommendation = {
        "needed": True,
        "feature": first_blocked["id"],
        "stage": hint["stage"],
        "maxStage": hint["maxStage"],
        "reason": hint["reason"],
        "liveTargetImageContractGroup": first_blocked_group,
        "missingReadyKeys": first_blocked["missingReadyKeys"],
        "missingRequiredKeys": first_blocked["missingRequiredKeys"],
        "plannerCommands": {
            platform: planner_command(platform, hint["maxStage"], candidate_outcome_paths)
            for platform in ("server", "linux-client", "windows")
        },
    }
    if candidate_outcome_paths:
        recommendation["candidateOutcomeInputs"] = [str(path) for path in candidate_outcome_paths]
    if report and first_blocked["id"] == "runtime-anchors":
        recommendation["runtimeRootCandidateLocations"] = runtime_candidate_locations(report)
    return recommendation


def append_runtime_evidence_section(lines, title, evidence):
    groups = evidence.get("groups", {}) if isinstance(evidence, dict) else {}
    if not groups:
        return
    lines.append("")
    lines.append(f"## {title}")
    lines.append("")
    lines.append(
        f"- ready=`{str(evidence.get('ready', False)).lower()}` "
        f"firstBlocked=`{evidence.get('firstBlockedGroup', '') or 'none'}`"
    )
    for group_name, group in groups.items():
        missing_group_keys = group.get("missingKeys", [])
        lines.append(
            f"- `{group_name}` ready=`{str(group.get('ready', False)).lower()}` "
            f"missing=`{', '.join(missing_group_keys) if missing_group_keys else 'none'}`"
        )
        for blocker in group.get("blockers", [])[:4]:
            detail = blocker.get("blocker") or blocker.get("evidence")
            if detail:
                lines.append(f"  - `{blocker['key']}`: {detail}")


def markdown(summary):
    lines = ["# UE4SS Port Gap Summary", ""]
    lines.append(f"- Complete UE4SS Lua API: `{str(summary['ready']).lower()}`")
    lines.append(f"- Status counts: `{summary['statusCounts']}`")
    missing = summary.get("liveTargetImageMissingKeys") or []
    lines.append(f"- Live target-image missing keys: `{', '.join(missing) if missing else 'none'}`")
    if summary.get("candidateOutcomeInputs"):
        lines.append(f"- Candidate outcome inputs: `{', '.join(summary.get('candidateOutcomeInputs', []))}`")
    live_contract = summary.get("liveTargetImageContract", {})
    first_group = live_contract.get("firstBlockedGroup") if isinstance(live_contract, dict) else ""
    if first_group:
        lines.append(f"- First blocked live target-image group: `{first_group}`")
    recommendation = summary.get("nextCanaryRecommendation", {})
    if recommendation:
        lines.append(f"- Recommended next stage: `{recommendation.get('stage', '')}`")
        lines.append(f"- Recommended max stage: `{recommendation.get('maxStage', '')}`")
        lines.append(f"- Recommended feature: `{recommendation.get('feature', '')}`")
        candidate_locations = recommendation.get("runtimeRootCandidateLocations") or []
        if candidate_locations:
            rendered_locations = [
                f"{row.get('name', 'candidate')}@{row.get('addr', '?')} offset={row.get('imageOffset', '?')} image={row.get('map', '?')}"
                for row in candidate_locations[:6]
            ]
            lines.append(f"- Runtime root candidates: `{'; '.join(rendered_locations)}`")
    lines.append("")
    lines.append("## Features")
    lines.append("")
    for feature in summary["features"]:
        lines.append(f"- `{feature['status']}` `{feature['id']}` {feature['title']}")
        if feature.get("candidateMissingGroups"):
            lines.append(f"  - candidate missing groups: `{', '.join(feature['candidateMissingGroups'])}`")
        if feature["missingRequiredKeys"]:
            lines.append(f"  - missing: `{', '.join(feature['missingRequiredKeys'])}`")
            for blocker in feature["blockers"][:8]:
                detail = blocker.get("blocker") or blocker.get("evidence")
                if detail:
                    lines.append(f"  - `{blocker['key']}`: {detail}")
    if isinstance(live_contract, dict) and live_contract.get("groups"):
        lines.append("")
        lines.append("## Live Target-Image Contract")
        lines.append("")
        for group_name, group in live_contract["groups"].items():
            missing_group_keys = group.get("missingKeys", [])
            lines.append(
                f"- `{group_name}` ready=`{str(group.get('ready', False)).lower()}` "
                f"feature=`{group.get('feature', '') or 'unmapped'}` "
                f"missing=`{', '.join(missing_group_keys) if missing_group_keys else 'none'}`"
            )
    append_runtime_evidence_section(lines, "Reflection Runtime Evidence", summary.get("reflectionRuntimeEvidence", {}))
    append_runtime_evidence_section(lines, "ProcessEvent Runtime Evidence", summary.get("processEventRuntimeEvidence", {}))
    append_runtime_evidence_section(lines, "Lua Dispatch Runtime Evidence", summary.get("luaDispatchRuntimeEvidence", {}))
    candidate_coverage = summary.get("rootRecoveryCandidateCoverage", {})
    if candidate_coverage.get("provided"):
        lines.append("")
        lines.append("## Root-Recovery Candidate Coverage")
        lines.append("")
        lines.append(f"- Ready groups: `{', '.join(candidate_coverage.get('readyGroups', [])) or 'none'}`")
        lines.append(f"- Missing groups: `{', '.join(candidate_coverage.get('missingGroups', [])) or 'none'}`")
        lines.append(f"- Anchor counts: `{candidate_coverage.get('anchorCounts', {})}`")
        lines.append(
            "- Filtered rejected candidates: "
            f"`total={candidate_coverage.get('filteredRejectedCandidateCount', 0)} "
            f"shape={candidate_coverage.get('filteredRejectedShapeOnlyCount', 0)} "
            f"outcome={candidate_coverage.get('filteredRejectedOutcomeCount', 0)}`"
        )
        sources = candidate_coverage.get("sourcePaths", {}) or {}
        if sources.get("outcome"):
            lines.append(f"- Live outcome sources: `{', '.join(sources.get('outcome', []))}`")
        for plan in candidate_coverage.get("plans", []):
            lines.append(
                f"- `{plan.get('platform') or 'unknown'}` stage=`{plan.get('selectedStage', '')}` "
                f"emitted=`{plan.get('emittedCount', 0)}` "
                f"filteredOutcome=`{plan.get('filteredRejectedOutcomeCount', 0)}` "
                f"runtimeCarry=`{plan.get('runtimeCarryForwardEntryCount', 0)}` "
                f"missing=`{', '.join(plan.get('missingGroups', [])) or 'none'}`"
            )
            if plan.get("runtimeCarryForwardEntries"):
                lines.append(
                    f"  - runtime carry-forward: `{'; '.join(plan.get('runtimeCarryForwardEntries', []))}`"
                )
    if summary.get("perLoader"):
        lines.append("")
        lines.append("## Per Loader")
        lines.append("")
        for loader, entry in sorted(summary["perLoader"].items()):
            lines.append(
                f"- `{loader}` complete=`{str(entry['ready']).lower()}` "
                f"statusCounts=`{entry['statusCounts']}`"
            )
    if recommendation and recommendation.get("plannerCommands"):
        lines.append("")
        lines.append("## Planner Commands")
        lines.append("")
        for platform, command in sorted(recommendation["plannerCommands"].items()):
            lines.append(f"- `{platform}`: `{' '.join(command)}`")
    lines.append("")
    lines.append("## Next Steps")
    lines.append("")
    for step in summary.get("nextSteps", [])[:8]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize remaining UE4SS feature-parity gaps from readiness evidence.")
    parser.add_argument("--readiness-json", type=Path)
    parser.add_argument("--client-log", type=Path, action="append", default=[])
    parser.add_argument("--server-log", type=Path, action="append", default=[])
    parser.add_argument("--log", type=Path, action="append", default=[])
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--signature-validation-json", type=Path, action="append", default=[])
    parser.add_argument("--anchor-coverage-json", type=Path, action="append", default=[])
    parser.add_argument("--canary-plan-json", type=Path, action="append", default=[])
    parser.add_argument(
        "--candidate-outcomes-json",
        type=Path,
        action="append",
        default=[],
        help="JSON from summarize-ue-candidate-outcomes.py; paths are threaded into recommended planner commands",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    candidate_plans = [load_json(path) for path in args.canary_plan_json]
    summary = summarize(build_readiness(args), candidate_plans, args.candidate_outcomes_json)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
