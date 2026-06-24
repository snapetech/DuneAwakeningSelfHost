#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-source-abi-recovery.py"

spec = importlib.util.spec_from_file_location("source_abi_recovery", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class SourceAbiRecoveryTests(unittest.TestCase):
    def write_loader(self, root):
        path = root / "loader.c"
        path.write_text(
            """
            typedef void *(*LoadAssetPackageStaticLoadObjectFn)(void *, void *, const wchar_t *, const wchar_t *, uint32_t, void *, int);
            typedef void *(*LoadAssetPackageLoadPackageFn)(void *, const wchar_t *, uint32_t);
            static const char *a = "UObject*(UClass*,UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*,bool)";
            static const char *b = "UPackage*(UPackage*,const TCHAR*,uint32)";
            static void f(void) {
              int ok = observed_unit_bytes == sizeof(wchar_t);
              load_asset_package_run_guarded_native_call(0, 0, 0, 0, 0);
            }
            """,
            encoding="utf-8",
        )
        return path

    def test_extracts_loader_contract_and_reports_missing_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = self.write_loader(Path(tmp))

            summary = module.summarize(
                loader,
                route_evidence={"routeCount": 12, "promotableRouteCount": 0},
                donor_search={"candidateCount": 2, "usableCandidateCount": 0, "candidates": []},
            )

        self.assertFalse(summary["complete"])
        self.assertEqual(summary["loaderContract"]["typedefCount"], 2)
        self.assertEqual(summary["loaderContract"]["requiredSignatureCount"], 2)
        self.assertTrue(summary["loaderContract"]["requiresObservedTcharUnitMatch"])
        self.assertTrue(summary["loaderContract"]["hasGuardedNativeCallAdapter"])
        self.assertIn("no target-image package-loading anchor", summary["blockers"][0])

    def test_marks_complete_when_anchor_and_donor_evidence_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = self.write_loader(Path(tmp))

            summary = module.summarize(
                loader,
                route_evidence={"routeCount": 12, "promotableRouteCount": 1, "complete": True},
                donor_search={"candidateCount": 1, "usableCandidateCount": 1, "candidates": []},
            )

        self.assertTrue(summary["complete"])
        self.assertEqual(summary["blockers"], [])


if __name__ == "__main__":
    unittest.main()
