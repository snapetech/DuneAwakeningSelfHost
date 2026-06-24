#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-rtti-function-object-vtables.py"

spec = importlib.util.spec_from_file_location("rtti_function_object_vtables", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class RttiFunctionObjectVtableTests(unittest.TestCase):
    def load_ptrctx(self):
        ptr_spec = importlib.util.spec_from_file_location(
            "ptrctx", ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
        )
        ptrctx = importlib.util.module_from_spec(ptr_spec)
        assert ptr_spec.loader is not None
        ptr_spec.loader.exec_module(ptrctx)
        return ptrctx

    def test_row_typeinfo_name_slots_uses_data_rel_ro_slots_only(self):
        row = {
            "pointerSlots": [
                {"address": "0x2008", "section": ".data.rel.ro"},
                {"address": "0x1000", "section": ".rela.dyn"},
                {"address": "0x2008", "section": ".data.rel.ro"},
            ]
        }

        self.assertEqual(module.row_typeinfo_name_slots(row), [0x2008])

    def test_executable_slots_after_stops_at_non_executable_value(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x400)
        text_vaddr = 0x1000
        ro_vaddr = 0x2000
        table_vaddr = 0x3000
        data[0:8] = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3"
        data[8:16] = b"\x55\x48\x89\xe5\x90\x90\x5d\xc3"
        struct.pack_into("<Q", data, 0x200, text_vaddr)
        struct.pack_into("<Q", data, 0x208, text_vaddr + 8)
        struct.pack_into("<Q", data, 0x210, ro_vaddr)
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, ro_vaddr, 0x100, 0x80, 0, 0),
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, table_vaddr, 0x200, 0x80, 0, 0),
        ]

        slots = module.executable_slots_after(ptrctx, bytes(data), sections, {}, {}, table_vaddr - 8, 8, 8, 64)

        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0]["candidateKind"], "trivial")
        self.assertEqual(slots[1]["candidateKind"], "method")

    def test_direct_control_targets_extracts_relative_calls(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x200)
        text_vaddr = 0x1000
        call_source = text_vaddr
        call_target = text_vaddr + 0x40
        rel = call_target - (call_source + 5)
        data[0:5] = b"\xe8" + struct.pack("<i", rel)
        data[0x40 : 0x48] = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3"
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x100, 0, 0),
        ]

        calls = module.direct_control_targets(ptrctx, bytes(data), sections, {}, text_vaddr, 16)

        self.assertEqual(calls[0]["opcode"], "call")
        self.assertEqual(calls[0]["source"], "0x1000")
        self.assertEqual(calls[0]["target"], "0x1040")

    def test_direct_control_targets_stops_at_ret_before_adjacent_function(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x200)
        text_vaddr = 0x1000
        data[0:8] = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3"
        call_source = text_vaddr + 0x10
        call_target = text_vaddr + 0x40
        rel = call_target - (call_source + 5)
        data[0x10:0x15] = b"\xe8" + struct.pack("<i", rel)
        data[0x40 : 0x48] = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3"
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x100, 0, 0),
        ]

        calls = module.direct_control_targets(ptrctx, bytes(data), sections, {}, text_vaddr, 64)

        self.assertEqual(calls, [])

    def test_qword_ref_addrs_includes_relocation_refs(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x300)
        struct.pack_into("<Q", data, 0x100, 0x2000)
        sections = [
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, 0x3000, 0x100, 0x80, 0, 0),
        ]

        refs = module.qword_ref_addrs(ptrctx, bytes(data), sections, {0x3010: 0x2000}, 0x2000)

        self.assertEqual(refs, [0x3000, 0x3010])

    def test_classify_owner_lead_marks_streamable_request_non_promotable(self):
        result = module.classify_owner_lead(
            ["Dreamworld::FTsomStreamableManagerLoader::RequestAsyncLoad"],
            (
                "typeinfo name for TFunction<Dreamworld::FTsomStreamableManagerLoader::RequestAsyncLoad("
                "unsigned int, FSoftObjectPath const&, TSharedPtr<FStreamableHandle> const&, UObject*)>"
            ),
        )

        self.assertEqual(result["leadKind"], "streamable-request")
        self.assertIn("owner-request-async-load", result["leadReasons"])
        self.assertIn("soft-object-path-argument", result["leadReasons"])
        self.assertIn("streamable-handle-callback", result["leadReasons"])
        self.assertIn("uobject-callback", result["leadReasons"])
        self.assertFalse(result["promotableAsPackageAnchor"])
        self.assertTrue(result["promotionBlockers"])

    def test_classify_owner_lead_marks_try_load_object_owner_non_promotable(self):
        result = module.classify_owner_lead(
            ["ALandscapeTileGizmoActor::TryLoadObjectImplementation"],
            (
                "typeinfo name for UE::Core::Private::Function::TFunction_CopyableOwnedObject<"
                "ALandscapeTileGizmoActor::TryLoadObjectImplementation(bool)::$_0, false>"
            ),
        )

        self.assertEqual(result["leadKind"], "loadobject-owner-method")
        self.assertIn("owner-try-load-object-implementation", result["leadReasons"])
        self.assertIn("load-object-name-present", result["leadReasons"])
        self.assertFalse(result["promotableAsPackageAnchor"])
        self.assertIn("gameplay/object-specific", " ".join(result["promotionBlockers"]))

    def test_classify_owner_lead_marks_load_asset_surface_non_promotable(self):
        result = module.classify_owner_lead(
            ["vtable for FLoadAssetActionBase"],
            "typeinfo for FVehicleModuleUtils::LoadAssetsAndAddLoadoutOperation",
        )

        self.assertEqual(result["leadKind"], "loadasset-owner-surface")
        self.assertIn("load-asset-name-present", result["leadReasons"])
        self.assertFalse(result["promotableAsPackageAnchor"])
        self.assertIn("StaticLoadObject", " ".join(result["promotionBlockers"]))

    def test_classify_owner_lead_marks_async_package_completion_delegate_non_promotable(self):
        result = module.classify_owner_lead(
            ["vtable for TBaseRawMethodDelegateInstance<false, FNetGUIDCache, void (FName const&, UPackage*, EAsyncLoadingResult::Type)>"],
            "",
        )

        self.assertEqual(result["leadKind"], "async-package-completion-delegate")
        self.assertIn("upackage-callback", result["leadReasons"])
        self.assertIn("async-loading-result-callback", result["leadReasons"])
        self.assertFalse(result["promotableAsPackageAnchor"])
        self.assertIn("callback surface", " ".join(result["promotionBlockers"]))

    def test_classify_owner_lead_marks_package_loader_owner_function_non_promotable(self):
        result = module.classify_owner_lead(
            ["typeinfo name for UE::Core::Private::Function::TFunction_CopyableOwnedObject<FAsyncPackage::CreateLinker()::$_0, false>"],
            "",
        )

        self.assertEqual(result["leadKind"], "package-loader-owner-function")
        self.assertIn("package-loader-owner", result["leadReasons"])
        self.assertFalse(result["promotableAsPackageAnchor"])
        self.assertIn("lifecycle/linker plumbing", " ".join(result["promotionBlockers"]))

    def test_symbol_surface_package_leads_uses_rtti_vtable_rows(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x400)
        text_vaddr = 0x1000
        vtable_vaddr = 0x3000
        data[0:8] = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3"
        struct.pack_into("<Q", data, 0x208, 0x2000)
        struct.pack_into("<Q", data, 0x210, text_vaddr)
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, vtable_vaddr, 0x200, 0x80, 0, 0),
        ]
        source = {
            "rows": [
                {
                    "role": "rtti-vtable",
                    "groups": ["package"],
                    "falsePositive": False,
                    "value": vtable_vaddr,
                    "demangled": "vtable for FLoadAssetActionBase",
                }
            ]
        }

        leads = module.symbol_surface_package_leads(ptrctx, bytes(data), sections, {}, source)

        self.assertEqual(leads[0]["owners"], ["vtable for FLoadAssetActionBase"])
        self.assertEqual(leads[0]["vtableRefSlots"], [vtable_vaddr + 8])

    def test_symbol_surface_package_leads_accepts_explicit_needles(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x400)
        text_vaddr = 0x1000
        vtable_vaddr = 0x3000
        struct.pack_into("<Q", data, 0x208, 0x2000)
        struct.pack_into("<Q", data, 0x210, text_vaddr)
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, vtable_vaddr, 0x200, 0x80, 0, 0),
        ]
        source = {
            "rows": [
                {
                    "role": "rtti-vtable",
                    "groups": ["names"],
                    "falsePositive": False,
                    "value": vtable_vaddr,
                    "demangled": "vtable for TBaseRawMethodDelegateInstance<void (FName const&, UPackage*, EAsyncLoadingResult::Type)>",
                }
            ]
        }

        self.assertEqual(module.symbol_surface_package_leads(ptrctx, bytes(data), sections, {}, source), [])
        leads = module.symbol_surface_package_leads(ptrctx, bytes(data), sections, {}, source, ["UPackage*"])

        self.assertEqual(leads[0]["vtableRefSlots"], [vtable_vaddr + 8])

    def test_raw_typeinfo_name_leads_follow_name_slot_to_vtable(self):
        ptrctx = self.load_ptrctx()
        data = bytearray(0x500)
        text_vaddr = 0x1000
        ro_vaddr = 0x2000
        table_vaddr = 0x3000
        raw_name = b"N11FLinkerLoad12CreateLinkerE3$_0\x00"
        data[0:8] = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3"
        data[0x100 : 0x100 + len(raw_name)] = raw_name
        typeinfo_object = table_vaddr
        name_slot = table_vaddr + 8
        vtable_ref_slot = table_vaddr + 0x20
        struct.pack_into("<Q", data, 0x200, 0)
        struct.pack_into("<Q", data, 0x208, ro_vaddr)
        struct.pack_into("<Q", data, 0x220, typeinfo_object)
        struct.pack_into("<Q", data, 0x228, text_vaddr)
        sections = [
            ptrctx.Section(".text", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_EXECINSTR, text_vaddr, 0, 0x80, 0, 0),
            ptrctx.Section(".rodata", 1, ptrctx.SHF_ALLOC, ro_vaddr, 0x100, 0x80, 0, 0),
            ptrctx.Section(".data.rel.ro", 1, ptrctx.SHF_ALLOC | ptrctx.SHF_WRITE, table_vaddr, 0x200, 0x100, 0, 0),
        ]

        leads = module.raw_typeinfo_name_leads(ptrctx, bytes(data), sections, {}, ["FLinkerLoad", "CreateLinker"])

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["addressText"], "0x2000")
        self.assertEqual(leads[0]["typeinfoObject"], f"0x{typeinfo_object:x}")
        self.assertEqual(leads[0]["typeinfoNameSlot"], f"0x{name_slot:x}")
        self.assertEqual(leads[0]["vtableRefSlots"], [vtable_ref_slot])

    def test_candidate_kind_marks_delete_call_as_deleting_destructor(self):
        kind = module.candidate_kind(
            {},
            {"hasCall": True},
            [{"symbols": ["_ZdlPvm size=0xb"]}],
        )

        self.assertEqual(kind, "deleting-destructor")

    def test_build_callgraph_seeds_dedupes_targets_and_formats_seed_args(self):
        rows = [
            {
                "leadKind": "package-loader-owner-function",
                "owners": ["owner"],
                "vtables": [
                    {
                        "slots": [
                            {"index": 0, "candidateKind": "method", "target": "0x1000"},
                            {"index": 1, "candidateKind": "function-object-dispatch", "target": "0x1010"},
                            {"index": 2, "candidateKind": "deleting-destructor", "target": "0x1020"},
                        ]
                    }
                ],
            },
            {
                "leadKind": "package-loader-owner-function",
                "owners": ["owner2"],
                "vtables": [{"slots": [{"index": 0, "candidateKind": "method", "target": "0x1000"}]}],
            },
        ]

        seeds = module.build_callgraph_seeds(rows, [], 8)

        self.assertEqual([seed["target"] for seed in seeds], ["0x1000", "0x1010"])
        self.assertIn("--seed rtti0_vt0_slot0_method=0x1000", module.seed_args({"callgraphSeeds": seeds}))
        self.assertIn("--seed rtti0_vt0_slot1_function_object_dispatch=0x1010", module.seed_args({"callgraphSeeds": seeds}))


if __name__ == "__main__":
    unittest.main()
