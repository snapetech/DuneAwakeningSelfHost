#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderModRefApiParityTests(unittest.TestCase):
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

    def existing_sources(self):
        return {name: path for name, path in self.SOURCES.items() if path.exists()}

    def existing_docs(self):
        return [path for path in self.DOCS if path.exists()]

    def test_all_targets_expose_per_mod_modref_context(self):
        required = (
            "lua_current_mod_name",
            "lua_current_mod_path",
            "lua_current_mod_script_path",
            "set_lua_current_mod_context",
            "lua_active_mod_name",
            "lua_modref_get_mod_name_callback",
            "lua_modref_get_mod_path_callback",
            "lua_modref_get_mod_script_path_callback",
            '"GetModName"',
            '"GetModPath"',
            '"GetModDir"',
            '"GetModScriptPath"',
            '"ScriptPath"',
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_assert_modref_metadata(self):
        required = (
            "ModRef:GetModName()",
            "ModRef:GetModPath()",
            "ModRef:GetModDir()",
            "ModRef:GetModScriptPath()",
            "ModRef.ScriptPath",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_modref_context_contract(self):
        required = (
            "per-mod `ModRef` context",
            "`GetModName()`",
            "`GetModPath()`",
            "`GetModScriptPath()`",
        )
        for doc in self.existing_docs():
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
