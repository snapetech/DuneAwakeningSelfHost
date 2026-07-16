#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import capacity_intelligence


def main():
    parser = argparse.ArgumentParser(description="Inspect and verify retained DASH capacity evidence")
    parser.add_argument("command", choices=("status", "verify", "metrics", "observe"))
    parser.add_argument("--database", default=os.environ.get("DUNE_CAPACITY_INTELLIGENCE_HOST_DATABASE", str(ROOT / "backups" / "capacity-intelligence" / "capacity.sqlite3")))
    parser.add_argument("--policy", default=os.environ.get("DUNE_CAPACITY_INTELLIGENCE_HOST_POLICY", str(ROOT / "config" / "capacity-intelligence.json")))
    parser.add_argument("--maps", help="JSON file containing a controlled map observation fixture")
    args = parser.parse_args()
    store = capacity_intelligence.Store(args.database, args.policy, os.getuid(), os.getgid())
    store.initialize()
    if args.command == "status":
        print(json.dumps(store.status(), indent=2, sort_keys=True))
    elif args.command == "verify":
        result = store.verify()
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ok") else 1)
    elif args.command == "metrics":
        print(store.prometheus(), end="")
    elif args.command == "observe":
        if not args.maps:
            parser.error("observe requires --maps")
        payload = json.loads(pathlib.Path(args.maps).read_text(encoding="utf-8"))
        print(json.dumps(store.observe(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
