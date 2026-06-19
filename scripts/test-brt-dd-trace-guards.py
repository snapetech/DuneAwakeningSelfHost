#!/usr/bin/env python3
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "lib" / "brt-dd-trace-guards.sh"


def run_bash(script: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


class BrtDdTraceGuardTests(unittest.TestCase):
    def test_emit_points_filters_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            points = Path(tmp) / "points.tsv"
            points.write_text(
                textwrap.dedent(
                    """\
                    # build_id=fake
                    minimal min_a 0x10
                    decision dec_a 0x20
                    hotbar hotbar_a 0x25
                    place place_a 0x28
                    place min_a 0x10
                    backup backup_a 0x2a
                    backup backup_args 0x2b rdi=%di:x64 rsi=%si:x64
                    focused focus_a 0x30
                    all all_a 0x40
                    """
                ),
                encoding="utf-8",
            )

            decision = run_bash(
                f"source {HELPER}; brt_dd_trace_emit_points {points} decision"
            )
            hotbar = run_bash(
                f"source {HELPER}; brt_dd_trace_emit_points {points} hotbar"
            )
            brt = run_bash(
                f"source {HELPER}; brt_dd_trace_emit_points {points} brt"
            )
            backup = run_bash(
                f"source {HELPER}; brt_dd_trace_emit_points {points} backup"
            )

        self.assertEqual(
            decision.stdout.strip().splitlines(),
            ["min_a 0x10", "dec_a 0x20", "all_a 0x40"],
        )
        self.assertEqual(
            hotbar.stdout.strip().splitlines(),
            ["hotbar_a 0x25", "all_a 0x40"],
        )
        self.assertEqual(
            brt.stdout.strip().splitlines(),
            [
                "min_a 0x10",
                "dec_a 0x20",
                "hotbar_a 0x25",
                "place_a 0x28",
                "all_a 0x40",
            ],
        )
        self.assertEqual(
            backup.stdout.strip().splitlines(),
            [
                "min_a 0x10",
                "dec_a 0x20",
                "hotbar_a 0x25",
                "backup_a 0x2a",
                "backup_args 0x2b rdi=%di:x64 rsi=%si:x64",
                "all_a 0x40",
            ],
        )

    def test_missing_build_id_header_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            points = Path(tmp) / "points.tsv"
            points.write_text("minimal min_a 0x10\n", encoding="utf-8")

            result = run_bash(
                f"source {HELPER}; brt_dd_trace_validate_points_file $$ {points}",
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no build_id header", result.stderr)

    def test_build_mismatch_requires_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            points = Path(tmp) / "points.tsv"
            points.write_text(
                "# build_id=0000000000000000000000000000000000000000\nminimal min_a 0x10\n",
                encoding="utf-8",
            )

            denied = run_bash(
                f"source {HELPER}; brt_dd_trace_validate_points_file $$ {points}",
                check=False,
            )
            allowed = run_bash(
                f"source {HELPER}; DUNE_BRT_DD_TRACE_ALLOW_BUILD_MISMATCH=1 brt_dd_trace_validate_points_file $$ {points}",
                check=False,
            )

        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("does not match", denied.stderr)
        self.assertEqual(allowed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
