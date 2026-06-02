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

SAFE_ROUTE_DETAIL = {
    "fixture": "Empty route preferred; live route allowed only because command should log/print state and not mutate player data.",
    "passCriteria": "Server logs show the command entered the native handler, ideally `Now running ServerCommand`, and command-specific output appears without queue backlog or server restart.",
    "rollback": "No rollback expected. If the route destabilizes, stop the target map only and preserve logs.",
    "proofOrder": 10,
    "liveEligible": True,
}
ISOLATED_ADMIN_DETAIL = {
    "fixture": "One isolated admin/test character on an empty route or private map; record starting map, dimension, position, and movement mode.",
    "passCriteria": "The admin character changes only as expected, then returns to the recorded baseline with no other online players on the route.",
    "rollback": "Run `Walk` if movement mode changed, then return the admin to the recorded baseline position/map.",
    "proofOrder": 20,
    "liveEligible": False,
}
ISOLATED_MUTATION_DETAIL = {
    "fixture": "Disposable target character/object on an empty route after `PrintAllowedCommands` and `PrintPos` have already proven the payload route.",
    "passCriteria": "Only the disposable target changes, verified by DB/log delta before and after the command.",
    "rollback": "Delete granted test inventory/vehicle/object or restore the disposable target snapshot.",
    "proofOrder": 30,
    "liveEligible": False,
}
DESTRUCTIVE_DETAIL = {
    "fixture": "Disposable lab vehicle, totem, placeable, building, or building piece with a fresh DB/export snapshot and no players on the route.",
    "passCriteria": "Exactly the disposable fixture is destroyed; no neighboring structures, characters, or inventories change.",
    "rollback": "Restore the fixture from snapshot or discard/recreate the lab route.",
    "proofOrder": 40,
    "liveEligible": False,
}
CONSOLE_DETAIL = {
    "fixture": "Lab route only, with exact command arguments chosen from static evidence before execution.",
    "passCriteria": "Console command produces the expected bounded log/audit output without changing gameplay state.",
    "rollback": "Restart or recreate the lab route if the console command changes runtime state.",
    "proofOrder": 50,
    "liveEligible": False,
}
REJECTED_DETAIL = {
    "fixture": "Static binary/config evidence only.",
    "passCriteria": "Command is absent from the shipped dedicated-server GM allow-list or resolves to non-GM UE/FLS helper code.",
    "rollback": "None; do not execute.",
    "proofOrder": 0,
    "liveEligible": False,
}


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
            **SAFE_ROUTE_DETAIL,
        }
    if name in ADMIN_ONLY_COMMANDS:
        return {
            "proofStage": "isolated-admin-session",
            "nonDisruptiveRequirement": "Run only on an isolated admin/test character on an empty lab route or a private map with no players.",
            "defaultAction": "preview only.",
            "confidence": "moderate",
            **ISOLATED_ADMIN_DETAIL,
        }
    if name in ISOLATED_MUTATION_COMMANDS:
        return {
            "proofStage": "isolated-target-mutation",
            "nonDisruptiveRequirement": "Run only against an isolated disposable test character or disposable spawned object after route proof succeeds.",
            "defaultAction": "preview only.",
            "confidence": "moderate",
            **ISOLATED_MUTATION_DETAIL,
        }
    if name in DESTRUCTIVE_COMMANDS:
        return {
            "proofStage": "destructive-lab-only",
            "nonDisruptiveRequirement": "Never run on a populated/live route; use a disposable lab base, vehicle, or placeable with rollback evidence.",
            "defaultAction": "blocked.",
            "confidence": "high",
            **DESTRUCTIVE_DETAIL,
        }
    if name in CONSOLE_COMMANDS:
        return {
            "proofStage": "console-static-first",
            "nonDisruptiveRequirement": "Needs exact argument contract; do not execute broad Unreal console commands on live routes.",
            "defaultAction": "preview only.",
            "confidence": "moderate",
            **CONSOLE_DETAIL,
        }
    if name in REJECTED_COMMANDS or command["status"] == "rejected":
        return {
            "proofStage": "static-rejected",
            "nonDisruptiveRequirement": "No live execution; binary/config evidence rejects this as a shipped dedicated-server GM command.",
            "defaultAction": "do not execute.",
            "confidence": "high",
            **REJECTED_DETAIL,
        }
    return {
        "proofStage": "unclassified-preview",
        "nonDisruptiveRequirement": "Classify before execution.",
        "defaultAction": "preview only.",
        "confidence": "low",
        "fixture": "Unknown.",
        "passCriteria": "Unknown.",
        "rollback": "Unknown.",
        "proofOrder": 90,
        "liveEligible": False,
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
        "| Command | Stage | Result | Fixture | Pass criteria | Rollback | Live eligible | Confidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(payload["commands"], key=lambda item: (item["proofOrder"], item["command"])):
        lines.append(
            "| {command} | {stage} | {result} | {fixture} | {pass_criteria} | {rollback} | {live_eligible} | {confidence} |".format(
                command=row["command"],
                stage=row["proofStage"],
                result=row["result"],
                fixture=row["fixture"],
                pass_criteria=row["passCriteria"],
                rollback=row["rollback"],
                live_eligible="yes" if row["liveEligible"] else "no",
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
