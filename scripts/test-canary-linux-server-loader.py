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
        self.assertIn('post-canary-summary.md', verify_body)
        self.assertIn('ue4ss-port-gaps.md', verify_body)

        self.assertIn('validate_prep_dir', self.source)
        self.assertIn('apply_extra_env_file "$(prep_anchor_env_path)" "prepared-canary.env"', self.source)
        self.assertIn('run_post_canary_verify "$captured_log"', self.source)

    def test_captures_readiness_sidecars_when_tooling_exists(self):
        self.assertIn('captured_log="$backup_dir/$(basename "$loader_log")"', self.source)
        self.assertIn('summarize-linux-loader-scan.py" "$captured_log"', self.source)
        self.assertIn('ue4ss-port-readiness.py"', self.source)
        self.assertIn('> "$backup_dir/ue4ss-readiness.md"', self.source)
        self.assertIn('> "$backup_dir/ue4ss-readiness.json"', self.source)

    def test_capture_falls_back_to_deterministic_container_name(self):
        self.assertIn('fallback_container="dune_server-${service}-1"', self.source)
        self.assertIn('preload_container_fallback=%s\\n', self.source)
        self.assertIn('if [[ -n "$cid" ]] && "$runtime" cp "$cid:$loader_log"', self.source)

    def test_capture_delay_is_configurable_for_delayed_runtime_probe(self):
        self.assertIn('capture_delay="${DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS:-10}"', self.source)
        self.assertIn("invalid capture delay seconds", self.source)
        self.assertIn('capture_delay_seconds=%s\\n', self.source)
        self.assertIn('sleep "$capture_delay"', self.source)

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
        build_index = self.source.index('if [[ "$skip_build" == "true" ]]')
        preload_index = self.source.index('set_env_value DUNE_ENABLE_LINUX_SERVER_PRELOAD true')
        restart_index = self.source.index('restart_canary_if_zero_players preload | tee "$backup_dir/preload-restart.log"')
        backup_mkdir_index = self.source.index('mkdir -p "$backup_dir"')
        backup_copy_index = self.source.index('cp -a "$env_file" "$backup_dir/env.before"')
        summary_index = self.source.index('tee "$backup_dir/summary.txt"')
        self.assertLess(prep_validate_index, preflight_index)
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
