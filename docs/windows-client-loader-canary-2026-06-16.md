# Windows Client Loader Canary - 2026-06-16

Host: `kspld0`

Target:

```text
~/.steam/steam/steamapps/common/DuneAwakening/DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe
```

## Result

The Windows/Proton client loader loaded in the real Dune client process and
completed a read-only full preset scan.

Evidence:

```text
/tmp/dune-win-client-probe-loader.log
```

Key log facts:

```text
event=loaded ... exe=...\DuneSandbox-Win64-Shipping.exe dll=...\Binaries\Win64\VERSION.dll config=...\dune-win-client-probe.env
event=scan-start strings=45 signatures=0 filters=0 maxHits=16 maxRegionBytes=268435456
event=scan-finish
```

The full scan worked only after setting the app-specific Wine DLL override:

```text
HKCU\Software\Wine\AppDefaults\DuneSandbox-Win64-Shipping.exe\DllOverrides
version=native,builtin
```

Without that override, the real Steam launch used Proton's builtin
`version.dll` from:

```text
/usr/share/steam/compatibilitytools.d/proton-ge-custom/files/lib/wine/x86_64-windows/version.dll
```

## Anchor Summary

Present:

- `GName`: 1 hit
- `UObject`: 32 hits
- `UClass`: 2 hits
- `FProperty`: 16 hits
- `CheatManager`: 19 hits
- `CheatClass`: 1 hit
- `EnableCheats`: 1 hit
- `AdminLogin`: 9 hits
- `ServerRequestBaseBackup`: 1 hit
- `BaseBackupActionPlace`: 1 hit
- `PerformCanBePlaced`: 6 hits
- `Fail_InvalidMap`: 1 hit
- `DeepDesert`: 4 hits
- `m_DeepDesertGameplay`: 1 hit
- `m_PerMapSystemSettings`: 2 hits
- `m_ShiftingSands`: 1 hit
- `m_SpiceFieldTypeSettings`: 2 hits

Missing from string scan:

- `FNamePool`
- `GUObjectArray`
- `GObjectArray`
- `GWorld`
- `ProcessEvent`
- `StaticFindObject`
- `UFunction`
- `DeepDesert_1`

Readiness:

```text
readyForObjectDiscovery=false
readyForHooks=false
```

## Static Xref Follow-Up

Follow-up static PE xref analysis is documented in
`docs/windows-client-loader-xrefs-2026-06-16.md`.

Key result:

```text
BRT/cheat/deep-desert targets: 56
Targets with xrefs: 21
Xrefs: 93
UE/core targets: 50
UE/core targets with xrefs: 6
UE/core xrefs: 37
```

High-signal candidates now include `PerformCanBePlaced*`,
`BaseBackupActionPlace.cpp`, and several `UDuneCheatManager::*` function string
neighborhoods. Follow-up signature validation found `93/93` BRT/cheat xref
seed windows were `unique-expected` in executable PE sections. Deep Desert had
no xref seeds in this pass. The validated signatures export to a 93-entry JSON
manifest, a one-launch signature file, and 8 fallback runtime env chunks. The
missing UE4SS-port anchors remain unresolved.

## Next Work

The next Windows/Proton client step is signature discovery for:

- object array: `GUObjectArray` or `GObjectArray`;
- world: `GWorld`;
- dispatch: `ProcessEvent` or `StaticFindObject`;
- names: convert the current `GName` string surface into an addressable names
  layout candidate, or find `FNamePool` by signature.
