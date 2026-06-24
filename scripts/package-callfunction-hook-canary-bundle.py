#!/usr/bin/env python3
import argparse
import json
import tarfile
from pathlib import Path


SCHEMA_VERSION = "dune-callfunction-hook-canary-bundle/v1"
DEFAULT_REMOTE = "kspls0"
DEFAULT_REMOTE_ROOT = "/tmp/dune-callfunction-hook-canary"
DEFAULT_REMOTE_REPO = "/home/keith/Documents/code/DuneAwakeningSelfHost"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def add_file(tar, path, arcname):
    tar.add(path, arcname=arcname, recursive=False)


def command_list(remote, tarball, remote_root, remote_repo, repo_root):
    tar_name = Path(tarball).name
    remote_tar = f"{remote_root}/{tar_name}"
    remote_stage = f"{remote_root}/stage"
    remote_canary_script = f"{remote_repo}/scripts/canary-linux-server-loader.sh"
    remote_env = f"{remote_repo}/.env"
    return {
        "copyBundle": f"ssh {remote} 'mkdir -p {remote_root}' && scp {tarball} {remote}:{remote_tar}",
        "unpackBundle": f"ssh {remote} 'rm -rf {remote_stage} && mkdir -p {remote_stage} && tar -xzf {remote_tar} -C {remote_stage}'",
        "preflightFirst": (
            f"ssh {remote} 'cd {remote_stage} && hostname && "
            "python3 scripts/run-callfunction-hook-candidate-canaries.py "
            "build/server-current-anchor-prep/callfunction-hook-validation-candidates.json "
            f"--canary-script {remote_canary_script} --env-file {remote_env} "
            "--limit 1 --execute --preflight-only --format markdown'"
        ),
        "runFullSequence": (
            f"ssh {remote} 'cd {remote_stage} && hostname && "
            "python3 scripts/run-callfunction-hook-candidate-canaries.py "
            "build/server-current-anchor-prep/callfunction-hook-validation-candidates.json "
            f"--canary-script {remote_canary_script} --env-file {remote_env} "
            "--limit 16 --execute --full-canary --format json "
            "> build/server-current-anchor-prep/callfunction-hook-canary-result.json'"
        ),
        "copyBackResults": (
            f"mkdir -p {repo_root}/build/server-current-anchor-prep/callfunction-hook-canary-results && "
            f"scp {remote}:{remote_stage}/build/server-current-anchor-prep/callfunction-hook-canary-result.json "
            f"{repo_root}/build/server-current-anchor-prep/callfunction-hook-canary-results/ && "
            "python3 scripts/run-callfunction-hook-candidate-canaries.py "
            "build/server-current-anchor-prep/callfunction-hook-validation-candidates.json "
            "--log-dir build/server-current-anchor-prep/callfunction-hook-canary-results --format markdown "
            "> build/server-current-anchor-prep/callfunction-hook-canary-observed.md"
        ),
    }


def build_manifest(args, included_files):
    plan = load_json(args.plan_json)
    commands = command_list(args.remote, args.tarball, args.remote_root, args.remote_repo, Path.cwd())
    return {
        "schemaVersion": SCHEMA_VERSION,
        "remote": args.remote,
        "remoteRoot": args.remote_root,
        "remoteRepo": args.remote_repo,
        "tarball": str(args.tarball),
        "planJson": str(args.plan_json),
        "candidateCount": plan.get("candidateCount", 0),
        "nativeCallAllowed": False,
        "includedFiles": [str(path) for path in included_files],
        "commands": commands,
        "safety": [
            "bundle does not execute remotely by itself",
            "bundle unpacks into a scratch directory and does not overlay the remote repo",
            "candidate runner points at the existing remote repo canary wrapper and .env",
            "canary wrapper verifies hostname through DUNE_LINUX_SERVER_CANARY_HOST default kspls0",
            "full sequence still requires explicit --execute --full-canary on kspls0",
            "native CallFunction active validation remains disabled in candidate env files",
        ],
    }


def package(args):
    candidate_dir = args.candidate_dir
    files = [
        Path("scripts/canary-linux-server-loader.sh"),
        Path("scripts/run-callfunction-hook-candidate-canaries.py"),
        Path("scripts/export-callfunction-hook-validation-candidates.py"),
        args.validation_json,
        args.validation_md,
        args.plan_json,
        args.plan_md,
    ]
    files.extend(sorted(candidate_dir.glob("*.env")))
    args.tarball.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.tarball, "w:gz") as tar:
        for path in files:
            add_file(tar, path, path)
    manifest = build_manifest(args, files)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def markdown(manifest):
    lines = [
        "# CallFunction Hook Canary Bundle",
        "",
        f"- Schema: `{manifest['schemaVersion']}`",
        f"- Remote: `{manifest['remote']}`",
        f"- Remote root: `{manifest['remoteRoot']}`",
        f"- Remote repo: `{manifest['remoteRepo']}`",
        f"- Tarball: `{manifest['tarball']}`",
        f"- Candidates: `{manifest['candidateCount']}`",
        f"- Native call allowed: `{str(manifest['nativeCallAllowed']).lower()}`",
        "",
        "## Safety",
        "",
    ]
    for item in manifest["safety"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Commands", ""])
    for name, command in manifest["commands"].items():
        lines.append(f"- `{name}`: `{command}`")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Package CallFunction hook candidate canary files for explicit kspls0 execution.")
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--candidate-dir", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-candidates"))
    parser.add_argument("--validation-json", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-validation-candidates.json"))
    parser.add_argument("--validation-md", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-validation-candidates.md"))
    parser.add_argument("--plan-json", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-plan.json"))
    parser.add_argument("--plan-md", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-plan.md"))
    parser.add_argument("--tarball", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-bundle.tar.gz"))
    parser.add_argument("--manifest", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-bundle.json"))
    parser.add_argument("--markdown", type=Path, default=Path("build/server-current-anchor-prep/callfunction-hook-canary-bundle.md"))
    args = parser.parse_args()

    manifest = package(args)
    args.markdown.write_text(markdown(manifest), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
