#!/usr/bin/env python3
"""Build a versioned CVar catalogue from an operator-owned Dune server ELF.

The registration-call extractor is adapted from Sponge/Dune-Awakening-Server-
Tools at revision 04689ba704a3f6dd2d19db89a8df3b6d6a2424b2 (MIT). DASH's
wrapper, schema, provenance, validation, relevance labels, and output are local.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import struct
import subprocess
import sys

WIDE = re.compile(rb"(?:[\x20-\x7e]\x00){2,}")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
LEA = re.compile(r"\blea\b\s+\S+\(%rip\),%(\w+)\s+#\s*([0-9a-f]+)")
MOVI = re.compile(r"\bmov\b\s+\$0x([0-9a-f]+),%(\w+)")
XORR = re.compile(r"\bxor\b\s+%(\w+),%(\w+)")
MOVSS = re.compile(r"\bmovss\b\s+\S+\(%rip\),%xmm0\s+#\s*([0-9a-f]+)")
CALL = re.compile(r"\bcall\b\s+(?:([0-9a-f]+)\b|\*)")
ARG = {reg: slot for slot, regs in {
    "a1": "rdi edi", "a2": "rsi esi", "a3": "rdx edx",
    "a4": "rcx ecx", "a5": "r8 r8d", "a6": "r9 r9d",
}.items() for reg in regs.split()}
SERVER_NAMESPACES = set("""dw Dune dune Vehicle Sandworm Sandstorm SandStorm Hazard
SecurityZones Loot LootTier Combat Coriolis Building Spice SpiceHarvesting
Harvesting Map NPC Npc Ai AI AbilitySystem Abilities Ability Inventory Hydration
Persistence Database Login Travel IgwTravel igw IGW Bgd SelfHosted Weather Farm
Sietch Deterioration Contracts Weapon Movement Pawn Player DuneRepGraph Encounter
World Server fls""".split())
SERVER_WORDS = re.compile(r"\b(server|players?|world|landclaim|pvp|partition|on the server)\b", re.I)


def sections(path):
    data = path.read_bytes()
    if data[:5] != b"\x7fELF\x02":
        raise ValueError("input must be a 64-bit ELF")
    shoff = struct.unpack_from("<Q", data, 0x28)[0]
    entsz, count, strings_index = struct.unpack_from("<HHH", data, 0x3A)
    raw = []
    for index in range(count):
        offset = shoff + index * entsz
        name, _kind, _flags, address, file_offset, size = struct.unpack_from("<IIQQQQ", data, offset)
        raw.append((name, address, file_offset, size))
    strings_offset = raw[strings_index][2]
    result = {}
    for name_offset, address, file_offset, size in raw:
        end = data.index(b"\0", strings_offset + name_offset)
        name = data[strings_offset + name_offset:end].decode("latin1")
        result[name] = (address, data[file_offset:file_offset + size])
    return result


def infer_type_default(help_text, default):
    match = (re.search(r"\[Default\s+([-\d.]+)\]", help_text, re.I)
             or re.search(r"default\s*[=:]\s*([-\d.]+)", help_text, re.I)
             or re.search(r"\(default\s*[=:]?\s*([-\d.]+)\)", help_text, re.I))
    value = match.group(1) if match else default
    lower = help_text.lower()
    kind = "unknown"
    if re.search(r"\b(enable|disable|toggle|whether|if true|if false)\b", lower):
        kind = "bool"
    if re.search(r"multiplier|fraction|seconds|rate|distance|radius|percent|time|scale|threshold|duration", lower):
        kind = "float"
    if kind == "unknown" and re.fullmatch(r"true|false", value or "", re.I): kind = "bool"
    if kind == "unknown" and re.fullmatch(r"-?\d+", value or ""): kind = "int"
    if kind == "unknown" and re.fullmatch(r"-?\d+\.\d+", value or ""): kind = "float"
    return kind, value


def flag_names(value):
    if value is None: return []
    result = []
    if value & 0x1: result.append("CHEAT")
    if value & 0x4: result.append("READONLY")
    if value & 0x40: result.append("SCALABILITY")
    if value & 0x80: result.append("SCALABILITY_GROUP")
    return result


def extract(binary):
    mapped = sections(binary)
    strings = {}
    for section in (".rodata", ".data.rel.ro", ".rodata.str1.1", ".data"):
        if section not in mapped: continue
        address, blob = mapped[section]
        for match in WIDE.finditer(blob):
            strings[address + match.start()] = match.group()[::2].decode("latin1")
    ro_address, ro_blob = mapped.get(".rodata", (0, b""))

    def read_float(address):
        offset = address - ro_address
        return struct.unpack_from("<f", ro_blob, offset)[0] if 0 <= offset <= len(ro_blob) - 4 else None

    disassembly = subprocess.Popen(
        ["objdump", "-d", "--no-show-raw-insn", str(binary)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    pointer_args, immediate_args, last_help, float_default = {}, {}, "", None
    candidates = {}
    assert disassembly.stdout is not None
    for line in disassembly.stdout:
        match = LEA.search(line)
        if match:
            register, address = match.group(1), int(match.group(2), 16)
            text = strings.get(address, "")
            if (" " in text or len(text) >= 20) and len(text) <= 600 and not NAME.fullmatch(text):
                last_help = text
            if register in ARG: pointer_args[ARG[register]] = address
        match = MOVI.search(line)
        if match and match.group(2) in ARG:
            immediate_args[ARG[match.group(2)]] = int(match.group(1), 16)
        match = XORR.search(line)
        if match and match.group(1) == match.group(2) and match.group(1) in ARG:
            immediate_args[ARG[match.group(1)]] = 0
        match = MOVSS.search(line)
        if match: float_default = read_float(int(match.group(1), 16))
        if not CALL.search(line): continue
        values = {slot: strings[address] for slot, address in pointer_args.items() if address in strings}
        name, name_slot = None, None
        for slot in ("a1", "a2"):
            if NAME.fullmatch(values.get(slot, "")) and len(values[slot]) <= 120:
                name, name_slot = values[slot], slot
                break
        if name:
            help_slot, default_slot, flags_slot = (("a3", "a2", "a4") if name_slot == "a1" else ("a4", "a3", "a5"))
            help_text = values.get(help_slot, "")
            if not help_text or NAME.fullmatch(help_text): help_text = last_help
            flags = immediate_args.get(flags_slot)
            default = ""
            if float_default is not None: default = f"{float_default:g}"
            elif default_slot in immediate_args: default = str(immediate_args[default_slot])
            if help_text or flags is not None or default:
                score = int(bool(help_text)) + int(flags is not None) + int(bool(default))
                previous = candidates.get(name)
                if not previous or score > previous[0]: candidates[name] = (score, help_text, default, flags)
        pointer_args, immediate_args, last_help, float_default = {}, {}, "", None
    _stdout, stderr = disassembly.communicate()
    if disassembly.returncode:
        raise RuntimeError(f"objdump failed: {stderr[-1000:]}")
    entries = []
    for name, (_score, help_text, default, flags) in sorted(candidates.items()):
        kind, parsed_default = infer_type_default(help_text, default)
        namespace = name.split(".", 1)[0]
        relevant = namespace in SERVER_NAMESPACES or bool(SERVER_WORDS.search(help_text))
        entries.append({"name": name, "namespace": namespace, "type": kind,
                        "default": parsed_default, "flags": flag_names(flags),
                        "help": help_text, "serverRelevant": relevant})
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=pathlib.Path)
    parser.add_argument("--build-tag", required=True)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("config/cvar-catalog.json"))
    args = parser.parse_args()
    if not args.binary.is_file(): parser.error("binary does not exist")
    entries = extract(args.binary)
    if len(entries) < 100:
        raise SystemExit(f"refusing implausibly small catalogue: {len(entries)}")
    with args.binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    payload = {"schemaVersion": 1, "buildTag": args.build_tag,
               "binarySha256": digest,
               "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "method": "static-console-registration-call-analysis",
               "entryCount": len(entries),
               "serverRelevantCount": sum(item["serverRelevant"] for item in entries),
               "entries": entries}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({key: payload[key] for key in ("buildTag", "binarySha256", "entryCount", "serverRelevantCount")}, indent=2))


if __name__ == "__main__": main()
