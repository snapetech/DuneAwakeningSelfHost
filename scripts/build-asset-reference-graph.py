#!/usr/bin/env python3
import argparse
import json
import pathlib
import re


ASSET_RE = re.compile(r"(/Game/[A-Za-z0-9_./-]+)")
INI_SECTION_RE = re.compile(r"^\[([^]]+)\]")
INI_KV_RE = re.compile(r"^([^=;#][^=]*)=(.*)$")


def add_edge(edges, source, relation, target, evidence):
    edges.append({"source": source, "relation": relation, "target": target, "evidence": evidence})


def scan_ini(path, edges):
    current = ""
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        section = INI_SECTION_RE.match(raw.strip())
        if section:
            current = section.group(1)
            continue
        kv = INI_KV_RE.match(raw.strip())
        if not kv:
            continue
        key = kv.group(1).strip()
        value = kv.group(2).strip()
        for asset in ASSET_RE.findall(value):
            add_edge(edges, f"ini:{current}:{key}", "references", asset, f"{path}:{lineno}")


def scan_text(path, prefix, edges):
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for asset in ASSET_RE.findall(raw):
            add_edge(edges, f"{prefix}:{path.name}", "mentions", asset, f"{path}:{lineno}")


def main():
    parser = argparse.ArgumentParser(description="Build a lightweight asset reference graph from INI/text/log evidence.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    edges = []
    for path in args.paths:
        if path.is_dir():
            candidates = sorted(item for item in path.rglob("*") if item.is_file())
        else:
            candidates = [path]
        for candidate in candidates:
            suffix = candidate.suffix.lower()
            if suffix in {".ini", ".txt"} or "config" in candidate.name.lower():
                scan_ini(candidate, edges)
            else:
                scan_text(candidate, "text", edges)
    nodes = sorted({edge["source"] for edge in edges} | {edge["target"] for edge in edges})
    result = {"ok": True, "nodes": nodes, "edges": edges}
    if args.format == "markdown":
        lines = ["# Asset Reference Graph", "", "| Source | Relation | Target | Evidence |", "| --- | --- | --- | --- |"]
        for edge in edges:
            lines.append(f"| `{edge['source']}` | {edge['relation']} | `{edge['target']}` | `{edge['evidence']}` |")
        output = "\n".join(lines)
    else:
        output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
