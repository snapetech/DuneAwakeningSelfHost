#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-route-evidence.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_package_route_evidence", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageRouteEvidenceTests(unittest.TestCase):
    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_callgraph_route_reports_package_anchor_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 4,
                    "edgeCount": 1,
                    "promotionBlockers": ["no direct package anchor hints"],
                },
            )

            summary = module.summarize([("route", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertFalse(summary["complete"])
        self.assertEqual(route["finding"], "negative")
        self.assertEqual(route["metrics"]["packageAnchorNodeCount"], 0)
        self.assertIn("packageAnchorNodeCount=0", route["summary"])

    def test_rtti_route_can_mark_promotable_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rtti.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-rtti-function-object-vtables/v1",
                    "rowCount": 3,
                    "vtableCount": 3,
                    "methodSlotCount": 9,
                    "promotablePackageAnchorCount": 1,
                    "leadKindCounts": {"package-loader-owner-function": 3},
                    "promotionRule": "reviewed",
                },
            )

            summary = module.summarize([("rtti", "rtti-vtables", str(path))])

        self.assertTrue(summary["complete"])
        self.assertEqual(summary["promotableRouteCount"], 1)
        self.assertEqual(summary["routes"][0]["finding"], "promotable")

    def test_source_xref_review_route_reports_negative_reviewed_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-xref-review.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-ue4ss-package-source-xref-review/v1",
                    "promotable": False,
                    "packageHitCount": 0,
                    "routes": [
                        {
                            "id": "loadobjectfrom-table-depth4",
                            "finding": "non-promotable",
                            "metrics": {
                                "nodeCount": 18,
                                "edgeCount": 37,
                                "packageAnchorNodeCount": 0,
                            },
                        },
                        {
                            "id": "source-diagnostic-xrefs",
                            "finding": "non-promotable",
                            "metrics": {
                                "focusedStringsWithCodeRefs": 5,
                                "focusedExecutableSymbolCandidateCount": 0,
                            },
                        },
                    ],
                    "blockers": [
                        "LoadObjectFrom table route has zero package anchor nodes at depth 4",
                        "focused package source xrefs have zero executable wrapper symbol candidates",
                    ],
                },
            )

            summary = module.summarize([("source-xref-review", "source-xref-review", str(path))])

        route = summary["routes"][0]
        self.assertFalse(summary["complete"])
        self.assertEqual(route["finding"], "negative")
        self.assertEqual(route["metrics"]["reviewedRouteCount"], 2)
        self.assertEqual(route["metrics"]["nonPromotableRouteCount"], 2)
        self.assertEqual(route["metrics"]["loadobjectfrom-table-depth4.packageAnchorNodeCount"], 0)
        self.assertEqual(route["metrics"]["source-diagnostic-xrefs.focusedStringsWithCodeRefs"], 5)
        self.assertIn("source/loadobject routes reviewed=2", route["summary"])

    def test_static_metadata_recovery_route_reports_missing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "static-metadata.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-ue4ss-package-static-metadata-recovery/v1",
                    "complete": False,
                    "debugLines": {"lineCount": 0},
                    "symbolAnchors": {"anchorSymbolCount": 0},
                    "sourcePointerContext": {"contextCount": 0, "targetCount": 3},
                    "blockers": [
                        "target binary has no decoded DWARF line table entries for source-line recovery"
                    ],
                },
            )

            summary = module.summarize([("static-metadata", "static-metadata-recovery", str(path))])

        route = summary["routes"][0]
        self.assertFalse(summary["complete"])
        self.assertEqual(route["finding"], "negative")
        self.assertEqual(route["metrics"]["debugLineCount"], 0)
        self.assertEqual(route["metrics"]["anchorSymbolCount"], 0)
        self.assertEqual(route["metrics"]["sourcePointerTargetCount"], 3)
        self.assertIn("static metadata debugLines=0", route["summary"])

    def test_rtti_route_exports_decompile_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rtti.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-rtti-function-object-vtables/v1",
                    "rowCount": 1,
                    "vtableCount": 1,
                    "methodSlotCount": 1,
                    "promotablePackageAnchorCount": 0,
                    "leadKindCounts": {"package-loader-owner-function": 1},
                    "rows": [
                        {
                            "leadKind": "package-loader-owner-function",
                            "owners": ["FAsyncLoadingThread::QueueEvent_CreateLinker"],
                            "vtables": [
                                {
                                    "slots": [
                                        {
                                            "candidateKind": "method",
                                            "index": 0,
                                            "value": "0xfa631e0",
                                            "shape": {"hasCall": True},
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("raw-rtti", "rtti-vtables", str(path))])

        self.assertEqual(summary["decompileReviewQueueCount"], 1)
        entry = summary["decompileReviewQueue"][0]
        self.assertEqual(entry["address"], "0xfa631e0")
        self.assertEqual(entry["leadKind"], "package-loader-owner-function")
        self.assertIn("stable package/load-object ABI", entry["reason"])

    def test_rtti_function_object_dispatch_thunk_is_not_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rtti.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-rtti-function-object-vtables/v1",
                    "rowCount": 1,
                    "vtableCount": 1,
                    "methodSlotCount": 1,
                    "promotablePackageAnchorCount": 0,
                    "rows": [
                        {
                            "leadKind": "package-loader-owner-function",
                            "owners": ["FAsyncLoadingThread::QueueEvent_CreateLinker"],
                            "vtables": [
                                {
                                    "slots": [
                                        {
                                            "candidateKind": "function-object-dispatch",
                                            "index": 1,
                                            "target": "0xfa63220",
                                            "shape": {"hasCall": True, "hasIndirectCall": True},
                                        },
                                        {
                                            "candidateKind": "method",
                                            "index": 3,
                                            "target": "0x959fd80",
                                            "shape": {"hasCall": True},
                                        },
                                    ]
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("raw-rtti", "rtti-vtables", str(path))])

        self.assertEqual(summary["decompileReviewQueueCount"], 0)

    def test_callgraph_indirect_calls_export_decompile_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodes": [
                        {
                            "function": "0x5000",
                            "seedName": "UnresolvedLoadPath",
                            "path": ["0x5000"],
                            "indirectCalls": [
                                {
                                    "instruction": "0x5008",
                                    "text": "call qword ptr [rax + 0x28]",
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("kismet-loadasset-callgraph", "callgraph", str(path))])

        self.assertEqual(summary["decompileReviewQueueCount"], 1)
        entry = summary["decompileReviewQueue"][0]
        self.assertEqual(entry["address"], "0x5000")
        self.assertEqual(entry["indirectCallCount"], 1)
        self.assertIn("call-frame contract", entry["reason"])

    def test_callgraph_allocator_dispatch_is_reported_but_not_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 1,
                    "edgeCount": 0,
                    "nodes": [
                        {
                            "function": "0xf7f3c10",
                            "seedName": "KismetLoadAsset_helper",
                            "refs": [{"target": "0x165f50f8"}],
                            "indirectCalls": [
                                {
                                    "instruction": "0xf7f3c46",
                                    "text": "call qword ptr [rax + 0x38]",
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("kismet", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertEqual(summary["decompileReviewQueueCount"], 0)
        self.assertEqual(summary["suppressedKnownNonPackageQueueCount"], 1)
        self.assertEqual(summary["suppressedKnownNonPackageQueue"][0]["address"], "0xf7f3c10")
        self.assertIn("FMalloc proxy singleton", summary["suppressedKnownNonPackageQueue"][0]["reason"])
        self.assertEqual(route["metrics"]["knownNonPackageDispatchNodeCount"], 1)
        self.assertIn("FMalloc proxy singleton", " ".join(route["blockers"]))

    def test_known_non_package_function_is_reported_but_not_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 1,
                    "edgeCount": 0,
                    "nodes": [
                        {
                            "function": "0x128ce8d0",
                            "seedName": "FLoadAssetActionBase_dispatch",
                            "refs": [],
                            "indirectCalls": [
                                {
                                    "instruction": "0x128ce902",
                                    "text": "call qword ptr [rax + 0x28]",
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("kismet", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertEqual(summary["decompileReviewQueueCount"], 0)
        self.assertEqual(summary["suppressedKnownNonPackageQueueCount"], 1)
        self.assertEqual(summary["suppressedKnownNonPackageQueue"][0]["address"], "0x128ce8d0")
        self.assertEqual(route["metrics"]["knownNonPackageDispatchNodeCount"], 1)
        self.assertIn("owner-surface assert/log path", " ".join(route["blockers"]))

    def test_function_object_dispatch_callgraph_seed_is_reported_but_not_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 1,
                    "edgeCount": 0,
                    "nodes": [
                        {
                            "function": "0xfa63230",
                            "seedName": "rtti0_vt0_slot2_function_object_dispatch",
                            "refs": [],
                            "indirectCalls": [
                                {
                                    "instruction": "0xfa63237",
                                    "text": "call qword ptr [rax + 0x18]",
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("raw-typeinfo", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertEqual(summary["decompileReviewQueueCount"], 0)
        self.assertEqual(route["metrics"]["knownNonPackageDispatchNodeCount"], 1)
        self.assertIn("type-erasure dispatch", " ".join(route["blockers"]))

    def test_streamable_delegate_thunk_is_reported_but_not_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 1,
                    "edgeCount": 0,
                    "nodes": [
                        {
                            "function": "0x9598a00",
                            "seedName": "stslot4",
                            "refs": [],
                            "indirectCalls": [
                                {
                                    "instruction": "0x9598a07",
                                    "text": "call qword ptr [rax + 0x40]",
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("streamable", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertEqual(summary["decompileReviewQueueCount"], 0)
        self.assertEqual(route["metrics"]["knownNonPackageDispatchNodeCount"], 1)
        self.assertIn("common delegate predicate thunk", " ".join(route["blockers"]))

    def test_decompiled_streamable_review_slots_are_not_requeued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 1,
                    "edgeCount": 0,
                    "nodes": [
                        {
                            "function": "0xa54f700",
                            "seedName": "streamable reviewed slot",
                            "refs": [],
                            "indirectCalls": [
                                {
                                    "instruction": "0xa54f92b",
                                    "text": "call qword ptr [rax + 0x10]",
                                }
                            ],
                        },
                        {
                            "function": "0xa8eac80",
                            "seedName": "streamable reviewed reflection slot",
                            "refs": [],
                            "indirectCalls": [
                                {
                                    "instruction": "0xa8eabe0",
                                    "text": "call qword ptr [rax + 0x68]",
                                }
                            ],
                        },
                        {
                            "function": "0x12de96e0",
                            "seedName": "streamable reviewed malformed slot",
                            "refs": [],
                            "indirectCalls": [
                                {
                                    "instruction": "0x12de96ee",
                                    "text": "call 0x12ab3050",
                                }
                            ],
                        },
                    ],
                },
            )

            summary = module.summarize([("streamable", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertEqual(summary["decompileReviewQueueCount"], 0)
        self.assertEqual(route["metrics"]["knownNonPackageDispatchNodeCount"], 3)
        self.assertIn("hash/map delta bookkeeping", " ".join(route["blockers"]))

    def test_decompiled_async_delegate_slots_are_not_requeued(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "callgraph.json"
            self.write_json(
                path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodeCount": 3,
                    "edgeCount": 0,
                    "nodes": [
                        {
                            "function": "0xf902440",
                            "seedName": "asyncpkg12",
                            "refs": [],
                            "indirectCalls": [{"instruction": "0xf9024d8", "text": "jmp 0x0f901ed1"}],
                        },
                        {
                            "function": "0x12de8ad0",
                            "seedName": "asyncpkg9",
                            "refs": [],
                            "indirectCalls": [{"instruction": "0x12de8cfd", "text": "jmp r8"}],
                        },
                        {
                            "function": "0x12de9160",
                            "seedName": "asyncpkg9",
                            "refs": [],
                            "indirectCalls": [{"instruction": "0x12de9677", "text": "call 0x12ab3050"}],
                        },
                    ],
                },
            )

            summary = module.summarize([("async", "callgraph", str(path))])

        route = summary["routes"][0]
        self.assertEqual(summary["decompileReviewQueueCount"], 0)
        self.assertEqual(route["metrics"]["knownNonPackageDispatchNodeCount"], 3)
        self.assertIn("ICU/Unicode decimal-format", " ".join(route["blockers"]))

    def test_package_loader_vtable_is_prioritized_before_streamable_callgraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "package.json"
            streamable_path = Path(tmp) / "streamable.json"
            self.write_json(
                package_path,
                {
                    "schemaVersion": "dune-elf-ue-package-loader-vtables/v1",
                    "rows": [
                        {
                            "demangled": "vtable for FLinkerLoad",
                            "executableSlots": [
                                {
                                    "candidateKind": "method",
                                    "index": 31,
                                    "value": "0x9b05000",
                                    "shape": {"hasCall": True},
                                }
                            ],
                        }
                    ],
                },
            )
            self.write_json(
                streamable_path,
                {
                    "schemaVersion": "dune-elf-ue-function-callgraph/v1",
                    "promotableAsPackageAnchor": False,
                    "packageAnchorNodeCount": 0,
                    "nodes": [
                        {
                            "function": "0xa54f700",
                            "seedName": "stslot0",
                            "indirectCalls": [
                                {
                                    "instruction": "0xa54f727",
                                    "text": "call qword ptr [rax + 0x10]",
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize(
                [
                    ("streamable", "callgraph", str(streamable_path)),
                    ("package", "package-loader-vtables", str(package_path)),
                ]
            )

        queue = summary["decompileReviewQueue"]
        self.assertEqual(queue[0]["address"], "0x9b05000")
        self.assertEqual(queue[0]["route"], "package")

    def test_reviewed_flinkerload_package_slots_are_not_requeued(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "package.json"
            self.write_json(
                package_path,
                {
                    "schemaVersion": "dune-elf-ue-package-loader-vtables/v1",
                    "rows": [
                        {
                            "demangled": "vtable for FLinkerLoad",
                            "executableSlots": [
                                {
                                    "candidateKind": "method",
                                    "index": 31,
                                    "value": "0x9b04600",
                                    "shape": {"hasCall": True},
                                }
                            ],
                        }
                    ],
                },
            )

            summary = module.summarize([("package", "package-loader-vtables", str(package_path))])

        self.assertEqual(summary["decompileReviewQueueCount"], 0)

    def test_method_route_review_is_reported_as_non_promotable_runtime_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "method-route-review.json"
            self.write_json(
                review_path,
                {
                    "schemaVersion": "dune-ue4ss-package-method-route-review/v1",
                    "methodHitCount": 5970,
                    "packageHitCount": 0,
                    "reviewedRoutes": [
                        {
                            "owner": "vtable for FLinkerLoad",
                            "slotIndex": "31",
                            "finding": "non-promotable",
                            "reason": "trivial accessor and archive/bit-writer route, not package loading",
                        }
                    ],
                },
            )

            summary = module.summarize([("runtime-method-route-review", "method-route-review", str(review_path))])

        route = summary["routes"][0]
        self.assertEqual(route["finding"], "negative")
        self.assertEqual(route["metrics"]["methodHitCount"], 5970)
        self.assertEqual(route["metrics"]["packageHitCount"], 0)
        self.assertEqual(route["metrics"]["nonPromotableRouteCount"], 1)
        self.assertIn("runtime method routes reviewed=1", route["summary"])
        self.assertIn("archive/bit-writer", route["blockers"][0])

    def test_missing_route_is_reported_as_missing(self):
        summary = module.summarize([("missing", "callgraph", "/tmp/does-not-exist-route.json")])

        self.assertEqual(summary["presentRouteCount"], 0)
        self.assertEqual(summary["routes"][0]["finding"], "missing")
        self.assertIn("missing artifact", summary["routes"][0]["blockers"])

    def test_markdown_includes_next_step_and_route_rows(self):
        summary = {
            "routeCount": 1,
            "presentRouteCount": 1,
            "promotableRouteCount": 0,
            "complete": False,
            "nextStep": "use decompile/runtime call-frame proof",
            "decompileReviewQueueCount": 1,
            "suppressedKnownNonPackageQueueCount": 1,
            "decompileReviewQueue": [
                {
                    "priority": 10,
                    "address": "0xfa631e0",
                    "kind": "decompile-rtti-vtable-slot",
                    "route": "raw-typeinfo",
                    "label": "package-loader-owner-function row 0 vtable 0 slot 0",
                    "reason": "decompile this function-object/vtable target",
                }
            ],
            "routes": [
                {
                    "finding": "negative",
                    "id": "raw-typeinfo",
                    "kind": "callgraph",
                    "path": "route.json",
                    "summary": "bounded callgraph packageAnchorNodeCount=0",
                    "blockers": ["indirect calls remain opaque"],
                }
            ],
            "suppressedKnownNonPackageQueue": [
                {
                    "address": "0x128ce8d0",
                    "kind": "suppressed-known-non-package-indirect-call-node",
                    "route": "kismet",
                    "label": "FLoadAssetActionBase_dispatch",
                    "reason": "owner-surface assert/log path",
                }
            ],
        }

        rendered = module.markdown(summary)

        self.assertIn("UE4SS Package Route Evidence", rendered)
        self.assertIn("use decompile/runtime call-frame proof", rendered)
        self.assertIn("raw-typeinfo", rendered)
        self.assertIn("packageAnchorNodeCount=0", rendered)
        self.assertIn("Decompile Review Queue", rendered)
        self.assertIn("Suppressed Known Non-Package Queue", rendered)
        self.assertIn("owner-surface assert/log path", rendered)
        self.assertIn("0xfa631e0", rendered)


if __name__ == "__main__":
    unittest.main()
