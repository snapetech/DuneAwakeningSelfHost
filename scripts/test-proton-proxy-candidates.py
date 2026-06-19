#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "proton-proxy-candidates.py",
    ROOT / "analysis" / "proton-proxy-candidates.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("proton_proxy_candidates", SCRIPT)
proxy_candidates = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(proxy_candidates)


class ProtonProxyCandidateTests(unittest.TestCase):
    def test_version_scores_above_non_imported_candidate(self):
        exe = Path("/tmp/game/Dune.exe")
        imports = {"version.dll": ["GetFileVersionInfoW"], "dxgi.dll": ["CreateDXGIFactory"]}
        with mock.patch.object(proxy_candidates, "objdump_imports", return_value=imports):
            summary = proxy_candidates.summarize(exe, [])

        names = [row["name"] for row in summary["candidates"][:2]]
        self.assertIn("version.dll", names)
        self.assertTrue(summary["best"]["imported"])

    def test_existing_file_lowers_score(self):
        imports = {"version.dll": ["VerQueryValueW"]}
        with mock.patch.object(proxy_candidates, "objdump_imports", return_value=imports):
            with mock.patch.object(Path, "exists", return_value=True):
                summary = proxy_candidates.summarize(Path("/tmp/game/Dune.exe"), ["version.dll"])

        version = next(row for row in summary["candidates"] if row["name"] == "version.dll")
        self.assertIn("existing-file-would-need-backup", version["notes"])


if __name__ == "__main__":
    unittest.main()
