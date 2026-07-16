#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import change_intelligence


def main():
    parser = argparse.ArgumentParser(description="Inspect and verify DASH operational change intelligence")
    parser.add_argument("command", choices=("status", "verify", "metrics", "capsule"))
    parser.add_argument("--incident-key", default="")
    parser.add_argument("--database", default=os.environ.get("DUNE_CHANGE_INTELLIGENCE_HOST_DATABASE", str(ROOT / "backups" / "change-intelligence" / "change-intelligence.sqlite3")))
    parser.add_argument("--policy", default=os.environ.get("DUNE_CHANGE_INTELLIGENCE_HOST_POLICY", str(ROOT / "config" / "change-intelligence.json")))
    parser.add_argument("--secret-file", default=os.environ.get("DUNE_CHANGE_INTELLIGENCE_HOST_HMAC_SECRET_FILE", str(ROOT / "config" / "secrets" / "change-intelligence-hmac.secret")))
    args = parser.parse_args()
    store = change_intelligence.Store(args.database, args.policy, args.secret_file, os.getuid(), os.getgid())
    store.initialize()
    if args.command == "status":
        result = store.status()
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.command == "verify":
        result = store.verify()
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ok") else 1)
    elif args.command == "metrics":
        print(store.prometheus(), end="")
    else:
        if not args.incident_key:
            parser.error("capsule requires --incident-key")
        print(json.dumps(store.capsule(args.incident_key), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
