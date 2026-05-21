#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]


def read_env(path):
    values = {}
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env(name, default="", env_file=None):
    if os.environ.get(name):
        return os.environ[name]
    if env_file is not None:
        return env_file.get(name, default)
    return default


def request_json(method, url, token="", body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Admin-Token"] = token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"admin API failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"admin API unavailable: {exc}") from exc


def admin_base(args, env_file):
    if args.base_url:
        return args.base_url.rstrip("/")
    port = env("DUNE_ADMIN_HOST_PORT", "18080", env_file)
    return f"http://127.0.0.1:{port}"


def main_with_argv(argv=None):
    parser = argparse.ArgumentParser(description="Inspect, plan, or execute DASH character slot switch/restore operations.")
    parser.add_argument("--env-file", type=pathlib.Path, default=ROOT / ".env")
    parser.add_argument("--base-url", default="", help="Admin panel base URL. Default: http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}")
    parser.add_argument("--token", default="", help="Admin token. Default: DUNE_ADMIN_TOKEN from env/.env when configured.")
    parser.add_argument("--account-id", required=True, type=int)
    parser.add_argument("--target-account-id", type=int)
    parser.add_argument("--action", choices=("inspect", "new-character", "switch-character", "restore-character"), default="inspect")
    parser.add_argument("--execute", action="store_true", help="Execute switch-character/restore-character through the admin API.")
    parser.add_argument("--confirm", default="", help='Required for execution: "SWAP CHARACTER".')
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    env_file = read_env(args.env_file)
    base = admin_base(args, env_file)
    token = args.token or env("DUNE_ADMIN_TOKEN", "", env_file)

    if args.action == "inspect":
        query = urllib.parse.urlencode({"account_id": args.account_id})
        result = request_json("GET", f"{base}/api/admin/character-slots?{query}", token=token)
    else:
        if args.action in ("switch-character", "restore-character") and args.target_account_id is None:
            raise SystemExit("--target-account-id is required for switch-character and restore-character")
        body = {
            "dry_run": not args.execute,
            "account_id": args.account_id,
            "action": args.action,
            "target_account_id": args.target_account_id,
        }
        if args.execute:
            if args.action == "new-character":
                raise SystemExit("new-character execution is intentionally blocked; use plan/inspect only")
            if args.confirm != "SWAP CHARACTER":
                raise SystemExit('execution requires --confirm "SWAP CHARACTER"')
            body["confirm"] = args.confirm
            endpoint = "execute"
        else:
            endpoint = "plan"
        result = request_json("POST", f"{base}/api/admin/character-slots/{endpoint}", token=token, body=body)

    if args.pretty:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout, separators=(",", ":"), sort_keys=True)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main_with_argv()
