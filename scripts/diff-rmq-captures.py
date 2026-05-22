#!/usr/bin/env python3
import argparse
import json
import pathlib


def load(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def key_item(item, fields):
    return tuple(str(item.get(field, "")) for field in fields)


def diff_list(before, after, fields):
    before_map = {key_item(item, fields): item for item in before or []}
    after_map = {key_item(item, fields): item for item in after or []}
    added = [after_map[key] for key in sorted(set(after_map) - set(before_map))]
    removed = [before_map[key] for key in sorted(set(before_map) - set(after_map))]
    changed = []
    for key in sorted(set(before_map) & set(after_map)):
        if before_map[key] != after_map[key]:
            changed.append({"key": key, "before": before_map[key], "after": after_map[key]})
    return {"added": added, "removed": removed, "changed": changed}


def diff_capture(before_path, after_path):
    before = load(before_path)
    after = load(after_path)
    return {
        "exchanges": diff_list(before.get("exchanges"), after.get("exchanges"), ("vhost", "name")),
        "queues": diff_list(before.get("queues"), after.get("queues"), ("vhost", "name")),
        "bindings": diff_list(before.get("bindings"), after.get("bindings"), ("vhost", "source", "destination", "destination_type", "routing_key")),
        "consumers": diff_list(before.get("consumers"), after.get("consumers"), ("consumer_tag",)),
    }


def render_markdown(result):
    lines = ["# RabbitMQ Topology Diff", ""]
    for section, diff in result.items():
        lines.extend([f"## {section}", ""])
        for kind in ("added", "removed", "changed"):
            rows = diff[kind]
            lines.append(f"- {kind}: {len(rows)}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Diff RabbitMQ topology snapshots captured before/after an observation window.")
    parser.add_argument("before", type=pathlib.Path)
    parser.add_argument("after", type=pathlib.Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    result = diff_capture(args.before, args.after)
    output = json.dumps({"ok": True, "diff": result}, indent=2, sort_keys=True) if args.format == "json" else render_markdown(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
