#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


CATEGORY_NEEDLES = {
    "package": (
        "StaticLoadObject",
        "LoadObject",
        "LoadPackage",
        "ResolveName",
    ),
    "ue": (
        "FNamePool",
        "NamePoolData",
        "GName",
        "GNames",
        "GUObjectArray",
        "GObjectArray",
        "GObjects",
        "FUObjectArray",
        "GWorld",
        "GEngine",
        "ProcessEvent",
        "StaticFindObject",
        "CallFunctionByNameWithArguments",
        "CallFunctionByName",
        "UObject",
        "UFunction",
        "UClass",
        "FProperty",
        "UStruct",
        "UEnum",
    ),
    "client": (
        "LocalPlayer",
        "PlayerController",
        "GameViewport",
        "ViewportClient",
        "ConsoleKey",
        "InputSettings",
        "ClientTravel",
        "ClientRestart",
    ),
    "cheat": (
        "CheatManager",
        "CheatClass",
        "EnableCheats",
        "AdminLogin",
        "ServerCheat",
        "ClientMessage",
    ),
    "brt": (
        "BaseBackup",
        "PerformCanBePlaced",
        "Fail_InvalidMap",
        "m_BaseBackupToolMapRestriction",
    ),
    "deep-desert": (
        "DeepDesert",
        "ShiftingSands",
        "SpiceField",
        "PerMapSystem",
    ),
    "platform": (
        "DuneSandbox",
        "EngineVersion",
        "rundll32.exe",
        "elf",
        "mz",
    ),
}

DEFAULT_EXPECTED = (
    "FNamePool",
    "NamePoolData",
    "GName",
    "GNames",
    "GUObjectArray",
    "GObjectArray",
    "GObjects",
    "FUObjectArray",
    "GWorld",
    "GEngine",
    "ProcessEvent",
    "CheatManager",
    "ServerRequestBaseBackup",
    "BaseBackupActionPlace",
    "DeepDesert",
)


def ue4ss_script_path_from_runtime_function_path(path):
    if not path or not path.startswith("/RuntimeProbe/") or not path.endswith(":Function"):
        return ""
    body = path[len("/RuntimeProbe/") : -len(":Function")]
    if "." not in body:
        return ""
    owner, function = body.rsplit(".", 1)
    owner = owner.rsplit("/", 1)[-1]
    if not owner or not function:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    owner = "".join(ch if ch in allowed else "_" for ch in owner)
    function = "".join(ch if ch in allowed else "_" for ch in function)
    if not owner or not function:
        return ""
    return f"/Script/{owner}.{function}:Function"


def is_ue4ss_script_function_path(path):
    return bool(path and path.startswith("/Script/") and path.endswith(":Function") and "." in path)


def parse_line(line):
    line = line.strip().replace("\r", "")
    if not line:
        return None
    parts = line.split()
    if not parts:
        return None
    record = {"timestamp": parts[0]}
    for token in parts[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        record[key] = value
    return record


def load_records(path):
    records = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            record = parse_line(line)
            if record:
                records.append(record)
    return records


def category_for(name):
    for category, needles in CATEGORY_NEEDLES.items():
        if any(needle in name for needle in needles):
            return category
    return "other"


def record_source(record):
    return record.get("map") or record.get("module") or record.get("name") or ""


def record_offset(record):
    return (
        record.get("imageOffset")
        or record.get("rva")
        or record.get("fileOffset")
        or record.get("addr")
        or ""
    )


def record_int(record, key, default=0):
    try:
        return int(str(record.get(key, default)), 0)
    except (TypeError, ValueError):
        return default


def record_bool(record, key):
    return str(record.get(key, "")).lower() in {"1", "true", "yes", "on"}


def record_float(record, key, default=0.0):
    try:
        return float(str(record.get(key, default)))
    except (TypeError, ValueError):
        return default


def runtime_discovery_summary(records, mapped_ue_anchors):
    starts = [record for record in records if record.get("event") == "ue-runtime-discovery-start"]
    finishes = [record for record in records if record.get("event") == "ue-runtime-discovery-finish"]
    candidates = [
        record for record in records if record.get("event") == "ue-runtime-discovery-candidate"
    ]
    candidate_name_counts = dict(Counter(record.get("name", "") for record in candidates))
    candidate_locations = []
    for record in candidates:
        location = {
            "name": record.get("name", ""),
            "addr": record.get("addr", ""),
            "imageOffset": record.get("imageOffset") or record.get("rva", ""),
            "fileOffset": record.get("fileOffset", ""),
            "map": record.get("map") or record.get("module", ""),
            "perms": record.get("perms", ""),
            "targetImage": record.get("targetImage", ""),
        }
        if any(location.values()):
            candidate_locations.append(location)
    candidate_image_counts = dict(Counter(item["map"] for item in candidate_locations if item.get("map")))
    outcomes = [
        record
        for record in records
        if record.get("event") == "ue-runtime-discovery"
        and record.get("name") not in {"target-writable-image-mappings", "target-writable-image-regions"}
    ]
    validations = [
        record
        for record in records
        if record.get("event") == "ue-runtime-root-validation"
        and record.get("status") == "validated"
    ]
    validation_names = sorted(
        {
            record.get("name", "")
            for record in validations
            if record.get("name", "").startswith("Runtime")
        }
    )
    target_writable_missing = [
        record
        for record in records
        if record.get("event") == "ue-runtime-discovery"
        and record.get("name") in {"target-writable-image-mappings", "target-writable-image-regions"}
        and record.get("status") == "missing"
    ]
    promoted_names = sorted(
        {
            record.get("name", "")
            for record in mapped_ue_anchors
            if record.get("name", "").startswith("Runtime")
        }
    )
    target_writable_count = sum(
        record_int(record, "targetWritableMappings") + record_int(record, "targetWritableRegions")
        for record in finishes
    )
    coverage = {
        "targetWritableImageCount": target_writable_count,
        "anonymousWritableMappingCount": sum(
            record_int(record, "anonymousWritableMappings")
            for record in finishes
        ),
        "oversizedImageCount": sum(
            record_int(record, "oversizedMappings") + record_int(record, "oversizedRegions")
            for record in finishes
        ),
        "scannedSlots": sum(record_int(record, "scannedSlots") for record in finishes),
        "fnameProbes": sum(record_int(record, "fnameProbes") for record in finishes),
        "objectArrayProbes": sum(record_int(record, "objectArrayProbes") for record in finishes),
        "fnameHits": sum(record_int(record, "fnameHits") for record in finishes),
        "objectArrayHits": sum(record_int(record, "objectArrayHits") for record in finishes),
    }
    if not starts and not finishes:
        failure = "not-run"
    elif target_writable_missing or target_writable_count == 0:
        failure = "no-target-writable-image"
    elif coverage["scannedSlots"] == 0:
        failure = "no-slots-scanned"
    elif coverage["fnameProbes"] == 0 or coverage["objectArrayProbes"] == 0:
        failure = "probe-not-run"
    elif coverage["fnameHits"] == 0 or coverage["objectArrayHits"] == 0:
        failure = "no-root-hits"
    elif any(record.get("status") == "ambiguous" for record in outcomes):
        failure = "ambiguous-root-hits"
    elif {"RuntimeFNamePool", "RuntimeGUObjectArray"}.issubset(set(promoted_names)):
        failure = ""
    else:
        failure = "incomplete-promotion"
    return {
        "startCount": len(starts),
        "finishCount": len(finishes),
        "candidateCount": len(candidates),
        "candidateNameCounts": candidate_name_counts,
        "candidateLocations": candidate_locations[:32],
        "candidateImageCounts": candidate_image_counts,
        "outcomeCount": len(outcomes),
        "targetWritableMissingCount": len(target_writable_missing),
        "statusCounts": dict(Counter(record.get("status", "") for record in outcomes)),
        "promotedNames": promoted_names,
        "consumerValidatedNames": validation_names,
        "consumerValidationCount": len(validations),
        "consumerValidationByName": dict(Counter(record.get("name", "") for record in validations)),
        "consumerValidationByConsumer": dict(Counter(record.get("consumer", "") for record in validations)),
        "coverage": coverage,
        "failure": failure,
        "ready": failure == "",
    }


def lua_object_api_surface_passed(record):
    return (
        record_int(record, "findObjectCalls") > 0
        and record_int(record, "findObjectHits") > 0
        and record_int(record, "getKnownObjectsCalls") > 0
        and record_int(record, "getKnownObjectsHits") > 0
        and record_int(record, "findObjectsCalls") > 0
        and record_int(record, "findObjectsHits") > 0
        and record_int(record, "findAllOfCalls") > 0
        and record_int(record, "findAllOfHits") > 0
        and record_int(record, "forEachUObjectCalls") > 0
        and record_int(record, "forEachUObjectCallbacks") > 0
        and record_int(record, "isACalls") >= 2
        and record_int(record, "isAHits") >= 2
        and record_int(record, "loadAssetCalls") > 0
        and record_int(record, "loadAssetHits") > 0
    )


def lua_load_asset_package_surface_passed(record):
    return (
        record_int(record, "loadAssetPackageCalls") > 0
        and record_int(record, "loadAssetPackageHits") > 0
    ) or (
        record_int(record, "loadAssetCalls") > 0
        and record_int(record, "loadAssetHits") > 0
        and record.get("loadAssetBackend") == "package"
    )


def lua_load_asset_backend_state_surface_passed(record):
    return (
        record_int(record, "loadAssetBackendStateCalls") > 0
        and record.get("loadAssetBackend") in {"registry", "package"}
        and record.get("loadAssetPackageArmed") in {"false", "true"}
    )


def lua_load_asset_backend_anchor_surface_passed(record):
    return lua_load_asset_backend_state_surface_passed(record) and (
        record_bool(record, "loadAssetPackageAvailable")
        or record_bool(record, "loadAssetStaticLoadObjectResolved")
        or record_bool(record, "loadAssetLoadObjectResolved")
        or record_bool(record, "loadAssetLoadPackageResolved")
        or record_bool(record, "loadAssetResolveNameResolved")
    )


def lua_load_asset_package_bridge_state_surface_passed(record):
    return (
        lua_load_asset_backend_state_surface_passed(record)
        and record_int(record, "loadAssetPackageBridgeStateCalls") > 0
        and record.get("loadAssetPackageArmed") in {"false", "true"}
    )


def lua_load_asset_package_native_invoke_surface_passed(record):
    return (
        record_int(record, "loadAssetPackageNativeCalls") > 0
        and record_int(record, "loadAssetPackageNativeGateHits") > 0
    )


def package_target_image_evidence_consistent(record):
    target_image = record.get("targetImage")
    if target_image not in {"false", "true"}:
        return False
    if record.get("status") == "target-not-target-image" and target_image != "false":
        return False
    if record.get("abiVerified") == "true" and target_image != "true":
        return False
    if record.get("tcharLayoutVerified") == "true" and target_image != "true":
        return False
    if record.get("callFrameReady") == "true" and target_image != "true":
        return False
    return True


def lua_load_asset_package_abi_state_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-abi-state"
        and package_target_image_evidence_consistent(record)
        and record.get("abiVerified") == "false"
        and record.get("callFrameReady") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_call_frame_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-call-frame-state"
        and record.get("pathStaged") == "true"
        and record.get("argumentDescriptorReady") == "true"
        and record.get("callFrameReady") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_call_frame_verification_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-call-frame-verification-state"
        and package_target_image_evidence_consistent(record)
        and record.get("pathStaged") == "true"
        and record.get("boundedInput") == "true"
        and record.get("abiEvidenceProvided") in {"false", "true"}
        and record.get("abiVerificationEnabled") in {"false", "true"}
        and record.get("abiVerified") in {"false", "true"}
        and record.get("tcharLayoutVerified") in {"false", "true"}
        and record.get("callFrameReady") in {"false", "true"}
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_crash_guard_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-crash-guard-state"
        and record.get("available") == "true"
        and record.get("enabled") in {"false", "true"}
        and record.get("armed") in {"false", "true"}
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_guarded_call_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-guarded-call-state"
        and record.get("guardedCallAvailable") == "true"
        and record.get("guardedCallExecuted") == "true"
        and record.get("guardedCallSucceeded") == "true"
        and record.get("guardedCallResult") is not None
        and record.get("crashCaptured") in {"false", "true"}
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_return_validation_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-return-validation-state"
        and record.get("registryHit") == "true"
        and record.get("mapped") == "true"
        and record.get("readable") == "true"
        and record.get("classMatch") == "true"
        and record.get("returnValidationReady") == "true"
        and record.get("nativeInvoked") == "false"
    )


def lua_load_asset_package_native_call_adapter_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-native-call-adapter-state"
        and record.get("pathStaged") == "true"
        and record.get("boundedInput") == "true"
        and record.get("functionPointerReady") in {"false", "true"}
        and record.get("abiVerified") in {"false", "true"}
        and record.get("tcharLayoutVerified") in {"false", "true"}
        and record.get("callFrameReady") in {"false", "true"}
        and record.get("nativeBridgeArmed") in {"false", "true"}
        and record.get("adapterReady") in {"false", "true"}
        and record.get("finalInvokeConfirmed") in {"false", "true"}
        and record.get("crashGuardRequired") in {"false", "true"}
        and record.get("crashGuardArmed") in {"false", "true"}
        and record.get("guardedCallRequired") in {"false", "true"}
        and record.get("guardedCallReady") in {"false", "true"}
        and record.get("guardedCallResult") is not None
        and record.get("returnValidationReady") in {"false", "true"}
        and record.get("nativeCallable") in {"false", "true"}
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_invocation_descriptor_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-invocation-descriptor-state"
        and record.get("descriptorKind") == "guarded-package-native-call"
        and record.get("descriptorProvenance") == "adapter-state-derived"
        and record.get("nativeCallPlanConstructed") == "true"
        and record.get("nativeCallExecutionMode") == "guarded-native-package-load"
        and record.get("nativeCallTargetField") == "TargetAddress"
        and record.get("nativeCallPathField") == "Path"
        and record.get("nativeCallGuardPolicy") == "crash-guard+guarded-call+return-validation"
        and record.get("nativeCallReturnValidator") == "uobject-registry-memory-class"
        and record.get("nativeInvoked") == "false"
    )


def lua_load_asset_package_native_executor_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-native-executor-state"
        and record.get("executorKind") == "guarded-package-native-executor"
        and record.get("nativeExecutorConstructed") == "true"
        and record.get("nativeExecutorDryRun") == "true"
        and record.get("nativeExecutorReady") in {"false", "true"}
        and record.get("executorPreflightPassed") in {"false", "true"}
        and record.get("finalNativeCallEligible") in {"false", "true"}
        and record.get("nativeExecutorBlockReason") is not None
        and record.get("finalNativeCallBlocked") == "true"
        and record.get("finalNativeCallBlockReason") == "preflight-state-only"
        and record.get("nativeInvoked") == "false"
    )


def lua_load_asset_package_native_executor_ready_event(record):
    return (
        lua_load_asset_package_native_executor_event_passed(record)
        and record.get("nativeExecutorReady") == "true"
        and record.get("executorPreflightPassed") == "true"
        and record.get("finalNativeCallEligible") == "true"
    )


def lua_load_asset_package_native_executor_target_ready_event(record):
    return (
        lua_load_asset_package_native_executor_ready_event(record)
        and record.get("targetName") in {"StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"}
        and record_int(record, "target") > 0
        and record.get("targetImage") == "true"
        and record.get("signatureFamily") in {"StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"}
    )


def lua_load_asset_package_string_bridge_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-string-bridge-state"
        and record.get("stringInputStaged") == "true"
        and record.get("boundedInput") == "true"
        and record.get("inputEncoding") == "utf-8"
        and record.get("tcharEncoding") == "unverified-live-build"
        and record.get("tcharBridgeReady") == "false"
        and record.get("nativeBufferReady") == "false"
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_native_buffer_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-native-buffer-state"
        and record.get("stringInputStaged") == "true"
        and record.get("boundedInput") == "true"
        and record.get("utf8BufferReady") == "true"
        and record.get("nativeInputBufferReady") == "true"
        and record_int(record, "bufferBytes") > 0
        and record.get("nullTerminated") == "true"
        and record.get("tcharEncoding") == "unverified-live-build"
        and record.get("tcharBufferReady") == "false"
        and record.get("callFrameReady") == "false"
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_tchar_buffer_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-tchar-buffer-state"
        and record.get("stringInputStaged") == "true"
        and record.get("boundedInput") == "true"
        and record.get("candidateEncoding") in {"host-wchar-unverified", "windows-wchar-unverified"}
        and record_int(record, "candidateUnitBytes") > 0
        and record_int(record, "candidateBufferBytes") > 0
        and record.get("tcharLayoutVerified") == "false"
        and record.get("tcharBufferReady") == "false"
        and record.get("callFrameReady") == "false"
        and record.get("nativeInvoked") == "false"
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_tchar_verification_event_passed(record):
    return (
        record.get("event") == "lua-load-asset-package-tchar-verification-state"
        and package_target_image_evidence_consistent(record)
        and record.get("candidateEncoding") in {"host-wchar-unverified", "windows-wchar-unverified"}
        and record_int(record, "candidateUnitBytes") > 0
        and record.get("evidenceProvided") in {"false", "true"}
        and record.get("verificationEnabled") in {"false", "true"}
        and record.get("unitMatch") in {"false", "true"}
        and record.get("tcharLayoutVerified") in {"false", "true"}
        and record.get("tcharBufferReady") in {"false", "true"}
        and record.get("platformAbi") in {"sysv-x86_64", "win64-ms-abi"}
    )


def lua_load_asset_package_preflight_surface_passed(record):
    return (
        record_int(record, "loadAssetPackagePreflightCalls") > 0
        and record_int(record, "loadAssetPackageGateHits") > 0
    )


def lua_scheduler_api_surface_passed(record):
    return (
        record_int(record, "executeInGameThreadCalls") == 1
        and record_int(record, "executeInGameThreadCallbacks") == 1
        and record.get("executeInGameThreadResult") == "9"
        and record.get("executeInGameThreadIsNumber") == "true"
        and record_int(record, "executeAsyncCalls") == 1
        and record_int(record, "executeAsyncCallbacks") == 1
        and record_int(record, "executeWithDelayCalls") == 2
        and record_int(record, "executeWithDelayCallbacks") == 1
        and record_int(record, "loopAsyncCalls") == 1
        and record_int(record, "loopAsyncCallbacks") == 1
        and record_int(record, "schedulerQueueDrains") == 1
        and record_int(record, "schedulerCancelCalls") == 1
        and record_int(record, "schedulerCancelHits") == 1
    )


def lua_scheduler_api_mod_surface_passed(record):
    return lua_scheduler_api_surface_passed(record)


def lua_input_command_api_surface_passed(record):
    return (
        record_int(record, "keyBindRegistrations") == 1
        and record_int(record, "keyBindLookupCalls") == 2
        and record_int(record, "keyBindLookupHits") == 1
        and record_int(record, "keyBindDispatchCalls") == 2
        and record_int(record, "keyBindCallbackCalls") == 1
        and record_int(record, "keyBindCallbackHandled") == 1
        and record_int(record, "keyBindUnregisterCalls") == 1
        and record_int(record, "keyBindUnregisterHits") == 1
        and record_int(record, "consoleCommandHandlers") == 2
        and record_int(record, "consoleCommandGlobalHandlers") == 1
        and record_int(record, "consoleCommandHandlerCalls") == 1
        and record_int(record, "consoleCommandHandlerHandled") == 0
        and record_int(record, "consoleCommandGlobalHandlerCalls") == 1
        and record_int(record, "consoleCommandGlobalHandlerHandled") == 1
        and record_int(record, "consoleCommandUnregisterCalls") == 1
        and record_int(record, "consoleCommandUnregisterHits") == 1
    )


def lua_input_command_api_mod_surface_passed(record):
    return (
        record_int(record, "keyBindLookupCalls") >= 2
        and record_int(record, "keyBindLookupHits") >= 1
        and record_int(record, "keyBindDispatchCalls") > 0
        and record_int(record, "keyBindCallbackCalls") > 0
        and record_int(record, "keyBindCallbackHandled") > 0
        and record_int(record, "keyBindUnregisterCalls") >= 2
        and record_int(record, "keyBindUnregisterHits") >= 2
        and record_int(record, "consoleCommandHandlers") >= 3
        and record_int(record, "consoleCommandGlobalHandlers") > 0
        and record_int(record, "consoleCommandHandlerCalls") > 0
        and record_int(record, "consoleCommandHandlerHandled") > 0
        and record_int(record, "consoleCommandGlobalHandlerCalls") > 0
        and record_int(record, "consoleCommandUnregisterCalls") > 0
        and record_int(record, "consoleCommandUnregisterHits") > 0
    )


def lua_function_iteration_surface_passed(record):
    return (
        record_int(record, "forEachFunctionCalls") > 0
        and record_int(record, "forEachFunctionCallbacks") > 0
    )


def lua_notify_on_new_object_surface_passed(record):
    return (
        record_int(record, "notifyOnNewObjectCalls") >= 2
        and record_int(record, "notifyOnNewObjectCallbacks") >= 2
        and record_int(record, "notifyOnNewObjectStatus", -1) == 0
    )


def lua_synthetic_outer_surface_passed(record):
    return record_int(record, "staticConstructObjectOuterHits") > 0


def lua_world_context_surface_passed(record):
    return record_int(record, "getWorldCalls") > 0 and record_int(record, "getWorldHits") > 0


def lua_global_runtime_helper_surface_passed(record):
    return (
        record.get("status") == "passed"
        and record.get("globalWorld") == "true"
        and record_int(record, "getWorldCalls") > 0
        and record_int(record, "getWorldHits") > 0
        and record.get("globalEngine") == "true"
        and record.get("globalEngineClass") == "UEngine"
    )


def lua_class_default_object_surface_passed(record):
    return record_int(record, "getCdoCalls") > 0 and record_int(record, "getCdoHits") > 0


def lua_level_surface_passed(record):
    return record_int(record, "getLevelCalls") > 0 and record_int(record, "getLevelHits") > 0


def lua_process_console_exec_hook_surface_passed(record):
    return (
        record_int(record, "processConsoleExecPreHooks") > 0
        and record_int(record, "processConsoleExecPostHooks") > 0
        and record_int(record, "processConsoleExecPreCalls") > 0
        and record_int(record, "processConsoleExecPostCalls") > 0
        and record_int(record, "processConsoleExecPreHandled") > 0
        and record_int(record, "processConsoleExecPostHandled") > 0
    )


def lua_local_player_exec_hook_surface_passed(record):
    return (
        record_int(record, "localPlayerExecPreHooks") > 0
        and record_int(record, "localPlayerExecPostHooks") > 0
        and record_int(record, "localPlayerExecPreCalls") > 0
        and record_int(record, "localPlayerExecPostCalls") > 0
        and record_int(record, "localPlayerExecPreHandled") > 0
        and record_int(record, "localPlayerExecPostHandled") > 0
    )


def lua_call_function_hook_surface_passed(record):
    return (
        record_int(record, "callFunctionPreHooks") > 0
        and record_int(record, "callFunctionPostHooks") > 0
        and record_int(record, "callFunctionPreCalls") > 0
        and record_int(record, "callFunctionPostCalls") > 0
        and record_int(record, "callFunctionPreHandled") > 0
        and record_int(record, "callFunctionPostHandled") > 0
    )


def lua_call_function_structured_args_surface_passed(record):
    return (
        lua_call_function_hook_surface_passed(record)
        and record_int(record, "callFunctionTableArgCalls") > 0
        and record_int(record, "callFunctionArgFieldHits") >= 10
        and record_int(record, "callFunctionArgStructHits") > 0
    )


def lua_process_event_compat_surface_passed(record):
    return (
        record_int(record, "processEventCompatCalls") >= 2
        and record_int(record, "processEventCompatHits") >= 2
    )


def lua_process_event_bridge_state_surface_passed(record):
    return record_int(record, "processEventBridgeStateCalls") > 0


def lua_process_event_native_invoke_surface_passed(record):
    return (
        record_int(record, "processEventNativeCalls") > 0
        and record_int(record, "processEventNativeHits") > 0
    )


def lua_process_event_native_invoke_non_self_test_gate_passed(record):
    if record.get("event") != "lua-process-event-native-invoke":
        return False
    if record.get("status") != "non-self-test-invoke-disabled":
        return False
    if record.get("liveCallsBefore") is None or record.get("liveCallsAfter") is None:
        return False
    if record.get("originalCallsBefore") is None or record.get("originalCallsAfter") is None:
        return False
    return (
        record_bool(record, "objectRegistryAllowed")
        and record_bool(record, "functionDescriptorAllowed")
        and not record_bool(record, "selfTestCallable")
        and record_bool(record, "descriptorBackedCallable")
        and record_bool(record, "invokeRequested")
        and not record_bool(record, "nativeNonSelfTestEnabled")
        and not record_bool(record, "nativeNonSelfTestInvoked")
        and record_bool(record, "paramsBufferConstructible")
        and record_int(record, "paramsDescriptorCount") > 0
        and record_int(record, "paramsBufferSize") > 0
        and record_int(record, "paramsWritten") == 0
        and record_int(record, "liveCallsBefore") == record_int(record, "liveCallsAfter")
        and record_int(record, "originalCallsBefore") == record_int(record, "originalCallsAfter")
    )


def lua_process_event_native_invoke_descriptor_preflight_ready(record):
    if record.get("event") != "lua-process-event-native-invoke":
        return False
    if record.get("status") != "descriptor-preflight-ready":
        return False
    if record.get("liveCallsBefore") is None or record.get("liveCallsAfter") is None:
        return False
    if record.get("originalCallsBefore") is None or record.get("originalCallsAfter") is None:
        return False
    return (
        record_bool(record, "objectRegistryAllowed")
        and record_bool(record, "functionDescriptorAllowed")
        and not record_bool(record, "selfTestCallable")
        and record_bool(record, "descriptorBackedCallable")
        and not record_bool(record, "invokeRequested")
        and not record_bool(record, "nativeNonSelfTestInvoked")
        and record_bool(record, "paramsBufferConstructible")
        and record_int(record, "paramsDescriptorCount") > 0
        and record_int(record, "paramsBufferSize") > 0
        and record_int(record, "paramsWritten") == 0
        and record_int(record, "liveCallsBefore") == record_int(record, "liveCallsAfter")
        and record_int(record, "originalCallsBefore") == record_int(record, "originalCallsAfter")
    )


def lua_process_event_native_invoke_non_self_test_invoked(record):
    return (
        record.get("event") == "lua-process-event-native-invoke"
        and record.get("status") == "non-self-test-invoked"
        and record_bool(record, "nativeNonSelfTestInvoked")
    )


def lua_lifecycle_hook_surface_passed(record):
    return (
        record_int(record, "customEvents") > 0
        and record_int(record, "customEventCalls") > 0
        and record_int(record, "customEventHandled") > 0
        and record_int(record, "loadMapPreHooks") > 0
        and record_int(record, "loadMapPostHooks") > 0
        and record_int(record, "loadMapPreCalls") > 0
        and record_int(record, "loadMapPostCalls") > 0
        and record_int(record, "loadMapPreHandled") > 0
        and record_int(record, "loadMapPostHandled") > 0
        and record_int(record, "beginPlayPreHooks") > 0
        and record_int(record, "beginPlayPostHooks") > 0
        and record_int(record, "beginPlayPreCalls") > 0
        and record_int(record, "beginPlayPostCalls") > 0
        and record_int(record, "beginPlayPreHandled") > 0
        and record_int(record, "beginPlayPostHandled") > 0
        and record_int(record, "initGameStatePreHooks") > 0
        and record_int(record, "initGameStatePostHooks") > 0
        and record_int(record, "initGameStatePreCalls") > 0
        and record_int(record, "initGameStatePostCalls") > 0
        and record_int(record, "initGameStatePreHandled") > 0
        and record_int(record, "initGameStatePostHandled") > 0
    )


def lua_custom_event_surface_passed(record):
    return (
        record_int(record, "customEvents") > 0
        and record_int(record, "customEventCalls") > 0
        and record_int(record, "customEventHandled") > 0
    )


def lua_load_map_hook_surface_passed(record):
    return (
        record_int(record, "loadMapPreHooks") > 0
        and record_int(record, "loadMapPostHooks") > 0
        and record_int(record, "loadMapPreCalls") > 0
        and record_int(record, "loadMapPostCalls") > 0
        and record_int(record, "loadMapPreHandled") > 0
        and record_int(record, "loadMapPostHandled") > 0
    )


def lua_begin_play_hook_surface_passed(record):
    return (
        record_int(record, "beginPlayPreHooks") > 0
        and record_int(record, "beginPlayPostHooks") > 0
        and record_int(record, "beginPlayPreCalls") > 0
        and record_int(record, "beginPlayPostCalls") > 0
        and record_int(record, "beginPlayPreHandled") > 0
        and record_int(record, "beginPlayPostHandled") > 0
    )


def lua_init_game_state_hook_surface_passed(record):
    return (
        record_int(record, "initGameStatePreHooks") > 0
        and record_int(record, "initGameStatePostHooks") > 0
        and record_int(record, "initGameStatePreCalls") > 0
        and record_int(record, "initGameStatePostCalls") > 0
        and record_int(record, "initGameStatePreHandled") > 0
        and record_int(record, "initGameStatePostHandled") > 0
    )


def lua_reflection_self_test_passed(record):
    if record.get("status") != "passed":
        return False
    raw_hits = record_int(record, "rawPropertyHits")
    raw_value = record_int(record, "rawPropertyValue")
    raw_set_hits = record_int(record, "rawPropertySetHits")
    raw_set_value = record_int(record, "rawPropertySetValue")
    return (
        record.get("result") == "42"
        and record_int(record, "staticFindObjectHits") >= 1
        and record_int(record, "getPropertyCalls") >= 17
        and record_int(record, "getPropertyHits") >= 17
        and record_int(record, "setPropertyCalls") >= 8
        and record_int(record, "setPropertyHits") >= 8
        and record.get("callFunctionCalls") == "2"
        and record.get("callFunctionHits") == "2"
        and record.get("probeValue") == "21"
        and record.get("probeBool") == "false"
        and abs(record_float(record, "probeFloat") - 13.75) < 0.001
        and abs(record_float(record, "probeDouble") + 47.5) < 0.001
        and record.get("probeName") == "ArrakisName"
        and record.get("probeString") == "melange"
        and record.get("probeText") == "WaterDebt"
        and str(record.get("probeObject", "")).startswith("0x")
        and (raw_hits == 0 or raw_value in (7, 13, 17))
        and (raw_set_hits == 0 or (raw_set_hits == 1 and raw_set_value == 17 and raw_value == 17))
    )


def lua_reflection_array_inner_property_passed(record):
    return lua_reflection_self_test_passed(record) and record_int(record, "arrayInnerPropertyHits") > 0


def lua_reflection_enum_property_passed(record):
    return (
        lua_reflection_self_test_passed(record)
        and record_int(record, "enumPropertyHits") > 0
        and record_int(record, "enumUnderlyingPropertyHits") > 0
    )


def lua_reflection_container_property_passed(record):
    return (
        lua_reflection_self_test_passed(record)
        and record_int(record, "setElementPropertyHits") > 0
        and record_int(record, "mapKeyPropertyHits") > 0
        and record_int(record, "mapValuePropertyHits") > 0
    )


def lua_reflection_import_text_passed(record):
    return lua_reflection_self_test_passed(record) and record_int(record, "importTextHits") > 0


def lua_reflection_export_text_passed(record):
    return lua_reflection_self_test_passed(record) and record_int(record, "exportTextHits") > 0


def lua_reflection_property_metadata_passed(record):
    return lua_reflection_self_test_passed(record) and record_int(record, "propertyMetadataHits") > 0


def lua_reflection_descriptor_values_passed(record):
    return (
        lua_reflection_self_test_passed(record)
        and record_int(record, "descriptorValueGetHits") > 0
        and record_int(record, "descriptorValueSetHits") > 0
        and record_int(record, "descriptorValueAliasHits") > 0
    )


def lua_reflection_for_each_property_passed(record):
    return lua_reflection_self_test_passed(record) and record_int(record, "reflectionForEachPropertyHits") > 0


def lua_reflection_live_descriptor_values_passed(record):
    return (
        lua_reflection_self_test_passed(record)
        and record_int(record, "liveDescriptorValueGetHits") > 0
        and record_int(record, "liveDescriptorValueSetHits") > 0
    )


def non_self_test_hook_record(record):
    return record.get("selfTestTarget") != "true"


def hook_target_address(record):
    return record_int(record, "target")


def hook_target_has_explicit_provenance(record):
    def meaningful(value):
        return bool(value) and str(value).lower() not in {"-", "unknown", "none", "null"}

    return any(
        meaningful(record.get(key))
        for key in (
            "targetSource",
            "targetName",
            "targetPath",
            "targetResolvedName",
            "targetRuntimePath",
            "targetModule",
        )
    )


def hook_target_matches_anchor(record, anchors, name_predicate):
    target = hook_target_address(record)
    if not target:
        return False
    for anchor in anchors:
        if not name_predicate(anchor.get("name", "")):
            continue
        anchor_addr = record_int(anchor, "addr")
        if anchor_addr and anchor_addr == target:
            return True
    return False


def process_event_anchor_name_matches(name):
    return name == "ProcessEvent" or "ProcessEvent" in (name or "")


def call_function_anchor_name_matches(name):
    return (
        name == "CallFunctionByNameWithArguments"
        or "CallFunctionByNameWithArguments" in (name or "")
        or "CallFunctionByName" in (name or "")
    )


def proven_process_event_hook_target_record(record, anchors):
    return non_self_test_hook_record(record) and (
        hook_target_has_explicit_provenance(record)
        or hook_target_matches_anchor(record, anchors, process_event_anchor_name_matches)
    )


def proven_call_function_hook_target_record(record, anchors):
    return non_self_test_hook_record(record) and (
        hook_target_has_explicit_provenance(record)
        or hook_target_matches_anchor(record, anchors, call_function_anchor_name_matches)
    )


def runtime_process_event_context_record(record):
    provenance = record.get("functionProvenance", "")
    if provenance == "runtime":
        return True
    if provenance == "self-test":
        return False
    for path in (record.get("functionPath", ""), record.get("functionRuntimePath", "")):
        if "SelfTest" in path or ".LiveProcessEvent" in path:
            return False
    return True


def self_test_registry_record(record):
    provenance = record.get("registryProvenance", "")
    if provenance == "self-test":
        return True
    if provenance == "runtime":
        return False
    values = (
        record.get("name", ""),
        record.get("path", ""),
        record.get("runtimePath", ""),
        record.get("class", ""),
        record.get("className", ""),
        record.get("functionName", ""),
        record.get("functionPath", ""),
        record.get("functionRuntimePath", ""),
    )
    return any("SelfTest" in value or ".LiveProcessEvent" in value for value in values)


def runtime_registry_record(record):
    return not self_test_registry_record(record)


def runtime_iteration_record(record):
    provenance = record.get("registryProvenance", "")
    if provenance == "runtime":
        return True
    if provenance == "self-test":
        return False
    return record.get("mode") not in ("", "self-test")


def self_test_iteration_record(record):
    provenance = record.get("registryProvenance", "")
    if provenance == "self-test":
        return True
    if provenance == "runtime":
        return False
    return record.get("mode") == "self-test"


def self_test_reflection_record(record):
    provenance = record.get("descriptorProvenance", "")
    if provenance == "self-test":
        return True
    if provenance == "runtime":
        return False
    values = (
        record.get("name", ""),
        record.get("fieldName", ""),
        record.get("chain", ""),
        record.get("className", ""),
    )
    return any("SelfTest" in value for value in values)


def runtime_reflection_record(record):
    return record.get("descriptorProvenance") == "runtime"


def lua_reflection_numeric_property_values_passed(record):
    return (
        lua_reflection_self_test_passed(record)
        and record_int(record, "getPropertyHits") >= 17
        and record_int(record, "setPropertyHits") >= 8
        and abs(record_float(record, "probeFloat") - 13.75) < 0.001
        and abs(record_float(record, "probeDouble") + 47.5) < 0.001
    )


def lua_reflection_name_text_property_values_passed(record):
    return (
        lua_reflection_self_test_passed(record)
        and record_int(record, "getPropertyHits") >= 17
        and record_int(record, "setPropertyHits") >= 8
        and record.get("probeName") == "ArrakisName"
        and record.get("probeText") == "WaterDebt"
    )


def process_event_accessor_value(record, suffix, prefix=""):
    key = f"{prefix}{suffix}" if prefix else suffix[:1].lower() + suffix[1:]
    return record_int(record, key)


def process_event_param_accessors_passed(record, prefix=""):
    return (
        process_event_accessor_value(record, "ParamDescriptorHits", prefix) > 0
        and process_event_accessor_value(record, "ParamDescriptorLookupHits", prefix) > 0
        and process_event_accessor_value(record, "FunctionParamDescriptorCalls", prefix) > 0
        and process_event_accessor_value(record, "FunctionParamDescriptorHits", prefix) > 0
        and process_event_accessor_value(record, "ParamGetHits", prefix) > 0
        and process_event_accessor_value(record, "ParamSetHits", prefix) > 0
    )


def process_event_function_param_methods_passed(record, prefix=""):
    return process_event_accessor_value(record, "FunctionParamMethodHits", prefix) > 0


def process_event_function_param_lookup_methods_passed(record, prefix=""):
    return process_event_accessor_value(record, "FunctionParamLookupMethodHits", prefix) > 0


def process_event_function_param_iteration_methods_passed(record, prefix=""):
    return process_event_accessor_value(record, "FunctionParamIterationMethodHits", prefix) > 0


def process_event_container_alias_methods_passed(record, prefix=""):
    return process_event_accessor_value(record, "ContainerAliasHits", prefix) > 0


def process_event_container_storage_layout_methods_passed(record, prefix=""):
    return process_event_accessor_value(record, "ContainerStorageLayoutHits", prefix) >= 3


def process_event_scalar_param_accessors_passed(record, prefix=""):
    return (
        process_event_accessor_value(record, "ParamDescriptorHits", prefix) >= 2
        and process_event_accessor_value(record, "ParamDescriptorLookupHits", prefix) >= 12
        and process_event_accessor_value(record, "FunctionParamDescriptorHits", prefix) >= 2
        and process_event_accessor_value(record, "ParamGetHits", prefix) >= 16
        and process_event_accessor_value(record, "ParamSetHits", prefix) >= 4
    )


def process_event_name_string_param_accessors_passed(record, prefix=""):
    return (
        process_event_accessor_value(record, "ParamDescriptorHits", prefix) >= 2
        and process_event_accessor_value(record, "ParamDescriptorLookupHits", prefix) >= 12
        and process_event_accessor_value(record, "FunctionParamDescriptorHits", prefix) >= 2
        and process_event_accessor_value(record, "ParamGetHits", prefix) >= 18
        and process_event_accessor_value(record, "ParamSetHits", prefix) >= 6
    )


def process_event_struct_param_accessors_passed(record, prefix=""):
    return (
        process_event_accessor_value(record, "ParamDescriptorHits", prefix) >= 2
        and process_event_accessor_value(record, "ParamDescriptorLookupHits", prefix) >= 13
        and process_event_accessor_value(record, "FunctionParamDescriptorHits", prefix) >= 2
        and process_event_accessor_value(record, "ParamGetHits", prefix) >= 21
        and process_event_accessor_value(record, "ParamSetHits", prefix) >= 7
    )


def process_event_enum_param_accessors_passed(record, prefix=""):
    key = f"{prefix}EnumParamAccessors" if prefix else "enumParamAccessors"
    return record.get(key) == "true"


def process_event_object_param_accessors_passed(record, prefix=""):
    key = f"{prefix}ObjectParamAccessors" if prefix else "objectParamAccessors"
    return record.get(key) == "true"


def process_event_bool_param_accessors_passed(record, prefix=""):
    key = f"{prefix}BoolParamAccessors" if prefix else "boolParamAccessors"
    return record.get(key) == "true"


def function_flags_readable(record):
    return record.get("functionFlagsReadable") == "true" and "functionFlags" in record


def process_label(record):
    loader = record.get("loader", "")
    exe = record.get("exe", "")
    if loader:
        return loader
    if "DuneSandboxServer" in exe:
        return "server"
    if "DuneSandbox-Win64" in exe or exe.lower().endswith(".exe"):
        return "win-client"
    if "DuneSandbox" in exe:
        return "linux-client"
    return "client"


def matches_filters(record, loader_filter, pid_filter, exe_substrings):
    if loader_filter and record.get("loader") not in loader_filter:
        return False
    if pid_filter and record.get("pid") not in pid_filter:
        return False
    if exe_substrings:
        haystack = " ".join(
            value for value in (record.get("exe", ""), record.get("module", ""), record.get("map", "")) if value
        )
        if not any(substring in haystack for substring in exe_substrings):
            return False
    return True


def record_matches_exe_substrings(record, exe_substrings):
    if not exe_substrings:
        return False
    haystack = " ".join(
        value for value in (record.get("exe", ""), record.get("module", ""), record.get("map", "")) if value
    )
    return any(substring in haystack for substring in exe_substrings)


def summarize(records, loader_filter=None, pid_filter=None, exe_substrings=None, expected=None):
    loader_filter = set(loader_filter or [])
    pid_filter = set(str(pid) for pid in (pid_filter or []))
    exe_substrings = tuple(exe_substrings or [])
    expected = tuple(expected or DEFAULT_EXPECTED)
    target_pids_from_exe = {
        record.get("pid", "")
        for record in records
        if record.get("pid")
        and record.get("event") == "loaded"
        and (not loader_filter or record.get("loader") in loader_filter)
        and record_matches_exe_substrings(record, exe_substrings)
    }
    effective_pid_filter = pid_filter
    effective_exe_substrings = exe_substrings
    if target_pids_from_exe:
        effective_pid_filter = pid_filter & target_pids_from_exe if pid_filter else target_pids_from_exe
        effective_exe_substrings = ()

    scoped_records = [
        record
        for record in records
        if matches_filters(record, loader_filter, effective_pid_filter, effective_exe_substrings)
    ]
    loaded = [record for record in scoped_records if record.get("event") == "loaded"]
    modules = [record for record in scoped_records if record.get("event") == "module"]
    starts = [record for record in scoped_records if record.get("event") == "scan-start"]
    finishes = [record for record in scoped_records if record.get("event") == "scan-finish"]
    skips = [record for record in scoped_records if record.get("event") == "scan-skip"]
    hits = [record for record in scoped_records if record.get("event") == "scan-hit"]
    ue_anchors = [record for record in scoped_records if record.get("event") == "ue-anchor"]
    mapped_ue_anchors = [record for record in ue_anchors if record.get("status") == "mapped"]
    ue_anchor_signatures = [
        record for record in scoped_records if record.get("event") == "ue-anchor-signature"
    ]
    resolved_ue_anchor_signatures = [
        record for record in ue_anchor_signatures if record.get("status") == "resolved"
    ]
    ue_candidate_globals = [record for record in scoped_records if record.get("event") == "ue-candidate-global"]
    added_ue_candidate_globals = [
        record for record in ue_candidate_globals if record.get("status") == "added"
    ]
    ue_anchor_group_counts = Counter(record.get("group") or "missing" for record in ue_anchors)
    mapped_ue_anchor_group_counts = Counter(record.get("group") or "missing" for record in mapped_ue_anchors)
    ue_anchor_signature_group_counts = Counter(record.get("group") or "missing" for record in ue_anchor_signatures)
    resolved_ue_anchor_signature_group_counts = Counter(
        record.get("group") or "missing" for record in resolved_ue_anchor_signatures
    )
    ue_runtime_discovery_records = [
        record
        for record in scoped_records
        if str(record.get("event", "")).startswith("ue-runtime-discovery")
        or record.get("event") == "ue-runtime-root-validation"
    ]
    ue_runtime_discovery = runtime_discovery_summary(ue_runtime_discovery_records, mapped_ue_anchors)
    ue_pointers = [record for record in scoped_records if record.get("event") == "ue-pointer"]
    mapped_ue_pointers = [record for record in ue_pointers if record.get("status") == "target-mapped"]
    ue_layouts = [record for record in scoped_records if record.get("event") == "ue-layout"]
    readable_ue_layouts = [record for record in ue_layouts if record.get("status") == "target-readable"]
    ue_layout_slots = [record for record in scoped_records if record.get("event") == "ue-layout-slot"]
    mapped_ue_layout_slots = [record for record in ue_layout_slots if record.get("status") == "target-mapped"]
    ue_uobjects = [record for record in scoped_records if record.get("event") == "ue-uobject"]
    candidate_ue_uobjects = [record for record in ue_uobjects if record.get("status") == "candidate"]
    class_mapped_ue_uobjects = [
        record for record in candidate_ue_uobjects if record.get("classMapped") == "true"
    ]
    ue_reflections = [record for record in scoped_records if record.get("event") == "ue-reflection"]
    class_mapped_ue_reflections = [
        record for record in ue_reflections if record.get("status") == "class-mapped"
    ]
    ue_reflection_slots = [
        record for record in scoped_records if record.get("event") == "ue-reflection-slot"
    ]
    mapped_ue_reflection_slots = [
        record for record in ue_reflection_slots if record.get("status") == "target-mapped"
    ]
    ue_reflection_fields = [
        record for record in scoped_records if record.get("event") == "ue-reflection-field"
    ]
    candidate_ue_reflection_fields = [
        record for record in ue_reflection_fields if record.get("status") == "candidate"
    ]
    class_mapped_ue_reflection_fields = [
        record for record in candidate_ue_reflection_fields if record.get("classMapped") == "true"
    ]
    ue_reflection_properties = [
        record for record in scoped_records if record.get("event") == "ue-reflection-property"
    ]
    candidate_ue_reflection_properties = [
        record for record in ue_reflection_properties if record.get("status") == "candidate"
    ]
    readable_ue_reflection_properties = [
        record
        for record in candidate_ue_reflection_properties
        if record.get("arrayDimReadable") == "true"
        and record.get("elementSizeReadable") == "true"
        and record.get("propertyFlagsReadable") == "true"
        and record.get("offsetInternalReadable") == "true"
        and 0 < record_int(record, "arrayDim") <= 1024
        and 0 < record_int(record, "elementSize") <= 4096
        and record_int(record, "offsetInternal", -1) >= 0
    ]
    runtime_ue_reflection_properties = [
        record for record in candidate_ue_reflection_properties if runtime_reflection_record(record)
    ]
    runtime_readable_ue_reflection_properties = [
        record for record in readable_ue_reflection_properties if runtime_reflection_record(record)
    ]
    runtime_readable_ue_reflection_property_keys = {
        (
            record.get("name", ""),
            record.get("chain", ""),
            record.get("index", ""),
            record.get("offsetInternal", ""),
            record.get("elementSize", ""),
            record.get("arrayDim", ""),
        )
        for record in runtime_readable_ue_reflection_properties
    }
    ue_reflection_values = [
        record for record in scoped_records if record.get("event") == "ue-reflection-value"
    ]
    read_ue_reflection_values = [
        record for record in ue_reflection_values if record.get("status") == "read"
    ]
    runtime_read_ue_reflection_values = [
        record for record in read_ue_reflection_values if runtime_reflection_record(record)
    ]
    runtime_descriptor_matched_read_ue_reflection_values = [
        record
        for record in runtime_read_ue_reflection_values
        if (
            record.get("name", ""),
            record.get("chain", ""),
            record.get("index", ""),
            record.get("offsetInternal", ""),
            record.get("elementSize", ""),
            record.get("arrayDim", ""),
        )
        in runtime_readable_ue_reflection_property_keys
    ]
    ue_function_param_roots = [
        record for record in scoped_records if record.get("event") == "ue-function-param-root"
    ]
    rooted_ue_function_param_roots = [
        record for record in ue_function_param_roots if record.get("status") == "root"
    ]
    ue_function_params = [record for record in scoped_records if record.get("event") == "ue-function-param"]
    candidate_ue_function_params = [
        record for record in ue_function_params if record.get("status") == "candidate"
    ]
    ue_function_param_container_children = [
        record for record in scoped_records if record.get("event") == "ue-function-param-container-child"
    ]
    ue_function_native_identities = [
        record for record in scoped_records if record.get("event") == "ue-function-native-identity"
    ]
    promoted_ue_function_native_identities = [
        record for record in ue_function_native_identities if record.get("status") == "promoted"
    ]
    readable_flag_ue_function_native_identities = [
        record for record in ue_function_native_identities if function_flags_readable(record)
    ]
    runtime_path_ue_function_native_identities = [
        record for record in ue_function_native_identities if record.get("functionRuntimePath")
    ]
    ue4ss_path_ue_function_native_identities = [
        record
        for record in ue_function_native_identities
        if is_ue4ss_script_function_path(record.get("functionPath", ""))
    ]
    candidate_ue_function_param_container_children = [
        record for record in ue_function_param_container_children if record.get("status") == "candidate"
    ]
    decoded_ue_function_param_container_children = [
        record
        for record in candidate_ue_function_param_container_children
        if record.get("childClassName") and record.get("role") in {"inner", "element", "key", "value"}
    ]
    readable_ue_function_params = [
        record
        for record in candidate_ue_function_params
        if record.get("arrayDimReadable") == "true"
        and record.get("elementSizeReadable") == "true"
        and record.get("propertyFlagsReadable") == "true"
        and record.get("offsetInternalReadable") == "true"
        and 0 < record_int(record, "arrayDim") <= 1024
        and 0 < record_int(record, "elementSize") <= 4096
        and record_int(record, "offsetInternal", -1) >= 0
    ]
    named_ue_function_params = [
        record
        for record in readable_ue_function_params
        if record.get("functionName") and record.get("functionPath")
    ]
    ue_function_paths = sorted(
        set(
            record.get("functionRuntimePath") or record.get("functionPath", "")
            for record in named_ue_function_params
            if record.get("functionRuntimePath") or record.get("functionPath")
        )
    )
    ue4ss_function_paths = sorted(
        set(
            path
            for path in (
                [
                    record.get("functionPath", "")
                    for record in named_ue_function_params
                    if is_ue4ss_script_function_path(record.get("functionPath", ""))
                ]
                + [
                    ue4ss_script_path_from_runtime_function_path(runtime_path)
                    for runtime_path in ue_function_paths
                ]
            )
            if path
        )
    )
    readable_ue_function_flag_roots = [
        record for record in rooted_ue_function_param_roots if function_flags_readable(record)
    ]
    readable_ue_function_flag_params = [
        record for record in candidate_ue_function_params if function_flags_readable(record)
    ]
    ue_function_flag_paths = sorted(
        set(
            record.get("functionRuntimePath") or record.get("functionPath", "")
            for record in readable_ue_function_flag_params
            if record.get("functionRuntimePath") or record.get("functionPath")
        )
    )
    ue_function_flag_values = sorted(
        set(record.get("functionFlags", "") for record in readable_ue_function_flag_roots + readable_ue_function_flag_params if record.get("functionFlags"))
    )
    hook_dispatches = [record for record in scoped_records if record.get("event") == "hook-dispatch"]
    hook_self_tests = [record for record in scoped_records if record.get("event") == "hook-dispatch-self-test"]
    passed_hook_self_tests = [record for record in hook_self_tests if record.get("status") == "passed"]
    mod_self_tests = [record for record in scoped_records if record.get("event") == "mod-dispatch-self-test"]
    passed_mod_self_tests = [record for record in mod_self_tests if record.get("status") == "passed"]
    lua_self_tests = [record for record in scoped_records if record.get("event") == "lua-dispatch-self-test"]
    passed_lua_self_tests = [record for record in lua_self_tests if record.get("status") == "passed"]
    passed_lua_callback_self_tests = [
        record
        for record in passed_lua_self_tests
        if record.get("callbackStatus") == "0"
        and record.get("preCalls") == "1"
        and record.get("postCalls") == "1"
        and record.get("preResult") == "11"
        and record.get("postResult") == "31"
        and record.get("preIsNumber") == "true"
        and record.get("postIsNumber") == "true"
    ]
    passed_lua_api_self_tests = [
        record
        for record in passed_lua_callback_self_tests
        if record.get("staticFindObjectCalls") == "1"
        and record.get("staticFindObjectHits") == "1"
        and lua_object_api_surface_passed(record)
        and record.get("findFirstOfCalls") == "1"
        and record.get("findFirstOfHits") == "1"
        and record.get("staticConstructObjectCalls") == "1"
        and record.get("staticConstructObjectHits") == "1"
        and record.get("notifyOnNewObjectCalls") == "1"
        and record.get("notifyOnNewObjectCallbacks") == "1"
        and record.get("notifyOnNewObjectResult") == "17"
        and record.get("notifyOnNewObjectIsNumber") == "true"
        and record.get("notifyOnNewObjectStatus") == "0"
        and record.get("executeInGameThreadCalls") == "1"
        and record.get("executeInGameThreadCallbacks") == "1"
        and record.get("executeInGameThreadResult") == "9"
        and record.get("executeInGameThreadIsNumber") == "true"
    ]
    passed_lua_scheduler_api_self_tests = [
        record for record in passed_lua_callback_self_tests if lua_scheduler_api_surface_passed(record)
    ]
    passed_lua_input_command_api_self_tests = [
        record for record in passed_lua_callback_self_tests if lua_input_command_api_surface_passed(record)
    ]
    passed_lua_object_api_self_tests = [
        record for record in passed_lua_callback_self_tests if lua_object_api_surface_passed(record)
    ]
    lua_reflection_self_tests = [
        record for record in scoped_records if record.get("event") == "lua-reflection-self-test"
    ]
    passed_lua_reflection_self_tests = [
        record
        for record in lua_reflection_self_tests
        if lua_reflection_self_test_passed(record)
    ]
    raw_set_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "rawPropertySetHits") > 0
    ]
    named_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "namedPropertyHits") > 0
    ]
    numeric_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_numeric_property_values_passed(record)
    ]
    name_text_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_name_text_property_values_passed(record)
    ]
    array_inner_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_array_inner_property_passed(record)
    ]
    enum_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_enum_property_passed(record)
    ]
    container_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_container_property_passed(record)
    ]
    import_text_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_import_text_passed(record)
    ]
    export_text_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_export_text_passed(record)
    ]
    property_metadata_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_property_metadata_passed(record)
    ]
    descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_descriptor_values_passed(record)
    ]
    reflection_for_each_property_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_for_each_property_passed(record)
    ]
    runtime_reflection_for_each_property_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "runtimeReflectionForEachPropertyCallbacks") > 0
    ]
    self_test_reflection_for_each_property_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "selfTestReflectionForEachPropertyCallbacks") > 0
    ]
    typed_live_descriptor_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "liveDescriptorTypedClassHits") > 0
    ]
    runtime_typed_live_descriptor_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "runtimeLiveDescriptorTypedClassHits") > 0
    ]
    self_test_typed_live_descriptor_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "selfTestLiveDescriptorTypedClassHits") > 0
    ]
    typed_live_descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "liveDescriptorTypedValueHits") > 0
    ]
    runtime_typed_live_descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "runtimeLiveDescriptorTypedValueHits") > 0
    ]
    self_test_typed_live_descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "selfTestLiveDescriptorTypedValueHits") > 0
    ]
    typed_live_descriptor_value_set_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "liveDescriptorTypedValueSetHits") > 0
    ]
    runtime_typed_live_descriptor_value_set_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "runtimeLiveDescriptorTypedValueSetHits") > 0
    ]
    self_test_typed_live_descriptor_value_set_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "selfTestLiveDescriptorTypedValueSetHits") > 0
    ]
    live_descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if lua_reflection_live_descriptor_values_passed(record)
    ]
    runtime_live_descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "runtimeLiveDescriptorValueGetHits") > 0
    ]
    self_test_live_descriptor_value_lua_reflection_self_tests = [
        record
        for record in passed_lua_reflection_self_tests
        if record_int(record, "selfTestLiveDescriptorValueGetHits") > 0
    ]
    lua_process_event_self_tests = [
        record for record in scoped_records if record.get("event") == "lua-process-event-self-test"
    ]
    passed_lua_process_event_self_tests = [
        record
        for record in lua_process_event_self_tests
        if record.get("status") == "passed"
        and record.get("installed") == "true"
        and record.get("restored") == "true"
        and record.get("hookCalls") == "1"
        and record.get("originalAfterHook") == "1"
        and record.get("preStatus") == "0"
        and record.get("postStatus") == "0"
        and record.get("preCalls") == "1"
        and record.get("postCalls") == "1"
        and record.get("preResult") == "11"
        and record.get("postResult") == "31"
        and record.get("paramsResult") == "42"
        and record.get("finalResult") == "52"
    ]
    lua_process_event_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_param_accessors_passed(record)
    ]
    lua_process_event_function_param_method_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_function_param_methods_passed(record)
    ]
    lua_process_event_function_param_lookup_method_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_function_param_lookup_methods_passed(record)
    ]
    lua_process_event_function_param_iteration_method_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_function_param_iteration_methods_passed(record)
    ]
    lua_process_event_container_alias_method_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_container_alias_methods_passed(record)
    ]
    lua_process_event_container_storage_layout_method_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_container_storage_layout_methods_passed(record)
    ]
    lua_process_event_scalar_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_scalar_param_accessors_passed(record)
    ]
    lua_process_event_name_string_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_name_string_param_accessors_passed(record)
    ]
    lua_process_event_struct_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_struct_param_accessors_passed(record)
    ]
    lua_process_event_enum_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_enum_param_accessors_passed(record)
    ]
    lua_process_event_object_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_object_param_accessors_passed(record)
    ]
    lua_process_event_bool_param_accessor_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if process_event_bool_param_accessors_passed(record)
    ]
    routed_lua_process_event_self_tests = [
        record
        for record in passed_lua_process_event_self_tests
        if record_int(record, "hooks") > record_int(record, "preCalls")
        and record_int(record, "preCalls") == record_int(record, "postCalls")
        and record_int(record, "preCalls") > 0
    ]
    lua_mod_scripts = [record for record in scoped_records if record.get("event") == "lua-mod-script"]
    passed_lua_mod_scripts = [record for record in lua_mod_scripts if record.get("status") == "passed"]
    lua_mod_dispatch_self_tests = [
        record for record in scoped_records if record.get("event") == "lua-mod-dispatch-self-test"
    ]
    passed_lua_mod_dispatch_self_tests = [
        record for record in lua_mod_dispatch_self_tests if record.get("status") == "passed"
    ]
    lua_mod_finishes = [record for record in scoped_records if record.get("event") == "lua-mod-finish"]
    passed_lua_mod_finishes = [record for record in lua_mod_finishes if record.get("status") == "passed"]
    lua_object_api_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_object_api_surface_passed(record)
    ]
    lua_load_asset_package_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_asset_package_surface_passed(record)
    ]
    lua_load_asset_backend_state_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_asset_backend_state_surface_passed(record)
    ]
    lua_load_asset_backend_anchor_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_asset_backend_anchor_surface_passed(record)
    ]
    lua_load_asset_package_bridge_state_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_asset_package_bridge_state_surface_passed(record)
    ]
    lua_load_asset_package_native_invoke_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_asset_package_native_invoke_surface_passed(record)
    ]
    lua_load_asset_package_abi_state_events = [
        record for record in scoped_records if lua_load_asset_package_abi_state_event_passed(record)
    ]
    lua_load_asset_package_string_bridge_events = [
        record for record in scoped_records if lua_load_asset_package_string_bridge_event_passed(record)
    ]
    lua_load_asset_package_native_buffer_events = [
        record for record in scoped_records if lua_load_asset_package_native_buffer_event_passed(record)
    ]
    lua_load_asset_package_tchar_buffer_events = [
        record for record in scoped_records if lua_load_asset_package_tchar_buffer_event_passed(record)
    ]
    lua_load_asset_package_tchar_verification_events = [
        record for record in scoped_records if lua_load_asset_package_tchar_verification_event_passed(record)
    ]
    lua_load_asset_package_call_frame_events = [
        record for record in scoped_records if lua_load_asset_package_call_frame_event_passed(record)
    ]
    lua_load_asset_package_call_frame_verification_events = [
        record for record in scoped_records if lua_load_asset_package_call_frame_verification_event_passed(record)
    ]
    lua_load_asset_package_crash_guard_events = [
        record for record in scoped_records if lua_load_asset_package_crash_guard_event_passed(record)
    ]
    lua_load_asset_package_guarded_call_events = [
        record for record in scoped_records if lua_load_asset_package_guarded_call_event_passed(record)
    ]
    lua_load_asset_package_return_validation_events = [
        record for record in scoped_records if lua_load_asset_package_return_validation_event_passed(record)
    ]
    lua_load_asset_package_native_call_adapter_events = [
        record for record in scoped_records if lua_load_asset_package_native_call_adapter_event_passed(record)
    ]
    lua_load_asset_package_invocation_descriptor_events = [
        record for record in scoped_records if lua_load_asset_package_invocation_descriptor_event_passed(record)
    ]
    lua_load_asset_package_native_executor_events = [
        record for record in scoped_records if lua_load_asset_package_native_executor_event_passed(record)
    ]
    lua_load_asset_package_native_executor_ready_events = [
        record for record in lua_load_asset_package_native_executor_events
        if lua_load_asset_package_native_executor_ready_event(record)
    ]
    lua_load_asset_package_native_executor_target_ready_events = [
        record for record in lua_load_asset_package_native_executor_ready_events
        if lua_load_asset_package_native_executor_target_ready_event(record)
    ]
    lua_load_asset_package_preflight_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_asset_package_preflight_surface_passed(record)
    ]
    lua_function_iteration_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_function_iteration_surface_passed(record)
    ]
    lua_function_iteration_checks = [
        record for record in scoped_records if record.get("event") == "lua-function-iteration-check"
    ]
    passed_lua_function_iteration_checks = [
        record for record in lua_function_iteration_checks if record.get("status") == "passed"
    ]
    runtime_lua_function_iteration_checks = [
        record
        for record in passed_lua_function_iteration_checks
        if runtime_iteration_record(record)
    ]
    self_test_lua_function_iteration_checks = [
        record
        for record in passed_lua_function_iteration_checks
        if self_test_iteration_record(record)
    ]
    lua_notify_on_new_object_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_notify_on_new_object_surface_passed(record)
    ]
    lua_synthetic_outer_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_synthetic_outer_surface_passed(record)
    ]
    lua_world_context_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_world_context_surface_passed(record)
    ]
    lua_class_default_object_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_class_default_object_surface_passed(record)
    ]
    lua_level_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_level_surface_passed(record)
    ]
    lua_process_console_exec_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_process_console_exec_hook_surface_passed(record)
    ]
    lua_scheduler_api_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_scheduler_api_mod_surface_passed(record)
    ]
    lua_input_command_api_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_input_command_api_mod_surface_passed(record)
    ]
    lua_local_player_exec_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_local_player_exec_hook_surface_passed(record)
    ]
    lua_call_function_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_call_function_hook_surface_passed(record)
    ]
    lua_call_function_structured_args_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_call_function_structured_args_surface_passed(record)
    ]
    lua_process_event_compat_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_process_event_compat_surface_passed(record)
    ]
    lua_process_event_bridge_state_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_process_event_bridge_state_surface_passed(record)
    ]
    lua_process_event_native_invoke_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_process_event_native_invoke_surface_passed(record)
    ]
    lua_process_event_native_invoke_self_tests = [
        record
        for record in scoped_records
        if record.get("event") == "lua-process-event-native-invoke-self-test"
        and record.get("status") == "passed"
        and lua_process_event_native_invoke_surface_passed(record)
    ]
    lua_process_event_native_invoke_non_self_test_gates = [
        record
        for record in scoped_records
        if lua_process_event_native_invoke_non_self_test_gate_passed(record)
    ]
    lua_process_event_native_invoke_descriptor_preflights = [
        record
        for record in scoped_records
        if lua_process_event_native_invoke_descriptor_preflight_ready(record)
    ]
    lua_process_event_native_invoke_non_self_test_invocations = [
        record
        for record in scoped_records
        if lua_process_event_native_invoke_non_self_test_invoked(record)
    ]
    lua_process_event_params_buffers = [
        record
        for record in scoped_records
        if record.get("event") == "lua-process-event-params-buffer"
        and record.get("status") == "created"
    ]
    lua_lifecycle_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_lifecycle_hook_surface_passed(record)
    ]
    lua_custom_event_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_custom_event_surface_passed(record)
    ]
    lua_load_map_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_load_map_hook_surface_passed(record)
    ]
    lua_begin_play_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_begin_play_hook_surface_passed(record)
    ]
    lua_init_game_state_hook_mod_finishes = [
        record for record in passed_lua_mod_finishes if lua_init_game_state_hook_surface_passed(record)
    ]
    lua_object_registry = [record for record in scoped_records if record.get("event") == "lua-object-registry"]
    added_lua_object_registry = [record for record in lua_object_registry if record.get("status") == "added"]
    lua_object_registry_checks = [
        record for record in scoped_records if record.get("event") == "lua-object-registry-check"
    ]
    passed_lua_object_registry_checks = [
        record for record in lua_object_registry_checks if record.get("status") == "passed"
    ]
    lua_function_registry_checks = [
        record for record in scoped_records if record.get("event") == "lua-function-registry-check"
    ]
    passed_lua_function_registry_checks = [
        record for record in lua_function_registry_checks if record.get("status") == "passed"
    ]
    runtime_lua_function_registry_checks = [
        record for record in passed_lua_function_registry_checks if runtime_registry_record(record)
    ]
    self_test_lua_function_registry_checks = [
        record for record in passed_lua_function_registry_checks if self_test_registry_record(record)
    ]
    ue_lua_object_registry = [
        record for record in added_lua_object_registry if record.get("source") == "ue-uobject"
    ]
    runtime_ue_lua_object_registry = [
        record for record in ue_lua_object_registry if runtime_registry_record(record)
    ]
    self_test_ue_lua_object_registry = [
        record for record in ue_lua_object_registry if self_test_registry_record(record)
    ]
    object_array_lua_object_registry = [
        record for record in added_lua_object_registry if record.get("source") == "ue-object-array"
    ]
    runtime_object_array_lua_object_registry = [
        record for record in object_array_lua_object_registry if runtime_registry_record(record)
    ]
    self_test_object_array_lua_object_registry = [
        record for record in object_array_lua_object_registry if self_test_registry_record(record)
    ]
    decoded_lua_object_alias_registry = [
        record
        for record in added_lua_object_registry
        if record.get("source") in ("ue-uobject-fname", "ue-object-array-fname")
    ]
    runtime_decoded_lua_object_alias_registry = [
        record for record in decoded_lua_object_alias_registry if runtime_registry_record(record)
    ]
    self_test_decoded_lua_object_alias_registry = [
        record for record in decoded_lua_object_alias_registry if self_test_registry_record(record)
    ]
    skipped_decoded_lua_object_alias_registry = [
        record
        for record in lua_object_registry
        if record.get("status") == "skipped"
        and record.get("source") in ("ue-uobject-fname", "ue-object-array-fname")
    ]
    lua_object_outer_chains = [
        record for record in scoped_records if record.get("event") == "lua-object-outer-chain"
    ]
    resolved_lua_object_outer_chains = [
        record
        for record in lua_object_outer_chains
        if record.get("status") == "resolved"
        and record_int(record, "depth") > 0
        and record.get("terminalPath")
        and record.get("chain")
    ]
    lua_object_outer_chain_identities = [
        record
        for record in resolved_lua_object_outer_chains
        if record.get("reconstructedPath")
        and record.get("reconstructedFullName")
        and record.get("fullNameResolved") == "true"
    ]
    lua_global_runtime_helper_checks = [
        record for record in scoped_records if record.get("event") == "lua-global-runtime-helper-check"
    ]
    passed_lua_global_runtime_helper_checks = [
        record for record in lua_global_runtime_helper_checks if lua_global_runtime_helper_surface_passed(record)
    ]
    promoted_world_lua_global_runtime_helper_checks = [
        record for record in passed_lua_global_runtime_helper_checks if record.get("globalWorldPromoted") == "true"
    ]
    promoted_engine_lua_global_runtime_helper_checks = [
        record for record in passed_lua_global_runtime_helper_checks if record.get("globalEnginePromoted") == "true"
    ]
    ue_object_arrays = [record for record in scoped_records if record.get("event") == "ue-object-array"]
    ue_object_array_shapes = [
        record for record in scoped_records if record.get("event") == "ue-object-array-shape"
    ]
    plausible_ue_object_array_shapes = [
        record
        for record in ue_object_array_shapes
        if record.get("status") == "header-plausible" or record.get("countsPlausible") == "true"
    ]
    implausible_ue_object_array_shapes = [
        record
        for record in ue_object_array_shapes
        if record.get("status") == "header-implausible" or record.get("countsPlausible") == "false"
    ]
    finished_ue_object_arrays = [
        record for record in ue_object_arrays if record.get("status") == "finished"
    ]
    ue_object_array_finishes = [
        record for record in scoped_records if record.get("event") == "ue-object-array-finish"
    ]
    registry_ue_object_array_finishes = [
        record for record in ue_object_array_finishes if record_int(record, "registryCount") > 0
    ] + [
        record for record in finished_ue_object_arrays if record_int(record, "registered") > 0
    ]
    ue_object_array_items = [
        record for record in scoped_records if record.get("event") == "ue-object-array-item"
    ]
    ue_object_native_identities = [
        record for record in scoped_records if record.get("event") == "ue-object-native-identity"
    ]
    promoted_ue_object_native_identities = [
        record for record in ue_object_native_identities if record.get("status") == "promoted"
    ]
    decoded_name_ue_object_native_identities = [
        record for record in ue_object_native_identities if record.get("nameDecoded") == "true"
    ]
    decoded_class_name_ue_object_native_identities = [
        record for record in ue_object_native_identities if record.get("classNameDecoded") == "true"
    ]
    internal_flag_ue_object_array_items = [
        record for record in ue_object_array_items if record.get("internalFlagsReadable") == "true"
    ]
    nonzero_internal_flag_ue_object_array_items = [
        record
        for record in internal_flag_ue_object_array_items
        if record_int(record, "internalFlags") != 0
    ]
    ue_fnames = [record for record in scoped_records if record.get("event") == "ue-fname"]
    decoded_ue_fnames = [record for record in ue_fnames if record.get("status") == "decoded"]
    ue_fname_finishes = [
        record for record in scoped_records if record.get("event") == "ue-fname-finish"
    ]
    ready_ue_fname_finishes = [
        record for record in ue_fname_finishes if record.get("status") == "ready"
    ]
    validated_runtime_root_names = set()
    runtime_discovery_ran = bool(ue_runtime_discovery.get("startCount") or ue_runtime_discovery.get("finishCount"))
    validated_runtime_root_candidate_names = set()
    if ready_ue_fname_finishes or decoded_ue_fnames:
        validated_runtime_root_candidate_names.add("RuntimeFNamePool")
    if registry_ue_object_array_finishes or class_mapped_ue_uobjects:
        validated_runtime_root_candidate_names.add("RuntimeGUObjectArray")
    validated_runtime_root_candidate_names.update(ue_runtime_discovery.get("consumerValidatedNames") or [])
    if runtime_discovery_ran and (ready_ue_fname_finishes or decoded_ue_fnames):
        validated_runtime_root_names.add("RuntimeFNamePool")
    if runtime_discovery_ran and (registry_ue_object_array_finishes or class_mapped_ue_uobjects):
        validated_runtime_root_names.add("RuntimeGUObjectArray")
    if runtime_discovery_ran:
        validated_runtime_root_names.update(ue_runtime_discovery.get("consumerValidatedNames") or [])
    runtime_roots_validated = {"RuntimeFNamePool", "RuntimeGUObjectArray"}.issubset(validated_runtime_root_names)
    runtime_root_validation_ready = {"RuntimeFNamePool", "RuntimeGUObjectArray"}.issubset(
        validated_runtime_root_candidate_names
    )
    runtime_discovery_failure = ue_runtime_discovery.get("failure", "")
    if not runtime_roots_validated and runtime_discovery_failure == "":
        runtime_discovery_failure = "unvalidated-root-hits"
    ue_runtime_discovery = {
        **ue_runtime_discovery,
        "ready": runtime_roots_validated,
        "rootValidationReady": runtime_root_validation_ready,
        "failure": runtime_discovery_failure,
        "validatedNames": sorted(validated_runtime_root_names),
        "rootValidationNames": sorted(validated_runtime_root_candidate_names),
        "validatedBy": {
            "fnameReadyFinishes": len(ready_ue_fname_finishes),
            "decodedFNames": len(decoded_ue_fnames),
            "objectArrayRegistryFinishes": len(registry_ue_object_array_finishes),
            "classMappedUObjects": len(class_mapped_ue_uobjects),
        },
    }
    ue_process_event_hooks = [
        record for record in scoped_records if record.get("event") == "ue-process-event-hook"
    ]
    passed_ue_process_event_hooks = [
        record for record in ue_process_event_hooks if record.get("status") == "passed"
    ]
    non_self_test_passed_ue_process_event_hooks = [
        record for record in passed_ue_process_event_hooks if non_self_test_hook_record(record)
    ]
    proven_target_passed_ue_process_event_hooks = [
        record
        for record in passed_ue_process_event_hooks
        if proven_process_event_hook_target_record(record, mapped_ue_anchors + resolved_ue_anchor_signatures)
    ]
    ue_call_function_hooks = [
        record for record in scoped_records if record.get("event") == "ue-call-function-hook"
    ]
    passed_ue_call_function_hooks = [
        record for record in ue_call_function_hooks if record.get("status") == "passed"
    ]
    non_self_test_passed_ue_call_function_hooks = [
        record for record in passed_ue_call_function_hooks if non_self_test_hook_record(record)
    ]
    proven_target_passed_ue_call_function_hooks = [
        record
        for record in passed_ue_call_function_hooks
        if proven_call_function_hook_target_record(record, mapped_ue_anchors + resolved_ue_anchor_signatures)
    ]
    ue_call_function_live_hooks = [
        record for record in scoped_records if record.get("event") == "ue-call-function-live-hook"
    ]
    installed_ue_call_function_live_hooks = [
        record for record in ue_call_function_live_hooks if record.get("status") == "installed"
    ]
    routed_ue_call_function_live_lua_hooks = [
        record
        for record in installed_ue_call_function_live_hooks
        if record.get("luaDispatch") == "true"
        and (record_int(record, "luaPreCalls") > 0 or record_int(record, "luaPostCalls") > 0)
    ]
    handled_ue_call_function_live_lua_hooks = [
        record
        for record in routed_ue_call_function_live_lua_hooks
        if record_int(record, "luaPreHandled") > 0 or record_int(record, "luaPostHandled") > 0
    ]
    non_self_test_installed_ue_call_function_live_hooks = [
        record for record in installed_ue_call_function_live_hooks if non_self_test_hook_record(record)
    ]
    proven_target_installed_ue_call_function_live_hooks = [
        record
        for record in installed_ue_call_function_live_hooks
        if proven_call_function_hook_target_record(record, mapped_ue_anchors + resolved_ue_anchor_signatures)
    ]
    proven_target_routed_ue_call_function_live_lua_hooks = [
        record
        for record in routed_ue_call_function_live_lua_hooks
        if proven_call_function_hook_target_record(record, mapped_ue_anchors + resolved_ue_anchor_signatures)
    ]
    proven_target_handled_ue_call_function_live_lua_hooks = [
        record
        for record in handled_ue_call_function_live_lua_hooks
        if proven_call_function_hook_target_record(record, mapped_ue_anchors + resolved_ue_anchor_signatures)
    ]
    ue_process_event_live_hooks = [
        record for record in scoped_records if record.get("event") == "ue-process-event-live-hook"
    ]
    installed_ue_process_event_live_hooks = [
        record for record in ue_process_event_live_hooks if record.get("status") == "installed"
    ]
    non_self_test_installed_ue_process_event_live_hooks = [
        record for record in installed_ue_process_event_live_hooks if non_self_test_hook_record(record)
    ]
    proven_target_installed_ue_process_event_live_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if proven_process_event_hook_target_record(record, mapped_ue_anchors + resolved_ue_anchor_signatures)
    ]
    ue_process_event_live_contexts = [
        record for record in scoped_records if record.get("event") == "ue-process-event-live-context"
    ]
    resolved_ue_process_event_live_contexts = [
        record
        for record in ue_process_event_live_contexts
        if record.get("status") == "resolved"
        and record.get("objectResolved") == "true"
        and record.get("functionPath")
        and record_int(record, "functionParamDescriptors") > 0
        and record.get("paramsPresent") == "true"
    ]
    ue_function_path_set = set(ue_function_paths)
    ue4ss_function_path_set = set(ue4ss_function_paths)
    matched_ue_process_event_live_contexts = [
        record
        for record in resolved_ue_process_event_live_contexts
        if record.get("functionPath") in ue4ss_function_path_set
        or record.get("functionPath") in ue_function_path_set
        or record.get("functionRuntimePath") in ue_function_path_set
    ]
    runtime_matched_ue_process_event_live_contexts = [
        record for record in matched_ue_process_event_live_contexts if runtime_process_event_context_record(record)
    ]
    self_test_provenance_ue_process_event_live_contexts = [
        record for record in ue_process_event_live_contexts if record.get("functionProvenance") == "self-test"
    ]
    runtime_provenance_ue_process_event_live_contexts = [
        record for record in ue_process_event_live_contexts if record.get("functionProvenance") == "runtime"
    ]
    ue_process_event_live_registry_contexts = [
        record for record in scoped_records if record.get("event") == "ue-process-event-live-registry-context"
    ]
    resolved_ue_process_event_live_registry_contexts = [
        record
        for record in ue_process_event_live_registry_contexts
        if record.get("status") == "resolved"
        and record.get("objectResolved") == "true"
        and record.get("functionResolved") == "true"
        and record.get("functionPath")
        and record_int(record, "functionParamDescriptors") > 0
        and record.get("paramsPresent") == "true"
    ]
    native_identity_ue_process_event_live_registry_contexts = [
        record
        for record in resolved_ue_process_event_live_registry_contexts
        if record.get("objectNativeIdentity") == "true"
        and record.get("functionNativeIdentity") == "true"
    ]
    matched_ue_process_event_live_registry_contexts = [
        record
        for record in native_identity_ue_process_event_live_registry_contexts
        if record.get("functionPath") in ue4ss_function_path_set
        or record.get("functionPath") in ue_function_path_set
        or record.get("functionRuntimePath") in ue_function_path_set
    ]
    runtime_matched_ue_process_event_live_registry_contexts = [
        record for record in matched_ue_process_event_live_registry_contexts if runtime_process_event_context_record(record)
    ]
    self_test_provenance_ue_process_event_live_registry_contexts = [
        record for record in ue_process_event_live_registry_contexts if record.get("functionProvenance") == "self-test"
    ]
    runtime_provenance_ue_process_event_live_registry_contexts = [
        record for record in ue_process_event_live_registry_contexts if record.get("functionProvenance") == "runtime"
    ]
    ue_process_event_live_params = [
        record for record in scoped_records if record.get("event") == "ue-process-event-live-param"
    ]
    runtime_process_event_context_keys = {
        (
            record.get("call", ""),
            record.get("function", ""),
            record.get("functionPath", "") or record.get("functionRuntimePath", ""),
        )
        for record in runtime_matched_ue_process_event_live_contexts
    } | {
        (
            record.get("call", ""),
            record.get("function", ""),
            record.get("functionPath", "") or record.get("functionRuntimePath", ""),
        )
        for record in runtime_matched_ue_process_event_live_registry_contexts
    }

    def process_event_live_param_matches_runtime_context(record):
        path = record.get("functionPath", "") or record.get("functionRuntimePath", "")
        return (
            record.get("call", ""),
            record.get("function", ""),
            path,
        ) in runtime_process_event_context_keys

    read_ue_process_event_live_params = [
        record
        for record in ue_process_event_live_params
        if record.get("status") == "read"
        and record.get("functionPath")
        and record.get("param")
        and record_int(record, "size") > 0
    ]
    raw_ue_process_event_live_params = [
        record
        for record in ue_process_event_live_params
        if record.get("status") == "raw"
        and record.get("functionPath")
        and record.get("param")
        and record_int(record, "size") > 0
        and "rawHex=" in record.get("value", "")
    ]
    container_ue_process_event_live_params = [
        record
        for record in ue_process_event_live_params
        if record.get("status") == "container"
        and record.get("functionPath")
        and record.get("param")
        and record_int(record, "size") > 0
        and "kind=" in record.get("value", "")
        and "rawHex=" in record.get("value", "")
    ]
    sampled_container_ue_process_event_live_params = [
        record
        for record in container_ue_process_event_live_params
        if "dataSampleHex=" in record.get("value", "")
    ]
    array_container_ue_process_event_live_params = [
        record
        for record in container_ue_process_event_live_params
        if "kind=FScriptArray" in record.get("value", "")
    ]
    set_container_ue_process_event_live_params = [
        record
        for record in container_ue_process_event_live_params
        if "kind=FScriptSetHeader" in record.get("value", "")
    ]
    map_container_ue_process_event_live_params = [
        record
        for record in container_ue_process_event_live_params
        if "kind=FScriptMapHeader" in record.get("value", "")
    ]
    set_map_container_ue_process_event_live_params = (
        set_container_ue_process_event_live_params + map_container_ue_process_event_live_params
    )
    runtime_read_ue_process_event_live_params = [
        record for record in read_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_raw_ue_process_event_live_params = [
        record for record in raw_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_container_ue_process_event_live_params = [
        record for record in container_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_sampled_container_ue_process_event_live_params = [
        record for record in sampled_container_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_array_container_ue_process_event_live_params = [
        record for record in array_container_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_set_container_ue_process_event_live_params = [
        record for record in set_container_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_map_container_ue_process_event_live_params = [
        record for record in map_container_ue_process_event_live_params if process_event_live_param_matches_runtime_context(record)
    ]
    runtime_set_map_container_ue_process_event_live_params = (
        runtime_set_container_ue_process_event_live_params + runtime_map_container_ue_process_event_live_params
    )
    ue_process_event_lua_context_handle_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if record_int(record, "luaObjectHandleHits") > 0
        and record_int(record, "luaFunctionHandleHits") > 0
        and record_int(record, "luaParamsHandleHits") > 0
    ]
    ue_process_event_live_lua_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_param_accessors_passed(record, "lua")
    ]
    ue_process_event_live_lua_function_param_method_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_function_param_methods_passed(record, "lua")
    ]
    ue_process_event_live_lua_function_param_lookup_method_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_function_param_lookup_methods_passed(record, "lua")
    ]
    ue_process_event_live_lua_function_param_iteration_method_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_function_param_iteration_methods_passed(record, "lua")
    ]
    ue_process_event_live_lua_container_storage_layout_method_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_container_storage_layout_methods_passed(record, "lua")
    ]
    ue_process_event_live_lua_scalar_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_scalar_param_accessors_passed(record, "lua")
    ]
    ue_process_event_live_lua_name_string_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_name_string_param_accessors_passed(record, "lua")
    ]
    ue_process_event_live_lua_struct_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_struct_param_accessors_passed(record, "lua")
    ]
    ue_process_event_live_lua_enum_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_enum_param_accessors_passed(record, "lua")
    ]
    ue_process_event_live_lua_object_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_object_param_accessors_passed(record, "lua")
    ]
    ue_process_event_live_lua_bool_param_accessor_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if process_event_bool_param_accessors_passed(record, "lua")
    ]
    routed_ue_process_event_live_lua_hooks = [
        record
        for record in installed_ue_process_event_live_hooks
        if record.get("luaDispatch") == "true"
        and record_int(record, "luaPreCalls") > 0
        and record_int(record, "luaPostCalls") > 0
    ]
    restored_ue_process_event_live_hooks = [
        record for record in ue_process_event_live_hooks if record.get("status") == "restored"
    ]
    ue_process_event_dispatch_self_tests = [
        record for record in scoped_records if record.get("event") == "ue-process-event-dispatch-self-test"
    ]
    armed_ue_process_event_dispatch_self_tests = [
        record for record in ue_process_event_dispatch_self_tests if record.get("status") == "armed"
    ]
    ue_process_event_live_lua_dispatches = [
        record for record in scoped_records if record.get("event") == "ue-process-event-live-lua-dispatch"
    ]
    armed_ue_process_event_live_lua_dispatches = [
        record for record in ue_process_event_live_lua_dispatches if record.get("status") == "armed"
    ]
    multi_hook_ue_process_event_live_lua_dispatches = [
        record for record in armed_ue_process_event_live_lua_dispatches if record_int(record, "hooks") > 1
    ]
    matched_ue_process_event_live_lua_dispatches = [
        record
        for record in multi_hook_ue_process_event_live_lua_dispatches
        if record.get("hook") and "NotTarget" not in record.get("hook", "")
    ]
    closed_ue_process_event_live_lua_dispatches = [
        record for record in ue_process_event_live_lua_dispatches if record.get("status") == "closed"
    ]
    closed_matched_ue_process_event_live_lua_dispatches = [
        record
        for record in closed_ue_process_event_live_lua_dispatches
        if record_int(record, "preCalls") > 0
        and record_int(record, "postCalls") > 0
        and record_int(record, "preResult") == 11
        and record_int(record, "postResult") == 31
        and record_int(record, "preStatus") == 0
        and record_int(record, "postStatus") == 0
    ]
    lua_process_event_path_exact_matches = sum(record_int(record, "pathExactMatches") for record in lua_process_event_self_tests)
    lua_process_event_path_alias_matches = sum(record_int(record, "pathAliasMatches") for record in lua_process_event_self_tests)
    ue_process_event_live_lua_path_exact_matches = sum(
        record_int(record, "pathExactMatches") for record in ue_process_event_live_lua_dispatches
    )
    ue_process_event_live_lua_path_alias_matches = sum(
        record_int(record, "pathAliasMatches") for record in ue_process_event_live_lua_dispatches
    )
    forward_smokes = [record for record in scoped_records if record.get("event") == "forward-smoke"]

    if not loaded and not hits and (loader_filter or pid_filter or exe_substrings):
        # Some logs put exe only on event=loaded. If an exe filter was too narrow,
        # still return an empty scoped summary rather than guessing.
        pass

    categories = Counter()
    hits_by_name = {}
    offsets_by_name = defaultdict(list)
    kinds_by_name = defaultdict(Counter)
    sources_by_name = defaultdict(Counter)
    pointers_by_name = defaultdict(list)
    layouts_by_name = defaultdict(list)
    layout_slots_by_name = defaultdict(list)
    uobjects_by_name = defaultdict(list)
    fnames_by_object_name = defaultdict(list)

    anchor_hit_records = hits + mapped_ue_anchors + resolved_ue_anchor_signatures
    for hit in anchor_hit_records:
        name = hit.get("name", "")
        if not name:
            continue
        categories[category_for(name)] += 1
        kind = hit.get("kind") or hit.get("event", "")
        if hit.get("event") == "ue-anchor-signature":
            kind = "ue-anchor-signature"
        kinds_by_name[name][kind] += 1
        source = record_source(hit)
        if source:
            sources_by_name[name][source] += 1
        offsets_by_name[name].append(
            {
                "kind": kind,
                "addr": hit.get("addr", ""),
                "offset": record_offset(hit),
                "imageOffset": hit.get("imageOffset", ""),
                "fileOffset": hit.get("fileOffset", ""),
                "rva": hit.get("rva", ""),
                "source": source,
            }
        )

    for name in sorted(offsets_by_name):
        offsets = offsets_by_name[name]
        hits_by_name[name] = {
            "category": category_for(name),
            "count": len(offsets),
            "kinds": dict(kinds_by_name[name]),
            "sources": dict(sources_by_name[name]),
            "first": offsets[0],
            "offsets": offsets,
        }

    for pointer in ue_pointers:
        name = pointer.get("name", "")
        if name:
            pointers_by_name[name].append(pointer)

    for layout in ue_layouts:
        name = layout.get("name", "")
        if name:
            layouts_by_name[name].append(layout)
    for slot in ue_layout_slots:
        name = slot.get("name", "")
        if name:
            layout_slots_by_name[name].append(slot)
    for uobject in ue_uobjects:
        name = uobject.get("name", "")
        if name:
            uobjects_by_name[name].append(uobject)
    for fname in ue_fnames:
        name = fname.get("objectName", "")
        if name:
            fnames_by_object_name[name].append(fname)

    present_names = set(hits_by_name)
    expected_status = {
        name: {
            "present": name in present_names,
            "category": category_for(name),
            "count": hits_by_name.get(name, {}).get("count", 0),
            "first": hits_by_name.get(name, {}).get("first", {}),
        }
        for name in expected
    }

    module_paths = []
    seen_modules = set()
    for module in modules:
        path = module.get("path") or module.get("name") or module.get("module") or ""
        if path and path not in seen_modules:
            seen_modules.add(path)
            module_paths.append(path)

    return {
        "recordCount": len(scoped_records),
        "targetPidsFromExe": sorted(target_pids_from_exe),
        "effectivePidFilter": sorted(effective_pid_filter),
        "loadCount": len(loaded),
        "moduleCount": len(modules),
        "scanStartCount": len(starts),
        "scanFinishCount": len(finishes),
        "scanSkipCount": len(skips),
        "hitCount": len(hits),
        "ueAnchorCount": len(ue_anchors),
        "mappedUeAnchorCount": len(mapped_ue_anchors),
        "ueAnchorGroupCounts": dict(sorted(ue_anchor_group_counts.items())),
        "mappedUeAnchorGroupCounts": dict(sorted(mapped_ue_anchor_group_counts.items())),
        "ueAnchorSignatureCount": len(ue_anchor_signatures),
        "resolvedUeAnchorSignatureCount": len(resolved_ue_anchor_signatures),
        "ueAnchorSignatureStatusCounts": dict(Counter(record.get("status", "") for record in ue_anchor_signatures)),
        "ueAnchorSignatureGroupCounts": dict(sorted(ue_anchor_signature_group_counts.items())),
        "resolvedUeAnchorSignatureGroupCounts": dict(sorted(resolved_ue_anchor_signature_group_counts.items())),
        "ueCandidateGlobalCount": len(ue_candidate_globals),
        "addedUeCandidateGlobalCount": len(added_ue_candidate_globals),
        "ueCandidateGlobalStatusCounts": dict(Counter(record.get("status", "") for record in ue_candidate_globals)),
        "ueRuntimeDiscovery": ue_runtime_discovery,
        "ueRuntimeDiscoveryReady": ue_runtime_discovery["ready"],
        "ueRuntimeDiscoveryFailure": ue_runtime_discovery["failure"],
        "ueRuntimeDiscoveryStartCount": ue_runtime_discovery["startCount"],
        "ueRuntimeDiscoveryFinishCount": ue_runtime_discovery["finishCount"],
        "ueRuntimeDiscoveryCandidateCount": ue_runtime_discovery["candidateCount"],
        "uePointerCount": len(ue_pointers),
        "mappedUePointerCount": len(mapped_ue_pointers),
        "ueLayoutCount": len(ue_layouts),
        "readableUeLayoutCount": len(readable_ue_layouts),
        "ueLayoutSlotCount": len(ue_layout_slots),
        "mappedUeLayoutSlotCount": len(mapped_ue_layout_slots),
        "ueUObjectCount": len(ue_uobjects),
        "candidateUeUObjectCount": len(candidate_ue_uobjects),
        "classMappedUeUObjectCount": len(class_mapped_ue_uobjects),
        "ueReflectionCount": len(ue_reflections),
        "classMappedUeReflectionCount": len(class_mapped_ue_reflections),
        "ueReflectionSlotCount": len(ue_reflection_slots),
        "mappedUeReflectionSlotCount": len(mapped_ue_reflection_slots),
        "ueReflectionFieldCount": len(ue_reflection_fields),
        "candidateUeReflectionFieldCount": len(candidate_ue_reflection_fields),
        "classMappedUeReflectionFieldCount": len(class_mapped_ue_reflection_fields),
        "ueReflectionPropertyCount": len(ue_reflection_properties),
        "candidateUeReflectionPropertyCount": len(candidate_ue_reflection_properties),
        "readableUeReflectionPropertyCount": len(readable_ue_reflection_properties),
        "runtimeUeReflectionPropertyCount": len(runtime_ue_reflection_properties),
        "runtimeReadableUeReflectionPropertyCount": len(runtime_readable_ue_reflection_properties),
        "ueReflectionValueCount": len(ue_reflection_values),
        "readUeReflectionValueCount": len(read_ue_reflection_values),
        "runtimeReadUeReflectionValueCount": len(runtime_read_ue_reflection_values),
        "runtimeDescriptorMatchedReadUeReflectionValueCount": len(runtime_descriptor_matched_read_ue_reflection_values),
        "ueFunctionParamRootCount": len(ue_function_param_roots),
        "rootedUeFunctionParamRootCount": len(rooted_ue_function_param_roots),
        "ueFunctionParamCount": len(ue_function_params),
        "candidateUeFunctionParamCount": len(candidate_ue_function_params),
        "ueFunctionParamContainerChildCount": len(ue_function_param_container_children),
        "ueFunctionNativeIdentityCount": len(ue_function_native_identities),
        "promotedUeFunctionNativeIdentityCount": len(promoted_ue_function_native_identities),
        "readableFlagUeFunctionNativeIdentityCount": len(readable_flag_ue_function_native_identities),
        "runtimePathUeFunctionNativeIdentityCount": len(runtime_path_ue_function_native_identities),
        "ue4ssPathUeFunctionNativeIdentityCount": len(ue4ss_path_ue_function_native_identities),
        "candidateUeFunctionParamContainerChildCount": len(candidate_ue_function_param_container_children),
        "decodedUeFunctionParamContainerChildCount": len(decoded_ue_function_param_container_children),
        "readableUeFunctionParamCount": len(readable_ue_function_params),
        "namedUeFunctionParamCount": len(named_ue_function_params),
        "uniqueUeFunctionPathCount": len(ue_function_paths),
        "ueFunctionPaths": ue_function_paths,
        "uniqueUe4ssFunctionPathCount": len(ue4ss_function_paths),
        "ue4ssFunctionPaths": ue4ss_function_paths,
        "readableUeFunctionFlagRootCount": len(readable_ue_function_flag_roots),
        "readableUeFunctionFlagParamCount": len(readable_ue_function_flag_params),
        "ueFunctionFlagPathCount": len(ue_function_flag_paths),
        "ueFunctionFlagPaths": ue_function_flag_paths,
        "ueFunctionFlagValues": ue_function_flag_values,
        "hookDispatchCount": len(hook_dispatches),
        "hookSelfTestCount": len(hook_self_tests),
        "passedHookSelfTestCount": len(passed_hook_self_tests),
        "modSelfTestCount": len(mod_self_tests),
        "passedModSelfTestCount": len(passed_mod_self_tests),
        "luaSelfTestCount": len(lua_self_tests),
        "passedLuaSelfTestCount": len(passed_lua_self_tests),
        "passedLuaCallbackSelfTestCount": len(passed_lua_callback_self_tests),
        "passedLuaApiSelfTestCount": len(passed_lua_api_self_tests),
        "passedLuaSchedulerApiSelfTestCount": len(passed_lua_scheduler_api_self_tests),
        "passedLuaInputCommandApiSelfTestCount": len(passed_lua_input_command_api_self_tests),
        "passedLuaObjectApiSelfTestCount": len(passed_lua_object_api_self_tests),
        "luaReflectionSelfTestCount": len(lua_reflection_self_tests),
        "passedLuaReflectionSelfTestCount": len(passed_lua_reflection_self_tests),
        "rawSetLuaReflectionSelfTestCount": len(raw_set_lua_reflection_self_tests),
        "namedLuaReflectionSelfTestCount": len(named_lua_reflection_self_tests),
        "numericLuaReflectionSelfTestCount": len(numeric_lua_reflection_self_tests),
        "nameTextLuaReflectionSelfTestCount": len(name_text_lua_reflection_self_tests),
        "arrayInnerLuaReflectionSelfTestCount": len(array_inner_lua_reflection_self_tests),
        "enumLuaReflectionSelfTestCount": len(enum_lua_reflection_self_tests),
        "containerLuaReflectionSelfTestCount": len(container_lua_reflection_self_tests),
        "importTextLuaReflectionSelfTestCount": len(import_text_lua_reflection_self_tests),
        "exportTextLuaReflectionSelfTestCount": len(export_text_lua_reflection_self_tests),
        "propertyMetadataLuaReflectionSelfTestCount": len(property_metadata_lua_reflection_self_tests),
        "descriptorValueLuaReflectionSelfTestCount": len(descriptor_value_lua_reflection_self_tests),
        "reflectionForEachPropertyLuaReflectionSelfTestCount": len(reflection_for_each_property_lua_reflection_self_tests),
        "runtimeReflectionForEachPropertyLuaReflectionSelfTestCount": len(runtime_reflection_for_each_property_lua_reflection_self_tests),
        "selfTestReflectionForEachPropertyLuaReflectionSelfTestCount": len(self_test_reflection_for_each_property_lua_reflection_self_tests),
        "typedLiveDescriptorLuaReflectionSelfTestCount": len(typed_live_descriptor_lua_reflection_self_tests),
        "runtimeTypedLiveDescriptorLuaReflectionSelfTestCount": len(runtime_typed_live_descriptor_lua_reflection_self_tests),
        "selfTestTypedLiveDescriptorLuaReflectionSelfTestCount": len(self_test_typed_live_descriptor_lua_reflection_self_tests),
        "typedLiveDescriptorValueLuaReflectionSelfTestCount": len(typed_live_descriptor_value_lua_reflection_self_tests),
        "runtimeTypedLiveDescriptorValueLuaReflectionSelfTestCount": len(runtime_typed_live_descriptor_value_lua_reflection_self_tests),
        "selfTestTypedLiveDescriptorValueLuaReflectionSelfTestCount": len(self_test_typed_live_descriptor_value_lua_reflection_self_tests),
        "typedLiveDescriptorValueSetLuaReflectionSelfTestCount": len(typed_live_descriptor_value_set_lua_reflection_self_tests),
        "runtimeTypedLiveDescriptorValueSetLuaReflectionSelfTestCount": len(runtime_typed_live_descriptor_value_set_lua_reflection_self_tests),
        "selfTestTypedLiveDescriptorValueSetLuaReflectionSelfTestCount": len(self_test_typed_live_descriptor_value_set_lua_reflection_self_tests),
        "liveDescriptorValueLuaReflectionSelfTestCount": len(live_descriptor_value_lua_reflection_self_tests),
        "runtimeLiveDescriptorValueLuaReflectionSelfTestCount": len(runtime_live_descriptor_value_lua_reflection_self_tests),
        "selfTestLiveDescriptorValueLuaReflectionSelfTestCount": len(self_test_live_descriptor_value_lua_reflection_self_tests),
        "luaProcessEventSelfTestCount": len(lua_process_event_self_tests),
        "passedLuaProcessEventSelfTestCount": len(passed_lua_process_event_self_tests),
        "luaProcessEventParamAccessorSelfTestCount": len(lua_process_event_param_accessor_self_tests),
        "luaProcessEventFunctionParamMethodSelfTestCount": len(lua_process_event_function_param_method_self_tests),
        "luaProcessEventFunctionParamLookupMethodSelfTestCount": len(lua_process_event_function_param_lookup_method_self_tests),
        "luaProcessEventFunctionParamIterationMethodSelfTestCount": len(lua_process_event_function_param_iteration_method_self_tests),
        "luaProcessEventContainerAliasMethodSelfTestCount": len(lua_process_event_container_alias_method_self_tests),
        "luaProcessEventContainerStorageLayoutMethodSelfTestCount": len(lua_process_event_container_storage_layout_method_self_tests),
        "luaProcessEventScalarParamAccessorSelfTestCount": len(lua_process_event_scalar_param_accessor_self_tests),
        "luaProcessEventNameStringParamAccessorSelfTestCount": len(lua_process_event_name_string_param_accessor_self_tests),
        "luaProcessEventStructParamAccessorSelfTestCount": len(lua_process_event_struct_param_accessor_self_tests),
        "luaProcessEventEnumParamAccessorSelfTestCount": len(lua_process_event_enum_param_accessor_self_tests),
        "luaProcessEventObjectParamAccessorSelfTestCount": len(lua_process_event_object_param_accessor_self_tests),
        "luaProcessEventBoolParamAccessorSelfTestCount": len(lua_process_event_bool_param_accessor_self_tests),
        "routedLuaProcessEventSelfTestCount": len(routed_lua_process_event_self_tests),
        "luaProcessEventPathExactMatchCount": lua_process_event_path_exact_matches,
        "luaProcessEventPathAliasMatchCount": lua_process_event_path_alias_matches,
        "luaModScriptCount": len(lua_mod_scripts),
        "passedLuaModScriptCount": len(passed_lua_mod_scripts),
        "luaModDispatchSelfTestCount": len(lua_mod_dispatch_self_tests),
        "passedLuaModDispatchSelfTestCount": len(passed_lua_mod_dispatch_self_tests),
        "luaModFinishCount": len(lua_mod_finishes),
        "passedLuaModFinishCount": len(passed_lua_mod_finishes),
        "luaObjectApiModFinishCount": len(lua_object_api_mod_finishes),
        "luaLoadAssetBackendStateModFinishCount": len(lua_load_asset_backend_state_mod_finishes),
        "luaLoadAssetBackendAnchorModFinishCount": len(lua_load_asset_backend_anchor_mod_finishes),
        "luaLoadAssetPackageBridgeStateModFinishCount": len(lua_load_asset_package_bridge_state_mod_finishes),
        "luaLoadAssetPackageNativeInvokeModFinishCount": len(lua_load_asset_package_native_invoke_mod_finishes),
        "luaLoadAssetPackageAbiStateEventCount": len(lua_load_asset_package_abi_state_events),
        "luaLoadAssetPackageStringBridgeEventCount": len(lua_load_asset_package_string_bridge_events),
        "luaLoadAssetPackageNativeBufferEventCount": len(lua_load_asset_package_native_buffer_events),
        "luaLoadAssetPackageTCharBufferEventCount": len(lua_load_asset_package_tchar_buffer_events),
        "luaLoadAssetPackageTCharVerificationEventCount": len(lua_load_asset_package_tchar_verification_events),
        "luaLoadAssetPackageCallFrameEventCount": len(lua_load_asset_package_call_frame_events),
        "luaLoadAssetPackageCallFrameVerificationEventCount": len(lua_load_asset_package_call_frame_verification_events),
        "luaLoadAssetPackageCrashGuardEventCount": len(lua_load_asset_package_crash_guard_events),
        "luaLoadAssetPackageGuardedCallEventCount": len(lua_load_asset_package_guarded_call_events),
        "luaLoadAssetPackageReturnValidationEventCount": len(lua_load_asset_package_return_validation_events),
        "luaLoadAssetPackageNativeCallAdapterEventCount": len(lua_load_asset_package_native_call_adapter_events),
        "luaLoadAssetPackageInvocationDescriptorEventCount": len(lua_load_asset_package_invocation_descriptor_events),
        "luaLoadAssetPackageNativeExecutorEventCount": len(lua_load_asset_package_native_executor_events),
        "luaLoadAssetPackageNativeExecutorReadyEventCount": len(
            lua_load_asset_package_native_executor_ready_events
        ),
        "luaLoadAssetPackageNativeExecutorTargetReadyEventCount": len(
            lua_load_asset_package_native_executor_target_ready_events
        ),
        "luaLoadAssetPackagePreflightModFinishCount": len(lua_load_asset_package_preflight_mod_finishes),
        "luaLoadAssetPackageModFinishCount": len(lua_load_asset_package_mod_finishes),
        "luaFunctionIterationModFinishCount": len(lua_function_iteration_mod_finishes),
        "luaFunctionIterationCheckCount": len(lua_function_iteration_checks),
        "passedLuaFunctionIterationCheckCount": len(passed_lua_function_iteration_checks),
        "runtimeLuaFunctionIterationCheckCount": len(runtime_lua_function_iteration_checks),
        "selfTestLuaFunctionIterationCheckCount": len(self_test_lua_function_iteration_checks),
        "luaSchedulerApiModFinishCount": len(lua_scheduler_api_mod_finishes),
        "luaInputCommandApiModFinishCount": len(lua_input_command_api_mod_finishes),
        "luaProcessConsoleExecHookModFinishCount": len(lua_process_console_exec_hook_mod_finishes),
        "luaLocalPlayerExecHookModFinishCount": len(lua_local_player_exec_hook_mod_finishes),
        "luaCallFunctionHookModFinishCount": len(lua_call_function_hook_mod_finishes),
        "luaCallFunctionStructuredArgsModFinishCount": len(lua_call_function_structured_args_mod_finishes),
        "luaProcessEventCompatModFinishCount": len(lua_process_event_compat_mod_finishes),
        "luaProcessEventBridgeStateModFinishCount": len(lua_process_event_bridge_state_mod_finishes),
        "luaProcessEventNativeInvokeModFinishCount": (
            len(lua_process_event_native_invoke_mod_finishes)
            + len(lua_process_event_native_invoke_self_tests)
        ),
        "luaProcessEventNativeInvokeSelfTestCount": len(lua_process_event_native_invoke_self_tests),
        "luaProcessEventNativeInvokeNonSelfTestGateCount": len(
            lua_process_event_native_invoke_non_self_test_gates
        ),
        "luaProcessEventNativeInvokeDescriptorPreflightCount": len(
            lua_process_event_native_invoke_descriptor_preflights
        ),
        "luaProcessEventNativeInvokeNonSelfTestInvokedCount": len(
            lua_process_event_native_invoke_non_self_test_invocations
        ),
        "luaProcessEventParamsBufferCount": len(lua_process_event_params_buffers),
        "luaLifecycleHookModFinishCount": len(lua_lifecycle_hook_mod_finishes),
        "luaCustomEventModFinishCount": len(lua_custom_event_mod_finishes),
        "luaLoadMapHookModFinishCount": len(lua_load_map_hook_mod_finishes),
        "luaBeginPlayHookModFinishCount": len(lua_begin_play_hook_mod_finishes),
        "luaInitGameStateHookModFinishCount": len(lua_init_game_state_hook_mod_finishes),
        "luaNotifyOnNewObjectModFinishCount": len(lua_notify_on_new_object_mod_finishes),
        "luaSyntheticOuterModFinishCount": len(lua_synthetic_outer_mod_finishes),
        "luaWorldContextModFinishCount": len(lua_world_context_mod_finishes),
        "luaClassDefaultObjectModFinishCount": len(lua_class_default_object_mod_finishes),
        "luaLevelModFinishCount": len(lua_level_mod_finishes),
        "luaObjectRegistryCount": len(lua_object_registry),
        "addedLuaObjectRegistryCount": len(added_lua_object_registry),
        "luaObjectRegistryCheckCount": len(lua_object_registry_checks),
        "passedLuaObjectRegistryCheckCount": len(passed_lua_object_registry_checks),
        "luaFunctionRegistryCheckCount": len(lua_function_registry_checks),
        "passedLuaFunctionRegistryCheckCount": len(passed_lua_function_registry_checks),
        "runtimeLuaFunctionRegistryCheckCount": len(runtime_lua_function_registry_checks),
        "selfTestLuaFunctionRegistryCheckCount": len(self_test_lua_function_registry_checks),
        "ueLuaObjectRegistryCount": len(ue_lua_object_registry),
        "runtimeUeLuaObjectRegistryCount": len(runtime_ue_lua_object_registry),
        "selfTestUeLuaObjectRegistryCount": len(self_test_ue_lua_object_registry),
        "objectArrayLuaObjectRegistryCount": len(object_array_lua_object_registry),
        "runtimeObjectArrayLuaObjectRegistryCount": len(runtime_object_array_lua_object_registry),
        "selfTestObjectArrayLuaObjectRegistryCount": len(self_test_object_array_lua_object_registry),
        "decodedLuaObjectAliasRegistryCount": len(decoded_lua_object_alias_registry),
        "runtimeDecodedLuaObjectAliasRegistryCount": len(runtime_decoded_lua_object_alias_registry),
        "selfTestDecodedLuaObjectAliasRegistryCount": len(self_test_decoded_lua_object_alias_registry),
        "skippedDecodedLuaObjectAliasRegistryCount": len(skipped_decoded_lua_object_alias_registry),
        "luaObjectOuterChainCount": len(lua_object_outer_chains),
        "resolvedLuaObjectOuterChainCount": len(resolved_lua_object_outer_chains),
        "luaObjectOuterChainIdentityCount": len(lua_object_outer_chain_identities),
        "luaGlobalRuntimeHelperCheckCount": len(lua_global_runtime_helper_checks),
        "passedLuaGlobalRuntimeHelperCheckCount": len(passed_lua_global_runtime_helper_checks),
        "promotedWorldLuaGlobalRuntimeHelperCheckCount": len(promoted_world_lua_global_runtime_helper_checks),
        "promotedEngineLuaGlobalRuntimeHelperCheckCount": len(promoted_engine_lua_global_runtime_helper_checks),
        "ueObjectArrayCount": len(ue_object_arrays),
        "ueObjectArrayFinishCount": len(ue_object_array_finishes),
        "registryUeObjectArrayFinishCount": len(registry_ue_object_array_finishes),
        "ueObjectArrayShapeCount": len(ue_object_array_shapes),
        "plausibleUeObjectArrayShapeCount": len(plausible_ue_object_array_shapes),
        "implausibleUeObjectArrayShapeCount": len(implausible_ue_object_array_shapes),
        "finishedUeObjectArrayCount": len(finished_ue_object_arrays),
        "ueObjectArrayItemCount": len(ue_object_array_items),
        "ueObjectNativeIdentityCount": len(ue_object_native_identities),
        "promotedUeObjectNativeIdentityCount": len(promoted_ue_object_native_identities),
        "decodedNameUeObjectNativeIdentityCount": len(decoded_name_ue_object_native_identities),
        "decodedClassNameUeObjectNativeIdentityCount": len(decoded_class_name_ue_object_native_identities),
        "internalFlagUeObjectArrayItemCount": len(internal_flag_ue_object_array_items),
        "nonzeroInternalFlagUeObjectArrayItemCount": len(nonzero_internal_flag_ue_object_array_items),
        "ueFNameCount": len(ue_fnames),
        "decodedUeFNameCount": len(decoded_ue_fnames),
        "ueFNameFinishCount": len(ue_fname_finishes),
        "readyUeFNameFinishCount": len(ready_ue_fname_finishes),
        "ueProcessEventHookCount": len(ue_process_event_hooks),
        "passedUeProcessEventHookCount": len(passed_ue_process_event_hooks),
        "nonSelfTestPassedUeProcessEventHookCount": len(non_self_test_passed_ue_process_event_hooks),
        "provenTargetPassedUeProcessEventHookCount": len(proven_target_passed_ue_process_event_hooks),
        "ueCallFunctionHookCount": len(ue_call_function_hooks),
        "passedUeCallFunctionHookCount": len(passed_ue_call_function_hooks),
        "nonSelfTestPassedUeCallFunctionHookCount": len(non_self_test_passed_ue_call_function_hooks),
        "provenTargetPassedUeCallFunctionHookCount": len(proven_target_passed_ue_call_function_hooks),
        "ueCallFunctionLiveHookCount": len(ue_call_function_live_hooks),
        "installedUeCallFunctionLiveHookCount": len(installed_ue_call_function_live_hooks),
        "routedUeCallFunctionLiveLuaHookCount": len(routed_ue_call_function_live_lua_hooks),
        "handledUeCallFunctionLiveLuaHookCount": len(handled_ue_call_function_live_lua_hooks),
        "nonSelfTestInstalledUeCallFunctionLiveHookCount": len(non_self_test_installed_ue_call_function_live_hooks),
        "provenTargetInstalledUeCallFunctionLiveHookCount": len(proven_target_installed_ue_call_function_live_hooks),
        "provenTargetRoutedUeCallFunctionLiveLuaHookCount": len(proven_target_routed_ue_call_function_live_lua_hooks),
        "provenTargetHandledUeCallFunctionLiveLuaHookCount": len(proven_target_handled_ue_call_function_live_lua_hooks),
        "ueProcessEventLiveHookCount": len(ue_process_event_live_hooks),
        "installedUeProcessEventLiveHookCount": len(installed_ue_process_event_live_hooks),
        "nonSelfTestInstalledUeProcessEventLiveHookCount": len(non_self_test_installed_ue_process_event_live_hooks),
        "provenTargetInstalledUeProcessEventLiveHookCount": len(proven_target_installed_ue_process_event_live_hooks),
        "ueProcessEventLiveContextCount": len(ue_process_event_live_contexts),
        "resolvedUeProcessEventLiveContextCount": len(resolved_ue_process_event_live_contexts),
        "matchedUeProcessEventLiveContextCount": len(matched_ue_process_event_live_contexts),
        "runtimeMatchedUeProcessEventLiveContextCount": len(runtime_matched_ue_process_event_live_contexts),
        "selfTestProvenanceUeProcessEventLiveContextCount": len(self_test_provenance_ue_process_event_live_contexts),
        "runtimeProvenanceUeProcessEventLiveContextCount": len(runtime_provenance_ue_process_event_live_contexts),
        "ueProcessEventLiveRegistryContextCount": len(ue_process_event_live_registry_contexts),
        "resolvedUeProcessEventLiveRegistryContextCount": len(resolved_ue_process_event_live_registry_contexts),
        "nativeIdentityUeProcessEventLiveRegistryContextCount": len(native_identity_ue_process_event_live_registry_contexts),
        "matchedUeProcessEventLiveRegistryContextCount": len(matched_ue_process_event_live_registry_contexts),
        "runtimeMatchedUeProcessEventLiveRegistryContextCount": len(runtime_matched_ue_process_event_live_registry_contexts),
        "selfTestProvenanceUeProcessEventLiveRegistryContextCount": len(self_test_provenance_ue_process_event_live_registry_contexts),
        "runtimeProvenanceUeProcessEventLiveRegistryContextCount": len(runtime_provenance_ue_process_event_live_registry_contexts),
        "ueProcessEventLiveParamCount": len(ue_process_event_live_params),
        "readUeProcessEventLiveParamCount": len(read_ue_process_event_live_params),
        "rawUeProcessEventLiveParamCount": len(raw_ue_process_event_live_params),
        "containerUeProcessEventLiveParamCount": len(container_ue_process_event_live_params),
        "sampledContainerUeProcessEventLiveParamCount": len(sampled_container_ue_process_event_live_params),
        "arrayContainerUeProcessEventLiveParamCount": len(array_container_ue_process_event_live_params),
        "setContainerUeProcessEventLiveParamCount": len(set_container_ue_process_event_live_params),
        "mapContainerUeProcessEventLiveParamCount": len(map_container_ue_process_event_live_params),
        "setMapContainerUeProcessEventLiveParamCount": len(set_map_container_ue_process_event_live_params),
        "runtimeReadUeProcessEventLiveParamCount": len(runtime_read_ue_process_event_live_params),
        "runtimeRawUeProcessEventLiveParamCount": len(runtime_raw_ue_process_event_live_params),
        "runtimeContainerUeProcessEventLiveParamCount": len(runtime_container_ue_process_event_live_params),
        "runtimeSampledContainerUeProcessEventLiveParamCount": len(runtime_sampled_container_ue_process_event_live_params),
        "runtimeArrayContainerUeProcessEventLiveParamCount": len(runtime_array_container_ue_process_event_live_params),
        "runtimeSetContainerUeProcessEventLiveParamCount": len(runtime_set_container_ue_process_event_live_params),
        "runtimeMapContainerUeProcessEventLiveParamCount": len(runtime_map_container_ue_process_event_live_params),
        "runtimeSetMapContainerUeProcessEventLiveParamCount": len(runtime_set_map_container_ue_process_event_live_params),
        "ueProcessEventLuaContextHandleCount": len(ue_process_event_lua_context_handle_hooks),
        "ueProcessEventLiveLuaParamAccessorCount": len(ue_process_event_live_lua_param_accessor_hooks),
        "ueProcessEventLiveLuaFunctionParamMethodCount": len(ue_process_event_live_lua_function_param_method_hooks),
        "ueProcessEventLiveLuaFunctionParamLookupMethodCount": len(ue_process_event_live_lua_function_param_lookup_method_hooks),
        "ueProcessEventLiveLuaFunctionParamIterationMethodCount": len(ue_process_event_live_lua_function_param_iteration_method_hooks),
        "ueProcessEventLiveLuaContainerAliasMethodCount": len([
            record for record in installed_ue_process_event_live_hooks
            if process_event_container_alias_methods_passed(record, prefix="lua")
        ]),
        "ueProcessEventLiveLuaContainerStorageLayoutMethodCount": len(ue_process_event_live_lua_container_storage_layout_method_hooks),
        "ueProcessEventLiveLuaScalarParamAccessorCount": len(ue_process_event_live_lua_scalar_param_accessor_hooks),
        "ueProcessEventLiveLuaNameStringParamAccessorCount": len(ue_process_event_live_lua_name_string_param_accessor_hooks),
        "ueProcessEventLiveLuaStructParamAccessorCount": len(ue_process_event_live_lua_struct_param_accessor_hooks),
        "ueProcessEventLiveLuaEnumParamAccessorCount": len(ue_process_event_live_lua_enum_param_accessor_hooks),
        "ueProcessEventLiveLuaObjectParamAccessorCount": len(ue_process_event_live_lua_object_param_accessor_hooks),
        "ueProcessEventLiveLuaBoolParamAccessorCount": len(ue_process_event_live_lua_bool_param_accessor_hooks),
        "routedUeProcessEventLiveLuaHookCount": len(routed_ue_process_event_live_lua_hooks),
        "restoredUeProcessEventLiveHookCount": len(restored_ue_process_event_live_hooks),
        "ueProcessEventLiveHookStatusCounts": dict(Counter(record.get("status", "") for record in ue_process_event_live_hooks)),
        "ueCallFunctionLiveHookStatusCounts": dict(Counter(record.get("status", "") for record in ue_call_function_live_hooks)),
        "ueProcessEventDispatchSelfTestCount": len(ue_process_event_dispatch_self_tests),
        "armedUeProcessEventDispatchSelfTestCount": len(armed_ue_process_event_dispatch_self_tests),
        "ueProcessEventLiveLuaDispatchCount": len(ue_process_event_live_lua_dispatches),
        "armedUeProcessEventLiveLuaDispatchCount": len(armed_ue_process_event_live_lua_dispatches),
        "multiHookUeProcessEventLiveLuaDispatchCount": len(multi_hook_ue_process_event_live_lua_dispatches),
        "matchedUeProcessEventLiveLuaDispatchCount": len(matched_ue_process_event_live_lua_dispatches),
        "closedUeProcessEventLiveLuaDispatchCount": len(closed_ue_process_event_live_lua_dispatches),
        "closedMatchedUeProcessEventLiveLuaDispatchCount": len(closed_matched_ue_process_event_live_lua_dispatches),
        "ueProcessEventLiveLuaPathExactMatchCount": ue_process_event_live_lua_path_exact_matches,
        "ueProcessEventLiveLuaPathAliasMatchCount": ue_process_event_live_lua_path_alias_matches,
        "ueProcessEventLiveLuaDispatchStatusCounts": dict(Counter(record.get("status", "") for record in ue_process_event_live_lua_dispatches)),
        "uniqueHitCount": len(hits_by_name),
        "forwardSmokeCount": len(forward_smokes),
        "loaders": sorted(set(record.get("loader", process_label(record)) for record in loaded + hits)),
        "pids": sorted(set(record.get("pid", "") for record in loaded + hits if record.get("pid"))),
        "loaded": loaded,
        "modules": module_paths,
        "scanStarts": starts,
        "scanFinishes": finishes,
        "scanSkips": skips,
        "ueAnchors": ue_anchors,
        "ueAnchorSignatures": ue_anchor_signatures,
        "ueRuntimeDiscoveryRecords": ue_runtime_discovery_records,
        "uePointers": ue_pointers,
        "uePointersByName": dict(sorted(pointers_by_name.items())),
        "ueLayouts": ue_layouts,
        "ueLayoutsByName": dict(sorted(layouts_by_name.items())),
        "ueLayoutSlots": ue_layout_slots,
        "ueLayoutSlotsByName": dict(sorted(layout_slots_by_name.items())),
        "ueUObjects": ue_uobjects,
        "ueUObjectsByName": dict(sorted(uobjects_by_name.items())),
        "ueReflectionFields": ue_reflection_fields,
        "ueReflectionProperties": ue_reflection_properties,
        "ueReflectionValues": ue_reflection_values,
        "ueFunctionParamRoots": ue_function_param_roots,
        "ueFunctionParams": ue_function_params,
        "ueFunctionParamContainerChildren": ue_function_param_container_children,
        "ueFunctionNativeIdentities": ue_function_native_identities,
        "hookDispatches": hook_dispatches,
        "hookSelfTests": hook_self_tests,
        "modSelfTests": mod_self_tests,
        "luaSelfTests": lua_self_tests,
        "luaReflectionSelfTests": lua_reflection_self_tests,
        "luaProcessEventSelfTests": lua_process_event_self_tests,
        "luaModScripts": lua_mod_scripts,
        "luaModDispatchSelfTests": lua_mod_dispatch_self_tests,
        "luaModFinishes": lua_mod_finishes,
        "luaObjectRegistry": lua_object_registry,
        "luaObjectOuterChains": lua_object_outer_chains,
        "ueObjectArrays": ue_object_arrays,
        "ueObjectArrayShapes": ue_object_array_shapes,
        "ueObjectArrayItems": ue_object_array_items,
        "ueObjectNativeIdentities": ue_object_native_identities,
        "ueFNames": ue_fnames,
        "ueProcessEventHooks": ue_process_event_hooks,
        "ueCallFunctionHooks": ue_call_function_hooks,
        "ueCallFunctionLiveHooks": ue_call_function_live_hooks,
        "ueProcessEventLiveHooks": ue_process_event_live_hooks,
        "ueProcessEventLiveContexts": ue_process_event_live_contexts,
        "ueProcessEventLiveRegistryContexts": ue_process_event_live_registry_contexts,
        "ueProcessEventLiveParams": ue_process_event_live_params,
        "ueProcessEventDispatchSelfTests": ue_process_event_dispatch_self_tests,
        "ueProcessEventLiveLuaDispatches": ue_process_event_live_lua_dispatches,
        "ueFNamesByObjectName": dict(sorted(fnames_by_object_name.items())),
        "forwardSmokes": forward_smokes,
        "categories": dict(sorted(categories.items())),
        "expected": expected_status,
        "missingExpected": [name for name, status in expected_status.items() if not status["present"]],
        "hitsByName": hits_by_name,
    }


def markdown(summary, top):
    lines = []
    lines.append("# Client Loader Scan Summary")
    lines.append("")
    lines.append(f"- Loaders: `{', '.join(summary['loaders']) or 'unknown'}`")
    lines.append(f"- PIDs: `{', '.join(summary['pids']) or 'none'}`")
    lines.append(f"- Loaded events: `{summary['loadCount']}`")
    lines.append(f"- Module events: `{summary['moduleCount']}`")
    lines.append(f"- Scan starts: `{summary['scanStartCount']}`")
    lines.append(f"- Scan finishes: `{summary['scanFinishCount']}`")
    lines.append(f"- Hit count: `{summary['hitCount']}`")
    if summary["ueAnchorCount"]:
        lines.append(
            f"- UE anchors: `{summary['mappedUeAnchorCount']}/{summary['ueAnchorCount']}` mapped "
            f"groups={summary['ueAnchorGroupCounts']}"
        )
    if summary["ueAnchorSignatureCount"]:
        lines.append(
            f"- UE anchor signatures: `{summary['resolvedUeAnchorSignatureCount']}/{summary['ueAnchorSignatureCount']}` "
            f"resolved status={summary['ueAnchorSignatureStatusCounts']} "
            f"groups={summary['ueAnchorSignatureGroupCounts']}"
        )
    if summary["ueCandidateGlobalCount"]:
        lines.append(
            f"- UE candidate globals: `{summary['addedUeCandidateGlobalCount']}/{summary['ueCandidateGlobalCount']}` "
            f"added status={summary['ueCandidateGlobalStatusCounts']}"
        )
    if summary["ueRuntimeDiscoveryStartCount"] or summary["ueRuntimeDiscoveryFinishCount"]:
        discovery = summary["ueRuntimeDiscovery"]
        lines.append(
            "- UE runtime discovery: "
            f"ready=`{str(discovery['ready']).lower()}` "
            f"failure=`{discovery['failure'] or 'none'}` "
            f"promoted={discovery['promotedNames']} "
            f"coverage={discovery['coverage']} "
            f"status={discovery['statusCounts']}"
        )
    if summary["uePointerCount"]:
        lines.append(f"- UE pointers: `{summary['mappedUePointerCount']}/{summary['uePointerCount']}` target-mapped")
    if summary["ueLayoutCount"] or summary["ueLayoutSlotCount"]:
        lines.append(
            f"- UE layouts: `{summary['readableUeLayoutCount']}/{summary['ueLayoutCount']}` readable, "
            f"slots `{summary['mappedUeLayoutSlotCount']}/{summary['ueLayoutSlotCount']}` target-mapped"
        )
    if summary["ueUObjectCount"]:
        lines.append(
            f"- UE UObject candidates: `{summary['candidateUeUObjectCount']}/{summary['ueUObjectCount']}` "
            f"candidates, class-mapped `{summary['classMappedUeUObjectCount']}`"
        )
    if summary["ueProcessEventHookCount"]:
        lines.append(
            f"- UE ProcessEvent hook probes: "
            f"`{summary['passedUeProcessEventHookCount']}/{summary['ueProcessEventHookCount']}` passed"
        )
    if summary["ueCallFunctionHookCount"]:
        lines.append(
            f"- UE CallFunctionByNameWithArguments hook probes: "
            f"`{summary['passedUeCallFunctionHookCount']}/{summary['ueCallFunctionHookCount']}` passed"
        )
    if summary["ueCallFunctionLiveHookCount"]:
        lines.append(
            f"- UE CallFunctionByNameWithArguments live hooks: "
            f"`{summary['installedUeCallFunctionLiveHookCount']}/{summary['ueCallFunctionLiveHookCount']}` installed, "
            f"Lua routed `{summary['routedUeCallFunctionLiveLuaHookCount']}`, "
            f"Lua handled `{summary['handledUeCallFunctionLiveLuaHookCount']}`, "
            f"status={summary['ueCallFunctionLiveHookStatusCounts']}"
        )
    if summary["ueProcessEventLiveHookCount"]:
        lines.append(
            f"- UE ProcessEvent live hooks: "
            f"`{summary['installedUeProcessEventLiveHookCount']}/{summary['ueProcessEventLiveHookCount']}` installed, "
            f"Lua context handles `{summary['ueProcessEventLuaContextHandleCount']}`, "
            f"function-descriptor Lua params accessors `{summary['ueProcessEventLiveLuaParamAccessorCount']}`, "
            f"matched live function contexts `{summary['matchedUeProcessEventLiveContextCount']}`, "
            f"restored `{summary['restoredUeProcessEventLiveHookCount']}` "
            f"status={summary['ueProcessEventLiveHookStatusCounts']}"
        )
    if summary["ueProcessEventDispatchSelfTestCount"]:
        lines.append(
            f"- UE ProcessEvent dispatch self-tests: "
            f"`{summary['armedUeProcessEventDispatchSelfTestCount']}/{summary['ueProcessEventDispatchSelfTestCount']}` armed"
        )
    if summary["ueProcessEventLiveLuaDispatchCount"]:
        lines.append(
            f"- UE ProcessEvent live Lua dispatch: "
            f"`{summary['armedUeProcessEventLiveLuaDispatchCount']}/{summary['ueProcessEventLiveLuaDispatchCount']}` armed, "
            f"matched `{summary['matchedUeProcessEventLiveLuaDispatchCount']}`, "
            f"closed `{summary['closedUeProcessEventLiveLuaDispatchCount']}` "
            f"closedMatched `{summary['closedMatchedUeProcessEventLiveLuaDispatchCount']}` "
            f"path exact `{summary['ueProcessEventLiveLuaPathExactMatchCount']}` "
            f"path alias `{summary['ueProcessEventLiveLuaPathAliasMatchCount']}` "
            f"status={summary['ueProcessEventLiveLuaDispatchStatusCounts']}"
        )
    if summary["hookSelfTestCount"]:
        lines.append(
            f"- Hook dispatch self-tests: `{summary['passedHookSelfTestCount']}/{summary['hookSelfTestCount']}` passed"
        )
    if summary["modSelfTestCount"]:
        lines.append(
            f"- Mod dispatch self-tests: `{summary['passedModSelfTestCount']}/{summary['modSelfTestCount']}` passed"
        )
    if summary["luaSelfTestCount"]:
        lines.append(
            f"- Lua dispatch self-tests: `{summary['passedLuaSelfTestCount']}/{summary['luaSelfTestCount']}` passed, "
            f"callback bridge `{summary['passedLuaCallbackSelfTestCount']}`, "
            f"api surface `{summary['passedLuaApiSelfTestCount']}`, "
            f"scheduler API `{summary['passedLuaSchedulerApiSelfTestCount']}`, "
            f"input/command API `{summary['passedLuaInputCommandApiSelfTestCount']}`, "
            f"object API `{summary['passedLuaObjectApiSelfTestCount']}`"
        )
    if summary["luaReflectionSelfTestCount"]:
        detail = f"`{summary['passedLuaReflectionSelfTestCount']}/{summary['luaReflectionSelfTestCount']}` passed"
        if summary.get("namedLuaReflectionSelfTestCount", 0):
            detail += f", named-property `{summary['namedLuaReflectionSelfTestCount']}`"
        if summary.get("rawSetLuaReflectionSelfTestCount", 0):
            detail += f", raw-set `{summary['rawSetLuaReflectionSelfTestCount']}`"
        if summary.get("numericLuaReflectionSelfTestCount", 0):
            detail += f", numeric-values `{summary['numericLuaReflectionSelfTestCount']}`"
        if summary.get("nameTextLuaReflectionSelfTestCount", 0):
            detail += f", name-text-values `{summary['nameTextLuaReflectionSelfTestCount']}`"
        if summary.get("arrayInnerLuaReflectionSelfTestCount", 0):
            detail += f", array-inner `{summary['arrayInnerLuaReflectionSelfTestCount']}`"
        if summary.get("enumLuaReflectionSelfTestCount", 0):
            detail += f", enum-property `{summary['enumLuaReflectionSelfTestCount']}`"
        if summary.get("containerLuaReflectionSelfTestCount", 0):
            detail += f", container-property `{summary['containerLuaReflectionSelfTestCount']}`"
        if summary.get("importTextLuaReflectionSelfTestCount", 0):
            detail += f", import-text `{summary['importTextLuaReflectionSelfTestCount']}`"
        if summary.get("exportTextLuaReflectionSelfTestCount", 0):
            detail += f", export-text `{summary['exportTextLuaReflectionSelfTestCount']}`"
        if summary.get("propertyMetadataLuaReflectionSelfTestCount", 0):
            detail += f", property-metadata `{summary['propertyMetadataLuaReflectionSelfTestCount']}`"
        if summary.get("descriptorValueLuaReflectionSelfTestCount", 0):
            detail += f", descriptor-values `{summary['descriptorValueLuaReflectionSelfTestCount']}`"
        lines.append(f"- Lua reflection self-tests: {detail}")
    if summary["ueReflectionCount"]:
        lines.append(
            f"- UE reflection probes: "
            f"`{summary['classMappedUeReflectionCount']}/{summary['ueReflectionCount']}` class-mapped, "
            f"slots `{summary['mappedUeReflectionSlotCount']}/{summary['ueReflectionSlotCount']}` mapped"
        )
    if summary["ueReflectionFieldCount"]:
        lines.append(
            f"- UE reflection fields: candidates "
            f"`{summary['candidateUeReflectionFieldCount']}/{summary['ueReflectionFieldCount']}`, "
            f"class-mapped `{summary['classMappedUeReflectionFieldCount']}`"
        )
    if summary["ueReflectionPropertyCount"]:
        lines.append(
            f"- UE reflection properties: candidates "
            f"`{summary['candidateUeReflectionPropertyCount']}/{summary['ueReflectionPropertyCount']}`, "
            f"readable descriptors `{summary['readableUeReflectionPropertyCount']}`"
        )
    if summary["ueReflectionValueCount"]:
        lines.append(
            f"- UE reflection values: read "
            f"`{summary['readUeReflectionValueCount']}/{summary['ueReflectionValueCount']}`"
        )
    if summary["ueFunctionParamRootCount"] or summary["ueFunctionParamCount"]:
        lines.append(
            f"- UE function params: roots "
            f"`{summary['rootedUeFunctionParamRootCount']}/{summary['ueFunctionParamRootCount']}`, "
            f"descriptors `{summary['readableUeFunctionParamCount']}/{summary['ueFunctionParamCount']}` readable, "
            f"flags roots `{summary['readableUeFunctionFlagRootCount']}`, "
            f"flags descriptors `{summary['readableUeFunctionFlagParamCount']}`, "
            f"UE4SS path hints `{summary['uniqueUe4ssFunctionPathCount']}`"
        )
    if summary["ueFunctionNativeIdentityCount"]:
        lines.append(
            "- UE function native identities: "
            f"`{summary['promotedUeFunctionNativeIdentityCount']}/{summary['ueFunctionNativeIdentityCount']}` promoted, "
            f"flags `{summary['readableFlagUeFunctionNativeIdentityCount']}`, "
            f"runtime paths `{summary['runtimePathUeFunctionNativeIdentityCount']}`, "
            f"UE4SS paths `{summary['ue4ssPathUeFunctionNativeIdentityCount']}`"
        )
    if summary["luaProcessEventSelfTestCount"]:
        lines.append(
            f"- Lua ProcessEvent self-tests: "
            f"`{summary['passedLuaProcessEventSelfTestCount']}/{summary['luaProcessEventSelfTestCount']}` passed, "
            f"path exact `{summary['luaProcessEventPathExactMatchCount']}`, "
            f"path alias `{summary['luaProcessEventPathAliasMatchCount']}`"
        )
    if summary["luaModScriptCount"] or summary["luaModFinishCount"]:
        lines.append(
            f"- Lua mod entrypoints: scripts `{summary['passedLuaModScriptCount']}/{summary['luaModScriptCount']}` passed, "
            f"dispatch `{summary['passedLuaModDispatchSelfTestCount']}/{summary['luaModDispatchSelfTestCount']}`, "
            f"finishes `{summary['passedLuaModFinishCount']}/{summary['luaModFinishCount']}`, "
            f"object API `{summary['luaObjectApiModFinishCount']}`, "
            f"scheduler API mods `{summary['luaSchedulerApiModFinishCount']}`, "
            f"input/command API mods `{summary['luaInputCommandApiModFinishCount']}`, "
            f"function iteration `{summary['luaFunctionIterationModFinishCount']}`, "
            f"console exec hooks `{summary['luaProcessConsoleExecHookModFinishCount']}`, "
            f"local player exec hooks `{summary['luaLocalPlayerExecHookModFinishCount']}`, "
            f"call function hooks `{summary['luaCallFunctionHookModFinishCount']}`, "
            f"call function structured args `{summary['luaCallFunctionStructuredArgsModFinishCount']}`, "
            f"process event compat `{summary['luaProcessEventCompatModFinishCount']}`, "
            f"process event bridge state `{summary['luaProcessEventBridgeStateModFinishCount']}`, "
            f"process event native invoke `{summary['luaProcessEventNativeInvokeSelfTestCount']}`, "
            f"process event native non-self-test gate `{summary['luaProcessEventNativeInvokeNonSelfTestGateCount']}`, "
            f"process event params buffers `{summary['luaProcessEventParamsBufferCount']}`, "
            f"lifecycle hooks `{summary['luaLifecycleHookModFinishCount']}`, "
            f"object notify `{summary['luaNotifyOnNewObjectModFinishCount']}`, "
            f"synthetic outer `{summary['luaSyntheticOuterModFinishCount']}`, "
            f"world context `{summary['luaWorldContextModFinishCount']}`, "
            f"class default object `{summary['luaClassDefaultObjectModFinishCount']}`, "
            f"level `{summary['luaLevelModFinishCount']}`"
        )
    if summary["luaObjectRegistryCount"]:
        lines.append(
            f"- Lua object registry: `{summary['addedLuaObjectRegistryCount']}/{summary['luaObjectRegistryCount']}` added, "
            f"UE candidates `{summary['ueLuaObjectRegistryCount']}`, "
            f"object-array candidates `{summary['objectArrayLuaObjectRegistryCount']}`, "
            f"decoded aliases `{summary['decodedLuaObjectAliasRegistryCount']}`"
        )
    if summary["ueObjectArrayCount"]:
        lines.append(
            f"- UE object arrays: `{summary['finishedUeObjectArrayCount']}/{summary['ueObjectArrayCount']}` finished"
        )
    if summary["ueObjectArrayShapeCount"]:
        lines.append(
            "- UE object-array shapes: "
            f"`{summary['plausibleUeObjectArrayShapeCount']}` plausible, "
            f"`{summary['implausibleUeObjectArrayShapeCount']}` implausible"
        )
    if summary["ueObjectArrayItemCount"]:
        lines.append(
            "- UE object-array internal flags: "
            f"`{summary['internalFlagUeObjectArrayItemCount']}/{summary['ueObjectArrayItemCount']}` readable, "
            f"`{summary['nonzeroInternalFlagUeObjectArrayItemCount']}` nonzero"
        )
    if summary["ueObjectNativeIdentityCount"]:
        lines.append(
            "- UE object native identities: "
            f"`{summary['promotedUeObjectNativeIdentityCount']}/{summary['ueObjectNativeIdentityCount']}` promoted, "
            f"decoded names `{summary['decodedNameUeObjectNativeIdentityCount']}`, "
            f"decoded classes `{summary['decodedClassNameUeObjectNativeIdentityCount']}`"
        )
    if summary["ueFNameCount"]:
        lines.append(
            f"- UE FName decodes: `{summary['decodedUeFNameCount']}/{summary['ueFNameCount']}` decoded"
        )
    lines.append(f"- Unique names: `{summary['uniqueHitCount']}`")
    if summary["forwardSmokeCount"]:
        lines.append(f"- Forward smokes: `{summary['forwardSmokeCount']}`")
    if summary["missingExpected"]:
        lines.append(f"- Missing expected: `{', '.join(summary['missingExpected'])}`")
    lines.append("")

    lines.append("## Expected Anchors")
    lines.append("")
    for name, status in summary["expected"].items():
        marker = "present" if status["present"] else "missing"
        first = status["first"].get("offset", "")
        suffix = f" first=`{first}`" if first else ""
        lines.append(f"- `{name}`: `{marker}` count=`{status['count']}`{suffix}")
    lines.append("")

    lines.append("## Categories")
    lines.append("")
    for category, count in summary["categories"].items():
        lines.append(f"- `{category}`: `{count}` hits")
    if not summary["categories"]:
        lines.append("- none")
    lines.append("")

    lines.append("## Modules")
    lines.append("")
    for module in summary["modules"][:top]:
        lines.append(f"- `{module}`")
    if len(summary["modules"]) > top:
        lines.append(f"- ... +{len(summary['modules']) - top} more")
    if not summary["modules"]:
        lines.append("- none")
    lines.append("")

    lines.append("## Hits")
    lines.append("")
    items = sorted(summary["hitsByName"].items(), key=lambda item: (item[1]["category"], item[0]))
    for name, data in items:
        offsets = ", ".join(offset["offset"] for offset in data["offsets"][:top] if offset["offset"])
        if len(data["offsets"]) > top:
            offsets += f", ... +{len(data['offsets']) - top}"
        lines.append(
            f"- `{data['category']}` `{name}` count=`{data['count']}` first=`{data['first']['offset']}` offsets=`{offsets}`"
        )
    if not items:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize Linux or Windows client loader probe logs.")
    parser.add_argument("log", type=Path)
    parser.add_argument("--loader", action="append", choices=("client", "win-client", "linux-client", "server"), default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--expected", action="append", default=[])
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args(argv)

    summary = summarize(
        load_records(args.log),
        loader_filter=args.loader,
        pid_filter=args.pid,
        exe_substrings=args.exe_substring,
        expected=args.expected or DEFAULT_EXPECTED,
    )
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.top))


if __name__ == "__main__":
    main()
