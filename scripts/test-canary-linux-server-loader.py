#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = next(
    (
        path
        for path in (
            ROOT / "scripts" / "canary-linux-server-loader.sh",
            ROOT / "examples" / "canary-linux-server-loader.sh",
        )
        if path.exists()
    ),
    ROOT / "scripts" / "canary-linux-server-loader.sh",
)
PACKAGE_SCRIPT = ROOT / "scripts" / "package-linux-server-loader.sh"


class CanaryLinuxServerLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SCRIPT.exists():
            raise unittest.SkipTest("Linux server canary wrapper is not packaged here")
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def function_body(self, name):
        match = re.search(rf"^{name}\(\) \{{\n(?P<body>.*?)\n\}}", self.source, re.M | re.S)
        self.assertIsNotNone(match, f"missing shell function: {name}")
        return match.group("body")

    def test_canary_targets_selected_partition(self):
        self.assertIn('partition_id="${DUNE_LINUX_SERVER_CANARY_PARTITION:-7}"', self.source)
        self.assertIn("set_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD true", self.source)
        self.assertIn('set_env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS "$partition_id"', self.source)
        self.assertIn('DUNE_RESTART_SERVICES="$service"', self.source)

    def test_cleanup_restores_preexisting_preload_state(self):
        self.assertIn('original_preload_enabled="$(env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD)"', self.source)
        self.assertIn('original_preload_partitions="$(env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS)"', self.source)
        self.assertIn('original_preload_path="$(env_value DUNE_LINUX_SERVER_PRELOAD)"', self.source)
        self.assertIn('original_loader_log="$(env_value DUNE_PROBE_LOADER_LOG)"', self.source)
        self.assertNotIn("set_preload_enabled false", self.source)
        cleanup = self.function_body("cleanup")
        self.assertIn('restore_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD "$original_preload_enabled"', cleanup)
        self.assertIn('restore_env_value DUNE_LINUX_SERVER_PRELOAD_PARTITIONS "$original_preload_partitions"', cleanup)
        self.assertIn('restore_env_value DUNE_LINUX_SERVER_PRELOAD "$original_preload_path"', cleanup)
        self.assertIn('restore_env_value DUNE_PROBE_LOADER_LOG "$original_loader_log"', cleanup)
        self.assertIn("restart_canary", cleanup)

    def test_can_use_staged_loader_without_rebuilding_remote_source(self):
        self.assertIn('canary_preload="${DUNE_LINUX_SERVER_CANARY_PRELOAD:-}"', self.source)
        self.assertIn('skip_build="${DUNE_LINUX_SERVER_CANARY_SKIP_BUILD:-false}"', self.source)
        self.assertIn('if [[ "$skip_build" == "true" ]]', self.source)
        self.assertIn('set_env_value DUNE_LINUX_SERVER_PRELOAD "$(container_preload_path "$canary_preload")"', self.source)
        self.assertIn('set_env_value DUNE_PROBE_LOADER_LOG "$loader_log"', self.source)

    def test_host_repo_preload_path_is_rewritten_for_container_mount(self):
        rewrite_body = self.function_body("container_preload_path")
        self.assertIn('if [[ "$path" == "$repo_root/"* ]]', rewrite_body)
        self.assertIn("'/workspace/%s\\n'", rewrite_body)
        self.assertIn('${path#"$repo_root/"}', rewrite_body)

    def test_extra_env_is_canary_scoped_and_restored(self):
        self.assertIn("DUNE_LINUX_SERVER_CANARY_EXTRA_ENV", self.source)
        apply_file_body = self.function_body("apply_extra_env_file")
        apply_body = self.function_body("apply_extra_env")
        restore_body = self.function_body("restore_extra_env")
        cleanup_body = self.function_body("cleanup")
        self.assertIn('cp -a "$path" "$backup_dir/$label"', apply_file_body)
        self.assertIn('printf \'%s=%s\\n\' "$key" "$original" >> "$extra_env_restore_file"', apply_file_body)
        self.assertIn('value="${value:1:${#value}-2}"', apply_file_body)
        self.assertIn('set_env_value "$key" "$value"', apply_file_body)
        self.assertIn('apply_extra_env_file "${DUNE_LINUX_SERVER_CANARY_EXTRA_ENV:-}" "extra.env"', apply_body)
        self.assertIn('restore_env_value "$key" "$value"', restore_body)
        self.assertIn("restore_extra_env", cleanup_body)

    def test_prepared_canary_bundle_is_canary_scoped_and_verified(self):
        self.assertIn('prep_dir="${DUNE_LINUX_SERVER_CANARY_PREP_DIR:-}"', self.source)
        self.assertIn('strict_verify="${DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY:-false}"', self.source)
        self.assertIn('printf \'%s/ue-server-anchors.env\\n\' "$prep_dir"', self.source)
        self.assertIn('printf \'%s/post-canary-verify.sh\\n\' "$prep_dir"', self.source)
        self.assertIn('printf \'%s/post-canary-verify-strict.sh\\n\' "$prep_dir"', self.source)

        validate_body = self.function_body("validate_prep_dir")
        self.assertIn('missing prepared canary dir', validate_body)
        self.assertIn('missing prepared canary anchor env', validate_body)
        self.assertIn('missing executable post-canary verifier', validate_body)

        verify_body = self.function_body("run_post_canary_verify")
        self.assertIn('"$verify_script" "$captured_log" > "$backup_dir/post-canary-verify.log" 2>&1', verify_body)
        self.assertIn('post_canary_verify_rc=%s\\n', verify_body)
        self.assertIn('ue4ss-readiness.json', verify_body)
        self.assertIn('anchor-coverage.json', verify_body)
        self.assertIn('post-canary-summary.md', verify_body)
        self.assertIn('ue4ss-port-gaps.md', verify_body)

        self.assertIn('validate_prep_dir', self.source)
        self.assertIn('apply_extra_env_file "$(prep_anchor_env_path)" "prepared-canary.env"', self.source)
        self.assertIn('run_post_canary_verify "$captured_log"', self.source)

    def test_planner_json_env_is_canary_scoped_and_validated(self):
        self.assertIn('plan_json="${DUNE_LINUX_SERVER_CANARY_PLAN_JSON:-}"', self.source)
        self.assertIn("DUNE_LINUX_SERVER_CANARY_PLAN_JSON", self.source)

        validate_body = self.function_body("validate_plan_json")
        self.assertIn('if [[ -z "$plan_json" ]]', validate_body)
        self.assertIn('missing canary plan JSON', validate_body)

        apply_body = self.function_body("apply_plan_env_json")
        self.assertIn('cp -a "$plan_json" "$backup_dir/applied-canary-plan.json"', apply_body)
        self.assertIn('extracted_env="$backup_dir/applied-canary-plan.env"', apply_body)
        self.assertIn('data.get("env", [])', apply_body)
        self.assertIn('invalid env name in plan JSON', apply_body)
        self.assertIn('invalid multiline env value in plan JSON', apply_body)
        self.assertIn('apply_extra_env_file "$extracted_env" "applied-canary-plan.env"', apply_body)

        extra_body = self.function_body("apply_extra_env")
        self.assertIn("apply_plan_env_json", extra_body)
        self.assertIn('apply_extra_env_file "${DUNE_LINUX_SERVER_CANARY_EXTRA_ENV:-}" "extra.env"', extra_body)
        self.assertLess(extra_body.index("apply_plan_env_json"), extra_body.index("DUNE_LINUX_SERVER_CANARY_EXTRA_ENV"))
        self.assertIn("validate_plan_json", self.source)
        self.assertIn('printf \'canary_plan_json=%s\\n\' "$plan_json"', self.source)

    def test_captures_readiness_sidecars_when_tooling_exists(self):
        self.assertIn('captured_log="$backup_dir/$(basename "$loader_log")"', self.source)
        self.assertIn('run_analysis "$script_dir/export-process-event-active-validation-candidates.py" --loader-log "$captured_log" --format json', self.source)
        self.assertIn('> "$backup_dir/process-event-active-validation-candidates.json"', self.source)
        self.assertIn('run_analysis "$script_dir/export-process-event-active-validation-candidates.py" --loader-log "$captured_log" --include-high-risk --format json', self.source)
        self.assertIn('> "$backup_dir/process-event-active-validation-candidates.high-risk.json"', self.source)
        self.assertIn('run_analysis "$script_dir/summarize-linux-loader-scan.py" "$captured_log"', self.source)
        self.assertIn('> "$backup_dir/loader-summary.json"', self.source)
        self.assertIn('-s "$backup_dir/loader-summary.json"', self.source)
        self.assertIn('run_analysis "$script_dir/export-process-event-active-validation-candidates.py" "$backup_dir/loader-summary.json" --format json', self.source)
        self.assertIn('> "$backup_dir/process-event-active-validation-candidates.json"', self.source)
        self.assertIn('run_analysis "$script_dir/export-process-event-active-validation-candidates.py" "$backup_dir/loader-summary.json" --format markdown', self.source)
        self.assertIn('> "$backup_dir/process-event-active-validation-candidates.md"', self.source)
        self.assertIn('run_analysis "$script_dir/summarize-ue-vtable-candidates.py" "$captured_log" --format json', self.source)
        self.assertIn('> "$backup_dir/ue-vtable-candidates.json"', self.source)
        self.assertIn('run_analysis "$script_dir/summarize-ue-vtable-candidates.py" "$captured_log" --format markdown', self.source)
        self.assertIn('> "$backup_dir/ue-vtable-candidates.md"', self.source)
        self.assertIn('run_analysis "$script_dir/ue4ss-port-readiness.py"', self.source)
        self.assertIn('> "$backup_dir/ue4ss-readiness.md"', self.source)
        self.assertIn('> "$backup_dir/ue4ss-readiness.json"', self.source)
        self.assertIn('cp -a "$prep_dir/anchor-coverage.json" "$backup_dir/anchor-coverage.json"', self.source)

    def test_captured_log_emits_evidence_inventory(self):
        inventory_body = self.function_body("write_evidence_inventory")
        self.assertIn('local inventory=("$script_dir/summarize-ue4ss-evidence-inventory.py" "$backup_dir")', inventory_body)
        self.assertIn('if [[ "$strict_verify" == "true" ]]', inventory_body)
        self.assertIn('"$post_canary_verify_rc" == "0"', inventory_body)
        self.assertIn("missing required strict evidence inventory tool", inventory_body)
        self.assertIn('inventory+=("$prep_dir")', inventory_body)
        self.assertIn('> "$backup_dir/ue4ss-evidence-inventory.md"', inventory_body)
        self.assertIn('> "$backup_dir/ue4ss-evidence-inventory.json"', inventory_body)
        self.assertIn('run_analysis "${inventory[@]}" --limit 12 --require-complete --format markdown > "$backup_dir/ue4ss-evidence-inventory.md"', inventory_body)
        self.assertIn('run_analysis "${inventory[@]}" --limit 12 --require-complete --format json > "$backup_dir/ue4ss-evidence-inventory.json"', inventory_body)
        self.assertIn('run_analysis "${inventory[@]}" --limit 12 --format markdown > "$backup_dir/ue4ss-evidence-inventory.md" || true', inventory_body)
        self.assertIn('run_analysis "${inventory[@]}" --limit 12 --format json > "$backup_dir/ue4ss-evidence-inventory.json" || true', inventory_body)
        self.assertIn("write_evidence_inventory", self.source)

    def test_captured_log_emits_reviewable_next_canary_plan(self):
        plan_body = self.function_body("write_next_canary_plan")
        self.assertIn('local captured_log="$1"', plan_body)
        self.assertIn('local hook_targets_json="$backup_dir/ue-vtable-candidates.json"', plan_body)
        self.assertIn('local active_validation_candidates_json="$backup_dir/process-event-active-validation-candidates.json"', plan_body)
        self.assertIn('"$script_dir/plan-ue4ss-canary-env.py" --platform server --server-log "$captured_log"', plan_body)
        self.assertIn('planner+=(--hook-targets-json "$hook_targets_json")', plan_body)
        self.assertIn('planner+=(--active-validation-candidates-json "$active_validation_candidates_json")', plan_body)
        self.assertIn('run_analysis "${planner[@]}" --format json > "$backup_dir/next-canary-plan.json"', plan_body)
        self.assertIn('run_analysis "${planner[@]}" --format env > "$backup_dir/next-canary-plan.env"', plan_body)
        self.assertIn('run_analysis "${planner[@]}" --format markdown > "$backup_dir/next-canary-plan.md"', plan_body)
        self.assertIn('write_next_canary_plan "$captured_log"', self.source)

    def test_capture_falls_back_to_deterministic_container_name(self):
        self.assertIn('fallback_container="dune_server-${service}-1"', self.source)
        self.assertIn('preload_container_fallback=%s\\n', self.source)
        self.assertIn('if [[ -n "$cid" ]] && "$runtime" cp "$cid:$loader_log"', self.source)

    def test_capture_delay_is_configurable_for_delayed_runtime_probe(self):
        self.assertIn('capture_delay="${DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS:-10}"', self.source)
        self.assertIn("invalid capture delay seconds", self.source)
        self.assertIn('capture_delay_seconds=%s\\n', self.source)
        self.assertIn('sleep "$capture_delay"', self.source)

    def test_analysis_timeout_keeps_cleanup_from_waiting_on_heavy_reports(self):
        self.assertIn('analysis_timeout="${DUNE_LINUX_SERVER_CANARY_ANALYSIS_TIMEOUT_SECONDS:-45}"', self.source)
        self.assertIn("invalid analysis timeout seconds", self.source)
        self.assertIn('analysis_timeout_seconds=%s\\n', self.source)
        run_analysis_body = self.function_body("run_analysis")
        self.assertIn('if [[ "$analysis_timeout" == "0" ]]', run_analysis_body)
        self.assertIn('timeout --kill-after=5s "$analysis_timeout" "$@"', run_analysis_body)

    def test_wrong_host_and_player_guards_remain(self):
        self.assertIn('required_host="${DUNE_LINUX_SERVER_CANARY_HOST:-kspls0}"', self.source)
        self.assertIn('refusing canary on host', self.source)
        self.assertIn('allow_players="${DUNE_LINUX_SERVER_CANARY_ALLOW_PLAYERS:-false}"', self.source)
        self.assertIn("refusing canary: connected_players=", self.source)
        self.assertIn("current_connected_players()", self.source)
        self.assertIn("require_zero_players()", self.source)
        self.assertIn('require_zero_players preflight', self.source)
        self.assertIn('restart_canary_if_zero_players preload | tee "$backup_dir/preload-restart.log"', self.source)
        self.assertIn('restart_canary_if_zero_players cleanup | tee "$backup_dir/cleanup-restart.log"', self.source)

    def test_live_restart_guard_rechecks_players_and_skips_cleanup_restart(self):
        require_body = self.function_body("require_zero_players")
        guarded_restart_body = self.function_body("restart_canary_if_zero_players")
        cleanup_body = self.function_body("cleanup")

        self.assertIn('value="$(current_connected_players)"', require_body)
        self.assertIn("player_guard_%s_connected_players=%s", require_body)
        self.assertIn('if [[ "$allow_players" != "true" && "$value" != "0" ]]', require_body)
        self.assertIn("refusing canary %s: connected_players=%s", require_body)
        self.assertIn('if require_zero_players "$phase"; then', guarded_restart_body)
        self.assertIn("restart_canary", guarded_restart_body)
        self.assertIn("restart_skipped_%s_due_players=true", guarded_restart_body)
        self.assertIn('restart_canary_if_zero_players cleanup >> "$backup_dir/cleanup.log" 2>&1', cleanup_body)

    def test_preflight_only_exits_before_mutating_or_restarting(self):
        self.assertIn('preflight_only="${DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY:-false}"', self.source)
        self.assertIn('if [[ "$preflight_only" == "true" ]]', self.source)
        preflight_index = self.source.index('if [[ "$preflight_only" == "true" ]]')
        prep_validate_index = self.source.index("validate_prep_dir")
        plan_validate_index = self.source.index("validate_plan_json")
        build_index = self.source.index('if [[ "$skip_build" == "true" ]]')
        preload_index = self.source.index('set_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD true')
        restart_index = self.source.index('restart_canary_if_zero_players preload | tee "$backup_dir/preload-restart.log"')
        backup_mkdir_index = self.source.index('mkdir -p "$backup_dir"')
        backup_copy_index = self.source.index('cp -a "$env_file" "$backup_dir/env.before"')
        summary_index = self.source.index('tee "$backup_dir/summary.txt"')
        self.assertLess(prep_validate_index, preflight_index)
        self.assertLess(plan_validate_index, preflight_index)
        self.assertLess(preflight_index, build_index)
        self.assertLess(preflight_index, preload_index)
        self.assertLess(preflight_index, restart_index)
        self.assertLess(preflight_index, backup_mkdir_index)
        self.assertLess(preflight_index, backup_copy_index)
        self.assertLess(preflight_index, summary_index)
        self.assertIn("printf 'preflight_ok=true\\n'", self.source)
        self.assertIn('printf \'prepared_canary_dir=%s\\n\' "$prep_dir"', self.source)
        self.assertIn('printf \'prepared_canary_anchor_env=%s\\n\' "$(prep_anchor_env_path)"', self.source)
        self.assertIn('printf \'post_canary_verify_script=%s\\n\' "$(prep_verify_script_path)"', self.source)
        self.assertNotIn('preflight_ok=true\\n\' | tee -a "$backup_dir/summary.txt"', self.source)

    def test_linux_server_package_carries_canary_workflow(self):
        if not PACKAGE_SCRIPT.exists():
            self.skipTest("package script is not packaged here")
        package_source = PACKAGE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("canary-linux-server-loader.sh", package_source)
        self.assertIn("test-canary-linux-server-loader.py", package_source)
        self.assertIn("export-ue-candidate-globals.py", package_source)
        self.assertIn("summarize-ue-candidate-outcomes.py", package_source)
        self.assertIn("test-export-ue-candidate-globals.py", package_source)
        self.assertIn("test-ue-candidate-outcomes.py", package_source)
        self.assertIn("linux-server-loader-canary-2026-06-18.md", package_source)


if __name__ == "__main__":
    unittest.main()
