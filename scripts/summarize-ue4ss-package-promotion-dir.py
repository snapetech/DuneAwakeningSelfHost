#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-promotion-dir-summary/v1"
MANIFEST_SCHEMA = "dune-ue4ss-package-promotion-env/v1"
PROMOTION_ACCEPTANCE_SCHEMA = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
REVIEW_PRIORITY_SCHEMA = "dune-ue4ss-package-review-priority/v1"
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
PACKAGE_TRACE_FAMILIES = ASSET_FAMILIES | {"StaticLoadClass"}


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def manifest_paths(root):
    root = Path(root)
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    return sorted(path for path in root.glob("*/promotion-env.json") if path.is_file())


def non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


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


def review_priority_for_manifest(path, manifest_family=""):
    priority_path = Path(path).parent / "review-priority.json"
    if not priority_path.is_file():
        return None, None, []
    try:
        payload = load_json(priority_path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, None, [{"path": str(priority_path), "error": str(exc)}]
    errors = []
    rel = str(priority_path)
    if not isinstance(payload, dict):
        return None, None, [{"path": rel, "error": "review priority must be a JSON object"}]
    if payload.get("schemaVersion") != REVIEW_PRIORITY_SCHEMA:
        errors.append({"path": rel, "error": "unsupported review priority schemaVersion"})
    rank = payload.get("rank")
    if not non_negative_int(rank):
        errors.append({"path": rel, "error": "invalid review priority rank"})
        rank = None
    hit_index = payload.get("hitIndex", "auto")
    if hit_index != "auto" and not non_negative_int(hit_index):
        errors.append({"path": rel, "error": "invalid review priority hitIndex"})
        hit_index = "auto"
    family = payload.get("signatureFamily", "")
    if not family:
        errors.append({"path": rel, "error": "missing review priority signatureFamily"})
    elif priority_path.parent.name != family:
        errors.append({"path": rel, "error": "review priority signatureFamily does not match parent directory"})
    if manifest_family and family and manifest_family != family:
        errors.append({"path": rel, "error": "review priority signatureFamily does not match promotion manifest"})
    return rank, hit_index, errors


def runtime_trace_env_evidence_errors(payload):
    family = payload.get("signatureFamily", "")
    caller_offset = payload.get("callerImageOffset", "")
    rip_offset = payload.get("ripImageOffset", "")
    trace_pid = payload.get("tracePid")
    evidence_json_sha256 = payload.get("sourceEvidenceJsonSha256", "")
    source_log_sha256 = payload.get("sourceLogSha256", "")
    env = payload.get("env", {}) or {}
    if not isinstance(env, dict):
        return ["package promotion env must be an object"]
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
    errors = []
    ready_claimed = payload.get("readyForNonInvokingCanary") is True or payload.get("readyForNativeInvoke") is True
    if ready_claimed and not evidence_values:
        errors.append("ready package promotion env is missing runtime trace evidence")
    evidence_tokens = [runtime_trace_evidence_tokens(value) for value in evidence_values]
    if family:
        for value in evidence_values:
            parts = value.split(":", 2)
            evidence_family = parts[1] if len(parts) > 1 else ""
            if evidence_family != family:
                errors.append("env evidence family does not match signatureFamily")
                break
        for tokens in evidence_tokens:
            if tokens.get("seed", family) != family:
                errors.append("env evidence seed does not match signatureFamily")
                break
    if caller_offset:
        for tokens in evidence_tokens:
            if tokens.get("caller", "") != caller_offset:
                errors.append("env evidence caller does not match callerImageOffset")
                break
    if rip_offset:
        for tokens in evidence_tokens:
            if tokens.get("rip", "") != rip_offset:
                errors.append("env evidence rip does not match ripImageOffset")
                break
    if trace_pid not in (None, ""):
        for tokens in evidence_tokens:
            if tokens.get("pid", "") != str(trace_pid):
                errors.append("env evidence pid does not match tracePid")
                break
    if evidence_json_sha256:
        for tokens in evidence_tokens:
            if tokens.get("evidenceJsonSha256", "") != str(evidence_json_sha256):
                errors.append("env evidence digest does not match sourceEvidenceJsonSha256")
                break
    if source_log_sha256:
        for tokens in evidence_tokens:
            if tokens.get("sourceLogSha256", "") != str(source_log_sha256):
                errors.append("env evidence log digest does not match sourceLogSha256")
                break
    return errors


def string_list_field(payload, key):
    raw = payload.get(key, [])
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [f"{key} must be a JSON array"]
    errors = []
    values = []
    for index, value in enumerate(raw):
        if not isinstance(value, str):
            errors.append(f"{key}[{index}] must be a string")
            continue
        values.append(value)
    return values, errors


def single_line_scalar(value):
    if not isinstance(value, (str, int, float, bool)):
        return False
    text = str(value)
    return bool(text.strip()) and not any(char in text for char in "\r\n\0")


def identity_scalar_errors(payload):
    errors = []
    for field in (
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
        "callerImageOffset",
        "ripImageOffset",
        "selectedHitSeed",
    ):
        if field not in payload:
            continue
        if payload.get(field) in (None, ""):
            continue
        if not single_line_scalar(payload.get(field)):
            errors.append(f"package promotion manifest {field} must be a non-empty single-line scalar")
    return errors


def missing_required_memory_registers(hit):
    return string_list_field(hit, "missingRequiredMemoryRegisters")


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
                break
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


def summarize_manifest(path):
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {
            "path": str(path),
            "reviewPriority": None,
            "reviewPriorityHitIndex": None,
            "reviewPriorityErrors": [{"path": str(path), "error": "promotion manifest must be a JSON object"}],
            "valid": False,
            "signatureFamily": Path(path).parent.name or "unknown",
            "hitIndex": None,
            "selectedHitSeed": "",
            "sourceEvidence": "",
            "sourceEvidenceJson": "",
            "sourceEvidenceJsonSha256": "",
            "sourceLogSha256": "",
            "sourceLogExists": None,
            "tracePidMatchesRequested": None,
            "tracePid": None,
            "imageRangeSource": "",
            "imageBase": "",
            "imageStart": "",
            "imageEnd": "",
            "imagePath": "",
            "imagePerms": "",
            "callerImageOffset": "",
            "ripImageOffset": "",
            "env": {},
            "hit": {},
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "abiReviewReady": False,
            "targetImageReviewed": False,
            "abiReviewed": False,
            "tcharReviewed": False,
            "classRootReviewed": False,
            "missingReviewFlags": [],
            "missingNativeInvokeFlags": [],
            "blockers": ["promotion manifest must be a JSON object"],
            "abiReviewBlockers": [],
            "nextStep": "",
        }
    valid = payload.get("schemaVersion") == MANIFEST_SCHEMA
    family = payload.get("signatureFamily", "unknown")
    review_priority, review_priority_hit_index, priority_errors = review_priority_for_manifest(path, family)
    if family and Path(path).parent.name != family:
        priority_errors.append({"path": str(path), "error": "promotion manifest signatureFamily does not match parent directory"})
    if family not in PACKAGE_TRACE_FAMILIES:
        priority_errors.append({"path": str(path), "error": f"unsupported package promotion signatureFamily: {family}"})
    manifest_hit_index = payload.get("hitIndex")
    if (
        isinstance(review_priority_hit_index, int)
        and manifest_hit_index is not None
        and review_priority_hit_index != manifest_hit_index
    ):
        priority_errors.append({"path": str(path), "error": "review priority hitIndex does not match promotion manifest"})
    ready_non_invoking = valid and payload.get("readyForNonInvokingCanary") is True
    ready_native = valid and payload.get("readyForNativeInvoke") is True
    blockers, blocker_shape_errors = string_list_field(payload, "blockers")
    raw_abi_review = payload.get("abiReview", {}) or {}
    abi_shape_errors = []
    if not isinstance(raw_abi_review, dict):
        abi_shape_errors.append("abiReview must be a JSON object")
        abi_review = {}
    else:
        abi_review = raw_abi_review
    abi_blockers, abi_blocker_shape_errors = string_list_field(abi_review, "blockers")
    missing_review, missing_review_shape_errors = string_list_field(payload, "missingReviewFlags")
    missing_native, missing_native_shape_errors = string_list_field(payload, "missingNativeInvokeFlags")
    shape_errors = (
        blocker_shape_errors
        + abi_shape_errors
        + [f"abiReview.{error}" for error in abi_blocker_shape_errors]
        + abi_review_argument_shape_errors(abi_review)
        + missing_review_shape_errors
        + missing_native_shape_errors
        + identity_scalar_errors(payload)
    )
    caller_offset = payload.get("callerImageOffset", "")
    rip_offset = payload.get("ripImageOffset", "")
    selected_hit_seed = payload.get("selectedHitSeed", "")
    raw_env = payload.get("env", {}) or {}
    env_shape_errors = []
    if not isinstance(raw_env, dict):
        env_shape_errors.append("package promotion env must be an object")
        env = {}
    else:
        env = raw_env
        for key, value in env.items():
            if not isinstance(key, str) or not key:
                env_shape_errors.append("package promotion env contains an invalid key")
                break
            if not isinstance(value, (str, int, float, bool)):
                env_shape_errors.append(f"package promotion env contains a non-scalar value for {key}")
                break
            if not single_line_scalar(value):
                env_shape_errors.append(f"package promotion env contains a non-empty single-line scalar violation for {key}")
                break
    if not valid:
        blockers.append("invalid package promotion manifest schema")
        priority_errors.append({"path": str(path), "error": "invalid package promotion manifest schema"})
    family_env_errors = []
    if family == "StaticLoadClass":
        if any(key in PACKAGE_ASSET_ENV_KEYS and env.get(key) for key in env):
            family_env_errors.append("StaticLoadClass promotion env includes LoadAsset package keys")
    elif family in ASSET_FAMILIES:
        if any(key in PACKAGE_CLASS_ENV_KEYS and env.get(key) for key in env):
            family_env_errors.append(f"{family} promotion env includes LoadClass package keys")
    ready_claimed = valid and (
        payload.get("readyForNonInvokingCanary") is True or payload.get("readyForNativeInvoke") is True
    )
    ready_errors = []
    priority_blockers = [item.get("error", "") for item in priority_errors if item.get("error")]
    if ready_claimed:
        ready_errors.extend(shape_errors)
        ready_errors.extend(env_shape_errors)
        ready_errors.extend(priority_blockers)
        if ready_native and not ready_non_invoking:
            ready_errors.append("ready native package promotion manifest is missing non-invoking canary readiness")
        if blockers:
            ready_errors.append("ready package promotion manifest still has blockers")
        if abi_blockers:
            ready_errors.append("ready package promotion manifest still has ABI review blockers")
        if payload.get("abiReviewReady") is not True and abi_review.get("ready") is not True:
            ready_errors.append("ready package promotion manifest is missing ABI review readiness")
        if payload.get("abiReviewed") is not True:
            ready_errors.append("ready package promotion manifest is missing reviewed ABI confirmation")
        if payload.get("promotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA:
            ready_errors.append("ready package promotion manifest is missing current package promotion acceptance schema")
        if not payload.get("sourceTracePlan", ""):
            ready_errors.append("ready package promotion manifest is missing sourceTracePlan provenance")
        if not payload.get("sourceTracePlanSchemaVersion", ""):
            ready_errors.append("ready package promotion manifest is missing sourceTracePlanSchemaVersion provenance")
        if payload.get("sourcePromotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA:
            ready_errors.append("ready package promotion manifest is missing current source promotion acceptance schema provenance")
        if not payload.get("sourceExternalPlan", ""):
            ready_errors.append("ready package promotion manifest is missing sourceExternalPlan provenance")
        if payload.get("targetImageReviewed") is not True:
            ready_errors.append("ready package promotion manifest is missing reviewed target-image confirmation")
        if family == "StaticLoadClass" and payload.get("classRootReviewed") is not True:
            ready_errors.append("ready package promotion manifest is missing reviewed class-root confirmation")
        if family in ASSET_FAMILIES and payload.get("tcharReviewed") is not True:
            ready_errors.append("ready package promotion manifest is missing reviewed TCHAR confirmation")
        if ready_native and payload.get("nativeInvokeEnabled") is not True:
            ready_errors.append("ready native package promotion manifest is missing native invoke enablement")
        if ready_native and payload.get("finalNativeCallConfirmed") is not True:
            ready_errors.append("ready native package promotion manifest is missing final native-call confirmation")
        if missing_review:
            ready_errors.append("ready package promotion manifest still has missing review flags")
        if missing_native and payload.get("readyForNativeInvoke") is True:
            ready_errors.append("ready native package promotion manifest still has missing native invoke flags")
        if not payload.get("sourceEvidence", ""):
            ready_errors.append("ready package promotion manifest is missing sourceEvidence")
        if not payload.get("sourceEvidenceJson", ""):
            ready_errors.append("ready package promotion manifest is missing sourceEvidenceJson provenance")
        if not payload.get("sourceEvidenceJsonSha256", ""):
            ready_errors.append("ready package promotion manifest is missing sourceEvidenceJsonSha256 provenance")
        elif not valid_sha256_text(payload.get("sourceEvidenceJsonSha256", "")):
            ready_errors.append("ready package promotion manifest has invalid sourceEvidenceJsonSha256")
        if not payload.get("sourceLogSha256", ""):
            ready_errors.append("ready package promotion manifest is missing sourceLogSha256 provenance")
        elif not valid_sha256_text(payload.get("sourceLogSha256", "")):
            ready_errors.append("ready package promotion manifest has invalid sourceLogSha256")
        if "sourceLogExists" not in payload:
            ready_errors.append("ready package promotion manifest is missing sourceLogExists")
        elif payload.get("sourceLogExists") is not True:
            ready_errors.append("ready package promotion manifest sourceLog does not exist")
        trace_pid_matches_requested = payload.get("tracePidMatchesRequested")
        if "tracePidMatchesRequested" not in payload:
            ready_errors.append("ready package promotion manifest is missing runtime trace PID match provenance")
        elif trace_pid_matches_requested is not True:
            ready_errors.append("trace log armed PID does not match requested runtime PID")
        if not positive_int(payload.get("tracePid")):
            ready_errors.append("ready package promotion manifest is missing concrete tracePid")
        if not non_negative_int(payload.get("hitIndex")):
            ready_errors.append("ready package promotion manifest is missing concrete hitIndex")
        if not selected_hit_seed:
            ready_errors.append("ready package promotion manifest is missing selectedHitSeed")
        if selected_hit_seed and family and selected_hit_seed != family:
            ready_errors.append("selectedHitSeed does not match signatureFamily")
        if not caller_offset:
            ready_errors.append("ready package promotion manifest is missing callerImageOffset")
        elif not valid_image_offset(caller_offset):
            ready_errors.append("ready package promotion manifest has invalid callerImageOffset")
        if not rip_offset:
            ready_errors.append("ready package promotion manifest is missing ripImageOffset")
        elif not valid_image_offset(rip_offset):
            ready_errors.append("ready package promotion manifest has invalid ripImageOffset")
        hit = payload.get("hit", {}) or {}
        if isinstance(hit, dict) and hit:
            trace_log_has_armed = hit.get("traceLogHasArmed")
            if trace_log_has_armed not in (None, True):
                ready_errors.append("embedded trace hit missing trace armed record; cannot prove runtime trace session")
            hit_trace_pid_matches_requested = hit.get("tracePidMatchesRequested")
            if hit_trace_pid_matches_requested not in (None, True):
                ready_errors.append("embedded trace hit trace log armed PID does not match requested runtime PID")
            if hit.get("traceAddressMatchesBase") is not True:
                ready_errors.append("embedded trace hit address does not match image base plus seed imageOffset")
            for error in register_memory_shape_errors(hit):
                ready_errors.append(f"embedded trace hit {error}")
            missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(hit)
            for error in missing_required_memory_errors:
                ready_errors.append(f"embedded trace hit {error}")
            if missing_required_memory:
                ready_errors.append(
                    "embedded trace hit is missing required memory registers: "
                    + ", ".join(str(item) for item in missing_required_memory)
                )
            hit_seed = hit.get("seed", "")
            if selected_hit_seed and hit_seed and selected_hit_seed != hit_seed:
                ready_errors.append("selectedHitSeed does not match embedded trace hit seed")
            if hit_seed and family and hit_seed != family:
                ready_errors.append("embedded trace hit seed does not match signatureFamily")
            if hit.get("callerImageOffset", "") and hit.get("callerImageOffset", "") != caller_offset:
                ready_errors.append("embedded trace hit callerImageOffset does not match manifest")
            if hit.get("ripImageOffset", "") and hit.get("ripImageOffset", "") != rip_offset:
                ready_errors.append("embedded trace hit ripImageOffset does not match manifest")
        ready_errors.extend(runtime_trace_env_evidence_errors(payload))
    ready_errors.extend(family_env_errors)
    if not ready_claimed:
        for error in shape_errors:
            if error not in blockers:
                blockers.append(error)
            row = {"path": str(path), "error": error}
            if row not in priority_errors:
                priority_errors.append(row)
    for error in ready_errors:
        if error not in blockers:
            blockers.append(error)
        row = {"path": str(path), "error": error}
        if row not in priority_errors:
            priority_errors.append(row)
    return {
        "path": str(path),
        "reviewPriority": review_priority,
        "reviewPriorityHitIndex": review_priority_hit_index,
        "reviewPriorityErrors": priority_errors,
        "valid": valid,
        "promotionAcceptanceSchemaVersion": payload.get("promotionAcceptanceSchemaVersion", ""),
        "signatureFamily": family,
        "hitIndex": payload.get("hitIndex"),
        "selectedHitSeed": selected_hit_seed,
        "sourceEvidence": payload.get("sourceEvidence", ""),
        "sourceEvidenceJson": payload.get("sourceEvidenceJson", ""),
        "sourceEvidenceJsonSha256": payload.get("sourceEvidenceJsonSha256", ""),
        "sourceLogSha256": payload.get("sourceLogSha256", ""),
        "sourceLogExists": payload.get("sourceLogExists"),
        "sourceTracePlan": payload.get("sourceTracePlan", ""),
        "sourceTracePlanSchemaVersion": payload.get("sourceTracePlanSchemaVersion", ""),
        "sourcePromotionAcceptanceSchemaVersion": payload.get("sourcePromotionAcceptanceSchemaVersion", ""),
        "sourceExternalPlan": payload.get("sourceExternalPlan", ""),
        "tracePidMatchesRequested": payload.get("tracePidMatchesRequested"),
        "tracePid": payload.get("tracePid"),
        "imageRangeSource": payload.get("imageRangeSource", ""),
        "imageBase": payload.get("imageBase", ""),
        "imageStart": payload.get("imageStart", ""),
        "imageEnd": payload.get("imageEnd", ""),
        "imagePath": payload.get("imagePath", ""),
        "imagePerms": payload.get("imagePerms", ""),
        "callerImageOffset": caller_offset,
        "ripImageOffset": rip_offset,
        "env": env,
        "hit": dict(payload.get("hit", {}) or {}) if isinstance(payload.get("hit", {}), dict) else {},
        "readyForNonInvokingCanary": ready_non_invoking and not ready_errors,
        "readyForNativeInvoke": ready_native and not ready_errors,
        "abiReviewReady": payload.get("abiReviewReady") is True or abi_review.get("ready") is True,
        "targetImageReviewed": payload.get("targetImageReviewed") is True,
        "abiReviewed": payload.get("abiReviewed") is True,
        "tcharReviewed": payload.get("tcharReviewed") is True,
        "classRootReviewed": payload.get("classRootReviewed") is True,
        "missingReviewFlags": missing_review,
        "missingNativeInvokeFlags": missing_native,
        "blockers": blockers,
        "abiReviewBlockers": abi_blockers,
        "nextStep": payload.get("nextStep", ""),
    }


def build_summary(root):
    rows = []
    errors = []
    for path in manifest_paths(root):
        try:
            row = summarize_manifest(path)
            rows.append(row)
            errors.extend(row.get("reviewPriorityErrors", []) or [])
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    rows.sort(
        key=lambda row: (
            row["reviewPriority"] if row.get("reviewPriority") is not None else 10_000,
            row["path"],
        )
    )
    ready_non_invoking = [row for row in rows if row["readyForNonInvokingCanary"]]
    ready_native = [row for row in rows if row["readyForNativeInvoke"]]
    blocked = [row for row in rows if not row["readyForNonInvokingCanary"] and not row["readyForNativeInvoke"]]
    next_step = "run package runtime trace status to generate per-family promotion manifests"
    if ready_native:
        next_step = "feed ready native package promotion manifests into lua-dispatch canary"
    elif ready_non_invoking:
        next_step = "feed ready non-invoking package promotion manifests into lua-dispatch canary"
    elif rows:
        pending = []
        for row in blocked:
            pending.extend(row["missingReviewFlags"])
            pending.extend(row["missingNativeInvokeFlags"])
        if pending:
            next_step = "complete package promotion review flags: " + ", ".join(sorted(set(pending)))
        else:
            next_step = "resolve package promotion blockers before canary planning"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "root": str(root),
        "manifestCount": len(rows),
        "errorCount": len(errors),
        "readyForNonInvokingCanaryCount": len(ready_non_invoking),
        "readyForNativeInvokeCount": len(ready_native),
        "blockedCount": len(blocked),
        "readyFamilies": [row["signatureFamily"] for row in rows if row["readyForNonInvokingCanary"] or row["readyForNativeInvoke"]],
        "blockedFamilies": [row["signatureFamily"] for row in blocked],
        "readyManifestPaths": [row["path"] for row in rows if row["readyForNonInvokingCanary"] or row["readyForNativeInvoke"]],
        "nextCanaryArgs": ["--package-promotion-dir", str(root)] if Path(root).is_dir() else [],
        "nextCanaryReadyArgs": [
            item
            for row in rows
            if row["readyForNonInvokingCanary"] or row["readyForNativeInvoke"]
            for item in ("--package-promotion-json", row["path"])
        ],
        "nextStep": next_step,
        "manifests": rows,
        "errors": errors,
    }


def markdown(summary):
    lines = ["# UE4SS Package Promotion Directory", ""]
    lines.append(f"- Root: `{summary['root']}`")
    lines.append(f"- Manifests: `{summary['manifestCount']}`")
    lines.append(f"- Ready for non-invoking canary: `{summary['readyForNonInvokingCanaryCount']}`")
    lines.append(f"- Ready for native invoke: `{summary['readyForNativeInvokeCount']}`")
    lines.append(f"- Blocked: `{summary['blockedCount']}`")
    lines.append(f"- Errors: `{summary['errorCount']}`")
    if summary.get("nextCanaryArgs"):
        lines.append(f"- Next canary args: `{' '.join(summary['nextCanaryArgs'])}`")
    if summary.get("nextCanaryReadyArgs"):
        lines.append(f"- Ready-only canary args: `{' '.join(summary['nextCanaryReadyArgs'])}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    lines.append("")
    if summary["manifests"]:
        lines.append("## Manifests")
        lines.append("")
        for row in summary["manifests"]:
            review_priority = row.get("reviewPriority")
            priority_text = f"reviewPriority=`{review_priority}` " if review_priority is not None else ""
            priority_hit_index = row.get("reviewPriorityHitIndex")
            priority_hit_text = f"reviewHitIndex=`{priority_hit_index}` " if priority_hit_index is not None else ""
            lines.append(
                f"- `{row['signatureFamily']}` {priority_text}{priority_hit_text}readyNonInvoking=`{str(row['readyForNonInvokingCanary']).lower()}` "
                f"readyNative=`{str(row['readyForNativeInvoke']).lower()}` "
                f"abiReviewReady=`{str(row['abiReviewReady']).lower()}` "
                f"sourceLogExists=`{str(row.get('sourceLogExists')).lower()}` "
                f"tracePidMatchesRequested=`{str(row.get('tracePidMatchesRequested')).lower()}` path=`{row['path']}`"
            )
            for flag in row["missingReviewFlags"]:
                lines.append(f"  - missing review flag: `{flag}`")
            for flag in row["missingNativeInvokeFlags"]:
                lines.append(f"  - missing native flag: `{flag}`")
            for blocker in row["blockers"]:
                lines.append(f"  - blocker: {blocker}")
            for blocker in row["abiReviewBlockers"]:
                lines.append(f"  - ABI review blocker: {blocker}")
            if row.get("nextStep"):
                lines.append(f"  - next step: {row['nextStep']}")
    if summary["errors"]:
        lines.append("")
        lines.append("## Errors")
        lines.append("")
        for row in summary["errors"]:
            lines.append(f"- `{row['path']}`: {row['error']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize per-family UE4SS package promotion manifests.")
    parser.add_argument("root")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = build_summary(args.root)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
