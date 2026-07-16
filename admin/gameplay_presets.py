#!/usr/bin/env python3
"""Validated gameplay preset planning/apply/rollback for UserGame INI files."""
import datetime
import json
import os
import pathlib
import re
import shutil

SECTIONS={
 "Sandworm":"/Script/DuneSandbox.SandwormSettings","Storm":"/Script/DuneSandbox.SandStormConfig",
 "Building":"/Script/DuneSandbox.BuildingSettings","Harvest":"/Script/DuneSandbox.SpiceHarvestingSystem",
 "FlourSand":"/Script/DuneSandbox.FlourSandSubsystem","TimeOfDay":"/Script/DuneSandbox.TimeOfDaySettings",
 "GameMode":"/Script/DuneSandbox.DuneSandboxGameModeBase","Hydration":"/Script/DuneSandbox.HydrationSubsystem",
}
SPECS={
 "ThreatScale":("float",0,5),"DefaultMaxThreatScore":("int",100,100000),"ThreatDecreaseCooldownInSeconds":("float",0,300),
 "WalkingThreatPerSec":("float",0,10000),"RunningThreatPerSec":("float",0,10000),"CrouchingThreatPerSec":("float",0,10000),"SprintingThreatPerSec":("float",0,10000),"HyperSprintingThreatPerSec":("float",0,10000),"DashingThreatPerSec":("float",0,10000),"SuspendingThreatPerSec":("float",0,10000),"ShieldingThreatPerSec":("float",0,10000),"VehicleShieldingThreatPerSec":("float",0,10000),"DrumsandThreatPerSec":("float",0,10000),
 "m_MinDistanceBetweenSandworms":("float",1000,1000000),"m_bGiantWormSystemEnabled":("bool",None,None),"m_GiantWormMinimumPlayersOnSpiceField":("int",1,100),"m_GiantWormMinimumSpiceAmountHarvested":("float",0,10000000),"m_GiantWormSpawningCooldown":("float",0,604800),"m_GiantWormSpawningUpdateFrequency":("float",1,3600),
 "m_bCoriolisAutoSpawnEnabled":("bool",None,None),"m_bCoriolisDoesDamage":("bool",None,None),"m_CoriolisHeavyDamage":("float",0,1000000),"m_CoriolisLightDamage":("float",0,1000000),"m_SandStormDebrisSpeed":("float",0,100000),"m_bMitigateAllSandstormDamage":("bool",None,None),
 "m_NodeValueToSpiceResourceRatio":("float",0.01,1000),"m_FlourSandFieldsActivePercentage":("float",0,1),"m_DefaultRepairCostMultiplier":("float",0,100),"m_DayLengthMinutes":("float",1,1440),"m_DropAmountOnDefeat":("float",0,1),"m_bHydrationEnabled":("bool",None,None),
}
TARGETS={"UserGame.ini","UserGame.deep-desert-coriolis.ini","UserGame.deep-desert-pvp.ini"}

def validate_value(key,value):
    if key not in SPECS: raise ValueError(f"preset key is not allowlisted: {key}")
    kind,minimum,maximum=SPECS[key]; text=str(value).strip()
    if kind=="bool":
        if text.lower() not in ("true","false"): raise ValueError(f"{key} must be true or false")
        return "True" if text.lower()=="true" else "False"
    try: number=int(text) if kind=="int" else float(text)
    except ValueError as exc: raise ValueError(f"{key} must be {kind}") from exc
    if number<minimum or number>maximum: raise ValueError(f"{key} must be from {minimum} to {maximum}")
    return str(number)

def load_catalog(path):
    value=json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(value,dict) or value.get("schemaVersion")!=1 or not isinstance(value.get("presets"),list): raise ValueError("gameplay preset catalog must be schemaVersion 1")
    seen=set(); presets=[]
    for raw in value["presets"]:
        preset_id=str(raw.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}",preset_id) or preset_id in seen: raise ValueError(f"invalid or duplicate preset id: {preset_id}")
        seen.add(preset_id); settings=[]
        for item in raw.get("settings") or []:
            group=str(item.get("group") or "")
            if group not in SECTIONS: raise ValueError(f"unknown preset group: {group}")
            key=str(item.get("key") or "").strip(); settings.append({"group":group,"section":SECTIONS[group],"key":key,"value":validate_value(key,item.get("value"))})
        if not settings: raise ValueError(f"preset {preset_id} has no settings")
        presets.append({"id":preset_id,"label":str(raw.get("label") or preset_id)[:200],"description":str(raw.get("description") or "")[:1000],"category":str(raw.get("category") or "custom")[:80],"settings":settings,"source":raw.get("source") or {}})
    return {"schemaVersion":1,"presets":presets,"source":value.get("source") or {}}

def _section_values(text):
    result={}; section=None
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith("[") and stripped.endswith("]"): section=stripped[1:-1]; continue
        if section and not stripped.startswith((";","#","+","-")) and "=" in line:
            key,value=line.split("=",1); result[(section,key.strip())]=value.strip()
    return result

def merge(text,settings):
    lines=text.splitlines(); by_section={}
    for item in settings: by_section.setdefault(item["section"],{})[item["key"]]=item["value"]
    rendered=[]; current=None; seen=set()
    for line in lines:
        stripped=line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current in by_section:
                for key,value in by_section[current].items():
                    if (current,key) not in seen: rendered.append(f"{key}={value}"); seen.add((current,key))
            current=stripped[1:-1]; rendered.append(line); continue
        if current in by_section and not stripped.startswith((";","#","+","-")) and "=" in line:
            key=line.split("=",1)[0].strip()
            if key in by_section[current]:
                if (current,key) not in seen: rendered.append(f"{key}={by_section[current][key]}"); seen.add((current,key))
                continue
        rendered.append(line)
    if current in by_section:
        for key,value in by_section[current].items():
            if (current,key) not in seen: rendered.append(f"{key}={value}"); seen.add((current,key))
    for section,items in by_section.items():
        if any(pair[0]==section for pair in seen): continue
        if rendered and rendered[-1] != "": rendered.append("")
        rendered.append(f"[{section}]")
        for key,value in items.items(): rendered.append(f"{key}={value}");seen.add((section,key))
    return "\n".join(rendered).rstrip()+"\n"

def validate_landsraad_cycle(config_root):
    checked=[]
    for name in ("UserGame.ini","UserGame.deep-desert-coriolis.ini"):
        path=pathlib.Path(config_root)/name
        text=path.read_text(encoding="utf-8")
        values=_section_values(text); duration=values.get(("/Script/DuneSandbox.CoriolisSubsystem","m_CycleDurationInDays"))
        if duration != "7": raise ValueError(f"{name} must keep m_CycleDurationInDays=7 for Landsraad; found {duration!r}")
        checked.append(name)
    return checked

def plan(config_root,catalog_path,preset_id,target):
    if target not in TARGETS: raise ValueError("unsupported UserGame target")
    catalog=load_catalog(catalog_path); preset=next((row for row in catalog["presets"] if row["id"]==preset_id),None)
    if not preset: raise ValueError("gameplay preset not found")
    validate_landsraad_cycle(config_root); path=pathlib.Path(config_root)/target; before=path.read_text(encoding="utf-8"); after=merge(before,preset["settings"]); old=_section_values(before); new=_section_values(after)
    changes=[{"group":item["group"],"section":item["section"],"key":item["key"],"before":old.get((item["section"],item["key"])),"after":new.get((item["section"],item["key"])),"changed":old.get((item["section"],item["key"]))!=new.get((item["section"],item["key"]))} for item in preset["settings"]]
    services=["deep-desert"] if target.endswith("coriolis.ini") else ["deep-desert-pvp"] if target.endswith("pvp.ini") else ["all default UserGame maps"]
    return {"ok":True,"dryRun":True,"preset":preset,"target":target,"changes":changes,"changed":before!=after,"before":before,"after":after,"restartRequired":True,"affectedServices":services,"landsraadCycleValidated":True}

def apply(config_root,catalog_path,preset_id,target,backup_root):
    result=plan(config_root,catalog_path,preset_id,target)
    if not result["changed"]: return {**result,"dryRun":False,"idempotent":True,"backup":None}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"); directory=pathlib.Path(backup_root)/"gameplay-presets"/stamp; directory.mkdir(parents=True,exist_ok=False,mode=0o700); path=pathlib.Path(config_root)/target; backup=directory/target; shutil.copy2(path,backup); os.chmod(backup,0o600)
    temporary=path.with_suffix(path.suffix+".preset.tmp"); temporary.write_text(result["after"],encoding="utf-8"); os.chmod(temporary,path.stat().st_mode & 0o777); temporary.replace(path)
    validate_landsraad_cycle(config_root)
    return {**result,"dryRun":False,"idempotent":False,"backup":str(backup),"before":None,"after":None}

def rollback(config_root,backup_path,backup_root):
    backup=pathlib.Path(backup_path).resolve(); root=(pathlib.Path(backup_root)/"gameplay-presets").resolve()
    if root not in backup.parents or backup.name not in TARGETS or not backup.is_file(): raise ValueError("rollback backup is outside the gameplay preset backup root")
    target=pathlib.Path(config_root)/backup.name; recovery=target.with_name(target.name+".before-rollback-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")); shutil.copy2(target,recovery); shutil.copy2(backup,target); validate_landsraad_cycle(config_root)
    return {"ok":True,"target":backup.name,"restoredFrom":str(backup),"recovery":str(recovery),"restartRequired":True}
