#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADER_SOURCES = (
    ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
    ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
    ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
)
GROUP_ALIASES = {
    "names": ("FNamePool", "RuntimeFNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "RuntimeGUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": (
        "UObject",
        "UFunction",
        "UClass",
        "FProperty",
        "FObjectProperty",
        "FArrayProperty",
        "FBoolProperty",
        "FStructProperty",
        "UStruct",
        "UEnum",
    ),
}


class LoaderAnchorGroupParityTests(unittest.TestCase):
    def test_anchor_group_helper_is_present_in_all_loaders(self):
        for source in LOADER_SOURCES:
            with self.subTest(source=source):
                text = source.read_text(encoding="utf-8")
                self.assertIn("ue_anchor_group_for_name", text)
                for group in (
                    '"names"',
                    '"objects"',
                    '"world"',
                    '"dispatch"',
                    '"package"',
                    '"reflection"',
                    '"cheat"',
                    '"brt"',
                    '"deep-desert"',
                    '"self-test"',
                    '"unknown"',
                ):
                    self.assertIn(group, text)

    def test_anchor_logs_emit_group_field_in_all_loaders(self):
        for source in LOADER_SOURCES:
            with self.subTest(source=source):
                text = source.read_text(encoding="utf-8")
                self.assertIn("event=ue-anchor-signature name=", text)
                self.assertIn("event=ue-anchor name=", text)
                self.assertIn(" group=", text)
                self.assertIn('"resolved"', text)
                self.assertIn("status=mapped", text)
                self.assertIn("status=unmapped", text)

    def test_core_anchor_aliases_are_classified_in_all_loaders(self):
        for source in LOADER_SOURCES:
            with self.subTest(source=source):
                text = source.read_text(encoding="utf-8")
                helper = text[text.index("ue_anchor_group_for_name") :]
                for group, aliases in GROUP_ALIASES.items():
                    group_index = helper.index(f'"{group}"')
                    previous_group_index = 0
                    for other_group in GROUP_ALIASES:
                        if other_group == group:
                            break
                        candidate = helper.find(f'"{other_group}"')
                        if candidate >= 0:
                            previous_group_index = max(previous_group_index, candidate)
                    group_block = helper[previous_group_index:group_index]
                    for alias in aliases:
                        self.assertIn(f'"{alias}"', group_block)

    def test_self_test_anchors_are_not_labeled_as_core_groups(self):
        for source in LOADER_SOURCES:
            with self.subTest(source=source):
                text = source.read_text(encoding="utf-8")
                self.assertIn("SelfTest", text)
                self.assertLess(text.index("SelfTest"), text.index("FNamePool"))


if __name__ == "__main__":
    unittest.main()
