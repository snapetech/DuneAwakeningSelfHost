#!/usr/bin/env python3
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "schedule-daily-maintenance.sh"


class DailyMaintenanceSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.capture = self.root / "request.json"
        self.env_file = self.root / ".env"
        self.env_file.write_text(
            "\n".join([
                "DUNE_ADMIN_TOKEN=test-token",
                "DUNE_ADMIN_REQUIRE_TOKEN=true",
                "DUNE_ADMIN_HOST_PORT=18081",
                "DUNE_UPDATE_REQUIRE_READINESS_RECEIPT=true",
                "",
            ]),
            encoding="utf-8",
        )
        curl = self.bin / "curl"
        curl.write_text(
            """#!/usr/bin/env python3
import os, pathlib, sys
args=sys.argv[1:]
if any("/api/ops/update-readiness" in arg for arg in args):
    print(os.environ["FAKE_READINESS"])
else:
    index=args.index("--data")
    pathlib.Path(os.environ["FAKE_CAPTURE"]).write_text(args[index + 1], encoding="utf-8")
    print('{"ok":true}')
""",
            encoding="utf-8",
        )
        curl.chmod(0o755)

    def invoke(self, readiness, **overrides):
        environment = os.environ.copy()
        environment.update({
            "PATH": str(self.bin) + os.pathsep + environment.get("PATH", ""),
            "DUNE_ENV_FILE": str(self.env_file),
            "DUNE_DAILY_RESTART_ALLOW_OUTSIDE_WINDOW": "true",
            "DUNE_DAILY_RESTART_UPDATE_POLICY": "certified",
            "FAKE_READINESS": json.dumps(readiness),
            "FAKE_CAPTURE": str(self.capture),
        })
        environment.update(overrides)
        return subprocess.run(
            [str(SCRIPT)], cwd=ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    @staticmethod
    def update_readiness(apply_ready):
        return {
            "applyReady": apply_ready,
            "currentReceiptReady": apply_ready,
            "evaluation": {
                "candidate": {
                    "status": "update-available", "updateRequired": True,
                    "imageTag": "dune_sb_1_4_11_0", "currentImageTag": "dune_sb_1_4_10_0",
                }
            },
        }

    def test_uncertified_candidate_falls_back_to_current_build_restart(self):
        completed = self.invoke(self.update_readiness(False))
        self.assertEqual(0, completed.returncode, completed.stderr)
        body = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual("current", body["update_policy"])
        self.assertIn("pinned to the current build", completed.stderr)

    def test_certified_candidate_remains_bound_for_execution_revalidation(self):
        completed = self.invoke(self.update_readiness(True))
        self.assertEqual(0, completed.returncode, completed.stderr)
        body = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual("certified", body["update_policy"])
        self.assertIn("daily maintenance update policy: certified", completed.stdout)

    def test_invalid_readiness_response_falls_back_without_losing_daily_restart(self):
        completed = self.invoke({}, FAKE_READINESS="not-json")
        self.assertEqual(0, completed.returncode, completed.stderr)
        body = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual("current", body["update_policy"])
        self.assertIn("response was invalid", completed.stderr)

    def test_automatic_policy_requires_explicit_receipt_enforcement_opt_out(self):
        completed = self.invoke(
            self.update_readiness(True), DUNE_DAILY_RESTART_UPDATE_POLICY="automatic",
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("blocked", completed.stderr)
        self.assertFalse(self.capture.exists())

    def test_staged_only_restart_mode_never_invokes_steam_acquisition(self):
        workspace = self.root / "workspace"
        scripts = workspace / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(ROOT / "scripts" / "restart-target.sh", scripts / "restart-target.sh")
        marker = workspace / "acquisition-ran"
        (scripts / "update-steam-tool.sh").write_text(
            f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8",
        )
        (scripts / "check-steam-update.sh").write_text(
            "#!/bin/sh\necho 'status: current'\nexit 0\n", encoding="utf-8",
        )
        for path in scripts.iterdir():
            path.chmod(0o755)
        env_file = workspace / ".env"
        env_file.write_text(
            "DUNE_IMAGE_TAG=dune_sb_1_4_10_0\nDUNE_RESTART_STEAM_UPDATE_MODE=none\n",
            encoding="utf-8",
        )
        docker = self.bin / "docker"
        docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker.chmod(0o755)
        environment = os.environ.copy()
        environment.update({
            "PATH": str(self.bin) + os.pathsep + environment.get("PATH", ""),
            "ENV_FILE": str(env_file),
            "DUNE_RESTART_TARGET": "all",
            "DUNE_RESTART_PHASE": "update",
            "DUNE_RESTART_ACTION": "restart",
            "DUNE_RESTART_CHECK_STEAM_UPDATE": "true",
            "DUNE_RESTART_STEAM_UPDATE_MODE": "none",
        })
        completed = subprocess.run(
            [str(scripts / "restart-target.sh"), "all"], cwd=workspace, env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertFalse(marker.exists())
        self.assertIn("acquisition disabled", completed.stdout)
        source = (scripts / "restart-target.sh").read_text(encoding="utf-8")
        self.assertIn('if [ "$steam_mode" = "none" ]', source)
        self.assertIn('if [ \\"$steam_mode\\" = none ]', source)


if __name__ == "__main__":
    unittest.main()
