#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/client-deployment.py"
CONFIRM = "MUTATE DUNE CLIENT FILES"
ADOPT_CONFIRM = "ADOPT EXISTING DUNE CLIENT FILES"


def load_manager():
    spec = importlib.util.spec_from_file_location("client_deployment", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClientDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.game = self.root / "game"
        self.bin = self.game / "DuneSandbox/Binaries/Win64"
        self.paks = self.game / "DuneSandbox/Content/Paks"
        self.bin.mkdir(parents=True); self.paks.mkdir(parents=True)
        (self.bin / "DuneSandbox-Win64-Shipping.exe").write_bytes(b"current-game")
        (self.bin / "version.dll").write_bytes(b"original-version")
        self.loader = self.root / "loader.dll"; self.loader.write_bytes(b"new-loader")
        self.pak = self.root / "overlay.pak"; self.pak.write_bytes(b"overlay")
        self.state = self.root / "state"

    def tearDown(self): self.tmp.cleanup()

    def invoke(self, *args, ok=True):
        command = [str(SCRIPT), "--state-root", str(self.state), *map(str, args)]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok and result.returncode: self.fail(f"{command}\n{result.stdout}\n{result.stderr}")
        return result

    def files(self):
        return ["--file", f"{self.loader}::DuneSandbox/Binaries/Win64/version.dll",
                "--file", f"{self.pak}::DuneSandbox/Content/Paks/zzz_dash_test.pak"]

    def plan(self, deployment="test", files=None):
        result = self.invoke("plan", "--game-dir", self.game, "--deployment", deployment,
                             *(files or self.files()))
        return json.loads(result.stdout)

    def install(self, deployment="test", files=None, plan_sha256=None, confirm=CONFIRM, ok=True):
        files = files or self.files()
        if plan_sha256 is None:
            plan_sha256 = self.plan(deployment, files)["planSha256"]
        return self.invoke("install", "--game-dir", self.game, "--deployment", deployment,
                           *files, "--expect-plan-sha256", plan_sha256,
                           "--confirm", confirm, ok=ok)

    def test_plan_is_non_mutating(self):
        result = self.invoke("plan", "--game-dir", self.game, "--deployment", "test", *self.files())
        self.assertTrue(json.loads(result.stdout)["mutationRequired"])
        self.assertFalse(self.state.exists())
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"original-version")

    def test_install_verify_and_rollback(self):
        self.install()
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"new-loader")
        self.assertEqual((self.paks / "zzz_dash_test.pak").read_bytes(), b"overlay")
        manifest=json.loads((self.state/"test/manifest.json").read_text())
        self.assertEqual(manifest["status"],"installed")
        self.assertTrue((self.state/"test/backups/DuneSandbox/Binaries/Win64/version.dll").is_file())
        self.assertEqual(self.invoke("verify","--deployment","test").returncode,0)
        self.invoke("rollback","--deployment","test","--confirm",CONFIRM)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"original-version")
        self.assertFalse((self.paks/"zzz_dash_test.pak").exists())

    def test_confirmation_and_target_allowlist(self):
        result=self.install("bad",confirm="yes",ok=False)
        self.assertNotEqual(result.returncode,0); self.assertFalse(self.state.exists())
        result=self.invoke("plan","--game-dir",self.game,"--deployment","bad","--file",f"{self.pak}::DuneSandbox/Content/Paks/Systems.pak",ok=False)
        self.assertNotEqual(result.returncode,0)

    def test_plan_rejects_non_file_and_symlink_targets(self):
        (self.bin / "version.dll").unlink()
        (self.bin / "version.dll").mkdir()
        result = self.invoke("plan", "--game-dir", self.game, "--deployment", "directory",
                             *self.files(), ok=False)
        self.assertIn("not a regular file", result.stderr)
        (self.bin / "version.dll").rmdir()
        real = self.bin / "real-version.dll"
        real.write_bytes(b"original-version")
        (self.bin / "version.dll").symlink_to(real.name)
        result = self.invoke("plan", "--game-dir", self.game, "--deployment", "symlink",
                             *self.files(), ok=False)
        self.assertIn("path contains a symlink", result.stderr)

    def test_rollback_refuses_drift(self):
        self.install()
        (self.bin/"version.dll").write_bytes(b"foreign-change")
        result=self.invoke("rollback","--deployment","test","--confirm",CONFIRM,ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"foreign-change")

    def test_active_target_collision_is_rejected(self):
        self.install("one")
        result=self.install("two",ok=False)
        self.assertNotEqual(result.returncode,0)

    def test_concurrent_installs_serialize_and_only_one_can_own_targets(self):
        plans = {name: self.plan(name) for name in ("one", "two")}
        processes = []
        for name in ("one", "two"):
            command = [str(SCRIPT), "--state-root", str(self.state), "install",
                       "--game-dir", str(self.game), "--deployment", name,
                       *map(str, self.files()), "--expect-plan-sha256", plans[name]["planSha256"],
                       "--confirm", CONFIRM]
            processes.append(subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        results = [process.communicate() + (process.returncode,) for process in processes]
        self.assertEqual(sorted(result[2] == 0 for result in results), [False, True])
        statuses = [json.loads((self.state / name / "manifest.json").read_text())["status"]
                    for name in ("one", "two") if (self.state / name / "manifest.json").is_file()]
        self.assertEqual(statuses, ["installed"])
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"new-loader")

    def test_game_update_invalidates_verify_and_rollback(self):
        self.install()
        (self.bin/"DuneSandbox-Win64-Shipping.exe").write_bytes(b"updated-game")
        self.assertNotEqual(self.invoke("verify","--deployment","test",ok=False).returncode,0)
        result=self.invoke("rollback","--deployment","test","--confirm",CONFIRM,ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"new-loader")

    def test_install_is_bound_to_reviewed_plan(self):
        plan = self.plan()
        self.loader.write_bytes(b"changed-after-review")
        result = self.install(plan_sha256=plan["planSha256"], ok=False)
        self.assertIn("reviewed plan mismatch", result.stderr)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"original-version")
        self.assertFalse(self.state.exists())

    def test_reviewed_plan_file_drives_install_without_repeating_paths(self):
        plan = self.plan()
        receipt = self.root / "reviewed-plan.json"
        receipt.write_text(json.dumps(plan))
        self.invoke("install", "--reviewed-plan", receipt, "--confirm", CONFIRM)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"new-loader")
        self.assertEqual(self.invoke("verify", "--deployment", "test").returncode, 0)

    def test_tampered_reviewed_plan_file_is_rejected(self):
        plan = self.plan()
        plan["gameRoot"] = "/tmp/different-game"
        receipt = self.root / "tampered-plan.json"
        receipt.write_text(json.dumps(plan))
        result = self.invoke("install", "--reviewed-plan", receipt, "--confirm", CONFIRM, ok=False)
        self.assertIn("reviewed plan checksum is invalid", result.stderr)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"original-version")

    def test_verify_and_rollback_refuse_corrupt_backup_without_partial_restore(self):
        second = self.root / "lua54.dll"; second.write_bytes(b"original-lua")
        staged = self.root / "new-lua.dll"; staged.write_bytes(b"new-lua")
        (self.bin / "lua54.dll").write_bytes(b"original-lua")
        files = self.files() + ["--file", f"{staged}::DuneSandbox/Binaries/Win64/lua54.dll"]
        self.install(files=files)
        backup = self.state / "test/backups/DuneSandbox/Binaries/Win64/version.dll"
        backup.write_bytes(b"corrupt")
        verify = self.invoke("verify", "--deployment", "test", ok=False)
        self.assertEqual(json.loads(verify.stdout)["backupSetHealthy"], False)
        rollback = self.invoke("rollback", "--deployment", "test", "--confirm", CONFIRM, ok=False)
        self.assertIn("backups drifted", rollback.stderr)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"new-loader")
        self.assertEqual((self.bin / "lua54.dll").read_bytes(), b"new-lua")

    def test_corrupt_active_manifest_fails_closed(self):
        corrupt = self.state / "broken"
        corrupt.mkdir(parents=True)
        (corrupt / "manifest.json").write_text("{}")
        result = self.invoke("plan", "--game-dir", self.game, "--deployment", "test",
                             *self.files(), ok=False)
        self.assertIn("cannot safely evaluate active deployments", result.stderr)

    def test_manifest_target_tampering_is_rejected(self):
        self.install()
        path = self.state / "test/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"][0]["target"] = "/tmp/not-the-game/version.dll"
        path.write_text(json.dumps(manifest))
        result = self.invoke("verify", "--deployment", "test", ok=False)
        self.assertIn("target does not match", result.stderr)

    def test_running_client_detection_reads_process_cmdline(self):
        proc = self.root / "proc"
        (proc / "321").mkdir(parents=True)
        (proc / "321/cmdline").write_bytes(b"wine\0DuneSandbox-Win64-Shipping.exe\0")
        (proc / "654").mkdir(parents=True)
        (proc / "654/cmdline").write_bytes(b"unrelated\0")
        self.assertEqual(
            load_manager().running_client_processes(proc),
            [{"pid": 321, "command": "wine DuneSandbox-Win64-Shipping.exe"}],
        )

    def test_adopt_legacy_install_then_rollback(self):
        original=self.root/"original-version.dll"; original.write_bytes(b"original-version")
        (self.bin/"version.dll").write_bytes(b"legacy-probe")
        sidecar=self.bin/"dune-win-client-probe.env"; sidecar.write_bytes(b"legacy-sidecar")
        self.invoke("adopt","--game-dir",self.game,"--deployment","legacy",
                    "--installed",f"DuneSandbox/Binaries/Win64/version.dll::{original}",
                    "--installed","DuneSandbox/Binaries/Win64/dune-win-client-probe.env::ABSENT",
                    "--confirm",ADOPT_CONFIRM)
        self.assertEqual(self.invoke("verify","--deployment","legacy").returncode,0)
        self.invoke("rollback","--deployment","legacy","--confirm",CONFIRM)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"original-version")
        self.assertFalse(sidecar.exists())

    def test_adopt_preparation_failure_removes_orphan_state(self):
        manager = load_manager()
        original = self.root / "original-version.dll"; original.write_bytes(b"original-version")
        (self.bin / "version.dll").write_bytes(b"legacy-probe")
        args = SimpleNamespace(confirm=ADOPT_CONFIRM, deployment="legacy", game_dir=str(self.game),
                               state_root=str(self.state),
                               installed=[f"DuneSandbox/Binaries/Win64/version.dll::{original}"])
        with mock.patch.object(manager, "require_client_stopped"), \
             mock.patch.object(manager, "copy_atomic", side_effect=RuntimeError("injected backup failure")):
            with self.assertRaisesRegex(RuntimeError, "injected backup failure"):
                manager.adopt(args)
        self.assertFalse((self.state / "legacy").exists())

    def test_failed_partial_rollback_is_retryable(self):
        staged = self.root / "new-lua.dll"; staged.write_bytes(b"new-lua")
        (self.bin / "lua54.dll").write_bytes(b"original-lua")
        files = ["--file", f"{self.loader}::DuneSandbox/Binaries/Win64/version.dll",
                 "--file", f"{staged}::DuneSandbox/Binaries/Win64/lua54.dll"]
        self.install(files=files)
        manager = load_manager()
        real_copy = manager.copy_atomic
        calls = 0

        def fail_second_restore(source, target, mode=0o644):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected restore failure")
            return real_copy(source, target, mode)

        args = SimpleNamespace(confirm=CONFIRM, deployment="test", state_root=str(self.state))
        with mock.patch.object(manager, "require_client_stopped"), \
             mock.patch.object(manager, "copy_atomic", side_effect=fail_second_restore):
            with self.assertRaisesRegex(RuntimeError, "rollback incomplete"):
                manager.rollback(args)
        manifest = json.loads((self.state / "test/manifest.json").read_text())
        self.assertEqual(manifest["status"], "failed-rollback-required")
        self.assertEqual((self.bin / "lua54.dll").read_bytes(), b"original-lua")
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"new-loader")
        self.invoke("rollback", "--deployment", "test", "--confirm", CONFIRM)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"original-version")
        self.assertEqual((self.bin / "lua54.dll").read_bytes(), b"original-lua")
        self.assertEqual(json.loads((self.state / "test/manifest.json").read_text())["status"], "rolled-back")

    def test_audit_reports_clean_active_state(self):
        self.install()
        result = self.invoke("audit")
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"], {"activeCount": 1, "attentionCount": 0, "deploymentCount": 1})
        self.assertTrue(report["deployments"][0]["backupSetHealthy"])

    def test_audit_reports_orphans_and_invalid_manifests(self):
        orphan = self.state / "orphan"; orphan.mkdir(parents=True)
        self.state.chmod(0o700)
        orphan.chmod(0o700)
        broken = self.state / "broken"; broken.mkdir(mode=0o700)
        broken_manifest = broken / "manifest.json"; broken_manifest.write_text("{}")
        broken_manifest.chmod(0o600)
        result = self.invoke("audit", ok=False)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual({issue["code"] for issue in report["issues"]},
                         {"orphan-state-directory", "invalid-manifest"})

    def test_audit_detects_duplicate_active_ownership(self):
        self.install("one")
        first = json.loads((self.state / "one/manifest.json").read_text())
        first["deploymentId"] = "two"
        second = self.state / "two"; second.mkdir()
        (second / "manifest.json").write_text(json.dumps(first))
        result = self.invoke("audit", ok=False)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        issue = next(issue for issue in report["issues"] if issue["code"] == "duplicate-active-owner")
        self.assertEqual(issue["deployments"], ["one", "two"])

    def test_audit_rejects_state_symlinks_and_status_rejects_missing_id(self):
        self.state.mkdir(mode=0o700)
        external = self.root / "external"; external.mkdir()
        (self.state / "linked").symlink_to(external, target_is_directory=True)
        result = self.invoke("audit", ok=False)
        self.assertIn("unexpected-state-symlink", result.stdout)
        missing = self.invoke("status", "--deployment", "missing", ok=False)
        self.assertIn("deployment manifest not found", missing.stderr)

    def test_audit_reports_private_backup_permissions(self):
        self.install()
        backup = self.state / "test/backups/DuneSandbox/Binaries/Win64/version.dll"
        backup.chmod(0o644)
        result = self.invoke("audit", ok=False)
        report = json.loads(result.stdout)
        issue = next(issue for issue in report["issues"]
                     if issue["code"] == "private-state-permissions" and issue["path"] == str(backup))
        self.assertEqual(issue["action"], f"chmod 600 {backup}")

    def test_interrupted_prepared_install_can_converge_to_original_state(self):
        self.install()
        manifest_path = self.state / "test/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["status"] = "prepared"
        manifest_path.write_text(json.dumps(manifest))
        (self.bin / "version.dll").write_bytes(b"original-version")
        self.invoke("rollback", "--deployment", "test", "--confirm", CONFIRM)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"original-version")
        self.assertFalse((self.paks / "zzz_dash_test.pak").exists())
        self.assertEqual(json.loads(manifest_path.read_text())["status"], "rolled-back")


if __name__ == "__main__": unittest.main()
