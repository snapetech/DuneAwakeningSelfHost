#!/usr/bin/env python3
import argparse
import importlib.util
import json
import shlex
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READINESS_SCRIPT = ROOT / "scripts" / "ue4ss-port-readiness.py"
READINESS_SCHEMA_VERSION = "dune-ue4ss-port-readiness/v1"
PACKAGE_NEXT_ACTION_SCHEMA_VERSION = "dune-ue4ss-package-next-action/v1"
CANARY_PLAN_SCHEMA_VERSION = "dune-ue4ss-canary-env-plan/v1"
LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS = "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256"
LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_SCHEMA = "dune-ue4ss-package-live-stimulus-review-summary/v1"
LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS = (
    "reviewBundleVerification,reviewBundleVerificationSha256,"
    "routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,"
    "prearmReadinessVerification,prearmReadinessVerificationSha256"
)
LIVE_TRACE_RUNBOOK_PREARM_READINESS_JSON = "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json"
LIVE_TRACE_RUNBOOK_PREARM_READINESS_MARKDOWN = "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.md"
LIVE_TRACE_RUNBOOK_REQUIRED_CLEANUP_ANCHORS = (
    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject",
    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadObject",
)
LIVE_TRACE_RUNBOOK_TRACE_LOG_PREFIX = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-"
LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE = (
    "preflight",
    "arm",
    "operator-client-login-travel-map-entry",
    "status",
    "cleanupCommand",
    "no-debugger-check",
)

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
            "luaStaticConstructObjectNativeExecutorState",
            "luaStaticConstructObjectNativeExecutorReady",
            "luaStaticConstructObjectNativeInvoke",
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
            "ueProcessEventActiveValidation",
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
            "ueCallFunctionActiveValidation",
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
            "luaProcessEventNativeExecutorState",
            "luaProcessEventNativeInvokeNonSelfTestGate",
            "luaProcessEventNativeInvokeNonSelfTestInvoked",
            "luaCallFunctionNativeInvoke",
            "luaCallFunctionNativeInvokePreflight",
            "luaCallFunctionNativeExecutorState",
            "luaCallFunctionNativeInvokeNonSelfTestGate",
            "luaCallFunctionNativeInvokeNonSelfTestInvoked",
            "luaProcessEventParamsBuffer",
            "ueProcessEventLiveLuaDispatch",
            "ueCallFunctionLiveLuaDispatch",
        ),
    },
    {
        "id": "package-loading",
        "title": "Package Loading And LoadAsset",
        "ready": (
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
            "luaLoadAssetPackageNativeInvocation",
            "luaLoadAssetPackage",
            "luaLoadClassPackageAbiState",
            "luaLoadClassPackageCallFrameVerification",
            "luaLoadClassPackageNativeExecutor",
            "luaLoadClassPackageNativeInvocation",
        ),
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
            "luaLoadAssetPackageNativeInvocation",
            "luaLoadAssetPackage",
            "luaLoadClassPackageAbiState",
            "luaLoadClassPackageCallFrameVerification",
            "luaLoadClassPackageNativeExecutor",
            "luaLoadClassPackageNativeInvocation",
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
        "guarded hook target installation and active call validation",
        (
            "ueProcessEventHookRuntimeTarget",
            "ueProcessEventLiveHookRuntimeTarget",
            "ueProcessEventActiveValidation",
            "ueCallFunctionHookRuntimeTarget",
            "ueCallFunctionLiveHookRuntimeTarget",
            "ueCallFunctionActiveValidation",
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
            "luaProcessEventNativeExecutorState",
            "luaProcessEventNativeInvokeNonSelfTestGate",
            "luaProcessEventNativeInvokeNonSelfTestInvoked",
            "luaCallFunctionNativeInvoke",
            "luaCallFunctionNativeInvokePreflight",
            "luaCallFunctionNativeExecutorState",
            "luaCallFunctionNativeInvokeNonSelfTestGate",
            "luaCallFunctionNativeInvokeNonSelfTestInvoked",
            "luaProcessEventParamsBuffer",
            "ueProcessEventLiveLuaDispatch",
            "ueCallFunctionLiveLuaDispatch",
        ),
    ),
)
KEY_BLOCKER_HINTS = {
    "reflection": (
        "reflection remains incomplete until both native runtime FProperty "
        "descriptor/value evidence and Lua typed descriptor get/set runtime "
        "proof are simultaneously ready"
    ),
    "targetHooks": (
        "target hook readiness requires ProcessEvent and "
        "CallFunctionByNameWithArguments hook installs against target-image "
        "runtime anchors, not only self-test hook scaffolds"
    ),
    "luaDispatch": (
        "Lua dispatch readiness requires mod entrypoints plus ProcessEvent, "
        "CallFunctionByNameWithArguments, scheduler/input, object, reflection, "
        "and lifecycle surfaces to pass their runtime gates"
    ),
    "targetImageProcess": (
        "scoped logs did not include a configured target executable or module; "
        "rerun the canary against the real game/server process or pass "
        "--exe-substring for this title"
    ),
    "runtimeRootDiscovery": (
        "runtime root discovery must identify target-image FNamePool, "
        "GUObjectArray, GWorld/GEngine, and dispatch/package root candidates "
        "from the live executable or module"
    ),
    "targetObjectDiscovery": (
        "object discovery must be proven from target-image names, objects, "
        "world, and dispatch anchors rather than loader/self-test scaffolds"
    ),
    "targetPackageLoadingSurface": (
        "package loading surface must be proven from target-image "
        "StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or "
        "ResolveName anchor evidence"
    ),
    "anchorCoverageObjectDiscovery": (
        "anchor coverage JSON must show target-image names, objects, and "
        "world coverage; rerun readiness with --anchor-coverage-json from the latest "
        "anchor-signature canary"
    ),
    "anchorCoverageHookPlanning": (
        "anchor coverage JSON must show target-image dispatch coverage before "
        "hook planning; rerun readiness with --anchor-coverage-json from the latest "
        "anchor-signature canary"
    ),
    "anchorCoveragePackageLoading": (
        "anchor coverage JSON must show target-image package-loading coverage before "
        "LoadAsset/LoadClass package parity can be claimed; rerun readiness "
        "with --anchor-coverage-json from the latest anchor-signature canary"
    ),
    "signatureManifestExact": (
        "signature validation must include exact target-image anchor matches "
        "for this build"
    ),
    "signatureManifestPromotable": (
        "signature validation must include promotable target-image anchor "
        "patterns for this build"
    ),
    "luaLoadAssetPackageNativeExecutor": (
        "package native executor must report NativeExecutorReady=true, "
        "ExecutorPreflightPassed=true, and FinalNativeCallEligible=true in the "
        "target image; dry-run executor shape evidence is diagnostic only"
    ),
    "luaLoadAssetPackageNativeInvocation": (
        "package native invoke must report nativeInvoked=true, nativeCallable=true, "
        "targetImage=true, and nativeReturnValidated=true from a guarded "
        "lua-load-asset-package-native-invoke row"
    ),
    "luaLoadClassPackageAbiState": (
        "LoadClass package ABI state must report targetImage=true, "
        "signatureFamily=StaticLoadClass, abiVerified=true, and classRootReady=true"
    ),
    "luaLoadClassPackageCallFrameVerification": (
        "LoadClass package call-frame verification must report targetImage=true, "
        "abiVerified=true, classRootReady=true, and callFrameReady=true for "
        "StaticLoadClass; anchor-missing or dry-run rows are diagnostic only"
    ),
    "luaLoadClassPackageNativeExecutor": (
        "LoadClass package native executor must report targetImage=true, "
        "NativeExecutorReady=true, ExecutorPreflightPassed=true, and "
        "FinalNativeCallEligible=true for StaticLoadClass"
    ),
    "luaLoadClassPackageNativeInvocation": (
        "LoadClass package native invoke must report nativeInvoked=true, "
        "nativeCallable=true, targetImage=true, classRootReady=true, and "
        "nativeCallPlanAccepted=true from a lua-load-class-package-native-invoke row"
    ),
    "luaStaticConstructObjectNativeExecutorState": (
        "StaticConstructObject native bridge must emit "
        "lua-static-construct-object-native-executor-state evidence"
    ),
    "luaStaticConstructObjectNativeExecutorReady": (
        "StaticConstructObject native executor must report targetImage=true, "
        "abiVerified=true, callFrameReady=true, finalInvokeConfirmed=true, "
        "and nativeCallable=true"
    ),
    "luaStaticConstructObjectNativeInvoke": (
        "StaticConstructObject native invoke must report targetImage=true and "
        "nativeInvoked=true from a guarded lua-static-construct-object-native-invoke row"
    ),
}
KNOWN_FAST_PATH_NOTES = {
    "package-loading": {
        "goal": "close the 1:1 UE4SS package-loading gap",
        "path": (
            "recover one target-image StaticLoadObject/StaticLoadClass/LoadObject/"
            "LoadPackage/ResolveName anchor, verify its ABI/call-frame contract, "
            "then run the guarded native LoadAsset/LoadClass invocation canary"
        ),
        "why": (
            "the current strict contract already has target-image object, world, "
            "dispatch, reflection, and Lua surfaces ahead of package loading; "
            "registry fallback is diagnostic and does not count as 1:1 package parity"
        ),
        "avoid": (
            "do not repeat string-only, package-loader-vtable, streamable, "
            "async-delegate, RTTI, or writable-global routes unless new runtime "
            "call-frame/decompile evidence is added"
        ),
    },
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


def anchor_list_from_count(prefix, count):
    if not isinstance(count, int) or count <= 0:
        return []
    return [f"{prefix}{index}" for index in range(count)]


def normalize_anchor_coverage_sidecar(payload, source):
    if not isinstance(payload, dict):
        raise ValueError(f"{source} is not a JSON object")
    if payload.get("schemaVersion") == READINESS_SCHEMA_VERSION:
        coverage = payload.get("anchorCoverage")
    elif payload.get("schemaVersion") == "dune-ue4ss-evidence-inventory/v1":
        best = payload.get("best") if isinstance(payload.get("best"), dict) else {}
        coverage = best.get("anchorCoverage")
    else:
        coverage = payload
    if not isinstance(coverage, dict):
        raise ValueError(f"{source} does not contain an anchor coverage object")
    normalized = dict(coverage)
    combined_count = normalized.get("combinedAnchorCount")
    if combined_count is None:
        present_groups = normalized.get("presentGroups")
        if isinstance(present_groups, list):
            combined_count = len([item for item in present_groups if isinstance(item, str) and item])
        else:
            groups = normalized.get("groups") if isinstance(normalized.get("groups"), dict) else {}
            combined_count = sum(
                1
                for group in groups.values()
                if isinstance(group, dict) and int(group.get("present", 0) or 0) > 0
            )
        normalized["combinedAnchorCount"] = combined_count
    normalized.setdefault(
        "explicitAnchors",
        anchor_list_from_count("__explicit_anchor_", int(normalized.get("explicitAnchorCount", 0) or 0)),
    )
    normalized.setdefault(
        "signatureAnchors",
        anchor_list_from_count("__signature_anchor_", int(normalized.get("signatureAnchorCount", 0) or 0)),
    )
    normalized.setdefault(
        "combinedAnchors",
        anchor_list_from_count("__combined_anchor_", int(normalized.get("combinedAnchorCount", 0) or 0)),
    )
    return normalized


def validate_readiness_report(report, source="readiness report"):
    if not isinstance(report, dict):
        raise ValueError(f"{source} is not a JSON object")
    schema = report.get("schemaVersion")
    if schema is not None and schema != READINESS_SCHEMA_VERSION:
        raise ValueError(
            f"{source} has schemaVersion {schema!r}; expected {READINESS_SCHEMA_VERSION!r}"
        )
    ready = report.get("ready")
    if not isinstance(ready, dict):
        raise ValueError(f"{source} is missing readiness `ready` object")
    contract = report.get("liveTargetImageCanaryContract")
    if contract is not None:
        validate_live_target_image_contract(contract, f"{source}.liveTargetImageCanaryContract")
    coverage = report.get("anchorCoverage")
    if coverage is not None:
        validate_anchor_coverage(coverage, f"{source}.anchorCoverage")
    per_loader = report.get("perLoaderReadiness")
    if per_loader is not None:
        if not isinstance(per_loader, dict):
            raise ValueError(f"{source}.perLoaderReadiness must be an object")
        for loader, entry in per_loader.items():
            if not isinstance(loader, str) or not loader:
                raise ValueError(f"{source}.perLoaderReadiness contains an invalid loader key")
            validate_readiness_report(entry, f"{source}.perLoaderReadiness.{loader}")
    return report


def validate_string_list(value, label):
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{label}[{index}] must be a string")


def validate_non_negative_int_field(payload, key, label):
    value = payload.get(key)
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label}.{key} must be a non-negative integer")


def validate_bool_field(payload, key, label):
    value = payload.get(key)
    if value is None:
        return
    if not isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be a boolean")


def validate_string_list_field(payload, key, label):
    value = payload.get(key)
    if value is None:
        return
    validate_string_list(value, f"{label}.{key}")


def validate_live_target_image_contract(contract, label):
    if not isinstance(contract, dict):
        raise ValueError(f"{label} must be an object")
    validate_bool_field(contract, "ready", label)
    validate_string_list_field(contract, "missingKeys", label)
    if contract.get("ready") is True and contract.get("missingKeys"):
        raise ValueError(f"{label}.ready cannot be true while missingKeys is non-empty")
    groups = contract.get("groups")
    if groups is not None:
        if not isinstance(groups, dict):
            raise ValueError(f"{label}.groups must be an object")
        for group_name, group in groups.items():
            group_label = f"{label}.groups.{group_name}"
            if not isinstance(group, dict):
                raise ValueError(f"{group_label} must be an object")
            validate_bool_field(group, "ready", group_label)
            validate_string_list_field(group, "requiredKeys", group_label)
            validate_string_list_field(group, "missingKeys", group_label)
            if group.get("ready") is True and group.get("missingKeys"):
                raise ValueError(f"{group_label}.ready cannot be true while missingKeys is non-empty")
            if contract.get("ready") is True and group.get("ready") is not True:
                raise ValueError(f"{label}.ready cannot be true while group {group_name} is not ready")


def validate_anchor_coverage(coverage, label):
    if not isinstance(coverage, dict):
        raise ValueError(f"{label} must be an object")
    for key in (
        "provided",
        "readyForTargetObjectDiscovery",
        "readyForTargetHookPlanning",
        "readyForTargetPackageLoading",
        "targetCoverageFieldsPresent",
    ):
        validate_bool_field(coverage, key, label)
    for key in ("explicitAnchorCount", "signatureAnchorCount", "combinedAnchorCount"):
        validate_non_negative_int_field(coverage, key, label)
    validate_string_list_field(coverage, "missingRequiredGroups", label)
    groups = coverage.get("groups")
    if groups is not None:
        if not isinstance(groups, dict):
            raise ValueError(f"{label}.groups must be an object")
        for group_name, group in groups.items():
            group_label = f"{label}.groups.{group_name}"
            if not isinstance(group, dict):
                raise ValueError(f"{group_label} must be an object")
            for key in ("complete", "targetComplete"):
                validate_bool_field(group, key, group_label)
            for key in ("present", "total", "targetPresent", "loaderPresent", "unknownPresent"):
                validate_non_negative_int_field(group, key, group_label)


def validate_canary_plan(plan, source="canary plan"):
    if not isinstance(plan, dict):
        raise ValueError(f"{source} is not a JSON object")
    schema = plan.get("schemaVersion")
    if schema != CANARY_PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"{source} has schemaVersion {schema!r}; expected {CANARY_PLAN_SCHEMA_VERSION!r}"
        )
    contract = plan.get("nextCanaryContract")
    if contract is None:
        return plan
    if not isinstance(contract, dict):
        raise ValueError(f"{source} nextCanaryContract must be an object")
    for key, label in (
        ("rootRecoveryCandidateInput", "rootRecoveryCandidateInput"),
        ("runtimeCandidateCarryForward", "runtimeCandidateCarryForward"),
    ):
        payload = contract.get(key)
        if payload is None:
            continue
        if not isinstance(payload, dict):
            raise ValueError(f"{source} {label} must be an object")
        for list_key in (
            "sourcePaths",
            "shapeSourcePaths",
            "outcomeSourcePaths",
            "sourceAnchorPresets",
            "missingGroups",
            "entries",
        ):
            validate_string_list(payload.get(list_key), f"{source} {label}.{list_key}")
        for dict_key in (
            "anchorCounts",
            "groupCoverage",
            "shapeQuality",
            "hintQuality",
            "sourceGroupQuality",
        ):
            value = payload.get(dict_key)
            if value is not None and not isinstance(value, dict):
                raise ValueError(f"{source} {label}.{dict_key} must be an object")
        for int_key in (
            "candidateCount",
            "emittedCount",
            "filteredRejectedShapeCount",
            "filteredRejectedCandidateCount",
            "filteredRejectedShapeOnlyCount",
            "filteredRejectedOutcomeCount",
            "entryCount",
        ):
            validate_non_negative_int_field(payload, int_key, f"{source} {label}")
    post_canary = contract.get("postCanaryVerification")
    if post_canary is not None:
        if not isinstance(post_canary, dict):
            raise ValueError(f"{source} postCanaryVerification must be an object")
        output_files = post_canary.get("outputFiles")
        if not isinstance(output_files, dict):
            raise ValueError(f"{source} postCanaryVerification.outputFiles must be an object")
        for key, expected in (
            ("readinessJson", "ue4ss-readiness.json"),
            ("objectDiscoveryCoverage", "object-discovery-coverage.json"),
            ("postCanaryGapSummaryJson", "ue4ss-port-gaps.json"),
            ("postCanaryGapSummary", "ue4ss-port-gaps.md"),
            ("evidenceInventoryJson", "ue4ss-evidence-inventory.json"),
            ("evidenceInventory", "ue4ss-evidence-inventory.md"),
            ("postCanarySummary", "post-canary-summary.md"),
        ):
            value = output_files.get(key)
            if not isinstance(value, str):
                raise ValueError(f"{source} postCanaryVerification.outputFiles.{key} must be a string")
            if not single_line_scalar(value):
                raise ValueError(
                    f"{source} postCanaryVerification.outputFiles.{key} must be a non-empty single-line string"
                )
            if value != expected:
                raise ValueError(
                    f"{source} postCanaryVerification.outputFiles.{key} must be {expected}"
                )
    return plan


def single_line_scalar(value):
    if not isinstance(value, (str, int, float, bool)):
        return False
    text = str(value)
    return bool(text.strip()) and not any(char in text for char in "\r\n\0")


def single_line_path(value):
    text = str(value)
    return bool(text.strip()) and not any(char in text for char in "\r\n\0")


def validate_candidate_outcome_paths(paths, source="candidate outcome inputs"):
    validated = []
    for index, path in enumerate(paths or []):
        if not single_line_path(path):
            raise ValueError(f"{source}[{index}] must be a non-empty single-line path")
        validated.append(str(path))
    return validated


def validate_target_image_substrings(values, source="target image filters"):
    validated = []
    for index, value in enumerate(values or []):
        if not single_line_scalar(value):
            raise ValueError(f"{source}[{index}] must be a non-empty single-line scalar")
        validated.append(str(value))
    return validated


def validate_next_steps(values, source="readiness nextSteps"):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{source} must be a list")
    validated = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not single_line_scalar(value):
            raise ValueError(f"{source}[{index}] must be a non-empty single-line string")
        validated.append(value)
    return validated


def validate_route_slot_trace_requirement(requirement, source):
    if requirement is None:
        return
    if not isinstance(requirement, dict):
        raise ValueError(f"{source} must be an object")
    for key in ("expectedTraceMarker", "routeAddress", "reviewField"):
        value = requirement.get(key)
        if not isinstance(value, str) or not single_line_scalar(value):
            raise ValueError(f"{source}.{key} must be a non-empty single-line string")
    for key in ("requiredSlots", "requiredRegisters"):
        values = requirement.get(key)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{source}.{key} must be a non-empty list")
        for index, value in enumerate(values):
            if not isinstance(value, str) or not single_line_scalar(value):
                raise ValueError(f"{source}.{key}[{index}] must be a non-empty single-line string")
    if requirement.get("expectedTraceMarker") != "UE4SS_PACKAGE_ROUTE_TRACE_HIT":
        raise ValueError(f"{source}.expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT")
    if requirement.get("reviewField") != "routeVtableStaticSlotMatches":
        raise ValueError(f"{source}.reviewField must be routeVtableStaticSlotMatches")


def validate_package_next_action(action, source="package next-action"):
    if not isinstance(action, dict):
        raise ValueError(f"{source} is not a JSON object")
    schema = action.get("schemaVersion")
    if schema != PACKAGE_NEXT_ACTION_SCHEMA_VERSION:
        raise ValueError(
            f"{source} has schemaVersion {schema!r}; expected {PACKAGE_NEXT_ACTION_SCHEMA_VERSION!r}"
        )
    action_name = action.get("action", "")
    if not isinstance(action_name, str) or not single_line_scalar(action_name):
        raise ValueError(f"{source} action must be a non-empty string")
    confidence = action.get("confidence")
    if confidence is not None and (not isinstance(confidence, str) or not single_line_scalar(confidence)):
        raise ValueError(f"{source} confidence must be a non-empty single-line string")
    reason = action.get("reason")
    if reason is not None and (not isinstance(reason, str) or not single_line_scalar(reason)):
        raise ValueError(f"{source} reason must be a non-empty single-line string")
    next_step = action.get("nextStep")
    if next_step is not None and (not isinstance(next_step, str) or not single_line_scalar(next_step)):
        raise ValueError(f"{source} nextStep must be a non-empty single-line string")
    commands = action.get("commands", [])
    if not isinstance(commands, list):
        raise ValueError(f"{source} commands must be a list")
    for index, command in enumerate(commands):
        if not isinstance(command, str):
            raise ValueError(f"{source} commands[{index}] must be a string")
        if not single_line_scalar(command):
            raise ValueError(f"{source} commands[{index}] must be a non-empty single-line string")
    ready_manifest_paths = action.get("readyManifestPaths")
    if ready_manifest_paths is not None and not isinstance(ready_manifest_paths, list):
        raise ValueError(f"{source} readyManifestPaths must be a list")
    if isinstance(ready_manifest_paths, list):
        for index, path in enumerate(ready_manifest_paths):
            if not isinstance(path, str) or not path:
                raise ValueError(f"{source} readyManifestPaths[{index}] must be a non-empty string")
    pending = action.get("pending")
    if pending is not None and not isinstance(pending, dict):
        raise ValueError(f"{source} pending must be an object")
    if isinstance(pending, dict):
        for key in ("missingReviewFlags", "missingNativeInvokeFlags", "blockers", "abiReviewBlockers"):
            values = pending.get(key)
            if values is None:
                continue
            if not isinstance(values, list):
                raise ValueError(f"{source} pending {key} must be a list")
            for index, value in enumerate(values):
                if not isinstance(value, str):
                    raise ValueError(f"{source} pending {key}[{index}] must be a string")
    blockers = action.get("blockers")
    if blockers is not None:
        if not isinstance(blockers, list):
            raise ValueError(f"{source} blockers must be a list")
        for index, blocker in enumerate(blockers):
            if not isinstance(blocker, str) or not single_line_scalar(blocker):
                raise ValueError(f"{source} blockers[{index}] must be a non-empty single-line string")
    trace_plan_blockers = action.get("tracePlanBlockers")
    if trace_plan_blockers is not None and not isinstance(trace_plan_blockers, list):
        raise ValueError(f"{source} tracePlanBlockers must be a list")
    if isinstance(trace_plan_blockers, list):
        for index, blocker in enumerate(trace_plan_blockers):
            if not isinstance(blocker, str):
                raise ValueError(f"{source} tracePlanBlockers[{index}] must be a string")
    trace_env = action.get("traceEnv")
    if trace_env is not None and not isinstance(trace_env, dict):
        raise ValueError(f"{source} traceEnv must be an object")
    if isinstance(trace_env, dict):
        for key, value in trace_env.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{source} traceEnv keys must be non-empty strings")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"{source} traceEnv {key} must be a scalar")
            if not single_line_scalar(value):
                raise ValueError(f"{source} traceEnv {key} must be a non-empty single-line scalar")
    promotion_errors = action.get("promotionSummaryErrors")
    if promotion_errors is not None and not isinstance(promotion_errors, list):
        raise ValueError(f"{source} promotionSummaryErrors must be a list")
    for index, row in enumerate(promotion_errors or []):
        if not isinstance(row, dict):
            raise ValueError(f"{source} promotionSummaryErrors[{index}] must be an object")
        if "path" in row and not isinstance(row.get("path"), str):
            raise ValueError(f"{source} promotionSummaryErrors[{index}].path must be a string")
        if "path" in row and row.get("path") and not single_line_scalar(row.get("path")):
            raise ValueError(f"{source} promotionSummaryErrors[{index}].path must be a single-line string")
        if not isinstance(row.get("error", ""), str) or not row.get("error", ""):
            raise ValueError(f"{source} promotionSummaryErrors[{index}].error must be a non-empty string")
        if not single_line_scalar(row.get("error", "")):
            raise ValueError(f"{source} promotionSummaryErrors[{index}].error must be a non-empty single-line string")
    if ready_manifest_paths and promotion_errors:
        raise ValueError(f"{source} cannot contain readyManifestPaths while promotionSummaryErrors are present")
    output_files = action.get("outputFiles")
    if output_files is not None and not isinstance(output_files, dict):
        raise ValueError(f"{source} outputFiles must be an object")
    if isinstance(output_files, dict):
        for key, value in output_files.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{source} outputFiles keys must be non-empty strings")
            if not isinstance(value, str):
                raise ValueError(f"{source} outputFiles {key} must be a string")
            if not single_line_scalar(value):
                raise ValueError(f"{source} outputFiles {key} must be a non-empty single-line string")
    live_trace_runbook = action.get("liveTraceRunbook")
    if live_trace_runbook is not None and not isinstance(live_trace_runbook, dict):
        raise ValueError(f"{source} liveTraceRunbook must be an object")
    if isinstance(live_trace_runbook, dict):
        command_count = live_trace_runbook.get("commandCount")
        if not isinstance(command_count, int) or command_count < 1:
            raise ValueError(f"{source} liveTraceRunbook.commandCount must be a positive integer")
        for key in (
            "cleanupCommand",
            "noDebuggerCheckCommand",
            "digestProvenanceFields",
            "recommendedCandidate",
            "remote",
            "container",
            "reviewBundleVerificationJson",
            "localReviewSummarySchemaVersion",
            "localReviewSummaryEmbeddedEvidenceFields",
            "localReviewSummaryRunbookMode",
            "localReviewSummaryVerificationCommand",
            "sourcePath",
            "traceLog",
        ):
            value = live_trace_runbook.get(key)
            if not isinstance(value, str) or not single_line_scalar(value):
                raise ValueError(f"{source} liveTraceRunbook.{key} must be a non-empty single-line string")
        local_review_summary = live_trace_runbook.get("localReviewSummaryJson", "")
        if local_review_summary is not None and local_review_summary != "":
            if not isinstance(local_review_summary, str) or not single_line_scalar(local_review_summary):
                raise ValueError(f"{source} liveTraceRunbook.localReviewSummaryJson must be a single-line string")
        coordinator_command = live_trace_runbook.get("coordinatorCommand", "")
        coordinator_dry_run_command = live_trace_runbook.get("coordinatorDryRunCommand", "")
        coordinator_fresh_preflight_command = live_trace_runbook.get("coordinatorFreshPreflightCommand", "")
        coordinator_fresh_trace_command = live_trace_runbook.get("coordinatorFreshTraceCommand", "")
        if coordinator_command is not None and coordinator_command != "":
            if not isinstance(coordinator_command, str) or not single_line_scalar(coordinator_command):
                raise ValueError(f"{source} liveTraceRunbook.coordinatorCommand must be a single-line string")
        if coordinator_dry_run_command is not None and coordinator_dry_run_command != "":
            if not isinstance(coordinator_dry_run_command, str) or not single_line_scalar(coordinator_dry_run_command):
                raise ValueError(f"{source} liveTraceRunbook.coordinatorDryRunCommand must be a single-line string")
        if coordinator_fresh_preflight_command is not None and coordinator_fresh_preflight_command != "":
            if not isinstance(coordinator_fresh_preflight_command, str) or not single_line_scalar(coordinator_fresh_preflight_command):
                raise ValueError(f"{source} liveTraceRunbook.coordinatorFreshPreflightCommand must be a single-line string")
        if coordinator_fresh_trace_command is not None and coordinator_fresh_trace_command != "":
            if not isinstance(coordinator_fresh_trace_command, str) or not single_line_scalar(coordinator_fresh_trace_command):
                raise ValueError(f"{source} liveTraceRunbook.coordinatorFreshTraceCommand must be a single-line string")
        if live_trace_runbook.get("digestProvenanceFields") != LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS:
            raise ValueError(
                f"{source} liveTraceRunbook.digestProvenanceFields must be {LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS}"
            )
        if live_trace_runbook.get("localReviewSummarySchemaVersion") != LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_SCHEMA:
            raise ValueError(
                f"{source} liveTraceRunbook.localReviewSummarySchemaVersion must be {LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_SCHEMA}"
            )
        if (
            live_trace_runbook.get("localReviewSummaryEmbeddedEvidenceFields")
            != LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS
        ):
            raise ValueError(
                f"{source} liveTraceRunbook.localReviewSummaryEmbeddedEvidenceFields must be {LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS}"
            )
        cleanup_command = live_trace_runbook.get("cleanupCommand", "")
        if not any(anchor in cleanup_command for anchor in LIVE_TRACE_RUNBOOK_REQUIRED_CLEANUP_ANCHORS):
            raise ValueError(
                f"{source} liveTraceRunbook.cleanupCommand must include one of {', '.join(LIVE_TRACE_RUNBOOK_REQUIRED_CLEANUP_ANCHORS)}"
            )
        trace_log = live_trace_runbook.get("traceLog", "")
        if not (trace_log.startswith(LIVE_TRACE_RUNBOOK_TRACE_LOG_PREFIX) and trace_log.endswith(".log")):
            raise ValueError(
                f"{source} liveTraceRunbook.traceLog must use timestamped {LIVE_TRACE_RUNBOOK_TRACE_LOG_PREFIX}*.log path"
            )
        no_debugger_check = live_trace_runbook.get("noDebuggerCheckCommand", "")
        if "grep -E \"gdb|ue4ss-package-runtime-trace\"" not in no_debugger_check:
            raise ValueError(f"{source} liveTraceRunbook.noDebuggerCheckCommand must check for gdb/runtime trace helpers")
        operator_window = live_trace_runbook.get("operatorWindow")
        if not isinstance(operator_window, dict):
            raise ValueError(f"{source} liveTraceRunbook.operatorWindow must be an object")
        if not isinstance(operator_window.get("maxArmSeconds"), int) or operator_window.get("maxArmSeconds") <= 0:
            raise ValueError(f"{source} liveTraceRunbook.operatorWindow.maxArmSeconds must be a positive integer")
        if operator_window.get("cleanupRequired") is not True:
            raise ValueError(f"{source} liveTraceRunbook.operatorWindow.cleanupRequired must be true")
        if tuple(operator_window.get("sequence", []) or []) != LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE:
            raise ValueError(f"{source} liveTraceRunbook.operatorWindow.sequence must preserve bounded cleanup handoff")
        validate_route_slot_trace_requirement(
            live_trace_runbook.get("routeSlotTraceRequirement"),
            f"{source} liveTraceRunbook.routeSlotTraceRequirement",
        )
        if live_trace_runbook.get("prearmReadinessJson") != LIVE_TRACE_RUNBOOK_PREARM_READINESS_JSON:
            raise ValueError(
                f"{source} liveTraceRunbook.prearmReadinessJson must be {LIVE_TRACE_RUNBOOK_PREARM_READINESS_JSON}"
            )
        if live_trace_runbook.get("prearmReadinessMarkdown") != LIVE_TRACE_RUNBOOK_PREARM_READINESS_MARKDOWN:
            raise ValueError(
                f"{source} liveTraceRunbook.prearmReadinessMarkdown must be {LIVE_TRACE_RUNBOOK_PREARM_READINESS_MARKDOWN}"
            )
        prearm_verifier = live_trace_runbook.get("prearmReadinessVerificationCommand", "")
        if (
            not isinstance(prearm_verifier, str)
            or not single_line_scalar(prearm_verifier)
            or "verify-ue4ss-package-prearm-readiness.py" not in prearm_verifier
            or "--preflight-summary" not in prearm_verifier
            or "--runbook-json" not in prearm_verifier
            or "--next-action-json" not in prearm_verifier
            or "--completion-audit-json" not in prearm_verifier
        ):
            raise ValueError(
                f"{source} liveTraceRunbook.prearmReadinessVerificationCommand must verify preflight, runbook, next-action, and completion audit"
            )
    return action


def build_readiness(args):
    if args.readiness_json:
        try:
            report = validate_readiness_report(load_json(args.readiness_json), str(args.readiness_json))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if args.anchor_coverage_json:
            readiness = import_readiness()
            anchor_coverages = [
                normalize_anchor_coverage_sidecar(load_json(path), str(path))
                for path in args.anchor_coverage_json
            ]
            anchor_coverage = readiness.anchor_coverage_status(anchor_coverages)
            report["anchorCoverage"] = anchor_coverage
            report.setdefault("ready", {})
            report["ready"]["anchorCoverageObjectDiscovery"] = anchor_coverage["readyForTargetObjectDiscovery"]
            report["ready"]["anchorCoverageHookPlanning"] = anchor_coverage["readyForTargetHookPlanning"]
            report["ready"]["anchorCoveragePackageLoading"] = anchor_coverage["readyForTargetPackageLoading"]
            report["ready"]["targetObjectDiscovery"] = bool(
                report["ready"].get("objectDiscovery", False)
                and report["ready"].get("runtimeRootDiscovery", False)
                and report["ready"].get("runtimeRootValidation", False)
                and report["ready"].get("targetNames", False)
                and report["ready"].get("targetObjects", False)
                and report["ready"].get("targetWorld", False)
                and (
                    report["ready"].get("targetDispatch", False)
                    or anchor_coverage["readyForTargetHookPlanning"]
                )
            )
            gate_updates = {
                "anchor-coverage-object-discovery": (
                    anchor_coverage["readyForTargetObjectDiscovery"],
                    (
                        f"combined={anchor_coverage['combinedAnchorCount']} "
                        f"targetReady={anchor_coverage['readyForTargetObjectDiscovery']} "
                        f"missingRequired={anchor_coverage['missingRequiredGroups']} "
                        f"groups={anchor_coverage['groups']}"
                    ),
                    "prepared canary anchor coverage is missing a required target-image object-discovery anchor group",
                ),
                "anchor-coverage-hook-planning": (
                    anchor_coverage["readyForTargetHookPlanning"],
                    (
                        f"combined={anchor_coverage['combinedAnchorCount']} "
                        f"targetReady={anchor_coverage['readyForTargetHookPlanning']} "
                        f"signatureAnchors={anchor_coverage['signatureAnchorCount']} "
                        f"dispatch={anchor_coverage['groups'].get('dispatch', {})}"
                    ),
                    "prepared canary anchor coverage does not include target-image ProcessEvent-level dispatch evidence for hook planning",
                ),
                "anchor-coverage-package-loading": (
                    anchor_coverage["readyForTargetPackageLoading"],
                    (
                        f"targetReady={anchor_coverage['readyForTargetPackageLoading']} "
                        f"groups={anchor_coverage['groups'].get('package', {})}"
                    ),
                    "prepared canary anchor coverage does not include target-image package-loading anchor evidence",
                ),
            }
            report.setdefault("gates", [])
            seen_gates = set()
            for gate in report.get("gates", []) or []:
                update = gate_updates.get(gate.get("name"))
                if not update:
                    continue
                seen_gates.add(gate.get("name"))
                passed, evidence, blocker = update
                gate["passed"] = passed
                gate["evidence"] = evidence
                gate["blocker"] = "" if passed else blocker
            for name, (passed, evidence, blocker) in gate_updates.items():
                if name in seen_gates:
                    continue
                report["gates"].append(
                    {
                        "name": name,
                        "passed": passed,
                        "evidence": evidence,
                        "blocker": "" if passed else blocker,
                    }
                )
            report["liveTargetImageCanaryContract"] = readiness.live_target_image_canary_contract(report["ready"])
            return validate_readiness_report(report, str(args.readiness_json))
        return report
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
    return validate_readiness_report(readiness.build_report(summaries, validations, anchor_coverages))


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
    missing_required = []
    for key in (*missing_ready, *required):
        if key not in missing_required and not ready_value(report, key):
            missing_required.append(key)
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


def top_level_blockers(features, live_contract, report):
    blockers = []
    if not bool(report.get("ready", {}).get("ue4ssLuaApiComplete", False)):
        blockers.append("ue4ssLuaApiComplete is not true")
    if isinstance(live_contract, dict) and live_contract.get("ready") is not True:
        first_group = live_contract.get("firstBlockedGroup", "")
        missing = live_contract.get("missingKeys", []) or []
        if first_group:
            blockers.append(f"live target-image contract is not ready: first blocked group {first_group}")
        elif missing:
            blockers.append(f"live target-image contract is not ready: missing {','.join(missing)}")
        else:
            blockers.append("live target-image contract is not ready")
    for feature in features:
        if feature.get("status") == "ready":
            continue
        missing_ready = feature.get("missingReadyKeys", []) or []
        missing_required = feature.get("missingRequiredKeys", []) or []
        if missing_ready:
            blockers.append(f"{feature['id']} missing ready keys: {','.join(missing_ready)}")
        if missing_required:
            blockers.append(
                f"{feature['id']} missing required keys: {','.join(missing_required[:8])}"
            )
        for item in (feature.get("blockers", []) or [])[:4]:
            detail = item.get("blocker") or item.get("evidence")
            if detail:
                blockers.append(f"{feature['id']} {item['key']}: {detail}")
        break
    return blockers


def append_package_next_action_blockers(blockers, package_next_action):
    if not isinstance(package_next_action, dict):
        return
    action_blockers = package_next_action.get("blockers", []) or []
    for blocker in action_blockers[:8]:
        if blocker:
            blockers.append(f"package-next-action: {blocker}")


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
        combined_coverage = dict(coverage)
        combined_missing = set(missing)
        combined_ready = set()
        for group_name, group in carry_coverage.items():
            if group.get("ready"):
                aggregate_ready.add(group_name)
                combined_ready.add(group_name)
            else:
                aggregate_missing.add(group_name)
                combined_missing.add(group_name)
            if group_name not in combined_coverage or group.get("ready"):
                combined_coverage[group_name] = group
        for group_name, group in coverage.items():
            if group.get("ready"):
                aggregate_ready.add(group_name)
                combined_ready.add(group_name)
            else:
                aggregate_missing.add(group_name)
                combined_missing.add(group_name)
        for group in missing:
            aggregate_missing.add(group)
        combined_missing.difference_update(combined_ready)
        for name, count in (root.get("anchorCounts", {}) or {}).items():
            aggregate_counts[name] = aggregate_counts.get(name, 0) + int(count or 0)
        for name, count in (carry.get("anchorCounts", {}) or {}).items():
            aggregate_counts[name] = aggregate_counts.get(name, 0) + int(count or 0)
        row_anchor_counts = {}
        for name, count in (root.get("anchorCounts", {}) or {}).items():
            row_anchor_counts[name] = row_anchor_counts.get(name, 0) + int(count or 0)
        for name, count in (carry.get("anchorCounts", {}) or {}).items():
            row_anchor_counts[name] = row_anchor_counts.get(name, 0) + int(count or 0)
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
                "anchorCounts": dict(sorted(row_anchor_counts.items())),
                "missingGroups": sorted(combined_missing),
                "groupCoverage": combined_coverage,
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


def summarize_anchor_coverage(report):
    coverage = report.get("anchorCoverage") or {}
    if not isinstance(coverage, dict) or not coverage.get("provided"):
        return {"provided": False}
    groups = {}
    missing_target_groups = []
    loader_only_groups = []
    for group_name, group in sorted((coverage.get("groups") or {}).items()):
        if not isinstance(group, dict):
            continue
        target_present = int(group.get("targetPresent", 0) or 0)
        loader_present = int(group.get("loaderPresent", 0) or 0)
        unknown_present = int(group.get("unknownPresent", 0) or 0)
        total = int(group.get("total", 0) or 0)
        target_complete = bool(group.get("targetComplete", False))
        if target_present == 0:
            missing_target_groups.append(group_name)
            if loader_present or unknown_present:
                loader_only_groups.append(group_name)
        groups[group_name] = {
            "present": int(group.get("present", 0) or 0),
            "total": total,
            "complete": bool(group.get("complete", False)),
            "targetPresent": target_present,
            "loaderPresent": loader_present,
            "unknownPresent": unknown_present,
            "targetComplete": target_complete,
        }
    return {
        "provided": True,
        "readyForTargetObjectDiscovery": bool(coverage.get("readyForTargetObjectDiscovery", False)),
        "readyForTargetHookPlanning": bool(coverage.get("readyForTargetHookPlanning", False)),
        "readyForTargetPackageLoading": bool(coverage.get("readyForTargetPackageLoading", False)),
        "targetCoverageFieldsPresent": bool(coverage.get("targetCoverageFieldsPresent", False)),
        "explicitAnchorCount": int(coverage.get("explicitAnchorCount", 0) or 0),
        "signatureAnchorCount": int(coverage.get("signatureAnchorCount", 0) or 0),
        "combinedAnchorCount": int(coverage.get("combinedAnchorCount", 0) or 0),
        "missingRequiredGroups": list(coverage.get("missingRequiredGroups", []) or []),
        "missingTargetGroups": missing_target_groups,
        "loaderOrUnknownOnlyGroups": loader_only_groups,
        "groups": groups,
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


def summarize(report, candidate_plans=None, candidate_outcome_paths=None, package_next_action=None):
    report = validate_readiness_report(report)
    candidate_outcome_paths = validate_candidate_outcome_paths(candidate_outcome_paths or [])
    features = [feature_row(report, feature) for feature in FEATURES]
    status_counts = {}
    for feature in features:
        status_counts[feature["status"]] = status_counts.get(feature["status"], 0) + 1
    per_loader = {}
    for loader, entry in sorted((report.get("perLoaderReadiness") or {}).items()):
        per_loader[loader] = summarize({**entry, "perLoaderReadiness": {}})
    live_contract = summarize_live_target_image_contract(report)
    anchor_coverage = summarize_anchor_coverage(report)
    next_canary = next_canary_recommendation(features, live_contract, report, candidate_outcome_paths)
    runtime_root_plan = runtime_root_recovery_plan(report, next_canary)
    object_registry_plan = object_registry_recovery_plan(report, features, next_canary)
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
    quickest_path = quickest_path_to_one_to_one(
        features,
        live_contract,
        anchor_coverage,
        next_canary,
        package_next_action,
    )
    next_steps = prioritized_next_steps(report, quickest_path)
    if runtime_root_plan.get("needed"):
        root_step = runtime_root_plan.get("renderedCommands", {}).get("server", "")
        if root_step and root_step not in next_steps:
            next_steps.insert(0, root_step)
    if object_registry_plan.get("needed"):
        object_step = object_registry_plan.get("renderedCommands", {}).get("server", "")
        if object_step and object_step not in next_steps:
            next_steps.insert(0, object_step)
    all_features_ready = bool(features) and all(feature["status"] == "ready" for feature in features)
    strict_ready = (
        all_features_ready
        and bool(report.get("ready", {}).get("ue4ssLuaApiComplete", False))
        and bool(live_contract.get("ready", False))
    )
    blockers = [] if strict_ready else top_level_blockers(features, live_contract, report)
    if not strict_ready:
        append_package_next_action_blockers(blockers, package_next_action)
    return {
        "schemaVersion": "dune-ue4ss-port-gap-summary/v1",
        "ready": strict_ready,
        "blockers": blockers,
        "statusCounts": dict(sorted(status_counts.items())),
        "quickestPathToOneToOne": quickest_path,
        "features": features,
        "nextCanaryRecommendation": next_canary,
        "runtimeRootRecoveryPlan": runtime_root_plan,
        "objectRegistryRecoveryPlan": object_registry_plan,
        "nextSteps": next_steps,
        "liveTargetImageMissingKeys": live_contract.get("missingKeys", []),
        "liveTargetImageContract": live_contract,
        "anchorCoverage": anchor_coverage,
        "reflectionRuntimeEvidence": reflection_evidence,
        "processEventRuntimeEvidence": process_event_evidence,
        "luaDispatchRuntimeEvidence": lua_dispatch_evidence,
        "rootRecoveryCandidateCoverage": candidate_coverage,
        "candidateOutcomeInputs": candidate_outcome_paths,
        "perLoader": per_loader,
    }


def package_next_action_hint(next_action):
    if not isinstance(next_action, dict):
        return {}
    if next_action.get("schemaVersion") != PACKAGE_NEXT_ACTION_SCHEMA_VERSION:
        return {}
    action = next_action.get("action", "")
    commands = [str(command) for command in next_action.get("commands", []) or [] if command]
    trace_env = {
        str(key): str(value)
        for key, value in (next_action.get("traceEnv", {}) or {}).items()
        if key and value is not None
    }
    promotion_errors = [
        {
            "path": str(row.get("path", "")),
            "error": str(row.get("error", "")),
        }
        for row in (next_action.get("promotionSummaryErrors", []) or [])
        if isinstance(row, dict) and row.get("error")
    ]
    output_files = {
        str(key): str(value)
        for key, value in (next_action.get("outputFiles", {}) or {}).items()
        if key and value is not None
    }
    live_trace_runbook = {}
    if isinstance(next_action.get("liveTraceRunbook"), dict):
        for key, value in next_action["liveTraceRunbook"].items():
            if not key or value is None:
                continue
            if key == "commandCount" and isinstance(value, int):
                live_trace_runbook[str(key)] = value
            elif key == "prearmReadinessReady" and isinstance(value, bool):
                live_trace_runbook[str(key)] = value
            elif key == "operatorWindow" and isinstance(value, dict):
                live_trace_runbook[str(key)] = {
                    str(window_key): window_value
                    for window_key, window_value in value.items()
                    if window_key
                }
            elif key in ("completionAuditNextClientGateClassification", "completionAuditNextRuntimeRootRecoveryPlan") and isinstance(value, dict):
                live_trace_runbook[str(key)] = {
                    str(item_key): list(item_value) if isinstance(item_value, list) else item_value
                    for item_key, item_value in value.items()
                    if item_key
                }
            elif key == "routeSlotTraceRequirement" and isinstance(value, dict):
                live_trace_runbook[str(key)] = {
                    str(req_key): list(req_value) if isinstance(req_value, list) else str(req_value)
                    for req_key, req_value in value.items()
                    if req_key
                }
            else:
                live_trace_runbook[str(key)] = str(value)
    return {
        "action": action,
        "confidence": next_action.get("confidence", ""),
        "reason": next_action.get("reason", ""),
        "liveTraceRunbook": live_trace_runbook,
        "traceEnv": trace_env,
        "commands": commands,
        "outputFiles": output_files,
        "nextStep": next_action.get("nextStep", ""),
        "promotionSummaryErrors": promotion_errors,
    }


def quickest_path_to_one_to_one(features, live_contract, anchor_coverage, next_canary, package_next_action=None):
    live_contract_ready = bool((live_contract or {}).get("ready", False))
    all_features_ready = bool(features) and all(feature["status"] == "ready" for feature in features)
    if not features or (all_features_ready and live_contract_ready):
        return {
            "ready": True,
            "feature": "",
            "goal": "1:1 UE4SS Linux parity is complete under the strict contract",
            "path": "rerun the full strict contract on the target build before release packaging",
            "why": "no blocked tracked feature remains",
            "avoid": "",
            "missingReadyKeys": [],
            "missingRequiredKeys": [],
            "missingTargetGroups": [],
            "recommendedStage": "none",
            "recommendedMaxStage": "",
        }
    feature_by_id = {feature["id"]: feature for feature in features}
    missing_target_groups = list((anchor_coverage or {}).get("missingTargetGroups", []))
    coverage_package_only = (
        bool(anchor_coverage or {})
        and missing_target_groups == ["package"]
        and bool((anchor_coverage or {}).get("readyForTargetObjectDiscovery", False))
        and bool((anchor_coverage or {}).get("readyForTargetHookPlanning", False))
        and not bool((anchor_coverage or {}).get("readyForTargetPackageLoading", False))
    )
    package_hint = package_next_action_hint(package_next_action)
    feature_id = "package-loading" if (package_hint or coverage_package_only) else (
        (live_contract or {}).get("firstBlockedFeature") or (next_canary or {}).get("feature")
    )
    feature = feature_by_id.get(feature_id)
    if feature is None or (feature["status"] == "ready" and not all_features_ready):
        feature = next((row for row in features if row["status"] != "ready"), features[0])
    note = KNOWN_FAST_PATH_NOTES.get(
        feature["id"],
        {
            "goal": f"close the {feature['title']} gap",
            "path": (next_canary or {}).get("reason", ""),
            "why": "this is the first blocked feature in strict readiness order",
            "avoid": "",
        },
    )
    row = {
        "ready": False,
        "feature": feature["id"],
        "goal": note["goal"],
        "path": note["path"],
        "why": note["why"],
        "avoid": note["avoid"],
        "missingReadyKeys": list(feature.get("missingReadyKeys", [])),
        "missingRequiredKeys": list(feature.get("missingRequiredKeys", [])),
        "missingTargetGroups": missing_target_groups,
        "recommendedStage": (next_canary or {}).get("stage", ""),
        "recommendedMaxStage": (next_canary or {}).get("maxStage", ""),
    }
    if feature["id"] == "package-loading":
        if package_hint:
            row["packageNextAction"] = package_hint
    return row


def prioritized_next_steps(report, quickest_path):
    steps = []
    package_next_action = (quickest_path or {}).get("packageNextAction") or {}
    if (quickest_path or {}).get("feature") == "package-loading" and package_next_action:
        action = package_next_action.get("action", "")
        if action:
            steps.append(f"package-loading quickest path: {action}")
        live_trace_runbook = package_next_action.get("liveTraceRunbook") or {}
        if live_trace_runbook:
            trace_log = live_trace_runbook.get("traceLog", "")
            candidate = live_trace_runbook.get("recommendedCandidate", "")
            remote = live_trace_runbook.get("remote", "")
            container = live_trace_runbook.get("container", "")
            coordinator_command = live_trace_runbook.get("coordinatorCommand", "")
            coordinator_dry_run_command = live_trace_runbook.get("coordinatorDryRunCommand", "")
            coordinator_fresh_preflight_command = live_trace_runbook.get("coordinatorFreshPreflightCommand", "")
            coordinator_fresh_trace_command = live_trace_runbook.get("coordinatorFreshTraceCommand", "")
            digest_fields = live_trace_runbook.get("digestProvenanceFields", "")
            review_json = live_trace_runbook.get("reviewBundleVerificationJson", "")
            local_review_summary = live_trace_runbook.get("localReviewSummaryJson", "")
            local_review_summary_schema = live_trace_runbook.get("localReviewSummarySchemaVersion", "")
            local_review_summary_embedded = live_trace_runbook.get("localReviewSummaryEmbeddedEvidenceFields", "")
            local_review_summary_runbook_mode = live_trace_runbook.get("localReviewSummaryRunbookMode", "")
            local_review_summary_verifier = live_trace_runbook.get("localReviewSummaryVerificationCommand", "")
            prearm_readiness_json = live_trace_runbook.get("prearmReadinessJson", "")
            prearm_readiness_markdown = live_trace_runbook.get("prearmReadinessMarkdown", "")
            prearm_readiness_verifier = live_trace_runbook.get("prearmReadinessVerificationCommand", "")
            prearm_readiness_ready = live_trace_runbook.get("prearmReadinessReady")
            prearm_readiness_next_step = live_trace_runbook.get("prearmReadinessNextStep", "")
            origin_classification = live_trace_runbook.get("completionAuditNextClientGateClassification") or {}
            runtime_root_recovery = live_trace_runbook.get("completionAuditNextRuntimeRootRecoveryPlan") or {}
            route_slot_trace_requirement = live_trace_runbook.get("routeSlotTraceRequirement") or {}
            if coordinator_dry_run_command:
                steps.append(f"live package trace dry-run: {coordinator_dry_run_command}")
            if coordinator_fresh_preflight_command:
                steps.append(f"live package trace fresh-log preflight: {coordinator_fresh_preflight_command}")
            if prearm_readiness_json:
                steps.append(f"verify package prearm readiness JSON: {prearm_readiness_json}")
            if prearm_readiness_markdown:
                steps.append(f"verify package prearm readiness Markdown: {prearm_readiness_markdown}")
            if prearm_readiness_verifier:
                steps.append(f"verify package prearm readiness: {prearm_readiness_verifier}")
            if prearm_readiness_ready is not None:
                steps.append(f"package prearm readiness ready: {str(prearm_readiness_ready).lower()}")
            if prearm_readiness_next_step:
                steps.append(f"package prearm readiness next step: {prearm_readiness_next_step}")
            if isinstance(origin_classification, dict) and origin_classification:
                fallback = origin_classification.get("serverSideFallbackCandidate", "")
                status = origin_classification.get("status", "")
                if fallback or status:
                    steps.append(f"package origin classification: status={status} server-side fallback={fallback}")
            if isinstance(runtime_root_recovery, dict) and runtime_root_recovery:
                required_log = runtime_root_recovery.get("requiredLogPath", "")
                if required_log:
                    steps.append(f"runtime-root recovery required log: {required_log}")
                if runtime_root_recovery.get("preflightCommand"):
                    steps.append(f"runtime-root recovery preflight: {runtime_root_recovery.get('preflightCommand', '')}")
                if runtime_root_recovery.get("runCommand"):
                    steps.append(f"runtime-root recovery canary: {runtime_root_recovery.get('runCommand', '')}")
            if coordinator_fresh_trace_command:
                steps.append(f"live package trace fresh-log coordinator: {coordinator_fresh_trace_command}")
            if coordinator_command:
                steps.append(f"live package trace coordinator: {coordinator_command}")
            if trace_log and candidate:
                target = f"{remote}/{container}" if remote and container else ""
                target_prefix = f"{target} " if target else ""
                steps.append(f"live package trace runbook: {candidate} -> {target_prefix}{trace_log}")
            if isinstance(route_slot_trace_requirement, dict) and route_slot_trace_requirement:
                slots = ",".join(str(slot) for slot in route_slot_trace_requirement.get("requiredSlots", []) or [])
                registers = ",".join(str(register) for register in route_slot_trace_requirement.get("requiredRegisters", []) or [])
                steps.append(
                    "package route-slot proof must capture "
                    f"{route_slot_trace_requirement.get('expectedTraceMarker', '')} "
                    f"route={route_slot_trace_requirement.get('routeAddress', '')} "
                    f"reviewField={route_slot_trace_requirement.get('reviewField', '')} "
                    f"slots={slots} registers={registers}"
                )
            if digest_fields:
                steps.append(
                    "package promotion proof must preserve digest-bound runtime-trace env evidence: "
                    f"tracePid,{digest_fields}"
                )
            if review_json:
                steps.append(f"verify package review bundle JSON: {review_json}")
            if local_review_summary:
                steps.append(f"capture local package review summary: {local_review_summary}")
            if local_review_summary_schema:
                steps.append(f"local package review summary schema: {local_review_summary_schema}")
            if local_review_summary_embedded:
                steps.append(f"local package review summary embedded evidence: {local_review_summary_embedded}")
            if local_review_summary_runbook_mode:
                steps.append(f"local package review summary runbook mode: {local_review_summary_runbook_mode}")
            if local_review_summary_verifier:
                steps.append(f"verify local package review summary: {local_review_summary_verifier}")
        for row in package_next_action.get("promotionSummaryErrors", []) or []:
            error = row.get("error", "")
            path = row.get("path", "")
            if error:
                steps.append(f"package promotion metadata error: {path}: {error}" if path else f"package promotion metadata error: {error}")
        for command in package_next_action.get("commands", []) or []:
            if command:
                steps.append(command)
        next_step = package_next_action.get("nextStep", "")
        if next_step:
            steps.append(next_step)
    for step in validate_next_steps(report.get("nextSteps", []) or []):
        if step and step not in steps:
            steps.append(step)
    return steps


def planner_command(platform, max_stage, candidate_outcome_paths=None, target_image_substrings=None):
    base = list(PLATFORM_PLANNER_COMMANDS[platform])
    for fragment in target_image_substrings or []:
        base += ["--exe-substring", str(fragment)]
    for path in candidate_outcome_paths or []:
        base += ["--candidate-outcomes-json", str(path)]
    return base + ["--max-stage", max_stage, "--format", "json"]


def render_command(command):
    return " ".join(shlex.quote(str(part)) for part in command)


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
    target_image_substrings = validate_target_image_substrings(
        (report or {}).get("targetImageSubstrings", []) or []
    )
    recommendation = {
        "needed": True,
        "feature": first_blocked["id"],
        "stage": hint["stage"],
        "maxStage": hint["maxStage"],
        "reason": hint["reason"],
        "liveTargetImageContractGroup": first_blocked_group,
        "targetImageSubstrings": target_image_substrings,
        "missingReadyKeys": first_blocked["missingReadyKeys"],
        "missingRequiredKeys": first_blocked["missingRequiredKeys"],
        "plannerCommands": {
            platform: planner_command(
                platform,
                hint["maxStage"],
                candidate_outcome_paths,
                target_image_substrings,
            )
            for platform in ("server", "linux-client", "windows")
        },
    }
    if candidate_outcome_paths:
        recommendation["candidateOutcomeInputs"] = [str(path) for path in candidate_outcome_paths]
    if report and first_blocked["id"] == "runtime-anchors":
        recommendation["runtimeRootCandidateLocations"] = runtime_candidate_locations(report)
    return recommendation


def runtime_root_recovery_plan(report, next_canary):
    ready = report.get("ready", {}) if isinstance(report, dict) else {}
    missing = [
        key
        for key in (
            "runtimeRootDiscovery",
            "runtimeRootValidation",
            "targetObjectDiscovery",
            "anchorCoverageObjectDiscovery",
        )
        if ready.get(key) is not True
    ]
    if not missing:
        return {
            "needed": False,
            "action": "none",
            "missingKeys": [],
            "commands": {},
            "acceptance": [],
        }
    discovery = report.get("runtimeDiscovery") or report.get("ueRuntimeDiscovery") or {}
    coverage = report.get("anchorCoverage") or {}
    target_image_substrings = validate_target_image_substrings(report.get("targetImageSubstrings", []) or [])
    commands = {
        platform: planner_command(platform, "read-only", target_image_substrings=target_image_substrings)
        for platform in ("server", "linux-client", "windows")
    }
    default_log_paths = {
        "server": "/tmp/dune-server-probe-loader.log",
        "linux-client": "/tmp/dune-client-probe-loader.log",
        "windows": "/tmp/dune-win-client-probe-loader.log",
    }
    next_canary_json = "build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.json"
    next_canary_env = "build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.env"
    blocked_by_missing_log = discovery.get("failureCounts", {}).get("not-run", 0) > 0
    capture_delay_seconds = "180"
    canary_wrapper_env = {
        "DUNE_LINUX_SERVER_CANARY_LOG_PATH": default_log_paths["server"],
        "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY": "false",
        "DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS": capture_delay_seconds,
        "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY": "true",
    }
    if not blocked_by_missing_log:
        canary_wrapper_env["DUNE_LINUX_SERVER_CANARY_PLAN_JSON"] = next_canary_json
    canary_preflight_env = dict(canary_wrapper_env)
    canary_preflight_env["DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY"] = "true"
    canary_wrapper_command = [
        *(f"{key}={value}" for key, value in canary_wrapper_env.items()),
        "scripts/canary-linux-server-loader.sh",
        ".env",
    ]
    canary_preflight_command = [
        *(f"{key}={value}" for key, value in canary_preflight_env.items()),
        "scripts/canary-linux-server-loader.sh",
        ".env",
    ]
    rendered_canary_preflight_command = render_command(canary_preflight_command)
    rendered_canary_run_command = render_command(canary_wrapper_command)
    return {
        "needed": True,
        "action": "recover-runtime-roots",
        "confidence": "high" if discovery.get("candidateCount", 0) == 0 else "moderate",
        "reason": (
            "current readiness has no target-image runtime root discovery proof"
            if discovery.get("candidateCount", 0) == 0
            else "current readiness has runtime root candidates but missing validation/object discovery"
        ),
        "missingKeys": missing,
        "currentEvidence": {
            "runtimeDiscoveryCandidateCount": int(discovery.get("candidateCount", 0) or 0),
            "runtimeDiscoveryFailureCounts": dict(discovery.get("failureCounts", {}) or {}),
            "anchorCoverageProvided": bool(coverage.get("provided", False)) if isinstance(coverage, dict) else False,
            "anchorCoverageReadyForObjectDiscovery": bool(coverage.get("readyForTargetObjectDiscovery", False))
            if isinstance(coverage, dict)
            else False,
            "targetImageSubstrings": target_image_substrings,
            "runtimeRootCandidateLocations": runtime_candidate_locations(report),
            "requiredCaptureDelaySeconds": int(capture_delay_seconds),
            "reasonForCaptureDelay": (
                "runtime-root canaries must outlive the 90-second delayed UE root validation probe "
                "and the follow-up runtime root scan"
            ),
        },
        "commands": commands,
        "renderedCommands": {platform: render_command(command) for platform, command in commands.items()},
        "immediatePlatform": "server",
        "preflightCommand": rendered_canary_preflight_command,
        "runCommand": rendered_canary_run_command,
        "outputFiles": {
            "nextCanaryJson": next_canary_json,
            "nextCanaryEnv": next_canary_env,
        },
        "canaryWrapper": {
            "script": "scripts/canary-linux-server-loader.sh",
            "env": canary_wrapper_env,
            "preflightEnv": canary_preflight_env,
            "preflightCommand": rendered_canary_preflight_command,
            "runCommand": rendered_canary_run_command,
            "guards": [
                "must run on kspls0 unless DUNE_LINUX_SERVER_CANARY_HOST is intentionally overridden",
                "requires zero connected players unless DUNE_LINUX_SERVER_CANARY_ALLOW_PLAYERS=true",
                "restores DUNE_ENABLE_LINUX_SERVER_PRELOAD, DUNE_LINUX_SERVER_PRELOAD_PARTITIONS, DUNE_LINUX_SERVER_PRELOAD, and DUNE_PROBE_LOADER_LOG during cleanup",
            ],
        },
        "blockedByMissingLog": blocked_by_missing_log,
        "requiredLogPath": default_log_paths["server"],
        "postCanaryVerificationOutputs": {
            "readinessJson": "ue4ss-readiness.json",
            "objectDiscoveryCoverage": "object-discovery-coverage.json",
            "postCanaryGapSummaryJson": "ue4ss-port-gaps.json",
            "postCanaryGapSummary": "ue4ss-port-gaps.md",
            "evidenceInventoryJson": "ue4ss-evidence-inventory.json",
            "evidenceInventory": "ue4ss-evidence-inventory.md",
            "postCanarySummary": "post-canary-summary.md",
        },
        "acceptance": [
            "read-only canary emits target-image RuntimeFNamePool and RuntimeGUObjectArray discovery candidates",
            "runtime root validation proves RuntimeFNamePool through FName decoding and RuntimeGUObjectArray through bounded object-array walking",
            "anchor coverage contains target-image names, objects, world, dispatch, and package groups instead of loader-only or unknown provenance",
            "targetObjectDiscovery becomes true from non-self-test target-image UObject/name/world evidence",
        ],
        "nextCanaryFeature": (next_canary or {}).get("feature", ""),
        "nextCanaryStage": (next_canary or {}).get("stage", ""),
    }


def object_registry_recovery_plan(report, features, next_canary):
    feature = next((item for item in features if item.get("id") == "object-registry"), {})
    if feature.get("status") == "ready":
        return {
            "needed": False,
            "action": "none",
            "missingKeys": [],
            "commands": {},
            "acceptance": [],
        }
    missing = list(feature.get("missingRequiredKeys", []) or [])
    ready = report.get("ready", {}) if isinstance(report, dict) else {}
    target_image_substrings = validate_target_image_substrings(report.get("targetImageSubstrings", []) or [])
    commands = {
        platform: planner_command(platform, "lua-dispatch", target_image_substrings=target_image_substrings)
        for platform in ("server", "linux-client", "windows")
    }
    next_canary_json = "build/server-current-anchor-prep/ue4ss-object-registry-next-canary.json"
    next_canary_env = "build/server-current-anchor-prep/ue4ss-object-registry-next-canary.env"
    capture_delay_seconds = "180"
    canary_wrapper_env = {
        "DUNE_LINUX_SERVER_CANARY_LOG_PATH": "/tmp/dune-server-probe-loader.log",
        "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY": "false",
        "DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS": capture_delay_seconds,
        "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY": "true",
        "DUNE_LINUX_SERVER_CANARY_PLAN_JSON": next_canary_json,
    }
    canary_preflight_env = dict(canary_wrapper_env)
    canary_preflight_env["DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY"] = "true"
    preflight_command = render_command(
        [
            *(f"{key}={value}" for key, value in canary_preflight_env.items()),
            "scripts/canary-linux-server-loader.sh",
            ".env",
        ]
    )
    run_command = render_command(
        [
            *(f"{key}={value}" for key, value in canary_wrapper_env.items()),
            "scripts/canary-linux-server-loader.sh",
            ".env",
        ]
    )
    coverage = report.get("objectDiscoveryCoverage", {}) if isinstance(report, dict) else {}
    return {
        "needed": True,
        "action": "recover-object-registry-semantics",
        "confidence": "high" if ready.get("targetObjectDiscovery") else "moderate",
        "reason": "runtime anchors are ready but FindObject/object-registry Lua semantics still lack runtime proof",
        "missingKeys": missing,
        "currentEvidence": {
            "targetObjectDiscovery": bool(ready.get("targetObjectDiscovery", False)),
            "objectDiscoveryCoverage": bool(ready.get("objectDiscoveryCoverage", False)),
            "findObjectSemantics": bool(ready.get("findObjectSemantics", False)),
            "luaObjectOuterChainIdentities": bool(ready.get("luaObjectOuterChainIdentities", False)),
            "luaObjectApi": bool(ready.get("luaObjectApi", False)),
            "luaStaticConstructObjectNativeExecutorState": bool(
                ready.get("luaStaticConstructObjectNativeExecutorState", False)
            ),
            "luaStaticConstructObjectNativeExecutorReady": bool(
                ready.get("luaStaticConstructObjectNativeExecutorReady", False)
            ),
            "luaStaticConstructObjectNativeInvoke": bool(ready.get("luaStaticConstructObjectNativeInvoke", False)),
            "missingFindObjectComponents": list(coverage.get("missingFindObjectComponents", []) or [])
            if isinstance(coverage, dict)
            else [],
            "requiredCaptureDelaySeconds": int(capture_delay_seconds),
            "reasonForCaptureDelay": (
                "object-registry canaries must outlive the 90-second delayed UE root/object validation probe "
                "and the follow-up runtime root scan"
            ),
        },
        "commands": commands,
        "renderedCommands": {platform: render_command(command) for platform, command in commands.items()},
        "immediatePlatform": "server",
        "preflightCommand": preflight_command,
        "runCommand": run_command,
        "outputFiles": {
            "nextCanaryJson": next_canary_json,
            "nextCanaryEnv": next_canary_env,
        },
        "canaryWrapper": {
            "script": "scripts/canary-linux-server-loader.sh",
            "env": canary_wrapper_env,
            "preflightEnv": canary_preflight_env,
            "preflightCommand": preflight_command,
            "runCommand": run_command,
            "guards": [
                "must run on kspls0 unless DUNE_LINUX_SERVER_CANARY_HOST is intentionally overridden",
                "requires zero connected players unless DUNE_LINUX_SERVER_CANARY_ALLOW_PLAYERS=true",
                "restores DUNE_ENABLE_LINUX_SERVER_PRELOAD, DUNE_LINUX_SERVER_PRELOAD_PARTITIONS, DUNE_LINUX_SERVER_PRELOAD, and DUNE_PROBE_LOADER_LOG during cleanup",
            ],
        },
        "postCanaryVerificationOutputs": {
            "readinessJson": "ue4ss-readiness.json",
            "objectDiscoveryCoverage": "object-discovery-coverage.json",
            "postCanaryGapSummaryJson": "ue4ss-port-gaps.json",
            "postCanaryGapSummary": "ue4ss-port-gaps.md",
            "evidenceInventoryJson": "ue4ss-evidence-inventory.json",
            "evidenceInventory": "ue4ss-evidence-inventory.md",
            "postCanarySummary": "post-canary-summary.md",
        },
        "acceptance": [
            "Lua FindObject/FindObjects/FindFirstOf/GetKnownObjects/ForEachUObject self-test and mod-entrypoint API checks pass in scoped logs",
            "runtime UObject outer chains resolve to reconstructed PathName/FullName identities, not only loader-owned self-test handles",
            "StaticConstructObject native executor emits state for targetName=StaticConstructObject",
            "StaticConstructObject native executor reports targetImage=true, abiVerified=true, callFrameReady=true, finalInvokeConfirmed=true, and nativeCallable=true",
            "guarded StaticConstructObject native invoke emits nativeInvoked=true from target-image native code",
        ],
        "nextCanaryFeature": (next_canary or {}).get("feature", ""),
        "nextCanaryStage": (next_canary or {}).get("stage", ""),
    }


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
    if summary.get("blockers"):
        lines.append(f"- Blockers: `{'; '.join(summary.get('blockers', []))}`")
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
        target_filters = recommendation.get("targetImageSubstrings") or []
        if target_filters:
            lines.append(f"- Recommended target filters: `{', '.join(target_filters)}`")
        candidate_locations = recommendation.get("runtimeRootCandidateLocations") or []
        if candidate_locations:
            rendered_locations = [
                f"{row.get('name', 'candidate')}@{row.get('addr', '?')} offset={row.get('imageOffset', '?')} image={row.get('map', '?')}"
                for row in candidate_locations[:6]
            ]
            lines.append(f"- Runtime root candidates: `{'; '.join(rendered_locations)}`")
    runtime_root_plan = summary.get("runtimeRootRecoveryPlan", {}) or {}
    if runtime_root_plan.get("needed"):
        lines.append("")
        lines.append("## Runtime Root Recovery")
        lines.append("")
        lines.append(f"- Action: `{runtime_root_plan.get('action', '')}`")
        lines.append(f"- Confidence: `{runtime_root_plan.get('confidence', '')}`")
        lines.append(f"- Reason: {runtime_root_plan.get('reason', '')}")
        lines.append(f"- Missing keys: `{', '.join(runtime_root_plan.get('missingKeys', []))}`")
        if runtime_root_plan.get("blockedByMissingLog"):
            lines.append(f"- Blocked by missing scoped log: `{runtime_root_plan.get('requiredLogPath', '')}`")
        evidence = runtime_root_plan.get("currentEvidence", {}) or {}
        lines.append(
            "- Current evidence: "
            f"candidates=`{evidence.get('runtimeDiscoveryCandidateCount', 0)}` "
            f"anchorCoverageProvided=`{str(evidence.get('anchorCoverageProvided', False)).lower()}`"
        )
        rendered_commands = runtime_root_plan.get("renderedCommands", {}) or {}
        if rendered_commands:
            lines.append("- Planner commands:")
            for platform in ("server", "linux-client", "windows"):
                command = rendered_commands.get(platform)
                if command:
                    lines.append(f"  - `{platform}`: `{command}`")
        output_files = runtime_root_plan.get("outputFiles", {}) or {}
        if output_files:
            lines.append("- Planner outputs:")
            for key, value in output_files.items():
                lines.append(f"  - `{key}`: `{value}`")
        wrapper = runtime_root_plan.get("canaryWrapper", {}) or {}
        if wrapper:
            lines.append("- Guarded canary wrapper:")
            if wrapper.get("preflightCommand"):
                lines.append(f"  - `preflight`: `{wrapper['preflightCommand']}`")
            if wrapper.get("runCommand"):
                lines.append(f"  - `run`: `{wrapper['runCommand']}`")
            for guard in wrapper.get("guards", []) or []:
                lines.append(f"  - guard: {guard}")
        outputs = runtime_root_plan.get("postCanaryVerificationOutputs", {}) or {}
        if outputs:
            lines.append("- Post-canary outputs:")
            for key, value in outputs.items():
                lines.append(f"  - `{key}`: `{value}`")
        if runtime_root_plan.get("acceptance"):
            lines.append("- Acceptance:")
            for item in runtime_root_plan["acceptance"]:
                lines.append(f"  - {item}")
    object_registry_plan = summary.get("objectRegistryRecoveryPlan", {}) or {}
    if object_registry_plan.get("needed"):
        lines.append("")
        lines.append("## Object Registry Recovery")
        lines.append("")
        lines.append(f"- Action: `{object_registry_plan.get('action', '')}`")
        lines.append(f"- Confidence: `{object_registry_plan.get('confidence', '')}`")
        lines.append(f"- Reason: {object_registry_plan.get('reason', '')}")
        lines.append(f"- Missing keys: `{', '.join(object_registry_plan.get('missingKeys', []))}`")
        evidence = object_registry_plan.get("currentEvidence", {}) or {}
        lines.append(
            "- Current evidence: "
            f"targetObjectDiscovery=`{str(evidence.get('targetObjectDiscovery', False)).lower()}` "
            f"findObjectSemantics=`{str(evidence.get('findObjectSemantics', False)).lower()}` "
            f"missingFindObject=`{', '.join(evidence.get('missingFindObjectComponents', [])) or 'none'}`"
        )
        rendered_commands = object_registry_plan.get("renderedCommands", {}) or {}
        if rendered_commands:
            lines.append("- Planner commands:")
            for platform in ("server", "linux-client", "windows"):
                command = rendered_commands.get(platform)
                if command:
                    lines.append(f"  - `{platform}`: `{command}`")
        output_files = object_registry_plan.get("outputFiles", {}) or {}
        if output_files:
            lines.append("- Planner outputs:")
            for key, value in output_files.items():
                lines.append(f"  - `{key}`: `{value}`")
        wrapper = object_registry_plan.get("canaryWrapper", {}) or {}
        if wrapper:
            lines.append("- Guarded canary wrapper:")
            if wrapper.get("preflightCommand"):
                lines.append(f"  - `preflight`: `{wrapper['preflightCommand']}`")
            if wrapper.get("runCommand"):
                lines.append(f"  - `run`: `{wrapper['runCommand']}`")
            for guard in wrapper.get("guards", []) or []:
                lines.append(f"  - guard: {guard}")
        if object_registry_plan.get("acceptance"):
            lines.append("- Acceptance:")
            for item in object_registry_plan["acceptance"]:
                lines.append(f"  - {item}")
    quickest_path = summary.get("quickestPathToOneToOne") or {}
    if quickest_path:
        lines.append("")
        lines.append("## Quickest Path To 1:1")
        lines.append("")
        lines.append(f"- Feature: `{quickest_path.get('feature') or 'none'}`")
        lines.append(f"- Goal: {quickest_path.get('goal', '')}")
        lines.append(f"- Path: {quickest_path.get('path', '')}")
        lines.append(f"- Why: {quickest_path.get('why', '')}")
        if quickest_path.get("avoid"):
            lines.append(f"- Avoid: {quickest_path.get('avoid', '')}")
        if quickest_path.get("missingTargetGroups"):
            lines.append(f"- Missing target groups: `{', '.join(quickest_path.get('missingTargetGroups', []))}`")
        if quickest_path.get("missingReadyKeys"):
            lines.append(f"- Missing ready keys: `{', '.join(quickest_path.get('missingReadyKeys', []))}`")
        package_next_action = quickest_path.get("packageNextAction") or {}
        if package_next_action:
            lines.append(f"- Package next action: `{package_next_action.get('action', '')}`")
            if package_next_action.get("confidence"):
                lines.append(f"- Package next action confidence: `{package_next_action.get('confidence')}`")
            if package_next_action.get("reason"):
                lines.append(f"- Package next action reason: {package_next_action.get('reason')}")
            live_trace_runbook = package_next_action.get("liveTraceRunbook") or {}
            if live_trace_runbook:
                lines.append("- Package live trace runbook:")
                for key in (
                    "sourcePath",
                    "recommendedCandidate",
                    "remote",
                    "container",
                    "traceLog",
                    "coordinatorDryRunCommand",
                    "coordinatorFreshPreflightCommand",
                    "coordinatorFreshTraceCommand",
                    "coordinatorCommand",
                    "cleanupCommand",
                    "noDebuggerCheckCommand",
                    "commandCount",
                    "digestProvenanceFields",
                    "reviewBundleVerificationJson",
                    "localReviewSummaryJson",
                    "localReviewSummarySchemaVersion",
                    "localReviewSummaryEmbeddedEvidenceFields",
                    "localReviewSummaryRunbookMode",
                    "localReviewSummaryVerificationCommand",
                ):
                    value = live_trace_runbook.get(key)
                    if value:
                        lines.append(f"  - `{key}`: `{value}`")
                route_slot = live_trace_runbook.get("routeSlotTraceRequirement") or {}
                if isinstance(route_slot, dict) and route_slot:
                    lines.append("  - `routeSlotTraceRequirement`:")
                    for key in (
                        "expectedTraceMarker",
                        "routeAddress",
                        "reviewField",
                        "requiredSlots",
                        "requiredRegisters",
                    ):
                        value = route_slot.get(key)
                        if isinstance(value, list):
                            value = ",".join(str(item) for item in value)
                        if value:
                            lines.append(f"    - `{key}`: `{value}`")
                operator_window = live_trace_runbook.get("operatorWindow") or {}
                if isinstance(operator_window, dict) and operator_window:
                    lines.append(f"  - `operatorWindow.maxArmSeconds`: `{operator_window.get('maxArmSeconds', '')}`")
                    lines.append(f"  - `operatorWindow.cleanupRequired`: `{operator_window.get('cleanupRequired', '')}`")
                    sequence = operator_window.get("sequence") or []
                    if isinstance(sequence, list):
                        lines.append(f"  - `operatorWindow.sequence`: `{', '.join(str(item) for item in sequence)}`")
                lines.append(
                    "- Package promotion proof gate: concrete `tracePid` plus digest-bound `runtime-trace:` env evidence "
                    "for `sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256`"
                )
            trace_env = package_next_action.get("traceEnv") or {}
            if trace_env:
                rendered_env = " ".join(f"{key}={value}" for key, value in sorted(trace_env.items()))
                lines.append(f"- Package trace env: `{rendered_env}`")
            for command in package_next_action.get("commands", [])[:4]:
                lines.append(f"- Package command: `{command}`")
            for key, value in sorted((package_next_action.get("outputFiles") or {}).items()):
                lines.append(f"- Package output file: `{key}={value}`")
            for row in package_next_action.get("promotionSummaryErrors", [])[:6]:
                path = row.get("path", "")
                prefix = f"`{path}`: " if path else ""
                lines.append(f"- Package promotion metadata error: {prefix}{row.get('error', '')}")
            if package_next_action.get("nextStep"):
                lines.append(f"- Package next step: {package_next_action.get('nextStep')}")
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
    anchor_coverage = summary.get("anchorCoverage", {})
    if isinstance(anchor_coverage, dict) and anchor_coverage.get("provided"):
        lines.append("")
        lines.append("## Anchor Coverage")
        lines.append("")
        lines.append(
            "- Target readiness: "
            f"objectDiscovery=`{str(anchor_coverage.get('readyForTargetObjectDiscovery', False)).lower()}` "
            f"hookPlanning=`{str(anchor_coverage.get('readyForTargetHookPlanning', False)).lower()}` "
            f"packageLoading=`{str(anchor_coverage.get('readyForTargetPackageLoading', False)).lower()}`"
        )
        lines.append(
            "- Anchor counts: "
            f"`explicit={anchor_coverage.get('explicitAnchorCount', 0)} "
            f"signature={anchor_coverage.get('signatureAnchorCount', 0)} "
            f"combined={anchor_coverage.get('combinedAnchorCount', 0)}`"
        )
        if anchor_coverage.get("missingTargetGroups"):
            lines.append(f"- Missing target groups: `{', '.join(anchor_coverage.get('missingTargetGroups', []))}`")
        if anchor_coverage.get("loaderOrUnknownOnlyGroups"):
            lines.append(
                "- Loader/unknown-only groups: "
                f"`{', '.join(anchor_coverage.get('loaderOrUnknownOnlyGroups', []))}`"
            )
        for group_name, group in anchor_coverage.get("groups", {}).items():
            lines.append(
                f"- `{group_name}` target=`{group.get('targetPresent', 0)}/{group.get('total', 0)}` "
                f"loader=`{group.get('loaderPresent', 0)}` "
                f"unknown=`{group.get('unknownPresent', 0)}` "
                f"targetComplete=`{str(group.get('targetComplete', False)).lower()}`"
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
            lines.append(f"- `{platform}`: `{render_command(command)}`")
    lines.append("")
    lines.append("## Next Steps")
    lines.append("")
    for step in summary.get("nextSteps", [])[:16]:
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
        "--package-next-action-json",
        type=Path,
        help="JSON from plan-ue4ss-package-next-action.py to annotate the package-loading quickest path",
    )
    parser.add_argument(
        "--candidate-outcomes-json",
        type=Path,
        action="append",
        default=[],
        help="JSON from summarize-ue-candidate-outcomes.py; paths are threaded into recommended planner commands",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    try:
        candidate_plans = [
            validate_canary_plan(load_json(path), str(path))
            for path in args.canary_plan_json
        ]
        package_next_action = (
            validate_package_next_action(load_json(args.package_next_action_json), str(args.package_next_action_json))
            if args.package_next_action_json
            else None
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    summary = summarize(build_readiness(args), candidate_plans, args.candidate_outcomes_json, package_next_action)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
