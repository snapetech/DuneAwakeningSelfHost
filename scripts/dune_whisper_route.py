#!/usr/bin/env python3
import re


FLS_ID_RE = re.compile(r"^[0-9A-Fa-f]{16}$")


def normalize_fls_id(fls_id):
    value = str(fls_id or "").strip()
    if not value:
        return ""
    return value.upper() if FLS_ID_RE.fullmatch(value) else value


def whisper_queue_for_fls_id(fls_id):
    normalized = normalize_fls_id(fls_id)
    if not normalized:
        return ""
    return f"{normalized}_queue"


def whisper_route_for_fls_id(fls_id):
    normalized = normalize_fls_id(fls_id)
    if not normalized:
        return {"ok": False, "error": "missing FLS id", "flsId": ""}
    return {
        "ok": True,
        "exchange": "chat.whispers",
        "routingKey": normalized,
        "queue": whisper_queue_for_fls_id(normalized),
        "channel": "Whispers",
        "derived": True,
    }
