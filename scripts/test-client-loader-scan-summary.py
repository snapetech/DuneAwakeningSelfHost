#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-client-loader-scan.py",
    ROOT / "analysis" / "summarize-client-loader-scan.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("summarize_client_loader_scan", SCRIPT)
scan_summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(scan_summary)


SAMPLE_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\windows\\system32\\rundll32.exe dll=Z:\\repo\\version.dll native=pe note=not-ue4ss-yet
2026-06-16T17:43:39Z pid=312 loader=win-client event=module base=0x140000000 firstRegion=0x140000000 protect=0x2 path=C:\\windows\\system32\\rundll32.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-start strings=3 signatures=1 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=FNamePool addr=0x140010000 rva=0x10000 allocationBase=0x140000000 regionBase=0x140010000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=GName addr=0x140011000 rva=0x11000 allocationBase=0x140000000 regionBase=0x140011000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=ProcessEvent addr=0x140020000 rva=0x20000 allocationBase=0x140000000 regionBase=0x140020000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor name=GUObjectArray group=objects status=mapped addr=0x140030000 rva=0x30000 allocationBase=0x140000000 regionBase=0x140030000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-candidate-global name=GUObjectArray status=added address=0x140030000 imageOffset=0x30000 absolute=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor name=GWorld group=world status=unmapped addr=0x1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GWorld group=world status=resolved hit=0x140020100 addr=0x140040000 transform=riprel32+3 rva=0x40000 allocationBase=0x140000000 regionBase=0x140040000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticFindObject group=dispatch status=missing oversizedRegions=0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-pointer name=GUObjectArray status=target-mapped anchor=0x140030000 value=0x140050000 rva=0x50000 allocationBase=0x140000000 regionBase=0x140050000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-pointer name=GWorld status=anchor-unmapped anchor=0x1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-layout name=GUObjectArray status=target-readable anchor=0x140030000 target=0x140050000 slots=2 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-layout-slot name=GUObjectArray target=0x140050000 offset=0x0 value=0x140060000 status=target-mapped readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-layout-slot name=GUObjectArray target=0x140050000 offset=0x8 value=0x0 status=null
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-uobject status=added name=GUObjectArray path=/RuntimeProbe/GUObjectArray class=UObjectCandidate address=0x140050000 registryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-uobject status=passed name=GUObjectArray path=/RuntimeProbe/GUObjectArray class=UObjectCandidate address=0x140050000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-uobject name=GUObjectArray status=candidate anchor=0x140030000 target=0x140050000 vtable=0x140060000 vtableMapped=true objectFlags=0x11 internalIndex=7 class=0x140050000 classMapped=true nameComparisonIndex=1234 nameNumber=1 outer=0x0 outerMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection name=GUObjectArray status=class-mapped object=0x140050000 class=0x140050000 classVtable=0x140060000 classVtableMapped=true classNameComparisonIndex=1234 classNameNumber=1 slots=6 nextOffset=0x28 superOffset=0x30 childrenOffset=0x38 childPropertiesOffset=0x40 propertyLinkOffset=0x48 functionLinkOffset=0x50
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-slot name=GUObjectArray slot=children status=target-mapped class=0x140050000 offset=0x38 value=0x140060000 readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-slot name=GUObjectArray slot=propertyLink status=target-mapped class=0x140050000 offset=0x48 value=0x140060000 readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-slot name=GUObjectArray slot=functionLink status=target-mapped class=0x140050000 offset=0x50 value=0x140060000 readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-fname source=ue-reflection-field objectName=GUObjectArray.children_0 status=decoded object=0x140060000 pool=0x1400a0000 resolver=FNamePool:direct comparisonIndex=1234 number=1 block=0 offset=0x4d2 entry=0x1400b1348 wide=false decoded=DecodedField_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-field name=GUObjectArray chain=children index=0 status=candidate field=0x140060000 class=0x140050000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-field name=GUObjectArray chain=propertyLink index=0 status=candidate field=0x140061000 class=0x140050000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-ffield-layout-candidate name=GUObjectArray chain=propertyLink index=0 layout=ffield-ue4 field=0x140061000 classOffset=0x8 class=0x140050000 classReadable=true classMapped=true classNameOffset=0x0 classNameReadable=true fieldClassName=FIntProperty fieldClassLooksProperty=true nameOffset=0x20 nameReadable=true fieldName=DecodedField_0 nameComparisonIndex=1234 nameNumber=1 nextOffset=0x18 next=0x0 nextReadable=true nextMapped=false descriptorLayout=fproperty-ue4 descriptorSane=true arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-property-root-scan name=GUObjectArray status=candidate class=0x140050000 offset=0x60 root=0x140061000 rootReadable=true rootMapped=true descriptorLayout=fproperty-ue4 descriptorSane=true arrayDim=1 elementSize=4 offsetInternal=12
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-property-root-scan name=GUObjectArray status=complete class=0x140050000 scanned=32 candidates=1 start=0x28 end=0x180
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-field name=GUObjectArray chain=functionLink index=0 status=candidate field=0x140062000 class=0x140050000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param-root name=GUObjectArray functionIndex=0 chain=childProperties status=root function=0x140062000 offset=0x40 root=0x140063000 functionFlags=0x400 functionFlagsReadable=true functionFlagsOffset=0x58
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-native-identity source=ue-function-param status=promoted name=GUObjectArray functionIndex=0 chain=childProperties function=0x140062000 functionName=DecodedFunction_0 functionPath=/Script/GUObjectArray.DecodedFunction_0:Function functionRuntimePath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function root=0x140063000 functionFlags=0x400 functionFlagsReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-function-registry-check source=ue-function-param status=passed name=DecodedFunction_0 path=/Script/GUObjectArray.DecodedFunction_0:Function runtimePath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function address=0x140062000 pathHit=true runtimePathHit=true nameHit=true addressHit=true flagsHit=true registryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param name=GUObjectArray functionIndex=0 chain=childProperties index=0 status=candidate function=0x140062000 functionName=DecodedFunction_0 functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function field=0x140063000 class=0x140050000 classMapped=true nameComparisonIndex=1234 nameNumber=1 fieldName=DecodedParam_0 arrayDim=1 elementSize=4 propertyFlags=0x80 offsetInternal=16 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true functionFlags=0x400 functionFlagsReadable=true next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param-container-child name=GUObjectArray functionIndex=0 chain=childProperties index=0 status=candidate field=0x140063000 containerClassName=FArrayProperty role=inner child=0x140064000 childOffset=0x70 childClass=0x140050000 childClassMapped=true childClassName=FIntProperty childNameComparisonIndex=1235 childNameNumber=1 childName=DecodedArrayInner_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param-root name=GUObjectArray functionIndex=0 chain=propertyLink status=null-root function=0x140062000 offset=0x48
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-property name=GUObjectArray descriptorProvenance=runtime chain=childProperties index=0 status=candidate field=0x140061000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-property name=GUObjectArray descriptorProvenance=runtime chain=propertyLink index=0 status=candidate field=0x140061000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-value name=GUObjectArray descriptorProvenance=runtime chain=childProperties index=0 fieldName=DecodedField_0 status=read object=0x140050000 address=0x14005000c offsetInternal=12 elementSize=4 arrayDim=1 requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-value name=GUObjectArray descriptorProvenance=runtime chain=propertyLink index=0 fieldName=DecodedField_0 status=read object=0x140050000 address=0x14005000c offsetInternal=12 elementSize=4 arrayDim=1 requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-fname source=ue-uobject objectName=GUObjectArray status=decoded object=0x140050000 pool=0x1400a0000 resolver=FNamePool:direct comparisonIndex=1234 number=1 block=0 offset=0x4d2 entry=0x1400b1348 wide=false decoded=DecodedObject_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-native-identity source=ue-uobject status=promoted object=0x140050000 name=DecodedObject_0 class=0x140050000 className=DecodedClass_0 outer=0x0 nameDecoded=true classNameDecoded=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-uobject-fname status=added name=DecodedObject_0 path=/RuntimeProbe/DecodedObject_0 aliasOf=GUObjectArray class=UObjectCandidate address=0x140050000 registryCount=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-uobject-fname status=passed name=DecodedObject_0 path=/RuntimeProbe/DecodedObject_0 class=UObjectCandidate address=0x140050000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array-shape name=GUObjectArray mode=direct status=header-implausible base=0x14006fff0 chunks=0x140080000 maxElements=1 numElements=2 maxChunks=1 numChunks=1 countsPlausible=false chunkSlotReadable=true firstChunk=0x140081000 firstChunkMapped=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array-shape name=GUObjectArray mode=indirect status=header-plausible base=0x140070000 chunks=0x140080000 maxElements=2 numElements=1 maxChunks=1 numChunks=1 countsPlausible=true chunkSlotReadable=true firstChunk=0x140081000 firstChunkMapped=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array name=GUObjectArray mode=indirect status=scanning base=0x140070000 chunks=0x140080000 maxElements=2 numElements=1 maxChunks=1 numChunks=1 limit=1 itemSize=24 chunkSize=65536
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-object-array status=added name=GUObjectArray_0 path=/RuntimeProbe/GUObjectArray_0 class=UObjectArrayItem address=0x140050000 registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-object-array status=passed name=GUObjectArray_0 path=/RuntimeProbe/GUObjectArray_0 class=UObjectArrayItem address=0x140050000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-outer-chain status=resolved object=0x140055000 path=/RuntimeProbe/ChildObject class=UObjectCandidate outer=0x140050000 depth=1 terminal=0x140050000 terminalPath=/RuntimeProbe/GUObjectArray terminalClass=UObjectCandidate chain=/RuntimeProbe/ChildObject<-/RuntimeProbe/GUObjectArray reconstructedPath=/RuntimeProbe/GUObjectArray.ChildObject reconstructedFullName=UObjectCandidate_/RuntimeProbe/GUObjectArray.ChildObject fullNameResolved=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-global-runtime-helper-check status=passed globalWorld=true globalWorldPromoted=true globalWorldAddress=0x140050000 globalWorldPath=/RuntimeProbe/GUObjectArray_0 globalWorldClass=UObjectArrayItem globalEngine=true globalEnginePromoted=false globalEngineAddress=0x140120000 globalEnginePath=/RuntimeProbe/Engine globalEngineClass=UEngine getWorldCalls=3 getWorldHits=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array-item name=GUObjectArray index=0 status=registered object=0x140050000 class=0x140050000 outer=0x0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-fname source=ue-object-array objectName=GUObjectArray_0 status=decoded object=0x140050000 pool=0x1400a0000 resolver=FNamePool:direct comparisonIndex=1234 number=1 block=0 offset=0x4d2 entry=0x1400b1348 wide=false decoded=DecodedObject_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-native-identity source=ue-object-array status=promoted object=0x140050000 name=DecodedObject_0 class=0x140050000 className=DecodedClass_0 outer=0x0 nameDecoded=true classNameDecoded=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-object-array-fname status=skipped name=DecodedObject_0 path=/RuntimeProbe/DecodedObject_0 aliasOf=GUObjectArray_0 class=UObjectArrayItem address=0x140050000 registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-object-array-fname status=passed name=DecodedObject_0 path=/RuntimeProbe/DecodedObject_0 class=UObjectArrayItem address=0x140050000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array name=GUObjectArray mode=indirect status=finished base=0x140070000 scanned=1 registered=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=hook-dispatch name=SelfTestHook status=installed target=0x140090000 replacement=0x140091000 trampoline=0x140092000 patchBytes=12
2026-06-16T17:43:39Z pid=312 loader=win-client event=hook-dispatch name=SelfTestHook status=restored target=0x140090000
2026-06-16T17:43:39Z pid=312 loader=win-client event=hook-dispatch-self-test phase=thread status=passed before=42 after=1042 final=42 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 installed=true restored=true target=0x140090000 replacement=0x140091000 trampoline=0x140092000
2026-06-16T17:43:39Z pid=312 loader=win-client event=mod-dispatch-self-test phase=thread status=passed mods=1 loaded=1 unloaded=1 result=1042 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 loadCallbacks=1 unloadCallbacks=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-dispatch-self-test phase=thread status=passed library=lua54.dll loadStatus=0 callStatus=0 callbackStatus=0 result=42 isNumber=true hooks=1 hook=/Script/DuneProbe.SelfTest:Function preRef=3 postRef=4 preCalls=1 postCalls=1 preResult=11 postResult=31 preIsNumber=true postIsNumber=true objectHandles=5 ueObjectHandles=2 staticFindObjectCalls=1 staticFindObjectHits=1 findObjectCalls=1 findObjectHits=1 findFirstOfCalls=1 findFirstOfHits=1 getKnownObjectsCalls=1 getKnownObjectsHits=1 findObjectsCalls=1 findObjectsHits=1 findAllOfCalls=1 findAllOfHits=1 forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=6 isAHits=5 loadAssetCalls=1 loadAssetHits=1 staticConstructObjectCalls=1 staticConstructObjectHits=1 notifyOnNewObjectCalls=1 notifyOnNewObjectCallbacks=1 notifyOnNewObjectResult=17 notifyOnNewObjectIsNumber=true notifyOnNewObjectStatus=0 executeInGameThreadCalls=1 executeInGameThreadCallbacks=1 executeInGameThreadResult=9 executeInGameThreadIsNumber=true executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2 executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 keyBindRegistrations=1 keyBindLookupCalls=2 keyBindLookupHits=1 keyBindDispatchCalls=2 keyBindCallbackCalls=1 keyBindCallbackHandled=1 keyBindUnregisterCalls=1 keyBindUnregisterHits=1 consoleCommandHandlers=2 consoleCommandGlobalHandlers=1 consoleCommandHandlerCalls=1 consoleCommandHandlerHandled=0 consoleCommandGlobalHandlerCalls=1 consoleCommandGlobalHandlerHandled=1 consoleCommandUnregisterCalls=1 consoleCommandUnregisterHits=1 scriptBytes=612
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-reflection-self-test phase=thread status=passed library=lua54.dll loadStatus=0 callStatus=0 result=42 isNumber=true staticFindObjectCalls=2 staticFindObjectHits=2 getPropertyCalls=20 getPropertyHits=20 rawPropertyHits=2 rawPropertyValue=17 namedPropertyHits=2 rawPropertySetHits=1 rawPropertySetValue=17 arrayInnerPropertyHits=1 enumPropertyHits=1 enumUnderlyingPropertyHits=1 setElementPropertyHits=1 mapKeyPropertyHits=1 mapValuePropertyHits=1 importTextHits=2 exportTextHits=2 propertyMetadataHits=7 descriptorValueGetHits=21 descriptorValueSetHits=9 descriptorValueAliasHits=3 reflectionForEachPropertyHits=2 runtimeReflectionForEachPropertyCallbacks=0 selfTestReflectionForEachPropertyCallbacks=14 liveDescriptorTypedClassHits=1 runtimeLiveDescriptorTypedClassHits=0 selfTestLiveDescriptorTypedClassHits=1 liveDescriptorTypedValueHits=1 runtimeLiveDescriptorTypedValueHits=0 selfTestLiveDescriptorTypedValueHits=1 liveDescriptorTypedValueSetHits=1 runtimeLiveDescriptorTypedValueSetHits=0 selfTestLiveDescriptorTypedValueSetHits=1 liveDescriptorValueGetHits=2 liveDescriptorValueSetHits=1 runtimeLiveDescriptorValueGetHits=0 selfTestLiveDescriptorValueGetHits=2 runtimeLiveDescriptorValueSetHits=0 selfTestLiveDescriptorValueSetHits=1 setPropertyCalls=10 setPropertyHits=10 callFunctionCalls=2 callFunctionHits=2 probeValue=21 probeBool=false probeFloat=13.750 probeDouble=-47.500 probeName=ArrakisName probeString=melange probeText=WaterDebt probeObject=0x1234 objectHandles=3 ueObjectHandles=2 scriptBytes=2200
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-process-event-self-test phase=thread status=passed library=lua54.dll loadStatus=0 callStatus=0 result=4 isNumber=true hooks=2 hook=/Script/DuneProbe.SelfTest:Function installed=true restored=true hookCalls=1 originalCalls=2 originalAfterHook=1 preStatus=0 postStatus=0 preCalls=1 postCalls=1 preResult=11 postResult=31 preIsNumber=true postIsNumber=true pathExactMatches=2 pathAliasMatches=0 paramDescriptorHits=2 paramDescriptorLookupCalls=17 paramDescriptorLookupHits=17 functionParamDescriptorCalls=2 functionParamDescriptorHits=4 functionParamMethodHits=2 functionParamLookupMethodHits=2 functionParamIterationMethodHits=12 containerAliasHits=6 containerStorageLayoutHits=9 paramGetCalls=29 paramGetHits=29 paramSetCalls=11 paramSetHits=11 enumParamAccessors=true objectParamAccessors=true boolParamAccessors=true paramsResult=42 paramsTouched=1 finalResult=52 finalTouched=1 object=0x140050000 function=0x140061000 params=0x20 trampoline=0x140092000 scriptBytes=103
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-call-function-hook phase=thread status=passed target=0x140041000 installed=true restored=true selfTestTarget=false callSelfTest=false before=0 after=0 final=0 original=0 trampoline=0x1400c1000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-call-function-live-hook phase=thread status=installed target=0x140041000 selfTestTarget=false callSelfTest=false liveCalls=0 originalCalls=0 result=0 trampoline=0x1400c2000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-dispatch-self-test phase=thread status=armed preRegistered=true postRegistered=true callbacks=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-lua-dispatch phase=thread status=armed library=lua54.dll loadStatus=0 callStatus=0 result=4 isNumber=true hooks=2 hook=/Script/DuneProbeAlias.SelfTestUObjectName_0:Function callbacks=4 scriptBytes=111
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-context status=resolved call=1 object=0x140050000 objectResolved=true objectPath=/RuntimeProbe/GUObjectArray objectClass=UObjectCandidate function=0x140062000 functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function functionProvenance=runtime functionParamDescriptors=1 params=0x20 paramsPresent=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-registry-context status=resolved call=1 object=0x140050000 objectResolved=true objectNativeIdentity=true objectPath=/RuntimeProbe/GUObjectArray objectClass=UObjectCandidate function=0x140062000 functionResolved=true functionNativeIdentity=true functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function functionRuntimePath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function functionProvenance=runtime functionParamDescriptors=1 params=0x20 paramsPresent=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=read call=1 function=0x140062000 functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function param=DecodedParam_0 className=FIntProperty type=int32 offset=16 size=4 value=62
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=raw call=1 function=0x140062000 functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function param=DecodedStruct_0 className=FStructProperty type=struct offset=24 size=16 value=rawHex=0102030405060708090a0b0c0d0e0f10
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=container call=1 function=0x140062000 functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function param=DecodedArray_0 className=FArrayProperty type=array offset=40 size=16 value=kind=FScriptArray,data=0x1400f0000,num=2,max=4,rawHex=00000f40010000000200000004000000,dataSampleHex=2a0000002b0000002c0000002d000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-hook phase=thread status=installed target=0x140040000 selfTestTarget=true callSelfTest=true dispatchCallbacks=4 luaDispatch=true luaPreStatus=0 luaPostStatus=0 luaPreCalls=1 luaPostCalls=1 luaObjectHandleHits=2 luaFunctionHandleHits=2 luaParamsHandleHits=2 luaParamDescriptorHits=2 luaParamDescriptorLookupCalls=17 luaParamDescriptorLookupHits=17 luaFunctionParamDescriptorCalls=2 luaFunctionParamDescriptorHits=4 luaFunctionParamMethodHits=2 luaFunctionParamLookupMethodHits=2 luaFunctionParamIterationMethodHits=12 luaContainerAliasHits=6 luaContainerStorageLayoutHits=9 luaParamGetCalls=29 luaParamGetHits=29 luaParamSetCalls=11 luaParamSetHits=11 luaEnumParamAccessors=true luaObjectParamAccessors=true luaBoolParamAccessors=true preCallbacks=2 postCallbacks=2 liveCalls=1 originalCalls=1 paramsResult=62 paramsTouched=1 trampoline=0x1400d0000
2026-06-16T17:43:40Z pid=312 loader=win-client event=ue-process-event-live-lua-dispatch phase=detach status=closed preCalls=1 postCalls=1 preResult=11 postResult=31 preStatus=0 postStatus=0 pathExactMatches=0 pathAliasMatches=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-start phase=thread status=running library=lua54.dll scripts=2 skipped=0
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-script phase=thread status=passed name=CallbackMod path=C:\\mods\\CallbackMod\\Scripts\\main.lua loadStatus=0 callStatus=0 hooksBefore=0 hooksAfter=1 scriptBytes=100
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-script phase=thread status=passed name=CallbackModTwo path=C:\\mods\\CallbackModTwo\\Scripts\\main.lua loadStatus=0 callStatus=0 hooksBefore=1 hooksAfter=2 scriptBytes=100
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-dispatch-self-test phase=thread status=passed callbackStatus=0 hooks=2 hook=/Script/DuneProbe.ModEntry:Function preCalls=2 postCalls=2 preResult=11 postResult=31 preIsNumber=true postIsNumber=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-function-iteration-check source=ForEachFunction status=passed mode=self-test name=DuneProbeSelfTestClass class=UClass callbacks=2 functionRegistryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-finish phase=thread status=passed library=lua54.dll scripts=2 loaded=2 failed=0 hooks=2 skipped=0 objectHandles=4 ueObjectHandles=2 staticFindObjectCalls=1 staticFindObjectHits=1 findObjectCalls=1 findObjectHits=1 findFirstOfCalls=1 findFirstOfHits=1 getKnownObjectsCalls=1 getKnownObjectsHits=1 findObjectsCalls=1 findObjectsHits=1 findAllOfCalls=1 findAllOfHits=1 forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 staticConstructObjectCalls=1 staticConstructObjectHits=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-finish
2026-06-16T17:43:40Z pid=332 loader=win-client event=forward-smoke function=GetFileVersionInfoSizeW result=1812 handle=0x0
"""

SAMPLE_LOG = SAMPLE_LOG.replace(
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=6",
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 forEachFunctionCalls=0 forEachFunctionCallbacks=0 isACalls=6",
)
SAMPLE_LOG = SAMPLE_LOG.replace(
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=5",
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 forEachFunctionCalls=2 forEachFunctionCallbacks=2 isACalls=5",
)
SAMPLE_LOG = SAMPLE_LOG.replace(
    "staticConstructObjectCalls=1 staticConstructObjectHits=1\n",
    (
        "staticConstructObjectCalls=1 staticConstructObjectHits=1 "
        "notifyOnNewObjectCalls=4 notifyOnNewObjectCallbacks=2 "
        "notifyOnNewObjectResult=19 notifyOnNewObjectIsNumber=true "
        "notifyOnNewObjectStatus=0 staticConstructObjectOuterHits=1 "
        "getWorldCalls=3 getWorldHits=2 "
        "getCdoCalls=1 getCdoHits=1 getLevelCalls=2 getLevelHits=2\n"
    ),
)
SAMPLE_LOG = SAMPLE_LOG.replace(
    "hooks=2 skipped=0 objectHandles=4",
    (
        "hooks=2 customEvents=1 customEventCalls=1 customEventHandled=1 "
        "loadMapPreHooks=1 loadMapPostHooks=1 loadMapPreCalls=1 loadMapPostCalls=1 "
        "loadMapPreHandled=1 loadMapPostHandled=1 "
        "beginPlayPreHooks=1 beginPlayPostHooks=1 beginPlayPreCalls=1 beginPlayPostCalls=1 "
        "beginPlayPreHandled=1 beginPlayPostHandled=1 "
        "initGameStatePreHooks=1 initGameStatePostHooks=1 "
        "initGameStatePreCalls=1 initGameStatePostCalls=1 "
        "initGameStatePreHandled=1 initGameStatePostHandled=1 "
        "processConsoleExecPreHooks=1 processConsoleExecPostHooks=1 "
        "processConsoleExecPreCalls=2 processConsoleExecPostCalls=2 "
        "processConsoleExecPreHandled=1 processConsoleExecPostHandled=1 "
        "localPlayerExecPreHooks=1 localPlayerExecPostHooks=1 "
        "localPlayerExecPreCalls=2 localPlayerExecPostCalls=2 "
        "localPlayerExecPreHandled=1 localPlayerExecPostHandled=1 "
        "callFunctionPreHooks=1 callFunctionPostHooks=1 "
        "callFunctionPreCalls=2 callFunctionPostCalls=1 "
        "callFunctionPreHandled=1 callFunctionPostHandled=1 "
        "callFunctionTableArgCalls=1 callFunctionArgFieldHits=10 "
        "callFunctionArgStructHits=1 processEventCompatCalls=2 processEventCompatHits=2 processEventBridgeStateCalls=1 processEventNativeCalls=0 processEventNativeHits=0 executeInGameThreadCalls=1 "
        "executeInGameThreadCallbacks=1 executeInGameThreadResult=9 "
        "executeInGameThreadIsNumber=true executeAsyncCalls=1 "
        "executeAsyncCallbacks=1 executeWithDelayCalls=2 "
        "executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 "
        "schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 "
        "keyBindLookupCalls=2 keyBindLookupHits=1 keyBindDispatchCalls=1 "
        "keyBindCallbackCalls=1 keyBindCallbackHandled=1 "
        "keyBindUnregisterCalls=2 keyBindUnregisterHits=2 "
        "consoleCommandHandlers=3 consoleCommandGlobalHandlers=1 "
        "consoleCommandHandlerCalls=3 consoleCommandHandlerHandled=3 "
        "consoleCommandGlobalHandlerCalls=3 consoleCommandGlobalHandlerHandled=0 "
        "consoleCommandUnregisterCalls=1 consoleCommandUnregisterHits=1 "
        "skipped=0 objectHandles=4"
    ),
)
SAMPLE_LOG += (
    "2026-06-16T00:00:16Z pid=123 loader=win-client event=lua-process-event-params-buffer "
    "status=created function=0x2000 descriptorCount=17 size=152 address=0x3000\n"
    "2026-06-16T00:00:16Z pid=123 loader=win-client event=lua-process-event-native-invoke "
    "phase=smoke status=descriptor-preflight-ready objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=false nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=0 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:17Z pid=123 loader=win-client event=lua-process-event-native-invoke "
    "phase=smoke status=non-self-test-invoke-disabled objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=true nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=0 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:18Z pid=123 loader=win-client event=lua-process-event-native-invoke-self-test "
    "phase=smoke status=passed processEventNativeCalls=3 processEventNativeHits=1 liveCalls=2 originalCalls=2\n"
    "2026-06-16T00:00:18Z pid=123 loader=win-client event=lua-process-event-native-executor-state "
    "status=prepared bridgeArmed=true objectAllowed=true functionAllowed=true "
    "objectRegistryAllowed=true functionDescriptorAllowed=true selfTestCallable=false "
    "descriptorBackedCallable=true nativeCallable=true nativeNonSelfTestEnabled=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 nativeExecutorBlockReason=none nativeInvoked=false "
    "object=0x1000 function=0x2000\n"
    "2026-06-16T00:00:19Z pid=123 loader=win-client event=lua-call-function-native-invoke "
    "phase=smoke status=preflight-ready objectRegistryAllowed=true selfTestCallable=false "
    "invokeRequested=false nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "object=0x1000 function=DoubleProbeValue args= forceCall=true result=0 "
    "liveCallsBefore=2 liveCallsAfter=2 originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:20Z pid=123 loader=win-client event=lua-call-function-native-invoke "
    "phase=smoke status=non-self-test-invoke-disabled objectRegistryAllowed=true "
    "selfTestCallable=false invokeRequested=true nativeNonSelfTestEnabled=false "
    "nativeNonSelfTestInvoked=false object=0x1000 function=DoubleProbeValue args= "
    "forceCall=true result=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:21Z pid=123 loader=win-client event=lua-call-function-native-invoke-self-test "
    "phase=smoke status=passed callFunctionNativeCalls=3 callFunctionNativeHits=1 liveCalls=2 originalCalls=3\n"
    "2026-06-16T00:00:21Z pid=123 loader=win-client event=lua-call-function-native-executor-state "
    "status=prepared bridgeArmed=true objectAllowed=true functionAllowed=true "
    "objectRegistryAllowed=true selfTestCallable=false nativeCallable=true "
    "nativeNonSelfTestEnabled=false object=0x1000 function=DoubleProbeValue args= "
    "forceCall=true nativeExecutorBlockReason=none nativeInvoked=false\n"
)


def new_loader_identity_sample(log):
    return log.replace(
        "functionPath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function",
        "functionPath=/Script/GUObjectArray.DecodedFunction_0:Function functionRuntimePath=/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function",
    )


class ClientLoaderScanSummaryTests(unittest.TestCase):
    def test_runtime_discovery_summary_promoted_roots(self):
        log = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded exe=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x140060000 blockSlot=0x140060010 firstBlock=0x140080000 blocksOffset=0x10 stride=2 hit=1 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140070000 base=0x140070000 numElements=42 numChunks=1 hit=1 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x140060000 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x140070000 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=1 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=2
"""
        records = [scan_summary.parse_line(line) for line in log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])

        self.assertFalse(summary["ueRuntimeDiscoveryReady"])
        self.assertEqual(summary["ueRuntimeDiscoveryFailure"], "unvalidated-root-hits")
        self.assertEqual(summary["ueRuntimeDiscoveryCandidateCount"], 2)
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["candidateNameCounts"],
            {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 1},
        )
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["candidateImageCounts"],
            {"C:\\game\\DuneSandbox-Win64-Shipping.exe": 2},
        )
        self.assertEqual(
            [item["imageOffset"] for item in summary["ueRuntimeDiscovery"]["candidateLocations"]],
            ["0x60000", "0x70000"],
        )
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["promotedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(summary["ueRuntimeDiscovery"]["validatedNames"], [])
        self.assertEqual(summary["ueRuntimeDiscovery"]["coverage"]["targetWritableImageCount"], 2)
        self.assertEqual(summary["ueRuntimeDiscovery"]["coverage"]["objectArrayProbes"], 2048)

    def test_zero_count_runtime_guobjectarray_validation_is_ignored(self):
        log = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded exe=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140070000 base=0x140070000 numElements=42 numChunks=1 hit=1 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x140070000 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-object-array name=RuntimeGUObjectArray mode=direct status=empty base=0x140070000 chunks=0x0 maxElements=0 numElements=0 maxChunks=0 numChunks=0
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-object-array-finish phase=thread registryCount=0
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-root-validation phase=thread name=RuntimeGUObjectArray status=validated consumer=object-array registryCount=0
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=0 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=0 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=1
"""
        records = [scan_summary.parse_line(line) for line in log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])

        self.assertFalse(summary["ueRuntimeDiscoveryReady"])
        self.assertNotIn(
            "RuntimeGUObjectArray",
            summary["ueRuntimeDiscovery"]["rootValidationNames"],
        )
        self.assertEqual(summary["ueRuntimeDiscovery"]["consumerValidatedNames"], [])
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["validatedBy"]["objectArrayRegistryFinishes"],
            0,
        )

    def test_runtime_discovery_summary_classifies_missing_target_writable_region(self):
        log = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded exe=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery name=target-writable-image-regions status=missing phase=thread
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery name=RuntimeFNamePool status=missing hits=0
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery name=RuntimeGUObjectArray status=missing hits=0
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=0 objectArrayHits=0 targetWritableRegions=0 oversizedRegions=0 scannedSlots=0 fnameProbes=0 objectArrayProbes=0 anchors=0
"""
        records = [scan_summary.parse_line(line) for line in log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])

        self.assertFalse(summary["ueRuntimeDiscoveryReady"])
        self.assertEqual(summary["ueRuntimeDiscoveryFailure"], "no-target-writable-image")
        self.assertEqual(summary["ueRuntimeDiscovery"]["targetWritableMissingCount"], 1)
        self.assertEqual(summary["ueRuntimeDiscovery"]["statusCounts"], {"missing": 2})

    def test_exe_filter_scopes_to_target_pid_for_rows_without_exe(self):
        log = """\
2026-06-18T00:00:00Z pid=10 loader=server event=loaded exe=/usr/bin/dash
2026-06-18T00:00:00Z pid=10 loader=server event=ue-anchor name=GUObjectArray group=objects status=unmapped addr=0x1
2026-06-18T00:00:01Z pid=20 loader=server event=loaded exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=20 loader=server event=scan-start strings=1 signatures=0 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-18T00:00:01Z pid=20 loader=server event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x550000 rva=0x5000 module=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=20 loader=server event=ue-runtime-discovery-start phase=snapshot maxMappingBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=20 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x550000 base=0x550000 numElements=42 numChunks=1 hit=1 rva=0x5000 module=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=20 loader=server event=ue-runtime-discovery-finish phase=snapshot fnameHits=0 objectArrayHits=1 targetWritableMappings=1 oversizedMappings=0 scannedSlots=64 fnameProbes=64 objectArrayProbes=64 anchors=1
2026-06-18T00:00:01Z pid=20 loader=server event=scan-finish
"""
        records = [scan_summary.parse_line(line) for line in log.splitlines()]
        summary = scan_summary.summarize(
            records,
            loader_filter=["server"],
            exe_substrings=["DuneSandbox"],
        )

        self.assertEqual(summary["targetPidsFromExe"], ["20"])
        self.assertEqual(summary["effectivePidFilter"], ["20"])
        self.assertEqual(summary["loadCount"], 1)
        self.assertEqual(summary["scanStartCount"], 1)
        self.assertEqual(summary["scanFinishCount"], 1)
        self.assertEqual(summary["ueAnchorCount"], 1)
        self.assertEqual(summary["mappedUeAnchorCount"], 1)
        self.assertTrue(summary["ueRuntimeDiscovery"]["coverage"]["objectArrayProbes"] > 0)

    def test_summarize_windows_log(self):
        records = [scan_summary.parse_line(line) for line in SAMPLE_LOG.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])

        self.assertEqual(summary["hitCount"], 3)
        self.assertEqual(summary["moduleCount"], 1)
        self.assertEqual(summary["ueAnchorCount"], 2)
        self.assertEqual(summary["mappedUeAnchorCount"], 1)
        self.assertEqual(summary["ueAnchorGroupCounts"], {"objects": 1, "world": 1})
        self.assertEqual(summary["mappedUeAnchorGroupCounts"], {"objects": 1})
        self.assertEqual(summary["ueAnchorSignatureCount"], 2)
        self.assertEqual(summary["resolvedUeAnchorSignatureCount"], 1)
        self.assertEqual(summary["ueAnchorSignatureStatusCounts"], {"missing": 1, "resolved": 1})
        self.assertEqual(summary["ueAnchorSignatureGroupCounts"], {"dispatch": 1, "world": 1})
        self.assertEqual(summary["resolvedUeAnchorSignatureGroupCounts"], {"world": 1})
        self.assertEqual(summary["ueCandidateGlobalCount"], 1)
        self.assertEqual(summary["addedUeCandidateGlobalCount"], 1)
        self.assertEqual(summary["ueCandidateGlobalStatusCounts"], {"added": 1})
        self.assertEqual(summary["uePointerCount"], 2)
        self.assertEqual(summary["mappedUePointerCount"], 1)
        self.assertEqual(summary["ueLayoutCount"], 1)
        self.assertEqual(summary["readableUeLayoutCount"], 1)
        self.assertEqual(summary["ueLayoutSlotCount"], 2)
        self.assertEqual(summary["mappedUeLayoutSlotCount"], 1)
        self.assertEqual(summary["ueUObjectCount"], 1)
        self.assertEqual(summary["candidateUeUObjectCount"], 1)
        self.assertEqual(summary["classMappedUeUObjectCount"], 1)
        self.assertEqual(summary["ueReflectionCount"], 1)
        self.assertEqual(summary["classMappedUeReflectionCount"], 1)
        self.assertEqual(summary["ueReflectionSlotCount"], 3)
        self.assertEqual(summary["mappedUeReflectionSlotCount"], 3)
        self.assertEqual(summary["ueReflectionFieldCount"], 3)
        self.assertEqual(summary["candidateUeReflectionFieldCount"], 3)
        self.assertEqual(summary["classMappedUeReflectionFieldCount"], 3)
        self.assertEqual(summary["ueFFieldLayoutCandidateCount"], 1)
        self.assertEqual(summary["mappedUeFFieldLayoutCandidateCount"], 1)
        self.assertEqual(summary["namedUeFFieldLayoutCandidateCount"], 1)
        self.assertEqual(summary["propertyLikeUeFFieldLayoutCandidateCount"], 1)
        self.assertEqual(summary["saneUeFFieldLayoutCandidateCount"], 1)
        self.assertEqual(summary["propertyLikeSaneUeFFieldLayoutCandidateCount"], 1)
        self.assertEqual(summary["ueReflectionPropertyRootScanCount"], 2)
        self.assertEqual(summary["candidateUeReflectionPropertyRootScanCount"], 1)
        self.assertEqual(summary["saneUeReflectionPropertyRootScanCount"], 1)
        self.assertEqual(summary["ueReflectionPropertyCount"], 2)
        self.assertEqual(summary["candidateUeReflectionPropertyCount"], 2)
        self.assertEqual(summary["readableUeReflectionPropertyCount"], 2)
        self.assertEqual(summary["runtimeUeReflectionPropertyCount"], 2)
        self.assertEqual(summary["runtimeReadableUeReflectionPropertyCount"], 2)
        self.assertEqual(summary["ueReflectionValueCount"], 2)
        self.assertEqual(summary["readUeReflectionValueCount"], 2)
        self.assertEqual(summary["runtimeReadUeReflectionValueCount"], 2)
        self.assertEqual(summary["runtimeDescriptorMatchedReadUeReflectionValueCount"], 2)
        self.assertEqual(summary["ueFunctionParamRootCount"], 2)
        self.assertEqual(summary["rootedUeFunctionParamRootCount"], 1)
        self.assertEqual(summary["ueFunctionParamCount"], 1)
        self.assertEqual(summary["candidateUeFunctionParamCount"], 1)
        self.assertEqual(summary["ueFunctionParamContainerChildCount"], 1)
        self.assertEqual(summary["candidateUeFunctionParamContainerChildCount"], 1)
        self.assertEqual(summary["decodedUeFunctionParamContainerChildCount"], 1)
        self.assertEqual(summary["readableUeFunctionParamCount"], 1)
        self.assertEqual(summary["namedUeFunctionParamCount"], 1)
        self.assertEqual(summary["uniqueUeFunctionPathCount"], 1)
        self.assertEqual(summary["ueFunctionPaths"], ["/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function"])
        self.assertEqual(summary["uniqueUe4ssFunctionPathCount"], 1)
        self.assertEqual(summary["ue4ssFunctionPaths"], ["/Script/GUObjectArray.DecodedFunction_0:Function"])
        self.assertEqual(summary["ueFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["promotedUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["readableFlagUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["runtimePathUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["ue4ssPathUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["readableUeFunctionFlagRootCount"], 1)
        self.assertEqual(summary["readableUeFunctionFlagParamCount"], 1)
        self.assertEqual(summary["ueFunctionFlagPathCount"], 1)
        self.assertEqual(summary["ueFunctionFlagPaths"], ["/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function"])
        self.assertEqual(summary["ueFunctionFlagValues"], ["0x400"])
        self.assertEqual(summary["hookDispatchCount"], 2)
        self.assertEqual(summary["hookSelfTestCount"], 1)
        self.assertEqual(summary["passedHookSelfTestCount"], 1)
        self.assertEqual(summary["modSelfTestCount"], 1)
        self.assertEqual(summary["passedModSelfTestCount"], 1)
        self.assertEqual(summary["luaSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaCallbackSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaApiSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaSchedulerApiSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaInputCommandApiSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaObjectApiSelfTestCount"], 1)
        self.assertEqual(summary["luaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["namedLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["rawSetLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["numericLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["nameTextLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["arrayInnerLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["enumLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["containerLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["importTextLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["exportTextLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["propertyMetadataLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["descriptorValueLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["reflectionForEachPropertyLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["runtimeReflectionForEachPropertyLuaReflectionSelfTestCount"], 0)
        self.assertEqual(summary["selfTestReflectionForEachPropertyLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["typedLiveDescriptorLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["runtimeTypedLiveDescriptorLuaReflectionSelfTestCount"], 0)
        self.assertEqual(summary["selfTestTypedLiveDescriptorLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["typedLiveDescriptorValueLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["runtimeTypedLiveDescriptorValueLuaReflectionSelfTestCount"], 0)
        self.assertEqual(summary["selfTestTypedLiveDescriptorValueLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["typedLiveDescriptorValueSetLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["runtimeTypedLiveDescriptorValueSetLuaReflectionSelfTestCount"], 0)
        self.assertEqual(summary["selfTestTypedLiveDescriptorValueSetLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["liveDescriptorValueLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["runtimeLiveDescriptorValueLuaReflectionSelfTestCount"], 0)
        self.assertEqual(summary["selfTestLiveDescriptorValueLuaReflectionSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaProcessEventSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventFunctionParamMethodSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventFunctionParamLookupMethodSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventFunctionParamIterationMethodSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventContainerAliasMethodSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventContainerStorageLayoutMethodSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventScalarParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventNameStringParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventStructParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventEnumParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventObjectParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventBoolParamAccessorSelfTestCount"], 1)
        self.assertEqual(summary["routedLuaProcessEventSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventPathExactMatchCount"], 2)
        self.assertEqual(summary["luaProcessEventPathAliasMatchCount"], 0)
        self.assertEqual(summary["ueCallFunctionHookCount"], 1)
        self.assertEqual(summary["passedUeCallFunctionHookCount"], 1)
        self.assertEqual(summary["nonSelfTestPassedUeCallFunctionHookCount"], 1)
        self.assertEqual(summary["ueCallFunctionLiveHookCount"], 1)
        self.assertEqual(summary["installedUeCallFunctionLiveHookCount"], 1)
        self.assertEqual(summary["nonSelfTestInstalledUeCallFunctionLiveHookCount"], 1)
        self.assertEqual(summary["provenTargetRoutedUeCallFunctionLiveLuaHookCount"], 0)
        self.assertEqual(summary["provenTargetHandledUeCallFunctionLiveLuaHookCount"], 0)
        self.assertEqual(summary["installedUeProcessEventLiveHookCount"], 1)
        self.assertEqual(summary["nonSelfTestInstalledUeProcessEventLiveHookCount"], 0)
        self.assertEqual(summary["ueProcessEventLiveContextCount"], 1)
        self.assertEqual(summary["resolvedUeProcessEventLiveContextCount"], 1)
        self.assertEqual(summary["matchedUeProcessEventLiveContextCount"], 1)
        self.assertEqual(summary["runtimeMatchedUeProcessEventLiveContextCount"], 1)
        self.assertIn(
            {
                "objectAddress": "0x140050000",
                "functionAddress": "0x140062000",
                "functionPath": "/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function",
                "objectPath": "/RuntimeProbe/GUObjectArray",
                "functionProvenance": "runtime",
                "callFunctionCommand": "DecodedFunction_0",
                "paramsAddress": "0x20",
            },
            summary["activeValidationCandidates"],
        )
        self.assertEqual(summary["runtimeProvenanceUeProcessEventLiveContextCount"], 1)
        self.assertEqual(summary["selfTestProvenanceUeProcessEventLiveContextCount"], 0)
        self.assertEqual(summary["ueProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["resolvedUeProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["nativeIdentityUeProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["matchedUeProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["runtimeMatchedUeProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["runtimeProvenanceUeProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["selfTestProvenanceUeProcessEventLiveRegistryContextCount"], 0)
        self.assertEqual(summary["ueProcessEventLiveParamCount"], 3)
        self.assertEqual(summary["readUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["rawUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["containerUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["sampledContainerUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["runtimeReadUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["runtimeRawUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["runtimeContainerUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["runtimeSampledContainerUeProcessEventLiveParamCount"], 1)
        self.assertEqual(summary["ueProcessEventLuaContextHandleCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaParamAccessorCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaFunctionParamMethodCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaFunctionParamLookupMethodCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaFunctionParamIterationMethodCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaContainerAliasMethodCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaContainerStorageLayoutMethodCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaScalarParamAccessorCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaNameStringParamAccessorCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaStructParamAccessorCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaEnumParamAccessorCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaObjectParamAccessorCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaBoolParamAccessorCount"], 1)
        self.assertEqual(summary["routedUeProcessEventLiveLuaHookCount"], 1)
        self.assertEqual(summary["armedUeProcessEventDispatchSelfTestCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaDispatchCount"], 2)
        self.assertEqual(summary["armedUeProcessEventLiveLuaDispatchCount"], 1)
        self.assertEqual(summary["multiHookUeProcessEventLiveLuaDispatchCount"], 1)
        self.assertEqual(summary["matchedUeProcessEventLiveLuaDispatchCount"], 1)
        self.assertEqual(summary["closedUeProcessEventLiveLuaDispatchCount"], 1)
        self.assertEqual(summary["closedMatchedUeProcessEventLiveLuaDispatchCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaPathExactMatchCount"], 0)
        self.assertEqual(summary["ueProcessEventLiveLuaPathAliasMatchCount"], 2)
        self.assertEqual(summary["ueProcessEventLiveLuaDispatchStatusCounts"], {"armed": 1, "closed": 1})
        self.assertEqual(summary["luaModScriptCount"], 2)
        self.assertEqual(summary["passedLuaModScriptCount"], 2)
        self.assertEqual(summary["luaModDispatchSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaModDispatchSelfTestCount"], 1)
        self.assertEqual(summary["luaModFinishCount"], 1)
        self.assertEqual(summary["passedLuaModFinishCount"], 1)
        self.assertEqual(summary["luaObjectApiModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetBackendStateModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetBackendAnchorModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)
        self.assertEqual(summary["luaFunctionIterationModFinishCount"], 1)
        self.assertEqual(summary["luaFunctionIterationCheckCount"], 1)
        self.assertEqual(summary["passedLuaFunctionIterationCheckCount"], 1)
        self.assertEqual(summary["runtimeLuaFunctionIterationCheckCount"], 0)
        self.assertEqual(summary["selfTestLuaFunctionIterationCheckCount"], 1)
        self.assertEqual(summary["luaSchedulerApiModFinishCount"], 1)
        self.assertEqual(summary["luaInputCommandApiModFinishCount"], 1)
        self.assertEqual(summary["luaProcessConsoleExecHookModFinishCount"], 1)
        self.assertEqual(summary["luaLocalPlayerExecHookModFinishCount"], 1)
        self.assertEqual(summary["luaCallFunctionHookModFinishCount"], 1)
        self.assertEqual(summary["luaCallFunctionStructuredArgsModFinishCount"], 1)
        self.assertEqual(summary["luaProcessEventCompatModFinishCount"], 1)
        self.assertEqual(summary["luaProcessEventBridgeStateModFinishCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeInvokeModFinishCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeInvokeSelfTestCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeInvokeDescriptorPreflightCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeExecutorStateCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeExecutorReadyStateCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeInvokeNonSelfTestGateCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeInvokeNonSelfTestInvokedCount"], 0)
        self.assertEqual(summary["luaCallFunctionNativeInvokeModFinishCount"], 1)
        self.assertEqual(summary["luaCallFunctionNativeInvokeSelfTestCount"], 1)
        self.assertEqual(summary["luaCallFunctionNativeInvokePreflightCount"], 1)
        self.assertEqual(summary["luaCallFunctionNativeExecutorStateCount"], 1)
        self.assertEqual(summary["luaCallFunctionNativeExecutorReadyStateCount"], 1)
        self.assertEqual(summary["luaCallFunctionNativeInvokeNonSelfTestGateCount"], 1)
        self.assertEqual(summary["luaCallFunctionNativeInvokeNonSelfTestInvokedCount"], 0)
        self.assertEqual(summary["luaProcessEventParamsBufferCount"], 1)
        self.assertEqual(summary["luaLifecycleHookModFinishCount"], 1)
        self.assertEqual(summary["luaCustomEventModFinishCount"], 1)
        self.assertEqual(summary["luaLoadMapHookModFinishCount"], 1)
        self.assertEqual(summary["luaBeginPlayHookModFinishCount"], 1)
        self.assertEqual(summary["luaInitGameStateHookModFinishCount"], 1)
        self.assertEqual(summary["luaNotifyOnNewObjectModFinishCount"], 1)
        self.assertEqual(summary["luaSyntheticOuterModFinishCount"], 1)
        self.assertEqual(summary["luaWorldContextModFinishCount"], 1)
        self.assertEqual(summary["luaClassDefaultObjectModFinishCount"], 1)
        self.assertEqual(summary["luaLevelModFinishCount"], 1)
        self.assertEqual(summary["luaObjectRegistryCount"], 4)
        self.assertEqual(summary["addedLuaObjectRegistryCount"], 3)
        self.assertEqual(summary["luaObjectRegistryCheckCount"], 4)
        self.assertEqual(summary["passedLuaObjectRegistryCheckCount"], 4)
        self.assertEqual(summary["luaFunctionRegistryCheckCount"], 1)
        self.assertEqual(summary["passedLuaFunctionRegistryCheckCount"], 1)
        self.assertEqual(summary["runtimeLuaFunctionRegistryCheckCount"], 1)
        self.assertEqual(summary["selfTestLuaFunctionRegistryCheckCount"], 0)
        self.assertEqual(summary["ueLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["runtimeUeLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["selfTestUeLuaObjectRegistryCount"], 0)
        self.assertEqual(summary["objectArrayLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["runtimeObjectArrayLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["selfTestObjectArrayLuaObjectRegistryCount"], 0)
        self.assertEqual(summary["decodedLuaObjectAliasRegistryCount"], 1)
        self.assertEqual(summary["runtimeDecodedLuaObjectAliasRegistryCount"], 1)
        self.assertEqual(summary["selfTestDecodedLuaObjectAliasRegistryCount"], 0)
        self.assertEqual(summary["skippedDecodedLuaObjectAliasRegistryCount"], 1)
        self.assertEqual(summary["luaObjectOuterChainCount"], 1)
        self.assertEqual(summary["resolvedLuaObjectOuterChainCount"], 1)
        self.assertEqual(summary["luaObjectOuterChainIdentityCount"], 1)
        self.assertEqual(summary["luaGlobalRuntimeHelperCheckCount"], 1)
        self.assertEqual(summary["passedLuaGlobalRuntimeHelperCheckCount"], 1)
        self.assertEqual(summary["promotedWorldLuaGlobalRuntimeHelperCheckCount"], 1)
        self.assertEqual(summary["promotedEngineLuaGlobalRuntimeHelperCheckCount"], 0)
        self.assertEqual(summary["ueObjectArrayCount"], 2)
        self.assertEqual(summary["ueObjectArrayShapeCount"], 2)
        self.assertEqual(summary["plausibleUeObjectArrayShapeCount"], 1)
        self.assertEqual(summary["implausibleUeObjectArrayShapeCount"], 1)
        self.assertEqual(summary["finishedUeObjectArrayCount"], 1)
        self.assertEqual(summary["ueObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["promotedUeObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["decodedNameUeObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["decodedClassNameUeObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["ueFNameCount"], 3)
        self.assertEqual(summary["decodedUeFNameCount"], 3)
        self.assertEqual(summary["forwardSmokeCount"], 1)
        self.assertEqual(summary["hitsByName"]["FNamePool"]["category"], "ue")
        self.assertEqual(summary["hitsByName"]["GName"]["category"], "ue")
        self.assertIn("GUObjectArray", summary["hitsByName"])
        self.assertEqual(summary["hitsByName"]["GWorld"]["kinds"], {"ue-anchor-signature": 1})
        self.assertEqual(summary["uePointersByName"]["GUObjectArray"][0]["status"], "target-mapped")
        self.assertEqual(summary["ueLayoutSlotsByName"]["GUObjectArray"][0]["status"], "target-mapped")
        self.assertEqual(summary["ueUObjectsByName"]["GUObjectArray"][0]["classMapped"], "true")
        self.assertEqual(summary["ueFNamesByObjectName"]["GUObjectArray"][0]["decoded"], "DecodedObject_0")
        self.assertNotIn("GWorld", summary["missingExpected"])
        self.assertIn("GObjectArray", summary["missingExpected"])

    def test_summarize_new_loader_script_and_runtime_function_paths(self):
        records = [scan_summary.parse_line(line) for line in new_loader_identity_sample(SAMPLE_LOG).splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])

        self.assertEqual(summary["ueFunctionPaths"], ["/RuntimeProbe/GUObjectArray.DecodedFunction_0:Function"])
        self.assertEqual(summary["ue4ssFunctionPaths"], ["/Script/GUObjectArray.DecodedFunction_0:Function"])
        self.assertEqual(summary["matchedUeProcessEventLiveContextCount"], 1)

    def test_load_asset_package_mod_finish_requires_package_backend_evidence(self):
        backend_state_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 loadAssetPackageArmed=false",
        )
        records = [scan_summary.parse_line(line) for line in backend_state_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetBackendStateModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetBackendAnchorModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageBridgeStateModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        backend_anchor_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 loadAssetPackageArmed=false "
            "loadAssetPackageAvailable=true loadAssetStaticLoadObjectResolved=true",
        )
        records = [scan_summary.parse_line(line) for line in backend_anchor_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetBackendStateModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetBackendAnchorModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageBridgeStateModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_bridge_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
            "loadAssetPackageBridgeStateCalls=1 loadAssetPackageArmed=false",
        )
        records = [scan_summary.parse_line(line) for line in package_bridge_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageBridgeStateModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_invoke_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
            "loadAssetPackageBridgeStateCalls=1 loadAssetPackageNativeCalls=1 "
            "loadAssetPackageNativeGateHits=1 loadAssetPackageArmed=false",
        )
        records = [scan_summary.parse_line(line) for line in package_native_invoke_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageBridgeStateModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageAbiStateEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_abi_state_log = (
            package_native_invoke_log
            + "\n2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-abi-state "
            "status=anchor-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=win64-ms-abi "
            "signatureFamily=StaticLoadObject abiVerified=false callFrameReady=false "
            "stringBridgeReady=false classRootReady=false outerReady=false packageAvailable=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_abi_state_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageAbiStateEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageStringBridgeEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_string_bridge_log = (
            package_abi_state_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-string-bridge-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi stringInputStaged=true boundedInput=true utf8ByteCount=37 "
            "inputEncoding=utf-8 tcharEncoding=unverified-live-build tcharBridgeReady=false "
            "nativeBufferReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_string_bridge_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageStringBridgeEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeBufferEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_buffer_log = (
            package_string_bridge_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-native-buffer-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi stringInputStaged=true boundedInput=true "
            "utf8BufferReady=true nativeInputBufferReady=true bufferBytes=38 nullTerminated=true "
            "tcharEncoding=unverified-live-build tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_buffer_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageNativeBufferEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageTCharBufferEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_tchar_buffer_log = (
            package_native_buffer_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-tchar-buffer-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi stringInputStaged=true boundedInput=true "
            "candidateEncoding=windows-wchar-unverified candidateUnitBytes=2 candidateBufferBytes=76 "
            "tcharLayoutVerified=false tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_tchar_buffer_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageTCharBufferEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageTCharVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_tchar_verification_log = (
            package_tchar_buffer_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-tchar-verification-state "
            "status=evidence-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=win64-ms-abi "
            "candidateEncoding=windows-wchar-unverified candidateUnitBytes=2 observedUnitBytes=0 "
            "evidenceProvided=false verificationEnabled=false unitMatch=false "
            "tcharLayoutVerified=false tcharBufferReady=false evidence=none\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_tchar_verification_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageTCharVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_call_frame_verification_log = (
            package_tchar_verification_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-call-frame-verification-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 targetImage=false platformAbi=win64-ms-abi signatureFamily=StaticLoadObject argumentCount=7 "
            "pathStaged=true boundedInput=true abiEvidenceProvided=false abiVerificationEnabled=false "
            "abiVerified=false tcharEvidenceProvided=false tcharVerificationEnabled=false "
            "tcharLayoutVerified=false tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_call_frame_verification_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_call_adapter_log = (
            package_call_frame_verification_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-native-call-adapter-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi adapterKind=win64-ms-abi-package-load "
            "signatureFamily=StaticLoadObject argumentCount=7 pathStaged=true boundedInput=true "
            "functionPointerReady=false abiVerified=false tcharLayoutVerified=false callFrameReady=false "
            "invokeEnabled=false nativeBridgeArmed=false adapterReady=false finalInvokeConfirmed=false crashGuardRequired=true crashGuardArmed=false guardedCallRequired=true guardedCallReady=true guardedCallResult=17 returnValidationReady=true invocationDescriptorRequired=true invocationDescriptorConsumed=true nativeCallPlanAccepted=true nativeCallExecutionMode=guarded-native-package-load nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallable=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_call_adapter_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_invocation_descriptor_log = (
            package_native_call_adapter_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-invocation-descriptor-state "
            "status=derived descriptorKind=guarded-package-native-call "
            "descriptorProvenance=adapter-state-derived nativeCallPlanConstructed=true nativeCallExecutionMode=guarded-native-package-load nativeCallTargetField=TargetAddress nativeCallPathField=Path nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallReturnValidator=uobject-registry-memory-class nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_invocation_descriptor_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_executor_log = (
            package_invocation_descriptor_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-native-executor-state "
            "status=prepared executorKind=guarded-package-native-executor nativeExecutorConstructed=true "
            "nativeExecutorDryRun=true nativeExecutorReady=false executorPreflightPassed=false "
            "finalNativeCallEligible=false nativeExecutorBlockReason=anchor-missing "
            "finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only "
            "nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_executor_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorReadyEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorTargetReadyEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_executor_ready_log = package_invocation_descriptor_log + (
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-native-executor-state "
            "status=prepared executorKind=guarded-package-native-executor nativeExecutorConstructed=true "
            "nativeExecutorDryRun=true nativeExecutorReady=true executorPreflightPassed=true "
            "finalNativeCallEligible=true nativeExecutorBlockReason=none "
            "finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only "
            "nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_executor_ready_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorReadyEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorTargetReadyEventCount"], 0)

        package_native_executor_target_ready_log = package_invocation_descriptor_log + (
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-native-executor-state "
            "status=prepared executorKind=guarded-package-native-executor nativeExecutorConstructed=true "
            "targetName=StaticLoadObject target=0x140048000 targetImage=true signatureFamily=StaticLoadObject "
            "nativeExecutorDryRun=true nativeExecutorReady=true executorPreflightPassed=true "
            "finalNativeCallEligible=true nativeExecutorBlockReason=none "
            "finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only "
            "nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_executor_target_ready_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorReadyEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorTargetReadyEventCount"], 1)

        package_call_frame_log = (
            package_native_executor_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-call-frame-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi signatureFamily=StaticLoadObject pathStaged=true "
            "argumentDescriptorReady=true tcharBridgeReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_call_frame_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_preflight_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=2 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 loadAssetPackageArmed=false "
            "loadAssetPackagePreflightCalls=1 loadAssetPackageGateHits=1",
        )
        records = [scan_summary.parse_line(line) for line in package_preflight_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        explicit_package_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetPackageCalls=1 loadAssetPackageHits=1",
        )
        records = [scan_summary.parse_line(line) for line in explicit_package_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 1)

        backend_package_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 loadAssetBackend=package",
        )
        records = [scan_summary.parse_line(line) for line in backend_package_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 1)

    def test_static_construct_object_native_summary_requires_target_image_and_invocation(self):
        dry_run_log = (
            "2026-01-01T00:00:00Z pid=1 loader=win-client "
            "event=lua-static-construct-object-native-executor-state status=anchor-missing "
            "executorKind=guarded-static-construct-object-native-executor targetName=StaticConstructObject "
            "target=0x0 targetImage=false platformAbi=win64-ms-abi class=0x1000 outer=0x2000 "
            "name=NativeConstructPreflightProbe invokeRequested=false invokeEnabled=false "
            "abiEvidenceProvided=false abiVerified=false callFrameReady=false "
            "finalInvokeConfirmed=false nativeCallable=false nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=1 loader=win-client "
            "event=lua-static-construct-object-native-invoke status=anchor-missing "
            "executorKind=guarded-static-construct-object-native-executor targetName=StaticConstructObject "
            "target=0x0 targetImage=false platformAbi=win64-ms-abi class=0x1000 outer=0x2000 "
            "name=NativeConstructPreflightProbe invokeRequested=true invokeEnabled=false "
            "abiEvidenceProvided=false abiVerified=false callFrameReady=false "
            "finalInvokeConfirmed=false nativeCallable=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in dry_run_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaStaticConstructObjectNativeExecutorStateCount"], 1)
        self.assertEqual(summary["luaStaticConstructObjectNativeExecutorReadyStateCount"], 0)
        self.assertEqual(summary["luaStaticConstructObjectNativeInvokeCount"], 1)
        self.assertEqual(summary["luaStaticConstructObjectNativeInvokedCount"], 0)

        target_ready_log = (
            dry_run_log
            + "2026-01-01T00:00:00Z pid=1 loader=win-client "
            "event=lua-static-construct-object-native-executor-state status=prepared "
            "executorKind=guarded-static-construct-object-native-executor targetName=StaticConstructObject "
            "target=0x140040000 targetImage=true platformAbi=win64-ms-abi class=0x1000 outer=0x2000 "
            "name=NativeConstructPreflightProbe invokeRequested=false invokeEnabled=true "
            "abiEvidenceProvided=true abiVerified=true callFrameReady=true "
            "finalInvokeConfirmed=true nativeCallable=true nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=1 loader=win-client "
            "event=lua-static-construct-object-native-invoke status=native-invoked "
            "executorKind=guarded-static-construct-object-native-executor targetName=StaticConstructObject "
            "target=0x140040000 targetImage=true platformAbi=win64-ms-abi class=0x1000 outer=0x2000 "
            "name=NativeConstructPreflightProbe invokeRequested=true invokeEnabled=true "
            "abiEvidenceProvided=true abiVerified=true callFrameReady=true "
            "finalInvokeConfirmed=true nativeCallable=true nativeInvoked=true\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in target_ready_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaStaticConstructObjectNativeExecutorStateCount"], 2)
        self.assertEqual(summary["luaStaticConstructObjectNativeExecutorReadyStateCount"], 1)
        self.assertEqual(summary["luaStaticConstructObjectNativeInvokeCount"], 2)
        self.assertEqual(summary["luaStaticConstructObjectNativeInvokedCount"], 1)

    def test_package_state_events_require_target_image_provenance(self):
        log = (
            SAMPLE_LOG
            + "\n2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-abi-state "
            "status=anchor-missing targetName=StaticLoadObject target=0x0 platformAbi=win64-ms-abi "
            "signatureFamily=StaticLoadObject abiVerified=false callFrameReady=false "
            "stringBridgeReady=false classRootReady=false outerReady=false packageAvailable=false\n"
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-tchar-verification-state "
            "status=target-not-target-image targetName=StaticLoadObject target=0x1234 targetImage=true "
            "platformAbi=win64-ms-abi candidateEncoding=windows-wchar-unverified candidateUnitBytes=2 "
            "observedUnitBytes=2 evidenceProvided=true verificationEnabled=true unitMatch=true "
            "tcharLayoutVerified=false tcharBufferReady=false evidence=self-test\n"
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=lua-load-asset-package-call-frame-verification-state "
            "status=call-frame-ready path=/Script/DuneProbe.Asset targetName=StaticLoadObject "
            "target=0x1234 targetImage=false platformAbi=win64-ms-abi signatureFamily=StaticLoadObject "
            "argumentCount=7 pathStaged=true boundedInput=true abiEvidenceProvided=true "
            "abiVerificationEnabled=true abiVerified=true tcharEvidenceProvided=true "
            "tcharVerificationEnabled=true tcharLayoutVerified=true tcharBufferReady=true "
            "callFrameReady=true nativeInvoked=false\n"
        )
        records = [record for record in (scan_summary.parse_line(line) for line in log.splitlines()) if record]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])
        self.assertEqual(summary["luaLoadAssetPackageAbiStateEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageTCharVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)

    def test_explicit_reflection_descriptor_provenance_overrides_name_heuristic(self):
        self_test_log = (
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=ue-reflection-property "
            "name=GWorld chain=propertyLink index=0 descriptorProvenance=self-test status=candidate "
            "field=0x1000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 "
            "arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true\n"
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=ue-reflection-value "
            "name=GWorld chain=propertyLink index=0 fieldName=DecodedWorld descriptorProvenance=self-test "
            "status=read object=0x2000 address=0x200c offsetInternal=12 elementSize=4 arrayDim=1 "
            "requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false\n"
        )
        runtime_log = self_test_log.replace("descriptorProvenance=self-test", "descriptorProvenance=runtime").replace(
            "name=GWorld",
            "name=SelfTestGWorld",
        )

        self_test_records = [scan_summary.parse_line(line) for line in self_test_log.splitlines()]
        runtime_records = [scan_summary.parse_line(line) for line in runtime_log.splitlines()]

        self_test_summary = scan_summary.summarize(self_test_records, loader_filter=["win-client"])
        runtime_summary = scan_summary.summarize(runtime_records, loader_filter=["win-client"])

        self.assertEqual(self_test_summary["runtimeReadableUeReflectionPropertyCount"], 0)
        self.assertEqual(self_test_summary["runtimeReadUeReflectionValueCount"], 0)
        self.assertEqual(runtime_summary["runtimeReadableUeReflectionPropertyCount"], 1)
        self.assertEqual(runtime_summary["runtimeReadUeReflectionValueCount"], 1)

    def test_reflection_runtime_counts_require_explicit_runtime_provenance(self):
        ambiguous_log = (
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=ue-reflection-property "
            "name=GWorld chain=propertyLink index=0 status=candidate "
            "field=0x1000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 "
            "arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true\n"
            "2026-01-01T00:00:00Z pid=1 loader=win-client event=ue-reflection-value "
            "name=GWorld chain=propertyLink index=0 fieldName=DecodedWorld "
            "status=read object=0x2000 address=0x200c offsetInternal=12 elementSize=4 arrayDim=1 "
            "requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false\n"
        )

        records = [scan_summary.parse_line(line) for line in ambiguous_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["win-client"])

        self.assertEqual(summary["readableUeReflectionPropertyCount"], 1)
        self.assertEqual(summary["readUeReflectionValueCount"], 1)
        self.assertEqual(summary["runtimeReadableUeReflectionPropertyCount"], 0)
        self.assertEqual(summary["runtimeReadUeReflectionValueCount"], 0)
        self.assertEqual(summary["runtimeDescriptorMatchedReadUeReflectionValueCount"], 0)

    def test_function_param_summary_rejects_non_property_field_class(self):
        bad_param_log = (
            "2026-01-01T00:00:00Z pid=1 loader=server event=ue-function-param "
            "name=Actor functionIndex=0 chain=childProperties index=0 status=candidate "
            "function=0x1000 functionName=WasRecentlyRendered "
            "functionPath=/RuntimeProbe/Actor.WasRecentlyRendered:Function "
            "field=0x2000 class=0x3000 classMapped=true fieldName=Actor "
            "fieldClassName=WasRecentlyRendered arrayDim=69 elementSize=1 "
            "propertyFlags=0x180 offsetInternal=1572880 "
            "arrayDimReadable=true elementSizeReadable=true "
            "propertyFlagsReadable=true offsetInternalReadable=true "
            "functionFlags=0x400 functionFlagsReadable=true next=0x0\n"
        )

        records = [scan_summary.parse_line(line) for line in bad_param_log.splitlines()]
        summary = scan_summary.summarize(records, loader_filter=["server"])

        self.assertEqual(summary["ueFunctionParamCount"], 1)
        self.assertEqual(summary["candidateUeFunctionParamCount"], 1)
        self.assertEqual(summary["readableUeFunctionParamCount"], 0)
        self.assertEqual(summary["namedUeFunctionParamCount"], 0)

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "client.log"
            log.write_text(SAMPLE_LOG, encoding="utf-8")
            result = subprocess.run(
                [str(SCRIPT), str(log), "--loader", "win-client", "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        summary = json.loads(result.stdout)
        self.assertEqual(summary["categories"], {"ue": 5})
        self.assertEqual(summary["scanFinishCount"], 1)


if __name__ == "__main__":
    unittest.main()
