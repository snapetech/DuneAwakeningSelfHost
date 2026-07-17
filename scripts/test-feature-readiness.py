#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("feature_readiness", ROOT / "admin" / "feature_readiness.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def feature(feature_id="alpha", **updates):
    value = {
        "id": feature_id,
        "title": "Alpha feature",
        "group": "Test",
        "description": "A bounded fixture feature.",
        "documentation": "docs/admin-panel.md",
        "primaryGate": "DUNE_ALPHA_ENABLED",
        "gates": ["DUNE_ALPHA_ENABLED"],
        "credentials": [],
        "files": [],
        "services": [],
        "probe": "",
        "dependencies": [],
        "canary": "runtime-proven",
        "remediation": {"surface": "settings", "summary": "Enable the fixture."},
    }
    value.update(updates)
    return value


class FeatureReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def catalog(self, *features):
        path = self.root / "catalog.json"
        path.write_text(json.dumps({"schemaVersion": 1, "features": list(features)}), encoding="utf-8")
        return MODULE.load_catalog(path)

    def test_ready_feature_requires_every_evidence_class(self):
        artifact = self.root / "config" / "ready.json"
        artifact.parent.mkdir()
        artifact.write_text("{}\n", encoding="utf-8")
        catalog = self.catalog(feature(
            gates=["DUNE_ALPHA_ENABLED", "DUNE_ALPHA_WRITE_ENABLED"],
            credentials=["DUNE_ALPHA_TOKEN"],
            files=[{"path": "config/ready.json", "minimumBytes": 2}],
            services=["alpha-worker"], probe="alpha-runtime",
        ))
        result = MODULE.evaluate(
            catalog,
            {"DUNE_ALPHA_ENABLED": "true", "DUNE_ALPHA_WRITE_ENABLED": "yes", "DUNE_ALPHA_TOKEN": "private-value"},
            root=self.root,
            services=[{"service": "alpha-worker", "state": "running"}],
            probes={"alpha-runtime": {"ready": True, "state": "ready", "detail": "fixture"}},
            generated_at="2026-01-01T00:00:00Z",
        )
        self.assertTrue(result["ok"])
        self.assertEqual("ready", result["features"][0]["state"])
        self.assertNotIn("private-value", json.dumps(result))
        self.assertEqual([{"key": "DUNE_ALPHA_TOKEN", "configured": True}], result["features"][0]["credentialChecks"])

    def test_disabled_partial_blocked_degraded_external_and_canary_states(self):
        features = [
            feature("disabled"),
            feature("partial", gates=["DUNE_ALPHA_ENABLED", "DUNE_ALPHA_WRITE_ENABLED"]),
            feature("blocked", files=[{"path": "missing", "minimumBytes": 1}]),
            feature("degraded", services=["missing-worker"]),
            feature("external", credentials=["DUNE_EXTERNAL_TOKEN"], canary="external-credential-pending"),
            feature("canary", canary="operator-canary-pending"),
        ]
        for row in features:
            row["primaryGate"] = "DUNE_ALPHA_ENABLED"
        catalog = self.catalog(*features)
        disabled = MODULE.evaluate(catalog, {}, root=self.root)
        self.assertEqual({"disabled"}, {row["state"] for row in disabled["features"]})
        active = MODULE.evaluate(catalog, {"DUNE_ALPHA_ENABLED": "true"}, root=self.root)
        states = {row["id"]: row["state"] for row in active["features"]}
        self.assertEqual("partial", states["partial"])
        self.assertEqual("blocked", states["blocked"])
        self.assertEqual("degraded", states["degraded"])
        self.assertEqual("external-blocked", states["external"])
        self.assertEqual("canary-pending", states["canary"])

    def test_external_probe_configuration_gap_is_external_blocked(self):
        catalog = self.catalog(feature("webhook", canary="external-credential-pending", probe="webhook"))
        result = MODULE.evaluate(
            catalog, {"DUNE_ALPHA_ENABLED": "true"}, root=self.root,
            probes={"webhook": {"ready": False, "state": "destination-missing", "detail": "reviewed endpoints=0"}},
        )
        self.assertEqual("external-blocked", result["features"][0]["state"])

    def test_dependency_failure_blocks_otherwise_ready_feature(self):
        catalog = self.catalog(
            feature("parent"),
            feature("child", dependencies=["parent"], gates=["DUNE_CHILD_ENABLED"], primaryGate="DUNE_CHILD_ENABLED"),
        )
        result = MODULE.evaluate(catalog, {"DUNE_CHILD_ENABLED": "true"}, root=self.root)
        rows = {row["id"]: row for row in result["features"]}
        self.assertEqual("disabled", rows["parent"]["state"])
        self.assertEqual("blocked", rows["child"]["state"])
        self.assertEqual([{"id": "parent", "state": "disabled", "ready": False}], rows["child"]["dependencyChecks"])

    def test_catalog_rejects_escape_unknown_fields_and_bad_dependencies(self):
        invalid = [
            feature(files=[{"path": "../secret", "minimumBytes": 1}]),
            {**feature(), "surprise": True},
            feature(dependencies=["missing"]),
        ]
        for index, row in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.catalog(row)

    def test_catalog_rejects_dependency_cycles(self):
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            self.catalog(
                feature("alpha", dependencies=["beta"]),
                feature("beta", dependencies=["alpha"], gates=["DUNE_BETA_ENABLED"], primaryGate="DUNE_BETA_ENABLED"),
            )

    def test_prometheus_is_label_free_and_reports_every_state(self):
        status = {"ok": False, "summary": {"total": 7, "active": 6, "activeProblems": 4, **{state: 1 for state in MODULE.STATES}}}
        metrics = MODULE.prometheus(status)
        self.assertIn("dash_feature_readiness_ok 0", metrics)
        self.assertIn("dash_feature_readiness_external_blocked 1", metrics)
        self.assertNotIn("{", metrics)

    def test_repository_catalog_is_valid_and_covers_parity_activator(self):
        catalog = MODULE.load_catalog(ROOT / "config" / "feature-readiness.json")
        for row in catalog["features"]:
            self.assertTrue((ROOT / row["documentation"]).is_file(), row["documentation"])
        activator = (ROOT / "scripts" / "enable-feature-parity.sh").read_text(encoding="utf-8")
        body = activator.split("keys=(", 1)[1].split("\n)", 1)[0]
        activated = set(re.findall(r"\bDUNE_[A-Z0-9_]+\b", body))
        cataloged = {gate for row in catalog["features"] for gate in row["gates"]}
        self.assertEqual(set(), activated - cataloged)


if __name__ == "__main__":
    unittest.main()
