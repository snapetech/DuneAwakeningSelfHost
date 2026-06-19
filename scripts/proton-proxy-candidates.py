#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


PREFERRED = (
    "version.dll",
    "dxgi.dll",
    "winmm.dll",
    "xinput1_3.dll",
    "d3d9.dll",
    "d3d11.dll",
    "dsound.dll",
    "dinput8.dll",
)


def objdump_imports(exe):
    result = subprocess.run(
        ["llvm-objdump", "-p", str(exe)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    imports = {}
    current = None
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if line.startswith("DLL Name:"):
            current = line.split(":", 1)[1].strip().lower()
            imports.setdefault(current, [])
        elif current and line and not line.startswith("Hint/Ord") and line[0].isdigit():
            parts = line.split()
            if len(parts) >= 2:
                imports[current].append(parts[-1])
        elif line.startswith("lookup "):
            current = None
    return imports


def manifest_owned(path, manifest):
    if not manifest or not manifest.exists() or not path.exists():
        return False
    manifest_target = ""
    manifest_sha = ""
    for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("target="):
            manifest_target = line.split("=", 1)[1]
        elif "  " in line and not manifest_sha:
            manifest_sha = line.split()[0]
    if manifest_target != str(path) or not manifest_sha:
        return False
    result = subprocess.run(["sha256sum", str(path)], text=True, stdout=subprocess.PIPE, check=True)
    return result.stdout.split()[0] == manifest_sha


def score_candidate(name, imports, exe_dir, manifest=None):
    imported = name.lower() in imports
    existing = exe_dir / name
    owned = manifest_owned(existing, manifest)
    preferred_index = PREFERRED.index(name) if name in PREFERRED else len(PREFERRED)
    risk = "low"
    notes = []
    score = 0

    if imported:
        score += 100
        notes.append("imported-by-exe")
    else:
        notes.append("not-imported-by-exe")

    if existing.exists() and owned:
        score += 10
        notes.append("existing-file-is-manifest-owned-probe")
    elif existing.exists():
        score -= 35
        risk = "medium"
        notes.append("existing-file-would-need-backup")
    else:
        score += 10
        notes.append("no-existing-file")

    if name in ("dxgi.dll", "d3d11.dll", "d3d9.dll"):
        risk = "medium" if risk == "low" else risk
        notes.append("graphics-proxy-can-affect-renderer")
    if name in ("xinput1_3.dll", "dsound.dll", "winmm.dll"):
        notes.append("peripheral-audio-proxy")
    if name == "version.dll":
        score += 20
        notes.append("small-forward-surface")

    score -= preferred_index
    return {
        "name": name,
        "score": score,
        "risk": risk,
        "imported": imported,
        "manifestOwned": owned,
        "existingPath": str(existing) if existing.exists() else "",
        "importedFunctions": imports.get(name.lower(), []),
        "notes": notes,
    }


def summarize(exe, candidates, manifest=None):
    exe_dir = exe.parent
    imports = objdump_imports(exe)
    names = list(dict.fromkeys([name.lower() for name in candidates] + list(PREFERRED)))
    rows = [score_candidate(name, imports, exe_dir, manifest) for name in names]
    rows.sort(key=lambda row: (-row["score"], row["name"]))
    return {
        "exe": str(exe),
        "exeDir": str(exe_dir),
        "importCount": len(imports),
        "candidates": rows,
        "best": rows[0] if rows else {},
    }


def markdown(summary):
    lines = []
    lines.append("# Proton Proxy Candidate Summary")
    lines.append("")
    lines.append(f"- Exe: `{summary['exe']}`")
    lines.append(f"- Import DLL count: `{summary['importCount']}`")
    if summary["best"]:
        lines.append(f"- Best candidate: `{summary['best']['name']}` score=`{summary['best']['score']}` risk=`{summary['best']['risk']}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in summary["candidates"]:
        funcs = ", ".join(row["importedFunctions"][:6])
        if len(row["importedFunctions"]) > 6:
            funcs += f", ... +{len(row['importedFunctions']) - 6}"
        notes = ", ".join(row["notes"])
        existing = f" existing=`{row['existingPath']}`" if row["existingPath"] else ""
        lines.append(
            f"- `{row['name']}` score=`{row['score']}` risk=`{row['risk']}` imported=`{str(row['imported']).lower()}`{existing} notes=`{notes}` funcs=`{funcs}`"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank Proton proxy DLL candidates from a PE import table.")
    parser.add_argument("exe", type=Path)
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=Path("build/windows-client-loader/game-dir-stage-manifest.txt"))
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    if not args.exe.exists():
        parser.error(f"missing exe: {args.exe}")
    summary = summarize(args.exe, args.candidate, args.manifest)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))


if __name__ == "__main__":
    main()
