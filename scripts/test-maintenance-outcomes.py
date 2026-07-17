#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import maintenance_outcomes


class MaintenanceOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.secret = b"m" * 64
        self.store = maintenance_outcomes.Store(self.root / "evidence", self.secret, retention=10)

    def tearDown(self):
        self.temp.cleanup()

    def job(self, suffix="one", **updates):
        value = {
            "id": f"job_{suffix}", "target": "all", "action": "restart",
            "updatePolicy": "certified", "runAt": 1000, "execute": True,
            "backup": True, "requireSoftDisconnect": True, "principalId": "owner",
        }
        value.update(updates)
        return value

    def passing_result(self):
        return {
            "ok": True, "action": "restart", "serviceRecovered": True,
            "updateApplied": False,
            "updatePreflight": {
                "ok": True, "policy": "certified", "effectivePolicy": "certified",
                "durationMs": 10, "candidate": {
                    "status": "update-available", "fingerprint": "f" * 64,
                    "imageTag": "dune_sb_1_4_11_0", "currentImageTag": "dune_sb_1_4_10_0",
                    "updateRequired": True,
                },
                "receiptId": "update-readiness-" + "a" * 32, "receiptSha256": "b" * 64,
            },
            "disconnect": {"ok": True, "durationMs": 20},
            "stop": {"ok": True, "returncode": 0, "durationMs": 30},
            "backup": {
                "ok": True, "verified": True, "durationMs": 40,
                "verification": {"ok": True, "path": "admin-panel/maintenance/fixture"},
            },
            "update": {"ok": True, "returncode": 0, "durationMs": 50},
            "start": {"ok": True, "returncode": 0, "durationMs": 60},
            "online": {"ok": True, "durationMs": 70},
        }

    def test_passed_receipt_is_signed_semantic_and_metric_visible(self):
        recorded = self.store.record(self.job(), self.passing_result(), 1000, 1002)
        receipt = recorded["document"]["receipt"]
        self.assertTrue(recorded["verification"]["ok"])
        self.assertEqual("passed", receipt["outcome"])
        self.assertTrue(receipt["backup"]["verified"])
        self.assertTrue(receipt["serviceRecovered"])
        self.assertFalse(receipt["gameDataMutationExecuted"])
        self.assertEqual(0o600, pathlib.Path(recorded["evidencePath"]).stat().st_mode & 0o777)
        self.assertIn("dash_maintenance_outcome_latest_ready 1", self.store.prometheus())
        self.assertIn("dash_maintenance_outcome_latest_backup_verified 1", self.store.prometheus())

    def test_backup_failure_records_failed_current_build_recovery(self):
        result = self.passing_result()
        result.update({
            "ok": False, "updateApplied": False, "updateSuppressedByBackupFailure": True,
            "error": "maintenance backup verification failed",
            "warnings": ["maintenance backup verification failed"],
        })
        result["backup"] = {
            "ok": False, "verified": False, "durationMs": 40,
            "verification": {"ok": False, "path": "admin-panel/maintenance/bad"},
        }
        result["update"] = {"ok": True, "skipped": True, "durationMs": 0}
        recorded = self.store.record(self.job("backup"), result, 1000, 1002)
        receipt = recorded["document"]["receipt"]
        self.assertTrue(recorded["verification"]["ok"])
        self.assertEqual("failed", receipt["outcome"])
        self.assertEqual("current", receipt["effectiveUpdatePolicy"])
        self.assertTrue(receipt["serviceRecovered"])
        self.assertTrue(receipt["candidateUpdateBlocked"])
        self.assertFalse(receipt["updateAttempted"])
        self.assertFalse(receipt["backup"]["verified"])

    def test_cryptographic_and_semantic_tampering_fail(self):
        document = self.store.record(self.job("tamper"), self.passing_result(), 1000, 1002)["document"]
        tampered = json.loads(json.dumps(document))
        tampered["receipt"]["ready"] = False
        self.assertFalse(maintenance_outcomes.verify_signed_document(tampered, self.secret)["ok"])

        resigned_receipt = json.loads(json.dumps(document["receipt"]))
        resigned_receipt.pop("receiptSha256")
        resigned_receipt["ready"] = False
        semantic = maintenance_outcomes.signed_document(resigned_receipt, self.secret, generated_at=1002)
        self.assertFalse(maintenance_outcomes.verify_signed_document(semantic, self.secret)["ok"])

    def test_early_failure_preserves_required_but_unattempted_stages(self):
        result = {
            "ok": False, "action": "restart", "serviceRecovered": False,
            "error": "preflight failed", "updatePreflight": {"ok": False, "policy": "certified", "durationMs": 5},
        }
        recorded = self.store.record(self.job("early"), result, 1000, 1001)
        receipt = recorded["document"]["receipt"]
        self.assertTrue(recorded["verification"]["ok"])
        self.assertTrue(receipt["stages"]["stop"]["required"])
        self.assertFalse(receipt["stages"]["stop"]["attempted"])
        self.assertFalse(receipt["stages"]["stop"]["ok"])

    def test_retention_is_bounded_and_invalid_history_drops_collector(self):
        for index in range(12):
            self.store.record(self.job(str(index)), self.passing_result(), 1000 + index, 1001 + index)
        self.assertEqual(10, len(list((self.root / "evidence").glob("maintenance-outcome-*.signed.json"))))
        newest = next(iter(self.store._paths()))
        document = json.loads(newest.read_text(encoding="utf-8"))
        document["signature"] = "0" * 64
        newest.write_text(json.dumps(document), encoding="utf-8")
        status = self.store.status(limit=10)
        self.assertFalse(status["ok"])
        self.assertIn("dash_maintenance_outcome_collector_up 0", self.store.prometheus())

    def test_shell_backup_verifier_dispatches_maintenance_schema(self):
        backup = self.root / "backup"
        backup.mkdir()
        (backup / "fixture.dump").write_bytes(b"fixture")
        evidence = self.store.record(self.job("archive"), self.passing_result(), 1000, 1001)["evidencePath"]
        with tarfile.open(backup / "operator-evidence.tgz", "w:gz") as archive:
            archive.add(evidence, arcname=f"operator-evidence/{pathlib.Path(evidence).name}")
        secret_file = self.root / "config" / "secrets" / "change-intelligence-hmac.secret"
        secret_file.parent.mkdir(parents=True)
        secret_file.write_text(self.secret.decode() + "\n", encoding="utf-8")
        secret_file.chmod(0o600)
        with tarfile.open(backup / "config-and-env.tgz", "w:gz") as archive:
            archive.add(secret_file, arcname="config/secrets/change-intelligence-hmac.secret")
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        pg_restore = fake_bin / "pg_restore"
        pg_restore.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        pg_restore.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment.get('PATH', '')}"
        completed = subprocess.run(
            ["bash", str(ROOT / "scripts" / "verify-backup.sh"), str(backup)],
            cwd=ROOT, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("OK 1 portable signed operator evidence capsule(s)", completed.stdout)


if __name__ == "__main__":
    unittest.main()
