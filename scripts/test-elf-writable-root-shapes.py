#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-writable-root-shapes.py"
PTRCTX_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

spec = importlib.util.spec_from_file_location("summarize_elf_writable_root_shapes", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

ptr_spec = importlib.util.spec_from_file_location("ptrctx", PTRCTX_SCRIPT)
ptrctx = importlib.util.module_from_spec(ptr_spec)
assert ptr_spec.loader is not None
ptr_spec.loader.exec_module(ptrctx)

xref_spec = importlib.util.spec_from_file_location("xrefs", XREF_SCRIPT)
xrefs = importlib.util.module_from_spec(xref_spec)
assert xref_spec.loader is not None
xref_spec.loader.exec_module(xrefs)


class ElfWritableRootShapeTests(unittest.TestCase):
    def test_qword_root_scores_above_byte_guard(self):
        data = bytearray(0x200)
        code_vaddr = 0x1000
        root_vaddr = 0x3000
        guard_vaddr = 0x3010

        pos = 0
        for target, op in [
            (root_vaddr, b"\x48\x8b\x05"),
            (root_vaddr, b"\x48\x89\x05"),
            (root_vaddr, b"\x48\x8d\x05"),
            (guard_vaddr, b"\x0f\xb6\x05"),
        ]:
            insn_vaddr = code_vaddr + pos
            disp = target - (insn_vaddr + 7)
            data[pos : pos + 7] = op + struct.pack("<i", disp)
            pos += 8

        segments = [xrefs.Segment(0, 0x100, code_vaddr, 0x100, xrefs.PF_X)]
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, code_vaddr, 0, 0x100, 0, 0),
            ptrctx.Section(".bss", 8, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, root_vaddr, 0x100, 0x80, 0, 0),
        ]

        rows = module.scan_writable_shapes(xrefs, ptrctx, bytes(data), segments, sections, set())
        root = rows[root_vaddr]
        guard = rows[guard_vaddr]

        self.assertEqual(root["kindCounts"]["read"], 1)
        self.assertEqual(root["kindCounts"]["write"], 1)
        self.assertEqual(root["kindCounts"]["address"], 1)
        self.assertEqual(guard["kindCounts"]["byte-guard"], 1)
        self.assertGreater(module.score_row(root), module.score_row(guard))

    def test_rejected_offsets_are_skipped(self):
        self.assertEqual(
            module.rejected_offsets({"candidates": [{"name": "GUObjectArray", "imageOffset": "0x3000", "verdict": "rejected"}]}),
            {0x3000},
        )

    def test_score_prefers_balanced_read_write_over_address_only(self):
        balanced = {
            "section": ".bss",
            "kindCounts": {"read": 4, "write": 4},
            "sizeCounts": {"8": 8},
            "functionBuckets": {0x1000: 4, 0x1100: 4},
        }
        address_only = {
            "section": ".bss",
            "kindCounts": {"address": 8},
            "sizeCounts": {"8": 8},
            "functionBuckets": {0x1000: 8},
        }

        self.assertGreater(module.score_row(balanced), module.score_row(address_only))

    def test_qword_and_scalar_filters_reject_scalar_roots(self):
        class Args:
            binary = Path("fake")
            candidate_outcomes_json = None
            require_read_write = True
            require_qword = True
            min_qword_refs = 2
            max_scalar_ratio = 0.25
            min_read_refs = 1
            min_write_refs = 1
            max_function_buckets = 0
            max_address_ratio = None
            min_score = 0
            limit = 20

        rows = {
            0x3000: {
                "target": 0x3000,
                "section": ".bss",
                "flags": "AW",
                "kindCounts": {"read": 4, "write": 4},
                "sizeCounts": {"4": 8},
                "functionBuckets": {0x1000: 8},
                "refs": [],
            },
            0x4000: {
                "target": 0x4000,
                "section": ".bss",
                "flags": "AW",
                "kindCounts": {"read": 4, "write": 4},
                "sizeCounts": {"8": 8},
                "functionBuckets": {0x2000: 8},
                "refs": [],
            },
        }

        class FakeXrefs:
            @staticmethod
            def load_elf_segments(_path):
                return b"", []

        class FakePtrctx:
            @staticmethod
            def load_sections(_data):
                return []

        original_import = module.import_script
        original_scan = module.scan_writable_shapes
        try:
            module.import_script = lambda path, name: FakeXrefs if "xrefs" in name else FakePtrctx
            module.scan_writable_shapes = lambda *_args: rows
            summary = module.summarize(Args())
        finally:
            module.import_script = original_import
            module.scan_writable_shapes = original_scan

        self.assertEqual([row["target"] for row in summary["rows"]], ["0x4000"])
        self.assertEqual(summary["rows"][0]["qwordRefCount"], 8)
        self.assertEqual(summary["rows"][0]["scalarRatio"], 0.0)
        self.assertEqual(summary["rows"][0]["addressRatio"], 0.0)

    def test_include_target_forces_diagnostic_row_past_filters(self):
        class Args:
            binary = Path("fake")
            candidate_outcomes_json = None
            require_read_write = True
            require_qword = True
            min_qword_refs = 2
            max_scalar_ratio = 0.10
            min_read_refs = 1
            min_write_refs = 1
            max_function_buckets = 4
            max_address_ratio = 0.25
            min_score = 0
            include_target = ["0x3000"]
            limit = 20

        rows = {
            0x3000: {
                "target": 0x3000,
                "section": ".bss",
                "flags": "AW",
                "kindCounts": {"address": 10, "byte-guard": 2},
                "sizeCounts": {"1": 2, "8": 10},
                "functionBuckets": {base: 1 for base in range(0x1000, 0x2000, 0x100)},
                "refs": [],
            },
        }

        class FakeXrefs:
            @staticmethod
            def load_elf_segments(_path):
                return b"", []

        class FakePtrctx:
            @staticmethod
            def load_sections(_data):
                return []

        original_import = module.import_script
        original_scan = module.scan_writable_shapes
        try:
            module.import_script = lambda path, name: FakeXrefs if "xrefs" in name else FakePtrctx
            module.scan_writable_shapes = lambda *_args: rows
            summary = module.summarize(Args())
        finally:
            module.import_script = original_import
            module.scan_writable_shapes = original_scan

        self.assertEqual([row["target"] for row in summary["rows"]], ["0x3000"])
        self.assertTrue(summary["rows"][0]["forcedInclude"])
        self.assertGreater(summary["rows"][0]["addressRatio"], 0.25)


if __name__ == "__main__":
    unittest.main()
