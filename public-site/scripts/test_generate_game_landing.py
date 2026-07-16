import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "public-site" / "scripts" / "generate-game-landing.py"
EXAMPLE = ROOT / "public-site" / "landing" / "game-links.example.json"


class GenerateGameLandingTests(unittest.TestCase):
    def run_generator(self, config, output):
        return subprocess.run(
            [str(SCRIPT), "--config", str(config), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_example_generates_dune_only_landing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "site"
            result = self.run_generator(EXAMPLE, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("Dune: Awakening", html)
            self.assertIn('href="/dune/"', html)
            self.assertEqual(html.count('class="game-link '), 1)
            self.assertEqual(len(list((output / "assets").iterdir())), 1)

    def test_same_manifest_produces_identical_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "site"
            first = self.run_generator(EXAMPLE, output)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
            second = self.run_generator(EXAMPLE, output)
            self.assertEqual(second.returncode, 0, second.stderr)
            after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_rejects_icon_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            manifest["games"][0]["icon"] = "../outside.svg"
            config = root / "config.json"
            config.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_generator(config, root / "site")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must stay inside", result.stderr)

    def test_rejects_executable_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "unsafe.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                encoding="utf-8",
            )
            manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            manifest["games"][0]["icon"] = "assets/unsafe.svg"
            config = root / "config.json"
            config.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_generator(config, root / "site")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe or invalid SVG", result.stderr)


if __name__ == "__main__":
    unittest.main()
