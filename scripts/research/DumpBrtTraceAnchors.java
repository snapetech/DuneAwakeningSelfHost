// Ghidra headless script: emit build-current trace offsets for the Phase-1
// BRT-in-Deep-Desert keystone trace (docs/brt-deep-desert-plan.md, Phase 1).
//
// Unlike FindBaseBackupToolDeepDesert.java (broad discovery), this prints a
// short, copy-paste set of offsets the live trace needs to answer the two
// gating unknowns:
//   1. client-vs-server block  -> the BRT place RPC server entry
//   2. did the config land      -> the function(s) that read the map restriction
//   plus the player-visible "not allowed in the region" emitter (Phase 2).
//
// Offsets are printed relative to the program image base, which is 0 for this
// server binary, so they can be pasted straight into the trace env vars
// (BRT_RPC_PLACE_OFFSET, BRT_RESTRICTION_GATE_OFFSET) used by
// scripts/trace-brt-place-live.sh.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpBrtTraceAnchors.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/brt-trace-anchors-ghidra.log
//
// Output:
//   ${BRT_TRACE_ANCHORS_FILE:-${DUNE_GHIDRA_WORK_DIR:-/tmp/ghidra-work}/brt-trace-anchors.txt}
//
// @category Reverse Engineering

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class DumpBrtTraceAnchors extends GhidraScript {
    // Each anchor: trace env var the operator should set, plus the strings whose
    // xref functions we report. The first string that resolves to a single
    // containing function wins for the headline offset; all hits are listed.
    private static final String[][] ANCHORS = new String[][] {
        // env var, role, strings...
        {"BRT_RPC_PLACE_OFFSET", "BRT place request server entry (Phase 1: did the request reach the server)",
            "ServerRequestBaseBackup_Implementation", "ServerRequestBaseBackup"},
        {"BRT_RESTRICTION_GATE_OFFSET", "Map restriction read site (Phase 1/3: does the live array contain DeepDesert)",
            "m_BaseBackupToolMapRestriction"},
        {"BRT_REGION_REJECT_OFFSET", "Player-visible region reject emitter (Phase 2: the true 'not allowed in the region' site)",
            "not allowed in the region", "BaseBackupToolMapRestriction"},
    };

    private PrintWriter out;
    private ReferenceManager refs;
    private long imageBase;

    @Override
    public void run() throws Exception {
        String outPath = outputPath();
        File parent = new File(outPath).getParentFile();
        if (parent != null) {
            parent.mkdirs();
        }
        out = new PrintWriter(new FileWriter(outPath));
        refs = currentProgram.getReferenceManager();
        imageBase = currentProgram.getImageBase().getOffset();
        try {
            log("Output: " + outPath);
            log("Program: " + currentProgram.getName());
            log("Image base: 0x" + Long.toHexString(imageBase));
            log("");
            log("== Phase-1 BRT trace anchors (offsets are image-base-relative)");
            for (String[] anchor : ANCHORS) {
                dumpAnchor(anchor);
            }
            log("");
            log("== Paste into the trace, e.g.:");
            log("   BRT_RPC_PLACE_OFFSET=0x<...> BRT_RESTRICTION_GATE_OFFSET=0x<...> \\");
            log("     scripts/trace-brt-place-live.sh dune_server-deep-desert-1");
        } finally {
            out.close();
        }
    }

    private String outputPath() {
        String explicit = System.getenv("BRT_TRACE_ANCHORS_FILE");
        if (explicit != null && !explicit.isEmpty()) {
            return explicit;
        }
        String workDir = System.getenv("DUNE_GHIDRA_WORK_DIR");
        if (workDir == null || workDir.isEmpty()) {
            workDir = "/tmp/ghidra-work";
        }
        return workDir + "/brt-trace-anchors.txt";
    }

    private void dumpAnchor(String[] anchor) throws Exception {
        String env = anchor[0];
        String role = anchor[1];
        log("");
        log("-- " + env + "  (" + role + ")");
        Set<Long> headline = new LinkedHashSet<>();
        boolean any = false;
        for (int i = 2; i < anchor.length; i++) {
            String needle = anchor[i];
            List<Address> hits = findStringBytes(needle);
            if (hits.isEmpty()) {
                log("   string not found: \"" + needle + "\"");
                continue;
            }
            for (Address hit : hits) {
                Set<Address> entries = xrefFunctionEntries(hit, needle);
                if (entries.isEmpty()) {
                    log("   string \"" + needle + "\" @ " + hit + " has no function xref");
                    continue;
                }
                any = true;
                for (Address entry : entries) {
                    long rel = entry.getOffset() - imageBase;
                    headline.add(rel);
                    Function f = currentProgram.getFunctionManager().getFunctionContaining(entry);
                    String size = f == null ? "" : " size=" + f.getBody().getNumAddresses();
                    log(String.format("   string \"%s\" @ %s -> func entry 0x%x%s", needle, hit, rel, size));
                }
            }
        }
        if (!any) {
            log("   (no resolvable offset; this anchor needs manual review)");
            return;
        }
        if (headline.size() == 1) {
            log(String.format("   => %s=0x%x", env, headline.iterator().next()));
        } else {
            StringBuilder sb = new StringBuilder();
            for (long v : headline) sb.append(String.format(" 0x%x", v));
            log("   => candidates (pick the one that fires in the trace):" + sb);
        }
    }

    private Set<Address> xrefFunctionEntries(Address stringAddr, String needle) {
        Set<Address> entries = new LinkedHashSet<>();
        int span = needle.length() + 1;
        for (int i = 0; i <= span; i++) {
            Address probe = stringAddr.add(i);
            ReferenceIterator rit = refs.getReferencesTo(probe);
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                if (f != null) entries.add(f.getEntryPoint());
            }
        }
        return entries;
    }

    private List<Address> findStringBytes(String needle) {
        List<Address> hits = new ArrayList<>();
        Memory mem = currentProgram.getMemory();
        byte[][] encodings = new byte[][] {asciiBytes(needle), utf16Bytes(needle)};
        for (byte[] pattern : encodings) {
            Address start = mem.getMinAddress();
            Address max = mem.getMaxAddress();
            while (start != null && start.compareTo(max) <= 0) {
                Address hit = mem.findBytes(start, max, pattern, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                start = hit.add(1);
            }
        }
        return hits;
    }

    private byte[] asciiBytes(String value) {
        try {
            return value.getBytes("US-ASCII");
        } catch (Exception exc) {
            throw new RuntimeException(exc);
        }
    }

    private byte[] utf16Bytes(String value) {
        try {
            return value.getBytes("UTF-16LE");
        } catch (Exception exc) {
            throw new RuntimeException(exc);
        }
    }

    private void log(String line) {
        println(line);
        out.println(line);
    }
}
