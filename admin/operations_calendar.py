#!/usr/bin/env python3
"""Pure operations-calendar normalization, collision analysis, and metrics."""

import datetime
import hashlib
import json
import math
import time


SCHEMA = "dash-operations-calendar/v1"
IMPACTS = {"communication", "planning", "preparatory", "recovery", "disruptive", "exclusion"}
SEVERITIES = {"critical", "warning"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def iso(value):
    return datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    if isinstance(value, bool):
        raise ValueError("calendar time cannot be boolean")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        result = parsed.timestamp()
    if not math.isfinite(result) or result <= 0:
        raise ValueError("calendar time is invalid")
    return result


def bounded(value, maximum, label):
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ValueError(f"{label} is invalid")
    return text


def normalize_window(raw):
    if not isinstance(raw, dict):
        raise ValueError("calendar window must be an object")
    start = epoch(raw.get("startsAt", raw.get("start")))
    end = epoch(raw.get("endsAt", raw.get("end")))
    if end <= start or end - start > 31 * 86400:
        raise ValueError("calendar window duration is invalid")
    impact = str(raw.get("impact") or "")
    if impact not in IMPACTS:
        raise ValueError("calendar window impact is invalid")
    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("calendar window metadata must be an object")
    try:
        metadata_json = canonical(metadata)
    except (TypeError, ValueError) as exc:
        raise ValueError("calendar window metadata is not JSON-serializable") from exc
    if len(metadata_json.encode("utf-8")) > 8192:
        raise ValueError("calendar window metadata is too large")
    return {
        "id": bounded(raw.get("id"), 180, "calendar window id"),
        "source": bounded(raw.get("source"), 80, "calendar window source"),
        "title": bounded(raw.get("title"), 180, "calendar window title"),
        "impact": impact,
        "startsAt": start,
        "startsAtIso": iso(start),
        "endsAt": end,
        "endsAtIso": iso(end),
        "durationSeconds": int(round(end - start)),
        "target": str(raw.get("target") or "")[:120],
        "recurring": bool(raw.get("recurring")),
        "metadata": metadata,
    }


def overlap_seconds(left, right):
    return max(0.0, min(left["endsAt"], right["endsAt"]) - max(left["startsAt"], right["startsAt"]))


def conflict_severity(left, right):
    if overlap_seconds(left, right) <= 0 or "exclusion" in {left["impact"], right["impact"]}:
        return None
    impacts = {left["impact"], right["impact"]}
    if impacts == {"disruptive"} or impacts == {"disruptive", "recovery"}:
        return "critical"
    if impacts == {"recovery"}:
        return "warning"
    if "disruptive" in impacts and "preparatory" in impacts:
        return "warning"
    return None


def analyze(windows, *, now=None, horizon_seconds=14 * 86400, source_errors=None):
    now = time.time() if now is None else float(now)
    horizon_seconds = max(3600, min(int(horizon_seconds), 31 * 86400))
    horizon_end = now + horizon_seconds
    normalized = []
    errors = []
    for raw in source_errors or []:
        if isinstance(raw, dict):
            source = str(raw.get("source") or "unknown")[:80]
            error = str(raw.get("error") or "calendar source failed")[:500]
        else:
            source = "unknown"
            error = str(raw or "calendar source failed")[:500]
        errors.append({"source": source, "error": error})
    seen = set()
    for index, raw in enumerate(windows or []):
        try:
            row = normalize_window(raw)
            if row["id"] in seen:
                raise ValueError("calendar window id is duplicated")
            seen.add(row["id"])
            if row["endsAt"] > now and row["startsAt"] < horizon_end:
                normalized.append(row)
        except (TypeError, ValueError) as exc:
            errors.append({"index": index, "error": str(exc)})
    normalized.sort(key=lambda row: (row["startsAt"], row["endsAt"], row["id"]))
    conflicts = []
    for index, left in enumerate(normalized):
        for right in normalized[index + 1:]:
            if right["startsAt"] >= left["endsAt"]:
                break
            severity = conflict_severity(left, right)
            if severity not in SEVERITIES:
                continue
            overlap = int(round(overlap_seconds(left, right)))
            conflicts.append({
                "id": "calendar-conflict-" + hashlib.sha256(f"{left['id']}\0{right['id']}".encode()).hexdigest()[:24],
                "severity": severity,
                "leftId": left["id"], "rightId": right["id"],
                "startsAt": max(left["startsAt"], right["startsAt"]),
                "startsAtIso": iso(max(left["startsAt"], right["startsAt"])),
                "overlapSeconds": overlap,
                "reason": (
                    "a disruptive operation overlaps recovery work" if {left["impact"], right["impact"]} == {"disruptive", "recovery"}
                    else "two disruptive operations overlap" if left["impact"] == right["impact"] == "disruptive"
                    else "two recovery operations overlap" if left["impact"] == right["impact"] == "recovery"
                    else "preparatory work overlaps a disruptive operation"
                ),
            })
    exclusions = [row for row in normalized if row["impact"] == "exclusion" and row["metadata"].get("maintenanceExclusion")]
    coverage_findings = []
    for row in normalized:
        if row["impact"] != "disruptive" or not row["metadata"].get("execute", True):
            continue
        covered = any(window["startsAt"] <= row["startsAt"] and window["endsAt"] >= row["endsAt"] for window in exclusions)
        if not covered:
            coverage_findings.append({
                "id": "calendar-coverage-" + hashlib.sha256(row["id"].encode()).hexdigest()[:24],
                "severity": "warning", "windowId": row["id"],
                "startsAt": row["startsAt"], "startsAtIso": row["startsAtIso"],
                "reason": "executing disruptive maintenance is not fully covered by a planned SLO maintenance exclusion",
            })
    next_window = next((row for row in normalized if row["startsAt"] >= now), None)
    current = [row for row in normalized if row["startsAt"] <= now < row["endsAt"]]
    payload = {
        "schemaVersion": SCHEMA, "generatedAt": iso(now),
        "horizonSeconds": horizon_seconds, "horizonEndsAt": horizon_end,
        "horizonEndsAtIso": iso(horizon_end), "windows": normalized,
        "current": current, "next": next_window, "conflicts": conflicts,
        "coverageFindings": coverage_findings, "errors": errors,
        "summary": {
            "windows": len(normalized), "current": len(current),
            "criticalConflicts": sum(row["severity"] == "critical" for row in conflicts),
            "warningConflicts": sum(row["severity"] == "warning" for row in conflicts),
            "uncoveredDisruptive": len(coverage_findings), "sourceErrors": len(errors),
        },
    }
    payload["fingerprint"] = hashlib.sha256(canonical({
        "windows": normalized, "conflicts": conflicts, "coverageFindings": coverage_findings,
        "errors": errors,
    }).encode()).hexdigest()
    payload["ok"] = not errors and not any(row["severity"] == "critical" for row in conflicts)
    return payload


def prometheus(status, *, now=None):
    now = time.time() if now is None else float(now)
    summary = status.get("summary") or {}
    next_window = status.get("next") or {}
    values = {
        "dash_operations_calendar_collector_up": int(not bool(status.get("errors"))),
        "dash_operations_calendar_windows": int(summary.get("windows") or 0),
        "dash_operations_calendar_current_windows": int(summary.get("current") or 0),
        "dash_operations_calendar_critical_conflicts": int(summary.get("criticalConflicts") or 0),
        "dash_operations_calendar_warning_conflicts": int(summary.get("warningConflicts") or 0),
        "dash_operations_calendar_uncovered_disruptive_windows": int(summary.get("uncoveredDisruptive") or 0),
        "dash_operations_calendar_next_window_timestamp_seconds": float(next_window.get("startsAt") or 0),
        "dash_operations_calendar_next_window_seconds": max(0.0, float(next_window.get("startsAt") or 0) - now) if next_window else 0.0,
    }
    return "".join(f"{name} {value}\n" for name, value in values.items())
