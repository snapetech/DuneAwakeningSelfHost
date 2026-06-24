#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-callfunction-hook-candidate-canary-runner/v1"
PASS_MARKERS = (
    "event=ue-call-function-hook",
    "status=passed",
    "selfTestTarget=false",
    "callSelfTest=false",
)
FAIL_MARKERS = (
    "event=ue-call-function-hook",
    "status=failed",
)


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or "candidate"


def write_env_file(path, env):
    with path.open("w", encoding="utf-8") as handle:
        for key, value in env.items():
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                raise ValueError(f"invalid env key: {key}")
            if "\n" in str(value) or "\r" in str(value):
                raise ValueError(f"invalid env value for {key}")
            handle.write(f"{key}={value}\n")


def candidate_log_path(candidate):
    return f"/tmp/dune-server-probe-loader-callfunction-rank{candidate['rank']}-{safe_name(candidate['imageOffset'])}.log"


def build_command(candidate, env_file, *, canary_script, target_env_file, preflight_only, capture_delay, strict_verify):
    env = {
        "DUNE_LINUX_SERVER_CANARY_EXTRA_ENV": str(env_file),
        "DUNE_LINUX_SERVER_CANARY_LOG_PATH": candidate_log_path(candidate),
        "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY": "true" if preflight_only else "false",
        "DUNE_LINUX_SERVER_CANARY_CAPTURE_DELAY_SECONDS": str(capture_delay),
        "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY": "true" if strict_verify else "false",
    }
    return {
        "env": env,
        "argv": [str(canary_script), str(target_env_file)],
        "shell": " ".join(f"{key}={value}" for key, value in env.items()) + f" {canary_script} {target_env_file}",
    }


def log_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def log_passed(path):
    text = log_text(path)
    return all(marker in text for marker in PASS_MARKERS)


def log_failed(path):
    text = log_text(path)
    return all(marker in text for marker in FAIL_MARKERS)


def matching_log_path(candidate, log_dir=None):
    expected = Path(candidate_log_path(candidate))
    if expected.exists():
        return expected
    if not log_dir:
        return expected
    log_dir = Path(log_dir)
    names = [
        expected.name,
        f"rank{candidate['rank']}-{safe_name(candidate['imageOffset'])}.log",
        f"rank{candidate['rank']:02d}-{safe_name(candidate['imageOffset'])}.log",
    ]
    for name in names:
        path = log_dir / name
        if path.exists():
            return path
    pattern = f"*rank{candidate['rank']}*{safe_name(candidate['imageOffset'])}*.log"
    matches = sorted(log_dir.glob(pattern))
    return matches[0] if matches else expected


def backup_log_path(candidate, backup_dir):
    if not backup_dir:
        return None
    path = Path(backup_dir) / Path(candidate_log_path(candidate)).name
    return path if path.exists() else None


def extract_backup_dir(stdout):
    for line in reversed(str(stdout or "").splitlines()):
        if line.startswith("backup_dir="):
            return line.split("=", 1)[1].strip()
    return ""


def evaluate_candidate_log(candidate, log_dir=None, backup_dir=None):
    path = backup_log_path(candidate, backup_dir) or matching_log_path(candidate, log_dir=log_dir)
    text = log_text(path)
    passed = bool(text) and all(marker in text for marker in PASS_MARKERS)
    failed = bool(text) and all(marker in text for marker in FAIL_MARKERS)
    event_lines = [
        line.strip()
        for line in text.splitlines()
        if "event=ue-call-function-hook" in line
    ][:8]
    return {
        "path": str(path),
        "exists": path.exists(),
        "hookProbePassed": passed,
        "hookProbeFailed": failed,
        "eventLines": event_lines,
    }


def run_command(command, *, cwd):
    env = os.environ.copy()
    env.update(command["env"])
    return subprocess.run(command["argv"], cwd=cwd, env=env, text=True, capture_output=True, check=False)


def build_plan(candidates_report, *, output_dir, canary_script, target_env_file, limit, preflight_only, capture_delay, strict_verify):
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for candidate in candidates_report.get("candidates", [])[:limit]:
        env_file = output_dir / f"rank{candidate['rank']:02d}-{safe_name(candidate['imageOffset'])}.env"
        write_env_file(env_file, candidate["env"])
        command = build_command(
            candidate,
            env_file.resolve(),
            canary_script=canary_script,
            target_env_file=target_env_file,
            preflight_only=preflight_only,
            capture_delay=capture_delay,
            strict_verify=strict_verify,
        )
        rows.append(
            {
                "rank": candidate["rank"],
                "imageOffset": candidate["imageOffset"],
                "narrowScore": candidate.get("narrowScore"),
                "rawScore": candidate.get("rawScore"),
                "envFile": str(env_file),
                "expectedLoaderLog": candidate_log_path(candidate),
                "command": command,
                "promotable": False,
                "promotionBlocker": "candidate canary has not passed hook probe and target-entry active validation",
            }
        )
    return rows


def summarize(args):
    candidates_report = load_json(args.candidates_json)
    rows = build_plan(
        candidates_report,
        output_dir=args.output_dir,
        canary_script=args.canary_script,
        target_env_file=args.env_file,
        limit=args.limit,
        preflight_only=args.preflight_only,
        capture_delay=args.capture_delay_seconds,
        strict_verify=args.strict_verify,
    )
    executed = []
    first_pass = None
    first_observed_pass = None
    if args.execute:
        for row in rows:
            result = run_command(row["command"], cwd=Path.cwd())
            backup_dir = extract_backup_dir(result.stdout)
            log_result = evaluate_candidate_log(row, log_dir=args.log_dir, backup_dir=backup_dir)
            passed = result.returncode == 0 and log_result["hookProbePassed"]
            row["execution"] = {
                "returnCode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "backupDir": backup_dir,
                "hookProbePassed": passed,
                "log": log_result,
            }
            executed.append(row)
            if passed:
                first_pass = row
                if args.stop_on_first_pass:
                    break
    for row in rows:
        log_result = evaluate_candidate_log(row, log_dir=args.log_dir)
        row["observedLog"] = log_result
        if log_result["hookProbePassed"] and first_observed_pass is None:
            first_observed_pass = row
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceCandidates": str(args.candidates_json),
        "candidateCount": len(rows),
        "execute": args.execute,
        "preflightOnly": args.preflight_only,
        "nativeCallAllowed": False,
        "reviewRequired": True,
        "firstHookProbePass": first_pass,
        "firstObservedHookProbePass": first_observed_pass,
        "candidates": rows,
        "executedCount": len(executed),
        "logDir": str(args.log_dir) if args.log_dir else "",
        "nextGate": "target-entry active validation with runtime object address and reviewed command",
    }


def markdown(report):
    lines = [
        "# CallFunction Hook Candidate Canary Plan",
        "",
        f"- Schema: `{report['schemaVersion']}`",
        f"- Candidates: `{report['candidateCount']}`",
        f"- Execute: `{str(report['execute']).lower()}`",
        f"- Preflight only: `{str(report['preflightOnly']).lower()}`",
        f"- Native call allowed: `{str(report['nativeCallAllowed']).lower()}`",
        f"- First observed hook pass: `{(report.get('firstObservedHookProbePass') or {}).get('imageOffset', '')}`",
        f"- Next gate: `{report['nextGate']}`",
        "",
        "| Rank | Image Offset | Observed | Env File | Expected Log | Command |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for row in report["candidates"]:
        observed = row.get("observedLog", {})
        observed_text = "pass" if observed.get("hookProbePassed") else "fail" if observed.get("hookProbeFailed") else "missing"
        lines.append(
            f"| {row['rank']} | `{row['imageOffset']}` | `{observed_text}` | `{row['envFile']}` | "
            f"`{row['expectedLoaderLog']}` | `{row['command']['shell']}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Plan or run guarded Linux server canaries for CallFunction hook target candidates."
    )
    parser.add_argument("candidates_json", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--canary-script", type=Path, default=Path("scripts/canary-linux-server-loader.sh"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-candidates"))
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--capture-delay-seconds", type=int, default=30)
    parser.add_argument("--log-dir", type=Path, help="directory containing copied candidate loader logs to evaluate")
    parser.add_argument("--strict-verify", action="store_true")
    parser.add_argument("--preflight-only", action="store_true", default=True)
    parser.add_argument("--full-canary", action="store_false", dest="preflight_only", help="run full canaries instead of preflight checks")
    parser.add_argument("--execute", action="store_true", help="actually run canary commands; default only writes env files and plan")
    parser.add_argument("--stop-on-first-pass", action="store_true", default=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)

    report = summarize(args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
