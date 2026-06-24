#!/usr/bin/env python3
import json
import importlib.util
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


def load_contract_module():
    spec = importlib.util.spec_from_file_location("ue4ss_portability_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
                self.assertTrue(item["artifactLayout"]["passed"])
                self.assertFalse(item["artifactLayout"]["missing"])
                for surface_name, surface in item["surfaces"].items():
                    with self.subTest(target=target, surface=surface_name):
                        self.assertTrue(surface["passed"])
                        self.assertFalse(surface["missing"])
                if target == "linux-server":
                    for marker in (
                        "$stage/scripts/ue4ss-package-runtime-trace.sh",
                        "$stage/scripts/verify-ue4ss-package-review-bundle.py",
                        "$stage/tests/test-review-ue4ss-package-abi.py",
                    ):
                        with self.subTest(target=target, artifact_marker=marker):
                            self.assertIn(marker, item["artifactLayout"]["required"])
                if target == "linux-client":
                    self.assertIn(
                        "$stage/analysis/plan-ue4ss-package-runtime-trace.py",
                        item["artifactLayout"]["required"],
                    )
                self.assertIn("package-root-artifact-verification", item["packageSurfaces"])
                artifact_verification = item["packageSurfaces"]["package-root-artifact-verification"]
                self.assertTrue(artifact_verification["passed"])
                self.assertFalse(artifact_verification["missing"])
                self.assertIn("generic-unreal-target-selection", item["packageSurfaces"])
                generic_target_selection = item["packageSurfaces"]["generic-unreal-target-selection"]
                self.assertTrue(generic_target_selection["passed"])
                self.assertFalse(generic_target_selection["missing"])
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
                    self.assertIn("package-route-slot-proof", item["packageSurfaces"])
                    route_slot_surface = item["packageSurfaces"]["package-route-slot-proof"]
                    self.assertTrue(route_slot_surface["passed"])
                    for marker in (
                        "routeSlotTraceRequirement",
                        "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                        "required object/vtable capture",
                    ):
                        with self.subTest(target=target, route_slot_marker=marker):
                            self.assertIn(marker, route_slot_surface["required"])
                    self.assertIn("package-archive-artifact-verification", item["packageSurfaces"])
                    self.assertTrue(item["packageSurfaces"]["package-archive-artifact-verification"]["passed"])
                    package_root_surface = item["packageSurfaces"]["package-root-artifact-verification"]
                    for marker in (
                        "ue4ss-package-runtime-trace.sh",
                        "verify-ue4ss-package-review-bundle.py",
                        "plan-ue4ss-package-next-action.py",
                        "playerGuardPhase",
                        "playerGuardPartition",
                        "playerGuardConnectedPlayers",
                    ):
                        with self.subTest(target=target, package_root_marker=marker):
                            self.assertIn(marker, package_root_surface["required"])
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
        for doc, item in report["docs"].items():
            with self.subTest(doc=doc, marker="evidence-inventory"):
                self.assertTrue(item["passed"])
                self.assertIn("ue4ss-evidence-inventory.md", item["required"])
                self.assertIn("summarize-ue4ss-evidence-inventory.py", item["required"])

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
        self.assertIn("package `artifact-layout`", text)
        self.assertIn("`compat-globals`", text)
        self.assertIn("`custom-property`", text)
        self.assertIn("package `generic-unreal-target-selection`", text)
        self.assertIn("package `package-route-slot-proof`", text)
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

    def test_artifact_layout_blocks_missing_packaged_runbook_tools(self):
        module = load_contract_module()
        result = module.package_artifact_layout_result(
            "linux-server",
            "$stage/scripts/ue4ss-port-readiness.py\n"
            "$stage/scripts/summarize-ue4ss-port-gaps.py\n",
        )

        self.assertFalse(result["passed"])
        self.assertIn("$stage/scripts/verify-ue4ss-package-review-bundle.py", result["missing"])
        self.assertIn("$stage/scripts/summarize-ue4ss-evidence-inventory.py", result["missing"])
        self.assertIn("$stage/tests/test-ue4ss-evidence-inventory.py", result["missing"])
        self.assertIn("$stage/docs/ue4ss-portability-contract.md", result["missing"])

    def test_package_loading_surface_requires_load_class_native_bridge(self):
        module = load_contract_module()
        markers = module.SURFACES["package-loading-anchors"]

        for marker in (
            "StaticLoadClass",
            "GetLoadClassPackageAbiState",
            "GetLoadClassPackageCallFrameVerificationState",
            "GetLoadClassPackageNativeExecutorState",
            "InvokeLoadClassPackageNative",
            "lua-load-class-package-native-invoke",
            "signatureFamily=StaticLoadClass",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, markers)


if __name__ == "__main__":
    unittest.main()
