#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "plan-ue4ss-canary-env.py",
    ROOT / "analysis" / "plan-ue4ss-canary-env.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


ANCHOR_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-start strings=0 signatures=4 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=FNamePool group=names status=resolved hit=0x140001000 addr=0x140010000 transform=riprel32+3 rva=0x10000 allocationBase=0x140000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GUObjectArray group=objects status=resolved hit=0x140002000 addr=0x140020000 transform=riprel32+3 rva=0x20000 allocationBase=0x140000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GWorld group=world status=resolved hit=0x140003000 addr=0x140030000 transform=riprel32+3 rva=0x30000 allocationBase=0x140000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=ProcessEvent group=dispatch status=resolved hit=0x140004000 addr=0x140040000 transform=callrel32 rva=0x40000 allocationBase=0x140000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-finish
"""

MAPPED_ONLY_SERVER_ANCHOR_LOG = """\
2026-06-16T17:43:39Z pid=100 loader=server event=loaded phase=snapshot exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-16T17:43:39Z pid=100 loader=server event=ue-anchor name=GName group=names status=mapped addr=0x557dcfcedb58 imageOffset=0x120ab58 fileOffset=0x120ab58 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:43:39Z pid=100 loader=server event=ue-anchor name=GUObjectArray group=objects status=mapped addr=0x557dd4483d55 imageOffset=0x59a0d55 fileOffset=0x59a0d55 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
"""


def ue_anchor_groups(
    names=1,
    objects=1,
    world=1,
    dispatch=1,
    package=1,
    reflection=2,
    target_names=None,
    target_objects=None,
    target_world=None,
    target_dispatch=None,
    target_package=None,
    target_reflection=None,
):
    totals = {
        "names": 2,
        "objects": 2,
        "world": 1,
        "dispatch": 2,
        "package": 4,
        "reflection": 4,
    }
    present = {
        "names": names,
        "objects": objects,
        "world": world,
        "dispatch": dispatch,
        "package": package,
        "reflection": reflection,
    }
    target_present = {
        "names": names if target_names is None else target_names,
        "objects": objects if target_objects is None else target_objects,
        "world": world if target_world is None else target_world,
        "dispatch": dispatch if target_dispatch is None else target_dispatch,
        "package": package if target_package is None else target_package,
        "reflection": reflection if target_reflection is None else target_reflection,
    }
    return {
        group: {
            "present": present[group],
            "targetPresent": target_present[group],
            "total": totals[group],
            "complete": present[group] == totals[group],
            "targetComplete": target_present[group] == totals[group],
            "anchors": [],
        }
        for group in totals
    }


def report(ready_overrides=None, passed_gates=None, canary_hints=None, ue_groups=None):
    ready = {
        "objectDiscovery": False,
        "targetImageProcess": True,
        "runtimeRootDiscovery": True,
        "runtimeRootValidation": True,
        "targetObjectDiscovery": True,
        "reflection": False,
        "hooks": False,
        "targetHooks": True,
        "luaDispatch": False,
        "anchorSignatureResolver": True,
        "anchorGroupProvenance": True,
        "ueProcessEventHookRuntimeTarget": True,
        "ueCallFunctionHookRuntimeTarget": True,
        "ueCallFunctionLiveHook": True,
        "ueCallFunctionLiveHookRuntimeTarget": True,
        "ueCallFunctionLiveLuaDispatch": True,
        "ueCallFunctionActiveValidation": True,
        "luaCallFunctionNativeInvoke": True,
        "luaCallFunctionNativeInvokePreflight": True,
        "luaCallFunctionNativeExecutorState": True,
        "luaCallFunctionNativeInvokeNonSelfTestGate": True,
        "luaCallFunctionNativeInvokeNonSelfTestInvoked": True,
        "ueProcessEventLiveHookRuntimeTarget": True,
        "ueProcessEventActiveValidation": True,
        "luaProcessEventNativeInvoke": True,
        "luaProcessEventNativeInvokeDescriptorPreflight": True,
        "luaProcessEventNativeExecutorState": True,
        "luaProcessEventNativeInvokeNonSelfTestGate": True,
        "luaProcessEventNativeInvokeNonSelfTestInvoked": True,
        "ueProcessEventLiveLuaDispatch": True,
        "ueProcessEventLiveFunctionPath": True,
        "ueProcessEventLiveRuntimeContext": True,
        "ueProcessEventLiveRegistryContext": True,
        "ueProcessEventLiveRuntimeRegistryContext": True,
        "ueProcessEventLiveParamValues": True,
        "ueProcessEventLiveRawParamValues": True,
        "ueProcessEventLiveContainerParamValues": True,
        "ueProcessEventLiveArrayContainerParamValues": True,
        "ueProcessEventLiveSetContainerParamValues": True,
        "ueProcessEventLiveMapContainerParamValues": True,
        "ueProcessEventLiveSetMapContainerParamValues": True,
        "ueProcessEventLiveContainerDataSamples": True,
        "ueProcessEventLuaContextHandles": True,
        "ueProcessEventLuaParamAccessors": True,
        "ueProcessEventLiveClassAwareParamValues": True,
        "ueProcessEventFunctionParamMethod": True,
        "ueProcessEventFunctionParamLookupMethod": True,
        "ueProcessEventFunctionParamIterationMethod": True,
        "ueProcessEventContainerAliasMethods": True,
        "ueProcessEventLuaHookRouting": True,
        "ueProcessEventLuaHookAliasRouting": True,
        "ueProcessEventContainerStorageLayoutMethods": True,
        "ueProcessEventLuaScalarParamAccessors": True,
        "ueProcessEventLuaNameStringParamAccessors": True,
        "ueProcessEventLuaStructParamAccessors": True,
        "ueProcessEventLuaEnumParamAccessors": True,
        "ueProcessEventLuaObjectParamAccessors": True,
        "ueProcessEventLuaBoolParamAccessors": True,
        "objectDiscoveryCoverage": True,
        "findObjectSemantics": True,
        "luaObjectRegistryRuntime": True,
        "luaFunctionRegistryRuntime": True,
        "luaDecodedObjectAliasesRuntime": True,
        "ueObjectArrayShape": True,
        "ueObjectArrayRegistryRuntime": True,
        "ueObjectNativeIdentities": True,
        "ueObjectInternalFlags": True,
        "ueFNameDecoder": True,
        "luaObjectOuterChainIdentities": True,
        "luaObjectApi": True,
        "luaFunctionIterationRuntime": True,
        "luaStaticConstructObjectNativeExecutorState": True,
        "luaStaticConstructObjectNativeExecutorReady": True,
        "luaStaticConstructObjectNativeInvoke": True,
        "ueReflectionPropertyDescriptorsRuntime": True,
        "ueReflectionPropertyValuesRuntime": True,
        "ueFunctionParamDescriptors": True,
        "ueFunctionParamContainerChildren": True,
        "ueFunctionIdentities": True,
        "ueFunctionNativeIdentities": True,
        "ueFunctionFlags": True,
        "luaReflectionForEachPropertyRuntime": True,
        "luaReflectionLiveDescriptorTypedClassRuntime": True,
        "luaReflectionLiveDescriptorTypedValuesRuntime": True,
        "luaReflectionLiveDescriptorTypedSetValuesRuntime": True,
        "luaReflectionLiveDescriptorValuesRuntime": True,
        "luaLoadAssetPackageCrashGuard": True,
        "luaLoadAssetPackageGuardedCall": True,
        "luaLoadAssetPackageReturnValidation": True,
        "luaLoadAssetPackageNativeCallAdapter": True,
        "luaLoadAssetPackageInvocationDescriptor": True,
        "luaLoadAssetPackageNativeExecutor": True,
        "luaLoadAssetPackageNativeInvocation": True,
        "luaLoadAssetPackage": True,
        "luaLoadClassPackageAbiState": True,
        "luaLoadClassPackageCallFrameVerification": True,
        "luaLoadClassPackageNativeExecutor": True,
        "luaLoadClassPackageNativeInvocation": True,
        "signatureManifestExact": True,
        "signatureManifestPromotable": True,
        "anchorCoverageObjectDiscovery": True,
        "anchorCoverageHookPlanning": True,
        "anchorCoveragePackageLoading": True,
        "targetPackageLoadingSurface": True,
        "targetNames": True,
        "targetObjects": True,
        "targetWorld": True,
        "targetDispatch": True,
        "targetReflectionSurface": True,
    }
    ready.update(ready_overrides or {})
    gates = [{"name": name, "passed": True, "evidence": "", "blocker": ""} for name in (passed_gates or [])]
    return {
        "schemaVersion": "dune-ue4ss-port-readiness/v1",
        "ready": ready,
        "gates": gates,
        "canaryHints": canary_hints or {},
        "anchorGroups": {
            "anchors": {},
            "mappedAnchors": {},
            "signatures": {"names": 1, "objects": 1, "world": 1, "dispatch": 1, "package": 1, "reflection": 2},
            "resolvedSignatures": {"names": 1, "objects": 1, "world": 1, "dispatch": 1, "package": 1, "reflection": 2},
        },
        "ue": {"provenOnly": True, "groups": ue_groups if ue_groups is not None else ue_anchor_groups()},
    }


def with_anchor_coverage(
    base,
    object_ready=True,
    hook_ready=True,
    package_ready=True,
    missing=None,
    target_object_ready=None,
    target_hook_ready=None,
    target_package_ready=None,
):
    base = dict(base)
    ready = dict(base.get("ready", {}))
    ready["anchorCoverageObjectDiscovery"] = object_ready
    ready["anchorCoverageHookPlanning"] = hook_ready
    ready["anchorCoveragePackageLoading"] = package_ready
    base["ready"] = ready
    target_fields_present = (
        target_object_ready is not None
        or target_hook_ready is not None
        or target_package_ready is not None
    )
    target_object_ready = object_ready if target_object_ready is None else target_object_ready
    target_hook_ready = hook_ready if target_hook_ready is None else target_hook_ready
    target_package_ready = package_ready if target_package_ready is None else target_package_ready
    base["anchorCoverage"] = {
        "provided": True,
        "explicitAnchorCount": 3,
        "signatureAnchorCount": 1,
        "combinedAnchorCount": 4,
        "readyForObjectDiscovery": object_ready,
        "readyForHookPlanning": hook_ready,
        "readyForPackageLoading": package_ready,
        "targetCoverageFieldsPresent": target_fields_present,
        "readyForTargetObjectDiscovery": target_object_ready,
        "readyForTargetHookPlanning": target_hook_ready,
        "readyForTargetPackageLoading": target_package_ready,
        "missingRequiredGroups": missing or [],
        "groups": {},
    }
    base["gates"] = list(base.get("gates", [])) + [
        {
            "name": "anchor-coverage-object-discovery",
            "passed": object_ready,
            "evidence": "",
            "blocker": "" if object_ready else "prepared canary anchor coverage is missing a required object-discovery anchor group",
        },
        {
            "name": "anchor-coverage-hook-planning",
            "passed": hook_ready,
            "evidence": "",
            "blocker": "" if hook_ready else "prepared canary anchor coverage does not include ProcessEvent-level dispatch evidence for hook planning",
        },
    ]
    return base


def with_object_discovery_coverage(base, object_ready=False, find_object_ready=False, missing=None):
    base = dict(base)
    ready = dict(base.get("ready", {}))
    ready["objectDiscoveryCoverage"] = object_ready
    ready["findObjectSemantics"] = find_object_ready
    base["ready"] = ready
    base["objectDiscoveryCoverage"] = {
        "schemaVersion": "dune-ue-object-discovery-coverage/v1",
        "components": {},
        "missingObjectDiscoveryComponents": missing or [],
        "missingFindObjectComponents": missing or [],
        "readyForObjectDiscovery": object_ready,
        "readyForFindObjectSemantics": find_object_ready,
    }
    return base


def write_root_recovery_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-root-recovery-candidate-export/v1",
        "platform": "windows",
        "anchorPreset": "object-discovery",
        "envName": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
        "candidateCount": 3,
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x166eba80",
                "hypothesis": "root-recovery-writable-global",
                "cluster": {"index": 2},
                "score": 656,
                "sourceName": ".init_array[2793]",
            },
            {
                "name": "GUObjectArray",
                "imageOffset": "0x166ebac0",
                "hypothesis": "root-recovery-writable-global",
                "cluster": {"index": 2},
                "score": 656,
                "sourceName": ".init_array[2793]",
            },
            {
                "name": "FNamePool",
                "imageOffset": "0x1686df70",
                "hypothesis": "root-recovery-writable-global",
                "cluster": {"index": 3},
                "score": 400,
                "sourceName": ".init_array[100]",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_writable_candidate_globals(path):
    payload = {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "candidateCount": 2,
        "anchorCounts": {"FNamePool": 1, "GUObjectArray": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x165ff4a8",
                "group": "objects",
                "score": 1756,
                "sourceTarget": "0x165ff4a8",
            },
            {
                "name": "FNamePool",
                "imageOffset": "0x1686df70",
                "group": "names",
                "score": 8503,
                "sourceTarget": "0x1686df70",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_scalar_heavy_writable_root_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-writable-root-shape-candidates/v1",
        "platform": "windows",
        "envName": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
        "candidateCount": 3,
        "anchorCounts": {"GUObjectArray": 1, "GObjectArray": 1, "GWorld": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x16501c38",
                "hypothesis": "writable-root-readwrite-shape",
                "score": 3850,
                "refCount": 448,
                "functionBucketCount": 280,
                "qwordRefCount": 0,
                "scalarRefCount": 448,
                "scalarRatio": 1.0,
            },
            {
                "name": "GObjectArray",
                "imageOffset": "0x16501c38",
                "hypothesis": "writable-root-readwrite-shape",
                "score": 3850,
                "refCount": 448,
                "functionBucketCount": 280,
                "qwordRefCount": 0,
                "scalarRefCount": 448,
                "scalarRatio": 1.0,
            },
            {
                "name": "GWorld",
                "imageOffset": "0x16501c38",
                "hypothesis": "writable-root-readwrite-shape",
                "score": 3850,
                "refCount": 448,
                "functionBucketCount": 280,
                "qwordRefCount": 0,
                "scalarRefCount": 448,
                "scalarRatio": 1.0,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_address_only_writable_global_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "candidateCount": 1,
        "anchorCounts": {"GUObjectArray": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x165ff4a8",
                "group": "objects",
                "score": 1756,
                "sourceTarget": "0x165ff4a8",
                "rootShape": {
                    "present": True,
                    "qwordRefCount": 406,
                    "scalarRefCount": 9,
                    "scalarRatio": 0.021687,
                    "addressRatio": 0.978313,
                    "kindCounts": {"address": 406, "byte-guard": 9},
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_read_write_writable_global_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "candidateCount": 1,
        "anchorCounts": {"GUObjectArray": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x16501c18",
                "group": "objects",
                "score": 19216,
                "sourceTarget": "0x16501c18",
                "rootShape": {
                    "present": True,
                    "qwordRefCount": 1420,
                    "scalarRefCount": 0,
                    "scalarRatio": 0.0,
                    "addressRatio": 0.0,
                    "kindCounts": {"read": 704, "write": 710, "other": 6},
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_address_heavy_read_write_writable_global_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "candidateCount": 1,
        "anchorCounts": {"GUObjectArray": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x16702ee8",
                "group": "objects",
                "score": 11091,
                "sourceTarget": "0x16702ee8",
                "rootShape": {
                    "present": True,
                    "qwordRefCount": 2681,
                    "scalarRefCount": 0,
                    "scalarRatio": 0.0,
                    "addressRatio": 0.987,
                    "kindCounts": {"address": 2649, "compare": 2, "read": 29, "write": 2},
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_generic_only_hint_writable_global_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "candidateCount": 1,
        "anchorCounts": {"GUObjectArray": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x16535950",
                "group": "objects",
                "score": 168,
                "sourceTarget": "0x16535950",
                "qwordRefCount": 32,
                "scalarRefCount": 0,
                "scalarRatio": 0.0,
                "addressRatio": 0.0,
                "kindCounts": {"read": 15, "write": 16, "other": 1},
                "hintQuality": {
                    "contextCount": 3,
                    "exactContextCount": 0,
                    "specificContextCount": 0,
                    "genericContextCount": 3,
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_unmatched_source_group_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-root-recovery-candidate-export/v1",
        "platform": "windows",
        "anchorPreset": "complete",
        "envName": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
        "candidateCount": 2,
        "anchorCounts": {"GUObjectArray": 1, "ProcessEvent": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x2000",
                "hypothesis": "root-recovery-writable-global",
                "sourceGroupCoverage": ["objects"],
                "anchorGroup": "objects",
                "anchorGroupMatched": True,
                "qwordRefCount": 8,
                "scalarRefCount": 0,
                "scalarRatio": 0.0,
            },
            {
                "name": "ProcessEvent",
                "imageOffset": "0x2000",
                "hypothesis": "root-recovery-writable-global",
                "sourceGroupCoverage": ["objects"],
                "anchorGroup": "dispatch",
                "anchorGroupMatched": False,
                "qwordRefCount": 8,
                "scalarRefCount": 0,
                "scalarRatio": 0.0,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_pointer_like_root_recovery_candidates(path):
    payload = {
        "schemaVersion": "dune-ue-root-recovery-candidate-export/v1",
        "platform": "server",
        "envName": "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS",
        "candidateCount": 1,
        "anchorCounts": {"GEngine": 1},
        "candidates": [
            {
                "name": "GEngine",
                "imageOffset": "0x16449320",
                "hypothesis": "root-recovery-writable-global",
                "cluster": {"index": 1},
                "score": 55,
                "section": ".bss",
                "refCount": 2,
                "pointerLikeRefCount": 2,
                "byteGuardRefCount": 0,
                "constantStoreRefCount": 0,
                "anchorGroup": "world",
                "anchorGroupMatched": False,
                "sourceGroupCoverage": [],
                "sourceName": "GEngine@0x59dffb3#1",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_candidate_shapes(path):
    payload = {
        "schemaVersion": "dune-ue-candidate-shapes/v1",
        "candidateCount": 1,
        "verdictCounts": {"weak-code-pointer": 1},
        "candidates": [
            {
                "name": "FNamePool",
                "imageOffset": "0x1686df70",
                "verdict": "weak-code-pointer",
                "reason": "candidate points into executable code/table context",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_candidate_outcomes(path, runtime_rw=False):
    payload = {
        "schemaVersion": "dune-ue-candidate-outcomes/v1",
        "candidateCount": 1,
        "verdictCounts": {"weak-false-positive": 1},
        "candidates": [
            {
                "name": "GUObjectArray",
                "imageOffset": "0x166eba80",
                "runtimeRwFileOffset": "true" if runtime_rw else "",
                "verdict": "weak-false-positive",
                "recommendation": "reject-runtime-auto-discovery-candidate",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class PlanUe4ssCanaryEnvTests(unittest.TestCase):
    def run_plan(self, tmp, readiness, *extra, platform="windows"):
        readiness_path = Path(tmp) / "readiness.json"
        readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
        result = subprocess.run(
            [
                str(SCRIPT),
                "--platform",
                platform,
                "--readiness-json",
                str(readiness_path),
                "--format",
                "json",
                *extra,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return json.loads(result.stdout)

    def test_read_only_plan_enables_object_discovery_without_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, report())

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS"], "core,ue")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_SCAN_PATH_FILTER"], "DuneSandbox-Win64-Shipping.exe;DuneSandbox")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE"], "16")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW", env)
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)

    def test_read_only_plan_reports_selected_stage_blockers_separately(self):
        readiness = report(
            {
                "objectDiscovery": False,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": True,
                "luaLoadClassPackageCallFrameVerification": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        all_codes = {item["code"] for item in plan["blockers"]}
        selected_codes = {item["code"] for item in plan["selectedStageBlockers"]}
        selected_stages = {item["stage"] for item in plan["selectedStageBlockers"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertIn("missing-load-class-package-call-frame-verification", all_codes)
        self.assertNotIn("missing-load-class-package-call-frame-verification", selected_codes)
        self.assertTrue(selected_stages <= {"object-discovery"})

    def test_explicit_linux_hook_targets_emit_image_offset_envs(self):
        readiness = report({"objectDiscovery": True, "reflection": True})
        with tempfile.TemporaryDirectory() as tmp:
            linux = self.run_plan(
                tmp,
                readiness,
                "--process-event-image-offset",
                "0xfa92d50",
                "--call-function-image-offset",
                "0xfa93000",
                "--max-stage",
                "hook-probe",
                platform="linux-client",
            )
            server = self.run_plan(
                tmp,
                readiness,
                "--process-event-image-offset",
                "0xfa92d50",
                "--call-function-image-offset",
                "0xfa93000",
                "--max-stage",
                "hook-probe",
                platform="server",
            )

        linux_env = {item["name"]: item["value"] for item in linux["env"]}
        server_env = {item["name"]: item["value"] for item in server["env"]}
        for prefix, env in (
            ("DUNE_CLIENT_PROBE", linux_env),
            ("DUNE_PROBE_LOADER", server_env),
        ):
            self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET"], "0xfa92d50")
            self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_IMAGE_OFFSET"], "0xfa92d50")
            self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET"], "0xfa92d50")
            self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET"], "0xfa93000")
            self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_IMAGE_OFFSET"], "0xfa93000")
            self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET"], "0xfa93000")

    def test_explicit_windows_hook_targets_emit_rva_envs(self):
        readiness = report({"objectDiscovery": True, "reflection": True})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--process-event-rva",
                "0x40000",
                "--call-function-rva",
                "0x41000",
                "--max-stage",
                "hook-probe",
                platform="windows",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_RVA"], "0x40000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_RVA"], "0x40000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_RVA"], "0x40000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_RVA"], "0x41000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_RVA"], "0x41000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_RVA"], "0x41000")

    def test_hook_targets_json_accepts_vtable_ranker_shortlist(self):
        readiness = report({"objectDiscovery": True, "reflection": True})
        payload = {
            "schemaVersion": "dune-ue-vtable-candidates/v1",
            "hookProbeShortlist": [
                {
                    "slot": 67,
                    "topTarget": {
                        "targetName": "ProcessEvent",
                        "imageOffset": "0xfa92d50",
                        "rva": "0x50000",
                    },
                }
            ],
            "targets": [
                {
                    "targetName": "CallFunctionByNameWithArguments",
                    "imageOffset": "0xfa93000",
                    "rva": "0x51000",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            targets_path = Path(tmp) / "hook-targets.json"
            targets_path.write_text(json.dumps(payload), encoding="utf-8")
            linux = self.run_plan(
                tmp,
                readiness,
                "--hook-targets-json",
                str(targets_path),
                platform="linux-client",
            )
            windows = self.run_plan(
                tmp,
                readiness,
                "--hook-targets-json",
                str(targets_path),
                platform="windows",
            )

        linux_env = {item["name"]: item["value"] for item in linux["env"]}
        windows_env = {item["name"]: item["value"] for item in windows["env"]}
        self.assertEqual(linux_env["DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET"], "0xfa92d50")
        self.assertEqual(linux_env["DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET"], "0xfa93000")
        self.assertEqual(windows_env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_RVA"], "0x50000")
        self.assertEqual(windows_env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_RVA"], "0x51000")

    def test_process_event_vtable_target_allows_process_event_only_hook_probe(self):
        readiness = report(
            {
                "objectDiscovery": False,
                "targetObjectDiscovery": False,
                "targetWorld": False,
                "targetDispatch": False,
                "reflection": True,
                "ueProcessEventHookProbe": False,
                "ueProcessEventHookRuntimeTarget": False,
                "ueCallFunctionHookRuntimeTarget": False,
            },
            ue_groups=ue_anchor_groups(target_world=0, target_dispatch=0),
        )
        payload = {
            "schemaVersion": "dune-ue-vtable-candidates/v1",
            "hookProbeShortlist": [
                {
                    "slot": 64,
                    "candidateCount": 512,
                    "objectCoverage": 1.0,
                    "topTargetShare": 1.0,
                    "topTarget": {
                        "targetName": "ProcessEvent",
                        "imageOffset": "0xfb4b060",
                        "map": "/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
                        "perms": "r-xp",
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            targets_path = Path(tmp) / "ue-vtable-candidates.json"
            targets_path.write_text(json.dumps(payload), encoding="utf-8")
            plan = self.run_plan(
                tmp,
                readiness,
                "--hook-targets-json",
                str(targets_path),
                "--max-stage",
                "hook-probe",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "hook-probe")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET"], "0xfb4b060")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE", env)
        self.assertNotIn("DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_INSTALL", env)
        self.assertIn("CallFunctionByNameWithArguments hook probe target is not explicit", " ".join(plan["notes"]))

    def test_process_event_runtime_target_allows_process_event_only_live_hook(self):
        readiness = report(
            {
                "objectDiscovery": False,
                "targetObjectDiscovery": False,
                "targetWorld": False,
                "targetDispatch": False,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventHookRuntimeTarget": True,
                "ueProcessEventLiveHook": False,
                "ueProcessEventLiveHookRuntimeTarget": False,
                "ueCallFunctionHookProbe": False,
                "ueCallFunctionHookRuntimeTarget": False,
                "ueCallFunctionLiveHook": False,
                "ueCallFunctionLiveHookRuntimeTarget": False,
                "ueProcessEventActiveValidation": False,
            },
            ue_groups=ue_anchor_groups(dispatch=0, target_world=0, target_dispatch=0),
        )
        payload = {
            "schemaVersion": "dune-ue-vtable-candidates/v1",
            "hookProbeShortlist": [
                {
                    "slot": 64,
                    "topTarget": {
                        "targetName": "ProcessEvent",
                        "imageOffset": "0xfb4b060",
                        "map": "/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
                        "perms": "r-xp",
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            targets_path = Path(tmp) / "ue-vtable-candidates.json"
            targets_path.write_text(json.dumps(payload), encoding="utf-8")
            plan = self.run_plan(
                tmp,
                readiness,
                "--hook-targets-json",
                str(targets_path),
                "--max-stage",
                "live-hook",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT"], "8")
        self.assertNotIn("DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK", env)
        self.assertNotIn("DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS", env)
        self.assertNotIn("DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE", env)
        self.assertNotIn("unproven-dispatch-anchor", {item["code"] for item in plan["blockers"]})
        self.assertNotIn("unproven-target-dispatch-anchor", {item["code"] for item in plan["blockers"]})
        self.assertIn("CallFunctionByNameWithArguments live hook target is not explicit", " ".join(plan["notes"]))

    def test_server_read_only_plan_filters_to_dune_target_process_and_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, report(), platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertEqual(env["DUNE_PROBE_LOADER_TARGET"], "DuneSandboxServer;DuneSandbox")
        self.assertEqual(env["DUNE_PROBE_LOADER_SCAN_ENABLED"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_SCAN_PRESETS"], "core,ue")
        self.assertEqual(env["DUNE_PROBE_LOADER_SCAN_PATH_FILTER"], "DuneSandboxServer;DuneSandbox")
        self.assertEqual(env["DUNE_PROBE_LOADER_SCAN_MAX_HITS_PER_NEEDLE"], "16")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW"], "true")
        self.assertIn(
            "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW",
            plan["nextCanaryContract"]["envNames"],
        )

    def test_server_read_only_plan_uses_explicit_target_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                report(),
                "--exe-substring",
                "ExampleServer",
                "--exe-substring",
                "ExampleServer",
                "--exe-substring",
                "ExampleGame",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_TARGET"], "ExampleServer;ExampleGame")
        self.assertEqual(env["DUNE_PROBE_LOADER_SCAN_PATH_FILTER"], "ExampleServer;ExampleGame")

    def test_linux_client_read_only_plan_uses_explicit_target_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                report(),
                "--exe-substring",
                "ExampleGame-Linux-Shipping",
                platform="linux-client",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_CLIENT_PROBE_SCAN_PATH_FILTER"], "ExampleGame-Linux-Shipping")

    def test_windows_read_only_plan_uses_explicit_target_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                report(),
                "--exe-substring",
                "ExampleGame-Win64-Shipping.exe",
                platform="windows",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_SCAN_PATH_FILTER"], "ExampleGame-Win64-Shipping.exe")

    def test_runtime_discovery_no_target_writable_image_widens_windows_region_scan(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"no-target-writable-image": 1},
            "coverage": {
                "targetWritableImageCount": 0,
                "scannedSlots": 0,
                "fnameProbes": 0,
                "objectArrayProbes": 0,
                "fnameHits": 0,
                "objectArrayHits": 0,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="windows")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REGION_BYTES"], "1073741824")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "8")
        self.assertIn("scanned no target writable image", " ".join(plan["notes"]))

    def test_runtime_discovery_no_root_hits_broadens_linux_mapping_scan(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"no-root-hits": 1},
            "coverage": {
                "targetWritableImageCount": 2,
                "scannedSlots": 4096,
                "fnameProbes": 4096,
                "objectArrayProbes": 4096,
                "fnameHits": 0,
                "objectArrayHits": 0,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="linux-client")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW"], "true")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES"], "536870912")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "32")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS"], "90")
        self.assertIn("did not find both root shapes", " ".join(plan["notes"]))
        self.assertIn("delayed UE-only probe", " ".join(plan["notes"]))

    def test_runtime_discovery_missing_fname_root_gets_specific_read_only_note(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"no-root-hits": 1},
            "candidateNameCounts": {"RuntimeGUObjectArray": 2},
            "coverage": {
                "targetWritableImageCount": 2,
                "scannedSlots": 4096,
                "fnameProbes": 4096,
                "objectArrayProbes": 4096,
                "fnameHits": 0,
                "objectArrayHits": 2,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="linux-client")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES"], "536870912")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "32")
        self.assertEqual(env["DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS"], "90")
        self.assertIn("no RuntimeFNamePool candidate", " ".join(plan["notes"]))

    def test_runtime_discovery_ambiguous_roots_tightens_server_candidate_count(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"ambiguous-root-hits": 1},
            "coverage": {
                "targetWritableImageCount": 3,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 3,
                "objectArrayHits": 2,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES", env)
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "3")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS"], "128")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_DELAYED_PROBE_SECONDS"], "90")
        self.assertIn("ambiguous root hits", " ".join(plan["notes"]))
        self.assertIn("same delayed canary", " ".join(plan["notes"]))

    def test_runtime_discovery_ambiguous_windows_object_array_tightens_min_elements(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"ambiguous-root-hits": 1},
            "candidateNameCounts": {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 2},
            "coverage": {
                "targetWritableImageCount": 2,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 1,
                "objectArrayHits": 2,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="windows")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "2")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS"], "128")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS"], "90")

    def test_runtime_discovery_ambiguous_fname_root_names_specific_family(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"ambiguous-root-hits": 1},
            "candidateNameCounts": {"RuntimeFNamePool": 3, "RuntimeGUObjectArray": 1},
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x140060000",
                    "imageOffset": "0x60000",
                    "map": "C:\\game\\DuneSandbox-Win64-Shipping.exe",
                },
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x140061000",
                    "imageOffset": "0x61000",
                    "map": "C:\\game\\DuneSandbox-Win64-Shipping.exe",
                },
            ],
            "coverage": {
                "targetWritableImageCount": 2,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 3,
                "objectArrayHits": 1,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="windows")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "3")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS"], "true")
        self.assertIn("RuntimeFNamePool", " ".join(plan["notes"]))
        self.assertNotIn("RuntimeGUObjectArray)", " ".join(plan["notes"]))
        self.assertIn("0x60000", " ".join(plan["notes"]))
        self.assertIn("DuneSandbox-Win64-Shipping.exe", " ".join(plan["notes"]))

    def test_unique_runtime_root_candidate_location_is_carried_forward(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"incomplete-promotion": 1},
            "candidateNameCounts": {"RuntimeFNamePool": 1},
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x140060000",
                    "imageOffset": "0x60000",
                    "targetImage": "true",
                    "map": "C:\\game\\DuneSandbox-Win64-Shipping.exe",
                }
            ],
            "coverage": {
                "targetWritableImageCount": 2,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 1,
                "objectArrayHits": 0,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="windows")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"], "RuntimeFNamePool=0x60000")
        self.assertIn("Carrying forward unique runtime root candidates", " ".join(plan["notes"]))
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertTrue(carry["provided"])
        self.assertEqual(carry["envName"], "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS")
        self.assertEqual(carry["entries"], ["RuntimeFNamePool=0x60000"])
        self.assertEqual(carry["anchorCounts"], {"RuntimeFNamePool": 1})
        self.assertTrue(carry["groupCoverage"]["names"]["ready"])
        self.assertFalse(carry["groupCoverage"]["objects"]["ready"])
        self.assertIn("objects", carry["missingGroups"])

    def test_unique_linux_runtime_rw_candidate_location_uses_rwfile_mode(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"incomplete-promotion": 1},
            "candidateNameCounts": {"RuntimeGUObjectArray": 1},
            "candidateLocations": [
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x7f000028c4c0",
                    "fileOffset": "0x28c4c0",
                    "targetImage": "false",
                    "map": "",
                }
            ],
            "coverage": {
                "targetWritableImageCount": 1,
                "anonymousWritableMappingCount": 1,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 0,
                "objectArrayHits": 1,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"], "RuntimeGUObjectArray@rwfile=0x28c4c0")
        self.assertIn("RuntimeGUObjectArray@rwfile=0x28c4c0", " ".join(plan["notes"]))
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertTrue(carry["provided"])
        self.assertEqual(carry["entries"], ["RuntimeGUObjectArray@rwfile=0x28c4c0"])
        self.assertEqual(carry["anchorCounts"], {"RuntimeGUObjectArray": 1})
        self.assertTrue(carry["groupCoverage"]["objects"]["ready"])

    def test_runtime_candidate_carry_forward_can_be_suppressed_after_static_rejection(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"ambiguous-root-hits": 1},
            "candidateNameCounts": {"RuntimeGUObjectArray": 1},
            "candidateLocations": [
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x7f000028c4c0",
                    "fileOffset": "0x28c4c0",
                    "targetImage": "false",
                    "map": "",
                }
            ],
            "coverage": {
                "anonymousWritableMappingCount": 1,
                "objectArrayHits": 1,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--suppress-runtime-candidate-carry-forward",
                "--suppress-runtime-candidate-carry-forward-reason",
                "current root-refresh rejected near-miss candidates",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS", env)
        self.assertIn("Suppressed runtime root candidate carry-forward entries", " ".join(plan["notes"]))
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertFalse(carry["provided"])
        self.assertTrue(carry["suppressed"])
        self.assertEqual(carry["suppressedEntries"], ["RuntimeGUObjectArray@rwfile=0x28c4c0"])
        self.assertEqual(carry["suppressedEntryCount"], 1)
        self.assertEqual(
            carry["suppressionReason"],
            "current root-refresh rejected near-miss candidates",
        )

    def test_empty_root_recovery_input_blocks_runtime_root_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "empty-root-candidates.json"
            candidates.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue-writable-root-shape-candidates/v1",
                        "anchorPreset": "object-discovery",
                        "candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            plan = self.run_plan(
                tmp,
                report(),
                "--candidate-globals-json",
                str(candidates),
                "--suppress-runtime-candidate-carry-forward",
                platform="server",
            )

        self.assertIn("empty-root-recovery-candidate-input", {item["code"] for item in plan["blockers"]})
        self.assertIn(
            "Root-recovery candidate input was provided, but it emitted no candidate globals",
            " ".join(plan["notes"]),
        )

    def test_ambiguous_linux_runtime_object_array_locations_are_carried_forward_numbered(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"ambiguous-root-hits": 1},
            "candidateNameCounts": {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 2},
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x7f00001e1e18",
                    "fileOffset": "0x1e1e18",
                    "targetImage": "false",
                    "map": "",
                },
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x7f000028c4c0",
                    "fileOffset": "0x28c4c0",
                    "targetImage": "false",
                    "map": "",
                },
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x7f00003448c8",
                    "fileOffset": "0x3448c8",
                    "targetImage": "false",
                    "map": "",
                },
            ],
            "coverage": {
                "targetWritableImageCount": 4,
                "anonymousWritableMappingCount": 2,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 1,
                "objectArrayHits": 2,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"],
            "RuntimeFNamePool@rwfile=0x1e1e18;"
            "RuntimeGUObjectArrayCandidate1@rwfile=0x28c4c0;"
            "RuntimeGUObjectArrayCandidate2@rwfile=0x3448c8",
        )
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertEqual(
            carry["entries"],
            [
                "RuntimeFNamePool@rwfile=0x1e1e18",
                "RuntimeGUObjectArrayCandidate1@rwfile=0x28c4c0",
                "RuntimeGUObjectArrayCandidate2@rwfile=0x3448c8",
            ],
        )
        self.assertEqual(
            carry["anchorCounts"],
            {
                "RuntimeFNamePool": 1,
                "RuntimeGUObjectArrayCandidate1": 1,
                "RuntimeGUObjectArrayCandidate2": 1,
            },
        )
        self.assertTrue(carry["groupCoverage"]["names"]["ready"])
        self.assertTrue(carry["groupCoverage"]["objects"]["ready"])

    def test_validated_fname_does_not_suppress_unvalidated_object_array_candidates(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"ambiguous-root-hits": 1},
            "validatedNames": ["RuntimeFNamePool"],
            "validatedLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x7f00001e1e18",
                    "fileOffset": "0x1e1e18",
                    "targetImage": "false",
                    "map": "",
                },
            ],
            "candidateNameCounts": {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 2},
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x7f00001e1e18",
                    "fileOffset": "0x1e1e18",
                    "targetImage": "false",
                    "map": "",
                },
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x7f000028c4c0",
                    "fileOffset": "0x28c4c0",
                    "targetImage": "false",
                    "map": "",
                },
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x7f00003448c8",
                    "fileOffset": "0x3448c8",
                    "targetImage": "false",
                    "map": "",
                },
            ],
            "coverage": {
                "targetWritableImageCount": 4,
                "anonymousWritableMappingCount": 2,
                "scannedSlots": 8192,
                "fnameProbes": 8192,
                "objectArrayProbes": 8192,
                "fnameHits": 1,
                "objectArrayHits": 2,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"],
            "RuntimeFNamePool@rwfile=0x1e1e18;"
            "RuntimeGUObjectArrayCandidate1@rwfile=0x28c4c0;"
            "RuntimeGUObjectArrayCandidate2@rwfile=0x3448c8",
        )
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertTrue(carry["groupCoverage"]["objects"]["ready"])

    def test_validated_runtime_locations_override_ambiguous_candidates(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": True,
            "failureCounts": {"ambiguous-root-hits": 1},
            "validatedNames": ["RuntimeFNamePool", "RuntimeGUObjectArray"],
            "candidateNameCounts": {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 35},
            "validatedLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x557e1201ce18",
                    "fileOffset": "0x1e1e18",
                    "targetImage": "false",
                    "map": "",
                },
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": "0x557e120c74c0",
                    "fileOffset": "0x28c4c0",
                    "targetImage": "false",
                    "map": "",
                },
            ],
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x557e1201ce18",
                    "fileOffset": "0x1e1e18",
                    "targetImage": "false",
                    "map": "",
                },
            ]
            + [
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": f"0x7f{i:08x}",
                    "fileOffset": f"0x{i:x}",
                    "targetImage": "false",
                    "map": "",
                }
                for i in range(35)
            ],
            "coverage": {
                "targetWritableImageCount": 18,
                "anonymousWritableMappingCount": 9,
                "scannedSlots": 4096,
                "fnameProbes": 4096,
                "objectArrayProbes": 4096,
                "fnameHits": 1,
                "objectArrayHits": 35,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"],
            "RuntimeFNamePool@rwfile=0x1e1e18;RuntimeGUObjectArray@rwfile=0x28c4c0",
        )
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertEqual(
            carry["entries"],
            ["RuntimeFNamePool@rwfile=0x1e1e18", "RuntimeGUObjectArray@rwfile=0x28c4c0"],
        )

    def test_manual_reviewed_runtime_roots_suppress_same_name_ambiguous_carry_forward(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": True,
            "failureCounts": {"ambiguous-root-hits": 1},
            "validatedNames": ["RuntimeFNamePool", "RuntimeGUObjectArray"],
            "candidateNameCounts": {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 3},
            "candidateLocations": [
                {
                    "name": "RuntimeFNamePool",
                    "addr": "0x557e1201ce18",
                    "fileOffset": "0x1e1e18",
                    "targetImage": "false",
                    "map": "",
                }
            ]
            + [
                {
                    "name": "RuntimeGUObjectArray",
                    "addr": f"0x7f{i:08x}",
                    "fileOffset": f"0x{i:x}",
                    "targetImage": "false",
                    "map": "",
                }
                for i in range(3)
            ],
            "coverage": {
                "targetWritableImageCount": 4,
                "anonymousWritableMappingCount": 2,
                "scannedSlots": 4096,
                "fnameProbes": 4096,
                "objectArrayProbes": 4096,
                "fnameHits": 1,
                "objectArrayHits": 3,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--candidate-global",
                "RuntimeFNamePool@rwfile=0x1e1e18",
                "--candidate-global",
                "RuntimeGUObjectArray@rwfile=0x28c4c0",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"],
            "RuntimeFNamePool@rwfile=0x1e1e18;RuntimeGUObjectArray@rwfile=0x28c4c0",
        )
        carry = plan["nextCanaryContract"]["runtimeCandidateCarryForward"]
        self.assertFalse(carry["provided"])
        self.assertEqual(carry["entries"], [])
        self.assertEqual(carry["excludedNames"], ["RuntimeFNamePool", "RuntimeGUObjectArray"])
        self.assertIn(
            "Skipped ambiguous carry-forward candidates for reviewed manual runtime roots",
            " ".join(plan["notes"]),
        )

    def test_promoted_manual_runtime_roots_do_not_require_world_root_candidate(self):
        readiness = report({"runtimeRootDiscovery": True, "runtimeRootValidation": True})
        candidates = {
            "schemaVersion": "dune-ue-candidate-globals/v1",
            "candidates": [
                {
                    "name": "GUObjectArray",
                    "imageOffset": "0x166d27f8",
                    "rootShape": {
                        "qwordRefCount": 2,
                        "kindCounts": {"read": 1, "write": 1},
                    },
                    "hintQuality": {"contextCount": 1, "specificContextCount": 1},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidates.json"
            candidate_path.write_text(json.dumps(candidates), encoding="utf-8")
            plan = self.run_plan(
                tmp,
                readiness,
                "--candidate-globals-json",
                str(candidate_path),
                "--candidate-global",
                "RuntimeFNamePool@rwfile=0x1e1e18",
                "--candidate-global",
                "RuntimeGUObjectArray@rwfile=0x28c4c0",
                platform="server",
            )

        blocker_codes = {row["code"] for row in plan["blockers"]}
        self.assertNotIn("incomplete-root-recovery-object-candidates", blocker_codes)
        self.assertIn(
            "Skipping root-recovery world-candidate blocker",
            " ".join(plan["notes"]),
        )

    def test_reflection_plan_enables_read_only_reflection(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                report({"objectDiscovery": True}, ["ue-reflection-surface", "ue-uobject-probe"]),
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "reflection")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST"], "true")

    def test_validated_runtime_roots_enable_deeper_object_array_function_canary(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "runtimeRootValidation": True,
                "runtimeRootDiscovery": False,
                "targetObjectDiscovery": False,
                "targetHooks": False,
                "luaFunctionRegistryRuntime": False,
                "reflection": False,
                "ueFunctionParamDescriptors": False,
                "ueFunctionParamContainerChildren": False,
                "ueFunctionIdentities": False,
                "ueFunctionNativeIdentities": False,
                "ueFunctionFlags": False,
            },
            ["ue-reflection-surface", "ue-uobject-probe"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "read-only")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS"], "16384")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX"], "256")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS"], "128")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS"], "64")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        note_text = " ".join(plan["notes"])
        self.assertIn("wide read-only GUObjectArray walk", note_text)
        self.assertIn("scan runtime UObject vtables for ProcessEvent candidates", note_text)
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["functionRuntimeEvidence"]["ueFunctionParamDescriptors"])
        self.assertFalse(contract["functionRuntimeEvidence"]["ueFunctionNativeIdentities"])
        self.assertFalse(contract["functionRuntimeEvidence"]["ueFunctionFlags"])
        self.assertIn("readable UFunction param descriptor evidence from functionLink", contract["requiredValidation"])
        self.assertIn("decoded UFunction container child property evidence", contract["requiredValidation"])
        self.assertIn("decoded UFunction path identity evidence", contract["requiredValidation"])
        self.assertIn("promoted UFunction native identity evidence", contract["requiredValidation"])
        self.assertIn("readable UFunction FunctionFlags evidence", contract["requiredValidation"])

    def test_object_discovery_coverage_missing_components_are_reported(self):
        readiness = with_object_discovery_coverage(
            report({"objectDiscovery": False}),
            object_ready=False,
            find_object_ready=False,
            missing=["pointerProbe", "fnameDecoder"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        self.assertEqual(plan["selectedStage"], "object-discovery")
        contract = plan["nextCanaryContract"]
        self.assertTrue(contract["objectDiscoveryCoverage"]["provided"])
        self.assertFalse(contract["objectDiscoveryCoverage"]["readyForObjectDiscovery"])
        self.assertFalse(contract["objectDiscoveryCoverage"]["readyForFindObjectSemantics"])
        self.assertEqual(contract["objectDiscoveryCoverage"]["missingObjectDiscoveryComponents"], ["pointerProbe", "fnameDecoder"])
        self.assertEqual(contract["objectDiscoveryCoverage"]["missingFindObjectComponents"], ["pointerProbe", "fnameDecoder"])
        self.assertIn("object-discovery coverage components: pointerProbe, fnameDecoder", contract["requiredValidation"])
        self.assertIn("FindObject semantics coverage components: pointerProbe, fnameDecoder", contract["requiredValidation"])
        note_text = " ".join(plan["notes"])
        self.assertIn("Object discovery coverage is incomplete", note_text)
        self.assertIn("pointerProbe", note_text)
        self.assertIn("fnameDecoder", note_text)

    def test_target_anchor_coverage_fields_override_stale_flattened_ready_keys(self):
        readiness = with_anchor_coverage(
            report({"objectDiscovery": True}),
            object_ready=True,
            hook_ready=True,
            package_ready=True,
            target_object_ready=False,
            target_hook_ready=False,
            target_package_ready=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        self.assertEqual(plan["selectedStage"], "object-discovery")
        contract = plan["nextCanaryContract"]
        prepared = contract["preparedAnchorCoverage"]
        self.assertTrue(prepared["readyForObjectDiscovery"])
        self.assertFalse(prepared["readyForTargetObjectDiscovery"])
        self.assertFalse(prepared["readyForTargetHookPlanning"])
        self.assertFalse(prepared["readyForTargetPackageLoading"])
        blocker_codes = {item["code"] for item in plan["selectedStageBlockers"]}
        self.assertIn("incomplete-prepared-object-anchor-coverage", blocker_codes)
        note_text = " ".join(plan["notes"])
        self.assertIn("Prepared anchor coverage is missing target-image object-discovery groups", note_text)

    def test_find_object_semantics_missing_components_are_reported(self):
        readiness = with_object_discovery_coverage(
            report({"objectDiscovery": True}, ["ue-reflection-surface", "ue-uobject-probe"]),
            object_ready=True,
            find_object_ready=False,
            missing=["outerChainIdentities", "luaFindObjectApi"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        self.assertEqual(plan["selectedStage"], "object-discovery")
        contract = plan["nextCanaryContract"]
        self.assertTrue(contract["objectDiscoveryCoverage"]["provided"])
        self.assertTrue(contract["objectDiscoveryCoverage"]["readyForObjectDiscovery"])
        self.assertFalse(contract["objectDiscoveryCoverage"]["readyForFindObjectSemantics"])
        self.assertEqual(
            contract["objectDiscoveryCoverage"]["missingFindObjectComponents"],
            ["outerChainIdentities", "luaFindObjectApi"],
        )
        self.assertIn(
            "FindObject semantics coverage components: outerChainIdentities, luaFindObjectApi",
            contract["requiredValidation"],
        )
        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        note_text = " ".join(plan["notes"])
        self.assertIn("FindObject semantics are not fully proven", note_text)
        self.assertIn("outerChainIdentities", note_text)
        self.assertIn("luaFindObjectApi", note_text)

    def test_find_object_semantics_missing_blocks_hook_probe(self):
        readiness = with_object_discovery_coverage(
            report({"objectDiscovery": True, "reflection": True}),
            object_ready=True,
            find_object_ready=False,
            missing=["nativeIdentities"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("nativeIdentities", " ".join(plan["notes"]))

    def test_self_test_only_object_registry_runtime_blocks_escalation(self):
        readiness = with_object_discovery_coverage(
            report(
                {
                    "objectDiscovery": True,
                    "reflection": True,
                    "luaObjectRegistryRuntime": False,
                    "luaDecodedObjectAliasesRuntime": False,
                    "ueObjectArrayRegistryRuntime": False,
                }
            ),
            object_ready=True,
            find_object_ready=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        codes = {item["code"] for item in plan["blockers"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("self-test-only-object-registry", codes)
        self.assertIn("self-test-only-decoded-object-aliases", codes)
        self.assertIn("self-test-only-object-array-registry", codes)
        self.assertFalse(contract["registryRuntimeEvidence"]["luaObjectRegistryRuntime"])
        self.assertFalse(contract["registryRuntimeEvidence"]["luaDecodedObjectAliasesRuntime"])
        self.assertFalse(contract["registryRuntimeEvidence"]["ueObjectArrayRegistryRuntime"])
        self.assertEqual(
            contract["registryRuntimeEvidenceContract"]["luaObjectRegistryRuntime"]["requiredProvenance"],
            "registryProvenance=runtime",
        )
        self.assertEqual(
            contract["registryRuntimeEvidenceContract"]["ueObjectArrayRegistryRuntime"]["requiredSource"],
            "ue-object-array or ue-object-array-fname",
        )
        self.assertIn("non-self-test UObject registry evidence", contract["requiredValidation"])
        self.assertIn("UObject registry log rows with registryProvenance=runtime", contract["requiredValidation"])
        self.assertIn("non-self-test decoded UObject alias registry evidence", contract["requiredValidation"])
        self.assertIn("decoded UObject alias log rows with registryProvenance=runtime", contract["requiredValidation"])
        self.assertIn("non-self-test object-array registry evidence", contract["requiredValidation"])
        self.assertIn("object-array registry log rows with registryProvenance=runtime", contract["requiredValidation"])

    def test_self_test_only_function_registry_runtime_blocks_hook_probe(self):
        readiness = with_object_discovery_coverage(
            report(
                {
                    "objectDiscovery": True,
                    "reflection": True,
                    "luaFunctionRegistryRuntime": False,
                }
            ),
            object_ready=True,
            find_object_ready=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "reflection")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("self-test-only-function-registry", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["registryRuntimeEvidence"]["luaFunctionRegistryRuntime"])
        self.assertEqual(
            contract["registryRuntimeEvidenceContract"]["luaFunctionRegistryRuntime"]["events"],
            ["lua-function-registry-check"],
        )
        self.assertIn("non-self-test UFunction registry evidence", contract["requiredValidation"])
        self.assertIn("UFunction registry log rows with registryProvenance=runtime", contract["requiredValidation"])

    def test_missing_registry_runtime_gate_fields_are_not_treated_as_live_evidence(self):
        readiness = with_object_discovery_coverage(
            report({"objectDiscovery": True, "reflection": True}),
            object_ready=True,
            find_object_ready=True,
        )
        for key in (
            "luaObjectRegistryRuntime",
            "luaFunctionRegistryRuntime",
            "luaDecodedObjectAliasesRuntime",
            "ueObjectArrayRegistryRuntime",
        ):
            readiness["ready"].pop(key, None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        self.assertEqual(plan["selectedStage"], "object-discovery")
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["registryRuntimeEvidence"]["luaObjectRegistryRuntime"])
        self.assertFalse(contract["registryRuntimeEvidence"]["luaFunctionRegistryRuntime"])
        self.assertFalse(contract["registryRuntimeEvidence"]["luaDecodedObjectAliasesRuntime"])
        self.assertFalse(contract["registryRuntimeEvidence"]["ueObjectArrayRegistryRuntime"])

    def test_claimed_object_discovery_without_proven_core_anchors_stays_read_only(self):
        readiness = report(
            {"objectDiscovery": True, "reflection": True, "hookDispatch": True},
            ue_groups=ue_anchor_groups(names=0, objects=0, world=0, dispatch=0, reflection=0),
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE", env)
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        note_text = " ".join(plan["notes"])
        self.assertIn("does not show proven names/objects/world UE anchor groups", note_text)
        self.assertIn("mapped ue-anchor or resolved ue-anchor-signature", note_text)
        self.assertIn("unproven-object-anchor-groups", {item["code"] for item in plan["blockers"]})
        contract = plan["nextCanaryContract"]
        self.assertEqual(contract["schemaVersion"], "dune-ue4ss-next-canary-contract/v1")
        self.assertEqual(contract["missingAnchorGroups"]["objectDiscovery"], ["names", "objects", "world"])
        self.assertEqual(contract["missingAnchorGroups"]["hookPlanning"], ["names", "objects", "world", "dispatch"])
        self.assertEqual(contract["missingAnchorGroups"]["reflection"], ["reflection"])
        self.assertFalse(contract["readOnlyUntil"]["objectDiscoveryAnchors"])
        self.assertFalse(contract["readOnlyUntil"]["hookPlanningAnchors"])
        self.assertFalse(contract["readOnlyUntil"]["reflectionSurface"])
        self.assertIn("same-build signature validation JSON", contract["requiredValidation"])
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE", contract["envNames"])
        self.assertEqual(contract["anchorSignatureFileEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE")

    def test_claimed_object_discovery_without_target_image_anchors_stays_read_only(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "targetObjectDiscovery": False,
                "reflection": True,
                "hookDispatch": True,
                "targetNames": False,
                "targetObjects": False,
                "targetWorld": False,
                "targetDispatch": False,
            },
            ue_groups=ue_anchor_groups(
                target_names=0,
                target_objects=0,
                target_world=0,
                target_dispatch=0,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE", env)
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("unproven-target-object-anchor-groups", {item["code"] for item in plan["blockers"]})
        note_text = " ".join(plan["notes"])
        self.assertIn("target-image object discovery is not proven", note_text)
        contract = plan["nextCanaryContract"]
        self.assertEqual(
            contract["missingAnchorGroups"]["targetObjectDiscovery"],
            ["names", "objects", "world", "dispatch"],
        )
        self.assertFalse(contract["readOnlyUntil"]["targetObjectDiscoveryAnchors"])
        self.assertEqual(contract["currentTargetAnchorGroupCounts"]["dispatch"], 0)
        self.assertIn("target-image names/object/world/dispatch anchors", contract["requiredValidation"])

    def test_claimed_hook_dispatch_without_proven_dispatch_anchor_blocks_hook_probe(self):
        readiness = report(
            {"objectDiscovery": True, "reflection": True, "hookDispatch": True},
            ue_groups=ue_anchor_groups(dispatch=0),
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "reflection")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("does not show a proven dispatch anchor", " ".join(plan["notes"]))
        self.assertIn("unproven-dispatch-anchor", {item["code"] for item in plan["blockers"]})

    def test_claimed_hook_dispatch_without_target_dispatch_anchor_blocks_hook_probe(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "targetObjectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "targetDispatch": False,
            },
            ue_groups=ue_anchor_groups(target_dispatch=0),
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "hook-probe")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL"], "true")
        self.assertIn("unproven-target-dispatch-anchor", {item["code"] for item in plan["blockers"]})
        self.assertIn("dispatch anchors are not proven in the target executable", " ".join(plan["notes"]))

    def test_package_load_claim_without_target_package_anchor_is_reported(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "targetObjectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "luaDispatch": True,
                "luaLoadAssetPackage": True,
                "targetPackageLoadingSurface": False,
            },
            ue_groups=ue_anchor_groups(target_package=0),
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("unproven-target-package-loading-anchor", codes)
        self.assertIn("Package-backed LoadAsset is not target-image ready", " ".join(plan["notes"]))
        contract = plan["nextCanaryContract"]
        self.assertEqual(contract["missingAnchorGroups"]["targetPackageLoading"], ["package"])
        self.assertFalse(contract["readOnlyUntil"]["targetPackageLoadingAnchors"])
        self.assertEqual(contract["currentTargetAnchorGroupCounts"]["package"], 0)
        self.assertIn(
            "target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchor",
            contract["requiredValidation"],
        )
        strict_contract = contract["postCanaryVerification"]["strictRuntimeContract"]
        self.assertIn("targetPackageLoadingSurface", strict_contract["missingSignatureAnchorReadyKeys"])

    def test_hook_probe_requires_explicit_max_stage(self):
        readiness = report({"objectDiscovery": True, "reflection": True})
        with tempfile.TemporaryDirectory() as tmp:
            read_only = self.run_plan(tmp, readiness)
            hook_probe = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        read_only_env = {item["name"]: item["value"] for item in read_only["env"]}
        hook_env = {item["name"]: item["value"] for item in hook_probe["env"]}
        self.assertEqual(read_only["selectedStage"], "hook-probe")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", read_only_env)
        self.assertIn("suppresses code-patching probes", " ".join(read_only["notes"]))
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL"], "true")
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE"], "true")
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL"], "true")

    def test_prepared_coverage_blocks_escalation_when_object_groups_missing(self):
        readiness = with_anchor_coverage(
            report({"objectDiscovery": True, "reflection": True}),
            object_ready=False,
            hook_ready=False,
            missing=["objects"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "object-discovery")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("missing target-image object-discovery groups", " ".join(plan["notes"]))
        self.assertIn("objects", " ".join(plan["notes"]))
        self.assertIn("incomplete-prepared-object-anchor-coverage", {item["code"] for item in plan["blockers"]})

    def test_prepared_coverage_blocks_hook_escalation_without_dispatch_evidence(self):
        readiness = with_anchor_coverage(
            report({"objectDiscovery": True, "reflection": True}),
            object_ready=True,
            hook_ready=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "reflection")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("lacks target-image ProcessEvent-level dispatch evidence", " ".join(plan["notes"]))

    def test_prepared_coverage_hook_gate_uses_platform_prefixes_equally(self):
        readiness = with_anchor_coverage(
            report({"objectDiscovery": True, "reflection": True}),
            object_ready=True,
            hook_ready=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            linux = self.run_plan(tmp, readiness, "--max-stage", "hook-probe", platform="linux-client")
            server = self.run_plan(tmp, readiness, "--max-stage", "hook-probe", platform="server")

        linux_env = {item["name"]: item["value"] for item in linux["env"]}
        server_env = {item["name"]: item["value"] for item in server["env"]}
        self.assertEqual(linux["selectedStage"], "hook-probe")
        self.assertEqual(server["selectedStage"], "hook-probe")
        self.assertEqual(linux_env["DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertEqual(linux_env["DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE"], "true")
        self.assertEqual(server_env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertEqual(server_env["DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE"], "true")
        self.assertEqual(linux["nextCanaryContract"]["anchorSignatureFileEnvName"], "DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE")
        self.assertEqual(server["nextCanaryContract"]["anchorSignatureFileEnvName"], "DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE")

    def test_missing_target_dispatch_after_target_object_groups_selects_hook_probe(self):
        readiness = with_anchor_coverage(
            report(
                {
                    "objectDiscovery": True,
                    "targetObjectDiscovery": False,
                    "targetNames": True,
                    "targetObjects": True,
                    "targetWorld": True,
                    "targetDispatch": False,
                    "reflection": True,
                    "hookDispatch": False,
                    "ueProcessEventHookProbe": False,
                    "ueProcessEventHookRuntimeTarget": False,
                },
                ue_groups=ue_anchor_groups(target_dispatch=0),
            ),
            object_ready=True,
            hook_ready=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "hook-probe", platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "hook-probe")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL"], "true")
        self.assertNotIn("unproven-target-object-anchor-groups", {item["code"] for item in plan["blockers"]})

    def test_per_loader_readiness_blocks_platform_escalation_when_aggregate_is_ready(self):
        aggregate = report({"objectDiscovery": True, "reflection": True, "hookDispatch": True})
        aggregate["perLoaderReadiness"] = {
            "win-client": {
                "logCount": 1,
                "paths": ["/tmp/dune-win-client-probe-loader.log"],
                "loaders": ["win-client"],
                "ready": dict(aggregate["ready"]),
                "gates": list(aggregate["gates"]),
                "anchorGroups": aggregate["anchorGroups"],
                "ue": aggregate["ue"],
                "signatures": aggregate.get("signatures", {}),
            },
            "client": {
                "logCount": 1,
                "paths": ["/tmp/dune-client-probe-loader.log"],
                "loaders": ["client"],
                "ready": {**aggregate["ready"], "objectDiscovery": False, "reflection": False, "hookDispatch": False},
                "gates": list(aggregate["gates"]),
                "failedGates": ["ue-objects"],
                "anchorGroups": aggregate["anchorGroups"],
                "ue": ue_anchor_groups(objects=0),
                "signatures": aggregate.get("signatures", {}),
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            linux = self.run_plan(tmp, aggregate, "--max-stage", "hook-probe", platform="linux-client")
            windows = self.run_plan(tmp, aggregate, "--max-stage", "hook-probe", platform="windows")

        self.assertEqual(linux["selectedStage"], "object-discovery")
        self.assertTrue(linux["selectedLoaderReadiness"]["available"])
        self.assertEqual(linux["selectedLoaderReadiness"]["loader"], "client")
        self.assertEqual(windows["selectedStage"], "hook-probe")
        self.assertEqual(windows["selectedLoaderReadiness"]["loader"], "win-client")

    def test_contract_includes_post_canary_verification_commands_for_all_platforms(self):
        readiness = report()
        expected = {
            "windows": ("--client-log", "/tmp/dune-win-client-probe-loader.log", "win-client"),
            "linux-client": ("--client-log", "/tmp/dune-client-probe-loader.log", "client"),
            "server": ("--server-log", "/tmp/dune-server-probe-loader.log", "server"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for platform, (log_arg, log_path, loader) in expected.items():
                plan = self.run_plan(tmp, readiness, platform=platform)
                verification = plan["nextCanaryContract"]["postCanaryVerification"]
                command = verification["readinessCommand"]
                prep_command = verification["prepareAnchorCanaryCommand"]
                verify_command = verification["postCanaryVerifyCommand"]
                strict_contract = verification["strictRuntimeContract"]
                self.assertEqual(verification["schemaVersion"], "dune-ue4ss-post-canary-verification/v1")
                self.assertEqual(verification["defaultLogPath"], log_path)
                self.assertEqual(strict_contract["envName"], "DUNE_UE4SS_STRICT_RUNTIME_CONTRACT")
                self.assertEqual(strict_contract["enabledValue"], "true")
                self.assertIn("targetImageProcess", strict_contract["requiredReadyKeys"])
                self.assertIn("runtimeRootDiscovery", strict_contract["requiredReadyKeys"])
                self.assertIn("runtimeRootValidation", strict_contract["requiredReadyKeys"])
                self.assertIn("targetObjectDiscovery", strict_contract["requiredReadyKeys"])
                self.assertIn("targetHooks", strict_contract["requiredReadyKeys"])
                self.assertIn("ueProcessEventHookRuntimeTarget", strict_contract["requiredReadyKeys"])
                self.assertIn("ueProcessEventLiveLuaDispatch", strict_contract["requiredReadyKeys"])
                self.assertIn("ueProcessEventLuaHookAliasRouting", strict_contract["requiredReadyKeys"])
                self.assertIn("luaReflectionLiveDescriptorValuesRuntime", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackageCrashGuard", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackageGuardedCall", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackageReturnValidation", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackageNativeCallAdapter", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackageInvocationDescriptor", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackageNativeExecutor", strict_contract["requiredReadyKeys"])
                self.assertIn("luaLoadAssetPackage", strict_contract["requiredReadyKeys"])
                self.assertIn("signatureManifestExact", strict_contract["requiredSignatureAnchorReadyKeys"])
                self.assertIn("anchorCoverageHookPlanning", strict_contract["requiredSignatureAnchorReadyKeys"])
                self.assertIn("anchorCoveragePackageLoading", strict_contract["requiredSignatureAnchorReadyKeys"])
                self.assertIn("targetPackageLoadingSurface", strict_contract["requiredSignatureAnchorReadyKeys"])
                self.assertTrue(strict_contract["contractReady"])
                self.assertTrue(strict_contract["runtimeReady"])
                self.assertTrue(strict_contract["signatureAnchorReady"])
                self.assertEqual(strict_contract["missingReadyKeys"], [])
                self.assertEqual(strict_contract["missingSignatureAnchorReadyKeys"], [])
                self.assertTrue(strict_contract["ready"]["luaFunctionRegistryRuntime"])
                self.assertTrue(strict_contract["signatureAnchorReadyKeys"]["signatureManifestPromotable"])
                live_target = verification["liveTargetImageCanaryContract"]
                self.assertEqual(
                    live_target["schemaVersion"],
                    "dune-ue4ss-live-target-image-canary-contract/v1",
                )
                self.assertTrue(live_target["ready"])
                self.assertEqual(live_target["missingKeys"], [])
                self.assertTrue(live_target["groups"]["runtimePackageLoading"]["ready"])
                self.assertTrue(live_target["groups"]["runtimeProcessEventDispatch"]["ready"])
                self.assertTrue(live_target["groups"]["runtimeCallFunctionDispatch"]["ready"])
                self.assertEqual(verification["inputFiles"]["loaderLog"], log_path)
                self.assertEqual(verification["inputFiles"]["signatureValidation"], "signature-validation.json")
                self.assertEqual(verification["inputFiles"]["anchorCoverage"], "anchor-coverage.json")
                self.assertEqual(verification["outputFiles"]["readinessJson"], "ue4ss-readiness.json")
                self.assertEqual(verification["outputFiles"]["objectDiscoveryCoverage"], "object-discovery-coverage.json")
                self.assertEqual(verification["outputFiles"]["postCanaryGapSummaryJson"], "ue4ss-port-gaps.json")
                self.assertEqual(verification["outputFiles"]["postCanaryGapSummary"], "ue4ss-port-gaps.md")
                self.assertEqual(verification["outputFiles"]["evidenceInventoryJson"], "ue4ss-evidence-inventory.json")
                self.assertEqual(verification["outputFiles"]["evidenceInventory"], "ue4ss-evidence-inventory.md")
                self.assertEqual(verification["outputFiles"]["postCanarySummary"], "post-canary-summary.md")
                self.assertEqual(
                    prep_command[:6],
                    ["python3", "scripts/prepare-ue-anchor-canary.py", "--platform", platform, "--binary", "<target-binary>"],
                )
                self.assertIn("--loader-log", prep_command)
                self.assertEqual(prep_command[prep_command.index("--loader-log") + 1], log_path)
                self.assertIn("--skip-readiness", prep_command)
                self.assertIn("--loader", prep_command)
                self.assertEqual(prep_command[prep_command.index("--loader") + 1], loader)
                self.assertIn("scripts/prepare-ue-anchor-canary.py", verification["prepareAnchorCanaryCommandText"])
                self.assertEqual(verify_command, ["build/ue4ss-anchor-canary/post-canary-verify.sh", log_path])
                self.assertIn("post-canary-verify.sh", verification["postCanaryVerifyCommandText"])
                self.assertEqual(command[:4], ["python3", "scripts/ue4ss-port-readiness.py", log_arg, log_path])
                self.assertIn("--loader", command)
                self.assertEqual(command[command.index("--loader") + 1], loader)
                self.assertIn("--signature-validation-json", command)
                self.assertIn("--anchor-coverage-json", command)
                self.assertIn("scripts/ue4ss-port-readiness.py", verification["readinessCommandText"])

    def test_prepare_anchor_canary_command_carries_target_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                report(
                    {
                        "targetNames": False,
                        "targetObjects": False,
                        "targetWorld": False,
                        "targetDispatch": False,
                        "targetPackageLoadingSurface": False,
                    }
                ),
                "--loader",
                "client",
                "--pid",
                "1234",
                "--exe-substring",
                "DuneSandbox",
                "--exe-substring",
                "DuneClient",
                platform="linux-client",
            )

        command = plan["nextCanaryContract"]["postCanaryVerification"]["prepareAnchorCanaryCommand"]
        command_text = plan["nextCanaryContract"]["postCanaryVerification"]["prepareAnchorCanaryCommandText"]
        self.assertEqual(command.count("--loader"), 1)
        self.assertEqual(command[command.index("--loader") + 1], "client")
        self.assertEqual(command.count("--pid"), 1)
        self.assertEqual(command[command.index("--pid") + 1], "1234")
        self.assertEqual(command.count("--exe-substring"), 2)
        self.assertIn("DuneSandbox", command)
        self.assertIn("DuneClient", command)
        self.assertIn("--loader client", command_text)
        self.assertIn("--pid 1234", command_text)
        self.assertIn("--exe-substring DuneSandbox", command_text)

    def test_target_image_anchor_recovery_commands_carry_linux_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            readiness = report(
                {
                    "targetNames": False,
                    "targetObjects": False,
                    "targetWorld": False,
                    "targetDispatch": False,
                    "targetPackageLoadingSurface": False,
                },
                ue_groups=ue_anchor_groups(
                    target_names=0,
                    target_objects=0,
                    target_world=0,
                    target_dispatch=0,
                    target_package=0,
                ),
            )
            plan = self.run_plan(
                tmp,
                readiness,
                "--loader",
                "client",
                "--pid",
                "1234",
                "--exe-substring",
                "DuneSandbox",
                platform="linux-client",
            )

        recovery = plan["nextCanaryContract"]["targetImageAnchorRecovery"]
        self.assertTrue(recovery["recommended"])
        self.assertIn("missing-target-object-anchor-groups", recovery["reasons"])
        self.assertIn("missing-target-hook-anchor-groups", recovery["reasons"])
        self.assertIn("missing-target-package-anchor-groups", recovery["reasons"])
        self.assertIn("missing-prepared-anchor-coverage", recovery["reasons"])
        self.assertIn("dispatch", recovery["missingTargetObjectGroups"])
        self.assertIn("dispatch", recovery["missingTargetHookGroups"])
        self.assertIn("package", recovery["missingTargetPackageGroups"])
        self.assertFalse(recovery["preparedAnchorCoverage"]["provided"])
        self.assertIn("scripts/summarize-linux-loader-xrefs.py", recovery["xrefCommandText"])
        self.assertIn("--pid 1234", recovery["xrefCommandText"])
        self.assertIn("--exe-substring DuneSandbox", recovery["xrefCommandText"])
        self.assertIn("ue-anchor-xrefs.json", recovery["xrefCommandText"])
        self.assertIn("scripts/promote-ue-anchor-xref-candidates.py", recovery["promoteCommandText"])
        self.assertIn("--require-target-source", recovery["promoteCommandText"])
        self.assertIn("ue-anchor-candidates.json", recovery["promoteCommandText"])
        self.assertIn("--xref-json build/ue4ss-anchor-canary/ue-anchor-candidates.json", recovery["prepareRecoveredCanaryCommandText"])
        self.assertIn("--loader client", recovery["prepareRecoveredCanaryCommandText"])
        self.assertIn("--pid 1234", recovery["prepareRecoveredCanaryCommandText"])
        self.assertIn("--exe-substring DuneSandbox", recovery["prepareRecoveredCanaryCommandText"])
        self.assertIn("recovered-target-anchors/post-canary-verify.sh", recovery["postRecoveryVerifyCommandText"])

    def test_target_image_anchor_recovery_uses_default_linux_loader_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, report(), platform="linux-client")

        recovery = plan["nextCanaryContract"]["targetImageAnchorRecovery"]
        command = recovery["prepareRecoveredCanaryCommand"]
        self.assertIn("--loader", command)
        self.assertEqual(command[command.index("--loader") + 1], "client")
        self.assertIn("--loader client", recovery["prepareRecoveredCanaryCommandText"])

    def test_target_image_anchor_recovery_not_recommended_when_target_coverage_ready(self):
        readiness = with_anchor_coverage(
            report(
                ue_groups=ue_anchor_groups(
                    names=2,
                    objects=2,
                    world=1,
                    dispatch=2,
                    package=4,
                    reflection=4,
                    target_names=2,
                    target_objects=2,
                    target_world=1,
                    target_dispatch=2,
                    target_package=4,
                    target_reflection=4,
                )
            ),
            object_ready=True,
            hook_ready=True,
            package_ready=True,
            target_object_ready=True,
            target_hook_ready=True,
            target_package_ready=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, platform="linux-client")

        recovery = plan["nextCanaryContract"]["targetImageAnchorRecovery"]
        self.assertFalse(recovery["recommended"])
        self.assertEqual(recovery["reasons"], [])
        self.assertEqual(recovery["missingTargetObjectGroups"], [])
        self.assertEqual(recovery["missingTargetHookGroups"], [])
        self.assertEqual(recovery["missingTargetPackageGroups"], [])
        self.assertTrue(recovery["preparedAnchorCoverage"]["provided"])

    def test_markdown_includes_target_image_anchor_recovery_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            readiness_path.write_text(json.dumps(report()), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "linux-client",
                    "--readiness-json",
                    str(readiness_path),
                    "--loader",
                    "client",
                    "--exe-substring",
                    "DuneSandbox",
                    "--format",
                    "markdown",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        self.assertIn("### Target-Image Anchor Recovery", result.stdout)
        self.assertIn("- Recovery reasons: `", result.stdout)
        self.assertIn("- Missing target groups: `", result.stdout)
        self.assertIn("scripts/summarize-linux-loader-xrefs.py", result.stdout)
        self.assertIn("scripts/promote-ue-anchor-xref-candidates.py", result.stdout)
        self.assertIn("scripts/prepare-ue-anchor-canary.py --platform linux-client", result.stdout)
        self.assertIn("recovered-target-anchors/post-canary-verify.sh", result.stdout)

    def test_contract_strict_runtime_contract_reports_missing_keys(self):
        readiness = report({
            "luaFunctionRegistryRuntime": False,
            "ueProcessEventLiveRuntimeContext": False,
            "signatureManifestPromotable": False,
            "anchorCoverageHookPlanning": False,
            "anchorCoveragePackageLoading": False,
            "targetPackageLoadingSurface": False,
        })
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        strict_contract = plan["nextCanaryContract"]["postCanaryVerification"]["strictRuntimeContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertFalse(strict_contract["runtimeReady"])
        self.assertFalse(strict_contract["signatureAnchorReady"])
        self.assertIn("luaFunctionRegistryRuntime", strict_contract["missingReadyKeys"])
        self.assertIn("ueProcessEventLiveRuntimeContext", strict_contract["missingReadyKeys"])
        self.assertNotIn("ueCallFunctionLiveLuaDispatch", strict_contract["missingReadyKeys"])
        self.assertIn("signatureManifestPromotable", strict_contract["missingSignatureAnchorReadyKeys"])
        self.assertIn("anchorCoverageHookPlanning", strict_contract["missingSignatureAnchorReadyKeys"])
        self.assertIn("anchorCoveragePackageLoading", strict_contract["missingSignatureAnchorReadyKeys"])
        self.assertIn("targetPackageLoadingSurface", strict_contract["missingSignatureAnchorReadyKeys"])
        self.assertNotIn("signatureManifestExact", strict_contract["missingSignatureAnchorReadyKeys"])

    def test_cross_platform_contract_requires_server_linux_and_windows_readiness(self):
        readiness = report()
        readiness["perLoaderReadiness"] = {
            "server": {
                "logCount": 1,
                "loaders": ["server"],
                "ready": dict(readiness["ready"]),
                "gates": list(readiness["gates"]),
                "anchorGroups": readiness["anchorGroups"],
                "ue": readiness["ue"],
            },
            "client": {
                "logCount": 1,
                "loaders": ["client"],
                "ready": dict(readiness["ready"]),
                "gates": list(readiness["gates"]),
                "anchorGroups": readiness["anchorGroups"],
                "ue": readiness["ue"],
            },
            "win-client": {
                "logCount": 1,
                "loaders": ["win-client"],
                "ready": dict(readiness["ready"]),
                "gates": list(readiness["gates"]),
                "anchorGroups": readiness["anchorGroups"],
                "ue": readiness["ue"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        cross = plan["nextCanaryContract"]["postCanaryVerification"]["crossPlatformStrictRuntimeContract"]
        self.assertEqual(
            cross["schemaVersion"],
            "dune-ue4ss-cross-platform-strict-runtime-contract/v1",
        )
        self.assertTrue(cross["ready"])
        self.assertEqual(cross["requiredLoaders"], ["server", "linux-client", "windows"])
        self.assertEqual(cross["missingLoaders"], [])
        self.assertEqual(cross["failedLoaders"], [])
        self.assertTrue(cross["loaders"]["server"]["ready"])
        self.assertEqual(cross["loaders"]["linux-client"]["loader"], "client")
        self.assertTrue(cross["loaders"]["windows"]["ready"])

    def test_cross_platform_contract_does_not_accept_aggregate_only_parity(self):
        readiness = report()
        linux_ready = dict(readiness["ready"])
        linux_ready["ueProcessEventLiveRuntimeContext"] = False
        readiness["perLoaderReadiness"] = {
            "client": {
                "logCount": 1,
                "loaders": ["client"],
                "ready": linux_ready,
                "gates": list(readiness["gates"]),
                "anchorGroups": readiness["anchorGroups"],
                "ue": readiness["ue"],
            },
            "win-client": {
                "logCount": 1,
                "loaders": ["win-client"],
                "ready": dict(readiness["ready"]),
                "gates": list(readiness["gates"]),
                "anchorGroups": readiness["anchorGroups"],
                "ue": readiness["ue"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        verification = plan["nextCanaryContract"]["postCanaryVerification"]
        self.assertTrue(verification["strictRuntimeContract"]["contractReady"])
        cross = verification["crossPlatformStrictRuntimeContract"]
        self.assertFalse(cross["ready"])
        self.assertEqual(cross["missingLoaders"], ["server"])
        self.assertEqual(cross["failedLoaders"], ["linux-client"])
        self.assertIn(
            "ueProcessEventLiveRuntimeContext",
            cross["loaders"]["linux-client"]["missingReadyKeys"],
        )
        self.assertTrue(cross["loaders"]["windows"]["ready"])

    def test_live_target_contract_tracks_call_function_dispatch_separately(self):
        readiness = report({
            "ueCallFunctionLiveLuaDispatch": False,
            "luaCallFunctionNativeInvoke": False,
            "luaCallFunctionNativeInvokePreflight": False,
            "luaCallFunctionNativeInvokeNonSelfTestGate": False,
        })
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        live_target = plan["nextCanaryContract"]["postCanaryVerification"]["liveTargetImageCanaryContract"]
        self.assertFalse(live_target["ready"])
        self.assertTrue(live_target["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertFalse(live_target["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimeCallFunctionDispatch"]["missingKeys"],
            [
                "ueCallFunctionLiveLuaDispatch",
                "luaCallFunctionNativeInvoke",
                "luaCallFunctionNativeInvokePreflight",
                "luaCallFunctionNativeInvokeNonSelfTestGate",
            ],
        )
        self.assertIn("ueCallFunctionLiveLuaDispatch", live_target["missingKeys"])
        self.assertIn("luaCallFunctionNativeInvoke", live_target["missingKeys"])

    def test_live_target_contract_requires_find_object_semantics(self):
        readiness = report({"findObjectSemantics": False})
        readiness = with_object_discovery_coverage(
            readiness,
            object_ready=True,
            find_object_ready=False,
            missing=["outerChainIdentities"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        verification = plan["nextCanaryContract"]["postCanaryVerification"]
        strict_contract = verification["strictRuntimeContract"]
        live_target = verification["liveTargetImageCanaryContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertIn("findObjectSemantics", strict_contract["missingReadyKeys"])
        self.assertFalse(live_target["ready"])
        self.assertFalse(live_target["groups"]["runtimeObjectRegistry"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimeObjectRegistry"]["missingKeys"],
            ["findObjectSemantics"],
        )

    def test_live_target_contract_requires_full_process_event_dispatch_evidence(self):
        readiness = report({"luaDispatch": True, "ueProcessEventLiveFunctionPath": False})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        live_target = plan["nextCanaryContract"]["postCanaryVerification"]["liveTargetImageCanaryContract"]
        strict_contract = plan["nextCanaryContract"]["postCanaryVerification"]["strictRuntimeContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertIn("ueProcessEventLiveFunctionPath", strict_contract["missingReadyKeys"])
        self.assertFalse(live_target["ready"])
        self.assertFalse(live_target["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertTrue(live_target["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimeProcessEventDispatch"]["missingKeys"],
            ["ueProcessEventLiveFunctionPath"],
        )
        self.assertIn(
            "decoded live ProcessEvent function path evidence",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_strict_contract_requires_call_function_native_invoke_gate(self):
        readiness = report({"luaCallFunctionNativeInvokeNonSelfTestGate": False})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        verification = plan["nextCanaryContract"]["postCanaryVerification"]
        strict_contract = verification["strictRuntimeContract"]
        live_target = verification["liveTargetImageCanaryContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertIn("luaCallFunctionNativeInvokeNonSelfTestGate", strict_contract["missingReadyKeys"])
        self.assertFalse(live_target["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimeCallFunctionDispatch"]["missingKeys"],
            ["luaCallFunctionNativeInvokeNonSelfTestGate"],
        )

    def test_live_target_contract_tracks_package_runtime_separately(self):
        readiness = report({"luaLoadAssetPackageNativeExecutor": False})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        verification = plan["nextCanaryContract"]["postCanaryVerification"]
        strict_contract = verification["strictRuntimeContract"]
        live_target = verification["liveTargetImageCanaryContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertFalse(strict_contract["runtimeReady"])
        self.assertIn("luaLoadAssetPackageNativeExecutor", strict_contract["missingReadyKeys"])
        self.assertFalse(live_target["ready"])
        self.assertTrue(live_target["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertTrue(live_target["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertFalse(live_target["groups"]["runtimePackageLoading"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimePackageLoading"]["missingKeys"],
            ["luaLoadAssetPackageNativeExecutor"],
        )
        self.assertIn("luaLoadAssetPackageNativeExecutor", live_target["missingKeys"])

    def test_live_target_contract_requires_package_native_invocation(self):
        readiness = report({"luaLoadAssetPackageNativeInvocation": False})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        verification = plan["nextCanaryContract"]["postCanaryVerification"]
        strict_contract = verification["strictRuntimeContract"]
        live_target = verification["liveTargetImageCanaryContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertIn("luaLoadAssetPackageNativeInvocation", strict_contract["missingReadyKeys"])
        self.assertFalse(live_target["groups"]["runtimePackageLoading"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimePackageLoading"]["missingKeys"],
            ["luaLoadAssetPackageNativeInvocation"],
        )
        self.assertIn("luaLoadAssetPackageNativeInvocation", live_target["missingKeys"])

    def test_live_target_contract_requires_load_class_package_native_invocation(self):
        readiness = report({"luaLoadClassPackageNativeInvocation": False})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        verification = plan["nextCanaryContract"]["postCanaryVerification"]
        strict_contract = verification["strictRuntimeContract"]
        live_target = verification["liveTargetImageCanaryContract"]
        self.assertFalse(strict_contract["contractReady"])
        self.assertIn("luaLoadClassPackageNativeInvocation", strict_contract["missingReadyKeys"])
        self.assertFalse(live_target["groups"]["runtimePackageLoading"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimePackageLoading"]["missingKeys"],
            ["luaLoadClassPackageNativeInvocation"],
        )
        self.assertIn("luaLoadClassPackageNativeInvocation", live_target["missingKeys"])

    def test_contract_strict_runtime_ready_when_all_runtime_keys_are_true(self):
        readiness = report({"objectDiscovery": True, "reflection": True, "hookDispatch": True, "luaDispatch": True})
        for key in (
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
            "ueObjectArrayRegistryRuntime",
            "luaFunctionIterationRuntime",
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
                "luaStaticConstructObjectNativeExecutorState",
                "luaStaticConstructObjectNativeExecutorReady",
                "luaStaticConstructObjectNativeInvoke",
                "luaLoadAssetPackage",
        ):
            readiness["ready"][key] = True
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        strict_contract = plan["nextCanaryContract"]["postCanaryVerification"]["strictRuntimeContract"]
        self.assertTrue(strict_contract["contractReady"])
        self.assertTrue(strict_contract["runtimeReady"])
        self.assertTrue(strict_contract["signatureAnchorReady"])
        self.assertEqual(strict_contract["missingReadyKeys"], [])
        self.assertEqual(strict_contract["missingSignatureAnchorReadyKeys"], [])
        self.assertTrue(all(strict_contract["ready"].values()))
        self.assertTrue(all(strict_contract["signatureAnchorReadyKeys"].values()))

    def test_contract_strict_runtime_uses_gate_evidence_when_ready_keys_are_absent(self):
        readiness = report()
        for key in (
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
            "ueObjectArrayRegistryRuntime",
            "luaFunctionIterationRuntime",
            "luaReflectionForEachPropertyRuntime",
            "luaReflectionLiveDescriptorTypedClassRuntime",
            "luaReflectionLiveDescriptorTypedValuesRuntime",
            "luaReflectionLiveDescriptorTypedSetValuesRuntime",
            "luaReflectionLiveDescriptorValuesRuntime",
            "signatureManifestExact",
            "signatureManifestPromotable",
            "anchorCoverageObjectDiscovery",
            "anchorCoverageHookPlanning",
            "anchorCoveragePackageLoading",
            "targetPackageLoadingSurface",
            "targetImageProcess",
            "runtimeRootDiscovery",
            "targetNames",
            "targetObjects",
            "targetWorld",
            "targetDispatch",
            "targetReflectionSurface",
        ):
            readiness["ready"].pop(key, None)
        readiness["gates"] = [
            {"name": name, "passed": True, "evidence": "", "blocker": ""}
            for name in (
                "ue-target-names",
                "ue-target-objects",
                "ue-target-world",
                "ue-target-dispatch",
                "ue-process-event-hook-runtime-target",
                "ue-call-function-hook-runtime-target",
                "ue-process-event-live-hook-runtime-target",
                "ue-call-function-live-hook-runtime-target",
                "ue-call-function-live-lua-dispatch",
                "ue-process-event-live-lua-dispatch",
                "ue-process-event-live-function-path",
                "ue-process-event-live-runtime-context",
                "ue-process-event-live-registry-context",
                "ue-process-event-live-runtime-registry-context",
                "ue-process-event-live-param-values",
                "ue-process-event-live-raw-param-values",
                "ue-process-event-live-container-param-values",
                "ue-process-event-live-array-container-param-values",
                "ue-process-event-live-set-container-param-values",
                "ue-process-event-live-map-container-param-values",
                "ue-process-event-live-set-map-container-param-values",
                "ue-process-event-live-container-data-samples",
                "ue-process-event-lua-context-handles",
                "ue-process-event-lua-param-accessors",
                "ue-process-event-live-class-aware-param-values",
                "ue-process-event-function-param-method",
                "ue-process-event-function-param-lookup-method",
                "ue-process-event-function-param-iteration-method",
                "ue-process-event-container-alias-methods",
                "ue-process-event-container-storage-layout-methods",
                "ue-process-event-lua-scalar-param-accessors",
                "ue-process-event-lua-name-string-param-accessors",
                "ue-process-event-lua-struct-param-accessors",
                "ue-process-event-lua-enum-param-accessors",
                "ue-process-event-lua-object-param-accessors",
                "ue-process-event-lua-bool-param-accessors",
                "ue-process-event-lua-hook-routing",
                "ue-process-event-lua-hook-alias-routing",
                "lua-object-registry-runtime",
                "lua-function-registry-runtime",
                "lua-decoded-object-aliases-runtime",
                "ue-object-array-registry-runtime",
                "lua-function-iteration-runtime",
                "lua-static-construct-object-native-executor-state",
                "lua-static-construct-object-native-executor-ready",
                "lua-static-construct-object-native-invoke",
                "lua-reflection-for-each-property-runtime",
                "lua-reflection-live-descriptor-typed-class-runtime",
                "lua-reflection-live-descriptor-typed-values-runtime",
                "lua-reflection-live-descriptor-typed-set-values-runtime",
                "lua-reflection-live-descriptor-values-runtime",
                "signature-manifest-exact",
                "signature-manifest-promotable",
                "anchor-coverage-object-discovery",
                "anchor-coverage-hook-planning",
                "anchor-coverage-package-loading",
                "ue-target-package-loading-surface",
                "target-image-process",
                "ue-runtime-root-discovery",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        strict_contract = plan["nextCanaryContract"]["postCanaryVerification"]["strictRuntimeContract"]
        self.assertTrue(strict_contract["contractReady"])
        self.assertTrue(strict_contract["runtimeReady"])
        self.assertTrue(strict_contract["signatureAnchorReady"])
        self.assertEqual(strict_contract["missingReadyKeys"], [])
        self.assertEqual(strict_contract["missingSignatureAnchorReadyKeys"], [])
        self.assertTrue(strict_contract["ready"]["ueProcessEventLiveRuntimeContext"])
        self.assertTrue(strict_contract["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertTrue(strict_contract["signatureAnchorReadyKeys"]["signatureManifestExact"])
        self.assertTrue(strict_contract["signatureAnchorReadyKeys"]["anchorCoverageHookPlanning"])
        self.assertTrue(strict_contract["signatureAnchorReadyKeys"]["anchorCoveragePackageLoading"])
        self.assertTrue(strict_contract["signatureAnchorReadyKeys"]["targetPackageLoadingSurface"])

    def test_missing_anchor_group_provenance_blocks_hook_escalation_on_all_platforms(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "anchorGroupProvenance": False,
            }
        )
        readiness["anchorGroups"] = {
            "anchors": {"missing": 1},
            "mappedAnchors": {},
            "signatures": {"missing": 1},
            "resolvedSignatures": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            windows = self.run_plan(tmp, readiness, "--max-stage", "hook-probe", platform="windows")
            linux = self.run_plan(tmp, readiness, "--max-stage", "hook-probe", platform="linux-client")
            server = self.run_plan(tmp, readiness, "--max-stage", "hook-probe", platform="server")

        for plan, hook_env in (
            (windows, "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE"),
            (linux, "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE"),
            (server, "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE"),
        ):
            env = {item["name"]: item["value"] for item in plan["env"]}
            self.assertEqual(plan["selectedStage"], "object-discovery")
            self.assertNotIn(hook_env, env)
            self.assertIn("missing-anchor-group-provenance", {item["code"] for item in plan["blockers"]})
            contract = plan["nextCanaryContract"]
            self.assertFalse(contract["anchorGroupProvenance"]["ready"])
            self.assertTrue(contract["anchorGroupProvenance"]["evidencePresent"])
            self.assertIn("loader-normalized UE anchor group provenance", contract["requiredValidation"])

    def test_contract_reports_signature_validation_counts(self):
        readiness = report({"objectDiscovery": True, "reflection": True})
        readiness["signatures"] = {
            "provided": True,
            "patternCount": 4,
            "promotableCount": 3,
            "allPromotable": False,
            "exactOnly": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        contract = plan["nextCanaryContract"]
        self.assertTrue(contract["signatureValidation"]["provided"])
        self.assertEqual(contract["signatureValidation"]["patternCount"], 4)
        self.assertEqual(contract["signatureValidation"]["promotableCount"], 3)
        self.assertFalse(contract["signatureValidation"]["allPromotable"])
        self.assertIn("all promoted signature rows", " ".join(contract["requiredValidation"]))

    def test_live_hook_plan_enables_bounded_call_context_logging(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "live-hook")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT"], "8")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH", env)

    def test_self_test_only_hook_probe_blocks_live_hook_escalation(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventHookRuntimeTarget": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "live-hook")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "hook-probe")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK", env)
        self.assertIn("self-test-only-hook-probe", {item["code"] for item in plan["blockers"]})
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["processEventRuntimeEvidence"]["hookRuntimeTarget"])
        self.assertEqual(
            contract["processEventRuntimeEvidenceContract"]["ueProcessEventHookRuntimeTarget"]["requiredFields"],
            ["selfTestTarget=false", "callSelfTest=false"],
        )
        self.assertTrue(contract["callFunctionRuntimeEvidence"]["hookRuntimeTarget"])
        self.assertEqual(
            contract["callFunctionRuntimeEvidenceContract"]["ueCallFunctionHookRuntimeTarget"]["events"],
            ["ue-call-function-hook"],
        )
        self.assertIn("non-self-test ProcessEvent hook probe target", contract["requiredValidation"])

    def test_self_test_only_call_function_hook_probe_blocks_live_hook_escalation(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueCallFunctionHookRuntimeTarget": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "live-hook")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "hook-probe")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK", env)
        self.assertIn("self-test-only-call-function-hook-probe", {item["code"] for item in plan["blockers"]})
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["callFunctionRuntimeEvidence"]["hookRuntimeTarget"])
        self.assertIn(
            "non-self-test CallFunctionByNameWithArguments hook probe target",
            contract["requiredValidation"],
        )

    def test_live_hook_plan_accepts_custom_call_context_log_limit(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "live-hook", "--live-call-log-limit", "3")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT"], "3")

    def test_missing_active_validation_stays_at_live_hook_and_emits_gated_env(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "live-hook")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET"], "false")
        blocker_codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("missing-process-event-active-validation", blocker_codes)
        self.assertIn("missing-call-function-active-validation", blocker_codes)
        required = plan["nextCanaryContract"]["requiredValidation"]
        self.assertIn(
            "explicitly allowed active ProcessEvent validation call through patched target entry, live hook, and original trampoline",
            required,
        )
        self.assertIn(
            "explicitly allowed active CallFunctionByNameWithArguments validation call through patched target entry, live hook, and original trampoline",
            required,
        )
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["processEventRuntimeEvidence"]["activeValidation"])
        self.assertFalse(contract["callFunctionRuntimeEvidence"]["activeValidation"])
        self.assertEqual(
            contract["processEventRuntimeEvidenceContract"]["ueProcessEventActiveValidation"]["requiredFields"],
            ["status=invoked", "targetEntry=true", "liveCallsDelta>0", "originalCallsDelta>0"],
        )
        self.assertEqual(
            contract["callFunctionRuntimeEvidenceContract"]["ueCallFunctionActiveValidation"]["events"],
            ["ue-call-function-active-validate"],
        )

    def test_process_event_live_hook_without_active_candidate_widens_read_only_discovery(self):
        readiness = report(
            {
                "objectDiscovery": False,
                "targetObjectDiscovery": False,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventHookRuntimeTarget": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionHookProbe": False,
                "ueCallFunctionHookRuntimeTarget": False,
                "ueCallFunctionLiveHook": False,
                "ueCallFunctionLiveHookRuntimeTarget": False,
            },
            ue_groups=ue_anchor_groups(target_world=0, target_dispatch=0),
        )
        payload = {
            "schemaVersion": "dune-ue-vtable-candidates/v1",
            "hookProbeShortlist": [
                {
                    "slot": 64,
                    "topTarget": {
                        "targetName": "ProcessEvent",
                        "imageOffset": "0xfb4b060",
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            targets_path = Path(tmp) / "ue-vtable-candidates.json"
            targets_path.write_text(json.dumps(payload), encoding="utf-8")
            plan = self.run_plan(
                tmp,
                readiness,
                "--hook-targets-json",
                str(targets_path),
                "--max-stage",
                "live-hook",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS"], "32768")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX"], "512")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE", env)
        self.assertNotIn("DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE", env)
        self.assertIn("widen read-only object/reflection discovery", " ".join(plan["notes"]))

    def test_active_validation_hints_emit_gated_windows_env(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
            },
            canary_hints={
                "activeValidationCandidates": [
                    {
                        "objectAddress": "0x140070000",
                        "functionAddress": "0x140082000",
                        "paramsAddress": "0x140090000",
                        "functionPath": "/RuntimeProbe/GWorld.DecodedFunction_0:Function",
                        "callFunctionCommand": "DecodedFunction_0",
                    }
                ]
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "live-hook",
                "--use-active-validation-hints",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x140070000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS"], "0x140082000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS"], "0x140090000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x140070000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND"], "DecodedFunction_0")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET"], "false")
        self.assertFalse(plan["nextCanaryContract"]["processEventRuntimeEvidence"]["activeValidation"])
        self.assertFalse(plan["nextCanaryContract"]["callFunctionRuntimeEvidence"]["activeValidation"])
        self.assertIn(
            "Active ProcessEvent validation inputs were promoted from canary hint function path /RuntimeProbe/GWorld.DecodedFunction_0:Function.",
            plan["notes"],
        )

    def test_active_validation_candidates_json_populates_hints(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "process-event-active-validation-candidates.json"
            candidate_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-process-event-active-validation-candidates/v1",
                        "activeValidationCandidates": [
                            {
                                "objectAddress": "0x140170000",
                                "functionAddress": "0x140182000",
                                "paramsAddress": "0x140190000",
                                "functionPath": "/RuntimeProbe/Actor.WasRecentlyRendered:Function",
                                "callFunctionCommand": "WasRecentlyRendered",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "live-hook",
                "--active-validation-candidates-json",
                str(candidate_path),
                "--use-active-validation-hints",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x140170000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS"], "0x140182000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS"], "0x140190000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND"], "WasRecentlyRendered")
        self.assertIn(
            "Active ProcessEvent validation inputs were promoted from canary hint function path /RuntimeProbe/Actor.WasRecentlyRendered:Function.",
            plan["notes"],
        )

    def test_active_validation_candidates_json_rejects_malformed_inputs(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
            }
        )
        cases = (
            ([], "must be a JSON object"),
            (
                {
                    "schemaVersion": "dune-process-event-active-validation-candidates/v1",
                    "activeValidationCandidates": {},
                },
                "activeValidationCandidates must be a JSON array",
            ),
            (
                {
                    "schemaVersion": "dune-process-event-active-validation-candidates/v1",
                    "activeValidationCandidates": ["not-object"],
                },
                "activeValidationCandidates[0] must be a JSON object",
            ),
            (
                {
                    "schemaVersion": "dune-process-event-active-validation-candidates/v1",
                    "activeValidationCandidates": [
                        {
                            "objectAddress": "0x140170000",
                            "functionAddress": "0x140182000\n0x140182100",
                        }
                    ],
                },
                "activeValidationCandidates[0].functionAddress must be a non-empty single-line scalar",
            ),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    candidate_path = root / "process-event-active-validation-candidates.json"
                    candidate_path.write_text(json.dumps(payload), encoding="utf-8")
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "windows",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "live-hook",
                            "--active-validation-candidates-json",
                            str(candidate_path),
                            "--use-active-validation-hints",
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_readiness_json_rejects_non_readiness_artifacts(self):
        cases = (
            (
                {"schemaVersion": "dune-ue4ss-evidence-inventory/v1", "readyForPackageLoading": False},
                "expected 'dune-ue4ss-port-readiness/v1'",
            ),
            ([], "must be a JSON object"),
            ({"schemaVersion": "dune-ue4ss-port-readiness/v1"}, "is missing readiness `ready` object"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    readiness_path = root / "not-readiness.json"
                    readiness_path.write_text(json.dumps(payload), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "windows",
                            "--readiness-json",
                            str(readiness_path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_readiness_json_rejects_malformed_live_contract_and_anchor_coverage(self):
        cases = []
        readiness = with_anchor_coverage(report())
        readiness["liveTargetImageCanaryContract"] = {
            "ready": "false",
            "groups": {},
            "missingKeys": [],
        }
        cases.append((readiness, "liveTargetImageCanaryContract.ready must be a boolean"))

        readiness = with_anchor_coverage(report())
        readiness["anchorCoverage"]["readyForTargetObjectDiscovery"] = "false"
        cases.append((readiness, "anchorCoverage.readyForTargetObjectDiscovery must be a boolean"))

        readiness = with_anchor_coverage(report())
        readiness["anchorCoverage"]["combinedAnchorCount"] = "4"
        cases.append((readiness, "anchorCoverage.combinedAnchorCount must be a non-negative integer"))

        for payload, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(payload), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "windows",
                            "--readiness-json",
                            str(readiness_path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_readiness_json_accepts_valid_readiness_schema(self):
        readiness = report({"objectDiscovery": True})
        readiness["schemaVersion"] = "dune-ue4ss-port-readiness/v1"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "windows",
                    "--readiness-json",
                    str(readiness_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["schemaVersion"], "dune-ue4ss-canary-env-plan/v1")

    def test_active_validation_inputs_emit_allowed_windows_env(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "live-hook",
                "--allow-active-native-call",
                "--active-validation-through-target",
                "--suppress-process-event-original",
                "--active-validation-object-address",
                "0x140070000",
                "--process-event-active-function-address",
                "0x140082000",
                "--process-event-active-params-address",
                "0x140090000",
                "--call-function-active-command",
                "ToggleProbe",
                "--call-function-active-output-address",
                "0x1400a0000",
                "--call-function-active-executor-address",
                "0x1400b0000",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x140070000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS"], "0x140082000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS"], "0x140090000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x140070000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND"], "ToggleProbe")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OUTPUT_ADDRESS"], "0x1400a0000")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_EXECUTOR_ADDRESS"], "0x1400b0000")

    def test_active_validation_prefixes_are_equal_for_server_linux_and_windows(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
            }
        )
        expected = {
            "server": "DUNE_PROBE_LOADER",
            "linux-client": "DUNE_CLIENT_PROBE",
            "windows": "DUNE_WIN_CLIENT_PROBE",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for platform, prefix in expected.items():
                plan = self.run_plan(
                    tmp,
                    readiness,
                    "--max-stage",
                    "live-hook",
                    "--allow-active-native-call",
                    "--active-validation-through-target",
                    "--active-validation-object-address",
                    "0x7000",
                    "--process-event-active-function-address",
                    "0x8200",
                    "--call-function-active-command-address",
                    "0x9300",
                    "--call-function-active-force-call",
                    platform=platform,
                )
                env = {item["name"]: item["value"] for item in plan["env"]}
                self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE"], "true")
                self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "true")
                self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
                self.assertEqual(env[f"{prefix}_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL"], "false")
                self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE"], "true")
                self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
                self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND_ADDRESS"], "0x9300")
                self.assertEqual(env[f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_FORCE_CALL"], "true")

    def test_missing_package_native_invocation_emits_closed_guard_env(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadAssetPackageNativeExecutor": True,
                "luaLoadAssetPackageNativeInvocation": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_ABI"], "false")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT"], "false")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT", env)
        self.assertIn("missing-load-asset-package-native-invocation", {item["code"] for item in plan["blockers"]})
        self.assertIn(
            "guarded InvokeLoadAssetPackageNative(path,{Invoke=true}) row with nativeInvoked=true, nativeCallable=true, targetImage=true, and nativeReturnValidated=true",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_missing_load_class_package_stages_emit_blockers(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": True,
                "luaLoadClassPackageCallFrameVerification": False,
                "luaLoadClassPackageNativeExecutor": False,
                "luaLoadClassPackageNativeInvocation": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        blocker_codes = {item["code"] for item in plan["blockers"]}
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertIn("missing-load-class-package-call-frame-verification", blocker_codes)
        self.assertIn("missing-load-class-package-native-executor", blocker_codes)
        self.assertIn("missing-load-class-package-native-invocation", blocker_codes)
        self.assertIn(
            "guarded InvokeLoadClassPackageNative(path,{Invoke=true}) row with nativeInvoked=true, nativeCallable=true, targetImage=true, classRootReady=true, and nativeCallPlanAccepted=true",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_package_promotion_manifest_emits_reviewed_load_class_env(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": False,
                "luaLoadClassPackageCallFrameVerification": False,
                "luaLoadClassPackageNativeExecutor": False,
                "luaLoadClassPackageNativeInvocation": False,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "imageRangeSource": "pid",
            "imageBase": "0x100000",
            "imageStart": "0x200000",
            "imageEnd": "0x7000000",
            "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
            "imagePerms": "r-xp",
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "abiReview": {
                "provided": True,
                "ready": True,
                "arguments": [
                    {
                        "role": "Name",
                        "memory": {
                            "hints": {
                                "candidateTcharLayouts": [
                                    {"unitBytes": 2, "sample": "/Game"},
                                ],
                            },
                        },
                    }
                ],
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE": "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL": "false",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch", "--package-promotion-json", str(path), platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"], "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0")
        self.assertEqual(env["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE", env)
        self.assertTrue(any("Applied 3 package promotion env values" in note for note in plan["notes"]))
        self.assertTrue(any("ABI review ready=true" in note for note in plan["notes"]))
        self.assertTrue(any("Name candidateTcharLayouts=2:/Game" in note for note in plan["notes"]))
        self.assertTrue(any("LOAD_CLASS_PACKAGE_ABI_EVIDENCE=runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0" in note for note in plan["notes"]))
        self.assertTrue(any("target identity: tracePid=4242" in note for note in plan["notes"]))
        self.assertTrue(any("imagePath=/srv/dune/DuneSandboxServer-Linux-Shipping" in note for note in plan["notes"]))

    def test_package_promotion_manifest_env_caller_must_match_manifest_identity(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6000 rip=0x5ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("env evidence caller does not match callerImageOffset", result.stderr)

    def test_package_promotion_manifest_env_family_must_match_manifest_identity(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("env evidence family does not match signatureFamily", result.stderr)

    def test_package_promotion_manifest_env_seed_must_match_manifest_identity(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:seed=LoadPackage caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("env evidence seed does not match signatureFamily", result.stderr)

    def test_package_promotion_manifest_env_rip_must_match_manifest_identity(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x5ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("env evidence rip does not match ripImageOffset", result.stderr)

    def test_package_promotion_manifest_env_must_be_object(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": ["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI=true"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion env must be an object", result.stderr)

    def test_package_promotion_manifest_env_values_must_be_scalar(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": {
                    "source": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0"
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion env contains a non-scalar value", result.stderr)

    def test_ready_package_promotion_manifest_with_blockers_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": ["manual blocker left behind"],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest still has blockers", result.stderr)

    def test_ready_package_promotion_manifest_malformed_list_fields_are_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "missingReviewFlags": "--reviewed-abi",
            "missingNativeInvokeFlags": ["--final-native-call", 42],
            "abiReview": {"ready": True, "blockers": [{"message": "bad role"}]},
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("abiReview.blockers[0] must be a string", result.stderr)

    def test_ready_package_promotion_manifest_malformed_abi_argument_memory_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "missingReviewFlags": [],
            "missingNativeInvokeFlags": [],
            "abiReview": {
                "ready": True,
                "blockers": [],
                "arguments": [
                    {"memory": {"lineCount": True, "hints": []}},
                    {"memory": []},
                ],
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "abiReview.arguments[0].memory.lineCount must be a non-negative integer",
            result.stderr,
        )

    def test_blocked_package_promotion_manifest_malformed_shapes_are_reported_in_notes(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "LoadPackage",
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "blockers": "reviewed TCHAR layout evidence is required",
            "missingReviewFlags": ["--reviewed-abi", 42],
            "missingNativeInvokeFlags": "--allow-native-invoke",
            "abiReview": ["not-object"],
            "env": {"DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "false"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch", "--package-promotion-json", str(path), platform="server")

        notes = " ".join(plan["notes"])
        self.assertIn("blockers must be a JSON array", notes)
        self.assertIn("abiReview must be a JSON object", notes)
        self.assertIn("missingReviewFlags[1] must be a string", notes)
        self.assertIn("missingNativeInvokeFlags must be a JSON array", notes)

    def test_ready_package_promotion_manifest_missing_rip_offset_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest is missing ripImageOffset", result.stderr)

    def test_ready_package_promotion_manifest_missing_trace_identity_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        for hit_index in ("auto", True, -1):
            with self.subTest(hit_index=hit_index):
                manifest = {
                    "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                    "signatureFamily": "StaticLoadClass",
                    "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                    "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                    "hitIndex": hit_index,
                    "selectedHitSeed": "StaticLoadClass",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                    },
                }
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    path = root / "package-promotion.json"
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "server",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "lua-dispatch",
                            "--package-promotion-json",
                            str(path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ready package promotion manifest is missing concrete hitIndex", result.stderr)

    def test_ready_package_promotion_manifest_missing_source_log_file_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": False,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest sourceLog does not exist", result.stderr)

    def test_ready_package_promotion_manifest_missing_source_log_exists_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest is missing sourceLogExists", result.stderr)

    def test_ready_package_promotion_manifest_missing_trace_pid_match_provenance_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest is missing runtime trace PID match provenance", result.stderr)

    def test_ready_package_promotion_manifest_missing_trace_pid_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
            "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
            "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
            "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest is missing concrete tracePid", result.stderr)

    def test_ready_package_promotion_manifest_missing_acceptance_schema_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "missingReviewFlags": [],
            "missingNativeInvokeFlags": ["--allow-native-invoke", "--final-native-call"],
            "abiReview": {"ready": True, "blockers": []},
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest is missing current package promotion acceptance schema", result.stderr)

    def test_ready_package_promotion_manifest_missing_trace_plan_provenance_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "missingReviewFlags": [],
            "missingNativeInvokeFlags": ["--allow-native-invoke", "--final-native-call"],
            "abiReview": {"ready": True, "blockers": []},
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready package promotion manifest is missing sourceTracePlan provenance", result.stderr)

    def test_ready_package_promotion_manifest_rejects_multiline_identity_fields(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log\nstale",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping\nold",
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion manifest sourceEvidence must be a non-empty single-line value", result.stderr)

    def test_ready_package_promotion_manifest_embedded_hit_identity_must_match(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "hit": {
                "seed": "LoadPackage",
                "callerImageOffset": "0x6000",
                "ripImageOffset": "0x5ff0",
                "traceAddressMatchesBase": False,
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", result.stderr)

    def test_ready_package_promotion_manifest_embedded_hit_requires_memory_evidence(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "hit": {
                "seed": "StaticLoadClass",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceAddressMatchesBase": True,
                "missingRequiredMemoryRegisters": ["rdx"],
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("embedded trace hit is missing required memory registers: rdx", result.stderr)

    def test_ready_package_promotion_manifest_rejects_stale_session_flags(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                readiness = report(
                    {
                        "objectDiscovery": True,
                        "reflection": True,
                        "hookDispatch": True,
                        "ueProcessEventHookProbe": True,
                        "ueCallFunctionHookProbe": True,
                        "ueProcessEventLiveHook": True,
                        "ueProcessEventDispatch": True,
                        "luaDispatch": True,
                    }
                )
                manifest = {
                    "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                    "signatureFamily": "StaticLoadClass",
                    "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                    "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                    "tracePidMatchesRequested": stale_value,
                    "hitIndex": 0,
                    "selectedHitSeed": "StaticLoadClass",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                    "hit": {
                        "seed": "StaticLoadClass",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                        "traceLogHasArmed": stale_value,
                        "tracePidMatchesRequested": stale_value,
                    },
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
                    },
                }
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    path = root / "package-promotion.json"
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "server",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "lua-dispatch",
                            "--package-promotion-json",
                            str(path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("trace log armed PID does not match requested runtime PID", result.stderr)

    def test_ready_package_promotion_manifest_rejects_embedded_stale_session_flags(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                readiness = report(
                    {
                        "objectDiscovery": True,
                        "reflection": True,
                        "hookDispatch": True,
                        "ueProcessEventHookProbe": True,
                        "ueCallFunctionHookProbe": True,
                        "ueProcessEventLiveHook": True,
                        "ueProcessEventDispatch": True,
                        "luaDispatch": True,
                    }
                )
                manifest = {
                    "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                    "signatureFamily": "StaticLoadClass",
                    "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                    "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "StaticLoadClass",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                    "hit": {
                        "seed": "StaticLoadClass",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                        "traceLogHasArmed": stale_value,
                        "tracePidMatchesRequested": stale_value,
                    },
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
                    },
                }
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    path = root / "package-promotion.json"
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "server",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "lua-dispatch",
                            "--package-promotion-json",
                            str(path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("embedded trace hit missing trace armed record; cannot prove runtime trace session", result.stderr)

    def test_ready_package_promotion_manifest_rejects_missing_embedded_address_base_proof(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
            "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
            "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
            "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "hit": {
                "seed": "StaticLoadClass",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceLogHasArmed": True,
                "tracePidMatchesRequested": True,
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", result.stderr)

    def test_ready_package_promotion_manifest_rejects_malformed_missing_required_memory(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "hit": {
                "seed": "StaticLoadClass",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceAddressMatchesBase": True,
                "missingRequiredMemoryRegisters": "rdx",
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("embedded trace hit missingRequiredMemoryRegisters must be a JSON array", result.stderr)

    def test_ready_package_promotion_manifest_rejects_malformed_register_memory(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "hit": {
                "seed": "StaticLoadClass",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceAddressMatchesBase": True,
                "registerMemory": {"rdx": ["0x3:\t0x2f", 42]},
            },
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("embedded trace hit registerMemory.rdx[1] must be a string", result.stderr)

    def test_ready_package_promotion_manifest_seed_must_match_family_without_embedded_hit(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "LoadPackage",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("selectedHitSeed does not match signatureFamily", result.stderr)

    def test_ready_native_package_promotion_manifest_requires_non_invoking_readiness(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "LoadPackage",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "LoadPackage",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": True,
            "nativeInvokeEnabled": True,
            "finalNativeCallConfirmed": True,
            "blockers": [],
            "missingReviewFlags": [],
            "missingNativeInvokeFlags": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready native package promotion manifest is missing non-invoking canary readiness", result.stderr)

    def test_package_promotion_manifest_family_must_match_env_keys(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("StaticLoadClass promotion env includes LoadAsset package keys", result.stderr)

    def test_package_promotion_manifest_rejects_unsupported_signature_family(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "LoadAsset",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "LoadAsset",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported package promotion signatureFamily: LoadAsset", result.stderr)

    def test_asset_package_promotion_manifest_rejects_load_class_env_keys(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "LoadPackage",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "LoadPackage",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "package-promotion.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LoadPackage promotion env includes LoadClass package keys", result.stderr)

    def test_blocked_package_promotion_manifest_does_not_emit_env(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": False,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "blockers": ["reviewed ABI evidence is required"],
            "missingReviewFlags": ["--reviewed-abi", "--reviewed-class-root"],
            "missingNativeInvokeFlags": ["--allow-native-invoke", "--final-native-call"],
            "nextStep": "complete manual review and rerun export with missing review flags: --reviewed-abi, --reviewed-class-root",
            "abiReview": {
                "provided": True,
                "ready": False,
                "blockers": ["required argument roles are missing or null: rdx:Name"],
                "arguments": [
                    {
                        "role": "Name",
                        "memory": {
                            "hints": {
                                "candidateTcharLayouts": [
                                    {"unitBytes": 1, "sample": "/Script"},
                                ],
                            },
                        },
                    }
                ],
            },
            "env": {
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "false",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package-promotion-blocked.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch", "--package-promotion-json", str(path), platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI", env)
        self.assertTrue(any("not ready; not emitting package promotion env" in note for note in plan["notes"]))
        self.assertTrue(any("ABI review: required argument roles are missing or null: rdx:Name" in note for note in plan["notes"]))
        self.assertTrue(any("missing review flags: --reviewed-abi, --reviewed-class-root" in note for note in plan["notes"]))
        self.assertTrue(any("missing native invoke flags: --allow-native-invoke, --final-native-call" in note for note in plan["notes"]))
        self.assertTrue(any("next step: complete manual review" in note for note in plan["notes"]))
        self.assertTrue(any("ABI review ready=false" in note for note in plan["notes"]))
        self.assertTrue(any("Name candidateTcharLayouts=1:/Script" in note for note in plan["notes"]))

    def test_package_promotion_dir_loads_per_family_manifests(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": False,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x6000",
            "ripImageOffset": "0x5ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6000 rip=0x5ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        blocked_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "LoadPackage",
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "blockers": ["reviewed TCHAR layout evidence is required for LoadAsset package promotion"],
            "env": {
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "false",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package-family-reviews"
            ready_dir = root / "StaticLoadClass"
            blocked_dir = root / "LoadPackage"
            ready_dir.mkdir(parents=True)
            blocked_dir.mkdir(parents=True)
            (ready_dir / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "rank": 0,
                        "signatureFamily": "StaticLoadClass",
                    }
                ),
                encoding="utf-8",
            )
            (blocked_dir / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "rank": 1,
                        "signatureFamily": "LoadPackage",
                    }
                ),
                encoding="utf-8",
            )
            (ready_dir / "promotion-env.json").write_text(json.dumps(ready_manifest), encoding="utf-8")
            (blocked_dir / "promotion-env.json").write_text(json.dumps(blocked_manifest), encoding="utf-8")
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch", "--package-promotion-dir", str(root), platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"], "runtime-trace:StaticLoadClass:caller=0x6000 rip=0x5ff0")
        self.assertEqual(env["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", env)
        self.assertTrue(any("Applied 3 package promotion env values" in note for note in plan["notes"]))
        self.assertTrue(any("Package promotion manifest" in note and "LoadPackage" in note and "not ready" in note for note in plan["notes"]))
        applied_index = next(index for index, note in enumerate(plan["notes"]) if "Applied 3 package promotion env values" in note)
        blocked_index = next(index for index, note in enumerate(plan["notes"]) if "LoadPackage" in note and "not ready" in note)
        self.assertLess(applied_index, blocked_index)

    def test_package_promotion_dir_invalid_review_priority_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": False,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "callerImageOffset": "0x6000",
            "ripImageOffset": "0x5ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6000 rip=0x5ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        cases = (
            ("invalid review priority rank", "bad", 0),
            ("invalid review priority rank", True, 0),
            ("invalid review priority rank", -1, 0),
            ("invalid review priority hitIndex", 0, "bad"),
            ("invalid review priority hitIndex", 0, True),
            ("invalid review priority hitIndex", 0, -1),
        )
        for expected_error, rank, hit_index in cases:
            with self.subTest(rank=rank, hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp) / "package-family-reviews"
                    ready_dir = root / "StaticLoadClass"
                    ready_dir.mkdir(parents=True)
                    (ready_dir / "review-priority.json").write_text(
                        json.dumps(
                            {
                                "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                                "rank": rank,
                                "hitIndex": hit_index,
                                "signatureFamily": "StaticLoadClass",
                            }
                        ),
                        encoding="utf-8",
                    )
                    (ready_dir / "promotion-env.json").write_text(json.dumps(ready_manifest), encoding="utf-8")
                    readiness_path = Path(tmp) / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "server",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "lua-dispatch",
                            "--package-promotion-dir",
                            str(root),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)

    def test_package_promotion_summary_json_loads_only_ready_manifests(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": False,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        blocked_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "LoadPackage",
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "blockers": ["reviewed TCHAR layout evidence is required for LoadAsset package promotion"],
            "env": {
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "false",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            blocked_path = root / "LoadPackage-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            blocked_path.write_text(json.dumps(blocked_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                        "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                        "tracePidMatchesRequested": True,
                        "tracePid": 4242,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    },
                    {"path": str(blocked_path), "signatureFamily": "LoadPackage", "readyForNonInvokingCanary": False},
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch", "--package-promotion-summary-json", str(summary_path), platform="server")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"], "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200")
        self.assertEqual(env["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", env)
        self.assertFalse(any("LoadPackage" in note and "not ready" in note for note in plan["notes"]))

    def test_package_promotion_summary_json_errors_block_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadClassPackageAbiState": False,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "selectedHitSeed": "StaticLoadClass",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "errorCount": 1,
                "errors": [
                    {
                        "path": str(root / "LoadPackage" / "review-priority.json"),
                        "error": "invalid review priority hitIndex",
                    }
                ],
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "signatureFamily": "StaticLoadClass",
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                    },
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion summary has validation errors", result.stderr)
        self.assertIn("invalid review priority hitIndex", result.stderr)

    def test_missing_package_promotion_summary_json_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "missing-summary.json"
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No such file or directory", result.stderr)

    def test_invalid_package_promotion_summary_json_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text("{", encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expecting property name enclosed in double quotes", result.stderr)

    def test_non_object_package_promotion_summary_json_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text("[]", encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion summary must be a JSON object", result.stderr)

    def test_non_array_package_promotion_summary_manifests_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "manifests": {},
                        "readyManifestPaths": [],
                    }
                ),
                encoding="utf-8",
            )
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion summary manifests must be a JSON array", result.stderr)

    def test_non_object_package_promotion_summary_manifest_row_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "manifests": [[]],
                        "readyManifestPaths": [],
                    }
                ),
                encoding="utf-8",
            )
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion summary manifest row 0 must be a JSON object", result.stderr)

    def test_non_array_package_promotion_summary_ready_paths_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "manifests": [],
                        "readyManifestPaths": {},
                    }
                ),
                encoding="utf-8",
            )
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion summary readyManifestPaths must be a JSON array", result.stderr)

    def test_non_array_package_promotion_summary_errors_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "errors": {},
                    }
                ),
                encoding="utf-8",
            )
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion summary errors must be a JSON array", result.stderr)

    def test_non_object_package_promotion_manifest_json_blocks_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "package-promotion.json"
            manifest_path.write_text("[]", encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-json",
                    str(manifest_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package promotion manifest must be a JSON object", result.stderr)

    def test_non_object_review_priority_blocks_package_promotion_dir_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x5000",
            "ripImageOffset": "0x4ff0",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x5000 rip=0x4ff0",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family_dir = root / "StaticLoadClass"
            family_dir.mkdir()
            (family_dir / "promotion-env.json").write_text(json.dumps(manifest), encoding="utf-8")
            (family_dir / "review-priority.json").write_text("[]", encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-dir",
                    str(root),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("review priority must be a JSON object", result.stderr)

    def test_package_promotion_summary_json_ready_path_must_have_ready_manifest_row(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready manifest path is not backed by a ready manifest row", result.stderr)

    def test_package_promotion_summary_json_ready_row_must_be_listed_in_ready_paths(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready manifest row is missing from readyManifestPaths", result.stderr)

    def test_package_promotion_summary_json_duplicate_ready_paths_block_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path), str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate readyManifestPaths entry", result.stderr)

    def test_package_promotion_summary_json_duplicate_ready_rows_block_canary_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            ready_row = {
                "path": str(ready_path),
                "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                "hitIndex": 0,
                "selectedHitSeed": "StaticLoadClass",
                "signatureFamily": "StaticLoadClass",
                "callerImageOffset": "0x6100",
                "ripImageOffset": "0x6200",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
            }
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [ready_row, dict(ready_row)],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate ready package promotion summary row", result.stderr)

    def test_package_promotion_summary_json_ready_path_row_must_be_ready(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "signatureFamily": "StaticLoadClass",
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready manifest path is not backed by a ready manifest row", result.stderr)

    def test_package_promotion_summary_json_row_must_match_manifest_identity(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("summary row callerImageOffset does not match promotion manifest", result.stderr)

    def test_package_promotion_summary_json_row_requires_manifest_trace_pid(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                        "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("summary row is missing tracePid for promotion manifest", result.stderr)

    def test_package_promotion_summary_json_row_trace_pid_must_match_manifest(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "tracePid": 4242,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                        "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "tracePid": 9999,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("summary row tracePid does not match promotion manifest", result.stderr)

    def test_package_promotion_summary_json_row_trace_pid_match_must_match_manifest(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        for summary_value, expected in (
            (None, "summary row is missing tracePidMatchesRequested for promotion manifest"),
            (False, "summary row tracePidMatchesRequested does not match promotion manifest"),
        ):
            with self.subTest(summary_value=summary_value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    ready_path = root / "StaticLoadClass-promotion-env.json"
                    ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
                    row = {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                        "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                    if summary_value is not None:
                        row["tracePidMatchesRequested"] = summary_value
                    summary = {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(ready_path)],
                        "manifests": [row],
                    }
                    summary_path = root / "package-promotion-summary.json"
                    summary_path.write_text(json.dumps(summary), encoding="utf-8")
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "server",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "lua-dispatch",
                            "--package-promotion-summary-json",
                            str(summary_path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_package_promotion_summary_json_ready_row_requires_selected_hit_seed(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        for hit_index in ("auto", True, -1):
            with self.subTest(hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    ready_path = root / "StaticLoadClass-promotion-env.json"
                    ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
                    summary = {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(ready_path)],
                        "manifests": [
                            {
                                "path": str(ready_path),
                                "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                                "hitIndex": hit_index,
                                "selectedHitSeed": "StaticLoadClass",
                                "signatureFamily": "StaticLoadClass",
                                "callerImageOffset": "0x6100",
                                "ripImageOffset": "0x6200",
                                "readyForNonInvokingCanary": True,
                                "targetImageReviewed": True,
                                "tcharReviewed": True,
                                "classRootReviewed": True,
                                "abiReviewReady": True,
                                "abiReviewed": True,
                                "readyForNativeInvoke": False,
                            }
                        ],
                    }
                    summary_path = root / "package-promotion-summary.json"
                    summary_path.write_text(json.dumps(summary), encoding="utf-8")
                    readiness_path = root / "readiness.json"
                    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
                    result = subprocess.run(
                        [
                            str(SCRIPT),
                            "--platform",
                            "server",
                            "--readiness-json",
                            str(readiness_path),
                            "--max-stage",
                            "lua-dispatch",
                            "--package-promotion-summary-json",
                            str(summary_path),
                            "--format",
                            "json",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ready summary row is missing concrete hitIndex", result.stderr)

    def test_package_promotion_summary_json_ready_row_rejects_multiline_identity_fields(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log\nstale",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                        "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping\nold",
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready summary row sourceEvidence must be a non-empty single-line value", result.stderr)

    def test_package_promotion_summary_json_ready_row_missing_source_log_file_is_rejected(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_manifest = {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "StaticLoadClass",
                "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                "sourceLogExists": False,
                "hitIndex": 0,
                "selectedHitSeed": "StaticLoadClass",
                "callerImageOffset": "0x6100",
                "ripImageOffset": "0x6200",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "blockers": [],
                "env": {
                    "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                },
            }
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
                        "sourceLogExists": False,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready summary row sourceLog does not exist", result.stderr)

    def test_package_promotion_summary_json_ready_row_seed_must_match_family(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready summary row selectedHitSeed does not match signatureFamily", result.stderr)

    def test_package_promotion_summary_json_priority_must_match_review_priority(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass" / "promotion-env.json"
            ready_path.parent.mkdir(parents=True, exist_ok=True)
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            (ready_path.parent / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "signatureFamily": "StaticLoadClass",
                        "rank": 1,
                        "hitIndex": 0,
                    }
                ),
                encoding="utf-8",
            )
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                        "reviewPriority": 9,
                        "reviewPriorityHitIndex": 1,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("summary row reviewPriority does not match review priority", result.stderr)

    def test_package_promotion_summary_json_invalid_review_priority_blocks_planning(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass" / "promotion-env.json"
            ready_path.parent.mkdir(parents=True, exist_ok=True)
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            (ready_path.parent / "review-priority.json").write_text("{", encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                        "reviewPriority": 1,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid JSON in review priority", result.stderr)

    def test_package_promotion_summary_json_row_must_match_manifest_readiness(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        ready_manifest = {
            "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
            "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
            "hitIndex": 0,
            "selectedHitSeed": "StaticLoadClass",
            "signatureFamily": "StaticLoadClass",
            "callerImageOffset": "0x6100",
            "ripImageOffset": "0x6200",
            "readyForNonInvokingCanary": True,
            "targetImageReviewed": True,
            "tcharReviewed": True,
            "classRootReviewed": True,
            "abiReviewReady": True,
            "abiReviewed": True,
            "readyForNativeInvoke": False,
            "blockers": [],
            "env": {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:StaticLoadClass:caller=0x6100 rip=0x6200",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready_path = root / "StaticLoadClass-promotion-env.json"
            ready_path.write_text(json.dumps(ready_manifest), encoding="utf-8")
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "readyManifestPaths": [str(ready_path)],
                "manifests": [
                    {
                        "path": str(ready_path),
                        "sourceEvidence": "/tmp/current-trace.log",
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "evidence-json-sha256",
            "sourceLogSha256": "trace-log-sha256",
            "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
            "tracePidMatchesRequested": True,
                        "hitIndex": 0,
                        "selectedHitSeed": "StaticLoadClass",
                        "signatureFamily": "StaticLoadClass",
                        "callerImageOffset": "0x6100",
                        "ripImageOffset": "0x6200",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": True,
                        "nativeInvokeEnabled": True,
                        "finalNativeCallConfirmed": True,
                    }
                ],
            }
            summary_path = root / "package-promotion-summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--max-stage",
                    "lua-dispatch",
                    "--package-promotion-summary-json",
                    str(summary_path),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("summary row readyForNativeInvoke does not match promotion manifest", result.stderr)

    def test_package_native_invocation_allowed_env_includes_reviewed_inputs(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadAssetPackageNativeExecutor": True,
                "luaLoadAssetPackageNativeInvocation": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "lua-dispatch",
                "--allow-load-asset-package-native-call",
                "--load-asset-package-native-script",
                "--load-asset-package-path",
                "/Script/DuneProbe.TargetAsset",
                "--load-asset-package-abi-evidence",
                "reviewed-static-load-object-sysv",
                "--load-asset-package-tchar-unit-bytes",
                "4",
                "--load-asset-package-tchar-evidence",
                "reviewed-linux-wchar-layout",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_ASSET_PACKAGE_ABI"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"], "reviewed-static-load-object-sysv")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_CONFIRM_TCHAR_LAYOUT"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_TCHAR_UNIT_BYTES"], "4")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_TCHAR_EVIDENCE"], "reviewed-linux-wchar-layout")
        self.assertIn("InvokeLoadAssetPackageNative(path,{Invoke=true})", env["DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT"])
        self.assertIn("native.Invoked", env["DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT"])
        self.assertIn("native.TargetImage", env["DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT"])
        self.assertIn("native.NativeCallable", env["DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT"])
        self.assertIn("NativeReturnValidated", env["DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT"])
        self.assertIn("/Script/DuneProbe.TargetAsset", env["DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST_SCRIPT"])

    def test_package_native_invocation_prefixes_are_equal_for_server_linux_and_windows(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "luaLoadAssetPackageNativeExecutor": True,
                "luaLoadAssetPackageNativeInvocation": False,
            }
        )
        expected = {
            "server": "DUNE_PROBE_LOADER",
            "linux-client": "DUNE_CLIENT_PROBE",
            "windows": "DUNE_WIN_CLIENT_PROBE",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for platform, prefix in expected.items():
                plan = self.run_plan(
                    tmp,
                    readiness,
                    "--max-stage",
                    "lua-dispatch",
                    "--allow-load-asset-package-native-call",
                    "--load-asset-package-native-script",
                    "--load-asset-package-abi-evidence",
                    "reviewed-abi",
                    "--load-asset-package-tchar-unit-bytes",
                    "4",
                    "--load-asset-package-tchar-evidence",
                    "reviewed-tchar",
                    platform=platform,
                )
                env = {item["name"]: item["value"] for item in plan["env"]}
                self.assertEqual(env[f"{prefix}_ENABLE_LOAD_ASSET_PACKAGE_CRASH_GUARD"], "true")
                self.assertEqual(env[f"{prefix}_ALLOW_LOAD_ASSET_PACKAGE_INVOKE"], "true")
                self.assertEqual(env[f"{prefix}_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL"], "true")
                self.assertEqual(env[f"{prefix}_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"], "reviewed-abi")
                self.assertEqual(env[f"{prefix}_TCHAR_UNIT_BYTES"], "4")
                self.assertIn("InvokeLoadAssetPackageNative", env[f"{prefix}_LUA_SELF_TEST_SCRIPT"])
                self.assertIn("native.TargetImage", env[f"{prefix}_LUA_SELF_TEST_SCRIPT"])
                self.assertIn("native.NativeCallable", env[f"{prefix}_LUA_SELF_TEST_SCRIPT"])

    def test_self_test_only_live_hook_blocks_lua_dispatch_escalation(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": False,
                "ueProcessEventDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH", env)
        self.assertIn("self-test-only-live-hook", {item["code"] for item in plan["blockers"]})
        self.assertFalse(plan["nextCanaryContract"]["processEventRuntimeEvidence"]["liveHookRuntimeTarget"])

    def test_self_test_only_call_function_live_hook_blocks_lua_dispatch_escalation(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": False,
                "ueProcessEventDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH", env)
        self.assertIn("self-test-only-call-function-live-hook", {item["code"] for item in plan["blockers"]})
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["callFunctionRuntimeEvidence"]["liveHookRuntimeTarget"])
        self.assertIn(
            "non-self-test persistent CallFunctionByNameWithArguments hook target",
            contract["requiredValidation"],
        )

    def test_missing_call_function_live_lua_dispatch_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "ueCallFunctionLiveLuaDispatch": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("missing-call-function-live-lua-dispatch", {item["code"] for item in plan["blockers"]})
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["callFunctionRuntimeEvidence"]["liveLuaDispatch"])
        self.assertIn("live CallFunctionByNameWithArguments Lua dispatch", contract["requiredValidation"])

    def test_missing_active_validation_and_call_function_lua_dispatch_escalates_together(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueCallFunctionHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventLiveHookRuntimeTarget": True,
                "ueCallFunctionLiveHook": True,
                "ueCallFunctionLiveHookRuntimeTarget": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventActiveValidation": False,
                "ueCallFunctionActiveValidation": False,
                "ueCallFunctionLiveLuaDispatch": False,
            },
            canary_hints={
                "activeValidationCandidates": [
                    {
                        "objectAddress": "0x140070000",
                        "functionAddress": "0x140082000",
                        "paramsAddress": "0x140090000",
                        "functionPath": "/RuntimeProbe/GWorld.DecodedFunction_0:Function",
                        "callFunctionCommand": "DecodedFunction_0",
                    }
                ]
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "lua-dispatch",
                "--use-active-validation-hints",
                "--allow-active-native-call",
                "--active-validation-through-target",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED"], "true")
        blocker_codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("missing-process-event-active-validation", blocker_codes)
        self.assertIn("missing-call-function-active-validation", blocker_codes)
        self.assertIn("missing-call-function-live-lua-dispatch", blocker_codes)

    def test_missing_process_event_container_storage_layout_methods_block_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "ueProcessEventContainerStorageLayoutMethods": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn(
            "missing-process-event-container-storage-layout-methods",
            {item["code"] for item in plan["blockers"]},
        )
        self.assertIn(
            "ProcessEvent Lua container storage-layout method evidence",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_missing_lua_native_non_self_test_invocations_block_dispatch_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaProcessEventNativeInvokeNonSelfTestGate": True,
                "luaProcessEventNativeInvokeNonSelfTestInvoked": False,
                "luaCallFunctionNativeInvokeNonSelfTestGate": True,
                "luaCallFunctionNativeInvokeNonSelfTestInvoked": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("missing-process-event-native-non-self-test-invocation", codes)
        self.assertIn("missing-call-function-native-non-self-test-invocation", codes)

    def test_missing_process_event_live_param_surfaces_are_required_for_lua_dispatch(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
                "ueProcessEventLiveRawParamValues": False,
                "ueProcessEventLiveContainerParamValues": False,
                "ueProcessEventLuaParamAccessors": False,
                "ueProcessEventLuaScalarParamAccessors": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        required = plan["nextCanaryContract"]["requiredValidation"]
        self.assertIn("live ProcessEvent raw param byte samples", required)
        self.assertIn("live ProcessEvent typed container param headers", required)
        self.assertIn("ProcessEvent Lua descriptor-backed param accessors in self-test and live hook", required)
        self.assertIn("ProcessEvent scalar param get/set accessor coverage", required)

    def test_self_test_only_live_context_blocks_lua_dispatch_escalation(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventLiveContext": True,
                "ueProcessEventLiveRegistryContext": True,
                "ueProcessEventLiveFunctionPath": False,
                "ueProcessEventLiveRuntimeContext": False,
                "ueProcessEventLiveRuntimeRegistryContext": False,
                "ueProcessEventLiveParamValues": False,
                "ueProcessEventLiveRawParamValues": False,
                "ueProcessEventLiveContainerParamValues": False,
                "ueProcessEventLiveContainerDataSamples": False,
                "ueProcessEventLuaContextHandles": False,
                "ueProcessEventLuaParamAccessors": False,
                "ueProcessEventLiveClassAwareParamValues": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "live-hook")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH", env)
        codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("self-test-only-live-context", codes)
        self.assertIn("self-test-only-live-registry-context", codes)
        contract = plan["nextCanaryContract"]
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveFunctionPath"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveRuntimeContext"])
        self.assertTrue(contract["processEventRuntimeEvidence"]["liveRegistryContext"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveRuntimeRegistryContext"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveParamValues"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveRawParamValues"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveContainerParamValues"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveContainerDataSamples"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["luaContextHandles"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["luaParamAccessors"])
        self.assertFalse(contract["processEventRuntimeEvidence"]["liveClassAwareParamValues"])
        self.assertIn("non-self-test live ProcessEvent runtime context", contract["requiredValidation"])
        self.assertIn("decoded live ProcessEvent function path evidence", contract["requiredValidation"])
        self.assertIn("live ProcessEvent descriptor-backed param values", contract["requiredValidation"])
        self.assertIn("live ProcessEvent Lua UObject/UFunction/params context handles", contract["requiredValidation"])

    def test_missing_runtime_gate_fields_are_not_treated_as_live_evidence(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
            }
        )
        for key in (
            "ueProcessEventHookRuntimeTarget",
            "ueCallFunctionHookRuntimeTarget",
            "ueProcessEventLiveHookRuntimeTarget",
            "ueCallFunctionLiveHookRuntimeTarget",
            "ueProcessEventLiveRuntimeContext",
            "ueProcessEventLiveRuntimeRegistryContext",
        ):
            readiness["ready"].pop(key, None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "live-hook")

        self.assertEqual(plan["selectedStage"], "hook-probe")
        self.assertIn("self-test-only-hook-probe", {item["code"] for item in plan["blockers"]})
        self.assertFalse(plan["nextCanaryContract"]["processEventRuntimeEvidence"]["hookRuntimeTarget"])
        self.assertFalse(plan["nextCanaryContract"]["callFunctionRuntimeEvidence"]["hookRuntimeTarget"])

    def test_missing_function_iteration_runtime_field_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        readiness["ready"].pop("luaFunctionIterationRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("self-test-only-function-iteration", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["registryRuntimeEvidence"]["luaFunctionIterationRuntime"])
        self.assertIn("non-self-test ForEachFunction owner iteration evidence", contract["requiredValidation"])

    def test_missing_reflection_live_descriptor_runtime_field_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        readiness["ready"].pop("luaReflectionLiveDescriptorValuesRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("self-test-only-reflection-live-descriptor", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertIn("non-self-test live reflection descriptor GetValue/SetValue evidence", contract["requiredValidation"])

    def test_missing_native_reflection_descriptor_runtime_field_blocks_reflection_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
            }
        )
        readiness["ready"].pop("ueReflectionPropertyDescriptorsRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        contract = plan["nextCanaryContract"]
        self.assertIn("self-test-only-native-reflection-descriptors", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["ueReflectionPropertyDescriptorsRuntime"])
        self.assertIn("non-self-test native FProperty descriptor probe evidence", contract["requiredValidation"])

    def test_missing_native_reflection_value_runtime_field_blocks_reflection_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
            }
        )
        readiness["ready"].pop("ueReflectionPropertyValuesRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        contract = plan["nextCanaryContract"]
        self.assertIn("self-test-only-native-reflection-values", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["ueReflectionPropertyValuesRuntime"])
        self.assertIn("non-self-test native reflected property value probe evidence", contract["requiredValidation"])

    def test_missing_reflection_for_each_property_runtime_field_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        readiness["ready"].pop("luaReflectionForEachPropertyRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("self-test-only-reflection-for-each-property", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["luaReflectionForEachPropertyRuntime"])
        self.assertIn("non-self-test Reflection():ForEachProperty descriptor enumeration evidence", contract["requiredValidation"])

    def test_missing_reflection_live_descriptor_typed_class_runtime_field_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        readiness["ready"].pop("luaReflectionLiveDescriptorTypedClassRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("self-test-only-reflection-live-descriptor-typed-class", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["luaReflectionLiveDescriptorTypedClassRuntime"])
        self.assertIn("non-self-test live reflection descriptor decoded FProperty class evidence", contract["requiredValidation"])

    def test_missing_reflection_live_descriptor_typed_values_runtime_field_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        readiness["ready"].pop("luaReflectionLiveDescriptorTypedValuesRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("self-test-only-reflection-live-descriptor-typed-values", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["luaReflectionLiveDescriptorTypedValuesRuntime"])
        self.assertIn("non-self-test live reflection descriptor typed GetValue evidence", contract["requiredValidation"])

    def test_missing_reflection_live_descriptor_typed_set_values_runtime_field_blocks_complete_claim(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "luaDispatch": True,
            }
        )
        readiness["ready"].pop("luaReflectionLiveDescriptorTypedSetValuesRuntime", None)
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        contract = plan["nextCanaryContract"]
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertIn("self-test-only-reflection-live-descriptor-typed-set-values", {item["code"] for item in plan["blockers"]})
        self.assertFalse(contract["reflectionRuntimeEvidence"]["luaReflectionLiveDescriptorTypedSetValuesRuntime"])
        self.assertIn("non-self-test live reflection descriptor typed SetValue evidence", contract["requiredValidation"])

    def test_lua_dispatch_waits_for_live_hook_evidence(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(plan["selectedStage"], "lua-dispatch")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST"], "true")

    def test_lua_dispatch_generates_alias_canary_script_from_function_hint(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventLuaHookAliasRouting": False,
            },
            canary_hints={
                "ueFunctionPaths": ["/RuntimeProbe/GWorld.DecodedFunction_0:Function"],
                "ue4ssFunctionPaths": ["/Script/GWorld.DecodedFunction_0:Function"],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        script = env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT"]
        self.assertIn("RegisterHook('/Script/GWorld.NotTarget:Function'", script)
        self.assertIn("RegisterHook('/Script/GWorld.DecodedFunction_0:Function'", script)
        self.assertIn("return 11", script)
        self.assertIn("return 31", script)

    def test_lua_dispatch_accepts_explicit_alias_hook_path(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventLuaHookAliasRouting": False,
            },
            canary_hints={
                "ueFunctionPaths": ["/RuntimeProbe/GWorld.DecodedFunction_0:Function"],
                "ue4ssFunctionPaths": ["/Script/GWorld.DecodedFunction_0:Function"],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "lua-dispatch",
                "--live-lua-alias-hook-path",
                "/Script/DuneAliasProbe.CustomLiveFunction:Function",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        script = env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT"]
        self.assertIn("RegisterHook('/Script/DuneAliasProbe.NotTarget:Function'", script)
        self.assertIn("RegisterHook('/Script/DuneAliasProbe.CustomLiveFunction:Function'", script)

    def test_lua_dispatch_accepts_explicit_alias_function_path_and_package(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventLuaHookAliasRouting": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(
                tmp,
                readiness,
                "--max-stage",
                "lua-dispatch",
                "--live-lua-alias-function-path",
                "/RuntimeProbe/World.CustomLiveFunction:Function",
                "--live-lua-alias-script-package",
                "DuneAliasProbe",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertIn(
            "RegisterHook('/Script/DuneAliasProbe.CustomLiveFunction:Function'",
            env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT"],
        )

    def test_lua_dispatch_without_alias_hint_adds_note_instead_of_script(self):
        readiness = report(
            {
                "objectDiscovery": True,
                "reflection": True,
                "hookDispatch": True,
                "ueProcessEventHookProbe": True,
                "ueProcessEventLiveHook": True,
                "ueProcessEventDispatch": True,
                "ueProcessEventLuaHookAliasRouting": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness, "--max-stage", "lua-dispatch")

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT", env)
        self.assertIn("no decoded UFunction path hint", " ".join(plan["notes"]))

    def test_builds_anchor_env_from_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "anchors.log"
            log.write_text(ANCHOR_LOG, encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "windows",
                    "--client-log",
                    str(log),
                    "--loader",
                    "win-client",
                    "--format",
                    "env",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_ANCHORS='FNamePool=0x140010000", result.stdout)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=true", result.stdout)
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=true", result.stdout)

    def test_linux_client_default_loader_filter_accepts_client_log_label(self):
        linux_log = ANCHOR_LOG.replace("loader=win-client", "loader=client").replace("rva=", "imageOffset=")
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "linux-client.log"
            log.write_text(linux_log, encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "linux-client",
                    "--client-log",
                    str(log),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        plan = json.loads(result.stdout)
        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertIn("FNamePool=0x140010000", env["DUNE_CLIENT_PROBE_UE_ANCHORS"])
        self.assertEqual(plan["nextCanaryContract"]["currentAnchorGroupCounts"]["names"], 1)
        self.assertEqual(plan["nextCanaryContract"]["anchorSignatureFileEnvName"], "DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE")

    def test_empty_anchor_export_does_not_emit_empty_anchor_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "empty.log"
            log.write_text(
                "2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "windows",
                    "--client-log",
                    str(log),
                    "--loader",
                    "win-client",
                    "--format",
                    "env",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_ANCHORS=", result.stdout)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=true", result.stdout)

    def test_plan_suppresses_mapped_only_runtime_root_anchor_export(self):
        readiness = report()
        readiness["runtimeDiscovery"] = {
            "ready": False,
            "failureCounts": {"no-root-hits": 1},
            "coverage": {
                "targetWritableImageCount": 13,
                "scannedSlots": 677888,
                "fnameProbes": 677888,
                "objectArrayProbes": 677888,
                "fnameHits": 0,
                "objectArrayHits": 0,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            log = Path(tmp) / "server.log"
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            log.write_text(MAPPED_ONLY_SERVER_ANCHOR_LOG, encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "server",
                    "--readiness-json",
                    str(readiness_path),
                    "--server-log",
                    str(log),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        plan = json.loads(result.stdout)
        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("DUNE_PROBE_LOADER_UE_ANCHORS", env)
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_DELAYED_PROBE_SECONDS"], "90")
        self.assertIn("Suppressed mapped-only UE anchor export entries", " ".join(plan["notes"]))

    def test_anchor_signature_file_is_emitted_for_next_canary(self):
        with tempfile.TemporaryDirectory() as tmp:
            signature_file = Path(tmp) / "anchor signatures.txt"
            signature_file.write_text("ProcessEvent@callrel32=e8 ?? ?? ?? ??\n", encoding="utf-8")
            plan = self.run_plan(
                tmp,
                report(),
                "--anchor-signatures-file",
                str(signature_file),
            )
            env = {item["name"]: item["value"] for item in plan["env"]}

        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE"], str(signature_file))

    def test_root_recovery_candidates_emit_bounded_candidate_globals(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            write_root_recovery_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"],
            "GUObjectArray=0x166eba80;GUObjectArray=0x166ebac0;FNamePool=0x1686df70",
        )
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertTrue(contract["provided"])
        self.assertEqual(contract["candidateCount"], 3)
        self.assertEqual(contract["emittedCount"], 3)
        self.assertEqual(contract["filteredRejectedShapeCount"], 0)
        self.assertEqual(contract["filteredRejectedCandidateCount"], 0)
        self.assertEqual(contract["filteredRejectedShapeOnlyCount"], 0)
        self.assertEqual(contract["filteredRejectedOutcomeCount"], 0)
        self.assertEqual(contract["envName"], "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS")
        self.assertEqual(contract["sourceAnchorPresets"], ["object-discovery"])
        self.assertEqual(contract["anchorCounts"], {"FNamePool": 1, "GUObjectArray": 2})
        self.assertTrue(contract["groupCoverage"]["names"]["ready"])
        self.assertTrue(contract["groupCoverage"]["objects"]["ready"])
        self.assertFalse(contract["groupCoverage"]["world"]["ready"])
        self.assertIn("world", contract["missingGroups"])
        self.assertIn(
            "runtime candidate-global shape report for root-recovery hypotheses",
            plan["nextCanaryContract"]["requiredValidation"],
        )
        self.assertIn(
            "root-recovery candidate groups: world, dispatch, package, reflection",
            plan["nextCanaryContract"]["requiredValidation"],
        )
        self.assertIn("incomplete-root-recovery-object-candidates", {item["code"] for item in plan["blockers"]})
        self.assertIn("hypothesis inputs only", " ".join(plan["notes"]))
        self.assertIn("Root-recovery candidate globals do not cover groups: world", " ".join(plan["notes"]))

    def test_manual_candidate_global_merges_with_root_recovery_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            write_root_recovery_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                "--candidate-global",
                "FNamePool=0x1686df70",
                "--candidate-global",
                "RuntimeGUObjectArray@rwfile=0x28c4c0",
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"],
            "FNamePool=0x1686df70;RuntimeGUObjectArray@rwfile=0x28c4c0;GUObjectArray=0x166eba80;GUObjectArray=0x166ebac0",
        )
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["anchorCounts"], {"FNamePool": 1, "GUObjectArray": 2, "RuntimeGUObjectArray": 1})
        self.assertEqual(contract["emittedCount"], 4)
        self.assertTrue(contract["groupCoverage"]["names"]["ready"])
        self.assertTrue(contract["groupCoverage"]["objects"]["ready"])
        self.assertNotIn("names", contract["missingGroups"])
        self.assertNotIn("objects", contract["missingGroups"])

    def test_writable_candidate_globals_emit_bounded_candidate_globals(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "writable-candidates.json"
            write_writable_candidate_globals(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--candidate-globals-json",
                str(candidates),
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"],
            "GUObjectArray=0x165ff4a8;FNamePool=0x1686df70",
        )
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertTrue(contract["provided"])
        self.assertEqual(contract["candidateCount"], 2)
        self.assertEqual(contract["sourceAnchorPresets"], ["writable-global-candidates"])
        self.assertEqual(contract["anchorCounts"], {"FNamePool": 1, "GUObjectArray": 1})
        self.assertTrue(contract["groupCoverage"]["names"]["ready"])
        self.assertTrue(contract["groupCoverage"]["objects"]["ready"])
        self.assertFalse(contract["groupCoverage"]["world"]["ready"])

    def test_scalar_heavy_root_shape_candidates_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "scalar-root-candidates.json"
            write_scalar_heavy_writable_root_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
            )

        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["shapeQuality"]["qwordCandidateCount"], 0)
        self.assertEqual(contract["shapeQuality"]["scalarHeavyCandidateCount"], 3)
        self.assertEqual(contract["shapeQuality"]["maxScalarRatio"], 1.0)
        codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("unproven-root-recovery-shape-quality", codes)
        self.assertIn("scalar-heavy-root-recovery-candidates", codes)
        self.assertIn(
            "remove scalar-heavy writable-root candidates before live canary",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_address_only_qword_candidates_are_not_shape_quality_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "address-only-candidates.json"
            write_address_only_writable_global_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--candidate-globals-json",
                str(candidates),
            )

        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["shapeQuality"]["classifiedCount"], 1)
        self.assertEqual(contract["shapeQuality"]["qwordCandidateCount"], 0)
        self.assertEqual(contract["shapeQuality"]["qwordReadWriteCandidateCount"], 0)
        self.assertIn("unproven-root-recovery-shape-quality", {item["code"] for item in plan["blockers"]})

    def test_nested_root_shape_read_write_candidates_satisfy_shape_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "read-write-candidates.json"
            write_read_write_writable_global_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--candidate-globals-json",
                str(candidates),
            )

        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["shapeQuality"]["classifiedCount"], 1)
        self.assertEqual(contract["shapeQuality"]["qwordCandidateCount"], 1)
        self.assertEqual(contract["shapeQuality"]["qwordReadWriteCandidateCount"], 1)
        self.assertNotIn("unproven-root-recovery-shape-quality", {item["code"] for item in plan["blockers"]})

    def test_address_heavy_read_write_candidates_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "address-heavy-read-write-candidates.json"
            write_address_heavy_read_write_writable_global_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--candidate-globals-json",
                str(candidates),
            )

        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["shapeQuality"]["qwordCandidateCount"], 1)
        self.assertEqual(contract["shapeQuality"]["addressHeavyCandidateCount"], 1)
        self.assertEqual(contract["shapeQuality"]["maxAddressRatio"], 0.987)
        self.assertIn("address-heavy-root-recovery-candidates", {item["code"] for item in plan["blockers"]})
        self.assertIn(
            "remove address-heavy writable-root candidates before live canary",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_generic_only_root_recovery_context_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "generic-only-candidates.json"
            write_generic_only_hint_writable_global_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--candidate-globals-json",
                str(candidates),
            )

        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["hintQuality"]["classifiedCount"], 1)
        self.assertEqual(contract["hintQuality"]["genericOnlyCandidateCount"], 1)
        self.assertEqual(contract["hintQuality"]["specificCandidateCount"], 0)
        self.assertIn("generic-only-root-recovery-context", {item["code"] for item in plan["blockers"]})
        self.assertIn(
            "non-generic or exact-anchor root-recovery context before live canary",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_unmatched_source_group_root_candidates_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "unmatched-source-groups.json"
            write_unmatched_source_group_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
            )

        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["sourceGroupQuality"]["classifiedCount"], 2)
        self.assertEqual(contract["sourceGroupQuality"]["matchedCount"], 1)
        self.assertEqual(contract["sourceGroupQuality"]["unmatchedCount"], 1)
        self.assertIn("unmatched-root-recovery-source-groups", {item["code"] for item in plan["blockers"]})
        self.assertIn(
            "source-group-matched root-recovery candidates for requested anchor groups",
            plan["nextCanaryContract"]["requiredValidation"],
        )

    def test_pointer_like_root_recovery_export_satisfies_shape_quality_without_source_group_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "pointer-like-root-candidates.json"
            write_pointer_like_root_recovery_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                platform="server",
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS"], "GEngine=0x16449320")
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["shapeQuality"]["classifiedCount"], 1)
        self.assertEqual(contract["shapeQuality"]["qwordCandidateCount"], 1)
        self.assertEqual(contract["shapeQuality"]["qwordReadWriteCandidateCount"], 1)
        self.assertEqual(contract["sourceGroupQuality"]["classifiedCount"], 0)
        codes = {item["code"] for item in plan["blockers"]}
        self.assertNotIn("unproven-root-recovery-shape-quality", codes)
        self.assertNotIn("unmatched-root-recovery-source-groups", codes)

    def test_root_recovery_candidates_suppress_stale_exported_runtime_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            log = Path(tmp) / "anchors.log"
            write_root_recovery_candidates(candidates)
            log.write_text(ANCHOR_LOG, encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "windows",
                    "--client-log",
                    str(log),
                    "--loader",
                    "win-client",
                    "--root-recovery-candidates-json",
                    str(candidates),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        plan = json.loads(result.stdout)
        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_ANCHORS", env)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS", env)
        self.assertIn("Suppressed explicit UE anchors", " ".join(plan["notes"]))

    def test_root_recovery_candidate_globals_filter_rejected_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            shapes = Path(tmp) / "candidate-shapes.json"
            write_root_recovery_candidates(candidates)
            write_candidate_shapes(shapes)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                "--candidate-shapes-json",
                str(shapes),
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertEqual(
            env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"],
            "GUObjectArray=0x166eba80;GUObjectArray=0x166ebac0",
        )
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["candidateCount"], 3)
        self.assertEqual(contract["emittedCount"], 2)
        self.assertEqual(contract["filteredRejectedShapeCount"], 1)
        self.assertEqual(contract["filteredRejectedCandidateCount"], 1)
        self.assertEqual(contract["filteredRejectedShapeOnlyCount"], 1)
        self.assertEqual(contract["filteredRejectedOutcomeCount"], 0)
        self.assertEqual(contract["shapeSourcePaths"], [str(shapes)])
        self.assertEqual(contract["anchorCounts"], {"GUObjectArray": 2})
        self.assertFalse(contract["groupCoverage"]["names"]["ready"])
        self.assertFalse(contract["groupCoverage"]["world"]["ready"])
        self.assertIn("names", contract["missingGroups"])
        self.assertIn("world", contract["missingGroups"])
        self.assertIn("incomplete-root-recovery-object-candidates", {item["code"] for item in plan["blockers"]})

    def test_root_recovery_candidate_globals_filter_rejected_live_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            outcomes = Path(tmp) / "candidate-outcomes.json"
            write_root_recovery_candidates(candidates)
            write_candidate_outcomes(outcomes)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                "--candidate-outcomes-json",
                str(outcomes),
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertNotIn("GUObjectArray=0x166eba80", env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"])
        self.assertIn("GUObjectArray=0x166ebac0", env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"])
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["candidateCount"], 3)
        self.assertEqual(contract["emittedCount"], 2)
        self.assertEqual(contract["filteredRejectedShapeCount"], 1)
        self.assertEqual(contract["filteredRejectedCandidateCount"], 1)
        self.assertEqual(contract["filteredRejectedShapeOnlyCount"], 0)
        self.assertEqual(contract["filteredRejectedOutcomeCount"], 1)
        self.assertEqual(contract["outcomeSourcePaths"], [str(outcomes)])

    def test_root_recovery_candidate_globals_keep_image_offset_after_rwfile_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            outcomes = Path(tmp) / "candidate-outcomes-rwfile.json"
            write_root_recovery_candidates(candidates)
            write_candidate_outcomes(outcomes, runtime_rw=True)
            plan = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                "--candidate-outcomes-json",
                str(outcomes),
            )

        env = {item["name"]: item["value"] for item in plan["env"]}
        self.assertIn("GUObjectArray=0x166eba80", env["DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS"])
        contract = plan["nextCanaryContract"]["rootRecoveryCandidateInput"]
        self.assertEqual(contract["emittedCount"], 3)
        self.assertEqual(contract["filteredRejectedShapeCount"], 0)
        self.assertEqual(contract["filteredRejectedCandidateCount"], 0)
        self.assertEqual(contract["filteredRejectedShapeOnlyCount"], 0)
        self.assertEqual(contract["filteredRejectedOutcomeCount"], 0)

    def test_root_recovery_candidate_group_gaps_block_later_stage_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            write_root_recovery_candidates(candidates)
            plan = self.run_plan(
                tmp,
                report({"objectDiscovery": True}),
                "--root-recovery-candidates-json",
                str(candidates),
            )

        self.assertEqual(plan["selectedStage"], "reflection")
        codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("incomplete-root-recovery-object-candidates", codes)
        self.assertIn("incomplete-root-recovery-reflection-candidates", codes)
        self.assertNotIn("incomplete-root-recovery-dispatch-candidates", codes)
        self.assertIn("reflection", plan["nextCanaryContract"]["rootRecoveryCandidateInput"]["missingGroups"])

    def test_root_recovery_candidate_global_env_uses_platform_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "root-candidates.json"
            write_root_recovery_candidates(candidates)
            linux = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                platform="linux-client",
            )
            server = self.run_plan(
                tmp,
                report(),
                "--root-recovery-candidates-json",
                str(candidates),
                platform="server",
            )

        linux_env = {item["name"]: item["value"] for item in linux["env"]}
        server_env = {item["name"]: item["value"] for item in server["env"]}
        self.assertEqual(linux_env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(linux_env["DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW"], "true")
        self.assertEqual(server_env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS"], "true")
        self.assertEqual(server_env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW"], "true")
        self.assertIn("DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS", linux_env)
        self.assertIn("DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS", server_env)
        self.assertEqual(
            linux["nextCanaryContract"]["rootRecoveryCandidateInput"]["envName"],
            "DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
        )
        self.assertEqual(
            server["nextCanaryContract"]["rootRecoveryCandidateInput"]["envName"],
            "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS",
        )

    def test_anchor_signature_file_env_output_quotes_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            readiness_path = Path(tmp) / "readiness.json"
            signature_file = Path(tmp) / "anchor signatures.txt"
            readiness_path.write_text(json.dumps(report()), encoding="utf-8")
            signature_file.write_text("ProcessEvent@callrel32=e8 ?? ?? ?? ??\n", encoding="utf-8")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--platform",
                    "windows",
                    "--readiness-json",
                    str(readiness_path),
                    "--anchor-signatures-file",
                    str(signature_file),
                    "--format",
                    "env",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        self.assertIn(f"DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE='{signature_file}'", result.stdout)


if __name__ == "__main__":
    unittest.main()
