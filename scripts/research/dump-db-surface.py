#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]


def psql(env_file, sql):
    cmd = [
        os.environ.get("CONTAINER_RUNTIME", "docker"),
        "compose",
        "--env-file",
        env_file,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "dune",
        "-d",
        os.environ.get("DUNE_DB_NAME", "dune_sb_1_4_0_0"),
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="Dump read-only Postgres schema/function surface metadata.")
    parser.add_argument("env_file", nargs="?", default=".env")
    args = parser.parse_args()

    tables = psql(
        args.env_file,
        """
        select table_schema, table_name, column_name, data_type, is_nullable
        from information_schema.columns
        where table_schema='dune'
        order by table_name, ordinal_position;
        """,
    )
    functions = psql(
        args.env_file,
        """
        select n.nspname, p.proname, pg_get_function_arguments(p.oid), pg_get_function_result(p.oid)
        from pg_proc p
        join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='dune'
        order by p.proname, pg_get_function_arguments(p.oid);
        """,
    )
    triggers = psql(
        args.env_file,
        """
        select event_object_schema, event_object_table, trigger_name, action_timing, event_manipulation
        from information_schema.triggers
        where event_object_schema='dune'
        order by event_object_table, trigger_name;
        """,
    )
    print(json.dumps({
        "ok": True,
        "tables": [
            {"schema": row[0], "table": row[1], "column": row[2], "type": row[3], "nullable": row[4]}
            for row in tables
        ],
        "functions": [
            {"schema": row[0], "name": row[1], "args": row[2], "returns": row[3]}
            for row in functions
        ],
        "triggers": [
            {"schema": row[0], "table": row[1], "name": row[2], "timing": row[3], "event": row[4]}
            for row in triggers
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
