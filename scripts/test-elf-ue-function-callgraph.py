#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-function-callgraph.py"

spec = importlib.util.spec_from_file_location("summarize_elf_ue_function_callgraph", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ElfUeFunctionCallgraphTests(unittest.TestCase):
    def test_parse_seed_accepts_named_and_unnamed_values(self):
        self.assertEqual(module.parse_seed("streamable=0xa721210"), ("streamable", 0xA721210))
        self.assertEqual(module.parse_seed("4096"), ("seed-4096", 4096))

    def test_hint_classification_distinguishes_package_and_streamable(self):
        class Section:
            name = ".rodata"

        class Ptrctx:
            @staticmethod
            def section_for_addr(_sections, _target):
                return Section()

            @staticmethod
            def printable_hint(_data, _sections, _target):
                return "Dreamworld::FTsomStreamableManagerLoader::RequestAsyncLoad StaticLoadObject"

        hint = module.hint_for(Ptrctx, b"", [], {}, 0x1000)

        self.assertEqual(hint["packageAnchorHints"], ["StaticLoadObject"])
        self.assertEqual(hint["streamableHints"], ["RequestAsyncLoad"])

    def test_summary_blocks_streamable_only_promotion(self):
        summary = {
            "seeds": [{"name": "streamable", "vaddr": "0x1000"}],
            "depth": 1,
            "nodeCount": 1,
            "edgeCount": 0,
            "packageAnchorNodeCount": 0,
            "streamableNodeCount": 1,
            "promotableAsPackageAnchor": False,
            "promotionBlockers": ["no direct package anchor hints in bounded direct-call graph"],
            "nodes": [
                {
                    "function": "0x1000",
                    "depth": 0,
                    "instructionCount": 3,
                    "directCallCount": 0,
                    "indirectCallCount": 1,
                    "packageAnchorHintCounts": {},
                    "streamableHintCounts": {"Streamable": 1},
                    "refs": [],
                    "calls": [],
                    "indirectCalls": [
                        {
                            "instruction": "0x1001",
                            "kind": "indirect-call",
                            "target": "",
                            "section": "",
                            "symbols": [],
                            "string": "",
                            "text": "call qword ptr [rax + 0x10]",
                        }
                    ],
                }
            ],
        }

        text = module.markdown(summary, 10)

        self.assertIn("Promotable as package anchor: `false`", text)
        self.assertIn("Package anchor nodes: `0`", text)
        self.assertIn("call qword ptr [rax + 0x10]", text)

    def test_analyze_node_reports_rip_memory_indirect_call(self):
        xref_spec = importlib.util.spec_from_file_location(
            "xrefs", ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
        )
        xrefs = importlib.util.module_from_spec(xref_spec)
        assert xref_spec.loader is not None
        xref_spec.loader.exec_module(xrefs)

        ptr_spec = importlib.util.spec_from_file_location(
            "ptrctx", ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
        )
        ptrctx = importlib.util.module_from_spec(ptr_spec)
        assert ptr_spec.loader is not None
        ptr_spec.loader.exec_module(ptrctx)

        data = bytearray(0x400)
        text_vaddr = 0x1000
        table_vaddr = 0x2000
        disp = table_vaddr - (text_vaddr + 6)
        data[0:7] = b"\xff\x15" + struct.pack("<i", disp) + b"\xc3"
        data[0x200:0x20d] = b"LoadPackage\x00"
        segments = [xrefs.Segment(0, 0x100, text_vaddr, 0x100, xrefs.PF_X)]
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x100, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, table_vaddr, 0x200, 0x100, 0, 0),
        ]

        node = module.analyze_node(ptrctx, xrefs, bytes(data), segments, sections, {}, text_vaddr, 8)

        self.assertEqual(node["indirectCallCount"], 1)
        self.assertEqual(node["indirectCalls"][0]["target"], "0x2000")
        self.assertEqual(node["indirectCalls"][0]["packageAnchorHints"], ["LoadPackage"])


if __name__ == "__main__":
    unittest.main()
