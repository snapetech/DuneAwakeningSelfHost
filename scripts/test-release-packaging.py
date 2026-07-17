#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build-release.py"
FINALIZE = ROOT / "scripts" / "finalize-release.py"
INSTALL = ROOT / "scripts" / "install-release.sh"
TAG = "v0.1.0-beta.1"


def run(*args, cwd=None, check=True, env=None):
    return subprocess.run(args, cwd=cwd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.repo = self.base / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "config").mkdir()
        shutil.copy2(INSTALL, self.repo / "scripts" / "install-release.sh")
        (self.repo / "VERSION").write_text("0.1.0-beta.1\n", encoding="utf-8")
        (self.repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (self.repo / ".env.example").write_text("DUNE_TEST=release\n", encoding="utf-8")
        (self.repo / "config" / "UserGame.ini").write_text("[Config]\nValue=release\n", encoding="utf-8")
        (self.repo / "data" / "exchange-price-snapshots").mkdir(parents=True)
        (self.repo / "data" / "exchange-price-snapshots" / "fixture.json").write_text("{}\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# DASH fixture\n", encoding="utf-8")
        (self.repo / "LICENSE").write_text("MIT fixture\n", encoding="utf-8")
        run("git", "init", "-q", cwd=self.repo)
        run("git", "config", "user.name", "DASH Test", cwd=self.repo)
        run("git", "config", "user.email", "dash-test@example.invalid", cwd=self.repo)
        run("git", "add", ".", cwd=self.repo)
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        run("git", "commit", "-qm", "fixture", cwd=self.repo, env=env)
        self.commit = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()

    def tearDown(self):
        self.temp.cleanup()

    def populate_loader_assets(self, output):
        names = (
            f"dune-linux-server-loader-{TAG}-linux-x86_64.tar.gz",
            f"dune-linux-client-loader-{TAG}-linux-x86_64.tar.gz",
            f"dune-windows-client-loader-{TAG}-windows-x86_64.tar.gz",
        )
        for name in names:
            archive = output / name
            archive.write_bytes(("fixture:" + name).encode("utf-8"))
            pathlib.Path(str(archive) + ".sha256").write_text(f"{sha(archive)}  {name}\n", encoding="utf-8")
            pathlib.Path(str(archive) + ".verification.json").write_text(
                json.dumps({"schemaVersion": "dune-loader-artifact-verification/v1", "passed": True, "targets": {}}) + "\n",
                encoding="utf-8",
            )
        (output / "RELEASE_NOTES.md").write_text("# Fixture release\n", encoding="utf-8")

    def build(self, output):
        output.mkdir()
        run("python3", str(BUILD), "--root", str(self.repo), "--version", TAG, "--ref", self.commit, "--output-dir", str(output))
        self.populate_loader_assets(output)
        run("python3", str(FINALIZE), "finalize", "--root", str(self.repo), "--version", TAG, "--ref", self.commit, "--asset-dir", str(output))
        run("python3", str(FINALIZE), "verify", "--version", TAG, "--ref", self.commit, "--asset-dir", str(output))

    def test_release_is_reproducible_verifiable_and_installable(self):
        first, second = self.base / "first", self.base / "second"
        self.build(first)
        self.build(second)
        first_hashes = {path.name: sha(path) for path in first.iterdir()}
        second_hashes = {path.name: sha(path) for path in second.iterdir()}
        self.assertEqual(first_hashes, second_hashes)

        archive = first / f"dash-{TAG}-linux-x86_64.tar.gz"
        prefix, state = self.base / "opt" / "dash", self.base / "var" / "lib" / "dash"
        run(
            "bash", str(INSTALL), "install", "--ref", self.commit, "--sha256", sha(archive),
            "--archive", str(archive), "--prefix", str(prefix), "--state-root", str(state), "--activate",
        )
        installed = json.loads((prefix / "current" / ".dash-release.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["commit"], self.commit)
        self.assertEqual(installed["releaseVersion"], "0.1.0-beta.1")

    def test_corruption_is_rejected(self):
        output = self.base / "release"
        self.build(output)
        sbom = output / f"dash-{TAG}-linux-x86_64.spdx.json"
        sbom.write_text("{}\n", encoding="utf-8")
        result = run(
            "python3", str(FINALIZE), "verify", "--version", TAG, "--ref", self.commit, "--asset-dir", str(output), check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stdout)

    def test_version_and_commit_binding_is_enforced(self):
        output = self.base / "release"
        result = run(
            "python3", str(BUILD), "--root", str(self.repo), "--version", "v0.1.1", "--ref", self.commit,
            "--output-dir", str(output), check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VERSION contains", result.stdout)

    def test_private_runtime_paths_are_rejected(self):
        (self.repo / ".env").write_text("SECRET=not-for-release\n", encoding="utf-8")
        run("git", "add", "-f", ".env", cwd=self.repo)
        run("git", "commit", "-qm", "bad runtime file", cwd=self.repo)
        bad_commit = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        result = run(
            "python3", str(BUILD), "--root", str(self.repo), "--version", TAG, "--ref", bad_commit,
            "--output-dir", str(self.base / "bad-release"), check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private/runtime path is not publishable", result.stdout)

    def test_release_workflow_is_pinned_and_noninteractive(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        publisher = (ROOT / "scripts" / "publish-github-release.sh").read_text(encoding="utf-8")
        self.assertIn('tags:\n      - "v*"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")
        self.assertRegex(workflow, r"actions/attest@[0-9a-f]{40}")
        self.assertIn("scripts/publish-github-release.sh", workflow)
        self.assertNotIn("environment:", workflow)
        self.assertIn('"${GITHUB_ACTIONS:-}" == true', publisher)
        self.assertIn("grep -q '(HTTP 403)'", publisher)
        self.assertIn('[[ "$immutable" == true ]]', publisher)
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("dist/release/", ignored)


if __name__ == "__main__":
    unittest.main()
