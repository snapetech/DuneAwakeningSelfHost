#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-port-gaps.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_port_gaps", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

NO_DEBUGGER_CHECK_COMMAND = (
    'ssh kspls0 \'ps -eo pid,stat,comm,args | grep -E "gdb|ue4ss-package-runtime-trace" '
    "| grep -v grep || true; docker top dune_server-deep-desert-1 -eo pid,stat,comm "
    "2>/dev/null | awk '\"'\"'NR==1 || /DuneSandboxServ/'\"'\"''"
)
LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS = (
    "reviewBundleVerification,reviewBundleVerificationSha256,"
    "routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,"
    "prearmReadinessVerification,prearmReadinessVerificationSha256"
)

LIVE_CONTRACT_GROUPS = {
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


def live_contract(missing_live):
    missing = set(missing_live or [])
    groups = {}
    for group_name, keys in LIVE_CONTRACT_GROUPS.items():
        group_missing = [key for key in keys if key in missing]
        groups[group_name] = {
            "ready": not group_missing,
            "requiredKeys": list(keys),
            "missingKeys": group_missing,
        }
    return {
        "ready": not missing,
        "groups": groups,
        "missingKeys": list(missing_live or []),
    }


def readiness_report(ready_overrides=None, missing_live=None):
    ready = {
        "targetImageProcess": False,
        "runtimeRootDiscovery": False,
        "runtimeRootValidation": False,
        "targetObjectDiscovery": False,
        "anchorGroupProvenance": True,
        "anchorCoverageObjectDiscovery": False,
        "objectDiscoveryCoverage": False,
        "findObjectSemantics": False,
        "luaObjectRegistryRuntime": False,
        "luaFunctionRegistryRuntime": False,
        "luaDecodedObjectAliasesRuntime": False,
        "ueObjectArrayShape": False,
        "ueObjectArrayRegistryRuntime": False,
        "ueObjectNativeIdentities": False,
        "ueObjectInternalFlags": False,
        "ueFNameDecoder": False,
        "luaObjectOuterChainIdentities": False,
        "luaObjectApi": True,
        "reflection": False,
        "ueReflectionProbe": False,
        "ueReflectionFieldWalk": False,
        "ueReflectionPropertyDescriptors": False,
        "ueReflectionPropertyDescriptorsRuntime": False,
        "ueReflectionPropertyValuesRuntime": False,
        "ueFunctionParamDescriptors": False,
        "ueFunctionParamContainerChildren": False,
        "ueFunctionIdentities": False,
        "ueFunctionNativeIdentities": False,
        "ueFunctionFlags": False,
        "luaReflectionForEachPropertyRuntime": False,
        "luaReflectionLiveDescriptorTypedClassRuntime": False,
        "luaReflectionLiveDescriptorTypedValuesRuntime": False,
        "luaReflectionLiveDescriptorTypedSetValuesRuntime": False,
        "luaReflectionLiveDescriptorValuesRuntime": False,
        "targetHooks": False,
        "ueProcessEventHookRuntimeTarget": False,
        "ueProcessEventLiveHookRuntimeTarget": False,
        "ueProcessEventLiveLuaDispatch": False,
        "ueProcessEventLiveFunctionPath": False,
        "ueProcessEventLiveRuntimeContext": False,
        "ueProcessEventLiveRegistryContext": False,
        "ueProcessEventLiveRuntimeRegistryContext": False,
        "ueProcessEventLiveParamValues": False,
        "ueProcessEventLiveRawParamValues": False,
        "ueProcessEventLiveContainerParamValues": False,
        "ueProcessEventLiveArrayContainerParamValues": False,
        "ueProcessEventLiveSetContainerParamValues": False,
        "ueProcessEventLiveMapContainerParamValues": False,
        "ueProcessEventLiveSetMapContainerParamValues": False,
        "ueProcessEventLiveContainerDataSamples": False,
        "ueProcessEventLuaContextHandles": False,
        "ueProcessEventLuaParamAccessors": False,
        "ueProcessEventLiveClassAwareParamValues": False,
        "ueProcessEventFunctionParamMethod": False,
        "ueProcessEventFunctionParamLookupMethod": False,
        "ueProcessEventFunctionParamIterationMethod": False,
        "ueProcessEventContainerAliasMethods": False,
        "ueProcessEventContainerStorageLayoutMethods": False,
        "ueProcessEventLuaScalarParamAccessors": False,
        "ueProcessEventLuaNameStringParamAccessors": False,
        "ueProcessEventLuaStructParamAccessors": False,
        "ueProcessEventLuaEnumParamAccessors": False,
        "ueProcessEventLuaObjectParamAccessors": False,
        "ueProcessEventLuaBoolParamAccessors": False,
        "ueProcessEventLuaHookRouting": False,
        "ueProcessEventLuaHookAliasRouting": False,
        "luaDispatch": False,
        "luaRuntime": True,
        "luaMods": True,
        "luaSchedulerApiMods": True,
        "luaInputCommandApiMods": True,
        "luaFunctionIterationRuntime": False,
        "luaProcessEventCompat": True,
        "luaProcessEventBridgeState": True,
        "luaProcessEventNativeInvoke": True,
        "luaProcessEventNativeInvokeDescriptorPreflight": True,
        "luaProcessEventNativeExecutorState": False,
        "luaProcessEventNativeInvokeNonSelfTestGate": False,
        "luaProcessEventNativeInvokeNonSelfTestInvoked": False,
        "luaCallFunctionNativeInvoke": True,
        "luaCallFunctionNativeInvokePreflight": True,
        "luaCallFunctionNativeExecutorState": False,
        "luaCallFunctionNativeInvokeNonSelfTestGate": False,
        "luaCallFunctionNativeInvokeNonSelfTestInvoked": False,
        "luaProcessEventParamsBuffer": True,
        "luaLoadAssetPackage": False,
        "targetPackageLoadingSurface": False,
        "anchorCoveragePackageLoading": False,
        "luaLoadAssetPackageAbiState": False,
        "luaLoadAssetPackageStringBridge": False,
        "luaLoadAssetPackageNativeBuffer": False,
        "luaLoadAssetPackageTCharBuffer": False,
        "luaLoadAssetPackageCallFrame": False,
        "luaLoadAssetPackageNativeCallAdapter": False,
        "luaLoadAssetPackageNativeExecutor": False,
        "liveTargetImageCanary": False,
        "ue4ssLuaApiComplete": False,
    }
    if ready_overrides:
        ready.update(ready_overrides)
    gates = [
        {"name": "ue-process-event-live-runtime-context", "passed": ready["ueProcessEventLiveRuntimeContext"], "evidence": "runtime=0", "blocker": "no runtime ProcessEvent context"},
        {"name": "lua-reflection-for-each-property-runtime", "passed": ready["luaReflectionForEachPropertyRuntime"], "evidence": "runtime=0", "blocker": "no runtime reflection descriptor"},
    ]
    return {
        "ready": ready,
        "gates": gates,
        "anchorCoverage": {
            "provided": True,
            "explicitAnchorCount": 0,
            "signatureAnchorCount": 5,
            "combinedAnchorCount": 5,
            "readyForTargetObjectDiscovery": False,
            "readyForTargetHookPlanning": False,
            "readyForTargetPackageLoading": False,
            "targetCoverageFieldsPresent": True,
            "missingRequiredGroups": [],
            "groups": {
                "names": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                "objects": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                "world": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 1},
                "dispatch": {"present": 1, "targetPresent": 0, "loaderPresent": 0, "unknownPresent": 1, "total": 1},
                "package": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
            },
        },
        "runtimeDiscovery": {
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x140060000",
                    "imageOffset": "0x60000",
                    "map": "C:\\game\\DuneSandbox-Win64-Shipping.exe",
                }
            ]
        },
        "nextSteps": ["recover live runtime roots"],
        "liveTargetImageCanaryContract": live_contract(
            ["targetObjectDiscovery"] if missing_live is None else missing_live
        ),
    }


def canary_plan(missing_groups=None):
    missing_groups = missing_groups or []
    groups = ("names", "objects", "world", "dispatch", "package", "reflection")
    return {
        "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
        "platform": "windows",
        "loader": "win-client",
        "selectedStage": "object-discovery",
        "blockers": [{"code": "incomplete-root-recovery-object-candidates"}],
        "nextCanaryContract": {
            "blockerCodes": ["incomplete-root-recovery-object-candidates"],
            "rootRecoveryCandidateInput": {
                "provided": True,
                "sourcePaths": ["/tmp/root-candidates.json"],
                "shapeSourcePaths": ["/tmp/candidate-shapes.json"],
                "outcomeSourcePaths": [],
                "envName": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
                "candidateCount": 4,
                "emittedCount": 3,
                "filteredRejectedShapeCount": 1,
                "filteredRejectedCandidateCount": 1,
                "filteredRejectedShapeOnlyCount": 1,
                "filteredRejectedOutcomeCount": 0,
                "sourceAnchorPresets": ["object-discovery"],
                "anchorCounts": {"FNamePool": 1, "GUObjectArray": 2},
                "missingGroups": missing_groups,
                "groupCoverage": {
                    group: {
                        "ready": group not in missing_groups,
                        "complete": group not in missing_groups,
                        "emittedAnchors": [] if group in missing_groups else [group],
                        "missingAnchors": [group] if group in missing_groups else [],
                    }
                    for group in groups
                },
            },
        },
    }


def add_post_canary_verification(plan, output_overrides=None):
    output_files = {
        "readinessJson": "ue4ss-readiness.json",
        "objectDiscoveryCoverage": "object-discovery-coverage.json",
        "postCanaryGapSummaryJson": "ue4ss-port-gaps.json",
        "postCanaryGapSummary": "ue4ss-port-gaps.md",
        "evidenceInventoryJson": "ue4ss-evidence-inventory.json",
        "evidenceInventory": "ue4ss-evidence-inventory.md",
        "postCanarySummary": "post-canary-summary.md",
    }
    if output_overrides:
        output_files.update(output_overrides)
    plan["nextCanaryContract"]["postCanaryVerification"] = {
        "schemaVersion": "dune-ue4ss-post-canary-verification/v1",
        "outputFiles": output_files,
    }
    return plan


def runtime_carry_forward_plan():
    plan = canary_plan(["names", "objects", "world", "dispatch", "package", "reflection"])
    root = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
    root["provided"] = False
    root["candidateCount"] = 0
    root["emittedCount"] = 0
    root["anchorCounts"] = {}
    root["groupCoverage"] = {
        group: {
            "ready": False,
            "complete": False,
            "emittedAnchors": [],
            "missingAnchors": [group],
        }
        for group in ("names", "objects", "world", "dispatch", "package", "reflection")
    }
    plan["nextCanaryContract"]["runtimeCandidateCarryForward"] = {
        "provided": True,
        "envName": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
        "entries": ["RuntimeFNamePool=0x60000"],
        "entryCount": 1,
        "anchorCounts": {"RuntimeFNamePool": 1},
        "groupCoverage": {
            "names": {
                "ready": True,
                "complete": False,
                "emittedAnchors": ["RuntimeFNamePool"],
                "missingAnchors": ["FNamePool"],
            },
            "objects": {
                "ready": False,
                "complete": False,
                "emittedAnchors": [],
                "missingAnchors": ["RuntimeGUObjectArray"],
            },
        },
        "missingGroups": ["objects", "world", "dispatch", "package", "reflection"],
    }
    return plan


class Ue4ssPortGapTests(unittest.TestCase):
    def test_summary_exposes_top_level_blockers_when_not_ready(self):
        summary = module.summarize({"ready": {}, "gates": []})
        rendered = module.markdown(summary)

        self.assertFalse(summary["ready"])
        self.assertIn("blockers", summary)
        self.assertIn("ue4ssLuaApiComplete is not true", summary["blockers"])
        self.assertTrue(
            any(item.startswith("runtime-anchors missing ready keys:") for item in summary["blockers"]),
            summary["blockers"],
        )
        self.assertIn("- Blockers: `", rendered)

    def test_gap_summary_keeps_live_runtime_gaps_blocked(self):
        summary = module.summarize(readiness_report())

        self.assertFalse(summary["ready"])
        by_id = {feature["id"]: feature for feature in summary["features"]}
        self.assertEqual(by_id["runtime-anchors"]["status"], "blocked")
        self.assertEqual(by_id["process-event-hooks"]["status"], "blocked")
        self.assertIn("ueProcessEventLiveRuntimeContext", by_id["process-event-hooks"]["missingRequiredKeys"])
        self.assertTrue(summary["nextCanaryRecommendation"]["needed"])
        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "runtime-anchors")
        self.assertEqual(summary["nextCanaryRecommendation"]["maxStage"], "read-only")
        self.assertEqual(summary["nextCanaryRecommendation"]["liveTargetImageContractGroup"], "targetImageAnchors")
        self.assertEqual(
            summary["nextCanaryRecommendation"]["runtimeRootCandidateLocations"][0]["imageOffset"],
            "0x60000",
        )
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedGroup"], "targetImageAnchors")
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedFeature"], "runtime-anchors")
        self.assertIn(
            "targetObjectDiscovery",
            summary["liveTargetImageContract"]["groups"]["targetImageAnchors"]["missingKeys"],
        )
        self.assertIn("--platform", summary["nextCanaryRecommendation"]["plannerCommands"]["windows"])
        rendered = module.markdown(summary)
        self.assertIn("no runtime ProcessEvent context", rendered)
        self.assertIn("Live Target-Image Contract", rendered)
        self.assertIn("targetImageAnchors", rendered)
        self.assertIn("Runtime root candidates", rendered)
        self.assertIn("Recommended next stage", rendered)
        self.assertIn("plan-ue4ss-canary-env.py", rendered)

    def test_gap_summary_reports_complete_when_readiness_contract_is_complete(self):
        all_ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                all_ready[key] = True
        summary = module.summarize(readiness_report(all_ready, missing_live=[]))

        self.assertTrue(summary["ready"])
        self.assertEqual(summary["statusCounts"], {"ready": len(module.FEATURES)})
        self.assertTrue(all(feature["status"] == "ready" for feature in summary["features"]))
        self.assertFalse(summary["nextCanaryRecommendation"]["needed"])
        self.assertEqual(summary["nextCanaryRecommendation"]["stage"], "none")
        self.assertTrue(summary["liveTargetImageContract"]["ready"])
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedGroup"], "")

    def test_gap_summary_rejects_complete_claim_when_live_contract_disagrees(self):
        all_ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                all_ready[key] = True
        report = readiness_report(all_ready, missing_live=["runtimeRootDiscovery"])
        report["ready"]["runtimeRootDiscovery"] = True
        report["ready"]["liveTargetImageCanary"] = True
        report["ready"]["ue4ssLuaApiComplete"] = True

        summary = module.summarize(report)
        quickest = summary["quickestPathToOneToOne"]

        self.assertFalse(summary["ready"])
        self.assertEqual(summary["statusCounts"], {"ready": len(module.FEATURES)})
        self.assertTrue(all(feature["status"] == "ready" for feature in summary["features"]))
        self.assertFalse(quickest["ready"])
        self.assertEqual(quickest["feature"], "runtime-anchors")
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedGroup"], "targetImageAnchors")
        self.assertIn(
            "runtimeRootDiscovery",
            summary["liveTargetImageContract"]["groups"]["targetImageAnchors"]["missingKeys"],
        )

    def test_runtime_anchor_gap_requires_runtime_root_discovery_even_with_target_objects(self):
        ready = {
            "targetImageProcess": True,
            "targetObjectDiscovery": True,
            "anchorGroupProvenance": True,
            "anchorCoverageObjectDiscovery": True,
            "runtimeRootDiscovery": False,
        }
        report = readiness_report(ready, missing_live=["runtimeRootDiscovery"])

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(by_id["runtime-anchors"]["status"], "partial")
        self.assertIn("runtimeRootDiscovery", by_id["runtime-anchors"]["missingReadyKeys"])
        self.assertIn("runtimeRootDiscovery", by_id["runtime-anchors"]["missingRequiredKeys"])
        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "runtime-anchors")
        self.assertEqual(summary["nextCanaryRecommendation"]["maxStage"], "read-only")
        self.assertEqual(
            summary["liveTargetImageContract"]["groups"]["targetImageAnchors"]["missingKeys"],
            ["runtimeRootDiscovery"],
        )

    def test_object_registry_gap_requires_find_object_runtime_identity(self):
        ready = {}
        for feature in module.FEATURES[:2]:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        ready["findObjectSemantics"] = False
        ready["ueObjectInternalFlags"] = False
        ready["luaObjectOuterChainIdentities"] = False
        ready["luaFunctionIterationRuntime"] = False
        report = readiness_report(
            ready,
            missing_live=[
                "findObjectSemantics",
                "ueObjectInternalFlags",
                "luaObjectOuterChainIdentities",
                "luaFunctionIterationRuntime",
            ],
        )

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(by_id["object-registry"]["status"], "partial")
        self.assertIn("findObjectSemantics", by_id["object-registry"]["missingReadyKeys"])
        self.assertIn("ueObjectInternalFlags", by_id["object-registry"]["missingRequiredKeys"])
        self.assertIn("luaObjectOuterChainIdentities", by_id["object-registry"]["missingRequiredKeys"])
        self.assertIn("luaFunctionIterationRuntime", by_id["object-registry"]["missingRequiredKeys"])
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedGroup"], "runtimeObjectRegistry")
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedFeature"], "object-registry")
        self.assertIn(
            "luaObjectOuterChainIdentities",
            summary["liveTargetImageContract"]["groups"]["runtimeObjectRegistry"]["missingKeys"],
        )

    def test_per_loader_gap_summary_is_kept_separate(self):
        complete = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                complete[key] = True
        report = readiness_report(complete, missing_live=[])
        report["perLoaderReadiness"] = {
            "win-client": readiness_report(complete, missing_live=[]),
            "linux-client": readiness_report(),
        }

        summary = module.summarize(report)

        self.assertTrue(summary["perLoader"]["win-client"]["ready"])
        self.assertFalse(summary["perLoader"]["linux-client"]["ready"])
        self.assertGreater(summary["perLoader"]["linux-client"]["statusCounts"]["blocked"], 0)

    def test_readiness_validator_rejects_malformed_per_loader_readiness(self):
        report = readiness_report()
        report["perLoaderReadiness"] = []

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn("perLoaderReadiness must be an object", str(raised.exception))

    def test_readiness_validator_rejects_per_loader_live_contract_contradiction(self):
        complete = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                complete[key] = True
        report = readiness_report(complete, missing_live=[])
        per_loader = readiness_report(complete, missing_live=[])
        per_loader["liveTargetImageCanaryContract"]["ready"] = True
        per_loader["liveTargetImageCanaryContract"]["missingKeys"] = ["runtimeRootDiscovery"]
        report["perLoaderReadiness"] = {"linux-client": per_loader}

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn(
            "perLoaderReadiness.linux-client.liveTargetImageCanaryContract.ready cannot be true while missingKeys is non-empty",
            str(raised.exception),
        )

    def test_process_event_gap_recommends_live_hook_planner_ceiling(self):
        ready = {}
        for feature in module.FEATURES[:3]:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(ready, missing_live=["ueProcessEventLiveRuntimeContext"])

        summary = module.summarize(report)

        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "process-event-hooks")
        self.assertEqual(summary["nextCanaryRecommendation"]["stage"], "process-event-hooks")
        self.assertEqual(summary["nextCanaryRecommendation"]["maxStage"], "live-hook")
        self.assertEqual(
            summary["nextCanaryRecommendation"]["liveTargetImageContractGroup"],
            "runtimeProcessEventDispatch",
        )
        self.assertIn(
            "live-hook",
            summary["nextCanaryRecommendation"]["plannerCommands"]["server"],
        )

    def test_reflection_gap_requires_runtime_function_identity(self):
        ready = {}
        for feature in module.FEATURES[:2]:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        reflection = next(feature for feature in module.FEATURES if feature["id"] == "reflection")
        for key in reflection["required"]:
            ready[key] = True
        ready["reflection"] = False
        ready["ueFunctionIdentities"] = False
        report = readiness_report(ready, missing_live=[])

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "reflection")
        self.assertEqual(summary["nextCanaryRecommendation"]["maxStage"], "read-only")
        self.assertIn("ueFunctionIdentities", by_id["reflection"]["missingRequiredKeys"])

    def test_reflection_gap_reports_composite_ready_key_when_subgates_are_green(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        ready["reflection"] = False
        report = readiness_report(ready, missing_live=["reflection"])

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(by_id["reflection"]["status"], "blocked")
        self.assertEqual(by_id["reflection"]["missingReadyKeys"], ["reflection"])
        self.assertIn("reflection", by_id["reflection"]["missingRequiredKeys"])
        rendered = module.markdown(summary)
        self.assertIn("reflection", rendered)
        self.assertIn("simultaneously ready", rendered)

    def test_reflection_runtime_evidence_groups_missing_descriptor_and_lua_bridge_proof(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        ready["ue4ssLuaApiComplete"] = False
        ready["ueFunctionParamContainerChildren"] = False
        ready["ueReflectionPropertyValuesRuntime"] = False
        ready["luaReflectionLiveDescriptorTypedValuesRuntime"] = False
        report = readiness_report(
            ready,
            missing_live=[
                "ueFunctionParamContainerChildren",
                "ueReflectionPropertyValuesRuntime",
                "luaReflectionLiveDescriptorTypedValuesRuntime",
            ],
        )

        summary = module.summarize(report)
        evidence = summary["reflectionRuntimeEvidence"]

        self.assertFalse(evidence["ready"])
        self.assertEqual(evidence["firstBlockedGroup"], "functionDescriptors")
        self.assertIn("ueFunctionParamContainerChildren", evidence["groups"]["functionDescriptors"]["missingKeys"])
        self.assertIn("ueReflectionPropertyValuesRuntime", evidence["groups"]["propertyValues"]["missingKeys"])
        self.assertIn(
            "luaReflectionLiveDescriptorTypedValuesRuntime",
            evidence["groups"]["luaReflectionBridge"]["missingKeys"],
        )

        rendered = module.markdown(summary)
        self.assertIn("## Reflection Runtime Evidence", rendered)
        self.assertIn("firstBlocked=`functionDescriptors`", rendered)

    def test_process_event_gap_requires_live_function_path_match(self):
        ready = {}
        for feature in module.FEATURES[:3]:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        hook_feature = next(feature for feature in module.FEATURES if feature["id"] == "process-event-hooks")
        for key in hook_feature["required"]:
            ready[key] = True
        ready["targetHooks"] = False
        ready["ueProcessEventLiveFunctionPath"] = False
        report = readiness_report(ready, missing_live=["ueProcessEventLiveFunctionPath"])

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "process-event-hooks")
        self.assertEqual(summary["nextCanaryRecommendation"]["maxStage"], "live-hook")
        self.assertIn("ueProcessEventLiveFunctionPath", by_id["process-event-hooks"]["missingRequiredKeys"])

    def test_process_event_gap_requires_active_validation(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        ready["ue4ssLuaApiComplete"] = False
        ready["ueProcessEventActiveValidation"] = False
        ready["ueCallFunctionActiveValidation"] = False
        report = readiness_report(
            ready,
            missing_live=[
                "ueProcessEventActiveValidation",
                "ueCallFunctionActiveValidation",
            ],
        )

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}
        hooks = by_id["process-event-hooks"]

        self.assertEqual(hooks["status"], "partial")
        self.assertIn("ueProcessEventActiveValidation", hooks["missingRequiredKeys"])
        self.assertIn("ueCallFunctionActiveValidation", hooks["missingRequiredKeys"])
        self.assertIn(
            "ueProcessEventActiveValidation",
            summary["processEventRuntimeEvidence"]["groups"]["hookTargets"]["missingKeys"],
        )
        self.assertIn(
            "ueCallFunctionActiveValidation",
            summary["processEventRuntimeEvidence"]["groups"]["hookTargets"]["missingKeys"],
        )
        self.assertIn(
            "ueProcessEventActiveValidation",
            summary["liveTargetImageContract"]["groups"]["runtimeProcessEventDispatch"]["missingKeys"],
        )
        self.assertIn(
            "ueCallFunctionActiveValidation",
            summary["liveTargetImageContract"]["groups"]["runtimeCallFunctionDispatch"]["missingKeys"],
        )

    def test_process_event_runtime_evidence_groups_missing_live_proof(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        ready["ue4ssLuaApiComplete"] = False
        ready["ueProcessEventLiveRuntimeContext"] = False
        ready["ueProcessEventLiveParamValues"] = False
        ready["ueProcessEventLuaContextHandles"] = False
        report = readiness_report(
            ready,
            missing_live=[
                "ueProcessEventLiveRuntimeContext",
                "ueProcessEventLiveParamValues",
                "ueProcessEventLuaContextHandles",
            ],
        )

        summary = module.summarize(report)
        evidence = summary["processEventRuntimeEvidence"]

        self.assertFalse(evidence["ready"])
        self.assertEqual(evidence["firstBlockedGroup"], "liveFunctionContext")
        self.assertIn("ueProcessEventLiveRuntimeContext", evidence["groups"]["liveFunctionContext"]["missingKeys"])
        self.assertIn("ueProcessEventLiveParamValues", evidence["groups"]["paramDecoding"]["missingKeys"])
        self.assertIn("ueProcessEventLuaContextHandles", evidence["groups"]["luaBridge"]["missingKeys"])

        rendered = module.markdown(summary)
        self.assertIn("## ProcessEvent Runtime Evidence", rendered)
        self.assertIn("firstBlocked=`liveFunctionContext`", rendered)
        self.assertIn("`paramDecoding`", rendered)
        self.assertIn("`luaBridge`", rendered)

    def test_lua_dispatch_runtime_evidence_groups_missing_bridge_proof(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        ready["ue4ssLuaApiComplete"] = False
        ready["luaProcessEventNativeInvoke"] = False
        ready["ueCallFunctionLiveLuaDispatch"] = False
        report = readiness_report(
            ready,
            missing_live=[
                "luaProcessEventNativeInvoke",
                "ueCallFunctionLiveLuaDispatch",
            ],
        )

        summary = module.summarize(report)
        evidence = summary["luaDispatchRuntimeEvidence"]

        self.assertFalse(evidence["ready"])
        self.assertEqual(evidence["firstBlockedGroup"], "processEventBridge")
        self.assertIn("luaProcessEventNativeInvoke", evidence["groups"]["processEventBridge"]["missingKeys"])
        self.assertIn("ueCallFunctionLiveLuaDispatch", evidence["groups"]["processEventBridge"]["missingKeys"])

        rendered = module.markdown(summary)
        self.assertIn("## Lua Dispatch Runtime Evidence", rendered)
        self.assertIn("firstBlocked=`processEventBridge`", rendered)

    def test_package_runtime_gap_recommends_package_loading_group(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(ready, missing_live=["luaLoadAssetPackageNativeExecutor"])
        report["ready"]["luaLoadAssetPackageNativeExecutor"] = False
        report["ready"]["ue4ssLuaApiComplete"] = False

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "package-loading")
        self.assertEqual(
            summary["nextCanaryRecommendation"]["liveTargetImageContractGroup"],
            "runtimePackageLoading",
        )
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedGroup"], "runtimePackageLoading")
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedFeature"], "package-loading")
        self.assertIn(
            "luaLoadAssetPackageNativeExecutor",
            summary["liveTargetImageContract"]["groups"]["runtimePackageLoading"]["missingKeys"],
        )
        package_blockers = {
            item["key"]: item["blocker"]
            for item in by_id["package-loading"]["blockers"]
        }
        self.assertIn("NativeExecutorReady=true", package_blockers["luaLoadAssetPackageNativeExecutor"])
        self.assertIn("ExecutorPreflightPassed=true", package_blockers["luaLoadAssetPackageNativeExecutor"])
        self.assertIn("FinalNativeCallEligible=true", package_blockers["luaLoadAssetPackageNativeExecutor"])

        report = readiness_report(ready, missing_live=["luaLoadAssetPackageNativeInvocation"])
        report["ready"]["luaLoadAssetPackageNativeInvocation"] = False
        summary = module.summarize(report)
        package_blockers = {
            item["key"]: item["blocker"]
            for item in {feature["id"]: feature for feature in summary["features"]}["package-loading"]["blockers"]
        }
        self.assertIn("nativeInvoked=true", package_blockers["luaLoadAssetPackageNativeInvocation"])
        self.assertIn("nativeReturnValidated=true", package_blockers["luaLoadAssetPackageNativeInvocation"])

    def test_package_loading_status_requires_load_class_package_subgates(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(ready, missing_live=["luaLoadClassPackageNativeInvocation"])
        report["ready"]["luaLoadClassPackageNativeInvocation"] = False
        report["ready"]["ue4ssLuaApiComplete"] = False

        summary = module.summarize(report)
        package = {feature["id"]: feature for feature in summary["features"]}["package-loading"]

        self.assertEqual(package["status"], "partial")
        self.assertIn("luaLoadClassPackageNativeInvocation", package["missingReadyKeys"])
        self.assertIn("luaLoadClassPackageNativeInvocation", package["missingRequiredKeys"])

    def test_quickest_path_to_one_to_one_names_package_anchor_route(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(
            ready,
            missing_live=["targetPackageLoadingSurface", "anchorCoveragePackageLoading"],
        )
        report["ready"]["targetPackageLoadingSurface"] = False
        report["ready"]["anchorCoveragePackageLoading"] = False
        report["ready"]["ue4ssLuaApiComplete"] = False

        summary = module.summarize(report)
        quickest = summary["quickestPathToOneToOne"]

        self.assertFalse(quickest["ready"])
        self.assertEqual(quickest["feature"], "package-loading")
        self.assertIn("1:1 UE4SS package-loading", quickest["goal"])
        self.assertIn("StaticLoadObject", quickest["path"])
        self.assertIn("LoadClass", quickest["path"])
        self.assertIn("guarded native", quickest["path"])
        self.assertIn("registry fallback", quickest["why"])
        self.assertIn("streamable", quickest["avoid"])

        rendered = module.markdown(summary)
        self.assertIn("## Quickest Path To 1:1", rendered)
        self.assertIn("StaticLoadObject", rendered)
        self.assertIn("guarded native LoadAsset/LoadClass", rendered)

    def test_package_quickest_path_includes_package_next_action_hint(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(
            ready,
            missing_live=["targetPackageLoadingSurface", "anchorCoveragePackageLoading"],
        )
        report["ready"]["targetPackageLoadingSurface"] = False
        report["ready"]["anchorCoveragePackageLoading"] = False
        report["ready"]["ue4ssLuaApiComplete"] = False
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "arm-trace",
            "confidence": "moderate",
            "reason": "runtime trace is the shortest path",
            "blockers": [
                "ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0",
                "route-slot recovery: missing route vtable static slot matches: 0x3a0, 0x3d8",
            ],
            "traceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "8",
            },
            "commands": [
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=8 scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=8 scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
            ],
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummaryJson": "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "prearmReadinessReady": False,
                "prearmReadinessNextStep": "operator must refresh the live preflight with coordinatorFreshPreflightCommand before arming the live package trace",
                "completionAuditNextClientGateClassification": {
                    "status": "pending",
                    "serverSideFallbackCandidate": "server-side-client-call-emulation",
                },
                "completionAuditNextRuntimeRootRecoveryPlan": {
                    "requiredLogPath": "/tmp/dune-server-probe-loader.log",
                    "missingKeys": ["runtimeRootDiscovery", "runtimeRootValidation"],
                    "preflightCommand": "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env",
                    "runCommand": "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env",
                },
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "coordinatorDryRunCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --dry-run --wait 30",
                "coordinatorFreshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                "coordinatorFreshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                "coordinatorCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
                "routeSlotTraceRequirement": {
                    "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                    "routeAddress": "0x129d58a2",
                    "reviewField": "routeVtableStaticSlotMatches",
                    "requiredSlots": ["0x3a0", "0x3d8"],
                    "requiredRegisters": ["rbx", "r14"],
                },
                "operatorWindow": {
                    "maxArmSeconds": 120,
                    "cleanupRequired": True,
                    "sequence": [
                        "preflight",
                        "arm",
                        "operator-client-login-travel-map-entry",
                        "status",
                        "cleanupCommand",
                        "no-debugger-check",
                    ],
                },
            },
            "outputFiles": {
                "nextCanaryJson": "/tmp/ue4ss-package-next-canary.json",
                "nextCanaryEnv": "/tmp/ue4ss-package-next-canary.env",
            },
            "nextStep": "capture a target-image package call frame",
        }

        summary = module.summarize(report, package_next_action=package_next_action)
        quickest = summary["quickestPathToOneToOne"]
        rendered = module.markdown(summary)

        self.assertEqual(quickest["feature"], "package-loading")
        self.assertEqual(quickest["packageNextAction"]["action"], "arm-trace")
        self.assertIn(
            "package-next-action: ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0",
            summary["blockers"],
        )
        self.assertIn(
            "package-next-action: route-slot recovery: missing route vtable static slot matches: 0x3a0, 0x3d8",
            summary["blockers"],
        )
        self.assertEqual(quickest["packageNextAction"]["liveTraceRunbook"]["commandCount"], 6)
        self.assertEqual(
            quickest["packageNextAction"]["liveTraceRunbook"]["operatorWindow"]["maxArmSeconds"],
            120,
        )
        self.assertEqual(
            quickest["packageNextAction"]["outputFiles"]["nextCanaryJson"],
            "/tmp/ue4ss-package-next-canary.json",
        )
        self.assertEqual(summary["nextSteps"][0], "package-loading quickest path: arm-trace")
        self.assertEqual(
            summary["nextSteps"][1],
            "live package trace dry-run: scripts/run-ue4ss-package-live-stimulus-trace.sh --dry-run --wait 30",
        )
        self.assertEqual(
            summary["nextSteps"][2],
            "live package trace fresh-log preflight: scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(
            summary["nextSteps"][3],
            "package prearm readiness ready: false",
        )
        self.assertEqual(
            summary["nextSteps"][4],
            "package prearm readiness next step: operator must refresh the live preflight with coordinatorFreshPreflightCommand before arming the live package trace",
        )
        self.assertEqual(
            summary["nextSteps"][5],
            "package origin classification: status=pending server-side fallback=server-side-client-call-emulation",
        )
        self.assertEqual(
            summary["nextSteps"][6],
            "runtime-root recovery required log: /tmp/dune-server-probe-loader.log",
        )
        self.assertEqual(
            summary["nextSteps"][7],
            "runtime-root recovery preflight: DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env",
        )
        self.assertEqual(
            summary["nextSteps"][8],
            "runtime-root recovery canary: DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env",
        )
        self.assertEqual(
            summary["nextSteps"][9],
            "live package trace fresh-log coordinator: scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(
            summary["nextSteps"][10],
            "live package trace coordinator: scripts/run-ue4ss-package-live-stimulus-trace.sh",
        )
        self.assertEqual(
            summary["nextSteps"][11],
            "live package trace runbook: operator-client-map-entry -> kspls0/dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
        )
        self.assertEqual(
            summary["nextSteps"][12],
            "package route-slot proof must capture UE4SS_PACKAGE_ROUTE_TRACE_HIT route=0x129d58a2 reviewField=routeVtableStaticSlotMatches slots=0x3a0,0x3d8 registers=rbx,r14",
        )
        self.assertEqual(
            summary["nextSteps"][13],
            "package promotion proof must preserve digest-bound runtime-trace env evidence: tracePid,sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
        )
        self.assertEqual(
            summary["nextSteps"][14],
            "verify package review bundle JSON: /tmp/ue4ss-package-review-bundle-verification.json",
        )
        self.assertEqual(
            quickest["packageNextAction"]["liveTraceRunbook"]["routeSlotTraceRequirement"]["requiredSlots"],
            ["0x3a0", "0x3d8"],
        )
        self.assertIn(
            "capture local package review summary: build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
            summary["nextSteps"],
        )
        self.assertIn(
            "local package review summary schema: dune-ue4ss-package-live-stimulus-review-summary/v1",
            summary["nextSteps"],
        )
        self.assertIn(
            f"local package review summary embedded evidence: {LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS}",
            summary["nextSteps"],
        )
        self.assertTrue(any("scripts/ue4ss-package-runtime-trace.sh arm" in step for step in summary["nextSteps"]))
        self.assertTrue(any("scripts/ue4ss-package-runtime-trace.sh status" in step for step in summary["nextSteps"]))
        self.assertIn("capture a target-image package call frame", summary["nextSteps"])
        self.assertIn("Package next action: `arm-trace`", rendered)
        self.assertIn("Package live trace runbook", rendered)
        self.assertIn("`operatorWindow.maxArmSeconds`: `120`", rendered)
        self.assertIn("`operatorWindow.sequence`: `preflight, arm, operator-client-login-travel-map-entry, status, cleanupCommand, no-debugger-check`", rendered)
        self.assertIn("`noDebuggerCheckCommand`", rendered)
        self.assertIn("`recommendedCandidate`: `operator-client-map-entry`", rendered)
        self.assertIn("`remote`: `kspls0`", rendered)
        self.assertIn("`container`: `dune_server-deep-desert-1`", rendered)
        self.assertIn("`coordinatorDryRunCommand`: `scripts/run-ue4ss-package-live-stimulus-trace.sh --dry-run --wait 30`", rendered)
        self.assertIn("`coordinatorFreshPreflightCommand`: `scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log`", rendered)
        self.assertIn("`coordinatorFreshTraceCommand`: `scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log`", rendered)
        self.assertIn("`coordinatorCommand`: `scripts/run-ue4ss-package-live-stimulus-trace.sh`", rendered)
        self.assertIn("`localReviewSummarySchemaVersion`: `dune-ue4ss-package-live-stimulus-review-summary/v1`", rendered)
        self.assertIn(f"`localReviewSummaryEmbeddedEvidenceFields`: `{LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS}`", rendered)
        self.assertIn("`localReviewSummaryRunbookMode`: `default-source-runbook;trace-log-override-effective-runbook`", rendered)
        self.assertIn("`routeSlotTraceRequirement`", rendered)
        self.assertIn("`expectedTraceMarker`: `UE4SS_PACKAGE_ROUTE_TRACE_HIT`", rendered)
        self.assertIn("`reviewField`: `routeVtableStaticSlotMatches`", rendered)
        self.assertIn("`requiredSlots`: `0x3a0,0x3d8`", rendered)
        self.assertIn("`requiredRegisters`: `rbx,r14`", rendered)
        self.assertIn("`cleanupCommand`", rendered)
        self.assertIn("concrete `tracePid`", rendered)
        self.assertIn("digest-bound `runtime-trace:` env evidence", rendered)
        self.assertIn("sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256", rendered)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject", rendered)
        self.assertIn("scripts/ue4ss-package-runtime-trace.sh arm", rendered)
        self.assertIn("Package output file: `nextCanaryJson=/tmp/ue4ss-package-next-canary.json`", rendered)

    def test_package_next_action_rejects_malformed_live_trace_runbook(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 0,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.commandCount"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_missing_live_trace_cleanup_command(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.cleanupCommand"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_stale_live_trace_runbook_digest_fields(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.digestProvenanceFields"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_stale_live_trace_cleanup_anchor(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.cleanupCommand must include"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_non_unique_live_trace_log(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.traceLog must use timestamped"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_missing_operator_window(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.operatorWindow must be an object"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_stale_operator_window_sequence(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
                "operatorWindow": {
                    "maxArmSeconds": 120,
                    "cleanupRequired": True,
                    "sequence": ["preflight", "arm", "status"],
                },
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.operatorWindow.sequence"):
            module.validate_package_next_action(package_next_action)

    def test_package_next_action_rejects_missing_prearm_readiness_contract(self):
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "recover-package-anchor",
            "liveTraceRunbook": {
                "commandCount": 6,
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T211300Z.log",
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
                "operatorWindow": {
                    "maxArmSeconds": 120,
                    "cleanupRequired": True,
                    "sequence": [
                        "preflight",
                        "arm",
                        "operator-client-login-travel-map-entry",
                        "status",
                        "cleanupCommand",
                        "no-debugger-check",
                    ],
                },
            },
        }

        with self.assertRaisesRegex(ValueError, "liveTraceRunbook.prearmReadinessJson"):
            module.validate_package_next_action(package_next_action)

    def test_package_quickest_path_surfaces_promotion_summary_errors(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(
            ready,
            missing_live=["targetPackageLoadingSurface", "anchorCoveragePackageLoading"],
        )
        report["ready"]["targetPackageLoadingSurface"] = False
        report["ready"]["anchorCoveragePackageLoading"] = False
        report["ready"]["ue4ssLuaApiComplete"] = False
        package_next_action = {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "complete-review",
            "confidence": "high",
            "reason": "package promotion summary has validation errors",
            "promotionSummaryErrors": [
                {
                    "path": "/tmp/families/LoadPackage/promotion-env.json",
                    "error": "package promotion env must be an object",
                }
            ],
            "commands": ["scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log"],
            "nextStep": "fix malformed package promotion review metadata",
        }

        summary = module.summarize(report, package_next_action=package_next_action)
        package_hint = summary["quickestPathToOneToOne"]["packageNextAction"]
        rendered = module.markdown(summary)

        self.assertEqual(
            package_hint["promotionSummaryErrors"][0]["error"],
            "package promotion env must be an object",
        )
        self.assertEqual(
            summary["nextSteps"][1],
            "package promotion metadata error: /tmp/families/LoadPackage/promotion-env.json: package promotion env must be an object",
        )
        self.assertIn("Package promotion metadata error", rendered)
        self.assertIn("package promotion env must be an object", rendered)

    def test_quickest_path_prefers_package_when_anchor_coverage_has_only_package_missing(self):
        report = readiness_report(
            {
                "targetImageProcess": True,
                "runtimeRootDiscovery": False,
                "targetObjectDiscovery": False,
                "targetHooks": False,
                "targetPackageLoadingSurface": False,
                "anchorCoveragePackageLoading": False,
                "ue4ssLuaApiComplete": False,
            },
            missing_live=[
                "runtimeRootDiscovery",
                "targetObjectDiscovery",
                "targetHooks",
                "targetPackageLoadingSurface",
                "anchorCoveragePackageLoading",
            ],
        )
        report["anchorCoverage"] = {
            "provided": True,
            "readyForTargetObjectDiscovery": True,
            "readyForTargetHookPlanning": True,
            "readyForTargetPackageLoading": False,
            "groups": {
                "objects": {"targetPresent": 1, "total": 1, "targetComplete": True},
                "dispatch": {"targetPresent": 1, "total": 1, "targetComplete": True},
                "package": {"targetPresent": 0, "total": 7, "targetComplete": False},
            },
        }

        summary = module.summarize(report)
        quickest = summary["quickestPathToOneToOne"]

        self.assertEqual(quickest["feature"], "package-loading")
        self.assertEqual(quickest["missingTargetGroups"], ["package"])
        self.assertIn("StaticLoadObject", quickest["path"])

    def test_load_class_package_gap_reports_call_frame_target_ready_requirements(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(ready, missing_live=["luaLoadClassPackageCallFrameVerification"])
        report["ready"]["luaLoadClassPackageCallFrameVerification"] = False

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}
        package_blockers = {
            item["key"]: item["blocker"]
            for item in by_id["package-loading"]["blockers"]
        }

        self.assertIn("targetImage=true", package_blockers["luaLoadClassPackageCallFrameVerification"])
        self.assertIn("abiVerified=true", package_blockers["luaLoadClassPackageCallFrameVerification"])
        self.assertIn("classRootReady=true", package_blockers["luaLoadClassPackageCallFrameVerification"])
        self.assertIn("callFrameReady=true", package_blockers["luaLoadClassPackageCallFrameVerification"])

    def test_anchor_coverage_gaps_have_actionable_blockers(self):
        report = readiness_report(
            {
                "targetImageProcess": False,
                "runtimeRootDiscovery": False,
                "targetObjectDiscovery": False,
                "targetPackageLoadingSurface": False,
                "anchorCoverageObjectDiscovery": False,
                "anchorCoveragePackageLoading": False,
            },
            missing_live=[
                "targetImageProcess",
                "runtimeRootDiscovery",
                "targetObjectDiscovery",
                "targetPackageLoadingSurface",
                "anchorCoverageObjectDiscovery",
                "anchorCoveragePackageLoading",
            ],
        )

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}
        runtime_blockers = {
            item["key"]: item["blocker"]
            for item in by_id["runtime-anchors"]["blockers"]
        }
        package_blockers = {
            item["key"]: item["blocker"]
            for item in by_id["package-loading"]["blockers"]
        }

        self.assertIn("--exe-substring", runtime_blockers["targetImageProcess"])
        self.assertIn("target-image FNamePool", runtime_blockers["runtimeRootDiscovery"])
        self.assertIn("target-image names", runtime_blockers["anchorCoverageObjectDiscovery"])
        self.assertIn("--anchor-coverage-json", runtime_blockers["anchorCoverageObjectDiscovery"])
        self.assertIn("StaticLoadObject", package_blockers["targetPackageLoadingSurface"])
        self.assertIn("target-image package-loading", package_blockers["anchorCoveragePackageLoading"])
        self.assertIn("--anchor-coverage-json", package_blockers["anchorCoveragePackageLoading"])

    def test_runtime_root_recovery_plan_is_emitted_when_discovery_not_run(self):
        report = readiness_report(
            {
                "targetImageProcess": True,
                "runtimeRootDiscovery": False,
                "runtimeRootValidation": False,
                "targetObjectDiscovery": False,
                "anchorCoverageObjectDiscovery": False,
            },
            missing_live=[
                "runtimeRootDiscovery",
                "runtimeRootValidation",
                "targetObjectDiscovery",
                "anchorCoverageObjectDiscovery",
            ],
        )
        report["runtimeDiscovery"] = {
            "candidateCount": 0,
            "failureCounts": {"not-run": 1},
            "candidateLocations": [],
        }
        report["anchorCoverage"] = {"provided": False}

        summary = module.summarize(report)
        plan = summary["runtimeRootRecoveryPlan"]
        rendered = module.markdown(summary)

        self.assertTrue(plan["needed"])
        self.assertEqual(plan["action"], "recover-runtime-roots")
        self.assertEqual(plan["immediatePlatform"], "server")
        self.assertTrue(plan["blockedByMissingLog"])
        self.assertEqual(plan["requiredLogPath"], "/tmp/dune-server-probe-loader.log")
        self.assertIn("runtimeRootDiscovery", plan["missingKeys"])
        self.assertEqual(plan["currentEvidence"]["runtimeDiscoveryCandidateCount"], 0)
        self.assertEqual(plan["currentEvidence"]["runtimeDiscoveryFailureCounts"], {"not-run": 1})
        self.assertIn("--max-stage read-only", plan["renderedCommands"]["server"])
        self.assertEqual(
            plan["outputFiles"]["nextCanaryJson"],
            "build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.json",
        )
        self.assertIn("scripts/canary-linux-server-loader.sh", plan["canaryWrapper"]["runCommand"])
        self.assertEqual(plan["preflightCommand"], plan["canaryWrapper"]["preflightCommand"])
        self.assertEqual(plan["runCommand"], plan["canaryWrapper"]["runCommand"])
        self.assertNotIn("DUNE_LINUX_SERVER_CANARY_PLAN_JSON=", plan["preflightCommand"])
        self.assertNotIn("DUNE_LINUX_SERVER_CANARY_PLAN_JSON=", plan["runCommand"])
        self.assertNotIn("DUNE_LINUX_SERVER_CANARY_PLAN_JSON=", plan["canaryWrapper"]["runCommand"])
        self.assertIn("DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true", plan["canaryWrapper"]["runCommand"])
        self.assertIn("DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS=180", plan["canaryWrapper"]["runCommand"])
        self.assertIn("DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=true", plan["canaryWrapper"]["preflightCommand"])
        self.assertEqual(plan["currentEvidence"]["requiredCaptureDelaySeconds"], 180)
        self.assertIn("90-second delayed UE root validation", plan["currentEvidence"]["reasonForCaptureDelay"])
        self.assertEqual(plan["postCanaryVerificationOutputs"]["readinessJson"], "ue4ss-readiness.json")
        self.assertIn("scripts/plan-ue4ss-canary-env.py", summary["nextSteps"][0])
        self.assertIn("Runtime Root Recovery", rendered)
        self.assertIn("Blocked by missing scoped log", rendered)
        self.assertIn("Guarded canary wrapper", rendered)
        self.assertIn("DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true", rendered)
        self.assertIn("Post-canary outputs", rendered)
        self.assertIn("target-image RuntimeFNamePool", rendered)

    def test_runtime_root_recovery_consumes_next_canary_after_log_exists(self):
        report = readiness_report()
        report["ready"]["runtimeRootDiscovery"] = False
        report["ready"]["runtimeRootValidation"] = False
        report["ready"]["targetObjectDiscovery"] = False
        report["runtimeDiscovery"] = {
            "candidateCount": 0,
            "failureCounts": {"no-root-hits": 1},
        }
        report["anchorCoverage"] = {"provided": True}

        summary = module.summarize(report)
        plan = summary["runtimeRootRecoveryPlan"]

        self.assertFalse(plan["blockedByMissingLog"])
        self.assertIn(
            "DUNE_LINUX_SERVER_CANARY_PLAN_JSON=build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.json",
            plan["preflightCommand"],
        )
        self.assertIn(
            "DUNE_LINUX_SERVER_CANARY_PLAN_JSON=build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.json",
            plan["runCommand"],
        )
        self.assertIn("DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS=180", plan["runCommand"])

    def test_object_registry_recovery_plan_is_emitted_when_find_object_semantics_are_incomplete(self):
        report = readiness_report()
        for key in (
            "targetImageProcess",
            "runtimeRootDiscovery",
            "runtimeRootValidation",
            "targetObjectDiscovery",
            "objectDiscovery",
            "objectDiscoveryCoverage",
            "luaObjectRegistryRuntime",
            "luaFunctionRegistryRuntime",
            "luaDecodedObjectAliasesRuntime",
            "ueObjectArrayShape",
            "ueObjectArrayRegistryRuntime",
            "ueObjectNativeIdentities",
            "ueObjectInternalFlags",
            "ueFNameDecoder",
            "luaFunctionIterationRuntime",
        ):
            report["ready"][key] = True
        for key in (
            "findObjectSemantics",
            "luaObjectOuterChainIdentities",
            "luaObjectApi",
            "luaStaticConstructObjectNativeExecutorState",
            "luaStaticConstructObjectNativeExecutorReady",
            "luaStaticConstructObjectNativeInvoke",
        ):
            report["ready"][key] = False
        report["objectDiscoveryCoverage"] = {
            "schemaVersion": "dune-ue-object-discovery-coverage/v1",
            "readyForObjectDiscovery": True,
            "readyForFindObjectSemantics": False,
            "missingObjectDiscoveryComponents": [],
            "missingFindObjectComponents": ["outerChainIdentities", "luaFindObjectApi"],
        }

        summary = module.summarize(report)
        plan = summary["objectRegistryRecoveryPlan"]
        rendered = module.markdown(summary)

        self.assertTrue(plan["needed"])
        self.assertEqual(plan["action"], "recover-object-registry-semantics")
        self.assertIn("findObjectSemantics", plan["missingKeys"])
        self.assertTrue(plan["currentEvidence"]["targetObjectDiscovery"])
        self.assertFalse(plan["currentEvidence"]["findObjectSemantics"])
        self.assertEqual(
            plan["currentEvidence"]["missingFindObjectComponents"],
            ["outerChainIdentities", "luaFindObjectApi"],
        )
        self.assertIn("--max-stage lua-dispatch", plan["renderedCommands"]["server"])
        self.assertEqual(
            plan["outputFiles"]["nextCanaryJson"],
            "build/server-current-anchor-prep/ue4ss-object-registry-next-canary.json",
        )
        self.assertIn("DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true", plan["runCommand"])
        self.assertIn("DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS=180", plan["runCommand"])
        self.assertEqual(plan["currentEvidence"]["requiredCaptureDelaySeconds"], 180)
        self.assertIn("90-second delayed UE root/object validation", plan["currentEvidence"]["reasonForCaptureDelay"])
        self.assertIn("follow-up runtime root scan", plan["currentEvidence"]["reasonForCaptureDelay"])
        self.assertIn("scripts/plan-ue4ss-canary-env.py", summary["nextSteps"][0])
        self.assertIn("Object Registry Recovery", rendered)
        self.assertIn("StaticConstructObject native executor", rendered)

    def test_object_registry_recovery_plan_not_needed_when_feature_is_ready(self):
        report = readiness_report()
        for key in (
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
        ):
            report["ready"][key] = True

        summary = module.summarize(report)

        self.assertFalse(summary["objectRegistryRecoveryPlan"]["needed"])

    def test_anchor_coverage_summary_preserves_target_loader_provenance(self):
        summary = module.summarize(readiness_report())
        coverage = summary["anchorCoverage"]

        self.assertTrue(coverage["provided"])
        self.assertFalse(coverage["readyForTargetObjectDiscovery"])
        self.assertEqual(coverage["groups"]["names"]["targetPresent"], 0)
        self.assertEqual(coverage["groups"]["names"]["loaderPresent"], 1)
        self.assertEqual(coverage["groups"]["dispatch"]["unknownPresent"], 1)
        self.assertIn("names", coverage["missingTargetGroups"])
        self.assertIn("dispatch", coverage["loaderOrUnknownOnlyGroups"])

        rendered = module.markdown(summary)
        self.assertIn("## Anchor Coverage", rendered)
        self.assertIn("Missing target groups", rendered)
        self.assertIn("Loader/unknown-only groups", rendered)
        self.assertIn("`names` target=`0/1` loader=`1` unknown=`0`", rendered)

    def test_call_function_runtime_gap_recommends_hook_group(self):
        ready = {}
        for feature in module.FEATURES:
            for key in feature["ready"] + feature["required"]:
                ready[key] = True
        report = readiness_report(ready, missing_live=["ueCallFunctionLiveLuaDispatch"])
        report["ready"]["ueCallFunctionLiveLuaDispatch"] = False
        report["ready"]["ue4ssLuaApiComplete"] = False

        summary = module.summarize(report)
        by_id = {feature["id"]: feature for feature in summary["features"]}

        self.assertEqual(summary["nextCanaryRecommendation"]["feature"], "process-event-hooks")
        self.assertEqual(
            summary["nextCanaryRecommendation"]["liveTargetImageContractGroup"],
            "runtimeCallFunctionDispatch",
        )
        self.assertEqual(summary["liveTargetImageContract"]["firstBlockedGroup"], "runtimeCallFunctionDispatch")
        self.assertIn(
            "ueCallFunctionLiveLuaDispatch",
            summary["liveTargetImageContract"]["groups"]["runtimeCallFunctionDispatch"]["missingKeys"],
        )
        self.assertIn(
            "ueCallFunctionLiveLuaDispatch",
            by_id["lua-mod-dispatch"]["missingRequiredKeys"],
        )

    def test_gap_summary_includes_root_recovery_candidate_coverage(self):
        summary = module.summarize(
            readiness_report(),
            [canary_plan(["world", "dispatch", "package", "reflection"])],
        )

        coverage = summary["rootRecoveryCandidateCoverage"]
        self.assertTrue(coverage["provided"])
        self.assertEqual(coverage["missingGroups"], ["dispatch", "package", "reflection", "world"])
        self.assertEqual(coverage["anchorCounts"], {"FNamePool": 1, "GUObjectArray": 2})
        by_id = {feature["id"]: feature for feature in summary["features"]}
        self.assertEqual(by_id["runtime-anchors"]["candidateMissingGroups"], ["world"])
        self.assertEqual(by_id["reflection"]["candidateMissingGroups"], ["reflection"])
        self.assertEqual(by_id["process-event-hooks"]["candidateMissingGroups"], ["dispatch"])
        self.assertEqual(by_id["package-loading"]["candidateMissingGroups"], ["package"])
        rendered = module.markdown(summary)
        self.assertIn("Root-Recovery Candidate Coverage", rendered)
        self.assertIn("candidate missing groups", rendered)

    def test_gap_summary_aggregates_candidate_groups_across_platform_plans(self):
        windows = canary_plan(["world", "dispatch"])
        server = canary_plan(["package", "reflection"])
        server["platform"] = "server"
        server["nextCanaryContract"]["rootRecoveryCandidateInput"]["anchorCounts"] = {"GWorld": 1, "ProcessEvent": 1}

        summary = module.summarize(readiness_report(), [windows, server])

        coverage = summary["rootRecoveryCandidateCoverage"]
        self.assertEqual(coverage["missingGroups"], [])
        self.assertIn("world", coverage["readyGroups"])
        self.assertIn("dispatch", coverage["readyGroups"])
        self.assertEqual(coverage["anchorCounts"], {"FNamePool": 1, "GUObjectArray": 2, "GWorld": 1, "ProcessEvent": 1})

    def test_gap_summary_preserves_live_candidate_outcome_filtering(self):
        plan = canary_plan(["world"])
        root = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        root["outcomeSourcePaths"] = ["/tmp/candidate-outcomes.json"]
        root["filteredRejectedShapeCount"] = 2
        root["filteredRejectedCandidateCount"] = 2
        root["filteredRejectedShapeOnlyCount"] = 1
        root["filteredRejectedOutcomeCount"] = 1

        summary = module.summarize(readiness_report(), [plan])

        coverage = summary["rootRecoveryCandidateCoverage"]
        self.assertEqual(coverage["filteredRejectedCandidateCount"], 2)
        self.assertEqual(coverage["filteredRejectedShapeOnlyCount"], 1)
        self.assertEqual(coverage["filteredRejectedOutcomeCount"], 1)
        self.assertEqual(coverage["sourcePaths"]["outcome"], ["/tmp/candidate-outcomes.json"])
        self.assertEqual(coverage["plans"][0]["filteredRejectedOutcomeCount"], 1)
        rendered = module.markdown(summary)
        self.assertIn("outcome=1", rendered)
        self.assertIn("/tmp/candidate-outcomes.json", rendered)

    def test_gap_summary_threads_candidate_outcomes_into_planner_commands(self):
        summary = module.summarize(
            readiness_report(),
            candidate_outcome_paths=["/tmp/candidate-outcomes.json"],
        )

        self.assertEqual(summary["candidateOutcomeInputs"], ["/tmp/candidate-outcomes.json"])
        recommendation = summary["nextCanaryRecommendation"]
        self.assertEqual(recommendation["candidateOutcomeInputs"], ["/tmp/candidate-outcomes.json"])
        for command in recommendation["plannerCommands"].values():
            self.assertIn("--candidate-outcomes-json", command)
            self.assertIn("/tmp/candidate-outcomes.json", command)
        rendered = module.markdown(summary)
        self.assertIn("Candidate outcome inputs", rendered)
        self.assertIn("/tmp/candidate-outcomes.json", rendered)

    def test_gap_summary_rejects_malformed_candidate_outcome_paths(self):
        for path, message in (
            ("", "candidate outcome inputs[0] must be a non-empty single-line path"),
            ("/tmp/candidate-outcomes.json\n/tmp/other.json", "candidate outcome inputs[0] must be a non-empty single-line path"),
        ):
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as raised:
                    module.summarize(readiness_report(), candidate_outcome_paths=[path])

                self.assertIn(message, str(raised.exception))

    def test_gap_summary_threads_target_filters_into_planner_commands(self):
        report = readiness_report()
        report["targetImageSubstrings"] = ["ExampleGame"]

        summary = module.summarize(report)

        recommendation = summary["nextCanaryRecommendation"]
        self.assertEqual(recommendation["targetImageSubstrings"], ["ExampleGame"])
        for command in recommendation["plannerCommands"].values():
            self.assertIn("--exe-substring", command)
            self.assertIn("ExampleGame", command)
        rendered = module.markdown(summary)
        self.assertIn("Recommended target filters", rendered)
        self.assertIn("ExampleGame", rendered)

    def test_gap_summary_quotes_planner_commands_in_markdown(self):
        report = readiness_report()
        report["targetImageSubstrings"] = ["Example Game"]

        summary = module.summarize(
            report,
            candidate_outcome_paths=["/tmp/candidate outcomes.json"],
        )

        command = summary["nextCanaryRecommendation"]["plannerCommands"]["server"]
        self.assertIn("Example Game", command)
        self.assertIn("/tmp/candidate outcomes.json", command)
        rendered = module.markdown(summary)
        self.assertIn("'Example Game'", rendered)
        self.assertIn("'/tmp/candidate outcomes.json'", rendered)

    def test_gap_summary_rejects_malformed_target_filters(self):
        for value, message in (
            ("", "target image filters[0] must be a non-empty single-line scalar"),
            ("ExampleGame\nOtherGame", "target image filters[0] must be a non-empty single-line scalar"),
            (["ExampleGame"], "target image filters[0] must be a non-empty single-line scalar"),
        ):
            with self.subTest(value=value):
                report = readiness_report()
                report["targetImageSubstrings"] = [value]

                with self.assertRaises(ValueError) as raised:
                    module.summarize(report)

                self.assertIn(message, str(raised.exception))

    def test_gap_summary_rejects_malformed_readiness_next_steps(self):
        cases = (
            ("recover live runtime roots", "readiness nextSteps must be a list"),
            ([42], "readiness nextSteps[0] must be a non-empty single-line string"),
            (["recover roots\nrun hooks"], "readiness nextSteps[0] must be a non-empty single-line string"),
        )
        for next_steps, message in cases:
            with self.subTest(message=message):
                report = readiness_report()
                report["nextSteps"] = next_steps

                with self.assertRaises(ValueError) as raised:
                    module.summarize(report)

                self.assertIn(message, str(raised.exception))

    def test_gap_summary_counts_runtime_candidate_carry_forward(self):
        summary = module.summarize(readiness_report(), [runtime_carry_forward_plan()])

        coverage = summary["rootRecoveryCandidateCoverage"]
        self.assertTrue(coverage["provided"])
        self.assertIn("names", coverage["readyGroups"])
        self.assertIn("objects", coverage["missingGroups"])
        self.assertEqual(coverage["anchorCounts"], {"RuntimeFNamePool": 1})
        self.assertEqual(coverage["plans"][0]["runtimeCarryForwardEntryCount"], 1)
        self.assertEqual(coverage["plans"][0]["runtimeCarryForwardEntries"], ["RuntimeFNamePool=0x60000"])
        self.assertTrue(coverage["plans"][0]["groupCoverage"]["names"]["ready"])
        self.assertNotIn("names", coverage["plans"][0]["missingGroups"])
        rendered = module.markdown(summary)
        self.assertIn("runtimeCarry=`1`", rendered)
        self.assertIn("RuntimeFNamePool=0x60000", rendered)

    def test_canary_plan_loader_rejects_non_canary_artifacts(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_canary_plan(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "plan-canary",
                },
                "next-canary.json",
            )

        self.assertIn("expected 'dune-ue4ss-canary-env-plan/v1'", str(raised.exception))

    def test_canary_plan_loader_rejects_malformed_candidate_contract(self):
        cases = (
            (
                {"schemaVersion": "dune-ue4ss-canary-env-plan/v1", "nextCanaryContract": []},
                "nextCanaryContract must be an object",
            ),
            (
                {
                    "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
                    "nextCanaryContract": {"rootRecoveryCandidateInput": []},
                },
                "rootRecoveryCandidateInput must be an object",
            ),
            (
                {
                    "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
                    "nextCanaryContract": {
                        "rootRecoveryCandidateInput": {"sourcePaths": "/tmp/candidates.json"}
                    },
                },
                "rootRecoveryCandidateInput.sourcePaths must be a list",
            ),
            (
                {
                    "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
                    "nextCanaryContract": {
                        "rootRecoveryCandidateInput": {"missingGroups": ["names", 42]}
                    },
                },
                "rootRecoveryCandidateInput.missingGroups[1] must be a string",
            ),
            (
                {
                    "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
                    "nextCanaryContract": {
                        "rootRecoveryCandidateInput": {"candidateCount": -1}
                    },
                },
                "rootRecoveryCandidateInput.candidateCount must be a non-negative integer",
            ),
            (
                {
                    "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
                    "nextCanaryContract": {
                        "runtimeCandidateCarryForward": {"anchorCounts": []}
                    },
                },
                "runtimeCandidateCarryForward.anchorCounts must be an object",
            ),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as raised:
                    module.validate_canary_plan(payload, "next-canary.json")

                self.assertIn(message, str(raised.exception))

    def test_canary_plan_loader_accepts_root_recovery_plan(self):
        plan = module.validate_canary_plan(canary_plan(["world"]), "next-canary.json")

        self.assertEqual(plan["schemaVersion"], "dune-ue4ss-canary-env-plan/v1")
        self.assertEqual(
            plan["nextCanaryContract"]["rootRecoveryCandidateInput"]["missingGroups"],
            ["world"],
        )

    def test_canary_plan_loader_requires_post_canary_inventory_outputs(self):
        cases = (
            (
                {"evidenceInventoryJson": None},
                "postCanaryVerification.outputFiles.evidenceInventoryJson must be a string",
            ),
            (
                {"evidenceInventory": "ue4ss-evidence-inventory-old.md"},
                "postCanaryVerification.outputFiles.evidenceInventory must be ue4ss-evidence-inventory.md",
            ),
            (
                {"postCanarySummary": "post-canary-summary.md\nold"},
                "postCanaryVerification.outputFiles.postCanarySummary must be a non-empty single-line string",
            ),
        )
        for overrides, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as raised:
                    module.validate_canary_plan(
                        add_post_canary_verification(canary_plan(["world"]), overrides),
                        "next-canary.json",
                    )

                self.assertIn(message, str(raised.exception))

    def test_canary_plan_loader_accepts_post_canary_inventory_outputs(self):
        plan = module.validate_canary_plan(
            add_post_canary_verification(canary_plan(["world"])),
            "next-canary.json",
        )

        output_files = plan["nextCanaryContract"]["postCanaryVerification"]["outputFiles"]
        self.assertEqual(output_files["evidenceInventoryJson"], "ue4ss-evidence-inventory.json")
        self.assertEqual(output_files["evidenceInventory"], "ue4ss-evidence-inventory.md")

    def test_readiness_json_loader_rejects_non_readiness_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ue4ss-evidence-inventory.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-evidence-inventory/v1",
                        "readyForPackageLoading": False,
                    }
                ),
                encoding="utf-8",
            )
            args = types.SimpleNamespace(
                readiness_json=path,
                log=[],
                client_log=[],
                server_log=[],
                loader=[],
                pid=[],
                exe_substring=[],
                signature_validation_json=[],
                anchor_coverage_json=[],
            )

            with self.assertRaises(SystemExit) as raised:
                module.build_readiness(args)

        self.assertIn("expected 'dune-ue4ss-port-readiness/v1'", str(raised.exception))

    def test_readiness_json_loader_accepts_real_readiness_schema(self):
        report = readiness_report()
        report["schemaVersion"] = "dune-ue4ss-port-readiness/v1"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ue4ss-readiness.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            args = types.SimpleNamespace(
                readiness_json=path,
                log=[],
                client_log=[],
                server_log=[],
                loader=[],
                pid=[],
                exe_substring=[],
                signature_validation_json=[],
                anchor_coverage_json=[],
            )

            loaded = module.build_readiness(args)

        self.assertEqual(loaded["schemaVersion"], "dune-ue4ss-port-readiness/v1")
        self.assertIn("ready", loaded)

    def test_readiness_json_loader_overlays_anchor_coverage_sidecar(self):
        report = readiness_report()
        report["schemaVersion"] = "dune-ue4ss-port-readiness/v1"
        report["ready"]["anchorCoverageObjectDiscovery"] = False
        report["ready"]["anchorCoverageHookPlanning"] = False
        report["ready"]["anchorCoveragePackageLoading"] = False
        coverage = {
            "schemaVersion": "dune-ue-anchor-coverage/v1",
            "groups": {
                "names": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 4},
                "objects": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 4},
                "world": {"present": 2, "targetPresent": 2, "loaderPresent": 0, "unknownPresent": 0, "total": 2},
                "dispatch": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 4},
                "package": {"present": 0, "targetPresent": 0, "loaderPresent": 0, "unknownPresent": 0, "total": 7},
            },
            "readyForTargetObjectDiscovery": True,
            "readyForTargetHookPlanning": True,
            "readyForTargetPackageLoading": False,
            "combinedAnchors": ["FNamePool", "GUObjectArray", "GWorld", "GEngine", "ProcessEvent"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            readiness_path = temp / "ue4ss-readiness.json"
            coverage_path = temp / "anchor-coverage.json"
            readiness_path.write_text(json.dumps(report), encoding="utf-8")
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            args = types.SimpleNamespace(
                readiness_json=readiness_path,
                log=[],
                client_log=[],
                server_log=[],
                loader=[],
                pid=[],
                exe_substring=[],
                signature_validation_json=[],
                anchor_coverage_json=[coverage_path],
            )

            loaded = module.build_readiness(args)

        self.assertTrue(loaded["anchorCoverage"]["provided"])
        self.assertTrue(loaded["ready"]["anchorCoverageObjectDiscovery"])
        self.assertTrue(loaded["ready"]["anchorCoverageHookPlanning"])
        self.assertFalse(loaded["ready"]["anchorCoveragePackageLoading"])
        object_gate = next(item for item in loaded["gates"] if item["name"] == "anchor-coverage-object-discovery")
        package_gate = next(item for item in loaded["gates"] if item["name"] == "anchor-coverage-package-loading")
        self.assertTrue(object_gate["passed"])
        self.assertIn("targetReady=True", object_gate["evidence"])
        self.assertFalse(package_gate["passed"])
        self.assertIn("package-loading anchor evidence", package_gate["blocker"])
        live_group = loaded["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]
        self.assertNotIn("anchorCoverageObjectDiscovery", live_group["missingKeys"])
        self.assertIn("anchorCoveragePackageLoading", loaded["liveTargetImageCanaryContract"]["missingKeys"])

    def test_readiness_json_loader_accepts_evidence_inventory_anchor_coverage_sidecar(self):
        report = readiness_report()
        report["schemaVersion"] = "dune-ue4ss-port-readiness/v1"
        for key in (
            "objectDiscovery",
            "runtimeRootDiscovery",
            "runtimeRootValidation",
            "targetNames",
            "targetObjects",
            "targetWorld",
        ):
            report["ready"][key] = True
        report["ready"]["targetDispatch"] = False
        report["ready"]["targetObjectDiscovery"] = False
        report["ready"]["anchorCoverageObjectDiscovery"] = False
        report["ready"]["anchorCoverageHookPlanning"] = False
        report["ready"]["anchorCoveragePackageLoading"] = False
        inventory = {
            "schemaVersion": "dune-ue4ss-evidence-inventory/v1",
            "best": {
                "anchorCoverage": {
                    "schemaVersion": "dune-ue-anchor-coverage/v1",
                    "provided": True,
                    "readyForTargetObjectDiscovery": True,
                    "readyForTargetHookPlanning": True,
                    "readyForTargetPackageLoading": False,
                    "targetCoverageFieldsPresent": True,
                    "presentGroups": ["names", "objects", "world", "dispatch"],
                    "groups": {
                        "names": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 4},
                        "objects": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 4},
                        "world": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 2},
                        "dispatch": {"present": 1, "targetPresent": 1, "loaderPresent": 0, "unknownPresent": 0, "total": 4},
                        "package": {"present": 0, "targetPresent": 0, "loaderPresent": 0, "unknownPresent": 0, "total": 7},
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            readiness_path = temp / "ue4ss-readiness.json"
            inventory_path = temp / "ue4ss-evidence-inventory.json"
            readiness_path.write_text(json.dumps(report), encoding="utf-8")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            args = types.SimpleNamespace(
                readiness_json=readiness_path,
                log=[],
                client_log=[],
                server_log=[],
                loader=[],
                pid=[],
                exe_substring=[],
                signature_validation_json=[],
                anchor_coverage_json=[inventory_path],
            )

            loaded = module.build_readiness(args)

        self.assertTrue(loaded["ready"]["anchorCoverageObjectDiscovery"])
        self.assertTrue(loaded["ready"]["anchorCoverageHookPlanning"])
        self.assertFalse(loaded["ready"]["anchorCoveragePackageLoading"])
        self.assertTrue(loaded["ready"]["targetObjectDiscovery"])
        self.assertEqual(loaded["anchorCoverage"]["combinedAnchorCount"], 4)
        self.assertEqual(loaded["anchorCoverage"]["explicitAnchorCount"], 0)

    def test_readiness_validator_rejects_string_booleans_in_live_contract(self):
        report = readiness_report()
        report["liveTargetImageCanaryContract"]["ready"] = "false"

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn("liveTargetImageCanaryContract.ready must be a boolean", str(raised.exception))

    def test_readiness_validator_rejects_malformed_live_contract_groups(self):
        report = readiness_report()
        report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]["ready"] = "false"

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn(
            "liveTargetImageCanaryContract.groups.targetImageAnchors.ready must be a boolean",
            str(raised.exception),
        )

    def test_readiness_validator_rejects_live_contract_ready_with_missing_keys(self):
        report = readiness_report()
        report["liveTargetImageCanaryContract"]["ready"] = True
        report["liveTargetImageCanaryContract"]["missingKeys"] = ["runtimeRootDiscovery"]

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn(
            "liveTargetImageCanaryContract.ready cannot be true while missingKeys is non-empty",
            str(raised.exception),
        )

    def test_readiness_validator_rejects_live_contract_ready_with_blocked_group(self):
        report = readiness_report()
        report["liveTargetImageCanaryContract"]["ready"] = True
        report["liveTargetImageCanaryContract"]["missingKeys"] = []
        report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]["ready"] = False

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn(
            "liveTargetImageCanaryContract.ready cannot be true while group targetImageAnchors is not ready",
            str(raised.exception),
        )

    def test_readiness_validator_rejects_ready_live_contract_group_with_missing_keys(self):
        report = readiness_report()
        group = report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]
        group["ready"] = True
        group["missingKeys"] = ["targetImageProcess"]

        with self.assertRaises(ValueError) as raised:
            module.summarize(report)

        self.assertIn(
            "liveTargetImageCanaryContract.groups.targetImageAnchors.ready cannot be true while missingKeys is non-empty",
            str(raised.exception),
        )

    def test_readiness_validator_rejects_malformed_anchor_coverage(self):
        cases = (
            (
                ("readyForTargetObjectDiscovery", "true"),
                "anchorCoverage.readyForTargetObjectDiscovery must be a boolean",
            ),
            (
                ("combinedAnchorCount", "5"),
                "anchorCoverage.combinedAnchorCount must be a non-negative integer",
            ),
        )
        for (key, value), message in cases:
            with self.subTest(key=key):
                report = readiness_report()
                report["anchorCoverage"][key] = value

                with self.assertRaises(ValueError) as raised:
                    module.summarize(report)

                self.assertIn(message, str(raised.exception))

    def test_package_next_action_loader_rejects_non_next_action_artifacts(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                    "selectedSeeds": [],
                },
                "package-next-action.json",
            )

        self.assertIn("expected 'dune-ue4ss-package-next-action/v1'", str(raised.exception))

    def test_package_next_action_loader_rejects_malformed_commands(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "arm-trace",
                    "commands": "scripts/ue4ss-package-runtime-trace.sh arm",
                },
                "package-next-action.json",
            )

        self.assertIn("commands must be a list", str(raised.exception))

    def test_package_next_action_loader_rejects_missing_action(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "commands": [],
                },
                "package-next-action.json",
            )

        self.assertIn("action must be a non-empty string", str(raised.exception))

    def test_package_next_action_loader_rejects_non_string_command_entries(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "arm-trace",
                    "commands": [{"argv": ["scripts/ue4ss-package-runtime-trace.sh", "arm"]}],
                },
                "package-next-action.json",
            )

        self.assertIn("commands[0] must be a string", str(raised.exception))

    def test_package_next_action_loader_rejects_non_scalar_trace_env(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "arm-trace",
                    "traceEnv": {"DUNE_UE4SS_PACKAGE_TRACE_LIMIT": ["2"]},
                    "commands": ["scripts/ue4ss-package-runtime-trace.sh arm"],
                },
                "package-next-action.json",
            )

        self.assertIn("traceEnv DUNE_UE4SS_PACKAGE_TRACE_LIMIT must be a scalar", str(raised.exception))

    def test_package_next_action_loader_rejects_malformed_guidance_strings(self):
        for key, value, message in (
            ("confidence", ["moderate"], "confidence must be a non-empty single-line string"),
            ("reason", {"text": "runtime trace"}, "reason must be a non-empty single-line string"),
            ("nextStep", ["capture a package frame"], "nextStep must be a non-empty single-line string"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ValueError) as raised:
                    module.validate_package_next_action(
                        {
                            "schemaVersion": "dune-ue4ss-package-next-action/v1",
                            "action": "arm-trace",
                            key: value,
                            "commands": ["scripts/ue4ss-package-runtime-trace.sh arm"],
                        },
                        "package-next-action.json",
                    )

                self.assertIn(message, str(raised.exception))

    def test_package_next_action_loader_rejects_multiline_operator_strings(self):
        cases = (
            (
                {"commands": ["scripts/ue4ss-package-runtime-trace.sh arm\nrm -rf /"]},
                "commands[0] must be a non-empty single-line string",
            ),
            (
                {"traceEnv": {"DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2\n3"}},
                "traceEnv DUNE_UE4SS_PACKAGE_TRACE_LIMIT must be a non-empty single-line scalar",
            ),
            (
                {"outputFiles": {"nextCanaryJson": "/tmp/next.json\nold"}},
                "outputFiles nextCanaryJson must be a non-empty single-line string",
            ),
            (
                {"promotionSummaryErrors": [{"path": "/tmp/promotion-env.json\nold", "error": "bad metadata"}]},
                "promotionSummaryErrors[0].path must be a single-line string",
            ),
            (
                {"promotionSummaryErrors": [{"path": "/tmp/promotion-env.json", "error": "bad metadata\nold"}]},
                "promotionSummaryErrors[0].error must be a non-empty single-line string",
            ),
            (
                {"blockers": ["valid blocker", ""]},
                "blockers[1] must be a non-empty single-line string",
            ),
        )
        for override, message in cases:
            with self.subTest(message=message):
                payload = {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "arm-trace",
                    "commands": ["scripts/ue4ss-package-runtime-trace.sh arm"],
                }
                payload.update(override)
                with self.assertRaises(ValueError) as raised:
                    module.validate_package_next_action(payload, "package-next-action.json")

                self.assertIn(message, str(raised.exception))

    def test_package_next_action_loader_rejects_malformed_ready_manifest_paths(self):
        for value, message in (
            ("/tmp/promotion-env.json", "readyManifestPaths must be a list"),
            ([""], "readyManifestPaths[0] must be a non-empty string"),
            ([{"path": "/tmp/promotion-env.json"}], "readyManifestPaths[0] must be a non-empty string"),
        ):
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as raised:
                    module.validate_package_next_action(
                        {
                            "schemaVersion": "dune-ue4ss-package-next-action/v1",
                            "action": "plan-canary",
                            "readyManifestPaths": value,
                            "commands": ["scripts/plan-ue4ss-canary-env.py --format json"],
                        },
                        "package-next-action.json",
                    )

                self.assertIn(message, str(raised.exception))

    def test_package_next_action_loader_rejects_malformed_pending_review(self):
        cases = (
            (["not-object"], "pending must be an object"),
            ({"missingReviewFlags": "--reviewed-abi"}, "pending missingReviewFlags must be a list"),
            ({"missingNativeInvokeFlags": ["--final-native-call", 42]}, "pending missingNativeInvokeFlags[1] must be a string"),
            ({"blockers": [{"message": "manual review"}]}, "pending blockers[0] must be a string"),
            ({"abiReviewBlockers": {"message": "abi mismatch"}}, "pending abiReviewBlockers must be a list"),
        )
        for value, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as raised:
                    module.validate_package_next_action(
                        {
                            "schemaVersion": "dune-ue4ss-package-next-action/v1",
                            "action": "complete-review",
                            "pending": value,
                            "commands": ["scripts/ue4ss-package-runtime-trace.sh status"],
                        },
                        "package-next-action.json",
                    )

                self.assertIn(message, str(raised.exception))

    def test_package_next_action_loader_rejects_malformed_trace_plan_blockers(self):
        for value, message in (
            ("no package runtime trace seeds selected", "tracePlanBlockers must be a list"),
            (["no package runtime trace seeds selected", {"code": "missing-seeds"}], "tracePlanBlockers[1] must be a string"),
        ):
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as raised:
                    module.validate_package_next_action(
                        {
                            "schemaVersion": "dune-ue4ss-package-next-action/v1",
                            "action": "refresh-trace-plan",
                            "tracePlanBlockers": value,
                            "commands": ["scripts/plan-ue4ss-package-runtime-trace.py --format json"],
                        },
                        "package-next-action.json",
                    )

                self.assertIn(message, str(raised.exception))

    def test_package_next_action_loader_rejects_malformed_promotion_errors(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "complete-review",
                    "promotionSummaryErrors": [{"path": "/tmp/promotion-env.json", "error": ""}],
                    "commands": ["scripts/ue4ss-package-runtime-trace.sh status"],
                },
                "package-next-action.json",
            )

        self.assertIn("promotionSummaryErrors[0].error must be a non-empty string", str(raised.exception))

    def test_package_next_action_loader_rejects_ready_paths_with_promotion_errors(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "plan-canary",
                    "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                    "promotionSummaryErrors": [
                        {
                            "path": "/tmp/families/LoadPackage/promotion-env.json",
                            "error": "abiReview.arguments[0].memory.lineCount must be a non-negative integer",
                        }
                    ],
                    "commands": ["scripts/plan-ue4ss-canary-env.py --format json"],
                },
                "package-next-action.json",
            )

        self.assertIn(
            "cannot contain readyManifestPaths while promotionSummaryErrors are present",
            str(raised.exception),
        )

    def test_package_next_action_loader_rejects_malformed_output_files(self):
        with self.assertRaises(ValueError) as raised:
            module.validate_package_next_action(
                {
                    "schemaVersion": "dune-ue4ss-package-next-action/v1",
                    "action": "plan-canary",
                    "outputFiles": {"nextCanaryJson": ["/tmp/next.json"]},
                    "commands": ["scripts/plan-ue4ss-canary-env.py --format json"],
                },
                "package-next-action.json",
            )

        self.assertIn("outputFiles nextCanaryJson must be a string", str(raised.exception))

    def test_package_next_action_loader_accepts_trace_env_object(self):
        action = module.validate_package_next_action(
            {
                "schemaVersion": "dune-ue4ss-package-next-action/v1",
                "action": "arm-trace",
                "traceEnv": {"DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2"},
                "commands": ["scripts/ue4ss-package-runtime-trace.sh arm"],
            },
            "package-next-action.json",
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"], "2")


if __name__ == "__main__":
    unittest.main()
