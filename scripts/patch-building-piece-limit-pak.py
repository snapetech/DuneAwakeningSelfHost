#!/usr/bin/env python3
import argparse
import ctypes
import os
from pathlib import Path
import re
import struct
import sys


PAK_MAGIC = 0x5A6F12E1
DEFAULT_PAK = Path("/home/dune/server/DuneSandbox/Content/Paks/pakchunk0-LinuxServer.pak")
DEFAULT_OODLE = Path("/tmp/oodle/liboodle-data-shared.so")
TARGET_TABLE = b"/Game/Dune/Systems/Building/Data/DT_BuildableStructureCategoryData"
BUILDING_ROW = b"UI/BuildingMenu_StructureCategory_BuildingPiece"
NEXT_ROW = b"UI/BuildingMenu_StructureCategory_Production"
DEFAULT_OLD_LIMIT = 5000


def is_steam_client_pak(path):
    try:
        normalized = str(path.expanduser().resolve()).replace("\\", "/")
    except OSError:
        normalized = str(path.expanduser()).replace("\\", "/")
    return "/steamapps/common/DuneAwakening/DuneSandbox/Content/Paks/" in normalized


def refuse_client_write(path, dry_run):
    if not dry_run and is_steam_client_pak(path):
        raise SystemExit("refusing to modify Steam client pak; server-side pak edits only")


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
    # 8 is Kraken in current Oodle builds. Higher levels give this tiny row payload
    # enough room to fit in the original pak slot without changing index metadata.
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
    raise RuntimeError(f"recompressed row did not round-trip within original {max_size}-byte slot")


def find_target(data, footer, decompress):
    decoded = []
    index_offset = footer["index_offset"]
    index_size = footer["index_size"]
    for rel in range(0, index_size - 16):
        entry = plausible_entry(data, index_offset, rel)
        if not entry:
            continue
        if decoded and rel < decoded[-1][0]["rel"] + decoded[-1][0]["encoded_size"]:
            continue
        try:
            blob = decompress_entry(data, entry, decompress)
        except Exception:
            continue
        decoded.append((entry, blob))
        if TARGET_TABLE in blob:
            continue
        if len(decoded) >= 2 and TARGET_TABLE in decoded[-2][1] and BUILDING_ROW in blob and NEXT_ROW in blob:
            return entry, blob

    raise RuntimeError("target BuildingPiece row payload was not found")


def patch_blob(blob, old_limit, new_limit):
    row_start = blob.find(BUILDING_ROW)
    row_end = blob.find(NEXT_ROW)
    if row_start < 0 or row_end <= row_start:
        raise RuntimeError("target row markers were not found in payload")
    old_bytes = struct.pack("<i", old_limit)
    new_bytes = struct.pack("<i", new_limit)
    old_hits = [m.start() for m in re.finditer(re.escape(old_bytes), blob[row_start:row_end])]
    new_hits = [m.start() for m in re.finditer(re.escape(new_bytes), blob[row_start:row_end])]
    if len(old_hits) == 0 and len(new_hits) == 1:
        absolute = row_start + new_hits[0]
        return blob, absolute, row_start, row_end, True
    if len(old_hits) != 1:
        raise RuntimeError(f"expected exactly one int32 {old_limit} in BuildingPiece row, found {len(old_hits)}")
    absolute = row_start + old_hits[0]
    patched = bytearray(blob)
    patched[absolute:absolute + 4] = new_bytes
    return bytes(patched), absolute, row_start, row_end, False


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


def main():
    parser = argparse.ArgumentParser(description="Patch Dune's cooked BuildingPiece buildable limit in pakchunk0.")
    parser.add_argument("--pak", type=Path, default=DEFAULT_PAK)
    parser.add_argument("--oodle", type=Path, default=Path(os.environ.get("DUNE_OODLE_LIBRARY", DEFAULT_OODLE)))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("DUNE_BUILDING_PIECE_LIMIT", "10000")))
    parser.add_argument("--old-limit", type=int, default=DEFAULT_OLD_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet-oodle", action="store_true", default=True)
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("limit must be positive")
    if args.limit == args.old_limit:
        print(f"BuildingPiece limit already requested as old limit {args.old_limit}; nothing to patch")
        return 0
    if not args.pak.exists():
        raise SystemExit(f"missing pak: {args.pak}")
    if not args.oodle.exists():
        raise SystemExit(f"missing Oodle library: {args.oodle}")
    refuse_client_write(args.pak, args.dry_run)

    data = bytearray(args.pak.read_bytes())
    footer = read_footer(data)
    if footer["version"] != 11:
        raise SystemExit(f"unsupported pak version {footer['version']}; expected 11")

    decompress, compress = load_oodle(args.oodle)
    saved_stderr = suppress_stderr(args.quiet_oodle)
    try:
        entry, blob = find_target(data, footer, decompress)
        patched_blob, value_offset, row_start, row_end, already_patched = patch_blob(blob, args.old_limit, args.limit)
        if already_patched:
            compressed = None
            compressed_size = entry["compressed"]
            compressor = "already-patched"
            level = "already-patched"
        else:
            compressed, compressed_size, compressor, level = compress_blob(
                patched_blob,
                entry["compressed"],
                compress,
                decompress,
            )
    finally:
        restore_stderr(saved_stderr)

    payload_start = pak_entry_payload_start(entry)
    payload_end = payload_start + entry["compressed"]
    print(
        "BuildingPiece limit pak patch:",
        f"pak={args.pak}",
        f"indexRel=0x{entry['rel']:x}",
        f"pakOffset={entry['offset']}",
        f"rowValueOffset={value_offset}",
        f"rowSpan={row_start}:{row_end}",
        f"{args.old_limit}->{args.limit}",
        f"compressed={compressed_size}/{entry['compressed']}",
        f"compressor={compressor}",
        f"level={level}",
    )
    if args.dry_run:
        print("dry-run: pak not modified")
        return 0
    if already_patched:
        print("pak already patched")
        return 0

    data[payload_start:payload_end] = compressed
    args.pak.write_bytes(data)
    print("patched pak successfully")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"patch-building-piece-limit-pak: {exc}", file=sys.stderr)
        raise SystemExit(1)
