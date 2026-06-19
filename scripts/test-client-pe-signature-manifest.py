#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "export-client-pe-signature-manifest.py",
    ROOT / "analysis" / "export-client-pe-signature-manifest.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("export_client_pe_signature_manifest", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(exporter)


VALIDATION = {
    "scope": "executable",
    "patternCount": 2,
    "promotableCount": 1,
    "statusCounts": {"unique-expected": 1, "ambiguous": 1},
    "categoryCounts": {"cheat": 2},
    "patterns": [
        {
            "name": "CheatManager@0x2000#1",
            "category": "cheat",
            "source": "test",
            "xrefRva": "0x1000",
            "targetRva": "0x2000",
            "pattern": "48 8d 0d ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x200",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x200", "rva": "0x1000", "section": ".text", "expected": True}],
        },
        {
            "name": "CheatManager@0x2010#1",
            "category": "cheat",
            "source": "test",
            "xrefRva": "0x1080",
            "targetRva": "0x2010",
            "pattern": "48 8d 15 ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x280",
            "matchCount": 2,
            "status": "ambiguous",
            "promotable": False,
            "matches": [{"fileOffset": "0x280", "rva": "0x1080", "section": ".text", "expected": True}],
        },
    ],
}


UE_VALIDATION = {
    "scope": "executable",
    "patternCount": 3,
    "promotableCount": 3,
    "statusCounts": {"unique-expected": 3},
    "categoryCounts": {"ue": 3},
    "patterns": [
        {
            "name": "GUObjectArray@0x2000#1",
            "category": "ue",
            "source": "test",
            "xrefRva": "0x1000",
            "targetRva": "0x2000",
            "pattern": "48 8d 0d ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x200",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x200", "rva": "0x1000", "section": ".text", "expected": True}],
        },
        {
            "name": "StaticFindObject@0x3000#1",
            "category": "ue",
            "source": "test",
            "xrefRva": "0x1080",
            "targetRva": "0x3000",
            "pattern": "e8 ?? ?? ?? ??",
            "length": 5,
            "fixedBytes": 1,
            "expectedFileOffset": "0x280",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x280", "rva": "0x1080", "section": ".text", "expected": True}],
        },
        {
            "name": "CheatManager@0x4000#1",
            "category": "cheat",
            "source": "test",
            "xrefRva": "0x1100",
            "targetRva": "0x4000",
            "pattern": "48 8d 05 ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x300",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x300", "rva": "0x1100", "section": ".text", "expected": True}],
        },
    ],
}


class ClientPeSignatureManifestTests(unittest.TestCase):
    def test_manifest_filters_non_promotable_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            binary.write_bytes(b"MZ-test")
            entries = exporter.build_entries(VALIDATION)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 40, 1800)

            self.assertEqual(manifest["entryCount"], 1)
            self.assertEqual(manifest["entries"][0]["status"], "unique-expected")
            self.assertEqual(manifest["entries"][0]["expectedRva"], "0x1000")
            self.assertEqual(manifest["runtimeLimits"]["signatureFileEnv"], "DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE")
            self.assertIn("sha256", manifest["binary"])

    def test_can_include_non_promotable(self):
        entries = exporter.build_entries(VALIDATION, promotable_only=False)

        self.assertEqual(len(entries), 2)
        self.assertFalse(entries[1]["promotable"])

    def test_env_chunks_respect_pattern_and_value_limits(self):
        entries = []
        for index in range(5):
            entry = dict(exporter.build_entries(VALIDATION)[0])
            entry["id"] = f"sig-{index}"
            entries.append(entry)

        chunks = exporter.env_chunks(entries, max_patterns_per_scan=2, max_env_value_chars=512)

        self.assertEqual([len(chunk) for chunk in chunks], [2, 2, 1])

    def test_env_output_uses_loader_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            binary.write_bytes(b"MZ-test")
            entries = exporter.build_entries(VALIDATION)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 40, 1800)

            text = exporter.env_text(manifest)

            self.assertIn("DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES=", text)
            self.assertIn("CheatManager", text)

    def test_signatures_output_is_line_based_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            binary.write_bytes(b"MZ-test")
            entries = exporter.build_entries(VALIDATION)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 256, 1800)

            text = exporter.signatures_text(manifest)

            self.assertIn("DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE", text)
            self.assertIn("cheat-CheatManager", text)
            self.assertIn("48 8d 0d ?? ?? ?? ??", text)

    def test_anchor_signatures_output_is_loader_consumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            binary.write_bytes(b"MZ-test")
            entries = exporter.build_entries(UE_VALIDATION)
            manifest = exporter.make_manifest(binary, UE_VALIDATION, entries, None, None, 256, 1800)

            text = exporter.anchor_signatures_text(manifest)

            self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE", text)
            self.assertIn("GUObjectArray@riprel32+3=48 8d 0d ?? ?? ?? ??", text)
            self.assertIn("StaticFindObject@callrel32=e8 ?? ?? ?? ??", text)
            self.assertNotIn("CheatManager@", text)

    def test_anchor_signature_env_names_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            binary.write_bytes(b"MZ-test")
            entries = exporter.build_entries(UE_VALIDATION)
            manifest = exporter.make_manifest(binary, UE_VALIDATION, entries, None, None, 256, 1800)

            self.assertEqual(manifest["runtimeLimits"]["anchorSignatureEnv"], "DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES")
            self.assertEqual(
                manifest["runtimeLimits"]["anchorSignatureFileEnv"],
                "DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE",
            )


if __name__ == "__main__":
    unittest.main()
