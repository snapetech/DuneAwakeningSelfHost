#!/usr/bin/env python3
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update-steam-tool.sh"


class UpdateSteamToolTests(unittest.TestCase):
    def test_configured_home_is_used_for_steamcmd_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            server = root / "server"
            home = root / "steam-home"
            bin_dir = root / "bin"
            server.mkdir()
            bin_dir.mkdir()
            capture = root / "home.txt"
            steamcmd = bin_dir / "steamcmd"
            steamcmd.write_text('#!/bin/sh\nprintf "%s" "$HOME" >"$CAPTURE_HOME"\n', encoding="utf-8")
            steamcmd.chmod(0o755)
            env_file = root / ".env"
            env_file.write_text("\n".join([
                "DUNE_RESTART_STEAM_UPDATE_MODE=steamcmd",
                "DUNE_RESTART_STEAMCMD_UPDATE=true",
                "DUNE_RESTART_STEAMCMD_REQUIRED=true",
                f"DUNE_STEAM_SERVER_DIR={server}",
                f"DUNE_STEAMCMD_HOME={home}",
                "DUNE_STEAMCMD_COMMAND=steamcmd",
                "DUNE_STEAM_LOGIN=anonymous",
                "DUNE_STEAMCMD_VALIDATE=false",
                "",
            ]), encoding="utf-8")
            environment = os.environ.copy()
            environment.update({"PATH": str(bin_dir) + os.pathsep + environment["PATH"], "CAPTURE_HOME": str(capture)})
            completed = subprocess.run([str(SCRIPT), str(env_file)], cwd=ROOT, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(str(home), capture.read_text(encoding="utf-8"))
            self.assertTrue(home.is_dir())


if __name__ == "__main__":
    unittest.main()
