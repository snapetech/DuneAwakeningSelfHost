#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib


def file_hash(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def inventory(root):
    root = pathlib.Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            result[rel] = {"sha256": file_hash(path), "bytes": path.stat().st_size}
    return result


def main():
    parser = argparse.ArgumentParser(description="Diff two generated build surface ledgers by file hash.")
    parser.add_argument("old", type=pathlib.Path)
    parser.add_argument("new", type=pathlib.Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    old = inventory(args.old)
    new = inventory(args.new)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(path for path in set(old) & set(new) if old[path]["sha256"] != new[path]["sha256"])
    result = {"ok": True, "old": str(args.old), "new": str(args.new), "added": added, "removed": removed, "changed": changed}
    if args.format == "json":
        output = json.dumps(result, indent=2, sort_keys=True)
    else:
        lines = [
            "# Build Surface Diff",
            "",
            f"- Old: `{args.old}`",
            f"- New: `{args.new}`",
            f"- Added: {len(added)}",
            f"- Removed: {len(removed)}",
            f"- Changed: {len(changed)}",
            "",
        ]
        for title, rows in (("Added", added), ("Removed", removed), ("Changed", changed)):
            lines.extend([f"## {title}", ""])
            lines.extend(f"- `{row}`" for row in rows)
            lines.append("")
        output = "\n".join(lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
