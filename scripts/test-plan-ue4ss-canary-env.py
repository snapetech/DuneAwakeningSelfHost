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
        "ueProcessEventLiveHookRuntimeTarget": True,
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
        "luaLoadAssetPackage": True,
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


def with_anchor_coverage(base, object_ready=True, hook_ready=True, package_ready=True, missing=None):
    base = dict(base)
    ready = dict(base.get("ready", {}))
    ready["anchorCoverageObjectDiscovery"] = object_ready
    ready["anchorCoverageHookPlanning"] = hook_ready
    ready["anchorCoveragePackageLoading"] = package_ready
    base["ready"] = ready
    base["anchorCoverage"] = {
        "provided": True,
        "explicitAnchorCount": 3,
        "signatureAnchorCount": 1,
        "combinedAnchorCount": 4,
        "readyForObjectDiscovery": object_ready,
        "readyForHookPlanning": hook_ready,
        "readyForPackageLoading": package_ready,
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
        self.assertIn("did not find both root shapes", " ".join(plan["notes"]))

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
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "1")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS"], "128")
        self.assertIn("ambiguous root hits", " ".join(plan["notes"]))

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
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "1")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS"], "128")

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
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_CANDIDATES"], "1")
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
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS"], "4096")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK"], "true")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
        self.assertIn("deeper read-only GUObjectArray walk", " ".join(plan["notes"]))
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
        self.assertEqual(plan["selectedStage"], "reflection")
        self.assertEqual(env["DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE"], "true")
        self.assertNotIn("DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE", env)
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
            "target-image StaticLoadObject/LoadObject/LoadPackage/ResolveName package-loading anchor",
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
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL"], "false")
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE"], "true")
        self.assertEqual(hook_env["DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL"], "false")

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
        self.assertIn("missing object-discovery groups", " ".join(plan["notes"]))
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
        self.assertIn("lacks ProcessEvent-level dispatch evidence", " ".join(plan["notes"]))

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
                self.assertEqual(verification["outputFiles"]["postCanarySummary"], "post-canary-summary.md")
                self.assertEqual(command[:4], ["python3", "scripts/ue4ss-port-readiness.py", log_arg, log_path])
                self.assertIn("--loader", command)
                self.assertEqual(command[command.index("--loader") + 1], loader)
                self.assertIn("--signature-validation-json", command)
                self.assertIn("--anchor-coverage-json", command)
                self.assertIn("scripts/ue4ss-port-readiness.py", verification["readinessCommandText"])

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
        readiness = report({"ueCallFunctionLiveLuaDispatch": False})
        with tempfile.TemporaryDirectory() as tmp:
            plan = self.run_plan(tmp, readiness)

        live_target = plan["nextCanaryContract"]["postCanaryVerification"]["liveTargetImageCanaryContract"]
        self.assertFalse(live_target["ready"])
        self.assertTrue(live_target["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertFalse(live_target["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertEqual(
            live_target["groups"]["runtimeCallFunctionDispatch"]["missingKeys"],
            ["ueCallFunctionLiveLuaDispatch"],
        )
        self.assertIn("ueCallFunctionLiveLuaDispatch", live_target["missingKeys"])

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
