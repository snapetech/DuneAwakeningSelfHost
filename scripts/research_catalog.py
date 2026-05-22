#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "research" / "surfaces.json"
STATUS_ORDER = ["candidate", "loadable", "observable", "validated", "admin-safe"]
CONFIDENCE_ORDER = ["unknown", "low", "moderate", "high"]
REQUIRED_FIELDS = {
    "id",
    "name",
    "kind",
    "scope",
    "status",
    "confidence",
    "risk",
    "restartRequired",
    "surface",
    "evidence",
    "validationProcedure",
    "rollbackProcedure",
}


def load_catalog(path=DEFAULT_CATALOG):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def validate_entry(entry):
    errors = []
    missing = sorted(REQUIRED_FIELDS - set(entry))
    if missing:
        errors.append(f"{entry.get('id', '<missing id>')}: missing fields {', '.join(missing)}")
    if entry.get("status") not in STATUS_ORDER:
        errors.append(f"{entry.get('id', '<missing id>')}: invalid status {entry.get('status')!r}")
    if entry.get("confidence") not in CONFIDENCE_ORDER:
        errors.append(f"{entry.get('id', '<missing id>')}: invalid confidence {entry.get('confidence')!r}")
    if not isinstance(entry.get("evidence"), list) or not entry.get("evidence"):
        errors.append(f"{entry.get('id', '<missing id>')}: evidence must be a non-empty list")
    if not isinstance(entry.get("surface"), dict) or not entry.get("surface"):
        errors.append(f"{entry.get('id', '<missing id>')}: surface must be a non-empty object")
    if entry.get("status") == "admin-safe" and entry.get("risk") == "high" and not entry.get("adminGate"):
        errors.append(f"{entry.get('id', '<missing id>')}: high-risk admin-safe entries require adminGate")
    return errors


def validate_catalog(catalog):
    errors = []
    if catalog.get("evidenceLevels") != STATUS_ORDER:
        errors.append("catalog evidenceLevels must match promotion order")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("catalog entries must be a non-empty list")
        return errors
    seen = set()
    for entry in entries:
        entry_id = entry.get("id")
        if entry_id in seen:
            errors.append(f"duplicate entry id {entry_id}")
        seen.add(entry_id)
        errors.extend(validate_entry(entry))
    return errors


def status_at_least(status, minimum):
    return STATUS_ORDER.index(status) >= STATUS_ORDER.index(minimum)


def promotion_blockers(entry, target):
    blockers = []
    current = entry.get("status")
    if current not in STATUS_ORDER or target not in STATUS_ORDER:
        return ["invalid status or target"]
    if status_at_least(current, target):
        return []
    if target in ("loadable", "observable", "validated", "admin-safe"):
        if "validationProcedure" not in entry or not entry["validationProcedure"]:
            blockers.append("missing validation procedure")
    if target in ("observable", "validated", "admin-safe"):
        if len(entry.get("evidence", [])) < 2:
            blockers.append("needs at least two independent evidence notes")
    if target in ("validated", "admin-safe"):
        if entry.get("confidence") in ("unknown", "low"):
            blockers.append("confidence must be moderate or high")
    if target == "admin-safe":
        if entry.get("rollbackProcedure") in ("", "No rollback"):
            blockers.append("missing rollback procedure")
        if entry.get("risk") == "high" and not entry.get("adminGate"):
            blockers.append("high-risk admin-safe surfaces need an explicit adminGate")
    return blockers


def render_markdown(catalog):
    lines = [
        "# Reverse Engineering Surface Catalog",
        "",
        "Generated from `research/surfaces.json`.",
        "",
        "| ID | Kind | Scope | Status | Confidence | Risk | Restart |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in sorted(catalog["entries"], key=lambda item: item["id"]):
        restart = "yes" if entry["restartRequired"] else "no"
        lines.append(
            f"| `{entry['id']}` | {entry['kind']} | {entry['scope']} | {entry['status']} | "
            f"{entry['confidence']} | {entry['risk']} | {restart} |"
        )
    lines.append("")
    for entry in sorted(catalog["entries"], key=lambda item: item["id"]):
        lines.extend([
            f"## {entry['name']}",
            "",
            f"- ID: `{entry['id']}`",
            f"- Status: `{entry['status']}`; confidence: `{entry['confidence']}`; risk: `{entry['risk']}`",
            f"- Surface: `{json.dumps(entry['surface'], sort_keys=True)}`",
            f"- Validation: {entry['validationProcedure']}",
            f"- Rollback: {entry['rollbackProcedure']}",
            "- Evidence:",
        ])
        for evidence in entry["evidence"]:
            lines.append(f"  - {evidence}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate and render the reverse-engineering surface catalog.")
    parser.add_argument("--catalog", type=pathlib.Path, default=DEFAULT_CATALOG)
    parser.add_argument("--format", choices=("json", "markdown", "ids"), default="json")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--status")
    parser.add_argument("--kind")
    parser.add_argument("--min-status")
    parser.add_argument("--promotion-target", choices=STATUS_ORDER)
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    errors = validate_catalog(catalog)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
        raise SystemExit(1)
    if args.validate:
        print(json.dumps({"ok": True, "entries": len(catalog["entries"])}, indent=2))
        return
    entries = catalog["entries"]
    if args.status:
        entries = [entry for entry in entries if entry["status"] == args.status]
    if args.kind:
        entries = [entry for entry in entries if entry["kind"] == args.kind]
    if args.min_status:
        entries = [entry for entry in entries if status_at_least(entry["status"], args.min_status)]
    output_catalog = {**catalog, "entries": entries}
    if args.promotion_target:
        result = {
            entry["id"]: promotion_blockers(entry, args.promotion_target)
            for entry in entries
        }
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(output_catalog))
    elif args.format == "ids":
        for entry in entries:
            print(entry["id"])
    else:
        print(json.dumps(output_catalog, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
