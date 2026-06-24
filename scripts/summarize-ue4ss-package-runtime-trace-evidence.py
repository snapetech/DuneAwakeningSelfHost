#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-evidence/v1"
TRACE_PLAN_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-plan/v1"
PROMOTION_ACCEPTANCE_SCHEMA_VERSION = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
ARMED_RE = re.compile(
    r"UE4SS_PACKAGE_TRACE armed pid=(?P<pid>\d+) base=0x(?P<base>[0-9a-fA-F]+) "
    r"build_id=(?P<build_id>[0-9a-fA-F]+|unknown) seeds=(?P<seeds>\d+)"
)
HIT_RE = re.compile(
    r"UE4SS_PACKAGE_TRACE_HIT seed=(?P<seed>\S+) imageOffset=(?P<image_offset>0x[0-9a-fA-F]+) "
    r"addr=(?P<addr>0x[0-9a-fA-F]+) rip=(?P<rip>0x[0-9a-fA-F]+|\(nil\)) "
    r"rdi=(?P<rdi>0x[0-9a-fA-F]+|\(nil\)) rsi=(?P<rsi>0x[0-9a-fA-F]+|\(nil\)) "
    r"rdx=(?P<rdx>0x[0-9a-fA-F]+|\(nil\)) rcx=(?P<rcx>0x[0-9a-fA-F]+|\(nil\)) "
    r"r8=(?P<r8>0x[0-9a-fA-F]+|\(nil\)) r9=(?P<r9>0x[0-9a-fA-F]+|\(nil\)) "
    r"(?:rbx=(?P<rbx>0x[0-9a-fA-F]+|\(nil\)) r12=(?P<r12>0x[0-9a-fA-F]+|\(nil\)) "
    r"r13=(?P<r13>0x[0-9a-fA-F]+|\(nil\)) r14=(?P<r14>0x[0-9a-fA-F]+|\(nil\)) "
    r"r15=(?P<r15>0x[0-9a-fA-F]+|\(nil\)) )?"
    r"rsp=(?P<rsp>0x[0-9a-fA-F]+|\(nil\)) rbp=(?P<rbp>0x[0-9a-fA-F]+|\(nil\))"
)
METHOD_HIT_RE = re.compile(
    r"UE4SS_PACKAGE_METHOD_TRACE_HIT imageOffset=(?P<image_offset>0x[0-9a-fA-F]+) "
    r"addr=(?P<addr>0x[0-9a-fA-F]+) slot=(?P<slot>\S+) owner=\"(?P<owner>.*?)\" "
    r"rip=(?P<rip>0x[0-9a-fA-F]+|\(nil\)) "
    r"rdi=(?P<rdi>0x[0-9a-fA-F]+|\(nil\)) rsi=(?P<rsi>0x[0-9a-fA-F]+|\(nil\)) "
    r"rdx=(?P<rdx>0x[0-9a-fA-F]+|\(nil\)) rcx=(?P<rcx>0x[0-9a-fA-F]+|\(nil\)) "
    r"r8=(?P<r8>0x[0-9a-fA-F]+|\(nil\)) r9=(?P<r9>0x[0-9a-fA-F]+|\(nil\)) "
    r"rsp=(?P<rsp>0x[0-9a-fA-F]+|\(nil\)) rbp=(?P<rbp>0x[0-9a-fA-F]+|\(nil\))"
)
ROUTE_HIT_RE = re.compile(
    r"UE4SS_PACKAGE_ROUTE_TRACE_HIT imageOffset=(?P<image_offset>0x[0-9a-fA-F]+) "
    r"addr=(?P<addr>0x[0-9a-fA-F]+) rip=(?P<rip>0x[0-9a-fA-F]+|\(nil\)) "
    r"rdi=(?P<rdi>0x[0-9a-fA-F]+|\(nil\)) rsi=(?P<rsi>0x[0-9a-fA-F]+|\(nil\)) "
    r"rdx=(?P<rdx>0x[0-9a-fA-F]+|\(nil\)) rcx=(?P<rcx>0x[0-9a-fA-F]+|\(nil\)) "
    r"r8=(?P<r8>0x[0-9a-fA-F]+|\(nil\)) r9=(?P<r9>0x[0-9a-fA-F]+|\(nil\)) "
    r"(?:rbx=(?P<rbx>0x[0-9a-fA-F]+|\(nil\)) r12=(?P<r12>0x[0-9a-fA-F]+|\(nil\)) "
    r"r13=(?P<r13>0x[0-9a-fA-F]+|\(nil\)) r14=(?P<r14>0x[0-9a-fA-F]+|\(nil\)) "
    r"r15=(?P<r15>0x[0-9a-fA-F]+|\(nil\)) )?"
    r"rsp=(?P<rsp>0x[0-9a-fA-F]+|\(nil\)) rbp=(?P<rbp>0x[0-9a-fA-F]+|\(nil\))"
)
BT_RE = re.compile(r"^#(?P<index>\d+)\s+(?P<ip>0x[0-9a-fA-F]+)\s+in\s+(?P<rest>.*)$")
REGMEM_BEGIN_RE = re.compile(r"UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=(?P<register>[a-z0-9]+)")
REGMEM_END_RE = re.compile(r"UE4SS_PACKAGE_TRACE_REGMEM_END reg=(?P<register>[a-z0-9]+)")
ROUTE_OBJECT_BEGIN_RE = re.compile(r"UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=(?P<register>[a-z0-9]+)")
ROUTE_OBJECT_END_RE = re.compile(r"UE4SS_PACKAGE_ROUTE_OBJECT_END reg=(?P<register>[a-z0-9]+)")
ROUTE_VTABLE_BEGIN_RE = re.compile(r"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg=(?P<register>[a-z0-9]+)")
ROUTE_VTABLE_END_RE = re.compile(r"UE4SS_PACKAGE_ROUTE_VTABLE_END reg=(?P<register>[a-z0-9]+)")
PACKAGE_SIGNATURE_FAMILIES = ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName")
FAMILY_PRIORITY = {
    "StaticLoadClass": 0,
    "StaticLoadObject": 1,
    "LoadPackage": 2,
    "LoadObject": 3,
    "ResolveName": 4,
}
FAMILY_REQUIRED_MEMORY_REGISTERS = {
    "StaticLoadObject": ("rdx",),
    "StaticLoadClass": ("rdx",),
    "LoadObject": ("rsi",),
    "LoadPackage": ("rsi",),
    "ResolveName": ("rsi",),
}
ROUTE_STATIC_VTABLE_SLOTS = {
    "child-dispatch-slot-0x3a0": 0x3A0,
    "wrapper-dispatch-slot-0x3d8": 0x3D8,
}


def parse_int(value):
    if value in (None, "", "(nil)"):
        return None
    return int(value, 16)


def hex_or_empty(value):
    return "" if value is None else f"0x{value:x}"


def match_hex_or_empty(match, name):
    try:
        return hex_or_empty(parse_int(match.group(name)))
    except IndexError:
        return ""


def file_sha256(path):
    candidate = Path(path)
    if not candidate.is_file():
        return ""
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shared_library_path(path):
    return (
        "/lib/" in path
        or "/lib64/" in path
        or "/usr/lib/" in path
        or path.endswith(".so")
        or ".so." in path
    )


def executable_image_range_for_pid(pid):
    if not pid:
        return None
    exe = ""
    try:
        exe = str(Path(f"/proc/{pid}/exe").resolve())
    except OSError:
        exe = ""
    try:
        lines = Path(f"/proc/{pid}/maps").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    first_exe_mapping = None
    executable_mapping = None
    first_generic_mapping = None
    generic_executable_mapping = None
    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        address, perms, offset, _, _, path = parts[:6]
        if exe and path != exe:
            continue
        if not exe and not path.startswith("/"):
            continue
        start_s, end_s = address.split("-", 1)
        start = int(start_s, 16)
        end = int(end_s, 16)
        file_offset = int(offset, 16)
        mapping = {
            "start": start,
            "end": end,
            "fileOffset": file_offset,
            "perms": perms,
            "path": path,
        }
        if exe and (first_exe_mapping is None or file_offset < first_exe_mapping["fileOffset"]):
            first_exe_mapping = mapping
        if not exe:
            rank = (1 if shared_library_path(path) else 0, file_offset, start, path)
            if first_generic_mapping is None or rank < first_generic_mapping[0]:
                first_generic_mapping = (rank, mapping)
            if "x" in perms and (generic_executable_mapping is None or rank < generic_executable_mapping[0]):
                generic_executable_mapping = (rank, mapping)
        if "x" in perms and executable_mapping is None:
            executable_mapping = {
                "start": start,
                "end": end,
                "fileOffset": file_offset,
                "perms": perms,
                "path": path,
            }
    if not exe and generic_executable_mapping:
        executable_mapping = generic_executable_mapping[1]
        first_exe_mapping = first_generic_mapping[1] if first_generic_mapping else executable_mapping
    if not executable_mapping:
        return None
    base = first_exe_mapping["start"] - first_exe_mapping["fileOffset"] if first_exe_mapping else executable_mapping["start"]
    return {
        "pid": pid,
        "base": base,
        "imageStart": executable_mapping["start"],
        "imageEnd": executable_mapping["end"],
        "fileOffset": executable_mapping["fileOffset"],
        "perms": executable_mapping["perms"],
        "path": executable_mapping["path"],
    }


def parse_log(path):
    armed = []
    hits = []
    method_hits = []
    route_hits = []
    current_hit = None
    capture = None
    capture_register = ""
    log_path = Path(path)
    if not log_path.exists():
        return armed, hits, method_hits, route_hits
    for raw_line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        armed_match = ARMED_RE.search(line)
        if armed_match:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before armed record")
                capture = None
                capture_register = ""
            armed.append(
                {
                    "pid": int(armed_match.group("pid")),
                    "base": f"0x{int(armed_match.group('base'), 16):x}",
                    "buildId": armed_match.group("build_id"),
                    "seedCount": int(armed_match.group("seeds")),
                }
            )
            continue
        hit_match = HIT_RE.search(line)
        if hit_match:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before next hit")
                capture = None
                capture_register = ""
            hit = {
                "seed": hit_match.group("seed"),
                "imageOffset": f"0x{int(hit_match.group('image_offset'), 16):x}",
                "seedAddress": f"0x{int(hit_match.group('addr'), 16):x}",
                "rip": hex_or_empty(parse_int(hit_match.group("rip"))),
                "registers": {
                    name: match_hex_or_empty(hit_match, name)
                    for name in ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "rbx", "r12", "r13", "r14", "r15", "rsp", "rbp")
                },
                "backtrace": [],
                "disassembly": [],
                "registerMemory": {},
                "stack": [],
                "parseWarnings": [],
            }
            hits.append(hit)
            current_hit = hit
            continue
        method_hit_match = METHOD_HIT_RE.search(line)
        if method_hit_match:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before next method hit")
                capture = None
                capture_register = ""
            method_hit = {
                "owner": method_hit_match.group("owner"),
                "slotIndex": method_hit_match.group("slot"),
                "imageOffset": f"0x{int(method_hit_match.group('image_offset'), 16):x}",
                "address": f"0x{int(method_hit_match.group('addr'), 16):x}",
                "rip": hex_or_empty(parse_int(method_hit_match.group("rip"))),
                "registers": {
                    name: hex_or_empty(parse_int(method_hit_match.group(name)))
                    for name in ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "rsp", "rbp")
                },
                "backtrace": [],
                "disassembly": [],
                "stack": [],
                "parseWarnings": [],
            }
            method_hits.append(method_hit)
            current_hit = method_hit
            continue
        route_hit_match = ROUTE_HIT_RE.search(line)
        if route_hit_match:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before next route hit")
                capture = None
                capture_register = ""
            route_hit = {
                "imageOffset": f"0x{int(route_hit_match.group('image_offset'), 16):x}",
                "address": f"0x{int(route_hit_match.group('addr'), 16):x}",
                "rip": hex_or_empty(parse_int(route_hit_match.group("rip"))),
                "registers": {
                    name: match_hex_or_empty(route_hit_match, name)
                    for name in ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "rbx", "r12", "r13", "r14", "r15", "rsp", "rbp")
                },
                "backtrace": [],
                "disassembly": [],
                "stack": [],
                "parseWarnings": [],
            }
            route_hits.append(route_hit)
            current_hit = route_hit
            continue
        regmem_begin = REGMEM_BEGIN_RE.search(line)
        if regmem_begin:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before register memory")
            capture = "registerMemory"
            capture_register = regmem_begin.group("register")
            if current_hit is not None:
                current_hit.setdefault("registerMemory", {}).setdefault(capture_register, [])
            continue
        regmem_end = REGMEM_END_RE.search(line)
        if regmem_end and capture == "registerMemory":
            capture = None
            capture_register = ""
            continue
        route_object_begin = ROUTE_OBJECT_BEGIN_RE.search(line)
        if route_object_begin:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before route object memory")
            capture = "routeObjectMemory"
            capture_register = route_object_begin.group("register")
            if current_hit is not None:
                current_hit.setdefault("routeObjectMemory", {}).setdefault(capture_register, [])
            continue
        route_object_end = ROUTE_OBJECT_END_RE.search(line)
        if route_object_end and capture == "routeObjectMemory":
            capture = None
            capture_register = ""
            continue
        route_vtable_begin = ROUTE_VTABLE_BEGIN_RE.search(line)
        if route_vtable_begin:
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before route vtable memory")
            capture = "routeVtableMemory"
            capture_register = route_vtable_begin.group("register")
            if current_hit is not None:
                current_hit.setdefault("routeVtableMemory", {}).setdefault(capture_register, [])
            continue
        route_vtable_end = ROUTE_VTABLE_END_RE.search(line)
        if route_vtable_end and capture == "routeVtableMemory":
            capture = None
            capture_register = ""
            continue
        if line in ("UE4SS_PACKAGE_TRACE_DISASM_BEGIN", "UE4SS_PACKAGE_METHOD_TRACE_DISASM_BEGIN", "UE4SS_PACKAGE_ROUTE_TRACE_DISASM_BEGIN"):
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before disassembly")
            capture = "disassembly"
            capture_register = ""
            continue
        if line in ("UE4SS_PACKAGE_TRACE_DISASM_END", "UE4SS_PACKAGE_METHOD_TRACE_DISASM_END", "UE4SS_PACKAGE_ROUTE_TRACE_DISASM_END"):
            capture = None
            capture_register = ""
            continue
        if line in ("UE4SS_PACKAGE_TRACE_STACK_BEGIN", "UE4SS_PACKAGE_METHOD_TRACE_STACK_BEGIN", "UE4SS_PACKAGE_ROUTE_TRACE_STACK_BEGIN"):
            if capture and current_hit is not None:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before stack")
            capture = "stack"
            capture_register = ""
            continue
        if line in ("UE4SS_PACKAGE_TRACE_STACK_END", "UE4SS_PACKAGE_METHOD_TRACE_STACK_END", "UE4SS_PACKAGE_ROUTE_TRACE_STACK_END"):
            capture = None
            capture_register = ""
            continue
        bt_match = BT_RE.match(line)
        if bt_match and current_hit is not None:
            if capture:
                current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture before backtrace")
                capture = None
                capture_register = ""
            current_hit["backtrace"].append(
                {
                    "index": int(bt_match.group("index")),
                    "ip": f"0x{int(bt_match.group('ip'), 16):x}",
                    "frame": bt_match.group("rest"),
                }
            )
            continue
        if capture == "registerMemory" and current_hit is not None and capture_register:
            current_hit.setdefault("registerMemory", {}).setdefault(capture_register, []).append(raw_line.rstrip())
            continue
        if capture == "routeObjectMemory" and current_hit is not None and capture_register:
            current_hit.setdefault("routeObjectMemory", {}).setdefault(capture_register, []).append(raw_line.rstrip())
            continue
        if capture == "routeVtableMemory" and current_hit is not None and capture_register:
            current_hit.setdefault("routeVtableMemory", {}).setdefault(capture_register, []).append(raw_line.rstrip())
            continue
        if capture and current_hit is not None:
            current_hit.setdefault(capture, []).append(raw_line.rstrip())
            continue
    if capture and current_hit is not None:
        current_hit.setdefault("parseWarnings", []).append(f"unterminated {capture} capture at end of log")
    return armed, hits, method_hits, route_hits


def load_trace_plan(path):
    if not path:
        return {}
    plan_path = Path(path)
    if not plan_path.is_file():
        raise ValueError(f"trace plan not found: {path}")
    with plan_path.open("r", encoding="utf-8", errors="replace") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise ValueError(f"{path} is not a JSON object")
    schema = plan.get("schemaVersion")
    if schema != TRACE_PLAN_SCHEMA_VERSION:
        raise ValueError(f"{path} has schemaVersion {schema!r}; expected {TRACE_PLAN_SCHEMA_VERSION!r}")
    return {
        "sourceTracePlan": str(path),
        "sourceTracePlanSchemaVersion": schema,
        "sourcePromotionAcceptanceSchemaVersion": plan.get("sourcePromotionAcceptanceSchemaVersion", ""),
        "sourceExternalPlan": plan.get("sourceExternalPlan", ""),
    }


def in_range(value, start, end):
    return value is not None and start <= value < end


def parse_gdb_gx_rows(rows):
    entries = []
    for row in rows or []:
        if not isinstance(row, str) or ":" not in row:
            continue
        address_text, values_text = row.split(":", 1)
        try:
            address = int(address_text.strip(), 16)
        except ValueError:
            continue
        values = re.findall(r"0x[0-9a-fA-F]+", values_text)
        for column, value_text in enumerate(values):
            try:
                value = int(value_text, 16)
            except ValueError:
                continue
            entries.append(
                {
                    "address": address + (column * 8),
                    "addressText": f"0x{address + (column * 8):x}",
                    "value": value,
                    "valueText": f"0x{value:x}",
                }
            )
    return entries


def derive_route_vtable_review(route_vtable_memory, image_start=None, image_end=None, base=None):
    if not isinstance(route_vtable_memory, dict):
        return {}, []
    static_slot_indexes = {
        name: slot_offset // 8
        for name, slot_offset in ROUTE_STATIC_VTABLE_SLOTS.items()
    }
    slots_by_register = {}
    matches = []
    for register, rows in route_vtable_memory.items():
        if not isinstance(register, str) or not isinstance(rows, list):
            continue
        entries = parse_gdb_gx_rows(rows)
        if not entries:
            slots_by_register[register] = []
            continue
        vtable_base = entries[0]["address"]
        register_slots = []
        for entry in entries:
            slot_index = (entry["address"] - vtable_base) // 8
            slot_offset = slot_index * 8
            target_image = (
                in_range(entry["value"], image_start, image_end)
                if image_start is not None and image_end is not None
                else None
            )
            target_image_offset = (
                f"0x{entry['value'] - base:x}"
                if base is not None and target_image is not False
                else ""
            )
            slot = {
                "slotIndex": slot_index,
                "slotOffset": f"0x{slot_offset:x}",
                "entryAddress": entry["addressText"],
                "target": entry["valueText"],
                "targetImageOffset": target_image_offset,
                "targetImage": target_image,
            }
            matched_names = [
                name for name, static_index in static_slot_indexes.items() if static_index == slot_index
            ]
            if matched_names:
                slot["staticSlotNames"] = matched_names
                for name in matched_names:
                    matches.append(
                        {
                            "register": register,
                            "name": name,
                            **slot,
                        }
                    )
            register_slots.append(slot)
        slots_by_register[register] = register_slots
    return slots_by_register, matches


def enrich_backtrace(backtrace, image_start=None, image_end=None, base=None):
    frames = []
    for frame in backtrace or []:
        ip = parse_int(frame.get("ip"))
        target_image = in_range(ip, image_start, image_end) if image_start is not None and image_end is not None else None
        image_offset = (
            f"0x{ip - base:x}"
            if base is not None and ip is not None and target_image is not False
            else ""
        )
        frames.append(
            {
                **frame,
                "imageOffset": image_offset,
                "targetImage": target_image,
            }
        )
    return frames


def select_caller_frame(frames):
    for frame in frames:
        if frame.get("index") == 0:
            continue
        if frame.get("targetImage") is True:
            return frame
    for frame in frames:
        if frame.get("index") == 0:
            continue
        return frame
    return None


def enrich_hits(
    hits,
    image_start=None,
    image_end=None,
    base=None,
    trace_pid_matches_requested=None,
    trace_log_has_armed=None,
    trace_armed_count=0,
):
    enriched = []
    for hit in hits:
        family = hit.get("seed", "")
        rip = parse_int(hit.get("rip"))
        seed_address = parse_int(hit.get("seedAddress"))
        image_offset = parse_int(hit.get("imageOffset"))
        expected_seed_address = base + image_offset if base is not None and image_offset is not None else None
        trace_address_matches_base = (
            seed_address == expected_seed_address
            if seed_address is not None and expected_seed_address is not None
            else None
        )
        raw_shape_blockers = hit_shape_blockers(hit)
        register_memory = register_memory_field(hit.get("registerMemory", {}) or {})
        captured_memory_registers = sorted(
            register
            for register, rows in register_memory.items()
            if rows
        )
        required_memory_registers = list(FAMILY_REQUIRED_MEMORY_REGISTERS.get(family, ()))
        missing_required_memory = [
            register for register in required_memory_registers if register not in captured_memory_registers
        ]
        enriched_backtrace = enrich_backtrace(
            list_field(hit.get("backtrace", [])),
            image_start=image_start,
            image_end=image_end,
            base=base if trace_address_matches_base is not False else None,
        )
        caller = select_caller_frame(enriched_backtrace)
        caller_ip = parse_int(caller.get("ip")) if caller else None
        target_image_rip = in_range(rip, image_start, image_end) if image_start is not None and image_end is not None else None
        target_image_caller = (
            in_range(caller_ip, image_start, image_end)
            if image_start is not None and image_end is not None and caller_ip is not None
            else None
        )
        image_relative_rip = (
            f"0x{rip - base:x}"
            if base is not None and rip is not None and target_image_rip is not False and trace_address_matches_base is not False
            else ""
        )
        image_relative_caller = (
            f"0x{caller_ip - base:x}"
            if base is not None and caller_ip is not None and target_image_caller is not False and trace_address_matches_base is not False
            else ""
        )
        route_vtable_slots, route_vtable_static_slot_matches = derive_route_vtable_review(
            hit.get("routeVtableMemory", {}) or {},
            image_start=image_start,
            image_end=image_end,
            base=base if trace_address_matches_base is not False else None,
        )
        blockers = []
        if trace_log_has_armed is False:
            blockers.append("missing trace armed record; cannot prove runtime trace session")
        if trace_armed_count > 1:
            blockers.append("multiple trace armed records; use a fresh single-session trace log")
        if trace_pid_matches_requested is False:
            blockers.append("trace log armed PID does not match requested runtime PID")
        elif trace_pid_matches_requested is not True:
            blockers.append("missing requested runtime PID match provenance")
        if trace_address_matches_base is False:
            blockers.append("trace hit address does not match image base plus seed imageOffset")
        if not list_field(hit.get("backtrace", [])):
            blockers.append("missing backtrace; cannot recover package-loading caller")
        if not list_field(hit.get("disassembly", [])):
            blockers.append("missing disassembly context for ABI review")
        if not list_field(hit.get("stack", [])):
            blockers.append("missing stack context for ABI review")
        if missing_required_memory:
            blockers.append("missing required memory registers: " + ", ".join(missing_required_memory))
        blockers.extend(raw_shape_blockers)
        for warning in list_field(hit.get("parseWarnings", [])):
            blockers.append(f"trace parser warning: {warning}")
        if image_start is None or image_end is None:
            blockers.append("missing executable image range; cannot prove target-image caller")
        elif target_image_caller is not True:
            blockers.append("caller frame is not proven inside target executable image")
        blockers.append("manual ABI review required before promotion")
        blockers.append("guarded LoadAsset or LoadClass native invocation evidence required before completion")
        enriched.append(
            {
                **hit,
                "backtrace": enriched_backtrace,
                "ripImageOffset": image_relative_rip,
                "caller": caller or {},
                "callerImageOffset": image_relative_caller,
                "targetImageRip": target_image_rip,
                "targetImageCaller": target_image_caller,
                "traceAddressMatchesBase": trace_address_matches_base,
                "tracePidMatchesRequested": trace_pid_matches_requested,
                "traceLogHasArmed": trace_log_has_armed,
                "traceArmedCount": trace_armed_count,
                "requiredMemoryRegisters": required_memory_registers,
                "missingRequiredMemoryRegisters": missing_required_memory,
                "promotable": False,
                "blockers": blockers,
            }
        )
    return enriched


def enrich_method_hits(
    method_hits,
    image_start=None,
    image_end=None,
    base=None,
    trace_pid_matches_requested=None,
    trace_log_has_armed=None,
    trace_armed_count=0,
):
    enriched = []
    for hit in method_hits:
        rip = parse_int(hit.get("rip"))
        address = parse_int(hit.get("address"))
        image_offset = parse_int(hit.get("imageOffset"))
        expected_address = base + image_offset if base is not None and image_offset is not None else None
        trace_address_matches_base = (
            address == expected_address
            if address is not None and expected_address is not None
            else None
        )
        enriched_backtrace = enrich_backtrace(
            list_field(hit.get("backtrace", [])),
            image_start=image_start,
            image_end=image_end,
            base=base if trace_address_matches_base is not False else None,
        )
        caller = select_caller_frame(enriched_backtrace)
        caller_ip = parse_int(caller.get("ip")) if caller else None
        target_image_rip = in_range(rip, image_start, image_end) if image_start is not None and image_end is not None else None
        target_image_caller = (
            in_range(caller_ip, image_start, image_end)
            if image_start is not None and image_end is not None and caller_ip is not None
            else None
        )
        image_relative_rip = (
            f"0x{rip - base:x}"
            if base is not None and rip is not None and target_image_rip is not False and trace_address_matches_base is not False
            else ""
        )
        image_relative_caller = (
            f"0x{caller_ip - base:x}"
            if base is not None and caller_ip is not None and target_image_caller is not False and trace_address_matches_base is not False
            else ""
        )
        blockers = []
        if trace_log_has_armed is False:
            blockers.append("missing trace armed record; cannot prove runtime trace session")
        if trace_armed_count > 1:
            blockers.append("multiple trace armed records; use a fresh single-session trace log")
        if trace_pid_matches_requested is False:
            blockers.append("trace log armed PID does not match requested runtime PID")
        elif trace_pid_matches_requested is not True:
            blockers.append("missing requested runtime PID match provenance")
        if trace_address_matches_base is False:
            blockers.append("method trace address does not match image base plus method imageOffset")
        if not list_field(hit.get("backtrace", [])):
            blockers.append("missing backtrace; cannot recover caller route")
        if not list_field(hit.get("disassembly", [])):
            blockers.append("missing disassembly context")
        if not list_field(hit.get("stack", [])):
            blockers.append("missing stack context")
        for warning in list_field(hit.get("parseWarnings", [])):
            blockers.append(f"trace parser warning: {warning}")
        blockers.append("method probes are route-recovery evidence only; capture a package trace hit before promotion")
        enriched.append(
            {
                **hit,
                "backtrace": enriched_backtrace,
                "ripImageOffset": image_relative_rip,
                "caller": caller or {},
                "callerImageOffset": image_relative_caller,
                "targetImageRip": target_image_rip,
                "targetImageCaller": target_image_caller,
                "traceAddressMatchesBase": trace_address_matches_base,
                "tracePidMatchesRequested": trace_pid_matches_requested,
                "traceLogHasArmed": trace_log_has_armed,
                "traceArmedCount": trace_armed_count,
                "promotable": False,
                "blockers": blockers,
            }
        )
    return enriched


def enrich_route_hits(
    route_hits,
    image_start=None,
    image_end=None,
    base=None,
    trace_pid_matches_requested=None,
    trace_log_has_armed=None,
    trace_armed_count=0,
):
    enriched = []
    for hit in route_hits:
        rip = parse_int(hit.get("rip"))
        address = parse_int(hit.get("address"))
        image_offset = parse_int(hit.get("imageOffset"))
        expected_address = base + image_offset if base is not None and image_offset is not None else None
        trace_address_matches_base = (
            address == expected_address
            if address is not None and expected_address is not None
            else None
        )
        enriched_backtrace = enrich_backtrace(
            list_field(hit.get("backtrace", [])),
            image_start=image_start,
            image_end=image_end,
            base=base if trace_address_matches_base is not False else None,
        )
        caller = select_caller_frame(enriched_backtrace)
        caller_ip = parse_int(caller.get("ip")) if caller else None
        target_image_rip = in_range(rip, image_start, image_end) if image_start is not None and image_end is not None else None
        target_image_caller = (
            in_range(caller_ip, image_start, image_end)
            if image_start is not None and image_end is not None and caller_ip is not None
            else None
        )
        image_relative_rip = (
            f"0x{rip - base:x}"
            if base is not None and rip is not None and target_image_rip is not False and trace_address_matches_base is not False
            else ""
        )
        image_relative_caller = (
            f"0x{caller_ip - base:x}"
            if base is not None and caller_ip is not None and target_image_caller is not False and trace_address_matches_base is not False
            else ""
        )
        route_vtable_slots, route_vtable_static_slot_matches = derive_route_vtable_review(
            hit.get("routeVtableMemory", {}) or {},
            image_start=image_start,
            image_end=image_end,
            base=base if trace_address_matches_base is not False else None,
        )
        blockers = []
        if trace_log_has_armed is False:
            blockers.append("missing trace armed record; cannot prove runtime trace session")
        if trace_armed_count > 1:
            blockers.append("multiple trace armed records; use a fresh single-session trace log")
        if trace_pid_matches_requested is False:
            blockers.append("trace log armed PID does not match requested runtime PID")
        elif trace_pid_matches_requested is not True:
            blockers.append("missing requested runtime PID match provenance")
        if trace_address_matches_base is False:
            blockers.append("route trace address does not match image base plus route imageOffset")
        if not list_field(hit.get("backtrace", [])):
            blockers.append("missing backtrace; cannot recover caller route")
        if not list_field(hit.get("disassembly", [])):
            blockers.append("missing disassembly context")
        if not list_field(hit.get("stack", [])):
            blockers.append("missing stack context")
        for warning in list_field(hit.get("parseWarnings", [])):
            blockers.append(f"trace parser warning: {warning}")
        blockers.append("route probes are route-recovery evidence only; capture a package trace hit before promotion")
        enriched.append(
            {
                **hit,
                "backtrace": enriched_backtrace,
                "ripImageOffset": image_relative_rip,
                "caller": caller or {},
                "callerImageOffset": image_relative_caller,
                "targetImageRip": target_image_rip,
                "targetImageCaller": target_image_caller,
                "traceAddressMatchesBase": trace_address_matches_base,
                "tracePidMatchesRequested": trace_pid_matches_requested,
                "traceLogHasArmed": trace_log_has_armed,
                "traceArmedCount": trace_armed_count,
                "routeVtableSlots": route_vtable_slots,
                "routeVtableStaticSlotMatches": route_vtable_static_slot_matches,
                "promotable": False,
                "blockers": blockers,
            }
        )
    return enriched


def summarize_route_slot_recovery(route_hits):
    required_slots = sorted({f"0x{offset:x}" for offset in ROUTE_STATIC_VTABLE_SLOTS.values()})
    matches = []
    for index, hit in enumerate(route_hits or []):
        for match in list_field(hit.get("routeVtableStaticSlotMatches", [])):
            if not isinstance(match, dict):
                continue
            slot = match.get("slotOffset", "")
            target = match.get("targetImageOffset", "") or match.get("target", "")
            if slot and target:
                matches.append(
                    {
                        "hitIndex": index,
                        "imageOffset": hit.get("imageOffset", ""),
                        "callerImageOffset": hit.get("callerImageOffset", ""),
                        "register": match.get("register", ""),
                        "slotOffset": slot,
                        "targetImageOffset": match.get("targetImageOffset", ""),
                        "target": match.get("target", ""),
                    }
                )
    present_slots = sorted({match["slotOffset"] for match in matches})
    missing_slots = [slot for slot in required_slots if slot not in present_slots]
    blockers = []
    if not route_hits:
        blockers.append("no route hits captured")
    if missing_slots:
        blockers.append("missing route vtable static slot matches: " + ", ".join(missing_slots))
    if matches and not any(match.get("targetImageOffset") for match in matches):
        blockers.append("route vtable static slot matches lack target-image offsets")
    return {
        "ready": not blockers,
        "routeHitCount": len(route_hits or []),
        "requiredSlots": required_slots,
        "presentSlots": present_slots,
        "missingSlots": missing_slots,
        "matchCount": len(matches),
        "matches": matches,
        "blockers": blockers,
    }


def list_field(value):
    return value if isinstance(value, list) else []


def register_memory_field(value):
    if not isinstance(value, dict):
        return {}
    return {
        register: rows
        for register, rows in value.items()
        if isinstance(register, str)
        and register
        and isinstance(rows, list)
        and all(isinstance(row, str) for row in rows)
    }


def hit_shape_blockers(hit):
    blockers = []
    seed = hit.get("seed", "")
    if not isinstance(seed, str) or not seed:
        blockers.append("seed must be a non-empty string")
    elif seed not in PACKAGE_SIGNATURE_FAMILIES:
        blockers.append(f"unsupported package trace seed: {seed}")
    for key in ("backtrace", "disassembly", "stack", "parseWarnings"):
        value = hit.get(key, [])
        if value is not None and not isinstance(value, list):
            blockers.append(f"{key} must be a JSON array")
    parse_warnings = hit.get("parseWarnings", [])
    if isinstance(parse_warnings, list) and parse_warnings:
        blockers.append("parseWarnings must be resolved before concrete review")
    if hit.get("traceLogHasArmed") is False:
        blockers.append("missing trace armed record; cannot prove runtime trace session")
    if hit.get("traceArmedCount", 0) > 1:
        blockers.append("multiple trace armed records; use a fresh single-session trace log")
    if hit.get("tracePidMatchesRequested") is False:
        blockers.append("trace log armed PID does not match requested runtime PID")
    elif hit.get("tracePidMatchesRequested") is not True:
        blockers.append("missing requested runtime PID match provenance")
    registers = hit.get("registers", {})
    if registers is not None and not isinstance(registers, dict):
        blockers.append("registers must be a JSON object")
    elif isinstance(registers, dict):
        for register, value in registers.items():
            if not isinstance(register, str) or not register:
                blockers.append("registers contains an invalid register key")
                continue
            if not isinstance(value, str):
                blockers.append(f"registers.{register} must be a string")
    register_memory = hit.get("registerMemory", {})
    if register_memory is not None and not isinstance(register_memory, dict):
        blockers.append("registerMemory must be a JSON object")
    elif isinstance(register_memory, dict):
        for register, rows in register_memory.items():
            if not isinstance(register, str) or not register:
                blockers.append("registerMemory contains an invalid register key")
                continue
            if rows is not None and not isinstance(rows, list):
                blockers.append(f"registerMemory.{register} must be a JSON array")
                continue
            if isinstance(rows, list) and any(not isinstance(row, str) for row in rows):
                blockers.append(f"registerMemory.{register} entries must be strings")
    return blockers


def candidate_review_score(candidate):
    score = 0
    missing_offsets = candidate.get("missingCallFrameOffsets", []) or []
    if candidate.get("targetImageCaller") is True:
        score += 8
    if candidate.get("targetImageRip") is True:
        score += 4
    if candidate.get("disassemblyLines", 0) > 0:
        score += 4
    if candidate.get("stackLines", 0) > 0:
        score += 2
    missing_memory = candidate.get("missingRequiredMemoryRegisters", []) or []
    if not missing_memory:
        score += 4
    if missing_offsets:
        score -= 16
    score -= FAMILY_PRIORITY.get(candidate.get("seed", ""), 9)
    return score


def family_candidates(hits):
    candidates = {}
    for index, hit in enumerate(hits):
        family = hit.get("seed", "")
        if family not in PACKAGE_SIGNATURE_FAMILIES:
            continue
        register_memory = register_memory_field(hit.get("registerMemory", {}) or {})
        captured_memory_registers = sorted(
            register
            for register, rows in register_memory.items()
            if rows
        )
        required_memory_registers = list(FAMILY_REQUIRED_MEMORY_REGISTERS.get(family, ()))
        missing_required_memory = [
            register for register in required_memory_registers if register not in captured_memory_registers
        ]
        missing_offsets = [
            key
            for key in ("callerImageOffset", "ripImageOffset")
            if not hit.get(key)
        ]
        if hit.get("traceAddressMatchesBase") is False:
            missing_offsets.append("traceAddressMatchesBase")
        candidate = {
            "hitIndex": index,
            "seed": family,
            "callerImageOffset": hit.get("callerImageOffset", ""),
            "ripImageOffset": hit.get("ripImageOffset", ""),
            "shapeBlockers": hit_shape_blockers(hit),
            "missingCallFrameOffsets": missing_offsets,
            "targetImageRip": hit.get("targetImageRip"),
            "targetImageCaller": hit.get("targetImageCaller"),
            "traceAddressMatchesBase": hit.get("traceAddressMatchesBase"),
            "disassemblyLines": len(list_field(hit.get("disassembly", []))),
            "stackLines": len(list_field(hit.get("stack", []))),
            "registerMemoryRegisters": captured_memory_registers,
            "requiredMemoryRegisters": required_memory_registers,
            "missingRequiredMemoryRegisters": missing_required_memory,
            "autoSelectedBySignatureFamily": family,
        }
        candidate["reviewScore"] = candidate_review_score(candidate)
        current = candidates.get(family)
        if current is None or (
            candidate["reviewScore"],
            -candidate["hitIndex"],
        ) > (
            current.get("reviewScore", 0),
            -current.get("hitIndex", 0),
        ):
            candidates[family] = candidate
    return candidates


def prioritized_family_candidates(candidates):
    return sorted(
        candidates.values(),
        key=lambda candidate: (
            candidate.get("reviewScore", 0),
            -candidate.get("hitIndex", 0),
        ),
        reverse=True,
    )


def concrete_review_candidates(candidates):
    return [
        candidate
        for candidate in prioritized_family_candidates(candidates)
        if not candidate.get("missingCallFrameOffsets")
        and not candidate.get("missingRequiredMemoryRegisters")
        and not candidate.get("shapeBlockers")
    ]


def build_summary(path, image_start=None, image_end=None, base=None, pid=None, trace_plan=None):
    armed, hits, method_hits, route_hits = parse_log(path)
    source_exists = Path(path).exists()
    image_range_source = "arguments" if image_start is not None and image_end is not None else ""
    trace_pid = pid if pid is not None else (armed[-1].get("pid") if armed else None)
    armed_pid = armed[-1].get("pid") if armed else None
    trace_pid_matches_requested = None
    if pid is not None and armed_pid is not None:
        trace_pid_matches_requested = armed_pid == pid
    if base is None and armed:
        base = parse_int(armed[-1].get("base"))
    pid_range = None
    if (image_start is None or image_end is None or base is None) and pid:
        pid_range = executable_image_range_for_pid(pid)
        if pid_range:
            image_start = image_start if image_start is not None else pid_range["imageStart"]
            image_end = image_end if image_end is not None else pid_range["imageEnd"]
            base = base if base is not None else pid_range["base"]
            image_range_source = "pid"
    enriched_hits = enrich_hits(
        hits,
        image_start=image_start,
        image_end=image_end,
        base=base,
        trace_pid_matches_requested=trace_pid_matches_requested,
        trace_log_has_armed=bool(armed),
        trace_armed_count=len(armed),
    )
    enriched_method_hits = enrich_method_hits(
        method_hits,
        image_start=image_start,
        image_end=image_end,
        base=base,
        trace_pid_matches_requested=trace_pid_matches_requested,
        trace_log_has_armed=bool(armed),
        trace_armed_count=len(armed),
    )
    enriched_route_hits = enrich_route_hits(
        route_hits,
        image_start=image_start,
        image_end=image_end,
        base=base,
        trace_pid_matches_requested=trace_pid_matches_requested,
        trace_log_has_armed=bool(armed),
        trace_armed_count=len(armed),
    )
    route_slot_recovery = summarize_route_slot_recovery(enriched_route_hits)
    candidates = family_candidates(enriched_hits)
    prioritized_candidates = prioritized_family_candidates(candidates)
    concrete_candidates = concrete_review_candidates(candidates)
    best_candidate = concrete_candidates[0] if concrete_candidates else {}
    trace_plan_provenance = load_trace_plan(trace_plan) if trace_plan else {}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceLog": str(path),
        "sourceLogSha256": file_sha256(path),
        **trace_plan_provenance,
        "sourceLogExists": source_exists,
        "pid": trace_pid,
        "armedPid": armed_pid,
        "tracePidMatchesRequested": trace_pid_matches_requested,
        "imageRangeSource": image_range_source,
        "imageBase": hex_or_empty(base),
        "imageStart": hex_or_empty(image_start),
        "imageEnd": hex_or_empty(image_end),
        "imagePath": pid_range["path"] if pid_range else "",
        "imagePerms": pid_range["perms"] if pid_range else "",
        "armedCount": len(armed),
        "hitCount": len(hits),
        "methodHitCount": len(method_hits),
        "routeHitCount": len(route_hits),
        "promotableHitCount": sum(1 for hit in enriched_hits if hit["promotable"]),
        "completePackageRoute": False,
        "routeSlotRecovery": route_slot_recovery,
        "nextStep": (
            "review captured caller frame and SysV argument order"
            if hits
            else "review route probe caller chain and keep tracing for UE4SS_PACKAGE_TRACE_HIT rows"
            if route_hits
            else "review method probe caller route and keep tracing for UE4SS_PACKAGE_TRACE_HIT rows"
            if method_hits
            else "arm package runtime trace and capture UE4SS_PACKAGE_TRACE_HIT rows"
        ),
        "armed": armed,
        "familyCandidates": candidates,
        "reviewPriority": prioritized_candidates,
        "concreteReviewPriority": concrete_candidates,
        "recommendedReview": best_candidate,
        "hits": enriched_hits,
        "methodHits": enriched_method_hits,
        "routeHits": enriched_route_hits,
    }


def markdown(summary):
    lines = ["# UE4SS Package Runtime Trace Evidence", ""]
    lines.append(f"- Source log: `{summary['sourceLog']}`")
    if summary.get("sourceLogSha256"):
        lines.append(f"- Source log SHA-256: `{summary.get('sourceLogSha256', '')}`")
    if summary.get("sourceTracePlan"):
        lines.append(f"- Source trace plan: `{summary.get('sourceTracePlan', '')}`")
    if summary.get("sourcePromotionAcceptanceSchemaVersion"):
        lines.append(
            "- Source promotion acceptance schema: "
            f"`{summary.get('sourcePromotionAcceptanceSchemaVersion', '')}`"
        )
    lines.append(f"- Source log exists: `{str(summary['sourceLogExists']).lower()}`")
    lines.append(f"- Trace PID matches requested: `{str(summary.get('tracePidMatchesRequested')).lower()}`")
    lines.append(f"- Image range source: `{summary['imageRangeSource']}`")
    if summary.get("imageStart") and summary.get("imageEnd"):
        lines.append(f"- Image range: `{summary['imageStart']}-{summary['imageEnd']}` base=`{summary['imageBase']}`")
    lines.append(f"- Armed records: `{summary['armedCount']}`")
    lines.append(f"- Hits: `{summary['hitCount']}`")
    lines.append(f"- Method hits: `{summary.get('methodHitCount', 0)}`")
    lines.append(f"- Route hits: `{summary.get('routeHitCount', 0)}`")
    lines.append(f"- Promotable hits: `{summary['promotableHitCount']}`")
    lines.append(f"- Complete package route: `{str(summary['completePackageRoute']).lower()}`")
    route_slot_recovery = summary.get("routeSlotRecovery") or {}
    if route_slot_recovery:
        lines.append(f"- Route slot recovery ready: `{str(route_slot_recovery.get('ready', False)).lower()}`")
        lines.append(f"- Route slot recovery matches: `{route_slot_recovery.get('matchCount', 0)}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    lines.append("")
    if route_slot_recovery and route_slot_recovery.get("blockers"):
        lines.append("## Route Slot Recovery")
        lines.append("")
        lines.append(f"- Required slots: `{', '.join(route_slot_recovery.get('requiredSlots', []))}`")
        lines.append(f"- Present slots: `{', '.join(route_slot_recovery.get('presentSlots', [])) or 'none'}`")
        for blocker in route_slot_recovery.get("blockers", []):
            lines.append(f"- Blocker: {blocker}")
        lines.append("")
    if summary["hits"]:
        if summary.get("familyCandidates"):
            lines.append("## Family Candidates")
            lines.append("")
            if summary.get("recommendedReview"):
                recommended = summary["recommendedReview"]
                lines.append(
                    f"- Recommended review: `{recommended.get('seed', '')}` "
                    f"hitIndex=`{recommended.get('hitIndex', '')}` "
                    f"score=`{recommended.get('reviewScore', '')}`"
                )
            else:
                lines.append("- Recommended review: `none` (missing concrete call-frame or required memory evidence)")
            for family, candidate in sorted(summary["familyCandidates"].items()):
                lines.append(
                    f"- `{family}` hitIndex=`{candidate['hitIndex']}` "
                    f"score=`{candidate.get('reviewScore', '')}` "
                    f"callerImageOffset=`{candidate['callerImageOffset']}` "
                    f"ripImageOffset=`{candidate.get('ripImageOffset', '')}` "
                    f"targetImageRip=`{candidate.get('targetImageRip')}` "
                    f"targetImageCaller=`{candidate['targetImageCaller']}` "
                    f"disasmLines=`{candidate['disassemblyLines']}` "
                    f"stackLines=`{candidate['stackLines']}` "
                    f"registerMemory=`{','.join(candidate['registerMemoryRegisters'])}`"
                )
                if candidate.get("missingCallFrameOffsets"):
                    lines.append(
                        "  - missing call-frame offsets: "
                        + ",".join(candidate["missingCallFrameOffsets"])
                    )
                if candidate.get("missingRequiredMemoryRegisters"):
                    lines.append(
                        "  - missing required memory: "
                        + ",".join(candidate["missingRequiredMemoryRegisters"])
                    )
            lines.append("")
        lines.append("## Hits")
        lines.append("")
        for hit in summary["hits"]:
            caller = hit.get("caller", {})
            lines.append(
                f"- `{hit['seed']}` seed=`{hit['seedAddress']}` rip=`{hit['rip']}` "
                f"ripImageOffset=`{hit['ripImageOffset']}` caller=`{caller.get('ip', '')}` "
                f"callerImageOffset=`{hit['callerImageOffset']}` targetImageRip=`{hit['targetImageRip']}` "
                f"targetImageCaller=`{hit['targetImageCaller']}` "
                f"disasmLines=`{len(list_field(hit.get('disassembly', [])))}` "
                f"stackLines=`{len(list_field(hit.get('stack', [])))}`"
            )
            register_memory = register_memory_field(hit.get("registerMemory", {}) or {})
            if register_memory:
                captured = ", ".join(
                    f"{register}:{len(rows)}"
                    for register, rows in sorted(register_memory.items())
                    if rows
                )
                lines.append(f"  - registerMemory: {captured}")
            for blocker in hit["blockers"]:
                lines.append(f"  - blocker: {blocker}")
    if summary.get("methodHits"):
        lines.append("")
        lines.append("## Method Hits")
        lines.append("")
        for hit in summary["methodHits"]:
            caller = hit.get("caller", {})
            lines.append(
                f"- `{hit.get('owner', '')}` slot=`{hit.get('slotIndex', '')}` "
                f"addr=`{hit.get('address', '')}` rip=`{hit.get('rip', '')}` "
                f"ripImageOffset=`{hit.get('ripImageOffset', '')}` caller=`{caller.get('ip', '')}` "
                f"callerImageOffset=`{hit.get('callerImageOffset', '')}` "
                f"targetImageRip=`{hit.get('targetImageRip')}` "
                f"targetImageCaller=`{hit.get('targetImageCaller')}` "
                f"disasmLines=`{len(list_field(hit.get('disassembly', [])))}` "
                f"stackLines=`{len(list_field(hit.get('stack', [])))}`"
            )
            for blocker in hit["blockers"]:
                lines.append(f"  - blocker: {blocker}")
    if summary.get("routeHits"):
        lines.append("")
        lines.append("## Route Hits")
        lines.append("")
        for hit in summary["routeHits"]:
            caller = hit.get("caller", {})
            lines.append(
                f"- addr=`{hit.get('address', '')}` rip=`{hit.get('rip', '')}` "
                f"ripImageOffset=`{hit.get('ripImageOffset', '')}` caller=`{caller.get('ip', '')}` "
                f"callerImageOffset=`{hit.get('callerImageOffset', '')}` "
                f"targetImageRip=`{hit.get('targetImageRip')}` "
                f"targetImageCaller=`{hit.get('targetImageCaller')}` "
                f"disasmLines=`{len(list_field(hit.get('disassembly', [])))}` "
                f"stackLines=`{len(list_field(hit.get('stack', [])))}`"
            )
            static_matches = list_field(hit.get("routeVtableStaticSlotMatches", []))
            if static_matches:
                rendered_matches = ", ".join(
                    f"{match.get('register', '')}:{match.get('slotOffset', '')}->{match.get('targetImageOffset') or match.get('target', '')}"
                    for match in static_matches
                )
                lines.append(f"  - routeVtableStaticSlotMatches: {rendered_matches}")
            for blocker in hit["blockers"]:
                lines.append(f"  - blocker: {blocker}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize UE4SS package runtime trace hit evidence.")
    parser.add_argument("log")
    parser.add_argument("--image-start", default="")
    parser.add_argument("--image-end", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--trace-plan-json", default="")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = build_summary(
        args.log,
        image_start=parse_int(args.image_start),
        image_end=parse_int(args.image_end),
        base=parse_int(args.base),
        pid=args.pid,
        trace_plan=args.trace_plan_json,
    )
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
