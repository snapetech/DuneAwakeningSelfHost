#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderWorldEngineApiParityTests(unittest.TestCase):
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

    def test_all_targets_register_global_world_and_engine_helpers(self):
        required = (
            "ue_uobject_anchor_class_name",
            "find_lua_registered_world_handle",
            "find_lua_registered_engine_handle",
            "find_or_add_lua_engine_handle",
            "lua_get_world_callback",
            "lua_get_engine_callback",
            "lua-global-runtime-helper-check",
            "globalWorldPromoted",
            "globalEnginePromoted",
            'api->set_global(state, "GetWorld")',
            'api->set_global(state, "GetEngine")',
            "/RuntimeProbe/Engine",
            "UWorld",
            "UEngine",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_prove_global_helpers_with_world_context(self):
        required = (
            "GetWorld()",
            "GetEngine()",
            "gw.Address==world.Address",
            "ge.ClassName=='UEngine'",
            "missing GetWorld/GetEngine/GetLevel world-context dispatch",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_global_world_and_engine_helpers(self):
        required = (
            "global `GetWorld()`",
            "global `GetEngine()`",
            "`lua-global-runtime-helper-check`",
            "loader-owned `UEngine`",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
