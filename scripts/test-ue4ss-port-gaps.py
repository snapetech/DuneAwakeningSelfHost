#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-port-gaps.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_port_gaps", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


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

    def test_gap_summary_counts_runtime_candidate_carry_forward(self):
        summary = module.summarize(readiness_report(), [runtime_carry_forward_plan()])

        coverage = summary["rootRecoveryCandidateCoverage"]
        self.assertTrue(coverage["provided"])
        self.assertIn("names", coverage["readyGroups"])
        self.assertIn("objects", coverage["missingGroups"])
        self.assertEqual(coverage["anchorCounts"], {"RuntimeFNamePool": 1})
        self.assertEqual(coverage["plans"][0]["runtimeCarryForwardEntryCount"], 1)
        self.assertEqual(coverage["plans"][0]["runtimeCarryForwardEntries"], ["RuntimeFNamePool=0x60000"])
        rendered = module.markdown(summary)
        self.assertIn("runtimeCarry=`1`", rendered)
        self.assertIn("RuntimeFNamePool=0x60000", rendered)


if __name__ == "__main__":
    unittest.main()
