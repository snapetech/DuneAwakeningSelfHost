#!/usr/bin/env python3
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "validate-elf-signatures.py",
    ROOT / "analysis" / "validate-elf-signatures.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("validate_elf_signatures", SCRIPT)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


XREF_SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-linux-loader-xrefs.py",
    ROOT / "analysis" / "summarize-linux-loader-xrefs.py",
)
XREF_SCRIPT = next((path for path in XREF_SCRIPT_CANDIDATES if path.exists()), XREF_SCRIPT_CANDIDATES[0])

xref_spec = importlib.util.spec_from_file_location("summarize_linux_loader_xrefs", XREF_SCRIPT)
xrefs = importlib.util.module_from_spec(xref_spec)
assert xref_spec.loader is not None
xref_spec.loader.exec_module(xrefs)


def make_synthetic_elf(duplicate=False):
    data = bytearray(0x400)
    data[:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    data[6] = 1
    struct.pack_into(
        "<HHIQQQIHHHHHH",
        data,
        16,
        3,
        0x3E,
        1,
        0,
        64,
        0,
        0,
        64,
        56,
        1,
        0,
        0,
        0,
    )
    base_vaddr = 0x1000
    struct.pack_into(
        "<IIQQQQQQ",
        data,
        64,
        xrefs.PT_LOAD,
        xrefs.PF_X | 4,
        0,
        base_vaddr,
        0,
        len(data),
        len(data),
        0x1000,
    )
    code_file = 0x100
    code_vaddr = base_vaddr + code_file
    target_file = 0x180
    target_vaddr = base_vaddr + target_file
    disp = target_vaddr - (code_vaddr + 7)
    instruction = b"\x48\x8d\x05" + struct.pack("<i", disp)
    data[code_file : code_file + len(instruction)] = instruction
    if duplicate:
        data[code_file + 0x40 : code_file + 0x40 + len(instruction)] = instruction
    data[target_file : target_file + len(b"CheatManager\0")] = b"CheatManager\0"
    return bytes(data), code_file, target_file, target_vaddr


class ElfSignatureTests(unittest.TestCase):
    def test_unique_expected_manual_pattern_is_promotable(self):
        binary, expected_file, _target_file, _target_vaddr = make_synthetic_elf()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            path.write_bytes(binary)
            binary_data, segments = xrefs.load_elf_segments(path)
            values, mask = validator.parse_pattern("48 8d 05 ?? ?? ?? ??")
            spec = validator.PatternSpec(
                name="lea-string",
                pattern="48 8d 05 ?? ?? ?? ??",
                bytes_=values,
                mask=mask,
                expected_file_offset=expected_file,
                category="manual",
                source="test",
                xref_vaddr="",
                target_vaddr="",
            )

            rows = validator.validate_patterns(binary_data, segments, [spec], "executable", 8)

            self.assertEqual(rows[0]["status"], "unique-expected")
            self.assertTrue(rows[0]["promotable"])
            self.assertEqual(rows[0]["matches"][0]["fileOffset"], "0x100")
            self.assertEqual(rows[0]["matches"][0]["imageOffset"], "0x100")

    def test_duplicate_pattern_is_ambiguous(self):
        binary, expected_file, _target_file, _target_vaddr = make_synthetic_elf(duplicate=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            path.write_bytes(binary)
            binary_data, segments = xrefs.load_elf_segments(path)
            values, mask = validator.parse_pattern("48 8d 05 ?? ?? ?? ??")
            spec = validator.PatternSpec(
                name="lea-string",
                pattern="48 8d 05 ?? ?? ?? ??",
                bytes_=values,
                mask=mask,
                expected_file_offset=expected_file,
                category="manual",
                source="test",
                xref_vaddr="",
                target_vaddr="",
            )

            rows = validator.validate_patterns(binary_data, segments, [spec], "executable", 8)

            self.assertEqual(rows[0]["status"], "ambiguous-expected")
            self.assertFalse(rows[0]["promotable"])
            self.assertEqual(rows[0]["matchCount"], 2)

    def test_extracts_patterns_from_xref_summary(self):
        binary, _expected_file, target_file, target_vaddr = make_synthetic_elf()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            path.write_bytes(binary)
            binary_data, segments = xrefs.load_elf_segments(path)
            target = xrefs.Target(
                name="CheatManager",
                category="cheat",
                kind="string",
                file_offset=target_file,
                image_offset=target_file,
                vaddr=target_vaddr,
            )
            found = xrefs.scan_xrefs(binary_data, segments, [target])
            summary = xrefs.serializable(binary_data, segments, [target], found, signature_prefix=0, signature_suffix=1)

            specs = validator.patterns_from_xref_summary(summary, ["cheat"], [], 0)
            rows = validator.validate_patterns(binary_data, segments, specs, "executable", 8)

            self.assertEqual(len(specs), 1)
            self.assertEqual(rows[0]["status"], "unique-expected")
            self.assertEqual(rows[0]["matches"][0]["fileOffset"], "0x100")

    def test_extracts_patterns_from_manifest(self):
        binary, expected_file, _target_file, _target_vaddr = make_synthetic_elf()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandboxServer-Linux-Shipping"
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
                                "pattern": "48 8d 05 ?? ?? ?? ??",
                                "expectedFileOffset": f"0x{expected_file:x}",
                                "xrefVaddr": "0x1100",
                                "targetVaddr": "0x1180",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            binary_data, segments = xrefs.load_elf_segments(binary_path)

            specs = validator.patterns_from_manifest(manifest_path, ["cheat"], [], 0)
            rows = validator.validate_patterns(binary_data, segments, specs, "executable", 8)

            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].name, "cheat-CheatManager-test")
            self.assertEqual(rows[0]["status"], "unique-expected")
            self.assertTrue(rows[0]["promotable"])

    def test_manifest_ignore_expected_offsets_accepts_moved_unique_match(self):
        binary, expected_file, _target_file, _target_vaddr = make_synthetic_elf()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandboxServer-Linux-Shipping"
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
                                "pattern": "48 8d 05 ?? ?? ?? ??",
                                "expectedFileOffset": f"0x{expected_file + 0x40:x}",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            binary_data, segments = xrefs.load_elf_segments(binary_path)

            exact_specs = validator.patterns_from_manifest(manifest_path, ["brt"], [], 0)
            exact_rows = validator.validate_patterns(binary_data, segments, exact_specs, "executable", 8)
            moved_specs = validator.patterns_from_manifest(
                manifest_path,
                ["brt"],
                [],
                0,
                ignore_expected_offsets=True,
            )
            moved_rows = validator.validate_patterns(binary_data, segments, moved_specs, "executable", 8)

            self.assertEqual(exact_rows[0]["status"], "unique-unexpected")
            self.assertFalse(exact_rows[0]["promotable"])
            self.assertEqual(moved_rows[0]["status"], "unique-unexpected")
            self.assertTrue(moved_rows[0]["promotable"])

    def test_extracts_patterns_from_donor_candidate_validation(self):
        binary, _expected_file, _target_file, _target_vaddr = make_synthetic_elf()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandboxServer-Linux-Shipping"
            binary_path.write_bytes(binary)
            candidate_path = tmp_path / "donor-candidate-validation.json"
            candidate_path.write_text(
                json.dumps(
                    {
                        "format": "elf64-donor-transfer",
                        "patterns": [
                            {
                                "name": "StaticLoadObject",
                                "category": "package",
                                "sourceProvenance": "external-donor",
                                "pattern": "48 8d 05 ?? ?? ?? ??",
                                "donor": {
                                    "symbol": "StaticLoadObject(UClass*)",
                                    "fileOffset": "0x200",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            binary_data, segments = xrefs.load_elf_segments(binary_path)

            specs = validator.patterns_from_donor_candidate_validation(candidate_path, ["package"], [], 0)
            rows = validator.validate_patterns(binary_data, segments, specs, "executable", 8)

            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].name, "StaticLoadObject")
            self.assertEqual(specs[0].category, "package")
            self.assertEqual(specs[0].source, "StaticLoadObject(UClass*)")
            self.assertEqual(specs[0].source_provenance, "external-donor")
            self.assertEqual(rows[0]["status"], "unique-unexpected")
            self.assertTrue(rows[0]["promotable"])


if __name__ == "__main__":
    unittest.main()
