#!/usr/bin/env python3
import argparse
import json
import pathlib
import re


PATTERNS = {
    "coriolis": re.compile(r"coriolis", re.I),
    "sandstorm": re.compile(r"sandstorm", re.I),
    "spice": re.compile(r"spice", re.I),
    "travel": re.compile(r"TravelDestination|TravelTo|LogTravel", re.I),
    "rabbitmq": re.compile(r"rabbit|amqp|queue|routing", re.I),
    "command": re.compile(r"ServerCommand|AdminLogin|Cheat|GM|PrintAllowedCommands|PrintPos", re.I),
    "config": re.compile(r"config|ini|cvar|console variable", re.I),
    "error": re.compile(r"error|warning|failed|fatal", re.I),
}
REDACTIONS = (
    (re.compile(r"ServiceAuthToken=[^\s]+"), "ServiceAuthToken=<redacted>"),
    (re.compile(r"ServerLoginPasswordSecret=\"[^\"]+\""), "ServerLoginPasswordSecret=\"<redacted>\""),
    (re.compile(r"UsernameServerLoginSecret=\"[^\"]+\""), "UsernameServerLoginSecret=\"<redacted>\""),
    (re.compile(r"Password=[^\s]+", re.I), "Password=<redacted>"),
)


def redact(text):
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def classify(path):
    counts = {name: 0 for name in PATTERNS}
    examples = {name: [] for name in PATTERNS}
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                counts[name] += 1
                if len(examples[name]) < 5:
                    examples[name].append({"line": lineno, "text": redact(line)[:500]})
    return {"path": str(path), "counts": counts, "examples": examples}


def main():
    parser = argparse.ArgumentParser(description="Build a subsystem-oriented index of server logs.")
    parser.add_argument("paths", nargs="*", default=["data/server-saved/Logs"])
    args = parser.parse_args()
    files = []
    for raw in args.paths:
        path = pathlib.Path(raw)
        if path.is_dir():
            files.extend(sorted(path.glob("*.log")))
        elif path.exists():
            files.append(path)
    print(json.dumps({"ok": True, "files": [classify(path) for path in files]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
