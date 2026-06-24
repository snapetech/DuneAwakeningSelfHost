#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-callfunction-shape-candidates.py"
PTRCTX_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

spec = importlib.util.spec_from_file_location("callfunction_shape", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

ptr_spec = importlib.util.spec_from_file_location("ptrctx", PTRCTX_SCRIPT)
ptrctx = importlib.util.module_from_spec(ptr_spec)
assert ptr_spec.loader is not None
ptr_spec.loader.exec_module(ptrctx)

xref_spec = importlib.util.spec_from_file_location("xrefs", XREF_SCRIPT)
xrefs = importlib.util.module_from_spec(xref_spec)
assert xref_spec.loader is not None
xref_spec.loader.exec_module(xrefs)


class CallFunctionShapeCandidateTests(unittest.TestCase):
    def test_scores_five_arg_command_shape_and_keeps_non_promotable(self):
        data = bytearray(0x400)
        code_vaddr = 0x1000
        code_file = 0
        string_vaddr = 0x2000
        string_file = 0x200
        data[string_file : string_file + len(b"CallFunctionByNameWithArguments\0")] = b"CallFunctionByNameWithArguments\0"
        prefix = (
            b"\x55\x48\x89\xe5"
            b"\x45\x85\xc0"
            b"\x48\x8b\x06"
            b"\x48\x89\xd7"
            b"\x48\x89\xce"
            b"\x48\x89\xfa"
        )
        lea_size = 7
        lea_disp = string_vaddr - (code_vaddr + len(prefix) + lea_size)
        # push rbp; mov rbp,rsp; test r8d,r8d; mov rax,[rsi]; lea rcx,[rip+disp];
        # call rax; call rax; ret
        code = (
            prefix +
            b"\x48\x8d\x0d" + struct.pack("<i", lea_disp) +
            b"\xff\xd0"
            b"\xff\xd0"
            b"\xc3"
        )
        data[code_file : code_file + len(code)] = code
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, code_vaddr, code_file, 0x100, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, string_vaddr, string_file, 0x100, 0, 0),
        ]
        segments = [xrefs.Segment(code_file, 0x100, code_vaddr, 0x100, xrefs.PF_X)]

        row = module.analyze_function(ptrctx, xrefs, bytes(data), segments, sections, {}, code_vaddr, 64, 16)

        self.assertIsNotNone(row)
        self.assertGreaterEqual(row["score"], 55)
        self.assertEqual(row["argUses"]["forceCall"], 1)
        self.assertGreaterEqual(row["argUses"]["command"], 1)
        self.assertEqual(row["commandMemoryReads"], 1)
        self.assertEqual(row["indirectCallCount"], 2)
        self.assertIn("CallFunction", row["stringHints"])

    def test_narrowing_demotes_repeated_wrapper_shapes(self):
        unique = {
            "function": "0x1000",
            "score": 120,
            "usedArgCount": 5,
            "commandMemoryReads": 3,
            "branchCount": 8,
            "stringHints": ["Command"],
            "signature": {"sha256": "unique"},
            "directCalls": [{"target": "0x2000"}, {"target": "0x2100"}, {"target": "0x2200"}],
            "indirectCalls": [{"text": "call qword ptr [rax + 0x38]"}, {"text": "call qword ptr [rcx + 0x60]"}],
        }
        repeated_rows = []
        for index in range(10):
            repeated_rows.append(
                {
                    "function": f"0x3{index:03x}",
                    "score": 130,
                    "usedArgCount": 5,
                    "commandMemoryReads": 3,
                    "branchCount": 8,
                    "stringHints": [],
                    "signature": {"sha256": "repeat"},
                    "directCalls": [{"target": "0x4000"}],
                    "indirectCalls": [
                        {"text": "call qword ptr [rax + 0x150]"},
                        {"text": "call qword ptr [rax + 0x150]"},
                        {"text": "call qword ptr [rax + 0x158]"},
                        {"text": "call qword ptr [rax + 0x168]"},
                    ],
                }
            )

        rows = module.annotate_narrowing([unique, *repeated_rows])

        self.assertFalse(rows[0]["narrowing"]["promotable"])
        self.assertEqual(rows[1]["narrowing"]["signatureRepeatCount"], 10)
        self.assertTrue(rows[1]["narrowing"]["repeatedVtableShape"])
        self.assertGreater(rows[0]["narrowing"]["score"], rows[1]["narrowing"]["score"])

    def test_summary_is_not_promotable_without_runtime_validation(self):
        summary = {
            "binary": "server",
            "textSection": {"name": ".text", "addr": "0x1000", "size": "0x100"},
            "candidateCount": 1,
            "promotable": False,
            "promotionBlockers": ["shape candidates are static review leads only"],
            "candidates": [],
            "narrowedCandidates": [],
        }

        text = module.markdown(summary)

        self.assertIn("Promotable: `false`", text)
        self.assertIn("shape candidates are static review leads only", text)


if __name__ == "__main__":
    unittest.main()
