#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-donor-search/v1"
DEFAULT_SKIP_DIRS = {
    ".cache",
    ".cargo",
    ".git",
    ".npm",
    ".rustup",
    ".venv",
    "__pycache__",
    "node_modules",
    "target",
}
ELF_NAMES = ("Linux-Shipping", "UnrealEditor", "UE4Editor")
ELF_SUFFIXES = (".so", ".debug", ".sym")
TEXT_SUFFIXES = (".map", ".nm", ".symbols", ".txt")
TEXT_NAME_HINTS = ("symbol", "symbols", "linker", "linux-shipping")
SOURCE_SUFFIXES = (".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx", ".inl")
SOURCE_PATH_HINTS = ("engine", "unreal", "coreuobject", "uobject")
UE_DONOR_HINTS = ("ue4", "ue5", "unreal", "engine", "coreuobject", "dunesandbox")
PRIMARY_PACKAGE_ANCHORS = {"StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage"}
PACKAGE_ANCHORS = tuple(sorted(PRIMARY_PACKAGE_ANCHORS | {"ResolveName"}))


def import_donor_symbols():
    script = Path(__file__).resolve().parent / "summarize-ue4ss-package-donor-symbols.py"
    spec = importlib.util.spec_from_file_location("summarize_ue4ss_package_donor_symbols_for_search", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def looks_like_elf_candidate(path):
    name = path.name
    return any(hint in name for hint in ELF_NAMES) or path.suffix in ELF_SUFFIXES


def looks_like_text_candidate(path):
    lower = path.name.lower()
    return path.suffix.lower() in TEXT_SUFFIXES and any(hint in lower for hint in TEXT_NAME_HINTS)


def looks_like_source_candidate(path):
    if path.suffix.lower() not in SOURCE_SUFFIXES:
        return False
    lowered_parts = {part.lower() for part in path.parts}
    return bool(lowered_parts & set(SOURCE_PATH_HINTS))


def looks_like_ue_donor_path(path):
    lowered = str(path).lower()
    return any(hint in lowered for hint in UE_DONOR_HINTS)


def candidate_mode(path):
    try:
        with path.open("rb") as handle:
            magic = handle.read(4)
    except OSError:
        return ""
    if magic == b"\x7fELF":
        return "elf"
    if looks_like_text_candidate(path):
        return "text"
    return ""


def iter_candidate_paths(roots, max_depth, skip_dirs):
    seen = set()
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        root_path = root_path.resolve()
        for current, dirs, files in os.walk(root_path):
            current_path = Path(current)
            rel_depth = len(current_path.relative_to(root_path).parts)
            dirs[:] = [
                item
                for item in dirs
                if item not in skip_dirs and (max_depth < 0 or rel_depth < max_depth)
            ]
            for filename in files:
                path = current_path / filename
                if not looks_like_elf_candidate(path) and not looks_like_text_candidate(path):
                    continue
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield path


def iter_source_paths(roots, max_depth, skip_dirs):
    seen = set()
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        root_path = root_path.resolve()
        for current, dirs, files in os.walk(root_path):
            current_path = Path(current)
            rel_depth = len(current_path.relative_to(root_path).parts)
            dirs[:] = [
                item
                for item in dirs
                if item not in skip_dirs and (max_depth < 0 or rel_depth < max_depth)
            ]
            for filename in files:
                path = current_path / filename
                if not looks_like_source_candidate(path):
                    continue
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield path


def summarize_source_candidate(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "path": str(path),
            "mode": "source",
            "error": str(exc),
            "anchorsPresent": [],
            "usable": False,
            "nextStep": "make this source tree produce a Linux linker map, debug ELF, or symbolized binary before signature transfer",
        }
    anchors = [anchor for anchor in PACKAGE_ANCHORS if anchor in text]
    if not anchors:
        return None
    return {
        "path": str(path),
        "mode": "source",
        "anchorsPresent": anchors,
        "anchorCount": len(anchors),
        "usable": False,
        "promotion": "source-reference-only",
        "nextStep": "build this UE source tree with symbols or locate its Linux linker map/debug ELF for target signature validation",
    }


def summarize_candidate(donor_module, path, target_binary, signature_bytes):
    mode = candidate_mode(path)
    if not mode:
        return None
    try:
        summary = donor_module.summarize(
            path,
            target_binary,
            assume_text=(mode == "text"),
            signature_bytes=signature_bytes,
        )
    except (OSError, RuntimeError, ValueError, UnicodeDecodeError) as exc:
        return {
            "path": str(path),
            "mode": mode,
            "error": str(exc),
            "symbolCount": 0,
            "promotableSymbolCount": 0,
            "anchorsPresent": [],
        }
    usable = candidate_is_usable(summary, path)
    row = {
        "path": str(path),
        "mode": mode,
        "symbolCount": summary.get("symbolCount", 0),
        "promotableSymbolCount": summary.get("promotableSymbolCount", 0),
        "anchorsPresent": summary.get("anchorsPresent", []),
        "usable": usable,
        "completeAnchorFamilyCoverage": summary.get("completeAnchorFamilyCoverage", False),
        "nextStep": summary.get("nextStep", ""),
    }
    if not usable:
        row["rejectionReason"] = candidate_rejection_reason(summary, path)
    return row


def candidate_is_usable(summary, path=None):
    anchors = set(summary.get("anchorsPresent", []) or [])
    if int(summary.get("promotableSymbolCount", 0) or 0) <= 0:
        return False
    if len(anchors) < 2 and path is not None and not looks_like_ue_donor_path(path):
        return False
    return bool(anchors & PRIMARY_PACKAGE_ANCHORS) or len(anchors) >= 2


def candidate_rejection_reason(summary, path=None):
    anchors = set(summary.get("anchorsPresent", []) or [])
    promotable = int(summary.get("promotableSymbolCount", 0) or 0)
    if promotable <= 0:
        return "no promotable text symbols for package-loading anchors"
    if not (anchors & PRIMARY_PACKAGE_ANCHORS):
        return "only ResolveName-like symbols were found; no primary package-loading anchor is present"
    if len(anchors) < 2 and path is not None and not looks_like_ue_donor_path(path):
        return "single generic package-name symbol outside a UE-looking donor path is treated as a false positive"
    return "candidate does not meet package donor acceptance rules"


def search(roots, target_binary, max_depth=6, signature_bytes=96, skip_dirs=None, source_max_depth=None):
    skip_dirs = set(skip_dirs or DEFAULT_SKIP_DIRS)
    if source_max_depth is None:
        source_max_depth = max_depth
    donor_module = import_donor_symbols()
    rows = []
    source_rows = []
    for path in iter_candidate_paths(roots, max_depth, skip_dirs):
        row = summarize_candidate(donor_module, path, target_binary, signature_bytes)
        if row and (row.get("symbolCount", 0) > 0 or row.get("error")):
            rows.append(row)
    for path in iter_source_paths(roots, source_max_depth, skip_dirs):
        row = summarize_source_candidate(path)
        if row:
            source_rows.append(row)
    rows.sort(
        key=lambda row: (
            -int(row.get("promotableSymbolCount", 0) or 0),
            -int(row.get("symbolCount", 0) or 0),
            row.get("path", ""),
        )
    )
    source_rows.sort(
        key=lambda row: (
            -int(row.get("anchorCount", 0) or 0),
            row.get("path", ""),
        )
    )
    usable = [row for row in rows if row.get("usable") is True]
    have_source = len(source_rows) > 0
    return {
        "schemaVersion": SCHEMA_VERSION,
        "roots": [str(root) for root in roots],
        "targetBinary": str(target_binary),
        "maxDepth": max_depth,
        "sourceMaxDepth": source_max_depth,
        "candidateCount": len(rows),
        "usableCandidateCount": len(usable),
        "candidates": rows,
        "sourceCandidateCount": len(source_rows),
        "sourceCandidates": source_rows,
        "nextStep": (
            "run summarize-ue4ss-package-donor-symbols.py on the top usable donor candidate"
            if usable
            else (
                "build the top source candidate with symbols or locate its Linux linker map/debug ELF containing StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName"
                if have_source
                else "provide an unstripped/symbolized Linux UE donor or linker map containing StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName"
            )
        ),
    }


def markdown(summary):
    lines = ["# UE4SS Package Donor Search", ""]
    lines.append(f"- Roots: `{', '.join(summary['roots'])}`")
    lines.append(f"- Target binary: `{summary['targetBinary']}`")
    lines.append(f"- Max depth: `{summary.get('maxDepth', '')}`")
    lines.append(f"- Source max depth: `{summary.get('sourceMaxDepth', summary.get('maxDepth', ''))}`")
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Usable candidates: `{summary['usableCandidateCount']}`")
    lines.append(f"- Source candidates: `{summary.get('sourceCandidateCount', 0)}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in summary.get("candidates", []):
        lines.append(
            f"- `{row.get('path', '')}` mode=`{row.get('mode', '')}` "
            f"symbols=`{row.get('symbolCount', 0)}` promotable=`{row.get('promotableSymbolCount', 0)}` "
            f"usable=`{str(row.get('usable', False)).lower()}`"
        )
        if row.get("anchorsPresent"):
            lines.append("  - anchors: `" + "`, `".join(row["anchorsPresent"]) + "`")
        if row.get("error"):
            lines.append(f"  - error: {row['error']}")
    if not summary.get("candidates"):
        lines.append("- none")
    lines.append("")
    lines.append("## Source Candidates")
    lines.append("")
    for row in summary.get("sourceCandidates", []):
        lines.append(
            f"- `{row.get('path', '')}` anchors=`{row.get('anchorCount', len(row.get('anchorsPresent', [])))} "
            f"usable=`{str(row.get('usable', False)).lower()}`"
        )
        if row.get("anchorsPresent"):
            lines.append("  - anchors: `" + "`, `".join(row["anchorsPresent"]) + "`")
        if row.get("nextStep"):
            lines.append(f"  - next step: {row['nextStep']}")
    if not summary.get("sourceCandidates"):
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find local symbolized UE donors for package-loading anchor transfer.")
    parser.add_argument("roots", nargs="*", default=["/home/keith", "/opt", "/tmp"])
    parser.add_argument("--target-binary", default="/tmp/dune-live-server-extract/DuneSandboxServer-Linux-Shipping")
    parser.add_argument("--max-depth", type=int, default=6, help="directory depth per root; use -1 for unlimited")
    parser.add_argument("--source-max-depth", type=int, default=None, help="directory depth for source donor discovery; defaults to --max-depth")
    parser.add_argument("--signature-bytes", type=int, default=96)
    parser.add_argument("--include-skip-dir", action="append", default=[])
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    skip_dirs = DEFAULT_SKIP_DIRS - set(args.include_skip_dir)
    summary = search(args.roots, args.target_binary, args.max_depth, args.signature_bytes, skip_dirs, args.source_max_depth)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
