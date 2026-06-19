#!/usr/bin/env python3
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-pe-ue-function-neighborhoods.py"
QUEUE_SCRIPT = ROOT / "scripts" / "summarize-ue-root-recovery-queue.py"

spec = importlib.util.spec_from_file_location("summarize_pe_ue_function_neighborhoods", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

queue_spec = importlib.util.spec_from_file_location("summarize_ue_root_recovery_queue", QUEUE_SCRIPT)
queue_module = importlib.util.module_from_spec(queue_spec)
assert queue_spec.loader is not None
queue_spec.loader.exec_module(queue_module)


def make_synthetic_pe():
    image_base = 0x140000000
    text_rva = 0x1000
    rdata_rva = 0x2000
    data_rva = 0x3000
    text_raw = 0x200
    rdata_raw = 0x400
    data_raw = 0x600
    data = bytearray(0x900)
    data[:2] = b"MZ"
    pe = 0x80
    data[0x3C:0x40] = struct.pack("<I", pe)
    data[pe : pe + 4] = b"PE\0\0"
    file_header = pe + 4
    optional_size = 0xF0
    struct.pack_into("<HHIIIHH", data, file_header, 0x8664, 3, 0, 0, 0, optional_size, 0x22)
    optional = file_header + 20
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<Q", data, optional + 24, image_base)
    sections = optional + optional_size
    data[sections : sections + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, sections + 8, 0x100, text_rva, 0x200, text_raw, 0, 0, 0, 0, 0x60000020)
    rdata_section = sections + 40
    data[rdata_section : rdata_section + 8] = b".rdata\0\0"
    struct.pack_into("<IIIIIIHHI", data, rdata_section + 8, 0x100, rdata_rva, 0x200, rdata_raw, 0, 0, 0, 0, 0x40000040)
    data_section = sections + 80
    data[data_section : data_section + 8] = b".data\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, data_section + 8, 0x100, data_rva, 0x200, data_raw, 0, 0, 0, 0, 0xC0000040)

    data[rdata_raw : rdata_raw + 7] = b"GWorld\0"
    # mov qword ptr [rip + disp], rax; ret
    disp = (image_base + data_rva + 0x20) - (image_base + text_rva + 7)
    data[text_raw : text_raw + 8] = b"\x48\x89\x05" + struct.pack("<i", disp) + b"\xc3"
    return bytes(data), text_rva, text_raw, rdata_rva, data_rva


class PeUeFunctionNeighborhoodTests(unittest.TestCase):
    def test_xref_seed_emits_queue_compatible_writable_refs(self):
        binary_data, text_rva, text_raw, rdata_rva, data_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "client.exe"
            binary.write_bytes(binary_data)
            xrefs = Path(tmp) / "xrefs.json"
            xrefs.write_text(
                json.dumps(
                    {
                        "targets": [
                            {
                                "name": "GWorld",
                                "category": "ue",
                                "rva": f"0x{rdata_rva:x}",
                                "xrefs": [
                                    {
                                        "kind": "rip-memory",
                                        "xrefRva": f"0x{text_rva:x}",
                                        "xrefFileOffset": f"0x{text_raw:x}",
                                        "targetRva": f"0x{rdata_rva:x}",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "binary": binary,
                    "xref_json": xrefs,
                    "loader_log": None,
                    "loader": [],
                    "pid": [],
                    "exe_substring": [],
                    "category": [],
                    "name": [],
                    "context_radius": 96,
                    "seed_limit": 8,
                    "prelude": 0,
                    "window": 32,
                    "signature_length": 8,
                    "count_uniqueness": True,
                },
            )()

            summary = module.summarize(args)
            queue = queue_module.summarize(summary, outcomes={}, limit=10, target_limit=4)

        self.assertEqual(summary["schemaVersion"], "dune-pe-ue-function-neighborhoods/v1")
        self.assertEqual(summary["functionCount"], 1)
        self.assertEqual(summary["functions"][0]["refs"][0]["section"], ".data")
        self.assertEqual(summary["functions"][0]["refs"][0]["target"], f"0x{data_rva + 0x20:x}")
        self.assertEqual(summary["writableTargetCount"], 1)
        self.assertEqual(summary["writableTargets"][0]["target"], f"0x{data_rva + 0x20:x}")
        self.assertEqual(summary["writableTargets"][0]["exactAnchorHintCounts"], {"GWorld": 1})
        self.assertEqual(summary["writableTargets"][0]["context"][0]["exactAnchorHints"], ["GWorld"])
        self.assertEqual(queue["queuedFunctionCount"], 1)
        self.assertEqual(queue["rows"][0]["candidateTargets"][0]["section"], ".data")

    def test_exact_anchor_hints_use_token_boundaries(self):
        self.assertEqual(module.exact_anchor_hints("GUObjectArray"), ["GUObjectArray"])
        self.assertEqual(module.exact_anchor_hints("UObject"), ["UObject"])


if __name__ == "__main__":
    unittest.main()
