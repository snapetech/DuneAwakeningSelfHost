#!/usr/bin/env python3
"""Apply narrow Base Reconstruction Tool action-state patches.

This is deliberately smaller than patch-brt-dd-tool-enable-binary.py. It does
not replace whole shared UGameItem* action methods. Each site changes one
observed false/failure branch that blocks the BRT action path when DD does not
initialize the same backing context as Hagga Basin.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

DEFAULT_BINARY = Path("/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping")


class PatchSite(NamedTuple):
    key: str
    name: str
    patterns: tuple[tuple[int | None, ...], ...]
    offset: int
    original: bytes
    patched: bytes


def hex_pattern(raw: str) -> tuple[int | None, ...]:
    values: list[int | None] = []
    for token in raw.split():
        if token in {"?", "??"}:
            values.append(None)
        else:
            values.append(int(token, 16))
    return tuple(values)


PATCHES = [
    PatchSite(
        key="can-use-empty-context",
        name="BRT can-use missing selected/backing context returns enabled",
        patterns=(
            hex_pattern(
                "4d 8b b4 24 10 01 00 00 4d 85 f6 74 07 "
                "41 f6 46 0b 60 74 05 45 31 f6 eb c2"
            ),
        ),
        offset=20,
        original=bytes.fromhex("45 31 f6"),
        patched=bytes.fromhex("41 b6 01"),
    ),
    PatchSite(
        key="state-empty-context",
        name="BRT action state missing selected/backing context returns enabled",
        patterns=(
            hex_pattern(
                "48 8b 81 10 01 00 00 48 85 c0 74 06 "
                "f6 40 0b 60 74 13 31 db 89 d8"
            ),
        ),
        offset=18,
        original=bytes.fromhex("31 db"),
        patched=bytes.fromhex("b3 01"),
    ),
    PatchSite(
        key="failure-reason-action-method",
        name="BRT action-method failure reason reports generic success reason",
        patterns=(
            hex_pattern(
                "48 8d bd 68 ff ff ff e8 ?? ?? ?? ?? "
                "48 8b bd 70 ff ff ff 48 85 ff 74 05 "
                "e8 ?? ?? ?? ?? 41 b6 32 e9 ?? ?? ?? ??"
            ),
        ),
        offset=29,
        original=bytes.fromhex("41 b6 32"),
        patched=bytes.fromhex("41 b6 03"),
    ),
    PatchSite(
        key="can-use-actor-lookup-null",
        name="BRT can-use missing actor lookup continues to enabled verdict",
        patterns=(
            hex_pattern(
                "4d 85 ff 74 17 48 89 df e8 ?? ?? ?? ?? "
                "48 85 c0 74 0a 41 b6 01 41 80 7f 55 01 "
                "?? 03 45 31 f6"
            ),
        ),
        offset=16,
        original=bytes.fromhex("74 0a"),
        patched=bytes.fromhex("90 90"),
    ),
    PatchSite(
        key="can-use-fallback-selected-actor",
        name="BRT can-use actor lookup uses selected/backing fallback accessor",
        patterns=(
            hex_pattern(
                "4d 8b be 30 01 00 00 4d 85 ff 75 14 "
                "4c 89 f7 e8 ?? ?? ?? ?? "
                "4d 8b be 30 01 00 00 4d 85 ff 74 17 "
                "48 89 df e8 ab 8d 2b ff 48 85 c0 74 0a "
                "41 b6 01 41 80 7f 55 01 ?? 03 45 31 f6"
            ),
        ),
        offset=36,
        original=bytes.fromhex("ab 8d 2b ff"),
        patched=bytes.fromhex("ab 8e 2b ff"),
    ),
    PatchSite(
        key="can-use-region-fail-join",
        name="BRT can-use buildable-region fail join returns enabled",
        patterns=(
            hex_pattern(
                "48 89 df e8 ?? ?? ?? ?? 48 85 c0 74 0a "
                "41 b6 01 41 80 7f 55 01 ?? 03 45 31 f6 "
                "48 8d bd 70 ff ff ff"
            ),
        ),
        offset=23,
        original=bytes.fromhex("45 31 f6"),
        patched=bytes.fromhex("41 b6 01"),
    ),
]


def selected_patches(raw: str) -> list[PatchSite]:
    requested = {site.strip() for site in raw.split(",") if site.strip()}
    valid = {site.key for site in PATCHES}
    if not requested:
        raise SystemExit("--sites cannot be empty")
    if requested == {"all"}:
        return PATCHES
    unknown = requested - valid
    if unknown:
        raise SystemExit(
            f"unknown --sites value(s): {', '.join(sorted(unknown))}; "
            f"valid values: all, {', '.join(sorted(valid))}"
        )
    return [site for site in PATCHES if site.key in requested]


def matches_at(data: bytes, start: int, pattern: tuple[int | None, ...]) -> bool:
    if start < 0 or start + len(pattern) > len(data):
        return False
    return all(value is None or data[start + index] == value for index, value in enumerate(pattern))


def find_pattern(data: bytes, pattern: tuple[int | None, ...]) -> list[int]:
    if not pattern:
        return []
    anchor_index = next((index for index, value in enumerate(pattern) if value is not None), None)
    if anchor_index is None:
        raise SystemExit("internal error: wildcard-only patch pattern is unsupported")
    anchor_value = pattern[anchor_index]
    assert anchor_value is not None

    hits: list[int] = []
    pos = 0
    while True:
        hit = data.find(bytes([anchor_value]), pos)
        if hit < 0:
            break
        start = hit - anchor_index
        if matches_at(data, start, pattern):
            hits.append(start)
        pos = hit + 1
    return hits


def find_site(data: bytes, site: PatchSite) -> tuple[int, bool]:
    hits: list[int] = []
    for pattern in site.patterns:
        prefix = pattern[:site.offset]
        suffix = pattern[site.offset + len(site.original):]
        for hit in find_pattern(data, prefix):
            patch_offset = hit + site.offset
            current = data[patch_offset:patch_offset + len(site.original)]
            suffix_offset = patch_offset + len(site.original)
            if (
                current in (site.original, site.patched)
                and matches_at(data, suffix_offset, suffix)
            ):
                hits.append(hit)
    hits = sorted(set(hits))
    if len(hits) != 1:
        raise SystemExit(
            f"{site.name}: expected one signature, found {len(hits)}: "
            f"{[hex(hit) for hit in hits]}"
        )

    patch_offset = hits[0] + site.offset
    current = data[patch_offset:patch_offset + len(site.original)]
    if current == site.original:
        return patch_offset, False
    if current == site.patched:
        return patch_offset, True
    raise SystemExit(
        f"{site.name}: unexpected bytes at 0x{patch_offset:x}: "
        f"{current.hex(' ')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument(
        "--sites",
        default="can-use-empty-context",
        help="comma-separated patch site keys: all, can-use-empty-context, "
        "state-empty-context, failure-reason-action-method, "
        "can-use-actor-lookup-null, can-use-fallback-selected-actor, "
        "can-use-region-fail-join",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args()

    data = args.binary.read_bytes()
    already_patched = []
    to_patch = []
    for site in selected_patches(args.sites):
        offset, is_patched = find_site(data, site)
        if is_patched:
            already_patched.append((site, offset))
        else:
            to_patch.append((site, offset))

    for site, offset in already_patched:
        print(f"already patched @ 0x{offset:x}: {site.name}")
    if not to_patch:
        print("requested BRT narrow action-state patch site(s) already applied; nothing to do")
        return

    sha_before = hashlib.sha256(data).hexdigest()
    patched = bytearray(data)
    for site, offset in to_patch:
        patched[offset:offset + len(site.original)] = site.patched
        print(
            f"patch @ 0x{offset:x}: {site.name}: "
            f"{site.original.hex(' ')} -> {site.patched.hex(' ')}"
        )
    sha_after = hashlib.sha256(bytes(patched)).hexdigest()

    if args.dry_run:
        print(f"DRY RUN: would patch {len(to_patch)} site(s).")
        print(f"  sha256 before: {sha_before}")
        print(f"  sha256 after:  {sha_after}")
        return

    if args.backup and not args.backup.exists():
        shutil.copy2(args.binary, args.backup)
        print(f"backup written: {args.backup}")
    args.binary.write_bytes(bytes(patched))
    print(f"patched OK: {args.binary}")
    print(f"  sha256 before: {sha_before}")
    print(f"  sha256 after:  {sha_after}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        sys.exit(str(exc))
