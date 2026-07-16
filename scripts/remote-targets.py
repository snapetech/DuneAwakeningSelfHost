#!/usr/bin/env python3
"""Pinned-host SSH profiles, private admin tunnels, and verified key rotation."""

import argparse
import base64
import datetime
import hashlib
import json
import os
import pathlib
import re
import shlex
import stat
import subprocess
import sys

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SAFE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
REMOTE_ROTATE = r'''
import base64,datetime,os,pathlib,re,sys
action,old64,new64=sys.argv[1:]
old=base64.b64decode(old64).decode(); new=base64.b64decode(new64).decode()
valid=re.compile(r'^(ssh-ed25519|sk-ssh-ed25519@openssh.com) [A-Za-z0-9+/]+={0,3}(?: .*)?$')
if not valid.fullmatch(new) or not re.fullmatch(r'[A-Za-z0-9+/]+={0,3}',old): raise SystemExit('invalid key material')
root=pathlib.Path.home()/'.ssh'; path=root/'authorized_keys'; root.mkdir(mode=0o700,exist_ok=True)
lines=path.read_text(encoding='utf-8').splitlines() if path.exists() else []
def blob(line):
 p=line.split()
 for i,v in enumerate(p[:-1]):
  if v in ('ssh-ed25519','sk-ssh-ed25519@openssh.com'): return p[i+1]
 return ''
new_blob=new.split()[1]
if action=='add':
 if not any(blob(line)==new_blob for line in lines): lines.append(new+' dash-rotation')
elif action=='remove':
 if not any(blob(line)==new_blob for line in lines): raise SystemExit('new key not installed')
 lines=[line for line in lines if blob(line)!=old]
else: raise SystemExit('invalid action')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
if path.exists(): (root/f'authorized_keys.before-{action}-{stamp}').write_bytes(path.read_bytes())
tmp=root/'.authorized_keys.new'; tmp.write_text('\n'.join(lines)+'\n',encoding='utf-8'); os.chmod(tmp,0o600); os.replace(tmp,path)
'''
REMOTE_CODE = base64.b64encode(REMOTE_ROTATE.encode()).decode()


def load_config(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("targets"), list):
        raise ValueError("remote target config schemaVersion must be 1")
    result = {}
    for item in data["targets"]:
        target_id = str(item.get("id", ""))
        if not SAFE_ID.fullmatch(target_id) or target_id in result: raise ValueError("invalid/duplicate target id")
        if not SAFE_HOST.fullmatch(str(item.get("host", ""))): raise ValueError(f"invalid host for {target_id}")
        if not SAFE_HOST.fullmatch(str(item.get("expectedHostname", ""))): raise ValueError(f"expectedHostname required for {target_id}")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", str(item.get("user", ""))): raise ValueError(f"invalid user for {target_id}")
        for key in ("port", "adminRemotePort", "adminLocalPort"):
            value = int(item.get(key, 0));
            if not 1 <= value <= 65535: raise ValueError(f"invalid {key} for {target_id}")
        for key in ("identityFile", "knownHostsFile"):
            value = pathlib.Path(str(item.get(key, "")))
            if not value.is_absolute(): raise ValueError(f"{key} must be absolute for {target_id}")
        result[target_id] = item
    return result


def ssh_base(item, identity=None):
    return ["ssh", "-T", "-p", str(item["port"]), "-i", str(identity or item["identityFile"]),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={item['knownHostsFile']}",
            "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes"]


def validate_files(item):
    for key in ("identityFile", "knownHostsFile"):
        path = pathlib.Path(item[key])
        if not path.is_file() or path.stat().st_size == 0: raise ValueError(f"missing/empty {key}: {path}")
    if stat.S_IMODE(pathlib.Path(item["identityFile"]).stat().st_mode) & 0o077:
        raise ValueError("identityFile must be mode 0600 or stricter")


def run_ssh(item, command, identity=None, timeout=30):
    destination = f"{item['user']}@{item['host']}"
    return subprocess.run(ssh_base(item, identity) + [destination, command], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout, check=False)


def check(item, identity=None):
    result = run_ssh(item, "hostname", identity)
    actual = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if result.returncode or actual != item["expectedHostname"]:
        raise RuntimeError(f"target identity check failed rc={result.returncode} expected={item['expectedHostname']} actual={actual}")
    return actual


def rotate(item, receipt_root):
    validate_files(item); check(item)
    identity = pathlib.Path(item["identityFile"]); public = identity.with_suffix(identity.suffix + ".pub")
    if not public.is_file(): raise ValueError(f"old public key is required: {public}")
    old_parts = public.read_text(encoding="utf-8").strip().split()
    if len(old_parts) < 2 or old_parts[0] not in ("ssh-ed25519", "sk-ssh-ed25519@openssh.com"):
        raise ValueError("only Ed25519 keys are rotated")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    next_key = identity.with_name(identity.name + ".next")
    for path in (next_key, pathlib.Path(str(next_key) + ".pub")):
        if path.exists(): raise ValueError(f"rotation staging path exists: {path}")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"dash-{item['id']}-{stamp}", "-f", str(next_key)], check=True)
    os.chmod(next_key, 0o600)
    new_text = pathlib.Path(str(next_key) + ".pub").read_text(encoding="utf-8").strip()
    old_blob = old_parts[1]
    command = lambda action: "python3 -c \"import base64;exec(base64.b64decode('%s'))\" %s %s %s" % (
        REMOTE_CODE, action, base64.b64encode(old_blob.encode()).decode(), base64.b64encode(new_text.encode()).decode())
    added = run_ssh(item, command("add"), timeout=60)
    if added.returncode: raise RuntimeError(f"remote key add failed: {added.stdout[-1000:]}")
    check(item, next_key)
    previous = identity.with_name(identity.name + f".previous-{stamp}")
    os.replace(identity, previous)
    if public.exists(): os.replace(public, pathlib.Path(str(previous) + ".pub"))
    os.replace(next_key, identity); os.replace(pathlib.Path(str(next_key) + ".pub"), public)
    removed = run_ssh(item, command("remove"), identity, 60)
    if removed.returncode: raise RuntimeError(f"new key works but old remote key removal failed: {removed.stdout[-1000:]}")
    receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = {"version": 1, "target": item["id"], "host": item["host"],
               "expectedHostname": item["expectedHostname"], "rotatedAt": stamp,
               "previousIdentity": str(previous),
               "newPublicKeySha256": hashlib.sha256(new_text.encode()).hexdigest()}
    out = receipt_root / f"{stamp}-{item['id']}.json"
    out.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"); os.chmod(out, 0o600)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, default=pathlib.Path("config/remote-targets.json"))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    for name in ("check", "tunnel"):
        child = sub.add_parser(name); child.add_argument("target")
    child = sub.add_parser("rotate-key"); child.add_argument("target"); child.add_argument("--confirm", required=True)
    args = parser.parse_args(); targets = load_config(args.config)
    if args.action == "list":
        print(json.dumps([{"id": key, "host": value["host"], "port": value["port"], "expectedHostname": value["expectedHostname"]} for key, value in sorted(targets.items())], indent=2)); return
    if args.target not in targets: raise SystemExit(f"unknown target: {args.target}")
    item = targets[args.target]; validate_files(item)
    if args.action == "check": print(json.dumps({"ok": True, "hostname": check(item), "target": args.target})); return
    if args.action == "tunnel":
        check(item)
        command = ssh_base(item) + ["-N", "-o", "ExitOnForwardFailure=yes",
                  "-L", f"127.0.0.1:{item['adminLocalPort']}:127.0.0.1:{item['adminRemotePort']}", f"{item['user']}@{item['host']}"]
        os.execvp(command[0], command)
    if args.confirm != "ROTATE DASH SSH KEY": raise SystemExit("exact confirmation required: ROTATE DASH SSH KEY")
    print(json.dumps(rotate(item, pathlib.Path("backups/remote-access")), indent=2))


if __name__ == "__main__": main()
