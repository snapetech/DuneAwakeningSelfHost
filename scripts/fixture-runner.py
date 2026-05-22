#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DB = "dune_sb_1_4_0_0"


def run(cmd, timeout=60):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)


def compose_cmd(env_file, *args):
    return [os.environ.get("CONTAINER_RUNTIME", "docker"), "compose", "--env-file", env_file, *args]


def psql(env_file, sql):
    db = os.environ.get("DUNE_DB_NAME", DEFAULT_DB)
    return run(compose_cmd(env_file, "exec", "-T", "postgres", "psql", "-U", "dune", "-d", db, "-v", "ON_ERROR_STOP=1", "-c", sql), timeout=30)


def load_fixture(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_result(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def execute_sql_group(env_file, statements):
    rows = []
    for sql in statements:
        result = psql(env_file, sql)
        rows.append({
            "sql": sql,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    return rows


def capture_logs(env_file, patterns):
    rows = []
    if not patterns:
        return rows
    result = run(compose_cmd(env_file, "logs", "--since=30m"), timeout=45)
    for pattern in patterns:
        import re
        matches = [line for line in result.stdout.splitlines() if re.search(pattern, line, re.I)]
        rows.append({"pattern": pattern, "matches": matches[-200:]})
    return rows


def write_diff_summary(out_dir, result):
    lines = [
        f"# Fixture Diff: {result['fixture']}",
        "",
        f"- Phase: `{result['phase']}`",
        f"- Requires client action: `{str(result.get('requiresClientAction', False)).lower()}`",
        "",
    ]
    for name in ("before", "after"):
        if name in result:
            failures = [row for row in result[name] if row["returncode"] != 0]
            lines.extend([f"## {name}", "", f"- SQL statements: {len(result[name])}", f"- Failures: {len(failures)}", ""])
    if result.get("logs"):
        lines.extend(["## logs", ""])
        for row in result["logs"]:
            lines.append(f"- `{row['pattern']}`: {len(row['matches'])} matches")
        lines.append("")
    (out_dir / "diff.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run read-only before/after fixture snapshots.")
    parser.add_argument("fixture", type=pathlib.Path)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--phase", choices=("before", "after", "both"), default="before")
    parser.add_argument("--output-dir", type=pathlib.Path)
    args = parser.parse_args()

    fixture = load_fixture(args.fixture)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir or ROOT / "research" / "fixtures" / f"{stamp}-{fixture['id']}"
    result = {"ok": True, "fixture": fixture["id"], "phase": args.phase, "requiresClientAction": fixture.get("requiresClientAction", False)}
    if args.phase in ("before", "both"):
        result["before"] = execute_sql_group(args.env_file, fixture.get("before", {}).get("sql", []))
    if args.phase in ("after", "both"):
        result["after"] = execute_sql_group(args.env_file, fixture.get("after", {}).get("sql", []))
        result["logs"] = capture_logs(args.env_file, fixture.get("after", {}).get("logs", []))
    result["operatorSteps"] = fixture.get("during", {}).get("operatorSteps", [])
    result["verdictRules"] = fixture.get("verdict", {})
    write_result(out_dir / "snapshot.json", result)
    write_diff_summary(out_dir, result)
    summary = [
        f"# Fixture Run: {fixture['id']}",
        "",
        f"- Phase: `{args.phase}`",
        f"- Requires client action: `{str(fixture.get('requiresClientAction', False)).lower()}`",
        "",
        "## Operator Steps",
        "",
    ]
    summary.extend(f"- {step}" for step in result["operatorSteps"])
    summary.append("")
    (out_dir / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    print(json.dumps({"ok": True, "outputDir": str(out_dir)}, indent=2))


if __name__ == "__main__":
    main()
