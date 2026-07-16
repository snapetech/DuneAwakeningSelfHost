#!/usr/bin/env python3
import copy
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest

import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import desired_state


def container(service="admin-panel", image="image:v1", image_id="sha256:one", token="secret-one", privileged=False):
    return {
        "Name": f"/{service}", "Image": image_id,
        "Config": {
            "Image": image, "Entrypoint": ["/entry"], "Cmd": ["serve"], "WorkingDir": "/workspace", "User": "1000",
            "Env": [f"TOKEN={token}", "MODE=production"],
            "Labels": {"com.docker.compose.service": service},
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "unless-stopped"}, "Privileged": privileged,
            "ReadonlyRootfs": True, "NetworkMode": "project_default", "CapAdd": [], "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"], "PidsLimit": 128, "Memory": 1024,
            "MemorySwap": 1024, "NanoCpus": 1000000000, "CpusetCpus": "0-3",
        },
        "Mounts": [{"Destination": "/workspace/config", "Type": "bind", "RW": False, "Source": "/host/config"}],
        "NetworkSettings": {"Networks": {"project_default": {"IPAddress": "172.31.0.9", "MacAddress": "02:42:ac:1f:00:09"}}},
    }


class DesiredStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / "admin").mkdir()
        (self.root / "config" / "secrets").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / ".env").write_text("TOKEN=not-returned\n", encoding="utf-8")
        (self.root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (self.root / "admin" / "admin_panel.py").write_text("print('ok')\n", encoding="utf-8")
        (self.root / "scripts" / "restart-target.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        self.policy_path = self.root / "config" / "desired-state.json"
        self.policy_path.write_text(json.dumps({
            "schemaVersion": 1, "pollSeconds": 60, "observationRetentionDays": 90,
            "maxFiles": 100, "maxFileBytes": 1000000, "maxTotalBytes": 10000000,
            "trackFileModes": True, "trackContainers": True,
            "includePatterns": [".env", "compose*.yaml", "admin/**/*", "scripts/*", "config/**/*"],
            "excludePatterns": ["config/desired-state.key"],
            "requiredPaths": [".env", "compose.yaml", "admin/admin_panel.py", "scripts/restart-target.sh"],
            "criticalPatterns": [".env", "compose*.yaml", "admin/**/*"],
        }), encoding="utf-8")
        self.secret_path = self.root / "config" / "desired-state.key"
        self.secret_path.write_text("a" * 64 + "\n", encoding="utf-8")
        self.secret_path.chmod(0o600)
        self.database = self.root / "backups" / "desired-state.sqlite3"
        self.store = desired_state.Store(self.database, self.policy_path, self.secret_path)
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, containers=None, at=1000):
        return desired_state.build_snapshot(self.root, self.store.policy, containers if containers is not None else [container()], self.store.secret, observed_at=at)

    def test_policy_secret_and_private_modes(self):
        self.assertEqual(self.store.policy["pollSeconds"], 60)
        self.assertEqual(self.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.database.parent.stat().st_mode & 0o777, 0o700)
        self.secret_path.chmod(0o644)
        with self.assertRaises(PermissionError):
            desired_state.read_secret(self.secret_path)

    def test_snapshot_never_contains_plaintext_secrets_or_mount_sources(self):
        snapshot = self.snapshot()
        encoded = json.dumps(snapshot)
        self.assertNotIn("not-returned", encoded)
        self.assertNotIn("secret-one", encoded)
        self.assertNotIn("/host/config", encoded)
        self.assertEqual(snapshot["fileCount"], 5)
        self.assertIn("TOKEN", snapshot["containers"]["admin-panel"]["envHmacs"])

    def test_seal_attest_and_hmac_integrity(self):
        baseline = self.store.seal(self.snapshot(), "operator", "known-good deploy", at=1000)
        result = self.store.observe(self.snapshot(at=1060), at=1060)
        self.assertTrue(result["sealed"])
        self.assertEqual(result["driftCount"], 0)
        status = self.store.status()
        self.assertEqual(status["state"], "attested")
        self.assertEqual(status["baseline"]["id"], baseline["baselineId"])
        self.assertTrue(status["integrity"]["ok"])

    def test_file_and_container_drift_open_acknowledge_resolve_and_reopen(self):
        self.store.seal(self.snapshot(), "operator", "baseline", at=1000)
        (self.root / ".env").write_text("TOKEN=changed\n", encoding="utf-8")
        drifted = self.snapshot([container(image="image:v2", image_id="sha256:two", privileged=True)], at=1060)
        observed = self.store.observe(drifted, at=1060)
        self.assertEqual(observed["driftCount"], 2)
        self.assertEqual(observed["criticalCount"], 2)
        status = self.store.status()
        self.assertEqual(status["state"], "drift")
        subjects = {row["subject"] for row in status["openFindings"]}
        self.assertEqual(subjects, {".env", "admin-panel"})
        finding = status["openFindings"][0]
        self.store.acknowledge(finding["id"], "operator", "reviewing", at=1070)
        acknowledged = next(row for row in self.store.status()["openFindings"] if row["id"] == finding["id"])
        self.assertEqual(acknowledged["note"], "reviewing")
        (self.root / ".env").write_text("TOKEN=not-returned\n", encoding="utf-8")
        self.store.observe(self.snapshot(at=1080), at=1080)
        self.assertEqual(self.store.status()["state"], "attested")
        self.store.observe(drifted, at=1090)
        reopened = self.store.status()["openFindings"]
        self.assertEqual(len(reopened), 2)
        self.assertTrue(all(row["acknowledgedAt"] is None for row in reopened))

    def test_missing_required_file_is_critical_drift(self):
        self.store.seal(self.snapshot(), "operator", "baseline", at=1000)
        (self.root / "compose.yaml").unlink()
        snapshot = self.snapshot(at=1060)
        result = self.store.observe(snapshot, at=1060)
        self.assertEqual(result["criticalCount"], 1)
        row = self.store.status()["openFindings"][0]
        self.assertEqual(row["details"]["after"]["kind"], "missing")

    def test_maintenance_suppresses_alert_metric_not_evidence(self):
        self.store.seal(self.snapshot(), "operator", "baseline", at=1000)
        (self.root / ".env").write_text("DRIFT=yes\n", encoding="utf-8")
        self.store.observe(self.snapshot(at=1060), maintenance_active=True, at=1060)
        metrics = self.store.prometheus()
        self.assertIn("dash_desired_state_open_critical_drift 1", metrics)
        self.assertIn("dash_desired_state_alertable_critical_drift 0", metrics)
        self.assertIn("dash_desired_state_maintenance_active 1", metrics)

    def test_reseal_preserves_history_and_resolves_findings(self):
        first = self.store.seal(self.snapshot(), "operator", "first", at=1000)
        (self.root / ".env").write_text("DRIFT=yes\n", encoding="utf-8")
        changed = self.snapshot(at=1060)
        self.store.observe(changed, at=1060)
        second = self.store.seal(changed, "operator", "approved change", at=1070)
        status = self.store.status()
        self.assertNotEqual(first["baselineId"], second["baselineId"])
        self.assertEqual(status["state"], "attested")
        self.assertEqual(len([row for row in status["events"] if row["eventType"] == "baseline-sealed"]), 2)

    def test_tampering_and_missing_triggers_fail_verification(self):
        self.store.seal(self.snapshot(), "operator", "baseline", at=1000)
        connection = sqlite3.connect(self.database)
        connection.execute("drop trigger desired_state_baselines_no_update")
        connection.execute("drop trigger desired_state_baselines_no_delete")
        connection.execute("update baselines set signature='bad'")
        connection.commit()
        connection.close()
        self.assertFalse(self.store.verify()["ok"])

    def test_backup_is_consistent_and_private(self):
        self.store.seal(self.snapshot(), "operator", "baseline", at=1000)
        target = self.root / "archive" / "desired-state.sqlite3"
        result = self.store.backup(target)
        self.assertEqual(result["integrity"], "ok")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_bounds_duplicate_services_and_unsealed_state(self):
        unsealed = self.store.observe(self.snapshot(at=1000), at=1000)
        self.assertFalse(unsealed["sealed"])
        self.assertEqual(self.store.status()["state"], "unsealed")
        with self.assertRaises(ValueError):
            desired_state.build_snapshot(self.root, self.store.policy, [container(), container()], self.store.secret)


if __name__ == "__main__":
    unittest.main()
