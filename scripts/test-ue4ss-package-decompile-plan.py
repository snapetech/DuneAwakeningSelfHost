#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-decompile-plan.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_package_decompile_plan", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageDecompilePlanTests(unittest.TestCase):
    def test_build_plan_exports_offsets_and_commands(self):
        evidence = {
            "complete": False,
            "promotableRouteCount": 0,
            "decompileReviewQueue": [
                {
                    "priority": 40,
                    "address": "0xa54f700",
                    "route": "streamable-reviewed-callgraph",
                    "kind": "decompile-indirect-call-node",
                    "label": "stslot0",
                    "reason": "recover dynamic target",
                },
                {
                    "priority": 40,
                    "address": "0xa54f700",
                    "route": "duplicate",
                    "kind": "decompile-indirect-call-node",
                    "label": "dup",
                    "reason": "duplicate address",
                },
                {
                    "priority": 40,
                    "address": "0xa54f730",
                    "route": "streamable-reviewed-callgraph",
                    "kind": "decompile-indirect-call-node",
                    "label": "stslot1",
                    "reason": "recover dynamic target",
                },
            ],
            "routes": [],
        }

        plan = module.build_plan(evidence, "/tmp/server", 3)

        self.assertEqual(plan["ghidraOffsets"], ["0xa54f700", "0xa54f730"])
        self.assertEqual(plan["focusedOutput"], "build/server-ue4ss-focused-functions.txt")
        self.assertIn("DUNE_GHIDRA_FOCUSED_OUT='build/server-ue4ss-focused-functions.txt'", plan["commands"]["ghidraRunWhenUnlocked"])
        self.assertIn("DUNE_GHIDRA_OFFSETS='0xa54f700,0xa54f730'", plan["commands"]["ghidraRunWhenUnlocked"])
        self.assertIn("--dry-run", plan["commands"]["ghidraDryRun"])
        self.assertIn("decompile queued offsets", plan["quickestPath"])
        self.assertIn("LoadAsset or LoadClass", " ".join(plan["acceptanceCriteria"]))

    def test_build_plan_without_offsets_exports_runtime_trace_path(self):
        evidence = {
            "complete": False,
            "promotableRouteCount": 0,
            "decompileReviewQueue": [],
            "suppressedKnownNonPackageQueue": [
                {
                    "address": "0x128ce8d0",
                    "route": "kismet",
                    "kind": "suppressed-known-non-package-indirect-call-node",
                    "label": "FLoadAssetActionBase_dispatch",
                    "reason": "owner-surface assert/log path",
                }
            ],
            "suppressedKnownNonPackageQueueCount": 1,
            "routes": [],
        }

        plan = module.build_plan(evidence, "/tmp/server", 3)

        self.assertEqual(plan["ghidraOffsets"], [])
        self.assertEqual(plan["commands"], {})
        self.assertEqual(plan["suppressedKnownNonPackageQueueCount"], 1)
        self.assertIn("owner-surface assert/log path", plan["suppressedKnownNonPackageQueue"][0]["reason"])
        self.assertIn("runtime trace", plan["quickestPath"])

    def test_markdown_contains_targets_and_negative_evidence(self):
        plan = {
            "completePackageRoute": False,
            "promotableRouteCount": 0,
            "binary": "/tmp/server",
            "ghidraOffsets": ["0x1000"],
            "reviewQueue": [
                {
                    "priority": 5,
                    "address": "0x1000",
                    "route": "package",
                    "kind": "decompile-package-loader-vtable-slot",
                    "label": "vtable for FLinkerLoad slot 42",
                    "reason": "locate package ABI",
                }
            ],
            "suppressedKnownNonPackageQueue": [
                {
                    "address": "0x128ce8d0",
                    "route": "kismet",
                    "kind": "suppressed-known-non-package-indirect-call-node",
                    "label": "FLoadAssetActionBase_dispatch",
                    "reason": "owner-surface assert/log path",
                }
            ],
            "acceptanceCriteria": ["prove package ABI"],
            "quickestPath": "decompile queued offsets",
            "commands": {"ghidraDryRun": "dry", "ghidraRunWhenUnlocked": "run"},
            "classification": {"knownBlockers": ["streamable path is non-promotable"]},
        }

        text = module.markdown(plan)

        self.assertIn("UE4SS Package Decompile Plan", text)
        self.assertIn("0x1000", text)
        self.assertIn("vtable for FLinkerLoad", text)
        self.assertIn("Suppressed Known Non-Package", text)
        self.assertIn("owner-surface assert/log path", text)
        self.assertIn("streamable path is non-promotable", text)

    def test_cli_reads_evidence_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(
                json.dumps(
                    {
                        "complete": False,
                        "promotableRouteCount": 0,
                        "decompileReviewQueue": [],
                        "routes": [],
                    }
                ),
                encoding="utf-8",
            )

            rc = module.main(["--evidence", str(path), "--format", "json"])

        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
