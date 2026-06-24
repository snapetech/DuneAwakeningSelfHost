#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-callfunction-hook-candidate-canaries.py"

spec = importlib.util.spec_from_file_location("run_callfunction_hook_candidate_canaries", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class RunCallFunctionHookCandidateCanariesTests(unittest.TestCase):
    def sample_report(self):
        return {
            "candidates": [
                {
                    "rank": 1,
                    "imageOffset": "0xabc",
                    "narrowScore": 200,
                    "rawScore": 120,
                    "env": {
                        "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE": "true",
                        "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET": "0xabc",
                    },
                }
            ]
        }

    def test_build_plan_writes_candidate_env_and_preflight_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = module.build_plan(
                self.sample_report(),
                output_dir=Path(tmp),
                canary_script=Path("scripts/canary-linux-server-loader.sh"),
                target_env_file=Path(".env"),
                limit=1,
                preflight_only=True,
                capture_delay=30,
                strict_verify=True,
            )

            self.assertEqual(len(rows), 1)
            env_file = Path(rows[0]["envFile"])
            self.assertTrue(env_file.exists())
            self.assertIn("DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET=0xabc", env_file.read_text())
            self.assertTrue(Path(rows[0]["command"]["env"]["DUNE_LINUX_SERVER_CANARY_EXTRA_ENV"]).is_absolute())
            self.assertEqual(rows[0]["command"]["env"]["DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY"], "true")
            self.assertEqual(rows[0]["command"]["env"]["DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY"], "true")
            self.assertIn("rank1-0xabc", rows[0]["expectedLoaderLog"])

    def test_log_passed_requires_all_runtime_hook_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "event=ue-call-function-hook status=passed selfTestTarget=false callSelfTest=false\n",
                encoding="utf-8",
            )
            self.assertTrue(module.log_passed(log))
            log.write_text("event=ue-call-function-hook status=failed selfTestTarget=false callSelfTest=false\n", encoding="utf-8")
            self.assertFalse(module.log_passed(log))
            self.assertTrue(module.log_failed(log))

    def test_evaluate_candidate_log_can_use_copied_log_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "rank02-0xdef.log"
            log.write_text(
                "event=ue-call-function-hook status=passed selfTestTarget=false callSelfTest=false\n",
                encoding="utf-8",
            )
            candidate = {"rank": 2, "imageOffset": "0xdef"}

            result = module.evaluate_candidate_log(candidate, log_dir=Path(tmp))

            self.assertTrue(result["exists"])
            self.assertTrue(result["hookProbePassed"])
            self.assertFalse(result["hookProbeFailed"])
            self.assertIn("status=passed", result["eventLines"][0])

    def test_evaluate_candidate_log_prefers_canary_backup_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "backups" / "canary-linux-loader" / "stamp"
            backup_dir.mkdir(parents=True)
            log = backup_dir / "dune-server-probe-loader-callfunction-rank1-0xabc.log"
            log.write_text(
                "event=ue-call-function-hook status=passed selfTestTarget=false callSelfTest=false\n",
                encoding="utf-8",
            )
            candidate = {"rank": 1, "imageOffset": "0xabc"}

            result = module.evaluate_candidate_log(candidate, backup_dir=backup_dir)

            self.assertTrue(result["hookProbePassed"])
            self.assertEqual(Path(result["path"]), log)

    def test_extract_backup_dir_reads_last_backup_dir_line(self):
        stdout = "backup_dir=old\nother\nbackup_dir=backups/canary-linux-loader/latest\n"

        self.assertEqual(module.extract_backup_dir(stdout), "backups/canary-linux-loader/latest")

    def test_markdown_contains_command_and_next_gate(self):
        report = {
            "schemaVersion": module.SCHEMA_VERSION,
            "candidateCount": 1,
            "execute": False,
            "preflightOnly": True,
            "nativeCallAllowed": False,
            "nextGate": "target-entry active validation",
            "candidates": [
                {
                    "rank": 1,
                    "imageOffset": "0xabc",
                    "envFile": "candidate.env",
                    "expectedLoaderLog": "/tmp/log",
                    "command": {"shell": "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=true scripts/canary-linux-server-loader.sh .env"},
                }
            ],
        }

        text = module.markdown(report)

        self.assertIn("Preflight only: `true`", text)
        self.assertIn("target-entry active validation", text)
        self.assertIn("canary-linux-server-loader.sh", text)

    def test_summarize_does_not_execute_without_execute_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text('{"candidates":[{"rank":1,"imageOffset":"0xabc","env":{"A":"B"}}]}', encoding="utf-8")
            args = Namespace(
                candidates_json=candidates,
                output_dir=Path(tmp) / "out",
                canary_script=Path("scripts/canary-linux-server-loader.sh"),
                env_file=Path(".env"),
                limit=1,
                preflight_only=True,
                capture_delay_seconds=30,
                log_dir=None,
                strict_verify=False,
                execute=False,
                stop_on_first_pass=True,
            )

            report = module.summarize(args)

            self.assertFalse(report["execute"])
            self.assertEqual(report["executedCount"], 0)
            self.assertFalse(report["nativeCallAllowed"])

    def test_summarize_reports_first_observed_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "candidates.json"
            candidates.write_text(
                '{"candidates":['
                '{"rank":1,"imageOffset":"0xabc","env":{"A":"B"}},'
                '{"rank":2,"imageOffset":"0xdef","env":{"A":"C"}}'
                "]}",
                encoding="utf-8",
            )
            log = Path(tmp) / "rank02-0xdef.log"
            log.write_text(
                "event=ue-call-function-hook status=passed selfTestTarget=false callSelfTest=false\n",
                encoding="utf-8",
            )
            args = Namespace(
                candidates_json=candidates,
                output_dir=Path(tmp) / "out",
                canary_script=Path("scripts/canary-linux-server-loader.sh"),
                env_file=Path(".env"),
                limit=2,
                preflight_only=True,
                capture_delay_seconds=30,
                log_dir=Path(tmp),
                strict_verify=False,
                execute=False,
                stop_on_first_pass=True,
            )

            report = module.summarize(args)

            self.assertEqual(report["firstObservedHookProbePass"]["imageOffset"], "0xdef")
            self.assertTrue(report["candidates"][1]["observedLog"]["hookProbePassed"])


if __name__ == "__main__":
    unittest.main()
