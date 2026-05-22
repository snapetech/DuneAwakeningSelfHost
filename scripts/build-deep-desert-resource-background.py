#!/usr/bin/env python3
import argparse
import ctypes
import json
import pathlib
import struct

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


DEFAULT_PAK = pathlib.Path("/tmp/dune-paks/pakchunk0-LinuxServer.pak")
DEFAULT_OODLE = pathlib.Path("/tmp/oodleue/lib/liboodle-data-shared.so")
INDEX_OFFSET = 257742272
DIRECTORY_TO_ENCODED_DELTA = 0x1F2C8

LAYOUT18_UEXP_OFFSETS = {
    "Copper": 0x28A50,
    "T6 A": 0x28AB0,
    "Iron": 0x28B10,
    "Carbon": 0x28B70,
    "Aluminium": 0x28BD0,
    "T6 B": 0x28C30,
    "Stone": 0x28C90,
    "Basalt": 0x28CF0,
}
LAYER_COLORS = {
    "Copper": (235, 149, 74),
    "T6 A": (132, 92, 255),
    "Iron": (205, 220, 225),
    "Carbon": (105, 120, 128),
    "Aluminium": (235, 240, 232),
    "T6 B": (70, 225, 205),
    "Stone": (190, 165, 118),
    "Basalt": (90, 92, 110),
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


def decode_entry(data, rel, oodle):
    pos = INDEX_OFFSET + rel
    bitfield = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    compression = (bitfield >> 23) & 0x3F
    block_count = (bitfield >> 6) & 0xFFFF
    block_uncompressed = (bitfield & 0x3F) << 11
    if (bitfield & 0x3F) == 0x3F:
        block_uncompressed = struct.unpack_from("<I", data, pos)[0]
        pos += 4

    def flag(bit):
        nonlocal pos
        if bitfield & (1 << bit):
            value = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            return value
        value = struct.unpack_from("<Q", data, pos)[0]
        pos += 8
        return value

    offset = flag(31)
    uncompressed = flag(30)
    compressed = flag(29) if compression else uncompressed
    if compression and block_count > 1:
        block_sizes = [struct.unpack_from("<I", data, pos + i * 4)[0] for i in range(block_count)]
    else:
        block_sizes = [compressed]
    header_size = 53 + (4 + 16 * block_count if compression else 0)
    chunk_pos = offset + header_size
    output = bytearray()
    for i, size in enumerate(block_sizes):
        raw = data[chunk_pos:chunk_pos + size]
        chunk_pos += size
        if not compression:
            output.extend(raw)
            continue
        out_len = uncompressed if len(block_sizes) == 1 else min(block_uncompressed, uncompressed - i * block_uncompressed)
        out = (ctypes.c_ubyte * out_len)()
        inp = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        written = oodle(inp, len(raw), out, out_len, 1, 1, 0, 0, 0, 0, 0, None, 0, 3)
        if written == 0:
            raise RuntimeError(f"Oodle decompression failed for encoded entry 0x{rel:x}")
        output.extend(bytes(out))
    return bytes(output)


def heatmap_image(blob):
    # HeatMapData .uexp starts with 152 bytes of serialized property wrapper,
    # followed by a 1024x1024 PF_G8 raster.
    raw = blob[152:152 + 1024 * 1024]
    if len(raw) != 1024 * 1024:
        raise ValueError("unexpected heatmap raster size")
    return Image.frombytes("L", (1024, 1024), raw)


def heatmap_hotspots(mask, name, color, threshold=42, max_components=18):
    small_size = 256
    small = mask.resize((small_size, small_size), Image.Resampling.BILINEAR)
    pixels = small.load()
    seen = set()
    components = []
    for y in range(small_size):
        for x in range(small_size):
            if (x, y) in seen or pixels[x, y] < threshold:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            xs = []
            ys = []
            total = 0
            while stack:
                cx, cy = stack.pop()
                value = pixels[cx, cy]
                xs.append(cx)
                ys.append(cy)
                total += int(value)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= small_size or ny >= small_size or (nx, ny) in seen:
                        continue
                    if pixels[nx, ny] >= threshold:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            area = len(xs)
            if area < 6:
                continue
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            components.append({
                "name": name,
                "color": "#{:02x}{:02x}{:02x}".format(*color),
                "x": ((min_x + max_x + 1) / 2) / small_size,
                "y": ((min_y + max_y + 1) / 2) / small_size,
                "w": max((max_x - min_x + 1) / small_size, 0.018),
                "h": max((max_y - min_y + 1) / small_size, 0.018),
                "area": area,
                "intensity": round(total / max(area * 255, 1), 4),
            })
    components.sort(key=lambda row: (row["area"], row["intensity"]), reverse=True)
    return components[:max_components]


def main():
    parser = argparse.ArgumentParser(description="Build a Deep Desert resource background from layout-18 pak heatmaps.")
    parser.add_argument("--pak", type=pathlib.Path, default=DEFAULT_PAK)
    parser.add_argument("--oodle", type=pathlib.Path, default=DEFAULT_OODLE)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("admin/static/deep-desert.webp"))
    parser.add_argument("--hotspots-output", type=pathlib.Path, default=pathlib.Path("admin/static/deep-desert-hotspots.json"))
    args = parser.parse_args()

    data = args.pak.read_bytes()
    oodle = load_oodle(args.oodle)
    width = height = 1600
    base = Image.new("RGB", (width, height), (18, 18, 15))
    draw = ImageDraw.Draw(base, "RGBA")
    for y, color, alpha in [(260, (120, 96, 52), 90), (620, (158, 122, 55), 70), (1070, (105, 82, 46), 80)]:
        points = [(0, y), (220, y - 70), (470, y - 45), (720, y + 25), (1010, y - 30), (1310, y + 20), (1600, y - 55)]
        draw.line(points, fill=(*color, alpha), width=18)
        draw.line([(x, py + 8) for x, py in points], fill=(230, 178, 72, 40), width=6)

    legend = []
    hotspots = []
    for name, directory_offset in LAYOUT18_UEXP_OFFSETS.items():
        blob = decode_entry(data, directory_offset - DIRECTORY_TO_ENCODED_DELTA, oodle)
        source_mask = heatmap_image(blob)
        hotspots.extend(heatmap_hotspots(source_mask, name, LAYER_COLORS[name]))
        mask = ImageEnhance.Contrast(source_mask).enhance(2.0)
        mask = mask.point(lambda v: 0 if v < 18 else min(210, int((v - 18) * 2.2)))
        mask = mask.resize((width, height), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))
        color = Image.new("RGBA", (width, height), (*LAYER_COLORS[name], 0))
        color.putalpha(mask)
        base = Image.alpha_composite(base.convert("RGBA"), color).convert("RGB")
        legend.append((name, LAYER_COLORS[name]))

    draw = ImageDraw.Draw(base, "RGBA")
    for i in range(10):
        x = round(i * width / 9)
        y = round(i * height / 9)
        draw.line([(x, 0), (x, height)], fill=(241, 208, 138, 72), width=1)
        draw.line([(0, y), (width, y)], fill=(241, 208, 138, 72), width=1)
        if i < 9:
            draw.text((round((i + 0.5) * width / 9) - 4, 20), str(i + 1), fill=(235, 205, 125, 210))
            draw.text((10, round((i + 0.5) * height / 9) - 8), "IHGFEDCBA"[i], fill=(235, 205, 125, 210))
    draw.rectangle((0, height - 54, width, height), fill=(18, 18, 15, 190))
    x = 16
    for name, color in legend:
        draw.ellipse((x, height - 37, x + 14, height - 23), fill=(*color, 220))
        draw.text((x + 20, height - 40), name, fill=(225, 218, 200, 230))
        x += 150

    args.output.parent.mkdir(parents=True, exist_ok=True)
    base.save(args.output, "WEBP", quality=88, method=6)
    if args.hotspots_output:
        args.hotspots_output.parent.mkdir(parents=True, exist_ok=True)
        args.hotspots_output.write_text(json.dumps({
            "layout": 18,
            "projection": "normalized 1024x1024 heatmap raster; row A bottom, I top in rendered grid",
            "layers": [{"name": name, "color": "#{:02x}{:02x}{:02x}".format(*LAYER_COLORS[name])} for name in LAYOUT18_UEXP_OFFSETS],
            "hotspots": hotspots,
        }, indent=2), encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
