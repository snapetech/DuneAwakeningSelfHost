#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderHookPathAliasParityTests(unittest.TestCase):
    SOURCES = {
        "linux-client": REPO_ROOT / "tools/linux-client-loader/dune_client_probe_loader.c",
        "linux-server": REPO_ROOT / "tools/linux-server-loader/dune_server_probe_loader.c",
        "windows-client": REPO_ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c",
    }

    def test_all_targets_store_terminal_hook_path_and_count_matches(self):
        required = (
            "char terminal_name[128];",
            "lua_hook_path_exact_matches",
            "lua_hook_path_alias_matches",
            "pathExactMatches",
            "pathAliasMatches",
            "registration->terminal_name",
            ":Function",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_windows_target_keeps_crt_clean_string_helpers(self):
        text = self.SOURCES["windows-client"].read_text(encoding="utf-8")
        self.assertIn("find_last_char", text)
        self.assertIn("find_substring", text)
        self.assertNotIn("strrchr(runtime_terminal", text)
        self.assertNotIn("strstr(runtime_name", text)

    def test_hook_target_resolution_uses_resolved_anchor_sources(self):
        required = (
            "collect_ue_hook_target_anchors",
            "collect_ue_candidate_global_anchors",
            "collect_ue_runtime_discovered_anchors",
            "ue_anchor_signatures_configured",
            "configured_process_event_hook_target",
            "configured_call_function_hook_target",
            "configured_process_event_live_hook_target",
            "ue-process-event-hook",
            "ue-call-function-hook",
            "ue-process-event-live-hook",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

        # CallFunction live hooks delegate through configured_call_function_hook_target,
        # so the widened dry-run resolver must remain the shared path for both modes.
        for target in ("linux-client", "linux-server", "windows-client"):
            with self.subTest(target=target, mode="call-function-live"):
                text = self.SOURCES[target].read_text(encoding="utf-8")
                self.assertIn("return configured_call_function_hook_target(phase, self_test_target);", text)


if __name__ == "__main__":
    unittest.main()
