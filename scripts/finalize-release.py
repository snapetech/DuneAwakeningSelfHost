#!/usr/bin/env python3
"""Finalize and verify a complete DASH release asset directory."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import mimetypes
import os
import pathlib
import re
import subprocess
import tarfile


TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = "https://github.com/snapetech/DuneAwakeningSelfHost"
GENERATED = {"SHA256SUMS", "release-manifest.json", "release-provenance.intoto.json"}


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: pathlib.Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def commit_time(root: pathlib.Path, commit: str) -> str:
    epoch = int(subprocess.check_output(["git", "-C", str(root), "show", "-s", "--format=%ct", commit], text=True).strip())
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def required_names(tag: str) -> set[str]:
    return {
        f"dash-{tag}-linux-x86_64.tar.gz",
        f"dash-{tag}-linux-x86_64.tar.gz.sha256",
        f"dash-{tag}-linux-x86_64.spdx.json",
        f"dune-linux-server-loader-{tag}-linux-x86_64.tar.gz",
        f"dune-linux-server-loader-{tag}-linux-x86_64.tar.gz.sha256",
        f"dune-linux-server-loader-{tag}-linux-x86_64.tar.gz.verification.json",
        f"dune-linux-client-loader-{tag}-linux-x86_64.tar.gz",
        f"dune-linux-client-loader-{tag}-linux-x86_64.tar.gz.sha256",
        f"dune-linux-client-loader-{tag}-linux-x86_64.tar.gz.verification.json",
        f"dune-windows-client-loader-{tag}-windows-x86_64.tar.gz",
        f"dune-windows-client-loader-{tag}-windows-x86_64.tar.gz.sha256",
        f"dune-windows-client-loader-{tag}-windows-x86_64.tar.gz.verification.json",
        "RELEASE_NOTES.md",
    }


def files_in(directory: pathlib.Path, *, exclude=()) -> list[pathlib.Path]:
    excluded = set(exclude)
    rows = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.name in excluded:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"release asset must be a regular non-symlink file: {path}")
        if "/" in path.name or path.name.startswith("."):
            raise ValueError(f"unsafe release asset name: {path.name}")
        rows.append(path)
    return rows


def role(name: str) -> str:
    if name.startswith("dash-") and name.endswith("linux-x86_64.tar.gz"):
        return "server-source-bundle"
    if name.endswith(".spdx.json"):
        return "sbom"
    if "loader" in name and name.endswith(".tar.gz"):
        return "experimental-loader-bundle"
    if name.endswith(".verification.json"):
        return "verification-receipt"
    if name.endswith(".sha256") or name == "SHA256SUMS":
        return "checksum"
    if name == "RELEASE_NOTES.md":
        return "release-notes"
    if name.endswith("intoto.json"):
        return "provenance"
    return "release-metadata"


def asset_row(path: pathlib.Path) -> dict:
    media, _encoding = mimetypes.guess_type(path.name)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path), "mediaType": media or "application/octet-stream", "role": role(path.name)}


def finalize(root: pathlib.Path, directory: pathlib.Path, tag: str, commit: str) -> dict:
    if not TAG_RE.fullmatch(tag) or not COMMIT_RE.fullmatch(commit):
        raise ValueError("invalid release tag or commit")
    directory.mkdir(parents=True, exist_ok=True)
    for name in GENERATED:
        (directory / name).unlink(missing_ok=True)
    present = {path.name for path in files_in(directory)}
    missing = sorted(required_names(tag) - present)
    if missing:
        raise ValueError("missing required release assets: " + ", ".join(missing))
    for receipt in directory.glob("*.verification.json"):
        value = json.loads(receipt.read_text(encoding="utf-8"))
        if value.get("schemaVersion") != "dune-loader-artifact-verification/v1" or not value.get("passed"):
            raise ValueError(f"loader verification did not pass: {receipt.name}")
    created = commit_time(root, commit)
    subjects = [{"name": path.name, "digest": {"sha256": digest(path)}} for path in files_in(directory)]
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": f"{REPOSITORY}/blob/{commit}/.github/workflows/release.yml",
                "externalParameters": {"tag": tag, "commit": commit, "serverPlatform": "linux-x86_64"},
                "internalParameters": {},
                "resolvedDependencies": [{"uri": f"git+{REPOSITORY}.git", "digest": {"gitCommit": commit}}],
            },
            "runDetails": {
                "builder": {"id": f"{REPOSITORY}/actions/workflows/release.yml"},
                "metadata": {
                    "invocationId": (
                        f"{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}/attempts/{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
                        if os.environ.get("GITHUB_RUN_ID")
                        else f"local:{commit}"
                    ),
                    "startedOn": created,
                    "finishedOn": created,
                },
            },
        },
    }
    write_json(directory / "release-provenance.intoto.json", provenance)
    assets = [asset_row(path) for path in files_in(directory, exclude={"release-manifest.json", "SHA256SUMS"})]
    manifest = {
        "schemaVersion": "dash-release-manifest/v1",
        "name": "DuneAwakeningSelfHost",
        "tag": tag,
        "version": tag.removeprefix("v"),
        "commit": commit,
        "createdAt": created,
        "immutableReleaseRequired": True,
        "serverPlatform": "linux-x86_64-avx2",
        "funcomArtifactsIncluded": False,
        "assets": assets,
    }
    write_json(directory / "release-manifest.json", manifest)
    checksum_files = files_in(directory, exclude={"SHA256SUMS"})
    (directory / "SHA256SUMS").write_text("".join(f"{digest(path)}  {path.name}\n" for path in checksum_files), encoding="utf-8")
    return {"ok": True, "tag": tag, "commit": commit, "assets": len(checksum_files) + 1, "directory": str(directory)}


def verify_tar_metadata(path: pathlib.Path, tag: str, commit: str) -> None:
    expected_root = f"dash-{tag}-linux-x86_64"
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        roots = {pathlib.PurePosixPath(member.name).parts[0] for member in members if pathlib.PurePosixPath(member.name).parts}
        if roots != {expected_root}:
            raise ValueError(f"primary archive has unexpected roots: {sorted(roots)}")
        for member in members:
            pure = pathlib.PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"primary archive contains unsafe member: {member.name}")
            relative = pathlib.PurePosixPath(*pure.parts[1:])
            path = relative.as_posix()
            if relative.parts and (
                relative.parts[0] in {"backups", "captures", "build", "dist"}
                or path == ".env"
                or path.startswith("config/tls/")
                or path.startswith("config/secrets/")
                or (relative.parts[0] == "data" and not path.startswith("data/exchange-price-snapshots/"))
            ):
                raise ValueError(f"primary archive contains private/runtime path: {path}")
        target = archive.getmember(f"{expected_root}/RELEASE-METADATA.json")
        handle = archive.extractfile(target)
        if handle is None:
            raise ValueError("release metadata is unreadable")
        metadata = json.load(io.TextIOWrapper(handle, encoding="utf-8"))
    if metadata.get("schemaVersion") != "dash-release-metadata/v1" or metadata.get("tag") != tag or metadata.get("commit") != commit:
        raise ValueError("primary archive release metadata does not match tag/commit")
    if (metadata.get("contents") or {}).get("funcomArtifactsIncluded") is not False:
        raise ValueError("primary archive metadata does not exclude Funcom artifacts")


def verify(directory: pathlib.Path, tag: str, commit: str) -> dict:
    required = required_names(tag) | GENERATED
    present = {path.name for path in files_in(directory)}
    missing = sorted(required - present)
    if missing:
        raise ValueError("missing finalized release assets: " + ", ".join(missing))
    checksums = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if not match or match.group(2) == "SHA256SUMS":
            raise ValueError("SHA256SUMS contains an invalid row")
        checksums[match.group(2)] = match.group(1)
    expected_checksum_names = present - {"SHA256SUMS"}
    if set(checksums) != expected_checksum_names:
        raise ValueError("SHA256SUMS coverage does not match release assets")
    for name, expected in checksums.items():
        if digest(directory / name) != expected:
            raise ValueError(f"release asset checksum mismatch: {name}")
    manifest = json.loads((directory / "release-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != "dash-release-manifest/v1" or manifest.get("tag") != tag or manifest.get("commit") != commit:
        raise ValueError("release manifest identity mismatch")
    rows = {row.get("name"): row for row in manifest.get("assets", [])}
    if set(rows) != present - {"release-manifest.json", "SHA256SUMS"}:
        raise ValueError("release manifest coverage does not match release assets")
    for name, row in rows.items():
        if name not in present or row.get("sha256") != digest(directory / name) or row.get("bytes") != (directory / name).stat().st_size:
            raise ValueError(f"release manifest asset mismatch: {name}")
    provenance = json.loads((directory / "release-provenance.intoto.json").read_text(encoding="utf-8"))
    if provenance.get("_type") != "https://in-toto.io/Statement/v1" or provenance.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise ValueError("release provenance schema mismatch")
    for subject in provenance.get("subject", []):
        name = subject.get("name")
        if name not in present or (subject.get("digest") or {}).get("sha256") != digest(directory / name):
            raise ValueError(f"release provenance subject mismatch: {name}")
    sbom = json.loads((directory / f"dash-{tag}-linux-x86_64.spdx.json").read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != "SPDX-2.3" or not sbom.get("files") or (sbom.get("packages") or [{}])[0].get("versionInfo") != tag.removeprefix("v"):
        raise ValueError("SPDX SBOM identity or file inventory is invalid")
    for archive in directory.glob("*.tar.gz"):
        sidecar = pathlib.Path(str(archive) + ".sha256")
        row = sidecar.read_text(encoding="utf-8").strip()
        if row != f"{digest(archive)}  {archive.name}":
            raise ValueError(f"archive sidecar mismatch: {archive.name}")
    verify_tar_metadata(directory / f"dash-{tag}-linux-x86_64.tar.gz", tag, commit)
    return {"ok": True, "tag": tag, "commit": commit, "assets": len(present), "directory": str(directory)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("finalize", "verify"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--asset-dir", required=True, type=pathlib.Path)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        result = finalize(args.root.resolve(), args.asset_dir.resolve(), args.version, args.ref) if args.action == "finalize" else verify(args.asset_dir.resolve(), args.version, args.ref)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
