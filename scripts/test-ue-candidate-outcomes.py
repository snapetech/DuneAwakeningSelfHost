#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue-candidate-outcomes.py"

spec = importlib.util.spec_from_file_location("summarize_ue_candidate_outcomes", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class UeCandidateOutcomesTests(unittest.TestCase):
    def records_from_lines(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "loader.log"
            path.write_text("\n".join(lines), encoding="utf-8")
            return module.load_records(path)

    def test_classifies_null_empty_candidate_as_rejected(self):
        records = self.records_from_lines(
            [
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-candidate-global name=GWorld status=added address=0x100 imageOffset=0x200 absolute=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-pointer name=GWorld status=null anchor=0x100 value=0x0",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-object-array name=GWorld mode=direct status=empty base=0x100 chunks=0x0 maxElements=0 numElements=0",
            ]
        )

        summary = module.summarize(records, server_pid="343")

        self.assertEqual(summary["verdictCounts"], {"rejected": 1})
        self.assertEqual(summary["recommendationCounts"], {"reject-null-or-empty-global": 1})
        self.assertEqual(summary["candidates"][0]["reasons"]["pointer-null"], 1)
        self.assertEqual(summary["candidates"][0]["reasons"]["object-array-empty"], 1)

    def test_classifies_executable_pointer_zero_scan_as_weak_false_positive(self):
        records = self.records_from_lines(
            [
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0x100 imageOffset=0x200 absolute=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-pointer name=GUObjectArray status=target-mapped anchor=0x100 value=0x500 readable=true writable=false executable=true perms=r-xp",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-layout name=GUObjectArray status=target-readable anchor=0x100 target=0x500 slots=8 perms=r-xp",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-uobject name=GUObjectArray status=candidate anchor=0x100 target=0x500 vtableMapped=false classMapped=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-object-array name=GUObjectArray mode=direct status=finished base=0x100 scanned=0 registered=0",
            ]
        )

        summary = module.summarize(records, server_pid="343")

        self.assertEqual(summary["verdictCounts"], {"weak-false-positive": 1})
        self.assertEqual(summary["recommendationCounts"], {"reject-code-pointer-and-trace-caller-dataflow": 1})
        row = summary["candidates"][0]
        self.assertEqual(row["positives"]["pointer-target-mapped"], 1)
        self.assertEqual(row["reasons"]["pointer-target-executable"], 1)
        self.assertEqual(row["reasons"]["object-array-zero-scan"], 1)
        self.assertEqual(row["pointerTargets"][0]["value"], "0x500")
        self.assertEqual(row["uobjectTargets"][0]["classMapped"], "false")

    def test_classifies_registered_object_array_as_promotable(self):
        records = self.records_from_lines(
            [
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0x100 imageOffset=0x200 absolute=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-pointer name=GUObjectArray status=target-mapped anchor=0x100 value=0x500 readable=true writable=true executable=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-object-array name=GUObjectArray mode=direct status=finished base=0x100 scanned=32 registered=4",
            ]
        )

        summary = module.summarize(records, server_pid="343")

        self.assertEqual(summary["verdictCounts"], {"promotable": 1})
        self.assertEqual(summary["recommendationCounts"], {"promote-to-anchor-canary": 1})
        self.assertEqual(summary["candidates"][0]["positives"]["object-array-registered"], 1)

    def test_name_pool_ready_is_promising_despite_object_array_noise(self):
        records = self.records_from_lines(
            [
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-candidate-global name=FNamePool status=added address=0x100 imageOffset=0x1686df70 absolute=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-fname-start status=ready pool=0x100 source=FNamePool:direct",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-pointer name=FNamePool status=null anchor=0x100 value=0x0",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-object-array name=FNamePool mode=direct status=empty base=0x100 chunks=0x0 maxElements=0 numElements=0",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-fname-finish status=ready pool=0x100 source=FNamePool:direct",
            ]
        )

        summary = module.summarize(records, server_pid="343")

        self.assertEqual(summary["verdictCounts"], {"promising": 1})
        self.assertEqual(summary["recommendationCounts"], {"rerun-with-deeper-fname-or-reflection-probes": 1})
        row = summary["candidates"][0]
        self.assertEqual(row["positives"]["fname-pool-ready"], 2)
        self.assertEqual(row["reasons"]["pointer-null"], 1)
        self.assertEqual(row["reasons"]["object-array-empty"], 1)
        self.assertEqual(row["fnameStartStatuses"], {"ready": 1})
        self.assertEqual(row["fnameFinishStatuses"], {"ready": 1})

    def test_anchor_addr_records_attach_to_candidate(self):
        records = self.records_from_lines(
            [
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0x100 imageOffset=0x200 absolute=false",
                "2026-06-18T18:15:06+0000 pid=343 loader=server event=ue-anchor name=GUObjectArray group=objects status=mapped addr=0x100 readable=true writable=false executable=false imageOffset=0x200 fileOffset=0x1200 perms=r--p",
            ]
        )

        summary = module.summarize(records, server_pid="343")

        self.assertEqual(summary["candidates"][0]["anchorTargets"][0]["fileOffset"], "0x1200")

    def test_runtime_discovery_ambiguous_candidates_feed_rejection_offsets(self):
        records = self.records_from_lines(
            [
                "2026-06-19T04:33:24+0000 pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x563a07577a38 blockSlot=0x563a07577a48 firstBlock=0x5639f64e0dfc blocksOffset=0x10 stride=2 hit=1 targetImage=true imageOffset=0x1642aa38 fileOffset=0x16428a38 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
                "2026-06-19T04:33:24+0000 pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x563a07577a40 blockSlot=0x563a07577a50 firstBlock=0x5639f64a8e22 blocksOffset=0x10 stride=2 hit=2 targetImage=true imageOffset=0x1642aa40 fileOffset=0x16428a40 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
                "2026-06-19T04:33:27+0000 pid=337 loader=server event=ue-runtime-discovery name=RuntimeFNamePool status=ambiguous hits=2",
            ]
        )

        summary = module.summarize(records, server_pid="337")

        self.assertEqual(summary["verdictCounts"], {"weak-false-positive": 2})
        self.assertEqual(summary["recommendationCounts"], {"reject-runtime-auto-discovery-candidate": 2})
        self.assertEqual(summary["nameCounts"], {"RuntimeFNamePool": 2})
        self.assertEqual(summary["candidates"][0]["source"], "runtime-discovery")
        self.assertEqual(summary["candidates"][0]["reasons"]["runtime-discovery-final-ambiguous"], 1)
        self.assertEqual(summary["candidates"][0]["imageOffset"], "0x1642aa38")
        self.assertEqual(summary["candidates"][0]["fileOffset"], "0x16428a38")
        self.assertEqual(summary["candidates"][0]["targetImage"], "true")
        self.assertEqual(summary["candidates"][0]["perms"], "rw-p")
        self.assertIn("DuneSandboxServer-Linux-Shipping", summary["candidates"][0]["map"])

    def test_candidate_global_rwfile_metadata_is_preserved(self):
        records = self.records_from_lines(
            [
                "2026-06-19T04:33:24+0000 pid=337 loader=server event=ue-candidate-global name=RuntimeGUObjectArray status=added address=0x7f000028c4c0 imageOffset=0x28c4c0 absolute=false runtimeRwFileOffset=true",
                "2026-06-19T04:33:24+0000 pid=337 loader=server event=ue-object-array name=RuntimeGUObjectArray mode=direct status=finished base=0x7f000028c4c0 scanned=32 registered=4",
            ]
        )

        summary = module.summarize(records, server_pid="337")

        row = summary["candidates"][0]
        self.assertEqual(row["verdict"], "promotable")
        self.assertEqual(row["runtimeRwFileOffset"], "true")
        self.assertEqual(row["imageOffset"], "0x28c4c0")

    def test_load_records_uses_packaged_sibling_scan_parser(self):
        original = module.SCAN_SUMMARY_SCRIPTS
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parser = tmp_path / "summarize-client-loader-scan.py"
            parser.write_text(
                "\n".join(
                    [
                        "def load_records(path):",
                        "    return [{'pid': '343', 'event': 'ue-candidate-global', 'name': 'GWorld', 'status': 'added', 'address': '0x100', 'imageOffset': '0x200'}]",
                    ]
                ),
                encoding="utf-8",
            )
            log = tmp_path / "loader.log"
            log.write_text("", encoding="utf-8")
            module.SCAN_SUMMARY_SCRIPTS = (tmp_path / "missing.py", parser)
            try:
                records = module.load_records(log)
            finally:
                module.SCAN_SUMMARY_SCRIPTS = original

        self.assertEqual(records[0]["name"], "GWorld")


if __name__ == "__main__":
    unittest.main()
