#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-donor-symbols/v1"
PACKAGE_ANCHORS = ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName")
SYMBOL_RE = re.compile(
    r"^\s*(?P<address>[0-9a-fA-F]+)?\s*(?P<type>[A-Za-z?])?\s*(?P<name>.+?)\s*$"
)


def import_xrefs():
    script = Path(__file__).resolve().parent / "summarize-linux-loader-xrefs.py"
    spec = importlib.util.spec_from_file_location("summarize_linux_loader_xrefs_for_donor_symbols", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def run_nm(path):
    proc = subprocess.run(
        ["nm", "-an", "--demangle", str(path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"nm failed with exit code {proc.returncode}")
    return proc.stdout.splitlines()


def read_lines(path, assume_text=False):
    candidate = Path(path)
    if assume_text:
        return candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    return run_nm(candidate)


def anchor_for_symbol(name):
    compact = re.sub(r"[^A-Za-z0-9_~:]", "", name)
    for anchor in PACKAGE_ANCHORS:
        if anchor in compact:
            return anchor
    return ""


def parse_symbol_lines(lines):
    rows = []
    seen = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        match = SYMBOL_RE.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        anchor = anchor_for_symbol(name)
        if not anchor:
            continue
        address = (match.group("address") or "").lower()
        symbol_type = match.group("type") or ""
        key = (anchor, address, name)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "anchor": anchor,
                "address": f"0x{int(address, 16):x}" if address else "",
                "type": symbol_type,
                "name": name,
                "promotable": symbol_type.upper() in {"T", "W"} and bool(address),
                "promotionUse": "donor byte-window seed; validate transferred signature against stripped target before promotion",
            }
        )
    return sorted(rows, key=lambda row: (PACKAGE_ANCHORS.index(row["anchor"]), row["address"], row["name"]))


def mask_relocatable_pattern(code, base_vaddr):
    xrefs = import_xrefs()
    wildcard_offsets = set()
    for pos in xrefs.iter_candidate_positions(code):
        for ref in xrefs.decode_rel_refs(code, pos, base_vaddr):
            disp = pos + int(ref.get("dispOffset", 0))
            wildcard_offsets.update(range(disp, min(len(code), disp + 4)))
        for ref in xrefs.decode_rip_memory_refs(code, pos, base_vaddr):
            disp = pos + int(ref.get("dispOffset", 0))
            wildcard_offsets.update(range(disp, min(len(code), disp + 4)))
    return " ".join("??" if index in wildcard_offsets else f"{value:02x}" for index, value in enumerate(code))


def attach_donor_patterns(rows, donor, signature_bytes):
    if signature_bytes <= 0:
        return rows
    xrefs = import_xrefs()
    try:
        data, segments = xrefs.load_elf_segments(Path(donor))
    except (OSError, ValueError):
        return rows
    enriched = []
    for row in rows:
        enriched_row = dict(row)
        if row.get("promotable") and row.get("address"):
            try:
                vaddr = int(row["address"], 16)
                file_offset = xrefs.vaddr_to_file_offset(segments, vaddr)
                segment = xrefs.segment_for_file_offset(segments, file_offset)
                end = min(file_offset + signature_bytes, segment.file_offset + segment.file_size)
                code = data[file_offset:end]
                if code:
                    enriched_row["donorSignature"] = {
                        "fileOffset": f"0x{file_offset:x}",
                        "vaddr": f"0x{vaddr:x}",
                        "length": len(code),
                        "pattern": mask_relocatable_pattern(code, vaddr),
                        "wildcardPolicy": "mask RIP-relative and relative branch/call 32-bit displacements",
                    }
            except (ValueError, IndexError):
                enriched_row["donorSignatureError"] = "symbol address is not inside a file-backed LOAD segment"
        enriched.append(enriched_row)
    return enriched


def build_commands(donor, target_binary, rows):
    commands = []
    for row in rows:
        if not row.get("promotable"):
            continue
        anchor = row["anchor"]
        address = row["address"]
        pattern = (row.get("donorSignature") or {}).get("pattern", "")
        signature = pattern or f"<reviewed bytes from donor {address}>"
        commands.append(
            {
                "anchor": anchor,
                "address": address,
                "dumpDonorWindow": (
                    f"objdump -d --demangle --no-show-raw-insn --start-address={address} "
                    f"--stop-address=$(({address}+0x180)) {donor}"
                ),
                "validateTransferredSignature": (
                    f"scripts/validate-elf-signatures.py {target_binary} "
                    f"--signature '{anchor}={signature}' "
                    "--scope executable --max-matches 8 --ignore-expected-offsets"
                ),
            }
        )
    return commands


def validation_pattern_from_symbol(row):
    signature = row.get("donorSignature") or {}
    pattern = signature.get("pattern", "")
    if not row.get("promotable") or not pattern:
        return None
    return {
        "name": row["anchor"],
        "category": "package",
        "source": row.get("name", ""),
        "sourceProvenance": "external-donor",
        "xrefVaddr": "",
        "targetVaddr": "",
        "pattern": pattern,
        "length": int(signature.get("length", 0) or 0),
        "fixedBytes": sum(1 for token in pattern.split() if token not in {"?", "??"}),
        "expectedFileOffset": "",
        "matchCount": 0,
        "matchesTruncated": False,
        "status": "donor-unvalidated",
        "promotable": False,
        "matches": [],
        "donor": {
            "address": row.get("address", ""),
            "fileOffset": signature.get("fileOffset", ""),
            "vaddr": signature.get("vaddr", ""),
            "symbol": row.get("name", ""),
            "wildcardPolicy": signature.get("wildcardPolicy", ""),
        },
    }


def candidate_validation(summary):
    patterns = [
        pattern
        for pattern in (validation_pattern_from_symbol(row) for row in summary.get("symbols", []))
        if pattern is not None
    ]
    return {
        "format": "elf64-donor-transfer",
        "imageBase": "",
        "scope": "executable",
        "patternCount": len(patterns),
        "promotableCount": 0,
        "statusCounts": {"donor-unvalidated": len(patterns)} if patterns else {},
        "categoryCounts": {"package": len(patterns)} if patterns else {},
        "patterns": patterns,
        "sourceDonorSymbols": summary.get("source", ""),
        "targetBinary": summary.get("targetBinary", ""),
        "nextStep": "validate these donor-derived patterns against the stripped target with validate-elf-signatures.py before promotion",
    }


def summarize(path, target_binary, assume_text=False, signature_bytes=96):
    source = str(path)
    rows = parse_symbol_lines(read_lines(path, assume_text=assume_text))
    if not assume_text:
        rows = attach_donor_patterns(rows, source, signature_bytes)
    promotable = [row for row in rows if row.get("promotable")]
    anchors = sorted({row["anchor"] for row in rows}, key=PACKAGE_ANCHORS.index)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": source,
        "sourceMode": "text" if assume_text else "nm",
        "targetBinary": str(target_binary),
        "anchorFamilies": list(PACKAGE_ANCHORS),
        "symbolCount": len(rows),
        "promotableSymbolCount": len(promotable),
        "anchorsPresent": anchors,
        "completeAnchorFamilyCoverage": all(anchor in anchors for anchor in PACKAGE_ANCHORS),
        "signatureBytes": 0 if assume_text else signature_bytes,
        "symbols": rows,
        "commands": build_commands(source, str(target_binary), rows),
        "nextStep": (
            "review a promotable donor function byte window, validate a unique target-image signature, then promote guarded package invocation evidence"
            if promotable
            else "find an unstripped/symbolized Linux UE donor with text symbols for StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName"
        ),
    }


def markdown(summary):
    lines = ["# UE4SS Package Donor Symbols", ""]
    lines.append(f"- Source: `{summary['source']}` mode=`{summary['sourceMode']}`")
    lines.append(f"- Target binary: `{summary['targetBinary']}`")
    lines.append(f"- Symbols: `{summary['symbolCount']}`")
    lines.append(f"- Promotable text symbols: `{summary['promotableSymbolCount']}`")
    lines.append("- Anchors present: `" + "`, `".join(summary.get("anchorsPresent", [])) + "`")
    lines.append(f"- Complete anchor family coverage: `{str(summary['completeAnchorFamilyCoverage']).lower()}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    if summary.get("symbols"):
        lines.append("")
        lines.append("## Symbols")
        lines.append("")
        for row in summary["symbols"]:
            lines.append(
                f"- `{row['anchor']}` `{row['address']}` type=`{row['type']}` promotable=`{str(row['promotable']).lower()}`"
            )
            lines.append(f"  - {row['name']}")
            if row.get("donorSignature"):
                sig = row["donorSignature"]
                lines.append(
                    f"  - donor signature: file=`{sig['fileOffset']}` length=`{sig['length']}` "
                    f"policy=`{sig['wildcardPolicy']}`"
                )
                lines.append(f"  - pattern: `{sig['pattern']}`")
            if row.get("donorSignatureError"):
                lines.append(f"  - signature error: {row['donorSignatureError']}")
    if summary.get("commands"):
        lines.append("")
        lines.append("## Commands")
        lines.append("")
        lines.append("```bash")
        for command in summary["commands"]:
            lines.append(command["dumpDonorWindow"])
            lines.append(command["validateTransferredSignature"])
        lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize package-loading symbols from an unstripped UE Linux donor.")
    parser.add_argument("donor")
    parser.add_argument("--target-binary", default="/tmp/dune-live-server-extract/DuneSandboxServer-Linux-Shipping")
    parser.add_argument("--assume-text", action="store_true", help="read donor as pre-produced nm/linker-map text")
    parser.add_argument("--signature-bytes", type=int, default=96, help="bytes to extract from each donor text symbol")
    parser.add_argument("--format", choices=("json", "markdown", "candidate-validation"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(
        args.donor,
        args.target_binary,
        assume_text=args.assume_text,
        signature_bytes=args.signature_bytes,
    )
    if args.format == "candidate-validation":
        json.dump(candidate_validation(summary), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
