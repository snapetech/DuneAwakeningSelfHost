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
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
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
        "    'ueCallFunctionLiveLuaDispatch': 'ue-call-function-live-lua-dispatch',",
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
        "    'luaLoadAssetPackage': 'lua-load-asset-package',",
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
        "    'runtimePackageLoading': ('luaLoadAssetPackageCrashGuard', 'luaLoadAssetPackageGuardedCall', 'luaLoadAssetPackageReturnValidation', 'luaLoadAssetPackageNativeCallAdapter', 'luaLoadAssetPackageInvocationDescriptor', 'luaLoadAssetPackageNativeExecutor', 'luaLoadAssetPackage'),",
        "    'runtimeObjectRegistry': ('objectDiscoveryCoverage', 'findObjectSemantics', 'luaObjectRegistryRuntime', 'luaFunctionRegistryRuntime', 'luaDecodedObjectAliasesRuntime', 'ueObjectArrayShape', 'ueObjectArrayRegistryRuntime', 'ueObjectNativeIdentities', 'ueObjectInternalFlags', 'ueFNameDecoder', 'luaObjectOuterChainIdentities', 'luaObjectApi', 'luaFunctionIterationRuntime'),",
        "    'runtimeReflection': ('ueReflectionPropertyDescriptorsRuntime', 'ueReflectionPropertyValuesRuntime', 'luaReflectionForEachPropertyRuntime', 'luaReflectionLiveDescriptorTypedClassRuntime', 'luaReflectionLiveDescriptorTypedValuesRuntime', 'luaReflectionLiveDescriptorTypedSetValuesRuntime', 'luaReflectionLiveDescriptorValuesRuntime'),",
        "    'runtimeProcessEventDispatch': ('ueProcessEventHookRuntimeTarget', 'ueProcessEventLiveHookRuntimeTarget', 'ueProcessEventLiveLuaDispatch', 'ueProcessEventLiveFunctionPath', 'ueProcessEventLiveRuntimeContext', 'ueProcessEventLiveRegistryContext', 'ueProcessEventLiveRuntimeRegistryContext', 'ueProcessEventLiveParamValues', 'ueProcessEventLiveRawParamValues', 'ueProcessEventLiveContainerParamValues', 'ueProcessEventLiveArrayContainerParamValues', 'ueProcessEventLiveSetContainerParamValues', 'ueProcessEventLiveMapContainerParamValues', 'ueProcessEventLiveSetMapContainerParamValues', 'ueProcessEventLiveContainerDataSamples', 'ueProcessEventLuaContextHandles', 'ueProcessEventLuaParamAccessors', 'ueProcessEventLiveClassAwareParamValues', 'ueProcessEventFunctionParamMethod', 'ueProcessEventFunctionParamLookupMethod', 'ueProcessEventFunctionParamIterationMethod', 'ueProcessEventContainerAliasMethods', 'ueProcessEventContainerStorageLayoutMethods', 'ueProcessEventLuaScalarParamAccessors', 'ueProcessEventLuaNameStringParamAccessors', 'ueProcessEventLuaStructParamAccessors', 'ueProcessEventLuaEnumParamAccessors', 'ueProcessEventLuaObjectParamAccessors', 'ueProcessEventLuaBoolParamAccessors', 'ueProcessEventLuaHookRouting', 'ueProcessEventLuaHookAliasRouting'),",
        "    'runtimeCallFunctionDispatch': ('ueCallFunctionHookRuntimeTarget', 'ueCallFunctionLiveHookRuntimeTarget', 'ueCallFunctionLiveLuaDispatch'),",
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
        "for key in ('targetImageProcess', 'runtimeRootDiscovery', 'runtimeRootValidation', 'targetObjectDiscovery', 'targetHooks', 'ueProcessEventHookRuntimeTarget', 'ueCallFunctionHookRuntimeTarget', 'ueProcessEventLiveHookRuntimeTarget', 'ueCallFunctionLiveHookRuntimeTarget', 'ueCallFunctionLiveLuaDispatch', 'ueProcessEventLiveLuaDispatch', 'ueProcessEventLiveFunctionPath', 'ueProcessEventLiveRuntimeContext', 'ueProcessEventLiveRegistryContext', 'ueProcessEventLiveRuntimeRegistryContext', 'ueProcessEventLiveParamValues', 'ueProcessEventLiveRawParamValues', 'ueProcessEventLiveContainerParamValues', 'ueProcessEventLiveArrayContainerParamValues', 'ueProcessEventLiveSetContainerParamValues', 'ueProcessEventLiveMapContainerParamValues', 'ueProcessEventLiveSetMapContainerParamValues', 'ueProcessEventLiveContainerDataSamples', 'ueProcessEventLuaContextHandles', 'ueProcessEventLuaParamAccessors', 'ueProcessEventLiveClassAwareParamValues', 'ueProcessEventFunctionParamMethod', 'ueProcessEventFunctionParamLookupMethod', 'ueProcessEventFunctionParamIterationMethod', 'ueProcessEventContainerAliasMethods', 'ueProcessEventContainerStorageLayoutMethods', 'ueProcessEventLuaScalarParamAccessors', 'ueProcessEventLuaNameStringParamAccessors', 'ueProcessEventLuaStructParamAccessors', 'ueProcessEventLuaEnumParamAccessors', 'ueProcessEventLuaObjectParamAccessors', 'ueProcessEventLuaBoolParamAccessors', 'ueProcessEventLuaHookRouting', 'ueProcessEventLuaHookAliasRouting', 'luaObjectRegistryRuntime', 'luaFunctionRegistryRuntime', 'luaDecodedObjectAliasesRuntime', 'ueObjectArrayRegistryRuntime', 'luaFunctionIterationRuntime'):",
        "    lines.append(f\"- {key}: `{str(bool(runtime_contract_status.get(key))).lower()}`\")",
        "lines.append('')",
        "lines.append('## Runtime Evidence Contract')",
        "lines.append('')",
        "lines.append('- Registry rows must include `registryProvenance=runtime`; `self-test` rows do not unlock runtime readiness.')",
        "lines.append('- Live ProcessEvent context rows must include `functionProvenance=runtime` before Lua dispatch is treated as runtime-backed.')",
        "lines.append('- Live CallFunctionByNameWithArguments hook rows must show `luaDispatch=true` before CallFunction Lua parity is treated as proven.')",
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
        'echo "wrote $script_dir/ue4ss-readiness.json"',
        'echo "wrote $script_dir/object-discovery-coverage.json"',
        'echo "wrote $script_dir/post-canary-summary.md"',
        'if [ -f "$script_dir/ue4ss-port-gaps.md" ]; then',
        '  echo "wrote $script_dir/ue4ss-port-gaps.json"',
        '  echo "wrote $script_dir/ue4ss-port-gaps.md"',
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


def build_anchor_coverage(exporter, manifest, anchor_export):
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
    for entry in signature_entries:
        signature_transforms.setdefault(entry["anchorName"], set()).add(entry["anchorTransform"])
    combined_anchors = sorted(explicit_anchors | signature_anchors, key=anchor_sort_key)

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
            signature_target_count = 1 if anchor in signature_anchors else 0
            target_source_count = explicit_target_count + signature_target_count
            loader_source_count = explicit_loader_count
            unknown_source_count = explicit_unknown_count
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
        "explicitAnchorCount": len(explicit_anchors),
        "runtimeCandidateAnchorCount": len(runtime_candidate_anchors),
        "runtimeCandidateAnchors": sorted(runtime_candidate_anchors, key=anchor_sort_key),
        "manifestEntryCount": manifest.get("entryCount", len(manifest.get("entries", []))),
        "manifestEntryCategoryCounts": entry_category_counts,
        "signatureAnchorEntryCount": len(signature_entries),
        "signatureAnchorEntryCategoryCounts": signature_entry_category_counts,
        "signatureAnchorCount": len(signature_anchors),
        "combinedAnchorCount": len(combined_anchors),
        "explicitAnchors": sorted(explicit_anchors, key=anchor_sort_key),
        "signatureAnchors": sorted(signature_anchors, key=anchor_sort_key),
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
    }


def write_summary(path, platform, manifest, anchor_export, anchor_coverage, files):
    lines = ["# UE Anchor Canary Prep", ""]
    lines.append(f"- Platform: `{platform}`")
    lines.append(f"- Manifest entries: `{manifest['entryCount']}`")
    lines.append(f"- Manifest entry categories: `{anchor_coverage['manifestEntryCategoryCounts']}`")
    lines.append(f"- Anchor env entries: `{anchor_export['entryCount']}`")
    lines.append(f"- Runtime candidate anchors: `{anchor_coverage['runtimeCandidateAnchorCount']}`")
    lines.append(f"- Signature anchor entries: `{anchor_coverage['signatureAnchorEntryCount']}`")
    lines.append(f"- Signature anchors: `{anchor_coverage['signatureAnchorCount']}`")
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
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    for label, output in files.items():
        lines.append(f"- {label}: `{output}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


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
    anchor_coverage = build_anchor_coverage(exporter, manifest, anchor_export)
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
    write_summary(summary_path, args.platform, manifest, anchor_export, anchor_coverage, files)
    files["summary"] = summary_path

    result = {
        "schemaVersion": "dune-ue-anchor-canary-prep/v1",
        "platform": args.platform,
        "manifestEntryCount": manifest["entryCount"],
        "anchorEnvEntryCount": anchor_export["entryCount"],
        "anchorSignatureEntryCount": anchor_coverage["signatureAnchorEntryCount"],
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
