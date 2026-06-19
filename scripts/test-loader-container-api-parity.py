#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOADER_SOURCE_CANDIDATES = {
    "linux-client": (
        ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
        ROOT / "src" / "dune_client_probe_loader.c",
    ),
    "linux-server": (
        ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
        ROOT / "src" / "dune_server_probe_loader.c",
    ),
    "windows-client": (
        ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
        ROOT / "src" / "dune_win_client_probe_loader.c",
    ),
}

DOCS = (
    ROOT / "docs" / "client-loader-support.md",
    ROOT / "docs" / "linux-client-loader.md",
    ROOT / "docs" / "windows-client-loader.md",
    ROOT / "docs" / "ue4ss-linux-loader-evaluation.md",
)

FULL_LUA_SMOKES = {
    "linux-client": ROOT / "scripts" / "smoke-linux-client-loader.sh",
    "linux-server": ROOT / "scripts" / "smoke-linux-server-loader.sh",
    "windows-client": ROOT / "scripts" / "smoke-windows-client-loader-lua.sh",
}


class LoaderContainerApiParityTests(unittest.TestCase):
    def existing_sources(self):
        sources = {}
        for target, candidates in LOADER_SOURCE_CANDIDATES.items():
            source = next((candidate for candidate in candidates if candidate.exists()), None)
            if source is not None:
                sources[target] = source
        self.assertGreaterEqual(len(sources), 1)
        return sources

    def existing_docs(self):
        docs = tuple(doc for doc in DOCS if doc.exists())
        self.assertGreaterEqual(len(docs), 1)
        return docs

    def existing_full_lua_smokes(self):
        smokes = {
            target: smoke
            for target, smoke in FULL_LUA_SMOKES.items()
            if smoke.exists()
        }
        self.assertGreaterEqual(len(smokes), 1)
        return smokes

    def test_all_targets_expose_set_and_map_header_metadata(self):
        required = (
            "element_name",
            "element_type",
            "element_class_name",
            "element_size",
            "key_name",
            "key_type",
            "key_class_name",
            "key_size",
            "value_name",
            "value_type",
            "value_class_name",
            "value_size",
            '"ElementName"',
            '"ElementType"',
            '"ElementClassName"',
            '"ElementElementSize"',
            '"KeyName"',
            '"KeyType"',
            '"KeyClassName"',
            '"KeyElementSize"',
            '"ValueName"',
            '"ValueType"',
            '"ValueClassName"',
            '"ValueElementSize"',
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_bind_set_and_map_raw_accessors(self):
        required = (
            "lua_param_descriptor_is_set(descriptor)",
            "lua_param_descriptor_is_map(descriptor)",
            "lua_script_set_get_element_callback",
            "lua_script_map_get_pair_callback",
            "lua_script_container_get_storage_layout_callback",
            "lua_script_container_is_sparse_layout_validated_callback",
            "lua_script_container_get_slot_stride_callback",
            '"GetNum"',
            '"NumElements"',
            '"GetData"',
            '"GetRawElement"',
            '"GetRawEntry"',
            '"GetRawPair"',
            '"GetElement"',
            '"GetPair"',
            '"GetStorageLayout"',
            '"IsSparseLayoutValidated"',
            '"GetSlotStride"',
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_promote_container_child_roles(self):
        required = (
            '"inner"',
            '"element"',
            '"key"',
            '"value"',
            "out->inner_class_name",
            "out->element_class_name",
            "out->key_class_name",
            "out->value_class_name",
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_decode_typed_container_elements(self):
        required = (
            "push_lua_container_scalar_or_raw",
            "push_live_ue_reflection_fstring_value_or_nil",
            "push_lua_fvector_table",
            'contains_ci(inner_class_name, "StrProperty")',
            'contains_ci(inner_class_name, "TextProperty")',
            'contains_ci(inner_class_name, "StructProperty")',
            'contains_ci(class_name, "StrProperty")',
            'contains_ci(class_name, "TextProperty")',
            'contains_ci(class_name, "StructProperty")',
            "sizeof(UeFStringValue)",
            "sizeof(UeFVectorValue)",
        )
        exact_string_markers = {
            "linux-client": ('strcmp(inner_type, "string") == 0', 'strcmp(type, "string") == 0'),
            "linux-server": ('strcmp(inner_type, "string") == 0', 'strcmp(type, "string") == 0'),
            "windows-client": ('str_equal(inner_type, "string")', 'str_equal(type, "string")'),
        }
        exact_text_markers = {
            "linux-client": ('strcmp(inner_type, "text") == 0', 'strcmp(type, "text") == 0'),
            "linux-server": ('strcmp(inner_type, "text") == 0', 'strcmp(type, "text") == 0'),
            "windows-client": ('str_equal(inner_type, "text")', 'str_equal(type, "text")'),
        }
        exact_vector_markers = {
            "linux-client": ('strcmp(inner_type, "vector") == 0', 'strcmp(type, "vector") == 0'),
            "linux-server": ('strcmp(inner_type, "vector") == 0', 'strcmp(type, "vector") == 0'),
            "windows-client": ('str_equal(inner_type, "vector")', 'str_equal(type, "vector")'),
        }
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)
                for needle in exact_string_markers[target]:
                    self.assertIn(needle, text)
                for needle in exact_text_markers[target]:
                    self.assertIn(needle, text)
                for needle in exact_vector_markers[target]:
                    self.assertIn(needle, text)

    def test_docs_describe_set_map_raw_contract(self):
        required = (
            "GetRawEntry(index, byteCount)",
            "GetRawPair(index, byteCount)",
            "GetElement(index)",
            "GetPair(index)",
            "GetStorageLayout()",
            "IsSparseLayoutValidated()",
            "GetSlotStride()",
            "Element*",
            "Key*",
            "Value*",
            "`FString`/`FText`",
            "descriptor-backed dense storage",
            "sparse layout",
            "FScriptSet",
            "FScriptMap",
        )
        for doc in self.existing_docs():
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_expose_native_executor_target_image_gate(self):
        required = (
            '"loader-load-asset-package-native-executor-state"',
            '"TargetImage"',
            "lua_load_asset_backend_package_target_image",
        )
        log_markers = {
            "linux-client": ('targetImage=%s',),
            "linux-server": ('targetImage=%s',),
            "windows-client": ('targetImage=',),
        }
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)
                for needle in log_markers[target]:
                    self.assertIn(needle, text)

    def test_full_lua_smokes_assert_native_executor_target_image_gate(self):
        required = (
            "packageExecutor.TargetImage==false",
            "not nativePackage.NativeCallPlanAccepted",
            "targetImage=false",
            "nativeCallPlanAccepted=false",
        )
        for target, smoke in self.existing_full_lua_smokes().items():
            with self.subTest(target=target):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
