#!/usr/bin/env python3
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ue4ss-package-remote-trace.sh"
RUNTIME_TRACE = ROOT / "scripts" / "ue4ss-package-runtime-trace.sh"


def json_runbook(trace_log, cleanup_command):
    return json.dumps(
        {
            "traceLog": trace_log,
            "cleanupCommand": cleanup_command,
        },
        sort_keys=True,
    )


class PackageRemoteTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_remote_trace_is_host_guarded_and_temp_staged(self):
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST:-kspls0", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_ANY_HOST", self.source)
        self.assertIn("refusing remote package trace", self.source)
        self.assertIn("/tmp/ue4ss-package-runtime-trace-handoff", self.source)
        self.assertIn("stage_remote_files", self.source)
        self.assertIn("scp -q", self.source)
        self.assertIn("chmod +x", self.source)

    def test_remote_trace_requires_zero_players_before_preflight_or_arm(self):
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PARTITION:-8", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_DB:-dune_sb_1_4_0_0", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS:-false", self.source)
        self.assertIn('if [[ "$required_host" == "kspls0" && "$allow_players" == "true" ]]; then', self.source)
        self.assertIn("ALLOW_PLAYERS=true is not allowed for live host kspls0", self.source)
        self.assertIn("remote_connected_players()", self.source)
        self.assertIn("require_zero_players()", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PHASE", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_PARTITION", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAYER_GUARD_CONNECTED_PLAYERS", self.source)
        self.assertIn("dune.world_partition", self.source)
        self.assertIn("dune.farm_state", self.source)
        self.assertIn("connected_players", self.source)
        self.assertIn('if [[ "$action" == "preflight" || "$action" == "arm" || "$action" == "status" ]]; then', self.source)
        self.assertIn('require_zero_players "$action"', self.source)
        self.assertIn("refusing remote package trace", self.source)
        status_guard = self.source.index('if [[ "$action" == "preflight" || "$action" == "arm" || "$action" == "status" ]]; then')
        stage_call = self.source.index("stage_remote_files", status_guard)
        self.assertLess(status_guard, stage_call)

    def test_remote_trace_stages_runtime_trace_dependencies(self):
        for path in (
            "scripts/ue4ss-package-runtime-trace.sh",
            "scripts/plan-ue4ss-package-runtime-trace.py",
            "scripts/summarize-ue4ss-package-runtime-trace-evidence.py",
            "scripts/review-ue4ss-package-abi.py",
            "scripts/export-ue4ss-package-promotion-env.py",
            "scripts/summarize-ue4ss-package-promotion-dir.py",
            "scripts/plan-ue4ss-package-next-action.py",
            "scripts/verify-ue4ss-package-review-bundle.py",
            "scripts/verify-ue4ss-package-live-stimulus-summary.py",
            "scripts/plan-ue4ss-canary-env.py",
        ):
            self.assertIn(path, self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON", self.source)
        self.assertIn('stage_file_as "$external_plan"', self.source)
        self.assertIn('stage_file_as "$trace_plan_json"', self.source)
        self.assertIn('stage_file_as "$trace_plan_md"', self.source)
        self.assertIn('stage_file_as "$method_candidates"', self.source)
        self.assertIn('stage_file_as "$live_trace_runbook_json"', self.source)
        self.assertIn("stage_remote_stop_file()", self.source)
        self.assertIn('if [[ "$action" == "stop" ]]; then', self.source)
        self.assertIn("stage_remote_stop_file", self.source)
        self.assertIn("build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json", self.source)
        self.assertIn("build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.json", self.source)
        self.assertIn("build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.md", self.source)
        self.assertIn("build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json", self.source)
        self.assertIn("build/server-ue-package-loader-vtables.json", self.source)

    def test_remote_trace_stages_all_runtime_trace_script_dependencies(self):
        runtime_source = RUNTIME_TRACE.read_text(encoding="utf-8")
        helper_names = sorted(
            set(re.findall(r"\$repo_root/scripts/([A-Za-z0-9_.-]+(?:\.py|\.sh))", runtime_source))
        )
        self.assertTrue(helper_names)
        self.assertIn("verify-ue4ss-package-route-slot-recovery.py", helper_names)
        for helper in helper_names:
            with self.subTest(helper=helper):
                self.assertIn(f"scripts/{helper}", self.source)

    def test_runtime_status_detaches_gdb_before_hashing_review_bundle(self):
        runtime_source = RUNTIME_TRACE.read_text(encoding="utf-8")

        detach_pos = runtime_source.index("status_detach=begin")
        evidence_pos = runtime_source.index('echo "--evidence--"')
        bundle_pos = runtime_source.index('write_review_bundle "$trace_log"')

        self.assertLess(detach_pos, evidence_pos)
        self.assertLess(detach_pos, bundle_pos)

    def test_remote_trace_prints_preflight_arm_status_handoff(self):
        self.assertIn("print|preflight|arm|status|stop", self.source)
        self.assertIn("remote_preflight=$(remote_command)", self.source)
        self.assertIn("remote_arm=$(remote_command)", self.source)
        self.assertIn("remote_status=$(remote_command)", self.source)
        self.assertIn("remote_stop=$(remote_command)", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAN=$remote_external", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_METHOD_CANDIDATES=$remote_method_candidates", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON=$remote_trace_plan_json", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD=$remote_trace_plan_md", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON=$remote_live_trace_runbook_json", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR:-LoadPackage,LoadObject", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY:-LoadPackage", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=$trace_anchor", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_SEED_ADDRESS=$trace_seed_address", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_LIMIT:-4", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_METHOD_LIMIT=$trace_method_limit", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=$trace_route_address", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=$trace_signature_family", self.source)

    def test_print_action_is_local_dry_render_before_ssh_guards(self):
        print_pos = self.source.index('if [[ "$action" == "print" ]]; then')
        host_guard_pos = self.source.index("assert_remote_host", print_pos)
        self.assertLess(print_pos, host_guard_pos)

    def test_print_action_runs_without_remote_connection_when_inputs_are_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "ue4ss-package-external-symbol-plan.json"
            trace_json = root / "ue4ss-package-runtime-trace-plan.json"
            trace_md = root / "ue4ss-package-runtime-trace-plan.md"
            methods = root / "ue-package-loader-vtables.json"
            runbook = root / "ue4ss-package-stimulus-trace-runbook.json"
            for path in (external, trace_json, methods):
                path.write_text("{}", encoding="utf-8")
            trace_md.write_text("# trace plan\n", encoding="utf-8")
            runbook.write_text(
                json_runbook(
                    trace_log="/tmp/package-trace.log",
                    cleanup_command=(
                        "scripts/ue4ss-package-remote-trace.sh stop "
                        "not-a-real-host dune_server-deep-desert-1 /tmp/package-trace.log"
                    ),
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "print",
                    "not-a-real-host",
                    "dune_server-deep-desert-1",
                    "/tmp/package-trace.log",
                ],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": str(external),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": str(trace_json),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": str(trace_md),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": str(methods),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON": str(runbook),
                },
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertIn("remote_preflight=env", proc.stdout)
        self.assertIn("remote_arm=env", proc.stdout)
        self.assertIn("remote_status=env", proc.stdout)
        self.assertIn("remote_stop=env", proc.stdout)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON=", proc.stdout)
        self.assertNotIn("remote_host=", proc.stdout)
        self.assertEqual(proc.stderr, "")

    def test_print_action_rejects_allow_players_on_live_host_before_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "ue4ss-package-external-symbol-plan.json"
            trace_json = root / "ue4ss-package-runtime-trace-plan.json"
            trace_md = root / "ue4ss-package-runtime-trace-plan.md"
            methods = root / "ue-package-loader-vtables.json"
            runbook = root / "ue4ss-package-stimulus-trace-runbook.json"
            for path in (external, trace_json, methods):
                path.write_text("{}", encoding="utf-8")
            trace_md.write_text("# trace plan\n", encoding="utf-8")
            runbook.write_text(
                json_runbook(
                    trace_log="/tmp/package-trace.log",
                    cleanup_command=(
                        "scripts/ue4ss-package-remote-trace.sh stop "
                        "not-a-real-host dune_server-deep-desert-1 /tmp/package-trace.log"
                    ),
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "print",
                    "not-a-real-host",
                    "dune_server-deep-desert-1",
                    "/tmp/package-trace.log",
                ],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": str(external),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": str(trace_json),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": str(trace_md),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": str(methods),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON": str(runbook),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST": "kspls0",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "true",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("ALLOW_PLAYERS=true is not allowed for live host kspls0", proc.stderr)
        self.assertNotIn("remote_host=", proc.stdout)

    def test_print_action_rejects_trace_log_mismatch_with_live_runbook_before_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "ue4ss-package-external-symbol-plan.json"
            trace_json = root / "ue4ss-package-runtime-trace-plan.json"
            trace_md = root / "ue4ss-package-runtime-trace-plan.md"
            methods = root / "ue-package-loader-vtables.json"
            runbook = root / "ue4ss-package-stimulus-trace-runbook.json"
            for path in (external, trace_json, methods):
                path.write_text("{}", encoding="utf-8")
            trace_md.write_text("# trace plan\n", encoding="utf-8")
            runbook.write_text(
                json_runbook(
                    trace_log="/tmp/current-package-trace.log",
                    cleanup_command=(
                        "scripts/ue4ss-package-remote-trace.sh stop "
                        "not-a-real-host dune_server-deep-desert-1 /tmp/current-package-trace.log"
                    ),
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "print",
                    "not-a-real-host",
                    "dune_server-deep-desert-1",
                    "/tmp/stale-package-trace.log",
                ],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": str(external),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": str(trace_json),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": str(trace_md),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": str(methods),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON": str(runbook),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("trace_log must match live trace runbook traceLog", proc.stderr)
        self.assertIn("/tmp/current-package-trace.log", proc.stderr)
        self.assertNotIn("remote_host=", proc.stdout)

    def test_print_action_rejects_cleanup_command_mismatch_before_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "ue4ss-package-external-symbol-plan.json"
            trace_json = root / "ue4ss-package-runtime-trace-plan.json"
            trace_md = root / "ue4ss-package-runtime-trace-plan.md"
            methods = root / "ue-package-loader-vtables.json"
            runbook = root / "ue4ss-package-stimulus-trace-runbook.json"
            for path in (external, trace_json, methods):
                path.write_text("{}", encoding="utf-8")
            trace_md.write_text("# trace plan\n", encoding="utf-8")
            runbook.write_text(
                json_runbook(
                    trace_log="/tmp/package-trace.log",
                    cleanup_command=(
                        "scripts/ue4ss-package-remote-trace.sh stop "
                        "not-a-real-host dune_server-deep-desert-1 /tmp/stale-package-trace.log"
                    ),
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "print",
                    "not-a-real-host",
                    "dune_server-deep-desert-1",
                    "/tmp/package-trace.log",
                ],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": str(external),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": str(trace_json),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": str(trace_md),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": str(methods),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON": str(runbook),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("cleanupCommand must match stop not-a-real-host dune_server-deep-desert-1 /tmp/package-trace.log", proc.stderr)
        self.assertNotIn("remote_host=", proc.stdout)

    def test_stop_action_does_not_require_local_plans_or_live_runbook_before_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "bin"
            fake_bin.mkdir()
            calls = Path(tmp) / "calls.log"
            ssh = fake_bin / "ssh"
            scp = fake_bin / "scp"
            ssh.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'ssh %s\\n' \"$*\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "if [[ \"$*\" == *\"hostname\"* ]]; then echo kspls0; exit 0; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            scp.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'scp %s\\n' \"$*\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            ssh.chmod(0o755)
            scp.chmod(0o755)

            proc = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "stop",
                    "kspls0",
                    "dune_server-deep-desert-1",
                    "/tmp/stale-package-trace.log",
                ],
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": str(Path(tmp) / "missing-external.json"),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": str(Path(tmp) / "missing-plan.json"),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": str(Path(tmp) / "missing-plan.md"),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": str(Path(tmp) / "missing-methods.json"),
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON": str(Path(tmp) / "missing-runbook.json"),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("missing external plan", proc.stderr)
            self.assertNotIn("missing live trace runbook", proc.stderr)
            call_text = calls.read_text(encoding="utf-8")
            self.assertIn("scp -q", call_text)
            self.assertIn("scripts/ue4ss-package-runtime-trace.sh", call_text)
            scp_lines = "\n".join(line for line in call_text.splitlines() if line.startswith("scp "))
            self.assertNotIn("ue4ss-package-external-symbol-plan.json", scp_lines)
            self.assertNotIn("ue4ss-package-stimulus-trace-runbook.json", scp_lines)


if __name__ == "__main__":
    unittest.main()
