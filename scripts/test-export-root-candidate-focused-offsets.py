#!/usr/bin/env python3
import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-root-candidate-focused-offsets.py"

spec = importlib.util.spec_from_file_location("export_root_candidate_focused_offsets", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class RootCandidateFocusedOffsetsTests(unittest.TestCase):
    def args(self, **overrides):
        values = {"limit": 10, "samples_per_candidate": 2, "only_promotable": True}
        values.update(overrides)
        return Namespace(**values)

    def test_exports_write_before_read_samples_for_promotable_candidate(self):
        candidates = {
            "candidates": [
                {
                    "target": "0x4000",
                    "evidenceKind": "root-group-context",
                    "rootGroups": ["objects"],
                    "promotable": True,
                }
            ]
        }
        shapes = {
            "rows": [
                {
                    "target": "0x4000",
                    "refCount": 3,
                    "qwordRefCount": 3,
                    "functionBucketCount": 2,
                    "addressRatio": 0.0,
                    "kindCounts": {"read": 2, "write": 1},
                    "samples": [
                        {"instruction": "0x120", "kind": "read", "text": "mov rax, [rip]"},
                        {"instruction": "0x110", "kind": "write", "text": "mov [rip], rax"},
                        {"instruction": "0x100", "kind": "address", "text": "lea rax, [rip]"},
                    ],
                }
            ]
        }

        report = module.summarize(candidates, shapes, self.args())

        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["offsetsCsv"], "0x110,0x120")
        self.assertEqual(report["candidates"][0]["offsets"], ["0x110", "0x120"])

    def test_skips_non_promotable_by_default(self):
        report = module.summarize(
            {"candidates": [{"target": "0x5000", "promotable": False}]},
            {"rows": [{"target": "0x5000", "samples": [{"instruction": "0x200", "kind": "read"}]}]},
            self.args(),
        )

        self.assertEqual(report["candidateCount"], 0)
        self.assertEqual(report["offsetCount"], 0)

    def test_can_include_non_promotable_when_requested(self):
        report = module.summarize(
            {"candidates": [{"target": "0x5000", "promotable": False}]},
            {"rows": [{"target": "0x5000", "samples": [{"instruction": "0x200", "kind": "read"}]}]},
            self.args(only_promotable=False),
        )

        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["offsetsCsv"], "0x200")


if __name__ == "__main__":
    unittest.main()
