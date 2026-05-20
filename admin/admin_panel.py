#!/usr/bin/env python3
import configparser
import concurrent.futures
import datetime
import hmac
import html
import json
import os
import pathlib
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
AUDIT_LOG = BACKUP_ROOT / "audit.jsonl"
AUDIT_MAX_BYTES = int(os.environ.get("DUNE_ADMIN_AUDIT_MAX_BYTES", str(5 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS", "10"))
MAX_ITEM_STACK_SIZE = int(os.environ.get("DUNE_ADMIN_MAX_ITEM_STACK_SIZE", "1000000"))
AUDIT_EVENT_LIMIT = int(os.environ.get("DUNE_ADMIN_AUDIT_EVENT_LIMIT", "100"))
HAGGA_MAP_MIN_X = float(os.environ.get("DUNE_HAGGA_MAP_MIN_X", "-407000"))
HAGGA_MAP_MAX_X = float(os.environ.get("DUNE_HAGGA_MAP_MAX_X", "407000"))
HAGGA_MAP_MIN_Y = float(os.environ.get("DUNE_HAGGA_MAP_MIN_Y", "-403500"))
HAGGA_MAP_MAX_Y = float(os.environ.get("DUNE_HAGGA_MAP_MAX_Y", "403500"))
HAGGA_MAP_INVERT_Y = os.environ.get("DUNE_HAGGA_MAP_INVERT_Y", "true").lower() not in ("0", "false", "no", "off")
ADMIN_REFERENCE_LIMIT = int(os.environ.get("DUNE_ADMIN_REFERENCE_LIMIT", "200"))
CHARACTER_SEARCH_LIMIT = int(os.environ.get("DUNE_ADMIN_CHARACTER_SEARCH_LIMIT", "100"))
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
CONFIRM_RESET_KEYSTONES = "RESET KEYSTONES"
CONFIRM_DELETE_ITEM = "DELETE ITEM"
CONFIRM_SET_STACK = "SET STACK"
CONFIRM_GM_COMMAND = "RUN GM COMMAND"
ANNOUNCEMENT_STATE_FILE = BACKUP_ROOT / "announcements.json"
RESTART_STATE_FILE = BACKUP_ROOT / "restart-jobs.json"
ANNOUNCEMENT_LOCK = threading.Lock()
RESTART_LOCK = threading.Lock()
ANNOUNCEMENT_THREAD_STARTED = False
ANNOUNCEMENT_POLL_SECONDS = 5
ANNOUNCEMENT_MAX_MESSAGE_BYTES = int(os.environ.get("DUNE_ADMIN_ANNOUNCEMENT_MAX_MESSAGE_BYTES", "500"))
ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45"))
ANNOUNCEMENT_COMMAND = os.environ.get("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh"))
RESTART_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_COMMAND_TIMEOUT_SECONDS", "1800"))
RESTART_COMMAND = os.environ.get("DUNE_ADMIN_RESTART_COMMAND", str(ROOT / "scripts" / "restart-target.sh"))
RESTART_ONLINE_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_ONLINE_TIMEOUT_SECONDS", "300"))
RESTART_ONLINE_POLL_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_ONLINE_POLL_SECONDS", "5"))
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
)

DIRECTOR_TRANSFER_RULESET_LABELS = {
    "0": "DenyAll",
    "1": "AllowFromPrivateOnly",
    "DenyAll": "DenyAll",
    "AllowFromPrivateOnly": "AllowFromPrivateOnly",
}

DIRECTOR_TRANSFER_RULESET_VALUES = {
    "DenyAll": "0",
    "AllowFromPrivateOnly": "1",
}

DIRECTOR_TRANSFER_SETTINGS = {
    "ShouldDeleteOriginCharactersDuringTransfers": {"type": "bool", "default": "true", "why": "Deletes the origin character after a successful transfer into this battlegroup."},
    "AcceptOutgoingCharacterTransfers": {"type": "bool", "default": "true", "why": "Allows characters on this battlegroup to transfer out."},
    "IncomingCharacterTransfers": {"type": "ruleset", "default": "0", "why": "Controls which origin server types can transfer characters into this battlegroup. Director build 1963158 expects numeric enum values: 0=DenyAll, 1=AllowFromPrivateOnly."},
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

ENV_KEY_DEFINITIONS = {
    "DUNE_STEAM_SERVER_DIR": {"group": "Install", "secret": False, "restart": False, "why": "Local Steam tool path used by image loading and preflight scripts."},
    "DUNE_IMAGE_TAG": {"group": "Install", "secret": False, "restart": True, "why": "Funcom container image tag used by Compose services."},
    "WORLD_NAME": {"group": "World", "secret": False, "restart": True, "why": "Public display name shown by Director/Text Router/Gateway."},
    "WORLD_UNIQUE_NAME": {"group": "World", "secret": False, "restart": True, "why": "Stable internal server/world identifier used for registration and routing."},
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
    "DUNE_ADMIN_MAX_BODY_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum accepted request body size."},
    "DUNE_ADMIN_AUDIT_MAX_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Audit log rotation threshold."},
    "DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Socket timeout to limit slow client abuse."},
    "DUNE_ADMIN_MAX_ITEM_STACK_SIZE": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum item stack mutation allowed through the panel."},
    "DUNE_ADMIN_AUDIT_EVENT_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Default number of audit events returned by the panel."},
    "DUNE_ADMIN_REFERENCE_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum reference rows returned by admin helper endpoints."},
    "DUNE_ADMIN_CHARACTER_SEARCH_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum character search rows returned."},
    "DUNE_ADMIN_BIND_ADDRESS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host interface used for the admin-panel published port. Keep this on 127.0.0.1 unless a trusted reverse proxy or VPN owns access."},
    "DUNE_ADMIN_HOST_PORT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host TCP port that publishes admin-panel:8080. Change this if another local service already owns 18080."},
    "DUNE_ADMIN_ALLOWED_HOSTS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host header allowlist for the admin HTTP service."},
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
        "nextSendAt": next_send_at,
        "lastSentAt": None,
        "deliveryCount": 0,
        "status": "scheduled",
        "lastError": None,
    }
    with ANNOUNCEMENT_LOCK:
        state = read_announcement_state()
        for existing in active_announcement_jobs(state):
            existing["status"] = "superseded"
        state.setdefault("jobs", []).append(job)
        write_announcement_state(state)
    return job


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
            "message": message,
            "restart_at": run_at,
            "action": action,
        })
    return job


def cancel_restart(job_id=None):
    with RESTART_LOCK:
        state = read_restart_state()
        changed = 0
        for job in active_restart_jobs(state):
            if job_id and job.get("id") != job_id:
                continue
            job["status"] = "cancelled"
            job["cancelledAt"] = time.time()
            changed += 1
        write_restart_state(state)
    return {"ok": True, "cancelled": changed}


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
    result = {"ok": False, "action": action, "disconnect": disconnect_result, "stop": stop_result, "backup": None, "start": None}
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

    if action == "shutdown":
        result["ok"] = True
        result["output"] = stop_result.get("output", "")
        return result

    start_result = run_restart_command(command, job, "start")
    result["start"] = start_result
    online_result = wait_for_restart_online() if start_result.get("ok") else {"ok": False, "skipped": True}
    result["online"] = online_result
    result["ok"] = bool(start_result.get("ok")) and bool(online_result.get("ok"))
    result["returncode"] = start_result.get("returncode")
    if start_result.get("ok") and not online_result.get("ok"):
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
                    repeat_seconds = int(job.get("repeatSeconds") or 0)
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
            "memoryPercent": round((mem_usage / mem_limit) * 100, 1) if mem_limit else None,
            "netIO": f"{fmt_bytes(net_rx)} / {fmt_bytes(net_tx)}",
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


def reference_query(errors, name, sql, params=None):
    try:
        return query(sql, params)
    except Exception as exc:
        errors[name] = str(exc)
        return []


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
            raise
        except Exception as exc:
            try:
                self.error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception:
                pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.validate_host()
            if parsed.path == "/":
                self.html(INDEX)
            elif parsed.path == "/static/hagga-basin.webp":
                self.static_file(STATIC_ROOT / "hagga-basin.webp", "image/webp")
            elif parsed.path == "/api/status":
                self.json({
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
            elif parsed.path == "/api/characters":
                self.require_token()
                params = urllib.parse.parse_qs(parsed.query)
                term = (params.get("q", [""])[0] or "").strip()
                self.json(self.characters(term))
            elif parsed.path == "/api/characters/roster":
                self.require_token()
                self.json(self.character_roster())
            elif parsed.path == "/api/players/hagga-basin":
                self.require_token()
                self.json(self.hagga_basin_players())
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
        except Exception as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_HEAD(self):
        self.validate_host()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.security_headers()
        self.end_headers()

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
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")
        except PermissionError as exc:
            self.audit("post-rejected", ok=False, error=str(exc))
            self.error(HTTPStatus.UNAUTHORIZED, str(exc))
        except NotImplementedError as exc:
            self.audit("post-not-implemented", ok=False, error=str(exc))
            self.error(HTTPStatus.NOT_IMPLEMENTED, str(exc))
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
        return query(sql, (term, like, like, like, CHARACTER_SEARCH_LIMIT))

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
        rows = query(sql)
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
        return {
            "map": "HaggaBasin",
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "bounds": bounds,
            "calibration": {
                "minX": HAGGA_MAP_MIN_X,
                "maxX": HAGGA_MAP_MAX_X,
                "minY": HAGGA_MAP_MIN_Y,
                "maxY": HAGGA_MAP_MAX_Y,
                "invertY": HAGGA_MAP_INVERT_Y,
                "source": "DUNE_HAGGA_MAP_* world-centimeter extents",
            },
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
            "account": query("select id, funcom_id, platform_name, platform_id, takeoverable from dune.accounts where id=%s", (account_id,)),
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
                       dimension_index, owner_account_id, serial
                from dune.actors
                where id in (%s,%s)
                order by id
            """, (controller_id, pawn_id)),
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
            "summary": {
                "readyAlive": current_ready_alive,
                "aliveActive": current_alive_active,
                "expectedPartitions": expected,
                "activeServers": active_count,
                "onlineMaps": sum(1 for row in map_status if row.get("online")),
                "totalMaps": len(map_status),
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
        checks = [
            {"name": "admin token configured", "ok": bool(ADMIN_TOKEN)},
            {"name": "admin token not placeholder", "ok": ADMIN_TOKEN not in ("", "change-me-admin-token")},
            {"name": "mutations disabled by default", "ok": not MUTATIONS_ENABLED, "value": MUTATIONS_ENABLED},
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
                "Use mutations only for deliberate admin edits after taking a backup.",
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
            "why": "The panel deliberately does not mount the container runtime socket or execute arbitrary shell commands.",
            "commands": [
                {"name": "Status", "command": "./scripts/status.sh .env", "when": "Quick health and high-signal logs."},
                {"name": "Routing capture before transition", "command": "./scripts/capture-routing.sh .env hagga-to-deep-desert-before", "when": "Before attempting a broken transition."},
                {"name": "Routing capture after transition", "command": "./scripts/capture-routing.sh .env hagga-to-deep-desert-after", "when": "Immediately after a failed transition."},
                {"name": "Runtime profile", "command": "./scripts/profile-runtime.sh .env", "when": "Memory/storage/network/process teardown."},
                {"name": "Summarize runtime profile", "command": "./scripts/summarize-runtime-profile.sh captures/YYYYMMDDTHHMMSSZ-runtime-profile", "when": "Compare profile captures."},
                {"name": "Network watch", "command": "./scripts/watch-network.sh .env", "when": "Check Postgres/RabbitMQ socket churn."},
                {"name": "Backup state", "command": "./scripts/backup-state.sh .env", "when": "Before upgrades, config surgery, or admin mutations."},
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

    def html(self, body):
        nonce = secrets.token_urlsafe(16)
        body = body.replace("__NONCE__", nonce)
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.security_headers(nonce=nonce)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json(self, value):
        data = json.dumps(value, default=json_default, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def static_file(self, path, content_type):
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
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, message):
        data = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def security_headers(self, nonce=None):
        self.send_header("Cache-Control", "no-store")
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
    main { display:grid; grid-template-columns:280px minmax(0,1fr); min-height:calc(100vh - 58px); }
    nav { border-right:1px solid var(--line); padding:14px; background:var(--nav); position:sticky; top:58px; height:calc(100vh - 58px); overflow:auto; }
    section { padding:18px; min-width:0; max-width:1680px; }
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
    .discordBadge { display:flex; align-items:center; justify-content:center; gap:8px; border:1px solid #5865f2; border-radius:8px; background:#1c2242; color:#f3f5ff; text-decoration:none; font-weight:700; padding:10px 12px; margin:14px 0; }
    .discordBadge:hover { border-color:#8ea1ff; background:#252d5c; }
    .panelBand { border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; margin-bottom:14px; }
    .pageStack { display:grid; gap:14px; }
    .twoCol { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(360px,.8fr); gap:14px; align-items:start; }
    .threeCol { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; align-items:start; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
    .metricGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:14px; }
    .metric { border:1px solid var(--line); border-radius:8px; background:var(--panel2); padding:12px; min-height:82px; }
    .metric .label { color:var(--muted); font-size:12px; }
    .metric .value { font-size:20px; font-weight:700; margin-top:6px; overflow-wrap:anywhere; }
    .pill { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); border-radius:999px; padding:5px 9px; background:#101310; color:var(--muted); font-size:12px; }
    .pill.ok { border-color:#315e31; color:var(--ok); }
    .pill.warn { border-color:#6d5624; color:var(--warn); }
    .pill.bad { border-color:#743932; color:var(--danger); }
    .row { display:flex; gap:8px; align-items:center; margin:8px 0; }
    .toolbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
    .sectionHeader { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }
    .sectionHeader .toolbar { margin-bottom:0; }
    .commandBar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:14px; }
    .commandBar button { min-height:38px; }
    .splitHeader { display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:10px; }
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
    .barList { display:grid; gap:9px; }
    .barRow { display:grid; grid-template-columns:minmax(100px,1fr) minmax(130px,2fr) auto; gap:10px; align-items:center; }
    .barTrack { height:10px; border-radius:999px; background:#0d100d; border:1px solid var(--line); overflow:hidden; }
    .barFill { height:100%; width:0%; background:var(--accent); }
    .barFill.ok { background:var(--ok); }
    .barFill.warn { background:var(--warn); }
    .barFill.bad { background:var(--danger); }
    .spark { display:flex; height:58px; gap:3px; align-items:end; padding:8px; border:1px solid var(--line); border-radius:8px; background:#0d100d; }
    .spark span { flex:1; min-width:3px; background:var(--accent); border-radius:2px 2px 0 0; opacity:.9; }
    .spark.compact { height:42px; }
    tr.selected td { background:#252416; }
    .mapGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; }
    .mapTile { border:1px solid var(--line); border-radius:7px; padding:9px; background:#101310; min-height:62px; }
    .mapTile.ok { border-color:#315e31; }
    .mapTile.bad { border-color:#743932; }
    .mapTile .name { font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .mapTile .meta { color:var(--muted); font-size:12px; margin-top:4px; }
    .haggaMap { position:relative; display:grid; place-items:start center; overflow:auto; background:#171513; inline-size:100%; max-block-size:min(78vh,900px); margin-inline:auto; border:1px solid var(--line); border-radius:8px; }
    .haggaMap svg { display:block; inline-size:min(100%,900px); min-inline-size:620px; aspect-ratio:1 / 1; block-size:auto; background:#171513; }
    .haggaMap .mapImage { opacity:.88; }
    .haggaMap .mapShade { fill:rgba(4,5,4,.22); }
    .haggaMap .gridLine { stroke:#f1d08a; stroke-width:1; opacity:.22; }
    .haggaMap .playerDot { fill:var(--ok); stroke:#071007; stroke-width:3; }
    .haggaMap .returnDot { fill:var(--warn); stroke:#160f04; stroke-width:3; }
    .haggaMap .uncertainLine { stroke:var(--warn); stroke-width:2; stroke-dasharray:7 7; opacity:.75; }
    .haggaMap .playerMarker:focus .playerDot, .haggaMap .playerMarker:hover .playerDot { fill:var(--accent); stroke:var(--text); }
    .haggaMap .playerLabel { fill:var(--text); font:700 13px system-ui,sans-serif; paint-order:stroke; stroke:#0b0d0a; stroke-width:4; }
    .haggaMap .coordLabel { fill:var(--muted); font:11px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .haggaMap .emptyState { fill:var(--muted); font:14px system-ui,sans-serif; text-anchor:middle; }
    .haggaMapStatus { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px; }
    .mapLegend { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
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
    @media (max-width: 1100px) { .twoCol, .threeCol { grid-template-columns:1fr; } }
    @media (max-width: 820px) { header { align-items:flex-start; flex-direction:column; } main { grid-template-columns:1fr; } nav { position:static; height:auto; border-right:0; border-bottom:1px solid var(--line); } .tabs { grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); } .row { flex-wrap:wrap; } .barRow { grid-template-columns:1fr; gap:4px; } }
  </style>
</head>
<body>
  <a class="skipLink" href="#view">Skip to dashboard</a>
  <header>
    <div class="brand"><h1>DASH Admin</h1><span class="subtle">Dune Awakening Self Host</span></div>
    <div class="row"><input id="token" type="password" placeholder="Admin token"><button id="saveTokenBtn">Use token</button><button id="clearTokenBtn">Clear</button></div>
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
      </div>
      <a class="discordBadge" href="https://discord.gg/cybhGntTts" target="_blank" rel="noopener noreferrer">Discord Support</a>
      <div class="card"><h3>Display</h3><div class="toolbar"><button id="contrastBtn">High contrast</button><button id="densityBtn">Dense mode</button><button id="expandAllBtn">Expand all</button><button id="collapseAllBtn">Collapse all</button><button id="helpBtn">Shortcuts</button></div></div>
      <div class="card hostNote"><div class="muted"><b>admin.example.test</b><br>LAN/VPN admin surface. Use the token to unlock data and writes.</div></div>
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
let token = (localStorage.getItem('duneAdminToken') || sessionStorage.getItem('duneAdminToken') || '').trim();
document.getElementById('token').value = token;
const validTabs = new Set(['overview', 'ops', 'security', 'runbook', 'characters', 'settings', 'mutations']);
let current = validTabs.has(location.hash.slice(1)) ? location.hash.slice(1) : (sessionStorage.getItem('duneAdminTab') || 'overview');
if (!validTabs.has(current)) current = 'overview';
let pendingAdminAccountId = '';
let resourceTimer = null;
let haggaMapTimer = null;
let loadSerial = 0;
let detailLoadSerial = 0;
let playerModalAccountId = '';
let playerModalTimer = null;
let playerModalInFlight = false;
let playerModalRef = null;
let resourceRefreshInFlight = false;
let haggaMapRefreshInFlight = false;
let haggaMapAutoRefresh = sessionStorage.getItem('duneAdminHaggaMapAutoRefresh') !== 'off';
let haggaMapLastGoodHtml = '';
let autoRefresh = sessionStorage.getItem('duneAdminAutoRefresh') !== 'off';
const resourceHistory = [];
let adminReferenceCache = null;
let adminReferenceCacheAt = 0;
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
  if (token) opts.headers['X-Admin-Token'] = token;
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
  return `<div class="barRow"><div title="${esc(label)}">${esc(label)}</div><div class="barTrack"><div class="barFill ${tone}" style="width:${pct.toFixed(1)}%"></div></div><div class="muted">${esc(detail || pct.toFixed(0) + '%')}</div></div>`;
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
  const legend = segments.map(s => `<div class="legendRow"><span class="swatch" style="background:${esc(s.color)}"></span><span>${esc(s.label)}</span><span class="muted">${esc(s.value)}</span></div>`).join('');
  return `<div class="vizCard"><h3>${esc(label)}</h3><div class="donutWrap"><svg class="donut" viewBox="0 0 36 36">${circles}<text x="18" y="18">${esc(total)}</text></svg><div class="legend">${legend}</div></div></div>`;
}
function spark(values){
  const vals = (values || []).map(v => Number(v || 0));
  const max = Math.max(...vals, 1);
  return `<div class="spark">${vals.map(v => `<span style="height:${Math.max(4, (v / max) * 100).toFixed(1)}%"></span>`).join('')}</div>`;
}
function historySpark(values){
  const vals = (values || []).map(v => Number(v || 0));
  const max = Math.max(...vals, 1);
  return `<div class="spark compact">${vals.map(v => `<span style="height:${Math.max(4, (v / max) * 100).toFixed(1)}%"></span>`).join('')}</div>`;
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
function characterOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">No characters found</option>';
  return '<option value="">Select character</option>' + vals.map(r => {
    const label = `${r.character_name || 'unnamed'} | account ${r.account_id} | ${r.online_status || 'unknown'}`;
    return `<option value="${esc(r.account_id)}" data-name="${esc(r.character_name || '')}" data-controller="${esc(r.player_controller_id || '')}">${esc(label)}</option>`;
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
function gmCommandOptions(commands, scripts){
  const commandOptions = (commands || []).map(r => `<option value="${esc(r.name)}">${esc(r.name)} | ${esc(r.kind)}</option>`).join('');
  const scriptOptions = (scripts || []).map(r => `<option value="CheatScript ${esc(r.name)}">CheatScript ${esc(r.name)}</option>`).join('');
  return commandOptions + scriptOptions;
}
function gmRouteOptions(routes){
  const vals = (routes || []).filter(r => r.exchange === 'rpc');
  if (!vals.length) return '<option value="Survival_11">Survival_11</option>';
  return vals.map(r => `<option value="${esc(r.routingKey)}">${esc(r.map || r.routingKey)} | ${esc(r.routingKey)} | ${r.alive ? 'alive' : 'not alive'}</option>`).join('');
}
function gmPresetButtons(presets){
  const vals = presets || [];
  if (!vals.length) return '';
  return `<div class="toolbar">${vals.map(p => `<button type="button" class="gmPresetBtn" data-command="${esc(p.command)}" data-args="${esc(p.args || '')}" title="${esc(p.risk || '')}">${esc(p.label)}</button>`).join('')}</div>`;
}
function gmCommandPanel(gm, characters){
  const routeRows = (gm.routeCandidates || []).map(r => ({
    exchange: r.exchange,
    routing_key: r.routingKey,
    map: r.map,
    ready: r.ready,
    alive: r.alive,
    notes: r.notes,
  }));
  const commandRows = (gm.commands || []).map(r => ({command: r.name, kind: r.kind, notes: r.notes}));
  const scriptRows = (gm.cheatScripts || []).map(r => ({script: r.name, command_count: (r.commands || []).length, commands: (r.commands || []).join(' | ')}));
  const chatRows = (gm.chatCommands || []).map(r => ({command: r.command, tier: r.tier, notes: r.notes}));
  return `<div class="panelBand dangerZone"><div class="sectionHeader"><h2>Native GM / Cheat Console</h2><div class="toolbar"><span class="pill ${gm.enabled ? 'ok' : 'warn'}">gate ${gm.enabled ? 'enabled' : 'disabled'}</span><span class="pill ${gm.payloadVerified ? 'ok' : 'bad'}">route ${gm.payloadVerified ? 'verified' : 'blocked'}</span><button id="refreshGmRefBtn">Refresh commands</button></div></div><p class="dangerText">${esc(gm.reason || 'Execution is blocked until the command route is verified.')}</p>${gmPresetButtons(gm.panelPresets)}<div class="grid"><label>Map RPC route<select id="gmRoute">${gmRouteOptions(gm.routeCandidates)}</select></label><label>Target player<select id="gmTarget">${characterOptions(characters)}</select></label><label>Command<select id="gmCommand">${gmCommandOptions(gm.commands, gm.cheatScripts)}</select></label><label>Arguments<input id="gmArgs" placeholder="template/count, player, map, or coordinates"></label></div><label>Confirmation<input id="gmConfirm" placeholder="RUN GM COMMAND"></label><p><button id="gmPreviewBtn" class="primary">Preview payload</button> <button id="gmExecuteBtn" class="danger" disabled>Execute after route verification</button></p><pre id="gmResult"></pre><details open><summary>Discovered Allow-List</summary>${table(commandRows)}</details><details open><summary>In-Game &gm Commands</summary>${table(chatRows)}</details><details><summary>Cheat Scripts</summary>${table(scriptRows)}</details><details><summary>RabbitMQ Route Candidates</summary>${table(routeRows)}</details></div>`;
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
function haggaBasinMapPanel(data){
  const players = data?.players || [];
  const bounds = data?.bounds || {};
  const calibration = data?.calibration || {};
  const width = 1000;
  const height = 1000;
  const pad = 0;
  const mapExtent = 100000;
  const minX = Number.isFinite(Number(calibration.minX)) ? Number(calibration.minX) : -407000;
  const maxX = Number.isFinite(Number(calibration.maxX)) ? Number(calibration.maxX) : 407000;
  const minY = Number.isFinite(Number(calibration.minY)) ? Number(calibration.minY) : -403500;
  const maxY = Number.isFinite(Number(calibration.maxY)) ? Number(calibration.maxY) : 403500;
  const invertY = calibration.invertY !== false;
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const mapX = x => clamp(((Number(x) - minX) / spanX) * mapExtent, 0, mapExtent);
  const mapY = y => {
    const normalized = ((Number(y) - minY) / spanY) * mapExtent;
    return clamp(invertY ? mapExtent - normalized : normalized, 0, mapExtent);
  };
  const px = x => pad + (mapX(x) / mapExtent) * (width - pad * 2);
  const py = y => pad + (mapY(y) / mapExtent) * (height - pad * 2);
  const grid = [1,2,3,4].map(i => {
    const gx = (i / 5) * width;
    const gy = (i / 5) * height;
    return `<line class="gridLine" x1="${gx}" y1="${pad}" x2="${gx}" y2="${height - pad}"></line><line class="gridLine" x1="${pad}" y1="${gy}" x2="${width - pad}" y2="${gy}"></line>`;
  }).join('');
  const markers = players.map((p, index) => {
    const x = px(p.x);
    const y = py(p.y);
    const rx = p.return_map === 'HaggaBasin' && Number.isFinite(Number(p.return_x)) ? px(p.return_x) : null;
    const ry = p.return_map === 'HaggaBasin' && Number.isFinite(Number(p.return_y)) ? py(p.return_y) : null;
    const hasReturnPoint = rx !== null && ry !== null && Math.hypot(rx - x, ry - y) > 8;
    const name = p.character_name || `Player ${index + 1}`;
    const labelX = clamp(x + 14, 8, width - 190);
    const labelY = clamp(y - 12, 22, height - 24);
    const title = `${name} | pawn x ${Number(p.x).toFixed(0)}, y ${Number(p.y).toFixed(0)}, z ${Number(p.z || 0).toFixed(0)}${hasReturnPoint ? ` | return x ${Number(p.return_x).toFixed(0)}, y ${Number(p.return_y).toFixed(0)}, z ${Number(p.return_z || 0).toFixed(0)}` : ''}`;
    const returnMarker = hasReturnPoint ? `<line class="uncertainLine" x1="${x.toFixed(1)}" y1="${y.toFixed(1)}" x2="${rx.toFixed(1)}" y2="${ry.toFixed(1)}"></line><circle class="returnDot" cx="${rx.toFixed(1)}" cy="${ry.toFixed(1)}" r="7"><title>${esc(name)} return-info position</title></circle>` : '';
    return `<g class="playerMarker" tabindex="0" role="button" data-account-id="${esc(p.account_id || '')}" aria-label="${esc(title)}"><title>${esc(title)}</title>${returnMarker}<circle class="playerDot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="8"></circle><text class="playerLabel" x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}">${esc(name)}</text><text class="coordLabel" x="${labelX.toFixed(1)}" y="${(labelY + 16).toFixed(1)}">${esc(Math.round(Number(p.x || 0)))}, ${esc(Math.round(Number(p.y || 0)))}</text></g>`;
  }).join('');
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
  const generatedAt = data?.generatedAt ? new Date(data.generatedAt).toLocaleTimeString() : '';
  return `<div class="panelBand"><div class="sectionHeader"><h2>Hagga Basin Player Map</h2><div class="toolbar"><span id="haggaMapCount" class="pill ${players.length ? 'ok' : ''}">${esc(players.length)} plotted</span><span id="haggaMapUpdated" class="pill">updated ${esc(generatedAt)}</span><span id="haggaMapHealth" class="pill warn">best-effort DB position</span><button id="toggleHaggaMapRefreshBtn" aria-pressed="${haggaMapAutoRefresh ? 'true' : 'false'}">${haggaMapAutoRefresh ? 'Pause map' : 'Resume map'}</button><button id="refreshHaggaMapBtn">Refresh map</button></div></div><div id="haggaMapSrStatus" class="srOnly" aria-live="polite">${esc(players.length)} Hagga Basin players plotted.</div><div class="haggaMap"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Hagga Basin online player coordinate map"><image class="mapImage" href="/static/hagga-basin.webp" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet"></image><rect class="mapShade" x="0" y="0" width="${width}" height="${height}"></rect>${grid}<text x="12" y="24" fill="var(--muted)" font-size="12">NW</text><text x="${width - 30}" y="${height - 12}" fill="var(--muted)" font-size="12">SE</text>${markers}${empty}</svg></div><div class="haggaMapStatus"><span class="pill ok">green: pawn/controller transform</span><span class="pill warn">yellow: travel return transform when different</span><span class="pill">background: Community Wiki Hagga Basin map</span><span class="pill">calibration X ${esc(Math.round(minX))}..${esc(Math.round(maxX))}, Y ${esc(Math.round(minY))}..${esc(Math.round(maxY))}${invertY ? ', inverted Y' : ''}</span></div><details open><summary>Coordinates</summary><div class="coordTable">${table(rows)}</div></details></div>`;
}
function wireHaggaMapControls(container){
  container.querySelectorAll('.playerMarker[data-account-id]').forEach(marker => {
    marker.addEventListener('click', () => openPlayerModal(marker.dataset.accountId));
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
function characterRosterTable(rows){
  if (!rows || !rows.length) return '<div class="muted">No characters in this group.</div>';
  return `<div class="tableWrap"><table class="dataDense"><thead><tr><th>Character</th><th>Status</th><th>Life</th><th>Map</th><th>Account</th><th>Last Login</th></tr></thead><tbody>${rows.map(r=>`<tr data-id="${esc(r.account_id ?? '')}"><td>${esc(r.character_name || 'unnamed')}<br><span class="muted">${esc(r.platform_name || '')} ${esc(r.platform_id || '')}</span></td><td>${esc(r.online_status || '')}</td><td>${esc(r.life_state || '')}</td><td>${esc(r.map || r.server_id || '')}</td><td>${esc(r.account_id || '')}</td><td>${esc(r.last_login_time || '')}</td></tr>`).join('')}</tbody></table></div>`;
}
function characterRosterPanel(roster){
  const counts = roster.counts || {};
  const chart = donut('Player State', [
    {label:'Online', value:Number(counts.online || 0), color:'var(--ok)'},
    {label:'Offline', value:Number(counts.offline || 0), color:'var(--muted)'}
  ]);
  return `<div class="rosterPanel"><div class="sectionHeader"><h2>Players</h2><div class="toolbar"><input class="filterInput rosterFilter" placeholder="Filter players, IDs, maps"></div></div><div class="metricGrid">${metric('Online Players', counts.online ?? 0, Number(counts.online || 0) ? 'ok' : '')}${metric('Offline Players', counts.offline ?? 0)}${metric('Total Characters', counts.total ?? 0)}</div><div class="vizGrid">${chart}<div class="vizCard"><h3>Roster Ratio</h3><div class="barList">${bar('Online', counts.online || 0, counts.total || 1)}${bar('Offline', counts.offline || 0, counts.total || 1)}</div></div></div><div class="twoCol"><div class="panelBand"><div class="splitHeader"><h2>Online Players</h2><span class="pill ok">${esc(counts.online ?? 0)} online</span></div>${characterRosterTable(roster.online)}</div><div class="panelBand"><div class="splitHeader"><h2>Offline Players</h2><span class="pill">${esc(counts.offline ?? 0)} offline</span></div>${characterRosterTable(roster.offline)}</div></div></div>`;
}
function probeTable(rows){
  if (!rows || !rows.length) return '<div class="muted">No probes.</div>';
  return `<div class="tableWrap"><table><thead><tr><th>Name</th><th>Status</th><th>Target</th><th>Latency</th><th>HTTP</th><th>Error</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${healthCell(r.ok || [401,403,404].includes(r.httpStatus), r.ok ? 'OK' : 'reachable', 'down')}</td><td>${esc(r.target)}</td><td>${esc(r.latencyMs)}ms</td><td>${esc(r.httpStatus ?? '')}</td><td>${esc(r.error ?? '')}</td></tr>`).join('')}</tbody></table></div>`;
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
  return `<div class="card"><h2>Restart Announcement</h2><p class="muted">Schedules repeated maintenance messages through <code>${esc(state.command || '')}</code>. The scheduler is live; in-game delivery depends on that command being implemented and executable.</p><div class="grid"><label>Restart time<select id="announceDelay">${delayOptions}</select></label><label>Repeat every<select id="announceRepeat"><option value="0">Do not repeat</option><option value="30">30 sec</option><option value="60" selected>60 sec</option><option value="300">5 min</option><option value="600">10 min</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option></select></label></div><label>Message<textarea id="announceMessage" rows="3" style="min-height:82px">Server restart soon. Please get to a safe place.</textarea></label><p><button id="scheduleAnnouncementBtn" class="primary">Schedule announcement</button> <button id="cancelAnnouncementBtn" class="danger">Cancel active announcement</button></p><h3>Current</h3>${jobSummary}<h3>Last Delivery</h3>${delivery}</div>`;
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
  return `<div class="card"><h2>Scheduled Restart / Shutdown</h2><p class="muted">Schedules a component restart or shutdown through <code>${esc(state.command || '')}</code>. Executed jobs take a maintenance backup first by default.</p><div class="grid"><label>Target<select id="restartTarget">${targetOptions}</select></label><label>Action<select id="restartAction"><option value="restart" selected>Restart target</option><option value="shutdown">Shutdown target</option></select></label><label>Run after<select id="restartDelay">${delayOptions}</select></label><label>Repeat notice every<select id="restartRepeat"><option value="0">Do not repeat</option><option value="30">30 sec</option><option value="60" selected>60 sec</option><option value="300">5 min</option><option value="600">10 min</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option></select></label><label>Execution<select id="restartExecute"><option value="false" selected>Dry-run schedule</option><option value="true">Execute hook</option></select></label></div><label><input id="restartBackup" type="checkbox" checked style="width:auto"> Backup before execution</label><label><input id="restartAnnounce" type="checkbox" checked style="width:auto"> Also schedule announcement</label><label>Message<textarea id="restartMessage" rows="3" style="min-height:82px">Server maintenance soon. Please get to a safe place.</textarea></label><p><button id="scheduleRestartBtn" class="primary">Schedule maintenance</button> <button id="cancelRestartBtn" class="danger">Cancel active job</button></p><h3>Current</h3>${jobSummary}<h3>Last Execution</h3>${execution}</div>`;
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
  return Object.entries(groups).map(([group, rows]) => `<div class="card"><h2>${esc(group)}</h2><div class="grid">${rows.map(([key, meta]) => {
    const type = meta.secret ? 'password' : 'text';
    const restart = meta.restart ? '<span class="muted"> restart/recreate applies</span>' : '';
    const configuredText = meta.secret && configured[key] ? ' configured, leave blank to keep' : '';
    return `<label>${esc(key)}${restart}<input id="env_${esc(key)}" data-secret="${meta.secret ? 'true' : 'false'}" type="${type}" value="${esc(values[key] || '')}" placeholder="${esc(configuredText.trim())}"><span class="muted">${esc(meta.why || '')}${esc(configuredText)}</span></label>`;
  }).join('')}</div></div>`).join('');
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
    const tabMap = {'1':'overview','2':'ops','3':'security','4':'runbook','5':'characters','6':'settings','7':'mutations'};
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
  document.getElementById('statusSummary').innerHTML = [
    statusPill('admin token configured', data.adminTokenConfigured),
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
  if (haggaMapTimer) {
    clearInterval(haggaMapTimer);
    haggaMapTimer = null;
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
  } catch (e) {
    if (serial !== loadSerial) return;
    view.innerHTML = `<div class="card"><h2>Admin Token Required</h2><p class="dangerText">${esc(e.message)}</p><p class="muted">Paste the admin token in the header and press <b>Use token</b>. The panel is reachable, but server data and write controls stay locked until the token is present.</p></div><div class="metricGrid">${metric('Endpoint', location.host)}${metric('Item Grants', 'enabled', 'ok')}${metric('Mutations', 'off', 'ok')}</div>`;
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
  const state = health;
  const summary = health.summary || {};
  const players = (state.farmState || []).reduce((sum, r) => sum + Number(r.connected_players || 0), 0);
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Overview</h2><div class="toolbar"><button data-jump="characters">Players</button><button data-jump="ops">Operations</button><button data-jump="mutations" class="primary">Admin Actions</button></div></div><div class="metricGrid">${metric('Ready Servers', `${summary.readyAlive ?? 0}/${summary.expectedPartitions ?? 0}`, summary.readyAlive === summary.expectedPartitions ? 'ok' : 'dangerText')}${metric('Online Maps', `${summary.onlineMaps ?? 0}/${summary.totalMaps ?? 0}`, summary.onlineMaps === summary.totalMaps ? 'ok' : 'dangerText')}${metric('Active IDs', `${summary.activeServers ?? 0}/${summary.expectedPartitions ?? 0}`)}${metric('Reported Players', players)}</div>${healthViz(health)}<div id="haggaBasinMap"><div class="panelBand"><h2>Hagga Basin Player Map</h2><div class="muted">Loading player positions...</div></div></div><div id="overviewRoster">${characterRosterPanel(roster)}</div><div id="detail"></div><div id="resources" class="panelBand"><h2>Resources</h2><div class="muted">Loading resource stats...</div></div>${actionGrid([{tab:'characters',label:'Player search and detail'},{tab:'ops',label:'Service controls and map health'},{tab:'security',label:'Security and audit'},{tab:'settings',label:'Server settings'}])}<div class="twoCol"><div class="panelBand"><h2>Map Health</h2>${mapTiles(health.mapStatus)}<details><summary>Map Table</summary>${mapStatusTable(health.mapStatus)}</details></div><div class="panelBand"><h2>Health Verdict</h2>${checks(health.verdicts)}</div></div><div class="panelBand" data-network-panel><h2>Network and Upstream</h2><div class="muted">Loading network probes...</div></div></div>`;
  document.querySelectorAll('#overviewRoster tbody tr').forEach(row => row.onclick = () => pickCharacter(row));
  makeRowsKeyboardFriendly(view);
  wireResourceControls(view);
  bindRosterFilters(view);
  bindResourceFilters(view);
  refreshHaggaMap().catch(e => {
    const container = document.getElementById('haggaBasinMap');
    if (container) container.innerHTML = `<h2>Hagga Basin Player Map</h2><div class="dangerText">${esc(e.message)}</div>`;
  });
  refreshResources().catch(e => {
    const container = document.getElementById('resources');
    if (container) container.innerHTML = `<div class="panelBand"><h2>Resources</h2><div class="dangerText">${esc(e.message)}</div></div>`;
  });
  refreshNetwork().catch(e => {
    document.querySelectorAll('[data-network-panel]').forEach(container => container.innerHTML = `<h2>Network and Upstream</h2><div class="dangerText">${esc(e.message)}</div>`);
  });
  resourceTimer = setInterval(() => {
    if (autoRefresh && current === 'overview') refreshResources().catch(() => {});
  }, 5000);
  haggaMapTimer = setInterval(() => {
    if (haggaMapAutoRefresh && current === 'overview') refreshHaggaMap().catch(() => {});
  }, 2000);
}
async function ops(serial=loadSerial){
  const [health, opt, announcement, restart] = await Promise.all([
    api('/api/ops/health'),
    api('/api/ops/optimization'),
    api('/api/ops/announcement'),
    api('/api/ops/restart')
  ]);
  if (serial !== loadSerial) return;
  const pc = health.playerCounts || {};
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Operations</h2><div class="toolbar"><button data-jump="overview">Overview</button><button data-jump="characters">Players</button><button data-jump="runbook">Runbook</button><button data-jump="settings">Settings</button></div></div><div class="metricGrid">${metric('Connected Players', pc.connected_players_reported ?? 0)}${metric('Online Controllers', pc.online_controller_ids ?? 0)}${metric('Recent Online State', pc.online_or_recently_disconnected ?? 0)}${metric('Grace Entries', pc.grace_period_entries ?? 0)}</div>${healthViz(health)}<div id="resources" class="panelBand"><h2>Resources</h2><div class="muted">Loading resource stats...</div></div><div class="twoCol">${restartPanel(restart)}${announcementPanel(announcement)}</div><div class="twoCol"><div class="panelBand"><h2>Health Verdict</h2>${checks(health.verdicts)}</div><div class="panelBand" data-network-panel><h2>Local and Upstream Network</h2><div class="muted">Loading network probes...</div></div></div><div class="panelBand"><h2>Map Online/Offline</h2>${mapTiles(health.mapStatus)}<details><summary>Map Table</summary>${mapStatusTable(health.mapStatus)}</details></div><details class="panelBand"><summary>Raw Farm State</summary>${table(health.farmState)}</details><details class="panelBand"><summary>Partitions</summary>${table(health.partitions)}</details>${signalList(opt)}</div>`;
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
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Security</h2><div class="toolbar"><span class="pill ${failed ? 'warn' : 'ok'}">${failed ? failed + ' checks need attention' : 'checks OK'}</span><button data-jump="settings">Settings</button><button data-jump="mutations">Backup</button></div></div><div class="twoCol"><div class="panelBand"><h2>Security Checks</h2>${checks(audit.checks)}</div><div class="panelBand"><h2>Recent Audit Events</h2>${table(events.events)}</div></div><div class="panelBand"><h2>Operating Notes</h2><ul>${audit.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></div><details class="panelBand"><summary>Editable Env Keys</summary><div class="toolbar">${audit.safeEnvKeys.map(k => `<span class="pill">${esc(k)}</span>`).join('')}</div></details><details class="panelBand"><summary>Editable Config Files</summary><div class="toolbar">${audit.allowedConfigFiles.map(k => `<span class="pill">${esc(k)}</span>`).join('')}</div></details></div>`;
}
async function runbook(serial=loadSerial){
  const data = await api('/api/ops/runbook');
  if (serial !== loadSerial) return;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Runbook</h2><div class="toolbar"><span class="pill">copy/paste commands</span><button data-jump="ops">Ops</button><button data-jump="settings">Settings</button></div></div>${actionGrid([{tab:'overview',label:'Overview'},{tab:'mutations',label:'Create DB backup',className:'primary'},{tab:'security',label:'Audit'}])}<div class="panelBand"><p class="muted">${esc(data.why)}</p>${table(data.commands)}</div></div>`;
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
  document.getElementById('playerModalBody').innerHTML = `<datalist id="itemTemplateList">${templateDatalist(ref)}</datalist><div class="playerModalGrid"><div class="pageStack"><div class="panelBand"><h2>${esc(p.character_name || 'Character')}</h2><div class="metricGrid">${metric('Status', p.online_status || '')}${metric('Life', p.life_state || '')}${metric('Map', map.label || map.map || p.server_id || '')}${metric('Items', items.length)}</div><div class="grid"><div><b>Account</b><br>${esc(p.account_id)}</div><div><b>Funcom</b><br>${esc(account.funcom_id || '')}</div><div><b>Platform</b><br>${esc(account.platform_name || '')} ${esc(account.platform_id || '')}</div><div><b>Last Login</b><br>${esc(p.last_login_time || '')}</div><div><b>Controller</b><br>${esc(p.player_controller_id)}</div><div><b>Pawn</b><br>${esc(p.player_pawn_id)}</div></div><p><button id="modalOpenAdminActionsBtn" class="primary">Open Admin Actions</button></p></div><div class="panelBand"><h2>Location and Runtime</h2>${table(locationRows)}<details open><summary>Actor Locations</summary>${table(d.actorLocations || [])}</details><details><summary>Travel Return</summary>${table(d.travelReturn || [])}</details><details><summary>Map Context</summary>${table(d.mapContext || [])}</details><details><summary>Respawn Locations</summary>${table(d.respawnLocations || [])}</details><details><summary>Runtime Source</summary><pre>${esc(JSON.stringify(d.realtime || {}, null, 2))}</pre></details></div><div class="panelBand"><h2>Currency and XP</h2><details open><summary>Currency</summary>${table(d.currency || [])}</details><details><summary>Specialization</summary>${table(d.specialization || [])}</details><details><summary>Faction</summary>${table(d.faction || [])}</details><details><summary>Reputation</summary>${table(d.reputation || [])}</details></div></div><div class="pageStack"><div class="panelBand"><div class="splitHeader"><h2>Inventory</h2><span class="pill">${esc(items.length)} items</span></div><div class="playerInventoryTools"><label>Inventory<select id="modalInventoryFilter"><option value="">All inventories</option>${inventoryOptions(inventories)}</select></label><label>Item Search<input id="modalItemFilter" placeholder="Template, item ID, inventory"></label></div><h3>Inventory Summary</h3>${table(inventorySummary)}<h3>Items</h3><div id="modalInventoryItems">${table(items)}</div></div><div class="panelBand"><h2>Quick Currency and XP</h2><div class="grid"><label>Currency<select id="detailCurId">${currencyBalanceOptions(d.currency, ref.currencyIds)}</select></label><label>Amount<input id="detailCurAmount" value="1000"></label><label>Mode<select id="detailCurMode"><option>add</option><option>set</option></select></label></div><p><button id="detailCurrencyBtn" class="primary">Apply currency</button></p><div class="grid"><label>Track<select id="detailTrack">${specializationOptions(d.specialization, ref.specializationTrackTypes)}</select></label><label>XP amount<input id="detailXpAmount" value="1000"></label><label>Level for set/new track<input id="detailXpLevel" value="${esc(firstTrack.level ?? 0)}"></label><label>Mode<select id="detailXpMode"><option>add</option><option>set</option></select></label></div><p><button id="detailXpBtn" class="primary">Apply XP</button></p></div><div class="panelBand"><h2>Quick Item Action</h2><div class="grid"><label>Owned inventory<select id="detailGrantInventory"><option value="">All owned inventories</option>${inventoryOptions(inventories)}</select></label><label>Owned item<select id="detailItemSelect">${inventoryItemOptions(items)}</select></label><label>Template ID<input id="detailGrantTemplate" list="itemTemplateList" placeholder="SMG_Unique_LargeMag_06"></label><label>Stack size<input id="detailGrantStack" value="1"></label><label>Delete count<input id="detailDeleteCount" placeholder="blank/all"></label></div><div id="detailSelectedItem" class="muted">Select an owned item to inspect stack and template details.</div><p><button id="detailDryRunBtn" class="primary">Dry run item</button> <button id="detailGrantBtn" class="danger">Grant item</button> <button id="detailSetStackBtn" class="primary">Set selected stack</button> <button id="detailDeleteItemBtn" class="danger">Delete selected item/count</button></p><pre id="detailGrantResult"></pre></div><details class="panelBand"><summary>Raw Detail</summary><pre>${esc(JSON.stringify(d, null, 2))}</pre></details></div></div>`;
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
  const [env, transfer, onlineState, configs] = await Promise.all([
    api('/api/settings/env'),
    api('/api/settings/director-transfer'),
    api('/api/settings/player-online-state'),
    api('/api/settings/configs')
  ]);
  if (serial !== loadSerial) return;
  view.innerHTML = `<div class="pageStack"><div class="sectionHeader"><h2>Settings</h2><div class="toolbar"><button data-jump="security">Security</button><button data-jump="ops">Ops</button><button id="saveEnvBtn" class="primary">Save env settings</button></div></div><div class="panelBand"><p class="muted">These write <code>.env</code>, <code>config/director.ini</code>, or <code>config/UserGame.ini</code> with a backup under <code>backups/admin-panel</code>. Most service settings need the affected containers recreated before running processes pick them up.</p></div>${actionGrid([{tab:'ops',label:'Check live state'},{tab:'mutations',label:'Create backup',className:'primary'},{tab:'characters',label:'Inspect players'}])}${envEditor(env)}<div class="twoCol">${playerOnlineStateEditor(onlineState)}${directorTransferEditor(transfer)}</div><div class="panelBand"><h2>Config Files</h2><select id="cfg">${Object.keys(configs).map(k=>`<option>${esc(k)}</option>`).join('')}</select><textarea id="cfgText"></textarea><p><button id="saveCfgBtn" class="primary">Save config with backup</button></p></div></div>`;
  window.configs = configs; selectCfg();
  document.getElementById('cfg').addEventListener('change', selectCfg);
  document.getElementById('saveEnvBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', saveEnv));
  document.getElementById('savePlayerOnlineStateBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', savePlayerOnlineState));
  document.getElementById('saveDirectorTransferBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', saveDirectorTransfer));
  document.getElementById('saveCfgBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', saveCfg));
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
async function mutations(serial=loadSerial){
  const [ref, characterRows, gm] = await Promise.all([
    adminReference(),
    api('/api/characters?q='),
    api('/api/admin/gm/reference')
  ]);
  if (serial !== loadSerial) return;
  const referenceErrors = ref.errors && Object.keys(ref.errors).length ? `<div class="card"><h2>Reference Errors</h2><pre>${esc(JSON.stringify(ref.errors, null, 2))}</pre></div>` : '';
  view.innerHTML = `<div class="pageStack">${referenceErrors}<div class="sectionHeader"><h2>Admin Actions</h2><div class="toolbar"><button data-jump="characters">Players</button><button data-jump="settings">Settings</button><button data-jump="security">Audit</button></div></div>${actionGrid([{tab:'characters',label:'Player lookup'},{tab:'settings',label:'Mutation settings'},{tab:'runbook',label:'Runbook'}])}<div class="panelBand"><h2>Backup First</h2><p class="muted">Creates a Postgres custom-format dump under <code>backups/admin-panel</code>.</p><button id="backupBtn" class="primary">Create DB backup</button><pre id="backupResult"></pre></div><div class="panelBand"><h2>Target Player</h2><div class="grid"><label>Character<select id="adminCharacterSelect">${characterOptions(characterRows)}</select></label><label>Player controller ID<input id="pcid"></label><label>Account ID<input id="grantAccount" placeholder="auto-select player inventory"></label><label>Character name<input id="grantCharacter" placeholder="auto-select by name"></label></div></div>${gmCommandPanel(gm, characterRows)}<div class="twoCol"><div class="panelBand"><h2>Currency and XP</h2><p class="dangerText">Writes require <code>DUNE_ADMIN_MUTATIONS_ENABLED=true</code> and a valid admin token.</p><div class="grid"><label>Currency ID<select id="curid">${options(ref.currencyIds, 'currency_id', '1')}</select></label><label>Amount<input id="amount" value="1000"></label><label>Mode<select id="mode"><option>add</option><option>set</option></select></label></div><p><button id="currencyBtn" class="primary">Apply currency</button></p><div class="grid"><label>Player/controller ID<input id="xpid"></label><label>Track type<select id="track">${options(ref.specializationTrackTypes, 'track_type')}</select></label><label>XP amount<input id="xpamount" value="1000"></label><label>Level for set/new track<input id="xplevel" value="0"></label><label>Mode<select id="xpmode"><option>add</option><option>set</option></select></label></div><p><button id="xpBtn" class="primary">Apply XP</button></p></div><div class="panelBand dangerZone"><h2>Specialization Keystones</h2><div class="grid"><label>Player/controller ID<input id="keyPlayer"></label><label>Keystone<select id="keystone">${options(ref.keystones, 'name')}</select></label></div><p><button id="purchaseKeystoneBtn" class="primary">Purchase keystone</button> <button id="resetKeystonesBtn" class="danger">Reset all keystones</button></p><pre id="keystoneResult"></pre></div></div><div class="twoCol"><div class="panelBand"><h2>Item Grants</h2><p class="dangerText">Use exact server template IDs. Dry run first when using IDs not observed locally.</p><div class="grid"><label>Known inventory<select id="grantInventorySelect">${inventoryOptions(ref.recentInventories)}</select></label><label>Inventory ID<input id="grantInventory" placeholder="explicit inventory"></label><label class="hidden">Character<select id="grantCharacterSelect">${characterOptions(characterRows)}</select></label><label>Inventory type<select id="grantInventoryType">${inventoryTypeOptions(ref.inventoryTypes)}</select></label><label>Template ID<input id="grantTemplate" list="itemTemplateList" placeholder="SMG_Unique_LargeMag_06"></label><label>Stack size<input id="grantStack" value="1"></label><label>Quality level<input id="grantQuality" value="0"></label><label>Position index<input id="grantPosition" placeholder="auto"></label></div><label>Stats JSON<textarea id="grantStats">{}</textarea></label><p><button id="dryRunItemBtn" class="primary">Dry run</button> <button id="grantItemBtn" class="danger">Grant item</button></p><pre id="grantResult"></pre></div><div class="panelBand dangerZone"><h2>Item Maintenance</h2><div class="grid"><label class="hidden">Character<select id="itemCharacterSelect">${characterOptions(characterRows)}</select></label><label>Owned item<select id="itemEditSelect"><option value="">Select a character first</option></select></label><label>Item ID<input id="itemEditId"></label><label>New stack size<input id="itemEditStack" value="1"></label><label>Delete count<input id="itemDeleteCount" placeholder="blank/all"></label></div><p><button id="setItemStackBtn" class="primary">Set stack</button> <button id="deleteItemBtn" class="danger">Delete item/count</button></p><pre id="itemEditResult"></pre></div></div><datalist id="itemTemplateList">${templateDatalist(ref)}</datalist><details class="panelBand"><summary>Known Item Templates</summary>${table(ref.knownItemTemplates)}</details><details class="panelBand"><summary>Observed Item Templates</summary>${table(ref.observedItemTemplates)}</details><details class="panelBand"><summary>Recent Inventories</summary>${table(ref.recentInventories)}</details><details class="panelBand"><summary>Inventory Types</summary>${table(ref.inventoryTypes)}</details></div>`;
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
    if (document.getElementById('grantCharacter')) document.getElementById('grantCharacter').value = option.dataset.name || '';
    if (document.getElementById('pcid')) document.getElementById('pcid').value = option.dataset.controller || '';
    if (document.getElementById('xpid')) document.getElementById('xpid').value = option.dataset.controller || '';
    if (document.getElementById('keyPlayer')) document.getElementById('keyPlayer').value = option.dataset.controller || '';
    if (document.getElementById('gmTarget')) document.getElementById('gmTarget').value = option.value;
    await loadCharacterAdminDetails(option.value, serial);
    if (serial !== detailLoadSerial) return;
  };
  document.getElementById('adminCharacterSelect').addEventListener('change', e => fillCharacter(e.target).catch(err => reportClientError(err, 'Load player admin detail')));
  document.getElementById('grantCharacterSelect').addEventListener('change', e => fillCharacter(e.target).catch(err => reportClientError(err, 'Load player admin detail')));
  document.getElementById('itemCharacterSelect').addEventListener('change', e => fillCharacter(e.target).catch(err => reportClientError(err, 'Load player admin detail')));
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
  document.getElementById('currencyBtn').addEventListener('click', e => runAction(e.currentTarget, 'Applying...', currency));
  document.getElementById('xpBtn').addEventListener('click', e => runAction(e.currentTarget, 'Applying...', xp));
  document.getElementById('purchaseKeystoneBtn').addEventListener('click', e => runAction(e.currentTarget, 'Purchasing...', purchaseKeystone));
  document.getElementById('resetKeystonesBtn').addEventListener('click', e => runAction(e.currentTarget, 'Resetting...', resetKeystones));
  document.getElementById('dryRunItemBtn').addEventListener('click', e => runAction(e.currentTarget, 'Checking...', () => grantItem(true)));
  document.getElementById('grantItemBtn').addEventListener('click', e => runAction(e.currentTarget, 'Granting...', () => grantItem(false)));
  document.getElementById('setItemStackBtn').addEventListener('click', e => runAction(e.currentTarget, 'Saving...', setItemStack));
  document.getElementById('deleteItemBtn').addEventListener('click', e => runAction(e.currentTarget, 'Deleting...', deleteItem));
  document.getElementById('refreshGmRefBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Refreshing...', async () => {
    const gmRef = await api('/api/admin/gm/reference');
    document.getElementById('gmResult').textContent = JSON.stringify(gmRef, null, 2);
  }));
  document.querySelectorAll('.gmPresetBtn').forEach(btn => btn.addEventListener('click', () => applyGmPreset(btn)));
  document.getElementById('gmPreviewBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Previewing...', previewGmCommand));
  document.getElementById('gmExecuteBtn')?.addEventListener('click', e => runAction(e.currentTarget, 'Executing...', executeGmCommand));
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
function gmCommandBody(){
  const target = document.getElementById('gmTarget')?.selectedOptions?.[0];
  return {
    route: document.getElementById('gmRoute')?.value || '',
    target_player: target?.dataset.controller || target?.value || '',
    target_account_id: target?.value || '',
    target_character: target?.dataset.name || '',
    command: document.getElementById('gmCommand')?.value || '',
    args: document.getElementById('gmArgs')?.value || '',
    confirm: document.getElementById('gmConfirm')?.value || ''
  };
}
function gmSelectedTargetName(){
  const target = document.getElementById('gmTarget')?.selectedOptions?.[0];
  return target?.dataset.name || '';
}
function applyGmPreset(btn){
  const command = btn.dataset.command || '';
  const targetName = gmSelectedTargetName();
  const args = (btn.dataset.args || '').replaceAll('<player>', targetName || '<player>');
  const commandSelect = document.getElementById('gmCommand');
  if (commandSelect) commandSelect.value = command;
  const argsInput = document.getElementById('gmArgs');
  if (argsInput) argsInput.value = args;
}
async function previewGmCommand(){
  const result = await api('/api/admin/gm/preview', {method:'POST', body:JSON.stringify(gmCommandBody())});
  document.getElementById('gmResult').textContent = JSON.stringify(result, null, 2);
  notify('GM payload preview generated');
}
async function executeGmCommand(){
  if (!confirm('Run native GM command on the live server?')) return;
  const result = await api('/api/admin/gm/execute', {method:'POST', body:JSON.stringify(gmCommandBody())});
  document.getElementById('gmResult').textContent = JSON.stringify(result, null, 2);
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
window.addEventListener('error', e => reportClientError(e.error || e.message));
window.addEventListener('unhandledrejection', e => reportClientError(e.reason || e, 'Request failed'));
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
