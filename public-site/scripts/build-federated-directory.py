#!/usr/bin/env python3
"""Build a static, verified directory from independently hosted DASH entries."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
for module_root in (pathlib.Path(os.environ.get("DUNE_ROOT", str(ROOT))) / "admin", ROOT / "admin"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
import public_directory  # noqa: E402


def load_sources(path):
    document = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"schemaVersion", "sources"}:
        raise ValueError("directory sources manifest schema is invalid")
    if document.get("schemaVersion") != public_directory.SOURCES_SCHEMA:
        raise ValueError("directory sources manifest version is unsupported")
    rows = document.get("sources")
    if not isinstance(rows, list) or not 1 <= len(rows) <= public_directory.MAX_SOURCES:
        raise ValueError(f"directory sources must contain 1 to {public_directory.MAX_SOURCES} URLs")
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"url"}:
            raise ValueError("every directory source must contain only url")
        normalized.append(public_directory.normalize_https_url(row["url"], "directory source", required=True))
    if len(set(normalized)) != len(normalized):
        raise ValueError("directory source URLs must be unique")
    return normalized


def collect_source(url, timeout, fetcher=public_directory.fetch_entry, now=None):
    document = fetcher(url, timeout=timeout)
    return public_directory.verify_entry(document, expected_url=url, now=now)


def build(sources, timeout=5, workers=8, fetcher=public_directory.fetch_entry, now=None):
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(sources))) as pool:
        futures = {pool.submit(collect_source, url, timeout, fetcher, now): url for url in sources}
        for future, url in [(future, futures[future]) for future in futures]:
            try:
                results.append((url, future.result(), None))
            except Exception as exc:
                results.append((url, None, str(exc)[:500] or exc.__class__.__name__))
    entries = []
    failures = []
    seen = set()
    for url, entry, error in sorted(results, key=lambda row: row[0]):
        if error:
            failures.append({"source": url, "error": error})
            continue
        if entry["serverId"] in seen:
            failures.append({"source": url, "error": "duplicate signed server identity"})
            continue
        seen.add(entry["serverId"])
        entries.append(entry)
    return public_directory.build_catalog(sources, entries, failures, now=now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, help="Signed-entry source manifest")
    parser.add_argument("--output", required=True, help="Output directory.json")
    parser.add_argument("--timeout", type=int, default=5, help="Per-source HTTPS timeout, 1-15 seconds")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent fetches, 1-32")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 15:
        parser.error("--timeout must be from 1 to 15 seconds")
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be from 1 to 32")
    sources = load_sources(args.sources)
    catalog = build(sources, timeout=args.timeout, workers=args.workers)
    public_directory.atomic_json(args.output, catalog)
    print(json.dumps({"ok": True, "output": str(pathlib.Path(args.output)), **catalog["stats"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
