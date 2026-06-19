#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPTS = {
    "linux-server": ROOT / "scripts" / "package-linux-server-loader.sh",
    "linux-client": ROOT / "scripts" / "package-linux-client-loader.sh",
    "windows-client": ROOT / "scripts" / "package-windows-client-loader.sh",
}
LOADER_SOURCES = {
    "linux-server": ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
    "linux-client": ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
    "windows-client": ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
}


class LoaderPackageAnalysisParityTests(unittest.TestCase):
    def test_candidate_global_analysis_tools_ship_with_all_loader_packages(self):
        common_required = [
            "export-ue-candidate-globals.py",
            "summarize-ue-candidate-outcomes.py",
            "summarize-ue-candidate-shapes.py",
            "summarize-ue-code-pointer-context.py",
            "summarize-ue-root-recovery-queue.py",
            "cluster-ue-root-recovery-queue.py",
            "export-ue-root-recovery-candidates.py",
            "summarize-ue4ss-port-gaps.py",
            "test-export-ue-candidate-globals.py",
            "test-ue-candidate-outcomes.py",
            "test-ue-candidate-shapes.py",
            "test-ue-code-pointer-context.py",
            "test-ue-root-recovery-queue.py",
            "test-ue-root-recovery-clusters.py",
            "test-export-ue-root-recovery-candidates.py",
            "test-ue4ss-port-gaps.py",
            "UE_CANDIDATE_GLOBALS=",
            "--root-recovery-candidates-json",
            "--candidate-shapes-json",
            "--canary-plan-json",
            "next-canary.json",
            "ensure-loader-build-toolchain.sh",
            "verify-loader-artifacts.py",
            "test-verify-loader-artifacts.py",
        ]
        platform_required = {
            "linux-server": [
                "summarize-elf-writable-global-refs.py",
                "summarize-elf-writable-root-shapes.py",
                "test-elf-writable-global-refs.py",
                "test-elf-writable-root-shapes.py",
            ],
            "linux-client": [
                "summarize-elf-writable-global-refs.py",
                "summarize-elf-writable-root-shapes.py",
                "test-elf-writable-global-refs.py",
                "test-elf-writable-root-shapes.py",
            ],
            "windows-client": [
                "summarize-pe-writable-root-shapes.py",
                "test-pe-writable-root-shapes.py",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                for item in common_required + platform_required[platform]:
                    self.assertIn(item, source)

    def test_packages_document_strict_process_event_dispatch_contract(self):
        required = [
            "runtimeProcessEventDispatch",
            "more than a live hook row",
            "decoded live function path",
            "runtime registry context",
            "raw and",
            "container param samples",
            "Lua context handles",
            "descriptor-backed param accessors",
            "typed scalar/name/string/struct/enum/object/bool accessor coverage",
            "container alias/layout methods",
            "hook routing/alias routing",
        ]
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_load_asset_package_preflight_logs_target_image_evidence_on_all_loaders(self):
        common_required = [
            "event=lua-load-asset-package-preflight status=native-bridge-missing",
            "targetName=",
            "targetImage=",
            "targetMapped=",
            "targetReadable=",
            "targetExecutable=",
            "invokeEnabled=",
            "nativeBridgeArmed=false",
            "nativeCallable=false",
            "nativeInvoked=false",
            "packageAvailable=",
            "lua_load_asset_backend_package_target_image = 0;",
        ]
        per_loader_required = {
            "linux-server": [
                "platformAbi=sysv-x86_64",
                "targetPerms=%s",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN",
            ],
            "linux-client": [
                "platformAbi=sysv-x86_64",
                "targetPerms=%s",
                "DUNE_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
                "DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN",
            ],
            "windows-client": [
                "platformAbi=win64-ms-abi",
                "targetProtect=",
                "DUNE_WIN_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
                "DUNE_WIN_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)
        server_source = LOADER_SOURCES["linux-server"].read_text(encoding="utf-8")
        self.assertLess(
            server_source.index("start_delayed_ue_probe();"),
            server_source.index("snapshot();", server_source.index("dune_server_probe_loader_init")),
        )
        linux_client_source = LOADER_SOURCES["linux-client"].read_text(encoding="utf-8")
        self.assertLess(
            linux_client_source.index("start_delayed_ue_probe();"),
            linux_client_source.index("snapshot();", linux_client_source.index("dune_client_probe_loader_init")),
        )
        windows_source = LOADER_SOURCES["windows-client"].read_text(encoding="utf-8")
        self.assertLess(
            windows_source.index("start_delayed_ue_probe();", windows_source.index("probe_thread")),
            windows_source.index('probe_run("thread");'),
        )

    def test_linux_server_loader_skips_non_target_helper_processes(self):
        source = LOADER_SOURCES["linux-server"].read_text(encoding="utf-8")
        for item in [
            "DUNE_PROBE_LOADER_TARGET",
            "DUNE_PROBE_LOADER_FORCE",
            "event=target-skip",
            "is_target_process(exe)",
            "DuneSandboxServer",
            "DuneSandbox",
        ]:
            self.assertIn(item, source)
        self.assertLess(source.index("event=target-skip"), source.index('log_modules("initial")'))

    def test_runtime_auto_discovery_logs_scan_coverage_on_all_loaders(self):
        common_required = [
            "event=ue-runtime-discovery-start",
            "event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray",
            "scannedSlots=",
            "fnameProbes=",
            "objectArrayProbes=",
            "event=ue-runtime-discovery-limited",
            "limited=",
            "rejectedFNameSamples=",
            "event=ue-runtime-discovery-rejected name=RuntimeFNamePool",
            "UeFNameCandidateMetrics",
            "plausibleEntries=",
            "firstEntry=",
            "firstHeader=",
            "firstLength=",
            "firstWide=",
            "firstBlockEntryPlausible=",
            "firstBlockEntryNone=",
            "firstBlockHeader=",
            "firstBlockLength=",
            "firstBlockWide=",
            "currentBlock=",
            "currentByteCursor=",
            "allocatorStatePlausible=",
            "targetImage=",
            "chunksReadable=",
            "firstChunkReadable=",
            "firstObjectReadable=",
            "MAX_REJECTED_FNAME_SAMPLES",
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW",
                "targetWritableMappings=",
                "privateWritableMappings=",
                "oversizedMappings=",
                "event=ue-runtime-discovery name=target-writable-image-mappings status=missing",
                "firstBlockSameMapping=",
                "firstBlockTargetImage=",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW",
                "targetWritableMappings=",
                "privateWritableMappings=",
                "oversizedMappings=",
                "event=ue-runtime-discovery name=target-writable-image-mappings status=missing",
                "firstBlockSameMapping=",
                "firstBlockTargetImage=",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW",
                "targetWritableRegions=",
                "privateWritableRegions=",
                "oversizedRegions=",
                "event=ue-runtime-discovery name=target-writable-image-regions status=missing",
                "firstBlockSameRegion=",
                "firstBlockTargetImage=",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

    def test_delayed_runtime_root_probe_is_available_on_all_loaders(self):
        common_required = [
            "event=ue-delayed-probe-config",
            "event=ue-delayed-probe-start",
            "event=ue-delayed-probe-finish",
            'validate_ue_anchors("ue-delayed")',
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_DELAYED_PROBE_SECONDS",
                "pthread_create",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS",
                "pthread_create",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS",
                "Sleep((DWORD)(delay * 1000))",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

    def test_object_array_ufunction_identity_promotion_is_available_on_all_loaders(self):
        common_required = [
            "add_ue_function_identity_descriptor(",
            'contains_ci(native_class_name, "Function")',
            "event=ue-function-native-identity source=",
            "status=promoted",
            "log_lua_function_registry_check_with_provenance(",
            '"ue-object-array"',
            '"runtime"',
            '"objectArray"',
            '"UFunction"',
            "decoded_outer_name",
            "outer_private ? outer_private : class_private",
            'decoded_outer_name[0] ? decoded_outer_name : array_name',
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_function_only_identities_do_not_count_as_param_descriptors(self):
        common_required = [
            "ue_function_descriptor_has_param_field(",
            "descriptor && descriptor->field != 0",
            "count_ue_function_param_descriptors(",
            "!ue_function_descriptor_has_param_field(descriptor)",
            "descriptor->function != function || !ue_function_descriptor_has_param_field(descriptor)",
            "find_ue_function_descriptor_by_path_or_name(",
            "push_ue_function_handle_from_descriptor(",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_lua_reflection_self_test_searches_runtime_function_owners(self):
        common_required = [
            "GetKnownObjects();if kos then for _,x in pairs(kos)",
            "x.ForEachFunction",
            "not tostring(x.Name or",
            "find('SelfTest')",
            "if rfi>0 then ro=x;break end",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_hook_runtime_target_provenance_is_logged_on_all_loaders(self):
        common_required = [
            "process_event_hook_target_source(",
            "process_event_live_hook_target_source(",
            "call_function_hook_target_source(",
            "call_function_live_hook_target_source(",
            "targetSource=",
            "targetName=ProcessEvent",
            "targetName=CallFunctionByNameWithArguments",
            "explicit-hook-address",
            "explicit-live-hook-address",
            "explicit-process-event-address",
            "explicit-call-function-address",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_runtime_root_consumer_validation_is_logged_on_all_loaders(self):
        common_required = [
            "event=ue-runtime-root-validation phase=",
            "name=RuntimeFNamePool status=validated consumer=fname",
            "name=RuntimeGUObjectArray status=validated consumer=object-array",
            "RuntimeGUObjectArray",
            "RuntimeFNamePool",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_native_reflection_descriptor_provenance_is_logged_on_all_loaders(self):
        common_required = [
            "reflection_descriptor_provenance(",
            "descriptorProvenance=",
            "fieldTargetImage=",
            "objectTargetImage=",
            "valueTargetImage=",
            "event=ue-reflection-property name=",
            "event=ue-reflection-value name=",
            "self-test",
            "runtime",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_runtime_candidate_global_restart_stable_modes_are_platform_specific(self):
        linux_required = [
            "@rwfile",
            "resolve_runtime_rw_file_offset",
            "runtimeRwFileOffset=%s",
            "runtime-rw-file-offset-missing",
        ]
        for loader in ("linux-server", "linux-client"):
            with self.subTest(loader=loader):
                source = LOADER_SOURCES[loader].read_text(encoding="utf-8")
                for item in linux_required:
                    self.assertIn(item, source)

        windows_source = LOADER_SOURCES["windows-client"].read_text(encoding="utf-8")
        for item in [
            "@private-rva",
            "resolve_runtime_private_rva",
            "runtimePrivateRva=",
            "runtime-private-rva-missing",
            "runtime-private-rva-ambiguous",
        ]:
            self.assertIn(item, windows_source)

    def test_fname_decode_diagnostics_are_available_on_all_loaders(self):
        common_required = [
            "event=ue-fname-diagnostic",
            "event=ue-fname-resolver-reject",
            "lenShift1",
            "wideBit0",
            "lenShift6",
            "wideBit15",
            "entryReadable",
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS",
                "DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS_MAX",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS",
                "DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS_MAX",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS",
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS_MAX",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

        package_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS=false",
                "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false",
                "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=false",
                "DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false",
                "DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=false",
                "DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false",
                "DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(package=platform):
                source = script.read_text(encoding="utf-8")
                for item in package_required[platform]:
                    self.assertIn(item, source)

    def test_fname_pool_resolver_rejects_pointer_table_false_positives(self):
        common_required = [
            "plausible_entries",
            "scan_limit = 4096",
            "plausible_entries >= 4",
            "first_block_entry_plausible",
            "first_block_entry_none",
            "allocator_state_plausible",
            "current_byte_cursor < (2U * 1024U * 1024U)",
            "pool == (uintptr_t)&ue_self_test_fname_pool",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_client_packages_ship_non_mutating_launch_preflight_tests(self):
        for platform in ("linux-client", "windows-client"):
            with self.subTest(platform=platform):
                source = PACKAGE_SCRIPTS[platform].read_text(encoding="utf-8")
                self.assertIn("test-client-launch-preflight.py", source)
                self.assertIn("tests/test-client-launch-preflight.py", source)

    def test_server_package_ships_zero_player_canary_preflight_test(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        self.assertIn("canary-linux-server-loader.sh", source)
        self.assertIn("test-canary-linux-server-loader.py", source)


if __name__ == "__main__":
    unittest.main()
