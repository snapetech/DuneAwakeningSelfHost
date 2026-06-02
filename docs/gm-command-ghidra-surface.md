# GM Command Ghidra Surface

Confidence: high for the shipped allow-list. Confidence: moderate/high for the
Ghidra command-format functions below. Confidence: low for using any command
until the live `UDuneServerCommandSubsystem` payload contract is proven.

## Source

Run:

```bash
/opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
  -process server-bin \
  -noanalysis \
  -postScript DumpGmCommandSurface.java \
  -scriptPath scripts/research \
  -log /tmp/ghidra-work/gm-command-surface-ghidra.log
```

Output:

- `/tmp/ghidra-work/gm-command-surface-findings.txt`
- `/tmp/ghidra-work/gm-command-surface-ghidra.log`

Supplemental extraction of reflected/demangled cheat-manager method names:

```bash
scripts/research/extract-cheat-manager-methods.py /tmp/ghidra-work/server-bin --format markdown
```

The live image also ships the authoritative allow-list at:

```text
/home/dune/server/DuneSandbox/Config/DedicatedServerGame.ini
```

## Shipped Allow-List

`[AdminSetting.Global]` has only these console commands:

- `obj`
- `FGL.ComponentAuditRequested`

It has only these GM commands:

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

## Reversed Command-Format Evidence

Ghidra found decompiled command-format or handler-adjacent evidence for:

- `AddItemToInventory`
- `AddBasicInventoryToCharacter`
- `AwardXP`
- `SpawnVehicle`
- `SpawnVehicleAt`
- `TeleportToMap`
- `TeleportToExact`
- `TeleportToPlayer`
- `TeleportToLocation`
- `TeleportToClosestSurveyPoint`
- `TeleportToClosestUnrevealedSurveyPoint`
- `TeleportToNearestExplorationVolume`
- `TeleportToNearestNpc`
- `TeleportToSpawnLocation`
- `TeleportToVehicleSpawner`
- `TeleportToSandworm`
- `TravelToDimension`
- `TravelToDimensionByDestination`
- `OvermapTravelToDimensionByDestination`
- `DestroyTargetVehicle`
- `DestroyBuildingPiece`
- `DestroyEntireBuilding`
- `DestroyPlaceable`
- `DestroyTotem`
- `DestroyAllSandStormsOnThisMapAndDimension`

Some of these are not in `DedicatedServerGame.ini`, so they are not exposed by
the shipped dedicated-server GM allow-list even though code exists in the
binary.

## Full Cheat-Manager Inventory

This is the full command/method inventory recovered from cheat-manager method
strings and embedded mangled fragments in the current binary. Treat these as
binary-resident cheat-manager methods, not automatically callable dedicated
server commands. The extractor returns `count=100` for this build.

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

## Exposure Notes

- Only the `DedicatedServerGame.ini` list above is exposed through the shipped
  dedicated-server admin GM allow-list.
- `AwardXP`, `SpawnVehicleAt`, `TeleportToLocation`,
  `TravelToDimensionByDestination`, `OvermapTravelToDimensionByDestination`,
  and `DestroyAllSandStormsOnThisMapAndDimension` have command-format evidence
  but are not allow-listed.
- The larger cheat-manager inventory contains client/admin/debug methods that
  may require in-game admin state, a player-controller cheat manager, editor
  context, or an internal service path. Do not assume broker publishability.
- No method in the full cheat-manager inventory is a targeted nice kick,
  return-to-main-menu, or player-session-close command.

## Kick / Disconnect Result

Bad news: the expected nice-kick command is not in the shipped GM allow-list.
Confidence: high.

- `KickPlayer` exists as a binary string and data-table entry, but Ghidra did
  not find a decompiled Dune GM handler for it in this pass.
- `BattlEyeMegaKick` exists as a string only in this pass; no xref.
- `ClientWasKicked`, `ClientReturnToMainMenu`, and
  `ClientReturnToMainMenuWithTextReason` are client RPC names, not exposed GM
  commands.
- `ClientLogOff` refs are UI/logoff dialog data/widget classes, not a targeted
  admin kick command.
- `RemoveSessionMember` and `KickLobbyMember` decompile as UE Online Services
  operation/result helpers, not Dune dedicated-server GM commands.

There may still be a working operational kick path through an authenticated
in-game admin/player-controller context or an unresolved server-command payload
contract. The current binary/config evidence does not show a simple shipped GM
command that cleanly bounces one player to the menu.
