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

import creator_canary


class CreatorCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="test-creator-canary-")
        self.addCleanup(self.temporary.cleanup)
        self.evidence = pathlib.Path(self.temporary.name) / "evidence"
        self.secret = b"c" * 64
        self.store = creator_canary.Store(
            self.evidence, self.secret, retention=20, max_age_seconds=3600,
        )

    def run_canary(self, **kwargs):
        return creator_canary.run_canary(
            ROOT, self.store, principal_id="test-operator", **kwargs,
        )

    def test_full_disposable_lifecycle_is_signed_current_and_isolated(self):
        result = self.run_canary()
        receipt = result["document"]["receipt"]
        self.assertIsNone(result["error"])
        self.assertTrue(receipt["ready"])
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(receipt["evidence"]["inputFiles"], len(creator_canary.INPUT_FILES))
        self.assertEqual(receipt["evidence"]["galleryDesigns"], 1)
        self.assertEqual(receipt["evidence"]["galleryRatings"], 1)
        self.assertGreater(receipt["evidence"]["cosmeticCatalogItems"], 300)
        self.assertEqual(receipt["evidence"]["addonPermissions"], 1)
        self.assertGreaterEqual(receipt["evidence"]["retirementBlockedConditions"], 5)
        self.assertTrue(receipt["isolation"]["temporaryStateCreated"])
        self.assertTrue(receipt["isolation"]["temporaryStateRemoved"])
        for key in (
            "liveGalleryOpened", "liveConfigWritten", "gameDatabaseOpened",
            "playerDataWritten", "gameMapLifecycleInvoked", "externalNetworkCalled",
        ):
            self.assertFalse(receipt["isolation"][key], key)
        current = creator_canary.input_manifest(ROOT)["sha256"]
        status = self.store.status(current)
        self.assertTrue(status["ok"])
        self.assertTrue(status["currentReady"])
        self.assertEqual(status["latest"]["id"], receipt["id"])
        self.assertEqual(pathlib.Path(result["evidencePath"]).stat().st_mode & 0o077, 0)
        metrics = self.store.prometheus(current)
        self.assertIn("dash_creator_canary_collector_up 1", metrics)
        self.assertIn("dash_creator_canary_current_ready 1", metrics)
        self.assertNotIn("{", metrics)

    def test_input_drift_and_age_expiry_remove_readiness_without_invalidating_receipt(self):
        result = self.run_canary()
        receipt = result["document"]["receipt"]
        drift = self.store.status("f" * 64)
        self.assertTrue(drift["ok"])
        self.assertFalse(drift["currentReady"])
        self.assertFalse(drift["latest"]["verification"]["inputsCurrent"])
        stale = self.store.status(
            receipt["inputsSha256"], now=creator_canary.epoch(receipt["completedAt"]) + 3601,
        )
        self.assertTrue(stale["ok"])
        self.assertFalse(stale["currentReady"])
        self.assertFalse(stale["latest"]["verification"]["ageCurrent"])

    def test_signature_and_semantic_tampering_are_rejected(self):
        result = self.run_canary()
        document = result["document"]
        signature_tamper = copy.deepcopy(document)
        signature_tamper["receipt"]["evidence"]["galleryDesigns"] = 99
        checked = creator_canary.verify_signed_document(signature_tamper, self.secret)
        self.assertFalse(checked["ok"])
        self.assertIn("signature", checked["error"])

        semantic_tamper = copy.deepcopy(document["receipt"])
        semantic_tamper["ready"] = False
        resigned = creator_canary.signed_document(semantic_tamper, self.secret)
        checked = creator_canary.verify_signed_document(resigned, self.secret)
        self.assertFalse(checked["ok"])
        self.assertIn("verdict", checked["error"])

        future = copy.deepcopy(document["receipt"])
        future["startedAt"] = creator_canary.iso(1000)
        future["completedAt"] = creator_canary.iso(1001)
        future["durationMs"] = 1000
        resigned = creator_canary.signed_document(future, self.secret, generated_at=1001)
        checked = creator_canary.verify_signed_document(resigned, self.secret, now=700)
        self.assertFalse(checked["ok"])
        self.assertIn("future", checked["error"])

    def test_failed_execution_still_records_a_valid_non_ready_receipt_and_cleans_up(self):
        with mock.patch.object(
            creator_canary.gameplay_presets, "plan",
            return_value={"changed": False, "dryRun": True},
        ):
            result = self.run_canary()
        receipt = result["document"]["receipt"]
        self.assertFalse(receipt["ready"])
        self.assertIn("no effective disposable change", result["error"])
        self.assertTrue(receipt["checks"]["temporaryStateRemoved"])
        self.assertTrue(receipt["isolation"]["temporaryStateRemoved"])
        verification = creator_canary.verify_signed_document(result["document"], self.secret)
        self.assertTrue(verification["ok"])
        self.assertFalse(verification["currentReady"])

    def test_injected_addon_fixture_preserves_permission_and_digest_fail_closed_guards(self):
        addon_id, index_url, fetcher = creator_canary._addon_fixture()
        addon_root = pathlib.Path(self.temporary.name) / "addon-adversarial"
        with self.assertRaisesRegex(PermissionError, "explicit approval"):
            creator_canary.addon_admin.install(
                addon_root, addon_id, [], index_url=index_url, fetcher=fetcher,
            )
        self.assertEqual([], creator_canary.addon_admin.list_installed(addon_root)["addons"])

        def corrupt_fetcher(url, maximum, timeout=10):
            value = fetcher(url, maximum, timeout)
            return b"corrupt archive" if url.endswith("canary.zip") else value

        with self.assertRaisesRegex(ValueError, "SHA-256"):
            creator_canary.addon_admin.install(
                addon_root, addon_id, ["ops:read"],
                index_url=index_url, fetcher=corrupt_fetcher,
            )
        self.assertEqual([], creator_canary.addon_admin.list_installed(addon_root)["addons"])

    def test_manifest_is_exact_and_changes_when_a_bound_input_changes(self):
        current = creator_canary.input_manifest(ROOT)
        self.assertEqual([row["path"] for row in current["files"]], list(creator_canary.INPUT_FILES))
        with tempfile.TemporaryDirectory(prefix="creator-canary-workspace-") as directory:
            workspace = pathlib.Path(directory)
            for relative in creator_canary.INPUT_FILES:
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            copied = creator_canary.input_manifest(workspace)
            self.assertEqual(copied["sha256"], current["sha256"])
            catalog = workspace / "config" / "gameplay-presets.json"
            payload = json.loads(catalog.read_text(encoding="utf-8"))
            payload["canaryTestMarker"] = True
            catalog.write_text(json.dumps(payload), encoding="utf-8")
            self.assertNotEqual(creator_canary.input_manifest(workspace)["sha256"], current["sha256"])
            linked = workspace / "admin" / "addon_admin.py"
            linked.unlink()
            linked.symlink_to("base_creator.py")
            with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
                creator_canary.input_manifest(workspace)

    def test_backup_deployment_readiness_metrics_and_alerts_are_manifest_bound(self):
        panel = (ROOT / "admin" / "admin_panel.py").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts" / "verify-backup.sh").read_text(encoding="utf-8")
        deployment = (ROOT / "scripts" / "deployment-assurance.py").read_text(encoding="utf-8")
        push = (ROOT / "scripts" / "push-assured-control-plane.sh").read_text(encoding="utf-8")
        alerts = (ROOT / "config" / "metrics" / "rules" / "dash.yml").read_text(encoding="utf-8")
        catalog = json.loads((ROOT / "config" / "feature-readiness.json").read_text(encoding="utf-8"))
        feature = next(row for row in catalog["features"] if row["id"] == "creator-modding")
        self.assertEqual("operator-canary-pending", feature["canary"])
        self.assertEqual("creator-modding", feature["probe"])
        self.assertIn({"path": "admin/creator_canary.py", "minimumBytes": 1000}, feature["files"])
        for source in (panel, verifier):
            self.assertIn("creator_canary.verify_signed_document", source)
            self.assertIn("creator_canary.SCHEMA", source)
        for source in (deployment, push):
            for relative in (
                "admin/creator_canary.py", "admin/addon_admin.py", "admin/base_creator.py",
                "admin/base_retirement.py", "admin/cosmetics_admin.py", "admin/gameplay_presets.py",
            ):
                self.assertIn(relative, source)
        self.assertIn("dash_creator_canary_current_ready", panel)
        self.assertIn("DashCreatorCanaryCollectorInvalid", alerts)
        self.assertIn("DashCreatorCanaryNotCurrent", alerts)

    def test_shell_backup_verifier_dispatches_creator_schema(self):
        backup = pathlib.Path(self.temporary.name) / "backup"
        backup.mkdir()
        (backup / "fixture.dump").write_bytes(b"fixture")
        evidence = self.run_canary()["evidencePath"]
        with tarfile.open(backup / "operator-evidence.tgz", "w:gz") as archive:
            archive.add(evidence, arcname=f"operator-evidence/{pathlib.Path(evidence).name}")
        secret_file = pathlib.Path(self.temporary.name) / "config" / "secrets" / "change-intelligence-hmac.secret"
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
            ["bash", str(ROOT / "scripts" / "verify-backup.sh"), str(backup)],
            cwd=ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("OK 1 portable signed operator evidence capsule(s)", completed.stdout)


if __name__ == "__main__":
    unittest.main()
