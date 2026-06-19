#!/usr/bin/env python3
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "validate-client-pe-signatures.py",
    ROOT / "analysis" / "validate-client-pe-signatures.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("validate_client_pe_signatures", SCRIPT)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


XREF_SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-client-loader-xrefs.py",
    ROOT / "analysis" / "summarize-client-loader-xrefs.py",
)
XREF_SCRIPT = next((path for path in XREF_SCRIPT_CANDIDATES if path.exists()), XREF_SCRIPT_CANDIDATES[0])

xref_spec = importlib.util.spec_from_file_location("summarize_client_loader_xrefs", XREF_SCRIPT)
xrefs = importlib.util.module_from_spec(xref_spec)
assert xref_spec.loader is not None
xref_spec.loader.exec_module(xrefs)


def make_synthetic_pe(duplicate=False):
    image_base = 0x140000000
    text_rva = 0x1000
    rdata_rva = 0x2000
    text_raw = 0x200
    rdata_raw = 0x400
    data = bytearray(0x800)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)

    pe = 0x80
    data[pe : pe + 4] = b"PE\0\0"
    file_header = pe + 4
    optional_size = 0xF0
    struct.pack_into("<HHIIIHH", data, file_header, 0x8664, 2, 0, 0, 0, optional_size, 0x22)

    optional = file_header + 20
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<Q", data, optional + 24, image_base)
    struct.pack_into("<II", data, optional + 32, 0x1000, 0x200)
    struct.pack_into("<II", data, optional + 56, 0x3000, 0x200)
    struct.pack_into("<I", data, optional + 108, 16)

    sections = optional + optional_size
    data[sections : sections + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, sections + 8, 0x200, text_rva, 0x200, text_raw, 0, 0, 0, 0, 0x60000020)
    rdata_section = sections + 40
    data[rdata_section : rdata_section + 8] = b".rdata\0\0"
    struct.pack_into(
        "<IIIIIIHHI",
        data,
        rdata_section + 8,
        0x200,
        rdata_rva,
        0x200,
        rdata_raw,
        0,
        0,
        0,
        0,
        0x40000040,
    )

    string_rva = rdata_rva + 0x20
    disp = string_rva - (text_rva + 7)
    instruction = b"\x48\x8d\x0d" + struct.pack("<i", disp)
    data[text_raw : text_raw + len(instruction)] = instruction
    if duplicate:
        data[text_raw + 0x80 : text_raw + 0x80 + len(instruction)] = instruction
    data[rdata_raw + 0x20 : rdata_raw + 0x20 + len(b"CheatManager\0")] = b"CheatManager\0"
    return bytes(data), text_raw, string_rva


class ClientPeSignatureTests(unittest.TestCase):
    def test_unique_expected_manual_pattern_is_promotable(self):
        binary, expected_file, _string_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            path.write_bytes(binary)
            pe = xrefs.load_pe_image(path)
            values, mask = validator.parse_pattern("48 8d 0d ?? ?? ?? ??")
            spec = validator.PatternSpec(
                name="lea-string",
                pattern="48 8d 0d ?? ?? ?? ??",
                bytes_=values,
                mask=mask,
                expected_file_offset=expected_file,
                category="manual",
                source="test",
                xref_rva="",
                target_rva="",
            )

            rows = validator.validate_patterns(pe, [spec], "executable", 8)

            self.assertEqual(rows[0]["status"], "unique-expected")
            self.assertTrue(rows[0]["promotable"])
            self.assertEqual(rows[0]["matches"][0]["fileOffset"], "0x200")

    def test_duplicate_pattern_is_ambiguous(self):
        binary, expected_file, _string_rva = make_synthetic_pe(duplicate=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            path.write_bytes(binary)
            pe = xrefs.load_pe_image(path)
            values, mask = validator.parse_pattern("48 8d 0d ?? ?? ?? ??")
            spec = validator.PatternSpec(
                name="lea-string",
                pattern="48 8d 0d ?? ?? ?? ??",
                bytes_=values,
                mask=mask,
                expected_file_offset=expected_file,
                category="manual",
                source="test",
                xref_rva="",
                target_rva="",
            )

            rows = validator.validate_patterns(pe, [spec], "executable", 8)

            self.assertEqual(rows[0]["status"], "ambiguous-expected")
            self.assertFalse(rows[0]["promotable"])
            self.assertEqual(rows[0]["matchCount"], 2)

    def test_extracts_patterns_from_xref_summary(self):
        binary, _expected_file, string_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandbox-Win64-Shipping.exe"
            binary_path.write_bytes(binary)
            pe = xrefs.load_pe_image(binary_path)
            target = xrefs.make_target(pe, "CheatManager", "cheat", "string", string_rva)
            found = xrefs.scan_xrefs(pe, [target])
            summary = xrefs.serializable(pe, [target], found, context_radius=0)

            specs = validator.patterns_from_xref_summary(summary, ["cheat"], [], 0)
            rows = validator.validate_patterns(pe, specs, "executable", 8)

            self.assertEqual(len(specs), 1)
            self.assertEqual(rows[0]["status"], "unique-expected")

    def test_extracts_patterns_from_manifest(self):
        binary, expected_file, _string_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandbox-Win64-Shipping.exe"
            binary_path.write_bytes(binary)
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "id": "cheat-CheatManager-test",
                                "category": "cheat",
                                "name": "CheatManager",
                                "pattern": "48 8d 0d ?? ?? ?? ??",
                                "expectedFileOffset": f"0x{expected_file:x}",
                                "xrefRva": "0x1000",
                                "targetRva": "0x2020",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            pe = xrefs.load_pe_image(binary_path)

            specs = validator.patterns_from_manifest(manifest_path, ["cheat"], [], 0)
            rows = validator.validate_patterns(pe, specs, "executable", 8)

            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].name, "cheat-CheatManager-test")
            self.assertEqual(rows[0]["status"], "unique-expected")
            self.assertTrue(rows[0]["promotable"])

    def test_manifest_ignore_expected_offsets_accepts_moved_unique_match(self):
        binary, expected_file, _string_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandbox-Win64-Shipping.exe"
            binary_path.write_bytes(binary)
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "id": "brt-PerformCanBePlaced-test",
                                "category": "brt",
                                "name": "PerformCanBePlaced",
                                "pattern": "48 8d 0d ?? ?? ?? ??",
                                "expectedFileOffset": f"0x{expected_file + 0x40:x}",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            pe = xrefs.load_pe_image(binary_path)

            exact_specs = validator.patterns_from_manifest(manifest_path, ["brt"], [], 0)
            exact_rows = validator.validate_patterns(pe, exact_specs, "executable", 8)
            moved_specs = validator.patterns_from_manifest(
                manifest_path,
                ["brt"],
                [],
                0,
                ignore_expected_offsets=True,
            )
            moved_rows = validator.validate_patterns(pe, moved_specs, "executable", 8)

            self.assertEqual(exact_rows[0]["status"], "unique-unexpected")
            self.assertFalse(exact_rows[0]["promotable"])
            self.assertEqual(moved_rows[0]["status"], "unique-unexpected")
            self.assertTrue(moved_rows[0]["promotable"])


if __name__ == "__main__":
    unittest.main()
