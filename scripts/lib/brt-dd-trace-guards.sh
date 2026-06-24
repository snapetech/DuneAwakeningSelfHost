#!/usr/bin/env bash
# Shared guardrails for Deep Desert BRT tracing.
#
# These scripts attach debuggers/uprobe events to live server processes. Offsets
# are build-specific; stale offsets can stop the wrong code path or produce
# useless evidence. Keep this helper small and fail closed.

brt_dd_trace_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
brt_dd_trace_current_build_id="427a3084dcc00057ad21f98555a7d17d5f3c1020"
brt_dd_trace_current_points_file="$brt_dd_trace_repo_root/scripts/research/brt-dd-points-427a3084.tsv"

brt_dd_trace_die() {
  echo "ERROR: $*" >&2
  exit 2
}

brt_dd_trace_build_id_for_pid() {
  local pid="$1" notes build_id
  notes="$(sudo -n readelf -n "/proc/$pid/exe" 2>/dev/null || readelf -n "/proc/$pid/exe" 2>/dev/null || true)"
  build_id="$(awk '/Build ID:/ {print $3; exit}' <<<"$notes")"
  [[ -n "$build_id" ]] || return 1
  printf '%s\n' "$build_id"
}

brt_dd_trace_expected_build_id() {
  local points_file="$1"
  awk -F= '
    /^[[:space:]]*#?[[:space:]]*build_id[[:space:]]*=/ {
      value=$2
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      print value
      exit
    }
  ' "$points_file"
}

brt_dd_trace_validate_points_file() {
  local pid="$1" points_file="$2" expected actual
  [[ -f "$points_file" ]] || brt_dd_trace_die "points file not found: $points_file"
  expected="$(brt_dd_trace_expected_build_id "$points_file")"
  [[ -n "$expected" ]] || brt_dd_trace_die "points file has no build_id header: $points_file"
  actual="$(brt_dd_trace_build_id_for_pid "$pid" || true)"
  [[ -n "$actual" ]] || brt_dd_trace_die "could not read build id for pid=$pid"
  if [[ "$actual" != "$expected" && "${DUNE_BRT_DD_TRACE_ALLOW_BUILD_MISMATCH:-0}" != "1" ]]; then
    brt_dd_trace_die "points file build_id=$expected does not match pid=$pid build_id=$actual; set DUNE_BRT_DD_TRACE_ALLOW_BUILD_MISMATCH=1 only for offline/lab research"
  fi
}

brt_dd_trace_default_points_file_for_pid() {
  local pid="$1" actual
  actual="$(brt_dd_trace_build_id_for_pid "$pid" || true)"
  if [[ "$actual" == "$brt_dd_trace_current_build_id" && -f "$brt_dd_trace_current_points_file" ]]; then
    printf '%s\n' "$brt_dd_trace_current_points_file"
    return 0
  fi
  return 1
}

brt_dd_trace_select_points_file() {
  local pid="$1" points_file="${DUNE_BRT_DD_POINTS_FILE:-}"
  if [[ -z "$points_file" ]]; then
    points_file="$(brt_dd_trace_default_points_file_for_pid "$pid" || true)"
  fi
  [[ -n "$points_file" ]] || return 1
  brt_dd_trace_validate_points_file "$pid" "$points_file"
  printf '%s\n' "$points_file"
}

brt_dd_trace_points_or_stale_override() {
  local pid="$1" label="$2" points_file actual
  points_file="$(brt_dd_trace_select_points_file "$pid" || true)"
  if [[ -n "$points_file" ]]; then
    printf '%s\n' "$points_file"
    return 0
  fi
  if [[ "${DUNE_BRT_DD_TRACE_ALLOW_STALE_BUILTINS:-0}" == "1" ]]; then
    return 0
  fi
  actual="$(brt_dd_trace_build_id_for_pid "$pid" || echo unknown)"
  brt_dd_trace_die "refusing to use built-in $label offsets on build_id=$actual; set DUNE_BRT_DD_POINTS_FILE to current offsets, or DUNE_BRT_DD_TRACE_ALLOW_STALE_BUILTINS=1 for deliberate research"
}

brt_dd_trace_emit_points() {
  local points_file="$1" profile="$2"
  awk -v profile="$profile" '
    /^[[:space:]]*(#|$)/ { next }
    {
      args = ""
      if (NF == 2) {
        scope = "all"; name = $1; offset = $2; arg_start = 3
      } else {
        scope = $1; name = $2; offset = $3; arg_start = 4
      }
      for (i = arg_start; i <= NF; i++) {
        args = args (args == "" ? "" : " ") $i
      }
      if (scope == "all" || scope == profile ||
          (profile == "decision" && scope == "minimal") ||
          (profile == "brt" && (scope == "minimal" || scope == "decision" || scope == "hotbar" || scope == "place")) ||
          (profile == "place" && scope == "place") ||
          (profile == "backup" && (scope == "minimal" || scope == "decision" || scope == "hotbar" || scope == "backup")) ||
          (profile == "full" && (scope == "minimal" || scope == "decision")) ||
          (profile == "focused" && scope == "minimal") ||
          (profile == "wide" && (scope == "minimal" || scope == "focused"))) {
        if (!seen[name]++) {
          if (args != "") print name, offset, args
          else print name, offset
        }
      }
    }
  ' "$points_file"
}

brt_dd_trace_refuse_dense_builtins_unless_allowed() {
  local pid="$1" label="$2" actual
  if [[ "${DUNE_BRT_DD_TRACE_ALLOW_STALE_BUILTINS:-0}" == "1" ]]; then
    return 0
  fi
  actual="$(brt_dd_trace_build_id_for_pid "$pid" || echo unknown)"
  brt_dd_trace_die "refusing to arm dense built-in $label breakpoints on build_id=$actual; dense offsets are not current-build validated"
}
