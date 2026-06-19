# Windows Client Loader Xrefs - 2026-06-16

Host: `kspld0`

Inputs:

```text
~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe
/tmp/dune-win-client-probe-loader.log
```

Tool:

```bash
scripts/summarize-client-loader-xrefs.py
```

The tool maps runtime loader `rva` hits into PE file offsets, scans executable
sections for simple x86-64 RIP-relative/call/jump references, and treats the
start of the containing ASCII string as an additional target for substring
hits. With `--show-seeds`, it also emits wildcarded byte windows around xrefs
for later signature validation. It does not patch or inject anything.
Confidence: high.

## BRT / Cheat / Deep Desert Run

Command:

```bash
scripts/summarize-client-loader-xrefs.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --category deep-desert \
  --show-context \
  --show-seeds
```

Summary:

```text
Format: pe64
Image base: 0x140000000
Sections: 9
Targets: 56
Targets with xrefs: 21
Xrefs: 93
```

Seed handling: the relative displacement inside each xref instruction is
wildcarded. Example shape:

```text
48 8d 15 ?? ?? ?? ??
```

Treat these as signature seeds only. A seed becomes durable only after it is
unique enough, survives at least one Funcom build, and still resolves to the
same neighborhood in runtime scan mode. Confidence: high.

## Signature Seed Validation

Command:

```bash
scripts/validate-client-pe-signatures.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --category deep-desert
```

Result:

```text
Patterns: 93
Promotable: 93
unique-expected: 93
brt: 53
cheat: 40
```

Every generated BRT/cheat seed matched exactly once in executable PE sections
and landed at the expected xref neighborhood. Deep Desert produced no xref
seeds in this pass, so it remains data/reflection context only. Confidence:
high.

## Manifest Export

Commands:

```bash
scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --category deep-desert \
  --format json \
  --output build/windows-client-loader/client-pe-signature-manifest.json

scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --category deep-desert \
  --format env \
  --output build/windows-client-loader/client-pe-signature-env-chunks.env

scripts/export-client-pe-signature-manifest.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category cheat \
  --category brt \
  --category deep-desert \
  --format signatures \
  --output build/windows-client-loader/client-pe-signatures.txt
```

Generated build artifacts:

```text
build/windows-client-loader/client-pe-signature-manifest.json
build/windows-client-loader/client-pe-signature-env-chunks.env
build/windows-client-loader/client-pe-signatures.txt
```

Manifest facts:

```text
Binary SHA256: bb8e07d4c5e2e1aa393d1f46796aaf42677045c0f0cef894956cc93c48e6093c
Entries: 93
Runtime chunks: 8
Chunk pattern counts: 13, 13, 13, 13, 12, 12, 12, 5
Chunk value sizes: 1782, 1754, 1754, 1786, 1667, 1667, 1678, 699
```

For a full one-launch signature canary, point
`DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE` at
`client-pe-signatures.txt`. The chunked env file remains useful if a signature
file path is inconvenient: set exactly one generated
`DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES` chunk per client launch. Do not
concatenate the chunks; the sidecar config value cap is lower than the full
manifest. Confidence: high.

The exported manifest can now be reused as a future-build gate:

```bash
scripts/validate-client-pe-signatures.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --manifest-json build/windows-client-loader/client-pe-signature-manifest.json \
  --ignore-expected-offsets \
  --format json \
  > build/windows-client-loader/client-pe-signature-revalidation.json
```

For same-build proof, omit `--ignore-expected-offsets` and require
`unique-expected`. For a later Funcom build, use `--ignore-expected-offsets` so
unique moved signatures remain usable canary anchors while `missing` and
`ambiguous` signatures are blocked. Confidence: high.

High-signal BRT candidates:

| Surface | Target RVA | File offset | Xrefs | First xref RVA | First xref file |
| --- | ---: | ---: | ---: | ---: | ---: |
| `PerformCanBePlaced_CheckCollisions` | `0x90ef100` | `0x90ee100` | 25 | `0x3531d97` | `0x3531397` |
| `PerformCanBePlaced` | `0x90eef80` | `0x90edf80` | 7 | `0x352fa71` | `0x352f071` |
| `PerformCanBePlaced_IsBuildingNearBorders` | `0x90ef068` | `0x90ee068` | 5 | `0x3539bde` | `0x35391de` |
| `PerformCanBePlaced_IsLoading` | `0x90ef020` | `0x90ee020` | 4 | `0x353c51d` | `0x353bb1d` |
| `PerformCanBePlaced_HasPermissions` | `0x90ef040` | `0x90ee040` | 4 | `0x35383e9` | `0x35379e9` |
| `PerformCanBePlaced_IsInHeightLimit` | `0x90ef098` | `0x90ee098` | 4 | `0x353b3ad` | `0x353a9ad` |
| `BaseBackupActionPlace.cpp` | `0x90dc6b0` | `0x90db6b0` | 4 | `0x34e3cdb` | `0x34e32db` |

No simple code xref was found for `ServerRequestBaseBackup`,
`m_BaseBackupToolMapRestriction`, or `Fail_InvalidMap`. Treat those as
reflection/data strings until a wider data-reference pass proves otherwise.
Confidence: moderate.

High-signal cheat candidates:

| Surface | Target RVA | File offset | Xrefs | First xref RVA | First xref file |
| --- | ---: | ---: | ---: | ---: | ---: |
| `UDuneCheatManager::SpiceFieldPrimeNearestField` | `0x91e6f78` | `0x91e5f78` | 8 | `0x386930f` | `0x386890f` |
| `UDuneCheatManager::SpiceFieldTeleportToNearestField` | `0x91e6ee0` | `0x91e5ee0` | 6 | `0x386c13e` | `0x386b73e` |
| `UDuneCheatManager::GlobalDistributionPrintTagsForCurrentLocation` | `0x91e1380` | `0x91e0380` | 4 | `0x3834c65` | `0x3834265` |
| `UDuneCheatManager::GlobalDistributionPrintLootSettingsForCurrentLocation` | `0x91e14f0` | `0x91e04f0` | 4 | `0x383489b` | `0x3833e9b` |
| `UDuneCheatManager::AddWeaponToInventory` | `0x91e4e88` | `0x91e3e88` | 2 | `0x3813e76` | `0x3813476` |
| `UDuneCheatManager::AddItemToInventory` | `0x91e4f38` | `0x91e3f38` | 2 | `0x3812348` | `0x3811948` |
| `UDuneCheatManager::AddItemToVehicleInventory` | `0x91e5768` | `0x91e4768` | 2 | `0x3812783` | `0x3811d83` |
| reflected `CheatManager` name | `0x872dfc8` | `0x872cfc8` | 1 | `0x920d86` | `0x920386` |

No simple code xref was found for most `AdminLogin`, `EnableCheats`,
`ServerCheat`, `ClientMessage`, or `CheatClass` string hits. Those are still
useful as reflection surfaces, but they are weaker hook-entry candidates from
this pass. Confidence: moderate.

Deep Desert hits resolved mostly to reflected property names and settings
strings, with no simple executable xrefs in this pass. Current high-value data
surfaces remain:

- `m_DeepDesertGameplay`
- `m_PerMapSystemSettings`
- `m_ShiftingSands`
- `m_SpiceFieldTypeSettings`

## UE/Core Run

Command:

```bash
scripts/summarize-client-loader-xrefs.py \
  ~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe \
  --loader-log /tmp/dune-win-client-probe-loader.log \
  --category ue \
  --name GName \
  --name UObject \
  --name UClass \
  --name FProperty \
  --show-context
```

Summary:

```text
Targets: 50
Targets with xrefs: 6
Xrefs: 37
```

Useful but not sufficient:

- `UClassRegisterAllCompiledInClasses`: target `0x9a1a368`, file
  `0x9a19368`, 2 xrefs, first xref `0x516422a`.
- `CoreUObject/Public/UObject/UnrealType.h`: string start `0x862a390`, 16
  xrefs, first xref `0x11ddb8b`.
- `FglUObjectUtilities.cpp`: string start `0x98f5290`, 1 xref at
  `0x4b5948c`.
- `UnrealNames.cpp`: visible as a string surface at `0x99ac6c0`, but no simple
  executable xref from this pass.

Bad news: this still does not locate `FNamePool`, `GUObjectArray`,
`GObjectArray`, `GWorld`, `ProcessEvent`, or `StaticFindObject`. The client is
not ready for object discovery or hooks from string anchors alone. Confidence:
high.

## Next Discovery Work

1. Disassemble the BRT and cheat xref neighborhoods above and generate durable
   byte signatures for the referenced functions.
2. Add a Windows PE signature scan preset for those function-neighborhood
   bytes, then confirm the signatures survive the next Funcom build before any
   hook work.
3. Add a PE global-candidate pass around UE/Core xrefs to search for
   RIP-relative loads/stores of nearby globals, especially names, object array,
   world, and dispatch-adjacent references.
4. Only after names/object/world candidates are validated at runtime, add
   read-only Unreal object discovery. Hook dispatch and Lua loading stay behind
   that gate.
