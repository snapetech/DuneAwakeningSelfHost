#!/usr/bin/env python3
import datetime
import html
import json
import os
import pathlib
import shutil
import subprocess
import sys


DUNE_ROOT = pathlib.Path(os.environ.get("DUNE_ROOT", "/opt/DuneAwakeningSelfHost"))
STATIC_DIR = pathlib.Path(os.environ.get("STATIC_DIR", "/srv/dash-public-site"))
DATABASE = os.environ.get("DUNE_DATABASE", "dune_sb_1_4_0_0")
WIDTH = 1600
HEIGHT = 1600


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


ENV = env_file_values(DUNE_ROOT / ".env")


def bool_env(key, default):
    value = ENV.get(key, os.environ.get(key, default))
    return str(value).lower() not in ("0", "false", "no", "off")


def float_env(key, default):
    try:
        return float(ENV.get(key, os.environ.get(key, default)))
    except ValueError:
        return float(default)


CAL = {
    "min_x": float_env("DUNE_HAGGA_MAP_MIN_X", "-407000"),
    "max_x": float_env("DUNE_HAGGA_MAP_MAX_X", "407000"),
    "min_y": float_env("DUNE_HAGGA_MAP_MIN_Y", "-403500"),
    "max_y": float_env("DUNE_HAGGA_MAP_MAX_Y", "403500"),
    "invert_x": bool_env("DUNE_HAGGA_MAP_INVERT_X", "true"),
    "invert_y": bool_env("DUNE_HAGGA_MAP_INVERT_Y", "false"),
    "image_min_u": float_env("DUNE_HAGGA_MAP_IMAGE_MIN_U", "0.15"),
    "image_max_u": float_env("DUNE_HAGGA_MAP_IMAGE_MAX_U", "1.15"),
    "image_min_v": float_env("DUNE_HAGGA_MAP_IMAGE_MIN_V", "0.10"),
    "image_max_v": float_env("DUNE_HAGGA_MAP_IMAGE_MAX_V", "1.10"),
}


def compose_psql(sql):
    cmd = [
        "docker",
        "compose",
        "--env-file",
        ".env",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "dune",
        "-d",
        DATABASE,
        "-X",
        "-q",
        "-t",
        "-A",
        "-c",
        "copy (" + sql + ") to stdout",
    ]
    return subprocess.check_output(cmd, cwd=DUNE_ROOT, text=True, timeout=20)


def load_rows():
    sql = r"""
        select coalesce(json_agg(row_to_json(t)), '[]'::json)
        from (
            select coalesce(ps.character_name, 'Unnamed') as character_name,
                   ps.online_status::text as online_status,
                   ps.life_state::text as life_state,
                   coalesce(wp.label, fs.map, ps.server_id, 'Unknown') as public_location,
                   fs.map as farm_map,
                   a.map as actor_map,
                   ((a.transform).location).x::float8 as x,
                   ((a.transform).location).y::float8 as y
            from dune.player_state ps
            left join dune.farm_state fs on fs.server_id = ps.server_id
            left join dune.world_partition wp on wp.server_id = ps.server_id
            left join dune.actors a on a.id = ps.player_pawn_id
            where ps.online_status::text = 'Online'
            order by ps.character_name nulls last, ps.account_id
        ) t
    """
    text = compose_psql(sql).strip() or "[]"
    return json.loads(text)


def clamp(value, low, high):
    return max(low, min(high, value))


def project(x, y):
    u = (float(x) - CAL["min_x"]) / (CAL["max_x"] - CAL["min_x"])
    v = (float(y) - CAL["min_y"]) / (CAL["max_y"] - CAL["min_y"])
    if CAL["invert_x"]:
        u = 1 - u
    if CAL["invert_y"]:
        v = 1 - v
    u = CAL["image_min_u"] + u * (CAL["image_max_u"] - CAL["image_min_u"])
    v = CAL["image_min_v"] + v * (CAL["image_max_v"] - CAL["image_min_v"])
    return clamp(u * WIDTH, 0, WIDTH), clamp(v * HEIGHT, 0, HEIGHT)


def render_svg(players, generated_at):
    hagga = [
        p for p in players
        if p.get("actor_map") == "HaggaBasin" and p.get("x") is not None and p.get("y") is not None
    ]
    grid = []
    for i in range(1, 4):
        pos = WIDTH * i / 4
        grid.append(f'<line x1="{pos:.1f}" y1="0" x2="{pos:.1f}" y2="{HEIGHT}" class="grid"/>')
        grid.append(f'<line x1="0" y1="{pos:.1f}" x2="{WIDTH}" y2="{pos:.1f}" class="grid"/>')
    markers = []
    for player in hagga:
        x, y = project(player["x"], player["y"])
        name = html.escape(str(player.get("character_name") or "Player"))
        label_x = clamp(x + 16, 10, WIDTH - 180)
        label_y = clamp(y - 14, 24, HEIGHT - 20)
        markers.append(
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="10" class="dot"/>'
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="label">{name}</text></g>'
        )
    empty = ""
    if not hagga:
        empty = f'<text x="{WIDTH / 2}" y="{HEIGHT / 2}" class="empty">No online Hagga Basin positions.</text>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Hagga Basin live player map">
<style>
.shade{{fill:rgba(4,5,4,.28)}}.grid{{stroke:#f1d08a;stroke-width:1;opacity:.24}}.dot{{fill:#78cf7a;stroke:#071007;stroke-width:4}}.label{{fill:#fff;font:700 24px system-ui,sans-serif;paint-order:stroke;stroke:#0b0d0a;stroke-width:7}}.meta{{fill:#c7bba9;font:20px system-ui,sans-serif}}.empty{{fill:#f3eadb;font:26px system-ui,sans-serif;text-anchor:middle;paint-order:stroke;stroke:#0b0d0a;stroke-width:6}}
</style>
<image href="/hagga-basin.webp" x="0" y="0" width="{WIDTH}" height="{HEIGHT}" preserveAspectRatio="xMidYMid meet"/>
<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" class="shade"/>
{''.join(grid)}
<text x="22" y="38" class="meta">NW</text>
<text x="{WIDTH - 56}" y="{HEIGHT - 24}" class="meta">SE</text>
<text x="22" y="{HEIGHT - 24}" class="meta">Updated {html.escape(generated_at)}</text>
{''.join(markers)}
{empty}
</svg>
'''


def main():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        players = load_rows()
        ok = True
        error = None
    except Exception as exc:
        players = []
        ok = False
        error = str(exc)

    public_players = [
        {
            "name": p.get("character_name") or "Unnamed",
            "location": p.get("public_location") or "Unknown",
            "lifeState": p.get("life_state") or "",
            "onHaggaMap": p.get("actor_map") == "HaggaBasin" and p.get("x") is not None and p.get("y") is not None,
        }
        for p in players
    ]
    snapshot = {
        "ok": ok,
        "generatedAt": generated,
        "onlineCount": len(public_players),
        "haggaPlotted": sum(1 for p in public_players if p["onHaggaMap"]),
        "players": public_players,
        "error": error,
    }
    (STATIC_DIR / "players.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    (STATIC_DIR / "hagga-map.svg").write_text(render_svg(players, generated), encoding="utf-8")
    source_map = DUNE_ROOT / "admin" / "static" / "hagga-basin.webp"
    if source_map.exists():
        shutil.copyfile(source_map, STATIC_DIR / "hagga-basin.webp")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
