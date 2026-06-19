#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "ue4ss-portability-contract.py",
    ROOT / "analysis" / "ue4ss-portability-contract.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


class Ue4ssPortabilityContractTests(unittest.TestCase):
    PACKAGE_SCRIPTS = (
        ROOT / "scripts/package-linux-client-loader.sh",
        ROOT / "scripts/package-linux-server-loader.sh",
        ROOT / "scripts/package-windows-client-loader.sh",
    )

    def run_contract(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def test_json_contract_passes_for_all_targets(self):
        result = self.run_contract("--check")
        report = json.loads(result.stdout)
        self.assertEqual(report["schemaVersion"], "dune-ue4ss-portability-contract/v1")
        self.assertTrue(report["passed"])
        self.assertEqual(
            set(report["targets"]),
            {"linux-client", "linux-server", "windows-client"},
        )
        self.assertEqual(report["targets"]["linux-client"]["injection"]["model"], "ld-preload-elf")
        self.assertEqual(report["targets"]["linux-server"]["injection"]["model"], "ld-preload-elf")
        self.assertEqual(
            report["targets"]["windows-client"]["injection"]["model"],
            "proton-version-dll-proxy",
        )
        for target, item in report["targets"].items():
            with self.subTest(target=target):
                self.assertTrue(item["passed"])
                self.assertTrue(item["injection"]["passed"])
                self.assertFalse(item["injection"]["missing"])
                for surface_name, surface in item["surfaces"].items():
                    with self.subTest(target=target, surface=surface_name):
                        self.assertTrue(surface["passed"])
                        self.assertFalse(surface["missing"])
                self.assertIn("post-canary-strict-contract", item["packageSurfaces"])
                strict_surface = item["packageSurfaces"]["post-canary-strict-contract"]
                self.assertTrue(strict_surface["passed"])
                self.assertFalse(strict_surface["missing"])
                self.assertIn("source-group-matched-root-recovery", item["packageSurfaces"])
                self.assertTrue(item["packageSurfaces"]["source-group-matched-root-recovery"]["passed"])
                if target in {"linux-client", "linux-server"}:
                    self.assertIn("elf-qword-root-shape-hardening", item["packageSurfaces"])
                    self.assertTrue(item["packageSurfaces"]["elf-qword-root-shape-hardening"]["passed"])
                if target == "linux-server":
                    self.assertIn("zero-player-server-canary-preflight", item["packageSurfaces"])
                    self.assertTrue(item["packageSurfaces"]["zero-player-server-canary-preflight"]["passed"])
                if target == "windows-client":
                    self.assertIn("pe-qword-root-shape-hardening", item["packageSurfaces"])
                    self.assertTrue(item["packageSurfaces"]["pe-qword-root-shape-hardening"]["passed"])
                if target in {"linux-client", "windows-client"}:
                    self.assertIn("non-mutating-client-preflight", item["launchSurfaces"])
                    self.assertTrue(item["launchSurfaces"]["non-mutating-client-preflight"]["passed"])
                package_text = (ROOT / item["package"]).read_text(encoding="utf-8")
                for marker in (
                    "targetObjectDiscovery",
                    "targetHooks",
                    "targetPackageLoadingSurface",
                    "liveTargetImageCanaryContract",
                    "ue4ssLuaApiComplete",
                    "targetImageAnchors",
                    "runtimePackageLoading",
                    "runtimeObjectRegistry",
                    "runtimeReflection",
                    "runtimeProcessEventDispatch",
                    "runtimeCallFunctionDispatch",
                ):
                    with self.subTest(target=target, package_marker=marker):
                        self.assertIn(marker, package_text)

    def test_markdown_contract_is_operator_readable(self):
        result = self.run_contract("--format", "markdown", "--check")
        text = result.stdout
        self.assertIn("# UE4SS Portability Contract", text)
        self.assertIn("- Passed: `true`", text)
        self.assertIn("`linux-client` injection `ld-preload-elf`", text)
        self.assertIn("`linux-server` injection `ld-preload-elf`", text)
        self.assertIn("`windows-client` injection `proton-version-dll-proxy`", text)
        self.assertIn("`process-event-hooks`", text)
        self.assertIn("`call-function-hooks`", text)
        self.assertIn("`lua-mod-lifecycle`", text)
        self.assertIn("`compat-globals`", text)
        self.assertIn("`custom-property`", text)
        self.assertIn("package `post-canary-strict-contract`", text)
        self.assertIn("launcher `non-mutating-client-preflight`", text)

    def test_package_scripts_are_shell_parseable(self):
        result = subprocess.run(
            ["bash", "-n", *(str(path) for path in self.PACKAGE_SCRIPTS)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_package_runbooks_do_not_duplicate_canary_prep_section(self):
        needle = "combines the validated"
        for path in self.PACKAGE_SCRIPTS:
            with self.subTest(package=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count(needle), 1)


if __name__ == "__main__":
    unittest.main()
