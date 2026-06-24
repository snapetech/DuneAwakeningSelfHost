#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-package-wrapper-candidates.py"


class ElfUePackageWrapperCandidateTests(unittest.TestCase):
    def test_script_source_documents_wrapper_not_vtable_promotion(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("promote only a proven wrapper/static package-loading ABI", source)
        self.assertIn("candidateKind", source)
        self.assertIn("call_targets_in_section", source)
        self.assertIn("objdump_direct_calls", source)
        self.assertIn("--raw-scan", source)

    def test_markdown_empty_callsite_report(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("package_wrapper_candidates", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = module.markdown(
            {
                "binary": "/tmp/server",
                "packageLoaderVTables": "pkg.json",
                "methodTargetCount": 2,
                "targetsWithDirectCalls": 0,
                "directCallsiteCount": 0,
                "callsiteConfirmation": "objdump",
                "targetRanked": [],
                "nonPromotableWithoutWrapperReason": "reason",
                "callsiteRanked": [],
            }
        )
        self.assertIn("# ELF UE Package Wrapper Candidates", text)
        self.assertIn("- Direct callsites: `0`", text)
        self.assertIn("- Callsite confirmation: `objdump`", text)
        self.assertIn("- none", text)

    def test_collect_package_method_targets_reads_real_rows_shape(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("package_wrapper_candidates", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = module.collect_package_method_targets(
            {
                "rows": [
                    {
                        "demangled": "vtable for FAsyncPackage2",
                        "executableSlots": [
                            {"index": 66, "value": "0xfa7a630", "candidateKind": "method"},
                            {"index": 67, "value": "0xfa7a680", "candidateKind": "trap"},
                        ],
                    }
                ]
            },
            48,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], 0xFA7A630)
        self.assertEqual(rows[0]["slot"], 66)

    def test_collect_package_method_targets_supports_vtable_and_slot_filters(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("package_wrapper_candidates", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = module.collect_package_method_targets(
            {
                "rows": [
                    {
                        "demangled": "vtable for FAsyncPackage2",
                        "executableSlots": [
                            {"index": 66, "value": "0xfa7a630", "candidateKind": "method"},
                            {"index": 94, "value": "0xf95a050", "candidateKind": "method"},
                        ],
                    },
                    {
                        "demangled": "vtable for FLinkerLoad",
                        "executableSlots": [
                            {"index": 53, "value": "0xf9461a0", "candidateKind": "method"},
                        ],
                    },
                ]
            },
            48,
            ["FAsyncPackage2"],
            ["94"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], 0xF95A050)
        self.assertEqual(rows[0]["slot"], 94)

    def test_fixture_json_is_valid_for_future_cli_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package-vtables.json"
            payload = {
                "schemaVersion": "dune-elf-ue-package-loader-vtables/v1",
                "rows": [
                    {
                        "demangled": "vtable for FAsyncPackage",
                        "executableSlots": [
                            {"index": 4, "value": "0x1000", "candidateKind": "method"},
                        ],
                    }
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["rows"][0]["executableSlots"][0]["candidateKind"], "method")


if __name__ == "__main__":
    unittest.main()
