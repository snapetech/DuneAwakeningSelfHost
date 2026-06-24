#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderObjectAddressApiParityTests(unittest.TestCase):
    SOURCES = {
        "linux-client": REPO_ROOT / "tools/linux-client-loader/dune_client_probe_loader.c",
        "linux-server": REPO_ROOT / "tools/linux-server-loader/dune_server_probe_loader.c",
        "windows-client": REPO_ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c",
    }

    SMOKES = {
        "linux-client": REPO_ROOT / "scripts/smoke-linux-client-loader.sh",
        "linux-server": REPO_ROOT / "scripts/smoke-linux-server-loader.sh",
        "windows-client": REPO_ROOT / "scripts/smoke-windows-client-loader-lua.sh",
    }

    DOCS = (
        REPO_ROOT / "docs/client-loader-support.md",
        REPO_ROOT / "docs/linux-client-loader.md",
        REPO_ROOT / "docs/windows-client-loader.md",
        REPO_ROOT / "docs/ue4ss-linux-loader-evaluation.md",
    )

    def test_all_targets_export_address_lookup_globals(self):
        required = (
            "lua_get_object_from_address_callback",
            "find_lua_object_by_address(address)",
            "GetObjectFromAddress",
            "FindObjectByAddress",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_require_both_address_lookup_aliases(self):
        required = (
            "GetObjectFromAddress(o.Address)",
            "FindObjectByAddress(o:GetAddress())",
            "byAddr.Address==o.Address",
            "byAddrAlias.Address==o.Address",
        )
        for target, smoke in self.SMOKES.items():
            with self.subTest(target=target):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_address_lookup_surface(self):
        required = ("GetObjectFromAddress", "FindObjectByAddress")
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
