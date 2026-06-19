#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue-candidate-shapes.py"

spec = importlib.util.spec_from_file_location("summarize_ue_candidate_shapes", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class UeCandidateShapeTests(unittest.TestCase):
    def test_classifies_null_and_code_pointer_candidates(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "null", "anchor": "0x1000", "value": "0x0"},
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x2000", "imageOffset": "0x20"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "target-mapped", "anchor": "0x2000", "value": "0x5000", "executable": "true"},
        ]

        summary = module.summarize_records(records)

        self.assertEqual(summary["verdictCounts"], {"rejected-null": 1, "weak-code-pointer": 1})

    def test_classifies_unmapped_uobject_shape(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "target-mapped", "anchor": "0x1000", "value": "0x3000", "executable": "false"},
            {
                "event": "ue-uobject",
                "name": "GUObjectArray",
                "status": "candidate",
                "anchor": "0x1000",
                "target": "0x3000",
                "classMapped": "false",
                "vtableMapped": "true",
            },
        ]

        summary = module.summarize_records(records)

        self.assertEqual(summary["candidates"][0]["verdict"], "rejected-uobject-shape")

    def test_classifies_promotable_object_array_with_decoded_fname(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "target-mapped", "anchor": "0x1000", "value": "0x3000", "executable": "false"},
            {
                "event": "ue-object-array-shape",
                "name": "GUObjectArray",
                "status": "header-plausible",
                "base": "0x1000",
                "countsPlausible": "true",
                "chunkSlotReadable": "true",
                "firstChunkMapped": "true",
                "numElements": "2",
                "numChunks": "1",
            },
            {"event": "ue-object-array", "name": "GUObjectArray", "status": "finished", "base": "0x1000", "scanned": "2", "registered": "1"},
            {"event": "ue-object-array-item", "name": "GUObjectArray", "status": "registered", "object": "0x5000"},
            {"event": "ue-fname", "objectName": "GUObjectArray_0", "status": "decoded", "decoded": "World_0"},
            {
                "event": "lua-object-registry",
                "source": "ue-object-array-fname",
                "status": "registered",
                "name": "GUObjectArray_0",
                "registryProvenance": "runtime",
            },
            {
                "event": "ue-object-native-identity",
                "source": "ue-object-array",
                "status": "promoted",
                "arrayName": "GUObjectArray",
                "name": "World_0",
            },
        ]

        summary = module.summarize_records(records)

        self.assertEqual(summary["candidates"][0]["verdict"], "promotable-object-array")
        self.assertIn("objectArrayShape status=`header-plausible`", module.markdown(summary))
        self.assertIn("runtimeRegistry objectRuntime=`1`", module.markdown(summary))

    def test_object_array_without_runtime_registry_is_only_promising(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "target-mapped", "anchor": "0x1000", "value": "0x3000", "executable": "false"},
            {
                "event": "ue-object-array-shape",
                "name": "GUObjectArray",
                "status": "header-plausible",
                "base": "0x1000",
                "countsPlausible": "true",
                "chunkSlotReadable": "true",
                "firstChunkMapped": "true",
            },
            {"event": "ue-object-array", "name": "GUObjectArray", "status": "finished", "base": "0x1000", "scanned": "2", "registered": "1"},
            {"event": "ue-fname", "objectName": "GUObjectArray_0", "status": "decoded", "decoded": "World_0"},
        ]

        summary = module.summarize_records(records)

        self.assertEqual(summary["candidates"][0]["verdict"], "promising-object-array")

    def test_runtime_registry_evidence_is_candidate_specific(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-candidate-global", "name": "GWorld", "status": "added", "address": "0x2000", "imageOffset": "0x20"},
            {"event": "ue-object-array-item", "name": "GUObjectArray", "status": "registered", "object": "0x5000"},
            {"event": "ue-fname", "objectName": "GUObjectArray_0", "status": "decoded", "decoded": "World_0"},
            {
                "event": "ue-object-native-identity",
                "source": "ue-object-array",
                "status": "promoted",
                "arrayName": "GUObjectArray",
                "name": "World_0",
            },
        ]

        summary = module.summarize_records(records)
        by_name = {row["name"]: row for row in summary["candidates"]}

        self.assertEqual(by_name["GUObjectArray"]["runtimeRegistry"]["nativeIdentityPromoted"], 1)
        self.assertEqual(by_name["GWorld"]["runtimeRegistry"]["nativeIdentityPromoted"], 0)

    def test_name_pool_ready_is_promising_despite_object_array_noise(self):
        records = [
            {"event": "ue-candidate-global", "name": "FNamePool", "status": "added", "address": "0x1000", "imageOffset": "0x1686df70"},
            {"event": "ue-fname-start", "status": "ready", "pool": "0x1000", "source": "FNamePool:direct"},
            {"event": "ue-pointer", "name": "FNamePool", "status": "null", "anchor": "0x1000", "value": "0x0"},
            {"event": "ue-object-array", "name": "FNamePool", "status": "empty", "base": "0x1000"},
            {"event": "ue-fname-finish", "status": "ready", "pool": "0x1000", "source": "FNamePool:direct"},
        ]

        summary = module.summarize_records(records)
        row = summary["candidates"][0]

        self.assertEqual(summary["verdictCounts"], {"promising-fname-pool": 1})
        self.assertEqual(row["verdict"], "promising-fname-pool")
        self.assertEqual(row["fname"]["ready"], 2)
        self.assertEqual(row["fname"]["readySources"], ["FNamePool:direct"])
        self.assertIn("fname ready=`2`", module.markdown(summary))

    def test_rejects_implausible_object_array_header(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "target-mapped", "anchor": "0x1000", "value": "0x3000", "executable": "false"},
            {
                "event": "ue-object-array-shape",
                "name": "GUObjectArray",
                "status": "header-implausible",
                "base": "0x1000",
                "countsPlausible": "false",
                "chunkSlotReadable": "false",
                "firstChunkMapped": "false",
                "numElements": "100",
                "maxElements": "1",
                "numChunks": "50",
                "maxChunks": "1",
            },
            {"event": "ue-object-array", "name": "GUObjectArray", "status": "header-implausible", "base": "0x1000"},
        ]

        summary = module.summarize_records(records)
        row = summary["candidates"][0]

        self.assertEqual(row["verdict"], "rejected-object-array-header")
        self.assertEqual(row["objectArray"]["implausibleHeaders"], 2)
        self.assertEqual(summary["verdictCounts"], {"rejected-object-array-header": 1})

    def test_plausible_indirect_header_prevents_direct_header_rejection(self):
        records = [
            {"event": "ue-candidate-global", "name": "GUObjectArray", "status": "added", "address": "0x1000", "imageOffset": "0x10"},
            {"event": "ue-pointer", "name": "GUObjectArray", "status": "target-mapped", "anchor": "0x1000", "value": "0x3000", "executable": "false"},
            {
                "event": "ue-object-array-shape",
                "name": "GUObjectArray",
                "status": "header-implausible",
                "base": "0x1000",
                "countsPlausible": "false",
            },
            {
                "event": "ue-object-array-shape",
                "name": "GUObjectArray",
                "status": "header-plausible",
                "base": "0x1000",
                "countsPlausible": "true",
                "chunkSlotReadable": "true",
                "firstChunkMapped": "true",
            },
        ]

        summary = module.summarize_records(records)
        row = summary["candidates"][0]

        self.assertEqual(row["verdict"], "weak-mapped")
        self.assertEqual(row["objectArray"]["implausibleHeaders"], 1)
        self.assertEqual(row["objectArray"]["plausibleHeaders"], 1)

    def test_loads_records_through_packaged_scan_parser(self):
        original = module.SCAN_SUMMARY_SCRIPTS
        with tempfile.TemporaryDirectory() as tmp:
            parser = Path(tmp) / "summarize-client-loader-scan.py"
            parser.write_text(
                "\n".join(
                    [
                        "def load_records(path):",
                        "    return [",
                        "      {'event': 'ue-candidate-global', 'name': 'GWorld', 'status': 'added', 'address': '0x100', 'imageOffset': '0x200'},",
                        "      {'event': 'ue-pointer', 'name': 'GWorld', 'status': 'null', 'anchor': '0x100'},",
                        "    ]",
                    ]
                ),
                encoding="utf-8",
            )
            log = Path(tmp) / "loader.log"
            log.write_text("", encoding="utf-8")
            module.SCAN_SUMMARY_SCRIPTS = (Path(tmp) / "missing.py", parser)
            try:
                summary = module.summarize_paths([log])
            finally:
                module.SCAN_SUMMARY_SCRIPTS = original

        self.assertEqual(summary["verdictCounts"], {"rejected-null": 1})


if __name__ == "__main__":
    unittest.main()
