#!/usr/bin/env python3
import base64
import concurrent.futures
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "admin"))

import change_approvals
import change_contracts
import access_control


class ChangeContractTests(unittest.TestCase):
    def setUp(self):
        self.secret = bytes(range(32))
        self.principal = {"id": "operator.one", "displayName": "Operator One"}
        self.body = {"action": "game-apply", "confirm": "APPLY GAME UPDATE"}
        self.path = "/api/ops/updates"
        self.capability = "infrastructure.write"
        self.now = 1_800_000_000

    def issue(self, **overrides):
        return change_contracts.issue(
            overrides.get("path", self.path), overrides.get("body", self.body),
            overrides.get("principal", self.principal), overrides.get("capability", self.capability),
            overrides.get("secret", self.secret), now=overrides.get("now", self.now),
            ttl_seconds=overrides.get("ttl_seconds", 120),
        )

    def verify(self, token, **overrides):
        return change_contracts.verify(
            token, overrides.get("path", self.path), overrides.get("body", self.body),
            overrides.get("principal", self.principal), overrides.get("capability", self.capability),
            overrides.get("secret", self.secret), now=overrides.get("now", self.now + 1),
        )

    def test_registry_covers_every_governed_policy(self):
        self.assertEqual(set(change_approvals.POLICIES), set(change_contracts.IMPACTS))
        self.assertEqual(len(change_contracts.public_policies()), len(change_approvals.POLICIES))
        for path in change_contracts.IMPACTS:
            self.assertNotEqual("read", access_control.required_capability("POST", path), path)

    def test_non_mutating_predicate_returns_no_token(self):
        issued = self.issue(body={"action": "status"})
        self.assertFalse(issued["contract"]["governed"])
        self.assertIsNone(issued["token"])
        previews = [
            ("/api/ops/backups/restore", {"dryRun": True}),
            ("/api/admin/character-slots/execute", {"dry_run": True}),
            ("/api/admin/item", {"dry_run": True}),
        ]
        for path, body in previews:
            with self.subTest(path=path):
                result = self.issue(path=path, body=body)
                self.assertFalse(result["contract"]["governed"])
                self.assertIsNone(result["token"])

    def test_contract_exposes_blast_radius_without_plaintext_body(self):
        issued = self.issue()
        contract = issued["contract"]
        self.assertTrue(contract["governed"])
        self.assertEqual("critical", contract["change"]["risk"])
        self.assertTrue(contract["impact"]["mapLifecycle"])
        self.assertEqual("required", contract["impact"]["backup"])
        self.assertNotIn("APPLY GAME UPDATE", json.dumps(contract))
        self.assertEqual(change_contracts.body_sha256(self.body), contract["target"]["bodySha256"])

    def test_valid_exact_contract_verifies(self):
        issued = self.issue()
        verified = self.verify(issued["token"])
        self.assertEqual(issued["contract"]["contractId"], verified["contractId"])

    def test_tampered_payload_and_signature_fail(self):
        issued = self.issue()
        prefix, payload, signature = issued["token"].split(".")
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        decoded["change"]["risk"] = "standard"
        changed = base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=").decode()
        with self.assertRaisesRegex(PermissionError, "signature"):
            self.verify(f"{prefix}.{changed}.{signature}")
        with self.assertRaisesRegex(PermissionError, "signature"):
            self.verify(issued["token"][:-1] + ("A" if issued["token"][-1] != "A" else "B"))

    def test_exact_body_route_principal_and_capability_are_bound(self):
        token = self.issue()["token"]
        cases = [
            {"body": {**self.body, "extra": 1}},
            {"path": "/api/ops/database/row"},
            {"principal": {"id": "operator.two"}},
            {"capability": "operations.write"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(PermissionError):
                self.verify(token, **case)

    def test_expired_future_and_overlong_lifetime_fail(self):
        token = self.issue(ttl_seconds=30)["token"]
        with self.assertRaisesRegex(PermissionError, "expired"):
            self.verify(token, now=self.now + 31)
        with self.assertRaisesRegex(PermissionError, "future"):
            self.verify(token, now=self.now - 11)

    def test_policy_revision_change_invalidates_contract(self):
        token = self.issue()["token"]
        original = change_contracts.IMPACTS[self.path]
        change_contracts.IMPACTS[self.path] = {**original, "restartImpact": "changed"}
        try:
            with self.assertRaisesRegex(PermissionError, "policy revision"):
                self.verify(token)
        finally:
            change_contracts.IMPACTS[self.path] = original

    def test_secret_and_token_bounds_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "32 bytes"):
            self.issue(secret=b"short")
        with self.assertRaisesRegex(PermissionError, "bounded"):
            self.verify("x" * (change_contracts.MAX_TOKEN_BYTES + 1))

    def test_ttl_is_bounded_and_owner_identity_is_supported(self):
        issued = self.issue(principal={"id": "owner-recovery"}, ttl_seconds=9999)
        contract = issued["contract"]
        self.assertEqual(change_contracts.MAX_TTL_SECONDS, contract["expiresAtEpoch"] - contract["issuedAtEpoch"])
        self.assertEqual("owner-recovery", contract["principalId"])

    def test_missing_identity_fails(self):
        with self.assertRaisesRegex(PermissionError, "authenticated operator"):
            self.issue(principal={})

    def test_replay_guard_is_atomic_one_attempt_and_prunes_expired_entries(self):
        clock = [self.now + 1]
        guard = change_contracts.ReplayGuard(clock=lambda: clock[0])
        first = self.issue(ttl_seconds=30)["contract"]
        guard.consume(first)
        with self.assertRaisesRegex(PermissionError, "already consumed"):
            guard.consume(first)
        second = self.issue(now=self.now + 31, ttl_seconds=30)["contract"]
        clock[0] = self.now + 32
        guard.consume(second)
        self.assertEqual(1, guard.size())

    def test_replay_guard_allows_exactly_one_concurrent_consumer(self):
        guard = change_contracts.ReplayGuard(clock=lambda: self.now + 1)
        contract = self.issue()["contract"]

        def attempt(_index):
            try:
                guard.consume(contract)
                return True
            except PermissionError:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(16)))
        self.assertEqual(1, sum(outcomes))


if __name__ == "__main__":
    unittest.main()
