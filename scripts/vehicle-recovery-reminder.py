#!/usr/bin/env python3
"""Manage durable per-account parked-vehicle recovery reminders."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import vehicle_recovery_reminders as registry


ROOT = pathlib.Path(__file__).resolve().parents[1]


def output(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, dict) and payload.get("action") == "add":
        reminder = payload.get("reminder") or {}
        print(f"Added vehicle reminder for account {reminder.get('accountId')} (vehicles {','.join(str(value) for value in reminder.get('vehicleIds') or [])}).")
        return
    if isinstance(payload, dict) and payload.get("action") == "remove":
        removed = payload.get("removed")
        print(f"Removed vehicle reminder for account {removed.get('accountId')}." if removed else f"No vehicle reminder found for account {payload.get('accountId', 'unknown')}.")
        return
    rows = payload.get("reminders", []) if isinstance(payload, dict) else payload
    if not rows:
        print("No vehicle recovery reminders configured.")
        return
    for row in rows:
        status = row.get("lastStatus") or row.get("status") or {}
        state = "restored" if row.get("restoredAt") or status.get("restored") else "active"
        online = "online" if row.get("online") else "offline"
        vehicles = ",".join(str(value) for value in row.get("vehicleIds") or [])
        print(f"account {row.get('accountId')} · vehicles {vehicles} · {state} · {online} · {row.get('playerName') or 'unknown player'}")


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--file", help="registry path (default: DUNE_PLAYER_PRESENCE_VEHICLE_RECOVERY_REMINDERS_FILE or backups/admin-bot/vehicle-recovery-reminders.json)")
    command.add_argument("--json", action="store_true", dest="as_json")
    sub = command.add_subparsers(dest="action", required=True)
    add = sub.add_parser("add", help="create or replace a reminder")
    add.add_argument("--account-id", required=True, type=int)
    add.add_argument("--vehicle-id", dest="vehicle_ids", action="append", type=int, required=True)
    add.add_argument("--message", default=registry.DEFAULT_MESSAGE)
    remove = sub.add_parser("remove", help="remove a reminder; future delivery stops on the next poll")
    remove.add_argument("--account-id", required=True, type=int)
    sub.add_parser("list", help="list configured reminders and latest runtime status")
    check = sub.add_parser("check", help="read live native vehicle-recovery/backup status without changing the registry")
    check.add_argument("--account-id", type=int)
    for child in (add, remove, sub.choices["list"], check):
        child.add_argument("--json", action="store_true", dest="as_json", default=argparse.SUPPRESS)
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    path = registry.registry_path(args.file)
    if args.action == "add":
        row = registry.upsert_reminder(args.account_id, args.vehicle_ids, args.message, path)
        output({"ok": True, "action": "add", "path": str(path), "reminder": row}, args.as_json)
        return 0
    if args.action == "remove":
        removed = registry.remove_reminder(args.account_id, path)
        output({"ok": True, "action": "remove", "path": str(path), "accountId": args.account_id, "removed": removed}, args.as_json)
        return 0
    rows = registry.list_reminders(path)
    if args.action == "list":
        runtime_path = ROOT / "backups" / "admin-bot" / "player-presence.json"
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            runtime = {}
        output({"ok": True, "path": str(path), "reminders": registry.merge_runtime(rows, runtime)}, args.as_json)
        return 0
    if args.account_id is not None:
        rows = [row for row in rows if int(row["accountId"]) == int(args.account_id)]
    import importlib.util
    announcer_path = pathlib.Path(__file__).with_name("player-presence-announcer.py")
    spec = importlib.util.spec_from_file_location("player_presence_vehicle_cli", announcer_path)
    announcer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(announcer)
    checked = []
    for row in rows:
        item = dict(row)
        item["status"] = announcer.vehicle_recovery_reminder_status(row)
        checked.append(item)
    output({"ok": True, "path": str(path), "reminders": checked}, args.as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
