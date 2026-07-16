#!/usr/bin/env python3
"""Inspect, verify, export, or feed the DASH operational SLO ledger."""

import argparse
import json
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import operational_slo


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=os.environ.get("DUNE_OPERATIONAL_SLO_DATABASE", str(ROOT / "backups" / "operational-slo" / "slo.sqlite3")))
    parser.add_argument("--policy", default=os.environ.get("DUNE_OPERATIONAL_SLO_POLICY", str(ROOT / "config" / "operational-slo.json")))
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Print the retained SLO/error-budget status")
    status.add_argument("--limit", type=int, default=100)
    sub.add_parser("verify", help="Verify SQLite integrity and the incident-event hash chain")
    sub.add_parser("metrics", help="Print Prometheus exposition text")
    record = sub.add_parser("record", help="Record explicit signals from a reviewed JSON file or stdin")
    record.add_argument("--signals", required=True, help="JSON file containing a signal object, or - for stdin")
    record.add_argument("--context", help="Optional JSON context file, or - for stdin when signals uses a file")
    record.add_argument("--observed-at", type=float)
    return parser


def read_json(path):
    if path == "-":
        return json.load(sys.stdin)
    with pathlib.Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    args = build_parser().parse_args(argv)
    ledger = operational_slo.Store(args.database, args.policy, owner_uid=os.getuid(), owner_gid=os.getgid())
    ledger.initialize()
    if args.command == "status":
        payload = ledger.status(limit=args.limit)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["overall"] in ("healthy", "no-data") else 2
    if args.command == "verify":
        payload = ledger.integrity_check()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    if args.command == "metrics":
        sys.stdout.write(ledger.prometheus())
        return 0
    if args.command == "record":
        signals = read_json(args.signals)
        context = read_json(args.context) if args.context else {}
        payload = ledger.record(signals, context=context, observed_at=args.observed_at)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
