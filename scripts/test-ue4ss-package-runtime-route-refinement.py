#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-runtime-route-refinement.py"

spec = importlib.util.spec_from_file_location("runtime_route_refinement", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageRuntimeRouteRefinementTests(unittest.TestCase):
    def write_evidence(self, data):
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        json.dump(data, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def evidence(self):
        return {
            "schemaVersion": "dune-ue4ss-package-runtime-trace-evidence/v1",
            "sourceLog": "/tmp/trace.log",
            "sourceLogSha256": "a" * 64,
            "hitCount": 0,
            "methodHitCount": 3,
            "routeHitCount": 4,
            "methodHits": [
                {"ripImageOffset": "0x9b04600", "callerImageOffset": "0xf94711c"},
                {"ripImageOffset": "0x9b04600", "callerImageOffset": "0xf94711c"},
                {"ripImageOffset": "0x9b04610", "callerImageOffset": "0xf9492bc"},
            ],
            "routeHits": [
                {
                    "ripImageOffset": "0xf94711c",
                    "callerImageOffset": "0x1299f5fa",
                    "rip": "0x55945957711c",
                    "caller": {"ip": "0x55945c5cf5fa"},
                    "backtrace": [{"index": 0, "ip": "0x55945957711c"}],
                    "disassembly": ["call *0x10(%rax)"],
                    "stack": ["0x1"],
                },
                {
                    "ripImageOffset": "0xf94711c",
                    "callerImageOffset": "0x1299f5fa",
                    "rip": "0x55945957711c",
                    "caller": {"ip": "0x55945c5cf5fa"},
                },
                {
                    "ripImageOffset": "0xf94711c",
                    "callerImageOffset": "0x12659bb6",
                    "rip": "0x55945957711c",
                    "caller": {"ip": "0x55945c289bb6"},
                },
                {
                    "ripImageOffset": "0xf9492bc",
                    "callerImageOffset": "0x12659bb6",
                    "rip": "0x5594595792bc",
                    "caller": {"ip": "0x55945c289bb6"},
                },
            ],
        }

    def test_summarize_ranks_route_callers_by_hits_and_sources(self):
        path = self.write_evidence(self.evidence())

        summary = module.summarize(path, limit=2)

        self.assertEqual(summary["routeHitCount"], 4)
        self.assertEqual(summary["candidateCount"], 2)
        self.assertEqual(summary["selectedCount"], 2)
        self.assertEqual(summary["selectedAddresses"], ["0x12659bb6", "0x1299f5fa"])
        self.assertEqual(summary["recommendedRouteAddressEnv"], "0x12659bb6,0x1299f5fa")
        self.assertEqual(summary["selectedRoutes"][0]["routeSourceCount"], 2)
        self.assertEqual(summary["hotRouteOffsets"][0]["address"], "0xf94711c")
        self.assertIn("--route-address", summary["nextStep"])

    def test_markdown_contains_selected_route_env(self):
        path = self.write_evidence(self.evidence())
        summary = module.summarize(path, limit=1)

        text = module.markdown(summary)

        self.assertIn("UE4SS Package Runtime Route Refinement", text)
        self.assertIn("Recommended route env", text)
        self.assertIn("0x12659bb6", text)

    def test_rejects_wrong_schema(self):
        path = self.write_evidence({"schemaVersion": "wrong"})

        with self.assertRaises(ValueError):
            module.summarize(path)


if __name__ == "__main__":
    unittest.main()
