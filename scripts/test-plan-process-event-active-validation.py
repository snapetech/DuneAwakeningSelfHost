#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-process-event-active-validation.py"

spec = importlib.util.spec_from_file_location("plan_process_event_active_validation", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PlanProcessEventActiveValidationTests(unittest.TestCase):
    def test_first_target_accepts_vtable_shortlist(self):
        observed = {
            "hookProbeShortlist": [
                {
                    "slot": 64,
                    "topTarget": {
                        "targetName": "ProcessEvent",
                        "imageOffset": "0xfb4b060",
                    },
                }
            ]
        }

        self.assertEqual(module.first_process_event_target(observed), "0xfb4b060")

    def test_first_target_accepts_direct_canary_plan_hook_offset(self):
        observed = {"hookOffset": "0xfb4b060"}

        self.assertEqual(module.first_process_event_target(observed), "0xfb4b060")

    def test_first_target_accepts_nested_process_event_runtime_evidence(self):
        observed = {
            "nextCanaryContract": {
                "processEventRuntimeEvidence": {
                    "hookRuntimeTarget": True,
                    "imageOffset": "0xfb4b060",
                }
            }
        }

        self.assertEqual(module.first_process_event_target(observed), "0xfb4b060")

    def test_missing_reviewed_candidate_emits_no_native_discovery_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(
                json.dumps(
                    {
                        "hookProbeShortlist": [
                            {
                                "topTarget": {
                                    "targetName": "ProcessEvent",
                                    "imageOffset": "0xfb4b060",
                                }
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(
                json.dumps(
                    {
                        "activeValidationCandidates": [
                            {
                                "objectAddress": "0x1000",
                                "functionAddress": "0x2000",
                                "nativeCallAllowed": False,
                                "reviewRequired": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                observed_json=observed,
                active_validation_candidates_json=candidates,
                hook_offset="",
                allow_native_call=False,
            )

            report = module.summarize(args)

        self.assertEqual(report["status"], "needs-reviewed-runtime-object-function-evidence")
        self.assertFalse(report["nativeCallAllowed"])
        self.assertIn("no candidate is explicitly reviewed", " ".join(report["blockers"]))
        env = {item["name"]: item["value"] for item in report["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE"], "false")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS"], "32768")

    def test_reviewed_candidate_still_requires_cli_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(json.dumps({"firstObservedHookProbePass": "0xfb4b060"}), encoding="utf-8")
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(
                json.dumps(
                    {
                        "activeValidationCandidates": [
                            {
                                "objectAddress": "0x1000",
                                "functionAddress": "0x2000",
                                "nativeCallAllowed": True,
                                "reviewRequired": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                observed_json=observed,
                active_validation_candidates_json=candidates,
                hook_offset="",
                allow_native_call=False,
            )

            report = module.summarize(args)

        self.assertEqual(report["reviewedNativeCandidateCount"], 1)
        self.assertIn("--allow-native-call was not set", " ".join(report["blockers"]))

    def test_reviewed_candidate_with_opt_in_emits_active_validation_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(json.dumps({"firstObservedHookProbePass": "0xfb4b060"}), encoding="utf-8")
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(
                json.dumps(
                    {
                        "activeValidationCandidates": [
                            {
                                "objectAddress": "0x1000",
                                "functionAddress": "0x2000",
                                "paramsAddress": "0x3000",
                                "nativeCallAllowed": True,
                                "reviewRequired": False,
                            }
                        ]
                    }
                ),
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
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS"], "0x1000")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS"], "0x2000")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS"], "0x3000")

    def test_synthetic_runtime_validation_keeps_native_call_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = Path(tmp) / "observed.json"
            observed.write_text(json.dumps({"firstObservedHookProbePass": "0xfb4b060"}), encoding="utf-8")
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(json.dumps({"activeValidationCandidates": []}), encoding="utf-8")
            args = Namespace(
                observed_json=observed,
                active_validation_candidates_json=candidates,
                hook_offset="",
                allow_native_call=False,
                synthetic_runtime_validate=True,
            )

            report = module.summarize(args)

        self.assertEqual(report["status"], "synthetic-runtime-validation-ready")
        self.assertFalse(report["nativeCallAllowed"])
        self.assertFalse(report["reviewRequired"])
        self.assertIn("strict native active validation remains blocked", " ".join(report["blockers"]))
        env = {item["name"]: item["value"] for item in report["env"]}
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_SYNTHETIC_RUNTIME_VALIDATE"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL"], "true")
        self.assertEqual(env["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS", env)
        self.assertNotIn("DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS", env)


if __name__ == "__main__":
    unittest.main()
