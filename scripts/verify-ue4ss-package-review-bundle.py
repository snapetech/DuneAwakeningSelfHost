#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-review-bundle-verification/v1"
MANIFEST_SCHEMA = "dune-ue4ss-package-review-bundle/v1"
REQUIRED_FILES = (
    "review-bundle-manifest.txt",
    "SHA256SUMS",
    "ue4ss-package-runtime-trace-plan.json",
    "ue4ss-package-runtime-trace-plan.md",
    "ue4ss-package-runtime-trace-evidence.json",
    "ue4ss-package-runtime-trace-evidence.md",
    "ue4ss-package-abi-review.json",
    "ue4ss-package-abi-review.md",
    "ue4ss-package-promotion-env.json",
    "ue4ss-package-promotion-env.md",
    "ue4ss-package-stimulus-trace-runbook.json",
    "ue4ss-package-next-action.json",
    "ue4ss-package-next-action.md",
)
JSON_SCHEMAS = {
    "ue4ss-package-runtime-trace-plan.json": "dune-ue4ss-package-runtime-trace-plan/v1",
    "ue4ss-package-runtime-trace-evidence.json": "dune-ue4ss-package-runtime-trace-evidence/v1",
    "ue4ss-package-abi-review.json": "dune-ue4ss-package-abi-review/v1",
    "ue4ss-package-promotion-env.json": "dune-ue4ss-package-promotion-env/v1",
    "ue4ss-package-stimulus-trace-runbook.json": "dune-ue4ss-package-stimulus-trace-runbook/v1",
    "ue4ss-package-next-action.json": "dune-ue4ss-package-next-action/v1",
    "ue4ss-package-next-canary.json": "dune-ue4ss-canary-env-plan/v1",
}
REVIEW_PRIORITY_SCHEMA = "dune-ue4ss-package-review-priority/v1"
PROMOTION_ENV_SCHEMA = "dune-ue4ss-package-promotion-env/v1"
PROMOTION_SUMMARY_SCHEMA = "dune-ue4ss-package-promotion-dir-summary/v1"
PROMOTION_ACCEPTANCE_SCHEMA = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS = "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256"
LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_SCHEMA = "dune-ue4ss-package-live-stimulus-review-summary/v1"
LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE = (
    "preflight",
    "arm",
    "operator-client-login-travel-map-entry",
    "status",
    "cleanupCommand",
    "no-debugger-check",
)
LIVE_TRACE_RUNBOOK_NO_DEBUGGER_NEEDLE = 'grep -E "gdb|ue4ss-package-runtime-trace"'
LIVE_TRACE_RUNBOOK_EXPECTED_REVIEW_ARTIFACTS = {
    "evidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
    "evidenceMarkdown": "/tmp/ue4ss-package-runtime-trace-evidence.md",
    "abiReviewJson": "/tmp/ue4ss-package-abi-review.json",
    "promotionEnvJson": "/tmp/ue4ss-package-promotion-env.json",
    "familyReviewsDir": "/tmp/ue4ss-package-family-reviews",
    "familyReviewsSummaryJson": "/tmp/ue4ss-package-family-reviews.json",
    "nextActionJson": "/tmp/ue4ss-package-next-action.json",
    "reviewBundleRoot": "/tmp/ue4ss-package-review-bundles",
    "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
    "localReviewSummarySchemaVersion": LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_SCHEMA,
    "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
    "localReviewSummaryVerificationCommand": (
        "scripts/verify-ue4ss-package-live-stimulus-summary.py "
        "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json "
        "--runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json "
        "--next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json"
    ),
    "digestProvenanceFields": LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS,
}
LIVE_TRACE_RUNBOOK_EXPECTED_TRACE_ENV = {
    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST": "kspls0",
    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "false",
    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PARTITION": "8",
}
PACKAGE_TRACE_ANCHORS = {"StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName"}
TRACE_PLAN_PROVENANCE_ENV_KEYS = {
    "DUNE_UE4SS_PACKAGE_TRACE_PLAN",
    "DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON",
    "DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD",
}
SUMMARY_MANIFEST_MATCH_FIELDS = (
    "signatureFamily",
    "hitIndex",
    "selectedHitSeed",
    "sourceEvidence",
    "sourceEvidenceJson",
    "sourceEvidenceJsonSha256",
    "sourceLogSha256",
    "sourceLogExists",
    "tracePid",
    "imageRangeSource",
    "imageBase",
    "imageStart",
    "imageEnd",
    "imagePath",
    "imagePerms",
    "callerImageOffset",
    "ripImageOffset",
    "abiReviewReady",
    "abiReviewed",
    "targetImageReviewed",
    "tcharReviewed",
    "classRootReviewed",
    "readyForNonInvokingCanary",
    "readyForNativeInvoke",
    "nativeInvokeEnabled",
    "finalNativeCallConfirmed",
)
ABI_REVIEW_PROMOTION_MATCH_FIELDS = (
    ("sourceEvidence", "sourceEvidence"),
    ("sourceEvidenceJson", "sourceEvidenceJson"),
    ("sourceEvidenceJsonSha256", "sourceEvidenceJsonSha256"),
    ("sourceLogSha256", "sourceLogSha256"),
    ("sourceLogExists", "sourceLogExists"),
    ("tracePid", "tracePid"),
    ("imageRangeSource", "imageRangeSource"),
    ("imageBase", "imageBase"),
    ("imageStart", "imageStart"),
    ("imageEnd", "imageEnd"),
    ("imagePath", "imagePath"),
    ("imagePerms", "imagePerms"),
    ("hitIndex", "hitIndex"),
    ("selectedHitSeed", "selectedHitSeed"),
    ("signatureFamily", "signatureFamily"),
    ("callerImageOffset", "callerImageOffset"),
    ("ripImageOffset", "ripImageOffset"),
)
PACKAGE_CLASS_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
}
PACKAGE_ASSET_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL",
    "DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES",
    "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT",
}
ASSET_FAMILIES = {"StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"}
BUILD_ID_RE = re.compile(r"^[0-9a-fA-F]+$")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(path):
    data = {}
    artifacts = []
    duplicate_keys = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "artifact":
            artifact, _, source = value.partition(" source=")
            artifacts.append({"path": artifact.strip(), "source": source.strip()})
        else:
            if key in data:
                duplicate_keys.append(key)
            data[key] = value
    if duplicate_keys:
        data["_duplicateKeys"] = duplicate_keys
    return data, artifacts


def parse_sha256s(path):
    rows = {}
    duplicates = []
    errors = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            errors.append(f"SHA256SUMS row {line_number} is malformed")
            continue
        rel_path = parts[1].strip()
        digest = parts[0].strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            errors.append(f"SHA256SUMS row {line_number} has malformed digest")
            continue
        normalized = Path(rel_path)
        if normalized.is_absolute() or ".." in normalized.parts or rel_path.startswith("./"):
            errors.append(f"SHA256SUMS row {line_number} has unsafe path: {rel_path}")
            continue
        if rel_path in rows:
            duplicates.append(rel_path)
        rows[rel_path] = digest
    if duplicates:
        rows["__duplicate_paths__"] = duplicates
    if errors:
        rows["__errors__"] = errors
    return rows


def verify_manifest_artifact_rows(artifacts, blockers):
    seen = set()
    for row in artifacts:
        rel_path = row.get("path", "")
        source = row.get("source", "")
        if not rel_path:
            blockers.append("review-bundle-manifest.txt has artifact row with empty path")
            continue
        path = Path(rel_path)
        if path.is_absolute() or ".." in path.parts:
            blockers.append(f"review-bundle-manifest.txt has artifact row outside bundle namespace: {rel_path}")
        if rel_path in seen:
            blockers.append(f"review-bundle-manifest.txt has duplicate artifact row: {rel_path}")
        seen.add(rel_path)
        if not source:
            blockers.append(f"review-bundle-manifest.txt artifact row is missing source: {rel_path}")


def verify_manifest_artifact_inventory(root, artifacts, checksums, blockers):
    for row in artifacts:
        rel_path = row.get("path", "")
        if not rel_path:
            continue
        path = Path(rel_path)
        if path.is_absolute() or ".." in path.parts:
            continue
        if not (root / rel_path).is_file():
            blockers.append(f"review-bundle-manifest.txt artifact row references missing bundled file: {rel_path}")
            continue
        if rel_path not in checksums:
            blockers.append(f"review-bundle-manifest.txt artifact row is missing from SHA256SUMS: {rel_path}")
            continue
        actual_sha = sha256(root / rel_path)
        if checksums.get(rel_path, "") != actual_sha:
            blockers.append(f"review-bundle-manifest.txt artifact row SHA256SUMS digest does not match bundled file: {rel_path}")


def single_line_value(value):
    return isinstance(value, str) and value != "" and "\n" not in value and "\r" not in value


def non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def positive_decimal_text(value):
    text = str(value)
    return text.isascii() and text.isdecimal() and int(text) > 0


def valid_image_offset(value):
    text = str(value)
    return text.startswith("0x") and len(text) > 2 and all(char in "0123456789abcdefABCDEF" for char in text[2:])


def valid_sha256_text(value):
    text = str(value)
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def present_non_true(value):
    return value is not None and value is not True


def runtime_trace_evidence_tokens(value):
    parts = str(value).split(":", 2)
    tail = parts[2] if len(parts) > 2 else ""
    tokens = {}
    for item in tail.split():
        if "=" not in item:
            continue
        key, token_value = item.split("=", 1)
        if key:
            tokens[key] = token_value
    return tokens


def scalar_identity_errors(payload, fields):
    errors = []
    for field in fields:
        if field not in payload:
            continue
        value = payload.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, (str, int, float, bool)):
            errors.append(f"{field} must be a scalar")
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append(f"{field} must be a non-empty single-line value")
    return errors


def add_scalar_identity_blockers(blockers, rel_path, payload, fields):
    for error in scalar_identity_errors(payload, fields):
        blockers.append(f"{rel_path} {error}")


def verify_manifest_runtime_selectors(manifest, blockers):
    for key in ("container", "processPattern", "traceLog"):
        if not single_line_value(manifest.get(key, "")):
            blockers.append(f"review-bundle-manifest.txt {key} must be non-empty and single-line")
    for key in ("traceHost", "tracePid", "playerGuardPhase", "playerGuardPartition", "playerGuardConnectedPlayers"):
        value = manifest.get(key, "")
        if value and not single_line_value(value):
            blockers.append(f"review-bundle-manifest.txt {key} must be single-line")
    trace_pid = manifest.get("tracePid", "")
    if trace_pid and not positive_decimal_text(trace_pid):
        blockers.append("review-bundle-manifest.txt tracePid must be numeric")
    if manifest.get("traceHost", "") == "kspls0":
        phase = manifest.get("playerGuardPhase", "")
        partition = manifest.get("playerGuardPartition", "")
        players = manifest.get("playerGuardConnectedPlayers", "")
        if phase != "status":
            blockers.append("review-bundle-manifest.txt playerGuardPhase must be status for live kspls0 package trace evidence")
        if not positive_decimal_text(partition):
            blockers.append("review-bundle-manifest.txt playerGuardPartition must be numeric for live kspls0 package trace evidence")
        if players != "0":
            blockers.append("review-bundle-manifest.txt playerGuardConnectedPlayers must be 0 for live kspls0 package trace evidence")


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def valid_build_id(value):
    return value in ("", "unknown") or (isinstance(value, str) and bool(BUILD_ID_RE.fullmatch(value)))


def bundled_promotion_payload(priority_path):
    promotion_path = priority_path.parent / "promotion-env.json"
    if not promotion_path.is_file():
        return {}
    try:
        payload = load_json(promotion_path)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def bundled_promotion_family(priority_path):
    return bundled_promotion_payload(priority_path).get("signatureFamily", "")


def expected_evidence_provenance_value(payload_key, evidence_key, evidence, manifest=None, checksums=None):
    evidence_value = evidence.get(evidence_key, "")
    if payload_key == "sourceEvidenceJson" and evidence_value in (None, ""):
        return (manifest or {}).get("sourceEvidenceJson", "")
    if payload_key == "sourceEvidenceJsonSha256" and evidence_value in (None, ""):
        return (
            (manifest or {}).get("sourceEvidenceJsonSha256", "")
            or (checksums or {}).get("ue4ss-package-runtime-trace-evidence.json", "")
        )
    return evidence_value


def verify_bundled_promotion_identity(root, path, payload, evidence, blockers, manifest=None, checksums=None):
    rel_path = path.relative_to(root).as_posix()
    add_scalar_identity_blockers(
        blockers,
        rel_path,
        payload,
        (
            "sourceEvidence",
            "sourceEvidenceJson",
            "sourceEvidenceJsonSha256",
            "sourceLogSha256",
            "sourceTracePlan",
            "sourceTracePlanSchemaVersion",
            "sourcePromotionAcceptanceSchemaVersion",
            "sourceExternalPlan",
            "tracePid",
            "imageRangeSource",
            "imageBase",
            "imageStart",
            "imageEnd",
            "imagePath",
            "imagePerms",
            "selectedHitSeed",
            "callerImageOffset",
            "ripImageOffset",
        ),
    )
    source = payload.get("sourceEvidence", "")
    evidence_source = evidence.get("sourceLog", "")
    if source and evidence_source and source != evidence_source:
        blockers.append(f"{rel_path} sourceEvidence does not match runtime trace evidence sourceLog")
    for payload_key, evidence_key in (
        ("sourceEvidenceJson", "sourceEvidenceJson"),
        ("sourceEvidenceJsonSha256", "sourceEvidenceJsonSha256"),
        ("sourceLogSha256", "sourceLogSha256"),
    ):
        payload_value = payload.get(payload_key, "")
        evidence_value = expected_evidence_provenance_value(
            payload_key,
            evidence_key,
            evidence,
            manifest,
            checksums,
        )
        if (payload_value or evidence_value) and payload_value != evidence_value:
            blockers.append(f"{rel_path} {payload_key} does not match runtime trace evidence {evidence_key}")
    if (
        "sourceLogExists" in payload
        and "sourceLogExists" in evidence
        and payload.get("sourceLogExists") is not evidence.get("sourceLogExists")
    ):
        blockers.append(f"{rel_path} sourceLogExists does not match runtime trace evidence sourceLogExists")
    hit_index = payload.get("hitIndex")
    hit = selected_trace_hit(evidence, hit_index)
    if isinstance(hit_index, int) and not hit:
        blockers.append(f"{rel_path} selected runtime trace hit is missing for hitIndex {hit_index}")
    if hit and hit.get("traceAddressMatchesBase") is not True:
        blockers.append(f"{rel_path} selected runtime trace hit address does not match image base plus seed imageOffset")
    for error in register_shape_errors(hit):
        blockers.append(f"{rel_path} selected runtime trace hit {error}")
    for error in register_memory_shape_errors(hit):
        blockers.append(f"{rel_path} selected runtime trace hit {error}")
    missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(hit)
    for error in missing_required_memory_errors:
        blockers.append(f"{rel_path} selected runtime trace hit {error}")
    if missing_required_memory:
        blockers.append(
            f"{rel_path} selected runtime trace hit is missing required memory registers: "
            + ", ".join(str(item) for item in missing_required_memory)
        )
    for key in ("callerImageOffset", "ripImageOffset"):
        expected = hit.get(key, "")
        promoted = payload.get(key, "")
        if promoted and expected and promoted != expected:
            blockers.append(f"{rel_path} {key} does not match selected runtime trace hit")


def string_list_field(payload, key):
    raw = (payload or {}).get(key, [])
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [f"{key} must be a JSON array"]
    values = []
    errors = []
    for index, value in enumerate(raw):
        if not isinstance(value, str):
            errors.append(f"{key}[{index}] must be a string")
            continue
        values.append(value)
    return values, errors


def missing_required_memory_registers(hit):
    return string_list_field(hit, "missingRequiredMemoryRegisters")


def register_shape_errors(hit):
    registers = (hit or {}).get("registers", {})
    if registers is None:
        return []
    if not isinstance(registers, dict):
        return ["registers must be a JSON object"]
    errors = []
    for register, value in registers.items():
        if not isinstance(register, str) or not register:
            errors.append("registers contains an invalid register key")
            continue
        if not isinstance(value, str):
            errors.append(f"registers.{register} must be a string")
    return errors


def register_memory_shape_errors(hit):
    register_memory = (hit or {}).get("registerMemory", {})
    if register_memory is None:
        return []
    if not isinstance(register_memory, dict):
        return ["registerMemory must be a JSON object"]
    errors = []
    for register, rows in register_memory.items():
        if not isinstance(register, str) or not register:
            errors.append("registerMemory contains an invalid register key")
            continue
        if not isinstance(rows, list):
            errors.append(f"registerMemory.{register} must be a JSON array")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, str):
                errors.append(f"registerMemory.{register}[{index}] must be a string")
    return errors


def abi_review_argument_shape_errors(abi_review):
    arguments = (abi_review or {}).get("arguments", [])
    if arguments is None:
        return []
    if not isinstance(arguments, list):
        return ["abiReview.arguments must be a JSON array"]
    errors = []
    for arg_index, argument in enumerate(arguments):
        if not isinstance(argument, dict):
            errors.append(f"abiReview.arguments[{arg_index}] must be a JSON object")
            continue
        memory = argument.get("memory", {})
        if memory is None:
            continue
        if not isinstance(memory, dict):
            errors.append(f"abiReview.arguments[{arg_index}].memory must be a JSON object")
            continue
        line_count = memory.get("lineCount", 0)
        if (
            not isinstance(line_count, int)
            or isinstance(line_count, bool)
            or line_count < 0
        ):
            errors.append(
                f"abiReview.arguments[{arg_index}].memory.lineCount must be a non-negative integer"
            )
        hints = memory.get("hints", {})
        if hints is not None and not isinstance(hints, dict):
            errors.append(f"abiReview.arguments[{arg_index}].memory.hints must be a JSON object")
    return errors


def verify_promotion_ready_claim(root, path, payload, blockers):
    rel_path = path.relative_to(root).as_posix()
    add_scalar_identity_blockers(
        blockers,
        rel_path,
        payload,
        (
            "sourceEvidence",
            "tracePid",
            "imageRangeSource",
            "imageBase",
            "imageStart",
            "imageEnd",
            "imagePath",
            "imagePerms",
            "selectedHitSeed",
            "callerImageOffset",
            "ripImageOffset",
        ),
    )
    ready_non_invoking = payload.get("readyForNonInvokingCanary") is True
    ready_native = payload.get("readyForNativeInvoke") is True
    if not (ready_non_invoking or ready_native):
        return
    manifest_blockers, manifest_blocker_errors = string_list_field(payload, "blockers")
    raw_abi_review = payload.get("abiReview", {}) or {}
    if not isinstance(raw_abi_review, dict):
        raw_abi_review = {}
        blockers.append(f"{rel_path} abiReview must be a JSON object")
    abi_blockers, abi_blocker_errors = string_list_field(raw_abi_review, "blockers")
    missing_review, missing_review_errors = string_list_field(payload, "missingReviewFlags")
    missing_native, missing_native_errors = string_list_field(payload, "missingNativeInvokeFlags")
    for error in (
        manifest_blocker_errors
        + [f"abiReview.{item}" for item in abi_blocker_errors]
        + abi_review_argument_shape_errors(raw_abi_review)
        + missing_review_errors
        + missing_native_errors
    ):
        blockers.append(f"{rel_path} {error}")
    if ready_native and not ready_non_invoking:
        blockers.append(f"{rel_path} ready native package promotion manifest is missing non-invoking canary readiness")
    if manifest_blockers:
        blockers.append(f"{rel_path} ready package promotion manifest still has blockers")
    if abi_blockers:
        blockers.append(f"{rel_path} ready package promotion manifest still has ABI review blockers")
    for review_field, manifest_field in ABI_REVIEW_PROMOTION_MATCH_FIELDS:
        if review_field not in raw_abi_review:
            continue
        review_value = raw_abi_review.get(review_field)
        manifest_value = payload.get(manifest_field)
        if review_value in (None, "") and manifest_value in (None, ""):
            continue
        if str(review_value) != str(manifest_value):
            blockers.append(
                f"{rel_path} abiReview.{review_field} does not match promotion manifest {manifest_field}"
            )
    if payload.get("abiReviewReady") is not True and raw_abi_review.get("ready") is not True:
        blockers.append(f"{rel_path} ready package promotion manifest is missing ABI review readiness")
    if payload.get("abiReviewed") is not True:
        blockers.append(f"{rel_path} ready package promotion manifest is missing reviewed ABI confirmation")
    if payload.get("promotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA:
        blockers.append(f"{rel_path} ready package promotion manifest is missing current package promotion acceptance schema")
    family = payload.get("signatureFamily", "")
    if payload.get("targetImageReviewed") is not True:
        blockers.append(f"{rel_path} ready package promotion manifest is missing reviewed target-image confirmation")
    if family == "StaticLoadClass" and payload.get("classRootReviewed") is not True:
        blockers.append(f"{rel_path} ready package promotion manifest is missing reviewed class-root confirmation")
    if family in ASSET_FAMILIES and payload.get("tcharReviewed") is not True:
        blockers.append(f"{rel_path} ready package promotion manifest is missing reviewed TCHAR confirmation")
    if ready_native and payload.get("nativeInvokeEnabled") is not True:
        blockers.append(f"{rel_path} ready native package promotion manifest is missing native invoke enablement")
    if ready_native and payload.get("finalNativeCallConfirmed") is not True:
        blockers.append(f"{rel_path} ready native package promotion manifest is missing final native-call confirmation")
    if missing_review:
        blockers.append(f"{rel_path} ready package promotion manifest still has missing review flags")
    if ready_native and missing_native:
        blockers.append(f"{rel_path} ready native package promotion manifest still has missing native invoke flags")
    if not payload.get("sourceEvidence", ""):
        blockers.append(f"{rel_path} ready package promotion manifest is missing sourceEvidence")
    if not payload.get("sourceEvidenceJsonSha256", ""):
        blockers.append(f"{rel_path} ready package promotion manifest is missing sourceEvidenceJsonSha256 provenance")
    elif not valid_sha256_text(payload.get("sourceEvidenceJsonSha256", "")):
        blockers.append(f"{rel_path} ready package promotion manifest has invalid sourceEvidenceJsonSha256")
    if not payload.get("sourceLogSha256", ""):
        blockers.append(f"{rel_path} ready package promotion manifest is missing sourceLogSha256 provenance")
    elif not valid_sha256_text(payload.get("sourceLogSha256", "")):
        blockers.append(f"{rel_path} ready package promotion manifest has invalid sourceLogSha256")
    if "sourceLogExists" not in payload:
        blockers.append(f"{rel_path} ready package promotion manifest is missing sourceLogExists")
    elif payload.get("sourceLogExists") is not True:
        blockers.append(f"{rel_path} ready package promotion manifest sourceLog does not exist")
    if "tracePidMatchesRequested" not in payload:
        blockers.append(f"{rel_path} ready package promotion manifest is missing runtime trace PID match provenance")
    elif payload.get("tracePidMatchesRequested") is not True:
        blockers.append(f"{rel_path} trace log armed PID does not match requested runtime PID")
    if not non_negative_int(payload.get("hitIndex")):
        blockers.append(f"{rel_path} ready package promotion manifest is missing concrete hitIndex")
    if not payload.get("selectedHitSeed", ""):
        blockers.append(f"{rel_path} ready package promotion manifest is missing selectedHitSeed")
    if not payload.get("callerImageOffset", ""):
        blockers.append(f"{rel_path} ready package promotion manifest is missing callerImageOffset")
    elif not valid_image_offset(payload.get("callerImageOffset", "")):
        blockers.append(f"{rel_path} ready package promotion manifest has invalid callerImageOffset")
    if not payload.get("ripImageOffset", ""):
        blockers.append(f"{rel_path} ready package promotion manifest is missing ripImageOffset")
    elif not valid_image_offset(payload.get("ripImageOffset", "")):
        blockers.append(f"{rel_path} ready package promotion manifest has invalid ripImageOffset")
    hit = payload.get("hit", {}) or {}
    family = payload.get("signatureFamily", "")
    selected_hit_seed = payload.get("selectedHitSeed", "")
    caller_offset = payload.get("callerImageOffset", "")
    rip_offset = payload.get("ripImageOffset", "")
    if selected_hit_seed and family and selected_hit_seed != family:
        blockers.append(f"{rel_path} selectedHitSeed does not match signatureFamily")
    if isinstance(hit, dict) and hit:
        if present_non_true(hit.get("traceLogHasArmed")):
            blockers.append(f"{rel_path} embedded trace hit missing trace armed record; cannot prove runtime trace session")
        if present_non_true(hit.get("tracePidMatchesRequested")):
            blockers.append(f"{rel_path} embedded trace hit trace log armed PID does not match requested runtime PID")
        if hit.get("traceAddressMatchesBase") is not True:
            blockers.append(f"{rel_path} embedded trace hit address does not match image base plus seed imageOffset")
        for error in register_shape_errors(hit):
            blockers.append(f"{rel_path} embedded trace hit {error}")
        for error in register_memory_shape_errors(hit):
            blockers.append(f"{rel_path} embedded trace hit {error}")
        missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(hit)
        for error in missing_required_memory_errors:
            blockers.append(f"{rel_path} embedded trace hit {error}")
        if missing_required_memory:
            blockers.append(
                f"{rel_path} embedded trace hit is missing required memory registers: "
                + ", ".join(str(item) for item in missing_required_memory)
            )
        hit_seed = hit.get("seed", "")
        if selected_hit_seed and hit_seed and selected_hit_seed != hit_seed:
            blockers.append(f"{rel_path} selectedHitSeed does not match embedded trace hit seed")
        if hit_seed and family and hit_seed != family:
            blockers.append(f"{rel_path} embedded trace hit seed does not match signatureFamily")
        if hit.get("callerImageOffset", "") and hit.get("callerImageOffset", "") != caller_offset:
            blockers.append(f"{rel_path} embedded trace hit callerImageOffset does not match manifest")
        if hit.get("ripImageOffset", "") and hit.get("ripImageOffset", "") != rip_offset:
            blockers.append(f"{rel_path} embedded trace hit ripImageOffset does not match manifest")
    verify_runtime_trace_env_evidence(root, path, payload, blockers)
    if not positive_int(payload.get("tracePid")):
        blockers.append(f"{rel_path} ready package promotion manifest is missing concrete tracePid")


def verify_runtime_trace_env_evidence(root, path, payload, blockers):
    rel_path = path.relative_to(root).as_posix()
    family = payload.get("signatureFamily", "")
    caller_offset = payload.get("callerImageOffset", "")
    rip_offset = payload.get("ripImageOffset", "")
    trace_pid = payload.get("tracePid")
    evidence_json_sha256 = payload.get("sourceEvidenceJsonSha256", "")
    source_log_sha256 = payload.get("sourceLogSha256", "")
    env = payload.get("env", {}) or {}
    if not isinstance(env, dict):
        blockers.append(f"{rel_path} package promotion env must be an object")
        return
    evidence_values = [
        str(value)
        for key, value in env.items()
        if key in (
            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
            "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
            "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
        )
        and str(value).startswith("runtime-trace:")
    ]
    ready_claimed = payload.get("readyForNonInvokingCanary") is True or payload.get("readyForNativeInvoke") is True
    if ready_claimed and not evidence_values:
        if rel_path == "ue4ss-package-family-reviews.json":
            blockers.append(f"{rel_path} ready summary row is missing runtime trace env evidence")
        else:
            blockers.append(f"{rel_path} ready package promotion env is missing runtime trace evidence")
    if family:
        for value in evidence_values:
            parts = value.split(":", 2)
            evidence_family = parts[1] if len(parts) > 1 else ""
            if evidence_family != family:
                blockers.append(f"{rel_path} env evidence family does not match signatureFamily")
                break
    evidence_tokens = [runtime_trace_evidence_tokens(value) for value in evidence_values]
    if family:
        for value in evidence_values:
            tokens = runtime_trace_evidence_tokens(value)
            if tokens.get("seed", family) != family:
                blockers.append(f"{rel_path} env evidence seed does not match signatureFamily")
                break
    if caller_offset:
        for tokens in evidence_tokens:
            if tokens.get("caller", "") != caller_offset:
                blockers.append(f"{rel_path} env evidence caller does not match callerImageOffset")
                break
    if rip_offset:
        for tokens in evidence_tokens:
            if tokens.get("rip", "") != rip_offset:
                blockers.append(f"{rel_path} env evidence rip does not match ripImageOffset")
                break
    if trace_pid not in (None, ""):
        for tokens in evidence_tokens:
            if tokens.get("pid", "") != str(trace_pid):
                blockers.append(f"{rel_path} env evidence pid does not match tracePid")
                break
    if evidence_json_sha256:
        for tokens in evidence_tokens:
            if tokens.get("evidenceJsonSha256", "") != str(evidence_json_sha256):
                blockers.append(f"{rel_path} env evidence digest does not match sourceEvidenceJsonSha256")
                break
    if source_log_sha256:
        for tokens in evidence_tokens:
            if tokens.get("sourceLogSha256", "") != str(source_log_sha256):
                blockers.append(f"{rel_path} env evidence log digest does not match sourceLogSha256")
                break


def verify_promotion_env_family_keys(root, path, payload, blockers):
    rel_path = path.relative_to(root).as_posix()
    family = payload.get("signatureFamily", "")
    env = payload.get("env", {}) or {}
    if not isinstance(env, dict):
        blockers.append(f"{rel_path} package promotion env must be an object")
        return
    for key, value in env.items():
        if not isinstance(key, str) or not key:
            blockers.append(f"{rel_path} package promotion env contains an invalid key")
            return
        if isinstance(value, (dict, list)):
            blockers.append(f"{rel_path} package promotion env contains a non-scalar value for {key}")
            return
    if family == "StaticLoadClass":
        if any(key in PACKAGE_ASSET_ENV_KEYS and env.get(key) for key in env):
            blockers.append(f"{rel_path} StaticLoadClass promotion env includes LoadAsset package keys")
    elif family in ASSET_FAMILIES:
        if any(key in PACKAGE_CLASS_ENV_KEYS and env.get(key) for key in env):
            blockers.append(f"{rel_path} {family} promotion env includes LoadClass package keys")


def verify_bundled_promotion_env(root, path, blockers, evidence=None, manifest=None, checksums=None):
    rel_path = path.relative_to(root).as_posix()
    try:
        payload = load_json(path)
    except json.JSONDecodeError as exc:
        blockers.append(f"invalid JSON in {rel_path}: {exc}")
        return
    if payload.get("schemaVersion") != PROMOTION_ENV_SCHEMA:
        blockers.append(f"{rel_path} has unsupported schemaVersion")
    family = payload.get("signatureFamily", "")
    if not family:
        blockers.append(f"{rel_path} has missing signatureFamily")
    elif path.parent.name != family:
        blockers.append(f"{rel_path} signatureFamily does not match parent directory")
    verify_promotion_env_family_keys(root, path, payload, blockers)
    verify_promotion_ready_claim(root, path, payload, blockers)
    if evidence:
        verify_bundled_promotion_identity(root, path, payload, evidence, blockers, manifest, checksums)


def add_identity_blocker(blockers, rel_path, message):
    blockers.append(f"{rel_path} {message}")


def selected_trace_hit(evidence, hit_index):
    hits = evidence.get("hits", []) or []
    if not isinstance(hit_index, int) or hit_index < 0 or hit_index >= len(hits):
        return {}
    hit = hits[hit_index]
    return hit if isinstance(hit, dict) else {}


def verify_top_level_package_identity(evidence, abi_review, promotion, blockers, manifest=None, checksums=None):
    manifest = manifest or {}
    checksums = checksums or {}
    evidence_source = evidence.get("sourceLog", "")
    abi_source = abi_review.get("sourceEvidence", "")
    promotion_source = promotion.get("sourceEvidence", "")
    abi_hit_index = abi_review.get("hitIndex")
    promotion_hit_index = promotion.get("hitIndex")
    abi_family = abi_review.get("signatureFamily", "")
    promotion_family = promotion.get("signatureFamily", "")
    for rel_path, payload in (
        ("ue4ss-package-abi-review.json", abi_review),
        ("ue4ss-package-promotion-env.json", promotion),
    ):
        add_scalar_identity_blockers(
            blockers,
            rel_path,
            payload,
            (
                "sourceEvidence",
                "sourceEvidenceJson",
                "sourceEvidenceJsonSha256",
                "sourceLogSha256",
                "sourceTracePlan",
                "sourceTracePlanSchemaVersion",
                "sourcePromotionAcceptanceSchemaVersion",
                "sourceExternalPlan",
                "tracePid",
                "imageRangeSource",
                "imageBase",
                "imageStart",
                "imageEnd",
                "imagePath",
                "imagePerms",
                "selectedHitSeed",
                "callerImageOffset",
                "ripImageOffset",
            ),
        )
    if abi_source and abi_source != evidence_source:
        add_identity_blocker(blockers, "ue4ss-package-abi-review.json", "sourceEvidence does not match runtime trace evidence sourceLog")
    if (
        "sourceLogExists" in abi_review
        and "sourceLogExists" in evidence
        and abi_review.get("sourceLogExists") is not evidence.get("sourceLogExists")
    ):
        add_identity_blocker(blockers, "ue4ss-package-abi-review.json", "sourceLogExists does not match runtime trace evidence sourceLogExists")
    if present_non_true(abi_review.get("sourceLogExists")):
        add_identity_blocker(blockers, "ue4ss-package-abi-review.json", "sourceLog does not exist")
    if promotion_source and promotion_source != evidence_source:
        add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", "sourceEvidence does not match runtime trace evidence sourceLog")
    if (
        "sourceLogExists" in promotion
        and "sourceLogExists" in evidence
        and promotion.get("sourceLogExists") is not evidence.get("sourceLogExists")
    ):
        add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", "sourceLogExists does not match runtime trace evidence sourceLogExists")
    for rel_path, payload in (
        ("ue4ss-package-abi-review.json", abi_review),
        ("ue4ss-package-promotion-env.json", promotion),
    ):
        for payload_key, evidence_key in (
            ("sourceTracePlan", "sourceTracePlan"),
            ("sourceEvidenceJson", "sourceEvidenceJson"),
            ("sourceEvidenceJsonSha256", "sourceEvidenceJsonSha256"),
            ("sourceLogSha256", "sourceLogSha256"),
            ("sourceTracePlanSchemaVersion", "sourceTracePlanSchemaVersion"),
            ("sourcePromotionAcceptanceSchemaVersion", "sourcePromotionAcceptanceSchemaVersion"),
            ("sourceExternalPlan", "sourceExternalPlan"),
            ("tracePid", "pid"),
            ("imageRangeSource", "imageRangeSource"),
            ("imageBase", "imageBase"),
            ("imageStart", "imageStart"),
            ("imageEnd", "imageEnd"),
            ("imagePath", "imagePath"),
            ("imagePerms", "imagePerms"),
        ):
            payload_value = payload.get(payload_key)
            evidence_value = evidence.get(evidence_key)
            if payload_key == "sourceEvidenceJson" and evidence_value in (None, ""):
                evidence_value = manifest.get("sourceEvidenceJson", "")
            elif payload_key == "sourceEvidenceJsonSha256" and evidence_value in (None, ""):
                evidence_value = (
                    manifest.get("sourceEvidenceJsonSha256", "")
                    or checksums.get("ue4ss-package-runtime-trace-evidence.json", "")
                )
            if payload_value in (None, "") and evidence_value in (None, ""):
                continue
            if payload_key in ("sourceEvidenceJson", "sourceEvidenceJsonSha256", "sourceLogSha256"):
                if str(payload_value or "") != str(evidence_value or ""):
                    add_identity_blocker(
                        blockers,
                        rel_path,
                        f"{payload_key} does not match runtime trace evidence {evidence_key}",
                    )
                continue
            if payload_value in (None, "") or evidence_value in (None, ""):
                continue
            if str(payload_value) != str(evidence_value):
                add_identity_blocker(
                    blockers,
                    rel_path,
                    f"{payload_key} does not match runtime trace evidence {evidence_key}",
                )
    if abi_hit_index != promotion_hit_index:
        add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", "hitIndex does not match ABI review")
    if abi_family and promotion_family and abi_family != promotion_family:
        add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", "signatureFamily does not match ABI review")
    hit = selected_trace_hit(evidence, abi_hit_index)
    if isinstance(abi_hit_index, int) and not hit:
        add_identity_blocker(
            blockers,
            "ue4ss-package-abi-review.json",
            f"selected runtime trace hit is missing for hitIndex {abi_hit_index}",
        )
    if hit and hit.get("traceAddressMatchesBase") is not True:
        add_identity_blocker(
            blockers,
            "ue4ss-package-abi-review.json",
            "selected runtime trace hit address does not match image base plus seed imageOffset",
        )
    for error in register_shape_errors(hit):
        add_identity_blocker(
            blockers,
            "ue4ss-package-abi-review.json",
            f"selected runtime trace hit {error}",
        )
    for error in register_memory_shape_errors(hit):
        add_identity_blocker(
            blockers,
            "ue4ss-package-abi-review.json",
            f"selected runtime trace hit {error}",
        )
    missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(hit)
    for error in missing_required_memory_errors:
        add_identity_blocker(
            blockers,
            "ue4ss-package-abi-review.json",
            f"selected runtime trace hit {error}",
        )
    if missing_required_memory:
        add_identity_blocker(
            blockers,
            "ue4ss-package-abi-review.json",
            "selected runtime trace hit is missing required memory registers: "
            + ", ".join(str(item) for item in missing_required_memory),
        )
    if isinstance(promotion_hit_index, int) and promotion_hit_index != abi_hit_index:
        promotion_hit = selected_trace_hit(evidence, promotion_hit_index)
        if not promotion_hit:
            add_identity_blocker(
                blockers,
                "ue4ss-package-promotion-env.json",
                f"selected runtime trace hit is missing for hitIndex {promotion_hit_index}",
            )
        if promotion_hit and promotion_hit.get("traceAddressMatchesBase") is not True:
            add_identity_blocker(
                blockers,
                "ue4ss-package-promotion-env.json",
                "selected runtime trace hit address does not match image base plus seed imageOffset",
            )
        for error in register_shape_errors(promotion_hit):
            add_identity_blocker(
                blockers,
                "ue4ss-package-promotion-env.json",
                f"selected runtime trace hit {error}",
            )
        for error in register_memory_shape_errors(promotion_hit):
            add_identity_blocker(
                blockers,
                "ue4ss-package-promotion-env.json",
                f"selected runtime trace hit {error}",
            )
        missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(promotion_hit)
        for error in missing_required_memory_errors:
            add_identity_blocker(
                blockers,
                "ue4ss-package-promotion-env.json",
                f"selected runtime trace hit {error}",
            )
        if missing_required_memory:
            add_identity_blocker(
                blockers,
                "ue4ss-package-promotion-env.json",
                "selected runtime trace hit is missing required memory registers: "
                + ", ".join(str(item) for item in missing_required_memory),
            )
    expected_seed = hit.get("seed", "")
    abi_seed = abi_review.get("selectedHitSeed", "")
    promotion_seed = promotion.get("selectedHitSeed", "")
    if abi_seed and promotion_seed and abi_seed != promotion_seed:
        add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", "selectedHitSeed does not match ABI review")
    if abi_seed and expected_seed and abi_seed != expected_seed:
        add_identity_blocker(blockers, "ue4ss-package-abi-review.json", "selectedHitSeed does not match selected runtime trace hit")
    if promotion_seed and expected_seed and promotion_seed != expected_seed:
        add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", "selectedHitSeed does not match selected runtime trace hit")
    for key in ("callerImageOffset", "ripImageOffset"):
        expected = hit.get(key, "")
        reviewed = abi_review.get(key, "")
        promoted = promotion.get(key, "")
        if reviewed and promoted and reviewed != promoted:
            add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", f"{key} does not match ABI review")
        if reviewed and expected and reviewed != expected:
            add_identity_blocker(blockers, "ue4ss-package-abi-review.json", f"{key} does not match selected runtime trace hit")
        if promoted and expected and promoted != expected:
            add_identity_blocker(blockers, "ue4ss-package-promotion-env.json", f"{key} does not match selected runtime trace hit")


def trace_env_assignments(command):
    try:
        args = shlex.split(str(command))
    except ValueError as error:
        return {}, [f"command is not shell-parseable: {error}"]
    assignments = {}
    errors = []
    for arg in args:
        if arg == "env":
            continue
        if "=" not in arg:
            break
        key, value = arg.split("=", 1)
        if not key.startswith("DUNE_UE4SS_PACKAGE_TRACE_"):
            if key.startswith("-") or "/" in key or key.endswith(".sh"):
                break
            continue
        if not key.replace("_", "").isalnum():
            errors.append(f"command has malformed traceEnv key: {key}")
            continue
        if not single_line_value(value):
            errors.append(f"command traceEnv {key} must be non-empty and single-line")
            continue
        assignments[key] = value
    return assignments, errors


def replay_commands_by_action(commands):
    arm = [str(command) for command in commands if "ue4ss-package-runtime-trace.sh arm " in str(command)]
    status = [str(command) for command in commands if "ue4ss-package-runtime-trace.sh status " in str(command)]
    return arm, status


def split_command(command):
    try:
        return shlex.split(str(command))
    except ValueError:
        return []


def command_flag_values(command, flag):
    args = split_command(command)
    values = []
    for index, arg in enumerate(args):
        if arg == flag and index + 1 < len(args):
            values.append(args[index + 1])
        elif arg.startswith(f"{flag}="):
            values.append(arg.split("=", 1)[1])
    return values


def command_redirect_targets(command):
    args = split_command(command)
    targets = []
    for index, arg in enumerate(args):
        if arg == ">" and index + 1 < len(args):
            targets.append(args[index + 1])
        elif arg.startswith(">") and len(arg) > 1:
            targets.append(arg[1:])
    return targets


def artifact_source(artifacts, rel_path):
    for row in artifacts or []:
        if row.get("path", "") == rel_path:
            return row.get("source", "")
    return ""


def artifact_path_for_source(artifacts, source):
    if not source:
        return ""
    for row in artifacts or []:
        if row.get("source", "") == source:
            return row.get("path", "")
    return ""


def path_is_inside(path, root):
    try:
        Path(path).resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def bundled_input_matches(root, value, allowed_rel_paths):
    if not value:
        return False
    candidate = Path(value)
    if candidate.is_absolute():
        return path_is_inside(candidate, root) and candidate.resolve() in {
            (root / rel_path).resolve() for rel_path in allowed_rel_paths
        }
    if ".." in candidate.parts:
        return False
    normalized = candidate.as_posix()
    return normalized in allowed_rel_paths


def verify_next_canary_post_canary_outputs(next_canary, blockers):
    if not next_canary:
        return
    contract = next_canary.get("nextCanaryContract")
    if not isinstance(contract, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-canary.json",
            "nextCanaryContract must be an object",
        )
        return
    post_canary = contract.get("postCanaryVerification")
    if not isinstance(post_canary, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-canary.json",
            "postCanaryVerification must be an object",
        )
        return
    output_files = post_canary.get("outputFiles")
    if not isinstance(output_files, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-canary.json",
            "postCanaryVerification outputFiles must be an object",
        )
        return
    for key, expected in (
        ("readinessJson", "ue4ss-readiness.json"),
        ("objectDiscoveryCoverage", "object-discovery-coverage.json"),
        ("postCanaryGapSummaryJson", "ue4ss-port-gaps.json"),
        ("postCanaryGapSummary", "ue4ss-port-gaps.md"),
        ("evidenceInventoryJson", "ue4ss-evidence-inventory.json"),
        ("evidenceInventory", "ue4ss-evidence-inventory.md"),
        ("postCanarySummary", "post-canary-summary.md"),
    ):
        value = output_files.get(key)
        if not isinstance(value, str):
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-canary.json",
                f"postCanaryVerification outputFiles {key} must be a string",
            )
            continue
        if value != expected:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-canary.json",
                f"postCanaryVerification outputFiles {key} must be {expected}",
            )


def verify_plan_canary_next_action(root, next_action, artifacts, blockers, next_canary=None):
    if next_action.get("action") != "plan-canary":
        return
    verify_next_canary_post_canary_outputs(next_canary, blockers)
    commands = [str(command) for command in next_action.get("commands", []) or []]
    canary_commands = [
        command
        for command in commands
        if "scripts/plan-ue4ss-canary-env.py" in command
    ]
    if not commands:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary action is missing canary planning commands",
        )
        return
    if not canary_commands:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary action is missing plan-ue4ss-canary-env.py command",
        )
        return
    allowed_promotion_json = {"ue4ss-package-promotion-env.json"}
    allowed_summary_json = set()
    allowed_promotion_dirs = set()
    if (root / "ue4ss-package-family-reviews.json").is_file():
        allowed_summary_json.add("ue4ss-package-family-reviews.json")
    if (root / "ue4ss-package-family-reviews").is_dir():
        allowed_promotion_dirs.add("ue4ss-package-family-reviews")
    next_canary_json_source = artifact_source(artifacts, "ue4ss-package-next-canary.json")
    next_canary_env_source = artifact_source(artifacts, "ue4ss-package-next-canary.env")
    output_files = next_action.get("outputFiles", {}) or {}
    if output_files and not isinstance(output_files, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary outputFiles must be an object",
        )
        output_files = {}
    next_canary_json_seen = not next_canary_json_source
    next_canary_env_seen = not next_canary_env_source
    output_json = output_files.get("nextCanaryJson", "")
    output_env = output_files.get("nextCanaryEnv", "")
    if output_json and not isinstance(output_json, str):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary outputFiles nextCanaryJson must be a string",
        )
        output_json = ""
    if output_env and not isinstance(output_env, str):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary outputFiles nextCanaryEnv must be a string",
        )
        output_env = ""
    if output_json and not next_canary_json_source:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary outputFiles nextCanaryJson is present but ue4ss-package-next-canary.json is not bundled",
        )
    if output_env and not next_canary_env_source:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary outputFiles nextCanaryEnv is present but ue4ss-package-next-canary.env is not bundled",
        )
    if next_canary_json_source and output_json:
        if output_json != next_canary_json_source:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                "plan-canary outputFiles nextCanaryJson does not match bundled next-canary JSON source",
            )
    if next_canary_env_source and output_env:
        if output_env != next_canary_env_source:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                "plan-canary outputFiles nextCanaryEnv does not match bundled next-canary env source",
            )
    for command in canary_commands:
        promotion_values = command_flag_values(command, "--package-promotion-json")
        summary_values = command_flag_values(command, "--package-promotion-summary-json")
        dir_values = command_flag_values(command, "--package-promotion-dir")
        source_values = promotion_values + summary_values + dir_values
        if not source_values:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                "plan-canary command is missing bundled promotion input",
            )
            continue
        for value in promotion_values:
            if not bundled_input_matches(root, value, allowed_promotion_json):
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-next-action.json",
                    "plan-canary command does not reference bundled promotion manifest",
                )
        for value in summary_values:
            if not bundled_input_matches(root, value, allowed_summary_json):
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-next-action.json",
                    "plan-canary command does not reference bundled promotion summary",
                )
        for value in dir_values:
            if not bundled_input_matches(root, value, allowed_promotion_dirs):
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-next-action.json",
                    "plan-canary command does not reference bundled promotion directory",
                )
        if not any(
            bundled_input_matches(root, value, allowed_promotion_json | allowed_summary_json | allowed_promotion_dirs)
            for value in source_values
        ):
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                "plan-canary command has no usable bundled promotion input",
            )
        redirect_targets = command_redirect_targets(command)
        format_values = command_flag_values(command, "--format")
        if next_canary_json_source and next_canary_json_source in redirect_targets:
            next_canary_json_seen = True
            if "json" not in format_values:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-next-action.json",
                    "plan-canary JSON command is missing --format json",
                )
        if next_canary_env_source and next_canary_env_source in redirect_targets:
            next_canary_env_seen = True
            if "env" not in format_values:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-next-action.json",
                    "plan-canary env command is missing --format env",
                )
    if not next_canary_json_seen:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "plan-canary commands do not write bundled next-canary JSON source",
        )
    if not next_canary_env_seen:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
                "plan-canary commands do not write bundled next-canary env source",
        )


def verify_next_action_shape(next_action, blockers):
    rel_path = "ue4ss-package-next-action.json"
    action = next_action.get("action", "")
    if not isinstance(action, str) or not action:
        add_identity_blocker(blockers, rel_path, "action must be a non-empty string")
    confidence = next_action.get("confidence")
    if confidence is not None and not isinstance(confidence, str):
        add_identity_blocker(blockers, rel_path, "confidence must be a string")
    reason = next_action.get("reason")
    if reason is not None and not isinstance(reason, str):
        add_identity_blocker(blockers, rel_path, "reason must be a string")
    next_step = next_action.get("nextStep")
    if next_step is not None and not isinstance(next_step, str):
        add_identity_blocker(blockers, rel_path, "nextStep must be a string")
    trace_env = next_action.get("traceEnv")
    if trace_env is not None and not isinstance(trace_env, dict):
        add_identity_blocker(blockers, rel_path, "traceEnv must be an object")
    if isinstance(trace_env, dict):
        for key, value in trace_env.items():
            if not isinstance(key, str) or not key:
                add_identity_blocker(blockers, rel_path, "traceEnv keys must be non-empty strings")
                break
            if not isinstance(value, (str, int, float, bool)):
                add_identity_blocker(blockers, rel_path, f"traceEnv {key} must be a scalar")
                break
            if not single_line_value(str(value)):
                add_identity_blocker(blockers, rel_path, f"traceEnv {key} must be a non-empty single-line value")
                break
    commands = next_action.get("commands", [])
    if not isinstance(commands, list):
        add_identity_blocker(blockers, rel_path, "commands must be a list")
    elif any(not isinstance(command, str) for command in commands):
        add_identity_blocker(blockers, rel_path, "commands entries must be strings")
    elif any(not single_line_value(command) for command in commands):
        add_identity_blocker(blockers, rel_path, "commands entries must be non-empty single-line strings")
    pending = next_action.get("pending")
    if pending is not None and not isinstance(pending, dict):
        add_identity_blocker(blockers, rel_path, "pending must be an object")
    if isinstance(pending, dict):
        for key in ("missingReviewFlags", "missingNativeInvokeFlags", "blockers", "abiReviewBlockers"):
            values = pending.get(key)
            if values is None:
                continue
            if not isinstance(values, list):
                add_identity_blocker(blockers, rel_path, f"pending {key} must be a list")
                break
            if any(not isinstance(value, str) for value in values):
                add_identity_blocker(blockers, rel_path, f"pending {key} entries must be strings")
                break
    trace_plan_blockers = next_action.get("tracePlanBlockers")
    if trace_plan_blockers is not None and not isinstance(trace_plan_blockers, list):
        add_identity_blocker(blockers, rel_path, "tracePlanBlockers must be a list")
    elif isinstance(trace_plan_blockers, list) and any(
        not isinstance(blocker, str) for blocker in trace_plan_blockers
    ):
        add_identity_blocker(blockers, rel_path, "tracePlanBlockers entries must be strings")
    promotion_errors = next_action.get("promotionSummaryErrors")
    if promotion_errors is not None and not isinstance(promotion_errors, list):
        add_identity_blocker(blockers, rel_path, "promotionSummaryErrors must be a list")
    if isinstance(promotion_errors, list):
        for index, row in enumerate(promotion_errors):
            if not isinstance(row, dict):
                add_identity_blocker(blockers, rel_path, f"promotionSummaryErrors[{index}] must be an object")
                break
            if "path" in row and not isinstance(row.get("path"), str):
                add_identity_blocker(blockers, rel_path, f"promotionSummaryErrors[{index}].path must be a string")
                break
            if not isinstance(row.get("error", ""), str) or not row.get("error", ""):
                add_identity_blocker(blockers, rel_path, f"promotionSummaryErrors[{index}].error must be a non-empty string")
                break
    live_runbook = next_action.get("liveTraceRunbook")
    if live_runbook is not None and not isinstance(live_runbook, dict):
        add_identity_blocker(blockers, rel_path, "liveTraceRunbook must be an object")
    if isinstance(live_runbook, dict):
        for key in (
            "sourcePath",
            "recommendedCandidate",
            "remote",
            "container",
            "traceLog",
            "coordinatorFreshPreflightCommand",
            "cleanupCommand",
            "noDebuggerCheckCommand",
            "reviewBundleVerificationJson",
            "localReviewSummaryJson",
            "localReviewSummarySchemaVersion",
            "localReviewSummaryRunbookMode",
            "localReviewSummaryVerificationCommand",
            "digestProvenanceFields",
        ):
            value = live_runbook.get(key, "")
            if value and not single_line_value(str(value)):
                add_identity_blocker(blockers, rel_path, f"liveTraceRunbook {key} must be a single-line value")
                break
        command_count = live_runbook.get("commandCount")
        if command_count is not None and not positive_int(command_count):
            add_identity_blocker(blockers, rel_path, "liveTraceRunbook commandCount must be a positive integer")
        digest_fields = live_runbook.get("digestProvenanceFields")
        if digest_fields and digest_fields != LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS:
            add_identity_blocker(
                blockers,
                rel_path,
                "liveTraceRunbook digestProvenanceFields must be sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
            )
        operator_window = live_runbook.get("operatorWindow")
        if operator_window is not None and not isinstance(operator_window, dict):
            add_identity_blocker(blockers, rel_path, "liveTraceRunbook operatorWindow must be an object")


def artifact_source_for(artifacts, rel_path):
    for row in artifacts or []:
        if row.get("path", "") == rel_path:
            return row.get("source", "")
    return ""


def parse_live_runbook_remote_command(command):
    try:
        parts = shlex.split(command)
    except ValueError:
        return {
            "valid": False,
            "env": {},
            "wrapper": "",
            "action": "",
            "remote": "",
            "container": "",
            "traceLog": "",
        }
    try:
        wrapper_index = parts.index("scripts/ue4ss-package-remote-trace.sh")
    except ValueError:
        return {
            "valid": False,
            "env": {},
            "wrapper": "",
            "action": "",
            "remote": "",
            "container": "",
            "traceLog": "",
        }
    env = {}
    for item in parts[:wrapper_index]:
        if "=" not in item:
            return {
                "valid": False,
                "env": env,
                "wrapper": "scripts/ue4ss-package-remote-trace.sh",
                "action": "",
                "remote": "",
                "container": "",
                "traceLog": "",
            }
        key, value = item.split("=", 1)
        env[key] = value
    tail = parts[wrapper_index + 1 :]
    return {
        "valid": len(tail) == 4,
        "env": env,
        "wrapper": "scripts/ue4ss-package-remote-trace.sh",
        "action": tail[0] if len(tail) > 0 else "",
        "remote": tail[1] if len(tail) > 1 else "",
        "container": tail[2] if len(tail) > 2 else "",
        "traceLog": tail[3] if len(tail) > 3 else "",
    }


def verify_next_action_live_runbook(next_action, live_runbook, blockers, manifest=None, artifacts=None):
    summary = next_action.get("liveTraceRunbook")
    if summary is None:
        return
    if not isinstance(summary, dict):
        return
    manifest = manifest or {}
    commands = live_runbook.get("commands", [])
    if not isinstance(commands, list):
        add_identity_blocker(blockers, "ue4ss-package-stimulus-trace-runbook.json", "commands must be a list")
        return
    string_commands = [command for command in commands if isinstance(command, str)]
    if len(string_commands) != len(commands):
        add_identity_blocker(blockers, "ue4ss-package-stimulus-trace-runbook.json", "commands entries must be strings")
        return
    if any(not single_line_value(command) for command in string_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands entries must be non-empty single-line strings",
        )
    remote_commands = [command for command in string_commands if "operator performs" not in command]
    expected_remote = live_runbook.get("remote", "")
    expected_container = live_runbook.get("container", "")
    expected_trace_log = live_runbook.get("traceLog", "")
    if remote_commands and not all("scripts/ue4ss-package-remote-trace.sh" in command for command in remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands must use scripts/ue4ss-package-remote-trace.sh for remote live trace actions",
        )
    if expected_remote and remote_commands and not all(expected_remote in command for command in remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands do not reference live runbook remote",
        )
    if expected_container and remote_commands and not all(expected_container in command for command in remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands do not reference live runbook container",
        )
    if expected_trace_log and remote_commands and not all(expected_trace_log in command for command in remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands do not reference live runbook traceLog",
        )
    if remote_commands and not all("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false" in command for command in remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands must set DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false",
        )
    parsed_remote_commands = [parse_live_runbook_remote_command(command) for command in remote_commands]
    if parsed_remote_commands and not all(parsed.get("valid") for parsed in parsed_remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands must parse as env assignments followed by remote trace wrapper action remote container traceLog",
        )
    if parsed_remote_commands and not all(
        parsed.get("env", {}).get("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS") == "false"
        for parsed in parsed_remote_commands
    ):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "parsed commands must set DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false",
        )
    if expected_remote and parsed_remote_commands and not all(parsed.get("remote") == expected_remote for parsed in parsed_remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "parsed commands remote does not match live runbook remote",
        )
    if expected_container and parsed_remote_commands and not all(parsed.get("container") == expected_container for parsed in parsed_remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "parsed commands container does not match live runbook container",
        )
    if expected_trace_log and parsed_remote_commands and not all(parsed.get("traceLog") == expected_trace_log for parsed in parsed_remote_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "parsed commands traceLog does not match live runbook traceLog",
        )
    expected_actions = ["print", "preflight", "arm", "status", "stop"]
    observed_actions = [parsed.get("action", "") for parsed in parsed_remote_commands if parsed.get("action")]
    stop_commands = [
        command
        for command, parsed in zip(remote_commands, parsed_remote_commands)
        if parsed.get("action") == "stop"
    ]
    manual_commands = [command for command in string_commands if "operator performs" in command]
    if observed_actions != expected_actions:
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands must run remote trace actions in print, preflight, arm, status, stop order",
        )
    if len(manual_commands) != 1:
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "commands must include exactly one operator stimulus step",
        )
    elif (
        "approved client login/travel/map-entry package-load stimulus" not in manual_commands[0]
        and "approved client login/travel/map-entry package-load classification stimulus" not in manual_commands[0]
    ):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "operator stimulus step must be the approved client login/travel/map-entry package-load stimulus or classification stimulus",
        )
    cleanup_command = live_runbook.get("cleanupCommand", "")
    if not isinstance(cleanup_command, str) or not single_line_value(cleanup_command):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "cleanupCommand must be a non-empty single-line string",
        )
    elif stop_commands and cleanup_command != stop_commands[-1]:
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "cleanupCommand must match the stop command",
        )
    no_debugger_check = live_runbook.get("noDebuggerCheckCommand", "")
    if not isinstance(no_debugger_check, str) or not single_line_value(no_debugger_check):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "noDebuggerCheckCommand must be a non-empty single-line string",
        )
    elif LIVE_TRACE_RUNBOOK_NO_DEBUGGER_NEEDLE not in no_debugger_check:
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "noDebuggerCheckCommand must check for gdb/runtime trace helpers",
        )
    operator_window = live_runbook.get("operatorWindow")
    if not isinstance(operator_window, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "operatorWindow must be an object",
        )
        operator_window = {}
    elif not positive_int(operator_window.get("maxArmSeconds")):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "operatorWindow maxArmSeconds must be a positive integer",
        )
    elif operator_window.get("cleanupRequired") is not True:
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "operatorWindow cleanupRequired must be true",
        )
    elif tuple(operator_window.get("sequence", []) or []) != LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE:
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "operatorWindow sequence must preserve bounded cleanup handoff",
        )
    expected = {
        "recommendedCandidate": live_runbook.get("recommendedCandidate", ""),
        "remote": live_runbook.get("remote", ""),
        "container": live_runbook.get("container", ""),
        "traceLog": live_runbook.get("traceLog", ""),
        "coordinatorFreshPreflightCommand": live_runbook.get("coordinatorFreshPreflightCommand", ""),
        "cleanupCommand": cleanup_command,
        "noDebuggerCheckCommand": no_debugger_check,
        "operatorWindow": operator_window,
        "commandCount": len(string_commands),
    }
    if live_runbook.get("remote", "") != "kspls0":
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "remote must be kspls0",
        )
    manifest_trace_host = manifest.get("traceHost", "")
    if manifest_trace_host != "kspls0":
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "traceHost must be kspls0 when bundled stimulus trace runbook remote is kspls0",
        )
    if expected_container and not manifest.get("tracePid", "") and manifest.get("container", "") != expected_container:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "container must match bundled stimulus trace runbook container",
        )
    if expected_trace_log and manifest.get("traceLog", "") != expected_trace_log:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "traceLog must match bundled stimulus trace runbook traceLog",
        )
    trace_env = live_runbook.get("traceEnv", {}) or {}
    if not isinstance(trace_env, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "traceEnv must be an object",
        )
    else:
        for env_key, expected_env_value in LIVE_TRACE_RUNBOOK_EXPECTED_TRACE_ENV.items():
            value = trace_env.get(env_key)
            if value != expected_env_value:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-stimulus-trace-runbook.json",
                    f"traceEnv {env_key} must be {expected_env_value}",
                )
                break
    route_slot_requirement = live_runbook.get("routeSlotTraceRequirement")
    if not isinstance(route_slot_requirement, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "routeSlotTraceRequirement must be an object",
        )
        route_slot_requirement = {}
    else:
        expected_marker = route_slot_requirement.get("expectedTraceMarker", "")
        if expected_marker != "UE4SS_PACKAGE_ROUTE_TRACE_HIT":
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            )
        if route_slot_requirement.get("reviewField", "") != "routeVtableStaticSlotMatches":
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "routeSlotTraceRequirement reviewField must be routeVtableStaticSlotMatches",
            )
        required_slots = route_slot_requirement.get("requiredSlots", [])
        if not isinstance(required_slots, list) or not required_slots or any(
            not isinstance(slot, str) or not slot for slot in required_slots
        ):
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "routeSlotTraceRequirement requiredSlots must be a non-empty string array",
            )
        required_registers = route_slot_requirement.get("requiredRegisters", [])
        if not isinstance(required_registers, list) or not required_registers or any(
            not isinstance(register, str) or not register for register in required_registers
        ):
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "routeSlotTraceRequirement requiredRegisters must be a non-empty string array",
            )
        trace_inputs = live_runbook.get("traceInputs", {}) or {}
        if trace_inputs is not None and not isinstance(trace_inputs, dict):
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "traceInputs must be an object when routeSlotTraceRequirement is present",
            )
            trace_inputs = {}
        route_address = route_slot_requirement.get("routeAddress", "")
        if route_address and route_address != trace_inputs.get("routeAddress", ""):
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "routeSlotTraceRequirement routeAddress does not match traceInputs routeAddress",
            )
        summary_requirement = summary.get("routeSlotTraceRequirement")
        if summary_requirement is not None and summary_requirement != route_slot_requirement:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                "liveTraceRunbook routeSlotTraceRequirement does not match bundled stimulus trace runbook",
            )
    review_artifacts = live_runbook.get("reviewArtifacts", {}) or {}
    if not isinstance(review_artifacts, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-stimulus-trace-runbook.json",
            "reviewArtifacts must be an object",
        )
    else:
        for artifact_key, expected_artifact_value in LIVE_TRACE_RUNBOOK_EXPECTED_REVIEW_ARTIFACTS.items():
            value = review_artifacts.get(artifact_key)
            if not isinstance(value, str) or not single_line_value(value):
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-stimulus-trace-runbook.json",
                    f"reviewArtifacts {artifact_key} must be a non-empty single-line string",
                )
                break
            if value != expected_artifact_value:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-stimulus-trace-runbook.json",
                    f"reviewArtifacts {artifact_key} must be {expected_artifact_value}",
                )
                break
        expected["reviewBundleVerificationJson"] = review_artifacts.get("reviewBundleVerificationJson", "")
        if review_artifacts.get("localReviewSummaryJson"):
            expected["localReviewSummaryJson"] = review_artifacts.get("localReviewSummaryJson", "")
        expected["localReviewSummarySchemaVersion"] = review_artifacts.get("localReviewSummarySchemaVersion", "")
        expected["localReviewSummaryRunbookMode"] = review_artifacts.get("localReviewSummaryRunbookMode", "")
        expected["localReviewSummaryVerificationCommand"] = review_artifacts.get("localReviewSummaryVerificationCommand", "")
        expected["digestProvenanceFields"] = review_artifacts.get("digestProvenanceFields", "")
        if expected["localReviewSummarySchemaVersion"] != LIVE_TRACE_RUNBOOK_LOCAL_REVIEW_SUMMARY_SCHEMA:
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "reviewArtifacts localReviewSummarySchemaVersion must be dune-ue4ss-package-live-stimulus-review-summary/v1",
            )
        if expected["localReviewSummaryRunbookMode"] != "default-source-runbook;trace-log-override-effective-runbook":
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "reviewArtifacts localReviewSummaryRunbookMode must be default-source-runbook;trace-log-override-effective-runbook",
            )
        if expected["digestProvenanceFields"] != LIVE_TRACE_RUNBOOK_DIGEST_PROVENANCE_FIELDS:
            add_identity_blocker(
                blockers,
                "ue4ss-package-stimulus-trace-runbook.json",
                "reviewArtifacts digestProvenanceFields must be sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
            )
        for key in (
            "localReviewSummaryJson",
            "localReviewSummarySchemaVersion",
            "localReviewSummaryRunbookMode",
            "localReviewSummaryVerificationCommand",
        ):
            top_level_value = live_runbook.get(key, "")
            artifact_value = review_artifacts.get(key, "")
            if top_level_value and top_level_value != artifact_value:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-stimulus-trace-runbook.json",
                    f"{key} does not match reviewArtifacts {key}",
                )
    for key, value in expected.items():
        if summary.get(key) != value:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                f"liveTraceRunbook {key} does not match bundled stimulus trace runbook",
            )
    manifest_runbook_source = artifact_source_for(artifacts or [], "ue4ss-package-stimulus-trace-runbook.json")
    if manifest_runbook_source and summary.get("sourcePath", "") != manifest_runbook_source:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "liveTraceRunbook sourcePath does not match review-bundle-manifest.txt source for ue4ss-package-stimulus-trace-runbook.json",
        )


def verify_next_action_matches_trace_plan(trace_plan, next_action, manifest, blockers):
    if next_action.get("action") != "arm-trace":
        return
    recommended = trace_plan.get("recommendedTraceEnv", {}) or {}
    if not isinstance(recommended, dict):
        return
    expected_trace_env = dict(recommended)
    requested_route_addresses = trace_plan.get("requestedRouteAddresses", []) or []
    if isinstance(requested_route_addresses, list):
        route_address_env = ",".join(str(value) for value in requested_route_addresses if str(value))
        if route_address_env:
            expected_trace_env["DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS"] = route_address_env
    raw_trace_env = next_action.get("traceEnv", {}) or {}
    raw_commands = next_action.get("commands", []) or []
    if not isinstance(raw_trace_env, dict) or not isinstance(raw_commands, list):
        return
    trace_env = dict(raw_trace_env)
    commands = [command for command in raw_commands if isinstance(command, str)]
    arm_commands, status_commands = replay_commands_by_action(commands)
    manifest_container = manifest.get("container", "")
    if not commands:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "arm-trace action is missing replay commands",
        )
    if commands and not arm_commands:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "arm-trace action is missing replay arm command",
        )
    if commands and not status_commands:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "arm-trace action is missing replay status command",
        )
    replay_runtime_commands = arm_commands + status_commands
    manifest_trace_pid = manifest.get("tracePid", "")
    pid_selector = f"pid-{manifest_trace_pid}" if positive_decimal_text(manifest_trace_pid) else ""
    if (
        manifest_container
        and replay_runtime_commands
        and not all(
            manifest_container in command or (pid_selector and pid_selector in command)
            for command in replay_runtime_commands
        )
    ):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "commands do not reference review-bundle-manifest.txt container",
        )
    manifest_trace_log = manifest.get("traceLog", "")
    if manifest_trace_log and replay_runtime_commands and not all(manifest_trace_log in command for command in replay_runtime_commands):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "commands do not reference review-bundle-manifest.txt traceLog",
        )
    manifest_process_pattern = manifest.get("processPattern", "")
    action_process_pattern = trace_env.get("DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN", "")
    action_trace_pid = trace_env.get("DUNE_UE4SS_PACKAGE_TRACE_PID", "")
    manifest_trace_host = manifest.get("traceHost", "")
    action_trace_host = trace_env.get("DUNE_UE4SS_PACKAGE_TRACE_HOST", "")
    if action_trace_host and manifest_trace_host and action_trace_host != manifest_trace_host:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "traceEnv DUNE_UE4SS_PACKAGE_TRACE_HOST does not match review-bundle-manifest.txt traceHost",
        )
    if manifest_trace_host and not action_trace_host:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "traceEnv is missing DUNE_UE4SS_PACKAGE_TRACE_HOST for review-bundle-manifest.txt traceHost",
        )
    if action_process_pattern and manifest_process_pattern and action_process_pattern != manifest_process_pattern:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "traceEnv DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN does not match review-bundle-manifest.txt processPattern",
        )
    if (
        manifest_process_pattern
        and manifest_process_pattern != "DuneSandboxServer-Linux-Shipping"
        and not action_process_pattern
    ):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "traceEnv is missing DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN for non-default review-bundle processPattern",
        )
    if action_trace_pid and manifest_trace_pid and str(action_trace_pid) != str(manifest_trace_pid):
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "traceEnv DUNE_UE4SS_PACKAGE_TRACE_PID does not match review-bundle-manifest.txt tracePid",
        )
    if manifest_trace_pid and not action_trace_pid:
        add_identity_blocker(
            blockers,
            "ue4ss-package-next-action.json",
            "traceEnv is missing DUNE_UE4SS_PACKAGE_TRACE_PID for review-bundle-manifest.txt tracePid",
        )
    if manifest_trace_pid and not positive_decimal_text(manifest_trace_pid):
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "tracePid must be numeric",
        )
    if not expected_trace_env:
        return
    allowed_trace_env_keys = {
        key
        for key in expected_trace_env
        if key.startswith("DUNE_UE4SS_PACKAGE_TRACE_")
    }
    allowed_trace_env_keys.update(TRACE_PLAN_PROVENANCE_ENV_KEYS)
    if manifest_process_pattern:
        allowed_trace_env_keys.add("DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN")
    if manifest_trace_pid:
        allowed_trace_env_keys.add("DUNE_UE4SS_PACKAGE_TRACE_PID")
    if manifest_trace_host:
        allowed_trace_env_keys.add("DUNE_UE4SS_PACKAGE_TRACE_HOST")
    for key in trace_env:
        if key.startswith("DUNE_UE4SS_PACKAGE_TRACE_") and key not in allowed_trace_env_keys:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                f"traceEnv {key} is not present in runtime trace plan",
            )
    for command in commands:
        command_assignments, command_errors = trace_env_assignments(command)
        for error in command_errors:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                error,
            )
        for key in command_assignments:
            if key not in allowed_trace_env_keys:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-next-action.json",
                    f"commands include unexpected traceEnv {key} not present in runtime trace plan",
                )
    for key, value in sorted(expected_trace_env.items()):
        if not key.startswith("DUNE_UE4SS_PACKAGE_TRACE_"):
            continue
        if trace_env.get(key) != value:
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                f"traceEnv {key} does not match runtime trace plan",
            )
        if commands and not all(
            trace_env_assignments(command)[0].get(key) == str(value)
            for command in commands
        ):
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                f"commands do not include traceEnv {key} from runtime trace plan",
            )
    for key, value in sorted(trace_env.items()):
        if not key.startswith("DUNE_UE4SS_PACKAGE_TRACE_"):
            continue
        if key in expected_trace_env:
            continue
        if commands and not all(
            trace_env_assignments(command)[0].get(key) == str(value)
            for command in commands
        ):
            add_identity_blocker(
                blockers,
                "ue4ss-package-next-action.json",
                f"commands do not include traceEnv {key} from next action traceEnv",
            )


def verify_manifest_matches_trace_inputs(root, manifest, trace_plan, evidence, blockers, artifacts=None, checksums=None):
    seed_count = trace_plan.get("seedCount", "")
    if seed_count != "" and (not isinstance(seed_count, int) or isinstance(seed_count, bool) or seed_count < 0):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "seedCount must be a non-negative integer",
        )
    for key in ("expectedBuildId", "runtimeBuildId"):
        if not valid_build_id(trace_plan.get(key, "")):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"{key} must be hex, empty, or unknown",
            )
    plan_acceptance_schema = trace_plan.get("sourcePromotionAcceptanceSchemaVersion", "")
    if plan_acceptance_schema != PROMOTION_ACCEPTANCE_SCHEMA:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            f"sourcePromotionAcceptanceSchemaVersion must be {PROMOTION_ACCEPTANCE_SCHEMA}",
        )
    for evidence_key, plan_key in (
        ("sourceTracePlanSchemaVersion", "schemaVersion"),
        ("sourcePromotionAcceptanceSchemaVersion", "sourcePromotionAcceptanceSchemaVersion"),
        ("sourceExternalPlan", "sourceExternalPlan"),
    ):
        evidence_value = evidence.get(evidence_key, "")
        plan_value = trace_plan.get(plan_key, "")
        if not evidence_value:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-evidence.json",
                f"{evidence_key} is missing for bundled runtime trace plan provenance",
            )
            continue
        if plan_value != "" and str(evidence_value) != str(plan_value):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-evidence.json",
                f"{evidence_key} does not match runtime trace plan {plan_key}",
            )
    if evidence.get("sourceTracePlan", ""):
        evidence_trace_plan = str(evidence.get("sourceTracePlan", ""))
        evidence_plan_name = Path(evidence_trace_plan).name
        if evidence_plan_name != "ue4ss-package-runtime-trace-plan.json":
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-evidence.json",
                "sourceTracePlan does not reference bundled runtime trace plan artifact",
            )
        trace_plan_source = artifact_source(artifacts or [], "ue4ss-package-runtime-trace-plan.json")
        if trace_plan_source and evidence_trace_plan != trace_plan_source:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-evidence.json",
                "sourceTracePlan does not match bundled runtime trace plan artifact source",
            )
    manifest_trace_plan = manifest.get("sourceTracePlan", "")
    trace_plan_source = artifact_source(artifacts or [], "ue4ss-package-runtime-trace-plan.json")
    evidence_trace_plan = str(evidence.get("sourceTracePlan", ""))
    if manifest_trace_plan:
        if evidence_trace_plan and manifest_trace_plan != evidence_trace_plan:
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                "sourceTracePlan does not match runtime trace evidence sourceTracePlan",
            )
        if trace_plan_source and manifest_trace_plan != trace_plan_source:
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                "sourceTracePlan does not match bundled runtime trace plan artifact source",
            )
    for manifest_key, plan_key in (
        ("tracePlanSourceExternalPlan", "sourceExternalPlan"),
        ("tracePlanPromotionAcceptanceSchema", "sourcePromotionAcceptanceSchemaVersion"),
        ("tracePlanBase", "base"),
        ("tracePlanExpectedBuildId", "expectedBuildId"),
        ("tracePlanRuntimeBuildId", "runtimeBuildId"),
        ("tracePlanSeedCount", "seedCount"),
    ):
        manifest_value = manifest.get(manifest_key, "")
        plan_value = trace_plan.get(plan_key, "")
        if manifest_value and plan_value != "" and str(manifest_value) != str(plan_value):
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                f"{manifest_key} does not match runtime trace plan {plan_key}",
            )
    manifest_blocker_count = manifest.get("tracePlanBlockerCount", "")
    plan_blockers, plan_blocker_errors = string_list_field(trace_plan, "blockers")
    for error in plan_blocker_errors:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            f"blockers {error}",
        )
    if manifest_blocker_count != "":
        plan_blocker_count = len(plan_blockers)
        if str(manifest_blocker_count) != str(plan_blocker_count):
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                "tracePlanBlockerCount does not match runtime trace plan blockers",
            )
    for blocker in plan_blockers:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            f"runtime trace plan has blocker: {blocker}",
        )
    recommended = trace_plan.get("recommendedTraceEnv", {}) or {}
    manifest_selected = manifest.get("tracePlanSelectedByFamily", "")
    seed_selection = trace_plan.get("seedSelection", {}) or {}
    selected_by_family = {}
    if not isinstance(seed_selection, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "seedSelection must be a JSON object",
        )
    else:
        selected_by_family = validate_selected_by_family(
            seed_selection.get("selectedByFamily", {}),
            "seedSelection",
            blockers,
        )
    plan_selected = selected_by_family_text(selected_by_family)
    if manifest_selected and manifest_selected != plan_selected:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "tracePlanSelectedByFamily does not match runtime trace plan seedSelection selectedByFamily",
        )
    manifest_seed_offsets = manifest.get("tracePlanSeedOffsets", "")
    plan_seed_offsets = trace_plan_seed_offsets_text(trace_plan_seed_rows(trace_plan, blockers))
    if manifest_seed_offsets and manifest_seed_offsets != plan_seed_offsets:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "tracePlanSeedOffsets does not match runtime trace plan seeds",
        )
    verify_trace_plan_recommended_env(trace_plan, recommended, blockers)
    if not isinstance(recommended, dict):
        recommended = {}
    for manifest_key, env_key in (
        ("tracePlanRecommendedAnchor", "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR"),
        ("tracePlanRecommendedLimit", "DUNE_UE4SS_PACKAGE_TRACE_LIMIT"),
        ("tracePlanRecommendedSignatureFamily", "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY"),
        ("tracePlanRecommendedHitIndex", "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX"),
    ):
        manifest_value = manifest.get(manifest_key, "")
        plan_value = recommended.get(env_key, "")
        if manifest_value and plan_value != "" and str(manifest_value) != str(plan_value):
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                f"{manifest_key} does not match runtime trace plan recommendedTraceEnv {env_key}",
            )
    manifest_family = manifest.get("signatureFamily", "")
    plan_family = recommended.get("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY", "")
    if manifest_family and plan_family and manifest_family != plan_family:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "signatureFamily does not match runtime trace plan",
        )
    manifest_hit_index = manifest.get("hitIndex", "")
    plan_hit_index = recommended.get("DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX", "")
    if manifest_hit_index and plan_hit_index and str(manifest_hit_index) != str(plan_hit_index):
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "hitIndex does not match runtime trace plan",
        )
    manifest_trace_log = manifest.get("traceLog", "")
    evidence_source = evidence.get("sourceLog", "")
    if manifest_trace_log and evidence_source and manifest_trace_log != evidence_source:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "traceLog does not match runtime trace evidence sourceLog",
        )
    trace_log_rel_path = artifact_path_for_source(artifacts or [], manifest_trace_log or evidence_source)
    if str(manifest.get("sourceLogExists", "")).lower() == "true" and not trace_log_rel_path:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "traceLog artifact is missing for existing runtime trace sourceLog",
        )
    if trace_log_rel_path:
        trace_log_path = Path(root) / trace_log_rel_path
        if trace_log_path.is_file():
            manifest_log_sha = manifest.get("sourceLogSha256", "")
            actual_log_sha = sha256(trace_log_path)
            checksum_log_sha = (checksums or {}).get(trace_log_rel_path, "")
            if manifest_log_sha != actual_log_sha:
                add_identity_blocker(
                    blockers,
                    "review-bundle-manifest.txt",
                    "sourceLogSha256 does not match bundled runtime trace log sha256",
                )
            if checksum_log_sha and manifest_log_sha != checksum_log_sha:
                add_identity_blocker(
                    blockers,
                    "review-bundle-manifest.txt",
                    "sourceLogSha256 does not match SHA256SUMS for runtime trace log",
                )
    evidence_json_source = artifact_source(artifacts or [], "ue4ss-package-runtime-trace-evidence.json")
    manifest_evidence_json = manifest.get("sourceEvidenceJson", "")
    if evidence_json_source and manifest_evidence_json != evidence_json_source:
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "sourceEvidenceJson does not match bundled runtime trace evidence artifact source",
        )
    evidence_json_path = Path(root) / "ue4ss-package-runtime-trace-evidence.json"
    if evidence_json_path.is_file():
        manifest_evidence_sha = manifest.get("sourceEvidenceJsonSha256", "")
        actual_evidence_sha = sha256(evidence_json_path)
        checksum_evidence_sha = (checksums or {}).get("ue4ss-package-runtime-trace-evidence.json", "")
        if manifest_evidence_sha != actual_evidence_sha:
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                "sourceEvidenceJsonSha256 does not match bundled runtime trace evidence JSON sha256",
            )
        if checksum_evidence_sha and manifest_evidence_sha != checksum_evidence_sha:
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                "sourceEvidenceJsonSha256 does not match SHA256SUMS for runtime trace evidence JSON",
            )
    for manifest_key, evidence_key in (
        ("sourceLogExists", "sourceLogExists"),
        ("sourceLogSha256", "sourceLogSha256"),
        ("evidencePid", "pid"),
        ("tracePidMatchesRequested", "tracePidMatchesRequested"),
        ("imageRangeSource", "imageRangeSource"),
        ("imageBase", "imageBase"),
        ("imageStart", "imageStart"),
        ("imageEnd", "imageEnd"),
        ("imagePath", "imagePath"),
        ("imagePerms", "imagePerms"),
    ):
        manifest_value = manifest.get(manifest_key, "")
        evidence_value = evidence.get(evidence_key, "")
        if manifest_key == "tracePidMatchesRequested" and evidence_value is not None and manifest_value == "":
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                "tracePidMatchesRequested is missing for runtime trace evidence tracePidMatchesRequested",
            )
            continue
        if manifest_value and evidence_value is not None and str(manifest_value) != str(evidence_value):
            add_identity_blocker(
                blockers,
                "review-bundle-manifest.txt",
                f"{manifest_key} does not match runtime trace evidence {evidence_key}",
            )
    manifest_trace_pid = manifest.get("tracePid", "")
    evidence_pid = evidence.get("pid", "")
    if manifest_trace_pid and evidence_pid is not None and str(manifest_trace_pid) != str(evidence_pid):
        add_identity_blocker(
            blockers,
            "review-bundle-manifest.txt",
            "tracePid does not match runtime trace evidence pid",
        )
    verify_runtime_route_slot_recovery(evidence, blockers)


def verify_runtime_route_slot_recovery(evidence, blockers):
    route_hit_count = evidence.get("routeHitCount", 0)
    if not isinstance(route_hit_count, int) or isinstance(route_hit_count, bool):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeHitCount must be an integer",
        )
        return
    if route_hit_count <= 0:
        return
    recovery = evidence.get("routeSlotRecovery")
    if not isinstance(recovery, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery is missing for route hit evidence",
        )
        return
    if recovery.get("routeHitCount") != route_hit_count:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery routeHitCount does not match routeHitCount",
        )
    required_slots = recovery.get("requiredSlots", [])
    if not isinstance(required_slots, list) or not required_slots or any(
        not isinstance(slot, str) or not slot for slot in required_slots
    ):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery requiredSlots must be a non-empty string array",
        )
    for key in ("presentSlots", "missingSlots", "blockers"):
        value = recovery.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-evidence.json",
                f"routeSlotRecovery {key} must be a string array",
            )
    matches = recovery.get("matches", [])
    if not isinstance(matches, list):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery matches must be an array",
        )
        matches = []
    if recovery.get("matchCount") != len(matches):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery matchCount does not match matches length",
        )
    if recovery.get("ready") is True and recovery.get("missingSlots"):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery ready cannot be true while missingSlots is non-empty",
        )
    if recovery.get("ready") is False and not recovery.get("blockers"):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery blockers must explain false readiness",
        )


def verify_runtime_route_slot_recovery_matches_runbook(evidence, live_runbook, blockers):
    if not isinstance(evidence, dict) or not isinstance(live_runbook, dict):
        return
    requirement = live_runbook.get("routeSlotTraceRequirement")
    if not isinstance(requirement, dict) or not requirement:
        return
    recovery = evidence.get("routeSlotRecovery")
    if not isinstance(recovery, dict):
        return
    expected_slots = requirement.get("requiredSlots", [])
    if isinstance(expected_slots, list) and expected_slots and recovery.get("requiredSlots") != expected_slots:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-evidence.json",
            "routeSlotRecovery requiredSlots do not match bundled routeSlotTraceRequirement",
        )
    expected_route = requirement.get("routeAddress", "")
    route_hits = evidence.get("routeHits", [])
    if expected_route and isinstance(route_hits, list) and route_hits:
        observed_routes = {
            str(row.get("imageOffset", "") or row.get("callerImageOffset", ""))
            for row in route_hits
            if isinstance(row, dict)
        }
        if expected_route not in observed_routes:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-evidence.json",
                "routeHits do not include bundled routeSlotTraceRequirement routeAddress",
            )


def verify_trace_plan_supports_route_slot_requirement(trace_plan, live_runbook, blockers):
    if not isinstance(trace_plan, dict) or not isinstance(live_runbook, dict):
        return
    requirement = live_runbook.get("routeSlotTraceRequirement")
    if not isinstance(requirement, dict) or not requirement:
        return
    route_address = requirement.get("routeAddress", "")
    required_registers = requirement.get("requiredRegisters", [])
    if not isinstance(required_registers, list):
        required_registers = []
    route_gdb = trace_plan.get("routeGdb", "")
    if not isinstance(route_gdb, str):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "routeGdb must be a string when routeSlotTraceRequirement is present",
        )
        route_gdb = ""
    if route_address:
        requested_routes = trace_plan.get("requestedRouteAddresses", [])
        route_probes = trace_plan.get("routeProbes", [])
        if isinstance(requested_routes, list) and route_address not in requested_routes:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                "requestedRouteAddresses does not include bundled routeSlotTraceRequirement routeAddress",
            )
        if isinstance(route_probes, list):
            probe_addresses = [
                row.get("address", "")
                for row in route_probes
                if isinstance(row, dict)
            ]
            if route_address not in probe_addresses:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-runtime-trace-plan.json",
                    "routeProbes does not include bundled routeSlotTraceRequirement routeAddress",
                )
        if route_address not in route_gdb:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                "routeGdb does not include bundled routeSlotTraceRequirement routeAddress",
            )
    if "UE4SS_PACKAGE_ROUTE_TRACE_HIT" not in route_gdb:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "routeGdb is missing UE4SS_PACKAGE_ROUTE_TRACE_HIT capture",
        )
    for register in required_registers:
        if not isinstance(register, str) or not register:
            continue
        if f"{register}=%p" not in route_gdb:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"routeGdb is missing required register print for {register}",
            )
        if f"UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={register}" not in route_gdb:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"routeGdb is missing required object capture for {register}",
            )
        if f"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={register}" not in route_gdb:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"routeGdb is missing required vtable capture for {register}",
            )


def positive_counts(mapping):
    if not isinstance(mapping, dict):
        return {}
    return {
        str(key): int(value)
        for key, value in (mapping or {}).items()
        if str(key) and isinstance(value, int) and value > 0
    }


def selected_by_family_text(mapping):
    counts = positive_counts(mapping)
    return ",".join(f"{key}:{counts[key]}" for key in sorted(counts))


def validate_selected_by_family(mapping, label, blockers):
    if mapping is None:
        return {}
    if not isinstance(mapping, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            f"{label} selectedByFamily must be a JSON object",
        )
        return {}
    counts = {}
    for family, count in mapping.items():
        if not isinstance(family, str) or not family:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"{label} selectedByFamily keys must be non-empty strings",
            )
            continue
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"{label} selectedByFamily values must be positive integers",
            )
            continue
        counts[family] = count
    return counts


def trace_plan_seed_offsets_text(seeds):
    rows = []
    for seed in seeds or []:
        if not isinstance(seed, dict):
            continue
        name = seed.get("name", "")
        address = seed.get("address", "")
        if name and address:
            rows.append(f"{name}@{address}")
    return ",".join(rows)


def trace_plan_seed_rows(trace_plan, blockers):
    seeds = trace_plan.get("seeds", [])
    if seeds is None:
        return []
    if not isinstance(seeds, list):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "seeds must be a JSON array",
        )
        return []
    valid = []
    for index, seed in enumerate(seeds):
        if not isinstance(seed, dict):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"seeds[{index}] must be a JSON object",
            )
            continue
        for key in ("name", "address"):
            if key in seed and not isinstance(seed.get(key), str):
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-runtime-trace-plan.json",
                    f"seeds[{index}].{key} must be a string",
                )
        valid.append(seed)
    return valid


def verify_trace_plan_recommended_env(trace_plan, recommended, blockers):
    if recommended is not None and not isinstance(recommended, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "recommendedTraceEnv must be an object",
        )
        return
    if not recommended:
        return
    for key, value in recommended.items():
        if not isinstance(key, str) or not key:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                "recommendedTraceEnv keys must be non-empty strings",
            )
            return
        if key != "selectedByFamily" and not isinstance(value, (str, int, float, bool)):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"recommendedTraceEnv {key} must be a scalar",
            )
            return
    selected_from_env = validate_selected_by_family(
        recommended.get("selectedByFamily", {}),
        "recommendedTraceEnv",
        blockers,
    )
    raw_seed_selection = trace_plan.get("seedSelection", {}) or {}
    selected_from_selection = {}
    if not isinstance(raw_seed_selection, dict):
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "seedSelection must be a JSON object",
        )
    else:
        selected_from_selection = validate_selected_by_family(
            raw_seed_selection.get("selectedByFamily", {}),
            "seedSelection",
            blockers,
        )
    if selected_from_env and selected_from_selection and selected_from_env != selected_from_selection:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            "recommendedTraceEnv selectedByFamily does not match seedSelection selectedByFamily",
        )

    selected_counts = selected_from_env or selected_from_selection
    if selected_counts:
        anchor_value = str(recommended.get("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR", ""))
        anchor_families = [part.strip() for part in anchor_value.split(",") if part.strip()]
        unsupported = [family for family in anchor_families if family not in PACKAGE_TRACE_ANCHORS]
        if unsupported:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                f"recommendedTraceEnv has unsupported trace anchor: {unsupported[0]}",
            )
        if set(anchor_families) != set(selected_counts):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                "recommendedTraceEnv anchors do not match selected trace seed families",
            )
    signature_family = str(recommended.get("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY", "")).strip()
    if signature_family and signature_family not in PACKAGE_TRACE_ANCHORS:
        add_identity_blocker(
            blockers,
            "ue4ss-package-runtime-trace-plan.json",
            f"recommendedTraceEnv has unsupported signature family: {signature_family}",
        )
    hit_index = recommended.get("DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX")
    if hit_index is not None and str(hit_index) != "auto":
        try:
            if int(str(hit_index)) < 0:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-runtime-trace-plan.json",
                    "recommendedTraceEnv hit index must be non-negative or auto",
                )
        except ValueError:
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                "recommendedTraceEnv hit index must be an integer or auto",
            )

    seed_count = trace_plan.get("seedCount", "")
    limit_value = recommended.get("DUNE_UE4SS_PACKAGE_TRACE_LIMIT", "")
    if seed_count != "" and limit_value != "":
        try:
            seed_count_int = int(seed_count)
            limit_int = int(str(limit_value), 0)
            max_watchpoints_raw = trace_plan.get("hardwareReadWatchpointLimit", "")
            max_watchpoints_int = int(str(max_watchpoints_raw), 0) if max_watchpoints_raw != "" else seed_count_int
        except (TypeError, ValueError):
            add_identity_blocker(
                blockers,
                "ue4ss-package-runtime-trace-plan.json",
                "recommendedTraceEnv limit, seedCount, or maxHardwareReadWatchpoints is not an integer",
            )
        else:
            if limit_int < 1:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-runtime-trace-plan.json",
                    "recommendedTraceEnv limit must be positive",
                )
            if max_watchpoints_int < 1:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-runtime-trace-plan.json",
                    "recommendedTraceEnv maxHardwareReadWatchpoints must be positive",
                )
            expected_limit = min(seed_count_int, max_watchpoints_int)
            if seed_count_int > 0 and limit_int != expected_limit:
                add_identity_blocker(
                    blockers,
                    "ue4ss-package-runtime-trace-plan.json",
                    "recommendedTraceEnv limit does not match hardware-safe selected trace seed count",
                )


def verify_optional_promotion_summary(root, blockers):
    path = root / "ue4ss-package-family-reviews.json"
    if not path.is_file():
        return
    rel_path = path.relative_to(root).as_posix()
    try:
        payload = load_json(path)
    except json.JSONDecodeError as exc:
        blockers.append(f"invalid JSON in {rel_path}: {exc}")
        return
    if not isinstance(payload, dict):
        blockers.append(f"{rel_path} must be a JSON object")
        return
    if payload.get("schemaVersion") != PROMOTION_SUMMARY_SCHEMA:
        blockers.append(f"{rel_path} has unsupported schemaVersion")
    summary_errors = payload.get("errors", [])
    if summary_errors is None:
        summary_errors = []
    if not isinstance(summary_errors, list):
        blockers.append(f"{rel_path} errors must be a JSON array")
        summary_errors = []
    if payload.get("errorCount", 0) or summary_errors:
        first_error_row = summary_errors[0] if summary_errors else {}
        first_error = first_error_row.get("error", "unknown") if isinstance(first_error_row, dict) else str(first_error_row)
        blockers.append(f"{rel_path} has promotion summary errors: {first_error}")
    ready_manifest_paths = payload.get("readyManifestPaths", [])
    if ready_manifest_paths is None:
        ready_manifest_paths = []
    if not isinstance(ready_manifest_paths, list):
        blockers.append(f"{rel_path} readyManifestPaths must be a JSON array")
        ready_manifest_paths = []
    manifest_rows = payload.get("manifests", [])
    if manifest_rows is None:
        manifest_rows = []
    if not isinstance(manifest_rows, list):
        blockers.append(f"{rel_path} manifests must be a JSON array")
        manifest_rows = []
    seen_ready_paths = set()
    for raw_path in ready_manifest_paths:
        if not isinstance(raw_path, str) or not raw_path:
            blockers.append(f"{rel_path} has invalid readyManifestPaths entry")
            continue
        if raw_path in seen_ready_paths:
            blockers.append(f"{rel_path} duplicate readyManifestPaths entry")
            continue
        seen_ready_paths.add(raw_path)
    ready_rows = {}
    for index, row in enumerate(manifest_rows):
        if not isinstance(row, dict):
            blockers.append(f"{rel_path} manifest row {index} must be a JSON object")
            continue
        if row.get("readyForNonInvokingCanary") is not True and row.get("readyForNativeInvoke") is not True:
            continue
        raw_path = str(row.get("path", ""))
        if raw_path in ready_rows:
            blockers.append(f"{rel_path} duplicate ready package promotion summary row")
            continue
        ready_rows[raw_path] = row
    ready_paths = [
        raw_path
        for raw_path in ready_manifest_paths
        if isinstance(raw_path, str) and raw_path
    ]
    omitted_ready_paths = sorted(set(ready_rows) - set(ready_paths))
    if omitted_ready_paths:
        blockers.append(f"{rel_path} ready summary row is missing from readyManifestPaths")
    for raw_path in ready_manifest_paths:
        if not isinstance(raw_path, str) or not raw_path:
            continue
        row = ready_rows.get(raw_path)
        if row is None:
            blockers.append(f"{rel_path} ready manifest path is not backed by a ready manifest row")
            continue
        family = row.get("signatureFamily", "")
        if not family:
            blockers.append(f"{rel_path} ready summary row is missing signatureFamily")
            continue
        manifest_path = root / "ue4ss-package-family-reviews" / family / "promotion-env.json"
        if not manifest_path.is_file():
            blockers.append(f"{rel_path} ready summary row has no bundled promotion manifest for {family}")
            continue
        try:
            manifest = load_json(manifest_path)
        except json.JSONDecodeError as exc:
            blockers.append(f"invalid JSON in {manifest_path.relative_to(root).as_posix()}: {exc}")
            continue
        if not isinstance(manifest, dict):
            blockers.append(f"{manifest_path.relative_to(root).as_posix()} must be a JSON object")
            continue
        priority_path = manifest_path.parent / "review-priority.json"
        if priority_path.is_file():
            try:
                priority = load_json(priority_path)
            except json.JSONDecodeError as exc:
                blockers.append(f"invalid JSON in {priority_path.relative_to(root).as_posix()}: {exc}")
                priority = {}
            if not isinstance(priority, dict):
                blockers.append(f"{priority_path.relative_to(root).as_posix()} must be a JSON object")
                priority = {}
            if "reviewPriority" in row and row.get("reviewPriority") != priority.get("rank"):
                blockers.append(f"{rel_path} ready summary row reviewPriority does not match bundled review priority")
            if "reviewPriorityHitIndex" in row and row.get("reviewPriorityHitIndex") != priority.get("hitIndex"):
                blockers.append(f"{rel_path} ready summary row reviewPriorityHitIndex does not match bundled review priority")
        for field in SUMMARY_MANIFEST_MATCH_FIELDS:
            if field in row and row.get(field) != manifest.get(field):
                blockers.append(f"{rel_path} ready summary row {field} does not match bundled promotion manifest")
                break
        for error in scalar_identity_errors(
            row,
            (
                "sourceEvidence",
                "tracePid",
                "imageRangeSource",
                "imageBase",
                "imageStart",
                "imageEnd",
                "imagePath",
                "imagePerms",
                "selectedHitSeed",
                "callerImageOffset",
                "ripImageOffset",
            ),
        ):
            blockers.append(f"{rel_path} ready summary row {error}")
        row_blockers, row_blocker_errors = string_list_field(row, "blockers")
        for error in row_blocker_errors:
            blockers.append(f"{rel_path} ready summary row {error}")
        row_missing_flags, row_missing_flag_errors = string_list_field(row, "missingReviewFlags")
        for error in row_missing_flag_errors:
            blockers.append(f"{rel_path} ready summary row {error}")
        row_abi_blockers, row_abi_blocker_errors = string_list_field(row, "abiReviewBlockers")
        for error in row_abi_blocker_errors:
            blockers.append(f"{rel_path} ready summary row {error}")
        row_missing_native_flags, row_missing_native_flag_errors = string_list_field(
            row,
            "missingNativeInvokeFlags",
        )
        for error in row_missing_native_flag_errors:
            blockers.append(f"{rel_path} ready summary row {error}")
        if row_blockers:
            blockers.append(f"{rel_path} ready summary row still has blockers")
        if row_abi_blockers:
            blockers.append(f"{rel_path} ready summary row still has ABI review blockers")
        if row.get("abiReviewReady") is not True:
            blockers.append(f"{rel_path} ready summary row is missing ABI review readiness")
        if row.get("abiReviewed") is not True:
            blockers.append(f"{rel_path} ready summary row is missing reviewed ABI confirmation")
        if row.get("targetImageReviewed") is not True:
            blockers.append(f"{rel_path} ready summary row is missing reviewed target-image confirmation")
        if family == "StaticLoadClass" and row.get("classRootReviewed") is not True:
            blockers.append(f"{rel_path} ready summary row is missing reviewed class-root confirmation")
        if family in ASSET_FAMILIES and row.get("tcharReviewed") is not True:
            blockers.append(f"{rel_path} ready summary row is missing reviewed TCHAR confirmation")
        if row.get("readyForNativeInvoke") is True and row.get("nativeInvokeEnabled") is not True:
            blockers.append(f"{rel_path} ready native summary row is missing native invoke enablement")
        if row.get("readyForNativeInvoke") is True and row.get("finalNativeCallConfirmed") is not True:
            blockers.append(f"{rel_path} ready native summary row is missing final native-call confirmation")
        if row_missing_flags:
            blockers.append(f"{rel_path} ready summary row still has missing review flags")
        if row.get("readyForNativeInvoke") is True and row.get("readyForNonInvokingCanary") is not True:
            blockers.append(f"{rel_path} ready native summary row is missing non-invoking canary readiness")
        if row.get("readyForNativeInvoke") is True and row_missing_native_flags:
            blockers.append(f"{rel_path} ready native summary row still has missing native invoke flags")
        if not row.get("sourceEvidence", ""):
            blockers.append(f"{rel_path} ready summary row is missing sourceEvidence")
        if not row.get("sourceEvidenceJsonSha256", ""):
            blockers.append(f"{rel_path} ready summary row is missing sourceEvidenceJsonSha256 provenance")
        elif not valid_sha256_text(row.get("sourceEvidenceJsonSha256", "")):
            blockers.append(f"{rel_path} ready summary row has invalid sourceEvidenceJsonSha256")
        if not row.get("sourceLogSha256", ""):
            blockers.append(f"{rel_path} ready summary row is missing sourceLogSha256 provenance")
        elif not valid_sha256_text(row.get("sourceLogSha256", "")):
            blockers.append(f"{rel_path} ready summary row has invalid sourceLogSha256")
        if "sourceLogExists" not in row:
            blockers.append(f"{rel_path} ready summary row is missing sourceLogExists")
        elif row.get("sourceLogExists") is not True:
            blockers.append(f"{rel_path} ready summary row sourceLog does not exist")
        if "tracePidMatchesRequested" not in row:
            blockers.append(f"{rel_path} ready summary row is missing runtime trace PID match provenance")
        elif row.get("tracePidMatchesRequested") is not True:
            blockers.append(f"{rel_path} ready summary row trace log armed PID does not match requested runtime PID")
        if not positive_int(row.get("tracePid")):
            blockers.append(f"{rel_path} ready summary row is missing concrete tracePid")
        if not non_negative_int(row.get("hitIndex")):
            blockers.append(f"{rel_path} ready summary row is missing concrete hitIndex")
        if not row.get("selectedHitSeed", ""):
            blockers.append(f"{rel_path} ready summary row is missing selectedHitSeed")
        if row.get("selectedHitSeed", "") and family and row.get("selectedHitSeed") != family:
            blockers.append(f"{rel_path} ready summary row selectedHitSeed does not match signatureFamily")
        if not row.get("callerImageOffset", ""):
            blockers.append(f"{rel_path} ready summary row is missing callerImageOffset")
        elif not valid_image_offset(row.get("callerImageOffset", "")):
            blockers.append(f"{rel_path} ready summary row has invalid callerImageOffset")
        if not row.get("ripImageOffset", ""):
            blockers.append(f"{rel_path} ready summary row is missing ripImageOffset")
        elif not valid_image_offset(row.get("ripImageOffset", "")):
            blockers.append(f"{rel_path} ready summary row has invalid ripImageOffset")
        row_hit = row.get("hit", {}) or {}
        if isinstance(row_hit, dict) and row_hit:
            if present_non_true(row_hit.get("traceLogHasArmed")):
                blockers.append(f"{rel_path} ready summary row embedded trace hit missing trace armed record; cannot prove runtime trace session")
            if present_non_true(row_hit.get("tracePidMatchesRequested")):
                blockers.append(f"{rel_path} ready summary row embedded trace hit trace log armed PID does not match requested runtime PID")
            if row_hit.get("traceAddressMatchesBase") is not True:
                blockers.append(f"{rel_path} ready summary row embedded trace hit address does not match image base plus seed imageOffset")
        env = row.get("env", {}) or {}
        if family == "StaticLoadClass":
            if any(key in PACKAGE_ASSET_ENV_KEYS and env.get(key) for key in env):
                blockers.append(f"{rel_path} StaticLoadClass ready summary row env includes LoadAsset package keys")
        elif family in ASSET_FAMILIES:
            if any(key in PACKAGE_CLASS_ENV_KEYS and env.get(key) for key in env):
                blockers.append(f"{rel_path} {family} ready summary row env includes LoadClass package keys")
        verify_runtime_trace_env_evidence(root, path, row, blockers)


def verify_bundle(root):
    root = Path(root)
    blockers = []
    warnings = []
    manifest_path = root / "review-bundle-manifest.txt"
    sums_path = root / "SHA256SUMS"
    if not root.exists() or not root.is_dir():
        blockers.append(f"bundle directory does not exist: {root}")
        return result(root, {}, [], {}, blockers, warnings)
    manifest = {}
    artifacts = []
    if manifest_path.exists():
        manifest, artifacts = parse_manifest(manifest_path)
        if manifest.get("schema") != MANIFEST_SCHEMA:
            blockers.append("review-bundle-manifest.txt has unsupported schema")
        for key in manifest.get("_duplicateKeys", []):
            blockers.append(f"review-bundle-manifest.txt has duplicate metadata key: {key}")
        verify_manifest_artifact_rows(artifacts, blockers)
        verify_manifest_runtime_selectors(manifest, blockers)
    else:
        blockers.append("missing review-bundle-manifest.txt")
    if not sums_path.exists():
        blockers.append("missing SHA256SUMS")
        checksums = {}
    else:
        checksums = parse_sha256s(sums_path)
        for rel_path in checksums.get("__duplicate_paths__", []):
            blockers.append(f"SHA256SUMS has duplicate checksum row: {rel_path}")
        for error in checksums.get("__errors__", []):
            blockers.append(error)
    verify_manifest_artifact_inventory(root, artifacts, checksums, blockers)
    for rel_path in REQUIRED_FILES:
        if not (root / rel_path).exists():
            blockers.append(f"missing required artifact: {rel_path}")
    for rel_path, expected in sorted(checksums.items()):
        if rel_path in ("SHA256SUMS", "__duplicate_paths__", "__errors__"):
            continue
        path = root / rel_path
        if not path.exists():
            blockers.append(f"checksum references missing artifact: {rel_path}")
            continue
        actual = sha256(path)
        if actual != expected:
            blockers.append(f"checksum mismatch: {rel_path}")
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    for rel_path in files:
        if rel_path == "SHA256SUMS":
            continue
        if rel_path not in checksums:
            blockers.append(f"artifact missing from SHA256SUMS: {rel_path}")
    json_payloads = {}
    for rel_path, schema in JSON_SCHEMAS.items():
        path = root / rel_path
        if not path.exists():
            continue
        try:
            payload = load_json(path)
        except json.JSONDecodeError as exc:
            blockers.append(f"invalid JSON in {rel_path}: {exc}")
            continue
        if not isinstance(payload, dict):
            blockers.append(f"{rel_path} must be a JSON object")
            continue
        if payload.get("schemaVersion") != schema:
            blockers.append(f"{rel_path} has unsupported schemaVersion")
        json_payloads[rel_path] = payload
    evidence = json_payloads.get("ue4ss-package-runtime-trace-evidence.json", {})
    trace_plan = json_payloads.get("ue4ss-package-runtime-trace-plan.json", {})
    abi_review = json_payloads.get("ue4ss-package-abi-review.json", {})
    promotion = json_payloads.get("ue4ss-package-promotion-env.json", {})
    live_runbook = json_payloads.get("ue4ss-package-stimulus-trace-runbook.json", {})
    next_action = json_payloads.get("ue4ss-package-next-action.json", {})
    if trace_plan and evidence:
        verify_manifest_matches_trace_inputs(root, manifest, trace_plan, evidence, blockers, artifacts=artifacts, checksums=checksums)
    if trace_plan and next_action:
        verify_next_action_matches_trace_plan(trace_plan, next_action, manifest, blockers)
    if next_action:
        verify_next_action_shape(next_action, blockers)
        if live_runbook:
            verify_next_action_live_runbook(next_action, live_runbook, blockers, manifest=manifest, artifacts=artifacts)
        verify_plan_canary_next_action(
            root,
            next_action,
            artifacts,
            blockers,
            json_payloads.get("ue4ss-package-next-canary.json", {}),
        )
    if evidence and live_runbook:
        verify_runtime_route_slot_recovery_matches_runbook(evidence, live_runbook, blockers)
    if trace_plan and live_runbook:
        verify_trace_plan_supports_route_slot_requirement(trace_plan, live_runbook, blockers)
    verify_optional_promotion_summary(root, blockers)
    if evidence and abi_review and promotion:
        verify_top_level_package_identity(evidence, abi_review, promotion, blockers, manifest, checksums)
        verify_promotion_env_family_keys(root, root / "ue4ss-package-promotion-env.json", promotion, blockers)
        verify_promotion_ready_claim(root, root / "ue4ss-package-promotion-env.json", promotion, blockers)
    for path in sorted(root.rglob("review-priority.json")):
        rel_path = path.relative_to(root).as_posix()
        try:
            payload = load_json(path)
        except json.JSONDecodeError as exc:
            blockers.append(f"invalid JSON in {rel_path}: {exc}")
            continue
        if not isinstance(payload, dict):
            blockers.append(f"{rel_path} must be a JSON object")
            continue
        if payload.get("schemaVersion") != REVIEW_PRIORITY_SCHEMA:
            blockers.append(f"{rel_path} has unsupported schemaVersion")
        if not non_negative_int(payload.get("rank")):
            blockers.append(f"{rel_path} has invalid rank")
        hit_index = payload.get("hitIndex", "auto")
        if hit_index != "auto" and not non_negative_int(hit_index):
            blockers.append(f"{rel_path} has invalid hitIndex")
        family = payload.get("signatureFamily", "")
        if not family:
            blockers.append(f"{rel_path} has missing signatureFamily")
        elif path.parent.name != family:
            blockers.append(f"{rel_path} signatureFamily does not match parent directory")
        promotion_payload = bundled_promotion_payload(path)
        manifest_family = promotion_payload.get("signatureFamily", "")
        if family and manifest_family and family != manifest_family:
            blockers.append(f"{rel_path} signatureFamily does not match promotion manifest")
        promotion_hit_index = promotion_payload.get("hitIndex")
        if (
            hit_index != "auto"
            and promotion_hit_index is not None
            and hit_index != promotion_hit_index
        ):
            blockers.append(f"{rel_path} hitIndex does not match promotion manifest")
    for path in sorted((root / "ue4ss-package-family-reviews").glob("*/promotion-env.json")):
        verify_bundled_promotion_env(root, path, blockers, evidence, manifest, checksums)
    artifact_paths = {row["path"] for row in artifacts}
    if (root / "ue4ss-package-family-reviews.json").is_file() and "ue4ss-package-family-reviews.json" not in artifact_paths:
        blockers.append("ue4ss-package-family-reviews.json missing from review-bundle-manifest.txt artifact rows")
    for rel_path in REQUIRED_FILES:
        if rel_path in ("review-bundle-manifest.txt", "SHA256SUMS"):
            continue
        if rel_path not in artifact_paths:
            blockers.append(f"required artifact not listed in review-bundle-manifest.txt artifact rows: {rel_path}")
    return result(root, manifest, artifacts, checksums, blockers, warnings)


def result(root, manifest, artifacts, checksums, blockers, warnings):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "bundle": str(root),
        "ready": not blockers,
        "manifest": manifest,
        "artifactCount": len(artifacts),
        "checksumCount": len(checksums),
        "blockers": blockers,
        "warnings": warnings,
    }


def markdown(report):
    lines = ["# UE4SS Package Review Bundle Verification", ""]
    lines.append(f"- Bundle: `{report['bundle']}`")
    lines.append(f"- Ready: `{str(report['ready']).lower()}`")
    lines.append(f"- Artifacts listed: `{report['artifactCount']}`")
    lines.append(f"- Checksums: `{report['checksumCount']}`")
    manifest = report.get("manifest", {})
    if manifest:
        lines.append(f"- Bundle schema: `{manifest.get('schema', '')}`")
        lines.append(f"- Created UTC: `{manifest.get('createdUtc', '')}`")
        if manifest.get("container", ""):
            lines.append(f"- Container: `{manifest.get('container', '')}`")
        if manifest.get("traceHost", ""):
            lines.append(f"- Trace host: `{manifest.get('traceHost', '')}`")
        if manifest.get("processPattern", ""):
            lines.append(f"- Process pattern: `{manifest.get('processPattern', '')}`")
        if manifest.get("tracePid", ""):
            lines.append(f"- Trace PID: `{manifest.get('tracePid', '')}`")
        if manifest.get("playerGuardPhase", ""):
            lines.append(f"- Player guard phase: `{manifest.get('playerGuardPhase', '')}`")
        if manifest.get("playerGuardPartition", ""):
            lines.append(f"- Player guard partition: `{manifest.get('playerGuardPartition', '')}`")
        if manifest.get("playerGuardConnectedPlayers", ""):
            lines.append(f"- Player guard connected players: `{manifest.get('playerGuardConnectedPlayers', '')}`")
        if manifest.get("traceLog", ""):
            lines.append(f"- Trace log: `{manifest.get('traceLog', '')}`")
        lines.append(f"- Signature family: `{manifest.get('signatureFamily', '')}`")
        lines.append(f"- Hit index: `{manifest.get('hitIndex', '')}`")
        if manifest.get("tracePlanSourceExternalPlan", ""):
            lines.append(f"- Trace plan external plan: `{manifest.get('tracePlanSourceExternalPlan', '')}`")
        if manifest.get("tracePlanBase", ""):
            lines.append(f"- Trace plan base: `{manifest.get('tracePlanBase', '')}`")
        if manifest.get("tracePlanExpectedBuildId", ""):
            lines.append(f"- Trace plan expected Build ID: `{manifest.get('tracePlanExpectedBuildId', '')}`")
        if manifest.get("tracePlanRuntimeBuildId", ""):
            lines.append(f"- Trace plan runtime Build ID: `{manifest.get('tracePlanRuntimeBuildId', '')}`")
        if manifest.get("tracePlanSeedCount", ""):
            lines.append(f"- Trace plan seed count: `{manifest.get('tracePlanSeedCount', '')}`")
        if manifest.get("tracePlanSeedOffsets", ""):
            lines.append(f"- Trace plan seed offsets: `{manifest.get('tracePlanSeedOffsets', '')}`")
        if manifest.get("tracePlanSelectedByFamily", ""):
            lines.append(f"- Trace plan selected by family: `{manifest.get('tracePlanSelectedByFamily', '')}`")
        if manifest.get("tracePlanBlockerCount", ""):
            lines.append(f"- Trace plan blocker count: `{manifest.get('tracePlanBlockerCount', '')}`")
        if manifest.get("tracePlanRecommendedAnchor", ""):
            lines.append(f"- Trace plan recommended anchor: `{manifest.get('tracePlanRecommendedAnchor', '')}`")
        if manifest.get("tracePlanRecommendedLimit", ""):
            lines.append(f"- Trace plan recommended limit: `{manifest.get('tracePlanRecommendedLimit', '')}`")
        if manifest.get("tracePlanRecommendedSignatureFamily", ""):
            lines.append(
                f"- Trace plan recommended signature family: `{manifest.get('tracePlanRecommendedSignatureFamily', '')}`"
            )
        if manifest.get("tracePlanRecommendedHitIndex", ""):
            lines.append(f"- Trace plan recommended hit index: `{manifest.get('tracePlanRecommendedHitIndex', '')}`")
        if manifest.get("sourceLogExists", ""):
            lines.append(f"- Source log exists: `{manifest.get('sourceLogExists', '')}`")
        if manifest.get("evidencePid", ""):
            lines.append(f"- Evidence PID: `{manifest.get('evidencePid', '')}`")
        if manifest.get("tracePidMatchesRequested", ""):
            lines.append(f"- Trace PID matches requested: `{manifest.get('tracePidMatchesRequested', '')}`")
        if manifest.get("imageRangeSource", ""):
            lines.append(f"- Image range source: `{manifest.get('imageRangeSource', '')}`")
        if manifest.get("imageStart", "") or manifest.get("imageEnd", "") or manifest.get("imageBase", ""):
            lines.append(
                f"- Image range: `{manifest.get('imageStart', '')}-{manifest.get('imageEnd', '')}` "
                f"base=`{manifest.get('imageBase', '')}`"
            )
        if manifest.get("imagePath", ""):
            lines.append(f"- Image path: `{manifest.get('imagePath', '')}`")
        if manifest.get("imagePerms", ""):
            lines.append(f"- Image perms: `{manifest.get('imagePerms', '')}`")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    if report["warnings"]:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify a UE4SS package review bundle.")
    parser.add_argument("bundle")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    report = verify_bundle(args.bundle)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(report))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
