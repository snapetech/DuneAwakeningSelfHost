#!/usr/bin/env python3
import configparser
import concurrent.futures
import datetime
import hmac
import html
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2
import psycopg2.extras


ROOT = pathlib.Path(os.environ.get("ADMIN_WORKSPACE", "/workspace"))
sys.path.insert(0, str(ROOT / "scripts"))

from dune_gm_command import build_envelope, publish_command, publish_command_management

CONFIG_ROOT = ROOT / "config"
ENV_FILE = ROOT / ".env"
BACKUP_ROOT = ROOT / "backups" / "admin-panel"
STATIC_ROOT = ROOT / "admin" / "static"
PLAYER_PEAKS_FILE = pathlib.Path(os.environ.get("DUNE_PLAYER_PEAKS_FILE", str(BACKUP_ROOT / "player-peaks.json")))
ADMIN_PANEL_BUILD = "20260520-hagga-clean-map-south"
AUDIT_LOG = BACKUP_ROOT / "audit.jsonl"
STEAM_PROFILE_CACHE_FILE = BACKUP_ROOT / "steam-profiles.json"
AUDIT_MAX_BYTES = int(os.environ.get("DUNE_ADMIN_AUDIT_MAX_BYTES", str(5 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS", "10"))
MAX_ITEM_STACK_SIZE = int(os.environ.get("DUNE_ADMIN_MAX_ITEM_STACK_SIZE", "1000000"))
AUDIT_EVENT_LIMIT = int(os.environ.get("DUNE_ADMIN_AUDIT_EVENT_LIMIT", "100"))
HAGGA_MAP_MIN_X = float(os.environ.get("DUNE_HAGGA_MAP_MIN_X", "-457200"))
HAGGA_MAP_MAX_X = float(os.environ.get("DUNE_HAGGA_MAP_MAX_X", "355600"))
HAGGA_MAP_MIN_Y = float(os.environ.get("DUNE_HAGGA_MAP_MIN_Y", "-457200"))
HAGGA_MAP_MAX_Y = float(os.environ.get("DUNE_HAGGA_MAP_MAX_Y", "355600"))
HAGGA_MAP_INVERT_X = os.environ.get("DUNE_HAGGA_MAP_INVERT_X", "false").lower() not in ("0", "false", "no", "off")
HAGGA_MAP_INVERT_Y = os.environ.get("DUNE_HAGGA_MAP_INVERT_Y", "false").lower() not in ("0", "false", "no", "off")
HAGGA_MAP_SHOW_RETURN_POINTS = os.environ.get("DUNE_HAGGA_MAP_SHOW_RETURN_POINTS", "false").lower() in ("1", "true", "yes", "on")
HAGGA_MAP_IMAGE_MIN_U = float(os.environ.get("DUNE_HAGGA_MAP_IMAGE_MIN_U", "0"))
HAGGA_MAP_IMAGE_MAX_U = float(os.environ.get("DUNE_HAGGA_MAP_IMAGE_MAX_U", "1"))
HAGGA_MAP_IMAGE_MIN_V = float(os.environ.get("DUNE_HAGGA_MAP_IMAGE_MIN_V", "0"))
HAGGA_MAP_IMAGE_MAX_V = float(os.environ.get("DUNE_HAGGA_MAP_IMAGE_MAX_V", "1"))
ADMIN_REFERENCE_LIMIT = int(os.environ.get("DUNE_ADMIN_REFERENCE_LIMIT", "200"))
CHARACTER_SEARCH_LIMIT = int(os.environ.get("DUNE_ADMIN_CHARACTER_SEARCH_LIMIT", "100"))
STEAM_PROFILE_CACHE_TTL_SECONDS = int(os.environ.get("DUNE_ADMIN_STEAM_PROFILE_CACHE_TTL_SECONDS", str(24 * 60 * 60)))
STEAM_PROFILE_LOOKUP_ENABLED = os.environ.get("DUNE_ADMIN_STEAM_PROFILE_LOOKUP_ENABLED", "true").lower() in ("1", "true", "yes", "on")
DATABASE = os.environ.get("DUNE_DATABASE", "dune_sb_1_4_0_0")
ADMIN_TOKEN = os.environ.get("DUNE_ADMIN_TOKEN", "")
MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_MUTATIONS_ENABLED", "true").lower() == "true"
ITEM_GRANTS_ENABLED = os.environ.get("DUNE_ADMIN_ITEM_GRANTS_ENABLED", "true").lower() == "true"
MAX_BODY_BYTES = int(os.environ.get("DUNE_ADMIN_MAX_BODY_BYTES", "65536"))
ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.environ.get("DUNE_ADMIN_ALLOWED_HOSTS", "127.0.0.1:18080,localhost:18080,admin.example.test,admin-panel:8080").split(",")
    if host.strip()
}
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_FAILURE_LIMIT = 5
AUTH_FAILURES = {}
AUDIT_LOCK = threading.Lock()
STEAM_PROFILE_CACHE_LOCK = threading.Lock()
CONFIRM_RESET_KEYSTONES = "RESET KEYSTONES"
CONFIRM_DELETE_ITEM = "DELETE ITEM"
CONFIRM_SET_STACK = "SET STACK"
CONFIRM_GM_COMMAND = "RUN GM COMMAND"
CONFIRM_TYPED_KNOBS = "WRITE TYPED KNOBS"
CONFIRM_BUNDLE_MUTATION = "EXECUTE BUNDLE"
CONFIRM_PLAYER_RECOVERY = "MOVE OFFLINE PLAYER"
CONFIRM_REPUTATION_MUTATION = "WRITE REPUTATION"
CONFIRM_JOURNEY_MUTATION = "WRITE JOURNEY"
CONFIRM_FACTION_MUTATION = "CHANGE FACTION"
CONFIRM_LANDSRAAD_MUTATION = "WRITE LANDSRAAD"
CONFIRM_RESPAWN_MUTATION = "DELETE RESPAWN"
CONFIRM_GUILD_MUTATION = "WRITE GUILD"
CONFIRM_MARKER_MUTATION = "DELETE MARKERS"
CONFIRM_LANDCLAIM_MUTATION = "WRITE LANDCLAIM"
CONFIRM_EXCHANGE_MUTATION = "WRITE EXCHANGE"
CONFIRM_PLAYER_TAG_MUTATION = "WRITE PLAYER TAGS"
CONFIRM_ACCESS_CODE_MUTATION = "WRITE ACCESS CODES"
CONFIRM_COMMUNINET_MUTATION = "WRITE COMMUNINET"
CONFIRM_TUTORIAL_MUTATION = "WRITE TUTORIAL"
CONFIRM_PERMISSION_MUTATION = "WRITE PERMISSION"
CONFIRM_VENDOR_MUTATION = "WRITE VENDOR"
CONFIRM_CHARACTER_SWAP = "SWAP CHARACTER"
CATALOG_ENABLED = os.environ.get("DUNE_ADMIN_CATALOG_ENABLED", "true").lower() in ("1", "true", "yes", "on")
TYPED_KNOBS_ENABLED = os.environ.get("DUNE_ADMIN_TYPED_KNOBS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
EVENT_EXECUTION_ENABLED = os.environ.get("DUNE_ADMIN_EVENT_EXECUTION_ENABLED", "false").lower() in ("1", "true", "yes", "on")
BUNDLE_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
REPUTATION_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
JOURNEY_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
FACTION_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_FACTION_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
LANDSRAAD_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
RESPAWN_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
GUILD_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_GUILD_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
MARKER_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_MARKER_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
LANDCLAIM_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
EXCHANGE_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
PLAYER_TAG_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
ACCESS_CODE_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
COMMUNINET_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
TUTORIAL_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
PERMISSION_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
VENDOR_MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED", "false").lower() in ("1", "true", "yes", "on")
CHARACTER_SWAP_ENABLED = os.environ.get("DUNE_ADMIN_CHARACTER_SWAP_ENABLED", "false").lower() in ("1", "true", "yes", "on")
ANNOUNCEMENT_STATE_FILE = BACKUP_ROOT / "announcements.json"
RESTART_STATE_FILE = BACKUP_ROOT / "restart-jobs.json"
EVENT_STATE_FILE = BACKUP_ROOT / "events.json"
ADMIN_DIGEST_STATE_FILE = ROOT / "backups" / "admin-bot" / "player-presence.json"
ANNOUNCEMENT_LOCK = threading.Lock()
RESTART_LOCK = threading.Lock()
EVENT_LOCK = threading.Lock()
ANNOUNCEMENT_THREAD_STARTED = False
ANNOUNCEMENT_POLL_SECONDS = 5
ANNOUNCEMENT_MAX_MESSAGE_BYTES = int(os.environ.get("DUNE_ADMIN_ANNOUNCEMENT_MAX_MESSAGE_BYTES", "500"))
ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45"))
ANNOUNCEMENT_COMMAND = os.environ.get("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh"))
RESTART_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_COMMAND_TIMEOUT_SECONDS", "1800"))
RESTART_COMMAND = os.environ.get("DUNE_ADMIN_RESTART_COMMAND", str(ROOT / "scripts" / "restart-target.sh"))
RESTART_ONLINE_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_ONLINE_TIMEOUT_SECONDS", "300"))
RESTART_ONLINE_POLL_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_ONLINE_POLL_SECONDS", "5"))
RESTART_RECOVERY_ENABLED = os.environ.get("DUNE_ADMIN_RESTART_RECOVERY_ENABLED", "true").lower() in ("1", "true", "yes", "on")
RESTART_RECOVERY_COMMAND = os.environ.get("DUNE_ADMIN_RESTART_RECOVERY_COMMAND", str(ROOT / "scripts" / "watch-maps.sh"))
RESTART_RECOVERY_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_RECOVERY_TIMEOUT_SECONDS", "900"))
RESTART_DISCONNECT_WAIT_SECONDS = float(os.environ.get("DUNE_ADMIN_RESTART_DISCONNECT_WAIT_SECONDS", "5"))
MAINTENANCE_BACKUP_ENABLED = os.environ.get("DUNE_ADMIN_MAINTENANCE_BACKUP_ENABLED", "true").lower() == "true"
MAINTENANCE_REPLICA_SNAPSHOT_ENABLED = os.environ.get("DUNE_ADMIN_MAINTENANCE_REPLICA_SNAPSHOT_ENABLED", "true").lower() == "true"
MAINTENANCE_REPLICA_SNAPSHOT_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_MAINTENANCE_REPLICA_SNAPSHOT_TIMEOUT_SECONDS", "300"))
DOCKER_SOCKET = os.environ.get("DUNE_RESTART_DOCKER_SOCKET", "/var/run/docker.sock")
DOCKER_COMPOSE_PROJECT = os.environ.get("DUNE_RESTART_COMPOSE_PROJECT", "dune_server")
ANNOUNCEMENT_DELAYS = {
    "immediate": 0,
    "30s": 30,
    "60s": 60,
    "5min": 5 * 60,
    "10min": 10 * 60,
    "15min": 15 * 60,
    "30min": 30 * 60,
    "60min": 60 * 60,
    "1hr": 60 * 60,
    "2hr": 2 * 60 * 60,
    "3hr": 3 * 60 * 60,
    "4hr": 4 * 60 * 60,
    "6hr": 6 * 60 * 60,
    "12hr": 12 * 60 * 60,
}
GAME_MAP_SERVICES = [
    "survival", "overmap", "arrakeen", "harko-village", "testing-hephaestus", "testing-carthag", "testing-waterfat",
    "deep-desert", "proces-verbal", "lostharvest-ecolab-a", "lostharvest-ecolab-b", "lostharvest-forgottenlab",
    "art-of-kanly", "dungeon-hephaestus", "dungeon-oldcarthag", "faction-outpost-atre", "faction-outpost-hark",
    "heighliner-dungeon", "ecolab-green-089", "ecolab-green-152", "ecolab-green-024", "ecolab-green-195",
    "ecolab-green-136", "overland-m-01", "overland-s-04", "overland-s-06", "bandit-fortress",
    "overland-s-07", "overland-s-08", "dungeon-thepit",
]
SERVICE_LAYER_SERVICES = ["rmq-auth-shim", "text-router", "gateway", "director"]
ALL_RESTART_SAFE_SERVICES = GAME_MAP_SERVICES + SERVICE_LAYER_SERVICES
RESTART_TARGETS = {
    "all": {"label": "All Restart-Safe Components", "services": ALL_RESTART_SAFE_SERVICES},
    "core": {"label": "Restart-Safe Core Services", "services": SERVICE_LAYER_SERVICES},
    "service-layer": {"label": "Service Layer", "services": SERVICE_LAYER_SERVICES},
    "game-all": {"label": "All Game Maps", "services": GAME_MAP_SERVICES},
    "survival": {"label": "Hagga Basin / Survival", "services": ["survival"]},
    "overmap": {"label": "Overland Map", "services": ["overmap"]},
    "arrakeen": {"label": "Arrakeen", "services": ["arrakeen"]},
    "harko-village": {"label": "Harko Village", "services": ["harko-village"]},
    "deep-desert": {"label": "Deep Desert", "services": ["deep-desert"]},
}

GM_COMMANDS_ENABLED = os.environ.get("DUNE_ADMIN_GM_COMMANDS_ENABLED", "false").lower() == "true"
GM_COMMAND_PAYLOAD_VERIFIED = os.environ.get("DUNE_GM_COMMAND_PAYLOAD_VERIFIED", "false").lower() == "true"
GM_ALLOWED_COMMANDS = (
    "obj",
    "FGL.ComponentAuditRequested",
)
GM_ALLOWED_GM_COMMANDS = (
    "AddItemToInventory",
    "AddBasicInventoryToCharacter",
    "SpawnVehicle",
    "PatrolShipTeleportToNearest",
    "TeleportTo",
    "TeleportToMap",
    "TeleportToExact",
    "TeleportToPlayer",
    "TeleportToVehicleSpawner",
    "TeleportToSandworm",
    "TeleportToPersonalMarker",
    "TravelTo",
    "TravelToDimension",
    "Fly",
    "Ghost",
    "Walk",
    "RemoveSessionMember",
    "KickLobbyMember",
    "DestroyTargetVehicle",
    "DestroyTotem",
    "DestroyPlaceable",
    "DestroyEntireBuilding",
    "DestroyBuildingPiece",
    "PrintPos",
)
GM_COMMAND_NOTES = {
    "AddItemToInventory": "Player inventory grant command exposed by DuneCheatManager. Args observed in scripts: <template_id> <count> [quality].",
    "AddBasicInventoryToCharacter": "Likely fills or creates a basic inventory set for the target character. Payload route not verified.",
    "SpawnVehicle": "Spawns a vehicle for/near the admin context. Vehicle template args still need validation.",
    "PatrolShipTeleportToNearest": "Teleports to nearest patrol ship context.",
    "TeleportTo": "Teleport helper; exact argument contract still needs validation.",
    "TeleportToMap": "Map teleport helper; probably map name plus optional location.",
    "TeleportToExact": "Exact coordinate teleport helper. Strings show this as a cheat/admin UI route.",
    "TeleportToPlayer": "Teleport to a target player.",
    "TeleportToVehicleSpawner": "Teleport to a vehicle spawner.",
    "TeleportToSandworm": "Teleport to sandworm location/context.",
    "TeleportToPersonalMarker": "Teleport to the player's personal marker.",
    "TravelTo": "Travel command exposed by server command/cheat path.",
    "TravelToDimension": "Travel to a map dimension.",
    "Fly": "Enable fly movement on the admin player.",
    "Ghost": "Enable collision-free movement on the admin player.",
    "Walk": "Return movement mode to normal walking.",
    "RemoveSessionMember": "Best current candidate for a soft targeted disconnect. Keep behind GM payload verification and player-disconnect execution gates.",
    "KickLobbyMember": "Fallback targeted lobby kick candidate if RemoveSessionMember is ineffective.",
    "DestroyTargetVehicle": "Destroys targeted vehicle.",
    "DestroyTotem": "Destroys targeted totem.",
    "DestroyPlaceable": "Destroys targeted placeable.",
    "DestroyEntireBuilding": "Destroys entire targeted building.",
    "DestroyBuildingPiece": "Destroys targeted building piece.",
    "PrintPos": "Prints current position; safest candidate for route testing once payload format is known.",
}
GM_CHEAT_SCRIPTS = {
    "LeaveMeAlone": [
        "EncountersDestroyAndDisableAll",
        "DestroyAllNpcs",
        "SetAutoSandstormSpawnEnabled 0",
        "DestroyAllSandStorms",
        "ServerExec sandworm.dune.Enabled 0",
    ],
    "StartHitchVehicleTest": [
        "ServerExec t.maxfps 20",
        "ServerExec CauseHitchesPeriod 10",
        "ServerExec CauseHitchesHitchMS 1000",
        "ServerExec CauseHitches 1",
        "ServerExec t.UnsteadyFps 1",
        "CauseHitchesPeriod 20",
        "CauseHitchesHitchMS 200",
        "CauseHitches 1",
        "t.UnsteadyFps 1",
    ],
    "StopHitchVehicleTest": [
        "ServerExec t.maxfps 0",
        "ServerExec CauseHitches 0",
        "ServerExec t.UnsteadyFps 0",
        "CauseHitches 0",
        "t.UnsteadyFps 0",
    ],
    "AwardPlayerXP": [
        "AwardXP Combat 10000",
        "AwardXP Exploration 10000",
        "AwardXP Science 10000",
    ],
}
GM_CHAT_COMMANDS = (
    {"command": "&gm help", "tier": "safe", "notes": "List wired GM chat commands."},
    {"command": "&gm routes", "tier": "safe", "notes": "Resolve current admin map route and gate status."},
    {"command": "&gm mark [name]", "tier": "movement", "notes": "Save current admin location; default marker is location0."},
    {"command": "&gm marks", "tier": "movement", "notes": "List saved admin markers."},
    {"command": "&gm recall [name]", "tier": "movement", "notes": "Preview/send teleport back to a saved marker."},
    {"command": "&gm where <player>", "tier": "player", "notes": "Resolve player online state and location."},
    {"command": "&gm goto <player>", "tier": "movement", "notes": "Preview/send admin teleport to player."},
    {"command": "&gm bring <player>", "tier": "movement", "notes": "Preview/send target teleport to admin."},
    {"command": "&gm unstuck <player> [mark]", "tier": "player", "notes": "Preview/send target teleport to saved marker or admin location."},
    {"command": "&gm item <player> <template> [count] [quality]", "tier": "inventory", "notes": "Preview native item grant payload."},
    {"command": "&gm kit <player> [basic]", "tier": "inventory", "notes": "Preview native basic kit payload."},
    {"command": "&gm xp <player> <track> <amount> [add|set] [level]", "tier": "mutation", "notes": "Resolve XP mutation body; execute through audited panel API."},
    {"command": "&gm map <map> [dimension]", "tier": "movement", "notes": "Preview/send native TeleportToMap."},
    {"command": "&gm travel <map> [location]", "tier": "movement", "notes": "Preview/send native TravelTo."},
    {"command": "&gm dimension <map> <dimension>", "tier": "movement", "notes": "Preview/send native TravelToDimension."},
    {"command": "&gm patrol", "tier": "movement", "notes": "Preview/send PatrolShipTeleportToNearest."},
    {"command": "&gm sandworm", "tier": "movement", "notes": "Preview/send TeleportToSandworm."},
    {"command": "&gm marker", "tier": "movement", "notes": "Preview/send TeleportToPersonalMarker."},
    {"command": "&gm vehicle <template> [args...]", "tier": "spawn", "notes": "Preview/send SpawnVehicle; exact args still need validation."},
    {"command": "&disconnect <player>", "tier": "player", "notes": "Preview/send gated targeted session removal; defaults to RemoveSessionMember."},
)
GM_PANEL_PRESETS = (
    {"label": "Print Position", "command": "PrintPos", "args": "", "risk": "safe"},
    {"label": "Teleport To Player", "command": "TeleportToPlayer", "args": "<player>", "risk": "movement"},
    {"label": "Teleport Exact", "command": "TeleportToExact", "args": "<x> <y> <z>", "risk": "movement"},
    {"label": "Add Item", "command": "AddItemToInventory", "args": "<player> <template> 1", "risk": "inventory"},
    {"label": "Basic Kit", "command": "AddBasicInventoryToCharacter", "args": "<player>", "risk": "inventory"},
    {"label": "Teleport Map", "command": "TeleportToMap", "args": "<map> [dimension]", "risk": "movement"},
    {"label": "Travel To", "command": "TravelTo", "args": "<map> [location]", "risk": "movement"},
    {"label": "Travel Dimension", "command": "TravelToDimension", "args": "<map> <dimension>", "risk": "movement"},
    {"label": "Nearest Patrol Ship", "command": "PatrolShipTeleportToNearest", "args": "", "risk": "movement"},
    {"label": "Sandworm", "command": "TeleportToSandworm", "args": "", "risk": "movement"},
    {"label": "Personal Marker", "command": "TeleportToPersonalMarker", "args": "", "risk": "movement"},
    {"label": "Spawn Vehicle", "command": "SpawnVehicle", "args": "<template>", "risk": "spawn"},
    {"label": "Fly", "command": "Fly", "args": "", "risk": "movement"},
    {"label": "Ghost", "command": "Ghost", "args": "", "risk": "movement"},
    {"label": "Walk", "command": "Walk", "args": "", "risk": "movement"},
    {"label": "Soft Disconnect", "command": "RemoveSessionMember", "args": "<player>", "risk": "player"},
    {"label": "Lobby Kick", "command": "KickLobbyMember", "args": "<player>", "risk": "player"},
)

ALLOWED_CONFIGS = {
    "director.ini": CONFIG_ROOT / "director.ini",
    "gateway.ini": CONFIG_ROOT / "gateway.ini",
    "rabbitmq-admin.conf": CONFIG_ROOT / "rabbitmq-admin.conf",
    "rabbitmq-game.conf": CONFIG_ROOT / "rabbitmq-game.conf",
    "UserEngine.ini": CONFIG_ROOT / "UserEngine.ini",
    "UserGame.ini": CONFIG_ROOT / "UserGame.ini",
}

DIRECTOR_TRANSFER_RULESETS = (
    "0",
    "1",
    "2",
    "3",
)

DIRECTOR_TRANSFER_RULESET_LABELS = {
    "0": "DenyAll",
    "1": "AllowFromPrivateOnly",
    "2": "AllowFromOfficialOnly",
    "3": "AllowFromPrivateAndOfficial",
    "DenyAll": "DenyAll",
    "AllowFromPrivateOnly": "AllowFromPrivateOnly",
    "AllowFromOfficialOnly": "AllowFromOfficialOnly",
    "AllowFromPrivateAndOfficial": "AllowFromPrivateAndOfficial",
}

DIRECTOR_TRANSFER_RULESET_VALUES = {
    "DenyAll": "0",
    "AllowFromPrivateOnly": "1",
    "AllowFromOfficialOnly": "2",
    "AllowFromPrivateAndOfficial": "3",
}

DIRECTOR_TRANSFER_SETTINGS = {
    "ShouldDeleteOriginCharactersDuringTransfers": {"type": "bool", "default": "true", "why": "Deletes the origin character after a successful transfer into this battlegroup."},
    "AcceptOutgoingCharacterTransfers": {"type": "bool", "default": "true", "why": "Allows characters on this battlegroup to transfer out."},
    "IncomingCharacterTransfers": {"type": "ruleset", "default": "0", "why": "Controls which origin server types can transfer characters into this battlegroup. Director build 1963158 expects numeric enum values: 0=DenyAll, 1=AllowFromPrivateOnly, 2=AllowFromOfficialOnly, 3=AllowFromPrivateAndOfficial."},
    "ExportCharacterTimeout": {"type": "int", "default": "900", "why": "Seconds before the export query times out."},
    "ImportCharacterTimeout": {"type": "int", "default": "900", "why": "Seconds before the import query times out."},
    "FreeToTransferCharactersFrom": {"type": "bool", "default": "false", "why": "Skips transfer token cost for transfers from this battlegroup."},
    "FreeToTransferCharactersTo": {"type": "bool", "default": "false", "why": "Skips transfer token cost for transfers to this battlegroup."},
    "ValidateBeforeImportCharacterTimeout": {"type": "int", "default": "180", "why": "Seconds before canceling a transfer stuck in validation before import starts."},
    "ActiveTransfersResolveProcessFrequencySeconds": {"type": "int", "default": "10", "why": "Seconds between resolving unhandled active transfers."},
    "CharacterTransferDbFunctionTimeLogThresholdMs": {"type": "int", "default": "10000", "why": "Milliseconds before character transfer DB function timing is logged."},
}

PLAYER_ONLINE_STATE_SECTION = "/Script/DuneSandbox.PlayerOnlineStateSettings"
PLAYER_ONLINE_STATE_SETTINGS = {
    "m_DefaultReconnectGracePeriodSeconds": {"type": "int", "default": "0", "why": "Seconds a disconnected player can be treated as recently online on normal maps. Use 0 for immediate logout persistence expiry."},
    "m_OvermapReturnGracePeriodSeconds": {"type": "int", "default": "0", "why": "Seconds allowed for returning from overmap disconnects. Use 0 for Steam Deck suspend-friendly immediate exit."},
    "m_InstancedMapReconnectGracePeriodSeconds": {"type": "int", "default": "0", "why": "Seconds a disconnected player can reconnect to instanced maps. Use 0 for immediate instanced-map logout persistence expiry."},
}

TYPED_CONFIG_KNOBS = {
    "spiceDeepDesertCaps": {
        "label": "Deep Desert spice caps",
        "file": "UserGame.ini",
        "section": "/Script/DuneSandbox.SpiceHarvestingSystem",
        "key": "m_PerMapSystemSettings",
        "type": "spice_caps",
        "restart": True,
        "confidence": "high",
        "risk": "medium",
        "why": "Caps materialize in dune.spicefield_types and resourcefield_state after map restart.",
        "default": '(("DeepDesert_1", (m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=60,MaxGloballyActive=60)),((Name="Medium"), (MaxGloballyPrimed=12,MaxGloballyActive=12)),((Name="Large"), (MaxGloballyPrimed=1,MaxGloballyActive=1))))),("Survival_1", (m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=5,MaxGloballyActive=5))))))',
    },
    "sandstormEnabled": {"label": "Sandstorm enabled", "file": "UserEngine.ini", "section": "ConsoleVariables", "key": "Sandstorm.Enabled", "type": "bool01", "restart": True, "confidence": "high", "risk": "low", "why": "Console variable is already present in config/UserEngine.ini.", "default": "1"},
    "sandstormTreasureEnabled": {"label": "Sandstorm treasure enabled", "file": "UserEngine.ini", "section": "ConsoleVariables", "key": "Sandstorm.Treasure.Enabled", "type": "bool01", "restart": True, "confidence": "moderate", "risk": "medium", "why": "Console variable is present; treasure runtime effect still needs live validation.", "default": "1"},
    "coriolisAutoSpawnEnabled": {"label": "Coriolis auto-spawn", "file": "UserGame.ini", "section": "/Script/DuneSandbox.SandStormConfig", "key": "m_bCoriolisAutoSpawnEnabled", "type": "bool", "restart": True, "confidence": "high", "risk": "medium", "why": "Shipped config key controls Coriolis auto-spawn. Cycle and wipe fields are deliberately excluded.", "default": "False"},
    "globalMiningMultiplier": {"label": "Player mining multiplier", "file": "UserEngine.ini", "section": "ConsoleVariables", "key": "Dune.GlobalMiningOutputMultiplier", "type": "float", "min": 0, "max": 100, "restart": True, "confidence": "high", "risk": "low", "why": "Console variable is already present in config/UserEngine.ini.", "default": "1.0"},
    "vehicleMiningMultiplier": {"label": "Vehicle mining multiplier", "file": "UserEngine.ini", "section": "ConsoleVariables", "key": "Dune.GlobalVehicleMiningOutputMultiplier", "type": "float", "min": 0, "max": 100, "restart": True, "confidence": "high", "risk": "low", "why": "Console variable is already present in config/UserEngine.ini.", "default": "1.0"},
    "pvpResourceMultiplier": {"label": "PvP resource multiplier", "file": "UserEngine.ini", "section": "ConsoleVariables", "key": "SecurityZones.PvpResourceMultiplier", "type": "float", "min": 0, "max": 100, "restart": True, "confidence": "high", "risk": "low", "why": "Console variable is already present in config/UserEngine.ini.", "default": "2.5"},
    "forcePvpAllPartitions": {"label": "Force PvP on all partitions", "file": "UserGame.ini", "section": "/Script/DuneSandbox.PvpPveSettings", "key": "m_bShouldForceEnablePvpOnAllPartitions", "type": "bool", "restart": True, "confidence": "high", "risk": "medium", "why": "Documented shipped PvP/PvE setting.", "default": "False"},
    "securityZonesEnabled": {"label": "Security zones enabled", "file": "UserGame.ini", "section": "/Script/DuneSandbox.SecurityZonesSubsystem", "key": "m_bAreSecurityZonesEnabled", "type": "bool", "restart": True, "confidence": "high", "risk": "medium", "why": "Documented shipped security-zone setting.", "default": "True"},
    "characterRecustomizationCost": {"label": "Character recustomization cost", "file": "UserGame.ini", "section": "/Script/DuneSandbox.CharacterRecustomizerSubsystem", "key": "m_CostAmount", "type": "int", "min": 0, "max": 1000000000, "restart": True, "confidence": "high", "risk": "low", "why": "Shipped CharacterRecustomizerSubsystem Solaris cost. Set 0 to make recustomization free.", "default": "5000"},
    "buildingShelterThreshold": {"label": "Building shelter threshold", "file": "UserGame.ini", "section": "/Script/DuneSandbox.ShelterSettings", "key": "m_BuildingShelterThreshold", "type": "float", "min": 0, "max": 1, "restart": True, "confidence": "moderate", "risk": "experimental", "why": "Shipped ShelterSettings key; hydration/base effect needs live validation.", "default": "0.5"},
    "placeableShelterThreshold": {"label": "Placeable shelter threshold", "file": "UserGame.ini", "section": "/Script/DuneSandbox.ShelterSettings", "key": "m_PlaceableShelterThreshold", "type": "float", "min": 0, "max": 1, "restart": True, "confidence": "moderate", "risk": "experimental", "why": "Shipped ShelterSettings key; hydration/base effect needs live validation.", "default": "0.5"},
    "shelteredProtectionThreshold": {"label": "Sheltered hydration protection threshold", "file": "UserGame.ini", "section": "/Script/DuneSandbox.HydrationSubsystem", "key": "ShelteredProtectionThreshold", "type": "float", "min": 0, "max": 1, "restart": True, "confidence": "low", "risk": "experimental", "why": "Candidate override; owner/asset path is not proven.", "default": "0.5"},
}

CATALOG_GROUPS = ("Deep Desert", "Economy/Admin", "World Rules", "GM/RabbitMQ", "Limits")

ENV_KEY_DEFINITIONS = {
    "DUNE_STEAM_SERVER_DIR": {"group": "Install", "secret": False, "restart": False, "why": "Local Steam tool path used by image loading and preflight scripts."},
    "DUNE_IMAGE_TAG": {"group": "Install", "secret": False, "restart": True, "why": "Funcom container image tag used by Compose services."},
    "DUNE_RESTART_STEAM_UPDATE_MODE": {"group": "Install", "secret": False, "restart": False, "why": "Steam package refresh mode during maintenance: auto uses the running Steam client first, steamcmd is for headless hosts, none disables refresh."},
    "DUNE_RESTART_STEAM_CLIENT_TRIGGER": {"group": "Install", "secret": False, "restart": False, "why": "When a Steam client is running, ask it to validate/update the self-hosted server app before DASH ingests images."},
    "DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS": {"group": "Install", "secret": False, "restart": False, "why": "Maximum time maintenance waits for the Steam client appmanifest/download state to settle before image ingest."},
    "DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS": {"group": "Install", "secret": False, "restart": False, "why": "Minimum wait after asking the Steam client to validate/update, so queued client work can begin."},
    "DUNE_STEAM_CLIENT_COMMAND": {"group": "Install", "secret": False, "restart": False, "why": "Steam client executable used for steam:// validation requests on desktop Steam hosts."},
    "DUNE_RESTART_STEAMCMD_UPDATE": {"group": "Install", "secret": False, "restart": False, "why": "Runs SteamCMD app_update for the self-hosted server tool during maintenance before DASH loads image tarballs."},
    "DUNE_RESTART_STEAMCMD_REQUIRED": {"group": "Install", "secret": False, "restart": False, "why": "When true, maintenance fails instead of starting from the old package if SteamCMD cannot run."},
    "DUNE_RESTART_STEAMCMD_HELPER_IMAGE": {"group": "Install", "secret": False, "restart": False, "why": "Container image used to run SteamCMD when the restart hook is operating through the Docker socket helper."},
    "DUNE_STEAM_APP_ID": {"group": "Install", "secret": False, "restart": False, "why": "Steam app id for the Dune: Awakening Self-Hosted Server tool."},
    "DUNE_STEAM_LOGIN": {"group": "Install", "secret": False, "restart": False, "why": "SteamCMD login name. Use anonymous if the tool allows anonymous updates."},
    "DUNE_STEAM_PASSWORD": {"group": "Secrets", "secret": True, "restart": False, "why": "Optional SteamCMD password for non-anonymous tool updates."},
    "DUNE_STEAMCMD_COMMAND": {"group": "Install", "secret": False, "restart": False, "why": "SteamCMD executable name or absolute path for host-side maintenance updates."},
    "DUNE_STEAMCMD_VALIDATE": {"group": "Install", "secret": False, "restart": False, "why": "Adds validate to SteamCMD app_update during maintenance."},
    "DUNE_STEAMCMD_TIMEOUT_SECONDS": {"group": "Install", "secret": False, "restart": False, "why": "Maximum time allowed for SteamCMD package update before the restart hook fails or skips based on required mode."},
    "WORLD_NAME": {"group": "World", "secret": False, "restart": True, "why": "Public display name shown by Director/Text Router/Gateway."},
    "WORLD_UNIQUE_NAME": {"group": "World", "secret": False, "restart": True, "why": "Stable internal server/world identifier used for registration and routing."},
    "DUNE_SERVER_DISPLAY_NAME": {"group": "World", "secret": False, "restart": True, "why": "Optional in-engine server display name injected as Bgd.ServerDisplayName. Leave blank to reuse WORLD_NAME."},
    "WORLD_REGION": {"group": "World", "secret": False, "restart": True, "why": "Farm region/datacenter label passed into game services."},
    "EXTERNAL_ADDRESS": {"group": "Network", "secret": False, "restart": True, "why": "Address advertised to clients/FLS for game traffic."},
    "DUNE_SERVER_LOGIN_PASSWORD": {"group": "Access", "secret": False, "restart": True, "why": "Optional player login password passed into game server console variables. Visible here so trusted operators can share and rotate it."},
    "FLS_SECRET": {"group": "Secrets", "secret": True, "restart": True, "why": "Funcom Live Services host token. Required for service auth and routing."},
    "POSTGRES_SUPER_PASSWORD": {"group": "Secrets", "secret": True, "restart": True, "why": "Postgres superuser password used during database initialization."},
    "POSTGRES_DUNE_PASSWORD": {"group": "Secrets", "secret": True, "restart": True, "why": "Application database password used by game services and admin tooling."},
    "RMQ_HTTP_TOKEN_AUTH_SECRET": {"group": "Secrets", "secret": True, "restart": True, "why": "RabbitMQ token auth shared secret."},
    "DUNE_ADMIN_TOKEN": {"group": "Admin Panel", "secret": True, "restart": True, "why": "Token required for admin panel APIs."},
    "DUNE_ADMIN_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Master gate for writes that mutate game/admin state."},
    "DUNE_ADMIN_ITEM_GRANTS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Item grant feature gate. Defaults to true in this repo."},
    "DUNE_ADMIN_GM_COMMANDS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for native Dune GM/admin command execution. Execution also stays blocked until the RabbitMQ payload format is verified."},
    "DUNE_ADMIN_CATALOG_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for read-only content insertion catalog endpoints."},
    "DUNE_ADMIN_TYPED_KNOBS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for typed config knob writes. Dry-runs remain available."},
    "DUNE_ADMIN_EVENT_EXECUTION_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for event orchestrator execution. Event creation and dry-run planning remain available."},
    "DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for economy bundle execution. Bundle planning defaults to dry-run."},
    "DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for raw faction reputation writes. Reputation planning and inspection remain available."},
    "DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for journey reveal/complete/reset/delete server-function calls. Journey planning and inspection remain available."},
    "DUNE_ADMIN_FACTION_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for player faction change server-function calls. Faction planning and inspection remain available."},
    "DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for Landsraad term administration server-function calls. Landsraad inspection and dry-runs remain available."},
    "DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for respawn-location deletion through update_respawn_locations. Respawn inspection and dry-runs remain available."},
    "DUNE_ADMIN_GUILD_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for guild description and role server-function calls. Guild inspection and dry-runs remain available."},
    "DUNE_ADMIN_MARKER_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for marker deletion server-function calls. Marker inspection and dry-runs remain available."},
    "DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for landclaim segment server-function calls. Landclaim inspection and dry-runs remain available."},
    "DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for Dune Exchange Solari balance server-function calls. Exchange inspection and dry-runs remain available."},
    "DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for player tag server-function calls. Player lifecycle inspection and dry-runs remain available."},
    "DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for server player access-code server-function calls. Player lifecycle inspection and dry-runs remain available."},
    "DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for Communinet player/channel server-function calls. Player lifecycle inspection and dry-runs remain available."},
    "DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for tutorial entry server-function calls. Player lifecycle inspection and dry-runs remain available."},
    "DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for permission actor name/access/rank server-function calls. World-state inspection and dry-runs remain available."},
    "DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for vendor player timestamp server-function calls. Player lifecycle inspection and dry-runs remain available."},
    "DUNE_ADMIN_CHARACTER_SWAP_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Feature gate for validated native character hibernation/switch execution. Character slot inspection and dry-runs remain available."},
    "DUNE_ADMIN_MAX_BODY_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum accepted request body size."},
    "DUNE_ADMIN_AUDIT_MAX_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Audit log rotation threshold."},
    "DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Socket timeout to limit slow client abuse."},
    "DUNE_ADMIN_MAX_ITEM_STACK_SIZE": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum item stack mutation allowed through the panel."},
    "DUNE_ADMIN_AUDIT_EVENT_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Default number of audit events returned by the panel."},
    "DUNE_ADMIN_REFERENCE_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum reference rows returned by admin helper endpoints."},
    "DUNE_ADMIN_CHARACTER_SEARCH_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum character search rows returned."},
    "DUNE_ADMIN_STEAM_PROFILE_CACHE_TTL_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "How long to cache public Steam persona names resolved from SteamID64 platform ids."},
    "DUNE_ADMIN_STEAM_PROFILE_LOOKUP_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Enable public Steam profile lookups so SteamID64 platform ids show persona names in the roster."},
    "DUNE_ADMIN_BIND_ADDRESS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host interface used for the admin-panel published port. Keep this on 127.0.0.1 unless a trusted reverse proxy or VPN owns access."},
    "DUNE_ADMIN_HOST_PORT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host TCP port that publishes admin-panel:8080. Change this if another local service already owns 18080."},
    "DUNE_ADMIN_ALLOWED_HOSTS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host header allowlist for the admin HTTP service."},
    "DUNE_HAGGA_MAP_MIN_X": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Full Hagga Basin world-space left bound for coordinate-grid plotting."},
    "DUNE_HAGGA_MAP_MAX_X": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Full Hagga Basin world-space right bound for coordinate-grid plotting."},
    "DUNE_HAGGA_MAP_MIN_Y": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Full Hagga Basin world-space lower Y bound for coordinate-grid plotting."},
    "DUNE_HAGGA_MAP_MAX_Y": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Full Hagga Basin world-space upper Y bound for coordinate-grid plotting."},
    "DUNE_HAGGA_MAP_INVERT_X": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Flip Hagga Basin plotting horizontally. Default false."},
    "DUNE_HAGGA_MAP_INVERT_Y": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Invert Hagga Basin plotting vertically. Default true so higher world Y renders north/up."},
    "DUNE_HAGGA_MAP_IMAGE_MIN_U": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Normalized image-space left edge for Hagga world-coordinate calibration. Values may be outside 0..1 when the bitmap has projection/crop offset."},
    "DUNE_HAGGA_MAP_IMAGE_MAX_U": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Normalized image-space right edge for Hagga world-coordinate calibration."},
    "DUNE_HAGGA_MAP_IMAGE_MIN_V": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Normalized image-space top edge for Hagga world-coordinate calibration."},
    "DUNE_HAGGA_MAP_IMAGE_MAX_V": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Normalized image-space bottom edge for Hagga world-coordinate calibration."},
    "DUNE_HAGGA_MAP_SHOW_RETURN_POINTS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Show yellow travel-return markers on the Hagga map. Default false because they are not live player positions."},
    "DUNE_ADMIN_ANNOUNCE_COMMAND": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Executable hook used by the restart-announcement scheduler to deliver in-game messages."},
    "DUNE_ADMIN_ANNOUNCEMENT_MAX_MESSAGE_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum UTF-8 size for a scheduled restart-announcement message."},
    "DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Timeout for each announcement delivery hook invocation."},
    "DUNE_ANNOUNCE_GAME_RMQ_MANAGEMENT_URL": {"group": "Announcements", "secret": False, "restart": False, "why": "Game RabbitMQ management API URL used by the chat announcement hook."},
    "DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST": {"group": "Announcements", "secret": False, "restart": False, "why": "Game RabbitMQ AMQP host used by the chat announcement publisher."},
    "DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT": {"group": "Announcements", "secret": False, "restart": False, "why": "Game RabbitMQ AMQP port used by the chat announcement publisher."},
    "DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS": {"group": "Announcements", "secret": False, "restart": False, "why": "Whether the chat announcement publisher uses TLS for game RabbitMQ AMQP."},
    "DUNE_ANNOUNCE_HTTP_TIMEOUT_SECONDS": {"group": "Announcements", "secret": False, "restart": False, "why": "Short timeout for RabbitMQ management API probes before the hook falls back to Docker socket binding plus AMQP publish."},
    "DUNE_ANNOUNCE_ALLOW_MANAGEMENT_PUBLISH": {"group": "Announcements", "secret": False, "restart": False, "why": "Emergency fallback for RabbitMQ HTTP publish. Leave false; HTTP publish can route successfully while the Dune client renders nothing."},
    "DUNE_ANNOUNCE_CHAT_USER": {"group": "Announcements", "secret": False, "restart": False, "why": "Player-shaped RabbitMQ identity used as the in-game announcement sender."},
    "DUNE_ANNOUNCE_CHAT_PASSWORD": {"group": "Announcements", "secret": True, "restart": False, "why": "Password supplied for the chat announcement sender."},
    "DUNE_ANNOUNCE_CHAT_FUNCOM_ID": {"group": "Announcements", "secret": False, "restart": False, "why": "Funcom id stamped onto restart chat messages."},
    "DUNE_ANNOUNCE_CHAT_SPOOF_NAME": {"group": "Announcements", "secret": False, "restart": False, "why": "Display name used when spoofed chat names are enabled."},
    "DUNE_ANNOUNCE_CHAT_EXCHANGE": {"group": "Announcements", "secret": False, "restart": False, "why": "Game RabbitMQ chat exchange used for restart announcements."},
    "DUNE_ANNOUNCE_CHAT_ROUTING_KEYS": {"group": "Announcements", "secret": False, "restart": False, "why": "Comma-separated chat routing keys to publish restart announcements to; use <empty> for the blank route."},
    "DUNE_ANNOUNCE_HOST_WORKSPACE": {"group": "Announcements", "secret": False, "restart": False, "why": "Absolute host path to this repo, used only by the Docker-socket fallback publisher."},
    "DUNE_ANNOUNCE_HOST_AMQP_HOST": {"group": "Announcements", "secret": False, "restart": False, "why": "Host-side address for the game RabbitMQ public AMQP port. The verified local Docker bridge value is 172.31.240.1."},
    "DUNE_ANNOUNCE_HOST_AMQP_PORT": {"group": "Announcements", "secret": False, "restart": False, "why": "Host-side game RabbitMQ AMQP port used by the verified pika publisher."},
    "DUNE_ANNOUNCE_CHAT_CHANNEL": {"group": "Announcements", "secret": False, "restart": False, "why": "Chat channel type stamped onto restart announcement messages."},
    "DUNE_ANNOUNCE_CHAT_USE_SPOOF_NAME": {"group": "Announcements", "secret": False, "restart": False, "why": "Whether restart announcements should use the spoofed display-name field."},
    "DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES": {"group": "Announcements", "secret": False, "restart": False, "why": "When enabled, the hook binds currently connected player queues to the announcement chat routes before publishing."},
    "DUNE_ANNOUNCE_CHAT_ENSURE_ACCOUNT": {"group": "Announcements", "secret": False, "restart": False, "why": "Optional DB write path to ensure the Paul announcer account exists before publishing. Leave disabled on live servers unless you are deliberately repairing the announcer account."},
    "DUNE_ANNOUNCE_CHAT_PLATFORM_ID": {"group": "Announcements", "secret": False, "restart": False, "why": "Platform id used when auto-creating the Paul announcer account."},
    "DUNE_ANNOUNCE_CHAT_PLATFORM_NAME": {"group": "Announcements", "secret": False, "restart": False, "why": "Platform name used when auto-creating the Paul announcer account."},
    "DUNE_ANNOUNCE_RMQ_URL": {"group": "Announcements", "secret": False, "restart": True, "why": "RabbitMQ management API URL used by the announcement hook."},
    "DUNE_ANNOUNCE_RMQ_USER": {"group": "Announcements", "secret": False, "restart": True, "why": "RabbitMQ management user used by the announcement hook. Use a bgd.<world>.*.admin identity so JSON-RPC sender permissions pass."},
    "DUNE_ANNOUNCE_RMQ_PASSWORD": {"group": "Announcements", "secret": True, "restart": True, "why": "RabbitMQ management password used by the announcement hook."},
    "DUNE_ANNOUNCE_RMQ_EXCHANGE": {"group": "Announcements", "secret": False, "restart": True, "why": "RabbitMQ exchange used for server-command announcements."},
    "DUNE_ANNOUNCE_RMQ_ROUTING_KEYS": {"group": "Announcements", "secret": False, "restart": True, "why": "Comma-separated map RPC routing keys that receive announcements."},
    "DUNE_ANNOUNCE_RMQ_REPLY_TO": {"group": "Announcements", "secret": False, "restart": True, "why": "Optional AMQP reply_to property for RPC-style announcement probes."},
    "DUNE_ANNOUNCE_RMQ_CORRELATION_ID": {"group": "Announcements", "secret": False, "restart": True, "why": "Optional fixed AMQP correlation_id property for RPC-style announcement probes. Defaults to the scheduled job id."},
    "DUNE_ANNOUNCE_RMQ_TYPE": {"group": "Announcements", "secret": False, "restart": True, "why": "AMQP type property used by the announcement hook. Defaults to the command name."},
    "DUNE_ANNOUNCE_RMQ_APP_ID": {"group": "Announcements", "secret": False, "restart": True, "why": "Optional AMQP app_id property for RPC-style announcement probes."},
    "DUNE_ANNOUNCE_RMQ_USER_ID": {"group": "Announcements", "secret": False, "restart": True, "why": "Optional AMQP user_id property for RPC-style announcement probes. Defaults to DUNE_ANNOUNCE_RMQ_USER."},
    "DUNE_ANNOUNCE_COMMAND_NAME": {"group": "Announcements", "secret": False, "restart": True, "why": "Server command name sent by the announcement hook."},
    "DUNE_ANNOUNCE_TITLE": {"group": "Announcements", "secret": False, "restart": True, "why": "Default title for generic in-game service broadcasts."},
    "DUNE_ANNOUNCE_DURATION_SECONDS": {"group": "Announcements", "secret": False, "restart": True, "why": "Default on-screen duration for generic in-game service broadcasts."},
    "DUNE_ANNOUNCE_PAYLOAD_MODE": {"group": "Announcements", "secret": False, "restart": True, "why": "Built-in announcement envelope variant used when no raw payload template is set."},
    "DUNE_ANNOUNCE_PAYLOAD_TEMPLATE": {"group": "Announcements", "secret": False, "restart": True, "why": "Optional raw RabbitMQ payload template for overriding the default ServiceBroadcast envelope."},
    "DUNE_ADMIN_RESTART_COMMAND": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Executable hook used by the scheduled restart runner."},
    "DUNE_ADMIN_RESTART_COMMAND_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Timeout for each scheduled restart hook invocation."},
    "DUNE_ADMIN_RESTART_RECOVERY_ENABLED": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Runs one map-watchdog recovery pass if a restart start phase completes but farm DB readiness is incomplete."},
    "DUNE_ADMIN_RESTART_RECOVERY_COMMAND": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Recovery hook used after an incomplete scheduled restart. Defaults to scripts/watch-maps.sh."},
    "DUNE_ADMIN_RESTART_RECOVERY_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Timeout for the post-restart recovery hook."},
    "DUNE_RESTART_COMPOSE_PROJECT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Compose project label used by the Docker-socket restart hook."},
    "DUNE_RESTART_DOCKER_SOCKET": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Docker Engine Unix socket path used by the restart hook when Docker CLI is unavailable."},
    "DUNE_RESTART_HOST_WORKSPACE": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Absolute host path to this repo. The Docker-socket fallback mounts it into a short-lived Compose helper so scheduled restarts can recreate containers and apply .env/config changes."},
    "DUNE_RESTART_COMPOSE_IMAGE": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Docker CLI image used for the short-lived host Compose helper."},
    "DUNE_RESTART_USE_HOST_COMPOSE": {"group": "Admin Panel", "secret": False, "restart": True, "why": "When true, the Docker-socket restart hook uses host Compose for start/recreate phases instead of only starting existing containers."},
    "DUNE_RESTART_COMPOSE_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Timeout for the short-lived host Compose helper used by scheduled restart recreate phases."},
    "DUNE_RESTART_DOCKER_STOP_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Socket read timeout for Docker stop/restart API calls made by the restart hook."},
    "DUNE_RESTART_DOCKER_API_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Socket read timeout for non-stop Docker API calls made by the restart hook."},
    "DUNE_CHAT_SPAM_PROTECT_ENABLED": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Enables repeated-message spam detection in the chat-command listener."},
    "DUNE_CHAT_SPAM_PROTECT_EXEMPT_ADMINS": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Exempts configured chat-command admins from automatic spam enforcement."},
    "DUNE_CHAT_SPAM_SAME_CONSECUTIVE_LIMIT": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Maximum identical consecutive messages allowed before enforcement. A value of 3 means the 4th repeat triggers."},
    "DUNE_CHAT_SPAM_SAME_WINDOW_LIMIT": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Identical-message count inside the rolling spam window that triggers enforcement."},
    "DUNE_CHAT_SPAM_SAME_WINDOW_SECONDS": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Rolling window length, in seconds, for repeated-message spam detection."},
    "DUNE_CHAT_SPAM_KICK_COOLDOWN_SECONDS": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Cooldown before the same sender can trigger another spam enforcement action."},
    "DUNE_CHAT_SPAM_MIN_MESSAGE_LENGTH": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Minimum normalized message length checked by spam protection."},
    "DUNE_CHAT_SPAM_ANNOUNCE_ACTION": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Announces spam enforcement or blocked enforcement through the configured in-game announcement hook."},
    "DUNE_CHAT_SPAM_KICK_COMMAND": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Optional executable hook for kicking a spammer. Leave blank until a real targeted kick backend is verified."},
    "DUNE_CHAT_SPAM_KICK_TIMEOUT_SECONDS": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Timeout for the spam kick hook command."},
    "DUNE_CHAT_SPAM_EXEMPT_NAMES": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Comma-separated character names exempt from spam enforcement."},
    "DUNE_CHAT_SPAM_EXEMPT_FLS_IDS": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Comma-separated Funcom Live Services account ids exempt from spam enforcement."},
    "DUNE_SPAM_KICK_BACKEND": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Backend mode used by scripts/spam-kick-player.sh. Keep blocked until a targeted Dune kick backend is verified."},
    "DUNE_SPAM_KICK_BACKEND_COMMAND": {"group": "Chat Spam Protection", "secret": False, "restart": True, "why": "Optional delegated backend command used only when DUNE_SPAM_KICK_BACKEND=command."},
    "DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT": {"group": "Chat Commands", "secret": False, "restart": True, "why": "Third gate for targeted player disconnect through the verified native GM command path."},
    "DUNE_PLAYER_DISCONNECT_COMMAND": {"group": "Chat Commands", "secret": False, "restart": True, "why": "Native command used by &disconnect. Default RemoveSessionMember is the softest known candidate; KickLobbyMember is the fallback."},
    "DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE": {"group": "Chat Commands", "secret": False, "restart": True, "why": "Allows BattlEyeMegaKick as a selectable disconnect command. Leave false unless you deliberately want the punitive kick path."},
    "DUNE_ADMIN_BOT_INTERVAL_SECONDS": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Loop interval for scripts/admin-bot.py when run in daemon mode."},
    "DUNE_ADMIN_BOT_BACKUP_MAX_AGE_HOURS": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Maximum acceptable age for the newest local backup before the bot reports stale backup risk."},
    "DUNE_ADMIN_BOT_BACKUP_STALE_RUN": {"group": "Admin Bot", "secret": False, "restart": True, "why": "When true, admin-bot runs scripts/backup-state.sh if the newest local backup is stale."},
    "DUNE_ADMIN_BOT_MAP_WATCHDOG_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Enables admin-bot map watchdog checks using scripts/watch-maps.sh."},
    "DUNE_ADMIN_BOT_MAP_WATCHDOG_RECOVER": {"group": "Admin Bot", "secret": False, "restart": True, "why": "When true, admin-bot allows watch-maps.sh --once recovery. Default false keeps it dry-run/report-only."},
    "DUNE_ADMIN_BOT_STUCK_TRANSITIONS_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Enables read-only reporting of players whose online activity appears stale."},
    "DUNE_ADMIN_BOT_STUCK_TRANSITION_MINUTES": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Minutes of stale online activity before a player is reported as potentially stuck."},
    "DUNE_ADMIN_BOT_AUDIT_DIGEST_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Enables incremental digesting of admin panel audit events."},
    "DUNE_ADMIN_BOT_ECONOMY_ANOMALIES_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Enables read-only Solari/currency anomaly reporting."},
    "DUNE_ADMIN_BOT_SOLARI_WARN_THRESHOLD": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Currency amount threshold used by the economy anomaly report."},
    "DUNE_ADMIN_BOT_BASE_CLAIM_MONITOR_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Enables read-only base/claim count anomaly reporting."},
    "DUNE_ADMIN_BOT_MAX_BASES_WARN": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Base/claim count threshold used by the claim monitor."},
    "DUNE_ADMIN_BOT_CONFIG_DRIFT_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Tracks hashes of key config files and reports changes between bot runs."},
    "DUNE_ADMIN_BOT_SECURITY_GUARD_ENABLED": {"group": "Admin Bot", "secret": False, "restart": True, "why": "Summarizes recent token, host, origin, and denied-request audit events."},
}
ENV_KEY_DEFINITIONS.update({
    "DUNE_ARTIFICIAL_EXCHANGE_ENABLED": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Master gate for the artificial buyer service."},
    "DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "When true, buyer scans select listings but do not purchase."},
    "DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Allows native Exchange purchases when the buyer is not in dry-run mode."},
    "DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Allows seller settlement auto-claim through the validated native retrieval path."},
    "DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Runs auto-claim after each buyer scan when auto-claim is enabled."},
    "DUNE_ARTIFICIAL_EXCHANGE_FUNDING_ENABLED": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Allows explicit buyer Solari funding actions."},
    "DUNE_ARTIFICIAL_EXCHANGE_ID": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Exchange id used for listing discovery and seeding. Default is 2."},
    "DUNE_ARTIFICIAL_EXCHANGE_ACCESS_POINT_ID": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Exchange access point id used for seeded listings. Default is 1."},
    "DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Player controller id used as the artificial buyer identity."},
    "DUNE_ARTIFICIAL_EXCHANGE_SCAN_LIMIT": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Maximum sell orders inspected per buyer scan."},
    "DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MIN_SECONDS": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Minimum randomized buyer loop sleep interval."},
    "DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MAX_SECONDS": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Maximum randomized buyer loop sleep interval."},
    "DUNE_ARTIFICIAL_EXCHANGE_DAILY_SOLARI_CAP": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Global daily Solari spend cap."},
    "DUNE_ARTIFICIAL_EXCHANGE_DAILY_SELLER_CAP": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Daily Solari cap per seller."},
    "DUNE_ARTIFICIAL_EXCHANGE_DAILY_TEMPLATE_CAP": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Daily Solari cap per item template."},
    "DUNE_ARTIFICIAL_EXCHANGE_LOW_BUY_PROBABILITY": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Random buy probability for low-liquidity catalog rows."},
    "DUNE_ARTIFICIAL_EXCHANGE_MEDIUM_BUY_PROBABILITY": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Random buy probability for medium-liquidity catalog rows."},
    "DUNE_ARTIFICIAL_EXCHANGE_HIGH_BUY_PROBABILITY": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Random buy probability for high-liquidity catalog rows."},
    "DUNE_ARTIFICIAL_EXCHANGE_BLOCKED_SELLERS": {"group": "Artificial Exchange", "secret": False, "restart": True, "why": "Comma-separated seller/controller ids the buyer must never buy from."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Master gate for seeded NPC-like Exchange listings."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "When true, the populator plans seeded listings without inserting them."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_LIVE_VALIDATION_ENABLED": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Allows live disposable validation of populator and buyer skip behavior."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Primary owner/controller id used for seeded listings."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_IDS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Comma-separated owner/controller ids treated as populator sellers and skipped by the buyer."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Exchange inventory id used to hold seeded listing item rows."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_POSITION_START": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "First inventory position reserved for seeded listing items."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_POSITION_MAX": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Last inventory position reserved for seeded listing items."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MIN_ORDERS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Minimum active seeded listings the populator tries to maintain."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MAX_ORDERS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Maximum active seeded listings the populator tries to maintain."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_HARD_MAX_ORDERS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Absolute cap on active seeded listings."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_PRICE_JITTER_PCT": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Percent jitter applied around catalog max buy prices for seeded listings."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRY_MIN_SECONDS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Minimum seeded listing lifetime."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRY_MAX_SECONDS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Maximum seeded listing lifetime."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRE_PROBABILITY": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Probability of expiring eligible seeded listings each loop."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_FORCE_COUNT": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Optional one-shot forced listing count for validation."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_VALIDATION_PRICE": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Optional forced price for disposable live validation listings."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CONFIRM": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Confirmation phrase passed to live populator actions."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_VALIDATED": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "When true, only catalog rows marked validated are seeded."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_MARKET_PRICE": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "When true, only catalog rows with dune.exchange price evidence are seeded."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MIN_TIER": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Minimum parsed tier allowed for seeded listings."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_SOURCE_CATEGORY": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Requires source-backed category evidence before seeding a template."},
    "DUNE_ARTIFICIAL_EXCHANGE_SOURCE_CATEGORY_MAP": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Path to the source-backed Exchange category map JSON."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_CATEGORY_REVIEW": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Blocks heuristic/bootstrap categories until reviewed."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_DETERMINISTIC_CATEGORY": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Requires inferred category and category mask/depth to match before seeding."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SKIP_UNKNOWN_CATEGORY": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Blocks unknown category rows and mask/depth 0/0 rows."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_PROTECT_AUGMENTS_CATEGORY": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Blocks non-augment templates from protected Augments category masks."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_AUGMENTS_CATEGORY_MASKS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Comma-separated category masks treated as Augments-only buckets."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TEMPLATE_TARGET_ORDERS": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Target active orders per eligible template for template population mode."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MAX_PER_TEMPLATE_PER_CATEGORY": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Maximum active seeded orders for the same template/category combination."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MIN_PRICE_SPAN": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Minimum price span used when widening tight fixed price ranges."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_STACK_SIZE": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Stack size for seeded items."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MAX_STACK_SIZE": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Max stack size written to seeded item rows."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CATEGORY_MASK": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Category mask written to seeded item rows when catalog rows do not override it."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CATEGORY_DEPTH": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Category depth written to seeded item rows when catalog rows do not override it."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DURABILITY_CUR": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Current durability for seeded items."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DURABILITY_MAX": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Maximum durability for seeded items."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MIN_QUALITY_LEVEL": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Minimum quality level allowed for seeded items."},
    "DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_QUALITY_LEVEL": {"group": "Artificial Exchange Populator", "secret": False, "restart": True, "why": "Default quality level for seeded items."},
    "DUNE_ARTIFICIAL_EXCHANGE_WATCHDOG_DRY_RUN": {"group": "Artificial Exchange Watchdog", "secret": False, "restart": False, "why": "When true, the watchdog reports inactive/missing services without repairing them."},
    "DUNE_ARTIFICIAL_EXCHANGE_WATCHDOG_BUYER_UNIT": {"group": "Artificial Exchange Watchdog", "secret": False, "restart": False, "why": "Systemd unit name for the buyer service repaired by the watchdog."},
    "DUNE_ARTIFICIAL_EXCHANGE_WATCHDOG_POPULATOR_UNIT": {"group": "Artificial Exchange Watchdog", "secret": False, "restart": False, "why": "Systemd unit name for the populator service repaired by the watchdog."},
})
SAFE_ENV_KEYS = set(ENV_KEY_DEFINITIONS)

AUDIT_FIELD_LIMIT = 240


def audit_safe(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [audit_safe(item) for item in value[:20]]
    if isinstance(value, dict):
        return {
            str(key): audit_safe(item)
            for key, item in value.items()
            if "token" not in str(key).lower() and "password" not in str(key).lower() and "secret" not in str(key).lower()
        }
    text = str(value)
    if len(text) > AUDIT_FIELD_LIMIT:
        return text[:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return text


def audit_event(action, ok=True, **fields):
    try:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        rotate_audit_log()
        event = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "ok": bool(ok),
        }
        event.update({key: audit_safe(value) for key, value in fields.items()})
        with AUDIT_LOCK:
            with AUDIT_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True, default=json_default) + "\n")
    except OSError:
        return


def rotate_audit_log():
    if AUDIT_MAX_BYTES <= 0 or not AUDIT_LOG.exists() or AUDIT_LOG.stat().st_size <= AUDIT_MAX_BYTES:
        return
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    AUDIT_LOG.rename(BACKUP_ROOT / f"{stamp}-audit.jsonl")


def recent_audit_events(limit=None):
    limit = max(1, min(int(limit or AUDIT_EVENT_LIMIT), 1000))
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"ts": "", "action": "audit-log-parse-error", "ok": False})
    return events


def announcement_default_state():
    return {"jobs": [], "lastDelivery": None, "command": ANNOUNCEMENT_COMMAND}


def read_announcement_state():
    if not ANNOUNCEMENT_STATE_FILE.exists():
        return announcement_default_state()
    try:
        state = json.loads(ANNOUNCEMENT_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return announcement_default_state()
    if not isinstance(state, dict):
        return announcement_default_state()
    state.setdefault("jobs", [])
    state.setdefault("lastDelivery", None)
    state["command"] = ANNOUNCEMENT_COMMAND
    return state


def write_announcement_state(state):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = ANNOUNCEMENT_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    tmp.replace(ANNOUNCEMENT_STATE_FILE)


def active_announcement_jobs(state):
    return [
        job for job in state.get("jobs", [])
        if job.get("status") in ("scheduled", "delivering")
    ]


def schedule_announcement(body):
    message = str(body.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")
    if len(message.encode("utf-8")) > ANNOUNCEMENT_MAX_MESSAGE_BYTES:
        raise ValueError(f"message exceeds {ANNOUNCEMENT_MAX_MESSAGE_BYTES} bytes")
    delay_key = str(body.get("delay", "immediate")).strip()
    if delay_key not in ANNOUNCEMENT_DELAYS:
        raise ValueError("invalid restart delay")
    repeat_seconds = int(body.get("repeat_seconds", body.get("repeatSeconds", 60)) or 0)
    if repeat_seconds < 0 or repeat_seconds > 24 * 60 * 60:
        raise ValueError("repeat_seconds must be between 0 and 86400")
    cadence = body.get("cadence", body.get("announcementCadence", []))
    if cadence is None:
        cadence = []
    if not isinstance(cadence, list):
        raise ValueError("cadence must be a list")
    normalized_cadence = []
    for entry in cadence:
        if not isinstance(entry, dict):
            raise ValueError("cadence entries must be objects")
        remaining_seconds = int(entry.get("remaining_seconds", entry.get("remainingSeconds", 0)) or 0)
        interval_seconds = int(entry.get("interval_seconds", entry.get("intervalSeconds", 0)) or 0)
        if remaining_seconds < 0 or remaining_seconds > 24 * 60 * 60:
            raise ValueError("cadence remaining_seconds must be between 0 and 86400")
        if interval_seconds <= 0 or interval_seconds > 24 * 60 * 60:
            raise ValueError("cadence interval_seconds must be between 1 and 86400")
        normalized_cadence.append({
            "remainingSeconds": remaining_seconds,
            "intervalSeconds": interval_seconds,
        })
    normalized_cadence.sort(key=lambda item: item["remainingSeconds"])
    now = time.time()
    restart_at = body.get("restart_at", body.get("restartAt"))
    if restart_at is None:
        restart_at = now + ANNOUNCEMENT_DELAYS[delay_key]
    else:
        restart_at = float(restart_at)
        if restart_at < now:
            raise ValueError("restart_at must be in the future")
    next_send_at = body.get("next_send_at", body.get("nextSendAt"))
    next_send_at = float(next_send_at) if next_send_at is not None else now + ANNOUNCEMENT_DELAYS[delay_key]
    next_send_at = min(max(next_send_at, now), restart_at)
    job = {
        "id": secrets.token_urlsafe(12),
        "message": message,
        "action": str(body.get("action", "maintenance")).strip() or "maintenance",
        "delay": delay_key,
        "createdAt": now,
        "restartAt": restart_at,
        "repeatSeconds": repeat_seconds,
        "cadence": normalized_cadence,
        "nextSendAt": next_send_at,
        "lastSentAt": None,
        "deliveryCount": 0,
        "status": "scheduled",
        "lastError": None,
    }
    restart_job_id = str(body.get("restart_job_id", body.get("restartJobId", ""))).strip()
    if restart_job_id:
        job["restartJobId"] = restart_job_id
    with ANNOUNCEMENT_LOCK:
        state = read_announcement_state()
        for existing in active_announcement_jobs(state):
            existing["status"] = "superseded"
        state.setdefault("jobs", []).append(job)
        write_announcement_state(state)
    return job


def announcement_next_interval(job, now=None):
    now = time.time() if now is None else float(now)
    remaining = max(0, float(job.get("restartAt", now)) - now)
    cadence = job.get("cadence") or []
    if isinstance(cadence, list):
        for entry in cadence:
            try:
                threshold = float(entry.get("remainingSeconds", 0))
                interval = int(entry.get("intervalSeconds", 0))
            except (AttributeError, TypeError, ValueError):
                continue
            if remaining <= threshold and interval > 0:
                return interval
    return int(job.get("repeatSeconds") or 0)


def cancel_announcement(job_id=None):
    with ANNOUNCEMENT_LOCK:
        state = read_announcement_state()
        changed = 0
        for job in active_announcement_jobs(state):
            if job_id and job.get("id") != job_id:
                continue
            job["status"] = "cancelled"
            job["cancelledAt"] = time.time()
            changed += 1
        write_announcement_state(state)
    return {"ok": True, "cancelled": changed}


def restart_default_state():
    return {"jobs": [], "lastExecution": None, "command": RESTART_COMMAND, "targets": RESTART_TARGETS}


def read_restart_state():
    if not RESTART_STATE_FILE.exists():
        return restart_default_state()
    try:
        state = json.loads(RESTART_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return restart_default_state()
    if not isinstance(state, dict):
        return restart_default_state()
    state.setdefault("jobs", [])
    state.setdefault("lastExecution", None)
    state["command"] = RESTART_COMMAND
    state["targets"] = RESTART_TARGETS
    return state


def read_admin_digest_state():
    try:
        state = json.loads(ADMIN_DIGEST_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    return {
        "path": str(ADMIN_DIGEST_STATE_FILE.relative_to(ROOT)),
        "updatedAt": state.get("updatedAt"),
        "digests": list(reversed(state.get("adminDigestLog", [])[-250:])),
        "onlinePlayers": state.get("onlinePlayers", {}),
        "mapHealthState": state.get("mapHealthState"),
        "dailyPeak": state.get("dailyPeak", {}),
        "lastSent": {
            key: value for key, value in state.items()
            if key.startswith("lastAdmin") or key in ("lastDailyStatusAt", "lastMaintenanceCancelScanAt")
        },
    }


def write_restart_state(state):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = RESTART_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    tmp.replace(RESTART_STATE_FILE)


def active_restart_jobs(state):
    return [job for job in state.get("jobs", []) if job.get("status") in ("scheduled", "executing")]


def schedule_restart(body):
    target = str(body.get("target", "")).strip()
    if target not in RESTART_TARGETS:
        raise ValueError("invalid restart target")
    action = str(body.get("action", "restart")).strip().lower()
    if action not in ("restart", "shutdown"):
        raise ValueError("invalid restart action")
    delay_key = str(body.get("delay", "immediate")).strip()
    if delay_key not in ANNOUNCEMENT_DELAYS:
        raise ValueError("invalid restart delay")
    message = str(body.get("message", "")).strip()
    repeat_seconds = int(body.get("repeat_seconds", body.get("repeatSeconds", 60)) or 0)
    announce = str(body.get("announce", "true")).lower() in ("1", "true", "yes", "on")
    execute = str(body.get("execute", "")).lower() in ("1", "true", "yes", "on")
    backup = str(body.get("backup", "true")).lower() in ("1", "true", "yes", "on")
    now = time.time()
    run_at = now + ANNOUNCEMENT_DELAYS[delay_key]
    job = {
        "id": secrets.token_urlsafe(12),
        "target": target,
        "action": action,
        "targetLabel": RESTART_TARGETS[target]["label"],
        "services": RESTART_TARGETS[target]["services"],
        "delay": delay_key,
        "createdAt": now,
        "runAt": run_at,
        "message": message,
        "announce": announce,
        "repeatSeconds": repeat_seconds,
        "execute": execute,
        "backup": backup,
        "status": "scheduled",
        "lastError": None,
    }
    with RESTART_LOCK:
        state = read_restart_state()
        for existing in active_restart_jobs(state):
            existing["status"] = "superseded"
        state.setdefault("jobs", []).append(job)
        write_restart_state(state)
    if announce and message:
        schedule_announcement({
            "delay": "immediate",
            "repeat_seconds": repeat_seconds,
            "cadence": body.get("announcement_cadence", body.get("announcementCadence", [])),
            "message": message,
            "restart_at": run_at,
            "action": action,
            "restart_job_id": job["id"],
        })
    return job


def cancel_restart(job_id=None):
    cancelled_ids = []
    with RESTART_LOCK:
        state = read_restart_state()
        changed = 0
        for job in active_restart_jobs(state):
            if job_id and job.get("id") != job_id:
                continue
            job["status"] = "cancelled"
            job["cancelledAt"] = time.time()
            cancelled_ids.append(job.get("id"))
            changed += 1
        write_restart_state(state)
    cancelled_announcements = 0
    if cancelled_ids:
        with ANNOUNCEMENT_LOCK:
            announcement_state = read_announcement_state()
            for job in active_announcement_jobs(announcement_state):
                if job.get("restartJobId") not in cancelled_ids:
                    continue
                job["status"] = "cancelled"
                job["cancelledAt"] = time.time()
                cancelled_announcements += 1
            write_announcement_state(announcement_state)
    return {"ok": True, "cancelled": changed, "cancelledAnnouncements": cancelled_announcements}


def run_restart_command(command, job, phase):
    command = pathlib.Path(RESTART_COMMAND)
    env = os.environ.copy()
    env.update({
        "DUNE_RESTART_JOB_ID": job.get("id", ""),
        "DUNE_RESTART_TARGET": job.get("target", ""),
        "DUNE_RESTART_SERVICES": " ".join(job.get("services", [])),
        "DUNE_RESTART_ACTION": job.get("action", "restart"),
        "DUNE_RESTART_PHASE": phase,
    })
    try:
        result = subprocess.run(
            [str(command), job.get("target", "")],
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=RESTART_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "phase": phase, "error": str(exc)}
    output = (result.stdout + result.stderr).strip()
    if len(output) > AUDIT_FIELD_LIMIT:
        output = output[:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return {"ok": result.returncode == 0, "phase": phase, "returncode": result.returncode, "output": output}


def restart_online_snapshot():
    rows = query("""
        select
          count(*)::int as expected,
          count(*) filter (
            where wp.server_id is not null
              and coalesce(fs.alive, false)
              and asi.server_id is not null
              and not coalesce(wp.blocked, false)
          )::int as online,
          count(*) filter (
            where wp.server_id is not null
              and coalesce(fs.alive, false)
              and coalesce(fs.ready, false)
              and asi.server_id is not null
              and not coalesce(wp.blocked, false)
          )::int as ready_online,
          count(*) filter (where wp.server_id is not null and coalesce(fs.alive, false))::int as alive,
          count(*) filter (where asi.server_id is not null)::int as active
        from dune.world_partition wp
        left join dune.farm_state fs on fs.server_id = wp.server_id
        left join dune.active_server_ids asi on asi.server_id = wp.server_id
    """)
    row = rows[0] if rows else {}
    expected = int(row.get("expected") or 0)
    online = int(row.get("online") or 0)
    ready_online = int(row.get("ready_online") or 0)
    return {
        "ok": expected > 0 and online == expected and ready_online == expected,
        "expected": expected,
        "online": online,
        "readyOnline": ready_online,
        "alive": int(row.get("alive") or 0),
        "active": int(row.get("active") or 0),
    }


def wait_for_restart_online():
    deadline = time.time() + max(0, RESTART_ONLINE_TIMEOUT_SECONDS)
    last = {"ok": False, "expected": 0, "online": 0, "alive": 0, "active": 0}
    while True:
        try:
            last = restart_online_snapshot()
        except Exception as exc:
            last = {"ok": False, "error": str(exc)}
        if last.get("ok") or time.time() >= deadline:
            last["timeoutSeconds"] = RESTART_ONLINE_TIMEOUT_SECONDS
            return last
        time.sleep(max(1, RESTART_ONLINE_POLL_SECONDS))


def run_restart_recovery(job):
    if not RESTART_RECOVERY_ENABLED:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    command = pathlib.Path(RESTART_RECOVERY_COMMAND)
    if not command.exists() or not os.access(command, os.X_OK):
        return {"ok": False, "skipped": True, "error": f"restart recovery command is not executable: {command}"}
    env = os.environ.copy()
    env.update({
        "COMPOSE_FILES": env.get("COMPOSE_FILES", "compose.yaml:compose.allmaps.yaml"),
        "DUNE_WATCH_STARTUP_GRACE": "0",
        "DUNE_WATCH_RECOVERY_WAIT": env.get("DUNE_WATCH_RECOVERY_WAIT", str(RESTART_ONLINE_TIMEOUT_SECONDS)),
    })
    try:
        result = subprocess.run(
            [str(command), str(ENV_FILE), "--once"],
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=RESTART_RECOVERY_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    output = (result.stdout + result.stderr).strip()
    if len(output) > AUDIT_FIELD_LIMIT:
        output = output[:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return {"ok": result.returncode == 0, "returncode": result.returncode, "output": output}


def execute_restart(job):
    if not job.get("execute"):
        return {"ok": True, "dryRun": True, "output": f"scheduled {job.get('action', 'restart')} reached run time; execute=false so no command was run"}
    command = pathlib.Path(RESTART_COMMAND)
    if not command.exists() or not os.access(command, os.X_OK):
        return {"ok": False, "error": f"restart command is not executable: {command}"}

    action = job.get("action", "restart")
    disconnect_result = soft_disconnect_online_players(job)
    if not disconnect_result.get("ok"):
        return {
            "ok": False,
            "action": action,
            "disconnect": disconnect_result,
            "error": disconnect_result.get("error", "soft disconnect failed"),
            "output": disconnect_result.get("error", "soft disconnect failed"),
        }
    stop_phase = "shutdown" if action == "shutdown" else "stop"
    stop_result = run_restart_command(command, job, stop_phase)
    result = {"ok": False, "action": action, "disconnect": disconnect_result, "stop": stop_result, "backup": None, "update": None, "start": None}
    if not stop_result.get("ok"):
        result["output"] = stop_result.get("output", stop_result.get("error", ""))
        return result

    if job.get("backup", True) and MAINTENANCE_BACKUP_ENABLED:
        try:
            result["backup"] = create_maintenance_backup(job)
        except Exception as exc:
            result["error"] = str(exc)
            result["output"] = f"{stop_result.get('output', '')}\nbackup failed: {exc}".strip()
            return result

    update_result = run_restart_command(command, job, "update")
    result["update"] = update_result
    if not update_result.get("ok"):
        result["error"] = update_result.get("error") or "Steam package update check failed"
        result["output"] = "\n".join(part for part in [stop_result.get("output", ""), update_result.get("output", ""), result["error"]] if part)
        return result

    if action == "shutdown":
        result["ok"] = True
        result["output"] = "\n".join(part for part in [stop_result.get("output", ""), update_result.get("output", "")] if part)
        return result

    start_result = run_restart_command(command, job, "start")
    result["start"] = start_result
    online_result = wait_for_restart_online()
    recovery_result = None
    if not online_result.get("ok"):
        recovery_result = run_restart_recovery(job)
        result["recovery"] = recovery_result
        if recovery_result.get("ok"):
            online_result = wait_for_restart_online()
    result["online"] = online_result
    start_ok = bool(start_result.get("ok")) or (start_result.get("returncode") == 141 and bool(online_result.get("ok")))
    result["ok"] = start_ok and bool(online_result.get("ok"))
    result["returncode"] = start_result.get("returncode")
    if start_result.get("returncode") == 141 and online_result.get("ok"):
        result["warning"] = "restart start hook returned 141, but farm reported fully online after verification"
    elif not start_result.get("ok"):
        result["error"] = start_result.get("error") or f"restart start hook failed with return code {start_result.get('returncode')}"
    elif not online_result.get("ok"):
        result["error"] = "restart start hook completed, but farm did not report fully online before timeout"
    result["output"] = "\n".join(part for part in [stop_result.get("output", ""), start_result.get("output", "")] if part)
    if len(result["output"]) > AUDIT_FIELD_LIMIT:
        result["output"] = result["output"][:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return result


def dashboard_announcement_message(message):
    message = str(message or "").strip()
    if message.startswith("!!! ") and message.endswith(" !!!"):
        return message
    return f"!!! {message} !!!"


def format_remaining(seconds):
    seconds = max(0, int(round(float(seconds))))
    if seconds <= 0:
        return "now"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return " ".join(parts)


def announcement_message_with_remaining(job):
    base = str(job.get("message", "")).strip()
    restart_at = float(job.get("restartAt", time.time()))
    remaining = max(0, restart_at - time.time())
    action = str(job.get("action", "maintenance")).strip() or "maintenance"
    remaining_text = format_remaining(remaining)
    if "{remaining}" in base or "{time_remaining}" in base:
        return base.replace("{remaining}", remaining_text).replace("{time_remaining}", remaining_text)
    if "{action}" in base:
        return base.replace("{action}", action).replace("{remaining}", remaining_text).replace("{time_remaining}", remaining_text)
    if remaining <= 0:
        return f"{base} Starting {action} now. Players will be disconnected cleanly."
    return f"{base} {action.capitalize()} in {remaining_text}."


def deliver_announcement(job):
    command = pathlib.Path(ANNOUNCEMENT_COMMAND)
    if not command.exists() or not os.access(command, os.X_OK):
        return {"ok": False, "error": f"announce command is not executable: {command}"}
    message = dashboard_announcement_message(announcement_message_with_remaining(job))
    env = os.environ.copy()
    env.update({
        "DUNE_ANNOUNCE_MESSAGE": message,
        "DUNE_ANNOUNCE_RESTART_AT": str(int(float(job.get("restartAt", time.time())))),
        "DUNE_ANNOUNCE_JOB_ID": job.get("id", ""),
    })
    try:
        result = subprocess.run(
            [str(command), message],
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    output = (result.stdout + result.stderr).strip()
    if len(output) > AUDIT_FIELD_LIMIT:
        output = output[:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return {"ok": result.returncode == 0, "returncode": result.returncode, "output": output}


def announcement_worker():
    while True:
        now = time.time()
        due_jobs = []
        due_restarts = []
        with ANNOUNCEMENT_LOCK:
            state = read_announcement_state()
            for job in active_announcement_jobs(state):
                if now >= float(job.get("restartAt", 0)) and job.get("finalSentAt"):
                    job["status"] = "expired"
                    continue
                if now >= float(job.get("nextSendAt", 0)):
                    job["status"] = "delivering"
                    due_jobs.append(dict(job))
            write_announcement_state(state)
        with RESTART_LOCK:
            restart_state = read_restart_state()
            for job in active_restart_jobs(restart_state):
                if now >= float(job.get("runAt", 0)):
                    job["status"] = "executing"
                    due_restarts.append(dict(job))
            write_restart_state(restart_state)
        for due in due_jobs:
            result = deliver_announcement(due)
            with ANNOUNCEMENT_LOCK:
                state = read_announcement_state()
                for job in state.get("jobs", []):
                    if job.get("id") != due.get("id") or job.get("status") not in ("delivering", "scheduled"):
                        continue
                    job["deliveryCount"] = int(job.get("deliveryCount") or 0) + 1
                    job["lastSentAt"] = time.time()
                    job["lastError"] = None if result.get("ok") else result.get("error") or result.get("output")
                    repeat_seconds = announcement_next_interval(job)
                    if time.time() >= float(job.get("restartAt", 0)):
                        job["finalSentAt"] = time.time()
                        job["status"] = "expired"
                    elif repeat_seconds <= 0:
                        job["status"] = "sent" if result.get("ok") else "failed"
                    else:
                        job["status"] = "scheduled"
                        job["nextSendAt"] = min(time.time() + repeat_seconds, float(job.get("restartAt", time.time())))
                state["lastDelivery"] = result
                write_announcement_state(state)
            audit_event("announcement-delivery", ok=result.get("ok"), job_id=due.get("id"), returncode=result.get("returncode"), error=result.get("error"), output=result.get("output"))
        for due in due_restarts:
            result = execute_restart(due)
            with RESTART_LOCK:
                restart_state = read_restart_state()
                for job in restart_state.get("jobs", []):
                    if job.get("id") != due.get("id") or job.get("status") != "executing":
                        continue
                    job["executedAt"] = time.time()
                    job["status"] = "executed" if result.get("ok") else "failed"
                    job["lastError"] = None if result.get("ok") else result.get("error") or result.get("output")
                restart_state["lastExecution"] = result
                write_restart_state(restart_state)
            audit_event("restart-execution", ok=result.get("ok"), job_id=due.get("id"), target=due.get("target"), dry_run=result.get("dryRun"), returncode=result.get("returncode"), error=result.get("error"), output=result.get("output"))
        time.sleep(ANNOUNCEMENT_POLL_SECONDS)


def ensure_announcement_thread():
    global ANNOUNCEMENT_THREAD_STARTED
    if ANNOUNCEMENT_THREAD_STARTED:
        return
    ANNOUNCEMENT_THREAD_STARTED = True
    thread = threading.Thread(target=announcement_worker, name="announcement-worker", daemon=True)
    thread.start()


def read_meminfo():
    values = {}
    try:
        for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            parts = raw.strip().split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0]) * 1024
    except (OSError, ValueError):
        return {}
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0) if total else 0
    return {"totalBytes": total, "availableBytes": available, "usedBytes": used, "usedPercent": round((used / total) * 100, 1) if total else None}


def read_loadavg():
    try:
        parts = pathlib.Path("/proc/loadavg").read_text(encoding="utf-8").split()
        return {"one": float(parts[0]), "five": float(parts[1]), "fifteen": float(parts[2]), "runnable": parts[3], "lastPid": parts[4]}
    except (OSError, ValueError, IndexError):
        return {}


def docker_api(path):
    sock_path = pathlib.Path(DOCKER_SOCKET)
    if not sock_path.exists():
        raise FileNotFoundError(f"Docker socket not found: {sock_path}")
    request = f"GET {path} HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n".encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(str(sock_path))
        sock.sendall(request)
        chunks = []
        header = b""
        body = b""
        headers = {}
        content_length = None
        chunked = False
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
            raw = b"".join(chunks)
            if not header and b"\r\n\r\n" in raw:
                header, _, body = raw.partition(b"\r\n\r\n")
                for line in header.split(b"\r\n")[1:]:
                    key, sep, value = line.partition(b":")
                    if sep:
                        headers[key.decode("utf-8", errors="replace").strip().lower()] = value.decode("utf-8", errors="replace").strip()
                if "content-length" in headers:
                    try:
                        content_length = int(headers["content-length"])
                    except ValueError:
                        content_length = None
                chunked = headers.get("transfer-encoding", "").lower() == "chunked"
            elif header:
                body += chunk
            if content_length is not None and len(body) >= content_length:
                body = body[:content_length]
                break
            if chunked and b"\r\n0\r\n\r\n" in body:
                break
    if not header:
        raw = b"".join(chunks)
        header, _, body = raw.partition(b"\r\n\r\n")
    if b" 200 " not in header.split(b"\r\n", 1)[0]:
        raise RuntimeError(header.split(b"\r\n", 1)[0].decode("utf-8", errors="replace"))
    if b"transfer-encoding: chunked" in header.lower():
        body = decode_chunked_body(body)
    return json.loads(body.decode("utf-8") or "null")


def decode_chunked_body(body):
    out = b""
    rest = body
    while rest:
        size_raw, sep, rest = rest.partition(b"\r\n")
        if not sep:
            break
        try:
            size = int(size_raw.split(b";", 1)[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        out += rest[:size]
        rest = rest[size + 2:]
    return out


def fmt_bytes(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    return f"{value:.1f} {units[unit]}" if unit else f"{int(value)} {units[unit]}"


def docker_container_stats(live_stats=False):
    containers = docker_api(f"/containers/json?all=1&filters={urllib.parse.quote(json.dumps({'label': [f'com.docker.compose.project={DOCKER_COMPOSE_PROJECT}']}))}")
    rows = []

    def container_row(container):
        container_id = container.get("Id", "")
        labels = container.get("Labels") or {}
        name = (container.get("Names") or [""])[0].lstrip("/")
        base = {
            "service": labels.get("com.docker.compose.service", name),
            "name": name,
            "status": container.get("State"),
        }
        if not live_stats:
            return base
        try:
            stats = docker_api(f"/containers/{container_id}/stats?stream=false")
        except Exception as exc:
            return {"service": labels.get("com.docker.compose.service", name), "name": name, "status": container.get("State"), "error": str(exc)}
        memory = stats.get("memory_stats") or {}
        cpu = stats.get("cpu_stats") or {}
        precpu = stats.get("precpu_stats") or {}
        networks = stats.get("networks") or {}
        blkio = ((stats.get("blkio_stats") or {}).get("io_service_bytes_recursive") or [])
        mem_usage = int(memory.get("usage") or 0)
        mem_limit = int(memory.get("limit") or 0)
        cpu_total = int((cpu.get("cpu_usage") or {}).get("total_usage") or 0)
        precpu_total = int((precpu.get("cpu_usage") or {}).get("total_usage") or 0)
        system_total = int(cpu.get("system_cpu_usage") or 0)
        presystem_total = int(precpu.get("system_cpu_usage") or 0)
        online_cpus = int(cpu.get("online_cpus") or len(((cpu.get("cpu_usage") or {}).get("percpu_usage") or [])) or 1)
        cpu_delta = cpu_total - precpu_total
        system_delta = system_total - presystem_total
        cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100, 1) if cpu_delta > 0 and system_delta > 0 else 0.0
        net_rx = sum(int(v.get("rx_bytes") or 0) for v in networks.values())
        net_tx = sum(int(v.get("tx_bytes") or 0) for v in networks.values())
        block_read = sum(int(v.get("value") or 0) for v in blkio if str(v.get("op", "")).lower() == "read")
        block_write = sum(int(v.get("value") or 0) for v in blkio if str(v.get("op", "")).lower() == "write")
        return base | {
            "cpuPercent": cpu_percent,
            "memory": f"{fmt_bytes(mem_usage)} / {fmt_bytes(mem_limit)}",
            "memoryUsageBytes": mem_usage,
            "memoryLimitBytes": mem_limit,
            "memoryPercent": round((mem_usage / mem_limit) * 100, 1) if mem_limit else None,
            "netIO": f"{fmt_bytes(net_rx)} / {fmt_bytes(net_tx)}",
            "netRxBytes": net_rx,
            "netTxBytes": net_tx,
            "blockIO": f"{fmt_bytes(block_read)} / {fmt_bytes(block_write)}",
            "pids": int((stats.get("pids_stats") or {}).get("current") or 0),
        }

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(48, max(len(containers), 1)))
    try:
        future_map = {executor.submit(container_row, container): container for container in containers}
        deadline = time.monotonic() + 4
        while future_map and time.monotonic() < deadline:
            timeout = max(deadline - time.monotonic(), 0)
            done, _ = concurrent.futures.wait(future_map, timeout=timeout, return_when=concurrent.futures.FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                container = future_map.pop(future)
                labels = container.get("Labels") or {}
                name = (container.get("Names") or [""])[0].lstrip("/")
                try:
                    rows.append(future.result())
                except Exception as exc:
                    rows.append({"service": labels.get("com.docker.compose.service", name), "name": name, "status": container.get("State"), "error": str(exc)})
        for future, container in list(future_map.items()):
            future.cancel()
            labels = container.get("Labels") or {}
            name = (container.get("Names") or [""])[0].lstrip("/")
            rows.append({"service": labels.get("com.docker.compose.service", name), "name": name, "status": container.get("State"), "error": "stats timed out"})
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return sorted(rows, key=lambda r: str(r.get("service", "")))


def db_connect():
    return psycopg2.connect(
        host=os.environ.get("DUNE_ADMIN_DB_HOST", "postgres"),
        port=int(os.environ.get("DUNE_ADMIN_DB_PORT", "5432")),
        database=DATABASE,
        user=os.environ.get("DUNE_ADMIN_DB_USER", "dune"),
        password=os.environ.get("DUNE_ADMIN_DB_PASSWORD", os.environ.get("POSTGRES_DUNE_PASSWORD", "")),
        connect_timeout=5,
        options="-c statement_timeout=15000",
    )


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def update_daily_player_peak(count):
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    now_text = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {"days": {}}
    try:
        if PLAYER_PEAKS_FILE.exists():
            data = json.loads(PLAYER_PEAKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {"days": {}}
    days = data.setdefault("days", {})
    day = days.setdefault(today, {})
    previous_peak = int(day.get("peak") or 0)
    if int(count) >= previous_peak:
        day["peak"] = int(count)
        day["peakAt"] = now_text
    else:
        day["peak"] = previous_peak
    day["last"] = int(count)
    day["lastAt"] = now_text
    data["today"] = today
    data["peakToday"] = int(day.get("peak") or count)
    data["peakTodayAt"] = day.get("peakAt") or now_text
    data["lastCount"] = int(count)
    data["lastCountAt"] = now_text
    try:
        PLAYER_PEAKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PLAYER_PEAKS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(PLAYER_PEAKS_FILE)
    except Exception as exc:
        return {"date": today, "peak": max(previous_peak, int(count)), "last": int(count), "error": str(exc)}
    return {"date": today, "peak": data["peakToday"], "peakAt": data["peakTodayAt"], "last": int(count), "lastAt": now_text}


def read_env():
    values = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def write_safe_env(updates):
    original = ENV_FILE.read_text(encoding="utf-8").splitlines()
    seen = set()
    rendered = []
    for line in original:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            rendered.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in SAFE_ENV_KEYS and key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rendered.append(line)
    for key in sorted(SAFE_ENV_KEYS - seen):
        if key in updates:
            rendered.append(f"{key}={updates[key]}")
    backup_file(ENV_FILE)
    ENV_FILE.write_text("\n".join(rendered) + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass


ARTIFICIAL_EXCHANGE_STATE_DIR = BACKUP_ROOT / "artificial-exchange"
ARTIFICIAL_EXCHANGE_CATALOG = ARTIFICIAL_EXCHANGE_STATE_DIR / "catalog.json"


def command_output_excerpt(text, limit=6000):
    text = (text or "").strip()
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text


def run_workspace_command(args, timeout=45):
    env = os.environ.copy()
    env.setdefault("ADMIN_WORKSPACE", str(ROOT))
    try:
        result = subprocess.run(
            args,
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "args": args}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": command_output_excerpt(result.stdout),
        "stderr": command_output_excerpt(result.stderr),
        "args": args,
    }


def parse_last_json(text):
    text = (text or "").strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if text[index + end:].strip():
            continue
        return value
    return None


def artificial_exchange_catalog_summary():
    if not ARTIFICIAL_EXCHANGE_CATALOG.exists():
        return {"ok": False, "path": str(ARTIFICIAL_EXCHANGE_CATALOG), "error": "catalog has not been built"}
    try:
        data = json.loads(ARTIFICIAL_EXCHANGE_CATALOG.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "path": str(ARTIFICIAL_EXCHANGE_CATALOG), "error": str(exc)}
    rows = data.get("items") if isinstance(data, dict) else data
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        rows = []
    return {
        "ok": True,
        "path": str(ARTIFICIAL_EXCHANGE_CATALOG),
        "items": len(rows),
        "enabledItems": sum(1 for row in rows if row.get("enabled")),
        "validatedItems": sum(1 for row in rows if row.get("sellable_status") == "validated"),
        "lowConfidenceItems": sum(1 for row in rows if row.get("confidence") == "low"),
        "mtime": datetime.datetime.fromtimestamp(ARTIFICIAL_EXCHANGE_CATALOG.stat().st_mtime, datetime.timezone.utc).isoformat(),
    }


def artificial_exchange_systemd_service(name):
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return {"name": name, "available": False, "ok": False, "error": "systemctl is not available in this runtime"}
    result = run_workspace_command([systemctl, "show", name, "--property=LoadState,ActiveState,SubState,UnitFileState,NRestarts,ExecMainStatus", "--no-pager"], timeout=10)
    service = {"name": name, "available": True, "ok": result.get("ok")}
    if not result.get("ok"):
        service["error"] = result.get("stderr") or result.get("stdout") or "systemctl show failed"
        return service
    for line in result.get("stdout", "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            service[key] = value
    service["ok"] = service.get("ActiveState") == "active"
    return service


def artificial_exchange_status():
    env_values = read_env()
    buyer_id = env_values.get("DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID", os.environ.get("DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID", "0")) or "0"
    scan_limit = env_values.get("DUNE_ARTIFICIAL_EXCHANGE_SCAN_LIMIT", "200") or "200"
    check = run_workspace_command([
        sys.executable,
        str(ROOT / "scripts" / "artificial-exchange-bot.py"),
        "--check-ready",
        "--buyer-controller-id",
        str(buyer_id),
        "--limit",
        str(scan_limit),
        "--settlement-limit",
        "50",
    ], timeout=60)
    check_json = parse_last_json(check.get("stdout", ""))
    if check_json is None and check.get("stderr"):
        check_json = parse_last_json(check.get("stderr", ""))
    return {
        "ok": bool(check.get("ok")) and bool((check_json or {}).get("ok", True)),
        "env": {key: env_values.get(key, "") for key in sorted(SAFE_ENV_KEYS) if key.startswith("DUNE_ARTIFICIAL_EXCHANGE_")},
        "catalog": artificial_exchange_catalog_summary(),
        "readiness": check_json,
        "readinessCommand": check,
        "services": {
            "buyer": artificial_exchange_systemd_service("dune-artificial-exchange-bot.service"),
            "populator": artificial_exchange_systemd_service("dune-artificial-exchange-populator.service"),
            "watchdog": artificial_exchange_systemd_service("dune-artificial-exchange-watchdog.timer"),
        },
    }


def artificial_exchange_action(action):
    systemctl = shutil.which("systemctl")
    scripts = ROOT / "scripts"
    commands = {
        "build-catalog": ([sys.executable, str(scripts / "build-exchange-catalog.py")], 120),
        "check-ready": ([sys.executable, str(scripts / "artificial-exchange-bot.py"), "--check-ready"], 60),
        "buyer-dry-run": ([sys.executable, str(scripts / "artificial-exchange-bot.py"), "--dry-run", "--report-skips", "100"], 90),
        "settlement-report": ([sys.executable, str(scripts / "artificial-exchange-bot.py"), "--settlement-report"], 60),
        "validate-populator": ([sys.executable, str(scripts / "artificial-exchange-bot.py"), "--validate-populator-once"], 120),
        "install-buyer-service": ([str(scripts / "install-artificial-exchange-service.sh"), str(ENV_FILE), "/etc/systemd/system/dune-artificial-exchange-bot.service", "buyer"], 120),
        "install-populator-service": ([str(scripts / "install-artificial-exchange-service.sh"), str(ENV_FILE), "/etc/systemd/system/dune-artificial-exchange-populator.service", "populator"], 120),
        "install-watchdog-timer": ([str(scripts / "install-artificial-exchange-watchdog-timer.sh"), str(ENV_FILE)], 120),
        "watchdog-once": ([str(scripts / "artificial-exchange-watchdog.sh"), str(ENV_FILE)], 60),
    }
    service_actions = {"start", "stop", "restart", "status"}
    service_names = {
        "buyer": "dune-artificial-exchange-bot.service",
        "populator": "dune-artificial-exchange-populator.service",
        "watchdog": "dune-artificial-exchange-watchdog.timer",
    }
    if action in commands:
        cmd, timeout = commands[action]
        result = run_workspace_command(cmd, timeout=timeout)
        parsed = parse_last_json(result.get("stdout", "")) or parse_last_json(result.get("stderr", ""))
        if parsed is not None:
            result["json"] = parsed
        return result
    if ":" in action:
        service_action, target = action.split(":", 1)
        if service_action in service_actions and target in service_names:
            if not systemctl:
                return {"ok": False, "error": "systemctl is not available in this runtime", "action": action}
            if service_action == "status":
                return artificial_exchange_systemd_service(service_names[target])
            return run_workspace_command([systemctl, service_action, service_names[target]], timeout=30)
    raise ValueError(f"unknown artificial exchange action: {action}")


def backup_file(path):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    shutil.copy2(path, BACKUP_ROOT / f"{stamp}-{path.name}")


def strip_ini_comment(value):
    for marker in (";;", ";"):
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.strip()


def parse_ini_multivalue(path):
    sections = {}
    if not path.exists():
        return sections
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line.strip("[]").strip()
            sections.setdefault(current, {})
            continue
        if not current or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        value = strip_ini_comment(value)
        bucket = sections.setdefault(current, {}).setdefault(key, [])
        bucket.append(value)
    return sections


def set_ini_section_values(path, section, updates):
    original = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    rendered = []
    seen = set()
    in_section = False
    inserted = False
    target_header = f"[{section}]".lower()

    def append_missing():
        nonlocal inserted
        if inserted:
            return
        for key, value in updates.items():
            if key not in seen:
                rendered.append(f"{key}={value}")
                seen.add(key)
        inserted = True

    for raw_line in original:
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section:
                append_missing()
            in_section = stripped.lower() == target_header
            rendered.append(raw_line)
            continue
        if in_section and "=" in raw_line:
            key, _ = raw_line.split("=", 1)
            key = key.strip()
            if key in updates:
                rendered.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        rendered.append(raw_line)
    if not original:
        rendered.append(f"[{section}]")
        in_section = True
    if in_section:
        append_missing()
    elif not inserted:
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append(f"[{section}]")
        append_missing()
    backup_file(path)
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def read_ini_section_value(path, section, key):
    sections = parse_ini_multivalue(path)
    values = sections.get(section, {}).get(key, [])
    return values[-1] if values else None


def render_spice_caps(value):
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        raise ValueError("spice caps must be an object or raw m_PerMapSystemSettings string")
    defaults = {"Small": (60, 60), "Medium": (12, 12), "Large": (1, 1)}
    caps = {}
    for name, pair in defaults.items():
        raw = value.get(name.lower(), value.get(name, {}))
        if isinstance(raw, dict):
            primed = int(raw.get("primed", raw.get("MaxGloballyPrimed", pair[0])))
            active = int(raw.get("active", raw.get("MaxGloballyActive", pair[1])))
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            primed, active = int(raw[0]), int(raw[1])
        else:
            primed, active = pair
        if primed < 0 or active < 0 or primed > 1000 or active > 1000:
            raise ValueError(f"{name} spice caps must be between 0 and 1000")
        caps[name] = (primed, active)
    field_settings = ",".join(
        f'((Name="{name}"), (MaxGloballyPrimed={primed},MaxGloballyActive={active}))'
        for name, (primed, active) in caps.items()
    )
    return f'(("DeepDesert_1", (m_SpiceFieldTypeSettings=({field_settings}))),("Survival_1", (m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=5,MaxGloballyActive=5))))))'


def validate_typed_knob_value(knob_id, value):
    meta = TYPED_CONFIG_KNOBS[knob_id]
    kind = meta["type"]
    if kind == "bool":
        lowered = str(value).strip().lower()
        if lowered not in ("true", "false"):
            raise ValueError(f"{knob_id} must be true or false")
        return "True" if lowered == "true" else "False"
    if kind == "bool01":
        lowered = str(value).strip().lower()
        if lowered not in ("0", "1", "true", "false"):
            raise ValueError(f"{knob_id} must be 0/1 or true/false")
        return "1" if lowered in ("1", "true") else "0"
    if kind == "float":
        try:
            number = float(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"{knob_id} must be a number") from exc
        if number < float(meta.get("min", -10**9)) or number > float(meta.get("max", 10**9)):
            raise ValueError(f"{knob_id} is outside allowed range")
        return str(number)
    if kind == "int":
        try:
            number = int(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"{knob_id} must be an integer") from exc
        if number < int(meta.get("min", -10**9)) or number > int(meta.get("max", 10**9)):
            raise ValueError(f"{knob_id} is outside allowed range")
        return str(number)
    if kind == "spice_caps":
        return render_spice_caps(value)
    raise ValueError(f"unsupported knob type: {kind}")


def read_typed_knobs():
    rows = {}
    for knob_id, meta in TYPED_CONFIG_KNOBS.items():
        path = ALLOWED_CONFIGS[meta["file"]]
        current = read_ini_section_value(path, meta["section"], meta["key"]) if path.exists() else None
        rows[knob_id] = dict(meta, id=knob_id, value=current if current is not None else meta.get("default", ""))
    return rows


def write_typed_knobs(updates):
    validated = {}
    by_file_section = {}
    for knob_id, value in updates.items():
        if knob_id not in TYPED_CONFIG_KNOBS:
            continue
        meta = TYPED_CONFIG_KNOBS[knob_id]
        rendered = validate_typed_knob_value(knob_id, value)
        validated[knob_id] = rendered
        by_file_section.setdefault((meta["file"], meta["section"]), {})[meta["key"]] = rendered
    for (filename, section), values in by_file_section.items():
        set_ini_section_values(ALLOWED_CONFIGS[filename], section, values)
    return {"ok": True, "updated": validated, "restartRequired": any(TYPED_CONFIG_KNOBS[k]["restart"] for k in validated)}


def gm_command_catalog():
    user_game = parse_ini_multivalue(ALLOWED_CONFIGS["UserGame.ini"])
    local_scripts = {
        section.split(".", 1)[1]: values.get("Cmd", [])
        for section, values in user_game.items()
        if section.startswith("CheatScript.")
    }
    scripts = dict(GM_CHEAT_SCRIPTS)
    scripts.update({name: commands for name, commands in local_scripts.items() if commands})
    commands = [{"name": name, "kind": "console", "notes": "Console command allowed by DedicatedServerGame.ini."} for name in GM_ALLOWED_COMMANDS]
    commands.extend({
        "name": name,
        "kind": "gm",
        "notes": GM_COMMAND_NOTES.get(name, "GM command exposed by DedicatedServerGame.ini allow-list."),
    } for name in GM_ALLOWED_GM_COMMANDS)
    return {
        "enabled": GM_COMMANDS_ENABLED,
        "payloadVerified": GM_COMMAND_PAYLOAD_VERIFIED,
        "status": "catalog-ready-route-blocked",
        "reason": "The native command names and map queues are known, but the live RabbitMQ payload envelope for UDuneServerCommandSubsystem is not yet verified.",
        "activeAllowListSource": "DuneSandbox/Config/DedicatedServerGame.ini from the live survival container",
        "commands": commands,
        "cheatScripts": [{"name": name, "commands": lines} for name, lines in sorted(scripts.items())],
        "chatCommands": list(GM_CHAT_COMMANDS),
        "panelPresets": list(GM_PANEL_PRESETS),
        "routeCandidates": gm_route_candidates(),
        "safeProbe": {"command": "PrintPos", "why": "Read-only position print is the safest first execution probe once payload format is known."},
    }


def gm_route_candidates():
    rows = []
    try:
        farm = query("select server_id,map,ready,alive from dune.farm_state order by map, server_id")
    except Exception:
        farm = []
    for row in farm:
        server_id = row.get("server_id") or ""
        if server_id:
            rows.append({
                "exchange": "rpc",
                "routingKey": server_id,
                "map": row.get("map"),
                "ready": row.get("ready"),
                "alive": row.get("alive"),
                "notes": "Map queue binding observed in admin RabbitMQ.",
            })
            rows.append({
                "exchange": "response",
                "routingKey": f"response.{server_id}",
                "map": row.get("map"),
                "ready": row.get("ready"),
                "alive": row.get("alive"),
                "notes": "Per-map response route observed in admin RabbitMQ.",
            })
            rows.append({
                "exchange": "grant",
                "routingKey": f"grant.{server_id}",
                "map": row.get("map"),
                "ready": row.get("ready"),
                "alive": row.get("alive"),
                "notes": "Per-map grant route observed in admin RabbitMQ.",
            })
    return rows


def content_catalog_entries():
    entries = [
        {"id": "deep-desert-spice-caps", "group": "Deep Desert", "surface": "Config/INI knobs", "capability": "Raise or lower Deep Desert spice field active/primed caps.", "evidence": ["DEEP_DESERT_EVENT_KNOBS.md", "SERVER_RUNTIME_SURFACES.md", "dune.spicefield_types", "dune.resourcefield_state"], "confidence": "high", "mutationRisk": "medium", "restartRequired": True, "validationCommand": "select * from dune.spicefield_types order by map, field_kind_id;", "rollback": "Restore backed-up UserGame.ini and restart deep-desert."},
        {"id": "sandstorm-coriolis-safe-toggles", "group": "Deep Desert", "surface": "Config/INI knobs", "capability": "Toggle sandstorm/Coriolis safe fields already present in config.", "evidence": ["config/UserGame.ini", "config/UserEngine.ini", "SERVER_RUNTIME_SURFACES.md"], "confidence": "high", "mutationRisk": "medium", "restartRequired": True, "validationCommand": "rg -n 'Sandstorm|Coriolis' config/UserGame.ini config/UserEngine.ini", "rollback": "Restore backed-up config file and restart affected maps."},
        {"id": "economy-bundle-plan", "group": "Economy/Admin", "surface": "Database state", "capability": "Plan currency, item, and XP grants as one audited dry-run bundle.", "evidence": ["admin/admin_panel.py existing currency/xp/item mutation paths", "docs/admin-mutation-map.md"], "confidence": "high", "mutationRisk": "medium", "restartRequired": False, "validationCommand": "Use /api/admin/bundle dry_run=true, then inspect balances/inventory after gated execution.", "rollback": "Manual compensating currency/xp/item edits from audit record."},
        {"id": "faction-reputation-plan", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and plan faction reputation changes for a player pawn.", "evidence": ["dune.set_player_faction_reputation(in_actor_id bigint, in_faction_id smallint, in_reputation_amount integer)", "dune.get_player_current_faction_reputation", "character detail reads dune.player_faction_reputation"], "confidence": "moderate-to-high", "mutationRisk": "high", "restartRequired": False, "validationCommand": "select * from dune.player_faction_reputation where actor_id=<pawn_id> order by faction_id;", "rollback": "Call /api/admin/faction-reputation with mode=set and the previous value from the dry-run/audit record."},
        {"id": "player-faction-change", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally change a player's faction using first-party faction functions.", "evidence": ["dune.change_player_faction(in_player_id bigint, in_faction_id smallint, neutral_faction_id smallint, in_utc_time_faction_change timestamp)", "dune.get_player_faction", "dune.factions table contains Atreides/Harkonnen/None/Smuggler"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/faction dry_run=true; verify dune.player_faction and guild side effects after disposable offline test.", "rollback": "Call /api/admin/faction with the previous faction_id from the dry-run/audit record."},
        {"id": "journey-server-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally reveal, complete, reset, or delete known journey story nodes for an offline player.", "evidence": ["dune.admin_get_journey_details(in_player_id text, in_story_node_id text)", "dune.reveal_journey_story_nodes_for_player", "dune.complete_journey_story_nodes_for_player", "dune.reset_journey_story_nodes_for_player", "dune.delete_journey_story_nodes_for_player"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/journey dry_run=true with known story_node_ids; inspect admin_get_journey_details before and after.", "rollback": "Use reset/delete/reveal/complete compensating calls for the affected story_node_ids from the audit record."},
        {"id": "respawn-location-delete", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally delete one known respawn location by UUID by re-saving the current respawnlocation array without that entry.", "evidence": ["dune.get_respawn_locations(in_account_id bigint)", "dune.update_respawn_locations(player_id bigint, respawn_locations respawnlocation[])", "dune.player_respawn_locations table"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/respawn-location dry_run=true; compare get_respawn_locations before and after.", "rollback": "No automatic rollback yet; restoring requires reconstructing the removed respawnlocation composite."},
        {"id": "landsraad-term-admin", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally change or force-end the current Landsraad term through first-party functions.", "evidence": ["dune.landsraad_load_current_term", "dune.landsraad_change_term_end_time", "dune.landsraad_force_end_term", "dune.landsraad_decree_term live rows"], "confidence": "moderate", "mutationRisk": "very high", "restartRequired": False, "validationCommand": "POST /api/admin/landsraad dry_run=true; inspect landsraad_load_current_term and landsraad_decree_term before/after.", "rollback": "For end-time changes, call change-end-time with the previous end_time. Force-end is not safely reversible."},
        {"id": "guild-admin-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect guild state and optionally edit guild description or promote/demote member roles through first-party guild functions.", "evidence": ["dune.get_guild_data", "dune.get_guild_members", "dune.edit_guild_description", "dune.promote_guild_member", "dune.demote_guild_member", "dune.guilds and dune.guild_members tables"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/world-state/inspect with guild_id; POST /api/admin/guild dry_run=true.", "rollback": "Dry-run/audit records prior description or role_id; apply a compensating guild mutation."},
        {"id": "marker-delete-functions", "group": "World Rules", "surface": "Database state", "capability": "Inspect and optionally delete known marker rows by marker id or static-location key through first-party marker functions.", "evidence": ["dune.delete_markers_by_id", "dune.delete_static_location_markers", "dune.delete_markers_return_actor_ids", "dune.markers and dune.player_markers tables"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/world-state/inspect; POST /api/admin/marker dry_run=true with marker_ids or static_location_keys.", "rollback": "No automatic rollback; marker save/composite semantics are not mapped, so preserve dry-run/audit rows before execution."},
        {"id": "landclaim-segment-functions", "group": "World Rules", "surface": "Database state", "capability": "Inspect existing landclaim grid segments and optionally add one segment for a known totem id.", "evidence": ["dune.get_landclaim_segments", "dune.add_landclaim_segment", "dune.landclaim_segments table"], "confidence": "moderate for function existence, low-to-moderate for live semantics", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/world-state/inspect; POST /api/admin/landclaim dry_run=true with totem_id/grid coordinates.", "rollback": "No delete function mapped; rollback requires DB backup restore or manual table repair."},
        {"id": "exchange-solari-balance", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally adjust a player's Dune Exchange Solari balance through first-party exchange functions.", "evidence": ["dune.dune_exchange_retrieve_solari_balance", "dune.dune_exchange_modify_user_solari_balance", "dune.dune_exchange_users table"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/economy/inspect; POST /api/admin/exchange dry_run=true.", "rollback": "Dry-run/audit records prior balance; apply mode=set to restore."},
        {"id": "exchange-order-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect exchange order/storage functions and tables without adding, fulfilling, relisting, cancelling, or purging orders.", "evidence": ["dune_exchange_add_sell_order", "dune_exchange_fulfill_sell_order", "dune_exchange_cancel_order", "dune_exchange_orders table", "dune_exchange_sell_orders table"], "confidence": "moderate for existence, low for safe admin semantics", "mutationRisk": "blocked", "restartRequired": False, "validationCommand": "POST /api/admin/economy/inspect with optional owner_id/exchange_id.", "rollback": "No execution in v1."},
        {"id": "vehicle-restore-functions", "group": "Limits", "surface": "Database state", "capability": "Inspect vehicle, recovered vehicle, backup vehicle, and module state without restoring/spawning vehicles.", "evidence": ["dune.get_player_owned_vehicles_data", "dune.load_recovered_vehicles", "dune.restore_recovered_vehicle", "dune.restore_backup_vehicle", "dune.vehicle_modules table"], "confidence": "moderate for reads, low for restore semantics", "mutationRisk": "blocked", "restartRequired": False, "validationCommand": "POST /api/admin/world-state/inspect or /api/admin/economy/inspect with account_id.", "rollback": "No execution in v1; restore requires serverinfo/transform validation."},
        {"id": "base-backup-functions", "group": "Limits", "surface": "Database state", "capability": "Inspect base backup save/recycle/delete functions without exposing base backup writes.", "evidence": ["base_backup_get_available_backups", "base_backup_save_from_totem", "base_backup_recycle", "base_backup_delete", "base_backups table"], "confidence": "moderate for existence, low for safe mutation semantics", "mutationRisk": "blocked", "restartRequired": False, "validationCommand": "POST /api/admin/economy/inspect with player_id.", "rollback": "No execution in v1."},
        {"id": "player-tag-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally add/remove player tags through first-party tag functions.", "evidence": ["dune.admin_read_player_tags", "dune.update_player_tags", "dune.player_tags table"], "confidence": "moderate", "mutationRisk": "medium", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect; POST /api/admin/player-tags dry_run=true.", "rollback": "Dry-run/audit records prior tags; apply inverse add/remove arrays."},
        {"id": "player-access-code-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally create/delete/reset server player access codes through first-party functions.", "evidence": ["dune.get_player_access_codes", "dune.create_server_player_access_codes", "dune.delete_server_player_access_codes", "dune.reset_server_all_player_access_codes"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect; POST /api/admin/access-code dry_run=true.", "rollback": "Dry-run/audit records prior codes; recreate deleted codes or delete created codes."},
        {"id": "character-slot-hibernation", "group": "Limits", "surface": "Database state", "capability": "Inspect active and same-owner hibernated character candidates, then plan new-character or switch-character actions without synthetic player_state rows.", "evidence": ["dune.player_state", "dune.accounts", "lifecycle function discovery for login_account/delete_account/takeover_account/save_player/save_player_pawn"], "confidence": "moderate for inspection, low for execution", "mutationRisk": "blocked until native swap contract is proven", "restartRequired": False, "validationCommand": "GET /api/admin/character-slots?account_id=<id>; POST /api/admin/character-slots/plan dry_run=true.", "rollback": "No execution in v1 unless a native lifecycle path is validated; restore from DB backup if future execution is enabled."},
        {"id": "communinet-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally update Communinet active/selected-channel state or tune/remove one player channel through first-party functions.", "evidence": ["dune.load_communinet_player_data", "dune.update_communinet_player_data", "dune.update_communinet_player_channel", "dune.remove_communinet_player_channel", "communinet_player tables"], "confidence": "moderate", "mutationRisk": "medium", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect; POST /api/admin/communinet dry_run=true.", "rollback": "Dry-run/audit records prior Communinet rows; apply compensating data/channel updates."},
        {"id": "tutorial-entry-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally create/update one tutorial state row for a player through a first-party function.", "evidence": ["dune.get_all_tutorial_entries", "dune.create_or_update_tutorial_entry", "dune.tutorials", "dune.tutorial_per_player"], "confidence": "moderate", "mutationRisk": "medium", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect; POST /api/admin/tutorial dry_run=true.", "rollback": "Dry-run/audit records prior tutorial row; apply compensating tutorial state. Missing-row deletion is not exposed."},
        {"id": "permission-actor-functions", "group": "World Rules", "surface": "Database state", "capability": "Inspect and optionally set permission actor name/access level or player rank through first-party functions.", "evidence": ["dune.permission_set_name", "dune.permission_set_access_level", "dune.permission_set_player_rank", "dune.permission_remove_player_rank", "permission_actor tables"], "confidence": "moderate", "mutationRisk": "high", "restartRequired": False, "validationCommand": "POST /api/admin/world-state/inspect; POST /api/admin/permission dry_run=true.", "rollback": "Dry-run/audit records prior actor/rank rows; apply compensating set-name/set-access-level/set-player-rank when possible."},
        {"id": "vendor-cycle-timestamp-functions", "group": "Economy/Admin", "surface": "Database state", "capability": "Inspect and optionally update one vendor/player stock-cycle timestamp through a first-party function.", "evidence": ["dune.update_vendor_timestamp_for_player", "dune.interact_get_vendor_items_bought_from_player", "dune.vendor_stock_cycle table"], "confidence": "moderate", "mutationRisk": "medium", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect; POST /api/admin/vendor dry_run=true.", "rollback": "Dry-run/audit records prior timestamp; apply compensating timestamp update."},
        {"id": "taxation-landsraad-vendor-functions", "group": "Limits", "surface": "Database state", "capability": "Inspect taxation invoice, Landsraad task progress, vendor stock counts, lore, and dungeon functions without exposing high-risk writes.", "evidence": ["tax_invoice table", "landsraad_task_* tables", "vendor_stock_state table", "lore tables", "dungeon completion tables", "pg_proc function signatures"], "confidence": "moderate for existence, low for mutation safety", "mutationRisk": "blocked except vendor timestamp", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect and catalog evidence endpoints.", "rollback": "No execution in v1 for blocked routes."},
        {"id": "vendor-tutorial-lore-dungeon-overmap-functions", "group": "Limits", "surface": "Database state", "capability": "Inspect vendor stock, tutorial, lore, dungeon completion, overmap survival, and Coriolis functions without exposing writes.", "evidence": ["vendor_stock_state tables", "tutorial_per_player table", "lore_pickups tables", "dungeon_completion tables", "overmap_players table", "coriolis functions"], "confidence": "moderate for existence, low for mutation safety", "mutationRisk": "blocked", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect with account_id/player_id.", "rollback": "No execution in v1."},
        {"id": "party-account-lifecycle-functions", "group": "Limits", "surface": "Database state", "capability": "Inspect party, account deletion/takeover, Communinet, dungeon, tutorial, and player lifecycle functions without executing destructive routes.", "evidence": ["party functions", "delete_account", "takeover_account", "communinet functions", "dungeon completion functions", "player_state tables"], "confidence": "moderate for existence, low for mutation safety", "mutationRisk": "blocked except tags/access codes", "restartRequired": False, "validationCommand": "POST /api/admin/player-lifecycle/inspect with optional account_id/player_id.", "rollback": "No execution for blocked lifecycle surfaces."},
        {"id": "world-state-function-discovery", "group": "Limits", "surface": "Database state", "capability": "Discover guild, vehicle, marker, landclaim, recipe, and respawn function/table evidence without executing unsafe routes.", "evidence": ["pg_proc runtime schema introspection", "information_schema table/column introspection", "docs/admin-mutation-map.md"], "confidence": "moderate for existence, low-to-moderate for mutation semantics", "mutationRisk": "blocked except promoted guild/respawn paths", "restartRequired": False, "validationCommand": "POST /api/admin/world-state/inspect with optional account_id/player_id/guild_id.", "rollback": "No execution for blocked discovery surfaces."},
        {"id": "offline-player-recovery", "group": "Economy/Admin", "surface": "Database state", "capability": "Preview offline player partition move; network-disconnect teleport uses dune.admin_move_offline_player_to_partition as its verified pawn-row primitive after Survival marks the player Offline.", "evidence": ["PLAYER_LOCATION_SOURCE_AUDIT.md", "database function name observed in local schema", "docs/soft-disconnect-teleport.md"], "confidence": "moderate-to-high for same-partition recovery", "mutationRisk": "high", "restartRequired": False, "validationCommand": "select * from dune.player_state where account_id=<id>;", "rollback": "Move player back to prior partition from audit record."},
        {"id": "mining-resource-multipliers", "group": "World Rules", "surface": "Config/INI knobs", "capability": "Adjust player mining, vehicle mining, and PvP resource multipliers.", "evidence": ["config/UserEngine.ini", "docs/server-knobs-audit.md"], "confidence": "high", "mutationRisk": "low", "restartRequired": True, "validationCommand": "rg -n 'MiningOutput|PvpResourceMultiplier' config/UserEngine.ini", "rollback": "Restore backed-up UserEngine.ini and restart maps."},
        {"id": "pvp-security-zones", "group": "World Rules", "surface": "Config/INI knobs", "capability": "Toggle forced PvP and security-zone behavior.", "evidence": ["config/UserGame.ini", "SERVER_CONFIG_KEYS.md"], "confidence": "high", "mutationRisk": "medium", "restartRequired": True, "validationCommand": "rg -n 'Pvp|SecurityZones' config/UserGame.ini", "rollback": "Restore backed-up UserGame.ini and restart maps."},
        {"id": "shelter-hydration-candidates", "group": "World Rules", "surface": "Config/INI knobs", "capability": "Experiment with shelter thresholds and candidate hydration protection.", "evidence": ["HYDRATION_WATER_KNOBS.md", "config/UserGame.ini"], "confidence": "low", "mutationRisk": "experimental", "restartRequired": True, "validationCommand": "Live in-base/outside hydration test after restart.", "rollback": "Restore backed-up UserGame.ini and restart maps."},
        {"id": "verified-chat-announcements", "group": "GM/RabbitMQ", "surface": "RabbitMQ/admin/GM routes", "capability": "Send verified chat announcements through existing announcement hook.", "evidence": ["scripts/verify-announcement.sh", "admin announcement scheduler"], "confidence": "high", "mutationRisk": "low", "restartRequired": False, "validationCommand": "./scripts/verify-announcement.sh", "rollback": "No persistent rollback; audit records message delivery."},
        {"id": "native-gm-routes", "group": "GM/RabbitMQ", "surface": "RabbitMQ/admin/GM routes", "capability": "Preview native GM command envelopes only.", "evidence": ["scripts/dune_gm_command.py", "DedicatedServerGame.ini command allow-list"], "confidence": "low", "mutationRisk": "blocked", "restartRequired": False, "validationCommand": "Keep execution blocked until DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true is proven live.", "rollback": "No execution in v1."},
        {"id": "recipe-vehicle-function-discovery", "group": "Limits", "surface": "Database state", "capability": "Discover recipe and vehicle DB functions without executing them.", "evidence": ["pg_proc/runtime schema introspection", "docs/admin-mutation-map.md"], "confidence": "moderate for function existence, low for mutation semantics", "mutationRisk": "blocked", "restartRequired": False, "validationCommand": "Use /api/admin/progression/inspect for function signatures and current player rows.", "rollback": "No execution in v1."},
        {"id": "true-new-content-limits", "group": "Limits", "surface": "Hard limits", "capability": "True new maps/assets/physics/algorithms are blocked without cooked assets or binary/plugin work.", "evidence": ["SERVER_RUNTIME_SURFACES.md", "SERVER_CONFIG_KEYS.md"], "confidence": "high", "mutationRisk": "blocked", "restartRequired": None, "validationCommand": "Not applicable for admin v1.", "rollback": "Not applicable."},
    ]
    return entries


def catalog_payload(group=None):
    entries = content_catalog_entries()
    if group:
        entries = [entry for entry in entries if entry["group"].lower() == group.lower()]
    grouped = {name: [entry for entry in entries if entry["group"] == name] for name in CATALOG_GROUPS}
    return {"enabled": CATALOG_ENABLED, "groups": grouped, "surfaces": entries}


def catalog_evidence_payload():
    return {
        "schema": ["surface", "capability", "evidence", "confidence", "mutationRisk", "restartRequired", "validationCommand", "rollback"],
        "rules": [
            "Shipped config plus live DB behavior is strong evidence.",
            "Binary strings are leads until section, syntax, and runtime effect are proven.",
            "Public websites are candidate lookup sources, not authoritative local server evidence.",
        ],
        "entries": content_catalog_entries(),
    }


def catalog_validation_payload():
    return {
        "commands": [
            {"name": "Static compile", "command": "python3 -m py_compile admin/admin_panel.py scripts/admin-chat-commands.py scripts/dune_gm_command.py"},
            {"name": "Repo validation", "command": "make validate"},
            {"name": "Announcement delivery", "command": "./scripts/verify-announcement.sh"},
            {"name": "Spice state", "command": "select * from dune.spicefield_types order by map, field_kind_id;"},
            {"name": "Resource fields", "command": "select map,dimension_index,field_kind_id,count(*),sum(value_remaining) from dune.resourcefield_state group by 1,2,3 order by 1,2,3;"},
        ]
    }


def read_event_state():
    if not EVENT_STATE_FILE.exists():
        return {"events": [], "lastRun": None}
    try:
        state = json.loads(EVENT_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"events": [], "lastRun": None}
    if not isinstance(state, dict):
        return {"events": [], "lastRun": None}
    state.setdefault("events", [])
    state.setdefault("lastRun", None)
    return state


def write_event_state(state):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = EVENT_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    tmp.replace(EVENT_STATE_FILE)


def event_action_plan(action):
    kind = str(action.get("type", "")).strip()
    if kind == "announcement":
        return {"type": kind, "endpoint": "/api/ops/announcement", "payload": {"message": action.get("message", ""), "delay": action.get("delay", "immediate"), "repeat_seconds": int(action.get("repeat_seconds", 0) or 0)}, "safePrimitive": True}
    if kind == "restart":
        return {"type": kind, "endpoint": "/api/ops/restart", "payload": {"target": action.get("target", "deep-desert"), "action": action.get("action", "restart"), "delay": action.get("delay", "immediate"), "execute": False}, "safePrimitive": True}
    if kind == "typed-knob-plan":
        return {"type": kind, "endpoint": "/api/settings/typed-knobs", "payload": {"updates": action.get("updates", {})}, "safePrimitive": True, "dryRunOnly": True}
    if kind == "economy-bundle":
        return {"type": kind, "endpoint": "/api/admin/bundle", "payload": dict(action.get("payload", {}), dry_run=True), "safePrimitive": True, "dryRunOnly": True}
    if kind == "spice-cap-proposal":
        return {"type": kind, "endpoint": "/api/settings/typed-knobs", "payload": {"updates": {"spiceDeepDesertCaps": action.get("caps", {})}}, "safePrimitive": True, "dryRunOnly": True}
    raise ValueError(f"unsupported event action type: {kind}")


def build_event(body):
    actions = body.get("actions", [])
    if not isinstance(actions, list) or not actions:
        raise ValueError("actions must be a non-empty list")
    plans = [event_action_plan(action) for action in actions]
    return {
        "id": secrets.token_hex(8),
        "name": str(body.get("name", "admin event")).strip()[:120] or "admin event",
        "status": "scheduled",
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runAt": str(body.get("runAt", body.get("run_at", ""))).strip() or None,
        "actions": actions,
        "plan": plans,
    }


def event_dry_run(body):
    event = build_event(body)
    event["status"] = "dry-run"
    return {"ok": True, "dryRun": True, "event": event, "executionEnabled": EVENT_EXECUTION_ENABLED}


def create_event(body):
    event = build_event(body)
    with EVENT_LOCK:
        state = read_event_state()
        state["events"].append(event)
        write_event_state(state)
    return event


def cancel_event(event_id):
    with EVENT_LOCK:
        state = read_event_state()
        cancelled = 0
        for event in state.get("events", []):
            if event.get("id") == event_id and event.get("status") == "scheduled":
                event["status"] = "cancelled"
                event["cancelledAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                cancelled += 1
        write_event_state(state)
    return {"ok": True, "cancelled": cancelled}


def execute_event(event_id):
    if not EVENT_EXECUTION_ENABLED:
        raise PermissionError("event execution is disabled; set DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true")
    with EVENT_LOCK:
        state = read_event_state()
        event = next((item for item in state.get("events", []) if item.get("id") == event_id), None)
        if not event:
            raise ValueError("event not found")
        if event.get("status") != "scheduled":
            raise ValueError("event is not scheduled")
        executed = []
        failures = []
        for plan in event.get("plan", []):
            if plan.get("dryRunOnly"):
                executed.append({"type": plan.get("type"), "ok": True, "dryRun": True, "notes": "plan-only action, no write executed"})
            else:
                failures.append({"type": plan.get("type"), "ok": False, "error": "direct event primitive execution is not implemented in v1; use the dedicated endpoint"})
        event["status"] = "failed" if failures else "executed"
        event["lastRunAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state["lastRun"] = {"eventId": event_id, "executed": executed, "failures": failures, "rollback": "Use per-action audit records and config backups."}
        write_event_state(state)
    audit_event("event-run", ok=not failures, event_id=event_id, executed=executed, failures=failures)
    return {"ok": not failures, "eventId": event_id, "executed": executed, "failures": failures}


def gm_payload_preview(body):
    command = str(body.get("command", "")).strip()
    args = str(body.get("args", "")).strip()
    target_player = str(body.get("target_player", body.get("targetPlayer", ""))).strip()
    route = str(body.get("route", "")).strip() or "Survival_11"
    admin_player = str(body.get("admin_player", body.get("adminPlayer", ""))).strip()
    mode = str(body.get("mode", "")).strip() or os.environ.get("DUNE_GM_COMMAND_ENVELOPE_MODE", "service-message")
    allowed = set(GM_ALLOWED_COMMANDS) | set(GM_ALLOWED_GM_COMMANDS) | {f"CheatScript {name}" for name in GM_CHEAT_SCRIPTS}
    if command not in allowed and not command.startswith("CheatScript "):
        raise ValueError("command is not in the discovered allow-list")
    text = " ".join(part for part in (command, args) if part)
    envelope = build_envelope(mode, text, target_player=target_player, admin_player=admin_player)
    return {
        "ok": True,
        "dryRun": True,
        "route": {"exchange": "rpc", "routingKey": route},
        "targetPlayer": target_player,
        "adminPlayer": admin_player,
        "mode": mode,
        "commandText": text,
        "blocked": True,
        "reason": "Native command execution is blocked until UDuneServerCommandSubsystem RabbitMQ payload format is verified.",
        "payload": envelope,
    }


def gm_payload_execute(body):
    preview = gm_payload_preview(body)
    route = preview["route"]["routingKey"]
    if os.environ.get("DUNE_GM_COMMAND_TRANSPORT", "amqp") == "management":
        result = publish_command_management(
            preview["commandText"],
            route,
            target_player=preview["targetPlayer"],
            admin_player=preview["adminPlayer"],
            mode=preview["mode"],
            exchange=preview["route"]["exchange"],
        )
    else:
        result = publish_command(
            preview["commandText"],
            route,
            target_player=preview["targetPlayer"],
            admin_player=preview["adminPlayer"],
            mode=preview["mode"],
            exchange=preview["route"]["exchange"],
            app_id="DASH-Admin-Panel",
        )
    result["dryRun"] = False
    return result


def bool_env(name, default=False):
    value = os.environ.get(name, "true" if default else "false").lower()
    return value in ("1", "true", "yes", "on")


def player_disconnect_command_name():
    command = os.environ.get("DUNE_PLAYER_DISCONNECT_COMMAND", "RemoveSessionMember").strip()
    allowed = {"RemoveSessionMember", "KickLobbyMember"}
    if bool_env("DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE", False):
        allowed.add("BattlEyeMegaKick")
    if command not in allowed:
        raise ValueError(f"DUNE_PLAYER_DISCONNECT_COMMAND must be one of: {', '.join(sorted(allowed))}")
    return command


def maintenance_player_disconnect_enabled():
    return GM_COMMANDS_ENABLED and GM_COMMAND_PAYLOAD_VERIFIED and bool_env("DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT", False)


def online_players_for_restart(job):
    broad_targets = {"all", "core", "service-layer", "game-all"}
    services = set(job.get("services") or [])
    rows = query("""
        select ps.account_id, ps.character_name, ps.server_id, fs.map
        from dune.player_state ps
        left join dune.farm_state fs on fs.server_id = ps.server_id
        where ps.online_status::text = 'Online'
          and ps.character_name is not null
          and ps.server_id is not null
        order by ps.character_name
    """)
    if not services or job.get("target") in broad_targets:
        return rows
    return [
        row for row in rows
        if not row.get("map") or map_name_to_service(row.get("map")) in services
    ]


def map_name_to_service(map_name):
    normalized = str(map_name or "").strip().lower().replace("_", "-")
    aliases = {
        "haggabasin": "survival",
        "survival": "survival",
        "overmap": "overmap",
        "arrakeen": "arrakeen",
        "harko-village": "harko-village",
        "deep-desert": "deep-desert",
    }
    return aliases.get(normalized, normalized)


def disconnect_player_for_restart(player):
    command = player_disconnect_command_name()
    character_name = str(player.get("character_name") or "").strip()
    route = str(player.get("server_id") or "").strip()
    if not character_name or not route:
        return {"ok": False, "player": character_name, "route": route, "error": "missing character name or route"}
    command_text = f"{command} {character_name}"
    if os.environ.get("DUNE_GM_COMMAND_TRANSPORT", "amqp") == "management":
        result = publish_command_management(command_text, route, target_player=character_name, admin_player="DASH")
    else:
        result = publish_command(command_text, route, target_player=character_name, admin_player="DASH", app_id="DASH-Maintenance")
    return {
        "ok": bool(result.get("ok")),
        "player": character_name,
        "route": route,
        "map": player.get("map"),
        "commandText": command_text,
        "correlationId": result.get("correlationId"),
        "transport": result.get("transport"),
    }


def soft_disconnect_online_players(job):
    players = online_players_for_restart(job)
    result = {
        "ok": True,
        "enabled": maintenance_player_disconnect_enabled(),
        "waitSeconds": RESTART_DISCONNECT_WAIT_SECONDS,
        "players": [{"characterName": row.get("character_name"), "serverId": row.get("server_id"), "map": row.get("map")} for row in players],
        "sent": [],
        "errors": [],
    }
    if not players:
        result["skipped"] = "no online players in restart target"
        return result
    if not result["enabled"]:
        result["ok"] = False
        result["error"] = "online players are present, but targeted disconnect is gated; set DUNE_ADMIN_GM_COMMANDS_ENABLED=true, DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true, and DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=true"
        return result
    max_workers = max(1, min(16, len(players)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(disconnect_player_for_restart, player): player for player in players}
        for future in concurrent.futures.as_completed(future_map):
            player = future_map[future]
            try:
                sent = future.result()
            except Exception as exc:
                sent = {"ok": False, "player": player.get("character_name"), "route": player.get("server_id"), "error": str(exc)}
            if sent.get("ok"):
                result["sent"].append(sent)
            else:
                result["errors"].append(sent)
    if result["errors"]:
        result["ok"] = False
        result["error"] = "one or more soft disconnect publishes failed"
        return result
    time.sleep(max(0, RESTART_DISCONNECT_WAIT_SECONDS))
    result["waited"] = True
    return result


def read_director_transfer_settings():
    values = {key: meta["default"] for key, meta in DIRECTOR_TRANSFER_SETTINGS.items()}
    path = ALLOWED_CONFIGS["director.ini"]
    if not path.exists():
        return values
    in_battlegroup = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            in_battlegroup = line.strip("[]").strip().lower() == "battlegroup"
            continue
        if not in_battlegroup or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if key in DIRECTOR_TRANSFER_SETTINGS:
            text = strip_ini_comment(value)
            if DIRECTOR_TRANSFER_SETTINGS[key]["type"] == "ruleset":
                text = DIRECTOR_TRANSFER_RULESET_VALUES.get(text, text)
            values[key] = text
    return values


def validate_director_transfer_settings(updates):
    validated = {}
    for key, value in updates.items():
        if key not in DIRECTOR_TRANSFER_SETTINGS:
            continue
        meta = DIRECTOR_TRANSFER_SETTINGS[key]
        text = str(value).strip()
        if meta["type"] == "bool":
            lowered = text.lower()
            if lowered not in ("true", "false"):
                raise ValueError(f"{key} must be true or false")
            validated[key] = lowered
        elif meta["type"] == "int":
            try:
                number = int(text)
            except ValueError as exc:
                raise ValueError(f"{key} must be an integer") from exc
            if number < 0:
                raise ValueError(f"{key} must be >= 0")
            validated[key] = str(number)
        elif meta["type"] == "ruleset":
            text = DIRECTOR_TRANSFER_RULESET_VALUES.get(text, text)
            if text not in DIRECTOR_TRANSFER_RULESETS:
                labels = ", ".join(f"{value}={DIRECTOR_TRANSFER_RULESET_LABELS[value]}" for value in DIRECTOR_TRANSFER_RULESETS)
                raise ValueError(f"{key} must be one of: {labels}")
            validated[key] = text
    return validated


def write_director_transfer_settings(updates):
    path = ALLOWED_CONFIGS["director.ini"]
    values = read_director_transfer_settings()
    values.update(validate_director_transfer_settings(updates))
    original = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    rendered = []
    seen = set()
    in_battlegroup = False
    inserted = False

    def append_missing():
        nonlocal inserted
        if inserted:
            return
        for key in DIRECTOR_TRANSFER_SETTINGS:
            if key in seen:
                continue
            rendered.append(f"{key}={values.get(key, DIRECTOR_TRANSFER_SETTINGS[key]['default'])}")
            seen.add(key)
        inserted = True

    for raw_line in original:
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_battlegroup:
                append_missing()
            in_battlegroup = stripped.strip("[]").strip().lower() == "battlegroup"
            rendered.append(raw_line)
            continue
        if in_battlegroup and "=" in raw_line:
            key, _ = raw_line.split("=", 1)
            key = key.strip()
            if key in DIRECTOR_TRANSFER_SETTINGS:
                rendered.append(f"{key}={values.get(key, DIRECTOR_TRANSFER_SETTINGS[key]['default'])}")
                seen.add(key)
                continue
        rendered.append(raw_line)

    if not original:
        rendered.extend(["[ Battlegroup ]"])
        in_battlegroup = True
    if in_battlegroup:
        append_missing()
    elif not inserted:
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append("[ Battlegroup ]")
        append_missing()

    backup_file(path)
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def read_player_online_state_settings():
    values = {key: meta["default"] for key, meta in PLAYER_ONLINE_STATE_SETTINGS.items()}
    path = ALLOWED_CONFIGS["UserGame.ini"]
    if not path.exists():
        return values
    in_section = False
    target_header = f"[{PLAYER_ONLINE_STATE_SECTION}]".lower()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line.lower() == target_header
            continue
        if not in_section or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if key in PLAYER_ONLINE_STATE_SETTINGS:
            values[key] = strip_ini_comment(value)
    return values


def validate_player_online_state_settings(updates):
    validated = {}
    for key, value in updates.items():
        if key not in PLAYER_ONLINE_STATE_SETTINGS:
            continue
        try:
            number = int(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if number < 0:
            raise ValueError(f"{key} must be >= 0")
        if number > 86400:
            raise ValueError(f"{key} must be <= 86400")
        validated[key] = str(number)
    return validated


def write_player_online_state_settings(updates):
    path = ALLOWED_CONFIGS["UserGame.ini"]
    values = read_player_online_state_settings()
    values.update(validate_player_online_state_settings(updates))
    original = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    rendered = []
    seen = set()
    in_section = False
    inserted = False
    target_header = f"[{PLAYER_ONLINE_STATE_SECTION}]".lower()

    def append_missing():
        nonlocal inserted
        if inserted:
            return
        for key in PLAYER_ONLINE_STATE_SETTINGS:
            if key in seen:
                continue
            rendered.append(f"{key}={values.get(key, PLAYER_ONLINE_STATE_SETTINGS[key]['default'])}")
            seen.add(key)
        inserted = True

    for raw_line in original:
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section:
                append_missing()
            in_section = stripped.lower() == target_header
            rendered.append(raw_line)
            continue
        if in_section and "=" in raw_line:
            key, _ = raw_line.split("=", 1)
            key = key.strip()
            if key in PLAYER_ONLINE_STATE_SETTINGS:
                rendered.append(f"{key}={values.get(key, PLAYER_ONLINE_STATE_SETTINGS[key]['default'])}")
                seen.add(key)
                continue
        rendered.append(raw_line)

    if not original:
        rendered.append(f"[{PLAYER_ONLINE_STATE_SECTION}]")
        in_section = True
    if in_section:
        append_missing()
    elif not inserted:
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append(f"[{PLAYER_ONLINE_STATE_SECTION}]")
        append_missing()

    backup_file(path)
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def parse_body(handler):
    length = validate_body_framing(handler)
    data = handler.rfile.read(length) if length else b"{}"
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        body = json.loads(data.decode("utf-8") or "{}")
        if not isinstance(body, dict):
            raise ValueError("JSON request body must be an object")
        return body
    parsed = urllib.parse.parse_qs(data.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def validate_body_framing(handler):
    if handler.headers.get("Transfer-Encoding"):
        raise ValueError("transfer-encoding is not supported")
    content_lengths = handler.headers.get_all("Content-Length", [])
    if len(content_lengths) > 1:
        raise ValueError("multiple content-length headers are not supported")
    try:
        length = int(content_lengths[0]) if content_lengths else 0
    except ValueError as exc:
        raise ValueError("invalid content-length") from exc
    if length < 0:
        raise ValueError("invalid content-length")
    if length > MAX_BODY_BYTES:
        raise ValueError("request body too large")
    return length


def validate_json_post(handler):
    length = validate_body_framing(handler)
    content_type = handler.headers.get("Content-Type", "")
    if content_type and "application/json" not in content_type.lower():
        raise ValueError("POST requests must use application/json")
    if length and not content_type:
        raise ValueError("POST requests must use application/json")
    return length


def require_confirmation(body, phrase):
    if str(body.get("confirm", "")).strip() != phrase:
        raise PermissionError(f"confirmation required: {phrase}")


def query(sql, params=None):
    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params or ())
            if cursor.description:
                return list(cursor.fetchall())
            return []


def execute(sql, params=None):
    with db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.rowcount


def character_swap_takeover(active_account_id, target_account_id, active_user, target_user):
    with db_connect() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                lock_a, lock_b = sorted([int(active_account_id), int(target_account_id)])
                cursor.execute("select pg_advisory_xact_lock(%s), pg_advisory_xact_lock(%s)", (lock_a, lock_b))
                cursor.execute("""
                    select eps.account_id,
                           dune.decrypt_user_data(eps.encrypted_character_name) as character_name,
                           eps.online_status::text, eps.life_state::text,
                           eps.server_id, eps.player_controller_id, eps.player_pawn_id, eps.player_state_id,
                           ea."user" as fls_id,
                           dune.decrypt_user_data(ea.encrypted_funcom_id) as funcom_id,
                           ea.platform_name, ea.platform_id
                    from dune.encrypted_player_state eps
                    join dune.encrypted_accounts ea on ea.id=eps.account_id
                    where eps.account_id in (%s, %s)
                    order by eps.account_id
                    for update of eps, ea
                """, (active_account_id, target_account_id))
                before_rows = list(cursor.fetchall())
                if len(before_rows) != 2:
                    raise RuntimeError("character swap aborted because active/target rows could not both be locked")
                online_now = [
                    row for row in before_rows
                    if str(row.get("online_status") or "").lower() == "online"
                ]
                if online_now:
                    raise RuntimeError("character swap aborted after backup because active or target account came online")
                before_by_account = {int(row.get("account_id")): row for row in before_rows}
                active_before = before_by_account.get(int(active_account_id), {})
                target_before = before_by_account.get(int(target_account_id), {})
                if active_before.get("fls_id") != active_user or target_before.get("fls_id") != target_user:
                    raise RuntimeError("character swap aborted because active/target FLS identities changed after planning")
                cursor.execute("select dune.takeover_account(%s, %s)", (target_user, active_user))
                cursor.execute("""
                    select eps.account_id,
                           dune.decrypt_user_data(eps.encrypted_character_name) as character_name,
                           eps.online_status::text, eps.life_state::text,
                           eps.server_id, eps.player_controller_id, eps.player_pawn_id, eps.player_state_id,
                           ea."user" as fls_id,
                           dune.decrypt_user_data(ea.encrypted_funcom_id) as funcom_id,
                           ea.platform_name, ea.platform_id
                    from dune.encrypted_player_state eps
                    join dune.encrypted_accounts ea on ea.id=eps.account_id
                    where eps.account_id in (%s, %s)
                    order by eps.account_id
                """, (active_account_id, target_account_id))
                after_rows = list(cursor.fetchall())
                after_by_account = {int(row.get("account_id")): row for row in after_rows}
                active_after = after_by_account.get(int(active_account_id), {})
                target_after = after_by_account.get(int(target_account_id), {})
                verified = (
                    active_after.get("fls_id") == target_user
                    and target_after.get("fls_id") == active_user
                )
                if not verified:
                    raise RuntimeError("character swap native call returned but post-swap identity verification failed")
            conn.commit()
            return before_rows, after_rows, verified
        except Exception:
            conn.rollback()
            raise


def reference_query(errors, name, sql, params=None):
    try:
        return query(sql, params)
    except Exception as exc:
        errors[name] = str(exc)
        return []


def read_steam_profile_cache():
    try:
        data = json.loads(STEAM_PROFILE_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_steam_profile_cache(cache):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STEAM_PROFILE_CACHE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STEAM_PROFILE_CACHE_FILE)


def fetch_steam_persona_name(steam_id):
    url = f"https://steamcommunity.com/profiles/{urllib.parse.quote(str(steam_id), safe='')}/?xml=1"
    request = urllib.request.Request(url, headers={"User-Agent": "DASH-Admin/1.0"})
    with urllib.request.urlopen(request, timeout=1.5) as response:
        text = response.read(32768).decode("utf-8", "replace")
    match = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", text, re.S)
    if match:
        return html.unescape(match.group(1).strip())
    match = re.search(r"<steamID>(.*?)</steamID>", text, re.S)
    return html.unescape(match.group(1).strip()) if match else ""


def steam_cache_entry_expired(cache, steam_id, now):
    try:
        fetched_at = float((cache.get(steam_id) or {}).get("fetchedAt") or 0)
    except (TypeError, ValueError):
        return True
    return now - fetched_at > STEAM_PROFILE_CACHE_TTL_SECONDS


def annotate_steam_profile_rows(rows, cache=None):
    cache = cache or {}
    for row in rows:
        steam_id = str(row.get("platform_id") or "").strip()
        if str(row.get("platform_name") or "").lower() == "steam" and steam_id:
            row["steam_profile_url"] = f"https://steamcommunity.com/profiles/{steam_id}"
            row["steam_persona_name"] = (cache.get(steam_id) or {}).get("personaName", "")
            row["steam_persona_lookup_enabled"] = STEAM_PROFILE_LOOKUP_ENABLED
    return rows


def enrich_steam_profiles(rows):
    steam_ids = sorted({
        str(row.get("platform_id") or "").strip()
        for row in rows
        if str(row.get("platform_name") or "").lower() == "steam" and str(row.get("platform_id") or "").strip().isdigit()
    })
    if not steam_ids:
        return rows
    if not STEAM_PROFILE_LOOKUP_ENABLED:
        return annotate_steam_profile_rows(rows)
    with STEAM_PROFILE_CACHE_LOCK:
        now = time.time()
        cache = read_steam_profile_cache()
        changed = False
        missing = [steam_id for steam_id in steam_ids if steam_cache_entry_expired(cache, steam_id, now)]
        if missing:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(missing))) as executor:
                future_map = {executor.submit(fetch_steam_persona_name, steam_id): steam_id for steam_id in missing}
                for future in concurrent.futures.as_completed(future_map):
                    steam_id = future_map[future]
                    try:
                        persona = future.result()
                        cache[steam_id] = {"personaName": persona, "fetchedAt": now, "ok": bool(persona)}
                    except Exception as exc:
                        previous = cache.get(steam_id) or {}
                        cache[steam_id] = {
                            "personaName": previous.get("personaName", ""),
                            "fetchedAt": now,
                            "ok": False,
                            "error": str(exc)[:160],
                        }
                    changed = True
        if changed:
            try:
                write_steam_profile_cache(cache)
            except OSError:
                pass
        return annotate_steam_profile_rows(rows, cache)


def read_hagga_pois():
    empty = {"source": {}, "crs": {"topLeft": [0, 0], "bottomRight": [100000, 100000], "order": "xy"}, "groups": {}, "markers": []}
    path = STATIC_ROOT / "hagga-pois.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty
    if not isinstance(data, dict):
        return empty
    data.setdefault("source", {})
    data.setdefault("crs", empty["crs"])
    data.setdefault("groups", {})
    data.setdefault("markers", [])
    return data


def create_db_backup():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    suffix = secrets.token_urlsafe(6)
    path = BACKUP_ROOT / f"{stamp}-{suffix}-{DATABASE}.dump"
    temp_path = BACKUP_ROOT / f".{stamp}-{suffix}-{DATABASE}.dump.tmp"
    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ.get("DUNE_ADMIN_DB_PASSWORD", os.environ.get("POSTGRES_DUNE_PASSWORD", ""))
    cmd = [
        "pg_dump",
        "-h", os.environ.get("DUNE_ADMIN_DB_HOST", "postgres"),
        "-p", os.environ.get("DUNE_ADMIN_DB_PORT", "5432"),
        "-U", os.environ.get("DUNE_ADMIN_DB_USER", "dune"),
        "-d", DATABASE,
        "-Fc",
        "-f", str(temp_path),
    ]
    try:
        subprocess.run(cmd, check=True, env=env, capture_output=True, text=True, timeout=120)
        temp_path.rename(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return {"path": str(path), "bytes": path.stat().st_size}


def add_tree_archive(archive_path, entries):
    added = []
    skipped = []
    with tarfile.open(archive_path, "w:gz") as archive:
        for source, arcname in entries:
            source = pathlib.Path(source)
            if not source.exists():
                skipped.append({"path": str(source), "reason": "missing"})
                continue
            try:
                archive.add(source, arcname=arcname)
                added.append({"path": str(source), "archiveName": arcname})
            except (OSError, tarfile.TarError) as exc:
                skipped.append({"path": str(source), "reason": str(exc)})
    return {"path": str(archive_path), "bytes": archive_path.stat().st_size, "added": added, "skipped": skipped}


def create_postgres_layers_report(backup_dir):
    report = {
        "streamingReplication": {"checked": False, "slots": [], "senders": [], "error": None},
        "remoteReplicaSnapshot": {"configured": False, "attempted": False, "ok": None, "output": "", "error": None},
    }
    try:
        report["streamingReplication"]["slots"] = query("""
            select slot_name, slot_type, active, restart_lsn::text, confirmed_flush_lsn::text,
                   wal_status, safe_wal_size
            from pg_replication_slots
            order by slot_name
        """)
        report["streamingReplication"]["senders"] = query("""
            select application_name, client_addr::text, state, sync_state,
                   write_lag::text, flush_lag::text, replay_lag::text
            from pg_stat_replication
            order by application_name, client_addr::text
        """)
        report["streamingReplication"]["checked"] = True
    except Exception as exc:
        report["streamingReplication"]["error"] = str(exc)

    remote = os.environ.get("POSTGRES_REMOTE_REPLICA_HOST", "").strip()
    remote_root = os.environ.get("POSTGRES_REMOTE_REPLICA_ROOT", "/srv/dune-postgres-replica").strip()
    report["remoteReplicaSnapshot"]["configured"] = bool(remote)
    if remote and MAINTENANCE_REPLICA_SNAPSHOT_ENABLED:
        command = ROOT / "scripts" / "replica-snapshot.sh"
        report["remoteReplicaSnapshot"]["attempted"] = True
        if not command.exists() or not os.access(command, os.X_OK):
            report["remoteReplicaSnapshot"]["ok"] = False
            report["remoteReplicaSnapshot"]["error"] = f"replica snapshot command is not executable: {command}"
        else:
            try:
                result = subprocess.run(
                    [str(command), str(ENV_FILE), remote, remote_root],
                    cwd=str(ROOT),
                    env=os.environ.copy(),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=MAINTENANCE_REPLICA_SNAPSHOT_TIMEOUT_SECONDS,
                    check=False,
                )
                output = (result.stdout + result.stderr).strip()
                if len(output) > AUDIT_FIELD_LIMIT:
                    output = output[:AUDIT_FIELD_LIMIT] + "...[truncated]"
                report["remoteReplicaSnapshot"]["ok"] = result.returncode == 0
                report["remoteReplicaSnapshot"]["output"] = output
                if result.returncode != 0:
                    report["remoteReplicaSnapshot"]["error"] = f"replica snapshot exited {result.returncode}"
            except Exception as exc:
                report["remoteReplicaSnapshot"]["ok"] = False
                report["remoteReplicaSnapshot"]["error"] = str(exc)

    status_path = backup_dir / "postgres-layers.json"
    status_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    return {"path": str(status_path), "bytes": status_path.stat().st_size, "report": report}


def create_maintenance_backup(job):
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    job_id = str(job.get("id", "manual"))[:24]
    backup_dir = BACKUP_ROOT / "maintenance" / f"{stamp}-{job_id}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    result = {
        "path": str(backup_dir),
        "createdAt": time.time(),
        "jobId": job.get("id"),
        "action": job.get("action", "restart"),
        "target": job.get("target"),
        "services": job.get("services", []),
        "artifacts": {},
        "warnings": [],
    }

    try:
        db_result = create_db_backup()
        db_path = pathlib.Path(db_result["path"])
        target = backup_dir / db_path.name
        shutil.move(str(db_path), target)
        result["artifacts"]["postgres"] = {"path": str(target), "bytes": target.stat().st_size}
    except Exception as exc:
        result["warnings"].append({"artifact": "postgres", "error": str(exc)})
        raise RuntimeError(f"maintenance database backup failed: {exc}") from exc

    try:
        result["artifacts"]["postgresLayers"] = create_postgres_layers_report(backup_dir)
        layers = result["artifacts"]["postgresLayers"]["report"]
        if layers["streamingReplication"].get("error"):
            result["warnings"].append({"artifact": "postgresLayers.streamingReplication", "error": layers["streamingReplication"]["error"]})
        snapshot = layers["remoteReplicaSnapshot"]
        if snapshot.get("configured") and snapshot.get("attempted") and not snapshot.get("ok"):
            result["warnings"].append({"artifact": "postgresLayers.remoteReplicaSnapshot", "error": snapshot.get("error") or "remote snapshot failed"})
    except Exception as exc:
        result["warnings"].append({"artifact": "postgresLayers", "error": str(exc)})

    archive_entries = [(CONFIG_ROOT, "config")]
    if ENV_FILE.exists():
        archive_entries.append((ENV_FILE, ".env"))
    result["artifacts"]["config"] = add_tree_archive(backup_dir / "config-and-env.tgz", archive_entries)

    data_root = ROOT / "data"
    server_saved = data_root / "server-saved"
    rabbitmq = data_root / "rabbitmq"
    if server_saved.exists():
        result["artifacts"]["serverSaved"] = add_tree_archive(backup_dir / "server-saved.tgz", [(server_saved, "server-saved")])
    else:
        result["warnings"].append({"artifact": "serverSaved", "error": f"{server_saved} is not mounted"})
    if rabbitmq.exists():
        result["artifacts"]["rabbitmq"] = add_tree_archive(backup_dir / "rabbitmq.tgz", [(rabbitmq, "rabbitmq")])
    else:
        result["warnings"].append({"artifact": "rabbitmq", "error": f"{rabbitmq} is not mounted"})

    manifest = backup_dir / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    result["artifacts"]["manifest"] = {"path": str(manifest), "bytes": manifest.stat().st_size}
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "dune-admin-panel"
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ConnectionError:
            return
        except Exception as exc:
            try:
                self.error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception:
                pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.validate_host()
            if self.is_app_route(parsed.path):
                self.html(INDEX)
            elif parsed.path == "/static/hagga-basin.webp":
                self.static_file(STATIC_ROOT / "hagga-basin.webp", "image/webp")
            elif parsed.path == "/static/hagga-basin-south.webp":
                self.static_file(STATIC_ROOT / "hagga-basin-south.webp", "image/webp")
            elif parsed.path == "/api/status":
                self.json({
                    "build": ADMIN_PANEL_BUILD,
                    "database": DATABASE,
                    "mutationsEnabled": MUTATIONS_ENABLED,
                    "itemGrantsEnabled": ITEM_GRANTS_ENABLED,
                    "adminTokenConfigured": bool(ADMIN_TOKEN),
                    "adminTokenRequired": os.environ.get("DUNE_ADMIN_REQUIRE_TOKEN", "false").lower() in ("1", "true", "yes", "on"),
                    "safeEnvKeys": sorted(SAFE_ENV_KEYS),
                    "configs": sorted(ALLOWED_CONFIGS),
                })
            elif parsed.path == "/api/server/state":
                self.require_token()
                self.json({
                    "farmState": query("select server_id,farm_id,ready,alive,map,revision,game_addr,igw_addr from dune.farm_state order by map, server_id"),
                    "partitions": query("select partition_id,server_id,map,dimension_index,label from dune.world_partition order by partition_id"),
                    "activeServers": query("select * from dune.active_server_ids order by server_id"),
                })
            elif parsed.path == "/api/ops/health":
                self.require_token()
                self.json(self.ops_health())
            elif parsed.path == "/api/ops/network":
                self.require_token()
                self.json(self.network_health())
            elif parsed.path == "/api/ops/security":
                self.require_token()
                self.json(self.security_audit())
            elif parsed.path == "/api/ops/audit":
                self.require_token()
                self.json({"events": recent_audit_events()})
            elif parsed.path == "/api/ops/optimization":
                self.require_token()
                self.json(self.optimization_signals())
            elif parsed.path == "/api/ops/resources":
                self.require_token()
                params = urllib.parse.parse_qs(parsed.query)
                self.json(self.resource_snapshot(live_stats=(params.get("live") or ["0"])[0] == "1"))
            elif parsed.path == "/api/ops/runbook":
                self.require_token()
                self.json(self.ops_runbook())
            elif parsed.path == "/api/ops/announcement":
                self.require_token()
                with ANNOUNCEMENT_LOCK:
                    self.json(read_announcement_state())
            elif parsed.path == "/api/ops/restart":
                self.require_token()
                with RESTART_LOCK:
                    self.json(read_restart_state())
            elif parsed.path == "/api/admin/digests":
                self.require_token()
                self.json(read_admin_digest_state())
            elif parsed.path == "/api/characters":
                self.require_token()
                params = urllib.parse.parse_qs(parsed.query)
                term = (params.get("q", [""])[0] or "").strip()
                self.json(self.characters(term))
            elif parsed.path == "/api/characters/roster":
                self.require_token()
                self.json(self.character_roster())
            elif parsed.path == "/api/admin/character-slots":
                self.require_token()
                params = urllib.parse.parse_qs(parsed.query)
                account_id = (params.get("account_id") or params.get("accountId") or [""])[0]
                self.json(self.character_slots(account_id))
            elif parsed.path == "/api/players/hagga-basin":
                self.require_token()
                self.json(self.hagga_basin_players())
            elif parsed.path == "/api/markers/hagga-basin":
                self.require_token()
                self.json(read_hagga_pois())
            elif parsed.path.startswith("/api/characters/"):
                self.require_token()
                account_id = int(parsed.path.rsplit("/", 1)[-1])
                self.json(self.character_detail(account_id))
            elif parsed.path == "/api/settings/env":
                self.require_token()
                env_values = read_env()
                values = {}
                configured = {}
                for key in sorted(SAFE_ENV_KEYS):
                    current = env_values.get(key, "")
                    is_secret = bool(ENV_KEY_DEFINITIONS.get(key, {}).get("secret"))
                    values[key] = "" if is_secret else current
                    configured[key] = bool(current)
                self.json({
                    "values": values,
                    "configured": configured,
                    "definitions": ENV_KEY_DEFINITIONS,
                })
            elif parsed.path == "/api/settings/configs":
                self.require_token()
                self.json({name: path.read_text(encoding="utf-8") for name, path in ALLOWED_CONFIGS.items() if path.exists()})
            elif parsed.path == "/api/settings/director-transfer":
                self.require_token()
                self.json({
                    "values": read_director_transfer_settings(),
                    "definitions": DIRECTOR_TRANSFER_SETTINGS,
                    "rulesets": DIRECTOR_TRANSFER_RULESETS,
                    "rulesetLabels": DIRECTOR_TRANSFER_RULESET_LABELS,
                })
            elif parsed.path == "/api/settings/player-online-state":
                self.require_token()
                self.json({
                    "values": read_player_online_state_settings(),
                    "definitions": PLAYER_ONLINE_STATE_SETTINGS,
                    "section": PLAYER_ONLINE_STATE_SECTION,
                })
            elif parsed.path == "/api/admin/artificial-exchange":
                self.require_token()
                self.json(artificial_exchange_status())
            elif parsed.path == "/api/settings/typed-knobs":
                self.require_token()
                self.json({
                    "enabled": TYPED_KNOBS_ENABLED,
                    "values": read_typed_knobs(),
                    "confirmPhrase": CONFIRM_TYPED_KNOBS,
                })
            elif parsed.path == "/api/catalog/surfaces":
                self.require_token()
                self.require_catalog()
                params = urllib.parse.parse_qs(parsed.query)
                self.json(catalog_payload(group=(params.get("group") or [""])[0]))
            elif parsed.path == "/api/catalog/evidence":
                self.require_token()
                self.require_catalog()
                self.json(catalog_evidence_payload())
            elif parsed.path == "/api/catalog/validation":
                self.require_token()
                self.require_catalog()
                self.json(catalog_validation_payload())
            elif parsed.path == "/api/events":
                self.require_token()
                with EVENT_LOCK:
                    self.json(dict(read_event_state(), executionEnabled=EVENT_EXECUTION_ENABLED))
            elif parsed.path == "/api/admin/reference":
                self.require_token()
                self.json(self.admin_reference())
            elif parsed.path == "/api/admin/gm/reference":
                self.require_token()
                self.json(gm_command_catalog())
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")
        except PermissionError as exc:
            self.error(HTTPStatus.UNAUTHORIZED, str(exc))
        except ConnectionError:
            return
        except Exception as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.validate_host()
            if self.is_app_route(parsed.path):
                self.html(INDEX, head_only=True)
            elif parsed.path == "/static/hagga-basin.webp":
                self.static_file(STATIC_ROOT / "hagga-basin.webp", "image/webp", head_only=True)
            elif parsed.path == "/static/hagga-basin-south.webp":
                self.static_file(STATIC_ROOT / "hagga-basin-south.webp", "image/webp", head_only=True)
            elif parsed.path.startswith("/api/"):
                self.json({}, head_only=True)
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found", head_only=True)
        except PermissionError as exc:
            self.error(HTTPStatus.UNAUTHORIZED, str(exc), head_only=True)
        except ConnectionError:
            return
        except Exception as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc), head_only=True)

    def do_OPTIONS(self):
        self.validate_host()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.security_headers()
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.validate_host()
            self.validate_same_origin()
            validate_json_post(self)
            if parsed.path.startswith("/api/settings/configs/"):
                self.require_token()
                name = parsed.path.rsplit("/", 1)[-1]
                body = parse_body(self)
                self.write_config(name, body.get("content", ""))
                self.audit("config-write", config=name)
                self.json({"ok": True})
            elif parsed.path == "/api/settings/env":
                self.require_token()
                body = parse_body(self)
                updates = {key: str(body.get(key, "")) for key in SAFE_ENV_KEYS if key in body}
                write_safe_env(updates)
                self.audit("env-write", keys=sorted(updates))
                self.json({"ok": True})
            elif parsed.path == "/api/settings/director-transfer":
                self.require_token()
                body = parse_body(self)
                updates = {key: body[key] for key in DIRECTOR_TRANSFER_SETTINGS if key in body}
                write_director_transfer_settings(updates)
                self.audit("director-transfer-write", keys=sorted(updates))
                self.json({"ok": True, "values": read_director_transfer_settings()})
            elif parsed.path == "/api/settings/player-online-state":
                self.require_token()
                body = parse_body(self)
                updates = {key: body[key] for key in PLAYER_ONLINE_STATE_SETTINGS if key in body}
                write_player_online_state_settings(updates)
                self.audit("player-online-state-write", keys=sorted(updates))
                self.json({"ok": True, "values": read_player_online_state_settings()})
            elif parsed.path == "/api/admin/artificial-exchange":
                self.require_token()
                body = parse_body(self)
                action = str(body.get("action", "")).strip()
                result = artificial_exchange_action(action)
                self.audit("artificial-exchange-action", action=action, ok=result.get("ok"))
                self.json(result)
            elif parsed.path == "/api/settings/typed-knobs":
                self.require_token()
                body = parse_body(self)
                updates = body.get("updates", body)
                if not isinstance(updates, dict):
                    raise ValueError("updates must be an object")
                if str(body.get("dry_run", body.get("dryRun", "false"))).lower() in ("1", "true", "yes", "on"):
                    planned = {key: validate_typed_knob_value(key, value) for key, value in updates.items() if key in TYPED_CONFIG_KNOBS}
                    self.json({"ok": True, "dryRun": True, "planned": planned, "restartRequired": any(TYPED_CONFIG_KNOBS[k]["restart"] for k in planned)})
                else:
                    self.require_mutations()
                    self.require_typed_knobs()
                    require_confirmation(body, CONFIRM_TYPED_KNOBS)
                    result = write_typed_knobs(updates)
                    self.audit("typed-knobs-write", keys=sorted(result.get("updated", {})))
                    self.json(dict(result, values=read_typed_knobs()))
            elif parsed.path == "/api/admin/currency":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.update_currency(body)
                self.audit("currency-update", player_controller_id=body.get("player_controller_id"), currency_id=body.get("currency_id"), amount=body.get("amount"), mode=body.get("mode", "add"))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/xp":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.update_xp(body)
                self.audit("xp-update", player_id=body.get("player_id"), track_type=body.get("track_type"), amount=body.get("amount"), mode=body.get("mode", "add"))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/keystone":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                result = self.purchase_keystone(body)
                self.audit("keystone-purchase", player_id=body.get("player_id"), keystone=body.get("keystone"))
                self.json(result)
            elif parsed.path == "/api/admin/reset-keystones":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                require_confirmation(body, CONFIRM_RESET_KEYSTONES)
                self.reset_keystones(body)
                self.audit("keystone-reset", player_id=body.get("player_id"))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/unsupported":
                self.require_token()
                parse_body(self)
                self.error(HTTPStatus.NOT_IMPLEMENTED, "gear/skill grants need mapped template IDs and table contracts before writes are safe")
            elif parsed.path == "/api/admin/backup":
                self.require_token()
                parse_body(self)
                result = create_db_backup()
                self.audit("database-backup", backup_path=result.get("path"), bytes=result.get("bytes"))
                self.json(result)
            elif parsed.path == "/api/admin/item":
                self.require_token()
                body = parse_body(self)
                dry_run = str(body.get("dry_run", "")).lower() in ("1", "true", "yes", "on")
                if not dry_run:
                    self.require_mutations()
                    self.require_item_grants()
                result = self.grant_item(body)
                self.audit("item-grant", inventory_id=result.get("inventory_id"), template_id=result.get("template_id"), item_id=result.get("item_id"), stack_size=result.get("stack_size"))
                self.json(result)
            elif parsed.path == "/api/admin/item/delete":
                self.require_token()
                self.require_mutations()
                self.require_item_grants()
                body = parse_body(self)
                require_confirmation(body, CONFIRM_DELETE_ITEM)
                result = self.delete_item(body)
                self.audit("item-delete", item_id=result.get("item_id"), count=result.get("count"), deleted=result.get("deleted"))
                self.json(result)
            elif parsed.path == "/api/admin/item/stack":
                self.require_token()
                self.require_mutations()
                self.require_item_grants()
                body = parse_body(self)
                require_confirmation(body, CONFIRM_SET_STACK)
                result = self.set_item_stack(body)
                self.audit("item-stack", item_id=result.get("item_id"), stack_size=result.get("stack_size"))
                self.json(result)
            elif parsed.path == "/api/admin/bundle":
                self.require_token()
                body = parse_body(self)
                result = self.economy_bundle(body)
                self.audit("economy-bundle", ok=result.get("ok"), dry_run=result.get("dryRun"), steps=len(result.get("plan", [])))
                self.json(result)
            elif parsed.path == "/api/admin/player-recovery/offline-teleport":
                self.require_token()
                body = parse_body(self)
                result = self.offline_player_recovery(body)
                self.audit("offline-player-recovery", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), partition_id=result.get("partitionId"))
                self.json(result)
            elif parsed.path == "/api/admin/spice-fields/inspect":
                self.require_token()
                parse_body(self)
                self.json(self.spice_field_inspect())
            elif parsed.path == "/api/admin/progression/inspect":
                self.require_token()
                body = parse_body(self)
                self.json(self.progression_inspect(body))
            elif parsed.path == "/api/admin/world-state/inspect":
                self.require_token()
                body = parse_body(self)
                self.json(self.world_state_inspect(body))
            elif parsed.path == "/api/admin/economy/inspect":
                self.require_token()
                body = parse_body(self)
                self.json(self.economy_inspect(body))
            elif parsed.path == "/api/admin/player-lifecycle/inspect":
                self.require_token()
                body = parse_body(self)
                self.json(self.player_lifecycle_inspect(body))
            elif parsed.path == "/api/admin/faction-reputation":
                self.require_token()
                body = parse_body(self)
                result = self.faction_reputation_mutation(body)
                self.audit("faction-reputation", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), actor_id=result.get("actorId"), faction_id=result.get("factionId"), mode=result.get("mode"))
                self.json(result)
            elif parsed.path == "/api/admin/journey":
                self.require_token()
                body = parse_body(self)
                result = self.journey_mutation(body)
                self.audit("journey-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), journey_action=result.get("action"), story_node_count=len(result.get("storyNodeIds", [])))
                self.json(result)
            elif parsed.path == "/api/admin/faction":
                self.require_token()
                body = parse_body(self)
                result = self.faction_change_mutation(body)
                self.audit("faction-change", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), actor_id=result.get("actorId"), faction_id=result.get("factionId"))
                self.json(result)
            elif parsed.path == "/api/admin/respawn-location":
                self.require_token()
                body = parse_body(self)
                result = self.respawn_location_mutation(body)
                self.audit("respawn-location", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), respawn_id=result.get("respawnId"), respawn_action=result.get("action"))
                self.json(result)
            elif parsed.path == "/api/admin/landsraad":
                self.require_token()
                body = parse_body(self)
                result = self.landsraad_mutation(body)
                self.audit("landsraad-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), landsraad_action=result.get("action"), term_id=result.get("termId"))
                self.json(result)
            elif parsed.path == "/api/admin/guild":
                self.require_token()
                body = parse_body(self)
                result = self.guild_mutation(body)
                self.audit("guild-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), guild_action=result.get("action"), guild_id=result.get("guildId"), player_id=result.get("playerId"))
                self.json(result)
            elif parsed.path == "/api/admin/marker":
                self.require_token()
                body = parse_body(self)
                result = self.marker_mutation(body)
                self.audit("marker-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), marker_action=result.get("action"), marker_count=result.get("markerCount"), key_count=result.get("keyCount"))
                self.json(result)
            elif parsed.path == "/api/admin/landclaim":
                self.require_token()
                body = parse_body(self)
                result = self.landclaim_mutation(body)
                self.audit("landclaim-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), totem_id=result.get("totemId"), grid_x=result.get("gridX"), grid_y=result.get("gridY"))
                self.json(result)
            elif parsed.path == "/api/admin/exchange":
                self.require_token()
                body = parse_body(self)
                result = self.exchange_mutation(body)
                self.audit("exchange-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), owner_id=result.get("ownerId"), controller_id=result.get("controllerId"), mode=result.get("mode"))
                self.json(result)
            elif parsed.path == "/api/admin/player-tags":
                self.require_token()
                body = parse_body(self)
                result = self.player_tags_mutation(body)
                self.audit("player-tags-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"))
                self.json(result)
            elif parsed.path == "/api/admin/access-code":
                self.require_token()
                body = parse_body(self)
                result = self.access_code_mutation(body)
                self.audit("access-code-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), access_code_action=result.get("action"))
                self.json(result)
            elif parsed.path == "/api/admin/communinet":
                self.require_token()
                body = parse_body(self)
                result = self.communinet_mutation(body)
                self.audit("communinet-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), communinet_action=result.get("action"))
                self.json(result)
            elif parsed.path == "/api/admin/tutorial":
                self.require_token()
                body = parse_body(self)
                result = self.tutorial_mutation(body)
                self.audit("tutorial-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), player_id=result.get("playerId"), tutorial_id=result.get("tutorialId"))
                self.json(result)
            elif parsed.path == "/api/admin/permission":
                self.require_token()
                body = parse_body(self)
                result = self.permission_mutation(body)
                self.audit("permission-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), permission_action=result.get("action"), actor_id=result.get("actorId"), player_id=result.get("playerId"))
                self.json(result)
            elif parsed.path == "/api/admin/vendor":
                self.require_token()
                body = parse_body(self)
                result = self.vendor_mutation(body)
                self.audit("vendor-mutation", ok=result.get("ok"), dry_run=result.get("dryRun"), vendor_id=result.get("vendorId"), player_id=result.get("playerId"))
                self.json(result)
            elif parsed.path == "/api/admin/character-slots/plan":
                self.require_token()
                body = parse_body(self)
                result = self.character_slot_plan(body)
                self.audit("character-slot-plan", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), slot_action=result.get("action"), executable=result.get("executable"))
                self.json(result)
            elif parsed.path == "/api/admin/character-slots/execute":
                self.require_token()
                body = parse_body(self)
                result = self.character_slot_execute(body)
                self.audit("character-slot-execute", ok=result.get("ok"), dry_run=result.get("dryRun"), account_id=result.get("accountId"), slot_action=result.get("action"), executable=result.get("executable"))
                self.json(result)
            elif parsed.path == "/api/admin/gm/preview":
                self.require_token()
                body = parse_body(self)
                result = gm_payload_preview(body)
                self.audit("gm-command-preview", command=body.get("command"), route=body.get("route"), target_player=body.get("target_player"))
                self.json(result)
            elif parsed.path == "/api/admin/gm/execute":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                require_confirmation(body, CONFIRM_GM_COMMAND)
                if not GM_COMMANDS_ENABLED:
                    raise PermissionError("GM commands are disabled; set DUNE_ADMIN_GM_COMMANDS_ENABLED=true")
                if not GM_COMMAND_PAYLOAD_VERIFIED:
                    raise PermissionError("GM command route is not verified yet; execution is intentionally blocked")
                result = gm_payload_execute(body)
                self.audit("gm-command-execute", command=body.get("command"), route=body.get("route"), target_player=body.get("target_player"), correlation_id=result.get("correlationId"))
                self.json(result)
            elif parsed.path == "/api/ops/announcement":
                self.require_token()
                body = parse_body(self)
                result = schedule_announcement(body)
                self.audit("announcement-schedule", job_id=result.get("id"), delay=result.get("delay"), repeat_seconds=result.get("repeatSeconds"))
                self.json({"ok": True, "job": result})
            elif parsed.path == "/api/ops/announcement/cancel":
                self.require_token()
                body = parse_body(self)
                result = cancel_announcement(body.get("id"))
                self.audit("announcement-cancel", job_id=body.get("id"), cancelled=result.get("cancelled"))
                self.json(result)
            elif parsed.path == "/api/ops/restart":
                self.require_token()
                body = parse_body(self)
                result = schedule_restart(body)
                self.audit("restart-schedule", job_id=result.get("id"), target=result.get("target"), delay=result.get("delay"), execute=result.get("execute"))
                self.json({"ok": True, "job": result})
            elif parsed.path == "/api/ops/restart/cancel":
                self.require_token()
                body = parse_body(self)
                result = cancel_restart(body.get("id"))
                self.audit("restart-cancel", job_id=body.get("id"), cancelled=result.get("cancelled"))
                self.json(result)
            elif parsed.path == "/api/events/dry-run":
                self.require_token()
                body = parse_body(self)
                result = event_dry_run(body)
                self.audit("event-dry-run", event_id=result.get("event", {}).get("id"), actions=len(result.get("event", {}).get("plan", [])))
                self.json(result)
            elif parsed.path == "/api/events":
                self.require_token()
                body = parse_body(self)
                event = create_event(body)
                self.audit("event-create", event_id=event.get("id"), actions=len(event.get("plan", [])))
                self.json({"ok": True, "event": event})
            elif parsed.path == "/api/events/cancel":
                self.require_token()
                body = parse_body(self)
                result = cancel_event(str(body.get("id", "")))
                self.audit("event-cancel", event_id=body.get("id"), cancelled=result.get("cancelled"))
                self.json(result)
            elif parsed.path == "/api/events/run":
                self.require_token()
                body = parse_body(self)
                result = execute_event(str(body.get("id", "")))
                self.json(result)
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")
        except PermissionError as exc:
            self.audit("post-rejected", ok=False, error=str(exc))
            self.error(HTTPStatus.UNAUTHORIZED, str(exc))
        except NotImplementedError as exc:
            self.audit("post-not-implemented", ok=False, error=str(exc))
            self.error(HTTPStatus.NOT_IMPLEMENTED, str(exc))
        except ConnectionError:
            return
        except Exception as exc:
            self.audit("post-failed", ok=False, error=str(exc))
            self.error(HTTPStatus.BAD_REQUEST, str(exc))

    def characters(self, term):
        like = f"%{term}%"
        sql = """
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, ps.player_controller_id, ps.player_pawn_id, ps.player_state_id,
                   ps.last_login_time, a.funcom_id, a.platform_name, a.platform_id
            from dune.player_state ps
            left join dune.accounts a on a.id = ps.account_id
            where (%s = '' or ps.character_name ilike %s or a.funcom_id ilike %s or a.platform_id ilike %s)
            order by ps.last_login_time desc nulls last, ps.account_id
            limit %s
        """
        return enrich_steam_profiles([dict(row) for row in query(sql, (term, like, like, like, CHARACTER_SEARCH_LIMIT))])

    def character_roster(self):
        sql = """
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, fs.map, fs.game_addr, fs.game_port,
                   ps.player_controller_id, ps.player_pawn_id,
                   ps.last_login_time, ps.logoff_persistence_end_time, ps.reconnect_grace_period_end,
                   a.funcom_id, a.platform_name, a.platform_id
            from dune.player_state ps
            left join dune.accounts a on a.id = ps.account_id
            left join dune.farm_state fs on fs.server_id = ps.server_id
            order by ps.last_login_time desc nulls last, ps.character_name nulls last, ps.account_id
        """
        rows = enrich_steam_profiles([dict(row) for row in query(sql)])
        online = [row for row in rows if str(row.get("online_status") or "").lower() == "online"]
        offline = [row for row in rows if str(row.get("online_status") or "").lower() != "online"]
        return {
            "counts": {
                "total": len(rows),
                "online": len(online),
                "offline": len(offline),
            },
            "online": online,
            "offline": offline,
        }

    def hagga_basin_players(self):
        rows = query("""
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, fs.map as farm_map, wp.partition_id, wp.dimension_index, wp.label,
                   ps.player_controller_id, ps.player_pawn_id, ps.last_login_time,
                   a.map as actor_map, a.partition_id as actor_partition_id,
                   ((a.transform).location).x::float8 as x,
                   ((a.transform).location).y::float8 as y,
                   ((a.transform).location).z::float8 as z,
                   tri.map as return_map,
                   ((tri.transform).location).x::float8 as return_x,
                   ((tri.transform).location).y::float8 as return_y,
                   ((tri.transform).location).z::float8 as return_z
            from dune.player_state ps
            left join dune.actors a on a.id = ps.player_pawn_id
            left join dune.travel_return_info tri on tri.player_controller_id = ps.player_controller_id
            left join dune.farm_state fs on fs.server_id = ps.server_id
            left join dune.world_partition wp on wp.server_id = ps.server_id
            where ps.online_status::text = 'Online'
              and a.map = 'HaggaBasin'
              and a.transform is not null
            order by ps.character_name nulls last, ps.account_id
        """)
        bounds_row = (query("""
            select min(((a.transform).location).x::float8) as min_x,
                   max(((a.transform).location).x::float8) as max_x,
                   min(((a.transform).location).y::float8) as min_y,
                   max(((a.transform).location).y::float8) as max_y,
                   count(*) as actor_count
            from dune.actors a
            where a.map = 'HaggaBasin'
              and a.transform is not null
        """) or [{}])[0]
        bounds = {
            "minX": bounds_row.get("min_x"),
            "maxX": bounds_row.get("max_x"),
            "minY": bounds_row.get("min_y"),
            "maxY": bounds_row.get("max_y"),
            "actorCount": bounds_row.get("actor_count") or 0,
        }
        landmarks = []
        diagnostics = query("""
            with online_players as (
                select ps.account_id, ps.character_name, ps.player_controller_id, ps.player_pawn_id, ps.player_state_id
                from dune.player_state ps
                where ps.online_status::text = 'Online'
            ),
            actor_candidates as (
                select op.account_id, op.character_name, 'actor:controller' as source, a.map,
                       ((a.transform).location).x::float8 as x,
                       ((a.transform).location).y::float8 as y,
                       ((a.transform).location).z::float8 as z,
                       a.partition_id, a.dimension_index,
                       a.id::text as ref
                from online_players op
                join dune.actors a on a.id = op.player_controller_id
                union all
                select op.account_id, op.character_name, 'actor:pawn' as source, a.map,
                       ((a.transform).location).x::float8,
                       ((a.transform).location).y::float8,
                       ((a.transform).location).z::float8,
                       a.partition_id, a.dimension_index,
                       a.id::text
                from online_players op
                join dune.actors a on a.id = op.player_pawn_id
                union all
                select op.account_id, op.character_name, 'actor:player_state' as source, a.map,
                       ((a.transform).location).x::float8,
                       ((a.transform).location).y::float8,
                       ((a.transform).location).z::float8,
                       a.partition_id, a.dimension_index,
                       a.id::text
                from online_players op
                join dune.actors a on a.id = op.player_state_id
            ),
            travel_candidates as (
                select op.account_id, op.character_name, 'travel:return_info' as source, tri.map,
                       ((tri.transform).location).x::float8 as x,
                       ((tri.transform).location).y::float8 as y,
                       ((tri.transform).location).z::float8 as z,
                       null::bigint as partition_id, null::integer as dimension_index,
                       op.player_controller_id::text as ref
                from online_players op
                join dune.travel_return_info tri on tri.player_controller_id = op.player_controller_id
            ),
            function_candidates as (
                select op.account_id, op.character_name, 'function:load_travel_to_player_info' as source, l.map,
                       ((l.transform).location).x::float8 as x,
                       ((l.transform).location).y::float8 as y,
                       ((l.transform).location).z::float8 as z,
                       l.partition_id, l.dimension_index,
                       op.player_controller_id::text as ref
                from online_players op
                cross join lateral dune.load_travel_to_player_info(op.player_controller_id) l
            ),
            respawn_candidates as (
                select op.account_id, op.character_name, 'respawn:' || prl.group as source, coalesce(a.map, prl.map) as map,
                       coalesce(((a.transform).location).x::float8, ((prl.locator_transform).location).x::float8) as x,
                       coalesce(((a.transform).location).y::float8, ((prl.locator_transform).location).y::float8) as y,
                       coalesce(((a.transform).location).z::float8, ((prl.locator_transform).location).z::float8) as z,
                       a.partition_id, coalesce(a.dimension_index, prl.dimension) as dimension_index,
                       coalesce(prl.locator_actor_id::text, prl.locator_name, prl.id::text) as ref
                from online_players op
                join dune.player_respawn_locations prl on prl.account_id = op.account_id
                left join dune.actors a on a.id = prl.locator_actor_id
            ),
            recent_events as (
                select distinct on (op.account_id, ge.event_type)
                       op.account_id, op.character_name, 'event:' || ge.event_type::text as source, ge.map,
                       ge.x::float8 as x, ge.y::float8 as y, ge.z::float8 as z,
                       ge.partition_id, null::integer as dimension_index,
                       ge.universe_time::text as ref
                from online_players op
                join dune.game_events ge on ge.actor_id in (op.player_controller_id, op.player_pawn_id, op.player_state_id)
                order by op.account_id, ge.event_type, ge.universe_time desc
            )
            select *, case
                when x is null or y is null then 'no coordinates'
                when source like 'actor:%%' then 'DB actor transform; persists but may lag live client'
                when source = 'function:load_travel_to_player_info' then 'DB server helper; same persistence layer as actors'
                when source = 'travel:return_info' then 'return/teleport target, not live position'
                when source like 'respawn:%%' then 'respawn target, vehicle, or beacon; useful context only'
                when source like 'event:%%' then 'historical event location, not live position'
                else 'candidate'
            end as assessment
            from (
                select * from actor_candidates
                union all select * from function_candidates
                union all select * from travel_candidates
                union all select * from respawn_candidates
                union all select * from recent_events
            ) candidates
            order by character_name, source
        """)
        return {
            "map": "HaggaBasin",
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "bounds": bounds,
            "calibration": {
                "minX": HAGGA_MAP_MIN_X,
                "maxX": HAGGA_MAP_MAX_X,
                "minY": HAGGA_MAP_MIN_Y,
                "maxY": HAGGA_MAP_MAX_Y,
                "invertX": HAGGA_MAP_INVERT_X,
                "invertY": HAGGA_MAP_INVERT_Y,
                "imageMinU": HAGGA_MAP_IMAGE_MIN_U,
                "imageMaxU": HAGGA_MAP_IMAGE_MAX_U,
                "imageMinV": HAGGA_MAP_IMAGE_MIN_V,
                "imageMaxV": HAGGA_MAP_IMAGE_MAX_V,
                "showReturnPoints": HAGGA_MAP_SHOW_RETURN_POINTS,
                "source": "Gaming.tools survival_1 tile bounds: image U from world X, image V from world Y",
            },
            "landmarks": landmarks,
            "pois": read_hagga_pois(),
            "diagnostics": diagnostics,
            "players": rows,
        }

    def character_detail(self, account_id):
        player = query("select * from dune.player_state where account_id=%s", (account_id,))
        if not player:
            self.error(HTTPStatus.NOT_FOUND, "character not found")
            return {}
        controller_id = player[0].get("player_controller_id")
        pawn_id = player[0].get("player_pawn_id")
        server_id = player[0].get("server_id")
        return {
            "player": player[0],
            "account": enrich_steam_profiles([dict(row) for row in query("select id, funcom_id, platform_name, platform_id, takeoverable from dune.accounts where id=%s", (account_id,))]),
            "mapContext": query("""
                select fs.server_id, fs.farm_id, fs.ready, fs.alive, fs.map,
                       fs.revision, fs.game_addr, fs.game_port, fs.igw_addr, fs.igw_port,
                       fs.connected_players,
                       wp.partition_id, wp.dimension_index, wp.label, wp.blocked
                from dune.farm_state fs
                left join dune.world_partition wp on wp.server_id = fs.server_id
                where fs.server_id=%s
                limit 1
            """, (server_id,)) if server_id else [],
            "previousPartition": query("""
                select partition_id, server_id, map, dimension_index, label, blocked
                from dune.world_partition
                where partition_id=%s
            """, (player[0].get("previous_server_partition_id"),)) if player[0].get("previous_server_partition_id") is not None else [],
            "actorLocations": query("""
                select id, class, map, transform::text as transform, partition_id,
                       dimension_index, owner_account_id, serial,
                       ((transform).location).x::float8 as x,
                       ((transform).location).y::float8 as y,
                       ((transform).location).z::float8 as z
                from dune.actors
                where id in (%s,%s,%s)
                order by id
            """, (controller_id, player[0].get("player_state_id"), pawn_id)),
            "travelReturn": query("""
                select player_controller_id, map, transform::text as transform
                from dune.travel_return_info
                where player_controller_id=%s
            """, (controller_id,)),
            "overmap": query("select * from dune.overmap_players where player_id in (%s,%s) order by player_id", (controller_id, pawn_id)),
            "respawnLocations": query("""
                select id, account_id, "group", locator_transform, locator_actor_id,
                       locator_name, map, dimension, last_used_timestamp, locator_name_index
                from dune.player_respawn_locations
                where account_id=%s
                order by last_used_timestamp desc nulls last
                limit 25
            """, (account_id,)),
            "currency": query("select * from dune.player_virtual_currency_balances where player_controller_id=%s order by currency_id", (controller_id,)),
            "specialization": query("select * from dune.specialization_tracks where player_id=%s order by track_type::text", (controller_id,)),
            "faction": query("select * from dune.player_faction where actor_id=%s order by faction_id", (pawn_id,)),
            "reputation": query("select * from dune.player_faction_reputation where actor_id=%s order by faction_id", (pawn_id,)),
            "inventories": query("select * from dune.inventories where actor_id in (%s,%s) order by id", (controller_id, pawn_id)),
            "inventoryItems": query("select * from dune.admin_get_inventory_details(%s)", (account_id,)),
            "realtime": {
                "source": "database snapshots and Director farm_state",
                "serverTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "pollSeconds": 5,
            },
        }

    def character_slot_contract(self):
        errors = {}
        functions = reference_query(errors, "characterLifecycleFunctions", """
            select p.proname as name,
                   pg_get_function_identity_arguments(p.oid) as args,
                   pg_get_function_result(p.oid) as result
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname='dune'
              and p.proname in (
                'login_account',
                'delete_account',
                'takeover_account',
                'save_player',
                'save_player_pawn',
                'export_character',
                'import_character',
                'transfer_character'
              )
            order by p.proname
        """)
        tables = reference_query(errors, "characterIdentityTables", """
            select table_name, column_name, data_type, udt_name
            from information_schema.columns
            where table_schema='dune'
              and table_name in (
                'accounts',
                'player_state',
                'player_transfers',
                'character_transfers',
                'actors',
                'inventories'
              )
            order by table_name, ordinal_position
        """)
        names = {str(row.get("name") or "") for row in functions}
        required_observed = {"login_account", "delete_account", "takeover_account", "save_player", "save_player_pawn"}
        has_takeover_swap = any(
            str(row.get("name") or "") == "takeover_account"
            and str(row.get("args") or "").strip() == "in_user_to_takeover text, in_current_user text"
            and str(row.get("result") or "").strip() == "void"
            for row in functions
        )
        has_lifecycle_evidence = bool(required_observed.intersection(names))
        return {
            "functions": functions,
            "tables": tables,
            "errors": errors,
            "safeNativeSwapPath": has_takeover_swap,
            "safeNativeSwapAction": "takeover_account" if has_takeover_swap else None,
            "blockedReason": None if has_takeover_swap else "No validated first-party hibernate/switch function contract is mapped; execution remains blocked to avoid synthetic player_state edits.",
            "observedLifecycleEvidence": sorted(required_observed.intersection(names)),
            "confidence": "moderate" if has_takeover_swap or has_lifecycle_evidence else "low",
        }

    def character_slots(self, account_id):
        account_id = int(account_id)
        errors = {}
        active_rows = reference_query(errors, "activePlayer", """
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, ps.player_controller_id, ps.player_pawn_id, ps.player_state_id,
                   ps.last_login_time, ps.logoff_persistence_end_time, ps.reconnect_grace_period_end,
                   a.id as account_row_id, a."user" as fls_id, a.funcom_id, a.platform_name, a.platform_id
            from dune.player_state ps
            left join dune.accounts a on a.id=ps.account_id
            where ps.account_id=%s
        """, (account_id,))
        if not active_rows:
            raise ValueError("account_id not found in dune.player_state")
        active = active_rows[0]
        candidates = reference_query(errors, "nativeOwnedCandidates", """
            with target_account as (
                select id, "user", funcom_id, platform_name, platform_id
                from dune.accounts
                where id=%s
            )
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, ps.player_controller_id, ps.player_pawn_id, ps.player_state_id,
                   ps.last_login_time, a."user" as fls_id, a.funcom_id, a.platform_name, a.platform_id,
                   case
                     when a."user" is not distinct from ta."user" then 'same-account-user'
                     when a.funcom_id is not distinct from ta.funcom_id then 'same-funcom-id'
                     when a.platform_name is not distinct from ta.platform_name and a.platform_id is not distinct from ta.platform_id then 'same-platform-id'
                     else 'unknown'
                   end as ownership_evidence
            from target_account ta
            join dune.accounts a on a.id <> ta.id
              and (
                a."user" is not distinct from ta."user"
                or a.funcom_id is not distinct from ta.funcom_id
                or (a.platform_name is not distinct from ta.platform_name and a.platform_id is not distinct from ta.platform_id)
              )
            join dune.player_state ps on ps.account_id=a.id
            order by ps.last_login_time desc nulls last, ps.account_id
            limit %s
        """, (account_id, ADMIN_REFERENCE_LIMIT))
        contract = self.character_slot_contract()
        return {
            "ok": True,
            "accountId": account_id,
            "activeCharacter": active,
            "offline": str(active.get("online_status") or "").lower() != "online",
            "candidates": candidates,
            "contract": contract,
            "actions": ["new-character", "switch-character", "restore-character"],
            "executionGate": "DUNE_ADMIN_CHARACTER_SWAP_ENABLED",
            "confirm": CONFIRM_CHARACTER_SWAP,
            "defaultDryRun": True,
            "errors": errors,
        }

    def character_slot_plan(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        action = str(body.get("action", "new-character")).strip().lower()
        if action not in ("new-character", "switch-character", "restore-character"):
            raise ValueError("action must be new-character, switch-character, or restore-character")
        target_account_id = body.get("target_account_id", body.get("targetAccountId"))
        if action in ("switch-character", "restore-character") and target_account_id in ("", None):
            raise ValueError("target_account_id is required for switch-character and restore-character")
        slots = self.character_slots(account_id)
        active = slots["activeCharacter"]
        online = str(active.get("online_status") or "").lower() == "online"
        target = None
        if target_account_id not in ("", None):
            target_id = int(target_account_id)
            for candidate in slots["candidates"]:
                if int(candidate.get("account_id")) == target_id:
                    target = candidate
                    break
            if target is None:
                raise ValueError("target_account_id is not a native-owned hibernated candidate for this account")
            if str(target.get("online_status") or "").lower() == "online":
                online = True
        contract = slots["contract"]
        executable = bool(contract.get("safeNativeSwapPath")) and not online and action in ("switch-character", "restore-character")
        blockers = []
        if online:
            blockers.append("target account or requested character is online")
        if action == "new-character":
            blockers.append("new-character execution is blocked because the only mapped native blank-character path is delete_account, which destroys the current character")
        if not contract.get("safeNativeSwapPath"):
            blockers.append(contract.get("blockedReason") or "safe native character swap path is not mapped")
        if action == "new-character":
            intent = "Hibernate the current active character, leaving the account to use the game's native character creator on next login."
        else:
            intent = "Switch active play back to a previously hibernated, native-owned character for the same account."
        native_call = None
        if action in ("switch-character", "restore-character") and target:
            native_call = {
                "function": "dune.takeover_account",
                "in_user_to_takeover": target.get("fls_id"),
                "in_current_user": active.get("fls_id"),
                "effect": "Swaps the active login identity onto the target character account and moves the target identity onto the current character account.",
            }
            if not target.get("fls_id") or not active.get("fls_id"):
                executable = False
                blockers.append("active and target accounts must both have FLS user ids")
        plan = {
            "intent": intent,
            "activeBefore": active,
            "targetCharacter": target,
            "nativeContract": contract,
            "nativeCall": native_call,
            "transactionSafety": {
                "backupBeforeTransaction": True,
                "advisoryLocks": "sorted active/target account ids",
                "rowLocks": "dune.encrypted_player_state and dune.encrypted_accounts rows for active and target account ids",
                "offlineRecheckInsideTransaction": True,
                "commitRequiresPostSwapVerification": True,
            },
            "steps": [
                "Refuse execution while the active account or selected target is online.",
                "Create a database backup.",
                "Take account-id advisory locks and lock both player_state rows in one transaction.",
                "Recheck offline status inside the transaction.",
                "Execute only the validated first-party takeover_account switch path.",
                "Verify swapped FLS identities before commit.",
                "Return before/after rows and rollback hints.",
            ],
            "rollback": {
                "hint": "Use the created DB backup or reverse with the same validated native lifecycle path after inspecting audit before/after rows.",
                "active_account_id": account_id,
                "target_account_id": int(target_account_id) if target_account_id not in ("", None) else None,
            },
            "blockers": blockers,
        }
        return {
            "ok": True,
            "dryRun": True,
            "accountId": account_id,
            "action": action,
            "targetAccountId": int(target_account_id) if target_account_id not in ("", None) else None,
            "executable": executable,
            "executionGate": "DUNE_ADMIN_CHARACTER_SWAP_ENABLED",
            "confirm": CONFIRM_CHARACTER_SWAP,
            "plan": plan,
        }

    def character_slot_execute(self, body):
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        planned = self.character_slot_plan(dict(body, dry_run=True))
        if dry_run:
            return planned
        self.require_mutations()
        if not CHARACTER_SWAP_ENABLED:
            raise PermissionError("character swap execution is disabled; set DUNE_ADMIN_CHARACTER_SWAP_ENABLED=true")
        require_confirmation(body, CONFIRM_CHARACTER_SWAP)
        if not planned.get("executable"):
            raise NotImplementedError("; ".join(planned.get("plan", {}).get("blockers") or ["character swap execution is blocked"]))
        backup = create_db_backup()
        active_before = planned["plan"]["activeBefore"]
        target_before = planned["plan"]["targetCharacter"]
        active_user = active_before.get("fls_id")
        target_user = target_before.get("fls_id") if target_before else None
        if not active_user or not target_user:
            raise ValueError("active and target accounts must both have FLS user ids")
        before_rows, after_rows, verified = character_swap_takeover(
            planned["accountId"],
            planned["targetAccountId"],
            active_user,
            target_user,
        )
        return {
            "ok": True,
            "dryRun": False,
            "accountId": planned["accountId"],
            "targetAccountId": planned["targetAccountId"],
            "action": planned["action"],
            "executable": True,
            "backup": backup,
            "nativeCall": planned["plan"]["nativeCall"],
            "before": before_rows,
            "after": after_rows,
            "verified": verified,
            "rollback": {
                "hint": "Run the inverse switch after verifying both characters are offline, or restore the DB backup.",
                "inversePayload": {
                    "dry_run": False,
                    "account_id": planned["targetAccountId"],
                    "action": "restore-character",
                    "target_account_id": planned["accountId"],
                    "confirm": CONFIRM_CHARACTER_SWAP,
                },
            },
        }

    def admin_reference(self):
        errors = {}
        return {
            "currencyIds": reference_query(errors, "currencyIds", "select distinct currency_id from dune.player_virtual_currency_balances order by currency_id"),
            "specializationTrackTypes": reference_query(errors, "specializationTrackTypes", """
                select enumlabel as track_type
                from pg_enum e
                join pg_type t on t.oid = e.enumtypid
                where t.typname = 'specializationtracktype'
                order by enumsortorder
            """),
            "observedItemTemplates": reference_query(errors, "observedItemTemplates", """
                select template_id, count(*) as count
                from dune.items
                where template_id is not null
                group by template_id
                order by count desc, template_id
                limit %s
            """, (ADMIN_REFERENCE_LIMIT,)),
            "knownItemTemplates": reference_query(errors, "knownItemTemplates", """
                with templates as (
                    select template_id, 'landsraad_task_reward' as source from dune.landsraad_task_rewards where template_id is not null
                    union all
                    select template_id, 'landsraad_house_reward' as source from dune.landsraad_house_rewards where template_id is not null
                    union all
                    select template_id, 'vendor_stock' as source from dune.vendor_stock_state where template_id is not null
                    union all
                    select template_id, 'vehicle_module' as source from dune.vehicle_modules where template_id is not null
                    union all
                    select template_id, 'exchange_order' as source from dune.dune_exchange_orders where template_id is not null
                    union all
                    select template_id, 'observed_item' as source from dune.items where template_id is not null
                )
                select template_id, count(*) as references, string_agg(distinct source, ', ' order by source) as sources
                from templates
                group by template_id
                order by template_id
                limit %s
            """, (ADMIN_REFERENCE_LIMIT,)),
            "recentInventories": reference_query(errors, "recentInventories", """
                with recent_players as (
                    select account_id, character_name, player_pawn_id, player_controller_id
                    from dune.player_state
                    order by last_login_time desc nulls last, account_id
                    limit %s
                )
                select ps.account_id, ps.character_name, inv.id as inventory_id, inv.actor_id,
                       inv.inventory_type, inv.max_item_count, count(i.id) as item_count
                from dune.inventories inv
                left join dune.items i on i.inventory_id = inv.id
                join recent_players ps on ps.player_pawn_id = inv.actor_id or ps.player_controller_id = inv.actor_id
                group by ps.account_id, ps.character_name, inv.id, inv.actor_id, inv.inventory_type, inv.max_item_count
                order by ps.character_name nulls last, inv.id
                limit %s
            """, (CHARACTER_SEARCH_LIMIT, ADMIN_REFERENCE_LIMIT)),
            "inventoryTypes": reference_query(errors, "inventoryTypes", """
                select inventory_type, count(*) as count, max(max_item_count) as max_item_count
                from dune.inventories
                group by inventory_type
                order by inventory_type
            """),
            "keystones": reference_query(errors, "keystones", "select id, name from dune.specialization_keystones_map order by name"),
            "worldPartitions": reference_query(errors, "worldPartitions", """
                select partition_id, map, dimension_index, label, blocked, server_id
                from dune.world_partition
                order by map, dimension_index, partition_id
                limit %s
            """, (ADMIN_REFERENCE_LIMIT,)),
            "haggaCalibration": {
                "minX": HAGGA_MAP_MIN_X,
                "maxX": HAGGA_MAP_MAX_X,
                "minY": HAGGA_MAP_MIN_Y,
                "maxY": HAGGA_MAP_MAX_Y,
                "invertX": HAGGA_MAP_INVERT_X,
                "invertY": HAGGA_MAP_INVERT_Y,
                "imageMinU": HAGGA_MAP_IMAGE_MIN_U,
                "imageMaxU": HAGGA_MAP_IMAGE_MAX_U,
                "imageMinV": HAGGA_MAP_IMAGE_MIN_V,
                "imageMaxV": HAGGA_MAP_IMAGE_MAX_V,
            },
            "errors": errors,
            "publicItemDatabase": "https://dune.gaming.tools/items",
            "publicItemDatabaseAlt": "https://dune.geno.gg/items/",
        }

    def grant_item(self, body):
        inventory_id = self.resolve_inventory_id(body)
        template_id = str(body["template_id"]).strip()
        stack_size = max(1, int(body.get("stack_size", 1)))
        if stack_size > MAX_ITEM_STACK_SIZE:
            raise ValueError(f"stack_size exceeds DUNE_ADMIN_MAX_ITEM_STACK_SIZE={MAX_ITEM_STACK_SIZE}")
        quality_level = max(0, int(body.get("quality_level", 0)))
        position_index = body.get("position_index", "")
        stats = body.get("stats", {}) or {}
        dry_run = str(body.get("dry_run", "")).lower() in ("1", "true", "yes", "on")
        if isinstance(stats, str):
            stats = json.loads(stats or "{}")
        if not isinstance(stats, dict):
            raise ValueError("stats must be a JSON object")
        if not template_id:
            raise ValueError("template_id is required")
        inventory = self.inventory_for_grant(inventory_id)
        if position_index in ("", None):
            rows = query("select coalesce(max(position_index), -1) + 1 as next_position from dune.items where inventory_id=%s", (inventory_id,))
            position_index = int(rows[0]["next_position"])
        else:
            position_index = int(position_index)
        if position_index < 0:
            raise ValueError("position_index must be >= 0")
        max_count = inventory.get("max_item_count")
        if max_count is not None and max_count >= 0 and position_index >= max_count:
            raise ValueError(f"position_index {position_index} is outside inventory capacity {max_count}")
        if query("select 1 from dune.items where inventory_id=%s and position_index=%s", (inventory_id, position_index)):
            raise ValueError("target inventory position is already occupied")
        result = {
            "inventory_id": inventory_id,
            "template_id": template_id,
            "stack_size": stack_size,
            "position_index": position_index,
            "quality_level": quality_level,
            "dry_run": dry_run,
            "warnings": self.item_grant_warnings(inventory, template_id),
        }
        if dry_run:
            return result
        item_id = query("select dune.advance_items_id_sequencer(1) as item_id")[0]["item_id"]
        acquisition_time = int(body.get("acquisition_time") or time.time() * 1000)
        execute("""
            select dune.save_item((
                %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s
            )::dune.inventoryitem)
        """, (
            item_id,
            inventory_id,
            stack_size,
            position_index,
            template_id,
            True,
            acquisition_time,
            json.dumps(stats),
            quality_level,
            None,
        ))
        result.update({
            "item_id": item_id,
            "item": query("select * from dune.load_item(%s)", (item_id,)),
        })
        return result

    def resolve_inventory_id(self, body):
        if str(body.get("inventory_id", "")).strip():
            return int(body["inventory_id"])
        account_id = body.get("account_id")
        character_name = str(body.get("character_name", "")).strip()
        inventory_type = body.get("inventory_type")
        if account_id in ("", None) and not character_name:
            raise ValueError("inventory_id, account_id, or character_name is required")
        player = self.resolve_player(account_id=account_id, character_name=character_name)
        params = [player["player_pawn_id"], player["player_controller_id"]]
        type_clause = ""
        if inventory_type not in ("", None):
            type_clause = "and inv.inventory_type=%s"
            params.append(int(inventory_type))
        rows = query(f"""
            select inv.id as inventory_id, inv.actor_id, inv.inventory_type, inv.max_item_count,
                   count(i.id) as item_count
            from dune.inventories inv
            left join dune.items i on i.inventory_id = inv.id
            where inv.actor_id in (%s,%s) {type_clause}
            group by inv.id, inv.actor_id, inv.inventory_type, inv.max_item_count
            order by
              case when inv.actor_id=%s then 0 else 1 end,
              inv.inventory_type nulls last,
              inv.id
            limit 1
        """, (*params, player["player_pawn_id"]))
        if not rows:
            raise ValueError("no owned inventory found for character; log in once or enter an explicit inventory_id")
        return int(rows[0]["inventory_id"])

    def resolve_player(self, account_id=None, character_name=""):
        if account_id not in ("", None):
            rows = query("select * from dune.player_state where account_id=%s", (int(account_id),))
        else:
            rows = query("select * from dune.player_state where character_name ilike %s order by last_login_time desc nulls last limit 2", (character_name,))
            if len(rows) > 1:
                raise ValueError("character_name matched multiple players; use account_id")
        if not rows:
            raise ValueError("player not found")
        return rows[0]

    def inventory_for_grant(self, inventory_id):
        rows = query("""
            select inv.id as inventory_id, inv.actor_id, inv.item_id, inv.inventory_type,
                   inv.max_item_count, inv.max_item_volume, count(i.id) as item_count,
                   ps.account_id, ps.character_name, ps.online_status::text
            from dune.inventories inv
            left join dune.items i on i.inventory_id = inv.id
            left join dune.player_state ps on ps.player_pawn_id = inv.actor_id or ps.player_controller_id = inv.actor_id
            where inv.id=%s
            group by inv.id, ps.account_id, ps.character_name, ps.online_status
        """, (inventory_id,))
        if not rows:
            raise ValueError("inventory_id does not exist")
        return rows[0]

    def item_grant_warnings(self, inventory, template_id):
        warnings = []
        if not inventory.get("account_id"):
            warnings.append("inventory is not directly tied to a player pawn/controller")
        if inventory.get("online_status") and str(inventory["online_status"]).lower() != "offline":
            warnings.append("player may be online; prefer grants while offline, then reconnect")
        known = query("""
            select 1 from (
                select template_id from dune.items where template_id is not null
                union
                select template_id from dune.landsraad_task_rewards where template_id is not null
                union
                select template_id from dune.landsraad_house_rewards where template_id is not null
                union
                select template_id from dune.vendor_stock_state where template_id is not null
                union
                select template_id from dune.vehicle_modules where template_id is not null
                union
                select template_id from dune.dune_exchange_orders where template_id is not null
            ) known_templates
            where lower(template_id)=lower(%s)
            limit 1
        """, (template_id,))
        if not known:
            warnings.append("template_id has not been observed in local item/reward tables; verify against a public item database before granting")
        return warnings

    def delete_item(self, body):
        item_id = int(body["item_id"])
        count = int(body.get("count") or 0)
        if count < 0:
            raise ValueError("count must be >= 0")
        item = query("select * from dune.load_item(%s)", (item_id,))
        if not item:
            raise ValueError("item_id does not exist")
        if count <= 0 or count >= int(item[0]["stack_size"]):
            execute("select dune.delete_item(%s)", (item_id,))
            return {"ok": True, "item_id": item_id, "count": count, "deleted": True}
        remaining = query("select dune.delete_inventory_item(%s,%s) as remaining_stack", (item_id, count))[0]["remaining_stack"]
        return {"ok": True, "item_id": item_id, "count": count, "deleted": False, "remaining_stack": remaining}

    def set_item_stack(self, body):
        item_id = int(body["item_id"])
        stack_size = max(1, int(body["stack_size"]))
        if stack_size > MAX_ITEM_STACK_SIZE:
            raise ValueError(f"stack_size exceeds DUNE_ADMIN_MAX_ITEM_STACK_SIZE={MAX_ITEM_STACK_SIZE}")
        item = query("select * from dune.load_item(%s)", (item_id,))
        if not item:
            raise ValueError("item_id does not exist")
        row = item[0]
        execute("""
            select dune.save_item((
                %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s
            )::dune.inventoryitem)
        """, (
            item_id,
            row["inventory_id"],
            stack_size,
            row["position_index"],
            row["template_id"],
            row.get("is_new", True),
            row["acquisition_time"],
            json.dumps(row.get("stats") or {}),
            row["quality_level"],
            row.get("volume_override"),
        ))
        return {"ok": True, "item_id": item_id, "stack_size": stack_size, "item": query("select * from dune.load_item(%s)", (item_id,))}

    def ops_health(self):
        farm = query("select server_id,farm_id,ready,alive,map,revision,game_addr,game_port,igw_addr,igw_port,connected_players from dune.farm_state order by map, server_id")
        partitions = query("select partition_id,server_id,map,dimension_index,label,blocked from dune.world_partition order by partition_id")
        active = query("select * from dune.active_server_ids order by server_id")
        active_ids = {row.get("server_id") for row in active}
        map_status = self.map_health_rows(farm, partitions, active_ids)
        expected = len(partitions)
        current_ready_alive = sum(1 for row in map_status if row.get("ready") and row.get("alive") and row.get("active"))
        current_alive_active = sum(1 for row in map_status if row.get("alive") and row.get("active"))
        active_count = len(active)
        player_counts = query("""
            select
              coalesce((select sum(connected_players) from dune.farm_state), 0) as connected_players_reported,
              (select count(*) from dune.get_online_player_controller_ids_on_farm()) as online_controller_ids,
              (select count(*) from dune.get_all_online_or_recently_disconnected_player_online_state()) as online_or_recently_disconnected,
              (select count(*) from dune.get_player_online_state_within_grace_period_for_each_server()) as grace_period_entries
        """)[0]
        current_players = int(player_counts.get("connected_players_reported") or 0)
        player_peak = update_daily_player_peak(current_players)
        verdicts = [
            {"name": "current partitions have alive active farm rows", "ok": expected > 0 and current_alive_active == expected, "value": f"{current_alive_active}/{expected}"},
            {"name": "current partitions have ready/alive farm rows", "ok": expected > 0 and current_ready_alive == expected, "value": f"{current_ready_alive}/{expected}"},
            {"name": "active server ids match partitions", "ok": expected > 0 and active_count == expected, "value": f"{active_count}/{expected}"},
            {"name": "map health rows", "ok": expected > 0 and all(row.get("online") for row in map_status), "value": f"{sum(1 for row in map_status if row.get('online'))}/{len(map_status)}"},
            {"name": "RabbitMQ-backed farm registration", "ok": expected > 0 and current_alive_active == expected and active_count == expected, "value": "inferred from current world_partition rows, farm_state, and active_server_ids"},
            {"name": "player counts query", "ok": True},
        ]
        return {
            "verdicts": verdicts,
            "playerCounts": player_counts,
            "playerPeak": player_peak,
            "summary": {
                "readyAlive": current_ready_alive,
                "aliveActive": current_alive_active,
                "expectedPartitions": expected,
                "activeServers": active_count,
                "onlineMaps": sum(1 for row in map_status if row.get("online")),
                "totalMaps": len(map_status),
                "peakPlayersToday": player_peak.get("peak"),
                "peakPlayersDate": player_peak.get("date"),
            },
            "mapStatus": map_status,
            "farmState": farm,
            "partitions": partitions,
            "activeServers": active,
        }

    def map_health_rows(self, farm, partitions, active_ids):
        farm_by_server = {row.get("server_id"): row for row in farm}
        rows = []
        for part in partitions:
            server_id = part.get("server_id")
            farm_row = farm_by_server.get(server_id, {})
            ready = bool(farm_row.get("ready"))
            alive = bool(farm_row.get("alive"))
            active = server_id in active_ids
            online = bool(server_id) and alive and active and not bool(part.get("blocked"))
            rows.append({
                "partition_id": part.get("partition_id"),
                "map": part.get("map"),
                "label": part.get("label"),
                "dimension": part.get("dimension_index"),
                "server_id": server_id,
                "online": online,
                "ready": ready,
                "alive": alive,
                "active": active,
                "blocked": bool(part.get("blocked")),
                "players": farm_row.get("connected_players", 0),
                "game": self.addr_port(farm_row.get("game_addr"), farm_row.get("game_port")),
                "igw": self.addr_port(farm_row.get("igw_addr"), farm_row.get("igw_port")),
            })
        return rows

    def addr_port(self, addr, port):
        if not addr or not port:
            return ""
        return f"{addr}:{port}"

    def network_health(self):
        probes = [
            self.tcp_probe("postgres", "postgres", 5432),
            self.http_probe("dune account portal", "https://account.duneawakening.com/"),
            self.http_probe("Dune website", "https://duneawakening.com/"),
            self.http_probe("Funcom website", "https://funcom.com/"),
        ]
        okish = [probe for probe in probes if probe.get("ok") or probe.get("httpStatus") in (401, 403, 404)]
        return {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "probes": probes,
            "verdicts": [
                {"name": "local database network", "ok": probes[0].get("ok"), "value": "postgres:5432"},
                {"name": "upstream HTTP reachable", "ok": len(okish) >= len(probes) - 1, "value": f"{len(okish)}/{len(probes)}"},
            ],
        }

    def tcp_probe(self, name, host, port):
        start = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=3):
                latency_ms = int((time.monotonic() - start) * 1000)
                return {"name": name, "type": "tcp", "target": f"{host}:{port}", "ok": True, "latencyMs": latency_ms}
        except OSError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"name": name, "type": "tcp", "target": f"{host}:{port}", "ok": False, "latencyMs": latency_ms, "error": str(exc)}

    def http_probe(self, name, url):
        start = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": "dune-admin-health/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                latency_ms = int((time.monotonic() - start) * 1000)
                return {"name": name, "type": "http", "target": url, "ok": 200 <= response.status < 400, "httpStatus": response.status, "latencyMs": latency_ms}
        except urllib.error.HTTPError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"name": name, "type": "http", "target": url, "ok": 200 <= exc.code < 400, "httpStatus": exc.code, "latencyMs": latency_ms, "error": exc.reason}
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"name": name, "type": "http", "target": url, "ok": False, "latencyMs": latency_ms, "error": str(exc)}

    def security_audit(self):
        env_values = read_env()
        token_required = os.environ.get("DUNE_ADMIN_REQUIRE_TOKEN", "false").lower() in ("1", "true", "yes", "on")
        checks = [
            {"name": "admin auth mode", "ok": True, "value": "token required" if token_required else "local unlocked"},
            {"name": "admin token configured", "ok": bool(ADMIN_TOKEN) if token_required else True, "value": "required" if token_required else "not required"},
            {"name": "admin token not placeholder", "ok": ADMIN_TOKEN not in ("", "change-me-admin-token") if token_required else True, "value": "required" if token_required else "not required"},
            {"name": "mutation gate configured", "ok": True, "value": "enabled" if MUTATIONS_ENABLED else "off"},
            {"name": "item grants enabled", "ok": ITEM_GRANTS_ENABLED, "value": ITEM_GRANTS_ENABLED},
            {"name": "allowed hosts configured", "ok": bool(ALLOWED_HOSTS), "value": ", ".join(sorted(ALLOWED_HOSTS))},
            {"name": "request body limit", "ok": MAX_BODY_BYTES <= 262144, "value": MAX_BODY_BYTES},
            {"name": "audit log rotation limit", "ok": 0 < AUDIT_MAX_BYTES <= 50 * 1024 * 1024, "value": AUDIT_MAX_BYTES},
            {"name": "request timeout bounded", "ok": 1 <= REQUEST_TIMEOUT_SECONDS <= 60, "value": REQUEST_TIMEOUT_SECONDS},
            {"name": "item stack mutation limit", "ok": 1 <= MAX_ITEM_STACK_SIZE <= 10000000, "value": MAX_ITEM_STACK_SIZE},
            {"name": "audit event response limit", "ok": 1 <= AUDIT_EVENT_LIMIT <= 1000, "value": AUDIT_EVENT_LIMIT},
            {"name": "admin reference response limit", "ok": 1 <= ADMIN_REFERENCE_LIMIT <= 1000, "value": ADMIN_REFERENCE_LIMIT},
            {"name": "character search response limit", "ok": 1 <= CHARACTER_SEARCH_LIMIT <= 1000, "value": CHARACTER_SEARCH_LIMIT},
            {"name": "JSON-only POST enforcement", "ok": True},
            {"name": "destructive action confirmation", "ok": True, "value": "server-side"},
            {"name": "FLS token represented in admin settings", "ok": "FLS_SECRET" in SAFE_ENV_KEYS},
            {"name": "server login password editable", "ok": "DUNE_SERVER_LOGIN_PASSWORD" in SAFE_ENV_KEYS},
            {"name": "director transfer settings editable", "ok": "director.ini" in ALLOWED_CONFIGS and bool(DIRECTOR_TRANSFER_SETTINGS)},
            {"name": "backup path under ignored backups/", "ok": str(BACKUP_ROOT).startswith(str(ROOT / "backups"))},
            {"name": "audit log under ignored backups/", "ok": str(AUDIT_LOG).startswith(str(ROOT / "backups")), "value": str(AUDIT_LOG.relative_to(ROOT))},
            {"name": "RabbitMQ secret represented in admin settings", "ok": "RMQ_HTTP_TOKEN_AUTH_SECRET" in SAFE_ENV_KEYS},
            {"name": "database password represented in admin settings", "ok": "POSTGRES_DUNE_PASSWORD" in SAFE_ENV_KEYS},
            {"name": "external address set", "ok": bool(env_values.get("EXTERNAL_ADDRESS", "")), "value": env_values.get("EXTERNAL_ADDRESS", "")},
        ]
        return {
            "checks": checks,
            "allowedConfigFiles": sorted(ALLOWED_CONFIGS),
            "safeEnvKeys": sorted(SAFE_ENV_KEYS),
            "notes": [
                "Keep the panel on trusted LAN/VPN only.",
                "Do not expose RabbitMQ, Postgres, or this panel directly to the internet.",
                "Take a backup before broad admin mutations or config surgery.",
            ],
        }

    def audit(self, action, ok=True, **fields):
        peer = self.client_address[0] if self.client_address else "unknown"
        audit_event(action, ok=ok, peer=peer, method=self.command, path=urllib.parse.urlparse(self.path).path, **fields)

    def optimization_signals(self):
        return {
            "memory": [
                {"name": "Survival guardrail", "value": "12Gi", "why": "Matches Funcom's official Survival_1 workload limit."},
                {"name": "Tight caps", "value": "avoid initially", "why": "Observed high-water memory can be much higher than later idle RSS."},
            ],
            "storage": [
                {"name": "Game image", "value": "~10.3GB", "why": "Large content/tooling layers dominate local image storage."},
                {"name": "Delete-in-child image", "value": "not enough", "why": "Deleting files in a child layer does not reclaim base image size."},
            ],
            "network": [
                {"name": "Gateway Postgres TIME_WAIT", "value": "watch", "why": "May indicate short-lived DB connections."},
                {"name": "TextRouter Postgres CLOSE_WAIT", "value": "watch", "why": "A growing count would indicate stale socket cleanup trouble."},
                {"name": "Public ports", "value": "7777/udp and 7888/udp only", "why": "RabbitMQ, Postgres, and admin surfaces should remain private."},
            ],
            "knobs": [
                {"name": "compose.limits.example.yaml", "value": "optional", "why": "Conservative memory guardrails without changing default topology."},
                {"name": "admin env settings", "value": sorted(SAFE_ENV_KEYS), "why": "Editable operational values, including protected secret fields behind the admin token."},
                {"name": "director transfer settings", "value": list(DIRECTOR_TRANSFER_SETTINGS), "why": "Typed character transfer policy controls written into config/director.ini."},
            ],
        }

    def resource_snapshot(self, live_stats=False):
        disk = shutil.disk_usage(ROOT)
        docker_error = None
        try:
            containers = docker_container_stats(live_stats=live_stats)
        except Exception as exc:
            docker_error = str(exc)
            containers = []
        return {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "host": {
                "hostname": socket.gethostname(),
                "cpuCount": os.cpu_count(),
                "load": read_loadavg(),
                "memory": read_meminfo(),
                "disk": {
                    "path": str(ROOT),
                    "totalBytes": disk.total,
                    "usedBytes": disk.used,
                    "freeBytes": disk.free,
                    "usedPercent": round((disk.used / disk.total) * 100, 1) if disk.total else None,
                },
            },
            "docker": {
                "socket": DOCKER_SOCKET,
                "composeProject": DOCKER_COMPOSE_PROJECT,
                "liveStats": live_stats,
                "error": docker_error,
                "containers": containers,
            },
        }

    def ops_runbook(self):
        return {
            "safeCliOnly": True,
            "why": "High-signal operator commands and workflows. Prefer the panel buttons for routine maintenance; use these when diagnosing or validating from a shell.",
            "commands": [
                {"name": "Current health", "command": "curl -sk https://<admin-host>/api/ops/health | jq '.summary'", "when": "Confirm 30/30 maps ready after restart or config changes."},
                {"name": "RabbitMQ auth path", "command": "./scripts/verify-rmq-auth-path.sh", "when": "Check admin-rmq/game-rmq can reach auth shim and text-router."},
                {"name": "Post-start recovery check", "command": "./scripts/restart-post-start-health.sh", "when": "Validate restart recovery plumbing without taking the game down."},
                {"name": "Backup validation", "command": "backup=backups/admin-panel/maintenance/<stamp>; tar -tzf \"$backup/server-saved.tgz\" >/dev/null && pg_restore --list \"$backup\"/*.dump >/dev/null", "when": "Verify a maintenance backup is readable."},
                {"name": "Daily timer", "command": "systemctl list-timers dune-daily-maintenance-schedule.timer --all --no-pager", "when": "Confirm 05:30 schedule for 06:00 maintenance."},
                {"name": "Status script", "command": "./scripts/status.sh .env", "when": "Quick health and high-signal logs."},
                {"name": "Runtime profile", "command": "./scripts/profile-runtime.sh .env", "when": "Memory/storage/network/process teardown."},
                {"name": "Network watch", "command": "./scripts/watch-network.sh .env", "when": "Check Postgres/RabbitMQ socket churn."},
            ],
        }

    def update_currency(self, body):
        controller_id = int(body["player_controller_id"])
        currency_id = int(body["currency_id"])
        amount = int(body["amount"])
        mode = body.get("mode", "add")
        if mode == "set":
            execute("""
                insert into dune.player_virtual_currency_balances(player_controller_id,currency_id,balance)
                values (%s,%s,%s)
                on conflict (player_controller_id,currency_id) do update set balance=excluded.balance
            """, (controller_id, currency_id, amount))
        elif mode == "add":
            execute("""
                insert into dune.player_virtual_currency_balances(player_controller_id,currency_id,balance)
                values (%s,%s,%s)
                on conflict (player_controller_id,currency_id) do update set balance=dune.player_virtual_currency_balances.balance + excluded.balance
            """, (controller_id, currency_id, amount))
        else:
            raise ValueError("mode must be add or set")

    def update_xp(self, body):
        player_id = int(body["player_id"])
        track_type = str(body["track_type"])
        amount = int(body["amount"])
        level = float(body.get("level", 0))
        mode = body.get("mode", "add")
        if mode == "set":
            execute("select dune.set_specialization_xp_and_level(%s, %s::dune.specializationtracktype, %s, %s)", (player_id, track_type, amount, level))
        elif mode == "add":
            existing = query("select xp_amount, level from dune.specialization_tracks where player_id=%s and track_type::text=%s", (player_id, track_type))
            current_xp = existing[0]["xp_amount"] if existing else 0
            current_level = existing[0]["level"] if existing else level
            execute("select dune.set_specialization_xp_and_level(%s, %s::dune.specializationtracktype, %s, %s)", (player_id, track_type, current_xp + amount, current_level))
        else:
            raise ValueError("mode must be add or set")

    def purchase_keystone(self, body):
        player_id = int(body["player_id"])
        keystone = str(body["keystone"]).strip()
        result = query("select dune.purchase_specialization_keystone(%s, %s) as purchased", (player_id, keystone))[0]["purchased"]
        if not result:
            raise ValueError("keystone was not purchased; it may be unknown or already present")
        return {"ok": True, "player_id": player_id, "keystone": keystone}

    def reset_keystones(self, body):
        player_id = int(body["player_id"])
        execute("select dune.reset_specialization_keystones(%s)", (player_id,))

    def economy_bundle(self, body):
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        plan = []
        for row in body.get("currency", []) or []:
            plan.append({"type": "currency", "payload": row, "statement": "insert/update dune.player_virtual_currency_balances"})
        for row in body.get("xp", []) or []:
            plan.append({"type": "xp", "payload": row, "statement": "select dune.set_specialization_xp_and_level(...)"})
        for row in body.get("items", []) or []:
            item_body = dict(row)
            item_body["dry_run"] = True
            try:
                preview = self.grant_item(item_body)
            except Exception as exc:
                preview = {"ok": False, "error": str(exc), "payload": item_body}
            plan.append({"type": "item", "payload": row, "preview": preview})
        if dry_run:
            return {"ok": True, "dryRun": True, "plan": plan, "executionGate": "DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED"}
        self.require_mutations()
        if not BUNDLE_MUTATIONS_ENABLED:
            raise PermissionError("bundle mutations are disabled; set DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_BUNDLE_MUTATION)
        executed = []
        for row in body.get("currency", []) or []:
            self.update_currency(row)
            executed.append({"type": "currency", "ok": True})
        for row in body.get("xp", []) or []:
            self.update_xp(row)
            executed.append({"type": "xp", "ok": True})
        for row in body.get("items", []) or []:
            self.require_item_grants()
            item_body = dict(row)
            item_body["dry_run"] = False
            executed.append({"type": "item", "result": self.grant_item(item_body)})
        return {"ok": True, "dryRun": False, "plan": plan, "executed": executed}

    def offline_player_recovery(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        partition_id = int(body.get("partition_id", body.get("partitionId")))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        player = query("""
            select ps.account_id, ps.character_name, ps.online_status::text, ps.server_id,
                   ps.previous_server_partition_id, a.funcom_id, a."user" as fls_id
            from dune.player_state ps
            left join dune.accounts a on a.id = ps.account_id
            where ps.account_id=%s
        """, (account_id,))
        partition = query("select partition_id, server_id, map, dimension_index, label, blocked from dune.world_partition where partition_id=%s", (partition_id,))
        if not player:
            raise ValueError("account_id not found")
        if not partition:
            raise ValueError("partition_id not found")
        if str(player[0].get("online_status") or "").lower() == "online":
            raise ValueError("player is online; offline recovery refuses to move online players")
        location = body.get("location", body.get("target_location", body.get("targetLocation", {})))
        if not isinstance(location, dict):
            raise ValueError("location must be an object with x, y, and z")
        target_location = {
            "x": float(location.get("x", 0)),
            "y": float(location.get("y", 0)),
            "z": float(location.get("z", 0)),
        }
        fls_id = str(player[0].get("fls_id") or player[0].get("funcom_id") or "").strip()
        if not fls_id:
            raise ValueError("player account has no FLS/user id for offline player recovery")
        offline_check = query("select dune.is_player_offline(%s) as offline", (fls_id,))
        is_offline = bool(offline_check and offline_check[0].get("offline"))
        actor_snapshot = query("""
            select a.id as actor_id, a.class, a.map, a.partition_id, a.dimension_index,
                   ((a.transform).location).x as x,
                   ((a.transform).location).y as y,
                   ((a.transform).location).z as z
            from dune.player_state ps
            join dune.actors a
              on a.id in (ps.player_controller_id, ps.player_state_id, ps.player_pawn_id)
            where ps.account_id=%s
            order by a.id
        """, (account_id,))
        plan = {
            "function": "dune.admin_move_offline_player_to_partition",
            "args": [fls_id, partition_id, target_location],
            "player": player[0],
            "targetPartition": partition[0],
            "currentActors": actor_snapshot,
            "executable": is_offline,
            "blockers": [] if is_offline else ["dune.is_player_offline(fls_id) is false; wait for Offline before moving"],
            "note": "Strict-offline teleport uses the first-party pawn-row move helper. Online/network-timeout automation is intentionally separate and not hidden behind this endpoint.",
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "accountId": account_id, "partitionId": partition_id, "plan": plan}
        self.require_mutations()
        require_confirmation(body, CONFIRM_PLAYER_RECOVERY)
        if not is_offline:
            raise ValueError("player is not fully Offline according to dune.is_player_offline")
        query("""
            select dune.admin_move_offline_player_to_partition(
                %s,
                %s,
                row(%s,%s,%s)::dune.vector
            )
        """, (
            fls_id,
            partition_id,
            target_location["x"], target_location["y"], target_location["z"],
        ))
        rows = query("""
            select a.id as actor_id, a.class, a.map, a.partition_id, a.dimension_index,
                   ((a.transform).location).x as x,
                   ((a.transform).location).y as y,
                   ((a.transform).location).z as z
            from dune.player_state ps
            join dune.actors a
              on a.id in (ps.player_controller_id, ps.player_state_id, ps.player_pawn_id)
            where ps.account_id=%s
            order by a.id
        """, (account_id,))
        return {
            "ok": True,
            "dryRun": False,
            "accountId": account_id,
            "partitionId": partition_id,
            "result": rows,
            "rollback": {
                "previousServerPartitionId": player[0].get("previous_server_partition_id"),
                "previousServerId": player[0].get("server_id"),
                "previousActors": actor_snapshot,
            },
        }

    def spice_field_inspect(self):
        errors = {}
        return {
            "caps": reference_query(errors, "spicefieldTypes", "select * from dune.spicefield_types order by map, field_kind_id"),
            "availability": reference_query(errors, "spicefieldAvailability", "select * from dune.spicefield_server_availability order by server_id, field_kind_id"),
            "resourceFields": reference_query(errors, "resourcefieldState", "select map,dimension_index,field_kind_id,count(*) as fields,min(value_remaining),max(value_remaining),sum(value_remaining) from dune.resourcefield_state group by 1,2,3 order by 1,2,3"),
            "typedKnob": read_typed_knobs().get("spiceDeepDesertCaps"),
            "errors": errors,
        }

    def progression_inspect(self, body):
        errors = {}
        account_id = body.get("account_id", body.get("accountId"))
        player = []
        faction = []
        reputation = []
        if account_id not in ("", None):
            player = reference_query(errors, "player", """
                select account_id, character_name, online_status::text, player_controller_id, player_pawn_id
                from dune.player_state
                where account_id=%s
            """, (int(account_id),))
            if player:
                pawn_id = player[0].get("player_pawn_id")
                faction = reference_query(errors, "faction", "select * from dune.player_faction where actor_id=%s order by faction_id", (pawn_id,))
                reputation = reference_query(errors, "reputation", "select * from dune.player_faction_reputation where actor_id=%s order by faction_id", (pawn_id,))
        functions = reference_query(errors, "functions", """
            select n.nspname as schema, p.proname as name,
                   pg_get_function_identity_arguments(p.oid) as args,
                   pg_get_function_result(p.oid) as result
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'dune'
              and (
                p.proname ilike '%%journey%%'
                or p.proname ilike '%%recipe%%'
                or p.proname ilike '%%vehicle%%'
                or p.proname ilike '%%faction%%'
                or p.proname ilike '%%reputation%%'
              )
            order by p.proname
            limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        tables = reference_query(errors, "tables", """
            select table_name, column_name, data_type, udt_name
            from information_schema.columns
            where table_schema='dune'
              and (
                table_name ilike '%%journey%%'
                or table_name ilike '%%recipe%%'
                or table_name ilike '%%vehicle%%'
                or table_name ilike '%%faction%%'
                or table_name ilike '%%reputation%%'
              )
            order by table_name, ordinal_position
            limit %s
        """, (ADMIN_REFERENCE_LIMIT * 5,))
        return {
            "player": player[0] if player else None,
            "faction": faction,
            "reputation": reputation,
            "functions": functions,
            "tables": tables,
            "mutators": {
                "factionReputation": {
                    "endpoint": "/api/admin/faction-reputation",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_REPUTATION_MUTATION,
                    "confidence": "moderate-to-high",
                },
                "playerFaction": {
                    "endpoint": "/api/admin/faction",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_FACTION_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_FACTION_MUTATION,
                    "confidence": "moderate",
                },
                "respawnLocation": {
                    "endpoint": "/api/admin/respawn-location",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_RESPAWN_MUTATION,
                    "actions": ["delete"],
                    "confidence": "moderate",
                },
                "journey": {
                    "endpoint": "/api/admin/journey",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_JOURNEY_MUTATION,
                    "actions": ["reveal", "complete", "reset", "delete"],
                    "confidence": "moderate",
                },
                "landsraad": {
                    "endpoint": "/api/admin/landsraad",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_LANDSRAAD_MUTATION,
                    "actions": ["change-end-time", "force-end"],
                    "confidence": "moderate",
                },
                "guild": {
                    "endpoint": "/api/admin/guild",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_GUILD_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_GUILD_MUTATION,
                    "actions": ["edit-description", "promote-member", "demote-member"],
                    "confidence": "moderate",
                },
                "marker": {
                    "endpoint": "/api/admin/marker",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_MARKER_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_MARKER_MUTATION,
                    "actions": ["delete-by-id", "delete-static-location"],
                    "confidence": "moderate",
                },
                "landclaim": {
                    "endpoint": "/api/admin/landclaim",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_LANDCLAIM_MUTATION,
                    "actions": ["add-segment"],
                    "confidence": "low-to-moderate",
                },
                "exchangeSolari": {
                    "endpoint": "/api/admin/exchange",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_EXCHANGE_MUTATION,
                    "actions": ["add", "set"],
                    "confidence": "moderate",
                },
                "playerTags": {
                    "endpoint": "/api/admin/player-tags",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_PLAYER_TAG_MUTATION,
                    "actions": ["add-remove"],
                    "confidence": "moderate",
                },
                "accessCodes": {
                    "endpoint": "/api/admin/access-code",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_ACCESS_CODE_MUTATION,
                    "actions": ["create", "delete", "reset"],
                    "confidence": "moderate",
                },
                "communinet": {
                    "endpoint": "/api/admin/communinet",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_COMMUNINET_MUTATION,
                    "actions": ["update-data", "update-channel", "remove-channel"],
                    "confidence": "moderate",
                },
                "tutorial": {
                    "endpoint": "/api/admin/tutorial",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_TUTORIAL_MUTATION,
                    "actions": ["set-state"],
                    "confidence": "moderate",
                },
                "permission": {
                    "endpoint": "/api/admin/permission",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_PERMISSION_MUTATION,
                    "actions": ["set-name", "set-access-level", "set-player-rank", "remove-player-rank"],
                    "confidence": "moderate",
                },
                "vendor": {
                    "endpoint": "/api/admin/vendor",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_VENDOR_MUTATION,
                    "actions": ["set-cycle-timestamp"],
                    "confidence": "moderate",
                },
                "journeyRecipeVehicle": {
                    "status": "inspect-only",
                    "reason": "Recipe and vehicle function signatures can be discovered here, but writes stay blocked until safe contracts and live examples are mapped.",
                },
            },
            "errors": errors,
        }

    def world_state_inspect(self, body):
        errors = {}
        account_id = body.get("account_id", body.get("accountId"))
        player_id = body.get("player_id", body.get("playerId"))
        guild_id = body.get("guild_id", body.get("guildId"))
        if account_id not in ("", None) and player_id in ("", None):
            player_rows = reference_query(errors, "playerForAccount", """
                select account_id, character_name, online_status::text, player_pawn_id
                from dune.player_state
                where account_id=%s
            """, (int(account_id),))
            if player_rows:
                player_id = player_rows[0].get("player_pawn_id")
        if player_id not in ("", None) and guild_id in ("", None):
            guild_rows = reference_query(errors, "guildForPlayer", "select dune.get_guild_for_player(%s) as guild_id", (int(player_id),))
            if guild_rows:
                guild_id = guild_rows[0].get("guild_id")
        guild = []
        guild_members = []
        guild_invites = []
        if guild_id not in ("", None):
            guild = reference_query(errors, "guild", "select * from dune.get_guild_data(%s)", (int(guild_id),))
            guild_members = reference_query(errors, "guildMembers", "select * from dune.get_guild_members(%s) order by role_id, player_id", (int(guild_id),))
            guild_invites = reference_query(errors, "guildInvites", "select * from dune.get_guild_invites(%s) order by invite_sent_timespan desc limit %s", (int(guild_id), ADMIN_REFERENCE_LIMIT))
        marker_counts = reference_query(errors, "markerCounts", """
            select 'markers' as table_name, count(*) as rows from dune.markers
            union all select 'player_markers', count(*) from dune.player_markers
            union all select 'landclaim_segments', count(*) from dune.landclaim_segments
        """)
        recent_markers = reference_query(errors, "recentMarkers", """
            select m.marker_hash_id, m.dimension_index, mn.map_name, m.area_id, m.area_radius, m.long_range, m.payload,
                   count(pm.player_id) as player_marker_count
            from dune.markers m
            left join dune.map_names mn on mn.map_name_id = m.map_name_id
            left join dune.player_markers pm on pm.marker_hash_id=m.marker_hash_id and pm.dimension_index=m.dimension_index
            group by m.marker_hash_id, m.dimension_index, mn.map_name, m.area_id, m.area_radius, m.long_range, m.payload
            order by m.marker_hash_id desc
            limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        landclaim_segments = reference_query(errors, "landclaimSegments", """
            select * from dune.landclaim_segments order by totem_id, grid_location_x, grid_location_y limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        permission_actors = reference_query(errors, "permissionActors", """
            select pa.*, count(par.player_id) as rank_count
            from dune.permission_actor pa
            left join dune.permission_actor_rank par on par.permission_actor_id=pa.actor_id
            group by pa.actor_id, pa.actor_name, pa.actor_type, pa.access_level, pa.is_child
            order by pa.actor_id
            limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        vehicles = []
        respawns = []
        if account_id not in ("", None):
            vehicles = reference_query(errors, "playerVehicles", """
                select * from dune.get_player_owned_vehicles_data(%s, %s)
                order by out_actor_id
                limit %s
            """, (int(player_id or 0), int(account_id), ADMIN_REFERENCE_LIMIT))
            respawns = reference_query(errors, "respawnLocations", """
                select * from dune.player_respawn_locations
                where account_id=%s
                order by last_used_timestamp desc nulls last
                limit %s
            """, (int(account_id), ADMIN_REFERENCE_LIMIT))
        functions = reference_query(errors, "functions", """
            select n.nspname as schema, p.proname as name,
                   pg_get_function_identity_arguments(p.oid) as args,
                   pg_get_function_result(p.oid) as result
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'dune'
              and (
                p.proname ilike '%%guild%%'
                or p.proname ilike '%%vehicle%%'
                or p.proname ilike '%%landclaim%%'
                or p.proname ilike '%%marker%%'
                or p.proname ilike '%%recipe%%'
                or p.proname ilike '%%respawn%%'
              )
            order by p.proname
            limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        tables = reference_query(errors, "tables", """
            select table_name, column_name, data_type, udt_name
            from information_schema.columns
            where table_schema='dune'
              and (
                table_name ilike '%%guild%%'
                or table_name ilike '%%vehicle%%'
                or table_name ilike '%%landclaim%%'
                or table_name ilike '%%marker%%'
                or table_name ilike '%%recipe%%'
                or table_name ilike '%%respawn%%'
              )
            order by table_name, ordinal_position
            limit %s
        """, (ADMIN_REFERENCE_LIMIT * 5,))
        return {
            "accountId": int(account_id) if account_id not in ("", None) else None,
            "playerId": int(player_id) if player_id not in ("", None) else None,
            "guildId": int(guild_id) if guild_id not in ("", None) else None,
            "guild": guild[0] if guild else None,
            "guildMembers": guild_members,
            "guildInvites": guild_invites,
            "markerCounts": marker_counts,
            "recentMarkers": recent_markers,
            "landclaimSegments": landclaim_segments,
            "permissionActors": permission_actors,
            "vehicles": vehicles,
            "respawnLocations": respawns,
            "functions": functions,
            "tables": tables,
            "mutators": {
                "guild": {
                    "endpoint": "/api/admin/guild",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_GUILD_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_GUILD_MUTATION,
                    "actions": ["edit-description", "promote-member", "demote-member"],
                    "confidence": "moderate",
                },
                "respawnLocation": {
                    "endpoint": "/api/admin/respawn-location",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_RESPAWN_MUTATION,
                    "actions": ["delete"],
                    "confidence": "moderate",
                },
                "marker": {
                    "endpoint": "/api/admin/marker",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_MARKER_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_MARKER_MUTATION,
                    "actions": ["delete-by-id", "delete-static-location"],
                    "confidence": "moderate",
                },
                "landclaim": {
                    "endpoint": "/api/admin/landclaim",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_LANDCLAIM_MUTATION,
                    "actions": ["add-segment"],
                    "confidence": "low-to-moderate",
                },
                "permission": {
                    "endpoint": "/api/admin/permission",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_PERMISSION_MUTATION,
                    "actions": ["set-name", "set-access-level", "set-player-rank", "remove-player-rank"],
                    "confidence": "moderate",
                },
                "vehicleRecipeMarkerLandclaim": {
                    "status": "inspect-only",
                    "reason": "Functions and tables are cataloged here, but writes stay blocked until transform/serverinfo/composite semantics and rollback are proven.",
                },
            },
            "errors": errors,
        }

    def economy_inspect(self, body):
        errors = {}
        account_id = body.get("account_id", body.get("accountId"))
        player_id = body.get("player_id", body.get("playerId"))
        owner_id = body.get("owner_id", body.get("ownerId", player_id))
        controller_id = body.get("controller_id", body.get("controllerId"))
        exchange_id = body.get("exchange_id", body.get("exchangeId"))
        if account_id not in ("", None) and player_id in ("", None):
            player_rows = reference_query(errors, "playerForAccount", """
                select account_id, character_name, online_status::text, player_controller_id, player_pawn_id
                from dune.player_state
                where account_id=%s
            """, (int(account_id),))
            if player_rows:
                player_id = player_rows[0].get("player_pawn_id")
                controller_id = controller_id or player_rows[0].get("player_controller_id")
                owner_id = owner_id or player_id
        exchange_users = []
        exchange_balance = []
        if owner_id not in ("", None):
            exchange_users = reference_query(errors, "exchangeUsers", "select * from dune.dune_exchange_users where owner_id=%s", (int(owner_id),))
            exchange_balance = reference_query(errors, "exchangeBalance", "select dune.dune_exchange_retrieve_solari_balance(%s) as solari_balance", (int(owner_id),))
        exchange_orders = []
        if owner_id not in ("", None):
            exchange_orders = reference_query(errors, "exchangeOrdersByOwner", """
                select * from dune.dune_exchange_orders where owner_id=%s order by id desc limit %s
            """, (int(owner_id), ADMIN_REFERENCE_LIMIT))
        elif exchange_id not in ("", None):
            exchange_orders = reference_query(errors, "exchangeOrdersByExchange", """
                select * from dune.dune_exchange_orders where exchange_id=%s order by id desc limit %s
            """, (int(exchange_id), ADMIN_REFERENCE_LIMIT))
        counts = reference_query(errors, "economyCounts", """
            select 'dune_exchange_orders' as table_name, count(*) as rows from dune.dune_exchange_orders
            union all select 'dune_exchange_users', count(*) from dune.dune_exchange_users
            union all select 'vehicles', count(*) from dune.vehicles
            union all select 'vehicle_modules', count(*) from dune.vehicle_modules
            union all select 'recovered_vehicles', count(*) from dune.recovered_vehicles
            union all select 'backup_vehicles', count(*) from dune.backup_vehicles
            union all select 'base_backups', count(*) from dune.base_backups
        """)
        recovered = []
        backup_vehicle = []
        if account_id not in ("", None):
            recovered = reference_query(errors, "recoveredVehicles", "select * from dune.load_recovered_vehicles(%s, %s) limit %s", (int(account_id), 0, ADMIN_REFERENCE_LIMIT))
            backup_vehicle = reference_query(errors, "backupVehicle", "select * from dune.load_backup_vehicle(%s) limit %s", (int(account_id), ADMIN_REFERENCE_LIMIT))
        base_backups = []
        if player_id not in ("", None):
            base_backups = reference_query(errors, "baseBackups", "select * from dune.base_backup_get_available_backups(%s) limit %s", (int(player_id), ADMIN_REFERENCE_LIMIT))
        functions = reference_query(errors, "functions", """
            select n.nspname as schema, p.proname as name,
                   pg_get_function_identity_arguments(p.oid) as args,
                   pg_get_function_result(p.oid) as result
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'dune'
              and (
                p.proname ilike '%%exchange%%'
                or p.proname ilike '%%vehicle%%'
                or p.proname ilike '%%backup%%'
                or p.proname ilike '%%contract%%'
              )
            order by p.proname
            limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        tables = reference_query(errors, "tables", """
            select table_name, column_name, data_type, udt_name
            from information_schema.columns
            where table_schema='dune'
              and (
                table_name ilike '%%exchange%%'
                or table_name ilike '%%vehicle%%'
                or table_name ilike '%%backup%%'
                or table_name ilike '%%contract%%'
              )
            order by table_name, ordinal_position
            limit %s
        """, (ADMIN_REFERENCE_LIMIT * 5,))
        return {
            "accountId": int(account_id) if account_id not in ("", None) else None,
            "playerId": int(player_id) if player_id not in ("", None) else None,
            "ownerId": int(owner_id) if owner_id not in ("", None) else None,
            "controllerId": int(controller_id) if controller_id not in ("", None) else None,
            "exchangeId": int(exchange_id) if exchange_id not in ("", None) else None,
            "exchangeUsers": exchange_users,
            "exchangeBalance": exchange_balance[0] if exchange_balance else None,
            "exchangeOrders": exchange_orders,
            "counts": counts,
            "recoveredVehicles": recovered,
            "backupVehicle": backup_vehicle,
            "baseBackups": base_backups,
            "functions": functions,
            "tables": tables,
            "mutators": {
                "exchangeSolari": {
                    "endpoint": "/api/admin/exchange",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_EXCHANGE_MUTATION,
                    "actions": ["add", "set"],
                    "confidence": "moderate",
                },
                "exchangeOrdersVehiclesBaseBackups": {
                    "status": "inspect-only",
                    "reason": "Order, vehicle restore, and base backup functions require inventory/serverinfo/transform/composite semantics and stronger rollback mapping.",
                },
            },
            "errors": errors,
        }

    def player_lifecycle_inspect(self, body):
        errors = {}
        account_id = body.get("account_id", body.get("accountId"))
        player_id = body.get("player_id", body.get("playerId"))
        if account_id not in ("", None) and player_id in ("", None):
            player_rows = reference_query(errors, "playerForAccount", """
                select account_id, character_name, online_status::text, player_controller_id, player_pawn_id
                from dune.player_state
                where account_id=%s
            """, (int(account_id),))
            if player_rows:
                player_id = player_rows[0].get("player_pawn_id")
        account = []
        player = []
        tags = []
        access_codes = []
        communinet = []
        tutorials = []
        vendor_cycles = []
        party = []
        party_invites = []
        if account_id not in ("", None):
            account = reference_query(errors, "account", "select id, \"user\", funcom_id, takeoverable, platform_id, platform_name from dune.accounts where id=%s", (int(account_id),))
            player = reference_query(errors, "player", "select * from dune.player_state where account_id=%s", (int(account_id),))
            tags = reference_query(errors, "playerTags", "select * from dune.admin_read_player_tags(%s)", (int(account_id),))
            access_codes = reference_query(errors, "accessCodes", "select * from dune.get_player_access_codes(%s) order by access_code_type, access_code", (int(account_id),))
            communinet = reference_query(errors, "communinet", "select * from dune.load_communinet_player_data(%s)", (int(account_id),))
        if player_id not in ("", None):
            tutorials = reference_query(errors, "tutorials", "select * from dune.get_all_tutorial_entries(%s) order by tutorial_id", (int(player_id),))
            vendor_cycles = reference_query(errors, "vendorCycles", "select * from dune.vendor_stock_cycle where player_id=%s order by vendor_id limit %s", (int(player_id), ADMIN_REFERENCE_LIMIT))
            party = reference_query(errors, "partyMembers", """
                select pm.*, ps.character_name
                from dune.party_members pm
                left join dune.player_state ps on ps.player_pawn_id=pm.player_id
                where pm.party_id in (select party_id from dune.party_members where player_id=%s)
                order by pm.party_id, pm.player_id
            """, (int(player_id),))
            party_invites = reference_query(errors, "partyInvites", """
                select * from dune.get_all_party_invites()
                where sender_player_id=%s or player_id=%s
                order by invite_sent_timespan desc
                limit %s
            """, (int(player_id), int(player_id), ADMIN_REFERENCE_LIMIT))
        counts = reference_query(errors, "lifecycleCounts", """
            select 'accounts' as table_name, count(*) as rows from dune.accounts
            union all select 'player_state', count(*) from dune.player_state
            union all select 'parties', count(*) from dune.parties
            union all select 'party_members', count(*) from dune.party_members
            union all select 'party_invites', count(*) from dune.party_invites
            union all select 'player_tags', count(*) from dune.player_tags
            union all select 'player_access_codes', count(*) from dune.player_access_codes
            union all select 'communinet_player', count(*) from dune.communinet_player
            union all select 'communinet_player_channels', count(*) from dune.communinet_player_channels
            union all select 'tutorial_per_player', count(*) from dune.tutorial_per_player
            union all select 'overmap_players', count(*) from dune.overmap_players
            union all select 'dungeon_completion_players', count(*) from dune.dungeon_completion_players
            union all select 'vendor_stock_state', count(*) from dune.vendor_stock_state
            union all select 'vendor_stock_cycle', count(*) from dune.vendor_stock_cycle
            union all select 'tax_invoice', count(*) from dune.tax_invoice
            union all select 'landsraad_task_progress_player', count(*) from dune.landsraad_task_progress_player
            union all select 'landsraad_task_player_contributions', count(*) from dune.landsraad_task_player_contributions
            union all select 'permission_actor', count(*) from dune.permission_actor
        """)
        functions = reference_query(errors, "functions", """
            select n.nspname as schema, p.proname as name,
                   pg_get_function_identity_arguments(p.oid) as args,
                   pg_get_function_result(p.oid) as result
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'dune'
              and (
                p.proname ilike '%%party%%'
                or p.proname ilike '%%account%%'
                or p.proname ilike '%%player%%'
                or p.proname ilike '%%communinet%%'
                or p.proname ilike '%%access_code%%'
                or p.proname ilike '%%tag%%'
                or p.proname ilike '%%dungeon%%'
                or p.proname ilike '%%tutorial%%'
              )
            order by p.proname
            limit %s
        """, (ADMIN_REFERENCE_LIMIT,))
        tables = reference_query(errors, "tables", """
            select table_name, column_name, data_type, udt_name
            from information_schema.columns
            where table_schema='dune'
              and (
                table_name ilike '%%party%%'
                or table_name ilike '%%account%%'
                or table_name ilike '%%player%%'
                or table_name ilike '%%communinet%%'
                or table_name ilike '%%access_code%%'
                or table_name ilike '%%tag%%'
                or table_name ilike '%%dungeon%%'
                or table_name ilike '%%tutorial%%'
              )
            order by table_name, ordinal_position
            limit %s
        """, (ADMIN_REFERENCE_LIMIT * 5,))
        return {
            "accountId": int(account_id) if account_id not in ("", None) else None,
            "playerId": int(player_id) if player_id not in ("", None) else None,
            "account": account[0] if account else None,
            "player": player[0] if player else None,
            "tags": tags,
            "accessCodes": access_codes,
            "communinet": communinet,
            "tutorials": tutorials,
            "vendorCycles": vendor_cycles,
            "party": party,
            "partyInvites": party_invites,
            "counts": counts,
            "functions": functions,
            "tables": tables,
            "mutators": {
                "playerTags": {
                    "endpoint": "/api/admin/player-tags",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_PLAYER_TAG_MUTATION,
                    "actions": ["add-remove"],
                    "confidence": "moderate",
                },
                "accessCodes": {
                    "endpoint": "/api/admin/access-code",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_ACCESS_CODE_MUTATION,
                    "actions": ["create", "delete", "reset"],
                    "confidence": "moderate",
                },
                "communinet": {
                    "endpoint": "/api/admin/communinet",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_COMMUNINET_MUTATION,
                    "actions": ["update-data", "update-channel", "remove-channel"],
                    "confidence": "moderate",
                },
                "tutorial": {
                    "endpoint": "/api/admin/tutorial",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_TUTORIAL_MUTATION,
                    "actions": ["set-state"],
                    "confidence": "moderate",
                },
                "vendor": {
                    "endpoint": "/api/admin/vendor",
                    "defaultDryRun": True,
                    "executionGate": "DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED",
                    "confirm": CONFIRM_VENDOR_MUTATION,
                    "actions": ["set-cycle-timestamp"],
                    "confidence": "moderate",
                },
                "partyAccountCommuninet": {
                    "status": "inspect-only",
                    "reason": "Party membership, account takeover/deletion, vendor, dungeon, tutorial, lore, overmap, Coriolis, and player save functions remain blocked pending lifecycle and rollback validation.",
                },
            },
            "errors": errors,
        }

    def resolve_player_identity(self, account_id):
        rows = query("""
            select ps.account_id, ps.character_name, ps.online_status::text,
                   ps.player_controller_id, ps.player_pawn_id,
                   a.funcom_id, a."user" as fls_id
            from dune.player_state ps
            left join dune.accounts a on a.id = ps.account_id
            where ps.account_id=%s
        """, (int(account_id),))
        if not rows:
            raise ValueError("account_id not found")
        player = rows[0]
        fls_id = str(player.get("fls_id") or player.get("funcom_id") or "").strip()
        if not fls_id:
            raise ValueError("player account has no FLS/user id")
        return player, fls_id

    def journey_mutation(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        action = str(body.get("action", "")).strip().lower()
        if action not in ("reveal", "complete", "reset", "delete"):
            raise ValueError("action must be reveal, complete, reset, or delete")
        story_node_ids = body.get("story_node_ids", body.get("storyNodeIds", body.get("story_node_id", body.get("storyNodeId", []))))
        if isinstance(story_node_ids, str):
            story_node_ids = [part.strip() for part in story_node_ids.split(",") if part.strip()]
        if not isinstance(story_node_ids, list) or not story_node_ids:
            raise ValueError("story_node_ids must be a non-empty list")
        story_node_ids = [str(item).strip() for item in story_node_ids if str(item).strip()]
        if not story_node_ids:
            raise ValueError("story_node_ids must contain at least one non-empty id")
        if len(story_node_ids) > 100:
            raise ValueError("story_node_ids is limited to 100 entries per request")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        player, fls_id = self.resolve_player_identity(account_id)
        details = []
        errors = {}
        for story_node_id in story_node_ids[:20]:
            rows = reference_query(errors, f"journey:{story_node_id}", "select * from dune.admin_get_journey_details(%s,%s)", (fls_id, story_node_id))
            details.append({"storyNodeId": story_node_id, "details": rows})
        function_by_action = {
            "reveal": "reveal_journey_story_nodes_for_player",
            "complete": "complete_journey_story_nodes_for_player",
            "reset": "reset_journey_story_nodes_for_player",
            "delete": "delete_journey_story_nodes_for_player",
        }
        function_name = function_by_action[action]
        functions = query("""
            select p.proname as name, pg_get_function_identity_arguments(p.oid) as args
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname='dune' and p.proname=%s
        """, (function_name,))
        if not functions:
            raise ValueError(f"dune.{function_name} is not available")
        plan = {
            "function": f"dune.{function_name}",
            "args": [fls_id, story_node_ids],
            "player": player,
            "preflightDetails": details,
            "errors": errors,
            "onlineExecutionBlocked": str(player.get("online_status") or "").lower() == "online",
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "accountId": account_id, "action": action, "storyNodeIds": story_node_ids, "plan": plan, "executionGate": "DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED", "confirm": CONFIRM_JOURNEY_MUTATION}
        self.require_mutations()
        if not JOURNEY_MUTATIONS_ENABLED:
            raise PermissionError("journey mutations are disabled; set DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_JOURNEY_MUTATION)
        if str(player.get("online_status") or "").lower() == "online":
            raise ValueError("player is online; journey execution refuses online targets")
        execute(f"select dune.{function_name}(%s,%s::text[])", (fls_id, story_node_ids))
        after = []
        after_errors = {}
        for story_node_id in story_node_ids[:20]:
            rows = reference_query(after_errors, f"journey:{story_node_id}", "select * from dune.admin_get_journey_details(%s,%s)", (fls_id, story_node_id))
            after.append({"storyNodeId": story_node_id, "details": rows})
        return {"ok": True, "dryRun": False, "accountId": account_id, "action": action, "storyNodeIds": story_node_ids, "before": details, "after": after, "errors": after_errors, "rollback": "Use the opposite journey action where meaningful; reset/delete can remove progress, reveal/complete can reapply it."}

    def faction_reputation_mutation(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        faction_id = int(body.get("faction_id", body.get("factionId")))
        amount = int(body.get("amount", body.get("reputation", 0)))
        mode = str(body.get("mode", "add")).strip().lower()
        if mode not in ("add", "set"):
            raise ValueError("mode must be add or set")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        player = query("""
            select account_id, character_name, online_status::text, player_pawn_id
            from dune.player_state
            where account_id=%s
        """, (account_id,))
        if not player:
            raise ValueError("account_id not found")
        actor_id = int(player[0]["player_pawn_id"])
        columns = query("""
            select column_name
            from information_schema.columns
            where table_schema='dune' and table_name='player_faction_reputation'
            order by ordinal_position
        """)
        column_names = {row["column_name"] for row in columns}
        required = {"actor_id", "faction_id"}
        if not required.issubset(column_names):
            raise ValueError("player_faction_reputation does not expose actor_id and faction_id columns")
        value_column = next((name for name in ("reputation", "reputation_amount", "amount", "value") if name in column_names), None)
        if not value_column:
            raise ValueError("player_faction_reputation reputation value column is not recognized")
        current_rows = query(f"select * from dune.player_faction_reputation where actor_id=%s and faction_id=%s", (actor_id, faction_id))
        current_value = int(current_rows[0].get(value_column) or 0) if current_rows else 0
        new_value = amount if mode == "set" else current_value + amount
        functions = query("""
            select p.proname as name, pg_get_function_identity_arguments(p.oid) as args
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname='dune' and p.proname in ('set_player_faction_reputation', 'get_player_current_faction_reputation')
            order by p.proname
        """)
        function_names = {row["name"] for row in functions}
        setter_available = "set_player_faction_reputation" in function_names
        getter_available = "get_player_current_faction_reputation" in function_names
        plan = {
            "function": "dune.set_player_faction_reputation" if setter_available else None,
            "table": "dune.player_faction_reputation",
            "key": {"actor_id": actor_id, "faction_id": faction_id},
            "valueColumn": value_column,
            "currentRows": current_rows,
            "currentValue": current_value,
            "newValue": new_value,
            "operation": "call server function" if setter_available else "blocked; setter function missing",
            "availableFunctions": functions,
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "accountId": account_id, "actorId": actor_id, "factionId": faction_id, "mode": mode, "plan": plan, "executionGate": "DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED", "confidence": "moderate-to-high" if setter_available and getter_available else "moderate"}
        self.require_mutations()
        if not REPUTATION_MUTATIONS_ENABLED:
            raise PermissionError("reputation mutations are disabled; set DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_REPUTATION_MUTATION)
        if not setter_available:
            raise ValueError("dune.set_player_faction_reputation is not available; refusing raw table mutation")
        execute("select dune.set_player_faction_reputation(%s,%s,%s)", (actor_id, faction_id, new_value))
        after = query("select * from dune.player_faction_reputation where actor_id=%s and faction_id=%s", (actor_id, faction_id))
        return {"ok": True, "dryRun": False, "accountId": account_id, "actorId": actor_id, "factionId": faction_id, "mode": mode, "before": current_rows, "after": after, "rollback": {"mode": "set", "amount": current_value, "confirm": CONFIRM_REPUTATION_MUTATION}}

    def faction_change_mutation(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        faction_id = int(body.get("faction_id", body.get("factionId")))
        neutral_faction_id = int(body.get("neutral_faction_id", body.get("neutralFactionId", 3)))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        player, _ = self.resolve_player_identity(account_id)
        actor_id = int(player["player_pawn_id"])
        factions = query("select id, name from dune.factions order by id")
        faction_ids = {int(row["id"]) for row in factions}
        if faction_id not in faction_ids:
            raise ValueError("faction_id is not present in dune.factions")
        if neutral_faction_id not in faction_ids:
            raise ValueError("neutral_faction_id is not present in dune.factions")
        current_rows = query("select * from dune.player_faction where actor_id=%s", (actor_id,))
        current_faction = query("select dune.get_player_faction(%s::bigint,%s::smallint) as faction_id", (actor_id, neutral_faction_id))
        current_faction_id = int(current_faction[0].get("faction_id") or neutral_faction_id) if current_faction else neutral_faction_id
        functions = query("""
            select p.proname as name, pg_get_function_identity_arguments(p.oid) as args
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname='dune' and p.proname in ('change_player_faction', 'get_player_faction', 'handle_player_faction_guild_effects', 'clean_guild_invites_with_incompatible_faction')
            order by p.proname
        """)
        function_names = {row["name"] for row in functions}
        if "change_player_faction" not in function_names:
            raise ValueError("dune.change_player_faction is not available")
        plan = {
            "function": "dune.change_player_faction",
            "args": [actor_id, faction_id, neutral_faction_id, "current UTC timestamp"],
            "player": player,
            "factions": factions,
            "currentRows": current_rows,
            "currentFactionId": current_faction_id,
            "newFactionId": faction_id,
            "availableFunctions": functions,
            "onlineExecutionBlocked": str(player.get("online_status") or "").lower() == "online",
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "accountId": account_id, "actorId": actor_id, "factionId": faction_id, "plan": plan, "executionGate": "DUNE_ADMIN_FACTION_MUTATIONS_ENABLED", "confirm": CONFIRM_FACTION_MUTATION}
        self.require_mutations()
        if not FACTION_MUTATIONS_ENABLED:
            raise PermissionError("faction mutations are disabled; set DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_FACTION_MUTATION)
        if str(player.get("online_status") or "").lower() == "online":
            raise ValueError("player is online; faction execution refuses online targets")
        execute("select dune.change_player_faction(%s::bigint,%s::smallint,%s::smallint, timezone('utc', now())::timestamp)", (actor_id, faction_id, neutral_faction_id))
        after = query("select * from dune.player_faction where actor_id=%s", (actor_id,))
        return {"ok": True, "dryRun": False, "accountId": account_id, "actorId": actor_id, "factionId": faction_id, "before": current_rows, "after": after, "rollback": {"faction_id": current_faction_id, "neutral_faction_id": neutral_faction_id, "confirm": CONFIRM_FACTION_MUTATION}}

    def guild_mutation(self, body):
        action = str(body.get("action", "")).strip().lower()
        if action not in ("edit-description", "promote-member", "demote-member"):
            raise ValueError("action must be edit-description, promote-member, or demote-member")
        guild_id = int(body.get("guild_id", body.get("guildId")))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        guild_rows = query("select * from dune.guilds where guild_id=%s", (guild_id,))
        if not guild_rows:
            raise ValueError("guild_id not found")
        before = {"guild": guild_rows[0], "members": query("select * from dune.guild_members where guild_id=%s order by role_id, player_id", (guild_id,))}
        plan = {"action": action, "guildId": guild_id, "before": before}
        player_id = None
        if action == "edit-description":
            description = str(body.get("description", body.get("guild_description", body.get("guildDescription", ""))))
            if len(description) > 2048:
                raise ValueError("description must be 2048 characters or less")
            plan.update({
                "function": "dune.edit_guild_description",
                "args": [guild_id, description],
                "rollback": {"action": "edit-description", "guild_id": guild_id, "description": guild_rows[0].get("guild_description"), "confirm": CONFIRM_GUILD_MUTATION},
            })
        else:
            player_id = int(body.get("player_id", body.get("playerId")))
            new_role = int(body.get("new_role", body.get("newRole")))
            if new_role < 0 or new_role > 32767:
                raise ValueError("new_role must fit a smallint")
            member_rows = [row for row in before["members"] if int(row.get("player_id")) == player_id]
            if not member_rows:
                raise ValueError("player_id is not a member of guild_id")
            function_name = "dune.promote_guild_member" if action == "promote-member" else "dune.demote_guild_member"
            plan.update({
                "function": function_name,
                "args": [guild_id, player_id, new_role],
                "previousRole": member_rows[0].get("role_id"),
                "rollback": {"action": action, "guild_id": guild_id, "player_id": player_id, "new_role": member_rows[0].get("role_id"), "confirm": CONFIRM_GUILD_MUTATION},
            })
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "guildId": guild_id, "playerId": player_id, "plan": plan, "executionGate": "DUNE_ADMIN_GUILD_MUTATIONS_ENABLED", "confirm": CONFIRM_GUILD_MUTATION}
        self.require_mutations()
        if not GUILD_MUTATIONS_ENABLED:
            raise PermissionError("guild mutations are disabled; set DUNE_ADMIN_GUILD_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_GUILD_MUTATION)
        if action == "edit-description":
            execute("select dune.edit_guild_description(%s,%s)", (guild_id, plan["args"][1]))
        elif action == "promote-member":
            execute("select dune.promote_guild_member(%s,%s,%s::smallint)", (guild_id, player_id, plan["args"][2]))
        else:
            execute("select dune.demote_guild_member(%s,%s,%s::smallint)", (guild_id, player_id, plan["args"][2]))
        after = {"guild": query("select * from dune.guilds where guild_id=%s", (guild_id,)), "members": query("select * from dune.guild_members where guild_id=%s order by role_id, player_id", (guild_id,))}
        return {"ok": True, "dryRun": False, "action": action, "guildId": guild_id, "playerId": player_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def parse_int_list(self, value, field_name):
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
        elif isinstance(value, list):
            parts = value
        else:
            parts = []
        result = [int(part) for part in parts]
        if not result:
            raise ValueError(f"{field_name} is required")
        return result

    def parse_text_list(self, value, field_name):
        if isinstance(value, str):
            result = [part.strip() for part in value.split(",") if part.strip()]
        elif isinstance(value, list):
            result = [str(part).strip() for part in value if str(part).strip()]
        else:
            result = []
        if not result:
            raise ValueError(f"{field_name} is required")
        return result

    def marker_mutation(self, body):
        action = str(body.get("action", "")).strip().lower()
        if action not in ("delete-by-id", "delete-static-location"):
            raise ValueError("action must be delete-by-id or delete-static-location")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        if action == "delete-by-id":
            marker_ids = self.parse_int_list(body.get("marker_ids", body.get("markerIds")), "marker_ids")
            marker_rows = query("""
                select m.*, mn.map_name
                from dune.markers m
                left join dune.map_names mn on mn.map_name_id = m.map_name_id
                where m.marker_hash_id = any(%s::integer[])
                order by m.marker_hash_id, m.dimension_index
            """, (marker_ids,))
            plan = {
                "action": action,
                "function": "dune.delete_markers_by_id",
                "args": [marker_ids],
                "markers": marker_rows,
                "rollback": "No automatic rollback; preserve marker/player_marker rows from dry-run/audit before execution.",
            }
            marker_count = len(marker_ids)
            key_count = 0
        else:
            keys = self.parse_text_list(body.get("static_location_keys", body.get("staticLocationKeys")), "static_location_keys")
            marker_rows = query("select * from dune.markers where payload::text = any(%s::text[]) or payload::text like any(%s::text[]) limit %s", (keys, [f"%{key}%" for key in keys], ADMIN_REFERENCE_LIMIT))
            plan = {
                "action": action,
                "function": "dune.delete_static_location_markers",
                "args": [keys],
                "candidateMarkers": marker_rows,
                "rollback": "No automatic rollback; static marker recreation semantics are not mapped.",
            }
            marker_count = 0
            key_count = len(keys)
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "markerCount": marker_count, "keyCount": key_count, "plan": plan, "executionGate": "DUNE_ADMIN_MARKER_MUTATIONS_ENABLED", "confirm": CONFIRM_MARKER_MUTATION}
        self.require_mutations()
        if not MARKER_MUTATIONS_ENABLED:
            raise PermissionError("marker mutations are disabled; set DUNE_ADMIN_MARKER_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_MARKER_MUTATION)
        if action == "delete-by-id":
            execute("select dune.delete_markers_by_id(%s::integer[])", (plan["args"][0],))
        else:
            execute("select dune.delete_static_location_markers(%s::text[])", (plan["args"][0],))
        return {"ok": True, "dryRun": False, "action": action, "markerCount": marker_count, "keyCount": key_count, "before": plan, "rollback": plan["rollback"]}

    def landclaim_mutation(self, body):
        action = str(body.get("action", "add-segment")).strip().lower()
        if action != "add-segment":
            raise ValueError("only add-segment is supported for landclaim")
        totem_id = int(body.get("totem_id", body.get("totemId")))
        grid_x = int(body.get("grid_location_x", body.get("gridX")))
        grid_y = int(body.get("grid_location_y", body.get("gridY")))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before = query("select * from dune.get_landclaim_segments(%s) order by grid_location_x, grid_location_y", (totem_id,))
        duplicate = [row for row in before if int(row.get("grid_location_x")) == grid_x and int(row.get("grid_location_y")) == grid_y]
        if duplicate:
            raise ValueError("landclaim segment already exists for this totem/grid coordinate")
        plan = {
            "action": action,
            "function": "dune.add_landclaim_segment",
            "args": [totem_id, grid_x, grid_y],
            "before": before,
            "rollback": "No delete function is mapped; take a DB backup before execution.",
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "totemId": totem_id, "gridX": grid_x, "gridY": grid_y, "plan": plan, "executionGate": "DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED", "confirm": CONFIRM_LANDCLAIM_MUTATION}
        self.require_mutations()
        if not LANDCLAIM_MUTATIONS_ENABLED:
            raise PermissionError("landclaim mutations are disabled; set DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_LANDCLAIM_MUTATION)
        execute("select dune.add_landclaim_segment(%s,%s,%s)", (totem_id, grid_x, grid_y))
        after = query("select * from dune.get_landclaim_segments(%s) order by grid_location_x, grid_location_y", (totem_id,))
        return {"ok": True, "dryRun": False, "action": action, "totemId": totem_id, "gridX": grid_x, "gridY": grid_y, "before": before, "after": after, "rollback": plan["rollback"]}

    def exchange_mutation(self, body):
        owner_id = int(body.get("owner_id", body.get("ownerId")))
        controller_id = int(body.get("controller_id", body.get("controllerId", owner_id)))
        amount = int(body.get("amount", 0))
        mode = str(body.get("mode", "add")).strip().lower()
        if mode not in ("add", "set"):
            raise ValueError("mode must be add or set")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before_rows = query("select dune.dune_exchange_retrieve_solari_balance(%s) as solari_balance", (owner_id,))
        before_balance = int((before_rows[0] if before_rows else {}).get("solari_balance") or 0)
        delta = amount if mode == "add" else amount - before_balance
        plan = {
            "function": "dune.dune_exchange_modify_user_solari_balance",
            "args": [controller_id, delta],
            "ownerId": owner_id,
            "controllerId": controller_id,
            "mode": mode,
            "amount": amount,
            "beforeBalance": before_balance,
            "delta": delta,
            "rollback": {"mode": "set", "owner_id": owner_id, "controller_id": controller_id, "amount": before_balance, "confirm": CONFIRM_EXCHANGE_MUTATION},
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "ownerId": owner_id, "controllerId": controller_id, "mode": mode, "plan": plan, "executionGate": "DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED", "confirm": CONFIRM_EXCHANGE_MUTATION}
        self.require_mutations()
        if not EXCHANGE_MUTATIONS_ENABLED:
            raise PermissionError("exchange mutations are disabled; set DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_EXCHANGE_MUTATION)
        execute("select dune.dune_exchange_modify_user_solari_balance(%s,%s)", (controller_id, delta))
        after = query("select dune.dune_exchange_retrieve_solari_balance(%s) as solari_balance", (owner_id,))
        return {"ok": True, "dryRun": False, "ownerId": owner_id, "controllerId": controller_id, "mode": mode, "before": before_rows, "after": after, "rollback": plan["rollback"]}

    def player_tags_mutation(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        tags_to_add = self.parse_text_list(body.get("tags_to_add", body.get("tagsToAdd", body.get("add", []))), "tags_to_add") if body.get("tags_to_add", body.get("tagsToAdd", body.get("add"))) not in (None, "", []) else []
        tags_to_remove = self.parse_text_list(body.get("tags_to_remove", body.get("tagsToRemove", body.get("remove", []))), "tags_to_remove") if body.get("tags_to_remove", body.get("tagsToRemove", body.get("remove"))) not in (None, "", []) else []
        if not tags_to_add and not tags_to_remove:
            raise ValueError("at least one tag to add or remove is required")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before = query("select * from dune.admin_read_player_tags(%s) order by tags", (account_id,))
        plan = {
            "function": "dune.update_player_tags",
            "args": [account_id, tags_to_add, tags_to_remove],
            "before": before,
            "rollback": {"account_id": account_id, "tags_to_add": tags_to_remove, "tags_to_remove": tags_to_add, "confirm": CONFIRM_PLAYER_TAG_MUTATION},
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "accountId": account_id, "plan": plan, "executionGate": "DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED", "confirm": CONFIRM_PLAYER_TAG_MUTATION}
        self.require_mutations()
        if not PLAYER_TAG_MUTATIONS_ENABLED:
            raise PermissionError("player tag mutations are disabled; set DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_PLAYER_TAG_MUTATION)
        execute("select dune.update_player_tags(%s,%s::text[],%s::text[])", (account_id, tags_to_add, tags_to_remove))
        after = query("select * from dune.admin_read_player_tags(%s) order by tags", (account_id,))
        return {"ok": True, "dryRun": False, "accountId": account_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def access_code_mutation(self, body):
        action = str(body.get("action", "")).strip().lower()
        if action not in ("create", "delete", "reset"):
            raise ValueError("action must be create, delete, or reset")
        account_id = int(body.get("account_id", body.get("accountId")))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before = query("select * from dune.get_player_access_codes(%s) order by access_code_type, access_code", (account_id,))
        plan = {"action": action, "accountId": account_id, "before": before}
        if action in ("create", "delete"):
            access_code = int(body.get("access_code", body.get("accessCode")))
            access_code_type = int(body.get("access_code_type", body.get("accessCodeType", 0)))
            plan.update({
                "accessCode": access_code,
                "accessCodeType": access_code_type,
                "function": "dune.create_server_player_access_codes" if action == "create" else "dune.delete_server_player_access_codes",
                "rollback": {"action": "delete" if action == "create" else "create", "account_id": account_id, "access_code": access_code, "access_code_type": access_code_type, "is_resettable": True, "confirm": CONFIRM_ACCESS_CODE_MUTATION},
            })
            if action == "create":
                plan["isResettable"] = str(body.get("is_resettable", body.get("isResettable", "true"))).lower() in ("1", "true", "yes", "on")
        else:
            plan.update({
                "function": "dune.reset_server_all_player_access_codes",
                "rollback": "No automatic rollback; recreate needed access codes from the dry-run/audit before rows.",
            })
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "accountId": account_id, "plan": plan, "executionGate": "DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED", "confirm": CONFIRM_ACCESS_CODE_MUTATION}
        self.require_mutations()
        if not ACCESS_CODE_MUTATIONS_ENABLED:
            raise PermissionError("access-code mutations are disabled; set DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_ACCESS_CODE_MUTATION)
        if action == "create":
            execute("select dune.create_server_player_access_codes(%s,%s,%s,%s)", (account_id, plan["accessCode"], plan["accessCodeType"], plan["isResettable"]))
        elif action == "delete":
            execute("select dune.delete_server_player_access_codes(%s,%s,%s)", (account_id, plan["accessCode"], plan["accessCodeType"]))
        else:
            execute("select dune.reset_server_all_player_access_codes(%s)", (account_id,))
        after = query("select * from dune.get_player_access_codes(%s) order by access_code_type, access_code", (account_id,))
        return {"ok": True, "dryRun": False, "action": action, "accountId": account_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def parse_bool_value(self, value, field_name):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"{field_name} must be boolean")

    def communinet_mutation(self, body):
        action = str(body.get("action", "")).strip().lower()
        if action not in ("update-data", "update-channel", "remove-channel"):
            raise ValueError("action must be update-data, update-channel, or remove-channel")
        account_id = int(body.get("account_id", body.get("accountId")))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before = query("select * from dune.load_communinet_player_data(%s) order by channel_name", (account_id,))
        plan = {"action": action, "accountId": account_id, "before": before}
        if action == "update-data":
            is_active = self.parse_bool_value(body.get("is_active", body.get("isActive")), "is_active")
            selected_channel = str(body.get("selected_channel_name", body.get("selectedChannelName", ""))).strip()
            plan.update({
                "function": "dune.update_communinet_player_data",
                "args": [account_id, is_active, selected_channel],
                "rollback": "Use the previous is_active and selected_channel_name values from the dry-run/audit record.",
            })
        elif action == "update-channel":
            channel_name = str(body.get("channel_name", body.get("channelName", ""))).strip()
            if not channel_name:
                raise ValueError("channel_name is required")
            is_tuned = self.parse_bool_value(body.get("is_tuned", body.get("isTuned")), "is_tuned")
            plan.update({
                "function": "dune.update_communinet_player_channel",
                "args": [account_id, channel_name, is_tuned],
                "rollback": "Use the previous channel is_tuned value from the dry-run/audit record.",
            })
        else:
            channel_name = str(body.get("channel_name", body.get("channelName", ""))).strip()
            if not channel_name:
                raise ValueError("channel_name is required")
            plan.update({
                "function": "dune.remove_communinet_player_channel",
                "args": [account_id, channel_name],
                "rollback": "Re-add/tune the channel with update-channel if the previous dry-run/audit rows show it existed.",
            })
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "accountId": account_id, "plan": plan, "executionGate": "DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED", "confirm": CONFIRM_COMMUNINET_MUTATION}
        self.require_mutations()
        if not COMMUNINET_MUTATIONS_ENABLED:
            raise PermissionError("communinet mutations are disabled; set DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_COMMUNINET_MUTATION)
        if action == "update-data":
            execute("select dune.update_communinet_player_data(%s,%s,%s)", tuple(plan["args"]))
        elif action == "update-channel":
            execute("select dune.update_communinet_player_channel(%s,%s,%s)", tuple(plan["args"]))
        else:
            execute("select dune.remove_communinet_player_channel(%s,%s)", tuple(plan["args"]))
        after = query("select * from dune.load_communinet_player_data(%s) order by channel_name", (account_id,))
        return {"ok": True, "dryRun": False, "action": action, "accountId": account_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def tutorial_mutation(self, body):
        player_id = int(body.get("player_id", body.get("playerId")))
        tutorial_id = int(body.get("tutorial_id", body.get("tutorialId")))
        tutorial_state = int(body.get("tutorial_state", body.get("tutorialState")))
        if tutorial_id < -32768 or tutorial_id > 32767 or tutorial_state < -32768 or tutorial_state > 32767:
            raise ValueError("tutorial_id and tutorial_state must fit smallint")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        tutorial_rows = query("select * from dune.tutorials where id=%s", (tutorial_id,))
        before = query("select * from dune.get_all_tutorial_entries(%s) where tutorial_id=%s", (player_id, tutorial_id))
        plan = {
            "function": "dune.create_or_update_tutorial_entry",
            "args": [player_id, tutorial_id, tutorial_state],
            "tutorial": tutorial_rows[0] if tutorial_rows else None,
            "before": before,
            "rollback": {"player_id": player_id, "tutorial_id": tutorial_id, "tutorial_state": before[0].get("tutorial_state") if before else None, "confirm": CONFIRM_TUTORIAL_MUTATION},
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "playerId": player_id, "tutorialId": tutorial_id, "plan": plan, "executionGate": "DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED", "confirm": CONFIRM_TUTORIAL_MUTATION}
        self.require_mutations()
        if not TUTORIAL_MUTATIONS_ENABLED:
            raise PermissionError("tutorial mutations are disabled; set DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_TUTORIAL_MUTATION)
        execute("select dune.create_or_update_tutorial_entry(%s,%s::smallint,%s::smallint)", (player_id, tutorial_id, tutorial_state))
        after = query("select * from dune.get_all_tutorial_entries(%s) where tutorial_id=%s", (player_id, tutorial_id))
        return {"ok": True, "dryRun": False, "playerId": player_id, "tutorialId": tutorial_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def permission_mutation(self, body):
        action = str(body.get("action", "")).strip().lower()
        if action not in ("set-name", "set-access-level", "set-player-rank", "remove-player-rank"):
            raise ValueError("action must be set-name, set-access-level, set-player-rank, or remove-player-rank")
        actor_id = int(body.get("actor_id", body.get("actorId")))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        actor_rows = query("select * from dune.permission_actor where actor_id=%s", (actor_id,))
        if not actor_rows:
            raise ValueError("permission actor not found")
        rank_rows = query("select * from dune.permission_actor_rank where permission_actor_id=%s order by player_id", (actor_id,))
        plan = {"action": action, "actorId": actor_id, "before": {"actor": actor_rows[0], "ranks": rank_rows}}
        player_id = None
        if action == "set-name":
            name = str(body.get("name", "")).strip()
            if not name:
                raise ValueError("name is required")
            plan.update({"function": "dune.permission_set_name", "args": [actor_id, name], "rollback": {"action": "set-name", "actor_id": actor_id, "name": actor_rows[0].get("actor_name"), "confirm": CONFIRM_PERMISSION_MUTATION}})
        elif action == "set-access-level":
            access_level = int(body.get("access_level", body.get("accessLevel")))
            if access_level < -32768 or access_level > 32767:
                raise ValueError("access_level must fit smallint")
            plan.update({"function": "dune.permission_set_access_level", "args": [actor_id, access_level], "rollback": {"action": "set-access-level", "actor_id": actor_id, "access_level": actor_rows[0].get("access_level"), "confirm": CONFIRM_PERMISSION_MUTATION}})
        else:
            player_id = int(body.get("player_id", body.get("playerId")))
            existing_rank = next((row for row in rank_rows if int(row.get("player_id")) == player_id), None)
            if action == "set-player-rank":
                rank = int(body.get("rank"))
                if rank < -32768 or rank > 32767:
                    raise ValueError("rank must fit smallint")
                map_id = str(body.get("map_id", body.get("mapId", ""))).strip()
                if not map_id:
                    raise ValueError("map_id is required")
                plan.update({"function": "dune.permission_set_player_rank", "args": [actor_id, player_id, rank, map_id], "previousRank": existing_rank, "rollback": {"action": "set-player-rank" if existing_rank else "remove-player-rank", "actor_id": actor_id, "player_id": player_id, "rank": existing_rank.get("rank") if existing_rank else None, "map_id": map_id, "confirm": CONFIRM_PERMISSION_MUTATION}})
            else:
                plan.update({"function": "dune.permission_remove_player_rank", "args": [actor_id, player_id], "previousRank": existing_rank, "rollback": {"action": "set-player-rank", "actor_id": actor_id, "player_id": player_id, "rank": existing_rank.get("rank") if existing_rank else None, "confirm": CONFIRM_PERMISSION_MUTATION}})
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "actorId": actor_id, "playerId": player_id, "plan": plan, "executionGate": "DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED", "confirm": CONFIRM_PERMISSION_MUTATION}
        self.require_mutations()
        if not PERMISSION_MUTATIONS_ENABLED:
            raise PermissionError("permission mutations are disabled; set DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_PERMISSION_MUTATION)
        if action == "set-name":
            execute("select dune.permission_set_name(%s,%s)", tuple(plan["args"]))
        elif action == "set-access-level":
            execute("select dune.permission_set_access_level(%s,%s::smallint)", tuple(plan["args"]))
        elif action == "set-player-rank":
            execute("select dune.permission_set_player_rank(%s,%s,%s::smallint,%s)", tuple(plan["args"]))
        else:
            execute("select dune.permission_remove_player_rank(%s,%s)", tuple(plan["args"]))
        after = {"actor": query("select * from dune.permission_actor where actor_id=%s", (actor_id,)), "ranks": query("select * from dune.permission_actor_rank where permission_actor_id=%s order by player_id", (actor_id,))}
        return {"ok": True, "dryRun": False, "action": action, "actorId": actor_id, "playerId": player_id, "before": plan["before"], "after": after, "rollback": plan["rollback"]}

    def vendor_mutation(self, body):
        action = str(body.get("action", "set-cycle-timestamp")).strip().lower()
        if action != "set-cycle-timestamp":
            raise ValueError("only set-cycle-timestamp is supported for vendor")
        vendor_id = str(body.get("vendor_id", body.get("vendorId", ""))).strip()
        if not vendor_id:
            raise ValueError("vendor_id is required")
        player_id = int(body.get("player_id", body.get("playerId")))
        timestamp = int(body.get("timestamp", body.get("last_interacted_timestamp", body.get("lastInteractedTimestamp"))))
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before = query("select * from dune.vendor_stock_cycle where vendor_id=%s and player_id=%s", (vendor_id, player_id))
        bought = query("select * from dune.interact_get_vendor_items_bought_from_player(%s,%s,%s) order by out_template_id", (vendor_id, player_id, timestamp))
        plan = {
            "function": "dune.update_vendor_timestamp_for_player",
            "args": [vendor_id, player_id, timestamp],
            "before": before,
            "itemsBoughtAtTimestamp": bought,
            "rollback": {"action": action, "vendor_id": vendor_id, "player_id": player_id, "timestamp": before[0].get("last_interacted_timestamp") if before else None, "confirm": CONFIRM_VENDOR_MUTATION},
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "vendorId": vendor_id, "playerId": player_id, "plan": plan, "executionGate": "DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED", "confirm": CONFIRM_VENDOR_MUTATION}
        self.require_mutations()
        if not VENDOR_MUTATIONS_ENABLED:
            raise PermissionError("vendor mutations are disabled; set DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_VENDOR_MUTATION)
        execute("select dune.update_vendor_timestamp_for_player(%s,%s,%s)", (vendor_id, player_id, timestamp))
        after = query("select * from dune.vendor_stock_cycle where vendor_id=%s and player_id=%s", (vendor_id, player_id))
        return {"ok": True, "dryRun": False, "vendorId": vendor_id, "playerId": player_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def respawn_location_mutation(self, body):
        account_id = int(body.get("account_id", body.get("accountId")))
        respawn_id = str(body.get("respawn_id", body.get("respawnId", ""))).strip()
        action = str(body.get("action", "delete")).strip().lower()
        if action != "delete":
            raise ValueError("only delete is supported for respawn-location")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", respawn_id):
            raise ValueError("respawn_id must be a UUID")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        player, _ = self.resolve_player_identity(account_id)
        current_rows = query("select * from dune.player_respawn_locations where account_id=%s order by last_used_timestamp desc nulls last", (account_id,))
        target = [row for row in current_rows if str(row.get("id")) == respawn_id]
        if not target:
            raise ValueError("respawn_id not found for account_id")
        plan = {
            "function": "dune.update_respawn_locations",
            "args": [account_id, f"get_respawn_locations({account_id}) minus {respawn_id}"],
            "player": player,
            "currentRows": current_rows,
            "delete": target[0],
            "remainingCount": max(0, len(current_rows) - 1),
            "rollback": "No automatic rollback; preserve the deleted row from this dry-run/audit record.",
        }
        if dry_run:
            return {"ok": True, "dryRun": True, "accountId": account_id, "respawnId": respawn_id, "action": action, "plan": plan, "executionGate": "DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED", "confirm": CONFIRM_RESPAWN_MUTATION}
        self.require_mutations()
        if not RESPAWN_MUTATIONS_ENABLED:
            raise PermissionError("respawn mutations are disabled; set DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_RESPAWN_MUTATION)
        if str(player.get("online_status") or "").lower() == "online":
            raise ValueError("player is online; respawn-location execution refuses online targets")
        execute("""
            select dune.update_respawn_locations(%s, coalesce(array(
                select current_location.loc
                from unnest(dune.get_respawn_locations(%s)) as current_location(loc)
                where (current_location.loc).id <> %s::uuid
            ), array[]::dune.respawnlocation[]))
        """, (account_id, account_id, respawn_id))
        after = query("select * from dune.player_respawn_locations where account_id=%s order by last_used_timestamp desc nulls last", (account_id,))
        return {"ok": True, "dryRun": False, "accountId": account_id, "respawnId": respawn_id, "action": action, "before": current_rows, "after": after, "rollback": plan["rollback"]}

    def landsraad_snapshot(self):
        errors = {}
        current = reference_query(errors, "currentTerm", "select * from dune.landsraad_load_current_term()")
        terms = reference_query(errors, "terms", "select * from dune.landsraad_decree_term order by term_id desc limit 5")
        functions = reference_query(errors, "functions", """
            select p.proname as name, pg_get_function_identity_arguments(p.oid) as args
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname='dune'
              and p.proname in ('landsraad_load_current_term', 'landsraad_change_term_end_time', 'landsraad_force_end_term')
            order by p.proname
        """)
        return {"currentTerm": current, "terms": terms, "functions": functions, "errors": errors}

    def landsraad_mutation(self, body):
        action = str(body.get("action", "")).strip().lower()
        if action not in ("change-end-time", "force-end"):
            raise ValueError("action must be change-end-time or force-end")
        dry_run = str(body.get("dry_run", body.get("dryRun", "true"))).lower() not in ("0", "false", "no", "off")
        before = self.landsraad_snapshot()
        current_term = (before.get("currentTerm") or before.get("terms") or [{}])[0] if (before.get("currentTerm") or before.get("terms")) else {}
        term_id = int(body.get("term_id", body.get("termId", current_term.get("term_id") or 0)) or 0)
        if term_id <= 0:
            raise ValueError("term_id is required")
        test_term = str(body.get("test_term", body.get("testTerm", current_term.get("testterm", False)))).lower() in ("1", "true", "yes", "on")
        plan = {
            "action": action,
            "termId": term_id,
            "testTerm": test_term,
            "before": before,
            "function": "dune.landsraad_change_term_end_time" if action == "change-end-time" else "dune.landsraad_force_end_term",
        }
        if action == "change-end-time":
            new_end_time = str(body.get("new_end_time", body.get("newEndTime", ""))).strip()
            if not new_end_time:
                raise ValueError("new_end_time is required for change-end-time")
            plan["newEndTime"] = new_end_time
            plan["rollback"] = {"action": "change-end-time", "term_id": term_id, "new_end_time": current_term.get("end_time"), "confirm": CONFIRM_LANDSRAAD_MUTATION}
        else:
            plan["rollback"] = "force-end is not safely reversible"
        if dry_run:
            return {"ok": True, "dryRun": True, "action": action, "termId": term_id, "plan": plan, "executionGate": "DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED", "confirm": CONFIRM_LANDSRAAD_MUTATION}
        self.require_mutations()
        if not LANDSRAAD_MUTATIONS_ENABLED:
            raise PermissionError("landsraad mutations are disabled; set DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=true")
        require_confirmation(body, CONFIRM_LANDSRAAD_MUTATION)
        if action == "change-end-time":
            execute("select dune.landsraad_change_term_end_time(%s,%s::timestamp,%s)", (term_id, plan["newEndTime"], test_term))
        else:
            execute("select dune.landsraad_force_end_term(%s)", (term_id,))
        after = self.landsraad_snapshot()
        return {"ok": True, "dryRun": False, "action": action, "termId": term_id, "before": before, "after": after, "rollback": plan["rollback"]}

    def write_config(self, name, content):
        if name not in ALLOWED_CONFIGS:
            raise ValueError("config file not allowed")
        path = ALLOWED_CONFIGS[name]
        if name.endswith(".ini"):
            parser = configparser.ConfigParser()
            parser.read_string(content)
        backup_file(path)
        path.write_text(content, encoding="utf-8")

    def require_token(self):
        if os.environ.get("DUNE_ADMIN_REQUIRE_TOKEN", "false").lower() not in ("1", "true", "yes", "on"):
            return
        if not ADMIN_TOKEN:
            raise PermissionError("DUNE_ADMIN_TOKEN is not configured")
        peer = self.client_address[0] if self.client_address else "unknown"
        now = time.time()
        failures = [ts for ts in AUTH_FAILURES.get(peer, []) if now - ts < AUTH_FAILURE_WINDOW_SECONDS]
        AUTH_FAILURES[peer] = failures
        if len(failures) >= AUTH_FAILURE_LIMIT:
            self.audit("auth-throttled", ok=False, failures=len(failures))
            raise PermissionError("too many failed admin token attempts")
        provided = self.headers.get("X-Admin-Token", "").strip()
        if not provided:
            authorization = self.headers.get("Authorization", "").strip()
            if authorization.lower().startswith("bearer "):
                provided = authorization[7:].strip()
        if not hmac.compare_digest(provided, ADMIN_TOKEN):
            failures.append(now)
            AUTH_FAILURES[peer] = failures
            self.audit("auth-failed", ok=False, failures=len(failures))
            raise PermissionError("invalid admin token")
        AUTH_FAILURES.pop(peer, None)

    def require_mutations(self):
        if not MUTATIONS_ENABLED:
            raise PermissionError("mutations are disabled; set DUNE_ADMIN_MUTATIONS_ENABLED=true")

    def require_item_grants(self):
        if not ITEM_GRANTS_ENABLED:
            raise PermissionError("item grants are disabled; set DUNE_ADMIN_ITEM_GRANTS_ENABLED=true")

    def require_catalog(self):
        if not CATALOG_ENABLED:
            raise PermissionError("catalog is disabled; set DUNE_ADMIN_CATALOG_ENABLED=true")

    def require_typed_knobs(self):
        if not TYPED_KNOBS_ENABLED:
            raise PermissionError("typed knob writes are disabled; set DUNE_ADMIN_TYPED_KNOBS_ENABLED=true")

    def validate_host(self):
        if not ALLOWED_HOSTS:
            return
        host = self.headers.get("Host", "").lower()
        if host not in ALLOWED_HOSTS:
            self.audit("host-rejected", ok=False, host=host)
            raise PermissionError("host is not allowed for admin panel")

    def validate_same_origin(self):
        host = self.headers.get("Host", "").lower()
        expected = {f"http://{host}", f"https://{host}"}
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") not in expected:
            self.audit("origin-rejected", ok=False, origin=origin)
            raise PermissionError("cross-origin admin request rejected")
        referer = self.headers.get("Referer")
        if referer:
            parsed = urllib.parse.urlparse(referer)
            referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
            if referer_origin not in expected:
                self.audit("referer-rejected", ok=False, referer_origin=referer_origin)
                raise PermissionError("cross-origin admin request rejected")

    def is_app_route(self, path):
        if path == "/":
            return True
        route = path.strip("/")
        return route in {"overview", "ops", "security", "runbook", "characters", "settings", "mutations", "catalog"}

    def html(self, body, head_only=False):
        nonce = secrets.token_urlsafe(16)
        body = body.replace("__NONCE__", nonce)
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.security_headers(nonce=nonce)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def json(self, value, head_only=False):
        data = json.dumps(value, default=json_default, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def static_file(self, path, content_type, head_only=False):
        try:
            resolved = path.resolve()
            resolved.relative_to(STATIC_ROOT.resolve())
            data = resolved.read_bytes()
        except Exception:
            self.error(HTTPStatus.NOT_FOUND, "static asset not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def error(self, status, message, head_only=False):
        data = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def security_headers(self, nonce=None):
        self.send_header("Cache-Control", "no-store, no-cache, max-age=0, must-revalidate, proxy-revalidate")
        self.send_header("Surrogate-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-Admin-Panel-Build", ADMIN_PANEL_BUILD)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        script_src = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
        style_src = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
        self.send_header("Content-Security-Policy", f"default-src 'self'; script-src {script_src}; style-src {style_src}; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("Connection", "close")
        self.close_connection = True

    def log_message(self, fmt, *args):
        return


INDEX = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="admin-panel-build" content="20260520-hagga-clean-map-south">
  <title>Dune Admin</title>
  <style nonce="__NONCE__">
    :root { color-scheme: dark; --bg:#0f1110; --nav:#141814; --panel:#1a1f1a; --panel2:#131713; --panel3:#20261f; --muted:#a3aea4; --line:#323b32; --text:#edf3ea; --accent:#d5a13e; --danger:#d96f62; --ok:#7fc27a; --warn:#e1b75f; }
    * { box-sizing:border-box; }
    body { margin:0; font:14px/1.45 system-ui, sans-serif; background:var(--bg); color:var(--text); }
    body.highContrast { --bg:#050605; --nav:#090b09; --panel:#101410; --panel2:#0b0e0b; --line:#6b7867; --text:#ffffff; --muted:#d5ded4; --accent:#ffd166; --danger:#ff8a80; --ok:#8cff8a; --warn:#ffe082; }
    body.denseMode { font-size:13px; }
    body.denseMode .card, body.denseMode .panelBand, body.denseMode .vizCard, body.denseMode .metric { padding:10px; }
    body.denseMode .metric { min-height:64px; }
    body.denseMode .metric .value { font-size:17px; }
    .skipLink { position:absolute; left:12px; top:-60px; z-index:20; background:var(--accent); color:#16120a; padding:8px 10px; border-radius:6px; font-weight:700; }
    .skipLink:focus { top:10px; }
    header { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:13px 18px; border-bottom:1px solid var(--line); background:#161a16; position:sticky; top:0; z-index:3; }
    h1 { font-size:18px; margin:0; letter-spacing:0; }
    h2 { font-size:16px; margin:0 0 10px; }
    h3 { font-size:13px; margin:0 0 8px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
    main { display:grid; grid-template-columns:264px minmax(0,1fr); min-height:calc(100vh - 58px); }
    nav { border-right:1px solid var(--line); padding:14px; background:var(--nav); position:sticky; top:58px; height:calc(100vh - 58px); overflow:auto; }
    section { padding:18px; min-width:0; max-width:1540px; }
    button, input, select, textarea { font:inherit; border:1px solid var(--line); background:#101310; color:var(--text); border-radius:6px; padding:8px 10px; }
    button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible, a:focus-visible, tr[tabindex]:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
    button { cursor:pointer; background:#22291f; white-space:nowrap; }
    button:hover { border-color:#53614d; }
    button.primary { background:var(--accent); color:#16120a; border-color:#e0b45e; font-weight:700; }
    button.danger { background:#35201e; color:#ffd5d0; border-color:#78423c; }
    input, select { width:100%; box-sizing:border-box; }
    textarea { width:100%; min-height:340px; box-sizing:border-box; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; }
    .brand { display:flex; align-items:baseline; gap:10px; }
    .brand .subtle { color:var(--muted); font-size:12px; }
    .tabs { display:grid; gap:6px; }
    .tab { padding:10px 11px; text-align:left; border-radius:7px; }
    .tab.active { border-color:var(--accent); color:var(--accent); background:#252416; }
    .card { border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; margin-bottom:14px; }
    .panelBand { border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; margin-bottom:14px; }
    .pageStack { display:grid; gap:14px; }
    .pageStack > * { min-width:0; }
    .twoCol { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(360px,.8fr); gap:14px; align-items:start; }
    .threeCol { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; align-items:start; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
    .settingsGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }
    .settingsGrid label { min-width:0; overflow-wrap:anywhere; }
    .metricGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:14px; }
    .metric { border:1px solid var(--line); border-radius:8px; background:var(--panel2); padding:12px; min-height:82px; }
    .metric .label { color:var(--muted); font-size:12px; }
    .metric .value { font-size:20px; font-weight:700; margin-top:6px; overflow-wrap:anywhere; }
    .overviewTopGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(108px,1fr)); gap:8px; margin-bottom:14px; }
    .overviewTopGrid .metric { min-height:74px; padding:10px 12px; min-width:0; }
    .overviewTopGrid .metric .value { font-size:18px; }
    .overviewMapShell .panelBand { margin-bottom:0; }
    .overviewMapShell .haggaMap { aspect-ratio:16 / 10; max-height:calc(100vh - 260px); min-height:520px; }
    .overviewMapShell .haggaMap svg { block-size:100%; inline-size:100%; aspect-ratio:auto; }
    .summaryCard { position:relative; border:1px solid var(--line); border-radius:8px; background:var(--panel2); padding:10px 12px; min-height:74px; min-width:0; }
    .summaryCard:focus-within, .summaryCard:hover { border-color:#53614d; }
    .summaryCard h3 { margin:0 0 6px; }
    .summaryValue { font-size:22px; font-weight:800; line-height:1; }
    .summaryMeta { color:var(--muted); font-size:12px; margin-top:7px; }
    .summaryCard .sparkSvg { height:28px; margin-top:5px; padding:4px; }
    .summaryHover { position:fixed; z-index:14; top:92px; right:24px; display:none; width:min(920px,calc(100vw - 48px)); max-height:calc(100vh - 128px); overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel); box-shadow:0 18px 60px rgba(0,0,0,.55); padding:14px; }
    .summaryCard:hover .summaryHover, .summaryCard:focus-within .summaryHover { display:block; }
    .summaryHover .panelBand { margin:0; }
    .pill { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); border-radius:999px; padding:5px 9px; background:#101310; color:var(--muted); font-size:12px; }
    .pill.ok { border-color:#315e31; color:var(--ok); }
    .pill.warn { border-color:#6d5624; color:var(--warn); }
    .pill.bad { border-color:#743932; color:var(--danger); }
    .row { display:flex; gap:8px; align-items:center; margin:8px 0; }
    .toolbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
    .toolbar label { display:inline-flex; align-items:center; gap:6px; }
    .checkToolbar label { min-width:auto; }
    .checkToolbar input[type="checkbox"] { width:auto !important; flex:0 0 auto; }
    .sectionHeader { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }
    .sectionHeader .toolbar { margin-bottom:0; }
    .commandBar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:14px; }
    .commandBar button { min-height:38px; }
    .splitHeader { display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:10px; }
    summary h2 { display:inline; margin:0; }
    .subgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; align-items:start; }
    .dangerZone { border-color:#74413b; background:#211816; }
    .dataDense th, .dataDense td { padding:6px; font-size:13px; }
    .vizGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-bottom:14px; }
    .vizCard { border:1px solid var(--line); border-radius:8px; background:var(--panel2); padding:14px; min-height:140px; }
    .vizCard h3 { margin-bottom:10px; }
    .donutWrap { display:flex; gap:14px; align-items:center; min-height:110px; }
    .donut { width:112px; height:112px; flex:0 0 auto; }
    .donut text { fill:var(--text); font:700 13px system-ui, sans-serif; text-anchor:middle; dominant-baseline:middle; }
    .legend { display:grid; gap:7px; min-width:0; }
    .legendRow { display:flex; align-items:center; gap:8px; min-width:0; }
    .swatch { width:10px; height:10px; border-radius:2px; flex:0 0 auto; background:var(--accent); }
    .swatch0 { background:var(--ok); }
    .swatch1 { background:var(--accent); }
    .swatch2 { background:var(--danger); }
    .barList { display:grid; gap:9px; }
    .barRow { display:grid; grid-template-columns:minmax(100px,1fr) minmax(130px,2fr) auto; gap:10px; align-items:center; }
    .barTrack { height:10px; border-radius:999px; background:#0d100d; border:1px solid var(--line); overflow:hidden; }
    .barProgress { width:100%; height:100%; appearance:none; display:block; border:0; background:transparent; }
    .barProgress::-webkit-progress-bar { background:transparent; }
    .barProgress::-webkit-progress-value { background:var(--accent); }
    .barProgress.ok::-webkit-progress-value { background:var(--ok); }
    .barProgress.warn::-webkit-progress-value { background:var(--warn); }
    .barProgress.bad::-webkit-progress-value { background:var(--danger); }
    .barProgress::-moz-progress-bar { background:var(--accent); }
    .barProgress.ok::-moz-progress-bar { background:var(--ok); }
    .barProgress.warn::-moz-progress-bar { background:var(--warn); }
    .barProgress.bad::-moz-progress-bar { background:var(--danger); }
    .spark { display:flex; height:58px; gap:3px; align-items:end; padding:8px; border:1px solid var(--line); border-radius:8px; background:#0d100d; }
    .spark span { flex:1; min-width:3px; background:var(--accent); border-radius:2px 2px 0 0; opacity:.9; }
    .spark.compact { height:42px; }
    .sparkSvg { display:block; width:100%; height:58px; padding:8px; box-sizing:border-box; border:1px solid var(--line); border-radius:8px; background:#0d100d; }
    .sparkSvg.compact { height:42px; }
    .sparkSvg rect { fill:var(--accent); opacity:.9; rx:2; }
    .compactTextarea { min-height:120px; }
    tr.selected td { background:#252416; }
    .mapGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; }
    .mapTile { border:1px solid var(--line); border-radius:7px; padding:9px; background:#101310; min-height:62px; }
    .mapTile.ok { border-color:#315e31; }
    .mapTile.bad { border-color:#743932; }
    .mapTile .name { font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .mapTile .meta { color:var(--muted); font-size:12px; margin-top:4px; }
    .haggaMap { position:relative; display:block; overflow:hidden; touch-action:none; cursor:grab; background:#171513; inline-size:100%; margin-inline:auto; border:1px solid var(--line); border-radius:8px; }
    .haggaMap.isDragging { cursor:grabbing; }
    .haggaMap svg { display:block; inline-size:100%; aspect-ratio:1 / 1; block-size:auto; background:#171513; transform-origin:center center; will-change:transform; user-select:none; }
    .haggaMap .mapImage { opacity:.95; }
    .haggaMap .mapShade { fill:rgba(4,5,4,.08); }
    .haggaMap .gridLine { stroke:#f1d08a; stroke-width:1; opacity:.22; }
    .haggaMap .gridLabel { fill:#ead9ac; font:10px ui-monospace, SFMono-Regular, Menlo, monospace; paint-order:stroke; stroke:#0b0d0a; stroke-width:3; opacity:.84; }
    .haggaMap .playerDot { fill:var(--ok); stroke:#071007; stroke-width:3; }
    .haggaMap .landmarkDot { fill:#d8b763; stroke:#17120a; stroke-width:1.5; opacity:.45; }
    .haggaMap .landmarkLabel { fill:#f0dfaa; font:700 10px system-ui,sans-serif; paint-order:stroke; stroke:#0b0d0a; stroke-width:3; opacity:.68; }
    .haggaMap .poiMarker { opacity:.86; }
    .haggaMap .poiMarker circle { stroke:#0b0d0a; stroke-width:2; }
    .haggaMap .poiMarker text { display:none; fill:var(--text); font:700 11px system-ui,sans-serif; paint-order:stroke; stroke:#0b0d0a; stroke-width:3; }
    .haggaMap .poiMarker:hover text, .haggaMap .poiMarker:focus text { display:block; }
    .haggaMap .returnDot { fill:var(--warn); stroke:#160f04; stroke-width:3; }
    .haggaMap .uncertainLine { stroke:var(--warn); stroke-width:2; stroke-dasharray:7 7; opacity:.75; }
    .haggaMap .playerMarker:focus .playerDot, .haggaMap .playerMarker:hover .playerDot { fill:var(--accent); stroke:var(--text); }
    .haggaMap .playerLabel { fill:var(--text); font:700 13px system-ui,sans-serif; paint-order:stroke; stroke:#0b0d0a; stroke-width:4; }
    .haggaMap .coordLabel { fill:var(--muted); font:11px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .haggaMap .emptyState { fill:var(--muted); font:14px system-ui,sans-serif; text-anchor:middle; }
    .haggaMapStatus { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px; }
    .mapLegend { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
    .poiToggleBar { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:6px 14px; border:1px solid var(--line); border-radius:7px; background:#101310; margin:0 0 10px; padding:10px 12px; }
    .poiToggleBar label { display:inline-flex; justify-content:space-between; gap:10px; align-items:center; color:var(--text); font-size:12px; line-height:1.25; }
    .poiToggleBar input { width:auto; }
    .poiLegendHeader { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:0 0 6px; }
    .poiLegendHeader .toolbar { margin:0; }
    .poiToggleLabel { display:inline-flex; align-items:center; gap:7px; min-width:0; }
    .poiSwatch { width:10px; height:10px; border:1px solid #0b0d0a; border-radius:2px; flex:0 0 auto; }
    .poiCount { color:var(--muted); font-size:11px; }
    .teleportMap { cursor:crosshair; min-height:360px; }
    .teleportMap .teleportTargetDot { fill:var(--danger); stroke:#fff0d0; stroke-width:3; }
    .teleportMap .teleportTargetLabel { fill:#fff0d0; font:700 12px system-ui,sans-serif; paint-order:stroke; stroke:#0b0d0a; stroke-width:4; }
    .coordTable td, .coordTable th { font-size:12px; }
    .filterInput { max-width:280px; }
    .toast { position:fixed; right:18px; bottom:18px; z-index:10; display:grid; gap:8px; max-width:min(420px,calc(100vw - 36px)); }
    .toastItem { border:1px solid var(--line); border-radius:8px; background:#151915; box-shadow:0 10px 30px rgba(0,0,0,.35); padding:10px 12px; }
    .toastItem.ok { border-color:#315e31; }
    .toastItem.bad { border-color:#743932; }
    .modalBackdrop { position:fixed; inset:0; z-index:12; display:none; place-items:center; background:rgba(0,0,0,.62); padding:18px; }
    .modalBackdrop.open { display:grid; }
    .modal { width:min(720px,100%); max-height:min(760px,92vh); overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:16px; box-shadow:0 18px 60px rgba(0,0,0,.5); }
    .modal.wide { width:min(1180px,100%); }
    .playerModalGrid { display:grid; grid-template-columns:minmax(260px,.75fr) minmax(0,1.25fr); gap:14px; align-items:start; }
    .playerModalGrid .panelBand { margin:0; }
    .playerInventoryTools { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
    @media (max-width:860px) { .playerModalGrid { grid-template-columns:1fr; } }
    .shortcutGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
    .shortcut { display:flex; justify-content:space-between; gap:12px; border:1px solid var(--line); border-radius:7px; padding:9px; background:var(--panel2); }
    kbd { border:1px solid var(--line); border-bottom-width:2px; border-radius:5px; padding:2px 6px; background:#0d100d; color:var(--text); font:12px ui-monospace, SFMono-Regular, Menlo, monospace; white-space:nowrap; }
    .copyWrap { position:relative; }
    .copyBtn { position:absolute; right:8px; top:8px; z-index:1; padding:5px 8px; font-size:12px; }
    .copyWrap pre { padding-top:42px; }
    .filterMeta { font-size:12px; color:var(--muted); }
    .eventList { display:grid; gap:8px; }
    .eventItem { border:1px solid var(--line); border-radius:7px; padding:9px; background:var(--panel2); }
    .eventItemHead { display:flex; gap:8px; align-items:center; justify-content:space-between; flex-wrap:wrap; margin-bottom:6px; }
    .srOnly { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
    .muted { color:var(--muted); }
    .ok { color:var(--ok); }
    .dangerText { color:var(--danger); }
    label span { display:block; margin-top:5px; font-size:12px; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; border-bottom:1px solid var(--line); padding:7px 6px; vertical-align:top; }
    .tableWrap { overflow:auto; border:1px solid var(--line); border-radius:8px; }
    .tableWrap table th { background:#151915; position:sticky; top:0; }
    th.sortable { cursor:pointer; user-select:none; }
    th.sortable[data-sort-dir="asc"]::after { content:" ↑"; color:var(--accent); }
    th.sortable[data-sort-dir="desc"]::after { content:" ↓"; color:var(--accent); }
    pre { white-space:pre-wrap; overflow:auto; background:#0d100d; border:1px solid var(--line); padding:10px; border-radius:6px; max-height:360px; }
    #statusSummary { display:grid; gap:8px; }
    #statusRaw { max-height:180px; font-size:12px; }
    .hostNote { font-size:13px; line-height:1.35; }
    .hidden { display:none; }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior:auto !important; transition:none !important; animation:none !important; } }
    @media (max-width: 1100px) { .twoCol, .threeCol { grid-template-columns:1fr; } .overviewMapShell .haggaMap { aspect-ratio:1 / 1; min-height:0; max-height:none; } }
    @media (max-width: 1180px) { main { grid-template-columns:1fr; } nav { position:static; height:auto; border-right:0; border-bottom:1px solid var(--line); } .tabs { grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); } .overviewTopGrid { grid-template-columns:repeat(3,minmax(0,1fr)); } .sectionHeader { flex-wrap:wrap; } }
    @media (max-width: 640px) { section { padding:12px; } .overviewTopGrid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width: 820px) { header { align-items:flex-start; flex-direction:column; } .row { flex-wrap:wrap; } .barRow { grid-template-columns:1fr; gap:4px; } }
  </style>
</head>
<body>
  <a class="skipLink" href="#view">Skip to dashboard</a>
  <header>
    <div class="brand"><h1>DASH Admin</h1><span class="subtle">Dune Awakening Self Host</span></div>
    <div class="row" id="tokenRow"><input id="token" type="password" placeholder="Admin token"><button id="saveTokenBtn">Use token</button><button id="clearTokenBtn">Clear</button></div>
  </header>
  <main>
    <nav aria-label="Admin panel navigation">
      <div class="tabs" role="tablist" aria-label="DASH sections">
        <button class="tab active" role="tab" aria-selected="true" data-tab="overview">Overview</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="ops">Ops</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="security">Security</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="runbook">Runbook</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="characters">Players</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="settings">Settings</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="mutations">Admin Actions</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="digests">Admin Digests</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="catalog">Catalog</button>
      </div>
      <div class="card"><h3>Display</h3><div class="toolbar"><button id="contrastBtn">High contrast</button><button id="densityBtn">Dense mode</button><button id="expandAllBtn">Expand all</button><button id="collapseAllBtn">Collapse all</button><button id="helpBtn">Shortcuts</button></div></div>
      <div class="card">
        <h3>Runtime</h3>
        <div id="statusSummary"></div>
        <div class="muted" id="lastRefresh">Not refreshed yet</div>
        <details>
          <summary class="muted">Raw status</summary>
          <pre id="statusRaw"></pre>
        </details>
      </div>
    </nav>
    <section id="view" tabindex="-1" role="tabpanel" aria-live="polite"></section>
  </main>
  <div id="toast" class="toast" aria-live="polite" aria-atomic="true"></div>
  <div id="srStatus" class="srOnly" aria-live="polite" aria-atomic="true"></div>
  <div id="helpModal" class="modalBackdrop" role="dialog" aria-modal="true" aria-labelledby="helpTitle">
    <div class="modal">
      <div class="sectionHeader"><h2 id="helpTitle">Keyboard and Display Controls</h2><button id="closeHelpBtn">Close</button></div>
      <div class="shortcutGrid">
        <div class="shortcut"><span>Open this dialog</span><kbd>?</kbd></div>
        <div class="shortcut"><span>Refresh current page</span><kbd>R</kbd></div>
        <div class="shortcut"><span>Focus player/search filter</span><kbd>/</kbd></div>
        <div class="shortcut"><span>Overview</span><kbd>1</kbd></div>
        <div class="shortcut"><span>Operations</span><kbd>2</kbd></div>
        <div class="shortcut"><span>Players</span><kbd>5</kbd></div>
        <div class="shortcut"><span>High contrast</span><kbd>H</kbd></div>
        <div class="shortcut"><span>Dense mode</span><kbd>D</kbd></div>
        <div class="shortcut"><span>Expand details</span><kbd>E</kbd></div>
        <div class="shortcut"><span>Collapse details</span><kbd>C</kbd></div>
        <div class="shortcut"><span>Close dialog</span><kbd>Esc</kbd></div>
      </div>
    </div>
  </div>
  <div id="playerModal" class="modalBackdrop" role="dialog" aria-modal="true" aria-labelledby="playerModalTitle">
    <div class="modal wide">
      <div class="sectionHeader"><h2 id="playerModalTitle">Player Detail</h2><div class="toolbar"><span id="playerModalRefreshState" class="pill">idle</span><button id="refreshPlayerModalBtn">Refresh</button><button id="closePlayerModalBtn">Close</button></div></div>
      <div id="playerModalBody"><div class="muted">No player selected.</div></div>
    </div>
  </div>
<script nonce="__NONCE__">
const ADMIN_PANEL_BUILD = '20260520-hagga-clean-map-south';
let token = (localStorage.getItem('duneAdminToken') || sessionStorage.getItem('duneAdminToken') || '').trim();
document.getElementById('token').value = token;
const validTabs = new Set(['overview', 'ops', 'security', 'runbook', 'characters', 'settings', 'mutations', 'digests', 'catalog']);
const pathTab = location.pathname.slice(1);
let current = validTabs.has(location.hash.slice(1)) ? location.hash.slice(1) : (validTabs.has(pathTab) ? pathTab : (sessionStorage.getItem('duneAdminTab') || 'overview'));
if (!validTabs.has(current)) current = 'overview';
let pendingAdminAccountId = '';
let resourceTimer = null;
let overviewResourceTimer = null;
let healthTimer = null;
let haggaMapTimer = null;
let loadSerial = 0;
let detailLoadSerial = 0;
let playerModalAccountId = '';
let playerModalTimer = null;
let playerModalInFlight = false;
let playerModalRef = null;
let resourceRefreshInFlight = false;
let healthRefreshInFlight = false;
let haggaMapRefreshInFlight = false;
let haggaMapAutoRefresh = sessionStorage.getItem('duneAdminHaggaMapAutoRefresh') !== 'off';
let haggaMapLastGoodHtml = '';
let haggaMapZoomState = {scale:1, x:0, y:0};
let haggaMapSuppressMarkerClick = false;
let haggaPoiGroups = {};
let autoRefresh = sessionStorage.getItem('duneAdminAutoRefresh') !== 'off';
const resourceHistory = [];
let adminReferenceCache = null;
let adminReferenceCacheAt = 0;
let overviewRosterCounts = {};
let overviewHealthSnapshot = null;
let overviewResourceSnapshot = null;
let overviewResourcePrevious = null;
const view = document.getElementById('view');

document.body.classList.toggle('highContrast', sessionStorage.getItem('duneAdminHighContrast') === 'on');
document.body.classList.toggle('denseMode', sessionStorage.getItem('duneAdminDenseMode') === 'on');
function normalizeToken(value){ return String(value || '').trim().replace(/^Bearer\s+/i, '').trim(); }
async function saveToken(){
  token = normalizeToken(document.getElementById('token').value);
  document.getElementById('token').value = token;
  localStorage.setItem('duneAdminToken', token);
  sessionStorage.setItem('duneAdminToken', token);
  await load();
}
function clearToken(){
  token = '';
  document.getElementById('token').value = '';
  localStorage.removeItem('duneAdminToken');
  sessionStorage.removeItem('duneAdminToken');
  notify('Admin token cleared');
  load();
}
function announce(message){ document.getElementById('srStatus').textContent = message; }
function notify(message, tone='ok'){
  const box = document.getElementById('toast');
  const item = document.createElement('div');
  item.className = `toastItem ${tone}`;
  item.textContent = message;
  box.appendChild(item);
  announce(message);
  setTimeout(() => item.remove(), 4200);
}
function reportClientError(error, context='Panel error'){
  const message = error?.message || String(error || 'unknown error');
  notify(`${context}: ${message}`, 'bad');
  console.error(context, error);
}
async function runAction(button, label, fn){
  const original = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = label;
  }
  try {
    await fn();
  } catch (e) {
    reportClientError(e, label);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}
function updateLastRefresh(label='Refreshed'){
  document.getElementById('lastRefresh').textContent = `${label}: ${new Date().toLocaleTimeString()}`;
}
async function api(path, opts={}) {
  const timeoutMs = opts.timeoutMs ?? 15000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  delete opts.timeoutMs;
  opts.signal = opts.signal || controller.signal;
  opts.headers = Object.assign({'Content-Type':'application/json'}, opts.headers || {});
  opts.cache = opts.cache || 'no-store';
  if (token) opts.headers['X-Admin-Token'] = token;
  if (!opts.method || String(opts.method).toUpperCase() === 'GET') {
    const separator = path.includes('?') ? '&' : '?';
    path = `${path}${separator}_=${Date.now()}`;
  }
  try {
    const res = await fetch(path, opts);
    const text = await res.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        throw new Error(`${res.status} ${res.statusText}: non-JSON response from ${path}`);
      }
    }
    if (!res.ok) {
      const message = data.error || res.statusText || `HTTP ${res.status}`;
      if (res.status === 401) throw new Error(`${message}. Paste the current admin token and press Use token.`);
      throw new Error(message);
    }
    return data;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error(`request timed out after ${Math.round(timeoutMs / 1000)}s`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
async function adminReference(opts={}) {
  const ttlMs = opts.ttlMs ?? 60000;
  const now = Date.now();
  if (adminReferenceCache && now - adminReferenceCacheAt < ttlMs) return adminReferenceCache;
  adminReferenceCache = await api('/api/admin/reference', opts);
  adminReferenceCacheAt = Date.now();
  return adminReferenceCache;
}
function esc(v){ return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function table(rows){
  if (!rows || !rows.length) return '<div class="muted">No rows.</div>';
  const keys = Object.keys(rows[0]);
  return `<div class="tableWrap"><table><thead><tr>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr data-id="${esc(r.account_id ?? '')}">${keys.map(k=>`<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function filterKey(input){
  const panel = input.closest('.rosterPanel, .resourcePanel, .panelBand, .card, section');
  const title = panel?.querySelector('h2, h3')?.textContent?.trim() || input.placeholder || 'filter';
  return `duneAdminFilter:${current}:${title}:${input.placeholder || ''}`;
}
function bindTextFilter(input, rows){
  if (input.dataset.filterBound) return;
  input.dataset.filterBound = 'true';
  const key = filterKey(input);
  const stored = sessionStorage.getItem(key);
  if (stored !== null && !input.value) input.value = stored;
  let meta = input.parentElement?.querySelector('.filterMeta');
  if (!meta) {
    meta = document.createElement('span');
    meta.className = 'filterMeta';
    input.insertAdjacentElement('afterend', meta);
  }
  const apply = () => {
    const term = input.value.trim().toLowerCase();
    sessionStorage.setItem(key, input.value);
    let visible = 0;
    rows.forEach(row => {
      row.hidden = term && !row.textContent.toLowerCase().includes(term);
      if (!row.hidden) visible++;
    });
    meta.textContent = `${visible}/${rows.length} visible`;
    announce(`${visible} of ${rows.length} rows visible`);
  };
  input.addEventListener('input', apply);
  apply();
}
async function copyText(text){
  try {
    await navigator.clipboard.writeText(text);
    notify('Copied to clipboard');
  } catch (e) {
    notify('Copy failed', 'bad');
  }
}
function enhanceCopyBlocks(root=document){
  root.querySelectorAll('pre').forEach((pre, index) => {
    if (pre.closest('.copyWrap')) return;
    const wrap = document.createElement('div');
    wrap.className = 'copyWrap';
    const button = document.createElement('button');
    button.className = 'copyBtn';
    button.type = 'button';
    button.textContent = 'Copy';
    button.setAttribute('aria-label', 'Copy block to clipboard');
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(button);
    wrap.appendChild(pre);
    button.addEventListener('click', () => copyText(pre.textContent || ''));
  });
}
function makeSortableTables(root=document){
  root.querySelectorAll('table').forEach(table => {
    if (table.dataset.sortableBound) return;
    table.dataset.sortableBound = 'true';
    table.querySelectorAll('th').forEach((th, index) => {
      th.classList.add('sortable');
      th.tabIndex = 0;
      th.setAttribute('role', 'button');
      th.setAttribute('aria-label', `Sort by ${th.textContent.trim() || 'column'}`);
      th.addEventListener('click', () => {
        const tbody = table.tBodies[0];
        if (!tbody) return;
        const dir = th.dataset.sortDir === 'asc' ? 'desc' : 'asc';
        table.querySelectorAll('th').forEach(header => delete header.dataset.sortDir);
        th.dataset.sortDir = dir;
        const rows = Array.from(tbody.rows);
        const cellValue = row => row.cells[index]?.textContent.trim() || '';
        rows.sort((a, b) => {
          const av = cellValue(a);
          const bv = cellValue(b);
          const an = Number.parseFloat(av.replace(/[^0-9.-]/g, ''));
          const bn = Number.parseFloat(bv.replace(/[^0-9.-]/g, ''));
          const bothNumeric = av && bv && !Number.isNaN(an) && !Number.isNaN(bn);
          const cmp = bothNumeric ? an - bn : av.localeCompare(bv, undefined, {numeric:true, sensitivity:'base'});
          return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(row => tbody.appendChild(row));
        announce(`Sorted by ${th.textContent.trim() || 'column'} ${dir === 'asc' ? 'ascending' : 'descending'}`);
      });
      th.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          th.click();
        }
      });
    });
  });
}
function makeRowsKeyboardFriendly(root=document){
  root.querySelectorAll('tbody tr[data-id]').forEach(row => {
    if (row.dataset.keyboardBound) return;
    row.dataset.keyboardBound = 'true';
    row.tabIndex = 0;
    row.setAttribute('role', 'button');
    row.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        row.click();
      }
    });
  });
}
function bindRosterFilters(root=document){
  root.querySelectorAll('.rosterFilter').forEach(input => {
    const panel = input.closest('.rosterPanel');
    if (panel) bindTextFilter(input, panel.querySelectorAll('tbody tr'));
  });
  makeSortableTables(root);
}
function bindResourceFilters(root=document){
  root.querySelectorAll('.resourceFilter').forEach(input => {
    const panel = input.closest('.resourcePanel');
    if (panel) bindTextFilter(input, panel.querySelectorAll('tbody tr'));
  });
  makeSortableTables(root);
}
function metric(label, value, tone=''){
  return `<div class="metric"><div class="label">${esc(label)}</div><div class="value ${tone}">${esc(value)}</div></div>`;
}
function clamp(n, min=0, max=100){ return Math.max(min, Math.min(max, Number(n || 0))); }
function toneForPercent(value){ value = Number(value || 0); return value >= 90 ? 'bad' : value >= 70 ? 'warn' : 'ok'; }
function bar(label, value, max=100, detail=''){
  const pct = max ? clamp((Number(value || 0) / max) * 100) : 0;
  const tone = toneForPercent(pct);
  return `<div class="barRow"><div title="${esc(label)}">${esc(label)}</div><div class="barTrack"><progress class="barProgress ${tone}" value="${esc(pct.toFixed(1))}" max="100"></progress></div><div class="muted">${esc(detail || pct.toFixed(0) + '%')}</div></div>`;
}
function donut(label, segments){
  const total = segments.reduce((sum, s) => sum + Number(s.value || 0), 0);
  let offset = 25;
  const circles = segments.map((s, i) => {
    const value = total ? (Number(s.value || 0) / total) * 100 : 0;
    const circle = `<circle r="15.9" cx="18" cy="18" fill="transparent" stroke="${esc(s.color)}" stroke-width="6" stroke-dasharray="${value} ${100 - value}" stroke-dashoffset="${offset}"></circle>`;
    offset -= value;
    return circle;
  }).join('');
  const legend = segments.map((s, i) => `<div class="legendRow"><span class="swatch swatch${i % 3}"></span><span>${esc(s.label)}</span><span class="muted">${esc(s.value)}</span></div>`).join('');
  return `<div class="vizCard"><h3>${esc(label)}</h3><div class="donutWrap"><svg class="donut" viewBox="0 0 36 36">${circles}<text x="18" y="18">${esc(total)}</text></svg><div class="legend">${legend}</div></div></div>`;
}
function spark(values){
  const vals = (values || []).map(v => Number(v || 0));
  const max = Math.max(...vals, 1);
  const count = Math.max(vals.length, 1);
  const width = 100;
  const gap = 1;
  const barWidth = Math.max((width - gap * (count - 1)) / count, 1);
  const rects = vals.map((v, i) => {
    const height = Math.max(4, (v / max) * 100);
    const x = i * (barWidth + gap);
    return `<rect x="${esc(x.toFixed(2))}" y="${esc((100 - height).toFixed(2))}" width="${esc(barWidth.toFixed(2))}" height="${esc(height.toFixed(2))}"></rect>`;
  }).join('');
  return `<svg class="sparkSvg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${rects}</svg>`;
}
function historySpark(values){
  const vals = (values || []).map(v => Number(v || 0));
  const max = Math.max(...vals, 1);
  const count = Math.max(vals.length, 1);
  const width = 100;
  const gap = 1;
  const barWidth = Math.max((width - gap * (count - 1)) / count, 1);
  const rects = vals.map((v, i) => {
    const height = Math.max(4, (v / max) * 100);
    const x = i * (barWidth + gap);
    return `<rect x="${esc(x.toFixed(2))}" y="${esc((100 - height).toFixed(2))}" width="${esc(barWidth.toFixed(2))}" height="${esc(height.toFixed(2))}"></rect>`;
  }).join('');
  return `<svg class="sparkSvg compact" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${rects}</svg>`;
}
function rememberResourceSample(data){
  const host = data.host || {};
  const mem = host.memory || {};
  const disk = host.disk || {};
  const load = host.load || {};
  const docker = data.docker || {};
  const containers = docker.containers || [];
  resourceHistory.push({
    at: data.generatedAt || new Date().toISOString(),
    memory: Number(mem.usedPercent || 0),
    disk: Number(disk.usedPercent || 0),
    load: Number(load.one || 0),
    containers: containers.length,
  });
  while (resourceHistory.length > 36) resourceHistory.shift();
}
function resourceHistoryPanel(){
  if (!resourceHistory.length) return '';
  const latest = resourceHistory[resourceHistory.length - 1];
  return `<div class="vizGrid"><div class="vizCard"><h3>Memory Trend</h3>${historySpark(resourceHistory.map(r => r.memory))}<div class="muted">${esc(latest.memory.toFixed(1))}% latest</div></div><div class="vizCard"><h3>Load Trend</h3>${historySpark(resourceHistory.map(r => r.load))}<div class="muted">${esc(latest.load.toFixed(2))} latest</div></div><div class="vizCard"><h3>Container Count</h3>${historySpark(resourceHistory.map(r => r.containers))}<div class="muted">${esc(latest.containers)} latest</div></div></div>`;
}
function fmtBytes(v){
  let value = Number(v || 0);
  const units = ['B','KiB','MiB','GiB','TiB'];
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return unit ? `${value.toFixed(1)} ${units[unit]}` : `${Math.round(value)} ${units[unit]}`;
}
function statusPill(label, ok){
  return `<span class="pill ${ok ? 'ok' : 'bad'}">${esc(label)}: ${ok ? 'OK' : 'No'}</span>`;
}
function options(rows, key, fallback=''){
  const vals = (rows || []).map(r => r[key]).filter(v => v !== undefined && v !== null);
  if (!vals.length && fallback) vals.push(fallback);
  return vals.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
}
function currencyBalanceOptions(rows, fallbackRows){
  const vals = rows || [];
  if (!vals.length) return options(fallbackRows, 'currency_id', '1');
  return vals.map(r => {
    const balance = r.balance ?? '';
    return `<option value="${esc(r.currency_id)}" data-balance="${esc(balance)}">currency ${esc(r.currency_id)} | balance ${esc(balance)}</option>`;
  }).join('');
}
function specializationOptions(rows, fallbackRows){
  const vals = rows || [];
  if (!vals.length) return options(fallbackRows, 'track_type');
  return vals.map(r => {
    const xp = r.xp_amount ?? '';
    const level = r.level ?? '';
    return `<option value="${esc(r.track_type)}" data-xp="${esc(xp)}" data-level="${esc(level)}">${esc(r.track_type)} | xp ${esc(xp)} | level ${esc(level)}</option>`;
  }).join('');
}
function inventoryOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">No inventories observed</option>';
  return vals.map(r => {
    const inventoryId = r.inventory_id ?? r.id ?? '';
    const owner = r.character_name || r.actor_id || 'unowned';
    const count = r.item_count ?? '';
    return `<option value="${esc(inventoryId)}" data-type="${esc(r.inventory_type ?? '')}">${esc(owner)} | inv ${esc(inventoryId)} | type ${esc(r.inventory_type)} | ${esc(count)} items</option>`;
  }).join('');
}
function inventoryTypeOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">Auto</option>';
  return '<option value="">Auto</option>' + vals.map(r => `<option value="${esc(r.inventory_type)}">type ${esc(r.inventory_type)} | ${esc(r.count)} inventories | cap ${esc(r.max_item_count)}</option>`).join('');
}
function partitionOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">No partitions found</option>';
  return vals.map(r => {
    const label = `${r.label || r.map || 'partition'} | id ${r.partition_id} | dim ${r.dimension_index ?? ''}${r.blocked ? ' | blocked' : ''}`;
    return `<option value="${esc(r.partition_id)}" data-map="${esc(r.map || '')}" data-label="${esc(r.label || '')}" data-dimension="${esc(r.dimension_index ?? '')}">${esc(label)}</option>`;
  }).join('');
}
function characterOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">No characters found</option>';
  return '<option value="">Select character</option>' + vals.map(r => {
    const label = `${r.character_name || 'unnamed'} | account ${r.account_id} | ${r.online_status || 'unknown'}`;
    return `<option value="${esc(r.account_id)}" data-name="${esc(r.character_name || '')}" data-controller="${esc(r.player_controller_id || '')}" data-status="${esc(r.online_status || '')}">${esc(label)}</option>`;
  }).join('');
}
function inventoryItemOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">No items found for selected character</option>';
  return '<option value="">Select item</option>' + vals.map(r => {
    const itemId = r.item_id ?? r.id ?? '';
    const template = r.template_id || r.item_template_id || 'item';
    const stack = r.stack_size ?? r.stack_count ?? '';
    const inventory = r.inventory_id ?? '';
    const position = r.position_index ?? r.slot_index ?? '';
    const label = `${template} | id ${itemId} | inv ${inventory} | stack ${stack} | pos ${position}`;
    return `<option value="${esc(itemId)}" data-stack="${esc(stack)}" data-template="${esc(template)}" data-inventory="${esc(inventory)}">${esc(label)}</option>`;
  }).join('');
}
function templateDatalist(ref){
  const templates = new Map();
  (ref.knownItemTemplates || []).forEach(r => templates.set(r.template_id, r.sources || 'known'));
  (ref.observedItemTemplates || []).forEach(r => templates.set(r.template_id, `observed ${r.count}`));
  return Array.from(templates.entries())
    .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
    .map(([id, label]) => `<option value="${esc(id)}" label="${esc(label)}"></option>`)
    .join('');
}
function checks(rows){
  return `<table><thead><tr><th>Check</th><th>Status</th><th>Value</th></tr></thead><tbody>${(rows || []).map(r=>`<tr><td>${esc(r.name)}</td><td class="${r.ok ? 'ok' : 'dangerText'}">${r.ok ? 'OK' : 'Needs attention'}</td><td>${esc(r.value ?? '')}</td></tr>`).join('')}</tbody></table>`;
}
function healthCell(ok, yes='online', no='offline'){
  return `<span class="pill ${ok ? 'ok' : 'bad'}">${ok ? yes : no}</span>`;
}
function mapStatusTable(rows){
  if (!rows || !rows.length) return '<div class="muted">No map status rows.</div>';
  return `<div class="tableWrap"><table><thead><tr><th>Map</th><th>Status</th><th>Ready</th><th>Alive</th><th>Active</th><th>Players</th><th>Game</th><th>IGW</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.label || r.map)}<br><span class="muted">${esc(r.map)} #${esc(r.partition_id)}</span></td><td>${healthCell(r.online)}</td><td>${healthCell(r.ready, 'yes', 'no')}</td><td>${healthCell(r.alive, 'yes', 'no')}</td><td>${healthCell(r.active, 'yes', 'no')}</td><td>${esc(r.players ?? 0)}</td><td>${esc(r.game)}</td><td>${esc(r.igw)}</td></tr>`).join('')}</tbody></table></div>`;
}
function mapTiles(rows){
  if (!rows || !rows.length) return '<div class="muted">No map rows.</div>';
  return `<div class="mapGrid">${rows.map(r => `<div class="mapTile ${r.online ? 'ok' : 'bad'}"><div class="name">${esc(r.label || r.map)}</div><div class="meta">${r.online ? 'online' : 'offline'} | ${esc(r.players ?? 0)} players</div></div>`).join('')}</div>`;
}
const haggaPoiPalette = ['#d5a13e', '#7fc27a', '#6fa8dc', '#d96f62', '#b78cff', '#6cc7bd', '#e1b75f', '#e89458'];
const haggaPoiPresetGroups = {Shipwrecks:true, Caves:true, TradingPosts:true, Outposts:true, Aql:true, Trainers:true};
function selectedHaggaPoiGroups(groups){
  if (!haggaPoiGroups || !Object.keys(haggaPoiGroups).length) {
    try {
      haggaPoiGroups = JSON.parse(sessionStorage.getItem('duneAdminHaggaPoiGroups') || '{}');
    } catch (e) {
      haggaPoiGroups = {};
    }
  }
  const selected = {};
  Object.keys(groups || {}).forEach(group => {
    selected[group] = Object.prototype.hasOwnProperty.call(haggaPoiGroups, group) ? haggaPoiGroups[group] === true : false;
  });
  return selected;
}
function saveHaggaPoiGroups(selected){
  haggaPoiGroups = selected;
  sessionStorage.setItem('duneAdminHaggaPoiGroups', JSON.stringify(selected));
}
function haggaPoiSummary(selected, pois){
  const enabled = Object.keys(selected || {}).filter(group => selected[group] === true).length;
  const markerCount = Array.isArray(pois?.markers) ? pois.markers.filter(marker => selected[marker.group] === true).length : 0;
  return enabled ? `${enabled} layer${enabled === 1 ? '' : 's'} / ${markerCount} markers` : 'POI layers off';
}
function haggaPoiOverlay(pois, selected){
  const markers = Array.isArray(pois?.markers) ? pois.markers : [];
  const groups = pois?.groups || {};
  const groupKeys = Object.keys(groups);
  const colors = {};
  groupKeys.forEach((group, index) => colors[group] = haggaPoiPalette[index % haggaPoiPalette.length]);
  return markers.filter(marker => selected[marker.group] === true).map(marker => {
    const x = clamp(Number(marker.x || 0) / 100, 0, 1000);
    const y = clamp(Number(marker.y || 0) / 100, 0, 1000);
    const group = (groups[marker.group] || {}).name || marker.group || 'POI';
    const name = marker.name || group;
    const color = colors[marker.group] || '#d5a13e';
    return `<g class="poiMarker" tabindex="0" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})"><title>${esc(group)}: ${esc(name)}</title><circle r="4.5" fill="${esc(color)}"></circle><text x="8" y="-8">${esc(name)}</text></g>`;
  }).join('');
}
function haggaPoiToggleBar(pois, selected){
  const groups = pois?.groups || {};
  const groupKeys = Object.keys(groups).filter(group => Number(groups[group]?.count || 0) > 0)
    .sort((a, b) => String(groups[a]?.name || a).localeCompare(String(groups[b]?.name || b), undefined, {sensitivity:'base'}));
  if (!groupKeys.length) return '';
  const colors = {};
  groupKeys.forEach((group, index) => colors[group] = haggaPoiPalette[index % haggaPoiPalette.length]);
  return `<div class="poiLegendHeader"><span id="haggaPoiSummary" class="muted">${esc(haggaPoiSummary(selected, pois))}</span><div class="toolbar"><button id="haggaPoiAllBtn">All</button><button id="haggaPoiPresetBtn">Preset</button><button id="haggaPoiClearBtn">Clear</button></div></div><div class="poiToggleBar" aria-label="POI layer toggles">${groupKeys.map(group => {
    const info = groups[group] || {};
    return `<label><span class="poiToggleLabel"><input type="checkbox" value="${esc(group)}"${selected[group] ? ' checked' : ''}><span class="poiSwatch" style="background:${esc(colors[group])}"></span><span>${esc(info.name || group)}</span></span><span class="poiCount">${esc(info.count || 0)}</span></label>`;
  }).join('')}</div>`;
}
function haggaBasinMapPanel(data){
  const players = data?.players || [];
  const pois = data?.pois || {};
  const selectedPois = selectedHaggaPoiGroups(pois.groups || {});
  const bounds = data?.bounds || {};
  const calibration = data?.calibration || {};
  const width = 1000;
  const height = 1000;
  const pad = 0;
  const mapExtent = 100000;
  const minX = Number.isFinite(Number(calibration.minX)) ? Number(calibration.minX) : -457200;
  const maxX = Number.isFinite(Number(calibration.maxX)) ? Number(calibration.maxX) : 355600;
  const minY = Number.isFinite(Number(calibration.minY)) ? Number(calibration.minY) : -457200;
  const maxY = Number.isFinite(Number(calibration.maxY)) ? Number(calibration.maxY) : 355600;
  const invertX = calibration.invertX === true;
  const invertY = calibration.invertY === true;
  const imageMinU = Number.isFinite(Number(calibration.imageMinU)) ? Number(calibration.imageMinU) : 0;
  const imageMaxU = Number.isFinite(Number(calibration.imageMaxU)) ? Number(calibration.imageMaxU) : 1;
  const imageMinV = Number.isFinite(Number(calibration.imageMinV)) ? Number(calibration.imageMinV) : 0;
  const imageMaxV = Number.isFinite(Number(calibration.imageMaxV)) ? Number(calibration.imageMaxV) : 1;
  const showReturnPoints = calibration.showReturnPoints === true;
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const worldToImageU = (x, y) => {
    const normalized = (Number(x) - minX) / spanX;
    const oriented = invertX ? 1 - normalized : normalized;
    return imageMinU + oriented * (imageMaxU - imageMinU);
  };
  const worldToImageV = (x, y) => {
    const normalized = (Number(y) - minY) / spanY;
    const oriented = invertY ? 1 - normalized : normalized;
    return imageMinV + oriented * (imageMaxV - imageMinV);
  };
  const px = (x, y) => clamp(pad + worldToImageU(x, y) * (width - pad * 2), 0, width);
  const py = (x, y) => clamp(pad + worldToImageV(x, y) * (height - pad * 2), 0, height);
  const gridSteps = 8;
  const grid = Array.from({length: gridSteps + 1}, (_, i) => {
    const t = i / gridSteps;
    const gx = pad + t * (width - pad * 2);
    const gy = pad + t * (height - pad * 2);
    const worldX = minX + t * spanX;
    const worldY = maxY - t * spanY;
    const xLabelY = i % 2 === 0 ? 18 : height - 10;
    const yLabelX = i % 2 === 0 ? 8 : width - 92;
    return `<line class="gridLine" x1="${gx}" y1="${pad}" x2="${gx}" y2="${height - pad}"></line><line class="gridLine" x1="${pad}" y1="${gy}" x2="${width - pad}" y2="${gy}"></line><text class="gridLabel" x="${clamp(gx + 4, 8, width - 96)}" y="${xLabelY}">X ${esc(Math.round(worldX))}</text><text class="gridLabel" x="${yLabelX}" y="${clamp(gy - 4, 18, height - 12)}">Y ${esc(Math.round(worldY))}</text>`;
  }).join('');
  const markers = players.map((p, index) => {
    const x = px(p.x, p.y);
    const y = py(p.x, p.y);
    const rx = p.return_map === 'HaggaBasin' && Number.isFinite(Number(p.return_x)) ? px(p.return_x, p.return_y) : null;
    const ry = p.return_map === 'HaggaBasin' && Number.isFinite(Number(p.return_y)) ? py(p.return_x, p.return_y) : null;
    const hasReturnPoint = showReturnPoints && rx !== null && ry !== null && Math.hypot(rx - x, ry - y) > 8;
    const name = p.character_name || `Player ${index + 1}`;
    const labelX = clamp(x + 14, 8, width - 190);
    const labelY = clamp(y - 12, 22, height - 24);
    const title = `${name} | pawn x ${Number(p.x).toFixed(0)}, y ${Number(p.y).toFixed(0)}, z ${Number(p.z || 0).toFixed(0)}${hasReturnPoint ? ` | return x ${Number(p.return_x).toFixed(0)}, y ${Number(p.return_y).toFixed(0)}, z ${Number(p.return_z || 0).toFixed(0)}` : ''}`;
    const returnMarker = hasReturnPoint ? `<line class="uncertainLine" x1="${x.toFixed(1)}" y1="${y.toFixed(1)}" x2="${rx.toFixed(1)}" y2="${ry.toFixed(1)}"></line><circle class="returnDot" cx="${rx.toFixed(1)}" cy="${ry.toFixed(1)}" r="7"><title>${esc(name)} return-info position</title></circle>` : '';
    return `<g class="playerMarker" tabindex="0" role="button" data-account-id="${esc(p.account_id || '')}" aria-label="${esc(title)}"><title>${esc(title)}</title>${returnMarker}<circle class="playerDot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="8"></circle><text class="playerLabel" x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}">${esc(name)}</text><text class="coordLabel" x="${labelX.toFixed(1)}" y="${(labelY + 16).toFixed(1)}">${esc(Math.round(Number(p.x || 0)))}, ${esc(Math.round(Number(p.y || 0)))}</text></g>`;
  }).join('');
  const poiMarkers = haggaPoiOverlay(pois, selectedPois);
  const empty = players.length ? '' : `<text class="emptyState" x="${width / 2}" y="${height / 2}">No online players with Hagga Basin coordinates.</text>`;
  const rows = players.map(p => ({
    character: p.character_name || '',
    account_id: p.account_id,
    server_map: p.label || p.farm_map || p.server_id || '',
    x: Math.round(Number(p.x || 0)),
    y: Math.round(Number(p.y || 0)),
    z: Math.round(Number(p.z || 0)),
    return_map: p.return_map || '',
    return_x: p.return_x === null || p.return_x === undefined ? '' : Math.round(Number(p.return_x)),
    return_y: p.return_y === null || p.return_y === undefined ? '' : Math.round(Number(p.return_y)),
    return_z: p.return_z === null || p.return_z === undefined ? '' : Math.round(Number(p.return_z)),
    last_login_time: p.last_login_time || ''
  }));
  const diagnosticRows = (data?.diagnostics || []).map(d => ({
    character: d.character_name || '',
    source: d.source || '',
    map: d.map || '',
    x: d.x === null || d.x === undefined ? '' : Math.round(Number(d.x)),
    y: d.y === null || d.y === undefined ? '' : Math.round(Number(d.y)),
    z: d.z === null || d.z === undefined ? '' : Math.round(Number(d.z)),
    partition: d.partition_id ?? '',
    ref: d.ref || '',
    assessment: d.assessment || ''
  }));
  const generatedAt = data?.generatedAt ? new Date(data.generatedAt).toLocaleTimeString() : '';
  return `<div class="panelBand"><div class="sectionHeader"><h2>Hagga Basin Coordinate Grid</h2><div class="toolbar"><span id="haggaMapCount" class="pill ${players.length ? 'ok' : ''}">${esc(players.length)} plotted</span><span id="haggaMapUpdated" class="pill">updated ${esc(generatedAt)}</span><span id="haggaMapHealth" class="pill warn">DB persistence position, not proven live</span><button id="haggaMapZoomOutBtn" title="Zoom map out">-</button><button id="haggaMapZoomInBtn" title="Zoom map in">+</button><button id="haggaMapResetBtn">Reset view</button><button id="toggleHaggaMapRefreshBtn" aria-pressed="${haggaMapAutoRefresh ? 'true' : 'false'}">${haggaMapAutoRefresh ? 'Pause map' : 'Resume map'}</button><button id="refreshHaggaMapBtn">Refresh map</button></div></div>${haggaPoiToggleBar(pois, selectedPois)}<div id="haggaMapSrStatus" class="srOnly" aria-live="polite">${esc(players.length)} Hagga Basin players plotted.</div><div id="haggaMapViewport" class="haggaMap"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Full Hagga Basin coordinate-grid map"><image class="mapImage" href="/static/hagga-basin.webp?v=${encodeURIComponent(ADMIN_PANEL_BUILD)}" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet"></image><rect class="mapShade" x="0" y="0" width="${width}" height="${height}"></rect>${grid}<text x="12" y="38" fill="var(--muted)" font-size="12">NW</text><text x="${width - 30}" y="${height - 12}" fill="var(--muted)" font-size="12">SE</text>${poiMarkers}${markers}${empty}</svg></div><div class="haggaMapStatus"><span class="pill warn">green: persisted actor transform</span><span class="pill ${showReturnPoints ? 'warn' : ''}">yellow return-info ${showReturnPoints ? 'shown' : 'hidden'}</span><span class="pill">POIs: Dune: Awakening Community Wiki CC BY-NC-SA 4.0</span><span class="pill">background: clean survival_1 tile composite</span><span class="pill">projection: world X -> image U, world Y -> image V</span><span class="pill">world X ${esc(Math.round(minX))}..${esc(Math.round(maxX))}, Y ${esc(Math.round(minY))}..${esc(Math.round(maxY))}${invertX ? ', flipped X' : ''}${invertY ? ', inverted Y' : ''}</span><span class="pill">image U ${esc(imageMinU.toFixed(2))}..${esc(imageMaxU.toFixed(2))}, V ${esc(imageMinV.toFixed(2))}..${esc(imageMaxV.toFixed(2))}</span></div><details open><summary>Coordinates</summary><div class="coordTable">${table(rows)}</div></details><details open><summary>Location Source Diagnostics</summary><div class="coordTable">${table(diagnosticRows)}</div></details></div>`;
}
function offlineTeleportPanel(ref, characterRows){
  const partitions = ref.worldPartitions || [];
  const calibration = ref.haggaCalibration || {};
  const haggaPartition = partitions.find(p => String(p.map || '').toLowerCase().includes('survival')) || partitions[0] || {};
  return `<div class="panelBand" id="offlineTeleportPanel"><div class="sectionHeader"><h2>Offline Teleport</h2><div class="toolbar"><span class="pill warn">requires Offline</span><span class="pill warn">targeted timeout is manual</span></div></div><p class="muted">Moves the selected player's stored pawn with <code>dune.admin_move_offline_player_to_partition</code>. Online players must first be disconnected by the documented targeted timeout mechanism or a future native kick path.</p><div class="grid"><label>Player<select id="teleportAccount">${characterOptions(characterRows)}</select></label><label>Partition<select id="teleportPartition">${partitionOptions(partitions)}</select></label><label>X<input id="teleportX" inputmode="decimal" value="0"></label><label>Y<input id="teleportY" inputmode="decimal" value="0"></label><label>Z<input id="teleportZ" inputmode="decimal" value="9000"></label></div><div class="commandBar"><button id="teleportPreviewBtn" class="primary">Preview teleport</button><button id="teleportExecuteBtn" class="danger">Execute offline teleport</button><button id="teleportUseSelectedBtn">Use selected player position</button></div><div id="offlineTeleportMap" class="haggaMap teleportMap" data-default-partition="${esc(haggaPartition.partition_id || '')}" data-calibration="${esc(JSON.stringify(calibration))}"></div><pre id="teleportResult"></pre></div>`;
}
function renderOfflineTeleportMap(){
  const box = document.getElementById('offlineTeleportMap');
  if (!box) return;
  const width = 1000, height = 1000, pad = 0;
  let calibration = {};
  try { calibration = JSON.parse(box.dataset.calibration || '{}'); } catch (e) { calibration = {}; }
  const minX = Number.isFinite(Number(calibration.minX)) ? Number(calibration.minX) : -457200;
  const maxX = Number.isFinite(Number(calibration.maxX)) ? Number(calibration.maxX) : 355600;
  const minY = Number.isFinite(Number(calibration.minY)) ? Number(calibration.minY) : -457200;
  const maxY = Number.isFinite(Number(calibration.maxY)) ? Number(calibration.maxY) : 355600;
  const invertX = calibration.invertX === true;
  const invertY = calibration.invertY === true;
  const imageMinU = Number.isFinite(Number(calibration.imageMinU)) ? Number(calibration.imageMinU) : 0;
  const imageMaxU = Number.isFinite(Number(calibration.imageMaxU)) ? Number(calibration.imageMaxU) : 1;
  const imageMinV = Number.isFinite(Number(calibration.imageMinV)) ? Number(calibration.imageMinV) : 0;
  const imageMaxV = Number.isFinite(Number(calibration.imageMaxV)) ? Number(calibration.imageMaxV) : 1;
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const worldToImageU = (x) => {
    const normalized = (Number(x) - minX) / spanX;
    const oriented = invertX ? 1 - normalized : normalized;
    return imageMinU + oriented * (imageMaxU - imageMinU);
  };
  const worldToImageV = (y) => {
    const normalized = (Number(y) - minY) / spanY;
    const oriented = invertY ? 1 - normalized : normalized;
    return imageMinV + oriented * (imageMaxV - imageMinV);
  };
  const imageUToWorld = (u) => {
    const oriented = (u - imageMinU) / ((imageMaxU - imageMinU) || 1);
    const normalized = invertX ? 1 - oriented : oriented;
    return minX + normalized * spanX;
  };
  const imageVToWorld = (v) => {
    const oriented = (v - imageMinV) / ((imageMaxV - imageMinV) || 1);
    const normalized = invertY ? 1 - oriented : oriented;
    return minY + normalized * spanY;
  };
  const px = (x) => clamp(pad + worldToImageU(x) * (width - pad * 2), 0, width);
  const py = (y) => clamp(pad + worldToImageV(y) * (height - pad * 2), 0, height);
  const tx = Number(document.getElementById('teleportX')?.value || 0);
  const ty = Number(document.getElementById('teleportY')?.value || 0);
  const target = Number.isFinite(tx) && Number.isFinite(ty) ? `<circle class="teleportTargetDot" cx="${px(tx).toFixed(1)}" cy="${py(ty).toFixed(1)}" r="10"></circle><text class="teleportTargetLabel" x="${clamp(px(tx) + 14, 8, width - 190).toFixed(1)}" y="${clamp(py(ty) - 14, 22, height - 22).toFixed(1)}">target ${esc(Math.round(tx))}, ${esc(Math.round(ty))}</text>` : '';
  box.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Click Hagga Basin map to choose teleport coordinates"><image class="mapImage" href="/static/hagga-basin.webp?v=${encodeURIComponent(ADMIN_PANEL_BUILD)}" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet"></image><rect class="mapShade" x="0" y="0" width="${width}" height="${height}"></rect>${target}</svg><div class="haggaMapStatus"><span class="pill">click map to fill X/Y</span><span class="pill">Z remains editable</span><span class="pill">Hagga Basin calibration</span></div>`;
  box.querySelector('svg')?.addEventListener('click', e => {
    const rect = e.currentTarget.getBoundingClientRect();
    const imageU = clamp((e.clientX - rect.left) / rect.width, 0, 1);
    const imageV = clamp((e.clientY - rect.top) / rect.height, 0, 1);
    document.getElementById('teleportX').value = imageUToWorld(imageU).toFixed(3);
    document.getElementById('teleportY').value = imageVToWorld(imageV).toFixed(3);
    const partition = document.getElementById('teleportPartition');
    if (partition && box.dataset.defaultPartition) partition.value = box.dataset.defaultPartition;
    renderOfflineTeleportMap();
  });
}
function initHaggaMapPanZoom(container){
  const viewport = container.querySelector('#haggaMapViewport');
  const content = viewport?.querySelector('svg');
  if (!viewport || !content) return;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  let drag = null;
  function fittedContent(){
    const rect = viewport.getBoundingClientRect();
    const viewBox = content.viewBox?.baseVal;
    const viewWidth = viewBox?.width || 1;
    const viewHeight = viewBox?.height || 1;
    const contentAspect = viewWidth / viewHeight;
    const fittedWidth = Math.min(rect.width, rect.height * contentAspect);
    return {width:fittedWidth, height:fittedWidth / contentAspect};
  }
  function stretchX(){
    const rect = viewport.getBoundingClientRect();
    const fitted = fittedContent();
    return fitted.width > 0 ? rect.width / fitted.width : 1;
  }
  function constrain(){
    const rect = viewport.getBoundingClientRect();
    const fitted = fittedContent();
    const maxX = Math.max(0, (fitted.width * stretchX() * haggaMapZoomState.scale - rect.width) / 2);
    const maxY = Math.max(0, (fitted.height * haggaMapZoomState.scale - rect.height) / 2);
    haggaMapZoomState.x = clamp(haggaMapZoomState.x, -maxX, maxX);
    haggaMapZoomState.y = clamp(haggaMapZoomState.y, -maxY, maxY);
  }
  function apply(){
    constrain();
    content.style.transform = `translate(${haggaMapZoomState.x}px, ${haggaMapZoomState.y}px) scale(${haggaMapZoomState.scale}) scaleX(${stretchX()})`;
  }
  function zoomAt(nextScale, clientX, clientY){
    const rect = viewport.getBoundingClientRect();
    const oldScale = haggaMapZoomState.scale;
    const newScale = clamp(nextScale, 1, 8);
    const px = (clientX - rect.left - rect.width / 2 - haggaMapZoomState.x) / stretchX();
    const py = clientY - rect.top - rect.height / 2 - haggaMapZoomState.y;
    haggaMapZoomState.x -= px * (newScale / oldScale - 1);
    haggaMapZoomState.y -= py * (newScale / oldScale - 1);
    haggaMapZoomState.scale = newScale;
    apply();
  }
  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    zoomAt(haggaMapZoomState.scale * (e.deltaY < 0 ? 1.18 : 0.84), e.clientX, e.clientY);
  }, {passive:false});
  viewport.addEventListener('pointerdown', e => {
    if (e.button !== undefined && e.button !== 0) return;
    e.preventDefault();
    drag = {id:e.pointerId, x:e.clientX, y:e.clientY, startX:haggaMapZoomState.x, startY:haggaMapZoomState.y};
    haggaMapSuppressMarkerClick = false;
    viewport.classList.add('isDragging');
    viewport.setPointerCapture(e.pointerId);
  }, true);
  viewport.addEventListener('pointermove', e => {
    if (!drag || drag.id !== e.pointerId) return;
    e.preventDefault();
    if (Math.abs(e.clientX - drag.x) > 3 || Math.abs(e.clientY - drag.y) > 3) haggaMapSuppressMarkerClick = true;
    haggaMapZoomState.x = drag.startX + e.clientX - drag.x;
    haggaMapZoomState.y = drag.startY + e.clientY - drag.y;
    apply();
  }, true);
  function endDrag(e){
    if (drag && drag.id === e.pointerId) {
      e.preventDefault();
      drag = null;
      viewport.classList.remove('isDragging');
    }
  }
  viewport.addEventListener('pointerup', endDrag, true);
  viewport.addEventListener('pointercancel', endDrag, true);
  viewport.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    e.preventDefault();
    drag = {id:'mouse', x:e.clientX, y:e.clientY, startX:haggaMapZoomState.x, startY:haggaMapZoomState.y};
    haggaMapSuppressMarkerClick = false;
    viewport.classList.add('isDragging');
  }, true);
  document.addEventListener('mousemove', e => {
    if (!drag || drag.id !== 'mouse') return;
    e.preventDefault();
    if (Math.abs(e.clientX - drag.x) > 3 || Math.abs(e.clientY - drag.y) > 3) haggaMapSuppressMarkerClick = true;
    haggaMapZoomState.x = drag.startX + e.clientX - drag.x;
    haggaMapZoomState.y = drag.startY + e.clientY - drag.y;
    apply();
  }, true);
  document.addEventListener('mouseup', e => {
    if (!drag || drag.id !== 'mouse') return;
    e.preventDefault();
    drag = null;
    viewport.classList.remove('isDragging');
  }, true);
  viewport.addEventListener('dblclick', e => zoomAt(haggaMapZoomState.scale < 2 ? 2 : 1, e.clientX, e.clientY));
  container.querySelector('#haggaMapZoomInBtn')?.addEventListener('click', () => {
    const rect = viewport.getBoundingClientRect();
    zoomAt(haggaMapZoomState.scale * 1.35, rect.left + rect.width / 2, rect.top + rect.height / 2);
  });
  container.querySelector('#haggaMapZoomOutBtn')?.addEventListener('click', () => {
    const rect = viewport.getBoundingClientRect();
    zoomAt(haggaMapZoomState.scale / 1.35, rect.left + rect.width / 2, rect.top + rect.height / 2);
  });
  container.querySelector('#haggaMapResetBtn')?.addEventListener('click', () => {
    haggaMapZoomState = {scale:1, x:0, y:0};
    apply();
  });
  window.addEventListener('resize', apply, {once:true});
  apply();
}
function wireHaggaMapControls(container){
  initHaggaMapPanZoom(container);
  container.querySelectorAll('.poiToggleBar input[type=checkbox]').forEach(input => {
    input.addEventListener('change', () => {
      const selected = selectedHaggaPoiGroups({});
      selected[input.value] = input.checked;
      saveHaggaPoiGroups(selected);
      refreshHaggaMap({force:true}).catch(e => reportClientError(e, 'Refresh Hagga map'));
    });
  });
  container.querySelector('#haggaPoiClearBtn')?.addEventListener('click', () => {
    const selected = selectedHaggaPoiGroups({});
    Object.keys(selected).forEach(group => selected[group] = false);
    saveHaggaPoiGroups(selected);
    refreshHaggaMap({force:true}).catch(e => reportClientError(e, 'Refresh Hagga map'));
  });
  container.querySelector('#haggaPoiAllBtn')?.addEventListener('click', () => {
    const selected = selectedHaggaPoiGroups({});
    Object.keys(selected).forEach(group => selected[group] = true);
    saveHaggaPoiGroups(selected);
    refreshHaggaMap({force:true}).catch(e => reportClientError(e, 'Refresh Hagga map'));
  });
  container.querySelector('#haggaPoiPresetBtn')?.addEventListener('click', () => {
    const selected = selectedHaggaPoiGroups({});
    Object.keys(selected).forEach(group => selected[group] = haggaPoiPresetGroups[group] === true);
    saveHaggaPoiGroups(selected);
    refreshHaggaMap({force:true}).catch(e => reportClientError(e, 'Refresh Hagga map'));
  });
  container.querySelectorAll('.playerMarker[data-account-id]').forEach(marker => {
    marker.addEventListener('click', e => {
      if (haggaMapSuppressMarkerClick) {
        e.preventDefault();
        e.stopPropagation();
        haggaMapSuppressMarkerClick = false;
        return;
      }
      openPlayerModal(marker.dataset.accountId);
    });
    marker.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openPlayerModal(marker.dataset.accountId);
      }
    });
  });
  container.querySelector('#refreshHaggaMapBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Refreshing...', () => refreshHaggaMap({force:true})));
  container.querySelector('#toggleHaggaMapRefreshBtn')?.addEventListener('click', () => {
    haggaMapAutoRefresh = !haggaMapAutoRefresh;
    sessionStorage.setItem('duneAdminHaggaMapAutoRefresh', haggaMapAutoRefresh ? 'on' : 'off');
    notify(haggaMapAutoRefresh ? 'Hagga map refresh resumed' : 'Hagga map refresh paused');
    refreshHaggaMap({force:true}).catch(e => reportClientError(e, 'Refresh Hagga map'));
  });
}
async function refreshHaggaMap(opts={}){
  const container = document.getElementById('haggaBasinMap');
  if (!container) return;
  if (document.hidden && !opts.force) return;
  if (haggaMapRefreshInFlight) return;
  haggaMapRefreshInFlight = true;
  try {
    const data = await api('/api/players/hagga-basin', {timeoutMs: 5000});
    haggaMapLastGoodHtml = haggaBasinMapPanel(data);
    container.innerHTML = haggaMapLastGoodHtml;
    wireHaggaMapControls(container);
  } catch (e) {
    const health = container.querySelector('#haggaMapHealth');
    if (health) {
      health.className = 'pill warn';
      health.textContent = `stale: ${e.message}`;
    } else {
      container.innerHTML = haggaMapLastGoodHtml || `<div class="panelBand"><h2>Hagga Basin Player Map</h2><div class="dangerText">${esc(e.message)}</div></div>`;
    }
    throw e;
  } finally {
    haggaMapRefreshInFlight = false;
  }
}
function healthViz(health){
  const verdicts = health.verdicts || [];
  const maps = health.mapStatus || [];
  const okVerdicts = verdicts.filter(v => v.ok).length;
  const onlineMaps = maps.filter(m => m.online).length;
  const playerValues = maps.map(m => Number(m.players || 0));
  return `<div class="vizGrid">${donut('Map State', [
    {label:'Online', value:onlineMaps, color:'var(--ok)'},
    {label:'Offline', value:Math.max(maps.length - onlineMaps, 0), color:'var(--danger)'}
  ])}${donut('Health Verdicts', [
    {label:'OK', value:okVerdicts, color:'var(--ok)'},
    {label:'Attention', value:Math.max(verdicts.length - okVerdicts, 0), color:'var(--warn)'}
  ])}<div class="vizCard"><h3>Players By Map</h3>${spark(playerValues)}<div class="muted">${esc(playerValues.reduce((a,b)=>a+b,0))} reported players across ${esc(maps.length)} maps</div></div></div>`;
}
function overviewHealthCards(health){
  const verdicts = health.verdicts || [];
  const maps = health.mapStatus || [];
  const okVerdicts = verdicts.filter(v => v.ok).length;
  const onlineMaps = maps.filter(m => m.online).length;
  const playerValues = maps.map(m => Number(m.players || 0));
  const offlineMaps = Math.max(maps.length - onlineMaps, 0);
  const attentionVerdicts = Math.max(verdicts.length - okVerdicts, 0);
  const players = playerValues.reduce((a,b)=>a+b,0);
  return `${summaryHoverCard('Map State', `${onlineMaps}/${maps.length || 0}`, `${offlineMaps} offline`, `<div class="panelBand"><h2>Map Online/Offline</h2>${mapTiles(maps)}${mapStatusTable(maps)}</div>`, offlineMaps ? 'dangerText' : 'ok')}${summaryHoverCard('Health Verdicts', okVerdicts, `${attentionVerdicts} attention`, `<div class="panelBand"><h2>Health Verdict</h2>${checks(verdicts)}</div>`, attentionVerdicts ? 'dangerText' : 'ok')}${summaryHoverCard('Players By Map', players, `${maps.length} maps`, `<div class="panelBand"><h2>Players By Map</h2>${spark(playerValues)}${mapStatusTable(maps)}</div>`)}`;
}
function overviewResourceCard(resources){
  const data = resources || {};
  const host = data.host || {};
  const mem = host.memory || {};
  const load = host.load || {};
  const cpuCount = Number(host.cpuCount || 1);
  const containers = ((data.docker || {}).containers || []).filter(r => !r.error);
  const cpuPercent = Math.round(clamp((Number(load.one || 0) / Math.max(cpuCount, 1)) * 100));
  const memPercent = mem.usedPercent ?? '?';
  const rx = containers.reduce((sum, r) => sum + Number(r.netRxBytes || 0), 0);
  const tx = containers.reduce((sum, r) => sum + Number(r.netTxBytes || 0), 0);
  const previous = overviewResourcePrevious;
  const seconds = previous?.at ? Math.max((Date.now() - previous.at) / 1000, 1) : 0;
  const rxRate = previous ? Math.max((rx - previous.rx) / seconds, 0) : 0;
  const txRate = previous ? Math.max((tx - previous.tx) / seconds, 0) : 0;
  const topCpu = containers
    .filter(r => r.cpuPercent !== undefined && r.cpuPercent !== null)
    .sort((a, b) => Number(b.cpuPercent || 0) - Number(a.cpuPercent || 0))
    .slice(0, 5);
  const detail = `<div class="panelBand"><h2>Server Load</h2><div class="metricGrid">${metric('Load Average', `${load.one ?? '?'} / ${load.five ?? '?'} / ${load.fifteen ?? '?'}`)}${metric('RAM', `${fmtBytes(mem.usedBytes)} / ${fmtBytes(mem.totalBytes)}`)}${metric('CPU Pressure', `${cpuPercent}% of ${cpuCount} cores`)}${metric('Network Rate', `Rx ${fmtBytes(rxRate)}/s Tx ${fmtBytes(txRate)}/s`)}</div><div class="barList">${bar('CPU Load', cpuPercent, 100, `${cpuPercent}%`)}${bar('RAM', mem.usedPercent || 0, 100, `${mem.usedPercent ?? '?'}%`)}</div>${topCpu.length ? `<h3>Top Container CPU</h3><div class="barList">${topCpu.map(r => bar(r.service || r.name, r.cpuPercent || 0, 100, `${r.cpuPercent ?? 0}%`)).join('')}</div>` : '<div class="muted">No live container CPU sample yet.</div>'}</div>`;
  const meta = `RAM ${memPercent}% | Rx ${fmtBytes(rxRate)}/s Tx ${fmtBytes(txRate)}/s`;
  return summaryHoverCard('Server Load', `${cpuPercent}% CPU`, meta, detail, cpuPercent >= 90 || Number(mem.usedPercent || 0) >= 90 ? 'dangerText' : '');
}
function overviewRealtimeHtml(health, rosterCounts={}, resources=null){
  const state = health || {};
  const summary = state.summary || {};
  const players = (state.farmState || []).reduce((sum, r) => sum + Number(r.connected_players || 0), 0);
  const playerPeak = state.playerPeak || {};
  const resourcesCard = resources ? overviewResourceCard(resources) : metric('Server Load', 'sampling');
  return `${metric('Ready Servers', `${summary.readyAlive ?? 0}/${summary.expectedPartitions ?? 0}`, summary.readyAlive === summary.expectedPartitions ? 'ok' : 'dangerText')}${metric('Online Maps', `${summary.onlineMaps ?? 0}/${summary.totalMaps ?? 0}`, summary.onlineMaps === summary.totalMaps ? 'ok' : 'dangerText')}${metric('Reported Players', players)}${metric('Peak Today', playerPeak.peak ?? summary.peakPlayersToday ?? 0)}${metric('Characters', rosterCounts.total ?? 0)}${resourcesCard}${overviewHealthCards(state)}`;
}
function opsRealtimeMetricsHtml(health){
  const pc = (health || {}).playerCounts || {};
  return `${metric('Connected Players', pc.connected_players_reported ?? 0)}${metric('Online Controllers', pc.online_controller_ids ?? 0)}${metric('Recent Online State', pc.online_or_recently_disconnected ?? 0)}${metric('Grace Entries', pc.grace_period_entries ?? 0)}`;
}
function renderOverviewRealtime(health){
  const container = document.getElementById('overviewRealtime');
  if (!container) return;
  overviewHealthSnapshot = health;
  container.innerHTML = overviewRealtimeHtml(health, overviewRosterCounts, overviewResourceSnapshot);
}
function renderOpsRealtime(health){
  const metrics = document.getElementById('opsRealtimeMetrics');
  if (metrics) metrics.innerHTML = opsRealtimeMetricsHtml(health);
  const viz = document.getElementById('opsHealthViz');
  if (viz) viz.innerHTML = healthViz(health);
  const verdicts = document.getElementById('opsHealthVerdicts');
  if (verdicts) {
    verdicts.innerHTML = checks(health.verdicts);
    makeSortableTables(verdicts);
  }
  const mapStatus = document.getElementById('opsMapStatus');
  if (mapStatus) {
    mapStatus.innerHTML = `${mapTiles(health.mapStatus)}${mapStatusTable(health.mapStatus)}`;
    makeSortableTables(mapStatus);
  }
  const rawFarm = document.getElementById('opsRawFarmState');
  if (rawFarm) {
    rawFarm.innerHTML = table(health.farmState);
    makeSortableTables(rawFarm);
  }
  const partitions = document.getElementById('opsPartitions');
  if (partitions) {
    partitions.innerHTML = table(health.partitions);
    makeSortableTables(partitions);
  }
}
async function refreshRealtimeHealth(opts={}){
  if (healthRefreshInFlight) return;
  if (document.hidden && !opts.force) return;
  if (current !== 'overview' && current !== 'ops') return;
  healthRefreshInFlight = true;
  try {
    const health = await api('/api/ops/health', {timeoutMs: 7000});
    if (current === 'overview') renderOverviewRealtime(health);
    else if (current === 'ops') renderOpsRealtime(health);
    updateLastRefresh('Health refreshed');
  } catch (e) {
    announce(`Health refresh failed: ${e.message}`);
  } finally {
    healthRefreshInFlight = false;
  }
}
async function refreshOverviewResources(opts={}){
  if (resourceRefreshInFlight) return;
  if (document.hidden && !opts.force) return;
  if (current !== 'overview') return;
  resourceRefreshInFlight = true;
  try {
    const resources = await api('/api/ops/resources?live=1', {timeoutMs: 8000});
    const containers = ((resources.docker || {}).containers || []).filter(r => !r.error);
    const rx = containers.reduce((sum, r) => sum + Number(r.netRxBytes || 0), 0);
    const tx = containers.reduce((sum, r) => sum + Number(r.netTxBytes || 0), 0);
    overviewResourcePrevious = overviewResourceSnapshot ? {rx: overviewResourceSnapshot.rxBytes || 0, tx: overviewResourceSnapshot.txBytes || 0, at: overviewResourceSnapshot.sampledAt || Date.now()} : null;
    overviewResourceSnapshot = {...resources, rxBytes: rx, txBytes: tx, sampledAt: Date.now()};
    if (overviewHealthSnapshot) renderOverviewRealtime(overviewHealthSnapshot);
    updateLastRefresh('Resources refreshed');
  } catch (e) {
    announce(`Resource refresh failed: ${e.message}`);
  } finally {
    resourceRefreshInFlight = false;
  }
}
function startHealthRefresh(){
  if (healthTimer) clearInterval(healthTimer);
  healthTimer = setInterval(() => {
    if (autoRefresh) refreshRealtimeHealth().catch(() => {});
  }, 2500);
}
function summaryHoverCard(label, value, meta, content, tone=''){
  return `<div class="summaryCard" tabindex="0"><h3>${esc(label)}</h3><div class="summaryValue ${tone}">${esc(value)}</div><div class="summaryMeta">${esc(meta)}</div><div class="summaryHover" role="dialog" aria-label="${esc(label)} details">${content}</div></div>`;
}
function steamProfileCell(r){
  const platform = String(r?.platform_name || '');
  const platformId = String(r?.platform_id || '').trim();
  if (platform.toLowerCase() !== 'steam' || !platformId) return `${esc(platform)} ${esc(platformId)}`.trim();
  const persona = String(r?.steam_persona_name || '').trim();
  const label = persona ? `${persona} (${platformId})` : platformId;
  const href = r?.steam_profile_url || `https://steamcommunity.com/profiles/${encodeURIComponent(platformId)}`;
  return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}
function characterRosterTable(rows){
  if (!rows || !rows.length) return '<div class="muted">No characters in this group.</div>';
  return `<div class="tableWrap"><table class="dataDense"><thead><tr><th>Character</th><th>Status</th><th>Life</th><th>Map</th><th>Account</th><th>Last Login</th></tr></thead><tbody>${rows.map(r=>`<tr data-id="${esc(r.account_id ?? '')}"><td>${esc(r.character_name || 'unnamed')}<br><span class="muted">${steamProfileCell(r)}</span></td><td>${esc(r.online_status || '')}</td><td>${esc(r.life_state || '')}</td><td>${esc(r.map || r.server_id || '')}</td><td>${esc(r.account_id || '')}</td><td>${esc(r.last_login_time || '')}</td></tr>`).join('')}</tbody></table></div>`;
}
function characterRosterPanel(roster){
  const counts = roster.counts || {};
  const chart = donut('Player State', [
    {label:'Online', value:Number(counts.online || 0), color:'var(--ok)'},
    {label:'Offline', value:Number(counts.offline || 0), color:'var(--muted)'}
  ]);
  return `<div class="rosterPanel"><div class="sectionHeader"><h2>Roster</h2><div class="toolbar"><input class="filterInput rosterFilter" placeholder="Filter players, IDs, maps"></div></div><div class="metricGrid">${metric('Online Players', counts.online ?? 0, Number(counts.online || 0) ? 'ok' : '')}${metric('Offline Players', counts.offline ?? 0)}${metric('Total Characters', counts.total ?? 0)}</div><div class="vizGrid">${chart}<div class="vizCard"><h3>Roster Ratio</h3><div class="barList">${bar('Online', counts.online || 0, counts.total || 1)}${bar('Offline', counts.offline || 0, counts.total || 1)}</div></div></div><div class="twoCol"><div class="panelBand"><div class="splitHeader"><h2>Online Players</h2><span class="pill ok">${esc(counts.online ?? 0)} online</span></div>${characterRosterTable(roster.online)}</div><div class="panelBand"><div class="splitHeader"><h2>Offline Players</h2><span class="pill">${esc(counts.offline ?? 0)} offline</span></div>${characterRosterTable(roster.offline)}</div></div></div>`;
}
function probeTable(rows){
  if (!rows || !rows.length) return '<div class="muted">No probes.</div>';
  return `<div class="tableWrap"><table><thead><tr><th>Name</th><th>Status</th><th>Target</th><th>Latency</th><th>HTTP</th><th>Error</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${healthCell(r.ok || [401,403,404].includes(r.httpStatus), r.ok ? 'OK' : 'reachable', 'down')}</td><td>${esc(r.target)}</td><td>${esc(r.latencyMs)}ms</td><td>${esc(r.httpStatus ?? '')}</td><td>${esc(r.error ?? '')}</td></tr>`).join('')}</tbody></table></div>`;
}
function auditEventsTable(events){
  const rows = (events || []).filter(e => {
    const detail = String(e.error || e.target || '');
    if (e.action === 'auth-failed') return false;
    if (e.action === 'post-rejected' && detail.toLowerCase().includes('admin token')) return false;
    return true;
  });
  const display = rows.slice(0, 40);
  if (!display.length) return '<div class="muted">No recent actionable audit events.</div>';
  return `<div class="eventList">${display.map(e => {
    const detail = e.error || e.target || e.command || e.template_id || e.backup_path || e.job_id || '';
    return `<div class="eventItem"><div class="eventItemHead"><b>${esc(e.action || '')}</b>${healthCell(e.ok !== false, 'OK', 'failed')}</div><div class="muted">${esc(String(e.ts || '').replace('T', ' ').replace('Z', ''))} ${esc(e.method || '')} ${esc(e.path || '')}</div>${detail ? `<div>${esc(detail)}</div>` : ''}</div>`;
  }).join('')}</div>`;
}
function announcementPanel(state){
  const active = (state.jobs || []).filter(j => ['scheduled','delivering'].includes(j.status));
  const latest = active[active.length - 1] || (state.jobs || []).slice(-1)[0] || null;
  const delayOptions = [
    ['immediate','Immediate'], ['30s','30 sec'], ['60s','60 sec'], ['5min','5 min'],
    ['10min','10 min'], ['15min','15 min'], ['30min','30 min'], ['60min','60 min'],
    ['1hr','1 hr'], ['2hr','2 hr'], ['3hr','3 hr'], ['4hr','4 hr'],
    ['6hr','6 hr'], ['12hr','12 hr']
  ].map(([value,label]) => `<option value="${value}">${label}</option>`).join('');
  const jobSummary = latest ? `<pre id="announcementState">${esc(JSON.stringify(latest, null, 2))}</pre>` : '<div class="muted">No scheduled announcement.</div>';
  const delivery = state.lastDelivery ? `<pre>${esc(JSON.stringify(state.lastDelivery, null, 2))}</pre>` : '<div class="muted">No delivery attempts yet.</div>';
  return `<div class="card"><h2>Announcement Only</h2><p class="muted">Sends warning messages without restarting anything.</p><div class="grid"><label>Message until<select id="announceDelay">${delayOptions}</select></label><label>Repeat every<select id="announceRepeat"><option value="0">Do not repeat</option><option value="30">30 sec</option><option value="60" selected>60 sec</option><option value="300">5 min</option><option value="600">10 min</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option></select></label></div><label>Message<textarea id="announceMessage" rows="3" class="compactTextarea">Server restart soon. Please get to a safe place.</textarea></label><p><button id="scheduleAnnouncementBtn" class="primary">Schedule announcement</button> <button id="cancelAnnouncementBtn" class="danger">Cancel active announcement</button></p><details><summary>Current announcement state</summary>${jobSummary}</details><details><summary>Last delivery</summary>${delivery}</details></div>`;
}
function restartPanel(state){
  const active = (state.jobs || []).filter(j => ['scheduled','executing'].includes(j.status));
  const latest = active[active.length - 1] || (state.jobs || []).slice(-1)[0] || null;
  const targets = state.targets || {};
  const targetOptions = Object.entries(targets).map(([key, meta]) => `<option value="${esc(key)}">${esc(meta.label || key)}</option>`).join('');
  const delayOptions = [
    ['immediate','Immediate'], ['30s','30 sec'], ['60s','60 sec'], ['5min','5 min'],
    ['10min','10 min'], ['15min','15 min'], ['30min','30 min'], ['60min','60 min'],
    ['1hr','1 hr'], ['2hr','2 hr'], ['3hr','3 hr'], ['4hr','4 hr'],
    ['6hr','6 hr'], ['12hr','12 hr']
  ].map(([value,label]) => `<option value="${value}">${label}</option>`).join('');
  const jobSummary = latest ? `<pre>${esc(JSON.stringify(latest, null, 2))}</pre>` : '<div class="muted">No scheduled restart.</div>';
  const execution = state.lastExecution ? `<pre>${esc(JSON.stringify(state.lastExecution, null, 2))}</pre>` : '<div class="muted">No restart execution attempts yet.</div>';
  return `<div class="card"><h2>Maintenance Job</h2><p class="muted">Stops the selected services, takes the maintenance backup, checks the Steam package image tag, starts them again, and waits for map readiness.</p><div class="grid"><label>Target<select id="restartTarget">${targetOptions}</select></label><label>Action<select id="restartAction"><option value="restart" selected>Restart target</option><option value="shutdown">Shutdown target</option></select></label><label>Run after<select id="restartDelay">${delayOptions}</select></label><label>Repeat notice every<select id="restartRepeat"><option value="0">Do not repeat</option><option value="30">30 sec</option><option value="60" selected>60 sec</option><option value="300">5 min</option><option value="600">10 min</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option></select></label><label>Execution<select id="restartExecute"><option value="false" selected>Dry-run schedule</option><option value="true">Execute hook</option></select></label></div><div class="toolbar checkToolbar"><label><input id="restartBackup" type="checkbox" checked> Backup before execution</label><label><input id="restartAnnounce" type="checkbox" checked> Send in-game warnings</label></div><label>Warning message<textarea id="restartMessage" rows="3" class="compactTextarea">Server maintenance soon. Please get to a safe place.</textarea></label><p><button id="scheduleRestartBtn" class="primary">Schedule maintenance</button> <button id="cancelRestartBtn" class="danger">Cancel active job</button></p><details><summary>Current job state</summary>${jobSummary}</details><details><summary>Last execution</summary>${execution}</details></div>`;
}
function signalList(groups){
  return Object.entries(groups || {}).map(([group, rows]) => `<div class="card"><h2>${esc(group)}</h2><table><thead><tr><th>Name</th><th>Value</th><th>Why</th></tr></thead><tbody>${(rows || []).map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(Array.isArray(r.value) ? r.value.join(', ') : r.value)}</td><td>${esc(r.why)}</td></tr>`).join('')}</tbody></table></div>`).join('');
}
function resourceViz(data){
  const host = data.host || {};
  const mem = host.memory || {};
  const disk = host.disk || {};
  const load = host.load || {};
  const cpuCount = Number(host.cpuCount || 1);
  const docker = data.docker || {};
  const containers = docker.containers || [];
  const cpuRows = containers
    .filter(r => r.cpuPercent !== undefined && r.cpuPercent !== null && !r.error)
    .sort((a, b) => Number(b.cpuPercent || 0) - Number(a.cpuPercent || 0))
    .slice(0, 8);
  const memRows = containers
    .filter(r => r.memoryPercent !== undefined && r.memoryPercent !== null && !r.error)
    .sort((a, b) => Number(b.memoryPercent || 0) - Number(a.memoryPercent || 0))
    .slice(0, 8);
  const running = containers.filter(r => String(r.status || '').toLowerCase() === 'running').length;
  const errored = containers.filter(r => r.error).length;
  return `<div class="vizGrid">${donut('Container State', [
    {label:'Running', value:running, color:'var(--ok)'},
    {label:'Other', value:Math.max(containers.length - running - errored, 0), color:'var(--warn)'},
    {label:'Errors', value:errored, color:'var(--danger)'}
  ])}<div class="vizCard"><h3>Host Pressure</h3><div class="barList">${bar('Memory', mem.usedPercent || 0, 100, `${mem.usedPercent ?? '?'}%`)}${bar('Workspace Disk', disk.usedPercent || 0, 100, `${disk.usedPercent ?? '?'}%`)}${bar('Load / CPU', load.one || 0, cpuCount, `${load.one ?? '?'} / ${cpuCount}`)}</div></div><div class="vizCard"><h3>Top Container CPU</h3><div class="barList">${cpuRows.length ? cpuRows.map(r => bar(r.service || r.name, r.cpuPercent || 0, 100, `${r.cpuPercent ?? 0}%`)).join('') : '<div class="muted">No CPU samples.</div>'}</div></div><div class="vizCard"><h3>Top Container Memory</h3><div class="barList">${memRows.length ? memRows.map(r => bar(r.service || r.name, r.memoryPercent || 0, 100, `${r.memoryPercent ?? 0}%`)).join('') : '<div class="muted">No memory samples.</div>'}</div></div></div>`;
}
function resourcePanel(data){
  rememberResourceSample(data);
  const host = data.host || {};
  const mem = host.memory || {};
  const disk = host.disk || {};
  const load = host.load || {};
  const docker = data.docker || {};
  const containers = docker.containers || [];
  const liveStats = !!docker.liveStats;
  const containerRows = containers.length ? `<div class="tableWrap"><table class="dataDense"><thead><tr><th>Service</th><th>Status</th><th>CPU</th><th>Memory</th><th>Net I/O</th><th>Block I/O</th><th>PIDs</th></tr></thead><tbody>${containers.map(r => `<tr><td>${esc(r.service || r.name)}</td><td>${esc(r.status || r.error || '')}</td><td>${esc(r.cpuPercent ?? '')}%</td><td>${esc(r.memory || '')}<br><span class="muted">${esc(r.memoryPercent ?? '')}%</span></td><td>${esc(r.netIO || '')}</td><td>${esc(r.blockIO || '')}</td><td>${esc(r.pids ?? '')}</td></tr>`).join('')}</tbody></table></div>` : `<div class="muted">${esc(docker.error || 'No container stats available.')}</div>`;
  return `<div class="card resourcePanel"><div class="sectionHeader"><h2>Resources</h2><div class="toolbar"><input class="filterInput resourceFilter" placeholder="Filter containers"><span class="pill">${esc(data.generatedAt || '')}</span><span class="pill">${liveStats ? 'live stats' : 'fast inventory'}</span><button id="toggleAutoRefreshBtn">${autoRefresh ? 'Pause refresh' : 'Resume refresh'}</button><button id="refreshResourcesBtn">Refresh</button><button id="sampleResourcesBtn">Sample live stats</button></div></div><div class="metricGrid">${metric('Host Load', `${load.one ?? '?'} / ${load.five ?? '?'} / ${load.fifteen ?? '?'}`)}${metric('Host Memory', `${fmtBytes(mem.usedBytes)} / ${fmtBytes(mem.totalBytes)}`, (mem.usedPercent || 0) > 90 ? 'dangerText' : '')}${metric('Workspace Disk', `${fmtBytes(disk.usedBytes)} / ${fmtBytes(disk.totalBytes)}`, (disk.usedPercent || 0) > 90 ? 'dangerText' : '')}${metric('Containers', containers.length)}</div>${resourceHistoryPanel()}${resourceViz(data)}<details><summary>Container Table</summary>${containerRows}</details></div>`;
}
function envEditor(payload){
  const values = payload.values || {};
  const configured = payload.configured || {};
  const definitions = payload.definitions || {};
  const groups = {};
  Object.keys(definitions).sort().forEach(key => {
    const meta = definitions[key] || {};
    const group = meta.group || 'Other';
    groups[group] = groups[group] || [];
    groups[group].push([key, meta]);
  });
  const groupOrder = ['World', 'Access', 'Admin Panel', 'Artificial Exchange', 'Artificial Exchange Populator', 'Announcements', 'Restart', 'Chat Spam Protection', 'Admin Bot', 'Secrets', 'Network', 'Install'];
  const orderedGroups = Object.entries(groups).sort(([a], [b]) => {
    const ai = groupOrder.indexOf(a);
    const bi = groupOrder.indexOf(b);
    if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    return a.localeCompare(b);
  });
  return orderedGroups.map(([group, rows]) => `<details class="card"${group === 'World' || group === 'Access' ? ' open' : ''}><summary><h2>${esc(group)}</h2></summary><div class="settingsGrid">${rows.map(([key, meta]) => {
    const type = meta.secret ? 'password' : 'text';
    const restart = meta.restart ? '<span class="muted"> restart/recreate applies</span>' : '';
    const configuredText = meta.secret && configured[key] ? ' configured, leave blank to keep' : '';
    return `<label>${esc(key)}${restart}<input id="env_${esc(key)}" data-secret="${meta.secret ? 'true' : 'false'}" type="${type}" value="${esc(values[key] || '')}" placeholder="${esc(configuredText.trim())}"><span class="muted">${esc(meta.why || '')}${esc(configuredText)}</span></label>`;
  }).join('')}</div></details>`).join('');
}
function directorTransferEditor(payload){
  const values = payload.values || {};
  const definitions = payload.definitions || {};
  const rulesets = payload.rulesets || [];
  const rulesetLabels = payload.rulesetLabels || {};
  return `<div class="card"><h2>Director Character Transfers</h2><div class="grid">${Object.entries(definitions).map(([key, meta]) => {
    let control = '';
    if (meta.type === 'bool') {
      control = `<select id="transfer_${esc(key)}"><option value="true"${values[key] === 'true' ? ' selected' : ''}>true</option><option value="false"${values[key] === 'false' ? ' selected' : ''}>false</option></select>`;
    } else if (meta.type === 'ruleset') {
      control = `<select id="transfer_${esc(key)}">${rulesets.map(v => `<option value="${esc(v)}"${values[key] === v ? ' selected' : ''}>${esc(rulesetLabels[v] || v)}</option>`).join('')}</select>`;
    } else {
      control = `<input id="transfer_${esc(key)}" type="number" min="0" value="${esc(values[key] || meta.default || '')}">`;
    }
    return `<label>${esc(key)}${control}<span class="muted">${esc(meta.why || '')}</span></label>`;
  }).join('')}</div><p><button id="saveDirectorTransferBtn" class="primary">Save transfer settings</button></p></div>`;
}
function playerOnlineStateEditor(payload){
  const values = payload.values || {};
  const definitions = payload.definitions || {};
  const section = payload.section || '';
  return `<div class="card"><h2>Logout and Reconnect Timers</h2><p class="muted"><code>${esc(section)}</code> in <code>UserGame.ini</code>. Set these to <code>0</code> for Steam Deck suspend/logout behavior. Recreate game-server containers after saving.</p><div class="grid">${Object.entries(definitions).map(([key, meta]) => {
    return `<label>${esc(key)}<input id="online_${esc(key)}" type="number" min="0" max="86400" value="${esc(values[key] || meta.default || '')}"><span class="muted">${esc(meta.why || '')}</span></label>`;
  }).join('')}</div><p><button id="savePlayerOnlineStateBtn" class="primary">Save logout timers</button></p></div>`;
}
function artificialExchangePanel(status){
  const env = status.env || {};
  const catalog = status.catalog || {};
  const readiness = status.readiness || {};
  const buyer = (status.services || {}).buyer || {};
  const populator = (status.services || {}).populator || {};
  const watchdog = (status.services || {}).watchdog || {};
  const checks = readiness.checks || [];
  const checkRows = checks.map(c => ({check:c.name, ok:c.ok, detail:Object.entries(c).filter(([k]) => !['name','ok'].includes(k)).map(([k,v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' ')}));
  const serviceRows = [
    {service:'buyer', active:buyer.ActiveState || '', substate:buyer.SubState || '', enabled:buyer.UnitFileState || '', restarts:buyer.NRestarts || '', status:buyer.error || ''},
    {service:'populator', active:populator.ActiveState || '', substate:populator.SubState || '', enabled:populator.UnitFileState || '', restarts:populator.NRestarts || '', status:populator.error || ''},
    {service:'watchdog', active:watchdog.ActiveState || '', substate:watchdog.SubState || '', enabled:watchdog.UnitFileState || '', restarts:watchdog.NRestarts || '', status:watchdog.error || ''}
  ];
  const gateRows = [
    {key:'Buyer enabled', value:env.DUNE_ARTIFICIAL_EXCHANGE_ENABLED},
    {key:'Buyer dry run', value:env.DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN},
    {key:'Purchases enabled', value:env.DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED},
    {key:'Auto-claim enabled', value:env.DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED},
    {key:'Auto-claim after scan', value:env.DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN},
    {key:'Populator enabled', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED},
    {key:'Populator dry run', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN},
    {key:'Require market price', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_MARKET_PRICE},
    {key:'Require deterministic category', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_DETERMINISTIC_CATEGORY},
    {key:'Max per template/category', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MAX_PER_TEMPLATE_PER_CATEGORY},
    {key:'Watchdog dry run', value:env.DUNE_ARTIFICIAL_EXCHANGE_WATCHDOG_DRY_RUN},
    {key:'Buyer controller', value:env.DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID},
    {key:'Populator owner', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID},
    {key:'Source inventory', value:env.DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID}
  ];
  return `<div class="panelBand" id="artificialExchangePanel"><div class="sectionHeader"><h2>Artificial Exchange</h2><div class="toolbar"><span class="pill ${status.ok ? 'ok' : 'warn'}">readiness ${status.ok ? 'clean' : 'check'}</span><span class="pill ${catalog.ok ? 'ok' : 'bad'}">catalog ${catalog.enabledItems ?? 0}/${catalog.items ?? 0}</span><span class="pill ${buyer.ok ? 'ok' : 'warn'}">buyer ${buyer.ActiveState || 'unknown'}</span><span class="pill ${populator.ok ? 'ok' : 'warn'}">populator ${populator.ActiveState || 'unknown'}</span><span class="pill ${watchdog.ok ? 'ok' : 'warn'}">watchdog ${watchdog.ActiveState || 'unknown'}</span><button id="aeRefreshBtn">Refresh</button></div></div><div class="commandBar"><button data-ae-action="build-catalog">Build catalog</button><button data-ae-action="check-ready" class="primary">Check ready</button><button data-ae-action="buyer-dry-run">Buyer dry run</button><button data-ae-action="settlement-report">Settlement report</button><button data-ae-action="validate-populator">Validate populator</button><button data-ae-action="watchdog-once">Watchdog once</button></div><div class="commandBar"><button data-ae-action="install-buyer-service">Install buyer service</button><button data-ae-action="install-populator-service">Install populator service</button><button data-ae-action="install-watchdog-timer">Install watchdog timer</button><button data-ae-action="restart:buyer">Restart buyer</button><button data-ae-action="restart:populator">Restart populator</button><button data-ae-action="restart:watchdog">Restart watchdog</button><button data-ae-action="start:buyer">Start buyer</button><button data-ae-action="start:populator">Start populator</button><button data-ae-action="start:watchdog">Start watchdog</button><button data-ae-action="stop:buyer" class="danger">Stop buyer</button><button data-ae-action="stop:populator" class="danger">Stop populator</button><button data-ae-action="stop:watchdog" class="danger">Stop watchdog</button></div><div class="twoCol"><div><h3>Gates</h3>${table(gateRows)}</div><div><h3>Services</h3>${table(serviceRows)}</div></div><details><summary>Readiness checks</summary>${table(checkRows)}<pre>${esc(JSON.stringify(readiness, null, 2))}</pre></details><pre id="artificialExchangeResult"></pre></div>`;
}
function actionGrid(actions){
  return `<div class="commandBar">${actions.map(a => `<button class="${esc(a.className || '')}" data-jump="${esc(a.tab)}">${esc(a.label)}</button>`).join('')}</div>`;
}
function syncTabs(){
  document.querySelectorAll('.tab').forEach(b=>{
    const active = b.dataset.tab === current;
    b.classList.toggle('active', active);
    b.setAttribute('aria-selected', active ? 'true' : 'false');
  });
}
function show(name){
  if (!validTabs.has(name)) return;
  current = name;
  sessionStorage.setItem('duneAdminTab', current);
  if (location.hash.slice(1) !== current) history.replaceState(null, '', '#' + current);
  syncTabs();
  load();
}
function modal(open){
  const dialog = document.getElementById('helpModal');
  dialog.classList.toggle('open', open);
  if (open) {
    document.getElementById('closeHelpBtn').focus();
    announce('Shortcut help opened');
  } else {
    announce('Shortcut help closed');
  }
}
function focusFirstFilter(){
  const input = view.querySelector('.rosterFilter, .resourceFilter, #q, input:not([type="hidden"]), select, textarea');
  if (input) {
    input.focus();
    if (input.select) input.select();
    announce('Focused first filter or input');
  }
}
function toggleClassSetting(className, key, label){
  const enabled = !document.body.classList.contains(className);
  document.body.classList.toggle(className, enabled);
  sessionStorage.setItem(key, enabled ? 'on' : 'off');
  notify(`${label} ${enabled ? 'enabled' : 'disabled'}`);
}
function setDetails(open){
  view.querySelectorAll('details').forEach(d => { d.open = open; });
  notify(open ? 'Expanded dashboard details' : 'Collapsed dashboard details');
}
function wireResourceControls(root=document){
  root.querySelector('#refreshResourcesBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Refreshing...', refreshResources));
  root.querySelector('#sampleResourcesBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Sampling...', () => refreshResources(true)));
  root.querySelector('#toggleAutoRefreshBtn')?.addEventListener('click', () => {
    autoRefresh = !autoRefresh;
    sessionStorage.setItem('duneAdminAutoRefresh', autoRefresh ? 'on' : 'off');
    notify(autoRefresh ? 'Live resource refresh resumed' : 'Live resource refresh paused');
    refreshResources().catch(e => notify(e.message, 'bad'));
  });
}
function wireGlobalAffordances(){
  document.getElementById('contrastBtn')?.addEventListener('click', () => toggleClassSetting('highContrast', 'duneAdminHighContrast', 'High contrast'));
  document.getElementById('densityBtn')?.addEventListener('click', () => toggleClassSetting('denseMode', 'duneAdminDenseMode', 'Dense mode'));
  document.getElementById('expandAllBtn')?.addEventListener('click', () => setDetails(true));
  document.getElementById('collapseAllBtn')?.addEventListener('click', () => setDetails(false));
  document.getElementById('helpBtn')?.addEventListener('click', () => modal(true));
  document.getElementById('closeHelpBtn')?.addEventListener('click', () => modal(false));
  document.getElementById('closePlayerModalBtn')?.addEventListener('click', closePlayerModal);
  document.getElementById('refreshPlayerModalBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Refreshing...', () => loadPlayerModal(playerModalAccountId)));
  document.getElementById('helpModal')?.addEventListener('click', e => {
    if (e.target.id === 'helpModal') modal(false);
  });
  document.getElementById('playerModal')?.addEventListener('click', e => {
    if (e.target.id === 'playerModal') closePlayerModal();
  });
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('keydown', e => {
      const tabs = Array.from(document.querySelectorAll('.tab'));
      const index = tabs.indexOf(tab);
      const next = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? tabs[index + 1] || tabs[0] : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? tabs[index - 1] || tabs[tabs.length - 1] : null;
      if (next) {
        e.preventDefault();
        next.focus();
        show(next.dataset.tab);
      }
    });
  });
  document.addEventListener('keydown', e => {
    const tag = e.target.tagName;
    const typing = ['INPUT','TEXTAREA','SELECT'].includes(tag);
    if (e.key === 'Escape' && document.getElementById('playerModal').classList.contains('open')) { closePlayerModal(); return; }
    if (e.key === 'Escape' && document.getElementById('helpModal').classList.contains('open')) { modal(false); return; }
    if (typing && e.key !== 'Escape') return;
    const tabMap = {'1':'overview','2':'ops','3':'security','4':'runbook','5':'characters','6':'settings','7':'mutations','8':'digests','9':'catalog'};
    if (tabMap[e.key]) { e.preventDefault(); show(tabMap[e.key]); return; }
    if (e.key === '?') { e.preventDefault(); modal(true); return; }
    if (e.key === '/') { e.preventDefault(); focusFirstFilter(); return; }
    if (e.key.toLowerCase() === 'r') { e.preventDefault(); load(); return; }
    if (e.key.toLowerCase() === 'h') { e.preventDefault(); toggleClassSetting('highContrast', 'duneAdminHighContrast', 'High contrast'); return; }
    if (e.key.toLowerCase() === 'd') { e.preventDefault(); toggleClassSetting('denseMode', 'duneAdminDenseMode', 'Dense mode'); return; }
    if (e.key.toLowerCase() === 'e') { e.preventDefault(); setDetails(true); return; }
    if (e.key.toLowerCase() === 'c') { e.preventDefault(); setDetails(false); }
  });
}
function renderStatus(data){
  const tokenRow = document.getElementById('tokenRow');
  if (tokenRow) tokenRow.classList.toggle('hidden', !data.adminTokenRequired);
  document.getElementById('statusSummary').innerHTML = [
    data.adminTokenRequired ? statusPill('admin token configured', data.adminTokenConfigured) : '<span class="pill ok">local admin: unlocked</span>',
    statusPill('item grants', data.itemGrantsEnabled),
    `<span class="pill ${data.mutationsEnabled ? 'warn' : 'ok'}">mutations: ${data.mutationsEnabled ? 'enabled' : 'off'}</span>`,
    `<span class="pill">db: ${esc(data.database)}</span>`
  ].join('');
  document.getElementById('statusRaw').textContent = JSON.stringify(data, null, 2);
  updateLastRefresh('Status refreshed');
}
async function refreshStatus(){ renderStatus(await api('/api/status')); }
async function refreshNetwork(){
  const network = await api('/api/ops/network');
  document.querySelectorAll('[data-network-panel]').forEach(container => {
    container.innerHTML = `<h2>Network and Upstream</h2>${probeTable(network.probes)}${checks(network.verdicts)}`;
  });
}
async function load(){
  const serial = ++loadSerial;
  if (resourceTimer) {
    clearInterval(resourceTimer);
    resourceTimer = null;
  }
  if (overviewResourceTimer) {
    clearInterval(overviewResourceTimer);
    overviewResourceTimer = null;
  }
  if (haggaMapTimer) {
    clearInterval(haggaMapTimer);
    haggaMapTimer = null;
  }
  if (healthTimer) {
    clearInterval(healthTimer);
    healthTimer = null;
  }
  view.setAttribute('aria-busy', 'true');
  syncTabs();
  view.innerHTML = `<div class="panelBand"><h2>${esc(current[0].toUpperCase() + current.slice(1))}</h2><div class="muted">Loading...</div></div>`;
  refreshStatus().catch(e => {
    document.getElementById('statusSummary').innerHTML = `<span class="pill bad">${esc(e.message)}</span>`;
    document.getElementById('statusRaw').textContent = e.message;
  });
  try {
    if (current === 'overview') await overview(serial);
    else if (current === 'ops') await ops(serial);
    else if (current === 'security') await security(serial);
    else if (current === 'runbook') await runbook(serial);
    else if (current === 'characters') await characters(serial);
    else if (current === 'settings') await settings(serial);
    else if (current === 'mutations') await mutations(serial);
    else if (current === 'digests') await digests(serial);
    else if (current === 'catalog') await catalog(serial);
  } catch (e) {
    if (serial !== loadSerial) return;
    view.innerHTML = `<div class="card"><h2>Panel Data Unavailable</h2><p class="dangerText">${esc(e.message)}</p><p class="muted">The page loaded, but one of the backing admin APIs failed. Refresh after the admin panel or database is healthy.</p></div><div class="metricGrid">${metric('Endpoint', location.host)}${metric('Item Grants', 'enabled', 'ok')}${metric('Mutations', 'check status')}</div>`;
  }
  if (serial !== loadSerial) return;
  makeSortableTables(view);
  makeRowsKeyboardFriendly(view);
  enhanceCopyBlocks(view);
  announce(`${current} loaded`);
  view.setAttribute('aria-busy', 'false');
}
async function overview(serial=loadSerial){
  const [health, roster] = await Promise.all([
    api('/api/ops/health'),
    api('/api/characters/roster')
  ]);
  if (serial !== loadSerial) return;
  overviewRosterCounts = roster.counts || {};
  overviewHealthSnapshot = health;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Overview</h2><div class="toolbar"><button data-jump="characters">Players</button><button data-jump="ops">Operations</button><button data-jump="mutations" class="primary">Admin Actions</button></div></div><div id="overviewRealtime" class="overviewTopGrid" aria-live="polite">${overviewRealtimeHtml(health, overviewRosterCounts, overviewResourceSnapshot)}</div><div id="haggaBasinMap" class="overviewMapShell"><div class="panelBand"><h2>Hagga Basin Player Map</h2><div class="muted">Loading player positions...</div></div></div>${actionGrid([{tab:'characters',label:'Open player roster',className:'primary'},{tab:'ops',label:'Restart / backup / map health'},{tab:'mutations',label:'Grant currency, XP, or items'},{tab:'settings',label:'Server settings'}])}<details class="panelBand"><summary>Player Roster Preview</summary><div id="overviewRoster">${characterRosterPanel(roster)}</div></details><div id="detail"></div></div>`;
  document.querySelectorAll('#overviewRoster tbody tr').forEach(row => row.onclick = () => pickCharacter(row));
  makeRowsKeyboardFriendly(view);
  bindRosterFilters(view);
  refreshHaggaMap().catch(e => {
    const container = document.getElementById('haggaBasinMap');
    if (container) container.innerHTML = `<h2>Hagga Basin Player Map</h2><div class="dangerText">${esc(e.message)}</div>`;
  });
  haggaMapTimer = setInterval(() => {
    if (haggaMapAutoRefresh && current === 'overview') refreshHaggaMap().catch(() => {});
  }, 2000);
  refreshOverviewResources({force:true}).catch(() => {});
  overviewResourceTimer = setInterval(() => {
    if (autoRefresh && current === 'overview') refreshOverviewResources().catch(() => {});
  }, 5000);
  startHealthRefresh();
}
async function ops(serial=loadSerial){
  const [health, opt, announcement, restart] = await Promise.all([
    api('/api/ops/health'),
    api('/api/ops/optimization'),
    api('/api/ops/announcement'),
    api('/api/ops/restart')
  ]);
  if (serial !== loadSerial) return;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Operations</h2><div class="toolbar"><button data-jump="overview">Overview</button><button data-jump="characters">Players</button><button data-jump="runbook">Runbook</button><button data-jump="settings">Settings</button></div></div><div id="opsRealtimeMetrics" class="metricGrid" aria-live="polite">${opsRealtimeMetricsHtml(health)}</div><div class="twoCol">${restartPanel(restart)}${announcementPanel(announcement)}</div><div class="twoCol"><div id="opsHealthViz">${healthViz(health)}</div><div class="panelBand"><h2>Health Verdict</h2><div id="opsHealthVerdicts">${checks(health.verdicts)}</div></div></div><details class="panelBand" open><summary>Map Online/Offline</summary><div id="opsMapStatus">${mapTiles(health.mapStatus)}${mapStatusTable(health.mapStatus)}</div></details><details class="panelBand"><summary>Host Resources</summary><div id="resources"><div class="muted">Loading resource stats...</div></div></details><details class="panelBand"><summary>Local and Upstream Network</summary><div data-network-panel><div class="muted">Loading network probes...</div></div></details><details class="panelBand"><summary>Raw Farm State</summary><div id="opsRawFarmState">${table(health.farmState)}</div></details><details class="panelBand"><summary>Partitions</summary><div id="opsPartitions">${table(health.partitions)}</div></details><details class="panelBand"><summary>Optimization Signals</summary>${signalList(opt)}</details></div>`;
  wireResourceControls(view);
  bindResourceFilters(view);
  refreshResources().catch(e => {
    const container = document.getElementById('resources');
    if (container) container.innerHTML = `<div class="panelBand"><h2>Resources</h2><div class="dangerText">${esc(e.message)}</div></div>`;
  });
  refreshNetwork().catch(e => {
    document.querySelectorAll('[data-network-panel]').forEach(container => container.innerHTML = `<h2>Local and Upstream Network</h2><div class="dangerText">${esc(e.message)}</div>`);
  });
  document.getElementById('scheduleAnnouncementBtn').addEventListener('click', e => runAction(e.currentTarget, 'Scheduling...', scheduleAnnouncement));
  document.getElementById('cancelAnnouncementBtn').addEventListener('click', e => runAction(e.currentTarget, 'Canceling...', cancelAnnouncement));
  document.getElementById('scheduleRestartBtn').addEventListener('click', e => runAction(e.currentTarget, 'Scheduling...', scheduleRestart));
  document.getElementById('cancelRestartBtn').addEventListener('click', e => runAction(e.currentTarget, 'Canceling...', cancelRestart));
  resourceTimer = setInterval(() => {
    if (autoRefresh && current === 'ops') refreshResources().catch(() => {});
  }, 5000);
  startHealthRefresh();
}
async function refreshResources(liveStats=false){
  if (resourceRefreshInFlight) return;
  resourceRefreshInFlight = true;
  const button = document.getElementById('refreshResourcesBtn');
  if (button) {
    button.disabled = true;
    button.textContent = 'Refreshing';
  }
  const sampleButton = document.getElementById('sampleResourcesBtn');
  if (sampleButton) {
    sampleButton.disabled = true;
    sampleButton.textContent = liveStats ? 'Sampling' : 'Sample live stats';
  }
  try {
    const resources = await api('/api/ops/resources' + (liveStats ? '?live=1' : ''), {timeoutMs: liveStats ? 8000 : 5000});
    const container = document.getElementById('resources');
    if (!container) return;
    container.innerHTML = resourcePanel(resources);
    wireResourceControls(container);
    bindResourceFilters(container);
    enhanceCopyBlocks(container);
    updateLastRefresh('Resources refreshed');
    announce('Resource panel refreshed');
  } catch (e) {
    notify(`Resource refresh failed: ${e.message}`, 'bad');
  } finally {
    if (button && document.body.contains(button)) {
      button.disabled = false;
      button.textContent = 'Refresh';
    }
    if (sampleButton && document.body.contains(sampleButton)) {
      sampleButton.disabled = false;
      sampleButton.textContent = 'Sample live stats';
    }
    resourceRefreshInFlight = false;
  }
}
async function security(serial=loadSerial){
  const [audit, events] = await Promise.all([
    api('/api/ops/security'),
    api('/api/ops/audit')
  ]);
  if (serial !== loadSerial) return;
  const failed = (audit.checks || []).filter(c => !c.ok).length;
  const failedChecks = (audit.checks || []).filter(c => !c.ok);
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Security</h2><div class="toolbar"><span class="pill ${failed ? 'warn' : 'ok'}">${failed ? failed + ' checks need attention' : 'checks OK'}</span><button data-jump="settings">Settings</button><button data-jump="mutations">Admin Actions</button></div></div>${failed ? `<div class="panelBand dangerZone"><h2>Needs Attention</h2>${checks(failedChecks)}</div>` : ''}<div class="twoCol"><div class="panelBand"><h2>Security Checks</h2>${checks(audit.checks)}</div><div class="panelBand"><h2>Recent Audit Events</h2>${auditEventsTable(events.events)}<details><summary>Raw audit events</summary>${table(events.events)}</details></div></div><div class="panelBand"><h2>Operating Notes</h2><ul>${audit.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></div><details class="panelBand"><summary>Editable Env Keys</summary><div class="toolbar">${audit.safeEnvKeys.map(k => `<span class="pill">${esc(k)}</span>`).join('')}</div></details><details class="panelBand"><summary>Editable Config Files</summary><div class="toolbar">${audit.allowedConfigFiles.map(k => `<span class="pill">${esc(k)}</span>`).join('')}</div></details></div>`;
}
async function runbook(serial=loadSerial){
  const data = await api('/api/ops/runbook');
  if (serial !== loadSerial) return;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Runbook</h2><div class="toolbar"><span class="pill">operator workflows</span><button data-jump="ops">Ops</button><button data-jump="settings">Settings</button></div></div>${actionGrid([{tab:'ops',label:'Restart / backup status',className:'primary'},{tab:'mutations',label:'Admin Actions'},{tab:'security',label:'Audit'}])}<div class="panelBand"><p class="muted">${esc(data.why)}</p>${table(data.commands)}</div></div>`;
}
function digestList(entries){
  if (!entries.length) return '<div class="muted">No digests recorded.</div>';
  return `<div class="eventList">${entries.map(e => `<div class="eventItem"><div class="eventItemHead"><b>${esc(e.event || 'digest')}</b><span class="pill">${esc(e.audience || '')}</span></div><div class="muted">${esc(String(e.ts || '').replace('T', ' ').replace('Z', ''))}</div><div>${esc(e.message || '')}</div>${e.payload && Object.keys(e.payload).length ? `<details><summary>Payload</summary><pre>${esc(JSON.stringify(e.payload, null, 2))}</pre></details>` : ''}</div>`).join('')}</div>`;
}
async function digests(serial=loadSerial){
  const data = await api('/api/admin/digests');
  if (serial !== loadSerial) return;
  const entries = data.digests || [];
  const adminEntries = entries.filter(e => e.audience === 'admin');
  const publicEntries = entries.filter(e => e.audience === 'public');
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Admin Digests</h2><div class="toolbar"><span class="pill">${esc(entries.length)} retained</span><span class="pill">${esc(data.updatedAt || 'not updated')}</span><button data-jump="ops">Ops</button><button data-jump="security">Audit</button></div></div><div class="metricGrid">${metric('Map Health State', data.mapHealthState || 'unknown')}${metric('Daily Peak', (data.dailyPeak || {}).peak ?? 0)}${metric('Online Snapshot', Object.keys(data.onlinePlayers || {}).length)}${metric('State File', data.path || '')}</div><div class="twoCol"><div class="panelBand"><h2>Admin-Only Digests</h2>${digestList(adminEntries)}</div><div class="panelBand"><h2>Public Notices</h2>${digestList(publicEntries)}</div></div><details class="panelBand"><summary>Last Send Markers</summary>${table(Object.entries(data.lastSent || {}).map(([key,value]) => ({key, value})))}</details><details class="panelBand"><summary>Raw Digest State</summary><pre>${esc(JSON.stringify(data, null, 2))}</pre></details></div>`;
}
async function characters(serial=loadSerial){
  const lastQuery = sessionStorage.getItem('duneAdminCharacterQuery') || '';
  if (serial !== loadSerial) return;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Players</h2><div class="toolbar"><span class="pill">online and offline roster</span><button id="refreshRosterBtn">Refresh roster</button><button data-jump="mutations" class="primary">Admin Actions</button><button data-jump="settings">Settings</button></div></div><div id="roster"></div><div class="panelBand"><h2>Player Search</h2><div class="row"><input id="q" placeholder="Character, Funcom ID, platform ID" value="${esc(lastQuery)}"><button id="characterSearchBtn" class="primary">Search</button><button id="characterListAllBtn">List all</button></div><div id="results"></div></div><div id="detail"></div></div>`;
  document.getElementById('refreshRosterBtn').addEventListener('click', e => runAction(e.currentTarget, 'Refreshing...', loadCharacterRoster));
  document.getElementById('characterSearchBtn').addEventListener('click', e => runAction(e.currentTarget, 'Searching...', searchCharacters));
  document.getElementById('characterListAllBtn').addEventListener('click', () => {
    document.getElementById('q').value = '';
    searchCharacters().catch(e => reportClientError(e, 'List players'));
  });
  document.getElementById('q').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchCharacters().catch(err => reportClientError(err, 'Search players'));
  });
  await loadCharacterRoster();
  if (lastQuery) await searchCharacters();
}
async function loadCharacterRoster(){
  const roster = await api('/api/characters/roster');
  const container = document.getElementById('roster');
  container.innerHTML = characterRosterPanel(roster);
  container.querySelectorAll('tbody tr').forEach(row => row.onclick = () => pickCharacter(row));
  bindRosterFilters(container);
  makeRowsKeyboardFriendly(container);
}
async function searchCharacters(){
  const query = document.getElementById('q').value;
  sessionStorage.setItem('duneAdminCharacterQuery', query);
  const rows = await api('/api/characters?q=' + encodeURIComponent(query));
  const results = document.getElementById('results');
  results.innerHTML = table(rows);
  results.querySelectorAll('tbody tr').forEach(row => row.onclick = () => pickCharacter(row));
  makeSortableTables(results);
  makeRowsKeyboardFriendly(results);
}
async function pickCharacter(row){
  const serial = ++detailLoadSerial;
  document.querySelectorAll('tbody tr.selected').forEach(r => r.classList.remove('selected'));
  row.classList.add('selected');
  const id = row.dataset.id || row.children[0].textContent;
  if (!id) return;
  const detail = document.getElementById('detail');
  if (detail) detail.innerHTML = '<div class="panelBand"><h2>Selected Player</h2><div class="muted">Opening player detail...</div></div>';
  await openPlayerModal(id, serial);
}
function playerLocationSummary(d){
  const p = d.player || {};
  const map = (d.mapContext || [])[0] || {};
  const prev = (d.previousPartition || [])[0] || {};
  const pawnLocation = (d.actorLocations || []).find(r => String(r.id) === String(p.player_pawn_id)) || {};
  const controllerLocation = (d.actorLocations || []).find(r => String(r.id) === String(p.player_controller_id)) || {};
  const actorLocation = pawnLocation.map || pawnLocation.transform ? pawnLocation : controllerLocation;
  const overmap = (d.overmap || [])[0] || {};
  const respawn = (d.respawnLocations || [])[0] || {};
  return [
    {label:'Status', value:p.online_status || ''},
    {label:'Life', value:p.life_state || ''},
    {label:'Current Map', value:actorLocation.map || map.label || map.map || p.server_id || ''},
    {label:'Actor Transform', value:actorLocation.transform || ''},
    {label:'Partition', value:actorLocation.partition_id ?? map.partition_id ?? prev.partition_id ?? ''},
    {label:'Dimension', value:actorLocation.dimension_index ?? map.dimension_index ?? p.return_dimension_index ?? p.home_dimension_index ?? ''},
    {label:'Server Ready', value:map.server_id ? `${map.ready ? 'ready' : 'not ready'} / ${map.alive ? 'alive' : 'not alive'}` : ''},
    {label:'Reported Players', value:map.connected_players ?? ''},
    {label:'Overmap Location', value:overmap.overmap_location ? JSON.stringify(overmap.overmap_location) : ''},
    {label:'Death Location', value:p.death_location ? JSON.stringify(p.death_location) : ''},
    {label:'Last Respawn', value:respawn.locator_name ? `${respawn.locator_name} ${respawn.map || ''}` : ''},
  ].filter(r => r.value !== undefined && r.value !== null && String(r.value) !== '');
}
function playerInventorySummary(items){
  const groups = new Map();
  (items || []).forEach(item => {
    const id = item.inventory_id ?? 'unknown';
    const group = groups.get(id) || {inventory_id:id, item_count:0, total_stack:0};
    group.item_count += 1;
    group.total_stack += Number(item.stack_size || item.stack_count || 0);
    groups.set(id, group);
  });
  return Array.from(groups.values()).sort((a, b) => String(a.inventory_id).localeCompare(String(b.inventory_id)));
}
function playerModalUiState(){
  const value = id => document.getElementById(id)?.value || '';
  return {
    inventoryFilter: value('modalInventoryFilter'),
    itemFilter: value('modalItemFilter'),
    grantInventory: value('detailGrantInventory'),
    itemId: value('detailItemSelect'),
    templateId: value('detailGrantTemplate'),
    stackSize: value('detailGrantStack'),
    deleteCount: value('detailDeleteCount'),
    currencyId: value('detailCurId'),
    currencyAmount: value('detailCurAmount'),
    currencyMode: value('detailCurMode'),
    trackType: value('detailTrack'),
    xpAmount: value('detailXpAmount'),
    xpLevel: value('detailXpLevel'),
    xpMode: value('detailXpMode'),
  };
}
function setIfPresent(id, value){
  const element = document.getElementById(id);
  if (element && value !== undefined && value !== null && value !== '') element.value = value;
}
function renderPlayerModal(d, ref, uiState={}){
  const p = d.player || {};
  const account = (d.account || [])[0] || {};
  const map = (d.mapContext || [])[0] || {};
  const locationRows = playerLocationSummary(d);
  const inventories = d.inventories || [];
  const items = d.inventoryItems || [];
  const inventorySummary = playerInventorySummary(items);
  const firstTrack = (d.specialization && d.specialization[0]) || {};
  document.getElementById('playerModalTitle').textContent = p.character_name || 'Player Detail';
  document.getElementById('playerModalRefreshState').textContent = `updated ${new Date().toLocaleTimeString()}`;
  document.getElementById('playerModalBody').innerHTML = `<datalist id="itemTemplateList">${templateDatalist(ref)}</datalist><div class="playerModalGrid"><div class="pageStack"><div class="panelBand"><h2>${esc(p.character_name || 'Character')}</h2><div class="metricGrid">${metric('Status', p.online_status || '')}${metric('Life', p.life_state || '')}${metric('Map', map.label || map.map || p.server_id || '')}${metric('Items', items.length)}</div><div class="grid"><div><b>Account</b><br>${esc(p.account_id)}</div><div><b>Funcom</b><br>${esc(account.funcom_id || '')}</div><div><b>Platform</b><br>${steamProfileCell(account)}</div><div><b>Last Login</b><br>${esc(p.last_login_time || '')}</div><div><b>Controller</b><br>${esc(p.player_controller_id)}</div><div><b>Pawn</b><br>${esc(p.player_pawn_id)}</div></div><p><button id="modalOpenAdminActionsBtn" class="primary">Open Admin Actions</button></p></div><div class="panelBand"><h2>Location and Runtime</h2>${table(locationRows)}<details open><summary>Actor Locations</summary>${table(d.actorLocations || [])}</details><details><summary>Travel Return</summary>${table(d.travelReturn || [])}</details><details><summary>Map Context</summary>${table(d.mapContext || [])}</details><details><summary>Respawn Locations</summary>${table(d.respawnLocations || [])}</details><details><summary>Runtime Source</summary><pre>${esc(JSON.stringify(d.realtime || {}, null, 2))}</pre></details></div><div class="panelBand"><h2>Currency and XP</h2><details open><summary>Currency</summary>${table(d.currency || [])}</details><details><summary>Specialization</summary>${table(d.specialization || [])}</details><details><summary>Faction</summary>${table(d.faction || [])}</details><details><summary>Reputation</summary>${table(d.reputation || [])}</details></div></div><div class="pageStack"><div class="panelBand"><div class="splitHeader"><h2>Inventory</h2><span class="pill">${esc(items.length)} items</span></div><div class="playerInventoryTools"><label>Inventory<select id="modalInventoryFilter"><option value="">All inventories</option>${inventoryOptions(inventories)}</select></label><label>Item Search<input id="modalItemFilter" placeholder="Template, item ID, inventory"></label></div><h3>Inventory Summary</h3>${table(inventorySummary)}<h3>Items</h3><div id="modalInventoryItems">${table(items)}</div></div><div class="panelBand"><h2>Quick Currency and XP</h2><div class="grid"><label>Currency<select id="detailCurId">${currencyBalanceOptions(d.currency, ref.currencyIds)}</select></label><label>Amount<input id="detailCurAmount" value="1000"></label><label>Mode<select id="detailCurMode"><option>add</option><option>set</option></select></label></div><p><button id="detailCurrencyBtn" class="primary">Apply currency</button></p><div class="grid"><label>Track<select id="detailTrack">${specializationOptions(d.specialization, ref.specializationTrackTypes)}</select></label><label>XP amount<input id="detailXpAmount" value="1000"></label><label>Level for set/new track<input id="detailXpLevel" value="${esc(firstTrack.level ?? 0)}"></label><label>Mode<select id="detailXpMode"><option>add</option><option>set</option></select></label></div><p><button id="detailXpBtn" class="primary">Apply XP</button></p></div><div class="panelBand"><h2>Quick Item Action</h2><div class="grid"><label>Owned inventory<select id="detailGrantInventory"><option value="">All owned inventories</option>${inventoryOptions(inventories)}</select></label><label>Owned item<select id="detailItemSelect">${inventoryItemOptions(items)}</select></label><label>Template ID<input id="detailGrantTemplate" list="itemTemplateList" placeholder="SMG_Unique_LargeMag_06"></label><label>Stack size<input id="detailGrantStack" value="1"></label><label>Delete count<input id="detailDeleteCount" placeholder="blank/all"></label></div><div id="detailSelectedItem" class="muted">Select an owned item to inspect stack and template details.</div><p><button id="detailDryRunBtn" class="primary">Dry run item</button> <button id="detailGrantBtn" class="danger">Grant item</button> <button id="detailSetStackBtn" class="primary">Set selected stack</button> <button id="detailDeleteItemBtn" class="danger">Delete selected item/count</button></p><pre id="detailGrantResult"></pre></div><details class="panelBand"><summary>Raw Detail</summary><pre>${esc(JSON.stringify(d, null, 2))}</pre></details></div></div>`;
  makeSortableTables(document.getElementById('playerModalBody'));
  enhanceCopyBlocks(document.getElementById('playerModalBody'));
  wirePlayerModalDetailActions(d, ref, firstTrack, uiState);
}
function wirePlayerModalDetailActions(d, ref, firstTrack, uiState={}){
  const p = d.player || {};
  const detailInventory = document.getElementById('detailGrantInventory');
  const detailItem = document.getElementById('detailItemSelect');
  const modalInventoryFilter = document.getElementById('modalInventoryFilter');
  const modalItemFilter = document.getElementById('modalItemFilter');
  const updateSelectedItemSummary = () => {
    const itemId = detailItem?.value || '';
    const item = (d.inventoryItems || []).find(r => String(r.item_id ?? r.id ?? '') === String(itemId));
    const target = document.getElementById('detailSelectedItem');
    if (!target) return;
    target.innerHTML = item ? table([item]) : '<div class="muted">Select an owned item to inspect stack and template details.</div>';
    makeSortableTables(target);
  };
  const filterInventoryTable = () => {
    const inventoryId = modalInventoryFilter?.value || '';
    const term = String(modalItemFilter?.value || '').toLowerCase();
    const filtered = (d.inventoryItems || []).filter(r => {
      const matchesInventory = !inventoryId || String(r.inventory_id ?? '') === String(inventoryId);
      const text = JSON.stringify(r).toLowerCase();
      return matchesInventory && (!term || text.includes(term));
    });
    document.getElementById('modalInventoryItems').innerHTML = table(filtered);
    makeSortableTables(document.getElementById('modalInventoryItems'));
    document.querySelectorAll('#modalInventoryItems tbody tr').forEach((row, index) => {
      const item = filtered[index] || {};
      row.tabIndex = 0;
      row.setAttribute('role', 'button');
      const selectItem = () => {
        const itemId = item.item_id ?? item.id ?? '';
        if (detailItem && itemId) {
          detailItem.value = String(itemId);
          detailItem.dispatchEvent(new Event('change'));
        }
      };
      row.addEventListener('click', selectItem);
      row.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          selectItem();
        }
      });
    });
  };
  modalInventoryFilter?.addEventListener('change', () => {
    if (detailInventory) {
      detailInventory.value = modalInventoryFilter.value;
      setDetailItemOptions();
    }
    filterInventoryTable();
  });
  modalItemFilter?.addEventListener('input', filterInventoryTable);
  const setDetailItemOptions = () => {
    const inventoryId = detailInventory?.value || '';
    const allItems = d.inventoryItems || [];
    const filtered = inventoryId ? allItems.filter(r => String(r.inventory_id ?? '') === String(inventoryId)) : allItems;
    detailItem.innerHTML = inventoryItemOptions(filtered);
    document.getElementById('detailGrantTemplate').value = '';
    updateSelectedItemSummary();
  };
  detailInventory?.addEventListener('change', setDetailItemOptions);
  detailItem?.addEventListener('change', e => {
    const option = e.target.selectedOptions?.[0];
    if (option?.dataset.template) document.getElementById('detailGrantTemplate').value = option.dataset.template;
    if (option?.dataset.stack) document.getElementById('detailGrantStack').value = option.dataset.stack;
    if (option?.dataset.inventory && detailInventory) detailInventory.value = option.dataset.inventory;
    updateSelectedItemSummary();
  });
  document.getElementById('detailTrack')?.addEventListener('change', e => {
    const level = e.target.selectedOptions?.[0]?.dataset.level || '';
    if (level) document.getElementById('detailXpLevel').value = level;
  });
  document.getElementById('modalOpenAdminActionsBtn')?.addEventListener('click', () => {
    pendingAdminAccountId = String(p.account_id || '');
    closePlayerModal();
    show('mutations');
  });
  document.getElementById('detailCurrencyBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Applying...', async () => { if (await currencyFor(p.player_controller_id)) await loadPlayerModal(p.account_id); }));
  document.getElementById('detailXpBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Applying...', async () => { if (await xpFor(p.player_controller_id)) await loadPlayerModal(p.account_id); }));
  document.getElementById('detailDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Checking...', () => grantItemForAccount(p.account_id, true)));
  document.getElementById('detailGrantBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Granting...', async () => { if (await grantItemForAccount(p.account_id, false)) await loadPlayerModal(p.account_id); }));
  document.getElementById('detailSetStackBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Saving...', async () => { if (await setDetailItemStack()) await loadPlayerModal(p.account_id); }));
  document.getElementById('detailDeleteItemBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Deleting...', async () => { if (await deleteDetailItem()) await loadPlayerModal(p.account_id); }));
  setIfPresent('modalInventoryFilter', uiState.inventoryFilter);
  setIfPresent('modalItemFilter', uiState.itemFilter);
  setIfPresent('detailGrantInventory', uiState.grantInventory || uiState.inventoryFilter);
  setDetailItemOptions();
  setIfPresent('detailItemSelect', uiState.itemId);
  setIfPresent('detailGrantTemplate', uiState.templateId);
  setIfPresent('detailGrantStack', uiState.stackSize);
  setIfPresent('detailDeleteCount', uiState.deleteCount);
  setIfPresent('detailCurId', uiState.currencyId);
  setIfPresent('detailCurAmount', uiState.currencyAmount);
  setIfPresent('detailCurMode', uiState.currencyMode);
  setIfPresent('detailTrack', uiState.trackType);
  setIfPresent('detailXpAmount', uiState.xpAmount);
  setIfPresent('detailXpLevel', uiState.xpLevel);
  setIfPresent('detailXpMode', uiState.xpMode);
  updateSelectedItemSummary();
  filterInventoryTable();
}
async function loadPlayerModal(accountId){
  if (!accountId || playerModalInFlight) return;
  playerModalInFlight = true;
  const uiState = playerModalUiState();
  document.getElementById('playerModalRefreshState').textContent = 'refreshing';
  try {
    const [d, ref] = await Promise.all([api('/api/characters/' + encodeURIComponent(accountId)), playerModalRef ? Promise.resolve(playerModalRef) : adminReference()]);
    playerModalRef = ref;
    renderPlayerModal(d, ref, uiState);
  } catch (e) {
    document.getElementById('playerModalBody').innerHTML = `<div class="dangerText">${esc(e.message)}</div>`;
    document.getElementById('playerModalRefreshState').textContent = 'error';
    reportClientError(e, 'Load player');
  } finally {
    playerModalInFlight = false;
  }
}
async function openPlayerModal(accountId, serial=detailLoadSerial){
  playerModalAccountId = String(accountId || '');
  playerModalRef = null;
  const modal = document.getElementById('playerModal');
  modal.classList.add('open');
  document.getElementById('playerModalBody').innerHTML = '<div class="muted">Loading player detail...</div>';
  document.getElementById('playerModalRefreshState').textContent = 'loading';
  document.getElementById('closePlayerModalBtn').focus();
  await loadPlayerModal(playerModalAccountId);
  if (serial !== detailLoadSerial) return;
  const detail = document.getElementById('detail');
  if (detail) detail.innerHTML = `<div class="panelBand"><h2>Selected Player</h2><div class="muted">Player detail is open in the modal. It refreshes every 5 seconds while open.</div></div>`;
  clearInterval(playerModalTimer);
  playerModalTimer = setInterval(() => {
    const active = document.activeElement;
    const editing = active && document.getElementById('playerModal').contains(active) && ['INPUT','SELECT','TEXTAREA'].includes(active.tagName);
    if (document.getElementById('playerModal').classList.contains('open') && !editing) loadPlayerModal(playerModalAccountId);
  }, 5000);
}
function closePlayerModal(){
  clearInterval(playerModalTimer);
  playerModalTimer = null;
  playerModalAccountId = '';
  document.getElementById('playerModal').classList.remove('open');
  announce('Player detail closed');
}
async function settings(serial=loadSerial){
  const [env, transfer, onlineState, artificialExchange, configs] = await Promise.all([
    api('/api/settings/env'),
    api('/api/settings/director-transfer'),
    api('/api/settings/player-online-state'),
    api('/api/admin/artificial-exchange', {timeoutMs:60000}),
    api('/api/settings/configs')
  ]);
  if (serial !== loadSerial) return;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Settings</h2><div class="toolbar"><button data-jump="security">Security</button><button data-jump="ops">Ops</button><button id="saveEnvBtn" class="primary">Save env settings</button></div></div><div class="panelBand"><p class="muted">These write <code>.env</code>, <code>config/director.ini</code>, or <code>config/UserGame.ini</code> with a backup under <code>backups/admin-panel</code>. Most service settings need the affected containers recreated before running processes pick them up.</p></div>${actionGrid([{tab:'ops',label:'Check live state'},{tab:'mutations',label:'Create backup',className:'primary'},{tab:'characters',label:'Inspect players'}])}${artificialExchangePanel(artificialExchange)}${envEditor(env)}<div class="twoCol">${playerOnlineStateEditor(onlineState)}${directorTransferEditor(transfer)}</div><div class="panelBand"><h2>Config Files</h2><select id="cfg">${Object.keys(configs).map(k=>`<option>${esc(k)}</option>`).join('')}</select><textarea id="cfgText"></textarea><p><button id="saveCfgBtn" class="primary">Save config with backup</button></p></div></div>`;
  window.configs = configs; selectCfg();
  document.getElementById('cfg').addEventListener('change', selectCfg);
  document.getElementById('saveEnvBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', saveEnv));
  document.getElementById('savePlayerOnlineStateBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', savePlayerOnlineState));
  document.getElementById('saveDirectorTransferBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', saveDirectorTransfer));
  document.getElementById('saveCfgBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', saveCfg));
  wireArtificialExchangeControls();
}

async function catalog(serial=loadSerial){
  const [surfaces, evidence, validation, knobs, events] = await Promise.all([
    api('/api/catalog/surfaces'),
    api('/api/catalog/evidence'),
    api('/api/catalog/validation'),
    api('/api/settings/typed-knobs'),
    api('/api/events')
  ]);
  if (serial !== loadSerial) return;
  const groups = surfaces.groups || {};
  const groupPanels = Object.entries(groups).map(([name, rows]) => `<details class="panelBand" open><summary>${esc(name)}</summary>${table(rows || [])}</details>`).join('');
  const knobRows = Object.values(knobs.values || {}).map(k => ({id:k.id,label:k.label,value:k.value,confidence:k.confidence,risk:k.risk,restartRequired:k.restart,why:k.why}));
  const eventRows = (events.events || []).map(e => ({id:e.id,name:e.name,status:e.status,createdAt:e.createdAt,runAt:e.runAt,actions:(e.plan || []).length}));
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Content Catalog</h2><div class="toolbar"><span class="pill ${surfaces.enabled ? 'ok' : 'warn'}">catalog ${surfaces.enabled ? 'enabled' : 'disabled'}</span><span class="pill ${knobs.enabled ? 'warn' : 'ok'}">typed writes ${knobs.enabled ? 'enabled' : 'dry-run only'}</span><span class="pill ${events.executionEnabled ? 'warn' : 'ok'}">events ${events.executionEnabled ? 'execute enabled' : 'plan only'}</span><button data-jump="settings">Settings</button><button data-jump="mutations">Admin Actions</button></div></div><div class="panelBand"><p class="muted">Catalog endpoints are read-only. Typed knob writes require the mutation gate, typed-knob gate, backup, and confirmation phrase.</p></div>${groupPanels}<div class="twoCol"><div class="panelBand"><h2>Typed Knob Dry Run</h2><div class="grid"><label>Knob<select id="typedKnobId">${Object.values(knobs.values || {}).map(k=>`<option value="${esc(k.id)}">${esc(k.label || k.id)}</option>`).join('')}</select></label><label>Value<input id="typedKnobValue" placeholder="true, 2.5, or JSON caps"></label></div><p><button id="typedKnobDryRunBtn" class="primary">Preview typed write</button></p><pre id="typedKnobResult"></pre></div><div class="panelBand"><h2>Spice Fields</h2><p><button id="inspectSpiceBtn" class="primary">Inspect spice/resource state</button></p><pre id="spiceInspectResult"></pre></div></div><div class="twoCol"><div class="panelBand"><h2>Progression Inspect</h2><label>Account ID<input id="progressionAccountId"></label><p><button id="progressionInspectBtn" class="primary">Inspect progression surfaces</button></p><pre id="progressionInspectResult"></pre></div><div class="panelBand"><h2>Faction Reputation Dry Run</h2><div class="grid"><label>Account ID<input id="repAccountId"></label><label>Faction ID<input id="repFactionId"></label><label>Amount<input id="repAmount" value="100"></label><label>Mode<select id="repMode"><option>add</option><option>set</option></select></label></div><p><button id="repDryRunBtn" class="primary">Preview reputation write</button></p><pre id="repDryRunResult"></pre></div><div class="panelBand"><h2>Faction Change Dry Run</h2><div class="grid"><label>Account ID<input id="factionAccountId"></label><label>Faction ID<input id="factionId" value="3"></label><label>Neutral faction ID<input id="neutralFactionId" value="3"></label></div><p><button id="factionDryRunBtn" class="primary">Preview faction change</button></p><pre id="factionDryRunResult"></pre></div></div><div class="twoCol"><div class="panelBand"><h2>Journey Dry Run</h2><div class="grid"><label>Account ID<input id="journeyAccountId"></label><label>Action<select id="journeyAction"><option>reveal</option><option>complete</option><option>reset</option><option>delete</option></select></label></div><label>Story node IDs<textarea id="journeyStoryNodes" rows="3" placeholder="comma-separated story node ids"></textarea></label><p><button id="journeyDryRunBtn" class="primary">Preview journey mutation</button></p><pre id="journeyDryRunResult"></pre></div><div class="panelBand"><h2>Economy Bundle Dry Run</h2><label>Bundle JSON<textarea id="bundlePlanJson" rows="7">{"currency":[],"xp":[],"items":[],"dry_run":true}</textarea></label><p><button id="bundleDryRunBtn" class="primary">Preview bundle</button></p><pre id="bundleDryRunResult"></pre></div></div><div class="twoCol"><div class="panelBand"><h2>Event Dry Run</h2><label>Event JSON<textarea id="eventPlanJson" rows="7">{"name":"Deep Desert spice proposal","actions":[{"type":"spice-cap-proposal","caps":{"Medium":{"primed":24,"active":24},"Large":{"primed":3,"active":3}}}]}</textarea></label><p><button id="eventDryRunBtn" class="primary">Preview event</button></p><pre id="eventDryRunResult"></pre></div><div class="panelBand"><h2>Typed Knobs</h2>${table(knobRows)}</div></div><div class="panelBand"><h2>Validation</h2>${table(validation.commands || [])}</div><details class="panelBand"><summary>Evidence Rules</summary><ul>${(evidence.rules || []).map(r=>`<li>${esc(r)}</li>`).join('')}</ul><p class="muted">${esc((evidence.schema || []).join(', '))}</p></details><details class="panelBand"><summary>Scheduled Events</summary>${table(eventRows)}</details></div>`;
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>World State Inspect</h2><div class="grid"><label>Account ID<input id="worldAccountId"></label><label>Player ID<input id="worldPlayerId"></label><label>Guild ID<input id="worldGuildId"></label></div><p><button id="worldInspectBtn" class="primary">Inspect world surfaces</button></p><pre id="worldInspectResult"></pre></div><div class="panelBand"><h2>Guild Dry Run</h2><div class="grid"><label>Action<select id="guildAction"><option>edit-description</option><option>promote-member</option><option>demote-member</option></select></label><label>Guild ID<input id="guildId"></label><label>Player ID<input id="guildPlayerId"></label><label>New role<input id="guildNewRole"></label></div><label>Description<textarea id="guildDescription" rows="3"></textarea></label><p><button id="guildDryRunBtn" class="primary">Preview guild mutation</button></p><pre id="guildDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Marker Delete Dry Run</h2><div class="grid"><label>Action<select id="markerAction"><option>delete-by-id</option><option>delete-static-location</option></select></label><label>Marker IDs<input id="markerIds" placeholder="comma-separated ids"></label><label>Static keys<input id="markerStaticKeys" placeholder="comma-separated keys"></label></div><p><button id="markerDryRunBtn" class="primary">Preview marker deletion</button></p><pre id="markerDryRunResult"></pre></div><div class="panelBand"><h2>Landclaim Dry Run</h2><div class="grid"><label>Totem ID<input id="landclaimTotemId"></label><label>Grid X<input id="landclaimGridX"></label><label>Grid Y<input id="landclaimGridY"></label></div><p><button id="landclaimDryRunBtn" class="primary">Preview landclaim segment</button></p><pre id="landclaimDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Economy Inspect</h2><div class="grid"><label>Account ID<input id="economyAccountId"></label><label>Player/Owner ID<input id="economyPlayerId"></label><label>Controller ID<input id="economyControllerId"></label><label>Exchange ID<input id="economyExchangeId"></label></div><p><button id="economyInspectBtn" class="primary">Inspect economy surfaces</button></p><pre id="economyInspectResult"></pre></div><div class="panelBand"><h2>Exchange Solari Dry Run</h2><div class="grid"><label>Owner ID<input id="exchangeOwnerId"></label><label>Controller ID<input id="exchangeControllerId"></label><label>Amount<input id="exchangeAmount" value="1000"></label><label>Mode<select id="exchangeMode"><option>add</option><option>set</option></select></label></div><p><button id="exchangeDryRunBtn" class="primary">Preview exchange balance</button></p><pre id="exchangeDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Player Lifecycle Inspect</h2><div class="grid"><label>Account ID<input id="lifecycleAccountId"></label><label>Player ID<input id="lifecyclePlayerId"></label></div><p><button id="lifecycleInspectBtn" class="primary">Inspect lifecycle surfaces</button></p><pre id="lifecycleInspectResult"></pre></div><div class="panelBand"><h2>Player Tags Dry Run</h2><div class="grid"><label>Account ID<input id="tagAccountId"></label><label>Add tags<input id="tagsToAdd" placeholder="comma-separated"></label><label>Remove tags<input id="tagsToRemove" placeholder="comma-separated"></label></div><p><button id="tagsDryRunBtn" class="primary">Preview tag update</button></p><pre id="tagsDryRunResult"></pre></div><div class="panelBand"><h2>Access Codes Dry Run</h2><div class="grid"><label>Action<select id="accessCodeAction"><option>create</option><option>delete</option><option>reset</option></select></label><label>Account ID<input id="accessCodeAccountId"></label><label>Access code<input id="accessCodeValue"></label><label>Type<input id="accessCodeType" value="0"></label></div><p><button id="accessCodeDryRunBtn" class="primary">Preview access-code change</button></p><pre id="accessCodeDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Communinet Dry Run</h2><div class="grid"><label>Action<select id="communinetAction"><option>update-data</option><option>update-channel</option><option>remove-channel</option></select></label><label>Account ID<input id="communinetAccountId"></label><label>Active<input id="communinetActive" value="true"></label><label>Selected channel<input id="communinetSelectedChannel"></label><label>Channel<input id="communinetChannel"></label><label>Tuned<input id="communinetTuned" value="true"></label></div><p><button id="communinetDryRunBtn" class="primary">Preview Communinet change</button></p><pre id="communinetDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Tutorial Dry Run</h2><div class="grid"><label>Player ID<input id="tutorialPlayerId"></label><label>Tutorial ID<input id="tutorialId"></label><label>State<input id="tutorialState" value="1"></label></div><p><button id="tutorialDryRunBtn" class="primary">Preview tutorial state</button></p><pre id="tutorialDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Permission Dry Run</h2><div class="grid"><label>Action<select id="permissionAction"><option>set-name</option><option>set-access-level</option><option>set-player-rank</option><option>remove-player-rank</option></select></label><label>Actor ID<input id="permissionActorId"></label><label>Name<input id="permissionName"></label><label>Access level<input id="permissionAccessLevel"></label><label>Player ID<input id="permissionPlayerId"></label><label>Rank<input id="permissionRank"></label><label>Map ID<input id="permissionMapId"></label></div><p><button id="permissionDryRunBtn" class="primary">Preview permission change</button></p><pre id="permissionDryRunResult"></pre></div></div>`);
  view.querySelector('.pageStack').insertAdjacentHTML('beforeend', `<div class="twoCol"><div class="panelBand"><h2>Vendor Cycle Dry Run</h2><div class="grid"><label>Vendor ID<input id="vendorId"></label><label>Player ID<input id="vendorPlayerId"></label><label>Timestamp<input id="vendorTimestamp"></label></div><p><button id="vendorDryRunBtn" class="primary">Preview vendor timestamp</button></p><pre id="vendorDryRunResult"></pre></div></div>`);
  wireCatalogControls();
}

function parseJsonInput(id){
  const text = document.getElementById(id).value.trim();
  return text ? JSON.parse(text) : {};
}
function parseTypedKnobValue(raw){
  const text = String(raw || '').trim();
  if (!text) return '';
  if (text.startsWith('{') || text.startsWith('[')) return JSON.parse(text);
  return text;
}
function wireCatalogControls(root=document){
  root.querySelector('#typedKnobDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Previewing...', async () => {
    const key = document.getElementById('typedKnobId').value;
    const value = parseTypedKnobValue(document.getElementById('typedKnobValue').value);
    const result = await api('/api/settings/typed-knobs', {method:'POST', body:JSON.stringify({dry_run:true, updates:{[key]:value}})});
    document.getElementById('typedKnobResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#inspectSpiceBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Inspecting...', async () => {
    const result = await api('/api/admin/spice-fields/inspect', {method:'POST', body:'{}'});
    document.getElementById('spiceInspectResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#eventDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/events/dry-run', {method:'POST', body:JSON.stringify(parseJsonInput('eventPlanJson'))});
    document.getElementById('eventDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#bundleDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const body = parseJsonInput('bundlePlanJson');
    body.dry_run = true;
    const result = await api('/api/admin/bundle', {method:'POST', body:JSON.stringify(body)});
    document.getElementById('bundleDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#progressionInspectBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Inspecting...', async () => {
    const result = await api('/api/admin/progression/inspect', {method:'POST', body:JSON.stringify({account_id:document.getElementById('progressionAccountId').value})});
    document.getElementById('progressionInspectResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#repDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/faction-reputation', {method:'POST', body:JSON.stringify({dry_run:true, account_id:repAccountId.value, faction_id:repFactionId.value, amount:repAmount.value, mode:repMode.value})});
    document.getElementById('repDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#journeyDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/journey', {method:'POST', body:JSON.stringify({dry_run:true, account_id:journeyAccountId.value, action:journeyAction.value, story_node_ids:journeyStoryNodes.value})});
    document.getElementById('journeyDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#factionDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/faction', {method:'POST', body:JSON.stringify({dry_run:true, account_id:factionAccountId.value, faction_id:factionId.value, neutral_faction_id:neutralFactionId.value})});
    document.getElementById('factionDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#worldInspectBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Inspecting...', async () => {
    const result = await api('/api/admin/world-state/inspect', {method:'POST', body:JSON.stringify({account_id:worldAccountId.value, player_id:worldPlayerId.value, guild_id:worldGuildId.value})});
    document.getElementById('worldInspectResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#guildDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/guild', {method:'POST', body:JSON.stringify({dry_run:true, action:guildAction.value, guild_id:guildId.value, player_id:guildPlayerId.value, new_role:guildNewRole.value, description:guildDescription.value})});
    document.getElementById('guildDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#markerDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/marker', {method:'POST', body:JSON.stringify({dry_run:true, action:markerAction.value, marker_ids:markerIds.value, static_location_keys:markerStaticKeys.value})});
    document.getElementById('markerDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#landclaimDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/landclaim', {method:'POST', body:JSON.stringify({dry_run:true, action:'add-segment', totem_id:landclaimTotemId.value, grid_location_x:landclaimGridX.value, grid_location_y:landclaimGridY.value})});
    document.getElementById('landclaimDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#economyInspectBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Inspecting...', async () => {
    const result = await api('/api/admin/economy/inspect', {method:'POST', body:JSON.stringify({account_id:economyAccountId.value, player_id:economyPlayerId.value, controller_id:economyControllerId.value, exchange_id:economyExchangeId.value})});
    document.getElementById('economyInspectResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#exchangeDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/exchange', {method:'POST', body:JSON.stringify({dry_run:true, owner_id:exchangeOwnerId.value, controller_id:exchangeControllerId.value || exchangeOwnerId.value, amount:exchangeAmount.value, mode:exchangeMode.value})});
    document.getElementById('exchangeDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#lifecycleInspectBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Inspecting...', async () => {
    const result = await api('/api/admin/player-lifecycle/inspect', {method:'POST', body:JSON.stringify({account_id:lifecycleAccountId.value, player_id:lifecyclePlayerId.value})});
    document.getElementById('lifecycleInspectResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#tagsDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/player-tags', {method:'POST', body:JSON.stringify({dry_run:true, account_id:tagAccountId.value, tags_to_add:tagsToAdd.value, tags_to_remove:tagsToRemove.value})});
    document.getElementById('tagsDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#accessCodeDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/access-code', {method:'POST', body:JSON.stringify({dry_run:true, action:accessCodeAction.value, account_id:accessCodeAccountId.value, access_code:accessCodeValue.value, access_code_type:accessCodeType.value})});
    document.getElementById('accessCodeDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#communinetDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/communinet', {method:'POST', body:JSON.stringify({dry_run:true, action:communinetAction.value, account_id:communinetAccountId.value, is_active:communinetActive.value, selected_channel_name:communinetSelectedChannel.value, channel_name:communinetChannel.value, is_tuned:communinetTuned.value})});
    document.getElementById('communinetDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#tutorialDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/tutorial', {method:'POST', body:JSON.stringify({dry_run:true, player_id:tutorialPlayerId.value, tutorial_id:tutorialId.value, tutorial_state:tutorialState.value})});
    document.getElementById('tutorialDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#permissionDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/permission', {method:'POST', body:JSON.stringify({dry_run:true, action:permissionAction.value, actor_id:permissionActorId.value, name:permissionName.value, access_level:permissionAccessLevel.value, player_id:permissionPlayerId.value, rank:permissionRank.value, map_id:permissionMapId.value})});
    document.getElementById('permissionDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
  root.querySelector('#vendorDryRunBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/vendor', {method:'POST', body:JSON.stringify({dry_run:true, action:'set-cycle-timestamp', vendor_id:vendorId.value, player_id:vendorPlayerId.value, timestamp:vendorTimestamp.value})});
    document.getElementById('vendorDryRunResult').textContent = JSON.stringify(result, null, 2);
  }));
}
function selectCfg(){ const name=document.getElementById('cfg').value; document.getElementById('cfgText').value = window.configs[name] || ''; }
async function saveEnv(){
  const body={};
  document.querySelectorAll('[id^=env_]').forEach(i => {
    if (i.dataset.secret === 'true' && !i.value) return;
    body[i.id.slice(4)] = i.value;
  });
  await api('/api/settings/env', {method:'POST', body:JSON.stringify(body)}); notify('Saved .env settings');
}
async function saveCfg(){
  const name=document.getElementById('cfg').value;
  await api('/api/settings/configs/' + encodeURIComponent(name), {method:'POST', body:JSON.stringify({content:document.getElementById('cfgText').value})});
  notify('Saved ' + name);
}
async function saveDirectorTransfer(){
  const body={};
  document.querySelectorAll('[id^=transfer_]').forEach(i => body[i.id.slice(9)] = i.value);
  await api('/api/settings/director-transfer', {method:'POST', body:JSON.stringify(body)});
  notify('Saved director transfer settings');
}
async function savePlayerOnlineState(){
  const body={};
  document.querySelectorAll('[id^=online_]').forEach(i => body[i.id.slice(7)] = i.value);
  await api('/api/settings/player-online-state', {method:'POST', body:JSON.stringify(body)});
  notify('Saved logout timers');
}
function wireArtificialExchangeControls(){
  document.getElementById('aeRefreshBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Refreshing...', async () => {
    await settings(++loadSerial);
    notify('Refreshed Artificial Exchange');
  }));
  document.querySelectorAll('[data-ae-action]').forEach(button => {
    button.addEventListener('click', e => runAction(e.currentTarget, 'Running...', async () => {
      const action = e.currentTarget.dataset.aeAction;
      const result = await api('/api/admin/artificial-exchange', {method:'POST', body:JSON.stringify({action}), timeoutMs:120000});
      const output = document.getElementById('artificialExchangeResult');
      if (output) output.textContent = JSON.stringify(result, null, 2);
      notify(result.ok ? `Artificial Exchange ${action} finished` : `Artificial Exchange ${action} failed`, result.ok ? 'good' : 'bad');
    }));
  });
}
async function mutations(serial=loadSerial){
  const [ref, characterRows] = await Promise.all([
    adminReference(),
    api('/api/characters?q=')
  ]);
  if (serial !== loadSerial) return;
  const referenceErrors = ref.errors && Object.keys(ref.errors).length ? `<div class="card"><h2>Reference Errors</h2><pre>${esc(JSON.stringify(ref.errors, null, 2))}</pre></div>` : '';
  view.innerHTML = `<div class="pageStack">${referenceErrors}<div class="sectionHeader"><h2>Admin Actions</h2><div class="toolbar"><button data-jump="characters">Players</button><button data-jump="settings">Settings</button><button data-jump="security">Audit</button></div></div><div class="panelBand"><h2>Target Player</h2><div class="grid"><label>Character<select id="adminCharacterSelect">${characterOptions(characterRows)}</select></label><label>Player controller ID<input id="pcid"></label><label>Account ID<input id="grantAccount" placeholder="auto-select player inventory"></label><label>Character name<input id="grantCharacter" placeholder="auto-select by name"></label></div></div>${offlineTeleportPanel(ref, characterRows)}<div class="panelBand"><h2>Character Slots</h2><div class="grid"><label>Action<select id="slotAction"><option>new-character</option><option>switch-character</option><option>restore-character</option></select></label><label>Target hibernated account ID<input id="slotTargetAccount"></label></div><p><button id="slotInspectBtn" class="primary">Inspect slots</button> <button id="slotPlanBtn" class="primary">Preview swap</button> <button id="slotExecuteBtn" class="danger">Execute swap</button></p><pre id="slotResult"></pre></div><div class="twoCol"><div class="panelBand"><h2>Currency and XP</h2><p class="muted">Select a character first; balances and tracks populate from that player.</p><div class="grid"><label>Currency ID<select id="curid">${options(ref.currencyIds, 'currency_id', '1')}</select></label><label>Amount<input id="amount" value="1000"></label><label>Mode<select id="mode"><option>add</option><option>set</option></select></label></div><p><button id="currencyBtn" class="primary">Apply currency</button></p><div class="grid"><label>Player/controller ID<input id="xpid"></label><label>Track type<select id="track">${options(ref.specializationTrackTypes, 'track_type')}</select></label><label>XP amount<input id="xpamount" value="1000"></label><label>Level for set/new track<input id="xplevel" value="0"></label><label>Mode<select id="xpmode"><option>add</option><option>set</option></select></label></div><p><button id="xpBtn" class="primary">Apply XP</button></p></div><div class="panelBand"><h2>Item Grants</h2><p class="muted">Use a known template ID and dry run before writing new items.</p><div class="grid"><label>Known inventory<select id="grantInventorySelect">${inventoryOptions(ref.recentInventories)}</select></label><label>Inventory ID<input id="grantInventory" placeholder="explicit inventory"></label><label class="hidden">Character<select id="grantCharacterSelect">${characterOptions(characterRows)}</select></label><label>Inventory type<select id="grantInventoryType">${inventoryTypeOptions(ref.inventoryTypes)}</select></label><label>Template ID<input id="grantTemplate" list="itemTemplateList" placeholder="SMG_Unique_LargeMag_06"></label><label>Stack size<input id="grantStack" value="1"></label><label>Quality level<input id="grantQuality" value="0"></label><label>Position index<input id="grantPosition" placeholder="auto"></label></div><details><summary>Advanced stats JSON</summary><textarea id="grantStats">{}</textarea></details><p><button id="dryRunItemBtn" class="primary">Dry run</button> <button id="grantItemBtn" class="danger">Grant item</button></p><pre id="grantResult"></pre></div></div><div class="twoCol"><div class="panelBand"><h2>Item Maintenance</h2><div class="grid"><label class="hidden">Character<select id="itemCharacterSelect">${characterOptions(characterRows)}</select></label><label>Owned item<select id="itemEditSelect"><option value="">Select a character first</option></select></label><label>Item ID<input id="itemEditId"></label><label>New stack size<input id="itemEditStack" value="1"></label><label>Delete count<input id="itemDeleteCount" placeholder="blank/all"></label></div><p><button id="setItemStackBtn" class="primary">Set stack</button> <button id="deleteItemBtn" class="danger">Delete item/count</button></p><pre id="itemEditResult"></pre></div><div class="panelBand"><h2>Specialization Keystones</h2><div class="grid"><label>Player/controller ID<input id="keyPlayer"></label><label>Keystone<select id="keystone">${options(ref.keystones, 'name')}</select></label></div><p><button id="purchaseKeystoneBtn" class="primary">Purchase keystone</button> <button id="resetKeystonesBtn" class="danger">Reset all keystones</button></p><pre id="keystoneResult"></pre></div></div><details class="panelBand"><summary>Backup</summary><p class="muted">Creates a Postgres custom-format dump under <code>backups/admin-panel</code>.</p><button id="backupBtn" class="primary">Create DB backup</button><pre id="backupResult"></pre></details><datalist id="itemTemplateList">${templateDatalist(ref)}</datalist><details class="panelBand"><summary>Known Item Templates</summary>${table(ref.knownItemTemplates)}</details><details class="panelBand"><summary>Observed Item Templates</summary>${table(ref.observedItemTemplates)}</details><details class="panelBand"><summary>Recent Inventories</summary>${table(ref.recentInventories)}</details><details class="panelBand"><summary>Inventory Types</summary>${table(ref.inventoryTypes)}</details></div>`;
  const loadCharacterAdminDetails = async (accountId, serial=detailLoadSerial) => {
    const itemSelect = document.getElementById('itemEditSelect');
    const inventorySelect = document.getElementById('grantInventorySelect');
    const currencySelect = document.getElementById('curid');
    const trackSelect = document.getElementById('track');
    if (!itemSelect || !accountId) return;
    itemSelect.innerHTML = '<option value="">Loading items...</option>';
    if (inventorySelect) inventorySelect.innerHTML = '<option value="">Loading inventories...</option>';
    document.getElementById('itemEditId').value = '';
    try {
      const detail = await api('/api/characters/' + encodeURIComponent(accountId));
      if (serial !== detailLoadSerial) return;
      const items = detail.inventoryItems || [];
      const inventories = detail.inventories || [];
      const currency = detail.currency || [];
      const specialization = detail.specialization || [];
      itemSelect.innerHTML = inventoryItemOptions(items);
      if (currencySelect) {
        currencySelect.innerHTML = currencyBalanceOptions(currency, ref.currencyIds);
      }
      if (trackSelect) {
        trackSelect.innerHTML = specializationOptions(specialization, ref.specializationTrackTypes);
        const level = trackSelect.selectedOptions?.[0]?.dataset.level || '';
        if (level) document.getElementById('xplevel').value = level;
      }
      if (inventorySelect) {
        inventorySelect.innerHTML = inventoryOptions(inventories);
        document.getElementById('grantInventory').value = inventorySelect.value || '';
        const inventoryType = inventorySelect.selectedOptions?.[0]?.dataset.type || '';
        if (inventoryType) document.getElementById('grantInventoryType').value = inventoryType;
      }
      document.getElementById('itemEditResult').textContent = JSON.stringify({
        character: detail.player?.character_name || accountId,
        currencyBalances: currency.length,
        specializationTracks: specialization.length,
        inventories: inventories.length,
        inventoryItems: items.length
      }, null, 2);
    } catch (e) {
      if (serial !== detailLoadSerial) return;
      itemSelect.innerHTML = '<option value="">Could not load items</option>';
      document.getElementById('itemEditResult').textContent = e.message;
    }
  };
  const fillCharacter = async (select) => {
    const serial = ++detailLoadSerial;
    const option = select?.selectedOptions?.[0];
    if (!option || !option.value) return;
    ['adminCharacterSelect', 'grantCharacterSelect', 'itemCharacterSelect'].forEach(id => {
      const other = document.getElementById(id);
      if (other && other !== select) other.value = option.value;
    });
    if (document.getElementById('grantAccount')) document.getElementById('grantAccount').value = option.value;
    if (document.getElementById('teleportAccount')) document.getElementById('teleportAccount').value = option.value;
    if (document.getElementById('grantCharacter')) document.getElementById('grantCharacter').value = option.dataset.name || '';
    if (document.getElementById('pcid')) document.getElementById('pcid').value = option.dataset.controller || '';
    if (document.getElementById('xpid')) document.getElementById('xpid').value = option.dataset.controller || '';
    if (document.getElementById('keyPlayer')) document.getElementById('keyPlayer').value = option.dataset.controller || '';
    await loadCharacterAdminDetails(option.value, serial);
    if (serial !== detailLoadSerial) return;
  };
  document.getElementById('adminCharacterSelect').addEventListener('change', e => fillCharacter(e.target).catch(err => reportClientError(err, 'Load player admin detail')));
  document.getElementById('grantCharacterSelect').addEventListener('change', e => fillCharacter(e.target).catch(err => reportClientError(err, 'Load player admin detail')));
  document.getElementById('itemCharacterSelect').addEventListener('change', e => fillCharacter(e.target).catch(err => reportClientError(err, 'Load player admin detail')));
  const initialTarget = document.getElementById('adminCharacterSelect');
  const initialOption = Array.from(initialTarget.options).find(o => o.value && String(o.dataset.status || '').toLowerCase() === 'online') || Array.from(initialTarget.options).find(o => o.value);
  if (initialOption) {
    initialTarget.value = initialOption.value;
    fillCharacter(initialTarget).catch(err => reportClientError(err, 'Load default player admin detail'));
  }
  document.getElementById('itemEditSelect').addEventListener('change', e => {
    const option = e.target.selectedOptions?.[0];
    document.getElementById('itemEditId').value = e.target.value || '';
    if (option?.dataset.stack) document.getElementById('itemEditStack').value = option.dataset.stack;
    if (option?.dataset.template && document.getElementById('grantTemplate')) document.getElementById('grantTemplate').value = option.dataset.template;
    if (option?.dataset.inventory && document.getElementById('grantInventory')) document.getElementById('grantInventory').value = option.dataset.inventory;
  });
  document.getElementById('track').addEventListener('change', e => {
    const level = e.target.selectedOptions?.[0]?.dataset.level || '';
    if (level) document.getElementById('xplevel').value = level;
  });
  const invSelect = document.getElementById('grantInventorySelect');
  if (invSelect && invSelect.value) document.getElementById('grantInventory').value = invSelect.value;
  invSelect?.addEventListener('change', () => {
    document.getElementById('grantInventory').value = invSelect.value;
    const inventoryType = invSelect.selectedOptions?.[0]?.dataset.type || '';
    if (inventoryType) document.getElementById('grantInventoryType').value = inventoryType;
  });
  document.getElementById('backupBtn').addEventListener('click', e => runAction(e.currentTarget, 'Backing up...', backup));
  renderOfflineTeleportMap();
  ['teleportX','teleportY','teleportZ'].forEach(id => document.getElementById(id)?.addEventListener('input', renderOfflineTeleportMap));
  document.getElementById('teleportPreviewBtn').addEventListener('click', e => runAction(e.currentTarget, 'Previewing...', () => offlineTeleport(true)));
  document.getElementById('teleportExecuteBtn').addEventListener('click', e => runAction(e.currentTarget, 'Teleporting...', () => offlineTeleport(false)));
  document.getElementById('teleportUseSelectedBtn').addEventListener('click', e => runAction(e.currentTarget, 'Loading position...', useSelectedTeleportPosition));
  document.getElementById('slotInspectBtn').addEventListener('click', e => runAction(e.currentTarget, 'Inspecting...', async () => {
    const result = await api('/api/admin/character-slots?account_id=' + encodeURIComponent(grantAccount.value));
    document.getElementById('slotResult').textContent = JSON.stringify(result, null, 2);
  }));
  document.getElementById('slotPlanBtn').addEventListener('click', e => runAction(e.currentTarget, 'Planning...', async () => {
    const result = await api('/api/admin/character-slots/plan', {method:'POST', body:JSON.stringify({dry_run:true, account_id:grantAccount.value, action:slotAction.value, target_account_id:slotTargetAccount.value})});
    document.getElementById('slotResult').textContent = JSON.stringify(result, null, 2);
  }));
  document.getElementById('slotExecuteBtn').addEventListener('click', e => runAction(e.currentTarget, 'Executing...', async () => {
    if (!confirm('Execute native character swap? Both characters must be offline and a database backup will be created first.')) return;
    const result = await api('/api/admin/character-slots/execute', {method:'POST', body:JSON.stringify({dry_run:false, account_id:grantAccount.value, action:slotAction.value, target_account_id:slotTargetAccount.value, confirm:'SWAP CHARACTER'})});
    document.getElementById('slotResult').textContent = JSON.stringify(result, null, 2);
  }));
  document.getElementById('currencyBtn').addEventListener('click', e => runAction(e.currentTarget, 'Applying...', currency));
  document.getElementById('xpBtn').addEventListener('click', e => runAction(e.currentTarget, 'Applying...', xp));
  document.getElementById('purchaseKeystoneBtn').addEventListener('click', e => runAction(e.currentTarget, 'Purchasing...', purchaseKeystone));
  document.getElementById('resetKeystonesBtn').addEventListener('click', e => runAction(e.currentTarget, 'Resetting...', resetKeystones));
  document.getElementById('dryRunItemBtn').addEventListener('click', e => runAction(e.currentTarget, 'Checking...', () => grantItem(true)));
  document.getElementById('grantItemBtn').addEventListener('click', e => runAction(e.currentTarget, 'Granting...', () => grantItem(false)));
  document.getElementById('setItemStackBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', setItemStack));
  document.getElementById('deleteItemBtn').addEventListener('click', e => runAction(e.currentTarget, 'Deleting...', deleteItem));
  if (pendingAdminAccountId) {
    const target = document.getElementById('adminCharacterSelect');
    target.value = pendingAdminAccountId;
    pendingAdminAccountId = '';
    if (target.value) await fillCharacter(target);
  }
}
async function currency(){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:pcid.value,currency_id:curid.value,amount:amount.value,mode:mode.value})});
  notify('Currency updated');
}
async function currencyFor(playerControllerId){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:playerControllerId,currency_id:detailCurId.value,amount:detailCurAmount.value,mode:detailCurMode.value})});
  notify('Currency updated');
  return true;
}
async function xp(){
  await api('/api/admin/xp', {method:'POST', body:JSON.stringify({player_id:xpid.value,track_type:track.value,amount:xpamount.value,level:xplevel.value,mode:xpmode.value})});
  notify('XP updated');
}
async function xpFor(playerId){
  await api('/api/admin/xp', {method:'POST', body:JSON.stringify({player_id:playerId,track_type:detailTrack.value,amount:detailXpAmount.value,level:detailXpLevel.value,mode:detailXpMode.value})});
  notify('XP updated');
  return true;
}
async function backup(){
  const result = await api('/api/admin/backup', {method:'POST', body:'{}'});
  document.getElementById('backupResult').textContent = JSON.stringify(result, null, 2);
}
function teleportPayload(dryRun=true){
  return {
    dry_run: dryRun,
    account_id: document.getElementById('teleportAccount')?.value || document.getElementById('grantAccount')?.value || '',
    partition_id: document.getElementById('teleportPartition')?.value || '',
    location: {
      x: document.getElementById('teleportX')?.value || '0',
      y: document.getElementById('teleportY')?.value || '0',
      z: document.getElementById('teleportZ')?.value || '0'
    },
    confirm: dryRun ? '' : 'MOVE OFFLINE PLAYER'
  };
}
async function offlineTeleport(dryRun=true){
  if (!dryRun && !confirm('Execute offline teleport for the selected player? The target must already be Offline.')) return;
  const result = await api('/api/admin/player-recovery/offline-teleport', {method:'POST', body:JSON.stringify(teleportPayload(dryRun))});
  document.getElementById('teleportResult').textContent = JSON.stringify(result, null, 2);
  notify(dryRun ? 'Teleport preview ready' : 'Offline teleport executed');
}
async function useSelectedTeleportPosition(){
  const accountId = document.getElementById('teleportAccount')?.value || document.getElementById('grantAccount')?.value || '';
  if (!accountId) { notify('Select a player first', 'bad'); return; }
  const detail = await api('/api/characters/' + encodeURIComponent(accountId));
  const pawnId = detail.player?.player_pawn_id;
  const actor = (detail.actorLocations || []).find(row => String(row.actor_id ?? row.id ?? '') === String(pawnId)) || (detail.actorLocations || [])[0];
  if (!actor) { notify('No stored actor position found', 'bad'); return; }
  document.getElementById('teleportX').value = Number(actor.x || 0).toFixed(3);
  document.getElementById('teleportY').value = Number(actor.y || 0).toFixed(3);
  document.getElementById('teleportZ').value = Number(actor.z || 0).toFixed(3);
  if (actor.partition_id && document.getElementById('teleportPartition')) document.getElementById('teleportPartition').value = actor.partition_id;
  renderOfflineTeleportMap();
  document.getElementById('teleportResult').textContent = JSON.stringify({source:'stored actor transform', actor}, null, 2);
}
async function scheduleAnnouncement(){
  const result = await api('/api/ops/announcement', {method:'POST', body:JSON.stringify({
    delay: announceDelay.value,
    repeat_seconds: announceRepeat.value,
    message: announceMessage.value
  })});
  notify('Announcement scheduled');
  await ops();
}
async function cancelAnnouncement(){
  if (!confirm('Cancel active restart announcement?')) return;
  await api('/api/ops/announcement/cancel', {method:'POST', body:'{}'});
  await ops();
}
async function scheduleRestart(){
  const execute = restartExecute.value === 'true';
  const action = restartAction.value || 'restart';
  const targetLabel = restartTarget.options[restartTarget.selectedIndex]?.textContent || restartTarget.value;
  const delayLabel = restartDelay.options[restartDelay.selectedIndex]?.textContent || restartDelay.value;
  const repeatLabel = restartRepeat.options[restartRepeat.selectedIndex]?.textContent || restartRepeat.value;
  const actionLabel = execute ? 'execute the restart hook' : 'dry-run only';
  const backupLabel = restartBackup.checked ? 'backup first' : 'no backup';
  if (!confirm(`Schedule ${targetLabel} ${action} after ${delayLabel}?\nNotice repeat: ${repeatLabel}\nAction: ${actionLabel}\nBackup: ${backupLabel}`)) return;
  await api('/api/ops/restart', {method:'POST', body:JSON.stringify({
    target: restartTarget.value,
    action,
    delay: restartDelay.value,
    repeat_seconds: restartRepeat.value,
    message: restartMessage.value,
    announce: restartAnnounce.checked,
    execute,
    backup: restartBackup.checked
  })});
  notify('Maintenance scheduled');
  await ops();
}
async function cancelRestart(){
  if (!confirm('Cancel active scheduled restart?')) return;
  await api('/api/ops/restart/cancel', {method:'POST', body:'{}'});
  await ops();
}
async function purchaseKeystone(){
  const result = await api('/api/admin/keystone', {method:'POST', body:JSON.stringify({player_id:keyPlayer.value,keystone:keystone.value})});
  document.getElementById('keystoneResult').textContent = JSON.stringify(result, null, 2);
}
async function resetKeystones(){
  if (!confirm('Reset all purchased keystones for this player?')) return;
  const result = await api('/api/admin/reset-keystones', {method:'POST', body:JSON.stringify({player_id:keyPlayer.value,confirm:'RESET KEYSTONES'})});
  document.getElementById('keystoneResult').textContent = JSON.stringify(result, null, 2);
}
async function grantItem(dryRun=false){
  const result = await api('/api/admin/item', {method:'POST', body:JSON.stringify({inventory_id:grantInventory.value,account_id:grantAccount.value,character_name:grantCharacter.value,inventory_type:grantInventoryType.value,template_id:grantTemplate.value,stack_size:grantStack.value,quality_level:grantQuality.value,position_index:grantPosition.value,stats:grantStats.value,dry_run:dryRun})});
  document.getElementById('grantResult').textContent = JSON.stringify(result, null, 2);
}
async function grantItemForAccount(accountId, dryRun=false){
  const inventoryId = document.getElementById('detailGrantInventory')?.value || '';
  const result = await api('/api/admin/item', {method:'POST', body:JSON.stringify({inventory_id:inventoryId,account_id:accountId,template_id:detailGrantTemplate.value,stack_size:detailGrantStack.value,dry_run:dryRun,stats:{}})});
  document.getElementById('detailGrantResult').textContent = JSON.stringify(result, null, 2);
  return true;
}
async function setItemStack(){
  if (!confirm('Set this item stack size?')) return;
  const result = await api('/api/admin/item/stack', {method:'POST', body:JSON.stringify({item_id:itemEditId.value,stack_size:itemEditStack.value,confirm:'SET STACK'})});
  document.getElementById('itemEditResult').textContent = JSON.stringify(result, null, 2);
}
async function deleteItem(){
  if (!confirm('Delete this item or count from the stack?')) return;
  const result = await api('/api/admin/item/delete', {method:'POST', body:JSON.stringify({item_id:itemEditId.value,count:itemDeleteCount.value,confirm:'DELETE ITEM'})});
  document.getElementById('itemEditResult').textContent = JSON.stringify(result, null, 2);
}
async function setDetailItemStack(){
  const itemId = document.getElementById('detailItemSelect')?.value || '';
  if (!itemId) { notify('Select an owned item first', 'bad'); return false; }
  if (!confirm('Set this selected item stack size?')) return false;
  const result = await api('/api/admin/item/stack', {method:'POST', body:JSON.stringify({item_id:itemId,stack_size:detailGrantStack.value,confirm:'SET STACK'})});
  document.getElementById('detailGrantResult').textContent = JSON.stringify(result, null, 2);
  return true;
}
async function deleteDetailItem(){
  const itemId = document.getElementById('detailItemSelect')?.value || '';
  if (!itemId) { notify('Select an owned item first', 'bad'); return false; }
  if (!confirm('Delete this selected item or count from the stack?')) return false;
  const result = await api('/api/admin/item/delete', {method:'POST', body:JSON.stringify({item_id:itemId,count:detailDeleteCount.value,confirm:'DELETE ITEM'})});
  document.getElementById('detailGrantResult').textContent = JSON.stringify(result, null, 2);
  return true;
}
document.getElementById('saveTokenBtn').addEventListener('click', saveToken);
document.getElementById('clearTokenBtn').addEventListener('click', clearToken);
wireGlobalAffordances();
document.addEventListener('click', e => {
  const target = e.target.closest('[data-jump]');
  if (target) {
    e.preventDefault();
    show(target.dataset.jump);
  }
});
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => show(button.dataset.tab)));
window.addEventListener('hashchange', () => {
  const tab = location.hash.slice(1);
  if (validTabs.has(tab) && tab !== current) show(tab);
});
window.addEventListener('pageshow', e => {
  if (e.persisted) location.reload();
});
window.addEventListener('error', e => reportClientError(e.error || e.message));
window.addEventListener('unhandledrejection', e => reportClientError(e.reason || e, 'Request failed'));
setInterval(() => refreshStatus().catch(() => {}), 5000);
load();
</script>
</body>
</html>
"""


def main():
    ensure_announcement_thread()
    bind = os.environ.get("DUNE_ADMIN_BIND", "0.0.0.0")
    port = int(os.environ.get("DUNE_ADMIN_PORT", "8080"))
    ThreadingHTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
