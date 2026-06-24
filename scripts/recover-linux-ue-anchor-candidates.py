#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


PF_X = 1
PF_W = 2
PF_R = 4

CANONICAL_GROUPS = {
    "FNamePool": "names",
    "NamePoolData": "names",
    "GName": "names",
    "GNames": "names",
    "GUObjectArray": "objects",
    "GObjectArray": "objects",
    "GObjects": "objects",
    "FUObjectArray": "objects",
    "GWorld": "world",
    "GEngine": "world",
    "ProcessEvent": "dispatch",
    "StaticFindObject": "dispatch",
    "CallFunctionByNameWithArguments": "dispatch",
    "CallFunctionByName": "dispatch",
    "StaticLoadObject": "package",
    "StaticLoadClass": "package",
    "LoadObject": "package",
    "LoadPackage": "package",
    "ResolveName": "package",
    "UObject": "reflection",
    "UFunction": "reflection",
    "UClass": "reflection",
    "FProperty": "reflection",
    "UStruct": "reflection",
    "UEnum": "reflection",
}
ALIASES = {
    "FNamePool": ("fnamepool", "namepool", "globalnamepool"),
    "NamePoolData": ("namepooldata",),
    "GName": ("gname", "gnames", "globalnames"),
    "GNames": ("gnames", "globalnames"),
    "GUObjectArray": ("guobjectarray", "guobjects", "globaluobjectarray"),
    "GObjectArray": ("gobjectarray", "gobjects", "globalobjectarray"),
    "GObjects": ("gobjects", "globalobjects"),
    "FUObjectArray": ("fuobjectarray",),
    "GWorld": ("gworld", "uworldglobal", "globalworld"),
    "GEngine": ("gengine", "uengineglobal", "globalengine"),
    "ProcessEvent": ("processevent", "uobjectprocessevent", "processinternal"),
    "StaticFindObject": ("staticfindobject", "findobject"),
    "CallFunctionByNameWithArguments": ("callfunctionbynamewitharguments",),
    "CallFunctionByName": ("callfunctionbyname",),
    "StaticLoadObject": ("staticloadobject",),
    "LoadObject": ("loadobject",),
    "LoadPackage": ("loadpackage",),
    "ResolveName": ("resolvename",),
    "UObject": ("uobject", "uobjectbase"),
    "UFunction": ("ufunction",),
    "UClass": ("uclass",),
    "FProperty": ("fproperty", "uproperty"),
    "UStruct": ("ustruct",),
    "UEnum": ("uenum",),
}


@dataclass(frozen=True)
class Candidate:
    source_name: str
    canonical_name: str
    group: str
    source_image_offset: int
    instruction_file_offset: int
    instruction_image_offset: int
    instruction_vaddr: int
    mnemonic: str
    op_str: str
    transform: str
    pattern: str
    pattern_sha256: str
    match_count: int
    target_vaddr: int
    target_file_offset: str
    target_image_offset: str
    target_segment_flags: str
    target_kind: str
    distance: int
    score: int


def import_script(script_name, module_name):
    script = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(str(value), 16 if str(value).lower().startswith("0x") else 10)


def normalize(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def canonical_anchor_name(name):
    normalized = normalize(name)
    for canonical in CANONICAL_GROUPS:
        if normalized == normalize(canonical):
            return canonical
    for canonical, aliases in ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def load_targets(binary, loader_log, exe_substring, pid, categories, names):
    xrefs = import_script("summarize-linux-loader-xrefs.py", "summarize_linux_loader_xrefs")
    data, segments = xrefs.load_elf_segments(binary)
    targets = xrefs.targets_from_log(loader_log, segments, exe_substring, pid, categories, names)
    rows = []
    seen = set()
    for target in targets:
        canonical = canonical_anchor_name(target.name)
        if not canonical:
            continue
        key = (target.name, target.file_offset)
        if key in seen:
            continue
        seen.add(key)
        rows.append(target)
    return data, segments, rows


def segment_for_file_offset(segments, offset):
    for segment in segments:
        if segment.file_offset <= offset < segment.file_offset + segment.file_size:
            return segment
    return None


def segment_for_vaddr(segments, vaddr):
    for segment in segments:
        if segment.vaddr <= vaddr < segment.vaddr + segment.file_size:
            return segment
    return None


def vaddr_to_file_offset(segments, vaddr):
    segment = segment_for_vaddr(segments, vaddr)
    if not segment:
        return None
    return segment.file_offset + (vaddr - segment.vaddr)


def flags_text(segment):
    if not segment:
        return "unmapped"
    return "".join(
        (
            "r" if segment.flags & PF_R else "-",
            "w" if segment.flags & PF_W else "-",
            "x" if segment.flags & PF_X else "-",
        )
    )


def image_offset_for_vaddr(segments, vaddr):
    file_offset = vaddr_to_file_offset(segments, vaddr)
    if file_offset is None:
        return ""
    return f"0x{file_offset:x}"


def make_pattern(data, file_offset, size, wildcard_offset, wildcard_size, prefix, suffix, segment):
    start = max(segment.file_offset, file_offset - prefix)
    end = min(segment.file_offset + segment.file_size, file_offset + size + suffix)
    raw = data[start:end]
    wild_start = file_offset + wildcard_offset
    wild_end = wild_start + wildcard_size
    parts = []
    for index, value in enumerate(raw):
        absolute = start + index
        parts.append("??" if wild_start <= absolute < wild_end else f"{value:02x}")
    return start, " ".join(parts), hashlib.sha256(raw).hexdigest()


def pattern_match_count(data, tokens):
    parsed = []
    for token in tokens.split():
        parsed.append(None if token in ("?", "??") else int(token, 16))
    if not parsed:
        return 0
    count = 0
    limit = len(data) - len(parsed) + 1
    for offset in range(max(0, limit)):
        for index, expected in enumerate(parsed):
            if expected is not None and data[offset + index] != expected:
                break
        else:
            count += 1
            if count > 32:
                return count
    return count


def candidate_score(group, transform, target_segment, distance, match_count):
    score = 0
    target_flags = flags_text(target_segment)
    if match_count == 1:
        score += 100
    if group in ("names", "objects", "world") and transform.startswith("riprel32"):
        score += 60
        if "w" in target_flags:
            score += 40
    if group in ("dispatch", "package") and transform.startswith("callrel32"):
        score += 60
        if "x" in target_flags:
            score += 40
    if group == "reflection" and transform.startswith("riprel32"):
        score += 20
    score += max(0, 30 - min(distance // 16, 30))
    if match_count != 1:
        score -= 50 + min(match_count, 32)
    return score


def recover_candidates(data, segments, targets, window, prefix, suffix, max_per_target):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    candidates = []
    for target in targets:
        canonical = canonical_anchor_name(target.name)
        group = CANONICAL_GROUPS[canonical]
        segment = segment_for_file_offset(segments, target.file_offset)
        if not segment or not (segment.flags & PF_X):
            continue
        start = max(segment.file_offset, target.file_offset - window)
        end = min(segment.file_offset + segment.file_size, target.file_offset + window)
        code = data[start:end]
        base_vaddr = segment.vaddr + (start - segment.file_offset)
        target_candidates = []
        for insn in md.disasm(code, base_vaddr):
            insn_file = segment.file_offset + (insn.address - segment.vaddr)
            distance = abs(insn_file - target.file_offset)
            if not insn.operands:
                continue
            for operand in insn.operands:
                transform = ""
                target_vaddr = None
                wildcard_offset = None
                wildcard_size = None
                target_kind = ""
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP and insn.disp_size == 4:
                    transform = f"riprel32+{insn.disp_offset}"
                    target_vaddr = insn.address + insn.size + operand.mem.disp
                    wildcard_offset = insn.disp_offset
                    wildcard_size = insn.disp_size
                    target_kind = "rip-memory"
                elif operand.type == X86_OP_IMM and insn.mnemonic.startswith(("call", "jmp")) and insn.imm_size == 4:
                    transform = f"callrel32+{insn.imm_offset}"
                    target_vaddr = operand.imm
                    wildcard_offset = insn.imm_offset
                    wildcard_size = insn.imm_size
                    target_kind = "rel-control"
                if not transform or target_vaddr is None:
                    continue
                target_segment = segment_for_vaddr(segments, target_vaddr)
                if not target_segment:
                    continue
                _pattern_file, pattern, digest = make_pattern(
                    data,
                    insn_file,
                    insn.size,
                    wildcard_offset,
                    wildcard_size,
                    prefix,
                    suffix,
                    segment,
                )
                match_count = pattern_match_count(data, pattern)
                target_file = vaddr_to_file_offset(segments, target_vaddr)
                target_candidates.append(
                    Candidate(
                        source_name=target.name,
                        canonical_name=canonical,
                        group=group,
                        source_image_offset=target.image_offset,
                        instruction_file_offset=insn_file,
                        instruction_image_offset=insn_file,
                        instruction_vaddr=insn.address,
                        mnemonic=insn.mnemonic,
                        op_str=insn.op_str,
                        transform=transform,
                        pattern=pattern,
                        pattern_sha256=digest,
                        match_count=match_count,
                        target_vaddr=target_vaddr,
                        target_file_offset="" if target_file is None else f"0x{target_file:x}",
                        target_image_offset=image_offset_for_vaddr(segments, target_vaddr),
                        target_segment_flags=flags_text(target_segment),
                        target_kind=target_kind,
                        distance=distance,
                        score=candidate_score(group, transform, target_segment, distance, match_count),
                    )
                )
        target_candidates.sort(key=lambda item: (-item.score, item.distance, item.match_count, item.instruction_file_offset))
        candidates.extend(target_candidates[:max_per_target])
    return candidates


def candidate_dict(candidate):
    return {
        "sourceName": candidate.source_name,
        "canonicalName": candidate.canonical_name,
        "group": candidate.group,
        "sourceImageOffset": f"0x{candidate.source_image_offset:x}",
        "instructionFileOffset": f"0x{candidate.instruction_file_offset:x}",
        "instructionImageOffset": f"0x{candidate.instruction_image_offset:x}",
        "instructionVaddr": f"0x{candidate.instruction_vaddr:x}",
        "instruction": f"{candidate.mnemonic} {candidate.op_str}".strip(),
        "transform": candidate.transform,
        "pattern": candidate.pattern,
        "patternSha256": candidate.pattern_sha256,
        "matchCount": candidate.match_count,
        "targetVaddr": f"0x{candidate.target_vaddr:x}",
        "targetFileOffset": candidate.target_file_offset,
        "targetImageOffset": candidate.target_image_offset,
        "targetSegmentFlags": candidate.target_segment_flags,
        "targetKind": candidate.target_kind,
        "distance": candidate.distance,
        "score": candidate.score,
    }


def selected_candidates(candidates):
    selected = {}
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.distance, item.match_count)):
        if candidate.match_count != 1:
            continue
        selected.setdefault(candidate.canonical_name, candidate)
    return selected


def signature_lines(selected):
    lines = [
        "# Experimental UE anchor candidates from static instruction neighborhoods.",
        "# Validate with one read-only canary before using for object/reflection/hook work.",
    ]
    for name in sorted(selected):
        candidate = selected[name]
        lines.append(f"{name}@{candidate.transform}={candidate.pattern}")
    lines.append("")
    return "\n".join(lines)


def build_summary(binary, loader_log, args):
    data, segments, targets = load_targets(
        binary,
        loader_log,
        args.exe_substring,
        args.pid,
        args.category,
        args.name,
    )
    candidates = recover_candidates(
        data,
        segments,
        targets,
        args.window,
        args.signature_prefix,
        args.signature_suffix,
        args.max_per_target,
    )
    selected = selected_candidates(candidates)
    return {
        "schemaVersion": "dune-linux-ue-anchor-candidates/v1",
        "binary": str(binary),
        "loaderLog": str(loader_log),
        "targetCount": len(targets),
        "candidateCount": len(candidates),
        "selectedCount": len(selected),
        "selected": {name: candidate_dict(candidate) for name, candidate in sorted(selected.items())},
        "candidates": [candidate_dict(candidate) for candidate in sorted(candidates, key=lambda item: (item.group, item.canonical_name, -item.score))],
    }


def markdown(summary):
    lines = ["# Linux UE Anchor Candidate Recovery", ""]
    lines.append(f"- Targets: `{summary['targetCount']}`")
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Selected unique signatures: `{summary['selectedCount']}`")
    lines.append("")
    lines.append("## Selected")
    lines.append("")
    if not summary["selected"]:
        lines.append("- none")
    else:
        for name, row in summary["selected"].items():
            lines.append(
                f"- `{name}` group=`{row['group']}` score=`{row['score']}` "
                f"matchCount=`{row['matchCount']}` target=`{row['targetImageOffset']}` "
                f"flags=`{row['targetSegmentFlags']}`"
            )
            lines.append(f"  - signature: `{name}@{row['transform']}={row['pattern']}`")
            lines.append(f"  - instruction: `{row['instructionImageOffset']}` `{row['instruction']}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in summary["candidates"][:200]:
        lines.append(
            f"- `{row['canonicalName']}` from `{row['sourceName']}` group=`{row['group']}` "
            f"score=`{row['score']}` matches=`{row['matchCount']}` distance=`{row['distance']}` "
            f"target=`{row['targetImageOffset']}` flags=`{row['targetSegmentFlags']}`"
        )
        lines.append(f"  - `{row['instructionImageOffset']}` `{row['instruction']}`")
    if len(summary["candidates"]) > 200:
        lines.append(f"- ... +{len(summary['candidates']) - 200} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recover Linux UE anchor candidates from instruction neighborhoods around live canary hits.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--loader-log", type=Path, required=True)
    parser.add_argument("--exe-substring", default="DuneSandboxServer")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--category", action="append", default=["ue", "other"])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--window", type=int, default=384)
    parser.add_argument("--signature-prefix", type=int, default=8)
    parser.add_argument("--signature-suffix", type=int, default=16)
    parser.add_argument("--max-per-target", type=int, default=4)
    parser.add_argument("--format", choices=("json", "markdown", "signatures"), default="markdown")
    args = parser.parse_args(argv)

    summary = build_summary(args.binary, args.loader_log, args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "signatures":
        selected = {
            name: Candidate(
                source_name=row["sourceName"],
                canonical_name=row["canonicalName"],
                group=row["group"],
                source_image_offset=parse_int(row["sourceImageOffset"]),
                instruction_file_offset=parse_int(row["instructionFileOffset"]),
                instruction_image_offset=parse_int(row["instructionImageOffset"]),
                instruction_vaddr=parse_int(row["instructionVaddr"]),
                mnemonic=row["instruction"].split(" ", 1)[0],
                op_str=row["instruction"].split(" ", 1)[1] if " " in row["instruction"] else "",
                transform=row["transform"],
                pattern=row["pattern"],
                pattern_sha256=row["patternSha256"],
                match_count=row["matchCount"],
                target_vaddr=parse_int(row["targetVaddr"]),
                target_file_offset=row["targetFileOffset"],
                target_image_offset=row["targetImageOffset"],
                target_segment_flags=row["targetSegmentFlags"],
                target_kind=row["targetKind"],
                distance=row["distance"],
                score=row["score"],
            )
            for name, row in summary["selected"].items()
        }
        sys.stdout.write(signature_lines(selected))
    else:
        sys.stdout.write(markdown(summary))


if __name__ == "__main__":
    main()
