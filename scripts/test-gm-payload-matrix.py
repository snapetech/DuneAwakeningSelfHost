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

    def test_native_notification_candidates_include_fls_sender(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        body = bodies["notification-native-fls-notifications-serverrequesteventnotifications-clientauth-content-auth"]
        self.assertEqual(body["EventNamespace"], "notifications")
        self.assertEqual(body["Name"], "ServerRequestEventNotifications")
        self.assertEqual(body["SenderId"], "fls")
        self.assertEqual(body["Sender"], "fls")
        self.assertEqual(body["Version"], 1)

    def test_engine_service_notification_candidates_include_event_fields(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        body = bodies["engine-service-fls-notifications-serverrequesteventnotifications-clientauth-content-auth"]
        self.assertEqual(body["Version"], 1)
        self.assertEqual(body["EntityId"], "fls")
        self.assertEqual(body["EntityType"], "fls")
        self.assertEqual(body["EventName"], "ServerRequestEventNotifications")
        self.assertEqual(body["EventNamespace"], "notifications")
        self.assertEqual(body["EventSettings"]["SenderId"], "fls")
        self.assertIn("PrintAllowedCommands", body["EventData"])

    def test_native_derived_notification_candidates_include_object_payload(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        body = bodies["native-derived-notification-clientauth-authtoken-object-content"]
        self.assertEqual(body["EventNamespace"], "notifications")
        self.assertEqual(body["Name"], "ServerRequestEventNotifications")
        self.assertEqual(body["SenderId"], "fls")
        self.assertEqual(body["Sender"], "fls")
        self.assertEqual(body["Version"], 1)
        self.assertEqual(body["Payload"]["AuthToken"], "test-token")
        self.assertEqual(
            body["Payload"]["Content"]["BroadcastPayload"]["ServerCommand"],
            "PrintAllowedCommands",
        )
        self.assertIn('"ServerCommand":"PrintAllowedCommands"', body["PayloadJSON"])

    def test_native_positive_generic_candidates_target_proven_broadcast_type(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        body = bodies["native-positive-notification-generic-servercommandsauthtoken-object-content"]
        self.assertEqual(body["Name"], "ServerRequestEventNotifications")
        self.assertEqual(body["SenderId"], "fls")
        self.assertEqual(body["Payload"]["ServerCommandsAuthToken"], "test-token")
        self.assertEqual(body["Payload"]["Content"]["BroadcastType"], "Generic")
        self.assertEqual(body["Payload"]["Content"]["BroadcastPayload"]["ServerCommand"], "PrintAllowedCommands")
        self.assertIn('"BroadcastType":"Generic"', body["PayloadJSON"])

    def test_native_derived_payload_only_candidate_can_omit_payload_json(self):
        bodies = probe_gm_payload_matrix.build_bodies("PrintAllowedCommands", "Target", "Admin")
        body = bodies["native-derived-notification-servercommand-only-servercommandsauthtoken-payload-only"]
        self.assertEqual(body["Name"], "NotificationSystemHandleServerMessages")
        self.assertNotIn("PayloadJSON", body)
        self.assertEqual(body["Payload"]["ServerCommandsAuthToken"], "test-token")
        self.assertEqual(body["Payload"]["Content"]["ServerCommand"], "PrintAllowedCommands")

    def test_publish_one_allows_native_amqp_property_controls(self):
        class FakeChannel:
            def basic_publish(self, **kwargs):
                self.kwargs = kwargs

        channel = FakeChannel()
        probe_gm_payload_matrix.publish_one(
            channel,
            "notifications",
            "route-key",
            b"{}",
            "application/json",
            "Content",
            "reply.queue",
            "fls",
            "probe-tag",
            "fls-app",
            "corr-1",
        )

        props = channel.kwargs["properties"]
        self.assertEqual(channel.kwargs["exchange"], "notifications")
        self.assertEqual(channel.kwargs["routing_key"], "route-key")
        self.assertEqual(props.type, "Content")
        self.assertEqual(props.reply_to, "reply.queue")
        self.assertEqual(props.user_id, "fls")
        self.assertEqual(props.app_id, "fls-app")
        self.assertEqual(props.correlation_id, "corr-1")

    def test_defaults_include_native_receive_helper_values(self):
        self.assertIn("grant", probe_gm_payload_matrix.NATIVE_AMQP_TYPES)
        self.assertIn("gme_token_response", probe_gm_payload_matrix.NATIVE_AMQP_TYPES)
        self.assertIn("json_rpc", probe_gm_payload_matrix.NATIVE_AMQP_TYPES)
        self.assertIn("Content", probe_gm_payload_matrix.DEFAULT_CONTENT_TYPE_MODES)
        self.assertIn("application/json", probe_gm_payload_matrix.DEFAULT_CONTENT_TYPE_MODES)
        self.assertEqual(
            probe_gm_payload_matrix.normalize_amqp_types(["empty", "grant"]),
            ["", "grant"],
        )
        self.assertEqual(
            probe_gm_payload_matrix.normalize_content_type_modes(["empty", "Content"]),
            ["", "Content"],
        )


if __name__ == "__main__":
    unittest.main()
