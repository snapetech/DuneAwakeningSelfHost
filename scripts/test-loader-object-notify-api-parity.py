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
            "UnregisterNotifyOnNewObject",
            "StaticConstructObject",
            "ConstructedProbe",
            "notifyOnNewObjectCallbacks",
            "notifyOnNewObjectResult",
            "notifyOnNewObjectStatus",
            "registration->id = ++lua_compat_registration_count",
            "lua_unregister_notify_on_new_object_callback",
            "lua_notify_on_new_object_callbacks == 1",
            "lua_notify_on_new_object_result == 17",
            "lua_notify_on_new_object_status == 0",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_expose_static_construct_native_bridge_state(self):
        required = (
            "lua_get_static_construct_object_native_executor_state_callback",
            "lua_invoke_static_construct_object_native_callback",
            "lua-static-construct-object-native-executor-state",
            "lua-static-construct-object-native-invoke",
            "guarded-static-construct-object-native-executor",
            'set_global(state, "GetStaticConstructObjectNativeExecutorState")',
            'set_global(state, "InvokeStaticConstructObjectNative")',
            "STATIC_CONSTRUCT_OBJECT_ABI_EVIDENCE",
            "ALLOW_STATIC_CONSTRUCT_OBJECT_INVOKE",
            "CONFIRM_STATIC_CONSTRUCT_OBJECT_NATIVE_CALL",
            "NativeExecutorBlockReason",
            "NativeInvoked",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_exercise_static_construct_native_bridge_gate(self):
        smokes = (
            REPO_ROOT / "scripts/smoke-linux-client-loader.sh",
            REPO_ROOT / "scripts/smoke-linux-server-loader.sh",
            REPO_ROOT / "scripts/smoke-windows-client-loader-lua.sh",
        )
        required = (
            "GetStaticConstructObjectNativeExecutorState",
            "InvokeStaticConstructObjectNative",
            "NativeConstructPreflightProbe",
            "loader-static-construct-object-native-executor-state",
            "loader-static-construct-object-native-bridge",
            "guarded-static-construct-object-native-executor",
            "missing StaticConstructObject native bridge gate",
        )
        for smoke in smokes:
            with self.subTest(smoke=smoke.name):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_describe_notify_on_new_object_self_test_proof(self):
        required = (
            "NotifyOnNewObject",
            "UnregisterNotifyOnNewObject",
            "StaticConstructObject",
            "notifyOnNewObjectCallbacks=1",
            "notifyOnNewObjectResult=17",
            "notifyOnNewObjectStatus=0",
            "GetStaticConstructObjectNativeExecutorState",
            "InvokeStaticConstructObjectNative",
            "guarded `StaticConstructObject` native executor",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
