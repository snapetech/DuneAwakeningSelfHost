#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cluster-ue-root-recovery-queue.py"

spec = importlib.util.spec_from_file_location("cluster_ue_root_recovery_queue", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class UeRootRecoveryClusterTests(unittest.TestCase):
    def test_clusters_overlapping_ranges_with_same_source_family(self):
        queue = {
            "schemaVersion": "dune-ue-root-recovery-queue/v1",
            "binary": "/tmp/server",
            "queuedFunctionCount": 2,
            "rows": [
                {
                    "function": "0x10",
                    "fileOffset": "0x10",
                    "sourceName": ".init_array[1]",
                    "score": 10,
                    "usableWritableRefCount": 2,
                    "writeLikeRefCount": 1,
                    "sectionCounts": {".bss": 2},
                    "candidateTargets": [{"target": "0x1000"}, {"target": "0x1080"}],
                },
                {
                    "function": "0x20",
                    "fileOffset": "0x20",
                    "sourceName": ".init_array[2]",
                    "score": 20,
                    "usableWritableRefCount": 2,
                    "writeLikeRefCount": 2,
                    "sectionCounts": {".bss": 2},
                    "candidateTargets": [{"target": "0x1100"}, {"target": "0x1180"}],
                },
            ],
        }

        summary = module.summarize(queue, gap=0x100, limit=10)

        self.assertEqual(summary["clusterCount"], 1)
        self.assertEqual(summary["clusters"][0]["functionCount"], 2)
        self.assertEqual(summary["clusters"][0]["minTarget"], "0x1000")
        self.assertEqual(summary["clusters"][0]["maxTarget"], "0x1180")

    def test_does_not_merge_different_source_families(self):
        queue = {
            "rows": [
                {
                    "function": "0x10",
                    "fileOffset": "0x10",
                    "sourceName": ".init_array[1]",
                    "candidateTargets": [{"target": "0x1000"}],
                },
                {
                    "function": "0x20",
                    "fileOffset": "0x20",
                    "sourceName": "manual[2]",
                    "candidateTargets": [{"target": "0x1008"}],
                },
            ]
        }

        summary = module.summarize(queue, gap=0x100, limit=10)

        self.assertEqual(summary["clusterCount"], 2)


if __name__ == "__main__":
    unittest.main()
