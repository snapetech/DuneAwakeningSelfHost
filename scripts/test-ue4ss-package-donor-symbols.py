#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-donor-symbols.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_package_donor_symbols", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageDonorSymbolsTests(unittest.TestCase):
    def write_symbols(self, text):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "donor.nm"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(tmp.cleanup)
        return path

    def test_text_symbol_rows_are_promotable(self):
        path = self.write_symbols(
            "\n".join(
                [
                    "0000000001234000 T StaticLoadObject(UClass*, UObject*, wchar_t const*, wchar_t const*, unsigned int, UPackageMap*, bool)",
                    "0000000001235000 W StaticLoadClass(UClass*, UObject*, wchar_t const*, wchar_t const*, unsigned int, UPackageMap*)",
                    "0000000001236000 R LoadPackageString",
                    "                 U ResolveName",
                    "",
                ]
            )
        )

        summary = module.summarize(path, "/tmp/target", assume_text=True)

        self.assertEqual(summary["schemaVersion"], "dune-ue4ss-package-donor-symbols/v1")
        self.assertEqual(summary["symbolCount"], 4)
        self.assertEqual(summary["promotableSymbolCount"], 2)
        self.assertEqual(summary["anchorsPresent"], ["StaticLoadObject", "StaticLoadClass", "LoadPackage", "ResolveName"])
        self.assertFalse(summary["completeAnchorFamilyCoverage"])
        self.assertEqual(summary["symbols"][0]["anchor"], "StaticLoadObject")
        self.assertTrue(summary["symbols"][0]["promotable"])
        self.assertIn("--signature 'StaticLoadObject=<reviewed bytes from donor 0x1234000>'", summary["commands"][0]["validateTransferredSignature"])
        self.assertIn("--ignore-expected-offsets", summary["commands"][0]["validateTransferredSignature"])

    def test_no_text_symbols_reports_donor_requirement(self):
        path = self.write_symbols("0000000001236000 R LoadPackageString\n")

        summary = module.summarize(path, "/tmp/target", assume_text=True)

        self.assertEqual(summary["promotableSymbolCount"], 0)
        self.assertEqual(summary["commands"], [])
        self.assertIn("find an unstripped/symbolized", summary["nextStep"])

    def test_relocatable_pattern_masks_relative_displacements(self):
        code = bytes.fromhex("55 48 89 e5 e8 11 22 33 44 48 8b 05 aa bb cc dd c3")

        pattern = module.mask_relocatable_pattern(code, 0x1000)

        self.assertEqual(
            pattern,
            "55 48 89 e5 e8 ?? ?? ?? ?? 48 8b 05 ?? ?? ?? ?? c3",
        )

    def test_commands_use_extracted_donor_signature_when_present(self):
        rows = [
            {
                "anchor": "StaticLoadObject",
                "address": "0x1234000",
                "type": "T",
                "name": "StaticLoadObject()",
                "promotable": True,
                "donorSignature": {
                    "pattern": "55 48 89 e5 e8 ?? ?? ?? ??",
                },
            }
        ]

        commands = module.build_commands("/tmp/donor", "/tmp/target", rows)

        self.assertIn(
            "--signature 'StaticLoadObject=55 48 89 e5 e8 ?? ?? ?? ??'",
            commands[0]["validateTransferredSignature"],
        )

    def test_candidate_validation_marks_donor_patterns_unvalidated(self):
        summary = {
            "source": "/tmp/donor",
            "targetBinary": "/tmp/target",
            "symbols": [
                {
                    "anchor": "StaticLoadObject",
                    "address": "0x1234000",
                    "type": "T",
                    "name": "StaticLoadObject()",
                    "promotable": True,
                    "donorSignature": {
                        "fileOffset": "0x4000",
                        "vaddr": "0x1234000",
                        "length": 9,
                        "pattern": "55 48 89 e5 e8 ?? ?? ?? ??",
                        "wildcardPolicy": "mask displacements",
                    },
                },
                {
                    "anchor": "LoadPackage",
                    "address": "0x1235000",
                    "type": "R",
                    "name": "LoadPackageString",
                    "promotable": False,
                },
            ],
        }

        validation = module.candidate_validation(summary)

        self.assertEqual(validation["format"], "elf64-donor-transfer")
        self.assertEqual(validation["patternCount"], 1)
        self.assertEqual(validation["promotableCount"], 0)
        row = validation["patterns"][0]
        self.assertEqual(row["category"], "package")
        self.assertEqual(row["name"], "StaticLoadObject")
        self.assertEqual(row["status"], "donor-unvalidated")
        self.assertFalse(row["promotable"])
        self.assertEqual(row["fixedBytes"], 5)
        self.assertEqual(row["sourceProvenance"], "external-donor")
        self.assertEqual(row["donor"]["fileOffset"], "0x4000")

    def test_markdown_lists_symbols_and_commands(self):
        path = self.write_symbols("0000000001234000 T StaticLoadObject(UClass*)\n")
        summary = module.summarize(path, "/tmp/target", assume_text=True)

        text = module.markdown(summary)

        self.assertIn("UE4SS Package Donor Symbols", text)
        self.assertIn("StaticLoadObject", text)
        self.assertIn("validate-elf-signatures.py", text)

    def test_cli_json(self):
        path = self.write_symbols("0000000001234000 T StaticLoadObject(UClass*)\n")

        rc = module.main([str(path), "--assume-text", "--format", "json"])

        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
