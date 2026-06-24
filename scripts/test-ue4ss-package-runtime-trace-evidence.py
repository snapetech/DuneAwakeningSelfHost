#!/usr/bin/env python3
import importlib.util
import os
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-runtime-trace-evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("trace_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageRuntimeTraceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_log(self, body):
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        tmp.write(body)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def write_trace_plan(self):
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        json.dump(
            {
                "schemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            },
            tmp,
        )
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_empty_log_keeps_route_incomplete(self):
        log = self.write_log("")
        summary = self.module.build_summary(log)
        self.assertTrue(summary["sourceLogExists"])
        self.assertEqual(summary["sourceLogSha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(summary["hitCount"], 0)
        self.assertFalse(summary["completePackageRoute"])
        self.assertIn("arm package runtime trace", summary["nextStep"])

    def test_missing_log_is_incomplete_not_exception(self):
        missing = Path(tempfile.gettempdir()) / "missing-ue4ss-package-trace.log"
        missing.unlink(missing_ok=True)
        summary = self.module.build_summary(missing)
        self.assertFalse(summary["sourceLogExists"])
        self.assertEqual(summary["sourceLogSha256"], "")
        self.assertEqual(summary["hitCount"], 0)
        self.assertFalse(summary["completePackageRoute"])

    def test_trace_plan_provenance_is_copied_into_evidence(self):
        log = self.write_log("")
        trace_plan = self.write_trace_plan()
        summary = self.module.build_summary(log, trace_plan=trace_plan)

        self.assertEqual(summary["sourceTracePlan"], str(trace_plan))
        self.assertEqual(summary["sourceTracePlanSchemaVersion"], "dune-ue4ss-package-runtime-trace-plan/v1")
        self.assertEqual(
            summary["sourcePromotionAcceptanceSchemaVersion"],
            "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        )
        self.assertEqual(summary["sourceExternalPlan"], "/tmp/external-plan.json")
        rendered = self.module.markdown(summary)
        self.assertIn("Source trace plan", rendered)
        self.assertIn("dune-ue4ss-package-anchor-promotion-acceptance/v1", rendered)

    def test_hit_is_parsed_with_registers_and_caller_offsets(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x0000000000000041\t0x0000000000000000\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            '0x2:\t"AssetName"\n'
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        self.assertEqual(summary["armedCount"], 1)
        self.assertEqual(summary["hitCount"], 1)
        hit = summary["hits"][0]
        self.assertEqual(hit["seed"], "LoadPackage")
        self.assertEqual(hit["registers"]["rdi"], "0x1")
        self.assertEqual(hit["caller"]["ip"], "0x6001234")
        self.assertEqual(hit["callerImageOffset"], "0x5f01234")
        self.assertEqual(len(hit["disassembly"]), 1)
        self.assertEqual(len(hit["stack"]), 1)
        self.assertTrue(hit["targetImageCaller"])
        self.assertTrue(hit["targetImageRip"])
        self.assertFalse(hit["promotable"])
        self.assertIn("manual ABI review required before promotion", hit["blockers"])
        self.assertEqual(hit["backtrace"][1]["imageOffset"], "0x5f01234")
        self.assertTrue(hit["backtrace"][1]["targetImage"])
        self.assertIn("rsi", hit["registerMemory"])
        self.assertEqual(len(hit["registerMemory"]["rsi"]), 3)

        rendered = self.module.markdown(summary)
        self.assertIn("Trace PID matches requested: `true`", rendered)
        self.assertIn("registerMemory: rsi:3", rendered)

    def test_method_hit_is_parsed_as_non_promotable_route_evidence(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=2\n"
            "UE4SS_PACKAGE_METHOD_TRACE_HIT imageOffset=0x9b04600 addr=0x9c04600 "
            'slot=31 owner="vtable for FLinkerLoad" '
            "rip=0x9c04600 rdi=0x7f00 rsi=(nil) rdx=0x8 rcx=0x8 "
            "r8=0x3 r9=0x1 rsp=0x7ffee000 rbp=0x7ffee010\n"
            "UE4SS_PACKAGE_METHOD_TRACE_DISASM_BEGIN\n"
            "=> 0x9c04600:\tpush %rbp\n"
            "UE4SS_PACKAGE_METHOD_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_METHOD_TRACE_STACK_BEGIN\n"
            "0x7ffee000:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_METHOD_TRACE_STACK_END\n"
            "#0  0x9c04600 in ?? ()\n"
            "#1  0xa001234 in ?? ()\n"
        )

        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x12000000, base=0x100000, pid=123)

        self.assertEqual(summary["hitCount"], 0)
        self.assertEqual(summary["methodHitCount"], 1)
        self.assertEqual(summary["promotableHitCount"], 0)
        self.assertIn("review method probe caller route", summary["nextStep"])
        method_hit = summary["methodHits"][0]
        self.assertEqual(method_hit["owner"], "vtable for FLinkerLoad")
        self.assertEqual(method_hit["slotIndex"], "31")
        self.assertEqual(method_hit["ripImageOffset"], "0x9b04600")
        self.assertEqual(method_hit["callerImageOffset"], "0x9f01234")
        self.assertFalse(method_hit["promotable"])
        self.assertIn("method probes are route-recovery evidence only", " ".join(method_hit["blockers"]))

        rendered = self.module.markdown(summary)
        self.assertIn("Method hits: `1`", rendered)
        self.assertIn("Method Hits", rendered)
        self.assertIn("vtable for FLinkerLoad", rendered)

    def test_route_hit_is_parsed_as_non_promotable_route_evidence(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=2\n"
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT imageOffset=0xf94711c addr=0xfa4711c "
            "rip=0xfa4711c rdi=0x7f00 rsi=(nil) rdx=0x8 rcx=0x8 "
            "r8=0x3 r9=0x1 rsp=0x7ffee000 rbp=0x7ffee010\n"
            "UE4SS_PACKAGE_ROUTE_TRACE_DISASM_BEGIN\n"
            "=> 0xfa4711c:\tcall *%rax\n"
            "UE4SS_PACKAGE_ROUTE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_ROUTE_TRACE_STACK_BEGIN\n"
            "0x7ffee000:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_ROUTE_TRACE_STACK_END\n"
            "#0  0xfa4711c in ?? ()\n"
            "#1  0xfa492bc in ?? ()\n"
        )

        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x12000000, base=0x100000, pid=123)

        self.assertEqual(summary["hitCount"], 0)
        self.assertEqual(summary["routeHitCount"], 1)
        self.assertEqual(summary["promotableHitCount"], 0)
        self.assertIn("review route probe caller chain", summary["nextStep"])
        route_hit = summary["routeHits"][0]
        self.assertEqual(route_hit["ripImageOffset"], "0xf94711c")
        self.assertEqual(route_hit["callerImageOffset"], "0xf9492bc")
        self.assertEqual(route_hit["registers"]["rbx"], "")
        self.assertFalse(route_hit["promotable"])
        self.assertIn("route probes are route-recovery evidence only", " ".join(route_hit["blockers"]))
        self.assertFalse(summary["routeSlotRecovery"]["ready"])
        self.assertEqual(summary["routeSlotRecovery"]["routeHitCount"], 1)
        self.assertEqual(summary["routeSlotRecovery"]["matchCount"], 0)
        self.assertEqual(summary["routeSlotRecovery"]["missingSlots"], ["0x3a0", "0x3d8"])
        self.assertIn("missing route vtable static slot matches: 0x3a0, 0x3d8", summary["routeSlotRecovery"]["blockers"])

        rendered = self.module.markdown(summary)
        self.assertIn("Route hits: `1`", rendered)
        self.assertIn("Route slot recovery ready: `false`", rendered)
        self.assertIn("Blocker: missing route vtable static slot matches: 0x3a0, 0x3d8", rendered)
        self.assertIn("Route Hits", rendered)
        self.assertIn("0xfa4711c", rendered)

    def test_route_hit_parses_callee_saved_registers_for_vtable_review(self):
        vtable_rows = []
        for row in range(0, 128, 2):
            left = 0x600000 + (row * 8)
            first = 0x100000 + (row * 0x10)
            second = 0x100000 + ((row + 1) * 0x10)
            if row == 116:
                first = 0x129993c0
                second = 0x129d5880
            if row == 122:
                second = 0x129d5880
            vtable_rows.append(f"0x{left:x}:\t0x{first:016x}\t0x{second:016x}\n")
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=2\n"
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT imageOffset=0x129d58a2 addr=0x12ad58a2 "
            "rip=0x12ad58a2 rdi=0x7f00 rsi=(nil) rdx=0x8 rcx=0x8 "
            "r8=0x3 r9=0x1 rbx=0x501000 r12=0x12 r13=0x13 r14=0x14 r15=0x15 "
            "rsp=0x7ffee000 rbp=0x7ffee010\n"
            "UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=rbx\n"
            "0x501000:\t0x0000000000600000\t0x0000000000000001\n"
            "UE4SS_PACKAGE_ROUTE_OBJECT_END reg=rbx\n"
            "UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg=rbx\n"
            + "".join(vtable_rows) +
            "UE4SS_PACKAGE_ROUTE_VTABLE_END reg=rbx\n"
            "UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=r14\n"
            "0x14:\tCannot access memory at address 0x14\n"
            "UE4SS_PACKAGE_ROUTE_OBJECT_END reg=r14\n"
            "#0  0x12ad58a2 in ?? ()\n"
            "#1  0x12affaf2 in ?? ()\n"
        )

        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x14000000, base=0x100000, pid=123)

        route_hit = summary["routeHits"][0]
        self.assertEqual(route_hit["registers"]["rbx"], "0x501000")
        self.assertEqual(route_hit["registers"]["r12"], "0x12")
        self.assertEqual(route_hit["registers"]["r13"], "0x13")
        self.assertEqual(route_hit["registers"]["r14"], "0x14")
        self.assertEqual(route_hit["registers"]["r15"], "0x15")
        self.assertEqual(route_hit["routeObjectMemory"]["rbx"][0], "0x501000:\t0x0000000000600000\t0x0000000000000001")
        self.assertEqual(route_hit["routeVtableMemory"]["rbx"][0], "0x600000:\t0x0000000000100000\t0x0000000000100010")
        self.assertIn("Cannot access memory", route_hit["routeObjectMemory"]["r14"][0])
        self.assertEqual(route_hit["callerImageOffset"], "0x129ffaf2")
        static_matches = route_hit["routeVtableStaticSlotMatches"]
        self.assertEqual([match["slotOffset"] for match in static_matches], ["0x3a0", "0x3d8"])
        self.assertEqual(static_matches[0]["name"], "child-dispatch-slot-0x3a0")
        self.assertEqual(static_matches[0]["targetImageOffset"], "0x128993c0")
        self.assertEqual(static_matches[1]["name"], "wrapper-dispatch-slot-0x3d8")
        self.assertEqual(static_matches[1]["targetImageOffset"], "0x128d5880")
        self.assertEqual(route_hit["routeVtableSlots"]["rbx"][116]["slotOffset"], "0x3a0")
        self.assertEqual(route_hit["routeVtableSlots"]["rbx"][123]["slotOffset"], "0x3d8")
        self.assertTrue(summary["routeSlotRecovery"]["ready"], summary["routeSlotRecovery"]["blockers"])
        self.assertEqual(summary["routeSlotRecovery"]["presentSlots"], ["0x3a0", "0x3d8"])
        self.assertEqual(summary["routeSlotRecovery"]["missingSlots"], [])
        self.assertEqual(summary["routeSlotRecovery"]["matchCount"], 2)
        self.assertEqual(summary["routeSlotRecovery"]["matches"][0]["hitIndex"], 0)

    def test_armed_record_base_supports_offline_image_offsets(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log)
        hit = summary["hits"][0]

        self.assertEqual(summary["imageBase"], "0x100000")
        self.assertEqual(summary["pid"], 123)
        self.assertEqual(hit["ripImageOffset"], "0x5ae7000")
        self.assertEqual(hit["callerImageOffset"], "0x5f01234")

    def test_explicit_pid_overrides_armed_record_pid(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
        )
        summary = self.module.build_summary(log, pid=456)

        self.assertEqual(summary["pid"], 456)
        self.assertEqual(summary["armedPid"], 123)
        self.assertFalse(summary["tracePidMatchesRequested"])

    def test_stale_armed_pid_does_not_satisfy_concrete_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=456)
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertFalse(summary["tracePidMatchesRequested"])
        self.assertFalse(summary["hits"][0]["tracePidMatchesRequested"])
        self.assertIn("trace log armed PID does not match requested runtime PID", summary["hits"][0]["blockers"])
        self.assertIn("trace log armed PID does not match requested runtime PID", candidate["shapeBlockers"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])

    def test_missing_requested_pid_does_not_satisfy_concrete_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertIsNone(summary["tracePidMatchesRequested"])
        self.assertIsNone(summary["hits"][0]["tracePidMatchesRequested"])
        self.assertIn("missing requested runtime PID match provenance", summary["hits"][0]["blockers"])
        self.assertIn("missing requested runtime PID match provenance", candidate["shapeBlockers"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])
        self.assertIn("Trace PID matches requested: `none`", self.module.markdown(summary))

    def test_missing_armed_record_does_not_satisfy_concrete_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertEqual(summary["armedCount"], 0)
        self.assertFalse(summary["hits"][0]["traceLogHasArmed"])
        self.assertIn("missing trace armed record; cannot prove runtime trace session", summary["hits"][0]["blockers"])
        self.assertIn("missing trace armed record; cannot prove runtime trace session", candidate["shapeBlockers"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])

    def test_multiple_armed_records_do_not_satisfy_concrete_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertEqual(summary["armedCount"], 2)
        self.assertEqual(summary["hits"][0]["traceArmedCount"], 2)
        self.assertIn("multiple trace armed records; use a fresh single-session trace log", summary["hits"][0]["blockers"])
        self.assertIn("multiple trace armed records; use a fresh single-session trace log", candidate["shapeBlockers"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])

    def test_hit_address_must_match_base_plus_seed_offset(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x7be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000)
        hit = summary["hits"][0]
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertFalse(hit["traceAddressMatchesBase"])
        self.assertEqual(hit["ripImageOffset"], "")
        self.assertEqual(hit["callerImageOffset"], "")
        self.assertIn("traceAddressMatchesBase", candidate["missingCallFrameOffsets"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertIn(
            "trace hit address does not match image base plus seed imageOffset",
            hit["blockers"],
        )

    def test_first_target_image_backtrace_frame_is_selected_as_caller(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x7ffff7f00123 in libpthread.so ()\n"
            "#2  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        hit = summary["hits"][0]
        self.assertEqual(hit["caller"]["index"], 2)
        self.assertEqual(hit["caller"]["ip"], "0x6001234")
        self.assertEqual(hit["callerImageOffset"], "0x5f01234")
        self.assertFalse(hit["backtrace"][1]["targetImage"])
        self.assertTrue(hit["backtrace"][2]["targetImage"])
        self.assertTrue(hit["targetImageCaller"])

    def test_family_candidates_report_first_hit_for_each_signature_family(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=2\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=StaticLoadClass imageOffset=0x6ae6260 "
            "addr=0x6be6260 rip=0x6be7000 rdi=0x10 rsi=0x20 rdx=0x30 rcx=0x40 "
            "r8=0x50 r9=0x60 rsp=0x70 rbp=0x80\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x6be7000:\tmov %rsi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rdx\n"
            "0x30:\t0x0000000000000041\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rdx\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x70:\t0x0000000000000003\t0x0000000000000004\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x6be7000 in ?? ()\n"
            "#1  0x6101234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        candidates = summary["familyCandidates"]
        self.assertEqual(candidates["LoadPackage"]["hitIndex"], 0)
        self.assertEqual(candidates["StaticLoadClass"]["hitIndex"], 1)
        self.assertEqual(candidates["StaticLoadClass"]["registerMemoryRegisters"], ["rdx"])
        self.assertEqual(candidates["StaticLoadClass"]["missingRequiredMemoryRegisters"], [])
        self.assertTrue(candidates["StaticLoadClass"]["targetImageCaller"])
        self.assertTrue(candidates["StaticLoadClass"]["targetImageRip"])
        self.assertEqual(summary["recommendedReview"]["seed"], "StaticLoadClass")
        self.assertEqual(summary["recommendedReview"]["hitIndex"], 1)
        self.assertEqual(summary["reviewPriority"][0]["seed"], "StaticLoadClass")

        rendered = self.module.markdown(summary)
        self.assertIn("## Family Candidates", rendered)
        self.assertIn("Recommended review: `StaticLoadClass`", rendered)
        self.assertIn("`StaticLoadClass` hitIndex=`1`", rendered)
        self.assertIn("targetImageRip=`True`", rendered)

    def test_family_candidates_keep_best_hit_for_same_signature_family(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x7ffff7f00123 in libc.so ()\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be8000 rdi=0x10 rsi=0x20 rdx=0x30 rcx=0x40 "
            "r8=0x50 r9=0x60 rsp=0x70 rbp=0x80\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be8000:\tmov %rsi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x20:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x70:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be8000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertEqual(candidate["hitIndex"], 1)
        self.assertEqual(candidate["missingRequiredMemoryRegisters"], [])
        self.assertTrue(candidate["targetImageCaller"])
        self.assertEqual(summary["recommendedReview"]["hitIndex"], 1)

    def test_unsupported_trace_seed_is_blocked_and_not_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=1\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=UnknownPackagePath imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)

        self.assertEqual(summary["hitCount"], 1)
        self.assertIn("unsupported package trace seed: UnknownPackagePath", summary["hits"][0]["blockers"])
        self.assertEqual(summary["familyCandidates"], {})
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])

    def test_unterminated_capture_does_not_swallow_next_hit(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=StaticLoadClass imageOffset=0x6ae6260 "
            "addr=0x6be6260 rip=0x6be7000 rdi=0x10 rsi=0x20 rdx=0x30 rcx=0x40 "
            "r8=0x50 r9=0x60 rsp=0x70 rbp=0x80\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rdx\n"
            "0x30:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rdx\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x70:\t0x0000000000000003\t0x0000000000000004\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x6be7000 in ?? ()\n"
            "#1  0x6101234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)

        self.assertEqual(summary["hitCount"], 2)
        self.assertEqual(summary["hits"][1]["seed"], "StaticLoadClass")
        self.assertIn("unterminated disassembly capture before next hit", summary["hits"][0]["parseWarnings"])
        self.assertIn(
            "trace parser warning: unterminated disassembly capture before next hit",
            summary["hits"][0]["blockers"],
        )
        self.assertEqual(summary["familyCandidates"]["StaticLoadClass"]["hitIndex"], 1)

    def test_unterminated_capture_at_eof_is_reported_as_blocker(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)

        self.assertEqual(summary["hitCount"], 1)
        self.assertIn("unterminated stack capture at end of log", summary["hits"][0]["parseWarnings"])
        self.assertIn(
            "trace parser warning: unterminated stack capture at end of log",
            summary["hits"][0]["blockers"],
        )

    def test_review_priority_prefers_complete_memory_over_family_order(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=2\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=StaticLoadClass imageOffset=0x6ae6260 "
            "addr=0x6be6260 rip=0x6be7000 rdi=0x10 rsi=0x20 rdx=0x30 rcx=0x40 "
            "r8=0x50 r9=0x60 rsp=0x70 rbp=0x80\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x6be7000:\tmov %rsi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x70:\t0x0000000000000003\t0x0000000000000004\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x6be7000 in ?? ()\n"
            "#1  0x6101234 in ?? ()\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)

        self.assertEqual(summary["familyCandidates"]["StaticLoadClass"]["missingRequiredMemoryRegisters"], ["rdx"])
        self.assertEqual(summary["familyCandidates"]["LoadPackage"]["missingRequiredMemoryRegisters"], [])
        self.assertEqual(summary["recommendedReview"]["seed"], "LoadPackage")
        self.assertGreater(
            summary["familyCandidates"]["LoadPackage"]["reviewScore"],
            summary["familyCandidates"]["StaticLoadClass"]["reviewScore"],
        )

    def test_review_score_rewards_target_image_rip(self):
        base_candidate = {
            "seed": "LoadPackage",
            "targetImageCaller": True,
            "targetImageRip": False,
            "disassemblyLines": 1,
            "stackLines": 1,
            "missingRequiredMemoryRegisters": [],
            "missingCallFrameOffsets": [],
        }
        target_rip_candidate = {**base_candidate, "targetImageRip": True}

        self.assertGreater(
            self.module.candidate_review_score(target_rip_candidate),
            self.module.candidate_review_score(base_candidate),
        )

    def test_review_priority_penalizes_missing_call_frame_offsets(self):
        log_body = (
            "UE4SS_PACKAGE_TRACE_HIT seed=StaticLoadClass imageOffset=0x6ae6260 "
            "addr=0x6be6260 rip=0x6be7000 rdi=0x10 rsi=0x20 rdx=0x30 rcx=0x40 "
            "r8=0x50 r9=0x60 rsp=0x70 rbp=0x80\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x6be7000:\tmov %rsi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rdx\n"
            "0x30:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rdx\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x70:\t0x0000000000000003\t0x0000000000000004\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x6be7000 in ?? ()\n"
            "#1  0x6101234 in ?? ()\n"
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        log = self.write_log(log_body)
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000)

        static_candidate = summary["familyCandidates"]["StaticLoadClass"]
        load_package_candidate = summary["familyCandidates"]["LoadPackage"]
        self.assertEqual(static_candidate["missingCallFrameOffsets"], ["callerImageOffset", "ripImageOffset"])
        self.assertEqual(load_package_candidate["missingCallFrameOffsets"], ["callerImageOffset", "ripImageOffset"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])

        armed_log = self.write_log("UE4SS_PACKAGE_TRACE armed pid=123 base=0x100000 build_id=abc123 seeds=2\n" + log_body)
        summary_with_base = self.module.build_summary(armed_log, image_start=0x100000, image_end=0x7000000, base=0x100000, pid=123)
        self.assertEqual(summary_with_base["familyCandidates"]["StaticLoadClass"]["missingCallFrameOffsets"], [])
        self.assertEqual(summary_with_base["recommendedReview"]["seed"], "StaticLoadClass")
        self.assertEqual(summary_with_base["concreteReviewPriority"][0]["seed"], "StaticLoadClass")
        self.assertGreater(
            self.module.candidate_review_score(summary_with_base["familyCandidates"]["StaticLoadClass"]),
            self.module.candidate_review_score(static_candidate),
        )
        rendered = self.module.markdown(summary)
        self.assertIn("missing call-frame offsets: callerImageOffset,ripImageOffset", rendered)
        self.assertIn("Recommended review: `none`", rendered)
        self.assertIn("ripImageOffset=", rendered)

    def test_concrete_review_priority_requires_family_memory_evidence(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)
        hit = summary["hits"][0]
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertEqual(hit["requiredMemoryRegisters"], ["rsi"])
        self.assertEqual(hit["missingRequiredMemoryRegisters"], ["rsi"])
        self.assertIn("missing required memory registers: rsi", hit["blockers"])
        self.assertEqual(candidate["missingCallFrameOffsets"], [])
        self.assertEqual(candidate["missingRequiredMemoryRegisters"], ["rsi"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])
        self.assertIn("missing required memory: rsi", self.module.markdown(summary))

    def test_missing_image_range_blocks_target_image_proof(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log)
        blockers = summary["hits"][0]["blockers"]
        self.assertIn("missing executable image range; cannot prove target-image caller", blockers)
        self.assertIn("missing disassembly context for ABI review", blockers)
        self.assertIn("missing stack context for ABI review", blockers)

    def test_malformed_hit_context_shapes_are_blockers_not_crashes(self):
        hit = {
            "seed": "LoadPackage",
            "imageOffset": "0x5ae6260",
            "seedAddress": "0x5be6260",
            "rip": "0x5be7000",
            "registers": {"": "0x0", "rsi": 42},
            "backtrace": "not-array",
            "disassembly": {"line": "mov"},
            "stack": "not-array",
            "registerMemory": {"": [], "rsi": "not-array", "rdx": ["ok", 42]},
            "parseWarnings": "not-array",
        }

        enriched = self.module.enrich_hits([hit], image_start=0x100000, image_end=0x7000000, base=0x100000)
        candidates = self.module.family_candidates(enriched)
        summary = {
            "hits": enriched,
            "familyCandidates": candidates,
            "armedCount": 0,
            "hitCount": 1,
            "promotableHitCount": 0,
            "sourceLog": "/tmp/trace.log",
            "sourceLogExists": True,
            "imageRangeSource": "argument",
            "pid": None,
            "imageBase": "0x100000",
            "imageStart": "0x100000",
            "imageEnd": "0x7000000",
            "imagePath": "",
            "imagePerms": "",
            "completePackageRoute": False,
            "recommendedReview": {},
            "reviewPriority": [],
            "concreteReviewPriority": [],
            "nextStep": "complete manual ABI review for a package trace hit",
        }
        rendered = self.module.markdown(summary)
        blockers = enriched[0]["blockers"]

        self.assertIn("backtrace must be a JSON array", blockers)
        self.assertIn("disassembly must be a JSON array", blockers)
        self.assertIn("stack must be a JSON array", blockers)
        self.assertIn("parseWarnings must be a JSON array", blockers)
        self.assertIn("registers contains an invalid register key", blockers)
        self.assertIn("registers.rsi must be a string", blockers)
        self.assertIn("registerMemory contains an invalid register key", blockers)
        self.assertIn("registerMemory.rsi must be a JSON array", blockers)
        self.assertIn("registerMemory.rdx entries must be strings", blockers)
        self.assertEqual(enriched[0]["requiredMemoryRegisters"], ["rsi"])
        self.assertEqual(enriched[0]["missingRequiredMemoryRegisters"], ["rsi"])
        self.assertEqual(candidates["LoadPackage"]["registerMemoryRegisters"], [])
        self.assertEqual(candidates["LoadPackage"]["missingRequiredMemoryRegisters"], ["rsi"])
        self.assertIn("disasmLines=`0` stackLines=`0`", rendered)

    def test_empty_hit_seed_is_blocked_and_not_review_candidate(self):
        hit = {
            "seed": "",
            "imageOffset": "0x5ae6260",
            "seedAddress": "0x5be6260",
            "rip": "0x5be7000",
            "registers": {},
            "backtrace": [],
            "disassembly": [],
            "stack": [],
            "registerMemory": {},
            "parseWarnings": [],
        }

        enriched = self.module.enrich_hits([hit], image_start=0x100000, image_end=0x7000000, base=0x100000)
        candidates = self.module.family_candidates(enriched)

        self.assertIn("seed must be a non-empty string", enriched[0]["blockers"])
        self.assertEqual(candidates, {})

    def test_malformed_required_memory_rows_do_not_satisfy_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)
        summary["hits"][0]["registerMemory"] = {"rsi": ["0x2:\t0x41", 42]}
        candidates = self.module.family_candidates(summary["hits"])
        concrete = self.module.concrete_review_candidates(candidates)

        candidate = candidates["LoadPackage"]
        self.assertEqual(candidate["registerMemoryRegisters"], [])
        self.assertEqual(candidate["missingRequiredMemoryRegisters"], ["rsi"])
        self.assertIn("registerMemory.rsi entries must be strings", candidate["shapeBlockers"])
        self.assertEqual(concrete, [])

    def test_malformed_hit_context_is_not_concrete_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)
        hit = summary["hits"][0]
        hit["registers"]["rsi"] = 42
        candidates = self.module.family_candidates(summary["hits"])
        concrete = self.module.concrete_review_candidates(candidates)

        candidate = candidates["LoadPackage"]
        self.assertEqual(candidate["missingCallFrameOffsets"], [])
        self.assertEqual(candidate["missingRequiredMemoryRegisters"], [])
        self.assertIn("registers.rsi must be a string", candidate["shapeBlockers"])
        self.assertEqual(concrete, [])

    def test_parse_warnings_do_not_satisfy_concrete_review_candidate(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x5be7000 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x5be7000:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x5be7000 in ?? ()\n"
            "#1  0x6001234 in ?? ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertIn("unterminated registerMemory capture before disassembly", summary["hits"][0]["parseWarnings"])
        self.assertIn("parseWarnings must be resolved before concrete review", candidate["shapeBlockers"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])

    def test_non_target_frames_do_not_emit_image_offsets(self):
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            "addr=0x5be6260 rip=0x7ffff7f00100 rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\n"
            "=> 0x7ffff7f00100:\tmov %rdi,%rax\n"
            "UE4SS_PACKAGE_TRACE_DISASM_END\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi\n"
            "0x2:\t0x41\t0x00\t0x00\t0x00\n"
            "UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi\n"
            "UE4SS_PACKAGE_TRACE_STACK_BEGIN\n"
            "0x7:\t0x0000000000000001\t0x0000000000000002\n"
            "UE4SS_PACKAGE_TRACE_STACK_END\n"
            "#0  0x7ffff7f00100 in libc.so ()\n"
            "#1  0x7ffff7f00123 in libc.so ()\n"
        )
        summary = self.module.build_summary(log, image_start=0x100000, image_end=0x7000000, base=0x100000)
        hit = summary["hits"][0]
        candidate = summary["familyCandidates"]["LoadPackage"]

        self.assertFalse(hit["targetImageCaller"])
        self.assertFalse(hit["targetImageRip"])
        self.assertEqual(hit["ripImageOffset"], "")
        self.assertEqual(hit["callerImageOffset"], "")
        self.assertEqual(hit["backtrace"][0]["imageOffset"], "")
        self.assertEqual(hit["backtrace"][1]["imageOffset"], "")
        self.assertEqual(candidate["missingCallFrameOffsets"], ["callerImageOffset", "ripImageOffset"])
        self.assertFalse(candidate["targetImageRip"])
        self.assertEqual(summary["recommendedReview"], {})
        self.assertEqual(summary["concreteReviewPriority"], [])
        self.assertIn("caller frame is not proven inside target executable image", hit["blockers"])

    def test_pid_range_derivation_reports_current_process_image(self):
        image = self.module.executable_image_range_for_pid(os.getpid())
        self.assertIsNotNone(image)
        self.assertIn("imageStart", {"imageStart": image["imageStart"]})
        self.assertLess(image["imageStart"], image["imageEnd"])
        self.assertTrue(image["perms"])

    def test_pid_range_can_prove_current_process_backtrace_frame(self):
        image = self.module.executable_image_range_for_pid(os.getpid())
        if not image:
            self.skipTest("no executable mapping for current process")
        caller = image["imageStart"]
        log = self.write_log(
            "UE4SS_PACKAGE_TRACE_HIT seed=LoadPackage imageOffset=0x5ae6260 "
            f"addr=0x5be6260 rip=0x{caller:x} rdi=0x1 rsi=0x2 rdx=0x3 rcx=0x4 "
            "r8=0x5 r9=0x6 rsp=0x7 rbp=0x8\n"
            f"#0  0x{caller:x} in ?? ()\n"
            f"#1  0x{caller:x} in ?? ()\n"
        )
        summary = self.module.build_summary(log, pid=os.getpid())
        self.assertEqual(summary["imageRangeSource"], "pid")
        self.assertTrue(summary["hits"][0]["targetImageCaller"])


if __name__ == "__main__":
    unittest.main()
