#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-ue-root-recovery-candidates.py"

spec = importlib.util.spec_from_file_location("export_ue_root_recovery_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def args(**overrides):
    values = {
        "anchor": ["GUObjectArray"],
        "anchor_preset": "object-discovery",
        "platform": "server",
        "env_name": None,
        "max_total": 4,
        "max_per_anchor": 4,
        "max_per_cluster": 1,
        "min_gap": 0x40,
        "reject_near_gap": 0x40,
        "suppress_rejected_clusters": True,
        "min_pointer_like_refs": 0,
        "max_byte_guard_refs": None,
        "max_constant_store_refs": None,
        "require_source_group_match": False,
    }
    values.update(overrides)
    return type("Args", (), values)()


QUEUE = {
    "schemaVersion": "dune-ue-root-recovery-queue/v1",
    "rows": [
        {
            "function": "0x100",
            "fileOffset": "0x100",
            "sourceName": ".init_array[1]",
            "score": 100,
            "requiredGroupCoverage": ["objects"],
            "groupCounts": {"objects": 1},
            "signature": {"sha256": "abc"},
            "candidateTargets": [
                {
                    "target": "0x1000",
                    "section": ".bss",
                    "refCount": 3,
                    "pointerLikeRefCount": 1,
                    "byteGuardRefCount": 0,
                    "constantStoreRefCount": 0,
                    "firstInstruction": "0x100",
                    "firstText": "mov rax, qword ptr [rip]",
                },
                {
                    "target": "0x1010",
                    "section": ".bss",
                    "refCount": 2,
                    "pointerLikeRefCount": 0,
                    "byteGuardRefCount": 1,
                    "constantStoreRefCount": 0,
                    "firstInstruction": "0x110",
                    "firstText": "movzx eax, byte ptr [rip]",
                },
            ],
        },
        {
            "function": "0x200",
            "fileOffset": "0x200",
            "sourceName": ".init_array[2]",
            "score": 80,
            "requiredGroupCoverage": ["dispatch", "package", "reflection"],
            "groupCounts": {"dispatch": 1, "package": 1, "reflection": 1},
            "candidateTargets": [
                {
                    "target": "0x2000",
                    "section": ".bss",
                    "refCount": 5,
                    "pointerLikeRefCount": 1,
                    "byteGuardRefCount": 0,
                    "constantStoreRefCount": 0,
                    "firstInstruction": "0x200",
                    "firstText": "mov qword ptr [rip], rax",
                }
            ],
        },
    ],
}

CLUSTERS = {
    "schemaVersion": "dune-ue-root-recovery-clusters/v1",
    "clusters": [
        {"minTarget": "0x1000", "maxTarget": "0x10ff", "functionCount": 1, "targetCount": 2},
        {"minTarget": "0x2000", "maxTarget": "0x20ff", "functionCount": 1, "targetCount": 1},
    ],
}


class ExportUeRootRecoveryCandidatesTests(unittest.TestCase):
    def test_exports_diversified_server_candidates(self):
        summary = module.summarize(QUEUE, CLUSTERS, {}, args())

        self.assertEqual(summary["envName"], "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS")
        self.assertIn("GUObjectArray=0x1000", summary["env"])
        self.assertIn("GUObjectArray=0x2000", summary["env"])
        self.assertNotIn("0x1010", summary["env"])
        self.assertEqual(summary["clusterCounts"], {"1": 1, "2": 1})

    def test_rejects_prior_failed_candidate_for_same_anchor(self):
        outcomes = {
            "candidates": [
                {
                    "name": "GUObjectArray",
                    "imageOffset": "0x1000",
                    "verdict": "weak-false-positive",
                    "anchorTargets": [{"imageOffset": "0x1000"}],
                }
            ]
        }

        summary = module.summarize(QUEUE, CLUSTERS, outcomes, args(max_per_cluster=2))

        self.assertNotIn("GUObjectArray=0x1000", summary["env"])
        self.assertIn("GUObjectArray=0x2000", summary["env"])
        self.assertEqual(summary["suppressedRejectedClusters"], [1])

    def test_merges_multiple_candidate_outcome_files(self):
        merged = module.merge_outcomes(
            [
                {
                    "candidates": [
                        {
                            "name": "GUObjectArray",
                            "imageOffset": "0x1000",
                            "verdict": "rejected",
                            "anchorTargets": [{"imageOffset": "0x1000"}],
                        }
                    ]
                },
                {
                    "candidates": [
                        {
                            "name": "GUObjectArray",
                            "imageOffset": "0x2000",
                            "verdict": "weak-false-positive",
                            "anchorTargets": [{"imageOffset": "0x2000"}],
                        }
                    ]
                },
            ]
        )

        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            merged,
            args(max_per_cluster=2, suppress_rejected_clusters=False, reject_near_gap=0),
        )

        self.assertNotIn("GUObjectArray=0x1000", summary["env"])
        self.assertNotIn("GUObjectArray=0x2000", summary["env"])
        self.assertIn("GUObjectArray=0x1010", summary["env"])

    def test_can_keep_rejected_cluster_for_manual_exploration(self):
        outcomes = {
            "candidates": [
                {
                    "name": "GUObjectArray",
                    "imageOffset": "0x1000",
                    "verdict": "weak-false-positive",
                    "anchorTargets": [{"imageOffset": "0x1000"}],
                }
            ]
        }

        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            outcomes,
            args(max_per_cluster=2, suppress_rejected_clusters=False, reject_near_gap=0),
        )

        self.assertNotIn("GUObjectArray=0x1000", summary["env"])
        self.assertIn("GUObjectArray=0x1010", summary["env"])
        self.assertIn("GUObjectArray=0x2000", summary["env"])
        self.assertEqual(summary["suppressedRejectedClusters"], [])

    def test_near_rejected_offsets_are_suppressed_without_cluster_suppression(self):
        outcomes = {
            "candidates": [
                {
                    "name": "GUObjectArray",
                    "imageOffset": "0x1000",
                    "verdict": "rejected",
                    "anchorTargets": [{"imageOffset": "0x1000"}],
                }
            ]
        }

        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            outcomes,
            args(max_per_cluster=2, suppress_rejected_clusters=False, reject_near_gap=0x20),
        )

        self.assertNotIn("GUObjectArray=0x1000", summary["env"])
        self.assertNotIn("GUObjectArray=0x1010", summary["env"])
        self.assertIn("GUObjectArray=0x2000", summary["env"])

    def test_runtime_rwfile_rejection_does_not_suppress_image_offset_candidate(self):
        outcomes = {
            "candidates": [
                {
                    "name": "GUObjectArray",
                    "imageOffset": "0x1000",
                    "runtimeRwFileOffset": "true",
                    "verdict": "rejected",
                }
            ]
        }

        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            outcomes,
            args(max_per_cluster=2, suppress_rejected_clusters=False, reject_near_gap=0),
        )

        self.assertIn("GUObjectArray=0x1000", summary["env"])

    def test_can_require_pointer_like_candidate_refs(self):
        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            {},
            args(max_per_cluster=2, min_pointer_like_refs=1),
        )

        self.assertIn("GUObjectArray=0x1000", summary["env"])
        self.assertNotIn("GUObjectArray=0x1010", summary["env"])
        self.assertIn("GUObjectArray=0x2000", summary["env"])

    def test_can_suppress_guard_and_constant_store_targets(self):
        queue = {
            "schemaVersion": "dune-ue-root-recovery-queue/v1",
            "rows": [
                {
                    "function": "0x100",
                    "fileOffset": "0x100",
                    "sourceName": ".init_array[1]",
                    "score": 100,
                    "candidateTargets": [
                        {
                            "target": "0x1000",
                            "section": ".bss",
                            "refCount": 3,
                            "pointerLikeRefCount": 1,
                            "byteGuardRefCount": 1,
                            "constantStoreRefCount": 0,
                            "firstInstruction": "0x100",
                            "firstText": "movzx eax, byte ptr [rip]",
                        },
                        {
                            "target": "0x2000",
                            "section": ".bss",
                            "refCount": 3,
                            "pointerLikeRefCount": 1,
                            "byteGuardRefCount": 0,
                            "constantStoreRefCount": 1,
                            "firstInstruction": "0x200",
                            "firstText": "mov dword ptr [rip], 0xffffffff",
                        },
                        {
                            "target": "0x3000",
                            "section": ".bss",
                            "refCount": 3,
                            "pointerLikeRefCount": 1,
                            "byteGuardRefCount": 0,
                            "constantStoreRefCount": 0,
                            "firstInstruction": "0x300",
                            "firstText": "mov qword ptr [rip], rax",
                        },
                    ],
                }
            ],
        }
        clusters = {
            "schemaVersion": "dune-ue-root-recovery-clusters/v1",
            "clusters": [{"minTarget": "0x1000", "maxTarget": "0x30ff", "functionCount": 1, "targetCount": 3}],
        }

        summary = module.summarize(
            queue,
            clusters,
            {},
            args(max_per_cluster=3, max_byte_guard_refs=0, max_constant_store_refs=0),
        )

        self.assertNotIn("GUObjectArray=0x1000", summary["env"])
        self.assertNotIn("GUObjectArray=0x2000", summary["env"])
        self.assertIn("GUObjectArray=0x3000", summary["env"])

    def test_uses_platform_env_names_and_multiple_anchors(self):
        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            {},
            args(platform="windows", anchor=["GUObjectArray", "GWorld"], max_total=4, max_per_cluster=1),
        )

        self.assertTrue(summary["env"].startswith("DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS="))
        self.assertEqual(summary["anchorCounts"], {"GUObjectArray": 2, "GWorld": 2})

    def test_default_preset_exports_object_discovery_anchors(self):
        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            {},
            args(anchor=[], max_total=20, max_per_anchor=4, max_per_cluster=1),
        )

        self.assertEqual(summary["anchorPreset"], "object-discovery")
        self.assertEqual(
            summary["requestedAnchors"],
            [
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
            ],
        )
        self.assertIn("FNamePool=0x1000", summary["env"])
        self.assertIn("NamePoolData=0x1000", summary["env"])
        self.assertIn("GName=0x1000", summary["env"])
        self.assertIn("GNames=0x1000", summary["env"])
        self.assertIn("GUObjectArray=0x1000", summary["env"])
        self.assertIn("GObjectArray=0x1000", summary["env"])
        self.assertIn("GObjects=0x1000", summary["env"])
        self.assertIn("FUObjectArray=0x1000", summary["env"])
        self.assertIn("GWorld=0x1000", summary["env"])
        self.assertIn("GEngine=0x1000", summary["env"])
        self.assertEqual(
            summary["anchorCounts"],
            {
                "FNamePool": 2,
                "NamePoolData": 2,
                "GName": 2,
                "GNames": 2,
                "GObjectArray": 2,
                "GObjects": 2,
                "GUObjectArray": 2,
                "FUObjectArray": 2,
                "GWorld": 2,
                "GEngine": 2,
            },
        )
        self.assertEqual(summary["missingGroups"], [])
        self.assertTrue(summary["groupCoverage"]["names"]["ready"])
        self.assertTrue(summary["groupCoverage"]["objects"]["ready"])
        self.assertTrue(summary["groupCoverage"]["world"]["ready"])

    def test_complete_preset_exports_dispatch_package_and_reflection_anchors(self):
        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            {},
            args(anchor=[], anchor_preset="complete", max_total=64, max_per_anchor=4, max_per_cluster=1),
        )

        self.assertEqual(summary["anchorPreset"], "complete")
        for anchor in (
            "ProcessEvent",
            "CallFunctionByNameWithArguments",
            "StaticLoadObject",
            "LoadPackage",
            "UFunction",
            "FProperty",
        ):
            self.assertIn(f"{anchor}=0x1000", summary["env"])
        self.assertEqual(summary["missingGroups"], [])
        self.assertTrue(summary["groupCoverage"]["dispatch"]["ready"])
        self.assertTrue(summary["groupCoverage"]["package"]["ready"])
        self.assertTrue(summary["groupCoverage"]["reflection"]["ready"])

    def test_can_require_source_group_match_for_later_stage_anchors(self):
        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            {},
            args(
                anchor=[],
                anchor_preset="complete",
                max_total=64,
                max_per_anchor=4,
                max_per_cluster=8,
                min_gap=0,
                require_source_group_match=True,
            ),
        )

        self.assertIn("GUObjectArray=0x1000", summary["env"])
        self.assertNotIn("ProcessEvent=0x1000", summary["env"])
        self.assertIn("ProcessEvent=0x2000", summary["env"])
        self.assertIn("StaticLoadObject=0x2000", summary["env"])
        self.assertIn("UFunction=0x2000", summary["env"])
        for row in summary["candidates"]:
            self.assertTrue(row["anchorGroupMatched"])
            self.assertIn(row["anchorGroup"], row["sourceGroupCoverage"])
        self.assertTrue(summary["requireSourceGroupMatch"])

    def test_group_coverage_reports_underbounded_complete_exports(self):
        summary = module.summarize(
            QUEUE,
            CLUSTERS,
            {},
            args(anchor=[], anchor_preset="complete", max_total=1, max_per_anchor=1, max_per_cluster=1),
        )

        self.assertEqual(summary["candidateCount"], 1)
        self.assertNotIn("names", summary["missingGroups"])
        self.assertIn("objects", summary["missingGroups"])
        self.assertIn("world", summary["missingGroups"])
        self.assertIn("dispatch", summary["missingGroups"])
        self.assertIn("package", summary["missingGroups"])
        self.assertIn("reflection", summary["missingGroups"])
        self.assertTrue(summary["groupCoverage"]["names"]["ready"])
        self.assertFalse(summary["groupCoverage"]["names"]["complete"])
        self.assertEqual(summary["groupCoverage"]["names"]["missingAnchors"], ["NamePoolData", "GName", "GNames"])
        self.assertEqual(
            summary["groupCoverage"]["dispatch"]["missingAnchors"],
            ["ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"],
        )


if __name__ == "__main__":
    unittest.main()
