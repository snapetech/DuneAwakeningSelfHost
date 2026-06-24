#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-callfunction-active-validation.py"

spec = importlib.util.spec_from_file_location("plan_callfunction_active_validation", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PlanCallFunctionActiveValidationTests(unittest.TestCase):
    def test_first_hook_pass_uses_observed_candidate(self):
        observed = {
            "candidates": [
                {"imageOffset": "0x1", "observedLog": {"hookProbePassed": False}},
                {"imageOffset": "0x2", "observedLog": {"hookProbePassed": True}},
            ]
        }

        self.assertEqual(module.first_hook_pass(observed), "0x2")

    def test_missing_runtime_candidate_emits_read_only_discovery_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(json.dumps({"firstObservedHookProbePass": "0xa043d60"}), encoding="utf-8")
            args = Namespace(
                observed_json=observed,
                active_validation_candidates_json=None,
                hook_offset="",
                allow_native_call=False,
            )

            report = module.summarize(args)

            self.assertEqual(report["status"], "needs-runtime-object-command-evidence")
            self.assertFalse(report["nativeCallAllowed"])
            env = {item["name"]: item["value"] for item in report["env"]}
            self.assertEqual(env["DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE"], "false")
            self.assertEqual(env["DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
            self.assertEqual(env["DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE"], "true")

    def test_candidate_without_native_opt_in_still_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(json.dumps({"firstObservedHookProbePass": "0xa043d60"}), encoding="utf-8")
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(
                json.dumps({"activeValidationCandidates": [{"objectAddress": "0x1000", "callFunctionCommand": "GetName"}]}),
                encoding="utf-8",
            )
            args = Namespace(
                observed_json=observed,
                active_validation_candidates_json=candidates,
                hook_offset="",
                allow_native_call=False,
            )

            report = module.summarize(args)

            self.assertEqual(report["status"], "needs-runtime-object-command-evidence")
            self.assertIn("--allow-native-call was not set", " ".join(report["blockers"]))

    def test_candidate_with_native_opt_in_emits_active_validation_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(json.dumps({"firstObservedHookProbePass": "0xa043d60"}), encoding="utf-8")
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(
                json.dumps({"activeValidationCandidates": [{"objectAddress": "0x1000", "callFunctionCommand": "GetName"}]}),
                encoding="utf-8",
            )
            args = Namespace(
                observed_json=observed,
                active_validation_candidates_json=candidates,
                hook_offset="",
                allow_native_call=True,
            )

            report = module.summarize(args)

            self.assertEqual(report["status"], "active-validation-ready")
            self.assertTrue(report["nativeCallAllowed"])
            env = {item["name"]: item["value"] for item in report["env"]}
            self.assertEqual(env["DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE"], "true")
            self.assertEqual(env["DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x1000")
            self.assertEqual(env["DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND"], "GetName")


if __name__ == "__main__":
    unittest.main()
