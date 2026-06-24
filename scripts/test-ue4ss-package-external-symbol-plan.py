#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-external-symbol-plan.py"

spec = importlib.util.spec_from_file_location("summarize_ue4ss_package_external_symbol_plan", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageExternalSymbolPlanTests(unittest.TestCase):
    def exhausted_evidence(self):
        return {
            "complete": False,
            "promotableRouteCount": 0,
            "decompileReviewQueueCount": 0,
            "routes": [
                {"id": "package-loader-vtables", "summary": "package-loader vtables=5"},
                {"id": "static-wrapper-candidates", "summary": "static wrappers executableSymbolCandidateCount=0"},
                {"id": "symbol-surface-callgraph", "summary": "bounded callgraph packageAnchorNodeCount=0"},
            ],
        }

    def test_build_plan_uses_external_symbol_path_when_queue_exhausted(self):
        plan = module.build_plan(self.exhausted_evidence(), "/tmp/missing-server", "/tmp/donor", [])

        self.assertEqual(plan["nextPath"], "external-symbol-or-runtime-trace")
        self.assertFalse(plan["binary"]["present"])
        self.assertIn("StaticLoadObject", plan["anchorFamilies"])
        self.assertIn("find-ue4ss-package-donors.py", plan["commands"]["findLocalDonors"])
        self.assertIn("summarize-ue4ss-package-donor-symbols.py /tmp/donor", plan["commands"]["summarizeDonorSymbols"])
        self.assertIn("--signature-bytes 96", plan["commands"]["summarizeDonorSymbols"])
        self.assertIn("candidate-validation", plan["commands"]["exportDonorCandidateValidation"])
        self.assertIn("--donor-candidate-validation-json build/server-ue4ss-package-donor-candidate-validation.json", plan["commands"]["validateTransferredSignature"])
        self.assertIn("> build/server-ue4ss-package-donor-target-validation.json", plan["commands"]["validateTransferredSignature"])
        self.assertIn("--validation-json build/server-ue4ss-package-donor-target-validation.json", plan["commands"]["exportPromotedManifest"])
        self.assertIn("--format anchor-signatures", plan["commands"]["exportPromotedManifest"])
        self.assertIn("nm -an --demangle /tmp/donor", plan["commands"]["listDonorSymbols"])
        self.assertIn("guarded LoadAsset or LoadClass", " ".join(plan["runtimeTraceTarget"]["acceptance"]))
        acceptance = plan["promotionAcceptance"]
        self.assertEqual(
            acceptance["schemaVersion"],
            "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        )
        self.assertTrue(acceptance["targetImageRequired"])
        self.assertTrue(acceptance["tracePidMatchRequired"])
        self.assertTrue(acceptance["sourceLogRequired"])
        self.assertIn("runtime-call-frame-trace", acceptance["acceptableProofPaths"])
        self.assertIn("async-package-vtable-method-only", acceptance["rejectProofKinds"])
        self.assertIn("--reviewed-abi", acceptance["requiredReviewFlags"]["common"])
        self.assertIn("--reviewed-class-root", acceptance["requiredReviewFlags"]["StaticLoadClass"])
        self.assertIn("--reviewed-tchar", acceptance["requiredReviewFlags"]["StaticLoadObject"])

    def test_build_plan_defers_when_local_queue_remains(self):
        evidence = self.exhausted_evidence()
        evidence["decompileReviewQueueCount"] = 2

        plan = module.build_plan(evidence, "/tmp/missing-server", "", [])

        self.assertEqual(plan["nextPath"], "finish queued local package-route evidence first")
        self.assertEqual(plan["commands"], {})

    def test_markdown_contains_donor_requirements_and_commands(self):
        plan = module.build_plan(self.exhausted_evidence(), "/tmp/missing-server", "/tmp/donor", [])

        text = module.markdown(plan)

        self.assertIn("UE4SS Package External Symbol Plan", text)
        self.assertIn("Required Donor", text)
        self.assertIn("Linux x86_64 SysV", text)
        self.assertIn("StaticLoadClass", text)
        self.assertIn("summarize-ue4ss-package-donor-symbols.py", text)
        self.assertIn("validate-elf-signatures.py", text)
        self.assertIn("Promotion Acceptance", text)
        self.assertIn("Trace PID match required: `true`", text)
        self.assertIn("async-package-vtable-method-only", text)

    def test_donor_search_summary_records_unusable_local_hits(self):
        donor_search = {
            "schemaVersion": "dune-ue4ss-package-donor-search/v1",
            "candidateCount": 2,
            "usableCandidateCount": 0,
            "sourceCandidateCount": 0,
            "nextStep": "provide an unstripped/symbolized Linux UE donor",
            "candidates": [
                {
                    "path": "/opt/liblldb.so",
                    "usable": False,
                    "anchorsPresent": ["ResolveName"],
                    "promotableSymbolCount": 7,
                    "completeAnchorFamilyCoverage": False,
                    "rejectionReason": "only ResolveName-like symbols were found",
                },
                {
                    "path": "/tmp/donor",
                    "usable": None,
                    "anchorsPresent": [],
                    "promotableSymbolCount": 0,
                },
            ],
        }

        plan = module.build_plan(self.exhausted_evidence(), "/tmp/missing-server", "", [], donor_search)
        text = module.markdown(plan)

        self.assertEqual(plan["donorSearch"]["candidateCount"], 2)
        self.assertEqual(plan["donorSearch"]["usableCandidateCount"], 0)
        self.assertEqual(plan["donorSearch"]["falsePositiveCandidateCount"], 1)
        self.assertEqual(plan["donorSearch"]["candidatePreview"][0]["path"], "/opt/liblldb.so")
        self.assertIn("ResolveName-like", plan["donorSearch"]["candidatePreview"][0]["rejectionReason"])
        self.assertIn("Local Donor Search", text)
        self.assertIn("Usable candidate count: `0`", text)
        self.assertIn("/opt/liblldb.so", text)
        self.assertIn("rejection:", text)

    def test_historical_string_seeds_are_trace_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "surface.md"
            path.write_text(
                "- `LoadPackage` source=`live-log` group=`package` role=`string` value=`0x5ae6260` section=`.rodata`\n",
                encoding="utf-8",
            )

            plan = module.build_plan(self.exhausted_evidence(), "/tmp/missing-server", "", [str(path)])

        self.assertEqual(plan["historicalStringSeeds"][0]["name"], "LoadPackage")
        self.assertEqual(plan["historicalStringSeeds"][0]["address"], "0x5ae6260")
        self.assertEqual(plan["historicalStringSeeds"][0]["promotion"], "non-promotable-string-only")
        self.assertEqual(len(plan["historicalStringSeeds"][0]["sources"]), 1)

    def test_cli_reads_evidence_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(self.exhausted_evidence()), encoding="utf-8")

            rc = module.main(["--evidence", str(path), "--binary", "/tmp/missing-server", "--format", "json"])

        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
