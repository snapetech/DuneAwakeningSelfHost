#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "review-ue4ss-package-abi.py"


def load_module():
    spec = importlib.util.spec_from_file_location("abi_review", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(seed="StaticLoadClass", target_image=True):
    path_register = {
        "LoadPackage": "rsi",
        "LoadObject": "rsi",
        "StaticLoadObject": "rdx",
        "StaticLoadClass": "rdx",
        "ResolveName": "rsi",
    }.get(seed, "rdx")
    return {
        "schemaVersion": "dune-ue4ss-package-runtime-trace-evidence/v1",
        "sourceLog": "/tmp/trace.log",
        "sourceLogExists": True,
        "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
        "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
        "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        "sourceExternalPlan": "/tmp/external-plan.json",
        "pid": 4242,
        "imageRangeSource": "pid",
        "imageBase": "0x100000",
        "imageStart": "0x200000",
        "imageEnd": "0x7000000",
        "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
        "imagePerms": "r-xp",
        "tracePidMatchesRequested": True,
        "hits": [
            {
                "seed": seed,
                "targetImageCaller": target_image,
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "tracePidMatchesRequested": True,
                "traceAddressMatchesBase": True,
                "registers": {
                    "rdi": "0x1",
                    "rsi": "0x2",
                    "rdx": "0x3",
                    "rcx": "0x4",
                    "r8": "0x5",
                    "r9": "0x6",
                },
                "disassembly": ["0x5000:\tcall *%rax"],
                "registerMemory": {
                    path_register: [
                        "0x3:\t0x0000000000000041\t0x0000000000000000",
                        '0x3:\t"/Script/DuneProbe.TargetAsset"',
                    ]
                },
                "stack": ["0x7:\t0x1"],
            }
        ],
    }


def multi_hit_evidence():
    payload = evidence("LoadPackage")
    payload["hits"].append(
        {
            **evidence("StaticLoadClass")["hits"][0],
            "seed": "StaticLoadClass",
            "callerImageOffset": "0x7000",
        }
    )
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": 1,
            "seed": "StaticLoadClass",
            "reviewScore": 18,
        }
    ]
    return payload


def ranked_multi_hit_evidence():
    payload = evidence("LoadPackage")
    payload["hits"].append(
        {
            **evidence("LoadPackage")["hits"][0],
            "seed": "LoadPackage",
            "callerImageOffset": "0x9000",
        }
    )
    payload["familyCandidates"] = {
        "LoadPackage": {
            "hitIndex": 1,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    }
    payload["recommendedReview"] = {
        "hitIndex": 1,
        "seed": "LoadPackage",
        "reviewScore": 18,
    }
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": 1,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    ]
    return payload


def non_concrete_family_candidate_evidence():
    payload = evidence("LoadPackage")
    payload["familyCandidates"] = {
        "LoadPackage": {
            "hitIndex": 0,
            "seed": "LoadPackage",
            "missingCallFrameOffsets": [],
            "missingRequiredMemoryRegisters": ["rsi"],
            "reviewScore": 18,
        }
    }
    payload["concreteReviewPriority"] = []
    payload["recommendedReview"] = {}
    return payload


def malformed_auto_hit_index_evidence(hit_index):
    payload = evidence("LoadPackage")
    payload["recommendedReview"] = {
        "hitIndex": hit_index,
        "seed": "LoadPackage",
        "reviewScore": 18,
    }
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": hit_index,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    ]
    return payload


def concrete_priority_evidence():
    payload = evidence("LoadPackage")
    payload["hits"][0].pop("callerImageOffset")
    payload["hits"].append(
        {
            **evidence("LoadPackage")["hits"][0],
            "seed": "LoadPackage",
            "callerImageOffset": "0x9100",
            "ripImageOffset": "0x9000",
        }
    )
    payload["familyCandidates"] = {
        "LoadPackage": {
            "hitIndex": 0,
            "seed": "LoadPackage",
            "missingCallFrameOffsets": ["callerImageOffset"],
            "reviewScore": 16,
        }
    }
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": 1,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    ]
    return payload


class PackageAbiReviewTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_static_load_class_maps_sysv_register_roles(self):
        data = evidence("StaticLoadClass")
        data["sourceLogExists"] = True
        report = self.module.review(data)
        self.assertTrue(report["readyForManualAbiReview"])
        self.assertIs(report["sourceLogExists"], True)
        self.assertEqual(report["tracePid"], 4242)
        self.assertEqual(report["imageRangeSource"], "pid")
        self.assertEqual(report["imageBase"], "0x100000")
        self.assertEqual(report["imageStart"], "0x200000")
        self.assertEqual(report["imageEnd"], "0x7000000")
        self.assertEqual(report["imagePath"], "/srv/dune/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(report["imagePerms"], "r-xp")
        self.assertEqual(report["selectedHitSeed"], "StaticLoadClass")
        roles = {item["register"]: item["role"] for item in report["arguments"]}
        self.assertEqual(roles["rdi"], "BaseClass")
        self.assertEqual(roles["rdx"], "Name")
        arg = next(item for item in report["arguments"] if item["register"] == "rdx")
        self.assertEqual(arg["kind"], "pointer")
        self.assertTrue(arg["required"])
        self.assertTrue(arg["looksSane"])
        self.assertEqual(report["requiredSignature"], "UClass*(UClass*,UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*)")

    def test_cli_loaded_evidence_records_evidence_json_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace-evidence.json"
            payload = evidence("LoadPackage")
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

            loaded = self.module.load_trace_evidence(path)
            report = self.module.review(loaded, signature_family="LoadPackage")

        self.assertEqual(report["sourceEvidenceJson"], str(path))
        self.assertEqual(
            report["sourceEvidenceJsonSha256"],
            hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest(),
        )

    def test_cli_rejects_wrong_schema_trace_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "not-trace-evidence.json"
            payload = evidence("LoadPackage")
            payload["schemaVersion"] = "dune-ue4ss-package-runtime-trace-plan/v1"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                self.module.main([str(path), "--format", "json"])

        self.assertIn("expected 'dune-ue4ss-package-runtime-trace-evidence/v1'", str(raised.exception))

    def test_load_package_uses_shorter_signature(self):
        report = self.module.review(evidence("LoadPackage"))
        roles = [item["role"] for item in report["arguments"]]
        self.assertEqual(roles, ["Outer", "PackageName", "LoadFlags"])

    def test_auto_hit_index_selects_requested_signature_family(self):
        report = self.module.review(multi_hit_evidence(), hit_index="auto", signature_family="StaticLoadClass")
        self.assertEqual(report["hitIndex"], 1)
        self.assertEqual(report["requestedHitIndex"], "auto")
        self.assertEqual(report["signatureFamily"], "StaticLoadClass")
        self.assertEqual(report["callerImageOffset"], "0x7000")

    def test_auto_hit_index_uses_ranked_family_candidate(self):
        report = self.module.review(ranked_multi_hit_evidence(), hit_index="auto", signature_family="LoadPackage")
        self.assertEqual(report["hitIndex"], 1)
        self.assertEqual(report["callerImageOffset"], "0x9000")

    def test_auto_hit_index_prefers_concrete_review_priority(self):
        report = self.module.review(concrete_priority_evidence(), hit_index="auto", signature_family="LoadPackage")
        self.assertTrue(report["readyForManualAbiReview"])
        self.assertEqual(report["hitIndex"], 1)
        self.assertEqual(report["callerImageOffset"], "0x9100")
        self.assertNotIn("missing callerImageOffset call-frame provenance", report["blockers"])

    def test_auto_hit_index_rejects_non_concrete_family_candidate(self):
        with self.assertRaises(ValueError) as raised:
            self.module.review(
                non_concrete_family_candidate_evidence(),
                hit_index="auto",
                signature_family="LoadPackage",
            )

        self.assertIn(
            "no concrete runtime trace review candidate for signature family LoadPackage",
            str(raised.exception),
        )

    def test_auto_hit_index_rejects_malformed_concrete_candidate_index(self):
        for hit_index in (True, -1):
            with self.subTest(hit_index=hit_index):
                with self.assertRaises(ValueError) as raised:
                    self.module.review(
                        malformed_auto_hit_index_evidence(hit_index),
                        hit_index="auto",
                        signature_family="LoadPackage",
                    )

                self.assertIn(
                    "no concrete runtime trace review candidate for signature family LoadPackage",
                    str(raised.exception),
                )

    def test_explicit_hit_index_must_be_non_negative_integer(self):
        for hit_index in ("later", -1, True, None):
            with self.subTest(hit_index=hit_index):
                with self.assertRaises(ValueError) as raised:
                    self.module.review(
                        evidence("LoadPackage"),
                        hit_index=hit_index,
                        signature_family="LoadPackage",
                    )

                self.assertIn("hit index must be auto or a non-negative integer", str(raised.exception))

    def test_explicit_signature_family_must_match_known_hit_seed(self):
        report = self.module.review(evidence("LoadPackage"), hit_index=0, signature_family="StaticLoadClass")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "selected trace hit seed LoadPackage does not match signature family StaticLoadClass",
            report["blockers"],
        )

    def test_explicit_signature_family_must_match_unknown_hit_seed(self):
        data = evidence("LoadPackage")
        data["hits"][0]["seed"] = "LoadPackag"

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "selected trace hit seed LoadPackag does not match signature family LoadPackage",
            report["blockers"],
        )

    def test_missing_trace_hit_seed_blocks_abi_review(self):
        data = evidence("LoadPackage")
        data["hits"][0].pop("seed")

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("missing trace hit seed provenance", report["blockers"])

    def test_missing_source_log_blocks_abi_review(self):
        data = evidence("LoadPackage")
        data.pop("sourceLog")

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("missing runtime trace sourceLog provenance", report["blockers"])
        self.assertEqual(report["sourceEvidence"], "")

    def test_missing_source_log_file_blocks_abi_review(self):
        data = evidence("LoadPackage")
        data["sourceLogExists"] = False

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertEqual(report["sourceEvidence"], "/tmp/trace.log")
        self.assertIn("runtime trace sourceLog does not exist", report["blockers"])

    def test_missing_source_log_exists_blocks_abi_review(self):
        data = evidence("LoadPackage")
        data.pop("sourceLogExists")

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertEqual(report["sourceEvidence"], "/tmp/trace.log")
        self.assertIn("missing runtime trace sourceLogExists provenance", report["blockers"])

    def test_missing_hit_report_keeps_trace_target_identity(self):
        data = evidence("LoadPackage")
        data["hits"] = []

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertEqual(report["tracePid"], 4242)
        self.assertEqual(report["imageRangeSource"], "pid")
        self.assertEqual(report["imagePath"], "/srv/dune/DuneSandboxServer-Linux-Shipping")
        self.assertIn("no runtime trace hit available for ABI review", report["blockers"])

    def test_pointer_argument_reports_register_memory_snapshot(self):
        data = evidence("LoadPackage")
        data["sourceLogExists"] = True
        data["hits"][0]["registerMemory"] = {
            "rsi": [
                "0x3:\t0x0000000000000041\t0x0000000000000000",
                "0x3:\t0x2f\t0x47\t0x61\t0x6d\t0x65\t0x00\t0x00\t0x00",
                '0x3:\t"/Script/DuneProbe.TargetAsset"',
            ]
        }
        report = self.module.review(data, signature_family="LoadPackage")
        package_name = next(item for item in report["arguments"] if item["role"] == "PackageName")
        self.assertEqual(package_name["reviewCategory"], "path-or-name-pointer")
        self.assertTrue(package_name["memory"]["provided"])
        self.assertEqual(package_name["memory"]["lineCount"], 3)
        self.assertIn("/Script/DuneProbe.TargetAsset", package_name["memory"]["sample"][2])
        self.assertEqual(package_name["memory"]["hints"]["quotedStrings"], ["/Script/DuneProbe.TargetAsset"])
        self.assertIn(
            {"unitBytes": 1, "sample": "/Game"},
            package_name["memory"]["hints"]["candidateTcharLayouts"],
        )
        rendered = self.module.markdown(report)
        self.assertIn("Selected hit seed: `LoadPackage`", rendered)
        self.assertIn("Source log exists: `true`", rendered)
        self.assertIn("Caller image offset: `0x5000`", rendered)
        self.assertIn("RIP image offset: `0x4ff0`", rendered)
        self.assertIn("category=`path-or-name-pointer`", rendered)
        self.assertIn("memoryLines=`3`", rendered)
        self.assertIn("memory hint: candidateTcharLayouts=", rendered)

    def test_register_memory_hints_detect_utf16le_ascii_prefix(self):
        data = evidence("LoadPackage")
        data["hits"][0]["registerMemory"] = {
            "rsi": [
                "0x3:\t0x2f\t0x00\t0x47\t0x00\t0x61\t0x00\t0x6d\t0x00\t0x65\t0x00\t0x00\t0x00",
            ]
        }
        report = self.module.review(data, signature_family="LoadPackage")
        package_name = next(item for item in report["arguments"] if item["role"] == "PackageName")
        self.assertIn(
            {"unitBytes": 2, "sample": "/Game"},
            package_name["memory"]["hints"]["candidateTcharLayouts"],
        )

    def test_required_pointer_roles_must_be_non_null(self):
        data = evidence("LoadPackage")
        data["hits"][0]["registers"]["rsi"] = "0x0"
        report = self.module.review(data, signature_family="LoadPackage")
        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("required argument roles are missing or null: rsi:PackageName", report["blockers"])
        package_name = next(item for item in report["arguments"] if item["role"] == "PackageName")
        self.assertFalse(package_name["looksSane"])

    def test_required_path_pointer_roles_need_memory_snapshot(self):
        data = evidence("LoadPackage")
        data["hits"][0]["registerMemory"] = {}
        report = self.module.review(data, signature_family="LoadPackage")
        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "missing memory snapshot for path/name pointer arguments: rsi:PackageName",
            report["blockers"],
        )

    def test_malformed_register_memory_shape_blocks_review_without_crashing(self):
        cases = (
            (["not-object"], "registerMemory must be a JSON object"),
            ({"rsi": "0x3:\t0x2f"}, "registerMemory.rsi must be a JSON array"),
            ({"rsi": ["0x3:\t0x2f", 42]}, "registerMemory.rsi[1] must be a string"),
        )
        for register_memory, message in cases:
            with self.subTest(message=message):
                data = evidence("LoadPackage")
                data["hits"][0]["registerMemory"] = register_memory

                report = self.module.review(data, signature_family="LoadPackage")

                self.assertFalse(report["readyForManualAbiReview"])
                self.assertIn(message, report["blockers"])

    def test_malformed_selected_hit_context_shape_blocks_review_without_crashing(self):
        cases = (
            ("registers", ["not-object"], "runtime trace hit 0 registers must be a JSON object"),
            ("registers", {"": "0x0"}, "runtime trace hit 0 registers contains an invalid register key"),
            ("registers", {"rsi": 42}, "runtime trace hit 0 registers.rsi must be a string"),
            (
                "missingRequiredMemoryRegisters",
                "rsi",
                "runtime trace hit 0 missingRequiredMemoryRegisters must be a JSON array",
            ),
            (
                "missingRequiredMemoryRegisters",
                ["rsi", 42],
                "runtime trace hit 0 missingRequiredMemoryRegisters[1] must be a string",
            ),
            ("disassembly", "not-array", "runtime trace hit 0 disassembly must be a JSON array"),
            ("stack", "not-array", "runtime trace hit 0 stack must be a JSON array"),
            ("backtrace", "not-array", "runtime trace hit 0 backtrace must be a JSON array"),
            ("parseWarnings", "not-array", "runtime trace hit 0 parseWarnings must be a JSON array"),
        )
        for key, value, message in cases:
            with self.subTest(message=message):
                data = evidence("LoadPackage")
                data["hits"][0][key] = value

                report = self.module.review(data, signature_family="LoadPackage")

                self.assertFalse(report["readyForManualAbiReview"])
                self.assertIn(message, report["blockers"])

    def test_missing_required_memory_registers_block_manual_abi_review(self):
        data = evidence("LoadPackage")
        data["hits"][0]["missingRequiredMemoryRegisters"] = ["rsi"]

        report = self.module.review(data, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "runtime trace hit 0 is missing required memory registers: rsi",
            report["blockers"],
        )

    def test_optional_pointer_roles_may_be_null(self):
        data = evidence("StaticLoadClass")
        data["hits"][0]["registers"]["rsi"] = ""
        data["hits"][0]["registers"]["rcx"] = "0x0"
        data["hits"][0]["registers"]["r9"] = ""
        report = self.module.review(data, signature_family="StaticLoadClass")
        self.assertTrue(report["readyForManualAbiReview"])
        optional = {item["role"]: item for item in report["arguments"] if item["role"] in {"Outer", "Filename", "Sandbox"}}
        self.assertFalse(optional["Outer"]["required"])
        self.assertTrue(optional["Filename"]["nullAllowed"])

    def test_markdown_includes_argument_sanity(self):
        rendered = self.module.markdown(self.module.review(evidence("StaticLoadClass")))
        self.assertIn("kind=`pointer`", rendered)
        self.assertIn("required=`true`", rendered)
        self.assertIn("sane=`true`", rendered)

    def test_static_load_object_reads_stack_tail_argument(self):
        data = evidence("StaticLoadObject")
        data["hits"][0]["stack"] = ["0x7fffffffd000:\t0x400001 0x1 0x0"]
        report = self.module.review(data, signature_family="StaticLoadObject")
        self.assertTrue(report["readyForManualAbiReview"])
        detail = report["stackArgumentDetails"][0]
        self.assertEqual(detail["slot"], 1)
        self.assertEqual(detail["role"], "AllowObjectReconciliation")
        self.assertEqual(detail["capturedValue"], "0x1")
        self.assertTrue(detail["looksSane"])

    def test_missing_static_load_object_stack_tail_blocks_review(self):
        data = evidence("StaticLoadObject")
        data["hits"][0]["stack"] = ["0x7fffffffd000:\t0x400001"]
        report = self.module.review(data, signature_family="StaticLoadObject")
        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "required stack argument roles are missing or null: stack[1]:AllowObjectReconciliation",
            report["blockers"],
        )

    def test_markdown_includes_stack_argument_sanity(self):
        data = evidence("StaticLoadObject")
        data["hits"][0]["stack"] = ["0x7fffffffd000:\t0x400001 0x1"]
        rendered = self.module.markdown(self.module.review(data, signature_family="StaticLoadObject"))
        self.assertIn("slot `1` `AllowObjectReconciliation` = `0x1`", rendered)
        self.assertIn("kind=`scalar`", rendered)

    def test_missing_hit_blocks_review(self):
        report = self.module.review({"sourceLog": "/tmp/missing.log", "hits": []})
        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("no runtime trace hit available for ABI review", report["blockers"])

    def test_missing_auto_hit_blocks_review_without_crashing(self):
        report = self.module.review(
            {"sourceLog": "/tmp/missing.log", "hits": []},
            hit_index="auto",
            signature_family="LoadPackage",
        )

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertEqual(report["hitIndex"], 0)
        self.assertEqual(report["requestedHitIndex"], "auto")
        self.assertIn("no runtime trace hit available for ABI review", report["blockers"])

    def test_non_array_hits_block_review_without_crashing(self):
        data = evidence("LoadPackage")
        data["hits"] = {}

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("runtime trace hits must be a JSON array", report["blockers"])
        self.assertIn("no runtime trace hit available for ABI review", report["blockers"])

    def test_non_object_selected_hit_blocks_review_without_crashing(self):
        data = evidence("LoadPackage")
        data["hits"] = [[]]

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("runtime trace hit 0 must be a JSON object", report["blockers"])
        self.assertIn("selected runtime trace hit must be a JSON object", report["blockers"])

    def test_non_object_recommended_review_blocks_auto_review_without_crashing(self):
        data = ranked_multi_hit_evidence()
        data["recommendedReview"] = []

        report = self.module.review(data, hit_index="auto", signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("recommendedReview must be a JSON object", report["blockers"])

    def test_non_array_concrete_review_priority_blocks_auto_review_without_crashing(self):
        data = ranked_multi_hit_evidence()
        data["recommendedReview"] = {}
        data["concreteReviewPriority"] = {}

        with self.assertRaises(ValueError) as raised:
            self.module.review(data, hit_index="auto", signature_family="LoadPackage")

        self.assertIn("no concrete runtime trace review candidate", str(raised.exception))

    def test_missing_armed_session_blocks_direct_abi_review(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                data = evidence("LoadPackage")
                data["armedCount"] = 0
                data["hits"][0]["traceLogHasArmed"] = stale_value

                report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(report["readyForManualAbiReview"])
                self.assertIn("missing trace armed record; cannot prove runtime trace session", report["blockers"])
                self.assertIn(
                    "runtime trace hit 0 missing trace armed record; cannot prove runtime trace session",
                    report["blockers"],
                )

    def test_multiple_armed_sessions_block_direct_abi_review(self):
        data = evidence("LoadPackage")
        data["armedCount"] = 2

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("multiple trace armed records; use a fresh single-session trace log", report["blockers"])

    def test_stale_trace_pid_session_blocks_direct_abi_review(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                data = evidence("LoadPackage")
                data["tracePidMatchesRequested"] = stale_value
                data["hits"][0]["tracePidMatchesRequested"] = stale_value

                report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(report["readyForManualAbiReview"])
                self.assertIn("trace log armed PID does not match requested runtime PID", report["blockers"])
                self.assertIn(
                    "runtime trace hit 0 trace log armed PID does not match requested runtime PID",
                    report["blockers"],
                )

    def test_bad_hit_address_base_provenance_blocks_direct_abi_review(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                data = evidence("LoadPackage")
                data["hits"][0]["traceAddressMatchesBase"] = stale_value

                report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(report["readyForManualAbiReview"])
                self.assertIn(
                    "runtime trace hit 0 address does not match image base plus seed imageOffset",
                    report["blockers"],
                )
                self.assertIn(
                    "selected runtime trace hit address does not match image base plus seed imageOffset",
                    report["blockers"],
                )

    def test_missing_hit_address_base_provenance_blocks_direct_abi_review(self):
        data = evidence("LoadPackage")
        data["hits"][0].pop("traceAddressMatchesBase", None)

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "runtime trace hit 0 address does not match image base plus seed imageOffset",
            report["blockers"],
        )
        self.assertIn(
            "selected runtime trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_missing_trace_pid_match_provenance_blocks_direct_abi_review(self):
        data = evidence("LoadPackage")
        data.pop("tracePidMatchesRequested", None)
        data["hits"][0].pop("tracePidMatchesRequested", None)

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("missing runtime trace PID match provenance", report["blockers"])
        self.assertIn("selected runtime trace hit is missing PID match provenance", report["blockers"])

    def test_missing_trace_plan_acceptance_schema_blocks_direct_abi_review(self):
        data = evidence("LoadPackage")
        data.pop("sourcePromotionAcceptanceSchemaVersion")

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn(
            "runtime trace evidence missing current package promotion acceptance schema provenance",
            report["blockers"],
        )

    def test_target_image_blocker_is_reported(self):
        report = self.module.review(evidence("StaticLoadClass", target_image=False))
        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("caller is not proven inside target image", report["blockers"])

    def test_missing_caller_image_offset_blocks_review(self):
        data = evidence("StaticLoadClass")
        data["hits"][0].pop("callerImageOffset")
        report = self.module.review(data)

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("missing callerImageOffset call-frame provenance", report["blockers"])

    def test_missing_rip_image_offset_blocks_review(self):
        data = evidence("StaticLoadClass")
        data["hits"][0].pop("ripImageOffset")
        report = self.module.review(data)

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("missing ripImageOffset call-frame provenance", report["blockers"])

    def test_multiline_trace_provenance_blocks_review(self):
        data = evidence("LoadPackage")
        data["sourceLog"] = "/tmp/trace.log\nold"
        data["imagePath"] = "/srv/dune/DuneSandboxServer-Linux-Shipping\nold"
        data["hits"][0]["callerImageOffset"] = "0x5000\nold"

        report = self.module.review(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(report["readyForManualAbiReview"])
        self.assertIn("sourceLog provenance must be a non-empty single-line value", report["blockers"])
        self.assertIn("imagePath provenance must be a non-empty single-line value", report["blockers"])
        self.assertIn("callerImageOffset provenance must be a non-empty single-line value", report["blockers"])


if __name__ == "__main__":
    unittest.main()
