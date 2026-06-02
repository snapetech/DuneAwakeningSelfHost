#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys


DIRECT = re.compile(r"(U[A-Za-z0-9]+CheatManager(?:Extension)?)::([A-Za-z_][A-Za-z0-9_]*)\(")
MANGLED_FRAGMENT = re.compile(
    r"ZN(\d+)(U[A-Za-z0-9]+CheatManager(?:Extension)?)(\d+)([A-Za-z_][A-Za-z0-9_]*)"
)


def strings(path):
    return subprocess.check_output(["strings", "-a", path], text=True, errors="ignore")


def extract_methods(text):
    methods = set()
    for line in text.splitlines():
        for match in DIRECT.finditer(line):
            methods.add(f"{match.group(1)}::{match.group(2)}")
        for match in MANGLED_FRAGMENT.finditer(line):
            class_len = int(match.group(1))
            class_name = match.group(2)
            method_len = int(match.group(3))
            method_blob = match.group(4)
            if len(class_name) != class_len or len(method_blob) < method_len:
                continue
            methods.add(f"{class_name}::{method_blob[:method_len]}")
    return sorted(methods)


def main():
    parser = argparse.ArgumentParser(description="Extract cheat-manager method names from a Dune server binary.")
    parser.add_argument("binary", nargs="?", default="/tmp/ghidra-work/server-bin")
    parser.add_argument("--format", choices=("names", "markdown"), default="names")
    args = parser.parse_args()

    methods = extract_methods(strings(args.binary))
    if args.format == "markdown":
        current_class = None
        for method in methods:
            class_name, method_name = method.split("::", 1)
            if class_name != current_class:
                if current_class is not None:
                    print()
                print(f"### `{class_name}`")
                print()
                current_class = class_name
            print(f"- `{method_name}`")
    else:
        for method in methods:
            print(method)
    print(f"count={len(methods)}", file=sys.stderr)


if __name__ == "__main__":
    main()
