#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderCompatGlobalsApiParityTests(unittest.TestCase):
    SOURCES = {
        "linux-client": REPO_ROOT / "tools/linux-client-loader/dune_client_probe_loader.c",
        "linux-server": REPO_ROOT / "tools/linux-server-loader/dune_server_probe_loader.c",
        "windows-client": REPO_ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c",
    }

    SMOKES = (
        REPO_ROOT / "scripts/smoke-linux-client-loader.sh",
        REPO_ROOT / "scripts/smoke-linux-server-loader.sh",
        REPO_ROOT / "scripts/smoke-windows-client-loader-lua.sh",
    )

    DOCS = (
        REPO_ROOT / "docs/client-loader-support.md",
        REPO_ROOT / "docs/linux-client-loader.md",
        REPO_ROOT / "docs/windows-client-loader.md",
        REPO_ROOT / "docs/ue4ss-linux-loader-evaluation.md",
    )

    def test_all_targets_seed_ue4ss_compat_globals(self):
        required = (
            "register_lua_compat_constant_tables",
            "register_lua_compat_metadata_tables",
            "lua_ue4ss_get_version_callback",
            "lua_unreal_version_get_major_callback",
            "lua_unreal_version_is_at_least_callback",
            '"UE4SS"',
            '"GetVersion"',
            '"3.0.0-dune-probe"',
            '"Compatibility"',
            '"ue4ss-lua-shim"',
            '"UnrealVersion"',
            '"GetMajor"',
            '"GetMinor"',
            '"IsEqual"',
            '"IsAtLeast"',
            '"IsAtMost"',
            '"IsBelow"',
            '"IsAbove"',
            '"EObjectFlags"',
            '"RF_NoFlags"',
            '"RF_ClassDefaultObject"',
            '"EInternalObjectFlags"',
            '"Native"',
            '"Key"',
            '"ModifierKey"',
            '"ModifierKeys"',
            '"IterateGameDirectories"',
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_exercise_compat_globals(self):
        required = (
            "UE4SS.GetVersion()",
            "UnrealVersion:GetMajor()",
            "UnrealVersion:IsAtLeast(4,27)",
            "EObjectFlags.RF_NoFlags",
            "EObjectFlags.RF_ClassDefaultObject",
            "EInternalObjectFlags.Native",
            "Key.O",
            "ModifierKey.CONTROL",
            "IterateGameDirectories()",
            "dirs.Game.Binaries.Win64",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_compat_globals(self):
        required = (
            "UE4SS",
            "UnrealVersion",
            "EObjectFlags",
            "EInternalObjectFlags",
            "PropertyTypes",
            "Key",
            "ModifierKey",
            "ModifierKeys",
            "IterateGameDirectories",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
