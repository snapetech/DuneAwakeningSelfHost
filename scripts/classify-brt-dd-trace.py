#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-brt-dd-trace-classification/v1"
SERVER_RPC_MARKERS = (
    "SERVER-RPC-ENTRY",
    "SERVER-RPC-EXEC",
)
UPROBE_RPC_MARKERS = (
    "brt_rpc_exec_server_request_basebackup",
    "brt_rpc_impl_server_request_basebackup",
    "server_request_basebackup_entry",
    "brt_rpc_request_handler",
    "brt_rpc_exec_server_request_building_blueprint",
    "brt_rpc_impl_server_request_building_blueprint",
)


def read_text(path):
    if str(path) == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="replace")


def classify_trace(text, source_path):
    lines = text.splitlines()
    marker_hits = []
    for line_no, line in enumerate(lines, start=1):
        for marker in SERVER_RPC_MARKERS + UPROBE_RPC_MARKERS:
            if marker in line:
                marker_hits.append(
                    {
                        "line": line_no,
                        "marker": marker,
                        "text": line[:500],
                    }
                )
    reached = bool(marker_hits)
    if reached:
        rpc_classification = "normal-request-reached-server"
        next_action = "fix-reached-server-side-branch"
    else:
        rpc_classification = "normal-request-not-observed"
        next_action = "server-side-request-emulation"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourcePath": str(source_path),
        "rpcReachedServer": reached,
        "rpcClassification": rpc_classification,
        "emulatorRpcClassification": (
            "operator-controlled-fallback" if reached else "normal-request-not-observed"
        ),
        "serverSideEmulationAllowed": not reached,
        "clientModificationRequired": False,
        "markerHits": marker_hits,
        "nextAction": next_action,
        "decision": (
            "SERVER-RPC-ENTRY/SERVER-RPC-EXEC or an equivalent current-build "
            "server_request_basebackup/brt_rpc uprobe fired; the request reached the server, "
            "so fix the reached server-side branch before using an operator fallback."
            if reached
            else
            "SERVER-RPC-ENTRY/SERVER-RPC-EXEC and equivalent current-build "
            "server_request_basebackup/brt_rpc uprobes did not fire; classify "
            "the normal request as not observed and use server-side request "
            "emulation rather than making client modification a requirement."
        ),
    }


def render_markdown(result):
    lines = [
        "# BRT DD Trace Classification",
        "",
        f"- Source: `{result['sourcePath']}`",
        f"- RPC reached server: `{str(result['rpcReachedServer']).lower()}`",
        f"- RPC classification: `{result['rpcClassification']}`",
        f"- Emulator classification: `{result['emulatorRpcClassification']}`",
        f"- Server-side emulation allowed: `{str(result['serverSideEmulationAllowed']).lower()}`",
        f"- Client modification required: `{str(result['clientModificationRequired']).lower()}`",
        f"- Next action: `{result['nextAction']}`",
        "",
        result["decision"],
    ]
    if result["markerHits"]:
        lines.extend(["", "## Marker Hits", ""])
        for hit in result["markerHits"]:
            lines.append(f"- line `{hit['line']}` `{hit['marker']}`: `{hit['text']}`")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Classify a DD1 BRT trace log for server RPC arrival. Missing RPC "
            "markers are classified as a server-side emulation path, not as a "
            "client modification requirement."
        )
    )
    parser.add_argument("trace_log", help="Trace log path, or '-' for stdin.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    text = read_text(args.trace_log)
    result = classify_trace(text, args.trace_log)
    if args.format == "markdown":
        print(render_markdown(result), end="")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
