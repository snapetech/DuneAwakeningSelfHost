#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-callfunction-source-abi-recovery.py"

spec = importlib.util.spec_from_file_location("callfunction_source_abi_recovery", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class CallFunctionSourceAbiRecoveryTests(unittest.TestCase):
    def write_loader(self, root):
        path = root / "loader.c"
        path.write_text(
            """
            typedef int (*CallFunctionByNameFn)(void *, const void *, void *, void *, int);
            static int call_function_live_hook_replacement(void *object, const void *command, void *output, void *executor, int force_call) { return 0; }
            static void run_call_function_active_validation(const char *phase) {
              const char *flag = "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET";
              (void)flag;
            }
            static int lua_get_call_function_native_executor_state_callback(void *state) { return 0; }
            static int lua_invoke_call_function_native_callback(void *state) { return 0; }
            static const char *pre = "RegisterCallFunctionByNameWithArgumentsPreHook";
            static const char *post = "RegisterCallFunctionByNameWithArgumentsPostHook";
            """,
            encoding="utf-8",
        )
        return path

    def test_marks_source_abi_ready_while_runtime_target_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = self.write_loader(Path(tmp))

            summary = module.summarize(
                loader,
                readiness={"ready": {"ueCallFunctionHookRuntimeTarget": False}},
                target_recovery={
                    "status": "noPromotableCallFunctionStringTarget",
                    "dataflowArtifacts": {"manualStringDataflowJson": "x.json"},
                    "callFunctionStringHits": [{"promotable": False}, {"promotable": False}],
                },
            )

        self.assertTrue(summary["sourceAbiReady"])
        self.assertFalse(summary["complete"])
        self.assertIn("no promotable CallFunctionByNameWithArguments string-derived target", summary["blockers"])
        self.assertIn("no non-self-test CallFunction hook runtime target proof", summary["blockers"])

    def test_marks_complete_when_contract_and_runtime_evidence_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = self.write_loader(Path(tmp))

            summary = module.summarize(
                loader,
                readiness={
                    "ready": {
                        "ueCallFunctionHookRuntimeTarget": True,
                        "ueCallFunctionActiveValidation": True,
                    }
                },
                target_recovery={"callFunctionStringHits": [{"promotable": True}]},
            )

        self.assertTrue(summary["sourceAbiReady"])
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["blockers"], [])


if __name__ == "__main__":
    unittest.main()
