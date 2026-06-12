#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("render-dune-public-snapshot.py")


def load_snapshot_module(env):
    with mock.patch.dict(os.environ, env, clear=True):
        spec = importlib.util.spec_from_file_location("render_dune_public_snapshot_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class PublicSnapshotConfigTest(unittest.TestCase):
    def test_game_env_database_beats_stale_public_site_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".env").write_text(
                "DUNE_GAME_DB_NAME=dune_sb_1_4_5_0\n"
                "DUNE_DATABASE=dune_sb_1_4_5_0\n",
                encoding="utf-8",
            )
            module = load_snapshot_module({
                "DUNE_ROOT": str(root),
                "STATIC_DIR": str(root / "static"),
                "DUNE_DATABASE": "dune_sb_1_4_0_0",
                "PATH": os.environ.get("PATH", ""),
            })

            self.assertEqual(module.DATABASE, "dune_sb_1_4_5_0")

            captured = {}

            def fake_check_output(cmd, cwd, text, timeout):
                captured["cmd"] = cmd
                captured["cwd"] = cwd
                return "[]\n"

            with mock.patch.object(module.subprocess, "check_output", side_effect=fake_check_output):
                module.compose_psql("select 1")

            self.assertEqual(captured["cwd"], root)
            self.assertEqual(captured["cmd"][captured["cmd"].index("-d") + 1], "dune_sb_1_4_5_0")
            self.assertEqual(captured["cmd"][captured["cmd"].index("--env-file") + 1], str(root / ".env"))

    def test_env_file_selects_authoritative_game_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            live_env = root / "live.env"
            live_env.write_text(
                "DUNE_DATABASE=dune_sb_1_4_5_0\n"
                "COMPOSE_FILES=compose.yaml:compose.allmaps.yaml:compose.patch.yaml\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("DUNE_DATABASE=dune_sb_1_4_0_0\n", encoding="utf-8")
            module = load_snapshot_module({
                "DUNE_ROOT": str(root),
                "ENV_FILE": str(live_env),
                "STATIC_DIR": str(root / "static"),
                "PATH": os.environ.get("PATH", ""),
            })

            self.assertEqual(module.GAME_ENV_FILE, live_env)
            self.assertEqual(module.DATABASE, "dune_sb_1_4_5_0")
            self.assertEqual(module.COMPOSE_FILES, ["compose.yaml", "compose.allmaps.yaml", "compose.patch.yaml"])


if __name__ == "__main__":
    unittest.main()
