#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-method-probe-refinement.py"

spec = importlib.util.spec_from_file_location("method_probe_refinement", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class MethodProbeRefinementTests(unittest.TestCase):
    def test_excludes_known_and_reviewed_slots_then_ranks_unreviewed_methods(self):
        vtables = {
            "rows": [
                {
                    "demangled": "vtable for FLinkerLoad",
                    "executableSlots": [
                        {
                            "index": 31,
                            "value": "0x9b04600",
                            "candidateKind": "method",
                            "shape": {"hasCall": True, "callOpcodeCount": 1},
                        },
                        {
                            "index": 40,
                            "value": "0xfb50000",
                            "candidateKind": "method",
                            "shape": {"hasCall": True, "hasIndirectCall": True, "callOpcodeCount": 2},
                        },
                        {
                            "index": 41,
                            "value": "0xfb50010",
                            "candidateKind": "method",
                            "shape": {"hasCall": False, "hasIndirectCall": False},
                        },
                    ],
                },
                {
                    "demangled": "vtable for FAsyncPackage2",
                    "executableSlots": [
                        {
                            "index": 70,
                            "value": "0xfa70000",
                            "candidateKind": "method",
                            "shape": {"hasCall": True, "callOpcodeCount": 1},
                        },
                        {
                            "index": 71,
                            "value": "0xfa70010",
                            "candidateKind": "trivial",
                            "shape": {"returnsConstantZero": True},
                        },
                    ],
                },
            ]
        }
        review = {"reviewedRoutes": [{"imageOffset": "0xfa70000"}]}

        summary = module.build_refinement(vtables, review, limit=8)

        self.assertEqual(summary["selectedAddresses"], ["0xfb50000"])
        self.assertEqual(summary["candidateCount"], 1)
        reasons = {row["address"]: row["reason"] for row in summary["excludedSample"]}
        self.assertEqual(reasons["0x9b04600"], "known-non-package-function")
        self.assertEqual(reasons["0xfb50010"], "method-slot-without-call-edge")
        self.assertEqual(reasons["0xfa70000"], "reviewed-runtime-method-route")
        self.assertEqual(reasons["0xfa70010"], "not-method-slot")


if __name__ == "__main__":
    unittest.main()
