#!/usr/bin/env python3
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-pe-writable-root-shapes.py"
XREF_SCRIPT = ROOT / "scripts" / "summarize-client-loader-xrefs.py"

spec = importlib.util.spec_from_file_location("summarize_pe_writable_root_shapes", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

xref_spec = importlib.util.spec_from_file_location("client_xrefs", XREF_SCRIPT)
xrefs = importlib.util.module_from_spec(xref_spec)
assert xref_spec.loader is not None
xref_spec.loader.exec_module(xrefs)


def make_synthetic_pe():
    image_base = 0x140000000
    text_rva = 0x1000
    data_rva = 0x3000
    text_raw = 0x200
    data_raw = 0x600
    data = bytearray(0x900)
    data[:2] = b"MZ"
    pe = 0x80
    data[0x3C:0x40] = struct.pack("<I", pe)
    data[pe : pe + 4] = b"PE\0\0"
    file_header = pe + 4
    optional_size = 0xF0
    struct.pack_into("<HHIIIHH", data, file_header, 0x8664, 2, 0, 0, 0, optional_size, 0x22)
    optional = file_header + 20
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<Q", data, optional + 24, image_base)
    sections = optional + optional_size
    data[sections : sections + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, sections + 8, 0x200, text_rva, 0x200, text_raw, 0, 0, 0, 0, 0x60000020)
    data_section = sections + 40
    data[data_section : data_section + 8] = b".data\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, data_section + 8, 0x200, data_rva, 0x200, data_raw, 0, 0, 0, 0, 0xC0000040)

    pos = text_raw
    text_va = image_base + text_rva
    qword_root_va = image_base + data_rva + 0x20
    scalar_root_va = image_base + data_rva + 0x40
    address_root_va = image_base + data_rva + 0x60
    for target_va, op, length in [
        (qword_root_va, b"\x48\x8b\x05", 7),
        (qword_root_va, b"\x48\x89\x05", 7),
        (scalar_root_va, b"\x8b\x05", 6),
        (scalar_root_va, b"\x89\x05", 6),
        (address_root_va, b"\x48\x8d\x05", 7),
    ]:
        insn_va = text_va + (pos - text_raw)
        disp = target_va - (insn_va + length)
        data[pos : pos + length] = op + struct.pack("<i", disp)
        pos += 8
    return bytes(data)


class PeWritableRootShapeTests(unittest.TestCase):
    def test_qword_filters_reject_scalar_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "client.exe"
            binary.write_bytes(make_synthetic_pe())
            args = type(
                "Args",
                (),
                {
                    "binary": binary,
                    "candidate_outcomes_json": None,
                    "require_read_write": True,
                    "require_qword": True,
                    "min_qword_refs": 2,
                    "max_scalar_ratio": 0.10,
                    "min_read_refs": 1,
                    "min_write_refs": 1,
                    "max_function_buckets": 0,
                    "max_address_ratio": None,
                    "include_target": [],
                    "min_score": 0,
                    "limit": 20,
                },
            )()

            summary = module.summarize(args)

        self.assertEqual(summary["schemaVersion"], "dune-pe-writable-root-shapes/v1")
        self.assertEqual([row["target"] for row in summary["rows"]], ["0x3020"])
        self.assertEqual(summary["rows"][0]["qwordRefCount"], 2)
        self.assertEqual(summary["rows"][0]["scalarRatio"], 0.0)
        self.assertEqual(summary["rows"][0]["addressRatio"], 0.0)

    def test_rejected_offsets_are_skipped(self):
        self.assertEqual(
            module.rejected_offsets({"candidates": [{"name": "GWorld", "imageOffset": "0x3020", "verdict": "rejected"}]}),
            {0x3020},
        )

    def test_include_target_forces_diagnostic_row_past_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "client.exe"
            binary.write_bytes(make_synthetic_pe())
            args = type(
                "Args",
                (),
                {
                    "binary": binary,
                    "candidate_outcomes_json": None,
                    "require_read_write": True,
                    "require_qword": True,
                    "min_qword_refs": 2,
                    "max_scalar_ratio": 0.10,
                    "min_read_refs": 1,
                    "min_write_refs": 1,
                    "max_function_buckets": 0,
                    "max_address_ratio": 0.25,
                    "include_target": ["0x3060"],
                    "min_score": 0,
                    "limit": 20,
                },
            )()

            summary = module.summarize(args)

        forced = next(row for row in summary["rows"] if row["target"] == "0x3060")
        self.assertTrue(forced["forcedInclude"])
        self.assertEqual(forced["kindCounts"], {"address": 1})
        self.assertEqual(forced["addressRatio"], 1.0)


if __name__ == "__main__":
    unittest.main()
