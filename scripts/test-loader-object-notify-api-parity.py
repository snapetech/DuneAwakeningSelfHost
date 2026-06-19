#!/usr/bin/env python3
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LoaderObjectNotifyApiParityTests(unittest.TestCase):
    SOURCES = {
        "linux-client": REPO_ROOT / "tools/linux-client-loader/dune_client_probe_loader.c",
        "linux-server": REPO_ROOT / "tools/linux-server-loader/dune_server_probe_loader.c",
        "windows-client": REPO_ROOT / "tools/windows-client-loader/dune_win_client_probe_loader.c",
    }

    DOCS = (
        REPO_ROOT / "docs/client-loader-support.md",
        REPO_ROOT / "docs/linux-client-loader.md",
        REPO_ROOT / "docs/windows-client-loader.md",
        REPO_ROOT / "docs/ue4ss-linux-loader-evaluation.md",
    )

    def test_all_targets_prove_notify_on_new_object_before_construction(self):
        required = (
            "NotifyOnNewObject",
            "StaticConstructObject",
            "ConstructedProbe",
            "notifyOnNewObjectCallbacks",
            "notifyOnNewObjectResult",
            "notifyOnNewObjectStatus",
            "lua_notify_on_new_object_callbacks == 1",
            "lua_notify_on_new_object_result == 17",
            "lua_notify_on_new_object_status == 0",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_notify_on_new_object_self_test_proof(self):
        required = (
            "NotifyOnNewObject",
            "StaticConstructObject",
            "notifyOnNewObjectCallbacks=1",
            "notifyOnNewObjectResult=17",
            "notifyOnNewObjectStatus=0",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
