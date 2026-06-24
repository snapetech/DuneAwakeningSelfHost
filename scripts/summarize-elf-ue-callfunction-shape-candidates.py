#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
SCHEMA_VERSION = "dune-elf-ue-callfunction-shape-candidates/v1"

STRING_HINTS = (
    "CallFunction",
    "Function",
    "ProcessEvent",
    "ProcessConsoleExec",
    "ScriptCore",
    "UFunction",
    "exec",
    "Command",
)


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def text_section(sections):
    for section in sections:
        if section.name == ".text":
            return section
    return next((section for section in sections if section.flags & 0x4), None)


def iter_function_starts(data, section, limit):
    start = section.offset
    end = section.offset + section.size
    patterns = (b"\x55\x48\x89\xe5", b"\x41\x57\x41\x56", b"\x41\x56\x53", b"\x53\x48\x83\xec")
    seen = set()
    for pattern in patterns:
        cursor = start
        while cursor < end:
            pos = data.find(pattern, cursor, end)
            if pos < 0:
                break
            if pos not in seen:
                seen.add(pos)
                yield section.addr + (pos - section.offset)
                if limit and len(seen) >= limit:
                    return
            cursor = pos + 1


def register_name(insn, reg_id):
    try:
        return insn.reg_name(reg_id) or ""
    except Exception:
        return ""


def operand_register_names(insn):
    names = []
    for operand in insn.operands:
        if operand.type == X86_OP_REG:
            names.append(register_name(insn, operand.reg))
        elif operand.type == X86_OP_MEM:
            for reg in (operand.mem.base, operand.mem.index):
                name = register_name(insn, reg)
                if name:
                    names.append(name)
    return names


def has_arg_register(names, prefixes):
    return any(name == prefix or name.startswith(prefix) for name in names for prefix in prefixes)


def hint_for(ptrctx, data, sections, symbols, target):
    section = ptrctx.section_for_addr(sections, target)
    string = ptrctx.printable_hint(data, sections, target)
    names = symbols.get(target, [])[:4]
    return {
        "target": f"0x{target:x}",
        "section": section.name if section else "",
        "symbols": names,
        "string": string,
    }


def disassemble(xrefs, data, segments, vaddr, max_instructions):
    file_offset = xrefs.vaddr_to_file_offset(segments, vaddr)
    segment = xrefs.segment_for_file_offset(segments, file_offset)
    code = data[file_offset : min(segment.file_offset + segment.file_size, file_offset + 3072)]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    rows = []
    for insn in md.disasm(code, vaddr):
        rows.append(insn)
        if insn.mnemonic == "ret" or insn.mnemonic == "ud2":
            break
        if len(rows) >= max_instructions:
            break
    return file_offset, rows


def signature(data, file_offset, length):
    raw = data[file_offset : min(len(data), file_offset + length)]
    return {
        "fileOffset": f"0x{file_offset:x}",
        "imageOffset": f"0x{file_offset:x}",
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pattern": " ".join(f"{byte:02x}" for byte in raw),
    }


def indirect_pattern(row):
    return tuple(call.get("text", "") for call in row.get("indirectCalls", [])[:4])


def direct_target_pattern(row):
    return tuple(call.get("target", "") for call in row.get("directCalls", [])[:4])


def annotate_narrowing(rows):
    signature_counts = Counter(row.get("signature", {}).get("sha256", "") for row in rows)
    indirect_counts = Counter(indirect_pattern(row) for row in rows)
    direct_counts = Counter(direct_target_pattern(row) for row in rows)
    for row in rows:
        sig_repeat = signature_counts[row.get("signature", {}).get("sha256", "")]
        indirect_repeat = indirect_counts[indirect_pattern(row)]
        direct_repeat = direct_counts[direct_target_pattern(row)]
        direct_targets = {call.get("target", "") for call in row.get("directCalls", []) if call.get("target")}
        indirect_texts = [call.get("text", "") for call in row.get("indirectCalls", [])]
        repeated_vtable_shape = indirect_repeat > 8 and not row.get("stringHints")
        narrow_score = row["score"]
        narrow_score += min(row.get("usedArgCount", 0), 5) * 5
        narrow_score += min(row.get("commandMemoryReads", 0), 4) * 6
        narrow_score += min(row.get("branchCount", 0), 12) * 2
        narrow_score += min(len(direct_targets), 6) * 4
        narrow_score += len(row.get("stringHints", [])) * 12
        narrow_score -= min(max(sig_repeat - 1, 0), 8) * 8
        narrow_score -= min(max(indirect_repeat - 1, 0), 12) * 5
        narrow_score -= min(max(direct_repeat - 1, 0), 12) * 3
        if repeated_vtable_shape:
            narrow_score -= 20
        if any("+ 0x150]" in text for text in indirect_texts) and any("+ 0x168]" in text for text in indirect_texts):
            narrow_score -= 8
        row["narrowing"] = {
            "score": narrow_score,
            "signatureRepeatCount": sig_repeat,
            "indirectPatternRepeatCount": indirect_repeat,
            "directTargetPatternRepeatCount": direct_repeat,
            "uniqueDirectTargetCount": len(direct_targets),
            "repeatedVtableShape": repeated_vtable_shape,
            "promotable": False,
            "promotionBlocker": "static narrowing only; requires hook probe and target-entry active validation",
        }
    return rows


def analyze_function(ptrctx, xrefs, data, segments, sections, symbols, vaddr, max_instructions, signature_length):
    try:
        file_offset, insns = disassemble(xrefs, data, segments, vaddr, max_instructions)
    except ValueError:
        return None
    arg_uses = {key: 0 for key in ("object", "command", "output", "executor", "forceCall")}
    direct_calls = []
    indirect_calls = []
    refs = []
    string_hints = []
    command_memory_reads = 0
    branch_count = 0
    for insn in insns:
        names = operand_register_names(insn)
        if has_arg_register(names, ("rdi", "edi")):
            arg_uses["object"] += 1
        if has_arg_register(names, ("rsi", "esi")):
            arg_uses["command"] += 1
        if has_arg_register(names, ("rdx", "edx")):
            arg_uses["output"] += 1
        if has_arg_register(names, ("rcx", "ecx")):
            arg_uses["executor"] += 1
        if has_arg_register(names, ("r8", "r8d")):
            arg_uses["forceCall"] += 1
        if insn.mnemonic.startswith("j") and insn.mnemonic != "jmp":
            branch_count += 1
        for operand in insn.operands:
            if operand.type == X86_OP_MEM:
                base = register_name(insn, operand.mem.base)
                if base in ("rsi", "esi"):
                    command_memory_reads += 1
                if operand.mem.base == X86_REG_RIP:
                    target = insn.address + insn.size + operand.mem.disp
                    hint = hint_for(ptrctx, data, sections, symbols, target)
                    if hint["section"] or hint["string"] or hint["symbols"]:
                        refs.append({"instruction": f"0x{insn.address:x}", "text": f"{insn.mnemonic} {insn.op_str}", **hint})
                        text = "\n".join([hint["string"], *hint["symbols"]])
                        matched = [needle for needle in STRING_HINTS if re.search(re.escape(needle), text, re.IGNORECASE)]
                        for needle in matched:
                            if needle not in string_hints:
                                string_hints.append(needle)
        if insn.mnemonic.startswith("call") and insn.operands:
            operand = insn.operands[0]
            row = {"instruction": f"0x{insn.address:x}", "text": f"{insn.mnemonic} {insn.op_str}"}
            if operand.type == X86_OP_IMM:
                direct_calls.append({**row, **hint_for(ptrctx, data, sections, symbols, int(operand.imm))})
            else:
                indirect_calls.append(row)
    used_arg_count = sum(1 for count in arg_uses.values() if count)
    score = 0
    score += used_arg_count * 8
    score += min(arg_uses["forceCall"], 2) * 10
    score += min(arg_uses["command"], 3) * 6
    score += min(command_memory_reads, 3) * 8
    score += min(len(indirect_calls), 4) * 8
    score += min(len(direct_calls), 8) * 2
    score += len(string_hints) * 10
    if len(insns) < 8:
        score -= 20
    if not arg_uses["forceCall"]:
        score -= 12
    if not arg_uses["command"]:
        score -= 12
    return {
        "function": f"0x{vaddr:x}",
        "fileOffset": f"0x{file_offset:x}",
        "score": score,
        "instructionCount": len(insns),
        "branchCount": branch_count,
        "argUses": arg_uses,
        "usedArgCount": used_arg_count,
        "commandMemoryReads": command_memory_reads,
        "directCallCount": len(direct_calls),
        "indirectCallCount": len(indirect_calls),
        "stringHints": string_hints,
        "refs": refs[:20],
        "directCalls": direct_calls[:20],
        "indirectCalls": indirect_calls[:20],
        "signature": signature(data, file_offset, signature_length),
    }


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_callfunction_shape")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_callfunction_shape")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    section = text_section(sections)
    if section is None:
        raise RuntimeError("no executable text section found")
    rows = []
    for vaddr in iter_function_starts(data, section, args.scan_function_limit):
        row = analyze_function(ptrctx, xrefs, data, segments, sections, symbols, vaddr, args.max_instructions, args.signature_length)
        if row and row["score"] >= args.min_score:
            rows.append(row)
    annotate_narrowing(rows)
    rows.sort(key=lambda row: (-row["score"], -row["usedArgCount"], row["function"]))
    narrowed_rows = sorted(rows, key=lambda row: (-row["narrowing"]["score"], -row["score"], row["function"]))
    blockers = [
        "shape candidates are static review leads only; promote only after hook probe and target-entry active validation",
    ]
    if not rows:
        blockers.append("no CallFunction ABI-shape candidates met the score threshold")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "binary": str(args.binary),
        "textSection": {"name": section.name, "addr": f"0x{section.addr:x}", "size": f"0x{section.size:x}"},
        "scannedFunctionLimit": args.scan_function_limit,
        "candidateCount": len(rows),
        "promotable": False,
        "promotionBlockers": blockers,
        "candidates": rows[: args.limit],
        "narrowedCandidates": narrowed_rows[: args.narrowed_limit],
    }


def markdown(summary):
    lines = ["# ELF UE CallFunction Shape Candidates", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Text: `{summary['textSection']}`")
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Promotable: `{str(summary['promotable']).lower()}`")
    lines.append("")
    lines.append("## Promotion Blockers")
    lines.append("")
    for blocker in summary.get("promotionBlockers", []):
        lines.append(f"- {blocker}")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in summary.get("candidates", []):
        sig = row.get("signature", {})
        lines.append(
            f"- function=`{row['function']}` score=`{row['score']}` args=`{row['usedArgCount']}` "
            f"argUses=`{row['argUses']}` commandReads=`{row['commandMemoryReads']}` "
            f"directCalls=`{row['directCallCount']}` indirectCalls=`{row['indirectCallCount']}` "
            f"hints=`{row['stringHints']}` sigFile=`{sig.get('fileOffset', '')}` sha256=`{sig.get('sha256', '')[:16]}`"
        )
        for ref in row.get("refs", [])[:4]:
            detail = " | ".join(ref.get("symbols", [])) or ref.get("string", "")
            if detail:
                lines.append(f"  - ref=`{ref['instruction']}` target=`{ref['target']}` section=`{ref['section']}` detail=`{detail}`")
        for call in row.get("directCalls", [])[:4]:
            detail = " | ".join(call.get("symbols", [])) or call.get("string", "")
            lines.append(f"  - call=`{call['instruction']}` target=`{call['target']}` section=`{call['section']}` detail=`{detail}`")
        for call in row.get("indirectCalls", [])[:4]:
            lines.append(f"  - indirect=`{call['instruction']}` text=`{call['text']}`")
    lines.append("")
    lines.append("## Narrowed Static Leads")
    lines.append("")
    for row in summary.get("narrowedCandidates", []):
        narrowing = row.get("narrowing", {})
        lines.append(
            f"- function=`{row['function']}` narrowScore=`{narrowing.get('score')}` rawScore=`{row['score']}` "
            f"sigRepeats=`{narrowing.get('signatureRepeatCount')}` indirectRepeats=`{narrowing.get('indirectPatternRepeatCount')}` "
            f"directRepeats=`{narrowing.get('directTargetPatternRepeatCount')}` uniqueDirectTargets=`{narrowing.get('uniqueDirectTargetCount')}` "
            f"promotable=`{str(narrowing.get('promotable')).lower()}`"
        )
        for call in row.get("directCalls", [])[:3]:
            lines.append(f"  - call=`{call['instruction']}` target=`{call['target']}` section=`{call['section']}`")
        for call in row.get("indirectCalls", [])[:3]:
            lines.append(f"  - indirect=`{call['instruction']}` text=`{call['text']}`")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank stripped ELF functions that resemble UObject::CallFunctionByNameWithArguments.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--scan-function-limit", type=int, default=50000)
    parser.add_argument("--max-instructions", type=int, default=160)
    parser.add_argument("--signature-length", type=int, default=32)
    parser.add_argument("--min-score", type=int, default=55)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--narrowed-limit", type=int, default=25)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
