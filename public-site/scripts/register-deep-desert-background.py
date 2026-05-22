#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys


DEFAULT_BOUNDS = {
    "min_x": -1167448.0,
    "max_x": 943584.0,
    "min_y": -1329426.0,
    "max_y": 1211103.0,
}
OUT_WIDTH = 2133
OUT_HEIGHT = 1600


def map_point(world, bounds):
    x, y = float(world[0]), float(world[1])
    u = (x - bounds["min_x"]) / max(bounds["max_x"] - bounds["min_x"], 1)
    v = (y - bounds["min_y"]) / max(bounds["max_y"] - bounds["min_y"], 1)
    return u * OUT_WIDTH, v * OUT_HEIGHT


def affine_from_three(src, dst):
    # Returns coefficients mapping dst/output pixels to src/input pixels.
    (x1, y1), (x2, y2), (x3, y3) = dst
    (u1, v1), (u2, v2), (u3, v3) = src
    det = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
    if abs(det) < 1e-9:
        raise ValueError("control points are collinear")

    def coeff(values):
        a1, a2, a3 = values
        a = (a1 * (y2 - y3) + a2 * (y3 - y1) + a3 * (y1 - y2)) / det
        b = (x1 * (a2 - a3) + x2 * (a3 - a1) + x3 * (a1 - a2)) / det
        c = (x1 * (y3 * a2 - y2 * a3) + x2 * (y1 * a3 - y3 * a1) + x3 * (y2 * a1 - y1 * a2)) / det
        return a, b, c

    return (*coeff((u1, u2, u3)), *coeff((v1, v2, v3)))


def main():
    parser = argparse.ArgumentParser(description="Register a weekly Deep Desert map screenshot to the DASH map coordinate frame.")
    parser.add_argument("source", help="Screenshot or exported map image.")
    parser.add_argument("control_points", help="JSON with at least three {world:[x,y], pixel:[x,y]} control points.")
    parser.add_argument("--output", default="admin/static/deep-desert.webp")
    parser.add_argument("--bounds", nargs=4, type=float, metavar=("MIN_X", "MAX_X", "MIN_Y", "MAX_Y"), default=None)
    args = parser.parse_args()

    try:
        from PIL import Image
    except Exception as exc:
        print(f"Pillow is required for image registration: {exc}", file=sys.stderr)
        return 2

    source = pathlib.Path(args.source)
    controls = json.loads(pathlib.Path(args.control_points).read_text(encoding="utf-8"))
    if len(controls) < 3:
        print("Need at least three control points.", file=sys.stderr)
        return 2

    bounds = dict(DEFAULT_BOUNDS)
    if args.bounds:
        bounds = {"min_x": args.bounds[0], "max_x": args.bounds[1], "min_y": args.bounds[2], "max_y": args.bounds[3]}

    output_points = [map_point(row["world"], bounds) for row in controls[:3]]
    source_points = [tuple(map(float, row["pixel"])) for row in controls[:3]]
    coeffs = affine_from_three(source_points, output_points)

    image = Image.open(source).convert("RGB")
    resample = getattr(Image, "Resampling", Image).BICUBIC
    registered = image.transform((OUT_WIDTH, OUT_HEIGHT), Image.Transform.AFFINE, coeffs, resample=resample)
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    registered.save(output, "WEBP", quality=88, method=6)
    meta = output.with_suffix(".registration.json")
    meta.write_text(json.dumps({"source": str(source), "bounds": bounds, "controlPoints": controls[:3]}, indent=2), encoding="utf-8")
    print(f"wrote {output} and {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
