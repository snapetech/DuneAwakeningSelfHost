#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "scripts/loader-package-common.sh"
PACKAGERS = (
    ROOT / "scripts/package-linux-server-loader.sh",
    ROOT / "scripts/package-linux-client-loader.sh",
    ROOT / "scripts/package-windows-client-loader.sh",
)


def run_bash(body, *args, env=None):
    return subprocess.run(
        ["bash", "-c", body, "loader-package-test", *(str(arg) for arg in args)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


class LoaderPackageReproducibilityTests(unittest.TestCase):
    def test_every_packager_uses_shared_metadata_provenance_and_archive_helpers(self):
        for path in PACKAGERS:
            with self.subTest(packager=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn('source "$repo_root/scripts/loader-package-common.sh"', source)
                self.assertIn('loader_package_init_metadata "$repo_root"', source)
                self.assertIn("loader_package_write_provenance", source)
                self.assertIn("loader_package_create_archive", source)

    def test_archive_is_byte_identical_after_input_mtime_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            package = dist / "fixture-package"
            nested = package / "nested"
            nested.mkdir(parents=True)
            (package / "alpha.txt").write_text("alpha\n", encoding="utf-8")
            executable = nested / "tool.sh"
            executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            command = (
                'source "$1"; LOADER_PACKAGE_SOURCE_DATE_EPOCH=1700000000; '
                'loader_package_create_archive "$2" fixture-package "$3"'
            )
            run_bash(command, COMMON, dist, first)
            os.utime(package / "alpha.txt", (1800000000, 1800000000))
            os.utime(executable, (1900000000, 1900000000))
            run_bash(command, COMMON, dist, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                members = archive.getmembers()
            self.assertEqual([member.name for member in members], sorted(member.name for member in members))
            for member in members:
                self.assertEqual(member.mtime, 1700000000)
                self.assertEqual(member.uid, 0)
                self.assertEqual(member.gid, 0)

    def test_provenance_is_deterministic_and_binds_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "loader.bin"
            loader.write_bytes(b"loader fixture\n")
            first = root / "first.json"
            second = root / "second.json"
            env = os.environ.copy()
            env.update(
                {
                    "LOADER_PACKAGE_BUILT_UTC": "2023-11-14T22:13:20Z",
                    "LOADER_PACKAGE_SOURCE_DATE_EPOCH": "1700000000",
                    "LOADER_PACKAGE_SOURCE_COMMIT": "a" * 40,
                    "LOADER_PACKAGE_SOURCE_TREE": "b" * 40,
                    "LOADER_PACKAGE_SOURCE_DIRTY": "false",
                }
            )
            command = (
                'source "$1"; loader_package_write_provenance "$2" fixture-package '
                'linux-client fixture linux-x86_64 "$3" lib/loader.bin RelWithDebInfo'
            )
            run_bash(command, COMMON, first, loader, env=env)
            run_bash(command, COMMON, second, loader, env=env)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            payload = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(payload["loader"]["sha256"], hashlib.sha256(loader.read_bytes()).hexdigest())
            self.assertEqual(payload["loader"]["size"], loader.stat().st_size)
            self.assertFalse(payload["source"]["dirty"])

    def test_metadata_marks_untracked_source_as_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Package Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "package-test@example.invalid"], check=True)
            tracked = repo / "tracked.txt"
            tracked.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            env = os.environ.copy()
            env.update(
                {
                    "GIT_AUTHOR_DATE": "2023-11-14T22:13:20Z",
                    "GIT_COMMITTER_DATE": "2023-11-14T22:13:20Z",
                    "SOURCE_DATE_EPOCH": "1700000000",
                }
            )
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True, env=env)
            command = (
                'source "$1"; loader_package_init_metadata "$2"; '
                'printf "%s" "$LOADER_PACKAGE_SOURCE_DIRTY"'
            )
            clean = run_bash(command, COMMON, repo, env=env)
            self.assertEqual(clean.stdout, "false")
            (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            dirty = run_bash(command, COMMON, repo, env=env)
            self.assertEqual(dirty.stdout, "true")


if __name__ == "__main__":
    unittest.main()
