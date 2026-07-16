#!/usr/bin/env python3
"""Manage DASH hashed admin-token identities without storing plaintext tokens."""

import argparse
import json
import os
import pathlib
import secrets
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import access_control  # noqa: E402


def load_document(path):
    if not path.exists():
        return {"version": 1, "users": []}
    document = json.loads(path.read_text(encoding="utf-8"))
    access_control.validate_document(document)
    return document


def write_document(path, document):
    access_control.validate_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=str(ROOT / "config/admin-access.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    subparsers.add_parser("list")
    add = subparsers.add_parser("add")
    add.add_argument("id")
    add.add_argument("--role", choices=sorted(access_control.ROLE_CAPABILITIES), required=True)
    add.add_argument("--display-name", default="")
    add.add_argument("--capability", action="append", default=[])
    rotate = subparsers.add_parser("rotate")
    rotate.add_argument("id")
    for command in ("enable", "disable", "remove"):
        target = subparsers.add_parser(command)
        target.add_argument("id")
    args = parser.parse_args()

    path = pathlib.Path(args.file)
    document = load_document(path)
    users = document["users"]
    user_id = str(getattr(args, "id", "")).strip().lower()
    existing = next((row for row in users if str(row.get("id")).lower() == user_id), None)

    if args.command == "init":
        write_document(path, document)
        print(f"initialized {path} with {len(users)} identities")
        return
    if args.command == "list":
        for row in access_control.validate_document(document):
            print(f"{row['id']}\t{row['role']}\t{'enabled' if row['enabled'] else 'disabled'}\t{','.join(row['capabilities'])}")
        return
    if args.command == "add":
        if existing:
            raise SystemExit(f"identity already exists: {user_id}")
        if not access_control.ID_PATTERN.fullmatch(user_id):
            raise SystemExit("id must match [a-z0-9][a-z0-9_.-]{1,63}")
        token = secrets.token_urlsafe(32)
        users.append({
            "id": user_id,
            "displayName": args.display_name or user_id,
            "enabled": True,
            "role": args.role,
            "capabilities": sorted(set(args.capability)),
            "tokenSha256": access_control.token_hash(token),
        })
        write_document(path, document)
        print(f"created {user_id}; token is shown once:\n{token}")
        return
    if not existing:
        raise SystemExit(f"identity not found: {user_id}")
    if args.command == "rotate":
        token = secrets.token_urlsafe(32)
        existing["tokenSha256"] = access_control.token_hash(token)
        write_document(path, document)
        print(f"rotated {user_id}; token is shown once:\n{token}")
    elif args.command in {"enable", "disable"}:
        existing["enabled"] = args.command == "enable"
        write_document(path, document)
        print(f"{args.command}d {user_id}")
    elif args.command == "remove":
        users.remove(existing)
        write_document(path, document)
        print(f"removed {user_id}")


if __name__ == "__main__":
    main()
