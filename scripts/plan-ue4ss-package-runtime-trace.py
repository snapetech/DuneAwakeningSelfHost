#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-plan/v1"
EXTERNAL_PLAN_SCHEMA_VERSION = "dune-ue4ss-package-external-symbol-plan/v1"
PROMOTION_ACCEPTANCE_SCHEMA_VERSION = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
DEFAULT_EXTERNAL_PLAN = "build/server-ue4ss-package-external-symbol-plan.json"
DEFAULT_METHOD_CANDIDATES = "build/server-ue-package-loader-vtables.json"
ANCHOR_PRIORITY = {
    "LoadPackage": 0,
    "StaticLoadObject": 1,
    "StaticLoadClass": 2,
    "LoadObject": 3,
    "ResolveName": 4,
}
ARGUMENT_REGISTERS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
ROUTE_OBJECT_REGISTERS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "rbx", "r12", "r13", "r14", "r15")
ROUTE_STACK_OBJECT_SLOTS = (0, 8, 16, 24, 32, 40)
HEX_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]+$")
BUILD_ID_RE = re.compile(r"^[0-9a-fA-F]+$")
METHOD_OWNER_PRIORITY = {
    "FLinkerLoad": 0,
    "FBootLoadClassData": 10,
    "FBootLoadObjectData": 11,
}
DEFAULT_MAX_HARDWARE_READ_WATCHPOINTS = 4


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def load_external_plan(path):
    plan = load_json(path)
    if not isinstance(plan, dict):
        raise ValueError(f"{path} is not a JSON object")
    schema = plan.get("schemaVersion")
    if schema != EXTERNAL_PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schemaVersion {schema!r}; expected {EXTERNAL_PLAN_SCHEMA_VERSION!r}"
        )
    validate_external_plan(plan, path)
    return plan


def validate_external_plan(plan, path="<external-plan>"):
    acceptance = plan.get("promotionAcceptance")
    if not isinstance(acceptance, dict):
        raise ValueError(f"{path} promotionAcceptance must be a JSON object")
    acceptance_schema = acceptance.get("schemaVersion")
    if acceptance_schema != PROMOTION_ACCEPTANCE_SCHEMA_VERSION:
        raise ValueError(
            f"{path} promotionAcceptance.schemaVersion {acceptance_schema!r}; "
            f"expected {PROMOTION_ACCEPTANCE_SCHEMA_VERSION!r}"
        )
    binary = plan.get("binary", {})
    if binary is None:
        binary = {}
    if not isinstance(binary, dict):
        raise ValueError(f"{path} binary must be a JSON object")
    build_id = binary.get("buildId", "")
    if build_id not in ("", "unknown"):
        if not isinstance(build_id, str) or not BUILD_ID_RE.fullmatch(build_id):
            raise ValueError(f"{path} binary.buildId must be hex, empty, or unknown")
    seeds = plan.get("historicalStringSeeds", [])
    if seeds is None:
        seeds = []
    if not isinstance(seeds, list):
        raise ValueError(f"{path} historicalStringSeeds must be a JSON array")
    seen_trace_seeds = {}
    for index, seed in enumerate(seeds):
        if not isinstance(seed, dict):
            raise ValueError(f"{path} historicalStringSeeds[{index}] must be a JSON object")
        if seed.get("promotion") != "non-promotable-string-only":
            continue
        name = seed.get("name", "")
        if name not in ANCHOR_PRIORITY:
            raise ValueError(f"{path} historicalStringSeeds[{index}] has unsupported package seed name: {name}")
        address = seed.get("address", "")
        if not isinstance(address, str) or not HEX_ADDRESS_RE.fullmatch(address):
            raise ValueError(f"{path} historicalStringSeeds[{index}] has invalid hex address")
        if int(address, 16) <= 0:
            raise ValueError(f"{path} historicalStringSeeds[{index}] has non-positive trace address")
        trace_key = (name, f"0x{int(address, 16):x}")
        if trace_key in seen_trace_seeds:
            first_index = seen_trace_seeds[trace_key]
            raise ValueError(
                f"{path} historicalStringSeeds[{index}] duplicates package trace seed "
                f"{name}@{trace_key[1]} from historicalStringSeeds[{first_index}]"
            )
        seen_trace_seeds[trace_key] = index


def parse_int(value):
    if value is None or value == "":
        return None
    return int(str(value), 0)


def validate_trace_seed_limit(limit):
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("package runtime trace seed limit must be a positive integer")
    return limit


def validate_single_line_path(value, label):
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{label} must be a scalar path")
    text = str(value)
    if not text.strip() or any(char in text for char in "\r\n\0"):
        raise ValueError(f"{label} must be a non-empty single-line path")
    return text


def normalize_anchors(anchors):
    normalized = []
    seen = set()
    for raw_anchor in anchors or []:
        for raw_name in str(raw_anchor).split(","):
            name = raw_name.strip()
            if not name:
                raise ValueError("package runtime trace anchor must be a non-empty string")
            if name not in ANCHOR_PRIORITY:
                raise ValueError(f"unsupported package runtime trace anchor: {name}")
            if name not in seen:
                normalized.append(name)
                seen.add(name)
    return normalized


def build_id_for_pid(pid):
    proc = run_capture(["readelf", "-n", f"/proc/{pid}/exe"])
    if proc.returncode != 0:
        proc = run_capture(["sudo", "-n", "readelf", "-n", f"/proc/{pid}/exe"])
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("Build ID:"):
            return line.split(":", 1)[1].strip()
    return ""


def shared_library_path(path):
    return (
        "/lib/" in path
        or "/lib64/" in path
        or "/usr/lib/" in path
        or path.endswith(".so")
        or ".so." in path
    )


def pie_base_for_pid(pid):
    exe_path = Path(f"/proc/{pid}/exe")
    try:
        exe = str(exe_path.resolve())
    except OSError:
        exe_proc = run_capture(["sudo", "-n", "readlink", "-f", f"/proc/{pid}/exe"])
        exe = exe_proc.stdout.strip() if exe_proc.returncode == 0 else ""
    try:
        lines = Path(f"/proc/{pid}/maps").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        maps_proc = run_capture(["sudo", "-n", "cat", f"/proc/{pid}/maps"])
        if maps_proc.returncode != 0:
            return None
        lines = maps_proc.stdout.splitlines()
    return pie_base_from_maps(lines, exe)


def run_capture(argv):
    try:
        return subprocess.run(
            argv,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return subprocess.CompletedProcess(argv, 127, "", "")


def pie_base_from_maps(lines, exe=""):
    first_mapping = None
    first_named_mapping = None
    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        address, perms, offset, _, _, path = parts[:6]
        start = int(address.split("-", 1)[0], 16)
        file_offset = int(offset, 16)
        row = (file_offset, start, path)
        if exe and path == exe and (first_mapping is None or row < first_mapping):
            first_mapping = row
        if path.startswith("/"):
            generic_row = (1 if shared_library_path(path) else 0, file_offset, start, path)
            if first_named_mapping is None or generic_row < first_named_mapping:
                first_named_mapping = generic_row
    if first_mapping:
        file_offset, start, _ = first_mapping
        return start - file_offset
    if first_named_mapping:
        _, file_offset, start, _ = first_named_mapping
        return start - file_offset
    return None


def normalize_seed_addresses(addresses):
    normalized = []
    seen = set()
    for raw_address in addresses or []:
        for raw_item in str(raw_address).split(","):
            item = raw_item.strip()
            if not item:
                raise ValueError("package runtime trace seed address must be a non-empty string")
            if not HEX_ADDRESS_RE.fullmatch(item):
                raise ValueError(f"unsupported package runtime trace seed address: {item}")
            canonical = f"0x{int(item, 16):x}"
            if canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)
    return normalized


def normalize_method_addresses(addresses):
    normalized = []
    seen = set()
    for raw_address in addresses or []:
        for raw_item in str(raw_address).split(","):
            item = raw_item.strip()
            if not item:
                raise ValueError("package method trace address must be a non-empty string")
            if not HEX_ADDRESS_RE.fullmatch(item):
                raise ValueError(f"unsupported package method trace address: {item}")
            canonical = f"0x{int(item, 16):x}"
            if canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)
    return normalized


def normalize_route_addresses(addresses):
    return normalize_method_addresses(addresses)


def select_seeds(plan, anchors, limit, seed_addresses=None):
    validate_external_plan(plan)
    seed_address_set = set(seed_addresses or [])
    seeds = [
        seed
        for seed in plan.get("historicalStringSeeds", []) or []
        if seed.get("promotion") == "non-promotable-string-only"
        and (not anchors or seed.get("name") in anchors)
        and (not seed_address_set or f"0x{int(seed.get('address', '0'), 16):x}" in seed_address_set)
    ]
    seeds.sort(key=lambda seed: (ANCHOR_PRIORITY.get(seed.get("name", ""), 99), int(seed["address"], 16)))
    return seeds[:limit]


def eligible_seeds(plan):
    validate_external_plan(plan)
    return [
        seed
        for seed in plan.get("historicalStringSeeds", []) or []
        if seed.get("promotion") == "non-promotable-string-only"
    ]


def count_by_family(seeds):
    counts = {}
    for seed in seeds:
        family = seed.get("name", "")
        counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (ANCHOR_PRIORITY.get(item[0], 99), item[0])))


def candidate_address(row):
    value = row.get("value") or row.get("target") or row.get("address")
    if not isinstance(value, str) or not HEX_ADDRESS_RE.fullmatch(value):
        return None
    return f"0x{int(value, 16):x}"


def method_owner_priority(owner):
    for needle, priority in METHOD_OWNER_PRIORITY.items():
        if needle in owner:
            return priority
    return 80


def method_shape_score(shape):
    score = 0
    if shape.get("hasIndirectCall"):
        score -= 4
    if shape.get("hasCall"):
        score -= 3
    if shape.get("startsWithFrame"):
        score -= 1
    if shape.get("callsDelete"):
        score += 4
    if shape.get("returnsConstantZero"):
        score += 6
    if shape.get("hasUd2"):
        score += 8
    return score


def select_method_candidates(candidate_artifact, limit=0, method_addresses=None):
    if not candidate_artifact or limit <= 0:
        return []
    method_address_set = set(method_addresses or [])
    rows = []
    for table_index, table in enumerate(candidate_artifact.get("rows", []) or []):
        owner = table.get("demangled", "")
        owner_priority = method_owner_priority(owner)
        for slot in table.get("executableSlots", []) or []:
            if slot.get("candidateKind") != "method":
                continue
            address = candidate_address(slot)
            if not address:
                continue
            if method_address_set and address not in method_address_set:
                continue
            shape = slot.get("shape", {}) or {}
            if not shape.get("hasCall") and not shape.get("hasIndirectCall"):
                continue
            rows.append(
                {
                    "name": "PackageMethodProbe",
                    "owner": owner,
                    "slotIndex": slot.get("index"),
                    "address": address,
                    "candidateKind": slot.get("candidateKind"),
                    "promotion": "non-promotable-method-probe",
                    "traceMode": "gdb-breakpoint",
                    "use": "capture target-image method call frames only; do not promote without a reviewed StaticLoadObject/LoadPackage-equivalent ABI",
                    "rank": {
                        "ownerPriority": owner_priority,
                        "shapeScore": method_shape_score(shape),
                        "address": address,
                        "tableIndex": table_index,
                    },
                    "shape": shape,
                }
            )
    rows.sort(
        key=lambda row: (
            row["rank"]["ownerPriority"],
            row["rank"]["shapeScore"],
            int(row["address"], 16),
            str(row.get("slotIndex", "")),
        )
    )
    deduped = []
    seen = set()
    for row in rows:
        key = row["address"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def selection_summary(plan, anchors, selected, seed_addresses=None):
    eligible = eligible_seeds(plan)
    requested = list(anchors or [])
    available_counts = count_by_family(eligible)
    selected_counts = count_by_family(selected)
    missing_requested = [anchor for anchor in requested if available_counts.get(anchor, 0) == 0]
    skipped_by_family = {
        family: max(0, count - selected_counts.get(family, 0))
        for family, count in available_counts.items()
        if count - selected_counts.get(family, 0) > 0
    }
    return {
        "eligibleSeedCount": len(eligible),
        "availableByFamily": available_counts,
        "selectedByFamily": selected_counts,
        "requestedAnchors": requested,
        "requestedSeedAddresses": list(seed_addresses or []),
        "missingRequestedAnchors": missing_requested,
        "skippedByFamily": skipped_by_family,
    }


def trace_plan_blockers(selection, selected):
    blockers = []
    if not selected:
        blockers.append("no package runtime trace seeds selected")
    if selection.get("requestedAnchors") and selection.get("missingRequestedAnchors"):
        missing = ", ".join(selection.get("missingRequestedAnchors", []))
        blockers.append(f"requested package trace anchors are missing: {missing}")
    if selection.get("requestedSeedAddresses") and not selected:
        missing = ", ".join(selection.get("requestedSeedAddresses", []))
        blockers.append(f"requested package trace seed addresses are missing: {missing}")
    return blockers


def recommended_trace_env(selection, selected):
    selected_counts = selection.get("selectedByFamily", {})
    families = [family for family in ANCHOR_PRIORITY if selected_counts.get(family, 0) > 0]
    if not families:
        return {}
    signature_family = "LoadPackage" if selected_counts.get("LoadPackage", 0) > 0 else families[0]
    return {
        "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": ",".join(families),
        "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": str(max(1, min(len(selected), DEFAULT_MAX_HARDWARE_READ_WATCHPOINTS))),
        "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": signature_family,
        "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
        "selectedByFamily": selected_counts,
    }


def gdb_commands(seeds, base, build_id, pid=None):
    lines = [
        "set pagination off",
        "set confirm off",
        "set print pretty off",
        "set breakpoint pending off",
        "handle SIGPIPE nostop noprint pass",
        "handle SIGUSR1 nostop noprint pass",
        (
            'printf "UE4SS_PACKAGE_TRACE armed pid=%d base=0x%lx build_id=%s seeds=%d\\n", '
            + str(pid or 0)
            + f", {base:#x}, \"{build_id}\", {len(seeds)}"
        ),
    ]
    for seed in seeds:
        image_offset = int(seed["address"], 16)
        absolute = base + image_offset
        name = seed["name"]
        register_memory_commands = []
        for register in ARGUMENT_REGISTERS:
            register_memory_commands.extend(
                [
                    f' printf "UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg={register}\\n"',
                    f" if ${register} > 0x10000",
                    f"  x/8gx ${register}",
                    f"  x/32bx ${register}",
                    f"  x/s ${register}",
                    " else",
                    f'  printf "UE4SS_PACKAGE_TRACE_REGMEM_SKIP reg={register} value=%p reason=low-or-null\\n", ${register}',
                    " end",
                    f' printf "UE4SS_PACKAGE_TRACE_REGMEM_END reg={register}\\n"',
                ]
            )
        lines.extend(
            [
                f"rwatch *(char*){absolute:#x}",
                "commands",
                " silent",
                (
                    f' printf "UE4SS_PACKAGE_TRACE_HIT seed={name} imageOffset={image_offset:#x} '
                    f'addr={absolute:#x} rip=%p rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p '
                    'rbx=%p r12=%p r13=%p r14=%p r15=%p rsp=%p rbp=%p\\n", '
                    "$rip, $rdi, $rsi, $rdx, $rcx, $r8, $r9, $rbx, $r12, $r13, $r14, $r15, $rsp, $rbp"
                ),
                f" x/s {absolute:#x}",
                ' printf "UE4SS_PACKAGE_TRACE_DISASM_BEGIN\\n"',
                " x/12i $rip-24",
                ' printf "UE4SS_PACKAGE_TRACE_DISASM_END\\n"',
                *register_memory_commands,
                ' printf "UE4SS_PACKAGE_TRACE_STACK_BEGIN\\n"',
                " x/8gx $rsp",
                ' printf "UE4SS_PACKAGE_TRACE_STACK_END\\n"',
                " bt 8",
                " continue",
                "end",
            ]
        )
    lines.append("continue")
    return "\n".join(lines) + "\n"


def gdb_method_commands(methods, base, build_id, pid=None):
    lines = [
        "set pagination off",
        "set confirm off",
        "set print pretty off",
        "set breakpoint pending off",
        "handle SIGPIPE nostop noprint pass",
        "handle SIGUSR1 nostop noprint pass",
        (
            'printf "UE4SS_PACKAGE_METHOD_TRACE armed pid=%d base=0x%lx build_id=%s methods=%d\\n", '
            + str(pid or 0)
            + f", {base:#x}, \"{build_id}\", {len(methods)}"
        ),
    ]
    for method in methods:
        image_offset = int(method["address"], 16)
        absolute = base + image_offset
        owner = str(method.get("owner", "")).replace("\\", "\\\\").replace('"', '\\"')
        slot = method.get("slotIndex", "")
        lines.extend(
            [
                f"break *{absolute:#x}",
                "commands",
                " silent",
                (
                    f' printf "UE4SS_PACKAGE_METHOD_TRACE_HIT imageOffset={image_offset:#x} '
                    f'addr={absolute:#x} slot={slot} owner=\\"{owner}\\" '
                    'rip=%p rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p rsp=%p rbp=%p\\n", '
                    "$rip, $rdi, $rsi, $rdx, $rcx, $r8, $r9, $rsp, $rbp"
                ),
                ' printf "UE4SS_PACKAGE_METHOD_TRACE_DISASM_BEGIN\\n"',
                " x/16i $rip",
                ' printf "UE4SS_PACKAGE_METHOD_TRACE_DISASM_END\\n"',
                ' printf "UE4SS_PACKAGE_METHOD_TRACE_STACK_BEGIN\\n"',
                " x/12gx $rsp",
                ' printf "UE4SS_PACKAGE_METHOD_TRACE_STACK_END\\n"',
                " bt 12",
                " continue",
                "end",
            ]
        )
    lines.append("continue")
    return "\n".join(lines) + "\n"


def gdb_route_commands(routes, base, build_id, pid=None):
    lines = [
        "set pagination off",
        "set confirm off",
        "set print pretty off",
        "set breakpoint pending off",
        "handle SIGPIPE nostop noprint pass",
        "handle SIGUSR1 nostop noprint pass",
        (
            'printf "UE4SS_PACKAGE_ROUTE_TRACE armed pid=%d base=0x%lx build_id=%s routes=%d\\n", '
            + str(pid or 0)
            + f", {base:#x}, \"{build_id}\", {len(routes)}"
        ),
    ]
    for route in routes:
        image_offset = int(route["address"], 16)
        absolute = base + image_offset
        route_memory_commands = []
        for register in ROUTE_OBJECT_REGISTERS:
            route_memory_commands.extend(
                [
                    f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={register}\\n"',
                    f" if ${register} > 0x10000",
                    f"  x/24gx ${register}",
                    f"  if *(void**){'$'}{register} > 0x10000",
                    f"   printf \"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={register}\\n\"",
                    f"   x/160gx *(void**){'$'}{register}",
                    f"   printf \"UE4SS_PACKAGE_ROUTE_VTABLE_END reg={register}\\n\"",
                    "  end",
                    " else",
                    f'  printf "UE4SS_PACKAGE_ROUTE_OBJECT_SKIP reg={register} value=%p reason=low-or-null\\n", ${register}',
                    " end",
                    f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_END reg={register}\\n"',
                ]
            )
        for stack_offset in ROUTE_STACK_OBJECT_SLOTS:
            label = f"rsp{stack_offset:x}"
            convenience = f"$ue4ss_route_{label}"
            route_memory_commands.extend(
                [
                    f" set {convenience} = *(void**)($rsp+{stack_offset})",
                    f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={label}\\n"',
                    f" if {convenience} > 0x10000",
                    f"  x/24gx {convenience}",
                    f"  if *(void**){convenience} > 0x10000",
                    f"   printf \"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={label}\\n\"",
                    f"   x/160gx *(void**){convenience}",
                    f"   printf \"UE4SS_PACKAGE_ROUTE_VTABLE_END reg={label}\\n\"",
                    "  end",
                    " else",
                    f'  printf "UE4SS_PACKAGE_ROUTE_OBJECT_SKIP reg={label} value=%p reason=low-or-null\\n", {convenience}',
                    " end",
                    f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_END reg={label}\\n"',
                ]
            )
        lines.extend(
            [
                f"break *{absolute:#x}",
                "commands",
                " silent",
                (
                    f' printf "UE4SS_PACKAGE_ROUTE_TRACE_HIT imageOffset={image_offset:#x} '
                    f'addr={absolute:#x} rip=%p rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p '
                    'rbx=%p r12=%p r13=%p r14=%p r15=%p rsp=%p rbp=%p\\n", '
                    "$rip, $rdi, $rsi, $rdx, $rcx, $r8, $r9, $rbx, $r12, $r13, $r14, $r15, $rsp, $rbp"
                ),
                ' printf "UE4SS_PACKAGE_ROUTE_TRACE_DISASM_BEGIN\\n"',
                " x/20i $rip-32",
                ' printf "UE4SS_PACKAGE_ROUTE_TRACE_DISASM_END\\n"',
                *route_memory_commands,
                ' printf "UE4SS_PACKAGE_ROUTE_TRACE_STACK_BEGIN\\n"',
                " x/12gx $rsp",
                ' printf "UE4SS_PACKAGE_ROUTE_TRACE_STACK_END\\n"',
                " bt 12",
                " continue",
                "end",
            ]
        )
    lines.append("continue")
    return "\n".join(lines) + "\n"


def strip_final_continue(text):
    lines = text.rstrip().splitlines()
    if lines and lines[-1].strip() == "continue":
        lines = lines[:-1]
    return "\n".join(lines).rstrip()


def combined_gdb_commands(seed_gdb, method_gdb="", route_gdb=""):
    parts = [strip_final_continue(seed_gdb)]
    if method_gdb:
        parts.append(strip_final_continue(method_gdb))
    if route_gdb:
        parts.append(strip_final_continue(route_gdb))
    return "\n".join(part for part in parts if part) + "\ncontinue\n"


def build_plan(
    external_plan,
    base=None,
    pid=None,
    anchors=None,
    seed_addresses=None,
    limit=1,
    source_external_plan=DEFAULT_EXTERNAL_PLAN,
    method_candidates=None,
    method_limit=0,
    method_addresses=None,
    route_addresses=None,
):
    limit = validate_trace_seed_limit(limit)
    anchors = normalize_anchors(anchors)
    seed_addresses = normalize_seed_addresses(seed_addresses)
    source_external_plan = validate_single_line_path(source_external_plan, "source external plan")
    method_addresses = normalize_method_addresses(method_addresses)
    route_addresses = normalize_route_addresses(route_addresses)
    binary = external_plan.get("binary", {}) or {}
    expected_build_id = binary.get("buildId", "")
    runtime_build_id = build_id_for_pid(pid) if pid else ""
    if pid and expected_build_id and runtime_build_id and runtime_build_id != expected_build_id:
        raise ValueError(f"pid build id {runtime_build_id} does not match plan build id {expected_build_id}")
    resolved_base = base if base is not None else (pie_base_for_pid(pid) if pid else None)
    if resolved_base is None:
        raise ValueError("provide --base or --pid so runtime image addresses can be computed")
    seeds = select_seeds(external_plan, set(anchors), limit, seed_addresses=seed_addresses)
    seed_summary = selection_summary(external_plan, anchors, seeds, seed_addresses=seed_addresses)
    recommended_env = recommended_trace_env(seed_summary, seeds)
    blockers = trace_plan_blockers(seed_summary, seeds)
    methods = select_method_candidates(method_candidates or {}, method_limit, method_addresses=method_addresses)
    method_gdb = gdb_method_commands(methods, resolved_base, expected_build_id or runtime_build_id or "unknown", pid) if methods else ""
    routes = [
        {
            "name": "PackageRouteProbe",
            "address": address,
            "absoluteAddress": f"0x{resolved_base + int(address, 16):x}",
            "promotion": "non-promotable-route-probe",
            "traceMode": "gdb-breakpoint",
            "use": "capture package-adjacent caller route frames only; do not promote without a package trace hit",
        }
        for address in route_addresses
    ]
    route_gdb = gdb_route_commands(routes, resolved_base, expected_build_id or runtime_build_id or "unknown", pid) if routes else ""
    seed_gdb = gdb_commands(seeds, resolved_base, expected_build_id or runtime_build_id or "unknown", pid)
    combined_gdb = combined_gdb_commands(seed_gdb, method_gdb, route_gdb)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceExternalPlan": str(source_external_plan),
        "sourcePromotionAcceptanceSchemaVersion": external_plan["promotionAcceptance"]["schemaVersion"],
        "pid": pid,
        "base": f"0x{resolved_base:x}",
        "expectedBuildId": expected_build_id,
        "runtimeBuildId": runtime_build_id,
        "seedCount": len(seeds),
        "hardwareReadWatchpointLimit": DEFAULT_MAX_HARDWARE_READ_WATCHPOINTS,
        "seedSelection": seed_summary,
        "blockers": blockers,
        "recommendedTraceEnv": recommended_env,
        "seeds": [
            {
                **seed,
                "absoluteAddress": f"0x{resolved_base + int(seed['address'], 16):x}",
                "traceMode": "gdb-read-watchpoint",
            }
            for seed in seeds
        ],
        "methodProbeCount": len(methods),
        "requestedMethodAddresses": method_addresses,
        "methodProbes": [
            {
                **method,
                "absoluteAddress": f"0x{resolved_base + int(method['address'], 16):x}",
            }
            for method in methods
        ],
        "routeProbeCount": len(routes),
        "requestedRouteAddresses": route_addresses,
        "routeProbes": routes,
        "acceptance": [
            "watchpoint hit captures a caller/backtrace in target image code",
            "method breakpoint hit captures target-image package-adjacent owner, slot, registers, disassembly, and backtrace",
            "captured caller is reviewed to recover a package-loading function boundary or call-frame",
            "method probes remain non-promotable until a StaticLoadObject/LoadPackage-equivalent ABI is proven",
            "route probes remain non-promotable until a package trace hit proves package ABI provenance",
            "candidate is promoted only after guarded native LoadAsset or LoadClass invocation succeeds",
        ],
        "gdb": combined_gdb,
        "seedGdb": seed_gdb,
        "methodGdb": method_gdb,
        "routeGdb": route_gdb,
    }


def markdown(plan):
    lines = ["# UE4SS Package Runtime Trace Plan", ""]
    lines.append(f"- PID: `{plan['pid'] or ''}`")
    lines.append(f"- Base: `{plan['base']}`")
    lines.append(f"- Expected Build ID: `{plan['expectedBuildId']}`")
    lines.append(
        f"- Source promotion acceptance schema: `{plan.get('sourcePromotionAcceptanceSchemaVersion', '')}`"
    )
    if plan.get("runtimeBuildId"):
        lines.append(f"- Runtime Build ID: `{plan['runtimeBuildId']}`")
    lines.append(f"- Seeds: `{plan['seedCount']}`")
    lines.append(f"- Method probes: `{plan.get('methodProbeCount', 0)}`")
    lines.append(f"- Route probes: `{plan.get('routeProbeCount', 0)}`")
    selection = plan.get("seedSelection", {})
    if selection:
        lines.append(f"- Eligible seeds: `{selection.get('eligibleSeedCount', 0)}`")
        lines.append(f"- Available by family: `{selection.get('availableByFamily', {})}`")
        lines.append(f"- Selected by family: `{selection.get('selectedByFamily', {})}`")
        if selection.get("requestedAnchors"):
            lines.append(f"- Requested anchors: `{','.join(selection.get('requestedAnchors', []))}`")
        if selection.get("missingRequestedAnchors"):
            lines.append(f"- Missing requested anchors: `{','.join(selection.get('missingRequestedAnchors', []))}`")
        if selection.get("requestedSeedAddresses"):
            lines.append(f"- Requested seed addresses: `{','.join(selection.get('requestedSeedAddresses', []))}`")
        if selection.get("skippedByFamily"):
            lines.append(f"- Skipped by family: `{selection.get('skippedByFamily', {})}`")
    if plan.get("blockers"):
        lines.append("- Blockers:")
        for blocker in plan.get("blockers", []):
            lines.append(f"  - {blocker}")
    if plan.get("requestedMethodAddresses"):
        lines.append(f"- Requested method addresses: `{','.join(plan.get('requestedMethodAddresses', []))}`")
    if plan.get("requestedRouteAddresses"):
        lines.append(f"- Requested route addresses: `{','.join(plan.get('requestedRouteAddresses', []))}`")
    if plan.get("recommendedTraceEnv"):
        env = plan["recommendedTraceEnv"]
        lines.append(
            "- Recommended wrapper env: "
            f"`DUNE_UE4SS_PACKAGE_TRACE_ANCHOR={env['DUNE_UE4SS_PACKAGE_TRACE_ANCHOR']} "
            f"DUNE_UE4SS_PACKAGE_TRACE_LIMIT={env['DUNE_UE4SS_PACKAGE_TRACE_LIMIT']} "
            f"DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY={env['DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY']} "
            f"DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX={env['DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX']}`"
        )
    lines.append("- Live use: pass `--pid` so the script derives the runtime PIE base and validates Build ID")
    lines.append("")
    lines.append("## Seeds")
    lines.append("")
    for seed in plan["seeds"]:
        lines.append(
            f"- `{seed['name']}` imageOffset=`{seed['address']}` absolute=`{seed['absoluteAddress']}` mode=`{seed['traceMode']}`"
        )
    methods = plan.get("methodProbes", [])
    if methods:
        lines.append("")
        lines.append("## Method Probes")
        lines.append("")
        for method in methods:
            lines.append(
                f"- `{method['owner']}` slot=`{method.get('slotIndex')}` imageOffset=`{method['address']}` "
                f"absolute=`{method['absoluteAddress']}` mode=`{method['traceMode']}` promotion=`{method['promotion']}`"
            )
    routes = plan.get("routeProbes", [])
    if routes:
        lines.append("")
        lines.append("## Route Probes")
        lines.append("")
        for route in routes:
            lines.append(
                f"- imageOffset=`{route['address']}` absolute=`{route['absoluteAddress']}` "
                f"mode=`{route['traceMode']}` promotion=`{route['promotion']}`"
            )
    lines.append("")
    lines.append("## Acceptance")
    lines.append("")
    for item in plan["acceptance"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## GDB Commands")
    lines.append("")
    lines.append("```gdb")
    lines.append(plan["gdb"].rstrip())
    lines.append("```")
    if plan.get("methodGdb"):
        lines.append("")
        lines.append("## Method GDB Commands")
        lines.append("")
        lines.append("```gdb")
        lines.append(plan["methodGdb"].rstrip())
        lines.append("```")
    if plan.get("routeGdb"):
        lines.append("")
        lines.append("## Route GDB Commands")
        lines.append("")
        lines.append("```gdb")
        lines.append(plan["routeGdb"].rstrip())
        lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a guarded GDB trace plan for UE4SS package string seeds.")
    parser.add_argument("--external-plan", default=DEFAULT_EXTERNAL_PLAN)
    parser.add_argument("--base", default="")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument("--seed-address", action="append", default=[])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--method-candidates", default="")
    parser.add_argument("--method-limit", type=int, default=0)
    parser.add_argument("--method-address", action="append", default=[])
    parser.add_argument("--route-address", action="append", default=[])
    parser.add_argument("--gdb-out", default="")
    parser.add_argument("--method-gdb-out", default="")
    parser.add_argument("--format", choices=("json", "markdown", "gdb"), default="markdown")
    args = parser.parse_args(argv)
    plan = build_plan(
        load_external_plan(args.external_plan),
        base=parse_int(args.base),
        pid=args.pid,
        anchors=args.anchor,
        seed_addresses=args.seed_address,
        limit=args.limit,
        source_external_plan=args.external_plan,
        method_candidates=load_json(args.method_candidates) if args.method_candidates else None,
        method_limit=args.method_limit,
        method_addresses=args.method_address,
        route_addresses=args.route_address,
    )
    if args.gdb_out:
        args.gdb_out = validate_single_line_path(args.gdb_out, "--gdb-out")
        Path(args.gdb_out).write_text(plan["gdb"], encoding="utf-8")
    if args.method_gdb_out:
        args.method_gdb_out = validate_single_line_path(args.method_gdb_out, "--method-gdb-out")
        Path(args.method_gdb_out).write_text(plan["methodGdb"], encoding="utf-8")
    if args.format == "json":
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "gdb":
        sys.stdout.write(plan["gdb"])
    else:
        sys.stdout.write(markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
