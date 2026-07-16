#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
log="${DUNE_WIN_CLIENT_PROBE_SMOKE_LOG:-/tmp/dune-win-client-probe-smoke.log}"
loader="${DUNE_WINDOWS_CLIENT_PRELOAD:-$repo_root/build/windows-client-loader/dune_win_client_probe_loader.dll}"

if ! command -v wine >/dev/null 2>&1; then
  echo "wine is required for the Windows client loader smoke test" >&2
  exit 1
fi
if ! command -v winepath >/dev/null 2>&1; then
  echo "winepath is required for the Windows client loader smoke test" >&2
  exit 1
fi

"$repo_root/scripts/build-windows-client-loader.sh" >/dev/null

rm -f "$log"
signature_file="$(mktemp)"
mod_root="$(mktemp -d)"
sidecar_tmp=""
trap 'rm -f "$signature_file"; rm -rf "$mod_root"; if [ -n "$sidecar_tmp" ]; then rm -rf "$sidecar_tmp"; fi' EXIT
printf 'mz-file=4d 5a\n' >"$signature_file"
mkdir -p "$mod_root/CallbackMod/Scripts"
printf "%s\n" "local o=FindObject('SelfTestObject'); local decoded=FindObject('SelfTestUObjectName_0'); local shaped=StaticFindObject(nil,nil,'SelfTestObject'); local all=GetKnownObjects(); local matches=FindObjects('DuneProbeSelfTestClass'); local allOf=FindAllOf('DuneProbeSelfTestClass'); local asset=LoadAsset('/Script/DuneProbe.SelfTestObject'); local cls=o and o:GetClass(); local methodOk=o and cls and o:GetName()=='SelfTestObject' and o:GetPathName()==o.PathName and o:GetAddress()==o.Address and o:IsValid() and o:GetFullName()=='DuneProbeSelfTestClass /Script/DuneProbe.SelfTestObject' and o:type()=='UObject' and o:GetFName()=='SelfTestObject' and o:GetOuter()==nil and o:GetWorld()==nil and cls.Name=='DuneProbeSelfTestClass' and cls.ClassName=='UClass' and cls:type()=='UClass' and not cls:IsValid() and o:HasAllFlags(0) and not o:HasAnyFlags(1) and not o:HasAnyInternalFlags(1); local async=0; local asyncId=ExecuteAsync(function() async=async+1 end); local delayId=ExecuteWithDelay(1,function() async=async+1 end); local drainedScheduler=DrainSchedulerQueue(); local fn=FName('ModProbe'); local ft=FText('ModText'); local compatOk=async==2 and asyncId and delayId and drainedScheduler==2 and fn.Name=='ModProbe' and ft.Text=='ModText' and RegisterConsoleCommandHandler('probe',function() return true end); local seen=0; ForEachUObject(function(x) if x and IsA(x,'DuneProbeSelfTestClass') then seen=seen+1 end end); local up,uq=RegisterHook('/Script/DuneProbe.TempMod:Function',function()return -1 end,function()return -1 end); local unregOk=up and uq and uq==up+1; UnregisterHook('/Script/DuneProbe.TempMod:Function',up,uq); if not (o and shaped and shaped.Address==o.Address and decoded and asset and asset.Address==o.Address and methodOk and compatOk and unregOk and decoded.PathName=='/RuntimeProbe/SelfTestUObjectName_0' and all and all.Count and all.Count >= 1 and all[o.PathName] and all[decoded.PathName] and matches and matches.Count and matches.Count >= 1 and allOf and allOf.Count and allOf.Count >= 1 and seen >= 1 and IsA(o,'UObject')) then error('missing object registry') end; local path='/Script/SelfTestUObject.SelfTestUObjectName_0:Function'; local f=FindFunction(path); local first=FindFirstFunction(); local known=GetKnownFunctions(); if not (f and first and known and known.Count and known.Count >= 1 and known[path] and known[path].Address == f.Address and f:GetName()=='SelfTestUObjectName_0' and f:type()=='UFunction') then error('missing function registry') end; RegisterHook('/Script/DuneProbe.ModEntry:Function', function() return 11 end, function() return 31 end)" >"$mod_root/CallbackMod/Scripts/main.lua"
dll_win="$(WINEDEBUG=-all winepath -w "$loader" 2>/dev/null)"
log_win="$(WINEDEBUG=-all winepath -w "$log" 2>/dev/null)"
signature_file_win="$(WINEDEBUG=-all winepath -w "$signature_file" 2>/dev/null)"
mod_root_win="$(WINEDEBUG=-all winepath -w "$mod_root" 2>/dev/null)"

WINEDEBUG=-all \
DUNE_WIN_CLIENT_PROBE_LOG="$log_win" \
DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=0 \
DUNE_WIN_CLIENT_PROBE_LOG_MODULES=true \
DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=true \
DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS= \
DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS='rundll32.exe' \
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES='mz=4d 5a' \
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE="$signature_file_win" \
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES='MzAnchor=4d 5a;MzHeaderByte@hit+1=4d 5a' \
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE="$signature_file_win" \
DUNE_WIN_CLIENT_PROBE_UE_ANCHORS='BadAnchor=0x1' \
DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_SLOTS=2 \
DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=true \
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS=4 \
DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_SELF_TEST_ANCHOR=true \
DUNE_WIN_CLIENT_PROBE_HOOK_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_MOD_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_LUA_DLL='Z:\definitely\missing\lua54.dll' \
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=true \
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=2 \
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=2 \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false \
DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED=true \
DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT="$mod_root_win" \
DUNE_WIN_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=true \
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=4 \
  wine rundll32.exe "$dll_win,DuneWinClientProbeSmoke" >/tmp/dune-win-client-probe-smoke.out 2>&1

WINEDEBUG=-all \
DUNE_WIN_CLIENT_PROBE_LOG="$log_win" \
DUNE_WIN_CLIENT_PROBE_AUTO_THREAD=false \
  wine rundll32.exe "$dll_win,DuneWinClientProbeForwardSmoke" >>/tmp/dune-win-client-probe-smoke.out 2>&1

require_log() {
  local pattern="$1"
  if ! grep -q "$pattern" "$log"; then
    echo "missing expected Windows client probe log pattern: $pattern" >&2
    sed -n '1,220p' "$log" >&2 || true
    sed -n '1,120p' /tmp/dune-win-client-probe-smoke.out >&2 || true
    exit 1
  fi
}

require_log 'event=loaded'
require_log 'event=module'
require_log 'event=scan-start'
require_log 'event=signature-file'
require_log 'event=scan-hit kind=signature name=mz'
require_log 'event=scan-hit kind=signature name=mz-file'
require_log 'event=scan-hit kind=string name=rundll32.exe'
require_log 'event=scan-finish'
require_log 'event=ue-anchor-signature-start'
require_log 'event=ue-anchor-signature name=MzAnchor group=unknown status=resolved'
require_log 'event=ue-anchor-signature name=MzHeaderByte group=unknown status=resolved.*transform=hit+1'
require_log 'event=ue-anchor-signature name=mz-file group=unknown status=resolved'
require_log 'event=ue-anchor-start'
require_log 'event=ue-anchor name=MzAnchor group=unknown status=mapped'
require_log 'event=ue-anchor name=MzHeaderByte group=unknown status=mapped'
require_log 'event=ue-anchor name=BadAnchor group=unknown status=unmapped'
require_log 'event=ue-anchor-finish'
require_log 'event=ue-pointer-start'
require_log 'event=ue-pointer name=BadAnchor status=anchor-unmapped'
require_log 'event=ue-pointer name=SelfTest status=target-mapped'
require_log 'event=ue-pointer-finish'
require_log 'event=ue-layout-start'
require_log 'event=ue-layout name=SelfTest status=target-readable'
require_log 'event=ue-layout-slot name=SelfTest.*status=target-mapped'
require_log 'event=ue-layout-slot name=SelfTest.*status=null'
require_log 'event=ue-layout-finish'
require_log 'event=ue-uobject-start'
require_log 'event=ue-uobject name=SelfTestUObject status=candidate'
require_log 'event=ue-uobject name=SelfTestUObject.*classMapped=true'
require_log 'event=lua-object-registry source=ue-uobject status=added name=SelfTestUObject path=/RuntimeProbe/SelfTestUObject class=SelfTestUObjectName_0'
require_log 'event=lua-object-registry-check source=ue-uobject status=passed name=SelfTestUObject path=/RuntimeProbe/SelfTestUObject class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_log 'event=lua-object-registry source=ue-uobject-fname status=added name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 aliasOf=SelfTestUObject class=SelfTestUObjectName_0'
require_log 'event=lua-object-registry-check source=ue-uobject-fname status=passed name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_log 'event=lua-function-registry-check source=ue-function-param status=passed name=SelfTestUObjectName_0 path=/Script/SelfTestUObject.SelfTestUObjectName_0:Function runtimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function .*pathHit=true runtimePathHit=true nameHit=true addressHit=true flagsHit=true'
require_log 'event=ue-uobject-finish'
require_log 'event=ue-reflection-start'
require_log 'event=ue-reflection name=SelfTestUObject status=class-mapped'
require_log 'event=ue-fname source=ue-reflection-class objectName=SelfTestUObject status=decoded .*decoded=SelfTestUObjectName_0'
require_log 'event=ue-reflection-slot name=SelfTestUObject slot=children .*status=target-mapped'
require_log 'event=ue-reflection-slot name=SelfTestUObject slot=propertyLink .*status=target-mapped'
require_log 'event=ue-reflection-slot name=SelfTestUObject slot=functionLink .*status=target-mapped'
require_log 'event=ue-reflection-field name=SelfTestUObject chain=children index=0 .*status=candidate'
require_log 'event=ue-reflection-field name=SelfTestUObject chain=propertyLink index=0 .*status=candidate'
require_log 'event=ue-reflection-field name=SelfTestUObject chain=functionLink index=0 .*status=candidate'
require_log 'event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=childProperties status=root'
require_log 'event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=propertyLink status=root'
require_log 'event=ue-function-native-identity source=ue-function-param status=promoted name=SelfTestUObject functionIndex=0 chain=childProperties .*functionName=SelfTestUObjectName_0 .*functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function .*functionFlags=0x400 functionFlagsReadable=true'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate .*functionName=SelfTestUObjectName_0 .*functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function'
require_log 'event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=childProperties status=root .*functionFlags=0x400 functionFlagsReadable=true'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate .*functionFlags=0x400 functionFlagsReadable=true'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate .*fieldClassName=FIntProperty .*fieldName=Value .*offsetInternal=0'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=2 status=candidate .*fieldClassName=FIntProperty .*fieldName=Touched .*offsetInternal=8'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=3 status=candidate .*fieldClassName=FNameProperty .*fieldName=NameToken .*offsetInternal=56'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=4 status=candidate .*fieldClassName=FStrProperty .*fieldName=Message .*offsetInternal=64'
require_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=5 status=candidate .*fieldClassName=FStructProperty .*fieldName=Location .*offsetInternal=80'
require_log 'event=ue-reflection-property name=SelfTestUObject chain=childProperties index=0 .*status=candidate .*arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12'
require_log 'event=ue-reflection-property name=SelfTestUObject chain=propertyLink index=0 .*status=candidate .*arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12'
require_log 'event=ue-reflection-value name=SelfTestUObject chain=childProperties index=0 fieldName=SelfTestUObjectName_0 .*descriptorProvenance=self-test .*status=read .*offsetInternal=12 elementSize=4 arrayDim=1 .*readBytes=4 raw=07000000 rawLe=0x7'
require_log 'event=ue-reflection-value name=SelfTestUObject chain=propertyLink index=0 fieldName=SelfTestUObjectName_0 .*descriptorProvenance=self-test .*status=read .*offsetInternal=12 elementSize=4 arrayDim=1 .*readBytes=4 raw=07000000 rawLe=0x7'
require_log 'event=ue-fname source=ue-reflection-field objectName=SelfTestUObject.children_0 status=decoded .*decoded=SelfTestUObjectName_0'
require_log 'event=ue-reflection-finish'
require_log 'event=ue-fname-start .*status=ready.*source=SelfTestFNamePool:direct'
require_log 'event=ue-fname source=ue-uobject objectName=SelfTestUObject status=decoded .*decoded=SelfTestUObjectName_0'
require_log 'event=ue-object-array-start'
require_log 'event=ue-object-array name=SelfTestObjectArray mode=indirect status=scanning'
require_log 'event=ue-fname source=ue-object-array objectName=SelfTestObjectArray_0 status=decoded .*decoded=SelfTestUObjectName_0'
require_log 'event=ue-object-native-identity source=ue-uobject status=promoted .*name=SelfTestUObjectName_0 .*className=SelfTestUObjectName_0 .*outer=0x0 nameDecoded=true classNameDecoded=true'
require_log 'event=ue-object-native-identity source=ue-object-array status=promoted .*name=SelfTestUObjectName_0 .*className=SelfTestUObjectName_0 .*outer=0x0 nameDecoded=true classNameDecoded=true'
require_log 'event=lua-object-registry source=ue-object-array-fname status=skipped name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 aliasOf=SelfTestObjectArray_0 class=SelfTestUObjectName_0'
require_log 'event=lua-object-registry-check source=ue-object-array-fname status=passed name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_log 'event=lua-object-registry source=ue-object-array status=added name=SelfTestObjectArray_0 path=/RuntimeProbe/SelfTestObjectArray_0 class=SelfTestUObjectName_0'
require_log 'event=lua-object-registry-check source=ue-object-array status=passed name=SelfTestObjectArray_0 path=/RuntimeProbe/SelfTestObjectArray_0 class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_log 'event=ue-object-array-item name=SelfTestObjectArray index=0 status=registered .*outer=0x0'
require_log 'event=ue-object-array name=SelfTestObjectArray mode=indirect status=finished .*registered=2'
require_log 'event=ue-object-array-finish'
require_log 'event=ue-fname-finish .*status=ready.*source=SelfTestFNamePool:direct'
require_log 'event=hook-dispatch name=SelfTestHook status=installed'
require_log 'event=hook-dispatch name=SelfTestHook status=restored'
require_log 'event=hook-dispatch-self-test phase=.* status=passed'
require_log 'event=hook-dispatch-self-test .*original=42 callbacks=2 preCallbacks=1 postCallbacks=1'
require_log 'event=mod-dispatch-self-test phase=.* status=passed'
require_log 'event=mod-dispatch-self-test .*mods=1 loaded=1 unloaded=1 result=1042 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 loadCallbacks=1 unloadCallbacks=1'
require_log 'event=lua-dispatch-self-test phase=.* status=library-missing'
require_log 'event=lua-reflection-self-test phase=.* status=library-missing'
require_log 'event=ue-process-event-hook phase=.* status=target-mapped .*selfTestTarget=true install=true'
require_log 'event=hook-dispatch name=ProcessEventHookProbe status=installed'
require_log 'event=hook-dispatch name=ProcessEventHookProbe status=restored'
require_log 'event=ue-process-event-hook phase=.* status=passed .*installed=true restored=true selfTestTarget=true .*callSelfTest=true liveCalls=1 originalCalls=1 paramsResult=62 paramsTouched=1'
require_log 'event=ue-call-function-hook phase=.* status=target-mapped .*selfTestTarget=true install=true'
require_log 'event=hook-dispatch name=CallFunctionHookProbe status=installed'
require_log 'event=hook-dispatch name=CallFunctionHookProbe status=restored'
require_log 'event=ue-call-function-hook phase=.* status=passed .*installed=true restored=true selfTestTarget=true .*callSelfTest=true before=42 after=1042 final=42 original=42'
require_log 'event=ue-call-function-live-hook phase=.* status=target-mapped .*selfTestTarget=true logCalls=true callLogLimit=2'
require_log 'event=hook-dispatch name=CallFunctionLiveHook status=installed'
require_log 'event=ue-call-function-live-hook-call status=entered call=1'
require_log 'event=ue-call-function-live-hook-call status=returned call=1 originalCalled=true .*result=42'
require_log 'event=ue-call-function-live-hook phase=.* status=installed .*selfTestTarget=true .*callSelfTest=true .*liveCalls=1 originalCalls=1 result=42'
require_log 'event=lua-process-event-self-test phase=.* status=library-missing'
require_log 'event=lua-mod-finish phase=.* status=library-missing'
require_log 'event=ue-process-event-dispatch-self-test phase=.* status=armed .*callbacks=2'
require_log 'event=ue-process-event-live-hook phase=.* status=target-mapped .*selfTestTarget=true logCalls=true callLogLimit=2'
require_log 'event=hook-dispatch name=ProcessEventLiveHook status=installed'
require_log 'event=ue-process-event-live-hook-call status=entered call=1'
require_log 'event=ue-process-event-live-hook-call status=returned call=1 originalCalled=true originalSuppressed=false preCallbacks=1 postCallbacks=1'
require_log 'event=ue-process-event-live-registry-context status=resolved .*objectResolved=true objectNativeIdentity=true .*functionResolved=true functionNativeIdentity=true .*functionParamDescriptors=[1-9][0-9]* .*paramsPresent=true'
require_log 'event=ue-process-event-live-hook phase=.*status=installed .*selfTestTarget=true .*callSelfTest=true dispatchCallbacks=2 luaDispatch=false .*preCallbacks=1 postCallbacks=1 liveCalls=2 originalCalls=2 .*paramsResult=62 paramsTouched=1'
require_log 'event=ue-process-event-live-param status=raw .*param=Location className=FStructProperty type=vector .*value=rawHex='
require_log 'event=ue-process-event-live-param status=container .*param=NumberArray className=FArrayProperty type=array .*value=kind=FScriptArray'
require_log 'event=ue-process-event-live-param status=container .*param=NumberSet className=FSetProperty type=set .*value=kind=FScriptSetHeader'
require_log 'event=ue-process-event-live-param status=container .*param=NumberMap className=FMapProperty type=map .*value=kind=FScriptMapHeader'
require_log 'event=hook-dispatch name=ProcessEventLiveHook status=restored'
require_log 'event=hook-dispatch name=CallFunctionLiveHook status=restored'
require_log 'event=ue-call-function-live-hook phase=detach status=restored .*liveCalls=1 originalCalls=1'
require_log 'event=ue-process-event-live-hook phase=detach status=restored .*liveCalls=2 originalCalls=2'
require_log 'event=forward-smoke function=GetFileVersionInfoSizeW result='

if grep -q 'event=forward-smoke function=GetFileVersionInfoSizeW result=0' "$log"; then
  echo "Windows version.dll forwarding smoke returned zero" >&2
  sed -n '1,220p' "$log" >&2
  exit 1
fi

sidecar_tmp="$(mktemp -d)"
sidecar_loader="$sidecar_tmp/version.dll"
sidecar_log="${DUNE_WIN_CLIENT_PROBE_SIDECAR_SMOKE_LOG:-/tmp/dune-win-client-probe-sidecar-smoke.log}"
sidecar_signature_file="$sidecar_tmp/signatures.txt"
cp "$loader" "$sidecar_loader"
printf 'mz-file=4d 5a\n' >"$sidecar_signature_file"
rm -f "$sidecar_log"
sidecar_dll_win="$(WINEDEBUG=-all winepath -w "$sidecar_loader" 2>/dev/null)"
sidecar_log_win="$(WINEDEBUG=-all winepath -w "$sidecar_log" 2>/dev/null)"
sidecar_signature_file_win="$(WINEDEBUG=-all winepath -w "$sidecar_signature_file" 2>/dev/null)"
cat > "$sidecar_tmp/dune-win-client-probe.env" <<EOF
DUNE_WIN_CLIENT_PROBE_LOG=$sidecar_log_win
DUNE_WIN_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=0
DUNE_WIN_CLIENT_PROBE_LOG_MODULES=true
DUNE_WIN_CLIENT_PROBE_SCAN_ENABLED=true
DUNE_WIN_CLIENT_PROBE_SCAN_PRESETS=
DUNE_WIN_CLIENT_PROBE_SCAN_STRINGS=rundll32.exe
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES=mz=4d 5a
DUNE_WIN_CLIENT_PROBE_SCAN_SIGNATURES_FILE=$sidecar_signature_file_win
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES=MzAnchor=4d 5a;MzHeaderByte@hit+1=4d 5a
DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=$sidecar_signature_file_win
DUNE_WIN_CLIENT_PROBE_UE_ANCHORS=BadAnchor=0x1
DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_SLOTS=2
DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_FIELD_WALK=true
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_PROPERTY_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_REFLECTION_VALUE_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_MAX_OBJECTS=4
DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_SELF_TEST_ANCHOR=true
DUNE_WIN_CLIENT_PROBE_HOOK_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_MOD_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_LUA_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_LUA_DLL=Z:\definitely\missing\lua54.dll
DUNE_WIN_CLIENT_PROBE_LUA_REFLECTION_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_INSTALL=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_PROBE=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_INSTALL=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=true
DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=2
DUNE_WIN_CLIENT_PROBE_LUA_PROCESS_EVENT_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=2
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_WIN_CLIENT_PROBE_LUA_MODS_ENABLED=true
DUNE_WIN_CLIENT_PROBE_LUA_MOD_ROOT=$mod_root_win
DUNE_WIN_CLIENT_PROBE_LUA_MOD_DISPATCH_SELF_TEST=true
DUNE_WIN_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=4
DUNE_WIN_CLIENT_PROBE_AUTO_THREAD=false
EOF

WINEDEBUG=-all \
  wine rundll32.exe "$sidecar_dll_win,DuneWinClientProbeSmoke" >>/tmp/dune-win-client-probe-smoke.out 2>&1

require_sidecar_log() {
  local pattern="$1"
  if ! grep -q "$pattern" "$sidecar_log"; then
    echo "missing expected Windows client sidecar smoke log pattern: $pattern" >&2
    sed -n '1,220p' "$sidecar_log" >&2 || true
    sed -n '1,160p' /tmp/dune-win-client-probe-smoke.out >&2 || true
    exit 1
  fi
}

require_sidecar_log 'event=loaded.*config=.*dune-win-client-probe.env'
require_sidecar_log 'event=scan-start'
require_sidecar_log 'event=signature-file'
require_sidecar_log 'event=scan-hit kind=signature name=mz'
require_sidecar_log 'event=scan-hit kind=signature name=mz-file'
require_sidecar_log 'event=scan-hit kind=string name=rundll32.exe'
require_sidecar_log 'event=scan-finish'
require_sidecar_log 'event=ue-anchor-signature-start'
require_sidecar_log 'event=ue-anchor-signature name=MzAnchor group=unknown status=resolved'
require_sidecar_log 'event=ue-anchor-signature name=MzHeaderByte group=unknown status=resolved.*transform=hit+1'
require_sidecar_log 'event=ue-anchor-signature name=mz-file group=unknown status=resolved'
require_sidecar_log 'event=ue-anchor-start'
require_sidecar_log 'event=ue-anchor name=MzAnchor group=unknown status=mapped'
require_sidecar_log 'event=ue-anchor name=MzHeaderByte group=unknown status=mapped'
require_sidecar_log 'event=ue-anchor name=BadAnchor group=unknown status=unmapped'
require_sidecar_log 'event=ue-anchor-finish'
require_sidecar_log 'event=ue-pointer-start'
require_sidecar_log 'event=ue-pointer name=BadAnchor status=anchor-unmapped'
require_sidecar_log 'event=ue-pointer name=SelfTest status=target-mapped'
require_sidecar_log 'event=ue-pointer-finish'
require_sidecar_log 'event=ue-layout-start'
require_sidecar_log 'event=ue-layout name=SelfTest status=target-readable'
require_sidecar_log 'event=ue-layout-slot name=SelfTest.*status=target-mapped'
require_sidecar_log 'event=ue-layout-slot name=SelfTest.*status=null'
require_sidecar_log 'event=ue-layout-finish'
require_sidecar_log 'event=ue-uobject-start'
require_sidecar_log 'event=ue-uobject name=SelfTestUObject status=candidate'
require_sidecar_log 'event=ue-uobject name=SelfTestUObject.*classMapped=true'
require_sidecar_log 'event=lua-object-registry source=ue-uobject status=added name=SelfTestUObject path=/RuntimeProbe/SelfTestUObject class=SelfTestUObjectName_0'
require_sidecar_log 'event=lua-object-registry-check source=ue-uobject status=passed name=SelfTestUObject path=/RuntimeProbe/SelfTestUObject class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_sidecar_log 'event=lua-object-registry source=ue-uobject-fname status=added name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 aliasOf=SelfTestUObject class=SelfTestUObjectName_0'
require_sidecar_log 'event=lua-object-registry-check source=ue-uobject-fname status=passed name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_sidecar_log 'event=lua-function-registry-check source=ue-function-param status=passed name=SelfTestUObjectName_0 path=/Script/SelfTestUObject.SelfTestUObjectName_0:Function runtimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function .*pathHit=true runtimePathHit=true nameHit=true addressHit=true flagsHit=true'
require_sidecar_log 'event=ue-uobject-finish'
require_sidecar_log 'event=ue-reflection-start'
require_sidecar_log 'event=ue-reflection name=SelfTestUObject status=class-mapped'
require_sidecar_log 'event=ue-fname source=ue-reflection-class objectName=SelfTestUObject status=decoded .*decoded=SelfTestUObjectName_0'
require_sidecar_log 'event=ue-reflection-slot name=SelfTestUObject slot=children .*status=target-mapped'
require_sidecar_log 'event=ue-reflection-slot name=SelfTestUObject slot=propertyLink .*status=target-mapped'
require_sidecar_log 'event=ue-reflection-slot name=SelfTestUObject slot=functionLink .*status=target-mapped'
require_sidecar_log 'event=ue-reflection-field name=SelfTestUObject chain=children index=0 .*status=candidate'
require_sidecar_log 'event=ue-reflection-field name=SelfTestUObject chain=propertyLink index=0 .*status=candidate'
require_sidecar_log 'event=ue-reflection-field name=SelfTestUObject chain=functionLink index=0 .*status=candidate'
require_sidecar_log 'event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=childProperties status=root'
require_sidecar_log 'event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=propertyLink status=root'
require_sidecar_log 'event=ue-function-native-identity source=ue-function-param status=promoted name=SelfTestUObject functionIndex=0 chain=childProperties .*functionName=SelfTestUObjectName_0 .*functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function .*functionFlags=0x400 functionFlagsReadable=true'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate .*functionName=SelfTestUObjectName_0 .*functionPath=/Script/SelfTestUObject.SelfTestUObjectName_0:Function functionRuntimePath=/RuntimeProbe/SelfTestUObject.SelfTestUObjectName_0:Function'
require_sidecar_log 'event=ue-function-param-root name=SelfTestUObject functionIndex=0 chain=childProperties status=root .*functionFlags=0x400 functionFlagsReadable=true'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate .*functionFlags=0x400 functionFlagsReadable=true'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=childProperties index=0 status=candidate .*fieldClassName=FIntProperty .*fieldName=Value .*offsetInternal=0'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=2 status=candidate .*fieldClassName=FIntProperty .*fieldName=Touched .*offsetInternal=8'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=3 status=candidate .*fieldClassName=FNameProperty .*fieldName=NameToken .*offsetInternal=56'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=4 status=candidate .*fieldClassName=FStrProperty .*fieldName=Message .*offsetInternal=64'
require_sidecar_log 'event=ue-function-param name=SelfTestUObject functionIndex=0 chain=propertyLink index=5 status=candidate .*fieldClassName=FStructProperty .*fieldName=Location .*offsetInternal=80'
require_sidecar_log 'event=ue-reflection-property name=SelfTestUObject chain=childProperties index=0 .*status=candidate .*arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12'
require_sidecar_log 'event=ue-reflection-property name=SelfTestUObject chain=propertyLink index=0 .*status=candidate .*arrayDim=1 elementSize=4 propertyFlags=0x1 offsetInternal=12'
require_sidecar_log 'event=ue-reflection-value name=SelfTestUObject chain=childProperties index=0 fieldName=SelfTestUObjectName_0 .*descriptorProvenance=self-test .*status=read .*offsetInternal=12 elementSize=4 arrayDim=1 .*readBytes=4 raw=07000000 rawLe=0x7'
require_sidecar_log 'event=ue-reflection-value name=SelfTestUObject chain=propertyLink index=0 fieldName=SelfTestUObjectName_0 .*descriptorProvenance=self-test .*status=read .*offsetInternal=12 elementSize=4 arrayDim=1 .*readBytes=4 raw=07000000 rawLe=0x7'
require_sidecar_log 'event=ue-fname source=ue-reflection-field objectName=SelfTestUObject.children_0 status=decoded .*decoded=SelfTestUObjectName_0'
require_sidecar_log 'event=ue-reflection-finish'
require_sidecar_log 'event=ue-fname-start .*status=ready.*source=SelfTestFNamePool:direct'
require_sidecar_log 'event=ue-fname source=ue-uobject objectName=SelfTestUObject status=decoded .*decoded=SelfTestUObjectName_0'
require_sidecar_log 'event=ue-object-array-start'
require_sidecar_log 'event=ue-object-array name=SelfTestObjectArray mode=indirect status=scanning'
require_sidecar_log 'event=ue-fname source=ue-object-array objectName=SelfTestObjectArray_0 status=decoded .*decoded=SelfTestUObjectName_0'
require_sidecar_log 'event=ue-object-native-identity source=ue-uobject status=promoted .*name=SelfTestUObjectName_0 .*className=SelfTestUObjectName_0 .*outer=0x0 nameDecoded=true classNameDecoded=true'
require_sidecar_log 'event=ue-object-native-identity source=ue-object-array status=promoted .*name=SelfTestUObjectName_0 .*className=SelfTestUObjectName_0 .*outer=0x0 nameDecoded=true classNameDecoded=true'
require_sidecar_log 'event=lua-object-registry source=ue-object-array-fname status=skipped name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 aliasOf=SelfTestObjectArray_0 class=SelfTestUObjectName_0'
require_sidecar_log 'event=lua-object-registry-check source=ue-object-array-fname status=passed name=SelfTestUObjectName_0 path=/RuntimeProbe/SelfTestUObjectName_0 class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_sidecar_log 'event=lua-object-registry source=ue-object-array status=added name=SelfTestObjectArray_0 path=/RuntimeProbe/SelfTestObjectArray_0 class=SelfTestUObjectName_0'
require_sidecar_log 'event=lua-object-registry-check source=ue-object-array status=passed name=SelfTestObjectArray_0 path=/RuntimeProbe/SelfTestObjectArray_0 class=SelfTestUObjectName_0 .*pathHit=true nameHit=true classHit=true addressHit=true'
require_sidecar_log 'event=ue-object-array-item name=SelfTestObjectArray index=0 status=registered .*outer=0x0'
require_sidecar_log 'event=ue-object-array name=SelfTestObjectArray mode=indirect status=finished .*registered=2'
require_sidecar_log 'event=ue-object-array-finish'
require_sidecar_log 'event=ue-fname-finish .*status=ready.*source=SelfTestFNamePool:direct'
require_sidecar_log 'event=hook-dispatch name=SelfTestHook status=installed'
require_sidecar_log 'event=hook-dispatch name=SelfTestHook status=restored'
require_sidecar_log 'event=hook-dispatch-self-test phase=smoke status=passed'
require_sidecar_log 'event=hook-dispatch-self-test .*original=42 callbacks=2 preCallbacks=1 postCallbacks=1'
require_sidecar_log 'event=mod-dispatch-self-test phase=smoke status=passed'
require_sidecar_log 'event=mod-dispatch-self-test .*mods=1 loaded=1 unloaded=1 result=1042 original=42 callbacks=2 preCallbacks=1 postCallbacks=1 loadCallbacks=1 unloadCallbacks=1'
require_sidecar_log 'event=lua-dispatch-self-test phase=smoke status=library-missing'
require_sidecar_log 'event=lua-reflection-self-test phase=smoke status=library-missing'
require_sidecar_log 'event=ue-process-event-hook phase=smoke status=target-mapped .*selfTestTarget=true install=true'
require_sidecar_log 'event=hook-dispatch name=ProcessEventHookProbe status=installed'
require_sidecar_log 'event=hook-dispatch name=ProcessEventHookProbe status=restored'
require_sidecar_log 'event=ue-process-event-hook phase=smoke status=passed .*installed=true restored=true selfTestTarget=true .*callSelfTest=true liveCalls=1 originalCalls=1 paramsResult=62 paramsTouched=1'
require_sidecar_log 'event=ue-call-function-hook phase=smoke status=target-mapped .*selfTestTarget=true install=true'
require_sidecar_log 'event=hook-dispatch name=CallFunctionHookProbe status=installed'
require_sidecar_log 'event=hook-dispatch name=CallFunctionHookProbe status=restored'
require_sidecar_log 'event=ue-call-function-hook phase=smoke status=passed .*installed=true restored=true selfTestTarget=true .*callSelfTest=true before=42 after=1042 final=42 original=42'
require_sidecar_log 'event=ue-call-function-live-hook phase=smoke status=target-mapped .*selfTestTarget=true logCalls=true callLogLimit=2'
require_sidecar_log 'event=hook-dispatch name=CallFunctionLiveHook status=installed'
require_sidecar_log 'event=ue-call-function-live-hook-call status=entered call=1'
require_sidecar_log 'event=ue-call-function-live-hook-call status=returned call=1 originalCalled=true .*result=42'
require_sidecar_log 'event=ue-call-function-live-hook phase=smoke status=installed .*selfTestTarget=true .*callSelfTest=true .*liveCalls=1 originalCalls=1 result=42'
require_sidecar_log 'event=lua-process-event-self-test phase=smoke status=library-missing'
require_sidecar_log 'event=lua-mod-finish phase=smoke status=library-missing'
require_sidecar_log 'event=ue-process-event-dispatch-self-test phase=smoke status=armed .*callbacks=2'
require_sidecar_log 'event=ue-process-event-live-hook phase=smoke status=target-mapped .*selfTestTarget=true logCalls=true callLogLimit=2'
require_sidecar_log 'event=hook-dispatch name=ProcessEventLiveHook status=installed'
require_sidecar_log 'event=ue-process-event-live-hook-call status=entered call=1'
require_sidecar_log 'event=ue-process-event-live-hook-call status=returned call=1 originalCalled=true originalSuppressed=false preCallbacks=1 postCallbacks=1'
require_sidecar_log 'event=ue-process-event-live-registry-context status=resolved .*objectResolved=true objectNativeIdentity=true .*functionResolved=true functionNativeIdentity=true .*functionParamDescriptors=[1-9][0-9]* .*paramsPresent=true'
require_sidecar_log 'event=ue-process-event-live-hook phase=smoke status=installed .*selfTestTarget=true .*callSelfTest=true dispatchCallbacks=2 luaDispatch=false .*preCallbacks=1 postCallbacks=1 liveCalls=2 originalCalls=2 .*paramsResult=62 paramsTouched=1'
require_sidecar_log 'event=ue-process-event-live-param status=raw .*param=Location className=FStructProperty type=vector .*value=rawHex='
require_sidecar_log 'event=ue-process-event-live-param status=container .*param=NumberArray className=FArrayProperty type=array .*value=kind=FScriptArray'
require_sidecar_log 'event=ue-process-event-live-param status=container .*param=NumberSet className=FSetProperty type=set .*value=kind=FScriptSetHeader'
require_sidecar_log 'event=ue-process-event-live-param status=container .*param=NumberMap className=FMapProperty type=map .*value=kind=FScriptMapHeader'
require_sidecar_log 'event=hook-dispatch name=ProcessEventLiveHook status=restored'
require_sidecar_log 'event=hook-dispatch name=CallFunctionLiveHook status=restored'
require_sidecar_log 'event=ue-call-function-live-hook phase=detach status=restored .*liveCalls=1 originalCalls=1'
require_sidecar_log 'event=ue-process-event-live-hook phase=detach status=restored .*liveCalls=2 originalCalls=2'

printf 'Windows client loader smoke passed: %s\n' "$log"
