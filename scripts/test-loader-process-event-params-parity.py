#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FULL_LUA_SMOKES = {
    "linux-client": ROOT / "scripts" / "smoke-linux-client-loader.sh",
    "linux-server": ROOT / "scripts" / "smoke-linux-server-loader.sh",
    "windows-client": ROOT / "scripts" / "smoke-windows-client-loader-lua.sh",
}

DOCS = (
    ROOT / "docs" / "client-loader-support.md",
    ROOT / "docs" / "linux-client-loader.md",
    ROOT / "docs" / "windows-client-loader.md",
    ROOT / "docs" / "ue4ss-linux-loader-evaluation.md",
)


class LoaderProcessEventParamsParityTests(unittest.TestCase):
    def existing_smokes(self):
        smokes = {
            target: path
            for target, path in FULL_LUA_SMOKES.items()
            if path.exists()
        }
        self.assertEqual(set(smokes), set(FULL_LUA_SMOKES))
        return smokes

    def existing_docs(self):
        docs = tuple(path for path in DOCS if path.exists())
        self.assertGreaterEqual(len(docs), 1)
        return docs

    def test_loaded_mods_directly_create_descriptor_backed_params_buffers(self):
        required = (
            "local f=FindFunction('/Script/SelfTestUObject.SelfTestUObjectName_0:Function')",
            "local p=f and CreateProcessEventParams(f)",
            "p.Kind=='ProcessEventParams'",
            "p.IsValid",
            "p.PropertyCount>=1",
            "SetParamValue(p,v,82)",
            "GetParamValue(p,v)==82",
            "p.Value and p.Value:get()==82",
            "missing direct ProcessEvent params buffer",
        )
        for target, smoke in self.existing_smokes().items():
            with self.subTest(target=target):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_smokes_require_process_event_params_buffer_log(self):
        required = (
            "event=lua-process-event-params-buffer status=created",
            "descriptorCount=[1-9][0-9]*",
            "size=[1-9][0-9]*",
            "address=0x[0-9a-fA-F][0-9a-fA-F]*",
        )
        for target, smoke in self.existing_smokes().items():
            with self.subTest(target=target):
                text = smoke.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_docs_call_out_loaded_mod_process_event_params_proof(self):
        required = (
            "CreateProcessEventParams(function)",
            "lua-process-event-params-buffer",
        )
        for doc in self.existing_docs():
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
