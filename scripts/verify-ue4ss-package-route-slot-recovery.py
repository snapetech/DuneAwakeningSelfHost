#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-route-slot-recovery-verification/v1"
EVIDENCE_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-evidence/v1"
NEXT_ACTION_SCHEMA_VERSION = "dune-ue4ss-package-next-action/v1"


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def valid_hex(value):
    return isinstance(value, str) and value.startswith("0x") and len(value) > 2 and all(
        char in "0123456789abcdefABCDEF" for char in value[2:]
    )


def normalize_hex(value):
    return f"0x{int(str(value), 16):x}" if valid_hex(value) else ""


def next_action_recovery(next_action):
    if not isinstance(next_action, dict):
        return {}, ["next-action JSON must be an object"]
    blockers = []
    if next_action.get("schemaVersion") != NEXT_ACTION_SCHEMA_VERSION:
        blockers.append(f"next-action schemaVersion must be {NEXT_ACTION_SCHEMA_VERSION}")
    recovery = next_action.get("routeSlotRecovery")
    if not isinstance(recovery, dict) or not recovery:
        blockers.append("next-action routeSlotRecovery is missing")
        return {}, blockers
    required = recovery.get("requiredRouteTrace")
    if not isinstance(required, dict) or not required:
        blockers.append("next-action routeSlotRecovery.requiredRouteTrace is missing")
        required = {}
    route = normalize_hex(required.get("address", ""))
    if not route:
        blockers.append("required route trace address must be a hex image offset")
    review_field = required.get("reviewField", "")
    if review_field != "routeVtableStaticSlotMatches":
        blockers.append("required route trace reviewField must be routeVtableStaticSlotMatches")
    slots = []
    raw_slots = required.get("slots", [])
    if not isinstance(raw_slots, list) or not raw_slots:
        blockers.append("required route trace slots must be a non-empty array")
    else:
        for value in raw_slots:
            slot = normalize_hex(value)
            if not slot:
                blockers.append("required route trace slots must be hex offsets")
                break
            if slot not in slots:
                slots.append(slot)
    registers = []
    raw_registers = required.get("registers", [])
    if not isinstance(raw_registers, list) or not raw_registers:
        blockers.append("required route trace registers must be a non-empty array")
    else:
        for register in raw_registers:
            if not isinstance(register, str) or not register:
                blockers.append("required route trace registers must be strings")
                break
            if register not in registers:
                registers.append(register)
    recovered = {
        "routeAddress": route,
        "reviewField": review_field,
        "slots": slots,
        "registers": registers,
    }
    live_runbook = next_action.get("liveTraceRunbook")
    if isinstance(live_runbook, dict) and live_runbook:
        requirement = live_runbook.get("routeSlotTraceRequirement")
        if not isinstance(requirement, dict) or not requirement:
            blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement is missing")
        else:
            expected_route = normalize_hex(requirement.get("routeAddress", ""))
            expected_slots = []
            expected_registers = []
            for value in requirement.get("requiredSlots", []) or []:
                slot = normalize_hex(value)
                if slot and slot not in expected_slots:
                    expected_slots.append(slot)
            for register in requirement.get("requiredRegisters", []) or []:
                if isinstance(register, str) and register and register not in expected_registers:
                    expected_registers.append(register)
            if requirement.get("expectedTraceMarker") != "UE4SS_PACKAGE_ROUTE_TRACE_HIT":
                blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT")
            if requirement.get("reviewField") != "routeVtableStaticSlotMatches":
                blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement reviewField must be routeVtableStaticSlotMatches")
            if expected_route != route:
                blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement routeAddress does not match required route trace")
            if expected_slots != slots:
                blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement requiredSlots do not match required route trace")
            if expected_registers != registers:
                blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement requiredRegisters do not match required route trace")
    return recovered, blockers


def route_hit_matches(evidence, route_address, slots, registers):
    matches = []
    for index, hit in enumerate(evidence.get("routeHits", []) or []):
        if not isinstance(hit, dict):
            continue
        image_offset = normalize_hex(hit.get("imageOffset", ""))
        caller_offset = normalize_hex(hit.get("callerImageOffset", ""))
        matched_field = ""
        if image_offset == route_address:
            matched_field = "imageOffset"
        elif caller_offset == route_address:
            matched_field = "callerImageOffset"
        if not matched_field:
            continue
        static_matches = hit.get("routeVtableStaticSlotMatches", [])
        if not isinstance(static_matches, list):
            static_matches = []
        by_slot = {}
        for match in static_matches:
            if not isinstance(match, dict):
                continue
            slot = normalize_hex(match.get("slotOffset", ""))
            register = match.get("register", "")
            if slot and register:
                by_slot.setdefault(slot, []).append(match)
        present_slots = sorted(by_slot)
        missing_slots = [slot for slot in slots if slot not in by_slot]
        present_registers = sorted(
            {
                str(match.get("register", ""))
                for rows in by_slot.values()
                for match in rows
                if match.get("register", "")
            }
        )
        missing_registers = [register for register in registers if register not in present_registers]
        target_offsets = [
            match.get("targetImageOffset", "") or match.get("target", "")
            for rows in by_slot.values()
            for match in rows
            if match.get("targetImageOffset", "") or match.get("target", "")
        ]
        matches.append(
            {
                "hitIndex": index,
                "imageOffset": hit.get("imageOffset", ""),
                "address": hit.get("address", ""),
                "rip": hit.get("rip", ""),
                "callerImageOffset": hit.get("callerImageOffset", ""),
                "matchedField": matched_field,
                "presentSlots": present_slots,
                "missingSlots": missing_slots,
                "presentRegisters": present_registers,
                "missingRegisters": missing_registers,
                "targetOffsets": target_offsets,
                "ready": not missing_slots and not missing_registers and bool(target_offsets),
            }
        )
    return matches


def next_trace_requirement(required, matches):
    if not required:
        return {}
    missing_slots = list(required.get("slots", []) or [])
    missing_registers = list(required.get("registers", []) or [])
    if matches:
        missing_slots = sorted(
            {
                slot
                for match in matches
                for slot in (match.get("missingSlots", []) or [])
            }
        )
        missing_registers = sorted(
            {
                register
                for match in matches
                for register in (match.get("missingRegisters", []) or [])
            }
        )
    return {
        "routeAddress": required.get("routeAddress", ""),
        "reviewField": required.get("reviewField", ""),
        "requiredSlots": list(required.get("slots", []) or []),
        "requiredRegisters": list(required.get("registers", []) or []),
        "missingSlots": missing_slots,
        "missingRegisters": missing_registers,
        "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
        "expectedReviewField": "routeVtableStaticSlotMatches",
    }


def report(evidence_path, next_action_path):
    blockers = []
    try:
        evidence = load_json(evidence_path)
    except FileNotFoundError:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "evidence": str(evidence_path),
            "nextAction": str(next_action_path),
            "blockers": ["runtime trace evidence JSON is missing"],
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "evidence": str(evidence_path),
            "nextAction": str(next_action_path),
            "blockers": [f"runtime trace evidence JSON is unreadable: {exc}"],
        }
    try:
        next_action = load_json(next_action_path)
    except FileNotFoundError:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "evidence": str(evidence_path),
            "nextAction": str(next_action_path),
            "blockers": ["next-action JSON is missing"],
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "evidence": str(evidence_path),
            "nextAction": str(next_action_path),
            "blockers": [f"next-action JSON is unreadable: {exc}"],
        }
    if evidence.get("schemaVersion") != EVIDENCE_SCHEMA_VERSION:
        blockers.append(f"runtime trace evidence schemaVersion must be {EVIDENCE_SCHEMA_VERSION}")
    required, required_blockers = next_action_recovery(next_action)
    blockers.extend(required_blockers)
    matches = []
    if required and not required_blockers:
        matches = route_hit_matches(
            evidence,
            required["routeAddress"],
            required["slots"],
            required["registers"],
        )
        if not matches:
            blockers.append(f"no route hit found for {required['routeAddress']}")
        elif not any(match.get("ready") for match in matches):
            blockers.append("route hits did not contain all required static vtable slot matches")
    ready = not blockers and any(match.get("ready") for match in matches)
    data = {
        "schemaVersion": SCHEMA_VERSION,
        "ready": ready,
        "evidence": str(evidence_path),
        "nextAction": str(next_action_path),
        "requiredRouteTrace": required,
        "matchCount": len(matches),
        "matches": matches,
        "blockers": blockers,
    }
    if not ready:
        requirement = next_trace_requirement(required, matches)
        if requirement:
            data["nextTraceRequirement"] = requirement
    return data


def markdown(data):
    lines = ["# UE4SS Package Route Slot Recovery Verification", ""]
    lines.append(f"- Ready: `{str(data.get('ready')).lower()}`")
    lines.append(f"- Evidence: `{data.get('evidence', '')}`")
    lines.append(f"- Next action: `{data.get('nextAction', '')}`")
    required = data.get("requiredRouteTrace") or {}
    if required:
        lines.append(
            f"- Required: route=`{required.get('routeAddress', '')}` "
            f"field=`{required.get('reviewField', '')}` "
            f"slots=`{', '.join(required.get('slots', []))}` "
            f"registers=`{', '.join(required.get('registers', []))}`"
        )
    for blocker in data.get("blockers", []):
        lines.append(f"- Blocker: {blocker}")
    requirement = data.get("nextTraceRequirement") or {}
    if requirement:
        lines.append(
            f"- Next trace requirement: marker=`{requirement.get('expectedTraceMarker', '')}` "
            f"route=`{requirement.get('routeAddress', '')}` "
            f"field=`{requirement.get('expectedReviewField', '')}` "
            f"missingSlots=`{', '.join(requirement.get('missingSlots', [])) or 'none'}` "
            f"missingRegisters=`{', '.join(requirement.get('missingRegisters', [])) or 'none'}`"
        )
    if data.get("matches"):
        lines.extend(["", "## Matches", ""])
        for match in data.get("matches", []):
            lines.append(
                f"- hitIndex=`{match.get('hitIndex', '')}` ready=`{str(match.get('ready')).lower()}` "
                f"imageOffset=`{match.get('imageOffset', '')}` caller=`{match.get('callerImageOffset', '')}` "
                f"matchedField=`{match.get('matchedField', '')}` "
                f"slots=`{', '.join(match.get('presentSlots', []))}` "
                f"registers=`{', '.join(match.get('presentRegisters', []))}` "
                f"targets=`{', '.join(match.get('targetOffsets', []))}`"
            )
            for slot in match.get("missingSlots", []):
                lines.append(f"  - missing slot: `{slot}`")
            for register in match.get("missingRegisters", []):
                lines.append(f"  - missing register: `{register}`")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify route-slot recovery evidence from a UE4SS package runtime trace.")
    parser.add_argument("evidence_json")
    parser.add_argument("--next-action-json", default="build/server-current-anchor-prep/ue4ss-package-next-action.json")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    data = report(args.evidence_json, args.next_action_json)
    if args.format == "json":
        json.dump(data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(data))
    return 0 if data.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
