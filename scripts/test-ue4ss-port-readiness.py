#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "ue4ss-port-readiness.py",
    ROOT / "analysis" / "ue4ss-port-readiness.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("ue4ss_port_readiness", SCRIPT)
readiness = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(readiness)


PARTIAL_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-start strings=2 signatures=0 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=FNamePool addr=0x140010000 rva=0x10000 allocationBase=0x140000000 regionBase=0x140010000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-finish
"""


SIGNATURE_ANCHOR_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-start strings=0 signatures=4 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=FNamePool group=names status=resolved hit=0x140001000 addr=0x140010000 transform=riprel32+3 rva=0x10000 allocationBase=0x140000000 regionBase=0x140010000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GUObjectArray group=objects status=resolved hit=0x140002000 addr=0x140020000 transform=riprel32+3 rva=0x20000 allocationBase=0x140000000 regionBase=0x140020000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GWorld group=world status=resolved hit=0x140003000 addr=0x140030000 transform=riprel32+3 rva=0x30000 allocationBase=0x140000000 regionBase=0x140030000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=ProcessEvent group=dispatch status=resolved hit=0x140004000 addr=0x140040000 transform=callrel32 rva=0x40000 allocationBase=0x140000000 regionBase=0x140040000 protect=0x20 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticLoadObject group=package status=resolved hit=0x140004800 addr=0x140048000 transform=callrel32 rva=0x48000 allocationBase=0x140000000 regionBase=0x140048000 protect=0x20 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UObject group=reflection status=resolved hit=0x140005000 addr=0x140050000 transform=hit rva=0x50000 allocationBase=0x140000000 regionBase=0x140050000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UFunction group=reflection status=resolved hit=0x140006000 addr=0x140060000 transform=hit rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticFindObject group=dispatch status=missing oversizedRegions=0
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-finish
"""


READY_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-start strings=8 signatures=1 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x1400b0000 blockSlot=0x1400b0010 firstBlock=0x1400c0000 blocksOffset=0x10 stride=2 hit=1 rva=0xb0000 allocationBase=0x140000000 regionBase=0x1400b0000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140090000 base=0x140090000 numElements=1 numChunks=1 hit=1 rva=0x90000 allocationBase=0x140000000 regionBase=0x140090000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x1400b0000 rva=0xb0000 allocationBase=0x140000000 regionBase=0x1400b0000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x140090000 rva=0x90000 allocationBase=0x140000000 regionBase=0x140090000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=1 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=0 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=FNamePool addr=0x140010000 rva=0x10000 allocationBase=0x140000000 regionBase=0x140010000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=GUObjectArray addr=0x140020000 rva=0x20000 allocationBase=0x140000000 regionBase=0x140020000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=GWorld addr=0x140030000 rva=0x30000 allocationBase=0x140000000 regionBase=0x140030000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=ProcessEvent addr=0x140040000 rva=0x40000 allocationBase=0x140000000 regionBase=0x140040000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=UObject addr=0x140050000 rva=0x50000 allocationBase=0x140000000 regionBase=0x140050000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=UFunction addr=0x140060000 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x2 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=FNamePool group=names status=resolved hit=0x140001000 addr=0x140010000 transform=riprel32+3 rva=0x10000 allocationBase=0x140000000 regionBase=0x140010000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GUObjectArray group=objects status=resolved hit=0x140002000 addr=0x140020000 transform=riprel32+3 rva=0x20000 allocationBase=0x140000000 regionBase=0x140020000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GWorld group=world status=resolved hit=0x140003000 addr=0x140030000 transform=riprel32+3 rva=0x30000 allocationBase=0x140000000 regionBase=0x140030000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=ProcessEvent group=dispatch status=resolved hit=0x140004000 addr=0x140040000 transform=callrel32 rva=0x40000 allocationBase=0x140000000 regionBase=0x140040000 protect=0x20 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticLoadObject group=package status=resolved hit=0x140004800 addr=0x140048000 transform=callrel32 rva=0x48000 allocationBase=0x140000000 regionBase=0x140048000 protect=0x20 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UObject group=reflection status=resolved hit=0x140005000 addr=0x140050000 transform=hit rva=0x50000 allocationBase=0x140000000 regionBase=0x140050000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UFunction group=reflection status=resolved hit=0x140006000 addr=0x140060000 transform=hit rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-pointer name=GWorld status=target-mapped anchor=0x140030000 value=0x140070000 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-layout name=GWorld status=target-readable anchor=0x140030000 target=0x140070000 slots=2 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-layout-slot name=GWorld target=0x140070000 offset=0x0 value=0x140080000 status=target-mapped readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-layout-slot name=GWorld target=0x140070000 offset=0x8 value=0x0 status=null
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-uobject status=added name=GWorld path=/RuntimeProbe/GWorld class=UObjectCandidate address=0x140070000 registryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-uobject status=passed name=GWorld path=/RuntimeProbe/GWorld class=UObjectCandidate address=0x140070000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-uobject name=GWorld status=candidate anchor=0x140030000 target=0x140070000 vtable=0x140080000 vtableMapped=true objectFlags=0x11 internalIndex=7 class=0x140070000 classMapped=true nameComparisonIndex=1234 nameNumber=1 outer=0x0 outerMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection name=GWorld status=class-mapped object=0x140070000 class=0x140070000 classVtable=0x140080000 classVtableMapped=true classNameComparisonIndex=1234 classNameNumber=1 slots=6 nextOffset=0x28 superOffset=0x30 childrenOffset=0x38 childPropertiesOffset=0x40 propertyLinkOffset=0x48 functionLinkOffset=0x50
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-slot name=GWorld slot=children status=target-mapped class=0x140070000 offset=0x38 value=0x140080000 readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-slot name=GWorld slot=propertyLink status=target-mapped class=0x140070000 offset=0x48 value=0x140080000 readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-slot name=GWorld slot=functionLink status=target-mapped class=0x140070000 offset=0x50 value=0x140080000 readable=true writable=true executable=false protect=0x4
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-field name=GWorld chain=children index=0 status=candidate field=0x140080000 class=0x140070000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-field name=GWorld chain=propertyLink index=0 status=candidate field=0x140081000 class=0x140070000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-field name=GWorld chain=functionLink index=0 status=candidate field=0x140082000 class=0x140070000 classMapped=true nameComparisonIndex=1234 nameNumber=1 next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param-root name=GWorld functionIndex=0 chain=childProperties status=root function=0x140082000 offset=0x40 root=0x140083000 functionFlags=0x400 functionFlagsReadable=true functionFlagsOffset=0x58
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-native-identity source=ue-function-param status=promoted name=GWorld functionIndex=0 chain=childProperties function=0x140082000 functionName=DecodedFunction_0 functionPath=/Script/GWorld.DecodedFunction_0:Function functionRuntimePath=/RuntimeProbe/GWorld.DecodedFunction_0:Function root=0x140083000 functionFlags=0x400 functionFlagsReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-function-registry-check source=ue-function-param status=passed name=DecodedFunction_0 path=/Script/GWorld.DecodedFunction_0:Function runtimePath=/RuntimeProbe/GWorld.DecodedFunction_0:Function address=0x140082000 pathHit=true runtimePathHit=true nameHit=true addressHit=true flagsHit=true registryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param name=GWorld functionIndex=0 chain=childProperties index=0 status=candidate function=0x140082000 functionName=DecodedFunction_0 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function field=0x140083000 class=0x140070000 classMapped=true nameComparisonIndex=1234 nameNumber=1 fieldName=DecodedParam_0 arrayDim=1 elementSize=4 propertyFlags=0x80 offsetInternal=16 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true functionFlags=0x400 functionFlagsReadable=true next=0x0 nextReadable=true nextMapped=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param-container-child name=GWorld functionIndex=0 chain=childProperties index=0 status=candidate field=0x140083000 containerClassName=FArrayProperty role=inner child=0x140084000 childOffset=0x70 childClass=0x140070000 childClassMapped=true childClassName=FIntProperty childNameComparisonIndex=1235 childNameNumber=1 childName=DecodedArrayInner_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-function-param-root name=GWorld functionIndex=0 chain=propertyLink status=null-root function=0x140082000 offset=0x48
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-property name=GWorld descriptorProvenance=runtime chain=childProperties index=0 status=candidate field=0x140081000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-property name=GWorld descriptorProvenance=runtime chain=propertyLink index=0 status=candidate field=0x140081000 arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12 arrayDimReadable=true elementSizeReadable=true propertyFlagsReadable=true offsetInternalReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-value name=GWorld descriptorProvenance=runtime chain=childProperties index=0 fieldName=DecodedWorld_0 status=read object=0x140070000 address=0x14007000c offsetInternal=12 elementSize=4 arrayDim=1 requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-reflection-value name=GWorld descriptorProvenance=runtime chain=propertyLink index=0 fieldName=DecodedWorld_0 status=read object=0x140070000 address=0x14007000c offsetInternal=12 elementSize=4 arrayDim=1 requestedBytes=4 readBytes=4 raw=07000000 rawLe=0x7 truncated=false
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-fname source=ue-uobject objectName=GWorld status=decoded object=0x140070000 pool=0x1400b0000 resolver=FNamePool:direct comparisonIndex=1234 number=1 block=0 offset=0x4d2 entry=0x1400b1348 wide=false decoded=DecodedWorld_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-native-identity source=ue-uobject status=promoted object=0x140070000 name=DecodedWorld_0 class=0x140070000 className=DecodedWorldClass_0 outer=0x0 nameDecoded=true classNameDecoded=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-uobject-fname status=added name=DecodedWorld_0 path=/RuntimeProbe/DecodedWorld_0 aliasOf=GWorld class=UObjectCandidate address=0x140070000 registryCount=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-uobject-fname status=passed name=DecodedWorld_0 path=/RuntimeProbe/DecodedWorld_0 class=UObjectCandidate address=0x140070000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array-shape name=GWorld mode=indirect status=header-plausible base=0x140090000 chunks=0x1400a0000 maxElements=2 numElements=1 maxChunks=1 numChunks=1 countsPlausible=true chunkSlotReadable=true firstChunk=0x1400a1000 firstChunkMapped=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array name=GWorld mode=indirect status=scanning base=0x140090000 chunks=0x1400a0000 maxElements=2 numElements=1 maxChunks=1 numChunks=1 limit=1 itemSize=24 chunkSize=65536
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-object-array status=added name=GWorld_0 path=/RuntimeProbe/GWorld_0 class=UObjectArrayItem address=0x140070000 registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-object-array status=passed name=GWorld_0 path=/RuntimeProbe/GWorld_0 class=UObjectArrayItem address=0x140070000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-outer-chain status=resolved object=0x140071000 path=/RuntimeProbe/ChildWorldObject class=UObjectCandidate outer=0x140070000 depth=1 terminal=0x140070000 terminalPath=/RuntimeProbe/GWorld terminalClass=UObjectCandidate chain=/RuntimeProbe/ChildWorldObject<-/RuntimeProbe/GWorld reconstructedPath=/RuntimeProbe/GWorld.ChildWorldObject reconstructedFullName=UObjectCandidate_/RuntimeProbe/GWorld.ChildWorldObject fullNameResolved=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-global-runtime-helper-check status=passed globalWorld=true globalWorldPromoted=true globalWorldAddress=0x140070000 globalWorldPath=/RuntimeProbe/GWorld_0 globalWorldClass=UObjectArrayItem globalEngine=true globalEnginePromoted=false globalEngineAddress=0x140120000 globalEnginePath=/RuntimeProbe/Engine globalEngineClass=UEngine getWorldCalls=3 getWorldHits=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array-item name=GWorld index=0 status=registered object=0x140070000 class=0x140070000 outer=0x0 internalFlags=0x2000000 internalFlagsReadable=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-fname source=ue-object-array objectName=GWorld_0 status=decoded object=0x140070000 pool=0x1400b0000 resolver=FNamePool:direct comparisonIndex=1234 number=1 block=0 offset=0x4d2 entry=0x1400b1348 wide=false decoded=DecodedWorld_0
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-native-identity source=ue-object-array status=promoted object=0x140070000 name=DecodedWorld_0 class=0x140070000 className=DecodedWorldClass_0 outer=0x0 nameDecoded=true classNameDecoded=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry source=ue-object-array-fname status=skipped name=DecodedWorld_0 path=/RuntimeProbe/DecodedWorld_0 aliasOf=GWorld_0 class=UObjectArrayItem address=0x140070000 registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-object-registry-check source=ue-object-array-fname status=passed name=DecodedWorld_0 path=/RuntimeProbe/DecodedWorld_0 class=UObjectArrayItem address=0x140070000 pathHit=true nameHit=true classHit=true addressHit=true registryCount=3
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-object-array name=GWorld mode=indirect status=finished base=0x140090000 scanned=1 registered=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-hook phase=thread status=passed target=0x140040000 installed=true restored=true selfTestTarget=false callSelfTest=false liveCalls=0 originalCalls=0 paramsResult=0 paramsTouched=0 trampoline=0x1400c0000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-call-function-hook phase=thread status=passed target=0x140041000 installed=true restored=true selfTestTarget=false callSelfTest=false before=0 after=0 final=0 original=0 trampoline=0x1400c1000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-call-function-live-hook phase=thread status=installed target=0x140041000 selfTestTarget=false callSelfTest=false liveCalls=0 originalCalls=0 result=0 trampoline=0x1400c2000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-dispatch-self-test phase=thread status=armed preRegistered=true postRegistered=true callbacks=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-lua-dispatch phase=thread status=armed library=lua54.dll loadStatus=0 callStatus=0 result=4 isNumber=true hooks=2 hook=/Script/DuneProbeAlias.SelfTestUObjectName_0:Function callbacks=4 scriptBytes=111
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-context status=resolved call=1 object=0x140070000 objectResolved=true objectPath=/RuntimeProbe/GWorld objectClass=UObjectCandidate function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function functionProvenance=runtime functionParamDescriptors=1 params=0x20 paramsPresent=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-registry-context status=resolved call=1 object=0x140070000 objectResolved=true objectNativeIdentity=true objectPath=/RuntimeProbe/GWorld objectClass=UObjectCandidate function=0x140082000 functionResolved=true functionNativeIdentity=true functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function functionRuntimePath=/RuntimeProbe/GWorld.DecodedFunction_0:Function functionProvenance=runtime functionParamDescriptors=1 params=0x20 paramsPresent=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=read call=1 function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function param=DecodedParam_0 className=FIntProperty type=int32 offset=16 size=4 value=62
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=raw call=1 function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function param=DecodedStruct_0 className=FStructProperty type=struct offset=24 size=16 value=rawHex=0102030405060708090a0b0c0d0e0f10
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=container call=1 function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function param=DecodedArray_0 className=FArrayProperty type=array offset=40 size=16 value=kind=FScriptArray,data=0x1400f0000,num=2,max=4,rawHex=00000f40010000000200000004000000,dataSampleHex=2a0000002b0000002c0000002d000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=container call=1 function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function param=DecodedSet_0 className=FSetProperty type=set offset=56 size=16 value=kind=FScriptSetHeader,data=0x140100000,num=1,max=2,rawHex=00001040010000000100000002000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-param status=container call=1 function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function param=DecodedMap_0 className=FMapProperty type=map offset=72 size=16 value=kind=FScriptMapHeader,data=0x140110000,num=1,max=2,rawHex=00001140010000000100000002000000
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-hook phase=thread status=installed target=0x140040000 selfTestTarget=false callSelfTest=false dispatchCallbacks=4 luaDispatch=true luaPreStatus=0 luaPostStatus=0 luaPreCalls=1 luaPostCalls=1 luaObjectHandleHits=2 luaFunctionHandleHits=2 luaParamsHandleHits=2 luaParamDescriptorHits=2 luaParamDescriptorLookupCalls=17 luaParamDescriptorLookupHits=17 luaFunctionParamDescriptorCalls=2 luaFunctionParamDescriptorHits=4 luaFunctionParamMethodHits=2 luaFunctionParamLookupMethodHits=2 luaFunctionParamIterationMethodHits=12 luaContainerAliasHits=6 luaContainerStorageLayoutHits=9 luaParamGetCalls=29 luaParamGetHits=29 luaParamSetCalls=11 luaParamSetHits=11 luaEnumParamAccessors=true luaObjectParamAccessors=true luaBoolParamAccessors=true preCallbacks=2 postCallbacks=2 liveCalls=1 originalCalls=1 paramsResult=62 paramsTouched=1 trampoline=0x1400d0000
2026-06-16T17:43:40Z pid=312 loader=win-client event=ue-process-event-live-lua-dispatch phase=detach status=closed preCalls=1 postCalls=1 preResult=11 postResult=31 preStatus=0 postStatus=0 pathExactMatches=0 pathAliasMatches=2
2026-06-16T17:43:39Z pid=312 loader=win-client event=hook-dispatch-self-test phase=thread status=passed before=42 after=1042 final=42 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 installed=true restored=true target=0x140090000 replacement=0x140091000 trampoline=0x140092000
2026-06-16T17:43:39Z pid=312 loader=win-client event=mod-dispatch-self-test phase=thread status=passed mods=1 loaded=1 unloaded=1 result=1042 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 loadCallbacks=1 unloadCallbacks=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-dispatch-self-test phase=thread status=passed library=lua54.dll loadStatus=0 callStatus=0 callbackStatus=0 result=42 isNumber=true hooks=1 hook=/Script/DuneProbe.SelfTest:Function preRef=3 postRef=4 preCalls=1 postCalls=1 preResult=11 postResult=31 preIsNumber=true postIsNumber=true objectHandles=5 ueObjectHandles=2 staticFindObjectCalls=1 staticFindObjectHits=1 findObjectCalls=1 findObjectHits=1 findFirstOfCalls=1 findFirstOfHits=1 getKnownObjectsCalls=1 getKnownObjectsHits=1 findObjectsCalls=1 findObjectsHits=1 findAllOfCalls=1 findAllOfHits=1 forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=6 isAHits=5 loadAssetCalls=1 loadAssetHits=1 staticConstructObjectCalls=1 staticConstructObjectHits=1 notifyOnNewObjectCalls=1 notifyOnNewObjectCallbacks=1 notifyOnNewObjectResult=17 notifyOnNewObjectIsNumber=true notifyOnNewObjectStatus=0 executeInGameThreadCalls=1 executeInGameThreadCallbacks=1 executeInGameThreadResult=9 executeInGameThreadIsNumber=true executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2 executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 keyBindRegistrations=1 keyBindLookupCalls=2 keyBindLookupHits=1 keyBindDispatchCalls=2 keyBindCallbackCalls=1 keyBindCallbackHandled=1 keyBindUnregisterCalls=1 keyBindUnregisterHits=1 consoleCommandHandlers=2 consoleCommandGlobalHandlers=1 consoleCommandHandlerCalls=1 consoleCommandHandlerHandled=0 consoleCommandGlobalHandlerCalls=1 consoleCommandGlobalHandlerHandled=1 consoleCommandUnregisterCalls=1 consoleCommandUnregisterHits=1 scriptBytes=612
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-reflection-self-test phase=thread status=passed library=lua54.dll loadStatus=0 callStatus=0 result=42 isNumber=true staticFindObjectCalls=2 staticFindObjectHits=2 getPropertyCalls=20 getPropertyHits=20 rawPropertyHits=2 rawPropertyValue=17 namedPropertyHits=2 rawPropertySetHits=1 rawPropertySetValue=17 arrayInnerPropertyHits=1 enumPropertyHits=1 enumUnderlyingPropertyHits=1 setElementPropertyHits=1 mapKeyPropertyHits=1 mapValuePropertyHits=1 importTextHits=2 exportTextHits=2 propertyMetadataHits=7 descriptorValueGetHits=21 descriptorValueSetHits=9 descriptorValueAliasHits=3 reflectionForEachPropertyHits=2 runtimeReflectionForEachPropertyCallbacks=1 selfTestReflectionForEachPropertyCallbacks=13 liveDescriptorTypedClassHits=2 runtimeLiveDescriptorTypedClassHits=2 selfTestLiveDescriptorTypedClassHits=0 liveDescriptorTypedValueHits=2 runtimeLiveDescriptorTypedValueHits=2 selfTestLiveDescriptorTypedValueHits=0 liveDescriptorTypedValueSetHits=1 runtimeLiveDescriptorTypedValueSetHits=1 selfTestLiveDescriptorTypedValueSetHits=0 liveDescriptorValueGetHits=2 liveDescriptorValueSetHits=1 runtimeLiveDescriptorValueGetHits=2 selfTestLiveDescriptorValueGetHits=0 runtimeLiveDescriptorValueSetHits=1 selfTestLiveDescriptorValueSetHits=0 setPropertyCalls=10 setPropertyHits=10 callFunctionCalls=2 callFunctionHits=2 probeValue=21 probeBool=false probeFloat=13.750 probeDouble=-47.500 probeName=ArrakisName probeString=melange probeText=WaterDebt probeObject=0x1234 objectHandles=3 ueObjectHandles=2 scriptBytes=2200
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-process-event-self-test phase=thread status=passed library=lua54.dll loadStatus=0 callStatus=0 result=4 isNumber=true hooks=2 hook=/Script/DuneProbe.SelfTest:Function installed=true restored=true hookCalls=1 originalCalls=2 originalAfterHook=1 preStatus=0 postStatus=0 preCalls=1 postCalls=1 preResult=11 postResult=31 preIsNumber=true postIsNumber=true pathExactMatches=2 pathAliasMatches=0 paramDescriptorHits=2 paramDescriptorLookupCalls=17 paramDescriptorLookupHits=17 functionParamDescriptorCalls=2 functionParamDescriptorHits=4 functionParamMethodHits=2 functionParamLookupMethodHits=2 functionParamIterationMethodHits=12 containerAliasHits=6 containerStorageLayoutHits=9 paramGetCalls=29 paramGetHits=29 paramSetCalls=11 paramSetHits=11 enumParamAccessors=true objectParamAccessors=true boolParamAccessors=true paramsResult=42 paramsTouched=1 finalResult=52 finalTouched=1 object=0x140070000 function=0x140061000 params=0x20 trampoline=0x140092000 scriptBytes=103
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-start phase=thread status=running library=lua54.dll scripts=2 skipped=0
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-script phase=thread status=passed name=CallbackMod path=C:\\mods\\CallbackMod\\Scripts\\main.lua loadStatus=0 callStatus=0 hooksBefore=0 hooksAfter=1 scriptBytes=100
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-script phase=thread status=passed name=CallbackModTwo path=C:\\mods\\CallbackModTwo\\Scripts\\main.lua loadStatus=0 callStatus=0 hooksBefore=1 hooksAfter=2 scriptBytes=100
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-dispatch-self-test phase=thread status=passed callbackStatus=0 hooks=2 hook=/Script/DuneProbe.ModEntry:Function preCalls=2 postCalls=2 preResult=11 postResult=31 preIsNumber=true postIsNumber=true
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-function-iteration-check source=ForEachFunction status=passed mode=owner name=GWorld class=UObjectCandidate callbacks=2 functionRegistryCount=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=lua-mod-finish phase=thread status=passed library=lua54.dll scripts=2 loaded=2 failed=0 hooks=2 skipped=0 objectHandles=4 ueObjectHandles=2 staticFindObjectCalls=1 staticFindObjectHits=1 findObjectCalls=1 findObjectHits=1 findFirstOfCalls=1 findFirstOfHits=1 getKnownObjectsCalls=1 getKnownObjectsHits=1 findObjectsCalls=1 findObjectsHits=1 findAllOfCalls=1 findAllOfHits=1 forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 staticConstructObjectCalls=1 staticConstructObjectHits=1
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-finish
"""

READY_LOG = READY_LOG.replace(
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=6",
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 forEachFunctionCalls=0 forEachFunctionCallbacks=0 isACalls=6",
)
READY_LOG = READY_LOG.replace(
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 isACalls=5",
    "forEachUObjectCalls=1 forEachUObjectCallbacks=4 forEachFunctionCalls=2 forEachFunctionCallbacks=2 isACalls=5",
)
READY_LOG = READY_LOG.replace(
    "event=ue-call-function-live-hook phase=thread status=installed target=0x140041000 selfTestTarget=false callSelfTest=false liveCalls=0 originalCalls=0 result=0 trampoline=0x1400c2000",
    "event=ue-call-function-live-hook phase=thread status=installed target=0x140041000 selfTestTarget=false targetSource=explicit targetName=CallFunctionByNameWithArguments callSelfTest=false liveCalls=1 originalCalls=1 result=0 luaDispatch=true luaPreCalls=1 luaPostCalls=1 luaPreHandled=1 luaPostHandled=1 trampoline=0x1400c2000",
)
READY_LOG = READY_LOG.replace(
    "event=ue-call-function-live-hook phase=thread status=installed target=0x140041000 selfTestTarget=false targetSource=explicit targetName=CallFunctionByNameWithArguments callSelfTest=false liveCalls=1 originalCalls=1 result=0 luaDispatch=true luaPreCalls=1 luaPostCalls=1 luaPreHandled=1 luaPostHandled=1 trampoline=0x1400c2000",
    (
        "event=ue-call-function-live-hook phase=thread status=installed target=0x140041000 selfTestTarget=false targetSource=explicit targetName=CallFunctionByNameWithArguments callSelfTest=false liveCalls=1 originalCalls=1 result=0 luaDispatch=true luaPreCalls=1 luaPostCalls=1 luaPreHandled=1 luaPostHandled=1 trampoline=0x1400c2000\n"
        "2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-call-function-active-validate phase=thread status=invoked object=0x140070000 command=0x140130000 commandSource=env-string output=0x0 executor=0x0 forceCall=true callSource=target-entry targetEntry=true result=84 liveCallsDelta=1 originalCallsDelta=1 luaDispatch=true"
    ),
)
READY_LOG = READY_LOG.replace(
    "event=ue-call-function-hook phase=thread status=passed target=0x140041000 installed=true restored=true selfTestTarget=false callSelfTest=false",
    "event=ue-call-function-hook phase=thread status=passed target=0x140041000 installed=true restored=true selfTestTarget=false targetSource=explicit targetName=CallFunctionByNameWithArguments callSelfTest=false",
)
READY_LOG = READY_LOG.replace(
    "event=ue-process-event-live-hook phase=thread status=installed target=0x140040000 selfTestTarget=false callSelfTest=false dispatchCallbacks=4 luaDispatch=true",
    "2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-active-validate phase=thread status=invoked object=0x140070000 function=0x140082000 params=0x20 paramsSource=descriptor-buffer paramsBufferSize=152 paramsDescriptorCount=17 callSource=target-entry targetEntry=true liveCallsDelta=1 originalCallsDelta=1 luaDispatch=true preCallbacks=2 postCallbacks=2\n2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-process-event-live-hook phase=thread status=installed target=0x140040000 selfTestTarget=false callSelfTest=false dispatchCallbacks=4 luaDispatch=true",
)
READY_LOG = READY_LOG.replace(
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
READY_LOG += (
    "2026-06-16T00:00:16Z pid=312 loader=win-client event=lua-process-event-params-buffer "
    "status=created function=0x2000 descriptorCount=17 size=152 address=0x3000\n"
    "2026-06-16T00:00:16Z pid=312 loader=win-client event=lua-process-event-native-invoke "
    "phase=smoke status=descriptor-preflight-ready objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=false nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=0 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:17Z pid=312 loader=win-client event=lua-process-event-native-invoke "
    "phase=smoke status=non-self-test-invoke-disabled objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=true nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=0 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:17Z pid=312 loader=win-client event=lua-process-event-native-invoke "
    "phase=smoke status=non-self-test-invoked objectRegistryAllowed=true "
    "functionDescriptorAllowed=true selfTestCallable=false descriptorBackedCallable=true "
    "invokeRequested=true nativeNonSelfTestEnabled=true nativeNonSelfTestInvoked=true "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 paramsWritten=1 object=0x1000 function=0x2000 value=74 "
    "originalResult=0 touched=1 liveCallsBefore=2 liveCallsAfter=3 "
    "originalCallsBefore=2 originalCallsAfter=3\n"
    "2026-06-16T00:00:18Z pid=312 loader=win-client event=lua-process-event-native-invoke-self-test "
    "phase=smoke status=passed processEventNativeCalls=3 processEventNativeHits=1 liveCalls=2 originalCalls=2\n"
    "2026-06-16T00:00:18Z pid=312 loader=win-client event=lua-process-event-native-executor-state "
    "status=prepared bridgeArmed=true objectAllowed=true functionAllowed=true "
    "objectRegistryAllowed=true functionDescriptorAllowed=true selfTestCallable=false "
    "descriptorBackedCallable=true nativeCallable=true nativeNonSelfTestEnabled=true "
    "paramsBufferConstructible=true descriptorCount=6 paramsDescriptorCount=17 "
    "paramsBufferSize=152 nativeExecutorBlockReason=none nativeInvoked=false "
    "object=0x1000 function=0x2000\n"
    "2026-06-16T00:00:19Z pid=312 loader=win-client event=lua-call-function-native-invoke "
    "phase=smoke status=preflight-ready objectRegistryAllowed=true selfTestCallable=false "
    "invokeRequested=false nativeNonSelfTestEnabled=false nativeNonSelfTestInvoked=false "
    "object=0x1000 function=DoubleProbeValue args= forceCall=true result=0 "
    "liveCallsBefore=2 liveCallsAfter=2 originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:20Z pid=312 loader=win-client event=lua-call-function-native-invoke "
    "phase=smoke status=non-self-test-invoke-disabled objectRegistryAllowed=true "
    "selfTestCallable=false invokeRequested=true nativeNonSelfTestEnabled=false "
    "nativeNonSelfTestInvoked=false object=0x1000 function=DoubleProbeValue args= "
    "forceCall=true result=0 liveCallsBefore=2 liveCallsAfter=2 "
    "originalCallsBefore=2 originalCallsAfter=2\n"
    "2026-06-16T00:00:20Z pid=312 loader=win-client event=lua-call-function-native-invoke "
    "phase=smoke status=non-self-test-invoked objectRegistryAllowed=true "
    "selfTestCallable=false invokeRequested=true nativeNonSelfTestEnabled=true "
    "nativeNonSelfTestInvoked=true object=0x1000 function=DoubleProbeValue args= "
    "forceCall=true result=42 liveCallsBefore=2 liveCallsAfter=3 "
    "originalCallsBefore=2 originalCallsAfter=3\n"
    "2026-06-16T00:00:21Z pid=312 loader=win-client event=lua-call-function-native-invoke-self-test "
    "phase=smoke status=passed callFunctionNativeCalls=3 callFunctionNativeHits=1 liveCalls=2 originalCalls=3\n"
    "2026-06-16T00:00:21Z pid=312 loader=win-client event=lua-call-function-native-executor-state "
    "status=prepared bridgeArmed=true objectAllowed=true functionAllowed=true "
    "objectRegistryAllowed=true selfTestCallable=false nativeCallable=true "
    "nativeNonSelfTestEnabled=true object=0x1000 function=DoubleProbeValue args= "
    "forceCall=true nativeExecutorBlockReason=none nativeInvoked=false\n"
)
READY_LOG = READY_LOG.replace(
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


def ready_anchor_coverage():
    return {
        "readyForObjectDiscovery": True,
        "readyForHookPlanning": True,
        "readyForPackageLoading": True,
        "explicitAnchors": [],
        "signatureAnchors": [
            "FNamePool",
            "GUObjectArray",
            "GWorld",
            "ProcessEvent",
            "StaticLoadObject",
            "UObject",
            "UFunction",
        ],
        "combinedAnchors": [
            "FNamePool",
            "GUObjectArray",
            "GWorld",
            "ProcessEvent",
            "StaticLoadObject",
            "UObject",
            "UFunction",
        ],
        "missingRequiredGroups": [],
        "groups": {
            "names": {"present": 1, "total": 1},
            "objects": {"present": 1, "total": 1},
            "world": {"present": 1, "total": 1},
            "dispatch": {"present": 1, "total": 1},
            "package": {"present": 1, "total": 1},
            "reflection": {"present": 2, "total": 2},
        },
    }


def load_asset_package_guard_evidence(loader="win-client", platform_abi="win64-ms-abi", executor_ready=False):
    ready = "true" if executor_ready else "false"
    block_reason = "none" if executor_ready else "invoke-disabled"
    evidence = (
        f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-crash-guard-state "
        f"status=available platformAbi={platform_abi} mechanism=test available=true enabled=false armed=false nativeInvoked=false\n"
        f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-guarded-call-state "
        f"status=passed platformAbi={platform_abi} mechanism=test guardedCallAvailable=true "
        "guardedCallExecuted=true guardedCallSucceeded=true guardedCallResult=17 crashCaptured=false signal=0 nativeInvoked=false\n"
        f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-return-validation-state "
        "status=passed path=/Script/DuneProbe.SelfTestObject address=0x140070000 candidateAddress=0x140070000 "
        "expectedClass=UObjectCandidate registryHit=true mapped=true readable=true classMatch=true "
        "returnValidationReady=true nativeInvoked=false\n"
        f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-native-call-adapter-state "
        f"status=prepared path=/Script/DuneProbe.SelfTestObject targetName=StaticLoadObject target=0x140048000 "
        f"platformAbi={platform_abi} adapterKind={platform_abi}-package-load signatureFamily=StaticLoadObject "
        "argumentCount=7 pathStaged=true boundedInput=true functionPointerReady=true abiVerified=true "
        "tcharLayoutVerified=true callFrameReady=true invokeEnabled=false nativeBridgeArmed=false "
        "adapterReady=true finalInvokeConfirmed=false crashGuardRequired=true crashGuardArmed=false "
        "guardedCallRequired=true guardedCallReady=true guardedCallResult=17 returnValidationReady=true "
        "invocationDescriptorRequired=true invocationDescriptorConsumed=true nativeCallPlanAccepted=true "
        "nativeCallExecutionMode=guarded-native-package-load "
        "nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallable=false nativeInvoked=false\n"
        f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-invocation-descriptor-state "
        "status=derived descriptorKind=guarded-package-native-call descriptorProvenance=adapter-state-derived "
        "nativeCallPlanConstructed=true nativeCallExecutionMode=guarded-native-package-load "
        "nativeCallTargetField=TargetAddress nativeCallPathField=Path "
        "nativeCallGuardPolicy=crash-guard+guarded-call+return-validation "
        "nativeCallReturnValidator=uobject-registry-memory-class nativeInvoked=false\n"
        f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-native-executor-state "
        "status=prepared executorKind=guarded-package-native-executor nativeExecutorConstructed=true "
        "targetName=StaticLoadObject target=0x140048000 targetImage=true signatureFamily=StaticLoadObject "
        f"nativeExecutorDryRun=true nativeExecutorReady={ready} executorPreflightPassed={ready} "
        f"finalNativeCallEligible={ready} nativeExecutorBlockReason={block_reason} "
        "finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only nativeInvoked=false\n"
    )
    if executor_ready:
        evidence += (
            f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-asset-package-native-invoke "
            "status=native-return-validated path=/Script/DuneProbe.SelfTestObject targetName=StaticLoadObject "
            "target=0x140048000 targetImage=true invokeRequested=true invokeEnabled=true pathStaged=true "
            "boundedInput=true abiEvidenceProvided=true abiVerificationEnabled=true abiVerified=true "
            "tcharLayoutVerified=true callFrameReady=true nativeBridgeArmed=true finalInvokeConfirmed=true "
            "crashGuardRequired=true crashGuardArmed=true guardedCallRequired=true guardedCallReady=true "
            "guardedCallResult=17 returnValidationReady=true invocationDescriptorRequired=true "
            "invocationDescriptorConsumed=true nativeCallPlanAccepted=true "
            "nativeCallExecutionMode=guarded-native-package-load "
            "nativeCallGuardPolicy=crash-guard+guarded-call+return-validation "
            "nativeCallable=true nativeInvoked=true nativeReturn=0x140088000 nativeSignal=0 "
            "nativeReturnNonNull=true nativeReturnMapped=true nativeReturnReadable=true "
            "nativeReturnValidated=true packageAvailable=true\n"
            f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-class-package-abi-state "
            f"status=target-ready targetName=StaticLoadClass target=0x140049000 targetImage=true "
            f"platformAbi={platform_abi} signatureFamily=StaticLoadClass abiVerified=true "
            "callFrameReady=false stringBridgeReady=false classRootReady=true packageAvailable=true\n"
            f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-class-package-call-frame-verification-state "
            "status=target-ready path=/Script/DuneProbe.SelfTestObject targetName=StaticLoadClass "
            f"target=0x140049000 targetImage=true platformAbi={platform_abi} "
            "signatureFamily=StaticLoadClass argumentCount=7 boundedInput=true "
            "abiVerified=true classRootReady=true callFrameReady=true nativeInvoked=false\n"
            f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-class-package-native-executor-state "
            "status=prepared targetName=StaticLoadClass target=0x140049000 targetImage=true "
            f"platformAbi={platform_abi} nativeExecutorReady=true executorPreflightPassed=true "
            "finalNativeCallEligible=true nativeExecutorBlockReason=none nativeInvoked=false\n"
            f"2026-06-16T17:43:39Z pid=312 loader={loader} event=lua-load-class-package-native-invoke "
            "status=native-invoked path=/Script/DuneProbe.SelfTestObject targetName=StaticLoadClass "
            "target=0x140049000 targetImage=true "
            f"platformAbi={platform_abi} invokeRequested=true invokeEnabled=true abiVerified=true "
            "classRootReady=true callFrameReady=true nativeCallable=true nativeInvoked=true "
            "nativeCallPlanAccepted=true\n"
            f"2026-06-16T17:43:39Z pid=312 loader={loader} "
            "event=lua-static-construct-object-native-executor-state status=prepared "
            "executorKind=guarded-static-construct-object-native-executor targetName=StaticConstructObject "
            f"target=0x140049000 targetImage=true platformAbi={platform_abi} class=0x140070000 outer=0x140071000 "
            "name=NativeConstructPreflightProbe className=UObjectCandidate invokeRequested=false "
            "invokeEnabled=true abiEvidenceProvided=true abiVerified=true callFrameReady=true "
            "finalInvokeConfirmed=true nativeCallable=true nativeInvoked=false\n"
            f"2026-06-16T17:43:39Z pid=312 loader={loader} "
            "event=lua-static-construct-object-native-invoke status=native-invoked "
            "executorKind=guarded-static-construct-object-native-executor targetName=StaticConstructObject "
            f"target=0x140049000 targetImage=true platformAbi={platform_abi} class=0x140070000 outer=0x140071000 "
            "name=NativeConstructPreflightProbe className=UObjectCandidate invokeRequested=true "
            "invokeEnabled=true abiEvidenceProvided=true abiVerified=true callFrameReady=true "
            "finalInvokeConfirmed=true nativeCallable=true nativeInvoked=true\n"
        )
    return evidence


class Ue4ssPortReadinessTests(unittest.TestCase):
    def test_blocks_without_core_ue_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "partial.log"
            log.write_text(PARTIAL_LOG, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        self.assertFalse(report["ready"]["objectDiscovery"])
        self.assertFalse(report["ready"]["objectDiscoveryCoverage"])
        self.assertFalse(report["ready"]["findObjectSemantics"])
        self.assertFalse(report["ready"]["ueObjectArrayShape"])
        self.assertIn("pointerProbe", report["objectDiscoveryCoverage"]["missingObjectDiscoveryComponents"])
        self.assertIn("nativeIdentities", report["objectDiscoveryCoverage"]["missingFindObjectComponents"])
        self.assertFalse(report["ready"]["pointerProbe"])
        self.assertFalse(report["ready"]["layoutProbe"])
        self.assertFalse(report["ready"]["uobjectProbe"])
        self.assertFalse(report["ready"]["hookDispatch"])
        self.assertFalse(report["ready"]["modDispatch"])
        self.assertFalse(report["ready"]["luaRuntime"])
        self.assertFalse(report["ready"]["luaSchedulerApiMods"])
        self.assertFalse(report["ready"]["luaInputCommandApiMods"])
        self.assertFalse(report["ready"]["luaObjectApi"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertFalse(report["ready"]["luaLoadAssetPackagePreflight"])
        self.assertFalse(report["ready"]["packageLoadingSurface"])
        self.assertFalse(report["ready"]["luaFunctionIteration"])
        self.assertFalse(report["ready"]["luaFunctionIterationRuntime"])
        self.assertFalse(report["ready"]["luaProcessConsoleExecHooks"])
        self.assertFalse(report["ready"]["luaLocalPlayerExecHooks"])
        self.assertFalse(report["ready"]["luaCallFunctionHooks"])
        self.assertFalse(report["ready"]["luaCallFunctionStructuredArgs"])
        self.assertFalse(report["ready"]["luaCallFunctionNativeInvoke"])
        self.assertFalse(report["ready"]["luaCallFunctionNativeInvokePreflight"])
        self.assertFalse(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaProcessEventCompat"])
        self.assertFalse(report["ready"]["luaProcessEventBridgeState"])
        self.assertFalse(report["ready"]["luaProcessEventNativeInvoke"])
        self.assertFalse(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaLifecycleHooks"])
        self.assertFalse(report["ready"]["luaCustomEventHooks"])
        self.assertFalse(report["ready"]["luaLoadMapHooks"])
        self.assertFalse(report["ready"]["luaBeginPlayHooks"])
        self.assertFalse(report["ready"]["luaInitGameStateHooks"])
        self.assertFalse(report["ready"]["luaObjectNotify"])
        self.assertFalse(report["ready"]["luaSyntheticOuter"])
        self.assertFalse(report["ready"]["luaWorldContext"])
        self.assertFalse(report["ready"]["luaClassDefaultObject"])
        self.assertFalse(report["ready"]["luaLevel"])
        self.assertFalse(report["ready"]["luaReflection"])
        self.assertFalse(report["ready"]["luaReflectionRawSet"])
        self.assertFalse(report["ready"]["luaReflectionNamedProperty"])
        self.assertFalse(report["ready"]["luaReflectionNumericPropertyValues"])
        self.assertFalse(report["ready"]["luaReflectionNameTextPropertyValues"])
        self.assertFalse(report["ready"]["luaReflectionArrayInnerProperty"])
        self.assertFalse(report["ready"]["luaReflectionEnumProperty"])
        self.assertFalse(report["ready"]["luaReflectionContainerProperties"])
        self.assertFalse(report["ready"]["luaReflectionImportText"])
        self.assertFalse(report["ready"]["luaReflectionExportText"])
        self.assertFalse(report["ready"]["luaReflectionPropertyMetadata"])
        self.assertFalse(report["ready"]["luaReflectionDescriptorValues"])
        self.assertFalse(report["ready"]["luaReflectionForEachProperty"])
        self.assertFalse(report["ready"]["luaReflectionForEachPropertyRuntime"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorTypedClassRuntime"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorTypedValuesRuntime"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorTypedSetValuesRuntime"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorValues"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertFalse(report["ready"]["luaProcessEvent"])
        self.assertFalse(report["ready"]["ueProcessEventHookProbe"])
        self.assertFalse(report["ready"]["ueCallFunctionHookProbe"])
        self.assertFalse(report["ready"]["ueCallFunctionLiveHook"])
        self.assertFalse(report["ready"]["ueProcessEventLiveHook"])
        self.assertFalse(report["ready"]["ueProcessEventDispatch"])
        self.assertFalse(report["ready"]["ueProcessEventLiveLuaDispatch"])
        self.assertFalse(report["ready"]["ueProcessEventLiveRegistryContext"])
        self.assertFalse(report["ready"]["ueProcessEventLiveParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveRawParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveArrayContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveSetContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveMapContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveSetMapContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveContainerDataSamples"])
        self.assertFalse(report["ready"]["ueProcessEventLuaContextHandles"])
        self.assertFalse(report["ready"]["ueProcessEventLuaParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLiveClassAwareParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventFunctionParamMethod"])
        self.assertFalse(report["ready"]["ueProcessEventFunctionParamLookupMethod"])
        self.assertFalse(report["ready"]["ueProcessEventFunctionParamIterationMethod"])
        self.assertFalse(report["ready"]["ueProcessEventContainerAliasMethods"])
        self.assertFalse(report["ready"]["ueProcessEventContainerStorageLayoutMethods"])
        self.assertFalse(report["ready"]["ueProcessEventLuaScalarParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLuaNameStringParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLuaStructParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLuaEnumParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLuaObjectParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLuaBoolParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLuaHookRouting"])
        self.assertFalse(report["ready"]["luaMods"])
        self.assertFalse(report["ready"]["luaObjectRegistry"])
        self.assertFalse(report["ready"]["luaObjectRegistryChecks"])
        self.assertFalse(report["ready"]["luaDecodedObjectAliases"])
        self.assertFalse(report["ready"]["ueObjectArrayRegistry"])
        self.assertFalse(report["ready"]["ueObjectNativeIdentities"])
        self.assertFalse(report["ready"]["ueObjectInternalFlags"])
        self.assertFalse(report["ready"]["ueFNameDecoder"])
        self.assertFalse(report["ready"]["ueReflectionProbe"])
        self.assertFalse(report["ready"]["ueReflectionFieldWalk"])
        self.assertFalse(report["ready"]["ueReflectionPropertyDescriptors"])
        self.assertFalse(report["ready"]["ueFunctionParamDescriptors"])
        self.assertFalse(report["ready"]["ueFunctionParamContainerChildren"])
        self.assertFalse(report["ready"]["ueFunctionIdentities"])
        self.assertFalse(report["ready"]["ueFunctionNativeIdentities"])
        self.assertFalse(report["ready"]["ueFunctionFlags"])
        self.assertFalse(report["ready"]["ueReflectionPropertyValues"])
        self.assertFalse(report["ready"]["hooks"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertFalse(next(gate for gate in report["gates"] if gate["name"] == "ue-objects")["passed"])

    def test_resolved_anchor_signatures_satisfy_core_anchor_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "signature-anchors.log"
            log.write_text(SIGNATURE_ANCHOR_LOG, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        self.assertTrue(next(gate for gate in report["gates"] if gate["name"] == "ue-names")["passed"])
        self.assertTrue(next(gate for gate in report["gates"] if gate["name"] == "ue-objects")["passed"])
        self.assertTrue(next(gate for gate in report["gates"] if gate["name"] == "ue-world")["passed"])
        self.assertTrue(next(gate for gate in report["gates"] if gate["name"] == "ue-dispatch")["passed"])
        self.assertTrue(next(gate for gate in report["gates"] if gate["name"] == "ue-reflection-surface")["passed"])
        self.assertFalse(report["ready"]["objectDiscovery"])
        self.assertFalse(report["ready"]["pointerProbe"])

    def test_raw_scan_hits_do_not_satisfy_core_anchor_gates(self):
        scan_only = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-start strings=4 signatures=0 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=FNamePool addr=0x140010000 rva=0x10000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=GUObjectArray addr=0x140020000 rva=0x20000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=GWorld addr=0x140030000 rva=0x30000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=string name=ProcessEvent addr=0x140040000 rva=0x40000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-finish
"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "scan-only.log"
            log.write_text(scan_only, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        self.assertFalse(next(gate for gate in report["gates"] if gate["name"] == "ue-names")["passed"])
        self.assertFalse(next(gate for gate in report["gates"] if gate["name"] == "ue-objects")["passed"])
        self.assertFalse(next(gate for gate in report["gates"] if gate["name"] == "ue-world")["passed"])
        self.assertFalse(next(gate for gate in report["gates"] if gate["name"] == "ue-dispatch")["passed"])
        self.assertFalse(report["ready"]["objectDiscovery"])

    def test_array_container_sample_does_not_satisfy_set_map_container_gates(self):
        array_only = "\n".join(
            line
            for line in READY_LOG.splitlines()
            if "param=DecodedSet_0" not in line and "param=DecodedMap_0" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "array-only.log"
            log.write_text(array_only, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        self.assertTrue(report["ready"]["ueProcessEventLiveContainerParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveArrayContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveSetContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveMapContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveSetMapContainerParamValues"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("TSet/FScriptSet", report["nextSteps"][0])

    def test_lua_dispatch_requires_each_lifecycle_hook_family(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_load_map = READY_LOG.replace("loadMapPreHooks=1", "loadMapPreHooks=0", 1)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-load-map.log"
            log.write_text(missing_load_map, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertFalse(report["ready"]["luaLifecycleHooks"])
        self.assertTrue(report["ready"]["luaCustomEventHooks"])
        self.assertFalse(report["ready"]["luaLoadMapHooks"])
        self.assertTrue(report["ready"]["luaBeginPlayHooks"])
        self.assertTrue(report["ready"]["luaInitGameStateHooks"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("lifecycle pre/post hooks", report["nextSteps"][0])

    def test_lua_dispatch_requires_process_event_compat_mod_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_process_event_compat = READY_LOG.replace("processEventCompatHits=2", "processEventCompatHits=0", 1)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-process-event-compat.log"
            log.write_text(missing_process_event_compat, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertFalse(report["ready"]["luaProcessEventCompat"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("ProcessEvent compatibility", report["nextSteps"][0])

    def test_lua_dispatch_requires_process_event_bridge_state_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_process_event_bridge_state = READY_LOG.replace("processEventBridgeStateCalls=1", "processEventBridgeStateCalls=0", 1)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-process-event-bridge-state.log"
            log.write_text(missing_process_event_bridge_state, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["luaProcessEventCompat"])
        self.assertFalse(report["ready"]["luaProcessEventBridgeState"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("ProcessEventBridgeState", report["nextSteps"][0])

    def test_lua_dispatch_requires_process_event_native_invoke_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_process_event_native_invoke = READY_LOG.replace(
            "event=lua-process-event-native-invoke-self-test "
            "phase=smoke status=passed processEventNativeCalls=3 processEventNativeHits=1",
            "event=lua-process-event-native-invoke-self-test "
            "phase=smoke status=failed processEventNativeCalls=3 processEventNativeHits=0",
            1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-process-event-native-invoke.log"
            log.write_text(missing_process_event_native_invoke, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["luaProcessEventCompat"])
        self.assertTrue(report["ready"]["luaProcessEventBridgeState"])
        self.assertFalse(report["ready"]["luaProcessEventNativeInvoke"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeDescriptorPreflight"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvoke"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokePreflight"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestGate"])
        self.assertTrue(report["ready"]["luaProcessEventParamsBuffer"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("native ProcessEvent", report["nextSteps"][0])

    def test_lua_dispatch_requires_process_event_non_self_test_invoked_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_non_self_test_invoked = "\n".join(
            line for line in READY_LOG.splitlines()
            if "event=lua-process-event-native-invoke " not in line
            or "status=non-self-test-invoked" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-process-event-non-self-test-invoked.log"
            log.write_text(missing_non_self_test_invoked, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "lua-process-event-native-invoke-non-self-test-invoked"
        )
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeDescriptorPreflight"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaProcessEventNativeInvokeNonSelfTestInvoked"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("non-self-test ProcessEvent", gate["blocker"])

    def test_process_event_non_self_test_invoked_satisfies_gate_without_disabled_row(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        invoked_only = "\n".join(
            line for line in READY_LOG.splitlines()
            if "event=lua-process-event-native-invoke " not in line
            or "status=non-self-test-invoke-disabled" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "process-event-invoked-only.log"
            log.write_text(invoked_only, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "lua-process-event-native-invoke-non-self-test-gate"
        )
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestInvoked"])
        self.assertIn("closedGates=0", gate["evidence"])
        self.assertIn("invoked=1", gate["evidence"])

    def test_lua_dispatch_requires_process_event_descriptor_preflight_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_descriptor_preflight = "\n".join(
            line for line in READY_LOG.splitlines()
            if "status=descriptor-preflight-ready" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-process-event-descriptor-preflight.log"
            log.write_text(missing_descriptor_preflight, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "lua-process-event-native-invoke-descriptor-preflight"
        )
        self.assertTrue(report["ready"]["luaProcessEventNativeInvoke"])
        self.assertFalse(report["ready"]["luaProcessEventNativeInvokeDescriptorPreflight"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("descriptor-preflight-ready", gate["blocker"])

    def test_lua_dispatch_requires_call_function_native_invoke_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_call_function_native_invoke = READY_LOG.replace(
            "event=lua-call-function-native-invoke-self-test "
            "phase=smoke status=passed callFunctionNativeCalls=3 callFunctionNativeHits=1",
            "event=lua-call-function-native-invoke-self-test "
            "phase=smoke status=failed callFunctionNativeCalls=3 callFunctionNativeHits=0",
            1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-call-function-native-invoke.log"
            log.write_text(missing_call_function_native_invoke, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "lua-call-function-native-invoke"
        )
        self.assertFalse(report["ready"]["luaCallFunctionNativeInvoke"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokePreflight"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("native CallFunction", gate["blocker"])

    def test_lua_dispatch_requires_call_function_non_self_test_invoked_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_non_self_test_invoked = "\n".join(
            line for line in READY_LOG.splitlines()
            if "event=lua-call-function-native-invoke " not in line
            or "status=non-self-test-invoked" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-call-function-non-self-test-invoked.log"
            log.write_text(missing_non_self_test_invoked, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "lua-call-function-native-invoke-non-self-test-invoked"
        )
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokePreflight"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestInvoked"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("non-self-test CallFunction", gate["blocker"])

    def test_call_function_non_self_test_invoked_satisfies_gate_without_disabled_row(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        invoked_only = "\n".join(
            line for line in READY_LOG.splitlines()
            if "event=lua-call-function-native-invoke " not in line
            or "status=non-self-test-invoke-disabled" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "call-function-invoked-only.log"
            log.write_text(invoked_only, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "lua-call-function-native-invoke-non-self-test-gate"
        )
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestGate"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestInvoked"])
        self.assertIn("closedGates=0", gate["evidence"])
        self.assertIn("invoked=1", gate["evidence"])

    def test_lua_dispatch_requires_process_event_params_buffer_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        missing_params_buffer = "\n".join(
            line for line in READY_LOG.splitlines()
            if "event=lua-process-event-params-buffer" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-process-event-params-buffer.log"
            log.write_text(missing_params_buffer, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(item for item in report["gates"] if item["name"] == "lua-process-event-params-buffer")
        self.assertTrue(report["ready"]["luaProcessEventNativeInvoke"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertFalse(report["ready"]["luaProcessEventParamsBuffer"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("descriptor-backed ProcessEvent params buffer", gate["blocker"])

    def test_opens_all_readiness_gates_with_core_anchors_and_promotable_signatures(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready.log"
            log.write_text(READY_LOG, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["objectDiscovery"])
        self.assertTrue(report["ready"]["objectDiscoveryCoverage"])
        self.assertTrue(report["ready"]["findObjectSemantics"])
        self.assertGreater(report["objectDiscoveryCoverage"]["components"]["objectRegistry"]["evidence"]["checks"], 0)
        self.assertEqual(report["objectDiscoveryCoverage"]["missingObjectDiscoveryComponents"], [])
        self.assertEqual(report["objectDiscoveryCoverage"]["missingFindObjectComponents"], [])
        self.assertTrue(report["ready"]["pointerProbe"])
        self.assertTrue(report["ready"]["layoutProbe"])
        self.assertTrue(report["ready"]["uobjectProbe"])
        self.assertTrue(report["ready"]["ueReflectionProbe"])
        self.assertTrue(report["ready"]["ueReflectionFieldWalk"])
        self.assertTrue(report["ready"]["ueReflectionPropertyDescriptors"])
        self.assertTrue(report["ready"]["ueReflectionPropertyDescriptorsRuntime"])
        self.assertTrue(report["ready"]["ueFunctionParamDescriptors"])
        self.assertTrue(report["ready"]["ueFunctionParamContainerChildren"])
        self.assertTrue(report["ready"]["ueFunctionIdentities"])
        self.assertTrue(report["ready"]["ueFunctionNativeIdentities"])
        self.assertTrue(report["ready"]["ueFunctionFlags"])
        self.assertTrue(report["ready"]["ueReflectionPropertyValues"])
        self.assertTrue(report["ready"]["ueReflectionPropertyValuesRuntime"])
        self.assertTrue(report["ready"]["hookDispatch"])
        self.assertTrue(report["ready"]["modDispatch"])
        self.assertTrue(report["ready"]["luaRuntime"])
        self.assertTrue(report["ready"]["luaSchedulerApi"])
        self.assertTrue(report["ready"]["luaSchedulerApiMods"])
        self.assertTrue(report["ready"]["luaInputCommandApi"])
        self.assertTrue(report["ready"]["luaInputCommandApiMods"])
        self.assertTrue(report["ready"]["luaObjectApi"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertTrue(report["ready"]["packageLoadingSurface"])
        self.assertTrue(report["ready"]["targetPackageLoadingSurface"])
        self.assertTrue(report["ready"]["luaFunctionIteration"])
        self.assertTrue(report["ready"]["luaFunctionIterationRuntime"])
        self.assertTrue(report["ready"]["luaProcessConsoleExecHooks"])
        self.assertTrue(report["ready"]["luaLocalPlayerExecHooks"])
        self.assertTrue(report["ready"]["luaCallFunctionHooks"])
        self.assertTrue(report["ready"]["luaCallFunctionStructuredArgs"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvoke"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokePreflight"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeExecutorState"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestGate"])
        self.assertTrue(report["ready"]["luaCallFunctionNativeInvokeNonSelfTestInvoked"])
        self.assertTrue(report["ready"]["luaProcessEventCompat"])
        self.assertTrue(report["ready"]["luaProcessEventBridgeState"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvoke"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeDescriptorPreflight"])
        self.assertTrue(report["ready"]["luaProcessEventNativeExecutorState"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestGate"])
        self.assertTrue(report["ready"]["luaProcessEventNativeInvokeNonSelfTestInvoked"])
        self.assertTrue(report["ready"]["luaProcessEventParamsBuffer"])
        self.assertTrue(report["ready"]["luaLifecycleHooks"])
        self.assertTrue(report["ready"]["luaCustomEventHooks"])
        self.assertTrue(report["ready"]["luaLoadMapHooks"])
        self.assertTrue(report["ready"]["luaBeginPlayHooks"])
        self.assertTrue(report["ready"]["luaInitGameStateHooks"])
        self.assertTrue(report["ready"]["luaObjectNotify"])
        self.assertTrue(report["ready"]["luaSyntheticOuter"])
        self.assertTrue(report["ready"]["luaObjectOuterChains"])
        self.assertTrue(report["ready"]["luaObjectOuterChainIdentities"])
        self.assertTrue(report["ready"]["luaWorldContext"])
        self.assertTrue(report["ready"]["luaGlobalRuntimeHelpers"])
        self.assertTrue(report["ready"]["luaClassDefaultObject"])
        self.assertTrue(report["ready"]["luaLevel"])
        self.assertTrue(report["ready"]["luaReflection"])
        self.assertTrue(report["ready"]["luaReflectionRawSet"])
        self.assertTrue(report["ready"]["luaReflectionNamedProperty"])
        self.assertTrue(report["ready"]["luaReflectionNumericPropertyValues"])
        self.assertTrue(report["ready"]["luaReflectionNameTextPropertyValues"])
        self.assertTrue(report["ready"]["luaReflectionArrayInnerProperty"])
        self.assertTrue(report["ready"]["luaReflectionEnumProperty"])
        self.assertTrue(report["ready"]["luaReflectionContainerProperties"])
        self.assertTrue(report["ready"]["luaReflectionImportText"])
        self.assertTrue(report["ready"]["luaReflectionExportText"])
        self.assertTrue(report["ready"]["luaReflectionPropertyMetadata"])
        self.assertTrue(report["ready"]["luaReflectionDescriptorValues"])
        self.assertTrue(report["ready"]["luaReflectionForEachProperty"])
        self.assertTrue(report["ready"]["luaReflectionForEachPropertyRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorTypedClassRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorTypedValuesRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorTypedSetValuesRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorValues"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertTrue(report["ready"]["luaProcessEvent"])
        self.assertTrue(report["ready"]["ueProcessEventHookProbe"])
        self.assertTrue(report["ready"]["ueProcessEventHookRuntimeTarget"])
        self.assertTrue(report["ready"]["ueCallFunctionHookProbe"])
        self.assertTrue(report["ready"]["ueCallFunctionHookRuntimeTarget"])
        self.assertTrue(report["ready"]["ueCallFunctionLiveHook"])
        self.assertTrue(report["ready"]["ueCallFunctionLiveHookRuntimeTarget"])
        self.assertTrue(report["ready"]["ueCallFunctionActiveValidation"])
        self.assertTrue(report["ready"]["ueCallFunctionLiveLuaDispatch"])
        self.assertEqual(summary["scan"]["invokedUeCallFunctionActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["originalUeCallFunctionActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["targetEntryUeCallFunctionActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["provenTargetRoutedUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(summary["scan"]["provenTargetHandledUeCallFunctionLiveLuaHookCount"], 1)
        self.assertTrue(report["ready"]["ueProcessEventLiveHook"])
        self.assertTrue(report["ready"]["ueProcessEventLiveHookRuntimeTarget"])
        self.assertTrue(report["ready"]["ueProcessEventActiveValidation"])
        self.assertTrue(report["ready"]["ueProcessEventDispatch"])
        self.assertEqual(summary["scan"]["invokedUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["originalUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["targetEntryUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["syntheticTargetEntryUeProcessEventActiveValidationCount"], 0)
        self.assertEqual(summary["scan"]["descriptorBufferUeProcessEventActiveValidationCount"], 1)
        self.assertFalse(report["ready"]["ueProcessEventSyntheticTargetEntry"])
        self.assertTrue(report["ready"]["ueProcessEventLiveLuaDispatch"])
        self.assertTrue(report["ready"]["ueProcessEventLiveContext"])
        self.assertTrue(report["ready"]["ueProcessEventLiveFunctionPath"])
        self.assertTrue(report["ready"]["ueProcessEventLiveRuntimeContext"])
        self.assertTrue(report["ready"]["ueProcessEventLiveRegistryContext"])
        self.assertTrue(report["ready"]["ueProcessEventLiveRuntimeRegistryContext"])
        self.assertTrue(report["ready"]["ueProcessEventLiveParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveRawParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveContainerParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveArrayContainerParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveSetContainerParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveMapContainerParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveSetMapContainerParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventLiveContainerDataSamples"])
        self.assertTrue(report["ready"]["ueProcessEventLuaContextHandles"])
        self.assertTrue(report["ready"]["ueProcessEventLuaParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLiveClassAwareParamValues"])
        self.assertTrue(report["ready"]["ueProcessEventFunctionParamMethod"])
        self.assertTrue(report["ready"]["ueProcessEventFunctionParamLookupMethod"])
        self.assertTrue(report["ready"]["ueProcessEventFunctionParamIterationMethod"])
        self.assertTrue(report["ready"]["ueProcessEventContainerAliasMethods"])
        self.assertTrue(report["ready"]["ueProcessEventContainerStorageLayoutMethods"])
        self.assertTrue(report["ready"]["ueProcessEventLuaScalarParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLuaNameStringParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLuaStructParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLuaEnumParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLuaObjectParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLuaBoolParamAccessors"])
        self.assertTrue(report["ready"]["ueProcessEventLuaHookRouting"])
        self.assertTrue(report["ready"]["ueProcessEventLuaHookAliasRouting"])
        self.assertTrue(report["ready"]["luaMods"])
        self.assertTrue(report["ready"]["luaObjectRegistry"])
        self.assertTrue(report["ready"]["luaObjectRegistryChecks"])
        self.assertTrue(report["ready"]["luaObjectRegistryRuntime"])
        self.assertTrue(report["ready"]["luaFunctionRegistryChecks"])
        self.assertTrue(report["ready"]["luaFunctionRegistryRuntime"])
        self.assertTrue(report["ready"]["luaDecodedObjectAliases"])
        self.assertTrue(report["ready"]["luaDecodedObjectAliasesRuntime"])
        self.assertTrue(report["ready"]["ueObjectArrayRegistry"])
        self.assertTrue(report["ready"]["ueObjectArrayShape"])
        self.assertTrue(report["ready"]["ueObjectArrayRegistryRuntime"])
        self.assertTrue(report["ready"]["ueObjectNativeIdentities"])
        self.assertTrue(report["ready"]["ueObjectInternalFlags"])
        self.assertTrue(report["ready"]["ueFNameDecoder"])
        self.assertTrue(report["ready"]["anchorGroupProvenance"])
        self.assertEqual(
            report["anchorGroups"]["signatures"],
            {"dispatch": 1, "names": 1, "objects": 1, "package": 1, "reflection": 2, "world": 1},
        )
        self.assertTrue(report["ready"]["hooks"])
        self.assertTrue(report["ready"]["reflection"])
        self.assertTrue(report["ready"]["luaDispatch"])
        self.assertFalse(report["ready"]["luaLoadAssetBackendState"])
        self.assertFalse(report["ready"]["luaLoadAssetBackendAnchors"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertFalse(report["ready"]["luaLoadAssetPackagePreflight"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertIn("guarded LoadAsset package bridge state", " ".join(report["nextSteps"]))
        self.assertIn("/RuntimeProbe/GWorld.DecodedFunction_0:Function", report["canaryHints"]["ueFunctionPaths"])
        self.assertIn("/Script/GWorld.DecodedFunction_0:Function", report["canaryHints"]["ue4ssFunctionPaths"])
        self.assertIn(
            {
                "objectAddress": "0x140070000",
                "functionAddress": "0x140082000",
                "functionPath": "/RuntimeProbe/GWorld.DecodedFunction_0:Function",
                "objectPath": "/RuntimeProbe/GWorld",
                "functionProvenance": "runtime",
                "callFunctionCommand": "DecodedFunction_0",
                "paramsAddress": "0x20",
            },
            report["canaryHints"]["activeValidationCandidates"],
        )
        self.assertIn(
            "- Ready target-image package loading surface: `true`",
            readiness.markdown(report),
        )

    def test_active_validation_requires_target_entry_proof(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        direct_replacement_log = READY_LOG.replace(
            "callSource=target-entry targetEntry=true",
            "callSource=replacement-direct targetEntry=false",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "direct-active-validation.log"
            log.write_text(direct_replacement_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertEqual(summary["scan"]["invokedUeCallFunctionActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["originalUeCallFunctionActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["targetEntryUeCallFunctionActiveValidationCount"], 0)
        self.assertFalse(report["ready"]["ueCallFunctionActiveValidation"])
        self.assertEqual(summary["scan"]["invokedUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["originalUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["targetEntryUeProcessEventActiveValidationCount"], 0)
        self.assertFalse(report["ready"]["ueProcessEventActiveValidation"])

    def test_suppressed_process_event_target_entry_is_tracked_without_full_validation(self):
        synthetic_log = READY_LOG.replace(
            "event=ue-process-event-active-validate phase=thread status=invoked object=0x140070000 function=0x140082000 params=0x20 paramsSource=descriptor-buffer paramsBufferSize=152 paramsDescriptorCount=17 callSource=target-entry targetEntry=true liveCallsDelta=1 originalCallsDelta=1 luaDispatch=true preCallbacks=2 postCallbacks=2",
            "event=ue-process-event-active-validate phase=thread status=invoked object=0x140070000 function=0x140082000 params=0x0 objectSource=synthetic-runtime-object functionSource=synthetic-runtime-function paramsSource=none paramsBufferSize=0 paramsDescriptorCount=0 callSource=target-entry targetEntry=true originalSuppressed=true liveCallsDelta=1 originalCallsDelta=0 luaDispatch=false preCallbacks=1 postCallbacks=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "synthetic-active-validation.log"
            log.write_text(synthetic_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        self.assertEqual(summary["scan"]["invokedUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["originalUeProcessEventActiveValidationCount"], 0)
        self.assertEqual(summary["scan"]["targetEntryUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["suppressedTargetEntryUeProcessEventActiveValidationCount"], 1)
        self.assertEqual(summary["scan"]["syntheticTargetEntryUeProcessEventActiveValidationCount"], 1)
        self.assertFalse(report["ready"]["ueProcessEventActiveValidation"])
        self.assertTrue(report["ready"]["ueProcessEventSyntheticTargetEntry"])

    def test_complete_ue4ss_lua_api_requires_live_target_image_contract(self):
        package_backend_log = READY_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetPackageCalls=1 loadAssetPackageHits=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-package-loadasset.log"
            log.write_text(package_backend_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaDispatch"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeExecutor"])
        self.assertFalse(report["ready"]["liveTargetImageCanary"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertIn(
            "luaLoadAssetPackageNativeExecutor",
            report["liveTargetImageCanaryContract"]["missingKeys"],
        )
        self.assertIn(
            "anchorCoverageObjectDiscovery",
            report["liveTargetImageCanaryContract"]["missingKeys"],
        )

    def test_complete_ue4ss_lua_api_accepts_package_load_asset_with_live_target_image_contract(self):
        package_backend_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetPackageCalls=1 loadAssetPackageHits=1",
            )
            + load_asset_package_guard_evidence(executor_ready=True)
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-package-loadasset-and-anchor-coverage.log"
            log.write_text(package_backend_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertTrue(report["ready"]["luaDispatch"])
        self.assertTrue(report["ready"]["luaLoadAssetPackage"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageCrashGuard"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageGuardedCall"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageReturnValidation"])
        self.assertTrue(report["ready"]["luaLoadClassPackageAbiState"])
        self.assertTrue(report["ready"]["luaLoadClassPackageCallFrameVerification"])
        self.assertTrue(report["ready"]["luaLoadClassPackageNativeExecutor"])
        self.assertTrue(report["ready"]["luaLoadClassPackageNativeInvocation"])
        self.assertTrue(report["ready"]["luaStaticConstructObjectNativeExecutorState"])
        self.assertTrue(report["ready"]["luaStaticConstructObjectNativeExecutorReady"])
        self.assertTrue(report["ready"]["luaStaticConstructObjectNativeInvoke"])
        self.assertTrue(report["ready"]["liveTargetImageCanary"])
        self.assertTrue(report["ready"]["ue4ssLuaApiComplete"])
        self.assertEqual(report["liveTargetImageCanaryContract"]["missingKeys"], [])
        self.assertTrue(report["ready"]["targetImageProcess"])
        self.assertTrue(report["ready"]["signatureManifestExact"])
        self.assertTrue(report["ready"]["signatureManifestPromotable"])
        self.assertTrue(report["liveTargetImageCanaryContract"]["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertTrue(report["liveTargetImageCanaryContract"]["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertTrue(report["liveTargetImageCanaryContract"]["groups"]["runtimePackageLoading"]["ready"])
        self.assertIn("- Ready live target-image canary: `true`", readiness.markdown(report))
        self.assertIn("- Missing live target-image canary keys: `none`", readiness.markdown(report))

    def test_live_target_contract_keys_are_exposed_in_ready_map(self):
        package_backend_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetPackageCalls=1 loadAssetPackageHits=1",
            )
            + load_asset_package_guard_evidence(executor_ready=True)
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-complete-contract.log"
            log.write_text(package_backend_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        contract_keys = {
            key
            for keys in readiness.LIVE_TARGET_IMAGE_CANARY_CONTRACT_GROUPS.values()
            for key in keys
        }
        self.assertEqual(sorted(contract_keys - set(report["ready"])), [])

    def test_complete_ue4ss_lua_api_rejects_missing_runtime_root_discovery(self):
        package_backend_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetPackageCalls=1 loadAssetPackageHits=1",
            )
            + load_asset_package_guard_evidence(executor_ready=True)
        )
        no_runtime_root_log = "\n".join(
            line
            for line in package_backend_log.splitlines()
            if "ue-runtime-discovery" not in line
            and "RuntimeFNamePool" not in line
            and "RuntimeGUObjectArray" not in line
        ) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-without-runtime-root-discovery.log"
            log.write_text(no_runtime_root_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertTrue(report["ready"]["luaDispatch"])
        self.assertTrue(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["runtimeRootDiscovery"])
        self.assertFalse(report["ready"]["targetObjectDiscovery"])
        self.assertFalse(report["ready"]["targetHooks"])
        self.assertFalse(report["ready"]["liveTargetImageCanary"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertIn(
            "runtimeRootDiscovery",
            report["liveTargetImageCanaryContract"]["missingKeys"],
        )
        self.assertEqual(
            report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]["missingKeys"],
            ["runtimeRootDiscovery", "targetObjectDiscovery", "targetHooks"],
        )

    def test_live_target_contract_rejects_wrong_executable_logs(self):
        wrong_exe_log = (
            READY_LOG.replace("DuneSandbox-Win64-Shipping.exe", "dash")
            + load_asset_package_guard_evidence(executor_ready=True)
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-but-wrong-executable.log"
            log.write_text(wrong_exe_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertFalse(report["ready"]["targetImageProcess"])
        self.assertFalse(report["ready"]["objectDiscovery"])
        self.assertFalse(report["ready"]["liveTargetImageCanary"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertIn(
            "targetImageProcess",
            report["liveTargetImageCanaryContract"]["missingKeys"],
        )
        target_gate = next(item for item in report["gates"] if item["name"] == "target-image-process")
        self.assertFalse(target_gate["passed"])
        self.assertIn("real game/server process", target_gate["blocker"])

    def test_explicit_exe_substring_accepts_non_dune_target_image(self):
        generic_log = (
            READY_LOG.replace("DuneSandbox-Win64-Shipping.exe", "ExampleGame-Linux-Shipping")
            + load_asset_package_guard_evidence(executor_ready=True)
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "generic-unreal-target.log"
            log.write_text(generic_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], ["ExampleGame"])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertEqual(summary["targetImageSubstrings"], ["ExampleGame"])
        self.assertEqual(report["targetImageSubstrings"], ["ExampleGame"])
        self.assertTrue(report["ready"]["targetImageProcess"])
        target_gate = next(item for item in report["gates"] if item["name"] == "target-image-process")
        self.assertTrue(target_gate["passed"])
        self.assertIn("targetFilters=ExampleGame", target_gate["evidence"])

    def test_non_dune_target_requires_explicit_exe_substring(self):
        generic_log = READY_LOG.replace("DuneSandbox-Win64-Shipping.exe", "ExampleGame-Linux-Shipping")
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "generic-unreal-target.log"
            log.write_text(generic_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertEqual(report["targetImageSubstrings"], ["DuneSandbox"])
        self.assertFalse(report["ready"]["targetImageProcess"])
        target_gate = next(item for item in report["gates"] if item["name"] == "target-image-process")
        self.assertIn("pass --exe-substring", target_gate["blocker"])

    def test_mixed_helper_process_log_auto_scopes_to_target_pid(self):
        helper_log = (
            "2026-06-16T17:43:38Z pid=1 loader=win-client event=loaded phase=thread exe=/usr/bin/dash native=elf\n"
            "2026-06-16T17:43:38Z pid=1 loader=win-client event=ue-anchor-signature name=FNamePool group=names status=resolved hit=0x10 addr=0x20 module=/usr/bin/dash\n"
            "2026-06-16T17:43:38Z pid=1 loader=win-client event=ue-anchor name=GWorld group=world status=unmapped addr=0x20\n"
            + READY_LOG
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "mixed-helper-and-target.log"
            log.write_text(helper_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertEqual(summary["autoTargetPidFilter"], ["312"])
        self.assertEqual(report["pids"], ["312"])
        self.assertEqual(report["autoTargetPidFilters"], ["312"])
        self.assertTrue(report["ready"]["targetImageProcess"])
        self.assertNotIn("/usr/bin/dash", report["loadedExes"])

    def test_live_target_contract_tracks_call_function_dispatch_separately(self):
        status = {
            key: True
            for keys in readiness.LIVE_TARGET_IMAGE_CANARY_CONTRACT_GROUPS.values()
            for key in keys
        }
        status["ueCallFunctionLiveHookRuntimeTarget"] = False
        contract = readiness.live_target_image_canary_contract(status)

        self.assertFalse(contract["ready"])
        self.assertTrue(contract["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertFalse(contract["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertEqual(
            contract["groups"]["runtimeCallFunctionDispatch"]["missingKeys"],
            ["ueCallFunctionLiveHookRuntimeTarget"],
        )

    def test_live_target_contract_requires_full_process_event_dispatch_evidence(self):
        status = {
            key: True
            for keys in readiness.LIVE_TARGET_IMAGE_CANARY_CONTRACT_GROUPS.values()
            for key in keys
        }
        status["ueProcessEventLiveFunctionPath"] = False
        status["ueProcessEventLiveRawParamValues"] = False
        status["ueProcessEventLuaParamAccessors"] = False
        contract = readiness.live_target_image_canary_contract(status)

        self.assertFalse(contract["ready"])
        self.assertFalse(contract["groups"]["runtimeProcessEventDispatch"]["ready"])
        self.assertTrue(contract["groups"]["runtimeCallFunctionDispatch"]["ready"])
        self.assertEqual(
            contract["groups"]["runtimeProcessEventDispatch"]["missingKeys"],
            [
                "ueProcessEventLiveFunctionPath",
                "ueProcessEventLiveRawParamValues",
                "ueProcessEventLuaParamAccessors",
            ],
        )

    def test_top_level_hook_and_lua_readiness_require_call_function_runtime_hooks(self):
        no_call_function_log = (
            READY_LOG.replace("event=ue-call-function-hook ", "event=ue-call-function-hook-disabled ")
            .replace("event=ue-call-function-live-hook ", "event=ue-call-function-live-hook-disabled ")
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-without-call-function-runtime.log"
            log.write_text(no_call_function_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        self.assertTrue(report["ready"]["ueProcessEventHookRuntimeTarget"])
        self.assertTrue(report["ready"]["ueProcessEventLiveHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueCallFunctionHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueCallFunctionLiveHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueCallFunctionLiveLuaDispatch"])
        self.assertFalse(report["ready"]["hooks"])
        self.assertFalse(report["ready"]["targetHooks"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn(
            "ueCallFunctionHookRuntimeTarget",
            report["liveTargetImageCanaryContract"]["missingKeys"],
        )

    def test_load_asset_backend_anchor_preflight_does_not_complete_package_api(self):
        package_anchor_preflight_log = READY_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 loadAssetPackageArmed=false "
            "loadAssetPackageAvailable=true loadAssetStaticLoadObjectResolved=true",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-loadasset-anchor-preflight.log"
            log.write_text(package_anchor_preflight_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaLoadAssetBackendState"])
        self.assertTrue(report["ready"]["luaLoadAssetBackendAnchors"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertFalse(report["ready"]["luaLoadAssetPackagePreflight"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])

    def test_load_asset_package_bridge_state_does_not_complete_package_api(self):
        package_bridge_log = READY_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
            "loadAssetPackageBridgeStateCalls=1 loadAssetPackageArmed=false",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-loadasset-package-bridge-state.log"
            log.write_text(package_bridge_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaLoadAssetBackendState"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertFalse(report["ready"]["luaLoadAssetPackagePreflight"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])

    def test_load_asset_package_native_invoke_does_not_complete_package_api(self):
        package_native_invoke_log = READY_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
            "loadAssetPackageBridgeStateCalls=1 loadAssetPackageNativeCalls=1 "
            "loadAssetPackageNativeGateHits=1 loadAssetPackageArmed=false",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-loadasset-package-native-invoke.log"
            log.write_text(package_native_invoke_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaLoadAssetBackendState"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageAbiState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackagePreflight"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])

    def test_load_asset_package_abi_state_does_not_complete_package_api(self):
        package_abi_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
                "loadAssetPackageBridgeStateCalls=1 loadAssetPackageNativeCalls=1 "
                "loadAssetPackageNativeGateHits=1 loadAssetPackageArmed=false",
            )
            + "\n2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-abi-state "
            "status=anchor-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=win64-ms-abi "
            "signatureFamily=StaticLoadObject abiVerified=false callFrameReady=false "
            "stringBridgeReady=false classRootReady=false outerReady=false packageAvailable=false\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-loadasset-package-abi-state.log"
            log.write_text(package_abi_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageAbiState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageStringBridge"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeBuffer"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageTCharBuffer"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageTCharVerification"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageCallFrame"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageCallFrameVerification"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeCallAdapter"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])

    def test_load_asset_package_call_frame_does_not_complete_package_api(self):
        package_call_frame_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
                "loadAssetPackageBridgeStateCalls=1 loadAssetPackageNativeCalls=1 "
                "loadAssetPackageNativeGateHits=1 loadAssetPackageArmed=false",
            )
            + "\n2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-abi-state "
            "status=anchor-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=win64-ms-abi "
            "signatureFamily=StaticLoadObject abiVerified=false callFrameReady=false "
            "stringBridgeReady=false classRootReady=false outerReady=false packageAvailable=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-string-bridge-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi stringInputStaged=true boundedInput=true utf8ByteCount=37 "
            "inputEncoding=utf-8 tcharEncoding=unverified-live-build tcharBridgeReady=false "
            "nativeBufferReady=false nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-native-buffer-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi stringInputStaged=true boundedInput=true "
            "utf8BufferReady=true nativeInputBufferReady=true bufferBytes=38 nullTerminated=true "
            "tcharEncoding=unverified-live-build tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-tchar-buffer-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi stringInputStaged=true boundedInput=true "
            "candidateEncoding=windows-wchar-unverified candidateUnitBytes=2 candidateBufferBytes=76 "
            "tcharLayoutVerified=false tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-tchar-verification-state "
            "status=evidence-missing targetName=StaticLoadObject target=0x0 targetImage=false platformAbi=win64-ms-abi "
            "candidateEncoding=windows-wchar-unverified candidateUnitBytes=2 observedUnitBytes=0 "
            "evidenceProvided=false verificationEnabled=false unitMatch=false "
            "tcharLayoutVerified=false tcharBufferReady=false evidence=none\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-call-frame-verification-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 targetImage=false platformAbi=win64-ms-abi signatureFamily=StaticLoadObject argumentCount=7 "
            "pathStaged=true boundedInput=true abiEvidenceProvided=false abiVerificationEnabled=false "
            "abiVerified=false tcharEvidenceProvided=false tcharVerificationEnabled=false "
            "tcharLayoutVerified=false tcharBufferReady=false callFrameReady=false nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-native-call-adapter-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi adapterKind=win64-ms-abi-package-load "
            "signatureFamily=StaticLoadObject argumentCount=7 pathStaged=true boundedInput=true "
            "functionPointerReady=false abiVerified=false tcharLayoutVerified=false callFrameReady=false "
            "invokeEnabled=false nativeBridgeArmed=false adapterReady=false finalInvokeConfirmed=false crashGuardRequired=true crashGuardArmed=false guardedCallRequired=true guardedCallReady=true guardedCallResult=17 returnValidationReady=true invocationDescriptorRequired=true invocationDescriptorConsumed=true nativeCallPlanAccepted=true nativeCallExecutionMode=guarded-native-package-load nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallable=false nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-invocation-descriptor-state "
            "status=derived descriptorKind=guarded-package-native-call "
            "descriptorProvenance=adapter-state-derived nativeCallPlanConstructed=true nativeCallExecutionMode=guarded-native-package-load nativeCallTargetField=TargetAddress nativeCallPathField=Path nativeCallGuardPolicy=crash-guard+guarded-call+return-validation nativeCallReturnValidator=uobject-registry-memory-class nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-native-executor-state "
            "status=prepared executorKind=guarded-package-native-executor nativeExecutorConstructed=true "
            "nativeExecutorDryRun=true nativeExecutorReady=false executorPreflightPassed=false "
            "finalNativeCallEligible=false nativeExecutorBlockReason=anchor-missing "
            "finalNativeCallBlocked=true finalNativeCallBlockReason=preflight-state-only "
            "nativeInvoked=false\n"
            "2026-01-01T00:00:00Z pid=312 loader=win-client event=lua-load-asset-package-call-frame-state "
            "status=anchor-missing path=/Script/DuneProbe.MissingPackageAsset targetName=StaticLoadObject "
            "target=0x0 platformAbi=win64-ms-abi signatureFamily=StaticLoadObject pathStaged=true "
            "argumentDescriptorReady=true tcharBridgeReady=false callFrameReady=false nativeInvoked=false\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-loadasset-package-call-frame.log"
            log.write_text(package_call_frame_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaLoadAssetPackageAbiState"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageStringBridge"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageNativeBuffer"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageTCharBuffer"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageTCharVerification"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageCallFrame"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageCallFrameVerification"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageNativeCallAdapter"])
        self.assertTrue(report["ready"]["luaLoadAssetPackageInvocationDescriptor"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeExecutor"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertIn("crash-guard state", " ".join(report["nextSteps"]))

    def test_load_asset_package_preflight_does_not_complete_package_api(self):
        package_preflight_log = READY_LOG.replace(
            "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
            "isACalls=5 isAHits=2 loadAssetCalls=2 loadAssetHits=1 "
            "loadAssetBackend=registry loadAssetBackendStateCalls=1 "
            "loadAssetPackageArmed=false loadAssetPackagePreflightCalls=1 "
            "loadAssetPackageGateHits=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-loadasset-package-preflight.log"
            log.write_text(package_preflight_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
            )

        self.assertTrue(report["ready"]["luaLoadAssetBackendState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageBridgeState"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeInvoke"])
        self.assertTrue(report["ready"]["luaLoadAssetPackagePreflight"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])

    def test_load_asset_package_executor_requires_target_image_anchor(self):
        generic_executor_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetPackageCalls=1 loadAssetPackageHits=1",
            )
            + load_asset_package_guard_evidence(executor_ready=True).replace(
                " targetName=StaticLoadObject target=0x140048000 targetImage=true signatureFamily=StaticLoadObject",
                "",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready-with-generic-loadasset-executor.log"
            log.write_text(generic_executor_log, encoding="utf-8")
            summary = readiness.summarize_log(log, [], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [ready_anchor_coverage()],
            )

        gate = next(
            item for item in report["gates"] if item["name"] == "lua-load-asset-package-native-executor"
        )
        self.assertFalse(gate["passed"])
        self.assertIn("targetReady=0 ready=1", gate["evidence"])
        self.assertFalse(report["ready"]["luaLoadAssetPackageNativeExecutor"])
        self.assertFalse(report["ready"]["luaLoadAssetPackage"])
        self.assertFalse(report["ready"]["liveTargetImageCanary"])
        self.assertFalse(report["ready"]["ue4ssLuaApiComplete"])
        self.assertIn("guarded LoadAsset package bridge state", " ".join(report["nextSteps"]))
        self.assertIn(
            "luaLoadAssetPackageNativeExecutor",
            report["liveTargetImageCanaryContract"]["groups"]["runtimePackageLoading"]["missingKeys"],
        )

    def test_per_loader_readiness_keeps_cross_target_runtime_evidence_separate(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        win_complete_log = (
            READY_LOG.replace(
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1",
                "isACalls=5 isAHits=2 loadAssetCalls=1 loadAssetHits=1 "
                "loadAssetPackageCalls=1 loadAssetPackageHits=1",
            )
            + load_asset_package_guard_evidence(executor_ready=True)
        )
        linux_without_runtime_context = win_complete_log.replace("loader=win-client", "loader=linux-client").replace(
            "functionProvenance=runtime",
            "functionProvenance=self-test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            win_log = Path(tmp) / "win-ready.log"
            linux_log = Path(tmp) / "linux-missing-runtime-context.log"
            win_log.write_text(win_complete_log, encoding="utf-8")
            linux_log.write_text(linux_without_runtime_context, encoding="utf-8")
            summaries = [
                readiness.summarize_log(win_log, [], [], []),
                readiness.summarize_log(linux_log, [], [], []),
            ]
            report = readiness.build_report(summaries, [validation], [ready_anchor_coverage()])

        self.assertTrue(report["ready"]["ueProcessEventLiveRuntimeContext"])
        self.assertIn("win-client", report["perLoaderReadiness"])
        self.assertIn("linux-client", report["perLoaderReadiness"])
        self.assertTrue(
            report["perLoaderReadiness"]["win-client"]["ready"]["ueProcessEventLiveRuntimeContext"]
        )
        self.assertTrue(
            report["perLoaderReadiness"]["win-client"]["ready"]["liveTargetImageCanary"]
        )
        self.assertTrue(
            report["perLoaderReadiness"]["win-client"]["ready"]["ue4ssLuaApiComplete"]
        )
        self.assertEqual(
            report["perLoaderReadiness"]["win-client"]["liveTargetImageCanaryContract"]["missingKeys"],
            [],
        )
        self.assertFalse(
            report["perLoaderReadiness"]["linux-client"]["ready"]["ueProcessEventLiveRuntimeContext"]
        )
        self.assertFalse(
            report["perLoaderReadiness"]["linux-client"]["ready"]["liveTargetImageCanary"]
        )
        self.assertFalse(
            report["perLoaderReadiness"]["linux-client"]["ready"]["ue4ssLuaApiComplete"]
        )
        self.assertIn(
            "ueProcessEventLiveRuntimeContext",
            report["perLoaderReadiness"]["linux-client"]["liveTargetImageCanaryContract"]["missingKeys"],
        )
        self.assertIn(
            "ue-process-event-live-runtime-context",
            report["perLoaderReadiness"]["linux-client"]["failedGates"],
        )
        markdown = readiness.markdown(report)
        self.assertIn("liveTargetImage=`true` ue4ssLuaApiComplete=`true`", markdown)
        self.assertIn("liveTargetImage=`false` ue4ssLuaApiComplete=`false`", markdown)

    def test_linux_client_loader_alias_matches_native_client_logs(self):
        linux_log = READY_LOG.replace("loader=win-client", "loader=client")
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "linux-client-alias.log"
            log.write_text(linux_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["linux-client"], [], [])

        self.assertEqual(summary["scan"]["loadCount"], 1)
        self.assertEqual(summary["scan"]["loaders"], ["client"])

    def test_runtime_root_discovery_gate_requires_validated_promoted_roots(self):
        runtime_log = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-18T00:00:01Z pid=312 loader=win-client event=scan-start strings=0 signatures=0 filters=0 maxHits=2 maxRegionBytes=268435456
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x140060000 blockSlot=0x140060010 firstBlock=0x140080000 blocksOffset=0x10 stride=2 hit=1 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140070000 base=0x140070000 numElements=42 numChunks=1 hit=1 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x140060000 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x140070000 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=1 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=2
2026-06-18T00:00:01Z pid=312 loader=win-client event=scan-finish
"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "runtime-roots.log"
            log.write_text(runtime_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        gate = next(item for item in report["gates"] if item["name"] == "ue-runtime-root-discovery")
        self.assertFalse(gate["passed"])
        self.assertFalse(report["ready"]["runtimeRootDiscovery"])
        self.assertEqual(
            report["runtimeDiscovery"]["promotedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(report["runtimeDiscovery"]["validatedNames"], [])
        self.assertEqual(report["runtimeDiscovery"]["coverage"]["targetWritableImageCount"], 2)
        self.assertEqual(
            report["runtimeDiscovery"]["candidateNameCounts"],
            {"RuntimeFNamePool": 1, "RuntimeGUObjectArray": 1},
        )
        self.assertEqual(
            report["runtimeDiscovery"]["candidateImageCounts"],
            {"C:\\game\\DuneSandbox-Win64-Shipping.exe": 2},
        )
        self.assertEqual(
            [item["imageOffset"] for item in report["runtimeDiscovery"]["candidateLocations"]],
            ["0x60000", "0x70000"],
        )
        self.assertEqual(report["runtimeDiscovery"]["failureCounts"], {"unvalidated-root-hits": 1})

    def test_runtime_root_discovery_gate_accepts_validated_ambiguous_roots(self):
        runtime_log = """\
2026-06-19T06:10:46Z pid=337 loader=server event=loaded phase=snapshot exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-19T06:10:48Z pid=337 loader=server event=scan-start strings=0 signatures=0 filters=0 maxHits=2 maxMappingBytes=268435456
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-start phase=ue-delayed mappings=419 maxMappingBytes=536870912 maxCandidates=32 minObjectArrayElements=1
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x55cb1ab14ce8 blockSlot=0x55cb1ab14cf8 firstBlock=0x55cb1a3cf8b8 blocksOffset=0x10 stride=2 hit=1 imageOffset=0x1642ace8 fileOffset=0x16428ce8 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x55cb1ab14d18 blockSlot=0x55cb1ab14d28 firstBlock=0x55cb18f772e8 blocksOffset=0x10 stride=2 hit=2 imageOffset=0x1642ad18 fileOffset=0x16428d18 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:11:18Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x55cb1adbf4c0 base=0x55cb1adbf4c0 numElements=144038 numChunks=3 hit=1 imageOffset=0x0 fileOffset=0x28c4c0 perms=rw-p map=
2026-06-19T06:11:18Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x55cb1ae778c8 base=0x55cb1ae778c8 numElements=32 numChunks=32 hit=2 imageOffset=0x0 fileOffset=0x3448c8 perms=rw-p map=
2026-06-19T06:11:57Z pid=337 loader=server event=ue-runtime-discovery name=RuntimeFNamePool status=ambiguous hits=2
2026-06-19T06:11:57Z pid=337 loader=server event=ue-runtime-discovery name=RuntimeGUObjectArray status=ambiguous hits=2
2026-06-19T06:11:57Z pid=337 loader=server event=ue-runtime-discovery-finish phase=ue-delayed fnameHits=2 objectArrayHits=2 targetWritableMappings=3 anonymousWritableMappings=2 oversizedMappings=0 scannedSlots=39619072 fnameProbes=1594 objectArrayProbes=7927141 anchors=80
2026-06-19T06:11:57Z pid=337 loader=server event=ue-uobject phase=ue-delayed name=RuntimeGUObjectArray status=candidate object=0x55cb1adbf4c0 class=0x55cb1adbf4c0 classMapped=true
2026-06-19T06:11:57Z pid=337 loader=server event=ue-object-array-finish phase=ue-delayed registryCount=10
2026-06-19T06:11:57Z pid=337 loader=server event=ue-fname-finish phase=ue-delayed status=ready pool=0x7f54e33bb4a0 source=FNamePool:indirect
2026-06-19T06:11:57Z pid=337 loader=server event=scan-finish
"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "validated-runtime-roots.log"
            log.write_text(runtime_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["server"], [], [])
            report = readiness.build_report([summary], [])

        gate = next(item for item in report["gates"] if item["name"] == "ue-runtime-root-discovery")
        self.assertTrue(gate["passed"])
        self.assertTrue(report["ready"]["runtimeRootDiscovery"])
        self.assertEqual(report["runtimeDiscovery"]["promotedNames"], [])
        self.assertEqual(
            report["runtimeDiscovery"]["validatedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(report["runtimeDiscovery"]["failureCounts"], {"ambiguous-root-hits": 1})

    def test_runtime_root_discovery_accepts_explicit_consumer_validation_events(self):
        runtime_log = """\
2026-06-19T06:10:46Z pid=337 loader=server event=loaded phase=snapshot exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-19T06:10:48Z pid=337 loader=server event=scan-start strings=0 signatures=0 filters=0 maxMappingBytes=536870912
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-start phase=ue-delayed mappings=419 maxMappingBytes=536870912 maxCandidates=32 minObjectArrayElements=1
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x55cb1ab14ce8 hit=1 imageOffset=0x1642ace8 fileOffset=0x16428ce8 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x55cb1adbf4c0 base=0x55cb1adbf4c0 numElements=144038 numChunks=3 hit=1 imageOffset=0x28c4c0 fileOffset=0x28c4c0 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:49Z pid=337 loader=server event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x55cb1ab14ce8 imageOffset=0x1642ace8 fileOffset=0x16428ce8 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:49Z pid=337 loader=server event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x55cb1adbf4c0 imageOffset=0x28c4c0 fileOffset=0x28c4c0 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:49Z pid=337 loader=server event=ue-runtime-discovery-finish phase=ue-delayed fnameHits=1 objectArrayHits=1 targetWritableMappings=2 anonymousWritableMappings=0 oversizedMappings=0 scannedSlots=4096 fnameProbes=512 objectArrayProbes=1024 anchors=2
2026-06-19T06:10:49Z pid=337 loader=server event=ue-runtime-root-validation phase=ue-delayed name=RuntimeGUObjectArray status=validated consumer=object-array registryCount=12
2026-06-19T06:10:49Z pid=337 loader=server event=ue-runtime-root-validation phase=ue-delayed name=RuntimeFNamePool status=validated consumer=fname pool=0x55cb1ab14ce8 source=RuntimeFNamePool:direct
2026-06-19T06:10:49Z pid=337 loader=server event=scan-finish
"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "explicit-consumer-validation.log"
            log.write_text(runtime_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["server"], [], [])
            report = readiness.build_report([summary], [])

        self.assertEqual(
            summary["scan"]["ueRuntimeDiscovery"]["consumerValidatedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(
            summary["scan"]["ueRuntimeDiscovery"]["consumerValidationByConsumer"],
            {"fname": 1, "object-array": 1},
        )
        self.assertTrue(report["ready"]["runtimeRootDiscovery"])
        self.assertTrue(report["ready"]["runtimeRootValidation"])
        self.assertEqual(
            report["runtimeDiscovery"]["validatedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )

    def test_live_target_contract_requires_runtime_root_validation(self):
        runtime_log = """\
2026-06-19T06:10:46Z pid=337 loader=server event=loaded phase=snapshot exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-19T06:10:48Z pid=337 loader=server event=scan-start strings=0 signatures=0 filters=0 maxMappingBytes=536870912
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-start phase=ue-delayed mappings=419 maxMappingBytes=536870912 maxCandidates=32 minObjectArrayElements=1
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x55cb1ab14ce8 hit=1 imageOffset=0x1642ace8 fileOffset=0x16428ce8 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:48Z pid=337 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x55cb1adbf4c0 base=0x55cb1adbf4c0 numElements=144038 numChunks=3 hit=1 imageOffset=0x28c4c0 fileOffset=0x28c4c0 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:49Z pid=337 loader=server event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x55cb1ab14ce8 imageOffset=0x1642ace8 fileOffset=0x16428ce8 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:49Z pid=337 loader=server event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x55cb1adbf4c0 imageOffset=0x28c4c0 fileOffset=0x28c4c0 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-19T06:10:49Z pid=337 loader=server event=ue-runtime-discovery-finish phase=ue-delayed fnameHits=1 objectArrayHits=1 targetWritableMappings=2 anonymousWritableMappings=0 oversizedMappings=0 scannedSlots=4096 fnameProbes=512 objectArrayProbes=1024 anchors=2
2026-06-19T06:10:49Z pid=337 loader=server event=scan-finish
"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "discovered-but-unvalidated-runtime-roots.log"
            log.write_text(runtime_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["server"], [], [])
            report = readiness.build_report([summary], [])

        self.assertFalse(report["ready"]["runtimeRootDiscovery"])
        self.assertFalse(report["ready"]["runtimeRootValidation"])
        self.assertFalse(report["ready"]["liveTargetImageCanary"])
        self.assertIn("runtimeRootDiscovery", report["liveTargetImageCanaryContract"]["missingKeys"])
        self.assertIn("runtimeRootValidation", report["liveTargetImageCanaryContract"]["missingKeys"])
        self.assertIn(
            "runtimeRootDiscovery",
            report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]["missingKeys"],
        )
        self.assertIn(
            "runtimeRootValidation",
            report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]["missingKeys"],
        )

    def test_runtime_root_discovery_gate_reports_not_run_on_old_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "partial.log"
            log.write_text(PARTIAL_LOG, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [])

        gate = next(item for item in report["gates"] if item["name"] == "ue-runtime-root-discovery")
        self.assertFalse(gate["passed"])
        self.assertFalse(report["ready"]["runtimeRootDiscovery"])
        self.assertEqual(report["runtimeDiscovery"]["failureCounts"], {"not-run": 1})
        self.assertFalse(report["ready"]["runtimeRootValidation"])

    def test_runtime_root_validation_can_pass_for_explicit_runtime_roots_without_auto_discovery(self):
        runtime_log = """\
2026-06-19T09:41:28Z pid=340 loader=server event=loaded phase=snapshot exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-19T09:41:28Z pid=340 loader=server event=scan-start strings=0 signatures=0 filters=0 maxHits=2 maxMappingBytes=268435456
2026-06-19T09:42:13Z pid=340 loader=server event=ue-candidate-global name=RuntimeFNamePool status=added address=0x557e1201ce18 imageOffset=0x1e1e18 absolute=false runtimeRwFileOffset=true
2026-06-19T09:42:13Z pid=340 loader=server event=ue-candidate-global name=RuntimeGUObjectArray status=added address=0x557e120c74c0 imageOffset=0x28c4c0 absolute=false runtimeRwFileOffset=true
2026-06-19T09:42:13Z pid=340 loader=server event=ue-anchor name=RuntimeFNamePool group=names status=mapped addr=0x557e1201ce18 readable=true writable=true executable=false imageOffset=0x0 fileOffset=0x1e1e18 perms=rw-p map=
2026-06-19T09:42:13Z pid=340 loader=server event=ue-anchor name=RuntimeGUObjectArray group=objects status=mapped addr=0x557e120c74c0 readable=true writable=true executable=false imageOffset=0x0 fileOffset=0x28c4c0 perms=rw-p map=
2026-06-19T09:42:13Z pid=340 loader=server event=ue-object-array name=RuntimeGUObjectArray mode=direct status=finished base=0x557e120c74c0 scanned=128 registered=15
2026-06-19T09:42:13Z pid=340 loader=server event=ue-object-array-finish phase=ue-delayed registryCount=32
2026-06-19T09:42:13Z pid=340 loader=server event=ue-runtime-root-validation phase=ue-delayed name=RuntimeGUObjectArray status=validated consumer=object-array registryCount=32
2026-06-19T09:42:13Z pid=340 loader=server event=ue-fname source=ue-object-array objectName=RuntimeGUObjectArray_0 status=decoded object=0x7efe0abdac40 pool=0x557e1201ce18 resolver=RuntimeFNamePool:direct comparisonIndex=2429 number=0 decoded=_Script_CoreUObject
2026-06-19T09:42:13Z pid=340 loader=server event=ue-fname-finish phase=ue-delayed status=ready pool=0x557e1201ce18 source=RuntimeFNamePool:direct
2026-06-19T09:42:13Z pid=340 loader=server event=ue-runtime-root-validation phase=ue-delayed name=RuntimeFNamePool status=validated consumer=fname pool=0x557e1201ce18 source=RuntimeFNamePool:direct
2026-06-19T09:42:13Z pid=340 loader=server event=scan-finish
"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "explicit-runtime-roots.log"
            log.write_text(runtime_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["server"], [], [])
            report = readiness.build_report([summary], [])

        validation_gate = next(item for item in report["gates"] if item["name"] == "ue-runtime-root-validation")
        discovery_gate = next(item for item in report["gates"] if item["name"] == "ue-runtime-root-discovery")
        self.assertTrue(validation_gate["passed"])
        self.assertFalse(discovery_gate["passed"])
        self.assertTrue(report["ready"]["runtimeRootValidation"])
        self.assertFalse(report["ready"]["runtimeRootDiscovery"])
        self.assertEqual(
            report["runtimeRootValidation"]["validatedNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(
            report["runtimeDiscovery"]["rootValidationNames"],
            ["RuntimeFNamePool", "RuntimeGUObjectArray"],
        )
        self.assertEqual(
            report["runtimeDiscovery"]["validatedLocations"],
            [
                {
                    "addr": "0x557e1201ce18",
                    "consumer": "fname",
                    "fileOffset": "0x1e1e18",
                    "imageOffset": "0x0",
                    "map": "",
                    "name": "RuntimeFNamePool",
                    "perms": "rw-p",
                    "targetImage": "",
                    "validated": "true",
                },
                {
                    "addr": "0x557e120c74c0",
                    "consumer": "object-array",
                    "fileOffset": "0x28c4c0",
                    "imageOffset": "0x0",
                    "map": "",
                    "name": "RuntimeGUObjectArray",
                    "perms": "rw-p",
                    "targetImage": "",
                    "validated": "true",
                },
            ],
        )

    def test_self_test_registry_records_do_not_open_runtime_registry_readiness(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_registry = (
            READY_LOG.replace("DecodedWorldClass_0", "SelfTestWorldClass_0")
            .replace("DecodedWorld_0", "SelfTestWorld_0")
            .replace("DecodedFunction_0", "SelfTestFunction_0")
            .replace("GWorld_0", "SelfTestGWorld_0")
            .replace("GWorld.", "SelfTestGWorld.")
            .replace("/RuntimeProbe/GWorld", "/RuntimeProbe/SelfTestGWorld")
            .replace("/Script/GWorld", "/Script/SelfTestGWorld")
            .replace("name=GWorld ", "name=SelfTestGWorld ")
            .replace("objectName=GWorld ", "objectName=SelfTestGWorld ")
            .replace("aliasOf=GWorld ", "aliasOf=SelfTestGWorld ")
            .replace("terminalPath=/RuntimeProbe/GWorld ", "terminalPath=/RuntimeProbe/SelfTestGWorld ")
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-registry.log"
            log.write_text(self_test_registry, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        object_gate = next(item for item in report["gates"] if item["name"] == "lua-object-registry-runtime")
        function_gate = next(item for item in report["gates"] if item["name"] == "lua-function-registry-runtime")
        alias_gate = next(item for item in report["gates"] if item["name"] == "lua-decoded-object-aliases-runtime")
        array_gate = next(item for item in report["gates"] if item["name"] == "ue-object-array-registry-runtime")
        self.assertTrue(report["ready"]["luaObjectRegistry"])
        self.assertTrue(report["ready"]["luaObjectRegistryChecks"])
        self.assertTrue(report["ready"]["luaFunctionRegistryChecks"])
        self.assertTrue(report["ready"]["luaDecodedObjectAliases"])
        self.assertTrue(report["ready"]["ueObjectArrayRegistry"])
        self.assertFalse(object_gate["passed"])
        self.assertFalse(function_gate["passed"])
        self.assertFalse(alias_gate["passed"])
        self.assertFalse(array_gate["passed"])
        self.assertFalse(report["ready"]["luaObjectRegistryRuntime"])
        self.assertFalse(report["ready"]["luaFunctionRegistryRuntime"])
        self.assertFalse(report["ready"]["luaDecodedObjectAliasesRuntime"])
        self.assertFalse(report["ready"]["ueObjectArrayRegistryRuntime"])
        self.assertFalse(report["ready"]["objectDiscovery"])
        self.assertFalse(report["ready"]["findObjectSemantics"])
        self.assertFalse(report["ready"]["reflection"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_explicit_registry_provenance_overrides_runtime_name_heuristic(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        lines = []
        for line in READY_LOG.splitlines():
            if (
                "event=lua-object-registry " in line
                or "event=lua-object-registry-check " in line
                or "event=lua-function-registry-check " in line
                or "event=lua-function-iteration-check " in line
            ):
                line += " registryProvenance=self-test"
            lines.append(line)
        explicit_self_test_registry = "\n".join(lines) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "explicit-self-test-registry.log"
            log.write_text(explicit_self_test_registry, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["luaObjectRegistry"])
        self.assertTrue(report["ready"]["luaObjectRegistryChecks"])
        self.assertTrue(report["ready"]["luaFunctionRegistryChecks"])
        self.assertTrue(report["ready"]["luaFunctionIteration"])
        self.assertFalse(report["ready"]["luaObjectRegistryRuntime"])
        self.assertFalse(report["ready"]["luaFunctionRegistryRuntime"])
        self.assertFalse(report["ready"]["luaDecodedObjectAliasesRuntime"])
        self.assertFalse(report["ready"]["ueObjectArrayRegistryRuntime"])
        self.assertFalse(report["ready"]["luaFunctionIterationRuntime"])

    def test_object_array_function_registry_check_counts_as_runtime_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        object_array_registry = "\n".join(
            line
            for line in READY_LOG.splitlines()
            if "event=lua-function-registry-check" not in line
            and "event=ue-function-native-identity" not in line
        )
        object_array_registry += (
            "\n2026-06-16T17:43:39Z pid=312 loader=win-client "
            "event=ue-function-native-identity source=ue-object-array status=promoted "
            "name=GWorld functionIndex=0 chain=objectArray function=0x140082000 "
            "functionName=DecodedFunction_0 "
            "functionPath=/Script/GWorld.DecodedFunction_0:Function "
            "functionRuntimePath=/RuntimeProbe/GWorld.DecodedFunction_0:Function "
            "root=0x0 functionFlags=0x400 functionFlagsReadable=true "
            "registryProvenance=runtime\n"
            "2026-06-16T17:43:39Z pid=312 loader=win-client "
            "event=lua-function-registry-check source=ue-object-array status=passed "
            "name=DecodedFunction_0 path=/Script/GWorld.DecodedFunction_0:Function "
            "runtimePath=/RuntimeProbe/GWorld.DecodedFunction_0:Function "
            "address=0x140082000 pathHit=true runtimePathHit=true nameHit=true "
            "addressHit=true flagsHit=true registryCount=1 registryProvenance=runtime\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "object-array-function-registry.log"
            log.write_text(object_array_registry, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(item for item in report["gates"] if item["name"] == "lua-function-registry-runtime")
        self.assertTrue(gate["passed"])
        self.assertTrue(report["ready"]["luaFunctionRegistryRuntime"])
        self.assertTrue(report["ready"]["luaFunctionRegistryChecks"])

    def test_self_test_only_live_hook_does_not_open_runtime_hook_readiness(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_target = READY_LOG.replace(
            "event=ue-process-event-live-hook phase=thread status=installed target=0x140040000 selfTestTarget=false callSelfTest=false",
            "event=ue-process-event-live-hook phase=thread status=installed target=0x140040000 selfTestTarget=true callSelfTest=true",
        ).replace(
            "functionProvenance=runtime",
            "functionProvenance=self-test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-live-hook.log"
            log.write_text(self_test_target, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        target_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-live-hook-runtime-target")
        self.assertFalse(target_gate["passed"])
        self.assertTrue(report["ready"]["ueProcessEventLiveHook"])
        self.assertFalse(report["ready"]["ueProcessEventLiveHookRuntimeTarget"])
        self.assertFalse(report["ready"]["hooks"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("target-image anchor/provenance", target_gate["blocker"])

    def test_non_self_test_hook_without_target_provenance_does_not_open_hook_readiness(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        unproven_hook_target = (
            READY_LOG
            .replace(
                "event=ue-anchor-signature name=ProcessEvent group=dispatch status=resolved hit=0x140004000 addr=0x140040000 transform=callrel32 rva=0x40000 allocationBase=0x140000000 regionBase=0x140040000 protect=0x20 type=0x1000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe\n",
                "",
            )
            .replace(" targetSource=explicit targetName=CallFunctionByNameWithArguments", "")
            .replace("functionProvenance=runtime", "functionProvenance=self-test")
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "unproven-non-self-test-hook.log"
            log.write_text(unproven_hook_target, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        scan = summary["scan"]
        self.assertGreater(scan["ueProcessEventHookCount"], 0)
        self.assertGreater(scan["nonSelfTestPassedUeProcessEventHookCount"], 0)
        self.assertEqual(scan["provenTargetPassedUeProcessEventHookCount"], 0)
        self.assertEqual(scan["provenTargetInstalledUeProcessEventLiveHookCount"], 0)
        self.assertEqual(scan["provenTargetPassedUeCallFunctionHookCount"], 0)
        self.assertEqual(scan["provenTargetInstalledUeCallFunctionLiveHookCount"], 0)
        self.assertEqual(scan["routedUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(scan["handledUeCallFunctionLiveLuaHookCount"], 1)
        self.assertEqual(scan["provenTargetRoutedUeCallFunctionLiveLuaHookCount"], 0)
        self.assertEqual(scan["provenTargetHandledUeCallFunctionLiveLuaHookCount"], 0)
        self.assertFalse(report["ready"]["ueProcessEventHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueProcessEventLiveHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueCallFunctionHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueCallFunctionLiveHookRuntimeTarget"])
        self.assertFalse(report["ready"]["ueCallFunctionLiveLuaDispatch"])
        self.assertFalse(report["ready"]["hooks"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_self_test_function_context_does_not_open_live_runtime_context_readiness(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_context = READY_LOG.replace(
            "/RuntimeProbe/GWorld.DecodedFunction_0:Function",
            "/RuntimeProbe/GWorld.SelfTestFunction_0:Function",
        ).replace(
            "/Script/GWorld.DecodedFunction_0:Function",
            "/Script/GWorld.SelfTestFunction_0:Function",
        ).replace(
            "functionProvenance=runtime",
            "functionProvenance=self-test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-function-context.log"
            log.write_text(self_test_context, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        context_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-live-runtime-context")
        registry_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-live-runtime-registry-context")
        param_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-live-param-values")
        class_aware_gate = next(
            item for item in report["gates"] if item["name"] == "ue-process-event-live-class-aware-param-values"
        )
        self.assertFalse(context_gate["passed"])
        self.assertFalse(registry_gate["passed"])
        self.assertFalse(param_gate["passed"])
        self.assertFalse(class_aware_gate["passed"])
        self.assertTrue(report["ready"]["ueProcessEventLiveFunctionPath"])
        self.assertFalse(report["ready"]["ueProcessEventLiveRuntimeContext"])
        self.assertFalse(report["ready"]["ueProcessEventLiveRuntimeRegistryContext"])
        self.assertFalse(report["ready"]["ueProcessEventLiveParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveClassAwareParamValues"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("outside loader-owned self-test functions", context_gate["blocker"])
        self.assertIn("runtime ProcessEvent params", param_gate["blocker"])
        self.assertIn("runtime ctx.Function registry identity", class_aware_gate["blocker"])

    def test_live_lua_hook_routing_requires_matching_close_results(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "wrong-routing.log"
            log.write_text(READY_LOG.replace("postResult=31", "postResult=-99"), encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        routing_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-lua-hook-routing")
        self.assertFalse(routing_gate["passed"])
        self.assertFalse(report["ready"]["ueProcessEventLuaHookRouting"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_hooks_require_find_object_semantics(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        without_outer_identity = "\n".join(
            line for line in READY_LOG.splitlines() if "event=lua-object-outer-chain" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-find-object-semantics.log"
            log.write_text(without_outer_identity, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["objectDiscovery"])
        self.assertTrue(report["ready"]["objectDiscoveryCoverage"])
        self.assertFalse(report["ready"]["findObjectSemantics"])
        self.assertFalse(report["ready"]["liveTargetImageCanary"])
        self.assertFalse(report["liveTargetImageCanaryContract"]["groups"]["runtimeObjectRegistry"]["ready"])
        self.assertIn(
            "findObjectSemantics",
            report["liveTargetImageCanaryContract"]["groups"]["runtimeObjectRegistry"]["missingKeys"],
        )
        self.assertFalse(report["ready"]["hooks"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("outerChainIdentities", report["objectDiscoveryCoverage"]["missingFindObjectComponents"])

    def test_find_object_semantics_require_native_registry_checks(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        without_registry_checks = "\n".join(
            line for line in READY_LOG.splitlines() if "event=lua-object-registry-check" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-registry-checks.log"
            log.write_text(without_registry_checks, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["objectDiscovery"])
        self.assertFalse(report["ready"]["luaObjectRegistryChecks"])
        self.assertFalse(report["ready"]["findObjectSemantics"])
        self.assertFalse(report["ready"]["hooks"])
        self.assertIn("objectRegistry", report["objectDiscoveryCoverage"]["missingFindObjectComponents"])

    def test_reflection_requires_native_function_registry_checks(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        without_registry_checks = "\n".join(
            line for line in READY_LOG.splitlines() if "event=lua-function-registry-check" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-function-registry-checks.log"
            log.write_text(without_registry_checks, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["objectDiscovery"])
        self.assertFalse(report["ready"]["luaFunctionRegistryChecks"])
        self.assertFalse(report["ready"]["reflection"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_function_iteration_requires_native_iteration_check(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        without_iteration_check = "\n".join(
            line for line in READY_LOG.splitlines() if "event=lua-function-iteration-check" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-function-iteration-check.log"
            log.write_text(without_iteration_check, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["reflection"])
        self.assertFalse(report["ready"]["luaFunctionIteration"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_function_iteration_requires_runtime_owner_iteration(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_iteration = READY_LOG.replace(
            "event=lua-function-iteration-check source=ForEachFunction status=passed mode=owner name=GWorld class=UObjectCandidate",
            "event=lua-function-iteration-check source=ForEachFunction status=passed mode=self-test name=DuneProbeSelfTestClass class=UClass",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-function-iteration.log"
            log.write_text(self_test_iteration, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        runtime_gate = next(item for item in report["gates"] if item["name"] == "lua-function-iteration-runtime")
        self.assertTrue(report["ready"]["luaFunctionIteration"])
        self.assertFalse(runtime_gate["passed"])
        self.assertFalse(report["ready"]["luaFunctionIterationRuntime"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_reflection_live_descriptor_values_require_runtime_descriptor(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_descriptor = READY_LOG.replace(
            "runtimeLiveDescriptorValueGetHits=2 selfTestLiveDescriptorValueGetHits=0 "
            "runtimeLiveDescriptorValueSetHits=1 selfTestLiveDescriptorValueSetHits=0",
            "runtimeLiveDescriptorValueGetHits=0 selfTestLiveDescriptorValueGetHits=2 "
            "runtimeLiveDescriptorValueSetHits=0 selfTestLiveDescriptorValueSetHits=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-live-descriptor.log"
            log.write_text(self_test_descriptor, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        runtime_gate = next(
            item for item in report["gates"] if item["name"] == "lua-reflection-live-descriptor-values-runtime"
        )
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorValues"])
        self.assertFalse(runtime_gate["passed"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_native_reflection_descriptors_require_runtime_target_records(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_native_reflection = (
            READY_LOG.replace("event=ue-reflection-property name=GWorld ", "event=ue-reflection-property name=SelfTestGWorld ")
            .replace("event=ue-reflection-value name=GWorld ", "event=ue-reflection-value name=SelfTestGWorld ")
            .replace("descriptorProvenance=runtime", "descriptorProvenance=self-test")
            .replace("fieldName=DecodedWorld_0 ", "fieldName=SelfTestWorld_0 ")
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-native-reflection.log"
            log.write_text(self_test_native_reflection, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        descriptor_gate = next(
            item for item in report["gates"] if item["name"] == "ue-reflection-property-descriptors-runtime"
        )
        value_gate = next(
            item for item in report["gates"] if item["name"] == "ue-reflection-property-values-runtime"
        )
        self.assertTrue(report["ready"]["ueReflectionPropertyDescriptors"])
        self.assertTrue(report["ready"]["ueReflectionPropertyValues"])
        self.assertFalse(descriptor_gate["passed"])
        self.assertFalse(value_gate["passed"])
        self.assertFalse(report["ready"]["ueReflectionPropertyDescriptorsRuntime"])
        self.assertFalse(report["ready"]["ueReflectionPropertyValuesRuntime"])
        self.assertFalse(report["ready"]["reflection"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_native_reflection_values_must_match_runtime_descriptors(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        orphan_value = READY_LOG.replace(
            "event=ue-reflection-value name=GWorld descriptorProvenance=runtime chain=childProperties index=0",
            "event=ue-reflection-value name=GWorld descriptorProvenance=runtime chain=childProperties index=99",
        ).replace(
            "event=ue-reflection-value name=GWorld descriptorProvenance=runtime chain=propertyLink index=0",
            "event=ue-reflection-value name=GWorld descriptorProvenance=runtime chain=propertyLink index=99",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "orphan-native-reflection-value.log"
            log.write_text(orphan_value, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        scan = summary["scan"]
        self.assertEqual(scan["runtimeReadUeReflectionValueCount"], 2)
        self.assertEqual(scan["runtimeDescriptorMatchedReadUeReflectionValueCount"], 0)
        descriptor_gate = next(
            item for item in report["gates"] if item["name"] == "ue-reflection-property-descriptors-runtime"
        )
        value_gate = next(
            item for item in report["gates"] if item["name"] == "ue-reflection-property-values-runtime"
        )
        self.assertTrue(descriptor_gate["passed"])
        self.assertFalse(value_gate["passed"])
        self.assertTrue(report["ready"]["ueReflectionPropertyDescriptorsRuntime"])
        self.assertFalse(report["ready"]["ueReflectionPropertyValuesRuntime"])
        self.assertFalse(report["ready"]["reflection"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("matching a readable non-self-test runtime descriptor", value_gate["blocker"])

    def test_lua_reflection_for_each_property_requires_runtime_descriptor_enumeration(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_iteration = READY_LOG.replace(
            "runtimeReflectionForEachPropertyCallbacks=1 selfTestReflectionForEachPropertyCallbacks=13",
            "runtimeReflectionForEachPropertyCallbacks=0 selfTestReflectionForEachPropertyCallbacks=14",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-reflection-for-each.log"
            log.write_text(self_test_iteration, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        runtime_gate = next(
            item for item in report["gates"] if item["name"] == "lua-reflection-for-each-property-runtime"
        )
        self.assertTrue(report["ready"]["luaReflectionForEachProperty"])
        self.assertFalse(runtime_gate["passed"])
        self.assertFalse(report["ready"]["luaReflectionForEachPropertyRuntime"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_reflection_live_descriptor_requires_runtime_typed_class(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        untyped_runtime_descriptor = READY_LOG.replace(
            "liveDescriptorTypedClassHits=2 runtimeLiveDescriptorTypedClassHits=2 selfTestLiveDescriptorTypedClassHits=0",
            "liveDescriptorTypedClassHits=1 runtimeLiveDescriptorTypedClassHits=0 selfTestLiveDescriptorTypedClassHits=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "untyped-live-descriptor.log"
            log.write_text(untyped_runtime_descriptor, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        runtime_gate = next(
            item for item in report["gates"] if item["name"] == "lua-reflection-live-descriptor-typed-class-runtime"
        )
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertFalse(runtime_gate["passed"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorTypedClassRuntime"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_reflection_live_descriptor_requires_runtime_typed_get_value(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_typed_value = READY_LOG.replace(
            "liveDescriptorTypedValueHits=2 runtimeLiveDescriptorTypedValueHits=2 selfTestLiveDescriptorTypedValueHits=0",
            "liveDescriptorTypedValueHits=1 runtimeLiveDescriptorTypedValueHits=0 selfTestLiveDescriptorTypedValueHits=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-typed-live-value.log"
            log.write_text(self_test_typed_value, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        runtime_gate = next(
            item for item in report["gates"] if item["name"] == "lua-reflection-live-descriptor-typed-values-runtime"
        )
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorTypedClassRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertFalse(runtime_gate["passed"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorTypedValuesRuntime"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_reflection_live_descriptor_requires_runtime_typed_set_value(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        self_test_typed_set_value = READY_LOG.replace(
            "liveDescriptorTypedValueSetHits=1 runtimeLiveDescriptorTypedValueSetHits=1 selfTestLiveDescriptorTypedValueSetHits=0",
            "liveDescriptorTypedValueSetHits=1 runtimeLiveDescriptorTypedValueSetHits=0 selfTestLiveDescriptorTypedValueSetHits=1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "self-test-typed-live-set-value.log"
            log.write_text(self_test_typed_set_value, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        runtime_gate = next(
            item for item in report["gates"] if item["name"] == "lua-reflection-live-descriptor-typed-set-values-runtime"
        )
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorTypedClassRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorTypedValuesRuntime"])
        self.assertTrue(report["ready"]["luaReflectionLiveDescriptorValuesRuntime"])
        self.assertFalse(runtime_gate["passed"])
        self.assertFalse(report["ready"]["luaReflectionLiveDescriptorTypedSetValuesRuntime"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_lua_dispatch_requires_scheduler_and_input_command_api_proof(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        without_api_family_counters = READY_LOG.replace(
            "executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2 "
            "executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 "
            "keyBindRegistrations=1 keyBindLookupCalls=2 keyBindLookupHits=1 "
            "keyBindDispatchCalls=2 keyBindCallbackCalls=1 keyBindCallbackHandled=1 "
            "keyBindUnregisterCalls=1 keyBindUnregisterHits=1 consoleCommandHandlers=2 "
            "consoleCommandGlobalHandlers=1 consoleCommandHandlerCalls=1 "
            "consoleCommandHandlerHandled=0 consoleCommandGlobalHandlerCalls=1 "
            "consoleCommandGlobalHandlerHandled=1 consoleCommandUnregisterCalls=1 "
            "consoleCommandUnregisterHits=1 ",
            "",
        )
        without_api_family_counters = without_api_family_counters.replace(
            "executeInGameThreadCalls=1 executeInGameThreadCallbacks=1 "
            "executeInGameThreadResult=9 executeInGameThreadIsNumber=true "
            "executeAsyncCalls=1 executeAsyncCallbacks=1 executeWithDelayCalls=2 "
            "executeWithDelayCallbacks=1 loopAsyncCalls=1 loopAsyncCallbacks=1 "
            "schedulerQueueDrains=1 schedulerCancelCalls=1 schedulerCancelHits=1 ",
            "",
        )
        without_api_family_counters = without_api_family_counters.replace(
            "keyBindLookupCalls=2 keyBindLookupHits=1 keyBindDispatchCalls=1 "
            "keyBindCallbackCalls=1 keyBindCallbackHandled=1 "
            "keyBindUnregisterCalls=2 keyBindUnregisterHits=2 "
            "consoleCommandHandlers=3 consoleCommandGlobalHandlers=1 "
            "consoleCommandHandlerCalls=3 consoleCommandHandlerHandled=3 "
            "consoleCommandGlobalHandlerCalls=3 consoleCommandGlobalHandlerHandled=0 "
            "consoleCommandUnregisterCalls=1 consoleCommandUnregisterHits=1 ",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-scheduler-input-command-api.log"
            log.write_text(without_api_family_counters, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        self.assertTrue(report["ready"]["luaRuntime"])
        self.assertFalse(report["ready"]["luaSchedulerApi"])
        self.assertFalse(report["ready"]["luaSchedulerApiMods"])
        self.assertFalse(report["ready"]["luaInputCommandApi"])
        self.assertFalse(report["ready"]["luaInputCommandApiMods"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_live_lua_hook_alias_routing_requires_alias_match_evidence(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "exact-only-routing.log"
            log.write_text(
                READY_LOG.replace("pathExactMatches=0 pathAliasMatches=2", "pathExactMatches=2 pathAliasMatches=0"),
                encoding="utf-8",
            )
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        alias_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-lua-hook-alias-routing")
        self.assertFalse(alias_gate["passed"])
        self.assertFalse(report["ready"]["ueProcessEventLuaHookAliasRouting"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_live_context_requires_scanned_ufunction_path_match(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "wrong-live-function-path.log"
            log.write_text(
                READY_LOG.replace(
                    "event=ue-process-event-live-context status=resolved call=1 object=0x140070000 objectResolved=true objectPath=/RuntimeProbe/GWorld objectClass=UObjectCandidate function=0x140082000 functionPath=/RuntimeProbe/GWorld.DecodedFunction_0:Function",
                    "event=ue-process-event-live-context status=resolved call=1 object=0x140070000 objectResolved=true objectPath=/RuntimeProbe/GWorld objectClass=UObjectCandidate function=0x140082000 functionPath=/RuntimeProbe/GWorld.UnscannedLiveFunction:Function",
                ),
                encoding="utf-8",
            )
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        path_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-live-function-path")
        self.assertFalse(path_gate["passed"])
        self.assertFalse(report["ready"]["ueProcessEventLiveFunctionPath"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_live_class_aware_param_values_require_promoted_registry_context(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-live-registry-context.log"
            log.write_text(
                READY_LOG.replace("event=ue-process-event-live-registry-context", "event=ue-process-event-live-registry-context-skipped"),
                encoding="utf-8",
            )
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        class_aware_gate = next(
            item for item in report["gates"] if item["name"] == "ue-process-event-live-class-aware-param-values"
        )
        self.assertFalse(class_aware_gate["passed"])
        self.assertFalse(report["ready"]["ueProcessEventLiveRegistryContext"])
        self.assertTrue(report["ready"]["ueProcessEventLuaParamAccessors"])
        self.assertFalse(report["ready"]["ueProcessEventLiveClassAwareParamValues"])
        self.assertFalse(report["ready"]["luaDispatch"])
        self.assertIn("promoted runtime ctx.Function registry identity", class_aware_gate["blocker"])

    def test_live_param_values_must_correlate_to_runtime_live_context(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        orphan_param_log = "\n".join(
            line.replace(" call=1 ", " call=99 ")
            if "event=ue-process-event-live-param " in line
            else line
            for line in READY_LOG.splitlines()
        ) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "orphan-live-process-event-params.log"
            log.write_text(orphan_param_log, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        scan = summary["scan"]
        self.assertEqual(scan["readUeProcessEventLiveParamCount"], 1)
        self.assertEqual(scan["rawUeProcessEventLiveParamCount"], 1)
        self.assertEqual(scan["containerUeProcessEventLiveParamCount"], 3)
        self.assertEqual(scan["runtimeReadUeProcessEventLiveParamCount"], 0)
        self.assertEqual(scan["runtimeRawUeProcessEventLiveParamCount"], 0)
        self.assertEqual(scan["runtimeContainerUeProcessEventLiveParamCount"], 0)
        self.assertTrue(report["ready"]["ueProcessEventLiveRuntimeContext"])
        self.assertFalse(report["ready"]["ueProcessEventLiveParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveRawParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveArrayContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveSetContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveMapContainerParamValues"])
        self.assertFalse(report["ready"]["ueProcessEventLiveContainerDataSamples"])
        self.assertFalse(report["ready"]["luaDispatch"])
        param_gate = next(item for item in report["gates"] if item["name"] == "ue-process-event-live-param-values")
        self.assertIn("matched live call/function", param_gate["blocker"])

    def test_lua_process_event_container_storage_layout_methods_are_required(self):
        validation = {
            "patternCount": 2,
            "promotableCount": 2,
            "statusCounts": {"unique-expected": 2},
        }
        without_storage_layout = READY_LOG.replace(" luaContainerStorageLayoutHits=9", "").replace(
            " containerStorageLayoutHits=9",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "missing-container-storage-layout.log"
            log.write_text(without_storage_layout, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report([summary], [validation])

        gate = next(
            item for item in report["gates"]
            if item["name"] == "ue-process-event-container-storage-layout-methods"
        )
        self.assertFalse(gate["passed"])
        self.assertFalse(report["ready"]["ueProcessEventContainerStorageLayoutMethods"])
        self.assertFalse(report["ready"]["luaDispatch"])

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "partial.log"
            validation = Path(tmp) / "validation.json"
            anchor_coverage = Path(tmp) / "anchor-coverage.json"
            log.write_text(PARTIAL_LOG, encoding="utf-8")
            validation.write_text(
                json.dumps({"patternCount": 1, "promotableCount": 1, "statusCounts": {"unique-unexpected": 1}}),
                encoding="utf-8",
            )
            anchor_coverage.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue-anchor-coverage/v1",
                        "explicitAnchors": ["FNamePool", "GWorld", "ProcessEvent"],
                        "signatureAnchors": ["GUObjectArray"],
                        "combinedAnchors": ["FNamePool", "GUObjectArray", "GWorld", "ProcessEvent"],
                        "groups": {
                            "names": {"present": 1, "total": 2},
                            "objects": {"present": 1, "total": 2},
                            "world": {"present": 1, "total": 1},
                            "dispatch": {"present": 1, "total": 2},
                        },
                        "missingRequiredGroups": [],
                        "readyForObjectDiscovery": True,
                        "readyForHookPlanning": True,
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--client-log",
                    str(log),
                    "--loader",
                    "win-client",
                    "--signature-validation-json",
                    str(validation),
                    "--anchor-coverage-json",
                    str(anchor_coverage),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        report = json.loads(result.stdout)
        self.assertEqual(report["schemaVersion"], "dune-ue4ss-port-readiness/v1")
        self.assertTrue(report["signatures"]["allPromotable"])
        self.assertFalse(report["signatures"]["exactOnly"])
        self.assertTrue(report["anchorCoverage"]["provided"])
        self.assertTrue(report["ready"]["anchorCoverageObjectDiscovery"])
        self.assertTrue(report["ready"]["anchorCoverageHookPlanning"])
        self.assertEqual(report["anchorCoverage"]["combinedAnchorCount"], 4)

    def test_legacy_anchor_coverage_groups_derive_non_target_readiness(self):
        coverage = {
            "schemaVersion": "dune-ue-anchor-coverage/v1",
            "groups": {
                "names": {"present": 1, "total": 2},
                "objects": {"present": 1, "total": 2},
                "world": {"present": 1, "total": 1},
                "dispatch": {"present": 1, "total": 2},
                "package": {"present": 1, "total": 4},
            },
            "missingRequiredGroups": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready.log"
            log.write_text(READY_LOG, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [coverage],
            )

        self.assertTrue(report["anchorCoverage"]["provided"])
        self.assertTrue(report["anchorCoverage"]["readyForObjectDiscovery"])
        self.assertTrue(report["anchorCoverage"]["readyForHookPlanning"])
        self.assertTrue(report["anchorCoverage"]["readyForPackageLoading"])
        self.assertFalse(report["anchorCoverage"]["targetCoverageFieldsPresent"])
        self.assertTrue(report["ready"]["anchorCoverageObjectDiscovery"])
        self.assertTrue(report["ready"]["anchorCoverageHookPlanning"])

    def test_target_anchor_coverage_fields_gate_live_target_readiness(self):
        coverage = ready_anchor_coverage()
        coverage.update(
            {
                "readyForTargetObjectDiscovery": False,
                "readyForTargetHookPlanning": False,
                "readyForTargetPackageLoading": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready.log"
            log.write_text(READY_LOG, encoding="utf-8")
            anchor_coverage = Path(tmp) / "anchor-coverage.json"
            anchor_coverage.write_text(json.dumps(coverage), encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            loaded_coverage = json.loads(anchor_coverage.read_text(encoding="utf-8"))
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [loaded_coverage],
            )

        self.assertTrue(report["anchorCoverage"]["readyForObjectDiscovery"])
        self.assertFalse(report["anchorCoverage"]["readyForTargetObjectDiscovery"])
        self.assertFalse(report["ready"]["anchorCoverageObjectDiscovery"])
        self.assertFalse(report["ready"]["anchorCoverageHookPlanning"])
        self.assertFalse(report["ready"]["anchorCoveragePackageLoading"])
        live_group = report["liveTargetImageCanaryContract"]["groups"]["targetImageAnchors"]
        self.assertIn("anchorCoverageObjectDiscovery", live_group["missingKeys"])
        self.assertIn("anchorCoverageHookPlanning", live_group["missingKeys"])
        self.assertIn("anchorCoveragePackageLoading", live_group["missingKeys"])

    def test_target_object_discovery_accepts_target_dispatch_from_anchor_coverage_sidecar(self):
        coverage = ready_anchor_coverage()
        coverage.update(
            {
                "readyForTargetObjectDiscovery": True,
                "readyForTargetHookPlanning": True,
                "readyForTargetPackageLoading": False,
                "targetCoverageFieldsPresent": True,
            }
        )
        log_without_dispatch = "\n".join(
            line
            for line in READY_LOG.splitlines()
            if " name=ProcessEvent " not in line
            and " group=dispatch " not in line
            and "event=ue-process-event-hook" not in line
            and "event=ue-process-event-live-hook" not in line
            and "event=ue-process-event-dispatch" not in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready.log"
            log.write_text(log_without_dispatch, encoding="utf-8")
            inventory = Path(tmp) / "ue4ss-evidence-inventory.json"
            inventory.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-evidence-inventory/v1",
                        "best": {"anchorCoverage": coverage},
                    }
                ),
                encoding="utf-8",
            )
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [readiness.normalize_anchor_coverage_sidecar(json.loads(inventory.read_text(encoding="utf-8")))],
            )

        self.assertFalse(report["ready"]["targetDispatch"])
        self.assertTrue(report["ready"]["anchorCoverageHookPlanning"])
        self.assertTrue(report["ready"]["targetObjectDiscovery"])
        self.assertFalse(report["ready"]["targetHooks"])

    def test_anchor_coverage_report_preserves_loader_provenance_counts(self):
        coverage = ready_anchor_coverage()
        coverage.update(
            {
                "readyForTargetObjectDiscovery": False,
                "readyForTargetHookPlanning": False,
                "readyForTargetPackageLoading": False,
                "groups": {
                    "names": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                    "objects": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                    "world": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                    "dispatch": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                    "package": {"present": 1, "targetPresent": 0, "loaderPresent": 1, "unknownPresent": 0, "total": 1},
                },
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "ready.log"
            log.write_text(READY_LOG, encoding="utf-8")
            summary = readiness.summarize_log(log, ["win-client"], [], [])
            report = readiness.build_report(
                [summary],
                [{"patternCount": 2, "promotableCount": 2, "statusCounts": {"unique-expected": 2}}],
                [coverage],
            )

        self.assertFalse(report["ready"]["anchorCoverageObjectDiscovery"])
        self.assertEqual(report["anchorCoverage"]["groups"]["objects"]["targetPresent"], 0)
        self.assertEqual(report["anchorCoverage"]["groups"]["objects"]["loaderPresent"], 1)
        self.assertFalse(report["anchorCoverage"]["groups"]["objects"]["targetComplete"])
        object_gate = next(item for item in report["gates"] if item["name"] == "anchor-coverage-object-discovery")
        self.assertFalse(object_gate["passed"])
        self.assertIn("'loaderPresent': 1", object_gate["evidence"])

    def test_cli_rejects_empty_runtime_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "empty.log"
            log.write_text("", encoding="utf-8")
            result = subprocess.run(
                ["python3", str(SCRIPT), "--server-log", str(log), "--format", "json"],
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime log must not be empty", result.stderr)

    def test_cli_rejects_special_device_runtime_log(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "--server-log", "/dev/null", "--format", "json"],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime log must be a regular file", result.stderr)


if __name__ == "__main__":
    unittest.main()
