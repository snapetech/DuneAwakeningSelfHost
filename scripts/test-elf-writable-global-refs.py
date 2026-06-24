#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-writable-global-refs.py"

spec = importlib.util.spec_from_file_location("summarize_elf_writable_global_refs", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ElfWritableGlobalRefsTests(unittest.TestCase):
    def load_xrefs(self):
        spec = importlib.util.spec_from_file_location(
            "xrefs", ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
        )
        xrefs = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(xrefs)
        return xrefs

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
        self.assertEqual(module.exact_anchor_hints("uobject-static-load-object"), ["StaticLoadObject"])
        self.assertEqual(module.exact_anchor_hints("uobject-static-load-class"), ["StaticLoadClass"])
        self.assertEqual(module.exact_anchor_hints("load-asset-package-path"), ["LoadAsset"])
        self.assertEqual(module.exact_anchor_hints("LoadClass"), ["LoadClass"])
        self.assertEqual(module.exact_anchor_hints("uobject-load-object"), ["LoadObject"])
        self.assertEqual(module.exact_anchor_hints("LoadPackage"), ["LoadPackage"])
        self.assertEqual(module.classify_text("ResolveName"), ["package"])

    def test_exact_anchor_aliases_include_root_and_reflection_aliases(self):
        self.assertEqual(module.exact_anchor_hints("NamePoolData"), ["FNamePool", "NamePoolData"])
        self.assertEqual(module.exact_anchor_hints("FUObjectArray"), ["GUObjectArray", "FUObjectArray"])
        self.assertEqual(module.exact_anchor_hints("GEngine"), ["GEngine"])
        self.assertEqual(module.exact_anchor_hints("UStruct"), ["UStruct"])

    def test_parse_target_args_accepts_names_and_hex_values(self):
        self.assertEqual(module.parse_target_args(["foo=0x2000", "0x1000", "bar=8192"]), [0x1000, 0x2000])

    def test_scan_refs_to_targets_filters_exact_rip_memory_targets(self):
        xrefs = self.load_xrefs()
        data = bytearray(0x80)
        base = 0x1000
        target = 0x2000
        instr = b"\x48\x8b\x05" + struct.pack("<i", target - (base + 7))
        data[: len(instr)] = instr
        data[0x20 : 0x20 + len(instr)] = b"\x48\x8b\x05" + struct.pack("<i", 0x3000 - (base + 0x20 + 7))
        segments = [xrefs.Segment(0, len(data), base, len(data), xrefs.PF_X)]

        refs = module.scan_refs_to_targets(xrefs, bytes(data), segments, [target])

        self.assertEqual(list(refs), [target])
        self.assertEqual(refs[target][0]["xrefVaddr"], base)


if __name__ == "__main__":
    unittest.main()
