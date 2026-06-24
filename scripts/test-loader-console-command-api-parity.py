#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderConsoleCommandApiParityTests(unittest.TestCase):
    SOURCES = {
        "linux-client": REPO_ROOT / "tools/linux-client-loader/dune_client_probe_loader.c",
        "linux-server": REPO_ROOT / "tools/linux-server-loader/dune_server_probe_loader.c",
        "windows-client": REPO_ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c",
    }

    DOCS = (
        REPO_ROOT / "docs/client-loader-support.md",
        REPO_ROOT / "docs/linux-client-loader.md",
        REPO_ROOT / "docs/windows-client-loader.md",
        REPO_ROOT / "docs/ue4ss-linux-loader-evaluation.md",
    )

    def test_all_targets_expose_direct_console_command_dispatch(self):
        required = (
            "lua_dune_probe_dispatch_console_command_callback",
            "invoke_lua_console_command_handlers",
            "lua_push_console_command_parameters",
            "LuaRawSetIFn",
            '"lua_rawseti"',
            "FOutputDevice",
            "lua_console_output_device_write_callback",
            '"Log"',
            '"Serialize"',
            '"Write"',
            '"GetOutput"',
            '"ToString"',
            '"Clear"',
            "lua_console_output_device_get_output_callback",
            "lua_console_output_device_clear_callback",
            "lua_call(active_lua_api, state, 6, 1, 0)",
            "lua_dune_probe_dispatch_key_bind_callback",
            "lua_key_code_to_name",
            "lua_read_key_bind_key",
            '"DuneProbeDispatchConsoleCommand"',
            '"DuneProbeDispatchKeyBind"',
            '"UnregisterConsoleCommandGlobalHandler"',
            "keyBindDispatchCalls",
            "keyBindCallbackHandled",
            "consoleCommandHandlerCalls",
            "consoleCommandGlobalHandlerCalls",
            "consoleCommandGlobalHandlerHandled",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_exercise_ue4ss_keybind_overloads(self):
        required = (
            "RegisterKeyBind(Key.O",
            "RegisterKeyBind({Key=Key.P}",
            "IsKeyBindRegistered(Key.O)",
            "IsKeyBindRegistered({Key=Key.P})",
            "DuneProbeDispatchKeyBind(o,Key.O)",
            "DuneProbeDispatchKeyBind(o,{Key=Key.P})",
            "missing UE4SS keybind overloads",
            "params[0]=='probe_args'",
            "params[1]=='spice'",
            "params[2]=='flow'",
            "output.Kind=='FOutputDevice'",
            "output:Log('probe-log')",
            "output:Serialize('probe-serialize')",
            "output:Write('probe-write')",
            "output.LastMessage=='probe-write'",
            "output.WriteCount==3",
            "output:GetOutput()=='probe-write'",
            "output:ToString()=='probe-write'",
            "output:Clear()",
            "RegisterConsoleCommandGlobalHandler(function(full)",
            "UnregisterConsoleCommandGlobalHandler(tempGlobal)",
            "tempGlobalHits==0",
            "missing UE4SS ProcessConsoleExec dispatch",
        )
        for smoke in (
            REPO_ROOT / "scripts/smoke-linux-client-loader.sh",
            REPO_ROOT / "scripts/smoke-linux-server-loader.sh",
            REPO_ROOT / "scripts/smoke-windows-client-loader-lua.sh",
        ):
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_direct_console_command_dispatch(self):
        required = (
            "DuneProbeDispatchConsoleCommand",
            "DuneProbeDispatchKeyBind",
            "keyBindCallbackHandled",
            "consoleCommandHandlerCalls",
            "consoleCommandGlobalHandlerHandled",
            "UnregisterConsoleCommandGlobalHandler",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
