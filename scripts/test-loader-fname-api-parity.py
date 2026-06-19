#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LoaderFNameApiParityTests(unittest.TestCase):
    SOURCES = {
        "linux-client": ROOT / "tools/linux-client-loader/dune_client_probe_loader.c",
        "linux-server": ROOT / "tools/linux-server-loader/dune_server_probe_loader.c",
        "windows-client": ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c",
    }

    DOCS = (
        ROOT / "docs/client-loader-support.md",
        ROOT / "docs/linux-client-loader.md",
        ROOT / "docs/windows-client-loader.md",
        ROOT / "docs/ue4ss-linux-loader-evaluation.md",
    )

    def test_all_targets_expose_lua_fname_decode_api(self):
        required = (
            "push_lua_fname_from_indices",
            "lua_decode_fname_callback",
            '"DecodeFName"',
            "active_lua_fname_resolver_available",
            "decode_ue_fname",
            "IsDecoded",
            "ComparisonIndex",
            "Number",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_lua_fname_decode_api(self):
        required = (
            "DecodeFName(index[, number])",
            "FName(index[, number])",
            "IsDecoded",
            "FNamePool",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
