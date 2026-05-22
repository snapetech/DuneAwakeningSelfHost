#!/usr/bin/env python3
import argparse
import ctypes
import json
import os
import pathlib
import re
import struct


PAK_MAGIC = 0x5A6F12E1
DEFAULT_PAK = pathlib.Path("/tmp/dune-paks/pakchunk0-LinuxServer.pak")
DEFAULT_OODLE = pathlib.Path("/tmp/oodleue/lib/liboodle-data-shared.so")


def read_footer(data):
    # UE pak v11 footer with FName compression method table.
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
    encrypted = False
    names = []
    pos = base + 64
    for _ in range(5):
        raw = data[pos:pos + 32].split(b"\0", 1)[0]
        names.append(raw.decode("ascii", "ignore"))
        pos += 32
    return {
        "version": version,
        "index_offset": index_offset,
        "index_size": index_size,
        "encrypted": encrypted,
        "compression": names,
    }


def plausible_entry(data, index_offset, rel):
    pos = index_offset + rel
    if pos < index_offset or pos + 16 > len(data):
        return None
    bitfield = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    compression = (bitfield >> 23) & 0x3F
    block_count = (bitfield >> 6) & 0xFFFF
    if compression > 5 or block_count > 128:
        return None
    encrypted = bool(bitfield & (1 << 22))
    if encrypted:
        return None
    block_uncompressed = (bitfield & 0x3F) << 11
    if (bitfield & 0x3F) == 0x3F:
        if pos + 4 > len(data):
            return None
        block_uncompressed = struct.unpack_from("<I", data, pos)[0]
        pos += 4

    def flag(bit):
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
        offset = flag(31)
        uncompressed = flag(30)
        compressed = flag(29) if compression else uncompressed
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
    elif compression and block_count == 1:
        block_sizes.append(compressed)
    else:
        block_sizes.append(compressed)

    return {
        "rel": rel,
        "bitfield": bitfield,
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
    fn = lib.OodleLZ_Decompress
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint64,
        ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_uint,
    ]
    return fn


def read_entry(data, entry, oodle):
    header_size = 53 + (4 + 16 * entry["block_count"] if entry["compression"] else 0)
    start = entry["offset"] + header_size
    if not entry["compression"]:
        return data[start:start + entry["compressed"]]
    output = bytearray()
    pos = start
    block_sizes = entry.get("block_sizes") or [entry["compressed"]]
    for i, size in enumerate(block_sizes):
        raw = data[pos:pos + size]
        pos += size
        out_len = entry["uncompressed"] if len(block_sizes) == 1 else min(
            entry["block_uncompressed"],
            entry["uncompressed"] - i * entry["block_uncompressed"],
        )
        out = (ctypes.c_ubyte * out_len)()
        inp = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        written = oodle(inp, len(raw), out, out_len, 1, 1, 0, 0, 0, 0, 0, None, 0, 3)
        if written == 0:
            raise RuntimeError(f"oodle decompression failed for index entry 0x{entry['rel']:x}")
        output.extend(bytes(out))
    return bytes(output)


def ascii_strings(blob, min_len=4):
    return [m.group(0).decode("ascii", "ignore") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, blob)]


def classify(blob):
    text = "\n".join(ascii_strings(blob, 5))
    if "DeepDesert_" not in text:
        return None
    if "HeatMap" in text and "m_Data" in text:
        match = re.search(r"DeepDesert_(\d+_[A-Za-z0-9]+)", text)
        return {"kind": "heatmap-header", "name": match.group(1) if match else "unknown"}
    if "DA_DeepDesert_Layout" in text:
        match = re.search(r"DA_DeepDesert_Layout\d+p?", text)
        return {"kind": "layout-data", "name": match.group(0) if match else "unknown"}
    return {"kind": "deep-desert", "name": "unknown"}


def main():
    parser = argparse.ArgumentParser(description="Extract Deep Desert pak entries needed for map reconstruction.")
    parser.add_argument("--pak", type=pathlib.Path, default=DEFAULT_PAK)
    parser.add_argument("--oodle", type=pathlib.Path, default=DEFAULT_OODLE)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("backups/deep-desert-pak-assets"))
    parser.add_argument("--window-before-header", type=int, default=12, help="Number of decoded entries before each header to keep as likely payload context.")
    parser.add_argument("--verbose-oodle", action="store_true", help="Do not suppress Oodle corruption noise from rejected false-positive index offsets.")
    args = parser.parse_args()

    data = args.pak.read_bytes()
    footer = read_footer(data)
    if footer["encrypted"]:
        raise ValueError("encrypted pak indexes are not supported")
    oodle = load_oodle(args.oodle)
    index_offset = footer["index_offset"]
    index_size = footer["index_size"]

    stderr_copy = None
    devnull = None
    if not args.verbose_oodle:
        stderr_copy = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)

    decoded = []
    try:
        for rel in range(0, index_size - 16):
            entry = plausible_entry(data, index_offset, rel)
            if not entry:
                continue
            # Accept only real encoded-entry starts. Valid adjacent starts in this pak are 12 or 16 bytes apart.
            if decoded and rel < decoded[-1]["rel"] + decoded[-1]["encoded_size"]:
                continue
            try:
                blob = read_entry(data, entry, oodle)
            except Exception:
                continue
            info = classify(blob)
            decoded.append({**entry, "class": info, "blob": blob})
    finally:
        if stderr_copy is not None:
            os.dup2(stderr_copy, 2)
            os.close(stderr_copy)
        if devnull is not None:
            os.close(devnull)

    wanted_indexes = set()
    for i, row in enumerate(decoded):
        if row["class"] and row["class"]["kind"] in ("heatmap-header", "layout-data"):
            for j in range(max(0, i - args.window_before_header), i + 1):
                wanted_indexes.add(j)

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"pak": str(args.pak), "footer": footer, "entries": []}
    for i in sorted(wanted_indexes):
        row = decoded[i]
        cls = row["class"] or {"kind": "payload-context", "name": f"before-{i}"}
        stem = f"{i:05d}-{row['rel']:06x}-{cls['kind']}-{cls['name']}"
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)
        path = args.output / f"{stem}.bin"
        path.write_bytes(row["blob"])
        strings = ascii_strings(row["blob"], 6)[:40]
        manifest["entries"].append({
            "file": str(path),
            "indexRel": row["rel"],
            "pakOffset": row["offset"],
            "compressed": row["compressed"],
            "uncompressed": row["uncompressed"],
            "compression": row["compression"],
            "class": cls,
            "strings": strings,
        })

    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {len(manifest['entries'])} entries to {args.output}")
    print(f"manifest {manifest_path}")


if __name__ == "__main__":
    main()
