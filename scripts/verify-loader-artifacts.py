#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    "linux-server": {
        "paths": (
            ROOT / "build" / "linux-server-loader" / "libdune_server_probe_loader.so",
            ROOT / "lib" / "libdune_server_probe_loader.so",
        ),
        "kind": "elf",
        "soname": "libdune_server_probe_loader.so",
    },
    "linux-client": {
        "paths": (
            ROOT / "build" / "linux-client-loader" / "libdune_client_probe_loader.so",
            ROOT / "lib" / "libdune_client_probe_loader.so",
        ),
        "kind": "elf",
        "soname": "libdune_client_probe_loader.so",
    },
    "windows-client": {
        "paths": (
            ROOT / "build" / "windows-client-loader" / "dune_win_client_probe_loader.dll",
            ROOT / "lib" / "dune_win_client_probe_loader.dll",
            ROOT / "lib" / "version.dll",
        ),
        "kind": "pe",
        "exports": (
            "DuneWinClientProbeSmoke",
            "DuneWinClientProbeForwardSmoke",
            "DuneWinClientProbeMarker",
            "GetFileVersionInfoA",
            "GetFileVersionInfoW",
            "GetFileVersionInfoSizeA",
            "GetFileVersionInfoSizeW",
            "VerQueryValueA",
            "VerQueryValueW",
        ),
    },
}


def run_command(argv):
    return subprocess.run(
        [str(arg) for arg in argv],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def command_text(argv, missing_ok=False):
    result = run_command(argv)
    if result.returncode != 0:
        if missing_ok:
            return None, result.stdout + result.stderr
        raise RuntimeError(f"{' '.join(str(arg) for arg in argv)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout, ""


def require_contains(text, needle, missing):
    if needle not in text:
        missing.append(needle)


def resolve_path(config):
    if "path" in config:
        return Path(config["path"])
    for path in config.get("paths", ()):
        candidate = Path(path)
        if candidate.is_file():
            return candidate
    paths = list(config.get("paths", ()))
    return Path(paths[0]) if paths else Path("")


def verify_elf(target, config):
    path = resolve_path(config)
    missing = []
    details = {"path": str(path), "kind": "elf"}
    if not path.is_file():
        return {"target": target, "passed": False, "missing": [f"file:{path}"], "details": details}

    file_text, _ = command_text(["file", path])
    header_text, _ = command_text(["readelf", "-h", path])
    dynamic_text, _ = command_text(["readelf", "-d", path])

    require_contains(file_text, "ELF 64-bit LSB shared object", missing)
    require_contains(file_text, "x86-64", missing)
    require_contains(header_text, "Type:                              DYN (Shared object file)", missing)
    require_contains(header_text, "Machine:                           Advanced Micro Devices X86-64", missing)
    require_contains(dynamic_text, f"Library soname: [{config['soname']}]", missing)
    require_contains(dynamic_text, "Shared library: [libc.so.6]", missing)

    details.update(
        {
            "file": file_text.strip(),
            "soname": config["soname"],
        }
    )
    return {"target": target, "passed": not missing, "missing": missing, "details": details}


def objdump_output(path):
    for command in ("x86_64-w64-mingw32-objdump", "llvm-objdump", "objdump"):
        result = run_command([command, "-x", path])
        if result.returncode == 0:
            return result.stdout, command
    raise RuntimeError(f"no objdump variant could inspect {path}")


def verify_pe(target, config):
    path = resolve_path(config)
    missing = []
    details = {"path": str(path), "kind": "pe"}
    if not path.is_file():
        return {"target": target, "passed": False, "missing": [f"file:{path}"], "details": details}

    file_text, _ = command_text(["file", path])
    objdump_text, objdump_command = objdump_output(path)

    require_contains(file_text, "PE32+ executable", missing)
    require_contains(file_text, "x86-64", missing)
    require_contains(file_text, "(DLL)", missing)
    require_contains(objdump_text, "DLL Name: KERNEL32.dll", missing)
    require_contains(objdump_text, "Subsystem", missing)
    require_contains(objdump_text, "(Windows GUI)", missing)
    require_contains(objdump_text, "Export Tables", missing)
    for export in config["exports"]:
        require_contains(objdump_text, export, missing)

    details.update(
        {
            "file": file_text.strip(),
            "objdump": objdump_command,
            "requiredExports": list(config["exports"]),
        }
    )
    return {"target": target, "passed": not missing, "missing": missing, "details": details}


def verify_target(target):
    config = TARGETS[target]
    if config["kind"] == "elf":
        return verify_elf(target, config)
    if config["kind"] == "pe":
        return verify_pe(target, config)
    raise ValueError(f"unknown target kind: {config['kind']}")


def target_has_existing_artifact(target):
    return resolve_path(TARGETS[target]).is_file()


def default_targets():
    existing = [target for target in TARGETS if target_has_existing_artifact(target)]
    return existing or list(TARGETS)


def render_text(report):
    lines = [f"loader_artifacts_ok={str(report['passed']).lower()}"]
    for target, row in report["targets"].items():
        lines.append(
            f"{target} passed={str(row['passed']).lower()} "
            f"path={row['details'].get('path', '')} "
            f"missing={','.join(row.get('missing', [])) or 'none'}"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify built Dune UE4SS-style loader artifacts.")
    parser.add_argument(
        "--target",
        action="append",
        choices=tuple(TARGETS) + ("all",),
        default=[],
        help="Artifact target to verify. Defaults to all.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    selected = args.target or default_targets()
    if "all" in selected:
        selected = list(TARGETS)

    targets = {target: verify_target(target) for target in selected}
    report = {
        "schemaVersion": "dune-loader-artifact-verification/v1",
        "passed": all(row["passed"] for row in targets.values()),
        "targets": targets,
    }

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
