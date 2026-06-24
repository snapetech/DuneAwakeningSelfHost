#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "dune-client-pe-signature-manifest/v1"
DEFAULT_MAX_PATTERNS_PER_SCAN = 256
DEFAULT_MAX_ENV_VALUE_CHARS = 1800
UE_ANCHORS = (
    "FNamePool",
    "NamePoolData",
    "GName",
    "GNames",
    "GUObjectArray",
    "GObjectArray",
    "GObjects",
    "FUObjectArray",
    "GWorld",
    "GEngine",
    "ProcessEvent",
    "StaticFindObject",
    "CallFunctionByNameWithArguments",
    "CallFunctionByName",
    "StaticLoadObject",
    "StaticLoadClass",
    "LoadObject",
    "LoadPackage",
    "ResolveName",
    "LoadAsset",
    "LoadClass",
    "UObject",
    "UFunction",
    "UClass",
    "FProperty",
    "FObjectProperty",
    "FArrayProperty",
    "FBoolProperty",
    "FStructProperty",
    "UStruct",
    "UEnum",
)

UE_ANCHOR_ALIASES = {
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
    "CallFunctionByNameWithArguments": ("callfunctionbynamewitharguments", "uobjectcallfunctionbynamewitharguments"),
    "CallFunctionByName": ("callfunctionbyname",),
    "StaticLoadObject": ("staticloadobject", "loadobjectstatic", "uobjectstaticloadobject"),
    "StaticLoadClass": ("staticloadclass", "loadclassstatic", "uobjectstaticloadclass"),
    "LoadObject": ("loadobject", "uobjectloadobject"),
    "LoadPackage": ("loadpackage", "upackageloadpackage"),
    "ResolveName": ("resolvename", "uresolvename"),
    "LoadAsset": ("loadasset",),
    "LoadClass": ("loadclass",),
    "UObject": ("uobject", "uobjectbase"),
    "UFunction": ("ufunction",),
    "UClass": ("uclass",),
    "FProperty": ("fproperty", "uproperty"),
    "FObjectProperty": ("fobjectproperty",),
    "FArrayProperty": ("farrayproperty",),
    "FBoolProperty": ("fboolproperty",),
    "FStructProperty": ("fstructproperty",),
    "UStruct": ("ustruct",),
    "UEnum": ("uenum",),
}
UE_ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
UE_ANCHOR_GROUP_BY_NAME = {
    anchor: group
    for group, anchors in UE_ANCHOR_GROUPS.items()
    for anchor in anchors
}


def import_script(filename, module_name):
    script = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def safe_id(value, limit=112):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned:
        cleaned = "signature"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 11].rstrip("-._") + "-" + short_hash(value)


def load_validation_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def normalize_anchor_name(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def canonical_anchor_name(value):
    normalized = normalize_anchor_name(value)
    if not normalized or normalized.startswith("selftest"):
        return None
    for canonical in UE_ANCHORS:
        if normalized == normalize_anchor_name(canonical):
            return canonical
    for canonical, aliases in UE_ANCHOR_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def is_loader_source(source):
    normalized = str(source or "").lower().replace("\\", "/")
    loader_needles = (
        "dune_client_probe_loader",
        "dune_server_probe_loader",
        "dune_win_client_probe_loader",
        "linux-client-loader",
        "linux-server-loader",
        "windows-client-loader",
        "libdune_",
    )
    return any(needle in normalized for needle in loader_needles)


def source_provenance(source):
    if not source:
        return "unknown"
    if is_loader_source(source):
        return "loader"
    return "target"


def build_validation(binary, loader_log, xref_json, loader, pid, exe_substrings, categories, names, prefix, suffix, scope, max_matches):
    validator = import_script("validate-client-pe-signatures.py", "validate_client_pe_signatures")
    xrefs = import_script("summarize-client-loader-xrefs.py", "summarize_client_loader_xrefs")
    pe = xrefs.load_pe_image(binary)
    specs = []
    if xref_json:
        specs.extend(
            validator.patterns_from_xref_summary(
                validator.xref_summary_from_json(xref_json),
                categories,
                names,
                max_seeds=0,
            )
        )
    if loader_log:
        pe, xref_summary = validator.xref_summary_from_log(
            binary,
            loader_log,
            loader,
            pid,
            exe_substrings,
            categories,
            names,
            prefix,
            suffix,
        )
        specs.extend(validator.patterns_from_xref_summary(xref_summary, [], [], max_seeds=0))
    if not specs:
        raise ValueError("provide --loader-log or --xref-json")
    rows = validator.validate_patterns(pe, specs, scope, max_matches)
    return validator.summarize(pe, rows, scope)


def entry_from_row(row, index):
    basis = "|".join(
        (
            row.get("category", ""),
            row.get("name", ""),
            row.get("xrefRva", ""),
            row.get("targetRva", ""),
            row.get("expectedFileOffset", ""),
            row.get("pattern", ""),
        )
    )
    prefix = safe_id(f"{row.get('category', 'client')}-{row.get('name', 'signature')}", limit=84)
    ident = safe_id(f"{prefix}-{short_hash(basis)}")
    matches = row.get("matches", [])
    first_match = matches[0] if matches else {}
    return {
        "id": ident,
        "index": index,
        "category": row.get("category", ""),
        "name": row.get("name", ""),
        "status": row.get("status", ""),
        "promotable": bool(row.get("promotable")),
        "pattern": row.get("pattern", ""),
        "length": row.get("length", 0),
        "fixedBytes": row.get("fixedBytes", 0),
        "expectedFileOffset": row.get("expectedFileOffset", ""),
        "expectedRva": first_match.get("rva", "") if first_match.get("expected") else "",
        "xrefRva": row.get("xrefRva", ""),
        "targetRva": row.get("targetRva", ""),
        "source": row.get("source", ""),
        "sourceProvenance": row.get("sourceProvenance") or source_provenance(row.get("source", "")),
    }


def build_entries(validation, promotable_only=True):
    entries = []
    for row in validation.get("patterns", []):
        if promotable_only and not row.get("promotable"):
            continue
        entries.append(entry_from_row(row, len(entries) + 1))
    return entries


def make_manifest(binary, validation, entries, loader_log, xref_json, max_patterns_per_scan, max_env_value_chars):
    binary = binary.resolve()
    return {
        "schemaVersion": SCHEMA,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": "windows-x86_64",
        "binary": {
            "path": str(binary),
            "size": binary.stat().st_size,
            "sha256": sha256_file(binary),
        },
        "source": {
            "loaderLog": str(loader_log) if loader_log else "",
            "xrefJson": str(xref_json) if xref_json else "",
        },
        "runtimeLimits": {
            "maxPatternsPerScan": max_patterns_per_scan,
            "maxSignatureValueChars": max_env_value_chars,
            "loaderEnv": "DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES",
            "signatureFileEnv": "DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE",
            "anchorSignatureEnv": "DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES",
            "anchorSignatureFileEnv": "DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE",
        },
        "validation": {
            "scope": validation.get("scope", ""),
            "patternCount": validation.get("patternCount", 0),
            "promotableCount": validation.get("promotableCount", 0),
            "statusCounts": validation.get("statusCounts", {}),
            "categoryCounts": validation.get("categoryCounts", {}),
        },
        "entryCount": len(entries),
        "entries": entries,
    }


def signature_item(entry):
    return f"{entry['id']}={entry['pattern']}"


def pattern_tokens(entry):
    return [token.lower() for token in entry.get("pattern", "").replace(",", " ").split()]


def tokens_are_wildcards(tokens):
    return bool(tokens) and all(token in ("?", "??") for token in tokens)


def infer_anchor_transform(entry):
    tokens = pattern_tokens(entry)
    if len(tokens) >= 5 and tokens[0] == "e8" and tokens_are_wildcards(tokens[1:5]):
        return "callrel32"
    if len(tokens) >= 7 and tokens[0] in ("40", "44", "48", "4c") and tokens[1] in ("8b", "8d", "89") and tokens_are_wildcards(tokens[3:7]):
        return "riprel32+3"
    if len(tokens) >= 6 and tokens[0] in ("8b", "8d", "89") and tokens_are_wildcards(tokens[2:6]):
        return "riprel32+2"
    return "hit"


def expected_anchor_transforms(anchor):
    group = UE_ANCHOR_GROUP_BY_NAME.get(anchor, "")
    if group in {"names", "objects", "world"}:
        return ("riprel32+3", "riprel32+2")
    if group in {"dispatch", "package"}:
        return ("callrel32",)
    if group == "reflection":
        return ("hit", "riprel32+3", "riprel32+2")
    return ()


def anchor_signature_entries(manifest):
    rows = []
    seen = set()
    for entry in manifest.get("entries", []):
        anchor = canonical_anchor_name(entry.get("name", "")) or canonical_anchor_name(entry.get("id", ""))
        if not anchor or anchor in seen:
            continue
        seen.add(anchor)
        transform = infer_anchor_transform(entry)
        expected = expected_anchor_transforms(anchor)
        rows.append(
            {
                **entry,
                "anchorName": anchor,
                "anchorGroup": UE_ANCHOR_GROUP_BY_NAME.get(anchor, "unknown"),
                "anchorTransform": transform,
                "anchorTransformExpected": bool(expected and transform in expected),
                "anchorTransformExpectedValues": list(expected),
            }
        )
    return rows


def anchor_signature_item(entry):
    transform = entry.get("anchorTransform") or infer_anchor_transform(entry)
    return f"{entry['anchorName']}@{transform}={entry['pattern']}"


def env_chunks(entries, max_patterns_per_scan, max_env_value_chars):
    chunks = []
    current = []
    current_len = 0
    for entry in entries:
        item = signature_item(entry)
        if len(item) > max_env_value_chars:
            raise ValueError(f"signature item exceeds max env value length: {entry['id']}")
        separator = 1 if current else 0
        if current and (
            len(current) >= max_patterns_per_scan or current_len + separator + len(item) > max_env_value_chars
        ):
            chunks.append(current)
            current = []
            current_len = 0
            separator = 0
        current.append(entry)
        current_len += separator + len(item)
    if current:
        chunks.append(current)
    return chunks


def single_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def env_text(manifest):
    limit_patterns = manifest["runtimeLimits"]["maxPatternsPerScan"]
    limit_chars = manifest["runtimeLimits"]["maxSignatureValueChars"]
    chunks = env_chunks(manifest["entries"], limit_patterns, limit_chars)
    lines = []
    lines.append("# Dune Windows/Proton client PE signature scan chunks")
    lines.append("# Set exactly one DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES value per client launch.")
    lines.append(f"# Manifest entries: {manifest['entryCount']}")
    lines.append(f"# Chunks: {len(chunks)}")
    for index, chunk in enumerate(chunks, 1):
        value = ";".join(signature_item(entry) for entry in chunk)
        lines.append("")
        lines.append(f"# chunk {index}/{len(chunks)} patterns={len(chunk)} valueChars={len(value)}")
        lines.append(f"DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES={single_quote(value)}")
    lines.append("")
    return "\n".join(lines)


def signatures_text(manifest):
    lines = []
    lines.append("# Dune Windows/Proton client PE signature file")
    lines.append("# Point DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE at this file.")
    lines.append(f"# Manifest entries: {manifest['entryCount']}")
    for entry in manifest["entries"]:
        lines.append(signature_item(entry))
    lines.append("")
    return "\n".join(lines)


def anchor_signatures_text(manifest):
    entries = anchor_signature_entries(manifest)
    lines = []
    lines.append("# Dune Windows/Proton UE anchor signature file")
    lines.append(f"# Point {manifest['runtimeLimits']['anchorSignatureFileEnv']} at this file.")
    lines.append(f"# Anchor entries: {len(entries)}")
    for entry in entries:
        lines.append(anchor_signature_item(entry))
    lines.append("")
    return "\n".join(lines)


def markdown(manifest, limit):
    lines = []
    lines.append("# Client PE Signature Manifest")
    lines.append("")
    lines.append(f"- Schema: `{manifest['schemaVersion']}`")
    lines.append(f"- Binary SHA256: `{manifest['binary']['sha256']}`")
    lines.append(f"- Entries: `{manifest['entryCount']}`")
    lines.append(f"- Validation promotable: `{manifest['validation']['promotableCount']}`")
    lines.append(f"- Status counts: `{manifest['validation']['statusCounts']}`")
    lines.append("")
    chunks = env_chunks(
        manifest["entries"],
        manifest["runtimeLimits"]["maxPatternsPerScan"],
        manifest["runtimeLimits"]["maxSignatureValueChars"],
    )
    lines.append("## Runtime Chunks")
    lines.append("")
    for index, chunk in enumerate(chunks, 1):
        value_len = len(";".join(signature_item(entry) for entry in chunk))
        lines.append(f"- chunk `{index}` patterns=`{len(chunk)}` valueChars=`{value_len}`")
    if not chunks:
        lines.append("- none")
    lines.append("")
    lines.append("## Entries")
    lines.append("")
    for entry in manifest["entries"][:limit]:
        lines.append(
            f"- `{entry['id']}` category=`{entry['category']}` "
            f"file=`{entry['expectedFileOffset']}` rva=`{entry['expectedRva']}`"
        )
    if manifest["entryCount"] > limit:
        lines.append(f"- ... +{manifest['entryCount'] - limit} more")
    lines.append("")
    return "\n".join(lines)


def render(manifest, output_format, limit):
    if output_format == "json":
        return json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if output_format == "env":
        return env_text(manifest)
    if output_format == "signatures":
        return signatures_text(manifest)
    if output_format == "anchor-signatures":
        return anchor_signatures_text(manifest)
    return markdown(manifest, limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export validated Windows/Proton client PE signature manifests.")
    parser.add_argument("binary", type=Path, help="DuneSandbox-Win64-Shipping.exe or another PE image")
    parser.add_argument("--loader-log", type=Path, help="build validation from this client probe log")
    parser.add_argument("--xref-json", type=Path, help="build validation from xref JSON")
    parser.add_argument("--validation-json", type=Path, help="export from existing validator JSON")
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--signature-prefix", type=int, default=8)
    parser.add_argument("--signature-suffix", type=int, default=16)
    parser.add_argument("--scope", choices=("executable", "all"), default="executable")
    parser.add_argument("--max-matches", type=int, default=16)
    parser.add_argument("--include-non-promotable", action="store_true")
    parser.add_argument("--max-patterns-per-scan", type=int, default=DEFAULT_MAX_PATTERNS_PER_SCAN)
    parser.add_argument("--max-env-value-chars", type=int, default=DEFAULT_MAX_ENV_VALUE_CHARS)
    parser.add_argument("--format", choices=("json", "env", "signatures", "anchor-signatures", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.validation_json:
        validation = load_validation_json(args.validation_json)
    else:
        validation = build_validation(
            args.binary,
            args.loader_log,
            args.xref_json,
            args.loader,
            args.pid,
            args.exe_substring,
            args.category,
            args.name,
            args.signature_prefix,
            args.signature_suffix,
            args.scope,
            args.max_matches,
        )

    entries = build_entries(validation, promotable_only=not args.include_non_promotable)
    manifest = make_manifest(
        args.binary,
        validation,
        entries,
        args.loader_log,
        args.xref_json,
        args.max_patterns_per_scan,
        args.max_env_value_chars,
    )
    text = render(manifest, args.format, args.limit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
