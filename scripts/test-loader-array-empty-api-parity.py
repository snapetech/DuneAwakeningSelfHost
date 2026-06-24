#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOADERS = {
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


class LoaderArrayEmptyApiParityTests(unittest.TestCase):
    def test_all_loaders_expose_tarray_empty_on_array_handles(self):
        for target, source in LOADERS.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                self.assertIn("lua_script_array_empty_callback", text)
                self.assertIn('set_lua_object_method(api, state, "Empty", lua_script_array_empty_callback);', text)
                self.assertIn('active_lua_api->set_field(state, 1, "Num");', text)

    def test_self_tests_prove_empty_on_populated_array_handles(self):
        required = (
            "local arrayOk=av and av.Kind == 'FScriptArray'",
            "av:GetNum() == 4",
            "av:GetRawElement(1,4)",
            "local emptyOk=arrayOk and av:Empty() and av:GetNum() == 0",
            "and arr and arr.ClassName == 'FArrayProperty' and arrayOk and emptyOk",
        )
        for target, source in LOADERS.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                if target == "windows-client":
                    self.assertIn("local arrayOk=av and av.Kind=='FScriptArray'", text)
                    self.assertIn("av:GetNum()==4", text)
                    self.assertIn("av:GetRawElement(1,4)", text)
                    self.assertIn("local emptyOk=arrayOk and av:Empty() and av:GetNum()==0", text)
                    self.assertIn("and ar and ar.ClassName=='FArrayProperty'and arrayOk and emptyOk", text)
                else:
                    for needle in required:
                        self.assertIn(needle, text)

    def test_docs_name_tarray_empty_compatibility(self):
        for doc in DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                self.assertIn("Empty()", text)
                self.assertIn("TArray", text)


if __name__ == "__main__":
    unittest.main()
