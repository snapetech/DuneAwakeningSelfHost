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

The same 100 recovered methods are also exposed by
`scripts/gm-command-catalog.py` as `binaryMethods`. Use:

```bash
./scripts/gm-command-catalog.py --format names --include-binary-methods
```

The broad static command catalog is summarized in
[native-gm-command-catalog.md](native-gm-command-catalog.md).

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

## Work Status

Bad news: none of these are proven to work through the current DASH/RMQ command
route. Confidence: high.

Status terms used below:

- `allow-listed-unverified`: the command name is in
  `DedicatedServerGame.ini`, but the live payload/envelope route is still not
  proven.
- `binary-only-unverified`: the method exists in the binary, but it is not in
  the shipped dedicated-server GM allow-list.
- `format-evidence-only`: Ghidra found command-format/decompiled string
  evidence, but it is not allow-listed.
- `rejected-for-kick`: useful as negative evidence only; it is not a working
  kick/disconnect command.

## Full Method Purpose Matrix

| Method | Status | What it appears to do | Risk |
| --- | --- | --- | --- |
| `UCharacterTransferCheatManager::CharacterTransfer_CancelCurrentTransfer` | binary-only-unverified | Cancels an active character-transfer flow. | high |
| `UCharacterTransferCheatManager::CharacterTransfer_CheckTransferStatus` | binary-only-unverified | Queries status for a character-transfer request. | medium |
| `UCharacterTransferCheatManager::CharacterTransfer_ExportData` | binary-only-unverified | Exports character-transfer data. | high |
| `UCharacterTransferCheatManager::CharacterTransfer_FullFlow` | binary-only-unverified | Runs a full character-transfer flow. | high |
| `UCharacterTransferCheatManager::CharacterTransfer_ImportData` | binary-only-unverified | Imports character-transfer data. | high |
| `UCharacterTransferCheatManager::CharacterTransfer_PreTransferCheck_InGame` | binary-only-unverified | Runs in-game transfer eligibility checks. | medium |
| `UCharacterTransferCheatManager::CharacterTransfer_PreTransferCheck_MainMenu` | binary-only-unverified | Runs main-menu transfer eligibility checks. | medium |
| `UCharacterTransferCheatManager::CharacterTransfer_RequestReservation` | binary-only-unverified | Requests a transfer reservation. | high |
| `UClaimSystemCheatManager::ClaimSystemPrintCharacterPacks_Client` | binary-only-unverified | Prints client-side claim-pack data for a character. | low |
| `UClaimSystemCheatManager::ClaimSystemPrintCharacterPacks_Server` | binary-only-unverified | Prints server-side claim-pack data. | low |
| `UClaimSystemCheatManager::ClaimSystemServerConsumeEntirePackForCharacter` | binary-only-unverified | Consumes an entire claim pack for a character. | high |
| `UClaimSystemCheatManager::ClaimSystemServerConsumeFrom2StacksFromPackForCharacter` | binary-only-unverified | Consumes items from two claim-pack stacks for a character. | high |
| `UClaimSystemCheatManager::ClaimSystemServerConsumeFromPackForCharacter` | binary-only-unverified | Consumes items from a claim pack for a character. | high |
| `UDuneCheatManager::AchievementTestPrintAllAchievements` | binary-only-unverified | Prints achievement data. | low |
| `UDuneCheatManager::AchievementTestResetAllAchievements` | binary-only-unverified | Resets achievement progress. | high |
| `UDuneCheatManager::AddItemToInventory` | allow-listed-unverified | Adds an item template/count/quality to inventory. | high |
| `UDuneCheatManager::AddItemToVehicleInventory` | binary-only-unverified | Adds an item to a vehicle inventory. | high |
| `UDuneCheatManager::AddWeaponToInventory` | binary-only-unverified | Adds a weapon with component/mod parameters to inventory. | high |
| `UDuneCheatManager::CheatCurrentDungeonCompletion` | binary-only-unverified | Mutates current dungeon completion state. | high |
| `UDuneCheatManager::ClearFlsCharacterData` | binary-only-unverified | Clears FLS character data. | high |
| `UDuneCheatManager::CompleteCurrentDungeon` | binary-only-unverified | Marks the current dungeon complete. | high |
| `UDuneCheatManager::ConditionsLogRegisteredConditions` | binary-only-unverified | Logs registered condition-system state. | low |
| `UDuneCheatManager::ConditionsLogRegisteredConditionsForCurrentPlayer` | binary-only-unverified | Logs condition state for the current player. | low |
| `UDuneCheatManager::ConditionsLogRegisteredConditionsForEvent` | binary-only-unverified | Logs condition registrations for an event type. | low |
| `UDuneCheatManager::ConditionsLogRegisteredConditionsForEventAndCurrentPlayer` | binary-only-unverified | Logs event condition state for current player. | low |
| `UDuneCheatManager::ConditionsLogRegisteredConditionsForEventAndPlayerId` | binary-only-unverified | Logs event condition state for a player id. | low |
| `UDuneCheatManager::ConditionsLogRegisteredConditionsForPlayerId` | binary-only-unverified | Logs condition state for a player id. | low |
| `UDuneCheatManager::ConditionsLogRegistrationKeys` | binary-only-unverified | Logs condition registration keys. | low |
| `UDuneCheatManager::ConditionsLogSummary` | binary-only-unverified | Logs a condition-system summary. | low |
| `UDuneCheatManager::CoriolisPrintStoredSeeds` | binary-only-unverified | Prints stored Coriolis/farm seed data. | low |
| `UDuneCheatManager::CoriolisSetFarmSeed` | binary-only-unverified | Sets a Coriolis farm seed. | high |
| `UDuneCheatManager::CoriolisSetMapSeed` | binary-only-unverified | Sets a Coriolis map seed. | high |
| `UDuneCheatManager::CoriolisSetPartitionSeed` | binary-only-unverified | Sets a Coriolis partition seed. | high |
| `UDuneCheatManager::DeleteAllCompletionsForAllDungeonsByThisPlayer` | binary-only-unverified | Deletes this player's dungeon completion records. | high |
| `UDuneCheatManager::DeleteAllCompletionsForCurrentDungeon` | binary-only-unverified | Deletes completion records for the current dungeon. | high |
| `UDuneCheatManager::DeleteAllCompletionsForCurrentDungeonByThisPlayer` | binary-only-unverified | Deletes this player's completion for the current dungeon. | high |
| `UDuneCheatManager::DisplayFlsBattlegroupsServerBrowserInfo` | binary-only-unverified | Prints/displays FLS battlegroup browser data. | low |
| `UDuneCheatManager::FlushActorPersistence` | binary-only-unverified | Forces actor persistence flushing. | high |
| `UDuneCheatManager::GlobalDistributionPrintLootSettingsForCurrentLocation` | binary-only-unverified | Prints loot distribution settings at current location. | low |
| `UDuneCheatManager::GlobalDistributionPrintTagsForCurrentLocation` | binary-only-unverified | Prints distribution tags at current location. | low |
| `UDuneCheatManager::InitializeContractsAutoCompleteNamesList` | binary-only-unverified | Initializes contract autocomplete name data. | low |
| `UDuneCheatManager::LogInAs` | binary-only-unverified | Attempts login-as/player impersonation flow. | high |
| `UDuneCheatManager::MigrateMyVehicles` | binary-only-unverified | Migrates vehicle state for the current player. | high |
| `UDuneCheatManager::OpenUIScene` | binary-only-unverified | Opens a named UI scene. | medium |
| `UDuneCheatManager::OverrideDungeonPlayerCount` | binary-only-unverified | Overrides dungeon player count. | high |
| `UDuneCheatManager::PatrolShipListSpawned` | binary-only-unverified | Lists spawned patrol ships. | low |
| `UDuneCheatManager::PatrolShipTeleportToNearest` | allow-listed-unverified | Teleports to the nearest patrol ship. | medium |
| `UDuneCheatManager::PayAllTaxesForNearbyTotem` | binary-only-unverified | Pays taxes for a nearby base/totem. | high |
| `UDuneCheatManager::PlayNow` | binary-only-unverified | Starts/forces a play-now flow. | medium |
| `UDuneCheatManager::PrintListPlayersInFarm` | binary-only-unverified | Prints players in the current farm/server. | low |
| `UDuneCheatManager::PrintMapSettings` | binary-only-unverified | Prints current map settings. | low |
| `UDuneCheatManager::PrintNpcRespawnTimerHere` | binary-only-unverified | Prints nearby NPC respawn timer data. | low |
| `UDuneCheatManager::PrintPlayerCap` | binary-only-unverified | Prints player cap data. | low |
| `UDuneCheatManager::RaiseDatabaseException` | binary-only-unverified | Deliberately raises a DB exception for testing. | high |
| `UDuneCheatManager::RequestFakeGroupTravel` | binary-only-unverified | Requests fake group travel. | high |
| `UDuneCheatManager::ResetCurrentDungeon` | binary-only-unverified | Resets the current dungeon. | high |
| `UDuneCheatManager::ResetCurrentDungeonRoom` | binary-only-unverified | Resets the current dungeon room. | high |
| `UDuneCheatManager::ResetVendorStockData` | binary-only-unverified | Resets vendor stock data. | high |
| `UDuneCheatManager::ReturnToHomeDimension` | binary-only-unverified | Travels/returns the player to home dimension. | medium |
| `UDuneCheatManager::SandBuildupSetOnAllObjects` | binary-only-unverified | Sets sand buildup on objects. | high |
| `UDuneCheatManager::ScheduleMTXEvent` | binary-only-unverified | Schedules an MTX/event entry. | high |
| `UDuneCheatManager::ScheduleMTXEventJson` | binary-only-unverified | Schedules an MTX/event entry from JSON. | high |
| `UDuneCheatManager::SetEyesOfIbad` | binary-only-unverified | Sets Eyes of Ibad visual/progression value. | medium |
| `UDuneCheatManager::SetUpItemList` | binary-only-unverified | Initializes item-list/cache data for cheats/UI. | low |
| `UDuneCheatManager::SpiceAddictionDecreaseSpiceAmount` | binary-only-unverified | Decreases spice addiction amount/state. | medium |
| `UDuneCheatManager::SpiceFieldForceSpawnNearestField` | binary-only-unverified | Forces nearest spice field spawn. | high |
| `UDuneCheatManager::SpiceFieldPrimeNearestField` | binary-only-unverified | Primes nearest spice field. | high |
| `UDuneCheatManager::SpiceFieldPrimeRandomField` | binary-only-unverified | Primes a random spice field. | high |
| `UDuneCheatManager::SpiceFieldPrintNearestFieldInfo` | binary-only-unverified | Prints nearest spice field info. | low |
| `UDuneCheatManager::SpiceFieldReplenishNearestField` | binary-only-unverified | Replenishes nearest spice field. | high |
| `UDuneCheatManager::SpiceFieldSetAgeForNearestField` | binary-only-unverified | Sets nearest spice field age. | high |
| `UDuneCheatManager::SpiceFieldSetFieldSpawnRate` | binary-only-unverified | Sets spice field spawn rate. | high |
| `UDuneCheatManager::SpiceFieldSetSpawningEnabled` | binary-only-unverified | Enables/disables spice field spawning. | high |
| `UDuneCheatManager::SpiceFieldShowNearestFieldContents` | binary-only-unverified | Shows/prints contents for nearest spice field. | low |
| `UDuneCheatManager::SpiceFieldTeleportToNearestField` | binary-only-unverified | Teleports to nearest spice field. | medium |
| `UDuneCheatManager::SpiceFieldUpdateGlobalRules` | binary-only-unverified | Updates global spice field rules. | high |
| `UDuneCheatManager::TestDatabaseTransaction` | binary-only-unverified | Runs test database transaction. | high |
| `UDuneCheatManager::TestDatabaseTransactionDataChange` | binary-only-unverified | Runs test DB transaction with data changes. | high |
| `UDuneCheatManager::TestIgwObjectFollowRemotePlayer` | binary-only-unverified | Tests IGW object follow behavior for remote player. | medium |
| `UDuneCheatManager::TravelToDimension` | allow-listed-unverified | Travels to a map/dimension with optional coordinates. | high |
| `UDuneCheatManager::VisitFriend` | binary-only-unverified | Starts friend visit/travel flow. | medium |
| `UDuneS2sCheatManager::EncountersRandomSetEnabled` | binary-only-unverified | Enables/disables random encounters. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationAroundPlayersDelayInSec` | binary-only-unverified | Sets encounter instigation delay around players. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationAroundPlayersEnabled` | binary-only-unverified | Enables encounter instigation around players. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationAroundPlayersRadius` | binary-only-unverified | Sets encounter instigation radius around players. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationByAreaDelayInSecOverride` | binary-only-unverified | Sets area-based encounter instigation delay override. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationByAreaEnabled` | binary-only-unverified | Enables area-based encounter instigation. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationOnWholeServerDelayInSec` | binary-only-unverified | Sets whole-server encounter instigation delay. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationOnWholeServerEnabled` | binary-only-unverified | Enables whole-server encounter instigation. | high |
| `UDuneS2sCheatManager::EncountersRandomSetInstigationOnWholeServerForced` | binary-only-unverified | Forces whole-server encounter instigation. | high |
| `UDuneS2sCheatManager::EncountersSetAreaLimitsEnabled` | binary-only-unverified | Enables/disables encounter area limits. | high |
| `UDuneS2sCheatManager::EncountersSetEnabled` | binary-only-unverified | Enables/disables encounters globally. | high |
| `UDuneS2sCheatManager::EncountersSetSpawnCooldownEnabled` | binary-only-unverified | Enables/disables encounter spawn cooldowns. | high |
| `UFlsCharacterTransfersCheatManager::FlsRestoreAllTokens` | binary-only-unverified | Restores FLS character-transfer tokens. | high |
| `UFlsCheatManager::GetFlsPlayerSession` | binary-only-unverified | Gets the FLS player session; helper, not an operator command. | low |
| `UFlsPlayerAccountCheatManager::FlsDeletePlayerAccountData` | binary-only-unverified | Deletes FLS player account data. | high |
| `UFlsPlayerAccountCheatManager::FlsSetIsDemoAccount` | binary-only-unverified | Sets demo-account flag. | high |
| `UFlsPlayerAccountCheatManager::FlsUpdateDemoPlaytime` | binary-only-unverified | Updates demo playtime. | high |
| `UFlsPlayerRewardsCheatManager::FlsClaimPendingRewards` | binary-only-unverified | Claims pending FLS rewards. | high |
| `UOvermapCheatManager::OvermapTravelToDimension` | format-evidence-only | Overmap-specific dimension travel. | high |

## Allow-Listed Command Purpose Matrix

These are the only command names the dedicated server config exposes. They are
still unverified through DASH/RMQ.

| Command | What it appears to do | Evidence | Risk |
| --- | --- | --- | --- |
| `obj` | Unreal object/debug console command. | allow-listed console command | high |
| `FGL.ComponentAuditRequested` | Component audit/debug console command. | allow-listed console command | low |
| `AddItemToInventory` | Adds item to inventory. | allow-listed GM + method evidence | high |
| `AddBasicInventoryToCharacter` | Adds a basic inventory kit to character. | allow-listed GM + command-format evidence | high |
| `SpawnVehicle` | Spawns vehicle. | allow-listed GM + command-format evidence | high |
| `PatrolShipTeleportToNearest` | Teleports admin/player to nearest patrol ship. | allow-listed GM + method evidence | medium |
| `TeleportTo` | Generic teleport helper. | allow-listed GM + command-format evidence | high |
| `TeleportToMap` | Teleports/travels to map. | allow-listed GM + command-format evidence | high |
| `TeleportToExact` | Teleports to exact coordinates. | allow-listed GM + command-format evidence | high |
| `TeleportToPlayer` | Teleports to named player. | allow-listed GM + command-format evidence | high |
| `TeleportToVehicleSpawner` | Teleports to a vehicle spawner. | allow-listed GM + command-format evidence | medium |
| `TeleportToSandworm` | Teleports to sandworm. | allow-listed GM + command-format evidence | medium |
| `TeleportToPersonalMarker` | Teleports to personal marker. | allow-listed GM only | medium |
| `TravelTo` | Travel helper. | allow-listed GM + command-format evidence | high |
| `TravelToDimension` | Travel to map/dimension. | allow-listed GM + method evidence | high |
| `Fly` | Admin movement mode. | allow-listed GM + noisy method/string evidence | medium |
| `Ghost` | Admin no-clip/ghost movement mode. | allow-listed GM + noisy method/string evidence | medium |
| `Walk` | Restores walking movement mode. | allow-listed GM + noisy method/string evidence | medium |
| `DestroyTargetVehicle` | Destroys targeted vehicle. | allow-listed GM + method evidence | high |
| `DestroyTotem` | Destroys a base/totem target. | allow-listed GM + method evidence | high |
| `DestroyPlaceable` | Destroys a placeable target. | allow-listed GM + method evidence | high |
| `DestroyEntireBuilding` | Destroys an entire building. | allow-listed GM + method evidence | high |
| `DestroyBuildingPiece` | Destroys a building piece. | allow-listed GM + method evidence | high |
| `PrintPos` | Prints current position. | allow-listed GM; safest route probe | low |

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
