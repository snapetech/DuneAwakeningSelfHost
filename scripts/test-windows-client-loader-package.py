#!/usr/bin/env python3
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "scripts/package-windows-client-loader.sh"
LOADER = ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c"


class WindowsClientLoaderPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = PACKAGE.read_text(encoding="utf-8")

    def test_package_stages_deployment_manager_tests_and_current_docs(self):
        for relative in (
            "scripts/client-deployment.py",
            "scripts/test-client-deployment.py",
            "docs/client-deployment.md",
            "docs/windows-client-loader-canary-2026-07-15.md",
        ):
            self.assertIn(f'cp "$repo_root/{relative}"', self.package)
        self.assertIn('chmod 0755 "$stage/scripts/client-deployment.py"', self.package)
        self.assertIn('chmod 0755 "$stage/tests/test-client-deployment.py"', self.package)

    def test_generated_readme_leads_with_transactional_install(self):
        self.assertIn("The recommended installation path is the packaged transactional manager", self.package)
        self.assertIn('scripts/client-deployment.py --state-root "\\$state" plan', self.package)
        self.assertIn('--reviewed-plan "\\$receipt"', self.package)
        self.assertIn('scripts/client-deployment.py --state-root "\\$state" audit', self.package)
        self.assertIn("### Experimental launch wrapper", self.package)
        self.assertIn("examples/launch-proton-client-probe.sh --stage-to-game-dir", self.package)

    def test_package_emits_test_and_verification_receipts(self):
        self.assertIn(
            "python3 -m unittest tests/test-client-deployment.py > client-deployment-test.txt 2>&1",
            self.package,
        )
        self.assertIn("loader-artifact-verification.txt", self.package)
        self.assertIn("loader-artifact-verification.json", self.package)
        self.assertIn('--package-archive "$archive"', self.package)
        self.assertIn('--package-archive-sha256 "${archive}.sha256"', self.package)
        self.assertIn('> "${archive}.verification.txt"', self.package)
        self.assertIn('> "${archive}.verification.json"', self.package)

    def test_archive_checksum_sidecar_is_download_portable(self):
        self.assertIn('"$(basename "$archive")" > "${archive}.sha256"', self.package)
        self.assertNotIn('sha256sum "$archive" > "${archive}.sha256"', self.package)

    def test_builtin_dispatch_script_literals_stay_below_c99_limit(self):
        source = LOADER.read_text(encoding="utf-8")
        start = source.index("static void run_lua_dispatch_self_test")
        end = source.index("LuaState *state = api.new_state();", start)
        literals = re.findall(r'"(?:\\.|[^"\\])*"', source[start:end])
        self.assertGreaterEqual(len(literals), 3)
        self.assertLessEqual(max(map(len, literals)), 4000)


if __name__ == "__main__":
    unittest.main()
