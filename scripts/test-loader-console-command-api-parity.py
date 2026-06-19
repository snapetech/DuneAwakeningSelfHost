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
            "lua_dune_probe_dispatch_key_bind_callback",
            '"DuneProbeDispatchConsoleCommand"',
            '"DuneProbeDispatchKeyBind"',
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

    def test_docs_describe_direct_console_command_dispatch(self):
        required = (
            "DuneProbeDispatchConsoleCommand",
            "DuneProbeDispatchKeyBind",
            "keyBindCallbackHandled",
            "consoleCommandHandlerCalls",
            "consoleCommandGlobalHandlerHandled",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
