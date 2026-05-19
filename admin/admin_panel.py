#!/usr/bin/env python3
import configparser
import hmac
import html
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
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
CONFIG_ROOT = ROOT / "config"
ENV_FILE = ROOT / ".env"
BACKUP_ROOT = ROOT / "backups" / "admin-panel"
AUDIT_LOG = BACKUP_ROOT / "audit.jsonl"
AUDIT_MAX_BYTES = int(os.environ.get("DUNE_ADMIN_AUDIT_MAX_BYTES", str(5 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS", "10"))
MAX_ITEM_STACK_SIZE = int(os.environ.get("DUNE_ADMIN_MAX_ITEM_STACK_SIZE", "1000000"))
AUDIT_EVENT_LIMIT = int(os.environ.get("DUNE_ADMIN_AUDIT_EVENT_LIMIT", "100"))
ADMIN_REFERENCE_LIMIT = int(os.environ.get("DUNE_ADMIN_REFERENCE_LIMIT", "200"))
CHARACTER_SEARCH_LIMIT = int(os.environ.get("DUNE_ADMIN_CHARACTER_SEARCH_LIMIT", "100"))
DATABASE = os.environ.get("DUNE_DATABASE", "dune_sb_1_4_0_0")
ADMIN_TOKEN = os.environ.get("DUNE_ADMIN_TOKEN", "")
MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_MUTATIONS_ENABLED", "false").lower() == "true"
ITEM_GRANTS_ENABLED = os.environ.get("DUNE_ADMIN_ITEM_GRANTS_ENABLED", "true").lower() == "true"
MAX_BODY_BYTES = int(os.environ.get("DUNE_ADMIN_MAX_BODY_BYTES", "65536"))
ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.environ.get("DUNE_ADMIN_ALLOWED_HOSTS", "127.0.0.1:18080,localhost:18080,admin.example.test").split(",")
    if host.strip()
}
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_FAILURE_LIMIT = 5
AUTH_FAILURES = {}
AUDIT_LOCK = threading.Lock()
CONFIRM_RESET_KEYSTONES = "RESET KEYSTONES"
CONFIRM_DELETE_ITEM = "DELETE ITEM"
CONFIRM_SET_STACK = "SET STACK"
ANNOUNCEMENT_STATE_FILE = BACKUP_ROOT / "announcements.json"
RESTART_STATE_FILE = BACKUP_ROOT / "restart-jobs.json"
ANNOUNCEMENT_LOCK = threading.Lock()
RESTART_LOCK = threading.Lock()
ANNOUNCEMENT_THREAD_STARTED = False
ANNOUNCEMENT_POLL_SECONDS = 5
ANNOUNCEMENT_MAX_MESSAGE_BYTES = int(os.environ.get("DUNE_ADMIN_ANNOUNCEMENT_MAX_MESSAGE_BYTES", "500"))
ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "10"))
ANNOUNCEMENT_COMMAND = os.environ.get("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh"))
RESTART_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DUNE_ADMIN_RESTART_COMMAND_TIMEOUT_SECONDS", "1800"))
RESTART_COMMAND = os.environ.get("DUNE_ADMIN_RESTART_COMMAND", str(ROOT / "scripts" / "restart-target.sh"))
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
RESTART_TARGETS = {
    "all": {"label": "All Components", "services": []},
    "core": {"label": "Core Services", "services": ["postgres", "admin-rmq", "game-rmq", "rmq-auth-shim", "text-router", "gateway", "director"]},
    "service-layer": {"label": "Service Layer", "services": ["rmq-auth-shim", "text-router", "gateway", "director"]},
    "game-all": {"label": "All Game Maps", "services": [
        "survival", "overmap", "arrakeen", "harko-village", "testing-hephaestus", "testing-carthag", "testing-waterfat",
        "deep-desert", "proces-verbal", "lostharvest-ecolab-a", "lostharvest-ecolab-b", "lostharvest-forgottenlab",
        "art-of-kanly", "dungeon-hephaestus", "dungeon-oldcarthag", "faction-outpost-atre", "faction-outpost-hark",
        "heighliner-dungeon", "ecolab-green-089", "ecolab-green-152", "ecolab-green-024", "ecolab-green-195",
        "ecolab-green-136", "overland-m-01", "overland-s-04", "overland-s-06", "bandit-fortress",
        "overland-s-07", "overland-s-08", "dungeon-thepit",
    ]},
    "survival": {"label": "Hagga Basin / Survival", "services": ["survival"]},
    "overmap": {"label": "Overland Map", "services": ["overmap"]},
    "arrakeen": {"label": "Arrakeen", "services": ["arrakeen"]},
    "harko-village": {"label": "Harko Village", "services": ["harko-village"]},
    "deep-desert": {"label": "Deep Desert", "services": ["deep-desert"]},
}

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
    "DUNE_ADMIN_MAX_BODY_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum accepted request body size."},
    "DUNE_ADMIN_AUDIT_MAX_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Audit log rotation threshold."},
    "DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Socket timeout to limit slow client abuse."},
    "DUNE_ADMIN_MAX_ITEM_STACK_SIZE": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum item stack mutation allowed through the panel."},
    "DUNE_ADMIN_AUDIT_EVENT_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Default number of audit events returned by the panel."},
    "DUNE_ADMIN_REFERENCE_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum reference rows returned by admin helper endpoints."},
    "DUNE_ADMIN_CHARACTER_SEARCH_LIMIT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum character search rows returned."},
    "DUNE_ADMIN_ALLOWED_HOSTS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Host header allowlist for the admin HTTP service."},
    "DUNE_ADMIN_ANNOUNCE_COMMAND": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Executable hook used by the restart-announcement scheduler to deliver in-game messages."},
    "DUNE_ADMIN_ANNOUNCEMENT_MAX_MESSAGE_BYTES": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Maximum UTF-8 size for a scheduled restart-announcement message."},
    "DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Timeout for each announcement delivery hook invocation."},
    "DUNE_ANNOUNCE_RMQ_URL": {"group": "Announcements", "secret": False, "restart": True, "why": "RabbitMQ management API URL used by the announcement hook."},
    "DUNE_ANNOUNCE_RMQ_USER": {"group": "Announcements", "secret": False, "restart": True, "why": "RabbitMQ management user used by the announcement hook."},
    "DUNE_ANNOUNCE_RMQ_PASSWORD": {"group": "Announcements", "secret": True, "restart": True, "why": "RabbitMQ management password used by the announcement hook."},
    "DUNE_ANNOUNCE_RMQ_EXCHANGE": {"group": "Announcements", "secret": False, "restart": True, "why": "RabbitMQ exchange used for server-command announcements."},
    "DUNE_ANNOUNCE_RMQ_ROUTING_KEYS": {"group": "Announcements", "secret": False, "restart": True, "why": "Comma-separated map RPC routing keys that receive announcements."},
    "DUNE_ANNOUNCE_COMMAND_NAME": {"group": "Announcements", "secret": False, "restart": True, "why": "Server command name sent by the announcement hook."},
    "DUNE_ANNOUNCE_TITLE": {"group": "Announcements", "secret": False, "restart": True, "why": "Default title for generic in-game service broadcasts."},
    "DUNE_ANNOUNCE_DURATION_SECONDS": {"group": "Announcements", "secret": False, "restart": True, "why": "Default on-screen duration for generic in-game service broadcasts."},
    "DUNE_ANNOUNCE_PAYLOAD_MODE": {"group": "Announcements", "secret": False, "restart": True, "why": "Built-in announcement envelope variant used when no raw payload template is set."},
    "DUNE_ANNOUNCE_PAYLOAD_TEMPLATE": {"group": "Announcements", "secret": False, "restart": True, "why": "Optional raw RabbitMQ payload template for overriding the default ServiceBroadcast envelope."},
    "DUNE_ADMIN_RESTART_COMMAND": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Executable hook used by the scheduled restart runner."},
    "DUNE_ADMIN_RESTART_COMMAND_TIMEOUT_SECONDS": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Timeout for each scheduled restart hook invocation."},
    "DUNE_RESTART_COMPOSE_PROJECT": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Compose project label used by the Docker-socket restart hook."},
    "DUNE_RESTART_DOCKER_SOCKET": {"group": "Admin Panel", "secret": False, "restart": True, "why": "Docker Engine Unix socket path used by the restart hook when Docker CLI is unavailable."},
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
    restart_at = now + ANNOUNCEMENT_DELAYS[delay_key]
    job = {
        "id": secrets.token_urlsafe(12),
        "message": message,
        "delay": delay_key,
        "createdAt": now,
        "restartAt": restart_at,
        "repeatSeconds": repeat_seconds,
        "nextSendAt": now,
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
    delay_key = str(body.get("delay", "immediate")).strip()
    if delay_key not in ANNOUNCEMENT_DELAYS:
        raise ValueError("invalid restart delay")
    message = str(body.get("message", "")).strip()
    repeat_seconds = int(body.get("repeat_seconds", body.get("repeatSeconds", 60)) or 0)
    announce = str(body.get("announce", "true")).lower() in ("1", "true", "yes", "on")
    execute = str(body.get("execute", "")).lower() in ("1", "true", "yes", "on")
    now = time.time()
    run_at = now + ANNOUNCEMENT_DELAYS[delay_key]
    job = {
        "id": secrets.token_urlsafe(12),
        "target": target,
        "targetLabel": RESTART_TARGETS[target]["label"],
        "services": RESTART_TARGETS[target]["services"],
        "delay": delay_key,
        "createdAt": now,
        "runAt": run_at,
        "message": message,
        "announce": announce,
        "repeatSeconds": repeat_seconds,
        "execute": execute,
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
        schedule_announcement({"delay": delay_key, "repeat_seconds": repeat_seconds, "message": message})
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


def execute_restart(job):
    if not job.get("execute"):
        return {"ok": True, "dryRun": True, "output": "scheduled restart reached run time; execute=false so no command was run"}
    command = pathlib.Path(RESTART_COMMAND)
    if not command.exists() or not os.access(command, os.X_OK):
        return {"ok": False, "error": f"restart command is not executable: {command}"}
    env = os.environ.copy()
    env.update({
        "DUNE_RESTART_JOB_ID": job.get("id", ""),
        "DUNE_RESTART_TARGET": job.get("target", ""),
        "DUNE_RESTART_SERVICES": " ".join(job.get("services", [])),
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
        return {"ok": False, "error": str(exc)}
    output = (result.stdout + result.stderr).strip()
    if len(output) > AUDIT_FIELD_LIMIT:
        output = output[:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return {"ok": result.returncode == 0, "returncode": result.returncode, "output": output}


def deliver_announcement(job):
    command = pathlib.Path(ANNOUNCEMENT_COMMAND)
    if not command.exists() or not os.access(command, os.X_OK):
        return {"ok": False, "error": f"announce command is not executable: {command}"}
    env = os.environ.copy()
    env.update({
        "DUNE_ANNOUNCE_MESSAGE": job.get("message", ""),
        "DUNE_ANNOUNCE_RESTART_AT": str(int(float(job.get("restartAt", time.time())))),
        "DUNE_ANNOUNCE_JOB_ID": job.get("id", ""),
    })
    try:
        result = subprocess.run(
            [str(command), job.get("message", "")],
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
                if now >= float(job.get("restartAt", 0)) and int(job.get("deliveryCount") or 0) > 0:
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
    path = BACKUP_ROOT / f"{stamp}-{DATABASE}.dump"
    temp_path = BACKUP_ROOT / f".{stamp}-{DATABASE}.dump.tmp"
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


class Handler(BaseHTTPRequestHandler):
    server_version = "dune-admin-panel"
    protocol_version = "HTTP/1.1"

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
            elif parsed.path == "/api/status":
                self.json({
                    "database": DATABASE,
                    "mutationsEnabled": MUTATIONS_ENABLED,
                    "itemGrantsEnabled": ITEM_GRANTS_ENABLED,
                    "adminTokenConfigured": bool(ADMIN_TOKEN),
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
                self.audit("database-backup", path=result.get("path"), bytes=result.get("bytes"))
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

    def character_detail(self, account_id):
        player = query("select * from dune.player_state where account_id=%s", (account_id,))
        if not player:
            self.error(HTTPStatus.NOT_FOUND, "character not found")
            return {}
        controller_id = player[0].get("player_controller_id")
        pawn_id = player[0].get("player_pawn_id")
        return {
            "player": player[0],
            "account": query("select id, funcom_id, platform_name, platform_id, takeoverable from dune.accounts where id=%s", (account_id,)),
            "currency": query("select * from dune.player_virtual_currency_balances where player_controller_id=%s order by currency_id", (controller_id,)),
            "specialization": query("select * from dune.specialization_tracks where player_id=%s order by track_type::text", (controller_id,)),
            "faction": query("select * from dune.player_faction where actor_id=%s order by faction_id", (pawn_id,)),
            "reputation": query("select * from dune.player_faction_reputation where actor_id=%s order by faction_id", (pawn_id,)),
            "inventories": query("select * from dune.inventories where actor_id in (%s,%s) order by id", (controller_id, pawn_id)),
            "inventoryItems": query("select * from dune.admin_get_inventory_details(%s)", (account_id,)),
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
        ready_alive = sum(1 for row in farm if row.get("ready") and row.get("alive"))
        active_count = len(active)
        player_counts = query("""
            select
              coalesce((select sum(connected_players) from dune.farm_state), 0) as connected_players_reported,
              (select count(*) from dune.get_online_player_controller_ids_on_farm()) as online_controller_ids,
              (select count(*) from dune.get_all_online_or_recently_disconnected_player_online_state()) as online_or_recently_disconnected,
              (select count(*) from dune.get_player_online_state_within_grace_period_for_each_server()) as grace_period_entries
        """)[0]
        verdicts = [
            {"name": "all partitions have ready/alive farm rows", "ok": expected > 0 and ready_alive == expected, "value": f"{ready_alive}/{expected}"},
            {"name": "active server ids match partitions", "ok": expected > 0 and active_count == expected, "value": f"{active_count}/{expected}"},
            {"name": "map health rows", "ok": expected > 0 and all(row.get("online") for row in map_status), "value": f"{sum(1 for row in map_status if row.get('online'))}/{len(map_status)}"},
            {"name": "RabbitMQ-backed farm registration", "ok": expected > 0 and ready_alive == expected and active_count == expected, "value": "inferred from farm_state and active_server_ids"},
            {"name": "player counts query", "ok": True},
        ]
        network = self.network_health()
        verdicts.extend(network["verdicts"])
        return {
            "verdicts": verdicts,
            "playerCounts": player_counts,
            "summary": {
                "readyAlive": ready_alive,
                "expectedPartitions": expected,
                "activeServers": active_count,
                "onlineMaps": sum(1 for row in map_status if row.get("online")),
                "totalMaps": len(map_status),
            },
            "mapStatus": map_status,
            "network": network,
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
            online = bool(server_id) and ready and alive and active and not bool(part.get("blocked"))
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
        if not ADMIN_TOKEN:
            raise PermissionError("DUNE_ADMIN_TOKEN is not configured")
        peer = self.client_address[0] if self.client_address else "unknown"
        now = time.time()
        failures = [ts for ts in AUTH_FAILURES.get(peer, []) if now - ts < AUTH_FAILURE_WINDOW_SECONDS]
        AUTH_FAILURES[peer] = failures
        if len(failures) >= AUTH_FAILURE_LIMIT:
            self.audit("auth-throttled", ok=False, failures=len(failures))
            raise PermissionError("too many failed admin token attempts")
        provided = self.headers.get("X-Admin-Token", "")
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
    :root { color-scheme: dark; --bg:#101310; --panel:#191d19; --panel2:#141814; --muted:#9da89e; --line:#30382f; --text:#ecf2e8; --accent:#d7a64a; --danger:#d66b5f; --ok:#7bbf74; --warn:#e0b45e; }
    * { box-sizing:border-box; }
    body { margin:0; font:14px/1.45 system-ui, sans-serif; background:var(--bg); color:var(--text); }
    header { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:14px 18px; border-bottom:1px solid var(--line); background:#151915; position:sticky; top:0; z-index:3; }
    h1 { font-size:18px; margin:0; }
    h2 { font-size:16px; margin:0 0 10px; }
    h3 { font-size:13px; margin:0 0 8px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
    main { display:grid; grid-template-columns:280px minmax(0,1fr); min-height:calc(100vh - 58px); }
    nav { border-right:1px solid var(--line); padding:14px; background:#121612; position:sticky; top:58px; height:calc(100vh - 58px); overflow:auto; }
    section { padding:18px; min-width:0; }
    button, input, select, textarea { font:inherit; border:1px solid var(--line); background:#101310; color:var(--text); border-radius:6px; padding:8px 10px; }
    button { cursor:pointer; background:#22291f; white-space:nowrap; }
    button.primary { background:var(--accent); color:#16120a; border-color:#e0b45e; font-weight:700; }
    button.danger { background:#35201e; color:#ffd5d0; border-color:#78423c; }
    input, select { width:100%; box-sizing:border-box; }
    textarea { width:100%; min-height:340px; box-sizing:border-box; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; }
    .tabs { display:grid; gap:8px; }
    .tab { padding:9px 10px; text-align:left; }
    .tab.active { border-color:var(--accent); color:var(--accent); background:#252416; }
    .card { border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; margin-bottom:14px; }
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
    .actionGrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:8px; }
    .actionGrid button { text-align:left; white-space:normal; min-height:42px; }
    .muted { color:var(--muted); }
    .ok { color:var(--ok); }
    .dangerText { color:var(--danger); }
    label span { display:block; margin-top:5px; font-size:12px; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; border-bottom:1px solid var(--line); padding:7px 6px; vertical-align:top; }
    .tableWrap { overflow:auto; border:1px solid var(--line); border-radius:8px; }
    .tableWrap table th { background:#151915; position:sticky; top:0; }
    pre { white-space:pre-wrap; overflow:auto; background:#0d100d; border:1px solid var(--line); padding:10px; border-radius:6px; max-height:360px; }
    #statusSummary { display:grid; gap:8px; }
    #statusRaw { max-height:180px; font-size:12px; }
    .hostNote { font-size:13px; line-height:1.35; }
    .hidden { display:none; }
    @media (max-width: 820px) { header { align-items:flex-start; flex-direction:column; } main { grid-template-columns:1fr; } nav { position:static; height:auto; border-right:0; border-bottom:1px solid var(--line); } .tabs { grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); } }
  </style>
</head>
<body>
  <header>
    <h1>Dune Admin</h1>
    <div class="row"><input id="token" type="password" placeholder="Admin token"><button id="saveTokenBtn">Use token</button><button id="clearTokenBtn">Clear</button></div>
  </header>
  <main>
    <nav>
      <div class="tabs">
        <button class="tab active" data-tab="overview">Overview</button>
        <button class="tab" data-tab="ops">Ops</button>
        <button class="tab" data-tab="security">Security</button>
        <button class="tab" data-tab="runbook">Runbook</button>
        <button class="tab" data-tab="characters">Characters</button>
        <button class="tab" data-tab="settings">Settings</button>
        <button class="tab" data-tab="mutations">Admin Actions</button>
      </div>
      <div class="card hostNote"><div class="muted"><b>admin.example.test</b><br>LAN/VPN admin surface. Use the token to unlock data and writes.</div></div>
      <div class="card">
        <h3>Runtime</h3>
        <div id="statusSummary"></div>
        <details>
          <summary class="muted">Raw status</summary>
          <pre id="statusRaw"></pre>
        </details>
      </div>
    </nav>
    <section id="view"></section>
  </main>
<script nonce="__NONCE__">
let token = sessionStorage.getItem('duneAdminToken') || '';
document.getElementById('token').value = token;
const validTabs = new Set(['overview', 'ops', 'security', 'runbook', 'characters', 'settings', 'mutations']);
let current = validTabs.has(location.hash.slice(1)) ? location.hash.slice(1) : (sessionStorage.getItem('duneAdminTab') || 'overview');
if (!validTabs.has(current)) current = 'overview';
let pendingAdminAccountId = '';
const view = document.getElementById('view');

function saveToken(){ token = document.getElementById('token').value; sessionStorage.setItem('duneAdminToken', token); load(); }
function clearToken(){ token = ''; document.getElementById('token').value = ''; sessionStorage.removeItem('duneAdminToken'); load(); }
async function api(path, opts={}) {
  opts.headers = Object.assign({'Content-Type':'application/json'}, opts.headers || {});
  if (token) opts.headers['X-Admin-Token'] = token;
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
function esc(v){ return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function table(rows){
  if (!rows || !rows.length) return '<div class="muted">No rows.</div>';
  const keys = Object.keys(rows[0]);
  return `<div class="tableWrap"><table><thead><tr>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr data-id="${esc(r.account_id ?? '')}">${keys.map(k=>`<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function metric(label, value, tone=''){
  return `<div class="metric"><div class="label">${esc(label)}</div><div class="value ${tone}">${esc(value)}</div></div>`;
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
  return `<div class="card"><h2>Scheduled Restart</h2><p class="muted">Schedules a component restart through <code>${esc(state.command || '')}</code>. Leave execution off for a dry-run schedule; enable it only when the restart hook should control Docker.</p><div class="grid"><label>Target<select id="restartTarget">${targetOptions}</select></label><label>Restart after<select id="restartDelay">${delayOptions}</select></label><label>Repeat notice every<select id="restartRepeat"><option value="0">Do not repeat</option><option value="30">30 sec</option><option value="60" selected>60 sec</option><option value="300">5 min</option><option value="600">10 min</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option></select></label><label>Restart action<select id="restartExecute"><option value="false" selected>Dry-run schedule</option><option value="true">Execute restart hook</option></select></label></div><label><input id="restartAnnounce" type="checkbox" checked style="width:auto"> Also schedule announcement</label><label>Message<textarea id="restartMessage" rows="3" style="min-height:82px">Server restart soon. Please get to a safe place.</textarea></label><p><button id="scheduleRestartBtn" class="primary">Schedule restart</button> <button id="cancelRestartBtn" class="danger">Cancel active restart</button></p><h3>Current</h3>${jobSummary}<h3>Last Execution</h3>${execution}</div>`;
}
function signalList(groups){
  return Object.entries(groups || {}).map(([group, rows]) => `<div class="card"><h2>${esc(group)}</h2><table><thead><tr><th>Name</th><th>Value</th><th>Why</th></tr></thead><tbody>${(rows || []).map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(Array.isArray(r.value) ? r.value.join(', ') : r.value)}</td><td>${esc(r.why)}</td></tr>`).join('')}</tbody></table></div>`).join('');
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
  return `<div class="card"><h2>Quick Actions</h2><div class="actionGrid">${actions.map(a => `<button class="${esc(a.className || '')}" data-jump="${esc(a.tab)}">${esc(a.label)}</button>`).join('')}</div></div>`;
}
function syncTabs(){
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.dataset.tab === current));
}
function show(name){
  if (!validTabs.has(name)) return;
  current = name;
  sessionStorage.setItem('duneAdminTab', current);
  if (location.hash.slice(1) !== current) history.replaceState(null, '', '#' + current);
  syncTabs();
  load();
}
function renderStatus(data){
  document.getElementById('statusSummary').innerHTML = [
    statusPill('admin token configured', data.adminTokenConfigured),
    statusPill('item grants', data.itemGrantsEnabled),
    `<span class="pill ${data.mutationsEnabled ? 'warn' : 'ok'}">mutations: ${data.mutationsEnabled ? 'enabled' : 'off'}</span>`,
    `<span class="pill">db: ${esc(data.database)}</span>`
  ].join('');
  document.getElementById('statusRaw').textContent = JSON.stringify(data, null, 2);
}
async function refreshStatus(){ renderStatus(await api('/api/status')); }
async function load(){
  syncTabs();
  await refreshStatus().catch(e => {
    document.getElementById('statusSummary').innerHTML = `<span class="pill bad">${esc(e.message)}</span>`;
    document.getElementById('statusRaw').textContent = e.message;
  });
  try {
    if (current === 'overview') { await overview(); return; }
    if (current === 'ops') { await ops(); return; }
    if (current === 'security') { await security(); return; }
    if (current === 'runbook') { await runbook(); return; }
    if (current === 'characters') { await characters(); return; }
    if (current === 'settings') { await settings(); return; }
    if (current === 'mutations') { await mutations(); return; }
  } catch (e) {
    view.innerHTML = `<div class="card"><h2>Admin Token Required</h2><p class="dangerText">${esc(e.message)}</p><p class="muted">Paste the admin token in the header and press <b>Use token</b>. The panel is reachable, but server data and write controls stay locked until the token is present.</p></div><div class="metricGrid">${metric('Endpoint', location.host)}${metric('Item Grants', 'enabled', 'ok')}${metric('Mutations', 'off', 'ok')}</div>`;
  }
}
async function overview(){
  const health = await api('/api/ops/health');
  const state = health;
  const summary = health.summary || {};
  const players = (state.farmState || []).reduce((sum, r) => sum + Number(r.connected_players || 0), 0);
  view.innerHTML = `<div class="sectionHeader"><h2>Overview</h2><div class="toolbar"><button data-jump="ops">Ops detail</button><button data-jump="characters">Find character</button><button data-jump="mutations" class="primary">Admin Actions</button></div></div><div class="metricGrid">${metric('Ready Servers', `${summary.readyAlive ?? 0}/${summary.expectedPartitions ?? 0}`, summary.readyAlive === summary.expectedPartitions ? 'ok' : 'dangerText')}${metric('Online Maps', `${summary.onlineMaps ?? 0}/${summary.totalMaps ?? 0}`, summary.onlineMaps === summary.totalMaps ? 'ok' : 'dangerText')}${metric('Active IDs', `${summary.activeServers ?? 0}/${summary.expectedPartitions ?? 0}`)}${metric('Reported Players', players)}</div>${actionGrid([{tab:'ops',label:'Open detailed map and network health'},{tab:'security',label:'Review security checks and audit trail'},{tab:'settings',label:'Edit server settings and configs'},{tab:'runbook',label:'Open operational runbook'}])}<div class="card"><h2>Map Health</h2>${mapStatusTable(health.mapStatus)}</div><div class="card"><h2>Network and Upstream</h2>${probeTable(health.network?.probes)}</div><div class="card"><h2>Health Verdict</h2>${checks(health.verdicts)}</div>`;
}
async function ops(){
  const health = await api('/api/ops/health');
  const opt = await api('/api/ops/optimization');
  const announcement = await api('/api/ops/announcement');
  const restart = await api('/api/ops/restart');
  const pc = health.playerCounts || {};
  view.innerHTML = `<div class="sectionHeader"><h2>Operations</h2><div class="toolbar"><button data-jump="overview">Overview</button><button data-jump="runbook">Runbook</button><button data-jump="settings">Settings</button></div></div><div class="metricGrid">${metric('Connected Players', pc.connected_players_reported ?? 0)}${metric('Online Controllers', pc.online_controller_ids ?? 0)}${metric('Recent Online State', pc.online_or_recently_disconnected ?? 0)}${metric('Grace Entries', pc.grace_period_entries ?? 0)}</div>${actionGrid([{tab:'characters',label:'Inspect characters currently represented in DB'},{tab:'security',label:'Check audit events and exposed settings'},{tab:'mutations',label:'Create a backup before writes',className:'primary'}])}${restartPanel(restart)}${announcementPanel(announcement)}<div class="card"><h2>Health Verdict</h2>${checks(health.verdicts)}</div><div class="card"><h2>Map Online/Offline</h2>${mapStatusTable(health.mapStatus)}</div><div class="card"><h2>Local and Upstream Network</h2>${probeTable(health.network?.probes)}</div><div class="card"><h2>Farm State</h2>${table(health.farmState)}</div><div class="card"><h2>Partitions</h2>${table(health.partitions)}</div>${signalList(opt)}`;
  document.getElementById('scheduleAnnouncementBtn').addEventListener('click', scheduleAnnouncement);
  document.getElementById('cancelAnnouncementBtn').addEventListener('click', cancelAnnouncement);
  document.getElementById('scheduleRestartBtn').addEventListener('click', scheduleRestart);
  document.getElementById('cancelRestartBtn').addEventListener('click', cancelRestart);
}
async function security(){
  const audit = await api('/api/ops/security');
  const events = await api('/api/ops/audit');
  const failed = (audit.checks || []).filter(c => !c.ok).length;
  view.innerHTML = `<div class="sectionHeader"><h2>Security</h2><div class="toolbar"><span class="pill ${failed ? 'warn' : 'ok'}">${failed ? failed + ' checks need attention' : 'checks OK'}</span><button data-jump="settings">Edit settings</button><button data-jump="mutations">Backup</button></div></div>${actionGrid([{tab:'settings',label:'Open editable env and config allowlists'},{tab:'runbook',label:'Open commands for service operations'},{tab:'ops',label:'Review health before exposing services'}])}<div class="card"><h2>Security Checks</h2>${checks(audit.checks)}</div><div class="card"><h2>Recent Audit Events</h2>${table(events.events)}</div><div class="card"><h2>Notes</h2><ul>${audit.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></div><div class="card"><h2>Editable Env Keys</h2><div class="toolbar">${audit.safeEnvKeys.map(k => `<span class="pill">${esc(k)}</span>`).join('')}</div></div><div class="card"><h2>Editable Config Files</h2><div class="toolbar">${audit.allowedConfigFiles.map(k => `<span class="pill">${esc(k)}</span>`).join('')}</div></div>`;
}
async function runbook(){
  const data = await api('/api/ops/runbook');
  view.innerHTML = `<div class="sectionHeader"><h2>Runbook</h2><div class="toolbar"><span class="pill">copy/paste commands</span><button data-jump="ops">Ops</button><button data-jump="settings">Settings</button></div></div>${actionGrid([{tab:'overview',label:'Check server health first'},{tab:'mutations',label:'Create DB backup before risky work',className:'primary'},{tab:'security',label:'Review recent admin audit events'}])}<div class="card"><p class="muted">${esc(data.why)}</p>${table(data.commands)}</div>`;
}
async function characters(){
  const lastQuery = sessionStorage.getItem('duneAdminCharacterQuery') || '';
  view.innerHTML = `<div class="sectionHeader"><h2>Characters</h2><div class="toolbar"><span class="pill">lookup and inspect</span><button data-jump="mutations" class="primary">Admin Actions</button><button data-jump="settings">Settings</button></div></div>${actionGrid([{tab:'mutations',label:'Open grants, XP, currency, and item maintenance'},{tab:'security',label:'Review audit trail for recent writes'},{tab:'ops',label:'Check server state before changing players'}])}<div class="card"><div class="row"><input id="q" placeholder="Character, Funcom ID, platform ID" value="${esc(lastQuery)}"><button id="characterSearchBtn" class="primary">Search</button><button id="characterListAllBtn">List all</button></div><div id="results"></div></div><div id="detail"></div>`;
  document.getElementById('characterSearchBtn').addEventListener('click', searchCharacters);
  document.getElementById('characterListAllBtn').addEventListener('click', () => {
    document.getElementById('q').value = '';
    searchCharacters();
  });
  document.getElementById('q').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchCharacters();
  });
  if (lastQuery) await searchCharacters();
}
async function searchCharacters(){
  const query = document.getElementById('q').value;
  sessionStorage.setItem('duneAdminCharacterQuery', query);
  const rows = await api('/api/characters?q=' + encodeURIComponent(query));
  const results = document.getElementById('results');
  results.innerHTML = table(rows);
  results.querySelectorAll('tbody tr').forEach(row => row.onclick = () => pickCharacter(row));
}
async function pickCharacter(row){
  const id = row.dataset.id || row.children[0].textContent;
  if (!id) return;
  const d = await api('/api/characters/' + encodeURIComponent(id));
  const ref = await api('/api/admin/reference');
  const p = d.player || {};
  const firstTrack = (d.specialization && d.specialization[0]) || {};
  document.getElementById('detail').innerHTML = `<datalist id="itemTemplateList">${templateDatalist(ref)}</datalist><div class="card"><h2>${esc(p.character_name || 'Character')}</h2><div class="grid"><div><b>Account</b><br>${esc(p.account_id)}</div><div><b>Controller</b><br>${esc(p.player_controller_id)}</div><div><b>Pawn</b><br>${esc(p.player_pawn_id)}</div><div><b>Status</b><br>${esc(p.online_status)}</div></div><p><button id="detailOpenAdminActionsBtn" class="primary">Open in Admin Actions</button></p></div><div class="card"><h2>Quick Admin</h2><p class="dangerText">Back up first. Mutations require server-side enablement.</p><div class="grid"><label>Currency<select id="detailCurId">${currencyBalanceOptions(d.currency, ref.currencyIds)}</select></label><label>Amount<input id="detailCurAmount" value="1000"></label><label>Mode<select id="detailCurMode"><option>add</option><option>set</option></select></label></div><p><button id="detailCurrencyBtn" class="primary">Apply currency</button></p><div class="grid"><label>Track<select id="detailTrack">${specializationOptions(d.specialization, ref.specializationTrackTypes)}</select></label><label>XP amount<input id="detailXpAmount" value="1000"></label><label>Level for set/new track<input id="detailXpLevel" value="${esc(firstTrack.level ?? 0)}"></label><label>Mode<select id="detailXpMode"><option>add</option><option>set</option></select></label></div><p><button id="detailXpBtn" class="primary">Apply XP</button></p><div class="grid"><label>Owned inventory<select id="detailGrantInventory"><option value="">All owned inventories</option>${inventoryOptions(d.inventories)}</select></label><label>Owned item<select id="detailItemSelect">${inventoryItemOptions(d.inventoryItems)}</select></label><label>Template ID<input id="detailGrantTemplate" list="itemTemplateList" placeholder="SMG_Unique_LargeMag_06"></label><label>Stack size<input id="detailGrantStack" value="1"></label><label>Delete count<input id="detailDeleteCount" placeholder="blank/all"></label></div><p><button id="detailDryRunBtn" class="primary">Dry run item</button> <button id="detailGrantBtn" class="danger">Grant item</button> <button id="detailSetStackBtn" class="primary">Set selected stack</button> <button id="detailDeleteItemBtn" class="danger">Delete selected item/count</button></p><pre id="detailGrantResult"></pre></div><div class="card"><h2>Inventories</h2>${table(d.inventories)}</div><div class="card"><h2>Inventory Items</h2>${table(d.inventoryItems)}</div><div class="card"><h2>Raw Detail</h2><pre>${esc(JSON.stringify(d, null, 2))}</pre></div>`;
  const detailInventory = document.getElementById('detailGrantInventory');
  const detailItem = document.getElementById('detailItemSelect');
  const setDetailItemOptions = () => {
    const inventoryId = detailInventory?.value || '';
    const allItems = d.inventoryItems || [];
    const filtered = inventoryId ? allItems.filter(r => String(r.inventory_id ?? '') === String(inventoryId)) : allItems;
    detailItem.innerHTML = inventoryItemOptions(filtered);
    document.getElementById('detailGrantTemplate').value = '';
  };
  detailInventory?.addEventListener('change', setDetailItemOptions);
  detailItem.addEventListener('change', e => {
    const option = e.target.selectedOptions?.[0];
    if (option?.dataset.template) document.getElementById('detailGrantTemplate').value = option.dataset.template;
    if (option?.dataset.stack) document.getElementById('detailGrantStack').value = option.dataset.stack;
    if (option?.dataset.inventory && detailInventory) detailInventory.value = option.dataset.inventory;
  });
  document.getElementById('detailTrack').addEventListener('change', e => {
    const level = e.target.selectedOptions?.[0]?.dataset.level || '';
    if (level) document.getElementById('detailXpLevel').value = level;
  });
  document.getElementById('detailCurrencyBtn').addEventListener('click', () => currencyFor(p.player_controller_id));
  document.getElementById('detailOpenAdminActionsBtn').addEventListener('click', () => {
    pendingAdminAccountId = String(p.account_id || '');
    show('mutations');
  });
  document.getElementById('detailXpBtn').addEventListener('click', () => xpFor(p.player_controller_id));
  document.getElementById('detailDryRunBtn').addEventListener('click', () => grantItemForAccount(p.account_id, true));
  document.getElementById('detailGrantBtn').addEventListener('click', () => grantItemForAccount(p.account_id, false));
  document.getElementById('detailSetStackBtn').addEventListener('click', setDetailItemStack);
  document.getElementById('detailDeleteItemBtn').addEventListener('click', deleteDetailItem);
}
async function settings(){
  const env = await api('/api/settings/env');
  const transfer = await api('/api/settings/director-transfer');
  const onlineState = await api('/api/settings/player-online-state');
  const configs = await api('/api/settings/configs');
  view.innerHTML = `<div class="sectionHeader"><h2>Settings</h2><div class="toolbar"><button data-jump="security">Security</button><button data-jump="ops">Ops</button><button id="saveEnvBtn" class="primary">Save env settings</button></div></div><div class="card"><p class="muted">These write <code>.env</code>, <code>config/director.ini</code>, or <code>config/UserGame.ini</code> with a backup under <code>backups/admin-panel</code>. Most service settings need the affected containers recreated before running processes pick them up.</p></div>${actionGrid([{tab:'ops',label:'Check live state after settings changes'},{tab:'mutations',label:'Create a DB backup before admin writes',className:'primary'},{tab:'characters',label:'Inspect player state affected by settings'}])}${envEditor(env)}${playerOnlineStateEditor(onlineState)}${directorTransferEditor(transfer)}<div class="card"><h2>Config Files</h2><select id="cfg">${Object.keys(configs).map(k=>`<option>${esc(k)}</option>`).join('')}</select><textarea id="cfgText"></textarea><p><button id="saveCfgBtn" class="primary">Save config with backup</button></p></div>`;
  window.configs = configs; selectCfg();
  document.getElementById('cfg').addEventListener('change', selectCfg);
  document.getElementById('saveEnvBtn').addEventListener('click', saveEnv);
  document.getElementById('savePlayerOnlineStateBtn').addEventListener('click', savePlayerOnlineState);
  document.getElementById('saveDirectorTransferBtn').addEventListener('click', saveDirectorTransfer);
  document.getElementById('saveCfgBtn').addEventListener('click', saveCfg);
}
function selectCfg(){ const name=document.getElementById('cfg').value; document.getElementById('cfgText').value = window.configs[name] || ''; }
async function saveEnv(){
  const body={};
  document.querySelectorAll('[id^=env_]').forEach(i => {
    if (i.dataset.secret === 'true' && !i.value) return;
    body[i.id.slice(4)] = i.value;
  });
  await api('/api/settings/env', {method:'POST', body:JSON.stringify(body)}); alert('Saved .env settings');
}
async function saveCfg(){
  const name=document.getElementById('cfg').value;
  await api('/api/settings/configs/' + encodeURIComponent(name), {method:'POST', body:JSON.stringify({content:document.getElementById('cfgText').value})});
  alert('Saved ' + name);
}
async function saveDirectorTransfer(){
  const body={};
  document.querySelectorAll('[id^=transfer_]').forEach(i => body[i.id.slice(9)] = i.value);
  await api('/api/settings/director-transfer', {method:'POST', body:JSON.stringify(body)});
  alert('Saved director transfer settings');
}
async function savePlayerOnlineState(){
  const body={};
  document.querySelectorAll('[id^=online_]').forEach(i => body[i.id.slice(7)] = i.value);
  await api('/api/settings/player-online-state', {method:'POST', body:JSON.stringify(body)});
  alert('Saved logout timers');
}
async function mutations(){
  const ref = await api('/api/admin/reference');
  const characterRows = await api('/api/characters?q=');
  const referenceErrors = ref.errors && Object.keys(ref.errors).length ? `<div class="card"><h2>Reference Errors</h2><pre>${esc(JSON.stringify(ref.errors, null, 2))}</pre></div>` : '';
  view.innerHTML = `${referenceErrors}<div class="sectionHeader"><h2>Admin Actions</h2><div class="toolbar"><button data-jump="characters">Characters</button><button data-jump="settings">Settings</button><button data-jump="security">Audit</button></div></div>${actionGrid([{tab:'characters',label:'Look up a character and inspect raw state'},{tab:'settings',label:'Enable or review mutation-related settings'},{tab:'runbook',label:'Open service commands after writes'}])}<div class="card"><h2>Backups</h2><p>Creates a Postgres custom-format dump under <code>backups/admin-panel</code>.</p><button id="backupBtn" class="primary">Create DB backup</button><pre id="backupResult"></pre></div><div class="card"><h2>Currency and XP</h2><p class="dangerText">Writes require <code>DUNE_ADMIN_MUTATIONS_ENABLED=true</code> and a valid admin token. Back up first.</p><div class="grid"><label>Character<select id="adminCharacterSelect">${characterOptions(characterRows)}</select></label><label>Player controller ID<input id="pcid"></label><label>Currency ID<select id="curid">${options(ref.currencyIds, 'currency_id', '1')}</select></label><label>Amount<input id="amount" value="1000"></label><label>Mode<select id="mode"><option>add</option><option>set</option></select></label></div><p><button id="currencyBtn" class="primary">Apply currency</button></p><div class="grid"><label>Player/controller ID<input id="xpid"></label><label>Track type<select id="track">${options(ref.specializationTrackTypes, 'track_type')}</select></label><label>XP amount<input id="xpamount" value="1000"></label><label>Level for set/new track<input id="xplevel" value="0"></label><label>Mode<select id="xpmode"><option>add</option><option>set</option></select></label></div><p><button id="xpBtn" class="primary">Apply XP</button></p></div><div class="card"><h2>Specialization Keystones</h2><div class="grid"><label>Player/controller ID<input id="keyPlayer"></label><label>Keystone<select id="keystone">${options(ref.keystones, 'name')}</select></label></div><p><button id="purchaseKeystoneBtn" class="primary">Purchase keystone</button> <button id="resetKeystonesBtn" class="danger">Reset all keystones</button></p><pre id="keystoneResult"></pre></div><div class="card"><h2>Item Grants</h2><p class="dangerText">Use exact server template IDs. Public item databases: <a href="${esc(ref.publicItemDatabase)}" target="_blank" rel="noreferrer">gaming.tools</a> and <a href="${esc(ref.publicItemDatabaseAlt)}" target="_blank" rel="noreferrer">Arrakis Atlas</a>. Dry run first when using IDs not observed locally.</p><div class="grid"><label>Character<select id="grantCharacterSelect">${characterOptions(characterRows)}</select></label><label>Known inventory<select id="grantInventorySelect">${inventoryOptions(ref.recentInventories)}</select></label><label>Inventory ID<input id="grantInventory" placeholder="explicit inventory"></label><label>Account ID<input id="grantAccount" placeholder="auto-select player inventory"></label><label>Character name<input id="grantCharacter" placeholder="auto-select by name"></label><label>Inventory type<select id="grantInventoryType">${inventoryTypeOptions(ref.inventoryTypes)}</select></label><label>Template ID<input id="grantTemplate" list="itemTemplateList" placeholder="SMG_Unique_LargeMag_06"></label><label>Stack size<input id="grantStack" value="1"></label><label>Quality level<input id="grantQuality" value="0"></label><label>Position index<input id="grantPosition" placeholder="auto"></label></div><label>Stats JSON<textarea id="grantStats">{}</textarea></label><p><button id="dryRunItemBtn" class="primary">Dry run</button> <button id="grantItemBtn" class="danger">Grant item</button></p><pre id="grantResult"></pre></div><div class="card"><h2>Item Maintenance</h2><div class="grid"><label>Character<select id="itemCharacterSelect">${characterOptions(characterRows)}</select></label><label>Owned item<select id="itemEditSelect"><option value="">Select a character first</option></select></label><label>Item ID<input id="itemEditId"></label><label>New stack size<input id="itemEditStack" value="1"></label><label>Delete count<input id="itemDeleteCount" placeholder="blank/all"></label></div><p><button id="setItemStackBtn" class="primary">Set stack</button> <button id="deleteItemBtn" class="danger">Delete item/count</button></p><pre id="itemEditResult"></pre></div><datalist id="itemTemplateList">${templateDatalist(ref)}</datalist><div class="card"><h2>Known Item Templates</h2><p class="muted">Exact template IDs observed in local item, reward, vendor, vehicle, or exchange tables.</p>${table(ref.knownItemTemplates)}</div><div class="card"><h2>Observed Item Templates</h2><p class="muted">Read-only reference from this server's current <code>dune.items</code> rows.</p>${table(ref.observedItemTemplates)}</div><div class="card"><h2>Recent Inventories</h2>${table(ref.recentInventories)}</div><div class="card"><h2>Inventory Types</h2>${table(ref.inventoryTypes)}</div><div class="card"><h2>Recipe Unlocks</h2><p class="muted">Not implemented yet. The DB exposes removal helpers and actor JSON recipe arrays, but no safe grant function has been mapped.</p><button id="unsupportedBtn" class="danger">Test unsupported endpoint</button></div>`;
  const loadCharacterAdminDetails = async (accountId) => {
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
      itemSelect.innerHTML = '<option value="">Could not load items</option>';
      document.getElementById('itemEditResult').textContent = e.message;
    }
  };
  const fillCharacter = async (select) => {
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
    await loadCharacterAdminDetails(option.value);
  };
  document.getElementById('adminCharacterSelect').addEventListener('change', e => fillCharacter(e.target));
  document.getElementById('grantCharacterSelect').addEventListener('change', e => fillCharacter(e.target));
  document.getElementById('itemCharacterSelect').addEventListener('change', e => fillCharacter(e.target));
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
  document.getElementById('backupBtn').addEventListener('click', backup);
  document.getElementById('currencyBtn').addEventListener('click', currency);
  document.getElementById('xpBtn').addEventListener('click', xp);
  document.getElementById('purchaseKeystoneBtn').addEventListener('click', purchaseKeystone);
  document.getElementById('resetKeystonesBtn').addEventListener('click', resetKeystones);
  document.getElementById('dryRunItemBtn').addEventListener('click', () => grantItem(true));
  document.getElementById('grantItemBtn').addEventListener('click', () => grantItem(false));
  document.getElementById('setItemStackBtn').addEventListener('click', setItemStack);
  document.getElementById('deleteItemBtn').addEventListener('click', deleteItem);
  document.getElementById('unsupportedBtn').addEventListener('click', unsupported);
  if (pendingAdminAccountId) {
    const target = document.getElementById('adminCharacterSelect');
    target.value = pendingAdminAccountId;
    pendingAdminAccountId = '';
    if (target.value) await fillCharacter(target);
  }
}
async function currency(){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:pcid.value,currency_id:curid.value,amount:amount.value,mode:mode.value})});
  alert('Currency updated');
}
async function currencyFor(playerControllerId){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:playerControllerId,currency_id:detailCurId.value,amount:detailCurAmount.value,mode:detailCurMode.value})});
  alert('Currency updated');
}
async function xp(){
  await api('/api/admin/xp', {method:'POST', body:JSON.stringify({player_id:xpid.value,track_type:track.value,amount:xpamount.value,level:xplevel.value,mode:xpmode.value})});
  alert('XP updated');
}
async function xpFor(playerId){
  await api('/api/admin/xp', {method:'POST', body:JSON.stringify({player_id:playerId,track_type:detailTrack.value,amount:detailXpAmount.value,level:detailXpLevel.value,mode:detailXpMode.value})});
  alert('XP updated');
}
async function backup(){
  const result = await api('/api/admin/backup', {method:'POST', body:'{}'});
  document.getElementById('backupResult').textContent = JSON.stringify(result, null, 2);
}
async function scheduleAnnouncement(){
  const result = await api('/api/ops/announcement', {method:'POST', body:JSON.stringify({
    delay: announceDelay.value,
    repeat_seconds: announceRepeat.value,
    message: announceMessage.value
  })});
  alert('Announcement scheduled');
  await ops();
}
async function cancelAnnouncement(){
  if (!confirm('Cancel active restart announcement?')) return;
  await api('/api/ops/announcement/cancel', {method:'POST', body:'{}'});
  await ops();
}
async function scheduleRestart(){
  const execute = restartExecute.value === 'true';
  const targetLabel = restartTarget.options[restartTarget.selectedIndex]?.textContent || restartTarget.value;
  const delayLabel = restartDelay.options[restartDelay.selectedIndex]?.textContent || restartDelay.value;
  const repeatLabel = restartRepeat.options[restartRepeat.selectedIndex]?.textContent || restartRepeat.value;
  const actionLabel = execute ? 'execute the restart hook' : 'dry-run only';
  if (!confirm(`Schedule ${targetLabel} restart after ${delayLabel}?\nNotice repeat: ${repeatLabel}\nAction: ${actionLabel}`)) return;
  await api('/api/ops/restart', {method:'POST', body:JSON.stringify({
    target: restartTarget.value,
    delay: restartDelay.value,
    repeat_seconds: restartRepeat.value,
    message: restartMessage.value,
    announce: restartAnnounce.checked,
    execute
  })});
  alert('Restart scheduled');
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
  if (!itemId) { alert('Select an owned item first'); return; }
  if (!confirm('Set this selected item stack size?')) return;
  const result = await api('/api/admin/item/stack', {method:'POST', body:JSON.stringify({item_id:itemId,stack_size:detailGrantStack.value,confirm:'SET STACK'})});
  document.getElementById('detailGrantResult').textContent = JSON.stringify(result, null, 2);
}
async function deleteDetailItem(){
  const itemId = document.getElementById('detailItemSelect')?.value || '';
  if (!itemId) { alert('Select an owned item first'); return; }
  if (!confirm('Delete this selected item or count from the stack?')) return;
  const result = await api('/api/admin/item/delete', {method:'POST', body:JSON.stringify({item_id:itemId,count:detailDeleteCount.value,confirm:'DELETE ITEM'})});
  document.getElementById('detailGrantResult').textContent = JSON.stringify(result, null, 2);
}
async function unsupported(){ try { await api('/api/admin/unsupported', {method:'POST', body:'{}'}); } catch(e) { alert(e.message); } }
document.getElementById('saveTokenBtn').addEventListener('click', saveToken);
document.getElementById('clearTokenBtn').addEventListener('click', clearToken);
document.addEventListener('click', e => {
  const target = e.target.closest('[data-jump]');
  if (target) show(target.dataset.jump);
});
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => show(button.dataset.tab)));
window.addEventListener('hashchange', () => {
  const tab = location.hash.slice(1);
  if (validTabs.has(tab) && tab !== current) show(tab);
});
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
