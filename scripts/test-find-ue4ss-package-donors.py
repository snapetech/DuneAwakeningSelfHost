#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "find-ue4ss-package-donors.py"

spec = importlib.util.spec_from_file_location("find_ue4ss_package_donors", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageDonorSearchTests(unittest.TestCase):
    def test_search_finds_text_symbol_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "ue-linux-symbols.map"
            candidate.write_text(
                "0000000001234000 T StaticLoadObject(UClass*, UObject*)\n"
                "0000000001235000 T LoadPackage(UPackage*, wchar_t const*)\n",
                encoding="utf-8",
            )

            summary = module.search([root], "/tmp/target", max_depth=2)

        self.assertEqual(summary["schemaVersion"], "dune-ue4ss-package-donor-search/v1")
        self.assertEqual(summary["candidateCount"], 1)
        self.assertEqual(summary["usableCandidateCount"], 1)
        self.assertEqual(summary["candidates"][0]["mode"], "text")
        self.assertEqual(summary["candidates"][0]["promotableSymbolCount"], 2)
        self.assertIn("StaticLoadObject", summary["candidates"][0]["anchorsPresent"])

    def test_search_skips_dependency_directories_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skipped = root / "node_modules"
            skipped.mkdir()
            (skipped / "ue-linux-symbols.map").write_text(
                "0000000001234000 T StaticLoadObject(UClass*)\n",
                encoding="utf-8",
            )

            summary = module.search([root], "/tmp/target", max_depth=3)

        self.assertEqual(summary["candidateCount"], 0)
        self.assertEqual(summary["usableCandidateCount"], 0)
        self.assertIn("provide an unstripped/symbolized", summary["nextStep"])

    def test_resolve_name_alone_is_not_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "ue-linux-symbols.map"
            candidate.write_text(
                "0000000001234000 T lldb_private::ResolveName(char const*)\n",
                encoding="utf-8",
            )

            summary = module.search([root], "/tmp/target", max_depth=2)

        self.assertEqual(summary["candidateCount"], 1)
        self.assertEqual(summary["usableCandidateCount"], 0)
        self.assertFalse(summary["candidates"][0]["usable"])
        self.assertEqual(summary["candidates"][0]["anchorsPresent"], ["ResolveName"])
        self.assertIn("only ResolveName-like", summary["candidates"][0]["rejectionReason"])

    def test_generic_single_load_object_symbol_is_not_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "generic-symbols.map"
            candidate.write_text(
                "0000000001234000 T SomeNamespace::LoadObject(void*)\n",
                encoding="utf-8",
            )

            summary = module.search([root], "/tmp/target", max_depth=2)

        self.assertEqual(summary["candidateCount"], 1)
        self.assertEqual(summary["usableCandidateCount"], 0)
        self.assertFalse(summary["candidates"][0]["usable"])
        self.assertIn("single generic", summary["candidates"][0]["rejectionReason"])

    def test_source_tree_candidates_do_not_count_as_usable_binary_donors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Engine" / "Source" / "Runtime" / "CoreUObject" / "Public" / "UObject" / "UObjectGlobals.h"
            source.parent.mkdir(parents=True)
            source.write_text(
                "UObject* StaticLoadObject(UClass* ObjectClass, UObject* InOuter, const TCHAR* Name);\n"
                "UPackage* LoadPackage(UPackage* InOuter, const TCHAR* LongPackageName, uint32 LoadFlags);\n",
                encoding="utf-8",
            )

            summary = module.search([root], "/tmp/target", max_depth=6, source_max_depth=12)

        self.assertEqual(summary["candidateCount"], 0)
        self.assertEqual(summary["usableCandidateCount"], 0)
        self.assertEqual(summary["sourceCandidateCount"], 1)
        self.assertEqual(summary["sourceCandidates"][0]["mode"], "source")
        self.assertFalse(summary["sourceCandidates"][0]["usable"])
        self.assertIn("StaticLoadObject", summary["sourceCandidates"][0]["anchorsPresent"])
        self.assertIn("build the top source candidate", summary["nextStep"])

    def test_source_tree_scan_uses_separate_depth_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "UnrealEngine" / "Engine" / "Source" / "Runtime" / "CoreUObject" / "Public" / "UObject" / "UObjectGlobals.h"
            source.parent.mkdir(parents=True)
            source.write_text("UClass* StaticLoadClass(UClass* BaseClass, UObject* InOuter, const TCHAR* Name);\n", encoding="utf-8")

            shallow = module.search([root], "/tmp/target", max_depth=6)
            deep = module.search([root], "/tmp/target", max_depth=6, source_max_depth=12)

        self.assertEqual(shallow["sourceCandidateCount"], 0)
        self.assertEqual(deep["sourceCandidateCount"], 1)
        self.assertEqual(deep["sourceMaxDepth"], 12)
        self.assertIn("StaticLoadClass", deep["sourceCandidates"][0]["anchorsPresent"])

    def test_markdown_reports_no_candidates(self):
        summary = {
            "roots": ["/tmp/root"],
            "targetBinary": "/tmp/target",
            "candidateCount": 0,
            "usableCandidateCount": 0,
            "sourceCandidateCount": 0,
            "candidates": [],
            "sourceCandidates": [],
            "nextStep": "provide donor",
        }

        text = module.markdown(summary)

        self.assertIn("UE4SS Package Donor Search", text)
        self.assertIn("- none", text)
        self.assertIn("Source candidates: `0`", text)


if __name__ == "__main__":
    unittest.main()
