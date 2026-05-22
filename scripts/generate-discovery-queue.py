#!/usr/bin/env python3
import argparse
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDER = ["candidate", "loadable", "observable", "validated", "admin-safe"]


def load_jsonl(path):
    rows = []
    for file in sorted(path.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                rows.append(json.loads(line))
    return rows


def bucket(row):
    if row["status"] in ("validated", "admin-safe") and row.get("validated"):
        return "ready-or-promoted"
    if row["surface"] == "binary-candidate":
        return "needs-startup-parse-test"
    if row["surface"] in ("rmq-command", "server-command"):
        return "needs-contract-capture"
    if row["status"] in ("loadable", "observable"):
        return "needs-runtime-effect-test"
    return "needs-triage"


def main():
    parser = argparse.ArgumentParser(description="Generate a discovery promotion queue from JSONL surfaces.")
    parser.add_argument("--surface-dir", type=pathlib.Path, default=ROOT / "research" / "surfaces")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    rows = load_jsonl(args.surface_dir)
    buckets = {}
    for row in rows:
        buckets.setdefault(bucket(row), []).append(row)
    lines = ["# Discovery Queue", "", "Generated from `research/surfaces/*.jsonl`.", ""]
    for name in sorted(buckets):
        lines.extend([f"## {name}", ""])
        for row in sorted(buckets[name], key=lambda item: (ORDER.index(item["status"]), item["id"])):
            lines.append(f"- `{row['id']}`: {row['name']} ({row['status']}, {row['confidence']}, risk {row['risk']})")
        lines.append("")
    output = "\n".join(lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
