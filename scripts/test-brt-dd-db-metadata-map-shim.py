#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "brt-dd-db-metadata-map-shim.sh"


class BrtDdDbMetadataMapShimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def function_body(self, name: str) -> str:
        match = re.search(rf"^{name}\(\) \{{\n(?P<body>.*?)\n\}}", self.source, re.M | re.S)
        self.assertIsNotNone(match, f"missing shell function: {name}")
        return match.group("body")

    def sql_function_body(self, name: str) -> str:
        match = re.search(
            rf"CREATE OR REPLACE FUNCTION dune\.{name}\([^)]*\).*?AS \$function\$\n(?P<body>.*?)\n\$function\$;",
            self.source,
            re.S,
        )
        self.assertIsNotNone(match, f"missing SQL function: {name}")
        return match.group("body")

    def test_auto_backup_has_source_player_and_one_shot_gates(self):
        body = self.sql_function_body("brt_dd_try_auto_backup")

        self.assertIn("auto_backup_source_events", body)
        self.assertIn("regexp_split_to_table(source_events", body)
        self.assertIn("allowed.value IN ('*', in_source_event)", body)
        self.assertIn("auto_backup_player_allowlist", body)
        self.assertIn("allowed.value::bigint = in_player_id", body)
        self.assertIn("auto_backup_one_shot", body)
        self.assertIn("auto_backup_one_shot_disabled", body)
        self.assertIn("WHERE key = 'auto_backup_on_brt_call'", body)

    def test_auto_backup_can_fall_back_to_backup_linked_dd_totem(self):
        body = self.sql_function_body("brt_dd_try_auto_backup")

        self.assertIn("base_backup_find_totems_from_player_owner", body)
        self.assertIn("JOIN base_backup_linked_actors bbla ON bbla.id = bb.id", body)
        self.assertIn("JOIN totems t ON t.id = bbla.actor_id", body)
        self.assertIn("WHERE bb.player_id = in_player_id", body)
        self.assertIn("ORDER BY candidate.priority, distance_xy", body)

    def test_auto_backup_cleans_stale_actor_state_inside_save_attempt(self):
        body = self.sql_function_body("brt_dd_try_auto_backup")

        self.assertIn("selected_totem_entity_id", body)
        self.assertIn("stale_actor_state_deleted", body)
        self.assertIn("DELETE FROM actor_state", body)
        self.assertIn("s.state = 'BaseBackup'::ActorState", body)
        self.assertIn("created_backup_id := base_backup_save_from_totem", body)
        self.assertIn("Deep Desert BRT Backup #", body)
        self.assertIn("'stale_actor_state_deleted', stale_actor_state_deleted", body)

    def test_available_backups_returns_newest_first(self):
        body = self.sql_function_body("base_backup_get_available_backups")

        self.assertIn("ORDER BY bb.id DESC", body)

    def test_available_backups_can_hide_existing_rows_for_backup_only_canary(self):
        body = self.sql_function_body("base_backup_get_available_backups")

        self.assertIn("available_backups_mode", body)
        self.assertIn("available_backups_player_allowlist", body)
        self.assertIn("available_mode = 'backup-only-empty'", body)
        self.assertIn("hide_existing_backups", body)
        self.assertIn("get_available_backups_hidden_for_backup_only", body)
        self.assertIn("RETURN;", body)

    def test_hidden_available_backups_still_runs_brt_triggered_auto_backup_first(self):
        body = self.sql_function_body("base_backup_get_available_backups")
        hidden_pos = body.find("IF hide_existing_backups THEN")
        auto_pos = body.find("PERFORM brt_dd_try_auto_backup(in_player_id, 'get_available_backups_hidden', NULL);", hidden_pos)
        log_pos = body.find("'get_available_backups_hidden_for_backup_only'", hidden_pos)
        return_pos = body.find("RETURN;", hidden_pos)

        self.assertGreaterEqual(hidden_pos, 0)
        self.assertGreaterEqual(auto_pos, 0)
        self.assertGreaterEqual(log_pos, 0)
        self.assertGreaterEqual(return_pos, 0)
        self.assertLess(auto_pos, log_pos)
        self.assertLess(auto_pos, return_pos)

    def test_get_data_can_deny_cached_restore_selection_for_backup_only_canary(self):
        body = self.sql_function_body("base_backup_get_data")

        self.assertIn("hidden_backup_data_mode", body)
        self.assertIn("deny_cached_backup_data", body)
        self.assertIn("available_mode = 'backup-only-empty'", body)
        self.assertIn("hidden_data_mode = 'return-null'", body)
        self.assertIn("get_data_hidden_for_backup_only", body)
        self.assertIn("RETURN NULL::GetBaseBackupData", body)

    def test_get_data_denial_still_runs_brt_triggered_auto_backup_first(self):
        body = self.sql_function_body("base_backup_get_data")
        denial_pos = body.find("IF deny_cached_backup_data THEN")
        auto_pos = body.find("PERFORM brt_dd_try_auto_backup(backup_player_id, 'get_data', in_base_backup_id);", denial_pos)
        log_pos = body.find("'get_data_hidden_for_backup_only'", denial_pos)
        return_pos = body.find("RETURN NULL::GetBaseBackupData", denial_pos)

        self.assertGreaterEqual(denial_pos, 0)
        self.assertGreaterEqual(auto_pos, 0)
        self.assertGreaterEqual(log_pos, 0)
        self.assertGreaterEqual(return_pos, 0)
        self.assertLess(auto_pos, log_pos)
        self.assertLess(auto_pos, return_pos)

    def test_default_auto_backup_settings_are_safe_for_canary(self):
        self.assertIn("('auto_backup_on_brt_call', 'false')", self.source)
        self.assertIn("('auto_backup_source_events', 'get_data')", self.source)
        self.assertIn("('auto_backup_player_allowlist', '')", self.source)
        self.assertIn("('auto_backup_one_shot', 'false')", self.source)
        self.assertIn("('available_backups_mode', 'normal')", self.source)
        self.assertIn("('available_backups_player_allowlist', '')", self.source)
        self.assertIn("('hidden_backup_data_mode', 'serve')", self.source)

    def test_canary_command_scopes_auto_backup_to_one_player_and_get_data(self):
        body = self.function_body("set_auto_backup_canary")

        self.assertIn("('auto_backup_on_brt_call', :'mode')", body)
        self.assertIn("('auto_backup_source_events', 'get_data,get_available_backups_hidden')", body)
        self.assertIn("('auto_backup_player_allowlist', :'player_id')", body)
        self.assertIn("('auto_backup_one_shot', 'true')", body)
        self.assertIn("('auto_backup_cooldown_seconds', '15')", body)
        self.assertIn("('auto_backup_radius', '50000')", body)

    def test_dispatcher_exposes_canary_command(self):
        self.assertIn("set-auto-backup-canary) set_auto_backup_canary", self.source)
        self.assertIn("set-auto-backup-canary", self.source)
        self.assertIn("set-available-backups-mode) set_available_backups_mode", self.source)
        self.assertIn("set-available-backups-mode", self.source)

    def test_available_backups_mode_command_controls_cached_data_denial(self):
        body = self.function_body("set_available_backups_mode")

        self.assertIn("hidden_data_mode", body)
        self.assertIn("serve|return-null", body)
        self.assertIn("('hidden_backup_data_mode', :'hidden_data_mode')", body)


if __name__ == "__main__":
    unittest.main()
