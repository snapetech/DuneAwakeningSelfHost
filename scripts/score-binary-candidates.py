#!/usr/bin/env python3
import argparse
import json
import pathlib
import re


POSITIVE = [
    (5, re.compile(r"_Key$"), "has _Key companion shape"),
    (5, re.compile(r"(Config|Settings|Subsystem|DeveloperSettings)", re.I), "near config/settings class naming"),
    (3, re.compile(r"^(m_b|b[A-Z]|.*(Multiplier|Rate|Seconds|Limit|Enabled|Chance|MinMax|Override|Count).*)$"), "scalar/operator knob shape"),
    (2, re.compile(r"(Spice|SandStorm|Treasure|Crash|Ship|Encounter|Resource|Respawn|Landclaim|Buildable)", re.I), "server-behavior noun"),
]
NEGATIVE = [
    (-5, re.compile(r"(Widget|UI|HUD|Material|Texture|Niagara|Camera|Audio|Sound|Anim|Montage)", re.I), "asset/ui/client naming"),
    (-4, re.compile(r"(^|_)(Component|Actor|Pawn|Controller|Instance|Transient)($|_)", re.I), "runtime object naming"),
    (-3, re.compile(r"^[/A-Za-z0-9_]+\\.(uasset|umap)$", re.I), "asset file path"),
]


def score(text):
    reasons = []
    value = 0
    for points, pattern, reason in POSITIVE + NEGATIVE:
        if pattern.search(text):
            value += points
            reasons.append({"points": points, "reason": reason})
    if value >= 8:
        tier = "A"
    elif value >= 4:
        tier = "B"
    elif value >= 1:
        tier = "C"
    else:
        tier = "D"
    return value, tier, reasons


def iter_strings(path):
    for raw in pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        text = raw.strip()
        if text:
            yield text


def main():
    parser = argparse.ArgumentParser(description="Rank binary string candidates for config/knob discovery.")
    parser.add_argument("strings_file", type=pathlib.Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--limit", type=int, default=250)
    args = parser.parse_args()

    rows = []
    for text in iter_strings(args.strings_file):
        value, tier, reasons = score(text)
        rows.append({"string": text, "score": value, "tier": tier, "reasons": reasons})
    rows.sort(key=lambda item: (-item["score"], item["string"]))
    rows = rows[:args.limit]
    if args.format == "markdown":
        lines = [
            "# Binary Candidate Scores",
            "",
            "| Tier | Score | String | Reasons |",
            "| --- | ---: | --- | --- |",
        ]
        for row in rows:
            reason_text = "; ".join(reason["reason"] for reason in row["reasons"])
            safe = row["string"].replace("|", "\\|")
            lines.append(f"| {row['tier']} | {row['score']} | `{safe}` | {reason_text} |")
        output = "\n".join(lines)
    else:
        output = json.dumps({"ok": True, "candidates": rows}, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
