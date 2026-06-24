#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


PLATFORMS = ("server", "linux-client", "windows")
MAX_STAGES = ("read-only", "hook-probe", "live-hook", "lua-dispatch")
READINESS_SCHEMA_VERSION = "dune-ue4ss-port-readiness/v1"
PLAN_STAGE_ORDER = ("object-discovery", "reflection", "hook-probe", "live-hook", "lua-dispatch", "complete")
CORE_ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
ROOT_RECOVERY_ANCHOR_GROUPS = {
    "names": ("FNamePool", "RuntimeFNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "RuntimeGUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
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
    "luaStaticConstructObjectNativeExecutorState": {
        "events": ["lua-static-construct-object-native-executor-state"],
        "requiredFields": ["targetName=StaticConstructObject"],
        "description": "guarded StaticConstructObject native executor state evidence",
    },
    "luaStaticConstructObjectNativeExecutorReady": {
        "events": ["lua-static-construct-object-native-executor-state"],
        "requiredFields": [
            "targetImage=true",
            "abiVerified=true",
            "callFrameReady=true",
            "finalInvokeConfirmed=true",
            "nativeCallable=true",
        ],
        "description": "target-image StaticConstructObject native executor readiness evidence",
    },
    "luaStaticConstructObjectNativeInvoke": {
        "events": ["lua-static-construct-object-native-invoke"],
        "requiredFields": ["targetImage=true", "nativeInvoked=true"],
        "description": "target-image StaticConstructObject native invocation evidence",
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
    "ueProcessEventActiveValidation": {
        "events": ["ue-process-event-active-validate"],
        "requiredFields": ["status=invoked", "targetEntry=true", "liveCallsDelta>0", "originalCallsDelta>0"],
        "description": "explicit active ProcessEvent call entered the patched target, live hook, and original trampoline",
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
    "ueCallFunctionActiveValidation": {
        "events": ["ue-call-function-active-validate"],
        "requiredFields": ["status=invoked", "targetEntry=true", "liveCallsDelta>0", "originalCallsDelta>0"],
        "description": "explicit active CallFunctionByNameWithArguments call entered the patched target, live hook, and original trampoline",
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
    "ueProcessEventActiveValidation",
    "ueCallFunctionActiveValidation",
    "ueCallFunctionLiveLuaDispatch",
    "luaCallFunctionNativeInvoke",
    "luaCallFunctionNativeInvokePreflight",
    "luaCallFunctionNativeExecutorState",
    "luaCallFunctionNativeInvokeNonSelfTestGate",
    "luaCallFunctionNativeInvokeNonSelfTestInvoked",
    "luaProcessEventNativeInvoke",
    "luaProcessEventNativeInvokeDescriptorPreflight",
    "luaProcessEventNativeExecutorState",
    "luaProcessEventNativeInvokeNonSelfTestGate",
    "luaProcessEventNativeInvokeNonSelfTestInvoked",
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
    "luaStaticConstructObjectNativeExecutorState",
    "luaStaticConstructObjectNativeExecutorReady",
    "luaStaticConstructObjectNativeInvoke",
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
    "luaLoadAssetPackageNativeInvocation",
    "luaLoadAssetPackage",
    "luaLoadClassPackageAbiState",
    "luaLoadClassPackageCallFrameVerification",
    "luaLoadClassPackageNativeExecutor",
    "luaLoadClassPackageNativeInvocation",
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
    "ueProcessEventActiveValidation": "ue-process-event-active-validation",
    "ueCallFunctionActiveValidation": "ue-call-function-active-validation",
    "ueCallFunctionLiveLuaDispatch": "ue-call-function-live-lua-dispatch",
    "luaCallFunctionNativeInvoke": "lua-call-function-native-invoke",
    "luaCallFunctionNativeInvokePreflight": "lua-call-function-native-invoke-preflight",
    "luaCallFunctionNativeExecutorState": "lua-call-function-native-executor-state",
    "luaCallFunctionNativeInvokeNonSelfTestGate": "lua-call-function-native-invoke-non-self-test-gate",
    "luaCallFunctionNativeInvokeNonSelfTestInvoked": "lua-call-function-native-invoke-non-self-test-invoked",
    "luaProcessEventNativeInvoke": "lua-process-event-native-invoke",
    "luaProcessEventNativeInvokeDescriptorPreflight": "lua-process-event-native-invoke-descriptor-preflight",
    "luaProcessEventNativeExecutorState": "lua-process-event-native-executor-state",
    "luaProcessEventNativeInvokeNonSelfTestGate": "lua-process-event-native-invoke-non-self-test-gate",
    "luaProcessEventNativeInvokeNonSelfTestInvoked": "lua-process-event-native-invoke-non-self-test-invoked",
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
    "luaStaticConstructObjectNativeExecutorState": "lua-static-construct-object-native-executor-state",
    "luaStaticConstructObjectNativeExecutorReady": "lua-static-construct-object-native-executor-ready",
    "luaStaticConstructObjectNativeInvoke": "lua-static-construct-object-native-invoke",
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
    "luaLoadAssetPackageNativeInvocation": "lua-load-asset-package-native-invocation",
    "luaLoadAssetPackage": "lua-load-asset-package",
    "luaLoadClassPackageAbiState": "lua-load-class-package-abi-state",
    "luaLoadClassPackageCallFrameVerification": "lua-load-class-package-call-frame-verification",
    "luaLoadClassPackageNativeExecutor": "lua-load-class-package-native-executor",
    "luaLoadClassPackageNativeInvocation": "lua-load-class-package-native-invocation",
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
        "luaLoadAssetPackageNativeInvocation",
        "luaLoadAssetPackage",
        "luaLoadClassPackageAbiState",
        "luaLoadClassPackageCallFrameVerification",
        "luaLoadClassPackageNativeExecutor",
        "luaLoadClassPackageNativeInvocation",
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
        "luaStaticConstructObjectNativeExecutorState",
        "luaStaticConstructObjectNativeExecutorReady",
        "luaStaticConstructObjectNativeInvoke",
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
        "luaProcessEventNativeInvoke",
        "luaProcessEventNativeInvokeDescriptorPreflight",
        "luaProcessEventNativeExecutorState",
        "luaProcessEventNativeInvokeNonSelfTestGate",
        "luaProcessEventNativeInvokeNonSelfTestInvoked",
    ),
    "runtimeCallFunctionDispatch": (
        "ueCallFunctionHookRuntimeTarget",
        "ueCallFunctionLiveHookRuntimeTarget",
        "ueCallFunctionActiveValidation",
        "ueCallFunctionLiveLuaDispatch",
        "luaCallFunctionNativeInvoke",
        "luaCallFunctionNativeInvokePreflight",
        "luaCallFunctionNativeExecutorState",
        "luaCallFunctionNativeInvokeNonSelfTestGate",
        "luaCallFunctionNativeInvokeNonSelfTestInvoked",
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
        report = validate_readiness_report(load_json(args.readiness_json), str(args.readiness_json))
        return merge_active_validation_candidate_files(report, args.active_validation_candidates_json)
    readiness = import_script("ue4ss-port-readiness.py", "ue4ss_port_readiness")
    log_paths = args.log + args.client_log + args.server_log
    if not log_paths:
        raise ValueError("provide --readiness-json, --log, --client-log, or --server-log")
    summaries = [
        readiness.summarize_log(path, loader_filter(args), args.pid, args.exe_substring)
        for path in log_paths
    ]
    validations = [load_json(path) for path in args.signature_validation_json]
    report = readiness.build_report(summaries, validations)
    return merge_active_validation_candidate_files(report, args.active_validation_candidates_json)


def validate_readiness_report(report, source="readiness report"):
    if not isinstance(report, dict):
        raise ValueError(f"{source} must be a JSON object")
    schema = report.get("schemaVersion")
    if schema is not None and schema != READINESS_SCHEMA_VERSION:
        raise ValueError(f"{source} has schemaVersion {schema!r}; expected {READINESS_SCHEMA_VERSION!r}")
    if not isinstance(report.get("ready"), dict):
        raise ValueError(f"{source} is missing readiness `ready` object")
    contract = report.get("liveTargetImageCanaryContract")
    if contract is not None:
        validate_live_target_image_contract(contract, f"{source}.liveTargetImageCanaryContract")
    coverage = report.get("anchorCoverage")
    if coverage is not None:
        validate_anchor_coverage(coverage, f"{source}.anchorCoverage")
    return report


def validate_bool_field(payload, key, label):
    value = payload.get(key)
    if value is None:
        return
    if not isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be a boolean")


def validate_string_list(value, label):
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{label}[{index}] must be a string")


def validate_string_list_field(payload, key, label):
    validate_string_list(payload.get(key), f"{label}.{key}")


def validate_non_negative_int_field(payload, key, label):
    value = payload.get(key)
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label}.{key} must be a non-negative integer")


def validate_live_target_image_contract(contract, label):
    if not isinstance(contract, dict):
        raise ValueError(f"{label} must be an object")
    validate_bool_field(contract, "ready", label)
    validate_string_list_field(contract, "missingKeys", label)
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


def validate_anchor_coverage(coverage, label):
    if not isinstance(coverage, dict):
        raise ValueError(f"{label} must be an object")
    for key in (
        "provided",
        "readyForObjectDiscovery",
        "readyForFindObjectSemantics",
        "readyForHookPlanning",
        "readyForPackageLoading",
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


def single_line_scalar(value):
    if not isinstance(value, (str, int, float, bool)):
        return False
    text = str(value)
    return bool(text.strip()) and "\n" not in text and "\r" not in text and "\0" not in text


def active_validation_candidates_from_payload(payload, source="active validation candidates"):
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must be a JSON object")
    candidates = payload.get("activeValidationCandidates", [])
    if not candidates and isinstance(payload.get("canaryHints"), dict):
        candidates = payload["canaryHints"].get("activeValidationCandidates", [])
    if not candidates and isinstance(payload.get("candidates"), list):
        candidates = payload["candidates"]
    if not isinstance(candidates, list):
        raise ValueError(f"{source} activeValidationCandidates must be a JSON array")
    validated = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"{source} activeValidationCandidates[{index}] must be a JSON object")
        for key, value in candidate.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{source} activeValidationCandidates[{index}] keys must be non-empty strings")
            if value is None:
                continue
            if not single_line_scalar(value):
                raise ValueError(
                    f"{source} activeValidationCandidates[{index}].{key} must be a non-empty single-line scalar"
                )
        validated.append(candidate)
    return validated


def merge_active_validation_candidate_files(report, paths):
    if not paths:
        return report
    merged = dict(report)
    hints = dict(merged.get("canaryHints", {}) or {})
    existing = active_validation_candidates_from_payload({"canaryHints": hints}, "readiness canaryHints")
    seen = {
        (
            str(candidate.get("objectAddress") or ""),
            str(candidate.get("functionAddress") or ""),
            str(candidate.get("functionPath") or ""),
        )
        for candidate in existing
    }
    for path in paths:
        payload = load_json(path)
        for candidate in active_validation_candidates_from_payload(payload, str(path)):
            key = (
                str(candidate.get("objectAddress") or ""),
                str(candidate.get("functionAddress") or ""),
                str(candidate.get("functionPath") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            existing.append(candidate)
    hints["activeValidationCandidates"] = existing[:16]
    merged["canaryHints"] = hints
    return merged


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


def plan_anchor_export(anchor_export):
    if not anchor_export:
        return None
    safe_kinds = {"ue-anchor-signature", "ue-runtime-discovery-candidate"}
    safe_entries = [
        entry
        for entry in anchor_export.get("entries", [])
        if entry.get("kind") in safe_kinds
    ]
    export = dict(anchor_export)
    export["entries"] = safe_entries
    export["entryCount"] = len(safe_entries)
    export["missing"] = [
        item
        for item in anchor_export.get("missing", [])
        if item not in {entry.get("name") for entry in safe_entries}
    ]
    return export


def unsafe_anchor_export_names(anchor_export):
    if not anchor_export:
        return []
    safe_kinds = {"ue-anchor-signature", "ue-runtime-discovery-candidate"}
    names = []
    for entry in anchor_export.get("entries", []):
        if entry.get("kind") not in safe_kinds:
            names.append(entry.get("name") or entry.get("matchedName") or "unknown")
    return names


def unquote_shell_value(value):
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("'\"'\"'", "'")
    return value


def parse_int(value, default=None):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def normalized_hex(value):
    parsed = parse_int(value)
    if parsed is None:
        return ""
    return f"0x{parsed:x}"


def hook_target_env_suffix(platform):
    if platform == "windows":
        return "RVA"
    return "IMAGE_OFFSET"


def hook_target_value_for_platform(args, process_name):
    explicit = {
        ("ProcessEvent", "server"): args.process_event_image_offset,
        ("ProcessEvent", "linux-client"): args.process_event_image_offset,
        ("ProcessEvent", "windows"): args.process_event_rva,
        ("CallFunction", "server"): args.call_function_image_offset,
        ("CallFunction", "linux-client"): args.call_function_image_offset,
        ("CallFunction", "windows"): args.call_function_rva,
    }.get((process_name, args.platform), "")
    if explicit:
        return normalized_hex(explicit)

    for path in args.hook_targets_json:
        payload = load_json(path)
        discovered = hook_target_value_from_json(payload, process_name, args.platform)
        if discovered:
            return discovered
    return ""


def hook_target_value_from_json(payload, process_name, platform):
    suffix = hook_target_env_suffix(platform)
    preferred_key = "rva" if suffix == "RVA" else "imageOffset"
    accepted_names = {
        "ProcessEvent": {"ProcessEvent", "UObject::ProcessEvent"},
        "CallFunction": {
            "CallFunction",
            "CallFunctionByNameWithArguments",
            "UObject::CallFunctionByNameWithArguments",
        },
    }[process_name]

    def rows(value):
        if isinstance(value, list):
            for row in value:
                yield row
            return
        if isinstance(value, dict):
            for key in ("targets", "hookTargets", "hookProbeTargets", "hookProbeShortlist", "rankedSlots"):
                nested = value.get(key)
                if isinstance(nested, list):
                    for row in nested:
                        yield row
            for key, nested in value.items():
                if key in accepted_names and isinstance(nested, dict):
                    yield nested
            yield value

    for row in rows(payload):
        if not isinstance(row, dict):
            continue
        target = row.get("topTarget") if isinstance(row.get("topTarget"), dict) else row
        target_name = str(target.get("targetName") or row.get("targetName") or row.get("name") or "")
        if target_name and target_name not in accepted_names:
            continue
        value = target.get(preferred_key) or row.get(preferred_key)
        if value:
            normalized = normalized_hex(value)
            if normalized:
                return normalized
    return ""


def set_hook_target_env(lines, args, process_name, reason):
    value = hook_target_value_for_platform(args, process_name)
    if not value:
        return
    prefix = env_prefix(args.platform)
    suffix = hook_target_env_suffix(args.platform)
    env_stem = "PROCESS_EVENT" if process_name == "ProcessEvent" else "CALL_FUNCTION"
    set_env(lines, f"{prefix}_UE_{env_stem}_HOOK_{suffix}", value, reason)
    set_env(lines, f"{prefix}_UE_{env_stem}_{suffix}", value, reason)
    set_env(lines, f"{prefix}_UE_{env_stem}_LIVE_HOOK_{suffix}", value, reason)


def has_hook_target(args, process_name):
    return bool(hook_target_value_for_platform(args, process_name))


def active_validation_hints(report):
    hints = report.get("canaryHints", {}) or {}
    candidates = hints.get("activeValidationCandidates", []) or []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def selected_active_validation_hint(args, report):
    if not args.use_active_validation_hints:
        return {}
    for candidate in active_validation_hints(report):
        if candidate.get("objectAddress") and candidate.get("functionAddress"):
            return candidate
    return {}


def active_validation_inputs(args, report):
    hint = selected_active_validation_hint(args, report)
    return {
        "objectAddress": args.active_validation_object_address or hint.get("objectAddress", ""),
        "processEventFunctionAddress": (
            args.process_event_active_function_address or hint.get("functionAddress", "")
        ),
        "processEventParamsAddress": args.process_event_active_params_address or hint.get("paramsAddress", ""),
        "callFunctionCommand": args.call_function_active_command or hint.get("callFunctionCommand", ""),
        "callFunctionCommandAddress": args.call_function_active_command_address,
        "callFunctionOutputAddress": args.call_function_active_output_address,
        "callFunctionExecutorAddress": args.call_function_active_executor_address,
        "hintFunctionPath": hint.get("functionPath", ""),
    }


def active_validation_has_process_event_input(inputs):
    return bool(inputs["objectAddress"] and inputs["processEventFunctionAddress"])


def active_validation_has_call_function_input(inputs):
    return bool(
        inputs["objectAddress"]
        and (inputs["callFunctionCommand"] or inputs["callFunctionCommandAddress"])
    )


def set_active_validation_env(lines, notes, args, report):
    prefix = env_prefix(args.platform)
    ready = report.get("ready", {}) or {}
    inputs = active_validation_inputs(args, report)
    needs_process_event = not ready_or_gate(
        report,
        "ueProcessEventActiveValidation",
        "ue-process-event-active-validation",
    )
    needs_call_function = not ready_or_gate(
        report,
        "ueCallFunctionActiveValidation",
        "ue-call-function-active-validation",
    )
    if needs_process_event:
        set_env(lines, f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE", "true", "actively exercise persistent ProcessEvent hook when explicit runtime inputs are supplied")
        set_env(
            lines,
            f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
            "true" if args.allow_active_native_call else "false",
            "native ProcessEvent invocation remains closed unless explicitly allowed for this canary",
        )
        set_env(
            lines,
            f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET",
            "true" if args.active_validation_through_target else "false",
            "call the patched target entrypoint instead of the replacement shim during active ProcessEvent validation",
        )
        set_env(
            lines,
            f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL",
            "true" if args.suppress_process_event_original else "false",
            "suppress forwarding synthetic ProcessEvent validation calls to the native original",
        )
        if inputs["objectAddress"]:
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS", inputs["objectAddress"], "runtime UObject address for active ProcessEvent validation")
        if inputs["processEventFunctionAddress"]:
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS", inputs["processEventFunctionAddress"], "runtime UFunction address for active ProcessEvent validation")
        if inputs["processEventParamsAddress"]:
            set_env(lines, f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS", inputs["processEventParamsAddress"], "optional descriptor-backed params buffer for active ProcessEvent validation")
        if args.use_active_validation_hints and inputs["hintFunctionPath"]:
            notes.append(f"Active ProcessEvent validation inputs were promoted from canary hint function path {inputs['hintFunctionPath']}.")
        if not args.allow_active_native_call:
            notes.append("Active ProcessEvent validation is planned but native invocation is gated; pass --allow-active-native-call only after runtime object/function inputs are reviewed.")
        elif not active_validation_has_process_event_input(inputs):
            notes.append("Active ProcessEvent validation is allowed but missing runtime object/function input; pass --active-validation-object-address and --process-event-active-function-address.")
        elif args.suppress_process_event_original:
            notes.append("Active ProcessEvent validation will prove target-entry hook/dispatch without forwarding the synthetic call to the native original.")

    if needs_call_function:
        set_env(lines, f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE", "true", "actively exercise persistent CallFunctionByNameWithArguments hook when explicit runtime inputs are supplied")
        set_env(
            lines,
            f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
            "true" if args.allow_active_native_call else "false",
            "native CallFunction invocation remains closed unless explicitly allowed for this canary",
        )
        set_env(
            lines,
            f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET",
            "true" if args.active_validation_through_target else "false",
            "call the patched target entrypoint instead of the replacement shim during active CallFunction validation",
        )
        if inputs["objectAddress"]:
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS", inputs["objectAddress"], "runtime UObject address for active CallFunction validation")
        if inputs["callFunctionCommand"]:
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND", inputs["callFunctionCommand"], "command string for active CallFunction validation")
        if inputs["callFunctionCommandAddress"]:
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND_ADDRESS", inputs["callFunctionCommandAddress"], "runtime command string address for active CallFunction validation")
        if inputs["callFunctionOutputAddress"]:
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OUTPUT_ADDRESS", inputs["callFunctionOutputAddress"], "optional output device address for active CallFunction validation")
        if inputs["callFunctionExecutorAddress"]:
            set_env(lines, f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_EXECUTOR_ADDRESS", inputs["callFunctionExecutorAddress"], "optional executor address for active CallFunction validation")
        if args.use_active_validation_hints and inputs["hintFunctionPath"]:
            notes.append(f"Active CallFunction validation command was promoted from canary hint function path {inputs['hintFunctionPath']}.")
        set_env(
            lines,
            f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_FORCE_CALL",
            "true" if args.call_function_active_force_call else "false",
            "forceCall flag for active CallFunction validation",
        )
        if not args.allow_active_native_call:
            notes.append("Active CallFunction validation is planned but native invocation is gated; pass --allow-active-native-call only after runtime object/command inputs are reviewed.")
        elif not active_validation_has_call_function_input(inputs):
            notes.append("Active CallFunction validation is allowed but missing runtime object/command input; pass --active-validation-object-address and --call-function-active-command or --call-function-active-command-address.")


def load_asset_package_native_invocation_script(path):
    quoted_path = path.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "local path='"
        + quoted_path
        + "'; "
        + "local executor=GetLoadAssetPackageNativeExecutorState(path); "
        + "local native=InvokeLoadAssetPackageNative(path,{Invoke=true}); "
        + "if not (executor and native and native.Invoked and native.InvokeRequested and native.TargetImage and native.NativeCallable and native.NativeCallExecutionMode=='guarded-native-package-load' and native.NativeReturnValidated and native.NativeReturnNonNull and native.NativeReturnMapped and native.NativeReturnReadable) then "
        + "error('load asset package native invocation canary failed') end; "
        + "return 42"
    )


def load_asset_package_native_invocation_ready_for_planning(report):
    return ready_or_gate(
        report,
        "luaLoadAssetPackageNativeExecutor",
        "lua-load-asset-package-native-executor",
    )


def set_load_asset_package_native_invocation_env(lines, notes, args, report):
    if ready_or_gate(
        report,
        "luaLoadAssetPackageNativeInvocation",
        "lua-load-asset-package-native-invocation",
    ):
        return

    prefix = env_prefix(args.platform)
    set_env(lines, f"{prefix}_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD", "true", "arm recoverable crash guard before guarded package LoadAsset native invocation")

    executor_ready = load_asset_package_native_invocation_ready_for_planning(report)
    allowed = bool(args.allow_load_asset_package_native_call)
    confirmed = bool(args.confirm_load_asset_package_native_call or args.allow_load_asset_package_native_call)
    set_env(
        lines,
        f"{prefix}_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
        "true" if allowed else "false",
        "native package LoadAsset invocation remains closed unless explicitly allowed for this canary",
    )
    set_env(
        lines,
        f"{prefix}_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL",
        "true" if confirmed else "false",
        "final package LoadAsset native call confirmation remains closed without reviewed ABI/TCHAR evidence",
    )
    set_env(
        lines,
        f"{prefix}_CONFIRM_LOAD_ASSET_PACKAGE_ABI",
        "true" if args.load_asset_package_abi_evidence else "false",
        "require reviewed package LoadAsset ABI evidence before native invocation can be callable",
    )
    if args.load_asset_package_abi_evidence:
        set_env(
            lines,
            f"{prefix}_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
            args.load_asset_package_abi_evidence,
            "reviewed StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage ABI evidence for the guarded native package canary",
        )
    set_env(
        lines,
        f"{prefix}_CONFIRM_TCHAR_LAYOUT",
        "true" if args.load_asset_package_tchar_evidence and args.load_asset_package_tchar_unit_bytes else "false",
        "require reviewed TCHAR unit-width evidence before native package path marshalling",
    )
    if args.load_asset_package_tchar_unit_bytes:
        set_env(
            lines,
            f"{prefix}_TCHAR_UNIT_BYTES",
            args.load_asset_package_tchar_unit_bytes,
            "observed TCHAR unit width for guarded package LoadAsset path marshalling",
        )
    if args.load_asset_package_tchar_evidence:
        set_env(
            lines,
            f"{prefix}_TCHAR_EVIDENCE",
            args.load_asset_package_tchar_evidence,
            "reviewed TCHAR layout evidence for guarded package LoadAsset path marshalling",
        )

    if args.load_asset_package_native_script:
        set_env(
            lines,
            f"{prefix}_LUA_SELF_TEST_SCRIPT",
            load_asset_package_native_invocation_script(args.load_asset_package_path),
            "execute InvokeLoadAssetPackageNative(path,{Invoke=true}) through the Lua self-test canary",
        )
    else:
        notes.append("Package LoadAsset native invocation is planned, but no Lua self-test script was emitted; pass --load-asset-package-native-script after choosing a reviewed package path.")

    if not executor_ready:
        notes.append("Package LoadAsset native invocation is blocked until luaLoadAssetPackageNativeExecutor is proven against a target-image package-loading anchor.")
    elif not allowed:
        notes.append("Package LoadAsset native invocation is planned but gated; pass --allow-load-asset-package-native-call only after ABI/TCHAR evidence and package path are reviewed.")
    elif not args.load_asset_package_path:
        notes.append("Package LoadAsset native invocation is allowed but missing a package path; pass --load-asset-package-path.")
    elif not args.load_asset_package_abi_evidence:
        notes.append("Package LoadAsset native invocation is allowed but missing --load-asset-package-abi-evidence.")
    elif not (args.load_asset_package_tchar_unit_bytes and args.load_asset_package_tchar_evidence):
        notes.append("Package LoadAsset native invocation is allowed but missing TCHAR layout evidence; pass --load-asset-package-tchar-unit-bytes and --load-asset-package-tchar-evidence.")


PACKAGE_PROMOTION_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL",
    "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
    "DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES",
    "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT",
}
PACKAGE_CLASS_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
}
PACKAGE_ASSET_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL",
    "DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES",
    "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT",
}
ASSET_FAMILIES = {"StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"}
PACKAGE_TRACE_FAMILIES = ASSET_FAMILIES | {"StaticLoadClass"}
PACKAGE_PROMOTION_ACCEPTANCE_SCHEMA = "dune-ue4ss-package-anchor-promotion-acceptance/v1"


def non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def present_non_true(value):
    return value is not None and value is not True


def platform_package_env_name(platform, key):
    server_prefix = "DUNE_PROBE_LOADER"
    if not key.startswith(server_prefix + "_"):
        return ""
    return env_prefix(platform) + key[len(server_prefix):]


SUMMARY_MANIFEST_MATCH_FIELDS = (
    "signatureFamily",
    "hitIndex",
    "selectedHitSeed",
    "sourceEvidence",
    "sourceEvidenceJson",
    "sourceEvidenceJsonSha256",
    "sourceLogSha256",
    "sourceLogExists",
    "sourceTracePlan",
    "sourceTracePlanSchemaVersion",
    "sourcePromotionAcceptanceSchemaVersion",
    "sourceExternalPlan",
    "callerImageOffset",
    "ripImageOffset",
    "abiReviewReady",
    "abiReviewed",
    "targetImageReviewed",
    "tcharReviewed",
    "classRootReviewed",
    "readyForNonInvokingCanary",
    "readyForNativeInvoke",
    "nativeInvokeEnabled",
    "finalNativeCallConfirmed",
)

SUMMARY_MANIFEST_TARGET_MATCH_FIELDS = (
    "tracePid",
    "tracePidMatchesRequested",
    "imageRangeSource",
    "imageBase",
    "imageStart",
    "imageEnd",
    "imagePath",
    "imagePerms",
)


def package_promotion_summary_ready_rows(summary_path, summary):
    ready_rows = {}
    manifest_rows = summary.get("manifests", [])
    if manifest_rows is None:
        manifest_rows = []
    if not isinstance(manifest_rows, list):
        raise ValueError(f"{summary_path}: package promotion summary manifests must be a JSON array")
    for index, row in enumerate(manifest_rows):
        if not isinstance(row, dict):
            raise ValueError(f"{summary_path}: package promotion summary manifest row {index} must be a JSON object")
        if row.get("readyForNonInvokingCanary") is not True and row.get("readyForNativeInvoke") is not True:
            continue
        raw_path = str(row.get("path", ""))
        if raw_path in ready_rows:
            raise ValueError(f"{summary_path}: duplicate ready package promotion summary row: {raw_path}")
        ready_rows[raw_path] = row
    ready_manifest_paths = summary.get("readyManifestPaths", [])
    if ready_manifest_paths is None:
        ready_manifest_paths = []
    if not isinstance(ready_manifest_paths, list):
        raise ValueError(f"{summary_path}: package promotion summary readyManifestPaths must be a JSON array")
    ready_paths = []
    seen_ready_paths = set()
    rows = []
    for raw_path in ready_manifest_paths:
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"{summary_path}: invalid readyManifestPaths entry")
        if raw_path in seen_ready_paths:
            raise ValueError(f"{summary_path}: duplicate readyManifestPaths entry: {raw_path}")
        seen_ready_paths.add(raw_path)
        ready_paths.append(raw_path)
        row = ready_rows.get(raw_path)
        if row is None:
            raise ValueError(f"{summary_path}: ready manifest path is not backed by a ready manifest row: {raw_path}")
        rows.append((Path(raw_path), row))
    omitted_ready_paths = sorted(set(ready_rows) - set(ready_paths))
    if omitted_ready_paths:
        raise ValueError(
            f"{summary_path}: ready manifest row is missing from readyManifestPaths: {omitted_ready_paths[0]}"
        )
    return rows


def package_promotion_summary_manifest_errors(summary_path, path, summary_row, manifest):
    errors = []
    if summary_row.get("readyForNonInvokingCanary") is True or summary_row.get("readyForNativeInvoke") is True:
        for error in single_line_scalar_errors(
            "ready summary row",
            summary_row,
            (
                "sourceEvidence",
                "sourceEvidenceJson",
                "sourceEvidenceJsonSha256",
                "sourceLogSha256",
                "sourceTracePlan",
                "sourceTracePlanSchemaVersion",
                "sourcePromotionAcceptanceSchemaVersion",
                "sourceExternalPlan",
                "tracePid",
                "imageRangeSource",
                "imageBase",
                "imageStart",
                "imageEnd",
                "imagePath",
                "imagePerms",
                "callerImageOffset",
                "ripImageOffset",
                "selectedHitSeed",
            ),
        ):
            errors.append(f"{summary_path}: {error} for {path}")
        if not summary_row.get("sourceEvidence", ""):
            errors.append(f"{summary_path}: ready summary row is missing sourceEvidence for {path}")
        if not summary_row.get("sourceEvidenceJson", ""):
            errors.append(f"{summary_path}: ready summary row is missing sourceEvidenceJson for {path}")
        if not summary_row.get("sourceEvidenceJsonSha256", ""):
            errors.append(f"{summary_path}: ready summary row is missing sourceEvidenceJsonSha256 for {path}")
        if not summary_row.get("sourceLogSha256", ""):
            errors.append(f"{summary_path}: ready summary row is missing sourceLogSha256 for {path}")
        if "sourceLogExists" not in summary_row:
            errors.append(f"{summary_path}: ready summary row is missing sourceLogExists for {path}")
        elif summary_row.get("sourceLogExists") is not True:
            errors.append(f"{summary_path}: ready summary row sourceLog does not exist for {path}")
        if not non_negative_int(summary_row.get("hitIndex")):
            errors.append(f"{summary_path}: ready summary row is missing concrete hitIndex for {path}")
        selected_hit_seed = summary_row.get("selectedHitSeed", "")
        family = summary_row.get("signatureFamily", "")
        if not selected_hit_seed:
            errors.append(f"{summary_path}: ready summary row is missing selectedHitSeed for {path}")
        if selected_hit_seed and family and selected_hit_seed != family:
            errors.append(f"{summary_path}: ready summary row selectedHitSeed does not match signatureFamily for {path}")
        if family not in PACKAGE_TRACE_FAMILIES:
            errors.append(f"{summary_path}: unsupported package promotion signatureFamily: {family} for {path}")
        if not summary_row.get("callerImageOffset", ""):
            errors.append(f"{summary_path}: ready summary row is missing callerImageOffset for {path}")
        if not summary_row.get("ripImageOffset", ""):
            errors.append(f"{summary_path}: ready summary row is missing ripImageOffset for {path}")
        if summary_row.get("abiReviewReady") is not True:
            errors.append(f"{summary_path}: ready summary row is missing ABI review readiness for {path}")
        if summary_row.get("abiReviewed") is not True:
            errors.append(f"{summary_path}: ready summary row is missing reviewed ABI confirmation for {path}")
        if summary_row.get("targetImageReviewed") is not True:
            errors.append(f"{summary_path}: ready summary row is missing reviewed target-image confirmation for {path}")
        if family == "StaticLoadClass" and summary_row.get("classRootReviewed") is not True:
            errors.append(f"{summary_path}: ready summary row is missing reviewed class-root confirmation for {path}")
        if family in ASSET_FAMILIES and summary_row.get("tcharReviewed") is not True:
            errors.append(f"{summary_path}: ready summary row is missing reviewed TCHAR confirmation for {path}")
        if summary_row.get("readyForNativeInvoke") is True and summary_row.get("nativeInvokeEnabled") is not True:
            errors.append(f"{summary_path}: ready native summary row is missing native invoke enablement for {path}")
        if summary_row.get("readyForNativeInvoke") is True and summary_row.get("finalNativeCallConfirmed") is not True:
            errors.append(f"{summary_path}: ready native summary row is missing final native-call confirmation for {path}")
    for field in SUMMARY_MANIFEST_MATCH_FIELDS:
        if field not in summary_row:
            continue
        if summary_row.get(field) != manifest.get(field):
            errors.append(f"{summary_path}: summary row {field} does not match promotion manifest {path}")
    for field in SUMMARY_MANIFEST_TARGET_MATCH_FIELDS:
        summary_value = summary_row.get(field)
        manifest_value = manifest.get(field)
        if summary_value in (None, "") and manifest_value in (None, ""):
            continue
        if summary_value in (None, ""):
            errors.append(f"{summary_path}: summary row is missing {field} for promotion manifest {path}")
            continue
        if manifest_value in (None, ""):
            errors.append(f"{summary_path}: promotion manifest is missing {field} for summary row {path}")
            continue
        if str(summary_value) != str(manifest_value):
            errors.append(f"{summary_path}: summary row {field} does not match promotion manifest {path}")
    priority_path = Path(path).parent / "review-priority.json"
    if priority_path.is_file():
        try:
            priority = load_json(priority_path)
        except json.JSONDecodeError as exc:
            errors.append(f"{summary_path}: invalid JSON in review priority {priority_path}: {exc}")
            priority = {}
        if "reviewPriority" in summary_row and summary_row.get("reviewPriority") != priority.get("rank"):
            errors.append(f"{summary_path}: summary row reviewPriority does not match review priority {priority_path}")
        if "reviewPriorityHitIndex" in summary_row and summary_row.get("reviewPriorityHitIndex") != priority.get("hitIndex"):
            errors.append(f"{summary_path}: summary row reviewPriorityHitIndex does not match review priority {priority_path}")
    return errors


def package_promotion_manifests(args):
    manifests = []
    paths = [(Path(path), None, None) for path in args.package_promotion_json]
    for directory in args.package_promotion_dir:
        paths.extend((path, None, None) for path in package_promotion_dir_paths(directory))
    for summary_path in args.package_promotion_summary_json:
        summary = load_json(summary_path)
        if not isinstance(summary, dict):
            raise ValueError(f"{summary_path}: package promotion summary must be a JSON object")
        if summary.get("schemaVersion") != "dune-ue4ss-package-promotion-dir-summary/v1":
            raise ValueError(f"{summary_path}: not a UE4SS package promotion directory summary")
        summary_errors = summary.get("errors", [])
        if summary_errors is None:
            summary_errors = []
        if not isinstance(summary_errors, list):
            raise ValueError(f"{summary_path}: package promotion summary errors must be a JSON array")
        if summary.get("errorCount", 0) or summary_errors:
            first_error_row = summary_errors[0] if summary_errors else {}
            first_error = first_error_row.get("error", "unknown") if isinstance(first_error_row, dict) else str(first_error_row)
            raise ValueError(f"{summary_path}: package promotion summary has validation errors: {first_error}")
        paths.extend((path, row, Path(summary_path)) for path, row in package_promotion_summary_ready_rows(summary_path, summary))
    for path, summary_row, summary_path in paths:
        payload = load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: package promotion manifest must be a JSON object")
        if payload.get("schemaVersion") != "dune-ue4ss-package-promotion-env/v1":
            raise ValueError(f"{path}: not a UE4SS package promotion env manifest")
        if summary_row is not None:
            summary_manifest_errors = package_promotion_summary_manifest_errors(summary_path, path, summary_row, payload)
            if summary_manifest_errors:
                raise ValueError(summary_manifest_errors[0])
        manifests.append((path, payload))
    return manifests


def package_promotion_review_priority(path):
    priority_path = Path(path).parent / "review-priority.json"
    if not priority_path.is_file():
        return None
    payload = load_json(priority_path)
    if not isinstance(payload, dict):
        raise ValueError(f"{priority_path}: review priority must be a JSON object")
    if payload.get("schemaVersion") != "dune-ue4ss-package-review-priority/v1":
        raise ValueError(f"{priority_path}: unsupported review priority schemaVersion")
    rank = payload.get("rank")
    if not non_negative_int(rank):
        raise ValueError(f"{priority_path}: invalid review priority rank")
    hit_index = payload.get("hitIndex", "auto")
    if hit_index != "auto" and not non_negative_int(hit_index):
        raise ValueError(f"{priority_path}: invalid review priority hitIndex")
    family = payload.get("signatureFamily", "")
    if not family:
        raise ValueError(f"{priority_path}: missing review priority signatureFamily")
    if priority_path.parent.name != family:
        raise ValueError(f"{priority_path}: review priority signatureFamily does not match parent directory")
    manifest = load_json(path)
    if not isinstance(manifest, dict):
        raise ValueError(f"{path}: package promotion manifest must be a JSON object")
    manifest_family = manifest.get("signatureFamily", "")
    if manifest_family and manifest_family != family:
        raise ValueError(f"{priority_path}: review priority signatureFamily does not match promotion manifest")
    return rank


def package_promotion_dir_paths(directory):
    paths = [path for path in Path(directory).glob("*/promotion-env.json") if path.is_file()]
    ranks = {path: package_promotion_review_priority(path) for path in paths}
    return sorted(
        paths,
        key=lambda path: (
            ranks[path] if ranks[path] is not None else 10_000,
            str(path),
        ),
    )


def validate_package_promotion_args(args):
    if args.package_promotion_json or args.package_promotion_dir or args.package_promotion_summary_json:
        package_promotion_manifests(args)


def package_promotion_review_notes(path, manifest):
    notes = []
    family = manifest.get("signatureFamily", "unknown")
    evidence_keys = [
        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
        "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
        "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
    ]
    env = manifest.get("env") or {}
    if not isinstance(env, dict):
        env = {}
    evidence_values = [
        f"{key}={env[key]}"
        for key in evidence_keys
        if env.get(key)
    ]
    if evidence_values:
        notes.append(
            f"Package promotion manifest {path} for {family} evidence: "
            + "; ".join(evidence_values)
            + "."
        )
    identity_parts = []
    if manifest.get("tracePid") not in (None, ""):
        identity_parts.append(f"tracePid={manifest.get('tracePid')}")
    for key in ("imageRangeSource", "imageBase", "imageStart", "imageEnd", "imagePath", "imagePerms"):
        if manifest.get(key):
            identity_parts.append(f"{key}={manifest.get(key)}")
    if identity_parts:
        notes.append(
            f"Package promotion manifest {path} for {family} target identity: "
            + "; ".join(identity_parts)
            + "."
        )
    abi_review = manifest.get("abiReview", {}) or {}
    if not isinstance(abi_review, dict):
        abi_review = {}
    if abi_review.get("provided"):
        notes.append(
            f"Package promotion manifest {path} for {family} ABI review ready={str(abi_review.get('ready') is True).lower()}."
        )
        for arg in abi_review.get("arguments", []) or []:
            if not isinstance(arg, dict):
                continue
            memory = arg.get("memory", {}) or {}
            if not isinstance(memory, dict):
                continue
            hints = memory.get("hints", {}) or {}
            if not isinstance(hints, dict):
                continue
            layouts = hints.get("candidateTcharLayouts", []) or []
            if not layouts:
                continue
            rendered = ", ".join(
                f"{item.get('unitBytes')}:{item.get('sample', '')}"
                for item in layouts
                if isinstance(item, dict)
            )
            if not rendered:
                continue
            notes.append(
                f"Package promotion manifest {path} for {family} {arg.get('role', '')} "
                f"candidateTcharLayouts={rendered}."
            )
    return notes


def string_list_field(payload, key):
    raw = payload.get(key, [])
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [f"{key} must be a JSON array"]
    values = []
    errors = []
    for index, value in enumerate(raw):
        if not isinstance(value, str):
            errors.append(f"{key}[{index}] must be a string")
            continue
        values.append(value)
    return values, errors


def missing_required_memory_registers(hit):
    return string_list_field(hit, "missingRequiredMemoryRegisters")


def register_memory_shape_errors(hit):
    register_memory = (hit or {}).get("registerMemory", {})
    if register_memory is None:
        return []
    if not isinstance(register_memory, dict):
        return ["registerMemory must be a JSON object"]
    errors = []
    for register, rows in register_memory.items():
        if not isinstance(register, str) or not register:
            errors.append("registerMemory contains an invalid register key")
            continue
        if not isinstance(rows, list):
            errors.append(f"registerMemory.{register} must be a JSON array")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, str):
                errors.append(f"registerMemory.{register}[{index}] must be a string")
                break
    return errors


def abi_review_argument_shape_errors(abi_review):
    arguments = (abi_review or {}).get("arguments", [])
    if arguments is None:
        return []
    if not isinstance(arguments, list):
        return ["abiReview.arguments must be a JSON array"]
    errors = []
    for arg_index, argument in enumerate(arguments):
        if not isinstance(argument, dict):
            errors.append(f"abiReview.arguments[{arg_index}] must be a JSON object")
            continue
        memory = argument.get("memory", {})
        if memory is None:
            continue
        if not isinstance(memory, dict):
            errors.append(f"abiReview.arguments[{arg_index}].memory must be a JSON object")
            continue
        line_count = memory.get("lineCount", 0)
        if (
            not isinstance(line_count, int)
            or isinstance(line_count, bool)
            or line_count < 0
        ):
            errors.append(
                f"abiReview.arguments[{arg_index}].memory.lineCount must be a non-negative integer"
            )
        hints = memory.get("hints", {})
        if hints is not None and not isinstance(hints, dict):
            errors.append(f"abiReview.arguments[{arg_index}].memory.hints must be a JSON object")
    return errors


def object_field(payload, key):
    raw = payload.get(key, {}) or {}
    if not isinstance(raw, dict):
        return {}, [f"{key} must be a JSON object"]
    return raw, []


def single_line_scalar_errors(label, payload, fields):
    errors = []
    for field in fields:
        if field not in payload:
            continue
        value = payload.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, (str, int, float, bool)):
            errors.append(f"{label} {field} must be a scalar")
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append(f"{label} {field} must be a non-empty single-line value")
    return errors


def package_promotion_identity_errors(path, manifest):
    errors = []
    caller_offset = manifest.get("callerImageOffset", "")
    rip_offset = manifest.get("ripImageOffset", "")
    selected_hit_seed = manifest.get("selectedHitSeed", "")
    family = manifest.get("signatureFamily", "")
    ready_non_invoking = manifest.get("readyForNonInvokingCanary") is True
    ready_native = manifest.get("readyForNativeInvoke") is True
    if ready_non_invoking or ready_native:
        for error in single_line_scalar_errors(
            "package promotion manifest",
            manifest,
            (
                "sourceEvidence",
                "sourceEvidenceJson",
                "sourceEvidenceJsonSha256",
                "sourceLogSha256",
                "sourceTracePlan",
                "sourceTracePlanSchemaVersion",
                "sourcePromotionAcceptanceSchemaVersion",
                "sourceExternalPlan",
                "tracePid",
                "imageRangeSource",
                "imageBase",
                "imageStart",
                "imageEnd",
                "imagePath",
                "imagePerms",
                "callerImageOffset",
                "ripImageOffset",
                "selectedHitSeed",
            ),
        ):
            errors.append(f"{path}: {error}")
        if family not in PACKAGE_TRACE_FAMILIES:
            errors.append(f"{path}: unsupported package promotion signatureFamily: {family}")
        blockers, blocker_shape_errors = string_list_field(manifest, "blockers")
        abi_review, abi_shape_errors = object_field(manifest, "abiReview")
        abi_blockers, abi_blocker_shape_errors = string_list_field(abi_review, "blockers")
        missing_review, missing_review_shape_errors = string_list_field(manifest, "missingReviewFlags")
        missing_native, missing_native_shape_errors = string_list_field(manifest, "missingNativeInvokeFlags")
        for error in (
            blocker_shape_errors
            + abi_shape_errors
            + [f"abiReview.{item}" for item in abi_blocker_shape_errors]
            + abi_review_argument_shape_errors(abi_review)
            + missing_review_shape_errors
            + missing_native_shape_errors
        ):
            errors.append(f"{path}: {error}")
        if ready_native and not ready_non_invoking:
            errors.append(f"{path}: ready native package promotion manifest is missing non-invoking canary readiness")
        if blockers:
            errors.append(f"{path}: ready package promotion manifest still has blockers")
        if abi_blockers:
            errors.append(f"{path}: ready package promotion manifest still has ABI review blockers")
        if manifest.get("abiReviewReady") is not True and abi_review.get("ready") is not True:
            errors.append(f"{path}: ready package promotion manifest is missing ABI review readiness")
        if manifest.get("abiReviewed") is not True:
            errors.append(f"{path}: ready package promotion manifest is missing reviewed ABI confirmation")
        if manifest.get("promotionAcceptanceSchemaVersion") != PACKAGE_PROMOTION_ACCEPTANCE_SCHEMA:
            errors.append(f"{path}: ready package promotion manifest is missing current package promotion acceptance schema")
        if manifest.get("targetImageReviewed") is not True:
            errors.append(f"{path}: ready package promotion manifest is missing reviewed target-image confirmation")
        if family == "StaticLoadClass" and manifest.get("classRootReviewed") is not True:
            errors.append(f"{path}: ready package promotion manifest is missing reviewed class-root confirmation")
        if family in ASSET_FAMILIES and manifest.get("tcharReviewed") is not True:
            errors.append(f"{path}: ready package promotion manifest is missing reviewed TCHAR confirmation")
        if ready_native and manifest.get("nativeInvokeEnabled") is not True:
            errors.append(f"{path}: ready native package promotion manifest is missing native invoke enablement")
        if ready_native and manifest.get("finalNativeCallConfirmed") is not True:
            errors.append(f"{path}: ready native package promotion manifest is missing final native-call confirmation")
        if missing_review:
            errors.append(f"{path}: ready package promotion manifest still has missing review flags")
        if ready_native and missing_native:
            errors.append(f"{path}: ready native package promotion manifest still has missing native invoke flags")
        if not manifest.get("sourceEvidence", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceEvidence")
        if not manifest.get("sourceEvidenceJson", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceEvidenceJson provenance")
        if not manifest.get("sourceEvidenceJsonSha256", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceEvidenceJsonSha256 provenance")
        if not manifest.get("sourceLogSha256", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceLogSha256 provenance")
        if "sourceLogExists" not in manifest:
            errors.append(f"{path}: ready package promotion manifest is missing sourceLogExists")
        elif manifest.get("sourceLogExists") is not True:
            errors.append(f"{path}: ready package promotion manifest sourceLog does not exist")
        if not manifest.get("sourceTracePlan", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceTracePlan provenance")
        if not manifest.get("sourceTracePlanSchemaVersion", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceTracePlanSchemaVersion provenance")
        if manifest.get("sourcePromotionAcceptanceSchemaVersion") != PACKAGE_PROMOTION_ACCEPTANCE_SCHEMA:
            errors.append(f"{path}: ready package promotion manifest is missing current source promotion acceptance schema provenance")
        if not manifest.get("sourceExternalPlan", ""):
            errors.append(f"{path}: ready package promotion manifest is missing sourceExternalPlan provenance")
        if "tracePidMatchesRequested" not in manifest:
            errors.append(f"{path}: ready package promotion manifest is missing runtime trace PID match provenance")
        elif manifest.get("tracePidMatchesRequested") is not True:
            errors.append(f"{path}: trace log armed PID does not match requested runtime PID")
        if not non_negative_int(manifest.get("hitIndex")):
            errors.append(f"{path}: ready package promotion manifest is missing concrete hitIndex")
        if not selected_hit_seed:
            errors.append(f"{path}: ready package promotion manifest is missing selectedHitSeed")
        if selected_hit_seed and family and selected_hit_seed != family:
            errors.append(f"{path}: selectedHitSeed does not match signatureFamily")
        if not caller_offset:
            errors.append(f"{path}: ready package promotion manifest is missing callerImageOffset")
        if not rip_offset:
            errors.append(f"{path}: ready package promotion manifest is missing ripImageOffset")
        hit = manifest.get("hit", {}) or {}
        if isinstance(hit, dict) and hit:
            if present_non_true(hit.get("traceLogHasArmed")):
                errors.append(f"{path}: embedded trace hit missing trace armed record; cannot prove runtime trace session")
            if present_non_true(hit.get("tracePidMatchesRequested")):
                errors.append(f"{path}: embedded trace hit trace log armed PID does not match requested runtime PID")
            if hit.get("traceAddressMatchesBase") is not True:
                errors.append(f"{path}: embedded trace hit address does not match image base plus seed imageOffset")
            for error in register_memory_shape_errors(hit):
                errors.append(f"{path}: embedded trace hit {error}")
            missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(hit)
            for error in missing_required_memory_errors:
                errors.append(f"{path}: embedded trace hit {error}")
            if missing_required_memory:
                errors.append(
                    f"{path}: embedded trace hit is missing required memory registers: "
                    + ", ".join(str(item) for item in missing_required_memory)
                )
            hit_seed = hit.get("seed", "")
            if selected_hit_seed and hit_seed and selected_hit_seed != hit_seed:
                errors.append(f"{path}: selectedHitSeed does not match embedded trace hit seed")
            if hit_seed and family and hit_seed != family:
                errors.append(f"{path}: embedded trace hit seed does not match signatureFamily")
            if hit.get("callerImageOffset", "") and hit.get("callerImageOffset", "") != caller_offset:
                errors.append(f"{path}: embedded trace hit callerImageOffset does not match manifest")
            if hit.get("ripImageOffset", "") and hit.get("ripImageOffset", "") != rip_offset:
                errors.append(f"{path}: embedded trace hit ripImageOffset does not match manifest")
    raw_env = manifest.get("env") or {}
    if not isinstance(raw_env, dict):
        errors.append(f"{path}: package promotion env must be an object")
        env = {}
    else:
        env = raw_env
        for key, value in env.items():
            if not isinstance(key, str) or not key:
                errors.append(f"{path}: package promotion env contains an invalid key")
                break
            if isinstance(value, (dict, list)):
                errors.append(f"{path}: package promotion env contains a non-scalar value for {key}")
                break
    if family == "StaticLoadClass":
        wrong_keys = sorted(key for key in env if key in PACKAGE_ASSET_ENV_KEYS and env.get(key))
        if wrong_keys:
            errors.append(f"{path}: StaticLoadClass promotion env includes LoadAsset package keys")
    elif family in ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"):
        wrong_keys = sorted(key for key in env if key in PACKAGE_CLASS_ENV_KEYS and env.get(key))
        if wrong_keys:
            errors.append(f"{path}: {family} promotion env includes LoadClass package keys")
    runtime_evidence_values = [
        str(value)
        for key, value in env.items()
        if key in (
            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
            "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
            "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
        )
        and str(value).startswith("runtime-trace:")
    ]
    if family:
        for value in runtime_evidence_values:
            parts = value.split(":", 2)
            evidence_family = parts[1] if len(parts) > 1 else ""
            if evidence_family != family:
                errors.append(f"{path}: env evidence family does not match signatureFamily")
                break
        for value in runtime_evidence_values:
            if f"seed={family}" not in value and "seed=" in value:
                errors.append(f"{path}: env evidence seed does not match signatureFamily")
                break
    if caller_offset:
        evidence_values = [
            value
            for key, value in env.items()
            if key in (
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
                "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
            )
            and value
        ]
        for value in evidence_values:
            marker = f"caller={caller_offset}"
            if marker not in str(value):
                errors.append(f"{path}: env evidence caller does not match callerImageOffset")
                break
    if rip_offset:
        for value in runtime_evidence_values:
            marker = f"rip={rip_offset}"
            if marker not in str(value):
                errors.append(f"{path}: env evidence rip does not match ripImageOffset")
                break
    if ready_non_invoking or ready_native:
        if not non_negative_int(manifest.get("tracePid")):
            errors.append(f"{path}: ready package promotion manifest is missing concrete tracePid")
    return errors


def set_package_promotion_env(lines, notes, args):
    for path, manifest in package_promotion_manifests(args):
        family = manifest.get("signatureFamily", "unknown")
        ready_non_invoking = manifest.get("readyForNonInvokingCanary") is True
        ready_native = manifest.get("readyForNativeInvoke") is True
        notes.extend(package_promotion_review_notes(path, manifest))
        identity_errors = package_promotion_identity_errors(path, manifest)
        if identity_errors:
            raise ValueError(identity_errors[0])
        if not (ready_non_invoking or ready_native):
            blockers, blocker_shape_errors = string_list_field(manifest, "blockers")
            blockers.extend(blocker_shape_errors)
            if not blockers:
                blockers = ["not ready"]
            abi_review, abi_shape_errors = object_field(manifest, "abiReview")
            blockers.extend(abi_shape_errors)
            abi_blockers, abi_blocker_shape_errors = string_list_field(abi_review, "blockers")
            blockers.extend(f"ABI review: {blocker}" for blocker in abi_blockers)
            blockers.extend(f"ABI review: {error}" for error in abi_blocker_shape_errors)
            missing_review, missing_review_shape_errors = string_list_field(manifest, "missingReviewFlags")
            missing_native, missing_native_shape_errors = string_list_field(manifest, "missingNativeInvokeFlags")
            blockers.extend(missing_review_shape_errors)
            blockers.extend(missing_native_shape_errors)
            if missing_review:
                blockers.append("missing review flags: " + ", ".join(missing_review))
            if missing_native:
                blockers.append("missing native invoke flags: " + ", ".join(missing_native))
            if manifest.get("nextStep"):
                blockers.append("next step: " + manifest.get("nextStep", ""))
            blockers_text = "; ".join(blockers)
            notes.append(f"Package promotion manifest {path} for {family} is not ready; not emitting package promotion env ({blockers_text}).")
            continue
        emitted = 0
        for key, value in sorted((manifest.get("env") or {}).items()):
            if key not in PACKAGE_PROMOTION_ENV_KEYS:
                continue
            if not ready_native and (
                key.endswith("_ALLOW_LOAD_ASSET_PACKAGE_INVOKE")
                or key.endswith("_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL")
                or key.endswith("_ALLOW_LOAD_CLASS_PACKAGE_INVOKE")
                or key.endswith("_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL")
            ):
                continue
            env_name = platform_package_env_name(args.platform, key)
            if not env_name:
                continue
            set_env(
                lines,
                env_name,
                str(value),
                f"reviewed package promotion manifest {path} for {family}",
            )
            emitted += 1
        if emitted:
            notes.append(f"Applied {emitted} package promotion env values from {path} for {family}.")


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
        effective_counts = Counter(anchor_counts)
        for anchor, count in anchor_counts.items():
            if str(anchor).startswith("RuntimeFNamePoolCandidate"):
                effective_counts["RuntimeFNamePool"] += int(count or 0)
            if str(anchor).startswith("RuntimeGUObjectArrayCandidate"):
                effective_counts["RuntimeGUObjectArray"] += int(count or 0)
        emitted = [anchor for anchor in anchors if int(effective_counts.get(anchor, 0) or 0) > 0]
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


def manual_runtime_root_candidate_names(root_candidate_input):
    names = set()
    for row in root_candidate_input.get("candidates", []) or []:
        if row.get("sourcePath") != "<manual>":
            continue
        name = row.get("name", "")
        if name in {"RuntimeFNamePool", "RuntimeGUObjectArray"}:
            names.add(name)
    return names


def has_promoted_manual_runtime_roots(root_candidate_input, readiness):
    ready = readiness.get("ready", {}) if isinstance(readiness, dict) else {}
    if not isinstance(ready, dict):
        ready = {}
    manual_names = manual_runtime_root_candidate_names(root_candidate_input)
    return (
        {"RuntimeFNamePool", "RuntimeGUObjectArray"} <= manual_names
        and ready.get("runtimeRootDiscovery") is True
        and ready.get("runtimeRootValidation") is True
    )


def set_env(lines, name, value, reason):
    lines.append({"name": name, "value": value, "reason": reason})


def set_env_if_absent(lines, name, value, reason):
    if any(item["name"] == name for item in lines):
        return
    set_env(lines, name, value, reason)


def set_env_override(lines, name, value, reason):
    lines[:] = [item for item in lines if item["name"] != name]
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


def effective_target_filter(args):
    fragments = []
    seen = set()
    for fragment in args.exe_substring or []:
        if not fragment or fragment in seen:
            continue
        seen.add(fragment)
        fragments.append(fragment)
    if fragments:
        return ";".join(fragments)
    return default_target_filter(args.platform)


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


def runtime_candidate_carry_forward_entries(discovery, platform, excluded_names=None):
    excluded_names = set(excluded_names or [])
    validated_locations = list(discovery.get("validatedLocations") or [])
    candidate_locations = list(discovery.get("candidateLocations") or [])
    validated_names = {
        location.get("name", "")
        for location in validated_locations
        if location.get("name", "") in {"RuntimeFNamePool", "RuntimeGUObjectArray"}
    }
    locations = list(validated_locations)
    locations.extend(
        location
        for location in candidate_locations
        if location.get("name", "") in {"RuntimeFNamePool", "RuntimeGUObjectArray"}
        and location.get("name", "") not in validated_names
    )
    by_name = defaultdict(list)
    seen_locations = set()
    for location in locations:
        name = location.get("name", "")
        if name in {"RuntimeFNamePool", "RuntimeGUObjectArray"}:
            if name in excluded_names:
                continue
            key = (
                name,
                location.get("addr", ""),
                location.get("imageOffset", ""),
                location.get("fileOffset", ""),
                location.get("map", ""),
            )
            if key in seen_locations:
                continue
            seen_locations.add(key)
            by_name[name].append(location)

    entries = []
    for name, name_locations in sorted(by_name.items()):
        if len(name_locations) == 1:
            location = name_locations[0]
            image_offset = location.get("imageOffset", "")
            file_offset = location.get("fileOffset", "")
            if image_offset and runtime_candidate_location_is_target_image(location):
                entries.append(f"{name}={image_offset}")
            elif platform != "windows" and file_offset:
                entries.append(f"{name}@rwfile={file_offset}")
            continue
        if name not in {"RuntimeFNamePool", "RuntimeGUObjectArray"}:
            continue
        for index, location in enumerate(name_locations, start=1):
            image_offset = location.get("imageOffset", "")
            file_offset = location.get("fileOffset", "")
            candidate_name = f"{name}Candidate{index}"
            if image_offset and runtime_candidate_location_is_target_image(location):
                entries.append(f"{candidate_name}={image_offset}")
            elif platform != "windows" and file_offset:
                entries.append(f"{candidate_name}@rwfile={file_offset}")
    return entries


def candidate_entry_name(entry):
    name, _, _ = entry.partition("=")
    for suffix in ("@addr", "@rwfile"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def runtime_candidate_carry_forward_summary(
    discovery,
    platform,
    suppressed=False,
    suppression_reason="",
    excluded_names=None,
):
    excluded_names = set(excluded_names or [])
    entries = runtime_candidate_carry_forward_entries(discovery, platform, excluded_names=excluded_names)
    original_entries = list(entries)
    if suppressed:
        entries = []
    anchor_counts = dict(sorted(Counter(candidate_entry_name(entry) for entry in entries).items()))
    summary = {
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
    if suppressed:
        summary["suppressed"] = True
        summary["suppressionReason"] = suppression_reason
        summary["suppressedEntries"] = original_entries
        summary["suppressedEntryCount"] = len(original_entries)
    if excluded_names:
        summary["excludedNames"] = sorted(excluded_names)
    return summary


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
                "delayedProbeSeconds": "90",
                "candidateNotes": candidate_location_notes,
                "note": (
                    "Previous runtime discovery found GUObjectArray-shaped evidence but no RuntimeFNamePool "
                    "candidate; broaden the read-only mapping/region scan, retain a wider candidate set, "
                    "and run a delayed UE-only probe after process startup."
                ),
            }
        if missing_object_array and not missing_fname:
            return {
                "failure": "missing-object-array-root",
                "maxBytes": "536870912",
                "maxCandidates": "32",
                "minObjectArrayElements": "",
                "delayedProbeSeconds": "90",
                "candidateNotes": candidate_location_notes,
                "note": (
                    "Previous runtime discovery found FNamePool-shaped evidence but no RuntimeGUObjectArray "
                    "candidate; broaden the read-only mapping/region scan, retain a wider candidate set, "
                    "and run a delayed UE-only probe after process startup."
                ),
            }
        return {
            "failure": "no-root-hits",
            "maxBytes": "536870912",
            "maxCandidates": "32",
            "minObjectArrayElements": "",
            "delayedProbeSeconds": "90",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Previous runtime discovery scanned target image memory but did not find both root shapes; "
                "broaden candidate count and scan size, and run a delayed UE-only probe for the next "
                "read-only canary."
            ),
        }
    if failure_counts.get("ambiguous-root-hits"):
        ambiguous_roots = []
        if ambiguous_fname:
            ambiguous_roots.append("RuntimeFNamePool")
        if ambiguous_object_array:
            ambiguous_roots.append("RuntimeGUObjectArray")
        root_note = " (" + ", ".join(ambiguous_roots) + ")" if ambiguous_roots else ""
        bounded_candidate_count = max(fname_candidates, object_array_candidates, fname_hits, object_array_hits, 2)
        if bounded_candidate_count > 64:
            bounded_candidate_count = 64
        return {
            "failure": "ambiguous-root-hits",
            "maxBytes": "",
            "maxCandidates": str(bounded_candidate_count),
            "minObjectArrayElements": "128" if ambiguous_object_array else "",
            "promoteAmbiguousRoots": True,
            "delayedProbeSeconds": "90",
            "candidateNotes": candidate_location_notes,
            "note": (
                "Previous runtime discovery found ambiguous root hits"
                + root_note
                + "; keep the bounded candidate set and promote numbered candidates "
                "so FName/object-array consumers can validate the real root in the same delayed canary."
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


def plan_stage_index(stage):
    if stage in PLAN_STAGE_ORDER:
        return PLAN_STAGE_ORDER.index(stage)
    if stage in MAX_STAGES:
        return 0 if stage == "read-only" else PLAN_STAGE_ORDER.index(stage)
    return len(PLAN_STAGE_ORDER)


def blockers_for_selected_stage(blockers, stage):
    ceiling = plan_stage_index(stage)
    return [
        blocker
        for blocker in blockers
        if plan_stage_index(blocker.get("stage", "")) <= ceiling
    ]


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


def anchor_coverage_ready(report, ready_name):
    coverage = report.get("anchorCoverage", {}) or {}
    target_fields = {
        "anchorCoverageObjectDiscovery": "readyForTargetObjectDiscovery",
        "anchorCoverageHookPlanning": "readyForTargetHookPlanning",
        "anchorCoveragePackageLoading": "readyForTargetPackageLoading",
    }
    general_fields = {
        "anchorCoverageObjectDiscovery": "readyForObjectDiscovery",
        "anchorCoverageHookPlanning": "readyForHookPlanning",
        "anchorCoveragePackageLoading": "readyForPackageLoading",
    }
    target_field = target_fields.get(ready_name)
    if target_field and (
        coverage.get("targetCoverageFieldsPresent")
        or target_field in coverage
    ):
        return bool(coverage.get(target_field))
    general_field = general_fields.get(ready_name)
    if general_field and general_field in coverage:
        return bool(coverage.get(general_field))
    return None


def coverage_ready(report, ready_name, gate_name):
    if not coverage_provided(report):
        return True
    coverage = anchor_coverage_ready(report, ready_name)
    if coverage is not None:
        return coverage
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
        if bool(ready.get("targetObjectDiscovery")):
            return True
        return not missing_target_groups(report, REQUIRED_OBJECT_DISCOVERY_GROUPS)
    return not missing_target_groups(report, REQUIRED_OBJECT_DISCOVERY_GROUPS)


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


def choose_stage(report, args=None):
    ready = report.get("ready", {})
    explicit_process_event_target = bool(args and has_hook_target(args, "ProcessEvent"))
    explicit_call_function_target = bool(args and has_hook_target(args, "CallFunction"))
    process_event_hook_probe_ready = (
        explicit_process_event_target
        and ready.get("runtimeRootValidation")
        and object_array_registry_runtime_ready(report)
        and function_registry_runtime_ready(report)
        and not ready.get("ueProcessEventHookProbe")
    )
    process_event_live_hook_ready = (
        explicit_process_event_target
        and ready.get("ueProcessEventHookProbe")
        and runtime_ready(report, "ueProcessEventHookRuntimeTarget", "ue-process-event-hook-runtime-target")
        and not ready_or_gate(report, "ueProcessEventLiveHook", "ue-process-event-live-hook")
    )
    process_event_active_candidate_discovery_ready = (
        explicit_process_event_target
        and ready_or_gate(report, "ueProcessEventLiveHook", "ue-process-event-live-hook")
        and runtime_ready(report, "ueProcessEventLiveHookRuntimeTarget", "ue-process-event-live-hook-runtime-target")
        and not ready_or_gate(report, "ueProcessEventActiveValidation", "ue-process-event-active-validation")
    )
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
    if process_event_hook_probe_ready:
        return "hook-probe"
    if process_event_live_hook_ready:
        return "live-hook"
    if process_event_active_candidate_discovery_ready:
        return "live-hook"
    if not ready.get("objectDiscovery"):
        return "object-discovery"
    if object_anchor_blocks:
        return "object-discovery"
    if target_object_anchor_blocks and not explicit_process_event_target:
        return "object-discovery"
    if coverage_blocks_object and not explicit_process_event_target:
        return "object-discovery"
    if (
        ready.get("objectDiscovery")
        and proven_target_object_anchor_groups_ready(report)
        and coverage_ready(report, "anchorCoverageHookPlanning", "anchor-coverage-hook-planning")
        and not proven_target_dispatch_anchor_ready(report)
    ):
        return "hook-probe"
    if object_coverage and not object_coverage.get("readyForObjectDiscovery", False):
        return "object-discovery"
    if object_coverage and not object_coverage.get("readyForFindObjectSemantics", False):
        return "object-discovery"
    if not all_object_registry_runtime_ready(report):
        return "object-discovery"
    if not ready.get("reflection"):
        return "reflection"
    if reflection_anchor_blocks or dispatch_anchor_blocks:
        return "reflection"
    if coverage_blocks_hooks:
        return "reflection"
    if not function_registry_runtime_ready(report):
        return "reflection"
    if target_dispatch_anchor_blocks:
        return "hook-probe"
    if not ready.get("hookDispatch") and not gate(report, "hook-dispatch-self-test"):
        return "hook-probe"
    if not ready_or_gate(report, "ueProcessEventHookProbe", "ue-process-event-hook-probe"):
        return "hook-probe"
    if not runtime_ready(report, "ueProcessEventHookRuntimeTarget", "ue-process-event-hook-runtime-target"):
        return "hook-probe"
    if (explicit_call_function_target or ready.get("ueCallFunctionHookProbe")) and not runtime_ready(report, "ueCallFunctionHookRuntimeTarget", "ue-call-function-hook-runtime-target"):
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
    if not ready_or_gate(report, "ueCallFunctionLiveLuaDispatch", "ue-call-function-live-lua-dispatch"):
        return "lua-dispatch"
    if not ready_or_gate(report, "ueProcessEventActiveValidation", "ue-process-event-active-validation"):
        return "live-hook"
    if not ready_or_gate(report, "ueCallFunctionActiveValidation", "ue-call-function-active-validation"):
        return "live-hook"
    if not runtime_ready(report, "ueProcessEventLiveRuntimeContext", "ue-process-event-live-runtime-context"):
        return "live-hook"
    if not runtime_ready(report, "ueProcessEventLiveRuntimeRegistryContext", "ue-process-event-live-runtime-registry-context"):
        return "live-hook"
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
    if not ready_or_gate(
        report,
        "luaLoadAssetPackageNativeInvocation",
        "lua-load-asset-package-native-invocation",
    ):
        return "lua-dispatch"
    if not ready_or_gate(
        report,
        "luaLoadClassPackageNativeInvocation",
        "lua-load-class-package-native-invocation",
    ):
        return "lua-dispatch"
    return "complete"


def target_image_anchor_recovery_commands(args, anchor_coverage, target_object_missing, target_hook_missing, target_package_missing):
    xref_json = "build/ue4ss-anchor-canary/ue-anchor-xrefs.json"
    candidates_json = "build/ue4ss-anchor-canary/ue-anchor-candidates.json"
    recovered_dir = "build/ue4ss-anchor-canary/recovered-target-anchors"
    post_canary_log = default_canary_log_path(args.platform)
    coverage_provided = bool(anchor_coverage.get("provided"))
    target_object_ready = bool(anchor_coverage.get("readyForTargetObjectDiscovery"))
    target_hook_ready = bool(anchor_coverage.get("readyForTargetHookPlanning"))
    target_package_ready = bool(anchor_coverage.get("readyForTargetPackageLoading"))
    reasons = []
    if target_object_missing:
        reasons.append("missing-target-object-anchor-groups")
    if target_hook_missing:
        reasons.append("missing-target-hook-anchor-groups")
    if target_package_missing:
        reasons.append("missing-target-package-anchor-groups")
    if not coverage_provided:
        reasons.append("missing-prepared-anchor-coverage")
    if coverage_provided and not target_object_ready:
        reasons.append("incomplete-target-object-anchor-coverage")
    if coverage_provided and not target_hook_ready:
        reasons.append("incomplete-target-hook-anchor-coverage")
    if coverage_provided and not target_package_ready:
        reasons.append("incomplete-target-package-anchor-coverage")
    needs_recovery = (
        target_object_missing
        or target_hook_missing
        or target_package_missing
        or not coverage_provided
        or not target_object_ready
        or not target_hook_ready
        or not target_package_ready
    )
    if args.platform == "windows":
        xref_command = [
            "python3",
            "scripts/summarize-client-loader-xrefs.py",
            "<target-binary>",
            "--loader-log",
            post_canary_log,
            "--loader",
            "win-client",
        ]
        default_exe_substring = "DuneSandbox"
    else:
        xref_command = [
            "python3",
            "scripts/summarize-linux-loader-xrefs.py",
            "<target-binary>",
            "--loader-log",
            post_canary_log,
        ]
        default_exe_substring = "DuneSandbox" if args.platform == "linux-client" else "DuneSandboxServer"
    for pid in args.pid:
        xref_command.extend(["--pid", pid])
    exe_substrings = args.exe_substring or [default_exe_substring]
    for substring in exe_substrings:
        xref_command.extend(["--exe-substring", substring])
    xref_command.extend(["--category", "ue", "--format", "json"])
    promote_command = [
        "python3",
        "scripts/promote-ue-anchor-xref-candidates.py",
        xref_json,
        "--require-target-source",
        "--format",
        "json",
    ]
    prepare_command = [
        "python3",
        "scripts/prepare-ue-anchor-canary.py",
        "--platform",
        args.platform,
        "--binary",
        "<target-binary>",
        "--loader-log",
        post_canary_log,
        "--xref-json",
        candidates_json,
        "--output-dir",
        recovered_dir,
        "--skip-readiness",
    ]
    recovery_loaders = args.loader or [post_canary_loader_name(args.platform)]
    for loader in recovery_loaders:
        prepare_command.extend(["--loader", loader])
    for pid in args.pid:
        prepare_command.extend(["--pid", pid])
    for substring in args.exe_substring:
        prepare_command.extend(["--exe-substring", substring])
    verify_command = [
        f"{recovered_dir}/post-canary-verify.sh",
        post_canary_log,
    ]
    return {
        "schemaVersion": "dune-ue4ss-target-image-anchor-recovery/v1",
        "recommended": bool(needs_recovery),
        "reasons": reasons,
        "missingTargetObjectGroups": list(target_object_missing),
        "missingTargetHookGroups": list(target_hook_missing),
        "missingTargetPackageGroups": list(target_package_missing),
        "preparedAnchorCoverage": {
            "provided": coverage_provided,
            "readyForTargetObjectDiscovery": target_object_ready,
            "readyForTargetHookPlanning": target_hook_ready,
            "readyForTargetPackageLoading": target_package_ready,
            "missingRequiredGroups": list(anchor_coverage.get("missingRequiredGroups", []) or []),
        },
        "xrefJson": xref_json,
        "candidateJson": candidates_json,
        "recoveredOutputDir": recovered_dir,
        "xrefCommand": xref_command,
        "xrefCommandText": command_text(xref_command) + f" > {xref_json}",
        "promoteCommand": promote_command,
        "promoteCommandText": command_text(promote_command) + f" > {candidates_json}",
        "prepareRecoveredCanaryCommand": prepare_command,
        "prepareRecoveredCanaryCommandText": command_text(prepare_command),
        "postRecoveryVerifyCommand": verify_command,
        "postRecoveryVerifyCommandText": command_text(verify_command),
    }


def build_canary_contract(args, report, stage, env_items, blockers, root_candidate_input=None):
    prefix = env_prefix(args.platform)
    root_candidate_input = root_candidate_input or root_recovery_candidate_input(args)
    excluded_carry_forward_names = manual_runtime_root_candidate_names(root_candidate_input)
    runtime_carry_forward = runtime_candidate_carry_forward_summary(
        report.get("runtimeDiscovery") or report.get("ueRuntimeDiscovery") or {},
        args.platform,
        suppressed=bool(args.suppress_runtime_candidate_carry_forward),
        suppression_reason=args.suppress_runtime_candidate_carry_forward_reason,
        excluded_names=excluded_carry_forward_names,
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
    prepare_anchor_canary_command = [
        "python3",
        "scripts/prepare-ue-anchor-canary.py",
        "--platform",
        args.platform,
        "--binary",
        "<target-binary>",
        "--loader-log",
        post_canary_log,
        "--output-dir",
        "build/ue4ss-anchor-canary",
        "--skip-readiness",
    ]
    prep_loaders = args.loader or [post_canary_loader_name(args.platform)]
    for loader in prep_loaders:
        prepare_anchor_canary_command.extend(["--loader", loader])
    for pid in args.pid:
        prepare_anchor_canary_command.extend(["--pid", pid])
    for substring in args.exe_substring:
        prepare_anchor_canary_command.extend(["--exe-substring", substring])
    post_canary_verify_command = [
        "build/ue4ss-anchor-canary/post-canary-verify.sh",
        post_canary_log,
    ]
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
        required_validation.append("target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchor")
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
    call_function_hook_relevant = (
        stage in ("live-hook", "lua-dispatch", "complete")
        or ready.get("ueCallFunctionHookProbe")
        or ready.get("ueCallFunctionLiveHook")
        or has_hook_target(args, "CallFunction")
    )
    if runtime_validation_relevant and call_function_hook_relevant and not runtime_ready(report, "ueCallFunctionHookRuntimeTarget", "ue-call-function-hook-runtime-target"):
        required_validation.append("non-self-test CallFunctionByNameWithArguments hook probe target")
    if runtime_validation_relevant and not runtime_ready(report, "ueCallFunctionLiveHookRuntimeTarget", "ue-call-function-live-hook-runtime-target"):
        required_validation.append("non-self-test persistent CallFunctionByNameWithArguments hook target")
    if (stage in ("live-hook", "lua-dispatch", "complete") or ready.get("ueProcessEventLiveHook")) and not ready_or_gate(
        report,
        "ueProcessEventActiveValidation",
        "ue-process-event-active-validation",
    ):
        required_validation.append("explicitly allowed active ProcessEvent validation call through patched target entry, live hook, and original trampoline")
    if (stage in ("live-hook", "lua-dispatch", "complete") or ready.get("ueCallFunctionLiveHook")) and not ready_or_gate(
        report,
        "ueCallFunctionActiveValidation",
        "ue-call-function-active-validation",
    ):
        required_validation.append("explicitly allowed active CallFunctionByNameWithArguments validation call through patched target entry, live hook, and original trampoline")
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
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "luaLoadClassPackageNativeInvocation",
        "lua-load-class-package-native-invocation",
    ):
        required_validation.append(
            "guarded InvokeLoadClassPackageNative(path,{Invoke=true}) row with nativeInvoked=true, nativeCallable=true, targetImage=true, classRootReady=true, and nativeCallPlanAccepted=true"
        )
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
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "luaLoadAssetPackageNativeInvocation",
        "lua-load-asset-package-native-invocation",
    ):
        required_validation.append("guarded InvokeLoadAssetPackageNative(path,{Invoke=true}) row with nativeInvoked=true, nativeCallable=true, targetImage=true, and nativeReturnValidated=true")
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
            "targetCoverageFieldsPresent": bool(anchor_coverage.get("targetCoverageFieldsPresent")),
            "readyForTargetObjectDiscovery": bool(anchor_coverage.get("readyForTargetObjectDiscovery")),
            "readyForTargetHookPlanning": bool(anchor_coverage.get("readyForTargetHookPlanning")),
            "readyForTargetPackageLoading": bool(anchor_coverage.get("readyForTargetPackageLoading")),
            "missingRequiredGroups": list(anchor_coverage.get("missingRequiredGroups", []) or []),
        },
        "targetImageAnchorRecovery": target_image_anchor_recovery_commands(
            args,
            anchor_coverage,
            target_object_missing,
            target_hook_missing,
            target_package_missing,
        ),
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
            "prepareAnchorCanaryCommand": prepare_anchor_canary_command,
            "prepareAnchorCanaryCommandText": command_text(prepare_anchor_canary_command),
            "postCanaryVerifyCommand": post_canary_verify_command,
            "postCanaryVerifyCommandText": command_text(post_canary_verify_command),
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
                "evidenceInventoryJson": "ue4ss-evidence-inventory.json",
                "evidenceInventory": "ue4ss-evidence-inventory.md",
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
            "activeValidation": ready_or_gate(
                report,
                "ueProcessEventActiveValidation",
                "ue-process-event-active-validation",
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
            "activeValidation": ready_or_gate(
                report,
                "ueCallFunctionActiveValidation",
                "ue-call-function-active-validation",
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
    stage = choose_stage(report, args)
    ready = report.get("ready", {})
    lines = []
    notes = []
    blockers = []
    root_candidate_input = root_recovery_candidate_input(args)
    plan_export = plan_anchor_export(anchor_export)
    unsafe_anchor_names = unsafe_anchor_export_names(anchor_export)
    if unsafe_anchor_names:
        notes.append(
            "Suppressed mapped-only UE anchor export entries from the automatic plan because they do not prove runtime root validity: "
            + ", ".join(unsafe_anchor_names)
            + "."
        )

    for line in anchor_lines(plan_export):
        name, _, value = line.partition("=")
        if root_candidate_input["provided"] and name == f"{prefix}_UE_ANCHORS":
            notes.append(
                "Suppressed explicit UE anchors exported from the previous runtime log because root-recovery candidate globals are restart-safe image-offset hypotheses."
            )
            continue
        set_env(lines, name, unquote_shell_value(value), "carry forward explicit UE anchor input")
    set_hook_target_env(
        lines,
        args,
        "ProcessEvent",
        "carry forward selected restart-safe ProcessEvent target for hook probe and persistent hook canaries",
    )
    set_hook_target_env(
        lines,
        args,
        "CallFunction",
        "carry forward selected restart-safe CallFunctionByNameWithArguments target for hook probe and persistent hook canaries",
    )
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
            add_blocker(
                blockers,
                notes,
                "empty-root-recovery-candidate-input",
                "object-discovery",
                "Root-recovery candidate input was provided, but it emitted no candidate globals. Re-export from current qword-filtered names/object/world root evidence before relying on the next canary to recover UE roots.",
            )

    if stage in ("object-discovery", "reflection", "hook-probe", "live-hook", "lua-dispatch", "complete"):
        target_filter = effective_target_filter(args)
        if args.platform == "server":
            set_env_if_absent(
                lines,
                f"{prefix}_TARGET",
                target_filter,
                "run expensive server probes only inside the configured target executable, not preload helper processes",
            )
        set_env_if_absent(lines, f"{prefix}_SCAN_ENABLED", "true", "collect target-image scan start/finish and anchor evidence")
        set_env_if_absent(lines, f"{prefix}_SCAN_PRESETS", "core,ue", "scan core Unreal target-image anchor strings")
        set_env_if_absent(
            lines,
            scan_path_filter_env_name(prefix),
            target_filter,
            "restrict read-only memory scan to configured target-image mappings",
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
        if runtime_policy.get("promoteAmbiguousRoots"):
            set_env(
                lines,
                f"{prefix}_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS",
                "true",
                "promote bounded ambiguous runtime root candidates for same-run FName/object-array validation",
            )
        if runtime_policy.get("delayedProbeSeconds"):
            set_env(
                lines,
                f"{prefix}_UE_DELAYED_PROBE_SECONDS",
                runtime_policy["delayedProbeSeconds"],
                "rerun UE runtime root validation after process startup instead of only at constructor snapshot",
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
            suppressed=bool(args.suppress_runtime_candidate_carry_forward),
            suppression_reason=args.suppress_runtime_candidate_carry_forward_reason,
            excluded_names=manual_runtime_root_candidate_names(root_candidate_input),
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
            if carry_forward.get("excludedNames"):
                notes.append(
                    "Skipped ambiguous carry-forward candidates for reviewed manual runtime roots: "
                    + ", ".join(carry_forward["excludedNames"])
                    + "."
                )
        elif carry_forward.get("excludedNames"):
            notes.append(
                "Skipped ambiguous carry-forward candidates for reviewed manual runtime roots: "
                + ", ".join(carry_forward["excludedNames"])
                + "."
            )
        elif carry_forward.get("suppressed") and carry_forward.get("suppressedEntryCount", 0):
            notes.append(
                "Suppressed runtime root candidate carry-forward entries: "
                + "; ".join(carry_forward.get("suppressedEntries", []))
                + "."
            )
            if carry_forward.get("suppressionReason"):
                notes.append("Runtime root carry-forward suppression reason: " + carry_forward["suppressionReason"])
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
                "16384",
                "wide read-only GUObjectArray walk after runtime roots validated but UFunction/reflection evidence is missing",
            )
            set_env(
                lines,
                f"{prefix}_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE",
                "true",
                "scan UClass entries reached from GUObjectArray for functionLink/property surfaces",
            )
            set_env(
                lines,
                f"{prefix}_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX",
                "256",
                "bound class reflection fanout during wide object walk",
            )
            set_env(lines, f"{prefix}_UE_REFLECTION_PROBE", "true", "read-only UClass slot probe after validated runtime roots")
            set_env(lines, f"{prefix}_UE_REFLECTION_FIELD_WALK", "true", "bounded UField chain walk after validated runtime roots")
            set_env(lines, f"{prefix}_UE_REFLECTION_PROPERTY_PROBE", "true", "bounded FProperty descriptor probe after validated runtime roots")
            set_env(lines, f"{prefix}_UE_REFLECTION_VALUE_PROBE", "true", "bounded read-only reflected value probe after validated runtime roots")
            if function_registry_runtime_ready(report):
                set_env(lines, f"{prefix}_LUA_REFLECTION_SELF_TEST", "true", "prove Lua reflection API against loader/live descriptors")
            else:
                set_env(lines, f"{prefix}_LUA_REFLECTION_SELF_TEST", "false", "defer Lua reflection self-test until a Lua runtime library is packaged into the target")
            notes.append(
                "Runtime roots are validated but UFunction/reflection runtime evidence is still missing; next canary should run a wide read-only GUObjectArray walk plus class reflection to promote live UFunction identities."
            )
        if (
            ready.get("ueProcessEventLiveHook")
            and runtime_ready(report, "ueProcessEventLiveHookRuntimeTarget", "ue-process-event-live-hook-runtime-target")
            and not ready_or_gate(report, "ueProcessEventActiveValidation", "ue-process-event-active-validation")
        ):
            set_env_override(
                lines,
                f"{prefix}_UE_OBJECT_ARRAY_MAX_OBJECTS",
                "32768",
                "widen read-only GUObjectArray walk to find safer CDO/instance ProcessEvent active-validation candidates",
            )
            set_env_override(
                lines,
                f"{prefix}_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE",
                "true",
                "scan UClass entries reached from GUObjectArray while looking for safe ProcessEvent validation candidates",
            )
            set_env_override(
                lines,
                f"{prefix}_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX",
                "512",
                "increase class reflection fanout for safer active-validation candidate discovery",
            )
            set_env_override(lines, f"{prefix}_UE_REFLECTION_PROBE", "true", "keep reflection descriptors fresh for active-validation candidate discovery")
            set_env_override(lines, f"{prefix}_UE_REFLECTION_FIELD_WALK", "true", "walk UField chains for active-validation candidate discovery")
            set_env_override(lines, f"{prefix}_UE_REFLECTION_PROPERTY_PROBE", "true", "collect FProperty descriptors for active-validation params")
            set_env_override(lines, f"{prefix}_UE_REFLECTION_VALUE_PROBE", "true", "read reflected values only for bounded active-validation candidate discovery")
            notes.append(
                "ProcessEvent live hook is proven but active validation lacks a safe runtime object/function candidate; widen read-only object/reflection discovery and keep native active validation disabled until a reviewed candidate is exported."
            )
        if ready.get("runtimeRootValidation") and (
            not ready.get("targetObjectDiscovery")
            or not ready.get("targetHooks")
            or ue_group_target_present_count(report, "dispatch") == 0
        ):
            set_env(
                lines,
                f"{prefix}_UE_PROCESS_EVENT_VTABLE_SCAN",
                "true",
                "scan runtime UObject vtables for target-image ProcessEvent dispatch candidates after roots validate",
            )
            set_env(
                lines,
                f"{prefix}_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS",
                "128",
                "include enough UObject vtable slots to cover stripped UE4 ProcessEvent candidates",
            )
            set_env(
                lines,
                f"{prefix}_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS",
                "512",
                "bound read-only ProcessEvent vtable candidate scan across runtime UObjectArray entries",
            )
            notes.append(
                "Runtime roots are validated but target dispatch anchors are still missing; next canary should scan runtime UObject vtables for ProcessEvent candidates."
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
            explicit_process_event_target = has_hook_target(args, "ProcessEvent")
            explicit_call_function_target = has_hook_target(args, "CallFunction")
            process_event_only_probe = explicit_process_event_target and not explicit_call_function_target
            set_env(lines, f"{prefix}_HOOK_SELF_TEST", "true", "prove guarded native hook dispatch on loader-owned target")
            if explicit_process_event_target or not explicit_call_function_target:
                set_env(lines, f"{prefix}_UE_PROCESS_EVENT_HOOK_PROBE", "true", "guarded install/restore probe on resolved ProcessEvent")
                set_env(lines, f"{prefix}_UE_PROCESS_EVENT_HOOK_INSTALL", "true", "temporarily install and restore hook during guarded hook probe")
            else:
                notes.append("ProcessEvent hook probe target is not explicit in this plan; keeping ProcessEvent hook install disabled.")
            if explicit_call_function_target or not process_event_only_probe:
                set_env(lines, f"{prefix}_UE_CALL_FUNCTION_HOOK_PROBE", "true", "guarded install/restore probe on resolved CallFunctionByNameWithArguments")
                set_env(lines, f"{prefix}_UE_CALL_FUNCTION_HOOK_INSTALL", "true", "temporarily install and restore hook during guarded hook probe")
            else:
                notes.append("CallFunctionByNameWithArguments hook probe target is not explicit in this plan; keeping CallFunction hook install disabled.")
        else:
            notes.append("ProcessEvent hook probe is next, but --max-stage read-only suppresses code-patching probes.")

    if stage in ("live-hook", "lua-dispatch", "complete"):
        if stage_allowed(args, "live-hook"):
            explicit_process_event_target = has_hook_target(args, "ProcessEvent")
            explicit_call_function_target = has_hook_target(args, "CallFunction")
            if explicit_process_event_target or not explicit_call_function_target:
                set_env(lines, f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK", "true", "install persistent ProcessEvent hook scaffold")
                set_env(lines, f"{prefix}_UE_PROCESS_EVENT_DISPATCH_SELF_TEST", "true", "arm native pre/original/post dispatch")
                set_env(lines, f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS", "true", "collect bounded live ProcessEvent context and param samples")
                set_env(
                    lines,
                    f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT",
                    str(args.live_call_log_limit),
                    "bound live ProcessEvent context sample count",
                )
            else:
                notes.append("ProcessEvent live hook target is not explicit in this plan; keeping ProcessEvent live hook disabled.")
            if explicit_call_function_target or ready.get("ueCallFunctionLiveHook"):
                set_env(lines, f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK", "true", "install persistent CallFunctionByNameWithArguments hook scaffold")
                set_env(lines, f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS", "true", "collect bounded live CallFunctionByNameWithArguments call samples")
                set_env(
                    lines,
                    f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT",
                    str(args.live_call_log_limit),
                    "bound live CallFunctionByNameWithArguments sample count",
                )
            else:
                notes.append("CallFunctionByNameWithArguments live hook target is not explicit in this plan; keeping CallFunction live hook disabled.")
            if explicit_call_function_target or not explicit_process_event_target:
                set_active_validation_env(lines, notes, args, report)
            else:
                notes.append("Active ProcessEvent validation inputs are not part of this passive live-hook plan; keeping native active validation disabled.")
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
            set_package_promotion_env(lines, notes, args)
            set_load_asset_package_native_invocation_env(lines, notes, args, report)
        else:
            notes.append("Lua dispatch is next, but --max-stage blocks Lua/live mod dispatch emission.")

    if stage == "complete":
        notes.append("All readiness gates are already satisfied by the provided evidence.")
    if root_candidate_input["provided"] and root_candidate_input["emittedCount"]:
        promoted_manual_roots = has_promoted_manual_runtime_roots(root_candidate_input, report)
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
        if missing_object_candidate_groups and promoted_manual_roots:
            notes.append(
                "Skipping root-recovery world-candidate blocker because reviewed manual RuntimeFNamePool and RuntimeGUObjectArray roots are supplied and current readiness already validates runtime roots; object-discovery coverage must still prove names/objects/world from live target evidence."
            )
        elif missing_object_candidate_groups:
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
            "Package-backed LoadAsset is not target-image ready; collect StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or ResolveName evidence from the game executable or module before treating luaLoadAssetPackage as complete.",
        )
    if (ready.get("luaLoadAssetPackageNativeExecutor") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "luaLoadAssetPackageNativeInvocation",
        "lua-load-asset-package-native-invocation",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-load-asset-package-native-invocation",
            "lua-dispatch",
            "Package-backed LoadAsset native invocation evidence is missing; run guarded InvokeLoadAssetPackageNative(path,{Invoke=true}) with reviewed ABI/TCHAR evidence, a target-image package-loading executor, and nativeReturnValidated=true before claiming LoadAsset parity.",
        )
    if (ready.get("luaLoadClassPackageAbiState") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "luaLoadClassPackageCallFrameVerification",
        "lua-load-class-package-call-frame-verification",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-load-class-package-call-frame-verification",
            "lua-dispatch",
            "Package-backed LoadClass call-frame verification is missing; run GetLoadClassPackageCallFrameVerificationState(path) against a target-image StaticLoadClass anchor and prove abiVerified=true, classRootReady=true, and callFrameReady=true.",
        )
    if (ready.get("luaLoadClassPackageCallFrameVerification") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "luaLoadClassPackageNativeExecutor",
        "lua-load-class-package-native-executor",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-load-class-package-native-executor",
            "lua-dispatch",
            "Package-backed LoadClass native executor evidence is missing; collect NativeExecutorReady, ExecutorPreflightPassed, and FinalNativeCallEligible state for the target-image StaticLoadClass path before native invocation.",
        )
    if (ready.get("luaLoadClassPackageNativeExecutor") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "luaLoadClassPackageNativeInvocation",
        "lua-load-class-package-native-invocation",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-load-class-package-native-invocation",
            "lua-dispatch",
            "Package-backed LoadClass native invocation evidence is missing; run guarded InvokeLoadClassPackageNative(path,{Invoke=true}) with a target-image StaticLoadClass anchor, classRootReady=true, nativeCallPlanAccepted=true, and nativeInvoked=true before claiming LoadClass parity.",
        )
    if ready.get("reflection") and not proven_reflection_surface_ready(report):
        add_blocker(
            blockers,
            notes,
            "unproven-reflection-anchors",
            "reflection",
            "Readiness claims reflection, but the report does not show at least two proven reflection anchors; keep reflection work read-only until anchor provenance is present.",
        )
    explicit_process_event_runtime_target = has_hook_target(args, "ProcessEvent") and runtime_ready(
        report,
        "ueProcessEventHookRuntimeTarget",
        "ue-process-event-hook-runtime-target",
    )
    if (ready.get("reflection") or ready.get("hookDispatch")) and not proven_dispatch_anchor_ready(report) and not explicit_process_event_runtime_target:
        add_blocker(
            blockers,
            notes,
            "unproven-dispatch-anchor",
            "hook-probe",
            "Readiness claims hook-capable stages, but the report does not show a proven dispatch anchor; do not emit ProcessEvent hook or Lua dispatch env.",
        )
    if (ready.get("reflection") or ready.get("hookDispatch")) and not proven_target_dispatch_anchor_ready(report) and not explicit_process_event_runtime_target:
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
    if (ready.get("ueProcessEventLiveHook") or ready.get("hooks") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "ueProcessEventActiveValidation",
        "ue-process-event-active-validation",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-process-event-active-validation",
            "live-hook",
            "Active ProcessEvent validation evidence is missing; run the persistent hook with explicit runtime object/function inputs and native invocation explicitly allowed before relying on passive live-call timing.",
        )
    if (ready.get("ueCallFunctionLiveHook") or ready.get("hooks") or ready.get("luaDispatch")) and not ready_or_gate(
        report,
        "ueCallFunctionActiveValidation",
        "ue-call-function-active-validation",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-call-function-active-validation",
            "live-hook",
            "Active CallFunctionByNameWithArguments validation evidence is missing; run the persistent hook with explicit runtime object/command inputs and native invocation explicitly allowed before claiming live CallFunction dispatch.",
        )
    if (stage in ("lua-dispatch", "complete") or ready.get("luaDispatch")) and not ready_or_gate(
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
    if ready_or_gate(report, "luaProcessEventNativeInvokeNonSelfTestGate", "lua-process-event-native-invoke-non-self-test-gate") and not ready_or_gate(
        report,
        "luaProcessEventNativeInvokeNonSelfTestInvoked",
        "lua-process-event-native-invoke-non-self-test-invoked",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-process-event-native-non-self-test-invocation",
            "lua-dispatch",
            "Lua ProcessEvent native bridge only proved preflight/closed-gate behavior; explicitly enable and invoke a descriptor-backed non-self-test ProcessEvent target before claiming Lua dispatch parity.",
        )
    if ready_or_gate(report, "luaCallFunctionNativeInvokeNonSelfTestGate", "lua-call-function-native-invoke-non-self-test-gate") and not ready_or_gate(
        report,
        "luaCallFunctionNativeInvokeNonSelfTestInvoked",
        "lua-call-function-native-invoke-non-self-test-invoked",
    ):
        add_blocker(
            blockers,
            notes,
            "missing-call-function-native-non-self-test-invocation",
            "lua-dispatch",
            "Lua CallFunction native bridge only proved preflight/closed-gate behavior; explicitly enable and invoke a non-self-test CallFunction target before claiming Lua dispatch parity.",
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
            "Prepared anchor coverage is missing target-image object-discovery groups; stay read-only until target coverage is complete"
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
            "Prepared anchor coverage lacks target-image ProcessEvent-level dispatch evidence; do not emit hook/live Lua escalation yet.",
        )

    deduped = []
    seen = set()
    for item in lines:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        deduped.append(item)
    selected_stage_blockers = blockers_for_selected_stage(blockers, stage)
    return {
        "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
        "platform": args.platform,
        "loader": loader_name(args.platform),
        "selectedStage": stage,
        "maxStage": args.max_stage,
        "env": deduped,
        "notes": notes,
        "blockers": blockers,
        "selectedStageBlockers": selected_stage_blockers,
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
    selected_blockers = plan.get("selectedStageBlockers") or []
    if selected_blockers:
        lines.append("")
        lines.append("## Selected Stage Blockers")
        lines.append("")
        for blocker in selected_blockers:
            lines.append(f"- `{blocker['code']}` blocks `{blocker['stage']}`: {blocker['message']}")
    if plan.get("blockers"):
        lines.append("")
        lines.append("## All Blockers")
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
        target_recovery = contract.get("targetImageAnchorRecovery", {})
        if target_recovery and target_recovery.get("recommended"):
            lines.append("")
            lines.append("### Target-Image Anchor Recovery")
            lines.append("")
            lines.append(
                "- Recovery reasons: `"
                + (", ".join(target_recovery.get("reasons", []) or []) or "none")
                + "`"
            )
            lines.append(
                "- Missing target groups: `object="
                + (", ".join(target_recovery.get("missingTargetObjectGroups", []) or []) or "none")
                + "; hook="
                + (", ".join(target_recovery.get("missingTargetHookGroups", []) or []) or "none")
                + "; package="
                + (", ".join(target_recovery.get("missingTargetPackageGroups", []) or []) or "none")
                + "`"
            )
            lines.append("- Xref command: `" + target_recovery.get("xrefCommandText", "") + "`")
            lines.append("- Promote command: `" + target_recovery.get("promoteCommandText", "") + "`")
            lines.append(
                "- Prepare recovered canary: `"
                + target_recovery.get("prepareRecoveredCanaryCommandText", "")
                + "`"
            )
            lines.append(
                "- Post-recovery verify: `"
                + target_recovery.get("postRecoveryVerifyCommandText", "")
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
    parser.add_argument(
        "--suppress-runtime-candidate-carry-forward",
        action="store_true",
        help="do not carry forward previous ambiguous RuntimeFNamePool/RuntimeGUObjectArray candidate globals",
    )
    parser.add_argument(
        "--suppress-runtime-candidate-carry-forward-reason",
        default="",
        help="single-line reason recorded when suppressing previous runtime root candidate globals",
    )
    parser.add_argument(
        "--hook-targets-json",
        type=Path,
        action="append",
        default=[],
        help="JSON containing selected restart-safe ProcessEvent/CallFunction hook targets; accepts vtable-ranker hookProbeShortlist rows",
    )
    parser.add_argument(
        "--process-event-image-offset",
        default="",
        help="selected Linux ELF image offset for UObject::ProcessEvent; emitted as hook, generic, and live-hook target env",
    )
    parser.add_argument(
        "--process-event-rva",
        default="",
        help="selected Windows/Proton PE RVA for UObject::ProcessEvent; emitted as hook, generic, and live-hook target env",
    )
    parser.add_argument(
        "--call-function-image-offset",
        default="",
        help="selected Linux ELF image offset for UObject::CallFunctionByNameWithArguments; emitted as hook, generic, and live-hook target env",
    )
    parser.add_argument(
        "--call-function-rva",
        default="",
        help="selected Windows/Proton PE RVA for UObject::CallFunctionByNameWithArguments; emitted as hook, generic, and live-hook target env",
    )
    parser.add_argument(
        "--allow-active-native-call",
        action="store_true",
        help="emit ALLOW_NATIVE_CALL=true for active ProcessEvent/CallFunction validation; requires reviewed runtime inputs",
    )
    parser.add_argument(
        "--active-validation-through-target",
        action="store_true",
        help="emit THROUGH_TARGET=true so active validation calls the patched target entrypoint instead of the replacement shim",
    )
    parser.add_argument(
        "--suppress-process-event-original",
        action="store_true",
        help="emit PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=true so synthetic ProcessEvent validation proves hook dispatch without forwarding to the native original",
    )
    parser.add_argument(
        "--allow-load-asset-package-native-call",
        action="store_true",
        help="emit ALLOW_LOAD_ASSET_PACKAGE_INVOKE=true for guarded package LoadAsset native invocation; requires reviewed package path and ABI/TCHAR evidence",
    )
    parser.add_argument(
        "--package-promotion-json",
        type=Path,
        action="append",
        default=[],
        help="reviewed JSON from export-ue4ss-package-promotion-env.py to feed package ABI/native promotion env into the next canary",
    )
    parser.add_argument(
        "--package-promotion-dir",
        type=Path,
        action="append",
        default=[],
        help="directory containing per-family promotion-env.json files from ue4ss-package-runtime-trace.sh status",
    )
    parser.add_argument(
        "--package-promotion-summary-json",
        type=Path,
        action="append",
        default=[],
        help="summary JSON from summarize-ue4ss-package-promotion-dir.py; only ready manifest paths are applied",
    )
    parser.add_argument(
        "--confirm-load-asset-package-native-call",
        action="store_true",
        help="emit CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL=true without implying the broader allow flag; mainly for staged adapter diagnostics",
    )
    parser.add_argument(
        "--load-asset-package-path",
        default="/Script/DuneProbe.MissingPackageAsset",
        help="package/object path passed to GetLoadAssetPackageNativeExecutorState and InvokeLoadAssetPackageNative",
    )
    parser.add_argument(
        "--load-asset-package-abi-evidence",
        default="",
        help="reviewed ABI evidence string emitted as LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
    )
    parser.add_argument(
        "--load-asset-package-tchar-unit-bytes",
        default="",
        help="observed TCHAR unit byte width emitted as TCHAR_UNIT_BYTES",
    )
    parser.add_argument(
        "--load-asset-package-tchar-evidence",
        default="",
        help="reviewed TCHAR layout evidence string emitted as TCHAR_EVIDENCE",
    )
    parser.add_argument(
        "--load-asset-package-native-script",
        action="store_true",
        help="emit a Lua self-test script that calls InvokeLoadAssetPackageNative(path,{Invoke=true})",
    )
    parser.add_argument(
        "--active-validation-object-address",
        default="",
        help="runtime UObject address used by active ProcessEvent and CallFunction validation",
    )
    parser.add_argument(
        "--use-active-validation-hints",
        action="store_true",
        help="promote reviewed canaryHints.activeValidationCandidates into active validation env when explicit addresses are omitted",
    )
    parser.add_argument(
        "--active-validation-candidates-json",
        type=Path,
        action="append",
        default=[],
        help="reviewed JSON from export-process-event-active-validation-candidates.py to merge into canaryHints.activeValidationCandidates",
    )
    parser.add_argument(
        "--process-event-active-function-address",
        default="",
        help="runtime UFunction address used by active ProcessEvent validation",
    )
    parser.add_argument(
        "--process-event-active-params-address",
        default="",
        help="optional descriptor-backed params buffer address used by active ProcessEvent validation",
    )
    parser.add_argument(
        "--call-function-active-command",
        default="",
        help="command string used by active CallFunctionByNameWithArguments validation",
    )
    parser.add_argument(
        "--call-function-active-command-address",
        default="",
        help="runtime command string address used by active CallFunctionByNameWithArguments validation",
    )
    parser.add_argument(
        "--call-function-active-output-address",
        default="",
        help="optional output device address used by active CallFunctionByNameWithArguments validation",
    )
    parser.add_argument(
        "--call-function-active-executor-address",
        default="",
        help="optional executor address used by active CallFunctionByNameWithArguments validation",
    )
    parser.add_argument(
        "--call-function-active-force-call",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="forceCall flag for active CallFunctionByNameWithArguments validation",
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
        validate_package_promotion_args(args)
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
