# Subfief / Totem Cap Research

Status: **No clean lever exists in shipped content. Binary patching is required.** The exact byte location is not yet identified; this doc captures what we've narrowed and how to continue.

## What the per-player cap actually is

The "3 / 3" notice players see on the 4th totem placement is enforced server-side as `EBuildingSystemActionResult::Fail_DisallowedBuildLimit`. Funcom ships:

- `DunePlayerCharacterAttributeSet.SubfiefLimitBonus` — a GAS `FGameplayAttributeData` attribute, persisted to `dune.actors.gas_attributes`, replicated to clients via `OnRep_SubfiefLimitBonus`.
- `DunePlayerCharacterAttributeSet.SubfiefCount` — sibling attribute for current count.
- `BP_SetMaxClaimCapacity` / `BP_ClearMaxClaimCapacity` — **unrelated**: they belong to `UClaimSubsystem` (FLS reward-pack queue, see Lukano's `m_QuarantinedPlayerRewards` for evidence) and govern how many pending Funcom Live Services reward packs a character can hold, not landclaims.

## Empirically ruled out

| Approach | Evidence |
|---|---|
| INI knob | No keys in `[/Script/DuneSandbox.DunePlayerCharacter]`, `[/Script/DuneSandbox.DuneCharacter]`, or `[/Script/DuneSandbox.BuildingSettings]` govern the cap. |
| `EServerGameplaySettingType` | Full enum dumped from binary (24 entries: SecurityZones, BaseBackup, BuildingBlueprint, Sandworm/Sandstorm, Vehicle, Hydration, Mining, etc.). No subfief / landclaim entry. |
| GameplayEffect content | Scanned all 12 paks for `DunePlayerCharacterAttributeSet` / `DuneCharacterAttributeSet`. Only hit is `:DungeonScalingDifficulty` (unrelated). **No GE in cooked content modifies `SubfiefLimitBonus`.** The `DA_GRP_AdvSubFief+Choam2` tech-tree node unlocks Choam-tier-2 building set + `DA_BLD_Totem_Patent`; the `+2` is a tier suffix, not a `+2` bonus. |
| Direct DB write of `SubfiefLimitBonus` | Verified live on kspls0: Lukano's pawn (account_id=2, pawn_id=19) has `BaseValue=6, CurrentValue=6` persisted, survives relog. In-game cap still displays/enforces 3 / 3. The placement validator does not consult this attribute. |
| Pak / BP CDO patch | Scanned `pakchunk170` (contains `BP_DunePlayerCharacter.uasset/.uexp`). `MaxClaimCapacity` / `SubfiefLimitBonus` / `SubfiefCount` do not appear as ASCII strings in any pak. Names are interned in the C++ binary's FName pool only, meaning the values are C++ class members with constructor defaults — not BP CDO overrideable. |

## Where the cap check lives

Source-file string xrefs from `.text` to `.rodata` (PIE binary, RIP-relative `lea r, [rip+disp]`):

| Source file (`DuneSandbox/Source/DuneSandbox/...`) | xrefs | Function(s) |
|---|--:|---|
| `BaseManagement/Placeables/Totem/TotemPersistenceComponent.cpp` | 2 | 0xcf2d730 (84 b), 0xe37d9b0 (90 b) — too small to host cap check |
| `BuildingSystem/Actions/BuildingSystemActionPlaceBuildable.cpp` | 3 | 0xcf6fc50 (641 b), **0xcf70210 (4860 b)** |
| `BuildingSystem/CanBePlaced/InsideLandclaimCanBePlaced.cpp` | 3 | 0xd04d020 (1676 b) — *inside-landclaim* check, not cap |
| `BuildingSystem/Actions/BuildingSystemActionSpawnBuildable.cpp` | 5 | 0xcf7ac80 (2487 b) |
| `BaseManagement/Placeables/Totem/DuneTotemCanBePlaced.cpp` | 7 | 0xcedcb40 (4706 b) — likely *location/collision* check, not cap |
| `BaseManagement/Placeables/Totem/DunePlaceableTotem.cpp` | 10 | many small (~80 b) — actor class methods |

The cap check is almost certainly inside **`UBuildingSystemActionPlaceBuildable::OnInstigatorServerBeforeValidation_Internal`** (function at `0xcf70210`, 4860 bytes), or in `UBuildingSystemActionSpawnBuildable` (`0xcf7ac80`, 2487 bytes). Neither contains a direct `cmp r32, 3` immediate compare — the cap-against-count comparison goes through indirect calls (probably GAS attribute getters via `UAbilitySystemComponent::GetNumericAttributeBase(SubfiefLimitBonus/SubfiefCount)`).

The candidate **hot callee `0xf7d8600`** is invoked 34 times in the place-buildable function and 22 times in DuneTotemCanBePlaced — almost certainly a small utility (GAS attribute access or shared logger). Worth disassembling to confirm.

## Next steps for actually finding the patch byte

1. **Ghidra auto-analysis on `DuneSandboxServer-Linux-Shipping`** (~2-4 hours):
   - Load binary, let auto-analysis name functions.
   - Set listing at the FName string `Fail_DisallowedBuildLimit` (file offset `0x5b8d854`).
   - Use Ghidra's "Find References to" → trace back through the UEnum metadata table to find call sites that *write* this enum value to a result struct.
   - In the writing function(s), identify the `cmp` / `ucomiss` / `vucomiss` instruction whose `jcc` branches into the Fail_DisallowedBuildLimit-writing basic block.
   - Document a 16-32 byte signature around the patch byte for the sigscan re-patcher.

2. **Live gdb in handoff lab** (needs lab + a test player — currently off-limits since user can't take primary offline):
   - Spin up `compose.handoff-lab.yaml` on kspld0.
   - Attach gdb to `DuneSandboxServer-Linux-Shipping` inside the container.
   - Set breakpoints at each of the 23 lea xrefs (7 in DuneTotemCanBePlaced + 3 in BuildingSystemActionPlaceBuildable + 5 in spawn + others).
   - Test character places a 4th totem; observe which breakpoint fires.
   - Single-step from there to the comparison.

3. **Patch byte → repo-owned sigscan patcher** (modeled on `scripts/patch-building-piece-limit-pak.py`):
   - Encode the 16-32 byte signature with a wildcard for the patch slot.
   - Search the live binary for the unique signature, patch the byte at signature-relative offset N from `3` → desired cap.
   - Idempotent: re-run on each container start via `scripts/run_server_safe.sh` (matches the existing pattern at `scripts/run_server_safe.sh:203`).
   - Add an env-gated knob `DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED` like the existing pak patches at `compose.yaml:12-14`.

## Re: "will it break every update?"

Signature-based patching of small comparisons typically survives many builds. The risk surface:

- **Stable across patches**: function signature byte pattern (CMP + JCC + register usage). UE5 codegen for simple `if (count >= cap)` checks is essentially identical across compiler versions.
- **Breaks on**: major refactor of the placement validator, switch from C++ class member to a config-driven UPROPERTY, or Funcom shipping the actual `EServerGameplaySettingType` entry (in which case we *want* the patch to fail-safe so we can switch to the new INI knob).

The probe script `scripts/research/probe-subfief-cap-binary.py` provides the search heuristics and can be re-run after each Funcom binary update to verify the candidate functions still exist and the signature is still present.

## radare2 follow-up (added after first commit)

Installed radare2 on kspld0 and re-confirmed the indirection. Key new findings:

- The hot callee at `0xf7d8600` calls `__cxa_guard_acquire` / `__cxa_guard_release` — it's the standard **C++ lazy static-local-variable initializer**, not a useful gateway. Pattern:
  ```c
  static Foo* instance = make_foo();  // guarded init
  return instance->vtable[9](this, arg);  // call qword [rax+0x48]
  ```
  Used 34× in `0xcf70210` and 22× in `0xcedcb40` because it's a generic logger/assert helper, not a cap check.
- The second-most-called callee `0x9591b80` (called 7× in PlaceBuildable) is a small array/string helper (uses `add rdi, rdi`, `shr rax, 1`, `mov esi, 2` — looks like `TArray::Reserve` or string copy).
- Third-most-called `0x1469aa50` is `memcpy` (PLT stub).

Full disassembly of the 4860-byte `0xcf70210` function shows **100+ cmp/test instructions but zero `cmp r, 3` or `cmp r, 6`** — i.e., the cap comparison is genuinely not inlined here. It's deeper in the call chain, likely behind a virtual dispatch.

`SubfiefCount` / `SubfiefLimitBonus` FName strings are referenced only via `.rela.dyn` relocations (1 reloc to `SubfiefCount` at `0x156e7890`, 5 relocs to `SubfiefLimitBonus` clustered at `0x1502bfc0…0x1502fd78`) — these populate descriptor entries in `.data.rel.ro` at load time, not in `.text`. So scanning `.text` for code that "uses" these FNames returns nothing; the property descriptors get looked up via UE5 reflection (UClass / FProperty walks), and the reflection results feed into GAS attribute getters.

Net: even with r2 + capstone, finding the cap byte from static analysis alone requires resolving 1–2 layers of virtual dispatch + reflection. That's exactly Ghidra's strength.

## Artifacts in this repo

Research tooling:
- `scripts/research/probe-subfief-cap-binary.py` — narrows search to candidate functions via source-file xref counting + cmp/float disassembly.
- `scripts/research/ghidra-find-subfief-cap.py` — Ghidra Python script that auto-walks from the `Fail_DisallowedBuildLimit` string xref to the cap comparison.
- `scripts/research/extract-binary-for-ghidra.sh` — packages the binary + scripts + this doc into `/tmp/dune-ghidra/` ready to ship to a workstation.
- `scripts/research/verify-subfief-cap-signature.py` — validates a candidate sigscan signature (uniqueness, expected old byte at patch offset, disasm sanity). Emits paste-ready `SIGNATURE` / `PATCH_OFFSETS`.

Runtime patcher:
- `scripts/patch-subfief-cap-binary.py` — sigscan-based binary patcher with
  Ghidra-derived signatures for `subfief`, `building-server`, and
  `building-map`. Use `--target all` to apply all three bypasses.
- `scripts/run_server_safe.sh` — `install_subfief_cap_binary_patch` hook fires
  on container start after pak patch hooks. It is gated by
  `DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED`.
- `compose.yaml`, `.env.example` — `DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED`
  (default `false`), `DUNE_SUBFIEF_CAP_BINARY_TARGET` (default `subfief` in
  compose, documented as `all` for the full maintenance experiment), and
  `DUNE_SUBFIEF_CAP` (default `6`) env knobs.

Other:
- `docs/subfief-cap-research.md` — this document.
- `scripts/apply-subfief-limit-knob.sh` — DB-side `SubfiefLimitBonus` writer + trigger. Still useful: when Funcom finally exposes the cap via `EServerGameplaySettingType` or wires the GAS attribute through, the persisted values are ready.

## Flow for the current binary patch

1. Dry-run against the target binary:
   `python3 scripts/patch-subfief-cap-binary.py --binary <server-bin> --target all --new-cap 6 --dry-run`.
2. Confirm the dry-run reports exactly three targets: `subfief`,
   `building-server`, and `building-map`.
3. Test in handoff lab: set `DUNE_SUBFIEF_CAP_BINARY_PATCH_ENABLED=true`,
   `DUNE_SUBFIEF_CAP_BINARY_TARGET=all`, bring up, then place a 4th totem with a
   test character and test building beyond the known piece cap.
4. If validated, keep the same env in prod's `.env` for the next maintenance
   restart.

The patch survives Funcom server-binary updates as long as the sigscan signature still finds exactly one match. If it stops finding a match, re-run Ghidra against the new binary and update the signature.
