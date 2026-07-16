#!/usr/bin/env python3
"""Generate a host-local Compose cpuset overlay from Linux CPU/cache topology."""

import argparse
import os
import pathlib
import re
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]


def parse_cpu_list(value):
    result = set()
    for part in str(value or "").strip().split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = (int(item) for item in part.split("-", 1))
            result.update(range(start, end + 1))
        else:
            result.add(int(part))
    return result


def format_cpu_list(cpus):
    return ",".join(str(cpu) for cpu in sorted(cpus))


def read_text(path, default=""):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return default


def size_kib(value):
    match = re.fullmatch(r"(\d+)([KMG])?", value.strip().upper())
    if not match:
        return 0
    amount = int(match.group(1))
    return amount * {None: 1, "K": 1, "M": 1024, "G": 1024 * 1024}[match.group(2)]


def discover_topology(sysfs_root):
    root = pathlib.Path(sysfs_root)
    online = []
    cores = {}
    cache_domains = {}
    for cpu_dir in sorted(root.glob("cpu[0-9]*"), key=lambda path: int(path.name[3:])):
        cpu = int(cpu_dir.name[3:])
        if read_text(cpu_dir / "online", "1") != "1":
            continue
        online.append(cpu)
        package = read_text(cpu_dir / "topology/physical_package_id", "0")
        core = read_text(cpu_dir / "topology/core_id", str(cpu))
        cores.setdefault((package, core), set()).add(cpu)
        shared = parse_cpu_list(read_text(cpu_dir / "cache/index3/shared_cpu_list"))
        if shared:
            domain = tuple(sorted(shared))
            cache_domains[domain] = max(
                cache_domains.get(domain, 0),
                size_kib(read_text(cpu_dir / "cache/index3/size")),
            )
    if not online:
        raise RuntimeError(f"no online CPUs discovered under {root}")
    return set(online), list(cores.values()), cache_domains


def choose_pools(online, cores, cache_domains):
    notes = []
    domains = [(set(domain) & online, size) for domain, size in cache_domains.items()]
    domains = [(cpus, size) for cpus, size in domains if cpus]
    unique_domains = {tuple(sorted(cpus)): size for cpus, size in domains}
    if len(unique_domains) >= 2:
        ranked = sorted(unique_domains.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
        if ranked[0][1] >= max(1, ranked[1][1]) * 3 // 2:
            foreground = set(ranked[0][0])
            background = online - foreground
            notes.append(
                f"foreground uses asymmetric largest shared L3 domain ({ranked[0][1]} KiB); "
                f"background uses remaining CPUs"
            )
        else:
            ordered = sorted(unique_domains)
            background_domain_count = max(1, len(ordered) // 3)
            background = {cpu for domain in ordered[:background_domain_count] for cpu in domain}
            foreground = online - background
            notes.append(
                f"symmetric multi-L3 topology; reserved {background_domain_count}/{len(ordered)} "
                f"complete cache domains for background"
            )
        if background:
            return foreground, background, notes

    ordered_cores = sorted((sorted(group) for group in cores), key=lambda group: group[0])
    if len(ordered_cores) == 1:
        return online, online, ["single physical core; foreground and background share all CPUs"]
    background_core_count = max(1, len(ordered_cores) // 3)
    background = {cpu for group in ordered_cores[:background_core_count] for cpu in group}
    foreground = online - background
    notes.append(
        f"single L3 topology; reserved {background_core_count}/{len(ordered_cores)} physical cores for background"
    )
    return foreground or online, background or online, notes


def read_env_file(path):
    values = {}
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def compose_services(env_file, services_file=None):
    if services_file:
        return [line.strip() for line in pathlib.Path(services_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    resolved = subprocess.run(
        [str(ROOT / "scripts/compose-files.sh"), str(env_file)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    command = [os.environ.get("CONTAINER_RUNTIME", "docker"), "compose", "--env-file", str(env_file)]
    for compose_file in resolved.split(":"):
        command.extend(["-f", compose_file])
    command.extend(["config", "--services"])
    output = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, check=True).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--output", default=str(ROOT / "compose.cpu-affinity.yaml"))
    parser.add_argument("--sysfs-root", default="/sys/devices/system/cpu")
    parser.add_argument("--services-from")
    parser.add_argument("--foreground-cpuset")
    parser.add_argument("--background-cpuset")
    parser.add_argument("--foreground-services")
    args = parser.parse_args()

    env = read_env_file(args.env_file)
    online, cores, cache_domains = discover_topology(args.sysfs_root)
    foreground, background, notes = choose_pools(online, cores, cache_domains)
    foreground_override = args.foreground_cpuset or env.get("DUNE_CPU_AFFINITY_FOREGROUND_CPUSET", "")
    background_override = args.background_cpuset or env.get("DUNE_CPU_AFFINITY_BACKGROUND_CPUSET", "")
    if foreground_override:
        foreground = parse_cpu_list(foreground_override)
        notes.append("foreground CPU set supplied by operator override")
    if background_override:
        background = parse_cpu_list(background_override)
        notes.append("background CPU set supplied by operator override")
    if not foreground or not background:
        raise SystemExit("foreground and background CPU sets must both be non-empty")
    if not foreground.issubset(online) or not background.issubset(online):
        raise SystemExit(f"CPU-set override includes an offline/unknown CPU; online={format_cpu_list(online)}")

    default_foreground = "survival,overmap,deep-desert,deep-desert-pvp"
    foreground_names = {
        item.strip()
        for item in (args.foreground_services or env.get("DUNE_CPU_AFFINITY_FOREGROUND_SERVICES", default_foreground)).split(",")
        if item.strip()
    }
    services = sorted(set(compose_services(args.env_file, args.services_from)))
    if not services:
        raise SystemExit("no Compose services discovered")

    lines = [
        "# Generated by scripts/generate-cpu-affinity.py; host-specific; do not commit.",
        f"# Online CPUs: {format_cpu_list(online)}",
        f"# Foreground CPUs: {format_cpu_list(foreground)}",
        f"# Background CPUs: {format_cpu_list(background)}",
    ]
    lines.extend(f"# Detection: {note}" for note in notes)
    lines.append("services:")
    for service in services:
        cpus = foreground if service in foreground_names else background
        lines.extend([f"  {service}:", f'    cpuset: "{format_cpu_list(cpus)}"'])
    lines.append("")

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
        handle.write("\n".join(lines))
        temporary = pathlib.Path(handle.name)
    temporary.replace(output)
    print(f"Wrote {output}")
    print(f"foreground={format_cpu_list(foreground)} services={','.join(sorted(foreground_names))}")
    print(f"background={format_cpu_list(background)}")


if __name__ == "__main__":
    main()
