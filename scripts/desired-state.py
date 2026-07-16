#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import desired_state


def main():
    parser = argparse.ArgumentParser(description="Inspect and verify DASH desired-state attestations")
    parser.add_argument("command", choices=("status", "verify", "metrics"))
    parser.add_argument("--database", default=os.environ.get("DUNE_DESIRED_STATE_HOST_DATABASE", str(ROOT / "backups" / "desired-state" / "desired-state.sqlite3")))
    parser.add_argument("--policy", default=os.environ.get("DUNE_DESIRED_STATE_HOST_POLICY", str(ROOT / "config" / "desired-state.json")))
    parser.add_argument("--secret-file", default=os.environ.get("DUNE_DESIRED_STATE_HOST_HMAC_SECRET_FILE", str(ROOT / "config" / "secrets" / "desired-state-hmac.secret")))
    args = parser.parse_args()
    store = desired_state.Store(args.database, args.policy, args.secret_file, os.getuid(), os.getgid())
    store.initialize()
    if args.command == "status":
        print(json.dumps(store.status(), indent=2, sort_keys=True))
    elif args.command == "verify":
        result = store.verify()
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ok") else 1)
    else:
        print(store.prometheus(), end="")


if __name__ == "__main__":
    main()
