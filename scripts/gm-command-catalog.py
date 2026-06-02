#!/usr/bin/env python3
import argparse
import json


COMMANDS = [
    {"name": "PrintAllowedCommands", "tier": "safe", "status": "probe-only", "syntax": "PrintAllowedCommands", "chat": "", "notes": "Best command-list probe after the native payload envelope is proven."},
    {"name": "PrintPos", "tier": "safe", "status": "wired-preview", "syntax": "PrintPos", "chat": "&gm pos", "notes": "Safest live route probe; should not mutate player state."},
    {"name": "AddItemToInventory", "tier": "inventory", "status": "wired-preview", "syntax": "AddItemToInventory <player> <template> [count] [quality]", "chat": "&gm item <player> <template> [count] [quality]", "notes": "Native inventory grant path. Execution remains behind GM payload verification."},
    {"name": "AddBasicInventoryToCharacter", "tier": "inventory", "status": "wired-preview", "syntax": "AddBasicInventoryToCharacter <player>", "chat": "&gm kit <player> [basic]", "notes": "Basic kit wrapper only; other kit names are not mapped."},
    {"name": "SpawnVehicle", "tier": "spawn", "status": "wired-preview", "syntax": "SpawnVehicle <template> [args...]", "chat": "&gm vehicle <template> [args...]", "notes": "Vehicle template and argument behavior still need live validation."},
    {"name": "PatrolShipTeleportToNearest", "tier": "movement", "status": "wired-preview", "syntax": "PatrolShipTeleportToNearest", "chat": "&gm patrol", "notes": "Admin movement helper."},
    {"name": "TeleportTo", "tier": "movement", "status": "cataloged", "syntax": "TeleportTo <args...>", "chat": "&gm dry TeleportTo <args...>", "notes": "Allowed by native config, but exact argument contract is not mapped yet."},
    {"name": "TeleportToMap", "tier": "movement", "status": "wired-preview", "syntax": "TeleportToMap <map> [dimension]", "chat": "&gm map <map> [dimension]", "notes": "Admin map teleport helper."},
    {"name": "TeleportToExact", "tier": "movement", "status": "wired-preview", "syntax": "TeleportToExact <x> <y> <z>", "chat": "&gm tp <x> <y> <z>; &gm recall [mark]; &gm unstuck <player> [mark]", "notes": "Exact-coordinate teleport helper."},
    {"name": "TeleportToPlayer", "tier": "movement", "status": "wired-preview", "syntax": "TeleportToPlayer <player>", "chat": "&gm goto <player>", "notes": "Online movement also requires same-route and one-use arm gates."},
    {"name": "TeleportToVehicleSpawner", "tier": "movement", "status": "cataloged", "syntax": "TeleportToVehicleSpawner <args...>", "chat": "&gm dry TeleportToVehicleSpawner <args...>", "notes": "Allowed by native config; no dedicated wrapper yet."},
    {"name": "TeleportToSandworm", "tier": "movement", "status": "wired-preview", "syntax": "TeleportToSandworm", "chat": "&gm sandworm", "notes": "Admin movement helper."},
    {"name": "TeleportToPersonalMarker", "tier": "movement", "status": "wired-preview", "syntax": "TeleportToPersonalMarker", "chat": "&gm marker", "notes": "Admin movement helper."},
    {"name": "TravelTo", "tier": "movement", "status": "wired-preview", "syntax": "TravelTo <map> [location]", "chat": "&gm travel <map> [location]", "notes": "Native travel helper."},
    {"name": "TravelToDimension", "tier": "movement", "status": "wired-preview", "syntax": "TravelToDimension <map> <dimension>", "chat": "&gm dimension <map> <dimension>", "notes": "Native dimension travel helper."},
    {"name": "Fly", "tier": "movement", "status": "wired-preview", "syntax": "Fly", "chat": "&gm fly", "notes": "Admin movement mode."},
    {"name": "Ghost", "tier": "movement", "status": "wired-preview", "syntax": "Ghost", "chat": "&gm ghost", "notes": "Admin movement mode."},
    {"name": "Walk", "tier": "movement", "status": "wired-preview", "syntax": "Walk", "chat": "&gm walk", "notes": "Return movement mode to normal walking."},
    {"name": "RemoveSessionMember", "tier": "player", "status": "rejected", "syntax": "RemoveSessionMember <player>", "chat": "", "notes": "Ghidra shows a UE Online Services operation/result helper, not a shipped dedicated-server GM command; not in DedicatedServerGame.ini."},
    {"name": "KickLobbyMember", "tier": "player", "status": "rejected", "syntax": "KickLobbyMember <player>", "chat": "", "notes": "Ghidra shows a UE Online Services lobby operation/result helper, not a shipped dedicated-server GM command; not in DedicatedServerGame.ini."},
    {"name": "BattlEyeMegaKick", "tier": "player", "status": "rejected", "syntax": "BattlEyeMegaKick <player>", "chat": "", "notes": "Binary string only in the Ghidra pass; no xref and not in DedicatedServerGame.ini."},
    {"name": "DestroyTargetVehicle", "tier": "destructive", "status": "blocked", "syntax": "DestroyTargetVehicle", "chat": "", "notes": "Do not expose as casual chat command; needs explicit confirmation/audit if ever enabled."},
    {"name": "DestroyTotem", "tier": "destructive", "status": "blocked", "syntax": "DestroyTotem", "chat": "", "notes": "Do not expose as casual chat command."},
    {"name": "DestroyPlaceable", "tier": "destructive", "status": "blocked", "syntax": "DestroyPlaceable", "chat": "", "notes": "Do not expose as casual chat command."},
    {"name": "DestroyEntireBuilding", "tier": "destructive", "status": "blocked", "syntax": "DestroyEntireBuilding", "chat": "", "notes": "Do not expose as casual chat command."},
    {"name": "DestroyBuildingPiece", "tier": "destructive", "status": "blocked", "syntax": "DestroyBuildingPiece", "chat": "", "notes": "Do not expose as casual chat command."},
    {"name": "obj", "tier": "console", "status": "cataloged", "syntax": "obj <args...>", "chat": "&gm dry obj <args...>", "notes": "Console command allowed by DedicatedServerGame.ini."},
    {"name": "FGL.ComponentAuditRequested", "tier": "console", "status": "cataloged", "syntax": "FGL.ComponentAuditRequested <args...>", "chat": "&gm dry FGL.ComponentAuditRequested <args...>", "notes": "Console command allowed by DedicatedServerGame.ini."},
]

CHEAT_SCRIPTS = {
    "LeaveMeAlone": ["EncountersDestroyAndDisableAll", "DestroyAllNpcs", "SetAutoSandstormSpawnEnabled 0", "DestroyAllSandStorms", "ServerExec sandworm.dune.Enabled 0"],
    "StartHitchVehicleTest": ["ServerExec t.maxfps 20", "ServerExec CauseHitchesPeriod 10", "ServerExec CauseHitchesHitchMS 1000", "ServerExec CauseHitches 1", "ServerExec t.UnsteadyFps 1", "CauseHitchesPeriod 20", "CauseHitchesHitchMS 200", "CauseHitches 1", "t.UnsteadyFps 1"],
    "StopHitchVehicleTest": ["ServerExec t.maxfps 0", "ServerExec CauseHitches 0", "ServerExec t.UnsteadyFps 0", "CauseHitches 0", "t.UnsteadyFps 0"],
    "AwardPlayerXP": ["AwardXP Combat 10000", "AwardXP Exploration 10000", "AwardXP Science 10000"],
}

STATUSES = {
    "wired-preview": "Dedicated wrapper exists; it publishes only when native GM execution and payload verification gates are enabled.",
    "gated-preview": "Preview is wired through a protected operational command; live publish has extra feature gates.",
    "probe-only": "Safe for route testing after the payload envelope is proven; not exposed as a normal admin action.",
    "cataloged": "Known native command name, no dedicated wrapper yet; use &gm dry for envelope previews.",
    "opt-in-only": "Candidate exists but is intentionally not wired by default.",
    "rejected": "Binary/config evidence says this is not a shipped dedicated-server GM command.",
    "blocked": "Known destructive command intentionally not executable through chat.",
}


def catalog():
    return {
        "confidence": "moderate",
        "execution": {
            "default": "preview-only",
            "liveRequiredGates": ["DUNE_ADMIN_GM_COMMANDS_ENABLED=true", "DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true"],
            "reason": "Native command names are mapped, but the live UDuneServerCommandSubsystem RabbitMQ payload contract is still unverified.",
        },
        "statuses": STATUSES,
        "commands": COMMANDS,
        "cheatScripts": [{"name": name, "commands": commands, "status": "cataloged"} for name, commands in sorted(CHEAT_SCRIPTS.items())],
    }


def markdown(data):
    lines = [
        "# Native GM / Cheat Command Catalog",
        "",
        f"Confidence: {data['confidence']}. Default execution: {data['execution']['default']}.",
        "",
        "| Command | Tier | Status | Syntax | Chat/Admin path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for command in data["commands"]:
        lines.append(f"| {command['name']} | {command['tier']} | {command['status']} | `{command['syntax']}` | {command['chat'] or 'none'} |")
    lines.extend(["", "## Cheat Scripts", ""])
    for script in data["cheatScripts"]:
        lines.append(f"- `{script['name']}`: " + "; ".join(f"`{line}`" for line in script["commands"]))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="List mapped native GM / cheat commands and wiring status.")
    parser.add_argument("--format", choices=("json", "markdown", "names"), default="json")
    parser.add_argument("--tier")
    parser.add_argument("--status")
    args = parser.parse_args()
    data = catalog()
    if args.tier:
        data["commands"] = [command for command in data["commands"] if command["tier"] == args.tier]
    if args.status:
        data["commands"] = [command for command in data["commands"] if command["status"] == args.status]
    if args.format == "markdown":
        print(markdown(data), end="")
    elif args.format == "names":
        for command in data["commands"]:
            print(command["name"])
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
