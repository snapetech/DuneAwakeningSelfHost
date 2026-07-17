#!/usr/bin/env python3
import copy
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import public_directory

BUILDER_PATH = ROOT / "public-site/scripts/build-federated-directory.py"
SPEC = importlib.util.spec_from_file_location("build_federated_directory_test", BUILDER_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
CONFIGURATOR_PATH = ROOT / "public-site/scripts/configure-federated-directory-sources.py"
CONFIGURATOR_SPEC = importlib.util.spec_from_file_location("configure_federated_directory_sources_test", CONFIGURATOR_PATH)
configurator = importlib.util.module_from_spec(CONFIGURATOR_SPEC)
CONFIGURATOR_SPEC.loader.exec_module(configurator)


NOW = dt.datetime(2026, 7, 17, 0, 0, tzinfo=dt.timezone.utc)


def environment(root, **updates):
    values = {
        "DUNE_ROOT": str(root),
        "DUNE_PUBLIC_DIRECTORY_ENABLED": "true",
        "DUNE_PUBLIC_DIRECTORY_ENTRY_URL": "https://dune.example.test/directory-entry.json",
        "DUNE_PUBLIC_SITE_URL": "https://dune.example.test/",
        "DUNE_PUBLIC_DIRECTORY_REGION": "North America",
        "DUNE_PUBLIC_DIRECTORY_CAPACITY": "40",
        "DUNE_PUBLIC_DIRECTORY_TTL_SECONDS": "180",
        "DUNE_PUBLIC_DIRECTORY_DISCORD_INVITE": "https://discord.gg/Example_1",
        "PUBLIC_SERVER_NAME": "Sietch Test",
        "PUBLIC_SERVER_DESCRIPTION": "A signed test community.",
        "DUNE_IMAGE_TAG": "1.2.3",
    }
    values.update(updates)
    return values


def snapshot(players=3):
    return {
        "ok": True,
        "onlineCount": players,
        "mapHealth": {"online": 2, "warming": 1, "onDemand": 5, "offline": 0, "total": 8},
        "mapStatus": [{"map": "Survival_1"}, {"map": "Survival_1"}, {"map": "Overmap"}],
    }


def resign(document, private_key):
    unsigned = {key: value for key, value in document.items() if key != "signature"}
    payload = public_directory.canonical(unsigned)
    document["signature"] = {
        "algorithm": public_directory.ALGORITHM,
        "payloadSha256": hashlib.sha256(payload).hexdigest(),
        "valueBase64": base64.b64encode(public_directory.sign_payload(private_key, payload)).decode("ascii"),
    }
    return document


class PublicDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.config = public_directory.public_config(environment(self.root), root=self.root)
        self.entry = public_directory.build_entry(snapshot(), self.config, now=NOW)

    def tearDown(self):
        self.temporary.cleanup()

    def test_config_defaults_private_and_requires_complete_public_contract_when_enabled(self):
        private = public_directory.public_config({}, root=self.root)
        self.assertFalse(private["enabled"])
        with self.assertRaisesRegex(ValueError, "entry URL"):
            public_directory.public_config(environment(self.root, DUNE_PUBLIC_DIRECTORY_ENTRY_URL=""), root=self.root)
        with self.assertRaisesRegex(ValueError, "region"):
            public_directory.public_config(environment(self.root, DUNE_PUBLIC_DIRECTORY_REGION="Moon"), root=self.root)
        with self.assertRaisesRegex(ValueError, "TTL"):
            public_directory.public_config(environment(self.root, DUNE_PUBLIC_DIRECTORY_TTL_SECONDS="59"), root=self.root)
        with self.assertRaisesRegex(ValueError, "capacity"):
            public_directory.public_config(environment(self.root, DUNE_PUBLIC_DIRECTORY_CAPACITY="0"), root=self.root)

    def test_urls_discord_and_public_text_are_confined(self):
        for value in ("http://example.com/entry.json", "https://user@example.com/x", "https://127.0.0.1/x", "https://example.com/x?q=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                public_directory.normalize_https_url(value, "test", required=True)
        self.assertEqual("https://discord.gg/abc_DEF", public_directory.normalize_discord_invite("https://discord.com/invite/abc_DEF"))
        with self.assertRaises(ValueError):
            public_directory.normalize_discord_invite("https://evil.example/invite/abc")
        normalized = public_directory.public_config(environment(self.root, PUBLIC_SERVER_NAME="x\ncommunity"), root=self.root)
        self.assertEqual("x community", normalized["name"])
        with self.assertRaises(ValueError):
            public_directory.public_config(environment(self.root, PUBLIC_SERVER_NAME="x\x00secret"), root=self.root)

    def test_signed_entry_is_secret_free_current_and_identity_bound(self):
        verified = public_directory.verify_entry(self.entry, expected_url=self.config["entryUrl"], now=NOW)
        self.assertEqual("online", verified["status"]["state"])
        self.assertEqual(2, verified["status"]["sietches"])
        self.assertEqual(3, verified["status"]["playersOnline"])
        rendered = json.dumps(verified)
        self.assertNotIn("PRIVATE" + " KEY", rendered)
        self.assertNotIn(str(self.config["keyFile"]), rendered)
        self.assertTrue(verified["serverId"].startswith("dash-"))
        public_der = base64.b64decode(verified["signingKey"]["publicKeyDerBase64"])
        signature = base64.b64decode(verified["signature"]["valueBase64"])
        self.assertEqual(public_directory.ED25519_PUBLIC_DER_BYTES, len(public_der))
        self.assertTrue(public_der.startswith(public_directory.ED25519_SPKI_PREFIX))
        self.assertEqual(public_directory.ED25519_SIGNATURE_BYTES, len(signature))

    def test_signed_but_noncanonical_or_type_confused_entries_fail(self):
        cases = []
        changed = copy.deepcopy(self.entry); changed["profile"]["name"] = "Sietch\nTest"; cases.append((changed, "name"))
        changed = copy.deepcopy(self.entry); changed["profile"]["websiteUrl"] = "https://DUNE.example.test/"; cases.append((changed, "website"))
        changed = copy.deepcopy(self.entry); changed["profile"]["discordInvite"] = "https://discord.com/invite/Example_1"; cases.append((changed, "Discord"))
        changed = copy.deepcopy(self.entry); changed["profile"]["features"].append("dynamic-maps"); cases.append((changed, "features"))
        changed = copy.deepcopy(self.entry); changed["status"]["capacity"] = "40"; cases.append((changed, "JSON integer"))
        for document, error in cases:
            resign(document, self.config["keyFile"])
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                public_directory.verify_entry(document, now=NOW)

    def test_tampering_payload_digest_signature_and_identity_fail(self):
        cases = []
        changed = copy.deepcopy(self.entry); changed["status"]["playersOnline"] = 4; cases.append(changed)
        changed = copy.deepcopy(self.entry); changed["signature"]["payloadSha256"] = "0" * 64; cases.append(changed)
        changed = copy.deepcopy(self.entry); changed["signature"]["valueBase64"] = "AAAA"; cases.append(changed)
        changed = copy.deepcopy(self.entry); changed["serverId"] = "dash-" + "0" * 64; cases.append(changed)
        for document in cases:
            with self.subTest(document=document.get("serverId")), self.assertRaises(ValueError):
                public_directory.verify_entry(document, now=NOW)

    def test_source_expiry_future_and_schema_drift_fail(self):
        with self.assertRaisesRegex(ValueError, "source URL"):
            public_directory.verify_entry(self.entry, expected_url="https://other.example.test/entry.json", now=NOW)
        with self.assertRaisesRegex(ValueError, "expired"):
            public_directory.verify_entry(self.entry, now=NOW + dt.timedelta(minutes=4))
        with self.assertRaisesRegex(ValueError, "future"):
            public_directory.verify_entry(self.entry, now=NOW - dt.timedelta(minutes=6))
        changed = copy.deepcopy(self.entry); changed["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "schema"):
            public_directory.verify_entry(changed, now=NOW)

    def test_private_key_is_mode_600_reused_and_concurrently_safe(self):
        first = self.config["keyFile"].read_bytes()
        self.assertEqual(0, stat.S_IMODE(self.config["keyFile"].stat().st_mode) & 0o077)
        second = public_directory.build_entry(snapshot(), self.config, now=NOW + dt.timedelta(seconds=1))
        self.assertEqual(first, self.config["keyFile"].read_bytes())
        self.assertEqual(self.entry["serverId"], second["serverId"])
        os.chmod(self.config["keyFile"], 0o644)
        with self.assertRaisesRegex(PermissionError, "mode-0600"):
            public_directory.build_entry(snapshot(), self.config, now=NOW)

    def test_publish_is_atomic_status_is_verifiable_and_disable_delists_by_removal(self):
        public_file = self.root / "static/directory-entry.json"
        result = public_directory.publish(snapshot(), self.config, public_file, now=NOW)
        self.assertTrue(result["published"])
        self.assertTrue(self.config["stateFile"].is_file())
        self.assertTrue(public_file.is_file())
        status = public_directory.status(self.config, now=NOW)
        self.assertTrue(status["valid"])
        metrics = public_directory.prometheus(status, now=NOW)
        self.assertIn("dash_public_directory_entry_valid 1", metrics)
        disabled = {**self.config, "enabled": False}
        public_directory.publish(snapshot(), disabled, public_file, now=NOW)
        self.assertFalse(self.config["stateFile"].exists())
        self.assertFalse(public_file.exists())

    def test_bounded_online_count_and_map_state(self):
        with self.assertRaisesRegex(ValueError, "online players"):
            public_directory.build_entry(snapshot(players=41), self.config, now=NOW)
        degraded = snapshot(); degraded["mapHealth"]["offline"] = 1
        entry = public_directory.build_entry(degraded, self.config, now=NOW)
        self.assertEqual("degraded", entry["status"]["state"])

    def test_sources_manifest_is_exact_unique_and_bounded(self):
        path = self.root / "sources.json"
        path.write_text(json.dumps({"schemaVersion": public_directory.SOURCES_SCHEMA, "sources": [{"url": self.config["entryUrl"]}]}))
        self.assertEqual([self.config["entryUrl"]], builder.load_sources(path))
        path.write_text(json.dumps({"schemaVersion": public_directory.SOURCES_SCHEMA, "sources": [{"url": self.config["entryUrl"]}, {"url": self.config["entryUrl"]}]}))
        with self.assertRaisesRegex(ValueError, "unique"):
            builder.load_sources(path)

    def test_source_configurator_is_atomic_canonical_and_replace_explicit(self):
        path = self.root / "configured-sources.json"
        first = configurator.configure(path, [self.config["entryUrl"]])
        self.assertEqual(public_directory.SOURCES_SCHEMA, first["schemaVersion"])
        self.assertEqual([self.config["entryUrl"]], builder.load_sources(path))
        with self.assertRaises(FileExistsError):
            configurator.configure(path, ["https://other.example.test/directory-entry.json"])
        replacement = configurator.configure(path, ["https://OTHER.example.test/directory-entry.json"], replace=True)
        self.assertEqual("https://other.example.test/directory-entry.json", replacement["sources"][0]["url"])
        with self.assertRaisesRegex(ValueError, "unique"):
            configurator.configure(path, [self.config["entryUrl"], self.config["entryUrl"]], replace=True)
        with self.assertRaisesRegex(ValueError, "absolute"):
            configurator.configure("relative.json", [self.config["entryUrl"]])

    def test_fetch_pins_a_prevalidated_public_address_and_bounds_response(self):
        payload = json.dumps(self.entry).encode()
        captured = {}

        class Response:
            status = 200
            def getheader(self, name):
                return "application/json" if name == "Content-Type" else str(len(payload)) if name == "Content-Length" else None
            def read(self, limit):
                self.limit = limit
                return payload

        class Connection:
            def __init__(self, host, address, timeout):
                captured.update(host=host, address=address, timeout=timeout)
            def request(self, method, path, headers):
                captured.update(method=method, path=path, headers=headers)
            def getresponse(self): return Response()
            def close(self): captured["closed"] = True

        with mock.patch.object(public_directory, "require_public_dns", return_value=["203.0.113.10"]):
            result = public_directory.fetch_entry(self.config["entryUrl"], timeout=7, connection_factory=Connection)
        self.assertEqual(self.entry, result)
        self.assertEqual("203.0.113.10", captured["address"])
        self.assertEqual("dune.example.test", captured["host"])
        self.assertEqual("/directory-entry.json", captured["path"])
        self.assertTrue(captured["closed"])

    def test_catalog_is_deterministic_and_isolates_bad_or_duplicate_sources(self):
        second_config = public_directory.public_config(environment(
            self.root / "second",
            DUNE_PUBLIC_DIRECTORY_ENTRY_URL="https://second.example.test/directory-entry.json",
            DUNE_PUBLIC_SITE_URL="https://second.example.test/",
            PUBLIC_SERVER_NAME="Another Sietch",
            DUNE_PUBLIC_DIRECTORY_REGION="Europe",
        ), root=self.root / "second")
        second = public_directory.build_entry(snapshot(7), second_config, now=NOW)
        documents = {
            self.config["entryUrl"]: self.entry,
            second_config["entryUrl"]: second,
        }

        def fetcher(url, timeout=5):
            if "bad" in url:
                raise ValueError("untrusted response")
            return documents[url]

        sources = [second_config["entryUrl"], "https://bad.example.test/directory-entry.json", self.config["entryUrl"]]
        catalog = builder.build(sources, fetcher=fetcher, now=NOW)
        self.assertEqual({"configured": 3, "listed": 2, "rejected": 1}, catalog["stats"])
        self.assertEqual(["Europe", "North America"], [row["profile"]["region"] for row in catalog["servers"]])
        self.assertEqual("untrusted response", catalog["rejected"][0]["error"])

    def test_public_directory_frontend_has_filters_reduced_motion_and_no_html_sinks(self):
        html = (ROOT / "public-site/directory/index.html").read_text()
        css = (ROOT / "public-site/directory/directory.css").read_text()
        script = (ROOT / "public-site/directory/directory.js").read_text()
        for control in ('id="search"', 'id="region"', 'id="state"', 'id="sort"', 'id="scan"'):
            self.assertIn(control, html)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("textContent", script)
        self.assertIn("crypto.subtle.verify", script)
        self.assertIn("listing identity mismatch", script)
        self.assertIn("listing freshness invalid", script)
        self.assertIn("listing schema is invalid", script)
        self.assertIn("hasExactKeys", script)
        self.assertIn("safeHttps", script)
        self.assertIn("Promise.all(catalog.servers.map(measure))", script)
        self.assertNotIn("void Promise.all(servers.map(measure))", script)
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            self.assertNotIn(sink, script)


if __name__ == "__main__":
    unittest.main()
