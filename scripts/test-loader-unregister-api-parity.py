#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderUnregisterApiParityTests(unittest.TestCase):
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

    REQUIRED_GLOBALS = (
        "UnregisterKeyBind",
        "UnregisterConsoleCommandHandler",
        "UnregisterCustomEvent",
        "UnregisterLoadMapPreHook",
        "UnregisterLoadMapPostHook",
        "UnregisterBeginPlayPreHook",
        "UnregisterBeginPlayPostHook",
        "UnregisterInitGameStatePreHook",
        "UnregisterInitGameStatePostHook",
        "UnregisterModInitCallback",
        "UnregisterModPostInitCallback",
        "UnregisterModUnloadCallback",
        "UnregisterProcessConsoleExecPreHook",
        "UnregisterProcessConsoleExecPostHook",
        "UnregisterCallFunctionByNameWithArgumentsPreHook",
        "UnregisterCallFunctionByNameWithArgumentsPostHook",
        "UnregisterULocalPlayerExecPreHook",
        "UnregisterULocalPlayerExecPostHook",
    )

    def existing_sources(self):
        return {name: path for name, path in self.SOURCES.items() if path.exists()}

    def existing_docs(self):
        return [path for path in self.DOCS if path.exists()]

    def existing_smokes(self):
        return [path for path in self.SMOKES if path.exists()]

    def test_all_targets_expose_unregister_globals(self):
        required = (
            "lua_read_registration_id",
            "lua_callback_unregister_calls",
            "lua_callback_unregister_hits",
            "lua_unregister_console_exec_registration_by_id",
            "lua_unregister_call_function_registration_by_id",
            "lua_unregister_key_bind_callback",
            "lua_unregister_console_command_handler_callback",
            "lua_unregister_custom_event_callback",
        ) + self.REQUIRED_GLOBALS
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_store_registration_ids(self):
        required = (
            "int id;",
            "registration->id = ++lua_compat_registration_count",
            "active_lua_api->push_integer(state, registration->id)",
            "lua_key_bind_registrations",
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_exercise_unregister_surface(self):
        required = (
            "UnregisterKeyBind",
            "UnregisterCustomEvent",
            "UnregisterModUnloadCallback",
            "callbackUnregisterCalls=16",
            "callbackUnregisterHits=16",
        )
        for smoke in self.existing_smokes():
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_unregister_contract(self):
        required = (
            "`UnregisterKeyBind`",
            "`UnregisterConsoleCommandHandler`",
            "`UnregisterCustomEvent`",
            "`UnregisterModUnloadCallback`",
            "`callbackUnregisterCalls=16 callbackUnregisterHits=16`",
            "active registrations",
        )
        for doc in self.existing_docs():
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
