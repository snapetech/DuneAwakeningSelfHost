#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-ue4ss-package-live-stimulus-summary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_stimulus_summary", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def json_sha256(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def runbook(path):
    return {
        "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
        "sourcePath": str(path),
        "remote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "operatorWindow": {"maxArmSeconds": 120, "cleanupRequired": True},
    }


def add_client_gate_runbook(rb):
    rb["originClassification"] = {
        "status": "unknown",
        "probeCandidate": "operator-client-map-entry",
        "serverSideFallbackCandidate": "server-side-client-call-emulation",
        "decision": "trace first; replay/spoof server-side if client-originated",
    }
    return rb


def origin_classification(status="missing", blockers=None):
    if blockers is None:
        blockers = ["package-load classification has no selected runtime package hit"] if status == "missing" else []
    return {
        "status": status,
        "source": "live-stimulus-review-summary",
        "probeCandidate": "operator-client-map-entry",
        "serverSideFallbackCandidate": "server-side-client-call-emulation",
        "decision": "trace first; replay/spoof server-side if client-originated",
        "requiresServerSideReplay": status == "client-originated-pending-server-replay",
        "blockers": blockers,
    }


def verifier_command(summary_path, runbook_path, next_action_path):
    return (
        "scripts/verify-ue4ss-package-live-stimulus-summary.py "
        f"{summary_path} --runbook-json {runbook_path} --next-action-json {next_action_path}"
    )


def next_action(summary_path, runbook_path=None, next_action_path=None):
    live = {
        "remote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "localReviewSummaryJson": str(summary_path),
        "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
        "localReviewSummaryEmbeddedEvidenceFields": "reviewBundleVerification,reviewBundleVerificationSha256,routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,prearmReadinessVerification,prearmReadinessVerificationSha256",
        "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
        "prearmReadinessJson": "/tmp/ue4ss-package-prearm-readiness.json",
    }
    if runbook_path and next_action_path:
        live["localReviewSummaryVerificationCommand"] = verifier_command(
            summary_path,
            runbook_path,
            next_action_path,
        )
    return {
        "schemaVersion": "dune-ue4ss-package-next-action/v1",
        "action": "recover-package-anchor",
        "liveTraceRunbook": live,
    }


def summary(summary_path, runbook_path):
    return {
        "schemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
        "runbook": str(runbook_path),
        "sourceRunbook": str(runbook_path),
        "traceLogOverride": "",
        "traceRemote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "operatorWindowSeconds": 30,
        "runStartedUtc": "2026-06-23T22:00:00Z",
        "statusFinishedUtc": "2026-06-23T22:00:30Z",
        "bundle": "/tmp/review-bundles/20260623T220030Z",
        "verifyJson": "/tmp/ue4ss-package-review-bundle-verification.json",
        "ready": False,
        "blockers": ["missing hit"],
        "artifactCount": 14,
        "checksumCount": 15,
    }


def review_verification(ready=False, blockers=None):
    if blockers is None:
        blockers = ["missing hit"] if not ready else []
    return {
        "schemaVersion": "dune-ue4ss-package-review-bundle-verification/v1",
        "ready": ready,
        "bundle": "/tmp/review-bundles/20260623T220030Z",
        "blockers": blockers,
        "artifactCount": 14,
        "checksumCount": 15,
    }


def route_slot_verification(ready=True, blockers=None):
    if blockers is None:
        blockers = [] if ready else ["missing route vtable slot"]
    payload = {
        "schemaVersion": "dune-ue4ss-package-route-slot-recovery-verification/v1",
        "ready": ready,
        "blockers": blockers,
        "routeAddress": "0x129d58a2",
        "requiredSlots": ["0x3a0", "0x3d8"],
    }
    if not ready:
        payload["nextTraceRequirement"] = {
            "routeAddress": "0x129d58a2",
            "reviewField": "routeVtableStaticSlotMatches",
            "requiredSlots": ["0x3a0", "0x3d8"],
            "requiredRegisters": ["rbx", "r14"],
            "missingSlots": ["0x3d8"],
            "missingRegisters": ["r14"],
            "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "expectedReviewField": "routeVtableStaticSlotMatches",
        }
    return payload


def add_route_slot_evidence(payload, ready=True, blockers=None):
    embedded = route_slot_verification(ready=ready, blockers=blockers)
    payload.update(
        {
            "routeSlotRecoveryVerification": embedded,
            "routeSlotRecoveryVerificationSha256": json_sha256(embedded),
        }
    )
    add_prearm_evidence(payload)
    return payload


def prearm_verification(ready=True, blockers=None):
    if blockers is None:
        blockers = [] if ready else ["trace plan is stale"]
    return {
        "schemaVersion": "dune-ue4ss-package-prearm-readiness/v1",
        "ready": ready,
        "blockers": blockers,
        "tracePlan": {"expandedRouteCaptureReady": ready},
    }


def add_prearm_evidence(payload, ready=True, blockers=None):
    embedded = prearm_verification(ready=ready, blockers=blockers)
    payload.update(
        {
            "prearmReadinessJson": "/tmp/ue4ss-package-prearm-readiness.json",
            "prearmReadinessVerification": embedded,
            "prearmReadinessVerificationSha256": json_sha256(embedded),
        }
    )
    return payload


class VerifyLiveStimulusSummaryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_missing_summary_reports_structured_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "missing-summary.json"
            runbook_path = root / "runbook.json"
            next_action_path = root / "next-action.json"
            write_json(runbook_path, runbook(runbook_path))
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertEqual(report["blockers"], ["summary JSON is missing"])
        self.assertIn("summary JSON is missing", rendered)

    def test_malformed_summary_reports_structured_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "summary.json"
            summary_path.write_text("{", encoding="utf-8")
            report = self.module.report(summary_path)

        self.assertFalse(report["ready"])
        self.assertTrue(
            any(blocker.startswith("summary JSON is unreadable:") for blocker in report["blockers"]),
            report["blockers"],
        )

    def test_valid_summary_matches_runbook_and_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            verify_path = root / "review-verification.json"
            embedded = review_verification(ready=True, blockers=[])
            rb = runbook(runbook_path)
            rb["localReviewSummaryVerificationCommand"] = verifier_command(
                summary_path,
                runbook_path,
                next_action_path,
            )
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": str(verify_path),
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            add_route_slot_evidence(payload)
            write_json(runbook_path, rb)
            write_json(summary_path, payload)
            write_json(verify_path, embedded)
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["blockers"], [])
        self.assertIn("Ready: `true`", rendered)

    def test_valid_summary_matches_readable_review_bundle_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            verify_path = root / "review-verification.json"
            embedded = review_verification(ready=True, blockers=[])
            payload = summary(summary_path, runbook_path)
            payload.update({"verifyJson": str(verify_path), "ready": True, "blockers": []})
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(verify_path, embedded)
            report = self.module.report(summary_path, runbook_path)

        self.assertTrue(report["ready"], report["blockers"])

    def test_valid_summary_matches_embedded_remote_review_bundle_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            payload = summary(summary_path, runbook_path)
            embedded = review_verification(ready=True, blockers=[])
            payload.update(
                {
                    "verifyJson": "/tmp/remote-only-review-verification.json",
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            add_route_slot_evidence(payload)
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertTrue(report["ready"], report["blockers"])

    def test_non_ready_summary_allows_route_slot_blockers_beside_review_bundle_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            review = review_verification(ready=False, blockers=["missing hit"])
            route = route_slot_verification(ready=False, blockers=["missing route vtable slot"])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": "/tmp/remote-only-review-verification.json",
                    "ready": False,
                    "blockers": ["missing hit", "route-slot recovery: missing route vtable slot"],
                    "reviewBundleVerification": review,
                    "reviewBundleVerificationSha256": json_sha256(review),
                    "routeSlotRecoveryVerification": route,
                    "routeSlotRecoveryVerificationSha256": json_sha256(route),
                    "routeSlotRecoveryNextTraceRequirement": route["nextTraceRequirement"],
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertEqual(
            report["routeSlotRecoveryNextTraceRequirement"],
            route["nextTraceRequirement"],
        )
        self.assertNotIn("summary blockers do not match review bundle verification blockers", report["blockers"])
        self.assertIn("summary is not ready: missing hit", report["blockers"])
        self.assertIn(
            "summary is not ready: route-slot recovery: missing route vtable slot",
            report["blockers"],
        )
        self.assertNotIn(
            "summary routeSlotRecoveryNextTraceRequirement does not match embedded routeSlotRecoveryVerification",
            report["blockers"],
        )
        self.assertIn("Route slot next trace", rendered)
        self.assertIn("missingSlots=`0x3d8`", rendered)

    def test_runbook_origin_classification_requires_summary_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            rb = add_client_gate_runbook(runbook(runbook_path))
            payload = summary(summary_path, runbook_path)
            write_json(runbook_path, rb)
            write_json(summary_path, payload)

            report = self.module.report(summary_path, runbook_path)

        self.assertIn(
            "summary missing originClassification required by stimulus runbook",
            report["blockers"],
        )

    def test_origin_classification_must_match_runbook_and_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            rb = add_client_gate_runbook(runbook(runbook_path))
            payload = summary(summary_path, runbook_path)
            payload["originClassification"] = origin_classification()
            write_json(runbook_path, rb)
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)
            rendered = self.module.markdown(report)

        self.assertNotIn(
            "summary missing originClassification required by stimulus runbook",
            report["blockers"],
        )
        self.assertIn("summary is not ready: missing hit", report["blockers"])
        self.assertIn("Origin/reachability classification: status=`missing`", rendered)

    def test_client_originated_classification_requires_server_side_replay_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            rb = add_client_gate_runbook(runbook(runbook_path))
            payload = summary(summary_path, runbook_path)
            gate = origin_classification(status="client-originated-pending-server-replay")
            gate["requiresServerSideReplay"] = False
            payload["originClassification"] = gate
            write_json(runbook_path, rb)
            write_json(summary_path, payload)

            report = self.module.report(summary_path, runbook_path)

        self.assertIn(
            "summary originClassification requires server-side replay when client-originated",
            report["blockers"],
        )

    def test_route_slot_next_trace_requirement_must_match_embedded_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            review = review_verification(ready=False, blockers=["missing hit"])
            route = route_slot_verification(ready=False, blockers=["missing route vtable slot"])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": "/tmp/remote-only-review-verification.json",
                    "ready": False,
                    "blockers": ["missing hit", "route-slot recovery: missing route vtable slot"],
                    "reviewBundleVerification": review,
                    "reviewBundleVerificationSha256": json_sha256(review),
                    "routeSlotRecoveryVerification": route,
                    "routeSlotRecoveryVerificationSha256": json_sha256(route),
                    "routeSlotRecoveryNextTraceRequirement": {"routeAddress": "0xdeadbeef"},
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertIn(
            "summary routeSlotRecoveryNextTraceRequirement does not match embedded routeSlotRecoveryVerification",
            report["blockers"],
        )

    def test_non_ready_route_slot_requires_next_trace_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            review = review_verification(ready=False, blockers=["missing hit"])
            route = route_slot_verification(ready=False, blockers=["missing route vtable slot"])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": "/tmp/remote-only-review-verification.json",
                    "ready": False,
                    "blockers": ["missing hit", "route-slot recovery: missing route vtable slot"],
                    "reviewBundleVerification": review,
                    "reviewBundleVerificationSha256": json_sha256(review),
                    "routeSlotRecoveryVerification": route,
                    "routeSlotRecoveryVerificationSha256": json_sha256(route),
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))

            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertIn(
            "summary non-ready routeSlotRecoveryVerification requires matching routeSlotRecoveryNextTraceRequirement",
            report["blockers"],
        )

    def test_ready_route_slot_rejects_stale_next_trace_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            verify_path = root / "review-verification.json"
            review = review_verification(ready=True, blockers=[])
            route = route_slot_verification(ready=True)
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": str(verify_path),
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": review,
                    "reviewBundleVerificationSha256": json_sha256(review),
                    "routeSlotRecoveryVerification": route,
                    "routeSlotRecoveryVerificationSha256": json_sha256(route),
                    "routeSlotRecoveryNextTraceRequirement": {"routeAddress": "0x129d58a2"},
                }
            )
            add_prearm_evidence(payload)
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(verify_path, review)
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))

            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertIn(
            "summary routeSlotRecoveryNextTraceRequirement must be empty when embedded routeSlotRecoveryVerification has no nextTraceRequirement",
            report["blockers"],
        )

    def test_ready_summary_requires_review_bundle_verification_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": "/tmp/remote-only-review-verification.json",
                    "ready": True,
                    "blockers": [],
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "summary ready requires readable or embedded review bundle verification evidence",
            report["blockers"],
        )

    def test_rejects_embedded_review_bundle_verification_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            payload = summary(summary_path, runbook_path)
            embedded = review_verification()
            payload.update(
                {
                    "verifyJson": "/tmp/remote-only-review-verification.json",
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": "0" * 64,
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "summary reviewBundleVerificationSha256 does not match embedded reviewBundleVerification",
            report["blockers"],
        )

    def test_rejects_embedded_review_bundle_verification_mismatch_with_readable_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            verify_path = root / "review-verification.json"
            readable = review_verification(ready=False, blockers=["missing hit"])
            embedded = review_verification(ready=False, blockers=["different blocker"])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": str(verify_path),
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(verify_path, readable)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "summary embedded reviewBundleVerification does not match readable review bundle verification",
            report["blockers"],
        )

    def test_rejects_stale_summary_when_review_bundle_verification_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            verify_path = root / "review-verification.json"
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "verifyJson": str(verify_path),
                    "ready": True,
                    "blockers": [],
                    "bundle": "/tmp/stale-bundle",
                    "artifactCount": 13,
                    "checksumCount": 14,
                }
            )
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(verify_path, review_verification())
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary ready does not match review bundle verification ready", report["blockers"])
        self.assertIn("summary blockers do not match review bundle verification blockers", report["blockers"])
        self.assertIn("summary artifactCount does not match review bundle verification artifactCount", report["blockers"])
        self.assertIn("summary checksumCount does not match review bundle verification checksumCount", report["blockers"])
        self.assertIn("summary bundle does not match review bundle verification bundle", report["blockers"])

    def test_rejects_stale_local_summary_verifier_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            rb = runbook(runbook_path)
            rb["localReviewSummaryVerificationCommand"] = verifier_command(
                root / "stale-summary.json",
                runbook_path,
                next_action_path,
            )
            na = next_action(summary_path, runbook_path, next_action_path)
            na["liveTraceRunbook"]["localReviewSummaryVerificationCommand"] = verifier_command(
                summary_path,
                root / "stale-runbook.json",
                next_action_path,
            )
            write_json(runbook_path, rb)
            write_json(summary_path, summary(summary_path, runbook_path))
            write_json(next_action_path, na)
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "stimulus runbook localReviewSummaryVerificationCommand does not match expected verifier command",
            report["blockers"],
        )
        self.assertIn(
            "next-action localReviewSummaryVerificationCommand does not match expected verifier command",
            report["blockers"],
        )

    def test_trace_log_override_accepts_source_or_effective_runbook_verifier_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_runbook_path = root / "source-runbook.json"
            effective_runbook_path = root / "effective-runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            rb = runbook(source_runbook_path)
            rb["localReviewSummaryVerificationCommand"] = verifier_command(
                summary_path,
                source_runbook_path,
                next_action_path,
            )
            na = next_action(summary_path, source_runbook_path, next_action_path)
            payload = summary(summary_path, effective_runbook_path)
            payload["sourceRunbook"] = str(source_runbook_path)
            payload["traceLogOverride"] = "/tmp/fresh-live.log"
            payload["traceLog"] = "/tmp/fresh-live.log"
            write_json(source_runbook_path, rb)
            write_json(summary_path, payload)
            write_json(next_action_path, na)
            report = self.module.report(summary_path, source_runbook_path, next_action_path)

        self.assertNotIn(
            "stimulus runbook localReviewSummaryVerificationCommand does not match expected verifier command",
            report["blockers"],
        )
        self.assertNotIn(
            "next-action localReviewSummaryVerificationCommand does not match expected verifier command",
            report["blockers"],
        )

    def test_rejects_next_action_live_trace_target_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            na = next_action(summary_path)
            na["liveTraceRunbook"]["remote"] = "kspld0"
            na["liveTraceRunbook"]["container"] = "stale-container"
            na["liveTraceRunbook"]["traceLog"] = "/tmp/stale.log"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, summary(summary_path, runbook_path))
            write_json(next_action_path, na)
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "summary traceRemote does not match next-action liveTraceRunbook remote",
            report["blockers"],
        )
        self.assertIn(
            "summary container does not match next-action liveTraceRunbook container",
            report["blockers"],
        )
        self.assertIn(
            "summary traceLog does not match next-action liveTraceRunbook traceLog",
            report["blockers"],
        )

    def test_next_action_embedded_evidence_contract_requires_summary_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            payload = summary(summary_path, runbook_path)
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path, runbook_path, next_action_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary missing reviewBundleVerification required by next-action", report["blockers"])
        self.assertIn("summary missing reviewBundleVerificationSha256 required by next-action", report["blockers"])

    def test_rejects_unexpected_next_action_embedded_evidence_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            embedded = review_verification(ready=True, blockers=[])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            add_route_slot_evidence(payload)
            na = next_action(summary_path, runbook_path, next_action_path)
            na["liveTraceRunbook"]["localReviewSummaryEmbeddedEvidenceFields"] = "reviewBundleVerification"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, na)
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn("next-action localReviewSummaryEmbeddedEvidenceFields has unexpected value", report["blockers"])

    def test_rejects_unexpected_next_action_runbook_mode_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            embedded = review_verification(ready=True, blockers=[])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            add_route_slot_evidence(payload)
            na = next_action(summary_path, runbook_path, next_action_path)
            na["liveTraceRunbook"]["localReviewSummaryRunbookMode"] = "source-runbook-only"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, na)
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn("next-action localReviewSummaryRunbookMode has unexpected value", report["blockers"])

    def test_accepts_absolute_summary_path_matching_relative_next_action_path(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            relative_summary = root.relative_to(ROOT) / "summary.json"
            summary_path = ROOT / relative_summary
            runbook_path = root / "runbook.json"
            next_action_path = root / "next-action.json"
            embedded = review_verification(ready=True, blockers=[])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            add_route_slot_evidence(payload)
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(relative_summary))
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertTrue(report["ready"], report["blockers"])

    def test_accepts_absolute_source_runbook_matching_relative_runbook_argument(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            relative_runbook = root.relative_to(ROOT) / "runbook.json"
            runbook_path = ROOT / relative_runbook
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            embedded = review_verification(ready=True, blockers=[])
            payload = summary(summary_path, runbook_path)
            payload.update(
                {
                    "ready": True,
                    "blockers": [],
                    "reviewBundleVerification": embedded,
                    "reviewBundleVerificationSha256": json_sha256(embedded),
                }
            )
            add_route_slot_evidence(payload)
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path))
            report = self.module.report(summary_path, relative_runbook, next_action_path)

        self.assertTrue(report["ready"], report["blockers"])

    def test_rejects_stale_schema_and_wrong_next_action_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            payload = summary(summary_path, runbook_path)
            payload["schemaVersion"] = "stale"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "summary schemaVersion must be dune-ue4ss-package-live-stimulus-review-summary/v1",
            report["blockers"],
        )
        self.assertIn(
            "summary schemaVersion does not match next-action localReviewSummarySchemaVersion",
            report["blockers"],
        )

    def test_ready_state_must_match_blockers_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            payload = summary(summary_path, runbook_path)
            payload["ready"] = True
            payload["blockers"] = ["stale blocker"]
            payload["artifactCount"] = -1
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            write_json(next_action_path, next_action(summary_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary ready must not be true when blockers are present", report["blockers"])
        self.assertIn("summary artifactCount must be a non-negative integer when present", report["blockers"])

    def test_not_ready_summary_must_have_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            payload = summary(summary_path, runbook_path)
            payload["ready"] = False
            payload["blockers"] = []
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary blockers must explain why ready is false", report["blockers"])

    def test_not_ready_summary_remains_a_completion_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            payload = summary(summary_path, runbook_path)
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary is not ready: missing hit", report["blockers"])

    def test_trace_log_override_must_match_effective_runbook_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            payload = summary(summary_path, runbook_path)
            payload["traceLogOverride"] = "/tmp/fresh.log"
            payload["traceLog"] = "/tmp/stale.log"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary traceLogOverride must match traceLog when an override was used", report["blockers"])
        self.assertIn("summary runbook must be the effective override runbook when traceLogOverride is set", report["blockers"])

    def test_rejects_runbook_and_next_action_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "summary.json"
            next_action_path = root / "next-action.json"
            rb = runbook(runbook_path)
            rb["remote"] = "kspld0"
            na = next_action(root / "other-summary.json")
            write_json(runbook_path, rb)
            write_json(summary_path, summary(summary_path, runbook_path))
            write_json(next_action_path, na)
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary traceRemote does not match stimulus runbook remote", report["blockers"])
        self.assertIn("summary path does not match next-action localReviewSummaryJson", report["blockers"])


if __name__ == "__main__":
    unittest.main()
