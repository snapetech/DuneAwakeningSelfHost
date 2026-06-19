#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue-root-recovery-queue.py"

spec = importlib.util.spec_from_file_location("summarize_ue_root_recovery_queue", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class UeRootRecoveryQueueTests(unittest.TestCase):
    def test_rejected_offsets_include_candidate_anchor_and_pointer_targets(self):
        outcomes = {
            "candidates": [
                {
                    "verdict": "weak-false-positive",
                    "imageOffset": "0x100",
                    "anchorTargets": [{"imageOffset": "0x200"}],
                    "pointerTargets": [{"imageOffset": "0x300"}],
                }
            ]
        }

        self.assertEqual(module.rejected_offsets(outcomes), {0x100, 0x200, 0x300})

    def test_summarize_filters_rejected_targets_and_ranks_writable_refs(self):
        neighborhoods = {
            "schemaVersion": "dune-elf-ue-function-neighborhoods/v1",
            "binary": "/tmp/server",
            "functions": [
                {
                    "function": "0x10",
                    "fileOffset": "0x10",
                    "sourceName": ".init_array[1]",
                    "sourceRole": "constructor",
                    "callCount": 2,
                    "requiredGroupCoverage": [],
                    "groupCounts": {},
                    "signature": {"sha256": "aaa", "fileOffset": "0x10", "length": 16},
                    "refs": [
                        {
                            "kind": "rip-memory",
                            "section": ".bss",
                            "target": "0x200",
                            "text": "mov qword ptr [rip + 1], rax",
                            "instruction": "0x12",
                            "symbols": [],
                            "string": "",
                        },
                        {
                            "kind": "rip-memory",
                            "section": ".bss",
                            "target": "0x400",
                            "text": "mov qword ptr [rip + 2], rax",
                            "instruction": "0x16",
                            "symbols": [],
                            "string": "",
                        },
                    ],
                },
                {
                    "function": "0x20",
                    "fileOffset": "0x20",
                    "sourceName": ".init_array[2]",
                    "sourceRole": "constructor",
                    "callCount": 0,
                    "requiredGroupCoverage": [],
                    "groupCounts": {},
                    "refs": [
                        {
                            "kind": "rip-memory",
                            "section": ".rodata",
                            "target": "0x500",
                            "text": "lea rax, [rip + 1]",
                            "instruction": "0x21",
                            "symbols": [],
                            "string": "",
                        }
                    ],
                },
            ],
        }
        outcomes = {"candidates": [{"verdict": "rejected", "imageOffset": "0x200"}]}

        summary = module.summarize(neighborhoods, outcomes, limit=10, target_limit=4)

        self.assertEqual(summary["queuedFunctionCount"], 1)
        self.assertEqual(summary["rows"][0]["function"], "0x10")
        self.assertEqual(summary["rows"][0]["candidateTargets"][0]["target"], "0x400")
        self.assertEqual(summary["rows"][0]["candidateTargets"][0]["pointerLikeRefCount"], 1)
        self.assertEqual(summary["rows"][0]["candidateTargets"][0]["byteGuardRefCount"], 0)
        self.assertEqual(summary["rows"][0]["candidateTargets"][0]["constantStoreRefCount"], 0)
        self.assertEqual(summary["rows"][0]["pointerLikeRefCount"], 1)
        self.assertEqual(summary["rows"][0]["usableWritableRefCount"], 1)
        self.assertEqual(summary["rows"][0]["targetSpan"], 0)

    def test_movzx_byte_guard_is_not_write_or_pointer_like(self):
        ref = {
            "kind": "rip-memory",
            "section": ".bss",
            "target": "0x1000",
            "text": "movzx eax, byte ptr [rip + 0x10]",
            "instruction": "0x10",
            "symbols": [],
            "string": "",
        }

        self.assertFalse(module.is_write_like(ref))
        self.assertFalse(module.is_pointer_like_ref(ref))
        self.assertTrue(module.is_byte_guard_ref(ref))

    def test_constant_store_ref_detection(self):
        ref = {
            "kind": "rip-memory",
            "section": ".bss",
            "target": "0x1000",
            "text": "mov dword ptr [rip + 0x10], 0xffffffff",
            "instruction": "0x10",
            "symbols": [],
            "string": "",
        }

        self.assertTrue(module.is_constant_store_ref(ref))


if __name__ == "__main__":
    unittest.main()
