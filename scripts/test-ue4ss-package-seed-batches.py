#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-seed-batches.py"

spec = importlib.util.spec_from_file_location("plan_ue4ss_package_seed_batches", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageSeedBatchPlanTests(unittest.TestCase):
    def sample_plan(self):
        return {
            "sourcePath": "external.json",
            "historicalStringSeeds": [
                {"name": "LoadObject", "address": "0x814c33"},
                {"name": "LoadObject", "address": "0x815640"},
                {"name": "LoadObject", "address": "0x81567c"},
                {"name": "LoadObject", "address": "0x1268545"},
                {"name": "LoadObject", "address": "0x59afafa"},
                {"name": "LoadObject", "address": "0x59f0b4b"},
                {"name": "LoadPackage", "address": "0x5ae6260"},
                {"name": "Ignored", "address": "0x1"},
                {"name": "LoadPackage", "address": "0x5ae6260"},
            ],
        }

    def test_batches_cover_unique_supported_seeds_once(self):
        report = module.build_batches(self.sample_plan(), batch_size=4)

        self.assertEqual(report["schemaVersion"], "dune-ue4ss-package-seed-batches/v1")
        self.assertEqual(report["seedCount"], 7)
        self.assertEqual(report["batchCount"], 2)
        addresses = [
            seed["address"]
            for batch in report["batches"]
            for seed in batch["seeds"]
        ]
        self.assertEqual(len(addresses), len(set(addresses)))
        self.assertIn("0x5ae6260", addresses)
        self.assertEqual(report["batches"][0]["seeds"][0]["name"], "LoadPackage")

    def test_commands_set_seed_addresses_and_limit(self):
        report = module.build_batches(self.sample_plan(), batch_size=4)
        first = report["batches"][0]

        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS=", first["freshTraceCommand"])
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT=4", first["freshTraceCommand"])
        self.assertIn("scripts/run-ue4ss-package-live-stimulus-trace.sh --wait 30", first["freshTraceCommand"])
        self.assertIn("--preflight-only --wait 30", first["freshPreflightCommand"])

    def test_cli_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "external.json"
            path.write_text(json.dumps(self.sample_plan()), encoding="utf-8")
            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--external-plan-json",
                    str(path),
                    "--batch-size",
                    "3",
                    "--format",
                    "json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["batchSize"], 3)
        self.assertEqual(report["batchCount"], 3)


if __name__ == "__main__":
    unittest.main()
