#!/usr/bin/env python3
import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "scripts" / "gm-command-catalog.py"


SAFE_PROBE_COMMANDS = {"PrintAllowedCommands", "PrintPos"}
ADMIN_ONLY_COMMANDS = {
    "PatrolShipTeleportToNearest",
    "TeleportTo",
    "TeleportToMap",
    "TeleportToExact",
    "TeleportToVehicleSpawner",
    "TeleportToSandworm",
    "TeleportToPersonalMarker",
    "TravelTo",
    "TravelToDimension",
    "Fly",
    "Ghost",
    "Walk",
}
ISOLATED_MUTATION_COMMANDS = {
    "AddItemToInventory",
    "AddBasicInventoryToCharacter",
    "SpawnVehicle",
    "TeleportToPlayer",
}
DESTRUCTIVE_COMMANDS = {
    "DestroyTargetVehicle",
    "DestroyTotem",
    "DestroyPlaceable",
    "DestroyEntireBuilding",
    "DestroyBuildingPiece",
}
CONSOLE_COMMANDS = {"obj", "FGL.ComponentAuditRequested"}
REJECTED_COMMANDS = {"RemoveSessionMember", "KickLobbyMember", "BattlEyeMegaKick"}


def load_catalog():
    spec = importlib.util.spec_from_file_location("gm_command_catalog", CATALOG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.catalog()


def proof_policy(command):
    name = command["name"]
    if name in SAFE_PROBE_COMMANDS:
        return {
            "proofStage": "safe-route-probe",
            "nonDisruptiveRequirement": "Can run on a live route; it should only print/log command output.",
            "defaultAction": "execute only with --execute-safe; otherwise preview.",
            "confidence": "moderate",
        }
    if name in ADMIN_ONLY_COMMANDS:
        return {
            "proofStage": "isolated-admin-session",
            "nonDisruptiveRequirement": "Run only on an isolated admin/test character on an empty lab route or a private map with no players.",
            "defaultAction": "preview only.",
            "confidence": "moderate",
        }
    if name in ISOLATED_MUTATION_COMMANDS:
        return {
            "proofStage": "isolated-target-mutation",
            "nonDisruptiveRequirement": "Run only against an isolated disposable test character or disposable spawned object after route proof succeeds.",
            "defaultAction": "preview only.",
            "confidence": "moderate",
        }
    if name in DESTRUCTIVE_COMMANDS:
        return {
            "proofStage": "destructive-lab-only",
            "nonDisruptiveRequirement": "Never run on a populated/live route; use a disposable lab base, vehicle, or placeable with rollback evidence.",
            "defaultAction": "blocked.",
            "confidence": "high",
        }
    if name in CONSOLE_COMMANDS:
        return {
            "proofStage": "console-static-first",
            "nonDisruptiveRequirement": "Needs exact argument contract; do not execute broad Unreal console commands on live routes.",
            "defaultAction": "preview only.",
            "confidence": "moderate",
        }
    if name in REJECTED_COMMANDS or command["status"] == "rejected":
        return {
            "proofStage": "static-rejected",
            "nonDisruptiveRequirement": "No live execution; binary/config evidence rejects this as a shipped dedicated-server GM command.",
            "defaultAction": "do not execute.",
            "confidence": "high",
        }
    return {
        "proofStage": "unclassified-preview",
        "nonDisruptiveRequirement": "Classify before execution.",
        "defaultAction": "preview only.",
        "confidence": "low",
    }


def preview_body(command, route, target_player, admin_player):
    return {
        "route": route,
        "commandText": command["syntax"].replace("<player>", target_player).replace("<target>", target_player),
        "targetPlayer": target_player,
        "adminPlayer": admin_player,
        "status": "preview-only",
    }


def run_safe_probe(command_name, route, target_player, admin_player, wait_response, modes):
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "probe-gm-command.py"),
        "--command",
        command_name,
        "--route",
        route,
        "--target-player",
        target_player,
        "--admin-player",
        admin_player,
        "--wait-response",
        str(wait_response),
    ]
    for mode in modes:
        cmd.extend(["--mode", mode])
    started = time.time()
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    evidence = {
        "argv": cmd,
        "returnCode": result.returncode,
        "elapsedSeconds": round(time.time() - started, 3),
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-4000:],
    }
    try:
        evidence["json"] = json.loads(result.stdout)
    except json.JSONDecodeError:
        pass
    return evidence


def build_rows(args):
    data = load_catalog()
    commands = data["commands"]
    if args.command:
        requested = set(args.command)
        commands = [command for command in commands if command["name"] in requested]
    rows = []
    for command in commands:
        policy = proof_policy(command)
        row = {
            "command": command["name"],
            "tier": command["tier"],
            "catalogStatus": command["status"],
            "syntax": command["syntax"],
            **policy,
            "preview": preview_body(command, args.route, args.target_player, args.admin_player),
            "result": "not-run",
        }
        if args.execute_safe and command["name"] in SAFE_PROBE_COMMANDS:
            row["evidence"] = run_safe_probe(
                command["name"],
                args.route,
                args.target_player,
                args.admin_player,
                args.wait_response,
                args.mode,
            )
            row["result"] = "executed-safe-probe" if row["evidence"]["returnCode"] == 0 else "safe-probe-failed"
        rows.append(row)
    return {
        "ok": True,
        "confidence": "moderate",
        "host": args.host,
        "route": args.route,
        "targetPlayer": args.target_player,
        "adminPlayer": args.admin_player,
        "executeSafe": args.execute_safe,
        "commands": rows,
    }


def markdown(payload):
    lines = [
        "# GM Command Proof Ledger",
        "",
        f"Confidence: {payload['confidence']}. Host: `{payload['host']}`. Route: `{payload['route']}`.",
        "",
        "| Command | Stage | Result | Non-disruptive requirement | Confidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload["commands"]:
        lines.append(
            "| {command} | {stage} | {result} | {requirement} | {confidence} |".format(
                command=row["command"],
                stage=row["proofStage"],
                result=row["result"],
                requirement=row["nonDisruptiveRequirement"],
                confidence=row["confidence"],
            )
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Build or execute a non-disruptive proof ledger for mapped GM commands.")
    parser.add_argument("--route", default="Survival_11")
    parser.add_argument("--target-player", default="SamplePlayer")
    parser.add_argument("--admin-player", default="SamplePlayer")
    parser.add_argument("--host", default="")
    parser.add_argument("--command", action="append", help="Limit to one command name. Repeatable.")
    parser.add_argument("--execute-safe", action="store_true", help="Execute only harmless route probes: PrintAllowedCommands and PrintPos.")
    parser.add_argument("--wait-response", type=float, default=3.0)
    parser.add_argument("--mode", action="append", default=[], help="Limit probe-gm-command envelope modes when --execute-safe is set.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", help="Optional output path for the generated ledger.")
    args = parser.parse_args()

    if not args.host:
        args.host = subprocess.run(["hostname"], text=True, capture_output=True, check=False).stdout.strip() or "unknown"

    payload = build_rows(args)
    rendered = markdown(payload) if args.format == "markdown" else json.dumps(payload, indent=2) + "\n"
    if args.output:
        pathlib.Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
