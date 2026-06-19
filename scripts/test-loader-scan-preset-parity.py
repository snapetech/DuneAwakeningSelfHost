#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADERS = {
    "linux-client": ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
    "linux-server": ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
    "windows-client": ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
}
SUMMARIZERS = {
    "client": ROOT / "scripts" / "summarize-client-loader-scan.py",
    "linux": ROOT / "scripts" / "summarize-linux-loader-scan.py",
}
UE_NEEDLES = (
    "GUObjectArray",
    "GObjectArray",
    "GObjects",
    "FUObjectArray",
    "FNamePool",
    "NamePoolData",
    "GName",
    "GNames",
    "GWorld",
    "GEngine",
    "ProcessEvent",
    "StaticFindObject",
    "CallFunctionByNameWithArguments",
    "CallFunctionByName",
    "StaticLoadObject",
    "LoadObject",
    "LoadPackage",
    "ResolveName",
    "UObject",
    "UFunction",
    "UClass",
    "FProperty",
    "UStruct",
    "UEnum",
)


def read_loader(name):
    return LOADERS[name].read_text(encoding="utf-8", errors="replace")


class LoaderScanPresetParityTests(unittest.TestCase):
    def test_all_loaders_define_ue_scan_preset(self):
        for name in LOADERS:
            with self.subTest(loader=name):
                text = read_loader(name)
                self.assertRegex(text, r'preset,\s*"ue"\)|str_equal\(preset,\s*"ue"\)')
                for needle in UE_NEEDLES:
                    self.assertIn(f'"{needle}"', text)
                self.assertIn('"package"', text)

    def test_default_scan_presets_include_ue(self):
        patterns = {
            "linux-client": r'presets\s*=\s*"([^"]*)"',
            "linux-server": r'presets\s*=\s*"([^"]*)"',
            "windows-client": r'copy_string\(presets,\s*sizeof\(presets\),\s*"([^"]*)"\)',
        }
        for name, pattern in patterns.items():
            with self.subTest(loader=name):
                matches = re.findall(pattern, read_loader(name))
                defaults = [value for value in matches if "core" in value and "," in value]
                self.assertTrue(defaults, f"no default scan preset string found for {name}")
                self.assertTrue(any("ue" in value.split(",") for value in defaults), defaults)

    def test_scan_summarizers_classify_all_ue_needles(self):
        for name, path in SUMMARIZERS.items():
            with self.subTest(summarizer=name):
                text = path.read_text(encoding="utf-8", errors="replace")
                for needle in UE_NEEDLES:
                    self.assertIn(f'"{needle}"', text)


if __name__ == "__main__":
    unittest.main()
