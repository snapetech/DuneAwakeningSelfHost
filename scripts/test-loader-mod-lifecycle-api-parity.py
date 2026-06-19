#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderModLifecycleApiParityTests(unittest.TestCase):
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

    def test_all_targets_parse_mods_txt_manifest(self):
        required = (
            "MAX_LUA_MOD_MANIFEST_ENTRIES",
            "LuaModManifestEntry",
            "LuaModManifest",
            "load_lua_mod_manifest",
            "find_lua_mod_manifest_entry",
            "add_lua_mod_script_from_root",
            "manifestEntries",
            "manifestDisabled",
            "mods.txt",
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_expose_mod_lifecycle_callbacks(self):
        required = (
            "lua_register_mod_init_callback_callback",
            "lua_register_mod_post_init_callback_callback",
            "lua_register_mod_unload_callback_callback",
            "RegisterModInitCallback",
            "RegisterModPostInitCallback",
            "RegisterModUnloadCallback",
            "ModInit",
            "ModPostInit",
            "ModUnload",
            "modInitCallbacks",
            "modPostInitCallbacks",
            "modUnloadCallbacks",
            "modInitCalls",
            "modPostInitCalls",
            "modUnloadCalls",
            "modInitHandled",
            "modPostInitHandled",
            "modUnloadHandled",
            "load_lua_live_mods_into_state",
            "lua-live-mod-start",
            "lua-live-mod-finish",
            "persistent=true",
            "close_process_event_live_lua_dispatch",
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_expose_lifecycle_callback_aliases(self):
        required = (
            "RegisterLoadMapPreCallback",
            "UnregisterLoadMapPreCallback",
            "RegisterLoadMapPostCallback",
            "UnregisterLoadMapPostCallback",
            "RegisterBeginPlayPreCallback",
            "UnregisterBeginPlayPreCallback",
            "RegisterBeginPlayPostCallback",
            "UnregisterBeginPlayPostCallback",
            "RegisterInitGameStatePreCallback",
            "UnregisterInitGameStatePreCallback",
            "RegisterInitGameStatePostCallback",
            "UnregisterInitGameStatePostCallback",
            "RegisterLocalPlayerExecPreHook",
            "UnregisterLocalPlayerExecPreHook",
            "RegisterLocalPlayerExecPostHook",
            "UnregisterLocalPlayerExecPostHook",
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_cover_disabled_manifest_entry(self):
        required = (
            "DisabledMod",
            "disabled mod should not load",
            "manifestEntries=",
            "manifestDisabled=1",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_cover_mod_lifecycle_callbacks(self):
        required = (
            "RegisterModInitCallback",
            "RegisterModPostInitCallback",
            "RegisterModUnloadCallback",
            "ModInit",
            "ModPostInit",
            "ModUnload",
            "modInitCallbacks=1",
            "modPostInitCallbacks=1",
            "modUnloadCallbacks=1",
            "modInitCalls=1",
            "modPostInitCalls=1",
            "modUnloadCalls=1",
            "modInitHandled=1",
            "modPostInitHandled=1",
            "modUnloadHandled=1",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_cover_lifecycle_callback_aliases(self):
        required = (
            "RegisterLoadMapPreCallback",
            "RegisterLoadMapPostCallback",
            "RegisterBeginPlayPreCallback",
            "RegisterBeginPlayPostCallback",
            "RegisterInitGameStatePreCallback",
            "RegisterInitGameStatePostCallback",
            "RegisterLocalPlayerExecPreHook",
            "RegisterLocalPlayerExecPostHook",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_mods_txt_contract(self):
        required = (
            "UE4SS-style `mods.txt`",
            "`+ModName`",
            "`-ModName`",
            "`manifestDisabled`",
            "`RegisterModInitCallback`",
            "`RegisterModPostInitCallback`",
            "`RegisterModUnloadCallback`",
            "`modInitCallbacks`",
            "`modPostInitCallbacks`",
            "`modUnloadCallbacks`",
            "persistent live ProcessEvent Lua state",
            "`lua-live-mod-start`",
            "`lua-live-mod-finish`",
            "`RegisterLoadMapPreCallback`",
            "`RegisterBeginPlayPreCallback`",
            "`RegisterInitGameStatePreCallback`",
            "`RegisterLocalPlayerExecPreHook`",
        )
        for doc in self.existing_docs():
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
