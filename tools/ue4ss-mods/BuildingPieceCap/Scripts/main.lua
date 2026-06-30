local MOD_NAME = "BuildingPieceCap"

local function getenv(name, default)
  if os and os.getenv then
    local value = os.getenv(name)
    if value ~= nil and value ~= "" then
      return value
    end
  end
  return default
end

local function truthy(value)
  return value == true or value == "true" or value == "1" or value == "yes" or value == "on"
end

local target_limit = tonumber(getenv("DUNE_BUILDING_PIECE_LIMIT", "7500")) or 7500
local apply_enabled = truthy(getenv("DUNE_BUILDING_PIECE_LIMIT_UE4SS_APPLY", "false"))

local asset_paths = {
  "/Game/Dune/Systems/Building/Data/DT_BuildableStructureCategoryData.DT_BuildableStructureCategoryData",
  "/Game/Dune/Systems/Building/Data/DT_BuildableStructureCategoryData",
}

local candidate_names = {
  "m_MaximumNumberOfBuildables",
  "MaximumNumberOfBuildables",
  "MaxNumberOfBuildables",
  "MaxBuildables",
  "BuildingPieceLimit",
}

local function safe_call(fn)
  local ok, result = pcall(fn)
  if ok then
    return result
  end
  return nil
end

local function log(message)
  if print then
    print("[" .. MOD_NAME .. "] " .. message)
  end
end

local function load_or_find_asset(path)
  local object = safe_call(function()
    return LoadAsset(path)
  end)
  if object then
    return object, "LoadAsset", path
  end
  object = safe_call(function()
    return StaticFindObject(path)
  end)
  if object then
    return object, "StaticFindObject", path
  end
  object = safe_call(function()
    return FindObject(path)
  end)
  if object then
    return object, "FindObject", path
  end
  return nil, nil, path
end

local function object_name(object)
  if not object then
    return "<nil>"
  end
  return tostring(object.PathName or object.Name or object)
end

local function patch_property(object, property_name)
  local old_value = safe_call(function()
    return GetPropertyValue(object, property_name)
  end)
  if old_value == nil and object.Reflection then
    local property = safe_call(function()
      return object:Reflection():GetProperty(property_name)
    end)
    if property and property.GetValue then
      old_value = safe_call(function()
        return property:GetValue()
      end)
    end
    if apply_enabled and property and property.SetValue then
      local ok = safe_call(function()
        return property:SetValue(target_limit)
      end)
      if ok then
        return true, old_value, "descriptor"
      end
    end
  end
  if old_value == nil then
    return false, nil, "missing"
  end
  if not apply_enabled then
    return true, old_value, "dry"
  end
  local set_ok = safe_call(function()
    return SetPropertyValue(object, property_name, target_limit)
  end)
  return set_ok == true, old_value, "global"
end

local function patch_object(object, source)
  local patched = 0
  local observed = 0
  for _, property_name in ipairs(candidate_names) do
    local ok, old_value, mode = patch_property(object, property_name)
    if old_value ~= nil then
      observed = observed + 1
      log("observed " .. property_name .. "=" .. tostring(old_value) .. " on " .. object_name(object) .. " via " .. mode)
    end
    if ok and old_value ~= nil then
      patched = patched + 1
    end
  end
  if patched > 0 or observed > 0 then
    log("object source=" .. source .. " name=" .. object_name(object) .. " observed=" .. tostring(observed) .. " patched=" .. tostring(patched) .. " apply=" .. tostring(apply_enabled) .. " target=" .. tostring(target_limit))
  end
  return patched, observed
end

local function patch_known_assets()
  local patched = 0
  local observed = 0
  for _, path in ipairs(asset_paths) do
    local object, source = load_or_find_asset(path)
    if object then
      local p, o = patch_object(object, source or "asset")
      patched = patched + p
      observed = observed + o
      local class = safe_call(function()
        return object:GetClass()
      end)
      local cdo = class and safe_call(function()
        return class:GetDefaultObject()
      end)
      if cdo then
        local cp, co = patch_object(cdo, "cdo:" .. path)
        patched = patched + cp
        observed = observed + co
      end
    end
  end
  return patched, observed
end

local function scan_known_objects()
  local patched = 0
  local observed = 0
  if not ForEachUObject then
    return patched, observed
  end
  safe_call(function()
    ForEachUObject(function(object)
      local name = object_name(object)
      if name:find("BuildableStructureCategoryData", 1, true) or name:find("BuildingPiece", 1, true) then
        local p, o = patch_object(object, "scan")
        patched = patched + p
        observed = observed + o
      end
    end)
  end)
  return patched, observed
end

local function run()
  local patched, observed = patch_known_assets()
  local scan_patched, scan_observed = scan_known_objects()
  patched = patched + scan_patched
  observed = observed + scan_observed
  log("summary observed=" .. tostring(observed) .. " patched=" .. tostring(patched) .. " apply=" .. tostring(apply_enabled) .. " target=" .. tostring(target_limit))
  return patched, observed
end

RegisterModInitCallback(function()
  run()
  return false
end)

RegisterModPostInitCallback(function()
  run()
  return false
end)
