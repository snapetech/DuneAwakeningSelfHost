#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-writable-global-refs.py"

spec = importlib.util.spec_from_file_location("summarize_elf_writable_global_refs", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ElfWritableGlobalRefsTests(unittest.TestCase):
    def test_context_ranking_prefers_exact_anchor_hints(self):
        rows = [
            {
                "xref": "0x100",
                "target": "0x5000",
                "groups": [],
                "exactAnchorHints": [],
                "symbols": ["UnrelatedSymbol"],
                "string": "",
            },
            {
                "xref": "0x200",
                "target": "0x6000",
                "groups": ["objects"],
                "exactAnchorHints": [],
                "symbols": [],
                "string": "Runtime/CoreUObject/Public\\UObject/Class.h",
            },
            {
                "xref": "0x300",
                "target": "0x7000",
                "groups": ["objects"],
                "exactAnchorHints": ["GUObjectArray"],
                "symbols": [],
                "string": "GUObjectArray",
            },
        ]

        ranked = module.rank_context_rows(rows)

        self.assertEqual(ranked[0]["exactAnchorHints"], ["GUObjectArray"])
        self.assertEqual(ranked[1]["groups"], ["objects"])
        self.assertEqual(ranked[2]["symbols"], ["UnrelatedSymbol"])

    def test_exact_anchor_aliases_include_package_loading(self):
        self.assertEqual(module.exact_anchor_hints("StaticLoadObject"), ["StaticLoadObject"])
        self.assertEqual(module.exact_anchor_hints("LoadPackage"), ["LoadPackage"])
        self.assertEqual(module.classify_text("ResolveName"), ["package"])

    def test_exact_anchor_aliases_include_root_and_reflection_aliases(self):
        self.assertEqual(module.exact_anchor_hints("NamePoolData"), ["FNamePool", "NamePoolData"])
        self.assertEqual(module.exact_anchor_hints("FUObjectArray"), ["GUObjectArray", "FUObjectArray"])
        self.assertEqual(module.exact_anchor_hints("GEngine"), ["GEngine"])
        self.assertEqual(module.exact_anchor_hints("UStruct"), ["UStruct"])


if __name__ == "__main__":
    unittest.main()
