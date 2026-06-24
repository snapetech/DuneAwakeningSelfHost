#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "export-elf-signature-manifest.py",
    ROOT / "analysis" / "export-elf-signature-manifest.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("export_elf_signature_manifest", SCRIPT)
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
            "name": "CheatManager@0x1180#1",
            "category": "cheat",
            "source": "test",
            "xrefVaddr": "0x1100",
            "targetVaddr": "0x1180",
            "pattern": "48 8d 05 ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x100",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x100", "imageOffset": "0x100", "vaddr": "0x1100", "expected": True}],
        },
        {
            "name": "CheatManager@0x1190#1",
            "category": "cheat",
            "source": "test",
            "xrefVaddr": "0x1140",
            "targetVaddr": "0x1190",
            "pattern": "48 8d 15 ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x140",
            "matchCount": 2,
            "status": "ambiguous",
            "promotable": False,
            "matches": [{"fileOffset": "0x140", "imageOffset": "0x140", "vaddr": "0x1140", "expected": True}],
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
            "name": "GWorld@0x1180#1",
            "category": "ue",
            "source": "test",
            "xrefVaddr": "0x1100",
            "targetVaddr": "0x1180",
            "pattern": "48 8b 0d ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x100",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x100", "imageOffset": "0x100", "vaddr": "0x1100", "expected": True}],
        },
        {
            "name": "ProcessEvent@0x2080#1",
            "category": "ue",
            "source": "test",
            "xrefVaddr": "0x2000",
            "targetVaddr": "0x2080",
            "pattern": "e8 ?? ?? ?? ??",
            "length": 5,
            "fixedBytes": 1,
            "expectedFileOffset": "0x200",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x200", "imageOffset": "0x200", "vaddr": "0x2000", "expected": True}],
        },
        {
            "name": "CheatManager@0x3000#1",
            "category": "cheat",
            "source": "test",
            "xrefVaddr": "0x3000",
            "targetVaddr": "0x3080",
            "pattern": "48 8d 05 ?? ?? ?? ??",
            "length": 7,
            "fixedBytes": 3,
            "expectedFileOffset": "0x300",
            "matchCount": 1,
            "status": "unique-expected",
            "promotable": True,
            "matches": [{"fileOffset": "0x300", "imageOffset": "0x300", "vaddr": "0x3000", "expected": True}],
        },
    ],
}


class ElfSignatureManifestTests(unittest.TestCase):
    def test_manifest_filters_non_promotable_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(VALIDATION)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 40, 1800, "server")

            self.assertEqual(manifest["schemaVersion"], "dune-elf-signature-manifest/v1")
            self.assertEqual(manifest["platform"], "linux-server-x86_64")
            self.assertEqual(manifest["entryCount"], 1)
            self.assertEqual(manifest["entries"][0]["status"], "unique-expected")
            self.assertEqual(manifest["entries"][0]["expectedVaddr"], "0x1100")
            self.assertEqual(manifest["entries"][0]["sourceProvenance"], "target")
            self.assertEqual(manifest["runtimeLimits"]["loaderEnv"], "DUNE_PROBE_LOADER_SCAN_SIGNATURES")
            self.assertEqual(manifest["runtimeLimits"]["signatureFileEnv"], "DUNE_PROBE_LOADER_SCAN_SIGNATURES_FILE")

    def test_linux_client_env_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(VALIDATION)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 40, 1800, "linux-client")

            self.assertEqual(manifest["platform"], "linux-client-x86_64")
            self.assertEqual(manifest["runtimeLimits"]["loaderEnv"], "DUNE_CLIENT_PROBE_SCAN_SIGNATURES")
            self.assertEqual(manifest["runtimeLimits"]["signatureFileEnv"], "DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE")

    def test_can_include_non_promotable(self):
        entries = exporter.build_entries(VALIDATION, promotable_only=False)

        self.assertEqual(len(entries), 2)
        self.assertFalse(entries[1]["promotable"])

    def test_env_chunks_use_target_loader_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = []
            for index in range(5):
                entry = dict(exporter.build_entries(VALIDATION)[0])
                entry["id"] = f"sig-{index}"
                entries.append(entry)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 2, 512, "server")

            chunks = exporter.env_chunks(entries, max_patterns_per_scan=2, max_env_value_chars=512)
            text = exporter.env_text(manifest)

            self.assertEqual([len(chunk) for chunk in chunks], [2, 2, 1])
            self.assertIn("DUNE_PROBE_LOADER_SCAN_SIGNATURES=", text)
            self.assertIn("48 8d 05 ?? ?? ?? ??", text)

    def test_signatures_output_is_line_based_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(VALIDATION)
            manifest = exporter.make_manifest(binary, VALIDATION, entries, None, None, 256, 1800, "server")

            text = exporter.signatures_text(manifest)

            self.assertIn("DUNE_PROBE_LOADER_SCAN_SIGNATURES_FILE", text)
            self.assertIn("cheat-CheatManager", text)
            self.assertIn("48 8d 05 ?? ?? ?? ??", text)

    def test_anchor_signatures_output_is_loader_consumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(UE_VALIDATION)
            manifest = exporter.make_manifest(binary, UE_VALIDATION, entries, None, None, 256, 1800, "server")

            text = exporter.anchor_signatures_text(manifest)

            self.assertIn("DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE", text)
            self.assertIn("GWorld@riprel32+3=48 8b 0d ?? ?? ?? ??", text)
            self.assertIn("ProcessEvent@callrel32=e8 ?? ?? ?? ??", text)
            self.assertNotIn("CheatManager@", text)

    def test_linux_client_anchor_signature_env_names_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(UE_VALIDATION)
            manifest = exporter.make_manifest(binary, UE_VALIDATION, entries, None, None, 256, 1800, "linux-client")

            self.assertEqual(manifest["runtimeLimits"]["anchorSignatureEnv"], "DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES")
            self.assertEqual(
                manifest["runtimeLimits"]["anchorSignatureFileEnv"],
                "DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE",
            )

    def test_default_ue_anchor_set_includes_static_load_class(self):
        self.assertIn("StaticLoadClass", exporter.UE_ANCHORS)
        self.assertIn("StaticLoadClass", exporter.UE_ANCHOR_GROUPS["package"])
        self.assertIn("staticloadclass", exporter.UE_ANCHOR_ALIASES["StaticLoadClass"])
        self.assertIn("uobjectstaticloadclass", exporter.UE_ANCHOR_ALIASES["StaticLoadClass"])

    def test_package_aliases_promote_to_anchor_signature_entries(self):
        validation = {
            "scope": "executable",
            "patterns": [
                {
                    "name": "uobject-static-load-class",
                    "category": "ue",
                    "source": "test",
                    "xrefVaddr": "0x5000",
                    "targetVaddr": "0x5080",
                    "pattern": "e8 ?? ?? ?? ??",
                    "length": 5,
                    "fixedBytes": 1,
                    "expectedFileOffset": "0x500",
                    "status": "unique-expected",
                    "promotable": True,
                    "matches": [{"fileOffset": "0x500", "imageOffset": "0x500", "vaddr": "0x5000", "expected": True}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandbox-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(validation)
            manifest = exporter.make_manifest(binary, validation, entries, None, None, 256, 1800, "linux-client")

        anchors = exporter.anchor_signature_entries(manifest)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["anchorName"], "StaticLoadClass")
        self.assertEqual(anchors[0]["anchorGroup"], "package")
        self.assertTrue(anchors[0]["anchorTransformExpected"])

    def test_donor_unique_unexpected_entry_preserves_target_match_offsets(self):
        validation = {
            "scope": "executable",
            "promotableCount": 1,
            "patterns": [
                {
                    "name": "StaticLoadObject",
                    "category": "package",
                    "source": "StaticLoadObject(UClass*)",
                    "sourceProvenance": "external-donor",
                    "xrefVaddr": "",
                    "targetVaddr": "",
                    "pattern": "e8 ?? ?? ?? ??",
                    "length": 5,
                    "fixedBytes": 1,
                    "expectedFileOffset": "",
                    "status": "unique-unexpected",
                    "promotable": True,
                    "matches": [
                        {
                            "fileOffset": "0x1234",
                            "imageOffset": "0x1234",
                            "vaddr": "0x2234",
                            "expected": False,
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            binary.write_bytes(b"\x7fELF-test")
            entries = exporter.build_entries(validation)
            manifest = exporter.make_manifest(binary, validation, entries, None, None, 256, 1800, "server")

        entry = manifest["entries"][0]
        anchors = exporter.anchor_signature_entries(manifest)

        self.assertEqual(entry["sourceProvenance"], "external-donor")
        self.assertEqual(entry["expectedImageOffset"], "")
        self.assertEqual(entry["matchFileOffset"], "0x1234")
        self.assertEqual(entry["matchImageOffset"], "0x1234")
        self.assertEqual(entry["matchVaddr"], "0x2234")
        self.assertEqual(anchors[0]["anchorName"], "StaticLoadObject")
        self.assertEqual(anchors[0]["anchorGroup"], "package")
        self.assertTrue(anchors[0]["anchorTransformExpected"])


if __name__ == "__main__":
    unittest.main()
