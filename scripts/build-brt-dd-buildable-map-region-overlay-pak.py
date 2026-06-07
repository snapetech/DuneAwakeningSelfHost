#!/usr/bin/env python3
"""Build a tiny V11 overlay pak for the Deep Desert BRT buildable-region patch."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


DEFAULT_PAK = Path("/home/dune/server/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak")
DEFAULT_OODLE = Path("/tmp/oodle/liboodle-data-shared.so")
DEFAULT_OUTPUT = Path("/home/dune/server/DuneSandbox/Content/Paks/pakchunk9999-LinuxServer.pak")
DEFAULT_REPAK_CLONE = Path("/tmp/repak")
MODE_SWAP_MAP_ROWS = "swap-map-rows"
MODE_DD_TOTEM_GROUPS = "dd-totem-groups"
MODE_DD_FULL_REGION = "dd-full-region"
THIS_DIR = Path(__file__).resolve().parent
PATCH_SCRIPT = THIS_DIR / "patch-brt-dd-buildable-map-region-pak.py"


def run(cmd, *, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_repak_manifest(clone_dir):
    manifest = clone_dir / "repak_cli" / "Cargo.toml"
    if manifest.exists():
        return manifest
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
    run(["git", "clone", "--depth", "1", "https://github.com/trumank/repak", str(clone_dir)])
    if not manifest.exists():
        raise RuntimeError(f"repak manifest not found after clone: {manifest}")
    return manifest


def build_overlay_tree(source_pak, oodle, mode, overlay_root):
    cmd = [
        "python3",
        str(PATCH_SCRIPT),
        "--pak",
        str(source_pak),
        "--oodle",
        str(oodle),
        "--mode",
        mode,
        "--emit-overlay-dir",
        str(overlay_root),
    ]
    run(cmd)


def build_overlay_pak(overlay_root, output_pak, repak_manifest, mount_point, path_hash_seed):
    output_pak.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "cargo",
            "run",
            "--manifest-path",
            str(repak_manifest),
            "--",
            "pack",
            str(overlay_root),
            str(output_pak),
            "--version",
            "V11",
            "--mount-point",
            mount_point,
            "--path-hash-seed",
            str(path_hash_seed),
            "--quiet",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pak", type=Path, default=DEFAULT_PAK)
    parser.add_argument("--oodle", type=Path, default=Path(os.environ.get("DUNE_OODLE_LIBRARY", DEFAULT_OODLE)))
    parser.add_argument(
        "--mode",
        choices=[MODE_SWAP_MAP_ROWS, MODE_DD_TOTEM_GROUPS, MODE_DD_FULL_REGION],
        default=MODE_DD_TOTEM_GROUPS,
    )
    parser.add_argument("--output-pak", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repak-clone", type=Path, default=DEFAULT_REPAK_CLONE)
    parser.add_argument("--mount-point", default="../../../")
    parser.add_argument("--path-hash-seed", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    if not args.source_pak.exists():
        raise SystemExit(f"missing source pak: {args.source_pak}")
    if not args.oodle.exists():
        raise SystemExit(f"missing Oodle library: {args.oodle}")
    if not PATCH_SCRIPT.exists():
        raise SystemExit(f"missing patch script: {PATCH_SCRIPT}")

    temp_ctx = tempfile.TemporaryDirectory(prefix="brt-dd-overlay-")
    try:
        temp_root = Path(temp_ctx.name)
        overlay_root = temp_root / "overlay-root"
        overlay_root.mkdir(parents=True, exist_ok=True)

        repak_manifest = ensure_repak_manifest(args.repak_clone)
        build_overlay_tree(args.source_pak, args.oodle, args.mode, overlay_root)
        output_pak = args.output_pak
        if args.dry_run:
            output_pak = temp_root / "dry-run-overlay.pak"
        build_overlay_pak(overlay_root, output_pak, repak_manifest, args.mount_point, args.path_hash_seed)
        print(
            "built BRT Deep Desert overlay pak successfully",
            f"sourcePak={args.source_pak}",
            f"outputPak={output_pak}",
            f"mode={args.mode}",
            f"mountPoint={args.mount_point}",
            f"pathHashSeed={args.path_hash_seed}",
        )
        if args.dry_run:
            print("dry-run: overlay pak not persisted")
        if args.keep_temp:
            kept = args.output_pak.parent / f".{args.output_pak.stem}.overlay-root"
            if kept.exists():
                shutil.rmtree(kept)
            shutil.copytree(overlay_root, kept)
            print(f"keptOverlayRoot={kept}")
    finally:
        if not args.keep_temp:
            temp_ctx.cleanup()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"build-brt-dd-buildable-map-region-overlay-pak: command failed: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode or 1)
    except Exception as exc:
        print(f"build-brt-dd-buildable-map-region-overlay-pak: {exc}", file=sys.stderr)
        raise SystemExit(1)
