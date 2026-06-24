#!/usr/bin/env python3
import argparse
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path


PLATFORMS = ("server", "linux-client", "windows")
CORE_ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
REQUIRED_DISCOVERY_GROUPS = ("names", "objects", "world", "dispatch")


def import_script(script_name, module_name):
    script = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def platform_config(platform):
    if platform == "windows":
        return {
            "manifestScript": "export-client-pe-signature-manifest.py",
            "manifestModule": "export_client_pe_signature_manifest",
            "loader": "win-client",
            "anchorPlatform": "windows",
            "manifestName": "client-pe-signature-manifest.json",
            "anchorSignatureName": "client-anchor-signatures.txt",
            "anchorEnvName": "ue-anchors.env",
            "readinessLogArg": "--client-log",
        }
    if platform == "linux-client":
        return {
            "manifestScript": "export-elf-signature-manifest.py",
            "manifestModule": "export_elf_signature_manifest",
            "targetLoader": "linux-client",
            "loader": "linux-client",
            "anchorPlatform": "linux",
            "manifestName": "client-elf-signature-manifest.json",
            "anchorSignatureName": "client-anchor-signatures.txt",
            "anchorEnvName": "ue-anchors.env",
            "readinessLogArg": "--client-log",
        }
    return {
        "manifestScript": "export-elf-signature-manifest.py",
        "manifestModule": "export_elf_signature_manifest",
        "targetLoader": "server",
        "loader": "server",
        "anchorPlatform": "server",
        "manifestName": "server-elf-signature-manifest.json",
        "anchorSignatureName": "server-anchor-signatures.txt",
        "anchorEnvName": "ue-server-anchors.env",
        "readinessLogArg": "--server-log",
    }


def post_canary_loader(platform, config):
    if platform == "linux-client":
        return "client"
    return config["loader"]


def default_canary_log_path(platform):
    if platform == "server":
        return "/tmp/dune-server-probe-loader.log"
    if platform == "windows":
        return "/tmp/dune-win-client-probe-loader.log"
    return "/tmp/dune-client-probe-loader.log"


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def command_text(argv):
    return " ".join(shlex.quote(str(part)) for part in argv)


def build_manifest(args, config):
    exporter = import_script(config["manifestScript"], config["manifestModule"])
    if args.validation_json:
        validation = load_json(args.validation_json)
    else:
        categories = args.category or ["ue"]
        names = args.name or []
        if args.platform == "windows":
            validation = exporter.build_validation(
                args.binary,
                args.loader_log,
                args.xref_json,
                args.loader or [config["loader"]],
                args.pid,
                args.exe_substring,
                categories,
                names,
                args.signature_prefix,
                args.signature_suffix,
                args.scope,
                args.max_matches,
            )
        else:
            validation = exporter.build_validation(
                args.binary,
                args.loader_log,
                args.xref_json,
                args.exe_substring[0] if args.exe_substring else (
                    "DuneSandbox" if args.platform == "linux-client" else "DuneSandboxServer"
                ),
                int(args.pid[0]) if args.pid else None,
                categories,
                names,
                args.signature_prefix,
                args.signature_suffix,
                args.scope,
                args.max_matches,
            )
    entries = exporter.build_entries(validation, promotable_only=not args.include_non_promotable)
    if args.platform == "windows":
        manifest = exporter.make_manifest(
            args.binary,
            validation,
            entries,
            args.loader_log,
            args.xref_json,
            args.max_patterns_per_scan,
            args.max_env_value_chars,
        )
    else:
        manifest = exporter.make_manifest(
            args.binary,
            validation,
            entries,
            args.loader_log,
            args.xref_json,
            args.max_patterns_per_scan,
            args.max_env_value_chars,
            config["targetLoader"],
        )
    return exporter, manifest


def build_anchor_env(args, config):
    anchor_exporter = import_script("export-ue-anchor-env.py", "export_ue_anchor_env")
    return anchor_exporter, anchor_exporter.build_export(
        args.loader_log,
        args.loader or [config["loader"]],
        args.pid,
        args.exe_substring,
        args.anchor_name or list(anchor_exporter.DEFAULT_ANCHORS),
        config["anchorPlatform"],
        include_runtime_candidates=args.include_runtime_candidates,
        runtime_candidate_selectors=args.runtime_candidate,
    )


def run_readiness(args, config, validation_path, anchor_coverage_path, output_format):
    readiness = Path(__file__).resolve().parent / "ue4ss-port-readiness.py"
    command = [
        sys.executable,
        str(readiness),
        config["readinessLogArg"],
        str(args.loader_log),
        "--loader",
        config["loader"],
        "--signature-validation-json",
        str(validation_path),
        "--anchor-coverage-json",
        str(anchor_coverage_path),
        "--format",
        output_format,
    ]
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def write_post_canary_verify_script(path, platform, config):
    readiness_script = Path(__file__).resolve().parent / "ue4ss-port-readiness.py"
    log_arg = config["readinessLogArg"]
    loader = post_canary_loader(platform, config)
    default_log = default_canary_log_path(platform)
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"',
        f"readiness_script=${{DUNE_UE4SS_READINESS_SCRIPT:-{shlex.quote(str(readiness_script))}}}",
        'if [ ! -f "$readiness_script" ]; then',
        '  readiness_script="scripts/ue4ss-port-readiness.py"',
        "fi",
        f"gaps_script=${{DUNE_UE4SS_GAPS_SCRIPT:-{shlex.quote(str(Path(__file__).resolve().parent / 'summarize-ue4ss-port-gaps.py'))}}}",
        'if [ ! -f "$gaps_script" ]; then',
        '  gaps_script="scripts/summarize-ue4ss-port-gaps.py"',
        "fi",
        f"inventory_script=${{DUNE_UE4SS_EVIDENCE_INVENTORY_SCRIPT:-{shlex.quote(str(Path(__file__).resolve().parent / 'summarize-ue4ss-evidence-inventory.py'))}}}",
        'if [ ! -f "$inventory_script" ]; then',
        '  inventory_script="scripts/summarize-ue4ss-evidence-inventory.py"',
        "fi",
        f"loader_log=${{1:-{shlex.quote(default_log)}}}",
        '"${PYTHON:-python3}" "$readiness_script" \\',
        f"  {shlex.quote(log_arg)} \"$loader_log\" \\",
        f"  --loader {shlex.quote(loader)} \\",
        '  --signature-validation-json "$script_dir/signature-validation.json" \\',
        '  --anchor-coverage-json "$script_dir/anchor-coverage.json" \\',
        '  --format json > "$script_dir/ue4ss-readiness.json"',
        '"${PYTHON:-python3}" - "$script_dir/ue4ss-readiness.json" "$script_dir/object-discovery-coverage.json" "$script_dir/anchor-coverage.json" "$script_dir/post-canary-summary.md" <<\'PY\'',
        "import json",
        "import os",
        "import sys",
        "readiness_path, coverage_path, anchor_coverage_path, summary_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]",
        "with open(readiness_path, 'r', encoding='utf-8') as handle:",
        "    readiness = json.load(handle)",
        "coverage = readiness.get('objectDiscoveryCoverage')",
        "if not isinstance(coverage, dict):",
        "    raise SystemExit('readiness report missing objectDiscoveryCoverage')",
        "with open(anchor_coverage_path, 'r', encoding='utf-8') as handle:",
        "    anchor_coverage = json.load(handle)",
        "with open(coverage_path, 'w', encoding='utf-8') as handle:",
        "    json.dump(coverage, handle, indent=2, sort_keys=True)",
        "    handle.write('\\n')",
        "ready = readiness.get('ready', {})",
        "gate_status = {item.get('name'): bool(item.get('passed')) for item in readiness.get('gates', []) if isinstance(item, dict)}",
        "def runtime_ready(ready_name, gate_name):",
        "    if ready_name in ready:",
        "        return bool(ready.get(ready_name))",
        "    if gate_name in gate_status:",
        "        return gate_status[gate_name]",
        "    return False",
        "strict_runtime_contract = os.getenv('DUNE_UE4SS_STRICT_RUNTIME_CONTRACT', '').lower() in ('1', 'true', 'yes', 'on')",
        "runtime_contract_key_gates = {",
        "    'targetImageProcess': 'target-image-process',",
        "    'runtimeRootDiscovery': 'ue-runtime-root-discovery',",
        "    'runtimeRootValidation': 'ue-runtime-root-validation',",
        "    'targetObjectDiscovery': 'ue-target-dispatch',",
        "    'targetHooks': 'ue-target-dispatch',",
        "    'ueProcessEventHookRuntimeTarget': 'ue-process-event-hook-runtime-target',",
        "    'ueCallFunctionHookRuntimeTarget': 'ue-call-function-hook-runtime-target',",
        "    'ueProcessEventLiveHookRuntimeTarget': 'ue-process-event-live-hook-runtime-target',",
        "    'ueCallFunctionLiveHookRuntimeTarget': 'ue-call-function-live-hook-runtime-target',",
        "    'ueProcessEventActiveValidation': 'ue-process-event-active-validation',",
        "    'ueCallFunctionActiveValidation': 'ue-call-function-active-validation',",
        "    'ueCallFunctionLiveLuaDispatch': 'ue-call-function-live-lua-dispatch',",
        "    'luaCallFunctionNativeInvoke': 'lua-call-function-native-invoke',",
        "    'luaCallFunctionNativeInvokePreflight': 'lua-call-function-native-invoke-preflight',",
        "    'luaCallFunctionNativeExecutorState': 'lua-call-function-native-executor-state',",
        "    'luaCallFunctionNativeInvokeNonSelfTestGate': 'lua-call-function-native-invoke-non-self-test-gate',",
        "    'luaCallFunctionNativeInvokeNonSelfTestInvoked': 'lua-call-function-native-invoke-non-self-test-invoked',",
        "    'luaProcessEventNativeInvoke': 'lua-process-event-native-invoke',",
        "    'luaProcessEventNativeInvokeDescriptorPreflight': 'lua-process-event-native-invoke-descriptor-preflight',",
        "    'luaProcessEventNativeExecutorState': 'lua-process-event-native-executor-state',",
        "    'luaProcessEventNativeInvokeNonSelfTestGate': 'lua-process-event-native-invoke-non-self-test-gate',",
        "    'luaProcessEventNativeInvokeNonSelfTestInvoked': 'lua-process-event-native-invoke-non-self-test-invoked',",
        "    'ueProcessEventLiveLuaDispatch': 'ue-process-event-live-lua-dispatch',",
        "    'ueProcessEventLiveFunctionPath': 'ue-process-event-live-function-path',",
        "    'ueProcessEventLiveRuntimeContext': 'ue-process-event-live-runtime-context',",
        "    'ueProcessEventLiveRegistryContext': 'ue-process-event-live-registry-context',",
        "    'ueProcessEventLiveRuntimeRegistryContext': 'ue-process-event-live-runtime-registry-context',",
        "    'ueProcessEventLiveParamValues': 'ue-process-event-live-param-values',",
        "    'ueProcessEventLiveRawParamValues': 'ue-process-event-live-raw-param-values',",
        "    'ueProcessEventLiveContainerParamValues': 'ue-process-event-live-container-param-values',",
        "    'ueProcessEventLiveArrayContainerParamValues': 'ue-process-event-live-array-container-param-values',",
        "    'ueProcessEventLiveSetContainerParamValues': 'ue-process-event-live-set-container-param-values',",
        "    'ueProcessEventLiveMapContainerParamValues': 'ue-process-event-live-map-container-param-values',",
        "    'ueProcessEventLiveSetMapContainerParamValues': 'ue-process-event-live-set-map-container-param-values',",
        "    'ueProcessEventLiveContainerDataSamples': 'ue-process-event-live-container-data-samples',",
        "    'ueProcessEventLuaContextHandles': 'ue-process-event-lua-context-handles',",
        "    'ueProcessEventLuaParamAccessors': 'ue-process-event-lua-param-accessors',",
        "    'ueProcessEventLiveClassAwareParamValues': 'ue-process-event-live-class-aware-param-values',",
        "    'ueProcessEventFunctionParamMethod': 'ue-process-event-function-param-method',",
        "    'ueProcessEventFunctionParamLookupMethod': 'ue-process-event-function-param-lookup-method',",
        "    'ueProcessEventFunctionParamIterationMethod': 'ue-process-event-function-param-iteration-method',",
        "    'ueProcessEventContainerAliasMethods': 'ue-process-event-container-alias-methods',",
        "    'ueProcessEventContainerStorageLayoutMethods': 'ue-process-event-container-storage-layout-methods',",
        "    'ueProcessEventLuaScalarParamAccessors': 'ue-process-event-lua-scalar-param-accessors',",
        "    'ueProcessEventLuaNameStringParamAccessors': 'ue-process-event-lua-name-string-param-accessors',",
        "    'ueProcessEventLuaStructParamAccessors': 'ue-process-event-lua-struct-param-accessors',",
        "    'ueProcessEventLuaEnumParamAccessors': 'ue-process-event-lua-enum-param-accessors',",
        "    'ueProcessEventLuaObjectParamAccessors': 'ue-process-event-lua-object-param-accessors',",
        "    'ueProcessEventLuaBoolParamAccessors': 'ue-process-event-lua-bool-param-accessors',",
        "    'ueProcessEventLuaHookRouting': 'ue-process-event-lua-hook-routing',",
        "    'ueProcessEventLuaHookAliasRouting': 'ue-process-event-lua-hook-alias-routing',",
        "    'luaObjectRegistryRuntime': 'lua-object-registry-runtime',",
        "    'luaFunctionRegistryRuntime': 'lua-function-registry-runtime',",
        "    'luaDecodedObjectAliasesRuntime': 'lua-decoded-object-aliases-runtime',",
        "    'objectDiscoveryCoverage': '',",
        "    'findObjectSemantics': '',",
        "    'ueObjectArrayShape': 'ue-object-array-shape',",
        "    'ueObjectArrayRegistryRuntime': 'ue-object-array-registry-runtime',",
        "    'ueObjectNativeIdentities': 'ue-object-native-identities',",
        "    'ueObjectInternalFlags': 'ue-object-internal-flags',",
        "    'ueFNameDecoder': 'ue-fname-decoder',",
        "    'luaObjectOuterChainIdentities': 'lua-object-outer-chain-identities',",
        "    'luaObjectApi': 'lua-object-api',",
        "    'luaFunctionIterationRuntime': 'lua-function-iteration-runtime',",
        "    'luaStaticConstructObjectNativeExecutorState': 'lua-static-construct-object-native-executor-state',",
        "    'luaStaticConstructObjectNativeExecutorReady': 'lua-static-construct-object-native-executor-ready',",
        "    'luaStaticConstructObjectNativeInvoke': 'lua-static-construct-object-native-invoke',",
        "    'ueReflectionPropertyDescriptorsRuntime': 'ue-reflection-property-descriptors-runtime',",
        "    'ueReflectionPropertyValuesRuntime': 'ue-reflection-property-values-runtime',",
        "    'luaReflectionForEachPropertyRuntime': 'lua-reflection-for-each-property-runtime',",
        "    'luaReflectionLiveDescriptorTypedClassRuntime': 'lua-reflection-live-descriptor-typed-class-runtime',",
        "    'luaReflectionLiveDescriptorTypedValuesRuntime': 'lua-reflection-live-descriptor-typed-values-runtime',",
        "    'luaReflectionLiveDescriptorTypedSetValuesRuntime': 'lua-reflection-live-descriptor-typed-set-values-runtime',",
        "    'luaReflectionLiveDescriptorValuesRuntime': 'lua-reflection-live-descriptor-values-runtime',",
        "    'luaLoadAssetPackageCrashGuard': 'lua-load-asset-package-crash-guard',",
        "    'luaLoadAssetPackageGuardedCall': 'lua-load-asset-package-guarded-call',",
        "    'luaLoadAssetPackageReturnValidation': 'lua-load-asset-package-return-validation',",
        "    'luaLoadAssetPackageNativeCallAdapter': 'lua-load-asset-package-native-call-adapter',",
        "    'luaLoadAssetPackageInvocationDescriptor': 'lua-load-asset-package-invocation-descriptor',",
        "    'luaLoadAssetPackageNativeExecutor': 'lua-load-asset-package-native-executor',",
        "    'luaLoadAssetPackageNativeInvocation': 'lua-load-asset-package-native-invocation',",
        "    'luaLoadAssetPackage': 'lua-load-asset-package',",
        "    'luaLoadClassPackageAbiState': 'lua-load-class-package-abi-state',",
        "    'luaLoadClassPackageCallFrameVerification': 'lua-load-class-package-call-frame-verification',",
        "    'luaLoadClassPackageNativeExecutor': 'lua-load-class-package-native-executor',",
        "    'luaLoadClassPackageNativeInvocation': 'lua-load-class-package-native-invocation',",
        "}",
        "runtime_contract_status = {key: runtime_ready(key, gate) for key, gate in runtime_contract_key_gates.items()}",
        "missing_runtime_contract = [key for key, value in runtime_contract_status.items() if not value]",
        "strict_signature_anchor_status = {",
        "    'signatureManifestExact': runtime_ready('signatureManifestExact', 'signature-manifest-exact'),",
        "    'signatureManifestPromotable': runtime_ready('signatureManifestPromotable', 'signature-manifest-promotable'),",
        "    'anchorCoverageObjectDiscovery': runtime_ready('anchorCoverageObjectDiscovery', 'anchor-coverage-object-discovery'),",
        "    'anchorCoverageHookPlanning': runtime_ready('anchorCoverageHookPlanning', 'anchor-coverage-hook-planning'),",
        "    'anchorCoveragePackageLoading': runtime_ready('anchorCoveragePackageLoading', 'anchor-coverage-package-loading'),",
        "    'targetPackageLoadingSurface': runtime_ready('targetPackageLoadingSurface', 'ue-target-package-loading-surface'),",
        "}",
        "missing_signature_anchor_contract = [key for key, value in strict_signature_anchor_status.items() if not value]",
        "live_target_image_contract_groups = {",
        "    'targetImageAnchors': ('targetImageProcess', 'runtimeRootDiscovery', 'runtimeRootValidation', 'targetObjectDiscovery', 'targetHooks', 'targetPackageLoadingSurface', 'signatureManifestExact', 'signatureManifestPromotable', 'anchorCoverageObjectDiscovery', 'anchorCoverageHookPlanning', 'anchorCoveragePackageLoading'),",
        "    'runtimePackageLoading': ('luaLoadAssetPackageCrashGuard', 'luaLoadAssetPackageGuardedCall', 'luaLoadAssetPackageReturnValidation', 'luaLoadAssetPackageNativeCallAdapter', 'luaLoadAssetPackageInvocationDescriptor', 'luaLoadAssetPackageNativeExecutor', 'luaLoadAssetPackageNativeInvocation', 'luaLoadAssetPackage', 'luaLoadClassPackageAbiState', 'luaLoadClassPackageCallFrameVerification', 'luaLoadClassPackageNativeExecutor', 'luaLoadClassPackageNativeInvocation'),",
        "    'runtimeObjectRegistry': ('objectDiscoveryCoverage', 'findObjectSemantics', 'luaObjectRegistryRuntime', 'luaFunctionRegistryRuntime', 'luaDecodedObjectAliasesRuntime', 'ueObjectArrayShape', 'ueObjectArrayRegistryRuntime', 'ueObjectNativeIdentities', 'ueObjectInternalFlags', 'ueFNameDecoder', 'luaObjectOuterChainIdentities', 'luaObjectApi', 'luaFunctionIterationRuntime', 'luaStaticConstructObjectNativeExecutorState', 'luaStaticConstructObjectNativeExecutorReady', 'luaStaticConstructObjectNativeInvoke'),",
        "    'runtimeReflection': ('ueReflectionPropertyDescriptorsRuntime', 'ueReflectionPropertyValuesRuntime', 'luaReflectionForEachPropertyRuntime', 'luaReflectionLiveDescriptorTypedClassRuntime', 'luaReflectionLiveDescriptorTypedValuesRuntime', 'luaReflectionLiveDescriptorTypedSetValuesRuntime', 'luaReflectionLiveDescriptorValuesRuntime'),",
        "    'runtimeProcessEventDispatch': ('ueProcessEventHookRuntimeTarget', 'ueProcessEventLiveHookRuntimeTarget', 'ueProcessEventActiveValidation', 'ueProcessEventLiveLuaDispatch', 'ueProcessEventLiveFunctionPath', 'ueProcessEventLiveRuntimeContext', 'ueProcessEventLiveRegistryContext', 'ueProcessEventLiveRuntimeRegistryContext', 'ueProcessEventLiveParamValues', 'ueProcessEventLiveRawParamValues', 'ueProcessEventLiveContainerParamValues', 'ueProcessEventLiveArrayContainerParamValues', 'ueProcessEventLiveSetContainerParamValues', 'ueProcessEventLiveMapContainerParamValues', 'ueProcessEventLiveSetMapContainerParamValues', 'ueProcessEventLiveContainerDataSamples', 'ueProcessEventLuaContextHandles', 'ueProcessEventLuaParamAccessors', 'ueProcessEventLiveClassAwareParamValues', 'ueProcessEventFunctionParamMethod', 'ueProcessEventFunctionParamLookupMethod', 'ueProcessEventFunctionParamIterationMethod', 'ueProcessEventContainerAliasMethods', 'ueProcessEventContainerStorageLayoutMethods', 'ueProcessEventLuaScalarParamAccessors', 'ueProcessEventLuaNameStringParamAccessors', 'ueProcessEventLuaStructParamAccessors', 'ueProcessEventLuaEnumParamAccessors', 'ueProcessEventLuaObjectParamAccessors', 'ueProcessEventLuaBoolParamAccessors', 'ueProcessEventLuaHookRouting', 'ueProcessEventLuaHookAliasRouting', 'luaProcessEventNativeInvoke', 'luaProcessEventNativeInvokeDescriptorPreflight', 'luaProcessEventNativeExecutorState', 'luaProcessEventNativeInvokeNonSelfTestGate', 'luaProcessEventNativeInvokeNonSelfTestInvoked'),",
        "    'runtimeCallFunctionDispatch': ('ueCallFunctionHookRuntimeTarget', 'ueCallFunctionLiveHookRuntimeTarget', 'ueCallFunctionActiveValidation', 'ueCallFunctionLiveLuaDispatch', 'luaCallFunctionNativeInvoke', 'luaCallFunctionNativeInvokePreflight', 'luaCallFunctionNativeExecutorState', 'luaCallFunctionNativeInvokeNonSelfTestGate', 'luaCallFunctionNativeInvokeNonSelfTestInvoked'),",
        "}",
        "live_target_image_status = {}",
        "combined_contract_status = {}",
        "combined_contract_status.update(runtime_contract_status)",
        "combined_contract_status.update(strict_signature_anchor_status)",
        "for group, keys in live_target_image_contract_groups.items():",
        "    missing_group = [key for key in keys if not combined_contract_status.get(key)]",
        "    live_target_image_status[group] = {'ready': not missing_group, 'missingKeys': missing_group}",
        "missing_live_target_image_contract = [key for group in live_target_image_status.values() for key in group['missingKeys']]",
        "lines = ['# UE4SS Post-Canary Summary', '']",
        "lines.append(f\"- Schema: `{readiness.get('schemaVersion', 'unknown')}`\")",
        "lines.append(f\"- Loaders: `{', '.join(readiness.get('loaders', []) or ['unknown'])}`\")",
        "lines.append(f\"- Logs: `{readiness.get('logCount', 0)}`\")",
        "for key in ('objectDiscovery', 'targetImageProcess', 'runtimeRootDiscovery', 'runtimeRootValidation', 'targetObjectDiscovery', 'objectDiscoveryCoverage', 'findObjectSemantics', 'reflection', 'hooks', 'targetHooks', 'targetPackageLoadingSurface', 'luaDispatch'):",
        "    lines.append(f\"- Ready {key}: `{str(bool(ready.get(key))).lower()}`\")",
        "runtime_discovery = readiness.get('runtimeDiscovery') or {}",
        "runtime_candidate_anchors = anchor_coverage.get('runtimeCandidateAnchors') or []",
        "runtime_candidate_to_promoted = {'FNamePool': 'RuntimeFNamePool', 'GUObjectArray': 'RuntimeGUObjectArray'}",
        "promoted_runtime_roots = set(runtime_discovery.get('promotedNames') or [])",
        "validated_runtime_roots = set(runtime_discovery.get('validatedNames') or [])",
        "promoted_candidate_roots = [name for name in runtime_candidate_anchors if runtime_candidate_to_promoted.get(name) in promoted_runtime_roots]",
        "validated_candidate_roots = [name for name in runtime_candidate_anchors if runtime_candidate_to_promoted.get(name) in validated_runtime_roots]",
        "missing_candidate_roots = [name for name in runtime_candidate_anchors if runtime_candidate_to_promoted.get(name) not in promoted_runtime_roots]",
        "lines.append('- Runtime discovery promoted roots: `' + ', '.join(runtime_discovery.get('promotedNames', []) or []) + '`')",
        "lines.append('- Runtime discovery validated roots: `' + ', '.join(runtime_discovery.get('validatedNames', []) or []) + '`')",
        "lines.append('- Runtime candidate anchors injected: `' + (', '.join(runtime_candidate_anchors) or 'none') + '`')",
        "lines.append('- Runtime candidate anchors promoted: `' + (', '.join(promoted_candidate_roots) or 'none') + '`')",
        "lines.append('- Runtime candidate anchors validated: `' + (', '.join(validated_candidate_roots) or 'none') + '`')",
        "lines.append('- Runtime candidate anchors still missing: `' + (', '.join(missing_candidate_roots) or 'none') + '`')",
        "lines.append('- Runtime discovery failures: `' + (', '.join(f'{key}={value}' for key, value in sorted((runtime_discovery.get('failureCounts') or {}).items())) or 'none') + '`')",
        "lines.append('- Runtime discovery coverage: `' + json.dumps(runtime_discovery.get('coverage', {}), sort_keys=True) + '`')",
        "lines.append('')",
        "lines.append('## Runtime Evidence')",
        "lines.append('')",
        "for key in ('targetImageProcess', 'runtimeRootDiscovery', 'runtimeRootValidation', 'targetObjectDiscovery', 'targetHooks', 'ueProcessEventHookRuntimeTarget', 'ueCallFunctionHookRuntimeTarget', 'ueProcessEventLiveHookRuntimeTarget', 'ueCallFunctionLiveHookRuntimeTarget', 'ueProcessEventActiveValidation', 'ueCallFunctionActiveValidation', 'ueCallFunctionLiveLuaDispatch', 'luaCallFunctionNativeInvoke', 'luaCallFunctionNativeInvokePreflight', 'luaCallFunctionNativeExecutorState', 'luaCallFunctionNativeInvokeNonSelfTestGate', 'luaCallFunctionNativeInvokeNonSelfTestInvoked', 'luaProcessEventNativeInvoke', 'luaProcessEventNativeInvokeDescriptorPreflight', 'luaProcessEventNativeExecutorState', 'luaProcessEventNativeInvokeNonSelfTestGate', 'luaProcessEventNativeInvokeNonSelfTestInvoked', 'ueProcessEventLiveLuaDispatch', 'ueProcessEventLiveFunctionPath', 'ueProcessEventLiveRuntimeContext', 'ueProcessEventLiveRegistryContext', 'ueProcessEventLiveRuntimeRegistryContext', 'ueProcessEventLiveParamValues', 'ueProcessEventLiveRawParamValues', 'ueProcessEventLiveContainerParamValues', 'ueProcessEventLiveArrayContainerParamValues', 'ueProcessEventLiveSetContainerParamValues', 'ueProcessEventLiveMapContainerParamValues', 'ueProcessEventLiveSetMapContainerParamValues', 'ueProcessEventLiveContainerDataSamples', 'ueProcessEventLuaContextHandles', 'ueProcessEventLuaParamAccessors', 'ueProcessEventLiveClassAwareParamValues', 'ueProcessEventFunctionParamMethod', 'ueProcessEventFunctionParamLookupMethod', 'ueProcessEventFunctionParamIterationMethod', 'ueProcessEventContainerAliasMethods', 'ueProcessEventContainerStorageLayoutMethods', 'ueProcessEventLuaScalarParamAccessors', 'ueProcessEventLuaNameStringParamAccessors', 'ueProcessEventLuaStructParamAccessors', 'ueProcessEventLuaEnumParamAccessors', 'ueProcessEventLuaObjectParamAccessors', 'ueProcessEventLuaBoolParamAccessors', 'ueProcessEventLuaHookRouting', 'ueProcessEventLuaHookAliasRouting', 'luaObjectRegistryRuntime', 'luaFunctionRegistryRuntime', 'luaDecodedObjectAliasesRuntime', 'ueObjectArrayRegistryRuntime', 'luaFunctionIterationRuntime', 'luaStaticConstructObjectNativeExecutorState', 'luaStaticConstructObjectNativeExecutorReady', 'luaStaticConstructObjectNativeInvoke', 'luaLoadAssetPackageNativeExecutor', 'luaLoadAssetPackageNativeInvocation', 'luaLoadAssetPackage', 'luaLoadClassPackageAbiState', 'luaLoadClassPackageCallFrameVerification', 'luaLoadClassPackageNativeExecutor', 'luaLoadClassPackageNativeInvocation'):",
        "    lines.append(f\"- {key}: `{str(bool(runtime_contract_status.get(key))).lower()}`\")",
        "lines.append('')",
        "lines.append('## Runtime Evidence Contract')",
        "lines.append('')",
        "lines.append('- Registry rows must include `registryProvenance=runtime`; `self-test` rows do not unlock runtime readiness.')",
        "lines.append('- Live ProcessEvent context rows must include `functionProvenance=runtime` before Lua dispatch is treated as runtime-backed.')",
        "lines.append('- Live CallFunctionByNameWithArguments hook rows must show `luaDispatch=true` before CallFunction Lua parity is treated as proven.')",
        "lines.append('- Active ProcessEvent validation must emit `event=ue-process-event-active-validate status=invoked targetEntry=true` with positive live/original deltas.')",
        "lines.append('- Active CallFunctionByNameWithArguments validation must emit `event=ue-call-function-active-validate status=invoked targetEntry=true` with positive live/original deltas.')",
        "lines.append('- Hook target rows must show `selfTestTarget=false` and `callSelfTest=false` before live-hook escalation.')",
        "lines.append('- Target-image readiness requires core anchors to resolve in the game executable/module, not the probe loader image.')",
        "lines.append('- Signature validation must show exact same-build and promotable UE anchor signatures before strict readiness.')",
        "lines.append('- Anchor coverage must prove object-discovery, hook-planning, and target-image package-loading coverage before strict readiness.')",
        "lines.append('- Package native executor readiness requires `NativeExecutorReady=true`, `ExecutorPreflightPassed=true`, and `FinalNativeCallEligible=true`; dry-run executor shape rows remain diagnostic only.')",
        "lines.append('- Strict runtime contract: `' + ('enabled' if strict_runtime_contract else 'disabled') + '`')",
        "lines.append('- Missing strict runtime keys: `' + (', '.join(missing_runtime_contract) or 'none') + '`')",
        "lines.append('- Missing strict signature/anchor keys: `' + (', '.join(missing_signature_anchor_contract) or 'none') + '`')",
        "lines.append('- Live target-image canary contract ready: `' + str(not missing_live_target_image_contract).lower() + '`')",
        "lines.append('- Missing live target-image canary keys: `' + (', '.join(missing_live_target_image_contract) or 'none') + '`')",
        "for group, status in live_target_image_status.items():",
        "    lines.append(f\"- Live target-image {group}: `ready={str(bool(status['ready'])).lower()}, missing={', '.join(status['missingKeys']) or 'none'}`\")",
        "lines.append('')",
        "lines.append('## Signature And Anchor Coverage')",
        "lines.append('')",
        "for key in ('signatureManifestExact', 'signatureManifestPromotable', 'anchorCoverageObjectDiscovery', 'anchorCoverageHookPlanning', 'anchorCoveragePackageLoading', 'targetPackageLoadingSurface'):",
        "    lines.append(f\"- {key}: `{str(bool(strict_signature_anchor_status.get(key))).lower()}`\")",
        "lines.append('')",
        "lines.append('## Reflection Runtime Evidence')",
        "lines.append('')",
        "for key in ('luaReflectionForEachPropertyRuntime', 'luaReflectionLiveDescriptorTypedClassRuntime', 'luaReflectionLiveDescriptorTypedValuesRuntime', 'luaReflectionLiveDescriptorTypedSetValuesRuntime', 'luaReflectionLiveDescriptorValuesRuntime'):",
        "    lines.append(f\"- {key}: `{str(bool(runtime_contract_status.get(key))).lower()}`\")",
        "missing = coverage.get('missingObjectDiscoveryComponents', [])",
        "missing_find = coverage.get('missingFindObjectComponents', [])",
        "lines.append('')",
        "lines.append('## Object Discovery Coverage')",
        "lines.append('')",
        "lines.append('- Missing object discovery components: `' + (', '.join(missing) or 'none') + '`')",
        "lines.append('- Missing FindObject components: `' + (', '.join(missing_find) or 'none') + '`')",
        "next_steps = readiness.get('nextSteps', [])",
        "lines.append('')",
        "lines.append('## Next Steps')",
        "lines.append('')",
        "if next_steps:",
        "    lines.extend(f'- {step}' for step in next_steps[:12])",
        "else:",
        "    lines.append('- none')",
        "with open(summary_path, 'w', encoding='utf-8') as handle:",
        "    handle.write('\\n'.join(lines) + '\\n')",
        "strict_missing = missing_runtime_contract + missing_signature_anchor_contract",
        "if strict_runtime_contract and strict_missing:",
        "    raise SystemExit('missing strict UE4SS contract keys: ' + ', '.join(strict_missing))",
        "PY",
        'if [ -f "$gaps_script" ]; then',
        '  gap_args=(--readiness-json "$script_dir/ue4ss-readiness.json")',
        '  if [ -f "$script_dir/next-canary.json" ]; then',
        '    gap_args+=(--canary-plan-json "$script_dir/next-canary.json")',
        "  fi",
        '  "${PYTHON:-python3}" "$gaps_script" "${gap_args[@]}" --format json > "$script_dir/ue4ss-port-gaps.json"',
        '  "${PYTHON:-python3}" "$gaps_script" "${gap_args[@]}" --format markdown > "$script_dir/ue4ss-port-gaps.md"',
        "fi",
        'if [ -f "$inventory_script" ]; then',
        '  inventory_args=("$script_dir" --limit 12)',
        '  if [ "${DUNE_UE4SS_STRICT_RUNTIME_CONTRACT:-}" = "true" ]; then',
        '    inventory_args+=(--require-complete)',
        "  fi",
        '  "${PYTHON:-python3}" "$inventory_script" "${inventory_args[@]}" --format json > "$script_dir/ue4ss-evidence-inventory.json"',
        '  "${PYTHON:-python3}" "$inventory_script" "${inventory_args[@]}" --format markdown > "$script_dir/ue4ss-evidence-inventory.md"',
        "fi",
        'echo "wrote $script_dir/ue4ss-readiness.json"',
        'echo "wrote $script_dir/object-discovery-coverage.json"',
        'echo "wrote $script_dir/post-canary-summary.md"',
        'if [ -f "$script_dir/ue4ss-port-gaps.md" ]; then',
        '  echo "wrote $script_dir/ue4ss-port-gaps.json"',
        '  echo "wrote $script_dir/ue4ss-port-gaps.md"',
        "fi",
        'if [ -f "$script_dir/ue4ss-evidence-inventory.md" ]; then',
        '  echo "wrote $script_dir/ue4ss-evidence-inventory.json"',
        '  echo "wrote $script_dir/ue4ss-evidence-inventory.md"',
        "fi",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o755)


def write_post_canary_strict_verify_script(path):
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"',
        'DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true exec "$script_dir/post-canary-verify.sh" "$@"',
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o755)


def anchor_sort_key(name):
    order = []
    for anchors in CORE_ANCHOR_GROUPS.values():
        order.extend(anchors)
    try:
        return (0, order.index(name))
    except ValueError:
        return (1, name)


def is_loader_source(source):
    normalized = str(source or "").lower().replace("\\", "/")
    loader_needles = (
        "dune_client_probe_loader",
        "dune_server_probe_loader",
        "dune_win_client_probe_loader",
        "linux-client-loader",
        "linux-server-loader",
        "windows-client-loader",
        "libdune_",
    )
    return any(needle in normalized for needle in loader_needles)


def anchor_entry_provenance(entry):
    source = entry.get("source", "")
    if not source:
        return "unknown"
    if is_loader_source(source):
        return "loader"
    return "target"


def source_provenance_from_entry(entry):
    return anchor_entry_provenance(entry)


def canonical_core_anchor_from_symbol(row):
    demangled = row.get("demangled") or row.get("name") or ""
    raw = row.get("name") or ""
    role = row.get("role") or ""
    haystacks = (demangled, raw)
    if role == "process-event" or any("ProcessEvent" in value for value in haystacks):
        return "ProcessEvent"
    if any("StaticFindObject" in value for value in haystacks):
        return "StaticFindObject"
    if any("CallFunctionByNameWithArguments" in value for value in haystacks):
        return "CallFunctionByNameWithArguments"
    if any("CallFunctionByName" in value for value in haystacks):
        return "CallFunctionByName"
    if any("StaticLoadObject" in value for value in haystacks):
        return "StaticLoadObject"
    if any("StaticLoadClass" in value for value in haystacks):
        return "StaticLoadClass"
    if any("LoadPackage" in value for value in haystacks):
        return "LoadPackage"
    if any("ResolveName" in value for value in haystacks):
        return "ResolveName"
    if any("LoadObject" in value for value in haystacks):
        return "LoadObject"
    if any("LoadClass" in value for value in haystacks):
        return "LoadClass"
    if any("LoadAsset" in value for value in haystacks):
        return "LoadAsset"
    for anchor in ("FNamePool", "NamePoolData", "GNames", "GName", "GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray", "GWorld", "GEngine"):
        if any(anchor in value for value in haystacks):
            return anchor
    for anchor in CORE_ANCHOR_GROUPS["reflection"]:
        if any(anchor in value for value in haystacks):
            return anchor
    return None


def symbol_surface_anchor_entries(symbol_surface):
    if not isinstance(symbol_surface, dict):
        return []
    binary = symbol_surface.get("binary", "")
    entries = []
    seen = set()
    for row in symbol_surface.get("rows", []):
        if row.get("falsePositive"):
            continue
        if row.get("role") not in ("process-event", "dispatch-function", "package-function", "global-symbol"):
            continue
        anchor = canonical_core_anchor_from_symbol(row)
        if not anchor:
            continue
        key = (anchor, row.get("section"), row.get("value"), row.get("name"))
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "name": anchor,
                "source": binary,
                "symbolName": row.get("name", ""),
                "demangled": row.get("demangled", ""),
                "role": row.get("role", ""),
                "section": row.get("section", ""),
                "value": row.get("value", 0),
                "sourceProvenance": "loader" if is_loader_source(binary) else ("target" if binary else "unknown"),
            }
        )
    return entries


def candidate_global_anchor_entries(candidate_globals):
    if not isinstance(candidate_globals, dict):
        return []
    entries = []
    seen = set()
    for row in candidate_globals.get("candidates", []):
        anchor = row.get("name", "")
        if not anchor:
            continue
        key = (anchor, row.get("imageOffset", ""))
        if key in seen:
            continue
        seen.add(key)
        source = row.get("source") or candidate_globals.get("binary", "")
        entries.append(
            {
                "name": anchor,
                "source": source,
                "imageOffset": row.get("imageOffset", ""),
                "sourceTarget": row.get("sourceTarget", ""),
                "score": row.get("score", 0),
                "sourceProvenance": row.get("sourceProvenance") or ("loader" if is_loader_source(source) else ("target" if source else "unknown")),
            }
        )
    return entries


def vtable_candidate_anchor_entries(vtable_candidates):
    if not isinstance(vtable_candidates, dict):
        return []
    entries = []
    seen = set()
    for row in vtable_candidates.get("hookProbeShortlist", []) + vtable_candidates.get("rankedSlots", []):
        top_target = row.get("topTarget") or {}
        if top_target.get("targetName") != "ProcessEvent":
            continue
        if top_target.get("targetSource") != "vtable-candidate":
            continue
        candidate_count = int(row.get("candidateCount", 0) or 0)
        if float(row.get("objectCoverage", 0.0) or 0.0) < 0.45 and candidate_count < 128:
            continue
        if float(row.get("topTargetShare", 0.0) or 0.0) < 0.75:
            continue
        reasons = set(row.get("reasons", []) or [])
        if "ue4-uobject-process-event-slot-heuristic" not in reasons:
            continue
        image_offset = top_target.get("imageOffset") or top_target.get("rva") or ""
        source = top_target.get("map") or top_target.get("module") or vtable_candidates.get("binary", "")
        key = ("ProcessEvent", image_offset, row.get("slot"))
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "name": "ProcessEvent",
                "source": source,
                "imageOffset": image_offset,
                "slot": row.get("slot"),
                "score": row.get("score", 0),
                "objectCoverage": row.get("objectCoverage", 0),
                "topTargetShare": row.get("topTargetShare", 0),
                "sourceProvenance": "loader" if is_loader_source(source) else ("target" if source else "unknown"),
            }
        )
    return entries


def package_loader_vtable_candidates(package_loader_vtables):
    if not isinstance(package_loader_vtables, dict):
        return {
            "entryCount": 0,
            "methodEntryCount": 0,
            "vtableCount": 0,
            "vtables": [],
            "strongestMethods": [],
        }
    entries = []
    vtable_names = set()
    vtable_rows = []
    vtable_rows.extend(package_loader_vtables.get("vtables", []) or [])
    vtable_rows.extend(package_loader_vtables.get("rows", []) or [])
    for vtable in vtable_rows:
        vtable_name = vtable.get("demangled") or vtable.get("name") or ""
        if vtable_name:
            vtable_names.add(vtable_name)
        slot_rows = vtable.get("executableSlots") or vtable.get("slots", []) or []
        for slot in slot_rows:
            candidate_kind = slot.get("candidateKind") or slot.get("kind") or ""
            entry = {
                "vtable": vtable_name,
                "slot": slot.get("index") if slot.get("index") is not None else slot.get("slot"),
                "target": slot.get("target") or slot.get("value") or slot.get("imageOffset") or "",
                "demangled": slot.get("demangled") or slot.get("symbol") or "",
                "candidateKind": candidate_kind,
                "sourceHints": slot.get("sourceHints") or slot.get("sourcePathHints") or [],
            }
            entries.append(entry)
    method_entries = [
        entry for entry in entries
        if entry.get("candidateKind") == "method"
    ]
    strongest_methods = sorted(
        method_entries,
        key=lambda entry: (
            str(entry.get("vtable") or ""),
            int(entry.get("slot") or 0),
            str(entry.get("target") or ""),
        ),
    )[:8]
    return {
        "entryCount": len(entries),
        "methodEntryCount": len(method_entries),
        "vtableCount": len(vtable_names),
        "vtables": sorted(vtable_names),
        "strongestMethods": strongest_methods,
    }


def build_anchor_coverage(
    exporter,
    manifest,
    anchor_export,
    symbol_surface=None,
    candidate_globals=None,
    vtable_candidates=None,
    package_loader_vtables=None,
):
    explicit_entries_by_anchor = {}
    for entry in anchor_export["entries"]:
        explicit_entries_by_anchor.setdefault(entry["name"], []).append(entry)
    explicit_anchors = set(explicit_entries_by_anchor)
    runtime_candidate_anchors = {
        entry["name"]
        for entry in anchor_export["entries"]
        if entry.get("kind") == "ue-runtime-discovery-candidate"
    }
    signature_entries = exporter.anchor_signature_entries(manifest)
    signature_anchors = {entry["anchorName"] for entry in signature_entries}
    entry_category_counts = {}
    for entry in manifest.get("entries", []):
        category = entry.get("category") or "unknown"
        entry_category_counts[category] = entry_category_counts.get(category, 0) + 1
    signature_entry_category_counts = {}
    for entry in signature_entries:
        category = entry.get("category") or "unknown"
        signature_entry_category_counts[category] = signature_entry_category_counts.get(category, 0) + 1
    signature_transforms = {}
    signature_provenance_counts_by_anchor = {}
    for entry in signature_entries:
        anchor_name = entry["anchorName"]
        signature_transforms.setdefault(anchor_name, set()).add(entry["anchorTransform"])
        provenance = entry.get("sourceProvenance") or source_provenance_from_entry(entry)
        counts = signature_provenance_counts_by_anchor.setdefault(
            anchor_name,
            {"target": 0, "loader": 0, "unknown": 0},
        )
        counts[provenance if provenance in counts else "unknown"] += 1
    symbol_entries_by_anchor = {}
    symbol_provenance_counts_by_anchor = {}
    for entry in symbol_surface_anchor_entries(symbol_surface):
        anchor_name = entry["name"]
        symbol_entries_by_anchor.setdefault(anchor_name, []).append(entry)
        provenance = entry.get("sourceProvenance", "unknown")
        counts = symbol_provenance_counts_by_anchor.setdefault(
            anchor_name,
            {"target": 0, "loader": 0, "unknown": 0},
        )
        counts[provenance if provenance in counts else "unknown"] += 1
    symbol_anchors = set(symbol_entries_by_anchor)
    candidate_global_entries_by_anchor = {}
    candidate_global_provenance_counts_by_anchor = {}
    for entry in candidate_global_anchor_entries(candidate_globals):
        anchor_name = entry["name"]
        candidate_global_entries_by_anchor.setdefault(anchor_name, []).append(entry)
        provenance = entry.get("sourceProvenance", "unknown")
        counts = candidate_global_provenance_counts_by_anchor.setdefault(
            anchor_name,
            {"target": 0, "loader": 0, "unknown": 0},
        )
        counts[provenance if provenance in counts else "unknown"] += 1
    candidate_global_anchors = set(candidate_global_entries_by_anchor)
    vtable_entries_by_anchor = {}
    vtable_provenance_counts_by_anchor = {}
    for entry in vtable_candidate_anchor_entries(vtable_candidates):
        anchor_name = entry["name"]
        vtable_entries_by_anchor.setdefault(anchor_name, []).append(entry)
        provenance = entry.get("sourceProvenance", "unknown")
        counts = vtable_provenance_counts_by_anchor.setdefault(
            anchor_name,
            {"target": 0, "loader": 0, "unknown": 0},
        )
        counts[provenance if provenance in counts else "unknown"] += 1
    vtable_anchors = set(vtable_entries_by_anchor)
    package_loader_vtable_summary = package_loader_vtable_candidates(package_loader_vtables)
    combined_anchors = sorted(
        explicit_anchors | signature_anchors | symbol_anchors | candidate_global_anchors | vtable_anchors,
        key=anchor_sort_key,
    )

    groups = {}
    for group_name, group_anchors in CORE_ANCHOR_GROUPS.items():
        anchor_rows = []
        present_count = 0
        target_present_count = 0
        loader_present_count = 0
        unknown_present_count = 0
        for anchor in group_anchors:
            sources = []
            if anchor in explicit_anchors:
                sources.append("explicit")
            if anchor in runtime_candidate_anchors:
                sources.append("runtime-candidate")
            if anchor in signature_anchors:
                sources.append("signature")
            if anchor in symbol_anchors:
                sources.append("symbol-surface")
            if anchor in candidate_global_anchors:
                sources.append("candidate-global")
            if anchor in vtable_anchors:
                sources.append("vtable-candidate")
            present = bool(sources)
            if present:
                present_count += 1
            explicit_target_count = 0
            explicit_loader_count = 0
            explicit_unknown_count = 0
            for entry in explicit_entries_by_anchor.get(anchor, []):
                provenance = anchor_entry_provenance(entry)
                if provenance == "target":
                    explicit_target_count += 1
                elif provenance == "loader":
                    explicit_loader_count += 1
                else:
                    explicit_unknown_count += 1
            signature_counts = signature_provenance_counts_by_anchor.get(anchor, {})
            signature_target_count = signature_counts.get("target", 0)
            signature_loader_count = signature_counts.get("loader", 0)
            signature_unknown_count = signature_counts.get("unknown", 0)
            symbol_counts = symbol_provenance_counts_by_anchor.get(anchor, {})
            symbol_target_count = symbol_counts.get("target", 0)
            symbol_loader_count = symbol_counts.get("loader", 0)
            symbol_unknown_count = symbol_counts.get("unknown", 0)
            candidate_global_counts = candidate_global_provenance_counts_by_anchor.get(anchor, {})
            candidate_global_target_count = candidate_global_counts.get("target", 0)
            candidate_global_loader_count = candidate_global_counts.get("loader", 0)
            candidate_global_unknown_count = candidate_global_counts.get("unknown", 0)
            vtable_counts = vtable_provenance_counts_by_anchor.get(anchor, {})
            vtable_target_count = vtable_counts.get("target", 0)
            vtable_loader_count = vtable_counts.get("loader", 0)
            vtable_unknown_count = vtable_counts.get("unknown", 0)
            target_source_count = (
                explicit_target_count
                + signature_target_count
                + symbol_target_count
                + candidate_global_target_count
                + vtable_target_count
            )
            loader_source_count = (
                explicit_loader_count
                + signature_loader_count
                + symbol_loader_count
                + candidate_global_loader_count
                + vtable_loader_count
            )
            unknown_source_count = (
                explicit_unknown_count
                + signature_unknown_count
                + symbol_unknown_count
                + candidate_global_unknown_count
                + vtable_unknown_count
            )
            target_present = target_source_count > 0
            loader_present = loader_source_count > 0
            unknown_present = unknown_source_count > 0
            if target_present:
                target_present_count += 1
            if loader_present:
                loader_present_count += 1
            if unknown_present:
                unknown_present_count += 1
            row = {
                "name": anchor,
                "present": present,
                "targetPresent": target_present,
                "loaderPresent": loader_present,
                "unknownPresent": unknown_present,
                "targetSourceCount": target_source_count,
                "loaderSourceCount": loader_source_count,
                "unknownSourceCount": unknown_source_count,
                "sources": sources,
            }
            if anchor in signature_transforms:
                row["signatureTransforms"] = sorted(signature_transforms[anchor])
            if anchor in symbol_entries_by_anchor:
                row["symbolSurfaceRoles"] = sorted({entry.get("role", "") for entry in symbol_entries_by_anchor[anchor]})
            if anchor in candidate_global_entries_by_anchor:
                row["candidateGlobalOffsets"] = sorted(
                    {
                        entry.get("imageOffset", "")
                        for entry in candidate_global_entries_by_anchor[anchor]
                        if entry.get("imageOffset", "")
                    }
                )
            if anchor in vtable_entries_by_anchor:
                row["vtableCandidateSlots"] = sorted(
                    {
                        int(entry.get("slot"))
                        for entry in vtable_entries_by_anchor[anchor]
                        if entry.get("slot") is not None
                    }
                )
                row["vtableCandidateOffsets"] = sorted(
                    {
                        entry.get("imageOffset", "")
                        for entry in vtable_entries_by_anchor[anchor]
                        if entry.get("imageOffset", "")
                    }
                )
            anchor_rows.append(row)
        groups[group_name] = {
            "present": present_count,
            "targetPresent": target_present_count,
            "loaderPresent": loader_present_count,
            "unknownPresent": unknown_present_count,
            "total": len(group_anchors),
            "complete": present_count == len(group_anchors),
            "targetComplete": target_present_count == len(group_anchors),
            "anchors": anchor_rows,
        }

    missing_required_groups = [
        group_name for group_name in REQUIRED_DISCOVERY_GROUPS
        if groups[group_name]["present"] == 0
    ]
    missing_signature_anchor_groups = [
        group_name for group_name, group in groups.items()
        if not any("signature" in anchor["sources"] for anchor in group["anchors"])
    ]
    missing_required_signature_anchor_groups = [
        group_name for group_name in REQUIRED_DISCOVERY_GROUPS
        if group_name in missing_signature_anchor_groups
    ]
    ready_for_object_discovery = not missing_required_groups
    ready_for_hook_planning = ready_for_object_discovery and (
        any(anchor["name"] == "ProcessEvent" and anchor["present"] for anchor in groups["dispatch"]["anchors"])
    )
    ready_for_package_loading = any(anchor["present"] for anchor in groups["package"]["anchors"])
    ready_for_target_object_discovery = all(groups[group]["targetPresent"] > 0 for group in REQUIRED_DISCOVERY_GROUPS)
    ready_for_target_hook_planning = ready_for_target_object_discovery and (
        any(anchor["name"] == "ProcessEvent" and anchor["targetPresent"] for anchor in groups["dispatch"]["anchors"])
    )
    ready_for_target_package_loading = any(anchor["targetPresent"] for anchor in groups["package"]["anchors"])

    return {
        "schemaVersion": "dune-ue-anchor-coverage/v1",
        "provided": True,
        "explicitAnchorCount": len(explicit_anchors),
        "runtimeCandidateAnchorCount": len(runtime_candidate_anchors),
        "runtimeCandidateAnchors": sorted(runtime_candidate_anchors, key=anchor_sort_key),
        "manifestEntryCount": manifest.get("entryCount", len(manifest.get("entries", []))),
        "manifestEntryCategoryCounts": entry_category_counts,
        "signatureAnchorEntryCount": len(signature_entries),
        "signatureAnchorEntryCategoryCounts": signature_entry_category_counts,
        "signatureAnchorCount": len(signature_anchors),
        "symbolSurfaceAnchorEntryCount": sum(len(entries) for entries in symbol_entries_by_anchor.values()),
        "symbolSurfaceAnchorCount": len(symbol_anchors),
        "candidateGlobalAnchorEntryCount": sum(len(entries) for entries in candidate_global_entries_by_anchor.values()),
        "candidateGlobalAnchorCount": len(candidate_global_anchors),
        "vtableCandidateAnchorEntryCount": sum(len(entries) for entries in vtable_entries_by_anchor.values()),
        "vtableCandidateAnchorCount": len(vtable_anchors),
        "packageLoaderVTableCandidateEntryCount": package_loader_vtable_summary["entryCount"],
        "packageLoaderVTableMethodCandidateCount": package_loader_vtable_summary["methodEntryCount"],
        "packageLoaderVTableCount": package_loader_vtable_summary["vtableCount"],
        "packageLoaderVTables": package_loader_vtable_summary["vtables"],
        "packageLoaderVTableStrongestMethods": package_loader_vtable_summary["strongestMethods"],
        "packageLoaderVTablePromotable": False,
        "packageLoaderVTableNonPromotableReason": (
            "package-loader vtable methods do not match the current guarded package bridge ABI "
            "(StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName)"
        ),
        "combinedAnchorCount": len(combined_anchors),
        "explicitAnchors": sorted(explicit_anchors, key=anchor_sort_key),
        "signatureAnchors": sorted(signature_anchors, key=anchor_sort_key),
        "symbolSurfaceAnchors": sorted(symbol_anchors, key=anchor_sort_key),
        "candidateGlobalAnchors": sorted(candidate_global_anchors, key=anchor_sort_key),
        "vtableCandidateAnchors": sorted(vtable_anchors, key=anchor_sort_key),
        "combinedAnchors": combined_anchors,
        "groups": groups,
        "missingRequiredGroups": missing_required_groups,
        "missingSignatureAnchorGroups": missing_signature_anchor_groups,
        "missingRequiredSignatureAnchorGroups": missing_required_signature_anchor_groups,
        "readyForObjectDiscovery": ready_for_object_discovery,
        "readyForHookPlanning": ready_for_hook_planning,
        "readyForPackageLoading": ready_for_package_loading,
        "readyForTargetObjectDiscovery": ready_for_target_object_discovery,
        "readyForTargetHookPlanning": ready_for_target_hook_planning,
        "readyForTargetPackageLoading": ready_for_target_package_loading,
        "targetCoverageFieldsPresent": True,
    }


def write_summary(path, args, platform, manifest, anchor_export, anchor_coverage, files):
    lines = ["# UE Anchor Canary Prep", ""]
    lines.append(f"- Platform: `{platform}`")
    lines.append(f"- Manifest entries: `{manifest['entryCount']}`")
    lines.append(f"- Manifest entry categories: `{anchor_coverage['manifestEntryCategoryCounts']}`")
    lines.append(f"- Anchor env entries: `{anchor_export['entryCount']}`")
    lines.append(f"- Runtime candidate anchors: `{anchor_coverage['runtimeCandidateAnchorCount']}`")
    lines.append(f"- Signature anchor entries: `{anchor_coverage['signatureAnchorEntryCount']}`")
    lines.append(f"- Signature anchors: `{anchor_coverage['signatureAnchorCount']}`")
    lines.append(f"- Symbol-surface anchor entries: `{anchor_coverage['symbolSurfaceAnchorEntryCount']}`")
    lines.append(f"- Symbol-surface anchors: `{anchor_coverage['symbolSurfaceAnchorCount']}`")
    lines.append(f"- Candidate-global anchor entries: `{anchor_coverage['candidateGlobalAnchorEntryCount']}`")
    lines.append(f"- Candidate-global anchors: `{anchor_coverage['candidateGlobalAnchorCount']}`")
    lines.append(f"- VTable candidate anchor entries: `{anchor_coverage['vtableCandidateAnchorEntryCount']}`")
    lines.append(f"- VTable candidate anchors: `{anchor_coverage['vtableCandidateAnchorCount']}`")
    lines.append(f"- Package-loader vtable candidate slots: `{anchor_coverage['packageLoaderVTableCandidateEntryCount']}`")
    lines.append(f"- Package-loader vtable method candidates: `{anchor_coverage['packageLoaderVTableMethodCandidateCount']}`")
    if anchor_coverage["packageLoaderVTableCandidateEntryCount"]:
        lines.append(f"- Package-loader vtable promotable: `{str(anchor_coverage['packageLoaderVTablePromotable']).lower()}`")
        lines.append(f"- Package-loader vtable non-promotable reason: `{anchor_coverage['packageLoaderVTableNonPromotableReason']}`")
    lines.append(f"- Combined anchors: `{anchor_coverage['combinedAnchorCount']}`")
    lines.append(f"- Ready for object discovery: `{str(anchor_coverage['readyForObjectDiscovery']).lower()}`")
    lines.append(f"- Ready for hook planning: `{str(anchor_coverage['readyForHookPlanning']).lower()}`")
    lines.append(f"- Ready for package loading anchors: `{str(anchor_coverage['readyForPackageLoading']).lower()}`")
    lines.append(f"- Ready for target-image object discovery: `{str(anchor_coverage['readyForTargetObjectDiscovery']).lower()}`")
    lines.append(f"- Ready for target-image hook planning: `{str(anchor_coverage['readyForTargetHookPlanning']).lower()}`")
    lines.append(f"- Ready for target-image package loading anchors: `{str(anchor_coverage['readyForTargetPackageLoading']).lower()}`")
    if anchor_export["missing"]:
        lines.append(f"- Missing anchors: `{', '.join(anchor_export['missing'])}`")
    if anchor_coverage["missingRequiredGroups"]:
        lines.append(f"- Missing required groups: `{', '.join(anchor_coverage['missingRequiredGroups'])}`")
    if manifest["entryCount"] and not anchor_coverage["signatureAnchorEntryCount"]:
        lines.append(
            "- UE anchor signature coverage: `none` "
            "(validated signatures exist, but none map to core UE anchors)"
        )
    if anchor_coverage["missingRequiredSignatureAnchorGroups"]:
        lines.append(
            "- Missing required signature anchor groups: "
            f"`{', '.join(anchor_coverage['missingRequiredSignatureAnchorGroups'])}`"
        )
    lines.append("")
    lines.append("## Core Anchor Coverage")
    lines.append("")
    for group_name, group in anchor_coverage["groups"].items():
        lines.append(
            f"- {group_name}: `{group['present']}/{group['total']}` "
            f"target=`{group['targetPresent']}/{group['total']}`"
        )
    if anchor_coverage["packageLoaderVTableStrongestMethods"]:
        lines.append("")
        lines.append("## Package Loader VTable Candidates")
        lines.append("")
        for entry in anchor_coverage["packageLoaderVTableStrongestMethods"]:
            lines.append(
                f"- slot `{entry.get('slot')}` target `{entry.get('target') or 'unknown'}` "
                f"kind `{entry.get('candidateKind') or 'unknown'}` "
                f"vtable `{entry.get('vtable') or 'unknown'}`"
            )
    if not (
        anchor_coverage["readyForTargetObjectDiscovery"]
        and anchor_coverage["readyForTargetHookPlanning"]
        and anchor_coverage["readyForTargetPackageLoading"]
    ):
        lines.extend(target_image_recovery_lines(path.parent, args, platform, manifest, anchor_coverage))
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    for label, output in files.items():
        lines.append(f"- {label}: `{output}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def target_image_missing_groups(anchor_coverage):
    groups = anchor_coverage.get("groups", {})
    object_groups = [
        group_name for group_name in REQUIRED_DISCOVERY_GROUPS
        if groups.get(group_name, {}).get("targetPresent", 0) == 0
    ]
    hook_groups = list(object_groups)
    dispatch = groups.get("dispatch", {})
    if not any(
        anchor.get("name") == "ProcessEvent" and anchor.get("targetPresent")
        for anchor in dispatch.get("anchors", [])
    ) and "dispatch" not in hook_groups:
        hook_groups.append("dispatch")
    package_groups = []
    if not groups.get("package", {}).get("targetPresent", 0):
        package_groups.append("package")
    return {
        "object": object_groups,
        "hook": hook_groups,
        "package": package_groups,
    }


def target_image_recovery_reasons(anchor_coverage, missing):
    reasons = []
    if missing["object"]:
        reasons.append("missing-target-object-anchor-groups")
    if missing["hook"]:
        reasons.append("missing-target-hook-anchor-groups")
    if missing["package"]:
        reasons.append("missing-target-package-anchor-groups")
    if not anchor_coverage.get("readyForTargetObjectDiscovery"):
        reasons.append("incomplete-target-object-anchor-coverage")
    if not anchor_coverage.get("readyForTargetHookPlanning"):
        reasons.append("incomplete-target-hook-anchor-coverage")
    if not anchor_coverage.get("readyForTargetPackageLoading"):
        reasons.append("incomplete-target-package-anchor-coverage")
    return reasons


def target_image_recovery_lines(output_dir, args, platform, manifest, anchor_coverage):
    binary = manifest.get("binary", {}).get("path") or "<target-binary>"
    loader_log = manifest.get("source", {}).get("loaderLog") or default_canary_log_path(platform)
    xref_json = output_dir / "ue-anchor-xrefs.json"
    candidates_json = output_dir / "ue-anchor-candidates.json"
    symbol_surface_json = output_dir / "elf-ue-symbol-surface.json"
    package_route_json = output_dir / "ue4ss-package-route-evidence.json"
    package_external_plan_json = output_dir / "ue4ss-package-external-symbol-plan.json"
    package_external_plan_md = output_dir / "ue4ss-package-external-symbol-plan.md"
    recovered_dir = output_dir / "recovered-target-anchors"
    missing = target_image_missing_groups(anchor_coverage)
    reasons = target_image_recovery_reasons(anchor_coverage, missing)
    if platform == "windows":
        xref_command = [
            "python3",
            "scripts/summarize-client-loader-xrefs.py",
            binary,
            "--loader-log",
            loader_log,
        ]
        for loader in args.loader or ["win-client"]:
            xref_command.extend(["--loader", loader])
    else:
        xref_command = [
            "python3",
            "scripts/summarize-linux-loader-xrefs.py",
            binary,
            "--loader-log",
            loader_log,
        ]
    for pid in args.pid:
        xref_command.extend(["--pid", pid])
    exe_substrings = args.exe_substring or ["DuneSandbox" if platform == "linux-client" else "DuneSandboxServer"]
    for substring in exe_substrings:
        xref_command.extend(["--exe-substring", substring])
    xref_command.extend(["--category", "ue", "--format", "json"])
    promote_command = [
        "python3",
        "scripts/promote-ue-anchor-xref-candidates.py",
        str(xref_json),
        "--require-target-source",
        "--format",
        "json",
    ]
    prepare_command = [
        "python3",
        "scripts/prepare-ue-anchor-canary.py",
        "--platform",
        platform,
        "--binary",
        binary,
        "--loader-log",
        loader_log,
        "--xref-json",
        str(candidates_json),
        "--output-dir",
        str(recovered_dir),
        "--skip-readiness",
    ]
    symbol_surface_command = []
    if platform != "windows":
        symbol_surface_command = [
            "python3",
            "scripts/summarize-elf-ue-symbol-surface.py",
            binary,
            "--format",
            "json",
        ]
        prepare_command.extend(["--symbol-surface-json", str(symbol_surface_json)])
    if platform == "windows":
        default_loader = "win-client"
    elif platform == "linux-client":
        default_loader = "client"
    else:
        default_loader = "server"
    for loader in args.loader or [default_loader]:
        prepare_command.extend(["--loader", loader])
    for pid in args.pid:
        prepare_command.extend(["--pid", pid])
    for substring in args.exe_substring:
        prepare_command.extend(["--exe-substring", substring])
    package_recovery_commands = []
    if missing["package"]:
        package_route_command = [
            "python3",
            "scripts/summarize-ue4ss-package-route-evidence.py",
            "--format",
            "json",
        ]
        package_plan_json_command = [
            "python3",
            "scripts/summarize-ue4ss-package-external-symbol-plan.py",
            "--evidence",
            str(package_route_json),
            "--binary",
            binary,
            "--format",
            "json",
        ]
        package_plan_md_command = [
            "python3",
            "scripts/summarize-ue4ss-package-external-symbol-plan.py",
            "--evidence",
            str(package_route_json),
            "--binary",
            binary,
            "--format",
            "markdown",
        ]
        package_recovery_commands = [
            "",
            "Package-loading anchors require a callable target-image StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or ResolveName ABI. Do not promote async-package vtable methods or string-only hits.",
            f"```sh\n{command_text(package_route_command)} > {shlex.quote(str(package_route_json))}\n```",
            f"```sh\n{command_text(package_plan_json_command)} > {shlex.quote(str(package_external_plan_json))}\n```",
            f"```sh\n{command_text(package_plan_md_command)} > {shlex.quote(str(package_external_plan_md))}\n```",
        ]
    return [
        "",
        "## Target-Image Anchor Recovery",
        "",
        "Run these when target-image object, hook, or package anchor coverage is false:",
        "",
        f"- Recovery reasons: `{', '.join(reasons) or 'none'}`",
        (
            "- Missing target groups: "
            f"`object={', '.join(missing['object']) or 'none'}; "
            f"hook={', '.join(missing['hook']) or 'none'}; "
            f"package={', '.join(missing['package']) or 'none'}`"
        ),
        "",
        *(
            [f"```sh\n{command_text(symbol_surface_command)} > {shlex.quote(str(symbol_surface_json))}\n```"]
            if symbol_surface_command
            else []
        ),
        f"```sh\n{command_text(xref_command)} > {shlex.quote(str(xref_json))}\n```",
        f"```sh\n{command_text(promote_command)} > {shlex.quote(str(candidates_json))}\n```",
        f"```sh\n{command_text(prepare_command)}\n```",
        *package_recovery_commands,
        (
            f"```sh\n{shlex.quote(str(recovered_dir / 'post-canary-verify.sh'))} "
            f"{shlex.quote(loader_log)}\n```"
        ),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Prepare second-pass UE anchor canary artifacts from a Dune loader log and binary."
    )
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--loader-log", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validation-json", type=Path)
    parser.add_argument("--xref-json", type=Path)
    parser.add_argument(
        "--symbol-surface-json",
        type=Path,
        help="optional summarize-elf-ue-symbol-surface.py JSON output to count target ELF exports as anchor evidence",
    )
    parser.add_argument(
        "--candidate-globals-json",
        type=Path,
        help="optional export-ue-candidate-globals.py JSON output to count reviewed target globals as anchor evidence",
    )
    parser.add_argument(
        "--vtable-candidates-json",
        type=Path,
        help="optional summarize-ue-vtable-candidates.py JSON output to count stable target ProcessEvent vtable candidates",
    )
    parser.add_argument(
        "--package-loader-vtables-json",
        type=Path,
        help="optional summarize-elf-ue-package-loader-vtables.py JSON output to record non-promotable package-loader vtable candidates",
    )
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--anchor-name", action="append", default=[])
    parser.add_argument(
        "--include-runtime-candidates",
        action="store_true",
        help="include unique RuntimeFNamePool/RuntimeGUObjectArray candidates in generated anchor env",
    )
    parser.add_argument(
        "--runtime-candidate",
        action="append",
        default=[],
        metavar="NAME=OFFSET",
        help="include a reviewed ambiguous runtime root candidate by canonical name and image offset/RVA",
    )
    parser.add_argument("--signature-prefix", type=int, default=8)
    parser.add_argument("--signature-suffix", type=int, default=16)
    parser.add_argument("--scope", choices=("executable", "all"), default="executable")
    parser.add_argument("--max-matches", type=int, default=16)
    parser.add_argument("--include-non-promotable", action="store_true")
    parser.add_argument("--max-patterns-per-scan", type=int, default=256)
    parser.add_argument("--max-env-value-chars", type=int, default=1800)
    parser.add_argument("--skip-readiness", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    config = platform_config(args.platform)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    exporter, manifest = build_manifest(args, config)
    manifest_path = args.output_dir / config["manifestName"]
    validation_path = args.output_dir / "signature-validation.json"
    anchor_signature_path = args.output_dir / config["anchorSignatureName"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation_path.write_text(json.dumps(manifest["validation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    anchor_signature_path.write_text(exporter.anchor_signatures_text(manifest), encoding="utf-8")

    anchor_exporter, anchor_export = build_anchor_env(args, config)
    anchor_env_path = args.output_dir / config["anchorEnvName"]
    anchor_env_text = anchor_exporter.env_text(anchor_export)
    anchor_env_text += (
        "# Signature-resolved UE anchor promotion input\n"
        f"{anchor_export['anchorSignatureFileEnvName']}={anchor_exporter.shell_quote(str(anchor_signature_path))}\n"
    )
    anchor_env_path.write_text(anchor_env_text, encoding="utf-8")
    symbol_surface = load_json(args.symbol_surface_json) if args.symbol_surface_json else None
    candidate_globals = load_json(args.candidate_globals_json) if args.candidate_globals_json else None
    vtable_candidates = load_json(args.vtable_candidates_json) if args.vtable_candidates_json else None
    package_loader_vtables = load_json(args.package_loader_vtables_json) if args.package_loader_vtables_json else None
    anchor_coverage = build_anchor_coverage(
        exporter,
        manifest,
        anchor_export,
        symbol_surface,
        candidate_globals,
        vtable_candidates,
        package_loader_vtables,
    )
    anchor_coverage_path = args.output_dir / "anchor-coverage.json"
    anchor_coverage_path.write_text(json.dumps(anchor_coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    post_canary_verify_path = args.output_dir / "post-canary-verify.sh"
    write_post_canary_verify_script(post_canary_verify_path, args.platform, config)
    post_canary_strict_verify_path = args.output_dir / "post-canary-verify-strict.sh"
    write_post_canary_strict_verify_script(post_canary_strict_verify_path)

    files = {
        "manifest": manifest_path,
        "signatureValidation": validation_path,
        "anchorSignatures": anchor_signature_path,
        "anchorEnv": anchor_env_path,
        "anchorCoverage": anchor_coverage_path,
        "postCanaryVerify": post_canary_verify_path,
        "postCanaryVerifyStrict": post_canary_strict_verify_path,
    }
    if not args.skip_readiness:
        readiness_path = args.output_dir / "ue4ss-readiness.md"
        readiness_json_path = args.output_dir / "ue4ss-readiness.json"
        object_discovery_coverage_path = args.output_dir / "object-discovery-coverage.json"
        readiness_path.write_text(
            run_readiness(args, config, validation_path, anchor_coverage_path, "markdown"),
            encoding="utf-8",
        )
        readiness_json = json.loads(run_readiness(args, config, validation_path, anchor_coverage_path, "json"))
        readiness_json_path.write_text(json.dumps(readiness_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        object_discovery_coverage_path.write_text(
            json.dumps(readiness_json["objectDiscoveryCoverage"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        files["readiness"] = readiness_path
        files["readinessJson"] = readiness_json_path
        files["objectDiscoveryCoverage"] = object_discovery_coverage_path

    summary_path = args.output_dir / "README.md"
    write_summary(summary_path, args, args.platform, manifest, anchor_export, anchor_coverage, files)
    files["summary"] = summary_path

    result = {
        "schemaVersion": "dune-ue-anchor-canary-prep/v1",
        "platform": args.platform,
        "manifestEntryCount": manifest["entryCount"],
        "anchorEnvEntryCount": anchor_export["entryCount"],
        "anchorSignatureEntryCount": anchor_coverage["signatureAnchorEntryCount"],
        "symbolSurfaceAnchorEntryCount": anchor_coverage["symbolSurfaceAnchorEntryCount"],
        "symbolSurfaceAnchorCount": anchor_coverage["symbolSurfaceAnchorCount"],
        "candidateGlobalAnchorEntryCount": anchor_coverage["candidateGlobalAnchorEntryCount"],
        "candidateGlobalAnchorCount": anchor_coverage["candidateGlobalAnchorCount"],
        "vtableCandidateAnchorEntryCount": anchor_coverage["vtableCandidateAnchorEntryCount"],
        "vtableCandidateAnchorCount": anchor_coverage["vtableCandidateAnchorCount"],
        "packageLoaderVTableCandidateEntryCount": anchor_coverage["packageLoaderVTableCandidateEntryCount"],
        "packageLoaderVTableMethodCandidateCount": anchor_coverage["packageLoaderVTableMethodCandidateCount"],
        "packageLoaderVTableCount": anchor_coverage["packageLoaderVTableCount"],
        "packageLoaderVTablePromotable": anchor_coverage["packageLoaderVTablePromotable"],
        "combinedAnchorCount": anchor_coverage["combinedAnchorCount"],
        "readyForObjectDiscovery": anchor_coverage["readyForObjectDiscovery"],
        "readyForHookPlanning": anchor_coverage["readyForHookPlanning"],
        "readyForPackageLoading": anchor_coverage["readyForPackageLoading"],
        "readyForTargetObjectDiscovery": anchor_coverage["readyForTargetObjectDiscovery"],
        "readyForTargetHookPlanning": anchor_coverage["readyForTargetHookPlanning"],
        "readyForTargetPackageLoading": anchor_coverage["readyForTargetPackageLoading"],
        "anchorCoverage": anchor_coverage,
        "missingAnchors": anchor_export["missing"],
        "includeRuntimeCandidates": anchor_export.get("includeRuntimeCandidates", False),
        "runtimeCandidateSelectors": anchor_export.get("runtimeCandidateSelectors", []),
        "outputs": {key: str(value) for key, value in files.items()},
    }
    if args.format == "json":
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
