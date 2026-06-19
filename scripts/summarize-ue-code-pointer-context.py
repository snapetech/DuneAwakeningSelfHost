#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
CLIENT_XREF_SCRIPT = ROOT / "scripts" / "summarize-client-loader-xrefs.py"
IMAGE_SCN_MEM_EXECUTE = 0x20000000
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_SCN_MEM_WRITE = 0x80000000


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value, default=0):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def flags_text(section):
    if not section:
        return ""
    return "".join(
        flag
        for bit, flag in ((0x2, "A"), (0x1, "W"), (0x4, "X"))
        if section.flags & bit
    )


def pe_flags_text(section):
    if not section:
        return ""
    return "".join(
        flag
        for bit, flag in (
            (IMAGE_SCN_MEM_READ, "R"),
            (IMAGE_SCN_MEM_WRITE, "W"),
            (IMAGE_SCN_MEM_EXECUTE, "X"),
        )
        if section.characteristics & bit
    )


def value_hint(ptrctx, data, sections, symbols, value):
    section = ptrctx.section_for_addr(sections, value)
    return {
        "value": f"0x{value:x}",
        "section": section.name if section else "",
        "flags": flags_text(section),
        "symbols": symbols.get(value, [])[:4],
        "string": ptrctx.printable_hint(data, sections, value),
    }


def pe_section_for_value(pe, value):
    rva = value - pe.image_base if value >= pe.image_base else value
    try:
        return rva, pe_xref_section_for_rva(pe, rva)
    except ValueError:
        return rva, None


def pe_xref_section_for_rva(pe, rva):
    for section in pe.sections:
        if section.contains_rva(rva):
            return section
    raise ValueError(f"RVA 0x{rva:x} is not inside a PE section")


def pe_printable_hint(pe, value):
    rva, section = pe_section_for_value(pe, value)
    if not section:
        return ""
    try:
        file_offset = section.raw_pointer + (rva - section.virtual_address)
    except ValueError:
        return ""
    if file_offset < 0 or file_offset >= len(pe.data):
        return ""
    raw = pe.data[file_offset : min(len(pe.data), file_offset + 96)]
    chars = []
    for byte in raw:
        if byte == 0:
            break
        if byte in (0x09, 0x20) or 0x21 <= byte <= 0x7E:
            chars.append(byte)
        else:
            break
    return bytes(chars).decode("ascii", errors="replace") if len(chars) >= 4 else ""


def pe_value_hint(pe, value):
    rva, section = pe_section_for_value(pe, value)
    return {
        "value": f"0x{value:x}",
        "rva": f"0x{rva:x}" if section else "",
        "section": section.name if section else "",
        "flags": pe_flags_text(section),
        "symbols": [],
        "string": pe_printable_hint(pe, value),
    }


def disassemble_target(ptrctx, xrefs, data, segments, sections, symbols, file_offset, max_instructions, signature_length):
    try:
        vaddr = xrefs.file_offset_to_vaddr(segments, file_offset)
    except ValueError:
        return None
    segment = xrefs.segment_for_file_offset(segments, file_offset)
    code = data[file_offset : min(segment.file_offset + segment.file_size, file_offset + 512)]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    instructions = []
    refs = []
    calls = []
    for index, insn in enumerate(md.disasm(code, vaddr)):
        if index >= max_instructions:
            break
        text = f"{insn.mnemonic} {insn.op_str}".strip()
        instructions.append({"address": f"0x{insn.address:x}", "text": text, "bytes": insn.bytes.hex()})
        for operand in insn.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                target = insn.address + insn.size + operand.mem.disp
                refs.append({"instruction": f"0x{insn.address:x}", "text": text, **value_hint(ptrctx, data, sections, symbols, target)})
            elif operand.type == X86_OP_IMM and insn.mnemonic.startswith(("call", "jmp")):
                target = int(operand.imm)
                calls.append({"instruction": f"0x{insn.address:x}", "text": text, **value_hint(ptrctx, data, sections, symbols, target)})
    signature = data[file_offset : min(len(data), file_offset + signature_length)]
    return {
        "fileOffset": f"0x{file_offset:x}",
        "vaddr": f"0x{vaddr:x}",
        "signatureLength": len(signature),
        "signatureSha256": hashlib.sha256(signature).hexdigest(),
        "signatureBytes": " ".join(f"{byte:02x}" for byte in signature),
        "instructions": instructions,
        "ripRefs": refs,
        "controlTargets": calls,
    }


def disassemble_pe_target(xrefs, pe, file_offset, max_instructions, signature_length):
    try:
        rva = xrefs.file_offset_to_rva(pe, file_offset)
        section = xrefs.section_for_file_offset(pe, file_offset)
    except ValueError:
        return None
    vaddr = pe.image_base + rva
    code = pe.data[file_offset : min(section.raw_pointer + section.raw_size, file_offset + 512)]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    instructions = []
    refs = []
    calls = []
    for index, insn in enumerate(md.disasm(code, vaddr)):
        if index >= max_instructions:
            break
        text = f"{insn.mnemonic} {insn.op_str}".strip()
        instructions.append({"address": f"0x{insn.address:x}", "text": text, "bytes": insn.bytes.hex()})
        for operand in insn.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                target = insn.address + insn.size + operand.mem.disp
                refs.append({"instruction": f"0x{insn.address:x}", "text": text, **pe_value_hint(pe, target)})
            elif operand.type == X86_OP_IMM and insn.mnemonic.startswith(("call", "jmp")):
                target = int(operand.imm)
                calls.append({"instruction": f"0x{insn.address:x}", "text": text, **pe_value_hint(pe, target)})
    signature = pe.data[file_offset : min(len(pe.data), file_offset + signature_length)]
    return {
        "fileOffset": f"0x{file_offset:x}",
        "rva": f"0x{rva:x}",
        "vaddr": f"0x{vaddr:x}",
        "signatureLength": len(signature),
        "signatureSha256": hashlib.sha256(signature).hexdigest(),
        "signatureBytes": " ".join(f"{byte:02x}" for byte in signature),
        "instructions": instructions,
        "ripRefs": refs,
        "controlTargets": calls,
    }


def pointer_slot_context(ptrctx, data, sections, symbols, relocations, file_offset, window):
    section = ptrctx.section_for_file_offset(sections, file_offset)
    if section is None:
        return []
    center = section.addr + (file_offset - section.offset)
    return ptrctx.pointer_context_at_addr(data, sections, symbols, relocations, center, window)


def pe_pointer_slot_context(xrefs, pe, file_offset, window):
    try:
        section = xrefs.section_for_file_offset(pe, file_offset)
    except ValueError:
        return []
    stride = 8
    rows = []
    start_slot = -window
    end_slot = window
    for slot in range(start_slot, end_slot + 1):
        current = file_offset + slot * stride
        if current < section.raw_pointer or current + stride > section.raw_pointer + section.raw_size:
            continue
        value = int.from_bytes(pe.data[current : current + stride], "little")
        rva = xrefs.file_offset_to_rva(pe, current)
        rows.append(
            {
                "slot": slot,
                "vaddr": f"0x{pe.image_base + rva:x}",
                "fileOffset": f"0x{current:x}",
                **pe_value_hint(pe, value),
            }
        )
    return rows


def candidate_code_pointer_rows(outcomes):
    rows = []
    for candidate in outcomes.get("candidates", []):
        if candidate.get("recommendation") != "reject-code-pointer-and-trace-caller-dataflow":
            continue
        yield candidate


def summarize_elf(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_code_pointer_context")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_code_pointer_context")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    relocations = ptrctx.load_relocations(data, sections)
    outcomes = load_json(args.candidate_outcomes_json)

    rows = []
    for candidate in candidate_code_pointer_rows(outcomes):
        anchor = (candidate.get("anchorTargets") or [{}])[0]
        anchor_file_offset = parse_int(anchor.get("fileOffset", ""), None)
        pointer_rows = []
        for pointer in candidate.get("pointerTargets", []):
            pointer_file_offset = parse_int(pointer.get("fileOffset", ""), None)
            if pointer_file_offset is None:
                continue
            pointer_rows.append(
                {
                    **pointer,
                    "staticTarget": disassemble_target(
                        ptrctx,
                        xrefs,
                        data,
                        segments,
                        sections,
                        symbols,
                        pointer_file_offset,
                        args.max_instructions,
                        args.signature_length,
                    ),
                }
            )
        rows.append(
            {
                "name": candidate.get("name", ""),
                "imageOffset": candidate.get("imageOffset", ""),
                "verdict": candidate.get("verdict", ""),
                "recommendation": candidate.get("recommendation", ""),
                "anchor": anchor,
                "anchorPointerContext": pointer_slot_context(
                    ptrctx,
                    data,
                    sections,
                    symbols,
                    relocations,
                    anchor_file_offset,
                    args.pointer_window,
                )
                if anchor_file_offset is not None
                else [],
                "pointerTargets": pointer_rows,
            }
        )
    return {
        "schemaVersion": "dune-ue-code-pointer-context/v1",
        "binary": str(args.binary),
        "sourceOutcomes": str(args.candidate_outcomes_json),
        "supported": True,
        "format": "elf",
        "rowCount": len(rows),
        "rows": rows,
    }


def summarize_pe(args):
    xrefs = import_script(CLIENT_XREF_SCRIPT, "summarize_client_loader_xrefs_for_code_pointer_context")
    pe = xrefs.load_pe_image(args.binary)
    outcomes = load_json(args.candidate_outcomes_json)
    rows = []
    for candidate in candidate_code_pointer_rows(outcomes):
        anchor = (candidate.get("anchorTargets") or [{}])[0]
        anchor_file_offset = parse_int(anchor.get("fileOffset", ""), None)
        pointer_rows = []
        for pointer in candidate.get("pointerTargets", []):
            pointer_file_offset = parse_int(pointer.get("fileOffset", ""), None)
            if pointer_file_offset is None:
                continue
            pointer_rows.append(
                {
                    **pointer,
                    "staticTarget": disassemble_pe_target(
                        xrefs,
                        pe,
                        pointer_file_offset,
                        args.max_instructions,
                        args.signature_length,
                    ),
                }
            )
        rows.append(
            {
                "name": candidate.get("name", ""),
                "imageOffset": candidate.get("imageOffset", ""),
                "verdict": candidate.get("verdict", ""),
                "recommendation": candidate.get("recommendation", ""),
                "anchor": anchor,
                "anchorPointerContext": pe_pointer_slot_context(xrefs, pe, anchor_file_offset, args.pointer_window)
                if anchor_file_offset is not None
                else [],
                "pointerTargets": pointer_rows,
            }
        )
    return {
        "schemaVersion": "dune-ue-code-pointer-context/v1",
        "binary": str(args.binary),
        "sourceOutcomes": str(args.candidate_outcomes_json),
        "supported": True,
        "format": "pe",
        "rowCount": len(rows),
        "rows": rows,
    }


def summarize(args):
    header = args.binary.read_bytes()[:4]
    if header[:4] == b"\x7fELF":
        return summarize_elf(args)
    if header[:2] == b"MZ":
        return summarize_pe(args)
    return {
        "schemaVersion": "dune-ue-code-pointer-context/v1",
        "binary": str(args.binary),
        "sourceOutcomes": str(args.candidate_outcomes_json),
        "supported": False,
        "reason": "unsupported-binary-format",
        "rowCount": 0,
        "rows": [],
    }


def markdown(summary, limit_instructions):
    lines = ["# UE Code Pointer Context", ""]
    lines.append(f"- Rows: `{summary['rowCount']}`")
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Outcomes: `{summary['sourceOutcomes']}`")
    if not summary.get("supported", True):
        lines.append(f"- Supported: `false`")
        lines.append(f"- Reason: `{summary.get('reason', '')}`")
        lines.append("")
        return "\n".join(lines)
    lines.append("")
    for row in summary["rows"]:
        anchor = row["anchor"]
        lines.append(f"## {row['name']} {row['imageOffset']}")
        lines.append("")
        lines.append(f"- verdict: `{row['verdict']}`")
        lines.append(f"- recommendation: `{row['recommendation']}`")
        lines.append(f"- anchor file: `{anchor.get('fileOffset', '')}` perms: `{anchor.get('perms', '')}`")
        if row["anchorPointerContext"]:
            lines.append("- pointer slot context:")
            for item in row["anchorPointerContext"]:
                symbol = " | ".join(item.get("symbols", []))
                hint = item.get("string", "")
                detail = symbol or hint
                suffix = f" detail=`{detail}`" if detail else ""
                lines.append(
                    f"  - slot=`{item['slot']}` vaddr=`{item['vaddr']}` value=`{item['value']}` "
                    f"section=`{item['section']}` flags=`{item['flags']}`{suffix}"
                )
        for pointer in row["pointerTargets"]:
            target = pointer.get("staticTarget") or {}
            lines.append(
                f"- code pointer `{pointer.get('imageOffset', '')}` file=`{pointer.get('fileOffset', '')}` "
                f"sha256=`{target.get('signatureSha256', '')}`"
            )
            for insn in (target.get("instructions") or [])[:limit_instructions]:
                lines.append(f"  - `{insn['address']}` `{insn['text']}`")
            if target.get("ripRefs"):
                lines.append("  - RIP refs:")
                for ref in target["ripRefs"][:12]:
                    detail = " | ".join(ref.get("symbols", [])) or ref.get("string", "")
                    suffix = f" detail=`{detail}`" if detail else ""
                    lines.append(
                        f"    - `{ref['instruction']}` `{ref['text']}` -> `{ref['value']}` "
                        f"section=`{ref['section']}` flags=`{ref['flags']}`{suffix}"
                    )
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize static context for UE candidates that point at code.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("candidate_outcomes_json", type=Path)
    parser.add_argument("--pointer-window", type=int, default=3)
    parser.add_argument("--max-instructions", type=int, default=32)
    parser.add_argument("--signature-length", type=int, default=32)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit-instructions", type=int, default=16)
    args = parser.parse_args(argv)

    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit_instructions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
