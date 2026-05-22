#!/usr/bin/env python3
import importlib.util
import io
import pathlib
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "admin-grant-item.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("admin_grant_item", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AdminGrantItemTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_catalog_resolves_complex_and_advanced_machinery(self):
        rows = self.tool.load_catalog()
        complex_row = self.tool.resolve_template("Complex Machinery", rows)
        advanced_row = self.tool.resolve_template("Advanced Machinery", rows)
        self.assertEqual(complex_row["template_id"], "T2MachineComponent")
        self.assertEqual(advanced_row["template_id"], "T6Machinery")

    def test_execute_requires_confirmation_before_write(self):
        responses = [
            [["2", "Lukano", "Online", "17", "19"]],
            [["14", "0", "35"]],
            [["1"]],
        ]
        with mock.patch.object(self.tool, "run_psql", side_effect=responses) as run_psql:
            with self.assertRaises(SystemExit):
                self.tool.main_with_argv([
                    "Complex Machinery", "2", "--character", "Lukano", "--execute"
                ])
        self.assertEqual(run_psql.call_count, 3)

    def test_dry_run_returns_resolved_plan(self):
        responses = [
            [["2", "Lukano", "Online", "17", "19"]],
            [["14", "0", "35"]],
            [["1"]],
        ]
        with mock.patch.object(self.tool, "run_psql", side_effect=responses):
            with redirect_stdout(io.StringIO()):
                plan = self.tool.main_with_argv(["Complex Machinery", "2", "--character", "Lukano"])
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["item"]["templateId"], "T2MachineComponent")
        self.assertEqual(plan["positionIndex"], 1)


if __name__ == "__main__":
    unittest.main()
