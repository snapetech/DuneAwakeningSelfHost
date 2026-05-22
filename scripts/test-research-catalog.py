#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("research_catalog", ROOT / "scripts" / "research_catalog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResearchCatalogTest(unittest.TestCase):
    def setUp(self):
        self.catalog = load_module()

    def test_repo_catalog_validates(self):
        data = self.catalog.load_catalog()
        self.assertEqual([], self.catalog.validate_catalog(data))
        ids = {entry["id"] for entry in data["entries"]}
        self.assertIn("spice-field-caps-deepdesert", ids)
        self.assertIn("native-gm-command-envelope", ids)

    def test_markdown_renderer_contains_status_table(self):
        rendered = self.catalog.render_markdown(self.catalog.load_catalog())
        self.assertIn("Reverse Engineering Surface Catalog", rendered)
        self.assertIn("sandstorm-coriolis-autospawn", rendered)
        self.assertIn("| ID | Kind | Scope | Status | Confidence | Risk | Restart |", rendered)

    def test_promotion_rules_block_high_risk_without_gate(self):
        data = self.catalog.load_catalog()
        entry = next(item for item in data["entries"] if item["id"] == "mapfeatures-deepdesert-shifting-sands")
        blockers = self.catalog.promotion_blockers(entry, "admin-safe")
        self.assertIn("high-risk admin-safe surfaces need an explicit adminGate", blockers)
        entry = {**entry, "adminGate": "MOVE OFFLINE PLAYER"}
        self.assertNotIn("high-risk admin-safe surfaces need an explicit adminGate", self.catalog.promotion_blockers(entry, "admin-safe"))

    def test_validation_rejects_bad_status(self):
        bad = {
            "schemaVersion": 1,
            "evidenceLevels": self.catalog.STATUS_ORDER,
            "entries": [{
                "id": "bad",
                "name": "Bad",
                "kind": "config",
                "scope": "global",
                "status": "maybe",
                "confidence": "high",
                "risk": "low",
                "restartRequired": False,
                "surface": {"key": "x"},
                "evidence": ["x"],
                "validationProcedure": "x",
                "rollbackProcedure": "x",
            }],
        }
        self.assertTrue(any("invalid status" in error for error in self.catalog.validate_catalog(bad)))

    def test_cli_validate_output_shape(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump(self.catalog.load_catalog(), handle)
            path = pathlib.Path(handle.name)
        try:
            loaded = self.catalog.load_catalog(path)
            self.assertGreater(len(loaded["entries"]), 0)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
