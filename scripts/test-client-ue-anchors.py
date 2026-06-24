#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-client-ue-anchors.py",
    ROOT / "analysis" / "summarize-client-ue-anchors.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("summarize_client_ue_anchors", SCRIPT)
ue_anchors = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ue_anchors)


class ClientUeAnchorTests(unittest.TestCase):
    def test_not_ready_without_core_groups(self):
        report = ue_anchors.summarize({"hitsByName": {"FNamePool": {"count": 1, "first": {"offset": "0x1"}, "sources": {}}}})

        self.assertFalse(report["readyForObjectDiscovery"])
        self.assertGreater(len(report["nextSteps"]), 0)
        self.assertEqual(report["groups"]["names"]["present"], 1)

    def test_ready_when_core_groups_present(self):
        hits = {
            "FNamePool": {"count": 1, "first": {"offset": "0x1"}, "sources": {}},
            "GUObjectArray": {"count": 1, "first": {"offset": "0x2"}, "sources": {}},
            "GWorld": {"count": 1, "first": {"offset": "0x3"}, "sources": {}},
            "ProcessEvent": {"count": 1, "first": {"offset": "0x4"}, "sources": {}},
            "CallFunctionByNameWithArguments": {"count": 1, "first": {"offset": "0x5"}, "sources": {}},
            "StaticLoadObject": {"count": 1, "first": {"offset": "0x6"}, "sources": {}},
            "StaticLoadClass": {"count": 1, "first": {"offset": "0x7"}, "sources": {}},
            "LoadAsset": {"count": 1, "first": {"offset": "0x8"}, "sources": {}},
            "LoadClass": {"count": 1, "first": {"offset": "0x9"}, "sources": {}},
        }
        report = ue_anchors.summarize({"hitsByName": hits})

        self.assertTrue(report["readyForObjectDiscovery"])
        self.assertTrue(report["readyForHooks"])
        self.assertEqual(report["groups"]["package"]["present"], 4)

    def test_proven_only_ignores_raw_scan_hits(self):
        hits = {
            "FNamePool": {"count": 1, "kinds": {"string": 1}, "first": {"offset": "0x1"}, "sources": {}},
            "GUObjectArray": {"count": 1, "kinds": {"string": 1}, "first": {"offset": "0x2"}, "sources": {}},
            "GWorld": {"count": 1, "kinds": {"string": 1}, "first": {"offset": "0x3"}, "sources": {}},
            "ProcessEvent": {"count": 1, "kinds": {"string": 1}, "first": {"offset": "0x4"}, "sources": {}},
        }
        report = ue_anchors.summarize({"hitsByName": hits}, proven_only=True)

        self.assertFalse(report["readyForObjectDiscovery"])
        self.assertFalse(report["readyForHooks"])
        self.assertEqual(report["groups"]["names"]["present"], 0)

    def test_proven_only_accepts_mapped_and_signature_anchors(self):
        hits = {
            "FNamePool": {"count": 1, "kinds": {"ue-anchor-signature": 1}, "first": {"offset": "0x1"}, "sources": {}},
            "GUObjectArray": {"count": 1, "kinds": {"ue-anchor": 1}, "first": {"offset": "0x2"}, "sources": {}},
            "GWorld": {"count": 1, "kinds": {"ue-anchor-signature": 1}, "first": {"offset": "0x3"}, "sources": {}},
            "ProcessEvent": {"count": 1, "kinds": {"ue-anchor-signature": 1}, "first": {"offset": "0x4"}, "sources": {}},
        }
        report = ue_anchors.summarize({"hitsByName": hits}, proven_only=True)

        self.assertTrue(report["readyForObjectDiscovery"])
        self.assertTrue(report["readyForHooks"])

    def test_alias_names_count_for_core_groups(self):
        hits = {
            "sig-core-fnamepool": {"count": 1, "first": {"offset": "0x1"}, "sources": {"scan": 1}},
            "gu-object-array-candidate": {"count": 1, "first": {"offset": "0x2"}, "sources": {"scan": 1}},
            "client-gworld": {"count": 1, "first": {"offset": "0x3"}, "sources": {"scan": 1}},
            "uobject-process-event": {"count": 1, "first": {"offset": "0x4"}, "sources": {"scan": 1}},
            "uobject-call-function-by-name-with-arguments": {"count": 1, "first": {"offset": "0x5"}, "sources": {"scan": 1}},
            "dune-static-load-object": {"count": 1, "first": {"offset": "0x6"}, "sources": {"scan": 1}},
            "uobject-static-load-class": {"count": 1, "first": {"offset": "0x7"}, "sources": {"scan": 1}},
            "load-asset-package-path": {"count": 1, "first": {"offset": "0x8"}, "sources": {"scan": 1}},
            "load-class-package-path": {"count": 1, "first": {"offset": "0x9"}, "sources": {"scan": 1}},
        }
        report = ue_anchors.summarize({"hitsByName": hits})

        self.assertTrue(report["readyForObjectDiscovery"])
        self.assertEqual(report["groups"]["names"]["anchors"][0]["matchedNames"], ["sig-core-fnamepool"])
        self.assertEqual(report["groups"]["dispatch"]["anchors"][0]["matchedNames"], ["uobject-process-event"])
        self.assertEqual(
            report["groups"]["dispatch"]["anchors"][2]["matchedNames"],
            ["uobject-call-function-by-name-with-arguments"],
        )
        self.assertEqual(report["groups"]["package"]["anchors"][0]["matchedNames"], ["dune-static-load-object"])
        self.assertEqual(report["groups"]["package"]["anchors"][1]["matchedNames"], ["uobject-static-load-class"])
        self.assertEqual(report["groups"]["package"]["anchors"][5]["matchedNames"], ["load-asset-package-path"])
        self.assertEqual(report["groups"]["package"]["anchors"][6]["matchedNames"], ["load-class-package-path"])

    def test_call_function_dispatch_anchor_does_not_open_process_event_hook_readiness(self):
        hits = {
            "FNamePool": {"count": 1, "first": {"offset": "0x1"}, "sources": {}},
            "GUObjectArray": {"count": 1, "first": {"offset": "0x2"}, "sources": {}},
            "GWorld": {"count": 1, "first": {"offset": "0x3"}, "sources": {}},
            "CallFunctionByNameWithArguments": {"count": 1, "first": {"offset": "0x5"}, "sources": {}},
        }
        report = ue_anchors.summarize({"hitsByName": hits})

        self.assertTrue(report["readyForObjectDiscovery"])
        self.assertFalse(report["readyForHooks"])

    def test_self_test_anchors_do_not_satisfy_real_anchor_groups(self):
        hits = {
            "SelfTestFNamePool": {"count": 1, "first": {"offset": "0x1"}, "sources": {}},
            "SelfTestObjectArray": {"count": 1, "first": {"offset": "0x2"}, "sources": {}},
            "SelfTestUObject": {"count": 1, "first": {"offset": "0x3"}, "sources": {}},
        }
        report = ue_anchors.summarize({"hitsByName": hits})

        self.assertFalse(report["readyForObjectDiscovery"])
        self.assertEqual(report["groups"]["names"]["present"], 0)
        self.assertEqual(report["groups"]["reflection"]["present"], 0)

    def test_loader_module_anchors_do_not_satisfy_target_image_readiness(self):
        hits = {
            "FNamePool": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x1", "source": "/tmp/libdune_client_probe_loader.so"},
                "sources": {"/tmp/libdune_client_probe_loader.so": 1},
                "offsets": [{"offset": "0x1", "source": "/tmp/libdune_client_probe_loader.so"}],
            },
            "GUObjectArray": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x2", "source": "/tmp/libdune_client_probe_loader.so"},
                "sources": {"/tmp/libdune_client_probe_loader.so": 1},
                "offsets": [{"offset": "0x2", "source": "/tmp/libdune_client_probe_loader.so"}],
            },
            "GWorld": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x3", "source": "/tmp/libdune_client_probe_loader.so"},
                "sources": {"/tmp/libdune_client_probe_loader.so": 1},
                "offsets": [{"offset": "0x3", "source": "/tmp/libdune_client_probe_loader.so"}],
            },
            "ProcessEvent": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x4", "source": "/tmp/libdune_client_probe_loader.so"},
                "sources": {"/tmp/libdune_client_probe_loader.so": 1},
                "offsets": [{"offset": "0x4", "source": "/tmp/libdune_client_probe_loader.so"}],
            },
        }
        report = ue_anchors.summarize({"hitsByName": hits}, proven_only=True)

        self.assertTrue(report["readyForObjectDiscovery"])
        self.assertFalse(report["readyForTargetObjectDiscovery"])
        self.assertFalse(report["readyForTargetHooks"])
        self.assertEqual(report["groups"]["dispatch"]["anchors"][0]["loaderSourceCount"], 1)
        self.assertEqual(report["groups"]["dispatch"]["anchors"][0]["targetSourceCount"], 0)

    def test_target_module_anchors_satisfy_target_image_readiness(self):
        hits = {
            "FNamePool": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x1", "source": "/game/DuneSandbox-Linux-Shipping"},
                "sources": {"/game/DuneSandbox-Linux-Shipping": 1},
                "offsets": [{"offset": "0x1", "source": "/game/DuneSandbox-Linux-Shipping"}],
            },
            "GUObjectArray": {
                "count": 1,
                "kinds": {"ue-anchor": 1},
                "first": {"offset": "0x2", "source": "/game/DuneSandbox-Linux-Shipping"},
                "sources": {"/game/DuneSandbox-Linux-Shipping": 1},
                "offsets": [{"offset": "0x2", "source": "/game/DuneSandbox-Linux-Shipping"}],
            },
            "GWorld": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x3", "source": "/game/DuneSandbox-Linux-Shipping"},
                "sources": {"/game/DuneSandbox-Linux-Shipping": 1},
                "offsets": [{"offset": "0x3", "source": "/game/DuneSandbox-Linux-Shipping"}],
            },
            "ProcessEvent": {
                "count": 1,
                "kinds": {"ue-anchor-signature": 1},
                "first": {"offset": "0x4", "source": "/game/DuneSandbox-Linux-Shipping"},
                "sources": {"/game/DuneSandbox-Linux-Shipping": 1},
                "offsets": [{"offset": "0x4", "source": "/game/DuneSandbox-Linux-Shipping"}],
            },
        }
        report = ue_anchors.summarize({"hitsByName": hits}, proven_only=True)

        self.assertTrue(report["readyForTargetObjectDiscovery"])
        self.assertTrue(report["readyForTargetHooks"])
        self.assertEqual(report["groups"]["names"]["anchors"][0]["targetSourceCount"], 1)
        self.assertEqual(report["groups"]["names"]["anchors"][0]["loaderSourceCount"], 0)


if __name__ == "__main__":
    unittest.main()
