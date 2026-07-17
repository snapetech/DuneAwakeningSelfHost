#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_archive="$root/source/busybox-1.36.1.tar.bz2"
config="$root/source/busybox-1.36.1.config"
output="/tmp/dash-busybox"
expected_source_sha="b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314"
source_date_epoch="1684449439"

while (($#)); do
  case "$1" in
    --output) output="${2:?missing --output value}"; shift 2 ;;
    -h|--help)
      printf 'Usage: vendor/build-busybox.sh [--output FILE]\n'
      exit 0
      ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ -f "$source_archive" && -f "$config" ]] || { printf 'BusyBox source/config is missing\n' >&2; exit 1; }
actual_source_sha="$(sha256sum "$source_archive" | awk '{print $1}')"
[[ "$actual_source_sha" == "$expected_source_sha" ]] || { printf 'BusyBox source checksum mismatch\n' >&2; exit 1; }
command -v make >/dev/null || { printf 'make is required\n' >&2; exit 1; }
command -v cc >/dev/null || { printf 'a C compiler is required\n' >&2; exit 1; }

work="$(mktemp -d)"
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
tar -xjf "$source_archive" -C "$work"
source="$work/busybox-1.36.1"
cp -- "$config" "$source/.config"
jobs="${DASH_BUSYBOX_BUILD_JOBS:-2}"
SOURCE_DATE_EPOCH="$source_date_epoch" \
KBUILD_BUILD_USER=dash KBUILD_BUILD_HOST=release \
  make -C "$source" -j "$jobs" busybox
install -m 0755 "$source/busybox" "$output"
printf 'built BusyBox: %s\n' "$output"
sha256sum "$output"
