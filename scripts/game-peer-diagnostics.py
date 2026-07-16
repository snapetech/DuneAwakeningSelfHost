#!/usr/bin/env python3
"""Ephemeral conntrack view for the configured Dune game/RMQ port ranges."""

import argparse
import ipaddress
import json
import pathlib
import re
import subprocess


def ranges(text):
    result = []
    for part in text.split(","):
        bits = part.strip().split("-")
        low, high = int(bits[0]), int(bits[-1])
        if not 1 <= low <= high <= 65535: raise ValueError("invalid port range")
        result.append((low, high))
    return result


def included(port, allowed): return any(low <= port <= high for low, high in allowed)


def parse(lines, allowed, raw):
    rows = []
    for line in lines:
        protocol = next((word for word in line.split()[:4] if word in ("tcp", "udp")), "")
        pairs = re.findall(r"\b(src|dst|sport|dport)=([^ ]+)", line)
        first = {}
        for key, value in pairs:
            if key not in first: first[key] = value
        if protocol not in ("tcp", "udp") or not first.get("dport", "").isdigit(): continue
        port = int(first["dport"])
        if not included(port, allowed): continue
        try: address = ipaddress.ip_address(first["src"])
        except (KeyError, ValueError): continue
        peer = str(address) if raw else str(ipaddress.ip_network(f"{address}/{24 if address.version == 4 else 64}", strict=False))
        rows.append({"protocol": protocol, "peer": peer, "destinationPort": port,
                     "state": "ESTABLISHED" if "ESTABLISHED" in line else ("UNREPLIED" if "UNREPLIED" in line else "tracked")})
    unique = {(row["protocol"], row["peer"], row["destinationPort"], row["state"]): row for row in rows}
    return [unique[key] for key in sorted(unique)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports", default="7777-7810,7888-7918,31982")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--fixture", type=pathlib.Path)
    args = parser.parse_args()
    if args.raw and args.confirm != "SHOW RAW GAME PEER IPS":
        raise SystemExit("raw mode requires --confirm 'SHOW RAW GAME PEER IPS'")
    if args.fixture:
        lines = args.fixture.read_text(encoding="utf-8").splitlines()
    else:
        result = subprocess.run(["conntrack", "-L", "-o", "extended"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise SystemExit("conntrack read failed; run as root/CAP_NET_ADMIN and install conntrack-tools")
        lines = result.stdout.splitlines()
    rows = parse(lines, ranges(args.ports), args.raw)
    print(json.dumps({"schemaVersion": 1, "rawPeerAddresses": args.raw,
                      "persisted": False, "count": len(rows), "connections": rows}, indent=2))


if __name__ == "__main__": main()
