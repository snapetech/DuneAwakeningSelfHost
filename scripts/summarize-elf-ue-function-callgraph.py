#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, deque
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

PACKAGE_ANCHORS = ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName")
STREAMABLE_HINTS = ("RequestAsyncLoad", "Streamable", "SoftObjectPath", "LoadAsset", "LoadClass")


def import_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def parse_seed(raw):
    if "=" in raw:
        name, value = raw.split("=", 1)
    else:
        value = raw
        name = f"seed-{value}"
    return name, parse_int(value)


def unique_preserve(values):
    seen = set()
    result = []
    for value in values:
        if not value:
            continue
        if isinstance(value, dict):
            key = (value.get("instruction"), value.get("kind"), value.get("target"))
        else:
            key = value
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def hint_for(ptrctx, data, sections, symbols, target):
    section = ptrctx.section_for_addr(sections, target)
    string = ptrctx.printable_hint(data, sections, target)
    names = symbols.get(target, [])[:4]
    text = "\n".join([string, *names])
    package = [
        anchor
        for anchor in PACKAGE_ANCHORS
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(anchor)}(?![A-Za-z0-9_])", text)
    ]
    streamable = [
        hint
        for hint in STREAMABLE_HINTS
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(hint)}(?![A-Za-z0-9_])", text)
    ]
    return {
        "target": f"0x{target:x}",
        "section": section.name if section else "",
        "symbols": names,
        "string": string,
        "packageAnchorHints": package,
        "streamableHints": streamable,
    }


def disassemble_function(xrefs, data, segments, vaddr, max_instructions):
    file_offset = xrefs.vaddr_to_file_offset(segments, vaddr)
    segment = xrefs.segment_for_file_offset(segments, file_offset)
    code = data[file_offset : min(segment.file_offset + segment.file_size, file_offset + 4096)]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    insns = []
    for insn in md.disasm(code, vaddr):
        insns.append(insn)
        if insn.mnemonic == "ret" or insn.mnemonic == "ud2":
            break
        if len(insns) >= max_instructions:
            break
    return file_offset, insns


def analyze_node(ptrctx, xrefs, data, segments, sections, symbols, vaddr, max_instructions):
    try:
        file_offset, insns = disassemble_function(xrefs, data, segments, vaddr, max_instructions)
    except ValueError:
        return None
    calls = []
    indirect_call_rows = []
    refs = []
    conditional_branches = 0
    indirect_calls = 0
    returns = 0
    for insn in insns:
        if insn.mnemonic.startswith("j") and insn.mnemonic != "jmp":
            conditional_branches += 1
        if insn.mnemonic == "ret":
            returns += 1
        if insn.mnemonic.startswith("call") and insn.operands:
            operand = insn.operands[0]
            if operand.type == X86_OP_IMM:
                target = int(operand.imm)
                calls.append(
                    {
                        "instruction": f"0x{insn.address:x}",
                        "text": f"{insn.mnemonic} {insn.op_str}".strip(),
                        "kind": "direct-call",
                        **hint_for(ptrctx, data, sections, symbols, target),
                    }
                )
            else:
                indirect_calls += 1
                row = {
                    "instruction": f"0x{insn.address:x}",
                    "text": f"{insn.mnemonic} {insn.op_str}".strip(),
                    "kind": "indirect-call",
                    "target": "",
                    "section": "",
                    "symbols": [],
                    "string": "",
                    "packageAnchorHints": [],
                    "streamableHints": [],
                }
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                    target = insn.address + insn.size + operand.mem.disp
                    row.update(hint_for(ptrctx, data, sections, symbols, target))
                indirect_call_rows.append(row)
        for operand in insn.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                target = insn.address + insn.size + operand.mem.disp
                hint = hint_for(ptrctx, data, sections, symbols, target)
                if hint["section"] or hint["symbols"] or hint["string"]:
                    refs.append(
                        {
                            "instruction": f"0x{insn.address:x}",
                            "text": f"{insn.mnemonic} {insn.op_str}".strip(),
                            "kind": "rip-memory",
                            **hint,
                        }
                    )
    package_hints = Counter(hint for row in refs + calls + indirect_call_rows for hint in row["packageAnchorHints"])
    streamable_hints = Counter(hint for row in refs + calls + indirect_call_rows for hint in row["streamableHints"])
    return {
        "function": f"0x{vaddr:x}",
        "fileOffset": f"0x{file_offset:x}",
        "instructionCount": len(insns),
        "conditionalBranchCount": conditional_branches,
        "directCallCount": len(calls),
        "indirectCallCount": indirect_calls,
        "returnCount": returns,
        "packageAnchorHintCounts": dict(package_hints),
        "streamableHintCounts": dict(streamable_hints),
        "refs": refs[:80],
        "calls": calls[:80],
        "indirectCalls": indirect_call_rows[:80],
    }


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_callgraph")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_callgraph")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)

    seeds = [parse_seed(seed) for seed in args.seed]
    queue = deque((name, vaddr, 0, []) for name, vaddr in seeds)
    visited = {}
    edges = []
    while queue and len(visited) < args.max_nodes:
        seed_name, vaddr, depth, path = queue.popleft()
        if vaddr in visited:
            continue
        node = analyze_node(ptrctx, xrefs, data, segments, sections, symbols, vaddr, args.max_instructions)
        if node is None:
            continue
        node["seedName"] = seed_name
        node["depth"] = depth
        node["path"] = [f"0x{item:x}" for item in path + [vaddr]]
        visited[vaddr] = node
        if depth >= args.depth:
            continue
        for call in node["calls"][: args.max_fanout]:
            target = parse_int(call["target"])
            if call.get("section") != ".text" or target in visited:
                continue
            edges.append({"from": f"0x{vaddr:x}", "to": f"0x{target:x}", "instruction": call["instruction"]})
            queue.append((seed_name, target, depth + 1, path + [vaddr]))

    package_nodes = [
        node for node in visited.values()
        if sum(node["packageAnchorHintCounts"].values()) > 0
    ]
    streamable_nodes = [
        node for node in visited.values()
        if sum(node["streamableHintCounts"].values()) > 0
    ]
    blockers = []
    if not package_nodes:
        blockers.append("no direct package anchor hints in bounded direct-call graph")
    if streamable_nodes and not package_nodes:
        blockers.append("streamable hints are async asset-manager evidence, not StaticLoadObject/StaticLoadClass/LoadPackage ABI proof")
    if any(node["indirectCallCount"] for node in visited.values()) and not package_nodes:
        blockers.append("indirect calls remain opaque without decompile/runtime call-frame proof")

    return {
        "schemaVersion": "dune-elf-ue-function-callgraph/v1",
        "binary": str(args.binary),
        "seeds": [{"name": name, "vaddr": f"0x{vaddr:x}"} for name, vaddr in seeds],
        "depth": args.depth,
        "maxNodes": args.max_nodes,
        "nodeCount": len(visited),
        "edgeCount": len(edges),
        "packageAnchorNodeCount": len(package_nodes),
        "streamableNodeCount": len(streamable_nodes),
        "promotableAsPackageAnchor": bool(package_nodes),
        "promotionBlockers": blockers,
        "edges": edges,
        "nodes": list(visited.values()),
    }


def markdown(summary, limit):
    lines = ["# ELF UE Function Callgraph", ""]
    lines.append(f"- Seeds: `{summary['seeds']}`")
    lines.append(f"- Depth: `{summary['depth']}`")
    lines.append(f"- Nodes: `{summary['nodeCount']}`")
    lines.append(f"- Edges: `{summary['edgeCount']}`")
    lines.append(f"- Package anchor nodes: `{summary['packageAnchorNodeCount']}`")
    lines.append(f"- Streamable nodes: `{summary['streamableNodeCount']}`")
    lines.append(f"- Promotable as package anchor: `{str(summary['promotableAsPackageAnchor']).lower()}`")
    if summary["promotionBlockers"]:
        lines.append(f"- Promotion blockers: `{summary['promotionBlockers']}`")
    lines.append("")
    lines.append("## Nodes")
    lines.append("")
    for node in summary["nodes"][:limit]:
        lines.append(
            f"- function=`{node['function']}` depth=`{node['depth']}` insns=`{node['instructionCount']}` "
            f"directCalls=`{node['directCallCount']}` indirectCalls=`{node['indirectCallCount']}` "
            f"package=`{node['packageAnchorHintCounts']}` streamable=`{node['streamableHintCounts']}`"
        )
        for ref in unique_preserve(node["refs"][:3] + node["calls"][:5] + node.get("indirectCalls", [])[:5]):
            string = f" string={ref['string']!r}" if ref.get("string") else ""
            symbols = f" symbols={ref['symbols']}" if ref.get("symbols") else ""
            text = f" text={ref['text']!r}" if ref.get("text") else ""
            lines.append(
                f"  - `{ref['instruction']}` `{ref['kind']}` target=`{ref['target']}` "
                f"section=`{ref.get('section') or '-'}`{string}{symbols}{text}"
            )
    if len(summary["nodes"]) > limit:
        lines.append(f"- ... +{len(summary['nodes']) - limit} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize a bounded direct-call graph from exact ELF function seeds.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--seed", action="append", required=True, help="Seed as NAME=VADDR or VADDR")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--max-nodes", type=int, default=64)
    parser.add_argument("--max-fanout", type=int, default=12)
    parser.add_argument("--max-instructions", type=int, default=260)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
