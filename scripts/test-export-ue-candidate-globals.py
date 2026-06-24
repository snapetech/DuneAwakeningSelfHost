#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-ue-candidate-globals.py"

spec = importlib.util.spec_from_file_location("export_ue_candidate_globals", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ExportUeCandidateGlobalsTests(unittest.TestCase):
    def test_exports_ranked_candidates_and_skips_rejected_log_offsets(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "binary": "/tmp/DuneSandboxServer-Linux-Shipping",
            "top": [
                {
                    "target": "0x165ff4a8",
                    "fileOffset": "unbacked",
                    "refCount": 416,
                    "functionBucketCount": 400,
                    "score": 1756,
                    "groupCounts": {"objects": 6},
                    "exactAnchorHintCounts": {"GUObjectArray": 1},
                },
                {
                    "target": "0x165d1ba0",
                    "fileOffset": "unbacked",
                    "refCount": 2163,
                    "functionBucketCount": 2019,
                    "score": 10279,
                    "groupCounts": {"objects": 2},
                    "exactAnchorHintCounts": {},
                },
                {
                    "target": "0x1686df70",
                    "fileOffset": "unbacked",
                    "refCount": 1799,
                    "functionBucketCount": 1666,
                    "score": 8503,
                    "groupCounts": {"names": 2},
                    "exactAnchorHintCounts": {},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "\n".join(
                    [
                        "pid=1 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0x1 imageOffset=0x165ff4a8 absolute=false",
                        "pid=1 loader=server event=ue-pointer name=GUObjectArray status=null anchor=0x1 value=0x0",
                    ]
                ),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "reject_log": [log],
                    "candidate_outcomes_json": [],
                    "writable_root_shapes_json": None,
                    "require_root_shape": False,
                    "min_qword_refs": 0,
                    "max_scalar_ratio": None,
                    "max_address_ratio": None,
                    "min_read_refs": 0,
                    "min_write_refs": 0,
                    "groups": None,
                    "include_reflection": False,
                    "min_refs": 0,
                    "max_refs": 0,
                    "max_function_buckets": 0,
                    "max_per_anchor": 4,
                    "max_total": 8,
                },
            )()
            result = module.export_candidates(summary, args)

        self.assertIn("GUObjectArray=0x165d1ba0", result["env"])
        self.assertIn("FNamePool=0x1686df70", result["env"])
        self.assertNotIn("0x165ff4a8", result["env"])
        self.assertEqual(result["anchorCounts"], {"FNamePool": 1, "GUObjectArray": 1})
        self.assertEqual(result["binary"], "/tmp/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(result["candidates"][0]["source"], "/tmp/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(result["candidates"][0]["sourceProvenance"], "target")

    def test_reject_log_matches_bad_anchor_address_before_same_name_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "\n".join(
                    [
                        "pid=1 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0xaaa imageOffset=0x111 absolute=false",
                        "pid=1 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0xbbb imageOffset=0x222 absolute=false",
                        "pid=1 loader=server event=ue-object-array name=GUObjectArray mode=direct status=empty base=0xbbb anchor=0xbbb chunks=0x0",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(module.load_rejected_offsets([log]), {("GUObjectArray", 0x222)})

    def test_reject_log_falls_back_to_same_name_when_anchor_address_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "\n".join(
                    [
                        "pid=1 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0xaaa imageOffset=0x111 absolute=false",
                        "pid=1 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0xbbb imageOffset=0x222 absolute=false",
                        "pid=1 loader=server event=ue-pointer name=GUObjectArray status=null value=0x0",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                module.load_rejected_offsets([log]),
                {("GUObjectArray", 0x111), ("GUObjectArray", 0x222)},
            )

    def test_reject_log_rejects_direct_object_array_zero_scan_by_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "\n".join(
                    [
                        "pid=343 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0xabc imageOffset=0x333 absolute=false",
                        "pid=343 loader=server event=ue-object-array name=GUObjectArray mode=direct status=finished base=0xabc scanned=0 registered=0",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(module.load_rejected_offsets([log]), {("GUObjectArray", 0x333)})

    def test_reject_log_rejects_uobject_candidate_with_unmapped_class_or_vtable(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "\n".join(
                    [
                        "pid=343 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0xabc imageOffset=0x333 absolute=false",
                        "pid=343 loader=server event=ue-uobject name=GUObjectArray status=candidate anchor=0xabc target=0xdef vtableMapped=false classMapped=false",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(module.load_rejected_offsets([log]), {("GUObjectArray", 0x333)})

    def test_reject_log_uses_packaged_sibling_scan_parser(self):
        original = module.SCAN_SUMMARY_SCRIPTS
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parser = tmp_path / "summarize-client-loader-scan.py"
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
            log = tmp_path / "loader.log"
            log.write_text("", encoding="utf-8")
            module.SCAN_SUMMARY_SCRIPTS = (tmp_path / "missing.py", parser)
            try:
                rejected = module.load_rejected_offsets([log])
            finally:
                module.SCAN_SUMMARY_SCRIPTS = original

        self.assertEqual(rejected, {("GWorld", 0x200)})

    def test_name_anchor_with_ready_fname_is_not_rejected_by_object_array_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(
                "\n".join(
                    [
                        "pid=343 loader=server event=ue-candidate-global name=FNamePool status=added address=0xabc imageOffset=0x1686df70 absolute=false",
                        "pid=343 loader=server event=ue-fname-start status=ready pool=0xabc source=FNamePool:direct",
                        "pid=343 loader=server event=ue-pointer name=FNamePool status=null anchor=0xabc value=0x0",
                        "pid=343 loader=server event=ue-object-array name=FNamePool status=empty base=0xabc",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(module.load_rejected_offsets([log]), set())

    def test_candidate_outcomes_json_rejects_failed_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            outcome = Path(tmp) / "outcomes.json"
            outcome.write_text(
                """
{
  "candidates": [
    {"name": "GUObjectArray", "imageOffset": "0x165d1fe8", "verdict": "rejected"},
    {"name": "GWorld", "imageOffset": "0x165f3e38", "verdict": "weak-false-positive"},
    {"name": "FNamePool", "imageOffset": "0x1686df70", "verdict": "rejected"}
  ]
}
""".strip(),
                encoding="utf-8",
            )

            self.assertEqual(
                module.load_rejected_offsets([], [outcome]),
                {("GUObjectArray", 0x165D1FE8), ("GWorld", 0x165F3E38)},
            )

    def test_ref_caps_filter_shared_globals(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 10000,
                    "functionBucketCount": 9000,
                    "score": 10000,
                    "groupCounts": {"objects": 2},
                    "exactAnchorHintCounts": {},
                },
                {
                    "target": "0x2000",
                    "fileOffset": "unbacked",
                    "refCount": 100,
                    "functionBucketCount": 90,
                    "score": 100,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {},
                },
            ],
        }
        args = type(
            "Args",
            (),
                {
                    "reject_log": [],
                    "candidate_outcomes_json": [],
                    "writable_root_shapes_json": None,
                    "require_root_shape": False,
                    "min_qword_refs": 0,
                    "max_scalar_ratio": None,
                    "max_address_ratio": None,
                    "min_read_refs": 0,
                    "min_write_refs": 0,
                    "groups": None,
                    "include_reflection": False,
                    "min_refs": 0,
                "max_refs": 1000,
                "max_function_buckets": 1000,
                "max_per_anchor": 4,
                "max_total": 8,
            },
        )()

        result = module.export_candidates(summary, args)

        self.assertNotIn("0x1000", result["env"])
        self.assertIn("GUObjectArray=0x2000", result["env"])

    def test_can_require_matching_qword_root_shape(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 100,
                    "groupCounts": {"objects": 2},
                    "exactAnchorHintCounts": {"GUObjectArray": 1},
                },
                {
                    "target": "0x2000",
                    "fileOffset": "unbacked",
                    "refCount": 40,
                    "functionBucketCount": 8,
                    "score": 90,
                    "groupCounts": {"world": 1},
                    "exactAnchorHintCounts": {},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            shapes = Path(tmp) / "shapes.json"
            shapes.write_text(
                """
{
  "rows": [
    {
      "target": "0x1000",
      "score": 70,
      "refCount": 20,
      "functionBucketCount": 4,
      "qwordRefCount": 20,
      "scalarRatio": 0.0,
      "kindCounts": {"read": 10, "write": 10}
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "reject_log": [],
                    "candidate_outcomes_json": [],
                    "writable_root_shapes_json": shapes,
                    "require_root_shape": True,
                    "min_qword_refs": 8,
                    "max_scalar_ratio": 0.0,
                    "max_address_ratio": 0.50,
                    "min_read_refs": 8,
                    "min_write_refs": 8,
                    "groups": None,
                    "include_reflection": False,
                    "min_refs": 0,
                    "max_refs": 0,
                    "max_function_buckets": 0,
                    "max_per_anchor": 4,
                    "max_total": 8,
                },
            )()
            result = module.export_candidates(summary, args)

        self.assertIn("GUObjectArray=0x1000", result["env"])
        self.assertNotIn("0x2000", result["env"])
        self.assertEqual(result["candidates"][0]["rootShape"]["qwordRefCount"], 20)

    def test_root_shape_thresholds_reject_weak_shape(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 100,
                    "groupCounts": {"objects": 2},
                    "exactAnchorHintCounts": {"GUObjectArray": 1},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            shapes = Path(tmp) / "shapes.json"
            shapes.write_text(
                """
{
  "rows": [
    {
      "target": "0x1000",
      "qwordRefCount": 2,
      "scalarRatio": 0.5,
      "kindCounts": {"read": 2, "write": 0}
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "reject_log": [],
                    "candidate_outcomes_json": [],
                    "writable_root_shapes_json": shapes,
                    "require_root_shape": True,
                    "min_qword_refs": 8,
                    "max_scalar_ratio": 0.0,
                    "max_address_ratio": 0.50,
                    "min_read_refs": 8,
                    "min_write_refs": 8,
                    "groups": None,
                    "include_reflection": False,
                    "min_refs": 0,
                    "max_refs": 0,
                    "max_function_buckets": 0,
                    "max_per_anchor": 4,
                    "max_total": 8,
                },
            )()
            result = module.export_candidates(summary, args)

        self.assertEqual(result["candidateCount"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "min-qword-refs")

    def test_root_shape_thresholds_reject_address_heavy_shape(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 100,
                    "groupCounts": {"objects": 2},
                    "exactAnchorHintCounts": {"GUObjectArray": 1},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            shapes = Path(tmp) / "shapes.json"
            shapes.write_text(
                """
{
  "rows": [
    {
      "target": "0x1000",
      "qwordRefCount": 100,
      "scalarRatio": 0.0,
      "addressRatio": 0.95,
      "kindCounts": {"address": 95, "read": 4, "write": 1}
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "reject_log": [],
                    "candidate_outcomes_json": [],
                    "writable_root_shapes_json": shapes,
                    "require_root_shape": True,
                    "min_qword_refs": 1,
                    "max_scalar_ratio": 0.0,
                    "max_address_ratio": 0.50,
                    "min_read_refs": 1,
                    "min_write_refs": 1,
                    "groups": None,
                    "include_reflection": False,
                    "min_refs": 0,
                    "max_refs": 0,
                    "max_function_buckets": 0,
                    "max_per_anchor": 4,
                    "max_total": 8,
                },
            )()
            result = module.export_candidates(summary, args)

        self.assertEqual(result["candidateCount"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "max-address-ratio")

    def test_hint_quality_marks_generic_context_and_can_filter_it(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 100,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {},
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": [],
                            "symbols": [],
                            "string": "Runtime/CoreUObject/Public\\UObject/Class.h",
                        }
                    ],
                },
                {
                    "target": "0x2000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 90,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {},
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": [],
                            "symbols": [],
                            "string": "Project-specific UObject registry walk",
                        }
                    ],
                },
            ],
        }
        args = type(
            "Args",
            (),
            {
                "reject_log": [],
                "candidate_outcomes_json": [],
                "writable_root_shapes_json": None,
                "require_root_shape": False,
                "min_qword_refs": 0,
                "max_scalar_ratio": None,
                "max_address_ratio": None,
                "min_read_refs": 0,
                "min_write_refs": 0,
                "require_exact_anchor": False,
                "require_specific_context": True,
                "max_generic_context_ratio": 0.50,
                "groups": None,
                "include_reflection": False,
                "min_refs": 0,
                "max_refs": 0,
                "max_function_buckets": 0,
                "max_per_anchor": 4,
                "max_total": 8,
            },
        )()

        result = module.export_candidates(summary, args)

        self.assertEqual(result["candidateCount"], 1)
        self.assertIn("GUObjectArray=0x2000", result["env"])
        self.assertEqual(result["candidates"][0]["hintQuality"]["specificContextCount"], 1)
        self.assertEqual(result["rejected"][0]["reason"], "missing-specific-context")
        self.assertEqual(result["rejectedReasonCounts"], {"missing-specific-context": 1})

    def test_can_require_exact_anchor_context(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 100,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {},
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": [],
                            "symbols": [],
                            "string": "Project-specific UObject registry walk",
                        }
                    ],
                },
                {
                    "target": "0x2000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 90,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {"GUObjectArray": 1},
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": ["GUObjectArray"],
                            "symbols": [],
                            "string": "GUObjectArray",
                        }
                    ],
                },
            ],
        }
        args = type(
            "Args",
            (),
            {
                "reject_log": [],
                "candidate_outcomes_json": [],
                "writable_root_shapes_json": None,
                "require_root_shape": False,
                "min_qword_refs": 0,
                "max_scalar_ratio": None,
                "max_address_ratio": None,
                "min_read_refs": 0,
                "min_write_refs": 0,
                "require_exact_anchor": True,
                "require_specific_context": False,
                "max_generic_context_ratio": None,
                "groups": None,
                "include_reflection": False,
                "min_refs": 0,
                "max_refs": 0,
                "max_function_buckets": 0,
                "max_per_anchor": 4,
                "max_total": 8,
            },
        )()

        result = module.export_candidates(summary, args)

        self.assertEqual(result["candidateCount"], 1)
        self.assertIn("GUObjectArray=0x2000", result["env"])
        self.assertEqual(result["candidates"][0]["hintQuality"]["exactContextCount"], 1)
        self.assertEqual(result["rejected"][0]["reason"], "missing-exact-anchor")
        self.assertEqual(result["rejectedReasonCounts"], {"missing-exact-anchor": 1})

    def test_exact_alias_hints_are_exported_with_core_groups(self):
        summary = {
            "schemaVersion": "dune-elf-writable-global-refs/v1",
            "top": [
                {
                    "target": "0x1000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 100,
                    "groupCounts": {"names": 1},
                    "exactAnchorHintCounts": {"NamePoolData": 1},
                    "context": [{"groups": ["names"], "exactAnchorHints": ["NamePoolData"], "string": "NamePoolData"}],
                },
                {
                    "target": "0x2000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 90,
                    "groupCounts": {"names": 1},
                    "exactAnchorHintCounts": {"GNames": 1},
                    "context": [{"groups": ["names"], "exactAnchorHints": ["GNames"], "string": "GNames"}],
                },
                {
                    "target": "0x3000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 80,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {"GObjects": 1},
                    "context": [{"groups": ["objects"], "exactAnchorHints": ["GObjects"], "string": "GObjects"}],
                },
                {
                    "target": "0x4000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 70,
                    "groupCounts": {"objects": 1},
                    "exactAnchorHintCounts": {"FUObjectArray": 1},
                    "context": [{"groups": ["objects"], "exactAnchorHints": ["FUObjectArray"], "string": "FUObjectArray"}],
                },
                {
                    "target": "0x5000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 60,
                    "groupCounts": {"dispatch": 1},
                    "exactAnchorHintCounts": {"CallFunctionByName": 1},
                    "context": [{"groups": ["dispatch"], "exactAnchorHints": ["CallFunctionByName"], "string": "CallFunctionByName"}],
                },
                {
                    "target": "0x6000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 50,
                    "groupCounts": {"reflection": 1},
                    "exactAnchorHintCounts": {"UStruct": 1},
                    "context": [{"groups": ["reflection"], "exactAnchorHints": ["UStruct"], "string": "UStruct"}],
                },
                {
                    "target": "0x7000",
                    "fileOffset": "unbacked",
                    "refCount": 50,
                    "functionBucketCount": 10,
                    "score": 40,
                    "groupCounts": {"reflection": 1},
                    "exactAnchorHintCounts": {"UEnum": 1},
                    "context": [{"groups": ["reflection"], "exactAnchorHints": ["UEnum"], "string": "UEnum"}],
                },
            ],
        }
        args = type(
            "Args",
            (),
            {
                "reject_log": [],
                "candidate_outcomes_json": [],
                "writable_root_shapes_json": None,
                "require_root_shape": False,
                "min_qword_refs": 0,
                "max_scalar_ratio": None,
                "max_address_ratio": None,
                "min_read_refs": 0,
                "min_write_refs": 0,
                "require_exact_anchor": True,
                "require_specific_context": False,
                "max_generic_context_ratio": None,
                "groups": None,
                "include_reflection": True,
                "min_refs": 0,
                "max_refs": 0,
                "max_function_buckets": 0,
                "max_per_anchor": 4,
                "max_total": 16,
            },
        )()

        result = module.export_candidates(summary, args)

        self.assertIn("NamePoolData=0x1000", result["env"])
        self.assertIn("GNames=0x2000", result["env"])
        self.assertIn("GObjects=0x3000", result["env"])
        self.assertIn("FUObjectArray=0x4000", result["env"])
        self.assertIn("CallFunctionByName=0x5000", result["env"])
        self.assertIn("UStruct=0x6000", result["env"])
        self.assertIn("UEnum=0x7000", result["env"])
        self.assertEqual(result["groups"], {"dispatch": 1, "names": 2, "objects": 2, "reflection": 2})


if __name__ == "__main__":
    unittest.main()
