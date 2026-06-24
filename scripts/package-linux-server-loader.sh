#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
build_script="$repo_root/scripts/build-linux-server-loader.sh"
build_dir="${DUNE_LINUX_SERVER_LOADER_BUILD_DIR:-$repo_root/build/linux-server-loader}"
loader="$build_dir/libdune_server_probe_loader.so"
dist_root="${DUNE_LINUX_SERVER_LOADER_DIST_DIR:-$repo_root/dist/linux-server-loader}"
default_version="$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%dT%H%M%SZ)"
if ! git -C "$repo_root" diff --quiet --ignore-submodules -- 2>/dev/null ||
   ! git -C "$repo_root" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
  default_version="${default_version}-dirty"
fi
version="${DUNE_LINUX_SERVER_LOADER_VERSION:-$default_version}"
platform="linux-x86_64"
package_name="dune-linux-server-loader-${version}-${platform}"
stage="$dist_root/$package_name"
archive="$dist_root/${package_name}.tar.gz"

"$build_script" >/dev/null

if [ ! -f "$loader" ]; then
  echo "missing built loader: $loader" >&2
  exit 1
fi

rm -rf "$stage" "$archive"
mkdir -p \
  "$stage/lib" \
  "$stage/src" \
  "$stage/scripts" \
  "$stage/scripts/research" \
  "$stage/tests" \
  "$stage/docs" \
  "$stage/examples" \
  "$stage/abi"

cp "$loader" "$stage/lib/libdune_server_probe_loader.so"
cp "$repo_root/tools/linux-server-loader/dune_server_probe_loader.c" "$stage/src/dune_server_probe_loader.c"
cp "$repo_root/tools/linux-server-loader/CMakeLists.txt" "$stage/src/CMakeLists.txt"
cp "$repo_root/scripts/summarize-linux-loader-scan.py" "$stage/scripts/summarize-linux-loader-scan.py"
cp "$repo_root/scripts/summarize-linux-loader-xrefs.py" "$stage/scripts/summarize-linux-loader-xrefs.py"
cp "$repo_root/scripts/summarize-linux-loader-anchors.py" "$stage/scripts/summarize-linux-loader-anchors.py"
cp "$repo_root/scripts/validate-elf-signatures.py" "$stage/scripts/validate-elf-signatures.py"
cp "$repo_root/scripts/export-elf-signature-manifest.py" "$stage/scripts/export-elf-signature-manifest.py"
cp "$repo_root/scripts/summarize-client-loader-scan.py" "$stage/scripts/summarize-client-loader-scan.py"
cp "$repo_root/scripts/ue4ss-port-readiness.py" "$stage/scripts/ue4ss-port-readiness.py"
cp "$repo_root/scripts/summarize-ue4ss-port-gaps.py" "$stage/scripts/summarize-ue4ss-port-gaps.py"
cp "$repo_root/scripts/summarize-ue4ss-evidence-inventory.py" "$stage/scripts/summarize-ue4ss-evidence-inventory.py"
cp "$repo_root/scripts/summarize-ue4ss-package-route-evidence.py" "$stage/scripts/summarize-ue4ss-package-route-evidence.py"
cp "$repo_root/scripts/summarize-ue4ss-package-decompile-plan.py" "$stage/scripts/summarize-ue4ss-package-decompile-plan.py"
cp "$repo_root/scripts/summarize-ue4ss-package-external-symbol-plan.py" "$stage/scripts/summarize-ue4ss-package-external-symbol-plan.py"
cp "$repo_root/scripts/plan-ue4ss-package-runtime-trace.py" "$stage/scripts/plan-ue4ss-package-runtime-trace.py"
cp "$repo_root/scripts/summarize-ue4ss-package-runtime-trace-evidence.py" "$stage/scripts/summarize-ue4ss-package-runtime-trace-evidence.py"
cp "$repo_root/scripts/plan-ue4ss-package-stimulus.py" "$stage/scripts/plan-ue4ss-package-stimulus.py"
cp "$repo_root/scripts/plan-ue4ss-package-stimulus-trace.py" "$stage/scripts/plan-ue4ss-package-stimulus-trace.py"
cp "$repo_root/scripts/plan-ue4ss-package-live-call-frame-recovery.py" "$stage/scripts/plan-ue4ss-package-live-call-frame-recovery.py"
cp "$repo_root/scripts/plan-ue4ss-package-server-replay.py" "$stage/scripts/plan-ue4ss-package-server-replay.py"
cp "$repo_root/scripts/export-ue4ss-package-promotion-env.py" "$stage/scripts/export-ue4ss-package-promotion-env.py"
cp "$repo_root/scripts/summarize-ue4ss-package-promotion-dir.py" "$stage/scripts/summarize-ue4ss-package-promotion-dir.py"
cp "$repo_root/scripts/plan-ue4ss-package-next-action.py" "$stage/scripts/plan-ue4ss-package-next-action.py"
cp "$repo_root/scripts/verify-ue4ss-package-review-bundle.py" "$stage/scripts/verify-ue4ss-package-review-bundle.py"
cp "$repo_root/scripts/verify-ue4ss-package-route-slot-recovery.py" "$stage/scripts/verify-ue4ss-package-route-slot-recovery.py"
cp "$repo_root/scripts/verify-ue4ss-package-live-stimulus-summary.py" "$stage/scripts/verify-ue4ss-package-live-stimulus-summary.py"
cp "$repo_root/scripts/verify-ue4ss-package-live-preflight-summary.py" "$stage/scripts/verify-ue4ss-package-live-preflight-summary.py"
cp "$repo_root/scripts/verify-ue4ss-package-prearm-readiness.py" "$stage/scripts/verify-ue4ss-package-prearm-readiness.py"
cp "$repo_root/scripts/audit-ue4ss-linux-port-completion.py" "$stage/scripts/audit-ue4ss-linux-port-completion.py"
cp "$repo_root/scripts/review-ue4ss-package-abi.py" "$stage/scripts/review-ue4ss-package-abi.py"
cp "$repo_root/scripts/ue4ss-package-runtime-trace.sh" "$stage/scripts/ue4ss-package-runtime-trace.sh"
cp "$repo_root/scripts/ue4ss-package-remote-trace.sh" "$stage/scripts/ue4ss-package-remote-trace.sh"
cp "$repo_root/scripts/run-ue4ss-package-live-stimulus-trace.sh" "$stage/scripts/run-ue4ss-package-live-stimulus-trace.sh"
cp "$repo_root/scripts/ue4ss-portability-contract.py" "$stage/scripts/ue4ss-portability-contract.py"
cp "$repo_root/scripts/verify-loader-artifacts.py" "$stage/scripts/verify-loader-artifacts.py"
cp "$repo_root/scripts/export-ue-anchor-env.py" "$stage/scripts/export-ue-anchor-env.py"
cp "$repo_root/scripts/export-ue-candidate-globals.py" "$stage/scripts/export-ue-candidate-globals.py"
cp "$repo_root/scripts/summarize-ue-candidate-outcomes.py" "$stage/scripts/summarize-ue-candidate-outcomes.py"
cp "$repo_root/scripts/summarize-ue-candidate-shapes.py" "$stage/scripts/summarize-ue-candidate-shapes.py"
cp "$repo_root/scripts/summarize-ue-code-pointer-context.py" "$stage/scripts/summarize-ue-code-pointer-context.py"
cp "$repo_root/scripts/summarize-ue-vtable-candidates.py" "$stage/scripts/summarize-ue-vtable-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-function-neighborhoods.py" "$stage/scripts/summarize-elf-ue-function-neighborhoods.py"
cp "$repo_root/scripts/summarize-elf-ue-function-callgraph.py" "$stage/scripts/summarize-elf-ue-function-callgraph.py"
cp "$repo_root/scripts/summarize-elf-ue-symbol-surface.py" "$stage/scripts/summarize-elf-ue-symbol-surface.py"
cp "$repo_root/scripts/summarize-elf-ue-package-loader-vtables.py" "$stage/scripts/summarize-elf-ue-package-loader-vtables.py"
cp "$repo_root/scripts/summarize-elf-ue-package-wrapper-candidates.py" "$stage/scripts/summarize-elf-ue-package-wrapper-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-package-static-wrapper-candidates.py" "$stage/scripts/summarize-elf-ue-package-static-wrapper-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-rtti-function-object-vtables.py" "$stage/scripts/summarize-elf-ue-rtti-function-object-vtables.py"
cp "$repo_root/scripts/export-process-event-active-validation-candidates.py" "$stage/scripts/export-process-event-active-validation-candidates.py"
cp "$repo_root/scripts/summarize-elf-ue-string-dataflow.py" "$stage/scripts/summarize-elf-ue-string-dataflow.py"
cp "$repo_root/scripts/summarize-elf-writable-global-refs.py" "$stage/scripts/summarize-elf-writable-global-refs.py"
cp "$repo_root/scripts/summarize-elf-writable-root-shapes.py" "$stage/scripts/summarize-elf-writable-root-shapes.py"
cp "$repo_root/scripts/export-ue-writable-root-shape-candidates.py" "$stage/scripts/export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/research/summarize-elf-pointer-context.py" "$stage/scripts/research/summarize-elf-pointer-context.py"
cp "$repo_root/scripts/summarize-ue-root-recovery-queue.py" "$stage/scripts/summarize-ue-root-recovery-queue.py"
cp "$repo_root/scripts/cluster-ue-root-recovery-queue.py" "$stage/scripts/cluster-ue-root-recovery-queue.py"
cp "$repo_root/scripts/export-ue-root-recovery-candidates.py" "$stage/scripts/export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/promote-ue-anchor-xref-candidates.py" "$stage/scripts/promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/prepare-ue-anchor-canary.py" "$stage/scripts/prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/plan-ue4ss-canary-env.py" "$stage/scripts/plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/canary-linux-server-loader.sh" "$stage/scripts/canary-linux-server-loader.sh"
cp "$repo_root/scripts/ensure-loader-build-toolchain.sh" "$stage/scripts/ensure-loader-build-toolchain.sh"
cp "$repo_root/scripts/test-linux-loader-scan-summary.py" "$stage/tests/test-linux-loader-scan-summary.py"
cp "$repo_root/scripts/test-ue4ss-port-readiness.py" "$stage/tests/test-ue4ss-port-readiness.py"
cp "$repo_root/scripts/test-ue4ss-port-gaps.py" "$stage/tests/test-ue4ss-port-gaps.py"
cp "$repo_root/scripts/test-ue4ss-portability-contract.py" "$stage/tests/test-ue4ss-portability-contract.py"
cp "$repo_root/scripts/test-ue4ss-evidence-inventory.py" "$stage/tests/test-ue4ss-evidence-inventory.py"
cp "$repo_root/scripts/test-ue4ss-package-route-evidence.py" "$stage/tests/test-ue4ss-package-route-evidence.py"
cp "$repo_root/scripts/test-ue4ss-package-decompile-plan.py" "$stage/tests/test-ue4ss-package-decompile-plan.py"
cp "$repo_root/scripts/test-ue4ss-package-external-symbol-plan.py" "$stage/tests/test-ue4ss-package-external-symbol-plan.py"
cp "$repo_root/scripts/test-ue4ss-package-runtime-trace-plan.py" "$stage/tests/test-ue4ss-package-runtime-trace-plan.py"
cp "$repo_root/scripts/test-ue4ss-package-runtime-trace-evidence.py" "$stage/tests/test-ue4ss-package-runtime-trace-evidence.py"
cp "$repo_root/scripts/test-ue4ss-package-stimulus.py" "$stage/tests/test-ue4ss-package-stimulus.py"
cp "$repo_root/scripts/test-ue4ss-package-stimulus-trace.py" "$stage/tests/test-ue4ss-package-stimulus-trace.py"
cp "$repo_root/scripts/test-ue4ss-package-live-call-frame-recovery.py" "$stage/tests/test-ue4ss-package-live-call-frame-recovery.py"
cp "$repo_root/scripts/test-ue4ss-package-server-replay.py" "$stage/tests/test-ue4ss-package-server-replay.py"
cp "$repo_root/scripts/test-export-ue4ss-package-promotion-env.py" "$stage/tests/test-export-ue4ss-package-promotion-env.py"
cp "$repo_root/scripts/test-ue4ss-package-promotion-dir-summary.py" "$stage/tests/test-ue4ss-package-promotion-dir-summary.py"
cp "$repo_root/scripts/test-ue4ss-package-next-action.py" "$stage/tests/test-ue4ss-package-next-action.py"
cp "$repo_root/scripts/test-verify-ue4ss-package-review-bundle.py" "$stage/tests/test-verify-ue4ss-package-review-bundle.py"
cp "$repo_root/scripts/test-verify-ue4ss-package-route-slot-recovery.py" "$stage/tests/test-verify-ue4ss-package-route-slot-recovery.py"
cp "$repo_root/scripts/test-verify-ue4ss-package-live-stimulus-summary.py" "$stage/tests/test-verify-ue4ss-package-live-stimulus-summary.py"
cp "$repo_root/scripts/test-verify-ue4ss-package-live-preflight-summary.py" "$stage/tests/test-verify-ue4ss-package-live-preflight-summary.py"
cp "$repo_root/scripts/test-verify-ue4ss-package-prearm-readiness.py" "$stage/tests/test-verify-ue4ss-package-prearm-readiness.py"
cp "$repo_root/scripts/test-audit-ue4ss-linux-port-completion.py" "$stage/tests/test-audit-ue4ss-linux-port-completion.py"
cp "$repo_root/scripts/test-review-ue4ss-package-abi.py" "$stage/tests/test-review-ue4ss-package-abi.py"
cp "$repo_root/scripts/test-ue4ss-package-runtime-trace-runner.py" "$stage/tests/test-ue4ss-package-runtime-trace-runner.py"
cp "$repo_root/scripts/test-ue4ss-package-remote-trace.py" "$stage/tests/test-ue4ss-package-remote-trace.py"
cp "$repo_root/scripts/test-ue4ss-package-live-stimulus-trace-runner.py" "$stage/tests/test-ue4ss-package-live-stimulus-trace-runner.py"
cp "$repo_root/scripts/test-verify-loader-artifacts.py" "$stage/tests/test-verify-loader-artifacts.py"
cp "$repo_root/scripts/test-loader-container-api-parity.py" "$stage/tests/test-loader-container-api-parity.py"
cp "$repo_root/scripts/test-loader-scheduler-api-parity.py" "$stage/tests/test-loader-scheduler-api-parity.py"
cp "$repo_root/scripts/test-loader-modref-api-parity.py" "$stage/tests/test-loader-modref-api-parity.py"
cp "$repo_root/scripts/test-loader-mod-lifecycle-api-parity.py" "$stage/tests/test-loader-mod-lifecycle-api-parity.py"
cp "$repo_root/scripts/test-loader-unregister-api-parity.py" "$stage/tests/test-loader-unregister-api-parity.py"
cp "$repo_root/scripts/test-loader-fname-api-parity.py" "$stage/tests/test-loader-fname-api-parity.py"
cp "$repo_root/scripts/test-loader-native-identity-parity.py" "$stage/tests/test-loader-native-identity-parity.py"
cp "$repo_root/scripts/test-loader-custom-property-api-parity.py" "$stage/tests/test-loader-custom-property-api-parity.py"
cp "$repo_root/scripts/test-loader-compat-globals-api-parity.py" "$stage/tests/test-loader-compat-globals-api-parity.py"
cp "$repo_root/scripts/test-loader-world-engine-api-parity.py" "$stage/tests/test-loader-world-engine-api-parity.py"
cp "$repo_root/scripts/test-loader-object-notify-api-parity.py" "$stage/tests/test-loader-object-notify-api-parity.py"
cp "$repo_root/scripts/test-loader-console-command-api-parity.py" "$stage/tests/test-loader-console-command-api-parity.py"
cp "$repo_root/scripts/test-loader-anchor-group-parity.py" "$stage/tests/test-loader-anchor-group-parity.py"
cp "$repo_root/scripts/test-loader-scan-preset-parity.py" "$stage/tests/test-loader-scan-preset-parity.py"
cp "$repo_root/scripts/test-promote-ue-anchor-xref-candidates.py" "$stage/tests/test-promote-ue-anchor-xref-candidates.py"
cp "$repo_root/scripts/test-export-ue-candidate-globals.py" "$stage/tests/test-export-ue-candidate-globals.py"
cp "$repo_root/scripts/test-ue-candidate-outcomes.py" "$stage/tests/test-ue-candidate-outcomes.py"
cp "$repo_root/scripts/test-ue-candidate-shapes.py" "$stage/tests/test-ue-candidate-shapes.py"
cp "$repo_root/scripts/test-ue-code-pointer-context.py" "$stage/tests/test-ue-code-pointer-context.py"
cp "$repo_root/scripts/test-ue-vtable-candidates.py" "$stage/tests/test-ue-vtable-candidates.py"
cp "$repo_root/scripts/test-elf-ue-function-neighborhoods.py" "$stage/tests/test-elf-ue-function-neighborhoods.py"
cp "$repo_root/scripts/test-elf-ue-function-callgraph.py" "$stage/tests/test-elf-ue-function-callgraph.py"
cp "$repo_root/scripts/test-elf-ue-package-loader-vtables.py" "$stage/tests/test-elf-ue-package-loader-vtables.py"
cp "$repo_root/scripts/test-elf-ue-package-wrapper-candidates.py" "$stage/tests/test-elf-ue-package-wrapper-candidates.py"
cp "$repo_root/scripts/test-elf-ue-package-static-wrapper-candidates.py" "$stage/tests/test-elf-ue-package-static-wrapper-candidates.py"
cp "$repo_root/scripts/test-elf-ue-rtti-function-object-vtables.py" "$stage/tests/test-elf-ue-rtti-function-object-vtables.py"
cp "$repo_root/scripts/test-export-process-event-active-validation-candidates.py" "$stage/tests/test-export-process-event-active-validation-candidates.py"
cp "$repo_root/scripts/test-elf-ue-string-dataflow.py" "$stage/tests/test-elf-ue-string-dataflow.py"
cp "$repo_root/scripts/test-elf-writable-global-refs.py" "$stage/tests/test-elf-writable-global-refs.py"
cp "$repo_root/scripts/test-elf-writable-root-shapes.py" "$stage/tests/test-elf-writable-root-shapes.py"
cp "$repo_root/scripts/test-export-ue-writable-root-shape-candidates.py" "$stage/tests/test-export-ue-writable-root-shape-candidates.py"
cp "$repo_root/scripts/test-elf-pointer-context.py" "$stage/tests/test-elf-pointer-context.py"
cp "$repo_root/scripts/test-ue-root-recovery-queue.py" "$stage/tests/test-ue-root-recovery-queue.py"
cp "$repo_root/scripts/test-ue-root-recovery-clusters.py" "$stage/tests/test-ue-root-recovery-clusters.py"
cp "$repo_root/scripts/test-export-ue-root-recovery-candidates.py" "$stage/tests/test-export-ue-root-recovery-candidates.py"
cp "$repo_root/scripts/test-prepare-ue-anchor-canary.py" "$stage/tests/test-prepare-ue-anchor-canary.py"
cp "$repo_root/scripts/test-plan-ue4ss-canary-env.py" "$stage/tests/test-plan-ue4ss-canary-env.py"
cp "$repo_root/scripts/test-canary-linux-server-loader.py" "$stage/tests/test-canary-linux-server-loader.py"
cp "$repo_root/scripts/smoke-linux-server-loader.sh" "$stage/examples/smoke-linux-server-loader.sh"
cp "$repo_root/docs/ue4ss-linux-loader-evaluation.md" "$stage/docs/ue4ss-linux-loader-evaluation.md"
if [ -f "$repo_root/docs/linux-server-loader-canary-2026-06-16.md" ]; then
  cp "$repo_root/docs/linux-server-loader-canary-2026-06-16.md" "$stage/docs/linux-server-loader-canary-2026-06-16.md"
fi
if [ -f "$repo_root/docs/linux-server-loader-canary-2026-06-18.md" ]; then
  cp "$repo_root/docs/linux-server-loader-canary-2026-06-18.md" "$stage/docs/linux-server-loader-canary-2026-06-18.md"
fi
if [ -f "$repo_root/docs/current-build-runtime-surface-1988751.md" ]; then
  cp "$repo_root/docs/current-build-runtime-surface-1988751.md" "$stage/docs/current-build-runtime-surface-1988751.md"
fi
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format json --check > "$stage/docs/ue4ss-portability-contract.json"
python3 "$repo_root/scripts/ue4ss-portability-contract.py" --format markdown --check > "$stage/docs/ue4ss-portability-contract.md"

cat > "$stage/build-linux-server-loader.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${DUNE_LINUX_SERVER_LOADER_SOURCE_DIR:-$script_dir/src}"
build_dir="${DUNE_LINUX_SERVER_LOADER_BUILD_DIR:-$script_dir/build}"
build_type="${CMAKE_BUILD_TYPE:-RelWithDebInfo}"

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required to build the Linux server loader" >&2
  exit 1
fi

generator=()
if command -v ninja >/dev/null 2>&1; then
  generator=(-G Ninja)
fi

cmake -S "$source_dir" -B "$build_dir" "${generator[@]}" -DCMAKE_BUILD_TYPE="$build_type"
build_args=(--build "$build_dir" --target dune_server_probe_loader)
if [ -n "${DUNE_LINUX_SERVER_LOADER_JOBS:-}" ]; then
  build_args+=(--parallel "$DUNE_LINUX_SERVER_LOADER_JOBS")
fi
cmake "${build_args[@]}"

loader="$build_dir/libdune_server_probe_loader.so"
if [ ! -f "$loader" ]; then
  loader="$(find "$build_dir" -name libdune_server_probe_loader.so -type f -print -quit)"
fi

if [ -z "$loader" ] || [ ! -f "$loader" ]; then
  echo "built target but did not find libdune_server_probe_loader.so under $build_dir" >&2
  exit 1
fi

printf 'built Linux server probe loader: %s\n' "$loader"
EOF

chmod 0755 "$stage/build-linux-server-loader.sh"
chmod 0755 "$stage/scripts/summarize-linux-loader-scan.py"
chmod 0755 "$stage/scripts/summarize-linux-loader-xrefs.py"
chmod 0755 "$stage/scripts/summarize-linux-loader-anchors.py"
chmod 0755 "$stage/scripts/validate-elf-signatures.py"
chmod 0755 "$stage/scripts/export-elf-signature-manifest.py"
chmod 0755 "$stage/scripts/summarize-client-loader-scan.py"
chmod 0755 "$stage/scripts/ue4ss-port-readiness.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-port-gaps.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-evidence-inventory.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-package-route-evidence.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-package-decompile-plan.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-package-external-symbol-plan.py"
chmod 0755 "$stage/scripts/plan-ue4ss-package-runtime-trace.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-package-runtime-trace-evidence.py"
chmod 0755 "$stage/scripts/plan-ue4ss-package-stimulus.py"
chmod 0755 "$stage/scripts/plan-ue4ss-package-stimulus-trace.py"
chmod 0755 "$stage/scripts/plan-ue4ss-package-live-call-frame-recovery.py"
chmod 0755 "$stage/scripts/plan-ue4ss-package-server-replay.py"
chmod 0755 "$stage/scripts/export-ue4ss-package-promotion-env.py"
chmod 0755 "$stage/scripts/summarize-ue4ss-package-promotion-dir.py"
chmod 0755 "$stage/scripts/plan-ue4ss-package-next-action.py"
chmod 0755 "$stage/scripts/verify-ue4ss-package-review-bundle.py"
chmod 0755 "$stage/scripts/verify-ue4ss-package-route-slot-recovery.py"
chmod 0755 "$stage/scripts/verify-ue4ss-package-live-stimulus-summary.py"
chmod 0755 "$stage/scripts/verify-ue4ss-package-live-preflight-summary.py"
chmod 0755 "$stage/scripts/verify-ue4ss-package-prearm-readiness.py"
chmod 0755 "$stage/scripts/audit-ue4ss-linux-port-completion.py"
chmod 0755 "$stage/scripts/review-ue4ss-package-abi.py"
chmod 0755 "$stage/scripts/ue4ss-package-runtime-trace.sh"
chmod 0755 "$stage/scripts/ue4ss-package-remote-trace.sh"
chmod 0755 "$stage/scripts/run-ue4ss-package-live-stimulus-trace.sh"
chmod 0755 "$stage/scripts/ue4ss-portability-contract.py"
chmod 0755 "$stage/scripts/verify-loader-artifacts.py"
chmod 0755 "$stage/scripts/export-ue-anchor-env.py"
chmod 0755 "$stage/scripts/export-ue-candidate-globals.py"
chmod 0755 "$stage/scripts/summarize-ue-candidate-outcomes.py"
chmod 0755 "$stage/scripts/summarize-ue-candidate-shapes.py"
chmod 0755 "$stage/scripts/summarize-ue-code-pointer-context.py"
chmod 0755 "$stage/scripts/summarize-ue-vtable-candidates.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-function-neighborhoods.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-function-callgraph.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-symbol-surface.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-package-loader-vtables.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-package-wrapper-candidates.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-package-static-wrapper-candidates.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-rtti-function-object-vtables.py"
chmod 0755 "$stage/scripts/export-process-event-active-validation-candidates.py"
chmod 0755 "$stage/scripts/summarize-elf-ue-string-dataflow.py"
chmod 0755 "$stage/scripts/summarize-elf-writable-global-refs.py"
chmod 0755 "$stage/scripts/summarize-elf-writable-root-shapes.py"
chmod 0755 "$stage/scripts/export-ue-writable-root-shape-candidates.py"
chmod 0755 "$stage/scripts/research/summarize-elf-pointer-context.py"
chmod 0755 "$stage/scripts/summarize-ue-root-recovery-queue.py"
chmod 0755 "$stage/scripts/cluster-ue-root-recovery-queue.py"
chmod 0755 "$stage/scripts/export-ue-root-recovery-candidates.py"
chmod 0755 "$stage/scripts/promote-ue-anchor-xref-candidates.py"
chmod 0755 "$stage/scripts/prepare-ue-anchor-canary.py"
chmod 0755 "$stage/scripts/plan-ue4ss-canary-env.py"
chmod 0755 "$stage/scripts/canary-linux-server-loader.sh"
chmod 0755 "$stage/scripts/ensure-loader-build-toolchain.sh"
chmod 0755 "$stage/examples/smoke-linux-server-loader.sh"
chmod 0755 "$stage/lib/libdune_server_probe_loader.so"

cat > "$stage/examples/env.scan.example" <<'EOF'
# Opt-in runtime loader. Keep disabled until a deliberate canary restart.
DUNE_ENABLE_LINUX_SERVER_PRELOAD=true
DUNE_LINUX_SERVER_PRELOAD=/workspace/build/linux-server-loader/libdune_server_probe_loader.so
DUNE_LINUX_SERVER_PRELOAD_PARTITIONS=7
DUNE_PROBE_LOADER_LOG=/tmp/dune-server-probe-loader.log
DUNE_PROBE_LOADER_TARGET=DuneSandboxServer;DuneSandbox
DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS=0

# Read-only runtime anchor scan.
DUNE_PROBE_LOADER_SCAN_ENABLED=true
DUNE_PROBE_LOADER_SCAN_PRESETS=core,ue,building,brt,deep-desert,gm,cheat
DUNE_PROBE_LOADER_SCAN_STRINGS=DeepDesert;ServerRequestBaseBackup;BaseBackupTool;BuildingSettings;CheatManager;PrintAllowedCommands;PartitionIndex;BuildableMapRegion;FuncomLiveServices;FarmHealth
DUNE_PROBE_LOADER_SCAN_SIGNATURES=brt-action-guard=48 85 c0 74 0a 41 b6 01 41 80 7f 55 01 75 03
DUNE_PROBE_LOADER_SCAN_SIGNATURES_FILE=
DUNE_PROBE_LOADER_SCAN_MAX_HITS_PER_NEEDLE=16
DUNE_PROBE_LOADER_SCAN_LOG_MAPPINGS=true
DUNE_PROBE_LOADER_SCAN_MAX_MAPPING_BYTES=536870912

# Explicit read-only UE anchor probes. Fill these with runtime addresses from
# symbol/signature work or prior canary logs before enabling the deeper probes.
DUNE_PROBE_LOADER_UE_ANCHORS=
DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS=
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES=
DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE=
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_ROOTS=true
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_ANONYMOUS_RW=true
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_MAPPING_BYTES=268435456
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_CANDIDATES=8
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0
DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MIN_OBJECT_ARRAY_ELEMENTS=1
DUNE_PROBE_LOADER_UE_POINTER_PROBE=false
DUNE_PROBE_LOADER_UE_LAYOUT_PROBE=false
DUNE_PROBE_LOADER_UE_LAYOUT_SLOTS=8
DUNE_PROBE_LOADER_UE_UOBJECT_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_NEXT_OFFSET=0x28
DUNE_PROBE_LOADER_UE_REFLECTION_SUPER_OFFSET=0x30
DUNE_PROBE_LOADER_UE_REFLECTION_CHILDREN_OFFSET=0x38
DUNE_PROBE_LOADER_UE_REFLECTION_CHILD_PROPERTIES_OFFSET=0x40
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_LINK_OFFSET=0x48
DUNE_PROBE_LOADER_UE_REFLECTION_FUNCTION_LINK_OFFSET=0x50
DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_WALK=false
DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_NEXT_OFFSET=0x28
DUNE_PROBE_LOADER_UE_REFLECTION_MAX_FIELDS=16
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_ARRAY_DIM_OFFSET=0x30
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_ELEMENT_SIZE_OFFSET=0x34
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_FLAGS_OFFSET=0x38
DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_OFFSET_INTERNAL_OFFSET=0x44
DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_START=0x48
DUNE_PROBE_LOADER_UE_REFLECTION_CONTAINER_CHILD_SCAN_END=0xa0
DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_PROBE=false
DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_MAX_BYTES=16
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE=false
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS=128
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_OFFSET=0
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_ITEM_SIZE=24
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_OBJECT_OFFSET=0
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CHUNK_SIZE=65536
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false
DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX=32
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=0
DUNE_PROBE_LOADER_UE_FNAME_PROBE=false
DUNE_PROBE_LOADER_UE_FNAME_POOL=
DUNE_PROBE_LOADER_UE_FNAME_POOL_ADDR=
DUNE_PROBE_LOADER_UE_FNAME_POOL_OFFSET=0
DUNE_PROBE_LOADER_UE_FNAME_BLOCKS_OFFSET=0x10
DUNE_PROBE_LOADER_UE_FNAME_STRIDE=2
DUNE_PROBE_LOADER_UE_FNAME_MAX_LENGTH=128
DUNE_PROBE_LOADER_UE_FNAME_ALLOW_MISSING_NONE=false
DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS=false
DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS_MAX=16
DUNE_PROBE_LOADER_UE_SELF_TEST_ANCHOR=false

# Loader-owned UE4SS-style dispatch self-tests. Keep disabled in normal live operation.
DUNE_PROBE_LOADER_HOOK_SELF_TEST=false
DUNE_PROBE_LOADER_MOD_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_LIBRARY=
DUNE_PROBE_LOADER_LUA_SELF_TEST_SCRIPT=
DUNE_PROBE_LOADER_LUA_REFLECTION_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_REFLECTION_RAW_SET_ENABLED=false
DUNE_PROBE_LOADER_LUA_REFLECTION_SELF_TEST_SCRIPT=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_INSTALL=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_LUA_DISPATCH=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET=false
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OUTPUT_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_EXECUTOR_ADDRESS=
DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_FORCE_CALL=true
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_SELF_TEST_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT=8
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_PATH=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_NAME=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_PATH=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS=
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH=false
DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_SCRIPT=
DUNE_PROBE_LOADER_LUA_PROCESS_EVENT_SELF_TEST=false
DUNE_PROBE_LOADER_LUA_PROCESS_EVENT_SELF_TEST_SCRIPT=
DUNE_PROBE_LOADER_LUA_MODS_ENABLED=false
DUNE_PROBE_LOADER_LUA_MOD_SCRIPTS=
DUNE_PROBE_LOADER_LUA_MOD_DISPATCH_SELF_TEST=false
EOF

cat > "$stage/examples/smoke-cached-funcom-image.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

image="${1:-registry.funcom.com/funcom/self-hosting/seabass-server:1988751-0-shipping}"
loader="${2:-$(pwd)/lib/libdune_server_probe_loader.so}"
log=/tmp/dune-loader-image-scan.log

docker run --rm --pull never --network none \
  -v "$(dirname "$loader"):/probe:ro" \
  --entrypoint /bin/sh \
  "$image" \
  -lc "rm -f '$log'; DUNE_PROBE_LOADER_LOG='$log' DUNE_PROBE_LOADER_FORCE=true DUNE_PROBE_LOADER_SNAPSHOT_DELAY_SECONDS=0 DUNE_PROBE_LOADER_SCAN_ENABLED=true DUNE_PROBE_LOADER_SCAN_PRESETS= DUNE_PROBE_LOADER_SCAN_STRINGS='Usage:' DUNE_PROBE_LOADER_SCAN_SIGNATURES='elf=7f 45 4c 46' DUNE_PROBE_LOADER_SCAN_MAX_HITS_PER_NEEDLE=4 LD_PRELOAD=/probe/$(basename "$loader") /usr/bin/true; cat '$log'"
EOF
chmod 0755 "$stage/examples/smoke-cached-funcom-image.sh"

cat > "$stage/README.md" <<EOF
# Dune Linux Server Loader

Package: ${package_name}
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source commit: $(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)
Platform: ${platform}

This is a native Linux server-process loader/probe for this Dune self-host repo.
It is not upstream UE4SS and does not install client mods. It is loaded into a
Linux dedicated-server process with LD_PRELOAD through scripts/run_server_safe.sh.
It supports read-only runtime scans, explicit UE anchor validation,
pointer/layout/UObject/object-array/FName probes, Lua object-handle registration
for UE candidates, and loader-owned hook/mod/Lua/ProcessEvent-shaped self-tests.

## Contents

- lib/libdune_server_probe_loader.so: runtime preload library.
- src/: source used for this package.
- build-linux-server-loader.sh: local rebuild helper.
- scripts/: scan, xref, ELF signature, anchor export, readiness, and portability contract helpers.
- scripts/summarize-elf-ue-package-loader-vtables.py: target-image package-loader vtable method candidate inventory.
- scripts/summarize-elf-ue-function-neighborhoods.py: static executable-neighborhood report for xref, init-array, or explicit function seeds.
- scripts/summarize-elf-ue-function-callgraph.py: bounded direct-call report for exact function seeds and package-anchor promotion blockers.
- scripts/summarize-elf-ue-symbol-surface.py: target-image UE-like static/dynamic symbol surface inventory.
- scripts/summarize-elf-ue-package-wrapper-candidates.py: direct caller/wrapper queue for package-loader method candidates.
- scripts/summarize-elf-ue-package-static-wrapper-candidates.py: static/free-function package wrapper symbol and string queue.
- scripts/summarize-elf-ue-rtti-function-object-vtables.py: RTTI function-object vtable queue for streamable/package owner-method leads.
- examples/env.scan.example: opt-in environment settings.
- examples/smoke-linux-server-loader.sh: local loader-owned dispatch/Lua smoke test.
- examples/smoke-cached-funcom-image.sh: one-off Docker smoke test for a cached image.
- docs/ue4ss-portability-contract.md: repo-generated all-target portability contract.
- loader-artifact-verification.txt and loader-artifact-verification.json: package-root artifact verification outputs.
- The packaged tarball also writes sibling .verification.txt and .verification.json reports that verify the staged root, tarball, and tarball .sha256 sidecar together.
- abi/: dependency and symbol-version report.
- SHA256SUMS: checksums for package contents.

## Safe Smoke Test

Local smoke without live Compose or game containers:

\`\`\`bash
examples/smoke-linux-server-loader.sh
\`\`\`

On a host with the Funcom server image cached:

\`\`\`bash
cd ${package_name}
examples/smoke-cached-funcom-image.sh registry.funcom.com/funcom/self-hosting/seabass-server:1988751-0-shipping
\`\`\`

The smoke test uses \`--pull never --network none\` and exits after \`/usr/bin/true\`.
It does not touch live Compose containers.

## Live Canary Shape

For a live canary, copy \`lib/libdune_server_probe_loader.so\` into a path mounted
readable in the target game container, set the variables from
\`examples/env.scan.example\`, then restart exactly one chosen map through the
repo restart/recovery scripts so post-start hooks still run.

Keep \`DUNE_PROBE_LOADER_SCAN_ENABLED=false\` for normal operation after collecting
anchors.

## Reports

\`\`\`bash
TARGET_BINARY="\${TARGET_BINARY:-/path/to/DuneSandboxServer-Linux-Shipping}"
TARGET_FILTER_ARGS=(\${TARGET_FILTER_ARGS[@]:---exe-substring DuneSandboxServer --exe-substring DuneSandbox})
PACKAGE_SIGNATURE_FAMILY="\${PACKAGE_SIGNATURE_FAMILY:-LoadPackage}"

scripts/summarize-linux-loader-scan.py /path/to/loader.log
scripts/export-ue-anchor-env.py /path/to/loader.log --loader server --platform server > ue-server-anchors.env
scripts/summarize-linux-loader-xrefs.py "\$TARGET_BINARY" --loader-log /path/to/loader.log "\${TARGET_FILTER_ARGS[@]}" --category brt
scripts/summarize-linux-loader-anchors.py "\$TARGET_BINARY" --loader-log /path/to/loader.log "\${TARGET_FILTER_ARGS[@]}" --category brt
scripts/validate-elf-signatures.py "\$TARGET_BINARY" --loader-log /path/to/loader.log "\${TARGET_FILTER_ARGS[@]}" --category brt
scripts/export-elf-signature-manifest.py "\$TARGET_BINARY" --loader-log /path/to/loader.log --target-loader server "\${TARGET_FILTER_ARGS[@]}" --format signatures > server-signatures.txt
scripts/export-elf-signature-manifest.py "\$TARGET_BINARY" --loader-log /path/to/loader.log --target-loader server "\${TARGET_FILTER_ARGS[@]}" --category ue --format anchor-signatures > server-anchor-signatures.txt
scripts/summarize-ue-candidate-outcomes.py /path/to/loader.log --format markdown > ue-candidate-outcomes.md
scripts/summarize-ue-candidate-outcomes.py /path/to/loader.log --format json > ue-candidate-outcomes.json
scripts/summarize-ue-candidate-shapes.py /path/to/loader.log --format markdown > ue-candidate-shapes.md
scripts/summarize-ue-candidate-shapes.py /path/to/loader.log --format json > ue-candidate-shapes.json
scripts/summarize-ue-code-pointer-context.py "\$TARGET_BINARY" ue-candidate-outcomes.json --format markdown > ue-code-pointer-context.md
scripts/summarize-ue-vtable-candidates.py /path/to/loader.log --format markdown > ue-vtable-candidates.md
scripts/summarize-ue-vtable-candidates.py /path/to/loader.log --format json > ue-vtable-candidates.json
scripts/summarize-elf-ue-function-neighborhoods.py "\$TARGET_BINARY" --seed reviewed-function=0x0 --format markdown > elf-ue-function-neighborhoods.example.md
scripts/summarize-elf-ue-function-callgraph.py "\$TARGET_BINARY" --seed reviewed-function=0x0 --depth 1 --format markdown > elf-ue-function-callgraph.example.md
scripts/summarize-elf-ue-symbol-surface.py "\$TARGET_BINARY" --format markdown > ue-symbol-surface.md
scripts/summarize-elf-ue-symbol-surface.py "\$TARGET_BINARY" --format json > ue-symbol-surface.json
scripts/summarize-elf-ue-package-loader-vtables.py "\$TARGET_BINARY" --format markdown > ue-package-loader-vtables.md
scripts/summarize-elf-ue-package-loader-vtables.py "\$TARGET_BINARY" --format json > ue-package-loader-vtables.json
scripts/summarize-elf-ue-package-loader-vtables.py "\$TARGET_BINARY" --no-default-class-filters --address reviewed-table=0x0 --format markdown > ue-reviewed-table-vtables.md
scripts/summarize-elf-ue-package-wrapper-candidates.py "\$TARGET_BINARY" --package-loader-vtables-json ue-package-loader-vtables.json --vtable-filter FAsyncPackage2 --slot 66 --slot 69 --slot 94 --slot 95 --format markdown > ue-package-wrapper-candidates.md
scripts/summarize-elf-ue-package-wrapper-candidates.py "\$TARGET_BINARY" --package-loader-vtables-json ue-package-loader-vtables.json --vtable-filter FAsyncPackage2 --slot 66 --slot 69 --slot 94 --slot 95 --format json > ue-package-wrapper-candidates.json
scripts/summarize-elf-ue-package-static-wrapper-candidates.py "\$TARGET_BINARY" --format markdown > ue-package-static-wrapper-candidates.md
scripts/summarize-elf-ue-package-static-wrapper-candidates.py "\$TARGET_BINARY" --format json > ue-package-static-wrapper-candidates.json
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --static-wrapper-json ue-package-static-wrapper-candidates.json --format markdown > ue-rtti-function-object-vtables.md
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --static-wrapper-json ue-package-static-wrapper-candidates.json --format json > ue-rtti-function-object-vtables.json
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --format markdown > ue-package-symbol-surface-vtables.md
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --format json > ue-package-symbol-surface-vtables.json
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UPackage*' --symbol-needle EAsyncLoadingResult --format markdown > ue-async-package-delegate-vtables.md
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UPackage*' --symbol-needle EAsyncLoadingResult --format json > ue-async-package-delegate-vtables.json
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UKismetSystemLibrary::LoadAsset' --symbol-needle FLoadAssetAction --symbol-needle FLoadAssetClassAction --format markdown > ue-kismet-loadasset-vtables.md
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --symbol-surface-json ue-symbol-surface.json --symbol-needle 'UKismetSystemLibrary::LoadAsset' --symbol-needle FLoadAssetAction --symbol-needle FLoadAssetClassAction --format json > ue-kismet-loadasset-vtables.json
scripts/summarize-elf-ue-function-callgraph.py "\$TARGET_BINARY" --seed FLoadAssetActionBase_dispatch=0x0 --seed KismetLoadAsset_helper=0x0 --depth 2 --format markdown > ue-kismet-loadasset-callgraph.md
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --raw-typeinfo-needle FLinkerLoad --raw-typeinfo-needle FAsyncPackage --raw-typeinfo-needle FAsyncLoadingThread --raw-typeinfo-needle FAsyncArchive --format markdown > ue-raw-typeinfo-linker-async-vtables.md
scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --raw-typeinfo-needle FLinkerLoad --raw-typeinfo-needle FAsyncPackage --raw-typeinfo-needle FAsyncLoadingThread --raw-typeinfo-needle FAsyncArchive --format json > ue-raw-typeinfo-linker-async-vtables.json
read -r -a RAW_TYPEINFO_SEEDS <<< "\$(scripts/summarize-elf-ue-rtti-function-object-vtables.py "\$TARGET_BINARY" --raw-typeinfo-needle FLinkerLoad --raw-typeinfo-needle FAsyncPackage --raw-typeinfo-needle FAsyncLoadingThread --raw-typeinfo-needle FAsyncArchive --seed-limit 16 --format seeds)"
scripts/summarize-elf-ue-function-callgraph.py "\$TARGET_BINARY" "\${RAW_TYPEINFO_SEEDS[@]}" --depth 2 --format markdown > ue-raw-typeinfo-linker-async-callgraph.md
scripts/summarize-elf-writable-global-refs.py "\$TARGET_BINARY" --target reviewed-global=0x0 --format markdown > writable-global-reviewed.md
scripts/summarize-ue4ss-package-route-evidence.py --format markdown > ue4ss-package-route-evidence.md
scripts/summarize-ue4ss-package-route-evidence.py --format json > ue4ss-package-route-evidence.json
scripts/summarize-ue4ss-package-decompile-plan.py --format markdown > ue4ss-package-decompile-plan.md
scripts/summarize-ue4ss-package-decompile-plan.py --format json > ue4ss-package-decompile-plan.json
scripts/summarize-ue4ss-package-external-symbol-plan.py --format markdown > ue4ss-package-external-symbol-plan.md
scripts/summarize-ue4ss-package-external-symbol-plan.py --format json > ue4ss-package-external-symbol-plan.json
scripts/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format markdown > ue4ss-package-runtime-trace-plan.md
scripts/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format json > ue4ss-package-runtime-trace-plan.json
scripts/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format gdb > ue4ss-package-runtime-trace.gdb
scripts/plan-ue4ss-package-stimulus.py --format markdown > ue4ss-package-stimulus-plan.md
scripts/plan-ue4ss-package-stimulus.py --format json > ue4ss-package-stimulus-plan.json
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --format markdown > ue4ss-package-live-call-frame-recovery-plan.md
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --format json > ue4ss-package-live-call-frame-recovery-plan.json
PACKAGE_STIMULUS_TRACE_LOG="/tmp/ue4ss-package-runtime-trace-live-client-map-entry-\$(date -u +%Y%m%dT%H%M%SZ).log"
scripts/plan-ue4ss-package-stimulus-trace.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --live-plan-json ue4ss-package-live-call-frame-recovery-plan.json --external-plan ue4ss-package-external-symbol-plan.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --trace-plan-md ue4ss-package-runtime-trace-plan.md --method-candidates ue-package-loader-vtables.json --trace-log "\$PACKAGE_STIMULUS_TRACE_LOG" --format markdown > ue4ss-package-stimulus-trace-runbook.md
scripts/plan-ue4ss-package-stimulus-trace.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --live-plan-json ue4ss-package-live-call-frame-recovery-plan.json --external-plan ue4ss-package-external-symbol-plan.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --trace-plan-md ue4ss-package-runtime-trace-plan.md --method-candidates ue-package-loader-vtables.json --trace-log "\$PACKAGE_STIMULUS_TRACE_LOG" --format json > ue4ss-package-stimulus-trace-runbook.json
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --trace-runbook-json ue4ss-package-stimulus-trace-runbook.json --format markdown > ue4ss-package-live-call-frame-recovery-plan.md
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --trace-runbook-json ue4ss-package-stimulus-trace-runbook.json --format json > ue4ss-package-live-call-frame-recovery-plan.json
scripts/summarize-ue4ss-package-runtime-trace-evidence.py /tmp/ue4ss-package-runtime-trace-live.log --format markdown > ue4ss-package-runtime-trace-evidence.md
scripts/summarize-ue4ss-package-runtime-trace-evidence.py /tmp/ue4ss-package-runtime-trace-live.log --format json > ue4ss-package-runtime-trace-evidence.json
scripts/review-ue4ss-package-abi.py ue4ss-package-runtime-trace-evidence.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format markdown > ue4ss-package-abi-review.md
scripts/review-ue4ss-package-abi.py ue4ss-package-runtime-trace-evidence.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format json > ue4ss-package-abi-review.json
scripts/export-ue4ss-package-promotion-env.py ue4ss-package-runtime-trace-evidence.json --abi-review-json ue4ss-package-abi-review.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format markdown > ue4ss-package-promotion-env.md
scripts/export-ue4ss-package-promotion-env.py ue4ss-package-runtime-trace-evidence.json --abi-review-json ue4ss-package-abi-review.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format json > ue4ss-package-promotion-env.json
scripts/plan-ue4ss-package-server-replay.py --live-summary-json ue4ss-package-live-stimulus-review-summary.json --promotion-json ue4ss-package-promotion-env.json --promotion-env ue4ss-package-promotion-env.env --format markdown > ue4ss-package-server-replay-plan.md
scripts/plan-ue4ss-package-server-replay.py --live-summary-json ue4ss-package-live-stimulus-review-summary.json --promotion-json ue4ss-package-promotion-env.json --promotion-env ue4ss-package-promotion-env.env --format json > ue4ss-package-server-replay-plan.json
scripts/summarize-ue4ss-package-promotion-dir.py /tmp/ue4ss-package-family-reviews --format markdown > ue4ss-package-promotion-dir.md
scripts/summarize-ue4ss-package-promotion-dir.py /tmp/ue4ss-package-family-reviews --format json > ue4ss-package-promotion-dir.json
PACKAGE_NEXT_ACTION_INPUTS=(--promotion-summary-json ue4ss-package-promotion-dir.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --live-trace-runbook-json ue4ss-package-stimulus-trace-runbook.json)
[ -f ue4ss-package-runtime-trace-history.json ] && PACKAGE_NEXT_ACTION_INPUTS+=(--trace-history-json ue4ss-package-runtime-trace-history.json)
[ -f ue4ss-package-route-evidence.json ] && PACKAGE_NEXT_ACTION_INPUTS+=(--route-evidence-json ue4ss-package-route-evidence.json)
[ -f ue4ss-package-method-probe-refinement.json ] && PACKAGE_NEXT_ACTION_INPUTS+=(--method-probe-refinement-json ue4ss-package-method-probe-refinement.json)
scripts/plan-ue4ss-package-next-action.py "\${PACKAGE_NEXT_ACTION_INPUTS[@]}" --format markdown > ue4ss-package-next-action.md
scripts/plan-ue4ss-package-next-action.py "\${PACKAGE_NEXT_ACTION_INPUTS[@]}" --format json > ue4ss-package-next-action.json
scripts/summarize-ue4ss-port-gaps.py --server-log /path/to/loader.log "\${TARGET_FILTER_ARGS[@]}" --package-next-action-json ue4ss-package-next-action.json --format markdown > ue4ss-port-gaps.md
scripts/summarize-ue4ss-port-gaps.py --server-log /path/to/loader.log "\${TARGET_FILTER_ARGS[@]}" --package-next-action-json ue4ss-package-next-action.json --format json > ue4ss-port-gaps.json
PACKAGE_NEXT_ACTION_PROMOTION_INPUTS=(--promotion-json ue4ss-package-promotion-env.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --live-trace-runbook-json ue4ss-package-stimulus-trace-runbook.json)
[ -f ue4ss-package-runtime-trace-history.json ] && PACKAGE_NEXT_ACTION_PROMOTION_INPUTS+=(--trace-history-json ue4ss-package-runtime-trace-history.json)
[ -f ue4ss-package-route-evidence.json ] && PACKAGE_NEXT_ACTION_PROMOTION_INPUTS+=(--route-evidence-json ue4ss-package-route-evidence.json)
[ -f ue4ss-package-method-probe-refinement.json ] && PACKAGE_NEXT_ACTION_PROMOTION_INPUTS+=(--method-probe-refinement-json ue4ss-package-method-probe-refinement.json)
scripts/plan-ue4ss-package-next-action.py "\${PACKAGE_NEXT_ACTION_PROMOTION_INPUTS[@]}" --format markdown > ue4ss-package-next-action-from-promotion.md
scripts/plan-ue4ss-package-next-action.py "\${PACKAGE_NEXT_ACTION_PROMOTION_INPUTS[@]}" --format json > ue4ss-package-next-action-from-promotion.json
find /tmp/ue4ss-package-review-bundles -maxdepth 2 -name review-bundle-manifest.txt -o -name SHA256SUMS
scripts/verify-ue4ss-package-review-bundle.py /tmp/ue4ss-package-review-bundles/20260622T000000Z --format markdown > ue4ss-package-review-bundle-verification.md
scripts/verify-ue4ss-package-review-bundle.py /tmp/ue4ss-package-review-bundles/20260622T000000Z --format json > ue4ss-package-review-bundle-verification.json
scripts/audit-ue4ss-linux-port-completion.py --format markdown > ue4ss-linux-port-completion-audit.md
scripts/audit-ue4ss-linux-port-completion.py --format json > ue4ss-linux-port-completion-audit.json
scripts/plan-ue4ss-package-next-action.py --review-bundle /tmp/ue4ss-package-review-bundles/20260622T000000Z --format markdown > ue4ss-package-next-action-from-bundle.md
scripts/plan-ue4ss-package-next-action.py --review-bundle /tmp/ue4ss-package-review-bundles --format markdown > ue4ss-package-next-action-from-latest-bundle.md
scripts/summarize-linux-loader-scan.py /path/to/loader.log --format json > loader-summary.json
scripts/export-process-event-active-validation-candidates.py loader-summary.json --format markdown > process-event-active-validation-candidates.md
scripts/export-process-event-active-validation-candidates.py loader-summary.json --format json > process-event-active-validation-candidates.json
scripts/summarize-ue-root-recovery-queue.py elf-ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format markdown > ue-root-recovery-queue.md
scripts/summarize-ue-root-recovery-queue.py elf-ue-function-neighborhoods.json --candidate-outcomes-json ue-candidate-outcomes.json --format json > ue-root-recovery-queue.json
scripts/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format markdown > ue-root-recovery-clusters.md
scripts/cluster-ue-root-recovery-queue.py ue-root-recovery-queue.json --format json > ue-root-recovery-clusters.json
scripts/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform server --anchor-preset object-discovery --format markdown > ue-root-recovery-candidates.md
scripts/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform server --anchor-preset object-discovery --format json > ue-root-recovery-candidates.json
scripts/export-ue-root-recovery-candidates.py ue-root-recovery-queue.json --clusters-json ue-root-recovery-clusters.json --candidate-outcomes-json ue-candidate-outcomes.json --platform server --anchor-preset complete --require-source-group-match --format json > ue-root-recovery-candidates-complete-source-matched.json
scripts/prepare-ue-anchor-canary.py --platform server --binary "\$TARGET_BINARY" --loader-log /path/to/loader.log --output-dir build/server-anchor-canary
scripts/plan-ue4ss-canary-env.py --platform server --server-log /path/to/loader.log --hook-targets-json ue-vtable-candidates.json "\${TARGET_FILTER_ARGS[@]}" --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --active-validation-candidates-json process-event-active-validation-candidates.json --package-promotion-json ue4ss-package-promotion-env.json --max-stage read-only --format json > next-canary.json
scripts/plan-ue4ss-canary-env.py --platform server --server-log /path/to/loader.log --hook-targets-json ue-vtable-candidates.json "\${TARGET_FILTER_ARGS[@]}" --root-recovery-candidates-json ue-root-recovery-candidates.json --candidate-shapes-json ue-candidate-shapes.json --active-validation-candidates-json process-event-active-validation-candidates.json --package-promotion-json ue4ss-package-promotion-env.json --max-stage read-only > next-canary.env
scripts/ue4ss-port-readiness.py --server-log /path/to/loader.log --loader server "\${TARGET_FILTER_ARGS[@]}" --anchor-coverage-json build/server-anchor-canary/anchor-coverage.json --format json > ue4ss-readiness.json
scripts/summarize-ue4ss-port-gaps.py --readiness-json ue4ss-readiness.json --canary-plan-json next-canary.json --format markdown > ue4ss-port-gaps.md
scripts/summarize-ue4ss-evidence-inventory.py build backups /tmp --limit 12 --format markdown > ue4ss-evidence-inventory.md
scripts/summarize-ue4ss-package-route-evidence.py --format markdown > ue4ss-package-route-evidence.md
scripts/summarize-ue4ss-package-decompile-plan.py --format markdown > ue4ss-package-decompile-plan.md
scripts/summarize-ue4ss-package-external-symbol-plan.py --format markdown > ue4ss-package-external-symbol-plan.md
scripts/plan-ue4ss-package-runtime-trace.py --external-plan ue4ss-package-external-symbol-plan.json --base 0x100000 --format markdown > ue4ss-package-runtime-trace-plan.md
scripts/plan-ue4ss-package-stimulus.py --format markdown > ue4ss-package-stimulus-plan.md
scripts/plan-ue4ss-package-stimulus.py --format json > ue4ss-package-stimulus-plan.json
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --format markdown > ue4ss-package-live-call-frame-recovery-plan.md
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --format json > ue4ss-package-live-call-frame-recovery-plan.json
PACKAGE_STIMULUS_TRACE_LOG="/tmp/ue4ss-package-runtime-trace-live-client-map-entry-\$(date -u +%Y%m%dT%H%M%SZ).log"
scripts/plan-ue4ss-package-stimulus-trace.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --live-plan-json ue4ss-package-live-call-frame-recovery-plan.json --external-plan ue4ss-package-external-symbol-plan.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --trace-plan-md ue4ss-package-runtime-trace-plan.md --method-candidates ue-package-loader-vtables.json --trace-log "\$PACKAGE_STIMULUS_TRACE_LOG" --format markdown > ue4ss-package-stimulus-trace-runbook.md
scripts/plan-ue4ss-package-stimulus-trace.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --live-plan-json ue4ss-package-live-call-frame-recovery-plan.json --external-plan ue4ss-package-external-symbol-plan.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --trace-plan-md ue4ss-package-runtime-trace-plan.md --method-candidates ue-package-loader-vtables.json --trace-log "\$PACKAGE_STIMULUS_TRACE_LOG" --format json > ue4ss-package-stimulus-trace-runbook.json
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --trace-runbook-json ue4ss-package-stimulus-trace-runbook.json --format markdown > ue4ss-package-live-call-frame-recovery-plan.md
scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --trace-runbook-json ue4ss-package-stimulus-trace-runbook.json --format json > ue4ss-package-live-call-frame-recovery-plan.json
scripts/summarize-ue4ss-package-runtime-trace-evidence.py /tmp/ue4ss-package-runtime-trace-live.log --format markdown > ue4ss-package-runtime-trace-evidence.md
scripts/summarize-ue4ss-package-runtime-trace-evidence.py /tmp/ue4ss-package-runtime-trace-live.log --format json > ue4ss-package-runtime-trace-evidence.json
scripts/review-ue4ss-package-abi.py ue4ss-package-runtime-trace-evidence.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format markdown > ue4ss-package-abi-review.md
scripts/review-ue4ss-package-abi.py ue4ss-package-runtime-trace-evidence.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format json > ue4ss-package-abi-review.json
scripts/export-ue4ss-package-promotion-env.py ue4ss-package-runtime-trace-evidence.json --abi-review-json ue4ss-package-abi-review.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format markdown > ue4ss-package-promotion-env.md
scripts/export-ue4ss-package-promotion-env.py ue4ss-package-runtime-trace-evidence.json --abi-review-json ue4ss-package-abi-review.json --signature-family "\$PACKAGE_SIGNATURE_FAMILY" --format json > ue4ss-package-promotion-env.json
scripts/summarize-ue4ss-package-promotion-dir.py /tmp/ue4ss-package-family-reviews --format markdown > ue4ss-package-promotion-dir.md
scripts/verify-loader-artifacts.py --target linux-server --package-root . --package-target linux-server --package-only --format text > loader-artifact-verification.txt
scripts/verify-loader-artifacts.py --target linux-server --package-root . --package-target linux-server --package-only --format json > loader-artifact-verification.json
scripts/ue4ss-portability-contract.py --targets available --format markdown --check > ue4ss-portability-contract.md
python3 -m unittest tests/test-linux-loader-scan-summary.py tests/test-ue4ss-port-readiness.py tests/test-ue4ss-port-gaps.py tests/test-ue4ss-portability-contract.py tests/test-ue4ss-evidence-inventory.py tests/test-verify-loader-artifacts.py tests/test-ue4ss-package-route-evidence.py tests/test-ue4ss-package-decompile-plan.py tests/test-ue4ss-package-external-symbol-plan.py tests/test-ue4ss-package-runtime-trace-plan.py tests/test-ue4ss-package-runtime-trace-evidence.py tests/test-ue4ss-package-stimulus.py tests/test-ue4ss-package-stimulus-trace.py tests/test-ue4ss-package-live-call-frame-recovery.py tests/test-ue4ss-package-server-replay.py tests/test-export-ue4ss-package-promotion-env.py tests/test-ue4ss-package-promotion-dir-summary.py tests/test-ue4ss-package-next-action.py tests/test-verify-ue4ss-package-review-bundle.py tests/test-verify-ue4ss-package-route-slot-recovery.py tests/test-verify-ue4ss-package-live-stimulus-summary.py tests/test-verify-ue4ss-package-live-preflight-summary.py tests/test-verify-ue4ss-package-prearm-readiness.py tests/test-audit-ue4ss-linux-port-completion.py tests/test-review-ue4ss-package-abi.py tests/test-ue4ss-package-runtime-trace-runner.py tests/test-loader-scheduler-api-parity.py tests/test-loader-modref-api-parity.py tests/test-loader-mod-lifecycle-api-parity.py tests/test-loader-unregister-api-parity.py tests/test-loader-fname-api-parity.py tests/test-loader-native-identity-parity.py tests/test-loader-custom-property-api-parity.py tests/test-loader-compat-globals-api-parity.py tests/test-loader-world-engine-api-parity.py tests/test-loader-object-notify-api-parity.py tests/test-loader-console-command-api-parity.py tests/test-loader-anchor-group-parity.py tests/test-loader-scan-preset-parity.py tests/test-export-ue-candidate-globals.py tests/test-ue-candidate-outcomes.py tests/test-ue-candidate-shapes.py tests/test-ue-code-pointer-context.py tests/test-ue-vtable-candidates.py tests/test-elf-ue-function-neighborhoods.py tests/test-elf-ue-function-callgraph.py tests/test-elf-ue-package-loader-vtables.py tests/test-elf-ue-package-wrapper-candidates.py tests/test-elf-ue-package-static-wrapper-candidates.py tests/test-elf-ue-rtti-function-object-vtables.py tests/test-export-process-event-active-validation-candidates.py tests/test-elf-writable-global-refs.py tests/test-elf-writable-root-shapes.py tests/test-ue-root-recovery-queue.py tests/test-ue-root-recovery-clusters.py tests/test-export-ue-root-recovery-candidates.py tests/test-promote-ue-anchor-xref-candidates.py tests/test-prepare-ue-anchor-canary.py tests/test-plan-ue4ss-canary-env.py
\`\`\`

\`export-ue-anchor-env.py\` exports core discovery anchors plus reflection
anchors by default, including anchors from resolved \`ue-anchor-signature\`
records. Unresolved and ambiguous signature anchors remain missing.
\`prepare-ue-anchor-canary.py\` combines the validated UE signature manifest,
loader-consumable anchor signature file, second-pass anchor env, validation
summary, readiness report, object-discovery coverage, and
\`post-canary-verify.sh\` in one output directory. After the next canary, run
\`post-canary-verify.sh [loader-log]\` from that output directory to rebuild
readiness, object-discovery coverage, the UE4SS gap summaries
(\`ue4ss-port-gaps.json\` and \`ue4ss-port-gaps.md\`), and a compact
post-canary summary from the collected log.
\`post-canary-verify-strict.sh [loader-log]\` sets
\`DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true\` and fails until
\`strictRuntimeContract.contractReady=true\`, including \`runtimeRootDiscovery\`.
\`DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true\` also requires
\`summarize-ue4ss-evidence-inventory.py\` to write
\`ue4ss-evidence-inventory.json\` and \`ue4ss-evidence-inventory.md\`; strict
canaries run the inventory with \`--require-complete\` and must not treat
missing or incomplete inventory as a best-effort side artifact.
Runtime root discovery means both \`RuntimeFNamePool\` and
\`RuntimeGUObjectArray\` are validated by FName/object-array consumers, not just
mapped or promoted. Strict readiness also requires exact/promotable signature
validation, target-image \`targetObjectDiscovery\`,
\`targetHooks\`, and \`targetPackageLoadingSurface\` evidence,
\`signatureAnchorReady=true\`, and no \`missingSignatureAnchorReadyKeys\`.
For a bounded ambiguous-root canary, set
\`DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_PROMOTE_AMBIGUOUS_ROOTS=true\`; the loader
promotes \`RuntimeFNamePoolCandidate<N>\` and
\`RuntimeGUObjectArrayCandidate<N>\` anchors so the same consumers can validate
the real root without a second explicit replay. The canary planner emits this
as \`promoteAmbiguousRoots\` for same-run FName/object-array validation when
bounded ambiguous root evidence is present.
The full UE4SS completion gate remains \`ue4ssLuaApiComplete=true\`, which also
requires \`liveTargetImageCanaryContract.ready=true\` across
\`targetImageAnchors\`, \`runtimePackageLoading\`, \`runtimeObjectRegistry\`,
\`runtimeReflection\`, and
\`runtimeProcessEventDispatch\`/\`runtimeCallFunctionDispatch\`;
self-test-only logs are not enough.
The \`runtimeProcessEventDispatch\` group requires more than a live hook row:
decoded live function path, runtime registry context, active params, raw and
container param samples, Lua context handles, descriptor-backed param accessors,
typed scalar/name/string/struct/enum/object/bool accessor coverage, container
alias/layout methods, and hook routing/alias routing must all be present.
It also requires \`luaProcessEventNativeInvokeNonSelfTestInvoked=true\`, proving
an explicitly enabled descriptor-backed non-self-test ProcessEvent target was
invoked through the Lua native bridge.
In short: container alias/layout methods are required, not optional.
The \`runtimeCallFunctionDispatch\` group requires
\`luaCallFunctionNativeInvokeNonSelfTestInvoked=true\`, proving an explicitly
enabled non-self-test CallFunction target was invoked through the Lua native
bridge.
The \`runtimePackageLoading\` group treats \`luaLoadAssetPackageNativeExecutor\`
as ready only when target-image evidence reports \`NativeExecutorReady=true\`,
\`ExecutorPreflightPassed=true\`, and \`FinalNativeCallEligible=true\`;
dry-run executor shape rows remain diagnostic only.
It also requires \`luaLoadAssetPackageNativeInvocation=true\`, proven by
\`lua-load-asset-package-native-invoke nativeInvoked=true nativeCallable=true
targetImage=true nativeReturnValidated=true\`; executor readiness alone is not
package-load completion.
The same group also requires the package-backed \`LoadClass\` chain:
\`luaLoadClassPackageAbiState=true\`,
\`luaLoadClassPackageCallFrameVerification=true\`,
\`luaLoadClassPackageNativeExecutor=true\`, and
\`luaLoadClassPackageNativeInvocation=true\` from target-image
\`StaticLoadClass\` evidence. The \`runtimeObjectRegistry\` group similarly
requires guarded target-image \`StaticConstructObject\` executor state,
executor readiness, and native invocation evidence before synthetic
construction counts toward 1:1 object API parity.
After \`ue4ss-package-runtime-trace.sh status\` emits a ready ABI review,
promotion remains blocked until the reviewer reruns status/export with explicit
review flags. The runtime trace captures bounded register memory snapshots as
\`registerMemory\`; use the ABI review's per-argument \`memoryLines\` counts and
samples to verify package-name/TCHAR pointer arguments before setting review
flags. Required path/name pointer roles such as \`Name\` and \`PackageName\`
must have register-memory snapshots before ABI review is considered ready; a
non-null pointer value alone is not enough. ABI review also requires selected
trace hit seed provenance plus \`callerImageOffset\` and \`ripImageOffset\`
call-frame provenance from the selected trace hit before it can report ready for
manual ABI review; the ABI review manifest and markdown carry the
\`selectedHitSeed\`, and the ABI review markdown prints both the caller and RIP image
offsets so reviewers see the complete call-frame identity. These
snapshots are supporting review evidence only; they do not bypass
the target-image, ABI, TCHAR/class-root, or native-invoke confirmation gates.
For non-Dune targets, \`DUNE_UE4SS_PACKAGE_TRACE_PID\` can point the runtime
trace wrapper at an explicit process without Docker discovery. Explicit PID
traces default their host guard to the current host unless
\`DUNE_UE4SS_PACKAGE_TRACE_HOST\` is explicitly set; Docker/container traces still
default to \`kspls0\`. When no container/target label is supplied, explicit PID
traces use a neutral \`pid-<pid>\` label in wrapper output, review-bundle
manifests, and next-action replay commands instead of the Dune default
container name. When no explicit PID is supplied,
\`DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN\` overrides the docker-top process
regex while the default remains
\`DuneSandboxServer-Linux-Shipping\`. The runtime trace status wrapper passes
that explicit PID into next-action replay commands and records it as
\`tracePid\` in review-bundle manifests. When an explicit trace host is set, the
wrapper also passes \`DUNE_UE4SS_PACKAGE_TRACE_HOST\` into next-action replay
commands and records \`traceHost\` in review-bundle manifests; bundle
verification requires copied next-action trace env to match both values.
The ABI review also emits conservative \`candidateTcharLayouts\` hints from
quoted GDB strings and captured byte patterns; use those hints to choose the
\`DUNE_UE4SS_PACKAGE_TRACE_TCHAR_UNIT_BYTES\` review flag, not as automatic
promotion proof. ABI review and promotion export require explicit
\`sourceLogExists=true\` trace provenance. Promotion export also requires ABI review \`selectedHitSeed\`
plus call-frame \`callerImageOffset\` / \`ripImageOffset\` fields to be present
and match the selected trace hit, and the selected trace hit must carry both offsets itself;
missing provenance blocks the promotion manifest instead of producing ready
canary env.
The canary planner carries package promotion evidence and
\`candidateTcharLayouts\` into plan notes so the trace-to-env audit trail is
visible beside emitted package env values. Promotion directory summaries demote
claimed-ready manifests that still carry blockers, ABI blockers, missing review
flags, missing \`abiReviewReady\`, missing \`abiReviewed\`, missing \`sourceEvidence\`,
missing \`targetImageReviewed\`, missing family review confirmation
(\`tcharReviewed\` or \`classRootReviewed\`), missing \`sourceLogExists\`,
\`sourceLogExists=false\`, non-concrete \`hitIndex\`, or missing
\`callerImageOffset\` / \`ripImageOffset\` provenance so stale or hand-edited
ready booleans do not reach canary planning.
Native-ready manifests must also
be ready for the non-invoking canary first; native-only ready claims are
demoted by promotion summaries, rejected by direct canary planning, blocked by
review-bundle verification, and treated as next-action validation errors.
Direct
\`--package-promotion-json\` inputs and next-action summary rows are rejected
with the same ready-claim checks before any package env or canary command is
emitted. Promotion export blocks selected trace hits that are missing seed
provenance, and promotion directory summaries plus direct package promotion
inputs with an embedded selected \`hit\` also reject identity drift: the hit seed
must match the manifest-level \`signatureFamily\`, newly exported manifests
carry top-level \`selectedHitSeed\` provenance for the same selected hit, and
\`hit.callerImageOffset\` / \`hit.ripImageOffset\` must
match the manifest-level \`callerImageOffset\` and \`ripImageOffset\`; embedded
hits with \`traceAddressMatchesBase=false\` are demoted because the captured
watchpoint address does not match image base plus seed imageOffset. Promotion
summaries must also keep ready rows and
\`readyManifestPaths\` closed over the same manifest set; a ready row omitted
from \`readyManifestPaths\`, or a listed ready path without a ready row, blocks
canary planning and review-bundle verification. Promotion export emits only
family-specific env keys, and promotion env keys must match the selected package
family, so \`StaticLoadClass\` manifests cannot emit LoadAsset package keys and
LoadAsset-family manifests cannot emit LoadClass package keys. Promotion
directory summaries and review-bundle verification enforce the same family env
key shape before marking copied manifests ready, and promotion directory
summaries demote ready \`runtime-trace:<family>\` env evidence whose family label
or \`seed=...\` marker does not match manifest-level \`signatureFamily\`.
\`ue4ss-package-runtime-trace.sh status\` also writes a timestamped
\`dune-ue4ss-package-review-bundle/v1\` directory under
\`DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_DIR\` with copied trace evidence,
ABI review, promotion manifests, next-action output, trace-plan provenance
(\`tracePlanSourceExternalPlan\`, \`tracePlanBase\`,
\`tracePlanExpectedBuildId\`, \`tracePlanRuntimeBuildId\`,
\`tracePlanSeedCount\`, \`tracePlanSeedOffsets\`,
\`tracePlanSelectedByFamily\`, and
\`tracePlanBlockerCount\`), recommended trace env provenance
(\`tracePlanRecommendedAnchor\`, \`tracePlanRecommendedLimit\`,
\`tracePlanRecommendedSignatureFamily\`, and
\`tracePlanRecommendedHitIndex\`), process selector provenance
	(\`processPattern\`, optional \`tracePid\`, and optional \`traceHost\`), live player-guard provenance
	(\`playerGuardPhase\`, \`playerGuardPartition\`, and
	\`playerGuardConnectedPlayers\`), trace evidence source provenance
(\`sourceLogExists\`, \`sourceLogSha256\`, \`sourceEvidenceJson\`,
\`sourceEvidenceJsonSha256\`, and \`tracePidMatchesRequested\`), image range provenance
(\`evidencePid\`, \`imageRangeSource\`, \`imageBase\`, \`imageStart\`,
\`imageEnd\`, \`imagePath\`, and \`imagePerms\`), and \`SHA256SUMS\` so a
post-trace review can be replayed without guessing which /tmp files matched.
\`verify-ue4ss-package-review-bundle.py\` validates that bundle's schema,
required artifacts, JSON schema versions, checksum coverage, SHA256 integrity,
top-level trace/ABI/promotion identity, \`callerImageOffset\` /
\`ripImageOffset\` provenance where present, ABI-review-to-promotion offset
and \`selectedHitSeed\` matches even when trace-hit lookup is unavailable, and nested per-family
promotion schema/family consistency before the bundle is trusted for manual
review or canary planning. Its markdown output includes the bundle \`traceLog\`
so replay reviews can see the exact trace source. If a copied \`ue4ss-package-family-reviews.json\`
summary is present, it must also be listed in \`review-bundle-manifest.txt\`
artifact rows so replay can prove where that summary came from. Bundled
top-level and per-family promotion manifests
that claim ready while carrying blockers, missing review/native flags, or
	missing trace identity, missing \`sourceLogExists\`, \`sourceLogExists=false\`,
	missing \`sourceEvidenceJson\`, missing \`sourceEvidenceJsonSha256\`, missing
	\`sourceLogSha256\`, missing \`tracePidMatchesRequested\`,
	\`tracePidMatchesRequested=false\`, or call-frame provenance
	block bundle verification. Top-level ABI review artifacts with
\`sourceLogExists=false\` also block bundle verification before their promotion
manifest is trusted. Top-level ABI review, top-level promotion, and nested
per-family promotion \`sourceLogExists\`, \`sourceLogSha256\`, and
	\`sourceEvidenceJsonSha256\` values must also match the copied runtime trace
	evidence so stale artifacts cannot silently inherit a newer trace source.
	Live \`traceHost=kspls0\` bundles must also record \`playerGuardPhase=status\`,
	numeric \`playerGuardPartition\`, and \`playerGuardConnectedPlayers=0\`, so
	promotion evidence cannot outlive the zero-player status guard.
	Native-ready promotion manifests and copied summary rows also require
\`readyForNonInvokingCanary=true\`; native-only ready claims block bundle
verification.
Nested per-family promotion manifests are also checked against
the bundled runtime trace \`sourceEvidence\`, \`sourceLogExists\`,
\`sourceLogSha256\`, \`sourceEvidenceJsonSha256\`, \`tracePidMatchesRequested\`, selected \`hitIndex\`,
and \`callerImageOffset\` / \`ripImageOffset\` call-frame identity so a copied or
stale family review cannot be promoted through a newer bundle.
The bundle also carries replay commands from \`ue4ss-package-next-action.json\`.
For \`arm-trace\` actions, verification requires replay commands for both
\`arm\` and \`status\`, requires each replay command to reference the manifest
\`container\` and \`traceLog\`, and rejects unexpected
\`DUNE_UE4SS_PACKAGE_TRACE_*\` assignments that are not present in the runtime
trace plan (except the process selector, explicit \`tracePid\`, and explicit
\`traceHost\`). Trace env values copied into replay
commands must match the runtime trace plan exactly. The bundled trace plan's
\`recommendedTraceEnv\` must also match the hardware-safe selected trace seed
count (the selected trace seed count capped by the hardware watchpoint limit)
and selected trace seed families, so stale anchor or limit recommendations
cannot be replayed as ready evidence. The review-bundle manifest mirrors the
recommended anchor, limit, signature family, and hit-index values and verifier
checks those plain-text fields against the copied runtime trace plan JSON.
The live trace runbook and next-action summary also carry a \`cleanupCommand\`;
the remote wrapper validates that it is the matching \`stop\` command for the
same remote, container, and \`traceLog\` before any non-cleanup SSH handoff, and
bundle verification rejects stale or missing cleanup identity in copied
runbook/next-action artifacts.
Use
\`scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-\$(date -u +%Y%m%dT%H%M%SZ).log\`
as the final remote validation for a fresh timestamped trace log before a real
operator stimulus window; it runs the same coordinator/runbook identity checks
and remote preflight without arming gdb, and writes
\`build/server-current-anchor-prep/ue4ss-package-live-preflight-summary.json\`
with the preflight host, container, trace log, and zero-player guard fields.
After the fresh preflight passes in the approved window, use
\`scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-\$(date -u +%Y%m%dT%H%M%SZ).log\`
with the same timestamped trace-log pattern to arm the bounded live trace,
perform the approved login/travel/map-entry stimulus, collect status, stop the
trace, and write the local review summary.
The coordinator writes the local live stimulus review summary from the remote
review-bundle verifier and embeds \`reviewBundleVerification\`,
\`reviewBundleVerificationSha256\`, \`routeSlotRecoveryVerification\`,
\`routeSlotRecoveryVerificationSha256\`, \`prearmReadinessVerification\`, and
\`prearmReadinessVerificationSha256\`, so the final local summary remains
self-contained after the remote \`/tmp\` verifier path expires. Treat
\`verify-ue4ss-package-live-stimulus-summary.py\` as the final local acceptance
gate; it rejects claimed-ready summaries that lack readable or embedded verifier
evidence. When \`--trace-log\` is used, the coordinator verifies the local summary
against the temporary effective runbook that carries the overridden trace log,
while preserving the original generated runbook as \`sourceRunbook\`.
When route-slot recovery is still pending, run
\`scripts/verify-ue4ss-package-route-slot-recovery.py <ue4ss-package-runtime-trace-evidence.json> --next-action-json ue4ss-package-next-action.json\`.
Its non-ready output carries \`nextTraceRequirement\`; the next live trace must
produce \`UE4SS_PACKAGE_ROUTE_TRACE_HIT\` evidence with
\`routeVtableStaticSlotMatches\` for the required route, missing slots, and
missing registers. The generated stimulus runbook also carries the same
machine-readable \`routeSlotTraceRequirement\` object, with
\`expectedTraceMarker=UE4SS_PACKAGE_ROUTE_TRACE_HIT\`,
\`reviewField=routeVtableStaticSlotMatches\`, \`requiredSlots=[0x3a0,0x3d8]\`,
and \`requiredRegisters=[rbx,r14]\`. Bundle verification, prearm readiness, and
the completion audit reject stale next-action or runtime evidence whose
route-slot requirement no longer matches that runbook object. Bundle
verification also rejects stale runtime trace plans whose \`routeGdb\` omits the
required route address, \`UE4SS_PACKAGE_ROUTE_TRACE_HIT\`, required register
prints, or required object/vtable capture blocks for those registers. The
current Dune handoff expects route \`0x129d58a2\`, slots \`0x3a0, 0x3d8\`, and
registers \`rbx, r14\` until the verifier reports ready.
For \`plan-canary\` actions, bundle verification requires the canary planning
commands to consume bundled promotion inputs and, when bundled
\`ue4ss-package-next-canary.json\` or \`ue4ss-package-next-canary.env\`
artifacts are present, to write the same source paths recorded in
\`review-bundle-manifest.txt\`. Stale next-canary output redirections block
bundle verification so replay cannot accidentally inspect canary artifacts from
a different promotion run. New next-action JSON also carries structured
\`outputFiles.nextCanaryJson\` and \`outputFiles.nextCanaryEnv\` values; bundle
verification accepts those fields as machine-readable proof of the same
next-canary output paths while still supporting shell redirection parsing for
older bundles.
\`plan-ue4ss-package-next-action.py --review-bundle <bundle>\` verifies the
bundle first, then derives the next review/canary command from the bundled
family summary, bundled per-family review directory, or promotion manifest plus
the bundled runtime trace plan. When the bundled per-family review directory is
present, next-action prefers it over copied summary paths so replay stays
self-contained. If it falls back to the bundled top-level promotion manifest,
the synthesized summary row preserves \`sourceEvidence\`, \`sourceEvidenceJson\`,
\`sourceEvidenceJsonSha256\`, \`sourceLogSha256\`, \`sourceLogExists\`,
\`tracePidMatchesRequested\`, \`hitIndex\`, \`callerImageOffset\`, \`ripImageOffset\`, \`abiReviewReady\`, and
\`abiReviewed\`, \`targetImageReviewed\`, \`tcharReviewed\`, and
\`classRootReviewed\` so single-manifest replay keeps the same trace identity surface
as per-family summaries.
Next-action also treats claimed-ready summary rows with blockers, missing
review/native flags, missing \`abiReviewReady\`, missing \`abiReviewed\`, missing
\`targetImageReviewed\`, missing family review confirmation (\`tcharReviewed\`
or \`classRootReviewed\`), missing \`sourceEvidence\`, missing \`sourceLogExists\`,
\`sourceLogExists=false\`, missing \`tracePidMatchesRequested\`,
\`tracePidMatchesRequested=false\`, non-concrete \`hitIndex\`, missing \`selectedHitSeed\`,
or missing call-frame provenance as validation errors before it recommends canary planning. It also rejects native-ready rows
that are not ready for the non-invoking canary, so the shortest-path command
cannot skip the non-invoking package ABI/call-frame gate. Copied summary rows that include
\`reviewPriority\` or
\`reviewPriorityHitIndex\` must also match the adjacent \`review-priority.json\`
before either standalone canary planning or next-action planning can consume
them, preventing stale review ordering metadata from steering package canaries.
Passing the bundle root, for example
\`--review-bundle /tmp/ue4ss-package-review-bundles\`, selects the newest timestamped bundle directory.
The trace evidence summary also emits \`familyCandidates\` / \`Family Candidates\`
plus \`reviewPriority\`, \`concreteReviewPriority\`, and \`recommendedReview\`,
mapping each captured package family to the hit index that \`--hit-index auto\`
will review only after call-frame offsets are concrete. Candidates expose
\`missingCallFrameOffsets\` and \`missingRequiredMemoryRegisters\` and are
excluded from \`recommendedReview\` when \`callerImageOffset\` or
\`ripImageOffset\` is missing, or when required package ABI argument registers
were not captured in \`registerMemory\` / \`memoryLines\`. ABI review, promotion
export, ready package promotion summaries, review-bundle verification,
next-action planning, and canary planning all reject embedded trace hits that
report missing required memory registers; direct rejection messages include
\`embedded trace hit is missing required memory registers\`. Those rows are also
penalized in review scoring. Candidate scoring and markdown distinguish
\`targetImageRip\` from \`targetImageCaller\` so a target-image caller cannot
hide a non-target RIP frame. The markdown
\`Family Candidates\` section prints \`ripImageOffset\`, \`targetImageRip\`, and a
\`missing call-frame offsets:\` line so missing provenance is visible during
manual review, not only in JSON. The status wrapper
uses \`reviewPriority\` to write per-family reviews in fastest-promotable order
and records each family rank as \`review-priority.json\`. Per-family ABI review
and promotion export prefer \`concreteReviewPriority\` before legacy
\`familyCandidates\`, then reuse that recorded hit index, so replay stays attached
to the same concrete candidate that the trace evidence ranked. \`--hit-index auto\`
does not fall back to raw family candidates when no concrete review candidate
exists for the requested signature family. Per-family review generation
requires concrete integer hit indexes and skips malformed candidate rows instead
of writing ambiguous \`auto\` review metadata.
Check that section before setting review flags. Select the reviewed family with
\`DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=<family>\` for the wrapper or
\`PACKAGE_SIGNATURE_FAMILY=<family>\` for the standalone commands; supported
families are \`StaticLoadObject\`, \`StaticLoadClass\`, \`LoadObject\`,
\`LoadPackage\`, and \`ResolveName\`. Multi-anchor traces default
\`DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject\` and
\`DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage\` because the current server external-symbol plan exposes \`LoadPackage\` and \`LoadObject\` string
seeds, but not \`StaticLoadObject\`, \`StaticLoadClass\`, or \`ResolveName\`
seeds.
\`ue4ss-package-runtime-trace-plan.md\` includes a Recommended wrapper env line
with the matching selected anchor, selected seed count limit, signature family,
and auto hit-index settings.
\`ue4ss-package-runtime-trace-plan.json\` also carries trace-plan blockers such
as missing requested anchors or no selected seeds. The runtime trace wrapper
refuses to arm GDB when those blockers are present, the next-action planner
emits \`refresh-trace-plan\` instead of \`arm-trace\`, and review-bundle
verification rejects copied bundles whose runtime trace plan still has blockers.
\`DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto\`, which selects the first captured
hit whose seed matches the selected signature family. The status command also
writes per-family ABI review and promotion manifests under
\`DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_DIR\` (default
\`/tmp/ue4ss-package-family-reviews\`) so a multi-anchor trace can be reviewed
without manually rerunning status for every family. Its next-canary preview
passes the generated summary as \`--package-promotion-summary-json\` so only
ready manifest paths are applied; standalone canary planning can use the same
argument or \`--package-promotion-dir\`. Raw directory canary planning also
honors \`review-priority.json\` ordering. blocked manifests remain closed by the canary planner.
The status command also writes \`ue4ss-package-promotion-dir.md\`-style summary
output with Ready for non-invoking canary counts, readyManifestPaths, and
missing review flag rows. It includes \`reviewPriority\` ranks and per-family
review hit indexes, \`callerImageOffset\` / \`ripImageOffset\` call-frame
provenance, \`tracePid\` plus image range identity
(\`imageRangeSource\`, \`imageBase\`, \`imageStart\`, \`imageEnd\`,
\`imagePath\`, and \`imagePerms\`), copied package env evidence, embedded trace-hit identity,
and blockers so the fastest promotable family is visible at a
glance; malformed \`review-priority.json\` metadata, including invalid hit
indexes, promotion-manifest family mismatches, promotion manifest
\`signatureFamily\` / parent-directory mismatches, and concrete
\`review-priority.json\` hit-index drift from the promotion manifest, is
reported as summary errors and demotes otherwise ready rows out of
\`readyManifestPaths\` until the priority metadata is regenerated.
The next-action planner reads the promotion summary and runtime trace plan to
emit the shortest current command path: canary planning for ready manifests,
review/status reruns for blocked manifests, or the recommended runtime trace
environment when no promotable manifest exists. It also repeats promotion
summary errors and blocks package canary planning while malformed review
metadata remains present during handoff. When only the top-level
\`ue4ss-package-promotion-env.json\` exists, use
\`plan-ue4ss-package-next-action.py --promotion-json ue4ss-package-promotion-env.json\`;
the runtime trace status wrapper uses that as a fallback when no generated
all-family summary exists, so a ready single-family promotion manifest is not
ignored. That single-manifest planner path preserves the same \`tracePid\` and
image range identity fields as \`summarize-ue4ss-package-promotion-dir.py\`.
Feed \`ue4ss-package-next-action.json\` into
\`summarize-ue4ss-port-gaps.py --package-next-action-json\` when rendering the
overall 1:1 gap summary. That input is schema-checked as
\`dune-ue4ss-package-next-action/v1\` and must carry a non-empty string
\`action\`, string \`commands\` entries, object \`traceEnv\`, non-empty
\`traceEnv\` keys, scalar \`traceEnv\` values, and well-formed
\`promotionSummaryErrors\` rows when malformed package promotion review
metadata is present. Passing a runtime trace plan, malformed next-action file,
or other JSON artifact is rejected instead of silently dropping the package trace
commands from \`Next Steps\`. Promotion metadata errors are rendered as
\`package promotion metadata error\` next steps so a bad
\`promotion-env.json\`, \`review-priority.json\`, or generated family summary
does not hide behind a generic package-loading gap.
Set a numeric hit index only when deliberately reviewing a specific
captured hit. For
\`StaticLoadClass\`, set
\`DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_TARGET_IMAGE=1\`,
\`DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_ABI=1\`, and
\`DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_CLASS_ROOT=1\`. For asset/package
families, set \`DUNE_UE4SS_PACKAGE_TRACE_REVIEWED_TCHAR=1\` and
\`DUNE_UE4SS_PACKAGE_TRACE_TCHAR_UNIT_BYTES=<1|2|4>\` instead of the class-root
flag. Native invocation additionally requires
\`DUNE_UE4SS_PACKAGE_TRACE_ALLOW_NATIVE_INVOKE=1\` and
\`DUNE_UE4SS_PACKAGE_TRACE_FINAL_NATIVE_CALL=1\`.
\`ue4ss-port-readiness.py\` auto-scopes mixed-process logs to loaded
\`DuneSandbox\` target PIDs when no explicit \`--pid\` or \`--exe-substring\`
filter is supplied. Strict completion requires \`targetImageProcess=true\` and
validated \`runtimeRootDiscovery=true\`; helper shell/tool process evidence,
mapped-only runtime roots, or self-test-only logs cannot satisfy target-image
runtime proof.
\`canary-linux-server-loader.sh\` writes \`ue-vtable-candidates.json\`,
\`ue-vtable-candidates.md\`, \`next-canary-plan.json\`,
\`next-canary-plan.env\`, and \`next-canary-plan.md\` into the canary backup
directory, using any ranked vtable shortlist as \`--hook-targets-json\` input
for the next guarded server plan. After review, pass that JSON back through
\`DUNE_LINUX_SERVER_CANARY_PLAN_JSON=<backup-dir>/next-canary-plan.json\` to run
the next scoped canary.
\`plan-ue4ss-canary-env.py\` reads readiness evidence and emits the next guarded
canary env. It defaults to read-only discovery/reflection and only emits
ProcessEvent/CallFunction hook or live Lua dispatch flags when \`--max-stage\`
allows them. Use \`--package-promotion-json ue4ss-package-promotion-env.json\`
after package ABI review, \`--package-promotion-summary-json
/tmp/ue4ss-package-family-reviews.json\` after a multi-family trace review, or
\`--package-promotion-dir /tmp/ue4ss-package-family-reviews\` for raw directory
loading; blocked promotion manifests are noted but do not emit package env,
while reviewed manifests are translated to the selected loader prefix for the
next canary.
\`ue4ss-package-promotion-env.json\` must carry
\`promotionAcceptanceSchemaVersion=dune-ue4ss-package-anchor-promotion-acceptance/v1\`;
the promotion directory summarizer, review-bundle verifier, next-action planner,
and canary planner reject ready package promotion artifacts that omit that
current package anchor promotion acceptance schema.
\`ue4ss-package-runtime-trace.sh status\` writes the same JSON manifest to
\`DUNE_UE4SS_PACKAGE_TRACE_PROMOTION_JSON\`, defaulting to
\`/tmp/ue4ss-package-promotion-env.json\`.
Each status run clears stale generated evidence, ABI review, promotion,
all-family summary, generated per-family review directory, next-action, and
next-canary artifacts before rebuilding them, so failed or no-candidate status
runs cannot accidentally reuse an older ready manifest or family review. The
canary planner also rejects a ready package promotion
manifest when its \`runtime-trace:<family>\` env evidence label or \`seed=...\`
marker conflicts with manifest-level \`signatureFamily\`, when its env evidence
\`caller=...\` marker conflicts with the manifest-level \`callerImageOffset\`,
or when a \`runtime-trace:\` env evidence \`rip=...\` marker conflicts with
\`ripImageOffset\`, or when its embedded trace hit reports
\`missingRequiredMemoryRegisters\`.
\`live-hook\` and \`lua-dispatch\` plans also enable bounded live ProcessEvent
call logging so \`ue-process-event-live-context\` and
\`ue-process-event-live-param\` readiness evidence is collected. The planner
also requires non-self-test ProcessEvent and CallFunction hook target evidence,
runtime ProcessEvent context, and live CallFunction Lua dispatch evidence before
live Lua dispatch is considered complete; older or self-test-only readiness
stays at hook-probe/live-hook.
EOF

readelf -d "$loader" > "$stage/abi/readelf-dynamic.txt"
objdump -T "$loader" | grep -E 'GLIBC|GLIBCXX|CXXABI|GCC_' | sort -u > "$stage/abi/symbol-versions.txt" || true
file "$loader" > "$stage/abi/file.txt"

(
  cd "$stage"
  find . -type f ! -name SHA256SUMS -print | sort | sed 's#^\./##' | xargs sha256sum > SHA256SUMS
)

tar -C "$dist_root" -czf "$archive" "$package_name"
sha256sum "$archive" > "${archive}.sha256"
python3 "$repo_root/scripts/verify-loader-artifacts.py" \
  --target linux-server \
  --package-root "$stage" \
  --package-target linux-server \
  --package-archive "$archive" \
  --package-only \
  --format text > "${archive}.verification.txt"
python3 "$repo_root/scripts/verify-loader-artifacts.py" \
  --target linux-server \
  --package-root "$stage" \
  --package-target linux-server \
  --package-archive "$archive" \
  --package-only \
  --format json > "${archive}.verification.json"

printf 'packaged Linux server loader: %s\n' "$archive"
printf 'package checksum: %s\n' "${archive}.sha256"
printf 'package verification: %s\n' "${archive}.verification.json"
