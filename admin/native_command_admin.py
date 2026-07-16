#!/usr/bin/env python3
"""Validated native admin-command payloads for the DASH browser console.

The wire contract is adapted from RedBlink's MIT-licensed admin-tools.sh at
commit 12ac3b8b30a0dac3d728a37db65cad4a292750b6.  Transport remains in
admin_panel.py so this module can be tested without a Docker daemon.
"""

import json
import math
import pathlib


COMMANDS = {
    "skill-points": "SkillsSetUnspentSkillPoints",
    "skill-module": "SkillsSetModuleLevel",
    "refill-water": "UpdateAllWaterFillables",
    "kick": "KickPlayer",
    "kick-all": "KickPlayer",
    "teleport": "TeleportTo",
    "clean-inventory": "CleanPlayerInventory",
    "reset-progression": "ResetProgression",
    "spawn-vehicle": "SpawnVehicleAt",
}

ONLINE_REQUIRED = {"refill-water", "teleport", "spawn-vehicle"}
CONFIRM_RUNTIME_ACTION = "RUN PLAYER ACTION"
CONFIRM_KICK_ALL = "KICK ALL ONLINE PLAYERS"


def _int(value, label, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return parsed


def _float(value, label, minimum=None, maximum=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return parsed


def load_catalog(path):
    path = pathlib.Path(path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"catalog must be an array: {path}")
    return rows


def resolve_skill_module(rows, value):
    folded = str(value or "").strip().casefold()
    if not folded:
        raise ValueError("module is required")
    exact = [row for row in rows if str(row.get("id") or "").casefold() == folded]
    if not exact:
        exact = [row for row in rows if str(row.get("name") or "").casefold() == folded]
    if len(exact) != 1:
        raise ValueError("skill module must uniquely match a catalog id or name")
    return exact[0]


def resolve_vehicle(rows, vehicle_id, template_name=""):
    folded = str(vehicle_id or "").strip().casefold()
    matches = [row for row in rows if str(row.get("id") or "").casefold() == folded]
    if len(matches) != 1:
        raise ValueError("vehicle must match a catalog id")
    vehicle = matches[0]
    templates = [str(value) for value in vehicle.get("templates") or []]
    requested = str(template_name or "").strip()
    if requested:
        selected = next((value for value in templates if value.casefold() == requested.casefold()), None)
        if not selected:
            raise ValueError("template is not valid for the selected vehicle")
    elif templates:
        selected = templates[0]
    else:
        raise ValueError("selected vehicle has no spawn templates")
    return {**vehicle, "template": selected}


def build_inner(action, player_id, body, skill_modules=None, vehicles=None):
    action = str(action or "").strip().lower()
    if action not in COMMANDS:
        raise ValueError(f"unsupported runtime action: {action}")
    player_id = "*" if action == "kick-all" else str(player_id or "").strip()
    if not player_id:
        raise ValueError("target Funcom player id is required")
    payload = {"ServerCommand": COMMANDS[action], "PlayerId": player_id}
    metadata = {}
    if action == "skill-points":
        payload["SkillPoints"] = _int(body.get("skill_points", body.get("skillPoints")), "skill points", 0, 100000)
    elif action == "skill-module":
        module = resolve_skill_module(skill_modules or [], body.get("module"))
        level = _int(body.get("level"), "level", 0, int(module.get("maxLevel", 1)))
        payload.update({"Module": str(module["id"]), "Level": level})
        metadata["skillModule"] = module
    elif action == "refill-water":
        payload["WaterAmount"] = _int(body.get("water_amount", body.get("waterAmount", 1000000)), "water amount", 1, 1000000000)
    elif action == "teleport":
        payload.update({
            "X": _float(body.get("x"), "x", -100000000, 100000000),
            "Y": _float(body.get("y"), "y", -100000000, 100000000),
            "Z": _float(body.get("z"), "z", -100000000, 100000000),
            "Yaw": _float(body.get("yaw", body.get("rotation", 0)), "yaw", -360, 360),
        })
    elif action == "spawn-vehicle":
        vehicle = resolve_vehicle(vehicles or [], body.get("vehicle"), body.get("template"))
        payload.update({
            "ClassName": str(vehicle["id"]),
            "TemplateName": str(vehicle["template"]),
            "X": _float(body.get("x"), "x"),
            "Y": _float(body.get("y"), "y"),
            "Z": _float(body.get("z"), "z"),
            "Rotation": _float(body.get("rotation", 0), "rotation"),
            "Persistent": 1.0,
        })
        metadata["vehicle"] = vehicle
    return payload, metadata


def build_outer(auth_token, inner):
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("DUNE_SERVER_COMMANDS_AUTH_TOKEN is not configured")
    return {
        "Version": 2,
        "AuthToken": token,
        "MessageContent": json.dumps(inner, separators=(",", ":")),
    }


def public_preview(outer):
    preview = json.loads(json.dumps(outer))
    preview["AuthToken"] = "<redacted>"
    try:
        inner = json.loads(preview["MessageContent"])
        if inner.get("PlayerId") != "*":
            inner["PlayerId"] = "<redacted>"
        preview["MessageContent"] = json.dumps(inner, separators=(",", ":"))
    except (TypeError, ValueError):
        pass
    return preview
