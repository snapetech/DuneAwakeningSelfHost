#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "research" / "surfaces"
VALID_STATUS = {"candidate", "loadable", "observable", "validated", "admin-safe"}
VALID_CONFIDENCE = {"unknown", "low", "moderate", "high"}
VALID_RISK = {"low", "medium", "high"}


def load_jsonl(path):
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid json: {exc}") from exc
        row["_sourceFile"] = str(path.relative_to(ROOT))
        row["_sourceLine"] = lineno
        rows.append(row)
    return rows


def load_surfaces(surface_dir):
    rows = []
    for path in sorted(pathlib.Path(surface_dir).glob("*.jsonl")):
        rows.extend(load_jsonl(path))
    return rows


def validate(rows):
    required = {"id", "build", "surface", "scope", "name", "status", "confidence", "risk", "evidence", "validated"}
    errors = []
    seen = set()
    for row in rows:
        label = f"{row.get('_sourceFile')}:{row.get('_sourceLine')}"
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
        if row.get("id") in seen:
            errors.append(f"{label}: duplicate id {row.get('id')}")
        seen.add(row.get("id"))
        if row.get("status") not in VALID_STATUS:
            errors.append(f"{label}: invalid status {row.get('status')!r}")
        if row.get("confidence") not in VALID_CONFIDENCE:
            errors.append(f"{label}: invalid confidence {row.get('confidence')!r}")
        if row.get("risk") not in VALID_RISK:
            errors.append(f"{label}: invalid risk {row.get('risk')!r}")
        if not isinstance(row.get("evidence"), list) or not row.get("evidence"):
            errors.append(f"{label}: evidence must be a non-empty array")
    return errors


def render_markdown(rows):
    lines = [
        "# Surface Ledger",
        "",
        "Generated from `research/surfaces/*.jsonl`.",
        "",
        "| ID | Build | Surface | Scope | Status | Confidence | Risk | Validated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda item: item["id"]):
        lines.append(
            f"| `{row['id']}` | `{row['build']}` | {row['surface']} | {row['scope']} | "
            f"{row['status']} | {row['confidence']} | {row['risk']} | {str(row['validated']).lower()} |"
        )
    lines.append("")
    for row in sorted(rows, key=lambda item: item["id"]):
        lines.extend([
            f"## {row['name']}",
            "",
            f"- ID: `{row['id']}`",
            f"- Build: `{row['build']}`",
            f"- Surface: `{row['surface']}`; scope: `{row['scope']}`",
            f"- Status: `{row['status']}`; confidence: `{row['confidence']}`; risk: `{row['risk']}`",
        ])
        if row.get("section") or row.get("key"):
            lines.append(f"- Config: section `{row.get('section', '')}`, key `{row.get('key', '')}`")
        if row.get("function"):
            lines.append(f"- Function: `{row['function']}`")
        if row.get("validationProcedure"):
            lines.append(f"- Validation: {row['validationProcedure']}")
        if row.get("rollbackProcedure"):
            lines.append(f"- Rollback: {row['rollbackProcedure']}")
        lines.append("- Evidence:")
        for evidence in row["evidence"]:
            lines.append(f"  - {evidence}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate and render machine-readable research surface JSONL.")
    parser.add_argument("--surface-dir", type=pathlib.Path, default=DEFAULT_DIR)
    parser.add_argument("--format", choices=("json", "markdown", "ids"), default="json")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    rows = load_surfaces(args.surface_dir)
    errors = validate(rows)
    if errors:
      print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
      raise SystemExit(1)
    if args.validate:
        output = json.dumps({"ok": True, "surfaces": len(rows)}, indent=2)
    elif args.format == "markdown":
        output = render_markdown(rows)
    elif args.format == "ids":
        output = "\n".join(row["id"] for row in sorted(rows, key=lambda item: item["id"]))
    else:
        output = json.dumps({"ok": True, "surfaces": rows}, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
