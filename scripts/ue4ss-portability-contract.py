#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    "linux-client": {
        "source": ("tools/linux-client-loader/dune_client_probe_loader.c", "src/dune_client_probe_loader.c"),
        "launcher": ("scripts/launch-linux-client-probe.sh", "examples/launch-native-client.sh"),
        "package": "scripts/package-linux-client-loader.sh",
        "injection": "ld-preload-elf",
    },
    "linux-server": {
        "source": ("tools/linux-server-loader/dune_server_probe_loader.c", "src/dune_server_probe_loader.c"),
        "launcher": ("scripts/run_server_safe.sh", "examples/smoke-linux-server-loader.sh"),
        "package": "scripts/package-linux-server-loader.sh",
        "injection": "ld-preload-elf",
    },
    "windows-client": {
        "source": ("tools/windows-client-loader/dune_win_client_probe_loader.c", "src/dune_win_client_probe_loader.c"),
        "launcher": ("scripts/launch-proton-client-probe.sh", "examples/launch-proton-client-probe.sh"),
        "package": "scripts/package-windows-client-loader.sh",
        "injection": "proton-version-dll-proxy",
    },
}

SURFACES = {
    "runtime-anchors": (
        "ue_anchor_group_for_name",
        "event=ue-anchor",
        "event=ue-anchor-signature",
        "FNamePool",
        "GUObjectArray",
        "StaticFindObject",
        "ProcessEvent",
        "CallFunctionByNameWithArguments",
    ),
    "package-loading-anchors": (
        "StaticLoadObject",
        "StaticLoadClass",
        "LOAD_ASSET_PACKAGE_SELF_TEST_ANCHOR",
        "LoadObject",
        "LoadPackage",
        "ResolveName",
        "GetLoadAssetPackageAbiState",
        "PrepareLoadAssetPackageStringBridge",
        "PrepareLoadAssetPackageNativeBuffer",
        "PrepareLoadAssetPackageTCharBuffer",
        "GetLoadAssetPackageTCharVerificationState",
        "GetLoadAssetPackageCallFrameVerificationState",
        "GetLoadAssetPackageCrashGuardState",
        "GetLoadAssetPackageGuardedCallState",
        "GetLoadAssetPackageReturnValidationState",
        "GetLoadAssetPackageNativeCallAdapterState",
        "GetLoadAssetPackageInvocationDescriptorState",
        "GetLoadAssetPackageNativeExecutorState",
        "load_asset_package_run_guarded_native_call",
        "native-return-validated",
        "nativeReturn",
        "nativeReturnValidated",
        "NativeReturnAddress",
        "NativeReturnValidated",
        "PackageBackendTargetImage",
        "target-not-target-image",
        "NativeCallPlanConstructed",
        "NativeCallExecutionMode",
        "NativeCallGuardPolicy",
        "InvocationDescriptorConsumed",
        "NativeCallPlanAccepted",
        "NativeExecutorConstructed",
        "NativeExecutorReady",
        "ExecutorPreflightPassed",
        "FinalNativeCallEligible",
        "NativeExecutorBlockReason",
        "FinalNativeCallBlocked",
        "PrepareLoadAssetPackageCallFrame",
        "lua-load-asset-package-abi-state",
        "lua-load-asset-package-string-bridge-state",
        "lua-load-asset-package-native-buffer-state",
        "lua-load-asset-package-tchar-buffer-state",
        "lua-load-asset-package-tchar-verification-state",
        "lua-load-asset-package-call-frame-verification-state",
        "lua-load-asset-package-crash-guard-state",
        "lua-load-asset-package-guarded-call-state",
        "lua-load-asset-package-return-validation-state",
        "lua-load-asset-package-native-call-adapter-state",
        "lua-load-asset-package-invocation-descriptor-state",
        "lua-load-asset-package-native-executor-state",
        "lua-load-asset-package-native-invoke",
        "native_invoked ? \"true\" : \"false\"",
        "guarded-native-package-load",
        "lua-load-asset-package-call-frame-state",
        "GetLoadClassPackageBridgeState",
        "GetLoadClassPackageAbiState",
        "GetLoadClassPackageCallFrameVerificationState",
        "GetLoadClassPackageNativeExecutorState",
        "InvokeLoadClassPackageNative",
        "lua-load-class-package-preflight",
        "lua-load-class-package-bridge-state",
        "lua-load-class-package-abi-state",
        "lua-load-class-package-call-frame-verification-state",
        "lua-load-class-package-native-executor-state",
        "lua-load-class-package-native-invoke",
        "ClassRootReady",
        "signatureFamily=StaticLoadClass",
        "\"package\"",
    ),
    "uobject-registry": (
        "FindObject",
        "FindObjects",
        "FindFirstOf",
        "FindAllOf",
        "ForEachUObject",
        "lua-object-registry-check",
        "event=lua-object-registry",
    ),
    "ufunction-registry": (
        "ForEachFunction",
        "ForEachUFunction",
        "lua_for_each_ufunction_callback",
        "lua-function-registry-check",
        "event=lua-function-registry-check",
        "lua-function-iteration-check",
        "UFunction",
    ),
    "reflection": (
        "UObjectReflection",
        "GetPropertyValue",
        "SetPropertyValue",
        "CallFunctionByNameWithArguments",
        "lua_call_function_name_arg",
        "ForEachProperty",
        "ImportText",
        "ExportText",
        "runtimeLiveDescriptorValueGetHits",
        "runtimeLiveDescriptorValueSetHits",
    ),
    "process-event-hooks": (
        "ProcessEventDispatchContext",
        "register_process_event_dispatch_callback",
        "ue-process-event-live-hook",
        "ue-process-event-vtable-candidate",
        "ue-process-event-vtable-scan",
        "targetSource=vtable-candidate",
        "CreateProcessEventParams",
        "lua_create_process_event_params_callback",
        "MAX_SYNTHETIC_PROCESS_EVENT_PARAMS",
        "DescriptorBackedCallable",
        "ParamsBufferConstructible",
        "lua-process-event-params-buffer",
        "NativeNonSelfTestEnabled",
        "NativeNonSelfTestInvoked",
        "ParamsWritten",
        "descriptor-preflight-ready",
        "non-self-test-invoke-disabled",
        "non-self-test-invoked",
        "luaParamGetHits",
        "luaParamSetHits",
        "luaBoolParamAccessors",
    ),
    "call-function-hooks": (
        "configured_call_function_hook_target",
        "run_call_function_hook_probe",
        "CallFunctionHookProbe",
        "ue-call-function-hook",
        "configured_call_function_live_hook_target",
        "install_call_function_live_hook",
        "CallFunctionLiveHook",
        "ue-call-function-live-hook",
        "InvokeCallFunctionNative",
        "lua-call-function-native-invoke",
        "lua-call-function-native-invoke-self-test",
        "loader-call-function-native-bridge",
        "NativeNonSelfTestInvoked",
        "non-self-test-invoked",
        "ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE",
    ),
    "lua-hook-dispatch": (
        "RegisterHook",
        "UnregisterHook",
        "lua_hook_path_exact_matches",
        "lua_hook_path_alias_matches",
        "pathAliasMatches",
    ),
    "lua-mod-lifecycle": (
        "run_lua_mod_entrypoints",
        "RegisterModInitCallback",
        "RegisterModPostInitCallback",
        "lua-mod-dispatch-self-test",
        "MAX_LUA_MOD_SCRIPTS",
        "MAX_LUA_MOD_MANIFEST_ENTRIES",
    ),
    "scheduler-and-input": (
        "ExecuteInGameThread",
        "DrainGameThreadQueue",
        "lua_drain_game_thread_queue_internal",
        "ExecuteAsync",
        "ExecuteWithDelay",
        "LoopAsync",
        "lua_drain_scheduler_queue_internal",
        "RegisterKeyBind",
        "RegisterConsoleCommandHandler",
    ),
    "compat-globals": (
        "register_lua_compat_constant_tables",
        "register_lua_compat_metadata_tables",
        "UE4SS",
        "GetVersion",
        "UnrealVersion",
        "IsAtLeast",
        "EObjectFlags",
        "EInternalObjectFlags",
        "PropertyTypes",
        "ModifierKeys",
        "IterateGameDirectories",
    ),
    "world-engine-helpers": (
        "GetWorld",
        "GetEngine",
        "find_lua_registered_world_handle",
        "find_lua_registered_engine_handle",
        "lua-global-runtime-helper-check",
    ),
    "object-notify": (
        "NotifyOnNewObject",
        "UnregisterNotifyOnNewObject",
        "StaticConstructObject",
        "GetStaticConstructObjectNativeExecutorState",
        "InvokeStaticConstructObjectNative",
        "lua-static-construct-object-native-executor-state",
        "lua-static-construct-object-native-invoke",
        "STATIC_CONSTRUCT_OBJECT_FNAME_COMPARISON_INDEX",
        "STATIC_CONSTRUCT_OBJECT_FNAME_NUMBER",
        "CONFIRM_STATIC_CONSTRUCT_OBJECT_FNAME",
        "ENABLE_STATIC_CONSTRUCT_OBJECT_CRASH_GUARD",
        "fname-unconfirmed",
        "crash-guard-missing",
        "native-invoked",
        "NativeReturnAddress",
        "NativeReturnReadable",
        "notifyOnNewObjectCallbacks",
        "notifyOnNewObjectResult",
        "lua_unregister_notify_on_new_object_callback",
    ),
    "container-marshalling": (
        "FScriptArray",
        "FScriptSet",
        "FScriptMap",
        "GetRawElement",
        "GetRawPair",
        "GetStorageLayout",
        "IsSparseLayoutValidated",
    ),
    "custom-property": (
        "lua_register_custom_property_callback",
        "RegisterCustomProperty",
        "PropertyTypes",
        "ObjectProperty",
        "IntProperty",
        "FloatProperty",
        "DoubleProperty",
        "BoolProperty",
        "NameProperty",
        "TextProperty",
        "StructProperty",
        "ArrayProperty",
        "MapProperty",
        "EnumProperty",
    ),
}

PACKAGE_SURFACES = {
    "post-canary-strict-contract": (
        "prepare-ue-anchor-canary.py",
        "post-canary-verify.sh",
        "post-canary-verify-strict.sh",
        "DUNE_UE4SS_STRICT_RUNTIME_CONTRACT",
        "strictRuntimeContract",
        "contractReady",
        "runtimeRootDiscovery",
        "UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS",
        "RuntimeFNamePoolCandidate",
        "RuntimeGUObjectArrayCandidate",
        "promoteAmbiguousRoots",
        "same-run FName/object-array validation",
        "signatureAnchorReady",
        "targetObjectDiscovery",
        "targetHooks",
        "targetPackageLoadingSurface",
        "liveTargetImageCanaryContract",
        "ue4ssLuaApiComplete",
        "targetImageAnchors",
        "runtimePackageLoading",
        "NativeExecutorReady",
        "ExecutorPreflightPassed",
        "FinalNativeCallEligible",
        "luaLoadAssetPackageNativeInvocation",
        "nativeInvoked=true",
        "nativeReturnValidated=true",
        "runtimeObjectRegistry",
        "runtimeReflection",
        "runtimeProcessEventDispatch",
        "more than a live hook row",
        "decoded live function path",
        "Lua context handles",
        "descriptor-backed param accessors",
        "container alias/layout methods",
        "runtimeCallFunctionDispatch",
        "luaProcessEventNativeInvokeNonSelfTestInvoked",
        "luaCallFunctionNativeInvokeNonSelfTestInvoked",
        "missingSignatureAnchorReadyKeys",
    ),
    "source-group-matched-root-recovery": (
        "--anchor-preset complete",
        "--require-source-group-match",
        "ue-root-recovery-candidates-complete-source-matched.json",
    ),
    "canary-next-plan-chaining": (
        "summarize-ue-vtable-candidates.py",
        "ue-vtable-candidates.json",
        "ue-vtable-candidates.md",
        "next-canary-plan.json",
        "next-canary-plan.env",
        "next-canary-plan.md",
        "--hook-targets-json",
        "plan-ue4ss-canary-env.py",
    ),
}

TARGET_PACKAGE_SURFACES = {
    "linux-server": {
        "generic-unreal-target-selection": (
            "DUNE_PROBE_LOADER_TARGET",
            "DUNE_PROBE_LOADER_FORCE",
            "For non-Dune targets",
            "DUNE_UE4SS_PACKAGE_TRACE_PID",
            "DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN",
            "explicit process without Docker discovery",
        ),
        "elf-qword-root-shape-hardening": (
            "summarize-elf-writable-root-shapes.py",
            "export-ue-writable-root-shape-candidates.py",
            "test-elf-writable-root-shapes.py",
            "test-export-ue-writable-root-shape-candidates.py",
        ),
        "zero-player-server-canary-preflight": (
            "canary-linux-server-loader.sh",
            "test-canary-linux-server-loader.py",
        ),
        "server-canary-next-plan-wrapper": (
            "canary-linux-server-loader.sh",
            "DUNE_LINUX_SERVER_CANARY_PLAN_JSON",
            "test-canary-linux-server-loader.py",
        ),
        "package-root-artifact-verification": (
            "scripts/verify-loader-artifacts.py --target linux-server --package-root .",
            "--package-target linux-server",
            "--package-only",
            "loader-artifact-verification.txt",
            "loader-artifact-verification.json",
            "ue4ss-package-runtime-trace.sh",
            "verify-ue4ss-package-review-bundle.py",
            "plan-ue4ss-package-next-action.py",
            "tracePidMatchesRequested",
            "playerGuardPhase",
            "playerGuardPartition",
            "playerGuardConnectedPlayers",
        ),
        "package-route-slot-proof": (
            "verify-ue4ss-package-route-slot-recovery.py",
            "routeSlotTraceRequirement",
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeVtableStaticSlotMatches",
            "requiredSlots=[0x3a0,0x3d8]",
            "requiredRegisters=[rbx,r14]",
            "routeGdb",
            "required object/vtable capture",
            "rbx, r14",
        ),
        "package-archive-artifact-verification": (
            "--package-archive \"$archive\"",
            "${archive}.verification.txt",
            "${archive}.verification.json",
            "package verification: %s",
        ),
    },
    "linux-client": {
        "generic-unreal-target-selection": (
            "DUNE_CLIENT_PROBE_TARGET",
            "DUNE_CLIENT_PROBE_FORCE",
            "For non-Dune native UE targets",
            "target executable fragment",
            "without editing installed game files",
        ),
        "elf-qword-root-shape-hardening": (
            "summarize-elf-writable-root-shapes.py",
            "export-ue-writable-root-shape-candidates.py",
            "test-elf-writable-root-shapes.py",
            "test-export-ue-writable-root-shape-candidates.py",
        ),
        "client-canary-next-plan-verifier": (
            "verify-client-probe-canary.sh",
            "test-client-launch-preflight.py",
            "linux-client",
        ),
        "package-root-artifact-verification": (
            "analysis/verify-loader-artifacts.py --target linux-client --package-root .",
            "--package-target linux-client",
            "--package-only",
            "loader-artifact-verification.txt",
            "loader-artifact-verification.json",
        ),
    },
    "windows-client": {
        "generic-unreal-target-selection": (
            "--game-dir",
            "--exe-rel",
            "--dll-name",
            "--stage-dir",
            "For non-Dune Windows UE targets",
            "without editing installed game files",
        ),
        "pe-qword-root-shape-hardening": (
            "summarize-pe-writable-root-shapes.py",
            "export-ue-writable-root-shape-candidates.py",
            "test-pe-writable-root-shapes.py",
            "test-export-ue-writable-root-shape-candidates.py",
        ),
        "client-canary-next-plan-verifier": (
            "verify-client-probe-canary.sh",
            "test-client-launch-preflight.py",
            "windows",
            "win-client",
        ),
        "package-root-artifact-verification": (
            "analysis/verify-loader-artifacts.py --target windows-client --package-root .",
            "--package-target windows-client",
            "--package-only",
            "loader-artifact-verification.txt",
            "loader-artifact-verification.json",
        ),
    },
}

TARGET_LAUNCH_SURFACES = {
    "linux-client": {
        "non-mutating-client-preflight": (
            "DUNE_CLIENT_PROBE_PREFLIGHT_ONLY",
            "linux_client_probe_preflight=true",
            "would_set_ld_preload",
            "would_exec",
        ),
    },
    "windows-client": {
        "non-mutating-client-preflight": (
            "--preflight-only",
            "DUNE_WIN_CLIENT_PROBE_PREFLIGHT_ONLY",
            "windows_client_probe_preflight=true",
            "stage_dir_valid",
            "would_exec",
        ),
    },
}

PACKAGE_ARTIFACT_LAYOUTS = {
    "linux-server": (
        "$stage/scripts/ue4ss-port-readiness.py",
        "$stage/scripts/summarize-ue4ss-port-gaps.py",
        "$stage/scripts/summarize-ue4ss-evidence-inventory.py",
        "$stage/scripts/ue4ss-portability-contract.py",
        "$stage/scripts/verify-loader-artifacts.py",
        "$stage/scripts/plan-ue4ss-package-runtime-trace.py",
        "$stage/scripts/summarize-ue4ss-package-runtime-trace-evidence.py",
        "$stage/scripts/export-ue4ss-package-promotion-env.py",
        "$stage/scripts/review-ue4ss-package-abi.py",
        "$stage/scripts/verify-ue4ss-package-review-bundle.py",
        "$stage/scripts/ue4ss-package-runtime-trace.sh",
        "$stage/tests/test-ue4ss-port-readiness.py",
        "$stage/tests/test-ue4ss-port-gaps.py",
        "$stage/tests/test-ue4ss-evidence-inventory.py",
        "$stage/tests/test-ue4ss-portability-contract.py",
        "$stage/tests/test-verify-loader-artifacts.py",
        "$stage/tests/test-ue4ss-package-runtime-trace-plan.py",
        "$stage/tests/test-ue4ss-package-runtime-trace-evidence.py",
        "$stage/tests/test-export-ue4ss-package-promotion-env.py",
        "$stage/tests/test-review-ue4ss-package-abi.py",
        "$stage/tests/test-verify-ue4ss-package-review-bundle.py",
        "$stage/docs/ue4ss-portability-contract.json",
        "$stage/docs/ue4ss-portability-contract.md",
    ),
    "linux-client": (
        "$stage/analysis/ue4ss-port-readiness.py",
        "$stage/analysis/summarize-ue4ss-port-gaps.py",
        "$stage/analysis/summarize-ue4ss-evidence-inventory.py",
        "$stage/analysis/ue4ss-portability-contract.py",
        "$stage/analysis/verify-loader-artifacts.py",
        "$stage/analysis/plan-ue4ss-package-runtime-trace.py",
        "$stage/tests/test-ue4ss-port-readiness.py",
        "$stage/tests/test-ue4ss-port-gaps.py",
        "$stage/tests/test-ue4ss-evidence-inventory.py",
        "$stage/tests/test-ue4ss-portability-contract.py",
        "$stage/tests/test-verify-loader-artifacts.py",
        "$stage/tests/test-ue4ss-package-runtime-trace-plan.py",
        "$stage/docs/ue4ss-portability-contract.json",
        "$stage/docs/ue4ss-portability-contract.md",
    ),
    "windows-client": (
        "$stage/analysis/ue4ss-port-readiness.py",
        "$stage/analysis/summarize-ue4ss-port-gaps.py",
        "$stage/analysis/summarize-ue4ss-evidence-inventory.py",
        "$stage/analysis/ue4ss-portability-contract.py",
        "$stage/analysis/verify-loader-artifacts.py",
        "$stage/tests/test-ue4ss-port-readiness.py",
        "$stage/tests/test-ue4ss-port-gaps.py",
        "$stage/tests/test-ue4ss-evidence-inventory.py",
        "$stage/tests/test-ue4ss-portability-contract.py",
        "$stage/tests/test-verify-loader-artifacts.py",
        "$stage/docs/ue4ss-portability-contract.json",
        "$stage/docs/ue4ss-portability-contract.md",
    ),
}

DOCS = (
    "docs/client-loader-support.md",
    "docs/linux-client-loader.md",
    "docs/windows-client-loader.md",
    "docs/ue4ss-linux-loader-evaluation.md",
)


def read_first(paths):
    for relative in paths:
        path = ROOT / relative
        if path.exists():
            return path, path.read_text(encoding="utf-8")
    return None, ""


def surface_result(text, markers):
    missing = [marker for marker in markers if marker not in text]
    return {"passed": not missing, "missing": missing, "required": list(markers)}


def injection_result(target, config, texts):
    launcher = texts["launcher"]
    package = texts["package"]
    if config["injection"] == "ld-preload-elf":
        required = ("LD_PRELOAD",)
        missing = [marker for marker in required if marker not in launcher and marker not in package]
        if target == "linux-client":
            for marker in ("Windows/PE", "refusing native Linux preload"):
                if marker not in launcher and marker not in package:
                    missing.append(marker)
        return {
            "model": config["injection"],
            "passed": not missing,
            "missing": missing,
        }
    required = ("version.dll", "WINEDLLOVERRIDES", "DUNE_WIN_CLIENT_PROBE", "dune-win-client-probe.env")
    missing = [marker for marker in required if marker not in launcher and marker not in package]
    if "LD_PRELOAD" in launcher:
        missing.append("launcher must not use LD_PRELOAD")
    return {
        "model": config["injection"],
        "passed": not missing,
        "missing": missing,
    }


def package_artifact_layout_result(target, package_text):
    required = PACKAGE_ARTIFACT_LAYOUTS.get(target, ())
    result = surface_result(package_text, required)
    result["required"] = list(required)
    return result


def build_report(target_mode="all"):
    targets = {}
    for target, config in TARGETS.items():
        source_path, source_text = read_first(config["source"])
        launcher_path, launcher_text = read_first(config["launcher"])
        package_path = ROOT / config["package"]
        if target_mode == "available" and not source_path:
            continue
        package_text = package_path.read_text(encoding="utf-8") if package_path.exists() else ""
        surfaces = {
            name: surface_result(source_text, markers)
            for name, markers in SURFACES.items()
        }
        package_surfaces = {
            name: surface_result(package_text, markers)
            for name, markers in PACKAGE_SURFACES.items()
        }
        package_surfaces.update(
            {
                name: surface_result(package_text, markers)
                for name, markers in TARGET_PACKAGE_SURFACES.get(target, {}).items()
            }
        )
        launch_surfaces = {
            name: surface_result(launcher_text, markers)
            for name, markers in TARGET_LAUNCH_SURFACES.get(target, {}).items()
        }
        artifact_layout = package_artifact_layout_result(target, package_text)
        injection = injection_result(
            target,
            config,
            {"launcher": launcher_text, "package": package_text},
        )
        targets[target] = {
            "source": str(source_path.relative_to(ROOT)) if source_path else None,
            "launcher": str(launcher_path.relative_to(ROOT)) if launcher_path else None,
            "package": config["package"] if package_path.exists() else None,
            "injection": injection,
            "artifactLayout": artifact_layout,
            "surfaces": surfaces,
            "packageSurfaces": package_surfaces,
            "launchSurfaces": launch_surfaces,
            "passed": (
                bool(source_path)
                and bool(launcher_path)
                and (target_mode == "available" or package_path.exists())
                and injection["passed"]
                and artifact_layout["passed"]
                and all(item["passed"] for item in surfaces.values())
                and all(item["passed"] for item in package_surfaces.values())
                and all(item["passed"] for item in launch_surfaces.values())
            ),
        }

    docs = {}
    for relative in DOCS:
        path = ROOT / relative
        if target_mode == "available" and not path.exists():
            continue
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        required = (
            "portability contract",
            "Linux native client",
            "Windows/Proton client",
            "Linux dedicated server",
            "version.dll",
            "LD_PRELOAD",
            "strictRuntimeContract",
            "contractReady",
            "runtimeRootDiscovery",
            "signatureAnchorReady",
            "targetObjectDiscovery",
            "targetHooks",
            "targetPackageLoadingSurface",
            "liveTargetImageCanaryContract",
            "ue4ssLuaApiComplete",
            "ue4ss-evidence-inventory.md",
            "summarize-ue4ss-evidence-inventory.py",
            "targetImageAnchors",
            "runtimePackageLoading",
            "NativeExecutorReady",
            "ExecutorPreflightPassed",
            "FinalNativeCallEligible",
            "runtimeObjectRegistry",
            "runtimeReflection",
            "runtimeProcessEventDispatch",
            "decoded live function path",
            "Lua context handles",
            "descriptor-backed param accessors",
            "container alias/layout methods",
            "runtimeCallFunctionDispatch",
            "missingSignatureAnchorReadyKeys",
        )
        docs[relative] = surface_result(text, required)
        docs[relative]["exists"] = path.exists()

    return {
        "schemaVersion": "dune-ue4ss-portability-contract/v1",
        "targets": targets,
        "docs": docs,
        "passed": bool(targets)
        and bool(docs)
        and all(target["passed"] for target in targets.values())
        and all(item["exists"] and item["passed"] for item in docs.values()),
    }


def markdown(report):
    lines = ["# UE4SS Portability Contract", ""]
    lines.append(f"- Passed: `{str(report['passed']).lower()}`")
    lines.append("")
    lines.append("## Targets")
    lines.append("")
    for target, item in report["targets"].items():
        status = "pass" if item["passed"] else "block"
        lines.append(f"- `{status}` `{target}` injection `{item['injection']['model']}`")
        if item["injection"]["missing"]:
            lines.append("  - missing injection markers: `" + "`, `".join(item["injection"]["missing"]) + "`")
        artifact_layout = item.get("artifactLayout", {"passed": False, "missing": ["missing artifact layout report"]})
        artifact_status = "pass" if artifact_layout["passed"] else "block"
        lines.append(f"  - `{artifact_status}` package `artifact-layout`")
        if artifact_layout["missing"]:
            lines.append("    - missing: `" + "`, `".join(artifact_layout["missing"]) + "`")
        for surface_name, surface in item["surfaces"].items():
            surface_status = "pass" if surface["passed"] else "block"
            lines.append(f"  - `{surface_status}` `{surface_name}`")
            if surface["missing"]:
                lines.append("    - missing: `" + "`, `".join(surface["missing"]) + "`")
        for surface_name, surface in item.get("packageSurfaces", {}).items():
            surface_status = "pass" if surface["passed"] else "block"
            lines.append(f"  - `{surface_status}` package `{surface_name}`")
            if surface["missing"]:
                lines.append("    - missing: `" + "`, `".join(surface["missing"]) + "`")
        for surface_name, surface in item.get("launchSurfaces", {}).items():
            surface_status = "pass" if surface["passed"] else "block"
            lines.append(f"  - `{surface_status}` launcher `{surface_name}`")
            if surface["missing"]:
                lines.append("    - missing: `" + "`, `".join(surface["missing"]) + "`")
    lines.append("")
    lines.append("## Docs")
    lines.append("")
    for doc, item in report["docs"].items():
        status = "pass" if item["exists"] and item["passed"] else "block"
        lines.append(f"- `{status}` `{doc}`")
        if item["missing"]:
            lines.append("  - missing: `" + "`, `".join(item["missing"]) + "`")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check Dune UE4SS-style loader portability parity.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument(
        "--targets",
        choices=("all", "available"),
        default="all",
        help="check every known target or only targets whose source is present",
    )
    parser.add_argument("--check", action="store_true", help="exit non-zero if the contract does not pass")
    args = parser.parse_args(argv)

    report = build_report(args.targets)
    if args.format == "markdown":
        print(markdown(report), end="")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    if args.check and not report["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
