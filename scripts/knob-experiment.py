#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
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


def load_catalog(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Create a one-variable knob experiment evidence directory.")
    parser.add_argument("--catalog", type=pathlib.Path, required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--apply", action="store_true", help="Reserved for a future guarded writer; current implementation only records evidence.")
    parser.add_argument("--output-dir", type=pathlib.Path)
    args = parser.parse_args()

    experiment = load_catalog(args.catalog)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir or ROOT / "experiments" / "runs" / f"{stamp}-{experiment['id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "experiment.json").write_text(json.dumps(experiment, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    config_file = ROOT / experiment.get("config", {}).get("file", "")
    if config_file.exists():
        shutil.copy2(config_file, out_dir / "before.ini")
        shutil.copy2(config_file, out_dir / "after.ini")
    else:
        (out_dir / "before.ini.missing").write_text(str(config_file) + "\n", encoding="utf-8")
        (out_dir / "after.ini.missing").write_text(str(config_file) + "\n", encoding="utf-8")

    sql_results = []
    for sql in experiment.get("observe", {}).get("sql", []):
        result = psql(args.env_file, sql)
        sql_results.append({"sql": sql, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    (out_dir / "before-db.json").write_text(json.dumps(sql_results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "after-db.json").write_text(json.dumps(sql_results, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    logs = []
    for pattern in experiment.get("observe", {}).get("logs", []):
        result = run(compose_cmd(args.env_file, "logs", "--since=30m", experiment.get("service", "")), timeout=30)
        lines = [line for line in result.stdout.splitlines() if __import__("re").search(pattern, line, __import__("re").I)]
        logs.append({"pattern": pattern, "matches": lines[-200:]})
    (out_dir / "logs.json").write_text(json.dumps(logs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "logs.txt").write_text(
        "\n".join(
            [f"== {row['pattern']} ==" for row in logs]
            + [line for row in logs for line in row["matches"]]
        ) + "\n",
        encoding="utf-8",
    )

    verdict = {
        "effectObserved": False,
        "confidence": "unknown",
        "applyMode": args.apply,
        "promoteToTypedKnob": False,
        "notes": "This harness records baseline evidence only. Config writing remains intentionally unimplemented until guarded structured writers are added."
    }
    (out_dir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "summary.md").write_text(
        f"# Knob Experiment: {experiment['id']}\n\n"
        f"- Service: `{experiment.get('service', '')}`\n"
        f"- Apply mode: `{str(args.apply).lower()}`\n"
        f"- Output: `{out_dir}`\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "outputDir": str(out_dir)}, indent=2))


if __name__ == "__main__":
    main()
