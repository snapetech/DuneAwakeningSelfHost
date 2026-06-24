#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderSchedulerApiParityTests(unittest.TestCase):
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

    def existing_sources(self):
        return {name: path for name, path in self.SOURCES.items() if path.exists()}

    def existing_docs(self):
        return [path for path in self.DOCS if path.exists()]

    def test_all_targets_expose_bounded_game_thread_queue(self):
        required = (
            "MAX_LUA_SCHEDULED_CALLBACKS",
            "LuaScheduledCallback",
            "lua_game_thread_queue",
            "lua_drain_game_thread_queue_internal",
            "lua_drain_game_thread_queue_callback",
            "lua_unref_scheduled_callbacks",
            '"ExecuteInGameThread"',
            '"DrainGameThreadQueue"',
            '"DrainSchedulerQueue"',
            '"CancelScheduledCallback"',
            "DrainGameThreadQueue()",
            "owner_state",
            "scheduled->owner_state != state",
            "lua_drain_scheduler_queue_internal",
            "lua_drain_game_thread_queue_internal(&process_event_live_lua_api, process_event_live_lua_state)",
            "lua_drain_scheduler_queue_internal(&process_event_live_lua_api, process_event_live_lua_state, 0)",
        )
        for target, source in self.existing_sources().items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_scheduler_contract(self):
        required = (
            "ExecuteInGameThread",
            "DrainGameThreadQueue()",
            "DrainSchedulerQueue()",
            "CancelScheduledCallback",
            "bounded game-thread queue",
            "bounded scheduler queue",
            "Lua-state-owned",
            "live ProcessEvent post-hook",
            "live CallFunction post-hook",
        )
        for doc in self.existing_docs():
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
