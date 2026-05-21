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


if __name__ == "__main__":
    unittest.main()
