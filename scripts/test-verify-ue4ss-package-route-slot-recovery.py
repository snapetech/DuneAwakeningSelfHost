#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-ue4ss-package-route-slot-recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location("route_slot_recovery_verifier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def next_action():
    return {
        "schemaVersion": "dune-ue4ss-package-next-action/v1",
        "action": "recover-package-anchor",
        "liveTraceRunbook": {
            "routeSlotTraceRequirement": {
                "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                "routeAddress": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "requiredSlots": ["0x3a0", "0x3d8"],
                "requiredRegisters": ["rbx", "r14"],
            }
        },
        "routeSlotRecovery": {
            "requiredRouteTrace": {
                "address": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "slots": ["0x3a0", "0x3d8"],
                "registers": ["rbx", "r14"],
            }
        },
    }


def evidence(matches=None):
    return {
        "schemaVersion": "dune-ue4ss-package-runtime-trace-evidence/v1",
        "routeHits": [
            {
                "imageOffset": "0x129d58a2",
                "address": "0x55945c6058a2",
                "rip": "0x55945c6058a2",
                "callerImageOffset": "0xa056aa2",
                "routeVtableStaticSlotMatches": matches or [],
            }
        ],
    }


class RouteSlotRecoveryVerifierTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_ready_when_required_slots_and_registers_are_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            next_action_path = root / "next-action.json"
            write_json(
                evidence_path,
                evidence(
                    [
                        {
                            "register": "rbx",
                            "slotOffset": "0x3a0",
                            "targetImageOffset": "0x128993c0",
                        },
                        {
                            "register": "r14",
                            "slotOffset": "0x3d8",
                            "targetImageOffset": "0x128d5880",
                        },
                    ]
                ),
            )
            write_json(next_action_path, next_action())
            report = self.module.report(evidence_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["matchCount"], 1)
        self.assertEqual(report["matches"][0]["presentSlots"], ["0x3a0", "0x3d8"])
        self.assertIn("targets=`0x128993c0, 0x128d5880`", rendered)

    def test_missing_route_hit_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            next_action_path = root / "next-action.json"
            payload = evidence([])
            payload["routeHits"][0]["imageOffset"] = "0xa056aa2"
            write_json(evidence_path, payload)
            write_json(next_action_path, next_action())
            report = self.module.report(evidence_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertIn("no route hit found for 0x129d58a2", report["blockers"])
        self.assertEqual(report["nextTraceRequirement"]["routeAddress"], "0x129d58a2")
        self.assertEqual(report["nextTraceRequirement"]["missingSlots"], ["0x3a0", "0x3d8"])
        self.assertEqual(report["nextTraceRequirement"]["missingRegisters"], ["rbx", "r14"])
        self.assertIn("marker=`UE4SS_PACKAGE_ROUTE_TRACE_HIT`", rendered)

    def test_partial_slot_capture_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            next_action_path = root / "next-action.json"
            write_json(
                evidence_path,
                evidence(
                    [
                        {
                            "register": "rbx",
                            "slotOffset": "0x3a0",
                            "targetImageOffset": "0x128993c0",
                        }
                    ]
                ),
            )
            write_json(next_action_path, next_action())
            report = self.module.report(evidence_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertIn("route hits did not contain all required static vtable slot matches", report["blockers"])
        self.assertEqual(report["matches"][0]["missingSlots"], ["0x3d8"])
        self.assertEqual(report["matches"][0]["missingRegisters"], ["r14"])
        self.assertEqual(report["nextTraceRequirement"]["missingSlots"], ["0x3d8"])
        self.assertEqual(report["nextTraceRequirement"]["missingRegisters"], ["r14"])
        self.assertIn("missingSlots=`0x3d8`", rendered)

    def test_route_address_can_match_caller_route_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            next_action_path = root / "next-action.json"
            payload = evidence(
                [
                    {
                        "register": "rbx",
                        "slotOffset": "0x3a0",
                        "targetImageOffset": "0x128993c0",
                    }
                ]
            )
            payload["routeHits"][0]["imageOffset"] = "0xa056aa2"
            payload["routeHits"][0]["callerImageOffset"] = "0x129d58a2"
            write_json(evidence_path, payload)
            write_json(next_action_path, next_action())
            report = self.module.report(evidence_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertEqual(report["matchCount"], 1)
        self.assertEqual(report["matches"][0]["matchedField"], "callerImageOffset")
        self.assertEqual(report["matches"][0]["missingSlots"], ["0x3d8"])
        self.assertNotIn("no route hit found for 0x129d58a2", report["blockers"])
        self.assertIn("matchedField=`callerImageOffset`", rendered)

    def test_missing_route_slot_recovery_in_next_action_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            next_action_path = root / "next-action.json"
            write_json(evidence_path, evidence([]))
            write_json(next_action_path, {"schemaVersion": "dune-ue4ss-package-next-action/v1"})
            report = self.module.report(evidence_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn("next-action routeSlotRecovery is missing", report["blockers"])

    def test_live_runbook_route_slot_requirement_must_match_required_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            next_action_path = root / "next-action.json"
            action = next_action()
            action["liveTraceRunbook"]["routeSlotTraceRequirement"]["requiredSlots"] = ["0x3a0"]
            write_json(evidence_path, evidence([]))
            write_json(next_action_path, action)
            report = self.module.report(evidence_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "next-action liveTraceRunbook.routeSlotTraceRequirement requiredSlots do not match required route trace",
            report["blockers"],
        )


if __name__ == "__main__":
    unittest.main()
