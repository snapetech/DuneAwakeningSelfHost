#!/usr/bin/env python3
"""Manage durable player base-recovery reminders from the command line.

The player-presence service delivers reminders on login. This command only
manages the shared registry or performs a read-only live status check.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

import base_recovery_reminders as registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
ANNOUNCER_PATH = pathlib.Path(__file__).with_name("player-presence-announcer.py")


def load_announcer():
    spec = importlib.util.spec_from_file_location("player_presence_announcer_cli", ANNOUNCER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_state():
    path = ROOT / "backups" / "admin-bot" / "player-presence.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def output(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, dict) and payload.get("action") == "add":
        reminder = payload.get("reminder") or {}
        print(
            f"Added reminder for account {reminder.get('accountId')} "
            f"(backup {reminder.get('backupId')}, totem {reminder.get('totemId')})."
        )
        return
    if isinstance(payload, dict) and payload.get("action") == "remove":
        removed = payload.get("removed")
        if removed:
            print(f"Removed reminder for account {removed.get('accountId')}.")
        else:
            print(f"No reminder found for account {payload.get('accountId', 'unknown')}.")
        return
    if isinstance(payload, dict) and "reminders" in payload:
        rows = payload["reminders"]
    else:
        rows = payload if isinstance(payload, list) else [payload]
    if not rows:
        print("No base-recovery reminders configured.")
        return
    for row in rows:
        status = row.get("lastStatus") or row.get("status") or {}
        state = "restored" if row.get("restoredAt") or status.get("restored") else "active"
        online = "online" if row.get("online") else "offline"
        print(
            f"account {row.get('accountId')} · backup {row.get('backupId')} · "
            f"totem {row.get('totemId')} · {state} · {online} · "
            f"{row.get('playerName') or 'unknown player'}"
        )


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--file", help="registry path (default: DUNE_PLAYER_PRESENCE_BASE_RECOVERY_REMINDERS_FILE or backups/admin-bot/base-recovery-reminders.json)")
    command.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")
    sub = command.add_subparsers(dest="action", required=True)

    add = sub.add_parser("add", help="create or replace a reminder")
    add.add_argument("--account-id", required=True, type=int)
    add.add_argument("--backup-id", required=True, type=int)
    add.add_argument("--totem-id", required=True, type=int)
    add.add_argument("--message", default=registry.DEFAULT_MESSAGE)

    remove = sub.add_parser("remove", help="remove a reminder; delivery stops on the next poll")
    remove.add_argument("--account-id", required=True, type=int)

    sub.add_parser("list", help="list configured reminders and latest runtime status")
    check = sub.add_parser("check", help="read live native BRT status without changing the registry")
    check.add_argument("--account-id", type=int, help="check one account instead of all configured reminders")
    for child in (add, remove, sub.choices["list"], check):
        child.add_argument("--json", action="store_true", dest="as_json", default=argparse.SUPPRESS, help="print machine-readable JSON")
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    path = registry.registry_path(args.file)
    if args.action == "add":
        row = registry.upsert_reminder(args.account_id, args.backup_id, args.totem_id, args.message, path)
        output({"ok": True, "action": "add", "path": str(path), "reminder": row}, args.as_json)
        return 0
    if args.action == "remove":
        removed = registry.remove_reminder(args.account_id, path)
        output({"ok": True, "action": "remove", "path": str(path), "removed": removed}, args.as_json)
        return 0

    rows = registry.list_reminders(path)
    if args.action == "list":
        output({"ok": True, "path": str(path), "reminders": registry.merge_runtime(rows, runtime_state())}, args.as_json)
        return 0

    if args.account_id is not None:
        rows = [row for row in rows if int(row["accountId"]) == int(args.account_id)]
    announcer = load_announcer()
    checked = []
    for row in rows:
        item = dict(row)
        item["status"] = announcer.base_recovery_reminder_status(row)
        checked.append(item)
    output({"ok": True, "path": str(path), "reminders": checked}, args.as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
