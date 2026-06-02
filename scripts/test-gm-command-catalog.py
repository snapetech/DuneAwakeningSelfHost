#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("gm-command-catalog.py")
SPEC = importlib.util.spec_from_file_location("gm_command_catalog", SCRIPT_PATH)
gm_command_catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gm_command_catalog)


class GmCommandCatalogTests(unittest.TestCase):
    def test_binary_method_inventory_has_full_extractor_count(self):
        data = gm_command_catalog.catalog()
        self.assertEqual(len(data["binaryMethods"]), 100)
        qualified = {method["qualifiedName"] for method in data["binaryMethods"]}
        self.assertIn("UDuneCheatManager::AddItemToInventory", qualified)
        self.assertIn("UDuneCheatManager::CoriolisSetPartitionSeed", qualified)
        self.assertIn("UCharacterTransferCheatManager::CharacterTransfer_FullFlow", qualified)
        self.assertIn("UOvermapCheatManager::OvermapTravelToDimension", qualified)

    def test_binary_methods_are_classified_separately_from_operational_commands(self):
        data = gm_command_catalog.catalog()
        by_name = {method["qualifiedName"]: method for method in data["binaryMethods"]}
        self.assertEqual(by_name["UDuneCheatManager::AddItemToInventory"]["status"], "allow-listed")
        self.assertEqual(by_name["UDuneCheatManager::CoriolisSetPartitionSeed"]["status"], "binary-only-unverified")
        self.assertEqual(by_name["UOvermapCheatManager::OvermapTravelToDimension"]["status"], "format-evidence-only")

    def test_markdown_includes_binary_inventory_section(self):
        rendered = gm_command_catalog.markdown(gm_command_catalog.catalog())
        self.assertIn("Full Binary Cheat-Manager Methods", rendered)
        self.assertIn("Recovered method count: 100", rendered)
        self.assertIn("UDuneS2sCheatManager::EncountersSetEnabled", rendered)


if __name__ == "__main__":
    unittest.main()
