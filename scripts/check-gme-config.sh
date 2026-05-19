#!/usr/bin/env sh
set -eu

config="${1:-config/director.ini}"

if [ ! -f "$config" ]; then
  echo "GmeSettings section: missing"
  echo "GmeAppId: missing"
  echo "GmeAppKey: missing"
  echo "config: $config not found"
  exit 1
fi

awk '
function trim(s) {
  sub(/^[[:space:]]+/, "", s)
  sub(/[[:space:]]+$/, "", s)
  return s
}
function strip_quotes(s) {
  s = trim(s)
  if (s ~ /^".*"$/) {
    s = substr(s, 2, length(s) - 2)
  }
  return s
}
BEGIN {
  in_gme = 0
  section = 0
  app_id = 0
  app_key = 0
}
{
  line = trim($0)
  if (line == "" || line ~ /^#/) {
    next
  }
  if (line ~ /^\[.*\]$/) {
    section_name = line
    gsub(/^\[/, "", section_name)
    gsub(/\]$/, "", section_name)
    section_name = tolower(trim(section_name))
    in_gme = section_name == "gmesettings"
    if (in_gme) {
      section = 1
    }
    next
  }
  if (!in_gme || index(line, "=") == 0) {
    next
  }
  key = trim(substr(line, 1, index(line, "=") - 1))
  value = strip_quotes(substr(line, index(line, "=") + 1))
  if (key == "GmeAppId" && value ~ /^[0-9]+$/ && value != "0") {
    app_id = 1
  }
  if (key == "GmeAppKey" && value != "" && value !~ /replace-with/) {
    app_key = 1
  }
}
END {
  print "GmeSettings section: " (section ? "present" : "missing")
  print "GmeAppId: " (app_id ? "present" : "missing")
  print "GmeAppKey: " (app_key ? "present" : "missing")
  if (section && app_id && app_key) {
    exit 0
  }
  exit 1
}
' "$config"
