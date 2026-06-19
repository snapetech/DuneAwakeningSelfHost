#!/usr/bin/env python3
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "brt-dd-runtime-patch-site.sh"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class BrtDdRuntimePatchSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = SCRIPT.read_text(encoding="utf-8")

    def test_script_is_syntax_valid(self):
        result = run("bash", "-n", str(SCRIPT))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_backup_gate_sites_are_listed_and_have_specs(self):
        for site in (
            "brt-component-use-force-backup-mode",
            "brt-backup-request-actor-validation-allow",
            "brt-backup-base-owner-allow",
            "brt-backup-mode-byte-allow-any",
            "brt-backup-inventory-match-allow",
        ):
            with self.subTest(site=site):
                self.assertIn(site, self.body)
                self.assertRegex(self.body, rf"{re.escape(site)}\)\n\s+#.*?\n(?:\s+#.*?\n)*\s+offset=0x[0-9a-f]+", re.S)

    def test_patch_byte_widths_match(self):
        cases = re.findall(
            r"\)\n(?:\s+#.*\n)*\s+offset=0x[0-9a-f]+\n\s+original=\"([0-9a-f ]+)\"\n\s+patched=\"([0-9a-f ]+)\"",
            self.body,
        )
        self.assertGreater(len(cases), 8)
        for original, patched in cases:
            with self.subTest(original=original, patched=patched):
                self.assertEqual(len(original.split()), len(patched.split()))

    def test_help_lists_new_backup_gate_sites(self):
        result = run("bash", str(SCRIPT), "--help")
        self.assertEqual(result.returncode, 0)
        help_text = result.stdout + result.stderr
        self.assertIn("brt-backup-mode-byte-allow-any", help_text)
        self.assertIn("brt-backup-inventory-match-allow", help_text)


if __name__ == "__main__":
    unittest.main()
