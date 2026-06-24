#!/usr/bin/env python3
import importlib.util
import json
import tarfile
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "package-callfunction-hook-canary-bundle.py"

spec = importlib.util.spec_from_file_location("package_callfunction_hook_canary_bundle", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageCallFunctionHookCanaryBundleTests(unittest.TestCase):
    def test_command_list_targets_kspls0_and_requires_full_canary_flag(self):
        commands = module.command_list("kspls0", "bundle.tar.gz", "/tmp/bundle", "/remote/repo", Path("/repo"))

        self.assertIn("ssh kspls0", commands["copyBundle"])
        self.assertIn("tar -xzf /tmp/bundle/bundle.tar.gz -C /tmp/bundle/stage", commands["unpackBundle"])
        self.assertIn("hostname", commands["runFullSequence"])
        self.assertIn("--canary-script /remote/repo/scripts/canary-linux-server-loader.sh", commands["runFullSequence"])
        self.assertIn("--env-file /remote/repo/.env", commands["runFullSequence"])
        self.assertIn("--execute --full-canary", commands["runFullSequence"])
        self.assertIn("callfunction-hook-canary-result.json", commands["copyBackResults"])

    def test_package_writes_manifest_and_tarball(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            candidate_dir.mkdir()
            (candidate_dir / "rank01.env").write_text("A=B\n", encoding="utf-8")
            files = {}
            for name in ("validation.json", "validation.md", "plan.md"):
                path = root / name
                path.write_text("{}\n" if name.endswith(".json") else "# doc\n", encoding="utf-8")
                files[name] = path
            plan_json = root / "plan.json"
            plan_json.write_text(json.dumps({"candidateCount": 1}), encoding="utf-8")
            script_dir = root / "scripts"
            script_dir.mkdir()
            for script_name in (
                "canary-linux-server-loader.sh",
                "run-callfunction-hook-candidate-canaries.py",
                "export-callfunction-hook-validation-candidates.py",
            ):
                (script_dir / script_name).write_text("#!/bin/sh\n", encoding="utf-8")
            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                args = Namespace(
                    remote="kspls0",
                    remote_root="/tmp/bundle",
                    remote_repo="/remote/repo",
                    candidate_dir=candidate_dir,
                    validation_json=files["validation.json"],
                    validation_md=files["validation.md"],
                    plan_json=plan_json,
                    plan_md=files["plan.md"],
                    tarball=root / "bundle.tar.gz",
                    manifest=root / "manifest.json",
                )

                manifest = module.package(args)
            finally:
                os.chdir(old_cwd)

            self.assertEqual(manifest["candidateCount"], 1)
            self.assertEqual(manifest["remoteRepo"], "/remote/repo")
            self.assertFalse(manifest["nativeCallAllowed"])
            self.assertTrue((root / "bundle.tar.gz").exists())
            self.assertTrue((root / "manifest.json").exists())
            with tarfile.open(root / "bundle.tar.gz", "r:gz") as tar:
                names = set(tar.getnames())
            self.assertIn(str(candidate_dir / "rank01.env").lstrip("/"), names)
            self.assertIn(str(plan_json).lstrip("/"), names)

    def test_markdown_lists_safety_and_commands(self):
        text = module.markdown(
            {
                "schemaVersion": module.SCHEMA_VERSION,
                "remote": "kspls0",
                "remoteRoot": "/tmp/bundle",
                "remoteRepo": "/remote/repo",
                "tarball": "bundle.tar.gz",
                "candidateCount": 1,
                "nativeCallAllowed": False,
                "safety": ["bundle does not execute remotely by itself"],
                "commands": {"runFullSequence": "ssh kspls0 'hostname'"},
            }
        )

        self.assertIn("Native call allowed: `false`", text)
        self.assertIn("bundle does not execute remotely by itself", text)
        self.assertIn("runFullSequence", text)


if __name__ == "__main__":
    unittest.main()
