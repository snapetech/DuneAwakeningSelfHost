#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("probe-gm-payload-matrix.py")
SPEC = importlib.util.spec_from_file_location("probe_gm_payload_matrix", SCRIPT_PATH)
probe_gm_payload_matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_gm_payload_matrix)


class GmPayloadMatrixTests(unittest.TestCase):
    def setUp(self):
        self.old_token = os.environ.get("DUNE_SERVER_COMMANDS_AUTH_TOKEN")
        self.old_gm_token = os.environ.get("DUNE_GM_SERVER_COMMAND_AUTH_TOKEN")
        os.environ["DUNE_SERVER_COMMANDS_AUTH_TOKEN"] = "test-token"
        os.environ.pop("DUNE_GM_SERVER_COMMAND_AUTH_TOKEN", None)

    def tearDown(self):
        if self.old_token is None:
            os.environ.pop("DUNE_SERVER_COMMANDS_AUTH_TOKEN", None)
        else:
            os.environ["DUNE_SERVER_COMMANDS_AUTH_TOKEN"] = self.old_token
        if self.old_gm_token is None:
            os.environ.pop("DUNE_GM_SERVER_COMMAND_AUTH_TOKEN", None)
        else:
            os.environ["DUNE_GM_SERVER_COMMAND_AUTH_TOKEN"] = self.old_gm_token

    def test_auth_aware_service_broadcast_bodies_exist(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        self.assertIn("payloadjson-broadcast-clientauth", bodies)
        self.assertIn("authfields-payloadtype-payloadjson-clientauth", bodies)
        self.assertIn("ServerBroadcastClientAuthenticated", bodies["payloadjson-broadcast-clientauth"]["PayloadJSON"])
        self.assertEqual(bodies["authfields-payloadtype-payloadjson-clientauth"]["ServerCommandsAuthToken"], "test-token")

    def test_notification_envelope_bodies_include_raw_content_and_token(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        body = bodies["notification-servercommand-payloadjson-clientauth-content-auth"]
        self.assertEqual(body["EventNamespace"], "ServerCommand")
        self.assertIn("PayloadJSON", body)
        self.assertIn("AuthToken", body["PayloadJSON"])
        self.assertIn("PrintAllowedCommands", body["PayloadJSON"])


if __name__ == "__main__":
    unittest.main()
