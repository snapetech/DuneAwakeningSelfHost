#!/usr/bin/env python3
"""Force Base Reconstruction Tool actions enabled in Deep Desert server binaries.

This is intentionally separate from the BuildingPiece/build limit patch. It
targets only UGameItemBaseBackupToolActions methods in the game-server binary:

- the can-use/action availability method returns true immediately;
- the failure-reason method returns the same success-ish code used by its normal
  happy path.

Because this is installed only for DD server containers, the blast radius is the
BaseBackupTool action path on those DD map processes.
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
    anchor_after_patch: bytes
    clean: bytes
    patched: bytes


PATCHES = [
    PatchSite(
        key="failure-reason",
        name="BRT failure-reason method force success",
        anchor_after_patch=bytes.fromhex(
            "41 56 41 55 41 54 53 48 83 ec 78 41 b6 32 48 85 "
            "c9 74 36 48 89 cb 49 89 fd 49 89 d4 49 89 f7 e8 "
            "46 cc 49 ff"
        ),
        clean=bytes.fromhex("55 48 89 e5 41 57"),
        patched=bytes.fromhex("b8 03 00 00 00 c3"),
    ),
    PatchSite(
        key="can-use",
        name="BRT can-use method force enabled",
        anchor_after_patch=bytes.fromhex(
            "41 56 41 55 41 54 53 48 83 ec 68 41 b6 01 48 85 "
            "c9 74 33"
        ),
        clean=bytes.fromhex("55 48 89 e5 41 57"),
        patched=bytes.fromhex("b8 01 00 00 00 c3"),
    ),
]


def find_site(data: bytes, site: PatchSite) -> tuple[int, bool]:
    hits = []
    pos = 0
    while True:
        hit = data.find(site.anchor_after_patch, pos)
        if hit < 0:
            break
        patch_offset = hit - len(site.clean)
        if patch_offset >= 0:
            current = data[patch_offset:patch_offset + len(site.clean)]
            if current in (site.clean, site.patched):
                hits.append(patch_offset)
        pos = hit + 1

    if len(hits) != 1:
        raise SystemExit(
            f"{site.name}: expected one signature, found {len(hits)}: "
            f"{[hex(hit) for hit in hits]}"
        )

    current = data[hits[0]:hits[0] + len(site.clean)]
    if current == site.clean:
        return hits[0], False
    if current == site.patched:
        return hits[0], True
    raise SystemExit(
        f"{site.name}: unexpected bytes at 0x{hits[0]:x}: "
        f"{current.hex(' ')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument(
        "--sites",
        default="all",
        help="comma-separated patch site keys to apply: all, failure-reason, can-use",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args()

    requested = {site.strip() for site in args.sites.split(",") if site.strip()}
    valid = {site.key for site in PATCHES}
    if not requested or requested == {"all"}:
        selected = PATCHES
    else:
        unknown = requested - valid
        if unknown:
            raise SystemExit(
                f"unknown --sites value(s): {', '.join(sorted(unknown))}; "
                f"valid values: all, {', '.join(sorted(valid))}"
            )
        selected = [site for site in PATCHES if site.key in requested]

    data = args.binary.read_bytes()
    to_patch = []
    already = []
    for site in selected:
        offset, is_patched = find_site(data, site)
        if is_patched:
            already.append((site, offset))
        else:
            to_patch.append((site, offset))

    for site, offset in already:
        print(f"already patched @ 0x{offset:x}: {site.name}")
    if not to_patch:
        print("requested BRT tool-enable force patch site(s) already applied; nothing to do")
        return

    sha_before = hashlib.sha256(data).hexdigest()
    patched = bytearray(data)
    for site, offset in to_patch:
        patched[offset:offset + len(site.clean)] = site.patched
        print(
            f"patch @ 0x{offset:x}: {site.name}: "
            f"{site.clean.hex(' ')} -> {site.patched.hex(' ')}"
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
