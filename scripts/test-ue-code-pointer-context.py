#!/usr/bin/env python3
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue-code-pointer-context.py"

spec = importlib.util.spec_from_file_location("summarize_ue_code_pointer_context", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def make_synthetic_pe_for_code_pointer():
    image_base = 0x140000000
    text_rva = 0x1000
    rdata_rva = 0x2000
    text_raw = 0x200
    rdata_raw = 0x400
    data = bytearray(0x800)
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
    struct.pack_into("<IIIIIIHHI", data, sections + 8, 0x100, text_rva, 0x200, text_raw, 0, 0, 0, 0, 0x60000020)
    rdata_section = sections + 40
    data[rdata_section : rdata_section + 8] = b".rdata\0\0"
    struct.pack_into(
        "<IIIIIIHHI",
        data,
        rdata_section + 8,
        0x100,
        rdata_rva,
        0x200,
        rdata_raw,
        0,
        0,
        0,
        0,
        0x40000040,
    )
    target_string_rva = rdata_rva + 0x40
    data[rdata_raw + 0x40 : rdata_raw + 0x4B] = b"GUObjectArray\0"
    # lea rax, [rip + disp]; ret
    disp = (image_base + target_string_rva) - (image_base + text_rva + 7)
    data[text_raw : text_raw + 8] = b"\x48\x8d\x05" + struct.pack("<i", disp) + b"\xc3"
    struct.pack_into("<Q", data, rdata_raw + 0x20, image_base + text_rva)
    return bytes(data), text_raw, rdata_raw + 0x20, text_rva, rdata_rva + 0x20


class UeCodePointerContextTests(unittest.TestCase):
    def test_markdown_includes_pointer_context_and_instruction(self):
        summary = {
            "rowCount": 1,
            "binary": "/tmp/server",
            "sourceOutcomes": "/tmp/outcomes.json",
            "rows": [
                {
                    "name": "GUObjectArray",
                    "imageOffset": "0x14a3bdc0",
                    "verdict": "weak-false-positive",
                    "recommendation": "reject-code-pointer-and-trace-caller-dataflow",
                    "anchor": {"fileOffset": "0x14a3adc0", "perms": "r--p"},
                    "anchorPointerContext": [
                        {
                            "slot": 0,
                            "vaddr": "0x14a3bdc0",
                            "value": "0xabbd820",
                            "section": ".text",
                            "flags": "AX",
                            "symbols": [],
                            "string": "",
                        }
                    ],
                    "pointerTargets": [
                        {
                            "imageOffset": "0xabbd820",
                            "fileOffset": "0xabbd820",
                            "staticTarget": {
                                "signatureSha256": "abc",
                                "instructions": [{"address": "0xabbd820", "text": "push rbp"}],
                                "ripRefs": [],
                            },
                        }
                    ],
                }
            ],
        }

        rendered = module.markdown(summary, limit_instructions=8)

        self.assertIn("GUObjectArray", rendered)
        self.assertIn("reject-code-pointer-and-trace-caller-dataflow", rendered)
        self.assertIn("push rbp", rendered)

    def test_summarize_ignores_non_code_pointer_recommendations(self):
        original_import_script = module.import_script
        original_load_json = module.load_json

        class FakePtrCtx:
            @staticmethod
            def load_sections(_data):
                return []

            @staticmethod
            def load_symbols(_data, _sections):
                return {}

            @staticmethod
            def load_relocations(_data, _sections):
                return {}

        class FakeXrefs:
            @staticmethod
            def load_elf_segments(_binary):
                return b"", []

        def fake_import_script(path, _name):
            return FakePtrCtx if "pointer-context" in str(path) else FakeXrefs

        def fake_load_json(_path):
            return {
                "candidates": [
                    {
                        "name": "GWorld",
                        "imageOffset": "0x1",
                        "recommendation": "reject-null-or-empty-global",
                    }
                ]
            }

        module.import_script = fake_import_script
        module.load_json = fake_load_json
        try:
            with tempfile.TemporaryDirectory() as tmp:
                binary = Path(tmp) / "server"
                binary.write_bytes(b"\x7fELF\x02\x01")
                outcomes = Path(tmp) / "outcomes.json"
                outcomes.write_text("{}", encoding="utf-8")
                args = type(
                    "Args",
                    (),
                    {
                        "binary": binary,
                        "candidate_outcomes_json": outcomes,
                        "pointer_window": 3,
                        "max_instructions": 8,
                        "signature_length": 16,
                    },
                )()
                summary = module.summarize(args)
        finally:
            module.import_script = original_import_script
            module.load_json = original_load_json

        self.assertEqual(summary["rowCount"], 0)

    def test_unknown_binary_reports_unsupported_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "blob.bin"
            binary.write_bytes(b"NOPE")
            outcomes = Path(tmp) / "outcomes.json"
            outcomes.write_text('{"candidates": []}', encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "binary": binary,
                    "candidate_outcomes_json": outcomes,
                    "pointer_window": 3,
                    "max_instructions": 8,
                    "signature_length": 16,
                },
            )()

            summary = module.summarize(args)

        self.assertFalse(summary["supported"])
        self.assertEqual(summary["reason"], "unsupported-binary-format")

    def test_pe_binary_reports_code_pointer_context(self):
        binary_data, text_file, anchor_file, text_rva, anchor_rva = make_synthetic_pe_for_code_pointer()
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "client.exe"
            binary.write_bytes(binary_data)
            outcomes = Path(tmp) / "outcomes.json"
            outcomes.write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "name": "GUObjectArray",
                                "imageOffset": f"0x{anchor_rva:x}",
                                "verdict": "weak-false-positive",
                                "recommendation": "reject-code-pointer-and-trace-caller-dataflow",
                                "anchorTargets": [{"fileOffset": f"0x{anchor_file:x}", "perms": "r--p"}],
                                "pointerTargets": [
                                    {"imageOffset": f"0x{text_rva:x}", "fileOffset": f"0x{text_file:x}"}
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
                    "candidate_outcomes_json": outcomes,
                    "pointer_window": 1,
                    "max_instructions": 8,
                    "signature_length": 16,
                },
            )()

            summary = module.summarize(args)

        self.assertTrue(summary["supported"])
        self.assertEqual(summary["format"], "pe")
        self.assertEqual(summary["rowCount"], 1)
        target = summary["rows"][0]["pointerTargets"][0]["staticTarget"]
        self.assertEqual(target["rva"], f"0x{text_rva:x}")
        self.assertIn("lea", target["instructions"][0]["text"])
        self.assertEqual(target["ripRefs"][0]["section"], ".rdata")
        self.assertEqual(summary["rows"][0]["anchorPointerContext"][1]["section"], ".text")


if __name__ == "__main__":
    unittest.main()
