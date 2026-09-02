#!/usr/bin/env python3
"""Manage one-shot private Paul notices sent when a player logs in."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import player_login_notices as registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "backups" / "admin-bot" / "player-presence.json"


def runtime_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def output(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, dict) and payload.get("action") == "add":
        notice = payload.get("notice") or {}
        print(f"Added login notice for account {notice.get('accountId')}.")
        return
    if isinstance(payload, dict) and payload.get("action") == "remove":
        removed = payload.get("removed")
        if removed:
            print(f"Removed login notice for account {removed.get('accountId')}.")
        else:
            print(f"No login notice found for account {payload.get('accountId', 'unknown')}.")
        return
    rows = payload.get("notices", []) if isinstance(payload, dict) else payload
    if not rows:
        print("No player login notices configured.")
        return
    for row in rows:
        state = "delivered" if row.get("deliveredAt") else "active"
        online = "online" if row.get("online") else "offline"
        print(f"account {row.get('accountId')} · {state} · {online} · {row.get('playerName') or 'unknown player'}")


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--file", help=f"registry path (default: {registry.DEFAULT_PATH})")
    command.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")
    sub = command.add_subparsers(dest="action", required=True)

    add = sub.add_parser("add", help="create or replace a one-shot login notice")
    add.add_argument("--account-id", required=True, type=int)
    add.add_argument("--message", default=registry.DEFAULT_MESSAGE)

    remove = sub.add_parser("remove", help="remove a notice; delivery stops on the next poll")
    remove.add_argument("--account-id", required=True, type=int)
    sub.add_parser("list", help="list configured notices and runtime status")
    for child in (add, remove, sub.choices["list"]):
        child.add_argument("--json", action="store_true", dest="as_json", default=argparse.SUPPRESS, help="print machine-readable JSON")
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    path = registry.registry_path(args.file)
    if args.action == "add":
        notice = registry.upsert_notice(args.account_id, args.message, path)
        output({"ok": True, "action": "add", "path": str(path), "notice": notice}, args.as_json)
        return 0
    if args.action == "remove":
        removed = registry.remove_notice(args.account_id, path)
        output({"ok": True, "action": "remove", "path": str(path), "accountId": args.account_id, "removed": removed}, args.as_json)
        return 0
    output({"ok": True, "path": str(path), "notices": registry.merge_runtime(registry.list_notices(path), runtime_state())}, args.as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
