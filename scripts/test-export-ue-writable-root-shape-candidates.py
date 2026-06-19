#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-ue-writable-root-shape-candidates.py"

spec = importlib.util.spec_from_file_location("export_ue_writable_root_shape_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ExportUeWritableRootShapeCandidateTests(unittest.TestCase):
    def test_selects_bounded_candidates_per_anchor(self):
        summary = {
            "rows": [
                {"target": "0x1000", "imageOffset": "0x1000", "score": 50, "refCount": 10, "functionBucketCount": 2},
                {
                    "target": "0x2000",
                    "imageOffset": "0x2000",
                    "score": 40,
                    "refCount": 8,
                    "functionBucketCount": 2,
                    "qwordRefCount": 8,
                    "scalarRefCount": 0,
                    "scalarRatio": 0.0,
                },
            ]
        }

        rows = module.select_candidates(summary, ["GUObjectArray", "GWorld"], max_total=3, max_per_anchor=1, min_score=0)

        self.assertEqual([(row["name"], row["imageOffset"]) for row in rows], [
            ("GUObjectArray", "0x1000"),
            ("GWorld", "0x1000"),
        ])

    def test_preserves_shape_quality_metadata(self):
        summary = {
            "rows": [
                {
                    "target": "0x2000",
                    "imageOffset": "0x2000",
                    "score": 40,
                    "refCount": 8,
                    "functionBucketCount": 2,
                    "qwordRefCount": 8,
                    "scalarRefCount": 0,
                    "scalarRatio": 0.0,
                    "addressRatio": 0.01,
                    "kindCounts": {"read": 4, "write": 4},
                },
            ]
        }

        rows = module.select_candidates(summary, ["GUObjectArray"], max_total=1, max_per_anchor=1, min_score=0)

        self.assertEqual(rows[0]["qwordRefCount"], 8)
        self.assertEqual(rows[0]["scalarRefCount"], 0)
        self.assertEqual(rows[0]["scalarRatio"], 0.0)
        self.assertEqual(rows[0]["addressRatio"], 0.01)
        self.assertEqual(rows[0]["readRefCount"], 4)
        self.assertEqual(rows[0]["writeRefCount"], 4)

    def test_quality_filters_reject_generic_high_fanout_globals(self):
        summary = {
            "rows": [
                {
                    "target": "0x1000",
                    "imageOffset": "0x1000",
                    "score": 1000,
                    "refCount": 1420,
                    "functionBucketCount": 746,
                    "qwordRefCount": 1420,
                    "addressRatio": 0.0,
                    "kindCounts": {"read": 710, "write": 710},
                },
                {
                    "target": "0x2000",
                    "imageOffset": "0x2000",
                    "score": 90,
                    "refCount": 12,
                    "functionBucketCount": 4,
                    "qwordRefCount": 12,
                    "addressRatio": 0.01,
                    "kindCounts": {"read": 8, "write": 4},
                },
            ]
        }

        rows = module.select_candidates(
            summary,
            ["GUObjectArray"],
            max_total=2,
            max_per_anchor=2,
            min_score=0,
            max_ref_count=64,
            max_function_buckets=16,
            max_address_ratio=0.05,
            require_read_write=True,
            require_qword=True,
            min_qword_refs=2,
        )

        self.assertEqual([(row["name"], row["imageOffset"]) for row in rows], [("GUObjectArray", "0x2000")])

    def test_quality_filter_rejections_are_reported(self):
        summary = {
            "rows": [
                {
                    "target": "0x1000",
                    "imageOffset": "0x1000",
                    "score": 100,
                    "refCount": 20,
                    "functionBucketCount": 4,
                    "qwordRefCount": 20,
                    "addressRatio": 0.98,
                    "kindCounts": {"address": 20},
                },
            ]
        }
        rejected = []

        rows = module.select_candidates(
            summary,
            ["GUObjectArray"],
            max_total=2,
            max_per_anchor=2,
            min_score=0,
            max_address_ratio=0.05,
            require_read_write=True,
            rejected=rejected,
        )

        self.assertEqual(rows, [])
        self.assertEqual(rejected, [{"target": "0x1000", "anchor": "GUObjectArray", "reason": "max-address-ratio"}])

    def test_quality_filters_can_emit_empty_env_when_only_generic_rows_exist(self):
        summary = {
            "rows": [
                {
                    "target": "0x1000",
                    "imageOffset": "0x1000",
                    "score": 1000,
                    "refCount": 1420,
                    "functionBucketCount": 746,
                    "qwordRefCount": 1420,
                    "addressRatio": 0.0,
                    "kindCounts": {"read": 710, "write": 710},
                },
            ]
        }

        rows = module.select_candidates(
            summary,
            ["GUObjectArray"],
            max_total=2,
            max_per_anchor=2,
            min_score=0,
            max_ref_count=64,
            max_function_buckets=16,
            require_read_write=True,
            require_qword=True,
        )

        self.assertEqual(rows, [])

    def test_require_specific_context_rejects_generic_only_rows(self):
        summary = {
            "rows": [
                {
                    "target": "0x1000",
                    "imageOffset": "0x1000",
                    "score": 100,
                    "refCount": 10,
                    "functionBucketCount": 2,
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": [],
                            "symbols": [],
                            "string": "Runtime/CoreUObject/Public\\UObject/Class.h",
                        },
                    ],
                },
                {
                    "target": "0x2000",
                    "imageOffset": "0x2000",
                    "score": 90,
                    "refCount": 8,
                    "functionBucketCount": 2,
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": [],
                            "symbols": [],
                            "string": "Dune-specific UObject registry walk",
                        },
                    ],
                },
            ],
        }
        rejected = []

        rows = module.select_candidates(
            summary,
            ["GUObjectArray"],
            max_total=4,
            max_per_anchor=4,
            min_score=0,
            require_specific_context=True,
            max_generic_context_ratio=0.50,
            rejected=rejected,
        )

        self.assertEqual([(row["name"], row["imageOffset"]) for row in rows], [("GUObjectArray", "0x2000")])
        self.assertEqual(rows[0]["hintQuality"]["specificContextCount"], 1)
        self.assertEqual(rejected, [{"target": "0x1000", "anchor": "GUObjectArray", "reason": "missing-specific-context"}])

    def test_require_exact_anchor_rejects_group_only_context(self):
        summary = {
            "rows": [
                {
                    "target": "0x1000",
                    "imageOffset": "0x1000",
                    "score": 100,
                    "refCount": 10,
                    "functionBucketCount": 2,
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": [],
                            "symbols": [],
                            "string": "Dune-specific object registry",
                        },
                    ],
                },
                {
                    "target": "0x2000",
                    "imageOffset": "0x2000",
                    "score": 90,
                    "refCount": 8,
                    "functionBucketCount": 2,
                    "context": [
                        {
                            "groups": ["objects"],
                            "exactAnchorHints": ["GUObjectArray"],
                            "symbols": [],
                            "string": "GUObjectArray",
                        },
                    ],
                },
            ],
        }
        rejected = []

        rows = module.select_candidates(
            summary,
            ["GUObjectArray"],
            max_total=4,
            max_per_anchor=4,
            min_score=0,
            require_exact_anchor=True,
            rejected=rejected,
        )

        self.assertEqual([(row["name"], row["imageOffset"]) for row in rows], [("GUObjectArray", "0x2000")])
        self.assertEqual(rows[0]["hintQuality"]["exactContextCount"], 1)
        self.assertEqual(rejected, [{"target": "0x1000", "anchor": "GUObjectArray", "reason": "missing-exact-anchor"}])

    def test_summary_reports_context_rejections(self):
        class Args:
            writable_root_shapes_json = None
            writable_global_refs_json = []
            platform = "server"
            env_name = None
            anchor = ["GUObjectArray"]
            anchor_preset = "object-discovery"
            include = []
            max_total = 10
            max_per_anchor = 4
            min_score = 0
            max_ref_count = 0
            max_function_buckets = 0
            max_address_ratio = None
            require_read_write = False
            require_qword = False
            min_qword_refs = 0
            require_exact_anchor = False
            require_specific_context = True
            max_generic_context_ratio = None

        def fake_load_json(_path):
            return {
                "schemaVersion": "test-shapes",
                "rows": [
                    {
                        "target": "0x1000",
                        "imageOffset": "0x1000",
                        "score": 50,
                        "refCount": 10,
                        "context": [
                            {
                                "groups": ["objects"],
                                "exactAnchorHints": [],
                                "symbols": [],
                                "string": "Runtime/CoreUObject/Public\\UObject/Class.h",
                            }
                        ],
                    },
                ],
            }

        original = module.load_json
        try:
            module.load_json = fake_load_json
            summary = module.summarize(Args())
        finally:
            module.load_json = original

        self.assertEqual(summary["candidateCount"], 0)
        self.assertEqual(summary["rejectedReasonCounts"], {"missing-specific-context": 1})
        self.assertEqual(summary["env"], "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=")

    def test_summary_can_join_writable_global_context_for_strict_export(self):
        class Args:
            writable_root_shapes_json = "shapes.json"
            writable_global_refs_json = ["globals.json"]
            platform = "server"
            env_name = None
            anchor = ["GUObjectArray"]
            anchor_preset = "object-discovery"
            include = []
            max_total = 10
            max_per_anchor = 4
            min_score = 0
            max_ref_count = 0
            max_function_buckets = 0
            max_address_ratio = None
            require_read_write = False
            require_qword = False
            min_qword_refs = 0
            require_exact_anchor = True
            require_specific_context = True
            max_generic_context_ratio = None

        def fake_load_json(path):
            if str(path) == "shapes.json":
                return {
                    "schemaVersion": "test-shapes",
                    "rows": [
                        {
                            "target": "0x2000",
                            "imageOffset": "0x2000",
                            "score": 50,
                            "refCount": 10,
                        },
                    ],
                }
            return {
                "schemaVersion": "test-globals",
                "top": [
                    {
                        "target": "0x2000",
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

        original = module.load_json
        try:
            module.load_json = fake_load_json
            summary = module.summarize(Args())
        finally:
            module.load_json = original

        self.assertEqual(summary["candidateCount"], 1)
        self.assertEqual(summary["sourceGlobalContextCount"], 1)
        self.assertEqual(summary["candidates"][0]["hintQuality"]["exactContextCount"], 1)
        self.assertEqual(summary["candidates"][0]["hintQuality"]["specificContextCount"], 1)
        self.assertEqual(summary["env"], "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=GUObjectArray=0x2000")

    def test_summary_can_join_string_dataflow_writable_targets(self):
        class Args:
            writable_root_shapes_json = "shapes.json"
            writable_global_refs_json = ["dataflow.json"]
            platform = "server"
            env_name = None
            anchor = ["GUObjectArray"]
            anchor_preset = "object-discovery"
            include = []
            max_total = 10
            max_per_anchor = 4
            min_score = 0
            max_ref_count = 0
            max_function_buckets = 0
            max_address_ratio = None
            require_read_write = False
            require_qword = False
            min_qword_refs = 0
            require_exact_anchor = True
            require_specific_context = True
            max_generic_context_ratio = None

        def fake_load_json(path):
            if str(path) == "shapes.json":
                return {
                    "schemaVersion": "test-shapes",
                    "rows": [{"target": "0x4000", "imageOffset": "0x4000", "score": 50, "refCount": 10}],
                }
            return {
                "schemaVersion": "dune-elf-ue-string-dataflow/v1",
                "writableTargets": [
                    {
                        "target": "0x4000",
                        "groups": {"objects": 1},
                        "exactAnchorHintCounts": {"GUObjectArray": 1},
                        "context": [
                            {
                                "groups": ["objects"],
                                "exactAnchorHints": ["GUObjectArray"],
                                "symbols": [],
                                "string": "GUObjectArray",
                            }
                        ],
                    }
                ],
            }

        original = module.load_json
        try:
            module.load_json = fake_load_json
            summary = module.summarize(Args())
        finally:
            module.load_json = original

        self.assertEqual(summary["candidateCount"], 1)
        self.assertEqual(summary["candidates"][0]["imageOffset"], "0x4000")
        self.assertEqual(summary["candidates"][0]["hintQuality"]["exactContextCount"], 1)

    def test_markdown_includes_env_line(self):
        text = module.markdown(
            {
                "platform": "server",
                "anchorPreset": "",
                "candidateCount": 1,
                "anchorCounts": {"FNamePool": 1},
                "groupCoverage": {},
                "missingGroups": [],
                "env": "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70",
                "candidates": [{"name": "FNamePool", "imageOffset": "0x1686df70", "hypothesis": "explicit-include"}],
                "rejectedReasonCounts": {},
            }
        )

        self.assertIn("DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=FNamePool=0x1686df70", text)

    def test_default_preset_covers_names_objects_and_world(self):
        class Args:
            writable_root_shapes_json = None
            platform = "server"
            env_name = None
            anchor = []
            anchor_preset = "object-discovery"
            include = []
            max_total = 10
            max_per_anchor = 1
            min_score = 0
            max_ref_count = 0
            max_function_buckets = 0
            max_address_ratio = None
            require_read_write = False
            require_qword = False
            min_qword_refs = 0

        def fake_load_json(_path):
            return {
                "schemaVersion": "test-shapes",
                "rows": [
                    {"target": "0x1000", "imageOffset": "0x1000", "score": 50, "refCount": 10},
                ],
            }

        original = module.load_json
        try:
            module.load_json = fake_load_json
            args = Args()
            summary = module.summarize(args)
        finally:
            module.load_json = original

        self.assertEqual(summary["anchorPreset"], "object-discovery")
        self.assertEqual(summary["missingGroups"], [])
        self.assertTrue(summary["groupCoverage"]["names"]["ready"])
        self.assertTrue(summary["groupCoverage"]["objects"]["ready"])
        self.assertTrue(summary["groupCoverage"]["world"]["ready"])
        self.assertIn("FNamePool=0x1000", summary["env"])
        self.assertIn("GUObjectArray=0x1000", summary["env"])
        self.assertIn("GWorld=0x1000", summary["env"])


if __name__ == "__main__":
    unittest.main()
