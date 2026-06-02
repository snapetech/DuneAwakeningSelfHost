# Native GM Command Catalog

Confidence: high for the shipped allow-list and recovered method names.
Confidence: moderate for inferred tiers/purposes. Confidence: low for live
execution until the native notification payload contract is proven.

This page is the broad static inventory for native GM and cheat-manager command
surfaces. It separates three different things that should not be mixed:

- Shipped dedicated-server allow-list entries.
- Operational DASH/chat wrappers that are preview-only until payload proof.
- Binary-resident cheat-manager methods recovered from the server binary.

## Current Counts

| Surface | Count | Meaning |
| --- | ---: | --- |
| Operational catalog entries | 28 | Names exposed by `scripts/gm-command-catalog.py` for operator preview/proof planning. |
| Recovered binary cheat-manager methods | 100 | Methods extracted from reflected/demangled cheat-manager strings in the current binary. |
| Binary methods overlapping operational allow-list | 3 | `AddItemToInventory`, `PatrolShipTeleportToNearest`, and `TravelToDimension`. |
| Binary-only unverified methods | 96 | Present in the binary, not shipped as dedicated-server GM allow-list entries. |
| Format-evidence-only methods | 1 | `UOvermapCheatManager::OvermapTravelToDimension`. |

## Commands

Use the script for the current machine-readable source:

```bash
./scripts/gm-command-catalog.py --format json
./scripts/gm-command-catalog.py --format markdown
./scripts/gm-command-catalog.py --format names --include-binary-methods
```

Use the proof runner to include static-only proof rows for all recovered methods:

```bash
./scripts/prove-gm-commands.py --format markdown --include-binary-methods
```

The full Ghidra purpose matrix remains in
[gm-command-ghidra-surface.md](gm-command-ghidra-surface.md). The proof and
transport status is tracked in
[gm-command-proof-ledger.md](gm-command-proof-ledger.md).

## Shipped Dedicated-Server Allow-List

Console commands:

- `obj`
- `FGL.ComponentAuditRequested`

GM commands:

- `AddItemToInventory`
- `AddBasicInventoryToCharacter`
- `SpawnVehicle`
- `PatrolShipTeleportToNearest`
- `TeleportTo`
- `TeleportToMap`
- `TeleportToExact`
- `TeleportToPlayer`
- `TeleportToVehicleSpawner`
- `TeleportToSandworm`
- `TeleportToPersonalMarker`
- `TravelTo`
- `TravelToDimension`
- `Fly`
- `Ghost`
- `Walk`
- `DestroyTargetVehicle`
- `DestroyTotem`
- `DestroyPlaceable`
- `DestroyEntireBuilding`
- `DestroyBuildingPiece`
- `PrintPos`

Status: allow-listed but unverified through the current DASH/RMQ native payload
route. Confidence: high.

## Safe Proof Order

1. `PrintAllowedCommands`: not in the shipped allow-list but useful as a native
   server-command payload probe after the notification wrapper is solved.
2. `PrintPos`: allow-listed and the safest shipped GM command.
3. Admin-only movement on an isolated admin character:
   `Fly`, `Ghost`, `Walk`, `TeleportToExact`, `TeleportToMap`, travel helpers.
4. Isolated target mutation:
   `AddItemToInventory`, `AddBasicInventoryToCharacter`, `SpawnVehicle`,
   `TeleportToPlayer`.
5. Destructive lab-only commands:
   `DestroyTargetVehicle`, `DestroyTotem`, `DestroyPlaceable`,
   `DestroyEntireBuilding`, `DestroyBuildingPiece`.

No mutating or destructive command should run until `Server command received`,
`Handling ServiceBroadcast Server command:`, and `Now running ServerCommand`
are proven with safe commands on an empty route. Confidence: high.

## Full Binary Cheat-Manager Inventory

These 100 methods are binary-resident. They are not automatically callable
dedicated-server GM commands.

### `UCharacterTransferCheatManager`

- `CharacterTransfer_CancelCurrentTransfer`
- `CharacterTransfer_CheckTransferStatus`
- `CharacterTransfer_ExportData`
- `CharacterTransfer_FullFlow`
- `CharacterTransfer_ImportData`
- `CharacterTransfer_PreTransferCheck_InGame`
- `CharacterTransfer_PreTransferCheck_MainMenu`
- `CharacterTransfer_RequestReservation`

### `UClaimSystemCheatManager`

- `ClaimSystemPrintCharacterPacks_Client`
- `ClaimSystemPrintCharacterPacks_Server`
- `ClaimSystemServerConsumeEntirePackForCharacter`
- `ClaimSystemServerConsumeFrom2StacksFromPackForCharacter`
- `ClaimSystemServerConsumeFromPackForCharacter`

### `UDuneCheatManager`

- `AchievementTestPrintAllAchievements`
- `AchievementTestResetAllAchievements`
- `AddItemToInventory`
- `AddItemToVehicleInventory`
- `AddWeaponToInventory`
- `CheatCurrentDungeonCompletion`
- `ClearFlsCharacterData`
- `CompleteCurrentDungeon`
- `ConditionsLogRegisteredConditions`
- `ConditionsLogRegisteredConditionsForCurrentPlayer`
- `ConditionsLogRegisteredConditionsForEvent`
- `ConditionsLogRegisteredConditionsForEventAndCurrentPlayer`
- `ConditionsLogRegisteredConditionsForEventAndPlayerId`
- `ConditionsLogRegisteredConditionsForPlayerId`
- `ConditionsLogRegistrationKeys`
- `ConditionsLogSummary`
- `CoriolisPrintStoredSeeds`
- `CoriolisSetFarmSeed`
- `CoriolisSetMapSeed`
- `CoriolisSetPartitionSeed`
- `DeleteAllCompletionsForAllDungeonsByThisPlayer`
- `DeleteAllCompletionsForCurrentDungeon`
- `DeleteAllCompletionsForCurrentDungeonByThisPlayer`
- `DisplayFlsBattlegroupsServerBrowserInfo`
- `FlushActorPersistence`
- `GlobalDistributionPrintLootSettingsForCurrentLocation`
- `GlobalDistributionPrintTagsForCurrentLocation`
- `InitializeContractsAutoCompleteNamesList`
- `LogInAs`
- `MigrateMyVehicles`
- `OpenUIScene`
- `OverrideDungeonPlayerCount`
- `PatrolShipListSpawned`
- `PatrolShipTeleportToNearest`
- `PayAllTaxesForNearbyTotem`
- `PlayNow`
- `PrintListPlayersInFarm`
- `PrintMapSettings`
- `PrintNpcRespawnTimerHere`
- `PrintPlayerCap`
- `RaiseDatabaseException`
- `RequestFakeGroupTravel`
- `ResetCurrentDungeon`
- `ResetCurrentDungeonRoom`
- `ResetVendorStockData`
- `ReturnToHomeDimension`
- `SandBuildupSetOnAllObjects`
- `ScheduleMTXEvent`
- `ScheduleMTXEventJson`
- `SetEyesOfIbad`
- `SetUpItemList`
- `SpiceAddictionDecreaseSpiceAmount`
- `SpiceFieldForceSpawnNearestField`
- `SpiceFieldPrimeNearestField`
- `SpiceFieldPrimeRandomField`
- `SpiceFieldPrintNearestFieldInfo`
- `SpiceFieldReplenishNearestField`
- `SpiceFieldSetAgeForNearestField`
- `SpiceFieldSetFieldSpawnRate`
- `SpiceFieldSetSpawningEnabled`
- `SpiceFieldShowNearestFieldContents`
- `SpiceFieldTeleportToNearestField`
- `SpiceFieldUpdateGlobalRules`
- `TestDatabaseTransaction`
- `TestDatabaseTransactionDataChange`
- `TestIgwObjectFollowRemotePlayer`
- `TravelToDimension`
- `VisitFriend`

### `UDuneS2sCheatManager`

- `EncountersRandomSetEnabled`
- `EncountersRandomSetInstigationAroundPlayersDelayInSec`
- `EncountersRandomSetInstigationAroundPlayersEnabled`
- `EncountersRandomSetInstigationAroundPlayersRadius`
- `EncountersRandomSetInstigationByAreaDelayInSecOverride`
- `EncountersRandomSetInstigationByAreaEnabled`
- `EncountersRandomSetInstigationOnWholeServerDelayInSec`
- `EncountersRandomSetInstigationOnWholeServerEnabled`
- `EncountersRandomSetInstigationOnWholeServerForced`
- `EncountersSetAreaLimitsEnabled`
- `EncountersSetEnabled`
- `EncountersSetSpawnCooldownEnabled`

### `UFlsCharacterTransfersCheatManager`

- `FlsRestoreAllTokens`

### `UFlsCheatManager`

- `GetFlsPlayerSession`

### `UFlsPlayerAccountCheatManager`

- `FlsDeletePlayerAccountData`
- `FlsSetIsDemoAccount`
- `FlsUpdateDemoPlaytime`

### `UFlsPlayerRewardsCheatManager`

- `FlsClaimPendingRewards`

### `UOvermapCheatManager`

- `OvermapTravelToDimension`

## Kick / Relog Result

Bad news: no shipped allow-listed nice kick, bounce-to-menu, or targeted relog
GM command has been found. Confidence: high.

Rejected or non-working static candidates:

- `KickPlayer`: binary string/table evidence only in the current work.
- `BattlEyeMegaKick`: binary string only in the current work.
- `RemoveSessionMember`: UE Online Services operation/result helper.
- `KickLobbyMember`: UE Online Services lobby operation/result helper.
- `ClientWasKicked`, `ClientReturnToMainMenu`, and
  `ClientReturnToMainMenuWithTextReason`: client RPC names, not exposed GM
  commands.
- `ClientLogOff`: UI/logoff dialog data/widget surface.

There may still be an operational disconnect path through a player-controller,
session, or unresolved notification payload route, but it is not present as a
simple shipped GM command. Confidence: moderate/high.

## Current Execution Status

No command in this catalog is proven to execute through DASH/RMQ yet. Confidence:
high.

The next proof is not "try more command names"; it is solving the decoded
`FNotificationsSystemMessage` wrapper documented in
[native-gm-notification-receive-proof.md](native-gm-notification-receive-proof.md),
then testing the proven `Generic` ServiceBroadcast inner body documented in
[native-gm-servicebroadcast-proof.md](native-gm-servicebroadcast-proof.md).
