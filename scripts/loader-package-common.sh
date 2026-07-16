#!/usr/bin/env bash

# Shared reproducibility primitives for loader package scripts.
# The caller must enable strict mode before sourcing this file.

loader_package_init_metadata() {
  local repo_root="$1"
  LOADER_PACKAGE_SOURCE_COMMIT="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)"
  LOADER_PACKAGE_SOURCE_TREE="$(git -C "$repo_root" rev-parse 'HEAD^{tree}' 2>/dev/null || printf unknown)"
  if [ -n "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=normal 2>/dev/null || printf unknown)" ]; then
    LOADER_PACKAGE_SOURCE_DIRTY=true
  else
    LOADER_PACKAGE_SOURCE_DIRTY=false
  fi
  LOADER_PACKAGE_SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-}"
  if [ -z "$LOADER_PACKAGE_SOURCE_DATE_EPOCH" ]; then
    LOADER_PACKAGE_SOURCE_DATE_EPOCH="$(git -C "$repo_root" show -s --format=%ct HEAD 2>/dev/null || date -u +%s)"
  fi
  case "$LOADER_PACKAGE_SOURCE_DATE_EPOCH" in
    ''|*[!0-9]*)
      echo "SOURCE_DATE_EPOCH must be a non-negative integer" >&2
      return 2
      ;;
  esac
  LOADER_PACKAGE_BUILT_UTC="$(date -u -d "@$LOADER_PACKAGE_SOURCE_DATE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
  export LOADER_PACKAGE_SOURCE_COMMIT LOADER_PACKAGE_SOURCE_TREE
  export LOADER_PACKAGE_SOURCE_DIRTY LOADER_PACKAGE_SOURCE_DATE_EPOCH LOADER_PACKAGE_BUILT_UTC
}

loader_package_write_provenance() {
  local output="$1"
  local package_name="$2"
  local target="$3"
  local version="$4"
  local platform="$5"
  local loader="$6"
  local loader_relative="$7"
  local build_type="$8"
  python3 - "$output" "$package_name" "$target" "$version" "$platform" "$loader" "$loader_relative" "$build_type" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

output, package_name, target, version, platform, loader_text, loader_relative, build_type = sys.argv[1:]
loader = pathlib.Path(loader_text)
digest = hashlib.sha256(loader.read_bytes()).hexdigest()
payload = {
    "schemaVersion": "dune-loader-package-provenance/v1",
    "packageName": package_name,
    "target": target,
    "version": version,
    "platform": platform,
    "builtUtc": os.environ["LOADER_PACKAGE_BUILT_UTC"],
    "sourceDateEpoch": int(os.environ["LOADER_PACKAGE_SOURCE_DATE_EPOCH"]),
    "source": {
        "commit": os.environ["LOADER_PACKAGE_SOURCE_COMMIT"],
        "tree": os.environ["LOADER_PACKAGE_SOURCE_TREE"],
        "dirty": os.environ["LOADER_PACKAGE_SOURCE_DIRTY"] == "true",
    },
    "build": {"type": build_type},
    "loader": {
        "path": loader_relative,
        "sha256": digest,
        "size": loader.stat().st_size,
    },
}
path = pathlib.Path(output)
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

loader_package_create_archive() {
  local dist_root="$1"
  local package_name="$2"
  local archive="$3"
  tar \
    --sort=name \
    --mtime="@$LOADER_PACKAGE_SOURCE_DATE_EPOCH" \
    --owner=0 \
    --group=0 \
    --numeric-owner \
    --format=posix \
    --pax-option=delete=atime,delete=ctime \
    -C "$dist_root" \
    -cf - "$package_name" | gzip -n > "$archive"
}
