#!/usr/bin/env python3
import argparse
import json
import pathlib
import re


READ_RE = re.compile(r"^(get|load|fetch|inspect|list|retrieve|find|search|debug_get)_", re.I)
WRITE_RE = re.compile(r"^(update|save|create|delete|remove|reset|upsert|insert|record|set|mark|admin_move)_", re.I)
DANGEROUS_RE = re.compile(r"(wipe|force|destroy|nuke|complete|end|purge|delete_all|cleanup|reset_global)", re.I)
ADMIN_RE = re.compile(r"(admin|debug|gm|cheat)", re.I)


def classify(name):
    labels = []
    if READ_RE.search(name):
        labels.append("read-only")
    if WRITE_RE.search(name):
        labels.append("state-write")
    if DANGEROUS_RE.search(name):
        labels.append("dangerous")
    if ADMIN_RE.search(name):
        labels.append("admin-looking")
    return labels or ["unknown"]


def load_surface(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return data.get("functions", [])


def render_markdown(rows):
    lines = [
        "# DB Function Surface Index",
        "",
        "Generated from DB surface JSON.",
        "",
        "| Function | Class | Args | Returns |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        name = row["name"]
        labels = ", ".join(row["classes"])
        lines.append(f"| `{row['schema']}.{name}` | {labels} | `{row.get('args', '')}` | `{row.get('returns', '')}` |")
    return "\n".join(lines)


def render_matrix(rows):
    lines = [
        "# DB Function Coverage Matrix",
        "",
        "Generated from DB surface JSON. Coverage fields default to `unknown` until a fixture or admin endpoint proves them.",
        "",
        "| Function | Class | Endpoint Coverage | Dry Run | Rollback | Fixture |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        labels = ", ".join(row["classes"])
        lines.append(
            f"| `{row['schema']}.{row['name']}` | {labels} | {row['existingEndpointCoverage']} | "
            f"{row['dryRunSupport']} | {row['rollbackKnown']} | {row['fixtureCoverage']} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Classify dune.* DB functions from scripts/research/dump-db-surface.py output.")
    parser.add_argument("db_surface_json", type=pathlib.Path)
    parser.add_argument("--format", choices=("json", "markdown", "matrix-markdown"), default="json")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    rows = []
    for func in load_surface(args.db_surface_json):
        row = dict(func)
        row["classes"] = classify(row["name"])
        row["existingEndpointCoverage"] = "unknown"
        row["dryRunSupport"] = "unknown"
        row["rollbackKnown"] = "unknown"
        row["fixtureCoverage"] = "unknown"
        rows.append(row)
    rows.sort(key=lambda item: (item.get("schema", ""), item.get("name", ""), item.get("args", "")))
    if args.format == "markdown":
        output = render_markdown(rows)
    elif args.format == "matrix-markdown":
        output = render_matrix(rows)
    else:
        output = json.dumps({"ok": True, "functions": rows}, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
