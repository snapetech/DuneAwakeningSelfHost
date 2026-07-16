#!/usr/bin/env python3
"""Bounded, signed outbound delivery for DASH audit events."""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import os
import pathlib
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|credential|private.?key|authorization|cookie",
    re.IGNORECASE,
)
MAX_STRING = 4000
MAX_LIST = 500
DEFAULT_EVENTS = ["*", "!auth-*", "!discord-adapter-read"]


def sanitize(value, depth=0):
    if depth > 12:
        return "[depth-limit]"
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:500]:
            key = str(key)[:200]
            result[key] = "[redacted]" if SENSITIVE_KEY.search(key) else sanitize(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth + 1) for item in list(value)[:MAX_LIST]]
    if isinstance(value, str):
        return value[:MAX_STRING]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_STRING]


def event_matches(event_name, patterns):
    patterns = [str(item).strip() for item in (patterns or DEFAULT_EVENTS) if str(item).strip()]
    excluded = any(fnmatch.fnmatchcase(event_name, pattern[1:]) for pattern in patterns if pattern.startswith("!"))
    included = any(fnmatch.fnmatchcase(event_name, pattern) for pattern in patterns if not pattern.startswith("!"))
    return included and not excluded


def load_config(path):
    path = pathlib.Path(path)
    if not path.exists():
        return {"version": 1, "endpoints": []}
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("webhook config contains secret URLs/keys and must use mode 0600")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("endpoints"), list):
        raise ValueError("webhook config must use version 1 and an endpoints array")
    seen = set()
    normalized = []
    for raw in data["endpoints"]:
        if not isinstance(raw, dict):
            raise ValueError("each webhook endpoint must be an object")
        endpoint = dict(raw)
        endpoint_id = str(endpoint.get("id", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", endpoint_id):
            raise ValueError(f"invalid webhook endpoint id: {endpoint_id!r}")
        if endpoint_id in seen:
            raise ValueError(f"duplicate webhook endpoint id: {endpoint_id}")
        seen.add(endpoint_id)
        parsed = urllib.parse.urlparse(str(endpoint.get("url", "")))
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"endpoint {endpoint_id} must have an http(s) URL without URL userinfo")
        if endpoint.get("format", "dash") not in ("dash", "discord"):
            raise ValueError(f"endpoint {endpoint_id} format must be dash or discord")
        secret = str(endpoint.get("secret", ""))
        if len(secret.encode("utf-8")) < 32:
            raise ValueError(f"endpoint {endpoint_id} signing secret must be at least 32 bytes")
        endpoint["id"] = endpoint_id
        endpoint["url"] = urllib.parse.urlunparse(parsed)
        endpoint["secret"] = secret
        endpoint["events"] = endpoint.get("events") or DEFAULT_EVENTS
        endpoint["enabled"] = bool(endpoint.get("enabled", True))
        endpoint["format"] = endpoint.get("format", "dash")
        endpoint["minIntervalSeconds"] = max(0.0, min(float(endpoint.get("minIntervalSeconds", 0)), 60.0))
        normalized.append(endpoint)
    return {"version": 1, "endpoints": normalized}


def public_endpoint(endpoint):
    parsed = urllib.parse.urlparse(endpoint["url"])
    origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        origin += f":{parsed.port}"
    return {
        "id": endpoint["id"],
        "enabled": endpoint["enabled"],
        "format": endpoint["format"],
        "events": endpoint["events"],
        "origin": origin,
        "minIntervalSeconds": endpoint["minIntervalSeconds"],
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Dispatcher:
    def __init__(
        self,
        config_path,
        state_dir,
        enabled=False,
        timeout=5.0,
        max_attempts=3,
        queue_size=1000,
        allow_http=False,
        sleep=time.sleep,
        opener=None,
    ):
        self.config_path = pathlib.Path(config_path)
        self.state_dir = pathlib.Path(state_dir)
        self.enabled = bool(enabled)
        self.timeout = max(0.1, min(float(timeout), 30.0))
        self.max_attempts = max(1, min(int(max_attempts), 8))
        self.allow_http = bool(allow_http)
        self.sleep = sleep
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.queue = queue.Queue(maxsize=max(1, min(int(queue_size), 10000)))
        self._thread = None
        self._lock = threading.Lock()
        self._last_delivery = {}
        self._dropped = 0
        self._delivered = 0
        self._failed = 0
        self._config_error = None

    def _config(self):
        try:
            config = load_config(self.config_path)
            self._config_error = None
            return config
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._config_error = str(exc)[:500]
            return {"version": 1, "endpoints": []}

    def status(self):
        config = self._config()
        mode = None
        try:
            mode = oct(self.config_path.stat().st_mode & 0o777)
        except OSError:
            pass
        return {
            "enabled": self.enabled,
            "configPath": str(self.config_path),
            "configExists": self.config_path.exists(),
            "configMode": mode,
            "configError": self._config_error,
            "endpoints": [public_endpoint(item) for item in config["endpoints"]],
            "queued": self.queue.qsize(),
            "queueLimit": self.queue.maxsize,
            "delivered": self._delivered,
            "failed": self._failed,
            "dropped": self._dropped,
            "maxAttempts": self.max_attempts,
            "timeoutSeconds": self.timeout,
        }

    def enqueue(self, event):
        if not self.enabled:
            return False
        safe_event = sanitize(event)
        try:
            self.queue.put_nowait(safe_event)
        except queue.Full:
            self._dropped += 1
            self._record({"status": "dropped", "reason": "queue-full", "event": safe_event.get("action")})
            return False
        self._ensure_worker()
        return True

    def _ensure_worker(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._worker, name="dash-webhooks", daemon=True)
            self._thread.start()

    def _worker(self):
        while True:
            try:
                event = self.queue.get(timeout=1.0)
            except queue.Empty:
                return
            try:
                self.deliver_now(event)
            finally:
                self.queue.task_done()

    def deliver_now(self, event):
        event = sanitize(event)
        delivery_id = str(uuid.uuid4())
        name = str(event.get("action") or "unknown")[:200]
        results = []
        for endpoint in self._config()["endpoints"]:
            if not endpoint["enabled"] or not event_matches(name, endpoint["events"]):
                continue
            result = self._deliver(endpoint, name, event, delivery_id)
            results.append(result)
        return results

    def _envelope(self, name, event, delivery_id):
        return {
            "version": 1,
            "id": delivery_id,
            "event": name,
            "occurredAt": event.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "dash-admin-panel",
            "server": socket.gethostname(),
            "payload": event,
        }

    def _body(self, endpoint, envelope):
        if endpoint["format"] == "discord":
            outcome = "succeeded" if envelope["payload"].get("ok", True) else "failed"
            description = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"))[:3500]
            payload = {
                "username": "DASH",
                "content": f"DASH event `{envelope['event']}` {outcome}",
                "embeds": [{
                    "title": envelope["event"][:256],
                    "description": f"```json\n{description}\n```",
                    "color": 0x2E8B57 if outcome == "succeeded" else 0xB22222,
                    "footer": {"text": f"delivery {envelope['id']}"},
                    "timestamp": envelope["occurredAt"],
                }],
                "allowed_mentions": {"parse": []},
            }
        else:
            payload = envelope
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _deliver(self, endpoint, name, event, delivery_id):
        parsed = urllib.parse.urlparse(endpoint["url"])
        if parsed.scheme != "https" and not self.allow_http:
            result = {"endpoint": endpoint["id"], "event": name, "delivery": delivery_id, "status": "failed", "reason": "http-disabled"}
            self._failed += 1
            self._record(result)
            return result
        minimum = endpoint["minIntervalSeconds"]
        elapsed = time.monotonic() - self._last_delivery.get(endpoint["id"], 0.0)
        if minimum and elapsed < minimum:
            self.sleep(minimum - elapsed)
        envelope = self._envelope(name, event, delivery_id)
        body = self._body(endpoint, envelope)
        timestamp = str(int(time.time()))
        signature = hmac.new(endpoint["secret"].encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DASH-Webhook/1",
            "X-DASH-Delivery": delivery_id,
            "X-DASH-Event": name,
            "X-DASH-Timestamp": timestamp,
            "X-DASH-Signature": f"sha256={signature}",
        }
        reason = "unknown"
        status_code = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(endpoint["url"], data=body, headers=headers, method="POST")
            try:
                response = self.opener.open(request, timeout=self.timeout)
                try:
                    status_code = getattr(response, "status", response.getcode())
                    response.read(4096)
                finally:
                    response.close()
                if 200 <= status_code < 300:
                    self._last_delivery[endpoint["id"]] = time.monotonic()
                    self._delivered += 1
                    result = {"endpoint": endpoint["id"], "event": name, "delivery": delivery_id, "status": "delivered", "statusCode": status_code, "attempts": attempt}
                    self._record(result)
                    return result
                reason = f"http-{status_code}"
            except urllib.error.HTTPError as exc:
                status_code = exc.code
                reason = f"http-{exc.code}"
                exc.close()
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                reason = type(exc).__name__
            if attempt < self.max_attempts:
                self.sleep(min(2 ** (attempt - 1), 8))
        self._failed += 1
        result = {"endpoint": endpoint["id"], "event": name, "delivery": delivery_id, "status": "failed", "statusCode": status_code, "attempts": self.max_attempts, "reason": reason}
        self._record(result)
        return result

    def _record(self, result):
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            record = dict(result, ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            with (self.state_dir / "delivery.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            pass


def from_environment(root, state_dir):
    truthy = ("1", "true", "yes", "on")
    return Dispatcher(
        os.environ.get("DUNE_WEBHOOK_CONFIG", str(pathlib.Path(root) / "config" / "outbound-webhooks.json")),
        state_dir,
        enabled=os.environ.get("DUNE_WEBHOOKS_ENABLED", "false").lower() in truthy,
        timeout=os.environ.get("DUNE_WEBHOOK_TIMEOUT_SECONDS", "5"),
        max_attempts=os.environ.get("DUNE_WEBHOOK_MAX_ATTEMPTS", "3"),
        queue_size=os.environ.get("DUNE_WEBHOOK_QUEUE_SIZE", "1000"),
        allow_http=os.environ.get("DUNE_WEBHOOK_ALLOW_HTTP", "false").lower() in truthy,
    )
