#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-runtime-trace.py"

spec = importlib.util.spec_from_file_location("plan_ue4ss_package_runtime_trace", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageRuntimeTracePlanTests(unittest.TestCase):
    def sample_external_plan(self):
        return {
            "schemaVersion": "dune-ue4ss-package-external-symbol-plan/v1",
            "promotionAcceptance": {
                "schemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            },
            "binary": {"buildId": "abc123"},
            "historicalStringSeeds": [
                {
                    "name": "LoadObject",
                    "address": "0x814c33",
                    "promotion": "non-promotable-string-only",
                    "sources": ["surface.md"],
                    "use": "trace only",
                },
                {
                    "name": "LoadPackage",
                    "address": "0x5ae6260",
                    "promotion": "non-promotable-string-only",
                    "sources": ["surface.md"],
                    "use": "trace only",
                },
                {
                    "name": "StaticLoadClass",
                    "address": "0x6ae6260",
                    "promotion": "non-promotable-string-only",
                    "sources": ["surface.md"],
                    "use": "trace only",
                },
            ],
        }

    def sample_method_candidates(self):
        return {
            "schemaVersion": "dune-elf-ue-package-loader-vtables/v1",
            "rows": [
                {
                    "demangled": "vtable for UScriptStruct::TCppStructOps<FBootLoadObjectData>",
                    "executableSlots": [
                        {
                            "index": 4,
                            "value": "0xbfca7e0",
                            "candidateKind": "method",
                            "shape": {"startsWithFrame": True, "hasCall": True},
                        }
                    ],
                },
                {
                    "demangled": "vtable for FLinkerLoad",
                    "executableSlots": [
                        {
                            "index": 9,
                            "value": "0xfb316a0",
                            "candidateKind": "method",
                            "shape": {"startsWithFrame": False, "hasIndirectCall": True},
                        },
                        {
                            "index": 8,
                            "value": "0xfb2eb00",
                            "candidateKind": "trivial",
                            "shape": {"returnsConstantZero": True},
                        },
                    ],
                },
            ],
        }

    def test_build_plan_prefers_load_package_seed(self):
        plan = module.build_plan(self.sample_external_plan(), base=0x100000, limit=1)

        self.assertEqual(plan["seedCount"], 1)
        self.assertEqual(plan["seeds"][0]["name"], "LoadPackage")
        self.assertEqual(plan["seedSelection"]["eligibleSeedCount"], 3)
        self.assertEqual(plan["seedSelection"]["availableByFamily"]["LoadPackage"], 1)
        self.assertEqual(plan["seedSelection"]["selectedByFamily"]["LoadPackage"], 1)
        self.assertEqual(plan["seedSelection"]["skippedByFamily"]["LoadObject"], 1)
        self.assertEqual(
            plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ANCHOR"],
            "LoadPackage",
        )
        self.assertEqual(plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"], "1")
        self.assertEqual(plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY"], "LoadPackage")
        self.assertEqual(plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX"], "auto")
        self.assertEqual(
            plan["sourcePromotionAcceptanceSchemaVersion"],
            "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        )
        self.assertEqual(plan["seeds"][0]["absoluteAddress"], "0x5be6260")
        self.assertIn("rwatch *(char*)0x5be6260", plan["gdb"])
        self.assertIn("base=0x%lx", plan["gdb"])
        self.assertIn("bt 8", plan["gdb"])
        self.assertIn("UE4SS_PACKAGE_TRACE_DISASM_BEGIN", plan["gdb"])
        self.assertIn("x/12i $rip-24", plan["gdb"])
        self.assertIn("UE4SS_PACKAGE_TRACE_STACK_BEGIN", plan["gdb"])
        self.assertIn("x/8gx $rsp", plan["gdb"])
        self.assertIn("UE4SS_PACKAGE_TRACE_REGMEM_BEGIN reg=rsi", plan["gdb"])
        self.assertIn("if $rsi > 0x10000", plan["gdb"])
        self.assertIn("x/8gx $rsi", plan["gdb"])
        self.assertIn("x/32bx $rsi", plan["gdb"])
        self.assertIn("x/s $rsi", plan["gdb"])
        self.assertIn("UE4SS_PACKAGE_TRACE_REGMEM_SKIP reg=rsi", plan["gdb"])
        self.assertIn("UE4SS_PACKAGE_TRACE_REGMEM_END reg=rsi", plan["gdb"])

    def test_anchor_filter_selects_load_object(self):
        plan = module.build_plan(self.sample_external_plan(), base=0x100000, anchors=["LoadObject"], limit=4)

        self.assertEqual(plan["seedCount"], 1)
        self.assertEqual(plan["seeds"][0]["name"], "LoadObject")
        self.assertEqual(plan["seedSelection"]["requestedAnchors"], ["LoadObject"])
        self.assertEqual(plan["seedSelection"]["missingRequestedAnchors"], [])

    def test_method_candidates_generate_non_promotable_breakpoint_probes(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            limit=1,
            method_candidates=self.sample_method_candidates(),
            method_limit=2,
        )

        self.assertEqual(plan["methodProbeCount"], 2)
        self.assertEqual(plan["methodProbes"][0]["owner"], "vtable for FLinkerLoad")
        self.assertEqual(plan["methodProbes"][0]["address"], "0xfb316a0")
        self.assertEqual(plan["methodProbes"][0]["absoluteAddress"], "0xfc316a0")
        self.assertEqual(plan["methodProbes"][0]["promotion"], "non-promotable-method-probe")
        self.assertIn("break *0xfc316a0", plan["methodGdb"])
        self.assertIn("UE4SS_PACKAGE_METHOD_TRACE_HIT", plan["methodGdb"])
        self.assertIn("UE4SS_PACKAGE_TRACE_HIT", plan["gdb"])
        self.assertIn("UE4SS_PACKAGE_METHOD_TRACE_HIT", plan["gdb"])
        self.assertTrue(plan["gdb"].endswith("continue\n"))
        self.assertIn("method probes remain non-promotable", " ".join(plan["acceptance"]))

    def test_route_addresses_generate_non_promotable_breakpoint_probes(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            limit=1,
            route_addresses=["0xf94711c,0xf9492bc"],
        )

        self.assertEqual(plan["routeProbeCount"], 2)
        self.assertEqual(plan["requestedRouteAddresses"], ["0xf94711c", "0xf9492bc"])
        self.assertEqual(plan["routeProbes"][0]["address"], "0xf94711c")
        self.assertEqual(plan["routeProbes"][0]["absoluteAddress"], "0xfa4711c")
        self.assertEqual(plan["routeProbes"][0]["promotion"], "non-promotable-route-probe")
        self.assertIn("break *0xfa4711c", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_TRACE_HIT", plan["routeGdb"])
        self.assertIn("rbx=%p r12=%p r13=%p r14=%p r15=%p", plan["routeGdb"])
        self.assertIn("$rbx, $r12, $r13, $r14, $r15", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=rbx", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg=rbx", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=r14", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg=r14", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=rdi", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg=rdi", plan["routeGdb"])
        self.assertIn("set $ue4ss_route_rsp0 = *(void**)($rsp+0)", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=rsp0", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg=rsp0", plan["routeGdb"])
        self.assertIn("set $ue4ss_route_rsp28 = *(void**)($rsp+40)", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg=rsp28", plan["routeGdb"])
        self.assertIn("UE4SS_PACKAGE_ROUTE_TRACE_HIT", plan["gdb"])
        self.assertIn("route probes remain non-promotable", " ".join(plan["acceptance"]))

        text = module.markdown(plan)
        self.assertIn("Route probes: `2`", text)
        self.assertIn("Route Probes", text)
        self.assertIn("Route GDB Commands", text)

    def test_method_candidate_selection_ignores_trivial_slots_and_deduplicates(self):
        artifact = self.sample_method_candidates()
        artifact["rows"][1]["executableSlots"].append(
            {
                "index": 10,
                "value": "0xfb316a0",
                "candidateKind": "method",
                "shape": {"startsWithFrame": True, "hasCall": True},
            }
        )
        artifact["rows"][1]["executableSlots"].append(
            {
                "index": 11,
                "value": "0xfb31700",
                "candidateKind": "method",
                "shape": {"startsWithFrame": True},
            }
        )

        methods = module.select_method_candidates(artifact, 8)

        self.assertEqual([method["address"] for method in methods], ["0xfb316a0", "0xbfca7e0"])

    def test_method_candidates_can_be_limited_to_requested_addresses(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            method_candidates=self.sample_method_candidates(),
            method_limit=4,
            method_addresses=["0xbfca7e0"],
        )

        self.assertEqual(plan["requestedMethodAddresses"], ["0xbfca7e0"])
        self.assertEqual(plan["methodProbeCount"], 1)
        self.assertEqual(plan["methodProbes"][0]["address"], "0xbfca7e0")

    def test_method_address_filter_rejects_non_hex(self):
        with self.assertRaises(ValueError) as raised:
            module.build_plan(
                self.sample_external_plan(),
                base=0x100000,
                method_candidates=self.sample_method_candidates(),
                method_limit=4,
                method_addresses=["bfca7e0"],
            )

        self.assertIn("unsupported package method trace address", str(raised.exception))

    def test_markdown_contains_method_probe_section(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            method_candidates=self.sample_method_candidates(),
            method_limit=1,
        )

        text = module.markdown(plan)

        self.assertIn("Method probes: `1`", text)
        self.assertIn("Method Probes", text)
        self.assertIn("non-promotable-method-probe", text)
        self.assertIn("Method GDB Commands", text)

    def test_anchor_filter_can_select_multiple_package_families(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            anchors=["LoadPackage", "StaticLoadClass"],
            limit=4,
        )

        self.assertEqual(plan["seedCount"], 2)
        self.assertEqual([seed["name"] for seed in plan["seeds"]], ["LoadPackage", "StaticLoadClass"])
        self.assertEqual(
            plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ANCHOR"],
            "LoadPackage,StaticLoadClass",
        )
        self.assertEqual(plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"], "2")
        self.assertIn("rwatch *(char*)0x5be6260", plan["gdb"])
        self.assertIn("rwatch *(char*)0x6be6260", plan["gdb"])

    def test_anchor_filter_accepts_comma_separated_values_and_deduplicates(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            anchors=["LoadPackage, StaticLoadClass", "LoadPackage"],
            limit=4,
        )

        self.assertEqual(plan["seedSelection"]["requestedAnchors"], ["LoadPackage", "StaticLoadClass"])
        self.assertEqual([seed["name"] for seed in plan["seeds"]], ["LoadPackage", "StaticLoadClass"])

    def test_seed_address_filter_selects_exact_offsets(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            anchors=["LoadObject"],
            seed_addresses=["0x814c33"],
            limit=4,
        )

        self.assertEqual(plan["seedCount"], 1)
        self.assertEqual(plan["seeds"][0]["address"], "0x814c33")
        self.assertEqual(plan["seedSelection"]["requestedSeedAddresses"], ["0x814c33"])
        self.assertIn("Requested seed addresses", module.markdown(plan))

    def test_seed_address_filter_rejects_non_hex(self):
        with self.assertRaises(ValueError) as raised:
            module.build_plan(self.sample_external_plan(), base=0x100000, seed_addresses=["814c33"])

        self.assertIn("unsupported package runtime trace seed address", str(raised.exception))

    def test_anchor_filter_rejects_unsupported_anchor(self):
        with self.assertRaises(ValueError) as raised:
            module.build_plan(self.sample_external_plan(), base=0x100000, anchors=["LoadPackage,MissingAnchor"])

        self.assertIn("unsupported package runtime trace anchor: MissingAnchor", str(raised.exception))

    def test_anchor_filter_rejects_empty_anchor(self):
        with self.assertRaises(ValueError) as raised:
            module.build_plan(self.sample_external_plan(), base=0x100000, anchors=["LoadPackage,"])

        self.assertIn("anchor must be a non-empty string", str(raised.exception))

    def test_recommended_trace_env_only_names_selected_watchpoint_families(self):
        plan = module.build_plan(self.sample_external_plan(), base=0x100000, limit=1)

        self.assertEqual([seed["name"] for seed in plan["seeds"]], ["LoadPackage"])
        self.assertEqual(plan["seedSelection"]["availableByFamily"]["StaticLoadClass"], 1)
        self.assertEqual(plan["seedSelection"]["availableByFamily"]["LoadObject"], 1)
        self.assertEqual(
            plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ANCHOR"],
            "LoadPackage",
        )
        self.assertEqual(plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"], "1")

    def test_recommended_trace_env_caps_hardware_watchpoint_limit(self):
        external = self.sample_external_plan()
        external["historicalStringSeeds"].extend(
            [
                {
                    "name": "LoadObject",
                    "address": "0x815640",
                    "promotion": "non-promotable-string-only",
                    "sources": ["surface.md"],
                    "use": "trace only",
                },
                {
                    "name": "ResolveName",
                    "address": "0x1268545",
                    "promotion": "non-promotable-string-only",
                    "sources": ["surface.md"],
                    "use": "trace only",
                },
            ]
        )

        plan = module.build_plan(external, base=0x100000, limit=5)

        self.assertEqual(plan["seedCount"], 5)
        self.assertEqual(plan["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"], "4")
        self.assertEqual(plan["hardwareReadWatchpointLimit"], 4)

    def test_anchor_filter_reports_missing_requested_anchor(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            anchors=["ResolveName"],
            limit=4,
        )

        self.assertEqual(plan["seedCount"], 0)
        self.assertEqual(plan["seedSelection"]["requestedAnchors"], ["ResolveName"])
        self.assertEqual(plan["seedSelection"]["missingRequestedAnchors"], ["ResolveName"])
        self.assertIn("no package runtime trace seeds selected", plan["blockers"])
        self.assertIn("requested package trace anchors are missing: ResolveName", plan["blockers"])
        self.assertIn("Missing requested anchors", module.markdown(plan))
        self.assertIn("Blockers", module.markdown(plan))

    def test_pie_base_from_maps_handles_nonzero_executable_mapping_offset(self):
        lines = [
            "555555400000-555555401000 r--p 00000000 08:01 1 /srv/DuneSandboxServer-Linux-Shipping",
            "555555601000-555555900000 r-xp 00002000 08:01 1 /srv/DuneSandboxServer-Linux-Shipping",
            "555555900000-555555a00000 r--p 00301000 08:01 1 /srv/DuneSandboxServer-Linux-Shipping",
        ]

        base = module.pie_base_from_maps(lines, "/srv/DuneSandboxServer-Linux-Shipping")

        self.assertEqual(base, 0x555555400000)

    def test_pie_base_from_maps_falls_back_to_generic_file_mapping(self):
        lines = [
            "7ffff7f00000-7ffff7f10000 r-xp 00000000 08:01 2 /lib/x86_64-linux-gnu/libc.so.6",
            "555555400000-555555401000 r--p 00000000 08:01 1 /opt/ExampleGame/Binaries/Linux/ExampleGame",
            "555555601000-555555900000 r-xp 00002000 08:01 1 /opt/ExampleGame/Binaries/Linux/ExampleGame",
            "555555900000-555555a00000 r--p 00301000 08:01 1 /opt/ExampleGame/Binaries/Linux/ExampleGame",
        ]

        base = module.pie_base_from_maps(lines)

        self.assertEqual(base, 0x555555400000)

    def test_pie_base_from_maps_uses_generic_file_mapping_when_exe_is_unresolved(self):
        lines = [
            "55e2161e5000-55e22a88d000 r-xp 00000000 00:9d 1 /home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
            "55e22a88d000-55e22c60f000 r--p 146a7000 00:9d 1 /home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
        ]

        base = module.pie_base_from_maps(lines, "/proc/3212164/exe")

        self.assertEqual(base, 0x55E2161E5000)

    def test_pie_base_for_pid_uses_sudo_maps_fallback(self):
        maps = "\n".join(
            [
                "555555400000-555555401000 r--p 00000000 08:01 1 /srv/DuneSandboxServer-Linux-Shipping",
                "555555601000-555555900000 r-xp 00002000 08:01 1 /srv/DuneSandboxServer-Linux-Shipping",
            ]
        )

        with mock.patch.object(module.Path, "resolve", side_effect=OSError), \
             mock.patch.object(module.Path, "read_text", side_effect=OSError), \
             mock.patch.object(module, "run_capture") as run_capture:
            run_capture.side_effect = [
                subprocess.CompletedProcess(["sudo", "-n", "readlink"], 0, "/srv/DuneSandboxServer-Linux-Shipping\n", ""),
                subprocess.CompletedProcess(["sudo", "-n", "cat"], 0, maps, ""),
            ]

            self.assertEqual(module.pie_base_for_pid(4242), 0x555555400000)

        self.assertEqual(run_capture.call_args_list[0].args[0][:3], ["sudo", "-n", "readlink"])
        self.assertEqual(run_capture.call_args_list[1].args[0][:3], ["sudo", "-n", "cat"])

    def test_build_id_for_pid_uses_sudo_readelf_fallback(self):
        with mock.patch.object(module, "run_capture") as run_capture:
            run_capture.side_effect = [
                subprocess.CompletedProcess(["readelf"], 1, "", ""),
                subprocess.CompletedProcess(["sudo", "-n", "readelf"], 0, "    Build ID: abc123\n", ""),
            ]

            self.assertEqual(module.build_id_for_pid(4242), "abc123")

        self.assertEqual(run_capture.call_args_list[0].args[0][:2], ["readelf", "-n"])
        self.assertEqual(run_capture.call_args_list[1].args[0][:3], ["sudo", "-n", "readelf"])

    def test_markdown_contains_gdb_commands(self):
        plan = module.build_plan(self.sample_external_plan(), base=0x100000, limit=1)

        text = module.markdown(plan)

        self.assertIn("UE4SS Package Runtime Trace Plan", text)
        self.assertIn("Available by family", text)
        self.assertIn("Skipped by family", text)
        self.assertIn("Recommended wrapper env", text)
        self.assertIn("Source promotion acceptance schema", text)
        self.assertIn("dune-ue4ss-package-anchor-promotion-acceptance/v1", text)
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage", text)
        self.assertIn("GDB Commands", text)
        self.assertIn("UE4SS_PACKAGE_TRACE_HIT", text)

    def test_cli_writes_combined_gdb_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "external.json"
            methods = Path(tmp) / "methods.json"
            gdb = Path(tmp) / "trace.gdb"
            external.write_text(json.dumps(self.sample_external_plan()), encoding="utf-8")
            methods.write_text(json.dumps(self.sample_method_candidates()), encoding="utf-8")

            rc = module.main(
                [
                    "--external-plan",
                    str(external),
                    "--base",
                    "0x100000",
                    "--method-candidates",
                    str(methods),
                    "--method-limit",
                    "1",
                    "--gdb-out",
                    str(gdb),
                    "--format",
                    "json",
                ]
            )

            self.assertEqual(rc, 0)
            text = gdb.read_text(encoding="utf-8")
            self.assertIn("rwatch", text)
            self.assertIn("UE4SS_PACKAGE_TRACE_HIT", text)
            self.assertIn("UE4SS_PACKAGE_METHOD_TRACE_HIT", text)

    def test_cli_writes_method_gdb_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "external.json"
            methods = Path(tmp) / "methods.json"
            method_gdb = Path(tmp) / "method-trace.gdb"
            external.write_text(json.dumps(self.sample_external_plan()), encoding="utf-8")
            methods.write_text(json.dumps(self.sample_method_candidates()), encoding="utf-8")

            rc = module.main(
                [
                    "--external-plan",
                    str(external),
                    "--base",
                    "0x100000",
                    "--method-candidates",
                    str(methods),
                    "--method-limit",
                    "1",
                    "--method-gdb-out",
                    str(method_gdb),
                    "--format",
                    "json",
                ]
            )

            self.assertEqual(rc, 0)
            self.assertIn("UE4SS_PACKAGE_METHOD_TRACE_HIT", method_gdb.read_text(encoding="utf-8"))

    def test_cli_rejects_wrong_schema_external_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "not-external-plan.json"
            payload = self.sample_external_plan()
            payload["schemaVersion"] = "dune-ue4ss-evidence-inventory/v1"
            external.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                module.main(["--external-plan", str(external), "--base", "0x100000", "--format", "json"])

        self.assertIn("expected 'dune-ue4ss-package-external-symbol-plan/v1'", str(raised.exception))

    def test_external_plan_seeds_must_be_array(self):
        payload = self.sample_external_plan()
        payload["historicalStringSeeds"] = {}

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn("historicalStringSeeds must be a JSON array", str(raised.exception))

    def test_external_plan_requires_promotion_acceptance_object(self):
        for value in (None, []):
            with self.subTest(value=value):
                payload = self.sample_external_plan()
                if value is None:
                    payload.pop("promotionAcceptance")
                else:
                    payload["promotionAcceptance"] = value

                with self.assertRaises(ValueError) as raised:
                    module.build_plan(payload, base=0x100000)

                self.assertIn("promotionAcceptance must be a JSON object", str(raised.exception))

    def test_external_plan_requires_current_promotion_acceptance_schema(self):
        payload = self.sample_external_plan()
        payload["promotionAcceptance"]["schemaVersion"] = "old-schema"

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn(
            "expected 'dune-ue4ss-package-anchor-promotion-acceptance/v1'",
            str(raised.exception),
        )

    def test_external_plan_seed_rows_must_be_objects(self):
        payload = self.sample_external_plan()
        payload["historicalStringSeeds"] = [[]]

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn("historicalStringSeeds[0] must be a JSON object", str(raised.exception))

    def test_external_plan_binary_must_be_object(self):
        payload = self.sample_external_plan()
        payload["binary"] = []

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn("binary must be a JSON object", str(raised.exception))

    def test_external_plan_build_id_must_be_hex_empty_or_unknown(self):
        for build_id in ('abc"123', "abc 123", "../abc", 123):
            with self.subTest(build_id=build_id):
                payload = self.sample_external_plan()
                payload["binary"]["buildId"] = build_id

                with self.assertRaises(ValueError) as raised:
                    module.build_plan(payload, base=0x100000)

                self.assertIn("binary.buildId must be hex, empty, or unknown", str(raised.exception))

    def test_external_plan_allows_empty_or_unknown_build_id(self):
        for build_id in ("", "unknown"):
            with self.subTest(build_id=build_id):
                payload = self.sample_external_plan()
                payload["binary"]["buildId"] = build_id

                plan = module.build_plan(payload, base=0x100000)

                self.assertEqual(plan["expectedBuildId"], build_id)

    def test_external_plan_seed_name_must_be_supported_package_anchor(self):
        payload = self.sample_external_plan()
        payload["historicalStringSeeds"][0]["name"] = "UnrelatedString"

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn("unsupported package seed name: UnrelatedString", str(raised.exception))

    def test_external_plan_seed_address_must_be_hex(self):
        payload = self.sample_external_plan()
        payload["historicalStringSeeds"][0]["address"] = "not-hex"

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn("historicalStringSeeds[0] has invalid hex address", str(raised.exception))

    def test_external_plan_seed_address_must_be_positive(self):
        payload = self.sample_external_plan()
        payload["historicalStringSeeds"][0]["address"] = "0x0"

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn("historicalStringSeeds[0] has non-positive trace address", str(raised.exception))

    def test_external_plan_rejects_duplicate_package_trace_seed(self):
        payload = self.sample_external_plan()
        payload["historicalStringSeeds"].append(
            {
                "name": "LoadPackage",
                "address": "0x05AE6260",
                "promotion": "non-promotable-string-only",
                "sources": ["other.md"],
                "use": "trace only",
            }
        )

        with self.assertRaises(ValueError) as raised:
            module.build_plan(payload, base=0x100000)

        self.assertIn(
            "historicalStringSeeds[3] duplicates package trace seed LoadPackage@0x5ae6260 from historicalStringSeeds[1]",
            str(raised.exception),
        )

    def test_build_plan_records_actual_external_plan_source(self):
        plan = module.build_plan(
            self.sample_external_plan(),
            base=0x100000,
            source_external_plan="/tmp/custom-package-plan.json",
        )

        self.assertEqual(plan["sourceExternalPlan"], "/tmp/custom-package-plan.json")

    def test_build_plan_rejects_malformed_external_plan_source(self):
        cases = (
            ("", "source external plan must be a non-empty single-line path"),
            (" \t", "source external plan must be a non-empty single-line path"),
            ("/tmp/package-plan.json\n/tmp/stale.json", "source external plan must be a non-empty single-line path"),
            (["/tmp/package-plan.json"], "source external plan must be a scalar path"),
        )
        for source_external_plan, message in cases:
            with self.subTest(source_external_plan=source_external_plan):
                with self.assertRaises(ValueError) as raised:
                    module.build_plan(
                        self.sample_external_plan(),
                        base=0x100000,
                        source_external_plan=source_external_plan,
                    )

                self.assertIn(message, str(raised.exception))

    def test_build_plan_requires_base_or_pid(self):
        with self.assertRaises(ValueError):
            module.build_plan(self.sample_external_plan())

    def test_build_plan_rejects_non_positive_trace_seed_limit(self):
        with self.assertRaises(ValueError) as raised:
            module.build_plan(self.sample_external_plan(), base=0x100000, limit=0)

        self.assertIn("seed limit must be a positive integer", str(raised.exception))

    def test_build_plan_rejects_non_integer_trace_seed_limit(self):
        for limit in ("1", 1.5, True):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError) as raised:
                    module.build_plan(self.sample_external_plan(), base=0x100000, limit=limit)

                self.assertIn("seed limit must be a positive integer", str(raised.exception))

    def test_cli_rejects_non_positive_trace_seed_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "external.json"
            external.write_text(json.dumps(self.sample_external_plan()), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                module.main(["--external-plan", str(external), "--base", "0x100000", "--limit", "0", "--format", "json"])

        self.assertIn("seed limit must be a positive integer", str(raised.exception))

    def test_cli_rejects_malformed_gdb_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp) / "external.json"
            external.write_text(json.dumps(self.sample_external_plan()), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                module.main(
                    [
                        "--external-plan",
                        str(external),
                        "--base",
                        "0x100000",
                        "--gdb-out",
                        "/tmp/trace.gdb\n/tmp/stale.gdb",
                        "--format",
                        "json",
                    ]
                )

        self.assertIn("--gdb-out must be a non-empty single-line path", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
