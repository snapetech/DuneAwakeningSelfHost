#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


PLATFORMS = ("server", "linux-client", "windows")
MAX_STAGES = ("read-only", "hook-probe", "live-hook", "lua-dispatch")
CORE_ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
ROOT_RECOVERY_ANCHOR_GROUPS = {
    "names": ("FNamePool", "RuntimeFNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "RuntimeGUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
REQUIRED_OBJECT_DISCOVERY_GROUPS = ("names", "objects", "world")
REQUIRED_HOOK_GROUPS = REQUIRED_OBJECT_DISCOVERY_GROUPS + ("dispatch",)
REQUIRED_REFLECTION_MINIMUM = 2
REGISTRY_RUNTIME_LOG_CONTRACT = {
    "luaObjectRegistryRuntime": {
        "events": ["lua-object-registry", "lua-object-registry-check"],
        "requiredProvenance": "registryProvenance=runtime",
        "description": "runtime UObject registry/add-check evidence",
    },
    "luaDecodedObjectAliasesRuntime": {
        "events": ["lua-object-registry", "lua-object-registry-check"],
        "requiredProvenance": "registryProvenance=runtime",
        "requiredSource": "ue-uobject-fname or ue-object-array-fname",
        "description": "runtime decoded UObject alias evidence",
    },
    "ueObjectArrayRegistryRuntime": {
        "events": ["lua-object-registry", "lua-object-registry-check"],
        "requiredProvenance": "registryProvenance=runtime",
        "requiredSource": "ue-object-array or ue-object-array-fname",
        "description": "runtime GUObjectArray-backed registry evidence",
    },
    "luaFunctionRegistryRuntime": {
        "events": ["lua-function-registry-check"],
        "requiredProvenance": "registryProvenance=runtime",
        "description": "runtime UFunction registry evidence",
    },
    "luaFunctionIterationRuntime": {
        "events": ["lua-function-iteration-check"],
        "requiredProvenance": "registryProvenance=runtime",
        "requiredMode": "owner",
        "description": "runtime owner ForEachFunction iteration evidence",
    },
}
PROCESS_EVENT_RUNTIME_LOG_CONTRACT = {
    "ueProcessEventHookRuntimeTarget": {
        "events": ["ue-process-event-hook"],
        "requiredFields": ["selfTestTarget=false", "callSelfTest=false"],
        "description": "hook probe installed/restored against the resolved runtime ProcessEvent target",
    },
    "ueProcessEventLiveHookRuntimeTarget": {
        "events": ["ue-process-event-live-hook"],
        "requiredFields": ["selfTestTarget=false", "callSelfTest=false"],
        "description": "persistent hook installed against the resolved runtime ProcessEvent target",
    },
    "ueProcessEventLiveRuntimeContext": {
        "events": ["ue-process-event-live-context"],
        "requiredFields": ["functionProvenance=runtime"],
        "description": "live ProcessEvent context resolved to a runtime UFunction",
    },
    "ueProcessEventLiveRuntimeRegistryContext": {
        "events": ["ue-process-event-live-registry-context"],
        "requiredFields": ["functionProvenance=runtime"],
        "description": "live ProcessEvent context resolved through promoted runtime registries",
    },
}
CALL_FUNCTION_RUNTIME_LOG_CONTRACT = {
    "ueCallFunctionHookRuntimeTarget": {
        "events": ["ue-call-function-hook"],
        "requiredFields": ["selfTestTarget=false", "callSelfTest=false"],
        "description": "hook probe installed/restored against the resolved runtime CallFunctionByNameWithArguments target",
    },
    "ueCallFunctionLiveHookRuntimeTarget": {
        "events": ["ue-call-function-live-hook"],
        "requiredFields": ["selfTestTarget=false", "callSelfTest=false"],
        "description": "persistent hook installed against the resolved runtime CallFunctionByNameWithArguments target",
    },
    "ueCallFunctionLiveLuaDispatch": {
        "events": ["ue-call-function-live-hook"],
        "requiredFields": ["status=installed", "luaDispatch=true"],
        "description": "live CallFunctionByNameWithArguments hook routed Lua pre/post callbacks",
    },
}
STRICT_RUNTIME_READY_KEYS = (
    "targetImageProcess",
    "runtimeRootDiscovery",
    "runtimeRootValidation",
    "targetObjectDiscovery",
    "targetHooks",
    "ueProcessEventHookRuntimeTarget",
    "ueCallFunctionHookRuntimeTarget",
    "ueProcessEventLiveHookRuntimeTarget",
    "ueCallFunctionLiveHookRuntimeTarget",
    "ueCallFunctionLiveLuaDispatch",
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
    "luaObjectRegistryRuntime",
    "luaFunctionRegistryRuntime",
    "luaDecodedObjectAliasesRuntime",
    "objectDiscoveryCoverage",
    "findObjectSemantics",
    "ueObjectArrayShape",
    "ueObjectArrayRegistryRuntime",
    "ueObjectNativeIdentities",
    "ueObjectInternalFlags",
    "ueFNameDecoder",
    "luaObjectOuterChainIdentities",
    "luaObjectApi",
    "luaFunctionIterationRuntime",
    "ueReflectionPropertyDescriptorsRuntime",
    "ueReflectionPropertyValuesRuntime",
    "luaReflectionForEachPropertyRuntime",
    "luaReflectionLiveDescriptorTypedClassRuntime",
    "luaReflectionLiveDescriptorTypedValuesRuntime",
    "luaReflectionLiveDescriptorTypedSetValuesRuntime",
    "luaReflectionLiveDescriptorValuesRuntime",
    "luaLoadAssetPackageCrashGuard",
    "luaLoadAssetPackageGuardedCall",
    "luaLoadAssetPackageReturnValidation",
    "luaLoadAssetPackageNativeCallAdapter",
    "luaLoadAssetPackageInvocationDescriptor",
    "luaLoadAssetPackageNativeExecutor",
    "luaLoadAssetPackage",
)
STRICT_RUNTIME_READY_KEY_GATES = {
    "targetImageProcess": "target-image-process",
    "runtimeRootDiscovery": "ue-runtime-root-discovery",
    "runtimeRootValidation": "ue-runtime-root-validation",
    "targetObjectDiscovery": "ue-target-dispatch",
    "targetHooks": "ue-target-dispatch",
    "ueProcessEventHookRuntimeTarget": "ue-process-event-hook-runtime-target",
    "ueCallFunctionHookRuntimeTarget": "ue-call-function-hook-runtime-target",
    "ueProcessEventLiveHookRuntimeTarget": "ue-process-event-live-hook-runtime-target",
    "ueCallFunctionLiveHookRuntimeTarget": "ue-call-function-live-hook-runtime-target",
    "ueCallFunctionLiveLuaDispatch": "ue-call-function-live-lua-dispatch",
    "ueProcessEventLiveLuaDispatch": "ue-process-event-live-lua-dispatch",
    "ueProcessEventLiveFunctionPath": "ue-process-event-live-function-path",
    "ueProcessEventLiveRuntimeContext": "ue-process-event-live-runtime-context",
    "ueProcessEventLiveRegistryContext": "ue-process-event-live-registry-context",
    "ueProcessEventLiveRuntimeRegistryContext": "ue-process-event-live-runtime-registry-context",
    "ueProcessEventLiveParamValues": "ue-process-event-live-param-values",
    "ueProcessEventLiveRawParamValues": "ue-process-event-live-raw-param-values",
    "ueProcessEventLiveContainerParamValues": "ue-process-event-live-container-param-values",
    "ueProcessEventLiveArrayContainerParamValues": "ue-process-event-live-array-container-param-values",
    "ueProcessEventLiveSetContainerParamValues": "ue-process-event-live-set-container-param-values",
    "ueProcessEventLiveMapContainerParamValues": "ue-process-event-live-map-container-param-values",
    "ueProcessEventLiveSetMapContainerParamValues": "ue-process-event-live-set-map-container-param-values",
    "ueProcessEventLiveContainerDataSamples": "ue-process-event-live-container-data-samples",
    "ueProcessEventLuaContextHandles": "ue-process-event-lua-context-handles",
    "ueProcessEventLuaParamAccessors": "ue-process-event-lua-param-accessors",
    "ueProcessEventLiveClassAwareParamValues": "ue-process-event-live-class-aware-param-values",
    "ueProcessEventFunctionParamMethod": "ue-process-event-function-param-method",
    "ueProcessEventFunctionParamLookupMethod": "ue-process-event-function-param-lookup-method",
    "ueProcessEventFunctionParamIterationMethod": "ue-process-event-function-param-iteration-method",
    "ueProcessEventContainerAliasMethods": "ue-process-event-container-alias-methods",
    "ueProcessEventContainerStorageLayoutMethods": "ue-process-event-container-storage-layout-methods",
    "ueProcessEventLuaScalarParamAccessors": "ue-process-event-lua-scalar-param-accessors",
    "ueProcessEventLuaNameStringParamAccessors": "ue-process-event-lua-name-string-param-accessors",
    "ueProcessEventLuaStructParamAccessors": "ue-process-event-lua-struct-param-accessors",
    "ueProcessEventLuaEnumParamAccessors": "ue-process-event-lua-enum-param-accessors",
    "ueProcessEventLuaObjectParamAccessors": "ue-process-event-lua-object-param-accessors",
    "ueProcessEventLuaBoolParamAccessors": "ue-process-event-lua-bool-param-accessors",
    "ueProcessEventLuaHookRouting": "ue-process-event-lua-hook-routing",
    "ueProcessEventLuaHookAliasRouting": "ue-process-event-lua-hook-alias-routing",
    "luaObjectRegistryRuntime": "lua-object-registry-runtime",
    "luaFunctionRegistryRuntime": "lua-function-registry-runtime",
    "luaDecodedObjectAliasesRuntime": "lua-decoded-object-aliases-runtime",
    "objectDiscoveryCoverage": "",
    "findObjectSemantics": "",
    "ueObjectArrayShape": "ue-object-array-shape",
    "ueObjectArrayRegistryRuntime": "ue-object-array-registry-runtime",
    "ueObjectNativeIdentities": "ue-object-native-identities",
    "ueObjectInternalFlags": "ue-object-internal-flags",
    "ueFNameDecoder": "ue-fname-decoder",
    "luaObjectOuterChainIdentities": "lua-object-outer-chain-identities",
    "luaObjectApi": "lua-object-api",
    "luaFunctionIterationRuntime": "lua-function-iteration-runtime",
    "ueReflectionPropertyDescriptorsRuntime": "ue-reflection-property-descriptors-runtime",
    "ueReflectionPropertyValuesRuntime": "ue-reflection-property-values-runtime",
    "luaReflectionForEachPropertyRuntime": "lua-reflection-for-each-property-runtime",
    "luaReflectionLiveDescriptorTypedClassRuntime": "lua-reflection-live-descriptor-typed-class-runtime",
    "luaReflectionLiveDescriptorTypedValuesRuntime": "lua-reflection-live-descriptor-typed-values-runtime",
    "luaReflectionLiveDescriptorTypedSetValuesRuntime": "lua-reflection-live-descriptor-typed-set-values-runtime",
    "luaReflectionLiveDescriptorValuesRuntime": "lua-reflection-live-descriptor-values-runtime",
    "luaLoadAssetPackageCrashGuard": "lua-load-asset-package-crash-guard",
    "luaLoadAssetPackageGuardedCall": "lua-load-asset-package-guarded-call",
    "luaLoadAssetPackageReturnValidation": "lua-load-asset-package-return-validation",
    "luaLoadAssetPackageNativeCallAdapter": "lua-load-asset-package-native-call-adapter",
    "luaLoadAssetPackageInvocationDescriptor": "lua-load-asset-package-invocation-descriptor",
    "luaLoadAssetPackageNativeExecutor": "lua-load-asset-package-native-executor",
    "luaLoadAssetPackage": "lua-load-asset-package",
}
STRICT_SIGNATURE_ANCHOR_READY_KEYS = (
    "signatureManifestExact",
    "signatureManifestPromotable",
    "anchorCoverageObjectDiscovery",
    "anchorCoverageHookPlanning",
    "anchorCoveragePackageLoading",
    "targetPackageLoadingSurface",
)
STRICT_SIGNATURE_ANCHOR_READY_KEY_GATES = {
    "signatureManifestExact": "signature-manifest-exact",
    "signatureManifestPromotable": "signature-manifest-promotable",
    "anchorCoverageObjectDiscovery": "anchor-coverage-object-discovery",
    "anchorCoverageHookPlanning": "anchor-coverage-hook-planning",
    "anchorCoveragePackageLoading": "anchor-coverage-package-loading",
    "targetPackageLoadingSurface": "ue-target-package-loading-surface",
}
LIVE_TARGET_IMAGE_CANARY_CONTRACT_GROUPS = {
    "targetImageAnchors": (
        "targetImageProcess",
        "runtimeRootDiscovery",
        "runtimeRootValidation",
        "targetObjectDiscovery",
        "targetHooks",
        "targetPackageLoadingSurface",
        "signatureManifestExact",
        "signatureManifestPromotable",
        "anchorCoverageObjectDiscovery",
        "anchorCoverageHookPlanning",
        "anchorCoveragePackageLoading",
    ),
    "runtimePackageLoading": (
        "luaLoadAssetPackageCrashGuard",
        "luaLoadAssetPackageGuardedCall",
        "luaLoadAssetPackageReturnValidation",
        "luaLoadAssetPackageNativeCallAdapter",
        "luaLoadAssetPackageInvocationDescriptor",
        "luaLoadAssetPackageNativeExecutor",
        "luaLoadAssetPackage",
    ),
    "runtimeObjectRegistry": (
        "objectDiscoveryCoverage",
        "findObjectSemantics",
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
    "runtimeReflection": (
        "ueReflectionPropertyDescriptorsRuntime",
        "ueReflectionPropertyValuesRuntime",
        "luaReflectionForEachPropertyRuntime",
        "luaReflectionLiveDescriptorTypedClassRuntime",
        "luaReflectionLiveDescriptorTypedValuesRuntime",
        "luaReflectionLiveDescriptorTypedSetValuesRuntime",
        "luaReflectionLiveDescriptorValuesRuntime",
    ),
    "runtimeProcessEventDispatch": (
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
    ),
    "runtimeCallFunctionDispatch": (
        "ueCallFunctionHookRuntimeTarget",
        "ueCallFunctionLiveHookRuntimeTarget",
        "ueCallFunctionLiveLuaDispatch",
    ),
}
CROSS_PLATFORM_REQUIRED_LOADERS = {
    "server": ("server", "linux-server"),
    "linux-client": ("linux-client", "client"),
    "windows": ("win-client", "windows", "windows-client"),
}


def import_script(script_name, module_name):
    script = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def env_prefix(platform):
    if platform == "server":
        return "DUNE_PROBE_LOADER"
    if platform == "windows":
        return "DUNE_WIN_CLIENT_PROBE"
    return "DUNE_CLIENT_PROBE"


def loader_name(platform):
    if platform == "server":
        return "server"
    if platform == "windows":
        return "win-client"
    return "linux-client"


def post_canary_loader_name(platform):
    if platform == "linux-client":
        return "client"
    return loader_name(platform)


def default_canary_log_path(platform):
    if platform == "server":
        return "/tmp/dune-server-probe-loader.log"
    if platform == "windows":
        return "/tmp/dune-win-client-probe-loader.log"
    return "/tmp/dune-client-probe-loader.log"


def readiness_log_arg_name(platform):
    if platform == "server":
        return "--server-log"
    return "--client-log"


def loader_filter(args):
    if args.loader:
        return args.loader
    if args.platform == "linux-client":
        return ["linux-client", "client"]
    return [loader_name(args.platform)]


def platform_loader_candidates(args):
    loaders = loader_filter(args)
    expanded = []
    for loader in loaders:
        expanded.append(loader)
        if loader == "linux-client":
            expanded.append("client")
        elif loader == "client":
            expanded.append("linux-client")
        elif loader == "windows":
            expanded.append("win-client")
        elif loader == "win-client":
            expanded.append("windows")
        elif loader == "linux-server":
            expanded.append("server")
        elif loader == "server":
            expanded.append("linux-server")
    ordered = []
    seen = set()
    for loader in expanded:
        if loader in seen:
            continue
        seen.add(loader)
        ordered.append(loader)
    return ordered


def scoped_report_for_platform(args, report):
    per_loader = report.get("perLoaderReadiness", {}) or {}
    selected_loader = ""
    selected_entry = None
    for loader in platform_loader_candidates(args):
        entry = per_loader.get(loader)
        if entry and int(entry.get("logCount", 0) or 0) > 0:
            selected_loader = loader
            selected_entry = entry
            break
    if not selected_entry:
        report = dict(report)
        report["selectedLoaderReadiness"] = {
            "available": False,
            "loader": "",
            "candidates": platform_loader_candidates(args),
            "reason": "no matching per-loader readiness entry",
        }
        return report

    scoped = loader_entry_report(report, selected_loader, selected_entry)
    scoped["selectedLoaderReadiness"] = {
        "available": True,
        "loader": selected_loader,
        "candidates": platform_loader_candidates(args),
        "paths": selected_entry.get("paths", []),
        "failedGates": selected_entry.get("failedGates", []),
    }
    return scoped


def default_alias_script_package(platform):
    if platform == "server":
        return "DuneServerProbe"
    return "DuneProbe"


def terminal_function_name(function_path):
    if not function_path:
        return ""
    value = function_path.rsplit("/", 1)[-1]
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    if value.endswith(":Function"):
        value = value[: -len(":Function")]
    return value


def is_script_function_path(path):
    return path.startswith("/Script/") and path.endswith(":Function") and "." in path


def script_package_name(hook_path):
    if not hook_path.startswith("/Script/"):
        return ""
    value = hook_path[len("/Script/") :]
    if "." not in value:
        return ""
    return value.split(".", 1)[0]


def live_lua_alias_script(hook_path):
    if not is_script_function_path(hook_path):
        return ""
    package_name = script_package_name(hook_path)
    if not package_name:
        return ""
    return (
        f"RegisterHook('/Script/{package_name}.NotTarget:Function', function() return -99 end, function() return -99 end); "
        f"return RegisterHook('{hook_path}', function() return 11 end, function() return 31 end)"
    )


def choose_alias_function_path(args, report):
    if args.live_lua_alias_function_path:
        return args.live_lua_alias_function_path
    hints = report.get("canaryHints", {})
    for path in hints.get("ueFunctionPaths", []):
        if terminal_function_name(path):
            return path
    for path in hints.get("ueFunctionFlagPaths", []):
        if terminal_function_name(path):
            return path
    return ""


def choose_alias_hook_path(args, report):
    if args.live_lua_alias_hook_path:
        return args.live_lua_alias_hook_path
    hints = report.get("canaryHints", {})
    for path in hints.get("ue4ssFunctionPaths", []):
        if is_script_function_path(path):
            return path
    function_path = choose_alias_function_path(args, report)
    function_name = terminal_function_name(function_path)
    if not function_name:
        return ""
    package_name = args.live_lua_alias_script_package or default_alias_script_package(args.platform)
    return f"/Script/{package_name}.{function_name}:Function"


def readiness_from_args(args):
    if args.readiness_json:
        return load_json(args.readiness_json)
    readiness = import_script("ue4ss-port-readiness.py", "ue4ss_port_readiness")
    log_paths = args.log + args.client_log + args.server_log
    if not log_paths:
        raise ValueError("provide --readiness-json, --log, --client-log, or --server-log")
    summaries = [
        readiness.summarize_log(path, loader_filter(args), args.pid, args.exe_substring)
        for path in log_paths
    ]
    validations = [load_json(path) for path in args.signature_validation_json]
    return readiness.build_report(summaries, validations)


def anchor_export_from_args(args):
    anchor_exporter = import_script("export-ue-anchor-env.py", "export_ue_anchor_env")
    log_paths = args.log + args.client_log + args.server_log
    if not log_paths:
        return None
    platform = {"server": "server", "linux-client": "linux", "windows": "windows"}[args.platform]
    return anchor_exporter.build_export(
        log_paths[0],
        loader_filter(args),
        args.pid,
        args.exe_substring,
        list(anchor_exporter.DEFAULT_ANCHORS),
        platform,
    )


def anchor_lines(anchor_export):
    if not anchor_export:
        return []
    anchor_exporter = import_script("export-ue-anchor-env.py", "export_ue_anchor_env")
    lines = []
    for line in anchor_exporter.env_text(anchor_export).splitlines():
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        if name == anchor_export.get("envName") and not unquote_shell_value(value):
            continue
        lines.append(line)
    return lines


def unquote_shell_value(value):
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("'\"'\"'", "'")
    return value


def parse_int(value, default=None):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def candidate_global_env_name(platform):
    return f"{env_prefix(platform)}_UE_CANDIDATE_GLOBALS"


def rejected_candidate_shape_pairs(candidate_shapes):
    rejected = set()
    for row in (candidate_shapes or {}).get("candidates", []) or []:
        verdict = row.get("verdict", "")
        if not (verdict.startswith("rejected") or verdict.startswith("weak")):
            continue
        name = row.get("name", "")
        offset = parse_int(row.get("imageOffset", ""))
        if name and offset is not None:
            rejected.add((name, offset))
    return rejected


def rejected_candidate_outcome_pairs(candidate_outcomes):
    rejected = set()
    for row in (candidate_outcomes or {}).get("candidates", []) or []:
        if row.get("verdict", "") not in {"rejected", "weak-false-positive"}:
            continue
        name = row.get("name", "")
        offset = parse_int(row.get("imageOffset", ""))
        if not name or offset is None:
            continue
        if row.get("runtimeRwFileOffset") == "true":
            rejected.add((name, offset, "rwfile"))
        else:
            rejected.add((name, offset))
    return rejected


def root_recovery_group_coverage(anchor_counts):
    coverage = {}
    for group_name, anchors in ROOT_RECOVERY_ANCHOR_GROUPS.items():
        emitted = [anchor for anchor in anchors if int(anchor_counts.get(anchor, 0) or 0) > 0]
        coverage[group_name] = {
            "knownAnchors": list(anchors),
            "emittedAnchors": emitted,
            "missingAnchors": [anchor for anchor in anchors if anchor not in emitted],
            "ready": bool(emitted),
            "complete": len(emitted) == len(anchors),
        }
    return coverage


def root_recovery_missing_groups(candidate_input, groups):
    missing = set(candidate_input.get("missingGroups", []) or [])
    return [group for group in groups if group in missing]


def root_candidate_qword_ref_count(row, root_shape):
    return int(row.get("qwordRefCount", root_shape.get("qwordRefCount", row.get("pointerLikeRefCount", 0))) or 0)


def root_candidate_kind_counts(row, root_shape):
    kind_counts = row.get("kindCounts", root_shape.get("kindCounts", {})) or {}
    if kind_counts:
        return kind_counts
    pointer_like = int(row.get("pointerLikeRefCount", 0) or 0)
    if pointer_like:
        return {"pointer-like": pointer_like}
    return {}


def root_candidate_is_qword_quality_ready(row):
    kind_counts = row.get("kindCounts") or {}
    if int(row.get("pointerLikeRefCount", 0) or 0) > 0:
        return True
    return (
        int(row.get("qwordRefCount", 0) or 0) > 0
        and int(kind_counts.get("read", 0) or 0) > 0
        and int(kind_counts.get("write", 0) or 0) > 0
    )


def root_recovery_candidate_input(args):
    manual_candidate_globals = list(getattr(args, "candidate_global", []) or [])
    candidate_input_paths = list(args.root_recovery_candidates_json) + list(getattr(args, "candidate_globals_json", []) or [])
    if not candidate_input_paths and not manual_candidate_globals:
        return {
            "provided": False,
            "sourcePaths": [],
            "sourceAnchorPresets": [],
            "candidateCount": 0,
            "emittedCount": 0,
            "filteredRejectedShapeCount": 0,
            "filteredRejectedOutcomeCount": 0,
            "filteredRejectedCandidateCount": 0,
            "envName": candidate_global_env_name(args.platform),
            "envValue": "",
            "anchorCounts": {},
            "groupCoverage": root_recovery_group_coverage({}),
            "missingGroups": list(ROOT_RECOVERY_ANCHOR_GROUPS),
            "candidates": [],
        }
    rejected_shapes = set()
    for path in args.candidate_shapes_json:
        rejected_shapes.update(rejected_candidate_shape_pairs(load_json(path)))
    rejected_outcomes = set()
    for path in args.candidate_outcomes_json:
        rejected_outcomes.update(rejected_candidate_outcome_pairs(load_json(path)))
    candidates = []
    source_anchor_presets = []
    for item in manual_candidate_globals:
        if "=" not in item:
            continue
        name_text, value_text = item.split("=", 1)
        name = name_text.strip()
        value = value_text.strip()
        if not name or not value:
            continue
        canonical_name = name
        address_mode = ""
        for suffix in ("@addr", "@rwfile"):
            if canonical_name.endswith(suffix):
                canonical_name = canonical_name[: -len(suffix)]
                address_mode = suffix[1:]
                break
        candidates.append(
            {
                "name": canonical_name,
                "imageOffset": value,
                "envEntry": f"{name}={value}",
                "addressMode": address_mode,
                "sourcePath": "<manual>",
                "hypothesis": "manual-candidate-global",
                "cluster": {},
                "score": 0,
                "qwordRefCount": 0,
                "pointerLikeRefCount": 0,
                "scalarRefCount": 0,
                "scalarRatio": 0.0,
                "addressRatio": 0.0,
                "kindCounts": {},
                "hintQuality": {},
                "sourceGroupCoverage": [],
                "anchorGroup": "",
                "anchorGroupMatched": None,
                "sourceName": "manual-candidate-global",
            }
        )
    for path in candidate_input_paths:
        summary = load_json(path)
        if summary.get("anchorPreset"):
            source_anchor_presets.append(summary["anchorPreset"])
        if summary.get("schemaVersion") == "dune-ue-candidate-globals/v1":
            source_anchor_presets.append("writable-global-candidates")
        for row in summary.get("candidates", []) or []:
            name = row.get("name", "")
            offset_text = row.get("imageOffset", "")
            offset = parse_int(offset_text)
            if not name or offset is None:
                continue
            root_shape = row.get("rootShape", {}) or {}
            kind_counts = root_candidate_kind_counts(row, root_shape)
            hint_quality = row.get("hintQuality", {}) or {}
            candidates.append(
                {
                    "name": name,
                    "imageOffset": f"0x{offset:x}",
                    "sourcePath": str(path),
                    "hypothesis": row.get("hypothesis", "root-recovery-writable-global"),
                    "cluster": row.get("cluster", {}),
                    "score": row.get("score", 0),
                    "qwordRefCount": root_candidate_qword_ref_count(row, root_shape),
                    "pointerLikeRefCount": int(row.get("pointerLikeRefCount", 0) or 0),
                    "scalarRefCount": int(row.get("scalarRefCount", root_shape.get("scalarRefCount", 0)) or 0),
                    "scalarRatio": float(row.get("scalarRatio", root_shape.get("scalarRatio", 0.0)) or 0.0),
                    "addressRatio": float(row.get("addressRatio", root_shape.get("addressRatio", 0.0)) or 0.0),
                    "kindCounts": kind_counts,
                    "hintQuality": hint_quality,
                    "sourceGroupCoverage": list(row.get("sourceGroupCoverage", []) or []),
                    "anchorGroup": row.get("anchorGroup", ""),
                    "anchorGroupMatched": row.get("anchorGroupMatched") if "anchorGroupMatched" in row else None,
                    "sourceName": row.get("sourceName", ""),
                }
            )
    emitted = []
    seen = set()
    filtered_shapes = 0
    filtered_outcomes = 0
    for row in candidates:
        name_offset_key = (row["name"], parse_int(row["imageOffset"]))
        key = (row["name"], parse_int(row["imageOffset"]), row.get("addressMode", ""))
        shape_rejected = name_offset_key in rejected_shapes or key in rejected_shapes
        outcome_rejected = name_offset_key in rejected_outcomes or key in rejected_outcomes
        if shape_rejected or outcome_rejected:
            if shape_rejected:
                filtered_shapes += 1
            if outcome_rejected:
                filtered_outcomes += 1
            continue
        if key in seen:
            continue
        seen.add(key)
        emitted.append(row)
    env_name = candidate_global_env_name(args.platform)
    env_value = ";".join(row.get("envEntry") or f"{row['name']}={row['imageOffset']}" for row in emitted)
    anchor_counts = dict(sorted(Counter(row["name"] for row in emitted).items()))
    group_coverage = root_recovery_group_coverage(anchor_counts)
    shape_classified = [row for row in emitted if row.get("qwordRefCount", 0) or row.get("scalarRefCount", 0)]
    qword_candidates = [
        row
        for row in emitted
        if root_candidate_is_qword_quality_ready(row)
    ]
    scalar_heavy_candidates = [
        row
        for row in emitted
        if float(row.get("scalarRatio", 0.0) or 0.0) > 0.10
    ]
    address_heavy_candidates = [
        row
        for row in emitted
        if float(row.get("addressRatio", 0.0) or 0.0) > 0.50
    ]
    hint_classified = [row for row in emitted if row.get("hintQuality")]
    exact_hint_candidates = [
        row
        for row in hint_classified
        if int((row.get("hintQuality") or {}).get("exactContextCount", 0) or 0) > 0
    ]
    specific_hint_candidates = [
        row
        for row in hint_classified
        if int((row.get("hintQuality") or {}).get("specificContextCount", 0) or 0) > 0
    ]
    generic_only_hint_candidates = [
        row
        for row in hint_classified
        if int((row.get("hintQuality") or {}).get("contextCount", 0) or 0) > 0
        and int((row.get("hintQuality") or {}).get("specificContextCount", 0) or 0) == 0
        and int((row.get("hintQuality") or {}).get("exactContextCount", 0) or 0) == 0
    ]
    source_group_classified = [
        row
        for row in emitted
        if row.get("anchorGroupMatched") is not None and bool(row.get("sourceGroupCoverage"))
    ]
    source_group_unmatched = [row for row in source_group_classified if not row.get("anchorGroupMatched")]
    return {
        "provided": True,
        "sourcePaths": [str(path) for path in candidate_input_paths],
        "sourceAnchorPresets": sorted(set(source_anchor_presets)),
        "shapeSourcePaths": [str(path) for path in args.candidate_shapes_json],
        "outcomeSourcePaths": [str(path) for path in args.candidate_outcomes_json],
        "candidateCount": len(candidates),
        "emittedCount": len(emitted),
        "filteredRejectedShapeCount": filtered_shapes + filtered_outcomes,
        "filteredRejectedCandidateCount": filtered_shapes + filtered_outcomes,
        "filteredRejectedShapeOnlyCount": filtered_shapes,
        "filteredRejectedOutcomeCount": filtered_outcomes,
        "envName": env_name,
        "envValue": env_value,
        "anchorCounts": anchor_counts,
        "shapeQuality": {
            "classifiedCount": len(shape_classified),
            "qwordReadWriteCandidateCount": len(qword_candidates),
            "qwordCandidateCount": len(qword_candidates),
            "scalarHeavyCandidateCount": len(scalar_heavy_candidates),
            "addressHeavyCandidateCount": len(address_heavy_candidates),
            "unclassifiedCount": max(0, len(emitted) - len(shape_classified)),
            "maxScalarRatio": max((float(row.get("scalarRatio", 0.0) or 0.0) for row in emitted), default=0.0),
            "maxAddressRatio": max((float(row.get("addressRatio", 0.0) or 0.0) for row in emitted), default=0.0),
        },
        "hintQuality": {
            "classifiedCount": len(hint_classified),
            "exactCandidateCount": len(exact_hint_candidates),
            "specificCandidateCount": len(specific_hint_candidates),
            "genericOnlyCandidateCount": len(generic_only_hint_candidates),
            "unclassifiedCount": max(0, len(emitted) - len(hint_classified)),
        },
        "sourceGroupQuality": {
            "classifiedCount": len(source_group_classified),
            "matchedCount": len(source_group_classified) - len(source_group_unmatched),
            "unmatchedCount": len(source_group_unmatched),
            "unclassifiedCount": max(0, len(emitted) - len(source_group_classified)),
        },
        "groupCoverage": group_coverage,
        "missingGroups": [name for name, group in group_coverage.items() if not group["ready"]],
        "candidates": emitted,
    }


def set_env(lines, name, value, reason):
    lines.append({"name": name, "value": value, "reason": reason})


def set_env_if_absent(lines, name, value, reason):
    if any(item["name"] == name for item in lines):
        return
    set_env(lines, name, value, reason)


def append_env_values(lines, name, values, reason):
    values = [value for value in values if value]
    if not values:
        return
    for item in lines:
        if item["name"] != name:
            continue
        existing = [value for value in str(item.get("value", "")).split(";") if value]
        merged = []
        seen = set()
        for value in existing + values:
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
        item["value"] = ";".join(merged)
        if reason not in item.get("reason", ""):
            item["reason"] = item.get("reason", "") + "; " + reason
        return
    set_env(lines, name, ";".join(values), reason)


def default_target_filter(platform):
    if platform == "server":
        return "DuneSandboxServer;DuneSandbox"
    if platform == "windows":
        return "DuneSandbox-Win64-Shipping.exe;DuneSandbox"
    return "DuneSandbox"


def scan_path_filter_env_name(prefix):
    return f"{prefix}_SCAN_PATH_FILTER"


def runtime_candidate_location_notes(discovery, limit=6):
    locations = discovery.get("candidateLocations") or []
    notes = []
    for location in locations[:limit]:
        name = location.get("name") or "candidate"
        address = location.get("addr") or "?"
        image_offset = location.get("imageOffset") or "?"
        image = location.get("map") or "?"
        notes.append(f"{name}@{address} offset={image_offset} image={image}")
    return notes


def runtime_candidate_location_is_target_image(location):
    verdict = str(location.get("targetImage", "")).lower()
    if verdict in {"1", "true", "yes", "on"}:
        return True
    if verdict in {"0", "false", "no", "off"}:
        return False
    image = location.get("map") or ""
    return bool(image and not image.startswith("["))


def runtime_candidate_carry_forward_entries(discovery, platform):
    locations = discovery.get("candidateLocations") or []
    by_name = defaultdict(list)
    for location in locations:
        name = location.get("name", "")
        if name in {"RuntimeFNamePool", "RuntimeGUObjectArray"}:
            by_name[name].append(location)

    entries = []
    for name, name_locations in sorted(by_name.items()):
        if len(name_locations) != 1:
            continue
        location = name_locations[0]
        image_offset = location.get("imageOffset", "")
        file_offset = location.get("fileOffset", "")
        if image_offset and runtime_candidate_location_is_target_image(location):
            entries.append(f"{name}={image_offset}")
        elif platform != "windows" and file_offset:
            entries.append(f"{name}@rwfile={file_offset}")
    return entries


def candidate_entry_name(entry):
    name, _, _ = entry.partition("=")
    for suffix in ("@addr", "@rwfile"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def runtime_candidate_carry_forward_summary(discovery, platform):
    entries = runtime_candidate_carry_forward_entries(discovery, platform)
    anchor_counts = dict(sorted(Counter(candidate_entry_name(entry) for entry in entries).items()))
    return {
        "provided": bool(entries),
        "envName": candidate_global_env_name(platform),
        "entries": entries,
        "entryCount": len(entries),
        "anchorCounts": anchor_counts,
        "groupCoverage": root_recovery_group_coverage(anchor_counts),
        "missingGroups": [
            group
            for group, coverage in root_recovery_group_coverage(anchor_counts).items()
            if not coverage.get("ready")
        ],
    }


def runtime_discovery_policy(report, platform):
    discovery = report.get("runtimeDiscovery") or report.get("ueRuntimeDiscovery") or {}
    failure_counts = discovery.get("failureCounts") or {}
    coverage = discovery.get("coverage") or {}
    candidate_counts = discovery.get("candidateNameCounts") or {}
    candidate_location_notes = runtime_candidate_location_notes(discovery)
    fname_candidates = int(candidate_counts.get("RuntimeFNamePool", 0) or 0)
    object_array_candidates = int(candidate_counts.get("RuntimeGUObjectArray", 0) or 0)
    fname_hits = int(coverage.get("fnameHits", 0) or 0)
    object_array_hits = int(coverage.get("objectArrayHits", 0) or 0)
    missing_fname = fname_candidates == 0 and fname_hits == 0
    missing_object_array = object_array_candidates == 0 and object_array_hits == 0
    ambiguous_fname = fname_candidates > 1 or fname_hits > 1
    ambiguous_object_array = object_array_candidates > 1 or object_array_hits > 1
    if not failure_counts:
        return {
            "failure": "",
            "maxBytes": "",
            "maxCandidates": "8",
            "minObjectArrayElements": "",
            "note": "",
            "candidateNotes": candidate_location_notes,
        }
    if failure_counts.get("no-target-writable-image"):
        return {
            "failure": "no-target-writable-image",
            "maxBytes": "1073741824",
            "maxCandidates": "8",
            "minObjectArrayElements": "",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Previous runtime discovery scanned no target writable image mappings/regions; "
                "widen the bounded auto-discovery region size for the next read-only canary."
            ),
        }
    if failure_counts.get("no-root-hits") or failure_counts.get("probe-not-run"):
        if missing_fname and not missing_object_array:
            return {
                "failure": "missing-fname-root",
                "maxBytes": "536870912",
                "maxCandidates": "32",
                "minObjectArrayElements": "",
                "candidateNotes": candidate_location_notes,
                "note": (
                    "Previous runtime discovery found GUObjectArray-shaped evidence but no RuntimeFNamePool "
                    "candidate; broaden the read-only mapping/region scan and retain a wider candidate set."
                ),
            }
        if missing_object_array and not missing_fname:
            return {
                "failure": "missing-object-array-root",
                "maxBytes": "536870912",
                "maxCandidates": "32",
                "minObjectArrayElements": "",
                "candidateNotes": candidate_location_notes,
                "note": (
                    "Previous runtime discovery found FNamePool-shaped evidence but no RuntimeGUObjectArray "
                    "candidate; broaden the read-only mapping/region scan and retain a wider candidate set."
                ),
            }
        return {
            "failure": "no-root-hits",
            "maxBytes": "536870912",
            "maxCandidates": "32",
            "minObjectArrayElements": "",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Previous runtime discovery scanned target image memory but did not find both root shapes; "
                "broaden candidate count and scan size for the next read-only canary."
            ),
        }
    if failure_counts.get("ambiguous-root-hits"):
        ambiguous_roots = []
        if ambiguous_fname:
            ambiguous_roots.append("RuntimeFNamePool")
        if ambiguous_object_array:
            ambiguous_roots.append("RuntimeGUObjectArray")
        root_note = " (" + ", ".join(ambiguous_roots) + ")" if ambiguous_roots else ""
        return {
            "failure": "ambiguous-root-hits",
            "maxBytes": "",
            "maxCandidates": "1",
            "minObjectArrayElements": "128" if ambiguous_object_array else "",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Previous runtime discovery found ambiguous root hits"
                + root_note
                + "; fail fast after the second hit "
                "and rely on candidate/outcome analysis before promotion."
            ),
        }
    if failure_counts.get("incomplete-promotion"):
        if missing_fname and not missing_object_array:
            return {
                "failure": "incomplete-promotion-missing-fname-root",
                "maxBytes": "",
                "maxCandidates": "16",
                "minObjectArrayElements": "",
                "candidateNotes": candidate_location_notes,
                "note": (
                    "Previous runtime discovery did not promote RuntimeFNamePool even though "
                    "RuntimeGUObjectArray evidence was present; keep auto-discovery read-only and collect "
                    "more FNamePool candidates."
                ),
            }
        if missing_object_array and not missing_fname:
            return {
                "failure": "incomplete-promotion-missing-object-array-root",
                "maxBytes": "",
                "maxCandidates": "16",
                "minObjectArrayElements": "",
                "candidateNotes": candidate_location_notes,
                "note": (
                    "Previous runtime discovery did not promote RuntimeGUObjectArray even though "
                    "RuntimeFNamePool evidence was present; keep auto-discovery read-only and collect "
                    "more object-array candidates."
                ),
            }
        return {
            "failure": "incomplete-promotion",
            "maxBytes": "",
            "maxCandidates": "16",
            "minObjectArrayElements": "",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Previous runtime discovery ran but did not promote the full root pair; keep auto-discovery "
                "read-only and collect a wider candidate set."
            ),
        }
    if failure_counts.get("not-run"):
        return {
            "failure": "not-run",
            "maxBytes": "",
            "maxCandidates": "8",
            "minObjectArrayElements": "",
            "candidateNotes": candidate_location_notes,
            "note": "Previous canary did not run runtime root auto-discovery; keep it enabled in the next plan.",
        }
    if coverage.get("targetWritableImageCount", 0) == 0 and discovery.get("startCount", 0):
        return {
            "failure": "no-target-writable-image",
            "maxBytes": "1073741824",
            "maxCandidates": "8",
            "minObjectArrayElements": "",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Runtime discovery started but reported zero target writable image mappings/regions; "
                "widen the bounded auto-discovery region size for the next read-only canary."
            ),
        }
    return {
        "failure": ",".join(sorted(failure_counts)),
        "maxBytes": "",
        "maxCandidates": "8",
        "minObjectArrayElements": "",
        "note": "",
        "candidateNotes": candidate_location_notes,
    }


def auto_discovery_max_bytes_env_name(prefix, platform):
    if platform == "windows":
        return f"{prefix}_UE_AUTO_DISCOVER_MAX_REGION_BYTES"
    return f"{prefix}_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES"


def add_blocker(blockers, notes, code, stage, message):
    blockers.append({"code": code, "stage": stage, "message": message})
    notes.append(message)


def max_stage_index(stage):
    return MAX_STAGES.index(stage)


def stage_allowed(args, stage):
    return max_stage_index(args.max_stage) >= max_stage_index(stage)


def gate(report, name):
    for item in report.get("gates", []):
        if item.get("name") == name:
            return bool(item.get("passed"))
    return False


def gate_present(report, name):
    return any(item.get("name") == name for item in report.get("gates", []))


def ready_or_gate(report, ready_name, gate_name):
    return bool(report.get("ready", {}).get(ready_name)) or gate(report, gate_name)


def runtime_ready(report, ready_name, gate_name):
    ready = report.get("ready", {})
    if ready_name in ready:
        return bool(ready.get(ready_name))
    if gate_present(report, gate_name):
        return gate(report, gate_name)
    return False


def runtime_registry_ready(report, ready_name, gate_name):
    return runtime_ready(report, ready_name, gate_name)


def strict_runtime_ready_map(report):
    return {
        ready_name: strict_runtime_ready(report, ready_name)
        for ready_name in STRICT_RUNTIME_READY_KEYS
    }


def strict_signature_anchor_ready_map(report):
    return {
        ready_name: strict_signature_anchor_ready(report, ready_name)
        for ready_name in STRICT_SIGNATURE_ANCHOR_READY_KEYS
    }


def live_target_image_canary_contract(strict_runtime_status, strict_signature_anchor_status):
    combined = {}
    combined.update(strict_runtime_status)
    combined.update(strict_signature_anchor_status)
    groups = {}
    for group_name, keys in LIVE_TARGET_IMAGE_CANARY_CONTRACT_GROUPS.items():
        missing = [key for key in keys if not combined.get(key)]
        groups[group_name] = {
            "ready": not missing,
            "requiredKeys": list(keys),
            "missingKeys": missing,
        }
    missing_all = [
        key
        for group in groups.values()
        for key in group["missingKeys"]
    ]
    return {
        "schemaVersion": "dune-ue4ss-live-target-image-canary-contract/v1",
        "ready": not missing_all,
        "groups": groups,
        "missingKeys": missing_all,
    }


def loader_entry_report(base_report, selected_loader, selected_entry):
    scoped = dict(base_report)
    scoped["logCount"] = selected_entry.get("logCount", base_report.get("logCount", 0))
    scoped["loaders"] = selected_entry.get("loaders") or [selected_loader]
    for key in (
        "ready",
        "gates",
        "anchorGroups",
        "anchorCoverage",
        "objectDiscoveryCoverage",
        "signatures",
        "ue",
        "canaryHints",
        "nextSteps",
    ):
        if key in selected_entry:
            scoped[key] = selected_entry[key]
    if "gates" not in selected_entry and "failedGates" in selected_entry:
        failed = set(selected_entry.get("failedGates", []) or [])
        gates = []
        for item in base_report.get("gates", []) or []:
            scoped_item = dict(item)
            scoped_item["passed"] = item.get("name") not in failed
            gates.append(scoped_item)
        scoped["gates"] = gates
    return scoped


def cross_platform_strict_runtime_contract(report):
    per_loader = report.get("perLoaderReadiness", {}) or {}
    loaders = {}
    missing_loaders = []
    failed_loaders = []
    for canonical, aliases in CROSS_PLATFORM_REQUIRED_LOADERS.items():
        selected_name = ""
        selected_entry = None
        for alias in aliases:
            entry = per_loader.get(alias)
            if entry and int(entry.get("logCount", 0) or 0) > 0:
                selected_name = alias
                selected_entry = entry
                break
        if not selected_entry:
            missing_loaders.append(canonical)
            loaders[canonical] = {
                "available": False,
                "loader": "",
                "aliases": list(aliases),
                "logCount": 0,
                "ready": False,
                "missingKeys": ["loaderReadiness"],
            }
            continue
        scoped = loader_entry_report(report, selected_name, selected_entry)
        runtime_status = strict_runtime_ready_map(scoped)
        signature_status = strict_signature_anchor_ready_map(scoped)
        live_contract = live_target_image_canary_contract(runtime_status, signature_status)
        missing_runtime = [key for key in STRICT_RUNTIME_READY_KEYS if not runtime_status[key]]
        missing_signature = [key for key in STRICT_SIGNATURE_ANCHOR_READY_KEYS if not signature_status[key]]
        loader_ready = bool(live_contract["ready"]) and not missing_runtime and not missing_signature
        if not loader_ready:
            failed_loaders.append(canonical)
        loaders[canonical] = {
            "available": True,
            "loader": selected_name,
            "aliases": list(aliases),
            "logCount": int(selected_entry.get("logCount", 0) or 0),
            "ready": loader_ready,
            "runtimeReady": not missing_runtime,
            "signatureAnchorReady": not missing_signature,
            "missingKeys": list(live_contract.get("missingKeys", []) or []),
            "missingReadyKeys": missing_runtime,
            "missingSignatureAnchorReadyKeys": missing_signature,
        }
    return {
        "schemaVersion": "dune-ue4ss-cross-platform-strict-runtime-contract/v1",
        "requiredLoaders": list(CROSS_PLATFORM_REQUIRED_LOADERS.keys()),
        "ready": not missing_loaders and not failed_loaders,
        "missingLoaders": missing_loaders,
        "failedLoaders": failed_loaders,
        "loaders": loaders,
    }


def object_registry_runtime_ready(report):
    return runtime_registry_ready(report, "luaObjectRegistryRuntime", "lua-object-registry-runtime")


def function_registry_runtime_ready(report):
    return runtime_registry_ready(report, "luaFunctionRegistryRuntime", "lua-function-registry-runtime")


def decoded_alias_registry_runtime_ready(report):
    return runtime_registry_ready(report, "luaDecodedObjectAliasesRuntime", "lua-decoded-object-aliases-runtime")


def object_array_registry_runtime_ready(report):
    return runtime_registry_ready(report, "ueObjectArrayRegistryRuntime", "ue-object-array-registry-runtime")


def all_object_registry_runtime_ready(report):
    return (
        object_registry_runtime_ready(report)
        and decoded_alias_registry_runtime_ready(report)
        and object_array_registry_runtime_ready(report)
    )


def lua_function_iteration_runtime_ready(report):
    return runtime_ready(report, "luaFunctionIterationRuntime", "lua-function-iteration-runtime")


def lua_reflection_live_descriptor_runtime_ready(report):
    return runtime_ready(
        report,
        "luaReflectionLiveDescriptorValuesRuntime",
        "lua-reflection-live-descriptor-values-runtime",
    )


def lua_reflection_for_each_property_runtime_ready(report):
    return runtime_ready(
        report,
        "luaReflectionForEachPropertyRuntime",
        "lua-reflection-for-each-property-runtime",
    )


def ue_reflection_property_descriptors_runtime_ready(report):
    return runtime_ready(
        report,
        "ueReflectionPropertyDescriptorsRuntime",
        "ue-reflection-property-descriptors-runtime",
    )


def ue_reflection_property_values_runtime_ready(report):
    return runtime_ready(
        report,
        "ueReflectionPropertyValuesRuntime",
        "ue-reflection-property-values-runtime",
    )


def lua_reflection_live_descriptor_typed_class_runtime_ready(report):
    return runtime_ready(
        report,
        "luaReflectionLiveDescriptorTypedClassRuntime",
        "lua-reflection-live-descriptor-typed-class-runtime",
    )


def lua_reflection_live_descriptor_typed_values_runtime_ready(report):
    return runtime_ready(
        report,
        "luaReflectionLiveDescriptorTypedValuesRuntime",
        "lua-reflection-live-descriptor-typed-values-runtime",
    )


def lua_reflection_live_descriptor_typed_set_values_runtime_ready(report):
    return runtime_ready(
        report,
        "luaReflectionLiveDescriptorTypedSetValuesRuntime",
        "lua-reflection-live-descriptor-typed-set-values-runtime",
    )


def command_text(argv):
    return " ".join(shell_quote(str(part)) if any(ch in str(part) for ch in (" ", "\t", "'", "\"", "$", "`", "\\")) else str(part) for part in argv)


def coverage_provided(report):
    return bool(report.get("anchorCoverage", {}).get("provided"))


def coverage_ready(report, ready_name, gate_name):
    if not coverage_provided(report):
        return True
    return ready_or_gate(report, ready_name, gate_name)


def anchor_group_counts(report):
    anchor_groups = report.get("anchorGroups", {}) or {}
    return {
        "anchors": dict(anchor_groups.get("anchors", {}) or {}),
        "mappedAnchors": dict(anchor_groups.get("mappedAnchors", {}) or {}),
        "signatures": dict(anchor_groups.get("signatures", {}) or {}),
        "resolvedSignatures": dict(anchor_groups.get("resolvedSignatures", {}) or {}),
    }


def anchor_group_evidence_present(report):
    counts = anchor_group_counts(report)
    return any(sum(int(value or 0) for value in group.values()) > 0 for group in counts.values())


def anchor_group_provenance_ready(report):
    ready = report.get("ready", {})
    if "anchorGroupProvenance" in ready:
        return bool(ready.get("anchorGroupProvenance"))
    if anchor_group_evidence_present(report):
        return False
    return not (
        ready.get("objectDiscovery")
        or ready.get("reflection")
        or ready.get("hookDispatch")
        or ready.get("hooks")
        or ready.get("luaDispatch")
    )


def ue_group_present(report, group_name, minimum=1):
    group = report.get("ue", {}).get("groups", {}).get(group_name, {})
    return int(group.get("present", 0) or 0) >= minimum


def ue_group_present_count(report, group_name):
    group = report.get("ue", {}).get("groups", {}).get(group_name, {})
    return int(group.get("present", 0) or 0)


def ue_group_target_present(report, group_name, minimum=1):
    group = report.get("ue", {}).get("groups", {}).get(group_name, {})
    if "targetPresent" in group:
        return int(group.get("targetPresent", 0) or 0) >= minimum
    return False


def ue_group_target_present_count(report, group_name):
    group = report.get("ue", {}).get("groups", {}).get(group_name, {})
    return int(group.get("targetPresent", 0) or 0)


def missing_groups(report, group_names, minimums=None):
    minimums = minimums or {}
    missing = []
    for group_name in group_names:
        minimum = minimums.get(group_name, 1)
        if ue_group_present_count(report, group_name) < minimum:
            missing.append(group_name)
    return missing


def missing_target_groups(report, group_names, minimums=None):
    minimums = minimums or {}
    ready = report.get("ready", {})
    missing = []
    for group_name in group_names:
        ready_name = {
            "names": "targetNames",
            "objects": "targetObjects",
            "world": "targetWorld",
            "dispatch": "targetDispatch",
            "package": "targetPackageLoadingSurface",
            "reflection": "targetReflectionSurface",
        }.get(group_name)
        if ready_name and ready.get(ready_name):
            continue
        if group_name == "reflection":
            gate_name = "ue-target-reflection-surface"
        elif group_name == "package":
            gate_name = "ue-target-package-loading-surface"
        else:
            gate_name = f"ue-target-{group_name}"
        if gate_present(report, gate_name) and gate(report, gate_name):
            continue
        minimum = minimums.get(group_name, 1)
        if ue_group_target_present_count(report, group_name) < minimum:
            missing.append(group_name)
    return missing


def proven_object_anchor_groups_ready(report):
    return (
        ue_group_present(report, "names")
        and ue_group_present(report, "objects")
        and ue_group_present(report, "world")
    )


def proven_dispatch_anchor_ready(report):
    return ue_group_present(report, "dispatch")


def proven_reflection_surface_ready(report):
    return ue_group_present(report, "reflection", minimum=2)


def proven_target_object_anchor_groups_ready(report):
    ready = report.get("ready", {})
    if "targetObjectDiscovery" in ready:
        return bool(ready.get("targetObjectDiscovery"))
    return not missing_target_groups(report, REQUIRED_HOOK_GROUPS)


def proven_target_dispatch_anchor_ready(report):
    ready = report.get("ready", {})
    if "targetDispatch" in ready:
        return bool(ready.get("targetDispatch"))
    return ue_group_target_present(report, "dispatch")


def proven_target_package_loading_ready(report):
    ready = report.get("ready", {})
    if "targetPackageLoadingSurface" in ready:
        return bool(ready.get("targetPackageLoadingSurface"))
    if gate_present(report, "ue-target-package-loading-surface"):
        return gate(report, "ue-target-package-loading-surface")
    return ue_group_target_present(report, "package")


def proven_target_hooks_ready(report):
    ready = report.get("ready", {})
    if "targetHooks" in ready:
        return bool(ready.get("targetHooks"))
    return proven_target_object_anchor_groups_ready(report) and proven_target_dispatch_anchor_ready(report)


def strict_runtime_ready(report, ready_name):
    if ready_name == "targetImageProcess":
        return runtime_ready(report, ready_name, STRICT_RUNTIME_READY_KEY_GATES[ready_name])
    if ready_name == "targetObjectDiscovery":
        return proven_target_object_anchor_groups_ready(report)
    if ready_name == "targetHooks":
        return proven_target_hooks_ready(report)
    if ready_name == "objectDiscoveryCoverage":
        coverage = report.get("objectDiscoveryCoverage", {}) or {}
        if "readyForObjectDiscovery" in coverage:
            return bool(coverage.get("readyForObjectDiscovery"))
        return bool((report.get("ready", {}) or {}).get("objectDiscoveryCoverage"))
    if ready_name == "findObjectSemantics":
        coverage = report.get("objectDiscoveryCoverage", {}) or {}
        if "readyForFindObjectSemantics" in coverage:
            return bool(coverage.get("readyForFindObjectSemantics"))
        return bool((report.get("ready", {}) or {}).get("findObjectSemantics"))
    return runtime_ready(report, ready_name, STRICT_RUNTIME_READY_KEY_GATES[ready_name])


def strict_signature_anchor_ready(report, ready_name):
    if ready_name == "targetPackageLoadingSurface":
        return proven_target_package_loading_ready(report)
    return runtime_ready(report, ready_name, STRICT_SIGNATURE_ANCHOR_READY_KEY_GATES[ready_name])


def choose_stage(report):
    ready = report.get("ready", {})
    if not anchor_group_provenance_ready(report):
        return "object-discovery"
    object_coverage = report.get("objectDiscoveryCoverage", {})
    object_anchor_blocks = ready.get("objectDiscovery") and not proven_object_anchor_groups_ready(report)
    target_object_anchor_blocks = ready.get("objectDiscovery") and not proven_target_object_anchor_groups_ready(report)
    dispatch_anchor_blocks = (ready.get("reflection") or ready.get("hookDispatch")) and not proven_dispatch_anchor_ready(report)
    target_dispatch_anchor_blocks = (ready.get("reflection") or ready.get("hookDispatch")) and not proven_target_dispatch_anchor_ready(report)
    reflection_anchor_blocks = ready.get("reflection") and not proven_reflection_surface_ready(report)
    coverage_blocks_object = not coverage_ready(
        report,
        "anchorCoverageObjectDiscovery",
        "anchor-coverage-object-discovery",
    )
    coverage_blocks_hooks = not coverage_ready(
        report,
        "anchorCoverageHookPlanning",
        "anchor-coverage-hook-planning",
    )
    if not ready.get("objectDiscovery"):
        return "object-discovery"
    if object_anchor_blocks:
        return "object-discovery"
    if target_object_anchor_blocks:
        return "object-discovery"
    if coverage_blocks_object:
        return "object-discovery"
    if object_coverage and not object_coverage.get("readyForObjectDiscovery", False):
        return "object-discovery"
    if object_coverage and not object_coverage.get("readyForFindObjectSemantics", False):
        return "object-discovery"
    if not all_object_registry_runtime_ready(report):
        return "object-discovery"
    if not ready.get("reflection"):
        return "reflection"
    if reflection_anchor_blocks or dispatch_anchor_blocks or target_dispatch_anchor_blocks:
        return "reflection"
    if coverage_blocks_hooks:
        return "reflection"
    if not function_registry_runtime_ready(report):
        return "reflection"
    if not ready.get("hookDispatch") and not gate(report, "hook-dispatch-self-test"):
        return "hook-probe"
    if not ready_or_gate(report, "ueProcessEventHookProbe", "ue-process-event-hook-probe"):
        return "hook-probe"
    if not runtime_ready(report, "ueProcessEventHookRuntimeTarget", "ue-process-event-hook-runtime-target"):
        return "hook-probe"
    if not runtime_ready(report, "ueCallFunctionHookRuntimeTarget", "ue-call-function-hook-runtime-target"):
        return "hook-probe"
    if not ready_or_gate(report, "ueProcessEventLiveHook", "ue-process-event-live-hook"):
        return "live-hook"
    if not runtime_ready(report, "ueProcessEventLiveHookRuntimeTarget", "ue-process-event-live-hook-runtime-target"):
        return "live-hook"
    if not ready_or_gate(report, "ueCallFunctionLiveHook", "ue-call-function-live-hook"):
        return "live-hook"
    if not runtime_ready(report, "ueCallFunctionLiveHookRuntimeTarget", "ue-call-function-live-hook-runtime-target"):
        return "live-hook"
    if not ready_or_gate(report, "ueProcessEventDispatch", "ue-process-event-dispatch-self-test"):
        return "live-hook"
    if not runtime_ready(report, "ueProcessEventLiveRuntimeContext", "ue-process-event-live-runtime-context"):
        return "live-hook"
    if not runtime_ready(report, "ueProcessEventLiveRuntimeRegistryContext", "ue-process-event-live-runtime-registry-context"):
        return "live-hook"
    if not ready_or_gate(report, "ueCallFunctionLiveLuaDispatch", "ue-call-function-live-lua-dispatch"):
        return "lua-dispatch"
    if not ready_or_gate(
        report,
        "ueProcessEventContainerStorageLayoutMethods",
        "ue-process-event-container-storage-layout-methods",
    ):
        return "lua-dispatch"
    if not lua_reflection_for_each_property_runtime_ready(report):
        return "lua-dispatch"
    if not lua_reflection_live_descriptor_typed_class_runtime_ready(report):
        return "lua-dispatch"
    if not lua_reflection_live_descriptor_typed_values_runtime_ready(report):
        return "lua-dispatch"
    if not lua_reflection_live_descriptor_typed_set_values_runtime_ready(report):
        return "lua-dispatch"
    if not lua_reflection_live_descriptor_runtime_ready(report):
        return "lua-dispatch"
    if not lua_function_iteration_runtime_ready(report):
        return "lua-dispatch"
    if not ready.get("luaDispatch"):
        return "lua-dispatch"
    return "complete"


def build_canary_contract(args, report, stage, env_items, blockers, root_candidate_input=None):
    prefix = env_prefix(args.platform)
    root_candidate_input = root_candidate_input or root_recovery_candidate_input(args)
    runtime_carry_forward = runtime_candidate_carry_forward_summary(
        report.get("runtimeDiscovery") or report.get("ueRuntimeDiscovery") or {},
        args.platform,
    )
    object_missing = missing_groups(report, REQUIRED_OBJECT_DISCOVERY_GROUPS)
    hook_missing = missing_groups(report, REQUIRED_HOOK_GROUPS)
    reflection_missing = missing_groups(
        report,
        ("reflection",),
        {"reflection": REQUIRED_REFLECTION_MINIMUM},
    )
    target_object_missing = missing_target_groups(report, REQUIRED_HOOK_GROUPS)
    target_hook_missing = missing_target_groups(report, REQUIRED_HOOK_GROUPS)
    target_package_missing = missing_target_groups(report, ("package",))
    anchor_coverage = report.get("anchorCoverage", {}) or {}
    object_coverage = report.get("objectDiscoveryCoverage", {}) or {}
    signature = report.get("signatures", {}) or {}
    ready = report.get("ready", {}) or {}
    env_names = [item["name"] for item in env_items]
    post_canary_log = default_canary_log_path(args.platform)
    readiness_command = [
        "python3",
        "scripts/ue4ss-port-readiness.py",
        readiness_log_arg_name(args.platform),
        post_canary_log,
        "--loader",
        post_canary_loader_name(args.platform),
        "--signature-validation-json",
        "signature-validation.json",
        "--anchor-coverage-json",
        "anchor-coverage.json",
        "--format",
        "json",
    ]
    strict_runtime_status = strict_runtime_ready_map(report)
    missing_strict_runtime_keys = [
        key for key in STRICT_RUNTIME_READY_KEYS
        if not strict_runtime_status[key]
    ]
    strict_signature_anchor_status = strict_signature_anchor_ready_map(report)
    missing_strict_signature_anchor_keys = [
        key for key in STRICT_SIGNATURE_ANCHOR_READY_KEYS
        if not strict_signature_anchor_status[key]
    ]
    live_target_image_contract = live_target_image_canary_contract(
        strict_runtime_status,
        strict_signature_anchor_status,
    )
    cross_platform_contract = cross_platform_strict_runtime_contract(report)
    required_validation = []
    if object_missing:
        required_validation.append("resolved-or-explicit names/object/world anchors")
    if hook_missing:
        required_validation.append("resolved-or-explicit dispatch anchor before hook probes")
    if target_object_missing:
        required_validation.append("target-image names/object/world/dispatch anchors")
    if target_hook_missing:
        required_validation.append("target-image dispatch anchor before hook probes")
    if target_package_missing:
        required_validation.append("target-image StaticLoadObject/LoadObject/LoadPackage/ResolveName package-loading anchor")
    if reflection_missing:
        required_validation.append("at least two resolved-or-explicit reflection anchors")
    if not anchor_group_provenance_ready(report):
        required_validation.append("loader-normalized UE anchor group provenance")
    runtime_validation_relevant = (
        stage in ("hook-probe", "live-hook", "lua-dispatch", "complete")
        or ready.get("hooks")
        or ready.get("luaDispatch")
        or ready.get("ueProcessEventHookProbe")
        or ready.get("ueCallFunctionHookProbe")
        or ready.get("ueProcessEventLiveHook")
    )
    if runtime_validation_relevant and not runtime_ready(report, "ueProcessEventHookRuntimeTarget", "ue-process-event-hook-runtime-target"):
        required_validation.append("non-self-test ProcessEvent hook probe target")
    if runtime_validation_relevant and not runtime_ready(report, "ueCallFunctionHookRuntimeTarget", "ue-call-function-hook-runtime-target"):
        required_validation.append("non-self-test CallFunctionByNameWithArguments hook probe target")
    if runtime_validation_relevant and not runtime_ready(report, "ueCallFunctionLiveHookRuntimeTarget", "ue-call-function-live-hook-runtime-target"):
        required_validation.append("non-self-test persistent CallFunctionByNameWithArguments hook target")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "ueCallFunctionLiveLuaDispatch",
        "ue-call-function-live-lua-dispatch",
    ):
        required_validation.append("live CallFunctionByNameWithArguments Lua dispatch")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "ueProcessEventContainerStorageLayoutMethods",
        "ue-process-event-container-storage-layout-methods",
    ):
        required_validation.append("ProcessEvent Lua container storage-layout method evidence")
    process_event_lua_dispatch_required = stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")
    if process_event_lua_dispatch_required:
        process_event_dispatch_checks = (
            (
                "ueProcessEventLiveFunctionPath",
                "ue-process-event-live-function-path",
                "decoded live ProcessEvent function path evidence",
            ),
            (
                "ueProcessEventLiveRegistryContext",
                "ue-process-event-live-registry-context",
                "live ProcessEvent promoted object/function registry context",
            ),
            (
                "ueProcessEventLiveRawParamValues",
                "ue-process-event-live-raw-param-values",
                "live ProcessEvent raw param byte samples",
            ),
            (
                "ueProcessEventLiveContainerParamValues",
                "ue-process-event-live-container-param-values",
                "live ProcessEvent typed container param headers",
            ),
            (
                "ueProcessEventLiveArrayContainerParamValues",
                "ue-process-event-live-array-container-param-values",
                "live ProcessEvent TArray/FScriptArray param headers",
            ),
            (
                "ueProcessEventLiveSetContainerParamValues",
                "ue-process-event-live-set-container-param-values",
                "live ProcessEvent TSet/FScriptSet param headers",
            ),
            (
                "ueProcessEventLiveMapContainerParamValues",
                "ue-process-event-live-map-container-param-values",
                "live ProcessEvent TMap/FScriptMap param headers",
            ),
            (
                "ueProcessEventLiveSetMapContainerParamValues",
                "ue-process-event-live-set-map-container-param-values",
                "live ProcessEvent set/map container layout evidence",
            ),
            (
                "ueProcessEventLiveContainerDataSamples",
                "ue-process-event-live-container-data-samples",
                "live ProcessEvent readable container data-pointer samples",
            ),
            (
                "ueProcessEventLuaContextHandles",
                "ue-process-event-lua-context-handles",
                "live ProcessEvent Lua UObject/UFunction/params context handles",
            ),
            (
                "ueProcessEventLuaParamAccessors",
                "ue-process-event-lua-param-accessors",
                "ProcessEvent Lua descriptor-backed param accessors in self-test and live hook",
            ),
            (
                "ueProcessEventFunctionParamMethod",
                "ue-process-event-function-param-method",
                "ProcessEvent ctx.Function:GetFunctionParams method evidence",
            ),
            (
                "ueProcessEventFunctionParamLookupMethod",
                "ue-process-event-function-param-lookup-method",
                "ProcessEvent ctx.Function:GetParamDescriptor method evidence",
            ),
            (
                "ueProcessEventFunctionParamIterationMethod",
                "ue-process-event-function-param-iteration-method",
                "ProcessEvent ctx.Function:ForEachParam method evidence",
            ),
            (
                "ueProcessEventContainerAliasMethods",
                "ue-process-event-container-alias-methods",
                "ProcessEvent container Get/get and key/value alias methods",
            ),
            (
                "ueProcessEventLuaScalarParamAccessors",
                "ue-process-event-lua-scalar-param-accessors",
                "ProcessEvent scalar param get/set accessor coverage",
            ),
            (
                "ueProcessEventLuaNameStringParamAccessors",
                "ue-process-event-lua-name-string-param-accessors",
                "ProcessEvent FName/FString param get/set accessor coverage",
            ),
            (
                "ueProcessEventLuaStructParamAccessors",
                "ue-process-event-lua-struct-param-accessors",
                "ProcessEvent struct param get/set accessor coverage",
            ),
            (
                "ueProcessEventLuaEnumParamAccessors",
                "ue-process-event-lua-enum-param-accessors",
                "ProcessEvent enum param get/set accessor coverage",
            ),
            (
                "ueProcessEventLuaObjectParamAccessors",
                "ue-process-event-lua-object-param-accessors",
                "ProcessEvent object param get/set accessor coverage",
            ),
            (
                "ueProcessEventLuaBoolParamAccessors",
                "ue-process-event-lua-bool-param-accessors",
                "ProcessEvent bool param get/set accessor coverage",
            ),
        )
        for ready_key, gate_name, description in process_event_dispatch_checks:
            if not ready_or_gate(report, ready_key, gate_name):
                required_validation.append(description)
    if runtime_validation_relevant and not runtime_ready(report, "ueProcessEventLiveHookRuntimeTarget", "ue-process-event-live-hook-runtime-target"):
        required_validation.append("non-self-test persistent ProcessEvent hook target")
    process_event_live_context_relevant = (
        stage in ("live-hook", "lua-dispatch", "complete")
        or ready.get("ueProcessEventLiveHook")
        or ready.get("luaDispatch")
    )
    if process_event_live_context_relevant and not ready_or_gate(report, "ueProcessEventLiveFunctionPath", "ue-process-event-live-function-path"):
        required_validation.append("decoded live ProcessEvent function path evidence")
    if runtime_validation_relevant and not runtime_ready(report, "ueProcessEventLiveRuntimeContext", "ue-process-event-live-runtime-context"):
        required_validation.append("non-self-test live ProcessEvent runtime context")
    if runtime_validation_relevant and not runtime_ready(report, "ueProcessEventLiveRuntimeRegistryContext", "ue-process-event-live-runtime-registry-context"):
        required_validation.append("non-self-test live ProcessEvent registry context")
    if process_event_live_context_relevant and not ready_or_gate(report, "ueProcessEventLiveParamValues", "ue-process-event-live-param-values"):
        required_validation.append("live ProcessEvent descriptor-backed param values")
    if process_event_live_context_relevant and not ready_or_gate(report, "ueProcessEventLuaContextHandles", "ue-process-event-lua-context-handles"):
        required_validation.append("live ProcessEvent Lua UObject/UFunction/params context handles")
    if not object_registry_runtime_ready(report):
        required_validation.append("non-self-test UObject registry evidence")
        required_validation.append("UObject registry log rows with registryProvenance=runtime")
    if not decoded_alias_registry_runtime_ready(report):
        required_validation.append("non-self-test decoded UObject alias registry evidence")
        required_validation.append("decoded UObject alias log rows with registryProvenance=runtime")
    if not object_array_registry_runtime_ready(report):
        required_validation.append("non-self-test object-array registry evidence")
        required_validation.append("object-array registry log rows with registryProvenance=runtime")
    if not function_registry_runtime_ready(report):
        required_validation.append("non-self-test UFunction registry evidence")
        required_validation.append("UFunction registry log rows with registryProvenance=runtime")
    function_runtime_relevant = (
        stage in ("reflection", "hook-probe", "live-hook", "lua-dispatch", "complete")
        or ready.get("runtimeRootValidation")
        or ready.get("reflection")
        or ready.get("luaDispatch")
    )
    if function_runtime_relevant and not ready_or_gate(report, "ueFunctionParamDescriptors", "ue-function-param-descriptors"):
        required_validation.append("readable UFunction param descriptor evidence from functionLink")
    if function_runtime_relevant and not ready_or_gate(report, "ueFunctionParamContainerChildren", "ue-function-param-container-children"):
        required_validation.append("decoded UFunction container child property evidence")
    if function_runtime_relevant and not ready_or_gate(report, "ueFunctionIdentities", "ue-function-identities"):
        required_validation.append("decoded UFunction path identity evidence")
    if function_runtime_relevant and not ready_or_gate(report, "ueFunctionNativeIdentities", "ue-function-native-identities"):
        required_validation.append("promoted UFunction native identity evidence")
    if function_runtime_relevant and not ready_or_gate(report, "ueFunctionFlags", "ue-function-flags"):
        required_validation.append("readable UFunction FunctionFlags evidence")
    if (stage in ("reflection", "lua-dispatch", "complete") or ready.get("reflection")) and not ue_reflection_property_descriptors_runtime_ready(report):
        required_validation.append("non-self-test native FProperty descriptor probe evidence")
    if (stage in ("reflection", "lua-dispatch", "complete") or ready.get("reflection")) and not ue_reflection_property_values_runtime_ready(report):
        required_validation.append("non-self-test native reflected property value probe evidence")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not lua_function_iteration_runtime_ready(report):
        required_validation.append("non-self-test ForEachFunction owner iteration evidence")
        required_validation.append("ForEachFunction owner iteration log rows with registryProvenance=runtime")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not lua_reflection_for_each_property_runtime_ready(report):
        required_validation.append("non-self-test Reflection():ForEachProperty descriptor enumeration evidence")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not lua_reflection_live_descriptor_typed_class_runtime_ready(report):
        required_validation.append("non-self-test live reflection descriptor decoded FProperty class evidence")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not lua_reflection_live_descriptor_typed_values_runtime_ready(report):
        required_validation.append("non-self-test live reflection descriptor typed GetValue evidence")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not lua_reflection_live_descriptor_typed_set_values_runtime_ready(report):
        required_validation.append("non-self-test live reflection descriptor typed SetValue evidence")
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not lua_reflection_live_descriptor_runtime_ready(report):
        required_validation.append("non-self-test live reflection descriptor GetValue/SetValue evidence")
    if not signature.get("provided"):
        required_validation.append("same-build signature validation JSON")
    elif not signature.get("allPromotable"):
        required_validation.append("all promoted signature rows must be unique-expected or otherwise promotable")
    missing_object_components = list(object_coverage.get("missingObjectDiscoveryComponents", []) or [])
    missing_find_object_components = list(object_coverage.get("missingFindObjectComponents", []) or [])
    if missing_object_components:
        required_validation.append("object-discovery coverage components: " + ", ".join(missing_object_components))
    if missing_find_object_components:
        required_validation.append("FindObject semantics coverage components: " + ", ".join(missing_find_object_components))
    if root_candidate_input.get("provided") and root_candidate_input.get("emittedCount"):
        required_validation.append("runtime candidate-global shape report for root-recovery hypotheses")
        shape_quality = root_candidate_input.get("shapeQuality", {}) or {}
        if int(shape_quality.get("qwordCandidateCount", 0) or 0) == 0:
            required_validation.append("qword-filtered root-recovery candidates before live canary")
        if int(shape_quality.get("scalarHeavyCandidateCount", 0) or 0) > 0:
            required_validation.append("remove scalar-heavy writable-root candidates before live canary")
        if int(shape_quality.get("addressHeavyCandidateCount", 0) or 0) > 0:
            required_validation.append("remove address-heavy writable-root candidates before live canary")
        hint_quality = root_candidate_input.get("hintQuality", {}) or {}
        if int(hint_quality.get("genericOnlyCandidateCount", 0) or 0) > 0:
            required_validation.append("non-generic or exact-anchor root-recovery context before live canary")
        source_group_quality = root_candidate_input.get("sourceGroupQuality", {}) or {}
        if int(source_group_quality.get("unmatchedCount", 0) or 0) > 0:
            required_validation.append("source-group-matched root-recovery candidates for requested anchor groups")
        missing_root_groups = list(root_candidate_input.get("missingGroups", []) or [])
        if missing_root_groups:
            required_validation.append("root-recovery candidate groups: " + ", ".join(missing_root_groups))

    return {
        "schemaVersion": "dune-ue4ss-next-canary-contract/v1",
        "platform": args.platform,
        "loader": loader_name(args.platform),
        "selectedStage": stage,
        "maxStage": args.max_stage,
        "readOnlyUntil": {
            "objectDiscoveryAnchors": not object_missing,
            "targetObjectDiscoveryAnchors": not target_object_missing,
            "hookPlanningAnchors": not hook_missing,
            "targetHookPlanningAnchors": not target_hook_missing,
            "targetPackageLoadingAnchors": not target_package_missing,
            "reflectionSurface": not reflection_missing,
            "signatureValidation": bool(signature.get("provided")) and bool(signature.get("allPromotable")),
        },
        "requiredAnchorGroups": {
            "objectDiscovery": list(REQUIRED_OBJECT_DISCOVERY_GROUPS),
            "hookPlanning": list(REQUIRED_HOOK_GROUPS),
            "reflectionMinimum": REQUIRED_REFLECTION_MINIMUM,
        },
        "missingAnchorGroups": {
            "objectDiscovery": object_missing,
            "targetObjectDiscovery": target_object_missing,
            "hookPlanning": hook_missing,
            "targetHookPlanning": target_hook_missing,
            "targetPackageLoading": target_package_missing,
            "reflection": reflection_missing,
        },
        "currentAnchorGroupCounts": {
            group_name: ue_group_present_count(report, group_name)
            for group_name in CORE_ANCHOR_GROUPS
        },
        "currentTargetAnchorGroupCounts": {
            group_name: ue_group_target_present_count(report, group_name)
            for group_name in CORE_ANCHOR_GROUPS
        },
        "anchorGroupProvenance": {
            "ready": anchor_group_provenance_ready(report),
            "evidencePresent": anchor_group_evidence_present(report),
            "groups": anchor_group_counts(report),
        },
        "signatureValidation": {
            "provided": bool(signature.get("provided")),
            "patternCount": int(signature.get("patternCount", 0) or 0),
            "promotableCount": int(signature.get("promotableCount", 0) or 0),
            "allPromotable": bool(signature.get("allPromotable")),
            "exactOnly": bool(signature.get("exactOnly")),
        },
        "preparedAnchorCoverage": {
            "provided": bool(anchor_coverage.get("provided")),
            "readyForObjectDiscovery": bool(anchor_coverage.get("readyForObjectDiscovery")),
            "readyForHookPlanning": bool(anchor_coverage.get("readyForHookPlanning")),
            "readyForPackageLoading": bool(anchor_coverage.get("readyForPackageLoading")),
            "missingRequiredGroups": list(anchor_coverage.get("missingRequiredGroups", []) or []),
        },
        "rootRecoveryCandidateInput": {
            "provided": bool(root_candidate_input.get("provided")),
            "sourcePaths": list(root_candidate_input.get("sourcePaths", []) or []),
            "sourceAnchorPresets": list(root_candidate_input.get("sourceAnchorPresets", []) or []),
            "shapeSourcePaths": list(root_candidate_input.get("shapeSourcePaths", []) or []),
            "outcomeSourcePaths": list(root_candidate_input.get("outcomeSourcePaths", []) or []),
            "candidateCount": int(root_candidate_input.get("candidateCount", 0) or 0),
            "emittedCount": int(root_candidate_input.get("emittedCount", 0) or 0),
            "filteredRejectedShapeCount": int(root_candidate_input.get("filteredRejectedShapeCount", 0) or 0),
            "filteredRejectedCandidateCount": int(root_candidate_input.get("filteredRejectedCandidateCount", 0) or 0),
            "filteredRejectedShapeOnlyCount": int(root_candidate_input.get("filteredRejectedShapeOnlyCount", 0) or 0),
            "filteredRejectedOutcomeCount": int(root_candidate_input.get("filteredRejectedOutcomeCount", 0) or 0),
            "envName": root_candidate_input.get("envName", candidate_global_env_name(args.platform)),
            "anchorCounts": dict(root_candidate_input.get("anchorCounts", {}) or {}),
            "shapeQuality": dict(root_candidate_input.get("shapeQuality", {}) or {}),
            "hintQuality": dict(root_candidate_input.get("hintQuality", {}) or {}),
            "sourceGroupQuality": dict(root_candidate_input.get("sourceGroupQuality", {}) or {}),
            "groupCoverage": dict(root_candidate_input.get("groupCoverage", {}) or {}),
            "missingGroups": list(root_candidate_input.get("missingGroups", []) or []),
        },
        "runtimeCandidateCarryForward": runtime_carry_forward,
        "postCanaryVerification": {
            "schemaVersion": "dune-ue4ss-post-canary-verification/v1",
            "defaultLogPath": post_canary_log,
            "readinessCommand": readiness_command,
            "readinessCommandText": command_text(readiness_command),
            "strictRuntimeContract": {
                "envName": "DUNE_UE4SS_STRICT_RUNTIME_CONTRACT",
                "enabledValue": "true",
                "contractReady": bool(live_target_image_contract["ready"]),
                "runtimeReady": not missing_strict_runtime_keys,
                "signatureAnchorReady": not missing_strict_signature_anchor_keys,
                "ready": strict_runtime_status,
                "signatureAnchorReadyKeys": strict_signature_anchor_status,
                "requiredReadyKeys": list(STRICT_RUNTIME_READY_KEYS),
                "requiredSignatureAnchorReadyKeys": list(STRICT_SIGNATURE_ANCHOR_READY_KEYS),
                "missingReadyKeys": missing_strict_runtime_keys,
                "missingSignatureAnchorReadyKeys": missing_strict_signature_anchor_keys,
            },
            "liveTargetImageCanaryContract": live_target_image_contract,
            "crossPlatformStrictRuntimeContract": cross_platform_contract,
            "inputFiles": {
                "loaderLog": post_canary_log,
                "signatureValidation": "signature-validation.json",
                "anchorCoverage": "anchor-coverage.json",
            },
            "outputFiles": {
                "readinessJson": "ue4ss-readiness.json",
                "objectDiscoveryCoverage": "object-discovery-coverage.json",
                "postCanaryGapSummaryJson": "ue4ss-port-gaps.json",
                "postCanaryGapSummary": "ue4ss-port-gaps.md",
                "postCanarySummary": "post-canary-summary.md",
            },
        },
        "objectDiscoveryCoverage": {
            "provided": bool(object_coverage),
            "readyForObjectDiscovery": bool(object_coverage.get("readyForObjectDiscovery")),
            "readyForFindObjectSemantics": bool(object_coverage.get("readyForFindObjectSemantics")),
            "missingObjectDiscoveryComponents": missing_object_components,
            "missingFindObjectComponents": missing_find_object_components,
        },
        "processEventRuntimeEvidence": {
            "hookRuntimeTarget": runtime_ready(
                report,
                "ueProcessEventHookRuntimeTarget",
                "ue-process-event-hook-runtime-target",
            ),
            "liveHookRuntimeTarget": runtime_ready(
                report,
                "ueProcessEventLiveHookRuntimeTarget",
                "ue-process-event-live-hook-runtime-target",
            ),
            "liveFunctionPath": ready_or_gate(
                report,
                "ueProcessEventLiveFunctionPath",
                "ue-process-event-live-function-path",
            ),
            "liveRuntimeContext": runtime_ready(
                report,
                "ueProcessEventLiveRuntimeContext",
                "ue-process-event-live-runtime-context",
            ),
            "liveRegistryContext": ready_or_gate(
                report,
                "ueProcessEventLiveRegistryContext",
                "ue-process-event-live-registry-context",
            ),
            "liveRuntimeRegistryContext": runtime_ready(
                report,
                "ueProcessEventLiveRuntimeRegistryContext",
                "ue-process-event-live-runtime-registry-context",
            ),
            "liveParamValues": ready_or_gate(
                report,
                "ueProcessEventLiveParamValues",
                "ue-process-event-live-param-values",
            ),
            "liveRawParamValues": ready_or_gate(
                report,
                "ueProcessEventLiveRawParamValues",
                "ue-process-event-live-raw-param-values",
            ),
            "liveContainerParamValues": ready_or_gate(
                report,
                "ueProcessEventLiveContainerParamValues",
                "ue-process-event-live-container-param-values",
            ),
            "liveContainerDataSamples": ready_or_gate(
                report,
                "ueProcessEventLiveContainerDataSamples",
                "ue-process-event-live-container-data-samples",
            ),
            "luaContextHandles": ready_or_gate(
                report,
                "ueProcessEventLuaContextHandles",
                "ue-process-event-lua-context-handles",
            ),
            "luaParamAccessors": ready_or_gate(
                report,
                "ueProcessEventLuaParamAccessors",
                "ue-process-event-lua-param-accessors",
            ),
            "liveClassAwareParamValues": ready_or_gate(
                report,
                "ueProcessEventLiveClassAwareParamValues",
                "ue-process-event-live-class-aware-param-values",
            ),
        },
        "processEventRuntimeEvidenceContract": PROCESS_EVENT_RUNTIME_LOG_CONTRACT,
        "callFunctionRuntimeEvidence": {
            "hookRuntimeTarget": runtime_ready(
                report,
                "ueCallFunctionHookRuntimeTarget",
                "ue-call-function-hook-runtime-target",
            ),
            "liveHookRuntimeTarget": runtime_ready(
                report,
                "ueCallFunctionLiveHookRuntimeTarget",
                "ue-call-function-live-hook-runtime-target",
            ),
            "liveLuaDispatch": ready_or_gate(
                report,
                "ueCallFunctionLiveLuaDispatch",
                "ue-call-function-live-lua-dispatch",
            ),
        },
        "callFunctionRuntimeEvidenceContract": CALL_FUNCTION_RUNTIME_LOG_CONTRACT,
        "registryRuntimeEvidence": {
            "luaObjectRegistryRuntime": object_registry_runtime_ready(report),
            "luaFunctionRegistryRuntime": function_registry_runtime_ready(report),
            "luaDecodedObjectAliasesRuntime": decoded_alias_registry_runtime_ready(report),
            "ueObjectArrayRegistryRuntime": object_array_registry_runtime_ready(report),
            "luaFunctionIterationRuntime": lua_function_iteration_runtime_ready(report),
        },
        "registryRuntimeEvidenceContract": REGISTRY_RUNTIME_LOG_CONTRACT,
        "functionRuntimeEvidence": {
            "ueFunctionParamDescriptors": ready_or_gate(report, "ueFunctionParamDescriptors", "ue-function-param-descriptors"),
            "ueFunctionParamContainerChildren": ready_or_gate(
                report,
                "ueFunctionParamContainerChildren",
                "ue-function-param-container-children",
            ),
            "ueFunctionIdentities": ready_or_gate(report, "ueFunctionIdentities", "ue-function-identities"),
            "ueFunctionNativeIdentities": ready_or_gate(
                report,
                "ueFunctionNativeIdentities",
                "ue-function-native-identities",
            ),
            "ueFunctionFlags": ready_or_gate(report, "ueFunctionFlags", "ue-function-flags"),
        },
        "reflectionRuntimeEvidence": {
            "ueReflectionPropertyDescriptorsRuntime": ue_reflection_property_descriptors_runtime_ready(report),
            "ueReflectionPropertyValuesRuntime": ue_reflection_property_values_runtime_ready(report),
            "luaReflectionForEachPropertyRuntime": lua_reflection_for_each_property_runtime_ready(report),
            "luaReflectionLiveDescriptorTypedClassRuntime": lua_reflection_live_descriptor_typed_class_runtime_ready(report),
            "luaReflectionLiveDescriptorTypedValuesRuntime": lua_reflection_live_descriptor_typed_values_runtime_ready(report),
            "luaReflectionLiveDescriptorTypedSetValuesRuntime": lua_reflection_live_descriptor_typed_set_values_runtime_ready(report),
            "luaReflectionLiveDescriptorValuesRuntime": lua_reflection_live_descriptor_runtime_ready(report),
        },
        "requiredValidation": required_validation,
        "envNames": env_names,
        "anchorSignatureFileEnvName": f"{prefix}_UE_ANCHOR_SIGNATURES_FILE",
        "blockerCodes": [item["code"] for item in blockers],
    }


def plan_env(args, report, anchor_export=None):
    prefix = env_prefix(args.platform)
    stage = choose_stage(report)
    ready = report.get("ready", {})
    lines = []
    notes = []
    blockers = []
    root_candidate_input = root_recovery_candidate_input(args)

    for line in anchor_lines(anchor_export):
        name, _, value = line.partition("=")
        if root_candidate_input["provided"] and name == f"{prefix}_UE_ANCHORS":
            notes.append(
                "Suppressed explicit UE anchors exported from the previous runtime log because root-recovery candidate globals are restart-safe image-offset hypotheses."
            )
            continue
        set_env(lines, name, unquote_shell_value(value), "carry forward explicit UE anchor input")
    for path in args.anchor_signatures_file:
        set_env(
            lines,
            f"{prefix}_UE_ANCHOR_SIGNATURES_FILE",
            str(path),
            "promote unique signature-resolved UE anchors during the next canary",
        )
    if root_candidate_input["provided"]:
        if root_candidate_input["envValue"]:
            set_env(
                lines,
                root_candidate_input["envName"],
                root_candidate_input["envValue"],
                "probe bounded root-recovery writable-global hypotheses as runtime candidate anchors",
            )
            notes.append(
                "Root-recovery candidate globals are hypothesis inputs only; keep this canary read-only until candidate shape and runtime object/FName evidence promote them."
            )
            missing_root_groups = list(root_candidate_input.get("missingGroups", []) or [])
            if missing_root_groups:
                notes.append(
                    "Root-recovery candidate globals do not cover groups: "
                    + ", ".join(missing_root_groups)
                    + "."
                )
        else:
            notes.append(
                "Root-recovery candidate input was provided, but no candidates survived rejected-shape filtering."
            )

    if stage in ("object-discovery", "reflection", "hook-probe", "live-hook", "lua-dispatch", "complete"):
        if args.platform == "server":
            set_env_if_absent(
                lines,
                f"{prefix}_TARGET",
                default_target_filter(args.platform),
                "run expensive server probes only inside the Dune target executable, not preload helper processes",
            )
        set_env_if_absent(lines, f"{prefix}_SCAN_ENABLED", "true", "collect target-image scan start/finish and anchor evidence")
        set_env_if_absent(lines, f"{prefix}_SCAN_PRESETS", "core,ue", "scan core Unreal target-image anchor strings")
        set_env_if_absent(
            lines,
            scan_path_filter_env_name(prefix),
            default_target_filter(args.platform),
            "restrict read-only memory scan to Dune target-image mappings",
        )
        set_env_if_absent(lines, f"{prefix}_SCAN_MAX_HITS_PER_NEEDLE", "16", "bound per-anchor scan evidence")
        set_env(lines, f"{prefix}_UE_AUTO_DISCOVER_ROOTS", "true", "scan mapped target image data for runtime FNamePool/GUObjectArray roots")
        if args.platform in ("server", "linux-client"):
            set_env(
                lines,
                f"{prefix}_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW",
                "true",
                "include bounded anonymous RW ELF mappings that hold relocated Unreal globals",
            )
        runtime_policy = runtime_discovery_policy(report, args.platform)
        if runtime_policy["maxBytes"]:
            set_env(
                lines,
                auto_discovery_max_bytes_env_name(prefix, args.platform),
                runtime_policy["maxBytes"],
                f"tune runtime root auto-discovery after {runtime_policy['failure']} evidence",
            )
        if runtime_policy["maxCandidates"]:
            set_env(
                lines,
                f"{prefix}_UE_AUTO_DISCOVER_MAX_CANDIDATES",
                runtime_policy["maxCandidates"],
                f"bound runtime root auto-discovery candidates after {runtime_policy['failure'] or 'default'} evidence",
            )
        if runtime_policy.get("minObjectArrayElements"):
            set_env(
                lines,
                f"{prefix}_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS",
                runtime_policy["minObjectArrayElements"],
                f"filter tiny GUObjectArray-shaped false positives after {runtime_policy['failure']} evidence",
            )
        if runtime_policy["note"]:
            notes.append(runtime_policy["note"])
        if runtime_policy.get("candidateNotes"):
            notes.append(
                "Runtime root candidate locations: "
                + "; ".join(runtime_policy["candidateNotes"])
                + "."
            )
        carry_forward = runtime_candidate_carry_forward_summary(
            report.get("runtimeDiscovery") or report.get("ueRuntimeDiscovery") or {},
            args.platform,
        )
        carry_forward_entries = carry_forward["entries"]
        if carry_forward_entries:
            append_env_values(
                lines,
                carry_forward["envName"],
                carry_forward_entries,
                "carry forward unique runtime root candidate locations from the previous canary",
            )
            notes.append(
                "Carrying forward unique runtime root candidates from the previous canary: "
                + "; ".join(carry_forward_entries)
                + "."
            )
        set_env(lines, f"{prefix}_UE_POINTER_PROBE", "true", "validate configured anchors as pointers")
        set_env(lines, f"{prefix}_UE_LAYOUT_PROBE", "true", "bounded slot read from mapped anchor targets")
        set_env(lines, f"{prefix}_UE_UOBJECT_PROBE", "true", "bounded UObjectBase candidate read")
        set_env(lines, f"{prefix}_UE_OBJECT_ARRAY_PROBE", "true", "bounded GUObjectArray walk")
        set_env(lines, f"{prefix}_UE_FNAME_PROBE", "true", "bounded FNamePool decode")
        if ready.get("runtimeRootValidation") and (
            not function_registry_runtime_ready(report)
            or not ready.get("reflection")
            or not lua_reflection_live_descriptor_runtime_ready(report)
        ):
            set_env(
                lines,
                f"{prefix}_UE_OBJECT_ARRAY_MAX_OBJECTS",
                "4096",
                "deeper read-only GUObjectArray walk after runtime roots validated but UFunction/reflection evidence is missing",
            )
            set_env(lines, f"{prefix}_UE_REFLECTION_PROBE", "true", "read-only UClass slot probe after validated runtime roots")
            set_env(lines, f"{prefix}_UE_REFLECTION_FIELD_WALK", "true", "bounded UField chain walk after validated runtime roots")
            set_env(lines, f"{prefix}_UE_REFLECTION_PROPERTY_PROBE", "true", "bounded FProperty descriptor probe after validated runtime roots")
            set_env(lines, f"{prefix}_UE_REFLECTION_VALUE_PROBE", "true", "bounded read-only reflected value probe after validated runtime roots")
            set_env(lines, f"{prefix}_LUA_REFLECTION_SELF_TEST", "true", "prove Lua reflection API against loader/live descriptors")
            notes.append(
                "Runtime roots are validated but UFunction/reflection runtime evidence is still missing; next canary should run a deeper read-only GUObjectArray walk to promote live UFunction identities."
            )

    if stage in ("reflection", "hook-probe", "live-hook", "lua-dispatch", "complete") or (
        gate(report, "ue-reflection-surface") and gate(report, "ue-uobject-probe")
    ):
        set_env(lines, f"{prefix}_UE_REFLECTION_PROBE", "true", "read-only UClass slot probe")
        set_env(lines, f"{prefix}_UE_REFLECTION_FIELD_WALK", "true", "bounded UField chain walk")
        set_env(lines, f"{prefix}_UE_REFLECTION_PROPERTY_PROBE", "true", "bounded FProperty descriptor probe")
        set_env(lines, f"{prefix}_UE_REFLECTION_VALUE_PROBE", "true", "bounded read-only reflected value probe")
        set_env(lines, f"{prefix}_LUA_REFLECTION_SELF_TEST", "true", "prove Lua reflection API against loader/live descriptors")

    if stage in ("hook-probe", "live-hook", "lua-dispatch", "complete"):
        if stage_allowed(args, "hook-probe"):
            set_env(lines, f"{prefix}_HOOK_SELF_TEST", "true", "prove guarded native hook dispatch on loader-owned target")
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_HOOK_PROBE", "true", "guarded install/restore probe on resolved ProcessEvent")
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_HOOK_INSTALL", "false", "do not keep hook installed during hook probe")
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_HOOK_PROBE", "true", "guarded install/restore probe on resolved CallFunctionByNameWithArguments")
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_HOOK_INSTALL", "false", "do not keep hook installed during hook probe")
        else:
            notes.append("ProcessEvent hook probe is next, but --max-stage read-only suppresses code-patching probes.")

    if stage in ("live-hook", "lua-dispatch", "complete"):
        if stage_allowed(args, "live-hook"):
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK", "true", "install persistent ProcessEvent hook scaffold")
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK", "true", "install persistent CallFunctionByNameWithArguments hook scaffold")
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_DISPATCH_SELF_TEST", "true", "arm native pre/original/post dispatch")
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS", "true", "collect bounded live ProcessEvent context and param samples")
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS", "true", "collect bounded live CallFunctionByNameWithArguments call samples")
            set_env(
                lines,
                f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT",
                str(args.live_call_log_limit),
                "bound live ProcessEvent context sample count",
            )
            set_env(
                lines,
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT",
                str(args.live_call_log_limit),
                "bound live CallFunctionByNameWithArguments sample count",
            )
        else:
            notes.append("Persistent ProcessEvent hook is next, but --max-stage blocks live hook emission.")
    if stage in ("lua-dispatch", "complete"):
        if stage_allowed(args, "lua-dispatch"):
            set_env(lines, f"{prefix}_LUA_SELF_TEST", "true", "prove Lua runtime and UE4SS-shaped API surface")
            set_env(lines, f"{prefix}_LUA_PROCESS_EVENT_SELF_TEST", "true", "prove ProcessEvent-shaped Lua callback bridge")
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH", "true", "route live ProcessEvent callbacks into Lua")
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH", "true", "route live CallFunctionByNameWithArguments callbacks into Lua")
            if not ready.get("ueProcessEventLuaHookAliasRouting"):
                alias_hook_path = choose_alias_hook_path(args, report)
                alias_script = live_lua_alias_script(alias_hook_path)
                if alias_script:
                    set_env(
                        lines,
                        f"{prefix}_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT",
                        alias_script,
                        f"prove UE4SS-style /Script hook alias routing for {alias_hook_path}",
                    )
                else:
                    notes.append(
                        "Lua dispatch is ready for alias routing, but no decoded UFunction path hint was available; pass --live-lua-alias-hook-path, --live-lua-alias-function-path, or run a function identity canary first."
                    )
            set_env(lines, f"{prefix}_MOD_SELF_TEST", "true", "prove native mod lifecycle dispatch")
            set_env(lines, f"{prefix}_LUA_MODS_ENABLED", "true", "load UE4SS-style Lua mod entrypoints")
            set_env(lines, f"{prefix}_LUA_MOD_DISPATCH_SELF_TEST", "true", "prove Lua mod RegisterHook dispatch")
        else:
            notes.append("Lua dispatch is next, but --max-stage blocks Lua/live mod dispatch emission.")

    if stage == "complete":
        notes.append("All readiness gates are already satisfied by the provided evidence.")
    if root_candidate_input["provided"] and root_candidate_input["emittedCount"]:
        missing_object_candidate_groups = root_recovery_missing_groups(
            root_candidate_input,
            REQUIRED_OBJECT_DISCOVERY_GROUPS,
        )
        missing_hook_candidate_groups = root_recovery_missing_groups(
            root_candidate_input,
            ("dispatch",),
        )
        missing_package_candidate_groups = root_recovery_missing_groups(
            root_candidate_input,
            ("package",),
        )
        missing_reflection_candidate_groups = root_recovery_missing_groups(
            root_candidate_input,
            ("reflection",),
        )
        if missing_object_candidate_groups:
            add_blocker(
                blockers,
                notes,
                "incomplete-root-recovery-object-candidates",
                "object-discovery",
                "Root-recovery candidate input lacks object-discovery groups: "
                + ", ".join(missing_object_candidate_groups)
                + ". Export candidates with --anchor-preset object-discovery or --anchor-preset complete before relying on the next canary to recover UE roots.",
            )
        shape_quality = root_candidate_input.get("shapeQuality", {}) or {}
        if int(shape_quality.get("qwordCandidateCount", 0) or 0) == 0:
            add_blocker(
                blockers,
                notes,
                "unproven-root-recovery-shape-quality",
                "object-discovery",
                "Root-recovery candidate input has no qword-classified candidates. Re-export from qword-filtered ELF/PE writable-root shape evidence before relying on a live canary.",
            )
        if int(shape_quality.get("scalarHeavyCandidateCount", 0) or 0) > 0:
            add_blocker(
                blockers,
                notes,
                "scalar-heavy-root-recovery-candidates",
                "object-discovery",
                "Root-recovery candidate input includes scalar-heavy writable-root rows. Filter with --require-qword and --max-scalar-ratio before live runtime testing.",
            )
        if int(shape_quality.get("addressHeavyCandidateCount", 0) or 0) > 0:
            add_blocker(
                blockers,
                notes,
                "address-heavy-root-recovery-candidates",
                "object-discovery",
                "Root-recovery candidate input includes address-heavy writable-root rows. Filter with --max-address-ratio before live runtime testing.",
            )
        hint_quality = root_candidate_input.get("hintQuality", {}) or {}
        if int(hint_quality.get("genericOnlyCandidateCount", 0) or 0) > 0:
            add_blocker(
                blockers,
                notes,
                "generic-only-root-recovery-context",
                "object-discovery",
                "Root-recovery candidate input is supported only by generic UE type mentions. Re-export with --require-specific-context or --require-exact-anchor before live runtime testing.",
            )
        source_group_quality = root_candidate_input.get("sourceGroupQuality", {}) or {}
        if int(source_group_quality.get("unmatchedCount", 0) or 0) > 0:
            add_blocker(
                blockers,
                notes,
                "unmatched-root-recovery-source-groups",
                "object-discovery",
                "Root-recovery candidate input labels anchors from source functions that did not cover the corresponding UE group. Re-export with --require-source-group-match before relying on these candidates for dispatch, package, or reflection escalation.",
            )
        if stage in ("hook-probe", "live-hook", "lua-dispatch", "complete") and missing_hook_candidate_groups:
            add_blocker(
                blockers,
                notes,
                "incomplete-root-recovery-dispatch-candidates",
                "hook-probe",
                "Root-recovery candidate input lacks dispatch groups: "
                + ", ".join(missing_hook_candidate_groups)
                + ". Export candidates with --anchor-preset hook-planning or --anchor-preset complete before hook planning.",
            )
        if stage in ("lua-dispatch", "complete") and missing_package_candidate_groups:
            add_blocker(
                blockers,
                notes,
                "incomplete-root-recovery-package-candidates",
                "lua-dispatch",
                "Root-recovery candidate input lacks package-loading groups: "
                + ", ".join(missing_package_candidate_groups)
                + ". Export candidates with --anchor-preset package-loading or --anchor-preset complete before claiming LoadAsset parity.",
            )
        if stage in ("reflection", "hook-probe", "live-hook", "lua-dispatch", "complete") and missing_reflection_candidate_groups:
            add_blocker(
                blockers,
                notes,
                "incomplete-root-recovery-reflection-candidates",
                "reflection",
                "Root-recovery candidate input lacks reflection groups: "
                + ", ".join(missing_reflection_candidate_groups)
                + ". Export candidates with --anchor-preset reflection or --anchor-preset complete before relying on reflection recovery.",
            )
    if not ready.get("anchorSignatureResolver") and not gate(report, "ue-names"):
        add_blocker(
            blockers,
            notes,
            "missing-core-anchor-signatures",
            "object-discovery",
            "No resolved anchor signatures or core names were found; run an anchor-signature canary first.",
        )
    if not anchor_group_provenance_ready(report):
        add_blocker(
            blockers,
            notes,
            "missing-anchor-group-provenance",
            "object-discovery",
            "UE anchor evidence is missing loader-normalized group provenance; rerun the native Linux or Proton/Windows canary with a grouped loader build before escalating beyond read-only discovery.",
        )
    if ready.get("objectDiscovery") and not proven_object_anchor_groups_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-object-anchor-groups",
            "object-discovery",
            "Readiness claims object discovery, but the report does not show proven names/objects/world UE anchor groups; stay read-only and rebuild readiness from mapped ue-anchor or resolved ue-anchor-signature evidence.",
        )
    if ready.get("objectDiscovery") and not proven_target_object_anchor_groups_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-target-object-anchor-groups",
            "object-discovery",
            "Readiness claims object discovery, but target-image object discovery is not proven; rerun the canary until names/objects/world/dispatch anchors resolve in the game executable or module rather than the probe loader image.",
        )
    if (ready.get("luaLoadAssetPackage") or ready.get("luaDispatch")) and not proven_target_package_loading_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-target-package-loading-anchor",
            "lua-dispatch",
            "Package-backed LoadAsset is not target-image ready; collect StaticLoadObject, LoadObject, LoadPackage, or ResolveName evidence from the game executable or module before treating luaLoadAssetPackage as complete.",
        )
    if ready.get("reflection") and not proven_reflection_surface_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-reflection-anchors",
            "reflection",
            "Readiness claims reflection, but the report does not show at least two proven reflection anchors; keep reflection work read-only until anchor provenance is present.",
        )
    if (ready.get("reflection") or ready.get("hookDispatch")) and not proven_dispatch_anchor_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-dispatch-anchor",
            "hook-probe",
            "Readiness claims hook-capable stages, but the report does not show a proven dispatch anchor; do not emit ProcessEvent hook or Lua dispatch env.",
        )
    if (ready.get("reflection") or ready.get("hookDispatch")) and not proven_target_dispatch_anchor_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-target-dispatch-anchor",
            "hook-probe",
            "Readiness claims hook-capable stages, but dispatch anchors are not proven in the target executable or game module; do not emit ProcessEvent hook or Lua dispatch env.",
        )
    if (ready.get("hooks") or ready.get("luaDispatch")) and not proven_target_hooks_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-target-hooks",
            "hook-probe",
            "Readiness claims hook or Lua dispatch readiness, but target-image hook readiness is false; keep the plan at hook validation until targetHooks=true.",
        )
    if (ready.get("ueProcessEventHookProbe") or ready.get("hooks") or ready.get("luaDispatch")) and not runtime_ready(
        report,
        "ueProcessEventHookRuntimeTarget",
        "ue-process-event-hook-runtime-target",
    ):
        add_blocker(
            blockers,
            notes,
            "self-test-only-hook-probe",
            "hook-probe",
            "ProcessEvent hook probe evidence is still loader-owned self-test target evidence; rerun hook-probe on a non-self-test resolved ProcessEvent target before live-hook or Lua escalation.",
        )
    if (ready.get("ueCallFunctionHookProbe") or ready.get("hooks") or ready.get("luaDispatch")) and not runtime_ready(
        report,
        "ueCallFunctionHookRuntimeTarget",
        "ue-call-function-hook-runtime-target",
    ):
        add_blocker(
            blockers,
            notes,
            "self-test-only-call-function-hook-probe",
            "hook-probe",
            "CallFunctionByNameWithArguments hook probe evidence is still loader-owned self-test target evidence; rerun hook-probe on a non-self-test resolved target before live-hook or Lua escalation.",
        )
    if (ready.get("ueProcessEventLiveHook") or ready.get("hooks") or ready.get("luaDispatch")) and not runtime_ready(
        report,
        "ueProcessEventLiveHookRuntimeTarget",
        "ue-process-event-live-hook-runtime-target",
    ):
        add_blocker(
            blockers,
            notes,
            "self-test-only-live-hook",
            "live-hook",
            "Persistent ProcessEvent hook evidence is still loader-owned self-test target evidence; keep the plan at live-hook until a non-self-test resolved ProcessEvent target is installed.",
        )
    if (ready.get("ueCallFunctionLiveHook") or ready.get("hooks") or ready.get("luaDispatch")) and not runtime_ready(
        report,
        "ueCallFunctionLiveHookRuntimeTarget",
        "ue-call-function-live-hook-runtime-target",
    ):
        add_blocker(
            blockers,
            notes,
            "self-test-only-call-function-live-hook",
            "live-hook",
            "Persistent CallFunctionByNameWithArguments hook evidence is still loader-owned self-test target evidence; keep the plan at live-hook until a non-self-test resolved CallFunction target is installed.",
        )
    if ready.get("luaDispatch") and not ready_or_gate(
        report,
        "ueCallFunctionLiveLuaDispatch",
        "ue-call-function-live-lua-dispatch",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-call-function-live-lua-dispatch",
            "lua-dispatch",
            "Live CallFunctionByNameWithArguments Lua dispatch evidence is missing; route RegisterCallFunctionByNameWithArguments pre/post callbacks through the persistent hook before claiming Lua dispatch parity.",
        )
    if ready.get("luaDispatch") and not ready_or_gate(
        report,
        "ueProcessEventContainerStorageLayoutMethods",
        "ue-process-event-container-storage-layout-methods",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-process-event-container-storage-layout-methods",
            "lua-dispatch",
            "ProcessEvent Lua container storage-layout method evidence is missing; prove GetStorageLayout, IsSparseLayoutValidated, and GetSlotStride in both self-test and live hook callbacks before claiming Lua dispatch parity.",
        )
    if (ready.get("ueProcessEventLiveContext") or ready.get("luaDispatch")) and not runtime_ready(
        report,
        "ueProcessEventLiveRuntimeContext",
        "ue-process-event-live-runtime-context",
    ):
        add_blocker(
            blockers,
            notes,
            "self-test-only-live-context",
            "live-hook",
            "Live ProcessEvent context evidence still matches loader-owned self-test functions; collect a non-self-test runtime UFunction context before Lua dispatch escalation.",
        )
    if (ready.get("ueProcessEventLiveRegistryContext") or ready.get("luaDispatch")) and not runtime_ready(
        report,
        "ueProcessEventLiveRuntimeRegistryContext",
        "ue-process-event-live-runtime-registry-context",
    ):
        add_blocker(
            blockers,
            notes,
            "self-test-only-live-registry-context",
            "live-hook",
            "Live ProcessEvent registry context evidence still matches loader-owned self-test functions; collect non-self-test object/function registry context before Lua dispatch escalation.",
        )
    object_coverage = report.get("objectDiscoveryCoverage", {})
    if object_coverage and not object_coverage.get("readyForObjectDiscovery", False):
        missing = object_coverage.get("missingObjectDiscoveryComponents", [])
        add_blocker(
            blockers,
            notes,
            "incomplete-object-discovery-coverage",
            "object-discovery",
            "Object discovery coverage is incomplete; missing "
            + (", ".join(missing) if missing else "one or more required components")
            + ".",
        )
    elif object_coverage and not object_coverage.get("readyForFindObjectSemantics", False):
        missing = object_coverage.get("missingFindObjectComponents", [])
        add_blocker(
            blockers,
            notes,
            "incomplete-find-object-semantics",
            "hook-probe",
            "FindObject semantics are not fully proven yet; missing "
            + (", ".join(missing) if missing else "one or more required components")
            + ".",
        )
    if ready.get("objectDiscovery") and not object_registry_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-object-registry",
            "object-discovery",
            "Lua object registry evidence is still loader-owned self-test data; collect a non-self-test UObject registry candidate before hook or Lua escalation.",
        )
    if ready.get("objectDiscovery") and not decoded_alias_registry_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-decoded-object-aliases",
            "object-discovery",
            "Decoded object alias evidence is still loader-owned self-test data; promote a non-self-test decoded UObject name before relying on FindObject semantics.",
        )
    if ready.get("objectDiscovery") and not object_array_registry_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-object-array-registry",
            "object-discovery",
            "Object-array registry evidence is still loader-owned self-test data; walk a non-self-test GUObjectArray/FChunkedFixedUObjectArray candidate before hook or Lua escalation.",
        )
    if ready.get("reflection") and not function_registry_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-function-registry",
            "reflection",
            "UFunction registry evidence is still loader-owned self-test data; collect a non-self-test function registry check before Lua dispatch escalation.",
        )
    if ready.get("reflection") and not ue_reflection_property_descriptors_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-native-reflection-descriptors",
            "reflection",
            "Native FProperty descriptor evidence is missing or self-test-only; collect readable non-self-test runtime property metadata before reflection escalation.",
        )
    if ready.get("reflection") and not ue_reflection_property_values_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-native-reflection-values",
            "reflection",
            "Native reflected property value evidence is missing or self-test-only; read non-self-test runtime descriptor bytes before reflection escalation.",
        )
    if ready.get("luaDispatch") and not lua_function_iteration_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-function-iteration",
            "lua-dispatch",
            "ForEachFunction evidence is still loader-owned self-test data; run a Lua mod that iterates promoted functions from a non-self-test object/class handle.",
        )
    if ready.get("luaDispatch") and not lua_reflection_for_each_property_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-reflection-for-each-property",
            "lua-dispatch",
            "Reflection():ForEachProperty evidence is still loader-owned self-test data; enumerate a promoted non-self-test descriptor before Lua dispatch escalation.",
        )
    if ready.get("luaDispatch") and not lua_reflection_live_descriptor_typed_class_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-reflection-live-descriptor-typed-class",
            "lua-dispatch",
            "Live reflection descriptor class evidence is missing or self-test-only; expose a decoded FProperty class on a promoted non-self-test descriptor before Lua dispatch escalation.",
        )
    if ready.get("luaDispatch") and not lua_reflection_live_descriptor_typed_values_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-reflection-live-descriptor-typed-values",
            "lua-dispatch",
            "Live reflection descriptor typed GetValue evidence is missing or self-test-only; return a typed Lua value from a promoted non-self-test descriptor before Lua dispatch escalation.",
        )
    if ready.get("luaDispatch") and not lua_reflection_live_descriptor_typed_set_values_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-reflection-live-descriptor-typed-set-values",
            "lua-dispatch",
            "Live reflection descriptor typed SetValue evidence is missing or self-test-only; write a typed Lua value to a promoted non-self-test descriptor before Lua dispatch escalation.",
        )
    if ready.get("luaDispatch") and not lua_reflection_live_descriptor_runtime_ready(report):
        add_blocker(
            blockers,
            notes,
            "self-test-only-reflection-live-descriptor",
            "lua-dispatch",
            "Live reflection descriptor GetValue/SetValue evidence is still loader-owned self-test data; run Lua reflection against a non-self-test promoted descriptor before Lua dispatch escalation.",
        )
    if coverage_provided(report) and not coverage_ready(
        report,
        "anchorCoverageObjectDiscovery",
        "anchor-coverage-object-discovery",
    ):
        missing = report.get("anchorCoverage", {}).get("missingRequiredGroups", [])
        add_blocker(
            blockers,
            notes,
            "incomplete-prepared-object-anchor-coverage",
            "object-discovery",
            "Prepared anchor coverage is missing object-discovery groups; stay read-only until coverage is complete"
            + (f" ({', '.join(missing)})" if missing else "."),
        )
    if coverage_provided(report) and not coverage_ready(
        report,
        "anchorCoverageHookPlanning",
        "anchor-coverage-hook-planning",
    ):
        add_blocker(
            blockers,
            notes,
            "incomplete-prepared-dispatch-anchor-coverage",
            "hook-probe",
            "Prepared anchor coverage lacks ProcessEvent-level dispatch evidence; do not emit hook/live Lua escalation yet.",
        )

    deduped = []
    seen = set()
    for item in lines:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        deduped.append(item)
    return {
        "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
        "platform": args.platform,
        "loader": loader_name(args.platform),
        "selectedStage": stage,
        "maxStage": args.max_stage,
        "env": deduped,
        "notes": notes,
        "blockers": blockers,
        "nextCanaryContract": build_canary_contract(args, report, stage, deduped, blockers, root_candidate_input),
        "ready": report.get("ready", {}),
        "selectedLoaderReadiness": report.get("selectedLoaderReadiness", {}),
    }


def env_text(plan):
    lines = [
        "# UE4SS-port canary env plan",
        f"# Platform: {plan['platform']}",
        f"# Selected stage: {plan['selectedStage']}",
        f"# Max stage: {plan['maxStage']}",
    ]
    for note in plan["notes"]:
        lines.append(f"# Note: {note}")
    for item in plan["env"]:
        lines.append(f"# {item['reason']}")
        value = item["value"]
        needs_quote = any(ch in value for ch in (";", " ", "\t", "'", "\"", "$", "`", "\\"))
        lines.append(f"{item['name']}={shell_quote(value) if needs_quote else value}")
    lines.append("")
    return "\n".join(lines)


def markdown(plan):
    lines = ["# UE4SS Canary Env Plan", ""]
    lines.append(f"- Platform: `{plan['platform']}`")
    lines.append(f"- Loader: `{plan['loader']}`")
    lines.append(f"- Selected stage: `{plan['selectedStage']}`")
    lines.append(f"- Max stage: `{plan['maxStage']}`")
    selected_loader = plan.get("selectedLoaderReadiness", {})
    if selected_loader:
        lines.append(
            f"- Scoped loader readiness: `available={str(bool(selected_loader.get('available'))).lower()}, "
            f"loader={selected_loader.get('loader') or 'none'}`"
        )
    if plan["notes"]:
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        for note in plan["notes"]:
            lines.append(f"- {note}")
    if plan.get("blockers"):
        lines.append("")
        lines.append("## Blockers")
        lines.append("")
        for blocker in plan["blockers"]:
            lines.append(f"- `{blocker['code']}` blocks `{blocker['stage']}`: {blocker['message']}")
    contract = plan.get("nextCanaryContract", {})
    if contract:
        lines.append("")
        lines.append("## Next Canary Contract")
        lines.append("")
        missing = contract.get("missingAnchorGroups", {})
        lines.append(
            "- Missing object-discovery groups: `"
            + (", ".join(missing.get("objectDiscovery", [])) or "none")
            + "`"
        )
        lines.append(
            "- Missing hook-planning groups: `"
            + (", ".join(missing.get("hookPlanning", [])) or "none")
            + "`"
        )
        lines.append(
            "- Missing reflection groups: `"
            + (", ".join(missing.get("reflection", [])) or "none")
            + "`"
        )
        required = contract.get("requiredValidation", [])
        lines.append("- Required validation: `" + (", ".join(required) or "none") + "`")
        runtime = contract.get("processEventRuntimeEvidence", {})
        if runtime:
            lines.append(
                "- ProcessEvent runtime evidence: `"
                + ", ".join(f"{name}={str(value).lower()}" for name, value in runtime.items())
                + "`"
            )
        call_runtime = contract.get("callFunctionRuntimeEvidence", {})
        if call_runtime:
            lines.append(
                "- CallFunction runtime evidence: `"
                + ", ".join(f"{name}={str(value).lower()}" for name, value in call_runtime.items())
                + "`"
            )
        registry_runtime = contract.get("registryRuntimeEvidence", {})
        if registry_runtime:
            lines.append(
                "- Registry runtime evidence: `"
                + ", ".join(f"{name}={str(value).lower()}" for name, value in registry_runtime.items())
                + "`"
            )
        object_coverage = contract.get("objectDiscoveryCoverage", {})
        if object_coverage:
            lines.append(
                "- Object discovery coverage: `objectDiscovery="
                + str(object_coverage.get("readyForObjectDiscovery", False)).lower()
                + ", findObjectSemantics="
                + str(object_coverage.get("readyForFindObjectSemantics", False)).lower()
                + ", missingObject="
                + (", ".join(object_coverage.get("missingObjectDiscoveryComponents", []) or []) or "none")
                + ", missingFindObject="
                + (", ".join(object_coverage.get("missingFindObjectComponents", []) or []) or "none")
                + "`"
            )
        root_candidates = contract.get("rootRecoveryCandidateInput", {})
        if root_candidates and root_candidates.get("provided"):
            lines.append(
                "- Root-recovery candidate globals: `"
                + f"env={root_candidates.get('envName', '')}, "
                + f"candidates={root_candidates.get('candidateCount', 0)}, "
                + f"emitted={root_candidates.get('emittedCount', 0)}, "
                + f"filteredRejectedShape={root_candidates.get('filteredRejectedShapeCount', 0)}"
                + "`"
            )
            lines.append(
                "- Root-recovery missing groups: `"
                + (", ".join(root_candidates.get("missingGroups", []) or []) or "none")
                + "`"
            )
        reflection_runtime = contract.get("reflectionRuntimeEvidence", {})
        if reflection_runtime:
            lines.append(
                "- Reflection runtime evidence: `"
                + ", ".join(f"{name}={str(value).lower()}" for name, value in reflection_runtime.items())
                + "`"
            )
        post_canary = contract.get("postCanaryVerification", {})
        if post_canary:
            lines.append("- Post-canary readiness command: `" + post_canary.get("readinessCommandText", "") + "`")
            strict_runtime = post_canary.get("strictRuntimeContract", {})
            if strict_runtime:
                lines.append(
                    "- Strict runtime contract: `"
                    + f"{strict_runtime.get('envName', 'DUNE_UE4SS_STRICT_RUNTIME_CONTRACT')}="
                    + f"{strict_runtime.get('enabledValue', 'true')}, "
                    + f"contractReady={str(bool(strict_runtime.get('contractReady'))).lower()}, "
                    + f"runtimeReady={str(bool(strict_runtime.get('runtimeReady'))).lower()}, "
                    + f"signatureAnchorReady={str(bool(strict_runtime.get('signatureAnchorReady'))).lower()}, "
                    + "missingRuntime="
                    + (", ".join(strict_runtime.get("missingReadyKeys", []) or []) or "none")
                    + ", missingSignatureAnchor="
                    + (", ".join(strict_runtime.get("missingSignatureAnchorReadyKeys", []) or []) or "none")
                    + "`"
                )
            live_target = post_canary.get("liveTargetImageCanaryContract", {})
            if live_target:
                lines.append(
                    "- Live target-image canary contract: `ready="
                    + str(bool(live_target.get("ready"))).lower()
                    + ", missing="
                    + (", ".join(live_target.get("missingKeys", []) or []) or "none")
                    + "`"
                )
            cross_platform = post_canary.get("crossPlatformStrictRuntimeContract", {})
            if cross_platform:
                lines.append(
                    "- Cross-platform strict runtime contract: `ready="
                    + str(bool(cross_platform.get("ready"))).lower()
                    + ", missingLoaders="
                    + (", ".join(cross_platform.get("missingLoaders", []) or []) or "none")
                    + ", failedLoaders="
                    + (", ".join(cross_platform.get("failedLoaders", []) or []) or "none")
                    + "`"
                )
    lines.append("")
    lines.append("## Env")
    lines.append("")
    for item in plan["env"]:
        lines.append(f"- `{item['name']}={item['value']}`: {item['reason']}")
    if not plan["env"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan the next guarded UE4SS-port canary env from readiness evidence.")
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--readiness-json", type=Path)
    parser.add_argument("--log", type=Path, action="append", default=[])
    parser.add_argument("--client-log", type=Path, action="append", default=[])
    parser.add_argument("--server-log", type=Path, action="append", default=[])
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--signature-validation-json", type=Path, action="append", default=[])
    parser.add_argument(
        "--anchor-signatures-file",
        type=Path,
        action="append",
        default=[],
        help="loader-consumable UE anchor signature sidecar to feed into the next canary",
    )
    parser.add_argument(
        "--root-recovery-candidates-json",
        type=Path,
        action="append",
        default=[],
        help="JSON from export-ue-root-recovery-candidates.py to feed as bounded candidate globals",
    )
    parser.add_argument(
        "--candidate-globals-json",
        type=Path,
        action="append",
        default=[],
        help="JSON from export-ue-candidate-globals.py to feed as bounded candidate globals",
    )
    parser.add_argument(
        "--candidate-global",
        action="append",
        default=[],
        help="explicit loader candidate global entry to merge into the next canary, e.g. FNamePool=0x1686df70 or RuntimeFNamePool@rwfile=0x1e1e18",
    )
    parser.add_argument(
        "--candidate-shapes-json",
        type=Path,
        action="append",
        default=[],
        help="JSON from summarize-ue-candidate-shapes.py; rejected/weak shape rows are filtered from root-recovery candidates",
    )
    parser.add_argument(
        "--candidate-outcomes-json",
        type=Path,
        action="append",
        default=[],
        help="JSON from summarize-ue-candidate-outcomes.py; rejected/weak live outcome rows are filtered from root-recovery candidates",
    )
    parser.add_argument("--max-stage", choices=MAX_STAGES, default="read-only")
    parser.add_argument("--live-call-log-limit", type=int, default=8)
    parser.add_argument(
        "--live-lua-alias-function-path",
        default="",
        help="decoded runtime UFunction path to target with the generated UE4SS-style /Script alias canary",
    )
    parser.add_argument(
        "--live-lua-alias-hook-path",
        default="",
        help="explicit UE4SS-style /Script package/class/function hook path for the generated alias canary",
    )
    parser.add_argument(
        "--live-lua-alias-script-package",
        default="",
        help="package/class prefix for the generated /Script alias hook path; defaults per platform",
    )
    parser.add_argument("--format", choices=("env", "json", "markdown"), default="env")
    args = parser.parse_args(argv)

    try:
        report = readiness_from_args(args)
        anchor_export = anchor_export_from_args(args)
        report = scoped_report_for_platform(args, report)
        plan = plan_env(args, report, anchor_export)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")

    if args.format == "json":
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "markdown":
        sys.stdout.write(markdown(plan))
    else:
        sys.stdout.write(env_text(plan))


if __name__ == "__main__":
    main()
