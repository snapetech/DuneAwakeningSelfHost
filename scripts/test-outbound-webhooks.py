#!/usr/bin/env python3

import hashlib
import hmac
import http.server
import json
import pathlib
import socketserver
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "admin"))
import outbound_webhooks


class Receiver(http.server.BaseHTTPRequestHandler):
    attempts = 0
    requests = []
    redirect_hits = 0

    def do_POST(self):
        if self.path == "/redirected":
            Receiver.redirect_hits += 1
            self.send_response(204)
            self.end_headers()
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        Receiver.attempts += 1
        Receiver.requests.append((self.path, dict(self.headers), body))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/redirected")
            self.end_headers()
        elif Receiver.attempts == 1:
            self.send_response(500)
            self.end_headers()
        else:
            self.send_response(204)
            self.end_headers()

    def log_message(self, *_args):
        return


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class WebhookTests(unittest.TestCase):
    def setUp(self):
        Receiver.attempts = 0
        Receiver.requests = []
        Receiver.redirect_hits = 0
        self.server = ThreadedServer(("127.0.0.1", 0), Receiver)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.secret = "s" * 48

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def config(self, path="/hook", fmt="dash", events=None):
        config = self.root / "webhooks.json"
        config.write_text(json.dumps({
            "version": 1,
            "endpoints": [{
                "id": "test_receiver",
                "url": f"http://127.0.0.1:{self.server.server_port}{path}",
                "format": fmt,
                "enabled": True,
                "secret": self.secret,
                "events": events or ["backup-*", "!backup-secret"],
            }],
        }), encoding="utf-8")
        config.chmod(0o600)
        return config

    def dispatcher(self, config, max_attempts=3):
        return outbound_webhooks.Dispatcher(
            config,
            self.root / "state",
            enabled=True,
            allow_http=True,
            max_attempts=max_attempts,
            sleep=lambda _seconds: None,
        )

    def test_retry_signature_and_recursive_redaction(self):
        dispatcher = self.dispatcher(self.config())
        results = dispatcher.deliver_now({
            "ts": "2026-07-15T00:00:00Z",
            "action": "backup-create-full",
            "ok": True,
            "nested": {"apiToken": "do-not-send", "safe": "value"},
        })
        self.assertEqual(results[0]["status"], "delivered")
        self.assertEqual(results[0]["attempts"], 2)
        self.assertEqual(len(Receiver.requests), 2)
        _, headers, body = Receiver.requests[-1]
        headers = {key.lower(): value for key, value in headers.items()}
        timestamp = headers["x-dash-timestamp"]
        expected = hmac.new(self.secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["x-dash-signature"], f"sha256={expected}")
        decoded = json.loads(body)
        self.assertEqual(decoded["payload"]["nested"]["apiToken"], "[redacted]")
        self.assertNotIn("do-not-send", body.decode())
        self.assertTrue((self.root / "state" / "delivery.jsonl").exists())

    def test_filters_and_discord_shape(self):
        dispatcher = self.dispatcher(self.config(fmt="discord"))
        self.assertEqual(dispatcher.deliver_now({"action": "player-write", "ok": True}), [])
        self.assertEqual(dispatcher.deliver_now({"action": "backup-secret", "ok": True}), [])
        result = dispatcher.deliver_now({"action": "backup-verify", "ok": False})
        self.assertEqual(result[0]["status"], "delivered")
        body = json.loads(Receiver.requests[-1][2])
        self.assertIn("content", body)
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        self.assertEqual(body["embeds"][0]["color"], 0xB22222)

    def test_redirect_is_not_followed(self):
        dispatcher = self.dispatcher(self.config(path="/redirect"), max_attempts=1)
        result = dispatcher.deliver_now({"action": "backup-test", "ok": True})
        self.assertEqual(result[0]["status"], "failed")
        self.assertEqual(result[0]["statusCode"], 302)
        self.assertEqual(Receiver.redirect_hits, 0)

    def test_config_rejects_short_secrets_and_userinfo(self):
        config = self.config()
        data = json.loads(config.read_text())
        data["endpoints"][0]["secret"] = "short"
        config.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            outbound_webhooks.load_config(config)
        data["endpoints"][0]["secret"] = self.secret
        data["endpoints"][0]["url"] = "https://user:pass@example.invalid/hook"
        config.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            outbound_webhooks.load_config(config)

    def test_config_rejects_group_readable_secret_file(self):
        config = self.config()
        config.chmod(0o640)
        with self.assertRaisesRegex(ValueError, "0600"):
            outbound_webhooks.load_config(config)


if __name__ == "__main__":
    unittest.main()
