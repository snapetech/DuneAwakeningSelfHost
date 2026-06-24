#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "restart-target.sh"


class RestartTargetSeedTimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def function_body(self, name):
        match = re.search(rf"^{name}\(\) \{{\n(?P<body>.*?)\n\}}", self.source, re.M | re.S)
        self.assertIsNotNone(match, f"missing shell function: {name}")
        return match.group("body")

    def test_seed_gateway_neighbors_is_bounded(self):
        body = self.function_body("seed_gateway_neighbors")

        self.assertIn('seed_timeout="${DUNE_SEED_NEIGHBOR_TIMEOUT_SECONDS:-90}"', body)
        self.assertIn('command -v timeout', body)
        self.assertIn('timeout --kill-after=5s "${seed_timeout}s" ./scripts/seed-gateway-neighbor.sh || true', body)

    def test_restart_paths_use_bounded_seed_helper(self):
        direct_calls = [
            line
            for line in self.source.splitlines()
            if "./scripts/seed-gateway-neighbor.sh" in line and "timeout" not in line and "[ ! -x" not in line
        ]

        self.assertEqual(direct_calls, ['    ./scripts/seed-gateway-neighbor.sh || true'])
        self.assertGreaterEqual(self.source.count("seed_gateway_neighbors"), 5)


if __name__ == "__main__":
    unittest.main()
