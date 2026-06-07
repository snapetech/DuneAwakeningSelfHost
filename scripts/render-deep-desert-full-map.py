#!/usr/bin/env python3
import argparse
import datetime
import json
import math
import os
import pathlib
import random
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageMath, ImageOps


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_BOUNDS = {
    "min_x": -1250000.0,
    "max_x": 1150000.0,
    "min_y": -1250000.0,
    "max_y": 1050000.0,
}
MAP_SIZE = 1600
LEGEND_WIDTH = 420
CANVAS_SIZE = (MAP_SIZE + LEGEND_WIDTH, MAP_SIZE)
ROW_LABELS_TOP_TO_BOTTOM = "IHGFEDCBA"

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
MARKER_COLORS = {
    "Transit": (111, 182, 255),
    "Locations": (213, 161, 62),
    "Wreckage": (183, 192, 199),
    "Resources": (120, 207, 122),
    "Markers": (243, 234, 219),
}


def env_file_values(path):
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def compose_files(root, env_file):
    helper = root / "scripts" / "compose-files.sh"
    if not helper.exists():
        return [root / "compose.yaml"]
    result = subprocess.run(
        [str(helper), str(env_file)],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=10,
    )
    return [root / item for item in result.stdout.strip().split(":") if item]


def compose_psql(root, env_file, database, sql):
    cmd = ["docker", "compose"]
    for compose_file in compose_files(root, env_file):
        cmd.extend(["-f", str(compose_file)])
    cmd.extend([
        "--env-file", str(env_file),
        "exec", "-T", "postgres",
        "psql", "-U", "dune", "-d", database,
        "-X", "-q", "-t", "-A",
        "-c", "copy (" + sql + ") to stdout",
    ])
    return subprocess.check_output(cmd, cwd=str(root), text=True, timeout=30)


def query_json(root, env_file, database, sql, fallback):
    text = compose_psql(root, env_file, database, sql).strip()
    return json.loads(text or json.dumps(fallback))


def load_db_state(root, env_file, database):
    state = {"ok": False, "error": None, "markers": [], "resources": [], "spice": [], "scanCoverage": []}
    try:
        state["markers"] = query_json(root, env_file, database, r"""
            select coalesce(json_agg(row_to_json(t)), '[]'::json)
            from (
                select m.marker_hash_id,
                       m.dimension_index,
                       m.area_id,
                       (m.marker).marker_type as marker_type,
                       (m.marker).x::float8 as x,
                       (m.marker).y::float8 as y,
                       (m.marker).z::float8 as z,
                       m.area_radius::float8 as area_radius
                from dune.markers m
                join dune.map_names mn on mn.map_name_id = m.map_name_id
                where mn.map_name = 'DeepDesert'
                order by m.area_id, (m.marker).marker_type, m.marker_hash_id
            ) t
        """, [])
        state["resources"] = query_json(root, env_file, database, r"""
            select coalesce(json_agg(row_to_json(t)), '[]'::json)
            from (
                select dimension_index, field_kind_id, count(*)::integer as fields,
                       coalesce(sum(value_remaining), 0)::bigint as value_remaining
                from dune.resourcefield_state
                where map = 'DeepDesert'
                group by dimension_index, field_kind_id
                order by dimension_index, field_kind_id
            ) t
        """, [])
        state["spice"] = query_json(root, env_file, database, r"""
            select coalesce(json_agg(row_to_json(t)), '[]'::json)
            from (
                select field_type, dimension_index, max_globally_primed,
                       max_globally_active, current_globally_primed,
                       current_globally_active, is_spawning_active
                from dune.spicefield_types
                where map_name = 'DeepDesert'
                order by dimension_index, field_type
            ) t
        """, [])
        state["scanCoverage"] = query_json(root, env_file, database, r"""
            select coalesce(json_agg(row_to_json(t)), '[]'::json)
            from (
                select ps.account_id, ps.character_name,
                       count(ma.*)::integer as rows,
                       count(ma.*) filter (where ma.time_discovered is not null)::integer as discovered_rows,
                       count(ma.*) filter (where ma.time_first_entered is not null)::integer as entered_rows,
                       count(ma.*) filter (where ma.items_surveyed_target is not null or ma.items_surveyed_progress is not null)::integer as survey_rows
                from dune.player_state ps
                left join dune.map_areas ma on ma.account_id = ps.account_id and ma.map_name = 'DeepDesert'
                where ps.character_name = 'Paul'
                group by ps.account_id, ps.character_name
                order by ps.account_id
            ) t
        """, [])
        state["ok"] = True
    except Exception as exc:
        state["error"] = str(exc)
    return state


def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if pathlib.Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def rgba(color, alpha):
    return (*color, alpha)


def marker_group(marker_type):
    value = str(marker_type or "Marker")
    if value == "TaxiService":
        return "Transit"
    if value in ("Cave", "Ecolab", "HomeBase"):
        return "Locations"
    if "Wreckage" in value or "Part" in value or value == "Shipwreck":
        return "Wreckage"
    if "Ore" in value or "Pickup" in value or value == "BrittleBush":
        return "Resources"
    return "Markers"


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def world_to_pixel(x, y, bounds):
    px = (float(x) - bounds["min_x"]) / max(bounds["max_x"] - bounds["min_x"], 1) * MAP_SIZE
    py = (float(y) - bounds["min_y"]) / max(bounds["max_y"] - bounds["min_y"], 1) * MAP_SIZE
    return clamp(px, 0, MAP_SIZE), clamp(py, 0, MAP_SIZE)


def value_noise(size, cells, seed):
    rnd = random.Random(seed)
    small = Image.new("L", (cells, cells))
    small.putdata([rnd.randrange(256) for _ in range(cells * cells)])
    return small.resize((size, size), Image.Resampling.BICUBIC)


def build_ingame_background(size=MAP_SIZE):
    broad = value_noise(size, 18, 1217).filter(ImageFilter.GaussianBlur(10))
    mid = value_noise(size, 48, 2401).filter(ImageFilter.GaussianBlur(4))
    fine = value_noise(size, 120, 3931).filter(ImageFilter.GaussianBlur(1.2))
    image_math_eval = getattr(ImageMath, "eval", None) or getattr(ImageMath, "unsafe_eval")
    height = image_math_eval(
        "convert(((a * 46 + b * 36 + c * 18) / 100), 'L')",
        a=broad,
        b=mid,
        c=fine,
    ).filter(ImageFilter.UnsharpMask(radius=3, percent=135, threshold=3))

    # Directional shade gives the same parchment relief feel as the client map.
    lit = ImageChops.subtract(ImageChops.offset(height, -4, -6), ImageChops.offset(height, 4, 6), scale=0.86, offset=132)
    lit = ImageEnhance.Contrast(lit).enhance(1.95).filter(ImageFilter.GaussianBlur(0.45))
    relief = ImageOps.colorize(lit, black=(115, 74, 44), mid=(207, 145, 87), white=(249, 214, 164), midpoint=132).convert("RGBA")
    base_height = ImageOps.colorize(height, black=(177, 111, 63), mid=(220, 162, 101), white=(244, 199, 138), midpoint=128).convert("RGBA")
    terrain = Image.blend(base_height, relief, 0.68)

    draw = ImageDraw.Draw(terrain, "RGBA")

    rnd = random.Random(7719)
    rock_overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rock_draw = ImageDraw.Draw(rock_overlay, "RGBA")
    for _ in range(310):
        x = rnd.randrange(-40, size + 40)
        y = rnd.randrange(-20, size + 20)
        rx = rnd.randrange(8, 36)
        ry = rnd.randrange(5, 26)
        shade = rnd.choice([(78, 47, 31, 55), (98, 59, 37, 42), (252, 220, 164, 28)])
        start = rnd.randrange(0, 360)
        rock_draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=shade)
        rock_draw.arc((x - rx, y - ry, x + rx, y + ry), start, start + 115, fill=(255, 226, 171, 42), width=2)
    rock_overlay = rock_overlay.filter(ImageFilter.GaussianBlur(1.4))
    terrain = Image.alpha_composite(terrain, rock_overlay)

    # Soft sun wash and edge vignette, matching the warmer in-game map read.
    wash = Image.new("RGBA", (size, size), (228, 163, 91, 32))
    terrain = Image.alpha_composite(terrain, wash)
    vignette = Image.new("L", (size, size), 0)
    vdraw = ImageDraw.Draw(vignette)
    vdraw.ellipse((-220, -180, size + 220, size + 180), fill=255)
    vignette = ImageOps.invert(vignette.filter(ImageFilter.GaussianBlur(80)))
    dark = Image.new("RGBA", (size, size), (92, 54, 31, 65))
    terrain = Image.composite(dark, terrain, vignette).convert("RGB")
    return terrain


def load_background(path, style):
    if style == "ingame":
        return build_ingame_background()
    if path.exists():
        return Image.open(path).convert("RGB").resize((MAP_SIZE, MAP_SIZE), Image.Resampling.BICUBIC)
    image = Image.new("RGB", (MAP_SIZE, MAP_SIZE), (18, 18, 15))
    draw = ImageDraw.Draw(image, "RGBA")
    for y, color, alpha in [(260, (120, 96, 52), 90), (620, (158, 122, 55), 70), (1070, (105, 82, 46), 80)]:
        points = [(0, y), (220, y - 70), (470, y - 45), (720, y + 25), (1010, y - 30), (1310, y + 20), (1600, y - 55)]
        draw.line(points, fill=(*color, alpha), width=18)
        draw.line([(x, py + 8) for x, py in points], fill=(230, 178, 72, 40), width=6)
    return image


def draw_grid(draw, style):
    small = font(18, bold=True)
    tiny = font(13)
    line = (255, 237, 206, 74) if style == "ingame" else (241, 208, 138, 96)
    text = (255, 232, 175, 238) if style == "ingame" else (245, 215, 134, 230)
    stroke = (78, 47, 28) if style == "ingame" else (10, 10, 8)
    for i in range(10):
        x = round(i * MAP_SIZE / 9)
        y = round(i * MAP_SIZE / 9)
        draw.line([(x, 0), (x, MAP_SIZE)], fill=line, width=2 if style == "ingame" else 1)
        draw.line([(0, y), (MAP_SIZE, y)], fill=line, width=2 if style == "ingame" else 1)
        if i < 9:
            col_label = str(i + 1)
            row_label = ROW_LABELS_TOP_TO_BOTTOM[i]
            cx = round((i + 0.5) * MAP_SIZE / 9)
            cy = round((i + 0.5) * MAP_SIZE / 9)
            draw.text((cx - 6, 18), col_label, fill=text, font=small, stroke_width=2, stroke_fill=stroke)
            draw.text((12, cy - 10), row_label, fill=text, font=small, stroke_width=2, stroke_fill=stroke)
    draw.text((34, 42), "NW", fill=text, font=tiny, stroke_width=1, stroke_fill=stroke)
    draw.text((MAP_SIZE - 44, MAP_SIZE - 34), "SE", fill=text, font=tiny, stroke_width=1, stroke_fill=stroke)


def draw_hotspots(draw, hotspots, style):
    label_font = font(13, bold=True)
    for row in hotspots:
        name = str(row.get("name") or "Resource")
        color = LAYER_COLORS.get(name, (225, 210, 170))
        x = float(row.get("x") or 0) * MAP_SIZE
        y = float(row.get("y") or 0) * MAP_SIZE
        w = max(float(row.get("w") or 0.025) * MAP_SIZE, 34)
        h = max(float(row.get("h") or 0.025) * MAP_SIZE, 34)
        box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        if style == "ingame":
            draw.ellipse(box, fill=rgba(color, 54), outline=rgba(color, 150), width=2)
            if name in ("T6 A", "T6 B", "Copper", "Iron", "Aluminium", "Stone", "Basalt", "Carbon"):
                draw.text((x + 10, y - 8), name, fill=(67, 41, 25, 230), font=label_font, stroke_width=2, stroke_fill=(255, 228, 175))
        else:
            draw.ellipse(box, fill=rgba(color, 88), outline=rgba(color, 235), width=3)
            draw.text((x + 10, y - 8), name, fill=(255, 255, 245, 235), font=label_font, stroke_width=3, stroke_fill=(10, 10, 8))


def draw_db_markers(draw, markers, bounds, style):
    label_font = font(12, bold=True)
    markers_by_type = {}
    for marker in markers:
        marker_type = str(marker.get("marker_type") or "Marker")
        markers_by_type[marker_type] = markers_by_type.get(marker_type, 0) + 1
        if marker.get("x") is None or marker.get("y") is None:
            continue
        x, y = world_to_pixel(marker["x"], marker["y"], bounds)
        group = marker_group(marker_type)
        color = MARKER_COLORS.get(group, MARKER_COLORS["Markers"])
        radius = 6 if group in ("Transit", "Locations") else 3
        halo = 105 if style == "ingame" else 110
        draw.ellipse((x - radius - 3, y - radius - 3, x + radius + 3, y + radius + 3), fill=rgba((44, 25, 15), halo))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(color, 215), outline=(58, 34, 20, 230), width=2)
        if marker_type in ("TaxiService", "Ecolab", "HomeBase"):
            fill = (82, 50, 29, 240) if style == "ingame" else (255, 255, 245, 235)
            stroke = (255, 229, 178) if style == "ingame" else (10, 10, 8)
            draw.text((x + 10, y - 10), marker_type, fill=fill, font=label_font, stroke_width=2 if style == "ingame" else 3, stroke_fill=stroke)
    return markers_by_type


def draw_title(draw, generated_at, style):
    title_font = font(30, bold=True)
    meta_font = font(16)
    if style == "ingame":
        draw.rectangle((0, 0, MAP_SIZE, 92), fill=(54, 32, 18, 116))
        draw.text((22, 18), "Deep Desert Full Map", fill=(255, 226, 167, 245), font=title_font, stroke_width=2, stroke_fill=(52, 31, 17))
        draw.text((24, 58), f"Surveyed terrain, resource overlays, and server marker state | {generated_at}", fill=(250, 219, 166, 235), font=meta_font, stroke_width=1, stroke_fill=(52, 31, 17))
    else:
        draw.rectangle((0, 0, MAP_SIZE, 92), fill=(12, 12, 10, 178))
        draw.text((22, 18), "Deep Desert Full Map", fill=(255, 244, 220, 245), font=title_font)
        draw.text((24, 58), f"Stitched resource heatmaps, DB markers, and server field state | {generated_at}", fill=(216, 205, 184, 235), font=meta_font)


def legend_line(draw, x, y, label, value="", color=(225, 210, 170), swatch=True, style="schematic"):
    text_font = font(14)
    text_color = (81, 50, 31, 245) if style == "ingame" else (248, 239, 220, 235)
    value_color = (111, 75, 48, 235) if style == "ingame" else (183, 174, 158, 230)
    if swatch:
        draw.rectangle((x, y + 4, x + 14, y + 18), fill=rgba(color, 230), outline=(255, 245, 220, 180))
        text_x = x + 22
    else:
        text_x = x
    draw.text((text_x, y), label, fill=text_color, font=text_font)
    if value:
        draw.text((x + 210, y), str(value), fill=value_color, font=text_font)
    return y + 24


def draw_legend(draw, hotspots, markers_by_type, db_state, style):
    x = MAP_SIZE + 22
    y = 22
    header = font(22, bold=True)
    small = font(13)
    if style == "ingame":
        draw.rectangle((MAP_SIZE, 0, CANVAS_SIZE[0], CANVAS_SIZE[1]), fill=(219, 158, 93, 255))
        draw.rectangle((MAP_SIZE + 8, 8, CANVAS_SIZE[0] - 8, CANVAS_SIZE[1] - 8), fill=(238, 194, 132, 220), outline=(91, 56, 32, 170), width=2)
        header_color = (63, 39, 24, 245)
        note_color = (103, 68, 43, 235)
    else:
        draw.rectangle((MAP_SIZE, 0, CANVAS_SIZE[0], CANVAS_SIZE[1]), fill=(18, 18, 15, 255))
        header_color = (255, 244, 220, 245)
        note_color = (170, 161, 146, 230)
    draw.text((x, y), "Layers", fill=header_color, font=header)
    y += 38
    for name, color in LAYER_COLORS.items():
        count = sum(1 for row in hotspots if row.get("name") == name)
        y = legend_line(draw, x, y, name, f"{count} hotspot{'s' if count != 1 else ''}", color, style=style)
    y += 16
    draw.text((x, y), "DB Markers", fill=header_color, font=header)
    y += 36
    for marker_type, count in sorted(markers_by_type.items(), key=lambda item: (-item[1], item[0]))[:18]:
        y = legend_line(draw, x, y, marker_type, count, MARKER_COLORS.get(marker_group(marker_type), MARKER_COLORS["Markers"]), style=style)
    y += 16
    draw.text((x, y), "Field State", fill=header_color, font=header)
    y += 36
    if db_state.get("resources"):
        for row in db_state["resources"][:8]:
            label = f"dim {row.get('dimension_index')} kind {row.get('field_kind_id')}"
            value = f"{row.get('fields')} fields"
            y = legend_line(draw, x, y, label, value, swatch=False, style=style)
    else:
        y = legend_line(draw, x, y, "resource fields unavailable", swatch=False, style=style)
    y += 10
    if db_state.get("spice"):
        for row in db_state["spice"][:8]:
            label = f"spice d{row.get('dimension_index')} {row.get('field_type')}"
            value = f"{row.get('current_globally_active')}/{row.get('max_globally_active')} active"
            y = legend_line(draw, x, y, label, value, swatch=False, style=style)
    else:
        y = legend_line(draw, x, y, "spice state unavailable", swatch=False, style=style)
    y += 16
    draw.text((x, y), "Scan Coverage", fill=header_color, font=header)
    y += 36
    if db_state.get("scanCoverage"):
        for row in db_state["scanCoverage"]:
            label = f"{row.get('character_name')} areas"
            value = f"{row.get('rows')} rows, {row.get('survey_rows')} surveyed"
            y = legend_line(draw, x, y, label, value, swatch=False, style=style)
    else:
        y = legend_line(draw, x, y, "Paul coverage unavailable", swatch=False, style=style)
    y += 20
    note = "Resource hotspots are distribution masks. DB markers are exact persisted marker rows where present."
    for offset in range(0, len(note), 44):
        draw.text((x, y), note[offset:offset + 44], fill=note_color, font=small)
        y += 18
    if not db_state.get("ok"):
        y += 10
        draw.text((x, y), "DB query failed:", fill=(255, 180, 110, 240), font=small)
        y += 18
        error = str(db_state.get("error") or "unknown")
        for offset in range(0, min(len(error), 180), 44):
            draw.text((x, y), error[offset:offset + 44], fill=(255, 180, 110, 220), font=small)
            y += 18


def main():
    parser = argparse.ArgumentParser(description="Render a full Deep Desert map from stitched heatmaps and server-side state.")
    parser.add_argument("--env-file", type=pathlib.Path, default=ROOT / ".env")
    parser.add_argument("--database", default=None)
    parser.add_argument("--background", type=pathlib.Path, default=ROOT / "admin" / "static" / "deep-desert.webp")
    parser.add_argument("--hotspots", type=pathlib.Path, default=ROOT / "admin" / "static" / "deep-desert-hotspots.json")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "admin" / "static" / "deep-desert-full-map.webp")
    parser.add_argument("--png-output", type=pathlib.Path, default=ROOT / "admin" / "static" / "deep-desert-full-map.png")
    parser.add_argument("--manifest-output", type=pathlib.Path, default=ROOT / "admin" / "static" / "deep-desert-full-map.json")
    parser.add_argument("--style", choices=("ingame", "schematic"), default="ingame")
    parser.add_argument("--no-legend", action="store_true", help="Render the map without the right-side legend panel.")
    parser.add_argument("--no-db", action="store_true", help="Render only static background and hotspot data.")
    args = parser.parse_args()

    env = env_file_values(args.env_file)
    database = args.database or os.environ.get("DUNE_DB_NAME") or env.get("DUNE_DB_NAME") or "dune_sb_1_4_0_0"
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    background = load_background(args.background, args.style)
    hotspot_data = {}
    if args.hotspots.exists():
        hotspot_data = json.loads(args.hotspots.read_text(encoding="utf-8"))
    hotspots = list(hotspot_data.get("hotspots") or [])
    db_state = {"ok": False, "error": "DB disabled", "markers": [], "resources": [], "spice": [], "scanCoverage": []}
    if not args.no_db:
        db_state = load_db_state(ROOT, args.env_file, database)

    canvas_size = (MAP_SIZE, MAP_SIZE) if args.no_legend else CANVAS_SIZE
    canvas = Image.new("RGB", canvas_size, (18, 18, 15))
    canvas.paste(background, (0, 0))
    overlay = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw_hotspots(draw, hotspots, args.style)
    markers_by_type = draw_db_markers(draw, db_state.get("markers") or [], DEFAULT_BOUNDS, args.style)
    draw_grid(draw, args.style)
    draw_title(draw, generated_at, args.style)
    if not args.no_legend:
        draw_legend(draw, hotspots, markers_by_type, db_state, args.style)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, "WEBP", quality=91, method=6)
    if args.png_output:
        args.png_output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(args.png_output, "PNG")
    if args.manifest_output:
        manifest = {
            "generatedAt": generated_at,
            "background": str(args.background),
            "hotspots": str(args.hotspots),
            "output": str(args.output),
            "style": args.style,
            "legend": not args.no_legend,
            "database": database,
            "dbOk": db_state.get("ok"),
            "dbError": db_state.get("error"),
            "hotspotCount": len(hotspots),
            "markerCount": len(db_state.get("markers") or []),
            "resourceSummaries": db_state.get("resources") or [],
            "spice": db_state.get("spice") or [],
            "scanCoverage": db_state.get("scanCoverage") or [],
            "bounds": DEFAULT_BOUNDS,
            "confidence": {
                "heatmaps": "moderate: broad distribution masks, not exact node coordinates",
                "dbMarkers": "high for persisted marker rows, mixed for whether every live node is present",
                "scanCoverage": "high for dune.map_areas row counts",
            },
        }
        args.manifest_output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    if args.png_output:
        print(f"wrote {args.png_output}")
    if args.manifest_output:
        print(f"wrote {args.manifest_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
