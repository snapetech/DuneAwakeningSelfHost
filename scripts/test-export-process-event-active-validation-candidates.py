import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-process-event-active-validation-candidates.py"


def load_module():
    spec = importlib.util.spec_from_file_location("export_process_event_active_validation_candidates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExportProcessEventActiveValidationCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_summary(self, payload):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "summary.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.addCleanup(tmp.cleanup)
        return path

    def write_log(self, text):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "loader.log"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(tmp.cleanup)
        return path

    def test_exports_reviewable_cdo_runtime_function_candidate(self):
        path = self.write_summary(
            {
                "ueObjectNativeIdentities": [
                    {
                        "event": "ue-object-native-identity",
                        "status": "promoted",
                        "name": "Default__Actor",
                        "object": "0x1000",
                        "className": "Actor",
                    }
                ],
                "luaObjectRegistry": [
                    {
                        "event": "lua-object-registry",
                        "status": "added",
                        "address": "0x1000",
                        "path": "/RuntimeProbe/Default__Actor",
                    }
                ],
                "ueFunctionNativeIdentities": [
                    {
                        "event": "ue-function-native-identity",
                        "status": "promoted",
                        "name": "Actor",
                        "function": "0x2000",
                        "functionName": "WasRecentlyRendered",
                        "functionPath": "/Script/Actor.WasRecentlyRendered:Function",
                        "functionRuntimePath": "/RuntimeProbe/Actor.WasRecentlyRendered:Function",
                    }
                ],
                "ueFunctionParams": [
                    {
                        "event": "ue-function-param",
                        "status": "candidate",
                        "function": "0x2000",
                        "descriptorSane": "true",
                    }
                ],
            }
        )

        report = self.module.summarize(path)

        self.assertEqual(report["candidateCount"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["objectAddress"], "0x1000")
        self.assertEqual(candidate["functionAddress"], "0x2000")
        self.assertEqual(candidate["functionPath"], "/RuntimeProbe/Actor.WasRecentlyRendered:Function")
        self.assertEqual(candidate["callFunctionCommand"], "WasRecentlyRendered")
        self.assertEqual(candidate["risk"], "moderate")
        self.assertEqual(candidate["score"], 145)
        self.assertTrue(candidate["reviewRequired"])
        self.assertFalse(candidate["nativeCallAllowed"])
        self.assertIn("query-like-function-name", candidate["reasons"])
        self.assertEqual(report["activeValidationCandidates"][0]["objectAddress"], "0x1000")

    def test_excludes_high_risk_execute_ubergraph_by_default(self):
        path = self.write_summary(
            {
                "ueObjectNativeIdentities": [
                    {
                        "status": "promoted",
                        "name": "Default__Object",
                        "object": "0x1000",
                        "className": "Object",
                    }
                ],
                "ueFunctionNativeIdentities": [
                    {
                        "status": "promoted",
                        "name": "Object",
                        "function": "0x2000",
                        "functionName": "ExecuteUbergraph",
                        "functionPath": "/Script/Object.ExecuteUbergraph:Function",
                        "functionRuntimePath": "/RuntimeProbe/Object.ExecuteUbergraph:Function",
                    }
                ],
                "ueFunctionParams": [
                    {
                        "status": "candidate",
                        "function": "0x2000",
                        "descriptorSane": "true",
                    }
                ],
            }
        )

        self.assertEqual(self.module.summarize(path)["candidateCount"], 0)

        report = self.module.summarize(path, include_high_risk=True)
        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["candidates"][0]["risk"], "high")
        self.assertIn("execute-ubergraph", report["candidates"][0]["reasons"])

    def test_streams_raw_loader_log_and_marks_class_object_candidates_high_risk(self):
        path = self.write_log(
            "\n".join(
                [
                    "2026-06-20T22:18:33+0000 pid=1 loader=server event=ue-object-array-class-reflection name=Actor index=3 status=scanning object=0x1000 className=Class count=2 max=2048",
                    "2026-06-20T22:18:33+0000 pid=1 loader=server event=ue-function-native-identity source=ue-function-link status=promoted name=Actor functionIndex=0 chain=objectArray function=0x2000 functionName=WasRecentlyRendered functionPath=/Script/Actor.WasRecentlyRendered:Function functionRuntimePath=/RuntimeProbe/Actor.WasRecentlyRendered:Function root=0x0 functionFlags=0x6438e00 functionFlagsReadable=true",
                    "2026-06-20T22:18:33+0000 pid=1 loader=server event=ue-function-param name=Actor functionIndex=0 chain=paramScan0x58 index=0 status=candidate function=0x2000 functionName=WasRecentlyRendered functionPath=/Script/Actor.WasRecentlyRendered:Function functionRuntimePath=/RuntimeProbe/Actor.WasRecentlyRendered:Function descriptorSane=true",
                ]
            )
        )

        self.assertEqual(self.module.summarize_log(path)["candidateCount"], 0)

        report = self.module.summarize_log(path, include_high_risk=True)

        self.assertEqual(report["sourceCounts"]["ueClassObjectIdentities"], 1)
        self.assertEqual(report["candidateCount"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["objectAddress"], "0x1000")
        self.assertEqual(candidate["functionAddress"], "0x2000")
        self.assertEqual(candidate["objectSourceKind"], "class-object")
        self.assertEqual(candidate["risk"], "high")
        self.assertIn("class-object-not-instance", candidate["reasons"])

    def test_streams_raw_loader_log_and_includes_skipped_decoded_cdo_candidate(self):
        path = self.write_log(
            "\n".join(
                [
                    "2026-06-20T22:18:33+0000 pid=1 loader=server event=ue-object-native-identity source=ue-object-array status=skipped arrayName=RuntimeGUObjectArray object=0x1000 name=Default__Actor class=0x3000 className=Actor outer=0x4000 nameDecoded=true classNameDecoded=true",
                    "2026-06-20T22:18:33+0000 pid=1 loader=server event=ue-function-native-identity source=ue-function-link status=promoted name=Actor functionIndex=0 chain=objectArray function=0x2000 functionName=WasRecentlyRendered functionPath=/Script/Actor.WasRecentlyRendered:Function functionRuntimePath=/RuntimeProbe/Actor.WasRecentlyRendered:Function root=0x0 functionFlags=0x6438e00 functionFlagsReadable=true",
                    "2026-06-20T22:18:33+0000 pid=1 loader=server event=ue-function-param name=Actor functionIndex=0 chain=paramScan0x58 index=0 status=candidate function=0x2000 functionName=WasRecentlyRendered functionPath=/Script/Actor.WasRecentlyRendered:Function functionRuntimePath=/RuntimeProbe/Actor.WasRecentlyRendered:Function descriptorSane=true",
                ]
            )
        )

        report = self.module.summarize_log(path)

        self.assertEqual(report["candidateCount"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["objectAddress"], "0x1000")
        self.assertEqual(candidate["objectPath"], "/RuntimeProbe/Default__Actor")
        self.assertEqual(candidate["objectSourceKind"], "object")
        self.assertEqual(candidate["risk"], "moderate")
        self.assertIn("class-default-object", candidate["reasons"])

    def test_excludes_side_effect_like_cdo_function_by_default(self):
        path = self.write_summary(
            {
                "ueObjectNativeIdentities": [
                    {
                        "status": "skipped",
                        "name": "Default__AbilityAsync",
                        "object": "0x1000",
                        "className": "AbilityAsync",
                    }
                ],
                "ueFunctionNativeIdentities": [
                    {
                        "status": "promoted",
                        "name": "AbilityAsync",
                        "function": "0x2000",
                        "functionName": "EndAction",
                        "functionPath": "/Script/AbilityAsync.EndAction:Function",
                        "functionRuntimePath": "/RuntimeProbe/AbilityAsync.EndAction:Function",
                    }
                ],
                "ueFunctionParams": [
                    {
                        "status": "candidate",
                        "function": "0x2000",
                        "descriptorSane": "true",
                    }
                ],
            }
        )

        self.assertEqual(self.module.summarize(path)["candidateCount"], 0)

        report = self.module.summarize(path, include_high_risk=True)
        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["candidates"][0]["risk"], "high")
        self.assertIn("side-effect-like-function-name", report["candidates"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
