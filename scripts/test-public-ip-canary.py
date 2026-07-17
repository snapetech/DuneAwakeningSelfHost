#!/usr/bin/env python3

import copy
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import access_control
import public_ip_canary


class PublicIpCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="test-public-ip-canary-")
        self.addCleanup(self.temporary.cleanup)
        self.evidence = pathlib.Path(self.temporary.name) / "evidence"
        self.secret = b"p" * 64
        self.store = public_ip_canary.Store(
            self.evidence, self.secret, retention=20, max_age_seconds=3600,
        )

    def run_canary(self, **kwargs):
        return public_ip_canary.run_canary(
            ROOT, self.store, principal_id="test-operator", **kwargs,
        )

    def test_complete_repair_lifecycle_is_signed_current_and_strictly_isolated(self):
        result = self.run_canary()
        receipt = result["document"]["receipt"]
        self.assertIsNone(result["error"])
        self.assertTrue(receipt["ready"])
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["evidence"]["inputFiles"], len(public_ip_canary.INPUT_FILES))
        self.assertEqual(receipt["evidence"]["environmentBackups"], 1)
        self.assertEqual(receipt["evidence"]["tlsBackupFiles"], 3)
        self.assertGreaterEqual(receipt["evidence"]["tlsSans"], 1)
        self.assertGreaterEqual(receipt["evidence"]["restartServices"], 4)
        self.assertEqual(receipt["evidence"]["timerIntervalMinutes"], 7)
        self.assertNotEqual(receipt["evidence"]["certificateSha256"], "0" * 64)
        self.assertTrue(receipt["isolation"]["temporaryStateCreated"])
        self.assertTrue(receipt["isolation"]["temporaryStateRemoved"])
        for key in (
            "liveEnvironmentWritten", "liveTlsWritten", "liveSystemdWritten",
            "liveStateDirectoryOpened", "gameMapLifecycleInvoked", "externalNetworkCalled",
        ):
            self.assertFalse(receipt["isolation"][key], key)
        current = public_ip_canary.input_manifest(ROOT)["sha256"]
        status = self.store.status(current)
        self.assertTrue(status["ok"])
        self.assertTrue(status["currentReady"])
        self.assertEqual(status["latest"]["id"], receipt["id"])
        self.assertEqual(pathlib.Path(result["evidencePath"]).stat().st_mode & 0o077, 0)
        metrics = self.store.prometheus(current)
        self.assertIn("dash_public_ip_canary_collector_up 1", metrics)
        self.assertIn("dash_public_ip_canary_current_ready 1", metrics)
        self.assertNotIn("{", metrics)

    def test_input_drift_and_expiry_remove_current_readiness(self):
        result = self.run_canary()
        receipt = result["document"]["receipt"]
        drift = self.store.status("f" * 64)
        self.assertTrue(drift["ok"])
        self.assertFalse(drift["currentReady"])
        self.assertFalse(drift["latest"]["verification"]["inputsCurrent"])
        stale = self.store.status(
            receipt["inputsSha256"],
            now=public_ip_canary.epoch(receipt["completedAt"]) + 3601,
        )
        self.assertTrue(stale["ok"])
        self.assertFalse(stale["currentReady"])
        self.assertFalse(stale["latest"]["verification"]["ageCurrent"])

    def test_signature_semantic_and_future_timestamp_tampering_fail_closed(self):
        result = self.run_canary()
        document = result["document"]
        signature_tamper = copy.deepcopy(document)
        signature_tamper["receipt"]["evidence"]["restartServices"] = 999
        checked = public_ip_canary.verify_signed_document(signature_tamper, self.secret)
        self.assertFalse(checked["ok"])
        self.assertIn("signature", checked["error"])

        semantic = copy.deepcopy(document["receipt"])
        semantic["ready"] = False
        checked = public_ip_canary.verify_signed_document(
            public_ip_canary.signed_document(semantic, self.secret), self.secret,
        )
        self.assertFalse(checked["ok"])
        self.assertIn("verdict", checked["error"])

        future = copy.deepcopy(document["receipt"])
        future.update({
            "startedAt": public_ip_canary.iso(1000),
            "completedAt": public_ip_canary.iso(1001),
            "durationMs": 1000,
        })
        checked = public_ip_canary.verify_signed_document(
            public_ip_canary.signed_document(future, self.secret, generated_at=1001),
            self.secret, now=700,
        )
        self.assertFalse(checked["ok"])
        self.assertIn("future", checked["error"])

    def test_failed_execution_records_a_valid_failure_receipt_and_removes_temp_state(self):
        with mock.patch.object(public_ip_canary, "_run", side_effect=ValueError("injected subprocess failure")):
            result = self.run_canary()
        receipt = result["document"]["receipt"]
        self.assertFalse(receipt["ready"])
        self.assertIn("injected subprocess failure", result["error"])
        self.assertTrue(receipt["checks"]["temporaryStateRemoved"])
        self.assertTrue(receipt["isolation"]["temporaryStateRemoved"])
        checked = public_ip_canary.verify_signed_document(result["document"], self.secret)
        self.assertTrue(checked["ok"])
        self.assertFalse(checked["currentReady"])

    def test_manifest_is_exact_drift_sensitive_and_rejects_symlinks(self):
        current = public_ip_canary.input_manifest(ROOT)
        self.assertEqual([row["path"] for row in current["files"]], list(public_ip_canary.INPUT_FILES))
        workspace = pathlib.Path(self.temporary.name) / "workspace"
        for relative in public_ip_canary.INPUT_FILES:
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        copied = public_ip_canary.input_manifest(workspace)
        self.assertEqual(current["sha256"], copied["sha256"])
        monitor = workspace / "scripts/public-ip-monitor.sh"
        monitor.write_text(monitor.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
        self.assertNotEqual(current["sha256"], public_ip_canary.input_manifest(workspace)["sha256"])
        canary = workspace / "admin/public_ip_canary.py"
        canary.unlink()
        canary.symlink_to("../scripts/public-ip-monitor.sh")
        with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
            public_ip_canary.input_manifest(workspace)

    def test_explicit_execution_capable_runtime_root_is_private_and_emptied(self):
        runtime = pathlib.Path(self.temporary.name) / "runtime"
        invocations = []

        def runner(arguments, *, cwd, environment, timeout):
            invocations.append((list(arguments), cwd, dict(environment), timeout))
            self.assertNotIn("DUNE_ADMIN_TOKEN", environment)
            return subprocess.run(
                arguments, cwd=cwd, env=environment, timeout=timeout,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )

        result = public_ip_canary.run_canary(
            ROOT, self.store, principal_id="test-runtime-root", work_root=runtime,
            runner=runner,
        )
        self.assertTrue(result["document"]["receipt"]["ready"])
        self.assertEqual(7, len(invocations))
        self.assertEqual(0o700, runtime.stat().st_mode & 0o777)
        self.assertEqual([], list(runtime.iterdir()))
        linked = pathlib.Path(self.temporary.name) / "linked-runtime"
        linked.symlink_to(runtime, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
            public_ip_canary.run_canary(
                ROOT, self.store, principal_id="test-runtime-root", work_root=linked,
            )

    def test_readiness_api_metrics_alerts_backup_and_deployment_are_bound(self):
        panel = (ROOT / "admin/admin_panel.py").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts/verify-backup.sh").read_text(encoding="utf-8")
        deployment = (ROOT / "scripts/deployment-assurance.py").read_text(encoding="utf-8")
        push = (ROOT / "scripts/push-assured-control-plane.sh").read_text(encoding="utf-8")
        alerts = (ROOT / "config/metrics/rules/dash.yml").read_text(encoding="utf-8")
        catalog = json.loads((ROOT / "config/feature-readiness.json").read_text(encoding="utf-8"))
        feature = next(row for row in catalog["features"] if row["id"] == "public-ip-repair")
        self.assertEqual("operator-canary-pending", feature["canary"])
        self.assertEqual("public-ip-monitor", feature["probe"])
        self.assertIn({"path": "admin/public_ip_canary.py", "minimumBytes": 1000}, feature["files"])
        for source in (panel, verifier):
            self.assertIn("public_ip_canary.verify_signed_document", source)
            self.assertIn("public_ip_canary.SCHEMA", source)
        for source in (deployment, push):
            for relative in public_ip_canary.INPUT_FILES:
                self.assertIn(relative, source)
        self.assertIn('"/api/ops/public-ip-canary"', panel)
        self.assertIn("dash_public_ip_canary_current_ready", panel)
        self.assertIn("dash_public_ip_monitor_armed", panel)
        self.assertIn("DashPublicIpCanaryCollectorInvalid", alerts)
        self.assertIn("DashPublicIpCanaryNotCurrent", alerts)
        self.assertIn("DashPublicIpMonitorNotArmed", alerts)
        for safeguard in (
            '"NetworkMode": "none"', '"ReadonlyRootfs": True',
            '"CapDrop": ["ALL"]', '"no-new-privileges:true"',
            '"PidsLimit": 128', '"NetworkDisabled": True',
        ):
            self.assertIn(safeguard, panel)
        self.assertNotIn('f"{DOCKER_SOCKET}:/var/run/docker.sock"', panel[panel.index("def public_ip_canary_container_runner"):panel.index("def run_public_ip_canary")])
        self.assertEqual(
            "infrastructure.write",
            access_control.required_capability("POST", "/api/ops/public-ip-canary"),
        )

    def test_shell_backup_verifier_dispatches_public_ip_schema(self):
        backup = pathlib.Path(self.temporary.name) / "backup"
        backup.mkdir()
        (backup / "fixture.dump").write_bytes(b"fixture")
        evidence = pathlib.Path(self.run_canary()["evidencePath"])
        with tarfile.open(backup / "operator-evidence.tgz", "w:gz") as archive:
            archive.add(evidence, arcname=f"operator-evidence/{evidence.name}")
        secret_file = pathlib.Path(self.temporary.name) / "config/secrets/change-intelligence-hmac.secret"
        secret_file.parent.mkdir(parents=True)
        secret_file.write_bytes(self.secret + b"\n")
        secret_file.chmod(0o600)
        with tarfile.open(backup / "config-and-env.tgz", "w:gz") as archive:
            archive.add(secret_file, arcname="config/secrets/change-intelligence-hmac.secret")
        fake_bin = pathlib.Path(self.temporary.name) / "bin"
        fake_bin.mkdir()
        pg_restore = fake_bin / "pg_restore"
        pg_restore.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        pg_restore.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment.get('PATH', '')}"
        completed = subprocess.run(
            ["bash", str(ROOT / "scripts/verify-backup.sh"), str(backup)],
            cwd=ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("OK 1 portable signed operator evidence capsule(s)", completed.stdout)


if __name__ == "__main__":
    unittest.main()
