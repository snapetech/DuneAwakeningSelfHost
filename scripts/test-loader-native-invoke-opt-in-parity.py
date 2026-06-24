#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SMOKES = {
    "linux-client": ROOT / "scripts" / "smoke-linux-client-loader.sh",
    "linux-server": ROOT / "scripts" / "smoke-linux-server-loader.sh",
    "windows-client": ROOT / "scripts" / "smoke-windows-client-loader-lua.sh",
}

SOURCES = {
    "linux-client": ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
    "linux-server": ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
    "windows-client": ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
}

DOCS = (
    ROOT / "docs" / "client-loader-support.md",
    ROOT / "docs" / "linux-client-loader.md",
    ROOT / "docs" / "windows-client-loader.md",
    ROOT / "docs" / "ue4ss-linux-loader-evaluation.md",
)


class LoaderNativeInvokeOptInParityTests(unittest.TestCase):
    def test_process_event_non_self_test_invocation_returns_invoked(self):
        for target, source in SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                if target == "windows-client":
                    self.assertIn('str_equal(status, "invoked") || str_equal(status, "non-self-test-invoked")', text)
                else:
                    self.assertIn('strcmp(status, "invoked") == 0 || strcmp(status, "non-self-test-invoked") == 0', text)

    def test_process_event_native_executor_state_is_available_on_all_loaders(self):
        required = (
            "lua_get_process_event_native_executor_state_callback",
            'set_global(state, "GetProcessEventNativeExecutorState")',
            "event=lua-process-event-native-executor-state",
            "guarded-process-event-native-executor",
            "NativeExecutorBlockReason",
            "loader-process-event-native-executor",
            "GetProcessEventNativeExecutorState(ro,f)",
            "missing ProcessEvent native executor state",
        )
        for target, source in SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_call_function_native_executor_state_is_available_on_all_loaders(self):
        required = (
            "lua_get_call_function_native_executor_state_callback",
            'set_global(state, "GetCallFunctionNativeExecutorState")',
            "event=lua-call-function-native-executor-state",
            "guarded-call-function-native-executor",
            "NativeExecutorBlockReason",
            "loader-call-function-native-executor",
            "GetCallFunctionNativeExecutorState(ro,'DoubleProbeValue'",
            "missing CallFunction native executor state",
        )
        for target, source in SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_enable_non_self_test_native_invoke_opt_ins(self):
        required_by_target = {
            "linux-client": (
                "DUNE_CLIENT_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE=true",
                "DUNE_CLIENT_PROBE_ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE=true",
            ),
            "linux-server": (
                "DUNE_SERVER_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE=true",
                "DUNE_SERVER_PROBE_ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE=true",
            ),
            "windows-client": (
                "DUNE_WIN_CLIENT_PROBE_ALLOW_NON_SELF_TEST_PROCESS_EVENT_INVOKE=true",
                "DUNE_WIN_CLIENT_PROBE_ALLOW_NON_SELF_TEST_CALL_FUNCTION_INVOKE=true",
            ),
        }
        for target, smoke in SMOKES.items():
            with self.subTest(target=target):
                text = smoke.read_text(encoding="utf-8")
                for needle in required_by_target[target]:
                    self.assertIn(needle, text)

    def test_smokes_require_enabled_non_self_test_native_invoke_rows(self):
        required = (
            "event=lua-process-event-native-invoke status=non-self-test-invoked",
            "nativeNonSelfTestEnabled=true nativeNonSelfTestInvoked=true",
            "event=lua-call-function-native-invoke status=non-self-test-invoked",
            "processEventNativeCalls=3 processEventNativeHits=2",
        )
        for target, smoke in SMOKES.items():
            with self.subTest(target=target):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_enabled_non_self_test_native_invoke_gate(self):
        required = (
            "status=non-self-test-invoked",
            "luaProcessEventNativeInvokeNonSelfTestInvoked=true",
        )
        for doc in DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
