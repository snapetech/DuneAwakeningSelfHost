#!/usr/bin/env python3

import copy
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import operations_briefing


def source(source_id, *, healthy=True, severity="warning", state="ready"):
    return {
        "id": source_id, "title": source_id.replace("-", " ").title(),
        "state": state, "healthy": healthy, "severity": severity,
        "detail": "Evidence-backed detail", "surface": "infrastructure",
    }


class OperationsBriefingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="test-operations-briefing-")
        self.addCleanup(self.temporary.cleanup)
        self.secret = b"b" * 64
        self.store = operations_briefing.Store(pathlib.Path(self.temporary.name) / "evidence", self.secret, retention=10, max_age_seconds=3600)

    def test_compile_prioritizes_failures_and_scores_without_executing(self):
        receipt = operations_briefing.compile_receipt([
            source("slo"), source("backup", healthy=False, severity="critical", state="failed"),
            source("external", healthy=False, severity="informational", state="credential-pending"),
            source("canary", healthy=False, severity="warning", state="due"),
        ], actor="test", now=1000)
        self.assertEqual(receipt["state"], "critical")
        self.assertEqual(receipt["score"], 73)
        self.assertEqual(receipt["summary"], {"sources": 4, "healthy": 1, "attention": 1, "critical": 1, "informational": 1, "actions": 3, "changes": 0})
        self.assertEqual([row["priority"] for row in receipt["actions"]], ["critical", "warning", "informational"])
        self.assertNotIn("execute", operations_briefing.canonical(receipt).lower())

    def test_signed_store_is_current_private_and_detects_changes(self):
        first = self.store.record([source("slo"), source("backup")], actor="test", now=1000)
        fingerprint = first["document"]["receipt"]["sourceFingerprint"]
        status = self.store.status(fingerprint, now=1001)
        self.assertTrue(status["ok"])
        self.assertTrue(status["currentReady"])
        self.assertEqual(pathlib.Path(first["evidencePath"]).stat().st_mode & 0o077, 0)
        second = self.store.record([source("slo", healthy=False, state="degraded"), source("backup")], actor="test", now=1002)
        second_receipt = second["document"]["receipt"]
        changes = second_receipt["changes"]
        self.assertEqual(changes, [{"source": "slo", "fromState": "ready", "toState": "degraded", "direction": "regression"}])
        self.assertEqual(second_receipt["previousReceiptId"], first["document"]["receipt"]["id"])
        self.assertEqual(second_receipt["previousReceiptSha256"], first["document"]["receipt"]["receiptSha256"])
        chained = self.store.status(second_receipt["sourceFingerprint"], now=1003)
        self.assertTrue(chained["latest"]["verification"]["historyLinkValid"])
        self.assertTrue(chained["latest"]["verification"]["changesValid"])
        self.assertFalse(self.store.status(fingerprint, now=1003)["currentReady"])

    def test_tampering_semantic_mismatch_and_expiry_fail_closed(self):
        result = self.store.record([source("slo"), source("backup")], actor="test", now=1000)
        document = result["document"]
        tampered = copy.deepcopy(document)
        tampered["receipt"]["score"] = 0
        self.assertIn("signature", operations_briefing.verify_signed_document(tampered, self.secret, now=1001)["error"])
        semantic = copy.deepcopy(document["receipt"])
        semantic["score"] = 0
        semantic["receiptSha256"] = operations_briefing.hashlib.sha256(operations_briefing.canonical({k:v for k,v in semantic.items() if k != "receiptSha256"}).encode()).hexdigest()
        checked = operations_briefing.verify_signed_document(operations_briefing.signed_document(semantic, self.secret), self.secret, now=1001)
        self.assertIn("score", checked["error"])
        stale = operations_briefing.verify_signed_document(document, self.secret, max_age_seconds=100, now=1101)
        self.assertTrue(stale["ok"])
        self.assertFalse(stale["currentReady"])

    def test_source_normalization_rejects_duplicates_unknown_fields_and_control_text(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            operations_briefing.normalize_sources([source("same"), source("same")])
        bad = source("bad"); bad["extra"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            operations_briefing.normalize_sources([bad])
        bad = source("bad"); bad["detail"] = "bad\nline"
        with self.assertRaisesRegex(ValueError, "detail"):
            operations_briefing.normalize_sources([bad])

    def test_metrics_are_label_free(self):
        result = self.store.record([source("slo"), source("backup")], actor="test", now=1000)
        status = self.store.status(result["document"]["receipt"]["sourceFingerprint"], now=1001)
        metrics = operations_briefing.prometheus(status, enabled=True, worker_running=True)
        self.assertIn("dash_operations_briefing_score 100", metrics)
        self.assertIn("dash_operations_briefing_current 1", metrics)
        self.assertNotIn("{", metrics)

    def test_repository_integration_is_complete(self):
        admin = (ROOT / "admin/admin_panel.py").read_text(encoding="utf-8")
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        activator = (ROOT / "scripts/enable-feature-parity.sh").read_text(encoding="utf-8")
        rules = (ROOT / "config/metrics/rules/dash.yml").read_text(encoding="utf-8")
        feature = json.loads((ROOT / "config/feature-readiness.json").read_text(encoding="utf-8"))
        deploy = (ROOT / "scripts/deployment-assurance.py").read_text(encoding="utf-8")
        push = (ROOT / "scripts/push-assured-control-plane.sh").read_text(encoding="utf-8")
        verify = (ROOT / "scripts/verify-backup.sh").read_text(encoding="utf-8")
        self.assertIn('"/api/ops/operations-briefing"', admin)
        self.assertIn("operations_briefing_public_status(refresh_sources=False", admin)
        self.assertIn("ensure_operations_briefing_thread()", admin)
        self.assertIn("operationsBriefingPanel", admin)
        self.assertIn("operations_briefing.verify_signed_document", admin)
        self.assertIn("DUNE_OPERATIONS_BRIEFING_ENABLED", compose)
        self.assertIn("DUNE_OPERATIONS_BRIEFING_ENABLED=true", env)
        self.assertIn("DUNE_OPERATIONS_BRIEFING_ENABLED", activator)
        self.assertIn("DashOperationsBriefingNotCurrent", rules)
        self.assertIn("operations-briefing", {row["id"] for row in feature["features"]})
        self.assertIn('"admin/operations_briefing.py"', deploy)
        self.assertIn("admin/operations_briefing.py", push)
        self.assertIn("operations_briefing.verify_signed_document", verify)
        self.assertTrue((ROOT / "docs/operations-briefing.md").is_file())


if __name__ == "__main__":
    unittest.main()
