#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import access_control  # noqa: E402


class AccessControlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "admin-access.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_user(self, token="correct-horse", role="operator", enabled=True, capabilities=None):
        self.path.write_text(json.dumps({
            "version": 1,
            "users": [{
                "id": "operator-one",
                "displayName": "Operator One",
                "enabled": enabled,
                "role": role,
                "capabilities": capabilities or [],
                "tokenSha256": access_control.token_hash(token),
            }],
        }), encoding="utf-8")

    def test_hashed_authentication_and_roles(self):
        self.write_user()
        principal = access_control.authenticate(self.path, "correct-horse")
        self.assertEqual(principal["id"], "operator-one")
        self.assertNotIn("tokenSha256", principal)
        self.assertTrue(access_control.has_capability(principal, "read"))
        self.assertTrue(access_control.has_capability(principal, "operations.write"))
        self.assertFalse(access_control.has_capability(principal, "players.write"))
        self.assertIsNone(access_control.authenticate(self.path, "wrong"))
        self.assertEqual(access_control.principal_by_id(self.path, "operator-one")["role"], "operator")
        self.assertIsNone(access_control.principal_by_id(self.path, "missing"))

    def test_disabled_identity_never_authenticates(self):
        self.write_user(enabled=False)
        self.assertIsNone(access_control.authenticate(self.path, "correct-horse"))

    def test_route_capability_mapping(self):
        cases = {
            ("GET", "/api/admin/players"): "read",
            ("POST", "/api/admin/gm/preview"): "read",
            ("POST", "/api/ops/restart"): "operations.write",
            ("POST", "/api/ops/database/password"): "infrastructure.write",
            ("POST", "/api/ops/restore-drill"): "infrastructure.write",
            ("POST", "/api/ops/slo"): "infrastructure.write",
            ("POST", "/api/ops/capacity"): "infrastructure.write",
            ("POST", "/api/ops/desired-state"): "infrastructure.write",
            ("POST", "/api/ops/deployment-assurance"): "infrastructure.write",
            ("POST", "/api/settings/env"): "configuration.write",
            ("POST", "/api/admin/currency"): "economy.write",
            ("POST", "/api/admin/guild"): "world.write",
            ("POST", "/api/admin/base-retirement"): "world.write",
            ("POST", "/api/admin/item"): "players.write",
            ("POST", "/api/community/rewards"): "community.write",
            ("POST", "/api/auth/logout"): "read",
            ("POST", "/api/security/approvals"): "read",
        }
        for route, expected in cases.items():
            self.assertEqual(access_control.required_capability(*route), expected, route)

    def test_cli_generates_once_only_token_and_lifecycle(self):
        command = [sys.executable, str(ROOT / "scripts/admin-access.py"), "--file", str(self.path)]
        created = subprocess.run(command + ["add", "night-ops", "--role", "operator"], text=True, stdout=subprocess.PIPE, check=True)
        token = created.stdout.strip().splitlines()[-1]
        self.assertGreaterEqual(len(token), 32)
        document_text = self.path.read_text(encoding="utf-8")
        self.assertNotIn(token, document_text)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(access_control.authenticate(self.path, token)["id"], "night-ops")
        subprocess.run(command + ["disable", "night-ops"], check=True, stdout=subprocess.PIPE)
        self.assertIsNone(access_control.authenticate(self.path, token))
        subprocess.run(command + ["enable", "night-ops"], check=True, stdout=subprocess.PIPE)
        rotated = subprocess.run(command + ["rotate", "night-ops"], text=True, stdout=subprocess.PIPE, check=True)
        new_token = rotated.stdout.strip().splitlines()[-1]
        self.assertIsNone(access_control.authenticate(self.path, token))
        self.assertEqual(access_control.authenticate(self.path, new_token)["id"], "night-ops")

    def test_cli_init_creates_empty_locked_file(self):
        command = [sys.executable, str(ROOT / "scripts/admin-access.py"), "--file", str(self.path), "init"]
        subprocess.run(command, text=True, stdout=subprocess.PIPE, check=True)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"users": [], "version": 1})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_documents_fail_closed(self):
        for document in (
            {"version": 2, "users": []},
            {"version": 1, "users": [{"id": "bad", "role": "root", "tokenSha256": "0" * 64}]},
            {"version": 1, "users": [{"id": "ok-user", "role": "observer", "tokenSha256": "plaintext"}]},
        ):
            with self.assertRaises(ValueError):
                access_control.validate_document(document)


if __name__ == "__main__":
    unittest.main()
