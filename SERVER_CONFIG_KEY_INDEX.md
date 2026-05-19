# Shipped Server Config Key Index

Generated from the shipped `DuneSandbox/Config/DefaultGame.ini` in build `1963158`.
This is an inventory, not a recommendation to override every key. Asset/UI/audio references are listed so missing knobs are searchable, but most useful self-host tuning is in `SERVER_CONFIG_KEYS.md`.

Status meanings: `Known` has shipped setup comments or strong default-config evidence; `Inferred` is based on section/key names and value shape; `Asset/reference` and `UI/visual` are usually poor server-tuning candidates; `Unknown / investigate` needs live testing or binary analysis.

## `[/Script/EngineSettings.GeneralProjectSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `ProjectID` | `5648D2154E457C21785E53AFC5964C49` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CopyrightNotice` | `Copyright 1998-2025 Funcom Oslo AS. All Rights Reserved.` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ProjectDisplayedTitle` | `"Dune: Awakening"` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `CompanyName` | `Funcom Oslo AS` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CompanyDistinguishedName` | `Funcom Oslo AS` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `Homepage` | `"https://www.funcom.com"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ProjectName` | `Dune: Awakening` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ProjectVersion` | `1.4.0.0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `Description` | `Dune: Awakening is an open world, multiplayer survival game on a massive scale.` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SupportContact` | `"https://duneawakening.com"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/UE4Dreamworld.DWWorldSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `GameplaySchedulerClass` | `/Script/DuneSandbox.DuneGameplayScheduler` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.DuneWorldSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MapSettings` | `/Game/Dune/Maps/Settings/DA_MapSettings_Default.DA_MapSettings_Default` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/Engine.GameNetworkManager]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `ClientErrorUpdateRateLimit` | `0.35f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `ClientNetSendMoveDeltaTime` | `0.0333f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ClientNetSendMoveDeltaTimeThrottled` | `0.0666f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ClientNetSendMoveDeltaTimeStationary` | `0.0833f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ClientnetSendMoveThrottleOverPlayerCount` | `30` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MAXCLIENTUPDATEINTERVAL` | `0.35f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MaxClientForcedUpdateDuration` | `0.60f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `ServerForcedUpdateHitchThreshold` | `0.10f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `ServerForcedUpdateHitchCooldown` | `0.30f` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `MaxMoveDeltaTime` | `0.25f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MAXPOSITIONERRORSQUARED` | `64` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `bMovementTimeDiscrepancyDetection` | `true` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bMovementTimeDiscrepancyResolution` | `true` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `MovementTimeDiscrepancyMaxTimeMargin` | `1.5f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MovementTimeDiscrepancyMinTimeMargin` | `-1.5f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MovementTimeDiscrepancyResolutionRate` | `1.0f` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `MovementTimeDiscrepancyDriftAllowance` | `0.03f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bMovementTimeDiscrepancyForceCorrectionsDuringResolution` | `true` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `ClientNetCamUpdateDeltaTime` | `0.66` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ClientNetCamUpdatePositionLimit` | `650` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.MapFpsSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+m_Maps` | `32 entries; first \`(m_Map=(Name="HaggaBasin"), m_MaxFps=20)\`` | 32 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.MapFeatures]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_Maps` | `(((Name="DeepDesert"), (m_Taxation=False,m_DeepDesertGameplay=True,m_ShiftingSands=True,m_bCanBlo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.FullscreenMapSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultMapZoomStep` | `2` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_RespawnMapZoomStep` | `1` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DetectionRangeModifier` | `0` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MapAreaMeshToWorldScalar` | `1.000000` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_OtherPlayerMarkerColour` | `(R=0.550000,G=0.550000,B=0.550000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PartyMemberMarkerColour` | `(R=0.000000,G=0.500000,B=0.000000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_RemoveDeathLocationMarkerRange` | `1000.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SandstormMarkerTextOffset` | `60.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SandstormMarkerTextSize` | `16` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_InWorldMarkerBase` | `BlueprintGeneratedClass'/Game/Dune/Systems/FullscreenMap/BP_InWorldMarkerActor.BP_InWorldMarkerAc...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MarkerReplicationRange` | `200000.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultServerSendMarkersTimer` | `1.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultClientSendViewportInterval` | `1` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_DefaultServerFlushMarkerBufferFrequency` | `4` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultSinkchartTemplateId` | `(Name="Sinkchart")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SurveyProbeScanAltitudeMeters` | `100` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SurveyProbeMinimumForwardDistanceMeters` | `50` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SurveyProbeFixedDistanceFromPlayerMeters` | `100` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SurveyReportDataAsset` | `/Game/Dune/Systems/Surveying/DA_ReportModeSurveyResultsConfiguration.DA_ReportModeSurveyResultsCo...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SpiceFieldTypeMarkerTypeLinkConfig` | `/Game/Dune/Systems/Surveying/DA_SpiceFieldTypeMapMarkerTypeConfig.DA_SpiceFieldTypeMapMarkerTypeC...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SurveyScanStartAudioOneShot` | `/Game/Dune/Audio/Events/AAA_NEW/ToolsGadgets/GAD_SurveyProbe/AD_GAD_SurveyProbe_2D_Scan.AD_GAD_Su...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SurveyScanCompletedAudioOneShot` | `/Game/Dune/Audio/Events/AAA_NEW/ToolsGadgets/GAD_SurveyProbe/AD_GAD_SurveyProbe_2D_Complete.AD_GA...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SurveyScanFailedAudioOneShot` | `/Game/Dune/Audio/Events/AAA_NEW/ToolsGadgets/GAD_SurveyProbe/AD_GAD_SurveyProbe_2D_Fail.AD_GAD_Su...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SoftMapMPC` | `/Game/Dune/Systems/UiMap/Materials/MPC_UiMap.MPC_UiMap` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SoftFogZoneRT` | `/Game/Dune/GUI/Textures/Menus/Gameplay/Map/RT_MapFogZones.RT_MapFogZones` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SoftFogTrailRT` | `/Game/Dune/GUI/Textures/Menus/Gameplay/Map/RT_MapFogTrail.RT_MapFogTrail` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultScanPostProcessMaterialInterface` | `/Game/Dune/Effects/PostProcess/Scan/Materials/MI_PP_GeoScan_Atreides_Combine.MI_PP_GeoScan_Atreid...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MarkerMapScreenDensityScale` | `(Value=1.000000,Curve=(CurveTable=/Script/Engine.CurveTable'"/Game/Dune/Systems/FullscreenMap/Dat...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_NewMarkerFloatCurve` | `/Game/Dune/Systems/FullscreenMap/CF_NewMarkerScaleIn.CF_NewMarkerScaleIn` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_NewMarkerSwipeSpeed` | `0.913029` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_NewMarkerScaleInDuration` | `0.500000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SurveyFailedTooLowHeightAudioOneShot` | `/Game/Dune/Audio/Events/AAA_NEW/ToolsGadgets/GAD_SurveyProbe/AD_GAD_SurveyProbe_2D_Fail.AD_GAD_Su...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SinkchartRecipeDataAsset` | `/Game/Dune/Systems/FullscreenMap/DataAssets/DA_CraftSinkchart.DA_CraftSinkchart` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NewMarkerCosmeticConfigurationAsset` | `/Game/Dune/Systems/FullscreenMap/DataAssets/DA_NewMarkerCosmeticConfiguration.DA_NewMarkerCosmeti...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ResourceMarkerKillSwitchBlacklist` | `(GameplayTags=((TagName="MapMarkers.Resource")))` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ResourceMarkerKillSwitchWhitelist` | `(GameplayTags=((TagName="MapMarkers.Resource.Compacted.Spice")))` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_AutoDiscoveredMarkerBase` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Systems/StaticMarkers/BP_AutoDiscoveredStaticMa...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultStaticLocationDataTable` | `/Game/Dune/Systems/FullscreenMap/DataTables/DT_StaticLocationData.DT_StaticLocationData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.PingSystemSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_PingsPerPlayerLimit` | `5` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PingMaximumDistance` | `2000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PingPlacementHeightOffset` | `0.500000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_QuickPingDoubleTapActionDelayInSeconds` | `0.300000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_PingInWorldMarkerExpiryTime` | `5` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PingMapMarkerExpiryTime` | `60` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.LoadingScreenSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_LoadingTimer` | `5.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_bEnableEditorLoadingScreen` | `False` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_bEnableBuildLoadingScreen` | `true` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultStartupMapName` | `MainMenu` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ShelterSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ShelterTraceLength` | `10000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShelterTimerSquareDistanceTolerance` | `1.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ShelterTraceGridCellSize` | `200.0000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `+m_ShelterDirections` | `9 entries; first \`(X=0.029990,Y=-0.017440,Z=0.999400)\`` | 9 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShelterTraceFrameBudget` | `350` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShelterGeneralTraceChannel` | `ECC_GameTraceChannel13` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShelterBuildableTraceChannel` | `ECC_EngineTraceChannel6` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_ShelterDeployableTraceChannel` | `ECC_GameTraceChannel13` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_WindShelterGeneralTraceChannel` | `ECC_GameTraceChannel13` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_WindStaticShelterGeneralTraceChannel` | `ECC_WorldStatic` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bUseShelterGeneralTraceOnly` | `false` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BuildingShelterThreshold` | `0.9` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableShelterThreshold` | `0.65` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |

## `[/Script/DuneSandbox.BuildingSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bShowBuildingSockets` | `False` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DebugMeshClass` | `/Game/Dune/Systems/Building/Pieces/BP_DebugBuildingMesh.BP_DebugBuildingMesh_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DebugMeshMaterial` | `/Game/Dune/Systems/Building/Materials/MI_WireframeMaterial_Inst.MI_WireframeMaterial_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DebugArrowLocalTransform` | `(Rotation=(X=0.000000,Y=-0.000000,Z=0.707107,W=0.707107),Translation=(X=0.000000,Y=0.000000,Z=190...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LootContainerTypeOnDestroy` | `(Name="ItemDrop")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bMitigateAllSandstormDamage` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_PlacementHelperCacheTransform` | `(Rotation=(X=0.000000,Y=-0.000000,Z=0.000000,W=1.000000),Translation=(X=0.000000,Y=0.000000,Z=-50...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BuildingCustomColorCustomDataIndex` | `7` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bBuildableElodEnabled` | `False` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_RepairStationSet` | `(Name="RepairStation_Patent")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_NumberOfPlaceablesWithLostStabilityToDestroyPerFrame` | `25` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_ReplaceCompatibleSocketSetups` | `(m_CompatibleSockets=((Name="Door"),(Name="Wall"),(Name="Door_Frame")))` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PersistenceDelayDefaultFast` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_PersistenceDelayDefault` | `15.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_PersistenceDelayAddedRandomizedRange` | `60.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PersistenceDelayWaterGeneration` | `300.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_PersistenceDelayDamage` | `120.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_QuickDepositInventoryInteractionClass` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Characters/Player/Interactions/Objects/BP_Stora...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_VehicleDepositOverlapRange` | `20000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_VehicleDepositLandclaimRange` | `2500.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableCameraHitDistanceMargin` | `5.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDefaultRelevancyRadius` | `80000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bEnableBuildingSmartRelevancy` | `False` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingSmartRelevancyDistanceSquaredRange` | `(X=2500000000.000000,Y=10000000000.000000)` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingSmartRelevancyVisualSizeSquaredRange` | `(X=1000000.000000,Y=56250000.000000)` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableDefaultRelevancyRadius` | `15000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bEnablePlaceableDynamicRelevancy` | `True` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableDynamicRelevancyDistanceSquaredRange` | `(X=100000000.000000,Y=2500000000.000000)` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableDynamicRelevancyVisualSizeSquaredRange` | `(X=18225.000000,Y=640000.000000)` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingCellSize` | `10000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bEnableStabilizationSystem` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bEnableDestabilizationSystem` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bEnableStabilizationSystemVFX` | `False` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ThreatBlobsSize` | `500.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BuildingSandBuildUpPercentageCustomDataIndex` | `0` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingSandBuildUpColorCustomDataIndex` | `11` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bSandBuildUpOverrideColor` | `False` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SandBuildUpDebugColor` | `602110` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SandBuildUpPlaceablesShelteredTargetValue` | `0.300000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SandBuildUpPlaceablesUnShelteredTargetValue` | `0.700000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDamageCustomDataIndex` | `1` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_PlaceableDamageCustomDataIndex` | `1` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableDamageMaterialUpdateThreshold` | `10.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DamageVisualizationMultiplier` | `1.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_FallbackDefaultBuildingHealth` | `2500.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_FallbackDefaultPlaceableHealth` | `400.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DefaultBuildingDamageMitigation` | `(((Name="RepairDamageMitigation"), 1.000000),((Name="EnergyDamageMitigation"), -1.000000),((Name=...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DefaultPlaceableDamageMitigation` | `(((Name="EnergyDamageMitigation"), -1.000000),((Name="SandstormDamageMitigationLevel1"), 1.000000...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PickupTotalDurabilityPercentageReduction` | `0.050000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BuildingDestructibleTimer` | `10.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DefaultDestructibleGeometryCollectionActorClass` | `/Game/Dune/Art/TechArt/ChaosDestruction/BP_DuneDestructibleActor.BP_DuneDestructibleActor_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_bEnableBuildingDestructionEffects` | `True` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bBuildingDestructionUseNiagaraSystem` | `True` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bPlaceableDestructionUseNiagaraSystem` | `False` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDestructionNumberOfStaticMeshCached` | `30` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDestructionMaximumNumberOfInstances` | `100` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDestructionMaximumNumberOfInstancesPerFrame` | `15` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDestructionNumberOfFramesDelay` | `2` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingDestructionEffectRemovalDelayInMS` | `0.100000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildableDestructionNiagaraSystem` | `/Game/Dune/Effects/RnD/BuildingPieceCrumble/Niagara/NS_VFX_RnD_CrumblingBuildingPiece.NS_VFX_RnD_...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintDetectionRange` | `200.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_BuildingBlueprintLookupPaths` | `/Game/Dune/Systems/Building/Data/Blueprints` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintBrushMaterial` | `/Game/Dune/Systems/Building/Materials/M_BuildBlueprintBrush.M_BuildBlueprintBrush` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintBrushExtensionsMaterial` | `/Game/Dune/Systems/Building/Materials/MI_BuildBlueprintExtensionsBrush.MI_BuildBlueprintExtension...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintBrushDoubleSidedMaterial` | `/Game/Dune/Systems/Building/Materials/M_BuildBlueprintBrushDoubleSided.M_BuildBlueprintBrushDoubl...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintDefaultHeightOffset` | `-192.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `s_BuildingBlueprintMaxPiecesPerFrame` | `100` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintMaxPlaceablesPerFrame` | `17` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_CopyToolDialogContentClass` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Building/CopyTool/W_CopyToolDialogueContent.W_CopyToolDialo...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BuildingBlueprintStructureCategoryValidationExclusion` | `()` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintGroupTypeValidationExclusion` | `()` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintViewUsePlaceableAsset` | `()` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingOverlapTraceChannel` | `ECC_GameTraceChannel6` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_CollisionDetectionPercentage` | `(X=0.700000,Y=0.700000,Z=0.700000)` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `+m_ClassesFailedOverlapMessage` | `4 entries; first \`(m_OverlapClass=/Script/CoreUObject.Class'"/Script/Landscape.Landsc...\`` | 4 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BuildingBaseClass` | `/Game/Dune/Systems/Building/Pieces/BP_DuneBuildingBase.BP_DuneBuildingBase_C` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingSetupClass` | `/Game/Dune/Systems/Building/Pieces/BP_BuildingSetup.BP_BuildingSetup_C` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingStatusWidgetClass` | `/Game/Dune/Systems/Building/Widgets/W_CanBuildIndicator.W_CanBuildIndicator_C` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBlueprintStatusWidgetClass` | `/Game/Dune/Systems/Building/Widgets/W_BlueprintCanBuildIndicator.W_BlueprintCanBuildIndicator_C` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingBrushMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_Materialization_Brush.MI_Building_Materializati...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingStabilityMaterial` | `/Game/Dune/Systems/Building/Materials/M_BuildingStability.M_BuildingStability` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_BuildingBrushVisibilityBlockingChannels` | `ECC_WorldStatic` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_CanBuildBrushColors` | `(R=1.000000,G=0.274510,B=0.023529,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_CanNotBuildBrushColors` | `(R=0.921569,G=0.047059,B=0.007843,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ProjectionBeamVfx` | `/Game/Dune/Systems/Holograms/Particle/NS_HologramBeam.NS_HologramBeam` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_FreeRotateSpeed` | `5.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_FreeTranslateSpeed` | `100.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_FreeTranslateMax` | `100.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_FreeRotateMax` | `45.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BrushEasingMaxDistance` | `1500.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BrushEasingSpeed` | `20.000000` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BrushEasingFunc` | `EaseOut` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bEnableBuildingList` | `False` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_DefaultFavorites` | `10 entries; first \`(Name="Totem_Small_Placeable")\`` | 10 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ExilesCameraModifier` | `None` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BuildableDetectionDistance` | `4000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildableDetectionSphereRadius` | `11.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_MaxBuildableDetectionDistanceCheckMultiplier` | `1.500000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingHeightLimitInM` | `980.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlacementHelperSocketStaticMesh` | `/Game/Dune/Systems/Building/Meshes/SM_BuildSocket2.SM_BuildSocket2` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BrushOrientationTextBlueprint` | `/Game/Dune/Systems/Building/Pieces/BP_BuildingBrushOrientationText.BP_BuildingBrushOrientationText_C` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BrushOrientationArrowStaticMesh` | `/Game/Dune/Systems/Building/Meshes/SM_BuildingBrushIndicatorArrow.SM_BuildingBrushIndicatorArrow` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BrushOrientationArrowMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_BrushArrow_Inst.MI_Building_BrushArrow_Inst` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BrushOrientationArrowHeight` | `100.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_CanBuildBrushOrientationArrowColor` | `(R=0.635000,G=0.015000,B=0.015000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CanNotBuildBrushOrientationArrowColor` | `(R=0.234000,G=0.005000,B=0.005000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CanBuildHologramBrushOrientationArrowColor` | `(R=0.927083,G=0.148914,B=0.000000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CanNotBuildHologramBrushOrientationArrowColor` | `(R=0.234000,G=0.005000,B=0.005000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BuildingBlueprintMaxExtensions` | `4` | 1 | Known | Number of times a landclaim/building blueprint can be expanded; not the active base-count cap. |
| `m_BaseBackupMaxExtensions` | `8` | 1 | Known | Base backup/reconstruction extension cap; not the active base-count cap. |
| `m_BuildingBlueprintRangeMultiplier` | `0.660000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingCategoryLimitWarningPercentageVisible` | `0.650000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlacementHelperAliveThresholdTimeInSecs` | `900.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BuildingSystemSecurityZoneUpdateRateInSeconds` | `1.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_NearbyBuildingDetectionHeightRange` | `25000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingHologramMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_Materialization.MI_Building_Materialization` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingHologramTwoSidedMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_Materialization_TwoSided.MI_Building_Materializ...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingHologramCollisionProfile` | `BuildingHologram` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableHologramCollisionProfile` | `PlaceableHologram` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_ThresholdDistanceFromTotemForHologramVisibilityInCm` | `2000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_CanBuildHologramBrushColors` | `(R=0.000000,G=1.000000,B=0.454902,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_CanNotBuildHologramBrushColors` | `(R=0.080000,G=0.210000,B=0.150000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BuildingHologramFillStabilityPercentCustomDataIndex` | `0` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingHologramFillProgressPercentCustomDataIndex` | `1` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingFillProgressPercentCustomDataIndex` | `12` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DefaultBuildAndFillTimeInSeconds` | `0.500000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_BuildAndFillStartThresholdTimerInSeconds` | `0.200000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_HologramFillCrosshairColorGradient` | `/Game/Dune/GUI/Data/C_WeldingTorch_HologramFill_ColorGradient.C_WeldingTorch_HologramFill_ColorGr...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BuildableBuildAndFillHoldTimes` | `((Short, 0.875000),(Medium, 1.250000),(Long, 2.000000),(VeryLong, 2.000000))` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_ValidPlacementClasses` | `6 entries; first \`/Script/Engine.StaticMeshActor\`` | 6 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `+m_ValidPlacementComponentClasses` | `2 entries; first \`/Script/Engine.HierarchicalInstancedStaticMeshComponent\`` | 2 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ValidPlacementActorTags` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlacementGhostObjectType` | `ECC_WorldStatic` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlacementGhostLineTraceChannel` | `ECC_GameTraceChannel2` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlacementGhostMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_Ghost_Inst.MI_Building_Ghost_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PlacementUpgradeGhostMaterial` | `/Game/Dune/Systems/Building/Materials/MI_BuildingUpgrade_Ghost_Inst.MI_BuildingUpgrade_Ghost_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PlacementInvalidGhostMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_InvalidGhost_Inst.MI_Building_InvalidGhost_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PlacementGhostRadius` | `750.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PlacementGhostBuildableSweepTraceRadius` | `750.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildRange` | `2000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TotemRespawnOffset` | `(X=0.000000,Y=0.000000,Z=100.000000)` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bEnableBuildingNearServerBorders` | `False` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bMinBuildableDistanceFromServerBorder` | `1000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bCustomMinBuildableDistanceFromServerBorder` | `(((Name="DeepDesert"), 10000.000000))` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildableBlockingVolumeMaterial` | `/Game/Dune/Systems/Building/Landclaim/Materials/MI_LandclaimBoundary_Blocking.MI_LandclaimBoundar...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_MaxNumLandclaimSegments` | `6` | 1 | Known | Maximum connected landclaim segments per base/landclaim. Shipped setup says clients also need this value. |
| `m_LandclaimThresholdDistance` | `512.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_LandclaimFoundationDistanceFromBorder` | `35.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_ThresholdDistanceVFXTotemRadius` | `5000.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_ComplementTotemName` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/BUILDING_SETTINGS_C...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_StakingUnitExtensionDefaultTimes` | `10 entries; first \`60.000000\`` | 10 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_StakingUnitVerticalExtensionDefaultTimes` | `10 entries; first \`60.000000\`` | 10 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bCanRemoveBuildablesWithNoOwner` | `True` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_bBuildingRestrictionLimitsEnabled` | `True` | 1 | Known | Enables building restriction limits. Shipped setup says clients also need this value. |
| `m_StakingUnitType` | `(Name="StakingUnit_Placeable")` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_StakingUnitVerticalType` | `(Name="StakingUnitVertical_Placeable")` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_InventoryCircuits` | `8 entries; first \`(m_CircuitId=1,m_CircuitName=LOCTABLE("/Game/Dune/Localization/ST_L...\`` | 8 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_WaterCircuits` | `(m_CircuitId=1,m_CircuitName=LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_PowerCircuits` | `(m_CircuitId=1,m_CircuitName=LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlaceableMaterialEmissivePowerParamName` | `Light Source - Emissive Power` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableMaterialEmissivePowerOnValue` | `10.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_StructuresOverLimitDialogContentWidget` | `2 entries; first \`/Game/Dune/GUI/Widgets/Menus/Gameplay/Building/StructuresOverLimitD...\`` | 2 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MinTotemCodeRandomRange` | `100000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_MaxTotemCodeRandomRange` | `999999` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DefaultTotemProfileName` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/BUILDING_SETTINGS_D...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_MinAccessLevelRange` | `1` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxAccessLevelRange` | `5` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultProfileAccessLevel` | `3` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultPlaceableAccessLevel` | `1` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_TimeToAutomaticallyCloseDoor` | `10` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TimeToAutomaticallyCloseDoorRetry` | `1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PentashieldDetectionInterval` | `0.100000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_PentashieldDetectionDistanceCharacterAudio` | `5000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PentashieldDetectionDistanceCharacter` | `500.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PentashieldMaxDetectionDistance` | `3000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SmallRangeDoorDetectionDistance` | `250.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_OpenDoorMinimumVelocity` | `600.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PentashieldAccessAllowedColor` | `(R=0.000000,G=2.220000,B=20.000000,A=0.100000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PentashieldAccessWalkingOnlyAllowedColor` | `(R=0.000000,G=1.000000,B=0.000000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PentashieldAccessDeniedColor` | `(R=1.000000,G=0.000000,B=0.000000,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PentashieldSurfaceMaxHeight` | `5568.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PentashieldSurfaceMaxWidth` | `7424.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultBuildingSystemModifiers` | `(m_RefundPercentage=1.000000,m_PlacementCostMultiplier=1.000000)` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_DefaultRepairCostMultiplier` | `0.500000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultShieldDamageMitigation` | `(((Name="DartDamageMitigation"), 2000.000000),((Name="EnergyDamageMitigation"), 2000.000000),((Na...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlaceableToolConfiguration` | `((Functional, (m_PlaceableDataTable="/Game/Dune/Systems/Building/Data/PlaceableData/CDT_Placeable...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_LandclaimNotificationTimeInSeconds` | `8` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BaseBackupToolMapRestriction` | `((Name="HaggaBasin"), (Name="Editor_Default"), (Name="IGW_Test_Small"))` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BuildingBlueprintSnapToOriginBaseBackupMaxAllowedDistance` | `5000.0` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BaseBackupToolTimeRestrictionInSeconds` | `604800` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ZAxisDoorMaxBuffer` | `900.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/ImprintSystem.DynamicSandSubSystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SoftDynamicSandSetupActor` | `/Game/Dune/Systems/DynamicSand/BP_DynamicSandSetupActor.BP_DynamicSandSetupActor_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.SandBuildUpSubSystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SoftSandBuildUpCapture` | `/Game/Dune/Systems/SandBuildUp/BP_SandBuildUpCapture.BP_SandBuildUpCapture_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SoftGlobalMaterialParameterCollection` | `/Game/Dune/Art/Global/MPC_GlobalMaterialValues.MPC_GlobalMaterialValues` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.StartMenuWidget]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MiddayMap` | `/Game/Dune/Maps/R4_Arrakis/ArtCorner/R4_Arrakis_ArtCorner_Midday.R4_Arrakis_ArtCorner_Midday` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GoldenHourMap` | `/Game/Dune/Maps/R4_Arrakis/ArtCorner/R4_Arrakis_ArtCorner_GoldenHour.R4_Arrakis_ArtCorner_GoldenHour` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_NightMap` | `/Game/Dune/Maps/R4_Arrakis/ArtCorner/R4_Arrakis_ArtCorner_Night.R4_Arrakis_ArtCorner_Night` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GrabenMap` | `/Game/Dune/Maps/R5_Arrakis/ArtCorner/R5_ArtCorner_Graben.R5_ArtCorner_Graben` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneWorldGenerator]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_IdentityStreamingVolumeAsset` | `/Game/Dune/Systems/DynamicContent/DefaultInstanceStreamingVolume.DefaultInstanceStreamingVolume` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[CoreRedirects]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+EnumRedirects` | `(OldName="/Script/Building.EBuildingSocketType",NewName="/Script/DuneSandbox.EBuildingSocketType_...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+PropertyRedirects` | `9 entries; first \`(OldName="NpcConfigurationDataRowBase.m_TeamId",NewName="NpcConfigu...\`` | 9 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+StructRedirects` | `(OldName="FrameTypeToAttributeRowBase", NewName="FrameTypeToWeaponClassRowBase")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneBuildSystemComponent]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_BuildingBaseClass` | `BlueprintGeneratedClass'/Game/Dune/Systems/Building/Pieces/BP_DuneBuildingBase.BP_DuneBuildingBas...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildingStatusWidgetClass` | `WidgetBlueprintGeneratedClass'/Game/Dune/Systems/Building/Widgets/W_CanBuildIndicator.W_CanBuildI...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `BuildingBrushMaterial` | `/Game/Dune/Systems/Building/Materials/M_BuildBrush.M_BuildBrush` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `PlacementGhostMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_Ghost_Inst.MI_Building_Ghost_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `PlacementInvalidGhostMaterial` | `/Game/Dune/Systems/Building/Materials/MI_Building_InvalidGhost_Inst.MI_Building_InvalidGhost_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `PlacementUpgradeGhostMaterial` | `/Game/Dune/Systems/Building/Materials/MI_BuildingUpgrade_Ghost_Inst.MI_BuildingUpgrade_Ghost_Inst` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/UnrealEd.ProjectPackagingSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `Build` | `IfProjectHasCode` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `BuildConfiguration` | `PPBC_Development` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `BuildTarget` | `DuneSandbox` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `FullRebuild` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ForDistribution` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `IncludeDebugFiles` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `BlueprintNativizationMethod` | `Disabled` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bIncludeNativizedAssetsInProjectGeneration` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bExcludeMonolithicEngineHeadersInNativizedCode` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `UsePakFile` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bUseIoStore` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bUseZenStore` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bMakeBinaryConfig` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bGenerateChunks` | `False` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `bGenerateNoChunks` | `False` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `bChunkHardReferencesOnly` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bForceOneChunkPerFile` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `MaxChunkSize` | `0` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `bBuildHttpChunkInstallData` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `HttpChunkInstallDataDirectory` | `(Path="")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `WriteBackMetadataToAssetRegistry` | `Disabled` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `bCompressed` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `PackageCompressionFormat` | `Oodle` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bForceUseProjectCompressionFormatIgnoreHardwareOverride` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `PackageAdditionalCompressionOptions` | `` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PackageCompressionMethod` | `Kraken` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PackageCompressionLevel_DebugDevelopment` | `4` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PackageCompressionLevel_TestShipping` | `5` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PackageCompressionLevel_Distribution` | `7` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PackageCompressionMinBytesSaved` | `1024` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PackageCompressionMinPercentSaved` | `5` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bPackageCompressionEnableDDC` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `PackageCompressionMinSizeToConsiderDDC` | `0` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `HttpChunkInstallDataVersion` | `` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `IncludePrerequisites` | `True` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `IncludeAppLocalPrerequisites` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bShareMaterialShaderCode` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bDeterministicShaderCodeOrder` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bSharedMaterialNativeLibraries` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `ApplocalPrerequisitesDirectory` | `(Path="")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `IncludeCrashReporter` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `InternationalizationPreset` | `All` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+CulturesToStage` | `14 entries; first \`en\`` | 14 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `LocalizationTargetCatchAllChunkId` | `0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bCookAll` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bCookMapsOnly` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bSkipEditorContent` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bSkipMovies` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `+DirectoriesToAlwaysCook` | `20 entries; first \`(Path="/Game/Dune/Systems/InfiniteGameWorlds")\`` | 20 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+DirectoriesToNeverCook` | `11 entries; first \`(Path="/Game/Dune/Systems/DayNightCycle/Biomes/PolarCap")\`` | 11 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+DirectoriesToAlwaysStageAsUFS` | `(Path="Dune/GUI/Slate/Cursor")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[Staging]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+DisallowedConfigFiles` | `6 entries; first \`DuneSandbox/Config/AssetVerifyRules.ini\`` | 6 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+AllowedConfigFiles` | `45 entries; first \`DuneSandbox/Config/TLS/cacert.pem\`` | 45 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+AllowedDirectories` | `2 entries; first \`DuneSandbox/Content/Dune/GUI/Textures/Icons/Gameplay/Origin\`` | 2 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneCheatManager]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_BrokenWeaponTemporaryEffect` | `/Game/Dune/GadgetsAbilities/Swordmaster/GE_Debug_BrokenWeaponDebuff.GE_Debug_BrokenWeaponDebuff_C` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_CharacterDeathEventsSpamLimit` | `2000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_NpcControlPanelClass` | `Blueprint'/Game/Dune/Prototyping/Blueprints/NpcControlPanel/BP_NpcControlPanel.BP_NpcControlPanel_C'` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CinematicCameraPanelClass` | `Blueprint'/Game/Dune/Prototyping/Blueprints/CinematicPanel/BP_CinematicPanel.BP_CinematicPanel_C'` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_TheresNoPlaceLikeHomeMap` | `(Name=HaggaBasin)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TheresNoPlaceLikeHomeLocation` | `(X=47750.0, Y=336370.0, Z=1500.0)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.OvermapCheatManager]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_TheresNoPlaceLikeHomeMap` | `(Name=HaggaBasin)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TheresNoPlaceLikeHomeLocation` | `(X=47750.0, Y=336370.0, Z=1500.0)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DataTablesSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_CharacterStatesDataTable` | `/Game/Dune/Characters/CharacterState/DT_CharacterStates.DT_CharacterStates` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CharacterSubstatesDataTable` | `/Game/Dune/Characters/CharacterState/DT_CharacterSubstates.DT_CharacterSubstates` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InteractionInputActionDataTable` | `/Game/Dune/Characters/Player/Interactions/DT_InteractionInputAction.DT_InteractionInputAction` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InteractionItemDataTable` | `/Game/Dune/Characters/Player/Interactions/DT_InteractionItem.DT_InteractionItem` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WeaponModDataTable` | `/Game/Dune/Weapons/CDT_WeaponsAndMods.CDT_WeaponsAndMods` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ItemsCraftingRecipesDataTable` | `/Game/Dune/Systems/Crafting/DT_ItemsCraftingRecipes.DT_ItemsCraftingRecipes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PostProcessCameraModifiersDataTable` | `/Game/Dune/Systems/PostProcess/DT_PostProcessCameraModifiersNames.DT_PostProcessCameraModifiersNames` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_AimAssistDataTable` | `/Game/Dune/Controller/DT_AimAssistDataTable.DT_AimAssistDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AimAssistAreaDataTable` | `/Game/Dune/Controller/DT_AimAssistAreaDataTable.DT_AimAssistAreaDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MeleeWeaponDataTable` | `/Game/Dune/Weapons/DT_MeleeWeaponDataTable.DT_MeleeWeaponDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InteractionDataTable` | `/Game/Dune/Characters/Player/Interactions/DT_Interactions.DT_Interactions` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InteractionKeyCodesDataTable` | `/Game/Dune/Characters/Player/Interactions/DT_InteractionKeyCodes.DT_InteractionKeyCodes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_FilmbooksDataTable` | `/Game/Dune/Characters/Player/Interactions/DT_Filmbooks.DT_Filmbooks` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CheatEngineSpawnerDataTable` | `/Game/Dune/Systems/CheatManager/DT_CheatSpawnerDataTable.DT_CheatSpawnerDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ScannableTypesDataTable` | `/Game/Dune/Systems/Scanner/Datatables/DT_ScannableTypes.DT_ScannableTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ScannableComponentsDataTable` | `/Game/Dune/Systems/Scanner/Datatables/DT_ScannableComponentTypes.DT_ScannableComponentTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ScannerTypesDataTable` | `/Game/Dune/Systems/Scanner/Datatables/DT_ScannerTypes.DT_ScannerTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ScannerDataTable` | `/Game/Dune/Systems/Scanner/Datatables/DT_Scanners.DT_Scanners` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ScannerModDataTable` | `/Game/Dune/Systems/Scanner/Datatables/DT_ScannerMods.DT_ScannerMods` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CraftingRecipeProductionTypesTable` | `/Game/Dune/Systems/Crafting/DT_CraftingProductionTypes.DT_CraftingProductionTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CommuninetChannelsDataTable` | `/Game/Dune/Systems/Communinet/Datatables/DT_CommuninetChannels.DT_CommuninetChannels` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CommuninetMessagesDataTable` | `/Game/Dune/Systems/Communinet/Datatables/DT_CommuninetMessages.DT_CommuninetMessages` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallCategoryDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallCategory.DT_MnemonicRecallCategory` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallLessonDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/CDT_MnemonicRecallLessons.CDT_MnemonicRecallLessons` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LootContainerActorsTable` | `/Game/Dune/Systems/Items/DT_LootContainerActorsTable.DT_LootContainerActorsTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LootDistributionSettingsTable` | `/Game/Dune/Systems/Looting/DT_LootDistributionSettings.DT_LootDistributionSettings` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PopupWidgetDataTable` | `/Game/Dune/GUI/Data/DT_PopupWidgetTable.DT_PopupWidgetTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InputUIDataTable` | `/Game/Dune/GUI/Data/DT_InputUITable.DT_InputUITable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InputContextDataTable` | `/Game/Dune/Input/CDT_InputContexts.CDT_InputContexts` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_InputActionDataTable` | `/Game/Dune/Input/CDT_InputActions.CDT_InputActions` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_FogRevealZoneDataTable` | `/Game/Dune/Systems/UiMap/FogOfWar/DataTables/DT_FogRevealZones.DT_FogRevealZones` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MapMarkerTypesDataTable` | `/Game/Dune/Systems/FullscreenMap/DataTables/FullscreenMapMarkers/CDT_FullscreenMapMarkers.CDT_Ful...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MapMarkerFiltersDataTable` | `/Game/Dune/Systems/FullscreenMap/DataTables/DT_MapMarkerFilters.DT_MapMarkerFilters` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CharacterTemplateDataTable` | `/Game/Dune/Systems/CharacterTemplate/CDT_CharacterTemplates.CDT_CharacterTemplates` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BasicInventoryDataTable` | `/Game/Dune/Systems/Items/CDT_InventoryItems.CDT_InventoryItems` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_CharacterCustomizationAssetsDataTable` | `/Game/Dune/Characters/Customization/DT_CharacterCustomizationAssets.DT_CharacterCustomizationAssets` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SecurityZonesDataTable` | `/Game/Dune/Systems/SecurityZones/DT_SecurityZones.DT_SecurityZones` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_SecurityZonesPvPOverrideDataTable` | `/Game/Dune/Systems/SecurityZones/DT_SecurityZones_PvPOverride.DT_SecurityZones_PvPOverride` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_VendorDataTable` | `/Game/Dune/Systems/Trading/DT_VendorTable.DT_VendorTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCConfigurationDataTable` | `/Game/Dune/AI/Config/CDT_NPCConfigs.CDT_NPCConfigs` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCBarksDataTable` | `/Game/Dune/AI/Config/DT_NPCBarks.DT_NPCBarks` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BotConfigurationDataTable` | `/Game/Dune/AI/Config/DT_Bot_Configs.DT_Bot_Configs` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_NPCCombatBehaviorSetDataTable` | `/Game/Dune/AI/Config/DT_Npc_CombatBehaviorSets.DT_Npc_CombatBehaviorSets` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCCombatAbilitiesDataTable` | `/Game/Dune/AI/Config/DT_Npc_CombatAbilities.DT_Npc_CombatAbilities` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LorePickupDataTable` | `/Game/Dune/Placables/DT_LorePickup.DT_LorePickup` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NpcCharacterCustomizationAssetsDataTable` | `/Game/Dune/Characters/Customization/DT_NpcCharacterCustomizationAssets.DT_NpcCharacterCustomizati...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_XPConstantsDataTable` | `/Game/Dune/Systems/Progression/DT_XPConstantsDataTable.DT_XPConstantsDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_XPEventsDataTable` | `/Game/Dune/Systems/Progression/DT_XPEventsDataTable.DT_XPEventsDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SkillsXPTable` | `/Game/Dune/Systems/Progression/SkillXPPerLevel.SkillXPPerLevel` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SkillsSpiceTable` | `/Game/Dune/Systems/Progression/SkillSpiceEffects.SkillSpiceEffects` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TrainingModuleDataTable` | `/Game/Dune/Systems/Progression/DT_TrainingModules.DT_TrainingModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SkillTreeBlockNameTable` | `/Game/Dune/Systems/Progression/DT_SkillTreeBlockNames.DT_SkillTreeBlockNames` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PerkDataTable` | `/Game/Dune/Systems/Progression/DT_Perks.DT_Perks` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TrainingModulePrereqTextTable` | `/Game/Dune/Systems/Progression/DT_TrainingModulePrereqText.DT_TrainingModulePrereqText` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ItemGiveItemsDataTable` | `/Game/Dune/Systems/Items/DT_ItemGiveItemsTable.DT_ItemGiveItemsTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TeleportLocationTable` | `/Game/Dune/Systems/CheatManager/DT_CheatTeleportLocations.DT_CheatTeleportLocations` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CharacterProgressCheckpointsTable` | `/Game/Dune/Systems/CheatManager/DT_CharacterProgressCheckpointsTable.DT_CharacterProgressCheckpoi...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallItemRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallItemRequirements.DT_MnemonicRecallItemReq...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallVehicleRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallVehicleRequirements.DT_MnemonicRecallVehi...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallBuildingRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallBuildingRequirements.DT_MnemonicRecallBui...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_MnemonicRecallActivityRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallActivityRequirements.DT_MnemonicRecallAct...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MutableArmorDataTable` | `/Game/Dune/Systems/Mutable/DT_CharacterMutable.DT_CharacterMutable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallWeaponRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallWeaponRequirements.DT_MnemonicRecallWeapo...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallMenuRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallMenuRequirements.DT_MnemonicRecallMenuReq...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_VelocityDamageDataTable` | `/Game/Dune/VelocityDamage/DT_VelocityDamageTable.DT_VelocityDamageTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CommuninetActionsDataTable` | `/Game/Dune/Systems/Communinet/Datatables/DT_CommuninetActions.DT_CommuninetActions` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WeaponModAnimationsTable` | `/Game/Dune/Animations/DT_WeaponModAnimationsTable.DT_WeaponModAnimationsTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DeathAnimationSettingsTable` | `/Game/Dune/Animations/DT_DeathAnimSettings.DT_DeathAnimSettings` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NoWeaponAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_NoWeapon.DT_AnimModes_NoWeapon` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_RifleAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_Rifle.DT_AnimModes_Rifle` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_OneHandedAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_OneHanded.DT_AnimModes_OneHanded` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_UnderslungAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_Underslung.DT_AnimModes_Underslung` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PistolAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_Pistol.DT_AnimModes_Pistol` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DewHarvestableTypeDataTable` | `/Game/Dune/Systems/Harvesting/Datatables/DT_DewHarvestableTypes.DT_DewHarvestableTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_FactionDataTable` | `/Game/Dune/Systems/Faction/Data/DT_FactionData.DT_FactionData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BuildableTierDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneBuildableTierData.DT_DuneBuildableTierData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildableSocketSetupDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneSocketSetupData.DT_DuneSocketSetupData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_FillableTypesDataTable` | `/Game/Dune/Systems/Items/DT_FillableTypes.DT_FillableTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ItemUsageLimitationGroupDataTable` | `/Game/Dune/Systems/Items/DT_ItemUsageLimitationGroups.DT_ItemUsageLimitationGroups` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BuildableSocketCostsDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneSocketCostsData.DT_DuneSocketCostsData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_ContainerLootTable` | `/Game/Dune/Systems/Looting/DT_ContainerLoot.DT_ContainerLoot` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_GameItemCategoryDataTable` | `/Game/Dune/Systems/Items/DT_GameItemCategories.DT_GameItemCategories` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_GameItemAudioCategoryDataTable` | `/Game/Dune/Systems/Items/DT_GameItemAudioCategories.DT_GameItemAudioCategories` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DuneExchangeNameDataTable` | `/Game/Dune/Systems/DuneExchange/DT_DuneExchangeNames.DT_DuneExchangeNames` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DuneExchangeRecurringOrdersDataTable` | `/Game/Dune/Systems/DuneExchange/DT_DuneExchangeRecurringOrders.DT_DuneExchangeRecurringOrders` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CameraContextDataTable` | `/Game/Dune/Systems/Camera/CDT_CameraContext.CDT_CameraContext` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CameraContextVehicleDataTable` | `/Game/Dune/Systems/Camera/DT_CameraContextVehicles.DT_CameraContextVehicles` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SandwormConfigurationDataTable` | `/Game/Dune/Creatures/Sandworm/Settings/DT_SandwormConfigDataTable.DT_SandwormConfigDataTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PentashieldSurfaceDataTable` | `/Game/Dune/Systems/Building/Data/DT_PentashieldSurfaceData.DT_PentashieldSurfaceData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCArchetypeStatsDataTable` | `/Game/Dune/AI/Config/DT_NPCArchetypeStats.DT_NPCArchetypeStats` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ContractItemsDataTable` | `/Game/Dune/Systems/Items/DT_ContractItems.DT_ContractItems` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ContractRewardItemsDataTable` | `/Game/Dune/Systems/Items/DT_ContractRewardItems.DT_ContractRewardItems` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LandsraadDecreesDataTable` | `/Game/Dune/Systems/Landsraad/DT_LandsraadDecrees.DT_LandsraadDecrees` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PainboxDialogueChoicesTable` | `/Game/Dune/Systems/CharacterCreation/DT_PainboxDialogueChoices.DT_PainboxDialogueChoices` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SoftBuildableUnlockableSetsDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableUnlockableSetsData.DT_BuildableUnlockableSetsData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_NPCSenseConfigurationDataTable` | `/Game/Dune/AI/Config/DT_NPCSensorConfigTable.DT_NPCSensorConfigTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallNPCRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallNPCRequirements.DT_MnemonicRecallNPCRequi...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ItemVolumeColorsDataTable` | `/Game/Dune/GUI/Data/DT_ItemVolumeColors.DT_ItemVolumeColors` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BuildableStabilizationGroupDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableStabilizationGroupData.DT_BuildableStabilizationGrou...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SecurityZoneGroupsDataTable` | `/Game/Dune/Systems/SecurityZones/DT_SecurityZoneGroups.DT_SecurityZoneGroups` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_AudioSwitchStateCharacterDataTable` | `/Game/Dune/Audio/DT_AudioSwitchStateCharacter.DT_AudioSwitchStateCharacter` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WeaponModAudioTable` | `/Game/Dune/Audio/DT_WeaponModAudio.DT_WeaponModAudio` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BuildableAudioCategoryDataTable` | `/Game/Dune/Audio/DT_BuildablesAudioCategories.DT_BuildablesAudioCategories` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SpiceFieldTypeDataTable` | `/Game/Dune/Systems/SpiceHarvesting/DT_SpiceFieldTypes.DT_SpiceFieldTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InteractionInputContextDataTable` | `/Game/Dune/Input/Interactions/DT_IMC_Interactions.DT_IMC_Interactions` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BuildableFactionDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableUiCategory.DT_BuildableUiCategory` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceablePlacementGroupDataTable` | `/Game/Dune/Systems/Building/Data/DT_PlaceablePlacementGroups.DT_PlaceablePlacementGroups` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_NPCMutablePartsDataTable` | `/Game/Dune/Systems/Mutable/DT_CharacterMutable.DT_CharacterMutable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCGeneticsPartLookDataTable` | `/Game/Dune/AI/Config/DT_NPCGeneticsLookParts.DT_NPCGeneticsLookParts` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCGeneticsLookDataTable` | `/Game/Dune/AI/Config/DT_NPCGeneticsLooks.DT_NPCGeneticsLooks` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCGeneticsPartOutfitDataTable` | `/Game/Dune/AI/Config/DT_NPCGeneticsOutfitParts.DT_NPCGeneticsOutfitParts` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCGeneticsOutfitDataTable` | `/Game/Dune/AI/Config/DT_NPCGeneticsOutfits.DT_NPCGeneticsOutfits` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PingMarkerTypesDataTable` | `/Game/Dune/Systems/PingSystem/DataTables/DT_PingMarkers.DT_PingMarkers` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MeleeAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_Melee.DT_AnimModes_Melee` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TutorialDataTable` | `/Game/Dune/GUI/Data/DT_TutorialContent_DEPRECATED.DT_TutorialContent_DEPRECATED` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TechTreeCategoryDataTable` | `/Game/Dune/Systems/TechKnowledge/Data/SDT_TechTreeCategories.SDT_TechTreeCategories` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DuneAiAttackSettings` | `/Game/Dune/AI/Config/DT_AiAttackSettings.DT_AiAttackSettings` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DamageSystemStaticsDataTable` | `/Game/Dune/Systems/DamageSystem/DT_DamageSystemStatics.DT_DamageSystemStatics` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InfoRingErrorMessageDataTable` | `/Game/Dune/GUI/Data/DT_InfoRingErrorMessageList.DT_InfoRingErrorMessageList` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_FrameTypeToWeaponClassDataTable` | `/Game/Dune/Weapons/DT_WeaponFrameToDamageModifier.DT_WeaponFrameToDamageModifier` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallPlayerStatRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallPlayerStatRequirements.DT_MnemonicRecallP...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MnemonicRecallSkillRequirementDataTable` | `/Game/Dune/Systems/MnemonicRecall/Data/DT_MnemonicRecallSkillRequirements.DT_MnemonicRecallSkillR...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_IntelDistributionSettingsTable` | `/Game/Dune/Systems/TechKnowledge/Data/DT_IntelDistributionSettings.DT_IntelDistributionSettings` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SurveyProbeConfigDataTable` | `/Game/Dune/GUI/Widgets/HUD/ProbeLauncher/DT_SurveyProbeConfiguration.DT_SurveyProbeConfiguration` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SurveyStateDataTable` | `/Game/Dune/GUI/Widgets/HUD/ProbeLauncher/DT_SurveyProgressState.DT_SurveyProgressState` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BuildableUiCategoryDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableUiCategory.DT_BuildableUiCategory` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_CutterayDataTable` | `/Game/Dune/Systems/Harvesting/Datatables/DT_Cutterays.DT_Cutterays` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TwoHandHeadAnimationModesTable` | `/Game/Dune/Animations/DT_AnimModes_TwoHandHead.DT_AnimModes_TwoHandHead` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_HarvestWaterPotentialDataTable` | `/Game/Dune/Systems/Harvesting/Datatables/DT_HarvestWaterPotential.DT_HarvestWaterPotential` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NotificationSettingsDataTable` | `/Game/Dune/Systems/Notifications/DT_Notifications.DT_Notifications` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_IconPresetWidgetDataTable` | `/Game/Dune/GUI/Data/DT_IconPreset.DT_IconPreset` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ActorDiegeticDataTable` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Diegetic/DT_ActorDiegeticUIData.DT_ActorDiegeticUIData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_BuildableStructureCategoryDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableStructureCategoryData.DT_BuildableStructureCategoryData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_TextChatChannelTypeDataTable` | `/Game/Dune/Systems/Chat/DT_TextChatChannelTypes.DT_TextChatChannelTypes` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ChatSettingsDataTable` | `/Game/Dune/Systems/Chat/DT_ChatSettings.DT_ChatSettings` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ShortCommandsDataTable` | `/Game/Dune/Systems/ShortCommands/DT_ShortCommands.DT_ShortCommands` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DiegeticGuiSetupDataTable` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Diegetic/DT_DiegeticGuiSetup.DT_DiegeticGuiSetup` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_LootTablesDirectory` | `(Path="Dune/Systems/LootTables")` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SkillDistributionSettingsTable` | `/Game/Dune/Placables/DT_SkillPickup.DT_SkillPickup` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_HarvestNodeEfficiencyDataTable` | `/Game/Dune/Systems/Harvesting/Datatables/DT_HarvestNodeEfficiency.DT_HarvestNodeEfficiency` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ItemCraftedMapsDataTable` | `/Game/Dune/Systems/Items/DT_ItemTableCraftableMaps.DT_ItemTableCraftableMaps` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TechTreeGroupDataTable` | `/Game/Dune/Systems/TechKnowledge/Data/DT_TechTreeGroups.DT_TechTreeGroups` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CraftingRecipeProductionContextTypesTable` | `/Game/Dune/Systems/Crafting/DT_CraftingProductionContextTypes.DT_CraftingProductionContextTypes` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_LoreObjectDataTable` | `/Game/Dune/Placables/DT_LoreObject.DT_LoreObject` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_StaticLocationDataTable` | `/Game/Dune/Systems/FullscreenMap/DataTables/CDT_StaticLocationData.CDT_StaticLocationData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_NPCHazardAreaResponseBehaviorSetDataTable` | `/Game/Dune/AI/Config/DT_Npc_HazardAreaResponseSets.DT_Npc_HazardAreaResponseSets` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SpecialReferenceItemCostsDataTable` | `/Game/Dune/Systems/Crafting/DT_SpecialReferenceItemCosts.DT_SpecialReferenceItemCosts` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ItemSinkchartsDataTable` | `/Game/Dune/Systems/Items/DT_ItemTableSinkcharts.DT_ItemTableSinkcharts` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AnimWeaponTemplatesDataTable` | `/Game/Dune/Animations/DT_AnimWeaponTemplates.DT_AnimWeaponTemplates` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MapInfoDataTable` | `/Game/Dune/Maps/CDT_MapsInfo.CDT_MapsInfo` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LandsraadHouseDataTable` | `/Game/Dune/Systems/Landsraad/DT_LandsraadHouses.DT_LandsraadHouses` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TierRepairReferenceItemCostsDataTable` | `/Game/Dune/Systems/Crafting/DT_TierRepairReferenceItemCosts.DT_TierRepairReferenceItemCosts` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TierRecycleReferenceItemCostsDataTable` | `/Game/Dune/Systems/Crafting/DT_TierRecycleReferenceItemCosts.DT_TierRecycleReferenceItemCosts` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BuildableStructureCategoryComposedLimitsDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableStructureComposedLimitsData.DT_BuildableStructureCom...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildableMapRegionDataTable` | `/Game/Dune/Systems/Building/Data/DT_BuildableMapRegion.DT_BuildableMapRegion` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_EconomyRewardsDataTable` | `None` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DoorDataTable` | `/Game/Dune/Systems/Building/Data/DT_PlaceableDoorData.DT_PlaceableDoorData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MTXCurrencyDataTable` | `/Game/Dune/GUI/Data/MTX/DT_MTXCurrencyData.DT_MTXCurrencyData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CurrencyDataTable` | `/Game/Dune/Systems/Currency/DT_Currencies.DT_Currencies` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_StaticSpawnLocationDefinitionTable` | `/Game/Dune/Systems/Spawning/CDT_StaticSpawnLocationDefinitions.CDT_StaticSpawnLocationDefinitions` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WeaponStatDataTable` | `/Game/Dune/Systems/DamageSystem/DT_WeaponStats.DT_WeaponStats` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DamageMitigationDataTable` | `/Game/Dune/Systems/DamageSystem/DT_DamageMitigations.DT_DamageMitigations` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ArmorStatDataTable` | `/Game/Dune/Systems/DamageSystem/DT_ArmorStats.DT_ArmorStats` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ItemStatDataTable` | `/Game/Dune/Systems/DamageSystem/DT_ItemStats.DT_ItemStats` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AugmentItemDataTable` | `/Game/Dune/Systems/Items/DT_ItemTable_Augments.DT_ItemTable_Augments` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ModifiableItemStatDataTable` | `/Game/Dune/Systems/DamageSystem/DT_ModifiableItemStats.DT_ModifiableItemStats` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LandsraadContractsDailyBonusDataTable` | `/Game/Dune/Systems/Landsraad/DT_LandsraadContractsDailyBonus.DT_LandsraadContractsDailyBonus` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_PlaceableCustomizationGroupDataTable` | `/Game/Dune/Systems/Building/Data/PlaceableData/DT_PlaceableCustomizationGroup.DT_PlaceableCustomi...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_LandsraadControlPointDataTable` | `/Game/Dune/Systems/Landsraad/DT_LandsraadControlPointData.DT_LandsraadControlPointData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[ItemModsSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `ItemModsCDTTableName` | `/Game/Dune/Weapons/CDT_WeaponsAndMods.CDT_WeaponsAndMods` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.DuneAudioSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_FlyByRadius` | `300.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_GlobalPreloadEvents` | `BlueprintGeneratedClass'/Game/Dune/Audio/BP_PreloadedAudioEventsGlobal.BP_PreloadedAudioEventsGlo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GlobalSettings` | `BlueprintGeneratedClass'/Game/Dune/Audio/BP_AudioSettings.BP_AudioSettings_C'` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/FcAudio.FcAudioSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SurfaceTypeMap` | `/Game/Dune/Audio/BP_SurfaceTypeAudioMap.BP_SurfaceTypeAudioMap_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultTraceCollisionChannel` | `ECC_GameTraceChannel15` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ReverbSettings` | `/Game/Dune/Audio/Settings/BP_ReverbSettings.BP_ReverbSettings_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShelteredSettings` | `/Game/Dune/Audio/Settings/BP_ShelteredSettings.BP_ShelteredSettings_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AmbientSettings` | `/Game/Dune/Audio/Settings/BP_ProceduralEnvironmentSettings.BP_ProceduralEnvironmentSettings_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultAudioEnvironment` | `None` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_bCreateAudioEventsInSameFolderAsAkEvents` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DefaultFcAudioEventsDirectory` | `(Path="/Game/Dune/Audio/DuneEvents")` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_FcAudioEventsDirectoryOverridePerAssetNameMatch` | `(("vod_*", (DirectoryPath=(Path="/Game/Dune/Audio/DuneEvents/VODialogue"))))` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WwiseSoundBanksImportDirectory` | `(Path="X:/IntermediateExportFolder")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_EditorSpatialAudioPreviewMaterial` | `/Game/Dune/Audio/EditorMaterials/M_SpatialAudioPreview.M_SpatialAudioPreview` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_EditorAudioSplinePreviewMaterial` | `/Game/Dune/Audio/EditorMaterials/M_SpatialAudioPreview.M_SpatialAudioPreview` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_HighQualityOcclusionForRadius` | `150.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/AkAudio.AkAndroidInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(SampleRate=48000,MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolS...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=0,Notificati...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(AudioAPI=3,RoundFrameSizeToHardwareSize=True,EnableMultiCoreRendering=False,IO_MemorySize=209715...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkLinuxInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(SampleRate=48000,MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolS...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=0,Notificati...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(EnableMultiCoreRendering=False,IO_MemorySize=2097152,TargetAutoStreamBufferLength=380.000000,Use...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkLuminInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(SampleRate=48000,MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolS...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=0,Notificati...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(EnableMultiCoreRendering=False,IO_MemorySize=2097152,TargetAutoStreamBufferLength=380.000000,Use...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkMacInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(SampleRate=48000,MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolS...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=0,Notificati...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(EnableMultiCoreRendering=False,IO_MemorySize=2097152,TargetAutoStreamBufferLength=380.000000,Use...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkPS4InitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolSize=134217728,Mem...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=0,Notificati...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(ACPBatchBufferSize=0,UseHardwareCodecLowLatencyMode=False,EnableMultiCoreRendering=False,IO_Memo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkSwitchInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(SampleRate=48000,MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolS...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=24025,NotificationPort=24026,NetworkNam...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(EnableMultiCoreRendering=False,IO_MemorySize=2097152,TargetAutoStreamBufferLength=380.000000,Use...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkWindowsInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(SampleRate=48000,MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolS...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=0,Notificati...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(UseHeadMountedDisplayAudioDevice=False,MaxSystemAudioObjects=128,EnableMultiCoreRendering=True,M...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AkAudio.AkXboxOneInitializationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `CommonSettings` | `(MaximumNumberOfMemoryPools=256,MaximumNumberOfPositioningPaths=255,DefaultPoolSize=134217728,Mem...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ApuHeapSettings` | `(CachedSize=67108864,NonCachedSize=0)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CommunicationSettings` | `(InitializeSystemComms=True,PoolSize=262144,DiscoveryBroadcastPort=24024,CommandPort=24025,Notifi...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AdvancedSettings` | `(ShapeDefaultPoolSize=0,MaximumNumberOfXMAVoices=128,UseHardwareCodecLowLatencyMode=False,EnableM...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.SpiceHarvestingSystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_PrimeRateInSeconds` | `30.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ManagerTickRateInSeconds` | `5.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ManagerRequestRefreshRateInSeconds` | `90.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_GlobalManagerRequestRefreshRateInSeconds` | `120.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_bPlayerMustWitnessBloom` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bEnableSpiceBloomLongRangeReplication` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bEnableSpiceFieldLongRangeReplication` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_NodeValueToSpiceResourceRatio` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PerMapSystemSettings` | `(("Editor_Default", (m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=10,MaxGlobally...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultSystemSettings` | `(m_SpiceFieldTypeSettings=(((Name="Small"), (MaxGloballyPrimed=6,MaxGloballyActive=3)),((Name="Me...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bSpawningActive` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[/Script/DuneSandbox.SpiceHarvestingSystemIgw]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MaxWaitTimeForIgwQuery` | `2.0` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SpiceFieldSmallClass` | `/Game/Dune/Systems/SpiceHarvesting/BP_SpiceField_Small.BP_SpiceField_Small_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SpiceFieldMediumClass` | `/Game/Dune/Systems/SpiceHarvesting/BP_SpiceField_Medium.BP_SpiceField_Medium_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.FlourSandSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_FlourSandFieldsActivePercentage` | `1.0` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.CommuninetSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_InitialCommuninetActiveState` | `True` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_InitialCommuninetSelectedChannel` | `(Name="TunedChannels")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_InitialCommuninetChannels` | `7 entries; first \`(Name="WeatherChannel")\`` | 7 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_InitialTunnedChannels` | `7 entries; first \`(Name="WeatherChannel")\`` | 7 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TuningGridRowsCount` | `4` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TuningGridColumnsCount` | `4` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultChatMessageId` | `(Name="Chat")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TestClickableMessage` | `(Name="TestClickableMessage")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TestMessageWithData` | `(Name="TestMapMarkerMessage")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TestClickableMessageMarkerType` | `(Name="Objective")` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CantPlaceBuildableMessage` | `(Name="CantPlaceBuildable")` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_P2pTradeRequestMessage` | `(Name="P2pTradingRequest")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DeliveryConfirmationMessage` | `(Name="DeliveryConfirmationMessage")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SeekerLostMessage` | `(Name="SeekerLost")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_P2pTradeRequestSentMessage` | `(Name="P2pTradingRequestSent")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractContactIssuerMessage` | `(Name="ContractContactIssuerMessage")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractNewContractMessage` | `(Name="ContractNewContractMessage")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RadioStationRangeEnteredMessage` | `(Name="RadioStationRangeEnteredMessage")` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_EventLogMessageId` | `(Name="EventLogMessage")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.HydrationSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_HydrationSystemSettings` | `/Game/Dune/Systems/Hydration/DA_HydrationSystemSettings.DA_HydrationSystemSettings` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bHydrationEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BiomeTierUpdateRateSeconds` | `2.5` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |

## `[/Script/DuneSandbox.DewHarvestSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DewRefreshTime` | `12.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DewRefreshTimeNPE` | `300.0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DewTargetSocket` | `wpn_Melee_02` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_InteractionPromptHasNoFillable` | `NSLOCTEXT("[/Script/DuneSandbox]", "3E807C7E40C5840CE2A470AB055985CE", "LOC_Drink")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_InteractionPromptHasFillable` | `NSLOCTEXT("[/Script/DuneSandbox]", "380E1E9F4E933249DB753FB3897F4FA8", "LOC_Harvest")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_HandHarvestInteraction` | `BlueprintGeneratedClass'/Game/Dune/Characters/Player/Interactions/Objects/BP_HandHarvestWaterBear...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.MnemonicRecallSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_JourneyCategories` | `((Story, (m_Category=Story,m_DisplayName=LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.AdminPanelWidget]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_TeleportToLocations` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/Mercuna.MerSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `DebugLengthScale` | `1000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bAlwaysShowErrors` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `+ModifierUsageTypes` | `ClosedDoor` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `GroundAgentTypes` | `(("StandardHumanoid", (MaxSlopeAngle=50.000000,StepHeight=45.000000)),("Vehicle", (Category=Vehic...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SurfaceAgentTypes` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bAutoLinkNavVolumesWithGraphs` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `GeometryCollectionTimePerFrame` | `0.002000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SingleThreadedJobTimePerFrame` | `0.010000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bIgnoreStepForHeightClearance` | `False` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `bWarnIfSubLevelNavGraphsNotBuiltInPersistentLevel` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bAllowNavGraphMerging` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `OctreeCellSize` | `80.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MinPawnRadius` | `1` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MaxPawnRadius` | `3` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.DuneVoxelWorld]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SpawnOnlyEveryNodeDivisibleBy` | `1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.BuildingSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SoftBuildingDataTable` | `/Game/Dune/Systems/Building/Data/CDT_BuildingData.CDT_BuildingData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftPlaceableDataTable` | `/Game/Dune/Systems/Building/Data/CDT_PlaceableData.CDT_PlaceableData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftBuildableGroupDataTable` | `/Game/Dune/Systems/Building/Data/CDT_BuildableGroupData.CDT_BuildableGroupData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftBuildableVehicleGroupDataTable` | `/Game/Dune/Systems/Building/Data/BuildableGroupData/DT_BuildableGroupData_Vehicle.DT_BuildableGro...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftBuildableCategoryDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneBuildableUiSubcategory.DT_DuneBuildableUiSubcategory` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftTotemDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneTotemData.DT_DuneTotemData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftBuildingBlueprintDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneBuildingBlueprintData.DT_DuneBuildingBlueprintData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftStilltentDataTable` | `/Game/Dune/Systems/Building/Data/DT_DuneStilltentData.DT_DuneStilltentData` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SoftBuildableDamageMitigationGroupDataTable` | `/Game/Dune/Systems/Building/Data/BuildableGroupData/DT_BuildableDamageMitigationGroupData.DT_Buil...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SoftFabricatorSettingsDataTable` | `/Game/Dune/Systems/Crafting/Data/DT_FabricatorSettings.DT_FabricatorSettings` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SoftBloodPlaceableSettingsDataTable` | `/Game/Dune/Systems/Building/Data/PlaceableData/DT_PlaceableBlood_Settings.DT_PlaceableBlood_Settings` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |

## `[/Script/DuneSandbox.DunePlaceableBase]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_NoAccessPlaceableDiegetic` | `(Name="NoAccessPlaceableDiegetic")` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |

## `[/Script/DuneSandbox.DiegeticGuiSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ActorDiegeticWidgetComponentClassSoftPtr` | `WidgetBlueprintGeneratedClass'/Game/Dune/GUI/Widgets/Menus/Gameplay/Diegetic/BP_ActorDiegeticWidg...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/AkAudio.AkSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `MaxSimultaneousReverbVolumes` | `4` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `WwiseProjectPath` | `(FilePath="X:/Seabass_WwiseProject/Seabass_WwiseProject.wproj")` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `RootOutputPath` | `(Path="Dune/Audio/GeneratedSoundBanks")` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `bAlwaysUseConsoleCommandToGenerateSoundBanks` | `True` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `bAllowWwiseProjectChanges` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bLoadProjectDatabaseAsync` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bAllowInitializeAudioWhenAppDoesntRenderAudio` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `WwiseStagingDirectory` | `(Path="Dune/Audio/WwiseStaging")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bSoundBanksTransfered` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bAssetsMigrated` | `True` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `bProjectMigrated` | `True` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `DefaultOcclusionCollisionChannel` | `ECC_Visibility` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DefaultFitToGeometryCollisionChannel` | `ECC_WorldStatic` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AkGeometryMap` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DefaultAcousticTexture` | `/Game/Dune/Audio/Virtual_Acoustics/AcousticTextures/Default.Default` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `DefaultTransmissionLoss` | `0.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `GeometrySurfacePropertiesTable` | `/Game/Dune/Audio/DT_DefaultGeometrySurfacePropertiesTable.DT_DefaultGeometrySurfacePropertiesTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `GlobalDecayAbsorption` | `0.500000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DefaultReverbAuxBus` | `None` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `EnvironmentDecayAuxBusMap` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ReverbAssignmentTable` | `/Game/Dune/Audio/DT_DefaultReverbAssignmentTable.DT_DefaultReverbAssignmentTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `HFDampingName` | `` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DecayEstimateName` | `` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `TimeToFirstReflectionName` | `` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HFDampingRTPC` | `None` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DecayEstimateRTPC` | `None` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `TimeToFirstReflectionRTPC` | `None` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AudioInputEvent` | `None` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `SplitSwitchContainerMedia` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SplitMediaPerFolder` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `UseEventBasedPackaging` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `UnrealCultureToWwiseCulture` | `(("en", "English(US)"))` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DefaultAssetCreationPath` | `/Game/Dune/Audio` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `InitBank` | `/Game/Dune/Audio/InitBank.InitBank` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AudioRouting` | `EnableWwiseOnly` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `bWwiseSoundEngineEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bWwiseAudioLinkEnabled` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bAkAudioMixerEnabled` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `DefaultListenerScalingFactor` | `1.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MigratedEnableMultiCoreRendering` | `True` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `FixupRedirectorsDuringMigration` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.CraftingSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_EquipmentMeshDisplayObjectInstance` | `/Game/Dune/Systems/Crafting/COI_EquipmentPreview.COI_EquipmentPreview` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_IPoseAnimation` | `/Game/Dune/Animations/Humans/Common/NoWeapon/Misc/Poses/A_Human_IPose_01.A_Human_IPose_01` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CraftingRepairItemCostData` | `/Game/Dune/Systems/Crafting/DA_CraftingItemRepairCostData.DA_CraftingItemRepairCostData` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_CraftingRecycleItemCostData` | `/Game/Dune/Systems/Crafting/DA_CraftingItemRecycleCostData.DA_CraftingItemRecycleCostData` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RecycleJackpotAudioEvent` | `/Game/Dune/Audio/DuneEvents/Default/AD_RecycleJackpot.AD_RecycleJackpot` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_EquipmentSlotBoundsMap` | `((Head, (Origin=(X=0.000000,Y=0.000000,Z=170.000000),BoxExtent=(X=22.000000,Y=22.000000,Z=22.0000...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_CraftingCostMultiplierPerItemType` | `2 entries; first \`(m_ItemFilter=(TokenStreamVersion=0,TagDictionary=((TagName="Items....\`` | 2 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `+m_CraftingOutputMultiplierPerItemType` | `(m_ItemFilter=(TokenStreamVersion=0,TagDictionary=((TagName="Items.Consumables.Repair"),(TagName=...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `+m_CraftingOutputMultiplierPerRecipeList` | `5 entries; first \`(m_RecipeMultipliers=(((Name="IronBarRecipe"), (LevelToMultiplierLi...\`` | 5 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaximumNumberOfCharges` | `999` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_UniqueChargesFromCheat` | `100` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MaximumNumberOfRequestsPerRecipe` | `1000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultRequestsQueueLength` | `6` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CostCheatMaxRecipes` | `500` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ListenResourcesResponseLimit` | `100` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ListenResourcesRequestCooldownTime` | `5.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaxItemMeshDisplayScale` | `1.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_UICameraTransitionTime` | `0.600000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_RepairCostWeight` | `0.500000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RecyclerOutputWeight` | `0.250000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CraftingGenericItemMesh` | `/Game/Dune/Weapons/2H/Choam/Scattergun_01/Meshes/Weapon_Modules/SM_Wpn_2H_Choam_Scattergun_01_Amm...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ItemTiers` | `((Plastanium, (m_Name=LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `BaseResourcesCacheFlushHighPriorityTimer` | `0.500000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `BaseResourcesCacheFlushLowPriorityTimer` | `3.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaxArraySerializationSize` | `500` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.DuneVehicleSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_VehicleTemplateDataTable` | `/Game/Dune/Systems/Vehicles/DT_VehicleTemplates.DT_VehicleTemplates` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableBaseModules` | `/Game/Dune/Systems/Vehicles/CDT_BaseVehicleModules.CDT_BaseVehicleModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableModuleSubTypes` | `/Game/Dune/Systems/Vehicles/DT_VehicleModuleSubTypes.DT_VehicleModuleSubTypes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableModuleInfoCards` | `/Game/Dune/Systems/Vehicles/DT_VehicleModuleInfoCards.DT_VehicleModuleInfoCards` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleBoostModules` | `/Game/Dune/Systems/Vehicles/DT_VehicleBoostModules.DT_VehicleBoostModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleHarnessModules` | `/Game/Dune/Systems/Vehicles/DT_VehicleHarnessModules.DT_VehicleHarnessModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehiclePowerModules` | `/Game/Dune/Systems/Vehicles/DT_VehiclePowerModules.DT_VehiclePowerModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleWeaponModules` | `/Game/Dune/Systems/Vehicles/DT_VehicleWeaponModules.DT_VehicleWeaponModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleAbilityItems` | `/Game/Dune/Systems/Items/DT_ItemTableVehicleAbilities.DT_ItemTableVehicleAbilities` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleShieldModules` | `/Game/Dune/Systems/Vehicles/DT_VehicleShieldModules.DT_VehicleShieldModules` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleCollisionDamage` | `/Game/Dune/Systems/Vehicles/DT_VehicleCollisionDamage.DT_VehicleCollisionDamage` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DataTableVehicleSchematics` | `/Game/Dune/Systems/Vehicles/DT_VehicleSchematics.DT_VehicleSchematics` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ModulePreviewMaterial` | `/Game/Dune/Systems/Building/Materials/M_BuildBlueprintBrush.M_BuildBlueprintBrush` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CustomDepthStencilValue` | `4` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_VehicleAccessTokenDuration` | `120.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_VehicleFuelCellFillableType` | `(Name="Fuel")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LastDamageDealtTimeThreshold` | `1.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_OrnithopterInAirDistanceToGround` | `300.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RecoveryPerVehicleClassCurrencyMultipliers` | `(("/Game/Dune/Systems/Vehicles/Blueprints/GroundVehicles/BP_Sandbike_CHOAM.BP_Sandbike_CHOAM_C", ...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_VehicleRecoveryCurrency` | `(Name="Solaris")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_VehicleStatsSkippedWhenSleeping` | `2 entries; first \`CurrentTemperature\`` | 2 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.AbilityUIEventSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_VehicleHarvestingAbilityClass` | `/Game/Dune/Abilities/Vehicles/VehicleHarvesting_Toggle_Ability.VehicleHarvesting_Toggle_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CruiseModeToggleAbilityClass` | `/Game/Dune/Abilities/Vehicles/CruiseMode_Toggle_Ability.CruiseMode_Toggle_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_OrnithopterBoostToggleAbilityClass` | `/Game/Dune/Abilities/Vehicles/Ornithopter_Boost_Toggle_Ability.Ornithopter_Boost_Toggle_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_OrnithopterLasgunTriggerAbilityClass` | `/Game/Dune/Abilities/Vehicles/Ornithopter_Lasgun_Trigger_Ability.Ornithopter_Lasgun_Trigger_Abili...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WheeledVehicleBoostAbilityClass` | `/Game/Dune/Abilities/Vehicles/WheeledVehicle_Boost_Ability.WheeledVehicle_Boost_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_HarnessModeHeldAbilityClass` | `/Game/Dune/Abilities/Vehicles/HarnessMode_Held_Ability.HarnessMode_Held_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_VehicleBoostAbilityClass` | `/Game/Dune/Abilities/Vehicles/Vehicle_Boost_Held_Ability.Vehicle_Boost_Held_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_VehicleThrusterAbilityClass` | `/Game/Dune/Abilities/Vehicles/Vehicle_Thruster_Toggle_Ability.Vehicle_Thruster_Toggle_Ability_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.BiomeSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SandBuildupMultiplier` | `1.0` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.TimeOfDaySettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultBiomeConfiguration` | `/Game/Dune/Systems/DayNightCycle/Biomes/Default/DefaultBiomeModifier.DefaultBiomeModifier` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_StartTime` | `12.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bTimeOfDayEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DayLengthMinutes` | `30.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AzimuthInDegrees` | `55.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SunriseInDegrees` | `180.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterCustomizationTimeOfDay` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_StartingExperienceTimeOfDay` | `8.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AuroraProbability` | `25` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/DeteriorationSystem.ItemDeteriorationConstants]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `UpdateRateInSeconds` | `1.0` | 1 | Known | Item deterioration update cadence. Shipped setup says 0 disables deterioration. |

## `[/Script/DuneSandbox.SandwormSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_EnableSandwormSystem` | `UseAllowList` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_SpawningAllowedBaseMapList` | `2 entries; first \`(Name="HaggaBasin")\`` | 2 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bGenerateTerritoriesFromHeatMap` | `True` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_SandwormTerritoriesHeatMaps` | `(("Arrakis", "/Game/Dune/Tools/HeatmapTool/Baking/Sandworm_Territories/BP_Sandworm_Territories_He...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SandwormTerritoryGridX` | `1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SandwormTerritoryGridY` | `1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TerritoryBorderReduction` | `(X=1000.000000,Y=1000.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MinDistanceBetweenSandworms` | `80000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SummonHeight` | `-5000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SandwormPawnClass` | `/Game/Dune/Creatures/Sandworm/Sandworm_Arrakis/BP_Crea_SandwormArrakis.BP_Crea_SandwormArrakis_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SandwormControllerClass` | `/Script/DuneSandbox.SandwormAIController` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DamageTypeClass` | `/Script/DuneSandbox.DamageTypeSandworm` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DangerZoneDamageTypeClass` | `/Game/Dune/Weapons/Blueprints/DamageTypes/BP_DmgType_Physical.BP_DmgType_Physical_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SafezoneAttackAnimationBlockingDistance` | `60000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `ThreatScale` | `1.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `RoamingSettings` | `(ElevationUpdateFrequency=1.000000,SoftBorders=15000.000000,BorderRepulsionFactor=0.200000,Roamin...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultRoamingElevation` | `-4000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bEnableDebugInfoReplication` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DebugInfoReplicationFrequency` | `5.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_bEnableDangerZones` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DangerZonesCooldown` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_SyncTargetIntervalSeconds` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `UpdateTargetTimeSeconds` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_bGenerateDisplacementDuringAnimations` | `False` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaximumTargetHeight` | `5000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MinimumTargetHeight` | `-2000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_UnstuckTimer` | `3.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_UnstuckDistance` | `1500.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bEnableHibernation` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `PlayerShootingRecoilThreatFactor` | `1.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `NPCShootingRecoilThreatFactor` | `1.650000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PlayerVehicleShootingThreatFactor` | `1.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `NPCVehicleShootingThreatFactor` | `1.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_TagsAffectingUncappedThreat` | `3 entries; first \`(TagName="CharacterState.Substate.Dashing")\`` | 3 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ThreatGeneratedPerSpiceHarvestedMap` | `(((Name="Large"), 0.500000),((Name="Medium"), 0.500000),((Name="Medium_RedDesert"), 0.500000),((N...` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_SpiceBlobLifespan` | `420.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HarvestSpicePickupThreatUnit` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HarvestSpiceCoalesceThreatUnit` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HarvestFlourSandPickupThreatUnit` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HarvestFlourSandCoalesceThreatUnit` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DefaultMaxThreatScore` | `5000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MaxThreatInSafezone` | `0.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `InitialThreatRate` | `0.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_RealTargetPickupRange` | `60000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `EnableBuildingThreatGeneration` | `True` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_CurveDistanceFromSandwormToThreatFactor` | `/Game/Dune/Creatures/Sandworm/Settings/ThreatSystem/Worm_DistanceFromSandwormToThreatFactor.Worm_...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `ThreatDecreasingValuePerSec` | `0.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AirborneThreatDecreasingValuePerSec` | `100.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `WalkingThreatPerSec` | `15.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `WWoRThreatPerSec` | `5.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `RunningThreatPerSec` | `20.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SprintingThreatPerSec` | `20.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CrouchingThreatPerSec` | `15.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SuspendingThreatPerSec` | `200.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DashingThreatPerSec` | `90.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ShieldingThreatPerSec` | `500.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DrumsandThreatPerSec` | `200.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `VehicleShieldingThreatPerSec` | `50.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HyperSprintingThreatPerSec` | `90.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ThreatDecreaseCooldownInSeconds` | `5.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_FootStepThreatWaveAmplitude` | `0.300000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_HighActivityThreatMeterDistanceFromSandworm` | `50000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_HighActivityThreatMeterUpdateFrequency` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaximumThreatBlobHeight` | `1000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MinimumThreatBlobHeight` | `-1000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DecreasingValuePerSecond` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SandwormThreatSystemSettings` | `(ThreatBlobTypeIsHighPrioMap=((ValuableDesertWreck, True),(Character, True),(Group, True),(Thumpe...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DesertWreckThreatValuePerVehicleMap` | `((Sandbike, 500.000000),(Sandcrawler, 500.000000),(LightOrnithopter, 500.000000),(HeavyOrnithopte...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TimeToDropWreckBlobPerVehicleMap` | `((Sandbike, 7200.000000),(Sandcrawler, 7200.000000),(LightOrnithopter, 7200.000000),(HeavyOrnitho...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DesertWreckBlobUpdateFrequency` | `3.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaxDistanceFromDesertWreckBlob` | `1000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TimeForRecentTraces` | `1.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TimeToStopEnrage` | `60.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TimeToStopThumperEnrage` | `60.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TimeToCountThumpersForThumperEnrage` | `300.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_NumberOfThumpersEatenForThumperEnrage` | `3` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bOnTargetedBySandwormCommuninetMessageEnabled` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_OnTargetedBySandwormCommuninetMessage` | `(Name="OnTargetedBySandworm")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bUseTerrainSampling` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_SandLandscapeMaterialInstance` | `/Game/Dune/Environment/Landscape/Materials/MI_Landscape_Arrakis_SoS.MI_Landscape_Arrakis_SoS` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DefaultSafezoneExpansionOffset` | `3000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BiggerSafezoneConvexHullsExpansionOffset` | `1800.000000` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DefaultSafezoneSampleStride` | `5000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CurveSafezoneAreaToSampleStride` | `/Game/Dune/Creatures/Sandworm/Settings/SafezoneSystem/SafezoneAreaToSampleStrideCurve.SafezoneAre...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SafezoneSubdivisionGridX` | `3` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SafezoneSubdivisionGridY` | `3` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DangerZoneUpdateFrequency` | `6` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `+m_PostSandwormDeathItemsGranted` | `(TemplateId=(Name="WormTooth"),Quantity=1,Durability=1.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SandwormStareObserverRadius` | `1000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bGiantWormSystemEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_GiantWormSpawningUpdateFrequency` | `60.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_GiantWormSpawningCooldown` | `7200.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_GiantWormSequenceClass` | `/Game/Dune/Systems/Sandworm/GiantWorm/BP_GiantWormSequence.BP_GiantWormSequence_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_GiantWormSafezoneDetectionDistance` | `35000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_GiantWormSequenceLifespan` | `78.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GiantWormSequencePlayDelay` | `30.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_GiantWormSpiceFieldType` | `(Name="Large")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GiantWormMinimumSpiceAmountHarvested` | `50000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_GiantWormMinimumPlayersOnSpiceField` | `4` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GiantWormMinimumDistanceFromIgwBoundary` | `2000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ThreatBlobDurabilityOutsideHeightRequirements` | `15.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.DuneAISettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DynamicNavSettings` | `(NavGridVolumeUpperLimit=100000.000000,NavGridVolumeLowerLimit=-50000.000000,AllowedAgentTypes=("...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MaxReinforcementSize` | `150.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_NavigableLocationSearchRadius` | `300.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ReinforcementHeightAboveGround` | `1000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MinAttackDelayTime` | `0.200000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaxAttackDelayTime` | `5.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_AttributeModEffect` | `None` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AttributeModEffectByLOD` | `/Game/Dune/AI/Shared/GameplayEffects/GE_NPCAttributeMods_ByLOD.GE_NPCAttributeMods_ByLOD_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultBehaviorStateDecisionSet` | `/Game/Dune/AI/ConsiderationSystem/DecisionSets/BP_DecisionSet_NpcBehaviorState_Default.BP_Decisio...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AiCombatSettings` | `(m_NpcWeaponUserConfigs=(((Name="Fireballer_NPC"), (m_VerticalAimOffsetByDistanceCurve=/Script/En...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AiLODSettings` | `(m_EntityLod0Radius=3750.000000,m_EntityLod1Radius=10000.000000,m_EntityLod2Radius=15000.000000,m...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AiSquadSettings` | `(FindSquadFormationQuery="/Game/Dune/AI/EQS/EQS_FindSquadPositions.EQS_FindSquadPositions",Defaul...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CritterSettings` | `(CritterSpawningConfigs=((CritterClass=/Script/Engine.BlueprintGeneratedClass'"/Game/Dune/AI/Crit...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PerceptionSettings` | `(SightMaxStimulusAge=15.000000,HearingMaxStimulusAge=20.000000,TimeKeepLostTarget=15.000000,Playe...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AudioSettings` | `(LasgunDamageTypeClass="/Game/Dune/Weapons/Blueprints/DamageTypes/BP_DmgType_Energy.BP_DmgType_En...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AiFocusSettings` | `(m_FocusDistanceCurve="/Game/Dune/AI/Shared/KeyNpcFocusCurves/KeyNPC_FocusDistance_Default.KeyNPC...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bUseStaticWeaponTraceOffsets` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_WeaponMuzzleOffsetMap` | `((Carbine, (X=0.000000,Y=20.000000,Z=50.000000)),(Pistol, (X=0.000000,Y=20.000000,Z=60.000000)),(...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultWeaponMuzzleOffset` | `(X=0.000000,Y=20.000000,Z=60.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_ThrownProjectileOffsets` | `3 entries; first \`(X=200.000000,Y=200.000000,Z=20.000000)\`` | 3 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ThrownProjectileTargetDistThreshhold` | `500.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_InformAiOfTeamChangeRange` | `10000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_LookTargetRange` | `400.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_NpcHomeDistanceRanges` | `((Far, 2097152.000000),(Medium, 10000.000000),(Close, 6000.000000),(Home, 3000.000000))` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultDiveDistance` | `200.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxDistanceToTarget` | `2000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultMeleeRange` | `200.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MinFillablePercent` | `0.250000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MaxFillablePercent` | `0.750000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_EditorSpawningDelayInSeconds` | `5.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_GhostModeMaxTimeInSeconds` | `30.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_CorpseLifespanInSeconds` | `120.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_UnableToMoveThreshold` | `10` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bEnablePlayerExtraSightChecks` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_HeightOffsetForExtraLos` | `10.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TargetDistanceForExtraLos` | `3000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TimeBeforeSightConeIsRequired` | `2.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RandomDBNOChance` | `0.100000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bEnableAimOverCover` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_AimOverOffset` | `(X=30.000000,Y=0.000000,Z=25.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_WeaponAccuracy` | `(m_WeaponMaxAccuracyModifierTiers=((m_DistanceCurve="/Game/Dune/AI/Shared/Accuracy/Flat/NPCAccura...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TeamDebugColors` | `((Atreides, (B=77,G=231,R=69,A=0)),(Harkonnen, (B=74,G=106,R=227,A=0)),(Smugglers, (B=203,G=233,R...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_WasRecentlyStaggeredMaxTimeInSeconds` | `5.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_WasRecentlyDamagedByTargetMaxTimeInSeconds` | `1.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxFocusDistanceFromTargetToAllowShooting` | `500.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_HostileTag` | `(TagName="NPC.Hostility.Hostile")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_HostileEffect` | `/Game/Dune/Effects/NPC/GE_NPC_Hostile.GE_NPC_Hostile_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_StaticCharactersSettings` | `(m_TickInterval=1.000000,m_TimeToShow=6,m_TimeToHide=19,m_VisibleRangeInSandStorm=4000.000000,m_V...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultDifficultyConfig` | `/Game/Dune/AI/Config/DifficultyControl/BP_DifficultyConfigBase.BP_DifficultyConfigBase_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DifficultyConfigToAttributeMap` | `(("m_PoiseDamageResistance", (AttributeName="PoiseDamageResistance",Attribute=/Script/DuneSandbox...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_AiSpawningAnimations` | `/Game/Dune/Animations/Humans/Common/NPC/Combat/AM_Human_NPC_Spawn_Door_01_Run.AM_Human_NPC_Spawn_...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_WorldContentNpcCompositions` | `24 entries; first \`/Game/Dune/AI/Spawners/NPCCompositions/NPCComp_Slavers.NPCComp_Slavers\`` | 24 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AiCoverPlacementToolSettings` | `(m_WallStandoffDistance=80.000000,m_WallSearchTraces=12,m_WallSearchDistance=160.000000,m_CornerA...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PVPRespawn` | `(m_TierRespawn=,m_FallbackRespawnTimeMinutes=8.000000)` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_DefaultRespawn` | `(m_TierRespawn=,m_FallbackRespawnTimeMinutes=8.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_BlackboardKeysDebuggerWatchlist` | `5 entries; first \`Target\`` | 5 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[/Script/DuneSandbox.SandStormConfig]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SandStormBaseClass` | `/Game/Dune/Systems/SandStorm/BP_SandStorm.BP_SandStorm_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SandStormDebrisClass` | `/Game/Dune/Systems/SandStorm/BP_SandStormDebris.BP_SandStormDebris_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TreasureItemsTable` | `/Game/Dune/Systems/LootTables/Loot_Experience/Buried_Treasure/DT_LootTable_BuriedTreasure_Main.DT...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_bAutoSpawnEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bSandStormDebrisEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_SandStormDebrisSpeed` | `3000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlayerOverlapCheckIntervalInSeconds` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_BuildingOverlapCheckIntervalInSeconds` | `5.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableOverlapCheckIntervalInSeconds` | `5.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_BuildablesOverlapCheckIntervalInSeconds` | `5.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_VehicleOverlapCheckIntervalInSeconds` | `3.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_DamageFramesPerOverlapInterval` | `15` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_NetCullDistanceInMeters` | `10000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_FadeDistanceInMeters` | `9000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bCoriolisAutoSpawnEnabled` | `True` | 1 | Known | Controls automatic Coriolis storm spawning. |
| `m_CoriolisSpawnWarningsDurationInHours` | `6` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CoriolisStage1DurationInSeconds` | `32400.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CoriolisStage2DurationInSeconds` | `3540.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CoriolisStage3DurationSeconds` | `60.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CoriolisStage4DurationSeconds` | `60.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CoriolisStage5DurationSeconds` | `1740.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CoriolisBaseClass` | `/Game/Dune/Systems/CoriolisStorm/BP_Coriolis.BP_Coriolis_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CoriolisSandstormSpawnPreventionSeconds` | `600.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_bCoriolisDoesDamage` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bCoriolisTriggerShiftingSands` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_CoriolisLightDamage` | `5.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CoriolisHeavyDamage` | `5000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TotemShortCircuitTimeAfterCoriolis` | `300.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_TotemShortCircuitTimeAfterSandstorm` | `300.000000` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_SandstormProtectedTag` | `(TagName="Character.Protection.Sandstorm")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_VolumetricCloudMinSampleCount` | `2` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_VolumetricCloudMaxDistanceInMetersForSampleCount` | `2000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_VolumetricCloudMinDistanceInMetersForSampleCount` | `100.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_VolumetricCloudMaxSampleCount` | `6` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SmallSandStormDamageConfig` | `(Player=5.000000,Building=5.000000,Placeable=5.000000,Vehicle=5.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LargeSandStormDamageConfig` | `(Player=7.000000,Building=7.000000,Placeable=7.000000,Vehicle=7.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.AiPopulationSpawnComponent]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_NpeActivationDelayInSeconds` | `30.0` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |

## `[/Script/DuneSandbox.TiledLandscapeEditor]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_LandscapeTileGizmoActorClass` | `/Game/Dune/Systems/DynamicContent/Blueprints/BP_LandscapeTileGizmoActor.BP_LandscapeTileGizmoActor_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WorldmassFlattenBrushClass` | `/Game/Dune/Art/TechArt/Worldmass/Blueprints/BP_Worldmass_Brush_SnapMap.BP_Worldmass_Brush_SnapMap_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `+m_LandscapeProxiesTags` | `Worldmass` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.WorldLayoutSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_WorldLayoutsPerWorld` | `(("/Game/Dune/Maps/Arrakis/DeepDesert_1/DeepDesert_1.DeepDesert_1", (WorldLayoutsSettingsList=((C...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_WorldLayoutTerrainBlockClass` | `/Game/Dune/Systems/DynamicContent/TerrainBlocks/BP_TerrainBlockActor.BP_TerrainBlockActor_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WorldLayoutTerrainBlockNameBase` | `CB_WL_0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_WorldLayoutGenericActorGizmoClass` | `/Game/Dune/Systems/DynamicContent/Blueprints/BP_GenericActorGizmoActor.BP_GenericActorGizmoActor_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WorldLayoutGenericActorNamePrefix` | `GA_WL_` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.TerrainBlocksSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ExcludedSubPathDuringTemplateGeneration` | `/SE/` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AssetsDirectoryPath` | `(Path="/Game/Dune/Systems/DynamicContent/TerrainBlocks/Collection")` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_StreamingDistanceSource` | `DataAsset` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bUseDefaultStreamingDistanceSettings` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultStreamingDistanceSettings_ByDistance` | `(Metric=20000.000000,LODMetrics=(50000,100000,200000,400000))` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_LargeStreamingDistanceSettings_ByDistance` | `(Metric=250000.000000,LODMetrics=(300000,350000,370000,400000))` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `+m_StreamingDistanceSettingsRules_ByDistance` | `17 entries; first \`(Description="Main Contents Block: Art",Directory=(Path="/Game/Dune...\`` | 17 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DefaultStreamingDistanceSettings_ByScreenSize` | `(Metric=0.6,LODMetrics=(0.3,0.1,0.05))` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bScreenSizeBasedStreamingDistanceIgnoreSubLevelBounds` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.EncountersSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultEncounterClass` | `/Game/Dune/Systems/DynamicContent/Encounters/BP_DE.BP_DE_C` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bAreRandomEncountersEnabled` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_AroundPlayersRandomEncounterTagsQuery` | `(TokenStreamVersion=0,TagDictionary=((TagName="Encounter.Dynamic.Random"),(TagName="Encounter.Dyn...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_WholeServerRandomEncounterTagsQuery` | `(TokenStreamVersion=0,TagDictionary=((TagName="Encounter.Dynamic.Random.WholeServer")),QueryToken...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RandomEncounterInstigationAroundPlayersBoxExtentInMeters` | `500` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RandomEncounterInstigationAroundPlayersDelayInSec` | `15.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RandomEncounterInstigationOnWholeServerDelayInSec` | `60.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RandomEncounterInstigationByAreaDelayInSecOverride` | `-1.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bAreEncounterAreaLimitsEnabled` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SpiceCollectorsAttackChance` | `0.000030` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SpiceCollectorsAttackName` | `(Name="SpiceCollectors")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_InitialTrialAttackName` | `(Name="InitialTrial")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bAreEncounterNodesEnabled` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_EncounterGroupMapping` | `(("15x15", (Template=(Class="/Game/Dune/Systems/DynamicContent/Encounters/BP_DE_Rck.BP_DE_Rck_C",...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bShouldLiftUndergroundEncounterNodes` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bIsRandomEncounterInstigationAroundPlayersEnabled` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bIsRandomEncounterInstigationOnWholeServerEnabled` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bIsRandomEncounterInstigationOnWholeServerForced` | `False` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bIsRandomEncounterInstigationByAreaEnabled` | `True` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DisabledEncounterNames` | `((Name="DE_120_SmallShipWreck_DeepDesert_Depricated"))` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_AssetsDirectoryPath` | `(Path="/Game/Dune/Systems/DynamicContent/Encounters/Collection")` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.ContractsSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bIsEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bIsIgwSupportEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_MaxContractVariationsNum` | `5` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxGlobalContractsNumberPerServer` | `10` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bShouldGroupAvailableContracts` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_MinNumOfPlayersOnServerForContractSpawn` | `1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractMapMarkerType` | `(Name="Contract")` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ContractItemTemplateId` | `(Name="ContractItem")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractRewardItemTemplateId` | `(Name="ContractRewardItem")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractTargetItemTag` | `(TagName="Contract.Target.Item")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractContentGlobalTag` | `(TagName="Contract.Global")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TickRateInSec` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_InitialTickDelayInSec` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ContractSpawnDelayInSec` | `0.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ContractLifetimeCheckDelayInSec` | `15.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ContractConditionCheckDistance` | `100` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ContractConditionGoToLocationCompleteDistance` | `10` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_KillConditionSettings` | `(bCanScoreKillByDamage=True,MaxDurationToScoreKillByDamageInSec=60,MaxDistanceToScoreKillByDamage...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_NpcContractsFilterRequiredTags` | `(GameplayTags=((TagName="Contract.Target.NPC")))` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContactIssuerDialogueWidgetClass` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Contracts/W_ContractContactIssuerDialogContent.W_ContractCo...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_SolarisAmountToTagMapping` | `(((TagName="Reward.Solaris.T1Small"), 1500),((TagName="Reward.Solaris.T1Medium"), 2000),((TagName...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ContractCompletionTag` | `(TagName="Contract.Tracking.Completed")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractGroupTag` | `(TagName="Contract.UI.Card.Group")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractChainTag` | `(TagName="Contract.UI.Card.Chain")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractChainFinalTag` | `(TagName="Contract.UI.Card.ChainFinal")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractOrderTag` | `(TagName="Contract.UI.Card.Order")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractsHierarchyAsset` | `/Game/Dune/Systems/Contracts/DA_ContractsHierarchy.DA_ContractsHierarchy` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ContractUpgradesAsset` | `/Game/Dune/Systems/Contracts/DA_ContractUpgrades.DA_ContractUpgrades` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.DuneSandboxGameModeBase]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_BrokenVehicleModuleArmorDeduction` | `2` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bShouldPlayersDropLootOnDeath` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bShouldPlayersDropLootOnDefeat` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bShouldPlayersLoseItemsOnDeath` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bShouldNpcDropLootOnDeath` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DropAmountOnDefeat` | `0.4` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RespawnClearanceCapsule` | `(x=36,y=92)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneGameState]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ArmorMitigationConstant` | `500` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.GenericActorSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ForbiddenTemplates` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.SecurityZonesSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bAreSecurityZonesEnabled` | `True` | 1 | Known | Enables security zones; disabling allows PvP/ability use everywhere per shipped setup comments. |
| `m_DefaultSecurityZoneType` | `(Name="NullSec")` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_DefaultSecurityZoneClassForCheats` | `/Game/Dune/Systems/SecurityZones/BP_SecurityZone.BP_SecurityZone_C` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_OutlawCriminalScore` | `5` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_CriminalScoreLifeTimeInSec` | `600.000000` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_OutlawFlagLifeTimeInSec` | `7200.000000` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_PersistentCriminalFlags` | `()` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_DuelingStartDelayInSeconds` | `5.000000` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_DuelingOutOfRangeDelayInSeconds` | `5.000000` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_DuelingXYRadiusInUnits` | `2500.000000` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |
| `m_PveFallbacks` | `(((Name="NullSec"), (Name="Security")))` | 1 | Known | PvP/security-zone related setting from shipped setup/default config. |

## `[/Script/DuneSandbox.HarvestingConfig]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bNPCCreatePhysicBodies` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_StartPickupSpiceInteraction` | `BlueprintGeneratedClass'/Game/Dune/Characters/Player/Interactions/Objects/BP_StartPickupSpiceInte...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_StopPickupSpiceInteraction` | `BlueprintGeneratedClass'/Game/Dune/Characters/Player/Interactions/Objects/BP_StopPickupSpiceInter...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.LeaveMeAlone]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `5 entries; first \`EncountersDestroyAndDisableAll\`` | 5 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.StartHitchVehicleTest]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `9 entries; first \`ServerExec t.maxfps 20\`` | 9 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.StopHitchVehicleTest]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `5 entries; first \`ServerExec t.maxfps 0\`` | 5 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.PlaytestSetup]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `31 entries; first \`ResetProgression\`` | 31 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.PlaytestSetupAdmin]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `31 entries; first \`ResetProgression\`` | 31 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.AwardPlayerXP]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `3 entries; first \`AwardXP Combat 10000\`` | 3 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.UnlockAllSkills]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `33 entries; first \`SkillsSetModuleLevel Skills.Key.Trooper1 1\`` | 33 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[CheatScript.UnlockAllAbilities]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+Cmd` | `20 entries; first \`SkillsSetModuleLevel Skills.Ability.Blindspot 1\`` | 20 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[DuneAutoScriptComponents]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `DunePlayerAutoScriptComponentClass` | `/Script/DuneSandboxAuto.DunePlayerAutoComponent` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DuneS2sControllerAutoScriptComponentClass` | `/Script/DuneSandboxAuto.S2sControllerAutoComponent` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.DunePlayerController]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_RespawnGUITimer` | `2.f` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SandwormDeathRespawnGUITimer` | `5.0f` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.DuneVehicle]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `s_RecentlyDrivenTime` | `15.f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `s_CombatRatingScalar` | `16` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_VehicleShelterThreshold` | `0.75f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.DuneCharacter]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ShelterThreshold` | `0.75f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_SuspendedEffectTag` | `Abilities.Suspended` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ExitShootingSubstateDelayDuration` | `1.0f` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_DefaultHealingDamageType` | `/Game/Dune/Weapons/Blueprints/DamageTypes/BP_DmgType_Healing.BP_DmgType_Healing_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DunePlayerCharacter]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `s_RepeatedKillCooldown` | `300.0` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |

## `[SkillsSystemsGlobals]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `s_SkillsServerVersionNumber` | `6` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.DuneNpcCharacter]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `s_CombatRatingScalar` | `16.0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ModularAiBehaviorAsset]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultBlackboardAsset` | `/Game/Dune/AI/Characters/Npc_SoldierBase/BT/BB_SoldierBase.BB_SoldierBase` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandboxTests.DuneAutomatedTestSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ActorTestsWorld` | `/Game/Dune/Smoketest/FunctionalTests/Building/Building.Building` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DialogueSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MaxParticipationRadiusInCm` | `50000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_NpcDialogueDataAsset` | `/Game/Dune/NPCs/Dialogue/DA_NPCDialogues.DA_NPCDialogues` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.CharacterCreationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_CharacterCreationMap` | `/Game/Dune/Maps/CharacterCreationPBE/CC_PBE.CC_PBE` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CustomizableObject` | `/Game/Dune/Characters/Player/MutableDev/CharacterCustomizer_RigUpdate.CharacterCustomizer_RigUpdate` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CustomizableObjectInstance` | `/Game/Dune/Characters/Player/MutableDev/CharacterCustomizer_RigUpdate_Inst.CharacterCustomizer_Ri...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterCreationScreenData` | `/Game/Dune/Systems/CharacterCreation/CharacterCreationScreenData.CharacterCreationScreenData` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterCreationServerData` | `/Game/Dune/Systems/CharacterCreation/AlwaysCook/CharacterCreationServerData.CharacterCreationServ...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PbeStatesQueueData` | `/Game/Dune/Systems/CharacterCreation/PbeStates/PbeStatesQueueData.PbeStatesQueueData` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_HeadScaleCompensation` | `0.750000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MinValidationDelayInSeconds` | `0.500000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_MaxValidationDelayInSeconds` | `3.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ValidationFailureMultiplierInSeconds` | `2.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ValidationDelayCoolDownTimeInSeconds` | `4.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_RandomizationBudgetPercent` | `200` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MinimumRandomizationChangePercent` | `10` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CreationCameraBPClass` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Characters/Player/Misc/BP_CharacterCreationCame...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_QualitySettings` | `((0, (MaxShadowResolution=1024,ContactShadows=1)),(1, (MaxShadowResolution=2048,ContactShadows=1)...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/Engine.AssetManagerSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+PrimaryAssetTypesToScan` | `18 entries; first \`(PrimaryAssetType="Map",AssetBaseClass="/Script/Engine.World",bHasB...\`` | 18 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `bOnlyCookProductionAssets` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bShouldManagerDetermineTypeAndName` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bShouldGuessTypeAndNameInEditor` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bShouldAcquireMissingChunksOnLoad` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bShouldWarnAboutInvalidAssets` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `MetaDataTagsForAssetRegistry` | `("HoudiniBatch","AssetChecker.EfficiencyRating","AssetChecker.EfficiencyGradingComments","AssetCh...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/GameplayAbilities.AbilitySystemGlobals]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+GameplayCueNotifyPaths` | `3 entries; first \`/Game/Dune/Abilities/Cues\`` | 3 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `+AbilitySystemGlobalsClassName` | `/Script/DWGameplayAbilities.DWAbilitySystemGlobals` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `ActivateFailTagsBlockedName` | `Abilities.Global.FailBlocked` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ActivateFailCooldownName` | `Abilities.Global.FailCooldown` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `ActivateFailCostName` | `Abilities.Global.FailCost` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `ActivateFailTagsMissingName` | `Abilities.Global.FailMissing` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `bAllowGameplayModEvaluationChannels` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `bUseDebugTargetFromHud` | `True` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.DuneWorldPartitioner]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ServerAreaBlocker` | `/Game/Dune/Systems/InfiniteGameWorlds/BP_ServerAreaBlocker.BP_ServerAreaBlocker_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_NeighboringPartitionTreshold` | `5.0f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_EnableNumPlayersPartitionBlocking` | `false` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BlockPartitionTresholdPercent` | `1.f` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_UnblockPartitionTresholdPercent` | `0.9f` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.AreaBlockerSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_BlockerWallHeight` | `2200f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BlockerWallHeightOffset` | `800.0f` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_BlockerWallDepth` | `1.0f` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_EnableClientBlockerWall` | `false` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_EnableServerBlockerWall` | `false` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneIgwServerConnectionComponent]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ClientAreaBlocker` | `/Game/Dune/Systems/InfiniteGameWorlds/BP_ClientAreaBlocker.BP_ClientAreaBlocker_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.MatchmakerEventsSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bSendEvents` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `+m_BattlegroupsAllMapSettings` | `32 entries; first \`(MapName="Survival_1",MapSettings=(SelectionRule="HomeDimension",Ma...\`` | 32 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BattlegroupsDefaultMapSettings` | `(SelectionRule="LowestDimension",MaxPlayerCapacity=40,IsStartingMap=False)` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[/Script/DuneSandbox.LandsraadSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `bIsLandsraadEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `Data` | `(m_NumberOfWeeksTermRetention=4,m_NumberOfDecreesToNominate=3,m_NumberOfGuildsInHighscoreList=5,m...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LandsraadControlPointClassForCheats` | `/Game/Dune/Systems/Landsraad/BP_LandsraadControlPoint.BP_LandsraadControlPoint_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LandsraadContractsDailyBonusReferenceTimestamp` | `1760572800` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ResourceLocationSystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bIsEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_ResourcePointTrace` | `MoveUpwards` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ResourceSpawnChance` | `1.0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ResourceNodeSpawner]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ResourceSpawnChance` | `1.0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Game/Dune/Systems/GlobalDistribution/BP_BrittleBush_Spawner.BP_BrittleBush_Spawner_C]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ResourceSpawnChance` | `1.0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneWorldComposition]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `bUseWorldGeneratorBounds` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_WorldOffset` | `50800` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.GUISettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_GUIAudioEvents` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Audio/BP_GUIAudioEvents.BP_GUIAudioEvents_C'` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ItemDurabilitySettings` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/GUI/BP_ItemDurabilitySettings.BP_ItemDurability...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_WindowWidgets` | `((AdminTeleportMap, "/Game/Dune/GUI/Widgets/Menus/Gameplay/AdminPanel/TeleportMap/W_Admin_Telepor...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_WindowTetherPollingRateSeconds` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_DesiredEntryClassMapping` | `(((Name="ConsumeFillable"), "/Game/Dune/GUI/Widgets/HUD/Notifications/W_ConsumeFillableNotificati...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ToastNotificationsData` | `/Game/Dune/GUI/Data/ToastNotificationData/ToastNotificationsDataSettings.ToastNotificationsDataSe...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_NotificationAudioEventsAsset` | `/Game/Dune/Systems/Notifications/DA_NotificationAudioEventAsset.DA_NotificationAudioEventAsset` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_HUDNotificationEntryBodyMapping` | `(((Name="HUDLandclaim"), "/Game/Dune/GUI/Widgets/HUD/Notifications/W_HUDNotificationEntryBodyLand...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PickupNotificationMaxCount` | `5` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ThresholdForMaxVolume` | `0.500000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_RadialCycleSkippedCharacterTags` | `(GameplayTags=((TagName="CharacterState.State.Building"),(TagName="CharacterState.State.BuildingB...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_VoiceChatIndicatorPollingRate` | `0.330000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_VoiceChatIconDefaultOffsetVehicle` | `(X=0.000000,Y=0.000000,Z=200.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_VoiceChatIconDefaultOffsetCharacter` | `(X=0.000000,Y=0.000000,Z=137.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_HardwareCursorPath` | `Dune/GUI/Slate/Cursor/T_UI_Cursor.png` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MissingDataIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Items/T_UI_IconItemUnknownS_D.T_UI_IconItemUnknownS_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ItemCategoryForAllItemsIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Categories/T_UI_CatIconAll_D.T_UI_CatIconAll_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ItemCategoryForUniqueItemsIcon` | `None` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PlaceholderCategoryIcon` | `None` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PlaceableCircuitsTabGeneralIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Categories/T_UI_CatIcon_PlaceablesGeneral_D.T_UI_CatIcon_P...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableCircuitsTabWaterIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Categories/T_UI_CatIcon_PlaceablesWater_D.T_UI_CatIcon_Pla...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableCircuitsTabInventoryIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Categories/T_UI_CatIcon_PlaceablesStorage_D.T_UI_CatIcon_P...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_PlaceableCircuitsTabAccessControlIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Categories/T_UI_CatIcon_PlaceablesAccess_D.T_UI_CatIcon_Pl...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_ArmorStatLabelWidget` | `/Game/Dune/GUI/Widgets/Components/Elements/ItemCard/W_ArmorStatLabel.W_ArmorStatLabel_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ArmorStatCompactLabelWidget` | `/Game/Dune/GUI/Widgets/Components/Elements/ItemCard/W_ArmorStatLabelCompact.W_ArmorStatLabelCompa...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TravelRequestContentWidget` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Travel/W_TravelRequestDialogContent.W_TravelRequestDialogCo...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InspectPlayerContentWidget` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/W_InspectWindow.W_InspectWindow_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InspectPlayerIcon` | `/Game/Dune/GUI/Textures/Components/AccountInformation/T_UI_AccountImage_Diamond_D.T_UI_AccountIma...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_InspectPlayerIconPresetWidget` | `(Name="SocialInspectMenu")` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BankingContentDepositIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Currency/T_UI_Icon_Currency_SolariCredit_D.T_UI_Icon_Curre...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_BankingContentWithdrawIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Currency/T_UI_Icon_Currency_SolariCoins_D.T_UI_Icon_Curren...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_TravelDimensionSelectionDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/InstanceSelection/W_MetaDialogTravelDimensionSelectionC...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_InfoCardClass` | `/Game/Dune/GUI/Widgets/Components/InfoCard/W_InfoCard.W_InfoCard_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InfoCardDeadzoneBorder` | `(Left=20.000000,Top=100.000000,Right=20.000000,Bottom=100.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DefaultItemInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Items/DA_BasicItemInfoCard.DA_BasicItemInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RequiredSlotItemInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Items/DA_ItemTemplateInfoCard.DA_ItemTemplateInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractItemInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Items/DA_ContractInfoCard.DA_ContractInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TechRecipeInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Technology/DA_TechRecipeInfoCard.DA_TechRecipeInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TechBuildableInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Technology/DA_TechBuildableInfoCard.DA_TechBuildableInfoCard` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_TechGroupInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Technology/DA_TechGroupInfoCard.DA_TechGroupInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BuildableInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Building/DA_BuildableInfoCard.DA_BuildableInfoCard` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_LandsraadTaskInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Landsraad/DA_LandsraadTaskInfoCard.DA_LandsraadTaskInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LandsraadTaskInfoCardUnrevealed` | `/Game/Dune/GUI/Data/InfoCardData/Landsraad/DA_LandsraadTaskInfoCardUnrevealed.DA_LandsraadTaskInf...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SkillModuleAbilityInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Skills/DA_SkillModuleAbilityInfoCard.DA_SkillModuleAbilityInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SkillModuleTechniqueInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Skills/DA_SkillModuleTechniqueInfoCard.DA_SkillModuleTechniqueIn...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SkillModuleAttributeInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Skills/DA_SkillModuleAttributeInfoCard.DA_SkillModuleAttributeIn...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SkillBuildTechniqueInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Skills/DA_SkillBuildTechniqueInfoCard.DA_SkillBuildTechniqueInfo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SkillBuildAbilityInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Skills/DA_SkillBuildAbilityInfoCard.DA_SkillBuildAbilityInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ContractInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Contracts/DA_ContractInfoCard.DA_ContractInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PermissionInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Permission/DA_PermissionInfoCard.DA_PermissionInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CustomizationInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Customization/DA_CustomizationInfoCard.DA_CustomizationInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DEOrderDurationData` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/DuneExchange/DA_DEOrderDurations.DA_DEOrderDurat...` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_DimensionNames` | `/Game/Dune/GUI/Widgets/Menus/Meta/BattlegroupMenu/DA_DimensionNames.DA_DimensionNames` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_StreamerModeNotificationExclusionList` | `/Game/Dune/Systems/Notifications/DA_StreamerModeNotificationDataExclusionList.DA_StreamerModeNoti...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DEDefaultItemPrice` | `1000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlaceablesTabsData` | `/Game/Dune/GUI/Data/BuildingSystem/DA_PlaceableTabsData.DA_PlaceableTabsData` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_HUDModeOpacityTweenDuration` | `0.500000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_StatusHUDModeDurationOnTap` | `3.000000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_HUDStateData` | `/Game/Dune/GUI/Data/DA_HUDStates.DA_HUDStates` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_StartingHUDUnLockLevel` | `FullExceptSpiceDream` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_KeybindCategoriesData` | `/Game/Dune/GUI/Data/KeybindSettingsData/DA_KeybindCategories.DA_KeybindCategories` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_KeybindConflictsData` | `/Game/Dune/GUI/Data/KeybindSettingsData/DA_KeybindConflicts.DA_KeybindConflicts` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ConnectionQueueDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogConnectionQueueContent.W_MetaDialogConnecti...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DataCollectionDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogDataCollectionContent.W_MetaDialogDataColle...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AmountSetterDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogAmountSetterContent.W_MetaDialogAmountSette...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_DungeonScalingDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogDungeonScalingContent.W_MetaDialogDungeonSc...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RecommendedServerDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogRecommendedServerContent.W_MetaDialogRecomm...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ServerPasswordDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogServerPasswordContent.W_MetaDialogServerPas...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterRespawnDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogCharacterRespawnContent.W_MetaDialogCharact...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterDeletionDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogCharacterDeletionContent.W_MetaDialogCharac...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_GenericTimerDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogTimerContent.W_MetaDialogTimerContent_C` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_SupportReportBugDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/Support/W_MetaDialogReportBugContent.W_MetaDialogReport...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SupportRequestHelpDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/Support/W_MetaDialogRequestHelpContent.W_MetaDialogRequ...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LorePickupDialogConfig` | `(m_TitleTopPadding=157.500000,m_BackgroundHorizontalAlignment=HAlign_Fill,m_BackgroundVerticalAli...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MaxSearchPlayerEntries` | `50` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MinHoldTimeToShowIAWProgressBar` | `0.400000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CustomizationItemIcons` | `((Swatch, "/Game/Dune/GUI/Textures/Icons/Gameplay/Customization/T_UI_IconTmogItemSwatches_D.T_UI_...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_NotCustomizableTag` | `(TagName="Items.NotCustomizable")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RewardIconSolaris` | `/Game/Dune/GUI/Textures/Icons/Gameplay/PickupNotifications/T_UI_IconPickupSolari_D.T_UI_IconPicku...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_RewardIconXP` | `/Game/Dune/GUI/Textures/Icons/Gameplay/PickupNotifications/T_UI_IconPickupXP_D.T_UI_IconPickupXP_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_RewardIconIntel` | `/Game/Dune/GUI/Textures/Icons/Gameplay/TechTree/T_UI_IconIntelCurrency_D.T_UI_IconIntelCurrency_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MarkerTypeScalarSettings` | `/Game/Dune/GUI/Data/DA_MarkerTypeScalarSettings.DA_MarkerTypeScalarSettings` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_TextInputFieldWithValidationDialogContentClass` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Building/CopyTool/W_TextInputFieldWithValidationDialogueCon...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_AllianceColors` | `((Party_0, (R=0.982251,G=0.346704,B=0.086500,A=1.000000)),(Party_1, (R=0.752942,G=0.485150,B=0.10...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultCrosshairColor` | `(R=1.000000,G=0.913726,B=0.792157,A=0.749020)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_CrosshairTargetIndicatorColor` | `(R=0.992157,G=0.815686,B=0.592157,A=0.749020)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PurchaseURL` | `"https://store.steampowered.com/app/1172710/Dune_Awakening"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DECreateSellOrderHeaderIconPreset` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/DuneExchange/DA_DEOrderHeaderIcon.DA_DEOrderHead...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_NewsfeedURLFormat` | `"https://duneawakening.com/launcher-feed/{LanguageCode}"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PatchNotesURL` | `"https://duneawakening.com/feed/"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ExternalLinkButtonIcon` | `/Game/Dune/GUI/Textures/Icons/Meta/ExternalContent/T_UI_Icon_ExternalLink_D.T_UI_Icon_ExternalLink_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DialogTransferTokenHeader` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/Components/W_DialogTransferTokenHeader.W_DialogTransfer...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TransferTokenIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Currency/T_UI_Icon_Currency_TransferToken_D.T_UI_Icon_Curr...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_TransferTokenIconColor` | `(R=1.000000,G=0.701102,B=0.300544,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ProgressionUnlockDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_ProgressionUnlockDialogContent.W_ProgressionUnlockDia...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PatchNotesLocalizedURL` | `"https://duneawakening.com/{LanguageCode}/feed/"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PatchNotesDefaultURL` | `"https://duneawakening.com/feed/"` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BaseBackupDeletionDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogBaseBackupForgetConfirmationContent.W_MetaD...` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BaseBackupRecycleDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogBaseBackupRecycleConfirmationContent.W_Meta...` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DungeonScalingDialogConfig` | `(m_HeightOverride=880.000000,m_TitleTopPadding=-55.000000,m_TitleVerticalAlignment=VAlign_Top,m_B...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_KeystoneInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Specialization/DA_KeystoneInfoCard.DA_KeystoneInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SpecTrackPassiveInfoCard` | `/Game/Dune/GUI/Data/InfoCardData/Specialization/DA_SpecPassiveInfoCard.DA_SpecPassiveInfoCard` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LandsraadMissionReportHeader` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/Landsraad/W_LandsraadBonusChargesDisplay.W_Lands...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterMigrationClosedTransferWelcomeDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/CharacterTransfer/W_CharacterMigrationClosedTransferWelcome...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterMigrationAnnouncementDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/CharacterTransfer/W_CharacterMigrationDialogContent.W_Chara...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterMigrationDialogConfig` | `(m_MetaDialogContentBackgroundConfig=(m_BackgroundConfig=(m_CustomContentBackground="/Game/Dune/G...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterMigrationAnnouncementClosedServersDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/CharacterTransfer/W_CharacterMigrationClosedServersDialogCo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CustomServerCreateCharacterDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogCustomServerCreateContent.W_MetaDialogCusto...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CustomServerTransferCharacterDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/Dialogs/W_MetaDialogCustomServerTransferContent.W_MetaDialogCus...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ServerBrowserCustomServerIcon` | `/Game/Dune/GUI/Textures/Icons/Meta/Frontend/T_UI_Icon_Server_Custom_D.T_UI_Icon_Server_Custom_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ServerBrowserStandardServerIcon` | `/Game/Dune/GUI/Textures/Icons/Meta/Frontend/T_UI_Icon_Server_Standard_D.T_UI_Icon_Server_Standard_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.AudioThreatSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ConfigEnableSystem` | `True` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ConfigMaxThreatEventBufferDuration` | `30.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_ConfigMaxDistanceConsideredFlyby` | `400.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.SpiceAddictionSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_bIsSpiceAddictionEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DefaultSpiceAddictionSettings` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Systems/SpiceAddiction/BP_SpiceAddictionSetting...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bIsSpiceVisionEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[/Script/DuneSandbox.TaxationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `PaymentItemTemplateId` | `(Name="SolarisCoin")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ReferenceUTCTimestamp` | `1724666400` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_TaxationCycleLengthSeconds` | `1209600` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_TimeToRemovePaidInvoices` | `2419200` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SpicePerHour` | `11.904750` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_CostMultiplierPerLandclaim` | `6 entries; first \`0.000000\`` | 6 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `+m_CostMultiplierPerVerticalExtension` | `6 entries; first \`0.000000\`` | 6 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TaxationDialogContentWidget` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/Taxation/W_TaxationDialogContent.W_TaxationDialogContent_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TaxationDialogTitle` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/TAXATION_DIALOG_TIT...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SolarisItemTemplateId` | `(Name="SolarisCoin")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PaymentItemPerHour` | `11.905000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bTaxationEnabled` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[Settings.Gameplay]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `ForceShowFullHUDLevel` | `True` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.InventorySystemSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `DataTableBaseItems` | `/Game/Dune/Systems/Items/CDT_BaseItems.CDT_BaseItems` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTablePerishableItems` | `/Game/Dune/Systems/Items/DT_ItemTablePerishables.DT_ItemTablePerishables` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableWearableItems` | `/Game/Dune/Systems/Items/CDT_Items_Wearables.CDT_Items_Wearables` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableSocialWearableItems` | `/Game/Dune/Systems/Items/DT_Items_Social_Wearables_Clothing.DT_Items_Social_Wearables_Clothing` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableWeaponItems` | `/Game/Dune/Systems/Items/DT_ItemTableWeapons.DT_ItemTableWeapons` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableWeaponModItems` | `/Game/Dune/Systems/Items/DT_ItemTableWeaponMods.DT_ItemTableWeaponMods` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableShieldItems` | `/Game/Dune/Systems/Items/DT_ItemTableShields.DT_ItemTableShields` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableAbilityItems` | `/Game/Dune/Systems/Items/DT_ItemTableAbilities.DT_ItemTableAbilities` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableVehicleAbilityItems` | `/Game/Dune/Systems/Items/DT_ItemTableVehicleAbilities.DT_ItemTableVehicleAbilities` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableBuildableItems` | `/Game/Dune/Systems/Items/DT_ItemTableBuildables.DT_ItemTableBuildables` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `DataTableBuildingBlueprintItems` | `/Game/Dune/Systems/Items/DT_BuildingBlueprintItemTable.DT_BuildingBlueprintItemTable` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `DataTableEdibleItems` | `/Game/Dune/Systems/Items/DT_ItemTableEdibles.DT_ItemTableEdibles` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableContainerItems` | `/Game/Dune/Systems/Items/DT_ItemTableContainerItems.DT_ItemTableContainerItems` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableSchematicItems` | `/Game/Dune/Systems/Items/DT_ItemTableSchematics.DT_ItemTableSchematics` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableCustomizationItems` | `/Game/Dune/Systems/Items/DT_ItemTableCustomizations.DT_ItemTableCustomizations` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableReferenceItems` | `/Game/Dune/Systems/Items/DT_ReferenceItemTable.DT_ReferenceItemTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableArmorItems` | `/Game/Dune/Systems/Items/DT_ArmorItemTable.DT_ArmorItemTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableMeleeWeaponItems` | `/Game/Dune/Systems/Items/DT_MeleeWeaponItemTable.DT_MeleeWeaponItemTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableHydrationClothingItems` | `/Game/Dune/Systems/Items/DT_ClothingHydrationItemTable.DT_ClothingHydrationItemTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableIconLayerPresets` | `None` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `DataTableResourceItems` | `None` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableFillableItems` | `/Game/Dune/Systems/Items/DT_ItemTableFillables.DT_ItemTableFillables` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableFuelContainerItems` | `/Game/Dune/Systems/Items/DT_FuelContainerItemTable.DT_FuelContainerItemTable` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableEmoteItems` | `/Game/Dune/Systems/Items/DT_ItemTableEmotes.DT_ItemTableEmotes` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableSinkchartsItems` | `/Game/Dune/Systems/Items/DT_ItemTableSinkcharts.DT_ItemTableSinkcharts` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableSolidFuelItems` | `/Game/Dune/Systems/Items/DT_ItemTableSolidFuel.DT_ItemTableSolidFuel` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableAugmentItems` | `/Game/Dune/Systems/Items/DT_ItemTable_Augments.DT_ItemTable_Augments` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DataTableUsageLimitationItems` | `/Game/Dune/Systems/Items/CDT_ItemTableUsageLimitations.CDT_ItemTableUsageLimitations` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `DataAssetItemsAndRecipesToRemove` | `/Game/Dune/Systems/Items/DA_ItemsAndRecipesToRemove.DA_ItemsAndRecipesToRemove` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `StatChangesPerQualityDataAsset` | `/Game/Dune/Systems/Items/Quality/DA_StatChangesPerQuality.DA_StatChangesPerQuality` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `LootQualityPerDifficulty` | `/Game/Dune/Systems/Looting/LootQualityChances/DA_LootQualityDropChancePerItemPerDifficulty.DA_Loo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `HolstersItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Holsters")),QueryTokenStream=(0,1,1,1,0),Use...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `WeaponsItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Holsters.MeleeWeapons"),(TagName="Items.Hols...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AmmoItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Ammo")),QueryTokenStream=(0,1,1,1,0),UserDes...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ToolsItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Holsters.BuildingTools"),(TagName="Items.Hol...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PlayerAbilityItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Abilities.Player")),QueryTokenStream=(0,1,1,...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `VehicleAbilityItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Abilities.Vehicle")),QueryTokenStream=(0,1,1...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `VehicleModuleItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Holsters.Deployables.VehicleBase"),(TagName=...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ConsumableItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Consumables")),QueryTokenStream=(0,1,1,1,0),...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ClothesItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Clothes")),QueryTokenStream=(0,1,1,1,0),User...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `StillsuitItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Clothes.Stillsuit")),QueryTokenStream=(0,1,1...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DeployablesItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Holsters.Deployables")),QueryTokenStream=(0,...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `BuildingPatentItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Consumables.BuildableSets")),QueryTokenStrea...` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `CustomizationItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Consumables.Customizations")),QueryTokenStre...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SchematicsItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Schematics")),QueryTokenStream=(0,1,1,1,0),U...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SolarisItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Solaris")),QueryTokenStream=(0,1,1,1,0),User...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ContractRelatedItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Contract")),QueryTokenStream=(0,1,1,1,0),Use...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MapsItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Maps")),QueryTokenStream=(0,1,1,1,0),UserDes...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ResourcesItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.RawResources"),(TagName="Items.RefinedResour...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `EmotesItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Event.Character.Emote")),QueryTokenStream=(0,1,3,1...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `CompactorItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Holsters.GatheringTools.Compactor")),QueryTo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AugmentItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Augment")),QueryTokenStream=(0,1,1,1,0),User...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AugmentSchematicFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Items.Schematics.Augments")),QueryTokenStream=(0,1...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `RangedWeaponTag` | `(TagName="Items.Holsters.RangedWeapons")` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MeleeWeaponTag` | `(TagName="Items.Holsters.MeleeWeapons")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `OriginsIconItemTagsFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Rarity.Rare"),(TagName="Loot.OldImperial"),(TagNam...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `FremenItemTag` | `(TagName="Loot.Fremen")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `OldImperialItemTag` | `(TagName="Loot.OldImperial")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `GreatHousesItemTag` | `(TagName="Loot.GreatHouse")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `UniqueItemTag` | `(TagName="Rarity.Rare")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MementoItemTag` | `(TagName="Rarity.Memento")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SolidFuelItemTag` | `(TagName="Items.RawResources.Fuel")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `InfluenceItemTag` | `(TagName="Items.Influence")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `LootBlacklistTag` | `(TagName="Items.ExcludeFromLootSystem")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ExchangeBlacklistTag` | `(TagName="Items.ExcludeFromExchange")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ExchangeHiddenItemTag` | `(TagName="Items.HideFromExchange")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PlayerSellToVendorBlacklistTag` | `(TagName="Items.ExcludeFromPlayerSellingToVendor")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PlayerBuyFromVendorBlacklistTag` | `(TagName="Items.ExcludeFromPlayerBuyingFromVendor")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ItemTierParentTag` | `(TagName="LootTier")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ActorBoundItemTag` | `(TagName="Items.ActorBoundItem")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SalvagedMetalTemplateId` | `(Name="ScrapMetal")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `WaterItemTemplateId` | `(Name="WaterItem")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DoubleRecipeApplicableItemFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Rarity.Rare")),QueryTokenStream=(0,1,1,1,0),UserDe...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+LootItemsOrder` | `14 entries; first \`(TokenStreamVersion=0,TagDictionary=((TagName="Items.ShowFirst")),Q...\`` | 14 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+DroppableLootContainers` | `4 entries; first \`(Name="Default")\`` | 4 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+LootContainersToHideWhenEmpty` | `(Name="NpcLootContainer")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `TierIconsMap` | `(((TagName="LootTier.0"), "/Game/Dune/GUI/Textures/Icons/Gameplay/TierIcons/T_UI_IconTierSalvage_...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_TakeSingleItemAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/UI/UI_IGM_PlayerMenu/AD_UI_IGM_Loot_Single.AD_UI_IGM_Loot_Single` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_TakeAllItemsAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/UI/UI_IGM_PlayerMenu/AD_UI_IGM_Loot_Multi.AD_UI_IGM_Loot_Multi` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_InventoryItemHoverAudioEvent` | `None` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `DurabilityPriceCurve` | `/Game/Dune/Systems/Trading/CF_DurabilityPrice.CF_DurabilityPrice` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `FillablePricesPer100Ml` | `(((Name="Blood"), 2),((Name="Fuel"), 25),((Name="Water"), 20))` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `LootSpawnerRandomizedIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Common/T_UI_Icon_QuestionMark_v1_D.T_UI_Icon_QuestionMark_...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `WaterItemIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/PickupNotifications/T_UI_IconPickupWater_D.T_UI_IconPickup...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `ExchangeItemCategoryTree` | `/Game/Dune/GUI/Data/ItemCategories/DA_ExchangeCategoryTree.DA_ExchangeCategoryTree` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `AllCategoryDataClass` | `/Game/Dune/GUI/Data/ItemCategories/BP_AllCategoryData.BP_AllCategoryData_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `ItemTypeCategoryTree` | `/Game/Dune/GUI/Data/ItemCategories/DA_ItemTypeCategoryTree.DA_ItemTypeCategoryTree` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `TechItemTypeCategoryTreeData` | `/Game/Dune/GUI/Data/ItemCategories/DA_TechItemTypeCategoryTree.DA_TechItemTypeCategoryTree` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `VendorBaselineDemand` | `0.050000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MaxSqrDistanceToVendor` | `250000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MaxVendorCycleDuration` | `2419200` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MaxSlotlessItemBuyAmountPerBulk` | `40` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `DemandText` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Vendor_Demand")` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `PositiveDemandTag` | `green` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `NegativeDemandTag` | `red` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `BuyKnowledgeItemGroupText` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/TechTree_Dialog_Buy...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `ItemTypeNameMap` | `((Backpack, LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/INVENTO...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `OriginDataMap` | `(((TagName="Loot.Fremen"), (m_NameToDescTag=(("Fremen", LOCTABLE("/Game/Dune/Localization/ST_Loca...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `TagsToTierDataMap` | `(((TagName="LootTier.0"), Salvage),((TagName="LootTier.1"), Copper),((TagName="LootTier.2"), Iron...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `LootCotainerDistanceThreshold` | `500.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `PerPlayerLootHiddemItemRefreshTime` | `5.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PerPlayerLootMinimumDespawnTimeAfterInteraction` | `30.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MaxLootDifficultyLevel` | `40` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `MaxLootQualityLevel` | `5` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `LootContainerEmissiveLightParamName` | `Light Source - Emissive Power` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `LootContainerEmissiveLightPulseParamName` | `Light Source - Blinking Speed` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `PlayerInventoryStartingSize` | `35` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `PlayerInventoryColumnCount` | `5` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `PlayerInventoryStartingVolumeCapacity` | `175.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `P2pTradingInventoryStartingSize` | `10` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `DecayedMaxDurabilityThreshold` | `0.200000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `EquippedAbilitySpiceAddictionSlotIndex` | `2` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BackpackSortType` | `Free` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `AugmentOriginData` | `(m_NameToDescTag=(),m_Color=(R=0.132868,G=0.084376,B=0.274677,A=1.000000),bShouldInventoryItemsUs...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlayerInboxInventoryMapRestriction` | `((Name="HaggaBasin"), (Name="Editor_Default"), (Name="IGW_Test_Small"))` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.NPESettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_NPEMap` | `/Game/Dune/Maps/NPE2/Levels/NPE2_Main.NPE2_Main` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_NPETutorialDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/NPE/W_MetaDialogImageContent_NPE.W_MetaDialogImageContent_NPE_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.OvermapSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `OvermapMap` | `/Game/Dune/Systems/Overmap/Overmap.Overmap` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_QualitySettings` | `((-1, (ShadowMaxResolution=256,ShadowFadeResolution=32,DFDistanceScale=1.0,DFShadowScatterTileCul...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.MiscSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MiningSettings` | `(CutterayMaxRangeServerLeniencyFactor=3.500000,ServerSplineMeshVerificationEllipseRadii=(X=35.000...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_TargetableActors` | `4 entries; first \`/Script/DuneSandbox.DuneCharacter\`` | 4 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_RegionalFeatureTimeOffsetSeconds` | `0` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_RegionSelectMenuDialogContent` | `/Game/Dune/GUI/Widgets/Menus/Meta/BattlegroupMenu/W_RegionSelectDialogContent.W_RegionSelectDialo...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.InteractionSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_InteractionHintWidgetClass` | `WidgetBlueprintGeneratedClass'/Game/Dune/GUI/Widgets/HUD/InteractionFeedback/W_InteractionHint.W_...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `+m_ActorClassesToHighlight` | `Class'/Script/Engine.Actor'` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_OutlineMesh` | `/Game/Dune/GUI/3D/SM_UnitCube.SM_UnitCube` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_OutlineBuildingMesh` | `/Game/Dune/GUI/3D/SM_UnitCubeOutlineBuilding.SM_UnitCubeOutlineBuilding` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_OutlineStencilValue` | `10` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ColorGradient` | `/Game/Dune/GUI/Data/C_WeldingTorch_Repair_ColorGradient.C_WeldingTorch_Repair_ColorGradient` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_LootPreviewWidget` | `/Game/Dune/GUI/Widgets/HUD/InteractionFeedback/W_LootPreview.W_LootPreview_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_DefaultInteractionIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Us...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_ManageInteractionIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Ma...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PickupInteractionIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Qu...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_VehicleRefuelInteraction` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Re...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_VehicleOpenManagementInteraction` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Ma...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SecondsToShowNPCLootPreview` | `1.200000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_VehicleEnterVehicleInteraction` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Pa...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_VehicleOpenInventoryInteraction` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_St...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_QuickDepositInteractionIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/RadialWheel_InteractionIcons/T_Ui_InteractionWheel_Icon_Pi...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_SecondsToKeepLootPreviewAfterMoving` | `0.400000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ServerInteractionDistanceToleranceSqr` | `2500000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.CommuninetRadioSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_AvailableRadioStations` | `/Game/Dune/Audio/CommuninetRadio/DA_AvailableRadios.DA_AvailableRadios` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[MetaCaptureMemReportCommands]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `PerClass` | `obj list -resourcesizesort` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `RHIRes` | `rhi.DumpResourceMemory` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SK` | `obj list class=SkeletalMesh -resourcesizesort` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SM` | `obj list class=StaticMesh -resourcesizesort` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `Tex` | `ListTextures` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.HazardsSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+m_SinkableMaterials` | `/Game/Dune/Art/PhysicalMaterials/PM_Sand.PM_Sand` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_ModifyDepthEffect` | `BlueprintGeneratedClass'/Game/Dune/Systems/Hazards/Quicksand/BP_Quicksand_AttributeDepth_GE.BP_Qu...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SlowEffect` | `BlueprintGeneratedClass'/Game/Dune/Systems/Hazards/Quicksand/BP_Quicksand_AttributeSpeed_GE.BP_Qu...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SnareEffect` | `BlueprintGeneratedClass'/Game/Dune/Systems/Hazards/Quicksand/BP_QuickSand_Snare_GE.BP_QuickSand_S...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DepthOverrideTag` | `(TagName="Quicksand.QuicksandDepthOverride")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SpeedOverrideTag` | `(TagName="Quicksand.QuicksandSpeedOverride")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CharacterSinkDepthCurve` | `/Game/Dune/Systems/Hazards/Quicksand/Curve_QuickSand_Depth.Curve_QuickSand_Depth` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_VehicleSinkDepthCurve` | `/Game/Dune/Systems/Hazards/Quicksand/Curve_QuickSand_VehicleDepth.Curve_QuickSand_VehicleDepth` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MovementInputContext` | `(Name="QuicksandMovement")` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_InputContextsToAddDuringCombatRestriction` | `2 entries; first \`(Name="TempBuildingBlacklist")\`` | 2 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_InputContextsToRemoveDuringCombatRestriction` | `3 entries; first \`(Name="WeaponEquipped")\`` | 3 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_VehicleQuicksandDamage` | `10000.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RadiationStatusEffectStack` | `BlueprintGeneratedClass'/Game/Dune/Abilities/StatusEffects/RadiationBuildup/BP_Radiation_Stack_GE...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DeathDelayDuration` | `3.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CharacterMaxDepthEffectsDelayDuration` | `5.500000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_VehicleMaxDepthEffectsDelayDuration` | `5.500000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.QuicksandActorComponent]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_QuicksandFX` | `NiagaraSystem'/Game/Dune/Effects/Hazards/Niagara/NS_Haz_Quicksand_PlayerCharacter.NS_Haz_Quicksan...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.UserDefaultSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_RadialWheelGamepadResetAxisDelaySeconds` | `1.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_bDefaultUseHardwareCursor` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_DefaultSprintLock` | `0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MinDesiredAspectRatio` | `(X=16,Y=9)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MinDesiredAspectRatioSteamDeck` | `(X=16,Y=10)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShouldAutoDisplayLandsraadPopup` | `True` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_bHasDisplayedDemoIntroTutorial` | `False` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultDLSSMode` | `Quality` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneCharacterMovementComponent]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MaxSimulationIterationsDefault` | `8` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxSimulationTimeStepDefault` | `0.050000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bAlwaysCheckFloorDefault` | `1` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_MaxSimulationIterationsOptimized` | `2` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxSimulationTimeStepOptimized` | `0.400000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bAlwaysCheckFloorOptimized` | `0` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[Internationalization]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+LocalizationPaths` | `%GAMEDIR%Content/Localization/Game` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.InactivityTimeoutSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_InactivityWarningWidgetClass` | `WidgetBlueprint'/Game/Dune/GUI/Widgets/HUD/W_InactivityTimeoutWarning.W_InactivityTimeoutWarning_C'` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[AdminSetting.Global]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `Password_Admin` | `sardaukar` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+Allowed_Commands` | `6 entries; first \`suicide\`` | 6 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.BootAssetLoaderSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ObjectsToLoad` | `((ObjectRef="/Game/Dune/Systems/Trading/CF_DurabilityPrice.CF_DurabilityPrice",LoadTarget=ClientA...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ClassesToLoad` | `((ClassRef="/Game/Dune/GUI/Data/ItemCategories/BP_AllCategoryData.BP_AllCategoryData_C",LoadTarge...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.PatrolShipSubSystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SpawnTimeSettings` | `(m_TimeOfDayToSpawn=18.000000,m_TimeOfDayToDespawn=6.000000)` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.FactionSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_FactionsMap` | `(((Name="Atreides"), "/Game/Dune/Systems/Faction/Settings/DA_Atreides.DA_Atreides"),((Name="Harko...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_FactionTierLock` | `2` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.JourneySubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultJourneyCinematicSettings` | `(m_CinematicModeSettings=(bShouldHidePlayerPawn=True,bShouldHideHUD=True,bShouldLockAllInput=True...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_JourneyCinematicMap` | `((SpiceDream, "/Game/Dune/Cinematics/Sequencers/SpiceDream/SpiceDream_01/MasterSequence/CINE_Spic...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_ChallengeRoomDataList` | `7 entries; first \`(ChallengeRoomLevel="/Game/Dune/Maps/ChallengeRoom/Levels/Standalon...\`` | 7 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SpiceDreamBlockingEffect` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Abilities/JourneyChallenge/GE_BlockSpiceDream.G...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MapAreaNameOfRegionThatShouldUnblockWhenLeft` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_NPCs_World.ST_Localization_NPCs_World", "NPCS_A...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_JourneyStoryThatShouldBeUnblocked` | `/Game/Dune/Systems/MnemonicRecall/Data/JourneyCards/MainQuests/DA_MQ_ANewBeginning.DA_MQ_ANewBegi...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_JourneyStoriesThatShouldBeRevealed` | `2 entries; first \`DA_MQ_FindTheFremen\`` | 2 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_JourneyStoryUnblockedGameplayTag` | `(TagName="Journey.RewardsUnblocked")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_JourneyStoriesThatUnlocksTechTreeSuggestedCategory` | `DA_SQ_VermiliusGap.Relocate.RelocateOutsideHBS.Drive north to the Vermilius Gap` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ClientCompletableJourneyStories` | `("DA_MQ_ANewBeginning.Building Basics.Craft Building equipment.Place down a Subfief Console","DA_...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_JourneyProgressionStatePresets` | `(((TagName="Journey.ProgressionStates.Initial"), (CompletedJourneys=("DA_MQ_NPEAutocompleted"),Ad...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlayerLeftCrashSiteJourney` | `DA_MQ_NPEAutocompleted.Escape.TalkToZantara` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PlayerReachedFirstRockIslandJourney` | `DA_MQ_NPEAutocompleted.Escape.EscapeTheEnclosure` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SandwormDeathLimboSettings` | `(ChallengeRoomNumber=6,DeathTravelDelayInSeconds=2.000000,JourneyStoryNodePrerequisiteFullName="D...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_BuildMenuHighlightedJourneyStories` | `("DA_MQ_ANewBeginning.Building Basics.Craft Building equipment.Place down a Subfief Console","DA_...` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `+m_TravelRequestFallbackNames` | `3 entries; first \`Arrakeen_to_Overland\`` | 3 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_JourneyStoryTimeoutNotificationDefaultMessageTitle` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Instance_TimeLimit_...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_JourneyStoryTimeoutNotificationDefaultMessageBody` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Instance_TimeLimit_...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/LayeredMaterials.LayeredMaterialSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `LayeredMaterialCategoryEnum` | `/Game/Dune/Systems/Customization/ETransmogPerMaterialCategory.ETransmogPerMaterialCategory` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `LayerCategoryEnum` | `/Game/Dune/Systems/Customization/ETransmogPerLayerCategory.ETransmogPerLayerCategory` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ShowroomsSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultShowrooms` | `((Map, (m_Map="/Game/Dune/Systems/Cartography/CartographyMapShowroom.CartographyMapShowroom")),(C...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.CartographyMapSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_CartographyMapSettings` | `/Game/Dune/Systems/Cartography/CartographyMapSettings.CartographyMapSettings` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_MaxMapRTSize` | `(X=2400,Y=1100)` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.BuildingBlueprintPreviewSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_OffsetDistanceFromBuilding` | `1000.0f` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |
| `m_FullRotationTimeInSeconds` | `15.0f` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |

## `[/Script/DuneSandbox.EntityLodOptimizationSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `Enabled` | `True` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ServerSettingsEnabled` | `True` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `ClientSettingsEnabled` | `False` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `DefaultSettings` | `(PerActorSettings=(("/Script/DuneSandbox.DuneNpcCharacter", (ServerPerLodSettings=((LOD_3, (TickI...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `MapOverrideSettings` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.PermissionSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_PermissionTypesDataAsset` | `/Game/Dune/Systems/PermissionSystem/PermissionTypesConfiguration.PermissionTypesConfiguration` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_LostPermissionsHeadline` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Permission_LostPerm...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LostPermissionsDescription` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Permission_LostPerm...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LostPermissionsHeadlinePopUp` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Permission_LostPerm...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_LostPermissionsDescriptionPopUp` | `LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localization_UI", "UI/Permission_LostPerm...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_PermissionRoleYesIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Grouping/T_UI_Icon_Approve_D.T_UI_Icon_Approve_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PermissionRoleNoIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/Grouping/T_UI_Icon_Decline_D.T_UI_Icon_Decline_D` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_PermissionLevelSettings` | `5 entries; first \`(m_PermissionLevel=Public,m_PermissionName=LOCTABLE("/Game/Dune/Loc...\`` | 5 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RoleEntryWidget` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/Social/Permissions/W_ActorPermissionRoleEntry.W_...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MaxPermissionsPerActor` | `32` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_TakeOverInteractionClass` | `/Script/Engine.BlueprintGeneratedClass'/Game/Dune/Characters/Player/Interactions/Objects/BP_TakeO...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_EditPermissionDialogContentWidget` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/Social/Permissions/EditDialog/W_EditPermissionDi...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.DuneTutorialSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_TutorialCollection` | `(m_Tutorials=(("SandwormDeathTutorial", /Script/DuneSandbox.TutorialBaseData'"/Game/Dune/Systems/...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DeathTutorial` | `(Name="Death")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CoriolisDeathTutorial` | `(Name="CoriolisDeathTutorial")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SandwormDeathTutorial` | `(Name="SandwormDeathTutorial")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SandwormThreatTutorial` | `(Name="SandwormThreat")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ShelterTutorial` | `(Name="Shelter")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_SkillsTutorial` | `(Name="Skills")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_UnspentSkillPointsTutorial` | `(Name="UnspentSkillPoints")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_UnclaimedLandsraadContractsRewardTutorial` | `(Name="UnclaimedLandsraadContractsRewardTutorial")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ExchangeNearbyTutorialEnum` | `(Name="ExchangeNearbyTutorial")` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_FadeInactiveHUDTutorial` | `(Name="FadeInactiveHUDTutorial")` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_TutorialRepositoryList` | `62 entries; first \`SandwormDeathTutorial\`` | 62 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.RespawnSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_RespawnMapSettings` | `(((Name="HaggaBasin"), (bCrossMapDestination=True)),((Name="DeepDesert"), (DisabledGroups=((Name=...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RespawnLocationMapLimit` | `(((Name="Vehicle"), 1),((Name="Checkpoint"), 1),((Name="BaseTotem"), 1),((Name="RespawnBeacon"), ...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_bCrossMapRespawnDropItems` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_IgnoringRespawnTimerSpawnLocationGroup` | `((Name="CheckpointEntrySpawn"),(Name="PlayerStart"))` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ManualRespawnDisabled` | `((Name="Arrakeen"),(Name="HarkoVillage"),(Name="NPE"),(Name="Overland"),(Name="ProcesVerbal"),(Na...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[Datacenters]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `Europe` | `1.1.1.1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `NorthAmerica` | `8.8.8.8` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SouthAmerica` | `8.8.4.4` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `Asia` | `1.1.1.1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `Japan` | `8.8.8.8` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `Tatooine` | `9.9.9.9` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ItemPreviewSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_EquipmentPreviewPose` | `/Game/Dune/Animations/Humans/Common/NoWeapon/Misc/CharCreation/A_Human_CharCreation_Idle_01.A_Hum...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_RotationSpeed` | `10.000000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneExchangeSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `SellOrderDailySolarisFee` | `20` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `SellOrderPricePercentageFee` | `2.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.CoriolisSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_CycleStartYear` | `2024` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CycleStartMonth` | `12` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CycleStartDay` | `3` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CycleStartHour` | `5` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CycleStartMinute` | `0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_CycleDurationInDays` | `7` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_CycleStartSeedIndex` | `0` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_ForcedCoriolisWorldSeed` | `-1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bShouldRestartServerOnCycleEnd` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_bIsDbWipeEnabled` | `True` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[/Script/DuneSandbox.CoriolisSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `+m_IgnoredMarkersList` | `80 entries; first \`(Name="HomeBase")\`` | 80 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.CombatSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_MeleeCombatSettings` | `(DirectionalInputTargetSelection=(DistanceScoreCurve=/Script/Engine.CurveFloat'"/Game/Dune/System...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_NearDeathDamageMitigationCurve` | `/Game/Dune/Systems/DamageSystem/NearDeathDamageMitigation.NearDeathDamageMitigation` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_KnockbackAbility` | `/Game/Dune/Abilities/HeavyStagger/GA_Knockback.GA_Knockback_C` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_PredictedKnockbackDamageTypes` | `2 entries; first \`/Game/Dune/Weapons/Blueprints/DamageTypes/BP_DmgType_Melee.BP_DmgTy...\`` | 2 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_KnockbackEventSettings` | `(((TagName="Event.Character.Knockback.Stumble"), (CharacterTagToApply=(TagName="Character.Knockba...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.TechKnowledgeSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_TechTreeUpgrades` | `/Game/Dune/Systems/TechKnowledge/Data/DA_TechTreeUpgrades.DA_TechTreeUpgrades` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `+m_SuggestedCategoryTiers` | `6 entries; first \`0\`` | 6 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_bRevealItemOnDistributedToCharacter` | `False` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `m_BuildingSetHealthPieceType` | `(Name="Foundation")` | 1 | Inferred | Building/landclaim/placeable setting. Some are server-authoritative; client may also need matching config for placement limits. |

## `[/Script/DuneSandboxAuto.DuneSandboxAutoModuleSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_FindActorTimeout` | `5.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_ServerToClientChunkSize` | `16384` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `+m_AllowedAutomatedCommandLineLevels` | `35 entries; first \`/Game/Dune/Maps/Arrakis/SOC_1/Survival_1.Survival_1\`` | 35 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/AutomatedCommandLine.AutomatedCommandLineModuleSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_FindValidWorldTimeout` | `300.000000` | 1 | Inferred | Timing/cadence key; value appears to be seconds unless the key states another unit. |
| `m_TimeBetweenCommands` | `0.500000` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.PlayerOnlineStateSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultReconnectGracePeriodSeconds` | `300` | 1 | Known | Normal-map reconnect grace period in seconds. |
| `m_OvermapReturnGracePeriodSeconds` | `90` | 1 | Known | Overmap return/reconnect grace period in seconds. |
| `m_InstancedMapReconnectGracePeriodSeconds` | `300` | 1 | Known | Instanced-map reconnect grace period in seconds. |

## `[/Script/DuneSandbox.PartySettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_SocialRange` | `1000000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.MapMarkerZoneSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DefaultMapMarkerZoneSoftClass` | `/Game/Dune/Systems/FullscreenMap/BP_MapMarkerZone.BP_MapMarkerZone_C` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[/Script/DuneSandbox.CharacterStateSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `BlacklistedParentCharacterTagsForGameplayEvent` | `(GameplayTags=((TagName="CharacterState"),(TagName="Character"),(TagName="EnergySystem")))` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |
| `WhitelistedCharacterTagsForGameplayEvent` | `(GameplayTags=((TagName="CharacterState.State.Dead"),(TagName="CharacterState.State.QuicksandDeat...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ExplorationSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_ExplorationVolumeToJourneyNodeNameMap` | `(((TagName="Exploration.Journey.Altar1CaveMarker"), "DA_MQ_FindTheFremen.FirstTest.FirstQuestion....` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneCollisionDefaultSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DuneCollisionSettings` | `/Game/Dune/Core/DA_DuneCollisionSettings.DA_DuneCollisionSettings` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.TaxiService]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_DisableTravelTo` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_DisableTravelFrom` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.DuneSkippableCinematicsSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_CameraModifiersWhitelist` | `(None)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_DefaultSafeZoneRadius` | `5000.000000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_QuickTimeEventsData` | `/Game/Dune/Cinematics/QuickTimeEvents/DA_QuickTimeEvents.DA_QuickTimeEvents` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.LastInteractedPlayersSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_LastInteractedPlayersDialogContentWidget` | `/Game/Dune/GUI/Widgets/Menus/Gameplay/PlayerMenu/LastInteracted/W_LastInteractedPlayersDialogCont...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/DuneSandbox.CharacterRecustomizerSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_CustomizationProxyClass` | `/Game/Dune/Cinematics/CharacterPreviews/BP_CustomizationProxy.BP_CustomizationProxy_C` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_CostAmount` | `5000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.GameContentPackSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_BaseGameContentPack` | `GameContentPack:DA_GameContentPack_BaseGame` | 1 | Inferred | Boolean feature/toggle style key inferred from name; validate in game before changing. |

## `[/Script/DuneSandbox.LootSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `GlobalLootRightsBehaviour` | `PerPlayerChestAndNpcDrop` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.GuildSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_GuildCreationCost` | `1000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MaxGuildsAllowed` | `3` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MaxGuildMembersAllowed` | `32` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MaxPendingGuildInvitesAllowed` | `10` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_GuildRoleSettings` | `((Member, (m_GuildRoleDisplayName=LOCTABLE("/Game/Dune/Localization/ST_Localization_UI.ST_Localiz...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |

## `[ShaderPipelineCache.CacheFile]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `GameVersion` | `1` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.AugmentSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_WeaponStatsGameplayEffects` | `((/Script/Engine.BlueprintGeneratedClass'"/Game/Dune/Abilities/StatusEffects/Burn/BP_Burn_Stack_G...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AttributeToArmorStats` | `(((AttributeName="DashStaminaCost",Attribute=/Script/DuneSandbox.DuneCharacterAttributeSet:DashSt...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |
| `m_AugmentableItemsFilter` | `(TokenStreamVersion=0,TagDictionary=((TagName="Rarity.Rare"),(TagName="LootTier.6")),QueryTokenSt...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_MinimumAugmentableItemQuality` | `0` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_JackpotRollPercentage` | `0.950000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PercentageStepInterval` | `0.001000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_PercentageDecimalCaseThreshold` | `0.050000` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_AugmentJackpotAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/UI/UI_Gameplay/AD_UI_IGM_JackpotRoll.AD_UI_IGM_JackpotRoll` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AugmentStartedMeleeAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/BuildingCrafting/BAC_Placeables/BAC_ModdingStation/AD_BAC_Modding...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AugmentStartedRangedAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/BuildingCrafting/BAC_Placeables/BAC_ModdingStation/AD_BAC_Modding...` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_AugmentStartedArmorAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/BuildingCrafting/BAC_Placeables/BAC_ModdingStation/AD_BAC_Modding...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `m_AugmentStartedStillsuitAudioEvent` | `/Game/Dune/Audio/Events/AAA_NEW/BuildingCrafting/BAC_Placeables/BAC_ModdingStation/AD_BAC_Modding...` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |
| `+m_AugmentTagColorMappings` | `4 entries; first \`(ItemTags=(GameplayTags=((TagName="Items.Augment.Ranged"),(TagName=...\`` | 4 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `+m_AugmentItemTypeTagColorMappings` | `3 entries; first \`(ItemTags=(GameplayTags=((TagName="Items.Holsters.RangedWeapons")))...\`` | 3 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_LockedSlotColor` | `(R=0.184475,G=0.184475,B=0.184475,A=1.000000)` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_UnlearnAugmentIcon` | `/Game/Dune/GUI/Textures/Icons/Gameplay/PickupNotifications/T_UI_IconPickupAugments_D.T_UI_IconPic...` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_MaxRangedWeaponAugments` | `3` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxMeleeWeaponAugments` | `3` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |
| `m_MaxArmorAugments` | `2` | 1 | Inferred | Numeric limit/scaling/distance key inferred from name; validate before changing. |

## `[/Script/DuneSandbox.PlayerRequestSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_NotificationTimeoutBufferInSeconds` | `0.250000` | 1 | UI/visual | UI, visual, marker, camera, or presentation setting. Usually low value for server tuning. |
| `m_PlayerRequestSystemStaticData` | `((Dueling, (NotificationType=(Name="DuelingPlayerRequestMessage"),ReceiverData=(Message=NSLOCTEXT...` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.TravelDestinationSubsystem]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_TravelDestinationsDataAsset` | `/Game/Dune/Systems/Travel/DA_TravelDestinations.DA_TravelDestinations` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

## `[/Script/Engine.NetworkActorSpawnConfig]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `m_Entries` | `()` | 1 | Unknown / investigate | Shipped config key. Exact runtime behavior needs validation before overriding. |

## `[/Script/DuneSandbox.ReturningPlayerSettings]`

| Key | Shipped value / summary | Count | Status | Description |
| --- | --- | ---: | --- | --- |
| `ReturningPlayerRewardsDataAsset` | `/Game/Dune/Characters/Player/Config/DA_ReturningPlayerRewards.DA_ReturningPlayerRewards` | 1 | Asset/reference | Asset, class, table, material, widget, audio, or data reference. Usually not a self-host gameplay knob. |

