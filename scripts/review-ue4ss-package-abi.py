#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-abi-review/v1"
TRACE_EVIDENCE_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-evidence/v1"
PROMOTION_ACCEPTANCE_SCHEMA_VERSION = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
OPTIONAL_NULL_ROLES = {"Outer", "Filename", "Sandbox"}
SCALAR_ROLES = {"LoadFlags", "AllowObjectReconciliation", "Create", "Throw"}
PATH_POINTER_ROLES = {"Name", "PackageName", "Filename"}
REQUIRED_PATH_MEMORY_ROLES = {"Name", "PackageName"}
POINTER_ROLES = {
    "Class",
    "BaseClass",
    "Outer",
    "Name",
    "Filename",
    "Sandbox",
    "PackageName",
    "OuterPtr",
}
HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
BYTE_RE = re.compile(r"\b0x([0-9a-fA-F]{1,2})\b")
QUOTED_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
SIGNATURES = {
    "StaticLoadObject": {
        "signature": "UObject*(UClass*,UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*,bool)",
        "registers": [
            ("rdi", "Class"),
            ("rsi", "Outer"),
            ("rdx", "Name"),
            ("rcx", "Filename"),
            ("r8", "LoadFlags"),
            ("r9", "Sandbox"),
        ],
        "stack": ["AllowObjectReconciliation"],
        "requires": ["target-image caller", "disassembly context", "stack context", "TCHAR layout evidence"],
    },
    "StaticLoadClass": {
        "signature": "UClass*(UClass*,UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*)",
        "registers": [
            ("rdi", "BaseClass"),
            ("rsi", "Outer"),
            ("rdx", "Name"),
            ("rcx", "Filename"),
            ("r8", "LoadFlags"),
            ("r9", "Sandbox"),
        ],
        "stack": [],
        "requires": ["target-image caller", "disassembly context", "stack context", "root UClass evidence"],
    },
    "LoadObject": {
        "signature": "UObject*(UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*,bool)",
        "registers": [
            ("rdi", "Outer"),
            ("rsi", "Name"),
            ("rdx", "Filename"),
            ("rcx", "LoadFlags"),
            ("r8", "Sandbox"),
            ("r9", "AllowObjectReconciliation"),
        ],
        "stack": [],
        "requires": ["target-image caller", "disassembly context", "stack context", "TCHAR layout evidence"],
    },
    "LoadPackage": {
        "signature": "UPackage*(UObject*,const TCHAR*,uint32)",
        "registers": [("rdi", "Outer"), ("rsi", "PackageName"), ("rdx", "LoadFlags")],
        "stack": [],
        "requires": ["target-image caller", "disassembly context", "stack context", "TCHAR layout evidence"],
    },
    "ResolveName": {
        "signature": "bool(UObject**,FString&,bool,bool,uint32)",
        "registers": [
            ("rdi", "OuterPtr"),
            ("rsi", "Name"),
            ("rdx", "Create"),
            ("rcx", "Throw"),
            ("r8", "LoadFlags"),
        ],
        "stack": [],
        "requires": ["target-image caller", "disassembly context", "stack context", "FString layout evidence"],
    },
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_trace_evidence(path):
    evidence = load_json(path)
    if not isinstance(evidence, dict):
        raise ValueError(f"{path} is not a JSON object")
    schema = evidence.get("schemaVersion")
    if schema != TRACE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schemaVersion {schema!r}; expected {TRACE_EVIDENCE_SCHEMA_VERSION!r}"
        )
    evidence.setdefault("sourceEvidenceJson", str(path))
    evidence.setdefault("sourceEvidenceJsonSha256", file_sha256(path))
    return evidence


def present_non_true(value):
    return value is not None and value is not True


def family_for_hit(hit, explicit):
    if explicit:
        return explicit
    seed = hit.get("seed", "")
    return seed if seed in SIGNATURES else "StaticLoadObject"


def trace_hits(evidence):
    hits = evidence.get("hits", [])
    if hits is None:
        return []
    return hits if isinstance(hits, list) else []


def evidence_shape_blockers(evidence):
    blockers = []
    if evidence.get("sourcePromotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA_VERSION:
        blockers.append(
            "runtime trace evidence missing current package promotion acceptance schema provenance"
        )
    armed_count = evidence.get("armedCount")
    if armed_count == 0:
        blockers.append("missing trace armed record; cannot prove runtime trace session")
    elif isinstance(armed_count, int) and not isinstance(armed_count, bool) and armed_count > 1:
        blockers.append("multiple trace armed records; use a fresh single-session trace log")
    if present_non_true(evidence.get("tracePidMatchesRequested")):
        blockers.append("trace log armed PID does not match requested runtime PID")
    hits = evidence.get("hits", [])
    if hits is None:
        hits = []
    if not isinstance(hits, list):
        blockers.append("runtime trace hits must be a JSON array")
        return blockers
    for index, hit in enumerate(hits):
        if not isinstance(hit, dict):
            blockers.append(f"runtime trace hit {index} must be a JSON object")
            continue
        if present_non_true(hit.get("traceLogHasArmed")):
            blockers.append(f"runtime trace hit {index} missing trace armed record; cannot prove runtime trace session")
        if present_non_true(hit.get("tracePidMatchesRequested")):
            blockers.append(f"runtime trace hit {index} trace log armed PID does not match requested runtime PID")
        if hit.get("traceAddressMatchesBase") is not True:
            blockers.append(f"runtime trace hit {index} address does not match image base plus seed imageOffset")
        missing_required_memory = hit.get("missingRequiredMemoryRegisters", [])
        if missing_required_memory is None:
            missing_required_memory = []
        if not isinstance(missing_required_memory, list):
            blockers.append(f"runtime trace hit {index} missingRequiredMemoryRegisters must be a JSON array")
        else:
            invalid_memory_register = False
            for register_index, register in enumerate(missing_required_memory):
                if not isinstance(register, str):
                    blockers.append(
                        f"runtime trace hit {index} missingRequiredMemoryRegisters[{register_index}] must be a string"
                    )
                    invalid_memory_register = True
                    break
            if missing_required_memory and not invalid_memory_register:
                blockers.append(
                    f"runtime trace hit {index} is missing required memory registers: "
                    + ", ".join(missing_required_memory)
                )
        for key in ("backtrace", "disassembly", "stack", "parseWarnings"):
            value = hit.get(key, [])
            if value is not None and not isinstance(value, list):
                blockers.append(f"runtime trace hit {index} {key} must be a JSON array")
        registers = hit.get("registers", {})
        if registers is not None and not isinstance(registers, dict):
            blockers.append(f"runtime trace hit {index} registers must be a JSON object")
        elif isinstance(registers, dict):
            for register, value in registers.items():
                if not isinstance(register, str) or not register:
                    blockers.append(f"runtime trace hit {index} registers contains an invalid register key")
                    continue
                if not isinstance(value, str):
                    blockers.append(f"runtime trace hit {index} registers.{register} must be a string")
    recommended = evidence.get("recommendedReview", {})
    if recommended is not None and not isinstance(recommended, dict):
        blockers.append("recommendedReview must be a JSON object")
    concrete_priority = evidence.get("concreteReviewPriority", [])
    if concrete_priority is not None and not isinstance(concrete_priority, list):
        blockers.append("concreteReviewPriority must be a JSON array")
    return blockers


def selected_hit_index(evidence, hit_index=0, signature_family=""):
    hits = trace_hits(evidence)
    if not hits:
        return 0
    def concrete_hit_index(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if hit_index == "auto":
        recommended = evidence.get("recommendedReview", {}) or {}
        if not isinstance(recommended, dict):
            recommended = {}
        if (
            signature_family
            and recommended.get("seed") == signature_family
            and concrete_hit_index(recommended.get("hitIndex"))
        ):
            return recommended["hitIndex"]
        concrete_priority = evidence.get("concreteReviewPriority", []) or []
        if not isinstance(concrete_priority, list):
            concrete_priority = []
        for candidate in concrete_priority:
            if (
                isinstance(candidate, dict)
                and candidate.get("seed") == signature_family
                and concrete_hit_index(candidate.get("hitIndex"))
            ):
                return candidate["hitIndex"]
        if signature_family:
            raise ValueError(f"no concrete runtime trace review candidate for signature family {signature_family}")
        for candidate in concrete_priority:
            if isinstance(candidate, dict) and concrete_hit_index(candidate.get("hitIndex")):
                return candidate["hitIndex"]
        return 0
    if isinstance(hit_index, bool):
        raise ValueError("hit index must be auto or a non-negative integer")
    try:
        resolved = int(hit_index)
    except (TypeError, ValueError):
        raise ValueError("hit index must be auto or a non-negative integer") from None
    if resolved < 0:
        raise ValueError("hit index must be auto or a non-negative integer")
    return resolved


def classify_argument(role, value):
    present = bool(value)
    null_value = value in ("", "0x0", "(nil)")
    if role in SCALAR_ROLES:
        return {
            "kind": "scalar",
            "required": True,
            "present": present,
            "nullAllowed": False,
            "looksSane": present,
            "note": "scalar value captured" if present else "missing scalar value",
        }
    if role in OPTIONAL_NULL_ROLES:
        return {
            "kind": "pointer",
            "required": False,
            "present": present,
            "nullAllowed": True,
            "looksSane": present,
            "note": "optional pointer captured" if present else "optional pointer is null or absent",
        }
    if role in POINTER_ROLES:
        return {
            "kind": "pointer",
            "required": True,
            "present": present and not null_value,
            "nullAllowed": False,
            "looksSane": present and not null_value,
            "note": "required pointer captured" if present and not null_value else "required pointer is null or absent",
        }
    return {
        "kind": "unknown",
        "required": True,
        "present": present,
        "nullAllowed": False,
        "looksSane": present,
        "note": "captured" if present else "missing",
    }


def stack_qwords(stack_lines):
    values = []
    for line in stack_lines or []:
        text = str(line)
        _, sep, rhs = text.partition(":")
        search_text = rhs if sep else text
        values.extend(HEX_RE.findall(search_text))
    return values


def stack_argument_details(stack_lines, roles):
    qwords = stack_qwords(stack_lines)
    details = []
    for index, role in enumerate(roles):
        slot = index + 1
        value = qwords[slot] if slot < len(qwords) else ""
        classification = classify_argument(role, value)
        details.append(
            {
                "slot": slot,
                "role": role,
                "capturedValue": value,
                "present": classification["present"],
                "kind": classification["kind"],
                "required": classification["required"],
                "nullAllowed": classification["nullAllowed"],
                "looksSane": classification["looksSane"],
                "note": classification["note"],
            }
        )
    return details


def trace_target_identity(evidence):
    return {
        "tracePid": evidence.get("pid"),
        "imageRangeSource": evidence.get("imageRangeSource", ""),
        "imageBase": evidence.get("imageBase", ""),
        "imageStart": evidence.get("imageStart", ""),
        "imageEnd": evidence.get("imageEnd", ""),
        "imagePath": evidence.get("imagePath", ""),
        "imagePerms": evidence.get("imagePerms", ""),
    }


def scalar_provenance_blockers(payload, fields):
    blockers = []
    for field in fields:
        if field not in payload:
            continue
        value = payload.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, (str, int, float, bool)):
            blockers.append(f"{field} provenance must be a scalar")
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            blockers.append(f"{field} provenance must be a non-empty single-line value")
    return blockers


def register_memory_rows(hit, register):
    register_memory = hit.get("registerMemory", {}) or {}
    if not isinstance(register_memory, dict):
        return []
    rows = register_memory.get(register, []) or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, str)]


def register_memory_shape_blockers(hit):
    register_memory = hit.get("registerMemory", {}) or {}
    if not isinstance(register_memory, dict):
        return ["registerMemory must be a JSON object"]
    blockers = []
    for register, rows in register_memory.items():
        if not isinstance(register, str) or not register:
            blockers.append("registerMemory contains an invalid register key")
            continue
        if rows is None:
            continue
        if not isinstance(rows, list):
            blockers.append(f"registerMemory.{register} must be a JSON array")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, str):
                blockers.append(f"registerMemory.{register}[{index}] must be a string")
                break
    return blockers


def register_memory_details(hit, register):
    rows = register_memory_rows(hit, register)
    hints = path_memory_hints(rows)
    return {
        "provided": bool(rows),
        "lineCount": len(rows),
        "sample": rows[:4],
        "hints": hints,
    }


def decode_escaped_text(value):
    try:
        return bytes(value, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return value


def quoted_string_samples(rows):
    samples = []
    for row in rows or []:
        for match in QUOTED_RE.finditer(str(row)):
            text = decode_escaped_text(match.group(1))
            if text and text not in samples:
                samples.append(text)
    return samples


def byte_values(rows):
    values = []
    for row in rows or []:
        text = str(row)
        _, sep, rhs = text.partition(":")
        if not sep:
            continue
        for match in BYTE_RE.finditer(rhs):
            value = int(match.group(1), 16)
            if 0 <= value <= 0xFF:
                values.append(value)
    return values


def printable_ascii_prefix(values):
    chars = []
    for value in values:
        if value == 0:
            break
        if 0x20 <= value <= 0x7E:
            chars.append(chr(value))
        else:
            break
    return "".join(chars)


def utf16le_ascii_prefix(values):
    chars = []
    for index in range(0, max(0, len(values) - 1), 2):
        low = values[index]
        high = values[index + 1]
        if low == 0 and high == 0:
            break
        if high == 0 and 0x20 <= low <= 0x7E:
            chars.append(chr(low))
        else:
            break
    return "".join(chars)


def path_memory_hints(rows):
    quoted = quoted_string_samples(rows)
    bytes_seen = byte_values(rows)
    narrow = printable_ascii_prefix(bytes_seen)
    wide = utf16le_ascii_prefix(bytes_seen)
    candidates = []
    for width, text in ((1, narrow), (2, wide)):
        if len(text) >= 3:
            candidates.append({"unitBytes": width, "sample": text})
    for text in quoted:
        if len(text) >= 3 and not any(item["sample"] == text for item in candidates):
            candidates.append({"unitBytes": 1, "sample": text, "source": "gdb-x/s"})
    return {
        "quotedStrings": quoted[:4],
        "byteCount": len(bytes_seen),
        "candidateTcharLayouts": candidates[:4],
    }


def review_category(role, classification):
    if classification["kind"] == "scalar":
        return "scalar"
    if role in PATH_POINTER_ROLES:
        return "path-or-name-pointer"
    if role in {"Outer", "OuterPtr", "Class", "BaseClass"}:
        return "object-pointer"
    if role == "Sandbox":
        return "package-map-pointer"
    return classification["kind"]


def review(evidence, hit_index=0, signature_family=""):
    hits = trace_hits(evidence)
    shape_blockers = evidence_shape_blockers(evidence)
    target_identity = trace_target_identity(evidence)
    resolved_hit_index = selected_hit_index(evidence, hit_index=hit_index, signature_family=signature_family)
    if resolved_hit_index < 0 or resolved_hit_index >= len(hits) or not isinstance(hits[resolved_hit_index], dict):
        family = signature_family or "StaticLoadClass"
        spec = SIGNATURES[family]
        blockers = list(shape_blockers)
        if resolved_hit_index >= 0 and resolved_hit_index < len(hits) and not isinstance(hits[resolved_hit_index], dict):
            blockers.append("selected runtime trace hit must be a JSON object")
        blockers.append("no runtime trace hit available for ABI review")
        return {
            "schemaVersion": SCHEMA_VERSION,
            "sourceEvidence": evidence.get("sourceLog", ""),
            "sourceEvidenceJson": evidence.get("sourceEvidenceJson", ""),
            "sourceEvidenceJsonSha256": evidence.get("sourceEvidenceJsonSha256", ""),
            "sourceLogSha256": evidence.get("sourceLogSha256", ""),
            "sourceLogExists": evidence.get("sourceLogExists"),
            "sourceTracePlan": evidence.get("sourceTracePlan", ""),
            "sourceTracePlanSchemaVersion": evidence.get("sourceTracePlanSchemaVersion", ""),
            "sourcePromotionAcceptanceSchemaVersion": evidence.get("sourcePromotionAcceptanceSchemaVersion", ""),
            "sourceExternalPlan": evidence.get("sourceExternalPlan", ""),
            **target_identity,
            "hitIndex": resolved_hit_index,
            "requestedHitIndex": hit_index,
            "signatureFamily": family,
            "requiredSignature": spec["signature"],
            "readyForManualAbiReview": False,
            "arguments": [],
            "stackArguments": spec["stack"],
            "blockers": blockers,
        }
    hit = hits[resolved_hit_index]
    family = family_for_hit(hit, signature_family)
    spec = SIGNATURES[family]
    raw_registers = hit.get("registers", {}) or {}
    registers = raw_registers if isinstance(raw_registers, dict) else {}
    raw_stack = hit.get("stack", []) or []
    stack_lines = raw_stack if isinstance(raw_stack, list) else []
    raw_disassembly = hit.get("disassembly", []) or []
    disassembly_lines = raw_disassembly if isinstance(raw_disassembly, list) else []
    stack_details = stack_argument_details(stack_lines, spec["stack"])
    arguments = []
    for register, role in spec["registers"]:
        value = registers.get(register, "")
        classification = classify_argument(role, value)
        memory = register_memory_details(hit, register) if classification["kind"] == "pointer" else {
            "provided": False,
            "lineCount": 0,
            "sample": [],
        }
        arguments.append(
            {
                "register": register,
                "role": role,
                "capturedValue": value,
                "present": classification["present"],
                "kind": classification["kind"],
                "reviewCategory": review_category(role, classification),
                "required": classification["required"],
                "nullAllowed": classification["nullAllowed"],
                "looksSane": classification["looksSane"],
                "note": classification["note"],
                "memory": memory,
            }
        )
    blockers = list(shape_blockers)
    blockers.extend(
        scalar_provenance_blockers(
            evidence,
            (
            "sourceLog",
            "sourceLogSha256",
            "sourceEvidenceJson",
            "sourceEvidenceJsonSha256",
            "sourceTracePlan",
            "sourceTracePlanSchemaVersion",
            "sourcePromotionAcceptanceSchemaVersion",
            "sourceExternalPlan",
            "pid",
                "imageRangeSource",
                "imageBase",
                "imageStart",
                "imageEnd",
                "imagePath",
                "imagePerms",
            ),
        )
    )
    blockers.extend(
        scalar_provenance_blockers(
            hit,
            ("seed", "callerImageOffset", "ripImageOffset"),
        )
    )
    if not evidence.get("sourceLog", ""):
        blockers.append("missing runtime trace sourceLog provenance")
    if "sourceLogExists" not in evidence:
        blockers.append("missing runtime trace sourceLogExists provenance")
    elif evidence.get("sourceLogExists") is not True:
        blockers.append("runtime trace sourceLog does not exist")
    if evidence.get("tracePidMatchesRequested") is not True:
        blockers.append("missing runtime trace PID match provenance")
    hit_seed = hit.get("seed", "")
    if not hit_seed:
        blockers.append("missing trace hit seed provenance")
    if hit_seed and hit_seed != family:
        blockers.append(f"selected trace hit seed {hit_seed} does not match signature family {family}")
    if hit.get("targetImageCaller") is not True:
        blockers.append("caller is not proven inside target image")
    if hit.get("tracePidMatchesRequested") is not True:
        blockers.append("selected runtime trace hit is missing PID match provenance")
    if hit.get("traceAddressMatchesBase") is not True:
        blockers.append("selected runtime trace hit address does not match image base plus seed imageOffset")
    blockers.extend(register_memory_shape_blockers(hit))
    if not hit.get("callerImageOffset"):
        blockers.append("missing callerImageOffset call-frame provenance")
    if not hit.get("ripImageOffset"):
        blockers.append("missing ripImageOffset call-frame provenance")
    if not disassembly_lines:
        blockers.append("missing disassembly context")
    if not stack_lines:
        blockers.append("missing stack context")
    if any(item["required"] and not item["present"] for item in arguments):
        blockers.append("one or more SysV argument registers were not captured")
    required_bad = [
        f"{item['register']}:{item['role']}"
        for item in arguments
        if item["required"] and not item["looksSane"]
    ]
    if required_bad:
        blockers.append("required argument roles are missing or null: " + ", ".join(required_bad))
    missing_path_memory = [
        f"{item['register']}:{item['role']}"
        for item in arguments
        if item["role"] in REQUIRED_PATH_MEMORY_ROLES
        and item["required"]
        and item["looksSane"]
        and not item.get("memory", {}).get("provided", False)
    ]
    if missing_path_memory:
        blockers.append("missing memory snapshot for path/name pointer arguments: " + ", ".join(missing_path_memory))
    stack_bad = [
        f"stack[{item['slot']}]:{item['role']}"
        for item in stack_details
        if item["required"] and not item["looksSane"]
    ]
    if stack_bad:
        blockers.append("required stack argument roles are missing or null: " + ", ".join(stack_bad))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceEvidence": evidence.get("sourceLog", ""),
        "sourceEvidenceJson": evidence.get("sourceEvidenceJson", ""),
        "sourceEvidenceJsonSha256": evidence.get("sourceEvidenceJsonSha256", ""),
        "sourceLogSha256": evidence.get("sourceLogSha256", ""),
        "sourceLogExists": evidence.get("sourceLogExists"),
        "sourceTracePlan": evidence.get("sourceTracePlan", ""),
        "sourceTracePlanSchemaVersion": evidence.get("sourceTracePlanSchemaVersion", ""),
        "sourcePromotionAcceptanceSchemaVersion": evidence.get("sourcePromotionAcceptanceSchemaVersion", ""),
        "sourceExternalPlan": evidence.get("sourceExternalPlan", ""),
        **target_identity,
        "hitIndex": resolved_hit_index,
        "requestedHitIndex": hit_index,
        "selectedHitSeed": hit_seed,
        "signatureFamily": family,
        "requiredSignature": spec["signature"],
        "callerImageOffset": hit.get("callerImageOffset", ""),
        "ripImageOffset": hit.get("ripImageOffset", ""),
        "readyForManualAbiReview": not blockers,
        "arguments": arguments,
        "stackArguments": spec["stack"],
        "stackArgumentDetails": stack_details,
        "requiredEvidence": spec["requires"],
        "blockers": blockers,
        "disassembly": disassembly_lines,
        "registerMemory": hit.get("registerMemory", {}) or {},
        "stack": stack_lines,
    }


def markdown(report):
    lines = ["# UE4SS Package ABI Review", ""]
    lines.append(f"- Signature family: `{report['signatureFamily']}`")
    if report.get("selectedHitSeed"):
        lines.append(f"- Selected hit seed: `{report['selectedHitSeed']}`")
    lines.append(f"- Required signature: `{report['requiredSignature']}`")
    if report.get("sourceEvidenceJsonSha256"):
        lines.append(f"- Source evidence JSON SHA-256: `{report.get('sourceEvidenceJsonSha256', '')}`")
    if report.get("sourceLogSha256"):
        lines.append(f"- Source log SHA-256: `{report.get('sourceLogSha256', '')}`")
    if "sourceLogExists" in report:
        lines.append(f"- Source log exists: `{str(report.get('sourceLogExists')).lower()}`")
    lines.append(f"- Ready for manual ABI review: `{str(report['readyForManualAbiReview']).lower()}`")
    if report.get("callerImageOffset"):
        lines.append(f"- Caller image offset: `{report['callerImageOffset']}`")
    if report.get("ripImageOffset"):
        lines.append(f"- RIP image offset: `{report['ripImageOffset']}`")
    lines.append("")
    lines.append("## Arguments")
    lines.append("")
    if report["arguments"]:
        for arg in report["arguments"]:
            lines.append(
                f"- `{arg['register']}` `{arg['role']}` = `{arg['capturedValue']}` "
                f"kind=`{arg.get('kind', '')}` category=`{arg.get('reviewCategory', '')}` "
                f"required=`{str(arg.get('required', False)).lower()}` "
                f"sane=`{str(arg.get('looksSane', False)).lower()}` "
                f"memoryLines=`{arg.get('memory', {}).get('lineCount', 0)}`"
            )
            hints = (arg.get("memory", {}) or {}).get("hints", {}) or {}
            layouts = hints.get("candidateTcharLayouts", []) or []
            if layouts:
                rendered = ", ".join(
                    f"{item.get('unitBytes')}:{item.get('sample', '')}"
                    for item in layouts
                )
                lines.append(f"  - memory hint: candidateTcharLayouts=`{rendered}`")
    else:
        lines.append("- none")
    if report.get("stackArguments"):
        lines.append("")
        lines.append("## Stack Arguments")
        lines.append("")
        details = report.get("stackArgumentDetails") or []
        if details:
            for arg in details:
                lines.append(
                    f"- slot `{arg['slot']}` `{arg['role']}` = `{arg['capturedValue']}` "
                    f"kind=`{arg.get('kind', '')}` required=`{str(arg.get('required', False)).lower()}` "
                    f"sane=`{str(arg.get('looksSane', False)).lower()}`"
                )
        else:
            for role in report["stackArguments"]:
                lines.append(f"- `{role}`")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a SysV ABI review checklist from UE4SS package trace evidence.")
    parser.add_argument("evidence_json")
    parser.add_argument("--hit-index", default="0")
    parser.add_argument("--signature-family", choices=sorted(SIGNATURES), default="")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    hit_index = "auto" if args.hit_index == "auto" else int(args.hit_index)
    report = review(load_trace_evidence(args.evidence_json), hit_index=hit_index, signature_family=args.signature_family)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
