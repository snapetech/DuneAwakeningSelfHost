#!/usr/bin/env python3
"""Manage the ignored, host-local DASH outbound webhook endpoint file."""

import argparse
import json
import pathlib
import secrets
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "admin"))
import outbound_webhooks


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def origin(url):
    parsed = urllib.parse.urlparse(url)
    value = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        value += f":{parsed.port}"
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/outbound-webhooks.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("endpoint_id")
    add.add_argument("url")
    add.add_argument("--format", choices=("dash", "discord"), default="dash")
    add.add_argument("--events", default=",".join(outbound_webhooks.DEFAULT_EVENTS))
    add.add_argument("--min-interval-seconds", type=float, default=0)
    remove = sub.add_parser("remove")
    remove.add_argument("endpoint_id")
    toggle = sub.add_parser("enable")
    toggle.add_argument("endpoint_id")
    disable = sub.add_parser("disable")
    disable.add_argument("endpoint_id")
    args = parser.parse_args()
    path = pathlib.Path(args.config).resolve()

    if args.command == "init":
        if path.exists():
            outbound_webhooks.load_config(path)
            print(f"already initialized: {path}")
        else:
            save(path, {"version": 1, "endpoints": []})
            print(f"initialized: {path}")
        return

    data = outbound_webhooks.load_config(path)
    if args.command == "list":
        for endpoint in data["endpoints"]:
            print(f"{endpoint['id']}\t{'enabled' if endpoint['enabled'] else 'disabled'}\t{endpoint['format']}\t{origin(endpoint['url'])}\t{','.join(endpoint['events'])}")
        return
    if args.command == "add":
        if any(item["id"] == args.endpoint_id for item in data["endpoints"]):
            raise SystemExit(f"endpoint already exists: {args.endpoint_id}")
        signing_secret = secrets.token_urlsafe(48)
        data["endpoints"].append({
            "id": args.endpoint_id,
            "url": args.url,
            "format": args.format,
            "enabled": True,
            "events": [item.strip() for item in args.events.split(",") if item.strip()],
            "minIntervalSeconds": args.min_interval_seconds,
            "secret": signing_secret,
        })
        save(path, data)
        outbound_webhooks.load_config(path)
        print(f"added {args.endpoint_id}; signing secret (shown once): {signing_secret}")
        return
    endpoint = next((item for item in data["endpoints"] if item["id"] == args.endpoint_id), None)
    if endpoint is None:
        raise SystemExit(f"endpoint not found: {args.endpoint_id}")
    if args.command == "remove":
        data["endpoints"] = [item for item in data["endpoints"] if item["id"] != args.endpoint_id]
    else:
        endpoint["enabled"] = args.command == "enable"
    save(path, data)
    print(f"{args.command}d endpoint: {args.endpoint_id}")


if __name__ == "__main__":
    main()
