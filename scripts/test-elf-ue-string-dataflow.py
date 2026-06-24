#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-string-dataflow.py"
PTRCTX_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

spec = importlib.util.spec_from_file_location("summarize_elf_ue_string_dataflow", SCRIPT)
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


class ElfUeStringDataflowTests(unittest.TestCase):
    def test_follows_string_pointer_slot_to_nearby_writable_root(self):
        data = bytearray(0x500)
        code_file = 0x00
        code_vaddr = 0x1000
        string_file = 0x200
        string_vaddr = 0x2000
        table_file = 0x280
        table_vaddr = 0x3000
        writable_vaddr = 0x4000

        data[string_file : string_file + len(b"GUObjectArray\0")] = b"GUObjectArray\0"
        struct.pack_into("<Q", data, table_file, string_vaddr)

        lea_disp = table_vaddr - (code_vaddr + 7)
        mov_vaddr = code_vaddr + 7
        mov_disp = writable_vaddr - (mov_vaddr + 7)
        data[code_file : code_file + 14] = (
            b"\x48\x8d\x05" + struct.pack("<i", lea_disp) + b"\x48\x8b\x1d" + struct.pack("<i", mov_disp)
        )

        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, code_vaddr, code_file, 0x80, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, string_vaddr, string_file, 0x80, 0, 0),
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC, table_vaddr, table_file, 0x80, 0, 0),
            ptrctx.Section(".data", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, writable_vaddr, 0x300, 0x80, 0, 0),
        ]
        segments = [xrefs.Segment(code_file, 0x80, code_vaddr, 0x80, xrefs.PF_X)]
        target = {
            "name": "GUObjectArray",
            "value": string_vaddr,
            "valueText": "0x2000",
            "groups": ["objects"],
        }

        target["pointerSlots"] = module.pointer_slots_for_target(ptrctx, bytes(data), sections, {}, target)
        slot_refs = module.scan_code_refs_to_targets(xrefs, bytes(data), segments, [table_vaddr])
        module.attach_code_refs(xrefs, ptrctx, bytes(data), segments, sections, {}, [target], slot_refs, 32, 8)

        self.assertEqual(len(target["pointerSlots"]), 1)
        slot = target["pointerSlots"][0]
        self.assertEqual(slot["vaddrText"], "0x3000")
        self.assertEqual(slot["codeRefCount"], 1)
        self.assertEqual(slot["nearbyWritableTargetCounts"], {"0x4000": 1})
        self.assertEqual(slot["codeRefs"][0]["nearbyWritableRefs"][0]["section"], ".data")

        writable_targets = module.summarize_writable_targets([target])
        self.assertEqual(writable_targets[0]["target"], "0x4000")
        self.assertEqual(writable_targets[0]["exactAnchorHintCounts"], {"GUObjectArray": 1})
        self.assertEqual(writable_targets[0]["context"][0]["exactAnchorHints"], ["GUObjectArray"])
        self.assertEqual(writable_targets[0]["context"][0]["string"], "GUObjectArray")

    def test_load_targets_filters_ue_scan_rows(self):
        scan = {
            "targets": [
                {"name": "GUObjectArray", "category": "ue", "kind": "string", "vaddr": "0x2000"},
                {"name": "CheatManager", "category": "cheat", "kind": "string", "vaddr": "0x3000"},
            ]
        }

        rows = module.load_targets(scan, ["ue"], [])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "GUObjectArray")
        self.assertEqual(rows[0]["groups"], ["objects"])

    def test_load_targets_can_include_all_scan_categories(self):
        scan = {
            "targets": [
                {"name": "GUObjectArray", "category": "ue", "kind": "string", "vaddr": "0x2000"},
                {"name": "CheatManager", "category": "cheat", "kind": "string", "vaddr": "0x3000"},
            ]
        }

        rows = module.load_targets(scan, [], [])

        self.assertEqual([row["name"] for row in rows], ["GUObjectArray", "CheatManager"])

    def test_load_manual_targets_accepts_named_and_unnamed_addresses(self):
        rows = module.load_manual_targets(["CallFunctionByNameWithArguments=0x53790e6", "4096"])

        self.assertEqual([row["value"] for row in rows], [0x53790E6, 0x1000])
        self.assertEqual(rows[0]["name"], "CallFunctionByNameWithArguments")
        self.assertEqual(rows[0]["category"], "manual")
        self.assertEqual(rows[0]["kind"], "manual")
        self.assertEqual(rows[0]["groups"], ["dispatch"])
        self.assertEqual(rows[1]["name"], "manual-4096")

    def test_exact_anchor_aliases_include_package_loading(self):
        self.assertEqual(module.exact_anchor_hints("uobject-static-load-object"), ["StaticLoadObject"])
        self.assertEqual(module.exact_anchor_hints("uobject-static-load-class"), ["StaticLoadClass"])
        self.assertEqual(module.exact_anchor_hints("load-asset-package-path"), ["LoadAsset"])
        self.assertEqual(module.exact_anchor_hints("LoadClass"), ["LoadClass"])
        self.assertEqual(module.exact_anchor_hints("uobject-load-object"), ["LoadObject"])

    def test_markdown_distinguishes_source_and_emitted_target_counts(self):
        text = module.markdown(
            {
                "binary": "server",
                "sourceTargetCount": 77,
                "targetCount": 0,
                "reportedTargetCount": 0,
                "targetsWithCodeRefs": 0,
                "groupCounts": {},
                "writableTargetCount": 0,
                "writableTargets": [],
                "targets": [],
            }
        )

        self.assertIn("Source targets: `77`", text)
        self.assertIn("Emitted targets: `0`", text)


if __name__ == "__main__":
    unittest.main()
