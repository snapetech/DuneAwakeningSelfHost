#!/usr/bin/env python3
"""Generate a deterministic static landing page from a small JSON manifest."""

import argparse
import hashlib
import html
import json
import pathlib
import re
import shutil
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
LANDING_ROOT = ROOT / "landing"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
UNSAFE_SVG_RE = re.compile(
    r"<(?:script|foreignObject|iframe|object|embed)\b|\bon[a-z]+\s*=|javascript:",
    re.IGNORECASE,
)


def fail(message):
    raise ValueError(message)


def required_text(value, field, maximum=160):
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum:
        fail(f"{field} must be at most {maximum} characters")
    return value


def optional_text(value, field, maximum=240):
    if value is None:
        return ""
    if not isinstance(value, str):
        fail(f"{field} must be a string")
    value = value.strip()
    if len(value) > maximum:
        fail(f"{field} must be at most {maximum} characters")
    return value


def color(value, field):
    value = required_text(value, field, 7)
    if not COLOR_RE.fullmatch(value):
        fail(f"{field} must be a six-digit hex color")
    return value.lower()


def href(value, field):
    value = required_text(value, field, 500)
    if value.startswith("/") and not value.startswith("//"):
        return value
    if value.startswith("https://"):
        return value
    fail(f"{field} must be a root-relative path or an https URL")


def icon_source(config_dir, value, field):
    value = required_text(value, field, 240)
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        fail(f"{field} must stay inside the config directory")
    source = (config_dir / pathlib.Path(*path.parts)).resolve()
    try:
        source.relative_to(config_dir.resolve())
    except ValueError:
        fail(f"{field} must stay inside the config directory")
    if source.suffix.lower() not in (".svg", ".webp", ".png", ".jpg", ".jpeg"):
        fail(f"{field} must be an SVG, WebP, PNG, or JPEG image")
    if not source.is_file() or source.stat().st_size == 0:
        fail(f"{field} does not exist or is empty: {source}")
    if source.stat().st_size > 8 * 1024 * 1024:
        fail(f"{field} must be no larger than 8 MiB")
    if source.suffix.lower() == ".svg":
        try:
            svg = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"{field} must be UTF-8 SVG text")
        if not re.search(r"<svg\b", svg, re.IGNORECASE) or UNSAFE_SVG_RE.search(svg):
            fail(f"{field} contains unsafe or invalid SVG content")
    return source


def load_manifest(config_path):
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("manifest root must be an object")

    manifest = {
        "site_name": required_text(data.get("site_name"), "site_name", 80),
        "eyebrow": optional_text(data.get("eyebrow"), "eyebrow", 100),
        "heading": required_text(data.get("heading"), "heading", 120),
        "intro": optional_text(data.get("intro"), "intro", 240),
        "footer": optional_text(data.get("footer"), "footer", 160),
        "games": [],
    }
    games = data.get("games")
    if not isinstance(games, list) or not 1 <= len(games) <= 8:
        fail("games must contain between 1 and 8 entries")

    seen = set()
    for index, raw in enumerate(games):
        prefix = f"games[{index}]"
        if not isinstance(raw, dict):
            fail(f"{prefix} must be an object")
        slug = required_text(raw.get("slug"), f"{prefix}.slug", 48).lower()
        if not SLUG_RE.fullmatch(slug):
            fail(f"{prefix}.slug must contain lowercase letters, digits, or hyphens")
        if slug in seen:
            fail(f"duplicate game slug: {slug}")
        seen.add(slug)
        manifest["games"].append({
            "slug": slug,
            "name": required_text(raw.get("name"), f"{prefix}.name", 80),
            "label": required_text(raw.get("label"), f"{prefix}.label", 16),
            "description": optional_text(raw.get("description"), f"{prefix}.description", 180),
            "href": href(raw.get("href"), f"{prefix}.href"),
            "icon": icon_source(config_path.parent, raw.get("icon"), f"{prefix}.icon"),
            "accent": color(raw.get("accent"), f"{prefix}.accent"),
            "accent_soft": color(raw.get("accent_soft"), f"{prefix}.accent_soft"),
            "ink": color(raw.get("ink"), f"{prefix}.ink"),
        })
    return manifest


def escaped(value):
    return html.escape(value, quote=True)


def render_index(manifest, asset_names, css_version):
    cards = []
    for index, game in enumerate(manifest["games"]):
        description = ""
        if game["description"]:
            description = f'<span class="game-description">{escaped(game["description"])}</span>'
        external = ' target="_blank" rel="noopener noreferrer"' if game["href"].startswith("https://") else ""
        cards.append(
            f'''<a class="game-link game-{index}" href="{escaped(game["href"])}" aria-label="Open {escaped(game["name"])}"{external}>
<span class="game-art"><img src="assets/{escaped(asset_names[index])}" alt="" width="720" height="720"></span>
<span class="game-copy"><span class="game-label">{escaped(game["label"])}</span><span class="game-name">{escaped(game["name"])}</span>{description}</span>
<span class="game-arrow" aria-hidden="true">↗</span>
</a>'''
        )

    eyebrow = f'<p class="eyebrow">{escaped(manifest["eyebrow"])}</p>' if manifest["eyebrow"] else ""
    intro = f'<p class="intro">{escaped(manifest["intro"])}</p>' if manifest["intro"] else ""
    footer = f'<p>{escaped(manifest["footer"])}</p>' if manifest["footer"] else ""
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{escaped(manifest["intro"] or manifest["heading"])}">
<meta name="theme-color" content="#0d1118">
<title>{escaped(manifest["site_name"])} · {escaped(manifest["heading"])}</title>
<link rel="stylesheet" href="landing.css?v={css_version}">
<link rel="stylesheet" href="landing-generated.css?v={css_version}">
</head>
<body>
<a class="skip-link" href="#games">Skip to game links</a>
<div class="page-shell">
<header class="masthead"><a class="wordmark" href="/">{escaped(manifest["site_name"])}</a><span>Community game servers</span></header>
<main>
<div class="hero-copy">{eyebrow}<h1>{escaped(manifest["heading"])}</h1>{intro}</div>
<nav id="games" class="game-grid" aria-label="Game servers">
{"".join(cards)}
</nav>
</main>
<footer>{footer}<span>Choose a world to continue</span></footer>
</div>
</body>
</html>
'''


def render_generated_css(manifest):
    lines = [f".game-grid {{ --game-count: {len(manifest['games'])}; }}"]
    for index, game in enumerate(manifest["games"]):
        lines.append(
            f".game-{index} {{ --accent: {game['accent']}; --accent-soft: {game['accent_soft']}; --game-ink: {game['ink']}; }}"
        )
    return "\n".join(lines) + "\n"


def write_if_changed(path, content):
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def generate(config_path, output_dir):
    manifest = load_manifest(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = output_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    asset_names = []
    for game in manifest["games"]:
        digest = hashlib.sha256(game["icon"].read_bytes()).hexdigest()[:12]
        name = f"{game['slug']}-{digest}{game['icon'].suffix.lower()}"
        shutil.copyfile(game["icon"], asset_dir / name)
        asset_names.append(name)

    base_css = (LANDING_ROOT / "landing.css").read_text(encoding="utf-8")
    generated_css = render_generated_css(manifest)
    css_version = hashlib.sha256((base_css + generated_css).encode("utf-8")).hexdigest()[:12]
    write_if_changed(output_dir / "landing.css", base_css)
    write_if_changed(output_dir / "landing-generated.css", generated_css)
    write_if_changed(output_dir / "index.html", render_index(manifest, asset_names, css_version))

    keep = set(asset_names)
    for stale in asset_dir.iterdir():
        if stale.is_file() and stale.name not in keep:
            stale.unlink()
    print(f"Generated {len(manifest['games'])} game link(s) in {output_dir}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, default=LANDING_ROOT / "game-links.example.json")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        generate(args.config.resolve(), args.output.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"game landing generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
