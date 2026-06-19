#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-linux-loader-scan.py"


spec = importlib.util.spec_from_file_location("summarize_linux_loader_scan", SCRIPT)
scan_summary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(scan_summary)


SAMPLE_LOG = """\
2026-06-16T17:27:26+0000 pid=93 event=loaded exe=/usr/bin/dash
2026-06-16T17:27:26+0000 pid=93 event=scan-hit kind=string name=DeepDesert addr=0x1 imageOffset=0x1 fileOffset=0x1 perms=r-xp map=/usr/bin/dash
2026-06-16T17:27:26+0000 pid=100 event=loaded exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:27:26+0000 pid=100 event=scan-map phase=snapshot bytes=342523904 perms=r-xp offset=0x0 map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:27:26+0000 pid=100 event=scan-hit kind=string name=ServerRequestBaseBackup addr=0x5628a0c2e3f9 imageOffset=0x5a553f9 fileOffset=0x5a553f9 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:27:26+0000 pid=100 event=scan-hit kind=string name=GName addr=0x5628a0c2e410 imageOffset=0x5a55410 fileOffset=0x5a55410 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:27:26+0000 pid=100 event=scan-hit kind=signature name=brt-action-guard addr=0x5628a9227d15 imageOffset=0xe04ed15 fileOffset=0xe04ed15 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:27:28+0000 pid=100 event=scan-finish phase=snapshot mappings=54 scanned=3 filtered=50 unreadable=1 sizeSkipped=0 hits=3
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-anchor name=SelfTestUObject group=self-test status=mapped addr=0x1000 imageOffset=0x100 fileOffset=0x100 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-candidate-global name=GUObjectArray status=added address=0x5628aa000000 imageOffset=0x165ff4a8 absolute=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-pointer name=SelfTestUObject status=target-mapped anchor=0x1000 value=0x2000
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-layout name=SelfTestUObject status=target-readable anchor=0x1000 target=0x2000 slots=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-layout-slot name=SelfTestUObject status=target-mapped target=0x2000 offset=0x0 value=0x3000
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-uobject name=SelfTestUObject status=candidate anchor=0x1000 target=0x2000 classMapped=true nameComparisonIndex=1234 nameNumber=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection name=SelfTestUObject status=class-mapped object=0x2000 class=0x3000 classVtable=0x4000 classVtableMapped=true classNameComparisonIndex=1234 classNameNumber=1 slots=6
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-slot name=SelfTestUObject slot=children status=target-mapped class=0x3000 offset=0x38 value=0x2000
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-slot name=SelfTestUObject slot=propertyLink status=target-mapped class=0x3000 offset=0x48 value=0x2000
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-slot name=SelfTestUObject slot=functionLink status=target-mapped class=0x3000 offset=0x50 value=0x2000
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-fname source=ue-reflection-field objectName=SelfTestUObject.children_0 status=decoded object=0x2100 decoded=SelfTestUObjectName_0
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-field name=SelfTestUObject chain=children index=0 status=candidate field=0x2100 class=0x3000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-field name=SelfTestUObject chain=propertyLink index=0 status=candidate field=0x2200 class=0x3000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-field name=SelfTestUObject chain=functionLink index=0 status=candidate field=0x2300 class=0x3000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=childProperties status=root function=0x2300 offset=0x40 root=0x2400 functionFlags=0x400 functionFlagsReadable=true functionFlagsOffset=0x58
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-function-native-identity source=ue-function-param status=promoted name=SelfTestUObject functionIndex=0 chain=childProperties function=0x2300 functionName=SelfTestUObjectName_0 functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function root=0x2400 functionFlags=0x400 functionFlagsReadable=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-function-registry-check source=ue-function-param status=passed name=SelfTestUObjectName_0 path=/Script/SelfTestUObject.SelfTestUObjectName_0:Function runtimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function address=0x2300 pathHit=true runtimePathHit=true nameHit=true addressHit=true flagsHit=true registryCount=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate function=0x2300 functionName=SelfTestUObjectName_0 functionPath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function field=0x2400 class=0x3000 classMapped=true nameComparisonIndex=1234 nameNumber=1 fieldName=SelfTestParam_0 arrayDim=1 elementSize=4 propertyFlags=0x80 offsetInternal=16 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true functionFlags=0x400 functionFlagsReadable=true next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-function-param-container-child name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate field=0x2400 containerClassName=FArrayProperty role=inner child=0x2500 childOffset=0x70 childClass=0x3000 childClassMapped=true childClassName=FIntProperty childNameComparisonIndex=1235 childNameNumber=1 childName=SelfTestInner_0
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=propertyLink status=null-root function=0x2300 offset=0x48
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-property name=SelfTestUObject chain=childProperties index=0 status=candidate field=0x2200 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-property name=SelfTestUObject chain=propertyLink index=0 status=candidate field=0x2200 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-value name=SelfTestUObject chain=childProperties index=0 fieldName=SelfTestUObjectName_0 status=read object=0x2000 address=0x200c offsetInternal=12 elementSize=4 arrayDim=1 requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-reflection-value name=SelfTestUObject chain=propertyLink index=0 fieldName=SelfTestUObjectName_0 status=read object=0x2000 address=0x200c offsetInternal=12 elementSize=4 arrayDim=1 requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry source=ue-uobject status=added name=SelfTestUObject path=/RuntimeProbe/SelfTestUObject class=UObjectCandidate address=0x2000 registryCount=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry-check source=ue-uobject status=passed name=SelfTestUObject path=/RuntimeProbe/SelfTestUObject class=UObjectCandidate address=0x2000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-object-native-identity source=ue-uobject status=promoted object=0x2000 name=SelfTestUObjectName_0 class=0x3000 className=SelfTestClass_0 outer=0x0 nameDecoded=true classNameDecoded=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry source=ue-uobject-fname status=added name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 aliasOf=SelfTestUObject class=UObjectCandidate address=0x2000 registryCount=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry-check source=ue-uobject-fname status=passed name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 class=UObjectCandidate address=0x2000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-object-array-shape name=SelfTestObjectArray mode=direct status=header-implausible base=0x2ff0 chunks=0x3000 maxElements=1 numElements=2 maxChunks=1 numChunks=1 countsPlausible=false chunkSlotReadable=true firstChunk=0x3100 firstChunkMapped=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-object-array-shape name=SelfTestObjectArray mode=indirect status=header-plausible base=0x3000 chunks=0x3100 maxElements=2 numElements=1 maxChunks=1 numChunks=1 countsPlausible=true chunkSlotReadable=true firstChunk=0x3200 firstChunkMapped=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-object-array name=SelfTestObjectArray mode=indirect status=finished base=0x3000 scanned=1 registered=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry source=ue-object-array status=added name=SelfTestObjectArray_0 path=/RuntimeProbe/SelfTestObjectArray_0 class=UObjectArrayItem address=0x2000 registryCount=3
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry-check source=ue-object-array status=passed name=SelfTestObjectArray_0 path=/RuntimeProbe/SelfTestObjectArray_0 class=UObjectArrayItem address=0x2000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=3
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-outer-chain status=resolved object=0x2600 path=/RuntimeProbe/ChildObject class=UObjectCandidate outer=0x2000 depth=1 terminal=0x2000 terminalPath=/RuntimeProbe/SelfTestUObject terminalClass=UObjectCandidate chain=/RuntimeProbe/ChildObject<-/RuntimeProbe/SelfTestUObject reconstructedPath=/RuntimeProbe/SelfTestUObject.ChildObject reconstructedFullName=UObjectCandidate_/RuntimeProbe/SelfTestUObject.ChildObject fullNameResolved=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-global-runtime-helper-check status=passed globalWorld=true globalWorldPromoted=true globalWorldAddress=0x2000 globalWorldPath=/RuntimeProbe/SelfTestObjectArray_0 globalWorldClass=UObjectArrayItem globalEngine=true globalEnginePromoted=false globalEngineAddress=0x2600 globalEnginePath=/RuntimeProbe/Engine globalEngineClass=UEngine getWorldCalls=3 getWorldHits=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-fname source=ue-object-array objectName=SelfTestObjectArray_0 status=decoded object=0x2000 decoded=SelfTestUObjectName_0
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-object-native-identity source=ue-object-array status=promoted object=0x2000 name=SelfTestUObjectName_0 class=0x3000 className=SelfTestClass_0 outer=0x0 nameDecoded=true classNameDecoded=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry source=ue-object-array-fname status=skipped name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 aliasOf=SelfTestObjectArray_0 class=UObjectArrayItem address=0x2000 registryCount=3
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-object-registry-check source=ue-object-array-fname status=passed name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 class=UObjectArrayItem address=0x2000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=3
2026-06-16T17:27:28+0000 pid=100 loader=server event=hook-dispatch-self-test phase=snapshot status=passed before=42 after=1042 final=42 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 installed=true restored=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=mod-dispatch-self-test phase=snapshot status=passed mods=1 loaded=1 unloaded=1 result=1042 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 loadCallbacks=1 unloadCallbacks=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-dispatch-self-test phase=snapshot status=passed library=liblua5.4.so loadStatus=0 callStatus=0 callbackStatus=0 result=42 isNumber=true hooks=1 hook=/Script/DuneServerProbe.SelfTest:Function preCalls=1 postCalls=1 preResult=11 postResult=31 preIsNumber=true postIsNumber=true staticFindObjectCalls=1 staticFindObjectHits=1 findObjectCalls=1 findObjectHits=1 findFirstOfCalls=1 findFirstOfHits=1 getKnownObjectsCalls=1 getKnownObjectsHits=1 findObjectsCalls=1 findObjectsHits=1 findAllOfCalls=1 findAllOfHits=1 forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=6 isAHits=5 loadAssetCalls=1 loadAssetHits=1 staticConstructObjectCalls=1 staticConstructObjectHits=1 notifyOnNewObjectCalls=1 notifyOnNewObjectCallbacks=1 notifyOnNewObjectResult=17 notifyOnNewObjectIsNumber=true notifyOnNewObjectStatus=0 executeInGameThreadCalls=1 executeInGameThreadCallbacks=1 executeInGameThreadResult=9 executeInGameThreadIsNumber=true executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2 executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 keyBindRegistrations=1 keyBindLookupCalls=2 keyBindLookupHits=1 keyBindDispatchCalls=2 keyBindCallbackCalls=1 keyBindCallbackHandled=1 keyBindUnregisterCalls=1 keyBindUnregisterHits=1 consoleCommandHandlers=2 consoleCommandGlobalHandlers=1 consoleCommandHandlerCalls=1 consoleCommandHandlerHandled=0 consoleCommandGlobalHandlerCalls=1 consoleCommandGlobalHandlerHandled=1 consoleCommandUnregisterCalls=1 consoleCommandUnregisterHits=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-reflection-self-test phase=snapshot status=passed library=liblua5.4.so loadStatus=0 callStatus=0 result=42 isNumber=true staticFindObjectCalls=2 staticFindObjectHits=2 getPropertyCalls=20 getPropertyHits=20 rawPropertyHits=2 rawPropertyValue=17 namedPropertyHits=2 rawPropertySetHits=1 rawPropertySetValue=17 arrayInnerPropertyHits=1 enumPropertyHits=1 enumUnderlyingPropertyHits=1 setElementPropertyHits=1 mapKeyPropertyHits=1 mapValuePropertyHits=1 importTextHits=2 exportTextHits=2 propertyMetadataHits=7 descriptorValueGetHits=21 descriptorValueSetHits=9 descriptorValueAliasHits=3 reflectionForEachPropertyHits=2 runtimeReflectionForEachPropertyCallbacks=0 selfTestReflectionForEachPropertyCallbacks=14 liveDescriptorTypedClassHits=1 runtimeLiveDescriptorTypedClassHits=0 selfTestLiveDescriptorTypedClassHits=1 liveDescriptorTypedValueHits=1 runtimeLiveDescriptorTypedValueHits=0 selfTestLiveDescriptorTypedValueHits=1 liveDescriptorTypedValueSetHits=1 runtimeLiveDescriptorTypedValueSetHits=0 selfTestLiveDescriptorTypedValueSetHits=1 liveDescriptorValueGetHits=2 liveDescriptorValueSetHits=1 runtimeLiveDescriptorValueGetHits=0 selfTestLiveDescriptorValueGetHits=2 runtimeLiveDescriptorValueSetHits=0 selfTestLiveDescriptorValueSetHits=1 setPropertyCalls=10 setPropertyHits=10 callFunctionCalls=2 callFunctionHits=2 probeValue=21 probeBool=false probeFloat=13.750 probeDouble=-47.500 probeName=ArrakisName probeString=melange probeText=WaterDebt probeObject=0x1234
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-process-event-self-test phase=snapshot status=passed library=liblua5.4.so loadStatus=0 callStatus=0 result=4 isNumber=true hooks=2 hook=/Script/DuneServerProbe.SelfTest:Function installed=true restored=true hookCalls=1 originalCalls=2 originalAfterHook=1 preStatus=0 postStatus=0 preCalls=1 postCalls=1 preResult=11 postResult=31 preIsNumber=true postIsNumber=true pathExactMatches=2 pathAliasMatches=0 paramDescriptorHits=2 paramDescriptorLookupCalls=17 paramDescriptorLookupHits=17 functionParamDescriptorCalls=2 functionParamDescriptorHits=4 functionParamMethodHits=2 functionParamLookupMethodHits=2 functionParamIterationMethodHits=12 containerAliasHits=6 containerStorageLayoutHits=9 paramGetCalls=29 paramGetHits=29 paramSetCalls=11 paramSetHits=11 enumParamAccessors=true objectParamAccessors=true boolParamAccessors=true paramsResult=42 paramsTouched=1 finalResult=52 finalTouched=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-call-function-hook phase=snapshot status=passed target=0x4100 installed=true restored=true selfTestTarget=true callSelfTest=true before=42 after=1042 final=42 original=42 trampoline=0x5100
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-call-function-live-hook phase=snapshot status=installed target=0x4100 selfTestTarget=true callSelfTest=true liveCalls=1 originalCalls=1 result=42 trampoline=0x5200
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-process-event-dispatch-self-test phase=snapshot status=armed preRegistered=true postRegistered=true callbacks=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-process-event-live-lua-dispatch phase=snapshot status=armed library=liblua5.4.so loadStatus=0 callStatus=0 result=4 isNumber=true hooks=2 hook=/Script/DuneProbeAlias.SelfTestUObjectName_0:Function callbacks=4 scriptBytes=111
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-process-event-live-context status=partial call=1 object=0x2000 objectResolved=true objectPath=/RuntimeProbe/SelfTestUObject objectClass=UObjectCandidate function=0x2300 functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function functionProvenance=self-test functionParamDescriptors=1 params=0x20 paramsPresent=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-process-event-live-registry-context status=partial call=1 object=0x2000 objectResolved=true objectNativeIdentity=false objectPath=/RuntimeProbe/SelfTestUObject objectClass=UObjectCandidate function=0x2300 functionResolved=false functionNativeIdentity=false functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function functionProvenance=self-test functionParamDescriptors=1 params=0x20 paramsPresent=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=ue-process-event-live-hook phase=snapshot status=installed target=0x4000 selfTestTarget=true callSelfTest=true dispatchCallbacks=4 luaDispatch=true luaPreStatus=0 luaPostStatus=0 luaPreCalls=1 luaPostCalls=1 luaObjectHandleHits=2 luaFunctionHandleHits=2 luaParamsHandleHits=2 luaParamDescriptorHits=2 luaParamDescriptorLookupCalls=17 luaParamDescriptorLookupHits=17 luaFunctionParamDescriptorCalls=2 luaFunctionParamDescriptorHits=4 luaFunctionParamMethodHits=2 luaFunctionParamLookupMethodHits=2 luaFunctionParamIterationMethodHits=12 luaContainerAliasHits=6 luaContainerStorageLayoutHits=9 luaParamGetCalls=29 luaParamGetHits=29 luaParamSetCalls=11 luaParamSetHits=11 luaEnumParamAccessors=true luaObjectParamAccessors=true luaBoolParamAccessors=true preCallbacks=2 postCallbacks=2 liveCalls=1 originalCalls=1 paramsResult=62 paramsTouched=1 trampoline=0x5000
2026-06-16T17:27:29+0000 pid=100 loader=server event=ue-process-event-live-lua-dispatch phase=unload status=closed preCalls=1 postCalls=1 preResult=11 postResult=31 preStatus=0 postStatus=0 pathExactMatches=0 pathAliasMatches=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-mod-script phase=snapshot status=passed name=mod.lua loadStatus=0 callStatus=0 bytes=100 hooksBefore=0 hooksAfter=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-mod-script phase=snapshot status=passed name=mod-two.lua loadStatus=0 callStatus=0 bytes=100 hooksBefore=1 hooksAfter=2
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-mod-dispatch-self-test phase=snapshot status=passed callbackStatus=0 hooks=2 hook=/Script/DuneServerProbe.ModEntry:Function preCalls=2 postCalls=2 preResult=11 postResult=31 preIsNumber=true postIsNumber=true
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-function-iteration-check source=ForEachFunction status=passed mode=self-test name=DuneServerProbeSelfTestClass class=UClass callbacks=2 functionRegistryCount=1
2026-06-16T17:27:28+0000 pid=100 loader=server event=lua-mod-finish phase=snapshot status=passed scripts=2 loaded=2 failed=0 hooks=2 findObjectCalls=1 findObjectHits=1 getKnownObjectsCalls=1 getKnownObjectsHits=1 findObjectsCalls=1 findObjectsHits=1 findAllOfCalls=1 findAllOfHits=1 forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1
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
    "loadAssetCalls=1 loadAssetHits=1\n",
    (
        "loadAssetCalls=1 loadAssetHits=1 "
        "staticConstructObjectCalls=1 staticConstructObjectHits=1 notifyOnNewObjectCalls=1 notifyOnNewObjectCallbacks=1 notifyOnNewObjectResult=17 notifyOnNewObjectIsNumber=true notifyOnNewObjectStatus=0 executeInGameThreadCalls=1 executeInGameThreadCallbacks=1 executeInGameThreadResult=9 executeInGameThreadIsNumber=true executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2 executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 "
        "notifyOnNewObjectCalls=3 notifyOnNewObjectCallbacks=2 "
        "notifyOnNewObjectResult=19 notifyOnNewObjectIsNumber=true "
        "notifyOnNewObjectStatus=0 staticConstructObjectOuterHits=1 "
        "getWorldCalls=3 getWorldHits=2 "
        "getCdoCalls=1 getCdoHits=1 getLevelCalls=2 getLevelHits=2\n"
    ),
)
SAMPLE_LOG = SAMPLE_LOG.replace(
    "hooks=2 findObjectCalls=1",
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
        "findObjectCalls=1"
    ),
)
SAMPLE_LOG += (
    "2026-06-16T00:00:16Z pid=100 loader=server event=lua-process-event-params-buffer "
    "status=created function=0x2000 descriptorCount=17 size=152 address=0x3000\n"
    "2026-06-16T00:00:16Z pid=100 loader=server event=lua-process-event-native-invoke "
    "phase=snapshot status=descriptor-preflight-ready objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=false nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=0 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:17Z pid=100 loader=server event=lua-process-event-native-invoke "
    "phase=snapshot status=non-self-test-invoke-disabled objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=true nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=0 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:18Z pid=100 loader=server event=lua-process-event-native-invoke-self-test "
    "phase=snapshot status=passed processEventNativeCalls=3 processEventNativeHits=1 liveCalls=2 originalCalls=2\n"
)


def new_loader_identity_sample(log):
    return log.replace(
        "functionPath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function",
        "functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function",
    )


class LinuxLoaderScanSummaryTests(unittest.TestCase):
    def test_runtime_discovery_summary_promoted_roots(self):
        log = """\
2026-06-18T00:00:00Z pid=44 event=loaded exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery-start phase=snapshot mappings=12 maxMappingBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x6000 blockSlot=0x6010 firstBlock=0x8000 blocksOffset=0x10 stride=2 hit=1 imageOffset=0x6000 fileOffset=0x6000 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x7000 base=0x7000 numElements=42 numChunks=1 hit=1 imageOffset=0x7000 fileOffset=0x7000 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=44 loader=server event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x6000 imageOffset=0x6000 fileOffset=0x6000 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=44 loader=server event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x7000 imageOffset=0x7000 fileOffset=0x7000 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery-finish phase=snapshot fnameHits=1 objectArrayHits=1 targetWritableMappings=3 oversizedMappings=1 scannedSlots=4096 fnameProbes=4096 objectArrayProbes=4096 anchors=2
"""
        records = [scan_summary.parse_line(line) for line in log.splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)

        self.assertFalse(summary["ueRuntimeDiscoveryReady"])
        self.assertEqual(summary["ueRuntimeDiscoveryFailure"], "unvalidated-root-hits")
        self.assertEqual(summary["ueRuntimeDiscoveryCandidateCount"], 2)
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["candidateNameCounts"],
            {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 1},
        )
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["candidateImageCounts"],
            {"/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping": 2},
        )
        self.assertEqual(
            [item["imageOffset"] for item in summary["ueRuntimeDiscovery"]["candidateLocations"]],
            ["0x6000", "0x7000"],
        )
        self.assertEqual(
            summary["ueRuntimeDiscovery"]["promotedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(summary["ueRuntimeDiscovery"]["coverage"]["targetWritableImageCount"], 3)
        self.assertEqual(summary["ueRuntimeDiscovery"]["coverage"]["scannedSlots"], 4096)

    def test_runtime_discovery_summary_classifies_missing_target_writable_mapping(self):
        log = """\
2026-06-18T00:00:00Z pid=44 event=loaded exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery-start phase=snapshot mappings=12 maxMappingBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery name=target-writable-image-mappings status=missing phase=snapshot mappings=12
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery name=RuntimeFNamePool status=missing hits=0
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery name=RuntimeGUObjectArray status=missing hits=0
2026-06-18T00:00:01Z pid=44 loader=server event=ue-runtime-discovery-finish phase=snapshot fnameHits=0 objectArrayHits=0 targetWritableMappings=0 oversizedMappings=0 scannedSlots=0 fnameProbes=0 objectArrayProbes=0 anchors=0
"""
        records = [scan_summary.parse_line(line) for line in log.splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)

        self.assertFalse(summary["ueRuntimeDiscoveryReady"])
        self.assertEqual(summary["ueRuntimeDiscoveryFailure"], "no-target-writable-image")
        self.assertEqual(summary["ueRuntimeDiscovery"]["targetWritableMissingCount"], 1)
        self.assertEqual(summary["ueRuntimeDiscovery"]["statusCounts"], {"missing": 2})

    def test_summarize_filters_to_server_pid(self):
        records = [scan_summary.parse_line(line) for line in SAMPLE_LOG.splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)

        self.assertEqual(summary["serverPids"], ["100"])
        self.assertEqual(summary["hitCount"], 3)
        self.assertEqual(summary["uniqueHitCount"], 4)
        self.assertIn("ServerRequestBaseBackup", summary["hitsByName"])
        self.assertNotIn("DeepDesert", summary["hitsByName"])
        self.assertEqual(summary["hitsByName"]["brt-action-guard"]["category"], "brt")
        self.assertEqual(summary["hitsByName"]["GName"]["category"], "ue")
        self.assertEqual(summary["hitsByName"]["SelfTestUObject"]["category"], "ue")
        self.assertEqual(summary["scanFinish"][0]["sizeSkipped"], "0")
        self.assertEqual(summary["mappedUeAnchorCount"], 1)
        self.assertEqual(summary["ueAnchorGroupCounts"], {"self-test": 1})
        self.assertEqual(summary["mappedUeAnchorGroupCounts"], {"self-test": 1})
        self.assertEqual(summary["ueCandidateGlobalCount"], 1)
        self.assertEqual(summary["addedUeCandidateGlobalCount"], 1)
        self.assertEqual(summary["ueCandidateGlobalStatusCounts"], {"added": 1})
        self.assertEqual(summary["mappedUePointerCount"], 1)
        self.assertEqual(summary["readableUeLayoutCount"], 1)
        self.assertEqual(summary["mappedUeLayoutSlotCount"], 1)
        self.assertEqual(summary["candidateUeUObjectCount"], 1)
        self.assertEqual(summary["classMappedUeUObjectCount"], 1)
        self.assertEqual(summary["ueReflectionCount"], 1)
        self.assertEqual(summary["classMappedUeReflectionCount"], 1)
        self.assertEqual(summary["ueReflectionSlotCount"], 3)
        self.assertEqual(summary["mappedUeReflectionSlotCount"], 3)
        self.assertEqual(summary["ueReflectionFieldCount"], 3)
        self.assertEqual(summary["candidateUeReflectionFieldCount"], 3)
        self.assertEqual(summary["classMappedUeReflectionFieldCount"], 3)
        self.assertEqual(summary["ueReflectionPropertyCount"], 2)
        self.assertEqual(summary["candidateUeReflectionPropertyCount"], 2)
        self.assertEqual(summary["readableUeReflectionPropertyCount"], 2)
        self.assertEqual(summary["runtimeUeReflectionPropertyCount"], 0)
        self.assertEqual(summary["runtimeReadableUeReflectionPropertyCount"], 0)
        self.assertEqual(summary["ueReflectionValueCount"], 2)
        self.assertEqual(summary["readUeReflectionValueCount"], 2)
        self.assertEqual(summary["runtimeReadUeReflectionValueCount"], 0)
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
        self.assertEqual(summary["ueFunctionPaths"], ["/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function"])
        self.assertEqual(summary["uniqueUe4ssFunctionPathCount"], 1)
        self.assertEqual(summary["ue4ssFunctionPaths"], ["/Script/SelfTestUObject.SelfTestUObjectName_0:Function"])
        self.assertEqual(summary["readableUeFunctionFlagRootCount"], 1)
        self.assertEqual(summary["readableUeFunctionFlagParamCount"], 1)
        self.assertEqual(summary["ueFunctionFlagPathCount"], 1)
        self.assertEqual(summary["ueFunctionFlagPaths"], ["/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function"])
        self.assertEqual(summary["ueFunctionFlagValues"], ["0x400"])
        self.assertEqual(summary["ueObjectArrayShapeCount"], 2)
        self.assertEqual(summary["plausibleUeObjectArrayShapeCount"], 1)
        self.assertEqual(summary["implausibleUeObjectArrayShapeCount"], 1)
        self.assertEqual(summary["finishedUeObjectArrayCount"], 1)
        self.assertEqual(summary["decodedUeFNameCount"], 2)
        self.assertEqual(summary["passedHookSelfTestCount"], 1)
        self.assertEqual(summary["passedModSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaCallbackSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaApiSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaSchedulerApiSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaInputCommandApiSelfTestCount"], 1)
        self.assertEqual(summary["passedLuaObjectApiSelfTestCount"], 1)
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
        self.assertEqual(summary["nonSelfTestPassedUeCallFunctionHookCount"], 0)
        self.assertEqual(summary["ueCallFunctionLiveHookCount"], 1)
        self.assertEqual(summary["installedUeCallFunctionLiveHookCount"], 1)
        self.assertEqual(summary["nonSelfTestInstalledUeCallFunctionLiveHookCount"], 0)
        self.assertEqual(summary["installedUeProcessEventLiveHookCount"], 1)
        self.assertEqual(summary["nonSelfTestInstalledUeProcessEventLiveHookCount"], 0)
        self.assertEqual(summary["ueProcessEventLiveContextCount"], 1)
        self.assertEqual(summary["resolvedUeProcessEventLiveContextCount"], 0)
        self.assertEqual(summary["matchedUeProcessEventLiveContextCount"], 0)
        self.assertEqual(summary["runtimeMatchedUeProcessEventLiveContextCount"], 0)
        self.assertEqual(summary["runtimeProvenanceUeProcessEventLiveContextCount"], 0)
        self.assertEqual(summary["selfTestProvenanceUeProcessEventLiveContextCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveRegistryContextCount"], 1)
        self.assertEqual(summary["resolvedUeProcessEventLiveRegistryContextCount"], 0)
        self.assertEqual(summary["nativeIdentityUeProcessEventLiveRegistryContextCount"], 0)
        self.assertEqual(summary["matchedUeProcessEventLiveRegistryContextCount"], 0)
        self.assertEqual(summary["runtimeMatchedUeProcessEventLiveRegistryContextCount"], 0)
        self.assertEqual(summary["runtimeProvenanceUeProcessEventLiveRegistryContextCount"], 0)
        self.assertEqual(summary["selfTestProvenanceUeProcessEventLiveRegistryContextCount"], 1)
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
        self.assertEqual(summary["closedUeProcessEventLiveLuaDispatchCount"], 1)
        self.assertEqual(summary["ueProcessEventLiveLuaPathExactMatchCount"], 0)
        self.assertEqual(summary["ueProcessEventLiveLuaPathAliasMatchCount"], 2)
        self.assertEqual(summary["ueProcessEventLiveLuaDispatchStatusCounts"], {"armed": 1, "closed": 1})
        self.assertEqual(summary["passedLuaModScriptCount"], 2)
        self.assertEqual(summary["passedLuaModDispatchSelfTestCount"], 1)
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
        self.assertEqual(summary["luaProcessEventNativeInvokeNonSelfTestGateCount"], 1)
        self.assertEqual(summary["luaProcessEventNativeInvokeNonSelfTestInvokedCount"], 0)
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
        self.assertEqual(summary["runtimeLuaFunctionRegistryCheckCount"], 0)
        self.assertEqual(summary["selfTestLuaFunctionRegistryCheckCount"], 1)
        self.assertEqual(summary["ueLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["runtimeUeLuaObjectRegistryCount"], 0)
        self.assertEqual(summary["selfTestUeLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["objectArrayLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["runtimeObjectArrayLuaObjectRegistryCount"], 0)
        self.assertEqual(summary["selfTestObjectArrayLuaObjectRegistryCount"], 1)
        self.assertEqual(summary["decodedLuaObjectAliasRegistryCount"], 1)
        self.assertEqual(summary["runtimeDecodedLuaObjectAliasRegistryCount"], 0)
        self.assertEqual(summary["selfTestDecodedLuaObjectAliasRegistryCount"], 1)
        self.assertEqual(summary["skippedDecodedLuaObjectAliasRegistryCount"], 1)
        self.assertEqual(summary["luaObjectOuterChainCount"], 1)
        self.assertEqual(summary["resolvedLuaObjectOuterChainCount"], 1)
        self.assertEqual(summary["luaObjectOuterChainIdentityCount"], 1)
        self.assertEqual(summary["luaGlobalRuntimeHelperCheckCount"], 1)
        self.assertEqual(summary["passedLuaGlobalRuntimeHelperCheckCount"], 1)
        self.assertEqual(summary["promotedWorldLuaGlobalRuntimeHelperCheckCount"], 1)
        self.assertEqual(summary["promotedEngineLuaGlobalRuntimeHelperCheckCount"], 0)
        self.assertEqual(summary["ueObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["promotedUeObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["decodedNameUeObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["decodedClassNameUeObjectNativeIdentityCount"], 2)
        self.assertEqual(summary["ueFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["promotedUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["readableFlagUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["runtimePathUeFunctionNativeIdentityCount"], 1)
        self.assertEqual(summary["ue4ssPathUeFunctionNativeIdentityCount"], 1)

    def test_summarize_new_loader_script_and_runtime_function_paths(self):
        records = [scan_summary.parse_line(line) for line in new_loader_identity_sample(SAMPLE_LOG).splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)

        self.assertEqual(summary["ueFunctionPaths"], ["/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function"])
        self.assertEqual(summary["ue4ssFunctionPaths"], ["/Script/SelfTestUObject.SelfTestUObjectName_0:Function"])

    def test_load_asset_package_mod_finish_requires_package_backend_evidence(self):
        backend_state_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 loadAssetPackageArmed=false",
        )
        records = [scan_summary.parse_line(line) for line in backend_state_log.splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
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
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
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
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
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
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageBridgeStateModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageAbiStateEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_abi_state_log = (
            package_native_invoke_log
            + "\n2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-abi-state "
            "status=anchor-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=sysv-x86_64 "
            "signatureFamily=StaticLoadObject abiVerified=false callFrameReady=false "
            "stringBridgeReady=false classRootReady=false outerReady=false packageAvailable=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_abi_state_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageAbiStateEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageStringBridgeEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_string_bridge_log = (
            package_abi_state_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-string-bridge-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=sysv-x86_64 stringInputStaged=true boundedInput=true utf8ByteCount=37 "
            "inputEncoding=utf-8 tcharEncoding=unverified-live-build tcharBridgeReady=false "
            "nativeBufferReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_string_bridge_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageStringBridgeEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeBufferEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_buffer_log = (
            package_string_bridge_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-native-buffer-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=sysv-x86_64 stringInputStaged=true boundedInput=true "
            "utf8BufferReady=true nativeInputBufferReady=true bufferBytes=38 nullTerminated=true "
            "tcharEncoding=unverified-live-build tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_buffer_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageNativeBufferEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageTCharBufferEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_tchar_buffer_log = (
            package_native_buffer_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-tchar-buffer-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=sysv-x86_64 stringInputStaged=true boundedInput=true "
            "candidateEncoding=host-wchar-unverified candidateUnitBytes=4 candidateBufferBytes=152 "
            "tcharLayoutVerified=false tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_tchar_buffer_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageTCharBufferEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageTCharVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_tchar_verification_log = (
            package_tchar_buffer_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-tchar-verification-state "
            "status=evidence-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=sysv-x86_64 "
            "candidateEncoding=host-wchar-unverified candidateUnitBytes=4 observedUnitBytes=0 "
            "evidenceProvided=false verificationEnabled=false unitMatch=false "
            "tcharLayoutVerified=false tcharBufferReady=false evidence=none\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_tchar_verification_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageTCharVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_call_frame_verification_log = (
            package_tchar_verification_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-call-frame-verification-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 targetImage=false platformAbi=sysv-x86_64 signatureFamily=StaticLoadObject argumentCount=7 "
            "pathStaged=true boundedInput=true abiEvidenceProvided=false abiVerificationEnabled=false "
            "abiVerified=false tcharEvidenceProvided=false tcharVerificationEnabled=false "
            "tcharLayoutVerified=false tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_call_frame_verification_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_call_adapter_log = (
            package_call_frame_verification_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-native-call-adapter-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=sysv-x86_64 adapterKind=sysv-x86_64-package-load "
            "signatureFamily=StaticLoadObject argumentCount=7 pathStaged=true boundedInput=true "
            "functionPointerReady=false abiVerified=false tcharLayoutVerified=false callFrameReady=false "
            "invokeEnabled=false nativeBridgeArmed=false adapterReady=false finalInvokeConfirmed=false crashGuardRequired=true crashGuardArmed=false guardedCallRequired=true guardedCallReady=true guardedCallResult=17 returnValidationReady=true invocationDescriptorRequired=true invocationDescriptorConsumed=true nativeCallPlanAccepted=true nativeCallExecutionMode=guarded-native-package-load nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallable=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_native_call_adapter_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_invocation_descriptor_log = (
            package_native_call_adapter_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-invocation-descriptor-state "
            "status=derived descriptorKind=guarded-package-native-call "
            "descriptorProvenance=adapter-state-derived nativeCallPlanConstructed=true nativeCallExecutionMode=guarded-native-package-load nativeCallTargetField=TargetAddress nativeCallPathField=Path nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallReturnValidator=uobject-registry-memory-class nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_invocation_descriptor_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_executor_log = (
            package_invocation_descriptor_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-native-executor-state "
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
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeCallAdapterEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageInvocationDescriptorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorReadyEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        package_native_executor_ready_log = package_invocation_descriptor_log + (
            "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-native-executor-state "
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
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorEventCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageNativeExecutorReadyEventCount"], 1)

        package_call_frame_log = (
            package_native_executor_log
            + "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-call-frame-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=sysv-x86_64 signatureFamily=StaticLoadObject pathStaged=true "
            "argumentDescriptorReady=true tcharBridgeReady=false callFrameReady=false nativeInvoked=false\n"
        )
        records = [
            record
            for record in (scan_summary.parse_line(line) for line in package_call_frame_log.splitlines())
            if record
        ]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
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
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageNativeInvokeModFinishCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackagePreflightModFinishCount"], 1)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 0)

        explicit_package_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetPackageCalls=1 loadAssetPackageHits=1",
        )
        records = [scan_summary.parse_line(line) for line in explicit_package_log.splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 1)

        backend_package_log = SAMPLE_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 loadAssetBackend=package",
        )
        records = [scan_summary.parse_line(line) for line in backend_package_log.splitlines()]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageModFinishCount"], 1)

    def test_package_state_events_require_target_image_provenance(self):
        log = (
            SAMPLE_LOG
            + "\n2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-abi-state "
            "status=anchor-missing targetName=StaticLoadObject target=0x0 platformAbi=sysv-x86_64 "
            "signatureFamily=StaticLoadObject abiVerified=false callFrameReady=false "
            "stringBridgeReady=false classRootReady=false outerReady=false packageAvailable=false\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-tchar-verification-state "
            "status=target-not-target-image targetName=StaticLoadObject target=0x1234 targetImage=true "
            "platformAbi=sysv-x86_64 candidateEncoding=host-wchar-unverified candidateUnitBytes=4 "
            "observedUnitBytes=4 evidenceProvided=true verificationEnabled=true unitMatch=true "
            "tcharLayoutVerified=false tcharBufferReady=false evidence=self-test\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=lua-load-asset-package-call-frame-verification-state "
            "status=call-frame-ready path=/Script/DuneProbe.Asset targetName=StaticLoadObject "
            "target=0x1234 targetImage=false platformAbi=sysv-x86_64 signatureFamily=StaticLoadObject "
            "argumentCount=7 pathStaged=true boundedInput=true abiEvidenceProvided=true "
            "abiVerificationEnabled=true abiVerified=true tcharEvidenceProvided=true "
            "tcharVerificationEnabled=true tcharLayoutVerified=true tcharBufferReady=true "
            "callFrameReady=true nativeInvoked=false\n"
        )
        records = [record for record in (scan_summary.parse_line(line) for line in log.splitlines()) if record]
        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        self.assertEqual(summary["luaLoadAssetPackageAbiStateEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageTCharVerificationEventCount"], 0)
        self.assertEqual(summary["luaLoadAssetPackageCallFrameVerificationEventCount"], 0)

    def test_explicit_reflection_descriptor_provenance_overrides_name_heuristic(self):
        self_test_log = (
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-reflection-property "
            "name=GWorld chain=propertyLink index=0 descriptorProvenance=self-test status=candidate "
            "field=0x1000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 "
            "arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-reflection-value "
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

        self_test_summary = scan_summary.summarize(self_test_records, "DuneSandboxServer", None)
        runtime_summary = scan_summary.summarize(runtime_records, "DuneSandboxServer", None)

        self.assertEqual(self_test_summary["runtimeReadableUeReflectionPropertyCount"], 0)
        self.assertEqual(self_test_summary["runtimeReadUeReflectionValueCount"], 0)
        self.assertEqual(runtime_summary["runtimeReadableUeReflectionPropertyCount"], 1)
        self.assertEqual(runtime_summary["runtimeReadUeReflectionValueCount"], 1)

    def test_reflection_runtime_counts_require_explicit_runtime_provenance(self):
        log = (
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-reflection-property "
            "name=GWorld chain=propertyLink index=0 status=candidate "
            "field=0x1000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 "
            "arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-reflection-value "
            "name=GWorld chain=propertyLink index=0 fieldName=DecodedWorld "
            "status=read object=0x2000 address=0x200c offsetInternal=12 elementSize=4 arrayDim=1 "
            "requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false\n"
        )
        records = [scan_summary.parse_line(line) for line in log.splitlines()]

        summary = scan_summary.summarize(records, "DuneSandboxServer", None)

        self.assertEqual(summary["readableUeReflectionPropertyCount"], 1)
        self.assertEqual(summary["readUeReflectionValueCount"], 1)
        self.assertEqual(summary["runtimeReadableUeReflectionPropertyCount"], 0)
        self.assertEqual(summary["runtimeReadUeReflectionValueCount"], 0)

    def test_live_hook_proven_target_counts_require_runtime_target_provenance(self):
        log = (
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-process-event-hook "
            "phase=snapshot status=passed target=0x4000 installed=true restored=true "
            "selfTestTarget=false targetSource=explicit targetName=ProcessEvent callSelfTest=false\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-call-function-hook "
            "phase=snapshot status=passed target=0x4100 installed=true restored=true "
            "selfTestTarget=false targetSource=explicit targetName=CallFunctionByNameWithArguments callSelfTest=false\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-call-function-live-hook "
            "phase=snapshot status=installed target=0x4100 selfTestTarget=false "
            "targetSource=explicit targetName=CallFunctionByNameWithArguments callSelfTest=false "
            "luaDispatch=true luaPreCalls=1 luaPostCalls=1 luaPreHandled=1 luaPostHandled=1 "
            "liveCalls=1 originalCalls=1 result=42 trampoline=0x5200\n"
            "2026-01-01T00:00:00Z pid=100 loader=server event=ue-process-event-live-hook "
            "phase=snapshot status=installed target=0x4000 selfTestTarget=false "
            "targetSource=explicit targetName=ProcessEvent callSelfTest=false "
            "dispatchCallbacks=2 luaDispatch=true luaPreStatus=0 luaPostStatus=0 luaPreCalls=1 luaPostCalls=1 "
            "luaObjectHandleHits=2 luaFunctionHandleHits=2 luaParamsHandleHits=2 luaParamDescriptorHits=2 "
            "luaParamDescriptorLookupCalls=17 luaParamDescriptorLookupHits=17 luaFunctionParamDescriptorCalls=2 "
            "luaFunctionParamDescriptorHits=4 luaFunctionParamMethodHits=2 luaFunctionParamLookupMethodHits=2 "
            "luaFunctionParamIterationMethodHits=12 luaContainerAliasHits=6 luaContainerStorageLayoutHits=9 "
            "luaParamGetCalls=29 luaParamGetHits=29 luaParamSetCalls=11 luaParamSetHits=11 "
            "luaEnumParamAccessors=true luaObjectParamAccessors=true luaBoolParamAccessors=true "
            "preCallbacks=2 postCallbacks=2 liveCalls=1 originalCalls=1 paramsResult=62 paramsTouched=1 "
            "trampoline=0x5000\n"
        )
        records = [scan_summary.parse_line(line) for line in log.splitlines()]

        summary = scan_summary.summarize(records, "DuneSandboxServer", None)
        unproven_summary = scan_summary.summarize(
            [scan_summary.parse_line(line) for line in log.replace(" targetSource=explicit targetName=ProcessEvent", "").replace(" targetSource=explicit targetName=CallFunctionByNameWithArguments", "").splitlines()],
            "DuneSandboxServer",
            None,
        )

        self.assertEqual(summary["provenTargetPassedUeProcessEventHookCount"], 1)
        self.assertEqual(summary["provenTargetInstalledUeProcessEventLiveHookCount"], 1)
        self.assertEqual(summary["provenTargetPassedUeCallFunctionHookCount"], 1)
        self.assertEqual(summary["provenTargetInstalledUeCallFunctionLiveHookCount"], 1)
        self.assertEqual(summary["provenTargetRoutedUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(summary["provenTargetHandledUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(unproven_summary["nonSelfTestInstalledUeProcessEventLiveHookCount"], 1)
        self.assertEqual(unproven_summary["routedUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(unproven_summary["handledUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(unproven_summary["provenTargetPassedUeProcessEventHookCount"], 0)
        self.assertEqual(unproven_summary["provenTargetInstalledUeProcessEventLiveHookCount"], 0)
        self.assertEqual(unproven_summary["provenTargetPassedUeCallFunctionHookCount"], 0)
        self.assertEqual(unproven_summary["provenTargetInstalledUeCallFunctionLiveHookCount"], 0)
        self.assertEqual(unproven_summary["provenTargetRoutedUeCallFunctionLiveLuaHookCount"], 0)
        self.assertEqual(unproven_summary["provenTargetHandledUeCallFunctionLiveLuaHookCount"], 0)

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "loader.log"
            log.write_text(SAMPLE_LOG, encoding="utf-8")
            result = subprocess.run(
                [str(SCRIPT), str(log), "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        summary = json.loads(result.stdout)
        self.assertEqual(summary["hitCount"], 3)
        self.assertEqual(summary["categories"], {"brt": 2, "ue": 2})


if __name__ == "__main__":
    unittest.main()
