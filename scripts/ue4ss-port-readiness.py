#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from pathlib import Path


CORE_GROUPS = ("names", "objects", "world", "dispatch")
PACKAGE_GROUP = "package"
REFLECTION_GROUP = "reflection"
TARGET_IMAGE_SUBSTRINGS = (
    "DuneSandbox",
)
LOADER_ALIASES = {
    "linux-client": ("linux-client", "client"),
    "client": ("client", "linux-client"),
    "linux-server": ("linux-server", "server"),
    "server": ("server", "linux-server"),
    "windows-client": ("windows-client", "win-client"),
    "win-client": ("win-client", "windows-client"),
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


def anchor_list_from_count(prefix, count):
    if not isinstance(count, int) or count <= 0:
        return []
    return [f"{prefix}{index}" for index in range(count)]


def normalize_anchor_coverage_sidecar(payload):
    if not isinstance(payload, dict):
        return {}
    if payload.get("schemaVersion") == "dune-ue4ss-port-readiness/v1":
        coverage = payload.get("anchorCoverage")
    elif payload.get("schemaVersion") == "dune-ue4ss-evidence-inventory/v1":
        best = payload.get("best") if isinstance(payload.get("best"), dict) else {}
        coverage = best.get("anchorCoverage")
    else:
        coverage = payload
    if not isinstance(coverage, dict):
        return {}
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


def gate(name, passed, evidence="", blocker=""):
    return {
        "name": name,
        "passed": bool(passed),
        "evidence": evidence,
        "blocker": "" if passed else blocker,
    }


def effective_target_image_substrings(exe_substrings):
    values = [value for value in (exe_substrings or []) if value]
    return values or list(TARGET_IMAGE_SUBSTRINGS)


def is_target_image_path(path, target_image_substrings=None):
    fragments = effective_target_image_substrings(target_image_substrings)
    return any(fragment.lower() in (path or "").lower() for fragment in fragments)


def live_target_image_canary_contract(status):
    groups = {}
    for group_name, keys in LIVE_TARGET_IMAGE_CANARY_CONTRACT_GROUPS.items():
        missing = [key for key in keys if not status.get(key)]
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


def expand_loader_filter(loader_filter):
    expanded = []
    seen = set()
    for loader in loader_filter:
        for candidate in LOADER_ALIASES.get(loader, (loader,)):
            if candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)
    return expanded


def summarize_log(path, loader_filter, pid_filter, exe_substrings):
    scan_mod = import_script("summarize-client-loader-scan.py", "summarize_client_loader_scan")
    ue_mod = import_script("summarize-client-ue-anchors.py", "summarize_client_ue_anchors")
    records = scan_mod.load_records(path)
    effective_pid_filter = list(pid_filter)
    if not effective_pid_filter and not exe_substrings:
        target_pids = sorted(
            {
                record.get("pid", "")
                for record in records
                if record.get("event") == "loaded"
                and record.get("pid")
                and is_target_image_path(record.get("exe", ""), exe_substrings)
            }
        )
        if target_pids:
            effective_pid_filter = target_pids
    scan = scan_mod.summarize(
        records,
        loader_filter=expand_loader_filter(loader_filter),
        pid_filter=effective_pid_filter,
        exe_substrings=exe_substrings,
    )
    ue = ue_mod.summarize(scan, proven_only=True)
    return {
        "path": str(path),
        "scan": scan,
        "ue": ue,
        "targetImageSubstrings": effective_target_image_substrings(exe_substrings),
        "autoTargetPidFilter": effective_pid_filter if effective_pid_filter != list(pid_filter) else [],
    }


def unique_candidates(candidates, key_fields, limit=16):
    unique = []
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = tuple(candidate.get(field, "") for field in key_fields)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


def merge_log_summaries(log_summaries):
    merged_hits = {}
    total_loads = 0
    total_starts = 0
    total_finishes = 0
    total_pointers = 0
    total_mapped_pointers = 0
    total_layouts = 0
    total_readable_layouts = 0
    total_layout_slots = 0
    total_mapped_layout_slots = 0
    total_uobjects = 0
    total_candidate_uobjects = 0
    total_class_mapped_uobjects = 0
    total_ue_reflections = 0
    total_class_mapped_ue_reflections = 0
    total_ue_reflection_slots = 0
    total_mapped_ue_reflection_slots = 0
    total_ue_reflection_fields = 0
    total_candidate_ue_reflection_fields = 0
    total_class_mapped_ue_reflection_fields = 0
    total_ue_reflection_properties = 0
    total_candidate_ue_reflection_properties = 0
    total_readable_ue_reflection_properties = 0
    total_runtime_ue_reflection_properties = 0
    total_runtime_readable_ue_reflection_properties = 0
    total_ue_reflection_values = 0
    total_read_ue_reflection_values = 0
    total_runtime_read_ue_reflection_values = 0
    total_runtime_descriptor_matched_read_ue_reflection_values = 0
    total_ue_function_param_roots = 0
    total_rooted_ue_function_param_roots = 0
    total_ue_function_params = 0
    total_candidate_ue_function_params = 0
    total_ue_function_param_container_children = 0
    total_candidate_ue_function_param_container_children = 0
    total_decoded_ue_function_param_container_children = 0
    total_ue_function_native_identities = 0
    total_promoted_ue_function_native_identities = 0
    total_readable_flag_ue_function_native_identities = 0
    total_runtime_path_ue_function_native_identities = 0
    total_ue4ss_path_ue_function_native_identities = 0
    total_readable_ue_function_params = 0
    total_named_ue_function_params = 0
    ue_function_paths = set()
    ue4ss_function_paths = set()
    active_validation_candidates = []
    total_readable_ue_function_flag_roots = 0
    total_readable_ue_function_flag_params = 0
    ue_function_flag_paths = set()
    ue_function_flag_values = set()
    total_hook_self_tests = 0
    total_passed_hook_self_tests = 0
    total_mod_self_tests = 0
    total_passed_mod_self_tests = 0
    total_lua_self_tests = 0
    total_passed_lua_self_tests = 0
    total_passed_lua_callback_self_tests = 0
    total_passed_lua_api_self_tests = 0
    total_passed_lua_scheduler_api_self_tests = 0
    total_passed_lua_input_command_api_self_tests = 0
    total_passed_lua_object_api_self_tests = 0
    total_lua_reflection_self_tests = 0
    total_passed_lua_reflection_self_tests = 0
    total_raw_set_lua_reflection_self_tests = 0
    total_named_lua_reflection_self_tests = 0
    total_numeric_lua_reflection_self_tests = 0
    total_name_text_lua_reflection_self_tests = 0
    total_array_inner_lua_reflection_self_tests = 0
    total_enum_lua_reflection_self_tests = 0
    total_container_lua_reflection_self_tests = 0
    total_import_text_lua_reflection_self_tests = 0
    total_export_text_lua_reflection_self_tests = 0
    total_property_metadata_lua_reflection_self_tests = 0
    total_descriptor_value_lua_reflection_self_tests = 0
    total_reflection_for_each_property_lua_reflection_self_tests = 0
    total_runtime_reflection_for_each_property_lua_reflection_self_tests = 0
    total_self_test_reflection_for_each_property_lua_reflection_self_tests = 0
    total_typed_live_descriptor_lua_reflection_self_tests = 0
    total_runtime_typed_live_descriptor_lua_reflection_self_tests = 0
    total_self_test_typed_live_descriptor_lua_reflection_self_tests = 0
    total_typed_live_descriptor_value_lua_reflection_self_tests = 0
    total_runtime_typed_live_descriptor_value_lua_reflection_self_tests = 0
    total_self_test_typed_live_descriptor_value_lua_reflection_self_tests = 0
    total_typed_live_descriptor_value_set_lua_reflection_self_tests = 0
    total_runtime_typed_live_descriptor_value_set_lua_reflection_self_tests = 0
    total_self_test_typed_live_descriptor_value_set_lua_reflection_self_tests = 0
    total_live_descriptor_value_lua_reflection_self_tests = 0
    total_runtime_live_descriptor_value_lua_reflection_self_tests = 0
    total_self_test_live_descriptor_value_lua_reflection_self_tests = 0
    total_lua_process_event_self_tests = 0
    total_passed_lua_process_event_self_tests = 0
    total_lua_process_event_param_accessor_self_tests = 0
    total_lua_process_event_function_param_method_self_tests = 0
    total_lua_process_event_function_param_lookup_method_self_tests = 0
    total_lua_process_event_function_param_iteration_method_self_tests = 0
    total_lua_process_event_container_alias_method_self_tests = 0
    total_lua_process_event_container_storage_layout_method_self_tests = 0
    total_lua_process_event_scalar_param_accessor_self_tests = 0
    total_lua_process_event_name_string_param_accessor_self_tests = 0
    total_lua_process_event_struct_param_accessor_self_tests = 0
    total_lua_process_event_enum_param_accessor_self_tests = 0
    total_lua_process_event_object_param_accessor_self_tests = 0
    total_lua_process_event_bool_param_accessor_self_tests = 0
    total_routed_lua_process_event_self_tests = 0
    total_lua_process_event_path_exact_matches = 0
    total_lua_process_event_path_alias_matches = 0
    total_lua_mod_scripts = 0
    total_passed_lua_mod_scripts = 0
    total_lua_mod_dispatch_self_tests = 0
    total_passed_lua_mod_dispatch_self_tests = 0
    total_lua_mod_finishes = 0
    total_passed_lua_mod_finishes = 0
    total_lua_object_api_mod_finishes = 0
    total_lua_load_asset_backend_state_mod_finishes = 0
    total_lua_load_asset_backend_anchor_mod_finishes = 0
    total_lua_load_asset_package_bridge_state_mod_finishes = 0
    total_lua_load_asset_package_native_invoke_mod_finishes = 0
    total_lua_load_asset_package_abi_state_events = 0
    total_lua_load_asset_package_string_bridge_events = 0
    total_lua_load_asset_package_native_buffer_events = 0
    total_lua_load_asset_package_tchar_buffer_events = 0
    total_lua_load_asset_package_tchar_verification_events = 0
    total_lua_load_asset_package_call_frame_events = 0
    total_lua_load_asset_package_call_frame_verification_events = 0
    total_lua_load_asset_package_crash_guard_events = 0
    total_lua_load_asset_package_guarded_call_events = 0
    total_lua_load_asset_package_return_validation_events = 0
    total_lua_load_asset_package_native_call_adapter_events = 0
    total_lua_load_asset_package_invocation_descriptor_events = 0
    total_lua_load_asset_package_native_executor_events = 0
    total_lua_load_asset_package_native_executor_ready_events = 0
    total_lua_load_asset_package_native_executor_target_ready_events = 0
    total_lua_load_asset_package_native_invoked_events = 0
    total_lua_load_class_package_abi_state_events = 0
    total_lua_load_class_package_call_frame_verification_events = 0
    total_lua_load_class_package_native_executor_events = 0
    total_lua_load_class_package_native_executor_ready_events = 0
    total_lua_load_class_package_native_invoked_events = 0
    total_lua_static_construct_object_native_executor_states = 0
    total_lua_static_construct_object_native_executor_ready_states = 0
    total_lua_static_construct_object_native_invokes = 0
    total_lua_static_construct_object_native_invoked = 0
    total_lua_load_asset_package_preflight_mod_finishes = 0
    total_lua_load_asset_package_mod_finishes = 0
    total_lua_function_iteration_mod_finishes = 0
    total_lua_function_iteration_checks = 0
    total_passed_lua_function_iteration_checks = 0
    total_runtime_lua_function_iteration_checks = 0
    total_self_test_lua_function_iteration_checks = 0
    total_lua_scheduler_api_mod_finishes = 0
    total_lua_input_command_api_mod_finishes = 0
    total_lua_process_console_exec_hook_mod_finishes = 0
    total_lua_local_player_exec_hook_mod_finishes = 0
    total_lua_call_function_hook_mod_finishes = 0
    total_lua_call_function_structured_args_mod_finishes = 0
    total_lua_call_function_native_invoke_mod_finishes = 0
    total_lua_call_function_native_invoke_self_tests = 0
    total_lua_call_function_native_invoke_preflights = 0
    total_lua_call_function_native_executor_states = 0
    total_lua_call_function_native_executor_ready_states = 0
    total_lua_call_function_native_invoke_non_self_test_gates = 0
    total_lua_call_function_native_invoke_non_self_test_invocations = 0
    total_lua_process_event_compat_mod_finishes = 0
    total_lua_process_event_bridge_state_mod_finishes = 0
    total_lua_process_event_native_invoke_mod_finishes = 0
    total_lua_process_event_native_invoke_self_tests = 0
    total_lua_process_event_native_invoke_descriptor_preflights = 0
    total_lua_process_event_native_executor_states = 0
    total_lua_process_event_native_executor_ready_states = 0
    total_lua_process_event_native_invoke_non_self_test_gates = 0
    total_lua_process_event_native_invoke_non_self_test_invocations = 0
    total_lua_process_event_params_buffers = 0
    total_lua_lifecycle_hook_mod_finishes = 0
    total_lua_custom_event_mod_finishes = 0
    total_lua_load_map_hook_mod_finishes = 0
    total_lua_begin_play_hook_mod_finishes = 0
    total_lua_init_game_state_hook_mod_finishes = 0
    total_lua_notify_on_new_object_mod_finishes = 0
    total_lua_synthetic_outer_mod_finishes = 0
    total_lua_object_outer_chains = 0
    total_resolved_lua_object_outer_chains = 0
    total_lua_object_outer_chain_identities = 0
    total_lua_global_runtime_helper_checks = 0
    total_passed_lua_global_runtime_helper_checks = 0
    total_promoted_world_lua_global_runtime_helper_checks = 0
    total_promoted_engine_lua_global_runtime_helper_checks = 0
    total_lua_world_context_mod_finishes = 0
    total_lua_class_default_object_mod_finishes = 0
    total_lua_level_mod_finishes = 0
    total_lua_object_registry = 0
    total_added_lua_object_registry = 0
    total_lua_object_registry_checks = 0
    total_passed_lua_object_registry_checks = 0
    total_lua_function_registry_checks = 0
    total_passed_lua_function_registry_checks = 0
    total_runtime_lua_function_registry_checks = 0
    total_self_test_lua_function_registry_checks = 0
    total_ue_lua_object_registry = 0
    total_runtime_ue_lua_object_registry = 0
    total_self_test_ue_lua_object_registry = 0
    total_object_array_lua_object_registry = 0
    total_runtime_object_array_lua_object_registry = 0
    total_self_test_object_array_lua_object_registry = 0
    total_decoded_lua_object_alias_registry = 0
    total_runtime_decoded_lua_object_alias_registry = 0
    total_self_test_decoded_lua_object_alias_registry = 0
    total_skipped_decoded_lua_object_alias_registry = 0
    total_ue_object_arrays = 0
    total_ue_object_array_shapes = 0
    total_plausible_ue_object_array_shapes = 0
    total_implausible_ue_object_array_shapes = 0
    total_finished_ue_object_arrays = 0
    total_ue_object_array_items = 0
    total_ue_object_native_identities = 0
    total_promoted_ue_object_native_identities = 0
    total_decoded_name_ue_object_native_identities = 0
    total_decoded_class_name_ue_object_native_identities = 0
    total_internal_flag_ue_object_array_items = 0
    total_nonzero_internal_flag_ue_object_array_items = 0
    total_ue_fnames = 0
    total_decoded_ue_fnames = 0
    total_ue_anchor_signatures = 0
    total_resolved_ue_anchor_signatures = 0
    total_ue_anchor_signature_status_counts = {}
    total_ue_anchor_group_counts = {}
    total_mapped_ue_anchor_group_counts = {}
    total_ue_anchor_signature_group_counts = {}
    total_resolved_ue_anchor_signature_group_counts = {}
    total_ue_runtime_discovery_starts = 0
    total_ue_runtime_discovery_finishes = 0
    total_ue_runtime_discovery_candidates = 0
    total_ue_runtime_discovery_candidate_name_counts = {}
    total_ue_runtime_discovery_candidate_image_counts = {}
    total_ue_runtime_discovery_candidate_locations = []
    total_ue_runtime_discovery_validated_locations = []
    total_ue_runtime_discovery_target_writable_missing = 0
    total_ue_runtime_discovery_status_counts = {}
    total_ue_runtime_discovery_failure_counts = {}
    total_ue_runtime_discovery_coverage = {
        "targetWritableImageCount": 0,
        "oversizedImageCount": 0,
        "scannedSlots": 0,
        "fnameProbes": 0,
        "objectArrayProbes": 0,
        "fnameHits": 0,
        "objectArrayHits": 0,
    }
    ue_runtime_discovery_promoted_names = set()
    ue_runtime_discovery_validated_names = set()
    ue_runtime_root_validation_names = set()
    total_ue_runtime_root_validated_by = {}
    total_ue_runtime_discovery_ready_scans = 0
    total_ue_runtime_root_validation_ready_scans = 0
    total_ue_process_event_hooks = 0
    total_passed_ue_process_event_hooks = 0
    total_non_self_test_passed_ue_process_event_hooks = 0
    total_proven_target_passed_ue_process_event_hooks = 0
    total_ue_call_function_hooks = 0
    total_passed_ue_call_function_hooks = 0
    total_non_self_test_passed_ue_call_function_hooks = 0
    total_proven_target_passed_ue_call_function_hooks = 0
    total_ue_call_function_live_hooks = 0
    total_installed_ue_call_function_live_hooks = 0
    total_routed_ue_call_function_live_lua_hooks = 0
    total_handled_ue_call_function_live_lua_hooks = 0
    total_non_self_test_installed_ue_call_function_live_hooks = 0
    total_proven_target_installed_ue_call_function_live_hooks = 0
    total_proven_target_routed_ue_call_function_live_lua_hooks = 0
    total_proven_target_handled_ue_call_function_live_lua_hooks = 0
    total_ue_call_function_active_validations = 0
    total_invoked_ue_call_function_active_validations = 0
    total_original_ue_call_function_active_validations = 0
    total_target_entry_ue_call_function_active_validations = 0
    total_ue_process_event_live_hooks = 0
    total_installed_ue_process_event_live_hooks = 0
    total_non_self_test_installed_ue_process_event_live_hooks = 0
    total_proven_target_installed_ue_process_event_live_hooks = 0
    total_ue_process_event_active_validations = 0
    total_invoked_ue_process_event_active_validations = 0
    total_original_ue_process_event_active_validations = 0
    total_suppressed_ue_process_event_active_validations = 0
    total_target_entry_ue_process_event_active_validations = 0
    total_suppressed_target_entry_ue_process_event_active_validations = 0
    total_synthetic_target_entry_ue_process_event_active_validations = 0
    total_descriptor_buffer_ue_process_event_active_validations = 0
    total_ue_process_event_live_contexts = 0
    total_resolved_ue_process_event_live_contexts = 0
    total_matched_ue_process_event_live_contexts = 0
    total_runtime_matched_ue_process_event_live_contexts = 0
    total_self_test_provenance_ue_process_event_live_contexts = 0
    total_runtime_provenance_ue_process_event_live_contexts = 0
    total_ue_process_event_live_registry_contexts = 0
    total_resolved_ue_process_event_live_registry_contexts = 0
    total_native_identity_ue_process_event_live_registry_contexts = 0
    total_matched_ue_process_event_live_registry_contexts = 0
    total_runtime_matched_ue_process_event_live_registry_contexts = 0
    total_self_test_provenance_ue_process_event_live_registry_contexts = 0
    total_runtime_provenance_ue_process_event_live_registry_contexts = 0
    total_ue_process_event_live_params = 0
    total_read_ue_process_event_live_params = 0
    total_raw_ue_process_event_live_params = 0
    total_container_ue_process_event_live_params = 0
    total_sampled_container_ue_process_event_live_params = 0
    total_array_container_ue_process_event_live_params = 0
    total_set_container_ue_process_event_live_params = 0
    total_map_container_ue_process_event_live_params = 0
    total_set_map_container_ue_process_event_live_params = 0
    total_runtime_read_ue_process_event_live_params = 0
    total_runtime_raw_ue_process_event_live_params = 0
    total_runtime_container_ue_process_event_live_params = 0
    total_runtime_sampled_container_ue_process_event_live_params = 0
    total_runtime_array_container_ue_process_event_live_params = 0
    total_runtime_set_container_ue_process_event_live_params = 0
    total_runtime_map_container_ue_process_event_live_params = 0
    total_runtime_set_map_container_ue_process_event_live_params = 0
    total_ue_process_event_lua_context_handles = 0
    total_ue_process_event_live_lua_param_accessors = 0
    total_ue_process_event_live_lua_function_param_methods = 0
    total_ue_process_event_live_lua_function_param_lookup_methods = 0
    total_ue_process_event_live_lua_function_param_iteration_methods = 0
    total_ue_process_event_live_lua_container_alias_methods = 0
    total_ue_process_event_live_lua_container_storage_layout_methods = 0
    total_ue_process_event_live_lua_scalar_param_accessors = 0
    total_ue_process_event_live_lua_name_string_param_accessors = 0
    total_ue_process_event_live_lua_struct_param_accessors = 0
    total_ue_process_event_live_lua_enum_param_accessors = 0
    total_ue_process_event_live_lua_object_param_accessors = 0
    total_ue_process_event_live_lua_bool_param_accessors = 0
    total_routed_ue_process_event_live_lua_hooks = 0
    total_restored_ue_process_event_live_hooks = 0
    total_ue_process_event_live_hook_status_counts = {}
    total_ue_call_function_live_hook_status_counts = {}
    total_ue_process_event_dispatch_self_tests = 0
    total_armed_ue_process_event_dispatch_self_tests = 0
    total_ue_process_event_live_lua_dispatches = 0
    total_armed_ue_process_event_live_lua_dispatches = 0
    total_multi_hook_ue_process_event_live_lua_dispatches = 0
    total_matched_ue_process_event_live_lua_dispatches = 0
    total_closed_ue_process_event_live_lua_dispatches = 0
    total_closed_matched_ue_process_event_live_lua_dispatches = 0
    total_ue_process_event_live_lua_path_exact_matches = 0
    total_ue_process_event_live_lua_path_alias_matches = 0
    total_ue_process_event_live_lua_dispatch_status_counts = {}
    loaders = set()
    pids = set()
    loaded_exes = set()
    modules = set()
    target_image_substrings = []
    seen_target_image_substrings = set()
    auto_target_pid_filters = set()
    for summary in log_summaries:
        scan = summary["scan"]
        for fragment in summary.get("targetImageSubstrings", []) or []:
            if fragment and fragment not in seen_target_image_substrings:
                target_image_substrings.append(fragment)
                seen_target_image_substrings.add(fragment)
        auto_target_pid_filters.update(summary.get("autoTargetPidFilter", []) or [])
        total_loads += scan.get("loadCount", 0)
        total_starts += scan.get("scanStartCount", 0)
        total_finishes += scan.get("scanFinishCount", 0)
        total_pointers += scan.get("uePointerCount", 0)
        total_mapped_pointers += scan.get("mappedUePointerCount", 0)
        total_layouts += scan.get("ueLayoutCount", 0)
        total_readable_layouts += scan.get("readableUeLayoutCount", 0)
        total_layout_slots += scan.get("ueLayoutSlotCount", 0)
        total_mapped_layout_slots += scan.get("mappedUeLayoutSlotCount", 0)
        total_uobjects += scan.get("ueUObjectCount", 0)
        total_candidate_uobjects += scan.get("candidateUeUObjectCount", 0)
        total_class_mapped_uobjects += scan.get("classMappedUeUObjectCount", 0)
        total_ue_reflections += scan.get("ueReflectionCount", 0)
        total_class_mapped_ue_reflections += scan.get("classMappedUeReflectionCount", 0)
        total_ue_reflection_slots += scan.get("ueReflectionSlotCount", 0)
        total_mapped_ue_reflection_slots += scan.get("mappedUeReflectionSlotCount", 0)
        total_ue_reflection_fields += scan.get("ueReflectionFieldCount", 0)
        total_candidate_ue_reflection_fields += scan.get("candidateUeReflectionFieldCount", 0)
        total_class_mapped_ue_reflection_fields += scan.get("classMappedUeReflectionFieldCount", 0)
        total_ue_reflection_properties += scan.get("ueReflectionPropertyCount", 0)
        total_candidate_ue_reflection_properties += scan.get("candidateUeReflectionPropertyCount", 0)
        total_readable_ue_reflection_properties += scan.get("readableUeReflectionPropertyCount", 0)
        total_runtime_ue_reflection_properties += scan.get("runtimeUeReflectionPropertyCount", 0)
        total_runtime_readable_ue_reflection_properties += scan.get("runtimeReadableUeReflectionPropertyCount", 0)
        total_ue_reflection_values += scan.get("ueReflectionValueCount", 0)
        total_read_ue_reflection_values += scan.get("readUeReflectionValueCount", 0)
        total_runtime_read_ue_reflection_values += scan.get("runtimeReadUeReflectionValueCount", 0)
        total_runtime_descriptor_matched_read_ue_reflection_values += scan.get(
            "runtimeDescriptorMatchedReadUeReflectionValueCount", 0
        )
        total_ue_function_param_roots += scan.get("ueFunctionParamRootCount", 0)
        total_rooted_ue_function_param_roots += scan.get("rootedUeFunctionParamRootCount", 0)
        total_ue_function_params += scan.get("ueFunctionParamCount", 0)
        total_candidate_ue_function_params += scan.get("candidateUeFunctionParamCount", 0)
        total_ue_function_param_container_children += scan.get("ueFunctionParamContainerChildCount", 0)
        total_candidate_ue_function_param_container_children += scan.get(
            "candidateUeFunctionParamContainerChildCount", 0
        )
        total_decoded_ue_function_param_container_children += scan.get(
            "decodedUeFunctionParamContainerChildCount", 0
        )
        total_ue_function_native_identities += scan.get("ueFunctionNativeIdentityCount", 0)
        total_promoted_ue_function_native_identities += scan.get("promotedUeFunctionNativeIdentityCount", 0)
        total_readable_flag_ue_function_native_identities += scan.get("readableFlagUeFunctionNativeIdentityCount", 0)
        total_runtime_path_ue_function_native_identities += scan.get("runtimePathUeFunctionNativeIdentityCount", 0)
        total_ue4ss_path_ue_function_native_identities += scan.get("ue4ssPathUeFunctionNativeIdentityCount", 0)
        total_readable_ue_function_params += scan.get("readableUeFunctionParamCount", 0)
        total_named_ue_function_params += scan.get("namedUeFunctionParamCount", 0)
        ue_function_paths.update(path for path in scan.get("ueFunctionPaths", []) if path)
        ue4ss_function_paths.update(path for path in scan.get("ue4ssFunctionPaths", []) if path)
        active_validation_candidates.extend(scan.get("activeValidationCandidates", []) or [])
        total_readable_ue_function_flag_roots += scan.get("readableUeFunctionFlagRootCount", 0)
        total_readable_ue_function_flag_params += scan.get("readableUeFunctionFlagParamCount", 0)
        ue_function_flag_paths.update(path for path in scan.get("ueFunctionFlagPaths", []) if path)
        ue_function_flag_values.update(value for value in scan.get("ueFunctionFlagValues", []) if value)
        total_hook_self_tests += scan.get("hookSelfTestCount", 0)
        total_passed_hook_self_tests += scan.get("passedHookSelfTestCount", 0)
        total_mod_self_tests += scan.get("modSelfTestCount", 0)
        total_passed_mod_self_tests += scan.get("passedModSelfTestCount", 0)
        total_lua_self_tests += scan.get("luaSelfTestCount", 0)
        total_passed_lua_self_tests += scan.get("passedLuaSelfTestCount", 0)
        total_passed_lua_callback_self_tests += scan.get("passedLuaCallbackSelfTestCount", 0)
        total_passed_lua_api_self_tests += scan.get("passedLuaApiSelfTestCount", 0)
        total_passed_lua_scheduler_api_self_tests += scan.get("passedLuaSchedulerApiSelfTestCount", 0)
        total_passed_lua_input_command_api_self_tests += scan.get("passedLuaInputCommandApiSelfTestCount", 0)
        total_passed_lua_object_api_self_tests += scan.get("passedLuaObjectApiSelfTestCount", 0)
        total_lua_reflection_self_tests += scan.get("luaReflectionSelfTestCount", 0)
        total_passed_lua_reflection_self_tests += scan.get("passedLuaReflectionSelfTestCount", 0)
        total_raw_set_lua_reflection_self_tests += scan.get("rawSetLuaReflectionSelfTestCount", 0)
        total_named_lua_reflection_self_tests += scan.get("namedLuaReflectionSelfTestCount", 0)
        total_numeric_lua_reflection_self_tests += scan.get("numericLuaReflectionSelfTestCount", 0)
        total_name_text_lua_reflection_self_tests += scan.get("nameTextLuaReflectionSelfTestCount", 0)
        total_array_inner_lua_reflection_self_tests += scan.get("arrayInnerLuaReflectionSelfTestCount", 0)
        total_enum_lua_reflection_self_tests += scan.get("enumLuaReflectionSelfTestCount", 0)
        total_container_lua_reflection_self_tests += scan.get("containerLuaReflectionSelfTestCount", 0)
        total_import_text_lua_reflection_self_tests += scan.get("importTextLuaReflectionSelfTestCount", 0)
        total_export_text_lua_reflection_self_tests += scan.get("exportTextLuaReflectionSelfTestCount", 0)
        total_property_metadata_lua_reflection_self_tests += scan.get("propertyMetadataLuaReflectionSelfTestCount", 0)
        total_descriptor_value_lua_reflection_self_tests += scan.get("descriptorValueLuaReflectionSelfTestCount", 0)
        total_reflection_for_each_property_lua_reflection_self_tests += scan.get(
            "reflectionForEachPropertyLuaReflectionSelfTestCount", 0
        )
        total_runtime_reflection_for_each_property_lua_reflection_self_tests += scan.get(
            "runtimeReflectionForEachPropertyLuaReflectionSelfTestCount", 0
        )
        total_self_test_reflection_for_each_property_lua_reflection_self_tests += scan.get(
            "selfTestReflectionForEachPropertyLuaReflectionSelfTestCount", 0
        )
        total_typed_live_descriptor_lua_reflection_self_tests += scan.get(
            "typedLiveDescriptorLuaReflectionSelfTestCount", 0
        )
        total_runtime_typed_live_descriptor_lua_reflection_self_tests += scan.get(
            "runtimeTypedLiveDescriptorLuaReflectionSelfTestCount", 0
        )
        total_self_test_typed_live_descriptor_lua_reflection_self_tests += scan.get(
            "selfTestTypedLiveDescriptorLuaReflectionSelfTestCount", 0
        )
        total_typed_live_descriptor_value_lua_reflection_self_tests += scan.get(
            "typedLiveDescriptorValueLuaReflectionSelfTestCount", 0
        )
        total_runtime_typed_live_descriptor_value_lua_reflection_self_tests += scan.get(
            "runtimeTypedLiveDescriptorValueLuaReflectionSelfTestCount", 0
        )
        total_self_test_typed_live_descriptor_value_lua_reflection_self_tests += scan.get(
            "selfTestTypedLiveDescriptorValueLuaReflectionSelfTestCount", 0
        )
        total_typed_live_descriptor_value_set_lua_reflection_self_tests += scan.get(
            "typedLiveDescriptorValueSetLuaReflectionSelfTestCount", 0
        )
        total_runtime_typed_live_descriptor_value_set_lua_reflection_self_tests += scan.get(
            "runtimeTypedLiveDescriptorValueSetLuaReflectionSelfTestCount", 0
        )
        total_self_test_typed_live_descriptor_value_set_lua_reflection_self_tests += scan.get(
            "selfTestTypedLiveDescriptorValueSetLuaReflectionSelfTestCount", 0
        )
        total_live_descriptor_value_lua_reflection_self_tests += scan.get(
            "liveDescriptorValueLuaReflectionSelfTestCount", 0
        )
        total_runtime_live_descriptor_value_lua_reflection_self_tests += scan.get(
            "runtimeLiveDescriptorValueLuaReflectionSelfTestCount", 0
        )
        total_self_test_live_descriptor_value_lua_reflection_self_tests += scan.get(
            "selfTestLiveDescriptorValueLuaReflectionSelfTestCount", 0
        )
        total_lua_process_event_self_tests += scan.get("luaProcessEventSelfTestCount", 0)
        total_passed_lua_process_event_self_tests += scan.get("passedLuaProcessEventSelfTestCount", 0)
        total_lua_process_event_param_accessor_self_tests += scan.get("luaProcessEventParamAccessorSelfTestCount", 0)
        total_lua_process_event_function_param_method_self_tests += scan.get("luaProcessEventFunctionParamMethodSelfTestCount", 0)
        total_lua_process_event_function_param_lookup_method_self_tests += scan.get("luaProcessEventFunctionParamLookupMethodSelfTestCount", 0)
        total_lua_process_event_function_param_iteration_method_self_tests += scan.get("luaProcessEventFunctionParamIterationMethodSelfTestCount", 0)
        total_lua_process_event_container_alias_method_self_tests += scan.get("luaProcessEventContainerAliasMethodSelfTestCount", 0)
        total_lua_process_event_container_storage_layout_method_self_tests += scan.get("luaProcessEventContainerStorageLayoutMethodSelfTestCount", 0)
        total_lua_process_event_scalar_param_accessor_self_tests += scan.get("luaProcessEventScalarParamAccessorSelfTestCount", 0)
        total_lua_process_event_name_string_param_accessor_self_tests += scan.get("luaProcessEventNameStringParamAccessorSelfTestCount", 0)
        total_lua_process_event_struct_param_accessor_self_tests += scan.get("luaProcessEventStructParamAccessorSelfTestCount", 0)
        total_lua_process_event_enum_param_accessor_self_tests += scan.get("luaProcessEventEnumParamAccessorSelfTestCount", 0)
        total_lua_process_event_object_param_accessor_self_tests += scan.get("luaProcessEventObjectParamAccessorSelfTestCount", 0)
        total_lua_process_event_bool_param_accessor_self_tests += scan.get("luaProcessEventBoolParamAccessorSelfTestCount", 0)
        total_routed_lua_process_event_self_tests += scan.get("routedLuaProcessEventSelfTestCount", 0)
        total_lua_process_event_path_exact_matches += scan.get("luaProcessEventPathExactMatchCount", 0)
        total_lua_process_event_path_alias_matches += scan.get("luaProcessEventPathAliasMatchCount", 0)
        total_lua_mod_scripts += scan.get("luaModScriptCount", 0)
        total_passed_lua_mod_scripts += scan.get("passedLuaModScriptCount", 0)
        total_lua_mod_dispatch_self_tests += scan.get("luaModDispatchSelfTestCount", 0)
        total_passed_lua_mod_dispatch_self_tests += scan.get("passedLuaModDispatchSelfTestCount", 0)
        total_lua_mod_finishes += scan.get("luaModFinishCount", 0)
        total_passed_lua_mod_finishes += scan.get("passedLuaModFinishCount", 0)
        total_lua_object_api_mod_finishes += scan.get("luaObjectApiModFinishCount", 0)
        total_lua_load_asset_backend_state_mod_finishes += scan.get("luaLoadAssetBackendStateModFinishCount", 0)
        total_lua_load_asset_backend_anchor_mod_finishes += scan.get("luaLoadAssetBackendAnchorModFinishCount", 0)
        total_lua_load_asset_package_bridge_state_mod_finishes += scan.get("luaLoadAssetPackageBridgeStateModFinishCount", 0)
        total_lua_load_asset_package_native_invoke_mod_finishes += scan.get("luaLoadAssetPackageNativeInvokeModFinishCount", 0)
        total_lua_load_asset_package_abi_state_events += scan.get("luaLoadAssetPackageAbiStateEventCount", 0)
        total_lua_load_asset_package_string_bridge_events += scan.get("luaLoadAssetPackageStringBridgeEventCount", 0)
        total_lua_load_asset_package_native_buffer_events += scan.get("luaLoadAssetPackageNativeBufferEventCount", 0)
        total_lua_load_asset_package_tchar_buffer_events += scan.get("luaLoadAssetPackageTCharBufferEventCount", 0)
        total_lua_load_asset_package_tchar_verification_events += scan.get("luaLoadAssetPackageTCharVerificationEventCount", 0)
        total_lua_load_asset_package_call_frame_events += scan.get("luaLoadAssetPackageCallFrameEventCount", 0)
        total_lua_load_asset_package_call_frame_verification_events += scan.get(
            "luaLoadAssetPackageCallFrameVerificationEventCount", 0
        )
        total_lua_load_asset_package_crash_guard_events += scan.get(
            "luaLoadAssetPackageCrashGuardEventCount", 0
        )
        total_lua_load_asset_package_guarded_call_events += scan.get(
            "luaLoadAssetPackageGuardedCallEventCount", 0
        )
        total_lua_load_asset_package_return_validation_events += scan.get(
            "luaLoadAssetPackageReturnValidationEventCount", 0
        )
        total_lua_load_asset_package_native_call_adapter_events += scan.get(
            "luaLoadAssetPackageNativeCallAdapterEventCount", 0
        )
        total_lua_load_asset_package_invocation_descriptor_events += scan.get(
            "luaLoadAssetPackageInvocationDescriptorEventCount", 0
        )
        total_lua_load_asset_package_native_executor_events += scan.get(
            "luaLoadAssetPackageNativeExecutorEventCount", 0
        )
        total_lua_load_asset_package_native_executor_ready_events += scan.get(
            "luaLoadAssetPackageNativeExecutorReadyEventCount", 0
        )
        total_lua_load_asset_package_native_executor_target_ready_events += scan.get(
            "luaLoadAssetPackageNativeExecutorTargetReadyEventCount", 0
        )
        total_lua_load_asset_package_native_invoked_events += scan.get(
            "luaLoadAssetPackageNativeInvokedEventCount", 0
        )
        total_lua_load_class_package_abi_state_events += scan.get("luaLoadClassPackageAbiStateEventCount", 0)
        total_lua_load_class_package_call_frame_verification_events += scan.get(
            "luaLoadClassPackageCallFrameVerificationEventCount", 0
        )
        total_lua_load_class_package_native_executor_events += scan.get(
            "luaLoadClassPackageNativeExecutorEventCount", 0
        )
        total_lua_load_class_package_native_executor_ready_events += scan.get(
            "luaLoadClassPackageNativeExecutorReadyEventCount", 0
        )
        total_lua_load_class_package_native_invoked_events += scan.get(
            "luaLoadClassPackageNativeInvokedEventCount", 0
        )
        total_lua_static_construct_object_native_executor_states += scan.get(
            "luaStaticConstructObjectNativeExecutorStateCount", 0
        )
        total_lua_static_construct_object_native_executor_ready_states += scan.get(
            "luaStaticConstructObjectNativeExecutorReadyStateCount", 0
        )
        total_lua_static_construct_object_native_invokes += scan.get(
            "luaStaticConstructObjectNativeInvokeCount", 0
        )
        total_lua_static_construct_object_native_invoked += scan.get(
            "luaStaticConstructObjectNativeInvokedCount", 0
        )
        total_lua_load_asset_package_preflight_mod_finishes += scan.get("luaLoadAssetPackagePreflightModFinishCount", 0)
        total_lua_load_asset_package_mod_finishes += scan.get("luaLoadAssetPackageModFinishCount", 0)
        total_lua_function_iteration_mod_finishes += scan.get("luaFunctionIterationModFinishCount", 0)
        total_lua_function_iteration_checks += scan.get("luaFunctionIterationCheckCount", 0)
        total_passed_lua_function_iteration_checks += scan.get("passedLuaFunctionIterationCheckCount", 0)
        total_runtime_lua_function_iteration_checks += scan.get("runtimeLuaFunctionIterationCheckCount", 0)
        total_self_test_lua_function_iteration_checks += scan.get("selfTestLuaFunctionIterationCheckCount", 0)
        total_lua_scheduler_api_mod_finishes += scan.get("luaSchedulerApiModFinishCount", 0)
        total_lua_input_command_api_mod_finishes += scan.get("luaInputCommandApiModFinishCount", 0)
        total_lua_process_console_exec_hook_mod_finishes += scan.get("luaProcessConsoleExecHookModFinishCount", 0)
        total_lua_local_player_exec_hook_mod_finishes += scan.get("luaLocalPlayerExecHookModFinishCount", 0)
        total_lua_call_function_hook_mod_finishes += scan.get("luaCallFunctionHookModFinishCount", 0)
        total_lua_call_function_structured_args_mod_finishes += scan.get(
            "luaCallFunctionStructuredArgsModFinishCount", 0
        )
        total_lua_call_function_native_invoke_mod_finishes += scan.get(
            "luaCallFunctionNativeInvokeModFinishCount", 0
        )
        total_lua_call_function_native_invoke_self_tests += scan.get(
            "luaCallFunctionNativeInvokeSelfTestCount", 0
        )
        total_lua_call_function_native_invoke_preflights += scan.get(
            "luaCallFunctionNativeInvokePreflightCount", 0
        )
        total_lua_call_function_native_executor_states += scan.get(
            "luaCallFunctionNativeExecutorStateCount", 0
        )
        total_lua_call_function_native_executor_ready_states += scan.get(
            "luaCallFunctionNativeExecutorReadyStateCount", 0
        )
        total_lua_call_function_native_invoke_non_self_test_gates += scan.get(
            "luaCallFunctionNativeInvokeNonSelfTestGateCount", 0
        )
        total_lua_call_function_native_invoke_non_self_test_invocations += scan.get(
            "luaCallFunctionNativeInvokeNonSelfTestInvokedCount", 0
        )
        total_lua_process_event_compat_mod_finishes += scan.get("luaProcessEventCompatModFinishCount", 0)
        total_lua_process_event_bridge_state_mod_finishes += scan.get(
            "luaProcessEventBridgeStateModFinishCount", 0
        )
        total_lua_process_event_native_invoke_mod_finishes += scan.get(
            "luaProcessEventNativeInvokeModFinishCount", 0
        )
        total_lua_process_event_native_invoke_self_tests += scan.get(
            "luaProcessEventNativeInvokeSelfTestCount", 0
        )
        total_lua_process_event_native_invoke_descriptor_preflights += scan.get(
            "luaProcessEventNativeInvokeDescriptorPreflightCount", 0
        )
        total_lua_process_event_native_executor_states += scan.get(
            "luaProcessEventNativeExecutorStateCount", 0
        )
        total_lua_process_event_native_executor_ready_states += scan.get(
            "luaProcessEventNativeExecutorReadyStateCount", 0
        )
        total_lua_process_event_native_invoke_non_self_test_gates += scan.get(
            "luaProcessEventNativeInvokeNonSelfTestGateCount", 0
        )
        total_lua_process_event_native_invoke_non_self_test_invocations += scan.get(
            "luaProcessEventNativeInvokeNonSelfTestInvokedCount", 0
        )
        total_lua_process_event_params_buffers += scan.get("luaProcessEventParamsBufferCount", 0)
        total_lua_lifecycle_hook_mod_finishes += scan.get("luaLifecycleHookModFinishCount", 0)
        total_lua_custom_event_mod_finishes += scan.get("luaCustomEventModFinishCount", 0)
        total_lua_load_map_hook_mod_finishes += scan.get("luaLoadMapHookModFinishCount", 0)
        total_lua_begin_play_hook_mod_finishes += scan.get("luaBeginPlayHookModFinishCount", 0)
        total_lua_init_game_state_hook_mod_finishes += scan.get("luaInitGameStateHookModFinishCount", 0)
        total_lua_notify_on_new_object_mod_finishes += scan.get("luaNotifyOnNewObjectModFinishCount", 0)
        total_lua_synthetic_outer_mod_finishes += scan.get("luaSyntheticOuterModFinishCount", 0)
        total_lua_object_outer_chains += scan.get("luaObjectOuterChainCount", 0)
        total_resolved_lua_object_outer_chains += scan.get("resolvedLuaObjectOuterChainCount", 0)
        total_lua_object_outer_chain_identities += scan.get("luaObjectOuterChainIdentityCount", 0)
        total_lua_global_runtime_helper_checks += scan.get("luaGlobalRuntimeHelperCheckCount", 0)
        total_passed_lua_global_runtime_helper_checks += scan.get("passedLuaGlobalRuntimeHelperCheckCount", 0)
        total_promoted_world_lua_global_runtime_helper_checks += scan.get(
            "promotedWorldLuaGlobalRuntimeHelperCheckCount", 0
        )
        total_promoted_engine_lua_global_runtime_helper_checks += scan.get(
            "promotedEngineLuaGlobalRuntimeHelperCheckCount", 0
        )
        total_lua_world_context_mod_finishes += scan.get("luaWorldContextModFinishCount", 0)
        total_lua_class_default_object_mod_finishes += scan.get("luaClassDefaultObjectModFinishCount", 0)
        total_lua_level_mod_finishes += scan.get("luaLevelModFinishCount", 0)
        total_lua_object_registry += scan.get("luaObjectRegistryCount", 0)
        total_added_lua_object_registry += scan.get("addedLuaObjectRegistryCount", 0)
        total_lua_object_registry_checks += scan.get("luaObjectRegistryCheckCount", 0)
        total_passed_lua_object_registry_checks += scan.get("passedLuaObjectRegistryCheckCount", 0)
        total_lua_function_registry_checks += scan.get("luaFunctionRegistryCheckCount", 0)
        total_passed_lua_function_registry_checks += scan.get("passedLuaFunctionRegistryCheckCount", 0)
        total_runtime_lua_function_registry_checks += scan.get("runtimeLuaFunctionRegistryCheckCount", 0)
        total_self_test_lua_function_registry_checks += scan.get("selfTestLuaFunctionRegistryCheckCount", 0)
        total_ue_lua_object_registry += scan.get("ueLuaObjectRegistryCount", 0)
        total_runtime_ue_lua_object_registry += scan.get("runtimeUeLuaObjectRegistryCount", 0)
        total_self_test_ue_lua_object_registry += scan.get("selfTestUeLuaObjectRegistryCount", 0)
        total_object_array_lua_object_registry += scan.get("objectArrayLuaObjectRegistryCount", 0)
        total_runtime_object_array_lua_object_registry += scan.get("runtimeObjectArrayLuaObjectRegistryCount", 0)
        total_self_test_object_array_lua_object_registry += scan.get("selfTestObjectArrayLuaObjectRegistryCount", 0)
        total_decoded_lua_object_alias_registry += scan.get("decodedLuaObjectAliasRegistryCount", 0)
        total_runtime_decoded_lua_object_alias_registry += scan.get("runtimeDecodedLuaObjectAliasRegistryCount", 0)
        total_self_test_decoded_lua_object_alias_registry += scan.get("selfTestDecodedLuaObjectAliasRegistryCount", 0)
        total_skipped_decoded_lua_object_alias_registry += scan.get("skippedDecodedLuaObjectAliasRegistryCount", 0)
        total_ue_object_arrays += scan.get("ueObjectArrayCount", 0)
        total_ue_object_array_shapes += scan.get("ueObjectArrayShapeCount", 0)
        total_plausible_ue_object_array_shapes += scan.get("plausibleUeObjectArrayShapeCount", 0)
        total_implausible_ue_object_array_shapes += scan.get("implausibleUeObjectArrayShapeCount", 0)
        total_finished_ue_object_arrays += scan.get("finishedUeObjectArrayCount", 0)
        total_ue_object_array_items += scan.get("ueObjectArrayItemCount", 0)
        total_ue_object_native_identities += scan.get("ueObjectNativeIdentityCount", 0)
        total_promoted_ue_object_native_identities += scan.get("promotedUeObjectNativeIdentityCount", 0)
        total_decoded_name_ue_object_native_identities += scan.get("decodedNameUeObjectNativeIdentityCount", 0)
        total_decoded_class_name_ue_object_native_identities += scan.get("decodedClassNameUeObjectNativeIdentityCount", 0)
        total_internal_flag_ue_object_array_items += scan.get("internalFlagUeObjectArrayItemCount", 0)
        total_nonzero_internal_flag_ue_object_array_items += scan.get("nonzeroInternalFlagUeObjectArrayItemCount", 0)
        total_ue_fnames += scan.get("ueFNameCount", 0)
        total_decoded_ue_fnames += scan.get("decodedUeFNameCount", 0)
        total_ue_anchor_signatures += scan.get("ueAnchorSignatureCount", 0)
        total_resolved_ue_anchor_signatures += scan.get("resolvedUeAnchorSignatureCount", 0)
        for status, count in scan.get("ueAnchorSignatureStatusCounts", {}).items():
            total_ue_anchor_signature_status_counts[status] = total_ue_anchor_signature_status_counts.get(status, 0) + count
        for group, count in scan.get("ueAnchorGroupCounts", {}).items():
            total_ue_anchor_group_counts[group] = total_ue_anchor_group_counts.get(group, 0) + count
        for group, count in scan.get("mappedUeAnchorGroupCounts", {}).items():
            total_mapped_ue_anchor_group_counts[group] = total_mapped_ue_anchor_group_counts.get(group, 0) + count
        for group, count in scan.get("ueAnchorSignatureGroupCounts", {}).items():
            total_ue_anchor_signature_group_counts[group] = total_ue_anchor_signature_group_counts.get(group, 0) + count
        for group, count in scan.get("resolvedUeAnchorSignatureGroupCounts", {}).items():
            total_resolved_ue_anchor_signature_group_counts[group] = (
                total_resolved_ue_anchor_signature_group_counts.get(group, 0) + count
            )
        runtime_discovery = scan.get("ueRuntimeDiscovery") or {}
        total_ue_runtime_discovery_starts += runtime_discovery.get("startCount", 0)
        total_ue_runtime_discovery_finishes += runtime_discovery.get("finishCount", 0)
        total_ue_runtime_discovery_candidates += runtime_discovery.get("candidateCount", 0)
        for name, count in (runtime_discovery.get("candidateNameCounts") or {}).items():
            total_ue_runtime_discovery_candidate_name_counts[name] = (
                total_ue_runtime_discovery_candidate_name_counts.get(name, 0) + count
            )
        for image, count in (runtime_discovery.get("candidateImageCounts") or {}).items():
            total_ue_runtime_discovery_candidate_image_counts[image] = (
                total_ue_runtime_discovery_candidate_image_counts.get(image, 0) + count
            )
        total_ue_runtime_discovery_candidate_locations.extend(
            runtime_discovery.get("candidateLocations") or []
        )
        total_ue_runtime_discovery_validated_locations.extend(
            runtime_discovery.get("validatedLocations") or []
        )
        total_ue_runtime_discovery_target_writable_missing += runtime_discovery.get(
            "targetWritableMissingCount", 0
        )
        failure = runtime_discovery.get("failure", "")
        if failure:
            total_ue_runtime_discovery_failure_counts[failure] = (
                total_ue_runtime_discovery_failure_counts.get(failure, 0) + 1
            )
        for status, count in (runtime_discovery.get("statusCounts") or {}).items():
            total_ue_runtime_discovery_status_counts[status] = (
                total_ue_runtime_discovery_status_counts.get(status, 0) + count
            )
        for key, value in (runtime_discovery.get("coverage") or {}).items():
            if key in total_ue_runtime_discovery_coverage:
                total_ue_runtime_discovery_coverage[key] += value
        ue_runtime_discovery_promoted_names.update(runtime_discovery.get("promotedNames") or [])
        ue_runtime_discovery_validated_names.update(runtime_discovery.get("validatedNames") or [])
        ue_runtime_root_validation_names.update(
            runtime_discovery.get("rootValidationNames") or runtime_discovery.get("validatedNames") or []
        )
        for key, value in (runtime_discovery.get("validatedBy") or {}).items():
            total_ue_runtime_root_validated_by[key] = total_ue_runtime_root_validated_by.get(key, 0) + value
        if runtime_discovery.get("ready"):
            total_ue_runtime_discovery_ready_scans += 1
        if runtime_discovery.get("rootValidationReady") or runtime_discovery.get("ready"):
            total_ue_runtime_root_validation_ready_scans += 1
        total_ue_process_event_hooks += scan.get("ueProcessEventHookCount", 0)
        total_passed_ue_process_event_hooks += scan.get("passedUeProcessEventHookCount", 0)
        total_non_self_test_passed_ue_process_event_hooks += scan.get("nonSelfTestPassedUeProcessEventHookCount", 0)
        total_proven_target_passed_ue_process_event_hooks += scan.get("provenTargetPassedUeProcessEventHookCount", 0)
        total_ue_call_function_hooks += scan.get("ueCallFunctionHookCount", 0)
        total_passed_ue_call_function_hooks += scan.get("passedUeCallFunctionHookCount", 0)
        total_non_self_test_passed_ue_call_function_hooks += scan.get("nonSelfTestPassedUeCallFunctionHookCount", 0)
        total_proven_target_passed_ue_call_function_hooks += scan.get("provenTargetPassedUeCallFunctionHookCount", 0)
        total_ue_call_function_live_hooks += scan.get("ueCallFunctionLiveHookCount", 0)
        total_installed_ue_call_function_live_hooks += scan.get("installedUeCallFunctionLiveHookCount", 0)
        total_routed_ue_call_function_live_lua_hooks += scan.get("routedUeCallFunctionLiveLuaHookCount", 0)
        total_handled_ue_call_function_live_lua_hooks += scan.get("handledUeCallFunctionLiveLuaHookCount", 0)
        total_non_self_test_installed_ue_call_function_live_hooks += scan.get("nonSelfTestInstalledUeCallFunctionLiveHookCount", 0)
        total_proven_target_installed_ue_call_function_live_hooks += scan.get("provenTargetInstalledUeCallFunctionLiveHookCount", 0)
        total_proven_target_routed_ue_call_function_live_lua_hooks += scan.get(
            "provenTargetRoutedUeCallFunctionLiveLuaHookCount", 0
        )
        total_proven_target_handled_ue_call_function_live_lua_hooks += scan.get(
            "provenTargetHandledUeCallFunctionLiveLuaHookCount", 0
        )
        total_ue_call_function_active_validations += scan.get("ueCallFunctionActiveValidationCount", 0)
        total_invoked_ue_call_function_active_validations += scan.get("invokedUeCallFunctionActiveValidationCount", 0)
        total_original_ue_call_function_active_validations += scan.get("originalUeCallFunctionActiveValidationCount", 0)
        total_target_entry_ue_call_function_active_validations += scan.get("targetEntryUeCallFunctionActiveValidationCount", 0)
        total_ue_process_event_live_hooks += scan.get("ueProcessEventLiveHookCount", 0)
        total_installed_ue_process_event_live_hooks += scan.get("installedUeProcessEventLiveHookCount", 0)
        total_non_self_test_installed_ue_process_event_live_hooks += scan.get("nonSelfTestInstalledUeProcessEventLiveHookCount", 0)
        total_proven_target_installed_ue_process_event_live_hooks += scan.get("provenTargetInstalledUeProcessEventLiveHookCount", 0)
        total_ue_process_event_active_validations += scan.get("ueProcessEventActiveValidationCount", 0)
        total_invoked_ue_process_event_active_validations += scan.get("invokedUeProcessEventActiveValidationCount", 0)
        total_original_ue_process_event_active_validations += scan.get("originalUeProcessEventActiveValidationCount", 0)
        total_suppressed_ue_process_event_active_validations += scan.get("suppressedUeProcessEventActiveValidationCount", 0)
        total_target_entry_ue_process_event_active_validations += scan.get("targetEntryUeProcessEventActiveValidationCount", 0)
        total_suppressed_target_entry_ue_process_event_active_validations += scan.get("suppressedTargetEntryUeProcessEventActiveValidationCount", 0)
        total_synthetic_target_entry_ue_process_event_active_validations += scan.get(
            "syntheticTargetEntryUeProcessEventActiveValidationCount",
            min(
                scan.get("invokedUeProcessEventActiveValidationCount", 0),
                scan.get("suppressedTargetEntryUeProcessEventActiveValidationCount", 0),
            ),
        )
        total_descriptor_buffer_ue_process_event_active_validations += scan.get("descriptorBufferUeProcessEventActiveValidationCount", 0)
        total_ue_process_event_live_contexts += scan.get("ueProcessEventLiveContextCount", 0)
        total_resolved_ue_process_event_live_contexts += scan.get("resolvedUeProcessEventLiveContextCount", 0)
        total_matched_ue_process_event_live_contexts += scan.get("matchedUeProcessEventLiveContextCount", 0)
        total_runtime_matched_ue_process_event_live_contexts += scan.get("runtimeMatchedUeProcessEventLiveContextCount", 0)
        total_self_test_provenance_ue_process_event_live_contexts += scan.get("selfTestProvenanceUeProcessEventLiveContextCount", 0)
        total_runtime_provenance_ue_process_event_live_contexts += scan.get("runtimeProvenanceUeProcessEventLiveContextCount", 0)
        total_ue_process_event_live_registry_contexts += scan.get("ueProcessEventLiveRegistryContextCount", 0)
        total_resolved_ue_process_event_live_registry_contexts += scan.get("resolvedUeProcessEventLiveRegistryContextCount", 0)
        total_native_identity_ue_process_event_live_registry_contexts += scan.get("nativeIdentityUeProcessEventLiveRegistryContextCount", 0)
        total_matched_ue_process_event_live_registry_contexts += scan.get("matchedUeProcessEventLiveRegistryContextCount", 0)
        total_runtime_matched_ue_process_event_live_registry_contexts += scan.get("runtimeMatchedUeProcessEventLiveRegistryContextCount", 0)
        total_self_test_provenance_ue_process_event_live_registry_contexts += scan.get("selfTestProvenanceUeProcessEventLiveRegistryContextCount", 0)
        total_runtime_provenance_ue_process_event_live_registry_contexts += scan.get("runtimeProvenanceUeProcessEventLiveRegistryContextCount", 0)
        total_ue_process_event_live_params += scan.get("ueProcessEventLiveParamCount", 0)
        total_read_ue_process_event_live_params += scan.get("readUeProcessEventLiveParamCount", 0)
        total_raw_ue_process_event_live_params += scan.get("rawUeProcessEventLiveParamCount", 0)
        total_container_ue_process_event_live_params += scan.get("containerUeProcessEventLiveParamCount", 0)
        total_sampled_container_ue_process_event_live_params += scan.get("sampledContainerUeProcessEventLiveParamCount", 0)
        total_array_container_ue_process_event_live_params += scan.get("arrayContainerUeProcessEventLiveParamCount", 0)
        total_set_container_ue_process_event_live_params += scan.get("setContainerUeProcessEventLiveParamCount", 0)
        total_map_container_ue_process_event_live_params += scan.get("mapContainerUeProcessEventLiveParamCount", 0)
        total_set_map_container_ue_process_event_live_params += scan.get("setMapContainerUeProcessEventLiveParamCount", 0)
        total_runtime_read_ue_process_event_live_params += scan.get("runtimeReadUeProcessEventLiveParamCount", 0)
        total_runtime_raw_ue_process_event_live_params += scan.get("runtimeRawUeProcessEventLiveParamCount", 0)
        total_runtime_container_ue_process_event_live_params += scan.get("runtimeContainerUeProcessEventLiveParamCount", 0)
        total_runtime_sampled_container_ue_process_event_live_params += scan.get("runtimeSampledContainerUeProcessEventLiveParamCount", 0)
        total_runtime_array_container_ue_process_event_live_params += scan.get("runtimeArrayContainerUeProcessEventLiveParamCount", 0)
        total_runtime_set_container_ue_process_event_live_params += scan.get("runtimeSetContainerUeProcessEventLiveParamCount", 0)
        total_runtime_map_container_ue_process_event_live_params += scan.get("runtimeMapContainerUeProcessEventLiveParamCount", 0)
        total_runtime_set_map_container_ue_process_event_live_params += scan.get("runtimeSetMapContainerUeProcessEventLiveParamCount", 0)
        total_ue_process_event_lua_context_handles += scan.get("ueProcessEventLuaContextHandleCount", 0)
        total_ue_process_event_live_lua_param_accessors += scan.get("ueProcessEventLiveLuaParamAccessorCount", 0)
        total_ue_process_event_live_lua_function_param_methods += scan.get("ueProcessEventLiveLuaFunctionParamMethodCount", 0)
        total_ue_process_event_live_lua_function_param_lookup_methods += scan.get("ueProcessEventLiveLuaFunctionParamLookupMethodCount", 0)
        total_ue_process_event_live_lua_function_param_iteration_methods += scan.get("ueProcessEventLiveLuaFunctionParamIterationMethodCount", 0)
        total_ue_process_event_live_lua_container_alias_methods += scan.get("ueProcessEventLiveLuaContainerAliasMethodCount", 0)
        total_ue_process_event_live_lua_container_storage_layout_methods += scan.get("ueProcessEventLiveLuaContainerStorageLayoutMethodCount", 0)
        total_ue_process_event_live_lua_scalar_param_accessors += scan.get("ueProcessEventLiveLuaScalarParamAccessorCount", 0)
        total_ue_process_event_live_lua_name_string_param_accessors += scan.get("ueProcessEventLiveLuaNameStringParamAccessorCount", 0)
        total_ue_process_event_live_lua_struct_param_accessors += scan.get("ueProcessEventLiveLuaStructParamAccessorCount", 0)
        total_ue_process_event_live_lua_enum_param_accessors += scan.get("ueProcessEventLiveLuaEnumParamAccessorCount", 0)
        total_ue_process_event_live_lua_object_param_accessors += scan.get("ueProcessEventLiveLuaObjectParamAccessorCount", 0)
        total_ue_process_event_live_lua_bool_param_accessors += scan.get("ueProcessEventLiveLuaBoolParamAccessorCount", 0)
        total_routed_ue_process_event_live_lua_hooks += scan.get("routedUeProcessEventLiveLuaHookCount", 0)
        total_restored_ue_process_event_live_hooks += scan.get("restoredUeProcessEventLiveHookCount", 0)
        for status, count in scan.get("ueProcessEventLiveHookStatusCounts", {}).items():
            total_ue_process_event_live_hook_status_counts[status] = (
                total_ue_process_event_live_hook_status_counts.get(status, 0) + count
            )
        for status, count in scan.get("ueCallFunctionLiveHookStatusCounts", {}).items():
            total_ue_call_function_live_hook_status_counts[status] = (
                total_ue_call_function_live_hook_status_counts.get(status, 0) + count
            )
        total_ue_process_event_dispatch_self_tests += scan.get("ueProcessEventDispatchSelfTestCount", 0)
        total_armed_ue_process_event_dispatch_self_tests += scan.get("armedUeProcessEventDispatchSelfTestCount", 0)
        total_ue_process_event_live_lua_dispatches += scan.get("ueProcessEventLiveLuaDispatchCount", 0)
        total_armed_ue_process_event_live_lua_dispatches += scan.get("armedUeProcessEventLiveLuaDispatchCount", 0)
        total_multi_hook_ue_process_event_live_lua_dispatches += scan.get("multiHookUeProcessEventLiveLuaDispatchCount", 0)
        total_matched_ue_process_event_live_lua_dispatches += scan.get("matchedUeProcessEventLiveLuaDispatchCount", 0)
        total_closed_ue_process_event_live_lua_dispatches += scan.get("closedUeProcessEventLiveLuaDispatchCount", 0)
        total_closed_matched_ue_process_event_live_lua_dispatches += scan.get("closedMatchedUeProcessEventLiveLuaDispatchCount", 0)
        total_ue_process_event_live_lua_path_exact_matches += scan.get("ueProcessEventLiveLuaPathExactMatchCount", 0)
        total_ue_process_event_live_lua_path_alias_matches += scan.get("ueProcessEventLiveLuaPathAliasMatchCount", 0)
        for status, count in scan.get("ueProcessEventLiveLuaDispatchStatusCounts", {}).items():
            total_ue_process_event_live_lua_dispatch_status_counts[status] = (
                total_ue_process_event_live_lua_dispatch_status_counts.get(status, 0) + count
            )
        loaders.update(scan.get("loaders", []))
        pids.update(scan.get("pids", []))
        for loaded in scan.get("loaded", []):
            exe = loaded.get("exe", "")
            if exe:
                loaded_exes.add(exe)
        modules.update(path for path in scan.get("modules", []) if path)
        for name, hit in scan.get("hitsByName", {}).items():
            current = merged_hits.setdefault(
                name,
                {
                    "category": hit.get("category", ""),
                    "count": 0,
                    "kinds": {},
                    "sources": {},
                    "first": hit.get("first", {}),
                    "offsets": [],
                },
            )
            current["count"] += hit.get("count", 0)
            current["offsets"].extend(hit.get("offsets", []))
            if not current.get("first") and hit.get("first"):
                current["first"] = hit["first"]
            for key, value in hit.get("kinds", {}).items():
                current["kinds"][key] = current["kinds"].get(key, 0) + value
            for key, value in hit.get("sources", {}).items():
                current["sources"][key] = current["sources"].get(key, 0) + value
    ue_mod = import_script("summarize-client-ue-anchors.py", "summarize_client_ue_anchors")
    return {
        "loadCount": total_loads,
        "scanStartCount": total_starts,
        "scanFinishCount": total_finishes,
        "uePointerCount": total_pointers,
        "mappedUePointerCount": total_mapped_pointers,
        "ueLayoutCount": total_layouts,
        "readableUeLayoutCount": total_readable_layouts,
        "ueLayoutSlotCount": total_layout_slots,
        "mappedUeLayoutSlotCount": total_mapped_layout_slots,
        "ueUObjectCount": total_uobjects,
        "candidateUeUObjectCount": total_candidate_uobjects,
        "classMappedUeUObjectCount": total_class_mapped_uobjects,
        "ueReflectionCount": total_ue_reflections,
        "classMappedUeReflectionCount": total_class_mapped_ue_reflections,
        "ueReflectionSlotCount": total_ue_reflection_slots,
        "mappedUeReflectionSlotCount": total_mapped_ue_reflection_slots,
        "ueReflectionFieldCount": total_ue_reflection_fields,
        "candidateUeReflectionFieldCount": total_candidate_ue_reflection_fields,
        "classMappedUeReflectionFieldCount": total_class_mapped_ue_reflection_fields,
        "ueReflectionPropertyCount": total_ue_reflection_properties,
        "candidateUeReflectionPropertyCount": total_candidate_ue_reflection_properties,
        "readableUeReflectionPropertyCount": total_readable_ue_reflection_properties,
        "runtimeUeReflectionPropertyCount": total_runtime_ue_reflection_properties,
        "runtimeReadableUeReflectionPropertyCount": total_runtime_readable_ue_reflection_properties,
        "ueReflectionValueCount": total_ue_reflection_values,
        "readUeReflectionValueCount": total_read_ue_reflection_values,
        "runtimeReadUeReflectionValueCount": total_runtime_read_ue_reflection_values,
        "runtimeDescriptorMatchedReadUeReflectionValueCount": (
            total_runtime_descriptor_matched_read_ue_reflection_values
        ),
        "ueFunctionParamRootCount": total_ue_function_param_roots,
        "rootedUeFunctionParamRootCount": total_rooted_ue_function_param_roots,
        "ueFunctionParamCount": total_ue_function_params,
        "candidateUeFunctionParamCount": total_candidate_ue_function_params,
        "ueFunctionParamContainerChildCount": total_ue_function_param_container_children,
        "candidateUeFunctionParamContainerChildCount": total_candidate_ue_function_param_container_children,
        "decodedUeFunctionParamContainerChildCount": total_decoded_ue_function_param_container_children,
        "ueFunctionNativeIdentityCount": total_ue_function_native_identities,
        "promotedUeFunctionNativeIdentityCount": total_promoted_ue_function_native_identities,
        "readableFlagUeFunctionNativeIdentityCount": total_readable_flag_ue_function_native_identities,
        "runtimePathUeFunctionNativeIdentityCount": total_runtime_path_ue_function_native_identities,
        "ue4ssPathUeFunctionNativeIdentityCount": total_ue4ss_path_ue_function_native_identities,
        "readableUeFunctionParamCount": total_readable_ue_function_params,
        "namedUeFunctionParamCount": total_named_ue_function_params,
        "uniqueUeFunctionPathCount": len(ue_function_paths),
        "ueFunctionPaths": sorted(ue_function_paths),
        "uniqueUe4ssFunctionPathCount": len(ue4ss_function_paths),
        "ue4ssFunctionPaths": sorted(ue4ss_function_paths),
        "activeValidationCandidates": unique_candidates(
            active_validation_candidates,
            ("objectAddress", "functionAddress", "functionPath"),
        ),
        "readableUeFunctionFlagRootCount": total_readable_ue_function_flag_roots,
        "readableUeFunctionFlagParamCount": total_readable_ue_function_flag_params,
        "ueFunctionFlagPathCount": len(ue_function_flag_paths),
        "ueFunctionFlagPaths": sorted(ue_function_flag_paths),
        "ueFunctionFlagValues": sorted(ue_function_flag_values),
        "hookSelfTestCount": total_hook_self_tests,
        "passedHookSelfTestCount": total_passed_hook_self_tests,
        "modSelfTestCount": total_mod_self_tests,
        "passedModSelfTestCount": total_passed_mod_self_tests,
        "luaSelfTestCount": total_lua_self_tests,
        "passedLuaSelfTestCount": total_passed_lua_self_tests,
        "passedLuaCallbackSelfTestCount": total_passed_lua_callback_self_tests,
        "passedLuaApiSelfTestCount": total_passed_lua_api_self_tests,
        "passedLuaSchedulerApiSelfTestCount": total_passed_lua_scheduler_api_self_tests,
        "passedLuaInputCommandApiSelfTestCount": total_passed_lua_input_command_api_self_tests,
        "passedLuaObjectApiSelfTestCount": total_passed_lua_object_api_self_tests,
        "luaReflectionSelfTestCount": total_lua_reflection_self_tests,
        "passedLuaReflectionSelfTestCount": total_passed_lua_reflection_self_tests,
        "rawSetLuaReflectionSelfTestCount": total_raw_set_lua_reflection_self_tests,
        "namedLuaReflectionSelfTestCount": total_named_lua_reflection_self_tests,
        "numericLuaReflectionSelfTestCount": total_numeric_lua_reflection_self_tests,
        "nameTextLuaReflectionSelfTestCount": total_name_text_lua_reflection_self_tests,
        "arrayInnerLuaReflectionSelfTestCount": total_array_inner_lua_reflection_self_tests,
        "enumLuaReflectionSelfTestCount": total_enum_lua_reflection_self_tests,
        "containerLuaReflectionSelfTestCount": total_container_lua_reflection_self_tests,
        "importTextLuaReflectionSelfTestCount": total_import_text_lua_reflection_self_tests,
        "exportTextLuaReflectionSelfTestCount": total_export_text_lua_reflection_self_tests,
        "propertyMetadataLuaReflectionSelfTestCount": total_property_metadata_lua_reflection_self_tests,
        "descriptorValueLuaReflectionSelfTestCount": total_descriptor_value_lua_reflection_self_tests,
        "reflectionForEachPropertyLuaReflectionSelfTestCount": total_reflection_for_each_property_lua_reflection_self_tests,
        "runtimeReflectionForEachPropertyLuaReflectionSelfTestCount": total_runtime_reflection_for_each_property_lua_reflection_self_tests,
        "selfTestReflectionForEachPropertyLuaReflectionSelfTestCount": total_self_test_reflection_for_each_property_lua_reflection_self_tests,
        "typedLiveDescriptorLuaReflectionSelfTestCount": total_typed_live_descriptor_lua_reflection_self_tests,
        "runtimeTypedLiveDescriptorLuaReflectionSelfTestCount": total_runtime_typed_live_descriptor_lua_reflection_self_tests,
        "selfTestTypedLiveDescriptorLuaReflectionSelfTestCount": total_self_test_typed_live_descriptor_lua_reflection_self_tests,
        "typedLiveDescriptorValueLuaReflectionSelfTestCount": total_typed_live_descriptor_value_lua_reflection_self_tests,
        "runtimeTypedLiveDescriptorValueLuaReflectionSelfTestCount": total_runtime_typed_live_descriptor_value_lua_reflection_self_tests,
        "selfTestTypedLiveDescriptorValueLuaReflectionSelfTestCount": total_self_test_typed_live_descriptor_value_lua_reflection_self_tests,
        "typedLiveDescriptorValueSetLuaReflectionSelfTestCount": total_typed_live_descriptor_value_set_lua_reflection_self_tests,
        "runtimeTypedLiveDescriptorValueSetLuaReflectionSelfTestCount": total_runtime_typed_live_descriptor_value_set_lua_reflection_self_tests,
        "selfTestTypedLiveDescriptorValueSetLuaReflectionSelfTestCount": total_self_test_typed_live_descriptor_value_set_lua_reflection_self_tests,
        "liveDescriptorValueLuaReflectionSelfTestCount": total_live_descriptor_value_lua_reflection_self_tests,
        "runtimeLiveDescriptorValueLuaReflectionSelfTestCount": total_runtime_live_descriptor_value_lua_reflection_self_tests,
        "selfTestLiveDescriptorValueLuaReflectionSelfTestCount": total_self_test_live_descriptor_value_lua_reflection_self_tests,
        "luaProcessEventSelfTestCount": total_lua_process_event_self_tests,
        "passedLuaProcessEventSelfTestCount": total_passed_lua_process_event_self_tests,
        "luaProcessEventParamAccessorSelfTestCount": total_lua_process_event_param_accessor_self_tests,
        "luaProcessEventFunctionParamMethodSelfTestCount": total_lua_process_event_function_param_method_self_tests,
        "luaProcessEventFunctionParamLookupMethodSelfTestCount": total_lua_process_event_function_param_lookup_method_self_tests,
        "luaProcessEventFunctionParamIterationMethodSelfTestCount": total_lua_process_event_function_param_iteration_method_self_tests,
        "luaProcessEventContainerAliasMethodSelfTestCount": total_lua_process_event_container_alias_method_self_tests,
        "luaProcessEventContainerStorageLayoutMethodSelfTestCount": total_lua_process_event_container_storage_layout_method_self_tests,
        "luaProcessEventScalarParamAccessorSelfTestCount": total_lua_process_event_scalar_param_accessor_self_tests,
        "luaProcessEventNameStringParamAccessorSelfTestCount": total_lua_process_event_name_string_param_accessor_self_tests,
        "luaProcessEventStructParamAccessorSelfTestCount": total_lua_process_event_struct_param_accessor_self_tests,
        "luaProcessEventEnumParamAccessorSelfTestCount": total_lua_process_event_enum_param_accessor_self_tests,
        "luaProcessEventObjectParamAccessorSelfTestCount": total_lua_process_event_object_param_accessor_self_tests,
        "luaProcessEventBoolParamAccessorSelfTestCount": total_lua_process_event_bool_param_accessor_self_tests,
        "routedLuaProcessEventSelfTestCount": total_routed_lua_process_event_self_tests,
        "luaProcessEventPathExactMatchCount": total_lua_process_event_path_exact_matches,
        "luaProcessEventPathAliasMatchCount": total_lua_process_event_path_alias_matches,
        "luaModScriptCount": total_lua_mod_scripts,
        "passedLuaModScriptCount": total_passed_lua_mod_scripts,
        "luaModDispatchSelfTestCount": total_lua_mod_dispatch_self_tests,
        "passedLuaModDispatchSelfTestCount": total_passed_lua_mod_dispatch_self_tests,
        "luaModFinishCount": total_lua_mod_finishes,
        "passedLuaModFinishCount": total_passed_lua_mod_finishes,
        "luaObjectApiModFinishCount": total_lua_object_api_mod_finishes,
        "luaLoadAssetBackendStateModFinishCount": total_lua_load_asset_backend_state_mod_finishes,
        "luaLoadAssetBackendAnchorModFinishCount": total_lua_load_asset_backend_anchor_mod_finishes,
        "luaLoadAssetPackageBridgeStateModFinishCount": total_lua_load_asset_package_bridge_state_mod_finishes,
        "luaLoadAssetPackageNativeInvokeModFinishCount": total_lua_load_asset_package_native_invoke_mod_finishes,
        "luaLoadAssetPackageAbiStateEventCount": total_lua_load_asset_package_abi_state_events,
        "luaLoadAssetPackageStringBridgeEventCount": total_lua_load_asset_package_string_bridge_events,
        "luaLoadAssetPackageNativeBufferEventCount": total_lua_load_asset_package_native_buffer_events,
        "luaLoadAssetPackageTCharBufferEventCount": total_lua_load_asset_package_tchar_buffer_events,
        "luaLoadAssetPackageTCharVerificationEventCount": total_lua_load_asset_package_tchar_verification_events,
        "luaLoadAssetPackageCallFrameEventCount": total_lua_load_asset_package_call_frame_events,
        "luaLoadAssetPackageCallFrameVerificationEventCount": total_lua_load_asset_package_call_frame_verification_events,
        "luaLoadAssetPackageCrashGuardEventCount": total_lua_load_asset_package_crash_guard_events,
        "luaLoadAssetPackageGuardedCallEventCount": total_lua_load_asset_package_guarded_call_events,
        "luaLoadAssetPackageReturnValidationEventCount": total_lua_load_asset_package_return_validation_events,
        "luaLoadAssetPackageNativeCallAdapterEventCount": total_lua_load_asset_package_native_call_adapter_events,
        "luaLoadAssetPackageInvocationDescriptorEventCount": total_lua_load_asset_package_invocation_descriptor_events,
        "luaLoadAssetPackageNativeExecutorEventCount": total_lua_load_asset_package_native_executor_events,
        "luaLoadAssetPackageNativeExecutorReadyEventCount": (
            total_lua_load_asset_package_native_executor_ready_events
        ),
        "luaLoadAssetPackageNativeExecutorTargetReadyEventCount": (
            total_lua_load_asset_package_native_executor_target_ready_events
        ),
        "luaLoadAssetPackageNativeInvokedEventCount": total_lua_load_asset_package_native_invoked_events,
        "luaLoadClassPackageAbiStateEventCount": total_lua_load_class_package_abi_state_events,
        "luaLoadClassPackageCallFrameVerificationEventCount": (
            total_lua_load_class_package_call_frame_verification_events
        ),
        "luaLoadClassPackageNativeExecutorEventCount": total_lua_load_class_package_native_executor_events,
        "luaLoadClassPackageNativeExecutorReadyEventCount": (
            total_lua_load_class_package_native_executor_ready_events
        ),
        "luaLoadClassPackageNativeInvokedEventCount": total_lua_load_class_package_native_invoked_events,
        "luaStaticConstructObjectNativeExecutorStateCount": (
            total_lua_static_construct_object_native_executor_states
        ),
        "luaStaticConstructObjectNativeExecutorReadyStateCount": (
            total_lua_static_construct_object_native_executor_ready_states
        ),
        "luaStaticConstructObjectNativeInvokeCount": total_lua_static_construct_object_native_invokes,
        "luaStaticConstructObjectNativeInvokedCount": total_lua_static_construct_object_native_invoked,
        "luaLoadAssetPackagePreflightModFinishCount": total_lua_load_asset_package_preflight_mod_finishes,
        "luaLoadAssetPackageModFinishCount": total_lua_load_asset_package_mod_finishes,
        "luaFunctionIterationModFinishCount": total_lua_function_iteration_mod_finishes,
        "luaFunctionIterationCheckCount": total_lua_function_iteration_checks,
        "passedLuaFunctionIterationCheckCount": total_passed_lua_function_iteration_checks,
        "runtimeLuaFunctionIterationCheckCount": total_runtime_lua_function_iteration_checks,
        "selfTestLuaFunctionIterationCheckCount": total_self_test_lua_function_iteration_checks,
        "luaSchedulerApiModFinishCount": total_lua_scheduler_api_mod_finishes,
        "luaInputCommandApiModFinishCount": total_lua_input_command_api_mod_finishes,
        "luaProcessConsoleExecHookModFinishCount": total_lua_process_console_exec_hook_mod_finishes,
        "luaLocalPlayerExecHookModFinishCount": total_lua_local_player_exec_hook_mod_finishes,
        "luaCallFunctionHookModFinishCount": total_lua_call_function_hook_mod_finishes,
        "luaCallFunctionStructuredArgsModFinishCount": total_lua_call_function_structured_args_mod_finishes,
        "luaCallFunctionNativeInvokeModFinishCount": total_lua_call_function_native_invoke_mod_finishes,
        "luaCallFunctionNativeInvokeSelfTestCount": total_lua_call_function_native_invoke_self_tests,
        "luaCallFunctionNativeInvokePreflightCount": total_lua_call_function_native_invoke_preflights,
        "luaCallFunctionNativeExecutorStateCount": total_lua_call_function_native_executor_states,
        "luaCallFunctionNativeExecutorReadyStateCount": (
            total_lua_call_function_native_executor_ready_states
        ),
        "luaCallFunctionNativeInvokeNonSelfTestGateCount": (
            total_lua_call_function_native_invoke_non_self_test_gates
        ),
        "luaCallFunctionNativeInvokeNonSelfTestInvokedCount": (
            total_lua_call_function_native_invoke_non_self_test_invocations
        ),
        "luaProcessEventCompatModFinishCount": total_lua_process_event_compat_mod_finishes,
        "luaProcessEventBridgeStateModFinishCount": total_lua_process_event_bridge_state_mod_finishes,
        "luaProcessEventNativeInvokeModFinishCount": total_lua_process_event_native_invoke_mod_finishes,
        "luaProcessEventNativeInvokeSelfTestCount": total_lua_process_event_native_invoke_self_tests,
        "luaProcessEventNativeInvokeDescriptorPreflightCount": (
            total_lua_process_event_native_invoke_descriptor_preflights
        ),
        "luaProcessEventNativeExecutorStateCount": total_lua_process_event_native_executor_states,
        "luaProcessEventNativeExecutorReadyStateCount": (
            total_lua_process_event_native_executor_ready_states
        ),
        "luaProcessEventNativeInvokeNonSelfTestGateCount": (
            total_lua_process_event_native_invoke_non_self_test_gates
        ),
        "luaProcessEventNativeInvokeNonSelfTestInvokedCount": (
            total_lua_process_event_native_invoke_non_self_test_invocations
        ),
        "luaProcessEventParamsBufferCount": total_lua_process_event_params_buffers,
        "luaLifecycleHookModFinishCount": total_lua_lifecycle_hook_mod_finishes,
        "luaCustomEventModFinishCount": total_lua_custom_event_mod_finishes,
        "luaLoadMapHookModFinishCount": total_lua_load_map_hook_mod_finishes,
        "luaBeginPlayHookModFinishCount": total_lua_begin_play_hook_mod_finishes,
        "luaInitGameStateHookModFinishCount": total_lua_init_game_state_hook_mod_finishes,
        "luaNotifyOnNewObjectModFinishCount": total_lua_notify_on_new_object_mod_finishes,
        "luaSyntheticOuterModFinishCount": total_lua_synthetic_outer_mod_finishes,
        "luaObjectOuterChainCount": total_lua_object_outer_chains,
        "resolvedLuaObjectOuterChainCount": total_resolved_lua_object_outer_chains,
        "luaObjectOuterChainIdentityCount": total_lua_object_outer_chain_identities,
        "luaGlobalRuntimeHelperCheckCount": total_lua_global_runtime_helper_checks,
        "passedLuaGlobalRuntimeHelperCheckCount": total_passed_lua_global_runtime_helper_checks,
        "promotedWorldLuaGlobalRuntimeHelperCheckCount": total_promoted_world_lua_global_runtime_helper_checks,
        "promotedEngineLuaGlobalRuntimeHelperCheckCount": total_promoted_engine_lua_global_runtime_helper_checks,
        "luaWorldContextModFinishCount": total_lua_world_context_mod_finishes,
        "luaClassDefaultObjectModFinishCount": total_lua_class_default_object_mod_finishes,
        "luaLevelModFinishCount": total_lua_level_mod_finishes,
        "luaObjectRegistryCount": total_lua_object_registry,
        "addedLuaObjectRegistryCount": total_added_lua_object_registry,
        "luaObjectRegistryCheckCount": total_lua_object_registry_checks,
        "passedLuaObjectRegistryCheckCount": total_passed_lua_object_registry_checks,
        "luaFunctionRegistryCheckCount": total_lua_function_registry_checks,
        "passedLuaFunctionRegistryCheckCount": total_passed_lua_function_registry_checks,
        "runtimeLuaFunctionRegistryCheckCount": total_runtime_lua_function_registry_checks,
        "selfTestLuaFunctionRegistryCheckCount": total_self_test_lua_function_registry_checks,
        "ueLuaObjectRegistryCount": total_ue_lua_object_registry,
        "runtimeUeLuaObjectRegistryCount": total_runtime_ue_lua_object_registry,
        "selfTestUeLuaObjectRegistryCount": total_self_test_ue_lua_object_registry,
        "objectArrayLuaObjectRegistryCount": total_object_array_lua_object_registry,
        "runtimeObjectArrayLuaObjectRegistryCount": total_runtime_object_array_lua_object_registry,
        "selfTestObjectArrayLuaObjectRegistryCount": total_self_test_object_array_lua_object_registry,
        "decodedLuaObjectAliasRegistryCount": total_decoded_lua_object_alias_registry,
        "runtimeDecodedLuaObjectAliasRegistryCount": total_runtime_decoded_lua_object_alias_registry,
        "selfTestDecodedLuaObjectAliasRegistryCount": total_self_test_decoded_lua_object_alias_registry,
        "skippedDecodedLuaObjectAliasRegistryCount": total_skipped_decoded_lua_object_alias_registry,
        "ueObjectArrayCount": total_ue_object_arrays,
        "ueObjectArrayShapeCount": total_ue_object_array_shapes,
        "plausibleUeObjectArrayShapeCount": total_plausible_ue_object_array_shapes,
        "implausibleUeObjectArrayShapeCount": total_implausible_ue_object_array_shapes,
        "finishedUeObjectArrayCount": total_finished_ue_object_arrays,
        "ueObjectArrayItemCount": total_ue_object_array_items,
        "ueObjectNativeIdentityCount": total_ue_object_native_identities,
        "promotedUeObjectNativeIdentityCount": total_promoted_ue_object_native_identities,
        "decodedNameUeObjectNativeIdentityCount": total_decoded_name_ue_object_native_identities,
        "decodedClassNameUeObjectNativeIdentityCount": total_decoded_class_name_ue_object_native_identities,
        "internalFlagUeObjectArrayItemCount": total_internal_flag_ue_object_array_items,
        "nonzeroInternalFlagUeObjectArrayItemCount": total_nonzero_internal_flag_ue_object_array_items,
        "ueFNameCount": total_ue_fnames,
        "decodedUeFNameCount": total_decoded_ue_fnames,
        "ueAnchorSignatureCount": total_ue_anchor_signatures,
        "resolvedUeAnchorSignatureCount": total_resolved_ue_anchor_signatures,
        "ueAnchorSignatureStatusCounts": dict(sorted(total_ue_anchor_signature_status_counts.items())),
        "ueAnchorGroupCounts": dict(sorted(total_ue_anchor_group_counts.items())),
        "mappedUeAnchorGroupCounts": dict(sorted(total_mapped_ue_anchor_group_counts.items())),
        "ueAnchorSignatureGroupCounts": dict(sorted(total_ue_anchor_signature_group_counts.items())),
        "resolvedUeAnchorSignatureGroupCounts": dict(sorted(total_resolved_ue_anchor_signature_group_counts.items())),
        "ueRuntimeDiscovery": {
            "ready": {"RuntimeFNamePool", "RuntimeGUObjectArray"}.issubset(
                ue_runtime_discovery_validated_names
            ),
            "startCount": total_ue_runtime_discovery_starts,
            "finishCount": total_ue_runtime_discovery_finishes,
            "candidateCount": total_ue_runtime_discovery_candidates,
            "candidateNameCounts": dict(sorted(total_ue_runtime_discovery_candidate_name_counts.items())),
            "candidateImageCounts": dict(sorted(total_ue_runtime_discovery_candidate_image_counts.items())),
            "candidateLocations": total_ue_runtime_discovery_candidate_locations[:64],
            "validatedLocations": total_ue_runtime_discovery_validated_locations[:16],
            "targetWritableMissingCount": total_ue_runtime_discovery_target_writable_missing,
            "promotedNames": sorted(ue_runtime_discovery_promoted_names),
            "validatedNames": sorted(ue_runtime_discovery_validated_names),
            "readyScanCount": total_ue_runtime_discovery_ready_scans,
            "rootValidationNames": sorted(ue_runtime_root_validation_names),
            "rootValidationReady": {"RuntimeFNamePool", "RuntimeGUObjectArray"}.issubset(
                ue_runtime_root_validation_names
            ),
            "rootValidationReadyScanCount": total_ue_runtime_root_validation_ready_scans,
            "validatedBy": dict(sorted(total_ue_runtime_root_validated_by.items())),
            "coverage": total_ue_runtime_discovery_coverage,
            "statusCounts": dict(sorted(total_ue_runtime_discovery_status_counts.items())),
            "failureCounts": dict(sorted(total_ue_runtime_discovery_failure_counts.items())),
        },
        "ueProcessEventHookCount": total_ue_process_event_hooks,
        "passedUeProcessEventHookCount": total_passed_ue_process_event_hooks,
        "nonSelfTestPassedUeProcessEventHookCount": total_non_self_test_passed_ue_process_event_hooks,
        "provenTargetPassedUeProcessEventHookCount": total_proven_target_passed_ue_process_event_hooks,
        "ueCallFunctionHookCount": total_ue_call_function_hooks,
        "passedUeCallFunctionHookCount": total_passed_ue_call_function_hooks,
        "nonSelfTestPassedUeCallFunctionHookCount": total_non_self_test_passed_ue_call_function_hooks,
        "provenTargetPassedUeCallFunctionHookCount": total_proven_target_passed_ue_call_function_hooks,
        "ueCallFunctionLiveHookCount": total_ue_call_function_live_hooks,
        "installedUeCallFunctionLiveHookCount": total_installed_ue_call_function_live_hooks,
        "routedUeCallFunctionLiveLuaHookCount": total_routed_ue_call_function_live_lua_hooks,
        "handledUeCallFunctionLiveLuaHookCount": total_handled_ue_call_function_live_lua_hooks,
        "nonSelfTestInstalledUeCallFunctionLiveHookCount": total_non_self_test_installed_ue_call_function_live_hooks,
        "provenTargetInstalledUeCallFunctionLiveHookCount": total_proven_target_installed_ue_call_function_live_hooks,
        "provenTargetRoutedUeCallFunctionLiveLuaHookCount": (
            total_proven_target_routed_ue_call_function_live_lua_hooks
        ),
        "provenTargetHandledUeCallFunctionLiveLuaHookCount": (
            total_proven_target_handled_ue_call_function_live_lua_hooks
        ),
        "ueCallFunctionActiveValidationCount": total_ue_call_function_active_validations,
        "invokedUeCallFunctionActiveValidationCount": total_invoked_ue_call_function_active_validations,
        "originalUeCallFunctionActiveValidationCount": total_original_ue_call_function_active_validations,
        "targetEntryUeCallFunctionActiveValidationCount": total_target_entry_ue_call_function_active_validations,
        "ueProcessEventLiveHookCount": total_ue_process_event_live_hooks,
        "installedUeProcessEventLiveHookCount": total_installed_ue_process_event_live_hooks,
        "nonSelfTestInstalledUeProcessEventLiveHookCount": total_non_self_test_installed_ue_process_event_live_hooks,
        "provenTargetInstalledUeProcessEventLiveHookCount": total_proven_target_installed_ue_process_event_live_hooks,
        "ueProcessEventActiveValidationCount": total_ue_process_event_active_validations,
        "invokedUeProcessEventActiveValidationCount": total_invoked_ue_process_event_active_validations,
        "originalUeProcessEventActiveValidationCount": total_original_ue_process_event_active_validations,
        "suppressedUeProcessEventActiveValidationCount": total_suppressed_ue_process_event_active_validations,
        "targetEntryUeProcessEventActiveValidationCount": total_target_entry_ue_process_event_active_validations,
        "suppressedTargetEntryUeProcessEventActiveValidationCount": total_suppressed_target_entry_ue_process_event_active_validations,
        "syntheticTargetEntryUeProcessEventActiveValidationCount": total_synthetic_target_entry_ue_process_event_active_validations,
        "descriptorBufferUeProcessEventActiveValidationCount": total_descriptor_buffer_ue_process_event_active_validations,
        "ueProcessEventLiveContextCount": total_ue_process_event_live_contexts,
        "resolvedUeProcessEventLiveContextCount": total_resolved_ue_process_event_live_contexts,
        "matchedUeProcessEventLiveContextCount": total_matched_ue_process_event_live_contexts,
        "runtimeMatchedUeProcessEventLiveContextCount": total_runtime_matched_ue_process_event_live_contexts,
        "selfTestProvenanceUeProcessEventLiveContextCount": total_self_test_provenance_ue_process_event_live_contexts,
        "runtimeProvenanceUeProcessEventLiveContextCount": total_runtime_provenance_ue_process_event_live_contexts,
        "ueProcessEventLiveRegistryContextCount": total_ue_process_event_live_registry_contexts,
        "resolvedUeProcessEventLiveRegistryContextCount": total_resolved_ue_process_event_live_registry_contexts,
        "nativeIdentityUeProcessEventLiveRegistryContextCount": total_native_identity_ue_process_event_live_registry_contexts,
        "matchedUeProcessEventLiveRegistryContextCount": total_matched_ue_process_event_live_registry_contexts,
        "runtimeMatchedUeProcessEventLiveRegistryContextCount": total_runtime_matched_ue_process_event_live_registry_contexts,
        "selfTestProvenanceUeProcessEventLiveRegistryContextCount": total_self_test_provenance_ue_process_event_live_registry_contexts,
        "runtimeProvenanceUeProcessEventLiveRegistryContextCount": total_runtime_provenance_ue_process_event_live_registry_contexts,
        "ueProcessEventLiveParamCount": total_ue_process_event_live_params,
        "readUeProcessEventLiveParamCount": total_read_ue_process_event_live_params,
        "rawUeProcessEventLiveParamCount": total_raw_ue_process_event_live_params,
        "containerUeProcessEventLiveParamCount": total_container_ue_process_event_live_params,
        "sampledContainerUeProcessEventLiveParamCount": total_sampled_container_ue_process_event_live_params,
        "arrayContainerUeProcessEventLiveParamCount": total_array_container_ue_process_event_live_params,
        "setContainerUeProcessEventLiveParamCount": total_set_container_ue_process_event_live_params,
        "mapContainerUeProcessEventLiveParamCount": total_map_container_ue_process_event_live_params,
        "setMapContainerUeProcessEventLiveParamCount": total_set_map_container_ue_process_event_live_params,
        "runtimeReadUeProcessEventLiveParamCount": total_runtime_read_ue_process_event_live_params,
        "runtimeRawUeProcessEventLiveParamCount": total_runtime_raw_ue_process_event_live_params,
        "runtimeContainerUeProcessEventLiveParamCount": total_runtime_container_ue_process_event_live_params,
        "runtimeSampledContainerUeProcessEventLiveParamCount": total_runtime_sampled_container_ue_process_event_live_params,
        "runtimeArrayContainerUeProcessEventLiveParamCount": total_runtime_array_container_ue_process_event_live_params,
        "runtimeSetContainerUeProcessEventLiveParamCount": total_runtime_set_container_ue_process_event_live_params,
        "runtimeMapContainerUeProcessEventLiveParamCount": total_runtime_map_container_ue_process_event_live_params,
        "runtimeSetMapContainerUeProcessEventLiveParamCount": total_runtime_set_map_container_ue_process_event_live_params,
        "ueProcessEventLuaContextHandleCount": total_ue_process_event_lua_context_handles,
        "ueProcessEventLiveLuaParamAccessorCount": total_ue_process_event_live_lua_param_accessors,
        "ueProcessEventLiveLuaFunctionParamMethodCount": total_ue_process_event_live_lua_function_param_methods,
        "ueProcessEventLiveLuaFunctionParamLookupMethodCount": total_ue_process_event_live_lua_function_param_lookup_methods,
        "ueProcessEventLiveLuaFunctionParamIterationMethodCount": total_ue_process_event_live_lua_function_param_iteration_methods,
        "ueProcessEventLiveLuaContainerAliasMethodCount": total_ue_process_event_live_lua_container_alias_methods,
        "ueProcessEventLiveLuaContainerStorageLayoutMethodCount": total_ue_process_event_live_lua_container_storage_layout_methods,
        "ueProcessEventLiveLuaScalarParamAccessorCount": total_ue_process_event_live_lua_scalar_param_accessors,
        "ueProcessEventLiveLuaNameStringParamAccessorCount": total_ue_process_event_live_lua_name_string_param_accessors,
        "ueProcessEventLiveLuaStructParamAccessorCount": total_ue_process_event_live_lua_struct_param_accessors,
        "ueProcessEventLiveLuaEnumParamAccessorCount": total_ue_process_event_live_lua_enum_param_accessors,
        "ueProcessEventLiveLuaObjectParamAccessorCount": total_ue_process_event_live_lua_object_param_accessors,
        "ueProcessEventLiveLuaBoolParamAccessorCount": total_ue_process_event_live_lua_bool_param_accessors,
        "routedUeProcessEventLiveLuaHookCount": total_routed_ue_process_event_live_lua_hooks,
        "restoredUeProcessEventLiveHookCount": total_restored_ue_process_event_live_hooks,
        "ueProcessEventLiveHookStatusCounts": dict(sorted(total_ue_process_event_live_hook_status_counts.items())),
        "ueCallFunctionLiveHookStatusCounts": dict(sorted(total_ue_call_function_live_hook_status_counts.items())),
        "ueProcessEventDispatchSelfTestCount": total_ue_process_event_dispatch_self_tests,
        "armedUeProcessEventDispatchSelfTestCount": total_armed_ue_process_event_dispatch_self_tests,
        "ueProcessEventLiveLuaDispatchCount": total_ue_process_event_live_lua_dispatches,
        "armedUeProcessEventLiveLuaDispatchCount": total_armed_ue_process_event_live_lua_dispatches,
        "multiHookUeProcessEventLiveLuaDispatchCount": total_multi_hook_ue_process_event_live_lua_dispatches,
        "matchedUeProcessEventLiveLuaDispatchCount": total_matched_ue_process_event_live_lua_dispatches,
        "closedUeProcessEventLiveLuaDispatchCount": total_closed_ue_process_event_live_lua_dispatches,
        "closedMatchedUeProcessEventLiveLuaDispatchCount": total_closed_matched_ue_process_event_live_lua_dispatches,
        "ueProcessEventLiveLuaPathExactMatchCount": total_ue_process_event_live_lua_path_exact_matches,
        "ueProcessEventLiveLuaPathAliasMatchCount": total_ue_process_event_live_lua_path_alias_matches,
        "ueProcessEventLiveLuaDispatchStatusCounts": dict(sorted(total_ue_process_event_live_lua_dispatch_status_counts.items())),
        "loaders": sorted(loaders),
        "pids": sorted(pids),
        "loadedExes": sorted(loaded_exes),
        "modules": sorted(modules),
        "targetImageSubstrings": effective_target_image_substrings(target_image_substrings),
        "autoTargetPidFilters": sorted(auto_target_pid_filters),
        "hitsByName": merged_hits,
        "ue": ue_mod.summarize({"hitsByName": merged_hits}, proven_only=True),
    }


def signature_validation_status(validation_summaries):
    if not validation_summaries:
        return {
            "provided": False,
            "patternCount": 0,
            "promotableCount": 0,
            "statusCounts": {},
            "exactOnly": False,
            "allPromotable": False,
        }
    pattern_count = 0
    promotable_count = 0
    status_counts = {}
    for validation in validation_summaries:
        pattern_count += validation.get("patternCount", 0)
        promotable_count += validation.get("promotableCount", 0)
        for status, count in validation.get("statusCounts", {}).items():
            status_counts[status] = status_counts.get(status, 0) + count
    exact_only = pattern_count > 0 and status_counts == {"unique-expected": pattern_count}
    return {
        "provided": True,
        "patternCount": pattern_count,
        "promotableCount": promotable_count,
        "statusCounts": dict(sorted(status_counts.items())),
        "exactOnly": exact_only,
        "allPromotable": pattern_count > 0 and promotable_count == pattern_count,
    }


def anchor_coverage_status(anchor_coverages):
    if not anchor_coverages:
        return {
            "provided": False,
            "explicitAnchorCount": 0,
            "signatureAnchorCount": 0,
            "combinedAnchorCount": 0,
            "readyForObjectDiscovery": False,
            "readyForHookPlanning": False,
            "readyForPackageLoading": False,
            "targetCoverageFieldsPresent": False,
            "readyForTargetObjectDiscovery": False,
            "readyForTargetHookPlanning": False,
            "readyForTargetPackageLoading": False,
            "missingRequiredGroups": [],
            "groups": {},
        }
    explicit_anchors = set()
    signature_anchors = set()
    combined_anchors = set()
    missing_required_groups = set()
    group_totals = {}
    group_present = {}
    group_target_present = {}
    group_loader_present = {}
    group_unknown_present = {}
    ready_for_object_discovery = False
    ready_for_hook_planning = False
    ready_for_package_loading = False
    ready_for_target_object_discovery = False
    ready_for_target_hook_planning = False
    ready_for_target_package_loading = False
    target_coverage_fields_present = False
    for coverage in anchor_coverages:
        coverage_groups = coverage.get("groups", {}) or {}
        if "readyForObjectDiscovery" not in coverage:
            ready_for_object_discovery = ready_for_object_discovery or all(
                int((coverage_groups.get(group_name) or {}).get("present", 0) or 0) > 0
                for group_name in ("names", "objects", "world")
            )
        if "readyForHookPlanning" not in coverage:
            dispatch = coverage_groups.get("dispatch") or {}
            ready_for_hook_planning = ready_for_hook_planning or (
                all(
                    int((coverage_groups.get(group_name) or {}).get("present", 0) or 0) > 0
                    for group_name in ("names", "objects", "world")
                )
                and int(dispatch.get("present", 0) or 0) > 0
            )
        if "readyForPackageLoading" not in coverage:
            package = coverage_groups.get("package") or {}
            ready_for_package_loading = (
                ready_for_package_loading
                or int(package.get("present", 0) or 0) > 0
            )
        explicit_anchors.update(coverage.get("explicitAnchors", []))
        signature_anchors.update(coverage.get("signatureAnchors", []))
        combined_anchors.update(coverage.get("combinedAnchors", []))
        missing_required_groups.update(coverage.get("missingRequiredGroups", []))
        ready_for_object_discovery = ready_for_object_discovery or coverage.get("readyForObjectDiscovery", False)
        ready_for_hook_planning = ready_for_hook_planning or coverage.get("readyForHookPlanning", False)
        ready_for_package_loading = ready_for_package_loading or coverage.get("readyForPackageLoading", False)
        if any(
            key in coverage
            for key in (
                "readyForTargetObjectDiscovery",
                "readyForTargetHookPlanning",
                "readyForTargetPackageLoading",
            )
        ):
            target_coverage_fields_present = True
            ready_for_target_object_discovery = (
                ready_for_target_object_discovery
                or coverage.get("readyForTargetObjectDiscovery", False)
            )
            ready_for_target_hook_planning = (
                ready_for_target_hook_planning
                or coverage.get("readyForTargetHookPlanning", False)
            )
            ready_for_target_package_loading = (
                ready_for_target_package_loading
                or coverage.get("readyForTargetPackageLoading", False)
            )
        for group_name, group in coverage_groups.items():
            group_totals[group_name] = max(group_totals.get(group_name, 0), group.get("total", 0))
            group_present[group_name] = max(group_present.get(group_name, 0), group.get("present", 0))
            if "targetPresent" in group:
                group_target_present[group_name] = max(
                    group_target_present.get(group_name, 0),
                    group.get("targetPresent", 0),
                )
            if "loaderPresent" in group:
                group_loader_present[group_name] = max(
                    group_loader_present.get(group_name, 0),
                    group.get("loaderPresent", 0),
                )
            if "unknownPresent" in group:
                group_unknown_present[group_name] = max(
                    group_unknown_present.get(group_name, 0),
                    group.get("unknownPresent", 0),
                )
    groups = {}
    for group_name in sorted(group_totals):
        present = group_present.get(group_name, 0)
        group_row = {
            "present": group_present.get(group_name, 0),
            "total": group_totals[group_name],
            "complete": present == group_totals[group_name],
        }
        if group_name in group_target_present:
            group_row["targetPresent"] = group_target_present.get(group_name, 0)
            group_row["targetComplete"] = group_target_present.get(group_name, 0) == group_totals[group_name]
        if group_name in group_loader_present:
            group_row["loaderPresent"] = group_loader_present.get(group_name, 0)
        if group_name in group_unknown_present:
            group_row["unknownPresent"] = group_unknown_present.get(group_name, 0)
        groups[group_name] = group_row
    return {
        "provided": True,
        "explicitAnchorCount": len(explicit_anchors),
        "signatureAnchorCount": len(signature_anchors),
        "combinedAnchorCount": len(combined_anchors),
        "readyForObjectDiscovery": ready_for_object_discovery,
        "readyForHookPlanning": ready_for_hook_planning,
        "readyForPackageLoading": ready_for_package_loading,
        "targetCoverageFieldsPresent": target_coverage_fields_present,
        "readyForTargetObjectDiscovery": (
            ready_for_target_object_discovery
            if target_coverage_fields_present
            else ready_for_object_discovery
        ),
        "readyForTargetHookPlanning": (
            ready_for_target_hook_planning
            if target_coverage_fields_present
            else ready_for_hook_planning
        ),
        "readyForTargetPackageLoading": (
            ready_for_target_package_loading
            if target_coverage_fields_present
            else ready_for_package_loading
        ),
        "missingRequiredGroups": sorted(missing_required_groups),
        "groups": groups,
    }


def object_discovery_coverage_status(merged, gate_map):
    components = {
        "coreAnchors": {
            "passed": gate_map["ue-names"] and gate_map["ue-objects"] and gate_map["ue-world"],
            "evidence": {
                "ue": merged["ue"]["groups"],
            },
        },
        "pointerProbe": {
            "passed": gate_map["ue-pointer-probe"],
            "evidence": {
                "mapped": merged["mappedUePointerCount"],
                "total": merged["uePointerCount"],
            },
        },
        "layoutProbe": {
            "passed": gate_map["ue-layout-probe"],
            "evidence": {
                "readable": merged["readableUeLayoutCount"],
                "total": merged["ueLayoutCount"],
                "mappedSlots": merged["mappedUeLayoutSlotCount"],
            },
        },
        "uobjectProbe": {
            "passed": gate_map["ue-uobject-probe"],
            "evidence": {
                "candidates": merged["candidateUeUObjectCount"],
                "classMapped": merged["classMappedUeUObjectCount"],
            },
        },
        "objectRegistry": {
            "passed": (
                gate_map["lua-object-registry"]
                and gate_map["lua-object-registry-checks"]
                and gate_map["lua-object-registry-runtime"]
            ),
            "evidence": {
                "ueCandidates": merged["ueLuaObjectRegistryCount"],
                "runtimeUeCandidates": merged["runtimeUeLuaObjectRegistryCount"],
                "selfTestUeCandidates": merged["selfTestUeLuaObjectRegistryCount"],
                "added": merged["addedLuaObjectRegistryCount"],
                "total": merged["luaObjectRegistryCount"],
                "checks": merged["passedLuaObjectRegistryCheckCount"],
                "totalChecks": merged["luaObjectRegistryCheckCount"],
            },
        },
        "decodedAliases": {
            "passed": gate_map["lua-decoded-object-aliases"] and gate_map["lua-decoded-object-aliases-runtime"],
            "evidence": {
                "added": merged["decodedLuaObjectAliasRegistryCount"],
                "runtime": merged["runtimeDecodedLuaObjectAliasRegistryCount"],
                "selfTest": merged["selfTestDecodedLuaObjectAliasRegistryCount"],
                "skippedDuplicates": merged["skippedDecodedLuaObjectAliasRegistryCount"],
            },
        },
        "objectArray": {
            "passed": gate_map["ue-object-array-registry"] and gate_map["ue-object-array-registry-runtime"],
            "evidence": {
                "registered": merged["objectArrayLuaObjectRegistryCount"],
                "runtimeRegistered": merged["runtimeObjectArrayLuaObjectRegistryCount"],
                "selfTestRegistered": merged["selfTestObjectArrayLuaObjectRegistryCount"],
                "finished": merged["finishedUeObjectArrayCount"],
                "total": merged["ueObjectArrayCount"],
                "shapes": merged["ueObjectArrayShapeCount"],
                "plausibleShapes": merged["plausibleUeObjectArrayShapeCount"],
                "implausibleShapes": merged["implausibleUeObjectArrayShapeCount"],
            },
        },
        "nativeIdentities": {
            "passed": gate_map["ue-object-native-identities"],
            "evidence": {
                "promoted": merged["promotedUeObjectNativeIdentityCount"],
                "total": merged["ueObjectNativeIdentityCount"],
                "decodedNames": merged["decodedNameUeObjectNativeIdentityCount"],
                "decodedClasses": merged["decodedClassNameUeObjectNativeIdentityCount"],
            },
        },
        "internalFlags": {
            "passed": gate_map["ue-object-internal-flags"],
            "evidence": {
                "readable": merged["internalFlagUeObjectArrayItemCount"],
                "nonzero": merged["nonzeroInternalFlagUeObjectArrayItemCount"],
                "items": merged["ueObjectArrayItemCount"],
            },
        },
        "fnameDecoder": {
            "passed": gate_map["ue-fname-decoder"],
            "evidence": {
                "decoded": merged["decodedUeFNameCount"],
                "total": merged["ueFNameCount"],
            },
        },
        "outerChainIdentities": {
            "passed": gate_map["lua-object-outer-chain-identities"],
            "evidence": {
                "identity": merged["luaObjectOuterChainIdentityCount"],
                "resolved": merged["resolvedLuaObjectOuterChainCount"],
                "total": merged["luaObjectOuterChainCount"],
            },
        },
        "luaFindObjectApi": {
            "passed": gate_map["lua-object-api"],
            "evidence": {
                "mods": merged["luaObjectApiModFinishCount"],
                "selfTests": merged["passedLuaObjectApiSelfTestCount"],
            },
        },
    }
    object_required = (
        "coreAnchors",
        "pointerProbe",
        "layoutProbe",
        "uobjectProbe",
        "decodedAliases",
        "internalFlags",
        "fnameDecoder",
    )
    find_object_required = object_required + (
        "objectRegistry",
        "objectArray",
        "nativeIdentities",
        "outerChainIdentities",
        "luaFindObjectApi",
    )
    missing_object = [name for name in object_required if not components[name]["passed"]]
    missing_find_object = [name for name in find_object_required if not components[name]["passed"]]
    return {
        "schemaVersion": "dune-ue-object-discovery-coverage/v1",
        "components": components,
        "requiredObjectDiscoveryComponents": list(object_required),
        "requiredFindObjectComponents": list(find_object_required),
        "missingObjectDiscoveryComponents": missing_object,
        "missingFindObjectComponents": missing_find_object,
        "readyForObjectDiscovery": not missing_object,
        "readyForFindObjectSemantics": not missing_find_object,
    }


def build_per_loader_readiness(log_summaries, validation_summaries, anchor_coverages, loaders):
    per_loader = {}
    paths = sorted({summary.get("path", "") for summary in log_summaries if summary.get("path")})
    target_image_substrings = effective_target_image_substrings(
        [
            fragment
            for summary in log_summaries
            for fragment in (summary.get("targetImageSubstrings", []) or [])
        ]
    )
    for loader in loaders:
        scoped_summaries = []
        scoped_paths = []
        for path_text in paths:
            summary = summarize_log(Path(path_text), [loader], [], target_image_substrings)
            if summary["scan"].get("loadCount", 0) <= 0:
                continue
            scoped_summaries.append(summary)
            scoped_paths.append(path_text)
        if not scoped_summaries:
            per_loader[loader] = {
                "logCount": 0,
                "paths": [],
                "ready": {},
                "failedGates": ["loader-loaded"],
                "nextSteps": [f"collect a scoped loader log for {loader}"],
            }
            continue
        report = build_report(
            scoped_summaries,
            validation_summaries,
            anchor_coverages,
            include_loader_matrix=False,
        )
        per_loader[loader] = {
            "logCount": report["logCount"],
            "paths": scoped_paths,
            "loaders": report["loaders"],
            "ready": report["ready"],
            "gates": report["gates"],
            "failedGates": [item["name"] for item in report["gates"] if not item["passed"]],
            "anchorGroups": report.get("anchorGroups", {}),
            "anchorCoverage": report.get("anchorCoverage", {}),
            "objectDiscoveryCoverage": report.get("objectDiscoveryCoverage", {}),
            "liveTargetImageCanaryContract": report.get("liveTargetImageCanaryContract", {}),
            "signatures": report.get("signatures", {}),
            "ue": report.get("ue", {}),
            "canaryHints": report.get("canaryHints", {}),
            "nextSteps": report["nextSteps"],
        }
    return per_loader


def build_report(log_summaries, validation_summaries, anchor_coverages=None, include_loader_matrix=True):
    merged = merge_log_summaries(log_summaries)
    ue = merged["ue"]
    signatures = signature_validation_status(validation_summaries)
    anchor_coverage = anchor_coverage_status(anchor_coverages or [])

    gates = []
    gates.append(
        gate(
            "loader-loaded",
            merged["loadCount"] > 0,
            f"loads={merged['loadCount']} loaders={','.join(merged['loaders']) or 'unknown'}",
            "no loader loaded event in scoped logs",
        )
    )
    target_image_substrings = merged["targetImageSubstrings"]
    target_image_paths = [
        path
        for path in merged["loadedExes"] + merged["modules"]
        if is_target_image_path(path, target_image_substrings)
    ]
    gates.append(
        gate(
            "target-image-process",
            bool(target_image_paths),
            (
                f"targetPaths={len(target_image_paths)} "
                f"loadedExes={len(merged['loadedExes'])} modules={len(merged['modules'])} "
                f"targetFilters={','.join(target_image_substrings)}"
            ),
            "scoped logs did not include a configured target executable or module; rerun the canary against the real game/server process or pass --exe-substring for this title",
        )
    )
    gates.append(
        gate(
            "scan-completed",
            merged["scanStartCount"] > 0 and merged["scanFinishCount"] >= merged["scanStartCount"],
            f"starts={merged['scanStartCount']} finishes={merged['scanFinishCount']}",
            "scan did not start and finish cleanly",
        )
    )
    runtime_discovery = merged["ueRuntimeDiscovery"]
    runtime_root_validation = {
        "ready": {"RuntimeFNamePool", "RuntimeGUObjectArray"}.issubset(
            runtime_discovery.get("rootValidationNames") or []
        ),
        "validatedNames": runtime_discovery.get("rootValidationNames") or [],
        "readyScanCount": runtime_discovery.get("rootValidationReadyScanCount", 0),
        "validatedBy": runtime_discovery.get("validatedBy", {}),
    }
    gates.append(
        gate(
            "ue-runtime-root-validation",
            runtime_root_validation["ready"],
            (
                f"validated={runtime_root_validation['validatedNames']} "
                f"readyScans={runtime_root_validation['readyScanCount']} "
                f"validatedBy={runtime_root_validation['validatedBy']}"
            ),
            "runtime roots have not been validated through both FName and GUObjectArray consumers",
        )
    )
    gates.append(
        gate(
            "ue-runtime-root-discovery",
            runtime_discovery["ready"],
            (
                f"starts={runtime_discovery['startCount']} finishes={runtime_discovery['finishCount']} "
                f"promoted={runtime_discovery['promotedNames']} "
                f"coverage={runtime_discovery['coverage']} "
                f"failures={runtime_discovery['failureCounts']}"
            ),
            "runtime root auto-discovery has not validated both RuntimeFNamePool and RuntimeGUObjectArray through FName/object-array consumers",
        )
    )
    for group in CORE_GROUPS:
        data = ue["groups"][group]
        gates.append(
            gate(
                f"ue-{group}",
                data["present"] > 0,
                f"present={data['present']}/{data['total']}",
                f"missing {group} anchor group",
            )
        )
        gates.append(
            gate(
                f"ue-target-{group}",
                data.get("targetPresent", 0) > 0,
                f"targetPresent={data.get('targetPresent', 0)}/{data['total']} present={data['present']}/{data['total']}",
                f"missing target-image {group} anchor group",
            )
        )
    reflection = ue["groups"][REFLECTION_GROUP]
    package = ue["groups"][PACKAGE_GROUP]
    gates.append(
        gate(
            "ue-package-loading-surface",
            package["present"] > 0,
            f"present={package['present']}/{package['total']}",
            "no StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchor evidence",
        )
    )
    gates.append(
        gate(
            "ue-target-package-loading-surface",
            package.get("targetPresent", 0) > 0,
            f"targetPresent={package.get('targetPresent', 0)}/{package['total']} present={package['present']}/{package['total']}",
            "no target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchor evidence",
        )
    )
    gates.append(
        gate(
            "ue-reflection-surface",
            reflection["present"] >= 2,
            f"present={reflection['present']}/{reflection['total']}",
            "need at least two reflection anchors before reflection reader work",
        )
    )
    gates.append(
        gate(
            "ue-target-reflection-surface",
            reflection.get("targetPresent", 0) >= 2,
            f"targetPresent={reflection.get('targetPresent', 0)}/{reflection['total']} present={reflection['present']}/{reflection['total']}",
            "need at least two target-image reflection anchors before reflection reader work",
        )
    )
    gates.append(
        gate(
            "ue-reflection-probe",
            merged["classMappedUeReflectionCount"] > 0
            and merged["mappedUeReflectionSlotCount"] > 0,
            (
                f"classMapped={merged['classMappedUeReflectionCount']}/{merged['ueReflectionCount']} "
                f"mappedSlots={merged['mappedUeReflectionSlotCount']}/{merged['ueReflectionSlotCount']}"
            ),
            "no read-only UClass reflection probe found a mapped class with mapped field/function slots",
        )
    )
    gates.append(
        gate(
            "ue-reflection-field-walk",
            merged["candidateUeReflectionFieldCount"] > 0
            and merged["classMappedUeReflectionFieldCount"] > 0,
            (
                f"candidates={merged['candidateUeReflectionFieldCount']}/{merged['ueReflectionFieldCount']} "
                f"classMapped={merged['classMappedUeReflectionFieldCount']}"
            ),
            "no bounded UClass field/function chain walk produced class-mapped reflected field candidates",
        )
    )
    gates.append(
        gate(
            "ue-reflection-property-descriptors",
            merged["candidateUeReflectionPropertyCount"] > 0
            and merged["readableUeReflectionPropertyCount"] > 0,
            (
                f"candidates={merged['candidateUeReflectionPropertyCount']}/{merged['ueReflectionPropertyCount']} "
                f"readable={merged['readableUeReflectionPropertyCount']}"
            ),
            "no bounded FProperty descriptor probe produced readable property metadata",
        )
    )
    gates.append(
        gate(
            "ue-reflection-property-descriptors-runtime",
            merged["runtimeUeReflectionPropertyCount"] > 0
            and merged["runtimeReadableUeReflectionPropertyCount"] > 0,
            (
                f"runtime={merged['runtimeReadableUeReflectionPropertyCount']}/"
                f"{merged['runtimeUeReflectionPropertyCount']} "
                f"readable={merged['readableUeReflectionPropertyCount']}"
            ),
            "no bounded FProperty descriptor probe produced readable non-self-test runtime property metadata",
        )
    )
    gates.append(
        gate(
            "ue-function-param-descriptors",
            merged["rootedUeFunctionParamRootCount"] > 0
            and merged["candidateUeFunctionParamCount"] > 0
            and merged["readableUeFunctionParamCount"] > 0,
            (
                f"roots={merged['rootedUeFunctionParamRootCount']}/{merged['ueFunctionParamRootCount']} "
                f"descriptors={merged['readableUeFunctionParamCount']}/{merged['ueFunctionParamCount']}"
            ),
            "no bounded UFunction param descriptor probe produced readable param metadata",
        )
    )
    gates.append(
        gate(
            "ue-function-param-container-children",
            merged["decodedUeFunctionParamContainerChildCount"] > 0,
            (
                f"decoded={merged['decodedUeFunctionParamContainerChildCount']} "
                f"candidates={merged['candidateUeFunctionParamContainerChildCount']}/"
                f"{merged['ueFunctionParamContainerChildCount']}"
            ),
            "no bounded UFunction container param scan produced decoded inner/key/value child property metadata",
        )
    )
    gates.append(
        gate(
            "ue-function-identities",
            merged["namedUeFunctionParamCount"] > 0
            and merged["uniqueUeFunctionPathCount"] > 0,
            (
                f"named={merged['namedUeFunctionParamCount']}/{merged['readableUeFunctionParamCount']} "
                f"paths={merged['uniqueUeFunctionPathCount']} "
                f"sample={merged['ueFunctionPaths'][:3]}"
            ),
            "no decoded UFunction identity produced a Lua-visible runtime function path",
        )
    )
    gates.append(
        gate(
            "ue-function-native-identities",
            merged["promotedUeFunctionNativeIdentityCount"] > 0
            and merged["readableFlagUeFunctionNativeIdentityCount"] > 0
            and merged["runtimePathUeFunctionNativeIdentityCount"] > 0
            and merged["ue4ssPathUeFunctionNativeIdentityCount"] > 0,
            (
                f"promoted={merged['promotedUeFunctionNativeIdentityCount']}/{merged['ueFunctionNativeIdentityCount']} "
                f"flags={merged['readableFlagUeFunctionNativeIdentityCount']} "
                f"runtimePaths={merged['runtimePathUeFunctionNativeIdentityCount']} "
                f"ue4ssPaths={merged['ue4ssPathUeFunctionNativeIdentityCount']}"
            ),
            "no UFunction root promoted readable flags plus UE4SS and runtime path identity into Lua-visible function handles",
        )
    )
    gates.append(
        gate(
            "ue-function-flags",
            merged["readableUeFunctionFlagRootCount"] > 0
            and merged["readableUeFunctionFlagParamCount"] > 0
            and merged["ueFunctionFlagPathCount"] > 0,
            (
                f"roots={merged['readableUeFunctionFlagRootCount']} "
                f"descriptors={merged['readableUeFunctionFlagParamCount']} "
                f"paths={merged['ueFunctionFlagPathCount']} "
                f"values={merged['ueFunctionFlagValues'][:4]}"
            ),
            "no bounded UFunction probe produced readable FunctionFlags promoted to Lua-visible function handles",
        )
    )
    gates.append(
        gate(
            "ue-reflection-property-values",
            merged["readUeReflectionValueCount"] > 0,
            f"read={merged['readUeReflectionValueCount']}/{merged['ueReflectionValueCount']}",
            "no bounded reflected property value probe read container bytes",
        )
    )
    gates.append(
        gate(
            "ue-reflection-property-values-runtime",
            merged["runtimeDescriptorMatchedReadUeReflectionValueCount"] > 0,
            (
                f"descriptorMatched={merged['runtimeDescriptorMatchedReadUeReflectionValueCount']} "
                f"runtimeRead={merged['runtimeReadUeReflectionValueCount']} "
                f"read={merged['readUeReflectionValueCount']}/{merged['ueReflectionValueCount']}"
            ),
            "no bounded reflected property value probe read bytes matching a readable non-self-test runtime descriptor",
        )
    )
    gates.append(
        gate(
            "ue-pointer-probe",
            merged["mappedUePointerCount"] > 0,
            f"targetMapped={merged['mappedUePointerCount']}/{merged['uePointerCount']}",
            "no UE anchor pointer probe resolved to a mapped target",
        )
    )
    gates.append(
        gate(
            "ue-layout-probe",
            merged["readableUeLayoutCount"] > 0 and merged["mappedUeLayoutSlotCount"] > 0,
            f"readable={merged['readableUeLayoutCount']}/{merged['ueLayoutCount']} mappedSlots={merged['mappedUeLayoutSlotCount']}/{merged['ueLayoutSlotCount']}",
            "no UE layout probe produced a readable target with mapped pointer slots",
        )
    )
    gates.append(
        gate(
            "ue-uobject-probe",
            merged["candidateUeUObjectCount"] > 0 and merged["classMappedUeUObjectCount"] > 0,
            f"candidates={merged['candidateUeUObjectCount']}/{merged['ueUObjectCount']} classMapped={merged['classMappedUeUObjectCount']}",
            "no UObjectBase candidate probe produced a class-mapped object candidate",
        )
    )
    gates.append(
        gate(
            "signature-manifest-exact",
            signatures["exactOnly"],
            f"patterns={signatures['patternCount']} statuses={signatures['statusCounts']}",
            "no exact same-build signature validation, or at least one signature is missing/ambiguous/moved",
        )
    )
    gates.append(
        gate(
            "signature-manifest-promotable",
            signatures["allPromotable"],
            f"promotable={signatures['promotableCount']}/{signatures['patternCount']}",
            "no promotable signature validation, or at least one signature is missing/ambiguous",
        )
    )
    anchor_group_evidence_count = merged["ueAnchorSignatureCount"] + sum(merged["ueAnchorGroupCounts"].values())
    missing_anchor_group_count = (
        merged["ueAnchorSignatureGroupCounts"].get("missing", 0)
        + merged["ueAnchorGroupCounts"].get("missing", 0)
    )
    gates.append(
        gate(
            "ue-anchor-group-provenance",
            anchor_group_evidence_count > 0 and missing_anchor_group_count == 0,
            (
                f"anchors={merged['ueAnchorGroupCounts']} "
                f"signatures={merged['ueAnchorSignatureGroupCounts']}"
            ),
            "mapped anchors or anchor signatures are missing loader-normalized group provenance",
        )
    )
    gates.append(
        gate(
            "anchor-coverage-object-discovery",
            (not anchor_coverage["provided"]) or anchor_coverage["readyForTargetObjectDiscovery"],
            (
                "not-provided" if not anchor_coverage["provided"]
                else (
                    f"combined={anchor_coverage['combinedAnchorCount']} "
                    f"targetReady={anchor_coverage['readyForTargetObjectDiscovery']} "
                    f"missingRequired={anchor_coverage['missingRequiredGroups']} "
                    f"groups={anchor_coverage['groups']}"
                )
            ),
            "prepared canary anchor coverage is missing a required target-image object-discovery anchor group",
        )
    )
    gates.append(
        gate(
            "anchor-coverage-hook-planning",
            (not anchor_coverage["provided"]) or anchor_coverage["readyForTargetHookPlanning"],
            (
                "not-provided" if not anchor_coverage["provided"]
                else (
                    f"combined={anchor_coverage['combinedAnchorCount']} "
                    f"targetReady={anchor_coverage['readyForTargetHookPlanning']} "
                    f"signatureAnchors={anchor_coverage['signatureAnchorCount']} "
                    f"dispatch={anchor_coverage['groups'].get('dispatch', {})}"
                )
            ),
            "prepared canary anchor coverage does not include target-image ProcessEvent-level dispatch evidence for hook planning",
        )
    )
    gates.append(
        gate(
            "anchor-coverage-package-loading",
            (not anchor_coverage["provided"]) or anchor_coverage["readyForTargetPackageLoading"],
            (
                "not-provided" if not anchor_coverage["provided"]
                else (
                    f"targetReady={anchor_coverage['readyForTargetPackageLoading']} "
                    f"groups={anchor_coverage['groups'].get('package', {})}"
                )
            ),
            "prepared canary anchor coverage does not include target-image package-loading anchor evidence",
        )
    )
    gates.append(
        gate(
            "hook-dispatch-self-test",
            merged["passedHookSelfTestCount"] > 0,
            f"passed={merged['passedHookSelfTestCount']}/{merged['hookSelfTestCount']}",
            "no guarded hook-dispatch self-test passed in scoped logs",
        )
    )
    gates.append(
        gate(
            "mod-dispatch-self-test",
            merged["passedModSelfTestCount"] > 0,
            f"passed={merged['passedModSelfTestCount']}/{merged['modSelfTestCount']}",
            "no native mod-dispatch lifecycle self-test passed in scoped logs",
        )
    )
    gates.append(
        gate(
            "lua-dispatch-self-test",
            merged["passedLuaSelfTestCount"] > 0
            and merged["passedLuaCallbackSelfTestCount"] > 0
            and merged["passedLuaApiSelfTestCount"] > 0,
            (
                f"passed={merged['passedLuaSelfTestCount']}/{merged['luaSelfTestCount']} "
                f"callbackBridge={merged['passedLuaCallbackSelfTestCount']} "
                f"apiSurface={merged['passedLuaApiSelfTestCount']}"
            ),
            "no Lua runtime execution plus callback-bridge and API-surface self-test passed in scoped logs",
        )
    )
    gates.append(
        gate(
            "lua-scheduler-api",
            merged["passedLuaSchedulerApiSelfTestCount"] > 0,
            f"selfTest={merged['passedLuaSchedulerApiSelfTestCount']}",
            "no Lua scheduler API self-test proved ExecuteInGameThread, ExecuteAsync, ExecuteWithDelay, and LoopAsync",
        )
    )
    gates.append(
        gate(
            "lua-scheduler-api-mods",
            merged["luaSchedulerApiModFinishCount"] > 0,
            f"mods={merged['luaSchedulerApiModFinishCount']}",
            "no loaded Lua mod proved ExecuteInGameThread, ExecuteAsync, ExecuteWithDelay, LoopAsync, and scheduler cancellation",
        )
    )
    gates.append(
        gate(
            "lua-input-command-api",
            merged["passedLuaInputCommandApiSelfTestCount"] > 0,
            f"selfTest={merged['passedLuaInputCommandApiSelfTestCount']}",
            "no Lua input/console command API self-test proved keybind registration/lookup/dispatch plus named and global console command handler dispatch",
        )
    )
    gates.append(
        gate(
            "lua-input-command-api-mods",
            merged["luaInputCommandApiModFinishCount"] > 0,
            f"mods={merged['luaInputCommandApiModFinishCount']}",
            "no loaded Lua mod proved keybind dispatch/unregister plus named/global console command handler dispatch/unregister",
        )
    )
    gates.append(
        gate(
            "lua-object-api",
            merged["passedLuaObjectApiSelfTestCount"] > 0
            and merged["luaObjectApiModFinishCount"] > 0,
            (
                f"selfTest={merged['passedLuaObjectApiSelfTestCount']} "
                f"mods={merged['luaObjectApiModFinishCount']}"
            ),
            "no Lua object lookup/enumeration API self-test and mod-entrypoint use passed in scoped logs",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-backend-state",
            merged["luaLoadAssetBackendStateModFinishCount"] > 0,
            f"mods={merged['luaLoadAssetBackendStateModFinishCount']}",
            "no Lua mod exercised the guarded LoadAsset backend-state contract",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-backend-anchors",
            merged["luaLoadAssetBackendAnchorModFinishCount"] > 0,
            f"mods={merged['luaLoadAssetBackendAnchorModFinishCount']}",
            "no Lua mod exercised LoadAsset backend state while package-loading anchors were resolved",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-preflight",
            merged["luaLoadAssetPackagePreflightModFinishCount"] > 0,
            f"mods={merged['luaLoadAssetPackagePreflightModFinishCount']}",
            "no Lua mod requested package-backed LoadAsset and observed the guarded native-bridge gate",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-bridge-state",
            merged["luaLoadAssetPackageBridgeStateModFinishCount"] > 0,
            f"mods={merged['luaLoadAssetPackageBridgeStateModFinishCount']}",
            "no Lua mod queried the guarded LoadAsset package bridge state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-native-invoke",
            merged["luaLoadAssetPackageNativeInvokeModFinishCount"] > 0,
            f"mods={merged['luaLoadAssetPackageNativeInvokeModFinishCount']}",
            "no Lua mod exercised the guarded LoadAsset package native invocation gate",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-abi-state",
            merged["luaLoadAssetPackageAbiStateEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageAbiStateEventCount']}",
            "no Lua mod queried the guarded LoadAsset package native ABI contract",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-string-bridge",
            merged["luaLoadAssetPackageStringBridgeEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageStringBridgeEventCount']}",
            "no Lua mod staged guarded LoadAsset package path input for the native string bridge",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-native-buffer",
            merged["luaLoadAssetPackageNativeBufferEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageNativeBufferEventCount']}",
            "no Lua mod prepared the guarded LoadAsset package native input buffer descriptor",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-tchar-buffer",
            merged["luaLoadAssetPackageTCharBufferEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageTCharBufferEventCount']}",
            "no Lua mod prepared the guarded LoadAsset package TCHAR layout descriptor",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-tchar-verification",
            merged["luaLoadAssetPackageTCharVerificationEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageTCharVerificationEventCount']}",
            "no Lua mod queried the guarded LoadAsset package TCHAR verification state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-call-frame",
            merged["luaLoadAssetPackageCallFrameEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageCallFrameEventCount']}",
            "no Lua mod prepared the guarded LoadAsset package native call-frame descriptor",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-call-frame-verification",
            merged["luaLoadAssetPackageCallFrameVerificationEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageCallFrameVerificationEventCount']}",
            "no Lua mod queried the guarded LoadAsset package call-frame verification state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-crash-guard",
            merged["luaLoadAssetPackageCrashGuardEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageCrashGuardEventCount']}",
            "no Lua mod queried the guarded LoadAsset package crash-guard state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-guarded-call",
            merged["luaLoadAssetPackageGuardedCallEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageGuardedCallEventCount']}",
            "no Lua mod queried the guarded LoadAsset package guarded-call state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-return-validation",
            merged["luaLoadAssetPackageReturnValidationEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageReturnValidationEventCount']}",
            "no Lua mod queried the guarded LoadAsset package return-validation state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-native-call-adapter",
            merged["luaLoadAssetPackageNativeCallAdapterEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageNativeCallAdapterEventCount']}",
            "no Lua mod queried the guarded LoadAsset package native call-adapter state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-invocation-descriptor",
            merged["luaLoadAssetPackageInvocationDescriptorEventCount"] > 0,
            f"events={merged['luaLoadAssetPackageInvocationDescriptorEventCount']}",
            "no Lua mod queried the guarded LoadAsset package invocation descriptor state",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-native-executor",
            merged["luaLoadAssetPackageNativeExecutorTargetReadyEventCount"] > 0,
            (
                f"targetReady={merged['luaLoadAssetPackageNativeExecutorTargetReadyEventCount']} "
                f"ready={merged['luaLoadAssetPackageNativeExecutorReadyEventCount']} "
                f"events={merged['luaLoadAssetPackageNativeExecutorEventCount']}"
            ),
            "no Lua mod proved the guarded LoadAsset package native executor reached ready/final-call-eligible state for a target-image package-loading anchor",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package-native-invocation",
            merged["luaLoadAssetPackageNativeInvokedEventCount"] > 0,
            f"nativeInvoked={merged['luaLoadAssetPackageNativeInvokedEventCount']}",
            "no guarded LoadAsset package native invocation reached target-image native code and returned under validation",
        )
    )
    gates.append(
        gate(
            "lua-load-asset-package",
            merged["luaLoadAssetPackageModFinishCount"] > 0
            and merged["luaLoadAssetPackageNativeExecutorTargetReadyEventCount"] > 0
            and merged["luaLoadAssetPackageNativeInvokedEventCount"] > 0,
            (
                f"mods={merged['luaLoadAssetPackageModFinishCount']} "
                f"targetExecutorReady={merged['luaLoadAssetPackageNativeExecutorTargetReadyEventCount']} "
                f"nativeInvoked={merged['luaLoadAssetPackageNativeInvokedEventCount']}"
            ),
            "no Lua mod proved LoadAsset resolved through a real package/asset backend with target-image native invocation evidence",
        )
    )
    gates.append(
        gate(
            "lua-load-class-package-abi-state",
            merged["luaLoadClassPackageAbiStateEventCount"] > 0,
            f"events={merged['luaLoadClassPackageAbiStateEventCount']}",
            "no Lua mod queried the guarded LoadClass package StaticLoadClass ABI contract",
        )
    )
    gates.append(
        gate(
            "lua-load-class-package-call-frame-verification",
            merged["luaLoadClassPackageCallFrameVerificationEventCount"] > 0,
            f"events={merged['luaLoadClassPackageCallFrameVerificationEventCount']}",
            "no Lua mod queried the guarded LoadClass package call-frame verification state",
        )
    )
    gates.append(
        gate(
            "lua-load-class-package-native-executor",
            merged["luaLoadClassPackageNativeExecutorReadyEventCount"] > 0,
            (
                f"ready={merged['luaLoadClassPackageNativeExecutorReadyEventCount']} "
                f"events={merged['luaLoadClassPackageNativeExecutorEventCount']}"
            ),
            "no Lua mod proved the guarded LoadClass package native executor reached ready/final-call-eligible state for target-image StaticLoadClass",
        )
    )
    gates.append(
        gate(
            "lua-load-class-package-native-invocation",
            merged["luaLoadClassPackageNativeInvokedEventCount"] > 0,
            f"nativeInvoked={merged['luaLoadClassPackageNativeInvokedEventCount']}",
            "no guarded LoadClass package native invocation reached target-image StaticLoadClass",
        )
    )
    gates.append(
        gate(
            "lua-function-iteration",
            merged["luaFunctionIterationModFinishCount"] > 0
            and merged["passedLuaFunctionIterationCheckCount"] > 0,
            (
                f"mods={merged['luaFunctionIterationModFinishCount']} "
                f"checks={merged['passedLuaFunctionIterationCheckCount']}/"
                f"{merged['luaFunctionIterationCheckCount']}"
            ),
            "no Lua mod plus native self-check proved ForEachFunction enumerated promoted UFunction handles from an owner/class handle",
        )
    )
    gates.append(
        gate(
            "lua-function-iteration-runtime",
            merged["runtimeLuaFunctionIterationCheckCount"] > 0,
            (
                f"runtime={merged['runtimeLuaFunctionIterationCheckCount']} "
                f"selfTest={merged['selfTestLuaFunctionIterationCheckCount']} "
                f"passed={merged['passedLuaFunctionIterationCheckCount']}"
            ),
            "no native self-check proved ForEachFunction enumerated promoted UFunction handles from a non-self-test owner/class handle",
        )
    )
    gates.append(
        gate(
            "lua-process-console-exec-hooks",
            merged["luaProcessConsoleExecHookModFinishCount"] > 0,
            f"mods={merged['luaProcessConsoleExecHookModFinishCount']}",
            "no Lua mod proved RegisterProcessConsoleExecPreHook/PostHook dispatch around loader-owned ProcessConsoleExec",
        )
    )
    gates.append(
        gate(
            "lua-local-player-exec-hooks",
            merged["luaLocalPlayerExecHookModFinishCount"] > 0,
            f"mods={merged['luaLocalPlayerExecHookModFinishCount']}",
            "no Lua mod proved RegisterULocalPlayerExecPreHook/PostHook dispatch around loader-owned ULocalPlayerExec",
        )
    )
    gates.append(
        gate(
            "lua-call-function-hooks",
            merged["luaCallFunctionHookModFinishCount"] > 0,
            f"mods={merged['luaCallFunctionHookModFinishCount']}",
            "no Lua mod proved RegisterCallFunctionByNameWithArgumentsPreHook/PostHook dispatch around loader-owned CallFunction",
        )
    )
    gates.append(
        gate(
            "lua-call-function-structured-args",
            merged["luaCallFunctionStructuredArgsModFinishCount"] > 0,
            f"mods={merged['luaCallFunctionStructuredArgsModFinishCount']}",
            "no Lua mod proved structured table argument marshalling for CallFunctionByNameWithArguments",
        )
    )
    gates.append(
        gate(
            "lua-process-event-compat",
            merged["luaProcessEventCompatModFinishCount"] > 0,
            f"mods={merged['luaProcessEventCompatModFinishCount']}",
            "no Lua mod proved global and UObject-method ProcessEvent compatibility dispatch",
        )
    )
    gates.append(
        gate(
            "lua-process-event-bridge-state",
            merged["luaProcessEventBridgeStateModFinishCount"] > 0,
            f"mods={merged['luaProcessEventBridgeStateModFinishCount']}",
            "no Lua mod proved GetProcessEventBridgeState native bridge introspection",
        )
    )
    gates.append(
        gate(
            "lua-process-event-native-invoke",
            merged["luaProcessEventNativeInvokeModFinishCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventNativeInvokeSelfTestCount']} "
                f"compat={merged['luaProcessEventNativeInvokeModFinishCount']}"
            ),
            "no Lua self-test proved guarded Lua-triggered native ProcessEvent bridge invocation",
        )
    )
    gates.append(
        gate(
            "lua-process-event-native-invoke-non-self-test-gate",
            merged["luaProcessEventNativeInvokeNonSelfTestGateCount"] > 0
            or merged["luaProcessEventNativeInvokeNonSelfTestInvokedCount"] > 0,
            (
                f"closedGates={merged['luaProcessEventNativeInvokeNonSelfTestGateCount']} "
                f"invoked={merged['luaProcessEventNativeInvokeNonSelfTestInvokedCount']}"
            ),
            "no descriptor-backed non-self-test ProcessEvent target proved either the closed invoke gate or the enabled invoke path",
        )
    )
    gates.append(
        gate(
            "lua-process-event-native-invoke-non-self-test-invoked",
            merged["luaProcessEventNativeInvokeNonSelfTestInvokedCount"] > 0,
            f"invoked={merged['luaProcessEventNativeInvokeNonSelfTestInvokedCount']}",
            "no explicitly enabled descriptor-backed non-self-test ProcessEvent target was invoked through the Lua native bridge",
        )
    )
    gates.append(
        gate(
            "lua-process-event-native-invoke-descriptor-preflight",
            merged["luaProcessEventNativeInvokeDescriptorPreflightCount"] > 0,
            f"preflights={merged['luaProcessEventNativeInvokeDescriptorPreflightCount']}",
            "no descriptor-backed non-self-test ProcessEvent target reached no-call descriptor-preflight-ready state",
        )
    )
    gates.append(
        gate(
            "lua-process-event-native-executor-state",
            merged["luaProcessEventNativeExecutorReadyStateCount"] > 0,
            (
                f"ready={merged['luaProcessEventNativeExecutorReadyStateCount']} "
                f"events={merged['luaProcessEventNativeExecutorStateCount']}"
            ),
            "no descriptor-backed non-self-test ProcessEvent target reached prepared native executor ready state",
        )
    )
    gates.append(
        gate(
            "lua-call-function-native-invoke",
            merged["luaCallFunctionNativeInvokeModFinishCount"] > 0,
            (
                f"selfTests={merged['luaCallFunctionNativeInvokeSelfTestCount']} "
                f"compat={merged['luaCallFunctionNativeInvokeModFinishCount']}"
            ),
            "no Lua self-test proved guarded Lua-triggered native CallFunction bridge invocation",
        )
    )
    gates.append(
        gate(
            "lua-call-function-native-invoke-preflight",
            merged["luaCallFunctionNativeInvokePreflightCount"] > 0,
            f"preflights={merged['luaCallFunctionNativeInvokePreflightCount']}",
            "no non-self-test CallFunction target reached no-call preflight-ready state",
        )
    )
    gates.append(
        gate(
            "lua-call-function-native-executor-state",
            merged["luaCallFunctionNativeExecutorReadyStateCount"] > 0,
            (
                f"ready={merged['luaCallFunctionNativeExecutorReadyStateCount']} "
                f"events={merged['luaCallFunctionNativeExecutorStateCount']}"
            ),
            "no non-self-test CallFunction target reached prepared native executor ready state",
        )
    )
    gates.append(
        gate(
            "lua-call-function-native-invoke-non-self-test-gate",
            merged["luaCallFunctionNativeInvokeNonSelfTestGateCount"] > 0
            or merged["luaCallFunctionNativeInvokeNonSelfTestInvokedCount"] > 0,
            (
                f"closedGates={merged['luaCallFunctionNativeInvokeNonSelfTestGateCount']} "
                f"invoked={merged['luaCallFunctionNativeInvokeNonSelfTestInvokedCount']}"
            ),
            "no non-self-test CallFunction target proved either the closed invoke gate or the enabled invoke path",
        )
    )
    gates.append(
        gate(
            "lua-call-function-native-invoke-non-self-test-invoked",
            merged["luaCallFunctionNativeInvokeNonSelfTestInvokedCount"] > 0,
            f"invoked={merged['luaCallFunctionNativeInvokeNonSelfTestInvokedCount']}",
            "no explicitly enabled non-self-test CallFunction target was invoked through the Lua native bridge",
        )
    )
    gates.append(
        gate(
            "lua-process-event-params-buffer",
            merged["luaProcessEventParamsBufferCount"] > 0,
            f"buffers={merged['luaProcessEventParamsBufferCount']}",
            "no Lua mod constructed a descriptor-backed ProcessEvent params buffer outside an active callback",
        )
    )
    gates.append(
        gate(
            "lua-lifecycle-hooks",
            merged["luaLifecycleHookModFinishCount"] > 0,
            f"mods={merged['luaLifecycleHookModFinishCount']}",
            "no Lua mod proved RegisterCustomEvent and lifecycle pre/post hooks dispatch around loader-owned lifecycle shims",
        )
    )
    gates.append(
        gate(
            "lua-custom-event-hooks",
            merged["luaCustomEventModFinishCount"] > 0,
            f"mods={merged['luaCustomEventModFinishCount']}",
            "no Lua mod proved RegisterCustomEvent dispatch around loader-owned custom event shims",
        )
    )
    gates.append(
        gate(
            "lua-load-map-hooks",
            merged["luaLoadMapHookModFinishCount"] > 0,
            f"mods={merged['luaLoadMapHookModFinishCount']}",
            "no Lua mod proved RegisterLoadMapPreHook/PostHook dispatch around loader-owned LoadMap shims",
        )
    )
    gates.append(
        gate(
            "lua-begin-play-hooks",
            merged["luaBeginPlayHookModFinishCount"] > 0,
            f"mods={merged['luaBeginPlayHookModFinishCount']}",
            "no Lua mod proved RegisterBeginPlayPreHook/PostHook dispatch around loader-owned BeginPlay shims",
        )
    )
    gates.append(
        gate(
            "lua-init-game-state-hooks",
            merged["luaInitGameStateHookModFinishCount"] > 0,
            f"mods={merged['luaInitGameStateHookModFinishCount']}",
            "no Lua mod proved RegisterInitGameStatePreHook/PostHook dispatch around loader-owned InitGameState shims",
        )
    )
    gates.append(
        gate(
            "lua-object-notify",
            merged["luaNotifyOnNewObjectModFinishCount"] > 0,
            f"mods={merged['luaNotifyOnNewObjectModFinishCount']}",
            "no Lua mod proved NotifyOnNewObject dispatched multiple callbacks for a newly constructed object handle",
        )
    )
    gates.append(
        gate(
            "lua-synthetic-outer",
            merged["luaSyntheticOuterModFinishCount"] > 0,
            f"mods={merged['luaSyntheticOuterModFinishCount']}",
            "no Lua mod proved StaticConstructObject preserved a loader-owned outer handle",
        )
    )
    gates.append(
        gate(
            "lua-static-construct-object-native-executor-state",
            merged["luaStaticConstructObjectNativeExecutorStateCount"] > 0,
            f"events={merged['luaStaticConstructObjectNativeExecutorStateCount']}",
            "no Lua mod queried the guarded StaticConstructObject native executor state",
        )
    )
    gates.append(
        gate(
            "lua-static-construct-object-native-executor-ready",
            merged["luaStaticConstructObjectNativeExecutorReadyStateCount"] > 0,
            (
                f"ready={merged['luaStaticConstructObjectNativeExecutorReadyStateCount']} "
                f"events={merged['luaStaticConstructObjectNativeExecutorStateCount']}"
            ),
            "no target-image StaticConstructObject executor reached ABI-verified call-frame-ready final-call-eligible state",
        )
    )
    gates.append(
        gate(
            "lua-static-construct-object-native-invoke",
            merged["luaStaticConstructObjectNativeInvokedCount"] > 0,
            (
                f"nativeInvoked={merged['luaStaticConstructObjectNativeInvokedCount']} "
                f"invokes={merged['luaStaticConstructObjectNativeInvokeCount']}"
            ),
            "no guarded StaticConstructObject native invocation reached target-image native code and returned with nativeInvoked=true",
        )
    )
    gates.append(
        gate(
            "lua-object-outer-chains",
            merged["resolvedLuaObjectOuterChainCount"] > 0,
            f"resolved={merged['resolvedLuaObjectOuterChainCount']}/{merged['luaObjectOuterChainCount']}",
            "no runtime object registry evidence proved a non-empty UObject outer chain resolved through known handles",
        )
    )
    gates.append(
        gate(
            "lua-object-outer-chain-identities",
            merged["luaObjectOuterChainIdentityCount"] > 0,
            f"identity={merged['luaObjectOuterChainIdentityCount']}/{merged['resolvedLuaObjectOuterChainCount']}",
            "no runtime object registry evidence produced a reconstructed UObject path/full-name from a resolved outer chain",
        )
    )
    gates.append(
        gate(
            "lua-world-context",
            merged["luaWorldContextModFinishCount"] > 0,
            f"mods={merged['luaWorldContextModFinishCount']}",
            "no Lua mod proved GetWorld resolved a world-like handle or a world outer chain",
        )
    )
    gates.append(
        gate(
            "lua-global-runtime-helpers",
            merged["passedLuaGlobalRuntimeHelperCheckCount"] > 0,
            (
                f"checks={merged['passedLuaGlobalRuntimeHelperCheckCount']}/"
                f"{merged['luaGlobalRuntimeHelperCheckCount']} "
                f"promotedWorld={merged['promotedWorldLuaGlobalRuntimeHelperCheckCount']} "
                f"promotedEngine={merged['promotedEngineLuaGlobalRuntimeHelperCheckCount']}"
            ),
            "no Lua mod proved global GetWorld() and GetEngine() helper resolution",
        )
    )
    gates.append(
        gate(
            "lua-class-default-object",
            merged["luaClassDefaultObjectModFinishCount"] > 0,
            f"mods={merged['luaClassDefaultObjectModFinishCount']}",
            "no Lua mod proved GetCDO returned a class-default-object handle",
        )
    )
    gates.append(
        gate(
            "lua-level",
            merged["luaLevelModFinishCount"] > 0,
            f"mods={merged['luaLevelModFinishCount']}",
            "no Lua mod proved GetLevel resolved a loader-owned level handle",
        )
    )
    gates.append(
        gate(
            "lua-process-event-self-test",
            merged["passedLuaProcessEventSelfTestCount"] > 0,
            f"passed={merged['passedLuaProcessEventSelfTestCount']}/{merged['luaProcessEventSelfTestCount']}",
            "no Lua callback bridge passed through a ProcessEvent-shaped hook/trampoline self-test",
        )
    )
    gates.append(
        gate(
            "ue-process-event-hook-probe",
            merged["passedUeProcessEventHookCount"] > 0,
            f"passed={merged['passedUeProcessEventHookCount']}/{merged['ueProcessEventHookCount']}",
            "no resolved ProcessEvent target passed guarded install/restore probing",
        )
    )
    gates.append(
        gate(
            "ue-process-event-hook-runtime-target",
            merged["provenTargetPassedUeProcessEventHookCount"] > 0,
            (
                f"nonSelfTest={merged['nonSelfTestPassedUeProcessEventHookCount']} "
                f"provenTarget={merged['provenTargetPassedUeProcessEventHookCount']} "
                f"runtimeContext={merged['runtimeMatchedUeProcessEventLiveContextCount']} "
                f"passed={merged['passedUeProcessEventHookCount']}/{merged['ueProcessEventHookCount']}"
            ),
            "no guarded ProcessEvent hook probe tied the resolved non-self-test target to target-image anchor/provenance",
        )
    )
    gates.append(
        gate(
            "ue-call-function-hook-probe",
            merged["passedUeCallFunctionHookCount"] > 0,
            f"passed={merged['passedUeCallFunctionHookCount']}/{merged['ueCallFunctionHookCount']}",
            "no resolved CallFunctionByNameWithArguments target passed guarded install/restore probing",
        )
    )
    gates.append(
        gate(
            "ue-call-function-hook-runtime-target",
            merged["provenTargetPassedUeCallFunctionHookCount"] > 0,
            (
                f"nonSelfTest={merged['nonSelfTestPassedUeCallFunctionHookCount']} "
                f"provenTarget={merged['provenTargetPassedUeCallFunctionHookCount']} "
                f"passed={merged['passedUeCallFunctionHookCount']}/{merged['ueCallFunctionHookCount']}"
            ),
            "no guarded CallFunctionByNameWithArguments hook probe tied the resolved non-self-test target to target-image anchor/provenance",
        )
    )
    gates.append(
        gate(
            "ue-call-function-live-hook",
            merged["installedUeCallFunctionLiveHookCount"] > 0,
            (
                f"installed={merged['installedUeCallFunctionLiveHookCount']}/{merged['ueCallFunctionLiveHookCount']} "
                f"statuses={merged['ueCallFunctionLiveHookStatusCounts']}"
            ),
            "no persistent CallFunctionByNameWithArguments hook scaffold was installed on a resolved target",
        )
    )
    gates.append(
        gate(
            "ue-call-function-live-hook-runtime-target",
            merged["provenTargetInstalledUeCallFunctionLiveHookCount"] > 0,
            (
                f"nonSelfTest={merged['nonSelfTestInstalledUeCallFunctionLiveHookCount']} "
                f"provenTarget={merged['provenTargetInstalledUeCallFunctionLiveHookCount']} "
                f"installed={merged['installedUeCallFunctionLiveHookCount']}/{merged['ueCallFunctionLiveHookCount']}"
            ),
            "no persistent CallFunctionByNameWithArguments hook install tied the resolved non-self-test target to target-image anchor/provenance",
        )
    )
    gates.append(
        gate(
            "ue-call-function-active-validation",
            merged["invokedUeCallFunctionActiveValidationCount"] > 0
            and merged["originalUeCallFunctionActiveValidationCount"] > 0
            and merged["targetEntryUeCallFunctionActiveValidationCount"] > 0,
            (
                f"invoked={merged['invokedUeCallFunctionActiveValidationCount']}/"
                f"{merged['ueCallFunctionActiveValidationCount']} "
                f"original={merged['originalUeCallFunctionActiveValidationCount']} "
                f"targetEntry={merged['targetEntryUeCallFunctionActiveValidationCount']}"
            ),
            "no explicitly allowed active CallFunctionByNameWithArguments validation call entered through the patched target entry and reached the original trampoline",
        )
    )
    gates.append(
        gate(
            "ue-call-function-live-lua-dispatch",
            merged["provenTargetRoutedUeCallFunctionLiveLuaHookCount"] > 0
            and merged["provenTargetHandledUeCallFunctionLiveLuaHookCount"] > 0,
            (
                f"provenRouted={merged['provenTargetRoutedUeCallFunctionLiveLuaHookCount']} "
                f"provenHandled={merged['provenTargetHandledUeCallFunctionLiveLuaHookCount']} "
                f"routed={merged['routedUeCallFunctionLiveLuaHookCount']} "
                f"handled={merged['handledUeCallFunctionLiveLuaHookCount']} "
                f"installed={merged['installedUeCallFunctionLiveHookCount']}/{merged['ueCallFunctionLiveHookCount']}"
            ),
            "no persistent CallFunctionByNameWithArguments target-image live hook routed and handled Lua callbacks",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-hook",
            merged["installedUeProcessEventLiveHookCount"] > 0,
            (
                f"installed={merged['installedUeProcessEventLiveHookCount']}/{merged['ueProcessEventLiveHookCount']} "
                f"restored={merged['restoredUeProcessEventLiveHookCount']} "
                f"statuses={merged['ueProcessEventLiveHookStatusCounts']}"
            ),
            "no persistent ProcessEvent hook scaffold was installed on a resolved target",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-hook-runtime-target",
            merged["provenTargetInstalledUeProcessEventLiveHookCount"] > 0
            or merged["runtimeMatchedUeProcessEventLiveContextCount"] > 0,
            (
                f"nonSelfTest={merged['nonSelfTestInstalledUeProcessEventLiveHookCount']} "
                f"provenTarget={merged['provenTargetInstalledUeProcessEventLiveHookCount']} "
                f"runtimeContext={merged['runtimeMatchedUeProcessEventLiveContextCount']} "
                f"installed={merged['installedUeProcessEventLiveHookCount']}/{merged['ueProcessEventLiveHookCount']}"
            ),
            "no persistent ProcessEvent hook install tied the resolved non-self-test target to target-image anchor/provenance or a sampled runtime ProcessEvent context",
        )
    )
    gates.append(
        gate(
            "ue-process-event-active-validation",
            merged["invokedUeProcessEventActiveValidationCount"] > 0
            and merged["originalUeProcessEventActiveValidationCount"] > 0
            and merged["targetEntryUeProcessEventActiveValidationCount"] > 0,
            (
                f"invoked={merged['invokedUeProcessEventActiveValidationCount']}/"
                f"{merged['ueProcessEventActiveValidationCount']} "
                f"original={merged['originalUeProcessEventActiveValidationCount']} "
                f"targetEntry={merged['targetEntryUeProcessEventActiveValidationCount']} "
                f"suppressedTargetEntry={merged['suppressedTargetEntryUeProcessEventActiveValidationCount']} "
                f"descriptorBuffer={merged['descriptorBufferUeProcessEventActiveValidationCount']}"
            ),
            "no explicitly allowed active ProcessEvent validation call entered through the patched target entry and reached the original trampoline",
        )
    )
    gates.append(
        gate(
            "ue-process-event-synthetic-target-entry",
            merged["syntheticTargetEntryUeProcessEventActiveValidationCount"] > 0,
            (
                f"syntheticTargetEntry={merged['syntheticTargetEntryUeProcessEventActiveValidationCount']} "
                f"invoked={merged['invokedUeProcessEventActiveValidationCount']} "
                f"original={merged['originalUeProcessEventActiveValidationCount']} "
                f"suppressedTargetEntry={merged['suppressedTargetEntryUeProcessEventActiveValidationCount']}"
            ),
            "no no-original-call synthetic ProcessEvent validation entered through the patched target entry",
        )
    )
    gates.append(
        gate(
            "ue-process-event-dispatch-self-test",
            merged["armedUeProcessEventDispatchSelfTestCount"] > 0,
            f"armed={merged['armedUeProcessEventDispatchSelfTestCount']}/{merged['ueProcessEventDispatchSelfTestCount']}",
            "no native ProcessEvent pre/original/post dispatch callback registry self-test was armed",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-lua-dispatch",
            merged["armedUeProcessEventLiveLuaDispatchCount"] > 0,
            (
                f"armed={merged['armedUeProcessEventLiveLuaDispatchCount']}/{merged['ueProcessEventLiveLuaDispatchCount']} "
                f"closed={merged['closedUeProcessEventLiveLuaDispatchCount']} "
                f"statuses={merged['ueProcessEventLiveLuaDispatchStatusCounts']}"
            ),
            "no live ProcessEvent hook armed Lua RegisterHook pre/post callbacks",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-context",
            merged["resolvedUeProcessEventLiveContextCount"] > 0,
            (
                f"resolved={merged['resolvedUeProcessEventLiveContextCount']}/"
                f"{merged['ueProcessEventLiveContextCount']}"
            ),
            "no sampled live ProcessEvent call resolved object, function path, params pointer, and function param descriptors",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-function-path",
            merged["matchedUeProcessEventLiveContextCount"] > 0,
            (
                f"matched={merged['matchedUeProcessEventLiveContextCount']} "
                f"resolved={merged['resolvedUeProcessEventLiveContextCount']} "
                f"functionPaths={len(merged['ueFunctionPaths'])}"
            ),
            "no sampled live ProcessEvent call used a functionPath that matched a decoded scanned UFunction identity",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-runtime-context",
            merged["runtimeMatchedUeProcessEventLiveContextCount"] > 0,
            (
                f"runtimeMatched={merged['runtimeMatchedUeProcessEventLiveContextCount']} "
                f"matched={merged['matchedUeProcessEventLiveContextCount']} "
                f"resolved={merged['resolvedUeProcessEventLiveContextCount']} "
                f"explicitRuntime={merged['runtimeProvenanceUeProcessEventLiveContextCount']} "
                f"explicitSelfTest={merged['selfTestProvenanceUeProcessEventLiveContextCount']}"
            ),
            "no sampled live ProcessEvent call matched a decoded runtime UFunction path outside loader-owned self-test functions",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-registry-context",
            merged["nativeIdentityUeProcessEventLiveRegistryContextCount"] > 0
            and merged["matchedUeProcessEventLiveRegistryContextCount"] > 0,
            (
                f"native={merged['nativeIdentityUeProcessEventLiveRegistryContextCount']} "
                f"matched={merged['matchedUeProcessEventLiveRegistryContextCount']} "
                f"resolved={merged['resolvedUeProcessEventLiveRegistryContextCount']}/"
                f"{merged['ueProcessEventLiveRegistryContextCount']}"
            ),
            "no sampled live ProcessEvent call resolved both object and function through promoted Lua-visible registries",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-runtime-registry-context",
            merged["runtimeMatchedUeProcessEventLiveRegistryContextCount"] > 0,
            (
                f"runtimeMatched={merged['runtimeMatchedUeProcessEventLiveRegistryContextCount']} "
                f"matched={merged['matchedUeProcessEventLiveRegistryContextCount']} "
                f"native={merged['nativeIdentityUeProcessEventLiveRegistryContextCount']} "
                f"explicitRuntime={merged['runtimeProvenanceUeProcessEventLiveRegistryContextCount']} "
                f"explicitSelfTest={merged['selfTestProvenanceUeProcessEventLiveRegistryContextCount']}"
            ),
            "no sampled live ProcessEvent call resolved promoted object/function registry identities outside loader-owned self-test functions",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-param-values",
            merged["runtimeReadUeProcessEventLiveParamCount"] > 0
            and merged["runtimeMatchedUeProcessEventLiveContextCount"] > 0,
            (
                f"runtimeRead={merged['runtimeReadUeProcessEventLiveParamCount']} "
                f"read={merged['readUeProcessEventLiveParamCount']}/"
                f"{merged['ueProcessEventLiveParamCount']} "
                f"runtimeContext={merged['runtimeMatchedUeProcessEventLiveContextCount']}"
            ),
            "no sampled runtime ProcessEvent params were read through promoted function param descriptors for the matched live call/function",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-raw-param-values",
            merged["runtimeRawUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeRaw={merged['runtimeRawUeProcessEventLiveParamCount']} "
                f"raw={merged['rawUeProcessEventLiveParamCount']} "
                f"total={merged['ueProcessEventLiveParamCount']}"
            ),
            "no sampled complex live ProcessEvent params for the matched runtime call/function were read as bounded raw payload bytes",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-container-param-values",
            merged["runtimeContainerUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeContainer={merged['runtimeContainerUeProcessEventLiveParamCount']} "
                f"container={merged['containerUeProcessEventLiveParamCount']} "
                f"total={merged['ueProcessEventLiveParamCount']}"
            ),
            "no sampled array/set/map live ProcessEvent params for the matched runtime call/function were read as typed container header values",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-array-container-param-values",
            merged["runtimeArrayContainerUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeArray={merged['runtimeArrayContainerUeProcessEventLiveParamCount']} "
                f"array={merged['arrayContainerUeProcessEventLiveParamCount']} "
                f"container={merged['containerUeProcessEventLiveParamCount']}"
            ),
            "no sampled live TArray/FScriptArray ProcessEvent params for the matched runtime call/function were read as typed container header values",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-set-container-param-values",
            merged["runtimeSetContainerUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeSet={merged['runtimeSetContainerUeProcessEventLiveParamCount']} "
                f"set={merged['setContainerUeProcessEventLiveParamCount']} "
                f"container={merged['containerUeProcessEventLiveParamCount']}"
            ),
            "no sampled live TSet/FScriptSet ProcessEvent params for the matched runtime call/function were read as typed container header values",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-map-container-param-values",
            merged["runtimeMapContainerUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeMap={merged['runtimeMapContainerUeProcessEventLiveParamCount']} "
                f"map={merged['mapContainerUeProcessEventLiveParamCount']} "
                f"container={merged['containerUeProcessEventLiveParamCount']}"
            ),
            "no sampled live TMap/FScriptMap ProcessEvent params for the matched runtime call/function were read as typed container header values",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-set-map-container-param-values",
            merged["runtimeSetMapContainerUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeSetMap={merged['runtimeSetMapContainerUeProcessEventLiveParamCount']} "
                f"setMap={merged['setMapContainerUeProcessEventLiveParamCount']} "
                f"set={merged['setContainerUeProcessEventLiveParamCount']} "
                f"map={merged['mapContainerUeProcessEventLiveParamCount']}"
            ),
            "no sampled live set/map ProcessEvent params for the matched runtime call/function proved FScriptSetHeader or FScriptMapHeader handling",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-container-data-samples",
            merged["runtimeSampledContainerUeProcessEventLiveParamCount"] > 0,
            (
                f"runtimeSampled={merged['runtimeSampledContainerUeProcessEventLiveParamCount']} "
                f"sampled={merged['sampledContainerUeProcessEventLiveParamCount']} "
                f"container={merged['containerUeProcessEventLiveParamCount']}"
            ),
            "no sampled live array ProcessEvent params for the matched runtime call/function had a readable data pointer for bounded storage bytes",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-context-handles",
            merged["ueProcessEventLuaContextHandleCount"] > 0,
            (
                f"withHandles={merged['ueProcessEventLuaContextHandleCount']} "
                f"installed={merged['installedUeProcessEventLiveHookCount']}"
            ),
            "no live ProcessEvent Lua callback received UObject, UFunction, and params context tables",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-param-accessors",
            merged["luaProcessEventParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaParamAccessorCount']}"
            ),
            "no function-param descriptor GetFunctionParams plus descriptor-handle GetParamDescriptor/GetParamValue/SetParamValue access passed through both the ProcessEvent self-test and live hook",
        )
    )
    gates.append(
        gate(
            "ue-process-event-live-class-aware-param-values",
            merged["runtimeMatchedUeProcessEventLiveRegistryContextCount"] > 0
            and merged["matchedUeProcessEventLiveRegistryContextCount"] > 0
            and merged["nativeIdentityUeProcessEventLiveRegistryContextCount"] > 0
            and merged["ueProcessEventLiveLuaParamAccessorCount"] > 0
            and merged["ueProcessEventLiveLuaFunctionParamLookupMethodCount"] > 0
            and merged["ueProcessEventLuaContextHandleCount"] > 0,
            (
                f"runtimeRegistryMatched={merged['runtimeMatchedUeProcessEventLiveRegistryContextCount']} "
                f"registryMatched={merged['matchedUeProcessEventLiveRegistryContextCount']} "
                f"nativeRegistry={merged['nativeIdentityUeProcessEventLiveRegistryContextCount']} "
                f"liveParamAccessors={merged['ueProcessEventLiveLuaParamAccessorCount']} "
                f"liveParamLookup={merged['ueProcessEventLiveLuaFunctionParamLookupMethodCount']} "
                f"contextHandles={merged['ueProcessEventLuaContextHandleCount']}"
            ),
            "no live ProcessEvent Lua callback proved promoted runtime ctx.Function registry identity plus descriptor-backed GetParamValue/SetParamValue on the active params pointer",
        )
    )
    gates.append(
        gate(
            "ue-process-event-function-param-method",
            merged["luaProcessEventFunctionParamMethodSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaFunctionParamMethodCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventFunctionParamMethodSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaFunctionParamMethodCount']}"
            ),
            "no ProcessEvent self/live Lua path proved ctx.Function:GetFunctionParams() method access",
        )
    )
    gates.append(
        gate(
            "ue-process-event-function-param-lookup-method",
            merged["luaProcessEventFunctionParamLookupMethodSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaFunctionParamLookupMethodCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventFunctionParamLookupMethodSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaFunctionParamLookupMethodCount']}"
            ),
            "no ProcessEvent self/live Lua path proved ctx.Function:GetParamDescriptor(name) method access",
        )
    )
    gates.append(
        gate(
            "ue-process-event-function-param-iteration-method",
            merged["luaProcessEventFunctionParamIterationMethodSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaFunctionParamIterationMethodCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventFunctionParamIterationMethodSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaFunctionParamIterationMethodCount']}"
            ),
            "no ProcessEvent self/live Lua path proved ctx.Function:ForEachParam(callback) descriptor iteration",
        )
    )
    gates.append(
        gate(
            "ue-process-event-container-alias-methods",
            merged["luaProcessEventContainerAliasMethodSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaContainerAliasMethodCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventContainerAliasMethodSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaContainerAliasMethodCount']}"
            ),
            "no ProcessEvent self/live Lua path proved FScriptArray/FScriptSet/FScriptMap Get/get and GetKey/GetValue aliases",
        )
    )
    gates.append(
        gate(
            "ue-process-event-container-storage-layout-methods",
            merged["luaProcessEventContainerStorageLayoutMethodSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaContainerStorageLayoutMethodCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventContainerStorageLayoutMethodSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaContainerStorageLayoutMethodCount']}"
            ),
            "no ProcessEvent self/live Lua path proved FScriptArray/FScriptSet/FScriptMap storage layout, sparse-layout validation flag, and slot stride methods",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-scalar-param-accessors",
            merged["luaProcessEventScalarParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaScalarParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventScalarParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaScalarParamAccessorCount']}"
            ),
            "no ProcessEvent self/live Lua path proved signed/unsigned integer plus float/double GetParamValue/SetParamValue coverage",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-name-string-param-accessors",
            merged["luaProcessEventNameStringParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaNameStringParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventNameStringParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaNameStringParamAccessorCount']}"
            ),
            "no ProcessEvent self/live Lua path proved FName/FString GetParamValue/SetParamValue coverage",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-struct-param-accessors",
            merged["luaProcessEventStructParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaStructParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventStructParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaStructParamAccessorCount']}"
            ),
            "no ProcessEvent self/live Lua path proved FVector-shaped FStructProperty GetParamValue/SetParamValue coverage",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-enum-param-accessors",
            merged["luaProcessEventEnumParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaEnumParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventEnumParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaEnumParamAccessorCount']}"
            ),
            "no ProcessEvent self/live Lua path proved byte-sized FEnumProperty GetParamValue/SetParamValue coverage",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-object-param-accessors",
            merged["luaProcessEventObjectParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaObjectParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventObjectParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaObjectParamAccessorCount']}"
            ),
            "no ProcessEvent self/live Lua path proved FObjectProperty GetParamValue/SetParamValue coverage",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-bool-param-accessors",
            merged["luaProcessEventBoolParamAccessorSelfTestCount"] > 0
            and merged["ueProcessEventLiveLuaBoolParamAccessorCount"] > 0,
            (
                f"selfTests={merged['luaProcessEventBoolParamAccessorSelfTestCount']} "
                f"liveHooks={merged['ueProcessEventLiveLuaBoolParamAccessorCount']}"
            ),
            "no ProcessEvent self/live Lua path proved FBoolProperty GetParamValue/SetParamValue coverage",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-hook-routing",
            merged["routedLuaProcessEventSelfTestCount"] > 0
            and merged["multiHookUeProcessEventLiveLuaDispatchCount"] > 0
            and merged["matchedUeProcessEventLiveLuaDispatchCount"] > 0
            and merged["closedMatchedUeProcessEventLiveLuaDispatchCount"] > 0
            and merged["routedUeProcessEventLiveLuaHookCount"] > 0,
            (
                f"selfTests={merged['routedLuaProcessEventSelfTestCount']} "
                f"multiHookDispatch={merged['multiHookUeProcessEventLiveLuaDispatchCount']} "
                f"matchedDispatch={merged['matchedUeProcessEventLiveLuaDispatchCount']} "
                f"closedMatched={merged['closedMatchedUeProcessEventLiveLuaDispatchCount']} "
                f"liveHooks={merged['routedUeProcessEventLiveLuaHookCount']}"
            ),
            "no ProcessEvent Lua self/live path proved multiple RegisterHook entries with only the matching function callback firing and returning the expected pre/post results",
        )
    )
    gates.append(
        gate(
            "ue-process-event-lua-hook-alias-routing",
            merged["ueProcessEventLiveLuaPathAliasMatchCount"] > 0,
            (
                f"liveAliasMatches={merged['ueProcessEventLiveLuaPathAliasMatchCount']} "
                f"liveExactMatches={merged['ueProcessEventLiveLuaPathExactMatchCount']} "
                f"selfAliasMatches={merged['luaProcessEventPathAliasMatchCount']} "
                f"selfExactMatches={merged['luaProcessEventPathExactMatchCount']}"
            ),
            "no live ProcessEvent Lua dispatch proved a UE4SS-style /Script hook path can route to a decoded runtime UFunction path by terminal function-name alias",
        )
    )
    gates.append(
        gate(
            "lua-reflection-self-test",
            merged["passedLuaReflectionSelfTestCount"] > 0,
            f"passed={merged['passedLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection/property get-set/function-call self-test passed",
        )
    )
    gates.append(
        gate(
            "lua-reflection-raw-set",
            merged["rawSetLuaReflectionSelfTestCount"] > 0,
            f"rawSet={merged['rawSetLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved guarded raw reflected scalar SetPropertyValue",
        )
    )
    gates.append(
        gate(
            "lua-reflection-named-property",
            merged["namedLuaReflectionSelfTestCount"] > 0,
            f"named={merged['namedLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test used a decoded FName-backed property alias",
        )
    )
    gates.append(
        gate(
            "lua-reflection-numeric-property-values",
            merged["numericLuaReflectionSelfTestCount"] > 0,
            f"numeric={merged['numericLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved FFloatProperty/FDoubleProperty get/set values",
        )
    )
    gates.append(
        gate(
            "lua-reflection-name-text-property-values",
            merged["nameTextLuaReflectionSelfTestCount"] > 0,
            f"nameText={merged['nameTextLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved FNameProperty/FTextProperty get/set values",
        )
    )
    gates.append(
        gate(
            "lua-reflection-array-inner-property",
            merged["arrayInnerLuaReflectionSelfTestCount"] > 0,
            f"arrayInner={merged['arrayInnerLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved FArrayProperty:GetInner() metadata",
        )
    )
    gates.append(
        gate(
            "lua-reflection-enum-property",
            merged["enumLuaReflectionSelfTestCount"] > 0,
            f"enum={merged['enumLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved FEnumProperty:GetEnum()/GetUnderlyingProperty() metadata",
        )
    )
    gates.append(
        gate(
            "lua-reflection-container-properties",
            merged["containerLuaReflectionSelfTestCount"] > 0,
            f"containers={merged['containerLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved FSetProperty element and FMapProperty key/value metadata",
        )
    )
    gates.append(
        gate(
            "lua-reflection-import-text",
            merged["importTextLuaReflectionSelfTestCount"] > 0,
            f"importText={merged['importTextLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved bounded FProperty:ImportText text-to-value writes",
        )
    )
    gates.append(
        gate(
            "lua-reflection-export-text",
            merged["exportTextLuaReflectionSelfTestCount"] > 0,
            f"exportText={merged['exportTextLuaReflectionSelfTestCount']}/{merged['luaReflectionSelfTestCount']}",
            "no Lua reflection self-test proved bounded FProperty:ExportText value-to-text exports",
        )
    )
    gates.append(
        gate(
            "lua-reflection-property-metadata",
            merged["propertyMetadataLuaReflectionSelfTestCount"] > 0,
            (
                f"metadata={merged['propertyMetadataLuaReflectionSelfTestCount']}/"
                f"{merged['luaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved FProperty metadata accessors",
        )
    )
    gates.append(
        gate(
            "lua-reflection-descriptor-values",
            merged["descriptorValueLuaReflectionSelfTestCount"] > 0,
            (
                f"descriptorValues={merged['descriptorValueLuaReflectionSelfTestCount']}/"
                f"{merged['luaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved descriptor-level FProperty GetValue/SetValue",
        )
    )
    gates.append(
        gate(
            "lua-reflection-for-each-property",
            merged["reflectionForEachPropertyLuaReflectionSelfTestCount"] > 0,
            (
                f"reflectionForEach={merged['reflectionForEachPropertyLuaReflectionSelfTestCount']}/"
                f"{merged['luaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved Reflection():ForEachProperty(callback)",
        )
    )
    gates.append(
        gate(
            "lua-reflection-for-each-property-runtime",
            merged["runtimeReflectionForEachPropertyLuaReflectionSelfTestCount"] > 0,
            (
                f"runtime={merged['runtimeReflectionForEachPropertyLuaReflectionSelfTestCount']} "
                f"selfTest={merged['selfTestReflectionForEachPropertyLuaReflectionSelfTestCount']} "
                f"total={merged['reflectionForEachPropertyLuaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved Reflection():ForEachProperty(callback) over a non-self-test promoted descriptor",
        )
    )
    gates.append(
        gate(
            "lua-reflection-live-descriptor-typed-class-runtime",
            merged["runtimeTypedLiveDescriptorLuaReflectionSelfTestCount"] > 0,
            (
                f"runtime={merged['runtimeTypedLiveDescriptorLuaReflectionSelfTestCount']} "
                f"selfTest={merged['selfTestTypedLiveDescriptorLuaReflectionSelfTestCount']} "
                f"total={merged['typedLiveDescriptorLuaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved a promoted non-self-test live descriptor exposed a decoded FProperty class",
        )
    )
    gates.append(
        gate(
            "lua-reflection-live-descriptor-typed-values-runtime",
            merged["runtimeTypedLiveDescriptorValueLuaReflectionSelfTestCount"] > 0,
            (
                f"runtime={merged['runtimeTypedLiveDescriptorValueLuaReflectionSelfTestCount']} "
                f"selfTest={merged['selfTestTypedLiveDescriptorValueLuaReflectionSelfTestCount']} "
                f"total={merged['typedLiveDescriptorValueLuaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved a promoted non-self-test live descriptor returned a typed GetValue result",
        )
    )
    gates.append(
        gate(
            "lua-reflection-live-descriptor-typed-set-values-runtime",
            merged["runtimeTypedLiveDescriptorValueSetLuaReflectionSelfTestCount"] > 0,
            (
                f"runtime={merged['runtimeTypedLiveDescriptorValueSetLuaReflectionSelfTestCount']} "
                f"selfTest={merged['selfTestTypedLiveDescriptorValueSetLuaReflectionSelfTestCount']} "
                f"total={merged['typedLiveDescriptorValueSetLuaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved a promoted non-self-test live descriptor accepted a typed SetValue result",
        )
    )
    gates.append(
        gate(
            "lua-reflection-live-descriptor-values",
            merged["liveDescriptorValueLuaReflectionSelfTestCount"] > 0,
            (
                f"liveDescriptorValues={merged['liveDescriptorValueLuaReflectionSelfTestCount']}/"
                f"{merged['luaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved promoted live reflection descriptor GetValue/SetValue",
        )
    )
    gates.append(
        gate(
            "lua-reflection-live-descriptor-values-runtime",
            merged["runtimeLiveDescriptorValueLuaReflectionSelfTestCount"] > 0,
            (
                f"runtime={merged['runtimeLiveDescriptorValueLuaReflectionSelfTestCount']} "
                f"selfTest={merged['selfTestLiveDescriptorValueLuaReflectionSelfTestCount']} "
                f"total={merged['liveDescriptorValueLuaReflectionSelfTestCount']}"
            ),
            "no Lua reflection self-test proved promoted non-self-test live reflection descriptor GetValue/SetValue",
        )
    )
    gates.append(
        gate(
            "lua-mod-entrypoints",
            merged["passedLuaModScriptCount"] > 0
            and merged["passedLuaModDispatchSelfTestCount"] > 0
            and merged["passedLuaModFinishCount"] > 0,
            (
                f"scripts={merged['passedLuaModScriptCount']}/{merged['luaModScriptCount']} "
                f"dispatch={merged['passedLuaModDispatchSelfTestCount']}/{merged['luaModDispatchSelfTestCount']} "
                f"finishes={merged['passedLuaModFinishCount']}/{merged['luaModFinishCount']}"
            ),
            "no Lua mod entrypoint load plus callback-dispatch self-test passed in scoped logs",
        )
    )
    gates.append(
        gate(
            "lua-object-registry",
            merged["ueLuaObjectRegistryCount"] > 0,
            (
                f"added={merged['addedLuaObjectRegistryCount']}/{merged['luaObjectRegistryCount']} "
                f"ueCandidates={merged['ueLuaObjectRegistryCount']}"
            ),
            "no class-mapped UObject probe candidate was added to the Lua object registry",
        )
    )
    gates.append(
        gate(
            "lua-object-registry-checks",
            merged["passedLuaObjectRegistryCheckCount"] > 0,
            (
                f"passed={merged['passedLuaObjectRegistryCheckCount']}/"
                f"{merged['luaObjectRegistryCheckCount']}"
            ),
            "no native object registry self-check proved path/name/class/address lookup consistency",
        )
    )
    gates.append(
        gate(
            "lua-object-registry-runtime",
            merged["runtimeUeLuaObjectRegistryCount"] > 0,
            (
                f"runtime={merged['runtimeUeLuaObjectRegistryCount']} "
                f"selfTest={merged['selfTestUeLuaObjectRegistryCount']} "
                f"total={merged['ueLuaObjectRegistryCount']}"
            ),
            "no non-self-test class-mapped UObject probe candidate was added to the Lua object registry",
        )
    )
    gates.append(
        gate(
            "lua-function-registry-checks",
            merged["passedLuaFunctionRegistryCheckCount"] > 0,
            (
                f"passed={merged['passedLuaFunctionRegistryCheckCount']}/"
                f"{merged['luaFunctionRegistryCheckCount']}"
            ),
            "no native function registry self-check proved path/runtimePath/name/address/flags lookup consistency",
        )
    )
    gates.append(
        gate(
            "lua-function-registry-runtime",
            merged["runtimeLuaFunctionRegistryCheckCount"] > 0,
            (
                f"runtime={merged['runtimeLuaFunctionRegistryCheckCount']} "
                f"selfTest={merged['selfTestLuaFunctionRegistryCheckCount']} "
                f"passed={merged['passedLuaFunctionRegistryCheckCount']}"
            ),
            "no non-self-test native function registry self-check proved path/runtimePath/name/address/flags lookup consistency",
        )
    )
    gates.append(
        gate(
            "lua-decoded-object-aliases",
            merged["decodedLuaObjectAliasRegistryCount"] > 0,
            (
                f"added={merged['decodedLuaObjectAliasRegistryCount']} "
                f"skippedDuplicates={merged['skippedDecodedLuaObjectAliasRegistryCount']}"
            ),
            "no FName-decoded UObject/object-array name was promoted into a Lua object alias",
        )
    )
    gates.append(
        gate(
            "lua-decoded-object-aliases-runtime",
            merged["runtimeDecodedLuaObjectAliasRegistryCount"] > 0,
            (
                f"runtime={merged['runtimeDecodedLuaObjectAliasRegistryCount']} "
                f"selfTest={merged['selfTestDecodedLuaObjectAliasRegistryCount']} "
                f"total={merged['decodedLuaObjectAliasRegistryCount']}"
            ),
            "no non-self-test FName-decoded UObject/object-array name was promoted into a Lua object alias",
        )
    )
    gates.append(
        gate(
            "ue-object-array-registry",
            merged["objectArrayLuaObjectRegistryCount"] > 0,
            (
                f"objectArrayCandidates={merged['objectArrayLuaObjectRegistryCount']} "
                f"finishedArrays={merged['finishedUeObjectArrayCount']}/{merged['ueObjectArrayCount']}"
            ),
            "no bounded object-array walk added a candidate to the Lua object registry",
        )
    )
    gates.append(
        gate(
            "ue-object-array-shape",
            merged["plausibleUeObjectArrayShapeCount"] > 0,
            (
                f"plausible={merged['plausibleUeObjectArrayShapeCount']} "
                f"implausible={merged['implausibleUeObjectArrayShapeCount']} "
                f"total={merged['ueObjectArrayShapeCount']}"
            ),
            "no bounded object-array probe produced a plausible FUObjectArray/FChunkedFixedUObjectArray header",
        )
    )
    gates.append(
        gate(
            "ue-object-array-registry-runtime",
            merged["runtimeObjectArrayLuaObjectRegistryCount"] > 0,
            (
                f"runtime={merged['runtimeObjectArrayLuaObjectRegistryCount']} "
                f"selfTest={merged['selfTestObjectArrayLuaObjectRegistryCount']} "
                f"total={merged['objectArrayLuaObjectRegistryCount']}"
            ),
            "no non-self-test bounded object-array walk added a candidate to the Lua object registry",
        )
    )
    gates.append(
        gate(
            "ue-object-native-identities",
            merged["promotedUeObjectNativeIdentityCount"] > 0
            and merged["decodedNameUeObjectNativeIdentityCount"] > 0
            and merged["decodedClassNameUeObjectNativeIdentityCount"] > 0,
            (
                f"promoted={merged['promotedUeObjectNativeIdentityCount']}/{merged['ueObjectNativeIdentityCount']} "
                f"decodedNames={merged['decodedNameUeObjectNativeIdentityCount']} "
                f"decodedClasses={merged['decodedClassNameUeObjectNativeIdentityCount']}"
            ),
            "no runtime UObject/object-array evidence promoted decoded native object and class identity into Lua handles",
        )
    )
    gates.append(
        gate(
            "ue-object-internal-flags",
            merged["internalFlagUeObjectArrayItemCount"] > 0
            and merged["nonzeroInternalFlagUeObjectArrayItemCount"] > 0,
            (
                f"readable={merged['internalFlagUeObjectArrayItemCount']}/{merged['ueObjectArrayItemCount']} "
                f"nonzero={merged['nonzeroInternalFlagUeObjectArrayItemCount']}"
            ),
            "no object-array item produced readable nonzero InternalFlags for Lua HasAnyInternalFlags",
        )
    )
    gates.append(
        gate(
            "ue-fname-decoder",
            merged["decodedUeFNameCount"] > 0,
            f"decoded={merged['decodedUeFNameCount']}/{merged['ueFNameCount']}",
            "no UObject or object-array candidate resolved through a bounded FNamePool decoder",
        )
    )

    gate_map = {item["name"]: item["passed"] for item in gates}
    object_discovery_coverage = object_discovery_coverage_status(merged, gate_map)
    ready_object_discovery = (
        gate_map["loader-loaded"]
        and gate_map["target-image-process"]
        and gate_map["scan-completed"]
        and gate_map["ue-names"]
        and gate_map["ue-objects"]
        and gate_map["ue-world"]
        and gate_map["ue-pointer-probe"]
        and gate_map["ue-layout-probe"]
        and gate_map["ue-uobject-probe"]
        and gate_map["ue-object-internal-flags"]
        and gate_map["ue-fname-decoder"]
        and gate_map["lua-decoded-object-aliases"]
        and gate_map["lua-decoded-object-aliases-runtime"]
    )
    ready_target_object_discovery = (
        ready_object_discovery
        and gate_map["ue-runtime-root-discovery"]
        and gate_map["ue-target-names"]
        and gate_map["ue-target-objects"]
        and gate_map["ue-target-world"]
        and (gate_map["ue-target-dispatch"] or anchor_coverage["readyForTargetHookPlanning"])
    )
    ready_hooks = (
        ready_object_discovery
        and object_discovery_coverage["readyForFindObjectSemantics"]
        and gate_map["ue-dispatch"]
        and gate_map["signature-manifest-promotable"]
        and gate_map["hook-dispatch-self-test"]
        and gate_map["ue-process-event-hook-probe"]
        and gate_map["ue-process-event-hook-runtime-target"]
        and gate_map["ue-process-event-live-hook"]
        and gate_map["ue-process-event-live-hook-runtime-target"]
        and gate_map["ue-process-event-dispatch-self-test"]
        and gate_map["ue-call-function-hook-probe"]
        and gate_map["ue-call-function-hook-runtime-target"]
        and gate_map["ue-call-function-live-hook"]
        and gate_map["ue-call-function-live-hook-runtime-target"]
    )
    ready_target_hooks = (
        ready_hooks
        and ready_target_object_discovery
        and gate_map["ue-target-dispatch"]
    )
    ready_reflection = (
        ready_object_discovery
        and gate_map["ue-reflection-surface"]
        and gate_map["ue-reflection-probe"]
        and gate_map["ue-reflection-field-walk"]
        and gate_map["ue-reflection-property-descriptors"]
        and gate_map["ue-reflection-property-descriptors-runtime"]
        and gate_map["ue-function-param-descriptors"]
        and gate_map["ue-function-param-container-children"]
        and gate_map["ue-function-identities"]
        and gate_map["ue-function-native-identities"]
        and gate_map["ue-function-flags"]
        and gate_map["lua-function-registry-checks"]
        and gate_map["lua-function-registry-runtime"]
        and gate_map["ue-reflection-property-values"]
        and gate_map["ue-reflection-property-values-runtime"]
    )
    ready_lua = (
        ready_hooks
        and ready_reflection
        and gate_map["mod-dispatch-self-test"]
        and gate_map["lua-dispatch-self-test"]
        and gate_map["lua-scheduler-api"]
        and gate_map["lua-scheduler-api-mods"]
        and gate_map["lua-input-command-api"]
        and gate_map["lua-input-command-api-mods"]
        and gate_map["lua-object-api"]
        and gate_map["lua-function-iteration"]
        and gate_map["lua-function-iteration-runtime"]
        and gate_map["lua-process-console-exec-hooks"]
        and gate_map["lua-local-player-exec-hooks"]
        and gate_map["lua-call-function-hooks"]
        and gate_map["lua-call-function-structured-args"]
        and gate_map["lua-call-function-native-invoke"]
        and gate_map["lua-call-function-native-invoke-preflight"]
        and gate_map["lua-call-function-native-executor-state"]
        and gate_map["lua-call-function-native-invoke-non-self-test-gate"]
        and gate_map["lua-call-function-native-invoke-non-self-test-invoked"]
        and gate_map["lua-process-event-compat"]
        and gate_map["lua-process-event-bridge-state"]
        and gate_map["lua-process-event-native-invoke"]
        and gate_map["lua-process-event-native-invoke-descriptor-preflight"]
        and gate_map["lua-process-event-native-executor-state"]
        and gate_map["lua-process-event-native-invoke-non-self-test-invoked"]
        and gate_map["lua-process-event-params-buffer"]
        and gate_map["ue-call-function-live-lua-dispatch"]
        and gate_map["lua-lifecycle-hooks"]
        and gate_map["lua-custom-event-hooks"]
        and gate_map["lua-load-map-hooks"]
        and gate_map["lua-begin-play-hooks"]
        and gate_map["lua-init-game-state-hooks"]
        and gate_map["lua-object-notify"]
        and gate_map["lua-synthetic-outer"]
        and gate_map["lua-world-context"]
        and gate_map["lua-global-runtime-helpers"]
        and gate_map["lua-class-default-object"]
        and gate_map["lua-level"]
        and gate_map["lua-reflection-self-test"]
        and gate_map["lua-reflection-numeric-property-values"]
        and gate_map["lua-reflection-name-text-property-values"]
        and gate_map["lua-reflection-for-each-property"]
        and gate_map["lua-reflection-for-each-property-runtime"]
        and gate_map["lua-reflection-live-descriptor-typed-class-runtime"]
        and gate_map["lua-reflection-live-descriptor-typed-values-runtime"]
        and gate_map["lua-reflection-live-descriptor-typed-set-values-runtime"]
        and gate_map["lua-reflection-live-descriptor-values"]
        and gate_map["lua-reflection-live-descriptor-values-runtime"]
        and gate_map["lua-process-event-self-test"]
        and gate_map["ue-process-event-live-lua-dispatch"]
        and gate_map["ue-process-event-live-context"]
        and gate_map["ue-process-event-live-function-path"]
        and gate_map["ue-process-event-live-runtime-context"]
        and gate_map["ue-process-event-live-registry-context"]
        and gate_map["ue-process-event-live-runtime-registry-context"]
        and gate_map["ue-process-event-live-param-values"]
        and gate_map["ue-process-event-live-raw-param-values"]
        and gate_map["ue-process-event-live-container-param-values"]
        and gate_map["ue-process-event-live-array-container-param-values"]
        and gate_map["ue-process-event-live-set-container-param-values"]
        and gate_map["ue-process-event-live-map-container-param-values"]
        and gate_map["ue-process-event-live-set-map-container-param-values"]
        and gate_map["ue-process-event-live-container-data-samples"]
        and gate_map["ue-process-event-lua-context-handles"]
        and gate_map["ue-process-event-lua-param-accessors"]
        and gate_map["ue-process-event-live-class-aware-param-values"]
        and gate_map["ue-process-event-function-param-method"]
        and gate_map["ue-process-event-function-param-lookup-method"]
        and gate_map["ue-process-event-function-param-iteration-method"]
        and gate_map["ue-process-event-container-alias-methods"]
        and gate_map["ue-process-event-container-storage-layout-methods"]
        and gate_map["ue-process-event-lua-scalar-param-accessors"]
        and gate_map["ue-process-event-lua-name-string-param-accessors"]
        and gate_map["ue-process-event-lua-struct-param-accessors"]
        and gate_map["ue-process-event-lua-enum-param-accessors"]
        and gate_map["ue-process-event-lua-object-param-accessors"]
        and gate_map["ue-process-event-lua-bool-param-accessors"]
        and gate_map["ue-process-event-lua-hook-routing"]
        and gate_map["ue-process-event-lua-hook-alias-routing"]
        and gate_map["lua-mod-entrypoints"]
        and gate_map["lua-object-registry"]
        and gate_map["lua-object-registry-checks"]
        and gate_map["lua-object-registry-runtime"]
        and gate_map["lua-decoded-object-aliases"]
        and gate_map["lua-decoded-object-aliases-runtime"]
        and gate_map["ue-object-array-registry"]
        and gate_map["ue-object-array-registry-runtime"]
        and gate_map["ue-object-native-identities"]
        and gate_map["lua-object-outer-chain-identities"]
        and gate_map["ue-fname-decoder"]
    )

    next_steps = []
    for item in gates:
        if (
            not item["passed"]
            and item["name"].startswith("ue-")
            and item["name"] != "ue-call-function-live-lua-dispatch"
            and item["name"] != "ue-runtime-root-discovery"
            and item["name"] != "ue-process-event-synthetic-target-entry"
        ):
            next_steps.append(item["blocker"])
    if not ready_object_discovery:
        next_steps.append("keep work in read-only scan/xref mode")
    elif not gate_map["hook-dispatch-self-test"]:
        next_steps.append("run the guarded hook-dispatch self-test before ProcessEvent hook work")
    elif not ready_hooks:
        next_steps.append("validate read-only object/world/dispatch surfaces before ProcessEvent hook work")
    elif not gate_map["ue-function-param-descriptors"]:
        next_steps.append("enable the bounded UFunction param descriptor probe from functionLink candidates before Lua dispatch")
    elif not gate_map["ue-function-param-container-children"]:
        next_steps.append("promote decoded inner/key/value child property metadata from live container UFunction params before typed container element unmarshaling")
    elif not gate_map["ue-function-identities"]:
        next_steps.append("decode functionLink FNames into runtime UFunction paths before exposing RegisterHook routing to Lua mods")
    elif not gate_map["ue-function-native-identities"]:
        next_steps.append("promote UFunction name, UE4SS path, runtime path, root, and FunctionFlags into explicit native identity evidence")
    elif not gate_map["ue-function-flags"]:
        next_steps.append("read and promote UFunction FunctionFlags into Lua-visible function handles before treating GetFunctionFlags as live-compatible")
    elif not gate_map["lua-function-registry-checks"]:
        next_steps.append("prove native UFunction registry path/runtimePath/name/address/flags lookup consistency before Lua dispatch")
    elif not gate_map["lua-function-registry-runtime"]:
        next_steps.append("prove native UFunction registry lookup consistency on a non-self-test runtime function before Lua dispatch")
    elif not ready_reflection:
        next_steps.append("enable the read-only UE reflection field/function chain walk, FProperty descriptor probe, UFunction param descriptor probe, and bounded property value probe before Lua dispatch")
    elif not gate_map["mod-dispatch-self-test"]:
        next_steps.append("run the native mod-dispatch lifecycle self-test before Lua binding work")
    elif not gate_map["lua-dispatch-self-test"]:
        next_steps.append("run the Lua runtime execution, callback-bridge, and API-surface self-test before exposing UE4SS Lua APIs")
    elif not gate_map["lua-scheduler-api-mods"]:
        next_steps.append("load a Lua mod that proves ExecuteInGameThread, ExecuteAsync, ExecuteWithDelay, LoopAsync, and scheduler cancellation from mod entrypoints")
    elif not gate_map["lua-input-command-api-mods"]:
        next_steps.append("load a Lua mod that proves keybind dispatch/unregister and console command handler dispatch/unregister from mod entrypoints")
    elif not gate_map["lua-function-iteration"]:
        next_steps.append("run a Lua mod that proves ForEachFunction enumerates promoted UFunction handles from object/class handles")
    elif not gate_map["lua-function-iteration-runtime"]:
        next_steps.append("run a Lua mod that proves ForEachFunction enumerates promoted UFunction handles from a non-self-test object/class handle")
    elif not gate_map["lua-process-console-exec-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterProcessConsoleExecPreHook/PostHook dispatch around loader-owned ProcessConsoleExec")
    elif not gate_map["lua-local-player-exec-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterULocalPlayerExecPreHook/PostHook dispatch around loader-owned ULocalPlayerExec")
    elif not gate_map["lua-call-function-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterCallFunctionByNameWithArgumentsPreHook/PostHook dispatch around loader-owned CallFunction")
    elif not gate_map["lua-call-function-structured-args"]:
        next_steps.append("run a Lua mod that proves structured table arguments marshal through CallFunctionByNameWithArguments")
    elif not gate_map["lua-call-function-native-invoke"]:
        next_steps.append("run a Lua mod that proves guarded Lua-triggered native CallFunction bridge invocation")
    elif not gate_map["lua-call-function-native-invoke-preflight"]:
        next_steps.append("run a non-self-test CallFunction preflight without requesting native invocation")
    elif not gate_map["lua-call-function-native-executor-state"]:
        next_steps.append("capture a prepared non-self-test CallFunction native executor state")
    elif not gate_map["lua-call-function-native-invoke-non-self-test-gate"]:
        next_steps.append("run a non-self-test CallFunction invoke request that proves either the disabled gate or the enabled native bridge")
    elif not gate_map["lua-call-function-native-invoke-non-self-test-invoked"]:
        next_steps.append("explicitly enable and invoke a non-self-test CallFunction target through the Lua native bridge")
    elif not gate_map["lua-process-event-compat"]:
        next_steps.append("run a Lua mod that proves global and UObject-method ProcessEvent compatibility dispatch")
    elif not gate_map["lua-process-event-bridge-state"]:
        next_steps.append("run a Lua mod that proves GetProcessEventBridgeState native ProcessEvent bridge introspection")
    elif not gate_map["lua-process-event-native-invoke"]:
        next_steps.append("run a Lua mod that proves guarded Lua-triggered native ProcessEvent bridge invocation")
    elif not gate_map["lua-process-event-native-invoke-descriptor-preflight"]:
        next_steps.append("run a descriptor-backed non-self-test ProcessEvent preflight without requesting native invocation")
    elif not gate_map["lua-process-event-native-executor-state"]:
        next_steps.append("capture a prepared descriptor-backed non-self-test ProcessEvent native executor state")
    elif not gate_map["lua-process-event-native-invoke-non-self-test-gate"]:
        next_steps.append("run a descriptor-backed non-self-test ProcessEvent invoke request that proves either the disabled gate or the enabled native bridge")
    elif not gate_map["lua-process-event-native-invoke-non-self-test-invoked"]:
        next_steps.append("explicitly enable and invoke a descriptor-backed non-self-test ProcessEvent target through the Lua native bridge")
    elif not gate_map["lua-process-event-params-buffer"]:
        next_steps.append("run a Lua mod that calls CreateProcessEventParams(function) and proves a descriptor-backed ProcessEvent params buffer outside an active callback")
    elif not gate_map["lua-lifecycle-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterCustomEvent and lifecycle pre/post hooks dispatch around loader-owned lifecycle shims")
    elif not gate_map["lua-custom-event-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterCustomEvent dispatch around loader-owned custom event shims")
    elif not gate_map["lua-load-map-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterLoadMapPreHook/PostHook dispatch around loader-owned LoadMap shims")
    elif not gate_map["lua-begin-play-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterBeginPlayPreHook/PostHook dispatch around loader-owned BeginPlay shims")
    elif not gate_map["lua-init-game-state-hooks"]:
        next_steps.append("run a Lua mod that proves RegisterInitGameStatePreHook/PostHook dispatch around loader-owned InitGameState shims")
    elif not gate_map["lua-object-notify"]:
        next_steps.append("run a Lua mod that proves NotifyOnNewObject dispatches multiple callbacks for a newly constructed object handle")
    elif not gate_map["lua-synthetic-outer"]:
        next_steps.append("run a Lua mod that proves StaticConstructObject preserves and resolves a loader-owned outer handle")
    elif not gate_map["lua-world-context"]:
        next_steps.append("run a Lua mod that proves GetWorld resolves a world-like handle and a world outer chain")
    elif not gate_map["lua-global-runtime-helpers"]:
        next_steps.append("run a Lua mod that proves global GetWorld() and GetEngine() helper resolution")
    elif not gate_map["lua-class-default-object"]:
        next_steps.append("run a Lua mod that proves GetCDO returns a class-default-object handle")
    elif not gate_map["lua-level"]:
        next_steps.append("run a Lua mod that proves GetLevel resolves a loader-owned level handle")
    elif not gate_map["ue-package-loading-surface"]:
        next_steps.append("find StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchors")
    elif not gate_map["anchor-coverage-package-loading"]:
        next_steps.append("prepare a canary env with package-loading anchor coverage before replacing LoadAsset")
    elif not gate_map["lua-load-asset-package-bridge-state"]:
        next_steps.append("run a Lua mod that queries the guarded LoadAsset package bridge state against a target-image package-loading anchor")
    elif not gate_map["lua-load-asset-package-abi-state"]:
        next_steps.append("run a Lua mod that queries the guarded LoadAsset package ABI state for the selected package-loading family")
    elif not gate_map["lua-load-asset-package-string-bridge"]:
        next_steps.append("stage a bounded package path through the guarded LoadAsset package string bridge")
    elif not gate_map["lua-load-asset-package-native-buffer"]:
        next_steps.append("stage a bounded native LoadAsset package input buffer for the selected target ABI")
    elif not gate_map["lua-load-asset-package-tchar-buffer"]:
        next_steps.append("stage the package path as a target TCHAR buffer before native LoadAsset package invocation")
    elif not gate_map["lua-load-asset-package-tchar-verification"]:
        next_steps.append("verify the target TCHAR layout for the selected package-loading family before native LoadAsset package invocation")
    elif not gate_map["lua-load-asset-package-call-frame-verification"]:
        next_steps.append("verify the selected package-loading call frame before native LoadAsset package invocation")
    elif not gate_map["lua-load-asset-package-crash-guard"]:
        next_steps.append("query the guarded LoadAsset package crash-guard state before native invocation")
    elif not gate_map["lua-load-asset-package-guarded-call"]:
        next_steps.append("query the guarded LoadAsset package guarded-call state before native invocation")
    elif not gate_map["lua-load-asset-package-return-validation"]:
        next_steps.append("query the guarded LoadAsset package return-validation state before native invocation")
    elif not gate_map["lua-load-asset-package-native-call-adapter"]:
        next_steps.append("query the guarded LoadAsset package native call adapter before native invocation")
    elif not gate_map["lua-load-asset-package-invocation-descriptor"]:
        next_steps.append("construct the guarded LoadAsset package native invocation descriptor before native invocation")
    elif not gate_map["lua-load-asset-package-native-executor"]:
        next_steps.append("promote the guarded LoadAsset package native executor to target-image ready/final-call-eligible state")
    elif not gate_map["lua-load-asset-package-native-invocation"]:
        next_steps.append("explicitly enable and invoke the guarded LoadAsset package native call, then validate the target-image return")
    elif not gate_map["lua-load-asset-package"]:
        next_steps.append("replace registry-only LoadAsset with a real package/asset backend and prove it from a Lua mod")
    elif not gate_map["lua-load-class-package-abi-state"]:
        next_steps.append("run a Lua mod that queries the guarded LoadClass StaticLoadClass ABI state")
    elif not gate_map["lua-load-class-package-call-frame-verification"]:
        next_steps.append("verify the guarded LoadClass StaticLoadClass call frame before native invocation")
    elif not gate_map["lua-load-class-package-native-executor"]:
        next_steps.append("promote the guarded LoadClass StaticLoadClass native executor to ready/final-call-eligible state")
    elif not gate_map["lua-load-class-package-native-invocation"]:
        next_steps.append("explicitly enable and invoke guarded LoadClass through target-image StaticLoadClass")
    elif not gate_map["lua-static-construct-object-native-executor-state"]:
        next_steps.append("run a Lua mod that queries the guarded StaticConstructObject native executor state")
    elif not gate_map["lua-static-construct-object-native-executor-ready"]:
        next_steps.append("promote a target-image StaticConstructObject address and prove ABI/call-frame/final-invoke readiness")
    elif not gate_map["lua-static-construct-object-native-invoke"]:
        next_steps.append("explicitly enable and invoke target-image StaticConstructObject through the guarded Lua native bridge")
    elif not gate_map["lua-reflection-self-test"]:
        next_steps.append("run the Lua reflection/property self-test before live FProperty marshaling")
    elif not gate_map["lua-reflection-numeric-property-values"]:
        next_steps.append("run the Lua reflection self-test with FFloatProperty/FDoubleProperty get/set coverage")
    elif not gate_map["lua-reflection-name-text-property-values"]:
        next_steps.append("run the Lua reflection self-test with FNameProperty/FTextProperty get/set coverage")
    elif not gate_map["lua-reflection-for-each-property"]:
        next_steps.append("run the Lua reflection self-test with Reflection():ForEachProperty descriptor enumeration")
    elif not gate_map["lua-reflection-for-each-property-runtime"]:
        next_steps.append("run the Lua reflection self-test with Reflection():ForEachProperty over a promoted non-self-test descriptor")
    elif not gate_map["lua-reflection-live-descriptor-typed-class-runtime"]:
        next_steps.append("run the Lua reflection self-test with a promoted non-self-test live descriptor whose decoded FProperty class reaches Lua")
    elif not gate_map["lua-reflection-live-descriptor-values"]:
        next_steps.append("run the Lua reflection self-test against a promoted live descriptor and prove descriptor GetValue/SetValue")
    elif not gate_map["lua-reflection-live-descriptor-values-runtime"]:
        next_steps.append("run the Lua reflection self-test against a promoted non-self-test live descriptor and prove descriptor GetValue/SetValue")
    elif not gate_map["lua-process-event-self-test"]:
        next_steps.append("run the ProcessEvent-shaped Lua callback hook self-test before game ProcessEvent hook work")
    elif not gate_map["ue-process-event-hook-probe"]:
        next_steps.append("run the guarded ProcessEvent install/restore probe on a resolved ProcessEvent target")
    elif not gate_map["ue-process-event-hook-runtime-target"]:
        next_steps.append("rerun the guarded ProcessEvent hook probe against a non-self-test resolved ProcessEvent target")
    elif not gate_map["ue-call-function-hook-probe"]:
        next_steps.append("run the guarded CallFunctionByNameWithArguments install/restore probe on a resolved target")
    elif not gate_map["ue-call-function-hook-runtime-target"]:
        next_steps.append("rerun the guarded CallFunctionByNameWithArguments hook probe against a non-self-test resolved target")
    elif not gate_map["ue-call-function-live-hook"]:
        next_steps.append("install the opt-in persistent CallFunctionByNameWithArguments hook scaffold on a resolved target")
    elif not gate_map["ue-call-function-live-hook-runtime-target"]:
        next_steps.append("install the opt-in persistent CallFunctionByNameWithArguments hook on a non-self-test resolved target")
    elif not gate_map["ue-process-event-live-hook"]:
        next_steps.append("install the opt-in persistent ProcessEvent hook scaffold on a resolved target")
    elif not gate_map["ue-process-event-live-hook-runtime-target"]:
        next_steps.append("install the opt-in persistent ProcessEvent hook on a non-self-test resolved ProcessEvent target")
    elif not gate_map["ue-process-event-dispatch-self-test"]:
        next_steps.append("arm and invoke the native ProcessEvent dispatch callback registry")
    elif not gate_map["ue-process-event-live-lua-dispatch"]:
        next_steps.append("arm the opt-in live ProcessEvent Lua dispatch bridge and prove RegisterHook callbacks run from the live hook")
    elif not gate_map["ue-process-event-lua-context-handles"]:
        next_steps.append("route live ProcessEvent Lua callbacks with resolved UObject, UFunction, and params context tables")
    elif not gate_map["ue-process-event-live-function-path"]:
        next_steps.append("prove live ProcessEvent ctx.Function path matches a decoded scanned UFunction identity before routing RegisterHook by path")
    elif not gate_map["ue-process-event-live-runtime-context"]:
        next_steps.append("sample a non-self-test live ProcessEvent call whose ctx.Function matches a decoded runtime UFunction identity")
    elif not gate_map["ue-process-event-live-runtime-registry-context"]:
        next_steps.append("sample a non-self-test live ProcessEvent call whose object/function identities resolve through the promoted registries")
    elif not gate_map["ue-process-event-lua-param-accessors"]:
        next_steps.append("prove Lua GetFunctionParams plus descriptor-handle GetParamDescriptor/GetParamValue/SetParamValue access from both ProcessEvent self-test and live hook callbacks")
    elif not gate_map["ue-process-event-live-class-aware-param-values"]:
        next_steps.append("prove a live ProcessEvent Lua callback where ctx.Function resolves through the promoted UFunction registry and descriptor-backed GetParamValue/SetParamValue operates on the active params pointer")
    elif not gate_map["ue-process-event-lua-scalar-param-accessors"]:
        next_steps.append("prove signed/unsigned integer plus float/double ProcessEvent Lua param get/set coverage in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-lua-name-string-param-accessors"]:
        next_steps.append("prove FName/FString ProcessEvent Lua param get/set coverage in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-lua-struct-param-accessors"]:
        next_steps.append("prove FVector-shaped FStructProperty ProcessEvent Lua param get/set coverage in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-lua-enum-param-accessors"]:
        next_steps.append("prove FEnumProperty ProcessEvent Lua param get/set coverage in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-lua-object-param-accessors"]:
        next_steps.append("prove FObjectProperty ProcessEvent Lua param get/set coverage in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-lua-bool-param-accessors"]:
        next_steps.append("prove FBoolProperty ProcessEvent Lua param get/set coverage in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-live-array-container-param-values"]:
        next_steps.append("sample a live TArray/FScriptArray ProcessEvent param as a typed container header before claiming Lua dispatch parity")
    elif not gate_map["ue-process-event-live-set-container-param-values"]:
        next_steps.append("sample a live TSet/FScriptSet ProcessEvent param as a typed container header before claiming Lua dispatch parity")
    elif not gate_map["ue-process-event-live-map-container-param-values"]:
        next_steps.append("sample a live TMap/FScriptMap ProcessEvent param as a typed container header before claiming Lua dispatch parity")
    elif not gate_map["ue-process-event-live-set-map-container-param-values"]:
        next_steps.append("sample both live set and map ProcessEvent params through the FScriptSetHeader/FScriptMapHeader paths before claiming Lua dispatch parity")
    elif not gate_map["ue-process-event-container-alias-methods"]:
        next_steps.append("prove ProcessEvent container Get/get aliases for arrays, sets, and maps in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-container-storage-layout-methods"]:
        next_steps.append("prove ProcessEvent container GetStorageLayout, IsSparseLayoutValidated, and GetSlotStride methods for arrays, sets, and maps in both self-test and live hook callbacks")
    elif not gate_map["ue-process-event-lua-hook-routing"]:
        next_steps.append("prove multiple Lua RegisterHook entries route only the matching ProcessEvent function path before exposing mod callbacks")
    elif not gate_map["ue-process-event-lua-hook-alias-routing"]:
        next_steps.append("run a live Lua ProcessEvent canary that registers a UE4SS-style /Script hook path whose terminal function name matches the decoded runtime UFunction path")
    elif not gate_map["ue-call-function-live-lua-dispatch"]:
        next_steps.append("arm the opt-in live CallFunctionByNameWithArguments Lua dispatch bridge and prove pre/post callbacks run from the live hook")
    elif not gate_map["lua-mod-entrypoints"]:
        next_steps.append("load a Lua mod entrypoint and prove its registered callbacks dispatch before exposing UE4SS Lua APIs")
    elif not gate_map["lua-object-registry"]:
        next_steps.append("ingest class-mapped UObject probe candidates into the Lua object registry")
    elif not gate_map["lua-object-registry-checks"]:
        next_steps.append("prove candidate object registry path/name/class/address lookup consistency before relying on FindObject semantics")
    elif not gate_map["lua-object-registry-runtime"]:
        next_steps.append("prove candidate object registry path/name/class/address lookup consistency on a non-self-test runtime object before relying on FindObject semantics")
    elif not gate_map["lua-decoded-object-aliases"]:
        next_steps.append("promote decoded UObject FNames into Lua object aliases before relying on UE4SS-style FindObject names")
    elif not gate_map["lua-decoded-object-aliases-runtime"]:
        next_steps.append("promote non-self-test decoded UObject FNames into Lua object aliases before relying on UE4SS-style FindObject names")
    elif not gate_map["ue-object-array-registry"]:
        next_steps.append("walk a bounded GUObjectArray/FChunkedFixedUObjectArray candidate into the Lua object registry")
    elif not gate_map["ue-object-array-registry-runtime"]:
        next_steps.append("walk a non-self-test bounded GUObjectArray/FChunkedFixedUObjectArray candidate into the Lua object registry")
    elif not gate_map["ue-object-native-identities"]:
        next_steps.append("promote decoded UObject names, decoded class names, class pointers, and outer pointers into Lua object handles")
    elif not gate_map["ue-object-internal-flags"]:
        next_steps.append("promote readable FUObjectItem InternalFlags into Lua object handles before relying on HasAnyInternalFlags")
    elif not gate_map["ue-fname-decoder"]:
        next_steps.append("decode UObject names through a bounded FNamePool reader")
    elif not gate_map["lua-reflection-named-property"]:
        next_steps.append("run the Lua reflection self-test with decoded FName property aliases enabled")
    elif not gate_map["lua-reflection-live-descriptor-typed-values-runtime"]:
        next_steps.append("prove a promoted non-self-test live reflection descriptor returns a typed GetValue result")
    elif not gate_map["lua-reflection-live-descriptor-typed-set-values-runtime"]:
        next_steps.append("prove a promoted non-self-test live reflection descriptor accepts a typed SetValue result")
    elif not ready_lua:
        next_steps.append("add guarded ProcessEvent hook dispatch before Lua/mod APIs")
    else:
        next_steps.append(
            "prove promoted UFunction param descriptors and class-aware GetParamValue/SetParamValue against a real ProcessEvent ctx.Function and active params pointer before full FProperty marshaling"
        )

    live_target_image_contract = live_target_image_canary_contract(
        {
            "targetObjectDiscovery": ready_target_object_discovery,
            "targetImageProcess": gate_map["target-image-process"],
            "runtimeRootDiscovery": gate_map["ue-runtime-root-discovery"],
            "runtimeRootValidation": gate_map["ue-runtime-root-validation"],
            "targetHooks": ready_target_hooks,
            "targetPackageLoadingSurface": gate_map["ue-target-package-loading-surface"],
            "signatureManifestExact": signatures["exactOnly"],
            "signatureManifestPromotable": signatures["allPromotable"],
            "anchorCoverageObjectDiscovery": anchor_coverage["readyForTargetObjectDiscovery"],
            "anchorCoverageHookPlanning": anchor_coverage["readyForTargetHookPlanning"],
            "anchorCoveragePackageLoading": anchor_coverage["readyForTargetPackageLoading"],
            "objectDiscoveryCoverage": object_discovery_coverage["readyForObjectDiscovery"],
            "findObjectSemantics": object_discovery_coverage["readyForFindObjectSemantics"],
            "luaObjectRegistryRuntime": gate_map["lua-object-registry-runtime"],
            "luaFunctionRegistryRuntime": gate_map["lua-function-registry-runtime"],
            "luaDecodedObjectAliasesRuntime": gate_map["lua-decoded-object-aliases-runtime"],
            "ueObjectArrayShape": gate_map["ue-object-array-shape"],
            "ueObjectArrayRegistryRuntime": gate_map["ue-object-array-registry-runtime"],
            "ueObjectNativeIdentities": gate_map["ue-object-native-identities"],
            "ueObjectInternalFlags": gate_map["ue-object-internal-flags"],
            "ueFNameDecoder": gate_map["ue-fname-decoder"],
            "luaObjectOuterChainIdentities": gate_map["lua-object-outer-chain-identities"],
            "luaObjectApi": gate_map["lua-object-api"],
            "luaFunctionIterationRuntime": gate_map["lua-function-iteration-runtime"],
            "luaStaticConstructObjectNativeExecutorState": gate_map[
                "lua-static-construct-object-native-executor-state"
            ],
            "luaStaticConstructObjectNativeExecutorReady": gate_map[
                "lua-static-construct-object-native-executor-ready"
            ],
            "luaStaticConstructObjectNativeInvoke": gate_map[
                "lua-static-construct-object-native-invoke"
            ],
            "ueReflectionPropertyDescriptorsRuntime": gate_map["ue-reflection-property-descriptors-runtime"],
            "ueReflectionPropertyValuesRuntime": gate_map["ue-reflection-property-values-runtime"],
            "luaReflectionForEachPropertyRuntime": gate_map["lua-reflection-for-each-property-runtime"],
            "luaReflectionLiveDescriptorTypedClassRuntime": gate_map["lua-reflection-live-descriptor-typed-class-runtime"],
            "luaReflectionLiveDescriptorTypedValuesRuntime": gate_map["lua-reflection-live-descriptor-typed-values-runtime"],
            "luaReflectionLiveDescriptorTypedSetValuesRuntime": gate_map["lua-reflection-live-descriptor-typed-set-values-runtime"],
            "luaReflectionLiveDescriptorValuesRuntime": gate_map["lua-reflection-live-descriptor-values-runtime"],
            "ueProcessEventHookRuntimeTarget": gate_map["ue-process-event-hook-runtime-target"],
            "ueProcessEventLiveHookRuntimeTarget": gate_map["ue-process-event-live-hook-runtime-target"],
            "ueProcessEventActiveValidation": gate_map["ue-process-event-active-validation"],
            "ueProcessEventSyntheticTargetEntry": gate_map["ue-process-event-synthetic-target-entry"],
            "ueProcessEventLiveLuaDispatch": gate_map["ue-process-event-live-lua-dispatch"],
            "ueProcessEventLiveFunctionPath": gate_map["ue-process-event-live-function-path"],
            "ueProcessEventLiveRuntimeContext": gate_map["ue-process-event-live-runtime-context"],
            "ueProcessEventLiveRegistryContext": gate_map["ue-process-event-live-registry-context"],
            "ueProcessEventLiveRuntimeRegistryContext": gate_map["ue-process-event-live-runtime-registry-context"],
            "ueProcessEventLiveParamValues": gate_map["ue-process-event-live-param-values"],
            "ueProcessEventLiveRawParamValues": gate_map["ue-process-event-live-raw-param-values"],
            "ueProcessEventLiveContainerParamValues": gate_map["ue-process-event-live-container-param-values"],
            "ueProcessEventLiveArrayContainerParamValues": gate_map["ue-process-event-live-array-container-param-values"],
            "ueProcessEventLiveSetContainerParamValues": gate_map["ue-process-event-live-set-container-param-values"],
            "ueProcessEventLiveMapContainerParamValues": gate_map["ue-process-event-live-map-container-param-values"],
            "ueProcessEventLiveSetMapContainerParamValues": gate_map["ue-process-event-live-set-map-container-param-values"],
            "ueProcessEventLiveContainerDataSamples": gate_map["ue-process-event-live-container-data-samples"],
            "ueProcessEventLuaContextHandles": gate_map["ue-process-event-lua-context-handles"],
            "ueProcessEventLuaParamAccessors": gate_map["ue-process-event-lua-param-accessors"],
            "ueProcessEventLiveClassAwareParamValues": gate_map["ue-process-event-live-class-aware-param-values"],
            "ueProcessEventFunctionParamMethod": gate_map["ue-process-event-function-param-method"],
            "ueProcessEventFunctionParamLookupMethod": gate_map["ue-process-event-function-param-lookup-method"],
            "ueProcessEventFunctionParamIterationMethod": gate_map["ue-process-event-function-param-iteration-method"],
            "ueProcessEventContainerAliasMethods": gate_map["ue-process-event-container-alias-methods"],
            "ueProcessEventContainerStorageLayoutMethods": gate_map["ue-process-event-container-storage-layout-methods"],
            "ueProcessEventLuaScalarParamAccessors": gate_map["ue-process-event-lua-scalar-param-accessors"],
            "ueProcessEventLuaNameStringParamAccessors": gate_map["ue-process-event-lua-name-string-param-accessors"],
            "ueProcessEventLuaStructParamAccessors": gate_map["ue-process-event-lua-struct-param-accessors"],
            "ueProcessEventLuaEnumParamAccessors": gate_map["ue-process-event-lua-enum-param-accessors"],
            "ueProcessEventLuaObjectParamAccessors": gate_map["ue-process-event-lua-object-param-accessors"],
            "ueProcessEventLuaBoolParamAccessors": gate_map["ue-process-event-lua-bool-param-accessors"],
            "ueProcessEventLuaHookRouting": gate_map["ue-process-event-lua-hook-routing"],
            "ueProcessEventLuaHookAliasRouting": gate_map["ue-process-event-lua-hook-alias-routing"],
            "luaProcessEventNativeInvoke": gate_map["lua-process-event-native-invoke"],
            "luaProcessEventNativeInvokeDescriptorPreflight": gate_map[
                "lua-process-event-native-invoke-descriptor-preflight"
            ],
            "luaProcessEventNativeExecutorState": gate_map[
                "lua-process-event-native-executor-state"
            ],
            "luaProcessEventNativeInvokeNonSelfTestGate": gate_map[
                "lua-process-event-native-invoke-non-self-test-gate"
            ],
            "luaProcessEventNativeInvokeNonSelfTestInvoked": gate_map[
                "lua-process-event-native-invoke-non-self-test-invoked"
            ],
            "ueCallFunctionHookRuntimeTarget": gate_map["ue-call-function-hook-runtime-target"],
            "ueCallFunctionLiveHookRuntimeTarget": gate_map["ue-call-function-live-hook-runtime-target"],
            "ueCallFunctionActiveValidation": gate_map["ue-call-function-active-validation"],
            "ueCallFunctionLiveLuaDispatch": gate_map["ue-call-function-live-lua-dispatch"],
            "luaCallFunctionNativeInvoke": gate_map["lua-call-function-native-invoke"],
            "luaCallFunctionNativeInvokePreflight": gate_map[
                "lua-call-function-native-invoke-preflight"
            ],
            "luaCallFunctionNativeExecutorState": gate_map[
                "lua-call-function-native-executor-state"
            ],
            "luaCallFunctionNativeInvokeNonSelfTestGate": gate_map[
                "lua-call-function-native-invoke-non-self-test-gate"
            ],
            "luaCallFunctionNativeInvokeNonSelfTestInvoked": gate_map[
                "lua-call-function-native-invoke-non-self-test-invoked"
            ],
            "luaLoadAssetPackageCrashGuard": gate_map["lua-load-asset-package-crash-guard"],
            "luaLoadAssetPackageGuardedCall": gate_map["lua-load-asset-package-guarded-call"],
            "luaLoadAssetPackageReturnValidation": gate_map["lua-load-asset-package-return-validation"],
            "luaLoadAssetPackageNativeCallAdapter": gate_map["lua-load-asset-package-native-call-adapter"],
            "luaLoadAssetPackageInvocationDescriptor": gate_map["lua-load-asset-package-invocation-descriptor"],
            "luaLoadAssetPackageNativeExecutor": gate_map["lua-load-asset-package-native-executor"],
            "luaLoadAssetPackageNativeInvocation": gate_map["lua-load-asset-package-native-invocation"],
            "luaLoadAssetPackage": gate_map["lua-load-asset-package"],
            "luaLoadClassPackageAbiState": gate_map["lua-load-class-package-abi-state"],
            "luaLoadClassPackageCallFrameVerification": gate_map[
                "lua-load-class-package-call-frame-verification"
            ],
            "luaLoadClassPackageNativeExecutor": gate_map[
                "lua-load-class-package-native-executor"
            ],
            "luaLoadClassPackageNativeInvocation": gate_map[
                "lua-load-class-package-native-invocation"
            ],
        }
    )
    ready_ue4ss_lua_api_complete = (
        ready_lua
        and gate_map["lua-load-asset-package"]
        and gate_map["lua-load-asset-package-crash-guard"]
        and gate_map["lua-load-asset-package-guarded-call"]
        and gate_map["lua-load-asset-package-return-validation"]
        and gate_map["lua-load-asset-package-native-call-adapter"]
        and gate_map["lua-load-asset-package-invocation-descriptor"]
        and gate_map["lua-load-asset-package-native-executor"]
        and gate_map["lua-load-asset-package-native-invocation"]
        and gate_map["lua-load-class-package-abi-state"]
        and gate_map["lua-load-class-package-call-frame-verification"]
        and gate_map["lua-load-class-package-native-executor"]
        and gate_map["lua-load-class-package-native-invocation"]
        and live_target_image_contract["ready"]
    )

    report = {
        "schemaVersion": "dune-ue4ss-port-readiness/v1",
        "logCount": len(log_summaries),
        "loaders": merged["loaders"],
        "pids": merged["pids"],
        "loadedExes": merged["loadedExes"],
        "modules": merged["modules"],
        "targetImageSubstrings": target_image_substrings,
        "autoTargetPidFilters": merged["autoTargetPidFilters"],
        "gates": gates,
        "signatures": signatures,
        "anchorCoverage": anchor_coverage,
        "anchorGroups": {
            "anchors": merged["ueAnchorGroupCounts"],
            "mappedAnchors": merged["mappedUeAnchorGroupCounts"],
            "signatures": merged["ueAnchorSignatureGroupCounts"],
            "resolvedSignatures": merged["resolvedUeAnchorSignatureGroupCounts"],
        },
        "runtimeDiscovery": runtime_discovery,
        "runtimeRootValidation": runtime_root_validation,
        "objectDiscoveryCoverage": object_discovery_coverage,
        "liveTargetImageCanaryContract": live_target_image_contract,
        "ue": ue,
        "canaryHints": {
            "ueFunctionPaths": merged["ueFunctionPaths"][:16],
            "ue4ssFunctionPaths": merged["ue4ssFunctionPaths"][:16],
            "ueFunctionFlagPaths": merged["ueFunctionFlagPaths"][:16],
            "activeValidationCandidates": merged["activeValidationCandidates"][:16],
        },
        "ready": {
            "objectDiscovery": ready_object_discovery,
            "targetImageProcess": gate_map["target-image-process"],
            "runtimeRootDiscovery": gate_map["ue-runtime-root-discovery"],
            "runtimeRootValidation": gate_map["ue-runtime-root-validation"],
            "targetObjectDiscovery": ready_target_object_discovery,
            "objectDiscoveryCoverage": object_discovery_coverage["readyForObjectDiscovery"],
            "findObjectSemantics": object_discovery_coverage["readyForFindObjectSemantics"],
            "signatureManifestExact": signatures["exactOnly"],
            "signatureManifestPromotable": signatures["allPromotable"],
            "hooks": ready_hooks,
            "targetHooks": ready_target_hooks,
            "reflection": ready_reflection,
            "luaDispatch": ready_lua,
            "liveTargetImageCanary": live_target_image_contract["ready"],
            "ue4ssLuaApiComplete": ready_ue4ss_lua_api_complete,
            "packageLoadingSurface": gate_map["ue-package-loading-surface"],
            "targetPackageLoadingSurface": gate_map["ue-target-package-loading-surface"],
            "pointerProbe": gate_map["ue-pointer-probe"],
            "layoutProbe": gate_map["ue-layout-probe"],
            "uobjectProbe": gate_map["ue-uobject-probe"],
            "ueReflectionProbe": gate_map["ue-reflection-probe"],
            "ueReflectionFieldWalk": gate_map["ue-reflection-field-walk"],
            "ueReflectionPropertyDescriptors": gate_map["ue-reflection-property-descriptors"],
            "ueReflectionPropertyDescriptorsRuntime": gate_map["ue-reflection-property-descriptors-runtime"],
            "ueFunctionParamDescriptors": gate_map["ue-function-param-descriptors"],
            "ueFunctionParamContainerChildren": gate_map["ue-function-param-container-children"],
            "ueFunctionIdentities": gate_map["ue-function-identities"],
            "ueFunctionNativeIdentities": gate_map["ue-function-native-identities"],
            "ueFunctionFlags": gate_map["ue-function-flags"],
            "ueReflectionPropertyValues": gate_map["ue-reflection-property-values"],
            "ueReflectionPropertyValuesRuntime": gate_map["ue-reflection-property-values-runtime"],
            "hookDispatch": gate_map["hook-dispatch-self-test"],
            "modDispatch": gate_map["mod-dispatch-self-test"],
            "luaRuntime": gate_map["lua-dispatch-self-test"],
            "luaSchedulerApi": gate_map["lua-scheduler-api"],
            "luaSchedulerApiMods": gate_map["lua-scheduler-api-mods"],
            "luaInputCommandApi": gate_map["lua-input-command-api"],
            "luaInputCommandApiMods": gate_map["lua-input-command-api-mods"],
            "luaObjectApi": gate_map["lua-object-api"],
            "luaLoadAssetBackendState": gate_map["lua-load-asset-backend-state"],
            "luaLoadAssetBackendAnchors": gate_map["lua-load-asset-backend-anchors"],
            "luaLoadAssetPackageBridgeState": gate_map["lua-load-asset-package-bridge-state"],
            "luaLoadAssetPackageNativeInvoke": gate_map["lua-load-asset-package-native-invoke"],
            "luaLoadAssetPackageAbiState": gate_map["lua-load-asset-package-abi-state"],
            "luaLoadAssetPackageStringBridge": gate_map["lua-load-asset-package-string-bridge"],
            "luaLoadAssetPackageNativeBuffer": gate_map["lua-load-asset-package-native-buffer"],
            "luaLoadAssetPackageTCharBuffer": gate_map["lua-load-asset-package-tchar-buffer"],
            "luaLoadAssetPackageTCharVerification": gate_map["lua-load-asset-package-tchar-verification"],
            "luaLoadAssetPackageCallFrame": gate_map["lua-load-asset-package-call-frame"],
            "luaLoadAssetPackageCallFrameVerification": gate_map["lua-load-asset-package-call-frame-verification"],
            "luaLoadAssetPackageCrashGuard": gate_map["lua-load-asset-package-crash-guard"],
            "luaLoadAssetPackageGuardedCall": gate_map["lua-load-asset-package-guarded-call"],
            "luaLoadAssetPackageReturnValidation": gate_map["lua-load-asset-package-return-validation"],
            "luaLoadAssetPackageNativeCallAdapter": gate_map["lua-load-asset-package-native-call-adapter"],
            "luaLoadAssetPackageInvocationDescriptor": gate_map["lua-load-asset-package-invocation-descriptor"],
            "luaLoadAssetPackageNativeExecutor": gate_map["lua-load-asset-package-native-executor"],
            "luaLoadAssetPackageNativeInvocation": gate_map["lua-load-asset-package-native-invocation"],
            "luaLoadAssetPackagePreflight": gate_map["lua-load-asset-package-preflight"],
            "luaLoadAssetPackage": gate_map["lua-load-asset-package"],
            "luaLoadClassPackageAbiState": gate_map["lua-load-class-package-abi-state"],
            "luaLoadClassPackageCallFrameVerification": gate_map[
                "lua-load-class-package-call-frame-verification"
            ],
            "luaLoadClassPackageNativeExecutor": gate_map[
                "lua-load-class-package-native-executor"
            ],
            "luaLoadClassPackageNativeInvocation": gate_map[
                "lua-load-class-package-native-invocation"
            ],
            "luaFunctionIteration": gate_map["lua-function-iteration"],
            "luaFunctionIterationRuntime": gate_map["lua-function-iteration-runtime"],
            "luaStaticConstructObjectNativeExecutorState": gate_map[
                "lua-static-construct-object-native-executor-state"
            ],
            "luaStaticConstructObjectNativeExecutorReady": gate_map[
                "lua-static-construct-object-native-executor-ready"
            ],
            "luaStaticConstructObjectNativeInvoke": gate_map[
                "lua-static-construct-object-native-invoke"
            ],
            "luaProcessConsoleExecHooks": gate_map["lua-process-console-exec-hooks"],
            "luaLocalPlayerExecHooks": gate_map["lua-local-player-exec-hooks"],
            "luaCallFunctionHooks": gate_map["lua-call-function-hooks"],
            "luaCallFunctionStructuredArgs": gate_map["lua-call-function-structured-args"],
            "luaCallFunctionNativeInvoke": gate_map["lua-call-function-native-invoke"],
            "luaCallFunctionNativeInvokePreflight": gate_map[
                "lua-call-function-native-invoke-preflight"
            ],
            "luaCallFunctionNativeExecutorState": gate_map[
                "lua-call-function-native-executor-state"
            ],
            "luaCallFunctionNativeInvokeNonSelfTestGate": gate_map[
                "lua-call-function-native-invoke-non-self-test-gate"
            ],
            "luaCallFunctionNativeInvokeNonSelfTestInvoked": gate_map[
                "lua-call-function-native-invoke-non-self-test-invoked"
            ],
            "luaProcessEventCompat": gate_map["lua-process-event-compat"],
            "luaProcessEventBridgeState": gate_map["lua-process-event-bridge-state"],
            "luaProcessEventNativeInvoke": gate_map["lua-process-event-native-invoke"],
            "luaProcessEventNativeInvokeDescriptorPreflight": gate_map[
                "lua-process-event-native-invoke-descriptor-preflight"
            ],
            "luaProcessEventNativeExecutorState": gate_map[
                "lua-process-event-native-executor-state"
            ],
            "luaProcessEventNativeInvokeNonSelfTestGate": gate_map[
                "lua-process-event-native-invoke-non-self-test-gate"
            ],
            "luaProcessEventNativeInvokeNonSelfTestInvoked": gate_map[
                "lua-process-event-native-invoke-non-self-test-invoked"
            ],
            "luaProcessEventParamsBuffer": gate_map["lua-process-event-params-buffer"],
            "luaLifecycleHooks": gate_map["lua-lifecycle-hooks"],
            "luaCustomEventHooks": gate_map["lua-custom-event-hooks"],
            "luaLoadMapHooks": gate_map["lua-load-map-hooks"],
            "luaBeginPlayHooks": gate_map["lua-begin-play-hooks"],
            "luaInitGameStateHooks": gate_map["lua-init-game-state-hooks"],
            "luaObjectNotify": gate_map["lua-object-notify"],
            "luaSyntheticOuter": gate_map["lua-synthetic-outer"],
            "luaObjectOuterChains": gate_map["lua-object-outer-chains"],
            "luaObjectOuterChainIdentities": gate_map["lua-object-outer-chain-identities"],
            "luaWorldContext": gate_map["lua-world-context"],
            "luaGlobalRuntimeHelpers": gate_map["lua-global-runtime-helpers"],
            "luaClassDefaultObject": gate_map["lua-class-default-object"],
            "luaLevel": gate_map["lua-level"],
            "luaReflection": gate_map["lua-reflection-self-test"],
            "luaReflectionRawSet": gate_map["lua-reflection-raw-set"],
            "luaReflectionNamedProperty": gate_map["lua-reflection-named-property"],
            "luaReflectionNumericPropertyValues": gate_map["lua-reflection-numeric-property-values"],
            "luaReflectionNameTextPropertyValues": gate_map["lua-reflection-name-text-property-values"],
            "luaReflectionArrayInnerProperty": gate_map["lua-reflection-array-inner-property"],
            "luaReflectionEnumProperty": gate_map["lua-reflection-enum-property"],
            "luaReflectionContainerProperties": gate_map["lua-reflection-container-properties"],
            "luaReflectionImportText": gate_map["lua-reflection-import-text"],
            "luaReflectionExportText": gate_map["lua-reflection-export-text"],
            "luaReflectionPropertyMetadata": gate_map["lua-reflection-property-metadata"],
            "luaReflectionDescriptorValues": gate_map["lua-reflection-descriptor-values"],
            "luaReflectionForEachProperty": gate_map["lua-reflection-for-each-property"],
            "luaReflectionForEachPropertyRuntime": gate_map["lua-reflection-for-each-property-runtime"],
            "luaReflectionLiveDescriptorTypedClassRuntime": gate_map["lua-reflection-live-descriptor-typed-class-runtime"],
            "luaReflectionLiveDescriptorTypedValuesRuntime": gate_map["lua-reflection-live-descriptor-typed-values-runtime"],
            "luaReflectionLiveDescriptorTypedSetValuesRuntime": gate_map["lua-reflection-live-descriptor-typed-set-values-runtime"],
            "luaReflectionLiveDescriptorValues": gate_map["lua-reflection-live-descriptor-values"],
            "luaReflectionLiveDescriptorValuesRuntime": gate_map["lua-reflection-live-descriptor-values-runtime"],
            "luaProcessEvent": gate_map["lua-process-event-self-test"],
            "ueProcessEventHookProbe": gate_map["ue-process-event-hook-probe"],
            "ueProcessEventHookRuntimeTarget": gate_map["ue-process-event-hook-runtime-target"],
            "ueCallFunctionHookProbe": gate_map["ue-call-function-hook-probe"],
            "ueCallFunctionHookRuntimeTarget": gate_map["ue-call-function-hook-runtime-target"],
            "ueCallFunctionLiveHook": gate_map["ue-call-function-live-hook"],
            "ueCallFunctionLiveHookRuntimeTarget": gate_map["ue-call-function-live-hook-runtime-target"],
            "ueCallFunctionActiveValidation": gate_map["ue-call-function-active-validation"],
            "ueCallFunctionLiveLuaDispatch": gate_map["ue-call-function-live-lua-dispatch"],
            "ueProcessEventLiveHook": gate_map["ue-process-event-live-hook"],
            "ueProcessEventLiveHookRuntimeTarget": gate_map["ue-process-event-live-hook-runtime-target"],
            "ueProcessEventActiveValidation": gate_map["ue-process-event-active-validation"],
            "ueProcessEventSyntheticTargetEntry": gate_map["ue-process-event-synthetic-target-entry"],
            "ueProcessEventDispatch": gate_map["ue-process-event-dispatch-self-test"],
            "ueProcessEventLiveLuaDispatch": gate_map["ue-process-event-live-lua-dispatch"],
            "ueProcessEventLiveContext": gate_map["ue-process-event-live-context"],
            "ueProcessEventLiveFunctionPath": gate_map["ue-process-event-live-function-path"],
            "ueProcessEventLiveRuntimeContext": gate_map["ue-process-event-live-runtime-context"],
            "ueProcessEventLiveRegistryContext": gate_map["ue-process-event-live-registry-context"],
            "ueProcessEventLiveRuntimeRegistryContext": gate_map["ue-process-event-live-runtime-registry-context"],
            "ueProcessEventLiveParamValues": gate_map["ue-process-event-live-param-values"],
            "ueProcessEventLiveRawParamValues": gate_map["ue-process-event-live-raw-param-values"],
            "ueProcessEventLiveContainerParamValues": gate_map["ue-process-event-live-container-param-values"],
            "ueProcessEventLiveArrayContainerParamValues": gate_map["ue-process-event-live-array-container-param-values"],
            "ueProcessEventLiveSetContainerParamValues": gate_map["ue-process-event-live-set-container-param-values"],
            "ueProcessEventLiveMapContainerParamValues": gate_map["ue-process-event-live-map-container-param-values"],
            "ueProcessEventLiveSetMapContainerParamValues": gate_map["ue-process-event-live-set-map-container-param-values"],
            "ueProcessEventLiveContainerDataSamples": gate_map["ue-process-event-live-container-data-samples"],
            "ueProcessEventLuaContextHandles": gate_map["ue-process-event-lua-context-handles"],
            "ueProcessEventLuaParamAccessors": gate_map["ue-process-event-lua-param-accessors"],
            "ueProcessEventLiveClassAwareParamValues": gate_map["ue-process-event-live-class-aware-param-values"],
            "ueProcessEventFunctionParamMethod": gate_map["ue-process-event-function-param-method"],
            "ueProcessEventFunctionParamLookupMethod": gate_map["ue-process-event-function-param-lookup-method"],
            "ueProcessEventFunctionParamIterationMethod": gate_map["ue-process-event-function-param-iteration-method"],
            "ueProcessEventContainerAliasMethods": gate_map["ue-process-event-container-alias-methods"],
            "ueProcessEventContainerStorageLayoutMethods": gate_map["ue-process-event-container-storage-layout-methods"],
            "ueProcessEventLuaScalarParamAccessors": gate_map["ue-process-event-lua-scalar-param-accessors"],
            "ueProcessEventLuaNameStringParamAccessors": gate_map["ue-process-event-lua-name-string-param-accessors"],
            "ueProcessEventLuaStructParamAccessors": gate_map["ue-process-event-lua-struct-param-accessors"],
            "ueProcessEventLuaEnumParamAccessors": gate_map["ue-process-event-lua-enum-param-accessors"],
            "ueProcessEventLuaObjectParamAccessors": gate_map["ue-process-event-lua-object-param-accessors"],
            "ueProcessEventLuaBoolParamAccessors": gate_map["ue-process-event-lua-bool-param-accessors"],
            "ueProcessEventLuaHookRouting": gate_map["ue-process-event-lua-hook-routing"],
            "ueProcessEventLuaHookAliasRouting": gate_map["ue-process-event-lua-hook-alias-routing"],
            "luaMods": gate_map["lua-mod-entrypoints"],
            "luaObjectRegistry": gate_map["lua-object-registry"],
            "luaObjectRegistryChecks": gate_map["lua-object-registry-checks"],
            "luaObjectRegistryRuntime": gate_map["lua-object-registry-runtime"],
            "luaFunctionRegistryChecks": gate_map["lua-function-registry-checks"],
            "luaFunctionRegistryRuntime": gate_map["lua-function-registry-runtime"],
            "luaDecodedObjectAliases": gate_map["lua-decoded-object-aliases"],
            "luaDecodedObjectAliasesRuntime": gate_map["lua-decoded-object-aliases-runtime"],
            "ueObjectArrayRegistry": gate_map["ue-object-array-registry"],
            "ueObjectArrayShape": gate_map["ue-object-array-shape"],
            "ueObjectArrayRegistryRuntime": gate_map["ue-object-array-registry-runtime"],
            "ueObjectNativeIdentities": gate_map["ue-object-native-identities"],
            "ueObjectInternalFlags": gate_map["ue-object-internal-flags"],
            "ueFNameDecoder": gate_map["ue-fname-decoder"],
            "anchorSignatureResolver": merged["resolvedUeAnchorSignatureCount"] > 0,
            "anchorGroupProvenance": gate_map["ue-anchor-group-provenance"],
            "targetNames": gate_map["ue-target-names"],
            "targetObjects": gate_map["ue-target-objects"],
            "targetWorld": gate_map["ue-target-world"],
            "targetDispatch": gate_map["ue-target-dispatch"],
            "targetReflectionSurface": gate_map["ue-target-reflection-surface"],
            "anchorCoverageObjectDiscovery": anchor_coverage["readyForTargetObjectDiscovery"],
            "anchorCoverageHookPlanning": anchor_coverage["readyForTargetHookPlanning"],
            "anchorCoveragePackageLoading": anchor_coverage["readyForTargetPackageLoading"],
        },
        "nextSteps": next_steps,
    }
    if include_loader_matrix:
        report["perLoaderReadiness"] = build_per_loader_readiness(
            log_summaries,
            validation_summaries,
            anchor_coverages,
            merged["loaders"],
        )
    return report


def markdown(report):
    lines = ["# UE4SS Port Readiness", ""]
    lines.append(f"- Logs: `{report['logCount']}`")
    lines.append(f"- Loaders: `{', '.join(report['loaders']) or 'unknown'}`")
    lines.append(f"- Ready pointer probe: `{str(report['ready']['pointerProbe']).lower()}`")
    lines.append(f"- Ready layout probe: `{str(report['ready']['layoutProbe']).lower()}`")
    lines.append(f"- Ready UObject probe: `{str(report['ready']['uobjectProbe']).lower()}`")
    lines.append(f"- Ready UE reflection probe: `{str(report['ready']['ueReflectionProbe']).lower()}`")
    lines.append(f"- Ready UE reflection field walk: `{str(report['ready']['ueReflectionFieldWalk']).lower()}`")
    lines.append(f"- Ready UE reflection property descriptors: `{str(report['ready']['ueReflectionPropertyDescriptors']).lower()}`")
    lines.append(f"- Ready UE runtime reflection property descriptors: `{str(report['ready']['ueReflectionPropertyDescriptorsRuntime']).lower()}`")
    lines.append(f"- Ready UE function param descriptors: `{str(report['ready']['ueFunctionParamDescriptors']).lower()}`")
    lines.append(f"- Ready UE function param container children: `{str(report['ready']['ueFunctionParamContainerChildren']).lower()}`")
    lines.append(f"- Ready UE function identities: `{str(report['ready']['ueFunctionIdentities']).lower()}`")
    lines.append(f"- Ready UE function native identities: `{str(report['ready']['ueFunctionNativeIdentities']).lower()}`")
    lines.append(f"- Ready UE function flags: `{str(report['ready']['ueFunctionFlags']).lower()}`")
    lines.append(f"- Ready UE reflection property values: `{str(report['ready']['ueReflectionPropertyValues']).lower()}`")
    lines.append(f"- Ready UE runtime reflection property values: `{str(report['ready']['ueReflectionPropertyValuesRuntime']).lower()}`")
    lines.append(f"- Ready hook dispatch: `{str(report['ready']['hookDispatch']).lower()}`")
    lines.append(f"- Ready mod dispatch: `{str(report['ready']['modDispatch']).lower()}`")
    lines.append(f"- Ready Lua runtime: `{str(report['ready']['luaRuntime']).lower()}`")
    lines.append(f"- Ready Lua scheduler API: `{str(report['ready']['luaSchedulerApi']).lower()}`")
    lines.append(f"- Ready Lua scheduler API from mods: `{str(report['ready']['luaSchedulerApiMods']).lower()}`")
    lines.append(f"- Ready Lua input/command API: `{str(report['ready']['luaInputCommandApi']).lower()}`")
    lines.append(f"- Ready Lua input/command API from mods: `{str(report['ready']['luaInputCommandApiMods']).lower()}`")
    lines.append(f"- Ready Lua object API: `{str(report['ready']['luaObjectApi']).lower()}`")
    lines.append(f"- Ready Lua function iteration: `{str(report['ready']['luaFunctionIteration']).lower()}`")
    lines.append(f"- Ready Lua function iteration runtime evidence: `{str(report['ready']['luaFunctionIterationRuntime']).lower()}`")
    lines.append(f"- Ready Lua ProcessConsoleExec hooks: `{str(report['ready']['luaProcessConsoleExecHooks']).lower()}`")
    lines.append(f"- Ready Lua ULocalPlayerExec hooks: `{str(report['ready']['luaLocalPlayerExecHooks']).lower()}`")
    lines.append(f"- Ready Lua CallFunctionByNameWithArguments hooks: `{str(report['ready']['luaCallFunctionHooks']).lower()}`")
    lines.append(f"- Ready Lua CallFunctionByNameWithArguments structured args: `{str(report['ready']['luaCallFunctionStructuredArgs']).lower()}`")
    lines.append(f"- Ready Lua native CallFunction invoke: `{str(report['ready']['luaCallFunctionNativeInvoke']).lower()}`")
    lines.append(
        "- Ready Lua native CallFunction preflight: "
        f"`{str(report['ready']['luaCallFunctionNativeInvokePreflight']).lower()}`"
    )
    lines.append(
        "- Ready Lua native CallFunction executor state: "
        f"`{str(report['ready']['luaCallFunctionNativeExecutorState']).lower()}`"
    )
    lines.append(
        "- Ready Lua native CallFunction non-self-test gate: "
        f"`{str(report['ready']['luaCallFunctionNativeInvokeNonSelfTestGate']).lower()}`"
    )
    lines.append(
        "- Ready Lua native CallFunction non-self-test invoked: "
        f"`{str(report['ready']['luaCallFunctionNativeInvokeNonSelfTestInvoked']).lower()}`"
    )
    lines.append(f"- Ready Lua ProcessEvent compatibility: `{str(report['ready']['luaProcessEventCompat']).lower()}`")
    lines.append(f"- Ready Lua ProcessEvent bridge state: `{str(report['ready']['luaProcessEventBridgeState']).lower()}`")
    lines.append(f"- Ready Lua native ProcessEvent invoke: `{str(report['ready']['luaProcessEventNativeInvoke']).lower()}`")
    lines.append(
        "- Ready Lua native ProcessEvent descriptor preflight: "
        f"`{str(report['ready']['luaProcessEventNativeInvokeDescriptorPreflight']).lower()}`"
    )
    lines.append(
        "- Ready Lua native ProcessEvent executor state: "
        f"`{str(report['ready']['luaProcessEventNativeExecutorState']).lower()}`"
    )
    lines.append(
        "- Ready Lua native ProcessEvent non-self-test gate: "
        f"`{str(report['ready']['luaProcessEventNativeInvokeNonSelfTestGate']).lower()}`"
    )
    lines.append(
        "- Ready Lua native ProcessEvent non-self-test invoked: "
        f"`{str(report['ready']['luaProcessEventNativeInvokeNonSelfTestInvoked']).lower()}`"
    )
    lines.append(f"- Ready Lua ProcessEvent params buffer: `{str(report['ready']['luaProcessEventParamsBuffer']).lower()}`")
    lines.append(f"- Ready Lua lifecycle hooks: `{str(report['ready']['luaLifecycleHooks']).lower()}`")
    lines.append(f"- Ready Lua custom event hooks: `{str(report['ready']['luaCustomEventHooks']).lower()}`")
    lines.append(f"- Ready Lua LoadMap hooks: `{str(report['ready']['luaLoadMapHooks']).lower()}`")
    lines.append(f"- Ready Lua BeginPlay hooks: `{str(report['ready']['luaBeginPlayHooks']).lower()}`")
    lines.append(f"- Ready Lua InitGameState hooks: `{str(report['ready']['luaInitGameStateHooks']).lower()}`")
    lines.append(f"- Ready Lua object notification: `{str(report['ready']['luaObjectNotify']).lower()}`")
    lines.append(f"- Ready Lua synthetic outer: `{str(report['ready']['luaSyntheticOuter']).lower()}`")
    lines.append(
        "- Ready Lua StaticConstructObject native executor state: "
        f"`{str(report['ready']['luaStaticConstructObjectNativeExecutorState']).lower()}`"
    )
    lines.append(
        "- Ready Lua StaticConstructObject native executor target: "
        f"`{str(report['ready']['luaStaticConstructObjectNativeExecutorReady']).lower()}`"
    )
    lines.append(
        "- Ready Lua StaticConstructObject native invocation: "
        f"`{str(report['ready']['luaStaticConstructObjectNativeInvoke']).lower()}`"
    )
    lines.append(f"- Ready Lua world context: `{str(report['ready']['luaWorldContext']).lower()}`")
    lines.append(f"- Ready Lua global runtime helpers: `{str(report['ready']['luaGlobalRuntimeHelpers']).lower()}`")
    lines.append(f"- Ready Lua class default object: `{str(report['ready']['luaClassDefaultObject']).lower()}`")
    lines.append(f"- Ready Lua level: `{str(report['ready']['luaLevel']).lower()}`")
    lines.append(f"- Ready Lua reflection: `{str(report['ready']['luaReflection']).lower()}`")
    lines.append(f"- Ready Lua reflection raw set: `{str(report['ready']['luaReflectionRawSet']).lower()}`")
    lines.append(f"- Ready Lua reflection named property: `{str(report['ready']['luaReflectionNamedProperty']).lower()}`")
    lines.append(f"- Ready Lua reflection numeric property values: `{str(report['ready']['luaReflectionNumericPropertyValues']).lower()}`")
    lines.append(f"- Ready Lua reflection name/text property values: `{str(report['ready']['luaReflectionNameTextPropertyValues']).lower()}`")
    lines.append(f"- Ready Lua reflection array inner property: `{str(report['ready']['luaReflectionArrayInnerProperty']).lower()}`")
    lines.append(f"- Ready Lua reflection enum property: `{str(report['ready']['luaReflectionEnumProperty']).lower()}`")
    lines.append(f"- Ready Lua reflection container properties: `{str(report['ready']['luaReflectionContainerProperties']).lower()}`")
    lines.append(f"- Ready Lua reflection ImportText: `{str(report['ready']['luaReflectionImportText']).lower()}`")
    lines.append(f"- Ready Lua reflection ExportText: `{str(report['ready']['luaReflectionExportText']).lower()}`")
    lines.append(f"- Ready Lua reflection property metadata: `{str(report['ready']['luaReflectionPropertyMetadata']).lower()}`")
    lines.append(f"- Ready Lua reflection descriptor values: `{str(report['ready']['luaReflectionDescriptorValues']).lower()}`")
    lines.append(f"- Ready Lua Reflection:ForEachProperty: `{str(report['ready']['luaReflectionForEachProperty']).lower()}`")
    lines.append(f"- Ready Lua Reflection:ForEachProperty runtime: `{str(report['ready']['luaReflectionForEachPropertyRuntime']).lower()}`")
    lines.append(f"- Ready Lua live reflection descriptor typed class runtime: `{str(report['ready']['luaReflectionLiveDescriptorTypedClassRuntime']).lower()}`")
    lines.append(f"- Ready Lua live reflection descriptor typed values runtime: `{str(report['ready']['luaReflectionLiveDescriptorTypedValuesRuntime']).lower()}`")
    lines.append(f"- Ready Lua live reflection descriptor typed SetValue runtime: `{str(report['ready']['luaReflectionLiveDescriptorTypedSetValuesRuntime']).lower()}`")
    lines.append(f"- Ready Lua live reflection descriptor values: `{str(report['ready']['luaReflectionLiveDescriptorValues']).lower()}`")
    lines.append(f"- Ready Lua live reflection descriptor runtime values: `{str(report['ready']['luaReflectionLiveDescriptorValuesRuntime']).lower()}`")
    lines.append(f"- Ready Lua ProcessEvent hook: `{str(report['ready']['luaProcessEvent']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent hook probe: `{str(report['ready']['ueProcessEventHookProbe']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent hook runtime target: `{str(report['ready']['ueProcessEventHookRuntimeTarget']).lower()}`")
    lines.append(f"- Ready UE CallFunctionByNameWithArguments hook probe: `{str(report['ready']['ueCallFunctionHookProbe']).lower()}`")
    lines.append(f"- Ready UE CallFunctionByNameWithArguments hook runtime target: `{str(report['ready']['ueCallFunctionHookRuntimeTarget']).lower()}`")
    lines.append(f"- Ready UE CallFunctionByNameWithArguments live hook: `{str(report['ready']['ueCallFunctionLiveHook']).lower()}`")
    lines.append(f"- Ready UE CallFunctionByNameWithArguments live hook runtime target: `{str(report['ready']['ueCallFunctionLiveHookRuntimeTarget']).lower()}`")
    lines.append(f"- Ready UE CallFunctionByNameWithArguments active validation: `{str(report['ready']['ueCallFunctionActiveValidation']).lower()}`")
    lines.append(f"- Ready UE CallFunctionByNameWithArguments live Lua dispatch: `{str(report['ready']['ueCallFunctionLiveLuaDispatch']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live hook: `{str(report['ready']['ueProcessEventLiveHook']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live hook runtime target: `{str(report['ready']['ueProcessEventLiveHookRuntimeTarget']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent active validation: `{str(report['ready']['ueProcessEventActiveValidation']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent dispatch: `{str(report['ready']['ueProcessEventDispatch']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live Lua dispatch: `{str(report['ready']['ueProcessEventLiveLuaDispatch']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live context: `{str(report['ready']['ueProcessEventLiveContext']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live runtime context: `{str(report['ready']['ueProcessEventLiveRuntimeContext']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live registry context: `{str(report['ready']['ueProcessEventLiveRegistryContext']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live runtime registry context: `{str(report['ready']['ueProcessEventLiveRuntimeRegistryContext']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live param values: `{str(report['ready']['ueProcessEventLiveParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live raw param values: `{str(report['ready']['ueProcessEventLiveRawParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live container param values: `{str(report['ready']['ueProcessEventLiveContainerParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live array container param values: `{str(report['ready']['ueProcessEventLiveArrayContainerParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live set container param values: `{str(report['ready']['ueProcessEventLiveSetContainerParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live map container param values: `{str(report['ready']['ueProcessEventLiveMapContainerParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live set/map container param values: `{str(report['ready']['ueProcessEventLiveSetMapContainerParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live container data samples: `{str(report['ready']['ueProcessEventLiveContainerDataSamples']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua context handles: `{str(report['ready']['ueProcessEventLuaContextHandles']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua function-param accessors: `{str(report['ready']['ueProcessEventLuaParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent live class-aware param values: `{str(report['ready']['ueProcessEventLiveClassAwareParamValues']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Function:GetFunctionParams method: `{str(report['ready']['ueProcessEventFunctionParamMethod']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Function:GetParamDescriptor method: `{str(report['ready']['ueProcessEventFunctionParamLookupMethod']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Function:ForEachParam method: `{str(report['ready']['ueProcessEventFunctionParamIterationMethod']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent container alias methods: `{str(report['ready']['ueProcessEventContainerAliasMethods']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent container storage-layout methods: `{str(report['ready']['ueProcessEventContainerStorageLayoutMethods']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua scalar param accessors: `{str(report['ready']['ueProcessEventLuaScalarParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua name/string param accessors: `{str(report['ready']['ueProcessEventLuaNameStringParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua struct param accessors: `{str(report['ready']['ueProcessEventLuaStructParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua enum param accessors: `{str(report['ready']['ueProcessEventLuaEnumParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua object param accessors: `{str(report['ready']['ueProcessEventLuaObjectParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua bool param accessors: `{str(report['ready']['ueProcessEventLuaBoolParamAccessors']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua hook routing: `{str(report['ready']['ueProcessEventLuaHookRouting']).lower()}`")
    lines.append(f"- Ready UE ProcessEvent Lua hook alias routing: `{str(report['ready']['ueProcessEventLuaHookAliasRouting']).lower()}`")
    lines.append(f"- Ready Lua mods: `{str(report['ready']['luaMods']).lower()}`")
    lines.append(f"- Ready Lua object registry: `{str(report['ready']['luaObjectRegistry']).lower()}`")
    lines.append(f"- Ready Lua object registry checks: `{str(report['ready']['luaObjectRegistryChecks']).lower()}`")
    lines.append(f"- Ready Lua object registry runtime evidence: `{str(report['ready']['luaObjectRegistryRuntime']).lower()}`")
    lines.append(f"- Ready Lua function registry checks: `{str(report['ready']['luaFunctionRegistryChecks']).lower()}`")
    lines.append(f"- Ready Lua function registry runtime evidence: `{str(report['ready']['luaFunctionRegistryRuntime']).lower()}`")
    lines.append(f"- Ready Lua decoded object aliases: `{str(report['ready']['luaDecodedObjectAliases']).lower()}`")
    lines.append(f"- Ready Lua decoded object aliases runtime evidence: `{str(report['ready']['luaDecodedObjectAliasesRuntime']).lower()}`")
    lines.append(f"- Ready UE object array registry: `{str(report['ready']['ueObjectArrayRegistry']).lower()}`")
    lines.append(f"- Ready UE object array header shape: `{str(report['ready']['ueObjectArrayShape']).lower()}`")
    lines.append(f"- Ready UE object array registry runtime evidence: `{str(report['ready']['ueObjectArrayRegistryRuntime']).lower()}`")
    lines.append(f"- Ready UE object native identities: `{str(report['ready']['ueObjectNativeIdentities']).lower()}`")
    lines.append(f"- Ready UE object internal flags: `{str(report['ready']['ueObjectInternalFlags']).lower()}`")
    lines.append(f"- Ready UE FName decoder: `{str(report['ready']['ueFNameDecoder']).lower()}`")
    lines.append(f"- Ready signature-resolved anchors: `{str(report['ready']['anchorSignatureResolver']).lower()}`")
    lines.append(f"- Ready UE anchor group provenance: `{str(report['ready']['anchorGroupProvenance']).lower()}`")
    lines.append(f"- Ready anchor coverage object discovery: `{str(report['ready']['anchorCoverageObjectDiscovery']).lower()}`")
    lines.append(f"- Ready anchor coverage hook planning: `{str(report['ready']['anchorCoverageHookPlanning']).lower()}`")
    lines.append(f"- Ready anchor coverage package loading: `{str(report['ready']['anchorCoveragePackageLoading']).lower()}`")
    lines.append(f"- Ready target-image package loading surface: `{str(report['ready']['targetPackageLoadingSurface']).lower()}`")
    lines.append(f"- Ready runtime root discovery: `{str(report['ready']['runtimeRootDiscovery']).lower()}`")
    lines.append(f"- Ready runtime root validation: `{str(report['ready']['runtimeRootValidation']).lower()}`")
    root_validation = report.get("runtimeRootValidation", {})
    lines.append(
        f"- Runtime root validation: validated={root_validation.get('validatedNames', [])} "
        f"readyScans={root_validation.get('readyScanCount', 0)}"
    )
    lines.append(
        f"- Runtime discovery: promoted={report['runtimeDiscovery']['promotedNames']} "
        f"validated={report['runtimeDiscovery']['validatedNames']} "
        f"coverage={report['runtimeDiscovery']['coverage']} "
        f"failures={report['runtimeDiscovery']['failureCounts']}"
    )
    lines.append(f"- Ready object discovery coverage: `{str(report['ready']['objectDiscoveryCoverage']).lower()}`")
    lines.append(f"- Ready FindObject semantics: `{str(report['ready']['findObjectSemantics']).lower()}`")
    lines.append(f"- Ready object discovery: `{str(report['ready']['objectDiscovery']).lower()}`")
    lines.append(f"- Ready target-image object discovery: `{str(report['ready']['targetObjectDiscovery']).lower()}`")
    lines.append(f"- Ready hooks: `{str(report['ready']['hooks']).lower()}`")
    lines.append(f"- Ready target-image hooks: `{str(report['ready']['targetHooks']).lower()}`")
    lines.append(f"- Ready reflection: `{str(report['ready']['reflection']).lower()}`")
    lines.append(f"- Ready Lua dispatch: `{str(report['ready']['luaDispatch']).lower()}`")
    lines.append(f"- Ready live target-image canary: `{str(report['ready']['liveTargetImageCanary']).lower()}`")
    lines.append(f"- Ready complete UE4SS Lua API: `{str(report['ready']['ue4ssLuaApiComplete']).lower()}`")
    live_contract = report.get("liveTargetImageCanaryContract", {})
    if live_contract:
        lines.append(
            "- Missing live target-image canary keys: `"
            + (", ".join(live_contract.get("missingKeys", []) or []) or "none")
            + "`"
        )
    lines.append("")
    lines.append("## Object Discovery Coverage")
    lines.append("")
    for name, component in report["objectDiscoveryCoverage"]["components"].items():
        status = "pass" if component["passed"] else "block"
        lines.append(f"- `{status}` `{name}`")
    if report["objectDiscoveryCoverage"]["missingFindObjectComponents"]:
        lines.append(
            "- Missing FindObject components: `"
            + ", ".join(report["objectDiscoveryCoverage"]["missingFindObjectComponents"])
            + "`"
        )
    lines.append("")
    if report.get("perLoaderReadiness"):
        lines.append("## Per Loader Readiness")
        lines.append("")
        for loader, entry in sorted(report["perLoaderReadiness"].items()):
            ready = entry.get("ready", {})
            failed = entry.get("failedGates", [])
            failed_text = ", ".join(failed[:8]) if failed else "none"
            lines.append(
                f"- `{loader}` logs=`{entry.get('logCount', 0)}` "
                f"objectDiscovery=`{str(ready.get('objectDiscovery', False)).lower()}` "
                f"reflection=`{str(ready.get('reflection', False)).lower()}` "
                f"luaDispatch=`{str(ready.get('luaDispatch', False)).lower()}` "
                f"liveTargetImage=`{str(ready.get('liveTargetImageCanary', False)).lower()}` "
                f"ue4ssLuaApiComplete=`{str(ready.get('ue4ssLuaApiComplete', False)).lower()}` "
                f"runtimeContext=`{str(ready.get('ueProcessEventLiveRuntimeContext', False)).lower()}` "
                f"hookRouting=`{str(ready.get('ueProcessEventLuaHookRouting', False)).lower()}` "
                f"aliasRouting=`{str(ready.get('ueProcessEventLuaHookAliasRouting', False)).lower()}`"
            )
            live_contract = entry.get("liveTargetImageCanaryContract", {})
            missing_live = live_contract.get("missingKeys", []) if isinstance(live_contract, dict) else []
            lines.append(
                "  - live target-image missing: `"
                + (", ".join(missing_live[:8]) if missing_live else "none")
                + "`"
            )
            lines.append(f"  - first failed gates: `{failed_text}`")
        lines.append("")
    lines.append("## Gates")
    lines.append("")
    for item in report["gates"]:
        status = "pass" if item["passed"] else "block"
        lines.append(f"- `{status}` `{item['name']}` {item['evidence']}")
        if item["blocker"]:
            lines.append(f"  - blocker: {item['blocker']}")
    lines.append("")
    lines.append("## Next Steps")
    lines.append("")
    for step in report["nextSteps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def validate_runtime_log_path(path):
    try:
        stat = path.stat()
    except OSError as exc:
        raise ValueError(f"runtime log is not readable: {path}: {exc}") from exc
    if not path.is_file():
        raise ValueError(f"runtime log must be a regular file: {path}")
    if stat.st_size <= 0:
        raise ValueError(f"runtime log must not be empty: {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gate UE4SS-port readiness from loader logs and signature validations.")
    parser.add_argument("--client-log", type=Path, action="append", default=[], help="client loader/probe log")
    parser.add_argument("--server-log", type=Path, action="append", default=[], help="server loader/probe log")
    parser.add_argument("--log", type=Path, action="append", default=[], help="generic loader/probe log")
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--signature-validation-json", type=Path, action="append", default=[])
    parser.add_argument("--anchor-coverage-json", type=Path, action="append", default=[])
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    log_paths = args.log + args.client_log + args.server_log
    if not log_paths:
        parser.error("provide --log, --client-log, or --server-log")
    for path in log_paths:
        try:
            validate_runtime_log_path(path)
        except ValueError as exc:
            parser.error(str(exc))
    log_summaries = [
        summarize_log(path, args.loader, args.pid, args.exe_substring)
        for path in log_paths
    ]
    validations = [load_json(path) for path in args.signature_validation_json]
    anchor_coverages = [
        normalize_anchor_coverage_sidecar(load_json(path))
        for path in args.anchor_coverage_json
    ]
    report = build_report(log_summaries, validations, anchor_coverages)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(report))


if __name__ == "__main__":
    main()
