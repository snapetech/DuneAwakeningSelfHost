#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-function-neighborhoods.py"

spec = importlib.util.spec_from_file_location("summarize_elf_ue_function_neighborhoods", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ElfUeFunctionNeighborhoodTests(unittest.TestCase):
    def test_xref_seed_harvest_honors_category_and_name_filters(self):
        summary = {
            "targets": [
                {
                    "name": "GEngine",
                    "category": "ue",
                    "vaddr": "0x5000",
                    "xrefs": [{"xrefVaddr": "0x1000", "kind": "rip-memory"}],
                },
                {
                    "name": "PerformCanBePlaced",
                    "category": "building",
                    "vaddr": "0x6000",
                    "xrefs": [{"xrefVaddr": "0x2000", "kind": "rip-memory"}],
                },
                {
                    "name": "LoadAsset",
                    "category": "other",
                    "vaddr": "0x7000",
                    "xrefs": [{"xrefVaddr": "0x3000", "kind": "rip-memory"}],
                },
            ]
        }

        seeds = module.harvest_xref_summary_seeds(summary, 8, categories=["ue"], names=["GEngine"])

        self.assertEqual([seed.vaddr for seed in seeds], [0x1000])
        self.assertEqual(seeds[0].source_name, "GEngine@0x5000#1")
        self.assertEqual(seeds[0].source_group, "ue")

    def test_xref_seed_harvest_accepts_decimal_and_hex_addresses(self):
        summary = {
            "targets": [
                {
                    "name": "GEngine",
                    "category": "ue",
                    "xrefs": [
                        {"xrefVaddr": "4096", "kind": "rip-memory"},
                        {"xrefVaddr": "0x2000", "kind": "rip-memory"},
                    ],
                }
            ]
        }

        seeds = module.harvest_xref_summary_seeds(summary, 8)

        self.assertEqual([seed.vaddr for seed in seeds], [0x1000, 0x2000])

    def test_parse_explicit_seeds_accepts_named_and_unnamed_addresses(self):
        seeds = module.parse_explicit_seeds(["streamable=0xa721210", "4096"])

        self.assertEqual([seed.vaddr for seed in seeds], [0xA721210, 0x1000])
        self.assertEqual(seeds[0].source_name, "streamable")
        self.assertEqual(seeds[0].source_group, "explicit")
        self.assertEqual(seeds[0].source_role, "manual-seed")
        self.assertEqual(seeds[1].source_name, "explicit-4096")

    def test_writable_target_summary_preserves_exact_anchor_context(self):
        functions = [
            {
                "function": "0x1000",
                "sourceName": "seed",
                "refs": [
                    {
                        "instruction": "0x1010",
                        "target": "0x4000",
                        "section": ".bss",
                        "groups": ["objects"],
                        "exactAnchorHints": ["GUObjectArray"],
                        "symbols": [],
                        "string": "GUObjectArray",
                    }
                ],
            }
        ]

        rows = module.summarize_writable_targets(functions)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "0x4000")
        self.assertEqual(rows[0]["exactAnchorHintCounts"], {"GUObjectArray": 1})
        self.assertEqual(rows[0]["context"][0]["exactAnchorHints"], ["GUObjectArray"])
        self.assertEqual(rows[0]["context"][0]["groups"], ["objects"])

    def test_writable_target_summary_inherits_source_anchor_context(self):
        functions = [
            {
                "function": "0x1000",
                "sourceName": "GWorld@0x5000#1",
                "refs": [
                    {
                        "instruction": "0x1010",
                        "target": "0x4000",
                        "section": ".bss",
                        "groups": [],
                        "exactAnchorHints": [],
                        "symbols": [],
                        "string": "",
                    }
                ],
            }
        ]

        rows = module.summarize_writable_targets(functions)

        self.assertEqual(rows[0]["groups"], {"world": 1})
        self.assertEqual(rows[0]["exactAnchorHintCounts"], {"GWorld": 1})
        self.assertEqual(rows[0]["context"][0]["exactAnchorHints"], ["GWorld"])
        self.assertEqual(rows[0]["context"][0]["string"], "GWorld@0x5000#1")

    def test_exact_anchor_hints_use_token_boundaries(self):
        self.assertEqual(module.exact_anchor_hints("GUObjectArray"), ["GUObjectArray"])
        self.assertEqual(module.exact_anchor_hints("UObject"), ["UObject"])
        self.assertEqual(module.exact_anchor_hints("uobject-static-load-class"), ["StaticLoadClass"])
        self.assertEqual(module.exact_anchor_hints("load-asset-package-path"), ["LoadAsset"])
        self.assertEqual(module.exact_anchor_hints("LoadClass"), ["LoadClass"])


if __name__ == "__main__":
    unittest.main()
