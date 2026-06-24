#!/usr/bin/env python3
import importlib.util
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-elf-ue-package-loader-vtables.py"

spec = importlib.util.spec_from_file_location("summarize_elf_ue_package_loader_vtables", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ElfUePackageLoaderVtableTests(unittest.TestCase):
    def test_strip_symbol_suffix_removes_loader_added_size(self):
        self.assertEqual("_ZTV11FLinkerLoad", module.strip_symbol_suffix("_ZTV11FLinkerLoad size=0x330"))

    def test_source_file_hint_accepts_package_loader_source_paths(self):
        self.assertEqual(
            ".\\Runtime\\CoreUObject\\Private\\Serialization\\AsyncPackageLoader.cpp",
            module.source_file_hint(
                {"string": ".\\Runtime\\CoreUObject\\Private\\Serialization\\AsyncPackageLoader.cpp"}
            ),
        )
        self.assertEqual("", module.source_file_hint({"string": "FAsyncPackage2"}))

    def test_function_shape_flags_trap_and_constant_zero(self):
        class Section:
            addr = 0x1000
            offset = 0
            size = 0x100
            sh_type = 1

        trap = b"\x55\x48\x89\xe5\x0f\x0b" + b"\xcc" * 16
        self.assertTrue(module.function_shape(trap, [Section()], 0x1000)["hasUd2"])
        zero = b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3" + b"\xcc" * 16
        self.assertTrue(module.function_shape(zero, [Section()], 0x1000)["returnsConstantZero"])
        vtable_reset = b"\x55\x48\x89\xe5\x48\x8d\x05\x11\x22\x33\x44\x48\x89\x07" + b"\xcc" * 16
        self.assertTrue(module.function_shape(vtable_reset, [Section()], 0x1000)["writesVtableToThis"])
        control = b"\x55\x48\x89\xe5\xe8\x11\x22\x33\x44\xe9\x55\x66\x77\x88" + b"\xcc" * 16
        shape = module.function_shape(control, [Section()], 0x1000)
        self.assertTrue(shape["hasCall"])
        self.assertTrue(shape["hasJump"])
        self.assertTrue(shape["hasControlTransfer"])
        self.assertEqual(shape["callOpcodeCount"], 1)
        self.assertEqual(shape["jumpOpcodeCount"], 1)

    def test_markdown_lists_executable_slots(self):
        text = module.markdown(
            {
                "binary": "server",
                "vtableCount": 1,
                "executableSlotCount": 1,
                "classFilters": ["FAsyncPackage2"],
                "explicitAddresses": ["streamable=0x149f36f0"],
                "rows": [
                    {
                        "demangled": "vtable for FAsyncPackage2",
                        "vtable": "0x1000",
                        "executableSlotCount": 1,
                        "sourceHints": ["AsyncPackageLoader.cpp"],
                        "executableSlots": [
                            {
                                "index": 2,
                                "value": "0x2000",
                                "section": ".text",
                                "candidateKind": "method",
                                "signature": {"fileOffset": "0x2000", "sha256": "abcdef0123456789"},
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn("vtable for FAsyncPackage2", text)
        self.assertIn("streamable=0x149f36f0", text)
        self.assertIn("target=`0x2000`", text)
        self.assertIn("sha256=`abcdef0123456789`", text)

    def test_no_default_class_filters_keeps_explicit_addresses_only(self):
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(b"\0" * 16)
            handle.flush()
            original_import = module.import_script
            original_summarize_vtable = module.summarize_vtable

            class Ptrctx:
                @staticmethod
                def load_sections(_data):
                    return []

                @staticmethod
                def load_relocations(_data, _sections):
                    return {}

                @staticmethod
                def load_symbols(_data, _sections):
                    return {}

            try:
                module.import_script = lambda _path, _name: Ptrctx
                module.summarize_vtable = lambda *_args: {
                    "vtable": "0x3000",
                    "demangled": "reviewed",
                    "executableSlotCount": 0,
                    "sourceHints": [],
                    "executableSlots": [],
                    "slots": [],
                }
                summary = module.summarize(
                    types.SimpleNamespace(
                        binary=Path(handle.name),
                        address=["reviewed=0x3000"],
                        class_filter=[],
                        no_default_class_filters=True,
                        max_slots=4,
                        signature_length=8,
                        limit=8,
                    )
                )
            finally:
                module.import_script = original_import
                module.summarize_vtable = original_summarize_vtable

        self.assertEqual(summary["classFilters"], [])
        self.assertEqual(summary["explicitAddresses"], ["reviewed=0x3000"])
        self.assertEqual(summary["vtableCount"], 1)


if __name__ == "__main__":
    unittest.main()
