#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-callfunction-hook-validation-candidates.py"

spec = importlib.util.spec_from_file_location("export_callfunction_hook_validation_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ExportCallFunctionHookValidationCandidatesTests(unittest.TestCase):
    def test_build_candidates_uses_narrowed_rows_and_disables_native_call(self):
        summary = {
            "candidateCount": 100,
            "narrowedCandidates": [
                {
                    "function": "0xaaa",
                    "score": 140,
                    "signature": {"sha256": "sha"},
                    "narrowing": {
                        "score": 220,
                        "signatureRepeatCount": 1,
                        "indirectPatternRepeatCount": 1,
                        "directTargetPatternRepeatCount": 1,
                        "uniqueDirectTargetCount": 5,
                        "repeatedVtableShape": False,
                    },
                },
                {
                    "function": "0xbbb",
                    "score": 130,
                    "signature": {"sha256": "sha2"},
                    "narrowing": {
                        "score": 200,
                        "signatureRepeatCount": 2,
                        "indirectPatternRepeatCount": 3,
                        "directTargetPatternRepeatCount": 4,
                        "uniqueDirectTargetCount": 2,
                        "repeatedVtableShape": True,
                    },
                },
            ],
        }

        rows = module.build_candidates(summary, prefix="DUNE_TEST", limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["imageOffset"], "0xaaa")
        self.assertFalse(rows[0]["promotable"])
        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_HOOK_PROBE"], "true")
        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET"], "0xaaa")
        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_ACTIVE_VALIDATE"], "false")
        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"], "false")
        self.assertIn("DUNE_TEST_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS=0x...", rows[0]["activeValidationPending"]["requiredEnv"])

    def test_live_hook_stage_exports_live_hook_vars(self):
        summary = {
            "candidateCount": 1,
            "narrowedCandidates": [{"function": "0x111", "score": 100, "narrowing": {"score": 120}}],
        }

        rows = module.build_candidates(summary, prefix="DUNE_TEST", limit=1, stage="live-hook")

        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_LIVE_HOOK"], "true")
        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET"], "0x111")
        self.assertEqual(rows[0]["env"]["DUNE_TEST_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS"], "true")

    def test_markdown_contains_shell_env_and_blocker(self):
        report = {
            "schemaVersion": module.SCHEMA_VERSION,
            "sourceCandidateCount": 1,
            "sourceNarrowedCandidateCount": 1,
            "candidateCount": 1,
            "validationStage": "hook-probe",
            "nativeCallAllowed": False,
            "promotable": False,
            "promotionBlockers": ["static target candidates require guarded hook probe"],
            "candidates": [
                {
                    "rank": 1,
                    "imageOffset": "0x111",
                    "narrowScore": 120,
                    "rawScore": 100,
                    "signatureRepeatCount": 1,
                    "indirectPatternRepeatCount": 1,
                    "directTargetPatternRepeatCount": 1,
                    "shellEnv": "DUNE_TEST_UE_CALL_FUNCTION_HOOK_PROBE=true",
                }
            ],
        }

        text = module.markdown(report)

        self.assertIn("Promotable: `false`", text)
        self.assertIn("DUNE_TEST_UE_CALL_FUNCTION_HOOK_PROBE=true", text)
        self.assertIn("static target candidates require guarded hook probe", text)


if __name__ == "__main__":
    unittest.main()
