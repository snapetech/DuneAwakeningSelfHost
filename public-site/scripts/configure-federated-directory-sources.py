#!/usr/bin/env python3
"""Atomically configure the reviewed sources for a DASH public directory."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
for module_root in (pathlib.Path(os.environ.get("DUNE_ROOT", str(ROOT))) / "admin", ROOT / "admin"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
import public_directory  # noqa: E402


def configure(output, sources, replace=False):
    path = pathlib.Path(output)
    if not path.is_absolute():
        raise ValueError("directory source manifest path must be absolute")
    if path.exists() and not replace:
        raise FileExistsError(f"directory source manifest already exists: {path}; pass --replace after review")
    if not 1 <= len(sources) <= public_directory.MAX_SOURCES:
        raise ValueError(f"directory sources must contain 1 to {public_directory.MAX_SOURCES} URLs")
    normalized = [public_directory.normalize_https_url(value, "directory source", required=True) for value in sources]
    if len(set(normalized)) != len(normalized):
        raise ValueError("directory source URLs must be unique")
    document = {
        "schemaVersion": public_directory.SOURCES_SCHEMA,
        "sources": [{"url": value} for value in normalized],
    }
    public_directory.atomic_json(path, document, mode=0o644)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/etc/dash-directory-sources.json", help="Absolute manifest path")
    parser.add_argument("--source", action="append", required=True, help="Reviewed public HTTPS descriptor URL; repeat for each server")
    parser.add_argument("--replace", action="store_true", help="Atomically replace an existing manifest")
    args = parser.parse_args(argv)
    try:
        document = configure(args.output, args.source, replace=args.replace)
    except (FileExistsError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"ok": True, "output": args.output, "sources": len(document["sources"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
