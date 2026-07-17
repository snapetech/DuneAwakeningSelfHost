#!/usr/bin/env python3
"""CLI for locked, inode-preserving dotenv updates."""

from __future__ import annotations

import argparse
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import env_file_store  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update an existing dotenv file without replacing its bind-mounted inode."
    )
    parser.add_argument("env_file", type=pathlib.Path)
    parser.add_argument(
        "--set", dest="updates", action="append", nargs=2, metavar=("KEY", "VALUE"), required=True,
        help="set one key; repeat to update multiple keys under one lock",
    )
    parser.add_argument("--max-bytes", type=int, default=env_file_store.DEFAULT_MAX_BYTES)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = env_file_store.update_values(args.env_file, args.updates, max_bytes=args.max_bytes)
    except (env_file_store.EnvFileError, OSError) as exc:
        print(f"env update refused: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        state = "updated" if result["changed"] else "unchanged"
        print(
            f"{state} {args.env_file}: keys={result['keys']} bytes={result['bytes']} "
            f"inode={result['device']}:{result['inode']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
