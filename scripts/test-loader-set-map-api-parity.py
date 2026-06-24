#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOADERS = {
    "linux-client": ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
    "linux-server": ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
    "windows-client": ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
}

DOCS = (
    ROOT / "docs" / "client-loader-support.md",
    ROOT / "docs" / "linux-client-loader.md",
    ROOT / "docs" / "windows-client-loader.md",
    ROOT / "docs" / "ue4ss-linux-loader-evaluation.md",
)


class LoaderSetMapApiParityTests(unittest.TestCase):
    def test_all_loaders_expose_ue4ss_style_tset_methods(self):
        for target, source in LOADERS.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                self.assertIn("lua_script_set_add_callback", text)
                self.assertIn("lua_script_set_remove_callback", text)
                self.assertIn("lua_script_set_contains_callback", text)
                self.assertIn("lua_script_set_for_each_callback", text)
                self.assertIn('set_lua_object_method(api, state, "Add", lua_script_set_add_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Remove", lua_script_set_remove_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Contains", lua_script_set_contains_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "ForEach", lua_script_set_for_each_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Empty", lua_script_array_empty_callback);', text)
                self.assertIn("process_event_self_test_set_values[4]", text)
                self.assertIn("setMut=", text)
                self.assertIn("Add(73)", text)
                self.assertIn("Remove(72)", text)

    def test_all_loaders_expose_ue4ss_style_tmap_methods(self):
        for target, source in LOADERS.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                self.assertIn("lua_script_map_add_callback", text)
                self.assertIn("lua_script_map_remove_callback", text)
                self.assertIn("lua_script_map_contains_callback", text)
                self.assertIn("lua_script_map_find_callback", text)
                self.assertIn("lua_script_map_for_each_callback", text)
                self.assertIn('set_lua_object_method(api, state, "Add", lua_script_map_add_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Remove", lua_script_map_remove_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Contains", lua_script_map_contains_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Find", lua_script_map_find_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "ForEach", lua_script_map_for_each_callback);', text)
                self.assertIn('set_lua_object_method(api, state, "Empty", lua_script_array_empty_callback);', text)
                self.assertIn("process_event_self_test_map_pairs[4]", text)
                self.assertIn("mapMut=", text)
                self.assertIn("Add(103,203)", text)
                self.assertIn("Remove(102)", text)

    def test_docs_name_supported_surface_and_allocator_gap(self):
        required = (
            "Contains(element)",
            "Find(key)",
            "ForEach(callback)",
            "Add(element)",
            "Remove(element)",
            "Add(key, value)",
            "Remove(key)",
            "dense scalar writable backing storage",
            "Real UE set/map allocator",
            "hash mutation",
            "not proven yet",
        )
        for doc in DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
