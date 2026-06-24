#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-evidence-inventory.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_evidence_inventory", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class Ue4ssEvidenceInventoryTests(unittest.TestCase):
    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_inventory_ranks_target_coverage_above_legacy_empty_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty"
            target = root / "target"
            self.write_json(
                empty / "anchor-coverage.json",
                {
                    "schemaVersion": "dune-ue-anchor-coverage/v1",
                    "groups": {
                        "names": {"present": 0, "total": 1},
                        "objects": {"present": 0, "total": 1},
                        "world": {"present": 0, "total": 1},
                        "dispatch": {"present": 0, "total": 1},
                    },
                },
            )
            self.write_json(
                target / "ue4ss-readiness.json",
                {
                    "ready": {
                        "targetImageProcess": True,
                        "runtimeRootDiscovery": True,
                        "targetObjectDiscovery": True,
                        "anchorCoverageObjectDiscovery": True,
                    },
                    "liveTargetImageCanaryContract": {"missingKeys": ["targetHooks"]},
                },
            )
            self.write_json(
                target / "anchor-coverage.json",
                {
                    "schemaVersion": "dune-ue-anchor-coverage/v1",
                    "targetCoverageFieldsPresent": True,
                    "readyForTargetObjectDiscovery": True,
                    "groups": {
                        "names": {"present": 1, "targetPresent": 1, "total": 1},
                        "objects": {"present": 1, "targetPresent": 1, "total": 1},
                        "world": {"present": 1, "targetPresent": 1, "total": 1},
                        "dispatch": {"present": 0, "targetPresent": 0, "total": 1},
                        "package": {"present": 0, "targetPresent": 0, "total": 1},
                    },
                },
            )

            inventory = module.build_inventory([root], limit=10)

        self.assertEqual(inventory["entryCount"], 2)
        self.assertEqual(Path(inventory["best"]["directory"]).name, "target")
        self.assertIn("dispatch", inventory["best"]["anchorCoverage"]["missingTargetGroups"])
        self.assertIn("package", inventory["best"]["anchorCoverage"]["missingTargetGroups"])
        self.assertTrue(inventory["best"]["anchorCoverage"]["targetCoverageFieldsPresent"])
        self.assertEqual(inventory["nextCanaryFocus"]["phase"], "target-anchor-coverage")
        self.assertEqual(inventory["nextCanaryFocus"]["missingTargetGroups"], ["dispatch", "package"])
        self.assertIn(
            "recover target-image StaticLoadObject/StaticLoadClass",
            " ".join(inventory["nextCanaryFocus"]["actions"]),
        )

    def test_inventory_penalizes_contradictory_complete_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            contradictory = root / "contradictory"
            for directory in (clean, contradictory):
                self.write_json(
                    directory / "anchor-coverage.json",
                    {
                        "schemaVersion": "dune-ue-anchor-coverage/v1",
                        "targetCoverageFieldsPresent": True,
                        "groups": {
                            "names": {"present": 1, "targetPresent": 1, "total": 1},
                            "objects": {"present": 1, "targetPresent": 1, "total": 1},
                            "world": {"present": 1, "targetPresent": 1, "total": 1},
                            "dispatch": {"present": 1, "targetPresent": 1, "total": 1},
                            "package": {"present": 0, "targetPresent": 0, "total": 1},
                        },
                    },
                )
            self.write_json(
                clean / "ue4ss-readiness.json",
                {
                    "ready": {
                        "targetImageProcess": True,
                        "runtimeRootDiscovery": True,
                        "targetObjectDiscovery": True,
                        "targetHooks": True,
                    },
                    "liveTargetImageCanaryContract": {
                        "ready": False,
                        "missingKeys": ["runtimePackageLoading"],
                    },
                },
            )
            self.write_json(
                contradictory / "ue4ss-readiness.json",
                {
                    "ready": {
                        "ue4ssLuaApiComplete": True,
                        "targetImageProcess": True,
                        "runtimeRootDiscovery": True,
                        "targetObjectDiscovery": True,
                        "targetHooks": True,
                    },
                    "liveTargetImageCanaryContract": {
                        "ready": True,
                        "missingKeys": [],
                        "groups": {
                            "runtimePackageLoading": {
                                "ready": False,
                                "missingKeys": ["luaLoadAssetPackageNativeInvocation"],
                            }
                        },
                    },
                },
            )

            inventory = module.build_inventory([root], limit=10)

        self.assertEqual(Path(inventory["best"]["directory"]).name, "clean")
        contradictory_entry = next(
            entry for entry in inventory["entries"]
            if Path(entry["directory"]).name == "contradictory"
        )
        self.assertTrue(contradictory_entry["readiness"]["contradictions"])
        self.assertLess(contradictory_entry["score"], inventory["best"]["score"])

    def test_markdown_reports_best_missing_target_groups(self):
        inventory = {
            "entryCount": 1,
            "best": {
                "directory": "/evidence",
                "score": 10,
                "anchorCoverage": {"missingTargetGroups": ["dispatch", "package"]},
            },
            "entries": [
                {
                    "directory": "/evidence",
                    "score": 10,
                    "readiness": {"complete": False, "targetImageProcess": True},
                    "anchorCoverage": {
                        "provided": True,
                        "targetCoverageFieldsPresent": True,
                        "missingTargetGroups": ["dispatch", "package"],
                    },
                }
            ],
        }

        rendered = module.markdown(inventory)

        self.assertIn("Best missing target groups", rendered)
        self.assertIn("dispatch, package", rendered)

    def test_readiness_complete_requires_ready_live_target_image_contract(self):
        summary = module.readiness_summary(
            {
                "ready": {
                    "ue4ssLuaApiComplete": True,
                    "targetImageProcess": True,
                },
                "liveTargetImageCanaryContract": {
                    "ready": False,
                    "missingKeys": ["runtimePackageLoading"],
                },
            }
        )

        self.assertFalse(summary["complete"])
        self.assertTrue(summary["ue4ssLuaApiComplete"])
        self.assertFalse(summary["liveTargetImageCanaryReady"])
        self.assertIn("runtimePackageLoading", summary["missingLiveTargetImageKeys"])
        self.assertIn(
            "ue4ssLuaApiComplete is true without a ready live target-image contract",
            summary["contradictions"],
        )

    def test_readiness_complete_accepts_strict_live_target_image_contract(self):
        summary = module.readiness_summary(
            {
                "ready": {
                    "ue4ssLuaApiComplete": True,
                    "targetImageProcess": True,
                },
                "liveTargetImageCanaryContract": {
                    "ready": True,
                    "missingKeys": [],
                },
            }
        )

        self.assertTrue(summary["complete"])
        self.assertEqual(summary["contradictions"], [])

    def test_inventory_complete_requires_complete_target_anchor_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            self.write_json(
                evidence / "ue4ss-readiness.json",
                {
                    "ready": {
                        "ue4ssLuaApiComplete": True,
                        "targetImageProcess": True,
                        "runtimeRootDiscovery": True,
                        "targetObjectDiscovery": True,
                        "targetHooks": True,
                        "targetPackageLoadingSurface": True,
                    },
                    "liveTargetImageCanaryContract": {
                        "ready": True,
                        "missingKeys": [],
                    },
                },
            )
            self.write_json(
                evidence / "anchor-coverage.json",
                {
                    "schemaVersion": "dune-ue-anchor-coverage/v1",
                    "targetCoverageFieldsPresent": True,
                    "groups": {
                        "names": {"present": 1, "targetPresent": 1, "total": 1},
                        "objects": {"present": 1, "targetPresent": 1, "total": 1},
                        "world": {"present": 1, "targetPresent": 1, "total": 1},
                        "dispatch": {"present": 1, "targetPresent": 1, "total": 1},
                        "package": {"present": 0, "targetPresent": 0, "total": 1},
                    },
                },
            )

            inventory = module.build_inventory([root], limit=10)

        best = inventory["best"]
        self.assertFalse(best["readiness"]["complete"])
        self.assertIn("package", best["anchorCoverage"]["missingTargetGroups"])
        self.assertIn(
            "readiness is complete without complete target-image anchor coverage",
            best["readiness"]["contradictions"],
        )

    def test_inventory_complete_accepts_strict_live_contract_and_complete_target_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            self.write_json(
                evidence / "ue4ss-readiness.json",
                {
                    "ready": {
                        "ue4ssLuaApiComplete": True,
                        "targetImageProcess": True,
                        "runtimeRootDiscovery": True,
                        "targetObjectDiscovery": True,
                        "targetHooks": True,
                        "targetPackageLoadingSurface": True,
                    },
                    "liveTargetImageCanaryContract": {
                        "ready": True,
                        "missingKeys": [],
                    },
                },
            )
            self.write_json(
                evidence / "anchor-coverage.json",
                {
                    "schemaVersion": "dune-ue-anchor-coverage/v1",
                    "targetCoverageFieldsPresent": True,
                    "groups": {
                        "names": {"present": 1, "targetPresent": 1, "total": 1},
                        "objects": {"present": 1, "targetPresent": 1, "total": 1},
                        "world": {"present": 1, "targetPresent": 1, "total": 1},
                        "dispatch": {"present": 1, "targetPresent": 1, "total": 1},
                        "package": {"present": 1, "targetPresent": 1, "total": 1},
                    },
                },
            )

            inventory = module.build_inventory([root], limit=10)

        self.assertTrue(inventory["best"]["readiness"]["complete"])
        self.assertEqual(inventory["completeEntryCount"], 1)
        self.assertEqual(inventory["bestComplete"]["directory"], inventory["best"]["directory"])
        self.assertEqual(inventory["best"]["anchorCoverage"]["missingTargetGroups"], [])
        self.assertEqual(inventory["best"]["readiness"]["contradictions"], [])
        self.assertTrue(inventory["nextCanaryFocus"]["ready"])
        self.assertEqual(inventory["nextCanaryFocus"]["phase"], "complete")

    def test_require_complete_exits_nonzero_without_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            self.write_json(
                evidence / "ue4ss-readiness.json",
                {
                    "ready": {"ue4ssLuaApiComplete": True, "targetImageProcess": True},
                    "liveTargetImageCanaryContract": {"ready": False, "missingKeys": ["targetHooks"]},
                },
            )
            result = subprocess.run(
                [str(SCRIPT), str(root), "--require-complete", "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["completeEntryCount"], 0)
        self.assertIsNone(payload["bestComplete"])

    def test_require_complete_accepts_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            self.write_json(
                evidence / "ue4ss-readiness.json",
                {
                    "ready": {
                        "ue4ssLuaApiComplete": True,
                        "targetImageProcess": True,
                    },
                    "liveTargetImageCanaryContract": {"ready": True, "missingKeys": []},
                },
            )
            self.write_json(
                evidence / "anchor-coverage.json",
                {
                    "targetCoverageFieldsPresent": True,
                    "groups": {
                        "names": {"present": 1, "targetPresent": 1, "total": 1},
                        "objects": {"present": 1, "targetPresent": 1, "total": 1},
                        "world": {"present": 1, "targetPresent": 1, "total": 1},
                        "dispatch": {"present": 1, "targetPresent": 1, "total": 1},
                        "package": {"present": 1, "targetPresent": 1, "total": 1},
                    },
                },
            )
            result = subprocess.run(
                [str(SCRIPT), str(root), "--require-complete", "--format", "markdown"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Complete entries: `1`", result.stdout)
        self.assertIn("Best complete evidence:", result.stdout)

    def test_readiness_complete_rejects_blocked_live_contract_group(self):
        summary = module.readiness_summary(
            {
                "ready": {
                    "ue4ssLuaApiComplete": True,
                    "targetImageProcess": True,
                },
                "liveTargetImageCanaryContract": {
                    "ready": True,
                    "missingKeys": [],
                    "groups": {
                        "runtimePackageLoading": {
                            "ready": False,
                            "missingKeys": ["luaLoadAssetPackageNativeInvocation"],
                        }
                    },
                },
            }
        )

        self.assertFalse(summary["complete"])
        self.assertFalse(summary["strictLiveTargetImageReady"])
        self.assertIn("runtimePackageLoading", summary["blockedLiveTargetImageGroups"])
        self.assertEqual(
            summary["liveTargetImageGroupMissingKeys"]["runtimePackageLoading"],
            ["luaLoadAssetPackageNativeInvocation"],
        )
        self.assertIn(
            "liveTargetImageCanaryContract.ready is true while one or more groups are blocked",
            summary["contradictions"],
        )

    def test_readiness_summary_reports_ready_live_group_with_missing_keys(self):
        summary = module.readiness_summary(
            {
                "ready": {"ue4ssLuaApiComplete": False},
                "liveTargetImageCanaryContract": {
                    "ready": False,
                    "missingKeys": ["runtimePackageLoading"],
                    "groups": {
                        "runtimePackageLoading": {
                            "ready": True,
                            "missingKeys": ["luaLoadAssetPackageNativeInvocation"],
                        }
                    },
                },
            }
        )

        self.assertFalse(summary["strictLiveTargetImageReady"])
        self.assertIn("runtimePackageLoading", summary["blockedLiveTargetImageGroups"])
        self.assertIn(
            "liveTargetImageCanaryContract group runtimePackageLoading is ready while missingKeys is non-empty",
            summary["contradictions"],
        )

    def test_markdown_reports_live_contract_contradictions(self):
        inventory = {
            "entryCount": 1,
            "best": {
                "directory": "/evidence",
                "score": 110,
                "anchorCoverage": {"missingTargetGroups": []},
            },
            "entries": [
                {
                    "directory": "/evidence",
                    "score": 110,
                    "readiness": {
                        "complete": False,
                        "ue4ssLuaApiComplete": True,
                        "liveTargetImageCanaryReady": False,
                        "strictLiveTargetImageReady": False,
                        "targetImageProcess": True,
                        "missingLiveTargetImageKeys": ["runtimePackageLoading"],
                        "blockedLiveTargetImageGroups": ["runtimePackageLoading"],
                        "contradictions": [
                            "ue4ssLuaApiComplete is true without a ready live target-image contract"
                        ],
                    },
                    "anchorCoverage": {
                        "provided": True,
                        "targetCoverageFieldsPresent": True,
                        "missingTargetGroups": [],
                    },
                }
            ],
        }

        rendered = module.markdown(inventory)

        self.assertIn("luaApiComplete=`true`", rendered)
        self.assertIn("liveTargetImage=`false`", rendered)
        self.assertIn("strictLiveTargetImage=`false`", rendered)
        self.assertIn("missingLive=`runtimePackageLoading`", rendered)
        self.assertIn("blockedLiveGroups=`runtimePackageLoading`", rendered)
        self.assertIn("contradiction:", rendered)

    def test_next_canary_focus_moves_to_live_contract_after_target_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            self.write_json(
                evidence / "ue4ss-readiness.json",
                {
                    "ready": {
                        "targetImageProcess": True,
                        "runtimeRootDiscovery": True,
                        "targetObjectDiscovery": True,
                        "targetHooks": True,
                        "targetPackageLoadingSurface": True,
                    },
                    "liveTargetImageCanaryContract": {
                        "ready": False,
                        "missingKeys": ["runtimePackageLoading", "runtimeProcessEventDispatch"],
                        "groups": {
                            "runtimePackageLoading": {
                                "ready": False,
                                "missingKeys": ["luaLoadAssetPackageNativeInvocation"],
                            },
                            "runtimeProcessEventDispatch": {
                                "ready": False,
                                "missingKeys": ["ueProcessEventActiveValidation"],
                            },
                        },
                    },
                },
            )
            self.write_json(
                evidence / "anchor-coverage.json",
                {
                    "targetCoverageFieldsPresent": True,
                    "groups": {
                        "names": {"present": 1, "targetPresent": 1, "total": 1},
                        "objects": {"present": 1, "targetPresent": 1, "total": 1},
                        "world": {"present": 1, "targetPresent": 1, "total": 1},
                        "dispatch": {"present": 1, "targetPresent": 1, "total": 1},
                        "package": {"present": 1, "targetPresent": 1, "total": 1},
                    },
                },
            )

            inventory = module.build_inventory([root], limit=10)

        focus = inventory["nextCanaryFocus"]
        self.assertFalse(focus["ready"])
        self.assertEqual(focus["phase"], "live-target-image-contract")
        self.assertEqual(focus["missingTargetGroups"], [])
        self.assertEqual(
            focus["blockedLiveTargetImageGroups"],
            ["runtimePackageLoading", "runtimeProcessEventDispatch"],
        )
        self.assertIn("strict post-canary verifier", " ".join(focus["actions"]))

    def test_markdown_reports_next_canary_focus(self):
        inventory = {
            "entryCount": 1,
            "completeEntryCount": 0,
            "best": {
                "directory": "/evidence",
                "score": 27,
                "anchorCoverage": {"missingTargetGroups": ["package"]},
            },
            "nextCanaryFocus": {
                "phase": "target-anchor-coverage",
                "summary": "complete target-image anchor coverage before live runtime promotion",
                "actions": [
                    "recover target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchor evidence",
                ],
            },
            "entries": [],
        }

        rendered = module.markdown(inventory)

        self.assertIn("Next canary phase: `target-anchor-coverage`", rendered)
        self.assertIn("Next canary focus: `complete target-image anchor coverage before live runtime promotion`", rendered)
        self.assertIn("StaticLoadObject/StaticLoadClass", rendered)


if __name__ == "__main__":
    unittest.main()
