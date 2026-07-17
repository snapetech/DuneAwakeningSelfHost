#!/usr/bin/env python3
"""Patch a reviewed dune_static_site Caddy snippet for the public directory."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import pathlib
import shutil
import socket
import stat
import tempfile


MARKER = "# DASH signed federated directory"
PORTAL_MARKER = "# DASH signed federated directory portal aliases"
START = "(dune_static_site) {"
END = "\n}\n\n(snape_game_portal) {"
PORTAL_START = "(snape_game_portal) {"
PORTAL_END = "\n}\n\nhttps://palworld.snape.tech {"

CSP_BEFORE = "connect-src 'self'; img-src 'self' data:"
CSP_AFTER = "connect-src 'self' https:; img-src 'self' data:"
CACHED_BEFORE = "path /style.css /app.js /hagga-map.svg /hagga-basin.webp /deep-desert-map.svg /deep-desert.webp"
CACHED_AFTER = CACHED_BEFORE + " /directory/directory.css /directory/directory.js"
SHORT_BEFORE = "path /players.json /hagga-pois.json"
SHORT_AFTER = SHORT_BEFORE + " /directory-entry.json /directory/directory.json"
STATIC_BEFORE = "path / /style.css /app.js /status.html /players.json /hagga-pois.json /hagga-map.svg /hagga-basin.webp /deep-desert-map.svg /deep-desert.webp"
STATIC_AFTER = STATIC_BEFORE + " /directory-entry.json /directory/ /directory/index.html /directory/directory.css /directory/directory.js /directory/directory.json"

DIRECTORY_HEADERS = """\
		# DASH signed federated directory
		@directory_descriptor {
			path /directory-entry.json
		}
		header @directory_descriptor {
			Access-Control-Allow-Origin "*"
			Cross-Origin-Resource-Policy "cross-origin"
			Cache-Control "no-store"
			CDN-Cache-Control "no-store"
			Cloudflare-CDN-Cache-Control "no-store"
			-Pragma
			-Expires
		}

"""

DIRECTORY_REDIRECT = """\
		@directory_bare {
			path /directory
		}
		redir @directory_bare /directory/ 308

"""

PORTAL_CACHED_BEFORE = "path /landing.css /landing-generated.css /assets/*.svg /assets/*.webp /assets/*.png /assets/*.jpg /assets/*.jpeg /palworld/style.css /palworld/app.js /palworld/palpagos-map.webp /dune/style.css /dune/app.js /dune/hagga-map.svg /dune/hagga-basin.webp /dune/deep-desert-map.svg /dune/deep-desert.webp"
PORTAL_CACHED_AFTER = PORTAL_CACHED_BEFORE + " /dune/directory/directory.css /dune/directory/directory.js /duneawakening/directory/directory.css /duneawakening/directory/directory.js /da/directory/directory.css /da/directory/directory.js"
PORTAL_SHORT_BEFORE = "path /palworld/status.json /palworld/locations.json /dune/players.json /dune/hagga-pois.json"
PORTAL_SHORT_AFTER = PORTAL_SHORT_BEFORE + " /dune/directory-entry.json /dune/directory/directory.json /duneawakening/directory-entry.json /duneawakening/directory/directory.json /da/directory-entry.json /da/directory/directory.json"
ALIAS_FILES_BEFORE = "path / /style.css /app.js /status.html /players.json /hagga-pois.json /hagga-map.svg /hagga-basin.webp /deep-desert-map.svg /deep-desert.webp"
ALIAS_FILES_AFTER = ALIAS_FILES_BEFORE + " /directory-entry.json /directory/ /directory/index.html /directory/directory.css /directory/directory.js /directory/directory.json"

PORTAL_HEADERS = """\
		# DASH signed federated directory portal aliases
		@directory_descriptors {
			path /dune/directory-entry.json /duneawakening/directory-entry.json /da/directory-entry.json
		}
		header @directory_descriptors {
			Access-Control-Allow-Origin "*"
			Cross-Origin-Resource-Policy "cross-origin"
			Cache-Control "no-store"
			CDN-Cache-Control "no-store"
			Cloudflare-CDN-Cache-Control "no-store"
			-Pragma
			-Expires
		}

"""

PORTAL_REDIRECT = """\
		@directory_alias_bare {
			path /dune/directory /duneawakening/directory /da/directory
		}
		redir @directory_alias_bare {path}/ 308

"""


class PatchError(ValueError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"expected exactly one {label}; found {count}")
    return text.replace(old, new, 1)


def verify_patched(snippet: str) -> None:
    required = (
        MARKER, CSP_AFTER, CACHED_AFTER, SHORT_AFTER, STATIC_AFTER,
        "Access-Control-Allow-Origin \"*\"", "Cross-Origin-Resource-Policy \"cross-origin\"",
        "redir @directory_bare /directory/ 308",
    )
    missing = [value for value in required if value not in snippet]
    if missing:
        raise PatchError("existing directory patch is incomplete: " + ", ".join(missing))
    for path in (
        "/directory-entry.json", "/directory/", "/directory/index.html",
        "/directory/directory.css", "/directory/directory.js", "/directory/directory.json",
    ):
        if path not in snippet:
            raise PatchError(f"existing directory patch omits {path}")


def patch_direct(text: str) -> tuple[str, bool]:
    start = text.index(START)
    end = text.index(END, start) + 3
    snippet = text[start:end]
    if MARKER in snippet:
        verify_patched(snippet)
        return text, False

    snippet = replace_once(snippet, CSP_BEFORE, CSP_AFTER, "Dune connect-src policy")
    snippet = replace_once(snippet, CACHED_BEFORE, CACHED_AFTER, "Dune cached-asset matcher")
    snippet = replace_once(snippet, SHORT_BEFORE, SHORT_AFTER, "Dune short-lived-data matcher")
    snippet = replace_once(snippet, STATIC_BEFORE, STATIC_AFTER, "Dune static-file matcher")
    snippet = replace_once(snippet, "\t\t@scanner_paths {", DIRECTORY_HEADERS + "\t\t@scanner_paths {", "scanner matcher insertion point")
    snippet = replace_once(snippet, "\t\t@static_files {", DIRECTORY_REDIRECT + "\t\t@static_files {", "static matcher insertion point")
    verify_patched(snippet)
    return text[:start] + snippet + text[end:], True


def verify_portal_patched(snippet: str) -> None:
    required = (
        PORTAL_MARKER, CSP_AFTER, PORTAL_CACHED_AFTER, PORTAL_SHORT_AFTER,
        'Access-Control-Allow-Origin "*"', 'Cross-Origin-Resource-Policy "cross-origin"',
        "redir @directory_alias_bare {path}/ 308",
    )
    for label in ("dune", "duneawakening", "da"):
        required += (f"@{label}_files {ALIAS_FILES_AFTER}",)
    missing = [value for value in required if value not in snippet]
    if missing:
        raise PatchError("existing portal directory patch is incomplete: " + ", ".join(missing))


def patch_portal(text: str) -> tuple[str, bool]:
    start = text.index(PORTAL_START)
    end = text.index(PORTAL_END, start) + 3
    snippet = text[start:end]
    if PORTAL_MARKER in snippet:
        verify_portal_patched(snippet)
        return text, False
    snippet = replace_once(snippet, CSP_BEFORE, CSP_AFTER, "portal connect-src policy")
    snippet = replace_once(snippet, PORTAL_CACHED_BEFORE, PORTAL_CACHED_AFTER, "portal cached-asset matcher")
    snippet = replace_once(snippet, PORTAL_SHORT_BEFORE, PORTAL_SHORT_AFTER, "portal short-lived-data matcher")
    for label in ("dune", "duneawakening", "da"):
        snippet = replace_once(
            snippet, f"@{label}_files {ALIAS_FILES_BEFORE}", f"@{label}_files {ALIAS_FILES_AFTER}",
            f"{label} alias file matcher",
        )
    snippet = replace_once(snippet, "\t\t@unexpected_methods {", PORTAL_HEADERS + "\t\t@unexpected_methods {", "portal method matcher insertion point")
    snippet = replace_once(snippet, "\t\thandle_path /dune/* {", PORTAL_REDIRECT + "\t\thandle_path /dune/* {", "portal Dune handler insertion point")
    verify_portal_patched(snippet)
    return text[:start] + snippet + text[end:], True


def patch_text(text: str) -> tuple[str, bool]:
    if text.count(START) != 1 or text.count(END) != 1 or text.count(PORTAL_START) != 1 or text.count(PORTAL_END) != 1:
        raise PatchError("reviewed Dune static/portal snippet boundaries were not found exactly once")
    text, direct_changed = patch_direct(text)
    text, portal_changed = patch_portal(text)
    return text, direct_changed or portal_changed


def atomic_write(path: pathlib.Path, payload: str, details: os.stat_result) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".dash-directory-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(details.st_mode))
        try:
            os.chown(temporary, details.st_uid, details.st_gid)
        except PermissionError:
            pass
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=pathlib.Path)
    parser.add_argument("--backup-dir", type=pathlib.Path)
    parser.add_argument("--required-host", default="")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.required_host and socket.gethostname().split(".", 1)[0] != args.required_host.split(".", 1)[0]:
        raise SystemExit(f"refusing Caddy mutation on {socket.gethostname()}; required host is {args.required_host}")
    try:
        details = args.file.lstat()
    except FileNotFoundError as exc:
        raise SystemExit(f"Caddyfile does not exist: {args.file}") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise SystemExit(f"Caddyfile must be a regular file, not a symlink: {args.file}")

    original = args.file.read_text(encoding="utf-8")
    try:
        rendered, changed = patch_text(original)
    except PatchError as exc:
        raise SystemExit(f"Caddy patch refused: {exc}") from exc
    if not args.execute:
        if changed:
            print("".join(difflib.unified_diff(original.splitlines(True), rendered.splitlines(True), fromfile=str(args.file), tofile=str(args.file) + ".patched")), end="")
        else:
            print(json.dumps({"ok": True, "changed": False, "file": str(args.file), "state": "already-patched"}, sort_keys=True))
        return 0
    if not changed:
        print(json.dumps({"ok": True, "changed": False, "file": str(args.file), "state": "already-patched"}, sort_keys=True))
        return 0

    backup_dir = args.backup_dir or args.file.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{args.file.name}.before-dash-directory-{timestamp}"
    if backup.exists():
        raise SystemExit(f"backup already exists: {backup}")
    shutil.copy2(args.file, backup)
    atomic_write(args.file, rendered, details)
    installed = args.file.read_text(encoding="utf-8")
    verify_patched(installed[installed.index(START):installed.index(END, installed.index(START)) + 3])
    verify_portal_patched(installed[installed.index(PORTAL_START):installed.index(PORTAL_END, installed.index(PORTAL_START)) + 3])
    print(json.dumps({"ok": True, "changed": True, "file": str(args.file), "backup": str(backup)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
