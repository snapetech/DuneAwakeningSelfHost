#!/usr/bin/env python3

import importlib.util
import contextlib
import os
import pathlib
import sqlite3
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("change_approvals", ROOT / "admin" / "change_approvals.py")
approvals = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(approvals)


REQUESTER = {"id": "requester", "displayName": "Request Operator"}
APPROVER = {"id": "approver", "displayName": "Approval Operator"}


class ChangeApprovalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = [1784246400.0]
        self.store = approvals.Store(pathlib.Path(self.tmp.name) / "approvals.sqlite3", ttl_seconds=300, clock=lambda: self.clock[0])
        self.store.initialize()
        self.path = "/api/admin/player-maintenance"
        self.body = {"action": "add-intel", "account_id": 7, "amount": 10, "dry_run": False, "confirm": "WRITE PLAYER PROGRESSION"}

    def tearDown(self):
        self.tmp.cleanup()

    def request(self):
        return self.store.create(REQUESTER, self.path, self.body, "players.write", "high", "Grant ten Intel")

    def test_policy_levels_and_preview_exclusion(self):
        self.assertIsNone(approvals.policy_for(self.path, {**self.body, "dry_run": True}))
        self.assertEqual("high", approvals.policy_for(self.path, self.body)["risk"])
        self.assertTrue(approvals.policy_enabled("high", "critical"))
        self.assertTrue(approvals.policy_enabled("high", "high"))
        self.assertFalse(approvals.policy_enabled("critical", "high"))
        self.assertTrue(any(row["path"] == "/api/ops/backups/restore" and row["enforced"] for row in approvals.public_policies("critical")))

    def test_two_people_exact_body_and_one_time_consumption(self):
        request = self.request()
        approved = self.store.approve(request["id"], APPROVER)
        self.assertEqual("approved", approved["state"])
        consumed = self.store.consume(request["id"], REQUESTER, self.path, self.body, "players.write", "high")
        self.assertEqual("consumed", consumed["state"])
        self.assertEqual("requester", consumed["consumedBy"])
        with self.assertRaisesRegex(PermissionError, "not approved"):
            self.store.consume(request["id"], REQUESTER, self.path, self.body, "players.write", "high")
        self.assertTrue(self.store.verify()["ok"])

    def test_approval_id_is_not_part_of_bound_body(self):
        request = self.request()
        self.store.approve(request["id"], APPROVER)
        body = {**self.body, "approvalId": request["id"]}
        consumed = self.store.consume(request["id"], REQUESTER, self.path, body, "players.write", "high")
        self.assertEqual("consumed", consumed["state"])

    def test_requester_cannot_self_approve_and_executor_is_bound(self):
        request = self.request()
        with self.assertRaisesRegex(PermissionError, "own change"):
            self.store.approve(request["id"], REQUESTER)
        self.store.approve(request["id"], APPROVER)
        with self.assertRaisesRegex(PermissionError, "original requester"):
            self.store.consume(request["id"], APPROVER, self.path, self.body, "players.write", "high")

    def test_execution_refuses_body_path_capability_and_risk_drift(self):
        for field, arguments in (
            ("request body", (self.path, {**self.body, "amount": 11}, "players.write", "high")),
            ("target path", ("/api/admin/vehicle", self.body, "players.write", "high")),
            ("capability", (self.path, self.body, "world.write", "high")),
            ("risk", (self.path, self.body, "players.write", "critical")),
        ):
            request = self.request()
            self.store.approve(request["id"], APPROVER)
            with self.assertRaisesRegex(PermissionError, field):
                self.store.consume(request["id"], REQUESTER, *arguments)

    def test_expiry_is_persisted_and_cannot_be_approved(self):
        request = self.request()
        self.clock[0] += 301
        expired = self.store.get(request["id"])
        self.assertEqual("expired", expired["state"])
        with self.assertRaisesRegex(RuntimeError, "expired"):
            self.store.approve(request["id"], APPROVER)

    def test_reject_and_requester_cancel_are_distinct(self):
        rejected = self.request()
        self.assertEqual("rejected", self.store.reject(rejected["id"], APPROVER, "No maintenance window")["state"])
        cancelled = self.request()
        with self.assertRaisesRegex(PermissionError, "cancel"):
            self.store.reject(cancelled["id"], REQUESTER)
        self.assertEqual("cancelled", self.store.cancel(cancelled["id"], REQUESTER)["state"])

    def test_database_key_and_parent_are_private(self):
        self.assertEqual(0o600, self.store.path.stat().st_mode & 0o777)
        self.assertEqual(0o600, self.store.key_path.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.store.path.parent.stat().st_mode & 0o777)
        self.assertEqual(32, len(self.store.key_path.read_bytes()))

    def test_review_body_redacts_secrets_but_exact_hmac_still_binds_them(self):
        body = {"confirm": "ROTATE DATABASE PASSWORD", "password": "correct horse battery staple", "nested": {"apiToken": "secret-token", "safe": "visible"}}
        request = self.store.create(REQUESTER, "/api/ops/database/password", body, "infrastructure.write", "critical", "Rotate database password")
        self.assertEqual("[redacted]", request["reviewBody"]["password"])
        self.assertEqual("[redacted]", request["reviewBody"]["nested"]["apiToken"])
        self.assertEqual("visible", request["reviewBody"]["nested"]["safe"])
        self.store.approve(request["id"], APPROVER)
        with self.assertRaisesRegex(PermissionError, "request body"):
            self.store.consume(request["id"], REQUESTER, "/api/ops/database/password", {**body, "password": "wrong"}, "infrastructure.write", "critical")

    def test_request_and_event_tampering_fail_verification(self):
        request = self.request()
        with contextlib.closing(sqlite3.connect(self.store.path)) as connection:
            connection.execute("update approval_requests set target_path='/api/admin/currency' where id=?", (request["id"],))
            connection.commit()
        self.assertFalse(self.store.verify()["ok"])
        with self.assertRaisesRegex(RuntimeError, "record HMAC"):
            self.store.get(request["id"])

        other = approvals.Store(pathlib.Path(self.tmp.name) / "other.sqlite3", clock=lambda: self.clock[0])
        other.initialize()
        created = other.create(REQUESTER, self.path, self.body, "players.write", "high", "Grant Intel")
        other.approve(created["id"], APPROVER)
        with contextlib.closing(sqlite3.connect(other.path)) as connection:
            connection.execute("update approval_events set action='tampered' where sequence=1")
            connection.commit()
        self.assertFalse(other.verify()["ok"])

        state_store = approvals.Store(pathlib.Path(self.tmp.name) / "state.sqlite3", clock=lambda: self.clock[0])
        state_store.initialize()
        state_request = state_store.create(REQUESTER, self.path, self.body, "players.write", "high", "Grant Intel")
        with contextlib.closing(sqlite3.connect(state_store.path)) as connection:
            connection.execute("update approval_requests set state='approved' where id=?", (state_request["id"],))
            connection.commit()
        self.assertFalse(state_store.verify()["ok"])
        with self.assertRaisesRegex(RuntimeError, "state HMAC"):
            state_store.get(state_request["id"])

    def test_status_and_metrics_are_label_free(self):
        self.request()
        status = self.store.status()
        self.assertEqual(1, status["counts"]["pending"])
        metrics = self.store.prometheus(enabled=True)
        self.assertIn("dash_change_approval_pending 1", metrics)
        self.assertIn("dash_change_approval_ledger_valid 1", metrics)
        self.assertNotIn("requester", metrics)


if __name__ == "__main__":
    unittest.main()
