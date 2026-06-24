#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderObjectQueryApiParityTests(unittest.TestCase):
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

    def test_all_targets_implement_ue4ss_find_objects_overload(self):
        required = (
            "lua_string_arg_if_string",
            "lua_size_limit_arg",
            "lua_u32_flags_arg",
            "lua_object_class_matches_query",
            "lua_object_name_matches_query",
            "lua_object_flags_match_query",
            "push_matching_lua_object_handles",
            "find_matching_lua_object_handle",
            "rawseti(state, -2, (long long)count)",
            "active_lua_api->type(state, 1) == LUA_TNUMBER_COMPAT",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_exercise_numeric_and_keyed_find_objects_results(self):
        required = (
            "FindObjects(1,",
            "FindObject('Dune",
            "flagsOk.Count==1",
            "flagsMiss.Count==0",
            "oneMiss==nil",
            "exact.Count==1",
            "exact[1]",
            "exact[exact[1].PathName]",
            "missing UE4SS FindObjects overload",
        )
        for smoke in self.SMOKES:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_ue4ss_find_objects_overload(self):
        required = (
            "FindObjects(limit, className, objectName, bannedFlags, requiredFlags, exactClass)",
            "FindObject(className, objectName, bannedFlags, requiredFlags)",
            "numeric entries",
            "path keys",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
