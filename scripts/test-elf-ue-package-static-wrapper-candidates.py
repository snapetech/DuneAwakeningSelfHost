#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-package-static-wrapper-candidates.py"

spec = importlib.util.spec_from_file_location("package_static_wrapper_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ElfUePackageStaticWrapperCandidateTests(unittest.TestCase):
    def test_package_string_rows_finds_source_and_api_needles(self):
        class Section:
            name = ".rodata"
            sh_type = 1
            flags = 0x2
            addr = 0x1000
            offset = 0
            size = 0x200

        data = b"prefix Runtime/CoreUObject/Private/UObject/UObjectGlobals.cpp\0LoadPackage\0"
        rows = module.package_string_rows(data, [Section()], module.PACKAGE_NEEDLES, 8)

        self.assertEqual(len(rows), 2)
        self.assertIn("UObjectGlobals", rows[0]["needles"])
        self.assertIn("CoreUObject", rows[0]["needles"])
        self.assertEqual(rows[0]["addressText"], "0x1000")
        self.assertIn("LoadPackage", rows[1]["needles"])

    def test_attach_demangled_typeinfo_rows_extracts_owner_function_candidates(self):
        rows = [
            {
                "text": (
                    "N2UE4Core7Private8Function27TFunction_UniqueOwnedObjectIZN10Dreamworld"
                    "28FTsomStreamableManagerLoader16RequestAsyncLoadEjRK15FSoftObjectPathE3$_0Lb1EEE"
                )
            }
        ]

        module.attach_demangled_typeinfo_rows(rows)

        self.assertIn("demangledTypeinfo", rows[0])
        self.assertIn(
            "Dreamworld::FTsomStreamableManagerLoader::RequestAsyncLoad",
            rows[0]["ownerFunctionCandidates"],
        )

    def test_attach_string_dataflow_follows_pointer_slot_code_refs(self):
        ptr_spec = importlib.util.spec_from_file_location(
            "ptrctx", ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
        )
        ptrctx = importlib.util.module_from_spec(ptr_spec)
        assert ptr_spec.loader is not None
        ptr_spec.loader.exec_module(ptrctx)
        xref_spec = importlib.util.spec_from_file_location(
            "xrefs", ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
        )
        xrefs = importlib.util.module_from_spec(xref_spec)
        assert xref_spec.loader is not None
        xref_spec.loader.exec_module(xrefs)

        data = bytearray(0x400)
        string_vaddr = 0x2000
        slot_vaddr = 0x3000
        code_vaddr = 0x1000
        data[0x200 : 0x200 + len(b"AsyncPackageLoader.cpp\0")] = b"AsyncPackageLoader.cpp\0"
        struct.pack_into("<Q", data, 0x300, string_vaddr)
        disp = slot_vaddr - (code_vaddr + 7)
        data[0:7] = b"\x48\x8d\x05" + struct.pack("<i", disp)
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, code_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, string_vaddr, 0x200, 0x80, 0, 0),
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC, slot_vaddr, 0x300, 0x80, 0, 0),
        ]
        segments = [xrefs.Segment(0, 0x80, code_vaddr, 0x80, xrefs.PF_X)]
        rows = [
            {
                "address": string_vaddr,
                "addressText": "0x2000",
                "section": ".rodata",
                "needles": ["AsyncPackageLoader"],
                "text": "AsyncPackageLoader.cpp",
            }
        ]

        module.attach_string_dataflow(ptrctx, xrefs, bytes(data), segments, sections, {}, rows, 8)

        self.assertEqual(rows[0]["pointerSlotCount"], 1)
        self.assertEqual(rows[0]["slotCodeRefCount"], 1)
        self.assertGreater(rows[0]["score"], 0)

    def test_attach_string_dataflow_classifies_source_diagnostic_direct_refs(self):
        ptr_spec = importlib.util.spec_from_file_location(
            "ptrctx", ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
        )
        ptrctx = importlib.util.module_from_spec(ptr_spec)
        assert ptr_spec.loader is not None
        ptr_spec.loader.exec_module(ptrctx)
        xref_spec = importlib.util.spec_from_file_location(
            "xrefs", ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
        )
        xrefs = importlib.util.module_from_spec(xref_spec)
        assert xref_spec.loader is not None
        xref_spec.loader.exec_module(xrefs)

        data = bytearray(0x400)
        string_vaddr = 0x2000
        code_vaddr = 0x1000
        data[0x200 : 0x200 + len(b"AsyncLoading2.cpp\0")] = b"AsyncLoading2.cpp\0"
        disp = string_vaddr - (code_vaddr + 7)
        data[0:7] = b"\x48\x8d\x0d" + struct.pack("<i", disp)
        data[7:12] = b"\xbe\x01\x00\x00\x00"
        data[12:18] = b"\x41\xb8\x34\x12\x00\x00"
        data[18:23] = b"\xe8\x11\x22\x33\x44"
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, code_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, string_vaddr, 0x200, 0x80, 0, 0),
        ]
        segments = [xrefs.Segment(0, 0x80, code_vaddr, 0x80, xrefs.PF_X)]
        rows = [
            {
                "address": string_vaddr,
                "addressText": "0x2000",
                "section": ".rodata",
                "needles": ["AsyncLoading2"],
                "text": "AsyncLoading2.cpp",
            }
        ]

        classifications = module.attach_string_dataflow(ptrctx, xrefs, bytes(data), segments, sections, {}, rows, 8)

        self.assertEqual(classifications, {"source-diagnostic-thunk": 1})
        self.assertEqual(rows[0]["directCodeRefs"][0]["classification"], "source-diagnostic-thunk")
        self.assertFalse(rows[0]["directCodeRefs"][0]["promotable"])

    def test_attach_string_dataflow_classifies_assertion_text_diagnostic_direct_refs(self):
        ptr_spec = importlib.util.spec_from_file_location(
            "ptrctx", ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
        )
        ptrctx = importlib.util.module_from_spec(ptr_spec)
        assert ptr_spec.loader is not None
        ptr_spec.loader.exec_module(ptrctx)
        xref_spec = importlib.util.spec_from_file_location(
            "xrefs", ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
        )
        xrefs = importlib.util.module_from_spec(xref_spec)
        assert xref_spec.loader is not None
        xref_spec.loader.exec_module(xrefs)

        data = bytearray(0x400)
        string_vaddr = 0x2000
        code_vaddr = 0x1000
        data[0x200 : 0x200 + len(b"IsAsyncLoading()\0")] = b"IsAsyncLoading()\0"
        disp = string_vaddr - (code_vaddr + 7)
        data[0:7] = b"\x48\x8d\x15" + struct.pack("<i", disp)
        data[7:12] = b"\xbe\x01\x00\x00\x00"
        data[12:18] = b"\x41\xb8\xd2\x04\x00\x00"
        data[18:23] = b"\xe8\x11\x22\x33\x44"
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, code_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, string_vaddr, 0x200, 0x80, 0, 0),
        ]
        segments = [xrefs.Segment(0, 0x80, code_vaddr, 0x80, xrefs.PF_X)]
        rows = [
            {
                "address": string_vaddr,
                "addressText": "0x2000",
                "section": ".rodata",
                "needles": ["AsyncLoading"],
                "text": "IsAsyncLoading()",
            }
        ]

        classifications = module.attach_string_dataflow(ptrctx, xrefs, bytes(data), segments, sections, {}, rows, 8)

        self.assertEqual(classifications, {"diagnostic-thunk": 1})
        self.assertEqual(rows[0]["directCodeRefs"][0]["classification"], "diagnostic-thunk")
        self.assertFalse(rows[0]["directCodeRefs"][0]["promotable"])

    def test_score_symbol_prioritizes_static_package_api_with_callers(self):
        row = {
            "address": 0x2000,
            "addressText": "0x2000",
            "symbol": "_Z17StaticLoadObjectv",
            "demangled": "StaticLoadObject()",
        }

        scored = module.score_symbol(row, {"directCallCount": 3, "sampleCallsites": ["0x1000"]})

        self.assertGreaterEqual(scored["score"], 13)
        self.assertIn("symbol:StaticLoadObject", scored["reasons"])
        self.assertIn("has-direct-callers", scored["reasons"])

    def test_executable_symbol_candidates_rejects_sdl_loadobject_false_positive(self):
        class Section:
            name = ".text"
            sh_type = 1
            flags = 0x6
            addr = 0x2000
            offset = 0
            size = 0x100

        rows = module.executable_symbol_candidates(
            [Section()],
            {0x2010: ["SDL_LoadObject"], 0x2020: ["_Z17StaticLoadObjectv"]},
            module.PACKAGE_NEEDLES,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "_Z17StaticLoadObjectv")

    def test_markdown_documents_promotion_rule(self):
        text = module.markdown(
            {
                "binary": "server",
                "needles": ["LoadPackage"],
                "stringHitCount": 1,
                "nonDynstrStringHitCount": 0,
                "executableSymbolCandidateCount": 0,
                "rankedSymbolCandidates": [],
                "stringsWithPointerSlots": 0,
                "stringsWithCodeRefs": 0,
                "stringsWithOwnerFunctionCandidates": 0,
                "directCodeRefClassifications": {},
                "packageStrings": [],
                "promotionRule": "Only promote after ABI proof.",
            }
        )

        self.assertIn("# ELF UE Package Static Wrapper Candidates", text)
        self.assertIn("Promotion rule", text)
        self.assertIn("- none", text)

    def test_markdown_includes_direct_code_ref_samples(self):
        text = module.markdown(
            {
                "binary": "server",
                "needles": ["AsyncLoading2"],
                "stringHitCount": 1,
                "nonDynstrStringHitCount": 1,
                "executableSymbolCandidateCount": 0,
                "rankedSymbolCandidates": [],
                "stringsWithPointerSlots": 0,
                "stringsWithCodeRefs": 1,
                "stringsWithOwnerFunctionCandidates": 0,
                "directCodeRefClassifications": {"unknown-direct-ref": 1},
                "packageStrings": [
                    {
                        "addressText": "0x5000",
                        "section": ".rodata",
                        "needles": ["AsyncLoading2"],
                        "score": 18,
                        "pointerSlotCount": 0,
                        "directCodeRefCount": 1,
                        "slotCodeRefCount": 0,
                        "directCodeRefs": [{"xref": "0x401234", "bytes": "48 8d 05"}],
                        "pointerSlots": [],
                        "text": "AsyncLoading2.cpp",
                    }
                ],
                "promotionRule": "Only promote after ABI proof.",
            }
        )

        self.assertIn("directCode=`0x401234`", text)
        self.assertIn("class=`unknown-direct-ref`", text)
        self.assertIn("bytes=`48 8d 05`", text)


if __name__ == "__main__":
    unittest.main()
