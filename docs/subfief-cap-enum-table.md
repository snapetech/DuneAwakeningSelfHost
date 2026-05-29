# EBuildingSystemActionResult enum values (extracted)

Reconstructed from the UEnum metadata table at VMA `0x14dbcb00` in
`DuneSandboxServer-Linux-Shipping` (build hash `9bf5fbdef43a6d6d…`,
captured 2026-05-29). The metadata is an array of 16-byte
`(FName_pointer, int64_value)` entries; `FName_pointer` lives in
`.data.rel.ro` and is filled at load time by `R_X86_64_RELATIVE`
relocations targeting the enum-name strings in `.rodata`.

This lets future binary searches hunt for the specific *integer* enum
value (e.g. `0x6b` for `Fail_DisallowedBuildLimit`) rather than the
string, which only appears in reflection metadata.

## Cap-related entries

| Enum entry                                              | Hex   | Dec |
|---------------------------------------------------------|-------|-----|
| `Fail_DisallowedBuildLimit` (per-player subfief cap)     | `0x6b` | 107 |
| `Fail_ReachedBuildableStructureLimitInServer`            | `0x7e` | 126 |
| `Fail_ReachedBuildableStructureLimitInMap`               | `0x7f` | 127 |
| `Fail_ReachedBuildableStructureComposedLimitInServer`    | `0x80` | 128 |
| `Fail_ReachedBuildableStructureComposedLimitInMap`       | `0x81` | 129 |

## Full table (59 entries, sequential)

```
slot VMA 0x14dbcb00  value=0x00 (0)    Empty
slot VMA 0x14dbcb10  value=0x01 (1)    Success
slot VMA 0x14dbcb20  value=0x02 (2)    Success_Update
slot VMA 0x14dbcb30  value=0x64 (100)  Fail
slot VMA 0x14dbcb40  value=0x65 (101)  Fail_Stability
slot VMA 0x14dbcb50  value=0x66 (102)  Fail_Stability_NoData
slot VMA 0x14dbcb60  value=0x67 (103)  Fail_Overlaps
slot VMA 0x14dbcb70  value=0x68 (104)  Fail_LandClaim
slot VMA 0x14dbcb80  value=0x69 (105)  Fail_LoadingBuildingData
slot VMA 0x14dbcb90  value=0x6a (106)  Fail_InsideCollision
slot VMA 0x14dbcba0  value=0x6b (107)  Fail_DisallowedBuildLimit         ← SUBFIEF CAP
slot VMA 0x14dbcbb0  value=0x6c (108)  Fail_NoSocketData
slot VMA 0x14dbcbc0  value=0x6d (109)  Fail_IncorrectSocketType
slot VMA 0x14dbcbd0  value=0x6e (110)  Fail_OverlapPlayer
slot VMA 0x14dbcbe0  value=0x6f (111)  Fail_OverlapQuicksand
slot VMA 0x14dbcbf0  value=0x70 (112)  Fail_OverlapTotem
slot VMA 0x14dbcc00  value=0x71 (113)  Fail_NoTotem
slot VMA 0x14dbcc10  value=0x72 (114)  Fail_NoPermissions
slot VMA 0x14dbcc20  value=0x73 (115)  Fail_NotConnectedToNonHologram
slot VMA 0x14dbcc30  value=0x74 (116)  Fail_MissingMaterials
slot VMA 0x14dbcc40  value=0x75 (117)  Fail_DifferentTotem
slot VMA 0x14dbcc50  value=0x76 (118)  Fail_ItemDamaged
slot VMA 0x14dbcc60  value=0x77 (119)  Fail_NearServerBorder
slot VMA 0x14dbcc70  value=0x78 (120)  Fail_NoAccessToBuildable
slot VMA 0x14dbcc80  value=0x79 (121)  Fail_Datatable
slot VMA 0x14dbcc90  value=0x7a (122)  Fail_NotTheOwner
slot VMA 0x14dbcca0  value=0x7b (123)  Fail_CantMoveOrPickup
slot VMA 0x14dbccb0  value=0x7c (124)  Fail_Landscape
slot VMA 0x14dbccc0  value=0x7d (125)  Fail_FullyInsideTerrain
slot VMA 0x14dbccd0  value=0x7e (126)  Fail_ReachedBuildableStructureLimitInServer   ← PIECE CAP (server)
slot VMA 0x14dbcce0  value=0x7f (127)  Fail_ReachedBuildableStructureLimitInMap      ← PIECE CAP (map)
slot VMA 0x14dbccf0  value=0x80 (128)  Fail_ReachedBuildableStructureComposedLimitInServer
slot VMA 0x14dbcd00  value=0x81 (129)  Fail_ReachedBuildableStructureComposedLimitInMap
slot VMA 0x14dbcd10  value=0x82 (130)  Fail_OverMaxAllowedDistance
slot VMA 0x14dbcd20  value=0x83 (131)  Fail_IncorrectSurfaceOrientation
slot VMA 0x14dbcd30  value=0x84 (132)  Fail_IncompatibleBuildableToReplace
slot VMA 0x14dbcd40  value=0x85 (133)  Fail_BuildingBlueprintTotemNotConnected
slot VMA 0x14dbcd50  value=0x86 (134)  Fail_BuildingBlueprintInvalidPlaceableStability
slot VMA 0x14dbcd60  value=0x87 (135)  Fail_BuildingBlueprintInvalidBuildingPieceConnection
slot VMA 0x14dbcd70  value=0x88 (136)  Fail_InvalidMap
slot VMA 0x14dbcd80  value=0x89 (137)  Fail_NoSwatchToCustomize
slot VMA 0x14dbcd90  value=0x8a (138)  Fail_CantCustomizeBuildings
slot VMA 0x14dbcda0  value=0x8b (139)  Fail_CantFindPieceToCustomize
slot VMA 0x14dbcdb0  value=0x8c (140)  Fail_PlayerReserveInventoryNotEmpty
slot VMA 0x14dbcdc0  value=0x8d (141)  Fail_InvalidDataOrObject
slot VMA 0x14dbcdd0  value=0x8e (142)  Fail_HashMatch
slot VMA 0x14dbcde0  value=0x8f (143)  Fail_NoValidPotentialGhosts
slot VMA 0x14dbcdf0  value=0x90 (144)  Fail_NoBuildableFound
slot VMA 0x14dbce00  value=0x91 (145)  Fail_FullHealth
slot VMA 0x14dbce10  value=0x92 (146)  Fail_NotAffectedByBuildingTool
slot VMA 0x14dbce20  value=0x93 (147)  Fail_NotHologram
slot VMA 0x14dbce30  value=0x94 (148)  Fail_MoveNotPlaceable
slot VMA 0x14dbce40  value=0x95 (149)  Fail_CantBeHologram
slot VMA 0x14dbce50  value=0x96 (150)  Fail_AssetNotPreloaded
slot VMA 0x14dbce60  value=0x97 (151)  Fail_CantLoadOwnedActors
slot VMA 0x14dbce70  value=0x98 (152)  Fail_NotElegibleToPickUp
slot VMA 0x14dbce80  value=0x99 (153)  Fail_NotElegibleToRemove
slot VMA 0x14dbce90  value=0x9a (154)  Fail_DoesntOwnSwatch
slot VMA 0x14dbcea0  value=0x9b (155)  Fail_IncompatibleSwatchWithPlaceable
```

## Caveats found while searching for `0x6b` writes

Naively scanning `.text` for `mov` instructions writing 0x6b returns hundreds
of false positives, in two flavours:

1. **UE5 logger-init stubs** (~31 in `Bgd*` log category init). Pattern:
   ```
   cmp byte [rip+X], 0       ; one-time-init guard
   jne ret
   ... setup ...
   mov esi, 1                ; verbosity = Warning
   mov r8d, 0x6b             ; passing the *enum value* as a logger arg
   call <UE_LOG>
   ```
   The `0x6b` here is passed to the log formatter, not written as the action result.

2. **Coincidental token values in tokenizers/lexers**. Function `0xaeb0e20`
   is a character lexer where `mov dword [rdx], 0x6b` writes a tokeniser tag
   that happens to equal 107.

The real "return `Fail_DisallowedBuildLimit`" sites are obscured behind
either a switch jump table (one `jmp [tbl+idx*8]`-style dispatch per
action class) or a struct-field write whose offset varies per call site.
Resolving them requires symbol/vtable reconstruction (Ghidra) or a live
attach during placement.
