#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "character-slot-tool.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("character_slot_tool_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CharacterSlotToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_execute_requires_confirmation_before_request(self):
        with mock.patch.object(self.tool, "request_json") as request_json:
            with self.assertRaises(SystemExit):
                self.tool.main_with_argv([
                    "--account-id", "10",
                    "--action", "switch-character",
                    "--target-account-id", "11",
                    "--execute",
                ])
        request_json.assert_not_called()

    def test_execute_blocks_new_character_before_request(self):
        with mock.patch.object(self.tool, "request_json") as request_json:
            with self.assertRaises(SystemExit):
                self.tool.main_with_argv([
                    "--account-id", "10",
                    "--action", "new-character",
                    "--execute",
                    "--confirm", "SWAP CHARACTER",
                ])
        request_json.assert_not_called()

    def test_switch_plan_requires_target_before_request(self):
        with mock.patch.object(self.tool, "request_json") as request_json:
            with self.assertRaises(SystemExit):
                self.tool.main_with_argv([
                    "--account-id", "10",
                    "--action", "switch-character",
                ])
        request_json.assert_not_called()

    def test_account_id_not_required_for_scan(self):
        responses = [
            [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}],
            {"ok": True, "accountId": 10, "offline": True, "candidates": [], "contract": {"safeNativeSwapPath": True}},
        ]
        with mock.patch.object(self.tool, "request_json", side_effect=responses) as request_json:
            with redirect_stdout(StringIO()):
                self.tool.main_with_argv([
                    "--action", "scan",
                    "--base-url", "http://admin.test",
                ])
        self.assertEqual(request_json.call_count, 2)

    def test_non_scan_requires_account_id(self):
        with mock.patch.object(self.tool, "request_json") as request_json:
            with self.assertRaises(SystemExit):
                self.tool.main_with_argv(["--action", "inspect"])
        request_json.assert_not_called()

    def test_reads_env_file_for_base_url_and_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = pathlib.Path(tmp) / ".env"
            env_path.write_text("DUNE_ADMIN_HOST_PORT=19090\nDUNE_ADMIN_TOKEN=secret\n", encoding="utf-8")
            with mock.patch.object(self.tool, "request_json", return_value={"ok": True}) as request_json:
                with redirect_stdout(StringIO()):
                    self.tool.main_with_argv([
                        "--env-file", str(env_path),
                        "--account-id", "10",
                        "--action", "inspect",
                    ])
        args, kwargs = request_json.call_args
        self.assertEqual(args[0], "GET")
        self.assertTrue(args[1].startswith("http://127.0.0.1:19090/"))
        self.assertEqual(kwargs["token"], "secret")

    def test_summary_for_plan_response(self):
        result = self.tool.summarize({
            "ok": True,
            "dryRun": True,
            "accountId": 10,
            "action": "switch-character",
            "targetAccountId": 11,
            "executable": True,
            "plan": {
                "blockers": [],
                "nativeCall": {"function": "dune.takeover_account"},
                "transactionSafety": {"commitRequiresPostSwapVerification": True},
            },
        })
        self.assertTrue(result["executable"])
        self.assertEqual(result["nativeCall"]["function"], "dune.takeover_account")
        self.assertTrue(result["transactionSafety"]["commitRequiresPostSwapVerification"])

    def test_summary_for_inspect_response(self):
        result = self.tool.summarize({
            "ok": True,
            "accountId": 10,
            "offline": True,
            "candidates": [{"account_id": 11}],
            "contract": {
                "safeNativeSwapPath": True,
                "safeNativeSwapAction": "takeover_account",
                "confidence": "moderate",
            },
        })
        self.assertEqual(result["candidateCount"], 1)
        self.assertTrue(result["safeNativeSwapPath"])

    def test_scan_accounts_returns_only_accounts_with_candidates(self):
        responses = [
            [
                {"account_id": 10, "character_name": "NoAlt", "online_status": "Offline"},
                {"account_id": 11, "character_name": "HasAlt", "online_status": "Offline"},
            ],
            {"ok": True, "accountId": 10, "offline": True, "candidates": [], "contract": {"safeNativeSwapPath": True}},
            {"ok": True, "accountId": 11, "offline": True, "candidates": [{"account_id": 12}], "contract": {"safeNativeSwapPath": True}},
        ]
        with mock.patch.object(self.tool, "request_json", side_effect=responses):
            result = self.tool.scan_accounts("http://admin.test", "token")
        self.assertEqual(result["scanned"], 2)
        self.assertEqual(result["withCandidates"], 1)
        self.assertEqual(result["accounts"][0]["accountId"], 11)
        self.assertEqual(result["accounts"][0]["characterName"], "HasAlt")

    def test_summary_for_scan_response(self):
        result = self.tool.summarize({
            "ok": True,
            "query": "",
            "scanned": 20,
            "withCandidates": 1,
            "accounts": [{"accountId": 11, "candidateCount": 2}],
        })
        self.assertEqual(result["scanned"], 20)
        self.assertEqual(result["withCandidates"], 1)
        self.assertEqual(result["accounts"][0]["accountId"], 11)


if __name__ == "__main__":
    unittest.main()
