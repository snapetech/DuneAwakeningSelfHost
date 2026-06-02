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

BINARY_METHODS = [
    "UCharacterTransferCheatManager::CharacterTransfer_CancelCurrentTransfer",
    "UCharacterTransferCheatManager::CharacterTransfer_CheckTransferStatus",
    "UCharacterTransferCheatManager::CharacterTransfer_ExportData",
    "UCharacterTransferCheatManager::CharacterTransfer_FullFlow",
    "UCharacterTransferCheatManager::CharacterTransfer_ImportData",
    "UCharacterTransferCheatManager::CharacterTransfer_PreTransferCheck_InGame",
    "UCharacterTransferCheatManager::CharacterTransfer_PreTransferCheck_MainMenu",
    "UCharacterTransferCheatManager::CharacterTransfer_RequestReservation",
    "UClaimSystemCheatManager::ClaimSystemPrintCharacterPacks_Client",
    "UClaimSystemCheatManager::ClaimSystemPrintCharacterPacks_Server",
    "UClaimSystemCheatManager::ClaimSystemServerConsumeEntirePackForCharacter",
    "UClaimSystemCheatManager::ClaimSystemServerConsumeFrom2StacksFromPackForCharacter",
    "UClaimSystemCheatManager::ClaimSystemServerConsumeFromPackForCharacter",
    "UDuneCheatManager::AchievementTestPrintAllAchievements",
    "UDuneCheatManager::AchievementTestResetAllAchievements",
    "UDuneCheatManager::AddItemToInventory",
    "UDuneCheatManager::AddItemToVehicleInventory",
    "UDuneCheatManager::AddWeaponToInventory",
    "UDuneCheatManager::CheatCurrentDungeonCompletion",
    "UDuneCheatManager::ClearFlsCharacterData",
    "UDuneCheatManager::CompleteCurrentDungeon",
    "UDuneCheatManager::ConditionsLogRegisteredConditions",
    "UDuneCheatManager::ConditionsLogRegisteredConditionsForCurrentPlayer",
    "UDuneCheatManager::ConditionsLogRegisteredConditionsForEvent",
    "UDuneCheatManager::ConditionsLogRegisteredConditionsForEventAndCurrentPlayer",
    "UDuneCheatManager::ConditionsLogRegisteredConditionsForEventAndPlayerId",
    "UDuneCheatManager::ConditionsLogRegisteredConditionsForPlayerId",
    "UDuneCheatManager::ConditionsLogRegistrationKeys",
    "UDuneCheatManager::ConditionsLogSummary",
    "UDuneCheatManager::CoriolisPrintStoredSeeds",
    "UDuneCheatManager::CoriolisSetFarmSeed",
    "UDuneCheatManager::CoriolisSetMapSeed",
    "UDuneCheatManager::CoriolisSetPartitionSeed",
    "UDuneCheatManager::DeleteAllCompletionsForAllDungeonsByThisPlayer",
    "UDuneCheatManager::DeleteAllCompletionsForCurrentDungeon",
    "UDuneCheatManager::DeleteAllCompletionsForCurrentDungeonByThisPlayer",
    "UDuneCheatManager::DisplayFlsBattlegroupsServerBrowserInfo",
    "UDuneCheatManager::FlushActorPersistence",
    "UDuneCheatManager::GlobalDistributionPrintLootSettingsForCurrentLocation",
    "UDuneCheatManager::GlobalDistributionPrintTagsForCurrentLocation",
    "UDuneCheatManager::InitializeContractsAutoCompleteNamesList",
    "UDuneCheatManager::LogInAs",
    "UDuneCheatManager::MigrateMyVehicles",
    "UDuneCheatManager::OpenUIScene",
    "UDuneCheatManager::OverrideDungeonPlayerCount",
    "UDuneCheatManager::PatrolShipListSpawned",
    "UDuneCheatManager::PatrolShipTeleportToNearest",
    "UDuneCheatManager::PayAllTaxesForNearbyTotem",
    "UDuneCheatManager::PlayNow",
    "UDuneCheatManager::PrintListPlayersInFarm",
    "UDuneCheatManager::PrintMapSettings",
    "UDuneCheatManager::PrintNpcRespawnTimerHere",
    "UDuneCheatManager::PrintPlayerCap",
    "UDuneCheatManager::RaiseDatabaseException",
    "UDuneCheatManager::RequestFakeGroupTravel",
    "UDuneCheatManager::ResetCurrentDungeon",
    "UDuneCheatManager::ResetCurrentDungeonRoom",
    "UDuneCheatManager::ResetVendorStockData",
    "UDuneCheatManager::ReturnToHomeDimension",
    "UDuneCheatManager::SandBuildupSetOnAllObjects",
    "UDuneCheatManager::ScheduleMTXEvent",
    "UDuneCheatManager::ScheduleMTXEventJson",
    "UDuneCheatManager::SetEyesOfIbad",
    "UDuneCheatManager::SetUpItemList",
    "UDuneCheatManager::SpiceAddictionDecreaseSpiceAmount",
    "UDuneCheatManager::SpiceFieldForceSpawnNearestField",
    "UDuneCheatManager::SpiceFieldPrimeNearestField",
    "UDuneCheatManager::SpiceFieldPrimeRandomField",
    "UDuneCheatManager::SpiceFieldPrintNearestFieldInfo",
    "UDuneCheatManager::SpiceFieldReplenishNearestField",
    "UDuneCheatManager::SpiceFieldSetAgeForNearestField",
    "UDuneCheatManager::SpiceFieldSetFieldSpawnRate",
    "UDuneCheatManager::SpiceFieldSetSpawningEnabled",
    "UDuneCheatManager::SpiceFieldShowNearestFieldContents",
    "UDuneCheatManager::SpiceFieldTeleportToNearestField",
    "UDuneCheatManager::SpiceFieldUpdateGlobalRules",
    "UDuneCheatManager::TestDatabaseTransaction",
    "UDuneCheatManager::TestDatabaseTransactionDataChange",
    "UDuneCheatManager::TestIgwObjectFollowRemotePlayer",
    "UDuneCheatManager::TravelToDimension",
    "UDuneCheatManager::VisitFriend",
    "UDuneS2sCheatManager::EncountersRandomSetEnabled",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationAroundPlayersDelayInSec",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationAroundPlayersEnabled",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationAroundPlayersRadius",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationByAreaDelayInSecOverride",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationByAreaEnabled",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationOnWholeServerDelayInSec",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationOnWholeServerEnabled",
    "UDuneS2sCheatManager::EncountersRandomSetInstigationOnWholeServerForced",
    "UDuneS2sCheatManager::EncountersSetAreaLimitsEnabled",
    "UDuneS2sCheatManager::EncountersSetEnabled",
    "UDuneS2sCheatManager::EncountersSetSpawnCooldownEnabled",
    "UFlsCharacterTransfersCheatManager::FlsRestoreAllTokens",
    "UFlsCheatManager::GetFlsPlayerSession",
    "UFlsPlayerAccountCheatManager::FlsDeletePlayerAccountData",
    "UFlsPlayerAccountCheatManager::FlsSetIsDemoAccount",
    "UFlsPlayerAccountCheatManager::FlsUpdateDemoPlaytime",
    "UFlsPlayerRewardsCheatManager::FlsClaimPendingRewards",
    "UOvermapCheatManager::OvermapTravelToDimension",
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


def classify_binary_method(method):
    class_name, method_name = method.split("::", 1)
    command = next((item for item in COMMANDS if item["name"] == method_name), None)
    if command is not None:
        status = "allow-listed" if command["status"] != "rejected" else "rejected"
        tier = command["tier"]
        notes = command["notes"]
    elif method == "UOvermapCheatManager::OvermapTravelToDimension":
        status = "format-evidence-only"
        tier = "movement"
        notes = "Overmap-specific dimension travel; not in the shipped dedicated-server GM allow-list."
    else:
        status = "binary-only-unverified"
        tier = infer_tier(method_name)
        notes = "Recovered from cheat-manager method strings; not in the shipped dedicated-server GM allow-list."
    return {
        "class": class_name,
        "method": method_name,
        "qualifiedName": method,
        "tier": tier,
        "status": status,
        "notes": notes,
    }


def infer_tier(name):
    lowered = name.lower()
    if lowered.startswith("conditionslog") or "print" in lowered or "show" in lowered or "info" in lowered:
        return "inspection"
    if "teleport" in lowered or "travel" in lowered or "visit" in lowered or "returntohome" in lowered:
        return "movement"
    if "item" in lowered or "weapon" in lowered or "inventory" in lowered or "claim" in lowered or "reward" in lowered:
        return "inventory"
    if "seed" in lowered or "database" in lowered or "fls" in lowered or "transfer" in lowered:
        return "account-data"
    if "reset" in lowered or "delete" in lowered or "destroy" in lowered or "clear" in lowered:
        return "destructive"
    if "spicefield" in lowered or "encounter" in lowered or "vendor" in lowered:
        return "world-mutation"
    if "spawn" in lowered or "vehicle" in lowered:
        return "spawn"
    if "achievement" in lowered or "dungeon" in lowered or "contract" in lowered:
        return "progression"
    return "misc"


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
        "binaryMethods": [classify_binary_method(method) for method in BINARY_METHODS],
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
    lines.extend(["", "## Full Binary Cheat-Manager Methods", ""])
    lines.extend([
        f"Recovered method count: {len(data['binaryMethods'])}. These are binary-resident methods, not automatically callable dedicated-server commands.",
        "",
        "| Qualified method | Tier | Status |",
        "| --- | --- | --- |",
    ])
    for method in data["binaryMethods"]:
        lines.append(f"| `{method['qualifiedName']}` | {method['tier']} | {method['status']} |")
    lines.extend(["", "## Cheat Scripts", ""])
    for script in data["cheatScripts"]:
        lines.append(f"- `{script['name']}`: " + "; ".join(f"`{line}`" for line in script["commands"]))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="List mapped native GM / cheat commands and wiring status.")
    parser.add_argument("--format", choices=("json", "markdown", "names"), default="json")
    parser.add_argument("--tier")
    parser.add_argument("--status")
    parser.add_argument("--include-binary-methods", action="store_true", help="Include recovered binary-only cheat-manager methods in names output.")
    args = parser.parse_args()
    data = catalog()
    if args.tier:
        data["commands"] = [command for command in data["commands"] if command["tier"] == args.tier]
        data["binaryMethods"] = [method for method in data["binaryMethods"] if method["tier"] == args.tier]
    if args.status:
        data["commands"] = [command for command in data["commands"] if command["status"] == args.status]
        data["binaryMethods"] = [method for method in data["binaryMethods"] if method["status"] == args.status]
    if args.format == "markdown":
        print(markdown(data), end="")
    elif args.format == "names":
        for command in data["commands"]:
            print(command["name"])
        if args.include_binary_methods:
            for method in data["binaryMethods"]:
                print(method["qualifiedName"])
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
