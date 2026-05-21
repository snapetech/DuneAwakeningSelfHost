#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("admin-chat-commands.py")
SPEC = importlib.util.spec_from_file_location("admin_chat_commands", SCRIPT_PATH)
admin_chat_commands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admin_chat_commands)


class AuctionCommandParserTests(unittest.TestCase):
    def parse(self, argv):
        return admin_chat_commands.parse_auction_command_args(argv)

    def test_name_listing_defaults_to_personal_inventory(self):
        self.assertEqual(
            self.parse(["PowerPack", "1", "456"]),
            ("personal", None, None, "PowerPack", 1, 456),
        )

    def test_quoted_name_can_contain_spaces(self):
        self.assertEqual(
            self.parse(["power pack", "2", "456"]),
            ("personal", None, None, "power pack", 2, 456),
        )

    def test_base_storage_source(self):
        self.assertEqual(
            self.parse(["--base", "PowerPack", "1", "456"]),
            ("base", None, None, "PowerPack", 1, 456),
        )

    def test_explicit_inventory_source(self):
        self.assertEqual(
            self.parse(["--inventory", "413", "PowerPack", "1", "456"]),
            ("inventory", 413, None, "PowerPack", 1, 456),
        )

    def test_item_id_source(self):
        self.assertEqual(
            self.parse(["--item-id", "33256803", "1", "456"]),
            ("personal", None, 33256803, "item-id:33256803", 1, 456),
        )

    def test_item_id_can_be_combined_with_explicit_inventory(self):
        self.assertEqual(
            self.parse(["--inventory", "413", "--item-id", "33256594", "1", "456"]),
            ("inventory", 413, 33256594, "item-id:33256594", 1, 456),
        )

    def test_item_id_rejects_extra_name(self):
        with self.assertRaisesRegex(ValueError, "do not provide an item name"):
            self.parse(["--item-id", "33256803", "PowerPack", "1", "456"])

    def test_count_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, "count must be a positive integer"):
            self.parse(["PowerPack", "zero", "456"])

    def test_price_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, "price must be a positive integer"):
            self.parse(["PowerPack", "1", "0"])


if __name__ == "__main__":
    unittest.main()
