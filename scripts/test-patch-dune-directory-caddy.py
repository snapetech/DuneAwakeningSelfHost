#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("patch_dune_directory_caddy", ROOT / "scripts" / "patch-dune-directory-caddy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


FIXTURE = """\
(dune_static_site) {
	route {
		header {
			Content-Security-Policy "default-src 'none'; connect-src 'self'; img-src 'self' data:"
		}
		@cached_assets {
			path /style.css /app.js /hagga-map.svg /hagga-basin.webp /deep-desert-map.svg /deep-desert.webp
		}
		@short_lived_data {
			path /players.json /hagga-pois.json
		}
		@scanner_paths {
			path /.env*
		}
		@static_files {
			path / /style.css /app.js /status.html /players.json /hagga-pois.json /hagga-map.svg /hagga-basin.webp /deep-desert-map.svg /deep-desert.webp
		}
	}
}

(snape_game_portal) {
	route {}
}
"""


class CaddyPatchTests(unittest.TestCase):
    def test_patch_is_complete_and_idempotent(self):
        rendered, changed = MODULE.patch_text(FIXTURE)
        self.assertTrue(changed)
        self.assertIn("connect-src 'self' https:", rendered)
        self.assertIn('Access-Control-Allow-Origin "*"', rendered)
        self.assertIn("/directory/directory.json", rendered)
        self.assertIn("redir @directory_bare /directory/ 308", rendered)
        again, changed_again = MODULE.patch_text(rendered)
        self.assertFalse(changed_again)
        self.assertEqual(rendered, again)

    def test_refuses_unreviewed_or_partial_shapes(self):
        with self.assertRaises(MODULE.PatchError):
            MODULE.patch_text(FIXTURE.replace(MODULE.STATIC_BEFORE, "path /"))
        partial = FIXTURE.replace("\t\t@scanner_paths {", f"\t\t{MODULE.MARKER}\n\t\t@scanner_paths {{")
        with self.assertRaises(MODULE.PatchError):
            MODULE.patch_text(partial)


if __name__ == "__main__":
    unittest.main()
