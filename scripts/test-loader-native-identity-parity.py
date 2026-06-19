#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LoaderNativeIdentityParityTests(unittest.TestCase):
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

    def test_all_targets_emit_native_identity_evidence(self):
        required = (
            "ue-object-native-identity",
            "ue-function-native-identity",
            "ue-process-event-live-registry-context",
            "decoded_class_name",
            "native_class_name",
            "classNameDecoded",
            "nameDecoded",
            "functionRuntimePath",
            "objectNativeIdentity",
            "functionNativeIdentity",
            "FindFunction",
            "FindFirstFunction",
            "GetKnownFunctions",
            "ForEachUFunction",
            "CallFunctionByNameWithArguments",
            "lua_call_function_name_arg",
            "lua_find_function_callback",
            "lua_get_known_functions_callback",
            "lua_for_each_ufunction_callback",
            "ue_function_descriptor_matches_filter",
            "GetFunctionParams",
            "GetParamDescriptor",
            "ForEachParam",
            '"GetSuper"',
            '"GetSuperClass"',
            '"GetDefaultObject"',
            '"GetDefaultObj"',
            "lua_function_get_function_params_callback",
            "lua_function_get_param_descriptor_callback",
            "lua_function_for_each_param_callback",
            "functionParamMethodHits",
            "functionParamLookupMethodHits",
            "functionParamIterationMethodHits",
            "descriptorValueAliasHits",
            "lua_property_get_alias_callback",
            "lua_property_set_alias_callback",
            "lua_reflection_for_each_property_callback",
            "reflectionForEachPropertyHits",
            "liveDescriptorValueGetHits",
            "liveDescriptorValueSetHits",
            "update_ue_candidate_object_metadata(object, class_private, outer_private, 0)",
            "record_lua_class_metadata(class_private, 0, native_class_name)",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)

    def test_all_targets_prove_enum_descriptor_value_marshaling(self):
        common_required = (
            "ProbeEnum",
            "enumExport",
            "ae:ImportText('4')",
            "ae:GetValue()==4",
            "SetPropertyValue(o,'ProbeEnum',3)",
            "bv==3",
            "lua_reflection_probe_enum_value == 3",
            'contains_ci(class_name, "ByteProperty") || contains_ci(class_name, "EnumProperty")',
            "pushed_typed = 1",
            "lua_reflection_descriptor_value_get_hits == 21",
            "lua_reflection_descriptor_value_set_hits == 9",
            "lua_reflection_import_text_hits == 2",
            "lua_reflection_export_text_hits == 2",
        )
        target_specific = {
            "linux-client": (
                'strcmp(name, "ProbeEnum") == 0',
                'snprintf(out, sizeof(out), "%u", (unsigned)lua_reflection_probe_enum_value)',
            ),
            "linux-server": (
                'strcmp(name, "ProbeEnum") == 0',
                'snprintf(out, sizeof(out), "%u", (unsigned)lua_reflection_probe_enum_value)',
            ),
            "windows-client": (
                'str_equal(name, "ProbeEnum")',
                "export_format_signed_dec(out, sizeof(out), (long long)lua_reflection_probe_enum_value)",
            ),
        }
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in common_required + target_specific[target]:
                    self.assertIn(needle, text)

    def test_all_targets_prove_process_event_enum_param_marshaling(self):
        common_required = (
            '"Mode", "mode"',
            'sizeof(uint8_t), "enum", "FEnumProperty"',
            "params->mode = 2",
            "GetParamDescriptor(p,'Mode')",
            "md.ClassName == 'FEnumProperty'",
            "GetParamValue(p,md) == 2",
            "SetParamValue(p,md,4)",
            "GetParamValue(p,md) == 4",
            "p.PropertyCount == 17",
        )
        compact_windows_required = (
            "G(p,'Mode')",
            "md.ClassName=='FEnumProperty'",
            "V(p,md)==2",
            "S(p,md,4)",
            "V(p,md)==4",
            "p.PropertyCount==17",
        )
        for target, source in self.SOURCES.items():
            with self.subTest(target=target):
                text = source.read_text(encoding="utf-8")
                for needle in common_required:
                    if target == "windows-client" and needle in {
                        "GetParamDescriptor(p,'Mode')",
                        "md.ClassName == 'FEnumProperty'",
                        "GetParamValue(p,md) == 2",
                        "SetParamValue(p,md,4)",
                        "GetParamValue(p,md) == 4",
                        "p.PropertyCount == 17",
                    }:
                        continue
                    self.assertIn(needle, text)
                if target == "windows-client":
                    for needle in compact_windows_required:
                        self.assertIn(needle, text)
        counter_required = (
            "paramDescriptorLookupCalls=17 paramDescriptorLookupHits=17",
            "paramGetCalls=29 paramGetHits=29 paramSetCalls=11 paramSetHits=11",
        )
        counter_files = (
            ROOT / "scripts/smoke-linux-client-loader.sh",
            ROOT / "scripts/smoke-linux-server-loader.sh",
            ROOT / "scripts/smoke-windows-client-loader-lua.sh",
            ROOT / "scripts/test-client-loader-scan-summary.py",
            ROOT / "scripts/test-linux-loader-scan-summary.py",
            ROOT / "scripts/test-ue4ss-port-readiness.py",
        )
        for path in counter_files:
            with self.subTest(counter_file=path.name):
                text = path.read_text(encoding="utf-8")
                for needle in counter_required:
                    self.assertIn(needle, text)

    def test_docs_describe_native_identity_readiness(self):
        required = (
            "ue-object-native-identity",
            "ue-function-native-identity",
            "ue-process-event-live-registry-context",
            "ueObjectNativeIdentities",
            "ueFunctionNativeIdentities",
            "ueProcessEventLiveRegistryContext",
            "Function:GetFunctionParams",
            "Function:GetParamDescriptor",
            "Function:ForEachParam",
            "FindFunction",
            "FindFirstFunction",
            "GetKnownFunctions",
            "ForEachUFunction",
            "GetSuper",
            "GetSuperClass",
            "GetDefaultObject",
            "GetDefaultObj",
            "ueProcessEventFunctionParamMethod",
            "ueProcessEventFunctionParamLookupMethod",
            "ueProcessEventFunctionParamIterationMethod",
            "Reflection():ForEachProperty",
            "luaReflectionForEachProperty",
            "luaReflectionLiveDescriptorValues",
            "get()` / `set()`",
            "decoded class",
            "OuterPrivate",
        )
        for doc in self.DOCS:
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                for needle in required:
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
