#!/usr/bin/env python3
"""Deterministic, secret-safe feature activation and runtime readiness matrix."""

import datetime
import json
import pathlib
import re


SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
CANARY_STATES = {
    "runtime-proven",
    "configuration-proven",
    "operator-canary-pending",
    "external-credential-pending",
}
STATES = ("ready", "canary-pending", "disabled", "partial", "blocked", "degraded", "external-blocked")
TRUTHY = {"1", "true", "yes", "on"}


def _bounded_text(value, field, maximum):
    value = str(value or "").strip()
    if not value or len(value) > maximum:
        raise ValueError(f"feature readiness {field} must be 1-{maximum} characters")
    return value


def _env_key(value, field):
    value = str(value or "").strip()
    if not ENV_RE.fullmatch(value):
        raise ValueError(f"feature readiness {field} is not a valid environment key")
    return value


def load_catalog(path):
    path = pathlib.Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"feature readiness catalog schemaVersion must be {SCHEMA_VERSION}")
    rows = data.get("features")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError("feature readiness catalog must contain 1-128 features")
    seen = set()
    normalized = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"feature readiness feature {index} must be an object")
        unknown = set(raw) - {
            "id", "title", "group", "description", "documentation", "primaryGate",
            "gates", "credentials", "files", "services", "probe", "dependencies",
            "canary", "remediation",
        }
        if unknown:
            raise ValueError(f"feature readiness feature {index} has unknown fields: {sorted(unknown)}")
        feature_id = str(raw.get("id") or "").strip()
        if not ID_RE.fullmatch(feature_id) or feature_id in seen:
            raise ValueError(f"feature readiness feature id is invalid or duplicated: {feature_id!r}")
        seen.add(feature_id)
        gates = raw.get("gates") or []
        credentials = raw.get("credentials") or []
        files = raw.get("files") or []
        services = raw.get("services") or []
        dependencies = raw.get("dependencies") or []
        if not all(isinstance(value, str) for value in gates + credentials + services + dependencies):
            raise ValueError(f"feature readiness {feature_id} list fields must contain strings")
        gates = list(dict.fromkeys(_env_key(value, f"{feature_id}.gates") for value in gates))
        credentials = list(dict.fromkeys(_env_key(value, f"{feature_id}.credentials") for value in credentials))
        services = list(dict.fromkeys(str(value).strip() for value in services))
        if any(not SERVICE_RE.fullmatch(value) for value in services):
            raise ValueError(f"feature readiness {feature_id} has an invalid service")
        dependencies = list(dict.fromkeys(str(value).strip() for value in dependencies))
        primary = str(raw.get("primaryGate") or (gates[0] if gates else "")).strip()
        if primary:
            primary = _env_key(primary, f"{feature_id}.primaryGate")
            if primary not in gates:
                raise ValueError(f"feature readiness {feature_id} primaryGate must be in gates")
        normalized_files = []
        for file_index, file_row in enumerate(files):
            if not isinstance(file_row, dict) or set(file_row) - {"path", "minimumBytes"}:
                raise ValueError(f"feature readiness {feature_id} file {file_index} is invalid")
            relative = pathlib.PurePosixPath(_bounded_text(file_row.get("path"), f"{feature_id}.files.path", 240))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"feature readiness {feature_id} file path must be confined and relative")
            minimum = int(file_row.get("minimumBytes", 1))
            if not 0 <= minimum <= 1024 * 1024 * 1024:
                raise ValueError(f"feature readiness {feature_id} file minimumBytes is invalid")
            normalized_files.append({"path": str(relative), "minimumBytes": minimum})
        canary = str(raw.get("canary") or "configuration-proven").strip()
        if canary not in CANARY_STATES:
            raise ValueError(f"feature readiness {feature_id} canary state is invalid")
        probe = str(raw.get("probe") or "").strip()
        if probe and not ID_RE.fullmatch(probe):
            raise ValueError(f"feature readiness {feature_id} probe id is invalid")
        remediation = raw.get("remediation") or {}
        if not isinstance(remediation, dict) or set(remediation) - {"surface", "summary"}:
            raise ValueError(f"feature readiness {feature_id} remediation is invalid")
        normalized.append({
            "id": feature_id,
            "title": _bounded_text(raw.get("title"), f"{feature_id}.title", 120),
            "group": _bounded_text(raw.get("group"), f"{feature_id}.group", 80),
            "description": _bounded_text(raw.get("description"), f"{feature_id}.description", 500),
            "documentation": _bounded_text(raw.get("documentation"), f"{feature_id}.documentation", 240),
            "primaryGate": primary,
            "gates": gates,
            "credentials": credentials,
            "files": normalized_files,
            "services": services,
            "probe": probe,
            "dependencies": dependencies,
            "canary": canary,
            "remediation": {
                "surface": _bounded_text(remediation.get("surface"), f"{feature_id}.remediation.surface", 120),
                "summary": _bounded_text(remediation.get("summary"), f"{feature_id}.remediation.summary", 300),
            },
        })
    ids = {row["id"] for row in normalized}
    for row in normalized:
        missing = set(row["dependencies"]) - ids
        if missing or row["id"] in row["dependencies"]:
            raise ValueError(f"feature readiness {row['id']} has invalid dependencies: {sorted(missing)}")
    dependencies = {row["id"]: row["dependencies"] for row in normalized}
    visiting, visited = set(), set()

    def visit(feature_id):
        if feature_id in visiting:
            raise ValueError(f"feature readiness dependency cycle includes {feature_id}")
        if feature_id in visited:
            return
        visiting.add(feature_id)
        for dependency in dependencies[feature_id]:
            visit(dependency)
        visiting.remove(feature_id)
        visited.add(feature_id)

    for feature_id in dependencies:
        visit(feature_id)
    return {"schemaVersion": SCHEMA_VERSION, "features": normalized}


def _enabled(environment, key):
    return str(environment.get(key, "")).strip().lower() in TRUTHY


def _present(environment, key):
    return bool(str(environment.get(key, "")).strip())


def _service_state(services, name):
    row = services.get(name) or {}
    return str(row.get("state") or row.get("status") or "missing").strip().lower()


def evaluate(catalog, environment, *, root, services=None, probes=None, generated_at=None):
    root = pathlib.Path(root)
    services = {
        str(row.get("service") or row.get("name") or ""): row
        for row in (services or []) if isinstance(row, dict)
    }
    probes = probes or {}
    rows = []
    for feature in catalog["features"]:
        gate_checks = [{"key": key, "enabled": _enabled(environment, key)} for key in feature["gates"]]
        credential_checks = [{"key": key, "configured": _present(environment, key)} for key in feature["credentials"]]
        file_checks = []
        for requirement in feature["files"]:
            path = root / requirement["path"]
            try:
                stat = path.stat()
                regular = path.is_file() and not path.is_symlink()
                size = stat.st_size if regular else 0
            except OSError:
                regular, size = False, 0
            file_checks.append({
                "path": requirement["path"], "present": regular,
                "sizeBytes": size, "minimumBytes": requirement["minimumBytes"],
                "ready": regular and size >= requirement["minimumBytes"],
            })
        service_checks = []
        for name in feature["services"]:
            state = _service_state(services, name)
            service_checks.append({"service": name, "state": state, "ready": state in {"running", "healthy", "up"}})
        probe = probes.get(feature["probe"]) if feature["probe"] else None
        probe_check = None
        if feature["probe"]:
            if isinstance(probe, dict):
                probe_check = {
                    "id": feature["probe"], "ready": bool(probe.get("ready", probe.get("ok"))),
                    "state": str(probe.get("state") or ("ready" if probe.get("ready", probe.get("ok")) else "failed"))[:80],
                    "detail": str(probe.get("detail") or probe.get("error") or "")[:500],
                }
            else:
                probe_check = {"id": feature["probe"], "ready": False, "state": "missing", "detail": "runtime probe was not supplied"}
        enabled_count = sum(1 for check in gate_checks if check["enabled"])
        active = not gate_checks or bool(enabled_count)
        primary_enabled = not feature["primaryGate"] or _enabled(environment, feature["primaryGate"])
        all_gates = enabled_count == len(gate_checks)
        credentials_ready = all(check["configured"] for check in credential_checks)
        artifacts_ready = all(check["ready"] for check in file_checks)
        services_ready = all(check["ready"] for check in service_checks)
        probe_ready = probe_check is None or probe_check["ready"]
        external_missing = [check["key"] for check in credential_checks if not check["configured"]]
        if not primary_enabled and not active:
            state = "disabled"
        elif not primary_enabled or not all_gates:
            state = "partial"
        elif external_missing and feature["canary"] == "external-credential-pending":
            state = "external-blocked"
        elif not credentials_ready or not artifacts_ready:
            state = "blocked"
        elif not services_ready or not probe_ready:
            state = "degraded"
        elif feature["canary"] in {"operator-canary-pending", "external-credential-pending"}:
            state = "canary-pending"
        else:
            state = "ready"
        rows.append({
            **feature,
            "state": state,
            "active": active,
            "configurationReady": all_gates and credentials_ready and artifacts_ready,
            "runtimeReady": state == "ready",
            "gateChecks": gate_checks,
            "credentialChecks": credential_checks,
            "fileChecks": file_checks,
            "serviceChecks": service_checks,
            "probeCheck": probe_check,
            "missingCredentials": external_missing,
        })
    by_id = {row["id"]: row for row in rows}
    for row in rows:
        dependency_checks = [{"id": dep, "state": by_id[dep]["state"], "ready": by_id[dep]["state"] == "ready"} for dep in row["dependencies"]]
        row["dependencyChecks"] = dependency_checks
        if row["state"] in {"ready", "canary-pending"} and not all(check["ready"] for check in dependency_checks):
            row["state"] = "blocked"
            row["runtimeReady"] = False
    counts = {state: sum(1 for row in rows if row["state"] == state) for state in STATES}
    active_problem_count = sum(counts[state] for state in ("partial", "blocked", "degraded", "external-blocked"))
    overall = "ready" if active_problem_count == 0 else "attention"
    return {
        "ok": overall == "ready",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall": overall,
        "summary": {
            **counts,
            "total": len(rows),
            "active": sum(1 for row in rows if row["active"]),
            "activeProblems": active_problem_count,
        },
        "features": rows,
        "semantics": {
            "ready": "enabled, configured, artifact/service/runtime checks passed, and live canary proven where required",
            "canary-pending": "implementation is loaded and configured but its explicit operator/provider canary is not proven",
            "disabled": "optional feature is intentionally inactive",
            "partial": "only part of the feature's required gate set is active",
            "blocked": "enabled feature is missing a required artifact, credential, or dependency",
            "degraded": "configuration is present but a required service or runtime probe is unhealthy",
            "external-blocked": "enabled integration still needs an external provider credential",
        },
    }


def prometheus(status):
    summary = status.get("summary") or {}
    lines = [
        f"dash_feature_readiness_ok {1 if status.get('ok') else 0}",
        f"dash_feature_readiness_total {int(summary.get('total') or 0)}",
        f"dash_feature_readiness_active {int(summary.get('active') or 0)}",
        f"dash_feature_readiness_active_problems {int(summary.get('activeProblems') or 0)}",
    ]
    for state in STATES:
        lines.append(f"dash_feature_readiness_{state.replace('-', '_')} {int(summary.get(state) or 0)}")
    return "\n".join(lines) + "\n"
