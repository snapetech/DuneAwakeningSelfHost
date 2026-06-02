#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("prove-gm-commands.py")
SPEC = importlib.util.spec_from_file_location("prove_gm_commands", SCRIPT_PATH)
prove_gm_commands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prove_gm_commands)


def command(name, tier="safe", status="cataloged", syntax=None):
    return {
        "name": name,
        "tier": tier,
        "status": status,
        "syntax": syntax or name,
        "chat": "",
        "notes": "",
    }


class GmCommandProofPolicyTests(unittest.TestCase):
    def test_only_print_commands_are_safe_route_probes(self):
        for name in ("PrintAllowedCommands", "PrintPos"):
            policy = prove_gm_commands.proof_policy(command(name))
            self.assertEqual(policy["proofStage"], "safe-route-probe")
            self.assertTrue(policy["liveEligible"])
            self.assertIn("native handler", policy["passCriteria"])

    def test_inventory_grant_requires_isolated_target(self):
        policy = prove_gm_commands.proof_policy(command("AddItemToInventory", tier="inventory"))
        self.assertEqual(policy["proofStage"], "isolated-target-mutation")
        self.assertIn("disposable test character", policy["nonDisruptiveRequirement"])
        self.assertFalse(policy["liveEligible"])
        self.assertIn("DB/log delta", policy["passCriteria"])

    def test_destroy_commands_are_lab_only(self):
        policy = prove_gm_commands.proof_policy(command("DestroyEntireBuilding", tier="destructive"))
        self.assertEqual(policy["proofStage"], "destructive-lab-only")
        self.assertEqual(policy["defaultAction"], "blocked.")
        self.assertIn("fresh DB/export snapshot", policy["fixture"])

    def test_rejected_kick_candidates_remain_static_only(self):
        policy = prove_gm_commands.proof_policy(command("KickLobbyMember", tier="player", status="rejected"))
        self.assertEqual(policy["proofStage"], "static-rejected")
        self.assertEqual(policy["defaultAction"], "do not execute.")
        self.assertEqual(policy["proofOrder"], 0)

    def test_console_commands_are_lab_only(self):
        policy = prove_gm_commands.proof_policy(command("obj", tier="console"))
        self.assertEqual(policy["proofStage"], "console-static-first")
        self.assertFalse(policy["liveEligible"])
        self.assertIn("exact command arguments", policy["fixture"])

    def test_include_binary_methods_adds_static_only_rows(self):
        class Args:
            route = "Survival_11"
            target_player = "Target"
            admin_player = "Admin"
            host = "kspld0"
            command = []
            execute_safe = False
            wait_response = 0
            mode = []
            include_binary_methods = True

        payload = prove_gm_commands.build_rows(Args())
        rows = {row["command"]: row for row in payload["commands"]}
        key = "UDuneCheatManager::CoriolisSetPartitionSeed"
        self.assertIn(key, rows)
        self.assertEqual(rows[key]["proofStage"], "binary-method-static-only")
        self.assertEqual(rows[key]["defaultAction"], "do not execute.")


if __name__ == "__main__":
    unittest.main()
