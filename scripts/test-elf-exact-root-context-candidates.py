#!/usr/bin/env python3
import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-exact-root-context-candidates.py"

spec = importlib.util.spec_from_file_location("summarize_elf_exact_root_context_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ExactRootContextCandidateTests(unittest.TestCase):
    def args(self, **overrides):
        values = {
            "max_address_ratio": 0.05,
            "min_qword_refs": 1,
            "require_read": True,
            "require_write": False,
            "max_function_buckets": 0,
            "context_limit": 2,
            "include_group_context": False,
            "limit": 50,
        }
        values.update(overrides)
        return Namespace(**values)

    def test_promotes_low_address_ratio_exact_root_context(self):
        global_refs = {
            "top": [
                {
                    "target": "0x4000",
                    "section": ".bss",
                    "exactAnchorHintCounts": {"GUObjectArray": 1},
                    "context": [{"exactAnchorHints": ["GUObjectArray"], "string": "GUObjectArray"}],
                }
            ]
        }
        shapes = {
            "rows": [
                {
                    "target": "0x4000",
                    "score": 10,
                    "refCount": 3,
                    "qwordRefCount": 3,
                    "functionBucketCount": 1,
                    "addressRatio": 0.0,
                    "kindCounts": {"read": 2, "write": 1},
                    "section": ".bss",
                }
            ]
        }

        report = module.summarize(global_refs, shapes, self.args())

        self.assertEqual(report["promotableCount"], 1)
        self.assertTrue(report["candidates"][0]["promotable"])
        self.assertEqual(report["rootGroupCounts"]["objects"], 1)

    def test_blocks_high_address_ratio_root_context(self):
        global_refs = {
            "top": [
                {
                    "target": "0x5000",
                    "section": ".bss",
                    "exactAnchorHintCounts": {"GEngine": 1},
                    "context": [{"exactAnchorHints": ["GEngine"], "string": "Create GEngine"}],
                }
            ]
        }
        shapes = {
            "rows": [
                {
                    "target": "0x5000",
                    "qwordRefCount": 9,
                    "functionBucketCount": 7,
                    "addressRatio": 0.99,
                    "kindCounts": {"address": 9},
                }
            ]
        }

        report = module.summarize(global_refs, shapes, self.args())

        self.assertEqual(report["promotableCount"], 0)
        self.assertIn("addressRatio", report["candidates"][0]["blockers"][0])
        self.assertIn("missing read refs", report["candidates"][0]["blockers"])

    def test_ignores_non_root_exact_context(self):
        report = module.summarize(
            {"top": [{"target": "0x6000", "exactAnchorHintCounts": {"UObject": 3}}]},
            {"rows": []},
            self.args(),
        )

        self.assertEqual(report["candidateCount"], 0)

    def test_can_include_group_context_near_misses(self):
        global_refs = {
            "top": [
                {
                    "target": "0x7000",
                    "section": ".bss",
                    "groupCounts": {"names": 2},
                    "context": [{"groups": ["names"], "string": "FName candidate context"}],
                }
            ]
        }
        shapes = {
            "rows": [
                {
                    "target": "0x7000",
                    "qwordRefCount": 30,
                    "functionBucketCount": 28,
                    "addressRatio": 0.0,
                    "kindCounts": {"read": 29, "write": 1},
                }
            ]
        }

        report = module.summarize(global_refs, shapes, self.args(include_group_context=True))

        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["exactCandidateCount"], 0)
        self.assertEqual(report["groupContextCandidateCount"], 1)
        self.assertTrue(report["candidates"][0]["promotable"])
        self.assertEqual(report["candidates"][0]["evidenceKind"], "root-group-context")


if __name__ == "__main__":
    unittest.main()
