#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


SCHEMA_VERSION = "dune-ue-vtable-candidates/v1"
DEFAULT_HEURISTIC_SLOTS = (64, 65, 66, 67, 68)


def parse_int(value, default=0):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def parse_log_fields(line):
    fields = {}
    for token in line.strip().split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    return fields


def target_key(fields):
    stable_offset = fields.get("imageOffset") or fields.get("rva") or ""
    module = fields.get("module") or fields.get("map") or ""
    if stable_offset:
        return f"{module}|{stable_offset}"
    return fields.get("target", "")


def target_record(fields, count):
    record = {
        "key": target_key(fields),
        "count": count,
        "target": fields.get("target", ""),
        "targetName": fields.get("targetName", ""),
        "targetSource": fields.get("targetSource", ""),
        "map": fields.get("map", ""),
        "module": fields.get("module", ""),
        "imageOffset": fields.get("imageOffset", ""),
        "rva": fields.get("rva", ""),
        "fileOffset": fields.get("fileOffset", ""),
        "perms": fields.get("perms", ""),
        "protect": fields.get("protect", ""),
    }
    return {key: value for key, value in record.items() if value != ""}


def counter_top(counter, limit):
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


class VtableCandidateSummary:
    def __init__(self):
        self.candidate_count = 0
        self.scan_count = 0
        self.scan_status_counts = Counter()
        self.scan_slot_totals = Counter()
        self.slot_counts = Counter()
        self.slot_target_counts = defaultdict(Counter)
        self.slot_target_examples = {}
        self.slot_class_counts = defaultdict(Counter)
        self.slot_name_counts = defaultdict(Counter)
        self.slot_vtable_counts = defaultdict(Counter)
        self.target_counts = Counter()
        self.target_examples = {}
        self.platform_counts = Counter()

    def add_scan(self, fields):
        self.scan_count += 1
        self.scan_status_counts[fields.get("status", "unknown")] += 1
        for key in ("readableSlots", "executableSlots", "nonExecutableSlots", "zeroSlots", "unreadableSlots"):
            if key in fields:
                self.scan_slot_totals[key] += parse_int(fields[key])
        platform = fields.get("platform")
        if platform:
            self.platform_counts[platform] += 1

    def add_candidate(self, fields):
        self.candidate_count += 1
        slot = parse_int(fields.get("slot"), None)
        if slot is None:
            return
        key = target_key(fields)
        self.slot_counts[slot] += 1
        self.slot_target_counts[slot][key] += 1
        self.slot_target_examples.setdefault((slot, key), dict(fields))
        self.target_counts[key] += 1
        self.target_examples.setdefault(key, dict(fields))
        if fields.get("className"):
            self.slot_class_counts[slot][fields["className"]] += 1
        if fields.get("objectName"):
            self.slot_name_counts[slot][fields["objectName"]] += 1
        if fields.get("vtable"):
            self.slot_vtable_counts[slot][fields["vtable"]] += 1
        platform = fields.get("platform")
        if platform:
            self.platform_counts[platform] += 1

    def ranked_slots(self, heuristic_slots, limit):
        total_scanned_objects = max(self.scan_status_counts.get("scanned", 0), 1)
        ranked = []
        for slot, count in self.slot_counts.items():
            top_key, top_count = self.slot_target_counts[slot].most_common(1)[0]
            unique_targets = len(self.slot_target_counts[slot])
            unique_vtables = len(self.slot_vtable_counts[slot])
            coverage = count / total_scanned_objects
            stability = top_count / count if count else 0
            heuristic_bonus = 0.25 if slot in heuristic_slots else 0
            score = coverage + stability + min(unique_vtables, 256) / 256 + heuristic_bonus
            reasons = []
            if slot in heuristic_slots:
                reasons.append("ue4-uobject-process-event-slot-heuristic")
            if coverage >= 0.90:
                reasons.append("present-on-most-scanned-objects")
            if stability >= 0.75:
                reasons.append("stable-target-for-slot")
            if unique_vtables > 1:
                reasons.append("observed-across-multiple-vtables")
            ranked.append(
                {
                    "slot": slot,
                    "score": round(score, 6),
                    "candidateCount": count,
                    "objectCoverage": round(coverage, 6),
                    "topTargetShare": round(stability, 6),
                    "uniqueTargets": unique_targets,
                    "uniqueClasses": len(self.slot_class_counts[slot]),
                    "uniqueObjectNames": len(self.slot_name_counts[slot]),
                    "uniqueVtables": unique_vtables,
                    "topTarget": target_record(self.slot_target_examples[(slot, top_key)], top_count),
                    "topClasses": counter_top(self.slot_class_counts[slot], 6),
                    "topObjectNames": counter_top(self.slot_name_counts[slot], 6),
                    "reasons": reasons,
                }
            )
        ranked.sort(key=lambda row: (-row["score"], -row["candidateCount"], row["slot"]))
        return ranked[:limit]

    def to_dict(self, heuristic_slots, limit):
        ranked = self.ranked_slots(set(heuristic_slots), limit)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "candidateCount": self.candidate_count,
            "scanCount": self.scan_count,
            "scanStatusCounts": dict(sorted(self.scan_status_counts.items())),
            "scanSlotTotals": dict(sorted(self.scan_slot_totals.items())),
            "slotCount": len(self.slot_counts),
            "targetCount": len(self.target_counts),
            "platformCounts": dict(sorted(self.platform_counts.items())),
            "heuristicSlots": list(heuristic_slots),
            "rankedSlots": ranked,
            "hookProbeShortlist": ranked[: min(10, len(ranked))],
        }


def summarize(paths, heuristic_slots, limit):
    summary = VtableCandidateSummary()
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "event=ue-process-event-vtable-" not in line:
                    continue
                fields = parse_log_fields(line)
                event = fields.get("event")
                if event == "ue-process-event-vtable-scan":
                    summary.add_scan(fields)
                elif event == "ue-process-event-vtable-candidate":
                    summary.add_candidate(fields)
    return summary.to_dict(heuristic_slots, limit)


def markdown_table(rows):
    lines = [
        "| Rank | Slot | Score | Candidates | Coverage | Top Target Share | Unique Targets | Unique Vtables | Stable Offset | Reasons |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for index, row in enumerate(rows, 1):
        target = row.get("topTarget", {})
        offset = target.get("imageOffset") or target.get("rva") or target.get("target", "")
        reasons = ", ".join(row.get("reasons", []))
        lines.append(
            "| {rank} | {slot} | {score:.3f} | {count} | {coverage:.3f} | {share:.3f} | {targets} | {vtables} | `{offset}` | {reasons} |".format(
                rank=index,
                slot=row["slot"],
                score=row["score"],
                count=row["candidateCount"],
                coverage=row["objectCoverage"],
                share=row["topTargetShare"],
                targets=row["uniqueTargets"],
                vtables=row["uniqueVtables"],
                offset=offset,
                reasons=reasons,
            )
        )
    return "\n".join(lines)


def emit_markdown(data, output):
    output.write(f"# UE VTable Candidate Summary\n\n")
    output.write(f"- Schema: `{data['schemaVersion']}`\n")
    output.write(f"- Candidate rows: {data['candidateCount']}\n")
    output.write(f"- Object scan rows: {data['scanCount']}\n")
    output.write(f"- Slots with candidates: {data['slotCount']}\n")
    output.write(f"- Unique targets: {data['targetCount']}\n")
    output.write(f"- Scan statuses: `{json.dumps(data['scanStatusCounts'], sort_keys=True)}`\n\n")
    output.write("## Hook Probe Shortlist\n\n")
    output.write(markdown_table(data["hookProbeShortlist"]))
    output.write("\n\n## Ranked Slots\n\n")
    output.write(markdown_table(data["rankedSlots"]))
    output.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Rank UE UObject vtable candidate rows emitted by the server/Linux-client/Windows-client loaders."
    )
    parser.add_argument("logs", nargs="+", type=Path, help="loader log files to summarize")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--limit", type=int, default=32, help="ranked slot rows to emit")
    parser.add_argument(
        "--heuristic-slot",
        action="append",
        type=lambda value: parse_int(value),
        default=[],
        help="slot to tag as a UE4 ProcessEvent heuristic candidate; repeatable",
    )
    args = parser.parse_args(argv)

    heuristic_slots = args.heuristic_slot or list(DEFAULT_HEURISTIC_SLOTS)
    data = summarize(args.logs, heuristic_slots, args.limit)
    if args.format == "json":
        json.dump(data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        emit_markdown(data, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
