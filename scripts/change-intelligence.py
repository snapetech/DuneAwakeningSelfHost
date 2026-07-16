#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import change_intelligence


def write_private_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.is_dir():
        raise ValueError("capsule output parent is not a directory")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Inspect and verify DASH operational change intelligence")
    parser.add_argument("command", choices=("status", "verify", "metrics", "capsule", "export-capsule", "verify-capsule"))
    parser.add_argument("--incident-key", default="")
    parser.add_argument("--capsule-file", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--database", default=os.environ.get("DUNE_CHANGE_INTELLIGENCE_HOST_DATABASE", str(ROOT / "backups" / "change-intelligence" / "change-intelligence.sqlite3")))
    parser.add_argument("--policy", default=os.environ.get("DUNE_CHANGE_INTELLIGENCE_HOST_POLICY", str(ROOT / "config" / "change-intelligence.json")))
    parser.add_argument("--secret-file", default=os.environ.get("DUNE_CHANGE_INTELLIGENCE_HOST_HMAC_SECRET_FILE", str(ROOT / "config" / "secrets" / "change-intelligence-hmac.secret")))
    args = parser.parse_args()
    if args.command == "verify-capsule":
        if not args.capsule_file:
            parser.error("verify-capsule requires --capsule-file")
        document = json.loads(pathlib.Path(args.capsule_file).read_text(encoding="utf-8"))
        result = change_intelligence.verify_signed_capsule(document, change_intelligence.read_secret(args.secret_file))
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ok") else 1)
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
    elif args.command == "capsule":
        if not args.incident_key:
            parser.error("capsule requires --incident-key")
        print(json.dumps(store.capsule(args.incident_key), indent=2, sort_keys=True))
    else:
        if not args.incident_key:
            parser.error("export-capsule requires --incident-key")
        result = store.signed_capsule(args.incident_key)
        if args.output:
            write_private_json(args.output, result)
            print(json.dumps({"ok": True, "path": str(pathlib.Path(args.output)), "incidentKey": result["incidentKey"], "signature": result["signature"]}, indent=2, sort_keys=True))
        else:
            print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
