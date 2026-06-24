#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-route-evidence/v1"

DEFAULT_ROUTES = (
    ("package-loader-vtables", "package-loader-vtables", "build/server-ue-package-loader-vtables.json"),
    ("package-wrapper-candidates", "package-wrapper-candidates", "build/server-ue-package-wrapper-candidates-fasyncpackage2.json"),
    ("static-wrapper-candidates", "static-wrapper-candidates", "build/server-ue-package-static-wrapper-candidates-focused.json"),
    ("symbol-surface-callgraph", "callgraph", "build/server-ue-package-symbol-surface-callgraph.json"),
    ("async-package-delegate-callgraph", "callgraph", "build/server-ue-async-package-delegate-callgraph-indirect.json"),
    ("streamable-reviewed-callgraph", "callgraph", "build/server-ue-streamable-reviewed-table-slots-callgraph.json"),
    ("kismet-loadasset-callgraph", "callgraph", "build/server-ue-kismet-loadasset-callgraph.json"),
    ("raw-typeinfo-linker-async-vtables", "rtti-vtables", "build/server-ue-raw-typeinfo-linker-async-vtables.json"),
    ("raw-typeinfo-linker-async-callgraph", "callgraph", "build/server-ue-raw-typeinfo-linker-async-callgraph.json"),
    ("writable-global-dispatch", "writable-globals", "build/server-elf-writable-global-refs-package-dispatch.json"),
    ("runtime-method-route-review", "method-route-review", "build/server-current-anchor-prep/ue4ss-package-method-route-review.json"),
    ("source-xref-review", "source-xref-review", "build/server-current-anchor-prep/ue4ss-package-source-xref-review.json"),
    ("static-metadata-recovery", "static-metadata-recovery", "build/server-current-anchor-prep/ue4ss-package-static-metadata-recovery.json"),
)

REVIEW_LEAD_PRIORITIES = {
    "package-loader-owner-function": 15,
    "loadasset-owner-surface": 10,
    "streamable-request": 40,
}

REVIEW_VTABLE_OWNER_PRIORITIES = {
    "FLinkerLoad": 5,
    "FAsyncPackage": 6,
    "FAsyncPackage2": 7,
}

KNOWN_NON_PACKAGE_DISPATCH_GLOBALS = {
    "0x165f50f8": "FMalloc proxy singleton; initialized via FMallocPoisonProxy/FMallocThreadSafeProxy path, allocator dispatch not package loading",
}

KNOWN_NON_PACKAGE_FUNCTIONS = {
    "0x128ce8d0": "FLoadAssetActionBase dispatch; virtual slot resolves to owner-surface assert/log path at 0x128cea80, not package loading",
    "0x128cea80": "FLoadAssetActionBase owner-surface assert/log path; bounded callgraph reaches KismetSystemLibrary.cpp logging with no package anchors",
    "0x9598a00": "common delegate predicate thunk reused by streamable/async delegate tables; not a package-loading ABI",
    "0x959fd80": "shared TFunction type-erasure helper/no-op method reused by package-loader owner-function RTTI rows; not a package-loading ABI",
    "0xa02fc00": "FStreamableHandle shared-pointer/reference-controller thunk; not a package-loading ABI",
    "0xa54f700": "streamable-reviewed slot decompile shows hash/map delta bookkeeping and no StaticLoadObject/LoadPackage-equivalent ABI",
    "0xa54f730": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa54f7e0": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa54f890": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa54f8c0": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa54f940": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa54f960": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa54f990": "streamable-reviewed slot collapses into 0xa54f700 hash/map delta bookkeeping, not package loading",
    "0xa8eab40": "streamable-reviewed offset decompiles as bad instruction/data, not a callable package-loading ABI",
    "0xa8eab60": "streamable-reviewed offset decompiles as no-op stub, not package loading",
    "0xa8eabe0": "streamable-reviewed slot decompile parses class/struct type text and builds reflection metadata, not package loading",
    "0xa8eac80": "streamable-reviewed slot collapses into class/struct reflection parser at 0xa8eabe0, not package loading",
    "0xa8eacc0": "streamable-reviewed slot collapses into class/struct reflection parser at 0xa8eabe0, not package loading",
    "0xa8ead30": "streamable-reviewed slot collapses into class/struct reflection parser at 0xa8eabe0, not package loading",
    "0x12de96e0": "streamable-reviewed offset decompiles as malformed control-flow/array bookkeeping, not a package-loading ABI",
    "0x9596cd0": "async-package delegate offset decompiles as bad instruction data, not a callable package-loading ABI",
    "0xf8a4190": "async-package delegate candidate decompiles with bad/discontinuous control-flow and no package-loading anchors",
    "0xf902440": "async-package delegate candidate is ICU/Unicode decimal-format setup, not package loading",
    "0x12de8ad0": "async-package delegate candidate is numeric/vector type conversion, not package loading",
    "0x12de8d70": "async-package delegate candidate is numeric/vector conversion jump-table helper, not package loading",
    "0x12de8f10": "async-package delegate candidate is a numeric/vector conversion thunk, not package loading",
    "0x12de9080": "async-package delegate candidate has no containing function in focused Ghidra import, not a callable package-loading ABI",
    "0x12de9160": "async-package delegate candidate copies converted numeric/vector arrays with capacity growth, not package loading",
    "0x12debae0": "async-package delegate candidate is malformed/overlapping control-flow around non-package helper logic",
    "0x12debf40": "async-package delegate candidate is non-package helper logic with no package anchor strings or load ABI",
    "0x12e1f520": "async-package delegate candidate performs logging/reader array handling and numeric reduction, not package loading",
    "0x9b04600": "FLinkerLoad slot decompile is malformed/vector math state update with no UObject/UClass/package ABI",
    "0x9b04610": "FLinkerLoad slot lands inside 0x9b04600 malformed/vector math state update, not package loading",
    "0x9b04860": "FLinkerLoad slot decompiles as vector interpolation/transform math, not package loading",
    "0xa206060": "FLinkerLoad slot decompiles as array/stride numeric loop with no package anchor ABI",
    "0xa206080": "FLinkerLoad slot lands inside 0xa206060 numeric loop, not package loading",
    "0xf944200": "FLinkerLoad slot decompiles as FString/UTF conversion buffer handling, not package loading",
    "0xf9443c0": "FLinkerLoad slot lands inside 0xf944200 string conversion buffer handling, not package loading",
    "0xf944610": "FLinkerLoad slot has no containing function in focused Ghidra import, not a callable package-loading ABI",
    "0xf944720": "FLinkerLoad slot has no containing function in focused Ghidra import, not a callable package-loading ABI",
    "0xf9449d0": "FLinkerLoad slot decompiles as small wrapper/finalizer around generic helper 0x147a5b90, not package loading",
    "0xf9449e0": "FLinkerLoad slot lands inside 0xf9449d0 small wrapper/finalizer, not package loading",
    "0xf946020": "FLinkerLoad slot decompiles as bad instruction/data stub, not a callable package-loading ABI",
    "0xf946040": "FLinkerLoad slot decompiles as guarded logging/name-format aggregation around helper calls, not StaticLoadObject/LoadPackage ABI",
    "0xf9460d0": "FLinkerLoad slot decompiles as trivial return stub, not package loading",
    "0xfb26a30": "FLinkerLoad slot decompiles as small flag/log helper call with malformed state, not package loading",
    "0xfb2a3f0": "FLinkerLoad slot decompiles as FArchive-style buffer serialization through vtable offset 0x170, not package loading",
    "0xfb2a400": "FLinkerLoad slot lands inside 0xfb2a3f0 serialization buffer helper, not package loading",
    "0xfb2c400": "FLinkerLoad slot decompiles as bulk serialization read/write loops through archive vtable offsets 0x120/0x170, not package loading",
    "0xfb2c450": "FLinkerLoad slot lands inside 0xfb2c400 bulk serialization read/write loop, not package loading",
    "0xfb2d7c0": "FLinkerLoad slot decompiles as serialization copy/read loop through archive vtable offsets 0x120/0x170, not package loading",
    "0xfb2e670": "FLinkerLoad slot decompiles as trivial return stub, not package loading",
    "0xfb2eb00": "FLinkerLoad slot decompiles as bitset/index reset and container cleanup logic, not package loading",
    "0xfb2eb20": "FLinkerLoad slot lands inside 0xfb2eb00 bitset/index reset logic, not package loading",
    "0xfb316a0": "FLinkerLoad slot decompiles as malformed small memory scribble stub, not package loading",
    "0xfb32d90": "FLinkerLoad slot decompiles as subsystem/static registration and logging/name lookup initialization, not package loading",
    "0xfb343a0": "FLinkerLoad slot decompiles as bad instruction/data stub, not a callable package-loading ABI",
    "0xfb344a0": "FLinkerLoad slot decompiles as shared-pointer/resource assignment and refcount cleanup, not package loading",
    "0xfb344c0": "FLinkerLoad slot lands inside 0xfb344a0 shared-pointer/resource assignment path, not package loading",
    "0xfb345c0": "FLinkerLoad slot lands inside 0xfb344a0 shared-pointer/resource assignment path, not package loading",
    "0xfb347c0": "FLinkerLoad slot decompiles as archive field reads gated by version offsets, not package loading",
    "0xfb347e0": "FLinkerLoad slot lands inside 0xfb347c0 archive field read path, not package loading",
    "0xfb34840": "FLinkerLoad slot lands inside 0xfb347c0 archive field read path, not package loading",
    "0xfb348b0": "FLinkerLoad slot lands inside 0xfb347c0 archive field read path, not package loading",
    "0xfb34910": "FLinkerLoad slot lands inside 0xfb347c0 archive field read path, not package loading",
    "0xfb34980": "FLinkerLoad slot decompiles as repeated archive scalar field reads, not package loading",
    "0xfb349d0": "FLinkerLoad slot lands inside 0xfb34980 repeated archive scalar field read path, not package loading",
    "0xfb34e50": "FLinkerLoad slot decompiles as archive-backed import/export metadata lookup and cleanup through internal virtual calls, not a stable StaticLoadObject/LoadPackage ABI",
    "0xfb353b0": "FLinkerLoad slot decompiles as guarded linker/archive helper orchestration with internal virtual calls and cleanup, not a public package-loading ABI",
    "0xfb359f0": "FLinkerLoad slot decompiles as small cleanup thunk around generic free helper, not package loading",
    "0xfb38b40": "FLinkerLoad slot decompiles as container/index bookkeeping and linker table mutation, not StaticLoadObject/LoadPackage ABI",
    "0xfb38d70": "FLinkerLoad slot lands inside 0xfb38b40 container/index bookkeeping path, not package loading",
    "0xfb38ed0": "FLinkerLoad slot decompiles as bad instruction/data stub, not a callable package-loading ABI",
    "0xfb38f60": "FLinkerLoad slot decompiles as small counter decrement thunk, not package loading",
    "0xfa53d40": "FAsyncPackage slot decompiles as bitstream/array serialization and vectorized bit packing logic, not package loading",
    "0xfa5c200": "FAsyncPackage slot decompiles as malformed byte-buffer write helper, not package loading",
    "0xfa7ab10": "FAsyncPackage2 slot decompiles as bad instruction/data stub, not a callable package-loading ABI",
    "0x95a3e40": "boot-load object/class data slot decompiles as bad instruction/data, not a callable package-loading ABI",
    "0xa01aa10": "boot-load object/class data slot decompiles as tiny generic cleanup helper, not package loading",
    "0xa01aa20": "boot-load object/class data slot decompiles as a small vtable setup/constructor helper, not package loading",
    "0xa01aa30": "boot-load object/class data slot lands inside 0xa01aa20 vtable setup helper, not package loading",
    "0xa01ab90": "boot-load object/class data slot decompiles as trap/assert-style thunk after a helper call, not a package-loading ABI",
    "0xa01ad50": "boot-load object/class data slot decompiles as refcounted object-state propagation and completion notification, not StaticLoadObject/LoadPackage ABI",
    "0xa01ad60": "boot-load object/class data slot lands inside 0xa01ad50 object-state propagation path, not package loading",
    "0xa01ad70": "boot-load object/class data slot lands inside 0xa01ad50 object-state propagation path, not package loading",
    "0xa01add0": "boot-load object/class data slot lands inside 0xa01ad50 object-state propagation path, not package loading",
    "0xa01ae90": "boot-load object/class data slot decompiles as malformed trap/bad-control-flow thunk, not package loading",
    "0xa01af50": "boot-load object/class data slot decompiles as typed setup and validation helper calls with no UObject/UClass package-load ABI",
    "0xa01b990": "boot-load object/class data slot decompiles as large boot-load data preparation/copy path, not a stable package-loading ABI",
    "0xa01c830": "boot-load object/class data slot decompiles as cleanup/lookup orchestration around boot-load data structures, not package loading",
    "0xbfca800": "boot-load object/class data slot decompiles as large vectorized asset-data serialization/copy routine, not StaticLoadObject/LoadPackage ABI",
    "0xbfca860": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfca8c0": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcaa70": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcaad0": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcad90": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcadc0": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcae20": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcae80": "boot-load object/class data slot lands inside 0xbfca800 vectorized asset-data serialization/copy routine, not package loading",
    "0xbfcb030": "boot-load object/class data slot decompiles as continuation of vectorized geometry/array construction with capacity growth, not StaticLoadObject/LoadPackage ABI",
    "0xbfcb090": "boot-load object/class data slot lands inside 0xbfcb030 vectorized geometry/array construction path, not package loading",
    "0xbfcc1a0": "boot-load object/class data slot decompiles as lazy singleton/global initialization, not package loading",
    "0xbfcc1b0": "boot-load object/class data slot lands inside 0xbfcc1a0 lazy singleton/global initialization, not package loading",
    "0xbfcc1c0": "boot-load object/class data slot lands inside 0xbfcc1a0 lazy singleton/global initialization, not package loading",
    "0xbfcc300": "boot-load object/class data slot decompiles as thunk into cleanup/destructor path, not package loading",
    "0xbfcc310": "boot-load object/class data slot lands inside 0xbfcc30a cleanup/destructor path, not package loading",
    "0xbfcc320": "boot-load object/class data slot lands inside 0xbfcc30a cleanup/destructor path, not package loading",
    "0xbfcc330": "boot-load object/class data slot lands inside 0xbfcc30a cleanup/destructor path, not package loading",
    "0xbfcc340": "boot-load object/class data slot lands inside 0xbfcc30a cleanup/destructor path, not package loading",
    "0xbfcc370": "boot-load object/class data slot decompiles as object cleanup/destructor helper with vtable field setup and free calls, not package loading",
    "0xbfcc380": "boot-load object/class data slot lands inside 0xbfcc370 object cleanup/destructor helper, not package loading",
    "0xbfcc3d0": "boot-load object/class data slot lands inside 0xbfcc370 object cleanup/destructor helper, not package loading",
    "0xbfcc410": "boot-load object/class data slot decompiles as object cleanup/destructor helper with vtable field setup and free calls, not package loading",
}


def load_json(path):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def route_status(route_id, kind, path):
    data = load_json(path)
    if data is None:
        return {
            "id": route_id,
            "kind": kind,
            "path": str(path),
            "present": False,
            "promotable": False,
            "finding": "missing",
            "summary": "artifact is missing or unreadable",
            "blockers": ["missing artifact"],
        }
    schema = data.get("schemaVersion", "")
    blockers = []
    metrics = {"schemaVersion": schema}
    promotable = False
    finding = "negative"
    summary = "no promotable package-loading anchor evidence"
    if kind == "callgraph":
        package_nodes = int(data.get("packageAnchorNodeCount", 0) or 0)
        allocator_nodes = count_known_non_package_dispatch_nodes(data)
        promotable = bool(data.get("promotableAsPackageAnchor", False))
        blockers = list(data.get("promotionBlockers", []) or [])
        if allocator_nodes and not promotable:
            reasons = known_non_package_dispatch_reasons(data)
            blockers.append(f"{allocator_nodes} indirect dispatch node(s) match known non-package path(s)")
            blockers.extend(reasons[:2])
        metrics.update(
            {
                "nodeCount": int(data.get("nodeCount", 0) or 0),
                "edgeCount": int(data.get("edgeCount", 0) or 0),
                "packageAnchorNodeCount": package_nodes,
                "streamableNodeCount": int(data.get("streamableNodeCount", 0) or 0),
                "knownNonPackageDispatchNodeCount": allocator_nodes,
            }
        )
        summary = f"bounded callgraph packageAnchorNodeCount={package_nodes}"
    elif kind == "rtti-vtables":
        promotable_count = int(data.get("promotablePackageAnchorCount", 0) or 0)
        promotable = promotable_count > 0
        metrics.update(
            {
                "rowCount": int(data.get("rowCount", 0) or 0),
                "vtableCount": int(data.get("vtableCount", 0) or 0),
                "methodSlotCount": int(data.get("methodSlotCount", 0) or 0),
                "promotablePackageAnchorCount": promotable_count,
                "leadKindCounts": dict(data.get("leadKindCounts", {}) or {}),
            }
        )
        summary = f"RTTI/vtable leads={metrics['rowCount']} promotable={promotable_count}"
        blockers = [data.get("promotionRule", "requires decompile/runtime call-frame proof")]
    elif kind == "package-loader-vtables":
        metrics.update(
            {
                "vtableCount": int(data.get("vtableCount", 0) or 0),
                "executableSlotCount": int(data.get("executableSlotCount", 0) or 0),
            }
        )
        summary = (
            f"package-loader vtables={metrics['vtableCount']} executableSlots={metrics['executableSlotCount']}"
        )
        blockers = ["package-loader vtable methods do not prove StaticLoadObject/StaticLoadClass ABI"]
    elif kind == "package-wrapper-candidates":
        direct_calls = int(data.get("directCallsiteCount", 0) or 0)
        targets_with_calls = int(data.get("targetsWithDirectCalls", 0) or 0)
        metrics.update(
            {
                "directCallsiteCount": direct_calls,
                "methodTargetCount": int(data.get("methodTargetCount", 0) or 0),
                "targetsWithDirectCalls": targets_with_calls,
            }
        )
        summary = f"wrapper candidates directCallsiteCount={direct_calls} targetsWithDirectCalls={targets_with_calls}"
        blockers = [data.get("nonPromotableWithoutWrapperReason", "no promotable wrapper ABI")]
    elif kind == "static-wrapper-candidates":
        exec_count = int(data.get("executableSymbolCandidateCount", 0) or 0)
        strings_with_refs = int(data.get("stringsWithCodeRefs", 0) or 0)
        metrics.update(
            {
                "executableSymbolCandidateCount": exec_count,
                "stringHitCount": int(data.get("stringHitCount", 0) or 0),
                "stringsWithCodeRefs": strings_with_refs,
                "stringsWithPointerSlots": int(data.get("stringsWithPointerSlots", 0) or 0),
            }
        )
        summary = f"static wrappers executableSymbolCandidateCount={exec_count} stringsWithCodeRefs={strings_with_refs}"
        blockers = [data.get("promotionRule", "no executable package wrapper symbol candidate")]
    elif kind == "writable-globals":
        exact_hints = dict(data.get("exactAnchorHintCounts", {}) or {})
        metrics.update(
            {
                "targetCount": int(data.get("targetCount", 0) or 0),
                "reportedTargetCount": int(data.get("reportedTargetCount", 0) or 0),
                "exactAnchorHintCounts": exact_hints,
            }
        )
        summary = f"writable/global refs targetCount={metrics['targetCount']} exactHints={sum(exact_hints.values()) if exact_hints else 0}"
        blockers = ["writable/global refs did not identify target-image package-loading entry ABI"]
    elif kind == "method-route-review":
        reviewed_routes = data.get("reviewedRoutes", []) or []
        reviewed_route_count = len(reviewed_routes) if isinstance(reviewed_routes, list) else 0
        non_promotable = sum(
            1
            for row in reviewed_routes
            if isinstance(row, dict) and row.get("finding") == "non-promotable"
        )
        metrics.update(
            {
                "methodHitCount": int(data.get("methodHitCount", 0) or 0),
                "packageHitCount": int(data.get("packageHitCount", 0) or 0),
                "reviewedRouteCount": reviewed_route_count,
                "nonPromotableRouteCount": non_promotable,
            }
        )
        summary = (
            f"runtime method routes reviewed={reviewed_route_count} "
            f"methodHits={metrics['methodHitCount']} packageHits={metrics['packageHitCount']}"
        )
        blockers = [
            row.get("reason", "runtime method route is not promotable package evidence")
            for row in reviewed_routes
            if isinstance(row, dict) and row.get("finding") == "non-promotable"
        ] or ["method route review did not produce promotable package ABI evidence"]
    elif kind == "source-xref-review":
        reviewed_routes = data.get("routes", []) or []
        reviewed_route_count = len(reviewed_routes) if isinstance(reviewed_routes, list) else 0
        non_promotable = sum(
            1
            for row in reviewed_routes
            if isinstance(row, dict) and row.get("finding") == "non-promotable"
        )
        promotable = bool(data.get("promotable", False))
        metrics.update(
            {
                "reviewedRouteCount": reviewed_route_count,
                "nonPromotableRouteCount": non_promotable,
                "packageHitCount": int(data.get("packageHitCount", 0) or 0),
            }
        )
        for row in reviewed_routes:
            if not isinstance(row, dict):
                continue
            row_metrics = row.get("metrics", {}) or {}
            for key in (
                "nodeCount",
                "edgeCount",
                "packageAnchorNodeCount",
                "focusedStringsWithCodeRefs",
                "focusedExecutableSymbolCandidateCount",
                "broadStringsWithCodeRefs",
                "broadExecutableSymbolCandidateCount",
            ):
                if key in row_metrics:
                    metrics[f"{row.get('id', 'route')}.{key}"] = row_metrics[key]
        summary = (
            f"source/loadobject routes reviewed={reviewed_route_count} "
            f"nonPromotable={non_promotable}"
        )
        blockers = list(data.get("blockers", []) or []) or [
            row.get("reason", "source/loadobject xref route is not promotable package evidence")
            for row in reviewed_routes
            if isinstance(row, dict) and row.get("finding") == "non-promotable"
        ] or ["source/loadobject xref review did not produce promotable package ABI evidence"]
    elif kind == "static-metadata-recovery":
        debug_lines = data.get("debugLines", {}) or {}
        symbol_anchors = data.get("symbolAnchors", {}) or {}
        source_context = data.get("sourcePointerContext", {}) or {}
        promotable = bool(data.get("complete", False))
        metrics.update(
            {
                "debugLineCount": int(debug_lines.get("lineCount", 0) or 0),
                "anchorSymbolCount": int(symbol_anchors.get("anchorSymbolCount", 0) or 0),
                "sourcePointerContextCount": int(source_context.get("contextCount", 0) or 0),
                "sourcePointerTargetCount": int(source_context.get("targetCount", 0) or 0),
            }
        )
        summary = (
            f"static metadata debugLines={metrics['debugLineCount']} "
            f"anchorSymbols={metrics['anchorSymbolCount']} "
            f"sourceContexts={metrics['sourcePointerContextCount']}"
        )
        blockers = list(data.get("blockers", []) or []) or [
            "static metadata recovery did not produce a package-loading target function"
        ]
    if promotable:
        finding = "promotable"
        summary = "route contains promotable package-loading evidence"
    return {
        "id": route_id,
        "kind": kind,
        "path": str(path),
        "present": True,
        "promotable": promotable,
        "finding": finding,
        "summary": summary,
        "metrics": metrics,
        "blockers": blockers,
    }


def hex_int(value):
    if value is None:
        return None
    try:
        return int(str(value), 16)
    except ValueError:
        return None


def add_review_entry(entries, route_id, kind, priority, address, label, reason, extra=None):
    if not address:
        return
    entry = {
        "route": route_id,
        "kind": kind,
        "priority": priority,
        "address": str(address),
        "label": label,
        "reason": reason,
    }
    if extra:
        entry.update(extra)
    entries.append(entry)


def rtti_slot_priority(base_priority, slot):
    priority = base_priority
    if slot.get("candidateKind") == "function-object-dispatch":
        priority -= 3
    shape = slot.get("shape", {}) or {}
    if shape.get("hasIndirectCall"):
        priority -= 2
    elif shape.get("hasCall"):
        priority -= 1
    return priority


def known_non_package_dispatch_reason(node):
    function = str(node.get("function", "")).lower()
    seed_name = str(node.get("seedName", ""))
    if "function_object_dispatch" in seed_name:
        return "TFunction function_object_dispatch seed is type-erasure dispatch, not a stable package-loading ABI"
    if function in KNOWN_NON_PACKAGE_FUNCTIONS:
        return KNOWN_NON_PACKAGE_FUNCTIONS[function]
    for ref in node.get("refs", []) or []:
        target = str(ref.get("target", "")).lower()
        if target in KNOWN_NON_PACKAGE_DISPATCH_GLOBALS:
            return KNOWN_NON_PACKAGE_DISPATCH_GLOBALS[target]
    return ""


def count_known_non_package_dispatch_nodes(data):
    return sum(1 for node in data.get("nodes", []) or [] if known_non_package_dispatch_reason(node))


def known_non_package_dispatch_reasons(data):
    reasons = []
    for node in data.get("nodes", []) or []:
        reason = known_non_package_dispatch_reason(node)
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def review_queue_for_rtti_vtables(route_id, data):
    entries = []
    for row_index, row in enumerate(data.get("rows", []) or []):
        lead_kind = row.get("leadKind", "")
        if lead_kind not in REVIEW_LEAD_PRIORITIES:
            continue
        owner = "; ".join(row.get("owners", []) or []) or row.get("demangledTypeinfo", "")
        base_priority = REVIEW_LEAD_PRIORITIES[lead_kind]
        for vtable_index, vtable in enumerate(row.get("vtables", []) or []):
            for slot in vtable.get("slots", []) or []:
                candidate_kind = slot.get("candidateKind", "")
                if candidate_kind == "function-object-dispatch":
                    continue
                if candidate_kind != "method":
                    continue
                shape = slot.get("shape", {}) or {}
                if not shape.get("hasCall") and not shape.get("hasIndirectCall"):
                    continue
                target = slot.get("value") or slot.get("target")
                if str(target).lower() in KNOWN_NON_PACKAGE_FUNCTIONS:
                    continue
                slot_index = slot.get("index")
                add_review_entry(
                    entries,
                    route_id,
                    "decompile-rtti-vtable-slot",
                    rtti_slot_priority(base_priority, slot),
                    target,
                    f"{lead_kind} row {row_index} vtable {vtable_index} slot {slot_index}",
                    "decompile this function-object/vtable target to prove whether it calls a stable package/load-object ABI",
                    {
                        "leadKind": lead_kind,
                        "candidateKind": candidate_kind,
                        "owner": owner,
                        "slotIndex": slot_index,
                    },
                )
    return entries


def review_queue_for_package_loader_vtables(route_id, data):
    entries = []
    for row in data.get("rows", []) or []:
        owner = row.get("demangled", "")
        priority = 60
        for owner_hint, owner_priority in REVIEW_VTABLE_OWNER_PRIORITIES.items():
            if owner_hint in owner:
                priority = owner_priority
                break
        for slot in row.get("executableSlots", []) or []:
            if slot.get("candidateKind") != "method":
                continue
            shape = slot.get("shape", {}) or {}
            if not shape.get("hasCall") and not shape.get("hasIndirectCall"):
                continue
            target = slot.get("value") or slot.get("target")
            if str(target).lower() in KNOWN_NON_PACKAGE_FUNCTIONS:
                continue
            slot_priority = priority
            if shape.get("hasIndirectCall"):
                slot_priority -= 1
            if int(slot.get("directControlTargetCount", 0) or 0) > 0:
                slot_priority -= 1
            add_review_entry(
                entries,
                route_id,
                "decompile-package-loader-vtable-slot",
                slot_priority,
                target,
                f"{owner} slot {slot.get('index')}",
                "decompile package-loader method to locate caller/callee edge to StaticLoadObject/LoadPackage-equivalent ABI",
                {
                    "candidateKind": slot.get("candidateKind"),
                    "owner": owner,
                    "slotIndex": slot.get("index"),
                },
            )
    return entries


def review_queue_for_callgraph(route_id, data):
    entries = []
    for node in data.get("nodes", []) or []:
        indirect_calls = node.get("indirectCalls", []) or []
        if not indirect_calls:
            continue
        non_package_reason = known_non_package_dispatch_reason(node)
        if non_package_reason:
            continue
        seed_name = node.get("seedName", "")
        priority = 50
        if "LoadAsset" in seed_name or "loadasset" in route_id:
            priority = 1
        elif "streamable" in route_id:
            priority = 40
        elif "raw-typeinfo" in route_id:
            priority = 20
        add_review_entry(
            entries,
            route_id,
            "decompile-indirect-call-node",
            priority,
            node.get("function"),
            seed_name or node.get("function", ""),
            "decompile indirect-call site(s) to recover dynamic target and call-frame contract",
            {
                "indirectCallCount": len(indirect_calls),
                "indirectCalls": indirect_calls[:4],
                "path": node.get("path", []),
            },
        )
    return entries


def suppressed_known_non_package_queue(routes, limit=None):
    entries = []
    for route_id, kind, path_text in routes:
        if kind != "callgraph":
            continue
        data = load_json(Path(path_text))
        if data is None:
            continue
        for node in data.get("nodes", []) or []:
            indirect_calls = node.get("indirectCalls", []) or []
            if not indirect_calls:
                continue
            reason = known_non_package_dispatch_reason(node)
            if not reason:
                continue
            add_review_entry(
                entries,
                route_id,
                "suppressed-known-non-package-indirect-call-node",
                100,
                node.get("function"),
                node.get("seedName", "") or node.get("function", ""),
                reason,
                {
                    "indirectCallCount": len(indirect_calls),
                    "indirectCalls": indirect_calls[:4],
                    "path": node.get("path", []),
                },
            )
    entries.sort(
        key=lambda row: (
            row.get("route", ""),
            hex_int(row.get("address")) if hex_int(row.get("address")) is not None else 1 << 80,
            row.get("label", ""),
        )
    )
    if limit is not None:
        return entries[:limit]
    return entries


def build_decompile_review_queue(routes, limit=None):
    entries = []
    for route_id, kind, path_text in routes:
        data = load_json(Path(path_text))
        if data is None:
            continue
        if kind == "rtti-vtables":
            entries.extend(review_queue_for_rtti_vtables(route_id, data))
        elif kind == "package-loader-vtables":
            entries.extend(review_queue_for_package_loader_vtables(route_id, data))
        elif kind == "callgraph":
            entries.extend(review_queue_for_callgraph(route_id, data))
    entries.sort(
        key=lambda row: (
            int(row.get("priority", 999)),
            hex_int(row.get("address")) if hex_int(row.get("address")) is not None else 1 << 80,
            row.get("route", ""),
            row.get("label", ""),
        )
    )
    deduped = []
    by_key = {}
    for entry in entries:
        key = (entry.get("route"), entry.get("kind"), entry.get("address"))
        existing = by_key.get(key)
        if existing is not None:
            existing["occurrenceCount"] = int(existing.get("occurrenceCount", 1)) + 1
            labels = existing.setdefault("labels", [existing.get("label", "")])
            if entry.get("label") and entry.get("label") not in labels:
                labels.append(entry.get("label"))
            if int(entry.get("priority", 999)) < int(existing.get("priority", 999)):
                existing["priority"] = entry["priority"]
                existing["label"] = entry["label"]
            continue
        entry["occurrenceCount"] = 1
        by_key[key] = entry
        deduped.append(entry)
    deduped.sort(
        key=lambda row: (
            int(row.get("priority", 999)),
            hex_int(row.get("address")) if hex_int(row.get("address")) is not None else 1 << 80,
            row.get("route", ""),
            row.get("label", ""),
        )
    )
    if limit is not None:
        return deduped[:limit]
    return deduped


def parse_route_arg(value):
    parts = value.split("=", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("route must be ID=KIND=PATH")
    return parts[0], parts[1], parts[2]


def summarize(routes, review_limit=20):
    route_rows = [route_status(route_id, kind, Path(path)) for route_id, kind, path in routes]
    promotable = [row for row in route_rows if row.get("promotable")]
    missing = [row for row in route_rows if not row.get("present")]
    review_queue = build_decompile_review_queue(routes, review_limit)
    suppressed_queue = suppressed_known_non_package_queue(routes, review_limit)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "routeCount": len(route_rows),
        "presentRouteCount": len(route_rows) - len(missing),
        "promotableRouteCount": len(promotable),
        "complete": bool(promotable),
        "routes": route_rows,
        "decompileReviewQueue": review_queue,
        "decompileReviewQueueCount": len(review_queue),
        "suppressedKnownNonPackageQueue": suppressed_queue,
        "suppressedKnownNonPackageQueueCount": len(suppressed_queue),
        "nextStep": (
            "promote reviewed package-loading anchor and run guarded native LoadAsset/LoadClass invocation"
            if promotable
            else "all tracked static/package-adjacent routes are non-promotable; use decompile/runtime call-frame proof or external symbols to identify StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName"
        ),
    }


def markdown(summary):
    lines = ["# UE4SS Package Route Evidence", ""]
    lines.append(f"- Routes: `{summary['routeCount']}`")
    lines.append(f"- Present routes: `{summary['presentRouteCount']}`")
    lines.append(f"- Promotable routes: `{summary['promotableRouteCount']}`")
    lines.append(f"- Complete package route: `{str(summary['complete']).lower()}`")
    lines.append(f"- Decompile review queue: `{summary.get('decompileReviewQueueCount', 0)}`")
    lines.append(f"- Suppressed known non-package queue: `{summary.get('suppressedKnownNonPackageQueueCount', 0)}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    lines.append("")
    lines.append("## Routes")
    lines.append("")
    for row in summary.get("routes", []):
        lines.append(
            f"- `{row['finding']}` `{row['id']}` kind=`{row['kind']}` path=`{row['path']}`"
        )
        lines.append(f"  - {row['summary']}")
        for blocker in row.get("blockers", [])[:2]:
            if blocker:
                lines.append(f"  - blocker: {blocker}")
    queue = summary.get("decompileReviewQueue", [])
    if queue:
        lines.append("")
        lines.append("## Decompile Review Queue")
        lines.append("")
        for entry in queue:
            lines.append(
                f"- priority `{entry['priority']}` `{entry['address']}` "
                f"{entry['kind']} route=`{entry['route']}`"
            )
            lines.append(f"  - {entry['label']}")
            lines.append(f"  - reason: {entry['reason']}")
    suppressed = summary.get("suppressedKnownNonPackageQueue", [])
    if suppressed:
        lines.append("")
        lines.append("## Suppressed Known Non-Package Queue")
        lines.append("")
        for entry in suppressed:
            lines.append(
                f"- `{entry['address']}` {entry['kind']} route=`{entry['route']}`"
            )
            lines.append(f"  - {entry['label']}")
            lines.append(f"  - reason: {entry['reason']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize UE4SS package-loading route evidence artifacts.")
    parser.add_argument("--route", action="append", type=parse_route_arg, default=[])
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--review-limit", type=int, default=20)
    args = parser.parse_args(argv)
    routes = args.route or list(DEFAULT_ROUTES)
    summary = summarize(routes, args.review_limit)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
