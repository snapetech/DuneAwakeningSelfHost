#!/usr/bin/env python3
import argparse
import ctypes
import os
import re
import struct
import sys
from pathlib import Path


PAK_MAGIC = 0x5A6F12E1
DEFAULT_PAK = Path("/home/dune/server/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak")
DEFAULT_OODLE = Path("/tmp/oodle/liboodle-data-shared.so")

TARGET_MARKERS = (
    b"/Game/Dune/NPCs/Dialogue/Generated/DA_Dialogue_",
    b"PlayerCanAccessLandsraadVendor",
    b"PlayerFactionHasReignOverLandsraad",
)
OLD_NAMES = (
    b"PlayerFactionHasReignOverLandsraad",
    b"Default__PlayerFactionHasReignOverLandsraad",
)
NEW_NAMES = (
    b"PlayerHasSolarisInPocketAndAccount",
    b"Default__PlayerHasSolarisInPocketAndAccount",
)
EXPECTED_TARGETS = 8


def read_footer(data):
    magic_bytes = struct.pack("<I", PAK_MAGIC)
    magic_pos = data.rfind(magic_bytes, max(0, len(data) - 512))
    if magic_pos < 20:
        raise ValueError("pak footer magic not found near end of file")
    base = magic_pos - 20
    magic = struct.unpack_from("<I", data, base + 20)[0]
    if magic != PAK_MAGIC:
        raise ValueError(f"unexpected pak footer magic 0x{magic:08x}")
    version = struct.unpack_from("<I", data, base + 24)[0]
    index_offset = struct.unpack_from("<Q", data, base + 28)[0]
    index_size = struct.unpack_from("<Q", data, base + 36)[0]
    return {"version": version, "index_offset": index_offset, "index_size": index_size}


def plausible_entry(data, index_offset, rel):
    pos = index_offset + rel
    if pos < index_offset or pos + 16 > len(data):
        return None
    bitfield = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    compression = (bitfield >> 23) & 0x3F
    block_count = (bitfield >> 6) & 0xFFFF
    if compression > 5 or block_count > 128 or bitfield & (1 << 22):
        return None
    block_uncompressed = (bitfield & 0x3F) << 11
    if (bitfield & 0x3F) == 0x3F:
        if pos + 4 > len(data):
            return None
        block_uncompressed = struct.unpack_from("<I", data, pos)[0]
        pos += 4

    def read_size(bit):
        nonlocal pos
        if bitfield & (1 << bit):
            if pos + 4 > len(data):
                raise ValueError("short encoded entry")
            value = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            return value
        if pos + 8 > len(data):
            raise ValueError("short encoded entry")
        value = struct.unpack_from("<Q", data, pos)[0]
        pos += 8
        return value

    try:
        offset = read_size(31)
        uncompressed = read_size(30)
        compressed = read_size(29) if compression else uncompressed
    except ValueError:
        return None
    if not (0 < offset < len(data) and 0 < uncompressed < 64 * 1024 * 1024 and 0 < compressed < 64 * 1024 * 1024):
        return None
    block_sizes = []
    if compression and block_count > 1:
        if pos + block_count * 4 > len(data):
            return None
        for _ in range(block_count):
            block_sizes.append(struct.unpack_from("<I", data, pos)[0])
            pos += 4
    elif compression:
        block_sizes.append(compressed)
    else:
        block_sizes.append(compressed)
    return {
        "rel": rel,
        "compression": compression,
        "block_count": block_count,
        "block_uncompressed": block_uncompressed,
        "offset": offset,
        "uncompressed": uncompressed,
        "compressed": compressed,
        "block_sizes": block_sizes,
        "encoded_size": pos - (index_offset + rel),
    }


def load_oodle(path):
    lib = ctypes.CDLL(str(path))
    decompress = lib.OodleLZ_Decompress
    decompress.restype = ctypes.c_int
    decompress.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint64,
        ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_uint,
    ]
    compress = lib.OodleLZ_Compress
    compress.restype = ctypes.c_int
    compress.argtypes = [
        ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_size_t,
    ]
    return decompress, compress


def pak_entry_payload_start(entry):
    return entry["offset"] + 53 + (4 + 16 * entry["block_count"] if entry["compression"] else 0)


def decompress_entry(data, entry, decompress):
    start = pak_entry_payload_start(entry)
    if not entry["compression"]:
        return data[start:start + entry["compressed"]]
    output = bytearray()
    pos = start
    for i, size in enumerate(entry["block_sizes"]):
        raw = data[pos:pos + size]
        pos += size
        out_len = entry["uncompressed"] if len(entry["block_sizes"]) == 1 else min(
            entry["block_uncompressed"],
            entry["uncompressed"] - i * entry["block_uncompressed"],
        )
        out = (ctypes.c_ubyte * out_len)()
        inp = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        written = decompress(inp, len(raw), out, out_len, 1, 1, 0, 0, 0, 0, 0, None, 0, 3)
        if written != out_len:
            raise RuntimeError(f"oodle decompression failed for index entry 0x{entry['rel']:x}")
        output.extend(bytes(out))
    return bytes(output)


def compress_blob(blob, max_size, compress, decompress):
    attempts = [(8, 6), (8, 7), (8, 8), (8, 9), (12, 6), (13, 8), (13, 9)]
    inp = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    for compressor, level in attempts:
        out = (ctypes.c_ubyte * (len(blob) + 65536))()
        size = compress(compressor, inp, len(blob), out, level, None, None, None, None, 0)
        if size <= 0 or size > max_size:
            continue
        compressed = bytes(out[:size])
        padded = compressed + (b"\0" * (max_size - size))
        verify_out = (ctypes.c_ubyte * len(blob))()
        verify_in = (ctypes.c_ubyte * len(padded)).from_buffer_copy(padded)
        written = decompress(verify_in, len(padded), verify_out, len(blob), 1, 1, 0, 0, 0, 0, 0, None, 0, 3)
        if written == len(blob) and bytes(verify_out) == blob:
            return padded, size, compressor, level
    raise RuntimeError(f"recompressed dialogue payload did not fit original {max_size}-byte slot")


def suppress_stderr(enabled):
    if not enabled:
        return None
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    return saved


def restore_stderr(saved):
    if saved is not None:
        os.dup2(saved, 2)
        os.close(saved)


def find_targets(data, footer, decompress):
    targets = []
    index_offset = footer["index_offset"]
    index_size = footer["index_size"]
    decoded = []
    for rel in range(0, index_size - 16):
        entry = plausible_entry(data, index_offset, rel)
        if not entry:
            continue
        if decoded and rel < decoded[-1]["rel"] + decoded[-1]["encoded_size"]:
            continue
        try:
            blob = decompress_entry(data, entry, decompress)
        except Exception:
            continue
        decoded.append(entry)
        already_patched = TARGET_MARKERS[0] in blob and TARGET_MARKERS[1] in blob and all(name in blob for name in NEW_NAMES)
        if all(marker in blob for marker in TARGET_MARKERS) or already_patched:
            targets.append((entry, blob))
    return targets


def patch_blob(blob):
    patched = blob
    changed = False
    for old, new in zip(OLD_NAMES, NEW_NAMES):
        if len(old) != len(new):
            raise RuntimeError(f"replacement length mismatch: {old!r} -> {new!r}")
        count = patched.count(old)
        if count:
            patched = patched.replace(old, new)
            changed = True
        elif new not in patched:
            raise RuntimeError(f"target name {old.decode()} was not found and replacement is absent")
    return patched, changed


def dialogue_name(blob):
    match = re.search(rb"/Game/Dune/NPCs/Dialogue/Generated/DA_Dialogue_[A-Za-z0-9_]+", blob)
    return match.group(0).decode("ascii", "ignore") if match else "unknown"


def main():
    parser = argparse.ArgumentParser(description="Patch Landsraad vendor dialogue faction gate in pakchunk0.")
    parser.add_argument("--pak", type=Path, default=DEFAULT_PAK)
    parser.add_argument("--oodle", type=Path, default=Path(os.environ.get("DUNE_OODLE_LIBRARY", DEFAULT_OODLE)))
    parser.add_argument("--expected-targets", type=int, default=EXPECTED_TARGETS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet-oodle", action="store_true", default=True)
    args = parser.parse_args()

    if not args.pak.exists():
        raise SystemExit(f"missing pak: {args.pak}")
    if not args.oodle.exists():
        raise SystemExit(f"missing Oodle library: {args.oodle}")

    data = bytearray(args.pak.read_bytes())
    footer = read_footer(data)
    if footer["version"] != 11:
        raise SystemExit(f"unsupported pak version {footer['version']}; expected 11")

    decompress, compress = load_oodle(args.oodle)
    saved_stderr = suppress_stderr(args.quiet_oodle)
    patches = []
    try:
        targets = find_targets(data, footer, decompress)
        if len(targets) != args.expected_targets:
            raise RuntimeError(f"expected {args.expected_targets} Landsraad vendor dialogue targets, found {len(targets)}")
        for entry, blob in targets:
            patched_blob, changed = patch_blob(blob)
            compressed = None
            compressed_size = entry["compressed"]
            compressor = "already-patched"
            level = "already-patched"
            if changed:
                compressed, compressed_size, compressor, level = compress_blob(
                    patched_blob,
                    entry["compressed"],
                    compress,
                    decompress,
                )
            patches.append({
                "entry": entry,
                "dialogue": dialogue_name(patched_blob),
                "compressed": compressed,
                "compressed_size": compressed_size,
                "compressor": compressor,
                "level": level,
                "changed": changed,
            })
    finally:
        restore_stderr(saved_stderr)

    for patch in patches:
        entry = patch["entry"]
        print(
            "Landsraad vendor faction-gate pak patch:",
            f"pak={args.pak}",
            f"dialogue={patch['dialogue']}",
            f"indexRel=0x{entry['rel']:x}",
            f"pakOffset={entry['offset']}",
            f"compressed={patch['compressed_size']}/{entry['compressed']}",
            f"compressor={patch['compressor']}",
            f"level={patch['level']}",
            f"changed={patch['changed']}",
        )

    if args.dry_run:
        print("dry-run: pak not modified")
        return 0

    changed_count = 0
    for patch in patches:
        if not patch["changed"]:
            continue
        entry = patch["entry"]
        payload_start = pak_entry_payload_start(entry)
        payload_end = payload_start + entry["compressed"]
        data[payload_start:payload_end] = patch["compressed"]
        changed_count += 1

    if changed_count:
        args.pak.write_bytes(data)
        print(f"patched pak successfully: {changed_count} dialogue payloads")
    else:
        print("pak already patched")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"patch-landsraad-vendor-faction-gate-pak: {exc}", file=sys.stderr)
        raise SystemExit(1)
