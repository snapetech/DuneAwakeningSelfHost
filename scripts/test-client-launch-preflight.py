#!/usr/bin/env python3
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINUX_WRAPPER = next(
    (
        path
        for path in (
            ROOT / "scripts" / "launch-linux-client-probe.sh",
            ROOT / "examples" / "launch-native-client.sh",
        )
        if path.exists()
    ),
    ROOT / "scripts" / "launch-linux-client-probe.sh",
)
PROTON_WRAPPER = next(
    (
        path
        for path in (
            ROOT / "scripts" / "launch-proton-client-probe.sh",
            ROOT / "examples" / "launch-proton-client-probe.sh",
        )
        if path.exists()
    ),
    ROOT / "scripts" / "launch-proton-client-probe.sh",
)
VERIFY_WRAPPER = ROOT / "scripts" / "verify-client-probe-canary.sh"


class ClientLaunchPreflightTests(unittest.TestCase):
    def make_prep_bundle(self, root: Path, strict_rc: int = 0) -> Path:
        prep = root / "prep"
        prep.mkdir()
        (prep / "ue-anchors.env").write_text(
            "DUNE_CLIENT_PROBE_UE_ANCHORS='GWorld=0x1234'\n",
            encoding="utf-8",
        )
        verifier = prep / "post-canary-verify.sh"
        verifier.write_text(
            "#!/usr/bin/env bash\n"
            "script_dir=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
            "printf 'verified %s\\n' \"$1\"\n"
            "printf '{\"ready\":true}\\n' > \"$script_dir/ue4ss-readiness.json\"\n"
            "printf '{\"coverage\":true}\\n' > \"$script_dir/object-discovery-coverage.json\"\n"
            "printf '# summary\\n' > \"$script_dir/post-canary-summary.md\"\n"
            "printf '{\"gaps\":[]}\\n' > \"$script_dir/ue4ss-port-gaps.json\"\n"
            "printf '# gaps\\n' > \"$script_dir/ue4ss-port-gaps.md\"\n",
            encoding="utf-8",
        )
        verifier.chmod(0o755)
        strict = prep / "post-canary-verify-strict.sh"
        strict.write_text(
            "#!/usr/bin/env bash\n"
            "script_dir=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
            "printf 'strict %s\\n' \"$1\"\n"
            "printf '{\"strict\":true}\\n' > \"$script_dir/ue4ss-readiness.json\"\n"
            f"exit {strict_rc}\n",
            encoding="utf-8",
        )
        strict.chmod(0o755)
        return prep

    def test_linux_client_preflight_validates_without_exec_or_build(self):
        if not LINUX_WRAPPER.exists():
            self.skipTest("native Linux client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            loader = Path(tmp) / "libdune_client_probe_loader.so"
            build_dir = Path(tmp) / "build"
            loader.write_bytes(b"loader")
            env = dict(os.environ)
            env["DUNE_CLIENT_PROBE_PREFLIGHT_ONLY"] = "true"
            env["DUNE_LINUX_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_LINUX_CLIENT_LOADER_BUILD_DIR"] = str(build_dir)

            result = subprocess.run(
                [str(LINUX_WRAPPER), "--", "/bin/true", "--probe-arg"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("linux_client_probe_preflight=true", result.stdout)
        self.assertIn("target=/bin/true", result.stdout)
        self.assertIn(f"loader={loader}", result.stdout)
        self.assertIn("loader_readable=true", result.stdout)
        self.assertIn("would_set_ld_preload=", result.stdout)
        self.assertIn("would_exec=/bin/true --probe-arg", result.stdout)
        self.assertFalse(build_dir.exists())

    def test_linux_client_preflight_rejects_missing_loader_without_building(self):
        if not LINUX_WRAPPER.exists():
            self.skipTest("native Linux client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            loader = Path(tmp) / "missing.so"
            build_dir = Path(tmp) / "build"
            env = dict(os.environ)
            env["DUNE_CLIENT_PROBE_PREFLIGHT_ONLY"] = "true"
            env["DUNE_LINUX_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_LINUX_CLIENT_LOADER_BUILD_DIR"] = str(build_dir)

            result = subprocess.run(
                [str(LINUX_WRAPPER), "--", "/bin/true"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("loader_readable=false", result.stdout)
        self.assertIn("client preload library is not readable", result.stderr)
        self.assertFalse(build_dir.exists())

    def test_linux_client_preflight_accepts_prepared_canary_bundle(self):
        if not LINUX_WRAPPER.exists():
            self.skipTest("native Linux client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "libdune_client_probe_loader.so"
            loader.write_bytes(b"loader")
            prep = root / "prep"
            prep.mkdir()
            (prep / "ue-anchors.env").write_text(
                "DUNE_CLIENT_PROBE_UE_ANCHORS='GWorld=0x1234'\n",
                encoding="utf-8",
            )
            verifier = prep / "post-canary-verify.sh"
            verifier.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            verifier.chmod(0o755)
            strict = prep / "post-canary-verify-strict.sh"
            strict.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            strict.chmod(0o755)
            env = dict(os.environ)
            env["DUNE_CLIENT_PROBE_PREFLIGHT_ONLY"] = "true"
            env["DUNE_LINUX_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_CLIENT_PROBE_PREP_DIR"] = str(prep)

            result = subprocess.run(
                [str(LINUX_WRAPPER), "--", "/bin/true"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"prep_dir={prep}", result.stdout)
        self.assertIn(f"prep_anchor_env={prep / 'ue-anchors.env'}", result.stdout)
        self.assertIn(f"post_canary_verify_script={verifier}", result.stdout)

    def test_linux_client_preflight_rejects_invalid_prepared_canary_bundle(self):
        if not LINUX_WRAPPER.exists():
            self.skipTest("native Linux client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "libdune_client_probe_loader.so"
            loader.write_bytes(b"loader")
            prep = root / "prep"
            prep.mkdir()
            (prep / "ue-anchors.env").write_text("", encoding="utf-8")
            env = dict(os.environ)
            env["DUNE_CLIENT_PROBE_PREFLIGHT_ONLY"] = "true"
            env["DUNE_LINUX_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_CLIENT_PROBE_PREP_DIR"] = str(prep)

            result = subprocess.run(
                [str(LINUX_WRAPPER), "--", "/bin/true"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing executable client post-canary verifier", result.stderr)

    def test_proton_client_preflight_validates_game_dir_without_staging(self):
        if not PROTON_WRAPPER.exists():
            self.skipTest("Proton client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "dune_win_client_probe_loader.dll"
            loader.write_bytes(b"dll")
            game_dir = root / "Dune"
            exe_dir = game_dir / "DuneSandbox" / "Binaries" / "Win64"
            exe_dir.mkdir(parents=True)
            stage_dir = root / "stage"
            build_dir = root / "build"
            env = dict(os.environ)
            env["DUNE_WINDOWS_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_WINDOWS_CLIENT_LOADER_BUILD_DIR"] = str(build_dir)
            env["DUNE_WIN_CLIENT_STAGE_DIR"] = str(stage_dir)

            result = subprocess.run(
                [
                    str(PROTON_WRAPPER),
                    "--preflight-only",
                    "--stage-to-game-dir",
                    "--game-dir",
                    str(game_dir),
                    "--",
                    "proton",
                    "run",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windows_client_probe_preflight=true", result.stdout)
        self.assertIn("stage_to_game_dir=true", result.stdout)
        self.assertIn(f"game_dir={game_dir}", result.stdout)
        self.assertIn(f"loader={loader}", result.stdout)
        self.assertIn("loader_readable=true", result.stdout)
        self.assertIn(f"stage_target={exe_dir / 'version.dll'}", result.stdout)
        self.assertIn(f"sidecar={exe_dir / 'dune-win-client-probe.env'}", result.stdout)
        self.assertIn("stage_dir_valid=true", result.stdout)
        self.assertIn("would_exec=proton run", result.stdout)
        self.assertFalse((exe_dir / "version.dll").exists())
        self.assertFalse((exe_dir / "dune-win-client-probe.env").exists())
        self.assertFalse(stage_dir.exists())
        self.assertFalse(build_dir.exists())

    def test_proton_client_preflight_rejects_invalid_game_dir_without_staging(self):
        if not PROTON_WRAPPER.exists():
            self.skipTest("Proton client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "dune_win_client_probe_loader.dll"
            loader.write_bytes(b"dll")
            game_dir = root / "missing-game"
            stage_dir = root / "stage"
            build_dir = root / "build"
            env = dict(os.environ)
            env["DUNE_WINDOWS_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_WINDOWS_CLIENT_LOADER_BUILD_DIR"] = str(build_dir)
            env["DUNE_WIN_CLIENT_STAGE_DIR"] = str(stage_dir)

            result = subprocess.run(
                [
                    str(PROTON_WRAPPER),
                    "--preflight-only",
                    "--stage-to-game-dir",
                    "--game-dir",
                    str(game_dir),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("stage_dir_valid=false", result.stdout)
        self.assertIn("--stage-to-game-dir needs a valid game exe directory", result.stderr)
        self.assertFalse(stage_dir.exists())
        self.assertFalse(build_dir.exists())

    def test_proton_client_preflight_accepts_prepared_canary_bundle(self):
        if not PROTON_WRAPPER.exists():
            self.skipTest("Proton client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "dune_win_client_probe_loader.dll"
            loader.write_bytes(b"dll")
            game_dir = root / "Dune"
            exe_dir = game_dir / "DuneSandbox" / "Binaries" / "Win64"
            exe_dir.mkdir(parents=True)
            prep = root / "prep"
            prep.mkdir()
            (prep / "ue-anchors.env").write_text(
                "DUNE_WIN_CLIENT_PROBE_UE_ANCHORS='GWorld=0x14001234'\n",
                encoding="utf-8",
            )
            verifier = prep / "post-canary-verify.sh"
            verifier.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            verifier.chmod(0o755)
            strict = prep / "post-canary-verify-strict.sh"
            strict.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            strict.chmod(0o755)
            env = dict(os.environ)
            env["DUNE_WINDOWS_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_WIN_CLIENT_PROBE_PREP_DIR"] = str(prep)

            result = subprocess.run(
                [
                    str(PROTON_WRAPPER),
                    "--preflight-only",
                    "--stage-to-game-dir",
                    "--game-dir",
                    str(game_dir),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"prep_dir={prep}", result.stdout)
        self.assertIn(f"prep_anchor_env={prep / 'ue-anchors.env'}", result.stdout)
        self.assertIn(f"post_canary_verify_script={verifier}", result.stdout)
        self.assertFalse((exe_dir / "version.dll").exists())

    def test_proton_client_preflight_rejects_invalid_prepared_canary_bundle(self):
        if not PROTON_WRAPPER.exists():
            self.skipTest("Proton client wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "dune_win_client_probe_loader.dll"
            loader.write_bytes(b"dll")
            prep = root / "prep"
            prep.mkdir()
            (prep / "ue-anchors.env").write_text("", encoding="utf-8")
            env = dict(os.environ)
            env["DUNE_WINDOWS_CLIENT_PRELOAD"] = str(loader)
            env["DUNE_WIN_CLIENT_PROBE_PREP_DIR"] = str(prep)
            env["DUNE_WIN_CLIENT_PROBE_PREFLIGHT_ONLY"] = "true"

            result = subprocess.run(
                [str(PROTON_WRAPPER)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing executable Proton post-canary verifier", result.stderr)

    def test_client_post_canary_verify_wrapper_copies_outputs(self):
        if not VERIFY_WRAPPER.exists():
            self.skipTest("client post-canary verifier wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prep = self.make_prep_bundle(root)
            log = root / "client.log"
            log.write_text("loader log\n", encoding="utf-8")
            output = root / "evidence"

            result = subprocess.run(
                [
                    str(VERIFY_WRAPPER),
                    "--platform",
                    "linux-client",
                    "--prep-dir",
                    str(prep),
                    "--log",
                    str(log),
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("platform=linux-client", result.stdout)
            self.assertIn("verify_rc=0", result.stdout)
            self.assertTrue((output / "client.log").exists())
            self.assertTrue((output / "ue-anchors.env").exists())
            self.assertTrue((output / "ue4ss-readiness.json").exists())
            self.assertTrue((output / "object-discovery-coverage.json").exists())
            self.assertTrue((output / "post-canary-summary.md").exists())
            self.assertTrue((output / "ue4ss-port-gaps.md").exists())
            self.assertIn(
                "verify_rc=0", (output / "summary.env").read_text(encoding="utf-8")
            )

    def test_client_post_canary_verify_wrapper_uses_strict_verifier(self):
        if not VERIFY_WRAPPER.exists():
            self.skipTest("client post-canary verifier wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prep = self.make_prep_bundle(root, strict_rc=7)
            log = root / "client.log"
            log.write_text("loader log\n", encoding="utf-8")
            output = root / "strict-evidence"

            result = subprocess.run(
                [
                    str(VERIFY_WRAPPER),
                    "--platform",
                    "windows",
                    "--prep-dir",
                    str(prep),
                    "--log",
                    str(log),
                    "--output-dir",
                    str(output),
                    "--strict",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 7)
            self.assertIn("verify_rc=7", result.stdout)
            summary = (output / "summary.env").read_text(encoding="utf-8")
            self.assertIn("platform=windows", summary)
            self.assertIn("strict=true", summary)
            self.assertIn("post-canary-verify-strict.sh", summary)

    def test_client_post_canary_verify_wrapper_rejects_missing_anchor_env(self):
        if not VERIFY_WRAPPER.exists():
            self.skipTest("client post-canary verifier wrapper is not packaged here")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prep = root / "prep"
            prep.mkdir()
            log = root / "client.log"
            log.write_text("loader log\n", encoding="utf-8")

            result = subprocess.run(
                [
                    str(VERIFY_WRAPPER),
                    "--platform",
                    "linux-client",
                    "--prep-dir",
                    str(prep),
                    "--log",
                    str(log),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("missing prepared canary anchor env", result.stderr)


if __name__ == "__main__":
    unittest.main()
