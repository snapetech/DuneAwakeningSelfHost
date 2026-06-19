#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "brt-dd-live-canary.sh"


class BrtDdLiveCanaryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def function_body(self, name: str) -> str:
        match = re.search(rf"^{name}\(\) \{{\n(?P<body>.*?)\n\}}", self.source, re.M | re.S)
        self.assertIsNotNone(match, f"missing shell function: {name}")
        return match.group("body")

    def test_ready_collects_before_arm_and_alerts_tester(self):
        body = self.function_body("ready")
        collect_pos = body.find("\n  collect prearm")
        arm_pos = body.find("\n  arm")

        self.assertGreaterEqual(collect_pos, 0)
        self.assertGreaterEqual(arm_pos, 0)
        self.assertLess(collect_pos, arm_pos)
        self.assertIn("not a user test", body)
        self.assertIn("printf '\\a\\a\\a'", body)
        self.assertIn('echo "READY_FOR_BRT_TEST"', body)
        self.assertIn("Canaries armed", body)

    def test_ready_backup_is_backup_only_and_alerts_tester(self):
        body = self.function_body("ready_backup")
        collect_pos = body.find("\n  collect prearm")
        arm_pos = body.find("\n  arm")

        self.assertGreaterEqual(collect_pos, 0)
        self.assertGreaterEqual(arm_pos, 0)
        self.assertLess(collect_pos, arm_pos)
        self.assertIn("not a user test", body)
        self.assertIn("test_kind=backup", body)
        self.assertIn("trace_profile=backup", body)
        self.assertIn("printf '\\a\\a\\a'", body)
        self.assertIn('echo "READY_FOR_BRT_BACKUP_TEST"', body)
        self.assertIn("exactly one BRT backup attempt", body)

    def test_prearm_collect_does_not_diagnose_failed_test(self):
        body = self.function_body("collect")
        self.assertIn('collect_mode="${1:-confirmed}"', body)
        self.assertIn('diagnosis=prearm_cleanup_not_user_test', body)
        self.assertIn('next_focus=arm_fresh_window_and_wait_for_confirmed_test', body)

    def test_arm_reports_key_probe_enablement_without_failing(self):
        body = self.function_body("arm")
        self.assertIn("key_probe_enabled=", body)
        self.assertIn("brt_component_can_backup_blueprint_", body)
        self.assertIn("brt_backup_perform_entry", body)
        self.assertIn("|| true", body)

    def test_trace_summary_counts_backup_events(self):
        body = self.function_body("print_trace_summary")
        self.assertIn("trace_backup_events=", body)
        self.assertIn("trace_backup_perform_events=", body)
        self.assertIn("trace_building_blueprint_rpc_events=", body)
        self.assertIn("trace_can_backup_blueprint_status_text_events=", body)
        self.assertIn("server_backup_path_reached", body)
        self.assertIn("server_building_blueprint_rpc_reached", body)
        self.assertIn("restore_preview_rpc_only", body)
        self.assertIn("/brt_backup_/", body)

    def test_tested_alias_collects_without_rearming(self):
        case_match = re.search(r"^case \"\$action\" in\n(?P<body>.*?)\nesac", self.source, re.M | re.S)
        self.assertIsNotNone(case_match, "missing action dispatcher")
        dispatcher = case_match.group("body")

        self.assertIsNotNone(
            re.search(r"^\s*tested\) collect confirmed ;;", dispatcher, re.M),
            "tested must collect the armed window without another arm",
        )
        self.assertIsNone(
            re.search(r"^\s*tested\).*arm", dispatcher, re.M),
            "tested must not re-arm and erase the active baseline",
        )

    def test_usage_mentions_ready_and_tested(self):
        self.assertIn("ready", self.source)
        self.assertIn("ready-backup", self.source)
        self.assertIn("tested", self.source)
        self.assertIn("usage: $0 arm|ready|ready-backup|collect|tested|snapshot|status|stop", self.source)

    def test_default_trace_skip_events_excludes_runtime_patch_sites(self):
        required = {
            "brt_action_method_failure_reason",
            "brt_action_state_empty_context",
            "brt_action_canuse_empty_context",
            "brt_action_canuse_actor_lookup_null",
            "brt_action_canuse_map_area_guard",
            "brt_action_canuse_region_fail_join",
            "brt_action_invalid_map_reason_guard",
            "brt_rpc_request_mode_branch",
            "perform_invalid_map_site_a",
            "perform_invalid_map_site_b",
            "perform_invalid_map_site_c",
            "perform_invalid_map_site_d",
        }
        match = re.search(r'^default_trace_skip_events="(?P<events>[^"]+)"', self.source, re.M)
        self.assertIsNotNone(match, "missing default runtime patch-site trace skip list")
        events = set(match.group("events").split(","))
        self.assertTrue(required.issubset(events))


if __name__ == "__main__":
    unittest.main()
